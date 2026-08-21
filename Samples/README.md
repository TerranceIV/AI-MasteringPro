# AI Agent Track — Runnable Samples

One capstone script per step, plus a few `b`-suffixed extras that close the gaps
found in the [plan audit](../guide-plan-audit.html). They build on each other: Step 5
and Step 6 **import** the Step 3 agent, so keep them in this folder and run
from here.

## Prerequisites

1. **Install `uv`** (the modern Python package manager — Step 1.7):
   - Windows (PowerShell): `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Docs: https://docs.astral.sh/uv/
   - Python **3.10+** is required (the MCP sample needs it).

2. **Set your Anthropic API key** (Step 1 and `step6b --offline` need no key):
   - PowerShell (current session): `$env:ANTHROPIC_API_KEY = "sk-ant-..."`
   - Get a key: https://console.anthropic.com/

3. **Add dependencies once** (from inside `samples/`):
   ```
   uv init
   uv add anthropic pydantic
   uv add langgraph langchain-anthropic     # only for Step 4
   uv add fastapi uvicorn                   # only for Step 6
   uv add "anthropic[mcp]" mcp              # only for Step 5b
   ```
   Or skip `uv init` entirely and use the throwaway form shown per-step below:
   `uv run --with "anthropic,pydantic" <file>.py`.

## Run each step

| Step | Command | Needs key? |
|------|---------|-----------|
| 1 · mock agent loop | `uv run --with pydantic step1_mock_agent.py` | no |
| 2 · first real LLM call | `uv run --with "anthropic,pydantic" step2_first_call.py` | yes |
| 2b · **documents → structured data** | `uv run --with "anthropic,pydantic" step2b_document_extract.py` | yes |
| 3 · async tool-calling agent | `uv run --with anthropic step3_agent.py "Total residents in Dorm A and B?"` | yes |
| 3b · **retrieval quality, measured** | `uv run --with "anthropic,pydantic" step3b_retrieval.py` | yes |
| 4 · same agent in LangGraph | `uv run --with "langgraph,langchain-anthropic" step4_langgraph_agent.py` | yes |
| 5 · orchestrator + 12-case eval suite | `uv run --with "anthropic,pydantic" step5_orchestrator.py` | yes |
| 5b · **MCP client + server** | `uv run --with "anthropic[mcp],mcp" step5b_mcp_client.py` | yes |
| 6 · FastAPI service (auth, SSE, tracing) | `uv run --with "fastapi,uvicorn,anthropic" uvicorn step6_service:app --reload` | yes |
| 6b · **governance & audit trail** | `uv run step6b_governance.py --offline` | no |

Test the Step 6 service in another terminal (it now requires an API key header):
```
$env:API_KEYS = "dev-key-123"      # in the terminal running uvicorn, before starting it

curl -s localhost:8000/ask -H "content-type: application/json" `
     -H "x-api-key: dev-key-123" `
     -d '{\"question\":\"Total residents across Dorm A and B?\"}'

curl -N localhost:8000/ask/stream -H "content-type: application/json" `
     -H "x-api-key: dev-key-123" `
     -d '{\"question\":\"What are the quiet hours?\"}'
