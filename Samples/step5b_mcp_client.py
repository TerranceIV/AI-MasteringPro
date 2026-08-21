"""
Step 5b -- speaking MCP.  (module 5.3)

THE POSITION THIS TRACK TAKES ON MCP: consuming servers is a genuinely useful
hour of your life; authoring servers is a "when you need it" skill. This sample
does the useful half -- it connects to a server, discovers whatever tools that
server offers, and hands them to the model without knowing in advance what they
are. That last part is the whole value of a standard: your agent gains
capabilities it was never coded against.

  5.3 connect over stdio, `list_tools()` to DISCOVER, convert, hand to the model
  4.3 this uses the SDK's built-in tool_runner -- the agent loop you hand-wrote
      in Step 3, supplied for you. Compare it against step3_agent.py.

Run:   uv run --with "anthropic[mcp],mcp" step5b_mcp_client.py
       uv run --with "anthropic[mcp],mcp" step5b_mcp_client.py "list every block"
Deps:  anthropic[mcp]  mcp        (needs Python 3.10+)
Env:   ANTHROPIC_API_KEY
"""
import asyncio
import os
import sys

from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from config import EFFORT, MODEL, get_client

client = get_client(async_=True)

# The server is launched as a SUBPROCESS and spoken to over stdin/stdout. Point
# this at any MCP server -- a published one (`uvx mcp-server-fetch`), a vendor's,
# or your own. Nothing below this line changes when the server does.
SERVER = StdioServerParameters(
    command=sys.executable,           # the same Python that's running us
    args=["mcp_dorm_server.py"],
)


async def main(question: str) -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 5.3 DISCOVERY -- we did not hardcode these. Print them to see
            # what a standard buys you: capability without integration work.
            listed = await session.list_tools()
            print("tools discovered from the server:")
            for tool in listed.tools:
                print(f"  - {tool.name}: {tool.description or ''}".rstrip())
            print()

            # Convert each MCP tool into something the Messages API understands.
            tools = [async_mcp_tool(t, session) for t in listed.tools]

            # 4.3 the SDK's tool_runner IS the Step 3 loop: call -> dispatch ->
            # feed results back -> repeat until the model stops asking. You
            # already know exactly what it is doing, which is the only reason
            # it is safe to let it do it for you.
            runner = client.beta.messages.tool_runner(
                model=MODEL,
                max_tokens=4096,
                output_config={"effort": EFFORT},
                tools=tools,
                messages=[{"role": "user", "content": question}],
            )

            final = None
            async for message in runner:
                final = message
                for block in message.content:
                    if block.type == "tool_use":
                        print(f"  [mcp] {block.name}({block.input})")

            if final:
                print("\nA:", "".join(b.text for b in final.content if b.type == "text"))


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first (see README).")
    q = " ".join(sys.argv[1:]) or "How many residents are in Dorm A and Dorm B in total?"
    print("Q:", q, "\n")
    asyncio.run(main(q))
