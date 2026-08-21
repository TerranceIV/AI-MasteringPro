"""
The eval suite.  (module 5.4, and the thing CI gates on in 6.6)

Two graders, deliberately:

  SUBSTRING  -- cheap, deterministic, free. Use it whenever the right answer
                contains a specific fact. Never use it to judge prose.
  LLM JUDGE  -- costs a call and is not perfectly stable, but it can grade
                things a substring cannot: did the agent REFUSE to invent a
                fact? did it stay grounded? was the reasoning sound?

The rule of thumb: reach for the judge only when you cannot write a substring
check. A suite that is 80% deterministic runs fast and never flakes.

Used by:  step5_orchestrator.py (interactive) and .github/workflows/eval.yml (CI)
"""
import asyncio

from pydantic import BaseModel, Field

from config import MODEL, get_client

client = get_client(async_=True)

# --- the suite --------------------------------------------------------------
# `subtasks` is what the orchestrator fans out (5.2). `expect` is the cheap
# grader. `rubric` is what the judge is asked to check -- write it as a
# PASS CONDITION, not as a description of the task.
EVALS = [
    {
        "id": "single-lookup",
        "q": "How many residents live in Dorm A?",
        "subtasks": ["How many residents live in Dorm A?"],
        "expect": "480",
    },
    {
        "id": "two-dorm-sum",
        "q": "What is the total number of residents across Dorm A and Dorm B?",
        "subtasks": ["How many residents live in Dorm A?",
                     "How many residents live in Dorm B?"],
        "expect": "800",
    },
    {
        "id": "floors-lookup",
        "q": "How many floors does Dorm B have?",
        "subtasks": ["How many floors does Dorm B have?"],
        "expect": "8",
    },
    {
        "id": "floors-sum",
        "q": "How many floors are there in total across Dorm A and Dorm B?",
        "subtasks": ["How many floors does Dorm A have?",
                     "How many floors does Dorm B have?"],
        "expect": "20",
    },
    {
        "id": "difference",
        "q": "How many more residents does Dorm A have than Dorm B?",
        "subtasks": ["How many residents live in Dorm A?",
                     "How many residents live in Dorm B?"],
        "expect": "160",
    },
    {
        "id": "average",
        "q": "What is the average number of residents per block across Dorm A and Dorm B?",
        "subtasks": ["How many residents live in Dorm A?",
                     "How many residents live in Dorm B?"],
        "expect": "400",
    },
    {
        "id": "quiet-hours",
        "q": "What are the quiet hours?",
        "subtasks": ["What are the quiet hours?"],
        "expect": "10pm",
    },
    {
        "id": "quiet-hours-end",
        "q": "When do quiet hours end in the morning?",
        "subtasks": ["What are the quiet hours?"],
        "expect": "7am",
    },
    {
        "id": "comparison",
        "q": "Which block has more residents, Dorm A or Dorm B?",
        "subtasks": ["How many residents live in Dorm A?",
                     "How many residents live in Dorm B?"],
        # No `expect`: "Dorm A" could appear in a wrong answer too, so a
        # substring check would pass for the wrong reason. Judge it instead.
        "rubric": "The answer must state that Dorm A has more residents than "
                  "Dorm B. It passes only if it names Dorm A as the larger block.",
    },
    {
        "id": "grounding-unknown-block",
        "q": "How many residents live in Dorm Z?",
        "subtasks": ["How many residents live in Dorm Z?"],
        # THE MOST IMPORTANT CASE IN THE SUITE. There is no Dorm Z in the
        # knowledge base. A substring grader cannot express "must not invent a
        # number" -- this is exactly what a judge is for.
        "rubric": "The knowledge base contains no information about Dorm Z. The "
                  "answer PASSES only if it says the information is not "
                  "available / unknown / not in the documents. It FAILS if it "
                  "states any resident count for Dorm Z, even a hedged one.",
    },
    {
        "id": "grounding-out-of-scope",
        "q": "What is the monthly rent for Dorm A?",
        "subtasks": ["What is the monthly rent for Dorm A?"],
        "rubric": "The knowledge base has no rent information. The answer "
                  "PASSES only if it declines to give a rent figure and says "
                  "it does not know. It FAILS if it quotes any amount.",
    },
    {
        "id": "multi-fact",
        "q": "How many residents and how many floors does Dorm A have?",
        "subtasks": ["How many residents and how many floors does Dorm A have?"],
        "rubric": "The answer must contain BOTH 480 residents AND 12 floors. "
                  "It fails if either number is missing or wrong.",
    },
]


class Verdict(BaseModel):
    passed: bool = Field(description="True only if the answer meets the rubric")
    reason: str = Field(description="One short sentence justifying the verdict")


async def grade(case: dict, answer: str) -> tuple[bool, str]:
    """Grade one answer with the cheapest grader that can do the job."""
    if "expect" in case:
        ok = case["expect"] in answer
        return ok, f"substring {case['expect']!r} {'found' if ok else 'MISSING'}"

    # 5.4 LLM-as-judge. Two things make a judge trustworthy:
    #   * it grades against a RUBRIC, not against a vibe
    #   * it never sees which outcome you were hoping for
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},
        output_format=Verdict,
        system="You are a strict grader. Apply the rubric literally. When in "
               "doubt, fail the answer -- a false pass is far more expensive "
               "than a false fail.",
        messages=[{"role": "user", "content": (
            f"Question asked: {case['q']}\n\n"
            f"Answer given: {answer}\n\n"
            f"Rubric: {case['rubric']}"
        )}],
    )
    v = response.parsed_output
    return v.passed, f"judge: {v.reason}"


async def run_suite(answer_fn, concurrency: int = 4) -> tuple[int, int, list]:
    """Run every case through `answer_fn(question, subtasks) -> str`.

    Returns (passed, total, rows). Cases run CONCURRENTLY (1.2) because an eval
    suite you have to wait five minutes for is an eval suite you stop running.
    """
    sem = asyncio.Semaphore(concurrency)

    async def one(case):
        async with sem:
            try:
                answer = await answer_fn(case["q"], case["subtasks"])
            except Exception as exc:            # a crash is a FAIL, not a stop
                return case["id"], False, f"raised {type(exc).__name__}: {exc}", ""
            ok, why = await grade(case, answer)
            return case["id"], ok, why, answer

    rows = await asyncio.gather(*(one(c) for c in EVALS))
    passed = sum(1 for _, ok, _, _ in rows if ok)
    return passed, len(EVALS), list(rows)


def report(passed: int, total: int, rows: list, verbose: bool = True) -> float:
    """Print a human-readable report and return the pass rate."""
    for case_id, ok, why, answer in rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {case_id:<26} {why}")
        if verbose and not ok and answer:
            print(f"         answer -> {answer[:160]!r}")
    rate = passed / total if total else 0.0
    print(f"\npass rate: {passed}/{total}  ({rate:.0%})")
    return rate
