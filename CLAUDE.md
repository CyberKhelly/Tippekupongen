# CLAUDE.md

Project guidance for Claude Code. Read the relevant `docs/` file before changing that area of the codebase.

## Project

TippeIQ — Norwegian Tipping (NT) prediction engine. Three parallel systems share the same SQLite database and analysis pipeline:

- **Streamlit** (`app.py`) — original UI, must not be broken
- **FastAPI** (`backend/main.py`) — REST API on port 8000
- **Next.js** (`frontend/`) — primary user-facing UI under development, port 3000

---

## Product Split

TippeIQ contains two separate intelligence products. They share the same model core but use different inputs and target different markets.

### 1. Kupong-intelligens

- Norsk Tipping pool / coupon logic
- **Uses** NT public tip percentages (crowd data)
- Goal: find where the model disagrees with the crowd, exploit pool mispricing
- Key metrics: PVR, P(12), P(11+), P(10+), folkeavvik (edge_pp), expected pool value
- Coupon output: Balansert + Jackpot strategies producing 1-2-3 mark recommendations
- Pages: `/signaler`, `/kupong`

### 2. Odds-intelligens / Modellspill

- Bookmaker market logic
- **Must NOT** use NT public tip percentages in any probability or edge calculation
- Uses: bookmaker odds + model probability (bookmaker prior + AF stats adjustment)
- Goal: beat bookmaker implied probability, find market mispricing
- Key metrics: ROI, CLV, bankroll, hit rate, drawdown, model edge
- Output: paper bets on 1X2 / BTTS / Over 2.5 with edge ≥ 3pp (tiered)
- Page: `/oddstips`

---

## Model Quality Hierarchy

All matches evaluated for Modellspill are tagged with a model quality level:

| Level | Label | Definition |
|---|---|---|
| `full_model` | Full modell | Real seasonal enrichment with venue-specific goal averages → Poisson from Phase 13 stats |
| `af_supported` | AF-støttet | No enrichment (or no goal data), but AF Predictions `last_5` goal data available for Poisson |
| `generic_prior` | Eurosnitt-prior | No enrichment, no AF predictions → European-average Poisson (xG home 1.40, away 1.10) |

The `model_quality` field is stored per bet in the `model_bets` table and used for transparency badges in the UI.

**Model quality for Kupong-intelligens (NT coupon matches):** Always goes through the full bookmaker prior pipeline. AF stats adjustment is applied when enrichment data exists. `estimated_prior` fallback is used when no bookmaker odds are available (never tagged "full_model" for the coupon product).

---

## Odds Scanner

`scan_af_market_odds()` in `ingestion/api_football_odds.py`:

- 72-hour lookahead window (configurable)
- 27 tracked leagues (see `_SCAN_LEAGUES` in `api_football_odds.py`)
- Markets fetched per fixture: 1X2, BTTS (Both Teams Score), Over/Under 2.5
- Bookmaker priority: Bet365 → William Hill → Marathonbet → 10Bet → first available
- World Cup included: `league_id=1, season=2026`
- New fixtures not yet in DB are inserted into `fixtures` + `api_football_fixture_links`
- 1X2 stored in `odds` table (skipped if already present)
- BTTS/O/U stored in `odds_markets` table (upserted every run — latest wins)

**Scheduler:** runs via `_market_scan_job()` every 2 hours inside the FastAPI process.

**Endpoint:** `POST /v1/bets/scan` — triggers scan + candidate generation immediately (manual trigger).

**Auto-settle:** `_auto_settle_job()` runs every 60 minutes. Settles pending bets for fixtures where `kickoff_utc + 100 min` is in the past and a result exists in `match_results`.

---

## Modellspill Persistence (model_bets table)

All generated Modellspill candidates are stored in the `model_bets` table (via `db/paper_bets.py`).

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `coupon_id` | TEXT \| NULL | NULL for global scan bets; set for coupon-specific bets |
| `fixture_id` | TEXT | Internal fixture ID |
| `match_name` | TEXT | "Home vs Away" |
| `league` | TEXT \| NULL | League name |
| `kickoff_utc` | TEXT \| NULL | ISO kickoff time |
| `market` | TEXT | `1x2`, `btts`, `over_2.5` |
| `outcome` | TEXT | `H`, `U`, `B`, `yes`, `no`, `over`, `under` |
| `bookmaker` | TEXT | Bookmaker name |
| `ref_odds` | REAL | Reference odds at bet generation time |
| `implied_prob` | REAL | De-vigged implied probability (0–1) |
| `model_prob` | REAL | Model probability (0–1) |
| `edge_pp` | REAL | `(model_prob − implied_prob) × 100` |
| `stake_nok` | REAL | Flat stake in NOK |
| `expected_value` | REAL | `model_prob × ref_odds − 1` |
| `insight_type` | TEXT \| NULL | `value_bet`, `longshot`, tier tag |
| `model_quality` | TEXT | `full_model`, `af_supported`, `generic_prior` |
| `risk_level` | TEXT | `tier_a` (≥8pp), `tier_b` (5–8pp), `tier_c` (3–5pp) |
| `reason` | TEXT \| NULL | Human-readable edge explanation |
| `status` | TEXT | `pending`, `won`, `lost`, `void` |
| `result_outcome` | TEXT \| NULL | Actual result (set on settle) |
| `closing_odds` | REAL \| NULL | Bookmaker odds at close (for CLV) |
| `clv` | REAL \| NULL | Closing Line Value: `ref_odds / closing_odds − 1` |
| `profit_nok` | REAL \| NULL | `stake × (ref_odds − 1)` if won, else `−stake` |
| `created_at` | TEXT | ISO timestamp |
| `settled_at` | TEXT \| NULL | ISO timestamp when settled |

