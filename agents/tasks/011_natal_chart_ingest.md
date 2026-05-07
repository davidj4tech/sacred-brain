# Task: Per-user natal chart ingest script (done)

## Context
The Hippocampus store keeps text memories under per-user `user_id`s (`david`,
`sam`, `mel`, …). Several agent flows want to surface a user's natal chart as
context — at minimum a "what's my moon sign" lookup, ultimately as input to
downstream tools (e.g. agent-audio-relay's planned media-chooser, which uses
natal placements + daily transits to inform music selection).

There was no ingest path for this yet: the chart had to be hand-typed or
recomputed every time. A small one-shot script that drops a structured chart
plus a handful of search-friendly atomic memories into Hippocampus closes the
gap without committing the project to any astrological feature beyond
"this user's chart is in the store".

## Goal
A single-command CLI that, given a user's birth data, writes 22 memories
(1 canonical full-chart JSON blob, 12 placements including angles, 8 tightest
aspects, 1 element/modality synthesis) under the chosen `user_id`. Re-runnable
(idempotent in spirit — a recompute deletes the old `source` set first).

## Requirements
- Single file: `scripts/natal_to_sacred_brain.py`. Run via the existing
  `/opt/sacred-brain/.venv` (already has `kerykeion`, no requirements bump).
- All memories tagged `metadata.source = "natal-chart-v1"` so the set is
  bulk-deletable on schema changes (DELETE by id; the API has no metadata-filter
  query). Bump to `v2` if the prose shape or atom set changes.
- Required CLI args: `--user-id`, `--name`, `--dob YYYY-MM-DD`, `--time HH:MM`,
  `--place`, `--country` (ISO 3166-1 alpha-2). Modes: `--dry-run` (print
  payloads, no write) or `--post`.
- Reads `HIPPOCAMPUS_URL` / `HIPPOCAMPUS_API_KEY` from env or
  `~/.config/hippocampus.env` — same convention as `sacred-search`.
- Atomic memories must read declaratively and self-contained (e.g. "David's
  natal Moon is in Aquarius at 11°24', in the 7th house. Aquarius is a fixed
  air sign.") so a cold semantic search hit makes sense without surrounding
  context.
- Aspect math uses absolute longitude (`sign_index * 30 + position`), not
  within-sign degrees. Orb tolerance: 6° for major aspects (conjunction,
  sextile, square, trine, opposition).
- Must NOT add a runtime dependency on `kerykeion` to any service — this is a
  one-shot script, not a Hippocampus/Governor feature.

## Suggested Steps
1. Implement chart computation with kerykeion's `AstrologicalSubject`.
2. Build a single canonical JSON blob with subject + ascendant/MC + houses +
   planets + aspects + element/modality synthesis.
3. Emit declarative atomic memories (placements, top-8 aspects by orb,
   synthesis).
4. POST each via `urllib.request` to `${HIPPOCAMPUS_URL}/memories` with
   `X-API-Key`. Print each returned id.

## Validation
- Dry-run round-trip:

      /opt/sacred-brain/.venv/bin/python scripts/natal_to_sacred_brain.py \
        --user-id david --name David --dob 1976-04-22 --time 12:19 \
        --place Melbourne --country AU --dry-run

  Should print 22 numbered payloads, each with a `kind=` line, no errors.
- Post + verify:

      ... --post
      sacred-search "david natal chart full" david 1
      sacred-search "david moon sign" david 3

  The first should return the JSON blob; the second should return the Moon
  placement atom as the top hit.

## References
- `scripts/natal_to_sacred_brain.py` — the script.
- `docs/API.md` — Hippocampus `POST /memories` shape.
- `docs/SACRED_SEARCH.md` — the read CLI; same env file.
- Downstream consumer (planned, separate repo): agent-audio-relay
  `media-chooser` CLI, designed to pull this chart + daily transits to
  inform music selection. The chooser depends only on sacred brain, not on
  any aar-side state.
