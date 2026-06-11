# Strategy System

Four named strategies control coverage depth, system shape, and halvdekk second-pick selection. Configured in `analysis/strategy.py` (StrategyConfig dataclass + STRATEGIES dict). Selected via `--strategy` in `verify_model.py` and `optimize_coupon(strategy=…)` in `analysis/optimizer.py`.

**Do not add new strategies or change strategy parameters without an explicit instruction.**

---

## Optimizer (Two-Stage Search)

**Stage 1 — Coverage ranking:** Each match is assigned a composite score. Lower score → receives deeper coverage (heldekk before halvdekk before single).

**Stage 2 — Shape search:** All valid `(n_full, n_half)` pairs with `rows ≥ budget × row_floor` are scored by the strategy's shape objective and the best is selected.

The four budget presets (32/96/192/384 NOK) are chosen to achieve exact full-budget coverage.

Thresholds in `analysis/classifier.py` control match classification and can be tuned without touching any other file.

---

## Composite Score Formulas (Stage 1)

| Strategy | Formula | Effect |
|---|---|---|
| Safe | `confidence` | Ignores all crowd signals |
| Balanced | `confidence + 0.03 × clip(value_top / 20, −1, +1)` | Tiny directional nudge from public mismatch |
| Value | `confidence − 0.20 × (CDS / 50)` | High CDS → lower score → more coverage |
| Jackpot | `confidence − 0.35 × (CDS / 50)` | CDS is the primary coverage driver |

---

## Shape Objectives (Stage 2)

| Strategy | Shape objective | Row floor | Budget fill |
|---|---|---|---|
| Safe | `P(12/12)^1.0` | 50% of budget | No |
| Balanced | `P(12/12)^0.9 × PVR^0.1` | 100% | Yes (always budget-filling) |
| Value | `P(12/12)^0.6 × PVR^0.4` | 50% of budget | No |
| Jackpot | `PVR^1.0` (floor: P(win) ≥ 0.3%) | 50% of budget | No |

Jackpot eliminates heldekk when halvdekk on an uncertain match yields better PVR. Typical result at 192 NOK: Safe/Balanced/Value → 192 rows (1 HD, 6 H, 5 S); Jackpot → 128 rows (0 HD, 7 H, 5 S).

---

## Strategy Descriptions

### Safe

**Objective:** Maximise the probability of predicting all 12 outcomes correctly.

Coverage ranking is based purely on model confidence — crowd signals ignored entirely. Contrarian halvdekk substitution never occurs (`contrarian_pp_tolerance = 0`). Highest P(12/12) of the four strategies. Lowest PVR and lowest expected payout per winning row.

### Balanced (default)

**Objective:** Balance hit-rate with mild pool uniqueness.

Applies a small directional nudge from public tip percentages when ranking matches for coverage. Always uses the full budget (100% row-floor). Allows mild contrarian halvdekk substitution (within 4pp probability gap, only when the third outcome's Value Index exceeds the second's by ≥0.20). Slightly lower P(win) than Safe; better PVR and higher expected median payout.

### Value

**Objective:** Promote underplayed outcomes into deeper coverage using crowd disagreement.

CDS-driven coverage; matches where the model strongly disagrees with the crowd receive more coverage regardless of raw model confidence (CDS weight 0.20). Allows contrarian halvdekk substitution within 10pp. Lower P(win) than Safe/Balanced; higher PVR than Safe. Best when the public tips look systematically wrong on several fixtures.

### Jackpot

**Objective:** Maximise Pool Value Ratio (expected payout per winning row).

CDS weight is 0.35 — the strongest of all modes. Eliminates heldekk when halvdekk on an uncertain match yields better PVR. Allows contrarian substitution within 15pp. P(win) floor of 0.3%. Lowest P(win) of the four strategies; highest PVR and highest expected median payout per winning row. Best reserved for large-turnover draws where pool dilution is high.

---

## Strategy Tradeoff Summary (typical 192 NOK / 15 M NOK omsetning)

| Strategy | P(12/12) | PVR | Median payout | Shape |
|---|---|---|---|---|
| Safe | Highest | Lowest | Lowest | 162 rows, more singles |
| Balanced | High | Good | Moderate | 192 rows, balanced |
| Value | Moderate | Good | Moderate–High | 192 rows, CDS-weighted |
| Jackpot | Lowest | Highest | Highest | 128 rows, no heldekk |

Actual numbers vary per coupon. The Strategisammenligning panel in the app always shows current-coupon values for all four strategies side by side.

---

## Halvdekk Second-Pick Substitution

Under Balanced/Value/Jackpot, the optimizer may substitute the third-ranked outcome (by model probability) for the second when all three conditions hold:

1. Probability gap between #2 and #3 ≤ `contrarian_pp_tolerance`
2. Third outcome's probability ≥ `min_prob_threshold`
3. Third outcome's Value Index exceeds the second's by ≥ `pick_vi_advantage`

Safe never substitutes (`contrarian_pp_tolerance = 0`). Jackpot allows the widest gap (15pp). Parameters per strategy are defined in `analysis/strategy.py`.

---

## Strategy Invariants (All Modes)

- The single recommended pick is always the highest model-probability outcome — strategy never changes it.
- Full covers (heldekk) always include all three outcomes (H/U/B).
- Model probabilities in `Match` are read-only; strategy never writes to them.
- Budget constraint (`rows ≤ max_rows`) is never violated.
