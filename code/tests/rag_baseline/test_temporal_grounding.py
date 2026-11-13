"""Temporal decisions must reach generation without another inference step."""

import json

import pytest

from rag_baseline.agentic import AgenticRagService
from rag_baseline.corpus import load_corpus
from rag_baseline.models import RetrievedChunk
from rag_baseline.prompts import V2_SYSTEM_PROMPT
from rag_baseline.router import NormativeRouter
from rag_baseline.service import RagService
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, VersionFilter

ROOT = REGISTRY_PATH.parent.parent


def chunk(norm, article, rank=1):
    names = {
        "177-2012": "graduacao_setor_v2.json",
        "956-2025": "pos_graduacao_setor_v2.json",
        "658-2024": "658_2024_temporal_v1.json",
        "1056-2026": "1056_2026_temporal_v1.json",
    }
    original = next(
        c
        for c in load_corpus(ROOT / "evaluation/corpora" / names[norm], id_prefix=f"ufpi-{norm}")
        if c.article_number == article
    )
    return RetrievedChunk(**original.model_dump(), rank=rank, distance=0.1)


class Client:
    llm_model = "test"

    def __init__(self):
        self.prompts = []

    async def structured_chat(self, **kwargs):
        pytest.fail("Grounding or manual scope must not call another LLM.")

    async def embed(self, texts):
        return [[0.0]]

    async def chat(self, **payload):
        self.prompts.append(payload)
        return "Raw answer from provider."


class Store:
    def __init__(self, chunks):
        self.chunks = chunks

    def count(self):
        return len(self.chunks) or 1

    def query(self, *args, **kwargs):
        return self.chunks


async def invoke(chunks, question, scope="graduacao"):
    client = Client()
    service = RagService(
        openrouter=client,
        vector_store=Store(chunks),
        top_k=5,
        embedding_model="test",
        llm_model="test",
        system_prompt=V2_SYSTEM_PROMPT,
    )
    result = await AgenticRagService(
        service, NormativeRouter(client), VersionFilter(NormativeRegistry.load())
    ).query(question, scope=scope)
    return result, client


def payload(client):
    prompt = client.prompts[0]["user_prompt"]
    assert "[TEMPORAL GROUNDING]" in prompt
    raw = prompt.split("[TEMPORAL GROUNDING]", 1)[1].split("[/TEMPORAL GROUNDING]", 1)[0]
    return json.loads(raw)


@pytest.mark.asyncio
async def test_historical_prompt_carries_preservation_decision_and_constraints():
    original = chunk("177-2012", "68")
    result, client = await invoke(
        [original], "Como era o §4º do art. 68 antes da alteração de 2026?"
    )
    grounding = payload(client)
    assert grounding["temporal_intent"] == "historical"
    assert grounding["generation_constraints"]["must_frame_as_historical"]
    assert grounding["generation_constraints"]["must_not_claim_current_validity"]
    assert grounding["generation_constraints"]["must_not_deny_present_evidence"]
    assert grounding["evidence_states"][0]["temporal_action"] == "historical_preserved"
    assert grounding["evidence_states"][0]["chunk_id"] == original.id
    assert result.references[0].content == original.content
    assert len(client.prompts) == 1


@pytest.mark.asyncio
async def test_current_grounding_excludes_removed_content_and_discloses_unknown():
    _, client = await invoke(
        [chunk("658-2024", "43"), chunk("956-2025", "53", 2)],
        "Qual é a regra atual no mestrado?",
        "pos_graduacao",
    )
    grounding = payload(client)
    assert grounding["temporal_intent"] == "current"
    assert {e["source_norm"] for e in grounding["evidence_states"]} == {"ufpi-956-2025"}
    assert grounding["evidence_states"][0]["temporal_action"] == "kept_current"
    assert grounding["generation_constraints"]["must_not_claim_unknown_as_current"]
    assert grounding["known_relations"] == []


@pytest.mark.asyncio
async def test_comparison_identifies_predecessor_and_successor_without_certifying_status():
    _, client = await invoke(
        [chunk("658-2024", "43"), chunk("956-2025", "53", 2)],
        "Qual era a regra na 658/2024 e qual é a regra atual na 956/2025?",
        "pos_graduacao",
    )
    grounding = payload(client)
    roles = {e["source_norm"]: e["temporal_role"] for e in grounding["evidence_states"]}
    assert roles == {"ufpi-658-2024": "historical", "ufpi-956-2025": "posterior"}
    assert grounding["generation_constraints"]["must_separate_temporal_states"]
    assert grounding["generation_constraints"]["must_follow_evidence_roles"]
    assert grounding["known_relations"][0]["relation"] == "REVOKED_BY"


