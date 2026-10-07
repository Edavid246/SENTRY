"""Local embedding tests (SPEC 8.1): run against the weights under data/models,
skipped when they are not present. Embeddings must be 1024-dim, L2-normalised
and deterministic."""

import math
from pathlib import Path

import pytest
from app.ai_gateway import LocalEmbeddingProvider, ProviderNotConfiguredError

WEIGHTS = (
    Path(__file__).resolve().parents[2] / "data" / "models" / "models--Xenova--bge-m3" / "snapshots"
)
pytestmark = pytest.mark.skipif(
    not any(WEIGHTS.glob("*/onnx/model_int8.onnx")),
    reason="embedding weights not present under data/models (download or image bake)",
)

SENTENCE_A = "Vehicle maintenance requires servicing every 500 operating hours."
SENTENCE_B = "The vehicle maintenance policy defines scheduled servicing intervals."
SENTENCE_C = "Runway condition normal, no active restrictions at airfield alpha."


@pytest.fixture(scope="module")
def embedder() -> LocalEmbeddingProvider:
    from app.config import get_settings

    settings = get_settings()
    return LocalEmbeddingProvider(
        model=settings.embedding_model,
        dim=settings.embedding_dim,
        cache_dir=settings.embedding_cache_dir,
    )


def test_vectors_have_configured_dimension(embedder: LocalEmbeddingProvider) -> None:
    vectors = embedder.embed([SENTENCE_A, SENTENCE_C])
    assert len(vectors) == 2
    assert all(len(vector) == 1024 for vector in vectors)


def test_vectors_are_l2_normalised(embedder: LocalEmbeddingProvider) -> None:
    (vector,) = embedder.embed([SENTENCE_A])
    norm = math.sqrt(sum(value * value for value in vector))
    assert norm == pytest.approx(1.0, abs=1e-3)


def test_embedding_is_deterministic(embedder: LocalEmbeddingProvider) -> None:
    first = embedder.embed([SENTENCE_A])
    second = embedder.embed([SENTENCE_A])
    assert first == second


def test_related_sentences_are_closer(embedder: LocalEmbeddingProvider) -> None:
    a, b, c = embedder.embed([SENTENCE_A, SENTENCE_B, SENTENCE_C])

    def cosine(left: list[float], right: list[float]) -> float:
        return sum(x * y for x, y in zip(left, right, strict=True))

    assert cosine(a, b) > cosine(a, c)


def test_empty_batch(embedder: LocalEmbeddingProvider) -> None:
    assert embedder.embed([]) == []


def test_unsupported_model_fails_closed() -> None:
    with pytest.raises(ProviderNotConfiguredError):
        LocalEmbeddingProvider(model="gte-base", dim=1024, cache_dir="data/models")


def test_dim_mismatch_fails_closed() -> None:
    with pytest.raises(ProviderNotConfiguredError):
        LocalEmbeddingProvider(model="bge-m3", dim=768, cache_dir="data/models")
