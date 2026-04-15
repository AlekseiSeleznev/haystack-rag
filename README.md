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
8. `Hayhooks MCP` is exposed for Codex-compatible clients at `http://localhost:1417/mcp`.

## Current Scope

Implemented in this scaffold:
- base Docker stack
- Qdrant-backed retrieval wrapper for Hayhooks
- simple `search` API mode
- structured retrieval filters for `domain`, `category`, `subcategory`, `source_dir`, `source_name`, `extension`, `language_hint`
- optional source collapsing via `collapse_sources=true`
- late-interaction reranking over the retrieved candidate set
- chat completion mode for Open WebUI
- MCP endpoint for Codex and other MCP clients
- full reindex flow from raw source files
- local embedding fallback via `fastembed`
- retrieval evaluation script and sample case set
- page-level provenance for PDF chunks (`page_number` for single-page chunks, `page_start/page_end/page_label` for multi-page chunks)
- lightweight parser path:
  - text-like files are read directly
  - PDF via `pypdf` with newline cleanup heuristics and repair of broken word splits like `усло - вия`
  - DOCX via `python-docx`
  - PPTX via `python-pptx`
  - XLSX via `openpyxl`

Not implemented yet:
- multilingual query routing
- OCR-only path for scanned PDFs

## Commands

Start everything:

```bash
docker compose up -d
```

The compose stack exposes:
- `Open WebUI`: `http://localhost:3000`
- `Hayhooks OpenAI-compatible API`: `http://localhost:1416`
- `Hayhooks MCP`: `http://localhost:1417/mcp`
- `Qdrant`: `http://localhost:6333`

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

Run only a subset of cases:

```bash
python3 scripts/evaluate_retrieval.py --cases eval/retrieval_cases.json --case oauth
```

Fail the command when at least one case misses:

```bash
python3 scripts/evaluate_retrieval.py \
  --cases eval/retrieval_cases.json \
  --fail-on-miss
```

Save a JSON report:

```bash
python3 scripts/evaluate_retrieval.py \
  --cases eval/retrieval_cases.json \
  --output eval/report.json
```

Run the same evaluation with reranking forced off:

```bash
python3 scripts/evaluate_retrieval.py \
  --cases eval/retrieval_cases.json \
  --reranking off
```

Compare reranking on vs off on the same case set:

```bash
python3 scripts/evaluate_retrieval.py \
  --cases eval/retrieval_cases.json \
  --compare-reranking
```

When a case contains `expect_any_content_contains`, the comparison uses the content-hit rank rather than only the source-file rank.

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

The response includes:
- `reranking_enabled`: reranker is configured for the service
- `reranking_requested`: this request asked to use reranking
- `reranking_applied`: reranking was actually used for this request
- page metadata for PDF-backed chunks when available:
  - `page_number` for single-page chunks
  - `page_start`, `page_end`, `page_label` for multi-page chunks
- `retrieval_score` and `rerank_score` inside each document `meta`

Example source-collapsed retrieval request:

```bash
curl -X POST http://localhost:1416/doc_search/run \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "1С payroll SAP assignmentIdExternal wage type",
    "mode": "search",
    "top_k": 8,
    "collapse_sources": true
  }'
```

## Codex MCP Integration

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.haystack-rag]
url = "http://localhost:1417/mcp"
```

After updating the config, restart Codex or the VS Code Codex extension so it reloads MCP servers.

Once connected, Codex will see `doc_search` as an MCP tool and can call it directly with the same fields used by `/doc_search/run`, including:
- `question`
- `mode`
- `top_k`
- `domain`
- `category`
- `subcategory`
- `source_dir`
- `source_name`
- `extension`
- `language_hint`
- `collapse_sources`
- `group_by`
- `group_size`
- `score_threshold`

## Real-Question Workflow

Base evaluation set:
- [retrieval_cases.json](/home/as/Документы/AI_PROJECTS/haystack-rag/eval/retrieval_cases.json)

Template for your own real questions:
- [retrieval_cases.user-template.json](/home/as/Документы/AI_PROJECTS/haystack-rag/eval/retrieval_cases.user-template.json)

Each case can validate two things:
- `expect_any_source_contains`: the correct file appears in top-k
- `expect_any_content_contains`: at least one returned chunk contains an expected phrase from the right answer area

This is useful because a query can hit the right PDF but still land on the wrong chunk.

Recommended workflow:
1. Copy the template to `eval/retrieval_cases.user.json`.
2. Add your real questions, expected source paths, and a short phrase that should appear in the relevant chunk.
3. Run:

```bash
python3 scripts/evaluate_retrieval.py \
  --cases eval/retrieval_cases.user.json \
  --fail-on-miss \
  --output eval/retrieval_cases.user.report.json
```

4. If something misses, inspect the printed top source paths and refine:
- question wording
- metadata filters
- chunking / parser strategy
- retrieval or reranking settings

## Next Steps

1. Add a stronger evaluation set with real user queries and expected sources.
2. Improve parser strategy for difficult or scanned PDFs.
3. Consider hybrid retrieval if dense retrieval misses exact-reference queries.
4. Revisit answer mode only after `search_only` remains stable on the real corpus.
