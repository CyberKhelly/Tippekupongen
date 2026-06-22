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

**Phase 13 — Expanded match card: league size fix + venue-specific stats.** (2026-06-22)

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
- `data/loader.py` — SQLite (preferred) or flat-file `data/coupon_weekNN_YYYY.py` (fallback)

**FastAPI routes:**
| Route | Purpose |
|---|---|
| `GET /v1/coupons` | Active non-expired coupons (no args); or by `?week=&year=` for history |
| `POST /v1/optimize` | Run optimizer — accepts `coupon_id`, `strategy`, `budget` |
| `GET /v1/sync/status` | Sync state: last refresh times, omsetning, tip change count |
| `POST /v1/sync/refresh-coupons` | Trigger NT refresh (background task — admin/backend only) |
| `POST /v1/sync/daily` | Trigger full daily sync |
| `GET /v1/analytics/strategy` | Per-strategy generation analytics (Phase 9) |
| `GET /health` | Health check |

**Database:** SQLite via `db/connection.py`. Key tables: `fixtures`, `coupons`, `coupon_fixtures`, `odds`, `odds_snapshots`, `coupon_predictions`, `match_results`, `coupon_evaluations`, `fixture_stat_enrichment`, `fixture_estimated_prior`, `coupon_save_snapshot`, `pick_evaluations`. Phase 9 tables: `coupon_generations`, `generation_picks`, `generation_results` (auto-populated by `/v1/optimize`; managed by `db/generation.py`). Phase 12 columns on `fixture_stat_enrichment`: `home_recent_fixture_stats TEXT`, `away_recent_fixture_stats TEXT` (JSON). Phase 13 columns on `fixture_stat_enrichment`: `league_size INTEGER`, `home_avg_goals_for_home REAL`, `home_avg_goals_against_home REAL`, `away_avg_goals_for_away REAL`, `away_avg_goals_against_away REAL`, `home_clean_sheets_home INTEGER`, `away_clean_sheets_away INTEGER`.

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

## Frontend Design Rules

**Before writing, modifying, or reviewing any frontend code, invoke the `frontend-design` skill. No exceptions.**

This applies to: React components, Next.js pages, Tailwind styling, layout changes, tables, cards, dashboards, navigation, mobile responsiveness, visual redesigns.

### Design Identity

TippeQongen is a **sports analytics product**, not a sportsbook.

Preferred inspirations: Football Manager, FotMob, SofaScore, Flashscore, Bloomberg Terminal, professional trading platforms, modern sports analytics dashboards.

Avoid: Casino websites, gambling landing pages, neon-heavy dashboards, crypto dashboards, excessive glassmorphism, excessive gradients, excessive glow effects.

### Visual Direction

- **Theme:** Moneyball Black — pure black background (`#050505`), amber/yellow as primary accent, emerald for positive signals, red for negative signals, minimal blue.
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
