from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, HttpUrl


class LLMConfig(BaseModel):
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    model: Optional[str] = None


class SummarizeRequest(BaseModel):
    github_url: HttpUrl
    config: Optional[LLMConfig] = None


class SummarizeResponse(BaseModel):
    summary: str
    technologies: List[str]
    structure: str


class ErrorResponse(BaseModel):
    status: Literal["error"]
    message: str


@dataclass
class ParsedRepo:
    owner: str
    repo: str
    branch: Optional[str] = None


@dataclass
class RepoMetadata:
    name: str
    full_name: str
    description: Optional[str]
    html_url: str
    stargazers_count: int
    forks_count: int
    default_branch: str


@dataclass
class TreeItem:
    path: str
    type: str
    size: Optional[int] = None


@dataclass
class SelectedFile:
    path: str
    content: str


@dataclass
class RepoAnalysisResult:
    dir_overview: str
    selected_files: List[SelectedFile]
    tech_hints: List[str]
    languages: Dict[str, int]
