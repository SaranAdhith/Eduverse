# Eduverse — agent overview

Eduverse is a research prototype: an adaptive Python-learning agent built to run a
within-subject study comparing a **personalized** (LLM-planned) learning path
against a **fixed** (topological) one. This page is the 10-minute orientation.

## Build order (phase = `DOC_0N`)

| Phase | Owns | Where |
|---|---|---|
| 00 | Curriculum + diagnostic data foundation, BKT math | `src/eduverse/`, `data/` |
| 01 | FastAPI scaffold, participants, structured logging | `app/`, `app/modules/participants/` |
| 02 | Knowledge graph + question/diagnostic bank | `app/modules/topics/`, `graph/`, `questions/` |
| 03 | YouTube video curation pipeline | `app/modules/curation/` |
| 04 | Mastery engine (BKT) + diagnostic delivery | `app/modules/mastery/` |
| 05 | Path planner (fixed + personalized) + mastery gate | `app/modules/planner/` |
| 06 | Per-topic content assembly (lesson + video + quiz) | `app/modules/content/` |
| 07 | Participant frontend | `frontend/` (Next.js) |
| 08 | Study instrumentation: assignment, events, export, LLM cache | `app/modules/study/`, `analysis/` |
| 09 | End-to-end seam tests + pilot readiness | `tests/e2e/`, `scripts/validate.py` |

The `src/eduverse/` package is the pure, installable data/BKT library; `app/` is
the runnable FastAPI service (exercised via pythonpath, not pip-installed).

## Data flow: enrollment → completion

1. **Enroll** (`POST /enroll`). A sequential code `P001…` is issued and a sealed
   **study assignment** is drawn from a 4-cell rotation — `block_order` (`AB`/`BA`)
   crossed with which block is personalized vs fixed. Mode is never client-chosen.
2. **Diagnostic** (`/diagnostic/*`). 25 anchor items place the learner. Each answer
   runs one BKT update on its topic and **propagates** to tier siblings, so all 47
   topics get a `mastery` row (cold-start floor at `p_init`).
3. **Path** (`POST /paths`). One `learning_paths` row per block. The server derives
   the mode from the assignment. **Fixed** mode walks the block's topological order;
   **personalized** mode asks Claude to pick the next topic from the mastery frontier
   (cached by `(mastery, candidates)` hash). Creating a path warms the first 3
   content chunks in the background.
4. **Learn a step**. `GET /steps/{id}/content` returns an assembled **chunk**: a
   bridging lesson (markdown), an optional YouTube segment deep-link, and — held
   back — a 5-item gate quiz. Chunks are addressed by `(topic_id, content_version)`
   and cached, so every participant sees an identical chunk for a topic regardless
   of mode (internal validity).
5. **Gate** (`/steps/{id}/gate/*`). The 5-item quiz feeds BKT; the step **passes**
   iff the posterior clears **0.85**. Pass → advance; fail → remediate and retry.
6. **Advance / complete**. When every block topic is passed, the path's
   `completed_at` is set (`path_completed`). The learner then does the **other**
   block under the **other** mode. Two completed blocks = done.

Every meaningful action emits an **event**, dual-written to the `events` table
(durable) and a JSONL log (streaming). `POST /admin/export` packages a
participant's responses, mastery trajectory, path steps, gate attempts, and event
stream into a tarball the `analysis/` notebooks consume.

## Key tables

`participants`, `study_assignments`, `topics` / `topic_prerequisites`,
`questions` / `choices`, `diagnostic_sessions`, `responses` (BKT prior+posterior
snapshot per answer), `mastery` (current vector), `learning_paths` / `path_steps`
/ `gate_attempts`, `content_chunks` / `chunk_quiz_items`, `video_resources` /
`video_segments` / `topic_video_coverage`, `events`, `llm_cache`.

## Study design summary

- **Design**: within-subject crossover, 2 blocks × 2 modes, counterbalanced via a
  4-cell rotation that stays balanced at small N.
- **Blocks** (`app/seeds/blocks.yaml`): A = T2/T3/T6-core (17 topics), B = T4/T5
  (12). Out-of-block prerequisites are treated as pre-mastered.
- **Mastery gate**: posterior ≥ **0.85** (Corbett & Anderson's 0.95 is too tight
  given default-parameter noise).
- **BKT defaults**: `p_init 0.30, p_transit 0.15, p_guess 0.25, p_slip 0.10`;
  update = Bayes posterior then a learning transition. It is the single source of
  truth in `app/modules/mastery/bkt.py`.
- **Reproducibility**: `temperature=0` everywhere; every Claude call is cached in
  `llm_cache` keyed by `(model, prompt_hash)` for replay during analysis.

## Proving it works

`make e2e` runs the seam tests (full participant run, mode determinism, graph
consistency, BKT invariants, content isolation, admin gating, performance smoke).
`make pilot-check` runs eight readiness checks (schema, DAG, diagnostic mix,
coverage, content pre-flight, BKT determinism, assignment balance, logging
dual-write) against a throwaway seeded DB and exits non-zero on any failure.
