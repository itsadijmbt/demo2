"""Vanilla MCP client -- HTTP version.

Talks to the ALREADY-RUNNING upstream Snowflake-Labs server over streamable-HTTP,
so the requests show up on the SERVER side (handshake + tool calls on :9000).

Difference from normal-client.py: that one spawns its OWN stdio server; THIS one
connects to the live HTTP server you started separately.

Both destructive calls are ACCEPTED -- vanilla = no MAPL, no identity, no audit.
Contrast with macaw-client.py (SecureMCP: deny + attestation).

Run:
    # Terminal 1 (in snowflake-mcp-upstream/):
    python run-mock-http.py
    # Terminal 2 (here):
    python normal-client-http.py
"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import _pretty as P

URL = "http://127.0.0.1:9000/mcp"


def render_content(result):
    if result is None:
        return "(no result)"
    parts = [getattr(b, "text", repr(b)) for b in (getattr(result, "content", []) or [])]
    return "\n".join(parts) if parts else repr(result)


async def run_test(session, idx, title, subtitle, tool, args):
    P.test_box(idx, title, subtitle, accent=P.YELLOW)
    P.call_summary(tool, args)
    try:
        r = await session.call_tool(tool, args)
        body = render_content(r)
        if getattr(r, "isError", False):
            P.denied("ERROR  (isError=True)")
            P.result_body(body)
            P.commentary(["Tool itself errored -- this was NOT a policy refusal."], kind="info")
        else:
            P.accepted("ACCEPTED  (isError=False)")
            P.result_body(body)
            P.commentary(
                ["Server accepted the destructive call without question.",
                 "No identity attached. No MAPL deny. No attestation prompt.",
                 "No signed audit envelope was produced."],
                kind="warn",
            )
    except Exception as e:
        P.denied(f"CALL RAISED  ({type(e).__name__})")
        P.result_body(str(e))
        P.commentary(["Transport/SDK error -- is the :9000 server running?"], kind="info")


async def main():
    P.banner("VANILLA MCP CLIENT  (HTTP)",
             subtitle=f"-> {URL}   .   connects to the LIVE server, no MACAW",
             accent=P.YELLOW)
    try:
        async with streamablehttp_client(URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                P.section("TOOLS ADVERTISED", accent=P.YELLOW)
                tools = (await session.list_tools()).tools
                P.tool_list(tools, columns=3, accent=P.YELLOW)

                P.section("SNOWFLAKE-MCP TESTS  .  vanilla side", accent=P.YELLOW)
                await run_test(
                    session, 1,
                    "drop_object(object_type=table, name=demo)",
                    "expected: vanilla server accepts (no policy layer)",
                    "drop_object",
                    {"object_type": "table", "target_object": {"name": "demo"}})
                await run_test(
                    session, 2,
                    'run_snowflake_query  .  "DROP TABLE customers"',
                    "expected: vanilla server runs it (no policy, no attestation)",
                    "run_snowflake_query",
                    {"statement": "DROP TABLE customers"})
    except Exception as e:
        print(f"\n  Could not connect to {URL}: {e}", file=sys.stderr)
        print("  Start the server first:  (in snowflake-mcp-upstream/)  python run-mock-http.py",
              file=sys.stderr)
        return 1

    P.footer("vanilla HTTP demo complete  .  both destructive calls accepted", accent=P.YELLOW)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
