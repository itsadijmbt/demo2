#!/usr/bin/env python3.11
"""Pretty-printing launcher for run-server-mock.py.

Filters Python deprecation/import warnings, fastmcp's rich banners, and
other startup noise. Renders the events that matter — boot identity,
tool registration, policy denies, attestation lifecycle — in a clean
structured form.

Usage (cwd = this dir):
    python3.11 launch-server.py

Verbose mode (show everything raw):
    python3.11 launch-server.py --verbose
    LAUNCH_SERVER_VERBOSE=1 python3.11 launch-server.py
"""

import ast
import os
import re
import signal
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# ANSI (no deps). Auto-disable when stdout isn't a TTY or NO_COLOR is set.
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") != "1"


def _c(code: str) -> str:
    return code if _USE_COLOR else ""


RESET = _c("\033[0m")
BOLD = _c("\033[1m")
DIM = _c("\033[2m")

GRAY = _c("\033[90m")
RED = _c("\033[91m")
GREEN = _c("\033[92m")
YELLOW = _c("\033[93m")
BLUE = _c("\033[94m")
MAGENTA = _c("\033[95m")
CYAN = _c("\033[96m")
WHITE = _c("\033[97m")

LEVEL_STYLE = {
    "DEBUG": GRAY,
    "INFO": CYAN,
    "WARNING": YELLOW,
    "WARN": YELLOW,
    "ERROR": RED,
    "CRITICAL": BOLD + RED,
    "FATAL": BOLD + RED,
}

# Short logging format: 10:36:47  INFO     logger.name    message
LOG_RE = re.compile(
    r"^(?P<ts>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\s+"
    r"(?P<logger>\S+)\s+(?P<message>.+)$"
)

# Full Python logging: 2026-06-09 22:30:54,163 - INFO - logger.name - msg
LOG_RE_FULL = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d{3})?)\s*-\s*"
    r"(?P<level>DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\s*-\s*"
    r"(?P<logger>[A-Za-z0-9_.]+)\s*-\s*"
    r"(?P<message>.*)$"
)

INDENT = " " * 49  # visual continuation alignment


# ---------------------------------------------------------------------------
# Noise patterns. Match the FULL line. Suppressed unless --verbose.
# ---------------------------------------------------------------------------
NOISE_PATTERNS = [
    re.compile(r"^/home/[^:]+:\d+:\s+\w*(?:Warning|Deprecation)"),
    re.compile(r"^\s*warnings?\.warn\("),
    re.compile(r"^\s*from authlib"),
    re.compile(r"^\s*It will be compatible"),
    # fastmcp rich banner box-drawing
    re.compile(r"^[│║╔╗╚╝╭╮╰╯─━═▄▀▐▌█▔▁ ]*[│║╔╗╚╝╭╮╰╯═─][│║╔╗╚╝╭╮╰╯─━═▄▀▐▌█▔▁ ]*$"),
    # fastmcp pre-mesh banners
    re.compile(r"^\[\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\]\s+INFO\s+(Using external authentication|Starting Snowflake)"),
    re.compile(r"^\s+INFO\s+Starting Snowflake MCP Server"),
    # run-server-mock notice
    re.compile(r"^\[run-server-mock\]"),
    re.compile(r"Tenant-aware context classes not available"),
    re.compile(r"DeprecationWarning:"),
    re.compile(r"RequestsDependencyWarning:"),
    re.compile(r"AuthlibDeprecationWarning:"),
]


def is_noise(line: str) -> bool:
    return any(p.search(line) for p in NOISE_PATTERNS)


def _trim_logger(name: str) -> str:
    parts = name.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else name


def _trim_ts_full(ts: str) -> str:
    if " " in ts:
        return ts.split()[-1].split(",")[0]
    return ts.split(",")[0]


def _ts_label(ts: str, level: str) -> str:
    lvl = LEVEL_STYLE.get(level, WHITE)
    return f"{GRAY}{ts}{RESET}  {lvl}{BOLD}{level:<7}{RESET}"


def _logger_col(logger_short: str) -> str:
    return f"{MAGENTA}{logger_short:<28}{RESET}"


# ---------------------------------------------------------------------------
# Event renderers.
# ---------------------------------------------------------------------------


