FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends mediainfo \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src

FROM base AS runtime

RUN pip install ".[gpio]" \
  && useradd --system --uid 1000 --create-home briefcase

USER briefcase
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
CMD ["briefcase-controller"]

FROM base AS test

RUN pip install -e ".[dev]"
COPY tests ./tests
CMD ["sh", "-c", "ruff check . && ruff format --check . && pytest -q"]
