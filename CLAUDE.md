# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the Streamlit web app (primary interface)
streamlit run app.py

# Run the original CLI tool (no Streamlit dependency)
python main.py

# Run test scripts (Playwright-based, not pytest)
python test_week23.py
python test_paste.py
```

Streamlit is installed via Anaconda (`C:\Users\kimme\anaconda3`). If `streamlit` is not on PATH, activate the base conda environment first. Log output goes to `logs/`.

## Architecture

**Two independent entry points share the same analysis pipeline:**

- `main.py` — original CLI tool, zero external dependencies, prompts for odds interactively
- `app.py` — Streamlit web UI, single file, all UI code and CSS injection

**Analysis pipeline** (used by both entry points):

```
decimal odds
    → analysis/probability.py   normalize odds → prob_h / prob_u / prob_b
    → analysis/classifier.py    classify match → banker / standard / half_cover / full_cover / uncertain
    → analysis/optimizer.py     exhaustive search for (n_full, n_half) maximizing rows ≤ budget
```

`Match` in `models/match.py` is a plain dataclass that carries odds in and probabilities + classification out. It is mutated in place by `process_match()` and `classify_match()`.

**Data layer:** Weekly fixture and odds data lives in `data/coupon_weekNN_YYYY.py` as a hardcoded `COUPONS` dict. Each key (`"midtuke"`, `"lordag"`, `"sondag"`) maps to a label, deadline, and list of 12 `(home, away, odds_h, odds_u, odds_b)` tuples. To add a new week, create a new file in `data/` following the same structure and update the import in `app.py`.

**Streamlit UI layout** (`app.py`):

- Full-width header (HTML injected via `st.markdown`)
- Two-column split `[5, 6]`: left = controls + coupon card; right = analysis table
- Coupon card and analysis table are rendered as raw HTML via `components.html()` and `st.markdown(unsafe_allow_html=True)` — they are not Streamlit widgets
- Selector rows (coupon tabs, budget cards) use `st.columns` + `st.button` with `type="primary"/"secondary"` toggled by session state

## Streamlit CSS notes

All CSS is injected once at the top of `app.py` via `st.markdown("<style>…</style>")`.

**Critical:** Streamlit ≥1.40 renamed the column element's `data-testid` from `"column"` to `"stColumn"`. The selector rows target both:
```css
[data-testid="stColumn"], [data-testid="column"]
```

Selector rows use `display: flex` (not grid) with `flex: 1 1 0` on columns so all buttons are equal-width regardless of label length. The `st.button()` widget wraps the `<button>` in a `<div data-testid="stButton">` — target this wrapper with `width: 100%; display: block` to make buttons fill their column.

Button state (selected = gold fill, unselected = ghost) is driven by `type="primary"/"secondary"` — target both `button[kind="primary"]` and `[data-testid="stBaseButton-primary"]` for robustness.

## Resume Instructions

When starting a new Claude Code session on this project:

1. **Read CLAUDE.md** — confirms what is already built; do not re-implement completed phases.
2. **Run `python sync.py --validate`** — confirms the database is clean and which checks are warnings vs failures.
3. **Run `python sync.py --status`** — shows which coupons and fixtures are in the DB for the current week.
4. **Confirm app state** — if the Streamlit app is needed, run `streamlit run app.py` and visually verify the main page and existing pages load without errors before touching any code.
5. **Only then continue with new work** — if the user asks to start Phase 4, confirm the above checks pass first and agree on the specific scope before writing any code.

Do not assume prior conversation context carries over. Always re-derive current state from the code and database.

---

## Optimizer math

The optimizer brute-forces all `(n_full_covers, n_half_covers)` pairs where `3^n_full * 2^n_half ≤ budget`. This is O(n²) over at most 13 matches — always fast. The four budget presets (32/96/192/384 NOK) are deliberately chosen to achieve exact full-budget coverage.

Thresholds in `analysis/classifier.py` control match classification and can be tuned without touching any other file.

## Current Project Status

### Completed phases

| Phase | Description | Status |
|---|---|---|
| 1 | NT coupon ingestion — fixtures, teams, odds from Norsk Tipping API | Complete |
| 1.5 | Validation suite + Team Review page | Complete |
| 2 | Historical results engine — save predictions, enter results, evaluate hit/cover rate | Complete |
| 3 | Odds movement + CLV tracking — timestamped snapshots, closing line, CLV per fixture | Complete |

### Current architecture

```
Entry points
  app.py              Streamlit web UI (primary)
  main.py             Original CLI tool (no external deps)
  sync.py             Data ingestion and maintenance CLI

Analysis pipeline (shared)
  analysis/probability.py   decimal odds → normalized implied probabilities
  analysis/classifier.py    classify match (banker/standard/half_cover/full_cover/uncertain)
  analysis/optimizer.py     exhaustive (n_full, n_half) search within budget

