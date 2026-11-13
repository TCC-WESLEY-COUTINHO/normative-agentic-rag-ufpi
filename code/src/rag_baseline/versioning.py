"""Explicit documentary registry. Unknown status never implies obsolescence."""

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rag_baseline.models import RetrievedChunk
from rag_baseline.scope import Sector

Status = Literal["vigente", "substituida", "revogada", "desconhecida"]
REGISTRY_PATH = Path(__file__).resolve().parents[3] / "data/normative_registry.json"


class LegalBasis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1)
    article: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_path: str | None = None


class ProvisionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    article: str = Field(pattern=r"^\d+[A-Za-z]?$", min_length=1)
    paragraph: str = Field(pattern=r"^\d+$", min_length=1)


class ProvisionAmendment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: ProvisionTarget
    amended_by: str = Field(min_length=1)
    status: Literal["alterado"] = "alterado"
    effective_text_source: str = Field(min_length=1)
    previous_text: str = Field(min_length=1)
    effective_text: str = Field(min_length=1)
    legal_basis: LegalBasis

    @model_validator(mode="after")
    def supported_replacement(self):
        if self.effective_text_source != self.amended_by:
            raise ValueError("A redação aplicável deve provir do ato alterador.")
        if self.effective_text not in self.legal_basis.text:
            raise ValueError("Redação aplicável ausente da base documental.")
        return self


class NormRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    norm_id: str = Field(min_length=1)
    sector: Sector
    sources: list[str] = Field(min_length=1)
    status: Status = "desconhecida"
    publication_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    legal_basis: LegalBasis | None = None
    corpus_path: str | None = None
    amendments: list[ProvisionAmendment] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def requires_evidence(self):
        if (
            self.status != "desconhecida"
            or self.supersedes
            or self.superseded_by
            or self.effective_from
            or self.effective_to
        ) and self.legal_basis is None:
            raise ValueError("Status/relação temporal exige evidência documental.")
        if any(not s.strip() for s in self.sources):
            raise ValueError("Fonte vazia no registry.")
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError("Intervalo de vigência inválido.")
        return self


class NormativeRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    norms: list[NormRecord]

    @model_validator(mode="after")
    def valid_relations(self):
        ids = {n.norm_id for n in self.norms}
        if len(ids) != len(self.norms):
            raise ValueError("norm_id duplicado no registry.")
        sources = [s for n in self.norms for s in n.sources]
        if len(set(sources)) != len(sources):
            raise ValueError("Fonte associada a mais de uma norma.")
        for norm in self.norms:
            targets = norm.supersedes + ([norm.superseded_by] if norm.superseded_by else [])
            if any(t not in ids or t == norm.norm_id for t in targets):
                raise ValueError("Relação temporal exige norm_id válido e distinto.")
            seen = set()
            for amendment in norm.amendments:
                target = amendment.target.article, amendment.target.paragraph
                other = next((n for n in self.norms if n.norm_id == amendment.amended_by), None)
                if (
                    other is None
                    or other.norm_id == norm.norm_id
                    or other.sector != norm.sector
                    or target in seen
                ):
                    raise ValueError("Alteração exige ato distinto do mesmo setor e alvo único.")
                seen.add(target)
        return self

    @classmethod
    def load(cls, path: Path = REGISTRY_PATH):
        try:
            registry = cls.model_validate_json(path.read_text(encoding="utf-8"))
            for norm in registry.norms:
                bases = ([norm.legal_basis] if norm.legal_basis else []) + [
                    a.legal_basis for a in norm.amendments
                ]
                for basis in bases:
                    if basis.source_path:
                        source = path.parent.parent / basis.source_path
                        raw = json.loads(source.read_text(encoding="utf-8"))
                        if not any(
                            r.get("conteudo") == basis.text
                            and r.get("metadados", {}).get("fonte") == basis.source
                            and r.get("metadados", {}).get("artigo_numero")
                            == basis.article.split(",")[0].strip()
                            for r in raw
                        ):
                            raise ValueError("Texto da evidência não coincide com o corpus.")
                if norm.amendments:
                    if not norm.corpus_path:
                        raise ValueError("Alteração carregada exige corpus da norma-base.")
                    raw = json.loads(
                        (path.parent.parent / norm.corpus_path).read_text(encoding="utf-8")
                    )
                    for amendment in norm.amendments:
                        if not any(
                            r.get("metadados", {}).get("artigo_numero") == amendment.target.article
                            and r.get("metadados", {}).get("fonte") in norm.sources
                            and r.get("conteudo", "").count(amendment.previous_text) == 1
                            for r in raw
                        ):
                            raise ValueError("Redação anterior não comprovada no dispositivo-base.")
            return registry
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("Registry inválido ou evidência documental indisponível.") from exc

    def record_for(self, chunk: RetrievedChunk) -> NormRecord | None:
        norm_id = chunk.id.split("-art-")[0]
        return next((n for n in self.norms if n.norm_id == norm_id), None) or next(
            (n for n in self.norms if chunk.source in n.sources), None
        )


