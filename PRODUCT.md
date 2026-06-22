# Product

## Register

product

## Users

Norwegian Tipping coupon bettor (solo analyst). Uses the tool in the days before a weekly betting deadline — often at a desk, focused, goal-directed. Their primary job: decide what to fill in on their Tippekupongen coupon and feel confident it's the best bet they can make. They are analytically minded and can read probability tables; they are not a passive recipient of picks.

## Product Purpose

TippeQongen is a coupon optimizer for Norsk Tipping's Tippekupongen. It recommends which outcomes to mark (H/U/B), at what coverage level (single / halvdekk / heldekk), and which budget tier to use — combining bookmaker odds, API-Football statistics, and NT public tip percentages into a single optimized generation. The History page answers "how have my past generations performed?" so the user can trust the optimizer going forward.

## Brand Personality

Analytical. Quiet confidence. Ruthlessly clear.

References that carry the right feel:
- **Bloomberg Terminal** — dense data, zero decoration, every pixel earns its place
- **Football Manager** — analytical scouting reports, compact tables, clear signal hierarchy
- **FotMob / Opta** — sports analytics clarity, result review, form visualization
- **Flashscore** — match result density, tabular precision

## Anti-references

- Casino landing pages (neon, glow, gold coins, "WIN BIG")
- Sportsbook UIs (heavy odds formatting, live-bet frenzy, red/green price flash)
- Generic SaaS dashboards (cream background, hero-metric cards, "trusted by 10,000 users")
- Crypto dashboards (glassmorphism, deep purple gradients, speculative energy)
- 2023-era fintech (navy + gold, circular progress rings, animated counters)

## Design Principles

1. **The coupon is the product.** Every element on screen either helps the user fill in or trust the coupon. If it does neither, remove it.
2. **Data clarity over decoration.** A number the user can read in 0.5 s is worth more than an animated chart they spend 2 s decoding.
3. **Signal before noise.** Evaluated results are signal. Pending cells are noise. The visual hierarchy must reflect this: evaluated data is primary, pending data is secondary and quiet.
4. **Coverage semantics, always.** A match is "correct" only when the coupon's covered outcomes include the actual result. Never show primary-pick accuracy to the user.
5. **Earn trust through precision.** The tool is only useful if the user believes the data. Dates must be accurate, labels must be unambiguous, and internal diagnostics must never leak into the UI.

## Accessibility & Inclusion

WCAG AA minimum. Dark theme requires careful contrast — body text at ≥ 4.5:1 against #050505. Color is never the sole indicator (always paired with text or icon). Reduced motion respected via `prefers-reduced-motion`.
