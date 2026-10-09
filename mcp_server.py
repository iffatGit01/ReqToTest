"""MCP server exposing two tools backed by Ollama:

  - generate_test_cases(requirements, model, count)
  - generate_playwright_script(test_cases_json, page_snapshot, url, model)

The web app connects to this server as an MCP client. To use a different AI
agent later, replace `_chat` (or point the app at another MCP server that
exposes tools with the same names and signatures).
"""
import ast
import json
import os
import re

import requests
try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

mcp = FastMCP("testcase-agent")


# --------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------
def _chat(messages: list[dict], model: str, json_mode: bool = False,
          temperature: float = 0.4) -> str:
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 8192},
        "messages": messages,
    }
    if json_mode:
        payload["format"] = "json"
    resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=900)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _error_message(e: Exception, model: str) -> str:
    if isinstance(e, requests.ConnectionError):
        return f"Could not reach Ollama at {OLLAMA_HOST}. Make sure it is running (ollama serve)."
    if isinstance(e, requests.HTTPError):
        detail = e.response.text[:200] if e.response is not None else str(e)
        return f"Ollama returned an error (is the model '{model}' pulled?): {detail}"
    if isinstance(e, requests.Timeout):
        return "Ollama took too long to respond. Try a smaller model or fewer test cases."
    return "The model returned an unexpected response. Try again or use a larger model."


# --------------------------------------------------------------------------
# Test cases
# --------------------------------------------------------------------------
TESTCASE_PROMPT = """You are a senior QA engineer. Read the requirements and design a \
thorough, realistic test suite.

Write AT LEAST {count} distinct test cases. Cover ALL of these areas that apply:
- Positive / happy paths for every requirement
- Negative cases: invalid, missing or malformed input, wrong state, unauthorized access
- Boundary values: min, max, just below / just above limits, empty, very long input
- Edge cases: special characters, whitespace, duplicates, concurrency, repeated actions
- Security (injection, access control, session handling) and usability (error messages, \
keyboard use, accessibility) where relevant
- Error handling and recovery

Quality rules:
- Each test case checks ONE thing and has a specific title (not "Test login").
- Use concrete example data in the steps (real-looking emails, numbers, strings).
- Steps are short, ordered, user-level actions.
- expected_result is specific and verifiable (exact message, state or value), never "works correctly".
- Priority: High for core flows and security, Medium for validation, Low for cosmetic.
- Do not repeat the same scenario twice.

Respond ONLY with JSON in this shape (the list must contain {count}+ items; the two below \
only show the format):
{{"test_cases": [
  {{"id": "TC001", "title": "Login succeeds with valid credentials", "type": "Functional",
   "priority": "High", "preconditions": "User jane@example.com exists with password Passw0rd!",
   "steps": ["Open the login page", "Enter jane@example.com and Passw0rd!", "Click Sign in"],
   "expected_result": "User lands on the dashboard and sees 'Welcome, Jane'"}},
  {{"id": "TC002", "title": "Login rejected when password is empty", "type": "Negative",
   "priority": "Medium", "preconditions": "Login page is open",
   "steps": ["Enter jane@example.com", "Leave password empty", "Click Sign in"],
   "expected_result": "Error 'Password is required' is shown and the user stays on the login page"}}
]}}
Allowed type values: Functional, Negative, Boundary, Edge, Security, Usability, Performance."""


def _normalize(raw: str) -> list[dict]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("test_cases") or next(
            (v for v in data.values() if isinstance(v, list)), []
        )
    cases = []
    for tc in data:
        if not isinstance(tc, dict):
            continue
        steps = tc.get("steps", [])
        if isinstance(steps, str):
            steps = [s.strip() for s in steps.split("\n") if s.strip()]
        cases.append(
            {
                "title": str(tc.get("title", "")).strip(),
                "type": str(tc.get("type", "Functional")),
                "priority": str(tc.get("priority", "Medium")),
                "preconditions": str(tc.get("preconditions", "")),
                "steps": [str(s) for s in steps],
                "expected_result": str(tc.get("expected_result", "")),
            }
        )
    return cases


def _merge(existing: list[dict], new: list[dict]) -> list[dict]:
    seen = {c["title"].lower() for c in existing}
    for c in new:
        if c["title"] and c["title"].lower() not in seen:
            existing.append(c)
            seen.add(c["title"].lower())
    return existing


