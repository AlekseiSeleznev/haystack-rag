COMPOSE = docker compose

.PHONY: up down restart logs reindex eval eval-compare smoke

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

eval:
	python3 scripts/evaluate_retrieval.py --cases eval/retrieval_cases.json --fail-on-miss

eval-compare:
	python3 scripts/evaluate_retrieval.py --cases eval/retrieval_cases.json --compare-reranking

smoke:
	python3 scripts/smoke_test_stack.py