class Removal(BaseModel):
    reference: RetrievedChunk
    norm_id: str
    reason: Status | Literal["amendment_unresolved", "historical_incompatible"]
    superseded_by: str | None
    legal_basis: LegalBasis


class AmendmentApplication(BaseModel):
    norm_id: str
    original_reference: RetrievedChunk
    final_reference: RetrievedChunk
    amendment: ProvisionAmendment
    precedence_rule: str = "Ato alterador prevalece somente no dispositivo indicado."


class TemporalIntent(BaseModel):
    mode: Literal["current", "historical", "comparison", "validity", "indeterminate"]
    norm_ids: list[str] = Field(default_factory=list)
    before_amendment: bool = False
    relation_query: Literal["amendment"] | None = None
    article: str | None = None
    paragraph: str | None = None
    requested_year: int | None = None
    historical_wording: bool = False
    document_year: int | None = None

    @property
    def needs_history(self):
        return self.mode in ("historical", "comparison")


class TemporalProvenance(BaseModel):
    chunk_id: str
    source_norm: str
    source_article: str
    temporal_action: str
    relation_source: LegalBasis | None = None


class VersionAudit(BaseModel):
    enabled: bool = True
    historical: bool = False
    pre_filter_references: list[RetrievedChunk]
    removed_references: list[Removal]
    final_references: list[RetrievedChunk]
    unknown_norm_ids: list[str]
    norm_statuses: dict[str, Status]
    amended_references: list[AmendmentApplication] = Field(default_factory=list)
    prefilter_excluded_norm_ids: list[str] = Field(default_factory=list)
    prefilter_exclusions: list[NormRecord] = Field(default_factory=list)
    requested_top_k: int = 5
    shortfall: int = 0
    temporal_intent: TemporalIntent | None = None
    provenance: list[TemporalProvenance] = Field(default_factory=list)
    insufficient_reason: str | None = None


