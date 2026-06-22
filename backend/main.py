"""
TippeQpongen FastAPI backend.

Run from the project root:
    uvicorn backend.main:app --reload --port 8000

Streamlit continues to run independently on its own port:
    streamlit run app.py

Both use the same analysis/, db/, data/, models/ modules — no duplication.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from analysis.optimizer import optimize_coupon
from analysis.pool_value import (
    compute_p_win,
    compute_pool_value_ratio,
    compute_value_index,
    simulate_payout,
)
from backend.pipeline import build_matches, parse_coupon_id
from backend.schemas import (
    CdsValidationBucket,
    ConvictionStat,
    CouponDetail,
    CouponListItem,
    CouponMatchRaw,
    CouponShape,
    GenerationAnalytics,
    GenerationDetail,
    GenerationPickResult,
    GenerationSummary,
    HistoryCouponDetail,
    HistoryCouponItem,
    HistoryPickItem,
    MatchEnrichment,
    MatchResult,
    NtComparison,
    OptimizeRequest,
    OptimizeResponse,
    PayoutSimulation,
    RecentMatch,
    StrategyPerformance,
    SyncAccepted,
    SyncStatus,
)
from backend.sync_state import load_state
from data.loader import load_coupons
from db.schema import init_db


# ── App lifespan (scheduler start/stop) ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="TippeQpongen API",
    version="1.0.0",
    description="Norwegian Tipping coupon optimizer — exposes the existing Python model via REST.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# ── Constants ─────────────────────────────────────────────────────────────────

_COVERAGE_TYPE = {1: "single", 2: "half_cover", 3: "full_cover"}
_CONVICTION_PP = 10.0


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


# ── Coupons ───────────────────────────────────────────────────────────────────

@app.get("/v1/coupons", response_model=list[CouponListItem])
def list_coupons(week: int | None = None, year: int | None = None):
    """
    List coupons.

    Without week/year: returns all active (non-expired) coupons, deduplicated by
    NT game day — the canonical view for the frontend.

    With week/year: returns all coupons for that specific week (including expired),
    useful for history and admin contexts.
    """
    if week is None and year is None:
        try:
            from db.coupon import list_active_coupons
            active = list_active_coupons()
            return [
                CouponListItem(
                    coupon_id=c["coupon_id"],
                    label=c["label"],
                    day_type=c.get("day_type"),
                    deadline_utc=c["deadline_utc"],
                    week=c["week"],
                    year=c["year"],
                    n_fixtures=c.get("n_fixtures") or 0,
                )
                for c in active
                if (c.get("n_fixtures") or 0) > 0
            ]
        except Exception:
            pass
        # Fallback to current ISO week
        iso = datetime.now().isocalendar()
        week, year = iso.week, iso.year

    if week is None or year is None:
        iso = datetime.now().isocalendar()
        week = week or iso.week
        year = year or iso.year

    coupons = load_coupons(week=week, year=year)
    if not coupons:
        return []

    db_meta: dict[str, dict] = {}
    try:
        from db.coupon import list_coupons as _db_list
        for row in _db_list(week=week, year=year):
            db_meta[row["coupon_id"]] = row
    except Exception:
        pass

    result: list[CouponListItem] = []
    for key, data in coupons.items():
        coupon_id = f"{key}-{week:02d}-{year}"
        meta = db_meta.get(coupon_id, {})
        result.append(CouponListItem(
            coupon_id=coupon_id,
            label=data["label"],
            day_type=meta.get("day_type"),
            deadline_utc=data["deadline"],
            week=week,
            year=year,
            n_fixtures=len(data["matches"]),
        ))
    return result


def _parse_json_field(raw: str | None) -> dict | None:
    """Deserialise a JSON TEXT column → dict, or None on failure."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _parse_recent_matches(raw: str | None) -> list[RecentMatch] | None:
    """Deserialise a JSON column and normalize opponent names to correct display form."""
    if not raw:
        return None
    try:
        from ingestion.api_football import normalize_opponent_name
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
        normalized = [
            {**m, "opponent_name": normalize_opponent_name(m.get("opponent_name"))}
            for m in data
        ]
        return [RecentMatch(**m) for m in normalized]
    except Exception:
        return None