**API endpoints:**
| Route | Purpose |
|---|---|
| `GET /v1/bets` | List bets (optional `status`, `market`, `limit` filters) |
| `GET /v1/bets/summary` | Aggregate performance metrics across all settled bets |
| `GET /v1/bets/bankroll` | Chronological bankroll series for equity chart |
| `POST /v1/bets/generate` | Generate bets for active coupon (edge ≥ 5pp) |
| `POST /v1/bets/scan` | Global 72h odds scan + candidate generation (edge ≥ 3pp) |
| `POST /v1/bets/settle/{fixture_id}` | Manually settle pending bets for a fixture |

---

## NT Oddsen Odds Source (Active — Playwright)

NT Oddsen 1X2 odds are scraped via Playwright headless Chromium from `https://www.norsk-tipping.no/sport/oddsen`. No login required. Odds load via NT's own WebSocket (`velnt-opr1.sport2.norsk-tipping.no`), not the Sportradar feed. Implemented in `ingestion/nt_oddsen_playwright.py` (production code, importable from main.py/scheduler.py).

**Scraper architecture:**
- Target: `norsk-tipping.no/sport/oddsen` → iframe `#sportsbookid` → `/sport/oddsen/sportsbook/`
- 1X2 odds: `div[data-for="selection-event-ID.1"]` with `aria-label="TeamName, odds X.XX"`
- Team names from `[class*='ParticipantNameItem']`, kickoff from `[class*='DateContainer']`
- 3 consecutive selection divs in DOM order = H, U, B for one match
- Stores to `nt_oddsen_odds_snapshot` table
- BTTS/O/U: per-event navigation via `[data-id="navigation_bonavigation_button_morema"]` (+N button) — feasibility confirmed, Phase 2 ready

**Modellspill 1X2 gating:** `generate_global_bet_candidates()` only generates 1X2 bets when an NT Oddsen snapshot row exists (max 6h old). Fixture matching uses `normalize_team_name(home)|normalize_team_name(away)|YYYY-MM-DD` key with ±1 day fallback.

**Scheduler flow (every 2h):** `scrape_nt_oddsen_playwright()` → `scan_af_market_odds()` → `generate_global_bet_candidates()`

`ingestion/nt_oddsen_scraper.py` (Firecrawl) is still **dev-only — not imported from production**. The Playwright scraper is the active production path.

**Why Firecrawl failed:** Firecrawl targeted `s5.sir.sportradar.com/norsktipping/no/sport/1` directly — a Sportradar SIR widget requiring authenticated WebSocket. NT's own site (`norsk-tipping.no`) uses their own React sportsbook with a public WebSocket. Do not use cookie/session scraping as an alternative to the Playwright approach.

**BTTS/O/U — production complete (2026-06-30):**
- Full architecture: `scrape_nt_oddsen_playwright()` scrapes main list (1X2) then navigates each event detail for BTTS + O/U, then calls `history.back()` to return
- Market values stored: `1x2`, `BTTS`, `OVER_UNDER_2_5`; selections: `H/U/B`, `YES/NO`, `OVER/UNDER`
- Cookie dialog (`ntds-dialog-sheet-backdrop` z-1300) dismissed via JS `_dismiss_cookie(page)` before any clicks
- More-markets button: `[data-id="navigation_bonavigation_button_morema"]` — button at index i matches match i
- Navigate back: `sbf.evaluate("window.history.back()")` — preserves React Router state; hard reload breaks buttons
- Market grouping JS (`_MARKET_JS`): `navigation_event_selection_toggle` → walk up to `NavWrapper` → collect `[data-for^="selection-event-"]`
- BTTS market: "Begge lag scorer" (Ja → YES, Nei → NO)
- O/U 2.5 market: "Totalt antall mål - Over/Under 2,5" (group name containing "2,5" or "2.5")
- Timing: ~5.5s per event + ~5s navigate-back settle = ~10.5s/match; 13 WC matches in ~136s
- `load_nt_market_bulk(conn, market, required_sels)` loads any NT market from the snapshot
- `generate_global_bet_candidates()` uses NT BTTS/O/U odds as primary source; AF `odds_markets` as fallback
- `_nt_find(nt_source, home, away, kickoff_utc)` handles exact + ±1 day fixture key lookup for all markets
- POC (dev-only): `scripts/nt_btts_ou_poc.py`

