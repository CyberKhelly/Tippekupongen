# TippeIQ — Product Vision

> Future roadmap. This file describes what TippeIQ should become, not what it is today.
> For current implementation state, see CLAUDE.md and DESIGN.md.

---

## What TippeIQ Is

TippeIQ is a sports intelligence platform for the Norwegian football bettor.

It has two parallel intelligence products:

1. **Kupong-intelligens** — exploits NT pool mispricing by finding where the crowd is wrong
2. **Odds-intelligens** — exploits bookmaker market mispricing using model probability vs implied probability

The differentiator in both cases is the same: **a calibrated model that produces independent probability estimates**, applied to a market that has systematic biases (NT crowd bias for coupons; bookmaker margin and recency bias for odds).

TippeIQ should always explain uncertainty. It should never pretend to be certain.

---

## Near-Term Backend Priorities

### Better enrichment for global Modellspill fixtures

Currently ~27 leagues are scanned, but most non-NT fixtures only get `generic_prior` Poisson (European average xG). Priorities:

- Expand enrichment pipeline to run for tracked leagues, not just NT coupon fixtures
- Fetch `/statistics` and `/standings` for Modellspill fixtures on a weekly cadence
- Store venue-specific goal averages for all enriched leagues
- Tag more bets as `full_model` instead of `generic_prior`

### More reliable expected payout / pool value calculations

- P(11+) and P(10+) currently require omsetning input from the user
- Goal: auto-fetch omsetning for active coupons and pre-compute payout distribution
- Store payout distributions as part of generation snapshots

### Historical NT public percentage archive

- NT public percentages currently only available live (during the active coupon week)
- Goal: archive public %% as they arrive via the 5-min NT refresh job
- Store time series in `public_pct_history` table
- Enable "how the crowd shifted during the week" visualizations in Historikk

### Better settlement and result tracking

- Auto-settle currently requires `match_results` to be populated via `evaluate.py --fetch`
- Goal: automatic result fetching from API-Football after kickoff + 110 min
- Add a dedicated settle scheduler job that fetches results and settles in one pass
- Store closing odds at settlement time for CLV calculation

### More detailed audit tables for rejected bets

- Currently only counts of rejected bets are tracked
- Goal: store each rejected candidate (fixture + edge + reason for rejection) in `bet_candidates_rejected`
- Enables analysis of "why we passed on a fixture" and calibration of thresholds

---

## Data Sources

| Source | Role |
|---|---|
| **Norsk Tipping** | Coupons, public tip percentages (% per outcome), NT turnover (omsetning), game day metadata |
| **API-Football** | Fixtures, standings, form, goal averages, venue records, clean sheets, streaks; odds for 1X2/BTTS/O/U; predictions (AF Predictions endpoint) |
| **Odds API (Pinnacle)** | High-quality closing line reference for CLV; opening and current 1X2 odds snapshots |
| **Optional: Firecrawl** | Fallback scraping for NT public data if the NT live-info API changes format again or rate-limits |

**On Sofascore-style visuals:** Team comparison graphics and match timeline visuals should be built internally using the data we already have, not scraped from Sofascore. The data exists in `fixture_stat_enrichment` — the work is frontend, not data collection.

---

## Future Product Features

### Match detail pages

A dedicated page per fixture accessible from any signal card or bet row. Shows:

- Full team comparison (form, goals, position, streaks)
- H2H last 5 matches
- Poisson distribution visualization
- Model probability vs bookmaker implied vs NT public
- Odds movement chart (Pinnacle snapshots)
- AF prediction breakdown
- "Why did the model play this?" explanation

### "Why did the model play this?"

Human-readable explanation of every model decision, auto-generated from the signal stack:

- Which inputs dominated (bookmaker prior vs AF stats adjustment)
- What the crowd is saying and why the model disagrees
- What the risk factors are (small sample, venue issues, WC group ambiguity, etc.)
- Formatted as a short analyst note, not a list of numbers

### "Why did the model skip this?"

For fixtures that had odds but were not recommended or not bet on:

- Edge below threshold
- Model quality too low (generic_prior)
- No bookmaker odds available
- Already covered by another correlated fixture

This is the rejection audit feature — shows the model is disciplined, not just lucky.

### Value timeline

Chart showing how model edge and implied probability moved during the week for each NT coupon fixture. Requires the NT public percentage archive (see backend priorities).

### Odds movement timeline

Chart showing Pinnacle opening vs closing odds for each fixture. Uses existing `odds_snapshots` data. Answers: "Did the market agree with us, or move against us?"

### Model confidence score

A single composite score per fixture combining:

- Edge strength (model vs implied or model vs crowd)
- Model quality (full_model > af_supported > generic_prior)
- Data freshness (how recent is the enrichment?)
- CDS signal strength

Displayed as a single number (e.g. 0–100) with color coding. Not a prediction — a measure of how much we trust the model's signal.

### Expected payout distribution

Full histogram of payout outcomes for the NT coupon, not just P(win), P(11+), P(10+):

- X-axis: payout bracket (0, 100–1k, 1k–10k, 10k–100k, jackpot)
- Y-axis: probability mass
- Requires Monte Carlo simulation with NT pool structure

### Team profile panels

Persistent team cards accessible from match rows and detail pages. Shows:

- Season form (last 10, home/away split)
- Goals for/against at home and away
- Clean sheets
- Position trajectory (moving up or down?)
- Key injury/suspension context (future: manual input)

### Live scanner dashboard

Real-time view of the Modellspill scan status:

- Last scan time and coverage (X fixtures evaluated)
- Active bet candidates by tier (A/B/C)
- Market coverage: % of scanned fixtures with BTTS odds, O/U odds
- Pending bets with countdown to kickoff
- Settlement queue: bets pending result

### Premium subscription concept

TippeIQ has a natural freemium split:

| Tier | Features |
|---|---|
| **Free** | Kupong-intelligens signals (model vs crowd), basic coupon optimizer |
| **Pro** | Modellspill scanner, full enrichment, payout distribution, odds movement |
| **Power** | API access, raw model outputs, custom strategy configuration |

No hard deadline on this, but the product is designed to support it: Kupong-intelligens is the acquisition hook, Modellspill is the retention driver.

---

## Important Product Rule

**TippeIQ should always explain uncertainty.**

- Never say "this will win." Say "the model gives this 67% — the crowd says 55%, a 12pp gap."
- Never show a single probability without context.
- Never hide the model quality tier. If it's `generic_prior`, the user should see "Eurosnitt-prior" on the bet.
- Rejection explanations matter as much as recommendations. A system that explains why it said no is more trustworthy than one that only talks about the bets it took.

The product's credibility comes from intellectual honesty about what the model knows and doesn't know.
