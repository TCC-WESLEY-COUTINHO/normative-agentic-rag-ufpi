"""Pure measurements. Lexical checks identify candidates, never certify grounding."""

import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict

VERDICTS = {"pass", "fail", "unknown", "not_run"}
FINDING_CATEGORIES = {
    "routing",
    "conversation",
    "context_leak",
    "temporal",
    "retrieval",
    "grounding",
    "guard",
    "generation",
    "fallback",
    "reference",
    "transport",
    "environment",
}
DEFINITIONS = {
    "association": "Exact case/conversation/turn/question/request/thread and operation correlation match",
    "routing": "Observed sector matches candidate scope (candidate labels, no legal judgment)",
    "clarification": "Expected clarification produces nonempty clarification",
    "redundant_clarification": "Unequivocal continuation does not request resolved scope again",
    "continuity": "Unequivocal continuation resolves with expected sector and no clarification",
    "undue_context": "Forbidden sector/terms absent from final body; explicit gate expectation matches",
    "isolation": "Request and conversation association; no forbidden sector reuse",
    "task_completion": "Substantive final answer with evidence, no fallback/error; lexical facts do not certify correctness",
    "expected_evidence": "At least one complete predefined evidence set recovered by norm and article",
    "reference": "Typed norm compatible with scope; predefined expected norm/article represented",
    "unsupported_claim": "Fail for detectable numbers/deadlines/articles/recipients absent from generation evidence; otherwise unknown, never grounded",
    "required_facts": "Textual required-fact comparison always unknown for normative review",
    "temporal": "Final body only: unsupported applied year or historical wording presented as current",
    "first_generation_accepted": "Incidence: core_status accepted",
    "regenerated_accepted": "Incidence: core_status regenerated",
    "fallback": "Incidence: core_status fallback",
    "abstention": "Incidence: explicit abstention/no eligible context",
    "infrastructure_error": "Incidence: transport failure or infrastructure error code",
    "transport": "HTTP/SSE completion with exactly one authoritative final message and no error event",
    "generation_changed": "Raw and final generation equal; differences retained as diagnostic candidates",
    "expected_status": "Observed status belongs to the predefined candidate status set",
    "cross_turn_consistency": "Comparable extracted procedure attributes do not diverge across turns",
}
CATEGORY = {
    "association": "transport",
    "routing": "routing",
    "clarification": "conversation",
    "redundant_clarification": "conversation",
    "continuity": "conversation",
    "undue_context": "conversation",
    "isolation": "context_leak",
    "task_completion": "generation",
    "expected_evidence": "retrieval",
    "reference": "reference",
    "unsupported_claim": "grounding",
    "required_facts": "grounding",
    "temporal": "temporal",
    "first_generation_accepted": "guard",
    "regenerated_accepted": "guard",
    "fallback": "fallback",
    "abstention": "fallback",
    "infrastructure_error": "environment",
    "transport": "transport",
    "generation_changed": "generation",
    "cross_turn_consistency": "conversation",
    "expected_status": "generation",
}


def folded(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", str(text or "").lower())
        if not unicodedata.combining(c)
    )


def body_only(text):
    # Typed references are separate; legacy bibliography tails must not become body claims.
    return re.split(
        r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:referencias|fontes(?: oficiais)?|sources)\s*:?(?:\*\*)?\s*$",
        folded(text),
    )[0]


def result(verdict="unknown", detail=None):
    if verdict not in VERDICTS:
        raise ValueError("Invalid verdict")
    return dict(verdict=verdict, detail=detail)


def strict_equal(a, b):
    return type(a) is type(b) and a == b


def numeric(value):
    return type(value) in {int, float} and math.isfinite(value)


