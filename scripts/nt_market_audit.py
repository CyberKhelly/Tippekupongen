"""
NT Oddsen market audit — diagnostic only, no DB writes.

Navigates to the NT Oddsen sportsbook, clicks the "more markets" button
for the first N fixtures, runs _MARKET_JS on each event detail page, and
prints every market name + all selections + odds without any filtering.

Usage:
    python scripts/nt_market_audit.py          # first 3 fixtures
    python scripts/nt_market_audit.py 5        # first 5 fixtures
"""
from __future__ import annotations

import io
import re
import sys

sys.path.insert(0, ".")

# Force UTF-8 output on Windows to avoid cp1252 encode errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

N_FIXTURES = int(sys.argv[1]) if len(sys.argv) > 1 else 3

from ingestion.nt_oddsen_playwright import (
    NT_SPORTSBOOK_URL,
    _BTN_MORE,
    _MARKET_JS,
    _ARIA_ODDS_RE,
    _dismiss_cookie,
    _wait_for_real_odds,
)

W = 72

def _fmt_odds(aria: str) -> str:
    m = _ARIA_ODDS_RE.search(aria)
    return m.group(1) if m else "—"

def _sel_label(aria: str) -> str:
    return aria.split(",")[0].strip() if aria else "(no label)"

def run_audit(n: int) -> None:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("playwright not installed — run: pip install playwright && python -m playwright install chromium")
        sys.exit(1)

    print(f"\n{'='*W}")
    print(f"  NT ODDSEN MARKET AUDIT  —  first {n} fixtures")
    print(f"  Source: {NT_SPORTSBOOK_URL}")
    print(f"{'='*W}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="nb-NO",
        )
        page = ctx.new_page()
        page.goto(NT_SPORTSBOOK_URL, wait_until="domcontentloaded", timeout=30_000)

        # Dismiss cookie before anything else
        _dismiss_cookie(page)

        # Acquire iframe
        try:
            page.wait_for_selector("iframe#sportsbookid", timeout=15_000)
        except PWTimeout:
            print("ERROR: iframe#sportsbookid not found after 15s")
            browser.close()
            return

        el = page.query_selector("iframe#sportsbookid")
        if not el:
            print("ERROR: iframe element is None")
            browser.close()
            return

        sbf = el.content_frame()
        if not sbf:
            print("ERROR: iframe has no content frame")
            browser.close()
            return

        # Wait for real odds to load
        try:
            sbf.wait_for_selector(_SEL_DIV := "[data-for^='selection-event-']", timeout=30_000)
        except PWTimeout:
            print("ERROR: no selection-event divs appeared after 30s")
            browser.close()
            return

        if not _wait_for_real_odds(sbf, timeout_ms=20_000):
            print("WARNING: selection divs present but odds aria-labels not filled after 20s — continuing anyway")

        page.wait_for_timeout(3_000)

        # Collect fixture labels from main list for headings
        containers = sbf.query_selector_all("[class*='EventContainer']")
        fixture_labels: list[str] = []
        for c in containers:
            try:
                team_els = c.query_selector_all("[class*='ParticipantNameItem']")
                teams = [t.inner_text().strip() for t in team_els]
                if len(teams) >= 2:
                    fixture_labels.append(f"{teams[0]} vs {teams[1]}")
            except Exception:
                pass

        # Navigate each fixture detail and dump all markets
        btns = sbf.query_selector_all(_BTN_MORE)
        actual = min(n, len(btns))
        print(f"  Found {len(btns)} fixtures with 'more markets' buttons. Auditing {actual}.\n")

        for idx in range(actual):
            label = fixture_labels[idx] if idx < len(fixture_labels) else f"Fixture #{idx + 1}"
            print(f"{'─'*W}")
            print(f"  FIXTURE {idx + 1}: {label}")
            print(f"{'─'*W}\n")

            # Re-acquire btns each iteration (DOM may update after history.back())
            el2 = page.query_selector("iframe#sportsbookid")
            sbf = (el2.content_frame() if el2 else sbf) or sbf
            btns_now = sbf.query_selector_all(_BTN_MORE)

            if len(btns_now) <= idx:
                print(f"  [skip] button {idx} no longer in DOM\n")
                continue

            # Dismiss cookie overlay immediately before click
            _dismiss_cookie(page)
            # Force-remove backdrop as fallback if _dismiss_cookie didn't clear it
            page.evaluate("""
                () => {
                    const el = document.querySelector('[data-testid="ntds-dialog-sheet-backdrop"]');
                    if (el) el.remove();
                    const portal = document.querySelector('#headlessui-portal-root');
                    if (portal) portal.remove();
                }
            """)
            page.wait_for_timeout(400)
            btns_now[idx].scroll_into_view_if_needed()
            btns_now[idx].click()
            page.wait_for_timeout(4_000)

            el2 = page.query_selector("iframe#sportsbookid")
            sbf = (el2.content_frame() if el2 else sbf) or sbf

            try:
                groups = sbf.evaluate(_MARKET_JS)
            except Exception as exc:
                print(f"  [error] _MARKET_JS failed: {exc}\n")
                sbf.evaluate("window.history.back()")
                page.wait_for_timeout(3_000)
                continue

            if not groups:
                print("  [no market groups returned by _MARKET_JS]\n")
            else:
                for g in groups:
                    mkt  = g.get("market", "(unnamed)")
                    sels = g.get("sels", [])
                    parsed = []
                    for s in sels:
                        aria  = s.get("aria", "")
                        label_s = _sel_label(aria)
                        odds_s  = _fmt_odds(aria)
                        parsed.append((label_s, odds_s))

                    print(f"  Market: {mkt!r}")
                    if parsed:
                        for sel_label, odds_val in parsed:
                            print(f"    {sel_label:<35}  odds {odds_val}")
                    else:
                        print("    (no selections with odds)")
                    print()

            # Navigate back
            if idx < actual - 1:
                sbf.evaluate("window.history.back()")
                page.wait_for_timeout(3_000)
                el2 = page.query_selector("iframe#sportsbookid")
                sbf = (el2.content_frame() if el2 else sbf) or sbf
                try:
                    sbf.wait_for_selector(_BTN_MORE, timeout=12_000)
                except Exception:
                    pass
                page.wait_for_timeout(2_000)

        browser.close()

    print(f"\n{'='*W}")
    print(f"  Audit complete — {actual} fixtures inspected.")
    print(f"{'='*W}\n")


if __name__ == "__main__":
    run_audit(N_FIXTURES)
