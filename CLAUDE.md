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
    → analysis/model.py         unified model: bookmaker prior + AF stats adjustment; CDS
    → analysis/classifier.py    classify match → banker / standard / half_cover / full_cover / uncertain
    → analysis/optimizer.py     two-stage strategy-aware search for (n_full, n_half) shape
```

`Match` in `models/match.py` is a plain dataclass that carries odds in and probabilities + classification out. It is mutated in place by `process_match()`, `run_model()`, and `classify_match()`.

**Data layer:** Weekly fixture and odds data is loaded from SQLite (preferred) or `data/coupon_weekNN_YYYY.py` flat files (fallback) via `data/loader.py`.

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
2. **Run `python sync.py --validate`** — confirms the database is clean and which checks are warnings vs failures (24 checks total).
3. **Run `python sync.py --status`** — shows which coupons and fixtures are in the DB for the current week.
4. **Run `python verify_model.py`** — prints model probabilities, picks, and coverage for all 3 coupons; confirms the pipeline is consistent across Kampanalyse, Statistikk, and coupon generation.
5. **Confirm app state** — if the Streamlit app is needed, run `streamlit run app.py` and visually verify the main page and existing pages load without errors before touching any code.
6. **Only then continue with new work** — agree on specific scope before writing any code.

Do not assume prior conversation context carries over. Always re-derive current state from the code and database.

---

## Prediction Engine

The unified prediction engine (`analysis/model.py → run_model()`) blends multiple signals into final H/U/B probabilities for each fixture.

### Signal blend

1. **Bookmaker prior** (≥87% weight) — normalised implied probabilities from the best available odds source. This is always the dominant signal; the prior is computed in `analysis/probability.py` from decimal odds.
2. **Form adjustment** — AF stats (last 5 results for home/away separately) can nudge probabilities by at most ±`_MAX_ADJ` (defined in `analysis/model.py`). Home form and away form are tracked independently.
3. **Standings adjustment** — league position and goal difference contribute a small directional nudge. A large table gap amplifies the bookmaker signal slightly.
4. **Goals adjustment** — recent goals scored/conceded per match provide a marginal signal on top of standings.
5. **NT expert tips** — used only in the estimated_prior fallback (see below); not blended when bookmaker odds exist.

The stats adjustments are additive and bounded: the combined AF stats adjustment never pushes the final probability more than `_MAX_ADJ` away from the bookmaker prior, preserving bookmaker dominance.

### Crowd signals

After blending, the model computes three crowd-signal fields per fixture (stored in `Match`, read-only):

- **`value_h / value_u / value_b`** — pp difference between model probability and public tip percentage for each outcome. Positive = crowd underweights this outcome. Computed as `model_prob_pct − public_tip_pct`.
- **`crowd_disagreement_score` (CDS)** — pp difference between the model's top-pick model probability and the public's tip percentage for that same outcome. Measures how much the model and crowd disagree on the most likely result. Range 0–50pp. Does **not** change the recommended pick.

### Estimated prior fallback

When no bookmaker odds exist for a fixture (Norwegian 3. Division, some women's club fixtures), the model falls back to `analysis/estimated_prior.py`:

- NT expert tips (60% weight) + stats-based home edge (40%)
- Confidence 0.35–0.65 depending on which signals are available
- Stored in `fixture_estimated_prior`, **never** in `odds` or `odds_snapshots`
- Substantially less reliable than bookmaker-derived probabilities — P(win) and PVR figures should be treated with skepticism for these fixtures

---

## Odds Sources

Odds are drawn from the following sources in priority order. The pipeline stops at the first source that has data for a given fixture.

| Priority | Source | Table | Note |
|---|---|---|---|
| 1 | Pinnacle (via The Odds API) | `odds` | Best sharp market; requires `ODDS_API_KEY` in `.env` |
| 2 | Other bookmakers (`norsk_tipping`, `betsson`, `manual`) | `odds` | Used when Pinnacle unavailable |
| 3 | API-Football odds fallback | `odds` | Bet365 → William Hill → Marathonbet → 10Bet → first available; `source='api_football'` |
| 4 | Model-estimated prior | `fixture_estimated_prior` | NT expert tips (60%) + stats (40%); **not** in `odds` table |
| 5 | NT expert tips (runtime only) | — | Converted to implied decimal odds at runtime; not persisted |
| 6 | Equal-probability placeholder | — | 3.0/3.0/3.0; last resort |

**Norwegian 3. Division and some women's fixtures** are not covered by Pinnacle or API-Football. These fixtures use priority 4 (model-estimated prior) or priority 5 (NT expert tips runtime conversion). The Statistikk page shows `odds_source` per fixture — look for `model_estimated` or `nt_expert` to identify lower-confidence matches.

---

## Strategy System

Four named strategies control coverage depth, system shape, and halvdekk second-pick selection. Configured in `analysis/strategy.py` (StrategyConfig dataclass + STRATEGIES dict). Selected via `--strategy` in `verify_model.py` and `optimize_coupon(strategy=…)` in `analysis/optimizer.py`.

The optimizer runs in two stages:

**Stage 1 — Coverage ranking:** Each match is assigned a composite score. Lower score → receives deeper coverage (heldekk before halvdekk before single).

**Stage 2 — Shape search:** All valid `(n_full, n_half)` pairs with `rows ≥ budget × row_floor` are scored by the strategy's shape objective and the best is selected.

### Composite score formulas

| Strategy | Formula | Effect |
|---|---|---|
| Safe | `confidence` | Ignores all crowd signals |
| Balanced | `confidence + 0.03 × clip(value_top / 20, −1, +1)` | Tiny directional nudge from public mismatch |
| Value | `confidence − 0.20 × (CDS / 50)` | High CDS → lower score → more coverage |
| Jackpot | `confidence − 0.35 × (CDS / 50)` | CDS is the primary coverage driver |

### Shape objectives

| Strategy | Shape objective | Row floor | Budget fill |
|---|---|---|---|
| Safe | `P(12/12)^1.0` | 50% of budget | No |
| Balanced | `P(12/12)^0.9 × PVR^0.1` | 100% | Yes (always budget-filling) |
| Value | `P(12/12)^0.6 × PVR^0.4` | 50% of budget | No |
| Jackpot | `PVR^1.0` (floor: P(win) ≥ 0.3%) | 50% of budget | No |

### Safe

Maximises the probability of predicting all 12 outcomes correctly. Coverage ranking is based purely on model confidence — crowd signals ignored entirely. Produces the highest P(win) of the four strategies. Contrarian halvdekk substitution never occurs (`contrarian_pp_tolerance = 0`). Best when you want maximum hit-rate protection with no pool-edge optimisation.

### Balanced (default)

Default mode. Applies a small directional nudge from public tip percentages when ranking matches for coverage. Always uses the full budget (100% row-floor). Allows mild contrarian halvdekk substitution (within 4pp probability gap, only when the third outcome's Value Index exceeds the second's by ≥0.20). A good all-round starting point for most coupons.

### Value

CDS-driven coverage. Matches where the model strongly disagrees with the crowd receive more coverage regardless of raw model confidence (CDS weight 0.20). Allows contrarian halvdekk substitution within 10pp. Accepts a slightly lower P(win) in exchange for a better Pool Value Ratio. Best when the public tips look systematically wrong on several fixtures.

### Jackpot

Maximises Pool Value Ratio (PVR) subject to a 0.3% P(win) floor. CDS weight is 0.35 — the strongest of all modes, making crowd disagreement the primary driver of which matches receive halvdekk coverage. Eliminates heldekk when halvdekk on an uncertain match yields better PVR (heldekk covers everything → contributes nothing to pool uniqueness). Allows contrarian substitution within 15pp. Produces the lowest P(win) and the highest expected payout per winning row. Best reserved for large-turnover draws.

### Halvdekk second-pick substitution

Under Balanced/Value/Jackpot, the optimizer may substitute the third-ranked outcome (by model probability) for the second when all three conditions hold:

1. Probability gap between #2 and #3 ≤ `contrarian_pp_tolerance`
2. Third outcome's probability ≥ `min_prob_threshold`
3. Third outcome's Value Index exceeds the second's by ≥ `pick_vi_advantage`

Safe never substitutes. Parameters per strategy are defined in `analysis/strategy.py`.

### Strategy invariants (all modes)

- The single recommended pick is always the highest model-probability outcome — strategy never changes it.
- Full covers (heldekk) always include all three outcomes (H/U/B).
- Model probabilities in `Match` are read-only; strategy never writes to them.
- Budget constraint (`rows ≤ max_rows`) is never violated.

**Do not add new strategies or change strategy parameters without an explicit instruction.**

---

## Pool Value Metrics

Computed in `analysis/pool_value.py`. Displayed in the Kampanalyse table, Statistikk page, and `verify_model.py` output.

### P(win)

**What:** Exact probability that the coupon covers all 12 match outcomes.

**Formula:** `P_win = Π_i Σ_{X ∈ picks_i} model_prob(X, i)`

For a single-pick match this equals the model probability of that pick. For halvdekk it is the sum of the two covered outcome probabilities. For heldekk it is 1.0. Computed analytically — no simulation required.

### Poolverdi

**What:** Average pp-advantage of the coupon's single picks over the public. Measures how underplayed the recommended singles are as a group.

**Formula:** Average of `model_prob_pct − public_tip_pct` across all single-pick matches with public tip data.

**Interpretation:** Positive = singles are collectively underplayed (good for parimutuel). Negative = singles follow the crowd. Strategy-dependent: different strategies assign halvdekk vs single to different matches, so Poolverdi differs across strategies even for the same fixture set.

### Value Index (VI)

**What:** Ratio of model probability to public probability for a single outcome.

**Formula:** `VI = model_prob / pub_prob`

**Interpretation:**
- 1.00 — model and crowd agree exactly
- 1.25 — model sees 25% more probability than the crowd
- 1.50 — strong value (crowd significantly underweights this outcome)
- 2.00+ — extreme value
- < 1.00 — crowd overweights this outcome (negative pool edge for this pick)

Returns `None` when `pub_prob < 2%` (unreliable division). Capped at 5.0 for display stability.

### Crowd Disagreement Score (CDS)

**What:** pp difference between the model's top-pick probability and the public's tip percentage for that same outcome.

**Formula:** `CDS = |model_prob_pct(top_pick) − public_tip_pct(top_pick)|`

**Interpretation:** High CDS = model and crowd strongly disagree. Under Value/Jackpot strategies, high CDS reduces the composite score → match is promoted toward deeper coverage. Under Safe/Balanced it has no effect on ranking. CDS never changes the recommended pick.

### Pool Value Ratio (PVR)

**What:** Expected payout multiplier relative to the average public ticket. Measures how unique our combination is in the pool.

**Formula:** `PVR = P_model_win / P_public_win`

where `P_public_win = Π_i Σ_{X ∈ picks_i} pub_prob(X, i)`.

**Interpretation:**
- 1.0 — neutral; same pool share as a random public ticket
- > 1.0 — positive edge; our combination is rarer than average → higher expected payout when we win
- < 1.0 — negative edge; our combination is popular with the crowd
- Returns `None` when fewer than 6 of 12 matches have public tip data

---

## Payout Simulator (Phase 7)

NT Tippekupongen is a parimutuel pool: `payout = prize_pool / n_winning_rows`. The simulator (`analysis/pool_value.py → simulate_payout()`) estimates the payout distribution for a given coupon and turnover.

### Algorithm

For each of 50,000 simulation draws:

1. **Sample outcome** — draw one result (H/U/B) per match from model probabilities.
2. **Check coverage** — skip this draw if the coupon does not cover the sampled outcome.
3. **Compute public probability** — `p_pub = Π_i pub_prob(outcome_i, i)` using normalised public tip fractions.
4. **Sample other winners** — `w_others ~ Poisson((N − n_rows) × p_pub)` where `N = omsetning / cost_per_row`.
5. **Compute payout** — `prize_pool / max(1, w_others + 1)`.

### Corrected denominator formula

```
other_winners = (total_tickets − coupon_rows) × p_public(outcome)
total_winners = other_winners + 1
payout        = prize_pool / total_winners
```

**Why `+ 1` not `+ n_rows`:** For any specific 12-match outcome, exactly one row in our coupon can match it — our system is a set of distinct rows. Adding `n_rows` would assume all rows win simultaneously, which is impossible and causes payouts to be systematically understated by a factor of ~n_rows.

**Why `N − n_rows` for other winners:** Our rows are already accounted for in the `+ 1` term. Other winners are drawn from the remaining `N − n_rows` tickets in the pool.

### Poisson variance

Winner counts are sampled from a Poisson distribution rather than using the expected value. This captures realistic variance in how many other tickets share the winning outcome on any given draw, producing fat tails in the payout distribution that reflect NT's actual mechanics.

- For `λ ≤ 200`: Knuth algorithm (exact)
- For `λ > 200`: Gaussian approximation (`max(0, round(λ + √λ × N(0,1)))`)

### Outputs

| Field | Meaning |
|---|---|
| `p_win_simulated` | Fraction of draws where the coupon won (should match analytical `compute_p_win()`) |
| `min` | Minimum observed payout across winning draws |
| `p10` | 10th-percentile payout |
| `median` | Median payout when the coupon wins |
| `p90` | 90th-percentile payout |
| `max` | Maximum observed payout |
| `mean` | Mean payout |
| `e_winners` | Average number of winning rows sharing the pot |
| `narrative` | Norwegian explanation of why the median is high or low |

Activate via `--omsetning <NOK>` in `verify_model.py`. Default: 50,000 draws, `prize_rate = 52%`, `cost_per_row = 1.0 NOK`.

---

## Daily Workflow

### Recommended daily commands

```bash
python sync.py --daily        # fetch NT coupons, odds, AF enrichment, validate (idempotent)
python sync.py --validate     # re-check DB integrity at any time
```

### Model verification (optional, before placing coupon)

```bash
python verify_model.py --strategy safe
python verify_model.py --strategy balanced
python verify_model.py --strategy value
python verify_model.py --strategy jackpot

