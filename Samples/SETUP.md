# Precondition — Tools You Must Install Before Running the Samples

## The one precondition

> **Before running any sample, this machine must have `uv` on PATH, and (for
> Steps 2–6 only) an `ANTHROPIC_API_KEY` environment variable set.**
>
> You do **not** need to install Python separately — `uv` downloads and manages
> a Python for you the first time you run a script.

This Windows Server currently has **no Python and no uv on PATH**, so start at
Step 1 below. All commands are PowerShell.

---

## Step 1 — Install uv

Run this in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

It installs uv to `%USERPROFILE%\.local\bin` and adds that folder to your user
PATH.

**Corporate machine that blocks the install script?** Use winget instead (if
available):

```powershell
winget install --id=astral-sh.uv -e
```

---

## Step 2 — Open a NEW PowerShell window

PATH changes only apply to shells opened *after* the install. Close this window,
open a fresh PowerShell, then verify:

```powershell
uv --version
```

You should see something like `uv 0.x.y`. If you get "not recognized", the PATH
didn't refresh — either open another new window, or add it for this session:

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv --version
```

---

## Step 3 — Go to the samples folder

```powershell
cd "C:\Users\Administrator\Documents\DEV\Learning\samples"
```

---

## Step 4 — Verify with Step 1 (needs NO API key)

This is the fastest proof your toolchain works. `uv run --with` installs the
needed package (and a Python, if missing) into a cached throwaway environment —
no project setup required.

```powershell
uv run --with pydantic step1_mock_agent.py
```

Expected: it prints the registered tools, a JSON schema, and a list of tool
results (including one `ERROR: bad args` line — that invalid case is on purpose).
The first run is slower because uv is fetching Python + pydantic; later runs are
instant.

**If Step 1 printed results, your precondition for Steps 1 is satisfied.**

---

## Step 5 — Get and set your Anthropic API key (needed for Steps 2–6)

1. Create a key at <https://console.anthropic.com/> → **API Keys**.
2. Set it. Choose one:

   **This session only** (simplest, disappears when you close the window):
   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-...paste-your-key..."
   ```

   **Persistent for your user** (survives new windows; open a NEW shell after):
   ```powershell
   [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...paste...", "User")
   ```

3. Confirm it's visible:
   ```powershell
   if ($env:ANTHROPIC_API_KEY) { "key is set" } else { "NOT set" }
   ```

---

## Step 6 — Run the rest of the samples

From inside `samples/`:

```powershell
# Step 2 — first real LLM call (structured output + async streaming)
uv run --with "anthropic,pydantic" step2_first_call.py

# Step 2b — read a PDF, get back a validated object
uv run --with "anthropic,pydantic" step2b_document_extract.py

# Step 3 — async tool-calling agent with retrieval + memory
uv run --with anthropic step3_agent.py "Total residents across Dorm A and B?"

# Step 3b — score three retrievers against 12 labelled queries
uv run --with "anthropic,pydantic" step3b_retrieval.py

# Step 4 — the same agent rebuilt on LangGraph
uv run --with "langgraph,langchain-anthropic" step4_langgraph_agent.py

# Step 5 — orchestrator + workers + the 12-case eval suite (imports step3_agent.py)
uv run --with "anthropic,pydantic" step5_orchestrator.py

# Step 5b — connect to an MCP server and discover its tools (needs Python 3.10+)
uv run --with "anthropic[mcp],mcp" step5b_mcp_client.py

# Step 6 — serve the agent behind a FastAPI endpoint (now requires an API key header)
$env:API_KEYS = "dev-key-123"
uv run --with "fastapi,uvicorn,anthropic" uvicorn step6_service:app --reload

# Step 6b — governance mechanics, free and offline (no key, no API call)
uv run step6b_governance.py --offline
```

Test the Step 6 service from a second PowerShell window. Note the
`x-api-key` header — the service returns 401 without it, on purpose:

