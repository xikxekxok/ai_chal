from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from dotenv import load_dotenv
from github_api import GitHubClient
from paths import DATA_DIR, REPO_ROOT, SEEN_STATE_PATH
from rag import load_index, retrieve
from review import review_pull_request

DEFAULT_GITHUB_REPO = "xikxekxok/ai_chal"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Polling CLI для PR review через GitHub REST API и Dockhost."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=120,
        help="Интервал polling в секундах (по умолчанию: 120).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Сделать один проход и завершиться.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        help="Проверить только один PR по номеру.",
    )
    return parser.parse_args()


def load_env() -> None:
    load_dotenv(REPO_ROOT / ".env")
    # Nested worktree: also load the outer course .env without overriding.
    if REPO_ROOT.parent.name == ".worktrees":
        load_dotenv(REPO_ROOT.parent.parent / ".env", override=False)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    print(f"[error] Не найдена переменная окружения: {name}", file=sys.stderr)
    raise SystemExit(1)


def resolve_github_repo() -> str:
    return os.getenv("GITHUB_REPO") or DEFAULT_GITHUB_REPO


def load_seen_state() -> dict[str, dict[str, str]]:
    if not SEEN_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SEEN_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_seen_state(state: dict[str, dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_target_prs(
    client: GitHubClient,
    pull_number: int | None,
) -> list[dict[str, Any]]:
    if pull_number:
        return [client.get_pull_request(pull_number)]
    return client.list_open_pull_requests()


def should_review(
    pull_request: dict[str, Any],
    seen_state: dict[str, dict[str, str]],
) -> bool:
    key = str(pull_request["number"])
    previous = seen_state.get(key)
    current = {
        "head_sha": pull_request["head"]["sha"],
        "updated_at": pull_request["updated_at"],
    }
    if previous != current:
        seen_state[key] = current
        return True
    return False


def render_review_header(pull_request: dict[str, Any], files: list[dict[str, Any]]) -> str:
    file_list = ", ".join(file["filename"] for file in files[:6])
    if len(files) > 6:
        file_list += ", ..."
    return (
        f"[pipeline] PR #{pull_request['number']} {pull_request['title']}\n"
        f"[pipeline] changed files: {len(files)}"
        f"{f' -> {file_list}' if file_list else ''}"
    )


def run_review_cycle(
    client: GitHubClient,
    seen_state: dict[str, dict[str, str]],
    once_mode: bool,
    pull_number: int | None,
) -> None:
    chunks = load_index()
    pull_requests = list_target_prs(client, pull_number)
    print(f"[pipeline] found {len(pull_requests)} PR(s)")

    for pull_request in pull_requests:
        if not should_review(pull_request, seen_state):
            print(f"[pipeline] skip PR #{pull_request['number']} (no changes)")
            continue

        files = client.get_pull_files(pull_request["number"])
        reviews = client.get_pull_reviews(pull_request["number"])
        comments = client.get_issue_comments(pull_request["number"])

        query_parts = [
            pull_request.get("title", ""),
            pull_request.get("body") or "",
            " ".join(file["filename"] for file in files),
        ]
        context_chunks = retrieve(
            chunks=chunks,
            query="\n".join(query_parts),
            path_hints=[file["filename"] for file in files],
        )

        print(render_review_header(pull_request, files))
        review_text = review_pull_request(
            pull_request=pull_request,
            files=files,
            reviews=reviews,
            comments=comments,
            context_chunks=context_chunks,
        )
        print(review_text)
        print()

    save_seen_state(seen_state)
    if once_mode:
        print("[pipeline] single pass complete")


def main() -> None:
    args = parse_args()
    load_env()

    token = require_env("GITHUB_TOKEN")
    repo = resolve_github_repo()

    client = GitHubClient(token=token, repo=repo)
    seen_state = load_seen_state()

    if args.once:
        run_review_cycle(
            client=client,
            seen_state=seen_state,
            once_mode=True,
            pull_number=args.pr,
        )
        return

    print(f"[pipeline] watching repo {repo} every {args.interval}s")
    while True:
        try:
            run_review_cycle(
                client=client,
                seen_state=seen_state,
                once_mode=False,
                pull_number=args.pr,
            )
        except KeyboardInterrupt:
            print("\n[pipeline] stopped by user")
            return
        except Exception as error:  # noqa: BLE001
            print(f"[error] {error}", file=sys.stderr)

        print(f"[pipeline] sleeping {args.interval}s")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