# With payout simulation (replace with realistic NT turnover):
python verify_model.py --strategy balanced --omsetning 15000000
```

`verify_model.py` is the authoritative check that the pipeline is consistent across Kampanalyse, Statistikk, and coupon generation. If output here looks wrong, the app will show the same wrong values.

---

## Optimizer math

The Phase 6C optimizer is a two-stage strategy-aware search (`analysis/optimizer.py`):

**Stage 1 — Coverage ranking:** Each match gets a composite score; lower score → receives deeper coverage (heldekk before halvdekk before single).

| Strategy | Composite score formula |
|---|---|
| Safe | `confidence` (ignores all crowd signals) |
| Balanced | `confidence + 0.03 × clip(value_top / 20, −1, +1)` |
| Value | `confidence − 0.20 × (CDS / 50)` |
| Jackpot | `confidence − 0.35 × (CDS / 50)` |

**Stage 2 — Shape search:** All valid `(n_full, n_half)` pairs with `rows ≥ budget × floor` are scored by the strategy's shape objective and the best is picked.

| Strategy | Shape objective | Row floor |
|---|---|---|
| Safe | `P(12/12)` | 50% of budget |
| Balanced | `P(12/12)^0.9 × PVR^0.1` | 100% (always budget-filling) |
| Value | `P(12/12)^0.6 × PVR^0.4` | 50% of budget |
| Jackpot | `PVR` (subject to P(win) ≥ 0.3%) | 50% of budget |

Jackpot eliminates heldekk when halvdekk on an uncertain match yields better PVR. Typical result at 192 NOK: Safe/Balanced/Value → 192 rows (1 HD, 6 H, 5 S); Jackpot → 128 rows (0 HD, 7 H, 5 S).

The four budget presets (32/96/192/384 NOK) are deliberately chosen to achieve exact full-budget coverage.

Thresholds in `analysis/classifier.py` control match classification and can be tuned without touching any other file.

## Current Project Status

### Completed phases

| Phase | Description | Status |
|---|---|---|
| 1 | NT coupon ingestion — fixtures, teams, odds from Norsk Tipping API | Complete |
| 1.5 | Validation suite + Team Review page | Complete |
| 2 | Historical results engine — save predictions, enter results, evaluate hit/cover rate | Complete |
| 3 | Odds movement + CLV tracking — timestamped snapshots, closing line, CLV per fixture | Complete |
| 4 | API-Football enrichment — fixture matching, stats/form, AF odds fallback | Complete |
| 4C | estimated_prior fallback — model-derived H/U/B for fixtures with no bookmaker odds | Complete |
| 5 | Unified prediction engine — `analysis/model.py`; bookmaker ≥87% weight; crowd disagreement score | Complete |
| 6B | Pool value analytics — `analysis/pool_value.py`; P(win), PVR, payout simulation; verify_model.py extended | Complete |
| 6C | Strategy system — `analysis/strategy.py`; four modes (safe/balanced/value/jackpot); strategy-aware optimizer | Complete |
| 7 | Corrected parimutuel payout simulator — fixed denominator (`+1` not `+n_rows`), Poisson winner variance, `e_winners`, narrative | Complete |

### Current architecture

```
Entry points
  app.py              Streamlit web UI (primary)
  main.py             Original CLI tool (no external deps)
  sync.py             Data ingestion and maintenance CLI
  verify_model.py     Model verification report — prints picks/probs/coverage for all 3 coupons; accepts --strategy and --omsetning

