"""Closed Portuguese identity grammar and fixed prototype presentation texts.

Questions addressed to the assistant itself ("qual é o seu nome?", "quem é você?",
"como você funciona?") receive a fixed first-person reply before the Scope Gate, without
model calls or retrieval. The grammar is closed and anchored: the whole message, after
folding case, accents and whitespace and removing at most one leading greeting and one
"Bisco" vocative, must match one pattern. Any extra word or clause (a normative question,
a third party, a quotation) leaves the message to the normal pipeline.

Enabled by ``ASSISTANT_IDENTITY=on`` (prototype default). With ``off`` the conversation
graph is the frozen v3.4 one.
"""

import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType

ROUTE = "assistant_identity"

_INVITATION = (
    " Se quiser, faça uma pergunta sobre normas acadêmicas, por exemplo sobre matrícula, "
    "trancamento ou prazos."
)
_UNOFFICIAL = " Não sou um serviço oficial da UFPI."
_REPLIES = MappingProxyType({
    "name": (
        "Meu nome é Bisco. Sou o assistente normativo da UFPI, um protótipo de pesquisa "
        "de um Trabalho de Conclusão de Curso em Ciência da Computação."
    ),
    "identity": (
        "Sou o Bisco, assistente normativo da UFPI — um protótipo de pesquisa de um "
        "Trabalho de Conclusão de Curso em Ciência da Computação. Respondo dúvidas sobre "
        "normas acadêmicas de graduação e pós-graduação com base nas resoluções do meu "
        "acervo, indicando os dispositivos para você conferir na fonte."
    ),
    "mission": (
        "Sou o Bisco. Respondo dúvidas sobre normas acadêmicas de graduação e "
        "pós-graduação da UFPI com base nas resoluções do meu acervo, indicando os "
        "dispositivos para você conferir na fonte."
    ),
    "operation": (
        "Sou o Bisco. Busco os trechos das resoluções do meu acervo, considero a versão "
        "vigente da norma e verifico se o texto recuperado apoia a resposta antes de "
        "entregá-la. Essa verificação tem limites; por isso indico os dispositivos para "
        "você conferir na fonte."
    ),
    "creator": (
        "Sou o Bisco, desenvolvido como protótipo de pesquisa no TCC II do curso de "
        "Ciência da Computação da UFPI."
    ),
})

_YOU = r"(?:voce|vc|tu)"
_PATTERNS = (
    ("name", re.compile(
        rf"(?:qual (?:e )?(?:o )?(?:seu|teu) nome|como (?:e )?(?:o )?(?:seu|teu) nome|"
        rf"como {_YOU} se chama|como te chamas|como te chamo|"
        rf"como posso (?:te chamar|chamar {_YOU})|{_YOU} tem (?:um )?nome)"
    )),
    ("identity", re.compile(
        rf"(?:quem (?:e {_YOU}|es tu)|{_YOU} e (?:o )?bisco|quem e (?:o )?bisco|"
        r"o que e (?:o )?bisco|"
        rf"{_YOU} e (?:um |uma )?(?:robo|bot|chatbot|ia|inteligencia artificial)|"
        rf"(?:{_YOU} pode |pode )?se apresentar)"
    )),
    ("mission", re.compile(
        rf"(?:o que {_YOU} (?:faz|pode fazer)|(?:para|pra) que {_YOU} serve|"
        rf"(?:como|em que) {_YOU} pode (?:me )?ajudar|"
        r"qual (?:e )?(?:a )?(?:sua|tua) (?:funcao|finalidade))"
    )),
    ("operation", re.compile(rf"(?:como {_YOU} funciona|como funciona o bisco)")),
    ("creator", re.compile(
        rf"(?:quem (?:te (?:criou|desenvolveu|fez)|(?:criou|desenvolveu|fez) {_YOU})|"
        r"quem (?:e )?(?:o )?(?:seu|teu) (?:criador|desenvolvedor))"
    )),
)
_GREETING = re.compile(r"(?:oi|ola|bom dia|boa tarde|boa noite)[\s,.!?:;]+")
_VOCATIVE = re.compile(r"bisco(?:\s*[,!:]\s*|\s+)")
_TRAILING_VOCATIVE = re.compile(r"\s*,\s*bisco$")


@dataclass(frozen=True)
class IdentityReply:
    intent: str
    content: str


def _fold(message: str) -> str:
    text = "".join(
        char for char in unicodedata.normalize("NFKD", message.casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(text.split()).rstrip(".!? ")


def _strip_prefix(pattern: re.Pattern, text: str) -> str:
    match = pattern.match(text)
    return text[match.end():] if match else text


def assistant_identity_reply(message: str) -> IdentityReply | None:
    """Accept a whole assistant-directed question, never a substring or extra clause."""
    text = _fold(message)
    greeting_first = _GREETING.match(text) is not None
    if greeting_first:
        text = _strip_prefix(_GREETING, text)
    leading_vocative = _VOCATIVE.match(text)
    if leading_vocative:
        text = text[leading_vocative.end():]
    if not greeting_first:
        text = _strip_prefix(_GREETING, text)
    if not leading_vocative:
        text = _TRAILING_VOCATIVE.sub("", text)
    text = text.rstrip(".!? ")
    for intent, pattern in _PATTERNS:
        if pattern.fullmatch(text):
            return IdentityReply(intent, _REPLIES[intent] + _UNOFFICIAL + _INVITATION)
    return None
