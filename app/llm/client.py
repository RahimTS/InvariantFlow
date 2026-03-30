from __future__ import annotations

import asyncio
from typing import Any, Protocol

import httpx

from app.config import settings
from app.llm.models import ChatMessage, LLMResponse, LLMUsage
from app.llm.structured_output import extract_json_object


class StructuredLLMClient(Protocol):
    async def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict,
        temperature: float = 0.0,
    ) -> dict: ...


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        app_name: str = "InvariantFlow",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._app_name = app_name
        self._http_client = http_client

    async def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        temperature: float = 0.0,
        response_format: dict | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        raw = await self._post_with_retries("/chat/completions", payload)
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = _coerce_message_content(message.get("content"))
        usage_raw = raw.get("usage") or {}

        return LLMResponse(
            model=raw.get("model", model),
            content=content,
            raw=raw,
            usage=LLMUsage(
                prompt_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
                total_tokens=int(usage_raw.get("total_tokens", 0) or 0),
            ),
        )

    async def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict,
        temperature: float = 0.0,
    ) -> dict:
        response = await self.complete(
            model=model,
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ],
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )
        return extract_json_object(response.content)

    async def _post_with_retries(self, path: str, payload: dict) -> dict:
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._post_json(path, payload)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise RuntimeError("OpenRouter returned non-JSON-object payload")
                return data
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(0.4 * (attempt + 1))

        raise RuntimeError(f"OpenRouter request failed after retries: {last_error}")

    async def _post_json(self, path: str, payload: dict) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": self._app_name,
        }
        if self._http_client is not None:
            return await self._http_client.post(
                f"{self._base_url}{path}",
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient() as client:
            return await client.post(
                f"{self._base_url}{path}",
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )


def create_openrouter_client() -> OpenRouterClient | None:
    if not settings.openrouter_api_key:
        return None
    return OpenRouterClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.openrouter_timeout_seconds,
        max_retries=settings.openrouter_max_retries,
    )


def _coerce_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks).strip()
    return str(content)

