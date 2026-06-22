# Model Architecture

## Unified Prediction Engine

`analysis/model.py → run_model()` blends multiple signals into final H/U/B probabilities for each fixture.

### Signal blend

1. **Bookmaker prior** (≥87% weight) — normalised implied probabilities from the best available odds source. Always the dominant signal; computed in `analysis/probability.py` from decimal odds.
2. **Form adjustment** — AF stats (last 5 results for home/away separately) nudge probabilities by at most ±`_MAX_ADJ` (defined in `analysis/model.py`). Home and away form tracked independently.
3. **Standings adjustment** — league position and goal difference contribute a small directional nudge. A large table gap amplifies the bookmaker signal slightly.
4. **Goals adjustment** — recent goals scored/conceded per match provide a marginal signal on top of standings.

The AF stats adjustments are additive and bounded: the combined adjustment never pushes the final probability more than `_MAX_ADJ` away from the bookmaker prior.

NT public/expert percentages are **forbidden** in the probability layer — see `docs/probability_architecture.md`.

### Key invariants

- **Single pipeline:** `process_match() → run_model() → classify_match() → optimize_coupon()` is used identically in app.py (Kampanalyse + coupon generation), Statistikk page, and `verify_model.py`. If you change the model, all three update automatically.
- **Bookmaker dominance:** bookmaker prior always has ≥87% weight. AF stats can adjust by at most ±`_MAX_ADJ`.
- **Model probabilities in `Match` are read-only** — strategy and optimizer logic never write to them.
- **`_effective_confidence()`** is kept for backward-compatibility imports only.

---

## Crowd Signals

After blending, the model computes three crowd-signal fields per fixture (stored in `Match`, read-only):

- **`value_h / value_u / value_b`** — pp difference between model probability and public tip percentage for each outcome. Positive = crowd underweights this outcome. Formula: `model_prob_pct − public_tip_pct`.
- **`crowd_disagreement_score` (CDS)** — pp difference between the model's top-pick probability and the public's tip percentage for that same outcome. Measures how much the model and crowd disagree on the most likely result. Range 0–50pp. Does **not** change the recommended pick.

---

## Estimated Prior Fallback

When no bookmaker odds exist for a fixture (Norwegian 3. Division, some women's club fixtures), the model falls back to `analysis/estimated_prior.py`:

- NT expert tips (60% weight) + stats-based home edge (40%)
- Confidence 0.35–0.65 depending on which signals are available
- Stored in `fixture_estimated_prior`, **never** in `odds` or `odds_snapshots`
- Validate check 24 enforces zero overlap between `fixture_estimated_prior` and `odds`
- Substantially less reliable than bookmaker-derived probabilities — treat P(win) and PVR skeptically for these fixtures

Signal blend in `compute_estimated_prior()`:
- **Only for fixtures with no bookmaker odds** — skips any fixture that already has a row in `odds`.
- **Confidence:** 0.20 (stats only, no expert) → 0.35 (stats only) → 0.50 (expert only) → 0.65 (both).
- CLV is only calculated from real bookmaker closing lines; estimated priors do not affect CLV.

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

Norwegian 3. Division and some women's fixtures are not covered by Pinnacle or API-Football — they use priority 4 or 5. The Statistikk page shows `odds_source` per fixture; look for `model_estimated` or `nt_expert` to identify lower-confidence matches.

**CLV uses real bookmaker odds only:** `odds_snapshots` must only ever contain Pinnacle (or other real bookmaker) odds. Estimated priors and NT expert conversions must never be written to `odds_snapshots`.

---

## Pool Value Metrics

Computed in `analysis/pool_value.py`. Displayed in the Kampanalyse table, Statistikk page, `verify_model.py` output, and the EV panel in `app.py`.

### P(12/12) — win probability

Exact probability that the coupon covers all 12 match outcomes.

**Formula:** `P_win = Π_i Σ_{X ∈ picks_i} model_prob(X, i)`

For a single-pick match this equals the model probability of that pick. For halvdekk it is the sum of the two covered outcome probabilities. For heldekk it is 1.0. Computed analytically — no simulation required.

### Poolverdi

Average pp-advantage of the coupon's single picks over the public. Measures how underplayed the recommended singles are as a group.

**Formula:** Average of `model_prob_pct − public_tip_pct` across all single-pick matches with public tip data.

Positive = singles are collectively underplayed (good for parimutuel). Negative = singles follow the crowd. Strategy-dependent: different strategies assign halvdekk vs single to different matches, so Poolverdi differs across strategies even for the same fixture set.

### Value Index (VI)

Ratio of model probability to public probability for a single outcome.

**Formula:** `VI = model_prob / pub_prob`

- 1.00 — model and crowd agree exactly
- 1.25 — model sees 25% more probability than the crowd
- 1.50 — strong value (crowd significantly underweights this outcome)
- 2.00+ — extreme value
- < 1.00 — crowd overweights this outcome (negative pool edge)

Returns `None` when `pub_prob < 2%` (unreliable division). Capped at 5.0 for display stability.

### Crowd Disagreement Score (CDS)

pp difference between the model's top-pick probability and the public's tip percentage for that same outcome.

**Formula:** `CDS = |model_prob_pct(top_pick) − public_tip_pct(top_pick)|`

High CDS = model and crowd strongly disagree. Under Value/Jackpot strategies, high CDS reduces the composite score → match is promoted toward deeper coverage. Under Safe/Balanced it has no effect on ranking. CDS never changes the recommended pick.

### Pool Value Ratio (PVR)

Expected payout multiplier relative to the average public ticket. Measures how unique our combination is in the pool.

**Formula:** `PVR = P_model_win / P_public_win`

where `P_public_win = Π_i Σ_{X ∈ picks_i} pub_prob(X, i)`.

- 1.0 — neutral; same pool share as a random public ticket
- > 1.0 — positive edge; our combination is rarer than average → higher expected payout when we win
- < 1.0 — negative edge; our combination is popular with the crowd
- Returns `None` when fewer than 6 of 12 matches have public tip data

### Expected winners (e_winners)

Mean number of total winning rows sharing the prize pool across all winning simulation draws. Includes our 1 winning row.

**Formula:** `e_winners = mean(w_others + 1)` across winning draws.

Lower = better. High PVR corresponds to low e_winners.

### API functions

```python
compute_value_index(prob, pub_prob)          # → float or None
compute_p_win(matches, coupon)               # → float (analytical)
compute_pool_value_ratio(matches, coupon)    # → float or None
simulate_payout(matches, coupon, n_rows, omsetning)  # → dict (Phase 7)
```
