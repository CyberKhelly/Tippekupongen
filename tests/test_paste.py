"""
End-to-end test for the Tippekupongen Streamlit app.
Verifies: paste fixtures, parse, form population, analyse, coupon visualization.

Run with:
    python test_paste.py
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

SHOTS_DIR = Path("test_screenshots")
SHOTS_DIR.mkdir(exist_ok=True)
APP_URL = "http://localhost:8501"

PASTE_INPUT = """\
1 Tyskland - Norge
2 Osterrike - Slovenia
3 Polen - Frankrike
4 Spania - Kroatia
5 Belgia - Italia
6 Portugal - Sveits
7 Arsenal - Chelsea
8 Man City - Liverpool
9 Real Madrid - Barcelona
10 Juventus - Inter Milan
11 Dortmund - Bayern
12 Ajax - PSV"""

EXPECTED_HOMES = [
    "Tyskland", "Osterrike", "Polen", "Spania", "Belgia", "Portugal",
    "Arsenal", "Man City", "Real Madrid", "Juventus", "Dortmund", "Ajax",
]
EXPECTED_AWAYS = [
    "Norge", "Slovenia", "Frankrike", "Kroatia", "Italia", "Sveits",
    "Chelsea", "Liverpool", "Barcelona", "Inter Milan", "Bayern", "PSV",
]

ODDS = [
    (1.90, 3.50, 4.00), (2.10, 3.20, 3.60), (1.50, 4.00, 6.00),
    (2.00, 3.30, 3.80), (1.70, 3.70, 4.50), (1.60, 3.80, 5.00),
    (1.85, 3.60, 4.20), (2.10, 3.40, 3.50), (2.00, 3.50, 3.80),
    (2.30, 3.20, 3.10), (3.80, 3.50, 1.95), (2.00, 3.40, 3.70),
]

PASS = []
FAIL = []

def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  [PASS] {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name}" + (f"  ({detail})" if detail else ""))

def shot(page, name):
    path = SHOTS_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"         -> {path.name}")

def wait_st(page, timeout=12000):
    """Wait for Streamlit's rerun indicator to disappear."""
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=timeout)
    except PWTimeout:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except PWTimeout:
        pass
    page.wait_for_timeout(400)

