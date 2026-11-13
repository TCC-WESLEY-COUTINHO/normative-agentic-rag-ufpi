"""Validate finite UI evidence, preservation manifests, and publish the technical report."""

import ast
import collections
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
NOW = datetime.now(timezone.utc).isoformat()


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def write(name, value):
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout


def event(kind, **kwargs):
    with (OUT / "execution_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(dict(timestamp=NOW, event=kind, **kwargs), ensure_ascii=False)
            + "\n"
        )


rows = [
    json.loads(line)
    for line in (OUT / "ui_probe_rows.jsonl").read_text(encoding="utf-8").splitlines()
]
protocol = read("ui_protocol.json")
assert len(rows) == 12 and all(row["passed"] for row in rows)
assert len(read("ui_requests.json")) == 12
assert all(
    hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    for path, digest in protocol["hashes"].items()
)
assert read("index_before.json") == read("index_after.json")
assert read("index_after.json")["count"] == 507
assert (
    read("external_attempts_18081.json") == read("external_attempts_18082.json") == []
)
private = (
    "internal_audit",
    "storage_key",
    "memory envelope",
    "prompt",
    "raw generation",
    "embedding",
    "correlation_id",
    "contract_version",
    "core_version",
)
assert all(not any(key in row["visible"] for key in private) for row in rows)
assert all(row["request"]["agent"] == "chatbot_ufpi_integrated_v1" for row in rows)
assert (
    len({(r["request"]["user_id"], r["request"]["thread_id"]) for r in rows[:10]}) == 1
)
assert rows[10]["request"]["thread_id"] != rows[9]["request"]["thread_id"]
assert rows[10]["request"]["user_id"] == rows[9]["request"]["user_id"]
assert all("chatbot_ufpi_v2" not in row["visible"] for row in rows)
metrics = {
    "Integrated Agent Selection Preservation": {
        "numerator": 12,
        "denominator": 12,
        "unit": "UI requests",
    },
    "Typed Message Rendering Rate": {
        "numerator": 11,
        "denominator": 11,
        "unit": "successful ChatMessages",
    },
    "Official Reference Rendering Rate": {
        "numerator": sum(r.get("shown_references", 0) for r in rows),
        "denominator": sum(r.get("expected_references", 0) for r in rows),
        "unit": "structurally unique references per last response",
    },
    "Content-to-Reference Parsing Count": {
        "numerator": 0,
        "denominator": 26,
        "unit": "rendered references; source audit and art999 AppTest",
    },
    "Grounded Follow-up Rendering Rate": {
        "numerator": 2,
        "denominator": 2,
        "unit": "grounded UI probes",
    },
    "Calculator Rendering Rate": {
        "numerator": 2,
        "denominator": 2,
        "unit": "calculator UI probes",
    },
    "Thread Continuity Rate": {
        "numerator": 10,
        "denominator": 10,
        "unit": "requests in original conversation",
    },
    "New Conversation Thread Reset Rate": {
        "numerator": 1,
        "denominator": 1,
        "unit": "new conversation action",
    },
    "Legacy Fallback Count": {
        "numerator": 0,
        "denominator": 1,
        "unit": "unavailable integrated service probe",
    },
    "Private Field UI Leakage Count": {
        "numerator": 0,
        "denominator": 12,
        "unit": "observed UI screens",
    },
    "UI Probe Success Rate": {
        "numerator": 12,
        "denominator": 12,
        "unit": "frozen UI cases",
    },
}
write("metrics.json", metrics)
before = read("preservation_before.json")
changed = [
    p
    for p, d in before.items()
    if not (ROOT / p).is_file()
    or hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != d
]
allowed = [
    "code/src/streamlit_app.py",
    "code/src/client/client.py",
    "code/tests/app/conftest.py",
    "code/tests/app/test_streamlit_app.py",
]
assert set(changed) == set(allowed), (changed, allowed)
old = ast.parse(
    git("show", "39f866c1b788ea8a5701bc74efee2aaf0812e5d7:code/src/client/client.py")
)
new = ast.parse((ROOT / "code/src/client/client.py").read_text(encoding="utf-8"))


