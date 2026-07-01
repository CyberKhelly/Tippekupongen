"""
NT Oddsen Playwright scraper -- production-safe 1X2 odds ingestion.

Scrapes https://www.norsk-tipping.no/sport/oddsen using headless Chromium.
The sportsbook loads in an iframe (same-origin: /sport/oddsen/sportsbook/).
1X2 odds render immediately as div[data-for="selection-event-ID.1"] with
aria-label="TeamName, odds X.XX" -- no login, no Sportradar auth required.

Architecture note:
  This module is PRODUCTION code.  It does NOT use Firecrawl.
  It may be imported by backend/main.py, backend/scheduler.py, sync.py.

Requires:
  playwright Python package + Chromium browser:
    pip install playwright
    python -m playwright install chromium
  Returns {error: "playwright_not_installed"} gracefully if missing.

Stores results in: nt_oddsen_odds_snapshot (shared with nt_oddsen_scraper.py)
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

NT_SPORTSBOOK_URL = "https://www.norsk-tipping.no/sport/oddsen"
NT_BOOKMAKER_LABEL = "NT Oddsen"

# ---- Name normalisation (self-contained, matches nt_oddsen_scraper.py) ------

# Norwegian → English national team name map
_NO_TO_EN: dict[str, str] = {
    "spania":          "spain",
    "frankrike":       "france",
    "tyskland":        "germany",
    "italia":          "italy",
    "nederland":       "netherlands",
    "belgia":          "belgium",
    "sveits":          "switzerland",
    "osterrike":       "austria",
    "osterreich":      "austria",
    "tsjekkia":        "czech republic",
    "kroatia":         "croatia",
    "serbias":         "serbia",
    "ungarn":          "hungary",
    "albanias":        "albania",
    "skottland":       "scotland",
    "norge":           "norway",
    "sverige":         "sweden",
    "danmark":         "denmark",
    "island":          "iceland",
    "brasil":          "brazil",
    "sordkorea":       "south korea",
    "saudi-arabia":    "saudi arabia",
    "saudiarabia":     "saudi arabia",
    "usa":             "united states",
    "storbritannia":   "great britain",
    "marokko":         "morocco",
    "elfenbenskysten": "ivory coast",
    "dr kongo":        "dr congo",
    "kongodr":         "dr congo",
    "congo dr":        "dr congo",   # AF name "Congo DR"; NT name "DR Kongo"
    "kongo":           "congo",
    "algerie":         "algeria",
    "kamerun":         "cameroon",
    "nigeria":         "nigeria",
    "etopia":          "ethiopia",
    "de forente arabiske emirater": "united arab emirates",
    "forente arabiske emirater":    "united arab emirates",
    "de forente stater":            "united states",
    "slovakias":       "slovakia",
    "osterrikisk":     "austria",
    "sveitsisk":       "switzerland",
    "tyrkia":          "turkey",
    "russland":        "russia",
    "hviterussland":   "belarus",
    "ukraina":         "ukraine",
    "moldova":         "moldova",
    "wales":           "wales",
    "nord-irland":     "northern ireland",
    "irland":          "ireland",
    # Bosnia: NT "Bosnia-Hercegovina" strips hyphen -> "bosniahercegovina";
    #         AF "Bosnia & Herzegovina" strips & -> "bosnia herzegovina"
    "bosniahercegovina":      "bosnia and herzegovina",
    "bosnia herzegovina":     "bosnia and herzegovina",
    "bosnia and hercegovina": "bosnia and herzegovina",
    # Cape Verde: NT "Kapp Verde"; AF "Cape Verde Islands"
    "kapp verde":          "cape verde",
    "cape verde islands":  "cape verde",
    # Austria: NT "Østerrike" → strip Ø → "sterrike" (already have "osterrike" for O-version)
    "sterrike":            "austria",
}

_SUFFIX_RE = re.compile(r"\b(fc|fk|if|bk|sk|aik|ik|il|cf|sc|ss)\b")

_ARIA_ODDS_RE = re.compile(r"odds\s+([\d]+\.[\d]{1,2})", re.IGNORECASE)

_BTN_MORE = "[data-id='navigation_bonavigation_button_morema']"
_SEL_DIV  = "[data-for^='selection-event-']"

# Groups event-detail market toggles with their selection divs.
# Returns [{market: str, sels: [{aria: str}]}]
_MARKET_JS = """() => {
    const groups = [];
    const toggles = document.querySelectorAll('[data-id="navigation_event_selection_toggle"]');
    for (const toggle of toggles) {
        const nameEl = toggle.querySelector('[class*="NavItemCompetitorEvent"], h2');
        const mktName = nameEl ? nameEl.innerText.trim() : '';
        let wrapper = toggle.parentElement;
        for (let i = 0; i < 5; i++) {
            if (!wrapper) break;
            if (wrapper.className && (wrapper.className.includes('NavWrapper') ||
                wrapper.className.includes('EventRow'))) break;
            wrapper = wrapper.parentElement;
        }
        const container = wrapper || toggle.parentElement;
        const selEls = container
            ? container.querySelectorAll('[data-for^="selection-event-"]') : [];
        const sels = [];
        for (const s of selEls) { sels.push({aria: s.getAttribute('aria-label') || ''}); }
        if (sels.length > 0) groups.push({market: mktName, sels});
    }
    return groups;
}"""


def normalize_team_name(name: str) -> str:
    """Lowercase, strip diacritics, remove org suffixes, apply NO->EN map."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name.lower().strip())
    s = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return _NO_TO_EN.get(s, s)


