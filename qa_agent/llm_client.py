"""Lightweight LLM clients for Anthropic, OpenAI and local Ollama."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "claude-sonnet-4-6",
    LLMProvider.OPENAI: "gpt-4o",
    LLMProvider.OLLAMA: "qwen2.5:3b",
}

_KEY_ENV_VARS: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.OPENAI: "OPENAI_API_KEY",
}


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    text: str
    provider: LLMProvider
    model: str


class LLMError(Exception):
    """Raised when an LLM API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _http_post(url: str, headers: dict[str, str], body: dict, timeout: int) -> dict:
    """POST JSON and return the parsed response."""

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        retryable = exc.code in (429, 500, 502, 503, 504, 529)
        raise LLMError(
            f"HTTP {exc.code}: {raw[:300]}",
            status_code=exc.code,
            retryable=retryable,
        ) from exc
    except urllib.error.URLError as exc:
        raise LLMError(str(exc), retryable=True) from exc
    except TimeoutError as exc:
        raise LLMError("Request timed out", retryable=True) from exc


class AnthropicClient:
    """Calls the Anthropic Messages API."""

    _API_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise LLMError(
                "Anthropic API key not found. "
                "Set the ANTHROPIC_API_KEY environment variable."
            )
        self._api_key = key

    def complete(self, system: str, user: str, max_tokens: int, timeout: int) -> LLMResponse:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._API_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = _http_post(self._API_URL, headers, body, timeout)
        content = data.get("content", [])
        text = next((b["text"] for b in content if b.get("type") == "text"), None)

        if not text:
            raise LLMError("Anthropic API returned no text content.")

        return LLMResponse(text=text, provider=LLMProvider.ANTHROPIC, model=self.model)


class OpenAIClient:
    """Calls the OpenAI Chat Completions API."""

    _API_URL = "https://api.openai.com/v1/chat/completions"
    _REASONING_MODEL_PREFIX = ("o1", "o3")

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise LLMError(
                "OpenAI API key not found. "
                "Set the OPENAI_API_KEY environment variable."
            )
        self._api_key = key

    def _tokens_param(self, max_tokens: int) -> dict:
        key = (
            "max_completion_tokens"
            if any(self.model.startswith(p) for p in self._REASONING_MODEL_PREFIX)
            else "max_tokens"
        )
        return {key: max_tokens}

    def complete(self, system: str, user: str, max_tokens: int, timeout: int) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            **self._tokens_param(max_tokens),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = _http_post(self._API_URL, headers, body, timeout)
        choices = data.get("choices", [])

        if not choices:
            raise LLMError("OpenAI API returned no choices.")

        text = choices[0].get("message", {}).get("content", "")
        if not text:
            raise LLMError("OpenAI API returned no text content.")

        return LLMResponse(text=text, provider=LLMProvider.OPENAI, model=self.model)


class OllamaClient:
    """Calls a locally running Ollama server."""

    def __init__(self, model: str) -> None:
        self.model = model
        self._base_url = os.environ.get(
            "OLLAMA_HOST", "http://localhost:11434"
        ).rstrip("/")

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int,
        timeout: int,
        json_mode: bool = False,
    ) -> LLMResponse:
        headers = {"Content-Type": "application/json"}
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"

        data = _http_post(
            f"{self._base_url}/api/chat",
            headers,
            body,
            timeout,
        )

        text = data.get("message", {}).get("content", "")
        if not text:
            raise LLMError("Ollama returned no text content.")

        return LLMResponse(
            text=text,
            provider=LLMProvider.OLLAMA,
            model=self.model,
        )


def has_api_key(provider: LLMProvider) -> bool:
    """Return True if the provider needs no API key or has one configured in env."""
    env_var = _KEY_ENV_VARS.get(provider)
    if not env_var:
        return True
    return bool(os.environ.get(env_var, "").strip())


def get_ollama_status(base_url: str | None = None, timeout: float = 2.0) -> dict[str, Any]:
    """Query local Ollama server health and installed models without raising."""
    host = (base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
    default_model = DEFAULT_MODELS[LLMProvider.OLLAMA]
    req = urllib.request.Request(f"{host}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        raw_models = payload.get("models", []) if isinstance(payload, dict) else []
        models: list[str] = [
            name
            for m in raw_models
            if isinstance(m, dict)
            for name in [m.get("name")]
            if isinstance(name, str)
        ]
        return {
            "available": True,
            "host": host,
            "models": models,
            "default_model": default_model,
            "has_default_model": any(
                m == default_model or m.startswith(f"{default_model}:") for m in models
            ),
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "host": host,
            "models": [],
            "default_model": default_model,
            "has_default_model": False,
            "error": str(exc),
        }


def create_llm_client(
    provider: LLMProvider,
    model: str | None = None,
    api_key: str | None = None,
) -> AnthropicClient | OpenAIClient | OllamaClient:
    """Create an LLM client for the selected provider."""

    resolved_model = model or DEFAULT_MODELS[provider]

    if provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(model=resolved_model, api_key=api_key)

    if provider == LLMProvider.OPENAI:
        return OpenAIClient(model=resolved_model, api_key=api_key)

    if provider == LLMProvider.OLLAMA:
        return OllamaClient(model=resolved_model)

    raise ValueError(f"Unknown LLM provider: {provider!r}")
