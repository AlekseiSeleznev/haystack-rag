from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from haystack import Document
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.document_stores.types import DuplicatePolicy

from haystack_rag.config import AppConfig, create_document_store, require_secret

try:
    from docling.document_converter import DocumentConverter
except Exception:
    DocumentConverter = None


TEXT_EXTENSIONS = {
    ".csv",
    ".html",
    ".htm",
    ".json",
    ".log",
    ".md",
    ".rst",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
DOCLING_EXTENSIONS = {".docx", ".pdf", ".pptx", ".xlsx"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index source documents into Qdrant.")
    parser.add_argument("--input-dir", default="data/input", help="Directory with source documents.")
    parser.add_argument(
        "--recreate-index",
        action="store_true",
        help="Drop and recreate the Qdrant collection before indexing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig.from_env()
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    converter = DocumentConverter() if DocumentConverter is not None else None
    documents = list(build_documents(input_dir=input_dir, config=config, converter=converter))
    if not documents:
        raise SystemExit("No indexable documents were found.")

    embedder = OpenAIDocumentEmbedder(
        api_key=require_secret(config.embedding_api_key, "EMBEDDING_API_KEY or OPENAI_API_KEY"),
        api_base_url=config.embedding_api_base_url,
        dimensions=config.embedding_dimensions,
        model=config.embedding_model,
        progress_bar=True,
    )
    embedded_documents = embedder.run(documents=documents)["documents"]

    document_store = create_document_store(config=config, recreate_index=args.recreate_index)
    written = document_store.write_documents(embedded_documents, policy=DuplicatePolicy.OVERWRITE)
    print(f"Indexed {written} chunks into '{config.qdrant_index}' from {input_dir}")


def build_documents(
    input_dir: Path,
    config: AppConfig,
    converter: DocumentConverter | None,
) -> Iterable[Document]:
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue

        text = extract_text(path=path, converter=converter)
        if not text:
            continue

        chunks = chunk_text(text=text, chunk_size=config.chunk_size, overlap=config.chunk_overlap)
        for chunk_index, chunk in enumerate(chunks):
            yield Document(
                content=chunk,
                meta={
                    "chunk_index": chunk_index,
                    "extension": path.suffix.lower(),
                    "source_name": path.name,
                    "source_path": str(path.relative_to(input_dir)),
                },
            )


def extract_text(path: Path, converter: DocumentConverter | None) -> str | None:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    if suffix in DOCLING_EXTENSIONS and converter is not None:
        try:
            result = converter.convert(str(path))
            document = result.document
            if hasattr(document, "export_to_markdown"):
                return document.export_to_markdown().strip()
            if hasattr(document, "export_to_text"):
                return document.export_to_text().strip()
        except Exception as exc:
            print(f"Skipping {path}: Docling conversion failed ({exc})")
            return None

    print(f"Skipping {path}: unsupported file type")
    return None


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = normalize_text(text)
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    text_length = len(normalized)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            split_at = normalized.rfind("\n\n", start, end)
            if split_at > start + chunk_size // 2:
                end = split_at
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(end - overlap, 0)

    return chunks


def normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


if __name__ == "__main__":
    main()