@pytest.mark.asyncio
async def test_validity_contract_contains_only_documented_relation_and_article_ceiling():
    _, client = await invoke(
        [chunk("658-2024", "43")], "A Resolução 658/2024 ainda está vigente?", "pos_graduacao"
    )
    grounding = payload(client)
    relation = grounding["known_relations"][0]
    assert relation["source_norm"] == "ufpi-658-2024"
    assert relation["target_norm"] == "ufpi-956-2025"
    assert relation["evidence_article"] == "62, VI"
    assert grounding["generation_constraints"]["citation_granularity_ceiling"] == "article"
    assert all("content" not in e for e in grounding["evidence_states"])


@pytest.mark.asyncio
async def test_partial_amendment_is_explicit_without_revoking_whole_base():
    _, client = await invoke([chunk("177-2012", "68")], "Como é atualmente o §4º do art. 68?")
    grounding = payload(client)
    assert grounding["evidence_states"][0]["temporal_action"] == "amendment_applied"
    relation = grounding["known_relations"][0]
    assert relation["relation"] == "AMENDED_BY"
    assert relation["target_article"] == "68" and relation["target_paragraph"] == "4"
    assert grounding["generation_constraints"][
        "must_not_treat_partial_amendment_as_total_revocation"
    ]


@pytest.mark.asyncio
async def test_unresolved_amendment_does_not_reach_generator():
    broken = chunk("177-2012", "68").model_copy(update={"content": "Art. 68. Incomplete."})
    result, client = await invoke([broken], "Como é atualmente o §4º do art. 68?")
    assert result.generation_attempts == 0 and client.prompts == []


@pytest.mark.asyncio
async def test_unrelated_article_does_not_gain_an_amendment_relation():
    _, client = await invoke([chunk("177-2012", "69")], "Qual é atualmente a regra do art. 69?")
    assert payload(client)["known_relations"] == []


@pytest.mark.asyncio
async def test_indeterminate_intent_remains_explicit_and_raw_body_is_preserved():
    result, client = await invoke(
        [chunk("956-2025", "53")], "Quais os requisitos de defesa?", "pos_graduacao"
    )
    assert payload(client)["temporal_intent"] == "indeterminate"
    assert result.output_audit.raw_answer == "Raw answer from provider."
    assert "Raw answer from provider." in result.answer
    assert result.answer.startswith("Com base nas normas indexadas no sistema:")
    assert any(
        f.kind == "STATUS_UNKNOWN" for f in result.normative_output.allowed_temporal_facts.items
    )


def test_builder_is_idempotent_and_rejects_nonfinal_evidence():
    from rag_baseline.agentic import classify_temporal_intent
    from rag_baseline.grounding import build_temporal_grounding

    registry = NormativeRegistry.load()
    original = chunk("177-2012", "68")
    intent = classify_temporal_intent("Como é atualmente o §4º do art. 68?", registry=registry)
    final, audit = VersionFilter(registry).apply([original], temporal_intent=intent)
    first = build_temporal_grounding(final, audit, registry)
    second = build_temporal_grounding(final, audit, registry)
    assert first == second
    assert first.evidence_states[0].chunk_id == original.id
    with pytest.raises(ValueError):
        build_temporal_grounding([original], audit, registry)


def test_generation_metrics_use_only_applicable_denominators():
    from rag_baseline.generation_evaluation import summarize_annotations

    rows = [
        dict(
            temporal_mode="historical",
            has_unknown=True,
            has_known_relation=True,
            has_normative_references=True,
            temporal_contradiction=True,
            historical_framing=False,
            current_state_consistent=None,
            unknown_overclaim=True,
            relation_consistent=False,
            granularity_violation=True,
        ),
        dict(
            temporal_mode="current",
            has_unknown=True,
            has_known_relation=True,
            has_normative_references=True,
            temporal_contradiction=False,
            historical_framing=None,
            current_state_consistent=True,
            unknown_overclaim=False,
            relation_consistent=True,
            granularity_violation=False,
        ),
    ]
    metrics = summarize_annotations(rows)
    assert metrics["TCR"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert metrics["HFA"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert metrics["CSC"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert metrics["UOR"]["denominator"] == 2
    assert metrics["TRC"]["numerator"] == 1
    assert metrics["CGVR"]["denominator"] == 2
    assert summarize_annotations([])["HFA"]["value"] is None


def test_generation_dataset_hash_requires_canonical_crlf():
    import hashlib
    import json
    from unittest.mock import Mock

    from rag_baseline.generation_evaluation import DATASET, ROOT, dataset_sha256_crlf

    original = DATASET.read_bytes()
    lf = original.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    manifest = json.loads(
        (
            ROOT / "evaluation/results/temporal_generation_grounding_v1_001/manifest.json"
        ).read_bytes()
    )
    expected = manifest["dataset_sha256"]
    assert hashlib.sha256(crlf).hexdigest() == expected
    assert hashlib.sha256(lf).hexdigest() != expected
    for raw in (lf, crlf):
        path = Mock()
        path.read_bytes.return_value = raw
        assert dataset_sha256_crlf(path) == expected
        path.read_bytes.return_value = raw.replace(
            b'"schema_version": "1.0"', b'"schema_version": "9.0"'
        )
        assert dataset_sha256_crlf(path) != expected
