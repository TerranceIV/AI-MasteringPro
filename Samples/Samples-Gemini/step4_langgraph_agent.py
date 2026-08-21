"""
Step 4 Capstone (Gemini twin) -- the SAME agent as Step 3, rebuilt on a
framework, this time pointed at Gemini instead of Claude.

This is the ONE file in this whole track where swapping vendors is nearly
free, and that's worth sitting with: LangGraph's entire pitch is hiding the
vendor behind a common chat-model interface, and `@tool`-decorated python
functions don't know or care who calls them. Diff this file against
../Samples/step4_langgraph_agent.py -- the change is the import, the model
constructor, and the API key's env var name. Compare that with step3_agent.py
in this folder, which needed a full rewrite because Step 3 has no abstraction
layer between your code and the vendor's raw API. THAT gap is the actual,
concrete value of a framework like LangGraph -- not "less code," portability.

Run:   uv run step4_langgraph_agent.py
Deps:  langgraph langchain-google-genai     (uv add langgraph langchain-google-genai)
Env:   GEMINI_API_KEY
"""
import os
import re

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
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


# GOTCHA worth knowing before you hit it: langchain-google-genai reads
# GOOGLE_API_KEY by default, NOT GEMINI_API_KEY -- a genuinely common source
# of "why won't it pick up my key" confusion, since every other file in this
# folder uses GEMINI_API_KEY. Passing google_api_key= explicitly here keeps
# ONE env var name for the whole folder instead of asking you to set two.
#
# The ENTIRE Step-3 loop + guardrails + history management, in one call:
# max_output_tokens is 4096, not 1024, for the same reason as the Claude
# version -- current Gemini models think adaptively by default too, and that
# budget caps thinking + answer TOGETHER. You had to know that about the
# MODEL, not the framework -- the framework won't tell you either way.
agent = create_react_agent(
    ChatGoogleGenerativeAI(
        model=MODEL,
        google_api_key=os.environ.get("GEMINI_API_KEY", ""),
        max_output_tokens=4096,
    ),
    [search, calculator],
)


if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Set GEMINI_API_KEY first (see README.md).")
    result = agent.invoke(
        {"messages": [("user", "How many residents live across Dorm A and Dorm B combined?")]}
    )
    print(result["messages"][-1].content)

    # WHAT THE FRAMEWORK HID (vs step3_agent.py in this folder):
    #   - the while-loop and MAX_STEPS cap
    #   - tool dispatch + function_response plumbing
    #   - stop-condition handling
    #   - message-history bookkeeping
    # Tradeoff: ~40 fewer lines, but you debug through the framework's
    # abstraction -- and now through a SECOND abstraction layer, the one that
    # hides which vendor you're even talking to.
