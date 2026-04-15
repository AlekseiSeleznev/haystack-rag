from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Iterable

from haystack import Document
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.document_stores.types import DuplicatePolicy
from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder
from openpyxl import load_workbook
from pypdf import PdfReader
from docx import Document as DocxDocument
from pptx import Presentation

from haystack_rag.config import AppConfig, create_document_store, require_secret

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

RU_MARKERS = {"ru", "rus", "russian", "рус", "русский"}
EN_MARKERS = {"en", "eng", "english", "англ", "english-language"}
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index source documents into Qdrant.")
    parser.add_argument(
        "--input-dir",
        default=os.getenv("INPUT_DIR", "data/input"),
        help="Directory with source documents.",
    )
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

    documents = list(build_documents(input_dir=input_dir, config=config))
    if not documents:
        raise SystemExit("No indexable documents were found.")

    embedder = create_document_embedder(config)
    embedded_documents = embedder.run(documents=documents)["documents"]

    document_store = create_document_store(config=config, recreate_index=args.recreate_index)
    written = document_store.write_documents(embedded_documents, policy=DuplicatePolicy.OVERWRITE)
    print(f"Indexed {written} chunks into '{config.qdrant_index}' from {input_dir}")


def build_documents(
    input_dir: Path,
    config: AppConfig,
) -> Iterable[Document]:
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue

        text = extract_text(path=path)
        if not text:
            continue

        metadata = build_metadata(path=path, input_dir=input_dir, text=text)
        chunks = chunk_text(text=text, chunk_size=config.chunk_size, overlap=config.chunk_overlap)
        for chunk_index, chunk in enumerate(chunks):
            yield Document(
                content=chunk,
                meta={**metadata, "chunk_index": chunk_index},
            )


def create_document_embedder(config: AppConfig) -> OpenAIDocumentEmbedder | FastembedDocumentEmbedder:
    if config.embedding_provider == "openai":
        return OpenAIDocumentEmbedder(
            api_key=require_secret(config.embedding_api_key, "EMBEDDING_API_KEY or OPENAI_API_KEY"),
            api_base_url=config.embedding_api_base_url,
            dimensions=config.embedding_dimensions,
            model=config.embedding_model,
            progress_bar=True,
        )

    return FastembedDocumentEmbedder(
        model=config.embedding_model,
        cache_dir=config.fastembed_cache_path,
        prefix="passage: " if "e5" in config.embedding_model.lower() else "",
        progress_bar=True,
    )


def extract_text(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    try:
        if suffix == ".pdf":
            return extract_pdf_text(path)
        if suffix == ".docx":
            return extract_docx_text(path)
        if suffix == ".pptx":
            return extract_pptx_text(path)
        if suffix == ".xlsx":
            return extract_xlsx_text(path)
    except Exception as exc:
        print(f"Skipping {path}: parser failed ({exc})")
        return None

    print(f"Skipping {path}: unsupported file type")
    return None


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page.strip() for page in pages if page.strip())


def extract_docx_text(path: Path) -> str:
    document = DocxDocument(str(path))
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(parts)


def extract_pptx_text(path: Path) -> str:
    presentation = Presentation(str(path))
    parts: list[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            text = getattr(shape, "text", "")
            if text and text.strip():
                parts.append(text.strip())
    return "\n".join(parts)


def extract_xlsx_text(path: Path) -> str:
    workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
    parts: list[str] = []
    for sheet in workbook.worksheets:
        parts.append(f"# Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def build_metadata(path: Path, input_dir: Path, text: str) -> dict[str, object]:
    relative_path = path.relative_to(input_dir)
    parent_parts = relative_path.parts[:-1]
    domain_raw = parent_parts[0] if len(parent_parts) >= 1 else ""
    category_raw = parent_parts[1] if len(parent_parts) >= 2 else ""
    subcategory_raw = parent_parts[2] if len(parent_parts) >= 3 else ""
    source_dir = "" if relative_path.parent == Path(".") else str(relative_path.parent)

    return {
        "extension": path.suffix.lower(),
        "source_name": path.name,
        "source_name_norm": path.name.casefold(),
        "source_stem": path.stem,
        "source_stem_norm": path.stem.casefold(),
        "source_path": str(relative_path),
        "source_path_norm": str(relative_path).casefold(),
        "source_dir": source_dir,
        "source_dir_norm": source_dir.casefold(),
        "path_depth": len(parent_parts),
        "domain_raw": domain_raw,
        "domain": domain_raw.casefold(),
        "category_raw": category_raw,
        "category": category_raw.casefold(),
        "subcategory_raw": subcategory_raw,
        "subcategory": subcategory_raw.casefold(),
        "language_hint": infer_language_hint(relative_path=relative_path, text=text),
    }


def infer_language_hint(relative_path: Path, text: str) -> str:
    path_tokens = {
        token
        for token in re.split(r"[\W_]+", " ".join(relative_path.parts).casefold())
        if token
    }
    if path_tokens & RU_MARKERS:
        return "ru"
    if path_tokens & EN_MARKERS:
        return "en"

    sample = text[:4000]
    return "ru" if CYRILLIC_RE.search(sample) else "en"


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
