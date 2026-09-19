from collections.abc import Sequence
from typing import Any

import httpx


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        embedding_model: str,
        llm_model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        embedding_batch_size: int = 64,
        llm_temperature: float = 0,
        llm_max_tokens: int = 800,
        timeout_seconds: float = 30,
        app_name: str | None = None,
        http_referer: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.base_url = base_url.rstrip("/")
        self.embedding_batch_size = embedding_batch_size
        self.llm_temperature = llm_temperature
        self.llm_max_tokens = llm_max_tokens
        self.timeout_seconds = timeout_seconds
        self.app_name = app_name
        self.http_referer = http_referer
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY não está configurada.")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.app_name:
            headers["X-OpenRouter-Title"] = self.app_name
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        return headers

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(path, json=payload)
        except httpx.TimeoutException as exc:
            raise OpenRouterError("OpenRouter excedeu o tempo limite configurado.") from exc
        except httpx.RequestError as exc:
            raise OpenRouterError("Não foi possível conectar ao OpenRouter.") from exc

        if response.is_error:
            raise OpenRouterError(f"OpenRouter retornou HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as exc:
            raise OpenRouterError("OpenRouter retornou uma resposta inválida.") from exc
        if not isinstance(data, dict):
            raise OpenRouterError("OpenRouter retornou uma resposta inválida.")
        return data

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.embedding_batch_size):
            batch = list(texts[start : start + self.embedding_batch_size])
            response = await self._post(
                "/embeddings",
                {"model": self.embedding_model, "input": batch},
            )
            items = response.get("data")
            if not isinstance(items, list) or len(items) != len(batch):
                raise OpenRouterError(
                    "A quantidade de embeddings retornada difere da quantidade enviada."
                )
            try:
                ordered = sorted(items, key=lambda item: item["index"])
                if [item["index"] for item in ordered] != list(range(len(batch))):
                    raise ValueError
                batch_embeddings = [item["embedding"] for item in ordered]
                if not all(isinstance(embedding, list) for embedding in batch_embeddings):
                    raise ValueError
            except (KeyError, TypeError, ValueError) as exc:
                raise OpenRouterError("OpenRouter retornou embeddings em formato inválido.") from exc
            embeddings.extend(batch_embeddings)
        return embeddings

    async def chat(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._post(
            "/chat/completions",
            {
                "model": self.llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": float(self.llm_temperature),
                "max_tokens": self.llm_max_tokens,
            },
        )
        try:
            content = response["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OpenRouterError("OpenRouter retornou uma resposta de chat inválida.") from exc
        return content
