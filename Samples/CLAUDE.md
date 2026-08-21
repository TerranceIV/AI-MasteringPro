# AI Agent Track — learning samples

## What this project is

A **teaching** repo, not a product. `step1` → `step6` build on each other and are
meant to be read as much as run. Later steps import earlier ones
(`step5` and `step6` import `step3`), so run everything from inside `samples/`.

Full map of what each file demonstrates: [README.md](README.md).
Environment setup: [SETUP.md](SETUP.md).
Why the extra `b`-suffixed files exist: [../guide-plan-audit.html](../guide-plan-audit.html).

## Who you're talking to

The user is learning AI agent engineering and says so — treat every answer as a
teaching moment:

- Plain language over jargon; expand an acronym the first time it appears.
- Explain **why**, not just what to type.
- Small snippets, not full-file rewrites.
- Point at real lines with clickable links: `[step3_agent.py:42](step3_agent.py#L42)`.
- Offer a short experiment they can run to see the concept move.

## Things that look like bugs but aren't

Some samples fail **on purpose** to demonstrate a guardrail. Check for a nearby
comment before calling something broken:

- `step1_mock_agent.py` sends `units: "x"` to `get_weather` so Pydantic
  validation rejects it — that `ERROR: bad args` line is the lesson.
- `mock_call` fails ~30% of the time on purpose, to exercise the retry/backoff
  decorator.
- `step3_agent.py` prints `cache_read_input_tokens` of 0. Correct: prompt
  caching needs a ~1024-token prefix and this toy prompt is far smaller. The
  zero is the teaching point — it is how you *verify* caching rather than
  assume it.
- `step3b_retrieval.py` scores 0.00 on "Can I keep a cat?" at every stage.
  Intentional — it is the one failure lexical search cannot fix, and the only
  honest argument for adding a vector index.
- `evals.py` includes cases the agent is supposed to *refuse*
  (`grounding-unknown-block`, `grounding-out-of-scope`). A confident numeric
  answer there is a FAIL, not a pass.

## Conventions

- Model id, provider, effort, and pricing live in **one** place: `config.py`.
  Never hardcode a model string in a sample. Override via `$env:AI_MODEL`,
  `$env:AI_PROVIDER`, `$env:AI_EFFORT`.
- Get a client with `get_client()` / `get_client(async_=True)` — never construct
  `Anthropic()` directly, or the sample stops being provider-portable.
- Real LLM calls are **async**. `step2b` and `step4` are the deliberate
  exceptions (single-shot and framework-owned respectively).
- Steps 2–6 need `ANTHROPIC_API_KEY`. Step 1 and `step6b --offline` need no key.
- Run with `uv run <file>.py`, or `uv run --with "<deps>" <file>.py` to skip
  project setup.
- `eval()` in the calculator tool, the Step 6 injection blocklist, and the
  `step6b` PII regexes are deliberately crude demo code. Flag the production
  gap; don't silently harden them.
- `audit-log.jsonl` is generated and gitignored. Its hash chain means editing a
  line by hand is *detectable* — that is the exercise, not a corruption bug.

## Project commands

- `/explain <file>` — read-only walkthrough before you run it.
- `/resolve <error>` — explain and fix an error, teaching-first.
- `/refactor <file>` — ranked recommendations with reasoning and trade-offs.
