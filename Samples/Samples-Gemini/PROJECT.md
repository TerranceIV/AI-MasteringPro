# AI Agent Track — Gemini samples

## Baseline: what this folder is

The **Gemini twin** of [`../`](../README.md). Same six capstones, same teaching
goals, rebuilt on Google's `google-genai` SDK instead of Anthropic's. The point
is not "Gemini instead of Claude" — it is to make visible which parts of *how to
build an agent* are universal and which parts are one vendor's API surface.
**Side-by-side diffing against `../step*.py` is most of the value here**; when
answering a question about a file, say what it shares with the Claude twin and
what it had to change.

- `step1` → `step6` build on each other. `step5`, `step5b`, `step6`, `step6b`
  import `step3_agent.py` from **this** folder; `step5` also imports this
  folder's `evals.py`. **Always run from inside `Samples-Gemini/`.**
- Credential is `GEMINI_API_KEY` (free, no card: <https://aistudio.google.com/apikey>).
  Steps 2–6 need it; step 1 and `step6b --offline` do not.
- Full run table, free-tier notes, and the Claude-vs-Gemini diff table:
  [README.md](README.md). Environment setup: [`../SETUP.md`](../SETUP.md).
- `step2b_document_extract.py` and Step 3's **prompt-caching** lesson are *not*
  ported (Gemini's context caching needs its own lesson design). Don't invent
  them; say they're absent and why.

## Who you're talking to

The user is learning AI agent engineering and says so — treat every answer as a
teaching moment:

- Plain language over jargon; expand an acronym the first time it appears.
- Explain **why**, not just what to type.
- Small snippets, not full-file rewrites.
- Point at real lines with clickable links: `[step3_agent.py:97](step3_agent.py#L97)`.
- Offer a short experiment they can run to see the concept move.

## Feature → learning outcome

Each file exists to make **one** idea land. Answer in terms of the outcome, not
just the code.

| File | Feature it demonstrates | Learning outcome |
|---|---|---|
| [step1_mock_agent.py](step1_mock_agent.py) | Mock agent loop: tool registry via decorator, async/`gather`/`Semaphore`, Pydantic tool schemas, retry with backoff+jitter, messy-JSON parsing | The *shape* of agent code is the reusable 80%; the vendor is a detail plugged in later. Byte-identical to the Claude twin — proof, not coincidence. |
| [step2_first_call.py](step2_first_call.py) | Native structured output (`response_schema` + `response_mime_type` → `response.parsed`), async streaming via `.aio`, token counting before sending | Concepts transfer one-for-one across vendors; call shapes do not. Gemini hands back validated objects natively where Claude fakes it with a forced tool call. |
| [step3_agent.py](step3_agent.py) | The loop by hand: `FunctionDeclaration` → `function_call` parts → `Part.from_function_response`, concurrent tool dispatch, hard step cap, errors returned as data | call → tool → observe → repeat, with automatic function calling **deliberately disabled** ([step3_agent.py:97](step3_agent.py#L97)) so the loop stays visible and comparable. |
| [step3b_retrieval.py](step3b_retrieval.py) | Three retrievers (naive overlap / BM25 / BM25+LLM rerank) scored on 12 labelled queries | Reranking fixes **ordering, not recall**. Retrieval itself is plain Python — only the rerank call is vendor-shaped. |
| [step4_langgraph_agent.py](step4_langgraph_agent.py) | The same agent on LangGraph + `ChatGoogleGenerativeAI` | The concrete value of a framework is **portability**, not less code: this file's diff against the Claude twin is ~3 lines, while `step3_agent.py` needed a rewrite. |
| [step5_orchestrator.py](step5_orchestrator.py) | Orchestrator/worker fan-out reusing this folder's Step 3 as the worker, graded by `evals.py`, `--threshold` for CI | Split → run workers concurrently → synthesize. The pattern is vendor-neutral; only synthesis touches Gemini. |
| [step5b_mcp_client.py](step5b_mcp_client.py) + [mcp_dorm_server.py](mcp_dorm_server.py) | MCP (Model Context Protocol) over stdio; hand the raw `ClientSession` to Gemini and the SDK does discovery, schema translation, and the loop | Tools can be *discovered* rather than hardcoded. The server is byte-identical to the Claude folder's — that zero-diff **is** the standard's value proposition. |
| [evals.py](evals.py) | 12 cases, two graders: substring checks plus an LLM judge | Reach for a judge only when a substring check cannot express the pass condition. |
| [step6_service.py](step6_service.py) | FastAPI service: API-key auth, input/output guardrails, request-id trace line with tokens **and dollars**, timeout, SSE streaming | An agent becomes a product through observability, cost control, guardrails, security, and serving — 6.1–6.5, in that order. |
| [step6b_governance.py](step6b_governance.py) | PII redaction, hash-chained append-only audit log, human approval gate, written retention/residency policy | REDACT → AUDIT → APPROVE → RETAIN. Almost none of it is vendor-specific: governance is ordinary backend discipline. |
| [config.py](config.py) | One home for model id, pricing, `cost_usd()`, client construction, thinking budget | Model churn and price drift are configuration problems, not code problems. |
| [Dockerfile](Dockerfile) | Containerised service, non-root user | Same shape as the Claude folder's — deployment doesn't care which vendor answers. |

## The Gemini baseline (get these right before answering)

Facts that trip people up when they assume the two APIs are interchangeable.
Do **not** answer a Gemini question from Claude habits:

- **One client, two namespaces.** `genai.Client()` for everything; sync via
  `client.models`, async via `client.aio.models`. There is no separate async
  class, and `get_client()` here takes **no** `async_=` argument.
- **`temperature` works.** Gemini does not reject it the way current Claude
  models do. The thinking dial is `thinking_config.thinking_budget` — a raw
  **token count** (Flash can set `0` to disable thinking), not a qualitative
  effort label.
- **Thinking is billed separately.** Usage fields are `prompt_token_count`,
  `candidates_token_count`, `thoughts_token_count` — nothing like
  `input_tokens`/`output_tokens`. Porting a cost tracer without checking this
  doesn't crash, it silently under-reports. See `cost_usd()` in
  [config.py](config.py).
- **Structured output is native**: `response_schema` (pass the Pydantic class)
  plus `response_mime_type`, then read `response.parsed`.
- **Automatic function calling exists**, and is switched off on purpose in
  Step 3 and Step 5 so the loop stays teachable. `step5b` is where the built-in
  loop is allowed to run.
- **`langchain-google-genai` reads `GOOGLE_API_KEY`, not `GEMINI_API_KEY`** —
  Step 4 passes `google_api_key=` explicitly to avoid needing two env vars.
- **Free tier**: Flash / Flash-Lite only (Pro moved to paid-only in April 2026).
  Attaching a billing account to the key's Google Cloud project **silently
  deletes** the free tier — flag this before suggesting anything cloud-console.
- **Residency** is `genai.Client(vertexai=True, project=..., location=...)` —
  same idea as the Claude folder's `AI_PROVIDER`, Google Cloud only.
- Some exact call shapes (`response.parsed`, the `await …generate_content_stream`
  double-step, `function_call.args` as a plain dict, a raw `ClientSession` in
  `tools=[…]`) were written from docs and **not executed here**. If a first run
  errors, suspect those first — each call site comments what to try instead.

## The standard every sample must meet

Hold new or edited samples to this bar, and cite it when reviewing:

1. **Teachable over clever.** Every non-obvious line earns a comment saying
   *why*. Module numbers (e.g. `# 6.4`) stay in place — they tie code to lessons.
2. **Single file, `uv run`-able.** `uv run <file>.py`, or
   `uv run --with "<deps>" <file>.py` to skip project setup. The header docstring
   always states **Run / Deps / Env**, plus what the file teaches relative to its
   Claude twin.
3. **Config in one place.** Never hardcode a model string. Override with
   `$env:AI_MODEL` / `$env:AI_THINKING_BUDGET`. Get clients via `get_client()`,
   never `genai.Client()` directly — that is what keeps a sample portable.
4. **Real LLM calls are async** (`client.aio.models`). `step2`'s `classify()` is
   the deliberate single-shot exception; `step4` is framework-owned.
5. **Stay diffable against `../`.** Same corpus, same 12 eval cases, same
   ordering, same section headers. When a divergence is unavoidable, comment it
   as a teaching point instead of quietly rewriting. Files with nothing
   vendor-specific in them (`step1_mock_agent.py`, `mcp_dorm_server.py`) stay
   **byte-identical** — don't "improve" them here alone.
6. **Demo-grade code is labelled, not hardened.** `eval()` in the calculator
   ([step3_agent.py:57](step3_agent.py#L57)), the Step 6 injection `BLOCKLIST`,
   and the `step6b` PII regexes are crude on purpose. Name the production gap
   (OWASP LLM Top 10, a real PII detection service, a real sandbox) — don't
   silently harden them, that deletes the lesson.
7. **Honest about cost and limits.** Prices in `config.py` are list prices and go
   stale fast; link the pricing page rather than quoting from memory.
8. **Unverified shapes get flagged**, in the file and in the README's honesty
   check. Never present an unrun call as tested.

## Things that look like bugs but aren't

Check for a nearby comment before calling something broken:

- [step1_mock_agent.py:152](step1_mock_agent.py#L152) sends `units: "x"` so the
  Pydantic `Literal["c","f"]` rejects it — that `ERROR: bad args` line **is** the
  lesson (1.3).
- `mock_call` fails ~**50%** of the time on purpose
  ([step1_mock_agent.py:101](step1_mock_agent.py#L101)) to exercise the
  retry/backoff decorator.
- `step3b_retrieval.py` scores 0.00 on **"Can I keep a cat?"** at every stage
  ([step3b_retrieval.py:65](step3b_retrieval.py#L65)). Intentional — the corpus
  has no pets document, so no lexical retriever can reach it. That single failure
  is the only honest argument in the folder for adding a vector index.
- `evals.py` contains cases the agent is supposed to **refuse**
  (`grounding-unknown-block`, `grounding-out-of-scope`). A confident numeric
  answer there is a FAIL, not a pass.
- `audit-log.jsonl` is generated. Its hash chain means hand-editing a line is
  *detectable* — `verify()` reporting a chain break is the exercise, not a
  corruption bug.
- No cache-hit numbers anywhere: prompt caching isn't ported to this folder.
  That's the documented gap, not a missing feature.

## Project commands

- `/explain <file>` — read-only walkthrough before you run it.
- `/resolve <error>` — explain and fix an error, teaching-first.
- `/refactor <file>` — ranked recommendations with reasoning and trade-offs.
