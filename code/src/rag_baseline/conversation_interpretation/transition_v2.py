"""Transition policy v2 (A''-J v2): the v1 policy with three bounded safety corrections.

Same inputs as v1, same interpreter, same contract. Differences, all structural:

P1. An explicit new question (or cancellation) is never consumed by, nor dropped in favour
    of, the pending operation. The new question runs; the superseded pending operation is
    recorded, exactly as A' supersedes a pending operation with any new question.
P2. A level read as belonging to a third party never resolves the user's pending question,
    is never stored, and never lets the user's own stored level leak into a question about
    that person. A question about the third party may use their explicit level for that
    query only.
P3. When the closed A' grammar matches the whole message (the only way A' reaches
    CONTINUE_CLARIFICATION or DECLARE_LEVEL), A' decides. Outside the grammar nothing
    changes: the grammar is never a filter on what the interpreter may recognise.

Persistence outside the grammar additionally requires the user as subject (``self``).
"""

import re
from dataclasses import dataclass

from rag_baseline.conversation_interpretation.contracts import MEMORY_LEVEL, fold
from rag_baseline.conversation_interpretation.transition import (
    _GRAMMAR_ONLY,
    ASK_QUESTION,
    CANONICAL_CLARIFICATION,
    INTERPRETABLE,
    REASK_GENERIC,
    REASK_UNCLEAR_LEVEL,
    TransitionDecision,
    clarification_for,
)
from rag_baseline.conversation_policy import FollowUpAction

POLICY_VERSION = "transition-v2"
REASK_THIRD_PARTY = (
    "O nível que você mencionou parece ser de outra pessoa. {question} "
    "Se a sua dúvida é sobre essa pessoa, envie a pergunta completa."
)
QUERY_LEVEL_TEXT = {"undergraduate": "graduação", "postgraduate": "pós-graduação"}
CONFIRM_RESUME = (
    "Entendi que você informou o nível ({level}). Quer que eu responda à pergunta anterior "
    "nesse nível? Responda só com o nível para confirmar ou envie a nova pergunta completa."
)
LEVEL_NAME = {"undergraduate": "graduação", "postgraduate": "pós-graduação", "both": "ambos"}

# Words that never make a request of their own: level vocabulary, pronouns, articles,
# prepositions, copulas and conversational markers. Used only to decide whether a reply
# that also states a level carries an independent request. A word missing from this
# closed list counts as content, so an omission errs towards running the message as a
# new question (never towards consuming it as the pending answer).
_LEVEL_TOKEN = re.compile(
    r"(?:pos|posgraduac\w*|graduac\w*|graduand\w*|mestrad\w*|mestrand\w*|doutorad\w*"
    r"|doutorand\w*|stricto|sensu|lato|bacharelad\w*|licenciatur\w*|especializac\w*"
    r"|ambos|ambas|dois|duas|nivel)"
)
_NON_CONTENT = frozenset(
    """eu voce vc me meu minha sou estou sao seu sua tou faco estudo nao sim mesmo mas
    pra para por com que dos das nos nas num numa uma uns umas isso isto aqui ali ali
    entao assim como qual quais tambem tbm ainda agora ja ok certo blz beleza valeu
    obrigado obrigada brigado ue hein uai opa oi ola entendi falei disse disso pois enfim
    tipo kkk kkkk desculpa desculpe foi mal nada bom boa dia tarde noite claro exato
    sei acho era eita nossa poxa putz hmm esquece esqueca deixa deixe cancela cancelar
    cancele preciso precisa mais importa mudando mudar assunto outro outra""".split()
)


def has_independent_content(message: str) -> bool:
    """True when the message contains a word that can carry a request of its own."""
    for token in re.findall(r"[a-z0-9]+", fold(message)):
        if token.isdigit():
            return True  # a year, a period, a number: a detail of a request of its own
        if len(token) <= 2 or token in _NON_CONTENT or _LEVEL_TOKEN.fullmatch(token):
            continue
        return True
    return False


@dataclass(frozen=True)
class TransitionDecisionV2(TransitionDecision):
    defer_to_base: bool = False
    suppress_declared_level: bool = False
    query_level: str | None = None
    superseded_pending: bool = False
    policy_version: str = POLICY_VERSION