def ensure_expander_open(page):
    """Open the fixture expander only if it is currently collapsed."""
    textarea = page.get_by_label("Fixtures")
    if textarea.is_visible():
        return  # already open
    header = page.get_by_text("Load or Paste Fixtures")
    header.click()
    page.wait_for_timeout(600)

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # ── 1. Load the app ───────────────────────────────────────────────────
        print("\n[1] Loading app...")
        page.goto(APP_URL, wait_until="networkidle", timeout=30000)
        wait_st(page)
        check("App title visible", "Tippekupongen" in page.title(), page.title())
        shot(page, "01_initial_load")

        # ── 2. Expander open state ────────────────────────────────────────────
        print("\n[2] Checking expander state...")
        textarea = page.get_by_label("Fixtures")
        check("Fixture textarea visible on load", textarea.is_visible())
        check("Parse Fixtures button visible", page.get_by_role("button", name="Parse Fixtures").is_visible())
        check("Load Example Coupon button visible", page.get_by_role("button", name="Load Example Coupon").is_visible())

        # ── 3. Paste fixtures ─────────────────────────────────────────────────
        print("\n[3] Pasting fixture text...")
        ensure_expander_open(page)
        textarea = page.get_by_label("Fixtures")
        textarea.fill(PASTE_INPUT)
        page.wait_for_timeout(300)
        pasted_val = textarea.input_value()
        check("Paste accepted all 12 lines", pasted_val.count("\n") == 11,
              f"{pasted_val.count(chr(10))+1} lines")
        check("First fixture in textarea", "Tyskland" in pasted_val)
        check("Last fixture in textarea", "Ajax" in pasted_val)
        shot(page, "02_fixtures_pasted")

        # ── 4. Parse Fixtures ─────────────────────────────────────────────────
        print("\n[4] Clicking Parse Fixtures...")
        page.get_by_role("button", name="Parse Fixtures").click()
        wait_st(page)
        shot(page, "03_after_parse")

        # ── 5. Verify team names populated ────────────────────────────────────
        print("\n[5] Checking team names populated in form...")
        home_inputs = page.get_by_label("home").all()
        away_inputs = page.get_by_label("away").all()
        check("12 home inputs found", len(home_inputs) == 12, f"got {len(home_inputs)}")
        check("12 away inputs found", len(away_inputs) == 12, f"got {len(away_inputs)}")

        all_homes_ok = True
        all_aways_ok = True
        mismatches = []
        for i, (exp_h, exp_a) in enumerate(zip(EXPECTED_HOMES, EXPECTED_AWAYS)):
            got_h = home_inputs[i].input_value() if i < len(home_inputs) else ""
            got_a = away_inputs[i].input_value() if i < len(away_inputs) else ""
            if got_h != exp_h:
                all_homes_ok = False
                mismatches.append(f"M{i+1} home: expected '{exp_h}' got '{got_h}'")
            if got_a != exp_a:
                all_aways_ok = False
                mismatches.append(f"M{i+1} away: expected '{exp_a}' got '{got_a}'")
        check("All home teams populated correctly", all_homes_ok)
        check("All away teams populated correctly", all_aways_ok)
        for m in mismatches[:3]:
            print(f"         {m}")
        shot(page, "04_teams_populated")

        # ── 6. Enter odds ─────────────────────────────────────────────────────
        print("\n[6] Entering odds for 12 matches...")
        number_inputs = page.locator('input[type="number"]').all()
        # First 3 are budget/cost_per_row — skip them? Actually let's count:
        # form has: 12*3 = 36 odds inputs + 2 budget inputs = 38 total
        # budget inputs come AFTER all odds inputs in DOM order
        check("36 odds number inputs found", len(number_inputs) >= 36,
              f"got {len(number_inputs)}")
        for i, (oh, ou, ob) in enumerate(ODDS):
            base = i * 3
            if base + 2 < len(number_inputs):
                number_inputs[base].fill(str(oh))
                number_inputs[base + 1].fill(str(ou))
                number_inputs[base + 2].fill(str(ob))
        shot(page, "05_odds_entered")

        # ── 7. Analyse Coupon ─────────────────────────────────────────────────
        print("\n[7] Clicking Analyse Coupon...")
        page.get_by_role("button", name="Analyse Coupon").click()
        wait_st(page, timeout=20000)
        shot(page, "06_results")

        # ── 8. Verify results ─────────────────────────────────────────────────
        print("\n[8] Checking results...")
        body = page.inner_text("body")
        check("Match Analysis heading visible",  "Match Analysis"    in body)
        check("Optimized Coupon heading visible", "Optimized Coupon"  in body)
        check("TIPPEKUPONGEN coupon card visible","TIPPEKUPONGEN"     in body)
        check("Avg confidence metric visible",    "Avg confidence"    in body)
        check("Coupon rows metric visible",       "Coupon rows"       in body)
        check("Bankers metric visible",           "Bankers"           in body)
        shot(page, "07_results_scroll")

        # Scroll down to see the coupon card
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
        shot(page, "08_coupon_card")

        # ── 9. Session state: results survive expander interaction ─────────────
        print("\n[9] Testing session state persistence...")
        ensure_expander_open(page)
        page.wait_for_timeout(400)
        body_after = page.inner_text("body")
        check("Results still visible after expander interaction",
              "TIPPEKUPONGEN" in body_after)
        shot(page, "09_persistence_check")

        # ── 10. Load Example Coupon button ────────────────────────────────────
        print("\n[10] Testing Load Example Coupon...")
        ensure_expander_open(page)
        page.get_by_role("button", name="Load Example Coupon").click()
        wait_st(page)
        home_1 = page.get_by_label("home").first.input_value()
        check("Example loads Arsenal as first home team", home_1 == "Arsenal",
              f"got '{home_1}'")
        shot(page, "10_example_loaded")

        browser.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  {len(PASS)} passed  |  {len(FAIL)} failed")
    if FAIL:
        print(f"  Failed checks: {', '.join(FAIL)}")
    print(f"  Screenshots: {SHOTS_DIR.resolve()}")
    return len(FAIL) == 0

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
