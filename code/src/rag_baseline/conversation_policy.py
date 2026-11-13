"""Bounded conversation decisions; normative domain/temporal routing stays in core."""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from rag_baseline.agent_policy import AgentActionPolicy
from rag_baseline.calculator import CalculatorIntentParser
from rag_baseline.calculator_contracts import CalculatorRequest
from rag_baseline.routing import is_level_comparison, question_sector
from rag_baseline.routing_normalization import routing_question

_DOMAIN_PREFIX = {
    "graduacao": "Na graduação",
    "pos_graduacao": "Na pós-graduação",
    "ambas": "Na graduação e na pós-graduação",
}
_CONTINUATION_LEAD = "em continuidade a: "
_CONTINUATION_NOW = "Pergunta de continuidade: "
_LEVEL_WORDS = r"\b(?:graduação|pós|mestrado|doutorado|ambos|ambas)\b"


def normalize(text):
    return unicodedata.normalize("NFC", text).strip().casefold().rstrip(".!?").rstrip()


class FollowUpAction(StrEnum):
    SAFE_DIRECT = "SAFE_DIRECT"
    ABOUT_ASSISTANT = "ABOUT_ASSISTANT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CLEAR_PENDING = "CLEAR_PENDING"
    CALCULATOR = "CALCULATOR"
    DECLARE_LEVEL = "DECLARE_LEVEL"
    # Only reachable when a conversation interpreter is configured (A'' conditions).
    CLARIFY_INTENT = "CLARIFY_INTENT"
    CONTINUE_CLARIFICATION = "CONTINUE_CLARIFICATION"
    GROUNDED_TRANSFORM = "GROUNDED_TRANSFORM"
    CONTEXTUAL_NORMATIVE_RAG = "CONTEXTUAL_NORMATIVE_RAG"
    CONTINUATION_NORMATIVE_RAG = "CONTINUATION_NORMATIVE_RAG"
    NORMATIVE_RAG = "NORMATIVE_RAG"