def _generate_cases(requirements: str, model: str, count: int) -> list[dict]:
    messages = [
        {"role": "system", "content": TESTCASE_PROMPT.format(count=count)},
        {"role": "user", "content": f"Requirements:\n{requirements}"},
    ]
    cases = _normalize(_chat(messages, model, json_mode=True))

    # Small models often stop early: ask for the missing ones (up to 2 follow-ups).
    for _ in range(2):
        if len(cases) >= max(3, int(count * 0.8)):
            break
        done = "; ".join(c["title"] for c in cases)
        messages = [
            {"role": "system", "content": TESTCASE_PROMPT.format(count=count)},
            {"role": "user", "content": (
                f"Requirements:\n{requirements}\n\n"
                f"These test cases already exist: {done}\n"
                f"Write {count - len(cases)} MORE different test cases (negative, boundary, "
                f"edge and security scenarios first). Do not repeat existing ones."
            )},
        ]
        try:
            cases = _merge(cases, _normalize(_chat(messages, model, json_mode=True)))
        except (json.JSONDecodeError, AttributeError, TypeError):
            break

    for i, c in enumerate(cases, 1):  # models repeat / skip IDs, so renumber
        c["id"] = f"TC{i:03d}"
    return [{"id": c["id"], **{k: v for k, v in c.items() if k != "id"}} for c in cases]


@mcp.tool()
def generate_test_cases(requirements: str, model: str = "", count: int = 15) -> str:
    """Analyze software requirements and return test cases as a JSON array."""
    model = model or DEFAULT_MODEL
    count = max(3, min(int(count), 40))
    try:
        cases = _generate_cases(requirements, model, count)
        if not cases:
            raise ValueError("no test cases")
        return json.dumps(cases)
    except (requests.RequestException, json.JSONDecodeError, AttributeError,
            TypeError, ValueError) as e:
        return json.dumps({"error": _error_message(e, model)})


# --------------------------------------------------------------------------
# Playwright script
# --------------------------------------------------------------------------
SCRIPT_PROMPT = """You are a senior test automation engineer. Write ONE Python test file \
using pytest and Playwright's sync API (the pytest-playwright `page` fixture).

Rules:
- Start with: import re, import pytest, from playwright.sync_api import Page, expect
- Define BASE_URL = "{url}" and call page.goto(BASE_URL) at the start of every test.
- Write one test function per test case, named test_<id in lowercase>_<short_snake_case_title>, \
with a docstring listing the steps.
- Use ONLY elements that appear in the PAGE ELEMENTS list. Prefer get_by_label, \
get_by_placeholder, get_by_role (with name), get_by_test_id, then page.locator("#id") or \
page.locator("[name='...']"). Never invent selectors, ids or URLs.
- Assert the test case's expected_result with expect(...) (expect(page).to_have_url, \
expect(locator).to_be_visible, to_have_text, to_contain_text, ...).
- If a step needs something that is not on the page (another page, an email, a database), \
write a `# TODO:` comment explaining it and call pytest.skip("reason") at that point.
- Keep the code simple, readable and runnable as is.
- Output ONLY the Python code. No markdown fences, no explanations."""


def _clean_code(text: str) -> str:
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def _syntax_error(code: str) -> str | None:
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"line {e.lineno}: {e.msg}"


@mcp.tool()
def generate_playwright_script(test_cases_json: str, page_snapshot: str, url: str,
                               model: str = "") -> str:
    """Write a pytest + Playwright (Python) automation script for the given test cases,
    using the real page elements from `page_snapshot` (JSON). Returns JSON with `script`."""
    model = model or DEFAULT_MODEL
    try:
        cases = json.loads(test_cases_json)
        compact = [
            {k: c.get(k) for k in ("id", "title", "preconditions", "steps", "expected_result")}
            for c in cases
        ]
        messages = [
            {"role": "system", "content": SCRIPT_PROMPT.format(url=url)},
            {"role": "user", "content": (
                f"APPLICATION URL: {url}\n\n"
                f"PAGE ELEMENTS (JSON):\n{page_snapshot}\n\n"
                f"TEST CASES (JSON):\n{json.dumps(compact, indent=1)}"
            )},
        ]
        code = _clean_code(_chat(messages, model, temperature=0.2))

        warning = None
        problem = _syntax_error(code)
        if problem:  # one repair attempt
            messages += [
                {"role": "assistant", "content": code},
                {"role": "user", "content": (
                    f"The code has a Python syntax error ({problem}). "
                    f"Return the complete corrected file, code only."
                )},
            ]
            code = _clean_code(_chat(messages, model, temperature=0.1))
            problem = _syntax_error(code)
            if problem:
                warning = (f"The model's script has a syntax error ({problem}). "
                           f"Fix it manually or try again with a larger model.")
        return json.dumps({"script": code, "warning": warning})
    except (requests.RequestException, json.JSONDecodeError, AttributeError,
            TypeError, ValueError) as e:
        return json.dumps({"error": _error_message(e, model)})


if __name__ == "__main__":
    mcp.run()  # stdio transport
