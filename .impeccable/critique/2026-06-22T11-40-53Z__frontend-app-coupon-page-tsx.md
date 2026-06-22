---
target: homepage coupon
total_score: 27
p0_count: 2
p1_count: 2
timestamp: 2026-06-22T11-40-53Z
slug: frontend-app-coupon-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Sync panel clear; no explicit "calculating..." during optimizer query |
| 2 | Match System / Real World | 3 | Norwegian localization solid; PVR/CDS/VI are unexplained domain jargon |
| 3 | User Control and Freedom | 3 | No undo on strategy/budget change; no destructive actions either |
| 4 | Consistency and Standards | 3 | Consistent vocabulary; two antipatterns break the contract |
| 5 | Error Prevention | 3 | Smart defaults; no confirmation for reversible selections (fine) |
| 6 | Recognition Rather Than Recall | 2 | P(12/12), PVR, CDS, VI, xG, GD used throughout with no inline definition |
| 7 | Flexibility and Efficiency | 2 | No keyboard shortcuts; no column sort/filter; no batch action |
| 8 | Aesthetic and Minimalist Design | 3 | Restrained and clean; gradient-text and side-tab antipatterns deduct |
| 9 | Help Users Recover from Errors | 3 | Offline banner clear; no retry button on failed coupon fetch |
| 10 | Help and Documentation | 2 | Tooltips only on form pips (hover); no glossary for metric abbreviations |
| **Total** | | **27/40** | **Acceptable — significant improvements needed** |

---

## Anti-Patterns Verdict

**LLM assessment**: The overall aesthetic is disciplined and intentional. Dark theme with amber/emerald accent, Bloomberg-adjacent data density, no SaaS clichés in the layout or navigation. Not AI slop at first glance — this feels like a tool built by someone who knows analytical product design. But two absolute-ban violations remain.

**Deterministic scan — 3 findings, 0 false positives:**

| Rule | Severity | File | Line | Snippet |
|------|----------|------|------|---------|
| `side-tab` | Warning | `components/MatchTable.tsx` | 232 | `borderLeft: "4px solid …"` |
| `side-tab` | Warning | `components/MatchTable.tsx` | 233 | `borderRight: "4px solid …"` |
| `gradient-text` | Warning | `components/MetricsRow.tsx` | 44 | `bg-clip-text + bg-gradient` |

The `side-tab` hits are on the team-color accent bars in the expanded match card — the left/right 4px colored borders marking home/away team zones. These are the single most identifiable AI-generation tell in the product UI register. Thick side-stripe borders as card/row decoration is the pattern to remove.

The `gradient-text` hit is on the PVR metric value in MetricsRow. Assessment A called this "purposeful" because it's amber/gold on a metric that indicates positive pool value. That reasoning doesn't rescue the pattern — gradient text is a visual decision that obscures the number's signal beneath a decorative effect. A solid amber or emerald with weight is more confident and more readable.

No false positives. All three hits are real violations of the absolute bans.

---

## Overall Impression

The coupon optimizer is the strongest part of this product — dense, analytical, Norwegian-localized, and built around the right mental model (analyst, not gambler). The MatchTable execution is genuinely good. But the gradient-text on the primary metric (PVR) and the side-tab borders on the expanded card are visible tells that should not survive a polish pass. The bigger structural problem is that metric abbreviations have no inline help — a weekly bettor who doesn't know what PVR means will either guess wrong or dismiss it as noise, and in both cases the optimizer's primary signal is wasted.

---

## What's Working

**1. Form pips with hover tooltips (MatchTable)** — W/D/L dots with opponent, score, venue, and date on hover is the correct density/disclosure tradeoff. Power users get the full picture; everyone else gets readable form strings. This is FotMob-level craft.

**2. Conviction signaling** — The pulsing amber dot on rows where model ≥10pp diverges from crowd opinion is a focused, purposeful use of color and motion. It answers "where do I pay attention?" without asking the user to compute it.

