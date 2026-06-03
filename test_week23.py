"""
End-to-end test for uke 23 2026 fixture loading.
Tests all three coupons: midtuke, lørdag, søndag.
Verifies: fixtures load, odds prefill, analysis runs, coupon renders.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from data.coupon_week23_2026 import COUPONS

SHOTS = Path("test_screenshots"); SHOTS.mkdir(exist_ok=True)
URL   = "http://localhost:8501"

PASS, FAIL = [], []

def check(name, condition, detail=""):
    if condition:
        PASS.append(name); print(f"  [PASS] {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL.append(name); print(f"  [FAIL] {name}" + (f"  ({detail})" if detail else ""))

def shot(page, name):
    p = SHOTS / f"{name}.png"; page.screenshot(path=str(p), full_page=True)
    print(f"         -> {p.name}")

def wait_st(page, timeout=15000):
    try: page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=timeout)
    except PWTimeout: pass
    try: page.wait_for_load_state("networkidle", timeout=5000)
    except PWTimeout: pass
    page.wait_for_timeout(500)

def ensure_expander_open(page):
    ta = page.get_by_label("Fixtures")
    if not ta.is_visible():
        page.get_by_text("Load or Paste Fixtures").click()
        page.wait_for_timeout(600)

def load_coupon(page, label):
    """Select a coupon from the dropdown and click Last inn."""
    ensure_expander_open(page)
    page.get_by_label("Fixtures").wait_for(state="visible", timeout=5000)
    # open the selectbox
    page.locator('[data-testid="stSelectbox"]').first.click()
    page.wait_for_timeout(400)
    # click the option inside the virtual dropdown list only
    page.locator('[data-testid="stSelectboxVirtualDropdown"]').get_by_text(label).click()
    page.wait_for_timeout(400)
    page.get_by_role("button", name="Last inn").click()
    wait_st(page)

def verify_coupon(page, key, label):
    """Check that the correct team names and odds are loaded for a coupon."""
    matches = COUPONS[key]["matches"]
    home_inputs = page.get_by_label("home").all()
    away_inputs = page.get_by_label("away").all()
    num_inputs  = page.locator('input[type="number"]').all()

    name_ok, odds_ok = True, True
    for i, (home, away, oh, ou, ob) in enumerate(matches):
        got_h = home_inputs[i].input_value() if i < len(home_inputs) else ""
        got_a = away_inputs[i].input_value() if i < len(away_inputs) else ""
        if got_h != home or got_a != away:
            name_ok = False
            print(f"         M{i+1}: expected '{home}'/'{away}' got '{got_h}'/'{got_a}'")

        # odds inputs: 3 per match (H, U, B)
        base = i * 3
        if base + 2 < len(num_inputs):
            got_oh = float(num_inputs[base].input_value() or 0)
            got_ou = float(num_inputs[base+1].input_value() or 0)
            got_ob = float(num_inputs[base+2].input_value() or 0)
            if abs(got_oh - oh) > 0.01 or abs(got_ou - ou) > 0.01 or abs(got_ob - ob) > 0.01:
                odds_ok = False
                print(f"         M{i+1} odds: expected {oh}/{ou}/{ob} got {got_oh}/{got_ou}/{got_ob}")

    check(f"{label}: 12 team names correct", name_ok)
    check(f"{label}: 12 x 3 odds prefilled", odds_ok)

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # ── 1. Load app ───────────────────────────────────────────────────────
        print("\n[1] Loading app...")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        wait_st(page)
        check("App loads", "Tippekupongen" in page.title(), page.title())
        shot(page, "w23_01_initial")

        # ── 2. Midtuke ────────────────────────────────────────────────────────
        print("\n[2] Loading Midtuke...")
        load_coupon(page, COUPONS["midtuke"]["label"])
        shot(page, "w23_02_midtuke_loaded")
        verify_coupon(page, "midtuke", "Midtuke")

        # Spot-check a few expected teams
        home_inputs = page.get_by_label("home").all()
        check("Midtuke M1 home = Deutschland", home_inputs[0].input_value() == "Deutschland")
        check("Midtuke M10 home = Spania",     home_inputs[9].input_value() == "Spania")

        # ── 3. Analyse midtuke ────────────────────────────────────────────────
        print("\n[3] Analysing Midtuke...")
        page.get_by_role("button", name="Analyse Coupon").click()
        wait_st(page, 20000)
        # Scroll to bottom so Streamlit renders the results section
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
        body = page.inner_text("body")
        check("Analysis: Match Analysis table visible",  "Match Analysis"   in body)
        check("Analysis: coupon card visible",           "TIPPEKUPONGEN"    in body)
        check("Analysis: Bankers metric visible",        "Bankers"          in body)
        shot(page, "w23_03_midtuke_analysis")

        # ── 4. Lørdag ─────────────────────────────────────────────────────────
        print("\n[4] Loading Lørdag...")
        load_coupon(page, COUPONS["lordag"]["label"])
        shot(page, "w23_04_lordag_loaded")
        verify_coupon(page, "lordag", "Lordag")

        home_inputs = page.get_by_label("home").all()
        check("Lordag M1 home = Belgia",   home_inputs[0].input_value() == "Belgia")
        check("Lordag M9 home = England",  home_inputs[8].input_value() == "England")

        # ── 5. Analyse lørdag ─────────────────────────────────────────────────
        print("\n[5] Analysing Lørdag...")
        page.get_by_role("button", name="Analyse Coupon").click()
        wait_st(page, 20000)
        body = page.inner_text("body")
        check("Lordag analysis renders",  "TIPPEKUPONGEN" in body)
        shot(page, "w23_05_lordag_analysis")

        # ── 6. Søndag ─────────────────────────────────────────────────────────
        print("\n[6] Loading Søndag...")
        load_coupon(page, COUPONS["sondag"]["label"])
        shot(page, "w23_06_sondag_loaded")
        verify_coupon(page, "sondag", "Sondag")

        home_inputs = page.get_by_label("home").all()
        check("Sondag M1 home = Marokko",  home_inputs[0].input_value() == "Marokko")
        check("Sondag M7 home = Ranheim",  home_inputs[6].input_value() == "Ranheim")

        # ── 7. Analyse søndag ─────────────────────────────────────────────────
        print("\n[7] Analysing Søndag...")
        page.get_by_role("button", name="Analyse Coupon").click()
        wait_st(page, 20000)
        body = page.inner_text("body")
        check("Sondag analysis renders",  "TIPPEKUPONGEN" in body)
        shot(page, "w23_07_sondag_analysis")

        # ── 8. Full flow: Midtuke → budget → coupon ───────────────────────────
        print("\n[8] Full flow: Midtuke with 192 NOK budget...")
        load_coupon(page, COUPONS["midtuke"]["label"])
        page.get_by_role("button", name="Analyse Coupon").click()
        wait_st(page, 20000)
        body = page.inner_text("body")
        check("Full flow: rows metric present", "Coupon rows" in body)
        check("Full flow: cost metric present", "Total cost"  in body)
        shot(page, "w23_08_full_flow")

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
        shot(page, "w23_09_coupon_bottom")

        browser.close()

    print(f"\n{'='*55}")
    print(f"  {len(PASS)} passed  |  {len(FAIL)} failed")
    if FAIL: print(f"  Failed: {', '.join(FAIL)}")
    print(f"  Screenshots: {SHOTS.resolve()}")
    return len(FAIL) == 0

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
