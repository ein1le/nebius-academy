import os
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from app.config import get_settings
from app.models import ParsedRepo, RepoAnalysisResult, SelectedFile
from .repo_config import (
    BINARY_EXTENSIONS,
    FRAMEWORK_PATTERNS,
    IGNORE_DIRS,
    MANIFEST_NAMES,
    ROLE_HINTS,
    SOURCE_PREFIXES,
)


LANGUAGE_EXTENSIONS: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".rb": "Ruby",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".scala": "Scala",
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
    if filename in MANIFEST_NAMES or lower.startswith(".github/workflows/"):
        return 2

    # Main source directories
    if lower.startswith(SOURCE_PREFIXES):
        return 3

    # Tests
    if lower.startswith("tests/") or "/tests/" in lower:
        return 4
    if filename.startswith("test_") or filename.endswith("_test.py"):
        return 4

    # Everything else
    return 5


def _build_dir_overview(paths: Iterable[str]) -> str:
    top_counts: Counter[str] = Counter()
    for path in paths:
        parts = path.split("/")
        if not parts:
            continue
        top_counts[parts[0]] += 1

    if not top_counts:
        return "Repository appears to be empty or has no visible files."

    lines: List[str] = []
    for name, count in sorted(top_counts.items()):
        role = ROLE_HINTS.get(name.lower())
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


def _extract_framework_hints(selected_files: Iterable[SelectedFile]) -> Set[str]:
    hints: Set[str] = set()
    for sf in selected_files:
        lower = sf.content.lower()
        for token, name in FRAMEWORK_PATTERNS.items():
            if token in lower:
                hints.add(name)
    return hints


def _scan_files(root: Path) -> List[Tuple[str, Path, int]]:
    """
    Walk the local repository and collect candidate files as
    (relative_path, absolute_path, size_bytes).
    """
    files: List[Tuple[str, Path, int]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dir_rel = Path(dirpath).relative_to(root)

        # Skip entire subtrees whose top-level dir is ignored.
        if dir_rel.parts and dir_rel.parts[0] in IGNORE_DIRS:
            dirnames[:] = []
            continue

        for name in filenames:
            rel_path = (dir_rel / name) if dir_rel.parts else Path(name)
            rel_str = rel_path.as_posix()
            full_path = Path(dirpath) / name

            try:
                size = full_path.stat().st_size
            except OSError:
                size = 0

            if _is_ignored(rel_str, size):
                continue

            files.append((rel_str, full_path, size))

    return files


def _infer_languages(files: Iterable[Tuple[str, Path, int]]) -> Dict[str, int]:
    """
    Approximate language usage by summing file sizes per common extension.
    """
    languages: Dict[str, int] = {}
    for rel_path, _, size in files:
        _, ext = os.path.splitext(rel_path.lower())
        language = LANGUAGE_EXTENSIONS.get(ext)
        if not language:
            continue
        languages[language] = languages.get(language, 0) + int(size or 0)
    return languages


def analyze_repo(
    parsed: ParsedRepo,
    repo_path: Path,
) -> RepoAnalysisResult:
    """
    Analyze a locally cloned repository to select representative files and
    derive directory overview and technology hints.
    """
    settings = get_settings()

    all_files = _scan_files(repo_path)
    if not all_files:
        languages: Dict[str, int] = {}
        return RepoAnalysisResult(
            dir_overview="Repository appears to be empty or has no visible files.",
            selected_files=[],
            tech_hints=[],
            languages=languages,
        )

    # Compute language usage and directory overview from all visible files.
    languages = _infer_languages(all_files)
    visible_paths = [rel for rel, _, _ in all_files]
    dir_overview = _build_dir_overview(visible_paths)

    # Sort candidates by priority and path.
    sorted_files = sorted(all_files, key=lambda item: (_priority(item[0]), item[0]))

    selected_files: List[SelectedFile] = []
    total_chars = 0

    for rel_path, full_path, _ in sorted_files:
        if total_chars >= settings.max_total_chars:
            break

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if not content:
            continue

        if len(content) > settings.max_chars_per_file:
            content = content[: settings.max_chars_per_file]

        selected_files.append(SelectedFile(path=rel_path, content=content))
        total_chars += len(content)

        if total_chars >= settings.max_total_chars:
            break

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
