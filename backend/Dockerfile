# syntax=docker/dockerfile:1
# Build context is the repository root (pyproject.toml + uv.lock live there).

FROM ghcr.io/astral-sh/uv:0.11.2 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Dependency layer, cached until the lockfile changes.
COPY .python-version pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Baked local embedding weights (BGE-M3 int8 ONNX, ~570 MB, gitignored on the
# host and copied into the image so the container never downloads models).
# Lives outside /app/data because ../data is bind-mounted over it at runtime.
ENV EMBEDDING_CACHE_DIR=/app/models \
    LLM_RESPONSE_CACHE_PATH=/app/data/demo_llm_cache.json
COPY data/models /app/models
RUN f="$(ls /app/models/models--Xenova--bge-m3/snapshots/*/onnx/model_int8.onnx)" \
    && [ "$(stat -Lc %s "$f")" -gt 100000000 ]

# Application source; project installed editable so --reload picks up binds.
COPY backend ./backend
RUN uv sync --frozen --no-dev

# git powers the layer-2 audit ledger; the ledger bind mount is owned by the
# host user while the container runs as root, hence the safe.directory entry.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory /ledger

EXPOSE 8001
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