Analysis pipeline (shared by app.py, Kampanalyse, Statistikk, coupon generation)
  analysis/probability.py     decimal odds → normalized implied probabilities
  analysis/model.py           unified model: bookmaker prior + AF stats adjustment; crowd disagreement score
  analysis/classifier.py      classify match (banker/standard/half_cover/full_cover/uncertain)
  analysis/strategy.py        StrategyConfig dataclass + STRATEGIES dict (safe/balanced/value/jackpot)
  analysis/optimizer.py       two-stage strategy-aware optimizer: composite score ranking → shape search
  analysis/pool_value.py      compute_value_index, compute_p_win, compute_pool_value_ratio, simulate_payout
  analysis/estimated_prior.py fallback H/U/B when no bookmaker odds — NT expert (60%) + stats (40%)

Database  (SQLite via db/connection.py)
  db/schema.py        DDL for all tables; init_db() is idempotent
  db/registry.py      teams + competitions CRUD
  db/coupon.py        coupons + coupon_fixtures + odds CRUD
  db/history.py       coupon_predictions + match_results + coupon_evaluations
  db/odds_movement.py odds_snapshots + CLV calculation
  db/enrichment.py    fixture_stat_enrichment + api_football_fixture_links + fixture_estimated_prior CRUD

Ingestion
  ingestion/norsk_tipping.py   NT gameDays API → coupons + fixtures + teams
  ingestion/odds_api.py        The Odds API (Pinnacle) → odds + snapshots
  ingestion/seed.py            flat-file fallback (data/coupon_weekNN_YYYY.py)
  ingestion/enrich_fixtures.py AF fixture matching → stats/form enrichment
  ingestion/api_football.py    AF API client; _NT_COMPETITION_MAP for league IDs
  ingestion/api_football_odds.py  AF odds fallback — fills gaps with preferred bookmaker priority