@app.get("/v1/coupons/{coupon_id}/enrichment", response_model=list[MatchEnrichment])
def get_coupon_enrichment_route(coupon_id: str):
    """
    Return raw API-Football enrichment stats for all fixtures in a coupon.

    Read-only — queries fixture_stat_enrichment via the existing
    get_coupon_enrichment() helper. Does not touch the optimizer or any
    probability calculations.
    """
    try:
        from db.enrichment import get_coupon_enrichment as _get_enrichment
        rows = _get_enrichment(coupon_id)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Coupon '{coupon_id}' not found")
        return [
            MatchEnrichment(
                match_number=r["match_number"],
                fixture_id=r.get("fixture_id"),
                home_team=r.get("home_name") or "",
                away_team=r.get("away_name") or "",
                league_name=r.get("league_name"),
                has_api_football_data=bool(r.get("has_api_football_data")),
                home_position=r.get("home_position"),
                away_position=r.get("away_position"),
                home_last_5=r.get("home_last_5"),
                away_last_5=r.get("away_last_5"),
                home_last_10=r.get("home_last_10"),
                away_last_10=r.get("away_last_10"),
                home_home_record=r.get("home_home_record"),
                away_away_record=r.get("away_away_record"),
                home_goals_for=r.get("home_goals_for"),
                home_goals_against=r.get("home_goals_against"),
                away_goals_for=r.get("away_goals_for"),
                away_goals_against=r.get("away_goals_against"),
                api_prediction_home=r.get("api_prediction_home"),
                api_prediction_draw=r.get("api_prediction_draw"),
                api_prediction_away=r.get("api_prediction_away"),
                api_prediction_advice=r.get("api_prediction_advice"),
                # Phase 10
                home_points=r.get("home_points"),
                away_points=r.get("away_points"),
                home_played=r.get("home_played"),
                away_played=r.get("away_played"),
                home_wins=r.get("home_wins"),
                home_draws=r.get("home_draws"),
                home_losses=r.get("home_losses"),
                away_wins=r.get("away_wins"),
                away_draws=r.get("away_draws"),
                away_losses=r.get("away_losses"),
                home_logo_url=r.get("home_logo_url"),
                away_logo_url=r.get("away_logo_url"),
                home_avg_goals_for=r.get("home_avg_goals_for"),
                away_avg_goals_for=r.get("away_avg_goals_for"),
                home_avg_goals_against=r.get("home_avg_goals_against"),
                away_avg_goals_against=r.get("away_avg_goals_against"),
                home_clean_sheets=r.get("home_clean_sheets"),
                away_clean_sheets=r.get("away_clean_sheets"),
                home_streak_wins=r.get("home_streak_wins"),
                away_streak_wins=r.get("away_streak_wins"),
                home_streak_draws=r.get("home_streak_draws"),
                away_streak_draws=r.get("away_streak_draws"),
                home_streak_losses=r.get("home_streak_losses"),
                away_streak_losses=r.get("away_streak_losses"),
                api_comparison_att_home=r.get("api_comparison_att_home"),
                api_comparison_att_away=r.get("api_comparison_att_away"),
                api_comparison_def_home=r.get("api_comparison_def_home"),
                api_comparison_def_away=r.get("api_comparison_def_away"),
                api_comparison_form_home=r.get("api_comparison_form_home"),
                api_comparison_form_away=r.get("api_comparison_form_away"),
                api_comparison_total_home=r.get("api_comparison_total_home"),
                api_comparison_total_away=r.get("api_comparison_total_away"),
                # Phase 11
                home_recent_matches=_parse_recent_matches(r.get("home_recent_matches")),
                away_recent_matches=_parse_recent_matches(r.get("away_recent_matches")),
                # Phase 12
                home_recent_fixture_stats=_parse_json_field(r.get("home_recent_fixture_stats")),
                away_recent_fixture_stats=_parse_json_field(r.get("away_recent_fixture_stats")),
                # Phase 13
                league_size=r.get("league_size"),
                home_avg_goals_for_home=r.get("home_avg_goals_for_home"),
                home_avg_goals_against_home=r.get("home_avg_goals_against_home"),
                away_avg_goals_for_away=r.get("away_avg_goals_for_away"),
                away_avg_goals_against_away=r.get("away_avg_goals_against_away"),
                home_clean_sheets_home=r.get("home_clean_sheets_home"),
                away_clean_sheets_away=r.get("away_clean_sheets_away"),
            )
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/coupons/{coupon_id}", response_model=CouponDetail)
def get_coupon(coupon_id: str):
    """Return raw fixture data for a coupon (no model processing)."""
    coupon_key, week, year = parse_coupon_id(coupon_id)

    try:
        from db.coupon import get_coupon_matches, list_coupons as _db_list
        rows = get_coupon_matches(coupon_id)
        if rows:
            db_rows = _db_list(week=week, year=year)
            meta = next((c for c in db_rows if c["coupon_id"] == coupon_id), {})
            matches = [
                CouponMatchRaw(
                    match_number=r["match_number"],
                    home_team=r["home_name"],
                    away_team=r["away_name"],
                    odds_h=r.get("odds_h"),
                    odds_u=r.get("odds_u"),
                    odds_b=r.get("odds_b"),
                    odds_source=r.get("source"),
                    expert_h=r.get("expert_h"),
                    expert_u=r.get("expert_u"),
                    expert_b=r.get("expert_b"),
                    public_h=r.get("public_h"),
                    public_u=r.get("public_u"),
                    public_b=r.get("public_b"),
                    fixture_id=r.get("fixture_id"),
                    kickoff_utc=r.get("kickoff_utc"),
                )
                for r in rows
            ]
            return CouponDetail(
                coupon_id=coupon_id,
                label=meta.get("label", coupon_id),
                deadline_utc=meta.get("deadline_utc", ""),
                week=week,
                year=year,
                matches=matches,
            )
    except Exception:
        pass

    coupons = load_coupons(week=week, year=year)
    if coupon_key not in coupons:
        raise HTTPException(status_code=404, detail=f"Coupon '{coupon_id}' not found")

    data = coupons[coupon_key]
    matches = [
        CouponMatchRaw(
            match_number=i,
            home_team=row[0],
            away_team=row[1],
            odds_h=float(row[2]) if len(row) > 2 else None,
            odds_u=float(row[3]) if len(row) > 3 else None,
            odds_b=float(row[4]) if len(row) > 4 else None,
            odds_source=row[5] if len(row) > 5 else None,
            expert_h=None, expert_u=None, expert_b=None,
            public_h=None, public_u=None, public_b=None,
            fixture_id=None, kickoff_utc=None,
        )
        for i, row in enumerate(data["matches"], 1)
    ]
    return CouponDetail(
        coupon_id=coupon_id,
        label=data["label"],
        deadline_utc=data["deadline"],
        week=week,
        year=year,
        matches=matches,
    )


# ── Optimize ──────────────────────────────────────────────────────────────────

@app.post("/v1/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    """
    Run the full model + optimizer pipeline and return picks with analytics.

    Calls the identical pipeline that Streamlit uses:
        build_matches() → optimize_coupon() → compute_p_win() → compute_pool_value_ratio()

    Optional: pass omsetning to include a Monte Carlo payout simulation.
    """
    try:
        matches = build_matches(req.coupon_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    picks, total_rows = optimize_coupon(
        matches,
        req.budget,
        cost_per_row=req.cost_per_row,
        strategy=req.strategy,
    )

    p_win = compute_p_win(matches, picks)
    pvr = compute_pool_value_ratio(matches, picks)
    total_cost = total_rows * req.cost_per_row

    n_singles  = sum(1 for m in matches if len(picks[m.number]) == 1)
    n_halvdekk = sum(1 for m in matches if len(picks[m.number]) == 2)
    n_heldekk  = sum(1 for m in matches if len(picks[m.number]) == 3)

    match_results: list[MatchResult] = []
    for m in matches:
        m_picks = picks[m.number]
        rec = m.recommendation or ""

        val_rec = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        is_conviction = (
            m.has_public_tips
            and val_rec is not None
            and abs(val_rec) >= _CONVICTION_PP
        )

        prob_rec = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec, 0.0)
        pub_rec  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec)
        vi = compute_value_index(prob_rec, pub_rec)

        match_results.append(MatchResult(
            match_number=m.number,
            home_team=m.home_team,
            away_team=m.away_team,
            picks=m_picks,
            coverage_type=_COVERAGE_TYPE[len(m_picks)],
            recommendation=rec,
            odds_h=m.odds_h,
            odds_u=m.odds_u,
            odds_b=m.odds_b,
            odds_source=m.odds_source,
            prob_h=m.prob_h,
            prob_u=m.prob_u,
            prob_b=m.prob_b,
            confidence=m.confidence,
            classification=m.classification,
            bm_prob_h=m.bm_prob_h,
            bm_prob_u=m.bm_prob_u,
            bm_prob_b=m.bm_prob_b,
            home_edge=m.home_edge,
            stats_adj_pp=m.stats_adj_pp,
            stats_signals=m.stats_signals or [],
            has_af_data=m.has_af_data,
            pub_prob_h=m.pub_prob_h,
            pub_prob_u=m.pub_prob_u,
            pub_prob_b=m.pub_prob_b,
            has_public_tips=m.has_public_tips,
            value_h=m.value_h,
            value_u=m.value_u,
            value_b=m.value_b,
            crowd_disagreement_score=m.crowd_disagreement_score,
            crowd_pressure_pick=m.crowd_pressure_pick,
            vi=vi,
            is_conviction=is_conviction,
            data_coverage=len(m.stats_signals or []),
        ))

    payout: PayoutSimulation | None = None
    if req.omsetning and req.omsetning > 0:
        sim = simulate_payout(
            matches, picks, total_rows, req.omsetning,
            cost_per_row=req.cost_per_row,
        )
        if sim.get("n_winning_sims", 0) > 0:
            payout = PayoutSimulation(**sim)

    # Phase 9 — auto-save this generation (fire-and-forget, never fails the request)
    try:
        from collections import Counter
        from db.generation import upsert_generation
        cov_dist = dict(Counter(len(m.stats_signals or []) for m in matches))
        upsert_generation(
            coupon_id=req.coupon_id,
            strategy=req.strategy,
            budget=req.budget,
            row_count=total_rows,
            p_win=p_win,
            pvr=pvr,
            n_singles=n_singles,
            n_halvdekk=n_halvdekk,
            n_heldekk=n_heldekk,
            coverage_dist=cov_dist,
            picks_data=[
                {
                    "fixture_id": m.fixture_id,
                    "match_number": m.number,
                    "pick": m.recommendation or "",
                    "coverage_type": _COVERAGE_TYPE[len(picks[m.number])],
                    "selected_outcomes": picks[m.number],
                    "confidence": m.confidence,
                    "model_prob_h": m.prob_h,
                    "model_prob_u": m.prob_u,
                    "model_prob_b": m.prob_b,
                    "pub_prob_h": m.pub_prob_h,
                    "pub_prob_u": m.pub_prob_u,
                    "pub_prob_b": m.pub_prob_b,
                    "value_h": m.value_h,
                    "value_u": m.value_u,
                    "value_b": m.value_b,
                    "crowd_disagreement_score": m.crowd_disagreement_score,
                    "odds_source": m.odds_source,
                    "has_af_data": m.has_af_data,
                }
                for m in matches
            ],
        )
    except Exception:
        pass

    return OptimizeResponse(
        coupon_id=req.coupon_id,
        strategy=req.strategy,
        budget=req.budget,
        cost_per_row=req.cost_per_row,
        total_rows=total_rows,
        total_cost=total_cost,
        p_win=p_win,
        pvr=pvr,
        shape=CouponShape(
            n_singles=n_singles,
            n_halvdekk=n_halvdekk,
            n_heldekk=n_heldekk,
        ),
        matches=match_results,
        payout=payout,
    )


# ── Sync endpoints ────────────────────────────────────────────────────────────

@app.get("/v1/sync/status", response_model=SyncStatus)
def sync_status():
    """Return the current sync state (timestamps, running flag, changes)."""
    state = load_state()
    return SyncStatus(
        last_nt_refresh_at=state.get("last_nt_refresh_at"),
        last_odds_refresh_at=state.get("last_odds_refresh_at"),
        last_full_sync_at=state.get("last_full_sync_at"),
        is_running=bool(state.get("is_running")),
        current_job=state.get("current_job"),
        last_success=state.get("last_success"),
        last_error=state.get("last_error"),
        next_nt_refresh_at=state.get("next_nt_refresh_at"),
        next_odds_refresh_at=state.get("next_odds_refresh_at"),
        updated_coupon_ids=state.get("updated_coupon_ids") or [],
        n_public_pct_changes=state.get("n_public_pct_changes") or 0,
        turnover=state.get("turnover") or {},
        last_freeze_at=state.get("last_freeze_at"),
        last_freeze_count=state.get("last_freeze_count") or 0,
        last_freeze_coupon_ids=state.get("last_freeze_coupon_ids") or [],
    )


@app.post("/v1/sync/refresh-coupons", response_model=SyncAccepted)
def sync_refresh_coupons(background_tasks: BackgroundTasks):
    """Trigger an immediate NT coupon refresh (public %, turnover)."""
    state = load_state()
    if state.get("is_running"):
        raise HTTPException(status_code=409, detail="A sync job is already running")
    from backend.scheduler import do_nt_refresh
    background_tasks.add_task(do_nt_refresh, force=True)
    return SyncAccepted(accepted=True, message="NT refresh started in background")


@app.post("/v1/sync/daily", response_model=SyncAccepted)
def sync_daily(background_tasks: BackgroundTasks):
    """Trigger a full daily sync (NT + Pinnacle odds + enrichment)."""
    state = load_state()
    if state.get("is_running"):
        raise HTTPException(status_code=409, detail="A sync job is already running")
    from backend.scheduler import do_daily_sync
    background_tasks.add_task(do_daily_sync, force=True)
    return SyncAccepted(accepted=True, message="Daily sync started in background")


# ── History ───────────────────────────────────────────────────────────────────

@app.get("/v1/history", response_model=list[HistoryCouponItem])
def list_history():
    """All coupons with saved predictions (evaluated or pending), newest first."""
    from db.evaluation import list_history_coupons
    return [HistoryCouponItem(**r) for r in list_history_coupons()]


@app.get("/v1/history/strategy-performance", response_model=list[StrategyPerformance])
def history_strategy_performance():
    """Aggregate performance metrics per strategy across all evaluated coupons."""
    from db.evaluation import get_strategy_performance
    return [StrategyPerformance(**r) for r in get_strategy_performance()]


@app.get("/v1/history/cds-validation", response_model=list[CdsValidationBucket])
def history_cds_validation():
    """Model vs NT accuracy split by CDS bucket (Phase 8+ coupons only)."""
    from db.evaluation import get_cds_validation
    return [CdsValidationBucket(**r) for r in get_cds_validation()]


@app.get("/v1/history/conviction-stats", response_model=list[ConvictionStat])
def history_conviction_stats():
    """Hit rate and cover rate by is_conviction flag and coverage type."""
    from db.evaluation import get_conviction_stats
    return [ConvictionStat(**r) for r in get_conviction_stats()]


@app.get("/v1/history/nt-comparison", response_model=NtComparison | None)
def history_nt_comparison():
    """Overall model vs NT public accuracy (None when insufficient data)."""
    from db.evaluation import get_nt_model_comparison
    data = get_nt_model_comparison()
    if not data or not data.get("n_total"):
        return None
    return NtComparison(**data)


@app.get("/v1/history/{coupon_id}", response_model=HistoryCouponDetail)
def get_history_coupon(coupon_id: str):
    """Metadata + per-pick breakdown for one saved coupon."""
    from db.evaluation import list_history_coupons, get_history_coupon_picks
    rows = list_history_coupons()
    meta = next((r for r in rows if r["coupon_id"] == coupon_id), None)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Coupon '{coupon_id}' not found in history")
    picks = [HistoryPickItem(**p) for p in get_history_coupon_picks(coupon_id)]
    return HistoryCouponDetail(**{**meta, "picks": picks})


@app.get("/v1/analytics/strategy", response_model=list[GenerationAnalytics])
def analytics_strategy():
    """Per-strategy statistics over frozen/evaluated generations (Phase 9)."""
    from db.generation import get_strategy_analytics
    return [GenerationAnalytics(**r) for r in get_strategy_analytics()]


@app.get("/v1/analytics/generations", response_model=list[GenerationSummary])
def analytics_generations():
    """All frozen/evaluated generations with coupon metadata and result summary."""
    from db.generation import get_all_generations_summary
    return [GenerationSummary(**r) for r in get_all_generations_summary()]


@app.get("/v1/analytics/generations/{generation_id}", response_model=GenerationDetail)
def analytics_generation_detail(generation_id: str):
    """Full generation: metadata + all 12 picks with team names and actual results."""
    from db.generation import get_generation_detail
    data = get_generation_detail(generation_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Generation '{generation_id}' not found")
    picks = [GenerationPickResult(**p) for p in data.pop("picks", [])]
    return GenerationDetail(**data, picks=picks)


@app.post("/v1/history/freeze-active")
def freeze_active_coupons_endpoint():
    """
    Freeze all active coupons for all 12 strategy×budget combinations.

    Idempotent — already-frozen records are left unchanged. Use for manual
    testing or to force a freeze outside the automatic 120-min window.
    """
    from backend.freeze import freeze_active_coupons
    results = freeze_active_coupons(force=True)
    n_created  = sum(1 for r in results if r.get("action") == "created")
    n_upgraded = sum(1 for r in results if r.get("action") == "upgraded")
    n_already  = sum(1 for r in results if r.get("action") == "already_frozen")
    n_errors   = sum(1 for r in results if r.get("error"))
    return {
        "n_frozen":         n_created + n_upgraded,
        "n_created":        n_created,
        "n_upgraded":       n_upgraded,
        "n_already_frozen": n_already,
        "n_errors":         n_errors,
        "results":          results,
    }


@app.post("/v1/sync/full", response_model=SyncAccepted)
def sync_full(background_tasks: BackgroundTasks):
    """Alias for daily sync (NT + odds + enrichment + estimated priors)."""
    state = load_state()
    if state.get("is_running"):
        raise HTTPException(status_code=409, detail="A sync job is already running")
    from backend.scheduler import do_daily_sync
    background_tasks.add_task(do_daily_sync, force=True)
    return SyncAccepted(accepted=True, message="Full sync started in background")