---

## Design Semantics

| Color | Role | Use |
|---|---|---|
| Gold `#F5C542` | Value / strong recommendation | Top signal, recommended pick, CTA |
| Indigo `#7B92FF` | Model disagreement / crowd mispricing | Edge signal, "where the crowd is wrong" |
| Green `#22C55E` | Positive outcome | Won bets, positive ROI, covered picks |
| Red `#EF4444` | Actual bad outcomes only | Losses, negative ROI, errors, drawdown |
| Amber `#F59E0B` | Caution / risk | Warning states, risk level badges |

**Red must never be used for ordinary model disagreement.** Disagreement is shown with indigo or as an absolute value + explanation, not as failure.

---

## Systemspill (frontend/app/strategien/page.tsx)

- **Risk slider:** Treffsikkerhet ↔ Jackpotpotensial — maps to n_full/n_half balance within the selected system
- **Coverage allocation:** Matches are ranked by coverage score; top `n_full` get full-cover (H+U+B), next `n_half` get half-cover (2 marks), remainder get single marks
- **Reduction funnel:** `buildSystemProposal` assigns coverage types rank-first; `generateRows()` computes the Cartesian product (3^n_full × 2^n_half = rows)
- **Reason bands per match:** Classification chip (banker/halvdekk/heldekk/standard) shown per row; Explain Mode shows coverage type and confidence rationale
- **Payout/profile section:** When omsetning is set, MetricsRow shows P(win), PVR, total rows, total cost

---

## Current Known Caveats

- **P(11+) / P(10+):** Depend on backend Monte Carlo simulation. Available only when omsetning > 0 is provided to `/v1/optimize`. Missing data shown as "—".
- **Non-enriched NT coupon matches:** Some matches (e.g. lower Norwegian leagues, some international fixtures) rely on `af_supported` or `generic_prior` Poisson for Modellspill. The Kupong-intelligens pipeline always uses bookmaker prior; enrichment data only adjusts the model, never replaces it.
- **NT odds for Modellspill:** NT odds are not used for Modellspill. Modellspill always uses bookmaker odds (Bet365 / Pinnacle via Odds API). NT public percentages are Layer 2 (coupon value) only.
- **API-Football odds:** Market references for BTTS and O/U. Odds from API-Football bookmakers (Bet365 etc.) are used as model_bets reference odds. These are not exchange prices.
- **Settlement lag:** Auto-settle requires `match_results` to be populated via `evaluate.py --fetch`. Results are not fetched automatically by the scheduler.
- **CLV accuracy:** `closing_odds` must be set manually or via a future closing-odds refresh job. Currently NULL for most bets.

---

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

**Milestone: Premium TippeIQ redesign + global Modellspill intelligence.** (2026-06-29)

