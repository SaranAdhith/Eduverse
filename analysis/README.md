# Analysis (DOC_08 §7)

The analysis pipeline that backs the paper's results section. It is deliberately
decoupled from the backend: the **only** contract is the export tarball produced
by `POST /admin/export` / `POST /admin/export-all` (see
`app/modules/study/export.py`). `lib/load.py` parses that tarball; everything
downstream works on DataFrames.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab
```

## Layout

- `lib/load.py`    — tarball → tables / DataFrames (stdlib core, pandas layer).
- `lib/metrics.py` — learning gain, time-to-mastery, AUC, Brier, Cohen's d.
- `lib/plots.py`   — paper-quality matplotlib (no seaborn defaults).
- `notebooks/`     — one notebook per results section, stubbed with the markdown
  structure of the paper:
  - `01_descriptives.ipynb`    — N, dropout, time-on-study, items answered.
  - `02_primary_analysis.ipynb`— per-block learning gain, paired t-test /
    Wilcoxon, effect size, 95% CI.
  - `03_bkt_predictive.ipynb`  — leave-last-out AUC + Brier for BKT predictions.
  - `04_qualitative.ipynb`     — coding of free-text preference responses.

## Running before the pilot

The notebooks must run end-to-end on a **small fixture export** (a single
synthetic participant) before real data lands, so the pipeline is proven. Point
`EXPORT_PATH` at a tarball produced by the export endpoint and run all cells.
