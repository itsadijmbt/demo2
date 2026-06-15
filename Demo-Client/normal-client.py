"""Vanilla MCP client for the snowflake-mcp DEMO.


Layout expected on disk:
    ./snowflake-mcp-upstream/                            (git clone)
    ./snowflake-mcp-upstream/services/configuration.yaml (ships in clone)
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


HERE = Path(__file__).resolve().parent
UPSTREAM = HERE / "snowflake-mcp-upstream"

INLINE_SERVER = r"""
import sys
from unittest.mock import MagicMock

import snowflake.connector
snowflake.connector.connect = lambda **kw: MagicMock(name="MockSnowflakeConnection")

import snowflake.core
snowflake.core.Root = lambda conn: MagicMock(name="MockSnowflakeRoot")

from mcp_server_snowflake.server import main
main()
"""


SEP = "=" * 64


def render(result) -> str:
    if result is None:
        return "(no result)"
    parts = [
        getattr(b, "text", repr(b))
        for b in (getattr(result, "content", []) or [])
    ]
    return "\n".join(parts) if parts else repr(result)


async def run_test(session, label, tool, args):
    print(f"\n[{label}] {tool} {args}")
    try:
        r = await session.call_tool(tool, args)
        is_err = getattr(r, "isError", False)
        print(f"  isError: {is_err}")
        for line in render(r).splitlines():
            print(f"  {line}")
        if not is_err:
            print("  *** Server accepted the request. No MAPL deny.")
            print("  *** No attestation prompt. No signed audit envelope.")
    except Exception as e:
        print(f"  [Call raised: {type(e).__name__}: {e}]")
        print("  Note: this is transport/SDK, not policy refusal.")


async def main() -> int:
    if not UPSTREAM.is_dir():
        print(f"Expected upstream clone at: {UPSTREAM}", file=sys.stderr)
        print("Run: git clone https://github.com/Snowflake-Labs/mcp.git "
              "snowflake-mcp-upstream", file=sys.stderr)
        return 2

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c", INLINE_SERVER,
            "--service-config-file", "services/configuration.yaml",
        ],
        cwd=str(UPSTREAM),
    )

    print(SEP)
    print("VANILLA MCP CLIENT  ->  upstream Snowflake-Labs fastmcp server (mocked)")
    print(SEP)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("\n" + SEP)
            print("TOOLS ADVERTISED")
            print(SEP)
            tools = (await session.list_tools()).tools
            for t in tools:
                print(f"  - {t.name}")

            print("\n" + SEP)
            print("SNOWFLAKE-MCP RED-TEAM POLICY TESTS  (vanilla side)")
            print(SEP)

        
            await run_test(
                session,
                "TEST 1 drop_object(table=demo)  "
                "(no MAPL -- expect server to attempt it)",
                "drop_object",
                {"object_type": "table",
                 "target_object": {"name": "demo"}},
            )

            await run_test(
                session,
                "TEST 2 run_snowflake_query w/ 'DROP' literal  "
                "(no attestation primitive -- expect server to run it)",
                "run_snowflake_query",
                {"statement": "SELECT 'pretend DROP' AS note"},
            )

            print("\n" + SEP)
            print("CONTRAST WITH macaw-client.py")
            print(SEP)
            print(
                "  TEST 1: vanilla server attempted drop_object; SecureMCP\n"
                "          DENIED at the Local Agent (denied_resources).\n"
                "  TEST 2: vanilla server ran the query; SecureMCP BLOCKED\n"
                "          via the allow_destroy attestation gate (admin\n"
                "          approval required).\n"
                "  No signed audit envelope on either call here. No identity\n"
                "  attached. Whoever ran this client is invisible to the\n"
                "  server's record-keeping."
            )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
