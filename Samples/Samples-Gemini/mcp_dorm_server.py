"""
A tiny MCP server -- byte-identical to ../Samples/mcp_dorm_server.py, on
purpose. (module 5.3)

MCP servers don't know or care which model vendor is consuming them -- that
IS the standard's value proposition. This file needing zero changes to work
with either step5b_mcp_client.py (this folder, Gemini) or
../Samples/step5b_mcp_client.py (Claude) is the demonstration, not an
afterthought.

You never run this file directly -- the client launches it as a subprocess
over stdio. To sanity-check it standalone:  uv run --with mcp mcp_dorm_server.py
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
    words = [w for w in query.lower().split() if len(w) > 2]
    hits = [text for text in DOCS.values() if any(w in text.lower() for w in words)]
    return "\n".join(hits) if hits else "no matching documents"


@mcp.tool()
def list_blocks() -> list[str]:
    """List the identifiers of every dormitory block on record."""
    return [key for key in DOCS if key.startswith("dorm-")]


if __name__ == "__main__":
    mcp.run()          # stdio transport -- the client spawns us and talks over pipes
