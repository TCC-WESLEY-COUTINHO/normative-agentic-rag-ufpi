"""Deterministic presentation and bounded Portuguese output checks.

The guard covers enumerated locator/chronology/status forms, not legal correctness
or arbitrary paraphrases. It reports spans and never rewrites provider content.
No dates can be inferred from a normative identifier or a relation's proof locator.
"""

import re
import unicodedata

from rag_baseline.content_locators import (
    associated_norm,
    locator_mentions,
    matching_permissions,
    norm_id,
)
from rag_baseline.evidence_support import (
    absence_claims,
    citation_mismatches,
    deadline_mismatches,
    denied_amendments,
    dropped_scope_conditions,
    inferred_user_facts,
    procedure_role_mismatches,
    unsupported_consequences,
    unsupported_generalizations,
    unsupported_numbers,
    unsupported_qualifiers,
)
from rag_baseline.grounding import TemporalGroundingContext
from rag_baseline.models import RetrievedChunk
from rag_baseline.output_contracts import (
    AllowedContentLocator,
    AllowedTemporalFacts,
    GuardViolation,
    NormativeReference,
    TemporalFact,
)

FALLBACK_BODY = (
    "Não foi possível formular a resposta com segurança a partir das evidências disponíveis."
)
BODY_SYSTEM_INSTRUCTION = (
    "\nProduza somente answer_body: explique o conteúdo substantivo em linguagem natural. "
    "A aplicação acrescentará status temporal e fontes oficiais separadamente. "
    "Não inclua seções finais Fontes, Referências ou Sources, nem listas bibliográficas. "
    "As referências são entregues em campo tipado. No corpo, use somente locators de conteúdo explicitamente autorizados; "
    "a permissão de conteúdo não altera as referências oficiais nem autoriza claims substantivos; "
    "nomes de normas podem ser mencionados. Não repita o status temporal fornecido. "
    "Não decida vigência, revogação, alteração ou datas; não infira publicação ou eficácia "
    "a partir do ano de um identificador. Para consulta histórica, explique a redação "
    "histórica disponível; para comparação, separe os conteúdos."
)


def norm_name(norm_id: str) -> str:
    match = re.fullmatch(r"ufpi-(\d+)-(\d{4})", norm_id)
    return f"Resolução {match[1]}/{match[2]}" if match else norm_id


def normative_references(
    chunks: list[RetrievedChunk], grounding: TemporalGroundingContext
) -> list[NormativeReference]:
    """Sort rank/id; equivalent norm/article/role displays retain the lowest rank/id.

    Validate membership and article identity against final grounding. Relations are
    internal provenance, never an independent source of displayed references.
    Current grounding validates articles only, so subdivisions stay unvalidated.
    """
    states = {e.chunk_id: e for e in grounding.evidence_states}
    if set(states) != {c.id for c in chunks}:
        raise ValueError("References exigem exatamente a evidência final elegível.")
    result, seen = [], set()
    for chunk in sorted(chunks, key=lambda c: (c.rank, c.id)):
        state = states[chunk.id]
        if state.source_article != chunk.article_number or (
            chunk.norm_id is not None and state.source_norm != chunk.norm_id
        ):
            raise ValueError("Reference difere da identidade da evidência final.")
        article = (
            state.source_article
            if grounding.generation_constraints.citation_granularity_ceiling == "article"
            else None
        )
        key = (state.source_norm, article, state.temporal_role)
        if key in seen:
            continue
        seen.add(key)
        display = norm_name(state.source_norm) + (f", art. {article}" if article else "")
        result.append(
            NormativeReference(
                chunk_id=chunk.id,
                norm_id=state.source_norm,
                source=chunk.source,
                article=article,
                display_text=display,
                temporal_role=state.temporal_role,
                evidence_text=chunk.content,
            )
        )
    return result


def allowed_temporal_facts(grounding: TemporalGroundingContext) -> AllowedTemporalFacts:
    facts = []
    if grounding.temporal_intent == "historical":
        facts.append(TemporalFact(kind="HISTORICAL_CONTEXT"))
    elif grounding.temporal_intent == "current":
        facts.append(TemporalFact(kind="CURRENT_CONTEXT"))
    for relation in grounding.known_relations:
        facts.append(
            TemporalFact(
                kind=relation.relation,
                norm_id=relation.source_norm,
                target_norm=relation.target_norm,
            )
        )
    for state in grounding.evidence_states:
        if state.normative_status == "desconhecida":
            facts.append(TemporalFact(kind="STATUS_UNKNOWN", norm_id=state.source_norm))
        if grounding.temporal_intent == "comparison":
            facts.append(
                TemporalFact(
                    kind="COMPARISON_ROLE", norm_id=state.source_norm, role=state.temporal_role
                )
            )
    # Structural equivalence only; no textual deduplication of generated answers.
    return AllowedTemporalFacts(items=list(dict.fromkeys(facts)))