Models
  models/match.py     Match dataclass (odds in, probs + classification out; includes crowd_disagreement_score)
```

### Streamlit pages

| File | Page | Purpose |
|---|---|---|
| `app.py` | Main | Coupon selector, analysis table, save coupon (Lagre kupong) |
| `pages/1_Team_Review.py` | Team Review | Inspect teams flagged for manual gender/age review |
| `pages/2_Results.py` | Resultater | Enter match scores after games are played |
| `pages/3_History.py` | Historikk | Evaluated coupons — hit rate, cover rate, CLV |
| `pages/4_Odds_Movement.py` | Odds Movement | Pinnacle odds time series, opening/closing, movement per fixture |
| `pages/5_Statistikk.py` | Statistikk | Per-fixture model breakdown: Model Inputs panel, odds source, AF stats, crowd vs model |

### sync.py commands

```
python sync.py                          full sync: NT coupons + Pinnacle odds
python sync.py --daily                  all-in-one: NT + Pinnacle + AF enrichment + AF odds + estimated priors + validate
python sync.py --refresh-coupons        force-refresh NT coupons + enrichment + AF odds fallback (start-of-week)
python sync.py --week N --year YYYY     explicit week/year for any command
python sync.py --seed-only              flat-file seed (no API calls)
python sync.py --nt-only                NT fixture fetch only
python sync.py --odds-only              Pinnacle odds only (fixtures must exist)
python sync.py --odds-snapshot          fetch odds and append timestamped snapshot
python sync.py --mark-closing-odds      mark last pre-kickoff snapshot as closing line
python sync.py --enrich-fixtures        match NT fixtures to API-Football, store stats/form
python sync.py --af-odds                fill missing odds from API-Football (manual/debug)
python sync.py --estimated-priors       compute model-estimated priors for fixtures with no bookmaker odds
python sync.py --status                 show DB contents for the week
python sync.py --validate               data integrity checks (PASS/WARN/FAIL) — 24 checks
python sync.py --review                 teams flagged for manual gender/age review
python sync.py --results-status         show coupons with predictions but missing results
python sync.py --evaluate               compute hit rate / cover rate for all evaluated coupons
python sync.py --nt-debug               print raw NT API response
```

### Database tables

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

### Data source priority

**Fixtures (source of truth):**
1. Norsk Tipping API (`nt_api`)

**Odds / probability prior (highest priority first):**
1. Pinnacle via The Odds API (`pinnacle`)
2. Other bookmaker odds (`norsk_tipping`, `manual`, `betsson`, ...)
3. API-Football odds (`api_football`) — Bet365 → William Hill → Marathonbet → 10Bet → first available
4. Model-estimated prior (`model_estimated`) — stored in `fixture_estimated_prior`, **not** in `odds`; NT expert tips (60%) + stats (40%)
5. NT expert tips fallback (runtime only — if no odds and no estimated prior, convert expert% to implied decimal odds)
6. Equal-probability placeholder (3.0/3.0/3.0) — last resort when nothing else available

**Statistics / form:**
1. API-Football (`fixture_stat_enrichment`)
2. Future fallbacks as needed

### Unified prediction engine — key invariants

These constraints must be preserved across all future changes:

- **Single pipeline:** `process_match()` → `run_model()` → `classify_match()` → `optimize_coupon()` is used identically in app.py (Kampanalyse + coupon generation), Statistikk page, and `verify_model.py`. If you change the model, all three update automatically.
- **Bookmaker dominance:** bookmaker prior always has ≥87% weight in the final probability blend. AF stats can adjust by at most ±`_MAX_ADJ` (defined in `analysis/model.py`).
- **Crowd disagreement score (CDS):** measures pp difference between model pick and public tips. Under Value/Jackpot strategies it reduces the composite score so high-disagreement matches receive more coverage; under Safe/Balanced it has no effect on ranking. Does **not** change the top recommended pick. `_effective_confidence()` is kept for backward-compatibility imports only.
- **CLV uses real bookmaker odds only:** `odds_snapshots` must only ever contain Pinnacle (or other real bookmaker) odds. Estimated priors and NT expert conversions must never be written to `odds_snapshots`. CLV is undefined when no real bookmaker closing line exists.
- **estimated_prior is not bookmaker odds:** validate check 24 enforces zero overlap between `fixture_estimated_prior` and `odds`.

### Strategy system (Phase 6B/C)

Four named strategies control coverage depth, system shape, and halvdekk second-pick selection. Selected via `--strategy` in `verify_model.py` and `optimize_coupon(strategy=…)` in the optimizer.

**Strategy invariants (all modes):**
- The single recommended pick is always the highest model-probability outcome — strategy never changes it.
- Full covers (heldekk) always include all three outcomes (H/U/B).
- Model probabilities in `Match` are read-only; strategy logic never writes to them.
- Budget constraint (`rows ≤ max_rows`) is never violated.

**Halvdekk second-pick substitution:** Under Balanced/Value/Jackpot the optimizer may substitute the third-ranked outcome (by probability) for the second when:
1. The probability gap between #2 and #3 is within `contrarian_pp_tolerance`
2. The third outcome's probability ≥ `min_prob_threshold`
3. The third outcome's value index exceeds the second's by ≥ `pick_vi_advantage`

Safe never substitutes (`contrarian_pp_tolerance = 0`). Jackpot allows the widest gap (15pp).

**Pool value analytics** (`analysis/pool_value.py`):
- `compute_value_index(prob, pub_prob)` — model_prob / public_prob; >1.0 means crowd underweights this outcome.
- `compute_p_win(matches, coupon)` — exact probability the coupon covers all 12 outcomes.
- `compute_pool_value_ratio(matches, coupon)` — P_model_win / P_public_win; >1.0 = positive pool edge. Returns `None` when fewer than 6 matches have public tip data.
- `simulate_payout(matches, coupon, n_rows, omsetning)` — Monte Carlo payout distribution (Phase 7); pass `--omsetning <NOK>` to `verify_model.py` to activate.

**Do not add new strategies or change strategy parameters without an explicit instruction.**

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
#    Should be PASS — all 24 checks clean (or PASS with expected WARNs: check 7 for AF/betsson odds)

# 3. Confirm the loader returns the right data
python -c "from data.loader import load_coupons; c=load_coupons(); print(list(c.keys())); [print(k, c[k]['label'], c[k]['deadline'][:10]) for k in c]"
#    Should print midtuke/lordag/sondag with correct 2026 dates

# 4. Visually verify in the app
streamlit run app.py
#    Coupon tabs should show Midtuke/Lørdag/Søndag with the correct deadline dates.
#    Fixtures should match what Norsk Tipping shows on their website.
```