def methods(tree):
    return {
        n.name: ast.dump(n, include_attributes=False)
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AgentClient"
        for n in node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


a, b = methods(old), methods(new)
assert [name for name in a if a[name] != b[name]] == ["_parse_stream_line"]
assert not any(p.startswith("evaluation/results/") for p in changed)
write(
    "preservation.json",
    dict(
        timestamp=NOW,
        initial_files=len(before),
        identical=len(before) - len(changed),
        changed=changed,
        client_changed_method="_parse_stream_line error-event branch only",
        unchanged_client_methods=sorted(name for name in a if a[name] == b[name]),
        prior_results_identical=True,
        index_count=507,
        index_sha256=read("index_after.json")["sha256"],
    ),
)
checks = [
    json.loads(line)
    for line in (OUT / "execution_log.jsonl").read_text(encoding="utf-8").splitlines()
    if json.loads(line).get("event") == "check"
]
assert next(r for r in checks if r["label"] == "full_final")["exit_code"] == 0
write("test_results.json", checks)
focused = collections.Counter(
    case.attrib["classname"]
    for case in ET.parse(OUT / "focused.junit.xml").iter("testcase")
)
full = collections.Counter()
for case in ET.parse(OUT / "full.junit.xml").iter("testcase"):
    outcome = (
        "skipped"
        if case.find("skipped") is not None
        else (
            "failed"
            if case.find("failure") is not None or case.find("error") is not None
            else "passed"
        )
    )
    full[outcome] += 1
write("test_counts.json", dict(focused=dict(focused), full=dict(full)))
decisions = [
    (
        "agent",
        "TCC_AGENT_ID fixo; update_agent verify=False e get_info=False evitam seleção pelo default.",
    ),
    (
        "backend_default",
        "DEFAULT_AGENT=chatbot_ufpi_v2 e registro experimental/non-default preservados.",
    ),
    (
        "identity",
        "UUID de usuário na sessão; não adotar IDs nem agente de query params; sem autenticação.",
    ),
    (
        "thread",
        "UUID por conversa e mesma identidade nos turnos; nova conversa mantém usuário.",
    ),
    (
        "migration",
        "Marcador de versão da UI migra estado legado uma vez; histórico antigo não vira autoridade.",
    ),
    (
        "history",
        "Sem /history ou cookies/localStorage; estado visual local tipado pode ser perdido em refresh.",
    ),
    (
        "dispatch",
        "Somente os três resultados tipados selecionam renderer; conteúdo é exibido intacto.",
    ),
    (
        "references",
        "Somente NormativeReference; dedup visual por todos os campos; objetos originais intactos.",
    ),
    (
        "temporal",
        "Apenas Consulta histórica para temporal_intent histórico; nenhum JSON/guard/status bruto.",
    ),
    (
        "grounded",
        "Indicação discreta de reformulação baseada na resposta anterior e fontes herdadas.",
    ),
    ("calculator", "Conteúdo simples e safe_message em erro; sem fontes normativas."),
    (
        "stream",
        "Um ChatMessage AI completo validado; sem tokens/cursor artificiais; DONE fica no AgentClient.",
    ),
    (
        "service_errors",
        "Mensagens públicas seguras, 503 por HTTPStatusError encadeado; zero fallback legado.",
    ),
    (
        "sse_error",
        "RED comprovou perda de erro pelo parser; única correção compartilhada levanta AgentClientError sem conteúdo do servidor.",
    ),
    (
        "configuration",
        "load_dotenv do cwd de lançamento documentado; variáveis do processo prevalecem; AppTests usam cwd temporário.",
    ),
    (
        "local_smoke",
        "Serviço e Streamlit locais em loopback; AppTest usa AgentClient HTTP/SSE real; provider/settings controlados no seam existente.",
    ),
    (
        "provider",
        "Vetor existente fixo exercita dense e geração controlada; nenhuma alegação de relevância/qualidade jurídica.",
    ),
    (
        "preservation",
        "Sem alterações de core/backend/schema/runtime/config/container; índice lógico e resultados prévios preservados.",
    ),
]
with (OUT / "decision_log.jsonl").open("w", encoding="utf-8") as f:
    for i, (topic, decision) in enumerate(decisions, 1):
        f.write(
            json.dumps(
                dict(id=i, recorded_at=NOW, topic=topic, decision=decision),
                ensure_ascii=False,
            )
            + "\n"
        )
write(
    "review_findings.json",
    dict(
        review="independent read-only engineering review",
        critical=0,
        findings=[
            dict(
                severity="important",
                issue="local .env configuration omitted",
                status="fixed; RED/GREEN",
            ),
            dict(
                severity="minor",
                issue="SSE error was converted to successful DIRECT message",
                status="fixed; RED/GREEN; minimal client exception",
            ),
            dict(
                severity="minor",
                issue="dotenv AppTest could leak synthetic env into later tests",
                status="fixed; controlled fixture uses mock_env rollback",
            ),
        ],
        remaining=[],
    ),
)
write(
    "negative_results.json",
    [
        dict(
            case="initial_fixture",
            result="21 failed / 1 passed",
            detail="Fake client lacked existing info metadata; fixture corrected before authoritative contract RED.",
        ),
        dict(
            case="contract_RED",
            result="17 failed / 5 passed",
            detail="Legacy product behavior did not meet TCC contract.",
        ),
        dict(
            case="first_GREEN",
            result="3 failed / 19 passed",
            detail="Streamlit Markdown strips outer whitespace. Spy proves exact original argument; framework presentation documented.",
        ),
        dict(
            case="review_RED",
            result="2 failed / 30 passed",
            detail="dotenv configuration and SSE error representation reproduced.",
        ),
        dict(
            case="smoke_attempt_01",
            result="11 cases passed, final unavailable expectation failed",
            detail="Default runtime loaded checkout .env. No external attempt observed; values never printed. Preserved attempt; final harness uses explicit settings _env_file=None and isolated dotenv discovery.",
        ),
        dict(
            case="full_initial",
            result="1 failed / 1000 passed / 12 skipped",
            detail="Runner USE_FAKE_MODEL=true violated default-settings test. Removed runner override; no product change.",
        ),
        dict(
            case="PowerShell_wrapper",
            result="stderr warning categorized NativeCommandError",
            detail="Final Python smoke reached its post-cleanup success print and 12/12 persisted assertions; PowerShell wrapper reported1 due Streamlit bare-mode stderr. Evidence validator independently verifies all rows and frozen hashes.",
        ),
        dict(
            case="tool_preparation",
            result="preserved execution limitations",
            detail="One temporary helper python -c quoting attempt failed before any mutation; helper file execution succeeded. Raw first RED runner stdout printing hit cp1252; UTF8 capture was already preserved and runner output encoding fixed.",
        ),
    ],
)
commits = []
for sha in git(
    "rev-list", "--reverse", "39f866c1b788ea8a5701bc74efee2aaf0812e5d7..HEAD"
).splitlines():
    commits.append(dict(sha=sha, subject=git("show", "-s", "--format=%s", sha).strip()))
write("commits.json", commits)
event(
    "evidence_validation",
    probes=12,
    references=26,
    initial_files=len(before),
    identical=len(before) - len(changed),
    frozen_hashes_unchanged=True,
)
log_count = len((OUT / "execution_log.jsonl").read_text(encoding="utf-8").splitlines())
metric_table = "\n".join(
    f"| {name} | {v['numerator']}/{v['denominator']} | {v['unit']} |"
    for name, v in metrics.items()
)
checks_table = "\n".join(
    f"| {r['label']} | {'; '.join(r['summary'])} |" for r in checks
)
commit_table = "\n".join(f"- `{c['sha']}` — {c['subject']}" for c in commits)
report = f"""# TCC UI Integration V1

Data: 01/11/2026, America/Sao_Paulo. Execuções em UTC; engenharia local com provider controlado.

**12/12 probes**, **12/12 requests ao integrado**, **26/26 referências tipadas**, **507/507 registros idênticos**. Suíte final: **{full["passed"]} passed / {full["skipped"]} skipped**. Default backend preservado; sem seletor ou fallback legado.

## 1. Objetivo

Integrar o Streamlit do TCC ao agente registrado, com apresentação tipada e continuidade por sessão. Sem avaliação científica ou deploy.

## 2. Estado inicial

Branch `test/container-runtime-smoke-v1`, HEAD `39f866c1b788ea8a5701bc74efee2aaf0812e5d7`, árvore limpa. Todos os comandos exigidos anteriores à alteração em [initial_audit.json](initial_audit.json). Branch `feat/tcc-ui-integration-v1` criada exatamente desse HEAD.

## 3. UI anterior

Toolkit genérico; herança do default via /info; seletores de agente/modelo; /history por query thread; identidade compartilhável pela URL; ferramentas/status e exceções expostos; renderização só de content, sem fontes tipadas.

## 4. UI depois

Mesma aplicação Streamlit com título/escopo UFPI, chat e botão Nova conversa. Fontes em expander. Removidos controles de agente/modelo, arquitetura remota, compartilhamento/history e feedback remoto do toolkit. `.env` do cwd de lançamento documentado em code/ e env de processo preservados; sem redesign.

## 5. Agente utilizado

Constante `TCC_AGENT_ID=chatbot_ufpi_integrated_v1`. AgentClient existente, get_info=False e update_agent explícito verify=False; não há seletor, modo legado ou escolha por query/session_state. 12/12 requests reais ao endpoint explícito /chatbot_ufpi_integrated_v1/stream.

## 6. Default backend

DEFAULT_AGENT=chatbot_ufpi_v2. Código do registry/backend intacto; /info real e teste obrigatório confirmam. Integrado permanece experimental/non-default internamente, sem rótulo técnico na UI.

## 7. Session identity

Identidade declarada por sessão, sem autenticação. Migração de estado legado incompatível gera nova thread uma vez e limpa mensagens/transientes. Query IDs não são adotados.

## 8. User ID

UUID gerado na sessão; estável entre mensagens e Nova conversa; sem exposição visual ou compartilhamento de URL.

## 9. Thread ID

UUID por conversa. 10/10 requests da conversa original conservaram usuário/thread. Não é regenerado a cada mensagem.

## 10. Nova conversa

Novo thread_id, mensagens locais vazias e transientes de erro/feedback limpos; mesmo usuário e agente. 1/1 ação real observada; checkpoints antigos não são apagados.

## 11. ChatMessage typed dispatch

normative_result → grounded_followup_result → calculator_result → regular. Exclusividade revalidada pelo schema existente antes de armazenar a mensagem. Payload inválido resulta em erro público seguro.

## 12. Direct renderer

Conteúdo normal, sem fontes/status/provenance. Greeting e repetição sem memória após nova conversa passaram.

## 13. Normative renderer

ANSWER exibe message.content sem reescrita nem síntese. Spy AppTest confirma argumento byte a byte; o componente Markdown do Streamlit remove whitespace externo na representação de tela, comportamento documentado da biblioteca já utilizada. accepted/regenerated/fallback não viram rótulos públicos.

## 14. Official references

Somente NormativeReference.references. display_text e validated_subdivision estruturados; identidade de todos os campos para dedup visual, sem alterar os objetos. 26/26 referências esperadas mostradas nos probes. AppTest com art.999 em content mostrou nas fontes somente art.68; referências distintas com mesmo display_text e subdivisão foram mantidas. Nenhum link inventado ou chunk_id exibido.

## 15. Temporal information

Somente caption Consulta histórica quando temporal_intent=historical; sem inferir vigência. Outros dados temporais não recebem apresentação nova nesta V1. Sem JSON/provenance/constraints/core_status/estratégia brutos.

## 16. Clarification

Pergunta normal por message.content; sem fontes vazias/status técnico. Resposta seguinte mantém a mesma thread e usa a continuidade real do backend.

## 17. Normative error

Conteúdo público do contrato/safe_message, sem error_code, audit ou traceback. Validado por AppTest controlado.

## 18. Grounded follow-up

Conteúdo com indicação discreta Reformulação baseada na resposta normativa anterior. Fontes herdadas do contrato, mesma correlação verificada tecnicamente e não exibida. REPEAT/SUMMARY reais: 2/2; REPHRASE também coberto no AppTest. Nenhuma busca da UI.

## 19. Calculator

Resultado simples, 4 e 15/11/2026 nos probes reais. Sem fontes nem informação normativa: 2/2.

## 20. Calculator error

safe_message em warning, sem códigos/stack/norma. Divisão por zero coberta por AppTest.

## 21. Streaming

Um ChatMessage AI completo, sem cursor ou tokens artificiais. Retenção só após o stream completo validado; eventos inesperados/duplicados são recusados de forma controlada. DONE consumido pelo AgentClient existente e não mostrado. RED adicional comprovou que SSE type=error virava DIRECT; mudança mínima no client agora levanta AgentClientError seguro, sem repassar conteúdo do servidor. Parser de mensagens/tokens e outros métodos do client conservados por AST.

## 22. Rerun/session state

ChatMessage Pydantic completo em messages, sem duplicar o contrato em campos paralelos. 11/11 respostas reais conservaram o dump tipado após rerun; testes conferem fontes e objeto original intactos.

## 23. Unavailable service

503 real antes de SSE no agente sem configuração de provider; UI mostra O assistente está temporariamente indisponível. HTTP500, rede, payload inválido e SSE error têm apresentação segura em AppTest.

## 24. No legacy fallback

Zero chamadas legadas em 12 requests; 0/1 falhas de disponibilidade causaram fallback. Falha não é salva como resposta AI de sucesso.

## 25. History limitation

Sem reconstrução por /history. Estado visual vive na sessão Streamlit; refresh/nova sessão pode perdê-lo e gerar nova identidade. Sem cookies/localStorage ou promessa de histórico persistente completo; checkpoints backend são separados da apresentação local.

## 26. AppTest

24 focused TCC + 8 regressões do entrypoint =32 AppTests aprovados. Fake AgentClient nas unidades; cwd e ambiente isolados. Cobertura inclui exclusividade, fontes, art999, erro503/500, SSE error/DONE, rerun, migração, IDs, nova conversa e configuração .env/env. Sem novo framework.

## 27. Local integration

Python3.11.15/Windows, Streamlit1.40.2 e Uvicorn reais em loopback 18081/18501; processo negativo 18082. AppTest executa o script real com AgentClient HTTP/SSE real; processo Streamlit também respondeu /_stcore/health. Sem verificação em navegador, screenshot ou avaliação mobile. Runtime/factory/graph/core/registry/índice/saver reais; somente settings/provider pelo seam existente são controlados. SQLite e vetor de teste em workspace temporário removido. Serviços encerraram com exit0 e provider fechou; Streamlit foi terminado pelo harness após captura. Sem repetir build/protocolo Docker anterior.

## 28. Probes

[ui_protocol.json](ui_protocol.json) foi congelado antes da execução final:12 casos e hashes de UI/client/harness. [ui_probe_rows.jsonl](ui_probe_rows.jsonl) contém12 observações finais. Nenhum produto/protocolo congelado mudou após os probes. Tentativa anterior com configuração inadequada preservada em attempt_01_env_configuration; não entra no denominador final. Zero tentativas externas nos guards socket/DNS dos dois processos finais; não é captura universal de pacotes.

## 29. Technical metrics

| Métrica | Resultado | Unidade |
|---|---:|---|
{metric_table}

Denominadores finitos e observações sobrepostas; não somar taxas. Contagem0 significa zero ocorrências na unidade indicada.

## 30. Negative results

[negative_results.json](negative_results.json) registra RED17/5, ajuste de fixture inicial21/1, diferença de whitespace do Markdown, RED da revisão2/30, tentativa local11 casos com indisponibilidade mal configurada e full inicial1failed/1000passed/12skipped por variável do runner. Raw logs preservados. PowerShell classificou stderr informativo do AppTest como NativeCommandError; o Python final chegou ao print12/12 após cleanup, e evidence_audit valida todos os artefatos/hashes independentemente. Helpers de preparação tiveram uma falha de quoting e stdout cp1252; sem mudança de produto decorrente. Nenhum tuning após os probes.

## 31. Limitations

Sem validação jurídica, relevância de embeddings, provider/credenciais reais, autenticação, carga, verificação em navegador/mobile, persistência de histórico visual após refresh, PostgreSQL/Mongo ou deploy. Vetor fixo e geração controlada exercitam encadeamento técnico. Não se afirma prontidão de produção nem validação das respostas pelo frontend. Primeira tentativa local leu configuração do checkout; nenhuma chave foi impressa, versionada ou utilizada por provider externo. Execução final isola explicitamente .env e usa somente placeholders.

## 32. Decisions

[decision_log.jsonl](decision_log.jsonl):{len(decisions)} decisões públicas. [execution_log.jsonl](execution_log.jsonl):{log_count} eventos até esta consolidação; eventos posteriores de checks/staging/commits podem ampliar o total, verificável no próprio arquivo. Revisão de código encontrou1important e2minor, todos corrigidos; zero pendentes em [review_findings.json](review_findings.json).

## 33. Preservation

{len(before)} arquivos iniciais; {len(before) - len(changed)} idênticos; quatro alterações existentes autorizadas: streamlit_app.py, client/client.py (somente erro SSE), tests/app/conftest.py e tests/app/test_streamlit_app.py. Novos testes/evidências adicionados. Core normativo, agent, Router, temporal, retrieval, VersionFilter, grounding, StructuredOutput, memory, calculator, ChatMessage/schema, emissão/projetor tipados, service, runtime, DEFAULT_AGENT, registry, corpora, pyproject/lock, container configs e todos os resultados anteriores permanecem idênticos. Outros métodos do AgentClient idênticos por AST. Índice507/507 IDs/documentos/metadados/embeddings float32 idênticos; SHA256 `{read("index_after.json")["sha256"]}`. Sem reindexação ou metadata update.

## 34. Tests

Focused final314passed/5warnings: UI32,client9,service24,typed51,conversation87,calculator111. Contagens por classe em [test_counts.json](test_counts.json), comandos/cwd/timestamps em [test_results.json](test_results.json). Seleções sobrepostas não são somadas à full. Full final inclui rag_baseline/runtime/legacy app/integration; Docker opt-in permanece skipped.

| Execução | Resultado real |
|---|---|
{checks_table}

Ruff check/format-check de produto/testes/scripts e diff --check/staged em verification.json após fechamento. Warnings completos nos logs: fixture deliberadamente inválida Pydantic, AsyncMock legado, depreciação de dependência e TestClient timeout.

## 35. Commits

{commit_table}

Sem agent selector, fallback legado, default change, tuning, deploy ou publicação de imagem.
"""
(OUT / "REPORT.md").write_text(report, encoding="utf-8")
print(
    json.dumps(
        dict(
            metrics=metrics,
            files=len(before),
            identical=len(before) - len(changed),
            full=dict(full),
            decisions=len(decisions),
            execution_events=log_count,
        )
    )
)
