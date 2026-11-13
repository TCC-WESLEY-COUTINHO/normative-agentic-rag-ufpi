import json

import pytest

from rag_baseline.models import RetrievedChunk
from rag_baseline.router import RouterDecision
from rag_baseline.service import RagService


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Quais regras de trancamento valem na graduação e na pós-graduação?", True),
        ("Quais regras valem para ambos os níveis?", True),
        ("Compare o trancamento na graduação e na pós.", True),
        ("Quero regras tanto da graduação quanto da pós-graduação.", True),
        ("Não sei se meu curso é graduação ou pós-graduação.", False),
        ("Concluí a graduação e agora faço mestrado. Posso trancar?", False),
        ("Posso cancelar uma disciplina?", False),
    ],
)
def test_both_guard_accepts_joint_requests_without_turning_uncertainty_into_comparison(
    question, expected
):
    from rag_baseline.adaptive_router import explicit_multidomain_request

    assert explicit_multidomain_request(question) is expected


def intent_decision(scope=None):
    reason = {
        None: "ambiguous_academic_level",
        "graduacao": "explicit_graduacao",
        "pos_graduacao": "explicit_pos",
        "ambas": "cross_norm_comparison",
    }[scope]
    return RouterDecision(
        scope=scope,
        needs_clarification=scope is None,
        reason_code=reason,
        clarification_question="Qual nível?" if scope is None else None,
    )


def chunk(i, sector="pos_graduacao", content="PROBE_TEXT_NOT_FOR_GENERATOR"):
    norm = "ufpi-956-2025" if sector == "pos_graduacao" else "ufpi-177-2012"
    return RetrievedChunk(
        id=f"{norm}-art-{i}-idx-{i:06}",
        norm_id=norm,
        sector=sector,
        source="Resolução CEPEX/UFPI nº 956/2025"
        if sector == "pos_graduacao"
        else "Resolução nº 177/2012 CEPEX/UFPI",
        article_number=str(i),
        article_label=f"Art. {i}",
        original_index=i,
        rank=i,
        distance=i / 100,
        content=content,
    )


class Intent:
    model = "same/router-model"

    def __init__(self, scope=None):
        self.decision = intent_decision(scope)
        self.calls = []

    async def route(self, question, *, clarification=None):
        self.calls.append((question, clarification))
        return self.decision


class Remote:
    llm_model = "same/router-model"

    def __init__(self, output=None):
        self.output = output or dict(
            scope="pos_graduacao",
            needs_clarification=False,
            reason_code="probe_supports_pos",
            clarification_question=None,
        )
        self.embeds, self.judgments, self.generations = [], [], []

    async def embed(self, texts):
        self.embeds.append(texts)
        return [[0.1, 0.2]]

    async def structured_chat(self, **payload):
        self.judgments.append(payload)
        return self.output if isinstance(self.output, str) else json.dumps(self.output)

    async def chat(self, **payload):
        self.generations.append(payload)
        return "Resposta final."


class Store:
    def __init__(self):
        self.calls = []

    def count(self):
        return 507

    def query(self, embedding, top_k, **kwargs):
        self.calls.append((embedding, top_k, kwargs))
        return (
            [chunk(i) for i in range(1, 5)] if top_k == 10 else [chunk(1, content="FINAL_EVIDENCE")]
        )


def service(remote=None):
    return RagService(
        openrouter=remote or Remote(),
        vector_store=Store(),
        top_k=5,
        embedding_model="same/embedding",
        llm_model="same/router-model",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["intent_v1", "adaptive_distribution_v2", "adaptive_llm_v2"])
@pytest.mark.parametrize("scope", ["graduacao", "ambas"])
async def test_valid_v1_route_never_activates_probe_or_judge(mode, scope):
    from rag_baseline.adaptive_router import AdaptiveRouter

    rag, intent = service(), Intent(scope)
    outcome = await AdaptiveRouter(rag, intent, mode=mode, threshold=0.7).route("Consulta")
    assert outcome.decision is intent.decision
    assert not outcome.audit["probe_activated"]
    assert not rag.openrouter.embeds and not rag.vector_store.calls and not rag.openrouter.judgments


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["adaptive_distribution_v2", "adaptive_llm_v2"])
async def test_uncertain_v1_activates_global_probe_without_generation(mode):
    from rag_baseline.adaptive_router import AdaptiveRouter

    rag, intent = service(), Intent()
    result = await AdaptiveRouter(rag, intent, mode=mode, threshold=0.7).route("Consulta original")
    assert result.decision.scope == "pos_graduacao"
    assert rag.openrouter.embeds == [["Consulta original"]]
    assert rag.vector_store.calls == [([0.1, 0.2], 10, {})]
    assert result.query_embedding == [0.1, 0.2]
    assert result.audit["probe_activated"]
    assert not rag.openrouter.generations
    assert len(rag.openrouter.judgments) == (mode == "adaptive_llm_v2")


