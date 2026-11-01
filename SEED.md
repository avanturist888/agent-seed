# SEED — instructions for the agent

You were given this repository by a person who wants what its author has: a
**steward** — a meta-agent that looks after their machine and all their
projects — plus **shared rules** that every agent on the machine follows, and
**mail** so agents of different projects can talk to each other.

You are going to grow that in *their* environment. Not copy — grow: the
principles come from the seed, but names, places, language and mechanisms come
from this person and this machine. Read [PHILOSOPHY.md](PHILOSOPHY.md) first:
when a step below doesn't fit their environment, the philosophy decides.

Work in phases. Finish and verify each before the next. Tell the person in one
or two lines what you are doing at each phase; ask only what you cannot find
out yourself.

## Phase 0 — Look around (no questions yet)

Find out yourself:

- OS, shell, home folder, where projects live (look for folders full of git
  repos).
- Which agent harness you run in and which are installed: Claude Code
  (`claude --version`), Codex (`codex --version`), OpenCode, Cursor, Gemini CLI,
  other. Where each reads **global instructions** — e.g. Claude Code:
  `~/.claude/CLAUDE.md` (supports `@path` imports); Codex: `~/.codex/AGENTS.md`;
  others: check their docs. Where each registers **MCP servers** (Claude Code:
  `claude mcp add -s user …`; Codex: `~/.codex/config.toml` `[mcp_servers.*]`).
- Whether an orchestrator runs the sessions (T3 Code: `~/.t3`, `t3` CLI,
  `T3CODE_THREAD_ID` in your environment) or the person works in plain
  terminals / an IDE.
- `git`, `gh` (logged in?), and a **working Python 3.9+ command** — try
  `python3`, `python`, `py -3`, `uv run --no-project python`. On Windows a bare
  `python` may be the Microsoft Store stub: run `<cmd> --version` to be sure.
  Below, `<py>` means the command that worked, and `<home>` the steward's home
  written with **forward slashes and absolute** (hooks may run through a POSIX
  shell that eats backslashes).
- If you run inside an IDE extension, check whether the harness CLI is on PATH
  (`claude`, `codex`). If not, find its binary (IDE extensions bundle one) or
  edit the config files directly (Claude Code user-scope MCP servers live in
  `~/.claude.json` under `mcpServers`), and ask the person to open a terminal
  session for the live checks.

Write down what you found; you will need it for every later phase.

## Phase 1 — Meet the person (short interview)

Ask in their language, 2–3 questions per turn, offer your guess with each:

1. **How to address them**, and the **name** of the steward. The author's
   steward is "Nestor" (Homer's elder who remembered three generations and sent
   others on their way). Offer a name that fits, or let them choose.
2. **Language** of rules and conversation.
3. **What must never be touched** without asking: folders, accounts, devices,
   anything shared with other people. This goes into `ROLE.md` → Authority.
4. **Where the steward lives**: default `~/<steward-name>` as a private git
   repository (GitHub private repo if `gh` is available; local-only otherwise).
   The steward's sessions run in that folder.

## Phase 2 — The steward's home

Create the home repository with this layout (copy from `template/`, translate
into their language, fill the `{{…}}` placeholders):

```
<home>/
  ROLE.md            ← from template/ROLE.md: who the steward is, habits, authority, map, round
  rules/global.md    ← from template/rules/global.md: shared rules for ALL agents
  memory/            ← facts that outlive conversations (one fact per file + an index)
  skills/philosophy-interview/SKILL.md
  tools/agent_mail.py
  README.md          ← how to restore this on a new machine
```

- Fill the map in `ROLE.md` with the real project folders you found.
- If the harness keeps per-folder memory (Claude Code:
  `~/.claude/projects/<steward folder, every non-alphanumeric char → "-">/memory`),
  make that folder a link to `<home>/memory`, so memory is versioned with the
  steward. If it already has files, move them into `<home>/memory` first (back
  up). Windows: use a junction (`mklink /J` from cmd, or PowerShell
  `New-Item -ItemType Junction`) — Git Bash `ln -s` silently makes a copy.
  Verify it is a link, not a copy.
- Commit. Push only to a **private** remote.

## Phase 3 — Shared rules for every agent

