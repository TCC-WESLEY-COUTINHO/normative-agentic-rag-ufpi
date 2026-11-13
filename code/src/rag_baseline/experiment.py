"""Frozen candidate-gold pilot: isolated versus combined dense RAG."""

import argparse
import asyncio
import hashlib
import json
import math
import random
import re
import statistics
import subprocess
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from rag_baseline.config import BaselineSettings
from rag_baseline.corpus import build_embedding_text, load_corpus
from rag_baseline.openrouter import OpenRouterClient, OpenRouterError
from rag_baseline.service import SYSTEM_PROMPT, _context
from rag_baseline.vector_store import ChromaVectorStore

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
DATASETS = [
    ROOT / "evaluation/datasets" / f"{name}_v1.json" for name in ("graduacao", "pos_graduacao")
]
SOURCES = {
    "ufpi-177-2012": (CODE / "scripts/chunks_v2.json", "Resolução nº 177/2012 CEPEX/UFPI"),
    "ufpi-956-2025": (
        CODE / "scripts/chunks_resolucao_956_2025_v1.json",
        "Resolução CEPEX/UFPI nº 956/2025",
    ),
}
PROMPT = (
    SYSTEM_PROMPT.replace(
        "Regulamento Geral da Graduação da UFPI", "conjunto de normas acadêmicas da UFPI"
    )
    + "\nIdentifique a resolução e o artigo que sustentam cada afirmação normativa."
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_gold():
    corpora = {norm: load_corpus(path, id_prefix=norm) for norm, (path, _) in SOURCES.items()}
    lookup = {
        (norm, chunk.article_number): chunk.content
        for norm, chunks in corpora.items()
        for chunk in chunks
    }
    if len(lookup) != sum(map(len, corpora.values())):
        raise ValueError("Artigos duplicados no corpus.")
    items = []
    for path in DATASETS:
        dataset = json.loads(path.read_text(encoding="utf-8"))
        if dataset["status"] != "candidate_gold":
            raise ValueError("Este piloto exige o snapshot candidato documentado.")
        items.extend(dataset["items"])
    if len(items) != 40 or len({q["id"] for q in items}) != len(items):
        raise ValueError("São esperadas 40 perguntas com IDs únicos.")
    for q in items:
        if not q["question"].strip() or not q["reference_answer"].strip() or not q["evidence"]:
            raise ValueError(f"Item incompleto: {q['id']}")
        for evidence in q["evidence"]:
            key = evidence["norm_id"], evidence["article_number"]
            if key[0] != q["norm_id"] or lookup.get(key) != evidence["text"]:
                raise ValueError(f"Evidência divergente do corpus: {q['id']} {key}")
    return items, corpora


def retrieval_metrics(gold, ranked, norm):
    if not gold:
        raise ValueError("Qrels vazios não suportados neste piloto respondível.")
    result = {}
    for k in (1, 3, 5):
        hits = len(gold & set(ranked[:k]))
        result[f"recall_at_{k}"] = hits / len(gold)
        result[f"hit_at_{k}"] = int(hits > 0)
    top = ranked[:5]
    result["evidence_complete_at_5"] = int(gold.issubset(set(top)))
    result["mrr_at_5"] = next((1 / i for i, key in enumerate(top, 1) if key in gold), 0)
    seen = set()
    dcg = 0
    for i, key in enumerate(top, 1):
        if key in gold and key not in seen:
            dcg += 1 / math.log2(i + 1)
        seen.add(key)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(5, len(gold)) + 1))
    result["ndcg_at_5"] = dcg / ideal
    applicable = {norm} if isinstance(norm, str) else set(norm)
    result["wrong_norm_at_5"] = (
        sum(key[0] not in applicable for key in top) / len(top) if top else None
    )
    return result


def token_f1(answer, reference):
    def tokenize(text):
        text = unicodedata.normalize("NFKD", text.casefold())
        text = "".join(c for c in text if not unicodedata.combining(c))
        return re.findall(r"\w+", text)

    a, b = tokenize(answer), tokenize(reference)
    overlap = sum((Counter(a) & Counter(b)).values())
    return 2 * overlap / (len(a) + len(b)) if a and b else 0


