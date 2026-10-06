FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY referentiel ./referentiel
COPY sql ./sql

RUN useradd --uid 10001 --create-home pipeline && mkdir -p /app/data && chown pipeline /app/data
USER pipeline
EXPOSE 8000
