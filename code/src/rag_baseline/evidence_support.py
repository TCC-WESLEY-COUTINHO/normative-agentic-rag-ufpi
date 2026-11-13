"""Bounded deterministic support checks between a generated body and its retrieved evidence.

These are conservative signals over text. They do not establish that a claim is legally
correct, and passing them does not certify grounding.
"""

import re
from dataclasses import dataclass

from rag_baseline.content_locators import ARTICLE, NORM, fold, norm_id
from rag_baseline.lexical_retrieval import terms

_BOILERPLATE = frozenset(
    terms(
        """prevista previsto previstas previstos estabelece estabelecido estabelecida determina
        dispoe disposto termos forma exigencia exigencias obrigacao obrigatoria norma cepex ainda
        tambem assim portanto alem disso aluno alunos discente discentes acordo trata tratando
        condicoes respectivo respectiva referida referido mesma mesmo"""
    )
)
_ANAPHORA = re.compile(
    r"^\s*(?:ess[ae]s?|est[ae]s?|tal|tais|a mesma|o mesmo)\b[^.]{0,40}"
    r"\b(?:regra|exigencia|limite|prazo|obrigacao|direito|procedimento|condicao|requisito|norma"
    r"|previs\w+|disposi\w+)\b"
)
_SENTENCE = re.compile(r"(?<!\bart)(?<!\barts)(?<!\bn)(?<![\d§])[.!?]+(?=\s)|\n+")
MIN_CLAIM_TERMS = 3
LOW_SUPPORT = 0.55
CLEAR_MARGIN = 0.3


def _sentences(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in _SENTENCE.finditer(text):
        if text[start : match.start()].strip():
            spans.append((start, match.start()))
        start = match.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


@dataclass(frozen=True)
class CitationMismatch:
    start: int
    end: int
    article: str
    cited_support: float
    better_article: str
    better_support: float


def _claim_terms(text: str) -> set[str]:
    clean = NORM.sub(" ", ARTICLE.sub(" ", text))
    return {term for term in terms(clean) if term not in _BOILERPLATE}


def _support(claim: set[str], document_terms: set[str]) -> float:
    return len(claim & document_terms) / len(claim)


def citation_mismatches(raw: str, evidence: dict, *, related=()) -> list[CitationMismatch]:
    """Flag only when a different retrieved article clearly fits the claim better.

    `related` holds provisions linked by a recorded relation: an amending article and its
    target describe the same rule, so citing one while the other fits better is not an error.
    """
    linked = set(related)
    text = fold(raw)
    documents = {key: set(terms(content)) for key, content in evidence.items()}
    spans = _sentences(text)
    result = []
    for index, (start, end) in enumerate(spans):
        sentence = text[start:end]
        found = list(ARTICLE.finditer(sentence))
        if not found:
            continue
        # Bounded on purpose: only "essa regra está prevista no art. X" says exactly which claim
        # the citation vouches for. On saved answers, wider clause matching flagged correct ones.
        if not index or not _ANAPHORA.search(sentence):
            continue
        claim = _claim_terms(sentence) | _claim_terms(
            text[spans[index - 1][0] : spans[index - 1][1]]
        )
        if len(claim) < MIN_CLAIM_TERMS:
            continue
        norms = {norm_id(match) for match in NORM.finditer(sentence)}
        cited = set()
        for match in found:
            for article in re.findall(r"\d+", match[1]):
                cited |= {
                    key for key in documents if key[1] == article and (not norms or key[0] in norms)
                }
        if not cited or cited & linked:
            continue  # An article outside the evidence is the citation check's own violation.
        best_cited = max(cited, key=lambda key: _support(claim, documents[key]))
        cited_support = _support(claim, documents[best_cited])
        others = [key for key in documents if key not in cited]
        if not others or cited_support >= LOW_SUPPORT:
            continue
        better = max(others, key=lambda key: (_support(claim, documents[key]), key))
        better_support = _support(claim, documents[better])
        if better_support >= cited_support + CLEAR_MARGIN:
            match = found[0]
            result.append(
                CitationMismatch(
                    start + match.start(),
                    start + match.end(),
                    best_cited[1],
                    round(cited_support, 3),
                    better[1],
                    round(better_support, 3),
                )
            )
    return result


_ABSENCE = re.compile(
    r"\b(?:resolucao|regulamento|regimento|norma)\b[^.\n]{0,90}?"
    r"\bnao\s+(?:preve|contem|estabelece|dispoe|menciona|aborda|regula|disciplina|trata)\b"
    r"|\bnao\s+(?:ha|tem|existe)\s+(?:qualquer\s+|nenhuma?\s+)?"
    r"(?:previsao|dispositivo|norma|regra)\b"
)
_LIMITED_TO_CONTEXT = re.compile(
    r"\b(?:trechos?|contexto|evidencias?|fornecid\w+|recuperad\w+|indexad\w+|disponive\w+|consultad\w+)\b"
)


@dataclass(frozen=True)
class AbsenceClaim:
    start: int
    end: int


def absence_claims(raw: str) -> list[AbsenceClaim]:
    """Silence of the retrieved excerpts says nothing about the whole norm."""
    text = fold(raw)
    result = []
    for start, end in _sentences(text):
        sentence = text[start:end]
        if _LIMITED_TO_CONTEXT.search(sentence):
            continue
        for match in _ABSENCE.finditer(sentence):
            # "Se a norma não prevê..." only supposes; a clause after the comma asserts.
            if re.match(r"\s*se\b", sentence) and "," not in sentence[: match.end()]:
                continue
            result.append(AbsenceClaim(start + match.start(), start + match.end()))
    return result


_UNITS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "quatorze": 14, "catorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19,
}  # fmt: skip
_TENS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
         "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100}  # fmt: skip
