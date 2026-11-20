"""Typed mathematical requests/results, without normative authority or persistence."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

Operation = Literal["ARITHMETIC", "DATE_OFFSET", "DATE_DIFFERENCE"]
ErrorCode = Literal[
    "invalid_expression",
    "division_by_zero",
    "expression_too_complex",
    "unsupported_operation",
    "invalid_date",
    "unsupported_relative_date",
    "ambiguous_date_offset",
    "unsupported_business_days",
    "input_too_large",
    "numeric_limit",
]
SAFE_MESSAGES = {
    "invalid_expression": "Expressão inválida. Use números com ponto decimal, +, -, *, / e parênteses.",
    "division_by_zero": "Não é possível dividir por zero.",
    "expression_too_complex": "O cálculo é muito complexo. Divida-o em partes menores.",
    "unsupported_operation": "Operação não suportada. Use somente +, -, *, / e parênteses.",
    "invalid_date": "Data inválida ou resultado fora do intervalo de datas suportado.",
    "unsupported_relative_date": "Informe a data completa, por exemplo: 25/12/2026.",
    "ambiguous_date_offset": "Escreva, por exemplo: adicione 10 dias corridos a 25/12/2026.",
    "unsupported_business_days": "Cálculo de dias úteis não é suportado nesta versão.",
    "input_too_large": "A pergunta ficou muito longa. Envie um cálculo por vez.",
    "numeric_limit": "Um número ou resultado ultrapassa o limite da calculadora.",
}


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class ArithmeticRequest(_Contract):
    operation_kind: Literal["ARITHMETIC"] = "ARITHMETIC"
    expression: StrictStr


class DateOffsetRequest(_Contract):
    operation_kind: Literal["DATE_OFFSET"] = "DATE_OFFSET"
    start_date: date
    days: StrictInt


class DateDifferenceRequest(_Contract):
    operation_kind: Literal["DATE_DIFFERENCE"] = "DATE_DIFFERENCE"
    start_date: date
    end_date: date


class RejectedRequest(_Contract):
    operation_kind: Literal["REJECTED"] = "REJECTED"
    target_kind: Operation | None = None
    error_code: ErrorCode


CalculatorRequest = Annotated[
    ArithmeticRequest | DateOffsetRequest | DateDifferenceRequest | RejectedRequest,
    Field(discriminator="operation_kind"),
]


class CalculatorToolInput(_Contract):
    request: CalculatorRequest


def decimal_text(value: Decimal) -> str:
    if not value:
        return "0"
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def answer_text(kind, numeric, day, days):
    if kind == "ARITHMETIC" and numeric is not None:
        return decimal_text(numeric)
    if kind == "DATE_OFFSET" and day is not None:
        return f"{day.day:02d}/{day.month:02d}/{day.year:04d}"
    if kind == "DATE_DIFFERENCE" and days is not None:
        return f"Diferença entre as datas: {days} dias."
    raise ValueError("Missing mathematical result.")


class CalculatorToolResult(_Contract):
    contract_version: Literal["1"] = "1"
    status: Literal["ANSWER", "ERROR"]
    operation_kind: Operation | None
    content: StrictStr = Field(min_length=1)
    normalized_input: StrictStr = Field(max_length=512)
    numeric_result: Decimal | None = None
    date_result: date | None = None
    days_result: StrictInt | None = None
    error_code: ErrorCode | None = None
    safe_message: StrictStr | None = None

    @model_validator(mode="after")
    def coherent_result(self):
        values = [self.numeric_result, self.date_result, self.days_result]
        if self.status == "ERROR":
            if any(v is not None for v in values) or self.error_code is None:
                raise ValueError("Error must have a code and no mathematical result.")
            if (
                self.safe_message != SAFE_MESSAGES[self.error_code]
                or self.content != self.safe_message
            ):
                raise ValueError("Error must preserve the deterministic safe message.")
            return self
        if self.error_code is not None or self.safe_message is not None:
            raise ValueError("Answer cannot carry error fields.")
        expected = {"ARITHMETIC": 0, "DATE_OFFSET": 1, "DATE_DIFFERENCE": 2}.get(
            self.operation_kind
        )
        if expected is None or [v is not None for v in values] != [i == expected for i in range(3)]:
            raise ValueError("Answer must contain exactly the matching result field.")
        if self.numeric_result is not None and (
            not self.numeric_result.is_finite()
            or self.numeric_result.copy_abs() > Decimal("1e24")
            or (self.numeric_result and self.numeric_result.adjusted() < -100)
        ):
            raise ValueError("Numeric result outside calculator bounds.")
        if self.content != answer_text(self.operation_kind, *values):
            raise ValueError("Content must match the deterministic mathematical result.")
        return self
