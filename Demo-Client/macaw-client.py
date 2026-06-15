"""MACAW client for the snowflake-mcp DEMO.

Mirrors normal-client.py's two tests but goes through the MACAW mesh
into the SecureMCP-ported snowflake server. Every call is signed; MAPL
evaluates at the Local Agent before the handler runs.

  TEST 1  drop_object              → expected DENY (denied_resources)
  TEST 2  run_snowflake_query DROP → expected WAIT → DENY (allow_destroy
                                     attestation, role:manager required)

Usage:
    python3 macaw-client.py "snowflake" macaw-snowflake-agent
"""

import asyncio
import sys

from macaw_adapters.mcp import Client

import _pretty as P


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
        print(f"{P.RED}No SecureMCP server agent matching '{name}'.{P.RESET}",
              file=sys.stderr)
        for a in agents:
            print(f"  - {a.get('agent_id', '<no id>')}", file=sys.stderr)
        return None
    return server[0].get("agent_id")


def _short_text(result):
    if isinstance(result, dict):
        inner = result.get("result", result)
        return str(inner)
    if hasattr(result, "text"):
        return result.text
    return str(result)


async def run_test(client, idx, title, subtitle, tool, args, expectation):
    P.test_box(idx, title, subtitle, accent=P.GREEN)
    P.call_summary(tool, args)
    if expectation:
        P.note(expectation, kind="info")
    try:
        result = await client.call_tool(tool, args)
        body = _short_text(result)
        # MACAW SDK raises on policy deny; reaching here means the call
        # actually returned (likely an allow path).
        P.accepted("RETURNED  (no policy deny)")
        P.result_body(body)
        P.commentary(
            ["The call reached and returned from the server handler.",
             "If you expected a deny here, check the policy file."],
            kind="warn",
        )
    except Exception as e:
        # In MACAW, exceptions on call_tool are almost always policy
        # outcomes: denied_resources hit, attestation expired/denied,
        # parameter constraint failed, etc.
        msg = str(e)
        if "Missing or invalid attestation" in msg:
            P.denied("ATTESTATION DENIED")
            P.result_body(msg)
            P.commentary(
                ["MAPL allow_destroy predicate fired on the statement.",
                 "Attestation request was created, sent for manager approval.",
                 "Admin denied (or timeout expired). Policy decision: Deny.",
                 "Audit chain: created → denied → policy: Deny."],
                kind="good",
            )
        elif "denied pattern" in msg or "Access denied" in msg or "Denied" in msg:
            P.denied("POLICY DENY  (denied_resources)")
            P.result_body(msg)
            P.commentary(
                ["Local Agent matched the tool name against denied_resources.",
                 "Handler was never invoked. Signed audit entry produced.",
                 "Activity graph: source_agent → red-X → target server."],
                kind="good",
            )
        else:
            P.denied(f"CALL RAISED  ({type(e).__name__})")
            P.result_body(msg)
            P.commentary(
                ["Unexpected error -- not the documented policy path.",
                 "Inspect MACAW Local Agent logs."],
                kind="warn",
            )