_WORD = "|".join(sorted({*_UNITS, *_TENS}, key=len, reverse=True))
_MEASURE = (
    r"%|por\s+cento|dias?|meses|mes|anos?|horas?|creditos?|semestres?|periodos?|vezes|pontos?"
    r"|membros?|alunos?"
)
_CLAIM_NUMBER = re.compile(
    rf"\b(?P<digits>\d+(?:,\d+)?)\s*(?:\([a-z ]+\)\s*)?(?P<unit>{_MEASURE})(?![a-z])"
    rf"|\b(?P<words>(?:{_WORD})(?:\s+e\s+(?:{_WORD}))?)\s+(?P<wunit>{_MEASURE})(?![a-z])"
    r"|\b(?P<decimal>\d+,\d+)\b"
)
_ANY_DIGITS = re.compile(r"\d+(?:,\d+)?")
_ANY_WORDS = re.compile(rf"\b({_WORD})(?:\s+e\s+({_WORD}))?\b")


def _digits(value: str) -> str:
    return re.sub(r",0+$", "", value)


def _words(first: str, second: str | None) -> str:
    table = {**_UNITS, **_TENS}
    return str(table[first] + (table[second] if second else 0))


def _known_values(*texts: str) -> set[str]:
    values = set()
    for text in texts:
        folded = fold(text)
        values |= {_digits(m[0]) for m in _ANY_DIGITS.finditer(folded)}
        for match in _ANY_WORDS.finditer(folded):
            values.add(str({**_UNITS, **_TENS}[match[1]]))
            if match[2]:
                values.add(_words(match[1], match[2]))
    return values


@dataclass(frozen=True)
class UnsupportedNumber:
    start: int
    end: int
    value: str


def unsupported_numbers(raw: str, evidence: dict, question: str) -> list[UnsupportedNumber]:
    """A deadline, percentage, grade or count must come from the evidence or the question."""
    known = _known_values(question, *evidence.values())
    result = []
    for match in _CLAIM_NUMBER.finditer(fold(raw)):
        if match["digits"]:
            value = _digits(match["digits"])
        elif match["decimal"]:
            value = _digits(match["decimal"])
        else:
            parts = re.split(r"\s+e\s+", match["words"])
            value = _words(parts[0], parts[1] if len(parts) > 1 else None)
        if value not in known:
            result.append(UnsupportedNumber(match.start(), match.end(), value))
    return result


_DENIAL = re.compile(
    r"\bnao\s+(?:modificou|alterou|mudou|afetou)\b|\bsem\s+alterar\b"
    r"|\bmant(?:em|eve|endo)\s+a\s+redacao\s+original\b"
)


