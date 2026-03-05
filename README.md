# GitHub Repository Summarizer

This project is a small FastAPI service that accepts a public GitHub repository URL, analyzes the repository structure and key files, and uses OpenAI to generate a human‑readable summary.

It exposes:

- `POST /summarize` — JSON API that returns a summary, technologies, and project structure.
- `GET /` — simple HTML page with a form to enter a GitHub URL and display the summary.

## Requirements

- Python 3.10+
- An OpenAI API key (`OPENAI_API_KEY`)
 - (Optional but recommended) A GitHub personal access token (`GITHUB_TOKEN`) for higher rate limits

## Setup

1. Clone this repository and change into its directory.

2. (Recommended) Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set your OpenAI API key (replace `sk-...` with your key):

   ```bash
   export OPENAI_API_KEY="sk-..."        # Linux/macOS
   setx OPENAI_API_KEY "sk-..."          # Windows (PowerShell)
   ```

   Additionally, you can set an optional GitHub token to avoid hitting unauthenticated
   rate limits when summarizing multiple repositories:

   ```bash
   export GITHUB_TOKEN="ghp_..."          # Linux/macOS
   setx GITHUB_TOKEN "ghp_..."            # Windows (PowerShell)
   ```

   Both `OPENAI_API_KEY` and `GITHUB_TOKEN` can also be placed in a `.env` file and
   will be loaded automatically.

## Running the Server

Start the FastAPI application with Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

This will start the server on `http://localhost:8000`.

## Using the API

Send a `POST /summarize` request with a JSON body containing a public GitHub repository URL:

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'
```

You can optionally control the language model configuration via a `config` object:

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "github_url": "https://github.com/psf/requests",
    "config": {
      "temperature": 0.3,
      "top_p": 0.9,
      "max_tokens": 512,
      "model": "gpt-4o-mini"
    }
  }'
```

Example success response:

```json
{
  "summary": "Requests is a popular Python library for making HTTP requests in a human-friendly way...",
  "technologies": ["Python", "urllib3", "certifi"],
  "structure": "The project follows a standard Python package layout with source code in `requests/`, tests in `tests/`, and documentation in `docs/`."
}
```

On error, the API returns an appropriate HTTP status code and JSON:

```json
{
  "status": "error",
  "message": "Description of what went wrong"
}
```

## Using the Web UI

After starting the server, open your browser at:

- `http://localhost:8000/`

You will see a simple form:

- Paste a GitHub repository URL (e.g., `https://github.com/psf/requests`).
- Click **Summarize**.
- The page will display the summary, technologies, and structure below the form, or an error message if something goes wrong.

## Limitations

- Only public repositories on `github.com` are supported.
- The service uses a heuristic selection of files (README, docs, manifests, key source files) to stay within the LLM context window.
- Summaries depend on the quality of the OpenAI model and may not capture every detail of very large or complex projects.

## Development Notes

- Main code lives under `app/`:
  - `app/main.py` — FastAPI app and routes.
  - `app/github_client.py` — GitHub API integration and URL parsing.
  - `app/repo_analysis.py` — Repository file selection and structure analysis.
  - `app/llm_client.py` — OpenAI integration and prompt handling.
  - `app/config.py` — Configuration and environment handling.
- Static frontend is in `static/index.html`.
