"""AI gateway interfaces (SPEC 8.1).

Principle Zero: the gateway never authorizes. Callers only build an
LLMRequest after authorization has already decided the data is visible to
them; the gateway transports prompts and records provenance metadata.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    text: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[ChatMessage, ...]
    model: str = ""
    temperature: float = 0.0
    # Thinking models spend part of this before the answer (~1000 tokens on the demo prompts).
    max_output_tokens: int = 4096
    system: str | None = None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResult:
    text: str
    provider: str
    model: str
    model_version: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    cached: bool = False
    notice: str = ""


class ProviderError(RuntimeError):
    """A provider call failed after leaving this process (network, API, parse)."""


class ProviderNotConfiguredError(ProviderError):
    """The provider or its credentials are not available in this environment."""


class ProviderTimeoutError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@runtime_checkable
class LLMProvider(Protocol):
    provider_name: str

    def complete(self, request: LLMRequest) -> LLMResult: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