def paired_summary(rows):
    pairs = defaultdict(dict)
    for row in rows:
        if row["condition"] in pairs[row["id"]]:
            raise ValueError("Condição duplicada no par.")
        pairs[row["id"]][row["condition"]] = row
    if not pairs or any(set(pair) != {"isolated", "combined"} for pair in pairs.values()):
        raise ValueError("Cada par deve conter isolated e combined.")
    strata = defaultdict(list)
    for pair in pairs.values():
        a, b = pair["isolated"], pair["combined"]
        if a["norm_id"] != b["norm_id"]:
            raise ValueError("Normas divergentes no par.")
        strata[a["norm_id"]].append(b["metrics"]["recall_at_5"] - a["metrics"]["recall_at_5"])
    rng = random.Random(956)
    boot = sorted(
        statistics.mean(
            statistics.mean(rng.choices(values, k=len(values))) for values in strata.values()
        )
        for _ in range(5000)
    )
    groups = {}
    for norm in ["all", *sorted(strata)]:
        groups[norm] = {}
        for condition in ("isolated", "combined"):
            selected = [
                r
                for r in rows
                if r["condition"] == condition and (norm == "all" or r["norm_id"] == norm)
            ]
            metrics = {}
            for metric in selected[0]["metrics"]:
                values = [
                    r["metrics"][metric] for r in selected if r["metrics"][metric] is not None
                ]
                metrics[metric] = statistics.mean(values) if values else None
            groups[norm][condition] = {"n": len(selected), "metrics": metrics}
    return {
        "n_pairs": len(pairs),
        "groups": groups,
        "delta_recall_at_5": statistics.mean(statistics.mean(v) for v in strata.values()),
        "bootstrap_95_ci": [boot[124], boot[4874]],
        "bootstrap_samples": 5000,
        "bootstrap_seed": 956,
        "review_answer_accuracy": None,
        "interpretation": "Exploratory candidate qrels; not proof of general RAG insufficiency.",
    }


