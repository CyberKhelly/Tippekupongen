---
target: frontend/app/history/page.tsx
total_score: 20
p0_count: 1
p1_count: 3
timestamp: 2026-06-22T09-51-33Z
slug: frontend-app-history-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Loading pulse exists; no data-freshness signal |
| 2 | Match System / Real World | 2 | "CDS-validering", "Generasjoner" are internal jargon |
| 3 | User Control and Freedom | 3 | Collapse/expand and generation select work |
| 4 | Consistency and Standards | 2 | StatCards, NtSection, GenStratCard all use identical card template |
| 5 | Error Prevention | 3 | Read-only page, low risk |
| 6 | Recognition Rather Than Recall | 2 | "Klikk en celle" hint is text-zinc-800, invisible |
| 7 | Flexibility and Efficiency | 1 | No keyboard nav; 7 sections all open = wall of content |
| 8 | Aesthetic and Minimalist Design | 1 | 8 equal-weight sections; no hierarchy between primary/secondary |
| 9 | Error Recovery | 2 | Error message exists; no retry |
| 10 | Help and Documentation | 2 | Footnote text only; no inline tooltips |
| **Total** | | **20/40** | **Acceptable** |

## Anti-Patterns Verdict
Deterministic scan: 0 violations. Issues are structural: eyebrow-on-every-section, identical card grid repetition, compressed typography scale with no dominant element.

## Priority Issues
- P0: IA inverts user priority — most valuable content (evaluated results) buried behind 3 aggregate sections
- P1: Eyebrow pattern on every section removes hierarchy signal
- P1: Matrix delta rows invisible (text-zinc-800 on #090909)
- P1: StatCards hero-metric template adds no signal with 1 coupon
- P2: Typography has no primary level; h1 is same scale as data numbers