### Current known limitations

- **ODDS_API_KEY not set** — Pinnacle odds are not being fetched. Set `ODDS_API_KEY` in `.env` to activate. When Pinnacle odds are missing, the pipeline falls back to API-Football odds (if `API_FOOTBALL_KEY` is set), then estimated priors, then equal-probability placeholders (3.0/3.0/3.0).
- **CLV requires real bookmaker closing odds** — CLV is not calculated unless a `is_closing_snapshot=1` row exists for the fixture. Run `python sync.py --mark-closing-odds` after the last pre-kickoff Pinnacle fetch.
- **Estimated prior confidence is low** — `fixture_estimated_prior` has confidence 0.35–0.65. For lower-tier domestic fixtures without bookmaker odds, the model relies heavily on NT expert tips (60% weight). Treat these recommendations with appropriate skepticism.
- **country_iso for NT-API teams** — new API does not provide country codes; national-tournament teams get `"INT"`, domestic-league teams get `"CLUB"`. Can be corrected manually in the DB.
- **No NT match IDs on manual coupons** — week 23 data was seeded from flat file; expected WARN in `--validate`.
- **No backtesting** — predictions are saved but there is no calibration or edge-vs-result analysis yet.
- **Team name matching is fuzzy substring** — works for major leagues; may miss NT teams with unusual spellings.
- **Validate check 7 WARN is expected** — AF odds (`api_football`) and occasional alternative bookmakers (`betsson`, etc.) are logged as fallback sources; this is normal and not a data integrity problem.

