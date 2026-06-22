# Probability Architecture (Critical Invariant)

## Core Principle

Model probabilities must be independent from Norsk Tipping public percentages and expert percentages.

The purpose of the model is to estimate the true football probability.

Public betting behaviour must never influence the probability estimate itself.

---

## Allowed Inputs For Model Probability

The model may use:

* Pinnacle odds
* Odds API odds
* API-Football odds fallback
* Estimated priors derived from football statistics
* API-Football enrichment:

  * form
  * league position
  * points
  * wins/draws/losses
  * goals scored
  * goals conceded
  * goal difference
  * home record
  * away record
  * clean sheets
  * prediction ratings

---

## Forbidden Inputs For Model Probability

The model must never use:

* NT public percentages
* NT expert percentages
* crowd popularity
* pick distribution
* betting ownership
* any derivative of public percentages

These values are forbidden anywhere in the probability calculation pipeline.

---

## Architecture

### Layer 1 — Probability

Goal:

Estimate true H/U/B probability.

Inputs:

* odds
* football statistics
* API-Football enrichment

Output:

* model_h
* model_u
* model_b

### Layer 2 — Value

Goal:

Compare model probability against the market.

Inputs:

* model_h/u/b
* NT public percentages

Output:

* edge
* value index
* CDS
* pool value metrics

### Layer 3 — Strategy

Goal:

Build the coupon.

Inputs:

* model probabilities
* edge
* value
* PVR
* CDS
* budget
* strategy profile

Output:

* picks
* singles
* halvdekk
* heldekk

---

## Verification Rule

Changing NT public percentages must never change model probabilities.

Example:

Fixture A

Run 1:
Public = 60 / 20 / 20

Run 2:
Public = 90 / 5 / 5

Expected:

model_h = identical
model_u = identical
model_b = identical

Only:

* edge
* value
* CDS
* strategy decisions

may change.

If model probabilities change, the architecture is considered broken.

The test suite in `tests/test_model_independence.py` enforces this rule automatically.

---

## Implementation

| Layer | Code | Notes |
|---|---|---|
| Probability | `analysis/probability.py` → `process_match()` | Converts bookmaker decimal odds to vig-normalised H/U/B |
| Probability | `analysis/model.py` → `run_model()` Step 1–2 | Bookmaker prior + bounded AF stats adjustment |
| Probability | `analysis/estimated_prior.py` | AF-stats-only fallback when no bookmaker odds |
| Value | `analysis/model.py` → `run_model()` Step 3 | NT public percentages → value_h/u/b, CDS |
| Value | `analysis/pool_value.py` | PVR, P(win), e_winners |
| Strategy | `analysis/optimizer.py` | Coupon shape from model + value |

---

## Historical Note

Prior to the Phase 10 audit, NT expert percentages leaked into:

* synthetic bookmaker odds (`data/loader.py._best_odds()`)
* estimated prior calculations (`analysis/estimated_prior.py`)
* final probability blending (`analysis/model.py` Step 3, `_W_EXPERT = 0.05`)

These pathways were removed. As of Phase 10, model probabilities are football-data driven and independent from NT expert/public percentages.
