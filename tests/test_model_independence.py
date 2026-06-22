"""
Tests: model probability must be independent of NT public/expert percentages.

Core invariant:
  Changing expert_h/u/b or public_h/u/b must NEVER change match.prob_h/u/b.
  Only bookmaker odds and AF statistical signals (form, standings, goals)
  may influence the final model probability.
"""
import pytest
from models.match import Match
from analysis.probability import process_match
from analysis.model import run_model


def _make_match(odds_h=2.0, odds_u=3.5, odds_b=3.0):
    m = Match(number=1, home_team="Home FC", away_team="Away FC",
              odds_h=odds_h, odds_u=odds_u, odds_b=odds_b)
    process_match(m)
    return m


def _run(enrichment: dict | None) -> tuple[float, float, float]:
    m = _make_match()
    run_model(m, enrichment)
    return m.prob_h, m.prob_u, m.prob_b


# ── NT expert independence ─────────────────────────────────────────────────────

def test_expert_tips_absent_vs_present():
    """Model prob must be identical whether expert tips are missing or present."""
    base = {"home_last_5": "WWDWW", "away_last_5": "LLDLL"}
    with_expert = {**base, "expert_h": 60.0, "expert_u": 20.0, "expert_b": 20.0}

    h0, u0, b0 = _run(base)
    h1, u1, b1 = _run(with_expert)

    assert h0 == pytest.approx(h1, abs=1e-9)
    assert u0 == pytest.approx(u1, abs=1e-9)
    assert b0 == pytest.approx(b1, abs=1e-9)


def test_expert_tips_extreme_values_no_effect():
    """Even extreme expert tips (90/5/5 vs 5/5/90) must not move model prob."""
    base = {"home_last_5": "WWWWW", "away_last_5": "LLLLL",
            "public_h": 50.0, "public_u": 25.0, "public_b": 25.0}

    home_heavy = {**base, "expert_h": 90.0, "expert_u": 5.0, "expert_b": 5.0}
    away_heavy = {**base, "expert_h": 5.0,  "expert_u": 5.0, "expert_b": 90.0}

    h1, u1, b1 = _run(home_heavy)
    h2, u2, b2 = _run(away_heavy)

    assert h1 == pytest.approx(h2, abs=1e-9)
    assert u1 == pytest.approx(u2, abs=1e-9)
    assert b1 == pytest.approx(b2, abs=1e-9)


def test_expert_tips_with_no_af_stats():
    """Expert tips alone (no AF stats) must not affect model prob at all."""
    h0, u0, b0 = _run(None)
    h1, u1, b1 = _run({"expert_h": 70.0, "expert_u": 15.0, "expert_b": 15.0})

    assert h0 == pytest.approx(h1, abs=1e-9)
    assert u0 == pytest.approx(u1, abs=1e-9)
    assert b0 == pytest.approx(b1, abs=1e-9)


# ── NT public independence ─────────────────────────────────────────────────────

def test_public_tips_dont_affect_model_prob():
    """Public tips must not change model probability — only value/edge."""
    base = {"home_last_5": "WDWWW"}

    real_pub   = {**base, "public_h": 55.0, "public_u": 25.0, "public_b": 20.0}
    fake_pub   = {**base, "public_h": 90.0, "public_u": 5.0,  "public_b": 5.0}
    no_pub     = base

    h0, u0, b0 = _run(real_pub)
    h1, u1, b1 = _run(fake_pub)
    h2, u2, b2 = _run(no_pub)

    assert h0 == pytest.approx(h1, abs=1e-9)
    assert u0 == pytest.approx(u1, abs=1e-9)
    assert b0 == pytest.approx(b1, abs=1e-9)

    assert h0 == pytest.approx(h2, abs=1e-9)
    assert u0 == pytest.approx(u2, abs=1e-9)
    assert b0 == pytest.approx(b2, abs=1e-9)


def test_public_tips_do_affect_value():
    """Changing public tips must change value scores even though prob is unchanged."""
    m1 = _make_match()
    run_model(m1, {"public_h": 30.0, "public_u": 35.0, "public_b": 35.0})

    m2 = _make_match()
    run_model(m2, {"public_h": 80.0, "public_u": 10.0, "public_b": 10.0})

    # Prob unchanged
    assert m1.prob_h == pytest.approx(m2.prob_h, abs=1e-9)

    # But value changes
    assert m1.value_h is not None
    assert m2.value_h is not None
    assert m1.value_h != pytest.approx(m2.value_h, abs=0.01)


