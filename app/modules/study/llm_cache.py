"""Deterministic LLM replay cache (DOC_08 §8).

For the study to be defensible every Claude call is cached, keyed by a hash of
``(model, temperature, prompt)``. A cache hit serves the stored response with no
API call; a miss makes the call and stores it. ``wrap`` returns a drop-in proxy
around an Anthropic async client, so a call site keeps writing
``client.messages.create(...)`` and gets caching for free.

Temperature defaults to 0 (study reproducibility beats variety, §8) and is part
of the hash so a deliberate temperature change never collides with a cached 0.
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import structlog
from app.db import session_scope
from app.logging import log_event
from app.modules.study.model import LLMCache
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = structlog.get_logger("study.llm_cache")

# Kwargs that determine the prompt; anything else (streaming flags etc.) is
# excluded so it can't perturb the key.
_HASHED_KEYS = ("model", "temperature", "system", "messages", "tools", "tool_choice", "max_tokens")


def prompt_hash(kwargs: dict[str, Any]) -> str:
    """SHA-256 over the prompt-determining kwargs (DOC_08 §8)."""
    material = {k: kwargs[k] for k in _HASHED_KEYS if k in kwargs}
    encoded = json.dumps(material, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _serialize(response: Any) -> dict[str, Any]:
    """Best-effort JSON view of a response (real SDK Message or a test double)."""
    if hasattr(response, "model_dump"):
        dumped: dict[str, Any] = response.model_dump(mode="json")
        return dumped
    keys = ("type", "name", "input", "text", "id")
    blocks = [
        {k: getattr(block, k) for k in keys if hasattr(block, k)}
        for block in getattr(response, "content", []) or []
    ]
    return {"content": blocks}


def _deserialize(data: dict[str, Any]) -> Any:
    """Rebuild an attribute-accessible response from stored JSON (cache hit)."""
    content = [SimpleNamespace(**block) for block in data.get("content", [])]
    extra = {k: v for k, v in data.items() if k != "content"}
    return SimpleNamespace(content=content, **extra)


async def _get(hash_: str) -> dict[str, Any] | None:
    async for session in session_scope():
        row = await session.get(LLMCache, hash_)
        if row is not None:
            return dict(row.response)
    return None


async def _store(hash_: str, model: str, response: dict[str, Any]) -> None:
    async for session in session_scope():
        stmt = pg_insert(LLMCache).values(
            prompt_hash=hash_, model=model, response=response
        )
        # Concurrent misses can both try to store; first writer wins.
        stmt = stmt.on_conflict_do_nothing(index_elements=[LLMCache.prompt_hash])
        await session.execute(stmt)


class _CachingMessages:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def create(self, **kwargs: Any) -> Any:
        kwargs.setdefault("temperature", 0)
        hash_ = prompt_hash(kwargs)
        cached = await _get(hash_)
        if cached is not None:
            log_event("llm_cache_hit", model=kwargs.get("model"), prompt_hash=hash_)
            return _deserialize(cached)
        response = await self._inner.create(**kwargs)
        try:
            await _store(hash_, str(kwargs.get("model")), _serialize(response))
        except Exception as exc:  # noqa: BLE001 — caching must never break a call
            log.warning("llm_cache_store_failed", error=str(exc))
        return response


class CachingClient:
    """Proxy exposing ``.messages.create`` with transparent caching."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.messages = _CachingMessages(inner.messages)

    def __getattr__(self, name: str) -> Any:  # pragma: no cover — passthrough
        return getattr(self._inner, name)


def wrap(client: Any) -> CachingClient:
    """Wrap an Anthropic async client so every message create is cached."""
    return CachingClient(client)
