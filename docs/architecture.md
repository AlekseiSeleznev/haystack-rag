# Architecture

## Current Flow

1. Documents are placed into the host directory `/home/as/Документы/RAG_DOCS`.
2. The ingestion command parses files and chunks them.
3. Chunks are embedded with either:
   - local `fastembed`, or
   - an external OpenAI-compatible embedding API
4. Embedded chunks are stored in Qdrant.
5. Ingestion stores normalized metadata for retrieval filters:
   - `domain`, `category`, `subcategory`
   - `source_dir`, `source_name`, `extension`
   - `language_hint`
6. PDF extraction applies newline cleanup heuristics to reduce broken word-by-word chunks.
7. The default PDF parser path stays lightweight:
   - `pypdf` first
   - optional `Docling` fallback only when explicitly enabled as a heavy parser profile
8. Hayhooks exposes retrieval and answer generation.
9. Retrieval can optionally collapse repeated chunks by source using `collapse_sources`.
10. Open WebUI connects to Hayhooks through the OpenAI-compatible API by default in `docker-compose`.

## Design Rules

- Reindex from source files instead of migrating the old index.
- Validate retrieval before spending effort on answer synthesis.
- Keep the backend grounded in retrieved documentation.
- Keep the default dev stack runnable without external keys.
- Use external models only when they add clear quality value.
- Treat parser quality as a first-class concern.
- Verify retrieval quality with repeatable eval cases before enabling richer answer synthesis.
- Keep heavy parser dependencies isolated from the default runtime whenever possible.
- Prefer layout-aware extraction tools like `Docling` over LLM-based extraction for ingestion.
- Use OpenAI-compatible providers such as `Polza AI` primarily for answer generation or, later, for embeddings if eval proves benefit.
