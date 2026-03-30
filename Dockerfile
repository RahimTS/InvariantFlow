FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# uv/container optimizations
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=0 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=8000

COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app/ ./app/
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}"]
