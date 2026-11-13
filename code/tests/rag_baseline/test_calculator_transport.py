"""Calculator result through real ASGI service and unmodified AgentClient."""

import httpx
import pytest
import test_calculator_tool_routing as tests
import test_conversation_memory_followups as memory
import test_typed_normative_transport as transport
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

calc = tests.calc
conversation = memory.conversation
harness = transport.harness


@pytest.mark.parametrize("mode", ["invoke", "stream"])
@pytest.mark.parametrize(
    "text,status",
    [("2+2", "ANSWER"), ("1/0", "ERROR"), ("Adicione 10 dias corridos a 05/11/2026", "ANSWER")],
)
@pytest.mark.asyncio
async def test_async_calculator_transport(
    conversation, calc, harness, monkeypatch, tmp_path, mode, text, status
):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "http.sqlite")) as saver:
        graph = memory.build(conversation, saver, harness.facade)
        monkeypatch.setattr(transport.service_module, "get_agent", lambda agent_id: graph)
        if mode == "invoke":
            result = await harness.client.ainvoke(text, user_id="A", thread_id="X")
        else:
            items = [
                x
                async for x in harness.client.astream(
                    text, user_id="A", thread_id="X", stream_tokens=True
                )
            ]
            assert len(items) == 1
            result = items[0]
        assert isinstance(result.calculator_result, calc.CalculatorToolResult)
        assert result.calculator_result.status == status
        assert result.normative_result is result.grounded_followup_result is None
        assert result.content == result.calculator_result.content
        assert not harness.facade.calls
        assert not transport.keys(result.model_dump(mode="json")) & {
            "internal_audit",
            "conversation_memory",
            "storage_key",
            "compatibility_stamp",
            "last_normative_result_persistence",
            "references",
            "temporal_provenance",
        }


@pytest.mark.asyncio
async def test_raw_sse_is_one_complete_message_and_done(
    conversation, harness, monkeypatch, tmp_path
):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "sse.sqlite")) as saver:
        graph = memory.build(conversation, saver, harness.facade)
        monkeypatch.setattr(transport.service_module, "get_agent", lambda agent_id: graph)
        async with httpx.AsyncClient() as web:
            response = await web.post(
                f"http://test/{transport.AGENT}/stream",
                json={"message": "2+2", "user_id": "A", "thread_id": "X", "stream_tokens": True},
            )
        lines = [line for line in response.text.splitlines() if line.startswith("data:")]
        assert len(lines) == 2 and lines[-1] == "data: [DONE]"
        assert '"calculator_result"' in lines[0] and '"token"' not in lines[0]


@pytest.mark.parametrize("mode", ["invoke", "stream"])
def test_sync_client_restores_calculator_type(calc, harness, monkeypatch, mode):
    from schema import ChatMessage

    result = tests.execute(calc, "2+2")
    payload = ChatMessage(type="ai", content="4", calculator_result=result).model_dump(mode="json")
    if mode == "invoke":
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *args, **kwargs: httpx.Response(
                200, json=payload, request=httpx.Request("POST", "http://test")
            ),
        )
        received = harness.client.invoke("2+2")
    else:
        import json
        from contextlib import contextmanager

        @contextmanager
        def stream(*args, **kwargs):
            yield httpx.Response(
                200,
                text=f"data: {json.dumps({'type': 'message', 'content': payload})}\n\ndata: [DONE]\n\n",
                request=httpx.Request("POST", "http://test"),
            )

        monkeypatch.setattr(httpx, "stream", stream)
        items = list(harness.client.stream("2+2"))
        assert len(items) == 1
        received = items[0]
    assert isinstance(received.calculator_result, calc.CalculatorToolResult)
    assert received.content == "4"