class MeasuredClient(OpenRouterClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receipts = []

    async def _post(self, path, payload):
        response = await super()._post(path, payload)
        self.receipts.append(
            {
                "endpoint": path,
                "id": response.get("id"),
                "model": response.get("model"),
                "usage": response.get("usage"),
            }
        )
        return response


def client_for(settings):
    return MeasuredClient(
        api_key=settings.api_key_value(),
        base_url=settings.OPENROUTER_BASE_URL,
        embedding_model=settings.EMBEDDING_MODEL,
        llm_model=settings.LLM_MODEL,
        embedding_batch_size=settings.EMBEDDING_BATCH_SIZE,
        llm_temperature=0,
        llm_max_tokens=settings.LLM_MAX_TOKENS,
        timeout_seconds=settings.OPENROUTER_TIMEOUT_SECONDS,
        app_name=settings.OPENROUTER_APP_NAME,
        http_referer=settings.OPENROUTER_HTTP_REFERER,
    )


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def run(output):
    items, corpora = load_gold()
    settings = BaselineSettings(_env_file=CODE / ".env")
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY não configurada.")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    persist = CODE / ".local/gold_pilot" / output.name
    if persist.exists():
        raise ValueError("Persistência desta execução já existe; use novo nome de saída.")
    files = [
        *DATASETS,
        *(p for p, _ in SOURCES.values()),
        CODE / "uv.lock",
        ROOT / "evaluation/protocol.md",
        *sorted((CODE / "src/rag_baseline").glob("*.py")),
    ]
    manifest = {
        "status": "started",
        "started_at": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_diff": subprocess.check_output(
            ["git", "diff", "--stat"], cwd=ROOT, text=True
        ),
        "file_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in files},
        "embedding_model": settings.EMBEDDING_MODEL,
        "llm_model": settings.LLM_MODEL,
        "temperature": 0,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "top_k": 5,
        "api_base_url": settings.OPENROUTER_BASE_URL,
        "system_prompt": PROMPT,
        "repetitions": 1,
        "candidate_gold": True,
        "concurrency": 2,
        "counts": {norm: len(chunks) for norm, chunks in corpora.items()},
    }
    save_json(output / "manifest.json", manifest)
    embedder = client_for(settings)
    all_chunks = [chunk for chunks in corpora.values() for chunk in chunks]
    texts = [
        build_embedding_text(chunk, norm_name=SOURCES[norm][1])
        for norm, chunks in corpora.items()
        for chunk in chunks
    ]
    print(f"Gerando embeddings de {len(all_chunks)} chunks...", flush=True)
    embeddings = await embedder.embed(texts)
    stores = {}
    offset = 0
    for norm, chunks in corpora.items():
        store = ChromaVectorStore(persist, norm)
        store.synchronize(chunks, embeddings[offset : offset + len(chunks)])
        stores[norm] = store
        offset += len(chunks)
    combined = ChromaVectorStore(persist, "ufpi_combined")
    combined.synchronize(all_chunks, embeddings)
    if combined.count() != len(all_chunks):
        raise ValueError("Contagem divergente no índice conjunto.")
    manifest["indexed_counts"] = {norm: store.count() for norm, store in stores.items()}
    manifest["indexed_counts"]["combined"] = combined.count()
    queries = await embedder.embed([q["question"] for q in items])
    manifest["embedding_receipts"] = embedder.receipts
    save_json(output / "manifest.json", manifest)
    rows = []
    semaphore = asyncio.Semaphore(2)

    async def evaluate(index, q, embedding):
        async with semaphore:
            conditions = ["isolated", "combined"] if index % 2 == 0 else ["combined", "isolated"]
            for condition in conditions:
                store = stores[q["norm_id"]] if condition == "isolated" else combined
                started = time.perf_counter()
                chunks = store.query(embedding, top_k=5)
                retrieval_seconds = time.perf_counter() - started
                ranked = [
                    (next(n for n in SOURCES if c.id.startswith(n + "-art-")), c.article_number)
                    for c in chunks
                ]
                gold = {(e["norm_id"], e["article_number"]) for e in q["evidence"]}
                user_prompt = (
                    "CONTEXTO NORMATIVO (use somente como evidência):\n"
                    f"{_context(chunks)}\n\nPERGUNTA:\n{q['question']}"
                )
                client = client_for(settings)
                answer, error = None, None
                try:
                    answer = await client.chat(system_prompt=PROMPT, user_prompt=user_prompt)
                except OpenRouterError as exc:
                    error = str(exc)
                row = {
                    "id": q["id"],
                    "norm_id": q["norm_id"],
                    "condition": condition,
                    "question": q["question"],
                    "reference_answer": q["reference_answer"],
                    "required_facts": q["required_facts"],
                    "gold_evidence": q["evidence"],
                    "retrieved": [c.model_dump() for c in chunks],
                    "user_prompt": user_prompt,
                    "answer": answer,
                    "error": error,
                    "metrics": retrieval_metrics(gold, ranked, q["norm_id"]),
                    "lexical_token_f1": token_f1(answer, q["reference_answer"]) if answer else None,
                    "retrieval_seconds": retrieval_seconds,
                    "total_seconds": time.perf_counter() - started,
                    "provider_receipts": client.receipts,
                }
                rows.append(row)
                with (output / "rows.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(
                    f"{len(rows)}/80 {q['id']} {condition}: recall@5="
                    f"{row['metrics']['recall_at_5']:.2f} error={bool(error)}",
                    flush=True,
                )

    await asyncio.gather(
        *(evaluate(i, q, vector) for i, (q, vector) in enumerate(zip(items, queries, strict=True)))
    )
    rows.sort(key=lambda r: (r["id"], r["condition"]))
    summary = paired_summary(rows)
    summary["generation_errors"] = sum(r["error"] is not None for r in rows)
    save_json(output / "summary.json", summary)
    shuffled = random.Random(177)
    review_rows = list(rows)
    shuffled.shuffle(review_rows)
    annotations, key = [], []
    for i, row in enumerate(review_rows, 1):
        aid = f"BLIND-{i:03d}"
        annotations.append(
            {
                "annotation_id": aid,
                "question": row["question"],
                "answer": row["answer"],
                "reference_answer": row["reference_answer"],
                "required_facts": row["required_facts"],
                "evidence": row["gold_evidence"],
                "annotator": None,
                "correctness_0_2": None,
                "fact_coverage": None,
                "unsupported_claims": None,
                "wrong_norm": None,
                "citation_precision": None,
                "citation_coverage": None,
                "notes": None,
            }
        )
        key.append({"annotation_id": aid, "id": row["id"], "condition": row["condition"]})
    save_json(output / "review_template.json", annotations)
    save_json(output / "blinding_key.json", key)
    manifest["status"] = "completed_with_errors" if summary["generation_errors"] else "completed"
    manifest["finished_at"] = datetime.now(UTC).isoformat()
    save_json(output / "manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        items, corpora = load_gold()
        print(f"{len(items)} itens; " + str({n: len(c) for n, c in corpora.items()}))
        return
    if args.output is None:
        parser.error("--output é obrigatório para executar o piloto")
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()
