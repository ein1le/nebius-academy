import json
from functools import lru_cache
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from openai import OpenAI

from .config import get_settings
from .models import LLMConfig, RepoAnalysisResult, RepoMetadata, SummarizeResponse


@lru_cache()
def _get_client() -> OpenAI:
    settings = get_settings()
    try:
        client = OpenAI(api_key=settings.openai_api_key)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError("Failed to initialize OpenAI client") from exc
    return client


def build_summary_prompt(
    repo_metadata: RepoMetadata,
    analysis: RepoAnalysisResult,
) -> Tuple[str, str]:
    languages = analysis.languages or {}
    language_summary = (
        ", ".join(f"{name} ({bytes_} bytes)" for name, bytes_ in sorted(languages.items(), key=lambda kv: kv[1], reverse=True))
        if languages
        else "Unknown"
    )

    tech_hints = analysis.tech_hints or []
    tech_hints_str = ", ".join(tech_hints) if tech_hints else "Unknown"

    system_prompt = (
        "You are an expert at reading GitHub repositories and summarizing them for humans.\n"
        "Given information about a repository, including a directory overview and the contents "
        "of some key files, you must produce a concise, clear explanation of:\n"
        "1. What the project does.\n"
        "2. The main technologies, languages, and frameworks used.\n"
        "3. How the project is structured (key modules/directories and their roles).\n\n"
        "Important: You must respond ONLY with a JSON object with the keys "
        '"summary", "technologies", and "structure". '
        "Do not include any additional commentary, markdown, or text outside the JSON."
    )

    parts = []
    parts.append(f"Repository: {repo_metadata.full_name}")
    parts.append(f"URL: {repo_metadata.html_url}")
    if repo_metadata.description:
        parts.append(f"Description: {repo_metadata.description}")
    parts.append(
        f"Stars: {repo_metadata.stargazers_count}, Forks: {repo_metadata.forks_count}"
    )
    parts.append(f"Languages (from GitHub): {language_summary}")
    parts.append(f"Technology hints: {tech_hints_str}")
    parts.append("Directory overview:")
    parts.append(analysis.dir_overview or "No directory information available.")

    if analysis.selected_files:
        parts.append("\nKey files (truncated for brevity):")
        for sf in analysis.selected_files:
            parts.append(f"\n### File: {sf.path}\n{sf.content}")

    parts.append(
        '\nUsing the information above, respond ONLY with a JSON object of the form:\n'
        '{"summary": "...", "technologies": ["..."], "structure": "..."}'
    )

    user_prompt = "\n".join(parts)
    return system_prompt, user_prompt


def call_llm(
    system_prompt: str,
    user_prompt: str,
    config: Optional[LLMConfig] = None,
) -> str:
    settings = get_settings()
    client = _get_client()

    model = settings.openai_model
    temperature = 0.2
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None

    if config is not None:
        if config.model:
            model = config.model
        if config.temperature is not None:
            temperature = config.temperature
        if config.top_p is not None:
            top_p = config.top_p
        if config.max_tokens is not None:
            max_tokens = config.max_tokens

    params: Dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if top_p is not None:
        params["top_p"] = top_p
    if max_tokens is not None:
        params["max_tokens"] = max_tokens

    try:
        response = client.chat.completions.create(**params)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "Failed to call OpenAI API"},
        ) from exc

    choice = response.choices[0]
    content = getattr(choice.message, "content", None)
    if not content:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "OpenAI API returned an empty response"},
        )
    return content


def parse_llm_result(
    raw_text: str,
    analysis: RepoAnalysisResult,
) -> SummarizeResponse:
    """
    Parse the LLM response into a SummarizeResponse.
    Falls back to a best-effort summary if JSON parsing fails.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        summary = str(data.get("summary", "")).strip()
        technologies_raw = data.get("technologies") or []
        if isinstance(technologies_raw, list):
            technologies = [
                str(t).strip() for t in technologies_raw if str(t).strip()
            ]
        else:
            technologies = [str(technologies_raw).strip()] if str(technologies_raw).strip() else []
        structure = str(data.get("structure", "")).strip()

        if summary and structure:
            # Deduplicate technologies while preserving order
            seen = set()
            deduped_technologies = []
            for tech in technologies:
                if tech not in seen:
                    seen.add(tech)
                    deduped_technologies.append(tech)

            return SummarizeResponse(
                summary=summary,
                technologies=deduped_technologies,
                structure=structure,
            )

    # Fallback: use raw text and analysis hints
    fallback_summary = raw_text.strip()
    if not fallback_summary:
        fallback_summary = "Summary not available from the language model."
    else:
        # Take only the first paragraph to keep it concise
        paragraphs = [p.strip() for p in fallback_summary.split("\n\n") if p.strip()]
        if paragraphs:
            fallback_summary = paragraphs[0]

    tech_set = set(analysis.tech_hints or [])
    technologies = sorted(tech_set)

    structure = analysis.dir_overview or "The repository structure could not be determined."

    return SummarizeResponse(
        summary=fallback_summary,
        technologies=technologies,
        structure=structure,
    )
