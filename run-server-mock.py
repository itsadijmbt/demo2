"""
Run snowflake-mcp under SecureMCP WITHOUT real Snowflake credentials.

TEST-ONLY launcher. Do NOT use in production -- production needs real
Snowflake credentials and the regular entry point.

    python3 run-server-mock.py --service-config-file services/configuration.yaml


=====================================================================
WHAT THIS DOES, IN PLAIN ENGLISH (first-principles)
=====================================================================

The snowflake server needs a live Snowflake connection at startup. We
don't have a Snowflake account on this machine. So we hand the server a
FAKE connection object that *looks* like the real one but does nothing.

The fake has to satisfy two completely separate jobs, and getting EITHER
one wrong means a different kind of failure:

  Job 1  -- "Don't crash at BOOT."
           The server constructor (SnowflakeService.__init__) eagerly
           calls connect(), then runs a warm-up query:

               with connection.cursor() as cur:
                   cur.execute("SELECT ...").fetchone()
                                ^^^^^^^^^^^^ ^^^^^^^^^^
               (server.py:251 -- note execute() is CHAINED into fetchone())

           So the fake cursor's execute() must return an object that
           HAS a .fetchone(). If execute() returns None, then
           None.fetchone() -> AttributeError -> boot dies. This is the
           subtle one. (A blanket MagicMock survives boot only because
           mock.execute(...).fetchone() chains forever through more
           mocks -- that "absorb everything" behaviour is also what
           causes Job 2 to fail, see below.)

  Job 2  -- "Don't crash when a tool's result is sent back."
           When a tool like run_snowflake_query is ALLOWED by policy,
           its handler runs:

               with service.get_connection(use_dict_cursor=True) as (con, cur):
                   cur.execute(statement)
                   return cur.fetchall()        # <-- value flows back to the client

           SecureMCP wraps a non-dict return as {"result": <value>}
           (mcp.py:670-671) and the MACAW HTTP transport then does
           json.dumps(...) on it. Plain json.dumps has NO fallback for
           arbitrary objects. So if fetchall() returns a MagicMock,
           you get:

               ERROR  Object of type MagicMock is not JSON serializable

           and the client times out with "No result received for request".
           (This is exactly the error seen on the attestation-APPROVED
           path -- deny paths never reach the handler, so a blanket
           MagicMock never gets serialized there and the bug stays hidden.)

=====================================================================
THE FIX
=====================================================================

Replace the blanket MagicMock CONNECTION with a thin stub that returns
real, JSON-clean Python primitives from the leaf calls:

    cursor.execute(...)  -> a tiny result object (so .fetchone() chains)
    cursor.fetchone()    -> None        (JSON-clean)
    cursor.fetchall()    -> []          (JSON-clean -> client gets {"result": []})
    cursor.close()       -> None
    cursor as context-mgr (__enter__/__exit__) for `with conn.cursor() as cur`

With this, the run_snowflake_query ALLOWED path returns [] instead of a
MagicMock, json.dumps succeeds, and the client renders {"result": []}.

snowflake.core.Root is LEFT as a MagicMock on purpose. The object-manager
tools (create_object / drop_object) use Root, but in this demo those tools
are policy-gated (drop_object is in denied_resources; create_object is
constrained) and are denied at the Local Agent BEFORE the handler runs --
so Root is never serialized. If you later add a demo path that actually
executes an object tool, give Root the same stub treatment.

=====================================================================
HOW TO VALIDATE
=====================================================================

  - Boot succeeds: you see "SecureMCP server 'snowflake-mcp' started"
    and the 16-tool list. (Proves Job 1: send_initial_query chained OK.)
  - Deny path unchanged: drop_object -> instant policy DENY; a denied
    run_snowflake_query -> attestation flow. (Handler never runs; stub
    untouched.)
  - Approve path now clean: approve the allow_destroy attestation and
    run_snowflake_query returns {"result": []} to the client instead of
    the MagicMock JSON error. (Proves Job 2.)
"""

import sys
from unittest.mock import MagicMock


# ----------------------------------------------------------------------
# Patch BEFORE importing the server module. Order matters: importing
# mcp_server_snowflake.server triggers SnowflakeService construction,
# which calls snowflake.connector.connect() eagerly. Patch after import
# and you're too late.
# ----------------------------------------------------------------------
import snowflake.connector


class _StubResult:
    """What cursor.execute(...) returns.

    Exists ONLY so the boot-time warm-up `cur.execute(...).fetchone()`
    (server.py:251) chains without crashing. Both fetchers are JSON-clean.
    """

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _StubCursor:
    def execute(self, *args, **kwargs):
        # Return a result object (not None) so .execute(...).fetchone()
        # chains. The return is ignored by run_query, which calls
        # fetchall() separately.
        return _StubResult()

    def fetchone(self):
        return None          # JSON-clean

    def fetchall(self):
        return []            # JSON-clean -> handler returns [], wraps to {"result": []}

    def close(self):
        return None

    # send_initial_query uses `with connection.cursor() as cur:`
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _StubRest:
    # Only touched by REST-API tools (cortex_search / cortex_analyst /
    # cortex_agent) via get_api_headers(); not used by the demo's
    # drop_object / run_snowflake_query path. Present for safety.
    token = "stub-token"


class _StubConnection:
    host = "stub-host"          # get_api_host() fallback (REST tools only)
    rest = _StubRest()

    def cursor(self, *args, **kwargs):
        # Ignores a DictCursor argument if passed; returns the same stub
        # either way. (get_connection calls .cursor(DictCursor) or .cursor().)
        return _StubCursor()

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_real_connect = snowflake.connector.connect


def _stub_connect(**kwargs):
    print("[run-server-mock] snowflake.connector.connect intercepted; "
          "returning JSON-clean stub connection (no real Snowflake).")
    return _StubConnection()


snowflake.connector.connect = _stub_connect

# Root stays a MagicMock on purpose -- object-manager tools are
# policy-denied in this demo and never reach serialization. See the
# module docstring "THE FIX" section for the rationale.
import snowflake.core
snowflake.core.Root = lambda conn: MagicMock(name="MockSnowflakeRoot")

# Now safe to import the real server.
from mcp_server_snowflake.server import main


if __name__ == "__main__":
    main()
