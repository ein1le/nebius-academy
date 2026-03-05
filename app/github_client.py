import base64
from typing import Dict, List
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from .config import get_settings
from .models import ParsedRepo, RepoMetadata, TreeItem


def parse_github_url(url: str) -> ParsedRepo:
    """
    Parse a GitHub repository URL into owner, repo, and optional branch.
    Supports:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/
      - https://github.com/owner/repo.git
      - https://github.com/owner/repo/tree/branch
    """
    parsed = urlparse(url)

    host = parsed.netloc.lower()
    if host not in ("github.com", "www.github.com"):
        raise ValueError("Only github.com URLs are supported")

    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 2:
        raise ValueError("Invalid GitHub repository URL")

    owner = path_parts[0]
    repo = path_parts[1]

    if repo.endswith(".git"):
        repo = repo[:-4]

    branch = None
    if len(path_parts) >= 4 and path_parts[2] == "tree":
        branch = path_parts[3]

    return ParsedRepo(owner=owner, repo=repo, branch=branch)


def _handle_github_error(response: httpx.Response) -> None:
    message = ""
    try:
        data = response.json()
        message = str(data.get("message") or "")
    except Exception:
        message = ""

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": "Repository not found or not public"},
        )

    if response.status_code in (401, 403):
        # Distinguish rate limits from generic auth issues where possible.
        if "API rate limit exceeded" in message:
            detail_msg = (
                "GitHub API rate limit exceeded. Set a GITHUB_TOKEN environment "
                "variable or try again later."
            )
        else:
            detail_msg = (
                "GitHub API request unauthorized. Ensure the repository is public "
                "or set a GITHUB_TOKEN environment variable."
            )
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": detail_msg,
            },
        )

    raise HTTPException(
        status_code=502,
        detail={
            "status": "error",
            "message": f"GitHub API error: HTTP {response.status_code}",
        },
    )


def get_repo_metadata(parsed: ParsedRepo) -> RepoMetadata:
    settings = get_settings()
    url = f"{settings.github_api_base}/repos/{parsed.owner}/{parsed.repo}"
    headers = {
        "User-Agent": "github-repo-summarizer",
        "Accept": "application/vnd.github+json",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "Failed to reach GitHub API"},
        )

    if response.status_code != 200:
        _handle_github_error(response)

    data = response.json()
    return RepoMetadata(
        name=data.get("name") or f"{parsed.owner}/{parsed.repo}",
        full_name=data.get("full_name") or f"{parsed.owner}/{parsed.repo}",
        description=data.get("description"),
        html_url=data.get("html_url") or f"https://github.com/{parsed.owner}/{parsed.repo}",
        stargazers_count=int(data.get("stargazers_count") or 0),
        forks_count=int(data.get("forks_count") or 0),
        default_branch=data.get("default_branch") or "main",
    )


def get_languages(parsed: ParsedRepo) -> Dict[str, int]:
    settings = get_settings()
    url = f"{settings.github_api_base}/repos/{parsed.owner}/{parsed.repo}/languages"
    headers = {
        "User-Agent": "github-repo-summarizer",
        "Accept": "application/vnd.github+json",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "Failed to reach GitHub API"},
        )

    if response.status_code == 404:
        # Keep behavior consistent with metadata call
        _handle_github_error(response)
    elif response.status_code != 200:
        _handle_github_error(response)

    data = response.json()
    return {str(k): int(v) for k, v in data.items()}


def get_repo_tree(parsed: ParsedRepo, ref: str) -> List[TreeItem]:
    settings = get_settings()
    url = f"{settings.github_api_base}/repos/{parsed.owner}/{parsed.repo}/git/trees/{ref}"
    headers = {
        "User-Agent": "github-repo-summarizer",
        "Accept": "application/vnd.github+json",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    try:
        response = httpx.get(url, headers=headers, params={"recursive": 1}, timeout=15.0)
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "Failed to reach GitHub API"},
        )

    if response.status_code != 200:
        _handle_github_error(response)

    data = response.json()
    tree_items: List[TreeItem] = []
    for entry in data.get("tree", []):
        if entry.get("type") not in ("blob", "tree"):
            continue
        tree_items.append(
            TreeItem(
                path=entry.get("path", ""),
                type=entry.get("type", ""),
                size=entry.get("size"),
            )
        )
    return tree_items


def get_file_content(parsed: ParsedRepo, path: str, ref: str) -> str:
    """
    Fetch file content from the GitHub contents API and return it as a text string.
    Non-text or missing content results in an empty string.
    """
    settings = get_settings()
    url = f"{settings.github_api_base}/repos/{parsed.owner}/{parsed.repo}/contents/{path}"
    headers = {
        "User-Agent": "github-repo-summarizer",
        "Accept": "application/vnd.github+json",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    try:
        response = httpx.get(url, headers=headers, params={"ref": ref}, timeout=10.0)
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "Failed to reach GitHub API"},
        )

    if response.status_code != 200:
        _handle_github_error(response)

    data = response.json()
    content = data.get("content")
    encoding = data.get("encoding")
    if not content or encoding != "base64":
        # Binary or unsupported content
        return ""

    try:
        decoded_bytes = base64.b64decode(content)
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""