def denied_amendments(raw: str, relations) -> list[tuple[int, int]]:
    """A body cannot say that a recorded amendment left its target provision unchanged."""
    text = fold(raw)
    amended = [r for r in relations if r.relation == "AMENDED_BY"]
    result = []
    if not amended:
        return result
    for start, end in _sentences(text):
        sentence = text[start:end]
        denials = list(_DENIAL.finditer(sentence))
        for index, denial in enumerate(denials):
            # Each denial answers for what it names; earlier text only fills what it omits.
            stop = denials[index + 1].start() if index + 1 < len(denials) else len(sentence)
            own = sentence[denial.end() : stop]
            before = sentence[: denials[0].start()]
            paragraphs = _named_paragraphs(own) or _named_paragraphs(before)
            if re.match(r"\s+(?:o\s+)?caput\b", own) and not _named_paragraphs(own):
                continue
            articles = _named_articles(own) or _named_articles(sentence)
            norms = {norm_id(match) for match in NORM.finditer(sentence)}
            for relation in amended:
                if articles and relation.target_article not in articles:
                    continue
                if paragraphs and relation.target_paragraph not in paragraphs:
                    continue
                if articles or paragraphs or {relation.source_norm, relation.target_norm} & norms:
                    result.append((start + denial.start(), start + denial.end()))
                    break
    return result


def _named_paragraphs(text: str) -> set[str]:
    return set(re.findall(r"(?:§+\s*|paragrafo\s+)(\d+)", text))


def _named_articles(text: str) -> set[str]:
    return set(re.findall(r"\bart(?:igo)?\.?\s*(\d+)", text))


@dataclass(frozen=True)
class RelationMismatch:
    start: int
    end: int
    detail: str


_DAY_QUALIFIER = r"uteis|corridos|letivos|consecutivos"
_DEADLINE = re.compile(
    rf"\b(?:(?P<digits>\d+)\s*(?:\([a-z ]+\)\s*)?"
    rf"|(?P<words>(?:{_WORD})(?:\s+e\s+(?:{_WORD}))?)\s+(?:\(\d+\)\s*)?)"
    rf"dias?(?![a-z])(?:\s+(?P<qualifier>{_DAY_QUALIFIER})\b)?"
)
_START_EVENT = re.compile(
    r"\b(?:a\s+partir\s+d[aoe]s?|apos\s+(?:[oa]s?\s+)?|contad[oa]s?\s+d[aoe]s?)\s*"
    r"(?P<event>[^,.;:\n]+)"
)
_START_STOPWORDS = frozenset(terms("data dia dias prazo contado contados contada este esta"))
# Bounded paraphrases of the same procedural event, compared by term prefix.
_EVENT_SYNONYMS = {"aprova": "deferi", "pedido": "requer"}


def _event_term(term: str) -> str:
    return _EVENT_SYNONYMS.get(term, term)


def _deadline_value(match) -> str:
    if match["digits"]:
        return _digits(match["digits"])
    parts = re.split(r"\s+e\s+", match["words"])
    return _words(parts[0], parts[1] if len(parts) > 1 else None)


def deadline_mismatches(raw: str, evidence: dict) -> list[RelationMismatch]:
    """A day count keeps the qualifier and the starting event its own provision states.

    A value absent from the evidence is left to `unsupported_numbers`. Qualifiers are compared
    across the retrieved evidence, so the same count with another qualifier elsewhere passes.
    The question never authorizes a qualifier: a user asking about "5 dias úteis" is not a source.
    """
    documents = [fold(content) for content in evidence.values()]
    stated = {
        (_deadline_value(match), match["qualifier"] or "")
        for document in documents
        for match in _DEADLINE.finditer(document)
    }
    known = {value for value, _ in stated}
    provisions = [
        (
            {_deadline_value(match) for match in _DEADLINE.finditer(document[start:end])},
            {_event_term(term) for term in terms(document[start:end])},
        )
        for document in documents
        for start, end in _sentences(document)
    ]
    text = fold(raw)
    result = []
    for start, end in _sentences(text):
        sentence = text[start:end]
        for match in _DEADLINE.finditer(sentence):
            value, qualifier = _deadline_value(match), match["qualifier"] or ""
            if value not in known:
                continue
            at = (start + match.start(), start + match.end())
            if (value, qualifier) not in stated:
                result.append(RelationMismatch(*at, f"qualifier:{value}:{qualifier}"))
                continue
            event = _START_EVENT.search(sentence, match.end())
            # A second count before the event means the event belongs to that count.
            if not event or _DEADLINE.search(sentence, match.end(), event.start()):
                continue
            wanted = [t for t in terms(event["event"]) if t not in _START_STOPWORDS]
            # The head noun names the event: "indeferimento do pedido" is not "deferimento".
            if wanted and not any(
                value in values and _event_term(wanted[0]) in words for values, words in provisions
            ):
                result.append(RelationMismatch(*at, f"start:{value}"))
    return result