def render_registered(ts, level, logger, msg):
    agent = msg.split("Registered as agent:", 1)[-1].strip()
    return [
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"{BOLD}{GREEN}● REGISTERED{RESET}  {GREEN}{agent}{RESET}",
    ]


def render_started(ts, level, logger, msg):
    m = re.search(r"SecureMCP server '([^']+)' started", msg)
    name = m.group(1) if m else "?"
    return [
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"{BOLD}{GREEN}✓ SERVER UP{RESET}  {BOLD}{name}{RESET}",
    ]


def render_agent_id(ts, level, logger, msg):
    aid = msg.split("Agent ID:", 1)[-1].strip()
    return [
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"Agent ID  {GREEN}{aid}{RESET}",
    ]


def _format_list_field(raw, item_color):
    try:
        items = ast.literal_eval(raw)
        if not isinstance(items, list):
            raise ValueError
    except Exception:
        return [raw]
    if not items:
        return [f"{DIM}(none){RESET}"]
    return [f"{DIM}({len(items)}){RESET}"] + [
        f"  {item_color}•{RESET} {it}" for it in items
    ]


def _render_list(ts, level, logger, msg, label, color):
    raw = msg.split(label + ":", 1)[-1].strip()
    lines = _format_list_field(raw, color)
    header = (
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"{BOLD}{label}{RESET}  {lines[0]}"
    )
    out = [header]
    for body in lines[1:]:
        out.append(f"{INDENT}{body}")
    return out


def render_tools(ts, level, logger, msg):
    return _render_list(ts, level, logger, msg, "Tools", CYAN)


def render_resources(ts, level, logger, msg):
    return _render_list(ts, level, logger, msg, "Resources", BLUE)


def render_prompts(ts, level, logger, msg):
    return _render_list(ts, level, logger, msg, "Prompts", MAGENTA)


def render_tool_agent_deny(ts, level, logger, msg):
    after = msg.split("Access denied:", 1)[-1].strip()
    return [
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"{BOLD}{RED}✗ DENY{RESET}  {RED}{after}{RESET}",
    ]


def render_audit(ts, level, logger, msg):
    parts = [p.strip() for p in msg.split("|")]
    head = parts[0]
    fields = {}
    for p in parts[1:]:
        if ":" in p:
            k, v = p.split(":", 1)
            fields[k.strip()] = v.strip()
        else:
            fields[p] = ""

    head_text = head.replace("AUDIT:", "").strip()
    head_color = RED if "DENIED" in head.upper() else GREEN
    lines = [
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"{BOLD}{head_color}AUDIT{RESET}  {head_color}{head_text}{RESET}"
    ]
    for k in ("Invoker", "Tool", "Service", "Request ID", "Policy", "Reason"):
        if k in fields:
            v = fields[k]
            vc = RED if k == "Reason" else WHITE
            lines.append(f"{INDENT}  {DIM}{k:<11}{RESET} {vc}{v}{RESET}")
    return lines


def render_verify_waiting(ts, level, logger, msg):
    m = re.search(
        r"WAITING:\s+(?P<key>\S+)\s+for\s+(?P<who>\S+)\s+\(timeout=(?P<to>\d+)s,\s+id=(?P<id>\S+)\)",
        msg,
    )
    if not m:
        return [
            f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
            f"{BOLD}{YELLOW}⏳ ATTESTATION WAITING{RESET}  {msg}"
        ]
    return [
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"{BOLD}{YELLOW}⏳ ATTESTATION WAITING{RESET}  {BOLD}{m['key']}{RESET}",
        f"{INDENT}  {DIM}for       {RESET}{m['who']}",
        f"{INDENT}  {DIM}timeout   {RESET}{m['to']}s",
        f"{INDENT}  {DIM}id        {RESET}{m['id']}",
    ]


