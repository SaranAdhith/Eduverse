"""Cross-checks the curriculum, diagnostic blueprint, and BKT params for the
internal consistency every later component assumes (DOC_00 sections 1, 2, 4).

Run as a module to get a human-readable report and a non-zero exit on failure:

    python -m eduverse.validate

This is the gate that proves the data foundation is sound before any engine is
built on top of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .bkt import load_params
from .curriculum import Curriculum
from .diagnostic import Blueprint

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def check(curriculum: Curriculum, blueprint: Blueprint) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors break downstream components; warnings
    are discrepancies worth a human's attention but not fatal."""
    errors: list[str] = []
    warnings: list[str] = []

    # --- curriculum DAG integrity ----------------------------------------
    missing = curriculum.missing_prerequisites()
    for tid, dangling in missing.items():
        errors.append(f"{tid} lists prerequisite(s) not in the graph: {dangling}")

    cycle = curriculum.find_cycle()
    if cycle:
        errors.append("prerequisite cycle: " + " -> ".join(cycle))

    if not missing and not cycle:
        order = curriculum.topological_order()
        # Sanity: every prereq must precede its dependent in the topo order.
        pos = {tid: i for i, tid in enumerate(order)}
        for t in curriculum.topics.values():
            for p in t.prerequisites:
                if pos[p] > pos[t.id]:
                    errors.append(f"topo order places {p} after dependent {t.id}")

    # --- blueprint integrity ---------------------------------------------
    declared = blueprint.items_total
    summed = blueprint.total_items()
    if declared != summed:
        errors.append(
            f"blueprint items_total={declared} but per-tier items sum to {summed}"
        )
    for e in blueprint.entries:
        mix = sum(e.difficulty.values())
        if mix != e.items:
            errors.append(
                f"tier {e.tier}: difficulty mix sums to {mix}, expected {e.items}"
            )
        for anchor in e.anchors:
            if anchor not in curriculum:
                errors.append(f"tier {e.tier}: anchor {anchor} is not a curriculum topic")
            elif curriculum[anchor].tier != e.tier:
                warnings.append(
                    f"anchor {anchor} sits in tier {curriculum[anchor].tier}, "
                    f"listed under blueprint tier {e.tier}"
                )

    # --- cross-document sanity (catches DOC_00's own '48 topics' claim) ---
    n = len(curriculum)
    if n != 48:
        warnings.append(
            f"curriculum has {n} topics; DOC_00 prose says 48. Reconcile the count "
            "before the Block A/B study split (DOC_00 sections 5 & 8)."
        )

    probed = {e.tier for e in blueprint.entries}
    all_tiers = set(curriculum.tiers)
    unprobed = sorted(all_tiers - probed)
    if unprobed:
        warnings.append(
            f"tiers with no diagnostic anchor (by design per DOC_00): {unprobed}"
        )

    return errors, warnings


def main() -> int:
    curriculum = Curriculum.load(DATA_DIR / "curriculum.yaml")
    blueprint = Blueprint.load(DATA_DIR / "diagnostic_blueprint.yaml")
    params = load_params(DATA_DIR / "bkt_params.yaml")  # __post_init__ validates

    errors, warnings = check(curriculum, blueprint)

    print(f"curriculum: {len(curriculum)} topics across {len(curriculum.tiers)} tiers")
    print(f"blueprint:  {blueprint.total_items()} items across {len(blueprint.entries)} tiers")
    print(f"bkt:        L0={params.p_l0} T={params.p_transit} "
          f"guess={params.p_guess} slip={params.p_slip} thr={params.mastery_threshold}")
    print()

    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s) — INVALID")
        return 1
    print(f"\n0 errors, {len(warnings)} warning(s) — data foundation is consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
