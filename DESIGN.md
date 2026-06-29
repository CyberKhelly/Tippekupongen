# TippeIQ — Design System

> **Single source of truth.** Every visual decision is derived from this file.
> Before touching any frontend file, check this document first.

---

## Product Visual Identity

| | |
|---|---|
| **Product** | Premium sports intelligence platform for Norsk Tipping and bookmaker markets |
| **Audience** | Serious football bettors who trust math over gut feel |
| **Tone** | Confident, precise, analytical. Not flashy. Not "casino". |
| **Feeling** | Bloomberg Terminal meets FotMob. Sports intelligence, not sports betting. |

**Looks like:** Linear · TradingView · StatsBomb IQ · FotMob

**Never looks like:** Gambling affiliate sites · Admin dashboards · Bootstrap tables · Generic SaaS

TippeIQ should feel like a **premium analytical tool** that a professional sports analyst or quant trader would be comfortable using. Every design decision should reinforce credibility, not excitement.

---

## Color System

### Canvas & Surface Ladder

Four levels. No drop shadows. Surface lift IS the depth signal.

| Token | Value | Use |
|---|---|---|
| `--canvas` | `#0A0A0B` | Page body |
| `--surf-0` | `#0F0F11` | App chrome — NavRail, TopBar |
| `--surf-1` | `#141416` | Cards, panels — primary surface |
| `--surf-2` | `#1A1A1C` | Elevated cards, selected rows |
| `--surf-3` | `#222226` | Hover states, active elements |

### Borders

| Token | Value | Use |
|---|---|---|
| `--bdr-0` | `rgba(255,255,255,0.04)` | Row dividers |
| `--bdr-1` | `rgba(255,255,255,0.07)` | Card borders (primary) |
| `--bdr-2` | `rgba(255,255,255,0.12)` | Strong borders, inputs |

### Text Hierarchy (warm, not cold white)

| Token | Value | Use |
|---|---|---|
| `--tx-1` | `#E8E4DD` | Primary — warm white |
| `--tx-2` | `#9A9592` | Secondary |
| `--tx-3` | `#5A5755` | Tertiary / labels |
| `--tx-4` | `#3A3835` | Ghost / disabled |

### Brand Gold

| Token | Value |
|---|---|
| `--gold` | `#F5C542` |
| `--gold-10` | `rgba(245,197,66,0.10)` |
| `--gold-22` | `rgba(245,197,66,0.22)` |

### Signal Indigo (crowd mispricing)

| Token | Value | Use |
|---|---|---|
| `--indigo` | `#7B92FF` | Model disagrees with crowd; edge signals |
| `--indigo-10` | `rgba(123,146,255,0.10)` | Indigo badge background |
| `--indigo-22` | `rgba(123,146,255,0.22)` | Indigo badge border |

### Signal Colors

| Token | Value | Use |
|---|---|---|
| `--green` | `#22C55E` | Won bets, positive ROI, covered picks |
| `--green-09` | `rgba(34,197,94,0.09)` | Green badge bg |
| `--red` | `#EF4444` | Losses, negative ROI, errors, drawdown **only** |
| `--red-09` | `rgba(239,68,68,0.09)` | Red badge bg |
| `--amber` | `#F59E0B` | Warning, risk badges, caution |

### Semantic Color Rules

- **Gold:** Value / strong recommendation / top signal / CTA
- **Indigo:** Model disagrees with crowd / folkeavvik / crowd mispricing signal
- **Green:** Actual positive outcomes — won bets, positive ROI, covered picks
- **Red:** Actual bad outcomes **only** — losses, negative ROI, errors, drawdown
- **Amber:** Risk / caution / warning states

**Red must never be used for "model disagrees with crowd."** Disagreement is shown as an absolute value with indigo or gold. Red is reserved for things that actually went wrong.

---

## Typography

**Pair:** Geist (`--font-display`, `--font-heading`) + Inter (`--font-sans`) + ui-monospace (`--font-mono`)

All numeric data is set in `--font-mono` with `font-variant-numeric: tabular-nums`.

### Type Scale (implemented as CSS classes in globals.css)

