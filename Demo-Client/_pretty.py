"""ANSI pretty-printing helpers shared by normal-client.py and
macaw-client.py.

Stdlib only -- no rich, no colorama, no extra deps.
Colors auto-disable when stdout isn't a TTY or NO_COLOR=1.
"""

import os
import sys

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") != "1"


def _c(code):
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

WIDTH = 72


# ---------------------------------------------------------------------------
# Banners / sections
# ---------------------------------------------------------------------------


def banner(title, subtitle=None, accent=CYAN):
    bar = "═" * WIDTH
    print()
    print(f"{accent}{bar}{RESET}")
    print(f"{BOLD}{accent}  {title}{RESET}")
    if subtitle:
        print(f"{DIM}  {subtitle}{RESET}")
    print(f"{accent}{bar}{RESET}")


def section(title, accent=CYAN):
    dash = "─" * max(0, WIDTH - len(title) - 5)
    print()
    print(f"{accent}── {BOLD}{title}{RESET}{accent} {dash}{RESET}")


def footer(message="done", accent=None):
    accent = accent or DIM
    print()
    print(f"{accent}{'═' * WIDTH}{RESET}")
    print(f"{accent}  {message}{RESET}")
    print(f"{accent}{'═' * WIDTH}{RESET}")


# ---------------------------------------------------------------------------
# Tool catalog
# ---------------------------------------------------------------------------


def _tool_name(t):
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        return t.get("name", "?")
    return getattr(t, "name", str(t))


def tool_list(tools, columns=3, accent=CYAN):
    names = [_tool_name(t) for t in tools]
    if not names:
        print(f"  {DIM}(none){RESET}")
        return
    col_w = max(len(n) for n in names) + 2
    rows = (len(names) + columns - 1) // columns
    for r in range(rows):
        line = ""
        for c in range(columns):
            i = c * rows + r
            if i < len(names):
                line += f"  {accent}•{RESET} {names[i]:<{col_w}}"
        print(line.rstrip())
    print(f"  {DIM}({len(names)} tools){RESET}")


# ---------------------------------------------------------------------------
# Per-test box
# ---------------------------------------------------------------------------


def test_box(idx, title, subtitle=None, accent=BLUE):
    label = f"TEST {idx}"
    dash = "─" * max(1, WIDTH - len(label) - 5)
    print()
    print(f"{accent}┌─ {BOLD}{label}{RESET}{accent} {dash}{RESET}")
    print(f"{accent}│{RESET}  {BOLD}{title}{RESET}")
    if subtitle:
        print(f"{accent}│{RESET}  {DIM}{subtitle}{RESET}")
    print(f"{accent}└{'─' * (WIDTH - 1)}{RESET}")


def call_summary(tool, args):
    args_str = _format_args(args)
    print(f"  {DIM}call{RESET}  {BOLD}{tool}{RESET}")
    print(f"  {DIM}args{RESET}  {args_str}")


def _format_args(args):
    if not args:
        return f"{DIM}(none){RESET}"
    parts = []
    for k, v in args.items():
        if isinstance(v, dict):
            sub = ", ".join(f"{kk}={_short_repr(vv)}" for kk, vv in v.items())
            parts.append(f"{CYAN}{k}{RESET}={{{sub}}}")
        else:
            parts.append(f"{CYAN}{k}{RESET}={_short_repr(v)}")
    return ", ".join(parts)


def _short_repr(v):
    if isinstance(v, str):
        return f'"{v}"' if len(v) <= 60 else f'"{v[:57]}..."'
    return repr(v)


# ---------------------------------------------------------------------------
# Result outcomes
# ---------------------------------------------------------------------------


def accepted(message="ACCEPTED"):
    print()
    print(f"  {BOLD}{GREEN}✓ {message}{RESET}")


def denied(message="DENIED"):
    print()
    print(f"  {BOLD}{RED}✗ {message}{RESET}")


def waiting(message="WAITING"):
    print()
    print(f"  {BOLD}{YELLOW}⏳ {message}{RESET}")


def result_body(text):
    if text is None or text == "":
        text = "(empty)"
    lines = str(text).splitlines() or [str(text)]
    for line in lines:
        print(f"    {DIM}│{RESET} {line}")


# ---------------------------------------------------------------------------
# Commentary
# ---------------------------------------------------------------------------


def note(message, kind="info"):
    if kind == "warn":
        prefix = f"{YELLOW}⚠{RESET}"
        msg_color = YELLOW
    elif kind == "good":
        prefix = f"{GREEN}✓{RESET}"
        msg_color = GREEN
    elif kind == "bad":
        prefix = f"{RED}✗{RESET}"
        msg_color = RED
    elif kind == "info":
        prefix = f"{CYAN}ℹ{RESET}"
        msg_color = DIM
    else:
        prefix = " "
        msg_color = DIM
    print(f"  {prefix} {msg_color}{message}{RESET}")


def commentary(messages, kind="info"):
    print()
    for m in messages:
        note(m, kind=kind)


# ---------------------------------------------------------------------------
# Interactive prompt
# ---------------------------------------------------------------------------


def prompt_box(label, default=None, hint=None, accent=CYAN):
    """Draw a boxed interactive prompt and return the entered text.

    - Press Enter with no input  -> returns `default`.
    - Non-interactive stdin (piped / redirected) -> uses `default`
      silently so the demo still runs end-to-end without a TTY.
    - Ctrl-C / EOF at the prompt  -> returns `default`.
    """
    print()
    print(f"{accent}╭{'─' * (WIDTH - 1)}{RESET}")
    print(f"{accent}│{RESET}  {BOLD}{accent}{label}{RESET}")
    if hint:
        print(f"{accent}│{RESET}  {DIM}{hint}{RESET}")
    if default is not None:
        print(f"{accent}│{RESET}  {DIM}press ⏎ for default →{RESET}  {WHITE}{default}{RESET}")
    print(f"{accent}╰{'─' * (WIDTH - 1)}{RESET}")

    if not sys.stdin.isatty():
        val = default or ""
        print(f"  {accent}❯{RESET} {DIM}{val}   (non-interactive · used default){RESET}")
        return val

    try:
        raw = input(f"  {accent}❯{RESET} {BOLD}")
    except (EOFError, KeyboardInterrupt):
        raw = ""
    finally:
        # input() leaves the BOLD SGR active on the typed text; reset it.
        sys.stdout.write(RESET)
        sys.stdout.flush()

    raw = raw.strip()
    return raw if raw else (default or "")
