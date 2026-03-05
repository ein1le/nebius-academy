from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import get_settings
from .github_client import (
    get_languages,
    get_repo_metadata,
    get_repo_tree,
    parse_github_url,
)
from .llm_client import build_summary_prompt, call_llm, parse_llm_result
from .models import ErrorResponse, SummarizeRequest, SummarizeResponse
from .repo_analysis import analyze_repo


app = FastAPI(title="GitHub Repo Summarizer")


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "status" in detail and "message" in detail:
        content = detail
    else:
        content = {"status": "error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": "Invalid request body"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    # Fail closed with a generic error while avoiding leaking internals.
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error while summarizing repository",
        },
    )


@app.get("/", response_class=HTMLResponse)
def get_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "Frontend index.html not found",
            },
        )
    return FileResponse(index_path)


@app.post(
    "/summarize",
    response_model=SummarizeResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def summarize(body: SummarizeRequest) -> SummarizeResponse:
    # Ensure configuration is valid (e.g., OPENAI_API_KEY present)
    try:
        get_settings()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "message": str(exc)},
        ) from exc

    github_url = str(body.github_url)
    parsed_url = urlparse(github_url)
    host = parsed_url.netloc.lower()
    if host not in ("github.com", "www.github.com"):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": "Only public GitHub URLs on github.com are supported",
            },
        )

    try:
        parsed_repo = parse_github_url(github_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": str(exc)},
        ) from exc

    repo_metadata = get_repo_metadata(parsed_repo)
    languages = get_languages(parsed_repo)
    ref = parsed_repo.branch or repo_metadata.default_branch
    tree_items = get_repo_tree(parsed_repo, ref)

    analysis = analyze_repo(parsed_repo, ref, tree_items, languages)
    system_prompt, user_prompt = build_summary_prompt(repo_metadata, analysis)
    raw_response = call_llm(system_prompt, user_prompt, config=body.config)
    result = parse_llm_result(raw_response, analysis)
    return result
