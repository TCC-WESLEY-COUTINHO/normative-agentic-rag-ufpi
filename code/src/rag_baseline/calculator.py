"""Bounded Decimal/date calculator. No providers, evaluation engine, IO or clock."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext

from langchain_core.tools import StructuredTool

from rag_baseline.calculator_contracts import (
    SAFE_MESSAGES,
    ArithmeticRequest,
    CalculatorRequest,
    CalculatorToolInput,
    CalculatorToolResult,
    DateDifferenceRequest,
    DateOffsetRequest,
    RejectedRequest,
    answer_text,
)

MAX_INPUT = 512
MAX_TOKENS = 128
MAX_DEPTH = 16
MAX_DIGITS = 24
MAX_ABSOLUTE = Decimal("1e24")
MAX_OFFSET_DAYS = 3652058
DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-100, Emax=100)
NORMATIVE_MARKERS = re.compile(
    r"\b(?:art(?:igo)?\.?|resolu[cç][aã]o|norma(?:tiv[oa])?|regulamento|prazo|vig[eê]ncia|"
    r"revoga[cç][aã]o|altera[cç][aã]o|gradua[cç][aã]o|p[oó]s(?:-gradua[cç][aã]o)?|ufpi|"
    r"recurso|matr[ií]cula|cancelamento|trancamento|jur[ií]dic[oa]|lei|legal|"
    r"[uú]ltimo dia|primeiro dia|ci[eê]ncia|dies a quo)\b",
    re.I,
)
DATE = r"(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})"
OFFSET = re.compile(
    rf"(?:(?P<verb>adicione|some|subtraia) (?P<n>\d+) dias? corridos? (?:a|de) (?P<date>{DATE})"
    rf"|(?P<n2>\d+) dias? (?P<direction>depois|antes) de (?P<date2>{DATE}))"
)
DIFFERENCE = re.compile(rf"quantos dias (?:existem )?entre (?P<a>{DATE}) e (?P<b>{DATE})")
DATE_INTENT = re.compile(r"(?:\d+ dias?\b|(?:adicione|some|subtraia)\b|quantos dias\b)")
RELATIVE = re.compile(r"\b(?:hoje|amanh[aã]|ontem|pr[oó]xim[ao]|fim do m[eê]s)\b")


@dataclass(frozen=True)
class CalculatorIntent:
    is_calculator_intent: bool
    parsed_request: CalculatorRequest | None = None
    unsupported_reason: str | None = None
    normative_mix_detected: bool = False
    reason_code: str = "requires_normative_tool"


def _date(value):
    if "/" in value:
        day, month, year = map(int, value.split("/"))
        return date(year, month, day)
    return date.fromisoformat(value)


class CalculatorIntentParser:
    """Full-message grammar plus conservative normative veto, never number matching alone."""

    def parse(self, text: str) -> CalculatorIntent:
        text = unicodedata.normalize("NFC", text)
        # Scan the full input for normative markers before accepting a numeric prefix.
        if NORMATIVE_MARKERS.search(text):
            return CalculatorIntent(False, normative_mix_detected=True)
        normalized = text.strip().casefold()
        normalized = re.sub(r"\s+", " ", normalized).rstrip("?!.").rstrip()
        prefix = re.match(r"(?:quanto [eé]|calcule)\s+", normalized)
        expression = normalized[prefix.end() :] if prefix else normalized
        # A date reply to a clarification must not become division/subtraction.
        if not prefix and re.fullmatch(DATE, expression):
            return CalculatorIntent(False)
        normalized = expression
        date_intent = bool(DATE_INTENT.match(normalized))
        arithmetic = bool(re.fullmatch(r"[\d\s.(),+*/%<>\-]+", normalized))
        # Explicit calculation prefixes admit mathematical/code-shaped errors,
        # not arbitrary prose whose interpretation belongs to the normative path.
        unsupported_shape = bool(
            prefix
            and re.fullmatch(
                r"(?:[A-Za-z_]\w*\([^\n;]*\)|[A-Za-z_]\w*|"
                r"[A-Za-z_]\w*\s*[+*/\-]\s*[0-9.]+|"
                r"\[[^\n]*\]|\{[^\n]*\}|lambda\s*:\s*[0-9]+|\"[^\"]*\"|'[^']*')",
                expression,
            )
        )
        if not (date_intent or arithmetic or unsupported_shape):
            return CalculatorIntent(False)

        def rejected(code, kind=None):
            return CalculatorIntent(
                True,
                RejectedRequest(target_kind=kind, error_code=code),
                code,
                reason_code=f"calculator_{code}",
            )

        if len(text) > MAX_INPUT:
            return rejected("input_too_large")
        if date_intent:
            kind = "DATE_DIFFERENCE" if normalized.startswith("quantos dias") else "DATE_OFFSET"
            if re.search(r"\bdias? [uú]teis\b", normalized):
                return rejected("unsupported_business_days", kind)
            if "a partir de" in normalized:
                return rejected("ambiguous_date_offset", kind)
            if RELATIVE.search(normalized):
                return rejected("unsupported_relative_date", kind)
            try:
                match = OFFSET.fullmatch(normalized)
                if match:
                    amount = int(match["n"] or match["n2"])
                    if amount > MAX_OFFSET_DAYS:
                        return rejected("numeric_limit", kind)
                    if match["verb"] == "subtraia" or match["direction"] == "antes":
                        amount = -amount
                    request = DateOffsetRequest(
                        start_date=_date(match["date"] or match["date2"]), days=amount
                    )
                else:
                    match = DIFFERENCE.fullmatch(normalized)
                    if not match:
                        return rejected("unsupported_operation", kind)
                    request = DateDifferenceRequest(
                        start_date=_date(match["a"]), end_date=_date(match["b"])
                    )
            except ValueError:
                return rejected("invalid_date", kind)
            return CalculatorIntent(True, request, reason_code=f"calculator_{kind.lower()}")
        return CalculatorIntent(
            True, ArithmeticRequest(expression=expression), reason_code="calculator_arithmetic"
        )


class _MathError(Exception):
    def __init__(self, code):
        self.code = code


def _bounded(value):
    if not value.is_finite() or abs(value) > MAX_ABSOLUTE or (value and value.adjusted() < -100):
        raise _MathError("numeric_limit")
    return value


def _arithmetic(expression):
    """Recursive descent: sum -> product -> unary -> number | '(' sum ')'."""
    if len(expression) > MAX_INPUT:
        raise _MathError("input_too_large")
    if any(op in expression for op in ("**", "//", "<<", ">>", "%")):
        raise _MathError("unsupported_operation")
    tokens = []
    cursor = 0
    while cursor < len(expression):
        if expression[cursor].isspace():
            cursor += 1
            continue
        match = re.match(r"(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)|[()+*/\-]", expression[cursor:])
        if not match:
            raise _MathError("invalid_expression")
        token = match[0]
        if sum(c.isdigit() for c in token) > MAX_DIGITS:
            raise _MathError("numeric_limit")
        tokens.append(token)
        if len(tokens) > MAX_TOKENS:
            raise _MathError("expression_too_complex")
        cursor += len(token)
    position = 0

    def peek():
        return tokens[position] if position < len(tokens) else None

    def atom(depth):
        nonlocal position
        if depth > MAX_DEPTH:
            raise _MathError("expression_too_complex")
        token = peek()
        if token in ("+", "-"):
            position += 1
            value = atom(depth + 1)
            return value if token == "+" else -value
        if token == "(":
            position += 1
            value = addition(depth + 1)
            if peek() != ")":
                raise _MathError("invalid_expression")
            position += 1
            return value
        if token is None or token in (")", "*", "/"):
            raise _MathError("invalid_expression")
        position += 1
        return _bounded(Decimal(token))

    def product(depth):
        nonlocal position
        value = atom(depth)
        while peek() in ("*", "/"):
            operator = peek()
            position += 1
            right = atom(depth)
            if operator == "/" and right == 0:
                raise _MathError("division_by_zero")
            value = _bounded(value * right if operator == "*" else value / right)
        return value

    def addition(depth):
        nonlocal position
        value = product(depth)
        while peek() in ("+", "-"):
            operator = peek()
            position += 1
            right = product(depth)
            value = _bounded(value + right if operator == "+" else value - right)
        return value

    with localcontext(DECIMAL_CONTEXT):
        value = addition(0)
    if position != len(tokens):
        raise _MathError("invalid_expression")
    return value


def calculate(request: CalculatorRequest) -> CalculatorToolResult:
    """Execute only typed current-message parameters. Return safe, stable results."""
    request = CalculatorToolInput(request=request).request
    kind, normalized = request.operation_kind, ""
    if isinstance(request, RejectedRequest):
        kind = request.target_kind
    try:
        if isinstance(request, RejectedRequest):
            raise _MathError(request.error_code)
        numeric, day, days = None, None, None
        if isinstance(request, ArithmeticRequest):
            if len(request.expression) <= MAX_INPUT:
                normalized = re.sub(r"\s+", " ", request.expression).strip()
            numeric = _arithmetic(request.expression)
        elif isinstance(request, DateOffsetRequest):
            if abs(request.days) > MAX_OFFSET_DAYS:
                raise _MathError("numeric_limit")
            normalized = f"{request.start_date.isoformat()} {request.days:+d} days"
            day = request.start_date + timedelta(days=request.days)
        else:
            normalized = f"{request.end_date.isoformat()} - {request.start_date.isoformat()}"
            days = (request.end_date - request.start_date).days
        return CalculatorToolResult(
            status="ANSWER",
            operation_kind=kind,
            content=answer_text(kind, numeric, day, days),
            normalized_input=normalized,
            numeric_result=numeric,
            date_result=day,
            days_result=days,
        )
    except (_MathError, DecimalException, OverflowError, ValueError) as exc:
        code = (
            exc.code
            if isinstance(exc, _MathError)
            else ("invalid_date" if kind != "ARITHMETIC" else "numeric_limit")
        )
        return CalculatorToolResult(
            status="ERROR",
            operation_kind=kind,
            normalized_input=normalized,
            error_code=code,
            safe_message=SAFE_MESSAGES[code],
            content=SAFE_MESSAGES[code],
        )


def build_calculator_tool() -> StructuredTool:
    return StructuredTool.from_function(
        func=calculate,
        name="calculator",
        args_schema=CalculatorToolInput,
        description="Execute bounded arithmetic or absolute-date mathematics with explicit parameters.",
    )