| Class | Size | Weight | Family | Tracking | Use |
|---|---|---|---|---|---|
| `.t-hero` | `clamp(52px,7vw,80px)` | 800 | display | -0.04em | Signal score, hero numbers |
| `.t-h1` | 22px | 700 | heading | -0.025em | Page title |
| `.t-h2` | 15px | 600 | heading | -0.015em | Section heading |
| `.t-h3` | 13px | 600 | heading | -0.01em | Card heading, match name |
| `.t-body` | 13px | 400 | sans | — | Body, insight text |
| `.t-caption` | 11px | 400 | sans | — | Meta, supporting text |
| `.t-label` | 9px | 600 | mono | +0.10em | Section eyebrows (UPPERCASE) |
| `.t-data` | 12px | 500 | mono | +0.02em | Numbers, stats |
| `.t-data-lg` | 14px | 700 | mono | +0.02em | Prominent edge scores |

---

## Spacing

Base unit: **4px**

Scale: `4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64 · 80 · 96`

---

## Border Radius

| Token | Value | Use |
|---|---|---|
| `--r-xs` | 3px | Pick badges, chips, small tags |
| `--r-sm` | 5px | Inputs, small buttons |
| `--r-md` | 8px | Cards, panels — primary |
| `--r-lg` | 12px | Large cards, drawers |
| `--r-xl` | 16px | Hero panels, terminal panel |
| `--r-pill` | 999px | Pips, avatar circles |

---

## Page Identities

### Oversikt / Home (`/home`)

**Identity:** Premium SaaS landing page. Explains why TippeIQ exists and makes the user want to open the coupon in under 10 seconds.

Layout: Two-column. Left = editorial hero copy. Right = live intelligence terminal panel.

The terminal panel should feel like a Bloomberg terminal alert — real data, live signal, countdown to deadline. Not a feature list, not a marketing slide.

### Signaler (`/signaler`)

**Identity:** Kupong-intelligens. Analyst report. Model vs folket.

**Job:** "Here is where the crowd is wrong — and why you should trust it."

Layout: Two-column. Left = watchlist (300px). Right = analyst brief.

**Left panel (watchlist):**
- Header: `ALLE KAMPER · RANGERT ETTER SIGNALSTYRKE` (t-label)
- Row: rank · match name · edge badge · pick badge
- Selected row: surf-2 bg + gold left stripe
- Sort: by `|edge_pp|` descending

**Right panel (analyst brief):**
1. Top bar: league + time (t-label) · classification chip
2. Hero score: `.t-hero`, colored by edge direction (gold=positive, red=negative, tx-3=no public data)
3. Verdict subtitle: `.t-caption`, `var(--tx-3)`
4. Match name: `.t-h2`
5. Probability bars: FOLKET vs MODELL (animate-bar-grow, CSS scaleX)
6. Divider
7. MODELLEN STØTTER SIGNALET: green eyebrow + insight bullets
8. RISIKOFAKTORER: amber eyebrow + risk bullets
9. ANBEFALING: pick badge + text + "Bygg kupong →"

### Kupong (`/kupong`)

**Identity:** Portfolio / coupon builder. Turns signals into a playable NT coupon.

**Job:** Build the optimal coupon. Remove noise, add clarity.

- No Safe strategy. Balansert + Jackpot only.
- Free-form budget input (snap to multiples of 32kr).
- Table: pick badges primary. Edge secondary. Classification tertiary.
- Model% / folk% / VI: collapsed behind row expansion.
- The coupon is the output — not the analysis. Analysis justifies the coupon.

### Modellspill (`/oddstips`)

**Identity:** Odds-intelligens. Trading platform. Model vs bookmaker market.

**Job:** Answer immediately: "What should I bet on?"

Default view: Match · Market · Odds · Edge · Risk · Stake · Status

Everything else: expandable row detail.

Components:
- Bankroll equity chart (chronological, line chart)
- Performance summary row: total bets, hit rate, ROI, max drawdown
- Bet tabs: Aktive / Avgjorte / Signaler
- Each row: model quality badge, market badge, edge badge, risk tier badge
- Expandable: reason text, xG, Poisson probabilities, bookmaker implied

### Historikk (`/historikk`)

**Identity:** Proof page. Shows whether the system works over time.

Strategy performance, hit rates, CDS validation, conviction vs coverage, model vs NT public, PVR vs payout. Data-first, no narrative.

