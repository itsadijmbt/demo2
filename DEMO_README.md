# Snowflake SecureMCP Demo — Vanilla vs MACAW

The **same destructive Snowflake query**, two ways:

- **Vanilla MCP server** runs it blindly — no identity, no policy, no audit.
- **MACAW-secured (SecureMCP) server** **denies** the drop and **requires manager
  attestation** for the destructive query — with a real user identity and a signed
  audit trail.

---

## The cast

| Side | File | Role |
|---|---|---|
| **Vanilla** | `Demo-Client/snowflake-mcp-upstream/run-mock-http.py` | upstream Snowflake-Labs server on `http://127.0.0.1:9000/mcp` (Snowflake mocked) |
| **Vanilla** | `Demo-Client/normal-client.py` | plain MCP client → the upstream; runs the destructive calls |
| **MACAW** | `run-server-mock.py` | the **ported SecureMCP** server (Snowflake mocked, no creds) |
| **MACAW** | `launch-server.py` | pretty-printing launcher for `run-server-mock.py` (nicer demo output) |
| **MACAW** | `Demo-Client/macaw-client.py` | the **caller** — invokes the tools through the MACAW mesh |
| **MACAW** | `Demo-Client/approve_manager.py` | the **approver** — a manager JWT that approves the pending attestation |
| Config | `Demo-Client/claims-config.yaml` | Auth0 → MACAW claims mapping (identity + roles) |
| Helper | `Demo-Client/_pretty.py` | shared ANSI formatting |

---

## Prerequisites (what you need to set up)

1. **MACAW installed** where you'll run it (`venv` + `MACAW_HOME`), with the **tenant
   `api_key`** in `$MACAW_HOME/.macaw/config.json` and the Local Agent reachable.
2. **Identity Bridge (Auth0)** registered in the MACAW Console — see [Identity setup](#identity-bridge-auth0).
3. **Test users with roles** in the IdP:
   - a **manager** (runs the approver) — e.g. `buszadi1@gmail.com` with role `manager`
   - a **caller** (analyst/user) — whoever runs `macaw-client.py`
4. **Snowflake STORE policy loaded** in the Console — `app:securemcp-snowflake-mcp`:
   - `denied_resources` includes `tool:drop_object`
   - attestations `allow_destroy` / `allow_privilege` with `approval_criteria: role:manager`, `timeout: 300`

---

## Identity Bridge (Auth0)

Add this provider in **MACAW Console → Settings → Identity Bridge**. The active provider
for this demo is **`macaw-mcp-test-api (Test Application)`**.

```jsonc
{
  "label": "macaw-mcp-test-api (Test Application)",
  "type": "auth0",
  "config": {
    "domain":        "dev-5ntnefdmlsiwh7nv.us.auth0.com",
    "client_id":     "hEsxdisSDvTFveohwR2JuiYEHCIgc0ZG",
    "audience":      "macaw-mcp-test-api",
    "client_secret": "<client_secret — shared separately via mail/drive, do NOT commit>"
  }
}
```
> ⚠️ `client_secret` is a live Auth0 secret — keep it out of this (public) repo; share it
> through the doc/mail like the other credentials.

### Claims mapping (Console → Claims Config)

| MACAW field | Auth0 claim path |
|---|---|
| subject | `sub` |
| email | `email` |
| name | `name` |
| organization (company) | `https://macaw.local/organization` |
| business_unit | `https://macaw.local/business_unit` |
| team | `https://macaw.local/team` |
| **roles** | `https://macaw.local/roles` |

Role filter (allowed): `analyst`, `manager`, `admin`, `viewer` (case-insensitive).

> ⚠️ Claim paths must have **no trailing spaces** — a trailing space makes MACAW look for a
> claim literally named `".../roles "` and the user gets **no role**, breaking the
> attestation/audit proof.

---

## Run it

> For every MACAW-side terminal first:
> `source /path/to/venv/bin/activate && export MACAW_HOME=/path/to/macaw-client`

### Side A — Vanilla (no security)
```bash
# Terminal 1 — upstream server (mocked Snowflake) on :9000
cd Demo-Client/snowflake-mcp-upstream && python run-mock-http.py

# Terminal 2 — plain MCP client
cd Demo-Client && python normal-client.py
```
**Result:** both destructive calls are **ACCEPTED**. No identity attached, no policy, no
signed audit — whoever ran it is invisible.

### Side B — MACAW (SecureMCP)
```bash
# Terminal 1 — the SecureMCP server (pretty logs; auto-adds --service-config-file)
python3 launch-server.py

# Terminal 2 — the caller
cd Demo-Client && python3 macaw-client.py "snowflake" macaw-snowflake-agent

# Terminal 3 — the manager approver (defaults: buszadi1@gmail.com / test@123)
cd Demo-Client && python3 approve_manager.py
```
**Result:**
- **TEST 1 — `drop_object`** → **DENY** at the policy (`denied_resources`). Handler never
  runs. Signed audit entry produced.
- **TEST 2 — `run_snowflake_query` (DROP/DELETE/…)** → the policy fires
  `allow_destroy`/`allow_privilege`; the caller **BLOCKS** pending attestation. Terminal 3
  shows **who** asked and **what**, you approve as **manager**, and the caller **unblocks**
  and runs. Whole flow is signed + audited.

---

## What to watch (MACAW visibility)
- **secCC / Console window** — the pending attestation, and the manager approving it.
- **MACAW Console — Traces/Audit** — the call flow `caller → app:securemcp-snowflake-mcp`,
  the **deny** on `drop_object`, the **attestation** on the destructive query, each as a
  **signed** entry. The caller appears as the real Auth0 user with role from the claims
  mapping above.

**The takeaway:** vanilla MCP executes destruction blindly; MACAW **denies** it, or holds
it for **manager approval**, tied to a verified identity and an unforgeable audit trail.