```powershell
curl.exe -s localhost:8000/ask `
  -H "content-type: application/json" -H "x-api-key: dev-key-123" `
  -d '{\"question\":\"Total residents across Dorm A and B?\"}'

# and the streaming endpoint (-N disables curl's buffering so you see deltas)
curl.exe -N localhost:8000/ask/stream `
  -H "content-type: application/json" -H "x-api-key: dev-key-123" `
  -d '{\"question\":\"What are the quiet hours?\"}'
```

---

## Summary — what each sample needs

| Sample | uv | Python | API key | Extra packages |
|--------|----|--------|---------|----------------|
| step1_mock_agent.py | ✅ | (uv fetches) | — | pydantic |
| step2_first_call.py | ✅ | (uv fetches) | ✅ | anthropic, pydantic |
| step2b_document_extract.py | ✅ | (uv fetches) | ✅ | anthropic, pydantic |
| step3_agent.py | ✅ | (uv fetches) | ✅ | anthropic |
| step3b_retrieval.py | ✅ | (uv fetches) | ✅ | anthropic, pydantic |
| step4_langgraph_agent.py | ✅ | (uv fetches) | ✅ | langgraph, langchain-anthropic |
| step5_orchestrator.py | ✅ | (uv fetches) | ✅ | anthropic, pydantic |
| step5b_mcp_client.py | ✅ | **3.10+** | ✅ | anthropic[mcp], mcp |
| step6_service.py | ✅ | (uv fetches) | ✅ | fastapi, uvicorn, anthropic |
| step6b_governance.py `--offline` | ✅ | (uv fetches) | — | *(stdlib only)* |

---

## Troubleshooting

- **`uv : not recognized`** — you didn't open a new shell after install (Step 2),
  or add `$env:USERPROFILE\.local\bin` to PATH for the session.
- **`irm ... | iex` is blocked** — the `-ExecutionPolicy ByPass` in the Step 1
  command handles most cases; if IT policy still blocks it, use the winget path.
- **`Could not resolve authentication` / 401** — `ANTHROPIC_API_KEY` isn't set in
  *this* shell (Step 5). If you set it persistently, open a new window.
- **Step 5/6 fail on import** — run them from *inside* `samples/`; they import
  `step3_agent.py`, which builds the Anthropic client at import time, so the key
  must be set first.
- **Slow first run** — normal. uv is downloading Python and packages; they're
  cached for every run after.
- **`400 ... temperature`** — a `temperature`, `top_p`, or `top_k` value crept
  back into a request. Current models reject non-default sampling parameters;
  delete the argument and use `output_config={"effort": ...}` instead. See the
  "What changed in the API" table in [README.md](README.md).
- **Answer is cut off mid-sentence** — `max_tokens` is too small. These models
  think adaptively by default and `max_tokens` caps thinking *plus* answer, so
  a budget that worked on an older model now truncates. Raise it.
- **Step 6 returns `401`** — the service requires `-H "x-api-key: ..."` matching
  one of the comma-separated values in `$env:API_KEYS`. That is deliberate
  (module 6.4): an unauthenticated agent endpoint is a bill anyone can run up.
- **Step 6 returns `503 server misconfigured`** — `API_KEYS` was never set in
  the shell that started uvicorn. Set it *before* launching the server.
- **Step 5b fails with `No module named 'mcp'`** — use the full dependency
  string: `uv run --with "anthropic[mcp],mcp" step5b_mcp_client.py`, on Python
  3.10 or newer.

---

## Alternative: the classic Python path (no uv)

If you'd rather not use uv:

```powershell
# 1. Install Python 3.12 from https://www.python.org/downloads/windows/
#    (tick "Add python.exe to PATH" in the installer), then open a NEW shell:
python --version

# 2. Create and activate a virtual environment in samples/
cd "C:\Users\Administrator\Documents\DEV\Learning\samples"
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install what you need and run
pip install pydantic anthropic
python step1_mock_agent.py
```