### Strategien / Systemspill (`/strategien`)

**Identity:** Educational strategy engine. Explains systems, coverage allocation, reduction funnel, and risk tradeoffs.

Components:
- System library dropdown (42 systems, 10 Category A active, 32 Category B disabled)
- Risk slider: Treffsikkerhet ↔ Jackpotpotensial
- Coverage allocation panel: how many singles / halvdekk / heldekk
- Per-match reason band: why each match got this coverage type
- Row generator: first 5 rows preview (H=black, U=amber, B=blue)
- Payout/profile section when omsetning is provided

---

## UX Rules

1. **Never start a page with a table.** Every page should open with a clear editorial statement of what the data means before showing the data.

2. **Use large editorial headlines.** The most important number on any page should be visually dominant. If everything is the same size, nothing is important.

3. **Explain numbers with text.** A probability of 67% means nothing without context: "Modellen er 67% sikker — folkeavvikket er +12pp" is always better.

4. **Raw percentages must have context.** Never show "67%" without also showing what it's compared to, what the crowd says, or what the threshold means.

5. **Team logos should be shown naturally, without circular wrappers.** Logos have their own shape. Circular wrappers distort them. Use the logo at native aspect ratio on a transparent or dark background.

6. **Red must never be used for ordinary model disagreement.** Indigo is for "model disagrees with crowd." Red is for "bet lost" or "negative ROI." These are different things. Using red for disagreement trains the user to feel bad about the model's signal.

7. **Disagreement should be shown as absolute value + explanation.** `+12pp` is a positive signal. Never show crowd disagreement as a negative number unless the model is actually below the crowd for the recommended pick.

8. **The optimizer is always the center.** Signals, analysis, and statistics exist to justify and explain the optimizer's output — not to be features in their own right.

---

## Component Patterns

### Panel

```
background: var(--surf-1)
border: 1px solid var(--bdr-1)
border-radius: var(--r-md)
overflow: hidden
```

### Panel Row

```
padding: 10px 16px
border-bottom: 1px solid var(--bdr-0)
transition: background 120ms ease
hover → background: var(--surf-3)
```

### Selected Row

```
background: var(--surf-2)
left stripe: 2px wide, 14px tall, var(--gold), absolute, vertically centered
```

### Pick Badge (H / U / B)

```
size: 20×20px, border-radius: var(--r-xs)
background: var(--surf-3)
border: 1px solid var(--bdr-2)
font: .t-label, color: var(--tx-1)
sign order: ALWAYS H → U → B
```

### Edge Badge

```
Positive: color var(--gold),  background var(--gold-10), border 1px solid var(--gold-22)
Negative: color var(--red),   background var(--red-09)
Neutral:  color var(--tx-4)
font: .t-data-lg, padding: 2px 6px, border-radius: var(--r-xs)
```

### Quality Badge (Modellspill)

```
full_model:    color var(--green), background green-09, label "Full modell"
af_supported:  color var(--indigo), background indigo-10, label "AF-støttet"
generic_prior: color var(--tx-3), background surf-2, label "Eurosnitt-prior"
```

### Tier Badge (risk level)

```
tier_a (≥8pp): color var(--gold), background gold-10
tier_b (5–8pp): color var(--amber), background amber-09
tier_c (3–5pp): color var(--tx-2), background surf-2
```

### Market Badge

```
1x2:      color #6098F2
btts:     color #A78BFA
over_2.5: color #F97316
padding: 2px 6px, border-radius: var(--r-xs), font: .t-label
```

### Section Eyebrow

```
.t-label (9px mono UPPERCASE +0.10em tracking)
color: var(--tx-3) default, or colored when semantic:
  green section → rgba(34,197,94,0.55)
  amber/risk section → rgba(245,158,11,0.55)
margin-bottom: 10px
```

### Insight Bullet Row

```
display: flex, gap: 8px, align-items: flex-start
icon (✓ or ⚠): 11px, flex-shrink: 0
text: .t-body, color: var(--tx-2), line-height: 1.5
gap between rows: 6px
```

### Probability Bar