- **NT Oddsen Playwright scraper + BTTS/O/U (complete, 2026-06-30):** `ingestion/nt_oddsen_playwright.py` scrapes `norsk-tipping.no/sport/oddsen` via headless Playwright Chromium. No login, no Firecrawl. 1X2 extracted from main list; BTTS and O/U 2.5 extracted from per-event detail pages via `_BTN_MORE` click → `_extract_btts_ou()` → `history.back()`. 13 WC matches / 91 rows per run (3 per 1X2 + 2 BTTS + 2 O/U). Market keys: `1x2`, `BTTS`, `OVER_UNDER_2_5`. `load_nt_market_bulk()` loads any market by key. `generate_global_bet_candidates()` uses NT BTTS/O/U as primary odds source with AF fallback. `_nt_find()` handles ±1 day fixture key lookup for all markets. The old Firecrawl scraper remains dev-only.
- **Modellspill odds model calibration (complete, 2026-06-30):** Bayesian xG shrinkage (`weight = n/(n+6)`) in `analysis/market_models.py` and `generate_global_bet_candidates()`. Minimum sample gates: venue-specific Phase 13 stats require n_home ≥ 5 AND n_away ≥ 5; AF predictions require played ≥ 5. `generic_prior` bets (EU-average constants) removed — no bets generated without match-specific data. Contradictory bets prevented: `get_conflicting_bet()` + `void_bet()` in `db/paper_bets.py`; `resolve_contradictory_bets()` runs at scan start. af_supported 1X2 bets removed (Poisson WDL without bookmaker anchor is unreliable). Every bet now stores `debug_json` with `xg_home_raw`, `xg_away_raw`, `xg_home_adjusted`, `xg_away_adjusted`, `sample_size_home`, `sample_size_away`, `shrinkage_weight` (Poisson bets) or `bookmaker_prior_h/u/b` (1x2 bets). **Pre-calibration Modellspill bets were cleared because they were generated before Bayesian xG shrinkage, sample-size gates, generic_prior blocking and contradiction prevention. These were test bets only and not valid launch history.** Modellspill history starts clean from 2026-06-30.
- **EV formula fix (2026-06-30):** `create_bet()` in `db/paper_bets.py` previously stored `edge_pp / 100 * stake_nok` (NOK profit estimate) as `expected_value`. Corrected to `model_prob * ref_odds - 1` (true decimal EV). Existing stored bets remain with the old formula; all new bets use the correct formula.
- **NT placeholder odds guard (2026-06-30):** NT Oddsen occasionally returns placeholder odds for two-way markets (BTTS, O/U): e.g. OVER=10.50/UNDER=1.03 — identical across multiple fixtures, clearly not real prices. Guard added in `generate_global_bet_candidates()`: any BTTS or O/U market where either leg ≥ 8.00 or ≤ 1.10 is rejected with reason `nt_placeholder_odds` before implied probability or edge calculation. Both legs are logged in `rejected_candidates` with the fake EV to make the rejection visible. Confirmed: Australia vs Egypt and Mexico vs Ecuador O/U 10.50/1.03 now rejected. `scan_diagnostics.py` shows `NT placeholder odds` count in rejection breakdown.
- **NT-only Modellspill mode + clean launch (2026-06-30):** `generate_global_bet_candidates(nt_only=True)` skips BTTS and O/U when no NT Oddsen match found — no AF/Bet365 fallback for user-facing bets. `delete_all_model_bets()` in `db/paper_bets.py` hard-deletes all rows (used for ledger resets). `scripts/reset_and_rescan.py` performs the full reset sequence: delete all bets → scrape NT → generate NT-only candidates → verify. All model bets were reset after NT Oddsen ingestion, true EV, and placeholder-odds guards were completed. From this point forward, user-facing Modellspill recommendations are NT-only. The scheduler's `_market_scan_job()` continues to use the default `nt_only=False` to preserve AF fallback for background batch generation; reset and production launch explicitly use `nt_only=True`.
- **Modellspill / Odds-intelligens (complete):** Global odds scanner (`scan_af_market_odds`) fetches 27 leagues, 72h window. `generate_global_bet_candidates()` runs the full model pipeline on every fixture with 1X2 odds. Edge tiers: A ≥ 8pp, B 5–8pp, C 3–5pp. Poisson model for BTTS/O/U uses `full_model` → `af_supported` quality hierarchy (generic_prior suppressed). `/oddstips` page shows bankroll chart, active/settled bets, market signals.
- **Modellspill scheduler jobs (complete):** `_market_scan_job()` runs every 2h. `_auto_settle_job()` runs every 60min. Both run inside FastAPI lifespan alongside existing NT and odds jobs.
- **Insights endpoint (complete):** `GET /v1/insights` returns per-fixture model probabilities + bookmaker odds + Pinnacle movement + Poisson BTTS/O/U + AF prediction signals. Multi-market odds from `odds_markets` table (row-per-selection schema).
- **Poisson market models (complete):** `analysis/market_models.py` — `btts_probability()`, `over_under_probability()`, `win_draw_loss_probability()`, `market_probs_from_enrichment()`. Uses Phase 13 venue-specific goal averages (preferred) or Phase 10 overall averages as fallback.
- **Paper bets system (complete):** `db/paper_bets.py`, `model_bets` table. Generation, settlement, bankroll tracking, CLV field. `BetSummary`, `BankrollPoint`, `PaperBet` schemas.

- **Systemspill Category A (complete):** `frontend/lib/systemLibrary.ts` rebuilt with `category: "A" | "B"` field. All 10 Category A systems have verified `n_full`/`n_half` values satisfying `3^n_full × 2^n_half = rows` exactly. 9 of 10 were wrong before (only U 8-2-432 was correct). Category A systems: U 7-0-36 (3²×2²=36), MU 4-3-64 (2⁶=64), U 6-0-64 (2⁶=64), MU 7-0-108 (3³×2²=108), MU 9-1-192 (3×2⁶=192), U 9-0-192 (3×2⁶=192), MU 6-2-324 (3⁴×2²=324), U 8-2-432 (3³×2⁴=432), MU 7-1-486 (3⁵×2=486), MU 5-5-864 (3³×2⁵=864).
- **Cartesian row generator:** `generateRows()` in `strategien/page.tsx` takes the sign state and computes the exact Cartesian product, returning the full `rows × 12` matrix. `buildSystemProposal` for Category A is rank-forced (no threshold) — always fills exactly n_full + n_half slots to guarantee correct row count. Row count verified against `system.rows` at generation time.
- **Category B disabled:** 32 systems whose row counts are not factorable into only 2s and 3s are disabled in the dropdown with a `(B)` marker. These require NT's proprietary reduction matrices (not published). Disabled, not removed — they remain visible in the library.
- **Debug / Explain Mode:** When Debug is on and a Category A system is active, the Explain panel shows "Genererte rader: N / N ✓" and a monospace preview of the first 5 rows (H black, U amber, B blue).
- **Architecture verdict (important):** Category A systems are a **model-driven Cartesian product** — they produce the correct row count (3^n_full × 2^n_half) but NOT the mathematical coverage guarantees of NT's named systems. NT "U 7-0-36" is a combinatorial covering code; our 36 rows are a Cartesian product driven by coverage scoring. The row count matches; the guarantee does not. Category B systems would require the actual NT reduction matrix data to implement correctly.