Database  (SQLite via db/connection.py)
  db/schema.py        DDL for all tables; init_db() is idempotent
  db/registry.py      teams + competitions CRUD
  db/coupon.py        coupons + coupon_fixtures + odds CRUD
  db/history.py       coupon_predictions + match_results + coupon_evaluations
  db/odds_movement.py odds_snapshots + CLV calculation

Ingestion
  ingestion/norsk_tipping.py   NT gameDays API → coupons + fixtures + teams
  ingestion/odds_api.py        The Odds API (Pinnacle) → odds + snapshots
  ingestion/seed.py            flat-file fallback (data/coupon_weekNN_YYYY.py)

Models
  models/match.py     Match dataclass (odds in, probs + classification out)
```

### Streamlit pages

| File | Page | Purpose |
|---|---|---|
| `app.py` | Main | Coupon selector, analysis table, save coupon (Lagre kupong) |
| `pages/1_Team_Review.py` | Team Review | Inspect teams flagged for manual gender/age review |
| `pages/2_Results.py` | Resultater | Enter match scores after games are played |
| `pages/3_History.py` | Historikk | Evaluated coupons — hit rate, cover rate, CLV |
| `pages/4_Odds_Movement.py` | Odds Movement | Pinnacle odds time series, opening/closing, movement per fixture |

### sync.py commands

```
python sync.py                        full sync: NT coupons + Pinnacle odds
python sync.py --daily                safe all-in-one: NT + odds + snapshots + validate + summary
python sync.py --refresh-coupons      force-refresh from NT API (clears stale fixture data, keeps predictions)
python sync.py --week N --year YYYY   explicit week/year for any command
python sync.py --seed-only            flat-file seed (no API calls)
python sync.py --nt-only              NT fixture fetch only
python sync.py --odds-only            Pinnacle odds only (fixtures must exist)
python sync.py --odds-snapshot        fetch odds and append timestamped snapshot
python sync.py --mark-closing-odds    mark last pre-kickoff snapshot as closing line
python sync.py --status               show DB contents for the week
python sync.py --validate             18-point data integrity checks (PASS/WARN/FAIL)
python sync.py --review               teams flagged for manual gender/age review
python sync.py --results-status       show coupons with predictions but missing results
python sync.py --evaluate             compute hit rate / cover rate for all evaluated coupons
python sync.py --nt-debug             print raw NT API response
```

### Database features implemented

- `teams` — canonical team registry with gender, age_group, team_type, country_iso
- `team_aliases` — fuzzy-match aliases per source (NT, Betradar)
- `competitions` — competition registry
- `fixtures` — one row per match; nt_match_id, kickoff_utc, source, confidence
- `coupon_fixtures` — junction with match_number, expert/public tip percentages
- `coupons` — weekly coupon metadata; deadline, day_type, nt_game_day_id
- `odds` — latest odds per fixture/source (used by the analysis pipeline)
- `odds_snapshots` — every timestamped odds fetch; is_closing_snapshot flag; basis for CLV
- `coupon_predictions` — saved recommendations at submission time
- `match_results` — entered scores and 1X2 outcome
- `coupon_evaluations` — hit_rate, cover_rate, all_12_correct per coupon
- `coupon_log` — audit log for ingestion events

### NT API — endpoint change (2026-06) and data-source rules

#### What changed and why

The Norsk Tipping website migrated to a new backend in mid-2026. As a result:

| | Old (pre-2026-06) | New (current) |
|---|---|---|
| **Endpoint** | `https://api.norsk-tipping.no/Content/v1/api/pages/sport/tipping/spill` | `https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/live-info` |
| **Website URL** | `/tippekupongen` | `/sport/tipping` |
| **HTTP response** | JSON with gameDays list | JSON with gameDays list (different shape) |
| **Status now** | 204 No Content (dead) | 200 OK (active) |

The response structure also changed significantly:
- **Tips** are now parallel arrays indexed by match position (`game.tips.fullTime.expert[i]`), not embedded per-match.
- **Team IDs** are integers (e.g. `100000807`), not strings.
- **Country codes** are not provided; the code infers `"INT"` for national-tournament teams and `"CLUB"` for domestic-league teams.
- **Deadline** comes from `game.sales.fullTime.saleStopDate`.
- **Game day ID** is `game.gameEngineBetObjectId`.

The parser for the new format lives in `ingestion/norsk_tipping.py` → `parse_live_info_response()`. The old parser (`parse_game_days()`) is kept as a fallback for the legacy endpoint and any future HTML scrape.

#### Data-source priority rule

**Live NT API data must always take precedence over flat-file data.**

The fetch order in `fetch_game_days()`:
1. New endpoint (`PoolGamesSportInfo/live-info`) + `parse_live_info_response()` — primary
2. Old endpoint (`Content/v1/api/…/spill`) + `parse_game_days()` — legacy fallback
3. HTML scrape of `https://www.norsk-tipping.no/sport/tipping` — last resort

