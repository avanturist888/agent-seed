#!/usr/bin/env python3
"""agent-mail — mail between AI coding agents on one machine.

One file, Python 3.9+ standard library only. Three faces:

  MCP server (stdio):  python agent_mail.py mcp
  CLI:                 python agent_mail.py send <to> <text|->
                       python agent_mail.py inbox [--peek]
                       python agent_mail.py agents
                       python agent_mail.py register <name> [--wake inbox|claude|codex|t3] [--session ID]
                                             [--args "extra wake flags"] [--steward]
                       python agent_mail.py log [--hours N]
  Hook (Claude Code):  python agent_mail.py hook      (SessionStart / UserPromptSubmit)

An agent is a folder: the working directory its session runs in. Every letter
is written to the recipient's inbox (always works), then the recipient is woken
the way its registry entry says:

  inbox  — nothing more; the letter is shown at its next session start / prompt
           (Claude Code hook) or when it calls `inbox` (any harness).
  claude — `claude -p --resume <last session>` in its folder: a headless turn in
           its latest Claude Code session. Do not use while a human has that
           session open in a terminal: two writers, one session.
  codex  — `codex exec resume <session>` in its folder (verify the syntax of
           your Codex version with `codex exec --help`).
  t3     — T3 Code: `t3 thread send <thread> -` (thread from T3CODE_THREAD_ID).

State lives in $AGENT_MAIL_HOME (default ~/.agent-mail): agents.json,
mail.jsonl (journal), inbox/<agent>/*.json.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

VERSION = "0.1.0"
BURST_WINDOW_MIN = 10
BURST_LIMIT = 6


# ---------- storage ----------

def home() -> Path:
    h = Path(os.environ.get("AGENT_MAIL_HOME") or Path.home() / ".agent-mail")
    h.mkdir(parents=True, exist_ok=True)
    return h


def now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def real(p: str | Path) -> str:
    """Absolute path as the OS spells it (case kept): for cwd of woken agents."""
    p = os.path.abspath(str(p))
    return p.rstrip("\\/") or p


def norm(p: str | Path) -> str:
    """Registry key: absolute, case-folded on Windows."""
    return os.path.normcase(real(p))


def key(folder: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", norm(folder)).strip("-")[-120:]


def load_agents() -> dict:
    f = home() / "agents.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_agents(a: dict) -> None:
    f = home() / "agents.json"
    tmp = f.with_name(f"agents.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(20):  # Windows: the target may be open by a reader
        try:
            os.replace(tmp, f)
            return
        except PermissionError:
            import time
            time.sleep(0.05 * (attempt + 1))
    tmp.unlink(missing_ok=True)
    raise PermissionError(f"could not update {f}")


def update_agent(folder: str, **fields) -> None:
    """Read-modify-write of one entry, as short as possible (concurrent hooks)."""
    a = load_agents()
    if folder not in a or all(a[folder].get(k) == v for k, v in fields.items()):
        return
    a[folder].update(fields)
    save_agents(a)


def journal(entry: dict) -> None:
    entry = {"at": now(), **entry}
    with open(home() / "mail.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def recent(minutes: float) -> list[dict]:
    f = home() / "mail.jsonl"
    if not f.exists():
        return []
    cutoff = _dt.datetime.now().astimezone() - _dt.timedelta(minutes=minutes)
    out = []
    for line in f.read_text(encoding="utf-8").splitlines()[-2000:]:
        try:
            e = json.loads(line)
            if _dt.datetime.fromisoformat(e["at"]) >= cutoff:
                out.append(e)
        except (ValueError, KeyError):
            continue
    return out


# ---------- identity ----------

def me() -> dict:
    """Who is calling: the folder of the session (MCP servers and hooks start
    in it); T3 Code also tells its thread id."""
    path = real(os.environ.get("AGENT_MAIL_SELF") or os.getcwd())
    folder = norm(path)
    entry = load_agents().get(folder, {})
    return {"folder": entry.get("path") or path, "key": folder,
            "name": entry.get("name") or Path(path).name,
            "thread": os.environ.get("T3CODE_THREAD_ID", "")}


def resolve(to: str) -> tuple[str, dict]:
    """to: agent name, folder path, or 'steward' (the meta-agent)."""
    agents = load_agents()
    t = to.strip()
    if t.lower() in ("steward", "meta", "meta-agent"):
        for folder, a in agents.items():
            if a.get("steward"):
                return folder, a
        raise ValueError("no steward registered (register one with --steward)")
    if os.path.isdir(t):
        folder = norm(t)
        return folder, agents.get(folder, {"name": Path(real(t)).name, "wake": "inbox", "path": real(t)})
    hits = [(f, a) for f, a in agents.items()
            if a.get("name", "").lower() == t.lower() or Path(f).name.lower() == t.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(f"several agents named '{t}', give a folder: " + "; ".join(f for f, _ in hits))
    raise ValueError(f"unknown agent '{t}'. Known: " + ", ".join(a.get("name", f) for f, a in agents.items()))


# ---------- sending ----------

def envelope(sender: dict, text: str) -> str:
    return (f"📨 Letter from agent «{sender['name']}» · {sender['folder']}\n\n{text.strip()}\n\n---\n"
            f"Reply with the `send` tool of agent-mail, to=\"{sender['folder']}\". "
            "Reply when you have something of substance; do not send thanks or acknowledgements.")


def deliver_inbox(folder: str, letter: dict) -> Path:
    d = home() / "inbox" / key(folder)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{_dt.datetime.now():%Y%m%d-%H%M%S}-{letter['id'][:8]}.json"
    f.write_text(json.dumps(letter, ensure_ascii=False, indent=2), encoding="utf-8")
    return f


def _spawn(cmd: list[str], cwd: str, stdin_text: str) -> None:
    """Start the waking command in the background; its output goes to wake.log."""
    with open(home() / "wake.log", "a", encoding="utf-8") as log:
        log.write(f"\n[{now()}] {cwd}: {' '.join(cmd[:4])} …\n")
        log.flush()
        kw: dict = {"cwd": cwd, "stdout": log, "stderr": log, "stdin": subprocess.PIPE}
        if os.name == "nt":
            kw["creationflags"] = 0x00000200 | 0x08000000  # NEW_PROCESS_GROUP | NO_WINDOW
        else:
            kw["start_new_session"] = True
        env = dict(os.environ)
        env.pop("T3CODE_THREAD_ID", None)  # the woken agent is not the sender
        env["AGENT_MAIL_SELF"] = cwd
        env["AGENT_MAIL_WOKEN"] = "1"  # its hook must not show the same letter again
        kw["env"] = env
        p = subprocess.Popen(cmd, **kw)
    p.stdin.write(stdin_text.encode("utf-8"))
    p.stdin.close()


# Pre-approved for a headless Claude turn, so a woken agent can answer and read mail.
CLAUDE_DEFAULT_ARGS = ["--allowedTools", "mcp__agent-mail__send", "mcp__agent-mail__inbox"]


def wake(folder: str, agent: dict, body: str) -> tuple[bool, str]:
    """(woken, description). Not woken = the letter waits in the inbox."""
    how = agent.get("wake", "inbox")
    cwd = agent.get("path") or folder
    args = agent.get("args")
    if how == "inbox":
        return False, "queued in inbox (shown at its next session start or prompt)"
    if how == "claude":
        exe = shutil.which("claude")
        if not exe:
            return False, "queued in inbox (claude CLI not found)"
        sid = agent.get("session")
        cmd = [exe, "-p", "--resume", sid] if sid else [exe, "-p", "--continue"]
        _spawn(cmd + (CLAUDE_DEFAULT_ARGS if args is None else args), cwd, body)
        return True, f"woke its Claude Code session {sid or '(latest)'} headless"
    if how == "codex":
        exe = shutil.which("codex")
        if not exe:
            return False, "queued in inbox (codex CLI not found)"
        sid = agent.get("session")
        cmd = [exe, "exec", "resume", sid] if sid else [exe, "exec", "resume", "--last"]
        _spawn(cmd + (args or []) + ["-"], cwd, body)
        return True, f"woke its Codex session {sid or '(last)'}"
    if how == "t3":
        thread = agent.get("thread")
        t3 = agent.get("t3_cli") or shutil.which("t3")
        if not (thread and t3):
            return False, "queued in inbox (no T3 thread or t3 CLI)"
        _spawn([t3, "thread", "send", thread, "-"], cwd, body)
        return True, f"sent to its T3 thread {thread}"
    return False, f"queued in inbox (unknown wake '{how}')"


def send(to: str, text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty letter")
    sender = me()
    folder, agent = resolve(to)
    if folder == sender["key"]:
        raise ValueError("that is your own folder")
    burst = [e for e in recent(BURST_WINDOW_MIN)
             if e.get("from") == sender["key"] and e.get("to") == folder and not e.get("error")]
    if len(burst) >= BURST_LIMIT:
        raise ValueError(f"already {len(burst)} letters to this agent in {BURST_WINDOW_MIN} min — "
                         "looks like ping-pong. Stop; merge your thoughts into one letter later.")
    letter = {"id": uuid.uuid4().hex, "at": now(), "from": sender, "to": folder, "text": text}
    box = deliver_inbox(folder, letter)  # first: the fallback if waking fails
    body = envelope(sender, text)
    try:
        woken, how = wake(folder, agent, body)
    except Exception as e:
        woken, how = False, f"queued in inbox (wake failed: {e})"
    if woken:  # the woken turn got the letter as its prompt: don't show it twice
        (box.parent / "read").mkdir(exist_ok=True)
        os.replace(box, box.parent / "read" / box.name)
    journal({"from": sender["key"], "to": folder, "how": how, "text": text})
    return f"Delivered to «{agent.get('name', Path(folder).name)}» · {agent.get('path') or folder}: {how}."


# ---------- reading ----------

def inbox(peek: bool = False, folder: str | None = None) -> str:
    folder = norm(folder or me()["folder"])
    d = home() / "inbox" / key(folder)
    files = sorted(d.glob("*.json")) if d.exists() else []
    if not files:
        return ""
    out = []
    for f in files:
        try:
            letter = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append(envelope(letter["from"], letter["text"]))
        if not peek:
            read = d / "read"
            read.mkdir(exist_ok=True)
            os.replace(f, read / f.name)
    return "\n\n════════\n\n".join(out)


def agents_list() -> str:
    a = load_agents()
    if not a:
        return "No agents registered yet."
    rows = []
    for folder, e in sorted(a.items()):
        d = home() / "inbox" / key(folder)
        unread = len(list(d.glob("*.json"))) if d.exists() else 0
        tag = " [steward]" if e.get("steward") else ""
        rows.append(f"- {e.get('name', Path(folder).name)}{tag} · {e.get('path') or folder} · wake={e.get('wake', 'inbox')}"
                    + (f" · unread {unread}" if unread else ""))
    return "\n".join(rows)


def register(name: str, wake_mode: str = "inbox", session: str | None = None,
             steward: bool = False, folder: str | None = None, **extra) -> str:
    if wake_mode not in ("inbox", "claude", "codex", "t3"):
        raise ValueError("wake must be inbox | claude | codex | t3")
    path = real(folder or me()["folder"])
    folder = norm(path)
    a = load_agents()
    e = a.get(folder, {})
    e.update({"name": name, "wake": wake_mode, "path": path, "registered": now()})
    if session:
        e["session"] = session
    if os.environ.get("T3CODE_THREAD_ID"):
        e["thread"] = os.environ["T3CODE_THREAD_ID"]
    e.update({k: v for k, v in extra.items() if v})
    if steward:
        for other in a.values():
            other.pop("steward", None)
        e["steward"] = True
    a[folder] = e
    save_agents(a)
    return f"Registered «{name}» · {folder} · wake={wake_mode}" + (" · steward" if steward else "")


def log(hours: float = 24) -> str:
    rows = [f"{e['at'][5:16]} {Path(e.get('from', '?')).name} → {Path(e.get('to', '?')).name}: "
            f"{e.get('text', '')[:100].replace(chr(10), ' ')} [{e.get('how', '')}]"
            for e in recent(hours * 60)]
    return "\n".join(rows) or "No letters in this period."


# ---------- Claude Code hook ----------

def hook() -> None:
    """SessionStart / UserPromptSubmit: remember the session id of this folder
    (so `wake=claude` resumes the right session) and show unread letters."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}
    folder = norm(data.get("cwd") or os.getcwd())
    if data.get("session_id"):
        update_agent(folder, session=data["session_id"])
    if os.environ.get("AGENT_MAIL_WOKEN"):
        return  # a turn started by a letter: that letter is its prompt already
    text = inbox(folder=folder)
    if text:
        print("You have mail from other agents (agent-mail):\n\n" + text)


