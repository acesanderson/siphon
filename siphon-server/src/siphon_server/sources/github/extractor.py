from __future__ import annotations

# NOTE: Pass use_cache=False at the pipeline level to force re-fetch of an
# already-ingested repo. The hash is stable (owner/repo), so the pipeline
# will otherwise return the cached version unchanged.

import base64
import os
from datetime import datetime
from datetime import timezone
from typing import override

import httpx

from siphon_api.enums import SourceType
from siphon_api.interfaces import ExtractorStrategy
from siphon_api.models import ContentData
from siphon_api.models import SourceInfo

_SKIP_EXTENSIONS = {
    ".json", ".lock", ".toml", ".yaml", ".yml",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".exe", ".bin", ".whl", ".pyc",
}
_API_BASE = "https://api.github.com"


class GitHubExtractor(ExtractorStrategy):
    """Fetch repository file contents from the GitHub API and build an XML blob."""

    source_type: SourceType = SourceType.GITHUB

    @override
    def extract(self, source: SourceInfo) -> ContentData:
        path = source.uri.removeprefix("github:///")
        owner, repo = path.split("/", 1)
        token = os.environ.get("GITHUB_TOKEN")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with httpx.Client(headers=headers, timeout=30) as client:
            repo_info = client.get(f"{_API_BASE}/repos/{owner}/{repo}").json()
            default_branch = repo_info.get("default_branch", "main")

            tree_resp = client.get(
                f"{_API_BASE}/repos/{owner}/{repo}/git/trees/{default_branch}",
                params={"recursive": "1"},
            ).json()
            tree = tree_resp.get("tree", [])

            file_blobs: list[str] = []
            for item in tree:
                if item.get("type") != "blob":
                    continue
                item_path = item["path"]
                ext = "." + item_path.rsplit(".", 1)[-1].lower() if "." in item_path else ""
                if ext in _SKIP_EXTENSIONS:
                    continue
                content_resp = client.get(
                    f"{_API_BASE}/repos/{owner}/{repo}/contents/{item_path}",
                    params={"ref": default_branch},
                ).json()
                encoded = content_resp.get("content", "")
                if not encoded:
                    continue
                try:
                    text = base64.b64decode(encoded).decode("utf-8", errors="replace")
                except Exception:
                    continue
                file_blobs.append(f'<file path="{item_path}">{text}</file>')

        xml_blob = (
            f'<repository owner="{owner}" repo="{repo}">\n'
            + "\n".join(file_blobs)
            + "\n</repository>"
        )
        metadata = {
            "owner": owner,
            "repo": repo,
            "default_branch": default_branch,
            "file_count": len(file_blobs),
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        return ContentData(
            source_type=self.source_type,
            text=xml_blob,
            metadata=metadata,
        )