class VersionFilter:
    def __init__(self, registry: NormativeRegistry):
        self.registry = registry

    def obsolete_records(self):
        return [n for n in self.registry.norms if n.status in ("substituida", "revogada")]

    def historical_exclusions(self, intent):
        """Only explicit documentary successors are incompatible with a prior wording."""
        excluded = {}
        if intent is None or intent.mode != "historical":
            return excluded
        for norm in self.registry.norms:
            if norm.norm_id in intent.norm_ids and norm.superseded_by:
                excluded[norm.superseded_by] = norm.legal_basis
            if (
                norm.norm_id in intent.norm_ids
                or intent.before_amendment
                or (intent.article and intent.paragraph)
            ):
                for amendment in norm.amendments:
                    if intent.article and intent.article != amendment.target.article:
                        continue
                    if intent.paragraph and intent.paragraph != amendment.target.paragraph:
                        continue
                    excluded[amendment.amended_by] = amendment.legal_basis
        return excluded

    def excluded_sources(self, intent=None):
        ids = (
            set(self.historical_exclusions(intent))
            if intent and intent.needs_history
            else {n.norm_id for n in self.obsolete_records()}
        )
        return [s for n in self.registry.norms if n.norm_id in ids for s in n.sources]

    def relation_evidence(self, intent, *, sector=None):
        """Expose registry evidence for relation questions, never resolve arbitrary articles."""
        if intent is None:
            return []
        evidence = []
        for norm in self.registry.norms:
            if sector is not None and norm.sector != sector:
                continue
            if intent.mode == "validity" and norm.norm_id in intent.norm_ids and norm.legal_basis:
                evidence.append((norm.superseded_by, norm.legal_basis))
            if intent.relation_query == "amendment":
                for amendment in norm.amendments:
                    if (
                        intent.article == amendment.target.article
                        and intent.paragraph == amendment.target.paragraph
                        and (not intent.norm_ids or norm.norm_id in intent.norm_ids)
                    ):
                        evidence.append((amendment.amended_by, amendment.legal_basis))
        chunks = []
        for norm_id, basis in evidence:
            record = next((n for n in self.registry.norms if n.norm_id == norm_id), None)
            if record is None or basis.source not in record.sources:
                continue
            article = basis.article.split(",")[0].strip()
            chunks.append(
                (
                    RetrievedChunk(
                        id=f"{norm_id}-art-{article}-registry-relation",
                        norm_id=norm_id,
                        source=basis.source,
                        sector=record.sector,
                        content=basis.text,
                        article_number=article,
                        article_label=f"Art. {article}",
                        original_index=0,
                        rank=len(chunks) + 1,
                        distance=0.0,
                    ),
                    basis,
                )
            )
        return chunks

    def apply(
        self,
        chunks: list[RetrievedChunk],
        *,
        historical=False,
        top_k=5,
        temporal_intent: TemporalIntent | None = None,
        relation_sector=None,
    ):
        if temporal_intent:
            historical = temporal_intent.needs_history
        kept, removed, unknown, statuses = [], [], [], {}
        amended, provenance = [], []
        historical_exclusions = self.historical_exclusions(temporal_intent)
        for chunk in chunks:
            norm = self.registry.record_for(chunk)
            norm_id = norm.norm_id if norm else chunk.id.split("-art-")[0]
            status = norm.status if norm else "desconhecida"
            statuses[norm_id] = status
            if status == "desconhecida":
                unknown.append(norm_id)
            action, basis = "historical_preserved" if historical else "kept_current", None
            if norm_id in historical_exclusions:
                basis = historical_exclusions[norm_id]
                removed.append(
                    Removal(
                        reference=chunk,
                        norm_id=norm_id,
                        reason="historical_incompatible",
                        superseded_by=None,
                        legal_basis=basis,
                    )
                )
                action = "excluded_later_wording"
            elif not historical and status in ("substituida", "revogada"):
                removed.append(
                    Removal(
                        reference=chunk,
                        norm_id=norm_id,
                        reason=status,
                        superseded_by=norm.superseded_by,
                        legal_basis=norm.legal_basis,
                    )
                )
                action, basis = "excluded_revoked", norm.legal_basis
            else:
                original = chunk
                unresolved = False
                for amendment in norm.amendments if norm and not historical else []:
                    if chunk.article_number != amendment.target.article:
                        continue
                    already_applied = (
                        chunk.content.count(amendment.effective_text) == 1
                        and amendment.previous_text not in chunk.content
                    )
                    if chunk.content.count(amendment.previous_text) != 1 and not already_applied:
                        removed.append(
                            Removal(
                                reference=original,
                                norm_id=norm_id,
                                reason="amendment_unresolved",
                                superseded_by=amendment.amended_by,
                                legal_basis=amendment.legal_basis,
                            )
                        )
                        unresolved = True
                        action, basis = "amendment_unresolved", amendment.legal_basis
                        break
                    notice = (
                        f"[REDAÇÃO APLICÁVEL: art. {amendment.target.article}, "
                        f"§ {amendment.target.paragraph}, da norma-base {norm_id}; "
                        f"alteração por {amendment.amended_by}, "
                        f"art. {amendment.legal_basis.article}. "
                        "Demais dispositivos preservados.]\n"
                    )
                    chunk = (
                        chunk
                        if already_applied
                        else chunk.model_copy(
                            update={
                                "content": notice
                                + chunk.content.replace(
                                    amendment.previous_text, amendment.effective_text, 1
                                ),
                            }
                        )
                    )
                    action, basis = "amendment_applied", amendment.legal_basis
                    amended.append(
                        AmendmentApplication(
                            norm_id=norm_id,
                            original_reference=original,
                            final_reference=chunk,
                            amendment=amendment,
                        )
                    )
                if unresolved:
                    provenance.append(
                        TemporalProvenance(
                            chunk_id=original.id,
                            source_norm=norm_id,
                            source_article=original.article_number,
                            temporal_action=action,
                            relation_source=basis,
                        )
                    )
                    continue
                kept.append(chunk.model_copy(update={"rank": len(kept) + 1}))
                if historical and norm and norm.legal_basis:
                    basis = norm.legal_basis
            provenance.append(
                TemporalProvenance(
                    chunk_id=chunk.id,
                    source_norm=norm_id,
                    source_article=chunk.article_number,
                    temporal_action=action,
                    relation_source=basis,
                )
            )
        for relation, basis in reversed(
            self.relation_evidence(temporal_intent, sector=relation_sector)
        ):
            # A registry excerpt replaces the same article if it was already retrieved.
            kept = [
                c
                for c in kept
                if not (c.source == relation.source and c.article_number == relation.article_number)
            ]
            kept.insert(0, relation)
            record = self.registry.record_for(relation)
            statuses[record.norm_id] = record.status
            if record.status == "desconhecida":
                unknown.append(record.norm_id)
            provenance.append(
                TemporalProvenance(
                    chunk_id=relation.id,
                    source_norm=record.norm_id,
                    source_article=relation.article_number,
                    temporal_action="relation_evidence",
                    relation_source=basis,
                )
            )
        kept = kept[:top_k]
        kept = [c.model_copy(update={"rank": rank}) for rank, c in enumerate(kept, 1)]
        return kept, VersionAudit(
            historical=historical,
            pre_filter_references=chunks,
            removed_references=removed,
            final_references=kept,
            unknown_norm_ids=sorted(set(unknown)),
            norm_statuses=statuses,
            amended_references=[a for a in amended if a.final_reference.id in {c.id for c in kept}],
            requested_top_k=top_k,
            shortfall=max(0, top_k - len(kept)),
            temporal_intent=temporal_intent,
            provenance=provenance,
        )
