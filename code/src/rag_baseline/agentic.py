"""LangGraph orchestration over the existing dense RAG service."""

import re
import unicodedata

from langchain_core.messages import AIMessage
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.types import interrupt

from rag_baseline.citation_verifier import mentioned_levels
from rag_baseline.grounding import TemporalGroundingContext, build_temporal_grounding
from rag_baseline.models import QueryResult, RetrievedChunk
from rag_baseline.openrouter import OpenRouterError
from rag_baseline.retrieval_policy import NormativeQueryReferenceParser
from rag_baseline.router import NormativeRouter, RouterDecision
from rag_baseline.router_probe import ProbeDecision
from rag_baseline.routing import is_level_comparison, question_sector
from rag_baseline.routing_normalization import routing_question, without_override_instructions
from rag_baseline.service import CorpusNotIndexedError, RagService, _reference
from rag_baseline.versioning import TemporalIntent, VersionAudit, VersionFilter


class AgenticState(MessagesState, total=False):
    question: str
    clarification: str | None
    decision: RouterDecision | ProbeDecision
    chunks: list[RetrievedChunk]
    audit: VersionAudit
    result: QueryResult
    use_version_filter: bool
    historical: bool
    error: str | None
    routing_audit: dict | None
    query_embedding: list[float] | None
    temporal_intent: TemporalIntent
    manual_scope: str | None
    temporal_grounding: TemporalGroundingContext | None


def classify_temporal_intent(
    question: str, *, registry=None, obsolete_norm_ids=()
) -> TemporalIntent:
    text = "".join(
        c for c in unicodedata.normalize("NFKD", question.lower()) if not unicodedata.combining(c)
    )
    text = re.sub(
        r"\bnao (?:quero|busco|peco) (?:a )?(?:(?:regra|redacao|versao) )?"
        r"(?:atual|vigente|de hoje)\b",
        "",
        text,
    )
    records = registry.norms if registry else []
    ids = [n.norm_id for n in records] or list(obsolete_norm_ids)
    mentioned = []
    for norm_id in ids:
        parts = norm_id.rsplit("-", 2)
        if len(parts) == 3:
            number = r"\.?".join(re.escape(d) for d in parts[1])
            if re.search(rf"\b{number}\s*/\s*{parts[2]}\b", text):
                mentioned.append(norm_id)
    article = re.search(r"\bart(?:igo)?\.?\s*(\d+[a-z]?)", text)
    paragraph = re.search(r"(?:§|paragrafo)\s*(\d+)", text)
    year = re.search(r"\b(?:em|no ano de)\s+((?:19|20)\d{2})\b", text)
    before = bool(
        re.search(
            r"\bantes (?:d[ao] |de )?(?:alteracao|ato alterador)"
            r"|\bantes (?:dessa|desta|desse|deste) (?:alteracao|ato alterador)\b"
            r"(?!\s+(?:cadastral|(?:de|do|da|dos|das)\s+(?!\d)))",
            text,
        )
    )
    past = (
        before
        or bool(year)
        or bool(
            re.search(
                r"\b(historicamente|na epoca|regra antiga|regras antigas|como era|qual era|quais eram)\b",
                text,
            )
        )
        or bool(re.search(r"\b(?:regra|redacao|versao) (?:antiga|anterior|original)\b", text))
    )
    current = bool(re.search(r"\b(atual|atuais|atualmente|hoje|agora|vigente|vigentes)\b", text))
    later = bool(re.search(r"\b(posterior|nova redacao|depois|apos)\b", text))
    # "como era ... e como e ..." coordinates two times in one question.
    coordinated_present = bool(re.search(r"\be\s+como\s+(?:e|esta|fica|ficou)\b", text))
    comparison = (
        past
        and (current or later or coordinated_present)
        and bool(
            coordinated_present
            or re.search(r"\be qual\b|\bcompare\b|\bdiferenca\b|\bcomparacao\b", text)
        )
    )
    validity = bool(
        re.search(
            r"\b(ainda (?:esta |e )?vigente|continua (?:em vigor|vigente)|"
            r"(?:esta|e|permanece|segue)\s+(?:(?:atualmente|ainda)\s+)?(?:vigente|em vigor)|"
            r"(?:esta|foi|e) revogad[ao]|vigencia)\b",
            text,
        )
    ) or bool(re.search(r"\bainda\s+(?:vale|se aplica)(?:\s+(?:hoje|atualmente))?\s*[?!.]*$", text))
    according = False
    obsolete = obsolete_norm_ids or [
        n.norm_id for n in records if n.status in ("revogada", "substituida")
    ]
    for norm_id in obsolete:
        parts = norm_id.rsplit("-", 2)
        if len(parts) == 3 and re.search(
            rf"\b(segundo|conforme|nos termos d[ao])\s+(?:a\s+)?"
            rf"(?:resolucao\s*(?:(?:cepex|ufpi)(?:\s*/\s*(?:cepex|ufpi))?\s*)?"
            rf"(?:n[ºo°]?\.?\s*)?)?{re.escape(parts[1])}\s*/\s*{parts[2]}\b",
            text,
        ):
            according = True
    mode = (
        "comparison"
        if comparison
        else "validity"
        if validity
        else "current"
        if current
        else "historical"
        if past or according
        else "indeterminate"
    )
    # A documentary wording request is not a claim of legal applicability on
    # a calendar date. Mixed wording/validity questions retain the conservative
    # date policy, even when they mention an edition or update year.
    document_year = re.search(
        r"\b(?:atualizad[oa]|versao|edicao|snapshot)\s+(?:(?:em|de)\s+)?((?:19|20)\d{2})\b",
        text,
    )
    historical_wording = (
        mode == "historical"
        and (before or document_year is not None)
        and bool(re.search(r"\b(?:redacao|texto|versao|snapshot|edicao)\b", text))
        and not re.search(
            r"\b(?:vig\w*|valid\w*|aplic\w*|val(?:e|eu|ia|iam)|reg(?:ia|iam|eu)|"
            r"em vigor|forca (?:de lei|juridica|normativa))\b",
            text,
        )
    )
    return TemporalIntent(
        mode=mode,
        norm_ids=mentioned,
        before_amendment=before,
        relation_query="amendment"
        if re.search(r"\bqual (?:norma|resolucao|ato) alterou\b", text)
        else None,
        article=article.group(1) if article else None,
        paragraph=paragraph.group(1) if paragraph else None,
        requested_year=int(year.group(1)) if year and not historical_wording else None,
        historical_wording=historical_wording,
        document_year=int(document_year.group(1)) if historical_wording and document_year else None,
    )


