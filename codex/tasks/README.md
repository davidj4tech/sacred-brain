# Codex Task Files

Every Codex task captures just enough structure so different agents can pick it up rapidly. Create one Markdown file per task inside this directory using the template below.

## Filename Rules
- Prefix with a three-digit ordering token (e.g., `001`, `002`).
- Follow with a short slug separated by `_` (e.g., `001_mem0_sdk.md`).
- Keep filenames lowercase without spaces to make shell access easier.

## Template
```
# Task: <Short headline>

## Context
Summarize the current state that motivates the work.

## Goal
Describe the user-visible outcome that should exist once the task is complete.

## Requirements
- Bullet list of explicit constraints, success criteria, and any implementation hints.

## Suggested Steps
1. Outline a plausible sequence of work items future agents can follow.

## Validation
List manual or automated checks (tests, commands, verifications) that prove the task is done.

## References
Link to relevant files, docs, issues, or log entries.
```

## Usage Guidance
- Update a task file status inline (e.g., append `(in progress)` or `(done)` to the headline) as work evolves.
- Keep tasks focused; if new discoveries surface, spawn another file instead of overloading one description.
- Reference `SESSION_LOG.md` whenever you create or close a task so continuity is preserved.