class TransitionPolicyV2:
    version = POLICY_VERSION

    def decide(self, base, outcome, context) -> TransitionDecisionV2:
        # R1: structural decisions; R0: technical failure (A' keeps full control).
        if base not in INTERPRETABLE or outcome is None:
            return TransitionDecisionV2(base, "structural_or_not_interpreted", base)
        if not outcome.ok:
            return TransitionDecisionV2(
                base, f"interpreter_{outcome.status}", base, defer_to_base=True
            )
        i = outcome.interpretation
        # R2 (P3): the closed grammar matched the whole message as the answer to this
        # thread's pending request; A' decides. A grammar *declaration* without a pending
        # request defers only when the reading reports nothing else: the grammar also
        # accepts elliptic level questions such as "e na pós" (independent review A3).
        if base == FollowUpAction.CONTINUE_CLARIFICATION:
            return TransitionDecisionV2(base, "grammar_precedence", base, defer_to_base=True)
        if base == FollowUpAction.DECLARE_LEVEL and not (
            i.has_new_question or i.cancels_pending or i.level_subject == "third_party"
        ):
            return TransitionDecisionV2(base, "grammar_precedence", base, defer_to_base=True)

        pending = context.has_pending_operation
        level, evidence, subject = i.declared_level, i.level_evidence, i.level_subject
        grounded = level != "none" and bool(i.evidence_spans)
        explicit = grounded and evidence == "explicit"
        third = subject == "third_party"
        own_level = MEMORY_LEVEL.get(level) if explicit and subject == "self" else None
        explicit_new = i.has_new_question or i.cancels_pending
        # Once grammar precedence is declined, a grammar base is never executed as such:
        # it would declare or resume without a level (re-verification N1).
        run_base = FollowUpAction.NORMATIVE_RAG if base in _GRAMMAR_ONLY else base

        def ask(reason, message):
            return TransitionDecisionV2(
                FollowUpAction.CLARIFY_INTENT, reason, base, direct_message=message
            )

        def pending_question():
            return context.pending_clarification_question or "Qual é o nível acadêmico?"

        def run_question(reason, superseded=False):
            # The user's full text always: an extraction is never substituted (spec R3).
            action = run_base
            query_level = None
            if third and explicit and level in QUERY_LEVEL_TEXT:
                query_level = QUERY_LEVEL_TEXT[level]
            return TransitionDecisionV2(
                action,
                reason,
                base,
                persist_level=own_level,
                persist_source="explicit_declaration" if own_level else None,
                clear_pending=pending and i.cancels_pending,
                suppress_declared_level=third,
                query_level=query_level,
                superseded_pending=superseded,
            )

        # R3 (P1): an explicit new question or cancellation with a pending operation.
        # A reply that references the pending request and states a level, but has no
        # content beyond level words and conversational markers, may be a plain answer
        # mislabelled as carrying a question. It is never resumed on that judgement: the
        # user is asked which request to answer (no retrieval, no persistence). A missing
        # word in the closed list only turns that question into running the message.
        reply_only = (
            not i.cancels_pending
            and i.references_pending
            and not third
            and grounded
            and evidence in {"explicit", "indirect"}
            and not has_independent_content(context.message)
        )
        if (
            pending
            and i.cancels_pending
            and not i.has_new_question
            and not has_independent_content(context.message)
        ):
            # A cancellation with nothing else to answer: A' CLEAR_PENDING (review A4).
            # With content of its own (re-verification N2) the message runs below.
            return TransitionDecisionV2(
                FollowUpAction.CLEAR_PENDING, "cancel_without_question", base
            )
        if pending and explicit_new and reply_only:
            return ask(
                "level_reply_confirm_resume",
                CONFIRM_RESUME.format(level=LEVEL_NAME.get(level, level)),
            )
        if pending and explicit_new:
            return run_question(
                "cancel_runs_new_question"
                if i.cancels_pending
                else "new_question_supersedes_pending",
                superseded=not i.cancels_pending,
            )

        # R4a (P2): a third party's level never answers the user's pending question.
        if pending and third and level != "none":
            return ask(
                "third_party_level_not_used_for_pending",
                REASK_THIRD_PARTY.format(question=pending_question()),
            )

        # R5: legitimate resumption.
        if pending and i.intent in {"clarification", "level_declaration"}:
            if grounded and evidence in {"explicit", "indirect"}:
                return TransitionDecisionV2(
                    FollowUpAction.CONTINUE_CLARIFICATION,
                    f"{i.intent}_resumes_pending",
                    base,
                    clarification_text=clarification_for(context.message, level),
                    persist_level=own_level,
                    persist_source="confirmed_clarification" if own_level else None,
                )
            return ask(
                f"{i.intent}_level_not_usable",
                REASK_UNCLEAR_LEVEL.format(question=pending_question()),
            )

        if i.intent in {"clarification", "level_declaration"}:
            # R6: a declaration without a pending operation.
            if own_level:
                return TransitionDecisionV2(
                    FollowUpAction.DECLARE_LEVEL,
                    "self_declaration",
                    base,
                    persist_level=own_level,
                    persist_source="explicit_declaration",
                )
            return ask("declaration_not_storable", ASK_QUESTION)

        if i.intent in {"new_question", "mixed"}:
            return run_question(i.intent if i.intent == "new_question" else "mixed_new_question")

        # uncertain
        if i.has_new_question:
            return TransitionDecisionV2(
                run_base,
                "uncertain_with_question_keeps_base",
                base,
                suppress_declared_level=third,
            )
        if pending and level != "none":
            return ask(
                "uncertain_with_pending",
                (REASK_UNCLEAR_LEVEL if evidence == "hedged" else REASK_GENERIC).format(
                    question=pending_question()
                ),
            )
        return TransitionDecisionV2(
            run_base, "uncertain_keeps_base", base, suppress_declared_level=third
        )


__all__ = [
    "CANONICAL_CLARIFICATION",
    "POLICY_VERSION",
    "TransitionDecisionV2",
    "TransitionPolicyV2",
]