Wire `<home>/rules/global.md` into the global instructions of **every** harness
installed (Phase 0 list):

- Claude Code: `~/.claude/CLAUDE.md` containing `@<home>/rules/global.md`
  (keep anything already there; back it up first).
- Codex and others without imports: back up their global file, then write
  `rules/global.md` into it between markers (`<!-- agent-seed:start -->` …
  `<!-- agent-seed:end -->`), keeping what the person had outside the markers.
  Note in `ROLE.md` that it must be regenerated after every edit (or add a
  small sync script).
- The steward's own folder: the harness's project instruction file there says
  "You are <name>; read ROLE.md and act by it." If the steward lives in the
  home folder itself, guard it: an instruction in that folder that applies only
  when the working directory is exactly that folder, not a subfolder.

Install the skill `skills/philosophy-interview` where the harness looks for
skills (Claude Code: `~/.claude/skills/philosophy-interview` → link to the
copy in the steward's home). Harnesses without skills: reference it from the
global rules by path.

**Verify with a live agent**, not by reading files: start a fresh session in an
unrelated project folder and ask it to quote the first principle of the shared
rules. Only a quote counts.

## Phase 4 — Mail

Use `tools/agent_mail.py` (stdlib-only Python; read its docstring) or, if the
environment has a better native channel, build on that — but keep the same
contract: **send(to, message)** that wakes or queues, **inbox**, **agents**, a
journal, and a loop guard.

1. Register the MCP server under the name **`agent-mail`** globally in every
   harness (the name matters: wake-ups pre-approve `mcp__agent-mail__send`).
   Claude Code: `claude mcp add -s user agent-mail -- <py> <home>/tools/agent_mail.py mcp`.
   Codex, `~/.codex/config.toml`:
   ```toml
   [mcp_servers.agent-mail]
   command = "<py>"          # split launcher words into command + args
   args = ["<home>/tools/agent_mail.py", "mcp"]
   ```
2. Claude Code: add hooks so a session sees its mail and its session id is
   remembered for waking — merge into `~/.claude/settings.json` (back it up
   first, keep existing hooks):
   ```json
   {"hooks": {
     "SessionStart":     [{"hooks": [{"type": "command", "command": "<py> <home>/tools/agent_mail.py hook"}]}],
     "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "<py> <home>/tools/agent_mail.py hook"}]}]
   }}
   ```
   Harnesses without hooks (Codex, …) see mail only by calling `inbox` — the
   shared rules tell every agent to do that at the start of a session.
3. Choose the **wake mode** per agent with the person (see `mail/README.md`):
   `t3` under T3 Code; `claude` / `codex` for headless wake-up of the latest
   session; `inbox` when the person keeps sessions open themselves (safest).
   A headless Claude turn may only use pre-approved tools; the default lets it
   `send` and `inbox`. If the steward must do more when woken, set
   `--args "--allowedTools …"` or a permission mode at `register` — never
   `--dangerously-skip-permissions` without the person's explicit consent.
4. Register the steward: from its folder,
   `<py> <home>/tools/agent_mail.py register <name> --steward --wake <mode>`.
   Register project agents as they appear (any agent can call `register`).

**Verify end to end:** from a project folder send the steward a letter; check
it is woken (or sees it at the next prompt) and its reply reaches the project
agent. Fix until the round trip works.

## Phase 5 — First round and philosophy

1. Do the first **round** from `ROLE.md`: mail, home folder, disk, background
   processes. The first round only **reports** — on a new machine you don't yet
   know what is garbage and which process is the person's work. Delete or stop
   nothing you did not start yourself.
2. Interview the person about the steward's own philosophy (skill
   `philosophy-interview`) — or confirm `PHILOSOPHY.md` of this seed as the
   starting point and record what differs.
3. Tell the person how to use what now exists, in three lines:
   - talk to the steward in its folder/thread;
   - every project agent follows the shared rules and can write to the steward;
   - a remark ("you should have…") becomes a sharper rule — that is how the
     system learns.

## While living

- Every remark from the person: fix the case → find the principle → put it at
  the right level (shared rules only for the universal) → check the edit → say
  what changed. Add the case in *(italics)* next to the rule it produced.
- Keep `ROLE.md` describing the present. Prune.
- Never publish the steward's home: it holds the person's life.
