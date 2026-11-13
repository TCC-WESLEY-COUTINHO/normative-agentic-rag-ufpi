# Exploratory battery

Characterization only. The executor reads candidate datasets and the existing
pipeline without changing policies, prompts, corpus, index sources or labels.
Python 3.11+ and the application's installed dependencies are required for
`deterministic`, `live` and `service_observer`. `plan` and `report` use the standard
library. Run from the repository root with both `code/src` and the repository root on `PYTHONPATH` for service
commands. Disable optional external tracing in the service environment.

```sh
python -B -m evaluation.exploratory.battery plan --output "$PLAN_OUTPUT"
python -B -m evaluation.exploratory.battery deterministic --output "$OFFLINE_OUTPUT"
python -B -m evaluation.exploratory.battery report --output "$OFFLINE_OUTPUT"
```

Each output must be a fresh directory outside every checkout. A plan creates all
report files with `not_run` turns. A round does not reuse a plan directory and
never selectively reruns cases. `report` recomputes checks from the recorded
round, filling interrupted or absent cases with `not_run`. A failed preflight
preserves the complete planned coverage with an explicit reason.

Inside the API image, mount the repository so `evaluation.exploratory` and the
application packages are importable. Choose external, shared output and temporary
directories. Keep the mounted index stable while copying it. Start one fresh
observer process per round:

```sh
python -B -m evaluation.exploratory.service_observer \
  --mounted-index "$INDEX_SOURCE" --copy-state-from "$SQLITE_SOURCE" \
  --temporary-root "$TEMPORARY_STATE_ROOT" --trace "$TRACE_FILE" \
  --max-chat 640 --max-embedding 320 --max-usd 1
```

The entry point copies the index and takes a read-only SQLite backup (including
committed WAL contents), sets `CHROMA_PERSIST_DIR` and `SQLITE_DB_PATH` to those
temporary copies before importing the app, installs observational wrappers, then
starts real uvicorn on `127.0.0.1:18080`. Source paths are not written to reports.
The entry point fixes and validates `DATABASE_TYPE=sqlite` and disables optional
external tracing for this process; inherited remote database settings are not used.
The index copy must not itself be a mount or contain symlinks. Temporary storage
must be outside repository checkouts. Normal shutdown removes the copies.
The original index and checkpoint database are never opened for writing by the
executor. The API's existing startup/readiness checks still apply.

Run the client where that loopback port and the same trace file are accessible
(normally inside the same container or network namespace):

```sh
python -B -m evaluation.exploratory.battery live \
  --output "$LIVE_OUTPUT" --trace "$TRACE_FILE"
python -B -m evaluation.exploratory.battery report --output "$LIVE_OUTPUT"
```

If the service requires bearer authentication, supply `EXPLORATORY_AUTH_TOKEN`
through the environment. It is never serialized. Retain existing application
provider configuration privately. The client checks a fresh observer handshake,
sends one request at a time, uses the actual `StreamInput` UI defaults, validates
SSE error/terminal events and matches response, request, thread, case, turn and
operation correlation. No browser or Streamlit interaction is driven.

Budgeting occurs only at `OpenRouterClient._post`. Chat and embedding requests
have separate counts. USD accumulation uses strictly numeric `usage.cost`;
missing chat cost or a provider failure with unknown cost stops the round.
Embedding without cost uses total tokens and the frozen tariff in a separate
estimated account; missing tokens stop the round. Reservations precede calls;
responses above the reservation stop the round and are recorded. A budget stop
raises the actual `OpenRouterError`. Unexecuted
messages retain `not_run` and the stop reason. There is no retry loop.

Wrappers return the same objects; extraction, serialization and trace-write
failures are contained by the recorder. The client stops following a dropped
trace record. Every assembled provider prompt, including user-role instructions,
is represented by SHA-256 and byte size. Original questions, retrieved evidence, raw/final generation and structured audits can
be retained. Headers, credentials and private reasoning are excluded.

The live path is HTTP/SSE → API → integrated agent → conversation policy →
Scope Gate → Router V1 or explicit-sector resolution → temporal interpretation →
retrieval strategy → VersionFilter → grounding → generation → output guard.
Short circuits and absent fields are recorded, not filled with inferred stages.

The catalog is exactly 160 user messages: G 80, C1 4, C2 21, B 10, I 8, D 8,
T 14, S 8, L 7. All four 20-item candidate datasets are read in full. V2 clarify
items send only their question. Exact `question_original` overlap is identified
by `duplicate_of`; these records are not independent observations. Additional
datasets are inventoried with hashes, counts and explicit use/reason.

