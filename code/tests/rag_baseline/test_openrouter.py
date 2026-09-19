import json

import httpx
import pytest

from rag_baseline.openrouter import OpenRouterClient, OpenRouterError


@pytest.mark.asyncio
async def test_embeddings_preserve_input_order_across_batches() -> None:
    seen_inputs: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_inputs.append(body["input"])
        if body["input"] == ["um", "dois"]:
            data = [
                {"object": "embedding", "index": 1, "embedding": [2.0]},
                {"object": "embedding", "index": 0, "embedding": [1.0]},
            ]
        else:
            data = [{"object": "embedding", "index": 0, "embedding": [3.0]}]
        return httpx.Response(200, json={"object": "list", "data": data})

    client = OpenRouterClient(
        api_key="test-key",
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
        embedding_batch_size=2,
        transport=httpx.MockTransport(handler),
    )

    embeddings = await client.embed(["um", "dois", "tres"])

    assert embeddings == [[1.0], [2.0], [3.0]]
    assert seen_inputs == [["um", "dois"], ["tres"]]


@pytest.mark.asyncio
async def test_embeddings_keep_api_version_path_from_base_url() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"index": 0, "embedding": [1.0]}]},
        )

    client = OpenRouterClient(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
        transport=httpx.MockTransport(handler),
    )

    await client.embed(["texto"])

    assert requested_urls == ["https://openrouter.ai/api/v1/embeddings"]


@pytest.mark.asyncio
async def test_embeddings_reject_response_with_wrong_item_count() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"index": 0, "embedding": [1.0]}]},
        )

    client = OpenRouterClient(
        api_key="test-key",
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenRouterError, match="quantidade"):
        await client.embed(["um", "dois"])


@pytest.mark.asyncio
async def test_chat_returns_assistant_content_and_sends_configured_parameters() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chat-1",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "Resposta."}}
                ],
            },
        )

    client = OpenRouterClient(
        api_key="test-key",
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
        llm_temperature=0,
        llm_max_tokens=800,
        transport=httpx.MockTransport(handler),
    )

    answer = await client.chat(
        system_prompt="Somente a norma.",
        user_prompt="Contexto e pergunta.",
    )

    assert answer == "Resposta."
    assert captured == {
        "model": "qwen/test",
        "messages": [
            {"role": "system", "content": "Somente a norma."},
            {"role": "user", "content": "Contexto e pergunta."},
        ],
        "temperature": 0.0,
        "max_tokens": 800,
    }


@pytest.mark.asyncio
async def test_missing_api_key_fails_without_making_a_request() -> None:
    client = OpenRouterClient(
        api_key=None,
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
    )

    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        await client.embed(["texto"])


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 429, 500])
async def test_http_errors_are_safe_and_do_not_expose_api_key(status_code: int) -> None:
    secret = "super-secret-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": f"upstream {secret}"}})

    client = OpenRouterClient(
        api_key=secret,
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenRouterError) as caught:
        await client.embed(["texto"])

    assert str(status_code) in str(caught.value)
    assert secret not in str(caught.value)


@pytest.mark.asyncio
async def test_timeout_is_reported_as_safe_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OpenRouterClient(
        api_key="test-key",
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenRouterError, match="tempo limite"):
        await client.embed(["texto"])


@pytest.mark.asyncio
async def test_invalid_chat_response_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = OpenRouterClient(
        api_key="test-key",
        embedding_model="openai/text-embedding-3-small",
        llm_model="qwen/test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenRouterError, match="inválida"):
        await client.chat(system_prompt="sistema", user_prompt="pergunta")
