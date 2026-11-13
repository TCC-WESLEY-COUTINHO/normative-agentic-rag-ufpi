"""Presentation-only transformation with a conservative observable expansion guard."""

import re
import unicodedata

from pydantic import BaseModel, ConfigDict

from rag_baseline.conversation_contracts import GroundedFollowUpResult
from rag_baseline.grounding import TemporalGroundingContext
from rag_baseline.output_contracts import AllowedTemporalFacts, NormativeReference


class GroundedTransformInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: str
    kind: str
    answer: str
    references: list[NormativeReference]
    temporal_provenance: TemporalGroundingContext
    allowed_temporal_facts: AllowedTemporalFacts
    instruction: str = (
        "Altere somente a apresentação do conteúdo fornecido. Não acrescente regra, norma, "
        "artigo, subdivisão, data, numeral ou decisão temporal. Não faça busca."
    )


def normalized(text):
    return unicodedata.normalize("NFC", text).casefold().strip()


class GroundedTransformGuard:
    """Lexical/structural coverage, not proof of semantic equivalence."""

    def check(self, source, candidate):
        if not isinstance(candidate, str) or not candidate.strip():
            return ["empty_transform"]
        if candidate == source.answer:
            return []
        allowed = "\n".join(
            [
                source.answer,
                *(r.display_text for r in source.references),
                source.temporal_status_text or "",
            ]
        )
        issues = []
        patterns = {
            "norm": r"(?:\d[\d.]*\s*/\s*\d{4}|ufpi-\d+-\d{4})",
            "resolution": r"\bresolu[çc][ãa]o\s*(?:n(?:\.[º°o]|[º°o.]?)\s*)?(\d[\d.]*)",
            "caput": r"\bcaput\b",
            "calendar_date": r"\b\d{1,2}\s+(?:de\s+)?[a-zçãé]+\s+(?:de\s+)?\d{4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            "number": r"\d+",
        }
        for code, pattern in patterns.items():
            before = set(re.findall(pattern, normalized(allowed)))
            after = set(re.findall(pattern, normalized(candidate)))
            if after - before:
                issues.append(f"new_{code}")

        def locators(text, label, value):
            found = set()
            normalized_text = re.sub(r"[\"'“”‘’()]", " ", normalized(text))
            for match in re.finditer(
                rf"{label}\s*(?:n(?:\.[º°o]|[º°o.]?)\s*)?(({value})(?:\s*(?:,|e|ou|/)\s*(?:{value}))*)",
                normalized_text,
            ):
                found.update(re.findall(value, match[1]))
            return found

        kinds = {
            "article": (r"\bart(?:igos?|s)?\.?", r"\d+[a-z]?"),
            "paragraph": (r"(?:§{1,2}|par[áa]grafos?)", r"\d+|[úu]nico"),
            "inciso": (r"\bincisos?", r"[ivxlcdm]+"),
            "alinea": (r"\bal[ií]neas?", r"[a-z]"),
        }
        for code, (label, value) in kinds.items():
            before, after = locators(allowed, label, value), locators(candidate, label, value)
            if code == "inciso":
                compact = r"\bart(?:igos?|s)?\.?\s*\d+[a-z]?\s*,\s*([ivxlcdm]+)\b"
                before.update(re.findall(compact, normalized(allowed)))
                after.update(re.findall(compact, normalized(candidate)))
            if after - before:
                issues.append(f"new_{code}")

        def chronological_years(text):
            without_identifiers = re.sub(patterns["norm"], "", normalized(text))
            return set(re.findall(r"\b(?:19|20)\d{2}\b", without_identifiers))

        if chronological_years(candidate) - chronological_years(allowed):
            issues.append("new_chronological_year")
        temporal = r"\b(?:vigentes?|vigência|vigor\w*|em vigor|publica\w*|eficácia|efeitos|retroativ\w*|revog\w*|alterad\w*|vale\w*|validade|válid[ao]s?|imediat\w*|desde|a partir de|aplica\w*|hoje|amanhã|ontem)\b"

        # A new temporal paraphrase is refused; whole clauses, never a substring
        # inside a negation, must already occur in authorized source presentation.
        def clauses(text):
            return {
                normalized(p).strip(" .!?,:") for p in re.split(r"[.!?;\n]+", text) if p.strip()
            }

        original_clauses = clauses(allowed)
        if any(
            re.search(temporal, part) and part not in original_clauses
            for part in clauses(candidate)
        ):
            issues.append("new_temporal_claim")
        return issues


class GroundedFollowUpTransformer:
    def __init__(self, provider=None):
        self.provider = provider
        self.guard = GroundedTransformGuard()

    @staticmethod
    def _result(source, kind, content, status):
        return GroundedFollowUpResult.model_validate(
            dict(
                kind=kind,
                content=content,
                guard_status=status,
                source_correlation_id=source.correlation_id,
                source_core_version=source.core_version,
                source_contract_version=source.contract_version,
                references=[r.model_dump() for r in source.references],
                temporal_provenance=source.temporal_provenance.model_dump(),
                domain=source.domain,
            )
        )

    def repeat(self, source):
        return self._result(source, "REPEAT", source.answer, "ACCEPTED")

    async def transform(self, request, kind, source):
        if kind == "REPEAT":
            return self.repeat(source), [], "repeat_source"
        if source.core_status == "fallback":
            return (
                self._result(source, kind, source.answer, "FALLBACK_TO_SOURCE"),
                [],
                "source_core_fallback",
            )
        try:
            if self.provider is None:
                raise RuntimeError("No presentation provider configured.")
            payload = GroundedTransformInput.model_validate(
                dict(
                    request=request,
                    kind=kind,
                    answer=source.answer,
                    references=[r.model_dump() for r in source.references],
                    temporal_provenance=source.temporal_provenance.model_dump(),
                    allowed_temporal_facts=source.allowed_temporal_facts.model_dump(),
                )
            )
            candidate = await self.provider.transform(payload)
            issues = self.guard.check(source, candidate)
            if issues:
                return (
                    self._result(source, kind, source.answer, "FALLBACK_TO_SOURCE"),
                    issues,
                    "transform_rejected",
                )
            return self._result(source, kind, candidate, "ACCEPTED"), [], "transform_accepted"
        except Exception:
            return (
                self._result(source, kind, source.answer, "FALLBACK_TO_SOURCE"),
                [],
                "transform_provider_error",
            )
