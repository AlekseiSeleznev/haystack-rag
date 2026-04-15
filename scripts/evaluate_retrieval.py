from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib import request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality against a case file.")
    parser.add_argument(
        "--endpoint",
        default="http://localhost:1416/doc_search/run",
        help="Hayhooks retrieval endpoint.",
    )
    parser.add_argument(
        "--cases",
        default="eval/retrieval_cases.json",
        help="Path to evaluation cases JSON file.",
    )
    parser.add_argument("--top-k", type=int, default=8, help="Top-K documents to request.")
    parser.add_argument("--output", default="", help="Optional path to save the JSON report.")
    parser.add_argument(
        "--case",
        default="",
        help="Optional substring filter for case id or question.",
    )
    parser.add_argument(
        "--show-top",
        type=int,
        default=3,
        help="How many top returned source paths to print per case.",
    )
    parser.add_argument(
        "--fail-on-miss",
        action="store_true",
        help="Exit with code 1 if at least one case fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases_path = Path(args.cases).resolve()
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if args.case:
        needle = args.case.casefold()
        cases = [
            case
            for case in cases
            if needle in case["id"].casefold() or needle in case["request"]["question"].casefold()
        ]

    report: list[dict[str, Any]] = []
    passed = 0
    for case in cases:
        payload = dict(case["request"])
        payload.setdefault("mode", "search")
        payload.setdefault("top_k", args.top_k)
        response = post_json(args.endpoint, payload)

        documents = response["result"]["documents"]
        source_paths = [str(document.get("meta", {}).get("source_path", "")) for document in documents]
        expected_substrings = case.get("expect_any_source_contains", [])
        matched_rank = find_match_rank(source_paths, expected_substrings)
        success = matched_rank is not None
        if success:
            passed += 1

        entry = {
            "id": case["id"],
            "question": payload["question"],
            "success": success,
            "matched_rank": matched_rank,
            "expected": expected_substrings,
            "returned_source_paths": source_paths,
            "top_documents": [
                {
                    "rank": index,
                    "source_path": str(document.get("meta", {}).get("source_path", "")),
                    "score": document.get("score"),
                    "retrieval_score": document.get("meta", {}).get("retrieval_score"),
                    "rerank_score": document.get("meta", {}).get("rerank_score"),
                }
                for index, document in enumerate(documents, start=1)
            ],
        }
        report.append(entry)
        print(render_case_line(entry, show_top=args.show_top))

    summary = {
        "total": len(report),
        "passed": passed,
        "failed": len(report) - passed,
        "pass_rate": round((passed / len(report)) * 100, 2) if report else 0.0,
    }
    print(
        "\nSummary: "
        f"{summary['passed']}/{summary['total']} passed "
        f"({summary['pass_rate']}% hit rate)"
    )

    if args.output:
        Path(args.output).write_text(
            json.dumps({"summary": summary, "cases": report}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.fail_on_miss and summary["failed"] > 0:
        raise SystemExit(1)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def find_match_rank(source_paths: list[str], expected_substrings: list[str]) -> int | None:
    for index, source_path in enumerate(source_paths, start=1):
        if any(expected in source_path for expected in expected_substrings):
            return index
    return None


def render_case_line(entry: dict[str, Any], show_top: int) -> str:
    top_paths = entry["returned_source_paths"][:show_top]
    top_paths_text = " | ".join(top_paths) if top_paths else "<no results>"
    if entry["success"]:
        return (
            f"[PASS] {entry['id']} rank={entry['matched_rank']} question={entry['question']}\n"
            f"       top={top_paths_text}"
        )
    return (
        f"[FAIL] {entry['id']} rank=- question={entry['question']}\n"
        f"       top={top_paths_text}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
