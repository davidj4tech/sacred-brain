# Dreaming (in progress)

Sacred Brain's memory consolidation sweep. Replaces the regex-bucket
heuristics in `mem_policy.consolidate_events` with a weighted multi-signal
score and (eventually) a nightly reflection pass.

The shape is borrowed from OpenClaw's `dreaming` feature, adapted to our
substrate: Hippocampus + SQLite rather than markdown files, explicit scopes,
systemd timers instead of a single cron. Phase names (Light / REM / Deep)
are not exposed — we have one scored pipeline and one reflection step.

Status: scoring + `/promote-explain` + sweep + promote (governor ledger) +
REM reflection shipped. Systemd timer wiring is the remaining step. Full
task spec:
[`agents/tasks/009_dreaming_sweep.md`](../agents/tasks/009_dreaming_sweep.md).

## Scoring

Every candidate memory is scored on six weighted signals summing to 1.0.
Thresholds gate promotion — a memory must clear **all three** gates to
promote.

| Signal              | Weight | Source                                                |
|---------------------|--------|-------------------------------------------------------|
| frequency           | 0.24   | `recall_stats.recall_count`, log-saturated            |
| relevance           | 0.30   | `recall_stats.sum_relevance / recall_count`           |
| query_diversity     | 0.15   | distinct query hashes (cap 20)                        |
| recency             | 0.15   | `exp(-age_days / 14)`                                 |
| consolidation       | 0.10   | distinct UTC days recalled (cap 30)                   |
| conceptual_richness | 0.06   | metadata tag count + scope depth                      |

Gate thresholds (env-tunable):

| Env var                         | Default |
|---------------------------------|---------|
| `MG_DREAM_MIN_SCORE`            | `0.35`  |
| `MG_DREAM_MIN_RECALL_COUNT`     | `2`     |
| `MG_DREAM_MIN_UNIQUE_QUERIES`   | `2`     |

The recall-side inputs (`sum_relevance`, `query_hashes`, `recall_days`) are
populated automatically on every `/recall` hit. No extra wiring needed.

## Explaining a promotion decision

Ask the governor directly:

```bash
curl -s -X POST http://127.0.0.1:54323/promote-explain \
  -H "Content-Type: application/json" \
  -d '{"memory_id":"<id>","user_id":"sam"}' | jq
```

Or use the CLI:

```bash
scripts/sacred-brain-explain <memory_id> --user-id sam
scripts/sacred-brain-explain <memory_id> --json
```

Sample pretty output:

```
memory_id: mem-abc
text:      always use docker compose plugin syntax

score:     0.612   threshold: 0.350
passed:    ✓

signal                    raw    weighted
------------------------------------------
frequency               0.778       0.187
relevance               0.820       0.246
query_diversity         0.600       0.090
recency                 0.867       0.130
consolidation           0.429       0.043
conceptual_richness     0.333       0.020

inputs:
  recall_count:     8
  distinct_queries: 3
  distinct_days:    3
  avg_relevance:    0.820
  age_days:         2.0
  tag_count:        2
  scope_depth:      1
```

## Dry-run sweep

Score every memory for a user and print a pass/fail table. Writes nothing.

```bash
PYTHONPATH=/opt/sacred-brain python scripts/dream_sweep.py \
  --user-id sam --limit 200
```

Flags:

- `--apply` — actually persist `dream_promotions` rows for memories that
  pass the gates (default is dry-run)
- `--reflect` — after scoring (and `--apply`, if set), run the REM
  reflection step: Haiku summarises the last 24h of stream events,
  today's promotions, and the top-recalled memories, and writes a
  narrative entry via `write_dream_entry`. Read-only on the memory
  store. Silently skips when there is nothing to reflect on.
- `--json` — emit JSON instead of the table
- `--min-score`, `--min-recall-count`, `--min-unique-queries` — override gates
- `--limit` — max memories to fetch (default 500)