TRANSFORMS = {
    "repita": "REPEAT",
    "explique melhor": "REPHRASE",
    "explique mais simples": "REPHRASE",
    "em outras palavras": "REPHRASE",
    "resuma": "SUMMARY",
    "resuma isso": "SUMMARY",
}
DOMAIN_TARGETS = {
    "e na pós": "Na pós-graduação",
    "e na pós-graduação": "Na pós-graduação",
    "e na graduação": "Na graduação",
    "e para ambos": "Na graduação e na pós-graduação",
}
_REFERENT = (
    r"(?:pedido|solicitacao|requerimento|prazo|caso|situacao|regra|procedimento|processo"
    r"|recurso|motivo|pedidos|solicitacoes|requerimentos|prazos|casos|situacoes|regras"
    r"|procedimentos|processos|recursos|motivos|resolucao|norma|artigo|dispositivo"
    r"|resolucoes|normas|artigos|dispositivos)"
)
_DEMONSTRATIVE = re.compile(
    r"\b(?:isso|disso|nisso|(?:d|n)?(?:esse|essa|este|esta|esses|essas|estes|estas)\s+"
    + _REFERENT
    # "esse pedido de trancamento" names its own subject.
    + r")\b(?!\s*,?\s+(?:de|do|da|dos|das|para|sobre)\b)"
)
_SHORT_ELLIPSIS = re.compile(
    r"e\s+(?:(?:qual|quais)\s+(?:e|sao|seria|seriam)\s+(?:o|a|os|as)\s+" + _REFERENT + r""
    r"|(?:como|onde|quando|quem)\s+(?:faco|solicito|peco|protocolo|recorro|decide|aprova|analisa)"
    r"|(?:o|a|os|as|quanto\s+ao|quanto\s+a)\s+" + _REFERENT + r")"
)
_QUESTION_LEAD = re.compile(
    r"(?:e|como|qual|quais|quem|quando|onde|quanto|quantos|quantas|o que|pode|posso"
    r"|isso|nisso|(?:d|n)?(?:esse|essa|este|esta|esses|essas|estes|estas))\b"
)
_FUNCTION_WORDS = frozenset(
    """e qual quais como quando onde quem quanto quantos quantas o a os as que de do da dos das
    para por em no na ao aos se seria seriam sao faco fazer posso pode podem devo deve
    solicitar pedir protocolar apresentar prazo prazos pos pos-graduacao graduacao mestrado
    doutorado motivo motivos
    ainda tambem vale valem valia aplica aplicam continua continuam vigente vigentes vigor
    hoje atualmente agora atual era eram foi tinha tem permitido permitida obrigatorio
    obrigatoria possivel mudou alterou alterado alterada alteracao revogado revogada revogou
    depois apos antes essa esta dessa desse ficou redacao resolucao norma decide aprova analisa""".split()
)
_PRESENT_MARKER = re.compile(
    r"\b(?:atual|atuais|atualmente|hoje|agora|vigente|vigentes|vigor|vale|valem|continua|continuam)\b"
)
_SECTOR_LEAD = re.compile(
    r"(?:na|no|para a|para o)\s+(?:pos(?:[- ]graduacao)?|graduacao|mestrado|doutorado),?\s+"
)
_NEW_SUBJECT = re.compile(
    r"(?:mudando de assunto|outra (?:duvida|pergunta|coisa)|sobre outro assunto"
    r"|nova (?:duvida|pergunta)|agora sobre|outro assunto)\b"
)
_CITATION = re.compile(r"\d+\s*/\s*\d{4}|ufpi-\d+-\d+|\bart(?:igo)?\.?\s*\d", re.I)
_MAX_RESOLVED_QUESTION = 3000
CANCEL = frozenset({"cancelar", "cancele", "esquece", "deixa pra lá", "deixa para lá"})
ABOUT_ASSISTANT_RESPONSE = (
    "Sou um assistente especializado em normas acadêmicas da UFPI. Posso ajudar com "
    "dúvidas sobre matrícula, cancelamento, trancamento, prazos, graduação e "
    "pós-graduação com base nas normas indexadas no sistema."
)
_ABOUT_ASSISTANT = frozenset(
    {"quem e voce", "o que voce faz", "como voce pode me ajudar", "para que voce serve"}
)
OUT_OF_SCOPE_RESPONSE = (
    "Posso ajudar com dúvidas sobre normas acadêmicas da UFPI, como matrícula, "
    "cancelamento, trancamento, prazos, graduação e pós-graduação."
)


def _closed_text(text: str) -> str:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFKD", normalize(text))
        if not unicodedata.combining(char)
    )
    return " ".join(folded.split()).rstrip(".!?").rstrip()


_LATER_WORDING = re.compile(r"\b(?:depois|após|apos|posterior|nova redação|nova redacao)\b", re.I)
_PAST_TO_PRESENT = (
    (re.compile(r"\bcomo era\b", re.I), "como é"),
    (re.compile(r"\bqual era\b", re.I), "qual é"),
    (re.compile(r"\bquais eram\b", re.I), "quais são"),
)
_TEMPORAL_FRAGMENT = re.compile(
    r"\b(?:antes|depois|após)\s+(?:d[ao]\s+|de\s+|dessa\s+|desta\s+|desse\s+|deste\s+)?(?:alteração|ato alterador)(?:\s+de\s+\d{4})?"
    r"|\b(?:atualizad[oa]|versão|edição|snapshot)\s+(?:(?:em|de)\s+)?(?:19|20)\d{2}\b"
    r"|\b(?:em|no ano de)\s+(?:19|20)\d{2}\b"
    r"|\b(?:atual|atuais|atualmente|hoje|agora|vigente|vigentes|na época|historicamente)\b",
    re.I,
)


