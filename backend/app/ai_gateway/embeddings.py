"""Local embedding provider (SPEC 8.1): fastembed + ONNX, always on-device.

Embeddings never leave the machine (AGENTS.md). The model name comes from
configuration; the demo build registers one supported recipe — BGE-M3 as the
int8 ONNX export from Xenova, mean-pooled and L2-normalised — and fails
closed for anything else.
"""

import threading
from collections.abc import Sequence
from functools import lru_cache

from app.ai_gateway.base import ProviderNotConfiguredError, ProviderResponseError

SUPPORTED_MODELS: dict[str, dict[str, object]] = {
    "bge-m3": {
        "hf_repo": "Xenova/bge-m3",
        "model_file": "onnx/model_int8.onnx",
        "dim": 1024,
        "size_in_GB": 0.57,
        "license": "mit",
        "description": "BGE-M3 int8 ONNX (Xenova export), local embedding model",
    }
}


class LocalEmbeddingProvider:
    provider_name = "local"

    _registered: set[str] = set()
    _registry_lock = threading.Lock()

    def __init__(self, *, model: str, dim: int, cache_dir: str) -> None:
        spec = SUPPORTED_MODELS.get(model)
        if spec is None:
            supported = ", ".join(sorted(SUPPORTED_MODELS))
            raise ProviderNotConfiguredError(
                f"embedding model '{model}' is not supported in this build "
                f"(supported: {supported}; see docs/STUBS.md)"
            )
        if int(spec["dim"]) != dim:
            raise ProviderNotConfiguredError(
                f"embedding model '{model}' produces {spec['dim']}-dim vectors, "
                f"configuration expects {dim}"
            )
        self.model_name = model
        self.dim = dim
        self._cache_dir = cache_dir
        self._model: object | None = None
        self._lock = threading.Lock()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        raw = self._ensure().embed(items)
        vectors = [[float(x) for x in vector] for vector in raw]
        if len(vectors[0]) != self.dim:
            raise ProviderResponseError(
                f"embedding model returned {len(vectors[0])}-dim vectors, expected {self.dim}"
            )
        return vectors

    def _ensure(self) -> object:
        with self._lock:
            if self._model is None:
                self._register(self.model_name)
                from fastembed.text.custom_text_embedding import CustomTextEmbedding

                self._model = CustomTextEmbedding(
                    model_name=self.model_name, cache_dir=self._cache_dir
                )
            return self._model

    @classmethod
    def _register(cls, name: str) -> None:
        with cls._registry_lock:
            if name in cls._registered:
                return
            from fastembed.common.model_description import (
                DenseModelDescription,
                ModelSource,
                PoolingType,
            )
            from fastembed.text.custom_text_embedding import CustomTextEmbedding

            spec = SUPPORTED_MODELS[name]
            description = DenseModelDescription(
                model=name,
                sources=ModelSource(hf=str(spec["hf_repo"])),
                model_file=str(spec["model_file"]),
                dim=int(spec["dim"]),
                description=str(spec["description"]),
                license=str(spec["license"]),
                size_in_GB=float(spec["size_in_GB"]),
            )
            CustomTextEmbedding.add_model(description, pooling=PoolingType.MEAN, normalization=True)
            cls._registered.add(name)


@lru_cache
def get_embedder() -> LocalEmbeddingProvider:
    from app.config import get_settings

    settings = get_settings()
    if settings.embedding_provider != "local":
        raise ProviderNotConfiguredError(
            f"embedding provider '{settings.embedding_provider}' is not part of the demo build"
        )
    return LocalEmbeddingProvider(
        model=settings.embedding_model,
        dim=settings.embedding_dim,
        cache_dir=settings.embedding_cache_dir,
    )


def reset_embedder() -> None:
    get_embedder.cache_clear()
