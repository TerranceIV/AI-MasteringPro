# AI Agent Track — Gemini Samples

The Gemini twin of [`../Samples`](../Samples/README.md). Same capstones,
same teaching goals, rebuilt on Google's Gemini API instead of Claude's, so
you can see which parts of "how to build an agent" are universal and which
parts are just one vendor's API surface. Keep both folders and compare files
side by side — that comparison is most of the value here.

They build on each other the same way the Claude folder does: step5, step5b,
step6, and step6b all import step3_agent.py from **this** folder, and step5
also imports evals.py from this folder. Run everything from inside
`Samples-Gemini/`.

## Prerequisites

1. **`uv`** — same tool, same install, as [`../Samples/SETUP.md`](../Samples/SETUP.md).
2. **A free Gemini API key** — <https://aistudio.google.com/apikey>, no card
   required. Set it:
   ```powershell
   $env:GEMINI_API_KEY = "AIza...paste-your-key..."
   ```
   **Trap to avoid:** don't attach a billing account to that key's Google
   Cloud project unless you mean to. Doing so silently deletes the free tier
   for that project, and every call afterwards bills from the very first
   token — there's no warning banner, it just starts charging.
3. **Add dependencies once** (from inside `Samples-Gemini/`):
   ```
   uv init
   uv add google-genai pydantic
   uv add langgraph langchain-google-genai   # only for Step 4
   uv add fastapi uvicorn                    # only for Step 6
   uv add mcp                                # only for Step 5b
   ```
   Or skip `uv init` and use the throwaway form shown per-step below.

## Run each step

| Step | Command | Needs key? |
|------|---------|-----------|
| 1 · mock agent loop | `uv run --with pydantic step1_mock_agent.py` | no |
| 2 · first real LLM call | `uv run --with "google-genai,pydantic" step2_first_call.py` | yes |
| 3 · async tool-calling agent | `uv run --with google-genai step3_agent.py "Total residents in Dorm A and B?"` | yes |
| 3b · retrieval quality, measured | `uv run --with "google-genai,pydantic" step3b_retrieval.py` | yes |
| 4 · same agent in LangGraph | `uv run --with "langgraph,langchain-google-genai" step4_langgraph_agent.py` | yes |
| 5 · orchestrator + 12-case eval suite | `uv run --with "google-genai,pydantic" step5_orchestrator.py` | yes |
| 5b · MCP client + server | `uv run --with "google-genai,mcp" step5b_mcp_client.py` | yes |
| 6 · FastAPI service (auth, SSE, tracing) | `uv run --with "fastapi,uvicorn,google-genai" uvicorn step6_service:app --reload` | yes |
| 6b · governance & audit trail | `uv run step6b_governance.py --offline` | no |

Test the Step 6 service in another terminal (same shape as the Claude folder):
```powershell
$env:API_KEYS = "dev-key-123"

curl.exe -s localhost:8000/ask -H "content-type: application/json" `
     -H "x-api-key: dev-key-123" `
     -d '{\"question\":\"Total residents across Dorm A and B?\"}'

curl.exe -N localhost:8000/ask/stream -H "content-type: application/json" `
     -H "x-api-key: dev-key-123" `
     -d '{\"question\":\"What are the quiet hours?\"}'
```

Containerise it:
```powershell
docker build -t dorm-agent-gemini Samples-Gemini/
docker run --rm -p 8000:8000 -e GEMINI_API_KEY=$env:GEMINI_API_KEY -e API_KEYS=dev-key-123 dorm-agent-gemini
```

## Free tier, as of 2026

Google AI Studio's free tier covers the **Flash and Flash-Lite** model
families (Pro-tier models moved to paid-only in April 2026). Limits are
roughly 5–15 requests per minute and up to ~1,000 requests/day depending on
the exact model — comfortable for working through these samples repeatedly.
`config.py`'s default model, `gemini-flash-latest`, is free-tier eligible.

## What each file demonstrates (relative to the Claude version)

- **step1_mock_agent.py** — byte-identical to `../Samples/step1_mock_agent.py`.
  No vendor code to change: the shape of agent code doesn't know which LLM
  Step 2 will end up calling.
- **step2_first_call.py** — structured output via Gemini's *native*
  `response_schema` (Claude fakes this with a forced tool call), async
  streaming through the same client's `.aio` namespace, token counting.
- **step3_agent.py** — the real agent loop, rebuilt on Gemini's manual
  function-calling shape (`FunctionDeclaration` → `function_call` parts →
  `Part.from_function_response`), with automatic function calling explicitly
  disabled so the loop stays visible. Prompt caching is **not** ported — see
  below.
