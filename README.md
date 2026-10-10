# Poketrix

A real-time probabilistic decision engine for competitive Pokémon: deterministic math for anything
with an exact answer, probabilistic ML for genuine uncertainty, retrieval for knowledge questions —
and an LLM that only ever *explains* already-computed numbers.

**Current scope:** Generations 1–4, competitive ladder (Showdown) first. Later gens are an extension.

## Build order

| # | Phase | Status |
|---|-------|--------|
| 0 | Repo scaffold + checkpoint workflow | done |
| 1 | Shared Pydantic schemas (gen-aware) | done (cp-01) |
| 2 | Dex data layer (Gens 1–4 species/moves snapshot) | done (cp-02) |
| 3 | Deterministic Math layer (type chart, stats, damage) — Gen 4 first, then 3 → 2 → 1 | Gen 4 done (cp-03a, cp-03b); Gens 3, 2, 1 built, awaiting review — see docs/PROGRESS_TRACKER.md |
| 4 | Bayesian set uncloaker (Showdown Gen 1–4 Random Battle set pools as priors) | |
| 5 | Showdown battle-log parser → `GameState` | |
| 6 | Orchestrator (plain state machine first) + synthesis guardrails | |
| 7 | XGBoost action predictor (needs replay data) | |
| — | Knowledge graph / RAG, vision ingestion | deferred |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -e ".[dev]"
pytest
```

See `docs/CHECKPOINTS.md` for the branch/tag workflow.
