# CLAUDE.md

Project guidance for Claude Code. Read the relevant `docs/` file before changing that area of the codebase.

## Project

Norsk Tipping (NT) prediction engine for Tippekupongen. Streamlit web app + CLI tool. Blends bookmaker odds with API-Football stats and NT public tip percentages to recommend coupon picks across four strategies (Safe/Balanced/Value/Jackpot).

## Commands

```bash
# App
streamlit run app.py         # Streamlit UI (primary; installed via Anaconda)
python main.py               # CLI tool (no external deps)
# python tests/test_week23.py  # Playwright end-to-end test (requires Playwright)

# Data sync
python sync.py --daily            # fetch NT + odds + enrichment + validate (idempotent)
python sync.py --refresh-coupons  # force-refresh at start of week
python sync.py --validate         # integrity checks (24 checks)
python sync.py --status           # show current week's DB contents

# Model verification — run all 4 before placing coupon
python verify_model.py --strategy safe
python verify_model.py --strategy balanced
python verify_model.py --strategy value
python verify_model.py --strategy jackpot
python verify_model.py --strategy balanced --omsetning 15000000
```

Log output goes to `logs/`. Streamlit is installed via Anaconda (`C:\Users\kimme\anaconda3`).

## Session Start Checklist

1. Read CLAUDE.md — confirms what is built; do not re-implement completed phases.
2. `python sync.py --validate` — confirm DB is clean (24 checks).
3. `python sync.py --status` — confirm correct week/coupons in DB.
4. Run all four strategies in `verify_model.py` — confirm pipeline consistency.
5. Agree on scope before writing any code.

Do not assume prior conversation context carries over. Always re-derive current state from the code and database.

## Current Phase

**Phase 8 — Historical evaluation and backtesting.**

- 8A: Compare saved coupon predictions vs actual outcomes; hit rate, cover rate, strategy comparison.
- 8B: Model calibration — Brier score, log-loss per fixture and odds source.
- 8C: Payout tracking — actual NT payouts vs simulator median; PVR predictive value.

See `docs/roadmap.md` for completed phases and future roadmap.

## Architecture

**Entry points:**
- `app.py` — Streamlit web UI (single file; all UI + CSS)
- `main.py` — CLI tool (no external deps)
- `sync.py` — data ingestion + maintenance CLI
- `verify_model.py` — pipeline verification report (accepts `--strategy` and `--omsetning`)

**Analysis pipeline** (shared by app.py, Kampanalyse, Statistikk, coupon generation):
```
decimal odds
  → analysis/probability.py   normalise odds → prob_h/u/b
  → analysis/model.py         bookmaker prior + AF stats adjustment + CDS
  → analysis/classifier.py    classify match (banker/standard/half_cover/full_cover/uncertain)
  → analysis/optimizer.py     two-stage strategy-aware search for (n_full, n_half)
```

`Match` in `models/match.py` carries odds in and probabilities + classification out (mutated in place).

**Key analysis modules:**
- `analysis/strategy.py` — StrategyConfig + STRATEGIES dict (safe/balanced/value/jackpot)
- `analysis/pool_value.py` — compute_value_index, compute_p_win, compute_pool_value_ratio, simulate_payout
- `analysis/estimated_prior.py` — fallback H/U/B when no bookmaker odds (NT expert 60% + stats 40%)
- `data/loader.py` — SQLite (preferred) or flat-file `data/coupon_weekNN_YYYY.py` (fallback)

**Database:** SQLite via `db/connection.py`. Key tables: `fixtures`, `coupons`, `coupon_fixtures`, `odds`, `odds_snapshots`, `coupon_predictions`, `match_results`, `coupon_evaluations`, `fixture_stat_enrichment`, `fixture_estimated_prior`.

**Streamlit pages:**
| File | Page |
|---|---|
| `app.py` | Main — coupon selector, analysis table, EV panel, strategy comparison (Lagre kupong) |
| `pages/1_Team_Review.py` | Team Review |
| `pages/2_Results.py` | Resultater — enter scores |
| `pages/3_History.py` | Historikk — hit rate, cover rate, CLV |
| `pages/4_Odds_Movement.py` | Odds Movement |
| `pages/5_Statistikk.py` | Statistikk — per-fixture model breakdown |

## Critical Rules

- **Single pipeline:** `process_match() → run_model() → classify_match() → optimize_coupon()` is used identically in app.py, Statistikk page, and verify_model.py. Do not branch it.
- **Bookmaker dominance:** bookmaker prior always has ≥87% weight. AF stats can adjust by at most ±`_MAX_ADJ` (defined in `analysis/model.py`).
- **Do not add new strategies or change strategy parameters** without explicit instruction.
- **Do not implement Elo, xG, or additional AI models** without explicit instruction.
- **estimated_prior is not bookmaker odds** — never write to `odds` or `odds_snapshots`. Validate check 24 enforces zero overlap.
- **CLV uses real bookmaker odds only** — `odds_snapshots` must only contain real bookmaker (Pinnacle etc.) data.
- **Model probabilities in `Match` are read-only** — strategy and optimizer never write to them.
- **Streamlit CSS:** Streamlit ≥1.40 renamed `data-testid="column"` → `"stColumn"`. Target both. Use `components.html()` for complex dynamic HTML (not `st.markdown`); CommonMark exits HTML blocks on blank lines.

## Detailed Documentation

Read the relevant doc before changing that area of the codebase:

| File | Contents |
|---|---|
| `docs/model_architecture.md` | Unified prediction engine, bookmaker prior, AF stats blend, estimated prior, CDS, value_h/u/b, odds source priority, pool value metrics (P(12/12), PVR, Poolverdi, VI, e_winners) |
| `docs/strategy_system.md` | Safe/Balanced/Value/Jackpot — objectives, composite score formulas, shape objectives, halvdekk substitution, optimizer math, strategy invariants |
| `docs/payout_simulator.md` | Phase 7 Monte Carlo simulator, corrected denominator (+1 not +n_rows), Poisson variance, payout percentiles, e_winners, EV panel UI structure |
| `docs/data_pipeline.md` | NT API endpoint change (2026-06), AF enrichment, odds fallback order, sync.py commands reference, DB tables, weekly workflow |
| `docs/roadmap.md` | Completed phases (1–7), Phase 8 scope, current architecture + code map, Streamlit pages, known limitations, future roadmap |
