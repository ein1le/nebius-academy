import os
from collections import Counter
from typing import Dict, Iterable, List, Set

from .config import get_settings
from .github_client import get_file_content
from .models import ParsedRepo, RepoAnalysisResult, SelectedFile, TreeItem


IGNORE_DIRS = {
    ".git",
    ".github",
    "node_modules",
    "dist",
    "build",
    "out",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "target",
}

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".jar",
    ".exe",
    ".dll",
    ".so",
}


def _is_ignored(path: str, size: int | None) -> bool:
    parts = path.split("/")
    if parts and parts[0] in IGNORE_DIRS:
        return True

    _, ext = os.path.splitext(path.lower())
    if ext in BINARY_EXTENSIONS:
        return True

    if size is not None and size > 200_000:
        return True

    return False


def _priority(path: str) -> int:
    lower = path.lower()
    filename = lower.split("/")[-1]

    # Docs and key meta
    if filename.startswith("readme"):
        return 0
    if filename.startswith("contributing") or filename.startswith("changelog"):
        return 1
    if filename == "license" or filename.startswith("license."):
        return 1
    if lower.startswith("docs/") or "/docs/" in lower:
        return 1

    # Manifests / config
    manifest_names = {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "package.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "dockerfile",
        "docker-compose.yml",
        "makefile",
    }
    if filename in manifest_names or lower.startswith(".github/workflows/"):
        return 2

    # Main source directories
    source_prefixes = (
        "src/",
        "lib/",
        "app/",
        "server/",
        "backend/",
        "api/",
        "core/",
    )
    if lower.startswith(source_prefixes):
        return 3

    # Tests
    if lower.startswith("tests/") or "/tests/" in lower:
        return 4
    if filename.startswith("test_") or filename.endswith("_test.py"):
        return 4

    # Everything else
    return 5


def _build_dir_overview(tree_items: Iterable[TreeItem]) -> str:
    top_counts: Counter[str] = Counter()
    for item in tree_items:
        parts = item.path.split("/")
        if not parts:
            continue
        top_counts[parts[0]] += 1

    if not top_counts:
        return "Repository appears to be empty or has no visible files."

    role_hints = {
        "src": "main source code",
        "lib": "library code",
        "app": "application code",
        "server": "server code",
        "backend": "backend code",
        "api": "API implementation",
        "core": "core logic",
        "tests": "tests",
        "test": "tests",
        "docs": "documentation",
        "examples": "examples",
    }

    lines: List[str] = []
    for name, count in sorted(top_counts.items()):
        role = role_hints.get(name.lower())
        if role:
            lines.append(f"- {name}/ ({role}, {count} files)")
        else:
            lines.append(f"- {name}/ ({count} files)")

    return "\n".join(lines)


def _extract_language_hints(languages: Dict[str, int]) -> List[str]:
    if not languages:
        return []
    sorted_langs = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in sorted_langs[:5]]


FRAMEWORK_PATTERNS = {
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "starlette": "Starlette",
    "react": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "vue": "Vue",
    "angular": "Angular",
    "svelte": "Svelte",
    "express": "Express",
    "spring-boot": "Spring Boot",
    "laravel": "Laravel",
}


def _extract_framework_hints(selected_files: Iterable[SelectedFile]) -> Set[str]:
    hints: Set[str] = set()
    for sf in selected_files:
        lower = sf.content.lower()
        for token, name in FRAMEWORK_PATTERNS.items():
            if token in lower:
                hints.add(name)
    return hints


def analyze_repo(
    parsed: ParsedRepo,
    ref: str,
    tree_items: List[TreeItem],
    languages: Dict[str, int],
) -> RepoAnalysisResult:
    """
    Given a GitHub tree listing and language information, select a subset of
    files to send to the LLM and build a human-readable directory overview and
    technology hints.
    """
    settings = get_settings()

    candidates: List[TreeItem] = []
    for item in tree_items:
        if item.type != "blob":
            continue
        if _is_ignored(item.path, item.size):
            continue
        candidates.append(item)

    candidates.sort(key=lambda item: (_priority(item.path), item.path))

    selected_files: List[SelectedFile] = []
    total_chars = 0

    for item in candidates:
        if total_chars >= settings.max_total_chars:
            break

        content = get_file_content(parsed, item.path, ref)
        if not content:
            continue

        if len(content) > settings.max_chars_per_file:
            content = content[: settings.max_chars_per_file]

        selected_files.append(SelectedFile(path=item.path, content=content))
        total_chars += len(content)

        if total_chars >= settings.max_total_chars:
            break

    visible_tree_items = [
        item for item in tree_items if item.type == "blob" and not _is_ignored(item.path, item.size)
    ]
    dir_overview = _build_dir_overview(visible_tree_items)

    tech_hint_set: Set[str] = set()
    tech_hint_set.update(_extract_language_hints(languages))
    tech_hint_set.update(_extract_framework_hints(selected_files))

    tech_hints = sorted(tech_hint_set)

    return RepoAnalysisResult(
        dir_overview=dir_overview,
        selected_files=selected_files,
        tech_hints=tech_hints,
        languages=languages,
    )

