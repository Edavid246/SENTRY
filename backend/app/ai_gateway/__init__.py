"""AI gateway (SPEC 8.1): LLM and embedding providers behind one facade.

All model traffic goes through this package; nothing else in the app may
call a provider directly (AGENTS.md).
"""

from app.ai_gateway.base import (
    ChatMessage,
    EmbeddingProvider,
    LLMProvider,
    LLMRequest,
    LLMResult,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TokenUsage,
)
from app.ai_gateway.cache import LLMResponseCache
from app.ai_gateway.embeddings import LocalEmbeddingProvider, get_embedder, reset_embedder
from app.ai_gateway.gateway import AIGateway, get_gateway, reset_gateway
from app.ai_gateway.hosted import HostedProvider
from app.ai_gateway.local_vllm import LocalVLLMProvider

__all__ = [
    "AIGateway",
    "ChatMessage",
    "EmbeddingProvider",
    "HostedProvider",
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "LLMResponseCache",
    "LocalEmbeddingProvider",
    "LocalVLLMProvider",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "TokenUsage",
    "get_embedder",
    "get_gateway",
    "reset_embedder",
    "reset_gateway",
]
