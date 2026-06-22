---
target: pages/3_History.py historikk
total_score: 27
p0_count: 2
p1_count: 2
timestamp: 2026-06-22T11-21-06Z
slug: pages-3-history-py
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Status badges good; Delvis undefined operationally |
| 2 | Match System / Real World | 3 | Norwegian terminology correct; CDS/CLV/VI jargon unexplained |
| 3 | User Control and Freedom | 3 | Selectbox drill-down works; no filter, sort, or export |
| 4 | Consistency and Standards | 4 | Color, badge, table styling consistent throughout |
| 5 | Error Prevention | 2 | Missing values shown as dash; no confirmation on actions |
| 6 | Recognition Rather Than Recall | 3 | Good color coding; acronyms require memorization |
| 7 | Flexibility and Efficiency | 2 | Dense tables good; no sort/filter/bulk/export |
| 8 | Aesthetic and Minimalist Design | 4 | Brutalist terminal aesthetic executed cleanly |
| 9 | Error Recovery | 1 | No retry, no rollback, no graceful partial-load fallback |
| 10 | Help and Documentation | 2 | Subtitles explain intent; no tooltips, no glossary |
| **Total** | | **27/40** | **Acceptable** |

## Anti-Patterns Verdict

No AI slop detected. Zero side-stripe borders, no gradient text, no glassmorphism, no hero-metric template, no identical card grids. The dark navy / muted-blue / yellow-accent palette is committed and brand-coherent. The page reads as a Bloomberg Terminal or Football Manager analytics surface. Brutalist, handcrafted, no padding inflation.

Detector returned empty on the Python source file (expected: the tool parses HTML markup, not Python strings with inline HTML).

## Overall Impression

The Historikk page is analytically rigorous and aesthetically honest. Seven sections, seven questions, clean visual identity. But it asks too much of working memory. Acronyms explained once in a subtitle reappear three sections later without re-definition. The per-fixture detail table has 13 columns -- a cognitive wall that hides the insight behind jargon. The biggest opportunity: progressive disclosure on the detail table and a persistent glossary would transform dense-but-hard into dense-and-trustworthy.

## What is Working

1. Brutalist terminal aesthetic fully committed. Dark navy, muted blue-gray, yellow accent, emerald for positive signals. Matches Bloomberg Terminal / FotMob identity exactly.

2. Snapshot semantics are technically rigorous. CDS, odds, and public percentages are frozen at save time and labeled as such. A bettor reviewing last week sees data as it was when placed, not contaminated by late odds.

3. Hit/miss color coding is immediately intuitive. Green tick for covered picks, red cross for misses. Consistent color roles across all 6 sections and the detail view.

## Priority Issues

P0 - Vocabulary amnesia: acronyms explained once, used everywhere. CDS, VI-bkt, Edge, CLV, Folkeavvik, halvdekk/heldekk, NT appear throughout. Each explained once in a section subtitle, then reused across sections and the detail table without re-definition. Also: two names for the same thing (CDS and Folkeavvik) in the same section.

P0 - 13-column detail table with no progressive disclosure. Kupongdetaljer shows match, odds, pick, confidence, system choice, result, score, hit/miss, CDS, VI-bkt, edge, CLV simultaneously for 12 fixtures (156 visible cells). The primary use case is why did this coupon miss -- that needs 4 columns. The other 9 are follow-up answers dumped into view at once.

P1 - Section headers are too dim to anchor navigation on a 7-section page. 0.65rem, color #2e4a64, very muted. On a long page the headers are nearly invisible during quick scroll. User cannot jump to the section they need.

P1 - Delvis evaluation status has no operational definition. The badge says partial but not what that means in action: waiting for results to be entered? Evaluation errored? Can the user do something about it?

P2 - No sorting or filtering on the summary table. Static HTML. With more than 5-6 saved coupons, finding the best or worst week requires manual scanning.

## Persona Red Flags

Alex (Power User): No sort/filter on primary table. 13-column detail requires horizontal scroll below 1600px. HTML tables copy-paste unfriendly, no export.

Sam (Accessibility): tick/cross spans carry no ARIA label -- screen reader announces check-mark symbol without semantic meaning. Abbr tags not used on CDS, VI, CLV, NT. Table th elements missing scope attribute. Muted dim text (#3a5a78) may fail contrast audit.

Weekly Bettor: Assumes familiarity with PVR, CDS, VI, CLV, conviction -- none defined on first encounter. History shows what happened but gives no actionable recommendation for next week.

## Minor Observations

Table row alternating striping at rgba 2% is barely perceptible, bump to 4%. Empty state CLI instruction assumes developer access. Selectbox format omits strategy label making coupon selection guesswork among same-week records. Section 6 empty state gives no explanation of what it unlocks when data arrives. Footnote font at 9px is borderline; floor at 10px.
