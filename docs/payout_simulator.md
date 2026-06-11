# Payout Simulator

NT Tippekupongen is a parimutuel pool: `payout = prize_pool / n_winning_rows`. The simulator (`analysis/pool_value.py → simulate_payout()`) estimates the payout distribution for a given coupon and turnover.

**All outputs are simulation estimates. Actual NT payouts depend on real omsetning, winner count, and NT's prize allocation rules. Do not present simulation figures as guaranteed payouts.**

Activate via `--omsetning <NOK>` in `verify_model.py`. Default: 50,000 draws, `prize_rate = 52%`, `cost_per_row = 1.0 NOK`.

---

## Algorithm

For each of 50,000 simulation draws:

1. **Sample outcome** — draw one result (H/U/B) per match from model probabilities.
2. **Check coverage** — skip this draw if the coupon does not cover the sampled outcome.
3. **Compute public probability** — `p_pub = Π_i pub_prob(outcome_i, i)` using normalised public tip fractions. Estimates how popular this exact 12-match outcome is among the ticket-buying public.
4. **Sample other winners** — `w_others ~ Poisson((N − n_rows) × p_pub)` where `N = omsetning / cost_per_row`. Poisson sampling adds realistic variance around the expected value.
5. **Compute payout** — `prize_pool / max(1, w_others + 1)`.

---

## Corrected Denominator Formula

```
other_winners = (total_tickets − coupon_rows) × p_public(outcome)
total_winners = other_winners + 1
payout        = prize_pool / total_winners
```

**Why `+ 1` not `+ n_rows`:** For any specific 12-match outcome, exactly one row in our coupon can match it — our system is a set of distinct rows covering different combinations. Adding `n_rows` would assume all rows win simultaneously, which is impossible and causes payouts to be systematically understated by a factor of ~n_rows.

**Why `N − n_rows` for other winners:** Our rows are already accounted for in the `+ 1` term. Other winners are drawn from the remaining `N − n_rows` tickets in the pool.

---

## Poisson Variance

Winner counts are sampled from a Poisson distribution rather than using the expected value. This captures realistic variance in winner counts, producing fat tails in the payout distribution that reflect NT's actual mechanics.

- For `λ ≤ 200`: Knuth algorithm (exact)
- For `λ > 200`: Gaussian approximation (`max(0, round(λ + √λ × N(0,1)))`)

---

## Simulation Outputs

| Field | Meaning |
|---|---|
| `p_win_simulated` | Fraction of draws where the coupon won (should match analytical `compute_p_win()`) |
| `min` | Minimum observed payout across winning draws |
| `p10` | 10th-percentile payout — only 10% of wins pay less than this |
| `median` | Median payout when the coupon wins |
| `p90` | 90th-percentile payout — only 10% of wins pay more than this |
| `max` | Maximum observed payout |
| `mean` | Mean payout |
| `e_winners` | Average number of winning rows sharing the pot |
| `narrative` | Norwegian explanation: winner count, PVR context, underplayed singles |

The spread between P10 and P90 reflects Poisson variance in winner counts. A high PVR narrows the winner count distribution (fewer co-winners) and shifts all percentiles upward.

---

## EV Panel UI (app.py — Phase 7 refinement, commit 5235e6e)

The left column of `app.py` displays an "Estimert verdi" panel below the coupon card.

### Top row (always visible)

- **Sjanse 12/12** — analytical P(win) as a percentage; green ≥5%, amber ≥1%, red <1%
- **Poolverdi ratio** — PVR; green ≥1.0×, red <1.0×
- **Verdivalg** — count of single-pick matches where model_prob > public_tip for the recommended pick

### Payout section (visible when omsetning > 0)

- Section heading: "Estimert utdeling ved 12/12"
- Five-cell grid: **Min · P10 · Median (gold) · P90 · Max** (all in NOK)
- Winner line: "Vinnere ved gevinst (snitt): ~N rekker deler potten"
- Strategy narrative (italic): one-line explanation of what the active strategy optimises for
- Pool narrative: context on winner count, PVR multiplier, and count of underplayed singles
- Amber sim-warn box: "⚠ Simuleringsestimat — ikke garantert utbetaling · 50 000 simuleringer · 52% premieandel · Omsetning X NOK"

**Crowd warning:** If PVR < 0.85, an amber warning appears: "⚠ Kupongen er nær folkets valg — vurder Verdi eller Jackpot strategi".

### Strategy comparison table (always visible)

Rendered via `components.html()` with self-contained inline CSS (not `st.markdown`) to bypass CommonMark's HTML-block parsing. Shows all four strategies for the current coupon and budget:

| Strategi | 12/12 | PVR | Median * |
|---|---|---|---|
| Safe | % | ×× | kr (if omsetning set) |
| ▶ Balansert | % | ×× | kr |
| Verdi | % | ×× | kr |
| Jackpot | % | ×× | kr |

Active strategy is highlighted in bright white/bold. PVR is colour-coded green (≥1.0×) or red (<1.0×) for the active row only. The Median column appears only when omsetning is set; comparison simulations use 10,000 draws per strategy.

### Omsetning input

Located in a collapsible expander below the comparison table. Uses `on_change` callback (`_on_om_change`) to write `st.session_state.omsetning` before the next render, ensuring the payout panel appears immediately on the first render after the user enters a value.