- **Phase 13 (complete):** League position denominator bug fixed and HJEMME/BORTE section upgraded with venue-specific data. `league_size` is now stored from the real standings team count per group (not estimated from position). Multi-group tournaments use the size of the team's own group (WC → 4, OBOS → 16). Venue-specific averages added: `home_avg_goals_for_home`, `home_avg_goals_against_home`, `away_avg_goals_for_away`, `away_avg_goals_against_away`, `home_clean_sheets_home`, `away_clean_sheets_away`. Frontend HJEMME/BORTE section now shows 4 rows (Rekord, Mål/kamp, Innsluppet, Nullhold.) with venue guards — rows are hidden when a team has played 0 games at that venue (e.g. WC teams always listed as "away" in both group games). New Phase 13 columns in `fixture_stat_enrichment` via `db/schema.py._add_phase13_columns()`.
- **Phase 12 (complete):** Aggregated fixture statistics from `/fixtures/statistics` — possession, shots, shots on goal, corners, pass %, fouls, yellow cards, xG. Stored as JSON in `home_recent_fixture_stats` / `away_recent_fixture_stats`. TOPPSTATISTIKK section in expanded card. Coverage: WC ✓, Eliteserien ✓, OBOS ✗, Toppserien ✗. xG available on Pro plan (`expected_goals` label). Cache keyed by `af_fixture_id` (one call returns both teams). Competition-specific: reuses `recent_cache[(team_id, league_id, season)]` from Phase 11.
- **Phase 11 (complete):** Recent-match tooltip data for form pips. Fetches last 5 completed fixtures per team in the same league+season (`get_fixtures(team_id, league_id, season, last=5)`). Validates W/D/L tail against stored form string before storing — stores null on mismatch. Fallback ("W · Seier" etc.) always shown when data unavailable. Norwegian opponent names normalised via `AF_TO_DISPLAY` at ingestion time and at API response time.
- **Phase 10 (complete):** Probability architecture audit. NT expert/public percentages removed from all model probability pathways. Test suite `tests/test_model_independence.py` (9 tests). Architecture in `docs/probability_architecture.md`.
- **Phase 9 (complete):** Generation-based tracking (`coupon_generations`, `generation_picks`, `generation_results`). Auto-saves every `POST /v1/optimize`. History page "Strategi-analyse" section with hit rates, avg PVR, ROI per strategy.
- **UI polish (complete):** SyncStatusPanel removed from sidebar. Pick badge amber → neutral slate. EdgeBadge positive amber → emerald. ShapePanel halvdekk → slate-500, heldekk → emerald-600. TopBar gradient → subtle slate. Coverage pip `{score}/4` text removed. Row height py-3 → py-2.5. Prob bar B color → emerald.
- **Logo task (NOT IMPLEMENTED):** Concept: football + Q + cow-horn shape. Do not implement without explicit instruction.
- **Phase 8B/8C:** Still pending. Model calibration and payout tracking.

**Evaluation baseline:** Week 25/2026 is the real baseline — all 36 fixtures enriched (4/4 for WC/2.Div), WC team name mappings fixed, Norsk 2. Divisjon mapped. Phase 8A baseline (Week 24/2026 Midtuke) was cleared with the old snapshot data.

See `docs/roadmap.md` for completed phases and future roadmap.

## Architecture

**Entry points:**
- `app.py` — Streamlit web UI (single file; all UI + CSS)
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
- `analysis/market_models.py` — Poisson BTTS/O/U models; `market_probs_from_enrichment()` uses Phase 13 venue-specific stats
- `data/loader.py` — SQLite (preferred) or flat-file `data/coupon_weekNN_YYYY.py` (fallback)

