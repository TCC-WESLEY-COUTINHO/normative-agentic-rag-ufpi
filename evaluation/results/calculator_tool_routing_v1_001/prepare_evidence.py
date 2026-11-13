"""Prepare declared engineering cases and decisions, before freezing probes."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def prepare():
    cases = []

    def case(
        message,
        action,
        kind=None,
        status=None,
        content=None,
        error=None,
        purpose="routing",
        notes="",
    ):
        cases.append(
            dict(
                id=f"case_{len(cases) + 1:03d}",
                message=message,
                expected_action=action,
                expected_operation_kind=kind,
                expected_status=status,
                expected_content=content,
                expected_error_code=error,
                expected_facade_calls=int(action == "NORMATIVE_RAG"),
                expected_calculator_calls=int(action == "CALCULATOR"),
                purpose=purpose,
                notes=notes,
            )
        )

    for text, output in [
        ("2+2", "4"),
        ("Quanto é 15 * 4?", "60"),
        ("Calcule 100 / 4.", "25"),
        ("2*(3+4)", "14"),
        ("-5+2", "-3"),
        ("1.5+2.5", "4"),
        ("0.1+0.2", "0.3"),
        ("10/4", "2.5"),
    ]:
        case(text, "CALCULATOR", "ARITHMETIC", "ANSWER", output, purpose="supported_math")
    for text, output in [
        ("Adicione 10 dias corridos a 05/11/2026.", "15/11/2026"),
        ("Some 10 dias corridos a 2026-11-05", "15/11/2026"),
        ("Subtraia 5 dias corridos de 05/11/2026", "31/10/2026"),
        ("1 dias depois de 28/02/2028", "29/02/2028"),
        ("1 dias depois de 28/02/2027", "01/03/2027"),
        ("5 dias antes de 05/11/2026", "31/10/2026"),
    ]:
        case(text, "CALCULATOR", "DATE_OFFSET", "ANSWER", output, purpose="supported_math")
    for text, days in [
        ("Quantos dias existem entre 05/11/2026 e 15/11/2026?", 10),
        ("Quantos dias entre 15/11/2026 e 05/11/2026?", -10),
    ]:
        case(
            text,
            "CALCULATOR",
            "DATE_DIFFERENCE",
            "ANSWER",
            f"Diferença entre as datas: {days} dias.",
            purpose="supported_math",
        )
    for expression, error in [
        ("1/0", "division_by_zero"),
        ('__import__("os")', "invalid_expression"),
        ('open("x")', "invalid_expression"),
        ("2 ** 999999", "unsupported_operation"),
        ("foo + 1", "invalid_expression"),
        ("[1, 2]", "invalid_expression"),
        ("lambda: 1", "invalid_expression"),
        ('"string"', "invalid_expression"),
        ("1 << 100", "unsupported_operation"),
        ("sin(1)", "invalid_expression"),
        ("1,5+2,5", "invalid_expression"),
        ("2+", "invalid_expression"),
    ]:
        case(
            "Calcule " + expression,
            "CALCULATOR",
            "ARITHMETIC",
            "ERROR",
            error=error,
            purpose="division_zero" if expression == "1/0" else "unsafe_or_invalid",
        )
    for text, error in [
        ("10 dias a partir de 05/11/2026", "ambiguous_date_offset"),
        ("Calcule 10 dias a partir de 05/11/2026", "ambiguous_date_offset"),
        ("10 dias úteis depois de 05/11/2026", "unsupported_business_days"),
        ("10 dias depois de amanhã", "unsupported_relative_date"),
        ("Adicione 10 dias corridos a hoje", "unsupported_relative_date"),
        ("Adicione 1 dias corridos a 31/02/2026", "invalid_date"),
    ]:
        case(
            text,
            "CALCULATOR",
            "DATE_OFFSET",
            "ERROR",
            error=error,
            purpose="ambiguous_date" if error == "ambiguous_date_offset" else "unsupported_date",
        )
    for text in [
        "Qual o prazo do art. 53?",
        "O prazo é de 10 dias úteis?",
        "Se o art. 53 fala em 10 dias, qual é o último dia?",
        "Na graduação, se eu pedir dia 5, quando vence?",
        "Segundo a resolução 956/2025, são 10 dias?",
        "Se a Resolução 956/2025 dá 10 dias, qual a data?",
        "O art. 53 conta 10 dias a partir da ciência?",
        "Na graduação são 10 dias úteis?",
        "Segundo o art. 53, some o prazo até 20/11.",
        "O prazo da UFPI conta o primeiro dia?",
        "São dias úteis ou corridos?",
        "Calcule 2+2 conforme a norma.",
        "Calcule o prazo para recurso: 10 dias depois de 05/11/2026",
        "Adicione 10 dias corridos a 05/11/2026 para a matrícula",
        "2+2; conforme o regulamento",
        "E na pós, são 10 dias?",
        "Calcule 2+2 para saber se mantenho minha bolsa estudantil",
        "Calcule 2+2 conforme a resoluc\u0327a\u0303o 956/2025",
    ]:
        case(
            text,
            "NORMATIVE_RAG",
            status="ANSWER",
            purpose="normative_boundary",
            notes="Facade controlada, sem gold jurídico.",
        )
    case("Obrigado", "SAFE_DIRECT", purpose="social")
    case(
        "Resuma em 2 linhas",
        "GROUNDED_TRANSFORM",
        purpose="numeric_transform",
        notes="Sem memória: resposta determinística pedindo contexto.",
    )
    case("Explique em 3 passos", "GROUNDED_TRANSFORM", purpose="numeric_transform")
    case("E na pós?", "CONTEXTUAL_NORMATIVE_RAG", purpose="domain_shift")
    for text in ["Obrigado, quanto é 2+2?", "E vezes 3?", "05/11/2026", "2026-11-05"]:
        case(text, "NORMATIVE_RAG", status="ANSWER", purpose="conservative_fallback")
    dataset = ROOT / "evaluation/datasets/tool_routing_calculator_v1.json"
    write(dataset, {"version": "1", "kind": "finite_engineering_dataset", "cases": cases})

    decisions = [
        (
            "legacy_calculator",
            "DO_NOT_USE no grafo novo; code/src/agents/tools.py permanece intacto. numexpr aceita linguagem mais ampla, retorna str e expõe exceção com entrada; sem limites explícitos ou datas. Bindings legados em chatbot_generic/research_assistant; nenhum teste dedicado encontrado por busca.",
        ),
        (
            "parser",
            "CalculatorIntentParser exige gramática de mensagem completa e veto normativo após NFC; prefixo não autoriza prosa arbitrária. Intent separado da executabilidade.",
        ),
        (
            "arithmetic_grammar",
            "Soma/produto/unário/número/parênteses por descida recursiva. + - * /; sem potência, funções, eval, exec, AST evaluator ou numexpr.",
        ),
        (
            "decimal",
            "Ponto decimal somente, sem vírgula/milhar/expoente. Contexto local independente: precisão 28, ROUND_HALF_EVEN, Emin=-100/Emax=100. Divisão recorrente é arredondada; sem alegação de racional exato.",
        ),
        (
            "limits",
            "512 caracteres por mensagem/expressão; 128 tokens; 24 dígitos/literal; 16 níveis de agrupamento/unário; magnitude intermediária <=1e24 e expoente ajustado >=-100; deslocamento <=3652058 dias e intervalo de date.",
        ),
        (
            "date_grammar",
            "adicione|some N dia(s) corrido(s) a|de DATA; subtraia ...; N dia(s) antes|depois de DATA; quantos dias [existem] entre DATA e DATA; prefixo Calcule/Quanto é opcional. Datas DD/MM/YYYY ou YYYY-MM-DD, sem relógio.",
        ),
        (
            "bare_dates",
            "Data absoluta isolada sem prefixo segue rota conservadora, ou continua pending. Evita tratar resposta de data como divisão/subtração.",
        ),
        (
            "ambiguous_dates",
            "a partir de produz ambiguous_date_offset; nenhum pressuposto de inclusão/exclusão dos extremos.",
        ),
        (
            "business_days",
            "dias úteis com intent de cálculo -> ERROR unsupported_business_days; sem calendário segunda-sexta ou feriados.",
        ),
        (
            "relative_dates",
            "hoje/amanhã/ontem/próxima/fim do mês recusados quando intent fechado; sem datetime.now na calculator.",
        ),
        (
            "normative_mix",
            "Marcadores vetam calculator; gramática fechada é segunda fronteira. Nenhuma execução parcial de mensagem mista. Listas finitas não demonstram cobertura linguística universal.",
        ),
        (
            "routing_priority",
            "Validação memória -> CLEAR_PENDING -> SAFE_DIRECT -> CALCULATOR -> CONTINUE_CLARIFICATION -> GROUNDED_TRANSFORM -> CONTEXTUAL_NORMATIVE_RAG -> NORMATIVE_RAG.",
        ),
        (
            "pending",
            "ANSWER e ERROR da calculator preservam pending integralmente e não substituem a correlação original.",
        ),
        (
            "memory",
            "Tool só recebe request da mensagem atual. Não recebe answer, referências ou provenance. Mantém envelope/stamp normativos, inclusive stale sem reutilização.",
        ),
        (
            "intervening_turn",
            "repita/explique/resuma continuam vinculados ao último ANSWER normativo após calculator; não há memória matemática. Pode surpreender UX; política explícita testada.",
        ),
        (
            "transport",
            "calculator_result exclusivo com normative_result/grounded_followup_result; conteúdo AI exato; um message completo + DONE. Service e AgentClient existentes permanecem intactos.",
        ),
        (
            "result_contract",
            "CalculatorToolResult v1 ANSWER/ERROR com payload exclusivo por operação, formatter estável, erro de catálogo seguro, sem campos normativos.",
        ),
        (
            "scope",
            "Somente branch/commits locais; default chatbot_ufpi_v2 e registry preservados. Sem UI, autenticação, deploy, API real ou composição RAG -> calculator.",
        ),
    ]
    now = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat()
    (OUT / "decision_log.jsonl").write_bytes(
        b"".join(
            (
                json.dumps(
                    dict(id=i, timestamp=now, topic=topic, decision=decision), ensure_ascii=False
                )
                + "\n"
            ).encode()
            for i, (topic, decision) in enumerate(decisions, 1)
        )
    )
    write(
        OUT / "legacy_calculator_audit.json",
        {
            "path": "code/src/agents/tools.py",
            "type": "LangChain BaseTool via tool decorator",
            "name": "Calculator",
            "input_schema": {"expression": "str"},
            "parser": "numexpr.evaluate",
            "eval_exec": False,
            "llm_in_function": False,
            "operations": "numexpr expression language, pi/e locals; no explicit application allowlist",
            "errors": "ValueError embeds input and underlying exception",
            "limits": "No application complexity/length limits",
            "side_effects": "Function evaluates locally; module imports integrations and creates tool bindings, includes lazy network helpers",
            "bindings": ["agents/chatbot_generic.py", "agents/research_assistant.py"],
            "dedicated_tests_found": False,
            "decision": "DO_NOT_USE",
            "legacy_preserved": True,
        },
    )
    print("Prepared", len(cases), "cases and", len(decisions), "decisions")


if __name__ == "__main__":
    prepare()
