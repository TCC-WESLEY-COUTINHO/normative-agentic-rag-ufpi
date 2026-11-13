"""Capture pre-freeze defect boundaries using real pipeline and controlled provider."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / "code/tests/rag_baseline"))
import test_pre_freeze_defects as cases  # noqa: E402
import test_retrieval_strategies as fixture  # noqa: E402
from service.normative_transport import project_integrated_state  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402


class UIClient:
    def __init__(self, message):
        self.message = message
        self.agent = None

    def update_agent(self, agent, verify=False):
        self.agent = agent

    async def astream(self, **kwargs):
        yield self.message


async def main():
    observations = {}
    with tempfile.TemporaryDirectory(
        prefix="pre-freeze-reproduction-", ignore_cleanup_errors=True
    ) as directory:
        directory = Path(directory)
        (OUT / "reproduction_workspace.json").write_text(
            json.dumps({"path": str(directory)}), encoding="utf-8"
        )
        for name, question in [
            ("source_layers", "como entrar na pós-graduação?"),
            ("explicit_post", "como entrar na pós?"),
        ]:
            runtime = fixture.runtime.__wrapped__(
                directory / name, fixture.registry.__wrapped__()
            )
            context = cases.integrated.__wrapped__(runtime)
            turn, provider, _ = next(context)
            try:
                state = await turn(question)
                result = state["normative_result"]
                message = project_integrated_state(state)
                row = dict(
                    original_question=question,
                    conversation_action=state["turn_audit"].conversation_action,
                    router_input=provider.routes[-1],
                    router_output=provider.decisions[-1],
                    prior_memory=False,
                    contextual_resolver_used=False,
                    pending_created=state["conversation_memory"].pending_clarification
                    is not None,
                    status=result.status.value,
                    domain=result.domain,
                )
                if result.status == "ANSWER":
                    audit = result.internal_audit.output_audit
                    row.update(
                        raw_generated_body=audit.raw_answer,
                        structured_final_answer=audit.final_answer,
                        normative_tool_answer=result.answer,
                        chat_message_content=message.content,
                        references=[
                            r.model_dump(mode="json") for r in result.references
                        ],
                        source_origin="normative_output.compose_answer",
                        references_semantics="final eligible evidence context projected before generation; not per-claim support attribution",
                    )
                    old_cwd = Path.cwd()
                    os.chdir(directory)
                    try:
                        with patch(
                            "client.AgentClient", return_value=UIClient(message)
                        ):
                            app = AppTest.from_file(
                                str(ROOT / "code/src/streamlit_app.py")
                            ).run(timeout=15)
                            app.chat_input[0].set_value(question).run(timeout=15)
                            assert not app.exception
                            row["ui_render"] = dict(
                                markdown=[m.value for m in app.markdown],
                                expander_labels=[e.label for e in app.expander],
                            )
                    finally:
                        os.chdir(old_cwd)
                observations[name] = row
            finally:
                context.close()
    (OUT / "reproduction_before.json").write_text(
        json.dumps(observations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "source_layers": {
                    "raw_body_has_bibliography": "Fontes:"
                    in observations["source_layers"]["raw_generated_body"],
                    "final_has_bibliography": "Fontes:"
                    in observations["source_layers"]["structured_final_answer"],
                    "references": len(observations["source_layers"]["references"]),
                },
                "explicit_post": observations["explicit_post"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    if (OUT / "reproduction_before.json").exists():
        raise FileExistsError(
            "Historical pre-fix reproduction must not be overwritten."
        )
    asyncio.run(main())
