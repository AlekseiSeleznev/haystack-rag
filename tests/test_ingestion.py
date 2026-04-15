from __future__ import annotations

import unittest

from haystack_rag.ingestion.index_documents import (
    SourceUnit,
    clean_docling_text,
    clean_pdf_text,
    combine_source_units,
    infer_extractor,
    resolve_page_metadata,
    should_retry_pdf_with_docling,
)


class IngestionTests(unittest.TestCase):
    def test_clean_pdf_text_repairs_split_words(self) -> None:
        text = "Территориальные усло - вия и рас - положено"
        cleaned = clean_pdf_text(text)
        self.assertIn("условия", cleaned)
        self.assertIn("расположено", cleaned)
        self.assertNotIn("усло - вия", cleaned)

    def test_combine_source_units_tracks_page_spans(self) -> None:
        text, spans = combine_source_units(
            [
                SourceUnit(text="first page", meta={"page_number": 10}),
                SourceUnit(text="second page", meta={"page_number": 11}),
            ]
        )

        self.assertEqual(text, "first page\n\nsecond page")
        self.assertEqual(
            spans,
            [
                {"page_number": 10, "start": 0, "end": 10},
                {"page_number": 11, "start": 12, "end": 23},
            ],
        )

    def test_resolve_page_metadata_single_page(self) -> None:
        metadata = resolve_page_metadata(
            page_spans=[{"page_number": 10, "start": 0, "end": 100}],
            start=10,
            end=40,
        )

        self.assertEqual(metadata["page_number"], 10)
        self.assertEqual(metadata["page_label"], "p.10")
        self.assertEqual(metadata["page_start"], 10)
        self.assertEqual(metadata["page_end"], 10)

    def test_resolve_page_metadata_multi_page(self) -> None:
        metadata = resolve_page_metadata(
            page_spans=[
                {"page_number": 10, "start": 0, "end": 100},
                {"page_number": 11, "start": 100, "end": 200},
            ],
            start=80,
            end=120,
        )

        self.assertNotIn("page_number", metadata)
        self.assertEqual(metadata["page_start"], 10)
        self.assertEqual(metadata["page_end"], 11)
        self.assertEqual(metadata["page_label"], "pp.10-11")

    def test_should_retry_pdf_with_docling_for_empty_or_sparse_text(self) -> None:
        self.assertTrue(should_retry_pdf_with_docling([]))
        self.assertTrue(
            should_retry_pdf_with_docling(
                [
                    SourceUnit(text="short text", meta={"page_number": 1, "extractor": "pypdf"}),
                    SourceUnit(text="", meta={"page_number": 2, "extractor": "pypdf"}),
                ]
            )
        )

    def test_should_not_retry_pdf_with_docling_for_healthy_extract(self) -> None:
        units = [
            SourceUnit(
                text="Это длинный и нормальный текст страницы " * 10,
                meta={"page_number": 1, "extractor": "pypdf"},
            ),
            SourceUnit(
                text="Это ещё один длинный и нормальный текст страницы " * 10,
                meta={"page_number": 2, "extractor": "pypdf"},
            ),
        ]
        self.assertFalse(should_retry_pdf_with_docling(units))

    def test_clean_docling_text_preserves_structure(self) -> None:
        text = "## Header\n\n\nParagraph\t\twith  spaces"
        cleaned = clean_docling_text(text)
        self.assertEqual(cleaned, "## Header\n\nParagraph with spaces")

    def test_infer_extractor_from_source_units(self) -> None:
        extractor = infer_extractor([SourceUnit(text="text", meta={"extractor": "docling"})])
        self.assertEqual(extractor, "docling")


if __name__ == "__main__":
    unittest.main()
