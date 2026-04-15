from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib import error, request


SYSTEM_PROMPT = """You answer only from the retrieved documentation context.
If the context is weak or incomplete, say so plainly.
Do not invent undocumented SAP or 1C details.
Prefer a concise answer with a short source list at the end."""

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LLM answer evaluation over retrieval cases.")
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
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the local env file with chat provider settings.",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Top-K documents to request.")
    parser.add_argument(
        "--language",
        choices=["all", "ru", "en"],
        default="all",
        help="Run all cases or only one language subset.",
    )
    parser.add_argument(
        "--case",
        default="",
        help="Optional substring filter for case id or question.",
    )
    parser.add_argument("--output", default="", help="Optional path to save JSON report.")
    parser.add_argument(
        "--markdown-output",
        default="",
        help="Optional path to save Markdown report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env(args.env_file)
    config = build_chat_config(env)
    cases = load_cases(args.cases, args.case, args.language)
    report = run_cases(
        endpoint=args.endpoint,
        cases=cases,
        top_k=args.top_k,
        config=config,
    )
    print_summary(report["summary"])
    maybe_write_json(args.output, report)
    maybe_write_markdown(args.markdown_output, report)


def load_env(path_str: str) -> dict[str, str]:
    path = Path(path_str).resolve()
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def build_chat_config(env: dict[str, str]) -> dict[str, str]:
    provider = env.get("CHAT_PROVIDER", "").strip().lower()
    api_key = env.get("CHAT_API_KEY", "").strip() or env.get("OPENAI_API_KEY", "").strip()
    api_base_url = env.get("CHAT_API_BASE_URL", "").strip() or env.get("OPENAI_API_BASE_URL", "").strip()
    model = env.get("CHAT_MODEL", "").strip()

    if provider != "openai":
        raise SystemExit("CHAT_PROVIDER is not set to openai in .env")
    if not api_key:
        raise SystemExit("CHAT_API_KEY or OPENAI_API_KEY is required in .env")
    if not api_base_url:
        raise SystemExit("CHAT_API_BASE_URL or OPENAI_API_BASE_URL is required in .env")
    if not model:
        raise SystemExit("CHAT_MODEL is required in .env")

    return {
        "api_key": api_key,
        "api_base_url": api_base_url.rstrip("/"),
        "model": model,
    }


def load_cases(cases_path_str: str, case_filter: str, language: str) -> list[dict[str, Any]]:
    cases_path = Path(cases_path_str).resolve()
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    filtered: list[dict[str, Any]] = []
    needle = case_filter.casefold()
    for case in cases:
        question = str(case["request"]["question"])
        case_language = infer_case_language(case)
        if language != "all" and case_language != language:
            continue
        if needle and needle not in case["id"].casefold() and needle not in question.casefold():
            continue
        filtered.append(case)
    return filtered


def infer_case_language(case: dict[str, Any]) -> str:
    request_language = str(case.get("request", {}).get("language_hint", "")).strip().lower()
    if request_language in {"ru", "en"}:
        return request_language
    question = str(case["request"]["question"])
    return "ru" if CYRILLIC_RE.search(question) else "en"


def run_cases(
    *,
    endpoint: str,
    cases: list[dict[str, Any]],
    top_k: int,
    config: dict[str, str],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    total_cost_rub = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for case in cases:
        retrieval = run_retrieval(endpoint=endpoint, case=case, top_k=top_k)
        documents = retrieval["result"]["documents"]
        question = str(case["request"]["question"])
        context = format_context(documents)
        sources = format_sources(documents)
        llm = run_chat_completion(
            config=config,
            question=question,
            context=context,
        )

        usage = llm.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        cost_rub = float(usage.get("cost_rub") or usage.get("cost") or 0.0)
        total_cost_rub += cost_rub
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens

        answer = str(llm["choices"][0]["message"]["content"]).strip()
        final_answer = f"{answer}\n\nSources:\n{sources}"
        entry = {
            "id": case["id"],
            "language": infer_case_language(case),
            "question": question,
            "answer": final_answer,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
                "cost_rub": cost_rub,
            },
            "sources": [str(document.get("source_ref") or document.get("meta", {}).get("source_path", "")) for document in documents],
        }
        results.append(entry)
        print(render_case_line(entry))

    summary = {
        "total_cases": len(results),
        "model": config["model"],
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "total_cost_rub": round(total_cost_rub, 6),
        "by_language": summarize_by_language(results),
    }
    return {"summary": summary, "cases": results}


def run_retrieval(*, endpoint: str, case: dict[str, Any], top_k: int) -> dict[str, Any]:
    payload = dict(case["request"])
    payload["mode"] = "search"
    payload["top_k"] = top_k
    return post_json(endpoint, payload)


def run_chat_completion(*, config: dict[str, str], question: str, context: str) -> dict[str, Any]:
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Retrieved context:\n{context}\n\n"
                    "Write a grounded answer in the same language as the user question. "
                    "If the documentation is insufficient, say that explicitly."
                ),
            },
        ],
    }
    return post_json(
        f"{config['api_base_url']}/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {config['api_key']}"},
    )


