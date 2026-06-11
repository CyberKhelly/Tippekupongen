# Roadmap

## Completed Phases

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
| 7 UI | EV panel refinement — 5-cell payout grid (Min/P10/Median/P90/Max), strategy comparison table, sim-warn box, strategy narrative, on_change omsetning input (commit 5235e6e) | Complete |

---

## Phase 8 — Historical Evaluation and Backtesting (Current)

Three areas of work:

### 8A — Historical evaluation / backtesting

Compare saved coupon predictions vs actual outcomes. Track hit rate (exact 12/12), cover rate, and P(at least 10/12) over time. Compare Safe/Balanced/Value/Jackpot side-by-side to identify which strategy has performed best over the sample.

### 8B — Model calibration

Measure how well model probabilities correspond to actual outcome frequencies. Compute Brier score and log-loss per fixture and per odds source. Compare model vs bookmaker implied probability vs public tip percentage vs NT expert.

### 8C — Payout tracking

Record actual NT payouts for weeks where a 12/12 was achieved. Compare actual payout vs simulator median estimate. Track whether PVR predicts higher actual payouts over time.

---

## Current Architecture

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

---

## Streamlit Pages

| File | Page | Purpose |
|---|---|---|
| `app.py` | Main | Coupon selector, analysis table, EV panel, strategy comparison, save coupon (Lagre kupong) |
| `pages/1_Team_Review.py` | Team Review | Inspect teams flagged for manual gender/age review |
| `pages/2_Results.py` | Resultater | Enter match scores after games are played |
| `pages/3_History.py` | Historikk | Evaluated coupons — hit rate, cover rate, CLV |
| `pages/4_Odds_Movement.py` | Odds Movement | Pinnacle odds time series, opening/closing, movement per fixture |
| `pages/5_Statistikk.py` | Statistikk | Per-fixture model breakdown: Model Inputs panel, odds source, AF stats, crowd vs model |

---

## Known Limitations

- **ODDS_API_KEY not set** — Pinnacle odds are not being fetched. Set `ODDS_API_KEY` in `.env` to activate. When Pinnacle odds are missing, the pipeline falls back to API-Football odds, then estimated priors, then equal-probability placeholders (3.0/3.0/3.0).
- **CLV requires real bookmaker closing odds** — CLV is not calculated unless a `is_closing_snapshot=1` row exists for the fixture. Run `python sync.py --mark-closing-odds` after the last pre-kickoff Pinnacle fetch.
- **Estimated prior confidence is low** — `fixture_estimated_prior` has confidence 0.35–0.65. For lower-tier domestic fixtures without bookmaker odds, the model relies heavily on NT expert tips (60% weight). Treat these recommendations with appropriate skepticism.
- **country_iso for NT-API teams** — new API does not provide country codes; national-tournament teams get `"INT"`, domestic-league teams get `"CLUB"`. Can be corrected manually in the DB.
- **No NT match IDs on manual coupons** — week 23 data was seeded from flat file; expected WARN in `--validate`.
- **Team name matching is fuzzy substring** — works for major leagues; may miss NT teams with unusual spellings.
- **Validate check 7 WARN is expected** — AF odds (`api_football`) and occasional alternative bookmakers (`betsson`, etc.) are logged as fallback sources; this is normal and not a data integrity problem.

---

## Future Roadmap (Do Not Implement Without Explicit Instruction)

| Phase | Area | Description |
|---|---|---|
| — | Payout simulator improvements | Incorporate NT prize tier structure (12/12, 11/12, 10/12 tiers) into the simulation; use real historical NT omsetning data for more accurate expected winner counts |
| — | xG integration | Add expected goals as an additional stats signal in `analysis/model.py`; currently documented as an extension point but not implemented |
| — | Expected value optimisation | Combine P(win), PVR, and median payout into a single EV metric for coupon comparison across strategies |
| — | Winner share estimation | Improve `p_public(outcome)` accuracy using NT's public tip percentages more directly, accounting for systematic biases in how the public tips home vs away |
| — | Strategy calibration | Backtest the four strategies against historical NT results to measure which strategy produces the best return per NOK across different fixture types |
