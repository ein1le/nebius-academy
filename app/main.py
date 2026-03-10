from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import shutil

from .config import get_settings
from .github_client import build_repo_metadata, clone_repo, parse_github_url
from .llm_client import build_summary_prompt, call_llm, parse_llm_result
from .models import ErrorResponse, SummarizeRequest, SummarizeResponse
from repo_analysis.repo_analysis import analyze_repo


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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
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

    repo_path = None
    try:
        parsed_repo = parse_github_url(github_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": str(exc)},
        ) from exc

    # clone repo
    repo_path = clone_repo(parsed_repo)
    repo_metadata = build_repo_metadata(parsed_repo, repo_path)

    analysis = analyze_repo(parsed_repo, repo_path)
    system_prompt, user_prompt = build_summary_prompt(repo_metadata, analysis)
    raw_response = call_llm(system_prompt, user_prompt, config=body.config)
    result = parse_llm_result(raw_response, analysis)

    # clean
    if repo_path is not None:
        try:
            shutil.rmtree(repo_path.parent, ignore_errors=True)
        except Exception:
            pass

    return result
