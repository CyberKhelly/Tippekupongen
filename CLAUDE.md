# CLAUDE.md

Project guidance for Claude Code. Read the relevant `docs/` file before changing that area of the codebase.

## Project

Norsk Tipping (NT) prediction engine for Tippekupongen. Three parallel systems share the same SQLite database and analysis pipeline:

- **Streamlit** (`app.py`) — original UI, must not be broken
- **FastAPI** (`backend/main.py`) — REST API on port 8000
- **Next.js** (`frontend/`) — primary user-facing UI under development, port 3000

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
# Streamlit UI (primary; Anaconda Python)
streamlit run app.py

# FastAPI backend (from project root)
uvicorn backend.main:app --reload --port 8000

# Next.js frontend (from frontend/)
cd frontend && npm run dev           # dev server, port 3000
node ./node_modules/next/dist/bin/next build   # production build

# Data sync
python sync.py --daily            # fetch NT + odds + enrichment + validate (idempotent)
python sync.py --refresh-coupons  # force-refresh at start of week
python sync.py --validate         # integrity checks (24 checks)
python sync.py --status           # show current week's DB contents

# Force-refresh a specific week (fixes fixture accumulation if needed)
python -c "from ingestion.norsk_tipping import ingest_game_days; ingest_game_days(week=25, year=2026, force_refresh=True)"

# Model verification — run all 4 before placing coupon
python verify_model.py --strategy safe
python verify_model.py --strategy balanced
python verify_model.py --strategy jackpot
python verify_model.py --strategy balanced --omsetning 15000000

# Evaluation pipeline (Phase 8A)
python evaluate.py --week 24 --year 2026   # evaluate one week
python evaluate.py --all                   # evaluate all saved coupons
python evaluate.py --status                # show which coupons have/need results
python evaluate.py --week 24 --year 2026 --fetch   # also pull results from API-Football
```

> **Python path:** `python` is not in PATH on this machine. Use `C:\Users\kimme\anaconda3\python.exe` or activate the Anaconda environment.
> **npm path:** `C:\Program Files\nodejs\npm` — or set `PATH="$PATH:/c/Program Files/nodejs"` in bash.
> **Known issue:** After major dependency changes or unexpected Next.js rendering failures, delete `frontend/.next/` and rebuild.

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

**Next.js frontend migration:** In progress. `/coupon` route is the only active page. The Streamlit UI remains the backup and must not be broken.

**Evaluation baseline:** Week 24/2026 Midtuke is the first coupon under the current model philosophy (CDS-driven, crowd-disagreement-first). All pre-baseline records were cleared. Do not compare pre-baseline performance.

See `docs/roadmap.md` for completed phases and future roadmap.

## Architecture

**Entry points:**
- `app.py` — Streamlit web UI (single file; all UI + CSS)
- `main.py` — CLI tool (no external deps)
- `sync.py` — data ingestion + maintenance CLI
- `verify_model.py` — pipeline verification report (accepts `--strategy` and `--omsetning`)
- `evaluate.py` — post-match evaluation pipeline (Phase 8A); idempotent; accepts `--week`, `--all`, `--status`, `--fetch`
- `backend/main.py` — FastAPI app; lifespan starts APScheduler; all REST routes
- `frontend/` — Next.js 15 / React 19 / TanStack Query / Framer Motion / Tailwind

**Analysis pipeline** (shared by app.py, Kampanalyse, Statistikk, coupon generation, and FastAPI):
```
decimal odds
  → analysis/probability.py   normalise odds → prob_h/u/b
  → analysis/model.py         bookmaker prior + AF stats adjustment + CDS
  → analysis/classifier.py    classify match (banker/standard/half_cover/full_cover/uncertain)
  → analysis/optimizer.py     two-stage strategy-aware search for (n_full, n_half)
