from __future__ import annotations

from typing import Any

from hayhooks import BasePipelineWrapper, get_last_user_message
from haystack import Pipeline
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage, Document
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
        self.query_embedder = OpenAITextEmbedder(
            api_key=require_secret(self.config.embedding_api_key, "EMBEDDING_API_KEY or OPENAI_API_KEY"),
            api_base_url=self.config.embedding_api_base_url,
            dimensions=self.config.embedding_dimensions,
            model=self.config.embedding_model,
        )
        self.retriever = QdrantEmbeddingRetriever(
            document_store=self.document_store,
            top_k=self.config.top_k,
        )
        self.answer_llm = OpenAIChatGenerator(
            api_key=require_secret(self.config.chat_api_key, "CHAT_API_KEY or OPENAI_API_KEY"),
            api_base_url=self.config.chat_api_base_url,
            model=self.config.chat_model,
        )

        self.pipeline = Pipeline()
        self.pipeline.add_component("query_embedder", self.query_embedder)
        self.pipeline.add_component("retriever", self.retriever)
        self.pipeline.connect("query_embedder.embedding", "retriever.query_embedding")

    def run_api(self, question: str, mode: str = "search", top_k: int | None = None) -> dict[str, Any]:
        """Run retrieval over the indexed technical documentation."""
        documents = self._retrieve(question=question, top_k=top_k)

        result: dict[str, Any] = {
            "question": question,
            "mode": mode,
            "documents": [self._serialize_document(document) for document in documents],
        }

        if mode == "answer":
            result["answer"] = self._answer(question=question, documents=documents)

        return result

    def run_chat_completion(self, model: str, messages: list[dict], body: dict) -> str:
        question = get_last_user_message(messages)
        if not question:
            return "I did not receive a user question."

        documents = self._retrieve(question=question, top_k=body.get("top_k"))
        return self._answer(question=question, documents=documents)

    def _retrieve(self, question: str, top_k: int | None = None) -> list[Document]:
        result = self.pipeline.run(
            data={
                "query_embedder": {"text": question},
                "retriever": {"top_k": top_k or self.config.top_k},
            }
        )
        return result["retriever"]["documents"]

    def _answer(self, question: str, documents: list[Document]) -> str:
        if not documents:
            return "No indexed context was found for this question. Rephrase the query or reindex the source documents."

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

    def _format_context(self, documents: list[Document]) -> str:
        blocks: list[str] = []
        for index, document in enumerate(documents, start=1):
            source_path = document.meta.get("source_path", "unknown")
            content = (document.content or "").strip()
            blocks.append(f"[{index}] {source_path}\n{content}")
        return "\n\n".join(blocks)

    def _format_sources(self, documents: list[Document]) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for document in documents:
            source_path = str(document.meta.get("source_path", "unknown"))
            if source_path in seen:
                continue
            seen.add(source_path)
            lines.append(f"- {source_path}")
        return "\n".join(lines)

    def _serialize_document(self, document: Document) -> dict[str, Any]:
        return {
            "id": document.id,
            "content": document.content,
            "meta": document.meta,
            "score": getattr(document, "score", None),
        }