**3. Layout discipline** — Sticky sidebar with strategy/budget inputs, main area for the table, top bar for navigation. No nested cards. Clear zones. The two-column layout serves the task, and the responsive collapse to single-column is structurally sound.

---

## Priority Issues

### [P0] Gradient text on PVR metric
- **What**: `MetricsRow.tsx:44` — PVR value rendered with `bg-clip-text + bg-gradient-to-r`. Absolute ban, no exceptions.
- **Why it matters**: Gradient text communicates nothing the color alone doesn't. It's decorative, not meaningful. On a primary decision metric it looks like decoration rather than signal. Solid amber (`text-amber-400`) is stronger and more readable.
- **Fix**: Remove `bg-clip-text`, `bg-gradient-*`, and `text-transparent`. Apply `text-amber-400 font-bold` or `text-emerald-400` depending on PVR sign. Single color, maximum clarity.
- **Suggested command**: `/impeccable polish`

### [P0] Side-tab accent borders on expanded match card
- **What**: `MatchTable.tsx:232-233` — `borderLeft: "4px solid …"` and `borderRight: "4px solid …"` used as team color accent in the expanded card. Absolute ban.
- **Why it matters**: Thick side-stripe borders as decoration are the single most recognized AI-generation tell in product UI. The pattern draws attention to the border rather than to the data it surrounds.
- **Fix**: Replace with: (a) a full `border-t` in the team color (1px top bar), (b) a background tint behind the team section (`bg-[teamColor]/10`), or (c) a leading colored dot/chip. Any of these conveys team identity without the side-stripe tell.
- **Suggested command**: `/impeccable polish`

### [P1] Metric abbreviations have no inline explanation
- **What**: P(12/12), PVR, CDS, VI, xG, GD appear in MetricsRow headers, MatchTable column heads, and the sync panel with no definition in view.
- **Why it matters**: A weekly Norwegian Tipping bettor — the primary persona — may know that PVR is good when high, but not what "Pool Value Ratio" means or how to act on it. Without anchoring the label to a concept, the optimizer's analysis is decorative from the user's perspective.
- **Fix**: Add `title` attribute tooltips (or custom tooltip components) to each metric header: `<abbr title="Pool Value Ratio — modellens vinnersjanse ÷ folkets vinnersjanse">PVR</abbr>`. The glossary added to the Streamlit History page is a good template. A persistent `ⓘ` icon on the first row of MetricsRow would also work.
- **Suggested command**: `/impeccable clarify`

### [P1] Expanded row affordance is invisible before click
- **What**: MatchTable rows expand on click to show the team comparison card. Nothing signals that rows are clickable — no `cursor-pointer` hint visible in the static view, no chevron column visible before hover, no "tap to expand" text.
- **Why it matters**: The expanded card contains the richest data in the product (form, standings, goals, venue stats, signals). Users who don't discover the expand will make decisions without the model's actual reasoning. This is the analysis that justifies the recommendation.
- **Fix**: (a) Add a persistent expand indicator column — a right-aligned `⌄` or "Analyse ›" on every row, not just on hover. (b) Apply `cursor-pointer` to the entire `<tr>` in CSS. (c) Optionally auto-expand the top-conviction row on page load to teach the affordance on first visit.
- **Suggested command**: `/impeccable clarify`

### [P2] Accessibility: hover-only form pip data, no aria-expanded on rows
- **What**: (a) Form pip (W/D/L dot) tooltip data is hover-only — no keyboard or touch equivalent. (b) Expanded rows have no `aria-expanded` attribute, so screen readers cannot announce the state change. (c) The pulsing amber conviction dot relies on color + animation to convey meaning with no text fallback.
- **Why it matters**: Sam (keyboard/screen reader user) cannot access the form pip details at all. The pulsing dot is invisible to assistive technology.
- **Fix**: (a) Add `tabIndex={0}` + `onKeyDown` (Enter/Space) to form pips to trigger tooltip visibility. (b) Add `aria-expanded={isOpen}` to expandable row `<tr>` or its trigger element. (c) Add `aria-label="Overbevisning — modellen avviker ≥10pp fra folket"` to the conviction dot span.
- **Suggested command**: `/impeccable audit`