## The dream_promotions ledger

Hippocampus exposes no PATCH endpoint, so the sweep does not mutate
memories. Instead it records a governor-side ledger in SQLite:

```
dream_promotions(memory_id, last_dreamed_at, dream_count, last_score, last_signals)
```

Two consumers read it:

1. **`/recall` ranking** adds a small `dream_boost = last_score * 0.05`
   to memories dreamed within the last 7 days. Both values are
   configurable via `MG_DREAM_BOOST_WEIGHT` and `MG_DREAM_BOOST_WINDOW_DAYS`.
2. **Auto-prune protection** — the prune script reads `GET /dream_stats`
   and adds those ids to its protected set, same pattern as
   `/recall_stats`. Default protection window is
   `MG_DREAM_PROTECT_DAYS=14`.

`/promote-explain` responses also include `last_dreamed_at` and
`dream_count` so you can see a memory's dreaming history without a
separate lookup.

## Env vars added by Dreaming

| Var                          | Default | Purpose                             |
|------------------------------|---------|-------------------------------------|
| `MG_DREAM_MIN_SCORE`         | `0.35`  | Gate: minimum total score           |
| `MG_DREAM_MIN_RECALL_COUNT`  | `2`     | Gate: minimum recall count          |
| `MG_DREAM_MIN_UNIQUE_QUERIES`| `2`     | Gate: minimum distinct queries      |
| `MG_DREAM_PROTECT_DAYS`      | `14`    | Prune protection window             |
| `MG_DREAM_BOOST_WEIGHT`      | `0.05`  | Weight of dream_boost in `/recall`  |
| `MG_DREAM_BOOST_WINDOW_DAYS` | `7`     | How long a promotion boosts recall  |
| `DREAMS_OUTPUT_PATH`         | —       | Override for `DREAMS.md` path       |
| `MG_ORACLE_ENABLED`          | `1`     | Fold astrology + tarot into REM     |

## REM reflection

The reflection step (`--reflect`) is a single read-only call to
`claude-haiku-4-5-20251001` via LiteLLM. Inputs:

1. Last 24h of `stream_log` JSONL records (path in
   `cfg.stream_log_path` — `var/memory-governor/stream.log`).
2. Every memory promoted in the last 24h (`dream_promotions` rows with
   `last_dreamed_at >= cutoff`).
3. Top-20 memories by `recall_stats.recall_count` across all time.

The system prompt and rubric carry `cache_control: {type: ephemeral}` so
repeated nights hit Anthropic's prompt cache; the per-night data block
does not. Output is 2-4 paragraphs of plain prose, prefixed with YAML
frontmatter (`date`, `promoted_count`, `reflection_model`,
`input_event_count`) and written via `write_dream_entry` to the path
resolved below. REM never mutates the memory store.

## Dream output path resolution

REM writes its narrative entry per sweep to a target resolved as:

1. `DREAMS_OUTPUT_PATH` env var
2. Per-package default (downstream packages pass this in code)
3. Sacred-brain default: `/opt/sacred-brain/var/dreams/`

Behavior by target shape:

- **Path ends in `.md`** → single-file mode. Overwrite the file each run.
  This is the right default for workspace-style installs (one DREAMS.md per
  git repo, committable).
- **Path is a directory** → dated rotation. Writes `YYYY-MM-DD.md` into the
  directory and updates a `latest.md` symlink.

**Mental model: a workspace = its own git repo.** Sacred-brain is a
service, not a workspace, so its dreams go to `var/`. Any repo that wants
dreams about itself sets `DREAMS_OUTPUT_PATH` to its own root and gets a
versionable single file.

## Oracle layer (astrology + tarot)

REM optionally folds a small "Oracle" block into the reflection: a
kerykeion-derived sky snapshot plus a deterministic single-card tarot pull
seeded on `(user_id, UTC date)`. The model is instructed to treat it as
*tone*, never to fabricate memory content to match the omen.