- **step3b_retrieval.py** — same three retrievers (naive / BM25 / BM25+rerank)
  scored against the same 12 labelled queries; only the rerank call's shape
  changed.
- **step4_langgraph_agent.py** — the one file where swapping vendors is
  nearly free, because LangGraph's whole pitch is hiding the vendor behind a
  common interface. Diff it against the Claude version to see how little
  changes.
- **step5_orchestrator.py** — orchestrator/worker fan-out reusing this
  folder's step3_agent.py as the worker, scored by evals.py.
- **step5b_mcp_client.py** + **mcp_dorm_server.py** — the server is
  byte-identical to the Claude folder's; only the client changes, and Gemini
  has its own experimental convenience for MCP (hand it a raw `ClientSession`
  and it runs the loop for you), directly comparable to Anthropic's
  `tool_runner`.
- **evals.py** — the same 12 cases and the same substring/LLM-judge split;
  only the judge call's shape changed.
- **step6_service.py** — the agent behind FastAPI with API-key auth,
  input/output guardrails, per-request token **and dollar** cost tracing
  (note the different usage-field names — see the table below), and an SSE
  streaming endpoint.
- **step6b_governance.py** — PII redaction, the hash-chained audit log, a
  human approval gate, and a written retention/residency policy. Almost none
  of this file is vendor-specific; only the residency note changes (Vertex AI
  regions instead of Bedrock/Vertex/Foundry).
- **Dockerfile** — containerised service, non-root user, same shape as the
  Claude folder's.

## What's actually different from the Claude version

Treat every row as something that would trip you up if you assumed the two
APIs were interchangeable:

| Concept | Claude (`../Samples`) | Gemini (here) |
|---|---|---|
| Steering output | `temperature` **400s** on current models; use `output_config={"effort": ...}` instead | `temperature` works normally, exactly like pre-2026 tutorials assume |
| Thinking dial | `effort`: a qualitative label (`low`…`max`) | `thinking_config.thinking_budget`: a raw **token count**; Flash models can set it to `0` and disable thinking entirely |
| Structured output | No native mode — fake it by forcing a tool call, then manually validate the `tool_use` block | Native `response_schema` + `response_mime_type`; `response.parsed` hands back an already-validated object |
| Async client | Two separate classes: `Anthropic()` / `AsyncAnthropic()` | One `genai.Client()`; async calls go through `.aio.models` |
| Usage/cost fields | `input_tokens`, `output_tokens`, `cache_*_input_tokens` | `prompt_token_count`, `candidates_token_count`, `thoughts_token_count` (thinking is billed **separately**, not folded into output) |
| Tool-loop automation | Always manual — you dispatch every `tool_use` block yourself | Offers **automatic** function calling if you hand it real Python callables (disabled in step3/step5 to keep the loop visible and comparable) |
| MCP convenience | `anthropic[mcp]` extra + `client.beta.messages.tool_runner()` | Pass a raw `ClientSession` in `tools=[...]` (experimental) |
| LangChain env var | `ANTHROPIC_API_KEY` matches the rest of the folder | `langchain-google-genai` reads `GOOGLE_API_KEY` by default, **not** `GEMINI_API_KEY` — step4 passes it explicitly to avoid needing two env vars |
| Prompt caching | `cache_control: {"type": "ephemeral"}` breakpoints on `system`/`tools`, verified via `cache_read_input_tokens` | Shaped differently (context caching); **not covered in this folder** |
| Residency control | `AI_PROVIDER` → Bedrock / Vertex / Foundry, same Claude model | `genai.Client(vertexai=True, project=..., location=...)` — same idea, Google Cloud only |

## What's not in this folder

- **Prompt caching** (Claude's step3 lesson) — Gemini's caching model doesn't
  map onto Claude's `cache_control` breakpoints closely enough to "port"; it
  would need its own lesson design, not a rewrite.
- **step2b_document_extract.py** — not ported; nothing prevents adding it
  later the same way the rest of this folder was built.

## Honesty check

A handful of exact call shapes here (`response.parsed`, the `await ...`
streaming double-step, `function_call.args` as a plain dict, passing a raw
MCP `ClientSession` as a tool) were written from current `google-genai`
documentation, not executed locally — this environment can't make a live
Gemini API call to verify them. If a sample errors on first run, it's most
likely one of those; the comment at each call site says what to try instead.
