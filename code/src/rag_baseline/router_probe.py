"""Metadata-only evidence and deterministic routing policy; no answer generation."""

import hashlib
import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rag_baseline.router import CLARIFICATION, Scope

DOMAINS = ("graduacao", "pos_graduacao")


class ProbeHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    rank: int = Field(ge=1, strict=True)
    chunk_id: str
    norm_id: str | None
    sector: str | None
    distance: float


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    hits: tuple[ProbeHit, ...]
    domain_counts: dict[str, int]
    best_rank_by_domain: dict[str, int | None]
    best_distance_by_domain: dict[str, float | None]
    rank_mass_by_domain: dict[str, float]
    rank_mass_share_by_domain: dict[str, float]
    top1_domain: str | None
    domains_present: tuple[str, ...]
    dominant_domain: str | None
    dominance: float | None
    unknown_sector_count: int
    best_distance_gap: float | None
    distance_statistics_by_domain: dict[str, dict[str, float] | None]
    distance_metric: Literal["cosine_distance"] = "cosine_distance"
    distance_interpretation: str = "Lower is better; not calibrated confidence."

    @classmethod
    def from_hits(cls, supplied):
        hits = tuple(supplied)
        if [h.rank for h in hits] != list(range(1, len(hits) + 1)):
            raise ValueError("O probe deve preservar os ranks consecutivos retornados.")
        groups = {d: [h for h in hits if h.sector == d] for d in DOMAINS}
        masses = {d: sum(1 / h.rank for h in group) for d, group in groups.items()}
        total = sum(masses.values())
        shares = {d: masses[d] / total if total else 0.0 for d in DOMAINS}
        present = tuple(d for d in DOMAINS if groups[d])
        largest = max(masses.values())
        winners = [d for d in present if masses[d] == largest]
        best_distances = {
            d: min((h.distance for h in group), default=None) for d, group in groups.items()
        }
        return cls(
            hits=hits,
            domain_counts={d: len(group) for d, group in groups.items()},
            best_rank_by_domain={
                d: min((h.rank for h in group), default=None) for d, group in groups.items()
            },
            best_distance_by_domain=best_distances,
            rank_mass_by_domain=masses,
            rank_mass_share_by_domain=shares,
            top1_domain=hits[0].sector if hits and hits[0].sector in DOMAINS else None,
            domains_present=present,
            dominant_domain=winners[0] if len(winners) == 1 else None,
            dominance=max(shares.values()) if total else None,
            unknown_sector_count=sum(h.sector not in DOMAINS for h in hits),
            best_distance_gap=(
                abs(best_distances[DOMAINS[0]] - best_distances[DOMAINS[1]])
                if len(present) == 2
                else None
            ),
            distance_statistics_by_domain={
                d: dict(
                    min=min(h.distance for h in group),
                    max=max(h.distance for h in group),
                    mean=sum(h.distance for h in group) / len(group),
                )
                if group
                else None
                for d, group in groups.items()
            },
        )

    def sha256(self):
        raw = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ProbeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scope: Scope | None
    needs_clarification: bool
    reason_code: Literal[
        "probe_supports_graduacao",
        "probe_supports_pos",
        "cross_domain_request",
        "conflicting_probe_evidence",
        "insufficient_probe_evidence",
    ]
    clarification_question: str | None

    @model_validator(mode="after")
    def consistent(self):
        reasons = {
            "graduacao": {"probe_supports_graduacao"},
            "pos_graduacao": {"probe_supports_pos"},
            "ambas": {"cross_domain_request"},
            None: {"conflicting_probe_evidence", "insufficient_probe_evidence"},
        }
        if (
            self.needs_clarification != (self.scope is None)
            or self.reason_code not in reasons[self.scope]
        ):
            raise ValueError("Decisão de probe inconsistente.")
        if self.needs_clarification:
            if not self.clarification_question or not self.clarification_question.strip():
                raise ValueError("Esclarecimento exige pergunta.")
        elif self.clarification_question is not None:
            raise ValueError("Rota resolvida não exige pergunta.")
        return self


def clarify_probe(reason="insufficient_probe_evidence"):
    return ProbeDecision(
        scope=None,
        needs_clarification=True,
        reason_code=reason,
        clarification_question=CLARIFICATION,
    )


def distribution_decision(probe: ProbeResult, *, threshold: float) -> ProbeDecision:
    if not math.isfinite(threshold) or not 0.5 < threshold <= 1:
        raise ValueError("O threshold deve estar no intervalo (0.5, 1].")
    if not probe.domains_present:
        return clarify_probe()
    if len(probe.domains_present) == 1 or (
        probe.dominance >= threshold and probe.dominant_domain is not None
    ):
        scope = (
            probe.domains_present[0] if len(probe.domains_present) == 1 else probe.dominant_domain
        )
        return ProbeDecision(
            scope=scope,
            needs_clarification=False,
            reason_code="probe_supports_graduacao"
            if scope == "graduacao"
            else "probe_supports_pos",
            clarification_question=None,
        )
    return clarify_probe("conflicting_probe_evidence")