def render_verify_outcome(ts, level, logger, msg):
    m = re.search(
        r"Attestation\s+(?P<id>\S+)\s+(?P<outcome>DENIED|APPROVED):\s*(?P<reason>.*)$",
        msg,
    )
    if not m:
        return [f"{_ts_label(ts, level)}  {_logger_col(logger)}  {msg}"]
    outcome = m["outcome"]
    color = RED if outcome == "DENIED" else GREEN
    icon = "✗" if outcome == "DENIED" else "✓"
    return [
        f"{_ts_label(ts, level)}  {_logger_col(logger)}  "
        f"{BOLD}{color}{icon} ATTESTATION {outcome}{RESET}  {BOLD}{m['id']}{RESET}",
        f"{INDENT}  {DIM}reason    {RESET}{color}{m['reason']}{RESET}",
    ]


EVENT_HANDLERS = [
    (lambda m: m.startswith("Registered as agent:"), render_registered),
    (lambda m: m.startswith("SecureMCP server '"), render_started),
    (lambda m: m.startswith("Agent ID:"), render_agent_id),
    (lambda m: m.startswith("Tools:"), render_tools),
    (lambda m: m.startswith("Resources:"), render_resources),
    (lambda m: m.startswith("Prompts:"), render_prompts),
    (lambda m: m.startswith("[TOOL-AGENT] Access denied:"), render_tool_agent_deny),
    (lambda m: m.startswith("AUDIT:"), render_audit),
    (lambda m: m.startswith("[VERIFY-FUTURE] WAITING:"), render_verify_waiting),
    (
        lambda m: m.startswith("[VERIFY-FUTURE] Attestation")
        and ("DENIED" in m or "APPROVED" in m),
        render_verify_outcome,
    ),
]


def format_line(line, verbose):
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped:
        return []

    if not verbose and is_noise(raw):
        return []

    m = LOG_RE.match(raw)
    if not m:
        full = LOG_RE_FULL.match(raw)
        if full:
            ts = _trim_ts_full(full.group("ts"))
            level = full.group("level")
            logger_name = _trim_logger(full.group("logger"))
            message = full.group("message")
        else:
            return [f"{DIM}{raw}{RESET}"] if verbose else []
    else:
        ts = m.group("ts")
        level = m.group("level")
        logger_name = _trim_logger(m.group("logger"))
        message = m.group("message")

    for matcher, renderer in EVENT_HANDLERS:
        if matcher(message):
            return renderer(ts, level, logger_name, message)

    return [f"{_ts_label(ts, level)}  {_logger_col(logger_name)}  {message}"]


def _print_banner(cmd, verbose):
    bar = "═" * 70
    print(f"{CYAN}{bar}{RESET}")
    print(f"{BOLD}{CYAN}  launch-server — pretty SecureMCP runner{RESET}")
    print(f"{DIM}  spawn:    {' '.join(cmd)}{RESET}")
    print(
        f"{DIM}  verbose:  {verbose}  "
        f"(set --verbose or LAUNCH_SERVER_VERBOSE=1 to see all noise){RESET}"
    )
    print(f"{DIM}  Ctrl-C to stop.{RESET}")
    print(f"{CYAN}{bar}{RESET}")
    print()


def main():
    here = Path(__file__).resolve().parent
    target = here / "run-server-mock.py"
    if not target.is_file():
        print(f"{RED}{BOLD}error:{RESET} can't find {target}", file=sys.stderr)
        return 2

    argv = list(sys.argv[1:])
    verbose = (
        "--verbose" in argv
        or "-v" in argv
        or os.environ.get("LAUNCH_SERVER_VERBOSE") == "1"
    )
    argv = [a for a in argv if a not in ("--verbose", "-v")]

    if "--service-config-file" not in argv:
        argv = ["--service-config-file", "services/configuration.yaml"] + argv

    cmd = [sys.executable, "-u", str(target)] + argv
    _print_banner(cmd, verbose)

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.setdefault(
        "PYTHONWARNINGS",
        "ignore::DeprecationWarning,ignore::PendingDeprecationWarning",
    )

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        cwd=str(here),
        env=env,
    )

    def _on_signal(signum, _frame):
        try:
            proc.send_signal(signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            for out in format_line(line, verbose):
                print(out, flush=True)
    except KeyboardInterrupt:
        pass

    rc = proc.wait()
    print(f"\n{DIM}{'═' * 70}{RESET}")
    print(f"{DIM}  child exited with code {rc}{RESET}")
    print(f"{DIM}{'═' * 70}{RESET}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
