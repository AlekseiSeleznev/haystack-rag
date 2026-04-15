# Architecture

## Current Flow

1. Documents are placed into `data/input/`.
2. The ingestion command parses files and chunks them.
3. Chunks are embedded with an external OpenAI-compatible embedding API.
4. Embedded chunks are stored in Qdrant.
5. Hayhooks exposes retrieval and answer generation.
6. Open WebUI connects to Hayhooks through the OpenAI-compatible API.

## Design Rules

- Reindex from source files instead of migrating the old index.
- Validate retrieval before spending effort on answer synthesis.
- Keep the backend grounded in retrieved documentation.
- Keep model inference external and cheap.
- Treat parser quality as a first-class concern.