_ROLE = (
    r"professor(?:es)?|docentes?|chefia|chefe|departamento|coordenac\w+|coordenador\w*|colegiado"
    r"|secretaria|direcao|diretoria|reitoria|pro-reitoria|daa|preg|camen|curso"
)
_ROLE_NAMED = re.compile(rf"\b({_ROLE})\b")
_ROUTED = re.compile(r"\b(?P<verb>protocolad\w*|protocolar|dirigid\w*)\b")
_CLAIM_ROUTE = re.compile(
    r"\b(?P<verb>protocolad\w*|protocolar|dirigid\w*)\s+(?:diretamente\s+|junto\s+)?"
    rf"(?:a|ao|aos|as|na|no|nas|nos|em|perante|pelo|pela)\s+(?:[a-z]+\s+){{0,2}}?(?P<role>{_ROLE})\b"
)
_DECISION = r"julg\w*|decid\w*|defer\w*"
_CLAIM_DECISION = re.compile(
    rf"\b(?:o|a|os|as)\s+(?P<role>{_ROLE})\b(?P<gap>(?:\s+[a-z]+){{0,4}}?)\s+(?:{_DECISION})\b"
)
_PASSIVE_DECISION = re.compile(
    rf"\b(?:julgad\w*|decidid\w*|deferid\w*)\s+(?:pelo|pela|pelos|pelas)\s+"
    rf"(?:[a-z]+\s+){{0,2}}?(?P<role>{_ROLE})\b"
)
_NEW_AGENT = re.compile(r";|\s+e\s+(?:o|a|os|as)\s+")
_RELATIVE_AGENT = re.compile(r",\s*que\s+$")


def _family(verb: str) -> str:
    return "protocol" if verb.startswith("protocol") else "addressed"


def _canonical(role: str) -> str:
    return re.sub(r"(?:es|s)$", "", role)


def _routes(document: str) -> dict[str, set[str]]:
    routes = {"protocol": set(), "addressed": set()}
    for start, end in _sentences(document):
        sentence = document[start:end]
        verbs = list(_ROUTED.finditer(sentence))
        for index, match in enumerate(verbs):
            stop = verbs[index + 1].start() if index + 1 < len(verbs) else len(sentence)
            for segment in sentence[match.end() : stop].split(","):
                named = _ROLE_NAMED.findall(segment)
                if named:
                    routes[_family(match["verb"])] |= {_canonical(role) for role in named}
                    break
    return routes


def _deciders(document: str) -> set[str]:
    result = set()
    for start, end in _sentences(document):
        sentence = document[start:end]
        result |= {_canonical(m["role"]) for m in _PASSIVE_DECISION.finditer(sentence)}
        for verb in re.finditer(rf"\b(?:{_DECISION})", sentence):
            before = sentence[: verb.start()]
            relative = _RELATIVE_AGENT.search(before)
            named_before = _ROLE_NAMED.findall(before[: relative.start()]) if relative else []
            if named_before:
                # "ao professor, que julga": the relative clause's agent is the nearest role.
                result.add(_canonical(named_before[-1]))
                continue
            before = _NEW_AGENT.split(before)[-1]
            result |= {_canonical(role) for role in _ROLE_NAMED.findall(before)}
    return result


