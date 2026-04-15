from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib import request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a smoke test against the local RAG stack.")
    parser.add_argument("--hayhooks-url", default="http://localhost:1416", help="Base URL for Hayhooks.")
    parser.add_argument("--mcp-url", default="http://localhost:1417", help="Base URL for Hayhooks MCP.")
    parser.add_argument("--webui-url", default="http://localhost:3000", help="Base URL for Open WebUI.")
    parser.add_argument(
        "--question",
        default="Северная надбавка территориальные условия",
        help="Question to use for retrieval smoke testing.",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Top-K for retrieval request.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    hayhooks_status = get_json(f"{args.hayhooks_url}/status")
    mcp_status = get_json(f"{args.mcp_url}/status")
    webui_status = get_http_status(args.webui_url)

    retrieval = post_json(
        f"{args.hayhooks_url}/doc_search/run",
        {
            "question": args.question,
            "mode": "search",
            "domain": "1c",
            "category": "books",
            "language_hint": "ru",
            "top_k": args.top_k,
        },
    )

    documents = retrieval["result"]["documents"]
    if not documents:
        raise SystemExit("Smoke test failed: retrieval returned no documents.")

    first_document = documents[0]
    source_ref = first_document.get("source_ref")
    if not source_ref:
        raise SystemExit("Smoke test failed: first document has no source_ref.")

    print("[PASS] hayhooks status:", hayhooks_status.get("status"))
    print("[PASS] hayhooks pipelines:", ", ".join(hayhooks_status.get("pipelines", [])))
    print("[PASS] hayhooks-mcp status:", mcp_status.get("status"))
    print("[PASS] open-webui status:", webui_status)
    print("[PASS] retrieval returned:", len(documents), "documents")
    print("[PASS] first source_ref:", source_ref)

    page_label = first_document.get("meta", {}).get("page_label")
    if page_label:
        print("[PASS] first page_label:", page_label)


def get_json(url: str) -> dict[str, Any]:
    with request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def get_http_status(url: str) -> int:
    with request.urlopen(url) as response:
        return response.status


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