def _without_temporal_context(text: str) -> str | None:
    """Return the subject without its time, or None if the two cannot be separated."""
    subject = text
    for pattern, replacement in _PAST_TO_PRESENT:
        subject = pattern.sub(replacement, subject)
    subject = _TEMPORAL_FRAGMENT.sub("", subject)
    subject = re.sub(r"\s+([,?.!])", r"\1", re.sub(r"\s+", " ", subject))
    subject = re.sub(r"[,\s]+([?.!])", r"\1", subject).strip(" ,")
    words = re.findall(r"\w{4,}", subject)
    if _has_temporal_signal(subject) or len(words) < 2:
        return _normative_anchors(text) or None
    return subject


def _has_temporal_signal(text: str) -> bool:
    from rag_baseline.agentic import classify_temporal_intent

    intent = classify_temporal_intent(text)
    return bool(
        _LATER_WORDING.search(text)
        or intent.mode != "indeterminate"
        or intent.requested_year
        or intent.document_year
        or intent.before_amendment
    )


def _normative_anchors(text: str) -> str:
    articles = re.findall(r"\bart(?:igo)?\.?\s*\d+[a-zºª°]?(?:\s*,?\s*§\s*\d+[º°]?)?", text, re.I)
    norms = re.findall(r"\b\d+(?:\.\d{3})?\s*/\s*\d{4}\b", text)
    return ", ".join([*articles, *(f"Resolução {norm}" for norm in norms)])


def is_referential_follow_up(text: str) -> bool:
    """Closed grammar: the message refers to the previous subject and brings no subject of its own."""
    closed = _closed_text(text)
    if not closed or _NEW_SUBJECT.search(closed) or _CITATION.search(text):
        return False
    # "antes da alteração atual" asks about two times at once; the classifier cannot tell which.
    if re.search(r"\bantes\b", closed) and _PRESENT_MARKER.search(closed):
        return False
    closed = _SECTOR_LEAD.sub("", closed, count=1) if _SECTOR_LEAD.match(closed) else closed
    if _SHORT_ELLIPSIS.fullmatch(closed):
        return True
    found = _DEMONSTRATIVE.search(closed)
    if found is None or not _QUESTION_LEAD.match(closed):
        return False
    # A referent only points back when nothing before it introduces a subject of its own.
    if re.search(r"[?!.]\s+\S", text.strip()):
        return False
    # The whole message is closed: any other word may name a subject of its own.
    rest = f"{closed[: found.start()]} {closed[found.end() :]}"
    return all(
        word in _FUNCTION_WORDS or re.fullmatch(r"(?:19|20)\d{2}", word)
        for word in re.findall(r"[\w-]+", rest)
    )


# What a procedure usually leaves open. It names a gap in the active subject, never a subject.
_GAP_TERMS = frozenset(
    term[:6]
    for term in """prazo prazos requerimento requerer pedido pedir solicitacao solicitar documento
    documentos comprovante comprovantes comprovacao comprovar formulario formularios anexar anexo
    entregar entrega entrego protocolar protocolo local condicao condicoes requisito requisitos
    exigencia exigencias cumprir perder perdi atrasar""".split()
)
_GAP_FUNCTION_WORDS = _FUNCTION_WORDS | frozenset(
    """eu meu minha preciso precisa algum alguma alguns algumas ha isso disso nisso esse essa este
    esta esses essas estes estas desse dessa deste desta nesse nessa neste nesta la aqui ele ela
    mas entao com sem sobre ser sera tenho""".split()
)
_GAP_LEAD = re.compile(
    r"(?:e|como|qual|quais|quem|quando|onde|quanto|preciso|precisa|tem|ha|devo)\b"
)
_MAX_GAP_WORDS = 8


def _subject_terms(text: str) -> set[str]:
    return {word[:6] for word in re.findall(r"[a-z]{4,}", _closed_text(text))}


