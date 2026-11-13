"""Generation contract projected from final evidence and deterministic temporal decisions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from rag_baseline.models import RetrievedChunk
from rag_baseline.versioning import NormativeRegistry, Status, VersionAudit


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceState(ContractModel):
    chunk_id: str
    source_norm: str
    source_article: str
    temporal_action: str
    normative_status: Status
    temporal_role: Literal["historical", "posterior", "eligible"]
    relation_source: dict[str, str] | None = None


class KnownRelation(ContractModel):
    relation: Literal["REVOKED_BY", "AMENDED_BY"]
    source_norm: str
    target_norm: str
    target_article: str | None = None
    target_paragraph: str | None = None
    evidence_source: str
    evidence_article: str


class GenerationConstraints(ContractModel):
    must_frame_as_historical: bool
    must_not_claim_current_validity: bool
    must_not_claim_unknown_as_current: bool
    must_not_present_revoked_rule_as_current: bool
    must_not_present_successor_as_historical_predecessor: bool
    must_separate_temporal_states: bool
    must_follow_evidence_roles: bool = True
    must_not_treat_partial_amendment_as_total_revocation: bool
    must_not_duplicate_superseded_wording: bool
    must_not_reintroduce_excluded_evidence: bool = True
    must_not_deny_present_evidence: bool = True
    must_not_invent_effective_date: bool = True
    must_not_invent_temporal_scope: bool = True
    citation_granularity_ceiling: Literal["source", "article"]


class TemporalGroundingContext(ContractModel):
    temporal_intent: Literal["current", "historical", "comparison", "validity", "indeterminate"]
    requested_time_context: dict
    evidence_states: list[EvidenceState]
    known_relations: list[KnownRelation]
    generation_constraints: GenerationConstraints

    def prompt_section(self):
        return (
            "As decisões temporais abaixo já foram tomadas pelo pipeline. Verbalize esses "
            "estados; não reavalie vigência nem contradiga as relações documentadas. "
            "temporal_role define o papel na resposta; temporal_action registra a ação do filtro. "
            "Texto com temporal_role=historical está disponível para responder sobre a "
            "redação histórica: não exija o ato posterior para reconhecer esse texto. "
            "Em comparação, apresente historical e posterior separadamente, mesmo quando "
            "ambos foram preservados pelo filtro com historical_preserved. Unknown/desconhecida "
            "não certifica vigência. Indeterminate não autoriza certeza temporal. "
            "A alteração parcial conserva a norma-base e os demais dispositivos. "
            "Não invente datas ou alcance temporal. Nas citações de localização, respeite "
            "citation_granularity_ceiling; mencionar o dispositivo perguntado não autoriza "
            "acrescentá-lo como localização bibliográfica sem metadado correspondente.\n"
            "[TEMPORAL GROUNDING]\n" + self.model_dump_json(indent=2) + "\n[/TEMPORAL GROUNDING]\n"
        )


def build_temporal_grounding(
    chunks: list[RetrievedChunk], audit: VersionAudit, registry: NormativeRegistry
) -> TemporalGroundingContext:
    if (
        not audit.enabled
        or audit.insufficient_reason
        or not chunks
        or chunks != audit.final_references
        or audit.temporal_intent is None
    ):
        raise ValueError(
            "Grounding exige decisões temporais e exatamente a evidência final elegível."
        )
    intent = audit.temporal_intent
    provisions = {
        (p.source_norm, p.source_article)
        for p in audit.provenance
        if p.chunk_id in {c.id for c in chunks}
    }
    norms = {norm for norm, _ in provisions}
    relations = []
    for norm in registry.norms:
        if (
            norm.superseded_by
            and norm.legal_basis
            and (
                norm.norm_id in norms
                or (
                    intent.mode == "validity"
                    and norm.norm_id in intent.norm_ids
                    and norm.superseded_by in norms
                )
            )
        ):
            relations.append(
                KnownRelation(
                    relation="REVOKED_BY",
                    source_norm=norm.norm_id,
                    target_norm=norm.superseded_by,
                    evidence_source=norm.legal_basis.source,
                    evidence_article=norm.legal_basis.article,
                )
            )
        for amendment in norm.amendments:
            if (norm.norm_id, amendment.target.article) in provisions or (
                amendment.amended_by,
                amendment.legal_basis.article,
            ) in provisions:
                relations.append(
                    KnownRelation(
                        relation="AMENDED_BY",
                        source_norm=norm.norm_id,
                        target_norm=amendment.amended_by,
                        target_article=amendment.target.article,
                        target_paragraph=amendment.target.paragraph,
                        evidence_source=amendment.legal_basis.source,
                        evidence_article=amendment.legal_basis.article,
                    )
                )
    states = []
    for chunk in chunks:
        provenance = next((p for p in reversed(audit.provenance) if p.chunk_id == chunk.id), None)
        if provenance is None:
            raise ValueError("Evidência final sem proveniência temporal.")
        role = "historical" if intent.mode == "historical" else "eligible"
        if intent.mode == "comparison":
            if any(r.source_norm == provenance.source_norm for r in relations):
                role = "historical"
            elif any(r.target_norm == provenance.source_norm for r in relations):
                role = "posterior"
        states.append(
            EvidenceState(
                chunk_id=chunk.id,
                source_norm=provenance.source_norm,
                source_article=provenance.source_article,
                temporal_action=provenance.temporal_action,
                normative_status=audit.norm_statuses.get(provenance.source_norm, "desconhecida"),
                temporal_role=role,
                relation_source=(
                    {
                        "source": provenance.relation_source.source,
                        "article": provenance.relation_source.article,
                    }
                    if provenance.relation_source
                    else None
                ),
            )
        )
    return TemporalGroundingContext(
        temporal_intent=intent.mode,
        requested_time_context=intent.model_dump(exclude={"mode"}),
        evidence_states=states,
        known_relations=relations,
        generation_constraints=GenerationConstraints(
            must_frame_as_historical=intent.mode == "historical",
            must_not_claim_current_validity=intent.mode == "historical",
            must_not_claim_unknown_as_current=any(
                s.normative_status == "desconhecida" for s in states
            ),
            must_not_present_revoked_rule_as_current=any(
                s.normative_status in ("revogada", "substituida") for s in states
            )
            or any(r.relation == "REVOKED_BY" for r in relations),
            must_not_present_successor_as_historical_predecessor=intent.needs_history
            and bool(relations),
            must_separate_temporal_states=intent.mode == "comparison",
            must_not_treat_partial_amendment_as_total_revocation=any(
                r.relation == "AMENDED_BY" for r in relations
            ),
            must_not_duplicate_superseded_wording=any(
                s.temporal_action == "amendment_applied" for s in states
            ),
            citation_granularity_ceiling="article"
            if all(c.article_number for c in chunks)
            else "source",
        ),
    )