def format_context(documents: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, document in enumerate(documents, start=1):
        source_ref = str(document.get("source_ref") or document.get("meta", {}).get("source_path", ""))
        content = str(document.get("content", "")).strip()
        blocks.append(f"[{index}] {source_ref}\n{content}")
    return "\n\n".join(blocks)


def format_sources(documents: list[dict[str, Any]]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for document in documents:
        source_ref = str(document.get("source_ref") or document.get("meta", {}).get("source_path", ""))
        if source_ref in seen:
            continue
        seen.add(source_ref)
        lines.append(f"- {source_ref}")
    return "\n".join(lines)


def summarize_by_language(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for entry in results:
        language = entry["language"]
        bucket = summary.setdefault(
            language,
            {
                "cases": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_rub": 0.0,
            },
        )
        usage = entry["usage"]
        bucket["cases"] += 1
        bucket["prompt_tokens"] += usage["prompt_tokens"]
        bucket["completion_tokens"] += usage["completion_tokens"]
        bucket["total_tokens"] += usage["total_tokens"]
        bucket["cost_rub"] += usage["cost_rub"]

    for bucket in summary.values():
        bucket["cost_rub"] = round(bucket["cost_rub"], 6)
    return summary


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        raise SystemExit(f"HTTP {exc.code} for {url}: {body}") from exc


def render_case_line(entry: dict[str, Any]) -> str:
    usage = entry["usage"]
    return (
        f"[OK] {entry['id']} lang={entry['language']} "
        f"tokens={usage['total_tokens']} cost_rub={usage['cost_rub']:.6f}\n"
        f"     answer={entry['answer'].splitlines()[0]}"
    )


def print_summary(summary: dict[str, Any]) -> None:
    print(
        "\nSummary: "
        f"cases={summary['total_cases']} "
        f"model={summary['model']} "
        f"tokens={summary['total_tokens']} "
        f"cost_rub={summary['total_cost_rub']:.6f}"
    )
    for language, bucket in sorted(summary["by_language"].items()):
        print(
            f"  {language}: "
            f"cases={bucket['cases']} "
            f"tokens={bucket['total_tokens']} "
            f"cost_rub={bucket['cost_rub']:.6f}"
        )


def maybe_write_json(path_str: str, report: dict[str, Any]) -> None:
    if not path_str:
        return
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def maybe_write_markdown(path_str: str, report: dict[str, Any]) -> None:
    if not path_str:
        return
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    summary = report["summary"]
    lines.append("# Answer Evaluation Report")
    lines.append("")
    lines.append(f"- Model: `{summary['model']}`")
    lines.append(f"- Cases: `{summary['total_cases']}`")
    lines.append(f"- Total tokens: `{summary['total_tokens']}`")
    lines.append(f"- Total cost (RUB): `{summary['total_cost_rub']:.6f}`")
    lines.append("")
    lines.append("## By Language")
    lines.append("")
    for language, bucket in sorted(summary["by_language"].items()):
        lines.append(
            f"- `{language}`: cases=`{bucket['cases']}`, tokens=`{bucket['total_tokens']}`, cost_rub=`{bucket['cost_rub']:.6f}`"
        )
    lines.append("")
    lines.append("## Cases")
    lines.append("")
    for entry in report["cases"]:
        usage = entry["usage"]
        lines.append(f"### {entry['id']}")
        lines.append("")
        lines.append(f"- Language: `{entry['language']}`")
        lines.append(f"- Question: `{entry['question']}`")
        lines.append(f"- Tokens: `{usage['total_tokens']}`")
        lines.append(f"- Cost (RUB): `{usage['cost_rub']:.6f}`")
        lines.append("- Sources:")
        for source in entry["sources"]:
            lines.append(f"  - `{source}`")
        lines.append("")
        lines.append("Answer:")
        lines.append("")
        lines.append(entry["answer"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
