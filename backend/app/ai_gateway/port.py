"""The model seam the pathways call through (SPEC 8.1, AGENTS.md "Models").

`ModelPort` is everything a pathway may ask of a model: complete a chat
request (through the AI gateway: retries, demo cache, provider from config)
and embed a question for retrieval (always local). It is handed to the
assistant as a FastAPI dependency (`app.api.deps.get_models`), so tests and
the prefill script swap the whole model side in one place instead of
patching import paths.

Both halves resolve lazily: building a port never contacts a provider or
loads embedding weights, so a misconfigured provider still fails inside the
pathway as a ProviderError (a clean 503), never while wiring the request.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.ai_gateway.base import LLMRequest, LLMResult


class Completer(Protocol):
    def complete(self, request: LLMRequest) -> LLMResult: ...


def _gateway() -> Completer:
    from app.ai_gateway.gateway import get_gateway

    return get_gateway()


def _local_embedding(question: str) -> list[float] | None:
    try:
        from app.ai_gateway.embeddings import get_embedder

        return list(get_embedder().embed([question])[0])
    except Exception:  # noqa: BLE001 - degrade to full-text search
        return None


class ModelPort:
    def __init__(
        self,
        llm: Completer | None = None,
        embed: Callable[[str], list[float] | None] | None = None,
    ) -> None:
        self._llm = llm
        self._embed = embed if embed is not None else _local_embedding

    def complete(self, request: LLMRequest) -> LLMResult:
        return (self._llm if self._llm is not None else _gateway()).complete(request)

    def embed_query(self, question: str) -> list[float] | None:
        """The query embedding, or None when no embedder is available (FTS only)."""
        return self._embed(question)
