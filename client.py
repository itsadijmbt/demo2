"""
Requester client for snowflake-mcp (red-team policy testing).

Same pattern as the postgres/mysql clients and the existing
client-test-macaw.py: macaw_adapters.mcp.Client + bare tool names in
call_tool() (the mesh canonicalizes bare `X` -> resource `tool:X`).

Tests focus on the DETERMINISTIC red-team controls, which are evaluated
by MAPL on the mesh BEFORE the tool body -> they work even under
run-server-mock.py (no real Snowflake needed):

  - drop_object              -> DENY (denied_resources)            [destruction blocked]
  - create_object(user)      -> DENY (allowed_values object_type)  [privilege-escalation blocked]
  - create_object(table)     -> ALLOW at policy (mock returns mock)
  - list_objects             -> ALLOW (read)
  - run_snowflake_query SELECT 1 -> ALLOW (no attestation trigger)
  - run_snowflake_query w/ 'DROP' literal -> BLOCKS on allow_destroy
        attestation (no approver here -> it will wait then time out;
        run last). This demonstrates the checkpoint fires.

Usage:
    python3 client.py "snowflake" snowflake-requester
"""

import asyncio
import sys

from macaw_adapters.mcp import Client


def get_server(name, client):
    agents = client.macaw_client.list_agents(agent_type="app")
    server = [
        a for a in agents
        if name in a.get("agent_id", "")
        and "app:securemcp-" in a.get("agent_id", "")
        and "/tool." not in a.get("agent_id", "")
        and "securemcp-client-" not in a.get("agent_id", "")
    ]
    if not server:
        print(f"No SecureMCP server agent matching '{name}'.")
        for a in agents:
            print(f"  - {a.get('agent_id', '<no id>')}")
        return None
    return server[0].get("agent_id")


async def main():
    if len(sys.argv) < 3:
        print('Usage: python3 client.py "<server filter>" <client name>')
        sys.exit(1)

    name = sys.argv[1]
    client_name = sys.argv[2]

    client = Client(client_name)
    server_id = get_server(name, client)
    if not server_id:
        return
    client.set_default_server(server_id)

    tools = await client.list_tools(server_name=name)
    seen = set()
    for t in tools:
        if t["name"] not in seen:
            seen.add(t["name"])
            print(f"  - {t['name']}")

    print("\n" + "=" * 60)
    print("SNOWFLAKE-MCP RED-TEAM POLICY TESTS")
    print("=" * 60)

    async def run(label, tool, args):
        print(f"\n[{label}] {tool} {args}")
        try:
            result = await client.call_tool(tool, args)
            output = result.get("result", result) if isinstance(result, dict) else getattr(result, "text", result)
            print("Result:\n", output)
        except Exception as e:
            print(f"[Tool failed: {e}]")



    # TEST 1 -- read, allowed
    await run("TEST 1 list_objects(table) (expect ALLOW)", "list_objects", {"object_type": "table"})

    # TEST 2 -- destruction blocked at the resource level
    await run("TEST 2 drop_object(table) (expect DENY via denied_resources)",
              "drop_object", {"object_type": "table", "target_object": {"name": "demo"}})

    # TEST 3 -- privilege escalation blocked: object_type=user not in allowed_values
    await run("TEST 3 create_object(USER) (expect DENY via allowed_values object_type)",
              "create_object", {"object_type": "user",
                                 "target_object": {"name": "eviladmin", "password": "Pwn3d!"}})

    # TEST 4 -- allowed object type passes the policy (mock returns a mock result)
    await run("TEST 4 create_object(table) (expect ALLOW at policy)",
              "create_object", {"object_type": "table",
                                 "target_object": {"name": "demo", "database_name": "db",
                                                   "schema_name": "sch",
                                                   "columns": [{"name": "id", "datatype": "NUMBER"}]}})

    # TEST 5 -- benign SQL, no attestation trigger
    await run("TEST 5 run_snowflake_query SELECT 1 (expect ALLOW)",
              "run_snowflake_query", {"statement": "SELECT 1 AS x"})

    # --- attestation checkpoint (BLOCKS; run last; no approver -> will time out) ---

    # TEST 6 -- 'DROP' in a string literal -> harmless SELECT that still trips
    #           allow_destroy (params.statement MATCHES '*DROP*'). Blocks up to
    #           the attestation timeout (300s) waiting for a role:manager approver.
    await run("TEST 6 run_snowflake_query w/ 'DROP' literal (expect BLOCK -> allow_destroy)",
              "run_snowflake_query", {"statement": "SELECT 'pretend DROP' AS note"})


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