def fills_gap_in_active_subject(text: str, active_subject: str | None) -> bool:
    """The state of this conversation decides: every content word must belong to its subject.

    A word outside the active subject and outside the closed gap class is a subject of its
    own, so the message stands alone and the scope gate judges it alone.
    """
    if not active_subject or not active_subject.strip():
        return False
    closed = _closed_text(text)
    words = re.findall(r"[\w-]+", closed)
    if (
        not words
        or len(words) > _MAX_GAP_WORDS
        or _NEW_SUBJECT.search(closed)
        or _CITATION.search(text)
        or not _GAP_LEAD.match(closed)
    ):
        return False
    # A level named in the message moves the subject: only a pure gap can carry it over.
    moved = question_sector(routing_question(text), explicit_only=True) is not None
    active = set() if moved else _subject_terms(active_subject)
    return all(
        word in _GAP_FUNCTION_WORDS
        or re.fullmatch(r"(?:19|20)\d{2}", word)
        or word[:6] in _GAP_TERMS
        or word[:6] in active
        for word in words
    )


def clarification_level(text: str) -> str | None:
    """Resolve the closed R1 reply grammar with the existing sector mechanism."""
    reply = _closed_text(text)
    if reply in {"ambas", "ambos", "os dois", "as duas"}:
        return "ambas"
    if not re.fullmatch(r"(?:na )?(?:graduacao|pos(?:[- ]graduacao)?)", reply):
        # Preserve legacy replies above, but do not treat a natural question as a declaration.
        if "?" in text:
            return None
        declaration = re.fullmatch(
            r"(?:(?:sou (?:(?:aluno|aluna|estudante) )?(?:de|da|do)"
            r"|faco|curso|estou (?:na|no)|estou cursando(?: [oa])?|e (?:sobre a|na|da)) )?"
            r"(?P<level>graduacao|pos(?:[- ]graduacao)?|mestrado|doutorado|stricto sensu)"
            r"|sou (?P<student>mestrand[oa]|doutorand[oa]|graduand[oa])",
            reply,
        )
        if declaration is None:
            return None
        reply = declaration["level"] or declaration["student"]
        if reply in {"graduando", "graduanda"}:
            reply = "graduacao"
    if reply in {"pos", "na pos"}:
        reply += "-graduacao"
    return question_sector(reply)


def is_direct_clarification(text: str) -> bool:
    """Only a complete level-only reply may resume a pending operation."""
    return clarification_level(text) is not None


def declared_level_clarification(text: str, level: str | None) -> str | None:
    """A stored declaration only supplies a missing level in a new single-level query."""
    question = routing_question(text)
    if (
        level not in {"graduacao", "pos_graduacao"}
        or question_sector(question, explicit_only=True) is not None
        or is_level_comparison(question)
        or re.search(r"\b(?:pos|ambas|ambos|os dois|as duas|dois niveis)\b", _closed_text(text))
    ):
        return None
    return "graduação" if level == "graduacao" else "pós-graduação"


@dataclass(frozen=True)
class FollowUpDecision:
    action: FollowUpAction
    transform_kind: str | None = None
    calculator_request: CalculatorRequest | None = None
    reason_code: str = "requires_normative_tool"


