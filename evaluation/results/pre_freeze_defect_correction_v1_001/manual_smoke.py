"""Separate operational smoke with real provider, explicitly invoked; no scientific metrics."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-provider-approved", action="store_true", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    app = AppTest.from_file("/app/code/src/streamlit_app.py").run(timeout=30)
    cases = [
        ("explicit_post_clean", "como entrar na pós?", "pos_graduacao"),
        ("explicit_grad", "qual a média para passar na graduação?", "graduacao"),
        ("explicit_post_after_grad", "como entrar na pós?", "pos_graduacao"),
        (
            "multiple_references",
            "como funciona o ingresso na pós-graduação?",
            "pos_graduacao",
        ),
    ]
    assert ord(cases[0][1][-3]) == 243
    rows = []
    for name, question, domain in cases:
        app.chat_input[0].set_value(question).run(timeout=180)
        assert not app.exception and not app.error
        message = app.session_state.messages[-1]
        result = message.normative_result
        last = app.chat_message[-1]
        refs = (
            list({tuple(r.model_dump().items()): r for r in result.references}.values())
            if result
            else []
        )
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": "pre-freeze manual operational smoke; real provider; not scientific evaluation",
            "case": name,
            "question": question,
            "question_codepoints": [ord(c) for c in question],
            "status": result.status.value if result else None,
            "domain": result.domain if result else None,
            "message": message.model_dump(mode="json"),
            "source_regions": len(last.expander),
            "source_labels": [e.label for e in last.expander],
            "typed_references": len(refs),
            "details_rendered": len(last.expander[0].text) if last.expander else 0,
        }
        row["duplicate_source_sections"] = sum(
            h in message.content for h in ["Fontes:", "Referências:", "Sources:"]
        )
        row["passed"] = bool(
            result
            and result.status == "ANSWER"
            and result.domain == domain
            and len(last.expander) == 1
            and last.expander[0].label == "Trechos normativos recuperados"
            and len(refs) > 1
            and len(last.expander[0].text) == len(refs)
            and all(
                r.evidence_text is not None and shown.value == r.evidence_text.strip()
                for r, shown in zip(refs, last.expander[0].text)
            )
            and row["duplicate_source_sections"] == 0
        )
        rows.append(row)
        args.out.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    k: row[k]
                    for k in (
                        "case",
                        "status",
                        "domain",
                        "typed_references",
                        "details_rendered",
                        "duplicate_source_sections",
                        "passed",
                    )
                }
            ),
            flush=True,
        )
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