def procedure_role_mismatches(raw: str, evidence: dict) -> list[RelationMismatch]:
    """Addressee, filing place and deciding authority are distinct relations, not synonyms."""
    routes = {"protocol": set(), "addressed": set()}
    deciders = set()
    for content in evidence.values():
        document = fold(content)
        found = _routes(document)
        routes["protocol"] |= found["protocol"]
        routes["addressed"] |= found["addressed"]
        deciders |= _deciders(document)
    text = fold(raw)
    result = []
    for match in _CLAIM_ROUTE.finditer(text):
        if _canonical(match["role"]) not in routes[_family(match["verb"])]:
            result.append(RelationMismatch(match.start(), match.end(), match["role"]))
    for match in _CLAIM_DECISION.finditer(text):
        negated = re.search(r"\bnao\b", match["gap"])
        if not negated and _canonical(match["role"]) not in deciders:
            result.append(RelationMismatch(match.start(), match.end(), match["role"]))
    for match in _PASSIVE_DECISION.finditer(text):
        if not _negated_before(text, match.start()) and _canonical(match["role"]) not in deciders:
            result.append(RelationMismatch(match.start(), match.end(), match["role"]))
    return result


_CONSEQUENCE = (
    r"nota\s+(?:0|zero)|perd\w+\s+(?:o|do|seu|esse)\s+direito|indeferid\w+|reprovad\w+|cancelad\w+"
)
_CONSEQUENCE_NAMED = re.compile(rf"\b(?:{_CONSEQUENCE})\b")
_DEADLINE_CONDITION = re.compile(
    r"\b(?:caso|se|quem|quando|ao\s+perder|perdendo|perder|perda\s+d[oe]|descumpri\w+)\b"
    r"[^.\n]*\bprazo\b(?P<between>[^.\n]*?)"
    rf"\b(?P<effect>{_CONSEQUENCE})\b"
)


def _effect_kind(effect: str) -> str:
    return re.split(r"\s+", effect)[0][:6]


def _negated_before(text: str, position: int) -> bool:
    return bool(re.search(r"\bnao\b(?:\s+[a-z]+){0,3}\s*$", text[max(0, position - 40) : position]))


def unsupported_consequences(raw: str, evidence: dict) -> list[RelationMismatch]:
    """Missing a deadline leads to a sanction only where a provision ties the two together."""
    linked = set()
    for content in evidence.values():
        document = fold(content)
        for start, end in _sentences(document):
            sentence = document[start:end]
            if "prazo" in sentence:
                linked |= {
                    _effect_kind(m[0])
                    for m in _CONSEQUENCE_NAMED.finditer(sentence)
                    if not _negated_before(sentence, m.start())
                }
    text = fold(raw)
    result = []
    for start, end in _sentences(text):
        sentence = text[start:end]
        for match in _DEADLINE_CONDITION.finditer(sentence):
            if _negated_before(sentence, match.start("effect")):
                continue
            if _effect_kind(match["effect"]) not in linked:
                result.append(
                    RelationMismatch(
                        start + match.start("effect"), start + match.end("effect"), match["effect"]
                    )
                )
    return result


_CONCLUDING = r"\b(?:portanto|assim|logo|dessa\s+forma|desse\s+modo)\b[^.\n]*"
_UNIVERSAL = re.compile(
    r"\b(?:independentemente\s+d\w+|em\s+qualquer\s+(?:caso|hipotese|situacao)"
    r"|em\s+todos\s+os\s+casos|sem\s+excecao|seja\s+qual\s+for|qualquer\s+que\s+seja)\b"
)


_EXTENSION = re.compile(r"\bo\s+que\s+(?:inclui|abrange|engloba)\s+(?:os|as|todos|todas)\b")


def _universal_form(phrase: str) -> str:
    # "independentemente de" and "independentemente do" are the same scope marker.
    return re.sub(r"^(independentemente)\s+d\w+$", r"\1", re.sub(r"\s+", " ", phrase))


def unsupported_generalizations(raw: str, evidence: dict, question: str) -> list[RelationMismatch]:
    """A concluding universal scope, or a category extension, must be stated by a provision.

    Only explicit markers are read. A generalization written without one is left to
    `dropped_scope_conditions`, which covers a closed list of categories.
    """
    sources = " ".join(fold(content) for content in [*evidence.values(), question])
    stated = {_universal_form(match[0]) for match in _UNIVERSAL.finditer(sources)}
    text = fold(raw)
    result = []
    for start, end in _sentences(text):
        sentence = text[start:end]
        if not re.search(_CONCLUDING, sentence):
            continue
        for match in _UNIVERSAL.finditer(sentence):
            if _universal_form(match[0]) not in stated:
                result.append(
                    RelationMismatch(start + match.start(), start + match.end(), match[0])
                )
    for match in _EXTENSION.finditer(text):
        if match[0] not in sources:
            result.append(RelationMismatch(match.start(), match.end(), match[0]))
    return result


