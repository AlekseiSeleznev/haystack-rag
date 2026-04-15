# haystack-rag

`haystack-rag` is a fresh RAG stack for technical documentation.

Current target architecture:
- `Qdrant` for vector storage
- `Haystack` for retrieval and orchestration
- `Hayhooks` for HTTP and OpenAI-compatible endpoints
- `Open WebUI` for operator and test UI
- external API models for embeddings and answer synthesis

Current non-goal:
- do not migrate the old `qdrant-loader` index

## Project Layout

- `config/pipelines/`: Hayhooks auto-deployed pipeline wrappers
- `data/input/`: source documents for indexing
- `data/qdrant/`: local Qdrant storage
- `docs/`: architecture notes
- `scripts/`: local helper scripts
- `src/haystack_rag/`: application code

## First Run

1. Copy env template:

```bash
cp .env.example .env
```

2. Fill at least:
- `OPENAI_API_KEY`
- `EMBEDDING_MODEL`
- `CHAT_MODEL`

3. Put source files into `data/input/`.

4. Start the base stack:

```bash
docker compose up -d qdrant hayhooks open-webui
```

5. Run a full reindex:

```bash
docker compose run --rm ingestion --recreate-index
```

6. Open `http://localhost:3000`.

7. In Open WebUI add Hayhooks as an OpenAI-compatible connection:
- API Base URL: `http://hayhooks:1416/v1`
- API Key: any value

If you connect from outside Docker, use `http://localhost:1416/v1`.

## Current Scope

Implemented in this scaffold:
- base Docker stack
- Qdrant-backed retrieval wrapper for Hayhooks
- simple `search` API mode
- chat completion mode for Open WebUI
- full reindex flow from raw source files
- parser fallback path:
  - text-like files are read directly
  - PDF/DOCX/PPTX/XLSX attempt Docling conversion

Not implemented yet:
- reranking
- multilingual query routing
- OCR-only path for scanned PDFs
- folder/source filtering in retrieval
- evaluation harness

## Commands

Start everything:

```bash
docker compose up -d
```

Rebuild the index from scratch:

```bash
docker compose run --rm ingestion --recreate-index
```

Incremental indexing:

```bash
docker compose run --rm ingestion
```

Follow logs:

```bash
docker compose logs -f hayhooks
docker compose logs -f open-webui
```

## Next Steps

1. Add reranking after dense retrieval is validated.
2. Improve parser strategy for difficult PDFs.
3. Add structured source filters.
4. Add evaluation queries for SAP / 1C docs.
5. Revisit answer mode only after `search_only` is stable.