def pair(item):
    """Resolve typed references and raw chunks without requiring optional metadata."""
    identities = set()
    for value in (
        item.get("norm_id"),
        item.get("source_norm"),
        item.get("id"),
        item.get("chunk_id"),
    ):
        if isinstance(value, str):
            match = re.fullmatch(r"(ufpi-\d+-\d{4})(?:-art-.+)?", value)
            if match:
                identities.add(match[1])
    if not identities and isinstance(item.get("source"), str):
        match = re.search(r"\b(\d[\d.]*)\s*/\s*((?:19|20)\d{2})\b", item["source"])
        if match:
            identities.add(f"ufpi-{match[1].replace('.', '')}-{match[2]}")
    article = (
        item.get("article") or item.get("article_number") or item.get("source_article")
    )
    return (
        next(iter(identities)) if len(identities) == 1 else "",
        str(article) if type(article) in {str, int} else "",
    )


def lexical_claims(text):
    text = body_only(text)
    patterns = {
        "number": r"\b\d+(?:[.,]\d+)?\s*(?:%|dias?\b|horas?\b|mes(?:es)?\b|anos?\b)?",
        "deadline": r"\b(?:um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|quinze|trinta|sessenta)\s+(?:dias?|horas?|meses|anos)\b",
        "article": r"\bart(?:igo)?\.?\s*\d+[a-z]?",
        "recipient": r"\b(?:coordenacao(?: do (?:curso|programa))?|colegiado(?: do (?:curso|programa))?|chefia(?: do departamento)?|departamento|pro[- ]?reitoria|secretaria|professor(?: responsavel)?|direcao)\b",
    }
    return [
        dict(kind=kind, excerpt=m.group().strip(), start=m.start())
        for kind, pattern in patterns.items()
        for m in re.finditer(pattern, text)
    ]


def abstains(row):
    text = body_only(row.get("final_answer"))
    return str(row.get("error_code") or "").upper() == "NO_ELIGIBLE_CONTEXT" or bool(
        re.search(
            r"nao (?:ha|tenho|encontrei|e possivel).*?(?:evidencia|contexto|base|informacao)|"
            r"nao posso (?:afirmar|responder|determinar)|evidencia.*?insuficiente",
            text,
        )
    )


