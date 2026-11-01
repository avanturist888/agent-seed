# agent-seed

A seed for growing your own **steward**: a meta-agent that looks after your
machine and all your projects, **shared rules** every AI agent on the machine
follows, and **mail** so agents of different projects can talk to each other.

It is not an app you install. It is instructions your agent reads and then
grows the system in *your* environment — your names, your language, your
folders, your tools (Claude Code, Codex, T3 Code or plain terminals).

## How to use

Open your AI coding agent (Claude Code, Codex, …) in your home folder and say:

> Read https://github.com/avanturist888/agent-seed — start with SEED.md — and
> grow a steward for me.

The agent will look around, ask you a few questions (name, language, what must
never be touched), create the steward's private home repository, wire the
shared rules into every agent, set up mail, and verify each step with a live
agent.

## What's inside

| | |
|---|---|
| [SEED.md](SEED.md) | step-by-step instructions for the agent doing the setup |
| [PHILOSOPHY.md](PHILOSOPHY.md) | why it is built this way; decides when a step doesn't fit |
| [template/rules/global.md](template/rules/global.md) | shared rules for all agents: four principles, project philosophy, mail |
| [template/ROLE.md](template/ROLE.md) | the steward's own instructions: habits, authority, round, map |
| [skills/philosophy-interview](skills/philosophy-interview/SKILL.md) | how an agent interviews you about a project's "why" |
| [mail/](mail/README.md) | agent-mail: MCP server + CLI + hook, one stdlib-only Python file |

## Where it comes from

Grown in daily use with a steward named Nestor on one person's Windows machine
with ~40 projects under Claude Code and T3 Code. Every principle in
`template/rules/global.md` started as a remark like "why are you asking me
this?" or "did you check, or are you assuming?" — and was sharpened until it
generalized. Your steward will grow the same way: from your remarks.

---

## По-русски

Семя для собственного **мета-агента**: он присматривает за машиной и всеми
проектами. Вместе с ним — **общие правила** для всех ИИ-агентов на машине и
**почта**, чтобы агенты разных проектов могли переписываться.

Это не программа, а инструкции. Ваш агент читает их и выращивает систему в
вашей среде: с вашими именами, языком, папками и инструментами.

Откройте агента (Claude Code, Codex…) в домашней папке и скажите:

> Прочитай https://github.com/avanturist888/agent-seed — начни с SEED.md — и
> вырасти мне мета-агента.

Агент осмотрится и задаст несколько вопросов: имя, язык, что трогать нельзя.
Потом заведёт мета-агенту приватный репозиторий, подключит общие правила всем
агентам и настроит почту. Каждый шаг он проверит на живом агенте. Правила и
шаблоны написаны по-английски, при установке агент переведёт их на ваш язык.

## License

MIT
