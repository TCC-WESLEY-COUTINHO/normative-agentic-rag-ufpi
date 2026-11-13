"""Elliptical follow-ups reuse the typed state of the same conversation, and nothing else."""

import pytest
from conversation_policy_fixtures import Probe
from test_conversation_memory_followups import Facade, identity, stamp, turn

from rag_baseline import conversation_graph as c
from rag_baseline.agent_graph import build_integrated_graph
from rag_baseline.agentic import classify_temporal_intent
from rag_baseline.conversation_policy import (
    ContextualNormativeQueryResolver,
    ConversationFollowUpPolicy,
    FollowUpAction,
)
from rag_baseline.routing import question_sector
from rag_baseline.routing_normalization import routing_question
from rag_baseline.scope_gate import ScopeGateResult
from rag_baseline.versioning import NormativeRegistry, VersionFilter

Q03 = "Quais motivos são aceitos para justificar a minha ausência em uma avaliação e solicitar a segunda chamada?"
Q04 = "Graduação."
Q05 = "E qual é o prazo para fazer esse pedido?"
FIRST = "Na graduação, como funciona a segunda chamada?"


class Gate:
    def __init__(self, decision="IN_SCOPE_NORMATIVE"):
        self.decision, self.questions = decision, []

    async def classify(self, question):
        self.questions.append(question)
        return ScopeGateResult(self.decision, "classified", 1, 0.0)


class DomainFacade(Facade):
    def __init__(self, domain="graduacao"):
        super().__init__()
        self.domain = domain

    async def query(self, **kwargs):
        result = await super().query(**kwargs)
        if result.status != "ANSWER":
            return result
        changed = result.model_copy(update={"domain": self.domain})
        self.results[-1] = changed
        return changed


def build(saver, facade, gate=None, current=None):
    return build_integrated_graph(
        facade,
        checkpointer=saver,
        memory_stamp=current or stamp(c),
        scope_gate=gate if gate is not None else Gate(),
    )


def explicit_sector(question):
    return question_sector(routing_question(question), explicit_only=True)


@pytest.fixture
def saver():
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


@pytest.mark.asyncio
async def test_q03_q04_q05_keeps_sector_and_subject_from_typed_state(saver):
    facade, gate = DomainFacade(), Gate()
    graph, who = build(saver, facade, gate), identity(c)
    facade.status = "CLARIFICATION"
    await turn(graph, who, Q03)
    facade.status = "ANSWER"
    await turn(graph, who, Q04)
    assert facade.calls[-1]["clarification"] == Q04
    state = await turn(graph, who, Q05)
    call = facade.calls[-1]
    assert Q03 in call["question"] and Q05 in call["question"]
    assert explicit_sector(call["question"]) == "graduacao"
    assert call["clarification"] is None
    assert state["turn_audit"].conversation_action == "CONTINUATION_NORMATIVE_RAG"
    assert state["normative_result"].status == "ANSWER"
    assert state["conversation_memory"].pending_clarification is None


@pytest.mark.asyncio
async def test_q03_q04_q05_needs_no_router_call_on_the_real_core():
    probe = Probe()
    probe.provider.scope = None
    first = await probe.send(Q03)
    assert first["normative_result"].status == "CLARIFICATION"
    probe.provider.scope = "graduacao"
    second = await probe.send(Q04)
    assert second["normative_result"].status == "ANSWER"
    routes = len(probe.provider.routes)
    third = await probe.send(Q05)
    assert third["normative_result"].status == "ANSWER"
    assert third["normative_result"].domain == "graduacao"
    assert len(probe.provider.routes) == routes
    assert Q03 in probe.retrieval_calls[-1] and Q05 in probe.retrieval_calls[-1]