_INFERENCE = re.compile(
    r"\b(?:isso|o\s+que)\s+(?:indica|implica|sugere)\s+que\b"
    r"|\b(?:presume-se|supoe-se|depreende-se)\b|\bno\s+seu\s+caso\b|\bna\s+sua\s+situacao\b"
)
_NORMATIVE_LIMIT = re.compile(
    r"\b(?:minim\w*|maxim\w*|exig\w*|previst\w*|requisit\w*)\b(?:\s+[a-z]+){0,3}\s*$"
)
_DONE = r"(?:fiz|fez|realiz\w+|feit\w+)"
_ASSESSMENT = r"(?:exame|prova|avaliacao)"
_DONE_ON_IT = rf"\b{_DONE}\b[^,.;]*\b{_ASSESSMENT}\b|\b{_ASSESSMENT}\b[^,.;]*\b{_DONE}\b"
_NOT_DONE_ON_IT = (
    rf"\bnao\s+(?:foi\s+)?{_DONE}\b[^,.;]*\b{_ASSESSMENT}\b"
    rf"|\b{_ASSESSMENT}\b[^,.;]*\bnao\s+(?:foi\s+)?{_DONE}\b"
)
# A status counts as given only for the same object: having done the enrollment says nothing
# about the exam. Objects outside these forms are not read.
_USER_STATUS = (
    (re.compile(rf"\b{_ASSESSMENT}(?:\s+final)?\s+ainda\s+nao\s+foi\s+(?:realizad|aplicad|feit)\w*"),
     _NOT_DONE_ON_IT, None),
    (re.compile(rf"\b{_ASSESSMENT}(?:\s+final)?\s+ja\s+foi\s+(?:realizad|aplicad|feit)\w*"
                rf"|\bvoce\s+(?:ja\s+)?(?:realizou|fez)\s+(?:o|a)\s+{_ASSESSMENT}\b"),
     _DONE_ON_IT, _NOT_DONE_ON_IT),
    (re.compile(r"\bvoce\s+(?:ja\s+)?(?:cumpriu|satisfaz|satisfez|atende|atendeu)\s+(?:[oa]s?\s+)?(?P<object>[a-z]+)"),
     r"\b(?:cumpri\w*|satisf\w+|atend\w+)\b", r"\bnao\s+(?:cumpri\w*|satisf\w+|atend\w+)\b"),
    (re.compile(r"\bvoce\s+foi\s+aprovad\w*(?:\s+(?:no|na|em)\s+(?P<object>[a-z]+))?"),
     r"\baprovad\w*", r"\bnao\s+(?:fui\s+)?aprovad\w*"),
    (re.compile(r"\bvoce\s+foi\s+reprovad\w*(?:\s+(?:no|na|em)\s+(?P<object>[a-z]+))?"),
     r"\breprovad\w*", r"\bnao\s+(?:fui\s+)?reprovad\w*"),
)  # fmt: skip
_CONDITION = re.compile(r"\b(?:se|caso|quando|desde\s+que)\b")


def _stated_by_user(question: str) -> str:
    """What the user states: an asked clause is not a fact the user gave."""
    kept = []
    for part in re.findall(r"[^.!?\n]+[.!?\n]?", fold(question)):
        if part.rstrip().endswith("?"):
            part = part.rpartition(",")[0]
        kept.append(part)
    return " ".join(kept)


_USER_ATTRIBUTE = re.compile(
    r"\b(?P<name>sua|seu)\s+(?P<attribute>(?:media|nota)\s+(?:final|parcial))\b"
)


def _inferred_values(segment: str) -> set[str]:
    values = set()
    for match in _ANY_DIGITS.finditer(segment):
        if not _NORMATIVE_LIMIT.search(segment[: match.start()]):
            values.add(_digits(match[0]))
    for match in _ANY_WORDS.finditer(segment):
        if not _NORMATIVE_LIMIT.search(segment[: match.start()]):
            values.add(str({**_UNITS, **_TENS}[match[1]]))
    return values


