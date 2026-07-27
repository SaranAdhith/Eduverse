# Eduverse

**An adaptive Python-learning agent — MSc research prototype.**

Eduverse diagnoses a learner, tracks per-topic mastery with Bayesian Knowledge
Tracing, and routes them through a prerequisite-constrained curriculum of 47
Python topics. It exists to run a **within-subject crossover study** comparing a
*personalized* (LLM-planned) learning path against a *fixed* (topological) one —
so the same components serve both arms and only the planner's `mode` differs.

```
enroll → diagnostic (25 items) → BKT mastery vector → path (block 1)
   → per-topic chunk: lesson + video segment + 5-item gate quiz
   → gate posterior ≥ 0.85 ? advance : remediate
   → block 1 complete → block 2 under the *other* mode → done
```

---

## Table of contents

- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [API surface](#api-surface)
- [Study design](#study-design)
- [Video curation](#video-curation)
- [Testing & CI](#testing--ci)
- [Common tasks](#common-tasks)
- [Research notes](#research-notes)

---

## Quick start

**Requirements:** Docker, [uv](https://docs.astral.sh/uv/) (provisions Python
3.11 automatically), Node 20 + pnpm 10 for the frontend.

### Backend

```bash
cp .env.example .env     # works as-is for a local demo — no API keys required
make install             # uv venv + runtime & dev deps
make db-up               # Postgres 16 + pgvector via docker compose
make migrate             # alembic upgrade head
make seed                # load 47 topics, prerequisites, 25 diagnostic items
make dev                 # uvicorn app.main:app --reload  →  http://localhost:8000
```

`GET /health` should return `{"status": "ok", "db": "ok"}`.

### Frontend

```bash
cd frontend
cp .env.local.example .env.local     # NEXT_PUBLIC_API_URL=http://localhost:8000
pnpm install
pnpm dev                             # → http://localhost:3000
```

Open <http://localhost:3000>, click through **Enroll**, and you get a complete
run: diagnostic → dashboard → lesson → gate quiz → next topic.

> **No Anthropic API key needed for the demo.** With `ANTHROPIC_API_KEY` unset
> (and `ENV != test`), `app/offline_llm.py` swaps in a deterministic offline
> synthesizer that produces valid lessons, quizzes, and planner decisions. Set a
> real key to use Claude for lesson authoring and personalized sequencing.

---

## How it works

### 1. Enrollment seals the study assignment

`POST /enroll` issues a sequential code (`P001`, `P002`, …) and draws a **sealed
assignment** from a 4-cell rotation: `block_order` (`AB`/`BA`) crossed with which
block runs personalized vs fixed. The mode is **never client-chosen** — the
server derives it, and a mismatched client claim gets a `409`.

### 2. The diagnostic places the learner

25 anchor items (`GET /diagnostic/items`, answer keys withheld) are scored one at
a time. Each answer runs a **BKT update** on its topic and **propagates to tier
siblings**, so all 47 topics end up with a `mastery` row rather than only the 25
that were directly probed. Untouched topics cold-start at `p_init`.

### 3. The planner picks the next topic

`POST /paths` creates one `learning_paths` row per block.

- **fixed** — walks the block's deterministic topological order (Kahn, tie-broken
  by `(tier, display_order, id)`). Mastery is ignored for routing.
- **personalized** — asks Claude to choose the next topic from the **mastery
  frontier** (topics whose prerequisites are satisfied), with the response cached
  by a `(mastery, candidates)` hash and clamped to the legal candidate set.

Creating a path warms the first three content chunks in the background.

### 4. Content is assembled once, shared by everyone

`GET /steps/{id}/content` returns a **chunk**: a bridging markdown lesson, an
optional deep-linked YouTube segment, and a 5-item gate quiz (held back until the
gate opens). Chunks are addressed by `(topic_id, content_version)` and cached, so
**every participant sees an identical chunk for a given topic regardless of
mode** — that isolation is what makes the mode comparison internally valid.

### 5. The gate decides advancement

The 5-item quiz feeds BKT; the step **passes iff the posterior clears 0.85**.
Pass → advance (and pre-generate the newly unlocked topic's content). Fail →
remediate and retry. When every topic in the block passes, `completed_at` is set
and the learner moves to the other block under the other mode.

### 6. Everything is instrumented

Every meaningful action emits an **event**, dual-written to the `events` table
(durable) and a JSONL log (streaming). `POST /admin/export` packages a
participant's responses, mastery trajectory, path steps, gate attempts, and event
stream into a tarball that the `analysis/` notebooks consume.

---

## Project layout

```
data/                        # DOC_00 source-of-truth YAML
  curriculum.yaml            #   47-topic prerequisite DAG
  diagnostic_blueprint.yaml  #   25-item placement blueprint
  bkt_params.yaml            #   BKT cold-start defaults

src/eduverse/                # pure, installable library (no DB, no network)
  models.py  curriculum.py  bkt.py  diagnostic.py  validate.py

app/                         # runnable FastAPI service
  main.py                    #   app factory, lifespan, CORS, /health, request-id mw
  config.py  logging.py  db.py  deps.py
  offline_llm.py             #   keyless deterministic Claude stand-in
  modules/
    participants/            #   enroll / resume, X-Participant-Code identity
    topics/  graph/          #   47-topic DAG: prerequisites, frontier, topo order
    questions/               #   diagnostic bank + delivery
    curation/                #   YouTube → transcript → Claude segments → embeddings
    mastery/                 #   BKT engine (bkt.py is the single source of truth)
    planner/                 #   fixed + personalized path planning, mastery gate
    content/                 #   per-topic chunk assembly + cache
    study/                   #   assignment rotation, events, admin export, llm_cache
  seeds/                     #   topics / prerequisites / diagnostic_items / blocks /
                             #   youtube_channels YAML + idempotent loader CLI

frontend/                    # Next.js 14 participant UI (App Router, Tailwind, RQ)
  src/app/                   #   enroll, resume, diagnostic, dashboard, learn, gate
  src/components/            #   MasteryBar, McqQuiz, VideoSegment, LessonMarkdown…
  src/lib/                   #   api client, react-query hooks, zustand store

migrations/                  # Alembic
tests/                       # unit + integration; tests/e2e/ = seam tests
scripts/validate.py          # `make pilot-check` — 8 readiness checks
analysis/                    # stdlib-only notebooks + helpers over exported data
docs/AGENT_OVERVIEW.md       # 10-minute orientation
PILOT_READINESS.md           # human/deployment checklist, gated in CI
```

The project is built in phases (`DOC_0N`); `docs/AGENT_OVERVIEW.md` maps each
phase to the directory that owns it.

---

## Configuration

Copy `.env.example` → `.env`. Every variable is read by `app/config.py`.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://eduverse:eduverse@localhost:5432/eduverse` | matches `docker-compose.yml` |
| `ANTHROPIC_API_KEY` | — | unset ⇒ deterministic offline LLM fallback |
| `ANTHROPIC_MODEL_REASONING` | `claude-opus-4-7` | lesson authoring + personalized planning |
| `ANTHROPIC_MODEL_FAST` | `claude-sonnet-4-6` | lighter-weight calls |
| `YOUTUBE_API_KEY` | — | required only to run the curation pipeline |
| `VOYAGE_API_KEY` | — | `voyage-3` embeddings; blank ⇒ offline embedder |
| `EMBEDDING_PROVIDER` | `voyage` | `voyage` \| `local` \| `hash` |
| `LLM_CACHE_ENABLED` | `true` | cache every Claude call for replayable analysis |
| `ADMIN_TOKEN` | — | guards content preview/regenerate and `/admin/export*` |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated browser origins |
| `ENV` | `dev` | `dev` \| `test` \| `study` |

**Pin model versions for a study run.** Both model variables must name concrete
versions, never floating aliases — reproducibility depends on it, and
`PILOT_READINESS.md` gates on it.

---

## API surface

All participant endpoints require an `X-Participant-Code` header (401 if missing
or unknown), resolved by the `get_participant` dependency.

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{status, db}` |
| POST | `/enroll` | `{consent_given}` → `{code, id}`; 400 if consent false |
| POST | `/resume` | `{code}` → participant + `block_order`; 404 if unknown |
| GET | `/topics`, `/topics/{id}` | paginated list; single topic + prerequisites |
| GET | `/graph?is_core_only=` | `{nodes, edges}` — 47 nodes, or 38 core-only |
| GET | `/diagnostic/items` | 25 items in order, **no answer keys** |
| POST | `/diagnostic/start` | opens a diagnostic session |
| POST | `/diagnostic/answer` | scores an answer, runs BKT + tier propagation |
| POST | `/diagnostic/complete` | closes the session, finalises the mastery vector |
| GET | `/mastery` | current 47-topic mastery vector |
| POST | `/paths` | create the block's path; mode derived server-side (409 on mismatch) |
| GET | `/paths/current` | active path: steps, statuses, progress |
| POST | `/paths/{path_id}/advance` | move to the next step once the gate passes |
| GET | `/steps/{step_id}/content` | assembled chunk (lesson + segment; quiz withheld) |
| POST | `/steps/{step_id}/gate/start` | opens the 5-item gate quiz |
| POST | `/steps/{step_id}/gate/submit` | scores, runs BKT, pass iff posterior ≥ 0.85 |
| POST | `/events/chunk_view`, `/events/idle` | frontend engagement telemetry |
| GET | `/topics/{id}/content/preview` | admin content preview; `X-Admin-Token` |
| POST | `/topics/{id}/content/regenerate` | admin chunk rebuild; `X-Admin-Token` |
| POST | `/admin/export`, `/admin/export-all` | tarball for analysis; `X-Admin-Token` |

---

## Study design

- **Design** — within-subject crossover, 2 blocks × 2 modes, counterbalanced by a
  4-cell rotation that stays balanced at small N.
- **Blocks** (`app/seeds/blocks.yaml`) — **A** = T2/T3/T6-core (17 topics),
  **B** = T4/T5 (12 topics). Out-of-block prerequisites are treated as
  pre-mastered so a block is self-contained.
- **Mastery gate** — posterior ≥ **0.85**. Corbett & Anderson's classic 0.95 is
  too tight given default-parameter noise at this scale.
- **BKT defaults** — `p_init 0.30`, `p_transit 0.15`, `p_guess 0.25`,
  `p_slip 0.10`. The update is a Bayes posterior followed by a learning
  transition; `app/modules/mastery/bkt.py` is the single source of truth.
- **Reproducibility** — `temperature=0` everywhere, and every Claude call is
  cached in `llm_cache` keyed by `(model, prompt_hash)` for exact replay during
  analysis.

---

## Video curation

A batch pipeline that, per topic, finds allow-listed YouTube videos, fetches
their **public captions**, asks Claude to slice each transcript into timestamped
sub-topic segments, embeds them, and stores everything with per-topic coverage
tracking.

```bash
make seed-channels                 # load + verify the channel allow-list
make curate ARGS="--topic T0.1"    # curate one topic end-to-end (uses quota)
make curate ARGS="--tier 5"        # curate a whole tier
make curation-status               # coverage report grouped by tier
```

**Legal/ethical posture.** Search and metadata come from the **YouTube Data API
v3** (respect the daily quota). Captions come from `youtube-transcript-api` — the
same public tracks YouTube serves every viewer. **No video or audio is ever
downloaded.** Search is always scoped to `channelId`s from a vetted allow-list;
there is no open search.

**Graceful degradation.** Quota exhaustion aborts cleanly; caption-less videos
are recorded and skipped, never faked; an unparseable Claude response is retried
once then skipped; embedding failures back off then skip the segment. A topic
that ends with zero segments is marked `no_content` so content assembly falls
back to a fully Claude-generated lesson — **no topic ever becomes a curriculum
dead-end.** Curation tests run fully offline with mocked clients.

---

## Testing & CI

```bash
make test          # full pytest suite
make e2e           # end-to-end seam tests
make pilot-check   # 8 readiness checks against a throwaway seeded DB
make lint          # ruff check + mypy (strict on app/)
```

The **seam tests** (`tests/e2e/`) cover a full participant run, mode determinism,
graph consistency, BKT invariants, content isolation across modes, admin gating,
and a performance smoke test. **`make pilot-check`** verifies schema, DAG
acyclicity, diagnostic mix, video coverage, content pre-flight, BKT determinism,
assignment balance, and logging dual-write — exiting non-zero on any failure.

CI (`.github/workflows/ci.yml`) runs the backend job (lint → migrate → seed →
unit → e2e → pilot-check) against a live pgvector service container, plus a
frontend job (typecheck → lint → build). On the `pilot-ready` branch an extra job
fails the build if `PILOT_READINESS.md` still has unchecked, unowned items.

---

## Common tasks

```bash
make install                 # uv sync --extra dev
make db-up / db-down         # Postgres 16 + pgvector
make migrate                 # alembic upgrade head
make revision m="add foo"    # autogenerate a migration
make seed / seed-clear       # load / truncate the catalog (clear blocked in study)
make dev                     # uvicorn with autoreload
make format                  # ruff format + autofix
make all                     # migrate seed test lint
```

The `src/eduverse/` library also runs standalone with no database:

```bash
PYTHONPATH=src python -m eduverse.validate            # cross-document consistency
PYTHONPATH=src python -m unittest discover -s tests   # data-layer tests
```

---

## Research notes

**47 topics, not 48.** DOC_00's prose says "48 topics" but its tier tables
enumerate 47. Per the "topic table is the source of truth" rule, **47 is
canonical**: the seed data, `GET /graph`, and the tests all use 47 (38 core), and
the Block A / Block B split is built against that.

**Why the two conditions share everything.** Both arms use the same diagnostic,
the same BKT engine, the same cached content chunks, and the same 0.85 gate. The
*only* difference is how the next topic is chosen. Anything else would confound
the comparison.

---

## License

Research prototype, released for academic reference. No warranty.
