# CLAUDE.md

Project guidance for Claude Code. Read the relevant `docs/` file before changing that area of the codebase.

## Project

Norsk Tipping (NT) prediction engine for Tippekupongen. Streamlit web app + CLI tool. Blends bookmaker odds with API-Football stats and NT public tip percentages to recommend coupon picks across four strategies (Safe/Balanced/Value/Jackpot).

## Product Philosophy

**TippeQpongen is a coupon optimization product.**

The user's primary job is: *"Tell me what to fill in on my coupon this week, and give me a reason to trust it."*

- The **coupon** is the product.
- The **analysis** is the justification.
- The **optimizer** is the engine.
- **Crowd disagreement** is the source of alpha.

### What the metrics are

CDS, PVR, NT public tip percentages, bookmaker probabilities, model adjustments, and payout simulations are not the product. They are evidence used to justify the recommended coupon. No feature, page, or metric should become an end in itself.

### Product vs. differentiator

| | |
|---|---|
| **Product** | A coupon optimizer that recommends marks and coverage structures based on budget, probability, and expected value. |
| **Differentiator** | The optimizer gains edge by incorporating crowd disagreement (CDS), pool value (PVR), public tip percentages, and model adjustments over the bookmaker baseline. |

### Evaluation rule for all frontend changes

Before implementing any UI, UX, or feature change, ask:

> Does this help the user understand, trust, or act on the recommended coupon?

If no, it is analysis for its own sake. Defer or remove it.

### Invariants

- The optimizer remains the center of the product.
- The coupon remains the primary output.
- Analysis exists to explain optimizer decisions, not to replace them.
- Statistics should support decisions, not become the product itself.
- "Where the crowd is wrong" is the differentiator and the reason to trust the coupon — it is not the product itself.

## Commands

```bash
# App
streamlit run app.py         # Streamlit UI (primary; installed via Anaconda)
python main.py               # CLI tool (no external deps)

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

# Evaluation pipeline (Phase 8A)
python evaluate.py --week 24 --year 2026   # evaluate one week
python evaluate.py --all                   # evaluate all saved coupons
python evaluate.py --status                # show which coupons have/need results
python evaluate.py --week 24 --year 2026 --fetch   # also pull results from API-Football
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

- 8A: ✅ Complete. Automated evaluation pipeline live: `evaluate.py`, `db/evaluation.py`, frozen snapshot fields in `coupon_predictions`, `coupon_save_snapshot` table, `pick_evaluations` table, History page with 6 sections.
- 8B: Model calibration — Brier score, log-loss per fixture and odds source.
- 8C: Payout tracking — actual NT payouts vs simulator median; PVR predictive value.

**Evaluation baseline:** Week 24/2026 Midtuke is the first coupon under the current model philosophy (CDS-driven, crowd-disagreement-first). All pre-baseline records were cleared. Do not compare pre-baseline performance.

See `docs/roadmap.md` for completed phases and future roadmap.

## Architecture

**Entry points:**
- `app.py` — Streamlit web UI (single file; all UI + CSS)
- `main.py` — CLI tool (no external deps)
- `sync.py` — data ingestion + maintenance CLI
- `verify_model.py` — pipeline verification report (accepts `--strategy` and `--omsetning`)
- `evaluate.py` — post-match evaluation pipeline (Phase 8A); idempotent; accepts `--week`, `--all`, `--status`, `--fetch`

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

**Database:** SQLite via `db/connection.py`. Key tables: `fixtures`, `coupons`, `coupon_fixtures`, `odds`, `odds_snapshots`, `coupon_predictions`, `match_results`, `coupon_evaluations`, `fixture_stat_enrichment`, `fixture_estimated_prior`, `coupon_save_snapshot`, `pick_evaluations`.

**Streamlit pages:**
| File | Page |
|---|---|
| `app.py` | Main — coupon selector, analysis table, EV panel, strategy comparison (Lagre kupong) |
| `pages/1_Team_Review.py` | Team Review |
| `pages/2_Results.py` | Resultater — enter scores |
| `pages/3_History.py` | Historikk — 6 sections: coupon results, strategy performance, CDS validation, conviction vs necessary, model vs NT public, PVR vs payout |
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
- **Evaluation uses frozen snapshot only** — `evaluate_coupon()` reads `pub_prob_*`, `value_*`, `crowd_disagreement_score` from `coupon_predictions` (frozen at save time). Never read live `coupon_fixtures.public_h/u/b` for historical evaluation. Old coupons with NULL snapshot fields show "—" — they are never backfilled.
- **Evaluation baseline** — Week 24/2026 Midtuke is record #1. Do not restore or compare pre-baseline coupon records.
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