# ---------- MCP (stdio JSON-RPC) ----------

TOOLS = [
    {"name": "send",
     "description": "Send a letter to another agent: wakes it (or queues it) with your text and how to reply. "
                    "to = agent name, folder path, or 'steward' (the meta-agent). Asynchronous: the answer "
                    "arrives later as a new letter; do not wait for it in this call.",
     "inputSchema": {"type": "object", "required": ["to", "message"], "properties": {
         "to": {"type": "string"}, "message": {"type": "string"}}}},
    {"name": "inbox", "description": "Read your unread letters (marks them read).",
     "inputSchema": {"type": "object", "properties": {"peek": {"type": "boolean"}}}},
    {"name": "agents", "description": "List registered agents: name, folder, how they are woken, unread count.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "register",
     "description": "Register the current folder as an agent. wake: inbox | claude | codex | t3. "
                    "steward=true marks the meta-agent.",
     "inputSchema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string"}, "wake": {"type": "string"},
         "session": {"type": "string"}, "steward": {"type": "boolean"}}}},
    {"name": "log", "description": "Mail journal for the last N hours (default 24).",
     "inputSchema": {"type": "object", "properties": {"hours": {"type": "number"}}}},
]

INSTRUCTIONS = ("Mail between AI agents on this machine. Write to the steward (to='steward') when you finished "
                "what it asked, found a problem that affects other projects or the whole machine, or need an "
                "agent from another folder. Letters are asynchronous. Do not reply to thanks or acknowledgements.")


