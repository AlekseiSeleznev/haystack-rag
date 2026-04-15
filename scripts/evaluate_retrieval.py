from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib import request


RERANKING_AUTO = "auto"
RERANKING_ON = "on"
RERANKING_OFF = "off"


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
        "--markdown-output",
        default="",
        help="Optional path to save a Markdown summary report.",
    )
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
    parser.add_argument(
        "--reranking",
        choices=[RERANKING_AUTO, RERANKING_ON, RERANKING_OFF],
        default=RERANKING_AUTO,
        help="Override per-request reranking behavior.",
    )
    parser.add_argument(
        "--compare-reranking",
        action="store_true",
        help="Run the same case set twice and compare reranking on vs off.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_cases(args.cases, args.case)
    if args.compare_reranking:
        compare_reranking(args=args, cases=cases)
        return

    evaluation = evaluate_cases(
        endpoint=args.endpoint,
        cases=cases,
        top_k=args.top_k,
        show_top=args.show_top,
        reranking_mode=args.reranking,
    )
    print_summary(evaluation["summary"])
    maybe_write_report(args.output, evaluation)
    maybe_write_markdown_report(args.markdown_output, evaluation)
    maybe_fail(args.fail_on_miss, evaluation["summary"])


def compare_reranking(args: argparse.Namespace, cases: list[dict[str, Any]]) -> None:
    reranking_on = evaluate_cases(
        endpoint=args.endpoint,
        cases=cases,
        top_k=args.top_k,
        show_top=args.show_top,
        reranking_mode=RERANKING_ON,
        heading="=== Reranking ON ===",
    )
    reranking_off = evaluate_cases(
        endpoint=args.endpoint,
        cases=cases,
        top_k=args.top_k,
        show_top=args.show_top,
        reranking_mode=RERANKING_OFF,
        heading="=== Reranking OFF ===",
    )

    comparison = build_comparison(
        on_cases=reranking_on["cases"],
        off_cases=reranking_off["cases"],
    )

    print("\n=== Comparison ===")
    for line in comparison["lines"]:
        print(line)
    print(
        "\nComparison Summary: "
        f"improved={comparison['summary']['improved']} "
        f"worsened={comparison['summary']['worsened']} "
        f"unchanged={comparison['summary']['unchanged']}"
    )

    maybe_write_report(
        args.output,
        {
            "reranking_on": reranking_on,
            "reranking_off": reranking_off,
            "comparison": comparison,
        },
    )
    maybe_write_markdown_report(
        args.markdown_output,
        {
            "reranking_on": reranking_on,
            "reranking_off": reranking_off,
            "comparison": comparison,
        },
    )
    if args.fail_on_miss and (
        reranking_on["summary"]["failed"] > 0 or reranking_off["summary"]["failed"] > 0
    ):
        raise SystemExit(1)


def load_cases(cases_path_str: str, case_filter: str) -> list[dict[str, Any]]:
    cases_path = Path(cases_path_str).resolve()
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if not case_filter:
        return cases

    needle = case_filter.casefold()
    return [
        case
        for case in cases
        if needle in case["id"].casefold() or needle in case["request"]["question"].casefold()
    ]


def evaluate_cases(
    *,
    endpoint: str,
    cases: list[dict[str, Any]],
    top_k: int,
    show_top: int,
    reranking_mode: str,
    heading: str = "",
) -> dict[str, Any]:
    if heading:
        print(heading)

    report: list[dict[str, Any]] = []
    passed = 0
    for case in cases:
        payload = build_payload(case=case, top_k=top_k, reranking_mode=reranking_mode)
        response = post_json(endpoint, payload)

        documents = response["result"]["documents"]
        source_paths = [str(document.get("meta", {}).get("source_path", "")) for document in documents]
        source_refs = [str(document.get("source_ref") or document.get("meta", {}).get("source_path", "")) for document in documents]
        document_contents = [str(document.get("content", "")) for document in documents]
        expected_substrings = case.get("expect_any_source_contains", [])
        expected_content_substrings = case.get("expect_any_content_contains", [])
        matched_rank = find_match_rank(source_paths, expected_substrings)
        matched_content_rank = find_match_rank(
            document_contents,
            expected_content_substrings,
            normalize=normalize_for_match,
        )
        source_success = matched_rank is not None
        content_success = matched_content_rank is not None if expected_content_substrings else True
        success = source_success and content_success
        if success:
            passed += 1

        entry = {
            "id": case["id"],
            "question": payload["question"],
            "success": success,
            "source_success": source_success,
            "content_success": content_success,
            "matched_rank": matched_rank,
            "matched_content_rank": matched_content_rank,
            "expected": expected_substrings,
            "expected_content": expected_content_substrings,
            "returned_source_paths": source_paths,
            "returned_source_refs": source_refs,
            "reranking_mode": reranking_mode,
            "reranking_enabled": response["result"].get("reranking_enabled"),
            "reranking_requested": response["result"].get("reranking_requested"),
            "reranking_applied": response["result"].get("reranking_applied"),
            "top_documents": [
                {
                    "rank": index,
                    "source_path": str(document.get("meta", {}).get("source_path", "")),
                    "source_ref": str(document.get("source_ref") or document.get("meta", {}).get("source_path", "")),
                    "page_number": document.get("meta", {}).get("page_number"),
                    "page_start": document.get("meta", {}).get("page_start"),
                    "page_end": document.get("meta", {}).get("page_end"),
                    "page_label": document.get("meta", {}).get("page_label"),
                    "score": document.get("score"),
                    "retrieval_score": document.get("meta", {}).get("retrieval_score"),
                    "rerank_score": document.get("meta", {}).get("rerank_score"),
                }
                for index, document in enumerate(documents, start=1)
            ],
        }
        report.append(entry)
        print(render_case_line(entry, show_top=show_top))

    summary = {
        "total": len(report),
        "passed": passed,
        "failed": len(report) - passed,
        "pass_rate": round((passed / len(report)) * 100, 2) if report else 0.0,
        "reranking_mode": reranking_mode,
    }
    return {"summary": summary, "cases": report}


def build_payload(case: dict[str, Any], top_k: int, reranking_mode: str) -> dict[str, Any]:
    payload = dict(case["request"])
    payload.setdefault("mode", "search")
    payload.setdefault("top_k", top_k)
    if reranking_mode == RERANKING_ON:
        payload["reranking"] = True
    elif reranking_mode == RERANKING_OFF:
        payload["reranking"] = False
    return payload


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_for_match(value: Any) -> str:
    normalized = str(value).casefold()
    normalized = re.sub(r"(?<=[a-zа-яё])\s*-\s*(?=[a-zа-яё])", "", normalized)
    return " ".join(normalized.split())


def normalize_verbatim(value: Any) -> str:
    return str(value)


def find_match_rank(
    values: list[str],
    expected_substrings: list[str],
    normalize: Any = normalize_verbatim,
) -> int | None:
    if not expected_substrings:
        return None
    normalized_expected = [normalize(expected) for expected in expected_substrings]
    for index, value in enumerate(values, start=1):
        normalized_value = normalize(value)
        if any(expected in normalized_value for expected in normalized_expected):
            return index
    return None


def render_case_line(entry: dict[str, Any], show_top: int) -> str:
    top_paths = entry["returned_source_refs"][:show_top]
    top_paths_text = " | ".join(top_paths) if top_paths else "<no results>"
    content_rank_text = display_optional_rank(
        entry["matched_content_rank"],
        available=bool(entry["expected_content"]),
    )
    reranking_note = (
        f" reranking={entry['reranking_mode']}"
        f" requested={entry['reranking_requested']}"
        f" applied={entry['reranking_applied']}"
    )
    if entry["success"]:
        return (
            f"[PASS] {entry['id']} rank={display_rank(entry['matched_rank'])} content_rank={content_rank_text} "
            f"question={entry['question']}{reranking_note}\n"
            f"       top={top_paths_text}"
        )
    return (
        f"[FAIL] {entry['id']} source_rank={display_rank(entry['matched_rank'])} "
        f"content_rank={content_rank_text} "
        f"question={entry['question']}{reranking_note}\n"
        f"       top={top_paths_text}"
    )


def build_comparison(on_cases: list[dict[str, Any]], off_cases: list[dict[str, Any]]) -> dict[str, Any]:
    off_by_id = {entry["id"]: entry for entry in off_cases}
    lines: list[str] = []
    improved = 0
    worsened = 0
    unchanged = 0

    for on_entry in on_cases:
        off_entry = off_by_id[on_entry["id"]]
        metric_name = "content" if on_entry["expected_content"] else "source"
        on_rank = comparison_rank(on_entry)
        off_rank = comparison_rank(off_entry)
        delta = off_rank - on_rank

        if delta > 0:
            improved += 1
            verdict = "improved"
        elif delta < 0:
            worsened += 1
            verdict = "worsened"
        else:
            unchanged += 1
            verdict = "unchanged"

        lines.append(
            f"{on_entry['id']}: {verdict} "
            f"(metric={metric_name}, "
            f"on_rank={display_optional_rank(on_entry['matched_content_rank'] if metric_name == 'content' else on_entry['matched_rank'], available=True)}, "
            f"off_rank={display_optional_rank(off_entry['matched_content_rank'] if metric_name == 'content' else off_entry['matched_rank'], available=True)})"
        )

    return {
        "summary": {
            "improved": improved,
            "worsened": worsened,
            "unchanged": unchanged,
        },
        "lines": lines,
    }


def normalize_rank(rank: int | None) -> int:
    return rank if rank is not None else 10**9


def display_rank(rank: int | None) -> str:
    return str(rank) if rank is not None else "miss"


def display_optional_rank(rank: int | None, available: bool) -> str:
    if not available:
        return "n/a"
    return display_rank(rank)


def comparison_rank(entry: dict[str, Any]) -> int:
    if entry["expected_content"]:
        return normalize_rank(entry["matched_content_rank"])
    return normalize_rank(entry["matched_rank"])


def print_summary(summary: dict[str, Any]) -> None:
    print(
        "\nSummary: "
        f"{summary['passed']}/{summary['total']} passed "
        f"({summary['pass_rate']}% hit rate)"
    )


def maybe_write_report(path_str: str, payload: dict[str, Any]) -> None:
    if not path_str:
        return
    Path(path_str).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def maybe_write_markdown_report(path_str: str, payload: dict[str, Any]) -> None:
    if not path_str:
        return
    Path(path_str).write_text(render_markdown_report(payload), encoding="utf-8")


def render_markdown_report(payload: dict[str, Any]) -> str:
    if "comparison" in payload:
        return render_compare_markdown_report(payload)
    return render_single_markdown_report(payload)


def render_single_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Retrieval Evaluation Report",
        "",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Pass rate: {summary['pass_rate']}%",
        f"- Reranking mode: {summary['reranking_mode']}",
        "",
        "## Cases",
        "",
    ]

    for case in payload["cases"]:
        lines.extend(render_case_markdown(case))

    return "\n".join(lines).strip() + "\n"


