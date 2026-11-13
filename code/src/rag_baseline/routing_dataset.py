"""Reproducible routing-only derivation; existing questions and labels stay intact."""

import ast
import hashlib
import json
import re
import unicodedata
from collections import defaultdict

SPLIT_SEED = "router-v2-split-2026-10-28"
CATEGORIES = {
    "graduacao": "explicit_graduacao",
    "pos_graduacao": "explicit_pos",
    "ambas": "cross_domain",
    None: "ambiguous",
}
PARAPHRASES = (
    "Compare as regras de matrícula na graduação e na pós-graduação da UFPI.",
    "Quais diferenças existem no aproveitamento de estudos entre graduação e pós-graduação?",
    "Quais regras de frequência valem na graduação e na pós-graduação?",
    "Compare os requisitos de conclusão da graduação e do mestrado na UFPI.",
    "Como funciona o trancamento nos dois níveis, graduação e pós-graduação?",
    "Quero conhecer as regras de avaliação tanto da graduação quanto da pós-graduação.",
)


def canonical_question(question):
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", question.casefold())
        if not unicodedata.combining(c)
    )
    return " ".join(re.findall(r"\w+", text))


def derive_dataset(root):
    folder = root / "evaluation/datasets"
    sources, items = {}, []

    def read(name):
        path = folder / (name + ".json")
        sources[path.relative_to(root).as_posix()] = hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        return json.loads(path.read_text(encoding="utf-8"))["items"]

    labels = {i["id"]: i for i in read("router_labels_v1")}

    def add(item_id, question, scope, source, *, forced=False, paraphrase=False):
        items.append(
            dict(
                id=item_id,
                question=question,
                expected_scope=scope,
                expected_action="esclarecer" if scope is None else "responder",
                category=CATEGORIES[scope],
                source_dataset=source,
                source_item_id=item_id,
                split="DEV" if forced else None,
                candidate_paraphrase=paraphrase,
                aliases=[],
            )
        )

    for name in ("graduacao_v2", "pos_graduacao_v2"):
        for q in read(name):
            add(
                q["id"],
                q["question"],
                labels[q["id"]]["expected_scope"],
                f"evaluation/datasets/{name}.json",
            )
    for name in ("temporal_candidates_v2", "agentic_smoke_v1"):
        for q in read(name):
            add(
                q["id"],
                q["question"],
                q["expected_scope"],
                f"evaluation/datasets/{name}.json",
                forced=True,
            )
    control_path = root / "evaluation/failure_analysis.py"
    sources[control_path.relative_to(root).as_posix()] = hashlib.sha256(
        control_path.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    tree = ast.parse(control_path.read_text(encoding="utf-8"))
    controls = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ROUTE_CONTROLS" for t in n.targets)
    )
    for item_id, question, scope in controls:
        add(item_id, question, scope, "evaluation/failure_analysis.py:ROUTE_CONTROLS", forced=True)
    for number, question in enumerate(
        (
            "Não sei se meu curso é graduação ou pós-graduação.",
            "Na graduação eu podia trancar; no meu curso atual também posso?",
        ),
        1,
    ):
        add(
            f"REGRESSION-{number:03}",
            question,
            None,
            "code/tests/rag_baseline/test_router_failure_regression.py",
            forced=True,
        )
    for number, question in enumerate(PARAPHRASES, 1):
        add(
            f"CROSS-CANDIDATE-{number:03}",
            question,
            "ambas",
            "prepared_candidate_paraphrase_of_agentic_smoke_v1:SMOKE-003",
            paraphrase=True,
        )
    unique = {}
    for q in items:
        key = canonical_question(q["question"])
        if key not in unique:
            unique[key] = q
        else:
            prior = unique[key]
            if prior["expected_scope"] != q["expected_scope"]:
                raise ValueError("Rótulos conflitantes em perguntas duplicadas.")
            prior["aliases"].append({k: q[k] for k in ("id", "question", "source_dataset")})
            if q["split"] == "DEV":
                prior["split"] = "DEV"
    groups = defaultdict(list)
    for q in unique.values():
        if q["split"] is None:
            groups[(q["category"], q["candidate_paraphrase"])].append(q)
    for group in groups.values():
        ordered = sorted(
            group, key=lambda q: hashlib.sha256((SPLIT_SEED + q["id"]).encode()).hexdigest()
        )
        for rank, q in enumerate(ordered):
            q["split"] = "DEV" if rank % 2 == 0 else "TEST"
    return dict(
        schema_version="1.0",
        candidate_gold=True,
        status="exploratory_candidate",
        split_seed=SPLIT_SEED,
        source_sha256=sources,
        source_sha256_representation="lf_normalized",
        split_method="stratified_hash_alternation; known cases forced DEV; duplicates grouped",
        independence="TEST held out from threshold calibration; prior exposure and shared paraphrase families prevent confirmatory inference",
        items=sorted(unique.values(), key=lambda q: q["id"]),
    )
