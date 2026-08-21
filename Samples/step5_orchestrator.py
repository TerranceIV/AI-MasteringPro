"""
Step 5 Capstone -- orchestrator/worker fan-out, graded by a real eval suite.

Reuses the Step 3 agent as a WORKER. The orchestrator splits a question into
sub-tasks, runs the workers CONCURRENTLY (1.2 / 5.2), synthesizes their
findings, then scores itself against the 12-case eval suite in evals.py (5.4).

Because the Step 3 agent is now async, the workers are genuinely concurrent --
no threads, no `to_thread` workaround. Two workers that each take 3 seconds
finish in 3 seconds.

MCP lives in its own sample: see step5b_mcp_client.py.

Run:   uv run step5_orchestrator.py
       uv run step5_orchestrator.py --threshold 0.75    # exit 1 below this (used by CI)
Deps:  anthropic pydantic
Env:   ANTHROPIC_API_KEY
Note:  imports step3_agent.py and evals.py from this folder -- run from inside samples/.
"""
import argparse
import asyncio
import os
import sys

import evals
from config import EFFORT, MODEL, get_client
from step3_agent import run as worker   # 5.5 reuse the Step 3 agent as a worker

client = get_client(async_=True)


def synthesize_prompt(question: str, findings: list[str]) -> str:
    joined = "\n".join(f"- {f}" for f in findings)
    return (
        f"Question: {question}\n\nWorker findings:\n{joined}\n\n"
        "Give a single concise final answer based ONLY on the findings above. "
        "If the findings do not contain the answer, say that the information "
        "is not available -- do not fill the gap yourself."
    )


async def synthesize(question: str, findings: list[str]) -> str:
    msg = await client.messages.create(
        model=MODEL,
        max_tokens=2048,
        output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": synthesize_prompt(question, findings)}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


async def orchestrate(question: str, subtasks: list[str]) -> str:
    """5.2 fan-out -> synthesize. The whole orchestrator is these two lines.

    Worth noticing how little code this is. "Multi-agent orchestration" is
    mostly gather() plus a summarizing prompt -- which is exactly why the
    critical path tells you not to over-invest in it.
    """
    findings = await asyncio.gather(*(worker(s) for s in subtasks))   # 5.2 fan-out
    return await synthesize(question, list(findings))                # 5.2 synthesize


async def main(threshold: float | None) -> None:
    passed, total, rows = await evals.run_suite(orchestrate)
    rate = evals.report(passed, total, rows)

    # 6.6 this number is what CI gates on. A suite that never fails the build
    # is documentation, not a gate.
    if threshold is not None and rate < threshold:
        print(f"\nFAILED: pass rate {rate:.0%} is below the {threshold:.0%} threshold.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=None,
                        help="exit non-zero if the pass rate falls below this (0..1)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first (see README).")
    asyncio.run(main(args.threshold))
