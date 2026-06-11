# Data Pipeline

## NT API — Endpoint Change (2026-06)

The Norsk Tipping website migrated to a new backend in mid-2026.

| | Old (pre-2026-06) | New (current) |
|---|---|---|
| **Endpoint** | `https://api.norsk-tipping.no/Content/v1/api/pages/sport/tipping/spill` | `https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/live-info` |
| **Website URL** | `/tippekupongen` | `/sport/tipping` |
| **Status now** | 204 No Content (dead) | 200 OK (active) |

Response structure changes:
- **Tips** are now parallel arrays indexed by match position (`game.tips.fullTime.expert[i]`), not embedded per-match.
- **Team IDs** are integers (e.g. `100000807`), not strings.
- **Country codes** are not provided; code infers `"INT"` for national-tournament teams and `"CLUB"` for domestic-league teams.
- **Deadline** comes from `game.sales.fullTime.saleStopDate`.
- **Game day ID** is `game.gameEngineBetObjectId`.

Parser for new format: `ingestion/norsk_tipping.py → parse_live_info_response()`. Old parser (`parse_game_days()`) kept as fallback.

### Fetch order in `fetch_game_days()`

1. New endpoint (`PoolGamesSportInfo/live-info`) + `parse_live_info_response()` — primary
2. Old endpoint (`Content/v1/api/…/spill`) + `parse_game_days()` — legacy fallback
3. HTML scrape of `https://www.norsk-tipping.no/sport/tipping` — last resort

---

## Data Source Priority

**Fixtures (source of truth):**
1. Norsk Tipping API (`nt_api`)

**Odds / probability prior (highest priority first):**
1. Pinnacle via The Odds API (`pinnacle`)
2. Other bookmaker odds (`norsk_tipping`, `manual`, `betsson`, ...)
3. API-Football odds (`api_football`) — Bet365 → William Hill → Marathonbet → 10Bet → first available
4. Model-estimated prior (`model_estimated`) — stored in `fixture_estimated_prior`, **not** in `odds`; NT expert tips (60%) + stats (40%)
5. NT expert tips fallback (runtime only — converts expert% to implied decimal odds; not persisted)
6. Equal-probability placeholder (3.0/3.0/3.0) — last resort

**Statistics / form:**
1. API-Football (`fixture_stat_enrichment`)

### Loader priority (`data/loader.py`)

1. SQLite DB for the current ISO week — preferred
2. Flat-file `data/coupon_weekNN_YYYY.py` for the current week — fallback
3. Most recent flat-file found in `data/` — last resort (never hardcoded to a specific week)

**Live NT API data must always take precedence over flat-file data.** Flat-file data is only used when no NT API data is available for the current week.

---

## API-Football Odds Fallback

Module: `ingestion/api_football_odds.py → ingest_af_odds_fallback()`. Run automatically by `--daily` and `--refresh-coupons`.

- **Source priority:** pinnacle → norsk_tipping → manual → api_football. AF odds are inserted with `source='api_football'` and only used when no higher-priority odds exist.
- **Never overwrites:** checks `SELECT 1 FROM odds WHERE fixture_id = ?` before every AF call. If any odds row exists for a fixture, AF odds are skipped entirely.
- **Bookmaker priority:** Bet365 → William Hill → Marathonbet → 10Bet → first available.
- **Rate limiting:** 2.1 s delay between actual API calls (AF limit: 30 req/min). Skipped fixtures do not count against the delay.
- **Coverage:** all leagues in `ingestion/api_football.py → _NT_COMPETITION_MAP` with AF league IDs — Women's WC Qual UEFA (league 880), Eliteserien, OBOS, Toppserien, Champions League, Nations League, FIFA World Cup.

---

## Model-Estimated Prior

Module: `analysis/estimated_prior.py → compute_estimated_prior()`. Run automatically by `--daily` and `--refresh-coupons` after AF odds.

- **Only for fixtures with no bookmaker odds** — skips any fixture that already has a row in `odds`.
- **Signal blend:** NT expert tips at 60% weight + stats-based home edge at 40%. Returns `None` when neither signal is available.
- **Confidence:** 0.20 (stats only, no expert) → 0.35 (stats only) → 0.50 (expert only) → 0.65 (both).
- **Stored in `fixture_estimated_prior`** — never written to `odds` or `odds_snapshots`. CLV is only calculated from real bookmaker closing lines.
- Validate check 24 enforces zero overlap with the `odds` table.

---

## sync.py Commands

