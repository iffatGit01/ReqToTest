# Test Case Generator

Paste requirements → an AI agent (Ollama, via an MCP server) generates test cases → download them as Excel →
enter your web app's URL → get a ready-to-run Playwright (Python) automation script.

## How it works

```
Browser ──> Flask app (MCP client) ──stdio──> mcp_server.py (MCP server) ──> Ollama
                  │
                  └── opens your app URL with Playwright to read its real fields/buttons
```

The MCP server exposes two tools:

| Tool                         | Purpose                                                          |
|------------------------------|------------------------------------------------------------------|
| `generate_test_cases`        | Requirements → structured test cases                             |
| `generate_playwright_script` | Test cases + real page elements → pytest + Playwright script     |

Swapping Ollama for another agent only means changing `_chat` in `mcp_server.py` (or pointing `app.py`
at a different MCP server that exposes the same tools).

## Run

1. Install and start Ollama, then pull a model:
   ```
   ollama pull llama3.2
   ollama serve
   ```
2. Install dependencies and the Playwright browser, then start the app:
   ```
   pip install -r requirements.txt
   playwright install chromium
   python app.py
   ```
3. Open http://localhost:5000

## Running a generated script

```
pytest test_app.py --headed
```

Always review generated scripts before relying on them. The app never runs them for you.

## Tips for better results

- Pick **Standard** or **Thorough** coverage for more test cases.
- Bigger models (e.g. `llama3.1:8b`, `qwen2.5:7b` or larger) write noticeably better test cases and scripts than 1–3B models.
- For the Playwright step, use a page that is reachable without login. Select only the test cases you want to automate.

## Configuration (environment variables)

| Variable       | Default                  | Purpose                        |
|----------------|--------------------------|--------------------------------|
| `OLLAMA_HOST`  | `http://localhost:11434` | Where Ollama is running        |
| `OLLAMA_MODEL` | `llama3.2`               | Model used if none is selected |