class ConversationFollowUpPolicy:
    def decide(self, text, *, pending=False, active_subject=None):
        normalized = normalize(text)
        if pending and normalized in CANCEL:
            return FollowUpDecision(FollowUpAction.CLEAR_PENDING)
        if AgentActionPolicy().decide(text).action == "DIRECT":
            return FollowUpDecision(FollowUpAction.SAFE_DIRECT)
        if _closed_text(text) in _ABOUT_ASSISTANT:
            return FollowUpDecision(FollowUpAction.ABOUT_ASSISTANT)
        intent = CalculatorIntentParser().parse(text)
        if intent.is_calculator_intent:
            return FollowUpDecision(
                FollowUpAction.CALCULATOR,
                calculator_request=intent.parsed_request,
                reason_code=intent.reason_code,
            )
        if pending and is_direct_clarification(text):
            return FollowUpDecision(FollowUpAction.CONTINUE_CLARIFICATION)
        if (
            not pending
            and "?" not in text
            and clarification_level(text)
            in {
                "graduacao",
                "pos_graduacao",
            }
        ):
            return FollowUpDecision(FollowUpAction.DECLARE_LEVEL)
        if normalized in TRANSFORMS:
            return FollowUpDecision(FollowUpAction.GROUNDED_TRANSFORM, TRANSFORMS[normalized])
        if re.fullmatch(r"resuma em [1-9] linhas?", normalized):
            return FollowUpDecision(FollowUpAction.GROUNDED_TRANSFORM, "SUMMARY")
        if re.fullmatch(r"explique em [1-9] passos?", normalized):
            return FollowUpDecision(FollowUpAction.GROUNDED_TRANSFORM, "REPHRASE")
        if normalized in DOMAIN_TARGETS:
            return FollowUpDecision(FollowUpAction.CONTEXTUAL_NORMATIVE_RAG)
        if not pending and (
            is_referential_follow_up(text) or fills_gap_in_active_subject(text, active_subject)
        ):
            return FollowUpDecision(FollowUpAction.CONTINUATION_NORMATIVE_RAG)
        return FollowUpDecision(FollowUpAction.NORMATIVE_RAG)


class ContextualNormativeQueryResolver:
    def resolve_continuation(self, current, previous_question, previous_domain):
        """Combine the current message with the last answered question of this conversation."""
        if not previous_question or previous_domain not in _DOMAIN_PREFIX:
            return None
        explicit = question_sector(routing_question(current), explicit_only=True)
        domain = explicit or previous_domain
        changed = explicit is not None and explicit != previous_domain
        # An old document/article cannot be implicitly mapped to a different norm.
        if changed and _CITATION.search(previous_question):
            return None
        topic = previous_question.replace(_CONTINUATION_LEAD, "").replace(_CONTINUATION_NOW, "")
        topic = re.sub(
            r"\b(?:na|da|para(?:\s+a)?)\s+(?:pós(?:-graduação)?|graduação)\b[,]?",
            "",
            topic,
            flags=re.I,
        )
        topic = re.sub(r"\s+", " ", topic).strip(" ,")
        if not topic or (changed and re.search(_LEVEL_WORDS, topic, re.I)):
            return None
        if _has_temporal_signal(current) and _has_temporal_signal(topic):
            # The current message decides the time, so the previous one keeps only its subject.
            topic = _without_temporal_context(topic)
            if not topic:
                return None
        resolved = (
            f"{_DOMAIN_PREFIX[domain]}, {_CONTINUATION_LEAD}{topic} {_CONTINUATION_NOW}{current}"
        )
        return resolved if len(resolved) <= _MAX_RESOLVED_QUESTION else None

    def resolve(self, current, previous_question, previous_domain):
        target = DOMAIN_TARGETS.get(normalize(current))
        if (
            not target
            or not previous_question
            or previous_domain not in {"graduacao", "pos_graduacao", "ambas"}
        ):
            return None
        # An old document/article cannot be implicitly mapped to a different norm.
        if re.search(
            r"\d+\s*/\s*\d{4}|ufpi-\d+-\d+|\bart(?:igo)?\.?\s*\d", previous_question, re.I
        ):
            return None
        topic = re.sub(
            r"\b(?:na|da|para(?:\s+a)?)\s+(?:pós(?:-graduação)?|graduação)\b[,]?",
            "",
            previous_question,
            flags=re.I,
        )
        topic = re.sub(r"\s+", " ", topic).strip(" ,")
        if not topic or re.search(
            r"\b(?:graduação|pós|mestrado|doutorado|ambos|ambas)\b", topic, re.I
        ):
            return None
        return f"{target}, {topic[0].lower()}{topic[1:]}"