# ── Bookmaker odds are the driver ──────────────────────────────────────────────

def test_model_prob_equals_bookmaker_prior_when_no_af_stats():
    """Without AF stats, model prob = vig-normalised bookmaker prior exactly."""
    m = _make_match(odds_h=2.0, odds_u=3.5, odds_b=3.0)
    # Enrichment with only NT data — AF stats absent
    run_model(m, {"expert_h": 70.0, "expert_u": 15.0, "expert_b": 15.0,
                  "public_h": 80.0, "public_u": 10.0, "public_b": 10.0})

    raw_h = 1 / 2.0
    raw_u = 1 / 3.5
    raw_b = 1 / 3.0
    total = raw_h + raw_u + raw_b

    assert m.prob_h == pytest.approx(raw_h / total, abs=1e-9)
    assert m.prob_u == pytest.approx(raw_u / total, abs=1e-9)
    assert m.prob_b == pytest.approx(raw_b / total, abs=1e-9)


def test_af_form_adjusts_model_prob():
    """AF form signals do change model prob (they are allowed to)."""
    m_strong = _make_match()
    run_model(m_strong, {"home_last_5": "WWWWW", "away_last_5": "LLLLL"})

    m_weak = _make_match()
    run_model(m_weak, {"home_last_5": "LLLLL", "away_last_5": "WWWWW"})

    assert m_strong.prob_h > m_weak.prob_h
    assert m_strong.prob_b < m_weak.prob_b


def test_different_odds_produce_different_probs():
    """Changing bookmaker odds does change model prob."""
    m1 = Match(number=1, home_team="A", away_team="B",
               odds_h=1.5, odds_u=4.0, odds_b=6.0)
    process_match(m1)
    run_model(m1, None)

    m2 = Match(number=1, home_team="A", away_team="B",
               odds_h=3.5, odds_u=3.5, odds_b=2.0)
    process_match(m2)
    run_model(m2, None)

    assert m1.prob_h != pytest.approx(m2.prob_h, abs=0.01)


# ── Full verification: same fixture, different NT percentages ──────────────────

def test_model_unchanged_when_only_nt_percentages_change():
    """
    Primary verification test.

    Run the same fixture twice:
    - Once with real NT percentages (55/25/20)
    - Once with fake NT percentages (90/5/5)

    Expected: model H/U/B identical; value/CDS may differ.
    """
    af_stats = {
        "home_last_5": "WWDWW",
        "away_last_5": "LDLWL",
        "home_position": 3,
        "away_position": 11,
        "home_goals_for": 30,
        "home_goals_against": 15,
        "away_goals_for": 18,
        "away_goals_against": 28,
    }

    real_nt = {**af_stats,
               "expert_h": 55.0, "expert_u": 25.0, "expert_b": 20.0,
               "public_h": 55.0, "public_u": 25.0, "public_b": 20.0}

    fake_nt = {**af_stats,
               "expert_h": 90.0, "expert_u": 5.0,  "expert_b": 5.0,
               "public_h": 90.0, "public_u": 5.0,  "public_b": 5.0}

    m_real = _make_match()
    run_model(m_real, real_nt)

    m_fake = _make_match()
    run_model(m_fake, fake_nt)

    # Model probability must be identical
    assert m_real.prob_h == pytest.approx(m_fake.prob_h, abs=1e-9), (
        f"prob_h changed: {m_real.prob_h:.6f} vs {m_fake.prob_h:.6f}")
    assert m_real.prob_u == pytest.approx(m_fake.prob_u, abs=1e-9), (
        f"prob_u changed: {m_real.prob_u:.6f} vs {m_fake.prob_u:.6f}")
    assert m_real.prob_b == pytest.approx(m_fake.prob_b, abs=1e-9), (
        f"prob_b changed: {m_real.prob_b:.6f} vs {m_fake.prob_b:.6f}")

    # Value/edge MUST differ (public tips changed significantly)
    assert m_real.value_h != pytest.approx(m_fake.value_h, abs=0.1), (
        "value_h should differ when public tips change")
    assert m_real.crowd_disagreement_score != pytest.approx(
        m_fake.crowd_disagreement_score, abs=0.1), (
        "CDS should differ when public tips change")
