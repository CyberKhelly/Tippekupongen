# TippeQpongen — Migration Status

Last updated: 2026-06-20 (team name fix)

## Architecture overview

Three parallel systems coexist. All three share the same SQLite database and the same Python analysis pipeline.

| System | Entry point | Port | Status |
|---|---|---|---|
| Streamlit UI | `streamlit run app.py` | 8501 | Active — must not be broken |
| FastAPI backend | `uvicorn backend.main:app --reload --port 8000` | 8000 | Active |
| Next.js frontend | `npm run dev` (inside `frontend/`) | 3000 / 3001 | Active — primary UI under development |

The Next.js frontend calls the FastAPI backend. Streamlit runs fully independently. Neither UI contains any model logic — all analysis runs in `analysis/`.

---

## Starting the stack

```bash
# Streamlit (from project root, Anaconda Python)
streamlit run app.py

# FastAPI backend (from project root)
uvicorn backend.main:app --reload --port 8000

# Next.js frontend (from frontend/)
cd frontend
npm run dev

# Next.js production build (from frontend/)
node ./node_modules/next/dist/bin/next build
```

> **Note:** `python` is not in PATH on this machine. Use `C:\Users\kimme\anaconda3\python.exe` or activate the Anaconda environment. `npm` is at `C:\Program Files\nodejs\npm`.

> **Known issue:** After major dependency changes or unexpected rendering failures, delete `frontend/.next/` and rebuild.

---

## Current working routes

| Route | Description |
|---|---|
| `http://localhost:3000/coupon` | Main coupon optimizer UI — the only active Next.js page |
| `http://localhost:8000/v1/coupons` | Active coupons (no week/year = non-expired, deduplicated) |
| `http://localhost:8000/v1/optimize` | POST — run optimizer for a coupon |
| `http://localhost:8000/v1/sync/status` | GET — sync state (last refresh times, omsetning, tip changes) |
| `http://localhost:8000/v1/sync/refresh-coupons` | POST — trigger NT data refresh (admin/backend only) |
| `http://localhost:8000/health` | GET — health check |

---

## Python path

```
C:\Users\kimme\anaconda3\python.exe
```