def inferred_user_facts(raw: str, question: str) -> list[RelationMismatch]:
    """A value about the user's situation must come from the user, not from an inference.

    A normative limit named next to the value is not a fact about the user. Status is read from a
    closed list of forms; other presumptions are not detected here.
    """
    known = _known_values(question)
    asked = fold(question)
    stated = _stated_by_user(question)
    text = fold(raw)
    result = []
    for start, end in _sentences(text):
        sentence = text[start:end]
        for marker in _INFERENCE.finditer(sentence):
            if _inferred_values(sentence[marker.end() :]) - known:
                result.append(
                    RelationMismatch(start + marker.start(), start + marker.end(), "value")
                )
        for pattern, given, denied in _USER_STATUS:
            for status in pattern.finditer(sentence):
                clause = re.split(r"[,;:]", sentence[: status.start()])[-1]
                authorized = re.search(given, stated) and not (denied and re.search(denied, stated))
                named = status.groupdict().get("object")
                if authorized and named and named[:6] not in stated:
                    authorized = None
                if not _CONDITION.search(clause) and not authorized:
                    result.append(
                        RelationMismatch(start + status.start(), start + status.end(), "status")
                    )
        for attribute in _USER_ATTRIBUTE.finditer(sentence):
            conditional = re.search(r"\bse\s+$", sentence[: attribute.start()])
            kind = attribute["attribute"].split()[-1]
            if not conditional and not re.search(rf"\b(?:media|nota)\s+{kind}\b", asked):
                result.append(
                    RelationMismatch(
                        start + attribute.start(), start + attribute.end(), "attribute"
                    )
                )
    return result


_NEGATIVE = re.compile(r"\bnao\s+(?:se\s+)?(?:tem|tera|possui|ha|assiste)\s+(?:o\s+)?direito\b"
                       r"|\bsem\s+direito\b"
                       r"|\bnao\s+(?:pode|podera|e\s+possivel|e\s+permitid\w+)\b")  # fmt: skip
_POSITIVE = re.compile(r"\b(?:tem|tera|possui|ha|assiste)\s+(?:o\s+)?direito\b"
                       r"|\b(?:pode|podera|e\s+possivel|e\s+permitid\w+)\b")  # fmt: skip
_APPLIED = re.compile(rf"{_CONCLUDING}|\bvoce\b|\bseu\s+caso\b|\bnessa\s+situacao\b")
_RIGHT = re.compile(r"\bdireito\b")


def _polarity_of(sentence: str, *, right_only: bool) -> str | None:
    negatives = [m[0] for m in _NEGATIVE.finditer(sentence)]
    positives = [m[0] for m in _POSITIVE.finditer(sentence)]
    if right_only:
        negatives = [m for m in negatives if _RIGHT.search(m)]
        positives = [m for m in positives if _RIGHT.search(m)]
    if negatives:
        return "negative"
    return "positive" if positives else None


def conclusion_polarity(raw: str) -> str | None:
    """Reads a closed set of deciding forms; a descriptive answer has no polarity.

    A statement about the right decides before a modal, which often only offers a next step.
    A sentence applying the rule to the asker decides before one that only restates the rule.
    """
    text = fold(raw)
    sentences = [text[start:end] for start, end in reversed(_sentences(text))]
    applied = [sentence for sentence in sentences if _APPLIED.search(sentence)]
    for group, right_only in ((applied, True), (sentences, True), (applied, False)):
        for sentence in group:
            polarity = _polarity_of(sentence, right_only=right_only)
            if polarity:
                return polarity
    lead = re.match(r"\W*(sim|nao)\b", text)
    return {"sim": "positive", "nao": "negative"}[lead[1]] if lead else None


def inverted_conclusion(first: str, second: str) -> bool:
    before, after = conclusion_polarity(first), conclusion_polarity(second)
    return before is not None and after is not None and before != after


@dataclass(frozen=True)
class ScopeCondition:
    """A category a provision itself names, read from the evidence and not from a case list."""

    norm: str
    article: str
    noun: str
    qualifier: str
    rule_terms: frozenset[str]
    preposition: str = ""


_SCOPE = re.compile(
    r"(?:\b(?P<preposition>de|em|para)\s+)?\b(?P<noun>cursos?)\s+(?P<qualifier>concluid\w+)\b"
    r"|\b(?P<noun2>alunos?|discentes?)\s+(?P<qualifier2>transferid\w+)\b"
)
_NOT_COVERED = re.compile(
    r"\bnao\s+(?:tratam?|cobrem?|abrangem?|se\s+aplicam?|estabelecem?|dispoem?|preveem?|preve)\b"
    r"|\btrata\s+(?:so|somente|apenas)\b"
)
MIN_RULE_TERMS = 3