Three astrology modes, picked automatically from the natal record's
precision:

- **`mundane`** (`precision: datetime`) — current sky only. Used when no
  natal date is on file.
- **`transit_partial`** (`precision: date`) — date-only natal: a chart is
  drawn with a noon-UTC stand-in, and slow-planet aspects (Sun, Mercury
  through Pluto) to natal are kept. Moon, Mean/True Node, Ascendant,
  Midheaven, and house-cusp aspects are dropped because they require an
  accurate birth time and location. The oracle block surfaces caveats and
  the YAML frontmatter records `astro_precision: date`.
- **`transit`** (`precision: datetime`) — full natal datetime + location;
  all aspects within 3° orb are eligible.

The dreaming sweep upgrades the precision tier whenever it can: a `none →
date` or `date → datetime` jump from a memory probe is auto-saved and
logged as `oracle.natal_recovered`. Anything below `datetime` also emits
a stream-log event naming the missing fields and the exact
`sacred-brain-oracle set` command to upgrade:

- `oracle.natal_missing` — no date on file; mundane fallback used.
- `oracle.natal_partial` — partial transit chart was drawn; lists the
  fields still missing (`hour`, `minute`, `tz_str`, `lat`/`lng`, …) so
  the operator sees exactly what would sharpen tonight's chart even
  though one was already produced.

**Auto-recovery from memory.** When the dreaming sweep runs and there is
no natal file for the user (or it is incomplete), it probes long-term
memory with queries like `"born"`, `"birthday"`, `"birth time"`,
`"birthplace"`, and parses any hits for date/time/place. If the probe
returns a complete date (year/month/day) it auto-saves the merged record;
otherwise it appends an `oracle.natal_missing` event to the stream log
(included in the next REM data block) listing exactly which fields are
missing and what command will fill them. A successful auto-recovery emits
`oracle.natal_recovered` with the source memory ids.

You can run the same probe manually:

```bash
scripts/sacred-brain-oracle discover sam            # report only
scripts/sacred-brain-oracle discover sam --save     # save if complete
```

Manage natal details with `scripts/sacred-brain-oracle`:

```bash
scripts/sacred-brain-oracle show sam
scripts/sacred-brain-oracle set sam --date 1990-06-15 --time 14:32 \
    --city Portland --nation US --lat 45.52 --lng -122.68 \
    --tz America/Los_Angeles
scripts/sacred-brain-oracle preview sam     # dry-run snapshot
scripts/sacred-brain-oracle rm sam
```

Storage: `<state_dir>/oracle/natal/<user_id>.json`. Disable globally with
`MG_ORACLE_ENABLED=0`. The astrology call is wrapped in try/except — a
broken kerykeion install never blocks the sweep.

## Relation to `/consolidate`

The existing hourly `/consolidate` timer (rule-based keyword bucketing) is
untouched. The Dreaming sweep is additive: a nightly scored layer that
eventually subsumes it. Both can run in parallel indefinitely; we'll fold
the hourly path in once scoring is proven on real data.

## References

- Task spec: [`agents/tasks/009_dreaming_sweep.md`](../agents/tasks/009_dreaming_sweep.md)
- OpenClaw's source: `/opt/openclaw/docs/concepts/dreaming.md`
- Code: `memory_governor/mem_policy.py` (`score_candidate`, `build_candidate_stats`),
  `memory_governor/dream.py` (sweep core + path helpers),
  `memory_governor/rem.py` (REM reflection: gather / build / call / format),
  `memory_governor/store.py` (`recall_stats` aggregates, `dream_promotions`,
  `top_recalled`)
- Systemd: `ops/systemd/sacred-brain-dream.{service,timer}`
  (OnCalendar `03:00`, runs `dream_sweep.py --apply --reflect` per user
  listed in `MG_DREAM_USERS`, default `sam`)