```

`Match` in `models/match.py` carries odds in and probabilities + classification out (mutated in place).

**Key analysis modules:**
- `analysis/strategy.py` — StrategyConfig + STRATEGIES dict (safe/balanced/jackpot)
- `analysis/pool_value.py` — compute_value_index, compute_p_win, compute_pool_value_ratio, simulate_payout
- `analysis/estimated_prior.py` — fallback H/U/B when no bookmaker odds (NT expert 60% + stats 40%)
- `data/loader.py` — SQLite (preferred) or flat-file `data/coupon_weekNN_YYYY.py` (fallback)

**FastAPI routes:**
| Route | Purpose |
|---|---|
| `GET /v1/coupons` | Active non-expired coupons (no args); or by `?week=&year=` for history |
| `POST /v1/optimize` | Run optimizer — accepts `coupon_id`, `strategy`, `budget` |
| `GET /v1/sync/status` | Sync state: last refresh times, omsetning, tip change count |
| `POST /v1/sync/refresh-coupons` | Trigger NT refresh (background task — admin/backend only) |
| `POST /v1/sync/daily` | Trigger full daily sync |
| `GET /health` | Health check |

**Database:** SQLite via `db/connection.py`. Key tables: `fixtures`, `coupons`, `coupon_fixtures`, `odds`, `odds_snapshots`, `coupon_predictions`, `match_results`, `coupon_evaluations`, `fixture_stat_enrichment`, `fixture_estimated_prior`, `coupon_save_snapshot`, `pick_evaluations`.

`coupons` table columns include: `omsetning REAL` (NT turnover in NOK, added 2026-06-19), `nt_game_day_id TEXT`, `day_type TEXT`, `deadline_utc TEXT`.

**Streamlit pages:**
| File | Page |
|---|---|
| `app.py` | Main — coupon selector, analysis table, EV panel, strategy comparison (Lagre kupong) |
| `pages/1_Team_Review.py` | Team Review |
| `pages/2_Results.py` | Resultater — enter scores |
| `pages/3_History.py` | Historikk — 6 sections: coupon results, strategy performance, CDS validation, conviction vs necessary, model vs NT public, PVR vs payout |
| `pages/4_Odds_Movement.py` | Odds Movement |
| `pages/5_Statistikk.py` | Statistikk — per-fixture model breakdown |

**Next.js frontend structure (`frontend/`):**
| File | Purpose |
|---|---|
| `app/coupon/page.tsx` | Main coupon optimizer page — all layout, queries, sidebar |
| `components/MatchTable.tsx` | 12-match table with conviction dots, prob bars, edge badges |
| `components/MetricsRow.tsx` | P(win), PVR, rows, cost metric cards |
| `components/StrategySelector.tsx` | Safe / Balanced / Jackpot tabs |
| `components/CouponSelector.tsx` | Active coupon tabs (feeds from `list_active_coupons` via API) |
| `components/BudgetSelector.tsx` | Budget selector (32 / 96 / 192 / 384 NOK) |
| `components/SyncStatus.tsx` | Data freshness panel — passive, no manual refresh button |
| `lib/api.ts` | All API fetch functions |
| `lib/types.ts` | TypeScript mirrors of backend Pydantic schemas |
| `lib/utils.ts` | Formatting helpers: `formatRelative`, `formatUntil`, `secsUntil`, `fmtKr`, etc. |

## Active Coupon Lifecycle

`GET /v1/coupons` with no `week`/`year` parameters returns only **active (non-expired) coupons**, deduplicated by `nt_game_day_id`. This handles the case where the same NT game day is ingested under two week numbers at a week boundary (e.g. `lordag-24-2026` and `lordag-25-2026` sharing `nt_game_day_id=69240`). The entry with the higher week number wins.

Expiry uses **timezone-aware datetime comparison** in Python (`db.coupon.list_active_coupons()`), not SQLite string comparison, because some deadlines are stored with `+02:00` offsets.

Expired coupons remain in the DB forever for history, Results entry, and evaluation. They are simply excluded from the active list.

## Turnover / Omsetning

**Source:** `game.sales.fullTime.saleAmount.amount` in `PoolGamesSportInfo/v1/api/tipping/live-info`.

**Storage:** `coupons.omsetning` (REAL, NOK). Updated on every NT refresh, even when fixture data is hash-unchanged (omsetning accumulates continuously until deadline).

**Display:** `SyncStatusPanel` in the Next.js sidebar shows total omsetning across active coupons when > 0. No turnover is shown for week 23 coupons (pre-column).

## Automatic Refresh (APScheduler)

`backend/scheduler.py` runs inside the FastAPI process via `lifespan`:

- **NT check:** every 5-min tick, self-throttles to 60/15/5-min intervals based on time-to-deadline.
- **Odds check:** every 3 hours.
- State: `data/sync_state.json` (thread-safe, atomic writes via `backend/sync_state.py`).
- Never calls `sync.py` functions that contain `sys.exit()`.

The Next.js frontend polls `/v1/sync/status` on an adaptive interval (5 s when running, 30–120 s by deadline proximity). **There is no manual refresh button in the user UI.**

## Critical Rules

- **Single pipeline:** `process_match() → run_model() → classify_match() → optimize_coupon()` is used identically in app.py, Statistikk page, FastAPI, and verify_model.py. Do not branch it.
- **Bookmaker dominance:** bookmaker prior always has ≥87% weight. AF stats can adjust by at most ±`_MAX_ADJ` (defined in `analysis/model.py`).
- **Do not add new strategies or change strategy parameters** without explicit instruction.
- **Do not implement Elo, xG, or additional AI models** without explicit instruction.
- **estimated_prior is not bookmaker odds** — never write to `odds` or `odds_snapshots`. Validate check 24 enforces zero overlap.
- **CLV uses real bookmaker odds only** — `odds_snapshots` must only contain real bookmaker (Pinnacle etc.) data.
- **Model probabilities in `Match` are read-only** — strategy and optimizer never write to them.
- **Evaluation uses frozen snapshot only** — `evaluate_coupon()` reads `pub_prob_*`, `value_*`, `crowd_disagreement_score` from `coupon_predictions` (frozen at save time). Never read live `coupon_fixtures.public_h/u/b` for historical evaluation. Old coupons with NULL snapshot fields show "—" — they are never backfilled.
- **Evaluation baseline** — Week 24/2026 Midtuke is record #1. Do not restore or compare pre-baseline coupon records.
- **Do not delete old coupons** — expired coupons must remain in DB for history, Results, and evaluation. Only exclude them from the active list.
- **Fixture accumulation bug is fixed** — `ingest_game_days()` now always clears `coupon_fixtures` before re-writing an existing coupon (not only on `force_refresh`). If a coupon ever shows double the expected fixture count, run `ingest_game_days(week=N, year=Y, force_refresh=True)`.
- **Streamlit CSS:** Streamlit ≥1.40 renamed `data-testid="column"` → `"stColumn"`. Target both. Use `components.html()` for complex dynamic HTML (not `st.markdown`); CommonMark exits HTML blocks on blank lines.
- **Balanced composite score formula:** `score = confidence × clip(VI_at_pick, 0.75, 1.25)` where `VI = model_prob(pick) / pub_prob(pick)`. This replaced the old additive `confidence + 0.03 × clip(value_top/20, −1, +1)` formula. `effective_conf_adj` in `StrategyConfig` is now unused for Balanced but kept as a field — do not remove it.
- **Do not add a crowd_trap_force_halvdekk rule to Balanced.** Audited and rejected: high-confidence singles (>55%, VI > 0.80) are correct under `P^0.9 × PVR^0.1` even when crowd-heavy. Forcing halvdekk on USA/StPatrick-type matches makes the shape objective worse. Use Jackpot strategy if stronger PVR weighting is needed.
- **`verify_model.py` `*` annotation is stale for Balanced.** The `*` marker is driven by `_effective_confidence()` (old Phase-5 shim), not the new composite score. It no longer reflects what Balanced actually does. Display-only artefact; does not affect coupon generation.
- **Halvdekk second pick:** Always derive the second mark from ModH/U/B probabilities directly — it is whichever non-primary outcome has the higher probability. Never assume U is the second pick. Compare ModU% vs ModB% explicitly. `verify_model.py` output shows halvdekk type but not always the explicit second mark; read the probability columns to confirm.
- **Next.js `refetchInterval` callback:** TanStack Query v5.56.2 passes `(data: TData | undefined)` to `refetchInterval` callbacks, not a `Query` object. Use a state-driven `useState<number | false>` + `useEffect` pattern instead of `(query) => query.state.data?....`.

## Detailed Documentation

Read the relevant doc before changing that area of the codebase:

| File | Contents |
|---|---|
| `docs/model_architecture.md` | Unified prediction engine, bookmaker prior, AF stats blend, estimated prior, CDS, value_h/u/b, odds source priority, pool value metrics (P(12/12), PVR, Poolverdi, VI, e_winners) |
| `docs/strategy_system.md` | Safe/Balanced/Jackpot — objectives, composite score formulas, shape objectives, halvdekk substitution, optimizer math, strategy invariants |
| `docs/payout_simulator.md` | Phase 7 Monte Carlo simulator, corrected denominator (+1 not +n_rows), Poisson variance, payout percentiles, e_winners, EV panel UI structure |
| `docs/data_pipeline.md` | NT API endpoint change (2026-06), AF enrichment, odds fallback order, sync.py commands reference, DB tables, weekly workflow |
| `docs/roadmap.md` | Completed phases (1–7), Phase 8 scope, current architecture + code map, Streamlit pages, known limitations, future roadmap |
| `MIGRATION_STATUS.md` | Full current state snapshot: active coupons, omsetning, file inventory, system start commands, known issues |
