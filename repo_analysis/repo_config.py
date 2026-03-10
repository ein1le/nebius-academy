from typing import Dict, Iterable, List, Set, Tuple

# Directories to ignore entirely when walking the Git tree.
IGNORE_DIRS: Set[str] = {
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

# File extensions treated as binary / not useful for LLM summarization.
BINARY_EXTENSIONS: Set[str] = {
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

# Filenames that represent project manifests or important configuration.
MANIFEST_NAMES: Set[str] = {
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

# Source directory prefixes that usually contain the main application code.
SOURCE_PREFIXES: Tuple[str, ...] = (
    "src/",
    "lib/",
    "app/",
    "server/",
    "backend/",
    "api/",
    "core/",
)

# High-level role hints for common top-level directories when building a tree overview.
ROLE_HINTS: Dict[str, str] = {
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

# String patterns searched for in selected files to infer frameworks / libraries.
FRAMEWORK_PATTERNS: Dict[str, str] = {
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