**FastAPI routes:**
| Route | Purpose |
|---|---|
| `GET /v1/coupons` | Active non-expired coupons (no args); or by `?week=&year=` for history |
| `POST /v1/optimize` | Run optimizer — accepts `coupon_id`, `strategy`, `budget` |
| `GET /v1/signals` | Signal board: all matches ranked by signal strength (model edge × CDS boost) |
| `GET /v1/insights` | Enriched insights: bookmaker odds + Pinnacle movement + Poisson + AF predictions |
| `GET /v1/sync/status` | Sync state: last refresh times, omsetning, tip change count |
| `POST /v1/sync/refresh-coupons` | Trigger NT refresh (background task — admin/backend only) |
| `POST /v1/sync/daily` | Trigger full daily sync |
| `GET /v1/analytics/strategy` | Per-strategy generation analytics (Phase 9) |
| `GET /v1/history` | All coupons with saved predictions (evaluated or pending) |
| `GET /v1/history/{coupon_id}` | Per-pick breakdown for one saved coupon |
| `GET /v1/bets` | List paper bets (Modellspill) |
| `GET /v1/bets/summary` | Aggregate performance metrics |
| `GET /v1/bets/bankroll` | Bankroll equity series |
| `POST /v1/bets/generate` | Generate bets from active coupon (edge ≥ 5pp) |
| `POST /v1/bets/scan` | Global 72h odds scan + candidate generation (edge ≥ 3pp) |
| `POST /v1/bets/settle/{fixture_id}` | Manually settle bets for a fixture |
| `GET /health` | Health check |

**Database:** SQLite via `db/connection.py`. Key tables: `fixtures`, `coupons`, `coupon_fixtures`, `odds`, `odds_snapshots`, `odds_markets`, `coupon_predictions`, `match_results`, `coupon_evaluations`, `fixture_stat_enrichment`, `fixture_estimated_prior`, `coupon_save_snapshot`, `pick_evaluations`, `model_bets`. Phase 9 tables: `coupon_generations`, `generation_picks`, `generation_results` (auto-populated by `/v1/optimize`; managed by `db/generation.py`). Phase 12 columns on `fixture_stat_enrichment`: `home_recent_fixture_stats TEXT`, `away_recent_fixture_stats TEXT` (JSON). Phase 13 columns on `fixture_stat_enrichment`: `league_size INTEGER`, `home_avg_goals_for_home REAL`, `home_avg_goals_against_home REAL`, `away_avg_goals_for_away REAL`, `away_avg_goals_against_away REAL`, `home_clean_sheets_home INTEGER`, `away_clean_sheets_away INTEGER`.

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
| `app/page.tsx` | Signal board — matches ranked by edge × CDS |
| `app/signaler/page.tsx` | Kupong-intelligens analyst view — model vs folket |
| `app/kupong/page.tsx` | Coupon builder (replaces legacy coupon page) |
| `app/coupon/page.tsx` | Legacy coupon optimizer page — all layout, queries, sidebar |
| `app/oddstips/page.tsx` | Modellspill — bankroll chart, bets list, market signals |
| `app/historikk/page.tsx` | History — generation performance, evaluated coupons |
| `app/strategien/page.tsx` | Systemspill — system library, Cartesian generator, Explain Mode |
| `app/home/page.tsx` | Marketing home — hero + terminal panel |
| `app/modellen/page.tsx` | Model explanation page |
| `app/om/page.tsx` | About page |
| `components/MatchTable.tsx` | 12-match table with conviction dots, prob bars, edge badges |
| `components/MetricsRow.tsx` | P(win), PVR, rows, cost metric cards |
| `components/StrategySelector.tsx` | Safe / Balanced / Jackpot tabs |
| `components/CouponSelector.tsx` | Active coupon tabs (feeds from `list_active_coupons` via API) |
| `components/BudgetSelector.tsx` | Budget selector (32 / 96 / 192 / 384 NOK) |
| `components/SyncStatus.tsx` | Data freshness panel — passive, no manual refresh button |
| `components/SystemMatchRow.tsx` | Per-match row for Systemspill |
| `lib/systemLibrary.ts` | 42 NT system definitions — `category: "A" | "B"`, verified `n_full`/`n_half` for Category A |
| `lib/api.ts` | All API fetch functions |
| `lib/types.ts` | TypeScript mirrors of backend Pydantic schemas |
| `lib/utils.ts` | Formatting helpers: `formatRelative`, `formatUntil`, `secsUntil`, `fmtKr`, etc. |
| `lib/insights.ts` | `deriveOddstips()` — client-side signal derivation from InsightsResponse |

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
- **Market scan:** every 2 hours — `scan_af_market_odds()` + `generate_global_bet_candidates()`.
- **Auto-settle:** every 60 minutes — settles pending bets with results in `match_results`.
- **Freeze check:** every 5 minutes — auto-freezes active coupons within FREEZE_WINDOW_MINUTES of deadline.
- State: `data/sync_state.json` (thread-safe, atomic writes via `backend/sync_state.py`).
- Never calls `sync.py` functions that contain `sys.exit()`.

The Next.js frontend polls `/v1/sync/status` on an adaptive interval (5 s when running, 30–120 s by deadline proximity). **There is no manual refresh button in the user UI.**

## Frontend Design Rules

**Before writing, modifying, or reviewing any frontend code, invoke the `frontend-design` skill. No exceptions.**

