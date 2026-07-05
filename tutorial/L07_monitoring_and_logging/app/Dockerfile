FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN useradd -m -u 1001 appuser
WORKDIR /app
COPY pyproject.toml ./
RUN uv lock && uv sync --frozen --no-dev --no-install-project
COPY app.py .
RUN mkdir -p /data && chown appuser:appuser /data
ENV UV_CACHE_DIR=/tmp/uv-cache
USER 1001
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