def evaluate_turn(case, row):
    checks = {k: result() for k in DEFINITIONS}
    if row.get("executed") is not True or row.get("harness_budget_stop") is True:
        return {
            k: result("not_run", row.get("not_run_reason", "No execution record"))
            for k in checks
        }
    exp, body = case["expected"], body_only(row.get("final_answer"))
    mismatch, missing = [], []
    for key in ("case_id", "conversation_id", "turn", "question"):
        if key not in row:
            missing.append(key)
        elif not strict_equal(case[key], row[key]):
            mismatch.append(key)
    for a, b in [
        ("request_id", "response_request_id"),
        ("conversation_id", "response_thread_id"),
        ("question", "response_question"),
        ("correlation_id", "observed_correlation_id"),
        ("final_answer", "observed_final_answer"),
    ]:
        if row.get(a) is None or row.get(b) is None:
            missing.append(b)
        elif not strict_equal(row[a], row[b]):
            mismatch.append(b)
    checks["association"] = result(
        "fail" if mismatch else "unknown" if missing else "pass",
        dict(mismatch=mismatch, unavailable=missing),
    )
    checks["transport"] = result(
        "pass"
        if row.get("sse_ok") is True
        else "fail"
        if row.get("sse_ok") is False
        else "unknown"
    )
    expected_sector, sector = exp.get("sector"), row.get("sector")
    if expected_sector is not None:
        checks["routing"] = result(
            "unknown"
            if sector is None
            else "pass"
            if strict_equal(sector, expected_sector)
            else "fail"
        )
    status, core = row.get("status"), row.get("core_status")
    if exp.get("status"):
        checks["expected_status"] = result(
            "unknown"
            if status is None
            else "pass"
            if status in exp["status"]
            else "fail"
        )
    if exp.get("status") == ["CLARIFICATION"]:
        scope_question = bool(
            re.search(r"\b(?:graduacao|pos|nivel|setor|mestrado|doutorado)\b", body)
        )
        checks["clarification"] = result(
            "pass" if status == "CLARIFICATION" and scope_question else "fail",
            "Lexical academic-scope clarification check",
        )
    if exp.get("unequivocal_continuation") is True:
        action = row.get("conversation_action") or row.get("policy_action")
        independent = action == "NORMATIVE_RAG"
        redundant = status == "CLARIFICATION" or bool(
            re.search(
                r"(?:graduacao ou pos|qual (?:o )?(?:setor|nivel)|especifique.*nivel)",
                body,
            )
        )
        checks["redundant_clarification"] = result(
            "fail" if redundant else "pass" if status else "unknown"
        )
        checks["continuity"] = result(
            "fail"
            if independent or redundant or checks["routing"]["verdict"] == "fail"
            else "pass"
            if status == "ANSWER" and sector is not None
            else "unknown",
            dict(
                conversation_action=action,
                independent_question=independent,
                redundant_clarification=redundant,
                expected="Reuse the resolved conversation context",
            ),
        )
        if row.get("antecedent_available") is not True:
            checks["continuity"] = result(
                "unknown", "Required antecedent was not available in the preceding turn"
            )
            checks["redundant_clarification"] = result(
                "unknown", "No resolved antecedent to repeat"
            )
    forbidden = [s for s in exp.get("sector_must_not_be", []) if sector == s]
    forbidden += [
        term for term in exp.get("forbidden_terms", []) if folded(term) in body
    ]
    if exp.get("gate") is not None and row.get("gate") != exp["gate"]:
        if row.get("gate") is None:
            checks["undue_context"] = result(
                "unknown", "Scope gate observation unavailable"
            )
        else:
            forbidden.append("gate")
    elif exp.get("forbidden_terms") or exp.get("sector_must_not_be"):
        checks["undue_context"] = result(
            "fail"
            if forbidden
            else "pass"
            if sector is not None or exp.get("forbidden_terms")
            else "unknown",
            forbidden,
        )
    if forbidden:
        checks["undue_context"] = result("fail", forbidden)
    if exp.get("must_not_disclose_system") is True:
        final_hash = hashlib.sha256(
            json.dumps(
                row.get("final_answer"), ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest()
        disclosed = final_hash in (row.get("system_prompt_hashes") or [])
        checks["undue_context"] = result(
            "fail" if disclosed else "unknown",
            "Exact full system-prompt hash comparison only",
        )
    if case["category"] == "I":
        association = checks["association"]["verdict"]
        checks["isolation"] = result(
            "fail" if forbidden or association == "fail" else association
        )
    chunks, references = row.get("chunks"), row.get("references")
    evidence_text = folded(
        "\n".join(str(c.get("content", c.get("text", ""))) for c in chunks or [])
    )
    temporal_support = row.get("temporal_status_text") or ""
    grounding = row.get("grounding") or {}
    if isinstance(grounding, dict):
        temporal_support += "\n" + json.dumps(
            {key: grounding.get(key) for key in ("known_relations", "evidence_states")},
            ensure_ascii=False,
        )
    # Citation labels cannot substantiate themselves. Only retained source evidence can.
    temporal_support += "\n" + "\n".join(
        str(r.get("evidence_text") or "") for r in references or []
    )
    support_text = evidence_text + "\n" + folded(temporal_support)
    claims = lexical_claims(body)
    unsupported = [claim for claim in claims if claim["excerpt"] not in support_text]
    checks["unsupported_claim"] = result(
        "fail" if evidence_text and unsupported else "unknown",
        dict(
            heuristic="exact lexical numbers/deadlines/articles/recipients",
            candidates=unsupported,
            reason="Absence of lexical mismatch never certifies grounding",
        ),
    )
    expected_sets = exp.get("alternative_evidence_sets") or (
        [exp["evidence"]] if exp.get("evidence") else []
    )
    actual = {pair(c) for c in chunks or [] if all(pair(c))}
    unresolved_chunks = [
        c.get("id", c.get("chunk_id")) for c in chunks or [] if not all(pair(c))
    ]
    evidence_hit = any({pair(e) for e in group} <= actual for group in expected_sets)
    if expected_sets:
        checks["expected_evidence"] = result(
            "unknown"
            if chunks is None or unresolved_chunks and not evidence_hit
            else "pass"
            if evidence_hit
            else "fail",
            dict(
                expected=[[pair(e) for e in group] for group in expected_sets],
                observed=sorted(actual),
                unresolved=unresolved_chunks,
                reason="Identity extraction unavailable"
                if unresolved_chunks
                else "Predefined norm/article evidence comparison",
            ),
        )
    norms = {pair(r)[0] for r in references or [] if pair(r)[0]}
    bad_norms = []
    reference_sector = sector or expected_sector
    for norm in norms:
        if reference_sector == "graduacao" and norm in {
            "ufpi-658-2024",
            "ufpi-956-2025",
        }:
            bad_norms.append(norm)
        if reference_sector == "pos_graduacao" and norm in {
            "ufpi-177-2012",
            "ufpi-1056-2026",
        }:
            bad_norms.append(norm)
    ref_pairs = {pair(r) for r in references or [] if all(pair(r))}
    unresolved_refs = [
        r.get("chunk_id", r.get("source")) for r in references or [] if not all(pair(r))
    ]
    reference_detail = dict(
        expected=[[pair(e) for e in group] for group in expected_sets],
        observed=sorted(ref_pairs),
        sector=reference_sector,
        incompatible_norms=bad_norms,
        unresolved=unresolved_refs,
    )
    registry = (
        row.get("registry_norms")
        or case.get("registry_norms")
        or {
            "ufpi-177-2012": "graduacao",
            "ufpi-1056-2026": "graduacao",
            "ufpi-658-2024": "pos_graduacao",
            "ufpi-956-2025": "pos_graduacao",
        }
    )
    invalid_refs = []
    for ref in references or []:
        norm, article = pair(ref)
        if norm and norm not in registry:
            invalid_refs.append(
                dict(reference=pair(ref), reason="Norm absent from registry")
            )
        elif norm and reference_sector not in {None, "ambas", registry.get(norm)}:
            invalid_refs.append(dict(reference=pair(ref), reason="Norm outside sector"))
        elif (
            norm
            and article
            and chunks is not None
            and not unresolved_chunks
            and (norm, article) not in actual
        ):
            invalid_refs.append(
                dict(
                    reference=pair(ref),
                    reason="Article absent from generation evidence",
                )
            )
    if invalid_refs:
        checks["reference"] = result(
            "fail",
            {
                **reference_detail,
                "invalid_references": invalid_refs,
                "reason": "Each typed reference must be registered, in sector and in generation evidence",
            },
        )
    elif bad_norms:
        checks["reference"] = result(
            "fail",
            {**reference_detail, "reason": "Norm incompatible with observed sector"},
        )
    elif unresolved_refs or unresolved_chunks:
        checks["reference"] = result(
            "unknown",
            {
                **reference_detail,
                "unresolved_chunks": unresolved_chunks,
                "reason": "Reference or generation chunk identity extraction unavailable",
            },
        )
    elif references and chunks is None:
        checks["reference"] = result(
            "unknown",
            {
                **reference_detail,
                "reason": "Generation evidence unavailable for per-reference validation",
            },
        )
    elif references:
        checks["reference"] = result(
            "pass"
            if not expected_sets
            or any({pair(e) for e in group} <= ref_pairs for group in expected_sets)
            else "fail",
            {
                **reference_detail,
                "reason": "Typed references compared with predefined norm/article sets",
            },
        )
    elif references == [] and expected_sets and status == "ANSWER":
        checks["reference"] = result(
            "fail",
            {
                **reference_detail,
                "reason": "Substantive answer has no typed references",
            },
        )
    if exp.get("required_facts"):
        checks["required_facts"] = result(
            "unknown",
            dict(
                textual_matches=[folded(f) in body for f in exp["required_facts"]],
                reason="Text matching requires normative review",
            ),
        )
    temporal_violations = []
    if exp.get("historical_wording") is True:
        for clause in re.split(r"[.!?\n]+", body):
            negated = re.search(r"\b(?:nao|sem|impossivel|desconhecid[ao])\b", clause)
            asserts_current = re.search(
                r"\b(?:atualmente|hoje)\b.{0,140}\b(?:deve|exige|e|sera|pode|tem)\b|\b(?:esta|e|continua|permanece|vigora|vale|aplica-se)\b.{0,60}\b(?:vigente|em vigor|hoje|atualmente)\b",
                clause,
            )
            if asserts_current and not negated:
                temporal_violations.append("historical_wording_as_current_candidate")
    years = re.findall(
        r"\b(?:em|no ano de|aplicavel em|vigente em)\s+((?:19|20)\d{2})\b", body
    )
    years += re.findall(
        r"\b(?:regra|redacao|norma)\s+(?:de\s+)?((?:19|20)\d{2})\b[^.!?\n]{0,100}\b(?:aplicavel|aplica|vigente|vale)\b",
        body,
    )
    requested = exp.get("requested_year")
    if type(requested) is int and any(int(y) != requested for y in years):
        temporal_violations.append("incorrect_applied_year_candidate")
    forbidden_year = exp.get("forbidden_applied_year")
    if type(forbidden_year) is int and str(forbidden_year) in years:
        temporal_violations.append("forbidden_applied_year_candidate")
    if exp.get("must_not_certify_current_validity") is True:
        for clause in re.split(r"[.!?\n]+", body):
            if not re.search(r"\b(?:nao|sem|impossivel)\b", clause) and re.search(
                r"\b(?:esta|e|continua|permanece)\s+(?:inteiramente\s+|totalmente\s+)?vigente\b|\b(?:certifico|garanto)\b.*\bvigencia\b",
                clause,
            ):
                temporal_violations.append(
                    "global_current_validity_certification_candidate"
                )
    if (
        case["category"] == "T"
        or requested is not None
        or exp.get("historical_wording") is True
        or exp.get("must_not_certify_current_validity") is True
    ):
        checks["temporal"] = result(
            "fail" if temporal_violations else "unknown", temporal_violations
        )
    is_abstention = abstains(row)
    if core is not None:
        for name, value in [
            ("first_generation_accepted", "accepted"),
            ("regenerated_accepted", "regenerated"),
            ("fallback", "fallback"),
        ]:
            checks[name] = result("pass" if core == value else "fail")
    checks["abstention"] = result(
        "pass" if is_abstention else "fail" if body else "unknown"
    )
    error_code = str(row.get("error_code") or "").upper()
    infra = row.get("sse_ok") is False or error_code in {
        "PROVIDER_ERROR",
        "INTERNAL_ERROR",
        "INDEX_UNAVAILABLE",
        "ROUTER_ERROR",
        "TRANSPORT_ERROR",
    }
    checks["infrastructure_error"] = result(
        "pass" if infra else "fail" if status else "unknown"
    )
    if exp.get("must_abstain") is True:
        checks["task_completion"] = result(
            "pass"
            if is_abstention or core == "fallback"
            else "fail"
            if status == "ANSWER"
            else "unknown"
        )
    elif status == "CLARIFICATION" and exp.get("status") == ["CLARIFICATION"]:
        checks["task_completion"] = checks["clarification"].copy()
    elif core == "fallback" or is_abstention or status == "ERROR":
        checks["task_completion"] = result("fail", "No substantive answer")
    elif status == "ANSWER" and body:
        checks["task_completion"] = result(
            "fail"
            if checks["association"]["verdict"] == "fail"
            or checks["transport"]["verdict"] == "fail"
            else "unknown"
            if not evidence_text or exp.get("required_facts")
            else "pass",
            "Operational completion only; not normative accuracy",
        )
    if row.get("raw_generation") is not None and row.get("final_answer") is not None:
        checks["generation_changed"] = result(
            "pass" if row["raw_generation"] == row["final_answer"] else "fail",
            "Diagnostic difference; may be intended guard/composition",
        )
    prerequisites = [checks[k]["verdict"] for k in ("association", "transport")]
    if "fail" in prerequisites:
        checks["task_completion"] = result(
            "fail", "Association or transport prerequisite failed"
        )
    elif "unknown" in prerequisites:
        checks["task_completion"] = result(
            "unknown", "Association or transport prerequisite unavailable"
        )
    if exp.get("exploratory") is True or (
        exp.get("unequivocal_continuation") is True
        and row.get("antecedent_available") is not True
    ):
        for name in (
            "continuity",
            "redundant_clarification",
            "expected_status",
            "routing",
        ):
            checks[name] = result(
                "unknown", "Exploratory continuation or required antecedent unavailable"
            )
        if "fail" not in prerequisites:
            checks["task_completion"] = result(
                "unknown", "No definite task expectation without a resolved antecedent"
            )
    return checks


def extract_procedure(row):
    """Explicit lexical procedure extractor; retain provenance for review."""
    text = body_only(row.get("final_answer"))
    patterns = {
        "deadline": r"\b(?:\d+|um|uma|dois|duas|tres|cinco|sete|dez|quinze|trinta|sessenta)\s+(?:dias?|horas?|meses)\b",
        "recipient": r"\b(?:coordenacao(?: do (?:curso|programa))?|colegiado(?: do (?:curso|programa))?|chefia(?: do departamento)?|secretaria|professor)\b",
        "protocol": r"\b(?:sigaa|protocolo eletronico|presencialmente|por e-?mail|formulario|requerimento escrito)\b",
        "proof": r"\b(?:atestado medico|comprovante|documento comprobatorio|sem comprovante|dispensa de comprovacao)\b",
    }
    evidence = folded(
        " ".join(c.get("content", c.get("text", "")) for c in row.get("chunks") or [])
    )
    articles = [pair(r) for r in row.get("references") or []]
    return [
        dict(
            attribute=kind,
            value=m.group(),
            excerpt=text[max(0, m.start() - 60) : m.end() + 80],
            supported_lexically=m.group() in evidence,
            articles=articles,
            turn=row.get("turn"),
        )
        for kind, pattern in patterns.items()
        for m in re.finditer(pattern, text)
    ]


def cross_turn_findings(rows):
    groups, findings = defaultdict(list), []
    for row in rows:
        if row.get("harness_budget_stop") is True or row.get("executed") is False:
            continue
        groups[row.get("conversation_id")].append(row)
    for conv, turns in groups.items():
        for i, current in enumerate(turns):
            for previous in turns[:i]:
                # Shared articles, sector and temporal intent are prerequisites for comparison.
                common = {pair(r) for r in current.get("references") or []} & {
                    pair(r) for r in previous.get("references") or []
                }
                if (
                    not common
                    or current.get("sector") != previous.get("sector")
                    or current.get("temporal_intent") != previous.get("temporal_intent")
                ):
                    continue
                for attr in ("deadline", "recipient", "protocol", "proof"):
                    a = [
                        x for x in extract_procedure(previous) if x["attribute"] == attr
                    ]
                    b = [
                        x for x in extract_procedure(current) if x["attribute"] == attr
                    ]
                    if a and b and {x["value"] for x in a} != {x["value"] for x in b}:
                        findings.append(
                            dict(
                                category="conversation",
                                classification="cross_turn_inconsistency",
                                conversation_id=conv,
                                case_id=current.get("case_id"),
                                attribute=attr,
                                turns=[previous.get("turn"), current.get("turn")],
                                articles=sorted(common),
                                excerpts=a + b,
                                verdict="fail",
                                reason="Candidate divergence; no legal procedure selected",
                            )
                        )
    return findings


def classify_response(row):
    checks = row.get("checks", {})
    if checks.get("cross_turn_consistency", {}).get("verdict") == "fail":
        return "cross_turn_inconsistency"
    if checks.get("unsupported_claim", {}).get("verdict") == "fail":
        return "unsupported_claim"
    if not row.get("chunks"):
        return "insufficient_evidence"
    if (
        checks.get("required_facts", {}).get("verdict") == "unknown"
        or row.get("category") == "T"
    ):
        return "requires_normative_review"
    if abstains(row) or row.get("core_status") == "fallback":
        return "supported_but_incomplete"
    # Lexical support is insufficient to select supported_consistent automatically.
    return "requires_normative_review"


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    p = (len(ordered) - 1) * fraction
    lo, hi = math.floor(p), math.ceil(p)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (p - lo)


def summarize(rows):
    rows = list(rows)

    def metrics(subset):
        names = sorted({k for row in subset for k in row.get("checks", {})})
        out = {}
        for name in names:
            verdicts = [
                r.get("checks", {}).get(name, {}).get("verdict", "unknown")
                for r in subset
            ]
            if any(v not in VERDICTS for v in verdicts):
                raise ValueError("Invalid metric verdict")
            numerator = verdicts.count("pass")
            denominator = numerator + verdicts.count("fail")
            out[name] = dict(
                definition=DEFINITIONS.get(name, name),
                numerator=numerator,
                denominator=denominator,
                value=numerator / denominator if denominator else None,
                unknown=verdicts.count("unknown"),
                not_run=verdicts.count("not_run"),
            )
        latencies = [
            r["latency_ms"]
            for r in subset
            if numeric(r.get("latency_ms")) and r.get("executed") is True
        ]
        costs = [
            r["cost_usd"]
            for r in subset
            if numeric(r.get("cost_usd")) and r.get("executed") is True
        ]
        out["latency"] = dict(
            definition="Executed measured turns; linear interpolated milliseconds; denominator is observed latencies",
            numerator=len(latencies),
            denominator=len(latencies),
            unknown=sum(
                r.get("executed") is True and not numeric(r.get("latency_ms"))
                for r in subset
            ),
            not_run=sum(r.get("executed") is not True for r in subset),
            p50=percentile(latencies, 0.5),
            p95=percentile(latencies, 0.95),
        )
        out["cost"] = dict(
            definition="Sum of observed usage.cost USD; missing costs excluded and separately reported",
            numerator=sum(costs),
            denominator=len(costs),
            unknown=sum(
                r.get("executed") is True and not numeric(r.get("cost_usd"))
                for r in subset
            ),
            not_run=sum(r.get("executed") is not True for r in subset),
            total_usd=sum(costs) if costs else None,
        )
        estimates = [
            r["estimated_cost_usd"]
            for r in subset
            if numeric(r.get("estimated_cost_usd")) and r.get("executed") is True
        ]
        out["estimated_cost"] = dict(
            definition="Separate embedding estimate at frozen USD 0.02 per million total tokens",
            numerator=sum(estimates),
            denominator=len(estimates),
            total_usd=sum(estimates) if estimates else None,
            unknown=sum(
                r.get("executed") is True and not numeric(r.get("estimated_cost_usd"))
                for r in subset
            ),
            not_run=sum(r.get("executed") is not True for r in subset),
        )
        return out

    return dict(
        overall=metrics(rows),
        by_category={
            cat: metrics([r for r in rows if r.get("category") == cat])
            for cat in sorted({r.get("category", "unknown") for r in rows})
        },
        cost_by_case={r.get("case_id"): r.get("cost_usd") for r in rows},
        independent_evidence_note="Overlapping duplicate_of rows are descriptive only",
        independent_only=metrics([r for r in rows if not r.get("duplicate_of")]),
    )