def render_temporal_statements(facts: AllowedTemporalFacts) -> str:
    lines = []
    for fact in facts.items:
        name = norm_name(fact.norm_id) if fact.norm_id else ""
        target = norm_name(fact.target_norm) if fact.target_norm else ""
        if fact.kind == "HISTORICAL_CONTEXT":
            lines.append(
                "Esta resposta considera a redação histórica solicitada e não certifica sua vigência atual."
            )
        elif fact.kind == "CURRENT_CONTEXT":
            lines.append(
                "Esta resposta considera o contexto selecionado para a consulta atual; essa seleção não certifica vigência."
            )
        elif fact.kind == "REVOKED_BY":
            lines.append(
                f"A relação normativa registrada indica que {name} foi revogada por {target}."
            )
        elif fact.kind == "AMENDED_BY":
            lines.append(
                f"O dispositivo consultado de {name} possui alteração parcial registrada por {target}; isso não representa revogação total da norma-base."
            )
        elif fact.kind == "STATUS_UNKNOWN":
            lines.append(
                f"Para {name}, o conjunto documental utilizado não permite certificar a vigência atual."
            )
        elif fact.kind == "COMPARISON_ROLE":
            role = {"historical": "histórico", "posterior": "posterior", "eligible": "elegível"}[
                fact.role
            ]
            lines.append(f"Papel {role}: {name}.")
    return "\n".join(lines)


def compose_answer(status: str, body: str, references: list[NormativeReference]) -> str:
    """Compose response text; references are delivered separately in the typed output."""
    return "\n\n".join(part for part in (status, body) if part)


def present_temporal_scope(facts: AllowedTemporalFacts, grounding: TemporalGroundingContext) -> str:
    """Present indexed-corpus scope without promoting unknown status to validity."""
    if grounding.temporal_intent in {"validity", "historical", "comparison"}:
        return render_temporal_statements(facts)
    relations = AllowedTemporalFacts(
        items=[fact for fact in facts.items if fact.kind in {"REVOKED_BY", "AMENDED_BY"}]
    )
    return "\n".join(
        part
        for part in (
            "Com base nas normas indexadas no sistema:",
            render_temporal_statements(relations),
        )
        if part
    )


def _fold(text: str) -> str:
    # Accented Portuguese characters keep one position, preserving audit offsets.
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c)
    )


NORM = re.compile(r"\b(\d+(?:\.\d{3})*)\s*/\s*(\d{4})\b")
ARTICLE = re.compile(r"\b(?:art(?:igo)?s?)\.?\s*(\d+[º°o]?(?:\s*(?:,|e)\s*\d+[º°o]?)*)", re.I)
SUBDIVISION = re.compile(
    r"§+\s*\d+[º°o]?|\bparagrafo\s+(?:unico|\d+[º°o]?)|"
    r"\bincisos?\s+[ivxlcdm\d]+\b|\balineas?\s+[\"'‘’“”]?[a-z]\b|"
    r"\bart(?:igo)?\.?\s*\d+[º°o]?\s*,\s*[ivxlcdm]+\b",
    re.I,
)
TEMPORAL_PATTERNS = {
    "unsupported_publication": (
        r"\bpublicad[ao]s?\s+(?:em|no dia|aos|na data)\b|"
        r"\b(?:norma|resolucao|ato)(?:\s+(?:n[.º°o]*\s*)?\d+(?:\.\d{3})*/\d{4})?"
        r"\s+(?:(?:foi|e|esta|sera)\s+)?publicad[ao]\b"
    ),
    "unsupported_effectivity": (
        r"\b(?:entrou|entra|entrara|entraram|entraria)\s+em\s+vigor\b|"
        r"\bem vigor\s+(?:na data|desde|a partir)\b|"
        r"\b(?:vigora|vigorou|vigente)\s+(?:desde|a partir)\b|"
        r"\b(?:passou|passa|passaram)\s+a\s+vigorar\b|"
        r"\b(?:produz|produzem|produziu)\s+efeitos\s+(?:desde|a partir)\b|"
        r"\befeitos?\s+imediatos?\b|"
        r"\ba partir da\s+vigencia\b|\bentrada\s+em\s+vigor\b|"
        r"\bna data de\s+(?:sua\s+)?publicacao\b"
    ),
    "unsupported_retroactivity": r"\bretroativ\w*\b",
    "unsupported_chronology": (
        r"\b(?:a partir de|desde)\s+(?:\d{1,2}\s+de\s+\w+\s+de\s+)?\d{4}\b|"
        r"\b(?:apos|ate|desde)\s+(?:a\s+)?(?:publicacao\s+(?:da|do)\s+(?:resolucao|norma|ato)|"
        r"entrada\s+em\s+vigor)\b"
    ),
}
CURRENT = re.compile(
    r"\b(?:esta|permanece|continua|encontra-se|e)\s+(?:atualmente\s+)?(?:em vigor|vigente)\b|"
    r"\b(?:redacao|norma|resolucao|regra)\s+(?:atualmente\s+)?vigente\b|"
    r"\btem\s+vigencia\s+atual\b"
)