def call_tool(name: str, args: dict) -> str:
    if name == "send":
        return send(args.get("to", ""), args.get("message", ""))
    if name == "inbox":
        return inbox(peek=bool(args.get("peek"))) or "No unread letters."
    if name == "agents":
        return agents_list()
    if name == "register":
        return register(args["name"], args.get("wake") or "inbox", args.get("session"), bool(args.get("steward")))
    if name == "log":
        return log(float(args.get("hours") or 24))
    raise ValueError(f"unknown tool {name}")


def mcp() -> None:
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):  # batches are not used by MCP clients
            continue
        mid, method = msg.get("id"), msg.get("method", "")
        if mid is None:  # notification
            continue
        try:
            if method == "initialize":
                res = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
                       "capabilities": {"tools": {}},
                       "serverInfo": {"name": "agent-mail", "version": VERSION},
                       "instructions": INSTRUCTIONS}
            elif method == "tools/list":
                res = {"tools": TOOLS}
            elif method == "tools/call":
                p = msg.get("params", {})
                try:
                    res = {"content": [{"type": "text", "text": call_tool(p.get("name"), p.get("arguments") or {})}]}
                except Exception as e:
                    res = {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
            elif method == "ping":
                res = {}
            else:
                out.write(json.dumps({"jsonrpc": "2.0", "id": mid,
                                      "error": {"code": -32601, "message": f"method not found: {method}"}}) + "\n")
                out.flush()
                continue
            out.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}, ensure_ascii=False) + "\n")
        except Exception as e:
            out.write(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}) + "\n")
        out.flush()


# ---------- CLI ----------

def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    def opt(flag: str, default=None):
        if flag in rest:
            i = rest.index(flag)
            v = rest[i + 1] if i + 1 < len(rest) else default
            del rest[i:i + 2]
            return v
        return default

    def flag(f: str) -> bool:
        if f in rest:
            rest.remove(f)
            return True
        return False

    try:
        if cmd == "mcp":
            mcp()
        elif cmd == "hook":
            hook()
        elif cmd == "send":
            to, text = rest[0], " ".join(rest[1:])
            print(send(to, sys.stdin.read() if text == "-" else text))
        elif cmd == "inbox":
            print(inbox(peek=flag("--peek")) or "No unread letters.")
        elif cmd == "agents":
            print(agents_list())
        elif cmd == "register":
            wake_mode = opt("--wake", "inbox")
            session = opt("--session")
            folder = opt("--folder")
            args = opt("--args")  # extra CLI flags for waking, as one string
            steward = flag("--steward")
            print(register(rest[0], wake_mode, session, steward, folder,
                           args=args.split() if args else None))
        elif cmd == "log":
            print(log(float(opt("--hours", 24))))
        else:
            print(f"unknown command {cmd}\n\n{__doc__}")
            return 2
    except (ValueError, IndexError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
