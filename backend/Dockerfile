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

# Application source; project installed editable so --reload picks up binds.
COPY backend ./backend
RUN uv sync --frozen --no-dev

EXPOSE 8001
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