def _negated(text: str, start: int) -> bool:
    # Bounded clause-local negative forms, not a general scope/negation parser.
    prefix = re.split(r"[.!?;,\n]|\bmas\b", text[max(0, start - 100) : start])[-1]
    return bool(
        re.search(
            r"\b(?:nao|nunca)(?:\s+(?:foi|esta|e|sera|foram|sao))?\s*$|"
            r"\b(?:nao (?:e possivel|foi possivel|se pode|permite|certifica|confirma|afirma|informa|comprova)|"
            r"sem (?:evidencia|comprovacao|informacao)|nao ha (?:evidencia|comprovacao|informacao|certeza)|"
            r"nao ha elementos suficientes para (?:confirmar|certificar|afirmar|concluir))\b.{0,90}$",
            prefix,
        )
    )


BIBLIOGRAPHY_HEADING = re.compile(
    r"^[ \t]*(?:\#{1,6}[ \t]+)?(?:\*\*|__)?"
    r"(?:fontes|referencias|sources|bibliografia)(?:[ \t]+(?:normativas|bibliograficas|oficiais))?"
    r"(?:[ \t]+(?:consultadas|utilizadas|consulted|used))?"
    r"(?:\*\*|__)?[ \t]*:?[ \t]*(?:\*\*|__)?[ \t]*\r?\n",
    re.MULTILINE,
)
BIBLIOGRAPHY_ITEM = re.compile(r"[ \t]*(?:[-*+•]|\d+[.)])[ \t]+\S[^\r\n]*")


def _bibliography_tail(text: str) -> bool:
    """Require a terminal list, allowing only blank lines and indented continuations."""
    seen_item = False
    for line in text.splitlines():
        if not line.strip():
            continue
        if BIBLIOGRAPHY_ITEM.fullmatch(line):
            seen_item = True
        elif seen_item and line.startswith(("  ", "\t")):
            continue
        else:
            return False
    return seen_item


