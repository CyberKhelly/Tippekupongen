"""
NT Oddsen Playwright POC -- feasibility test (v4).

Key findings:
- Sportsbook is in an iframe: /sport/oddsen/sportsbook/ (same-origin)
- NT uses its own React app, NOT Sportradar SIR
- 1X2 odds rendered immediately as div[data-for="selection-event-ID.1"]
  with aria-label="TeamName, odds X.XX"
- Each event ID maps to ONE selection (H, U, or B) -- NOT a selectionNum
- 3 consecutive event IDs in DOM order = one 1X2 market (H, then U/Uavgjort, then B)
- WebSocket: wss://velnt-opr1.sport2.norsk-tipping.no/ (NT's own domain)
- BTTS/O/U behind "Vis odds" link (navigates to event detail page)

Saves:
  scripts/nt_oddsen_playwright_rendered.html
  scripts/nt_oddsen_playwright_results.json

Usage:
    python scripts/nt_oddsen_playwright_poc.py            # headless
    python scripts/nt_oddsen_playwright_poc.py --headed   # visible browser

DEV ONLY -- do not import from backend/main.py, scheduler.py, or sync.py.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---- Config -----------------------------------------------------------------

TARGET_URL  = "https://www.norsk-tipping.no/sport/oddsen"
OUT_DIR     = Path(__file__).parent
HTML_OUT    = OUT_DIR / "nt_oddsen_playwright_rendered.html"
JSON_OUT    = OUT_DIR / "nt_oddsen_playwright_results.json"

HEADED      = "--headed" in sys.argv
SETTLE_MS   = 5_000   # ms after selection items appear

_ARIA_ODDS_RE = re.compile(r"odds\s+([\d]+\.[\d]{1,2})", re.IGNORECASE)


def _odds_from_aria(aria: str) -> float | None:
    m = _ARIA_ODDS_RE.search(aria)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v if 1.01 <= v <= 99.0 else None
    except ValueError:
        return None


def _label_from_aria(aria: str) -> str:
    """Extract 'TeamName' from 'TeamName, odds 3.50'."""
    return aria.split(",")[0].strip()


# ---- Extraction -------------------------------------------------------------

def _extract_all_selections(frame) -> list[dict]:
    """
    Return all selection divs in DOM order as:
      [{"label": str, "odds": float, "data_for": str}, ...]
    Each div represents one selection (H, U, or B).
    """
    sel_divs = frame.query_selector_all("[data-for^='selection-event-']")
    out = []
    for div in sel_divs:
        aria    = div.get_attribute("aria-label") or ""
        data_for = div.get_attribute("data-for") or ""
        odds_v  = _odds_from_aria(aria)
        if odds_v is not None:
            out.append({
                "label":    _label_from_aria(aria),
                "odds":     odds_v,
                "data_for": data_for,
            })
    return out


def _get_event_containers(frame):
    """
    Return all EventContainer elements that have at least one team name
    and at least one selection div.
    """
    containers = frame.query_selector_all("[class*='EventContainer']")
    result = []
    for c in containers:
        has_teams = c.query_selector("[class*='ParticipantNameItem']") is not None
        has_sels  = c.query_selector("[data-for^='selection-event-']") is not None
        if has_teams and has_sels:
            result.append(c)
    return result


def _extract_match_metadata(frame) -> list[dict]:
    """
    Extract teams, kickoff, league in DOM order from all EventContainers.
    Returns list of dicts with home/away/kickoff/league — one per match.
    Note: EventContainers are siblings of the MarketsContainer in the live DOM,
    so we extract metadata and selections separately then zip them by index.
    """
    containers = frame.query_selector_all("[class*='EventContainer']")
    meta = []
    for c in containers:
        try:
            # Team names
            team_els = c.query_selector_all("[class*='ParticipantNameItem']")
            teams    = [(t.inner_text() or "").strip() for t in team_els]
            if len(teams) < 2:
                continue
            # Kickoff
            kickoff = ""
            dt = c.query_selector("[class*='DateContainer']")
            if dt:
                kickoff = (dt.inner_text() or "").strip()
            # League
            league = ""
            lg = c.query_selector("[class*='TournamentNameItem']")
            if lg:
                league = (lg.inner_text() or "").strip()
            meta.append({
                "home_team": teams[0],
                "away_team": teams[1] if len(teams) > 1 else "",
                "kickoff":   kickoff,
                "league":    league,
            })
        except Exception:
            pass
    return meta


def _extract_matches_per_container(frame) -> list[dict]:
    """
    Zip match metadata (teams/date/league from EventContainers) with
    selection groups (1X2 odds from selection divs) by DOM index.
    """
    meta  = _extract_match_metadata(frame)
    sels  = _extract_all_selections(frame)
    print(f"  EventContainers with 2+ teams: {len(meta)}")
    print(f"  Total selections: {len(sels)}")

    # Group selections into triples (H, U, B per match)
    sel_groups = []
    for i in range(0, len(sels) - 2, 3):
        trio = sels[i:i+3]
        if len(trio) >= 3:
            sel_groups.append(trio)

    print(f"  Selection groups (3-sel each): {len(sel_groups)}")

    # Zip by index
    matches = []
    for i, trio in enumerate(sel_groups):
        m = meta[i] if i < len(meta) else {
            "home_team": trio[0]["label"],
            "away_team": trio[2]["label"],
            "kickoff": "",
            "league": "",
        }
        matches.append({
            "home_team":     m["home_team"],
            "away_team":     m["away_team"],
            "league":        m["league"],
            "kickoff":       m["kickoff"],
            "n_odds":        3,
            "odds_raw":      [trio[0]["odds"], trio[1]["odds"], trio[2]["odds"]],
            "odds_1x2":      {
                "H": trio[0]["odds"],
                "U": trio[1]["odds"],
                "B": trio[2]["odds"],
            },
            "sel_labels":    [s["label"] for s in trio],
            "sel_event_ids": [s["data_for"] for s in trio],
        })
    return matches


def _extract_matches_fallback(frame) -> list[dict]:
    """
    Fallback: group all selection divs in DOM order into triples = 1X2 markets.
    Used when per-container extraction yields nothing.
    """
    sels = _extract_all_selections(frame)
    print(f"  Fallback: {len(sels)} total selections, grouping into triples")
    matches = []
    for i in range(0, len(sels) - 2, 3):
        trio = sels[i:i+3]
        if len(trio) < 3:
            break
        matches.append({
            "home_team":     trio[0]["label"],
            "away_team":     trio[2]["label"],
            "league":        "",
            "kickoff":       "",
            "n_odds":        3,
            "odds_raw":      [trio[0]["odds"], trio[1]["odds"], trio[2]["odds"]],
            "odds_1x2":      {
                "H": trio[0]["odds"],
                "U": trio[1]["odds"],
                "B": trio[2]["odds"],
            },
            "sel_labels":    [s["label"] for s in trio],
            "sel_event_ids": [s["data_for"] for s in trio],
        })
    return matches


# ---- Main -------------------------------------------------------------------

def run():
    print("=" * 62)
    print("  NT Oddsen Playwright POC  (v4)")
    print(f"  URL:    {TARGET_URL}")
    print(f"  Mode:   {'headed' if HEADED else 'headless'}")
    print("=" * 62)

    results = {
        "url":         TARGET_URL,
        "status":      "failed",
        "matches":     [],
        "n_matches":   0,
        "n_1x2":       0,
        "dom_signals": {},
        "error":       None,
    }

    def save_results():
        JSON_OUT.write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not HEADED,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
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

        ws_urls:  list[str] = []
        api_calls: list[str] = []

        def on_request(req):
            url = req.url
            if any(x in url for x in ["sport2.norsk-tipping", "sportradar", "feedservice"]):
                api_calls.append(url)

        def on_websocket(ws):
            ws_urls.append(ws.url)

        page.on("request", on_request)
        page.on("websocket", on_websocket)

        # 1: Navigate
        print(f"\n[1/5] Navigating...")
        t0 = time.monotonic()
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            results["error"] = f"navigation: {e}"
            save_results()
            browser.close()
            return results
        print(f"  OK in {time.monotonic()-t0:.1f}s  title: {page.title()!r}")

        # 2: Find sportsbook iframe
        print("\n[2/5] Finding iframe#sportsbookid...")
        sb_frame = None
        try:
            page.wait_for_selector("iframe#sportsbookid", timeout=15_000)
            el = page.query_selector("iframe#sportsbookid")
            if el:
                sb_frame = el.content_frame()
                print(f"  Found: {sb_frame.url if sb_frame else 'no content'}")
        except PWTimeout:
            print(f"  Not found. Frames: {[f.url for f in page.frames]}")

        if sb_frame is None:
            results["error"] = "no sportsbook iframe"
            save_results()
            browser.close()
            return results

        target = sb_frame

        # 3: Wait for selection divs
        print(f"\n[3/5] Waiting for selection-event divs...")
        try:
            target.wait_for_selector("[data-for^='selection-event-']", timeout=30_000)
            print(f"  Appeared -- settling {SETTLE_MS}ms...")
            page.wait_for_timeout(SETTLE_MS)
        except PWTimeout:
            results["error"] = "timeout: no selection-event divs"
            HTML_OUT.write_text(target.content(), encoding="utf-8")
            results["dom_signals"]["ws_urls"] = ws_urls
            save_results()
            browser.close()
            return results

        if ws_urls:
            print(f"  WebSocket(s): {len(ws_urls)}")
            for u in ws_urls[:3]:
                print(f"    {u}")

        # 4: DOM signals
        print("\n[4/5] DOM signals...")
        n_sel   = len(target.query_selector_all("[data-for^='selection-event-']"))
        n_cont  = len(target.query_selector_all("[class*='EventContainer']"))
        n_teams = len(target.query_selector_all("[class*='ParticipantNameItem']"))
        n_btns  = len(target.query_selector_all("button"))

        dom_signals = {
            "selection_event_divs":  n_sel,
            "event_containers":      n_cont,
            "participant_names":     n_teams,
            "total_buttons":         n_btns,
            "ws_urls":               ws_urls[:10],
            "api_calls":             api_calls[:20],
        }
        print(f"  selection-event divs  : {n_sel}")
        print(f"  EventContainers       : {n_cont}")
        print(f"  ParticipantNameItems  : {n_teams}")
        print(f"  total buttons         : {n_btns}")

        # Sample aria-labels
        sample_sels = target.query_selector_all("[data-for^='selection-event-']")[:6]
        print("  Sample aria-labels:")
        for s in sample_sels:
            aria = s.get_attribute("aria-label") or ""
            dfr  = s.get_attribute("data-for") or ""
            print(f"    {dfr:42}  {aria}")

        # Save iframe HTML
        HTML_OUT.write_text(target.content(), encoding="utf-8")
        dom_signals["html_size_kb"] = round(HTML_OUT.stat().st_size / 1024, 1)
        print(f"\n  HTML saved ({dom_signals['html_size_kb']} KB) -> {HTML_OUT.name}")

        # 5: Extract
        print("\n[5/5] Extracting matches...")
        matches = _extract_matches_per_container(target)
        if not matches:
            print("  Per-container extraction empty -- using fallback")
            matches = _extract_matches_fallback(target)

        n_1x2 = sum(1 for m in matches if len(m.get("odds_raw", [])) >= 3)
        print(f"  Matches found : {len(matches)}")
        print(f"  1X2 markets   : {n_1x2}")

        results.update({
            "status":      "ok" if n_1x2 > 0 else ("partial" if matches else "no_data"),
            "matches":     matches,
            "n_matches":   len(matches),
            "n_1x2":       n_1x2,
            "dom_signals": dom_signals,
        })

        if matches:
            print("\nSample records (up to 5):")
            for m in matches[:5]:
                name = f"{m.get('home_team','?')} vs {m.get('away_team','?')}"
                ods  = m.get("odds_1x2", {})
                lbs  = m.get("sel_labels", [])
                print(
                    f"  {name[:40]:40}  "
                    f"H={ods.get('H','?')}  U={ods.get('U','?')}  B={ods.get('B','?')}  "
                    f"labels={lbs}"
                )
                if m.get("kickoff"):
                    print(f"    kickoff={m['kickoff']}  league={m.get('league','')}")
        else:
            print("  No matches -- inspect HTML")

        browser.close()

    save_results()

    # Verdict
    print("\n" + "=" * 62)
    print("VERDICT:")
    n_s = results["dom_signals"].get("selection_event_divs", 0)
    n_m = results["n_1x2"]
    if n_m > 0:
        print(f"  OK  {n_s} selection divs, {n_m} 1X2 markets extracted")
        print("      Odds accessible via [data-for] + aria-label -- no login needed")
        if ws_urls:
            print(f"      NT WebSocket: {ws_urls[0][:70]}")
            print("      Odds arrive via WebSocket (NT's own domain, not Sportradar)")
        print("      1X2 inline; BTTS/O/U behind 'Vis odds' (event-detail page)")
        print("      --> NT Oddsen 1X2 Playwright scraping is FEASIBLE")
    elif n_s > 0:
        print(f"  PARTIAL  {n_s} selection divs found but extraction needs work")
        print("      See HTML and refine selectors")
    else:
        print("  FAIL  No selection divs found -- check HTML")
    print(f"\nResults -> {JSON_OUT}")
    print(f"HTML    -> {HTML_OUT}")
    print("=" * 62)
    return results


if __name__ == "__main__":
    run()
