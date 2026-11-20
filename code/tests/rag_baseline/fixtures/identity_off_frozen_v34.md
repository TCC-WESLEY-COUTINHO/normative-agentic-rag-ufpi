Frozen identity-off reference
=============================

From `code/`, in PowerShell:

```powershell
uv run --frozen python scripts/regenerate_identity_off_frozen.py
```

The script reads `conversation_policy.py`, `agent_graph.py` and
`conversation_graph.py` with `git show` from `tcc2-cond-v3.4`, pinned to commit
`1f6a03216267bbcff98123f8b3c215d3ca2deef9`. It loads those modules in its own
process before importing the replay harness. No temporary worktree is needed.
Other dependencies and test doubles use the current checkout and locked environment,
as in the original review. The JSON records the source hashes for provenance.

The reference contains the original 14-turn review sequence twice: without an
interpreter and with the scripted interpreter plus transition policy v2. Each turn
captures the entire state (including complete audit and private normative memory)
and cumulative Scope Gate, facade and interpreter call arguments. Generated graph
UUIDs use a deterministic sequence; message IDs use stable distinct placeholders.
All other fields, including telemetry, remain intact.

The regression test reads the checked-in JSON without Git or regeneration and
compares it with the current integrated graph with `ASSISTANT_IDENTITY=off`.
Regeneration must be explicit; inspect the JSON diff if dependencies or test
doubles have changed. Never regenerate from the current graph to accept a failure.