```
track: 7-8px height, border-radius: 999px, background: rgba(255,255,255,0.06)
fill: CSS class .animate-bar-grow (scaleX from 0→1, transform-origin: left)
NEVER animate width directly — use scaleX to avoid layout thrash
```

### Hero Card

```
Large editorial number (t-hero or t-h1), colored by signal direction
Subtitle below in t-caption / tx-3
Optional supporting context in t-body / tx-2
No decorative icons — the number is the hero
```

### Signal Card

```
Top: league chip (t-label) + kickoff (tx-3)
Middle: match name (t-h3) + pick badge
Right: edge badge
Expandable bottom: Poisson probs, reason text
```

### Bankroll Chart

```
Line chart, single series
X-axis: settled_at timestamps
Y-axis: bankroll_after in NOK
Color: var(--green) above starting bankroll, var(--red) below
No fill gradient (too decorative)
```

### Coverage Allocation (Systemspill)

```
Three bars: Heldekk (n_full) · Halvdekk (n_half) · Singel (remainder)
Proportional width based on n_full + n_half + n_singles = 12
Color: heldekk=emerald, halvdekk=slate-500, singel=tx-4
```

### Strategy Tab (horizontal)

```
Active: color var(--tx-1), 2px underline var(--gold) at bottom
Inactive: color var(--tx-3), no decoration
Hover (inactive): color var(--tx-2), transition 120ms
```

### Button — Primary

```
background: var(--gold), color: #0A0A0B
font: 700 13px var(--font-sans), letter-spacing: -0.01em
padding: 10px 20px, border-radius: var(--r-sm)
```

### Button — Secondary

```
background: var(--surf-2), color: var(--tx-1)
border: 1px solid var(--bdr-1)
font: 500 13px, padding: 10px 18px, border-radius: var(--r-sm)
```

---

## Layout

### NavRail

- Width: 48px (`w-12`), `position: fixed`, `left: 0`, `z-index: 30`
- Does NOT affect layout flow — wrap page content in `pl-12`
- Background: `var(--surf-0)`
- Active icon: gold left stripe (2px)

### Top Bar

- Height: 44px, `sticky top-0 z-20`
- Background: `var(--surf-0)`, border-bottom: `1px solid var(--bdr-0)`
- Left: LABEL · meta info (t-label, tx-4 separators)
- Right: status dot + t-label countdown

### Content Widths

| Layout | Class |
|---|---|
| Narrow (forms) | `max-w-2xl` |
| Standard (tables, feeds) | `max-w-5xl` |
| Split-panel | full width in columns |
| Dashboard | `max-w-7xl` |

---

## Motion

**Rules:**
- Use CSS animations only. Framer Motion `initial={{ opacity/translate }}` breaks in React Strict Mode dev.
- NEVER animate `width` — use `transform: scaleX()` for bars.
- NEVER animate `max-height` — use pre-calculated pixel heights or opacity transitions.
- Always respect `prefers-reduced-motion` (handled globally in globals.css).

**Available CSS animation classes:**
- `.animate-hero-up` — staggered page entrance (use `animationDelay` inline)
- `.animate-fade-up` — section reveal
- `.animate-expand-down` — accordion open
- `.animate-bar-grow` — metric bars (scaleX 0→1)

---

## Information Hierarchy Rule

For every surface, resolve in order:

1. **What is the single most important number/action?** → Largest element on the surface
2. **What justifies trusting it?** → Second most prominent
3. **What could go wrong?** → Visible but clearly secondary
4. **What's next?** → CTA

---

## Consistency Enforcement

**Violations of these rules = design debt:**

1. Hardcoded hex color in component JSX → use `var(--xxx)`
2. Framer Motion `initial={{ opacity: 0 }}` on mount → use CSS `.animate-xxx`
3. Width animation on bars → use `scaleX` transform
4. Pick badges not in H→U→B order → fix the sort
5. `font-family: "..."` hardcoded → use `var(--font-xxx)`
6. Drop shadows → remove (surface ladder only)
7. Gradients on backgrounds → remove (flat surfaces only)
8. Different border-radius per page → use `var(--r-xxx)`
9. Red used for crowd disagreement or CDS → replace with indigo or gold
10. Team logos in circular wrappers → remove the wrapper

---

*Last updated: 2026-06-29. All frontend decisions must trace back to this document.*