class NormativeOutputGuard:
    def check(
        self,
        raw: str,
        references: list[NormativeReference],
        facts: AllowedTemporalFacts,
        grounding: TemporalGroundingContext,
        *,
        allowed_content_locators: list[AllowedContentLocator] | None = None,
        evidence: dict | None = None,
        question: str = "",
    ) -> list[GuardViolation]:
        text = _fold(raw)
        violations = []

        def add(code, match):
            violations.append(
                GuardViolation(
                    code=code,
                    start=match.start(),
                    end=match.end(),
                    excerpt=raw[match.start() : match.end()],
                )
            )

        for match in BIBLIOGRAPHY_HEADING.finditer(text):
            if _bibliography_tail(text[match.end() :]):
                add("terminal_bibliography", match)

        known_norms = {r.norm_id for r in references}
        for fact in facts.items:
            known_norms.update(n for n in (fact.norm_id, fact.target_norm) if n)
        norm_matches = list(NORM.finditer(text))
        for match in norm_matches:
            if f"ufpi-{match[1].replace('.', '')}-{match[2]}" not in known_norms:
                add("unallowed_norm", match)
        for match in ARTICLE.finditer(text):
            # Associate an explicit norm within the same short clause when present.
            nearby = [
                n
                for n in norm_matches
                if abs(n.start() - match.start()) < 80
                and not re.search(
                    r"[;\n]", text[min(n.end(), match.end()) : max(n.start(), match.start())]
                )
            ]
            norms = {f"ufpi-{n[1].replace('.', '')}-{n[2]}" for n in nearby}
            articles = re.findall(r"\d+", match[1])
            if allowed_content_locators is not None:
                explicit_norm = associated_norm(text, match, norm_matches)
                candidates = allowed_content_locators
                invalid = any(
                    not any(
                        locator.article == article
                        and (explicit_norm is None or locator.norm_id == norm_id(explicit_norm))
                        for locator in candidates
                    )
                    for article in articles
                )
            else:
                invalid = any(
                    not any(
                        r.article == article and (not norms or r.norm_id in norms)
                        for r in references
                    )
                    for article in articles
                )
            if invalid:
                add("unallowed_article", match)
        for mention in locator_mentions(raw):
            if not matching_permissions(mention, allowed_content_locators or []):
                violations.append(
                    GuardViolation(
                        code="unvalidated_subdivision",
                        start=mention.start,
                        end=mention.end,
                        excerpt=raw[mention.start : mention.end],
                    )
                )
        for code, pattern in TEMPORAL_PATTERNS.items():
            for match in re.finditer(pattern, text):
                if not _negated(text, match.start()):
                    add(code, match)
        if grounding.requested_time_context.get("historical_wording"):
            # A documentary text does not establish legal applicability in the
            # past either. Keep this stricter check scoped to wording requests.
            for match in re.finditer(
                r"\b(?:vigentes?|em vigor|valid[oa]s?|aplicave(?:l|is)|"
                r"vigorava(?:m)?|vigorou|valia(?:m)?|valeu|aplicava(?:m)?(?:-se)?)\b",
                text,
            ):
                if not _negated(text, match.start()):
                    add("unsupported_historical_validity", match)
        constraints = grounding.generation_constraints
        if (
            constraints.must_not_claim_current_validity
            or constraints.must_not_claim_unknown_as_current
            or constraints.must_not_present_revoked_rule_as_current
        ):
            for match in CURRENT.finditer(text):
                # A nominal "regra vigente ... estabelecia" may describe a
                # historical evidence role; direct "está vigente" stays blocked.
                suffix = re.split(r"[;!?\n]|\.(?=\s+[a-z])", text[match.end() : match.end() + 160])[
                    0
                ]
                source = NORM.search(suffix)
                if (
                    match[0].startswith(("regra", "redacao"))
                    and grounding.temporal_intent in {"historical", "comparison"}
                    and re.search(r"\b(?:estabelecia|previa|disciplinava)\b", suffix)
                    and source
                    and any(
                        e.source_norm == norm_id(source) and e.temporal_role == "historical"
                        for e in grounding.evidence_states
                    )
                ):
                    continue
                if not _negated(text, match.start()):
                    add("unsupported_current_validity", match)
        # Explicit relation forms observed in the corpus, with direction validation.
        relation_pattern = r"(\d+)\s*/\s*(\d{4})[^.!?;\n]{0,40}?\b(?:foi\s+)?(revogad[ao]|substituid[ao]|alterad[ao])\s+(?:por|pela|pelo)\s+(?:resolucao\s+)?(?:n[.º°o]*\s*)?(\d+)\s*/\s*(\d{4})"
        for match in re.finditer(relation_pattern, text):
            source, target = f"ufpi-{match[1]}-{match[2]}", f"ufpi-{match[4]}-{match[5]}"
            kind = "AMENDED_BY" if match[3].startswith("alterad") else "REVOKED_BY"
            if not _negated(text, match.start(3)) and not any(
                f.kind == kind and f.norm_id == source and f.target_norm == target
                for f in facts.items
            ):
                add("contradictory_relation", match)
        # A bare total-repeal assertion must also have a recorded REVOKED_BY.
        for match in re.finditer(
            r"(\d+)\s*/\s*(\d{4})[^.!?;\n]{0,40}?\b(revogad[ao]|substituid[ao])\b", text
        ):
            source = f"ufpi-{match[1]}-{match[2]}"
            if not _negated(text, match.start(3)) and not any(
                f.kind == "REVOKED_BY" and f.norm_id == source for f in facts.items
            ):
                add("contradictory_relation", match)

        def span(code, start, end):
            violations.append(
                GuardViolation(code=code, start=start, end=end, excerpt=raw[start:end])
            )

        for start, end in denied_amendments(raw, grounding.known_relations):
            span("contradictory_relation", start, end)
        if evidence:
            related = set()
            for relation in grounding.known_relations:
                related.add((relation.source_norm, relation.target_article))
                evidence_article = re.match(r"\s*(\d+)", relation.evidence_article or "")
                if evidence_article:
                    related.add((relation.target_norm, evidence_article[1]))
            for mismatch in citation_mismatches(raw, evidence, related=related):
                span("citation_content_mismatch", mismatch.start, mismatch.end)
            for claim in absence_claims(raw):
                span("absence_claim", claim.start, claim.end)
            for number in unsupported_numbers(raw, evidence, question):
                span("unsupported_number", number.start, number.end)
            for item in deadline_mismatches(raw, evidence):
                span("deadline_mismatch", item.start, item.end)
            for item in procedure_role_mismatches(raw, evidence):
                span("procedure_role_mismatch", item.start, item.end)
            for item in unsupported_consequences(raw, evidence):
                span("unsupported_consequence", item.start, item.end)
            for item in unsupported_generalizations(raw, evidence, question):
                span("unsupported_generalization", item.start, item.end)
            for item in inferred_user_facts(raw, question):
                span("inferred_user_fact", item.start, item.end)
            for item in dropped_scope_conditions(raw, evidence):
                span("dropped_scope_condition", item.start, item.end)
            for item in unsupported_qualifiers(raw, evidence):
                span("unsupported_qualifier", item.start, item.end)
        return sorted(violations, key=lambda v: (v.start, v.end, v.code))


