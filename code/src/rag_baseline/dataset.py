"""Plain numbered question/answer presentation used by the original graduation gold."""

import re
from pathlib import Path


def render_gold(items: list[dict]) -> str:
    if not items:
        raise ValueError("Dataset vazio.")
    lines = ["Bancada de Questões", ""]
    for number, item in enumerate(items, 1):
        question = item["question"].strip()
        answer = " ".join(item["reference_answer"].split())
        if not question or "\n" in question or not answer:
            raise ValueError("Pergunta ou resposta inválida.")
        if item.get("expected_action") != "clarify":
            articles = ", ".join(e["article_number"] for e in item["evidence"])
            answer += f" [Resolução CEPEX/UFPI nº 956/2025, art. {articles}]."
        lines.extend((f"{number}. {question}", f"   {answer}"))
    return "\n".join(lines) + "\n"


def load_questions(path: str | Path) -> list[str]:
    text = Path(path).read_text(encoding="utf-8-sig")
    matches = list(re.finditer(r"^(\d+)\.\s+([^\n]+)$", text, flags=re.M))
    if not matches or [int(m[1]) for m in matches] != list(range(1, len(matches) + 1)):
        raise ValueError("Esperada uma lista de perguntas numeradas sequencialmente a partir de 1.")
    return [m[2].strip() for m in matches]
