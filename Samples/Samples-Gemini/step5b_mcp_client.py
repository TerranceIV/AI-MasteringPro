"""
Step 5b -- speaking MCP, on Gemini instead of Claude. (module 5.3)

Same idea as ../Samples/step5b_mcp_client.py: connect to an MCP server,
DISCOVER whatever tools it offers, hand them to the model without knowing in
advance what they are. mcp_dorm_server.py in this folder is intentionally
byte-identical to the Claude version's -- MCP is a vendor-neutral standard,
so the server doesn't change when the client's vendor does.

  5.3 connect over stdio; hand the raw MCP ClientSession to Gemini and the
      SDK does discovery + schema translation + the call/response bridge
  This IS Gemini's own built-in agent loop (automatic function calling
      against an MCP session) -- the same convenience Anthropic's
      `tool_runner` gives the Claude version. Compare both against
      step3_agent.py, which you drove by hand.

Run:   uv run --with "google-genai,mcp" step5b_mcp_client.py
       uv run --with "google-genai,mcp" step5b_mcp_client.py "list every block"
Deps:  google-genai  mcp        (needs Python 3.10+)
Env:   GEMINI_API_KEY
"""
import asyncio
import sys

from google.genai import types
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from config import MAX_OUTPUT_TOKENS_DEFAULT, MODEL, THINKING_BUDGET, get_client

client = get_client()

SERVER = StdioServerParameters(
    command=sys.executable,           # the same Python that's running us
    args=["mcp_dorm_server.py"],
)


async def main(question: str) -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 5.3 DISCOVERY -- print what the server offers before using it,
            # to see what the standard buys you: capability with zero
            # integration work written against this specific server.
            listed = await session.list_tools()
            print("tools discovered from the server:")
            for tool in listed.tools:
                print(f"  - {tool.name}: {tool.description or ''}".rstrip())
            print()

            # Hand the RAW session to Gemini. As of the current google-genai
            # SDK (documented as an experimental feature), passing a
            # ClientSession directly in `tools` makes the SDK do discovery,
            # schema translation, and the call/response bridge itself, AND
            # run the loop for you via automatic function calling -- Gemini's
            # version of the exact convenience Anthropic's tool_runner gives
            # the Claude sample.
            #
            # Tradeoff worth noticing: because dispatch is automatic and
            # hidden, you do NOT get the per-call "[mcp] tool_name(args)"
            # print lines that the Claude version shows as it iterates the
            # runner. If you want that visibility back, the fallback is to
            # convert each discovered tool into a FunctionDeclaration by
            # hand, disable automatic_function_calling, and drive the loop
            # yourself -- exactly like step3_agent.py, but calling
            # `await session.call_tool(name, args)` instead of a local
            # python function.
            response = await client.aio.models.generate_content(
                model=MODEL,
                contents=question,
                config=types.GenerateContentConfig(
                    tools=[session],
                    max_output_tokens=MAX_OUTPUT_TOKENS_DEFAULT,
                    thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
                ),
            )
            print("A:", response.text)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How many residents are in Dorm A and Dorm B in total?"
    print("Q:", q, "\n")
    asyncio.run(main(q))
