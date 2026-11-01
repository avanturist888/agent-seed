# agent-mail

Mail between AI coding agents on one machine. One file, Python 3.9+ standard
library, no dependencies: [`agent_mail.py`](agent_mail.py).

- **An agent is a folder** — the working directory its sessions run in.
- **Every letter lands in the recipient's inbox** (`~/.agent-mail/inbox/…`),
  then the recipient is **woken** according to its registry entry.
- **The envelope tells how to reply** (`send` to the sender's folder) and asks
  not to answer thanks — that, plus a limit of 6 letters per pair in 10
  minutes, keeps agents from ping-pong.

## Interfaces

| Face | Command |
|---|---|
| MCP server (stdio) | `python agent_mail.py mcp` — tools `send`, `inbox`, `agents`, `register`, `log` |
| CLI | `python agent_mail.py send <to> <text\|->`, `inbox [--peek]`, `agents`, `register <name> [--wake M] [--session ID] [--steward]`, `log [--hours N]` |
| Claude Code hook | `python agent_mail.py hook` on `SessionStart` and `UserPromptSubmit`: shows unread letters, remembers the session id for waking |

`to` is an agent name, a folder path, or `steward`.

## Wake modes

| Mode | What happens | Use when |
|---|---|---|
| `inbox` | Nothing more. Claude Code sees the letter at the next session start or prompt (hook); other harnesses — when the agent calls `inbox`. | The person keeps sessions open and talks to agents themselves. Safest. |
| `claude` | `claude -p --resume <last session>` in the agent's folder, letter on stdin: a headless turn in its latest session, with its full history. Pre-approved by default: `mcp__agent-mail__send`, `mcp__agent-mail__inbox` (so it can answer). | Agents that should act on mail without a human. Don't use while the person has that same session open: one session, two writers. Other flags (allowed tools, permission mode, model): `register … --args "…"` — they replace the default. |
| `codex` | `codex exec resume <session or --last> -` in the agent's folder. | Codex users. Verify the exact syntax with `codex exec --help` for your version. |
| `t3` | `t3 thread send <thread> -` | Sessions run under T3 Code (the thread id is captured from `T3CODE_THREAD_ID` at `register`). |

Other orchestrators: add a branch in `wake()` that hands the envelope to the
session the same way a human message would arrive. Keep the inbox write — it is
the fallback when waking fails.

## State

`$AGENT_MAIL_HOME` (default `~/.agent-mail`):

- `agents.json` — folder → `{name, wake, session, thread, steward, args}`;
- `mail.jsonl` — journal of every letter;
- `inbox/<folder-key>/*.json`, read letters move to `read/`;
- `wake.log` — output of headless wake-ups (look here when a woken agent seems
  silent).

## Check that it works

```sh
python agent_mail.py register alice --steward       # in folder A
python agent_mail.py register bob                   # in folder B
python agent_mail.py send steward "ping from bob"   # in folder B
python agent_mail.py inbox                          # in folder A → the letter
```

Then the real test: a live agent in folder B sends a letter through the MCP
tool, the steward is woken (or sees it at the next prompt), replies, and the
reply reaches B.