**Do not implement Elo, xG, or additional AI models without an explicit instruction to do so.**

---

## Weekly workflow

```
# 0. Start of week (Monday) — import new coupons
python sync.py --refresh-coupons
#    Fetches live NT coupons for the current ISO week, clears stale fixture data,
#    runs fixture enrichment (AF stats/form), fills missing odds from API-Football,
#    and validates the DB.
#    Run this as soon as NT publishes the week's coupons (usually Monday morning).
#    If NT hasn't published yet (204 / no content), try again later.

# 1. Every day during the week (Monday–Friday)
python sync.py --daily
#    6-step all-in-one sync:
#      [1/6] NT coupons          — fetch/update fixtures
#      [2/6] Pinnacle odds       — update + snapshot (skipped if ODDS_API_KEY not set)
#      [3/6] AF enrichment       — stats/form for new/unmatched fixtures (skips already-enriched)
#      [4/6] AF odds fallback    — fills any fixture still missing odds (never overwrites existing)
#      [4b/6] Estimated priors   — model-estimated H/U/B for any fixture still without bookmaker odds
#      [5/6] Validation          — PASS/WARN/FAIL integrity checks (24 checks)
#    Safe to run multiple times — all steps are idempotent.

python sync.py --validate     # run separately to re-check integrity at any time
python verify_model.py        # print model picks/probabilities/coverage for all 3 coupons

# 2. Before the deadline — open the app and save your coupon
streamlit run app.py
#    Select coupon, review recommendations, click "Lagre kupong".

# 3. After kickoff (Saturday/Sunday evening)
python sync.py --mark-closing-odds
#    Marks the last pre-kickoff Pinnacle snapshot as the closing line for each fixture.
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

### API-Football odds fallback — how it works

`--daily` and `--refresh-coupons` both run this automatically. Manual invocation: `python sync.py --af-odds`.
Module: `ingestion/api_football_odds.py → ingest_af_odds_fallback()`.

- **Source priority:** pinnacle → norsk_tipping → manual → api_football. AF odds are inserted with `source='api_football'` and only used when no higher-priority odds exist.
- **Never overwrites:** the guard checks `SELECT 1 FROM odds WHERE fixture_id = ?` before every AF call. If any odds row exists for a fixture, AF odds are skipped entirely.
- **Bookmaker priority:** Bet365 → William Hill → Marathonbet → 10Bet → first available.
- **Rate limiting:** 2.1 s delay between actual API calls (AF limit: 30 req/min). Skipped fixtures do not count against the delay.
- **Coverage:** all leagues mapped in `ingestion/api_football.py → _NT_COMPETITION_MAP` that have AF league IDs. Currently covers Women's WC Qual UEFA (league 880), Eliteserien, OBOS, Toppserien, Champions League, Nations League, FIFA World Cup.

### Model-estimated prior — how it works

`--daily` and `--refresh-coupons` run step 4b automatically after AF odds. Manual invocation: `python sync.py --estimated-priors`.
Module: `analysis/estimated_prior.py → compute_estimated_prior()`.

- **Only for fixtures with no bookmaker odds** — skips any fixture that already has a row in `odds`.
- **Signal blend:** NT expert tips at 60% weight (dominant signal) + stats-based home edge at 40%. Returns `None` when neither signal is available.
- **Confidence:** 0.20 (stats only, no expert) → 0.35 (stats only) → 0.50 (expert only) → 0.65 (both).
- **Stored in `fixture_estimated_prior`** — never written to `odds` or `odds_snapshots`. CLV is only calculated from real bookmaker closing lines; estimated priors do not affect CLV.
- **Validate check 24** enforces zero overlap with the `odds` table.

---

## Future Roadmap

Features that may be implemented in future phases. Do not implement any of these without an explicit instruction.

| Area | Description |
|---|---|
| Historical model evaluation | Calibration analysis — compare model probabilities to actual outcomes over all saved coupons; measure Brier score and log-loss per odds source |
| Payout simulator improvements | Incorporate NT prize tier structure (12/12, 11/12, 10/12 tiers) into the simulation; use real historical NT omsetning data for more accurate expected winner counts |
| xG integration | Add expected goals as an additional stats signal in `analysis/model.py`; currently documented as an extension point but not implemented |
| Expected value optimisation | Combine P(win), PVR, and median payout into a single EV metric for coupon comparison across strategies |
| Winner share estimation | Improve `p_public(outcome)` accuracy using NT's public tip percentages more directly, accounting for systematic biases in how the public tips home vs away |
| Strategy calibration | Backtest the four strategies against historical NT results to measure which strategy produces the best return per NOK across different fixture types |
