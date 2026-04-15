from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
from fastembed import LateInteractionTextEmbedding
from hayhooks import BasePipelineWrapper, get_last_user_message
from haystack import Pipeline
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage, Document
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder
from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever

from haystack_rag.config import AppConfig, create_document_store, require_secret


SYSTEM_PROMPT = """You answer only from the retrieved documentation context.
If the context is weak or incomplete, say so plainly.
Do not invent undocumented SAP or 1C details.
Prefer a concise answer with a short source list at the end."""


class PipelineWrapper(BasePipelineWrapper):
    def setup(self) -> None:
        self.config = AppConfig.from_env()
        self.document_store = create_document_store(self.config)
        self.query_embedder = self._create_query_embedder()
        self.retriever = QdrantEmbeddingRetriever(
            document_store=self.document_store,
            top_k=self.config.top_k,
        )
        self.reranker = self._create_reranker()
        self.answer_llm = self._create_answer_llm()

        self.pipeline = Pipeline()
        self.pipeline.add_component("query_embedder", self.query_embedder)
        self.pipeline.add_component("retriever", self.retriever)
        self.pipeline.connect("query_embedder.embedding", "retriever.query_embedding")

    def run_api(
        self,
        question: str,
        mode: str = "search",
        top_k: int | None = None,
        reranking: bool | None = None,
        collapse_sources: bool = False,
        group_by: str | None = None,
        group_size: int | None = None,
        domain: str | list[str] | None = None,
        category: str | list[str] | None = None,
        subcategory: str | list[str] | None = None,
        source_dir: str | list[str] | None = None,
        source_name: str | list[str] | None = None,
        extension: str | list[str] | None = None,
        language_hint: str | list[str] | None = None,
        filters: dict[str, Any] | list[dict[str, Any]] | None = None,
        score_threshold: float | None = None,
    ) -> dict[str, Any]:
        """Run retrieval over the indexed technical documentation."""
        applied_filters = self._build_filters(
            domain=domain,
            category=category,
            subcategory=subcategory,
            source_dir=source_dir,
            source_name=source_name,
            extension=extension,
            language_hint=language_hint,
            filters=filters,
        )
        documents = self._retrieve(
            question=question,
            top_k=top_k,
            reranking=reranking,
            filters=applied_filters,
            score_threshold=score_threshold,
            group_by=self._resolve_group_by(group_by=group_by, collapse_sources=collapse_sources),
            group_size=self._resolve_group_size(
                group_by=group_by,
                group_size=group_size,
                collapse_sources=collapse_sources,
            ),
        )
        reranking_requested = self._reranking_requested(reranking=reranking)
        reranking_applied = reranking_requested and self._resolve_group_by(
            group_by=group_by,
            collapse_sources=collapse_sources,
        ) is None

        result: dict[str, Any] = {
            "question": question,
            "mode": mode,
            "applied_filters": applied_filters,
            "reranking_enabled": self.reranker is not None,
            "reranking_requested": reranking_requested,
            "reranking_applied": reranking_applied,
            "group_by": self._resolve_group_by(group_by=group_by, collapse_sources=collapse_sources),
            "group_size": self._resolve_group_size(
                group_by=group_by,
                group_size=group_size,
                collapse_sources=collapse_sources,
            ),
            "documents": [self._serialize_document(document) for document in documents],
        }

        if mode == "answer":
            result["answer"] = self._answer(question=question, documents=documents)

        return result

    def run_chat_completion(self, model: str, messages: list[dict], body: dict) -> str:
        question = get_last_user_message(messages)
        if not question:
            return "I did not receive a user question."

        documents = self._retrieve(
            question=question,
            top_k=body.get("top_k"),
            reranking=body.get("reranking"),
            filters=self._build_filters(
                domain=body.get("domain"),
                category=body.get("category"),
                subcategory=body.get("subcategory"),
                source_dir=body.get("source_dir"),
                source_name=body.get("source_name"),
                extension=body.get("extension"),
                language_hint=body.get("language_hint"),
                filters=body.get("filters"),
            ),
            score_threshold=body.get("score_threshold"),
            group_by=self._resolve_group_by(
                group_by=body.get("group_by"),
                collapse_sources=body.get("collapse_sources", False),
            ),
            group_size=self._resolve_group_size(
                group_by=body.get("group_by"),
                group_size=body.get("group_size"),
                collapse_sources=body.get("collapse_sources", False),
            ),
        )
        return self._answer(question=question, documents=documents)

    def _retrieve(
        self,
        question: str,
        top_k: int | None = None,
        reranking: bool | None = None,
        filters: dict[str, Any] | list[dict[str, Any]] | None = None,
        score_threshold: float | None = None,
        group_by: str | None = None,
        group_size: int | None = None,
    ) -> list[Document]:
        requested_top_k = top_k or self.config.top_k
        retrieval_top_k = requested_top_k
        reranking_requested = self._reranking_requested(reranking=reranking)
        if reranking_requested and group_by is None:
            retrieval_top_k = max(requested_top_k, self.config.reranker_candidates)

        result = self.pipeline.run(
            data={
                "query_embedder": {"text": question},
                "retriever": {
                    "filters": filters,
                    "top_k": retrieval_top_k,
                    "score_threshold": score_threshold,
                    "group_by": group_by,
                    "group_size": group_size,
                },
            }
        )
        documents = result["retriever"]["documents"]
        if reranking_requested and documents and group_by is None:
            documents = self._rerank_documents(question=question, documents=documents, top_k=requested_top_k)
        else:
            documents = documents[:requested_top_k]
        return documents

    def _answer(self, question: str, documents: list[Document]) -> str:
        if not documents:
            return "No indexed context was found for this question. Rephrase the query or reindex the source documents."

        if self.answer_llm is None:
            return self._fallback_answer(question=question, documents=documents)

        context = self._format_context(documents)
        sources = self._format_sources(documents)
        response = self.answer_llm.run(
            messages=[
                ChatMessage.from_system(SYSTEM_PROMPT),
                ChatMessage.from_user(
                    f"Question:\n{question}\n\n"
                    f"Retrieved context:\n{context}\n\n"
                    "Write a grounded answer in the same language as the user question. "
                    "If the documentation is insufficient, say that explicitly."
                ),
            ]
        )
        answer = response["replies"][0].text.strip()
        return f"{answer}\n\nSources:\n{sources}"

    def _fallback_answer(self, question: str, documents: list[Document]) -> str:
        snippets: list[str] = []
        for index, document in enumerate(documents[:3], start=1):
            source_path = self._source_reference(document)
            content = (document.content or "").strip()
            snippets.append(f"[{index}] {source_path}\n{content[:700]}")

        return (
            "LLM answer mode is disabled because no chat provider is configured.\n\n"
            f"Question:\n{question}\n\n"
            "Top retrieved context:\n"
            + "\n\n".join(snippets)
        )

    def _format_context(self, documents: list[Document]) -> str:
        blocks: list[str] = []
        for index, document in enumerate(documents, start=1):
            source_path = self._source_reference(document)
            content = (document.content or "").strip()
            blocks.append(f"[{index}] {source_path}\n{content}")
        return "\n\n".join(blocks)

    def _format_sources(self, documents: list[Document]) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for document in documents:
            source_ref = self._source_reference(document)
            if source_ref in seen:
                continue
            seen.add(source_ref)
            lines.append(f"- {source_ref}")
        return "\n".join(lines)

    def _serialize_document(self, document: Document) -> dict[str, Any]:
        return {
            "id": document.id,
            "content": document.content,
            "meta": document.meta,
            "score": getattr(document, "score", None),
        }

    def _create_query_embedder(self) -> OpenAITextEmbedder | FastembedTextEmbedder:
        if self.config.embedding_provider == "openai":
            return OpenAITextEmbedder(
                api_key=require_secret(self.config.embedding_api_key, "EMBEDDING_API_KEY or OPENAI_API_KEY"),
                api_base_url=self.config.embedding_api_base_url,
                dimensions=self.config.embedding_dimensions,
                model=self.config.embedding_model,
            )

        return FastembedTextEmbedder(
            model=self.config.embedding_model,
            cache_dir=self.config.fastembed_cache_path,
            prefix=self._query_prefix(),
            progress_bar=False,
        )

    def _create_answer_llm(self) -> OpenAIChatGenerator | None:
        if self.config.chat_provider != "openai":
            return None

        return OpenAIChatGenerator(
            api_key=require_secret(self.config.chat_api_key, "CHAT_API_KEY or OPENAI_API_KEY"),
            api_base_url=self.config.chat_api_base_url,
            model=self.config.chat_model,
        )

    def _query_prefix(self) -> str:
        return "query: " if "e5" in self.config.embedding_model.lower() else ""

    def _create_reranker(self) -> LateInteractionTextEmbedding | None:
        if not self.config.reranker_enabled:
            return None
        if self.config.reranker_provider != "fastembed_late_interaction":
            return None
        try:
            return LateInteractionTextEmbedding(
                model_name=self.config.reranker_model,
                cache_dir=self.config.fastembed_cache_path,
                lazy_load=False,
            )
        except Exception as exc:
            print(f"Reranker disabled: failed to initialize '{self.config.reranker_model}' ({exc})")
            return None

    def _build_filters(
        self,
        domain: str | list[str] | None = None,
        category: str | list[str] | None = None,
        subcategory: str | list[str] | None = None,
        source_dir: str | list[str] | None = None,
        source_name: str | list[str] | None = None,
        extension: str | list[str] | None = None,
        language_hint: str | list[str] | None = None,
        filters: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        conditions: list[dict[str, Any]] = []
        self._add_filter_conditions(conditions, "meta.domain", domain, normalize=self._normalize_text_filter)
        self._add_filter_conditions(conditions, "meta.category", category, normalize=self._normalize_text_filter)
        self._add_filter_conditions(
            conditions,
            "meta.subcategory",
            subcategory,
            normalize=self._normalize_text_filter,
        )
        self._add_filter_conditions(
            conditions,
            "meta.source_dir_norm",
            source_dir,
            normalize=self._normalize_text_filter,
        )
        self._add_filter_conditions(
            conditions,
            "meta.source_name_norm",
            source_name,
            normalize=self._normalize_text_filter,
        )
        self._add_filter_conditions(
            conditions,
            "meta.extension",
            extension,
            normalize=self._normalize_extension_filter,
        )
        self._add_filter_conditions(
            conditions,
            "meta.language_hint",
            language_hint,
            normalize=self._normalize_text_filter,
        )

        if filters is None:
            return conditions or None
        if isinstance(filters, list):
            return conditions + filters
        return conditions + [filters]

    def _add_filter_conditions(
        self,
        conditions: list[dict[str, Any]],
        field: str,
        value: str | list[str] | None,
        normalize: Any,
    ) -> None:
        if value is None:
            return
        if isinstance(value, list):
            normalized_values = [normalize(item) for item in value if item is not None and str(item).strip()]
            if normalized_values:
                conditions.append({"field": field, "operator": "in", "value": normalized_values})
            return

        normalized_value = normalize(value)
        if normalized_value:
            conditions.append({"field": field, "operator": "==", "value": normalized_value})

    def _normalize_extension_filter(self, value: Any) -> str:
        text = str(value).strip().casefold()
        if not text:
            return ""
        return text if text.startswith(".") else f".{text}"

    def _normalize_text_filter(self, value: Any) -> str:
        return str(value).strip().casefold()

    def _rerank_documents(self, question: str, documents: list[Document], top_k: int) -> list[Document]:
        assert self.reranker is not None

        query_embedding = next(self.reranker.query_embed(question))
        document_texts = [document.content or "" for document in documents]
        document_embeddings = list(self.reranker.embed(document_texts, batch_size=16))

        rescored: list[tuple[float, Document]] = []
        for document, document_embedding in zip(documents, document_embeddings, strict=False):
            retrieval_score = float(getattr(document, "score", 0.0) or 0.0)
            rerank_score = self._late_interaction_score(query_embedding, document_embedding)
            updated_document = replace(
                document,
                score=rerank_score,
                meta={
                    **(document.meta or {}),
                    "retrieval_score": retrieval_score,
                    "rerank_score": rerank_score,
                },
            )
            rescored.append((rerank_score, updated_document))

        rescored.sort(key=lambda item: item[0], reverse=True)
        return [document for _, document in rescored[:top_k]]

    def _late_interaction_score(self, query_embedding: np.ndarray, document_embedding: np.ndarray) -> float:
        token_similarities = document_embedding @ query_embedding.T
        return float(token_similarities.max(axis=0).sum())

    def _resolve_group_by(self, group_by: str | None, collapse_sources: bool) -> str | None:
        if group_by:
            return group_by
        if collapse_sources:
            return "meta.source_path"
        return None

    def _resolve_group_size(
        self,
        group_by: str | None,
        group_size: int | None,
        collapse_sources: bool,
    ) -> int | None:
        if group_size is not None:
            return group_size
        if group_by or collapse_sources:
            return 1
        return None

    def _reranking_requested(self, reranking: bool | None) -> bool:
        if reranking is None:
            return self.reranker is not None
        return bool(reranking) and self.reranker is not None

    def _source_reference(self, document: Document) -> str:
        source_path = str(document.meta.get("source_path", "unknown"))
        page_number = document.meta.get("page_number")
        if page_number is None:
            return source_path
        return f"{source_path} (p.{page_number})"
