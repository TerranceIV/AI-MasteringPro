"""
Step 3 Capstone (Gemini twin) -- the same tool-calling agent loop as
../Samples/step3_agent.py, rebuilt on Gemini's function-calling API.

Same shape, same lesson (call -> tool -> observe -> repeat, tools dispatched
concurrently, a hard step cap, errors fed back as data not exceptions). The
wire format is what changes -- see the comments at each divergence, and
README.md for the full diff table.

Not covered here (see README.md "what's not in this folder" for why):
Gemini's prompt/context caching works differently enough from Claude's
`cache_control` breakpoints that porting step3's caching lesson needs its own
redesign, not a rewrite -- so it's left out of this starter set.

Run:   uv run step3_agent.py "How many residents live across Dorm A and Dorm B?"
Deps:  google-genai          (uv add google-genai)
Env:   GEMINI_API_KEY
"""
import asyncio
import re
import sys

from google.genai import types

from config import MAX_OUTPUT_TOKENS_DEFAULT, MODEL, THINKING_BUDGET, get_client

MAX_STEPS = 6                # 3.6 ALWAYS cap the loop
client = get_client()        # one client; async calls go through client.aio


# --- 3.3  the same tiny in-memory retrieval store as the Claude version -----
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
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    hits = [text for text in DOCS.values() if any(w in text.lower() for w in words)]
    return "\n".join(hits) if hits else "no matching documents"


async def calculator(expression: str) -> str:
    """Evaluate arithmetic. Regex-sandboxed -- NEVER eval untrusted input in prod
    (see 6.4 in the Anthropic folder for the production version of this warning)."""
    if not re.fullmatch(r"[0-9+\-*/(). ]+", expression):
        return "ERROR: only digits and + - * / ( ) are allowed"
    return str(eval(expression))    # demo only; the regex is the (weak) sandbox


TOOLS = {"search": search, "calculator": calculator}

# --- 3.2  tool schemas the model sees ---------------------------------------
# These are SCHEMA-ONLY declarations -- no python callable attached. That
# matters: hand Gemini a real python function instead, and its SDK will run
# the ENTIRE tool loop for you automatically, calling your function directly
# and never showing you a function_call part at all. That's a genuinely
# useful shortcut for production code, but it would hide the exact mechanics
# this sample exists to teach -- so we declare schemas only, and also disable
# automatic dispatch explicitly below, to keep the loop visible and
# comparable to the Claude version.
TOOL_DECLARATIONS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="search",
        description="Search the dormitory knowledge base for facts.",
        parameters_json_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    types.FunctionDeclaration(
        name="calculator",
        description="Evaluate a simple arithmetic expression like '480 + 320'.",
        parameters_json_schema={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    ),
])

GENERATE_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM,
    tools=[TOOL_DECLARATIONS],
    max_output_tokens=MAX_OUTPUT_TOKENS_DEFAULT,          # 2.4-equivalent: room for thinking AND the answer
    thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)


async def _run_one_tool(call) -> types.Part:
    """Execute one function_call and shape the result into a function_response part."""
    args = dict(call.args)
    try:
        output = await TOOLS[call.name](**args)          # 3.2 dispatch
    except Exception as exc:                              # 3.6 feed the error BACK, not raise
        output = f"ERROR: {exc}"
    print(f"  [tool] {call.name}({args}) -> {output}")
    return types.Part.from_function_response(name=call.name, response={"result": output})


# --- 3.1  the agent loop -----------------------------------------------------
async def run(task: str, on_usage=None) -> str:
    """Run the agent loop until the model stops asking for tools.

    `on_usage` mirrors ../Samples/step3_agent.py's observability seam (6.1):
    pass a callback and it's invoked with the `usage_metadata` of every model
    call in the loop -- note the different attribute name from Claude's `usage`.
    """
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=task)])]  # 3.4 memory

    for _ in range(MAX_STEPS):                            # 3.6 bounded
        response = await client.aio.models.generate_content(
            model=MODEL, contents=contents, config=GENERATE_CONFIG,
        )
        if on_usage is not None:                          # 6.1-equivalent tracing hook
            on_usage(response.usage_metadata)

        candidate_content = response.candidates[0].content
        contents.append(candidate_content)                # keep the model's turn (3.4)

        calls = [p.function_call for p in candidate_content.parts if p.function_call]
        if not calls:                                     # model gave a final answer
            return "".join(p.text for p in candidate_content.parts if p.text)

        # 3.2 the model may ask for SEVERAL tools at once -- run them
        # concurrently, same trap as Claude: send every result back in ONE
        # turn, not split across turns, or you silently teach the model to
        # stop asking for tools in parallel.
        tool_parts = await asyncio.gather(*(_run_one_tool(c) for c in calls))
        contents.append(types.Content(role="user", parts=list(tool_parts)))

    return "stopped: hit MAX_STEPS without a final answer"


def run_sync(task: str) -> str:
    """Convenience wrapper for callers that aren't async yet."""
    return asyncio.run(run(task))


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or (
        "How many residents live across Dorm A and Dorm B combined? Use the tools."
    )
    print("Q:", task)
    print("A:", run_sync(task))
