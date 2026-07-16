from __future__ import annotations

from typing import Any

import requests


class GitHubClient:
    def __init__(self, token: str, repo: str) -> None:
        self.repo = repo
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-chal-week07-day02",
            }
        )

    def _get(self, path: str, **params: Any) -> Any:
        url = f"https://api.github.com{path}"
        response = self.session.get(url, params=params or None, timeout=30)
        response.raise_for_status()
        return response.json()

    def list_open_pull_requests(self) -> list[dict[str, Any]]:
        payload = self._get(f"/repos/{self.repo}/pulls", state="open", per_page=30)
        return list(payload)

    def get_pull_request(self, pull_number: int) -> dict[str, Any]:
        return self._get(f"/repos/{self.repo}/pulls/{pull_number}")

    def get_pull_files(self, pull_number: int) -> list[dict[str, Any]]:
        payload = self._get(f"/repos/{self.repo}/pulls/{pull_number}/files", per_page=100)
        return list(payload)

    def get_pull_reviews(self, pull_number: int) -> list[dict[str, Any]]:
        payload = self._get(
            f"/repos/{self.repo}/pulls/{pull_number}/reviews",
            per_page=50,
        )
        return list(payload)

    def get_issue_comments(self, pull_number: int) -> list[dict[str, Any]]:
        payload = self._get(
            f"/repos/{self.repo}/issues/{pull_number}/comments",
            per_page=50,
        )
        return list(payload)
