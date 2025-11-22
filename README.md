# Traderbot Momentum Skeleton

This repository holds a modular, CSV-first daily-bar trading system scaffold for iterating on pairs and cross-section momentum strategies. The focus is clarity over speed so each component can evolve independently while keeping “one action ↔ one module” symmetry.

## Why this layout?
- **Topic folders under `src/`** align with distinct concerns (analytics, backtesting, config, data, execution, strategies, utils, venues, orchestration). Each can be developed, tested, and owned independently.
- **`actions/` directory** contains tiny scripts (“buttons”) that import exactly one library function. Automation, cron, and humans all trigger workflows the same way.
- **`data/` (top-level)** stores artifacts (`raw/`, `processed/`, `results/`) separate from the ingest code in `src/data/`, reinforcing the CSV contracts and keeping notebooks/reporting simple.
- **`src/orchestration/` + `actions/run_daily_pipeline.py`** provide the daily driver: the orchestrator does the work, the action just parses flags and calls `run_pipeline()`.

For detailed responsibilities, interfaces, CSV schemas, and the phased roadmap, see `docs/ARCHITECTURE.md`.