The loader in `data/loader.py` follows:
1. SQLite DB for the current ISO week — preferred
2. Flat-file `data/coupon_weekNN_YYYY.py` for the current week — fallback
3. Most recent flat-file found in `data/` — last resort (never hardcoded to a specific week)

Flat-file data is only used when **no NT API data is available for the current week**. If NT API coupons exist in the DB, the loader always returns those — even if they have no Pinnacle odds yet (the app uses 3.0/3.0/3.0 equal-probability placeholders when odds are missing).

#### Weekly refresh flow

```bash
# Standard daily run (safe to repeat; skips unchanged data)
python sync.py --daily

# Force-refresh when fixtures have changed or the app shows stale coupons
python sync.py --refresh-coupons
#   → fetches live NT coupons
#   → clears and re-inserts coupon_fixtures for the current week
#   → leaves coupon_predictions and match_results untouched
#   → runs validation and prints a summary
```

Use `--refresh-coupons` instead of `--nt-only` whenever:
- The app is showing fixtures from a previous week
- NT has updated a coupon after the initial import (postponed match, lineup change)
- A new week's coupons just appeared on the NT website

#### Verifying the app shows correct coupons

```bash
# 1. Confirm DB has the right week and source
python sync.py --status
#    Should show week 24/2026, source=nt_api, 12 fixtures per coupon

# 2. Confirm no integrity issues
python sync.py --validate
#    Should be PASS — all 18 checks clean (or PASS with expected WARNs on manual coupons)

# 3. Confirm the loader returns the right data
python -c "from data.loader import load_coupons; c=load_coupons(); print(list(c.keys())); [print(k, c[k]['label'], c[k]['deadline'][:10]) for k in c]"
#    Should print midtuke/lordag/sondag with correct 2026 dates

# 4. Visually verify in the app
streamlit run app.py
#    Coupon tabs should show Midtuke/Lørdag/Søndag with the correct deadline dates.
#    Fixtures should match what Norsk Tipping shows on their website.
```

### Current known limitations

- **ODDS_API_KEY not set** — Pinnacle odds are not being fetched. Set `ODDS_API_KEY` in `.env` to activate. When odds are missing, the app uses equal-probability placeholders (3.0/3.0/3.0) so coupons remain visible and usable.
- **country_iso for NT-API teams** — new API does not provide country codes; national-tournament teams get `"INT"`, domestic-league teams get `"CLUB"`. Can be corrected manually in the DB.
- **No NT match IDs on manual coupons** — week 23 data was seeded from flat file; expected WARN in `--validate`.
- **No day_type on manual coupons** — same root cause; expected WARN.
- **No backtesting** — predictions are saved but there is no calibration or edge-vs-result analysis yet.
- **Team name matching is fuzzy substring** — works for major leagues; may miss NT teams with unusual spellings.
- **Odds pipeline uses only Pinnacle** — no fallback bookmaker if Pinnacle is not available on The Odds API.

### Next recommended phase

**Phase 4: Team Strength / Power Rating Engine**

Goal: add a lightweight statistical prior alongside the odds prior so recommendations are not 100% dependent on bookmaker lines.

Candidate signals (high signal-to-noise only):
- Club Elo ratings — `clubelo.com` free API; covers most European club teams
- eloratings.net — national team Elo (scrape)
- Recent form — last 5 results from NT or API-Football

Probability blend target: `0.5 × odds_prior + 0.5 × elo_model`

**Do not implement Elo, xG, or AI without an explicit instruction to do so.**

---

## Weekly workflow

```
# 0. Start of week (Monday) — import new coupons
python sync.py --refresh-coupons
#    Fetches live NT coupons for the current ISO week, clears stale fixture
#    data, and verifies the DB.  Run this as soon as NT publishes the week's
#    coupons (usually Monday morning for Midtuke, same day for Lørdag/Søndag).
#    If NT hasn't published yet (204 / no content), try again later.

# 1. Every day during the week (Monday–Friday)
python sync.py --daily
#    Fetches NT coupons (skips if unchanged), updates Pinnacle odds, saves
#    timestamped snapshots, runs validation, and prints a summary.
#    Safe to run multiple times — duplicates are silently skipped.

# 2. Before the deadline — open the app and save your coupon
streamlit run app.py
#    Select coupon, review recommendations, click "Lagre kupong".

# 3. After kickoff (Saturday/Sunday evening)
python sync.py --mark-closing-odds
#    Marks the last pre-kickoff snapshot as the closing line for each fixture.
#    Required for CLV calculation.

# 4. After matches are played — enter results in the app
streamlit run app.py
#    Navigate to the Resultater page, enter scores.

# 5. Compute performance metrics
python sync.py --evaluate
#    Calculates hit rate, cover rate, and all-12 flag for each saved coupon.

# 6. Review results in the app
#    Historikk page  — hit rate, cover rate, CLV per coupon
#    Odds Movement page — opening/closing line, movement direction per fixture
```
