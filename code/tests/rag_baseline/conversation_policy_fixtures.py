"""Real integrated graph/core with controlled provider I/O and an in-memory store."""

from dataclasses import asdict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from test_normative_tool_facade import Provider

from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.conversation_contracts import (
    ConversationIdentity,
    NormativeMemoryCompatibilityStamp,
)
from rag_baseline.corpus import load_corpus
from rag_baseline.models import RetrievedChunk
from rag_baseline.router import NormativeRouter
from rag_baseline.scope_gate import NormativeScopeGate
from rag_baseline.service import RagService
from rag_baseline.tool_facade import NormativeRagFacade
from rag_baseline.versioning import REGISTRY_PATH, NormativeRegistry, VersionFilter

ABOUT = [
    "quem é você?",
    "quem é voce?",
    "o que você faz?",
    "o que voce faz?",
    "como você pode me ajudar?",
    "para que você serve?",
]
EXTERNAL = "quantos anos tem a cidade mais antiga do piauí?"
NEW_QUERY = (
    "Faço mestrado e estou doente. Qual é a diferença entre cancelar uma matéria e trancar o curso?"
)
NORMATIVE = [
    "qual é a frequência mínima que preciso ter?",
    "posso cancelar uma disciplina?",
    "como funciona o trancamento?",
    "o que é a Láurea Universitária?",
    "Quanto tempo tenho para terminar o mestrado?",
    "Sou mestrando e já dei aula. Posso ser dispensado do estágio de docência?",
    "Essa resolução ainda vale?",
    "O que o professor tem que apresentar no primeiro dia de aula?",
]
EXPLICIT_POST_QUESTIONS = frozenset(
    {
        "Quanto tempo tenho para terminar o mestrado?",
        "Sou mestrando e já dei aula. Posso ser dispensado do estágio de docência?",
        NEW_QUERY,
    }
)


class GateProvider:
    llm_model = "controlled-scope-model"

    def __init__(self):
        self.decision, self.calls = "IN_SCOPE_NORMATIVE", []

    async def structured_chat(self, **kwargs):
        import json

        self.calls.append(json.loads(kwargs["user_prompt"]))
        return json.dumps({"decision": self.decision})