All Python commands in this project must be run from the project root `C:\Users\kimme\Desktop\Tippekupongen\`.

---

## Model constraints — do not change

- The analysis pipeline is `process_match() → run_model() → classify_match() → optimize_coupon()`.
- Bookmaker prior always has ≥ 87% weight. AF stats can adjust by at most `±_MAX_ADJ`.
- Strategies: **Safe**, **Balanced**, **Jackpot** only. Do not add, rename, or reorder.
- Balanced composite score formula: `score = confidence × clip(VI_at_pick, 0.75, 1.25)`.
- Do not add Elo, xG, or additional AI models.
- Model probabilities in `Match` are read-only — strategy and optimizer never write to them.

---

## Active coupon lifecycle (as of 2026-06-19)

### Current DB state

| coupon_id | Label | Deadline (CEST) | Fixtures | Omsetning |
|---|---|---|---|---|
| `lordag-25-2026` | Lørdag — frist 2026-06-20 | 2026-06-20 14:55+02 | 12 | ~797k NOK |
| `sondag-25-2026` | Søndag — frist 2026-06-21 | 2026-06-21 15:55+02 | 12 | ~419k NOK |
| `midtuke-25-2026` | Midtuke — frist 2026-06-24 | 2026-06-24 23:55+02 | 12 | ~687 NOK (just opened) |

Old expired coupons (week 23, 24) remain in the DB for history/evaluation. They are not returned by `/v1/coupons` (no week/year).

### Important lifecycle rule

`/v1/coupons` with no `week`/`year` parameters now returns only active (non-expired) coupons, deduplicated by `nt_game_day_id`. This was added because the same NT game day was sometimes ingested under two different week numbers at a week boundary (e.g. `lordag-24-2026` and `lordag-25-2026` both referred to the same game day with the same `nt_game_day_id`). The deduplication keeps the entry with the higher week number.

### Bug fixed: fixture accumulation on content change

Previously, `ingest_game_days()` only cleared old `coupon_fixtures` rows when `force_refresh=True`. If the NT API returned a new set of matches for the same coupon (content hash changed), the new fixtures were appended on top of the old ones. This caused `midtuke-25-2026` to have 24 fixtures (two overlapping sets of 12). The bug is fixed: `coupon_fixtures` are now cleared whenever an existing coupon is about to be re-written, regardless of `force_refresh`.

To force-clean and re-import a specific week:
```bash
python -c "from ingestion.norsk_tipping import ingest_game_days; ingest_game_days(week=25, year=2026, force_refresh=True)"
```

---

## Turnover / omsetning

**Source confirmed:** `game.sales.fullTime.saleAmount.amount` in the NT `PoolGamesSportInfo/v1/api/tipping/live-info` endpoint.

**Storage:** `coupons.omsetning` (REAL column, added 2026-06-19 via `_PHASE1_COLUMNS`).

**Flow:**
1. `parse_live_info_response()` extracts `omsetning` from the NT API response.
2. `ingest_game_days()` writes it to `coupons.omsetning` via `upsert_coupon()`.
3. On hash-unchanged coupons, omsetning is still updated (it accumulates continuously).
4. `_get_turnover()` in `backend/scheduler.py` reads from `list_active_coupons()`.
5. `SyncStatus` in the frontend shows total omsetning when > 0 (collapsed panel, expanded view).

**Turnover is NOT shown for:** week 23 coupons (ingested before this column existed, have `NULL`).

---

## Automatic refresh (APScheduler)

`backend/scheduler.py` runs background jobs inside the FastAPI process:

- **NT check:** every 5 min tick, self-throttles to 60/15/5 min intervals based on time-to-deadline.
- **Odds check:** every 3 hours.
- State persisted to `data/sync_state.json` (thread-safe, atomic writes).
- Never calls `sync.py` functions that contain `sys.exit()`.

The frontend polls `/v1/sync/status` on an adaptive interval (5s when running, 30–120s otherwise). There is **no manual refresh button** in the user UI — refresh is fully automatic.

---

## Evaluation baseline

**Week 24/2026 Midtuke** is record #1 under the current CDS-driven model philosophy. All pre-baseline coupon records were cleared. Do not restore or compare pre-baseline data.

Evaluation pipeline: `evaluate.py` (Phase 8A). Tables: `coupon_save_snapshot`, `pick_evaluations`, extended `coupon_predictions` / `coupon_evaluations`.

---

## Important files

### Backend / analysis (Python)

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — single file, all UI + CSS |
| `backend/main.py` | FastAPI app, lifespan, all API routes |
| `backend/scheduler.py` | APScheduler background jobs (NT refresh, odds refresh) |
| `backend/sync_state.py` | Thread-safe JSON sync state (`data/sync_state.json`) |
| `backend/pipeline.py` | `build_matches()` — bridges DB rows to `Match` objects for FastAPI |
| `backend/schemas.py` | Pydantic schemas for all API request/response types |
| `analysis/model.py` | Unified prediction engine (bookmaker prior + AF stats + CDS) |
| `analysis/optimizer.py` | Two-stage strategy-aware optimizer |
| `analysis/strategy.py` | `StrategyConfig` + `STRATEGIES` dict |
| `analysis/pool_value.py` | CDS, PVR, VI, simulate_payout |
| `ingestion/norsk_tipping.py` | NT API fetch + parse (primary: `PoolGamesSportInfo/v1/api/tipping/live-info`) |
| `ingestion/odds_api.py` | Pinnacle odds via The Odds API |
| `db/schema.py` | `init_db()` — all DDL, idempotent migrations via `_PHASE1_COLUMNS` etc. |
| `db/coupon.py` | `upsert_coupon`, `list_coupons`, `list_active_coupons`, `get_coupon_matches` |
| `data/loader.py` | `load_coupons()` — DB → flat file fallback |
| `data/sync_state.json` | Live sync state (created at runtime) |
| `sync.py` | CLI data sync tool (`--daily`, `--refresh-coupons`, `--validate`, `--status`) |
| `verify_model.py` | Pipeline verification — run all 4 strategies before placing a coupon |
| `evaluate.py` | Phase 8A evaluation pipeline |

### Next.js frontend (`frontend/`)

| File | Purpose |
|---|---|
| `app/layout.tsx` | Root layout, `<Providers>` wrapper |
| `app/providers.tsx` | TanStack Query `QueryClientProvider` |
| `app/coupon/page.tsx` | Main coupon page — all layout, queries, sidebar |
| `app/globals.css` | Tailwind + custom CSS (glass, card-top-line, skeleton, animations) |
| `components/MatchTable.tsx` | 12-match table with conviction dots, prob bars, edge badges |
| `components/MetricsRow.tsx` | P(win), PVR, total rows, total cost metric cards |
| `components/StrategySelector.tsx` | Safe / Balanced / Jackpot tabs with layoutId animation |
| `components/CouponSelector.tsx` | Active coupon tabs (uses `list_active_coupons` via API) |
| `components/BudgetSelector.tsx` | Budget selector (32 / 96 / 192 / 384 NOK) |
| `components/SyncStatus.tsx` | Data freshness panel (passive — no manual refresh button) |
| `lib/api.ts` | All fetch functions (`getCoupons`, `optimize`, `getSyncStatus`, …) |
| `lib/types.ts` | TypeScript mirrors of backend Pydantic schemas |
| `lib/utils.ts` | `cn`, `fmtPct`, `fmtKr`, `formatRelative`, `formatUntil`, `secsUntil`, `recValue` |

---

## What must not change

- **Streamlit** (`app.py` and `pages/`) — must continue to work independently.
- **Optimizer logic** (`analysis/optimizer.py`) — do not alter.
- **Model logic** (`analysis/model.py`) — do not alter.
- **Strategy parameters** (`analysis/strategy.py`) — Safe / Balanced / Jackpot only.
- **Evaluation baseline** — Week 24/2026 Midtuke is record #1; no pre-baseline data to restore.
- **Old coupon records** in DB — expired coupons are hidden from the active list but must remain in the DB for history, Results, and evaluation pages.
- **`coupon_predictions` historical data** — never delete or backfill with live data.

---

## API-Football league mappings (verified 2026-06-20)

IDs confirmed via `/leagues?country=Norway&season=2026`:

| NT arrangement_name pattern | AF league ID | AF name |
|---|---|---|
| `2.divisjon avd. 1` | 473 | 2. Division - Group 1 |
| `2.divisjon avd. 2` | 474 | 2. Division - Group 2 |
| `2.divisjon` (catch-all) | not_covered | Groups 3–7 not indexed by AF |
| `Norsk Tipping-ligaen avd1–6` | 774–779 | 3. Division - Girone 1–6 |
| `Norsk Tipping-ligaen` (catch-all) | not_covered | — |
| `OBOS-ligaen` | 104 | 1. Division |
| `Eliteserien` | 103 | Eliteserien |
| `Toppserien` | 725 | Toppserien |
| `NM Cup` / `NFF Cup` | 105 | NM Cupen |
| `Fotball-VM` / `FIFA World Cup` | 1 | World Cup |
| `UEFA Champions League` | 2 | Champions League |
| `UEFA Nations League` | 5 | Nations League |
| `FIFA World Cup, Women, Qualification, UEFA` | 880 | WC Women Qual Europe |
| `FIFA World Cup, Women` | 6 | World Cup Women |

**To re-run enrichment for a specific week:**
```bash
C:\Users\kimme\anaconda3\python.exe sync.py --daily
# or for a specific week:
C:\Users\kimme\anaconda3\python.exe -c "from ingestion.enrich_fixtures import enrich_active_fixtures; enrich_active_fixtures(week=25, year=2026, verbose=True)"
```

### Known enrichment limitations

- **2. Divisjon Groups 3–7:** AF does not index these. `has_api_football_data=None`, `data_coverage=0`. Bookmaker-prior-only fallback applies.
- **WC home/away record:** WC games are neutral-venue. AF `teams/statistics` returns 0 for home/away record throughout the tournament. `data_coverage` for WC fixtures is structurally capped at 3/4 — but in practice AF still returns a non-None record (e.g. `W0 D1 L0` after one game), so all 4 signals populate once the tournament is underway.

---

## Phase status

| Phase | Status |
|---|---|
| 1 — Data pipeline (NT + odds) | Complete |
| 2 — Streamlit UI | Complete |
| 3 — Odds movement / CLV | Complete |
| 4 — API-Football enrichment | Complete |
| 5 — Unified prediction engine | Complete |
| 6 — Strategy system (Safe/Balanced/Jackpot) | Complete |
| 7 — Payout simulator | Complete |
| 8A — Automated evaluation pipeline | Complete |
| 8B — Model calibration (Brier, log-loss) | Not started |
| 8C — Payout tracking (actual vs simulator) | Not started |
| Next.js frontend migration | In progress — `/coupon` route live |