@pytest.mark.asyncio
async def test_gate_sees_the_current_message_and_can_still_refuse_it(saver):
    facade, gate = DomainFacade(), Gate()
    graph, who = build(saver, facade, gate), identity(c)
    await turn(graph, who, FIRST)
    calls = len(facade.calls)
    gate.decision = "OUT_OF_SCOPE"
    state = await turn(graph, who, "E qual é o cardápio do RU nesse caso?")
    assert gate.questions[-1] == "E qual é o cardápio do RU nesse caso?"
    assert len(facade.calls) == calls
    assert state["turn_audit"].conversation_action == "OUT_OF_SCOPE"
    assert state["conversation_memory"].last_normative_question == FIRST


@pytest.mark.parametrize(
    "text",
    [
        "Qual é a frequência mínima?",
        "Posso trancar o curso?",
        "Mudando de assunto, qual é o prazo desse pedido?",
        "Outra dúvida: qual é o prazo desse pedido?",
        "Sobre outro assunto, isso vale para bolsas?",
        "E esse curso tem bolsa?",
        "Qual é o prazo do art. 108 da Resolução 177/2012?",
    ],
)
@pytest.mark.asyncio
async def test_independent_or_deliberately_new_questions_keep_their_own_text(saver, text):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, FIRST)
    state = await turn(graph, who, text)
    assert facade.calls[-1]["question"] == text
    assert state["turn_audit"].conversation_action == "NORMATIVE_RAG"


@pytest.mark.asyncio
async def test_explicit_sector_in_the_current_message_prevails(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, FIRST)
    await turn(graph, who, "E na pós, qual é o prazo desse pedido?")
    question = facade.calls[-1]["question"]
    assert explicit_sector(question) == "pos_graduacao"
    assert "como funciona a segunda chamada" in question
    assert "Na graduação" not in question


@pytest.mark.asyncio
async def test_cited_norm_is_not_carried_to_another_sector(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, "Na graduação, o que diz o art. 108 da Resolução 177/2012?")
    text = "E na pós, qual é o prazo desse pedido?"
    state = await turn(graph, who, text)
    assert facade.calls[-1]["question"] == text
    assert state["turn_audit"].conversation_action == "NORMATIVE_RAG"