```

Containerise it (module 6.5):
```
docker build -t dorm-agent .
docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY=$env:ANTHROPIC_API_KEY -e API_KEYS=dev-key-123 dorm-agent
```

## Read before you run — the walkthroughs

Every sample has a block-by-block walkthrough in [`code-explain/`](code-explain/).
Each one gives you, per block: what it does, **the concept it teaches**, and *why
it was written that way* rather than the obvious naive alternative — plus one
traced example, the traps, and a prediction to make before you press enter.

They form a chain, in reading order:

| | walkthrough | the idea it turns on |
|---|---|---|
| 1 | [step1_mock_agent](code-explain/step1_mock_agent.html) | the shape of agent code, with no LLM |
| 2 | [step2_first_call](code-explain/step2_first_call.html) | one real call — and the three patterns that now 400 |
| 2b | [step2b_document_extract](code-explain/step2b_document_extract.html) | a PDF is just a content block |
| 3 | [step3_agent](code-explain/step3_agent.html) | **the agent loop** — the keystone |
| 3b | [step3b_retrieval](code-explain/step3b_retrieval.html) | grade the retriever separately from the agent |
| 4 | [step4_langgraph_agent](code-explain/step4_langgraph_agent.html) | what a framework hides |
| 5 | [step5_orchestrator](code-explain/step5_orchestrator.html) | fan-out, and why eval sets need refusal cases |
| 5b | [step5b_mcp_client](code-explain/step5b_mcp_client.html) | tools discovered at runtime, not hardcoded |
| 6 | [step6_service](code-explain/step6_service.html) | auth, tracing, cost, streaming |
| 6b | [step6b_governance](code-explain/step6b_governance.html) | logs vs. **evidence** |

The four files that aren't numbered steps live one level down, in
[`code-explain/support/`](code-explain/support/):

| walkthrough | the idea it turns on |
|---|---|
| [config.py](code-explain/support/config.html) | the model is a dependency, not a fact of nature |
| [evals.py](code-explain/support/evals.html) | use the cheapest grader that can do the job |
| [mcp_dorm_server.py](code-explain/support/mcp_dorm_server.html) | the signature *is* the schema |
| [Dockerfile](code-explain/support/Dockerfile.html) | layer ordering, and why you drop root |

Regenerate any of them with the project command `/explain <file>`.

## What each file demonstrates

- **step1_mock_agent.py** — the *shape* of agent code with no LLM: decorator
  registry (1.1), async + Semaphore + retry (1.2, 1.5), Pydantic schemas +
  validation (1.3), messy-JSON parsing (1.4), env config (1.6).
- **step2_first_call.py** — structured output via a tool schema (2.6 ↔ 1.3),
  **async** streaming (2.7 ↔ 1.2), token counting (2.2), and `effort` instead of
  temperature (2.4 — see "What changed" below).
- **step2b_document_extract.py** — a PDF or image is just a content block (2.9);
  `messages.parse()` returns a validated Pydantic object; a confidence
  threshold routes low-certainty documents to a human (6.3).
- **step3_agent.py** — the real agent loop (3.1), concurrent tool dispatch (3.2),
  a keyword retrieval store (3.3), short-term memory (3.4), a step cap +
  errors-fed-back guardrail (3.6), prompt caching (6.2), and an `on_usage`
  hook that Step 6 turns into cost tracing (6.1). **Fully async** (1.2).
- **step3b_retrieval.py** — three retrievers (naive / BM25 / BM25+rerank) scored
  against 12 labelled queries (3.3a, 3.3b). Shows that the big win is free, the
  rerank win is modest, and only the *last* gap justifies a vector database.
- **step4_langgraph_agent.py** — the same agent on `create_react_agent`; a
  comment block lists exactly what the framework hides.
- **step5_orchestrator.py** — orchestrator/worker fan-out (5.2) reusing the
  Step 3 agent as a genuinely concurrent worker (5.5), scored by `evals.py`.
- **step5b_mcp_client.py** + **mcp_dorm_server.py** — connect to an MCP server,
  **discover** its tools at runtime, hand them to the model (5.3). Also your
  first look at the SDK's built-in agent loop (4.3).
- **evals.py** — 12 cases, two graders: cheap substring checks plus an
  LLM-as-judge for the cases a substring cannot express, like "must refuse to
  invent a number" (5.4).
- **step6_service.py** — the agent behind FastAPI with API-key auth (6.4),
  input/output guardrails (6.3), per-request tracing with token **and dollar**
  cost (6.1), and an SSE streaming endpoint (6.5).
- **step6b_governance.py** — PII redaction, a hash-chained tamper-evident audit
  log, a human approval gate on write tools, and a written retention/residency
  policy (6.7). Runs free with `--offline`.
- **Dockerfile** — containerised service, non-root user (6.5, 6.4).
- **../.github/workflows/eval.yml** — CI that fails the build when the pass rate
  drops below threshold (6.6).

## What changed in the API (and breaks old tutorials)

Current models — Sonnet 5, Opus 5, Opus 4.7/4.8 — **reject** three things that
almost every pre-2026 tutorial uses:

| Old pattern | What happens now | Do this instead |
|---|---|---|
| `temperature=0` / `top_p` / `top_k` | **400 error** | omit it; steer with the prompt and `output_config={"effort": ...}` |
| `thinking={"type":"enabled","budget_tokens":N}` | **400 error** | `thinking={"type":"adaptive"}` |
| assistant-turn prefill | **400 error** | `output_config={"format": ...}` or a system instruction |

Also: adaptive thinking is **on by default**, and `max_tokens` caps thinking +
answer *together* — so budgets tuned for older models can truncate. That is why
these samples use `max_tokens=4096` rather than `1024`.

## Safety notes (read before reusing this code)

- The `calculator` tool uses `eval()` behind a regex allowlist **for demo only**.
  Never `eval()` untrusted input in production — see Step 6.4 (Security).
- The Step 6 injection blocklist is intentionally crude. It also cannot catch
  the attack that actually matters for agents: injection arriving inside a
  *retrieved document* rather than the user's message. Treat tool output as
  untrusted (OWASP LLM Top 10: https://genai.owasp.org/llm-top-10/).
- `step6b_governance.py`'s PII regexes are illustrative. Real deployments need
  a proper detection service — a redactor that silently misses things is worse
  than none, because it manufactures false confidence.
- Model id, provider, effort and pricing are centralized in **`config.py`**.
  Override without editing files:
  `$env:AI_MODEL`, `$env:AI_PROVIDER`, `$env:AI_EFFORT`.
