# Python + uv Dockerfile Reference

Use this baseline for uv-managed Python services.

```dockerfile
# Build: docker build -t <image-name> .
# Run:   docker run -d -p 8000:8000 <image-name>

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

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
```

Notes:
- Change `APP_PORT` if needed, then map host/container ports accordingly.
- Keep `uv.lock` committed so `--frozen` works in CI/builds.
