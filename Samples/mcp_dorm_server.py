"""
A tiny MCP server -- the thing you'll usually CONSUME rather than write. (5.3)

MCP (Model Context Protocol) is an open standard for exposing tools, resources
and prompts to any AI client. The point of the standard is reuse: write this
server once and Claude Desktop, Claude Code, your own agent, and someone else's
agent can all use it without you writing an integration for each.

This file exists so step5b_mcp_client.py has a real server to talk to, and so
you can see there is no magic in one. In practice your ratio will be something
like 20 servers consumed for every 1 written.

MCP is a SEPARATE project from the Anthropic SDK, with its own docs:
    https://modelcontextprotocol.io/

You never run this file directly -- the client launches it as a subprocess over
stdio. To sanity-check it standalone:  uv run --with mcp mcp_dorm_server.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("dorm-facts")

DOCS = {
    "dorm-a": "Dorm A has 12 floors and houses 480 residents.",
    "dorm-b": "Dorm B has 8 floors and houses 320 residents.",
    "rules":  "Quiet hours are 10pm to 7am across all dormitories.",
}


@mcp.tool()
def search_dorm_facts(query: str) -> str:
    """Search the dormitory knowledge base for facts about blocks and rules.

    Args:
        query: Words to look for, e.g. "Dorm A residents" or "quiet hours".
    """
    # Note what the decorator is doing for you: the function signature becomes
    # the tool's JSON schema and this docstring becomes its description --
    # exactly the Pydantic-to-schema idea from module 1.3, standardised.
    words = [w for w in query.lower().split() if len(w) > 2]
    hits = [text for text in DOCS.values() if any(w in text.lower() for w in words)]
    return "\n".join(hits) if hits else "no matching documents"


@mcp.tool()
def list_blocks() -> list[str]:
    """List the identifiers of every dormitory block on record."""
    return [key for key in DOCS if key.startswith("dorm-")]


if __name__ == "__main__":
    mcp.run()          # stdio transport -- the client spawns us and talks over pipes