This applies to: React components, Next.js pages, Tailwind styling, layout changes, tables, cards, dashboards, navigation, mobile responsiveness, visual redesigns.

### Design Identity

TippeIQ is a **premium sports intelligence platform**, not a sportsbook.

Preferred inspirations: Football Manager, FotMob, SofaScore, Flashscore, Bloomberg Terminal, professional trading platforms, modern sports analytics dashboards.

Avoid: Casino websites, gambling landing pages, neon-heavy dashboards, crypto dashboards, excessive glassmorphism, excessive gradients, excessive glow effects.

### Visual Direction

- **Theme:** Near-black canvas (`#0A0A0B`), gold as primary accent, indigo for crowd mispricing signals, green for positive outcomes, red for actual losses only.
- **Design priorities (in order):** Data clarity → information hierarchy → fast scanning → professional appearance → compact layouts → meaningful visualizations.
- **Not priorities:** Fancy animations, decorative effects, visual clutter, empty marketing space.

### Information Design Rules

Always prefer charts over paragraphs, visual comparisons over repeated numbers, team-vs-team graphics over text explanations, compact analytical summaries.

**Never show the same information twice.** If model probabilities are already in the main table, do not repeat them in the expanded card — use the card for new information.

Valuable information for cards: league position, form, goals scored/conceded, home/away strength, momentum, streaks, clean sheets, team logos, relative strengths, API-Football statistics.

### Expanded Match Cards

Cards must explain **WHY the model likes a selection** using API-Football statistics, team comparisons, strength indicators, signal conflicts, and contextual insights.

Do NOT repeat in cards: Model %, public %, edge, VI, CDS — these are already visible in the main table.

### Screenshot-Driven Development

For all meaningful frontend changes:
1. Generate screenshots.
2. Review screenshots critically.
3. Identify visual weaknesses.
4. Improve before considering the task complete.

Never assume the UI is good without visual verification.

## Critical Rules

