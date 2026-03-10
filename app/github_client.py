from pathlib import Path
from typing import Dict
from urllib.parse import urlparse
import subprocess
import tempfile
import shutil

from fastapi import HTTPException

from .models import ParsedRepo, RepoMetadata


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


def clone_repo(parsed: ParsedRepo) -> Path:
    """
    Clone the repository via git (prefer SSH, fall back to HTTPS) into a
    temporary directory and return the path to the cloned repo.
    """
    try:
        tmp_root = Path(tempfile.mkdtemp(prefix="repo_clone_"))
    except Exception as exc:  
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "Failed to create temporary directory for cloning repository",
            },
        ) from exc

    repo_dir = tmp_root / parsed.repo

    def _run_clone(remote: str) -> subprocess.CompletedProcess[str]:
        cmd = ["git", "clone", "--depth", "1"]
        if parsed.branch:
            cmd += ["--branch", parsed.branch]
        cmd += [remote, str(repo_dir)]
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )

    # SSH -> fallback to HTTPS cloning
    ssh_remote = f"git@github.com:{parsed.owner}/{parsed.repo}.git"
    https_remote = f"https://github.com/{parsed.owner}/{parsed.repo}.git"

    try:
        result = _run_clone(ssh_remote)
    except FileNotFoundError as exc:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "git is not installed or not available on PATH",
            },
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": "Failed to clone repository via git",
            },
        ) from exc

    # HTTPs
    if result.returncode != 0:
        result = _run_clone(https_remote)

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "Unknown git error"
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": f"Failed to clone repository via git: {msg}",
            },
        )

    if not repo_dir.exists():
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise HTTPException(
            status_code=502,
            detail={
                "status": "error",
                "message": "Repository clone completed but target directory was not found",
            },
        )

    return repo_dir


def build_repo_metadata(parsed: ParsedRepo, repo_path: Path) -> RepoMetadata:
    """
    Build minimal repository metadata from local clone and URL structure.
    """

    description = None
    readme_candidates = [
        "README.md",
        "README.rst",
        "README.txt",
        "README",
    ]
    for name in readme_candidates:
        candidate = repo_path / name
        if candidate.exists():
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if paragraphs:
                description = paragraphs[0]
            break

    default_branch = "main"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            branch = result.stdout.strip() or "HEAD"
            default_branch = branch
    except Exception:
        pass

    return RepoMetadata(
        name=parsed.repo,
        full_name=f"{parsed.owner}/{parsed.repo}",
        description=description,
        html_url=f"https://github.com/{parsed.owner}/{parsed.repo}",
        stargazers_count=0,
        forks_count=0,
        default_branch=parsed.branch or default_branch,
    )
