"""
Step 4 Capstone -- the SAME agent as Step 3, rebuilt on a framework.

Point of the exercise: see what the framework HIDES. In Step 3 you wrote the
loop, the dispatch, the message plumbing, and the stop condition by hand.
`create_react_agent` gives you all of that in one call -- less code, but also
less visibility when it misbehaves. Keep BOTH files and compare.

Run:   uv run step4_langgraph_agent.py
Deps:  langgraph langchain-anthropic     (uv add langgraph langchain-anthropic)
Env:   ANTHROPIC_API_KEY
"""
import os
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from config import MODEL  # model id centralized in config.py


@tool
def search(query: str) -> str:
    """Search the dormitory knowledge base for facts."""
    docs = [
        "Dorm A has 12 floors and houses 480 residents.",
        "Dorm B has 8 floors and houses 320 residents.",
        "Quiet hours are 10pm to 7am across all dormitories.",
    ]
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    hits = [d for d in docs if any(w in d.lower() for w in words)]
    return "\n".join(hits) if hits else "no matching documents"


@tool
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression like '480 + 320'."""
    if not re.fullmatch(r"[0-9+\-*/(). ]+", expression):
        return "ERROR: invalid characters"
    return str(eval(expression))  # demo only


# The ENTIRE Step-3 loop + guardrails + history management, in one line:
# max_tokens is 4096, not 1024: current models think adaptively by default and
# max_tokens caps thinking + answer TOGETHER, so a tight budget truncates the
# answer. Note you had to know that about the MODEL -- the framework won't tell
# you, and this is exactly the class of bug that abstraction hides.
agent = create_react_agent(
    ChatAnthropic(model=MODEL, max_tokens=4096),
    [search, calculator],
)


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first (see README).")
    result = agent.invoke(
        {"messages": [("user", "How many residents live across Dorm A and Dorm B combined?")]}
    )
    print(result["messages"][-1].content)

    # WHAT THE FRAMEWORK HID (vs step3_agent.py):
    #   - the while-loop and MAX_STEPS cap
    #   - tool dispatch + tool_result plumbing
    #   - stop_reason handling
    #   - message-history bookkeeping
    # Tradeoff: ~40 fewer lines, but you debug through the framework's abstraction.