def _subdivision_label(locator):
    kind = {"paragraph": "§", "inciso": "inciso", "alinea": "alínea", "caput": "caput"}[
        locator.subdivision_type
    ]
    if locator.subdivision_type == "caput":
        return kind
    if locator.subdivision_value == "unico":
        return "parágrafo único"
    return f"{kind} {locator.subdivision_value}"


def body_instructions(references, facts, status, content_locators=()):
    forms = []
    evidence_levels = {}
    explicit_locators = []
    for locator in content_locators:
        if locator.source == "validated_evidence" and locator.subdivision_type:
            evidence_levels.setdefault((locator.norm_id, locator.article), []).append(locator)
            continue
        explicit_locators.append(locator)
        label = norm_name(locator.norm_id) + f", art. {locator.article}"
        if locator.subdivision_type:
            kind = {
                "paragraph": "parágrafo",
                "inciso": "inciso",
                "alinea": "alínea",
                "caput": "caput",
            }[locator.subdivision_type]
            label += f", {kind} {locator.subdivision_value}"
        if label not in forms:
            forms.append(label)
    return (
        "\n[STRUCTURED OUTPUT]\n"
        + "REFERÊNCIAS PERMITIDAS: "
        + "\n".join(r.display_text for r in references)
        + "\nFATOS TEMPORAIS PERMITIDOS: "
        + facts.model_dump_json()
        + "\nLOCATORS DE CONTEÚDO (não são fontes oficiais adicionais): "
        + str([locator.model_dump() for locator in explicit_locators])
        + "\nFORMAS DE CITAÇÃO AUTORIZADAS:\n"
        + "\n".join(forms)
        + "".join(
            f"\n{norm_name(norm)}, art. {article}: "
            + ", ".join(_subdivision_label(locator) for locator in levels)
            for (norm, article), levels in evidence_levels.items()
            if any(locator.subdivision_type != "caput" for locator in levels)
        )
        + "\nNão copie subdivisões do texto da evidência para as citações se não estiverem "
        "nas formas autorizadas acima. Um locator de artigo com subdivision_type=null "
        "autoriza somente a citação do artigo, sem inciso, parágrafo, alínea ou caput. "
        "A regra substantiva pode ser explicada com base no trecho completo, "
        "sem acrescentar um locator de subdivisão não autorizado."
        + (
            "\nGRANULARIDADE DESTA RESPOSTA: somente artigo. "
            "Não escreva §, parágrafo, inciso, alínea ou caput nas citações; "
            "cite apenas norma e artigo, inclusive ao explicar uma regra contida numa subdivisão."
            if content_locators
            and not any(
                locator.subdivision_type != "caput"
                for levels in evidence_levels.values()
                for locator in levels
            )
            and all(locator.subdivision_type is None for locator in explicit_locators)
            else ""
        )
        + "\nSTATUS QUE A APLICAÇÃO ACRESCENTARÁ:\n"
        + status
        + "\n[/STRUCTURED OUTPUT]\n"
    )