def render_compare_markdown_report(payload: dict[str, Any]) -> str:
    comparison = payload["comparison"]
    on_summary = payload["reranking_on"]["summary"]
    off_summary = payload["reranking_off"]["summary"]
    lines = [
        "# Retrieval Reranking Comparison",
        "",
        "## Summary",
        "",
        f"- Reranking ON: {on_summary['passed']}/{on_summary['total']} passed ({on_summary['pass_rate']}%)",
        f"- Reranking OFF: {off_summary['passed']}/{off_summary['total']} passed ({off_summary['pass_rate']}%)",
        f"- Improved: {comparison['summary']['improved']}",
        f"- Worsened: {comparison['summary']['worsened']}",
        f"- Unchanged: {comparison['summary']['unchanged']}",
        "",
        "## Comparison",
        "",
    ]
    lines.extend(f"- {line}" for line in comparison["lines"])
    lines.extend(["", "## Reranking ON Cases", ""])
    for case in payload["reranking_on"]["cases"]:
        lines.extend(render_case_markdown(case))
    lines.extend(["", "## Reranking OFF Cases", ""])
    for case in payload["reranking_off"]["cases"]:
        lines.extend(render_case_markdown(case))
    return "\n".join(lines).strip() + "\n"


def render_case_markdown(case: dict[str, Any]) -> list[str]:
    top_documents = case.get("top_documents", [])
    lines = [
        f"### {case['id']}",
        "",
        f"- Success: {case['success']}",
        f"- Question: {case['question']}",
        f"- Source rank: {display_rank(case['matched_rank'])}",
        f"- Content rank: {display_optional_rank(case['matched_content_rank'], available=bool(case['expected_content']))}",
        f"- Reranking: {case['reranking_mode']} (requested={case['reranking_requested']}, applied={case['reranking_applied']})",
    ]
    if case["expected"]:
        lines.append(f"- Expected source contains: {', '.join(case['expected'])}")
    if case["expected_content"]:
        lines.append(f"- Expected content contains: {', '.join(case['expected_content'])}")

    lines.extend(["", "Top documents:", ""])
    for document in top_documents[:5]:
        lines.append(
            f"- #{document['rank']} {document['source_ref']} "
            f"(score={document['score']}, retrieval={document['retrieval_score']}, rerank={document['rerank_score']})"
        )
    lines.append("")
    return lines


def maybe_fail(fail_on_miss: bool, summary: dict[str, Any]) -> None:
    if fail_on_miss and summary["failed"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
