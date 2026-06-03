# Tippekupongen Analyser v1.0

A command-line tool for analysing the weekly Norwegian Tippekupongen.
Enter bookmaker odds for each match and get probability-based recommendations,
match classifications, and an optimized coupon within your budget.

---

## Requirements

- Python 3.9 or later
- No external packages — uses the standard library only

---

## How to Run

```bash
python main.py
```

That's it. The program guides you through input step by step.

---

## What You Enter

For each of the 12 matches you provide:

| Field     | Example         | Notes                                 |
|-----------|-----------------|---------------------------------------|
| Home team | `Arsenal`       | Press Enter to use a placeholder name |
| Away team | `Chelsea`       | Press Enter to use a placeholder name |
| H odds    | `2.10`          | Decimal odds for a home win           |
| U odds    | `3.40`          | Decimal odds for a draw               |
| B odds    | `3.60`          | Decimal odds for an away win          |

**Odds must be in decimal format.**
- Decimal `2.50` = fractional `3/2` = American `+150`
- All odds must be greater than `1.00`

At the end you enter your budget and the tool builds an optimized coupon.

---

## Understanding the Output

### Match Analysis Table

| Column | Meaning                                                    |
|--------|------------------------------------------------------------|
| H%     | Normalized probability of a home win                       |
| U%     | Normalized probability of a draw                           |
| B%     | Normalized probability of an away win                      |
| Pick   | Recommended outcome (highest probability)                  |
| Conf   | Confidence = the highest of the three probabilities        |
| Type   | Match classification (see below)                           |

> **Normalization** removes the bookmaker's margin so the three
> probabilities always sum to exactly 100%. This gives a fairer
> comparison between outcomes.

### Match Classifications

| Type       | Meaning                                                            |
|------------|--------------------------------------------------------------------|
| Banker     | Confidence ≥ 60%. Strong single pick, no cover needed.             |
| Standard   | One outcome leads clearly but below banker threshold.              |
| Half Cover | Top two outcomes are close (within 13pp). Consider covering both.  |
| Full Cover | All three outcomes nearly equal (top–bottom < 10pp). High risk.    |
| Uncertain  | No outcome reaches 45% probability. Maximum uncertainty.           |

### Optimized Coupon

The optimizer fits as many covers as possible within your budget.

- **Bankers** are always played as singles.
- **Uncertain / full-cover matches** are upgraded to full covers first.
- **Half-cover matches** are upgraded to two-pick covers next.
- The number of rows = product of pick counts across all 12 matches.

**Example with a 192 NOK budget at 1 NOK/row:**
```
Bankers (singles):     ×1 each
Half covers (2 picks): ×2 each  → e.g. 6 half covers = 64 rows
Full covers (3 picks): ×3 each  → e.g. 1 full cover on top of 64 = 192 rows
```

---

## Configuration

At the top of `main.py`:

```python
NUM_MATCHES = 12  # Change to 13 for weeks with 13 matches
```

In `analysis/classifier.py` you can adjust the classification thresholds:

```python
BANKER_THRESHOLD    = 0.60   # Confidence needed to call a match a banker
UNCERTAIN_THRESHOLD = 0.45   # Below this = no clear favourite
FULL_COVER_SPREAD   = 0.10   # top–bottom gap below this = full cover candidate
HALF_COVER_SPREAD   = 0.13   # top–second gap below this = half cover candidate
```

---

## Project Structure

```
tippekupongen/
├── main.py                  # Entry point — run this
├── requirements.txt
├── models/
│   └── match.py             # Match data class
├── analysis/
│   ├── probability.py       # Odds → normalized probabilities
│   ├── classifier.py        # Banker / uncertain / cover classification
│   └── optimizer.py         # Budget-based coupon optimizer
└── ui/
    └── display.py           # Terminal output formatting
```

---

## Limitations of v1.0

- **Odds are the only input.** The model has no access to team form, injuries,
  xG, head-to-head records, or news. Probabilities reflect only what the
  bookmaker market implies.

- **Normalized probabilities ≠ true probabilities.** Removing the bookmaker
  margin improves comparability but does not produce a model with genuine
  predictive edge. The bookmaker's margin is redistributed proportionally,
  which may still reflect their model's biases.

- **Tippekupongen is parimutuel.** You compete for a prize pool split among
  all correct coupons. A high-confidence pick played by everyone is not
  necessarily a high-value pick. Pool distribution modeling is a future
  feature.

- **No historical tracking.** Prediction accuracy is not recorded yet.

---

## Planned for Future Versions

- Automatic fixture retrieval from Norsk Tipping
- Football stats API integration (form, xG, head-to-head)
- Injury and suspension tracking
- Odds movement / market sentiment analysis
- Historical prediction accuracy dashboard
- Parimutuel pool-share estimation
- Multiple strategy modes (Conservative / Balanced / Aggressive)
