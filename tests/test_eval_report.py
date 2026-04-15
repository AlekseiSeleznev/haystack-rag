from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_retrieval import normalize_for_match, render_markdown_report


class EvalReportTests(unittest.TestCase):
    def test_normalize_for_match_repairs_split_words(self) -> None:
        normalized = normalize_for_match("Территориальные усло - вия")
        self.assertEqual(normalized, "территориальные условия")

    def test_render_single_markdown_report_includes_source_ref(self) -> None:
        markdown = render_markdown_report(
            {
                "summary": {
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "pass_rate": 100.0,
                    "reranking_mode": "auto",
                },
                "cases": [
                    {
                        "id": "north_bonus",
                        "success": True,
                        "question": "Северная надбавка территориальные условия",
                        "matched_rank": 1,
                        "matched_content_rank": 1,
                        "expected": ["1C/BOOKS/book.pdf"],
                        "expected_content": ["Территориальные условия"],
                        "reranking_mode": "auto",
                        "reranking_requested": True,
                        "reranking_applied": True,
                        "top_documents": [
                            {
                                "rank": 1,
                                "source_ref": "1C/BOOKS/book.pdf (pp.245-246)",
                                "score": 12.34,
                                "retrieval_score": 0.56,
                                "rerank_score": 12.34,
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn("# Retrieval Evaluation Report", markdown)
        self.assertIn("1C/BOOKS/book.pdf (pp.245-246)", markdown)

    def test_render_compare_markdown_report_includes_comparison_summary(self) -> None:
        markdown = render_markdown_report(
            {
                "reranking_on": {"summary": {"passed": 1, "total": 1, "pass_rate": 100.0}, "cases": []},
                "reranking_off": {"summary": {"passed": 0, "total": 1, "pass_rate": 0.0}, "cases": []},
                "comparison": {
                    "summary": {"improved": 1, "worsened": 0, "unchanged": 0},
                    "lines": ["north_bonus: improved (metric=content, on_rank=1, off_rank=miss)"],
                },
            }
        )

        self.assertIn("# Retrieval Reranking Comparison", markdown)
        self.assertIn("Improved: 1", markdown)
        self.assertIn("north_bonus: improved", markdown)


if __name__ == "__main__":
    unittest.main()
