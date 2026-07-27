# Pilot readiness checklist (DOC_09 §4)

Every box must be checked — or carry a named owner in parentheses — before the
`pilot-ready` branch is cut. CI fails the `pilot-ready` branch if any unchecked,
unowned item remains.

## Code & infra
- [ ] All Alembic migrations applied on the pilot DB (`make migrate`)
- [ ] `make pilot-check` passes (owner: eng)
- [ ] `make e2e` passes (owner: eng)
- [ ] LLM model versions pinned in `.env` (no floating aliases); documented in README
- [ ] `LLM_CACHE_ENABLED=true` on the pilot backend (DOC_08 §8 reproducibility)
- [ ] Frontend deployed to a stable URL accessible from participant devices
- [ ] Backend deployed; HTTPS configured
- [ ] `ADMIN_TOKEN` set to a strong secret on the pilot backend

## Study materials
- [ ] Consent text finalised and approved by department (owner: PI)
- [ ] Block A and Block B topic lists matched for difficulty (independent review)
- [ ] Diagnostic items reviewed by a Python instructor for correctness
- [ ] At least 3 segments per core topic in T0–T5, or a fallback registered
      (`make pilot-check` reports fallback reliance; run curation to reduce it)

## Process
- [ ] Recruitment plan written (owner: PI)
- [ ] Per-participant time budget estimated and documented
- [ ] Researcher contact channel visible in the UI (email/phone)
- [ ] Backup process for participants who get stuck

---

_This file is hand-edited. The full participant flow, block-and-mode balance, BKT
invariants, content isolation, and admin gating are all enforced automatically by
`tests/e2e/` and `scripts/validate.py`; the boxes above cover the human and
deployment steps those checks can't._
