# Becoming an AI Agent Engineer

A self-paced track from Python reflexes to a production agent service.
Six steps, 42 modules, 13 runnable samples, every one explained line by line.

---

## 👉 Open this first

### **[`00-START-HERE.html`](00-START-HERE.html)**

Double-click it. It is your home base — it remembers your progress, links
everything else, and tells you honestly how long this takes. If you read
nothing else on this page, open that file.

---

## The reading order, as the filenames

Files are numbered so the sequence is obvious from the folder listing alone.
**Numbers are the path. `guide-` files are companions you can read any time.**

| | file | what it is |
|---|---|---|
| **00** | [00-START-HERE.html](00-START-HERE.html) | ★ **the entry point** — setup, checklist, saved progress |
| 01 | [01-python-fluency-map.html](01-python-fluency-map.html) | Step 1 · the Python subset agents assume |
| 02 | [02-llm-fundamentals-map.html](02-llm-fundamentals-map.html) | Step 2 · the model as a black box |
| 03 | [03-agent-building-blocks-map.html](03-agent-building-blocks-map.html) | Step 3 · **the agent loop — the keystone** |
| 04 | [04-frameworks-map.html](04-frameworks-map.html) | Step 4 · let a framework remove the boilerplate |
| 05 | [05-multi-agent-mcp-map.html](05-multi-agent-mcp-map.html) | Step 5 · orchestration, MCP, evaluation |
| 06 | [06-production-map.html](06-production-map.html) | Step 6 · ship it — observability, security, governance |

### Companions — read any time

| file | what it is | when |
|---|---|---|
| [guide-critical-path.html](guide-critical-path.html) | what to **master** vs **skim** across all 42 modules | early — especially if short on time |
| [guide-exit-checks.html](guide-exit-checks.html) | 30 "predict what this does" questions + 2 rebuild drills | after each step |
| [guide-plan-audit.html](guide-plan-audit.html) | an honest audit of whether this track is comprehensive | curiosity, or before extending it |
| [index.html](index.html) | the visual hub — same content, map-first layout | if you prefer browsing to a checklist |

### Code

| folder | what's in it |
|---|---|
| [samples/](samples/) | 13 runnable Python files, one capstone per step — start with [samples/README.md](samples/README.md) |
| [samples/code-explain/](samples/code-explain/) | a block-by-block walkthrough of every sample |
| [samples/code-explain/support/](samples/code-explain/support/) | walkthroughs for the non-step files: config, evals, MCP server, Dockerfile |

---

## If you have 30 minutes right now

```powershell
# 1. install the only tool you need (it brings Python with it)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. open a NEW PowerShell window, then:
cd samples
uv run --with pydantic step1_mock_agent.py     # needs no API key
```

That prints a working agent loop. Then open
**[00-START-HERE.html](00-START-HERE.html)** and tick the first box.

Full setup and troubleshooting: [samples/SETUP.md](samples/SETUP.md).

---

## What this track is, in one paragraph

An agent is a `while` loop plus tool dispatch. Every framework, every
multi-agent system, and every AI product is that with decoration on top. So the
track builds it **by hand** in Step 3 before touching a framework in Step 4 —
which means a framework upgrade, or a framework dying, never resets your
skills. Steps 5 and 6 then make it cooperate, measure it, and ship it safely.
The whole thing is one continuous build: Step 5 and Step 6 literally `import`
the agent you wrote in Step 3.

## Honest expectations

- **~4–6 months of evenings** to finish Step 6, at 30–60 minutes a day.
  The per-step estimates on the six maps add up to that.
- **Step 3 alone is 3–4 weeks** and is supposed to be. It is the step that
  matters most; you are not behind.
- Short on time? Don't half-finish every step. Follow the 20% path on the
  [Critical Path](guide-critical-path.html) instead:
  `1.2+1.3 → 2.5+2.6 → 3.1+3.2 → 5.4 → 6.7`.

## One thing that will save you an afternoon

Current models (Sonnet 5, Opus 5, Opus 4.7/4.8) **reject** three things that
essentially every pre-2026 LLM tutorial uses:

| old pattern | what happens now | do this instead |
|---|---|---|
| `temperature=0` / `top_p` / `top_k` | **400 error** | omit it; steer with the prompt and `output_config={"effort": ...}` |
| `thinking={"budget_tokens": N}` | **400 error** | `thinking={"type": "adaptive"}` |
| assistant-turn prefill | **400 error** | structured output, or a system instruction |

Adaptive thinking is also **on by default**, and `max_tokens` caps thinking
*plus* the answer together — so a budget copied from an older tutorial
truncates mid-sentence. Module 2.4 in
[Step 2](02-llm-fundamentals-map.html) covers all of it.

---

*Everything here is local static HTML — no server, no build step. Open the files in any browser.*