async def main():
    if len(sys.argv) < 3:
        print('Usage: python3 macaw-client.py "<server filter>" <client name>',
              file=sys.stderr)
        sys.exit(1)

    name = sys.argv[1]
    client_name = sys.argv[2]

    client = Client(client_name)
    server_id = get_server(name, client)
    if not server_id:
        return 2
    client.set_default_server(server_id)

    P.banner(
        "MACAW CLIENT  →  SecureMCP snowflake server",
        subtitle=f"target: {server_id}",
        accent=P.GREEN,
    )

    P.section("TOOLS ADVERTISED  (via MACAW mesh)", accent=P.GREEN)
    tools = await client.list_tools(server_name=name)
    seen = []
    for t in tools:
        if t["name"] not in seen:
            seen.append(t["name"])
    P.tool_list(seen, columns=3, accent=P.GREEN)

    P.section("SNOWFLAKE-MCP RED-TEAM POLICY TESTS  ·  MACAW side",
              accent=P.GREEN)

    # TEST 1 -- denied_resources hard deny. drop_object takes an OBJECT
    # NAME (not SQL). The deny happens regardless of the name because the
    # TOOL itself is listed in denied_resources -- the Local Agent refuses
    # before the handler (and the upstream's name validation) ever runs.
    # So here you can type anything; on MACAW it's denied either way.
    target = P.prompt_box(
        "TEST 1 — type a TABLE NAME to drop (just the name, e.g. customers):",
        default="customers",
        hint="drop_object is in denied_resources -- ANY name is denied at the Local Agent",
        accent=P.GREEN,
    )
    await run_test(
        client,
        idx=1,
        title=f"drop_object(object_type=table, name={target})",
        subtitle="expected: DENY at Local Agent before handler runs",
        tool="drop_object",
        args={"object_type": "table", "target_object": {"name": target}},
        expectation='hits denied_resources: ["tool:drop_object"]',
    )

    # TEST 2 -- attestation gate. You type the SQL live. A destructive
    # statement triggers the allow_destroy predicate in the MAPL policy:
    #   allow_destroy::{ params.statement MATCHES '*DROP*' OR ... }
    #   approval_criteria: "role:manager"
    # MAPL pauses, creates an out-of-band approval task, blocks up to
    # 300s. Admin denies/approves (or it times out). Whatever you type is
    # evaluated by the same policy -- a plain SELECT passes, a DROP /
    # DELETE / TRUNCATE / ALTER hits the gate.
    statement = P.prompt_box(
        "TEST 2 — type a SQL statement to send through MACAW:",
        default="DROP TABLE customers",
        hint="DROP / DELETE / TRUNCATE / ALTER trigger the allow_destroy gate",
        accent=P.GREEN,
    )
    await run_test(
        client,
        idx=2,
        title=f'run_snowflake_query  ·  "{statement}"',
        subtitle="expected: destructive → WAIT for manager attestation → DENY",
        tool="run_snowflake_query",
        args={"statement": statement},
        expectation="MAPL evaluates this statement; destructive verbs pause "
                    "up to 300s for role:manager approval",
    )

    P.footer("MACAW demo complete  ·  see Console activity graph + audit trail",
             accent=P.GREEN)
    return 0


# =========================================================================
# OPTIONAL: stdio MCP gateway for gemini-cli / claude-cli.
# Uncomment the block below to expose this MACAW client as a stdio MCP
# server. Each tools/call from gemini-cli is forwarded via
# client.call_tool(...) -- MAPL evaluates with this Client's identity.
# (Comment out the run_test() calls above before enabling, since stdout
# must be clean JSON-RPC for the gemini handshake.)
# =========================================================================
#
# async def gateway_main():
#     import json
#     from mcp.server import Server
#     from mcp.server.stdio import stdio_server
#     import mcp.types as types
#
#     if len(sys.argv) < 3:
#         sys.exit(1)
#     name, client_name = sys.argv[1], sys.argv[2]
#     client = Client(client_name)
#     server_id = get_server(name, client)
#     if not server_id:
#         sys.exit(2)
#     client.set_default_server(server_id)
#
#     raw_tools = await client.list_tools(server_name=name)
#     tool_objs = [
#         types.Tool(
#             name=t["name"],
#             description=t.get("description", ""),
#             inputSchema=(
#                 t.get("inputSchema")
#                 or t.get("schema")
#                 or {"type": "object"}
#             ),
#         )
#         for t in raw_tools
#     ]
#
#     srv = Server("snowflake-macaw-gateway")
#
#     @srv.list_tools()
#     async def _list():
#         return tool_objs
#
#     @srv.call_tool()
#     async def _call(tool_name, args):
#         r = await client.call_tool(tool_name, args or {})
#         payload = r.get("result", r) if isinstance(r, dict) else r
#         return [types.TextContent(type="text", text=json.dumps(payload, default=str))]
#
#     async with stdio_server() as (rd, wr):
#         await srv.run(rd, wr, srv.create_initialization_options())


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nExiting...")