def make_fixture_key(home: str, away: str, kickoff_date: str | None = None) -> str:
    """Canonical lookup key: normalize(home)|normalize(away)|YYYY-MM-DD."""
    return f"{normalize_team_name(home)}|{normalize_team_name(away)}|{(kickoff_date or '')[:10]}"


# ---- Kickoff parsing --------------------------------------------------------

_MO_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}

# NT kickoff format: "Tir.  30/6 19:00"  or  "Ons. 1/7 03:00"
_KO_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})\s+(\d{2}:\d{2})"  # "30/6 19:00"
)


def _parse_nt_kickoff(text: str) -> str | None:
    """Parse NT kickoff string to ISO date-time (local time, no tz)."""
    if not text:
        return None
    m = _KO_RE.search(text)
    if m:
        day, month, time_str = m.groups()
        year = datetime.now().year
        return f"{year}-{int(month):02d}-{int(day):02d}T{time_str}:00"
    return None


# ---- DB helpers -------------------------------------------------------------

_DDL_NT_ODDSEN = """
CREATE TABLE IF NOT EXISTS nt_oddsen_odds_snapshot (
    id               TEXT    PRIMARY KEY,
    scraped_at       TEXT    NOT NULL,
    source_url       TEXT    NOT NULL,
    fixture_key      TEXT    NOT NULL,
    home_team        TEXT    NOT NULL,
    away_team        TEXT    NOT NULL,
    league           TEXT,
    kickoff_iso      TEXT,
    market           TEXT    NOT NULL,
    selection        TEXT    NOT NULL,
    odds             REAL    NOT NULL,
    raw_json         TEXT,
    confidence_score REAL    DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_nt_oddsen_key
    ON nt_oddsen_odds_snapshot(fixture_key, market, selection, scraped_at);
CREATE INDEX IF NOT EXISTS idx_nt_oddsen_scraped
    ON nt_oddsen_odds_snapshot(scraped_at);
"""


def ensure_table(conn) -> None:
    conn.executescript(_DDL_NT_ODDSEN)


