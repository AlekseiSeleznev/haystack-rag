FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG INSTALL_DOCLING=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY scripts /app/scripts

RUN chmod +x /app/scripts/start-hayhooks.sh \
    && pip install --upgrade pip \
    && if [ "$INSTALL_DOCLING" = "true" ]; then pip install -e '.[docling]'; else pip install -e .; fi

CMD ["bash", "/app/scripts/start-hayhooks.sh"]
