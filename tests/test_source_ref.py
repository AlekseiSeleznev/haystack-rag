from __future__ import annotations

import unittest

from haystack.dataclasses import Document

from haystack_rag.pipelines.search_wrapper import PipelineWrapper


class SourceReferenceTests(unittest.TestCase):
    def test_source_reference_uses_page_label(self) -> None:
        wrapper = PipelineWrapper.__new__(PipelineWrapper)
        document = Document(
            content="example",
            meta={
                "source_path": "1C/BOOKS/book.pdf",
                "page_label": "pp.245-246",
            },
        )

        self.assertEqual(
            wrapper._source_reference(document),
            "1C/BOOKS/book.pdf (pp.245-246)",
        )

    def test_source_reference_falls_back_to_source_path(self) -> None:
        wrapper = PipelineWrapper.__new__(PipelineWrapper)
        document = Document(content="example", meta={"source_path": "WORK/PUIG/doc.pdf"})
        self.assertEqual(wrapper._source_reference(document), "WORK/PUIG/doc.pdf")


if __name__ == "__main__":
    unittest.main()