def store_nt_snapshot(conn, rows: list[dict]) -> int:
    """Insert rows into nt_oddsen_odds_snapshot. Skips duplicates (INSERT OR IGNORE)."""
    stored = 0
    for row in rows:
        conn.execute(
            """INSERT OR IGNORE INTO nt_oddsen_odds_snapshot
               (id, scraped_at, source_url, fixture_key, home_team, away_team,
                league, kickoff_iso, market, selection, odds, raw_json, confidence_score)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                row["scraped_at"],
                row["source_url"],
                row["fixture_key"],
                row["home_team"],
                row["away_team"],
                row.get("league"),
                row.get("kickoff_iso"),
                row["market"],
                row["selection"],
                row["odds"],
                row.get("raw_json"),
                row.get("confidence_score", 1.0),
            ),
        )
        stored += 1
    return stored


def load_nt_market_bulk(
    conn,
    market: str,
    required_sels: set,
    max_age_hours: int = 6,
) -> dict[str, dict[str, float]]:
    """
    Load NT Oddsen rows for a specific market (e.g. "BTTS", "OVER_UNDER_2_5").
    Returns {fixture_key: {selection: odds}} for fixtures where all required_sels are present.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        rows = conn.execute(
            """SELECT fixture_key, selection, odds
               FROM nt_oddsen_odds_snapshot
               WHERE market = ? AND scraped_at >= ?
               ORDER BY scraped_at DESC""",
            (market, cutoff),
        ).fetchall()
    except Exception:
        return {}

    raw: dict[str, dict[str, float]] = {}
    for r in rows:
        fk  = r["fixture_key"]
        sel = r["selection"]
        if fk not in raw:
            raw[fk] = {}
        if sel not in raw[fk]:
            raw[fk][sel] = float(r["odds"])

    result: dict[str, dict[str, float]] = {}
    for fk, sels in raw.items():
        if all(s in sels for s in required_sels):
            result[fk] = {s: sels[s] for s in required_sels}
    return result


def load_nt_odds_bulk(conn, max_age_hours: int = 6) -> dict[str, dict[str, float]]:
    """
    Load all recent NT Oddsen 1X2 rows into memory as:
      { fixture_key: {"H": float, "U": float, "B": float} }

    Only includes fixtures where all 3 selections (H, U, B) are present.
    Returns {} gracefully if the table does not exist yet.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        rows = conn.execute(
            """SELECT fixture_key, selection, odds
               FROM nt_oddsen_odds_snapshot
               WHERE market = '1x2' AND scraped_at >= ?
               ORDER BY scraped_at DESC""",
            (cutoff,),
        ).fetchall()
    except Exception:
        return {}

    # Aggregate per fixture_key; keep most-recent per selection
    raw: dict[str, dict[str, float]] = {}
    for r in rows:
        fk  = r["fixture_key"]
        sel = r["selection"]
        if fk not in raw:
            raw[fk] = {}
        if sel not in raw[fk]:  # most-recent first (ORDER BY DESC)
            raw[fk][sel] = float(r["odds"])

    # Only return fixtures with all 3 selections
    result: dict[str, dict[str, float]] = {}
    for fk, sels in raw.items():
        if all(s in sels for s in ("H", "U", "B")):
            result[fk] = {"H": sels["H"], "U": sels["U"], "B": sels["B"]}

    return result


# ---- Event-detail helpers ---------------------------------------------------

def _dismiss_cookie(page) -> None:
    """Dismiss NT cookie consent dialog before any iframe click; no-op if absent."""
    try:
        if not page.query_selector('[data-testid="ntds-dialog-sheet-backdrop"]'):
            return
        page.evaluate("""
            () => {
                const btns = [...document.querySelectorAll('button')];
                for (const t of ['Kun n', 'Godta', 'Lukk']) {
                    const b = btns.find(x => x.innerText && x.innerText.includes(t));
                    if (b) { b.click(); return; }
                }
            }
        """)
        page.wait_for_timeout(800)
    except Exception:
        pass


def _extract_btts_ou(frame) -> dict:
    """
    Extract BTTS and O/U 1.5 / 2.5 / 3.5 from an event detail iframe.
    Returns a dict with keys present only when found:
      btts_yes, btts_no  — odds for Ja / Nei
      over_15, under_15  — odds for Over 1.5 / Under 1.5
      over_25, under_25  — odds for Over 2.5 / Under 2.5
      over_35, under_35  — odds for Over 3.5 / Under 3.5
    First-half markets (containing "omgang") are excluded.
    DNB market captured when present:
      dnb_home, dnb_away — odds for Home / Away (Uavgjort tilbakebetales)
    """
    result: dict[str, float] = {}
    try:
        groups = frame.evaluate(_MARKET_JS)
    except Exception:
        return result
    for g in (groups or []):
        mkt  = g.get("market", "")
        sels = []
        for s in g.get("sels", []):
            aria = s.get("aria", "")
            mv = _ARIA_ODDS_RE.search(aria)
            if mv:
                v = float(mv.group(1))
                if 1.01 <= v <= 99.0:
                    sels.append({"label": aria.split(",")[0].strip(), "odds": v})
        t = mkt.lower()
        if "begge lag" in t:
            yes_ = next((s["odds"] for s in sels if s["label"].lower() == "ja"),  None)
            no_  = next((s["odds"] for s in sels if s["label"].lower() == "nei"), None)
            if yes_ and no_:
                result["btts_yes"] = yes_
                result["btts_no"]  = no_
        elif "uavgjort tilbakebetales" in t:
            # Draw No Bet: exactly 2 selections (Home / Away); reject if more
            if len(sels) == 2:
                result["dnb_home"] = sels[0]["odds"]
                result["dnb_away"] = sels[1]["odds"]
                result["dnb_home_label"] = sels[0]["label"]
                result["dnb_away_label"] = sels[1]["label"]
        elif "omgang" not in t and ("1,5" in t or "1.5" in t):
            ov = next((s["odds"] for s in sels if "over"  in s["label"].lower()), None)
            un = next((s["odds"] for s in sels if "under" in s["label"].lower()), None)
            if ov and un:
                result["over_15"]  = ov
                result["under_15"] = un
        elif "2,5" in t or "2.5" in t:
            ov = next((s["odds"] for s in sels if "over"  in s["label"].lower()), None)
            un = next((s["odds"] for s in sels if "under" in s["label"].lower()), None)
            if ov and un:
                result["over_25"]  = ov
                result["under_25"] = un
        elif "omgang" not in t and ("3,5" in t or "3.5" in t):
            ov = next((s["odds"] for s in sels if "over"  in s["label"].lower()), None)
            un = next((s["odds"] for s in sels if "under" in s["label"].lower()), None)
            if ov and un:
                result["over_35"]  = ov
                result["under_35"] = un
    return result


# ---- Scraper helpers --------------------------------------------------------

def _dump_debug_info(page, frame, attempt: int, verbose: bool) -> None:
    """Save screenshot + rendered HTML when 0 fixtures found. No-ops silently on error."""
    import pathlib
    debug_dir = pathlib.Path("logs")
    try:
        debug_dir.mkdir(exist_ok=True)
    except Exception:
        return
    ts     = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"nt_oddsen_debug_{ts}_attempt{attempt}"

    try:
        ss = str(debug_dir / f"{prefix}.png")
        page.screenshot(path=ss, full_page=False)
        if verbose:
            print(f"[NT Playwright]   screenshot -> {ss}")
    except Exception as exc:
        if verbose:
            print(f"[NT Playwright]   screenshot failed: {exc}")

    try:
        ht = str(debug_dir / f"{prefix}.html")
        with open(ht, "w", encoding="utf-8") as fh:
            fh.write(page.content())
        if verbose:
            print(f"[NT Playwright]   page html  -> {ht}")
    except Exception as exc:
        if verbose:
            print(f"[NT Playwright]   html save failed: {exc}")

    try:
        iframe_n = len(page.query_selector_all("iframe"))
        btn_n    = len(frame.query_selector_all(_BTN_MORE)) if frame else -1
        sel_n    = len(frame.query_selector_all("[data-for^='selection-event-']")) if frame else -1
        if verbose:
            print(
                f"[NT Playwright]   diagnostics: "
                f"url={page.url!r}  iframes={iframe_n}  btns={btn_n}  sel_divs={sel_n}"
            )
    except Exception:
        pass


def _wait_for_real_odds(frame, timeout_ms: int = 20_000) -> bool:
    """
    Stall until at least one selection div carries a real odds value in its
    aria-label (e.g. "Spain, odds 1.33").  The divs appear immediately as
    skeletons; the WebSocket fills them seconds later.  Returns True on
    success, False on timeout.
    """
    try:
        frame.wait_for_function(
            r"""() => {
                const divs = document.querySelectorAll('[data-for^="selection-event-"]');
                for (const d of divs) {
                    const a = d.getAttribute('aria-label') || '';
                    if (/odds\s+[\d.]+/.test(a)) return true;
                }
                return false;
            }""",
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def _extract_1x2(frame) -> tuple[list[dict], list[dict]]:
    """Return (meta_list, selections) from the sportsbook iframe."""
    containers = frame.query_selector_all("[class*='EventContainer']")
    meta_list: list[dict] = []
    for c in containers:
        try:
            team_els = c.query_selector_all("[class*='ParticipantNameItem']")
            teams    = [(t.inner_text() or "").strip() for t in team_els]
            if len(teams) < 2:
                continue
            kickoff_raw = ""
            dt = c.query_selector("[class*='DateContainer']")
            if dt:
                kickoff_raw = (dt.inner_text() or "").strip()
            league_str = ""
            lg = c.query_selector("[class*='TournamentNameItem']")
            if lg:
                league_str = (lg.inner_text() or "").strip()
            meta_list.append({
                "home": teams[0], "away": teams[1],
                "kickoff_raw": kickoff_raw, "league": league_str,
            })
        except Exception:
            pass

    sel_divs   = frame.query_selector_all("[data-for^='selection-event-']")
    selections: list[dict] = []
    for div in sel_divs:
        aria     = div.get_attribute("aria-label") or ""
        data_for = div.get_attribute("data-for")   or ""
        mv = _ARIA_ODDS_RE.search(aria)
        if not mv:
            continue
        odds_v = float(mv.group(1))
        if not (1.01 <= odds_v <= 99.0):
            continue
        selections.append({
            "label": aria.split(",")[0].strip(),
            "odds":  odds_v,
            "data_for": data_for,
        })
    return meta_list, selections


# ---- Multi-category helpers -------------------------------------------------

_CAT_PREFIX    = "navigation_verticalsportlist_sport_selection_"
_CAT_NUMERIC   = re.compile(r"^\d+\.\d+$")


def _assemble_matches(meta_list: list[dict], selections: list[dict]) -> list[dict]:
    """Convert (meta_list, selections) from _extract_1x2 into match records."""
    matches: list[dict] = []
    n_meta = len(meta_list)
    for i, gs in enumerate(range(0, len(selections) - 2, 3)):
        trio = selections[gs:gs + 3]
        if len(trio) < 3:
            break
        if i < n_meta:
            home   = meta_list[i]["home"]
            away   = meta_list[i]["away"]
            ko_raw = meta_list[i]["kickoff_raw"]
            league = meta_list[i]["league"]
        else:
            home   = trio[0]["label"]
            away   = trio[2]["label"]
            ko_raw = ""
            league = ""
        ko_iso  = _parse_nt_kickoff(ko_raw)
        ko_date = (ko_iso or "")[:10]
        matches.append({
            "home_team":    home,
            "away_team":    away,
            "league":       league,
            "kickoff_raw":  ko_raw,
            "kickoff_iso":  ko_iso,
            "kickoff_date": ko_date,
            "fixture_key":  make_fixture_key(home, away, ko_date),
            "odds_h":       trio[0]["odds"],
            "odds_u":       trio[1]["odds"],
            "odds_b":       trio[2]["odds"],
            "sel_labels":   [s["label"] for s in trio],
        })
    return matches


def _discover_categories(frame, page, verbose: bool = True) -> list[dict]:
    """
    Discover all football sub-category items from the left sidebar.
    Returns [{"data_id": str, "label": str, "count": int|None}, ...] in DOM order.
    Only returns numeric tournament IDs (e.g. 66748.1), not sport-level entries.
    """
    def _read(f) -> list[dict]:
        cats: list[dict] = []
        try:
            items = f.query_selector_all(f'[data-id^="{_CAT_PREFIX}"]')
            for item in items:
                did    = item.get_attribute("data-id") or ""
                suffix = did[len(_CAT_PREFIX):]
                if not _CAT_NUMERIC.match(suffix):
                    continue
                label_raw = (item.inner_text() or "").strip()
                m = re.match(r"^(.*?)\s*\((\d+)\)\s*$", label_raw)
                if m:
                    label = m.group(1).strip().lower()
                    count = int(m.group(2))
                else:
                    label = label_raw.lower()
                    count = None
                cats.append({"data_id": did, "label": label, "count": count})
        except Exception:
            pass
        return cats

    cats = _read(frame)
    if not cats:
        # Sub-menu may be collapsed — click Fotball top-level to expand
        try:
            btn = frame.query_selector(f'[data-id="{_CAT_PREFIX}Fotball"]')
            if btn:
                btn.click()
                page.wait_for_timeout(1_500)
                cats = _read(frame)
        except Exception:
            pass
    return cats


def _extract_btts_ou_for_matches(
    frame, page,
    cat_matches:    list[dict],
    settle_ms:      int,
    btts_ou_results: dict,
    cat_label:      str,
    verbose:        bool,
) -> int:
    """
    Per-event BTTS/OU extraction for all matches in cat_matches.
    Always does history.back() after each event (including the last) so the
    caller is left on the category match listing, ready for the next category.
    Returns the number of events where at least one market was extracted.
    """
    n_ok  = 0
    _sbf  = frame
    for idx in range(len(cat_matches)):
        try:
            _el   = page.query_selector("iframe#sportsbookid")
            _sbf  = (_el.content_frame() if _el else _sbf) or _sbf
            _btns = _sbf.query_selector_all(_BTN_MORE)
            if len(_btns) <= idx:
                break
            _btns[idx].scroll_into_view_if_needed()
            _btns[idx].click()
            page.wait_for_timeout(settle_ms)
            _el   = page.query_selector("iframe#sportsbookid")
            _sbf  = (_el.content_frame() if _el else _sbf) or _sbf
            _mkt  = _extract_btts_ou(_sbf)
            fk    = cat_matches[idx]["fixture_key"]
            if _mkt:
                btts_ou_results[fk] = _mkt
                n_ok += 1
            # Always navigate back (even last event) so the next category click works
            _sbf.evaluate("window.history.back()")
            page.wait_for_timeout(2_000)
            _el   = page.query_selector("iframe#sportsbookid")
            _sbf  = (_el.content_frame() if _el else _sbf) or _sbf
            is_last = (idx == len(cat_matches) - 1)
            if not is_last:
                try:
                    _sbf.wait_for_selector(_SEL_DIV, timeout=12_000)
                except Exception:
                    pass
                page.wait_for_timeout(settle_ms // 2)
                _el   = page.query_selector("iframe#sportsbookid")
                _sbf  = (_el.content_frame() if _el else _sbf) or _sbf
                if not _sbf.query_selector_all(_BTN_MORE):
                    if verbose:
                        print(
                            f"[NT Playwright] [{cat_label}] "
                            f"history.back() lost btn list at idx {idx}, stopping BTTS/OU"
                        )
                    break
        except Exception as ev_exc:
            if verbose:
                print(
                    f"[NT Playwright] [{cat_label}] "
                    f"event {idx} BTTS/OU error: {ev_exc!s:.80}"
                )
            break
    return n_ok


# ---- Scraper ----------------------------------------------------------------

def scrape_nt_oddsen_playwright(
    verbose:     bool = True,
    settle_ms:   int  = 5_000,
    timeout_ms:  int  = 30_000,
    max_retries: int  = 3,
) -> dict:
    """
    Scrape NT Oddsen football 1X2 + BTTS + O/U 2.5 via headless Playwright Chromium.

    Retries the main-page 1X2 extraction up to max_retries times.  On each
    failure a screenshot and rendered HTML are saved to logs/ for diagnosis.

    Returns:
        {
          "n_matches":     int,   # fixtures with 1X2 odds extracted
          "n_fixtures":    int,   # alias for n_matches
          "n_btts":        int,   # fixtures with BTTS odds extracted
          "n_ou25":        int,   # fixtures with O/U 2.5 odds extracted
          "n_rows_stored": int,   # total DB rows written (all markets)
          "n_stored":      int,   # alias for n_rows_stored
          "scraped_at":    str,   # ISO UTC timestamp
          "matches":       list,
          "error":         str | None,
        }
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        msg = "playwright not installed -- run: pip install playwright && python -m playwright install chromium"
        if verbose:
            print(f"[NT Playwright] {msg}")
        return {
            "error": "playwright_not_installed", "message": msg,
            "n_matches": 0, "n_fixtures": 0, "n_rows_stored": 0, "n_stored": 0,
            "n_btts": 0, "n_ou25": 0, "matches": [],
        }

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if verbose:
        print(f"[NT Playwright] Scraping {NT_SPORTSBOOK_URL} (max_retries={max_retries})...")

    matches_extracted: list[dict]       = []
    btts_ou_results:   dict[str, dict]  = {}
    error_msg: str | None               = None
    cat_stats: list[dict]               = []

    try:
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

            sb_frame = None

            # ── 1X2 extraction with retry ─────────────────────────────────────
            for attempt in range(1, max_retries + 1):
                if attempt > 1:
                    if verbose:
                        print(f"[NT Playwright] Retry {attempt}/{max_retries}: reloading page...")
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=30_000)
                    except Exception:
                        pass
                    page.wait_for_timeout(3_000)

                # Dismiss cookie overlay before any selection/rendering
                _dismiss_cookie(page)

                # Acquire sportsbook iframe
                try:
                    page.wait_for_selector("iframe#sportsbookid", timeout=15_000)
                except PWTimeout:
                    if verbose:
                        print(f"[NT Playwright] Attempt {attempt}: iframe#sportsbookid not found after 15s")
                    _dump_debug_info(page, None, attempt, verbose)
                    continue

                el = page.query_selector("iframe#sportsbookid")
                if not el:
                    if verbose:
                        print(f"[NT Playwright] Attempt {attempt}: iframe element is None")
                    continue
                sb_frame = el.content_frame()
                if not sb_frame:
                    if verbose:
                        print(f"[NT Playwright] Attempt {attempt}: iframe has no content frame")
                    continue

                # Wait for selection divs to exist
                try:
                    sb_frame.wait_for_selector("[data-for^='selection-event-']", timeout=timeout_ms)
                except PWTimeout:
                    if verbose:
                        print(
                            f"[NT Playwright] Attempt {attempt}: "
                            f"no selection-event divs after {timeout_ms // 1000}s"
                        )
                    _dump_debug_info(page, sb_frame, attempt, verbose)
                    continue

                # Wait for WebSocket odds to fill the aria-labels (not loading skeletons)
                if not _wait_for_real_odds(sb_frame, timeout_ms=20_000):
                    if verbose:
                        print(
                            f"[NT Playwright] Attempt {attempt}: "
                            "selection divs present but no real odds in aria-labels after 20s"
                        )
                    _dump_debug_info(page, sb_frame, attempt, verbose)
                    continue

                # Additional WebSocket settle
                page.wait_for_timeout(settle_ms)

                # Log diagnostics on every successful load
                try:
                    _iframe_n = len(page.query_selector_all("iframe"))
                    _btn_n    = len(sb_frame.query_selector_all(_BTN_MORE))
                    if verbose:
                        print(
                            f"[NT Playwright] Attempt {attempt}: "
                            f"url={page.url!r}  iframes={_iframe_n}  btns={_btn_n}"
                        )
                except Exception:
                    pass

                # Extract metadata + selections
                meta_list, selections = _extract_1x2(sb_frame)
                if verbose:
                    print(
                        f"[NT Playwright] Attempt {attempt}: "
                        f"containers={len(meta_list)}  sel_divs={len(selections)}"
                    )

                # Assemble match records
                candidate = _assemble_matches(meta_list, selections)

                if not candidate:
                    if verbose:
                        print(
                            f"[NT Playwright] Attempt {attempt}: "
                            f"0 matches assembled (containers={len(meta_list)}, sels={len(selections)})"
                        )
                    _dump_debug_info(page, sb_frame, attempt, verbose)
                    continue

                matches_extracted = candidate
                if verbose:
                    print(
                        f"[NT Playwright] Attempt {attempt}: "
                        f"{len(matches_extracted)} matches -- OK"
                    )
                break  # success

            if not matches_extracted and verbose:
                print(f"[NT Playwright] 1X2 extraction failed after {max_retries} attempts")

            # ── Multi-category loop ───────────────────────────────────────────
            did_per_category = False
            cat_stats: list[dict] = []

            if matches_extracted and sb_frame:
                # ── BTTS/OU for initial default-view matches ──────────────────
                # Run while still on the initial view (before any category nav).
                # This ensures WC/default fixtures get BTTS/OU even if their
                # category fails to reload below.
                _dismiss_cookie(page)
                page.wait_for_timeout(300)
                _n_init_btts = _extract_btts_ou_for_matches(
                    sb_frame, page, list(matches_extracted),
                    settle_ms, btts_ou_results, "initial", verbose,
                )
                if verbose:
                    print(
                        f"[NT Playwright] Initial BTTS/OU: "
                        f"{_n_init_btts}/{len(matches_extracted)} events"
                    )

                categories_found = _discover_categories(sb_frame, page, verbose)
                if verbose:
                    print(
                        f"[NT Playwright] Categories discovered: {len(categories_found)}  "
                        + "  ".join(
                            f"[{c['label']}={c['count']}]" for c in categories_found
                        )
                    )

                if categories_found:
                    # Seed with the initial extraction so that fixtures from
                    # categories that fail to load (e.g. internasjonal reloading
                    # slowly) are never dropped from the final output.
                    all_cat_matches: list[dict] = list(matches_extracted)
                    seen_keys: set[str]         = {m["fixture_key"] for m in matches_extracted}

                    for cat in categories_found:
                        cat_label = cat["label"]
                        cat_stat: dict = {
                            "label":     cat_label,
                            "n_fixtures": 0,
                            "n_btts_ou":  0,
                            "error":      None,
                        }
                        try:
                            # Click category nav item via JS (bypasses Playwright
                            # actionability checks; sidebar items pass DOM-ready
                            # but may fail Playwright's visible/stable guards)
                            _el   = page.query_selector("iframe#sportsbookid")
                            _sbf2 = (_el.content_frame() if _el else sb_frame) or sb_frame
                            did_escaped = cat["data_id"].replace("'", "\\'")
                            clicked = _sbf2.evaluate(
                                f"() => {{ "
                                f"  const el = document.querySelector('[data-id=\"{did_escaped}\"]'); "
                                f"  if (!el) return false; "
                                f"  el.click(); "
                                f"  return true; "
                                f"}}"
                            )
                            if not clicked:
                                raise RuntimeError("category button not found in iframe")
                            page.wait_for_timeout(2_000)

                            _el   = page.query_selector("iframe#sportsbookid")
                            _sbf2 = (_el.content_frame() if _el else sb_frame) or sb_frame

                            if not _wait_for_real_odds(_sbf2, timeout_ms=15_000):
                                raise RuntimeError("no real odds after 15 s")
                            page.wait_for_timeout(settle_ms)

                            _el   = page.query_selector("iframe#sportsbookid")
                            _sbf2 = (_el.content_frame() if _el else sb_frame) or sb_frame

                            meta_list, selections = _extract_1x2(_sbf2)
                            cat_matches = _assemble_matches(meta_list, selections)

                            # Dedup by fixture_key across categories
                            new_matches = [
                                m for m in cat_matches
                                if m["fixture_key"] not in seen_keys
                            ]
                            n_dupes = len(cat_matches) - len(new_matches)
                            for m in new_matches:
                                seen_keys.add(m["fixture_key"])
                            all_cat_matches.extend(new_matches)
                            cat_stat["n_fixtures"] = len(new_matches)

                            if verbose:
                                print(
                                    f"[NT Playwright] [{cat_label}] "
                                    f"{len(new_matches)} fixtures"
                                    + (f"  ({n_dupes} dupes skipped)" if n_dupes else "")
                                )

                            # BTTS/OU for this category's new fixtures
                            if new_matches:
                                _dismiss_cookie(page)
                                page.wait_for_timeout(300)
                                n_ok = _extract_btts_ou_for_matches(
                                    _sbf2, page, new_matches,
                                    settle_ms, btts_ou_results,
                                    cat_label, verbose,
                                )
                                cat_stat["n_btts_ou"] = n_ok

                        except Exception as cat_exc:
                            cat_stat["error"] = str(cat_exc)[:120]
                            if verbose:
                                print(
                                    f"[NT Playwright] [{cat_label}] FAILED: "
                                    f"{cat_exc!s:.120}"
                                )

                        cat_stats.append(cat_stat)

                    if all_cat_matches:
                        matches_extracted  = all_cat_matches
                        did_per_category   = True

                        if verbose:
                            ok_cats   = sum(1 for c in cat_stats if not c["error"])
                            fail_cats = len(cat_stats) - ok_cats
                            print(
                                f"[NT Playwright] Category summary: "
                                f"{ok_cats}/{len(cat_stats)} OK  "
                                f"{len(matches_extracted)} unique fixtures  "
                                f"failures={fail_cats}"
                            )
                            for c in cat_stats:
                                status = "OK" if not c["error"] else f"FAIL({c['error'][:40]})"
                                print(
                                    f"  [{c['label']:20}] "
                                    f"fixtures={c['n_fixtures']:3}  "
                                    f"btts_ou={c['n_btts_ou']:3}  "
                                    f"{status}"
                                )

            # ── BTTS / O/U 2.5 (fallback: per-event navigation) ──────────────
            # Only runs when matches_extracted is set but the initial BTTS/OU
            # block above was skipped (matches_extracted was empty at that point,
            # meaning the initial view produced 0 results AND category discovery
            # also produced nothing).  In practice: first cold start only.
            if not did_per_category and not btts_ou_results and matches_extracted and sb_frame:
                _dismiss_cookie(page)
                page.wait_for_timeout(500)
                _sbf = sb_frame
                for idx in range(len(matches_extracted)):
                    try:
                        _el  = page.query_selector("iframe#sportsbookid")
                        _sbf = (_el.content_frame() if _el else _sbf) or _sbf
                        _btns = _sbf.query_selector_all(_BTN_MORE)
                        if len(_btns) <= idx:
                            break
                        _btns[idx].scroll_into_view_if_needed()
                        _btns[idx].click()
                        page.wait_for_timeout(settle_ms)
                        _el  = page.query_selector("iframe#sportsbookid")
                        _sbf = (_el.content_frame() if _el else _sbf) or _sbf
                        _mkt = _extract_btts_ou(_sbf)
                        fk   = matches_extracted[idx]["fixture_key"]
                        if _mkt:
                            btts_ou_results[fk] = _mkt
                        if idx < len(matches_extracted) - 1:
                            _sbf.evaluate("window.history.back()")
                            page.wait_for_timeout(2_000)
                            _el  = page.query_selector("iframe#sportsbookid")
                            _sbf = (_el.content_frame() if _el else _sbf) or _sbf
                            try:
                                _sbf.wait_for_selector(_SEL_DIV, timeout=12_000)
                            except Exception:
                                pass
                            page.wait_for_timeout(settle_ms // 2)
                            _el  = page.query_selector("iframe#sportsbookid")
                            _sbf = (_el.content_frame() if _el else _sbf) or _sbf
                            if not _sbf.query_selector_all(_BTN_MORE):
                                if verbose:
                                    print(f"[NT Playwright] history.back() lost btn list at idx {idx}, stopping")
                                break
                    except Exception as _ev_exc:
                        if verbose:
                            print(f"[NT Playwright] event {idx} detail error: {_ev_exc!s:.80}")
                        break

            browser.close()

    except Exception as exc:
        error_msg = str(exc)
        if verbose:
            print(f"[NT Playwright] ERROR: {exc}")

    n_btts_extracted = sum(1 for v in btts_ou_results.values() if v.get("btts_yes"))
    n_ou15_extracted = sum(1 for v in btts_ou_results.values() if v.get("over_15"))
    n_ou25_extracted = sum(1 for v in btts_ou_results.values() if v.get("over_25"))
    n_ou35_extracted = sum(1 for v in btts_ou_results.values() if v.get("over_35"))
    n_dnb_extracted  = sum(1 for v in btts_ou_results.values() if v.get("dnb_home"))

    if verbose and matches_extracted:
        print(
            f"[NT Playwright] Extracted {len(matches_extracted)} matches  "
            f"BTTS={n_btts_extracted}  "
            f"OU1.5={n_ou15_extracted}  OU2.5={n_ou25_extracted}  OU3.5={n_ou35_extracted}  "
            f"DNB={n_dnb_extracted}"
        )

    # ── Build DB rows and store ───────────────────────────────────────────────
    rows: list[dict] = []
    for m in matches_extracted:
        fk = m["fixture_key"]
        base_common = {
            "scraped_at":       scraped_at,
            "source_url":       NT_SPORTSBOOK_URL,
            "fixture_key":      fk,
            "home_team":        m["home_team"],
            "away_team":        m["away_team"],
            "league":           m["league"] or None,
            "kickoff_iso":      m["kickoff_iso"],
            "confidence_score": 1.0,
        }
        raw_1x2 = json.dumps({
            "home": m["home_team"], "away": m["away_team"],
            "league": m["league"], "kickoff_raw": m["kickoff_raw"],
            "H": m["odds_h"], "U": m["odds_u"], "B": m["odds_b"],
        }, ensure_ascii=False)
        base_1x2 = {**base_common, "market": "1x2", "raw_json": raw_1x2}
        rows.append({**base_1x2, "selection": "H", "odds": m["odds_h"]})
        rows.append({**base_1x2, "selection": "U", "odds": m["odds_u"]})
        rows.append({**base_1x2, "selection": "B", "odds": m["odds_b"]})
        ou = btts_ou_results.get(fk, {})
        if ou.get("btts_yes") and ou.get("btts_no"):
            raw_btts = json.dumps({"yes": ou["btts_yes"], "no": ou["btts_no"]})
            base_btts = {**base_common, "market": "BTTS", "raw_json": raw_btts}
            rows.append({**base_btts, "selection": "YES", "odds": ou["btts_yes"]})
            rows.append({**base_btts, "selection": "NO",  "odds": ou["btts_no"]})
        if ou.get("over_15") and ou.get("under_15"):
            raw_ou15 = json.dumps({"over": ou["over_15"], "under": ou["under_15"]})
            base_ou15 = {**base_common, "market": "OVER_UNDER_1_5", "raw_json": raw_ou15}
            rows.append({**base_ou15, "selection": "OVER",  "odds": ou["over_15"]})
            rows.append({**base_ou15, "selection": "UNDER", "odds": ou["under_15"]})
        if ou.get("over_25") and ou.get("under_25"):
            raw_ou = json.dumps({"over": ou["over_25"], "under": ou["under_25"]})
            base_ou = {**base_common, "market": "OVER_UNDER_2_5", "raw_json": raw_ou}
            rows.append({**base_ou, "selection": "OVER",  "odds": ou["over_25"]})
            rows.append({**base_ou, "selection": "UNDER", "odds": ou["under_25"]})
        if ou.get("over_35") and ou.get("under_35"):
            raw_ou35 = json.dumps({"over": ou["over_35"], "under": ou["under_35"]})
            base_ou35 = {**base_common, "market": "OVER_UNDER_3_5", "raw_json": raw_ou35}
            rows.append({**base_ou35, "selection": "OVER",  "odds": ou["over_35"]})
            rows.append({**base_ou35, "selection": "UNDER", "odds": ou["under_35"]})

    n_stored = 0
    if rows:
        try:
            from db.connection import get_conn
            conn = get_conn()
            ensure_table(conn)
            n_stored = store_nt_snapshot(conn, rows)
            conn.commit()
            conn.close()
        except Exception as exc:
            if verbose:
                print(f"[NT Playwright] DB store error: {exc}")
            error_msg = error_msg or str(exc)

    if verbose and n_stored:
        print(f"[NT Playwright] Stored {n_stored} rows ({len(matches_extracted)} matches × 1X2 + BTTS/OU)")

    return {
        "n_matches":        len(matches_extracted),
        "n_fixtures":       len(matches_extracted),   # alias
        "n_btts":           n_btts_extracted,
        "n_ou15":           n_ou15_extracted,
        "n_ou25":           n_ou25_extracted,
        "n_ou35":           n_ou35_extracted,
        "n_dnb":            n_dnb_extracted,
        "n_rows_stored":    n_stored,
        "n_stored":         n_stored,                 # alias
        "scraped_at":       scraped_at,
        "matches":          matches_extracted,
        "category_stats":   cat_stats,
        "error":            error_msg,
    }
