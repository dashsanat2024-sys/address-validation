"""Ollama client with timeout, keep-alive, and model warm-up."""

from __future__ import annotations

import logging
import os
from typing import Any

from ollama import Client

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))
DEFAULT_FIRST_TIMEOUT = float(os.getenv("OLLAMA_FIRST_TIMEOUT", "240"))
DEFAULT_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

_client: Client | None = None
_warmed_model: str | None = None


class OllamaTimeoutError(RuntimeError):
    """Raised when Ollama doesn't respond in time."""


def ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434")


def get_client(host: str | None = None) -> Client:
    global _client
    host = host or ollama_host()
    if _client is None:
        _client = Client(host=host, timeout=DEFAULT_TIMEOUT)
    return _client


def ping_ollama(timeout: float = 5.0) -> tuple[bool, str]:
    """Quick check that Ollama responds (not full inference)."""
    try:
        Client(host=ollama_host(), timeout=timeout).list()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def warm_model(model: str | None = None, host: str | None = None) -> bool:
    """Load model into memory so first user request is not stuck ~40s with no feedback."""
    global _warmed_model
    model = model or DEFAULT_MODEL
    if _warmed_model == model:
        return True
    try:
        client = get_client(host)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "{}"}],
            "format": "json",
            "keep_alive": DEFAULT_KEEP_ALIVE,
            "options": {"num_predict": 1, "temperature": 0},
        }
        if "qwen3" in model.lower():
            kwargs["think"] = False
        client.chat(**kwargs)
        _warmed_model = model
        logger.info("Ollama model warmed: %s", model)
        return True
    except Exception as exc:
        logger.warning("Ollama warm-up failed for %s: %s", model, exc)
        return False


def chat(model: str, messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("keep_alive", DEFAULT_KEEP_ALIVE)
    if "qwen3" in model.lower():
        kwargs.setdefault("think", False)
    try:
        return get_client().chat(model=model, messages=messages, **kwargs)
    except Exception as exc:
        if not _is_timeout_error(exc):
            raise
        logger.warning("Ollama timeout for %s, trying warm-up retry", model)
        warm_model(model=model)
        try:
            retry_client = Client(host=ollama_host(), timeout=DEFAULT_FIRST_TIMEOUT)
            return retry_client.chat(model=model, messages=messages, **kwargs)
        except Exception as retry_exc:
            if _is_timeout_error(retry_exc):
                raise OllamaTimeoutError(
                    f"Ollama model '{model}' is still loading. Please retry in 30-60 seconds."
                ) from retry_exc
            raise


def _is_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    timeout_markers = (
        "timed out",
        "timeout",
        "readtimeout",
        "connecttimeout",
        "deadline exceeded",
    )
    return any(marker in text for marker in timeout_markers)