- **Probability independence (Phase 10 invariant):** Model probability (`match.prob_h/u/b`) must NEVER use NT public percentages, NT expert percentages, or any derivative of public/crowd data. These are Layer 2 (value) inputs only. See `docs/probability_architecture.md`. Enforced by `tests/test_model_independence.py`.
- **Single pipeline:** `process_match() → run_model() → classify_match() → optimize_coupon()` is used identically in app.py, Statistikk page, FastAPI, and verify_model.py. Do not branch it.
- **Bookmaker dominance:** bookmaker prior always has ≥87% weight. AF stats can adjust by at most ±`_MAX_ADJ` (defined in `analysis/model.py`).
- **Do not add new strategies or change strategy parameters** without explicit instruction.
- **Do not implement Elo, xG, or additional AI models** without explicit instruction.
- **estimated_prior is not bookmaker odds** — never write to `odds` or `odds_snapshots`. Validate check 24 enforces zero overlap.
- **Modellspill 1X2 uses NT Oddsen odds** — `generate_global_bet_candidates()` only generates 1X2 bets when `nt_oddsen_odds_snapshot` has a matching row (max 6h old, scraped by `ingestion/nt_oddsen_playwright.py`). Fixtures without NT match → no 1X2 bet. BTTS/O/U still uses AF/Bet365 odds_markets. The Firecrawl scraper (`ingestion/nt_oddsen_scraper.py`) is dev-only — do NOT import it from production. Do not claim NT odds in the UI unless the bet's `bookmaker` field is "NT Oddsen".
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
- **Phase 11 — recent-match tooltip data must be competition-specific:** `get_fixtures(team_id, last=5)` fetches across *all competitions* and must never be used alone. Always pass `league_id=af_league_id, season=af_season` so the fetched sequence matches the form string (which comes from `get_team_statistics(league_id, season, team_id)`). Cache key is `(team_id, league_id, season)`, not just `team_id`. Before storing, derive the W/D/L tail from the fetched fixtures and compare it to the stored form string — store `null` if they do not match. Fallback ("W · Seier" / "D · Uavgjort" / "L · Tap") is always better than showing wrong opponents. Root cause: WC teams that have played 1–2 WC games showed cross-competition friendlies as tooltip data. Implemented in `ingestion/enrich_fixtures.py`: `_parse_recent_matches(form_str=...)` and `recent_cache` keyed by `(team_id, league_id, season)`.
- **WC standings — within-group rank, first-match-wins:** The API-Football `/standings` response for multi-group tournaments (WC, UCL group stage) includes both specific group tables ("Group A"–"Group L", rank 1–4 each) and an aggregate "Group Stage" table with a global/cross-group rank. The enrichment loop uses `enumerate(group, 1)` for the within-group position AND a `if tid in team_data: continue` first-match-wins guard so the aggregate table never overwrites the correct group rank. Without this, Spain shows as position 6 (their "Group Stage" aggregate rank) instead of 3 (their rank in Group H). Implemented in `ingestion/enrich_fixtures.py: _fetch_enrichment()`.
- **Norwegian team name normalization:** `opponent_name` in recent-match tooltip JSON comes from API-Football and uses ASCII English names (`Stabaek`, `Strommen`, `hodd`, `Asane`). The single source of truth is `AF_TO_DISPLAY` in `ingestion/api_football.py` and `normalize_opponent_name()`. Applied at two points: (1) ingestion time in `_parse_recent_matches()` (new data), (2) API response time in `backend/main.py:_parse_recent_matches()` (existing stored data). Do not hardcode name fixes in React components. The main table uses `teams.name_local` from the DB (already correct) — normalization is only needed for opponent names inside the tooltip JSON.
- **Phase 12 — fixture stats competition coverage:** `/fixtures/statistics` is available for WC and Eliteserien on the Pro plan; OBOS-ligaen and Toppserien return empty. xG is available as `expected_goals` (not Enterprise-only). Cache key is `af_fixture_id` (one call returns both teams). Never mix competitions — `fix_stats_cache` is fed from `recent_cache[(team_id, league_id, season)]` which is already competition-filtered.
- **Phase 13 — league size from standings, not position:** `league_size` in `fixture_stat_enrichment` is the real team count from `/standings`, not estimated from positions. For multi-group tournaments (WC), use the size of the group containing the home or away team (4 for WC group stage, not 48 total teams). Logic is in `_fetch_enrichment()` in `ingestion/enrich_fixtures.py`. `PositionBar` in `MatchTable.tsx` takes `total: number | null` — when null (no standings data), the denominator is hidden rather than showing a misleading "av X".
- **Phase 13 — venue-specific stats only shown when games played > 0:** `home_avg_goals_for_home` and related columns can be 0.0 when a WC team was always listed as "away" in the API fixture (no home games played). The frontend guards these rows with `hHomeGames > 0` / `aAwayGames > 0` (derived by parsing the W/D/L counts in `home_home_record` / `away_away_record`). Do not remove this guard — showing "0.0 | MÅL/KAMP | X.X" for a team with 0 home games misleads the user.
- **Systemspill — Category A is Cartesian product, not an NT reduction matrix:** `generateRows()` produces all combinations of selected sign sets (3^n_full × 2^n_half = rows). The row count matches the NT system name, but the mathematical coverage guarantee does not — NT's named systems are combinatorial covering codes, not Cartesian products. Never represent Category A as "NT-compatible" or claim it has the same guarantees as the official system. Category B systems (32 of 42) require NT's proprietary reduction tables and are disabled. `n_full` and `n_half` in `systemLibrary.ts` are the unique factorization of `rows` into 3^a × 2^b — do not change them without re-verifying the row count formula.
- **Systemspill — rank-forced coverage for Category A:** `buildSystemProposal` with `system.category === "A"` must NEVER use `minCoverageThreshold` — it must always force-assign exactly `n_full` full-cover slots and `n_half` half-cover slots by coverage score rank, regardless of how confident the model is. Any threshold gating would break the row count (3^n_full × 2^n_half only holds when ALL slots are filled).
- **Modellspill — model quality tags are informational only:** `model_quality` stored in `model_bets` records which Poisson data source was used. It does not affect edge calculation or bet generation logic. Do not use it as a filter gate.
- **Red is for losses and errors only:** Never use red color for "model disagrees with crowd" or CDS signals. Crowd mispricing signals use indigo or gold. Red is reserved for: negative profit, negative ROI, losses, errors, drawdown.

## Detailed Documentation

Read the relevant doc before changing that area of the codebase:

| File | Contents |
|---|---|
| `docs/model_architecture.md` | Unified prediction engine, bookmaker prior, AF stats blend, estimated prior, CDS, value_h/u/b, odds source priority, pool value metrics (P(12/12), PVR, Poolverdi, VI, e_winners) |
| `docs/probability_architecture.md` | **Critical invariant**: probability layer must be independent of NT public/expert percentages. Layer 1/2/3 separation, allowed/forbidden inputs, verification rule, implementation map. |
| `docs/strategy_system.md` | Safe/Balanced/Jackpot — objectives, composite score formulas, shape objectives, halvdekk substitution, optimizer math, strategy invariants |
| `docs/payout_simulator.md` | Phase 7 Monte Carlo simulator, corrected denominator (+1 not +n_rows), Poisson variance, payout percentiles, e_winners, EV panel UI structure |
| `docs/data_pipeline.md` | NT API endpoint change (2026-06), AF enrichment, odds fallback order, sync.py commands reference, DB tables, weekly workflow |
| `docs/roadmap.md` | Completed phases (1–7), Phase 8 scope, current architecture + code map, Streamlit pages, known limitations, future roadmap |
| `docs/migration_status.md` | Full current state snapshot: active coupons, omsetning, file inventory, system start commands, known issues |
