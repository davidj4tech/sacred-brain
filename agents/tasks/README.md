# Agent Task Files

One Markdown file per focused unit of work. Any agent (Codex, Claude Code, OpenCode, Aider, human) can pick one up, implement it, and mark it done.

Historical Codex-era tasks live at `codex/tasks/001`–`009`. This directory (`agents/tasks/`) is the canonical home for all new tasks.

## Filename rules

- Three-digit prefix (`001`, `002`, …). Continue the numbering in this directory; don't restart.
- Short lowercase slug, underscores: `001_recall_extends_life.md`.
- One PR's worth of work per file. If scope creeps, spawn a new file rather than widening an existing one.

## Template

```
# Task: <Short headline>

## Context
Current state that motivates the work. Link to the design doc or section.

## Goal
The user-visible (or operator-visible) outcome once this task is merged.

## Requirements
- Explicit constraints, success criteria, API shape, behavioural guarantees.
- Call out what must NOT change (backwards-compat, wire format, etc.).

## Suggested Steps
1. A plausible sequence. Agents may deviate — this is guidance, not a script.

## Validation
- Manual commands and/or automated tests that prove the task is done.
- Include the exact curl / pytest invocations where useful.

## References
- Files the work will touch.
- Design doc section(s) being implemented.
- Related prior tasks.
```

## Status tracking

Update the headline inline as work progresses:

- `# Task: Recall extends life` — pending
- `# Task: Recall extends life (in progress)` — being worked on
- `# Task: Recall extends life (done)` — merged

No external tracker needed. `git log agents/tasks/` is the audit trail.

## Tips

- Keep Context and Goal ≤ 5 lines each. Requirements do the heavy lifting.
- If a task would take more than ~500 lines of diff, split it.
- Reference the *design doc section*, not a screenshot of it. The doc stays authoritative.
- Don't encode agent-specific tooling in the task body. Say "run the test suite", not "open the Codex Run panel".
