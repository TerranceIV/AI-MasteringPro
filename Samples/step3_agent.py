"""
Step 3 Capstone -- a REAL tool-calling agent, fully ASYNC.

This is the flagship: Step 2's single call wrapped in a bounded loop, handed
two tools, a mini retrieval store, and short-term memory.
  3.1 the agent loop (call -> tool -> observe -> repeat)
  3.2 tool use / dispatch, with tools running CONCURRENTLY
  3.3 retrieval (keyword search over an in-memory doc store)
  3.4 memory (the growing `messages` list)
  3.6 guardrails: hard step cap + tool errors fed back
  1.2 async throughout -- this is where Step 1's async drill finally pays off

Run:   uv run step3_agent.py "How many residents live across Dorm A and Dorm B?"
Deps:  anthropic          (uv add anthropic)
Env:   ANTHROPIC_API_KEY
"""
import asyncio
import os
import re
import sys

from config import EFFORT, MODEL, get_client

MAX_STEPS = 6                       # 3.6 ALWAYS cap the loop
client = get_client(async_=True)    # 1.2 the ASYNC client


# --- 3.3  a tiny in-memory retrieval store: keyword search over documents ----
# This is deliberately the simplest thing that works. See step3b_retrieval.py
# for why keyword-only search is not enough, and how you MEASURE the difference.
DOCS = {
    "dorm-a": "Dorm A has 12 floors and houses 480 residents.",
    "dorm-b": "Dorm B has 8 floors and houses 320 residents.",
    "rules":  "Quiet hours are 10pm to 7am across all dormitories.",
}

SYSTEM = (
    "You are a dormitory operations assistant. Answer only from the documents "
    "returned by the search tool -- if the documents do not contain the answer, "
    "say so plainly rather than guessing. Use the calculator for any arithmetic "
    "instead of doing it in your head."
)


async def search(query: str) -> str:
    """Return doc chunks whose text overlaps the query words."""
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    hits = [text for text in DOCS.values() if any(w in text.lower() for w in words)]
    return "\n".join(hits) if hits else "no matching documents"


async def calculator(expression: str) -> str:
    """Evaluate arithmetic. Regex-sandboxed -- NEVER eval untrusted input in prod (see 6.4)."""
    if not re.fullmatch(r"[0-9+\-*/(). ]+", expression):
        return "ERROR: only digits and + - * / ( ) are allowed"
    return str(eval(expression))    # demo only; the regex is the (weak) sandbox


# --- 3.2  tool registry + schemas the model sees ----------------------------
TOOLS = {"search": search, "calculator": calculator}
TOOL_SCHEMAS = [
    {
        "name": "search",
        "description": "Search the dormitory knowledge base for facts.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculator",
        "description": "Evaluate a simple arithmetic expression like '480 + 320'.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
]


async def _run_one_tool(block) -> dict:
    """Execute a single tool_use block and shape it into a tool_result."""
    try:
        output = await TOOLS[block.name](**block.input)      # 3.2 dispatch
        is_error = False
    except Exception as exc:                                 # 3.6 feed the error BACK
        output, is_error = f"ERROR: {exc}", True
    print(f"  [tool] {block.name}({block.input}) -> {output}")
    return {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": output,
        "is_error": is_error,   # tells the model this was a failure, not data
    }


# --- 3.1  the agent loop ----------------------------------------------------
async def run(task: str, on_usage=None) -> str:
    """Run the agent loop until the model stops asking for tools.

    `on_usage` is the observability seam (6.1): pass a callback and it is
    invoked with the `usage` object of every model call in the loop. Step 6 uses
    it to log tokens and cost per request. Note that a loop spends tokens on
    EVERY iteration -- one user question is many billable calls, which is the
    thing that surprises people about agent costs.
    """
    messages = [{"role": "user", "content": task}]        # 3.4 short-term memory

    for _ in range(MAX_STEPS):                            # 3.6 bounded
        msg = await client.messages.create(
            model=MODEL,
            max_tokens=4096,          # 2.4 room for thinking AND the answer
            output_config={"effort": EFFORT},
            # 6.2 prompt caching: `system` and `tools` are byte-identical on every
            # turn of the loop, so they are the ideal cache prefix. Caching only
            # engages above ~1024 tokens, and this toy prompt is far below that --
            # so expect cache_read_input_tokens to stay 0 here. Point this at a
            # real system prompt and watch that number jump; that readout is how
            # you verify caching instead of assuming it.
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        if on_usage is not None:                        # 6.1 the tracing hook
            on_usage(msg.usage)
        messages.append({"role": "assistant", "content": msg.content})  # keep the turn

        if msg.stop_reason != "tool_use":                # model gave a final answer
            return "".join(b.text for b in msg.content if b.type == "text")

        # 3.2 / 1.2 the model may ask for SEVERAL tools at once. Run them
        # concurrently -- two 200ms tools take 200ms, not 400ms -- but send every
        # result back in ONE user message. Splitting them across messages
        # silently teaches the model to stop making parallel calls.
        blocks = [b for b in msg.content if b.type == "tool_use"]
        tool_results = await asyncio.gather(*(_run_one_tool(b) for b in blocks))
        messages.append({"role": "user", "content": list(tool_results)})

    return "stopped: hit MAX_STEPS without a final answer"


def run_sync(task: str) -> str:
    """Convenience wrapper for callers that aren't async yet."""
    return asyncio.run(run(task))


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first (see README).")
    task = " ".join(sys.argv[1:]) or (
        "How many residents live across Dorm A and Dorm B combined? Use the tools."
    )
    print("Q:", task)
    print("A:", run_sync(task))