def is_historical_question(question: str, *, obsolete_norm_ids=()) -> bool:
    return classify_temporal_intent(question, obsolete_norm_ids=obsolete_norm_ids).needs_history


def build_graph(
    service: RagService | None = None,
    router: NormativeRouter | None = None,
    version_filter: VersionFilter | None = None,
    *,
    interactive=False,
    checkpointer=None,
    routing_mode="intent_v1",
    probe_top_k=10,
    distribution_threshold=None,
):
    def dependencies():
        nonlocal service, router, version_filter
        if service is None:
            from rag_baseline.api import _Runtime
            from rag_baseline.config import BaselineSettings
            from rag_baseline.profiles import apply_profile

            settings = BaselineSettings()
            runtime = _Runtime(apply_profile(settings, settings.CORPUS_PROFILE))
            configured = runtime.agentic()
            service, router, version_filter = (
                configured.service,
                configured.router,
                configured.version_filter,
            )
        return service, router, version_filter

    def clarification_result(state, *, unresolved=False):
        service, _, _ = dependencies()
        decision = state["decision"]
        question = decision.clarification_question
        error = (
            decision.reason_code
            if decision.reason_code in ("router_error", "invalid_model_decision")
            else None
        )
        return QueryResult(
            answer="Ainda faltam informações sobre o nível do curso." if unresolved else question,
            references=[],
            llm_model=service.llm_model,
            embedding_model=service.embedding_model,
            route=decision.model_dump(),
            needs_clarification=True,
            clarification_question=None if unresolved else question,
            selected_scope=None,
            response_kind="clarification",
            generation_attempts=0,
            error=error,
            routing=state.get("routing_audit"),
        )

    def _single_cited_norm_sector(question):
        """One registered norm named by the user settles its level without inference."""
        _, _, version_filter = dependencies()
        if is_level_comparison(question):
            return None
        registry = version_filter.registry
        parsed = NormativeQueryReferenceParser(registry).parse(question)
        if len(parsed.norm_ids) != 1 or parsed.unknown_norm:
            return None
        return next((n.sector for n in registry.norms if n.norm_id == parsed.norm_ids[0]), None)

    async def decide(question, clarification, manual_scope=None):
        service, router, _ = dependencies()
        if manual_scope:
            reason = {
                "graduacao": "explicit_graduacao",
                "pos_graduacao": "explicit_pos",
                "ambas": "cross_norm_comparison",
            }[manual_scope]
            return (
                RouterDecision(
                    scope=manual_scope,
                    needs_clarification=False,
                    clarification_question=None,
                    reason_code=reason,
                ),
                None,
                None,
            )
        if routing_mode == "intent_v1":
            # Only a declared level can skip domain inference. The parent
            # conversation has already performed the independent scope triage.
            # Existing pending replies still go through the clarification flow.
            level_text = routing_question(without_override_instructions(question))
            sector = (
                question_sector(level_text, explicit_only=True) if clarification is None else None
            )
            resolved_by = "explicit_level"
            if sector is None and clarification is None:
                sector = _single_cited_norm_sector(level_text)
                resolved_by = "explicit_norm"
            if sector is not None:
                return (
                    RouterDecision(
                        scope=sector,
                        needs_clarification=False,
                        clarification_question=None,
                        reason_code="explicit_pos"
                        if sector == "pos_graduacao"
                        else "explicit_graduacao",
                    ),
                    {
                        "mode": "intent_v1",
                        "explicit_sector_fast_path_used": True,
                        "resolved_sector": sector,
                        "resolved_by": resolved_by,
                        "router_calls": 0,
                    },
                    None,
                )
            return (
                await router.route(
                    level_text,
                    clarification=routing_question(clarification)
                    if clarification is not None
                    else None,
                ),
                None,
                None,
            )
        from rag_baseline.adaptive_router import AdaptiveRouter

        outcome = await AdaptiveRouter(
            service,
            router,
            mode=routing_mode,
            threshold=distribution_threshold,
            probe_top_k=probe_top_k,
        ).route(question, clarification=clarification)
        return outcome.decision, outcome.audit, outcome.query_embedding

    async def route_query(state):
        _, router, version_filter = dependencies()
        question = state.get("question")
        if state.get("messages") and state["messages"][-1].type == "human":
            question = str(state["messages"][-1].content)
            clarification = None
        else:
            clarification = state.get("clarification")
        if not question or not question.strip():
            raise ValueError("A pergunta não pode estar vazia.")
        decision, routing_audit, query_embedding = await decide(
            question, clarification, state.get("manual_scope")
        )
        temporal = classify_temporal_intent(
            question + "\n" + (clarification or ""), registry=version_filter.registry
        )
        return {
            "question": question,
            "decision": decision,
            "historical": temporal.needs_history,
            "temporal_intent": temporal,
            "chunks": [],
            "clarification": clarification,
            "result": None,
            "error": None,
            "routing_audit": routing_audit,
            "query_embedding": query_embedding,
            "temporal_grounding": None,
        }

    def after_route(state):
        return "clarify" if state["decision"].needs_clarification else "retrieve"

    def clarify(state):
        # Never repeat a clarification, including failed scope extraction after resumption.
        if not interactive or state.get("clarification") is not None:
            result = clarification_result(state, unresolved=state.get("clarification") is not None)
            return {
                "result": result,
                "messages": [AIMessage(content=result.answer)],
                "clarification": None,
            }
        answer = interrupt(state["decision"].clarification_question)
        return {"clarification": str(answer)}

    def after_clarify(state):
        return END if state.get("result") is not None else "reroute"

    async def reroute(state):
        _, router, version_filter = dependencies()
        decision, routing_audit, query_embedding = await decide(
            state["question"], state["clarification"]
        )
        result = None
        if decision.needs_clarification:
            result = clarification_result(
                {**state, "decision": decision, "routing_audit": routing_audit}, unresolved=True
            )
        temporal = classify_temporal_intent(
            state["question"] + "\n" + state["clarification"], registry=version_filter.registry
        )
        updates = {
            "decision": decision,
            "result": result,
            "routing_audit": routing_audit,
            "query_embedding": query_embedding,
            "historical": temporal.needs_history,
            "temporal_intent": temporal,
        }
        if result:
            updates["messages"] = [AIMessage(content=result.answer)]
            updates["clarification"] = None
        return updates

    async def retrieve(state):
        service, _, version_filter = dependencies()
        scope = state["decision"].scope
        excluded = (
            version_filter.excluded_sources(state["temporal_intent"])
            if state.get("use_version_filter", True)
            else []
        )
        try:
            reuse = (
                {"query_embedding": state["query_embedding"]}
                if state.get("query_embedding") is not None
                else {}
            )
            chunks = await service.retrieve(
                state["question"],
                sector=None if scope == "ambas" else scope,
                excluded_sources=excluded,
                **reuse,
            )
            return {"chunks": chunks}
        except (OpenRouterError, CorpusNotIndexedError) as exc:
            return {"chunks": [], "error": type(exc).__name__}

    def filter_context(state):
        service, _, version_filter = dependencies()
        enabled = state.get("use_version_filter", True)
        kept, audit = version_filter.apply(
            state["chunks"],
            historical=state["historical"] or not enabled,
            # Complementary retrieval adds to the dense top-k; it must not displace it.
            top_k=max(service.top_k, len(state["chunks"])),
            temporal_intent=state["temporal_intent"] if enabled else None,
            relation_sector=None if state["decision"].scope == "ambas" else state["decision"].scope,
        )
        audit.requested_top_k = service.top_k
        audit.shortfall = max(0, service.top_k - len(kept))
        audit.enabled = enabled
        audit.historical = state["historical"]
        if enabled:
            sources = version_filter.excluded_sources(state["temporal_intent"])
            audit.prefilter_exclusions = [
                n for n in version_filter.registry.norms if any(s in sources for s in n.sources)
            ]
            audit.prefilter_excluded_norm_ids = [n.norm_id for n in audit.prefilter_exclusions]
        if enabled and any(r.reason == "amendment_unresolved" for r in audit.removed_references):
            # Unrelated surviving articles cannot establish the unresolved wording.
            kept = []
            audit.final_references = []
            audit.shortfall = service.top_k
            audit.insufficient_reason = "amendment_unresolved"
        if enabled and state["temporal_intent"].requested_year:
            # A documentary snapshot cannot establish applicability on a calendar date.
            # Norm numbering/signature years are not effective dates.
            kept = []
            audit.final_references = []
            audit.shortfall = service.top_k
            audit.insufficient_reason = "chronology_unresolved"
        if enabled and state["temporal_intent"].mode == "comparison":
            present = {
                version_filter.registry.record_for(c).norm_id
                for c in kept
                if version_filter.registry.record_for(c) is not None
            }
            if not set(state["temporal_intent"].norm_ids) <= present:
                kept = []
                audit.final_references = []
                audit.shortfall = service.top_k
                audit.insufficient_reason = "comparison_evidence_missing"
        grounding = (
            build_temporal_grounding(kept, audit, version_filter.registry)
            if kept and enabled
            else None
        )
        return {"chunks": kept, "audit": audit, "temporal_grounding": grounding}

    async def generate(state):
        service, _, _ = dependencies()
        chunks = state["chunks"]
        question = state["question"]
        if state.get("clarification") is not None:
            question += "\nESCLARECIMENTO DO USUÁRIO:\n" + state["clarification"]
        notice = None
        if state.get("use_version_filter", True):
            notice = (
                "O snapshot documental não certifica vigência global. Status por norma: "
                + str(state["audit"].norm_statuses)
                + ". Status desconhecida não significa vigente; não certifique vigência atual "
                "sem evidência. Não infira datas de publicação, eficácia ou retroatividade."
            )
            if state["temporal_intent"].mode == "comparison":
                notice += (
                    "\nCOMPARAÇÃO TEMPORAL: distinga expressamente a redação histórica "
                    "da posterior, sem aplicar ambas ao mesmo período."
                )
            elif state["historical"]:
                notice += (
                    "\nCONSULTA HISTÓRICA: contextualize temporalmente a resposta; "
                    "não apresente a redação histórica como regra vigente hoje."
                )
            if state["temporal_intent"].historical_wording:
                notice += (
                    "\nCONSULTA DE REDAÇÃO DOCUMENTAL: descreva o texto do snapshot "
                    "disponível, anterior à alteração quando indicado. document_year "
                    "é a referência documental solicitada, não uma certificação de "
                    "vigência ou de data de edição. Não afirme aplicabilidade jurídica "
                    "universal naquele ano. Distinga a redação anterior da alteração posterior."
                )
        if chunks:
            try:
                result = await service.generate(
                    question,
                    chunks,
                    context_notice=notice,
                    **(
                        {"temporal_grounding": state["temporal_grounding"]}
                        if state.get("temporal_grounding") is not None
                        else {}
                    ),
                    # Scope "ambas" is also the default; require both levels in the user's text.
                    **(
                        {"expected_sides": ["graduacao", "pos_graduacao"]}
                        if state["decision"].scope == "ambas"
                        and getattr(service, "generation_mode", "free_text_v2") == "cited_v3"
                        and mentioned_levels(question) == {"graduacao", "pos_graduacao"}
                        else {}
                    ),
                )
            except OpenRouterError:
                result = QueryResult(
                    answer="Não foi possível gerar a resposta. Tente novamente.",
                    references=[_reference(c) for c in chunks],
                    llm_model=service.llm_model,
                    embedding_model=service.embedding_model,
                    error="generation_error",
                )
        else:
            result = QueryResult(
                answer="Não há contexto normativo elegível suficiente para responder.",
                references=[],
                llm_model=service.llm_model,
                embedding_model=service.embedding_model,
                generation_attempts=0,
                error=state.get("error"),
            )
        result.route = None if state.get("manual_scope") else state["decision"].model_dump()
        result.needs_clarification = False
        result.selected_scope = state["decision"].scope
        result.version_filter = state["audit"].model_dump(mode="json")
        result.routing = state.get("routing_audit")
        return {
            "result": result,
            "messages": [AIMessage(content=result.answer)],
            "clarification": None,
        }

    graph = StateGraph(AgenticState)
    for name, node in (
        ("route_query", route_query),
        ("clarify", clarify),
        ("reroute", reroute),
        ("retrieve", retrieve),
        ("version_filter", filter_context),
        ("generate", generate),
    ):
        graph.add_node(name, node)
    graph.set_entry_point("route_query")
    graph.add_conditional_edges("route_query", after_route)
    graph.add_conditional_edges("clarify", after_clarify)
    graph.add_conditional_edges("reroute", lambda s: END if s.get("result") else "retrieve")
    graph.add_edge("retrieve", "version_filter")
    graph.add_edge("version_filter", "generate")
    graph.add_edge("generate", END)
    return graph.compile(checkpointer=checkpointer)


class AgenticRagService:
    def __init__(
        self,
        service: RagService,
        router: NormativeRouter,
        version_filter: VersionFilter,
        *,
        routing_mode="intent_v1",
        probe_top_k=10,
        distribution_threshold=None,
    ):
        self.service = service
        self.router = router
        self.version_filter = version_filter
        self.graph = build_graph(
            service,
            router,
            version_filter,
            routing_mode=routing_mode,
            probe_top_k=probe_top_k,
            distribution_threshold=distribution_threshold,
        )

    async def query(self, question, *, clarification=None, use_version_filter=True, scope=None):
        if scope not in (None, "graduacao", "pos_graduacao", "ambas"):
            raise ValueError("Escopo manual inválido.")
        state = await self.graph.ainvoke(
            dict(
                question=question,
                clarification=clarification,
                use_version_filter=use_version_filter,
                manual_scope=scope,
            )
        )
        return state["result"]
