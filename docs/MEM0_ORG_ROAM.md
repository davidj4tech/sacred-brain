# Mem0 ↔ Org-roam / Denote Bridge

This bridge keeps Hippocampus memories available as Org/Denote notes so you can
index them with org-roam, and it can pull hand-written Zettelkasten notes back
into Mem0.

## Format
- Files live under `data/memories-denote/` (configurable via `[notes].notes_dir`).
- Denote-friendly name: `YYYYMMDDThhmmss--slug__mem0.org`
- Header example:

```
#+title: Memory: meeting-notes
#+date: 2025-01-10T12:34:56
:PROPERTIES:
:ID: 123e4567-e89b-12d3-a456-426614174000
:MEM0_ID: 123e4567-e89b-12d3-a456-426614174000
:USER: alice
:SOURCE: mem0
:CREATED: 2025-01-10T12:34:56
:TAGS: product roadmap
:END:

Body text stored in Mem0...
```

Org-roam will index the directory; Denote users can edit the notes normally.

## Commands

From the repo root:

```bash
# Export Mem0 -> Org/Denote
python scripts/mem0_org_sync.py export --dir data/memories-denote --user alice --limit 100

# Import Org/Denote -> Mem0 (adds MEM0_ID when missing)
python scripts/mem0_org_sync.py import --dir data/memories-denote --user alice
```

Arguments:
- `--dir`: override the target/source directory (defaults to `[notes].notes_dir`).
- `--user`: filter exports to a user_id, or use as the default user_id when importing.
- `--limit`: cap export volume (useful for quick iterations).

## Behaviour
- Export is idempotent: if a note already has `:MEM0_ID:`/`:ID:`, it is
  overwritten in place; otherwise a new file is created with a Denote-style
  filename.
- Import only acts on notes without a `:MEM0_ID:`/`:ID:`. After pushing to
  Mem0, it writes those properties back so subsequent imports skip the note.
- Metadata: all Org properties except `ID`, `MEM0_ID`, `USER`, and `SOURCE`
  are forwarded into Mem0 metadata; `:TAGS:` becomes a space-separated string.

## Config
- `config/hippocampus.toml`:
  - `[notes].notes_dir`: directory for Denote/Org files (default
    `data/memories-denote`).
  - `[notes].default_user`: fallback user_id when importing notes.
- The Mem0 backend honours `[mem0]` settings (remote/SQLite/in-memory); export
  uses the new `Mem0Adapter.list_memories` helper.

## Gotchas / next steps
- Provider dependencies for Agno models (openai/ollama) are not installed by
  default; install them if you want the Agno agent to call those models.
- If using a remote Mem0, ensure the SDK exposes `get_all` or `search` supports
  empty queries; otherwise export may return limited results. Extend
  `Mem0RemoteClient.list_memories` if your backend needs a different call.
