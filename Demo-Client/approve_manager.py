#!/usr/bin/env python3
"""
approve_manager.py -- Manager attestation console for the Snowflake demo.

ROLE IN THE DEMO:
  1. A caller runs run_snowflake_query with a DROP/DELETE/GRANT statement.
  2. The Snowflake STORE policy (app:securemcp-snowflake-mcp) fires
     allow_destroy / allow_privilege (approval_criteria: role:manager, timeout 300).
     The caller's invoke_tool BLOCKS (pending attestation).
  3. THIS script -- a MACAWClient minted from the MANAGER's JWT -- polls for the
     pending request, prints WHO asked + WHAT they want, prompts you, and
     approve_attestation()s it. The caller then unblocks and the query runs.


RUN:
  python3 approve_manager.py            # defaults to buszadi1@gmail.com / test@123
  # override: MANAGER_USER=other@x MANAGER_PW=... python3 approve_manager.py
"""

import os
import sys
import json
import time
import base64

from macaw_client import MACAWClient, RemoteIdentityProvider

MANAGER_USER = os.environ.get("MANAGER_USER", "buszadi1@gmail.com")
MANAGER_PW = os.environ.get("MANAGER_PW", "test@123")
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "2"))
AUTO = os.environ.get("AUTO", "")  


def main():
    print("=" * 64)
    print("SNOWFLAKE MANAGER ATTESTATION CONSOLE")
    print("=" * 64)

    print(f"\n[1] Authenticating as manager '{MANAGER_USER}'...")
    try:
        jwt_token, _ = RemoteIdentityProvider().login(MANAGER_USER, MANAGER_PW)
    except Exception as e:
        print(f"  ERROR: login failed: {e}")
        print("  Check MANAGER_USER/MANAGER_PW and that the IdP is reachable.")
        return 1
    print("  got JWT")


    manager = MACAWClient(
        user_name=MANAGER_USER.split("@")[0],
        iam_token=jwt_token,
        agent_type="user",
        app_name="snowflake-attestation-manager",
        intent_policy={
            "resources": ["attestation:*"],
            "constraints": {"roles": ["manager"]},
        },
    )
    if not manager.register():
        print("  ERROR: register failed (is LocalAgent running?)")
        return 1
    print(f"  approver agent_id: {manager.agent_id}")
    print(f"  -> every approval below is signed by THIS identity (audit: approved_by)")

    # --- Step 3: poll for pending attestations and approve/deny ---
    print(f"\n[3] Watching for pending attestations (every {POLL_SECONDS}s). Ctrl-C to stop.")
    print("    Trigger one: run a DROP/DELETE/GRANT via run_snowflake_query in the caller.\n")
    seen = set()
    try:
        while True:
            try:
                pending = manager.list_attestations(status="pending") or []
            except Exception as e:
                print(f"  [warn] list_attestations error: {e}")
                pending = []

            for att in pending:
                rid = att.get("request_id") or att.get("id") or json.dumps(att, sort_keys=True)
                if rid in seen:
                    continue
                seen.add(rid)
                print("-" * 64)
                print(f"  PENDING attestation")
                print(f"    key             : {att.get('key')}")
                print(f"    requested by    : {att.get('for_agent')}")
                print(f"    approval_criteria: {att.get('approval_criteria')}")
                print(f"    one_time        : {att.get('one_time')}")
                if att.get("value"):
                    print(f"    value           : {json.dumps(att.get('value'))}")
                print("-" * 64)

                choice = AUTO or input("  Approve / Deny / Skip? [y/d/s]: ").strip().lower()
                if choice == "y":
                    ok = manager.approve_attestation(att, reason=f"Approved by {MANAGER_USER} (manager console)")
                    print(f"  -> APPROVED by {manager.agent_id} : {ok}")
                    print(f"     (audit: attestation_approved | approved_by={MANAGER_USER} | + signature)")
                elif choice == "d":
                    ok = manager.deny_attestation(att, reason=f"Denied by {MANAGER_USER}")
                    print(f"  -> DENIED by {manager.agent_id} : {ok}")
                else:
                    print("  -> skipped (will reappear next poll)")
                    seen.discard(rid)

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n  stopping...")
    finally:
        try:
            manager.unregister()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
