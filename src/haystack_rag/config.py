from __future__ import annotations

import os
from dataclasses import dataclass

from haystack.utils import Secret
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


@dataclass(frozen=True)
class AppConfig:
    qdrant_url: str
    qdrant_index: str
    top_k: int
    chunk_size: int
    chunk_overlap: int
    pdf_extractor: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_api_key: str
    embedding_api_base_url: str | None
    fastembed_cache_path: str | None
    reranker_enabled: bool
    reranker_provider: str
    reranker_model: str
    reranker_candidates: int
    chat_provider: str
    chat_model: str
    chat_api_key: str
    chat_api_base_url: str | None

    @classmethod
    def from_env(cls) -> "AppConfig":
        shared_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        shared_api_base_url = _optional_env("OPENAI_API_BASE_URL")

        embedding_api_key = os.getenv("EMBEDDING_API_KEY", "").strip() or shared_api_key
        chat_api_key = os.getenv("CHAT_API_KEY", "").strip() or shared_api_key

        return cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333").strip(),
            qdrant_index=os.getenv("QDRANT_INDEX", "tech_docs").strip(),
            top_k=int(os.getenv("TOP_K", "8")),
            chunk_size=int(os.getenv("CHUNK_SIZE", "1400")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
            pdf_extractor=os.getenv("PDF_EXTRACTOR", "hybrid").strip().lower(),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "fastembed").strip().lower(),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            ).strip(),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "384")),
            embedding_api_key=embedding_api_key,
            embedding_api_base_url=_optional_env("EMBEDDING_API_BASE_URL") or shared_api_base_url,
            fastembed_cache_path=_optional_env("FASTEMBED_CACHE_PATH"),
            reranker_enabled=os.getenv("RERANKER_ENABLED", "true").strip().lower() == "true",
            reranker_provider=os.getenv("RERANKER_PROVIDER", "fastembed_late_interaction").strip().lower(),
            reranker_model=os.getenv(
                "RERANKER_MODEL",
                "answerdotai/answerai-colbert-small-v1",
            ).strip(),
            reranker_candidates=int(os.getenv("RERANKER_CANDIDATES", "24")),
            chat_provider=os.getenv("CHAT_PROVIDER", "disabled").strip().lower(),
            chat_model=os.getenv("CHAT_MODEL", "gpt-4o-mini").strip(),
            chat_api_key=chat_api_key,
            chat_api_base_url=_optional_env("CHAT_API_BASE_URL") or shared_api_base_url,
        )


def require_secret(value: str, name: str) -> Secret:
    if not value:
        raise RuntimeError(f"{name} is required")
    return Secret.from_token(value)


def create_document_store(config: AppConfig, recreate_index: bool = False) -> QdrantDocumentStore:
    return QdrantDocumentStore(
        url=config.qdrant_url,
        index=config.qdrant_index,
        embedding_dim=config.embedding_dimensions,
        recreate_index=recreate_index,
    )
