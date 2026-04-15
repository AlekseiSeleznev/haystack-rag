COMPOSE = docker compose

.PHONY: up down restart logs reindex reindex-pypdf reindex-hybrid reindex-docling build-docling eval eval-compare eval-report smoke test

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart hayhooks hayhooks-mcp open-webui

logs:
	$(COMPOSE) logs -f hayhooks open-webui

reindex:
	$(COMPOSE) run --rm ingestion python -m haystack_rag.ingestion.index_documents --input-dir /documents/rag_docs --recreate-index

reindex-pypdf:
	PDF_EXTRACTOR=pypdf $(COMPOSE) run --rm ingestion python -m haystack_rag.ingestion.index_documents --input-dir /documents/rag_docs --recreate-index

reindex-hybrid:
	PDF_EXTRACTOR=hybrid $(COMPOSE) run --rm ingestion python -m haystack_rag.ingestion.index_documents --input-dir /documents/rag_docs --recreate-index

reindex-docling:
	PDF_EXTRACTOR=docling $(COMPOSE) run --rm ingestion python -m haystack_rag.ingestion.index_documents --input-dir /documents/rag_docs --recreate-index

build-docling:
	INSTALL_DOCLING=true $(COMPOSE) build ingestion hayhooks hayhooks-mcp

eval:
	python3 scripts/evaluate_retrieval.py --cases eval/retrieval_cases.json --fail-on-miss

eval-compare:
	python3 scripts/evaluate_retrieval.py --cases eval/retrieval_cases.json --compare-reranking

eval-report:
	python3 scripts/evaluate_retrieval.py --cases eval/retrieval_cases.json --fail-on-miss --output eval/report.json --markdown-output eval/report.md

smoke:
	python3 scripts/smoke_test_stack.py

test:
	$(COMPOSE) run --rm ingestion python -m unittest discover -s /app/tests -v