Offline mode uses the real graph, facade, router, temporal filter, generation
guard, transport projection and ASGI/SSE endpoint with an in-memory candidate
store and fixed provider responses. It records catalog policy actions and
separate operational/component probes in `deterministic_probes.jsonl`. These
probes include failed generation/retrieval/router calls, empty responses,
rejected/invalid/accepted regeneration, no-context fallback, resumption,
in-memory adversarial documents and generator interruption. They measure
contracts rather than provider answer quality. Generator interruption does not
simulate a TCP disconnect. Component-only dataset usage is stated per probe;
symbolic follow-up fixtures are not interpreted as real user messages.

Required outputs are `test_plan.json`, `cases.jsonl`, `runs.jsonl`, `turns.jsonl`,
`metrics.json`, `failures.csv`, `coverage_matrix.csv`, `REPORT.md` and
`REPRODUCTION.md`. Auxiliary files retain observer traces, offline probes and
the round's thread mapping. Null fields include known `unavailable_reason`.
Each case ID identifies one message; `conversation_id` and `turn` retain the
conversation structure, including sequentially interleaved isolation cases.

Only `pass`, `fail`, `unknown`, `not_run` are verdicts. Metric definitions and
numerators/denominators are explicit. Unknown/not_run are never promoted to pass.
Occurrence metrics (`fallback`, `abstention`, infrastructure errors, accepted
first/regenerated output) use pass to mean the event occurred. Diagnostic raw
versus final differences may be intended guard/composition behavior.

Numbers, deadlines, articles and recipients in the final body are compared
lexically with the generation evidence; bibliography tails are excluded. A
detectable unsupported claim produces fail; all other grounding outcomes are
unknown. Required facts always remain unknown with textual match details.
Expected evidence is checked by norm/article and predefined alternative sets.
Temporal applied-year/historical-current checks are heuristic candidates.
Cross-turn procedure extraction retains deadlines, recipients, protocol, proof,
excerpts and articles; candidate divergences never establish which procedure is
legally correct. Allowed response classes are `supported_consistent`,
`supported_but_incomplete`, `cross_turn_inconsistency`, `unsupported_claim`,
`insufficient_evidence`, `requires_normative_review`. Automatic lexical checks
do not assign `supported_consistent` as a grounding certificate.

Host verification:

```sh
python -B -m pytest code/tests/rag_baseline/test_exploratory_battery.py -q
```

The mutation tests cover association, scope, references, temporal application,
fallback, SSE, missing execution, raw/final changes, denominator arithmetic,
strict boolean types, missing evidence, budgets and output boundaries.

Temporal probes use the controlled candidate assembly and complete graph path
from `rag_baseline.temporal_evaluation`: source corpus identity, dataset candidate
order/rank, excluded sources, scope, comparisons and broken-amendment fixtures.
The unchanged dataset expectations are evaluated by its existing `inspect_case`.
Every probe records `expected`, `observed` and `reason`; missing input identities
are reported as an unavailable measurement rather than a system failure.

Evidence/reference identities use explicit `norm_id` first and the actual
`id`/`chunk_id` when that optional metadata is absent. Unresolved or conflicting
identities remain unknown; mismatches retain expected/observed norm/article
pairs. Public transport validation uses JSON serialization, including UUIDs.
An unequivocal continuation classified as independent `NORMATIVE_RAG` is a
functional continuity failure even when a standalone answer was returned.
The initial scope clarification is excluded from redundant-clarification checks.

Cost is reserved before each request using the frozen model tariffs and UTF-8 byte counts, with safety factor 2. The server and client reject caps above USD 1.00. Embedding usage without cost uses a separate estimate at USD 0.02 per million total tokens; missing tokens stop the round. Chat without cost stops. A response above its reservation stops the round. All assembled provider prompts, including user-role repair instructions, retain only hash and size. Original/effective questions, chunks and structured audits remain separate. Use --image-id and --candidate-head on both server and live client to record and check candidate identity. The imported product manifest hashes actual package locations; missing Git metadata is unknown.

The fixed tariff snapshot in test_plan.json and REPORT.md records the public table read at 2026-11-04T02:19:02Z. Qwen qwen/qwen3-30b-a3b-instruct-2507 uses USD 0.0000001 per prompt token and USD 0.0000003 per completion token (Nebius table row: USD 0.10/0.30 per million). openai/text-embedding-3-small uses USD 0.00000002 per input token. Sources: https://openrouter.ai/qwen/qwen3-30b-a3b-instruct-2507 and https://openrouter.ai/openai/text-embedding-3-small .

Chat reservation is 2 * (UTF-8 bytes across message contents * prompt tariff + payload max_tokens * completion tariff). Embedding reservation is 2 * UTF-8 bytes of input * its model tariff. A missing max_tokens uses --max-tokens (round default 800), recorded with max_tokens_source. Unknown models stop before invocation with unpriced_model. A provider_reservation event precedes every invocation and records inputs to this calculation without prompt contents. This bounds cost under the frozen tariffs and stated byte/token bound; real provider charges could differ and are detected only after the response. Last-permitted completed responses remain evaluated; only subsequent requests or actually interrupted current turns are not_run.