def scope_conditions(evidence: dict) -> list[ScopeCondition]:
    result = []
    for (norm, article), content in evidence.items():
        document = fold(content)
        for start, end in _sentences(document):
            sentence = document[start:end]
            for match in _SCOPE.finditer(sentence):
                noun = match["noun"] or match["noun2"]
                qualifier = match["qualifier"] or match["qualifier2"]
                rule = set(terms(sentence)) - _BOILERPLATE - set(terms(f"{noun} {qualifier}"))
                result.append(
                    ScopeCondition(
                        norm, article, noun, qualifier, frozenset(rule), match["preposition"] or ""
                    )
                )
    return result


def scope_instruction(conditions: list[ScopeCondition]) -> str:
    if not conditions:
        return ""
    lines = "".join(
        f"\n- {c.norm}, art. {c.article}: a regra se refere a {c.noun} {c.qualifier}."
        for c in conditions
    )
    return (
        "\nCONDIÇÕES DE APLICAÇÃO NOS TRECHOS:"
        + lines
        + "\nAo usar essas regras, mantenha a condição por escrito. Se o caso perguntado não "
        "atender à condição, ou se ela não tiver sido informada, diga o que esse artigo cobre e que "
        "ele não trata dos demais casos, sem aplicar a regra a eles.\n"
    )


def dropped_scope_conditions(raw: str, evidence: dict) -> list[RelationMismatch]:
    """A rule the provision limits to a category cannot be stated without that category.

    Bounded to a closed list of categories and to sentences sharing the provision's own terms.
    It does not establish that the rule was applied correctly when the category is written.
    """
    text = fold(raw)
    result = []
    for condition in scope_conditions(evidence):
        singular = condition.noun.rstrip("s")
        # The same relation as the provision: "de cursos concluídos" names where the credit came
        # from; "aproveitados em curso da UFPI" names where it went, and is another rule.
        lead = rf"\b{condition.preposition}\s+(?:[a-z]+\s+)?" if condition.preposition else r"\b"
        noun = re.compile(rf"{lead}{singular}s?\b")
        any_noun = re.compile(rf"\b{singular}s?\b")
        stem = condition.qualifier[:6]
        for start, end in _sentences(text):
            sentence = text[start:end]
            # "curso de graduação" names the level of study, not the category being limited.
            without_level = re.sub(r"\bcursos?\s+de\s+graduacao\b", " ", sentence)
            negated = re.search(rf"\bnao\s+(?:foi\s+|tenha\s+)?{stem}", sentence)
            if not noun.search(without_level) and not (negated and any_noun.search(without_level)):
                continue
            shared = (set(terms(sentence)) - _BOILERPLATE) & condition.rule_terms
            if len(shared) < MIN_RULE_TERMS or _NOT_COVERED.search(sentence):
                continue
            if stem not in sentence or negated:
                result.append(
                    RelationMismatch(start, end, f"{condition.noun} {condition.qualifier}")
                )
    return result


_QUALIFIED_INSTRUMENT = re.compile(
    r"\b(?P<head>regimento\s+interno|projeto\s+pedagogico|calendario\s+academico)"
    r"(?:\s+d[oa]s?\s+(?:ppgs?|programas?|cursos?))?\s+de\s+(?P<first>origem|destino|ambos)"
    r"(?:\s+e\s+(?P<second>origem|destino))?\b"
)


def unsupported_qualifiers(raw: str, evidence: dict) -> list[RelationMismatch]:
    """A qualifier added to a named instrument must be written next to it in the evidence."""
    documents = [fold(content) for content in evidence.values()]
    result = []
    for match in _QUALIFIED_INSTRUMENT.finditer(fold(raw)):
        head = re.sub(r"\s+", r"\\s+", match["head"])
        words = [word for word in (match["first"], match["second"]) if word]
        if not all(
            any(re.search(rf"\b{head}\b[^.\n]{{0,40}}\b{word}\b", doc) for doc in documents)
            for word in words
        ):
            result.append(RelationMismatch(match.start(), match.end(), " ".join(words)))
    return result
