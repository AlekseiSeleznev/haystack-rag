# haystack-rag

`haystack-rag` is a fresh RAG stack for technical documentation.

Current target architecture:
- `Qdrant` for vector storage
- `Haystack` for retrieval and orchestration
- `Hayhooks` for HTTP and OpenAI-compatible endpoints
- `Open WebUI` for operator and test UI
- local multilingual embeddings by default
- optional external API models for embeddings and answer synthesis

Current non-goal:
- do not migrate the old `qdrant-loader` index

## Project Layout

- `config/pipelines/`: Hayhooks auto-deployed pipeline wrappers
- `data/input/`: local fixtures and smoke-test inputs
- `data/qdrant/`: local Qdrant storage
- `docs/`: architecture notes
- `eval/`: retrieval evaluation cases
- `scripts/`: local helper scripts
- `src/haystack_rag/`: application code

Default external source directory:
- host path: `/home/as/Документы/RAG_DOCS`
- container path: `/documents/rag_docs`

## First Run

1. Copy env template:

```bash
cp .env.example .env
```

2. Fill at least:
- nothing, if you want local retrieval-only mode
- `OPENAI_API_KEY`, if you want OpenAI-compatible providers
- `EMBEDDING_PROVIDER=openai`, if you want external embeddings
- `CHAT_PROVIDER=openai`, if you want LLM answers instead of retrieval-only fallback

3. Put source files into `/home/as/Документы/RAG_DOCS`.
Nested subfolders are indexed and preserved in `source_path` metadata.

4. Start the base stack:

```bash
docker compose up -d qdrant hayhooks open-webui
```

5. Run a full reindex:

```bash
docker compose run --rm ingestion python -m haystack_rag.ingestion.index_documents --input-dir /documents/rag_docs --recreate-index
```

6. Open `http://localhost:3000`.

7. `Open WebUI` is preconfigured to use `Hayhooks` as an OpenAI-compatible backend.
If you connect to `Hayhooks` directly from outside Docker, use `http://localhost:1416/v1`.

## Current Scope

Implemented in this scaffold:
- base Docker stack
- Qdrant-backed retrieval wrapper for Hayhooks
- simple `search` API mode
- structured retrieval filters for `domain`, `category`, `subcategory`, `source_dir`, `source_name`, `extension`, `language_hint`
- chat completion mode for Open WebUI
- full reindex flow from raw source files
- local embedding fallback via `fastembed`
- retrieval evaluation script and sample case set
- lightweight parser path:
  - text-like files are read directly
  - PDF via `pypdf`
  - DOCX via `python-docx`
  - PPTX via `python-pptx`
  - XLSX via `openpyxl`

Not implemented yet:
- reranking
- multilingual query routing
- OCR-only path for scanned PDFs

## Commands

Start everything:

```bash
docker compose up -d
```

Rebuild the index from scratch:

```bash
docker compose run --rm ingestion python -m haystack_rag.ingestion.index_documents --input-dir /documents/rag_docs --recreate-index
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

Run retrieval evaluation:

```bash
python3 scripts/evaluate_retrieval.py --cases eval/retrieval_cases.json
```

Example filtered retrieval request:

```bash
curl -X POST http://localhost:1416/doc_search/run \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Настольная книга по оплате труда и ее расчету в 1С",
    "mode": "search",
    "domain": "1c",
    "category": "books",
    "language_hint": "ru"
  }'
```

## Next Steps

1. Add reranking after dense retrieval is validated.
2. Improve parser strategy for difficult PDFs.
3. Expand the evaluation case set with real user queries.
4. Revisit answer mode only after `search_only` is stable.
