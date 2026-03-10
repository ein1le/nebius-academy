# GitHub Repository Summarizer

This project is a small FastAPI service that accepts a public GitHub repository URL, analyzes the repository structure and key files, and uses OpenAI to generate a human‑readable summary. 
This application clones repositories via SSH with an HTTPS clone as a fallback. 
This avoids GitHub API rate limits and matches typical production setups where CI and services access code using SSH deploy keys.
It is a submission to the Nebius Academy Performance Engineering admission assignment

It exposes:

- `POST /summarize` — JSON API that returns a summary, technologies, and project structure.
- `GET /` — simple HTML page with a form to enter a GitHub URL and display the summary.

## Requirements

- Python 3.10+
- An OpenAI API key (`OPENAI_API_KEY`)

## Setup

1. Clone this repository to a local directory

2. Create and activate a virtual environment:

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

   `OPENAI_API_KEY` can also be placed in a `.env` file and
   will be loaded automatically.

5. Configure SSH for `git clone`:

   The backend clones repositories using `git` (preferring SSH). To avoid prompts and make this work smoothly:

   - Generate a key if you do not have one:

     ```bash
     ssh-keygen -t ed25519 -C "your_email@example.com"
     ```

     Accept the default location (e.g. `~/.ssh/id_ed25519`) and set a passphrase if you like.

   - Copy the contents of `id_ed25519.pub` and add it to GitHub under
     **Settings → SSH and GPG keys → New SSH key**.

   - Test your setup:

     ```bash
     ssh -T git@github.com
     ```

   If SSH is not configured or fails, the app will fall back to cloning over HTTPS, but SSH is preferred.

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

Optionally control the language model configuration via a `config` object:

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

Simple form display:

- Paste a GitHub repository URL (e.g., `https://github.com/psf/requests`).
- Click **Summarize**.
- The page will display the summary, technologies, and structure below the form, or an error message if something goes wrong.

## Limitations

- Only public repositories on `github.com` are supported.
- The service uses a heuristic selection of files (README, docs, manifests, key source files) to stay within the LLM context window.
- Summaries depend on the quality of the OpenAI model and may not capture every detail of very large or complex projects.