@pytest.mark.asyncio
async def test_cited_norm_stays_in_the_same_sector_continuation(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    previous = "Na graduação, o que diz o art. 108 da Resolução 177/2012?"
    await turn(graph, who, previous)
    await turn(graph, who, "E qual é o prazo desse pedido?")
    question = facade.calls[-1]["question"]
    assert "art. 108 da Resolução 177/2012" in question
    assert explicit_sector(question) == "graduacao"


@pytest.mark.asyncio
async def test_other_conversation_has_no_access_to_the_context(saver):
    facade = DomainFacade()
    graph = build(saver, facade)
    await turn(graph, identity(c, thread="X"), FIRST)
    state = await turn(graph, identity(c, thread="Y"), Q05)
    assert facade.calls[-1]["question"] == Q05
    assert state["turn_audit"].conversation_action == "NORMATIVE_RAG"
    state = await turn(graph, identity(c, user="B", thread="X"), Q05)
    assert facade.calls[-1]["question"] == Q05


@pytest.mark.asyncio
async def test_first_message_is_not_a_continuation(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, Q05)
    assert facade.calls[-1]["question"] == Q05


@pytest.mark.asyncio
async def test_incompatible_memory_is_not_reused(saver):
    facade = DomainFacade()
    who = identity(c)
    await turn(build(saver, facade), who, FIRST)
    newer = build(saver, facade, current=stamp(c, corpus_fingerprint="c" * 64))
    state = await turn(newer, who, Q05)
    assert facade.calls[-1]["question"] == Q05
    assert state["turn_audit"].memory_status != "VALID"


@pytest.mark.asyncio
async def test_pending_clarification_is_not_resolved_by_a_continuation(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, FIRST)
    facade.status = "CLARIFICATION"
    await turn(graph, who, Q03)
    state = await turn(graph, who, Q05)
    assert facade.calls[-1]["question"] == Q05
    assert facade.calls[-1]["clarification"] is None
    assert state["conversation_memory"].pending_clarification.original_question == Q05


@pytest.mark.asyncio
async def test_cancelled_clarification_leaves_nothing_to_continue(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    facade.status = "CLARIFICATION"
    await turn(graph, who, Q03)
    calls = len(facade.calls)
    state = await turn(graph, who, "cancelar")
    assert state["conversation_memory"].pending_clarification is None
    assert len(facade.calls) == calls
    await turn(graph, who, Q05)
    assert facade.calls[-1]["question"] == Q05


@pytest.mark.asyncio
async def test_answer_for_both_levels_continues_for_both_levels(saver):
    facade = DomainFacade(domain="ambas")
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, "Compare a segunda chamada entre graduação e pós-graduação")
    state = await turn(graph, who, Q05)
    assert state["turn_audit"].conversation_action == "CONTINUATION_NORMATIVE_RAG"
    assert "graduação e na pós-graduação" in facade.calls[-1]["question"]


@pytest.mark.asyncio
async def test_chained_continuations_stay_readable_and_bounded(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, FIRST)
    await turn(graph, who, Q05)
    await turn(graph, who, "E como faço esse pedido?")
    question = facade.calls[-1]["question"]
    assert question.count("Na graduação") == 1
    assert question.count("Pergunta de continuidade:") == 1
    for _ in range(60):
        await turn(graph, who, "E como faço esse pedido?")
    assert len(facade.calls[-1]["question"]) <= 4000


@pytest.mark.parametrize(
    "text",
    [
        "E qual é o prazo?",
        "E qual é o prazo para fazer esse pedido?",
        "E quanto a esse prazo?",
        "Nesse caso, quem decide?",
        "E como faço esse requerimento?",
        "e quais são esses motivos?",
    ],
)
def test_grammar_accepts_referential_follow_ups(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        == FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "text",
    [
        "Qual é o prazo?",
        "Qual é a frequência mínima para aprovação?",
        "E qual é a média necessária para aprovação direta em uma disciplina obrigatória?",
        "E na pós?",
        "Resuma isso",
        "Quantos créditos preciso completar no mestrado?",
        "Mudando de assunto, e isso?",
    ],
)
def test_grammar_rejects_questions_with_their_own_subject(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


def test_pending_blocks_the_grammar():
    decision = ConversationFollowUpPolicy().decide(Q05, pending=True)
    assert decision.action == FollowUpAction.NORMATIVE_RAG


@pytest.mark.parametrize(
    "previous,domain",
    [(None, "graduacao"), (FIRST, None), (FIRST, "desconhecido"), ("x" * 3990, "graduacao")],
)
def test_resolver_refuses_without_usable_state(previous, domain):
    assert ContextualNormativeQueryResolver().resolve_continuation(Q05, previous, domain) is None


@pytest.mark.parametrize(
    "text",
    [
        "E como é o trancamento?",
        "E quantos créditos tem o mestrado?",
        "E quanto custa o RU?",
        "E onde fica a PREG?",
        "E quando abre a matrícula?",
        "E qual é a frequência mínima?",
        "Obrigado por isso",
        "Quero cancelar isso",
    ],
)
def test_grammar_rejects_own_subject_and_non_questions(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "text",
    [
        "E quem decide?",
        "E como faço?",
        "E o prazo?",
        "Como faço isso?",
        "Isso é permitido?",
        "Qual o motivo disso?",
    ],
)
def test_grammar_keeps_follow_ups_without_their_own_subject(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        == FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


TEMP_GRAD_002 = (
    "Como era a redação do art. 68, §4º da Resolução 177/2012 no regulamento "
    "da graduação atualizado em 2023, antes da alteração de 2026?"
)


def combined_intent(current, previous, domain):
    question = ContextualNormativeQueryResolver().resolve_continuation(current, previous, domain)
    assert question is not None
    return classify_temporal_intent(question, registry=NormativeRegistry.load())


def test_combined_question_adds_no_temporal_signal():
    intent = combined_intent(Q05, FIRST, "graduacao")
    assert intent.mode == "indeterminate"
    assert intent.requested_year is None and intent.document_year is None


def test_historical_wording_survives_a_neutral_follow_up():
    intent = combined_intent("E esse prazo?", TEMP_GRAD_002, "graduacao")
    assert intent.mode == "historical"
    assert intent.historical_wording is True
    assert intent.document_year == 2023
    assert intent.requested_year is None


def test_current_validity_question_does_not_inherit_the_document_year():
    question = ContextualNormativeQueryResolver().resolve_continuation(
        "Isso ainda vale hoje?", TEMP_GRAD_002, "graduacao"
    )
    assert "art. 68" in question and "177/2012" in question
    assert "2023" not in question and "antes da alteração" not in question
    intent = classify_temporal_intent(question, registry=NormativeRegistry.load())
    assert intent.mode == "validity"
    assert intent.requested_year is None and intent.document_year is None
    assert intent.before_amendment is False
    assert tuple(intent.norm_ids) == ("ufpi-177-2012",)


def test_year_of_the_current_message_replaces_the_previous_year():
    intent = combined_intent(
        "E em 2024, isso era permitido?", "Qual era a regra em 2020 na graduação?", "graduacao"
    )
    assert intent.requested_year == 2024


def test_neutral_previous_question_keeps_its_subject_with_a_temporal_follow_up():
    question = ContextualNormativeQueryResolver().resolve_continuation(
        "Isso ainda vale hoje?", FIRST, "graduacao"
    )
    assert "como funciona a segunda chamada" in question


def test_question_about_a_revoked_norm_is_not_turned_into_a_comparison_by_the_wrapper():
    previous = "Segundo a Resolução 658/2024, como era a antecedência para divulgar a defesa?"
    intent = combined_intent("E esse prazo?", previous, "pos_graduacao")
    assert intent.mode == "historical"
    assert tuple(intent.norm_ids) == ("ufpi-658-2024",)


@pytest.mark.parametrize(
    "text",
    [
        "Qual o prazo desse pedido de trancamento?",
        "E isso? Mudando de assunto, qual o prazo da matrícula?",
        "Esse prazo? Outra dúvida: como funciona a matrícula?",
    ],
)
def test_new_explicit_subject_is_not_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "text",
    [
        "Essa resolução ainda vale?",
        "Esse artigo ainda vale?",
        "Na pós-graduação, esse prazo também vale?",
        "No mestrado, esse prazo também vale?",
    ],
)
def test_legitimate_continuations_are_accepted(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        == FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


def test_explicit_sector_prefix_keeps_the_subject_and_changes_the_sector():
    question = ContextualNormativeQueryResolver().resolve_continuation(
        "Na pós-graduação, esse prazo também vale?", FIRST, "graduacao"
    )
    assert question_sector(routing_question(question), explicit_only=True) == "pos_graduacao"
    assert "como funciona a segunda chamada" in question
    assert "Na graduação" not in question


def test_previous_citation_is_not_carried_to_a_new_sector_by_the_prefix():
    previous = "Na graduação, o que diz o art. 108 da Resolução 177/2012?"
    assert (
        ContextualNormativeQueryResolver().resolve_continuation(
            "Na pós-graduação, esse prazo também vale?", previous, "graduacao"
        )
        is None
    )


@pytest.mark.asyncio
async def test_independent_question_does_not_inherit_a_previous_citation(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, "Na graduação, o que diz o art. 68 da Resolução 177/2012?")
    text = "Qual o prazo desse pedido de trancamento?"
    await turn(graph, who, text)
    assert facade.calls[-1]["question"] == text


AFTER = "E depois dessa alteração, como ficou esse dispositivo?"


def test_question_about_the_later_wording_does_not_inherit_the_previous_wording():
    question = ContextualNormativeQueryResolver().resolve_continuation(
        AFTER, TEMP_GRAD_002, "graduacao"
    )
    assert "art. 68" in question and "177/2012" in question
    assert "antes da alteração" not in question and "2023" not in question
    intent = classify_temporal_intent(question, registry=NormativeRegistry.load())
    assert intent.before_amendment is False
    assert intent.historical_wording is False
    assert intent.document_year is None and intent.requested_year is None
    assert intent.mode != "historical"


def test_later_wording_reaches_the_amended_text():
    from rag_baseline.retrieval_policy import RetrievalStrategySelector

    question = ContextualNormativeQueryResolver().resolve_continuation(
        AFTER, TEMP_GRAD_002, "graduacao"
    )
    registry = NormativeRegistry.load()
    intent = classify_temporal_intent(question, registry=registry)
    excluded = VersionFilter(registry).excluded_sources(intent)
    assert not [source for source in excluded if "1.056" in source or "1056" in source]
    assert RetrievalStrategySelector(registry).select(question, scope="graduacao")


def test_temporal_follow_up_keeps_a_subject_without_citation():
    previous = "Na graduação, qual era o prazo para solicitar segunda chamada em 2020?"
    question = ContextualNormativeQueryResolver().resolve_continuation(
        "Isso ainda vale hoje?", previous, "graduacao"
    )
    assert "segunda chamada" in question
    assert "2020" not in question
    intent = classify_temporal_intent(question, registry=NormativeRegistry.load())
    assert intent.mode == "validity" and intent.requested_year is None


def test_subject_that_cannot_be_separated_from_its_time_is_not_combined():
    assert (
        ContextualNormativeQueryResolver().resolve_continuation(
            "Isso ainda vale hoje?", "Na época, em 2020?", "graduacao"
        )
        is None
    )


def test_continuation_never_goes_out_without_a_subject():
    resolver = ContextualNormativeQueryResolver()
    for current in ("Isso ainda vale hoje?", "E em 2024, isso era permitido?", Q05):
        question = resolver.resolve_continuation(current, FIRST, "graduacao")
        assert "segunda chamada" in question


@pytest.mark.parametrize(
    "text",
    [
        "Qual é o prazo desse pedido para trancamento?",
        "Qual é o prazo desse pedido, de trancamento?",
        "Qual é o prazo desse pedido sobre trancamento?",
        "E esse requerimento para matrícula?",
    ],
)
def test_referent_followed_by_its_own_subject_is_not_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.asyncio
async def test_own_subject_does_not_carry_the_previous_article(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, "Na graduação, o que diz o art. 68 da Resolução 177/2012?")
    text = "Qual é o prazo desse pedido para trancamento?"
    await turn(graph, who, text)
    assert facade.calls[-1]["question"] == text
    assert "art. 68" not in facade.calls[-1]["question"]


@pytest.mark.parametrize(
    "text",
    [
        "Como funciona o trancamento e qual é o prazo desse pedido?",
        "Como funciona o trancamento? Esse pedido cancela minha matrícula?",
        "Qual o prazo do trancamento nesse caso?",
        "Posso trancar o curso e isso cancela a matrícula?",
        "A matrícula institucional muda esse prazo?",
    ],
)
def test_subject_introduced_before_the_referent_is_not_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.asyncio
async def test_subject_of_its_own_does_not_select_the_previous_article(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, "Na graduação, o que diz o art. 68 da Resolução 177/2012?")
    text = "Como funciona o trancamento e qual é o prazo desse pedido?"
    await turn(graph, who, text)
    assert facade.calls[-1]["question"] == text


@pytest.mark.parametrize(
    "text",
    [
        Q05,
        "E na pós, qual é o prazo desse pedido?",
        "Como faço isso?",
        "Qual é o prazo para apresentar esse recurso?",
        "Nesse caso, quem decide?",
    ],
)
def test_function_words_before_the_referent_remain_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        == FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "text",
    [
        "Esse requerimento administrativo de trancamento tem prazo?",
        "Esse processo seletivo exige entrevista?",
        "Esse prazo também vale para o trancamento?",
        "Isso vale para quem trabalha?",
        "Nesse caso posso trancar o curso?",
        "Isso cai na prova?",
        "Qual é o valor disso?",
    ],
)
def test_subject_after_the_referent_is_not_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "text",
    [
        AFTER,
        "E qual é a redação atual desse artigo?",
        "E em 2024, isso era permitido?",
        "Isso ainda vale hoje?",
        "Esse artigo ainda vale hoje?",
        "Esse artigo tinha qual redação antes da alteração?",
        "Esse dispositivo mudou depois da alteração?",
        "Qual resolução alterou esse dispositivo?",
        "Essa resolução foi revogada?",
    ],
)
def test_temporal_follow_ups_remain_continuations(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        == FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.asyncio
async def test_subject_after_the_referent_does_not_select_the_previous_article(saver):
    facade = DomainFacade()
    graph, who = build(saver, facade), identity(c)
    await turn(graph, who, "Na graduação, o que diz o art. 68 da Resolução 177/2012?")
    text = "Esse requerimento administrativo de trancamento tem prazo?"
    await turn(graph, who, text)
    assert facade.calls[-1]["question"] == text


CURRENT_WORDING = "Na graduação, qual é a redação atual do art. 68, §4º da Resolução 177/2012?"


@pytest.mark.parametrize(
    "text",
    [
        "Esse artigo tinha qual redação antes dessa alteração?",
        "Isso valia antes dessa alteração?",
        "Esse artigo tinha qual redação antes da alteração?",
    ],
)
def test_earlier_wording_after_a_current_question_selects_the_previous_wording(text):
    assert ConversationFollowUpPolicy().decide(text).action == (
        FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )
    question = ContextualNormativeQueryResolver().resolve_continuation(
        text, CURRENT_WORDING, "graduacao"
    )
    assert "atual" not in question
    registry = NormativeRegistry.load()
    intent = classify_temporal_intent(question, registry=registry)
    assert intent.before_amendment is True
    assert intent.mode == "historical"
    assert tuple(intent.norm_ids) == ("ufpi-177-2012",)
    assert VersionFilter(registry).excluded_sources(intent)


@pytest.mark.parametrize(
    "text", ["antes dessa alteração", "antes desta alteração", "antes da alteração"]
)
def test_classifier_recognises_the_demonstrative_forms(text):
    intent = classify_temporal_intent(f"Como era o art. 68 {text}?")
    assert intent.before_amendment is True and intent.mode == "historical"


@pytest.mark.parametrize(
    "text",
    [
        "Esse artigo tinha qual redação antes da alteração atual?",
        "Esse artigo tinha qual redação antes da atual alteração?",
        "Isso valia antes dessa alteração vigente?",
        "Essa norma mudou antes da alteração vigente?",
    ],
)
def test_mixed_time_in_the_same_message_is_not_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "complement",
    ["alteração de coordenador", "alteração de matrícula", "alteração cadastral"],
)
def test_administrative_change_is_not_a_previous_wording(complement):
    question = (
        "Na graduação, segundo o art. 68, §4º da Resolução 177/2012, "
        f"quem devo consultar antes dessa {complement}?"
    )
    intent = classify_temporal_intent(question, registry=NormativeRegistry.load())
    assert intent.before_amendment is False
    assert intent.mode == "indeterminate"


def test_demonstrative_with_a_year_still_refers_to_the_amendment():
    intent = classify_temporal_intent("Como era o art. 68 antes dessa alteração de 2026?")
    assert intent.before_amendment is True


def test_after_this_change_is_a_continuation():
    assert (
        ConversationFollowUpPolicy().decide("Esse artigo mudou após essa alteração?").action
        == FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "text",
    [
        "Esse artigo tinha qual redação antes da alteração de hoje?",
        "Isso valia antes dessa alteração de agora?",
        "Essa norma mudou antes da alteração que vale hoje?",
        "Essa regra era como antes da alteração que vale atualmente?",
        "Esse dispositivo ficou como antes dessa alteração que continua em vigor?",
    ],
)
def test_before_with_any_present_marker_is_not_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        != FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )


@pytest.mark.parametrize(
    "text",
    ["Isso valia antes da alteração?", "Esse artigo tinha qual redação antes dessa alteração?"],
)
def test_before_without_a_present_marker_remains_a_continuation(text):
    assert (
        ConversationFollowUpPolicy().decide(text).action
        == FollowUpAction.CONTINUATION_NORMATIVE_RAG
    )
