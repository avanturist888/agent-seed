---
name: philosophy-interview
description: Interview the owner about a project's philosophy — why it exists, what matters most and what is sacrificed for it — and write the result where the project keeps its rules. Use when a project has no philosophy (or it turned out incomplete or outdated), when the owner says "interview", "project philosophy", "let's figure out why this project exists", or when a decision can be checked against nothing but habit.
---

# Project philosophy interview

A philosophy is what decisions are derived from: architecture, interface,
texts, trade-offs. It answers **why** the project exists and **what is
sacrificed for the main thing**. Rules, structure and plans are not yet a
philosophy: "how it is built", "what must not be touched" and "what we do next"
follow from it but do not replace it.

## Before the first question

1. Find what already exists: `CLAUDE.md`, `AGENTS.md`, README, docs, the
   project's memory. A detailed instruction file full of mechanisms and bans is
   easy to mistake for a philosophy — check whether it has "why" and "what we
   sacrifice".
2. Build a hypothesis from the code, documents, commit history and what the
   owner has already said. Come with it, not with a blank page: it is easier for
   the owner to correct a wrong draft than to compose from scratch.

## How to ask

Go down the layers, one per turn:

1. **Why the project, and for whom** — what pain it removes, what was there
   before.
2. **What matters most, and what we sacrifice for it** — what yields in a
   conflict.
3. **Principles** — what follows for decisions.
4. **How to check a decision** — a measure that shows whether a decision is
   right.

Test every question: **will the answer change how we decide, or only what we
will do?** The second is a question about plans — don't ask it.

- Bad (plans): which features are needed, will there be users, which
  integrations to add.
- Bad (mechanisms): "is this filter/ban in the code a value or a compromise?"
  — the structure follows from the philosophy, not the other way round.
- Bad (confirm a list): "do you agree with principles 2–4?" — show them in a
  draft instead; the owner will correct it.
- Good (philosophy): what counts as a defect; what yields when X runs into Y;
  what you will never give up.

During the interview:

- 2–3 questions per turn, not a questionnaire.
- Restate the owner's answer as one clear sentence and derive a **measure** from
  it — a check that can be applied to any decision.
- Immediately apply the measure to a real recent decision of the project: where
  it confirms what was done and where it says it was done wrong. This tests the
  wording: if the measure distinguishes nothing, it is empty.
- Separate values from current constraints: a ban the owner plans to lift is a
  compromise, not a principle.
- A remark from the owner during the interview (wrong focus, wrong question) —
  correct course first, then continue.

## Result

1. A draft — short, in sections:
   - **Why** — one or two sentences;
   - **Main thing** — what is placed above the rest;
   - **What we sacrifice** — what yields, and when;
   - **Principles** — consequences for decisions;
   - **Checking a decision** — questions that serve as measures.
2. The owner approves it. Until then, do not record it as a rule.
3. Write it where the project keeps its rules (usually the first section of the
   project's instruction file) and commit by the project's rules.
4. Go through recent decisions and current mechanisms with the new measure:
   whatever contradicts it — a list to the owner with a proposal of what to
   change.