class Probe:
    def __init__(self, scope_gate=None):
        self.provider = Provider(scope=None)
        self.scope_provider = GateProvider()
        self.router_calls, self.retrieval_calls = [], []
        corpus_root = REGISTRY_PATH.parent.parent / "evaluation/corpora"
        chunks = {}
        for sector, article, prefix in [
            ("graduacao", "112", "ufpi-177-2012"),
            ("pos_graduacao", "38", "ufpi-956-2025"),
        ]:
            chunks[sector] = next(
                chunk
                for chunk in load_corpus(
                    corpus_root / (sector + "_setor_v2.json"), id_prefix=prefix
                )
                if chunk.article_number == article
            )

        class Store:
            def count(self):
                return 2

            def query(self, embedding, top_k, *, sector=None, excluded_sources=None):
                assert top_k == 5
                selected = [chunks[sector]] if sector else list(chunks.values())
                return [
                    RetrievedChunk(**chunk.model_dump(), distance=0.1, rank=i + 1)
                    for i, chunk in enumerate(selected)
                ]

        service = RagService(
            openrouter=self.provider,
            vector_store=Store(),
            top_k=5,
            embedding_model="fake",
            llm_model="fake",
        )
        router = NormativeRouter(self.provider)
        native_route, native_retrieve = router.route, service.retrieve

        async def route(question, *, clarification=None):
            self.router_calls.append(dict(question=question, clarification=clarification))
            return await native_route(question, clarification=clarification)

        async def retrieve(question, **kwargs):
            self.retrieval_calls.append(question)
            return await native_retrieve(question, **kwargs)

        router.route, service.retrieve = route, retrieve
        stamp = NormativeMemoryCompatibilityStamp(
            core_version="structured_output_v2",
            contract_version="1",
            corpus_fingerprint="a" * 64,
            registry_fingerprint="b" * 64,
        )
        kwargs = {}
        if scope_gate is not None:
            import inspect

            assert "scope_gate" in inspect.signature(build_integrated_graph).parameters, (
                "Integrated scope gate dependency is missing"
            )
            kwargs["scope_gate"] = scope_gate
        else:
            kwargs["scope_gate"] = NormativeScopeGate(self.scope_provider)
        self.graph = build_integrated_graph(
            NormativeRagFacade(service, router, VersionFilter(NormativeRegistry.load())),
            checkpointer=InMemorySaver(),
            memory_stamp=stamp,
            **kwargs,
        )
        self.identity = ConversationIdentity(
            user_id="policy-probe", agent_id="chatbot_ufpi_integrated_v1", thread_id=str(uuid4())
        )
        self.config = {"configurable": {"thread_id": self.identity.storage_key()}}
        self.state = None

    def counts(self):
        return (
            len(self.router_calls),
            len(self.retrieval_calls),
            len(self.provider.routes) + len(self.provider.embeddings) + len(self.provider.prompts),
        )

    def pending(self):
        memory = self.state.get("conversation_memory") if self.state else None
        return (
            memory.pending_clarification.model_dump(mode="json")
            if memory and memory.pending_clarification
            else None
        )

    async def send(self, text):
        self.state = await self.graph.ainvoke(
            {"messages": [("human", text)], "conversation_identity": self.identity}, self.config
        )
        return self.state

    async def record(self, text, expected):
        self.scope_provider.decision = (
            "OUT_OF_SCOPE" if expected == "OUT_OF_SCOPE" else "IN_SCOPE_NORMATIVE"
        )
        before, counts = self.pending(), self.counts()
        state = await self.send(text)
        after = self.pending()
        audit = asdict(state["turn_audit"])
        return dict(
            question=text,
            expected_action=expected,
            observed_action=audit["conversation_action"],
            router_calls=self.counts()[0] - counts[0],
            scope_gate_decision=audit["scope_gate_decision"],
            scope_gate_provider_calls=audit["scope_gate_provider_calls"],
            scope_gate_latency_ms=audit["scope_gate_latency_ms"],
            scope_gate_status=audit["scope_gate_status"],
            retrieval_calls=self.counts()[1] - counts[1],
            provider_calls=self.counts()[2] - counts[2],
            pending_before=before,
            pending_after=after,
            correlation=audit["correlation_id"],
            correlation_changed=(audit["correlation_id"] != before["correlation_id"])
            if before and audit["correlation_id"]
            else None,
            router_inputs=self.router_calls[counts[0] :],
            final_content=state["messages"][-1].content,
            normative_status=state["normative_result"].status
            if state.get("normative_result")
            else None,
        )


async def collect_probes():
    records = []
    for text in ABOUT + [EXTERNAL]:
        records.append(
            await Probe().record(text, "OUT_OF_SCOPE" if text == EXTERNAL else "ABOUT_ASSISTANT")
        )
    probe = Probe()
    records.append(await probe.record(EXTERNAL, "OUT_OF_SCOPE"))
    probe.provider.scope = "pos_graduacao"
    records.append(await probe.record(NEW_QUERY, "NORMATIVE_RAG"))
    for interrupt, action in [
        ("obrigado", "SAFE_DIRECT"),
        ("quem é você?", "ABOUT_ASSISTANT"),
        (EXTERNAL, "OUT_OF_SCOPE"),
        ("cancele", "CLEAR_PENDING"),
    ]:
        probe = Probe()
        records.append(await probe.record("Posso cancelar uma disciplina?", "NORMATIVE_RAG"))
        records.append(await probe.record(interrupt, action))
        if interrupt != "cancele":
            probe.provider.scope = "pos_graduacao"
            records.append(await probe.record("pós", "CONTINUE_CLARIFICATION"))
    probe = Probe()
    records.append(await probe.record("Posso cancelar uma disciplina?", "NORMATIVE_RAG"))
    probe.provider.scope = "pos_graduacao"
    records.append(await probe.record(NEW_QUERY, "NORMATIVE_RAG"))
    return records
