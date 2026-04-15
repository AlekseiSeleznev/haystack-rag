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
    embedding_model: str
    embedding_dimensions: int
    embedding_api_key: str
    embedding_api_base_url: str | None
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
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1536")),
            embedding_api_key=embedding_api_key,
            embedding_api_base_url=_optional_env("EMBEDDING_API_BASE_URL") or shared_api_base_url,
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