---

## Persona Red Flags

### Alex (Power User — data-heavy analytics interface)
- No keyboard shortcut to expand/collapse rows (must click each row)
- MatchTable columns cannot be sorted or filtered — must read all 12 rows linearly to find the highest-conviction picks
- No way to compare strategies side-by-side in the UI (must switch tabs and hold results in memory)
- The expand affordance being hover-dependent slows repeated use on dense table
- Minor: shape panel re-animates on every strategy/budget change, adds ~300ms latency to comparison workflow

### Sam (Accessibility)
- Form pip match history is hover-only with no keyboard path — entire previous-match detail layer inaccessible
- Conviction dot conveys meaning by color and motion only; no text equivalent, no aria-label
- MatchTable row expansion has no `aria-expanded` state announcement
- Gradient text on PVR may fail contrast check depending on background chroma
- Team logos have no confirmed alt text in the fetched API data

### Weekly Norwegian Bettor (project-specific)
**Profile**: Comes once a week with one goal — "What do I fill in?" Analytically curious but not a metrics specialist. Knows what Halvdekk/Heldekk means from Tipping, but not what PVR or CDS means.
**Behaviors**: Opens page, scans the recommended picks in amber, checks strategy, places budget. Rarely reads expanded card. Wants confidence signals, not raw data.
**Red flags**:
- "PVR: 9.45x" shows next to P(12/12) with no label tooltip — user sees a big number with no context and no action to take
- "Folket" column is correct terminology but doesn't signal that this is Norsk Tipping's own crowd data vs. external bookmakers
- Conviction badge count ("3 overbevisninger — modellen avviker ≥10pp fra folket") is correct but positioned between MetricsRow and the table — easy to scroll past
- Sync status panel with job names ("NT check", "Odds check") reads as technical, not reassuring

---

## Minor Observations

1. **Shape panel re-animation on strategy/budget change** — The bar fill animation restarts on every parameter change. At ~300ms it adds perceptible latency to comparison workflows. Consider animating only on mount, not on update.
2. **CDS and VI visual weight inconsistency** — VI is plain colored text; CDS renders as a bordered badge. They're at the same semantic level; they should look the same.
3. **0 convictions case is silent** — When no rows meet the ≥10pp threshold, the conviction legend disappears. "0 overbevisninger denne uken" would confirm the system checked and found none, rather than leaving users wondering if the feature is broken.
4. **Budget selector 2×2 grid** — Four budget options in a 2×2 grid is fine, but the recommended option (highlighted) could use a more prominent treatment — currently just a border change. A subtle amber background tint on the recommended tier would accelerate selection.
5. **"Folket" column header needs tooltip** — Even for power users who know this means NT public opinion, "Folket" gives no hint it's frozen at a specific time. `title="Norsk Tippings folkeprosent — oppdatert ved siste synkronisering"` on the `<th>` would surface this.
6. **Data coverage pips (4-dot row)** — Pos, form, H/A, GD are unexplained. Most users will read "◆◆◆◇" as "3/4 data" without knowing what the missing element is. A tooltip on each pip naming the data source would close this.
7. **Team logos: silent failure when missing** — "TM" initials fallback is handled, but no visual cue that a logo is still loading vs. genuinely absent. A skeleton shimmer on first load would prevent layout flash.
8. **`<details>/<summary>` progressive disclosure explored in Streamlit** — If the same pattern of analytics-in-expand is needed in the NextJS table, the current `onClick` toggle is more appropriate; however the row expand UX needs the affordance fix (P1 above).

---

## Questions to Consider

- What would the experience look like if PVR were replaced by a plain-language "pool position" label ("din kupong er blant de 10% mest unike")? Would that land better with the weekly bettor than a ratio?
- If the conviction dot is the single most important signal on the page, why is it the same size as the form pips? Should it command more vertical space when present?
- Is the MetricsRow the right home for P(12/12) and PVR — metrics that require a budget and strategy to mean anything — before the user has selected those inputs?