```bash
python sync.py                          # full sync: NT coupons + Pinnacle odds
python sync.py --daily                  # all-in-one: NT + Pinnacle + AF enrichment + AF odds + estimated priors + validate
python sync.py --refresh-coupons        # force-refresh NT coupons + enrichment + AF odds fallback (start-of-week)
python sync.py --week N --year YYYY     # explicit week/year for any command
python sync.py --seed-only              # flat-file seed (no API calls)
python sync.py --nt-only                # NT fixture fetch only
python sync.py --odds-only              # Pinnacle odds only (fixtures must exist)
python sync.py --odds-snapshot          # fetch odds and append timestamped snapshot
python sync.py --mark-closing-odds      # mark last pre-kickoff snapshot as closing line
python sync.py --enrich-fixtures        # match NT fixtures to API-Football, store stats/form
python sync.py --af-odds                # fill missing odds from API-Football (manual/debug)
python sync.py --estimated-priors       # compute model-estimated priors for fixtures with no bookmaker odds
python sync.py --status                 # show DB contents for the week
python sync.py --validate               # data integrity checks (PASS/WARN/FAIL) — 24 checks
python sync.py --review                 # teams flagged for manual gender/age review
python sync.py --results-status         # show coupons with predictions but missing results
python sync.py --evaluate               # compute hit rate / cover rate for all evaluated coupons
python sync.py --nt-debug               # print raw NT API response
```

Use `--refresh-coupons` instead of `--nt-only` whenever:
- The app is showing fixtures from a previous week
- NT has updated a coupon after the initial import
- A new week's coupons just appeared on the NT website

---

## Database Tables

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
- `fixture_stat_enrichment` — AF stats: form last 5, standings position, goals, H2H
- `api_football_fixture_links` — NT fixture_id → AF fixture_id mapping + confidence
- `fixture_estimated_prior` — model-derived H/U/B for fixtures with no bookmaker odds (source='model_estimated'); **never written to `odds` or `odds_snapshots`**

---

## Weekly Workflow

```bash
# 0. Start of week (Monday) — import new coupons
python sync.py --refresh-coupons
# Fetches live NT coupons, clears stale fixture data, runs enrichment + AF odds + validation.
# Run as soon as NT publishes the week's coupons (usually Monday morning).

# 1. Every day during the week
python sync.py --daily
#   [1/6] NT coupons          — fetch/update fixtures
#   [2/6] Pinnacle odds       — update + snapshot (skipped if ODDS_API_KEY not set)
#   [3/6] AF enrichment       — stats/form for new/unmatched fixtures
#   [4/6] AF odds fallback    — fills any fixture still missing odds
#   [4b/6] Estimated priors   — model-estimated H/U/B for fixtures still without bookmaker odds
#   [5/6] Validation          — PASS/WARN/FAIL integrity checks (24 checks)
# Safe to run multiple times — all steps are idempotent.

python sync.py --validate     # re-check integrity at any time

# 2. Before the deadline
streamlit run app.py
# Select coupon, review recommendations, enter omsetning, compare strategies, click "Lagre kupong".

# 3. After kickoff (Saturday/Sunday evening)
python sync.py --mark-closing-odds
# Marks the last pre-kickoff Pinnacle snapshot as the closing line for each fixture.
# Required for CLV calculation.

# 4. After matches are played — enter results in the app
streamlit run app.py   # navigate to Resultater page, enter scores

# 5. Compute performance metrics
python sync.py --evaluate
# Calculates hit rate, cover rate, and all-12 flag for each saved coupon.

# 6. Review in app
# Historikk page  — hit rate, cover rate, CLV per coupon
# Odds Movement page — opening/closing line, movement direction per fixture
```

---

## Verifying the App Shows Correct Coupons

```bash
# 1. Confirm DB has the right week and source
python sync.py --status
#    Should show week 24/2026, source=nt_api, 12 fixtures per coupon

# 2. Confirm no integrity issues
python sync.py --validate
#    Should be PASS — all 24 checks clean (or PASS with expected WARNs: check 7 for AF/betsson odds)

# 3. Confirm the loader returns the right data
python -c "from data.loader import load_coupons; c=load_coupons(); print(list(c.keys())); [print(k, c[k]['label'], c[k]['deadline'][:10]) for k in c]"
#    Should print midtuke/lordag/sondag with correct 2026 dates

# 4. Visually verify in the app
streamlit run app.py
#    Coupon tabs should show Midtuke/Lørdag/Søndag with the correct deadline dates.
```
