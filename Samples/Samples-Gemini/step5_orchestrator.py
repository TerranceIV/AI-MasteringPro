"""
Step 5 Capstone (Gemini twin) -- orchestrator/worker fan-out, graded by the
12-case eval suite in evals.py. Same pattern as ../Samples/step5_orchestrator.py.

Reuses THIS folder's step3_agent.py as the worker. The orchestration pattern
itself -- split into subtasks, run workers CONCURRENTLY, synthesize their
findings with one more model call -- is vendor-neutral; only the synthesis
call's shape is Gemini-specific.

MCP lives in its own sample: see step5b_mcp_client.py.

Run:   uv run step5_orchestrator.py
       uv run step5_orchestrator.py --threshold 0.75    # exit 1 below this (used by CI)
Deps:  google-genai pydantic
Env:   GEMINI_API_KEY
Note:  imports step3_agent.py and evals.py from this folder -- run from
       inside Samples-Gemini/.
"""
import argparse
import asyncio
import sys

import evals
from google.genai import types
from step3_agent import run as worker   # 5.5-equivalent: reuse this folder's Step 3 agent

from config import MAX_OUTPUT_TOKENS_DEFAULT, MODEL, THINKING_BUDGET, get_client

client = get_client()


def synthesize_prompt(question: str, findings: list[str]) -> str:
    joined = "\n".join(f"- {f}" for f in findings)
    return (
        f"Question: {question}\n\nWorker findings:\n{joined}\n\n"
        "Give a single concise final answer based ONLY on the findings above. "
        "If the findings do not contain the answer, say that the information "
        "is not available -- do not fill the gap yourself."
    )


async def synthesize(question: str, findings: list[str]) -> str:
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=synthesize_prompt(question, findings),
        config=types.GenerateContentConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS_DEFAULT,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
        ),
    )
    return response.text


async def orchestrate(question: str, subtasks: list[str]) -> str:
    """Fan-out -> synthesize. The whole orchestrator is these two lines, same
    as the Claude version -- "multi-agent orchestration" is mostly gather()
    plus a summarizing prompt, which doesn't change with the vendor.
    """
    findings = await asyncio.gather(*(worker(s) for s in subtasks))
    return await synthesize(question, list(findings))


async def main(threshold: float | None) -> None:
    passed, total, rows = await evals.run_suite(orchestrate)
    rate = evals.report(passed, total, rows)

    # this number is what CI gates on. A suite that never fails the build is
    # documentation, not a gate.
    if threshold is not None and rate < threshold:
        print(f"\nFAILED: pass rate {rate:.0%} is below the {threshold:.0%} threshold.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=None,
                        help="exit non-zero if the pass rate falls below this (0..1)")
    args = parser.parse_args()
    asyncio.run(main(args.threshold))
