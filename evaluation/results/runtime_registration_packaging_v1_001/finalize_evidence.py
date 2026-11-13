"""Assemble public engineering evidence from actual commands and frozen probes."""

import ast
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
BASE = "706bd7cc5e7f333032c7de7b58ed89dc41c09bd0"


def write(name, value):
    (OUT / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def definitions(source):
    return {
        n.name: ast.dump(n)
        for n in ast.parse(source).body
        if isinstance(n, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }


def main():
    results = json.loads((OUT / "test_results.json").read_text(encoding="utf-8"))
    probes = json.loads((OUT / "local_probes.json").read_text(encoding="utf-8"))
    preservation = json.loads((OUT / "preservation.json").read_text(encoding="utf-8"))
    verification = json.loads((OUT / "verification.json").read_text(encoding="utf-8"))
    protocol = json.loads((OUT / "technical_protocol.json").read_text(encoding="utf-8"))
    packaging = json.loads((OUT / "packaging_audit.json").read_text(encoding="utf-8"))
    assert results[-1]["selection"] == "full" and all(r["exit_code"] == 0 for r in results)
    assert all(v["exit_code"] == 0 for v in verification.values())
    assert probes["all_hashes_unchanged"] and probes["external_call_attempts"] == 0
    for path, expected in protocol["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    checks = {}
    for path, names in {
        "code/src/schema/schema.py": ["ChatMessage", "UserInput", "StreamInput", "ServiceMetadata"],
        "code/src/service/service.py": [
            "verify_bearer",
            "_handle_input",
            "_create_ai_message",
            "_sse_response_example",
            "feedback",
            "history",
            "info",
        ],
    }.items():
        before = definitions(
            subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT).decode()
        )
        after = definitions((ROOT / path).read_text(encoding="utf-8"))
        checks.update({f"{path}:{name}": before[name] == after[name] for name in names})
    checks["DEFAULT_AGENT"] = 'DEFAULT_AGENT = "chatbot_ufpi_v2"' in (
        ROOT / "code/src/agents/agents.py"
    ).read_text(encoding="utf-8")
    before_hashes = json.loads((OUT / "preservation_before.json").read_text(encoding="utf-8"))[
        "files"
    ]
    checks["langgraph_unchanged"] = (
        hashlib.sha256((ROOT / "code/langgraph.json").read_bytes()).hexdigest()
        == before_hashes["code/langgraph.json"]
    )
    # Byte-level preservation is stronger than these AST checks and is recorded separately.
    assert all(checks.values())
    write("contract_checks.json", checks)
    write(
        "review_findings.json",
        dict(
            mode="independent_read_only_review_with_author_reproduction",
            findings=[
                dict(
                    severity="P2",
                    topic="partial_chroma_acquisition",
                    observation="PersistentClient can cache a new System before a failed native startup; the unleased partial system previously survived.",
                    reproduction="Corrupt temporary chroma.sqlite3: assertion failed; stock Rust stop also raised AttributeError because bindings were never assigned.",
                    correction="Protect acquisition; stop initialized components and remove only newly owned partial system. Preserve borrowed systems; skip uninitialized Rust bindings only in partial cleanup.",
                    verification="tdd_review_red_confirmed.txt -> tdd_review_green.txt, 37 focused passed; full suite green",
                )
            ],
            unresolved_important_or_critical_in_inspected_scope=0,
            no_second_review_of_fixes=True,
            limitations=[
                "No Docker/container execution",
                "No live provider/Postgres/Mongo",
                "Single application lifespan per process; no overlapping-lifespan guarantee",
            ],
        ),
    )
    events = [
        (
            "audit",
            f"Requested git audit executed before code changes: source branch feat/calculator-tool-routing-v1, clean, HEAD {BASE}.",
        ),
        ("branch", "Created feat/runtime-registration-packaging-v1 from audited HEAD."),
        ("preservation", "798 initial tracked files and 507-record logical snapshot captured."),
        ("baseline", "Existing service selection: 24 passed, 3 legacy warnings."),
        ("RED", "Initial new selection: 14 failed, 1 passed, 16 missing-component fixture errors."),
        ("commit", "3610c0c test: define integrated runtime registration boundaries"),
        (
            "factory",
            "Explicit context-managed assembly added, borrowing saver and reusing core/facade/policy/calculator.",
        ),
        (
            "registry",
            "Four legacy IDs/descriptions preserved; integrated registered experimental/non-default with lazy graph imports.",
        ),
        (
            "lifecycle",
            "Owned/borrowed Chroma leases, provider optional aclose, application saver/store ownership.",
        ),
        (
            "availability",
            "Expected integrated asset/config failures -> unavailable503; unknown404 beforeSSE; default remains legacy.",
        ),
        (
            "health",
            "Local readiness added; process status retained; no remote Langfuse auth check.",
        ),
        (
            "harness_findings",
            "Initial GREEN attempt: 4 failed/27 passed from missing subprocess PYTHONPATH, fake provider model mismatch and canonical resolver whitespace. Fixtures corrected without core changes.",
        ),
        (
            "integration_GREEN",
            "64 passed for new selection plus legacy service and calculator transport.",
        ),
        (
            "lifecycle_GREEN",
            "36 new tests passed, including reopen, partial failure, shared leases and network/Supabase block.",
        ),
        (
            "review",
            "Independent read-only review identified partial Chroma startup ownership leak.",
        ),
        (
            "review_RED",
            "Actual corrupt temporary index reproduced cache leak; cleaned RED confirms 1 failure. Original capture also preserves missing native-bindings cleanup exception.",
        ),
        ("review_GREEN", "Acquisition cleanup fixed; 37 focused passed."),
        (
            "registry_transition",
            "Old assertion AGENT not in registry failed as expected; changed only registry expectation to experimental presence/default preserved.",
        ),
        (
            "packaging",
            "Service root context/layout, six packages, entrypoint and four documentary assets; client image shared-contract layout; Streamlit source untouched.",
        ),
        (
            "docker",
            "Docker CLI absent. No build or container smoke; static packaging and simulated layout import performed.",
        ),
        (
            "freeze",
            "15 groups and 18 source/harness/audit hashes frozen before the full local probe run.",
        ),
        (
            "probes",
            "One complete run, 25 journaled rows, 0 external attempts, frozen hashes unchanged.",
        ),
        (
            "concurrency",
            "Registered runtime served concurrent identities with normative metadata_exact and calculator operations.",
        ),
        (
            "shutdown",
            "2 providers, 2 owned Chroma systems and 5 SQLite savers closed, 9/9 observations.",
        ),
        ("verification", "975 passed/12 skipped full suite; all declared selections passed."),
        (
            "lint",
            "Initial evidence format check overlapped script preparation and reported unformatted files. Final static checks repeated after formatting; frozen sources/harness unchanged.",
        ),
        (
            "preservation_final",
            "788/798 initial files identical; ten authorized existing files changed; 507-record logical snapshot identical.",
        ),
        (
            "commit",
            "7be35db0999240d111ddf430fe108b09afd072a9 feat: register integrated agent runtime",
        ),
        (
            "commit",
            "fa567262ab2dabe7ec59f09796416c6888e8cbb3 build: package integrated normative agent runtime",
        ),
        (
            "evidence",
            "Report/manifests prepared for final local evidence commit; final SHA omitted to avoid self-reference.",
        ),
    ]
    now = datetime.now(UTC).isoformat()
    (OUT / "execution_log.jsonl").write_bytes(
        b"".join(
            (
                json.dumps(dict(id=i, recorded_at=now, event=e, observation=o), ensure_ascii=False)
                + "\n"
            ).encode()
            for i, (e, o) in enumerate(events, 1)
        )
    )
    metric_table = "\n".join(f"| {name} | {n}/{d} |" for name, (n, d) in probes["metrics"].items())
    test_table = "\n".join(f"| {r['selection']} | {r['summary']} |" for r in results)
    changed = "\n".join(f"- `{r['path']}`" for r in preservation["authorized_changes"])
    sections = [
        (
            "Objetivo",
            "Registrar e empacotar o integrado como experimental/non-default no runtime normal, com lifecycle e readiness explícitos. Sem UI nova, autenticação, deploy, tuning, calculator/memória novas ou experimento científico.",
        ),
        (
            "Estado inicial",
            f"Branch `feat/calculator-tool-routing-v1`, HEAD `{BASE}`, árvore limpa na inspeção inicial. Status, branch, HEAD, log -15, diff, diff --cached e diff --stat foram executados antes de mudar código. A branch `feat/runtime-registration-packaging-v1` nasceu desse HEAD. [initial_audit.json](initial_audit.json) distingue a observação da branch-fonte da captura posterior à criação da pasta de evidência.",
        ),
        (
            "Arquitetura antes",
            "Registry com quatro grafos importados antecipadamente, além de agentes não registrados e modelo de supervisor. Lifespan atribuía saver/store a grafos prontos. O integrado existia apenas por builder/injeção; Dockerfile.service não copiava rag_baseline nem os assets documentais necessários.",
        ),
        (
            "Arquitetura depois",
            "Registry import-safe → lifespan das factories existentes de saver/store → assembly do integrado uma vez → get_agent geral → invoke/stream tipados. Falha esperada de dependência experimental não derruba legado; erro crítico de banco/store ou programação continua interrompendo startup.",
        ),
        (
            "Runtime factory",
            "[integrated_runtime.py](../../../code/src/rag_baseline/integrated_runtime.py) contém build_integrated_agent_runtime e IntegratedAgentRuntime. Monta settings, registry validado, índice existente, RagService, Router V1, VersionFilter, facade, stamp, transformer e grafo. O builder anterior constrói a calculator; não há implementação duplicada. Saver real é recebido do lifespan/factory existente, com um único owner.",
        ),
        (
            "Registration",
            "Extensão mínima de Agent com import_path e runtime_factory, mantendo graph pronto para compatibilidade. Não há special-case do ID em invoke/stream; o contrato geral resolve agentes. AgentInfo ganha experimental, available e unavailable_reason opcionais/aditivos. Os quatro IDs/descrições anteriores permanecem.",
        ),
        (
            "Agent ID",
            "`chatbot_ufpi_integrated_v1`, sem aliases. Registrado publicamente nesta etapa, experimental e chamado por seleção explícita.",
        ),
        (
            "Default preservation",
            "DEFAULT_AGENT antes/depois = `chatbot_ufpi_v2`. Rotas sem agent_id permanecem vinculadas a esse default. Verificação rígida e probes: 5/5 snapshots de /info conservaram o default.",
        ),
        (
            "Lazy/eager behavior",
            "Importar registry/factory não abre Chroma, provider, banco, registry documental ou fingerprint. Grafos legados são carregados sob demanda e recebem as dependências no lifespan. O integrado é montado no startup e reutilizado por request. Supervisor não registrado deixa de ser importado pelo registry.",
        ),
        (
            "Resource ownership",
            "Aplicação: saver/store e respectivos context managers. Runtime: graph, provider closable e leases Chroma. OpenRouter existente não mantém httpx client permanente: cada request possui seu contexto. Transformer sem provider não tem recurso externo. Sistema Chroma pré-existente é borrowed e permanece do criador. O adapter usa APIs internas estreitas da versão instalada porque não há Client.close público; upgrades exigem revisão.",
        ),
        (
            "Startup",
            "Factories existentes inicializam saver/store; registry carrega grafos legados e entra no context manager integrado. Sem provider/HTTP, embeddings, retrieval de pergunta ou geração no startup observado. Leitura local de arquivos/count/get para validar e fingerprint é permitida. Um assembly por lifespan, não por request. Dois startups válidos e três indisponibilidades configuradas foram observados.",
        ),
        (
            "Shutdown",
            "AsyncExitStack fecha provider e leases; aplicação fecha saver/store. Falhas depois da aquisição também limpam recursos. Chroma parcialmente iniciado é limpo sem parar sistemas borrowed; Rust sem bindings é tratado apenas nesse caminho parcial. Observações: provider 2/2, Chroma owned 2/2, SQLite saver 5/5, total 9/9. Store SQLite é InMemoryStore, sem conexão a fechar.",
        ),
        (
            "Registry",
            "Quatro entradas legadas: chatbot_ufpi_agentic, chatbot_ufpi, chatbot_ufpi_v2 e chatbot_generic. Agente desconhecido retorna 404; experimental conhecido e indisponível retorna 503 com código seguro, inclusive antes dos headers SSE. Sem fallback silencioso para outro agente. /info conserva a lista, ampliando metadata aditivamente.",
        ),
        (
            "Chroma/index",
            "Adapter reutiliza métodos de ChromaVectorStore e abre somente get_collection, desviando do get_or_create do construtor legado. Exige diretório/database existentes; não cria índice ausente ou collection faltante. Bind persistente no container, fora da imagem. Chroma pode fazer housekeeping local no startup; a fronteira protegida mede igualdade lógica de IDs/documentos/metadados/embeddings.",
        ),
        (
            "Normative registry",
            "NormativeRegistry.load valida schema, relações e evidências documentais, sem aceitar registry parcial. Default no layout do checkout/imagem; override opcional NORMATIVE_REGISTRY_PATH. Registry inválido ou evidência ausente produz registry_invalid, sem expor paths/exceção/chaves ao client.",
        ),
        (
            "Memory stamp",
            "build_memory_stamp existente executa uma vez por build após a validação. Corpus/registry fingerprints e versões conservam o contrato anterior. Requests e health não recalculam o fingerprint. Restart é necessário após mudanças nos assets/índice; readiness não monitora equivalência semântica ou deriva do corpus.",
        ),
        (
            "Checkpointer",
            "initialize_database/initialize_store e backends existentes permanecem intactos. Default do código: SQLite; Compose de produção mantém PostgreSQL como antes. Runtime borrows o saver, sem conectar outro. SQLite em arquivo temporário foi fechado/reaberto; Postgres/Mongo não foram iniciados nem validados ao vivo.",
        ),
        (
            "Provider config",
            "BaselineSettings e perfil duas-regulacoes existentes; OpenRouter, embedding/modelo de geração, temperatura, top_k e Router V1 preservados. Campo model legado do request não substitui modelos internos. Chave obrigatória é validada por presença, sem imprimir valor ou testar credencial remotamente. Todos os providers dos probes são controlados. Transformer usa fallback determinístico para o source answer.",
        ),
        (
            "Readiness",
            "Endpoint `/agents/{agent_id}/readiness`. Checa registro, configuração, registry/stamp montados, saver inicializado, calculator/facade disponíveis e count/acesso local ao índice. Não confunde configured com connected. Flag de registry/stamp reflete startup; acesso/count do índice é consultado localmente. Resultados esperados de cinco snapshots: 5/5, incluindo três falhas explícitas.",
        ),
        (
            "Health",
            "`/health` conserva status do processo e adiciona integrated_agent. Processo ok não implica agente pronto. Health/readiness não chamam OpenRouter/LLM ou HTTP; a antiga auth_check remota do Langfuse foi substituída por estado de configuração, sem alegar conectividade.",
        ),
        (
            "/info",
            "Lista o integrado experimental e sua disponibilidade/reason code, sem removê-lo quando faltam assets. Default e estrutura de lista anteriores permanecem. Legacy registry preservation 4/4 entradas; mensagens de erro não expõem chave, envelope privado ou storage key.",
        ),
        (
            "Invoke registered",
            "POST `/chatbot_ufpi_integrated_v1/invoke` usa o registry/factory/lifespan reais, sem substituir get_agent, facade ou graph no harness. Somente settings/provider controlado e path SQLite são configurados em dependências confiáveis da aplicação. AgentClient restaura modelos tipados pelo schema compartilhado.",
        ),
        (
            "Stream registered",
            "POST `/chatbot_ufpi_integrated_v1/stream` usa o mesmo runtime e transporte existente. Um message completo + DONE para emissão integrada, inclusive stream_tokens=true. /stream desconhecido/indisponível recebe erro HTTP explícito antes dos headers. Testes/probes usam ASGI em processo, sem servidor exposto.",
        ),
        (
            "Direct",
            "Oi no agente registrado produz resposta direta e nenhum dos três resultados tipados; não chama provider normativo.",
        ),
        (
            "Calculator",
            "2+2 no agente registrado produz CalculatorToolResult e zero provider. ERROR 1/0 durante pending preserva memória/pendência. Parser/tool/contratos e semântica da calculator permanecem byte a byte iguais.",
        ),
        (
            "Normative",
            "Queries passam por Router V1, facade, estratégias e núcleo anteriores. Há metadata_exact real/controlado, além de dense para perguntas temáticas. Providers e vetores 2D de dez chunks temporários são fixtures técnicas; não medem qualidade jurídica ou relevância do índice completo de 507 registros.",
        ),
        (
            "Memory continuity",
            "Mesma identidade mantém envelope ao transformar/calcular; mudança de domínio cria operação nova; clarification retorna UUID/pergunta originais sem campo clarification manual. Após fechar/reabrir o lifespan/SQLite, repita recupera o último ANSWER sem nova rota/provider. Seis observações de continuidade: 6/6. /history permanece legado/default, sem reconstrução dos resultados integrados privados.",
        ),
        (
            "Isolation",
            "Mesmo thread público e usuários diferentes não compartilham authority. Requests concorrentes distintos para normativa/calculator ficaram isolados: 2/2 grupos. Identidade segue declarada pelo cliente; nenhuma autenticação/autorizaçao adicionada. Sem promessa de turnos simultâneos da mesma identidade ou segurança distribuída.",
        ),
        (
            "Typed transport",
            "normative_result, grounded_followup_result e calculator_result continuam exclusivos, com conteúdo exato. ChatMessage e projetor tipado anteriores são preservados. AgentClient não mudou. 12/12 mensagens tipadas conservadas e 0/25 vazamentos de campos privados nos registros públicos avaliados.",
        ),
        (
            "Dockerfile",
            "Dockerfile.service passa a buildar com contexto da raiz; layout /app/code/src preserva paths package-relative. Copia seis pacotes, entrypoint e quatro assets documentais específicos. Não copia evaluation/results, datasets, logs, .env ou índice. Imagem não foi construída neste ambiente.",
        ),
        (
            "Runtime assets",
            "Lista derivada da validação do registry: data/normative_registry.json, graduacao_setor_v2.json, pos_graduacao_setor_v2.json e 1056_2026_temporal_v1.json. Não são datasets de experimento; a validação documental existente lê esses arquivos. Arquivos fonte permanecem idênticos.",
        ),
        (
            "Chroma packaging",
            "Compose monta `code/.local/chroma` em `/app/index` e configura CHROMA_PERSIST_DIR absoluto. Índice é persistent data, não code asset; não é embutido na imagem nem gerado no startup. Mount é writable por requisitos de housekeeping do Chroma, sem chamadas de indexação da aplicação.",
        ),
        (
            "Paths Windows/Linux",
            "Index/registry relativos ancorados em code/; testados a partir de outro cwd. Docker usa caminhos POSIX e hierarquia compatível com versioning.py. Factory SQLite anterior conserva resolução de path relativo por cwd; use path absoluto fora de code/. Nenhum path Windows hardcoded na implementação/packaging. Linux real de container não foi executado.",
        ),
        (
            "langgraph.json",
            "Permanece byte a byte igual: Python3.12 e research_assistant. É entrypoint separado do registry da API. Não muda graph principal/default desta configuração.",
        ),
        (
            "Python/dependencies",
            f"Execução local: {packaging['python_executed'].splitlines()[0]}. Docker3.12.3 e LangGraph3.12 mantidos. Pyproject/lock intactos; versões instaladas em packaging_audit.json. Nenhuma instalação/atualização necessária. Compatibilidade Linux3.12 é inspecionada/configurada, não demonstrada por execução.",
        ),
        (
            "Container build",
            "Não executado: Docker CLI não encontrado no PATH nem no local convencional inspecionado. Não se instalou Docker nem se publicou imagem. packaging_audit.json registra indisponibilidade; a checagem de completeness é estática/contexto, não prova de build.",
        ),
        (
            "Container smoke",
            "Não executado, pelo mesmo motivo. Smoke alternativo copia pacotes/assets para filesystem temporário com layout da imagem, muda cwd e importa registry/service, validando registry/evidências: 1/1. Não equivale a container/startup Linux real. Dockerfile.app também passa a copiar os contratos rag_baseline no layout profundo; fonte Streamlit permanece intacta.",
        ),
        (
            "Probes",
            "[technical_protocol.json](technical_protocol.json) congelou 15 grupos e 18 hashes antes da única execução integral. [local_probes.py](local_probes.py) bloqueia socket/HTTP externos e permite somente ASGI local exato; usa factories existentes, provider controlado e journal imediato. [probe_rows.jsonl](probe_rows.jsonl) tem 25 observações. Nenhum código/harness/expectativa congelado mudou após execução. Startup external calls 0/5 startups; nenhuma tentativa externa no conjunto observado.",
        ),
        (
            "Technical metrics",
            "Denominadores finitos e unidades: builds válidos 2; snapshots de disponibilidade 2/default5/readiness5; quatro entradas legadas únicas; mensagens tipadas12; continuidade6; grupos de isolamento2; recursos com fechamento9; configurações recusadas3; entradas declaradas de packaging11; import smoke1. Não somar métricas sobrepostas.\n\n| Métrica | Numerador/denominador |\n|---|---:|\n"
            + metric_table,
        ),
        (
            "Negative results",
            "RED inicial: 14 failed, 1 passed, 16 erros de fixture por ausência do componente. Primeiro GREEN: 4 failed/27 passed por fixtures de subprocess/modelo/pergunta canônica; corrigidas sem mudar núcleo/resolver. Revisão reproduziu vazamento de sistema Chroma parcial com SQLite corrompido, inclusive stop nativo sem bindings; corrigido por regressão RED→GREEN. Um teste antigo de ausência no registry falhou legitimamente e teve a expectativa atualizada para esta etapa. Capturas tdd_*.txt preservam resultados. Check de format de scripts ocorreu durante sua preparação; captura inicial foi preservada e os checks estáticos repetidos depois. Não houve tuning seletivo após freeze.",
        ),
        (
            "Limitations",
            "Sem Docker/container real, Python3.12 executado, Postgres/Mongo ao vivo, API real, carga, deployment ou validação de credenciais. Adapter Chroma depende de API privada da versão instalada. Registry global pressupõe uma lifespan de aplicação por processo; overlapping lifespans não são suportadas. Readiness não certifica semântica do corpus, modelo ou qualidade jurídica. As limitações científicas anteriores, inclusive o experimento dos 44 casos, permanecem; nenhum novo experimento ou tuning foi realizado.",
        ),
        (
            "Decisions",
            "[decision_log.jsonl](decision_log.jsonl) tem 22 decisões públicas. [execution_log.jsonl](execution_log.jsonl) tem 30 eventos observáveis; recorded_at é consolidação, enquanto testes/protocolo contêm timestamps de execução. [runtime_audit.json](runtime_audit.json), [packaging_audit.json](packaging_audit.json) e [review_findings.json](review_findings.json) preservam escolhas/achados. A correção da revisão foi verificada por regressões e suíte completa; não houve segunda revisão.",
        ),
        (
            "Preservation",
            f"[preservation_before.json](preservation_before.json) e [preservation.json](preservation.json): **798 arquivos iniciais, 788 idênticos e dez mudanças autorizadas**:\n\n{changed}\n\nCore normativo, RouterV1/V2, Temporal Intent, dense/metadata_exact/vector_filtered, VersionFilter, grounding, StructuredOutputV2, NormativeToolResult, facade/tool, agent builder, conversation policy/memory/transformer, calculator, ChatMessage/projetor, client, registry normativo, Streamlit, pyproject/lock, langgraph.json e resultados anteriores permanecem intactos. Registro público muda intencionalmente; default/IDs/descrições legados são preservados. [contract_checks.json](contract_checks.json) confirma AST de contratos/funções preservados dentro dos arquivos alterados.\n\n**507 IDs/documentos/metadados/embeddings float32 idênticos**, snapshot `{preservation['index_sha256']}`. Sem reindexação, metadata update ou re-embedding. .gitattributes -text/CR aplica-se somente à pasta nova de evidências. Manifests distinguem working files e blobs Git quando finais de linha diferem.",
        ),
        (
            "Tests",
            "[test_results.json](test_results.json) e stdout pytest registram comandos, cwd, timestamps, status e contagens reais. Seleções sobrepostas não são somáveis.\n\n| Seleção | Resultado real |\n|---|---|\n"
            + test_table
            + "\n\nRuff check/format-check de produto/testes e scripts de evidência aprovados; git diff --check staged/unstaged aprovados, conforme [verification.json](verification.json). Warnings completos são legados: Pydantic de dependência, AsyncMock/client e timeout TestClient. Docker opt-in e skips anteriores permanecem.",
        ),
        (
            "Commits",
            "1. `3610c0c` — test: define integrated runtime registration boundaries.\n2. `7be35db0999240d111ddf430fe108b09afd072a9` — feat: register integrated agent runtime.\n3. `fa567262ab2dabe7ec59f09796416c6888e8cbb3` — build: package integrated normative agent runtime.\n4. Evidências — test: verify registered runtime and packaging.\n\nSem deploy, autenticação nova, Supabase no integrado, reindexação, tuningV2 ou API real nos probes. Default e fonte Streamlit intactos. Esta entrega termina no runtime/packaging experimental, sem iniciar a próxima etapa.",
        ),
    ]
    assert len(sections) == 45
    intro = """# Runtime Registration & Packaging V1

Data: 01/11/2026, America/Sao_Paulo, conforme contexto atualizado do cliente. Verificação local de engenharia com providers controlados; timestamps de execução nos artefatos estão em UTC.

O integrado foi registrado como **experimental/non-default** e construído pelo runtime normal nos dois startups válidos observados (2/2). Default preservado (5/5), transporte tipado (12/12), continuidade (6/6), isolamento (2/2) e fechamento de recursos (9/9). Zero chamadas externas em cinco startups. A suíte completa passou com **975 passed / 12 skipped**; **507 registros** permaneceram idênticos. Docker indisponível: completeness estático 11/11 e import smoke em layout simulado 1/1 não demonstram build/container Linux ou prontidão para produção.

"""
    report = (
        intro
        + "\n\n".join(f"## {i}. {title}\n\n{body}" for i, (title, body) in enumerate(sections, 1))
        + "\n"
    )
    (OUT / "REPORT.md").write_bytes(report.encode("utf-8"))
    paths = sorted(
        set(protocol["hashes"]) | {p.relative_to(ROOT).as_posix() for p in OUT.glob("*.py")}
    )
    manifest = []
    for path in paths:
        try:
            blob = subprocess.check_output(
                ["git", "show", f"HEAD:{path}"], cwd=ROOT, stderr=subprocess.DEVNULL
            )
            blob_hash = hashlib.sha256(blob).hexdigest()
        except subprocess.CalledProcessError:
            blob_hash = None
        manifest.append(
            dict(
                path=path,
                working_sha256=hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                head_blob_sha256=blob_hash,
            )
        )
    write(
        "manifest.json",
        dict(base=BASE, implementation_packaging_head=git("rev-parse", "HEAD"), files=manifest),
    )
    artifacts = [
        dict(
            path=p.relative_to(OUT).as_posix(),
            bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        for p in sorted(OUT.rglob("*"))
        if p.is_file() and p.name != "ARTIFACTS.json" and "__pycache__" not in p.parts
    ]
    write("ARTIFACTS.json", dict(excludes_self=True, files=artifacts))
    print(
        "Finalized 45 report sections,",
        len(events),
        "execution events and",
        len(artifacts),
        "artifacts",
    )


if __name__ == "__main__":
    main()
