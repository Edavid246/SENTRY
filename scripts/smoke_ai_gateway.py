#!/usr/bin/env python3
"""AI gateway smoke test: local embedding round trip + one hosted LLM call.

Run from the repository root, with the API key in the environment:

    set -a && . ./.env && set +a
    uv run python scripts/smoke_ai_gateway.py            # live call, no write
    uv run python scripts/smoke_ai_gateway.py --record   # live call, prefills cache
    uv run python scripts/smoke_ai_gateway.py --cache-only  # offline replay

The API key itself is never printed. Canned answers are demo shortcuts
(docs/PRODUCTION_DEBT.md).
"""

import argparse
import math
import sys
import time

from app.ai_gateway import (
    AIGateway,
    ChatMessage,
    LLMRequest,
    LLMResponseCache,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderUnavailableError,
)
from app.ai_gateway.embeddings import get_embedder
from app.ai_gateway.gateway import build_llm
from app.config import get_settings

DEMO_SYSTEM = (
    "You are the Defence Gateway demo assistant. All data referenced is fictitious "
    "demo data. Answer in at most three sentences."
)
DEMO_QUESTION = "Summarise the key requirements of the vehicle maintenance policy."

EMBED_SENTENCES = (
    "The vehicle maintenance policy requires scheduled servicing every 500 operating hours.",
    "Airfield alpha reports runway condition normal and no active restrictions.",
)


class OfflineProvider:
    provider_name = "offline"

    def complete(self, request: LLMRequest):
        raise ProviderUnavailableError("offline mode (--cache-only): provider not called")


def print_settings() -> None:
    settings = get_settings()
    key_state = "set (redacted)" if settings.hosted_api_key else "missing"
    print("== settings")
    print(f"  llm_provider           : {settings.llm_provider}")
    print(f"  llm_model              : {settings.llm_model or '(empty)'}")
    print(f"  hosted_base_url        : {settings.hosted_base_url}")
    print(f"  hosted_api_key         : {key_state}")
    print(f"  hosted_timeout_seconds : {settings.hosted_timeout_seconds:g}")
    print(f"  embedding_provider     : {settings.embedding_provider}")
    print(f"  embedding_model        : {settings.embedding_model}")
    print(f"  embedding_dim          : {settings.embedding_dim}")
    print(f"  embedding_cache_dir    : {settings.embedding_cache_dir}")
    print(f"  llm_response_cache_path: {settings.llm_response_cache_path}")


def run_embedder() -> None:
    print("== local embedding")
    try:
        embedder = get_embedder()
        started = time.perf_counter()
        vectors = embedder.embed(list(EMBED_SENTENCES))
    except Exception as exc:
        print(f"  FAILED                 : {exc}", file=sys.stderr)
        print(
            "  embedding weights missing under data/models "
            "(downloaded from HuggingFace once; baked into the image at build)",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    elapsed = (time.perf_counter() - started) * 1000.0
    norms = [math.sqrt(sum(value * value for value in vector)) for vector in vectors]
    dot = sum(a * b for a, b in zip(vectors[0], vectors[1], strict=True))
    cosine = dot / (norms[0] * norms[1])
    print(f"  provider               : {embedder.provider_name}")
    print(f"  model                  : {embedder.model_name}")
    print(f"  vectors                : {len(vectors)} x {len(vectors[0])}")
    print(f"  norms                  : {norms[0]:.6f}, {norms[1]:.6f}")
    print(f"  cosine similarity      : {cosine:.4f}")
    print(f"  latency_ms             : {elapsed:.1f}")


def build_request(settings) -> LLMRequest:
    return LLMRequest(
        messages=(ChatMessage("user", DEMO_QUESTION),),
        model=settings.llm_model,
        temperature=0.0,
        max_output_tokens=1024,
        system=DEMO_SYSTEM,
    )


def run_llm(mode: str) -> None:
    settings = get_settings()
    request = build_request(settings)
    cache = LLMResponseCache(settings.llm_response_cache_path)
    key = cache.key(request)
    print(f"== hosted LLM ({mode})")
    print(f"  cache_key              : {key[:16]}…")

    if mode == "cache-only":
        gateway = AIGateway(OfflineProvider(), cache=cache, max_retries=0)
    else:
        gateway = AIGateway(build_llm(), cache=cache, max_retries=settings.hosted_max_retries)

    started = time.perf_counter()
    try:
        result = gateway.complete(request)
    except ProviderNotConfiguredError as exc:
        print(f"  NOT CONFIGURED         : {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except ProviderError as exc:
        if mode == "cache-only":
            print(f"  no cached answer       : {exc}", file=sys.stderr)
            print(
                "  run scripts/smoke_ai_gateway.py --record while online first",
                file=sys.stderr,
            )
        else:
            print(f"  PROVIDER FAILED        : {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    elapsed = (time.perf_counter() - started) * 1000.0

    if mode == "record":
        cache.record(
            request, text=result.text, model_version=result.model_version, usage=result.usage
        )
        print("  cache                  : recorded")

    print(f"  provider               : {result.provider}")
    print(f"  model                  : {result.model}")
    print(f"  model_version          : {result.model_version or '(none)'}")
    print(f"  cached                 : {result.cached}")
    if result.notice:
        print(f"  notice                 : {result.notice}")
    print(
        "  usage                  : "
        f"prompt={result.usage.prompt_tokens} "
        f"completion={result.usage.completion_tokens} "
        f"total={result.usage.total_tokens}"
    )
    print(f"  latency_ms (gateway)   : {elapsed:.1f}")
    print(f"  latency_ms (provider)  : {result.latency_ms:.1f}")
    print("  answer:")
    for line in result.text.splitlines() or ["(empty)"]:
        print(f"    {line}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description="AI gateway smoke test")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--record", action="store_true", help="live call, then write the cache")
    group.add_argument("--cache-only", action="store_true", help="replay from cache, no network")
    args = parser.parse_args()
    mode = "record" if args.record else "cache-only" if args.cache_only else "live"

    print_settings()
    run_embedder()
    run_llm(mode)
    print("smoke_ai_gateway: OK")


if __name__ == "__main__":
    main()