@pytest.mark.asyncio
async def test_distribution_and_judge_receive_the_same_metadata_only_probe():
    from rag_baseline.adaptive_router import ProbeJudge, retrieve_probe
    from rag_baseline.router_probe import distribution_decision

    rag = service()
    probe, _ = await retrieve_probe(rag, "Pergunta", top_k=10)
    initial = probe.sha256()
    distribution_decision(probe, threshold=0.7)
    result = await ProbeJudge(rag.openrouter, model="same/router-model").judge("Pergunta", probe)
    assert result.status == "valid"
    payload = json.loads(rag.openrouter.judgments[0]["user_prompt"])
    assert set(payload) == {"query", "probe"}
    assert payload["query"] == "Pergunta"
    assert payload["probe"] == probe.model_dump(mode="json")
    assert "PROBE_TEXT" not in json.dumps(payload)
    assert not {"answer", "expected_scope", "expected_action", "gold"} & set(payload)
    assert probe.sha256() == initial


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,output,status,scope",
    [
        (
            "Compare graduação e pós-graduação.",
            dict(
                scope="ambas",
                needs_clarification=False,
                reason_code="cross_domain_request",
                clarification_question=None,
            ),
            "valid",
            "ambas",
        ),
        (
            "Posso cancelar uma disciplina?",
            dict(
                scope="ambas",
                needs_clarification=False,
                reason_code="cross_domain_request",
                clarification_question=None,
            ),
            "invalid",
            None,
        ),
        (
            "Posso cancelar uma disciplina?",
            dict(
                scope=None,
                needs_clarification=True,
                reason_code="conflicting_probe_evidence",
                clarification_question="Qual nível?",
            ),
            "valid",
            None,
        ),
        ("Pergunta", "not-json", "invalid", None),
        (
            "Pergunta",
            dict(
                scope="graduacao",
                needs_clarification=True,
                reason_code="probe_supports_graduacao",
                clarification_question=None,
            ),
            "invalid",
            None,
        ),
    ],
)
async def test_judge_validates_output_and_never_infers_both_from_mixed_evidence(
    query, output, status, scope
):
    from rag_baseline.adaptive_router import ProbeJudge, retrieve_probe

    rag = service(Remote(output))
    probe, _ = await retrieve_probe(rag, query, top_k=10)
    result = await ProbeJudge(rag.openrouter, model="same/router-model").judge(query, probe)
    assert result.status == status
    assert result.decision.scope == scope
    if scope is None:
        assert result.decision.needs_clarification


@pytest.mark.asyncio
async def test_final_retrieval_can_reuse_embedding_without_changing_top_k():
    rag = service()
    result = await rag.retrieve("Pergunta", sector="pos_graduacao", query_embedding=[0.1, 0.2])
    assert not rag.openrouter.embeds
    assert rag.vector_store.calls == [([0.1, 0.2], 5, {"sector": "pos_graduacao"})]
    assert result[0].content == "FINAL_EVIDENCE"


@pytest.mark.asyncio
async def test_adaptive_graph_discards_probe_chunks_and_reuses_only_query_vector():
    from rag_baseline.agentic import AgenticRagService
    from rag_baseline.versioning import NormativeRegistry, VersionFilter

    rag = service()
    agent = AgenticRagService(
        rag,
        Intent(),
        VersionFilter(NormativeRegistry.load()),
        routing_mode="adaptive_distribution_v2",
        distribution_threshold=0.7,
    )
    result = await agent.query("Na pós-graduação, como funciona?")
    assert len(rag.openrouter.embeds) == 1
    assert [c[1] for c in rag.vector_store.calls] == [10, 5]
    assert rag.vector_store.calls[0][2] == {}
    assert rag.vector_store.calls[1][2]["sector"] == "pos_graduacao"
    assert "excluded_sources" in rag.vector_store.calls[1][2]
    assert "PROBE_TEXT" not in rag.openrouter.generations[0]["user_prompt"]
    assert "FINAL_EVIDENCE" in rag.openrouter.generations[0]["user_prompt"]
    assert result.routing["routing_mode"] == "adaptive_distribution_v2"
