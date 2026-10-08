"""AI gateway facade (SPEC 8.1).

Resolves the configured model, retries retryable provider failures with a
bounded delay, and falls back to the pre-canned demo response cache only
after retries are exhausted. Configuration failures
(ProviderNotConfiguredError) are never masked by the cache. The cache is
read-only unless the dev-only record mode is on (LLM_CACHE_RECORD=1, see
scripts/prefill_cache.py); record mode replays a request already recorded
instead of calling the provider again. In cache-only mode (LLM_CACHE_ONLY=1) the hosted
provider is never called: a hit is replayed, a miss raises
ProviderUnavailableError.

Every completed call carries provider, model, model version, token counts
and latency for the audit event (SPEC 8.1); audit attachment happens when
the knowledge pathway lands.
"""

import time
from dataclasses import replace
from functools import lru_cache

from app.ai_gateway.base import (
    LLMProvider,
    LLMRequest,
    LLMResult,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TokenUsage,
)
from app.ai_gateway.cache import LLMResponseCache

_RETRYABLE = (ProviderTimeoutError, ProviderRateLimitError, ProviderUnavailableError)
_CACHE_NOTICE = "replayed from pre-canned demo cache (docs/PRODUCTION_DEBT.md)"


class AIGateway:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        cache: LLMResponseCache | None = None,
        max_retries: int = 2,
        record: bool = False,
        cache_only: bool = False,
        retry_after_cap: float = 5.0,
        sleep=time.sleep,
        clock=time.perf_counter,
    ) -> None:
        self._llm = llm
        self._cache = cache
        self._max_retries = max(0, max_retries)
        if (record or cache_only) and cache is None:
            raise ValueError("record and cache-only modes need a cache")
        if record and cache_only:
            raise ValueError("record and cache-only modes are mutually exclusive")
        self._record = record
        self.recorded_count = 0
        self.replayed_count = 0
        self._cache_only = cache_only
        self._retry_after_cap = retry_after_cap
        self._sleep = sleep
        self._clock = clock

    @property
    def llm(self) -> LLMProvider:
        return self._llm

    @property
    def cache(self) -> LLMResponseCache | None:
        return self._cache

    def complete(self, request: LLMRequest) -> LLMResult:
        from app.config import get_settings

        resolved = request if request.model else replace(request, model=get_settings().llm_model)
        key = self._cache.key(resolved) if self._cache else ""
        started = self._clock()
        if self._cache_only:
            miss = ProviderUnavailableError(
                f"cache-only mode: no cached answer for request {key[:12]}"
            )
            return self._replay(resolved, key, started, miss)
        if self._record and self._cache is not None and self._cache.get(key) is not None:
            # Same key, same request: re-recording would only spend quota (20 calls a
            # day on the free tier). Delete the cache file to record afresh.
            return self._replay(resolved, key, started, ProviderUnavailableError("unreachable"))
        attempt = 0
        while True:
            try:
                result = self._llm.complete(resolved)
            except ProviderNotConfiguredError:
                raise
            except _RETRYABLE as exc:
                attempt += 1
                if attempt > self._max_retries:
                    return self._replay(resolved, key, started, exc)
                self._sleep(self._delay(exc, attempt))
                continue
            if self._record and result.text.strip():
                self._cache.record(
                    resolved,
                    text=result.text,
                    model_version=result.model_version,
                    usage=result.usage,
                )
                self.recorded_count += 1
            return replace(result, latency_ms=(self._clock() - started) * 1000.0)

    def _delay(self, exc: Exception, attempt: int) -> float:
        if isinstance(exc, ProviderRateLimitError) and exc.retry_after is not None:
            return min(exc.retry_after, self._retry_after_cap)
        return min(0.5 * (2 ** (attempt - 1)), self._retry_after_cap)

    def _replay(self, request: LLMRequest, key: str, started: float, exc: Exception) -> LLMResult:
        entry = self._cache.get(key) if self._cache and key else None
        if entry is None:
            raise exc
        self.replayed_count += 1
        response = entry.get("response") or {}
        usage = response.get("usage") or {}
        return LLMResult(
            text=str(response.get("text") or ""),
            provider=self._llm.provider_name,
            model=request.model,
            model_version=str(response.get("model_version") or ""),
            usage=TokenUsage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            ),
            latency_ms=(self._clock() - started) * 1000.0,
            cached=True,
            notice=_CACHE_NOTICE,
        )


class _DisabledProvider:
    """Stands in for the hosted provider in cache-only mode; never reached.

    It keeps the configured provider name so replayed answers are still
    labelled with the provider that originally produced them (cached=true).
    """

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def complete(self, request: LLMRequest) -> LLMResult:
        raise ProviderUnavailableError("hosted provider disabled (LLM_CACHE_ONLY)")


def build_llm() -> LLMProvider:
    from app.ai_gateway.hosted import HostedProvider
    from app.ai_gateway.local_vllm import LocalVLLMProvider
    from app.config import get_settings

    settings = get_settings()
    if settings.llm_provider == "hosted":
        return HostedProvider(
            api_key=settings.hosted_api_key,
            base_url=settings.hosted_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.hosted_timeout_seconds,
        )
    if settings.llm_provider == "local_vllm":
        return LocalVLLMProvider(base_url=settings.local_vllm_base_url, model=settings.llm_model)
    raise ProviderNotConfiguredError(
        f"llm provider '{settings.llm_provider}' is not part of the demo build"
    )


@lru_cache
def get_gateway() -> AIGateway:
    from app.config import get_settings

    settings = get_settings()
    return AIGateway(
        _DisabledProvider(settings.llm_provider) if settings.llm_cache_only else build_llm(),
        cache=LLMResponseCache(settings.llm_response_cache_path),
        max_retries=settings.hosted_max_retries,
        record=settings.llm_cache_record,
        cache_only=settings.llm_cache_only,
    )


def reset_gateway() -> None:
    get_gateway.cache_clear()
