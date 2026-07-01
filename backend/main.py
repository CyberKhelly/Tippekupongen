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
    BankrollPoint,
    BetSummary,
    CdsValidationBucket,
    ConvictionStat,
    CouponDetail,
    CouponListItem,
    CouponMatchRaw,
    CouponShape,
    GenerateBetsResponse,
    GenerationAnalytics,
    GenerationDetail,
    GenerationPickResult,
    GenerationSummary,
    HistoryCouponDetail,
    HistoryCouponItem,
    HistoryPickItem,
    InsightSignal,
    InsightsResponse,
    MatchEnrichment,
    MatchResult,
    MatchSignal,
    NtComparison,
    OddsMovement,
    OptimizeRequest,
    OptimizeResponse,
    PaperBet,
    PayoutSimulation,
    RecentMatch,
    SignalBoardResponse,
    ScanResponse,
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


# ── Signal board ──────────────────────────────────────────────────────────────

@app.get("/v1/signals", response_model=SignalBoardResponse)
def get_signal_board(coupon_id: str | None = None):
    """
    All matches for the active coupon, ranked by signal strength.

    Signal strength = max(0, edge_pp) × (1 + CDS/100).
    Runs the model pipeline only — no optimizer.
    """
    from db.coupon import list_active_coupons, get_coupon_matches

    # Resolve coupon + metadata
    resolved_id = coupon_id
    coupon_label = ""
    deadline_utc = ""
    week = 0
    year = 0

    if resolved_id is None:
        try:
            active = list_active_coupons()
            if active:
                c = active[0]
                resolved_id   = c["coupon_id"]
                coupon_label  = c.get("label", "")
                deadline_utc  = c.get("deadline_utc", "")
                week          = c.get("week", 0)
                year          = c.get("year", 0)
        except Exception:
            pass

    if resolved_id is None:
        raise HTTPException(status_code=404, detail="No active coupon found")

    if not coupon_label:
        _key, week, year = parse_coupon_id(resolved_id)
        try:
            from db.coupon import list_coupons as _db_list
            for c in _db_list(week=week, year=year):
                if c["coupon_id"] == resolved_id:
                    coupon_label = c.get("label", resolved_id)
                    deadline_utc = c.get("deadline_utc", "")
                    break
        except Exception:
            coupon_label = resolved_id

    # Kickoff times from DB
    kickoff_map: dict[int, str | None] = {}
    try:
        for r in get_coupon_matches(resolved_id):
            kickoff_map[r["match_number"]] = r.get("kickoff_utc")
    except Exception:
        pass

    # League names + logos from enrichment
    league_map: dict[int, str | None] = {}
    logo_map: dict[int, dict] = {}
    try:
        from db.enrichment import get_coupon_enrichment as _get_enr
        for r in _get_enr(resolved_id):
            league_map[r["match_number"]] = r.get("league_name")
            logo_map[r["match_number"]] = {
                "home": r.get("home_logo_url"),
                "away": r.get("away_logo_url"),
            }
    except Exception:
        pass

    # Model pipeline (no optimizer)
    try:
        matches = build_matches(resolved_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Coupon '{resolved_id}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    signals: list[MatchSignal] = []
    for m in matches:
        probs = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}
        rec = max(probs, key=lambda k: probs[k])  # argmax
        model_prob = probs[rec]

        pub_prob_map = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}
        pub_prob = pub_prob_map[rec]

        edge_pp = round((model_prob - pub_prob) * 100, 1) if pub_prob is not None else None

        values = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
        value_index = values[rec]

        # Ranking: positive edge boosted by CDS; matches without public data rank last
        if edge_pp is not None:
            cds_boost = 1.0 + (m.crowd_disagreement_score or 0.0) / 100.0
            strength = max(0.0, edge_pp) * cds_boost
        elif m.crowd_disagreement_score is not None:
            strength = m.crowd_disagreement_score * 0.1
        else:
            strength = 0.0

        signals.append(MatchSignal(
            match_number=m.number,
            home_team=m.home_team,
            away_team=m.away_team,
            fixture_id=m.fixture_id,
            league_name=league_map.get(m.number),
            kickoff_utc=kickoff_map.get(m.number),
            recommended_pick=rec,
            model_prob=round(model_prob * 100, 1),
            pub_prob=round(pub_prob * 100, 1) if pub_prob is not None else None,
            edge_pp=edge_pp,
            crowd_disagreement_score=m.crowd_disagreement_score,
            value_index=round(value_index, 3) if value_index is not None else None,
            signal_strength=round(strength, 3),
            has_public_tips=m.has_public_tips,
            prob_h=round(m.prob_h * 100, 1),
            prob_u=round(m.prob_u * 100, 1),
            prob_b=round(m.prob_b * 100, 1),
            pub_prob_h=round(m.pub_prob_h * 100, 1) if m.pub_prob_h is not None else None,
            pub_prob_u=round(m.pub_prob_u * 100, 1) if m.pub_prob_u is not None else None,
            pub_prob_b=round(m.pub_prob_b * 100, 1) if m.pub_prob_b is not None else None,
            stats_signals=m.stats_signals,
            classification=m.classification,
            home_logo_url=logo_map.get(m.number, {}).get("home"),
            away_logo_url=logo_map.get(m.number, {}).get("away"),
        ))

    signals.sort(key=lambda s: s.signal_strength, reverse=True)

    return SignalBoardResponse(
        coupon_id=resolved_id,
        coupon_label=coupon_label,
        deadline_utc=deadline_utc,
        week=week,
        year=year,
        signals=signals,
    )


@app.get("/v1/insights", response_model=InsightsResponse)
def get_insights(coupon_id: str | None = None):
    """
    Active coupon matches enriched with bookmaker odds and Pinnacle snapshot
    data. The frontend derives insight types (value bet, crowd trap, etc.)
    from this payload via deriveOddstips().
    """
    from db.coupon import list_active_coupons, get_coupon_matches
    from db.odds_movement import _devig, get_opening_snapshot, get_latest_snapshot, get_snapshots_for_fixture
    from db.connection import get_conn

    # ── Resolve coupon ────────────────────────────────────────────────────────
    resolved_id = coupon_id
    coupon_label = ""
    deadline_utc = ""
    week = 0
    year = 0

    if resolved_id is None:
        try:
            active = list_active_coupons()
            if active:
                c = active[0]
                resolved_id  = c["coupon_id"]
                coupon_label = c.get("label", "")
                deadline_utc = c.get("deadline_utc", "")
                week         = c.get("week", 0)
                year         = c.get("year", 0)
        except Exception:
            pass

    if resolved_id is None:
        raise HTTPException(status_code=404, detail="No active coupon found")

    if not coupon_label:
        _key, week, year = parse_coupon_id(resolved_id)
        try:
            from db.coupon import list_coupons as _db_list
            for c in _db_list(week=week, year=year):
                if c["coupon_id"] == resolved_id:
                    coupon_label = c.get("label", resolved_id)
                    deadline_utc = c.get("deadline_utc", "")
                    break
        except Exception:
            coupon_label = resolved_id

    # ── Ancillary maps ────────────────────────────────────────────────────────
    kickoff_map: dict[int, str | None] = {}
    fixture_id_map: dict[int, str | None] = {}
    try:
        for r in get_coupon_matches(resolved_id):
            kickoff_map[r["match_number"]] = r.get("kickoff_utc")
            fixture_id_map[r["match_number"]] = r.get("fixture_id")
    except Exception:
        pass

    league_map: dict[int, str | None] = {}
    enrichment_map: dict[int, dict] = {}
    try:
        from db.enrichment import get_coupon_enrichment as _get_enr
        for r in _get_enr(resolved_id):
            league_map[r["match_number"]] = r.get("league_name")
            enrichment_map[r["match_number"]] = dict(r)
    except Exception:
        pass

    # ── Multi-market odds (BTTS, O/U) from odds_markets table ────────────────
    # New row-per-selection schema: one row per (fixture_id, market_key, selection).
    # mkt_odds_map: fixture_id → market_key → {selection: odds, "bookmaker": str}
    mkt_odds_map: dict[str, dict[str, dict]] = {}
    try:
        with get_conn() as conn:
            mkt_rows = conn.execute(
                """SELECT om.fixture_id, om.market_key, om.selection, om.odds, om.bookmaker
                   FROM odds_markets om
                   JOIN coupon_fixtures cf ON cf.fixture_id = om.fixture_id
                   WHERE cf.coupon_id = ?
                   ORDER BY om.updated_at DESC""",
                (resolved_id,),
            ).fetchall()
        for r in mkt_rows:
            fid = r["fixture_id"]
            mk  = r["market_key"]
            sel = r["selection"]
            if fid not in mkt_odds_map:
                mkt_odds_map[fid] = {}
            if mk not in mkt_odds_map[fid]:
                mkt_odds_map[fid][mk] = {"bookmaker": r["bookmaker"]}
            mkt_odds_map[fid][mk][sel] = r["odds"]
    except Exception:
        pass

    # ── Odds per fixture (latest row, prefer pinnacle > api_football) ─────────
    odds_map: dict[str, dict] = {}
    try:
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT o.fixture_id, o.odds_h, o.odds_u, o.odds_b, o.source
                   FROM odds o
                   JOIN coupon_fixtures cf ON cf.fixture_id = o.fixture_id
                   WHERE cf.coupon_id = ?
                   ORDER BY
                     CASE o.source
                       WHEN 'pinnacle' THEN 1
                       WHEN 'betsson'  THEN 2
                       ELSE 3
                     END,
                     o.fetched_at DESC""",
                (resolved_id,),
            ).fetchall()
        for r in rows:
            fid = r["fixture_id"]
            if fid not in odds_map:
                odds_map[fid] = dict(r)
    except Exception:
        pass

    # ── Odds movement (Pinnacle snapshots, ≥2 required) ──────────────────────
    movement_map: dict[str, OddsMovement] = {}
    try:
        with get_conn() as conn:
            snap_fids = [
                r[0] for r in conn.execute(
                    """SELECT DISTINCT s.fixture_id
                       FROM odds_snapshots s
                       JOIN coupon_fixtures cf ON cf.fixture_id = s.fixture_id
                       WHERE cf.coupon_id = ? AND s.bookmaker = 'pinnacle'""",
                    (resolved_id,),
                ).fetchall()
            ]
        for fid in snap_fids:
            opening = get_opening_snapshot(fid)
            latest  = get_latest_snapshot(fid)
            n       = len(get_snapshots_for_fixture(fid))
            if opening and latest and n >= 2:
                diff_h = latest["odds_h"] - opening["odds_h"]
                if abs(diff_h) < 0.05:
                    direction = "stable"
                elif diff_h < 0:
                    direction = "steaming"
                else:
                    direction = "drifting"
                movement_map[fid] = OddsMovement(
                    open_h=opening["odds_h"],
                    open_u=opening["odds_u"],
                    open_b=opening["odds_b"],
                    current_h=latest["odds_h"],
                    current_u=latest["odds_u"],
                    current_b=latest["odds_b"],
                    n_snapshots=n,
                    direction=direction,
                    bookmaker="Pinnacle",
                )
    except Exception:
        pass

    # ── AF predictions + fixture links ────────────────────────────────────────
    # pred_map:  fixture_id → prediction row dict
    # link_map:  fixture_id → {af_home_team_id, af_away_team_id}
    pred_map: dict[str, dict] = {}
    link_map: dict[str, dict] = {}
    try:
        with get_conn() as conn:
            pred_rows = conn.execute(
                """SELECT p.fixture_id, p.af_fixture_id,
                          p.prediction_winner_id, p.prediction_winner_name,
                          p.prediction_winner_comment, p.prediction_win_or_draw,
                          p.prediction_under_over, p.prediction_goals_home,
                          p.prediction_goals_away, p.advice,
                          p.comparison_json,
                          lnk.api_football_home_team_id, lnk.api_football_away_team_id
                   FROM api_football_predictions p
                   JOIN coupon_fixtures cf ON cf.fixture_id = p.fixture_id
                   LEFT JOIN api_football_fixture_links lnk ON lnk.fixture_id = p.fixture_id
                   WHERE cf.coupon_id = ?""",
                (resolved_id,),
            ).fetchall()
        for r in pred_rows:
            fid = r["fixture_id"]
            pred_map[fid] = dict(r)
            link_map[fid] = {
                "af_home_team_id": r["api_football_home_team_id"],
                "af_away_team_id": r["api_football_away_team_id"],
            }
    except Exception:
        pass

    # ── Model pipeline ────────────────────────────────────────────────────────
    try:
        matches = build_matches(resolved_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Coupon '{resolved_id}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    from analysis.market_models import market_probs_from_enrichment
    from ingestion.api_football_predictions import compute_confidence_score

    insight_signals: list[InsightSignal] = []
    for m in matches:
        probs = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}
        rec   = max(probs, key=lambda k: probs[k])
        model_prob = probs[rec]

        pub_prob_map = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}
        pub_prob = pub_prob_map[rec]
        edge_pp  = round((model_prob - pub_prob) * 100, 1) if pub_prob is not None else None

        values      = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
        value_index = values[rec]

        fid      = m.fixture_id
        odds_row = odds_map.get(fid, {}) if fid else {}
        odds_h   = odds_row.get("odds_h")
        odds_u   = odds_row.get("odds_u")
        odds_b   = odds_row.get("odds_b")
        odds_src = odds_row.get("source")

        ih_val = iu_val = ib_val = None
        implied_prob = None
        market_edge_pp = None
        if odds_h and odds_u and odds_b:
            try:
                ih_val, iu_val, ib_val = _devig(odds_h, odds_u, odds_b)
                implied_map = {"H": ih_val, "U": iu_val, "B": ib_val}
                implied_prob = round(implied_map[rec] * 100, 1)
                market_edge_pp = round(model_prob * 100 - implied_prob, 1)
            except Exception:
                pass

        movement = movement_map.get(fid) if fid else None

        # ── Poisson BTTS / O/U probabilities ─────────────────────────────────
        enr = enrichment_map.get(m.number, {})
        poisson = market_probs_from_enrichment(enr)

        # BTTS bookmaker odds from odds_markets (row-per-selection schema)
        btts_yes_odds = btts_no_odds = btts_bkm = btts_implied_yes = btts_mep = None
        if fid and fid in mkt_odds_map:
            btts_mkt = mkt_odds_map[fid].get("BTTS", {})
            _ba = btts_mkt.get("YES")
            _bb = btts_mkt.get("NO")
            if _ba and _bb and _ba > 1 and _bb > 1:
                btts_yes_odds = _ba
                btts_no_odds  = _bb
                btts_bkm      = btts_mkt.get("bookmaker")
                try:
                    total = 1 / _ba + 1 / _bb
                    btts_implied_yes = round((1 / _ba / total) * 100, 1)
                    btts_mep = round(poisson["btts_yes"] * 100 - btts_implied_yes, 1)
                except Exception:
                    pass

        # O/U bookmaker odds from odds_markets (row-per-selection schema)
        over_25_odds = under_25_odds = ou_bkm = over_implied = over_mep = None
        if fid and fid in mkt_odds_map:
            ou_mkt = mkt_odds_map[fid].get("OVER_UNDER", {})
            _oa = ou_mkt.get("OVER")
            _ob = ou_mkt.get("UNDER")
            if _oa and _ob and _oa > 1 and _ob > 1:
                over_25_odds  = _oa
                under_25_odds = _ob
                ou_bkm        = ou_mkt.get("bookmaker")
                try:
                    total = 1 / _oa + 1 / _ob
                    over_implied = round((1 / _oa / total) * 100, 1)
                    over_mep = round(poisson["over_2_5"] * 100 - over_implied, 1)
                except Exception:
                    pass

        # ── AF prediction signals ─────────────────────────────────────────────
        af_pred = pred_map.get(fid) if fid else None
        af_link = link_map.get(fid) if fid else None

        af_winner_name = af_winner_pick = af_winner_agrees = af_win_or_draw = None
        af_under_over  = af_advice = af_poisson_home = af_poisson_away = None
        af_goals_home  = af_goals_away = af_ou_agrees = None

        if af_pred:
            af_winner_name    = af_pred.get("prediction_winner_name")
            af_win_or_draw    = bool(af_pred.get("prediction_win_or_draw"))
            af_advice         = af_pred.get("advice")
            af_winner_id      = af_pred.get("prediction_winner_id")

            # Parse under_over
            uo_raw = af_pred.get("prediction_under_over")
            if uo_raw is not None:
                try:
                    af_under_over = float(str(uo_raw))
                except (ValueError, TypeError):
                    pass

            # Parse comparison.poisson_distribution and comparison.goals
            try:
                comp = json.loads(af_pred.get("comparison_json") or "{}")
                pois = comp.get("poisson_distribution", {})
                if pois.get("home") is not None:
                    try:
                        af_poisson_home = float(str(pois["home"]).rstrip("%"))
                    except (ValueError, TypeError):
                        pass
                if pois.get("away") is not None:
                    try:
                        af_poisson_away = float(str(pois["away"]).rstrip("%"))
                    except (ValueError, TypeError):
                        pass
                goals_comp = comp.get("goals", {})
                if goals_comp.get("home") is not None:
                    try:
                        af_goals_home = float(str(goals_comp["home"]).rstrip("%"))
                    except (ValueError, TypeError):
                        pass
                if goals_comp.get("away") is not None:
                    try:
                        af_goals_away = float(str(goals_comp["away"]).rstrip("%"))
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass

            # Determine AF winner pick (H/U/B) from team IDs
            if af_link and af_winner_id is not None:
                if af_winner_id == af_link.get("af_home_team_id"):
                    af_winner_pick = "H"
                elif af_winner_id == af_link.get("af_away_team_id"):
                    af_winner_pick = "B"
            if af_winner_id is None and af_winner_name is None:
                af_winner_pick = "U"   # draw

            # Determine agreement with our model
            if af_winner_pick is not None:
                if af_win_or_draw:
                    af_winner_agrees = rec in (af_winner_pick, "U")
                else:
                    af_winner_agrees = rec == af_winner_pick

            # O/U alignment with our Poisson model
            if af_under_over is not None and poisson["has_data"]:
                our_over_model = poisson["over_2_5"]   # probability 0–1
                af_says_over = af_under_over > 0
                we_say_over  = our_over_model > 0.5
                af_ou_agrees = af_says_over == we_say_over

        # ── Confidence score ──────────────────────────────────────────────────
        confidence_score = compute_confidence_score(
            market_edge_pp=market_edge_pp,
            af_agrees=af_winner_agrees,
            af_has_data=af_pred is not None,
            odds_movement_direction=movement.direction if movement else None,
            has_bookmaker_odds=bool(odds_h),
            has_odds_movement=movement is not None,
            af_poisson_home_pct=af_poisson_home,
            is_home_pick=rec == "H",
        )

        insight_signals.append(InsightSignal(
            match_number=m.number,
            home_team=m.home_team,
            away_team=m.away_team,
            fixture_id=fid,
            league_name=league_map.get(m.number),
            kickoff_utc=kickoff_map.get(m.number),
            recommended_pick=rec,
            prob_h=round(m.prob_h * 100, 1),
            prob_u=round(m.prob_u * 100, 1),
            prob_b=round(m.prob_b * 100, 1),
            model_prob=round(model_prob * 100, 1),
            pub_prob_h=round(m.pub_prob_h * 100, 1) if m.pub_prob_h is not None else None,
            pub_prob_u=round(m.pub_prob_u * 100, 1) if m.pub_prob_u is not None else None,
            pub_prob_b=round(m.pub_prob_b * 100, 1) if m.pub_prob_b is not None else None,
            pub_prob=round(pub_prob * 100, 1) if pub_prob is not None else None,
            has_public_tips=m.has_public_tips,
            edge_pp=edge_pp,
            crowd_disagreement_score=m.crowd_disagreement_score,
            value_index=round(value_index, 3) if value_index is not None else None,
            odds_h=odds_h,
            odds_u=odds_u,
            odds_b=odds_b,
            odds_source=odds_src,
            implied_prob=implied_prob,
            market_edge_pp=market_edge_pp,
            odds_movement=movement,
            # Poisson
            btts_model_prob=round(poisson["btts_yes"] * 100, 1) if poisson["has_data"] else None,
            over_model_prob=round(poisson["over_2_5"] * 100, 1) if poisson["has_data"] else None,
            under_model_prob=round(poisson["under_2_5"] * 100, 1) if poisson["has_data"] else None,
            xg_home=poisson["xg_home"] if poisson["has_data"] else None,
            xg_away=poisson["xg_away"] if poisson["has_data"] else None,
            btts_yes_odds=btts_yes_odds,
            btts_no_odds=btts_no_odds,
            btts_bookmaker=btts_bkm,
            btts_implied_yes=btts_implied_yes,
            btts_market_edge_pp=btts_mep,
            over_25_odds=over_25_odds,
            under_25_odds=under_25_odds,
            ou_bookmaker=ou_bkm,
            over_implied=over_implied,
            over_market_edge_pp=over_mep,
            # AF predictions
            af_winner_name=af_winner_name,
            af_winner_pick=af_winner_pick,
            af_winner_agrees=af_winner_agrees,
            af_win_or_draw=af_win_or_draw,
            af_under_over=af_under_over,
            af_advice=af_advice,
            af_poisson_home=af_poisson_home,
            af_poisson_away=af_poisson_away,
            af_goals_home=af_goals_home,
            af_goals_away=af_goals_away,
            af_ou_agrees=af_ou_agrees,
            confidence_score=confidence_score,
        ))

    return InsightsResponse(
        coupon_id=resolved_id,
        coupon_label=coupon_label,
        deadline_utc=deadline_utc,
        week=week,
        year=year,
        signals=insight_signals,
    )


# ── /v1/bets/* — Modellspill (paper bets) ─────────────────────────────────────

def _bet_to_schema(b: dict) -> PaperBet:
    return PaperBet(
        id=b["id"],
        coupon_id=b.get("coupon_id"),
        fixture_id=b["fixture_id"],
        match_name=b["match_name"],
        league=b.get("league"),
        kickoff_utc=b.get("kickoff_utc"),
        market=b["market"],
        outcome=b["outcome"],
        bookmaker=b["bookmaker"],
        ref_odds=b["ref_odds"],
        implied_prob=b["implied_prob"],
        model_prob=b["model_prob"],
        edge_pp=b["edge_pp"],
        stake_nok=b["stake_nok"],
        expected_value=b["expected_value"],
        insight_type=b.get("insight_type"),
        risk_level=b["risk_level"],
        reason=b.get("reason"),
        status=b["status"],
        result_outcome=b.get("result_outcome"),
        closing_odds=b.get("closing_odds"),
        clv=b.get("clv"),
        profit_nok=b.get("profit_nok"),
        created_at=b["created_at"],
        settled_at=b.get("settled_at"),
    )


@app.get("/v1/bets", response_model=list[PaperBet])
def list_bets(status: str | None = None, market: str | None = None, limit: int = 200):
    """Return paper bets, optionally filtered by status/market."""
    from db.paper_bets import list_bets as _list
    return [_bet_to_schema(b) for b in _list(status=status, market=market, limit=limit)]


@app.get("/v1/bets/summary", response_model=BetSummary)
def get_bet_summary():
    """Aggregate performance metrics across all settled paper bets."""
    from db.paper_bets import get_summary
    return BetSummary(**get_summary())


@app.get("/v1/bets/bankroll", response_model=list[BankrollPoint])
def get_bankroll():
    """Chronological bankroll series for the equity chart."""
    from db.paper_bets import get_bankroll_history
    return [BankrollPoint(**p) for p in get_bankroll_history()]


@app.post("/v1/bets/generate", response_model=GenerateBetsResponse)
def generate_bets(coupon_id: str | None = None):
    """
    Generate paper bets for the active coupon based on model edge vs market.

    Rules:
    - 1X2: market_edge_pp (model_prob − implied_prob) ≥ 5pp
    - BTTS: btts_market_edge_pp ≥ 5pp  (only when odds_markets has BTTS odds)
    - Over 2.5: over_market_edge_pp ≥ 5pp  (only when odds_markets has O/U odds)
    - Bets are idempotent per (fixture_id, market, outcome, coupon_id)
    """
    from db.paper_bets import create_bet, bet_exists

    # Re-use the insights endpoint logic to get a fully enriched signal list
    # (calling the function directly avoids code duplication)
    insights_resp = get_insights(coupon_id=coupon_id)
    resolved_coupon_id = insights_resp.coupon_id

    created_bets: list[PaperBet] = []
    n_skipped = 0
    MIN_EDGE_PP = 5.0

    for s in insights_resp.signals:
        fid = s.fixture_id
        if fid is None:
            n_skipped += 1
            continue

        match_name = f"{s.home_team} vs {s.away_team}"

        # ── 1X2 ──────────────────────────────────────────────────────────────
        if (
            s.implied_prob is not None
            and s.market_edge_pp is not None
            and s.market_edge_pp >= MIN_EDGE_PP
            and s.odds_h and s.odds_u and s.odds_b
        ):
            pick = s.recommended_pick
            ref_odds_map = {"H": s.odds_h, "U": s.odds_u, "B": s.odds_b}
            ref_odds = ref_odds_map.get(pick)
            implied = s.implied_prob / 100 if s.implied_prob else None

            if ref_odds and implied and not bet_exists(fid, "1x2", pick, resolved_coupon_id):
                insight_type = "longshot" if s.model_prob <= 35 else "value_bet"
                reason = (
                    f"Modell {s.model_prob}% vs marked {s.implied_prob}% "
                    f"(+{s.market_edge_pp:.1f}pp). "
                    f"Odds: {ref_odds:.2f} ({s.odds_source or 'ukjent'})."
                )
                bet_id = create_bet(
                    fixture_id=fid,
                    match_name=match_name,
                    market="1x2",
                    outcome=pick,
                    bookmaker=s.odds_source or "ukjent",
                    ref_odds=ref_odds,
                    implied_prob=implied,
                    model_prob=s.model_prob / 100,
                    edge_pp=s.market_edge_pp,
                    insight_type=insight_type,
                    reason=reason,
                    league=s.league_name,
                    kickoff_utc=s.kickoff_utc,
                    coupon_id=resolved_coupon_id,
                )
                from db.paper_bets import list_bets as _lb
                for b in _lb(limit=1):
                    if b["id"] == bet_id:
                        created_bets.append(_bet_to_schema(b))
                        break
            else:
                n_skipped += 1

        # ── BTTS ─────────────────────────────────────────────────────────────
        if (
            s.btts_model_prob is not None
            and s.btts_implied_yes is not None
            and s.btts_market_edge_pp is not None
            and s.btts_market_edge_pp >= MIN_EDGE_PP
            and s.btts_yes_odds
        ):
            if not bet_exists(fid, "btts", "yes", resolved_coupon_id):
                reason = (
                    f"Poisson BTTS {s.btts_model_prob}% vs marked {s.btts_implied_yes}% "
                    f"(+{s.btts_market_edge_pp:.1f}pp). xG: {s.xg_home}–{s.xg_away}."
                )
                bet_id = create_bet(
                    fixture_id=fid,
                    match_name=match_name,
                    market="btts",
                    outcome="yes",
                    bookmaker=s.btts_bookmaker or "ukjent",
                    ref_odds=s.btts_yes_odds,
                    implied_prob=s.btts_implied_yes / 100,
                    model_prob=s.btts_model_prob / 100,
                    edge_pp=s.btts_market_edge_pp,
                    insight_type="value_bet",
                    reason=reason,
                    league=s.league_name,
                    kickoff_utc=s.kickoff_utc,
                    coupon_id=resolved_coupon_id,
                )
                from db.paper_bets import list_bets as _lb2
                for b in _lb2(limit=1):
                    if b["id"] == bet_id:
                        created_bets.append(_bet_to_schema(b))
                        break
            else:
                n_skipped += 1

        # ── Over 2.5 ─────────────────────────────────────────────────────────
        if (
            s.over_model_prob is not None
            and s.over_implied is not None
            and s.over_market_edge_pp is not None
            and s.over_market_edge_pp >= MIN_EDGE_PP
            and s.over_25_odds
        ):
            if not bet_exists(fid, "over_2.5", "over", resolved_coupon_id):
                reason = (
                    f"Poisson Over2.5 {s.over_model_prob}% vs marked {s.over_implied}% "
                    f"(+{s.over_market_edge_pp:.1f}pp). xG: {s.xg_home}–{s.xg_away}."
                )
                bet_id = create_bet(
                    fixture_id=fid,
                    match_name=match_name,
                    market="over_2.5",
                    outcome="over",
                    bookmaker=s.ou_bookmaker or "ukjent",
                    ref_odds=s.over_25_odds,
                    implied_prob=s.over_implied / 100,
                    model_prob=s.over_model_prob / 100,
                    edge_pp=s.over_market_edge_pp,
                    insight_type="value_bet",
                    reason=reason,
                    league=s.league_name,
                    kickoff_utc=s.kickoff_utc,
                    coupon_id=resolved_coupon_id,
                )
                from db.paper_bets import list_bets as _lb3
                for b in _lb3(limit=1):
                    if b["id"] == bet_id:
                        created_bets.append(_bet_to_schema(b))
                        break
            else:
                n_skipped += 1

    return GenerateBetsResponse(
        created=len(created_bets),
        skipped=n_skipped,
        bets=created_bets,
    )


@app.post("/v1/bets/settle")
def settle_all_bets():
    """
    Fetch API-Football results for all expired pending bets, then settle them.
    Returns a summary of what was checked, fetched, and settled.
    Idempotent — safe to call multiple times.
    """
    from db.paper_bets import fetch_and_settle_all_expired
    return fetch_and_settle_all_expired(buffer_minutes=100)


@app.post("/v1/bets/settle/{fixture_id}")
def settle_bets(fixture_id: str):
    """Settle pending paper bets for a fixture using match_results."""
    from db.paper_bets import settle_pending_bets
    n = settle_pending_bets(fixture_id)
    return {"settled": n, "fixture_id": fixture_id}


def generate_global_bet_candidates(min_edge_pp: float = 5.0, nt_only: bool = False) -> dict:
    """
    Evaluate ALL upcoming fixtures with 1X2 odds using available bookmaker market odds.

    Calibration rules (all preserved from 2026-06-30):
      • min_edge_pp = 5.0 — only bets with ≥ 5pp model edge
      • min_odds    = 1.50 — skip recommended outcomes with odds < 1.50
      • Bayesian xG shrinkage (k=6) applied to Poisson BTTS/O/U models
      • Minimum sample gates: venue Phase 13 requires n ≥ 5; AF predictions require played ≥ 5
      • generic_prior bets suppressed — no bet without match-specific data
      • Contradictory bets prevented via resolve_contradictory_bets()
      • af_supported 1X2 suppressed — bookmaker prior required for WDL edge

    Model quality hierarchy:
      full_model    — enrichment with real goal data → Poisson from seasonal stats
      af_supported  — no enrichment, but AF Predictions last_5 available (Poisson only)
      generic_prior — no enrichment, no AF predictions (suppressed — no bets)

    Tier system (edge_pp stored in insight_type):
      tier_a — edge ≥ 8pp | tier_b — 5–8pp | tier_c — 3–5pp

    Markets: 1X2 · BTTS-yes/no · Over/Under 2.5
    Coupon ID is NULL for all global candidates.
    Idempotent via bet_exists().
    """
    import json as _json
    from db.connection import get_conn
    from db.paper_bets import (
        create_bet, bet_exists,
        get_conflicting_bet, void_bet, resolve_contradictory_bets, _QUALITY_RANK,
    )
    from db.odds_movement import _devig
    from models.match import Match
    from analysis.probability import process_match
    from analysis.model import run_model
    from analysis.market_models import (
        market_probs_from_enrichment, btts_probability, over_under_probability,
        win_draw_loss_probability, bookmaker_implied_xg,
    )
    from datetime import datetime, timezone

    _min_edge  = min_edge_pp  # 5.0 by default
    _min_odds  = 1.50         # skip heavy favourites with tiny edges
    _plaus_max = 8.00         # two-way market: reject if either leg ≥ this (placeholder)
    _plaus_min = 1.10         # two-way market: reject if either leg ≤ this (placeholder)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # European-average Poisson prior (Level 4 — last resort)
    _EU_HOME_XG = 1.40
    _EU_AWAY_XG = 1.10
    _eu_btts_yes = btts_probability(_EU_HOME_XG, _EU_AWAY_XG)
    _eu_over_25, _eu_under_25 = over_under_probability(_EU_HOME_XG, _EU_AWAY_XG)

    conn = get_conn()

    rows = conn.execute(
        """SELECT DISTINCT o.fixture_id, o.odds_h, o.odds_u, o.odds_b, o.source,
                  f.kickoff_utc,
                  COALESCE(ht.name_local, ht2.name_local, f.home_name) AS home_name,
                  COALESCE(at.name_local, at2.name_local, f.away_name) AS away_name,
                  lnk.api_football_fixture_id AS af_id
           FROM odds o
           JOIN fixtures f ON f.fixture_id = o.fixture_id
           LEFT JOIN teams ht  ON ht.team_id   = f.home_team_id
           LEFT JOIN teams at  ON at.team_id   = f.away_team_id
           LEFT JOIN api_football_fixture_links lnk ON lnk.fixture_id = o.fixture_id
           LEFT JOIN teams ht2 ON ht2.external_id = lnk.api_football_home_team_id
           LEFT JOIN teams at2 ON at2.external_id = lnk.api_football_away_team_id
           WHERE f.kickoff_utc > ?
           ORDER BY o.fixture_id, o.fetched_at DESC""",
        (now_iso,),
    ).fetchall()

    seen_fids: set[str] = set()
    fixtures_to_eval: list[dict] = []
    for r in rows:
        fid = r["fixture_id"]
        if fid not in seen_fids:
            seen_fids.add(fid)
            fixtures_to_eval.append(dict(r))

    fid_list = [f["fixture_id"] for f in fixtures_to_eval]

    enr_map: dict[str, dict] = {}
    pred_map: dict[str, str | None] = {}  # fixture_id → raw_json
    mkt_map: dict[str, dict] = {}

    if fid_list:
        placeholders = ",".join("?" * len(fid_list))
        for er in conn.execute(
            f"SELECT * FROM fixture_stat_enrichment WHERE fixture_id IN ({placeholders})",
            fid_list,
        ).fetchall():
            enr_map[er["fixture_id"]] = dict(er)

        for pr in conn.execute(
            f"SELECT fixture_id, raw_json FROM api_football_predictions WHERE fixture_id IN ({placeholders})",
            fid_list,
        ).fetchall():
            pred_map[pr["fixture_id"]] = pr["raw_json"]

        for mr in conn.execute(
            f"SELECT fixture_id, market_key, selection, odds, bookmaker FROM odds_markets WHERE fixture_id IN ({placeholders})",
            fid_list,
        ).fetchall():
            fid = mr["fixture_id"]; mk = mr["market_key"]; sel = mr["selection"]
            if fid not in mkt_map: mkt_map[fid] = {}
            if mk not in mkt_map[fid]: mkt_map[fid][mk] = {"bookmaker": mr["bookmaker"]}
            mkt_map[fid][mk][sel] = mr["odds"]

    # Load NT Oddsen snapshots (Playwright scraper, max 6h old)
    _nt_map:       dict[str, dict[str, float]] = {}
    _nt_btts_map:  dict[str, dict[str, float]] = {}
    _nt_ou15_map:  dict[str, dict[str, float]] = {}
    _nt_ou_map:    dict[str, dict[str, float]] = {}
    _nt_ou35_map:  dict[str, dict[str, float]] = {}
    _nt_norm = None
    try:
        from ingestion.nt_oddsen_playwright import (
            load_nt_odds_bulk, load_nt_market_bulk, normalize_team_name as _nt_norm_fn,
        )
        _nt_map      = load_nt_odds_bulk(conn)
        _nt_btts_map = load_nt_market_bulk(conn, "BTTS",            {"YES", "NO"})
        _nt_ou15_map = load_nt_market_bulk(conn, "OVER_UNDER_1_5",  {"OVER", "UNDER"})
        _nt_ou_map   = load_nt_market_bulk(conn, "OVER_UNDER_2_5",  {"OVER", "UNDER"})
        _nt_ou35_map = load_nt_market_bulk(conn, "OVER_UNDER_3_5",  {"OVER", "UNDER"})
        _nt_norm     = _nt_norm_fn
    except Exception:
        pass

    conn.close()

    # Minimum played games required to trust AF predictions xG
    _MIN_AF_PLAYED = 5

    # Parse last_5 goal averages from AF prediction raw JSON -> xG estimate.
    # Requires played >= _MIN_AF_PLAYED and applies Bayesian shrinkage (k=6).
    # Returns (xg_h, xg_a, raw_xg_h, raw_xg_a, n_eff, w) or None.
    # Callers that only use pxg[0] and pxg[1] are unaffected by the extra fields.
    def _pred_xg(raw_json: str | None) -> tuple[float, float, float, float, int, float] | None:
        if not raw_json:
            return None
        try:
            raw = _json.loads(raw_json)
            h5 = raw["teams"]["home"]["last_5"]["goals"]
            a5 = raw["teams"]["away"]["last_5"]["goals"]
            h_played = int(raw["teams"]["home"]["last_5"].get("played") or 0)
            a_played = int(raw["teams"]["away"]["last_5"].get("played") or 0)
            if h_played < _MIN_AF_PLAYED or a_played < _MIN_AF_PLAYED:
                return None
            hf = float(h5["for"]["average"])
            ha = float(h5["against"]["average"])
            af = float(a5["for"]["average"])
            aa = float(a5["against"]["average"])
            raw_xg_h = max((hf + aa) / 2, 0.1)
            raw_xg_a = max((af + ha) / 2, 0.05)
            # Bayesian shrinkage toward EU average
            n_eff = min(h_played, a_played)
            w = n_eff / (n_eff + 6)
            xg_h = max(w * raw_xg_h + (1 - w) * _EU_HOME_XG, 0.1)
            xg_a = max(w * raw_xg_a + (1 - w) * _EU_AWAY_XG, 0.05)
            return xg_h, xg_a, raw_xg_h, raw_xg_a, n_eff, round(w, 3)
        except Exception:
            return None

    # Resolve existing contradictory bets before generating new ones
    resolve_contradictory_bets()

    # NT fixture-key lookup helper (exact date + ±1 day fallback)
    def _nt_find(nt_source: dict, home: str, away: str, ko_utc: str | None) -> dict | None:
        if not _nt_norm or not nt_source:
            return None
        ko_date = (ko_utc or "")[:10]
        fk = f"{_nt_norm(home)}|{_nt_norm(away)}|{ko_date}"
        if fk in nt_source:
            return nt_source[fk]
        if ko_date:
            try:
                from datetime import timedelta as _td
                d0 = datetime.strptime(ko_date, "%Y-%m-%d")
                for delta in (1, -1):
                    adj = (d0 + _td(days=delta)).strftime("%Y-%m-%d")
                    fk2 = f"{_nt_norm(home)}|{_nt_norm(away)}|{adj}"
                    if fk2 in nt_source:
                        return nt_source[fk2]
            except Exception:
                pass
        return None

    # NT fixture key deduplication: prevents two DB fixture IDs for the same match
    # (e.g. one from NT coupon + one inserted by enrichment) from generating duplicate bets.
    _processed_nt_keys: set[str] = set()

    # Rejection counters
    reject_bad_odds          = 0
    reject_no_enr_1x2        = 0
    reject_af_1x2            = 0
    reject_generic_prior     = 0
    reject_edge_small        = 0
    reject_duplicate         = 0
    reject_contradictory     = 0
    reject_error             = 0
    reject_odds_too_low      = 0
    reject_no_nt_odds        = 0
    reject_no_btts_ou_odds   = 0
    reject_nt_placeholder    = 0
    reject_no_nt_btts_ou     = 0  # nt_only mode: no NT odds found for BTTS/O/U
    reject_small_sample      = 0  # n_eff < 5 and edge < 10pp
    n_evaluated              = 0
    tier_counts              = {"a": 0, "b": 0, "c": 0}
    bets_by_market           = {"1x2": 0, "btts": 0, "over_1.5": 0, "over_2.5": 0, "over_3.5": 0}

    # Diagnostics
    rejected_candidates: list[dict]       = []
    _market_edge_data:   dict[str, list]  = {}
    n_nt_matched         = {"1x2": 0, "btts": 0, "over_1.5": 0, "over_2.5": 0, "over_3.5": 0}

    # Cross-market conflict rules: (market, outcome) → incompatible (market, outcome) pairs.
    # e.g. if BTTS-yes lands, Under 1.5 is impossible (needs ≥2 goals vs ≤1 goal).
    _CROSS_CONFLICTS: dict[tuple, list] = {
        ("btts",     "yes"):  [("over_1.5", "under")],
        ("over_1.5", "over"): [("over_1.5", "under")],
        ("over_2.5", "over"): [("over_1.5", "under"), ("over_2.5", "under")],
        ("over_3.5", "over"): [("over_1.5", "under"), ("over_2.5", "under"), ("over_3.5", "under")],
        ("over_1.5", "under"): [("btts", "yes"), ("over_1.5", "over"), ("over_2.5", "over"), ("over_3.5", "over")],
        ("over_2.5", "under"): [("over_2.5", "over"), ("over_3.5", "over")],
        ("over_3.5", "under"): [("over_3.5", "over")],
    }

    # Per-fixture candidate buffer: candidates queue here; _flush_fixture() resolves
    # cross-market conflicts before any create_bet() call.
    _fixture_buf:          list[dict] = []
    cross_conflict_log:    list[dict] = []
    n_cross_conflict_rejected         = 0

    def _tier(ep: float) -> str:
        return "tier_a" if ep >= 8 else ("tier_b" if ep >= 5 else "tier_c")

    def _reject_candidate(match_name, market, outcome, bookmaker, ref_odds,
                          impl_p, model_p, ep, reason, model_quality, league, kickoff):
        ev = round(model_p * ref_odds - 1, 4) if ref_odds else None
        rejected_candidates.append({
            "fixture":       match_name,
            "market":        market,
            "selection":     outcome,
            "bookmaker":     bookmaker,
            "ref_odds":      round(ref_odds, 2) if ref_odds else None,
            "model_prob":    round(model_p, 4),
            "implied_prob":  round(impl_p, 4),
            "edge_pp":       round(ep, 2),
            "ev":            ev,
            "reason":        reason,
            "model_quality": model_quality,
            "league":        league,
            "kickoff_utc":   kickoff,
        })

    def _make_bet(fid, match_name, market, outcome, bookmaker, ref_odds,
                  impl_p, model_p, ep, reason, league, kickoff, model_quality,
                  debug_json=None, n_eff=None):
        """Filter candidate and buffer it for cross-market conflict resolution."""
        nonlocal reject_edge_small, reject_duplicate, reject_odds_too_low, reject_small_sample
        _market_edge_data.setdefault(market, []).append(ep)
        # Small-sample caution: n_eff < 5 requires ≥10pp edge for BTTS/O/U
        if n_eff is not None and n_eff < 5 and ep < 10.0:
            reject_small_sample += 1
            _reject_candidate(match_name, market, outcome, bookmaker, ref_odds,
                              impl_p, model_p, ep, "small_sample_edge_too_low",
                              model_quality, league, kickoff)
            return
        if ep < _min_edge:
            reject_edge_small += 1
            _reject_candidate(match_name, market, outcome, bookmaker, ref_odds,
                              impl_p, model_p, ep, "edge_too_small", model_quality,
                              league, kickoff)
            return
        if ref_odds < _min_odds:
            reject_odds_too_low += 1
            _reject_candidate(match_name, market, outcome, bookmaker, ref_odds,
                              impl_p, model_p, ep, "odds_too_low", model_quality,
                              league, kickoff)
            return
        if bet_exists(fid, market, outcome):
            reject_duplicate += 1
            return
        _fixture_buf.append({
            "fid": fid, "match_name": match_name, "market": market, "outcome": outcome,
            "bookmaker": bookmaker, "ref_odds": ref_odds, "impl_p": impl_p,
            "model_p": model_p, "ep": ep, "ev": round(model_p * ref_odds - 1, 4),
            "reason": reason, "league": league, "kickoff": kickoff,
            "model_quality": model_quality, "debug_json": debug_json,
        })

    def _flush_fixture():
        """Resolve cross-market conflicts for buffered candidates, then insert survivors."""
        nonlocal n_cross_conflict_rejected, reject_contradictory
        if not _fixture_buf:
            return

        # Build key index: (market, outcome) → candidate
        buf_idx: dict[tuple, dict] = {(c["market"], c["outcome"]): c for c in _fixture_buf}
        dropped: set[tuple] = set()

        for key, cand in list(buf_idx.items()):
            if key in dropped:
                continue
            for conf_key in _CROSS_CONFLICTS.get(key, []):
                if conf_key not in buf_idx or conf_key in dropped:
                    continue
                conf = buf_idx[conf_key]
                # Keep higher EV; tie-break on edge
                cand_score = (round(cand["ev"], 6), cand["ep"])
                conf_score = (round(conf["ev"], 6), conf["ep"])
                keep, drop = (cand, conf) if cand_score >= conf_score else (conf, cand)
                drop_key   = (drop["market"], drop["outcome"])
                dropped.add(drop_key)
                cross_conflict_log.append({
                    "fixture":  cand["match_name"],
                    "kept":     f"{keep['market']} {keep['outcome']}  ev={keep['ev']:+.4f}  ep={keep['ep']:+.1f}pp",
                    "rejected": f"{drop['market']} {drop['outcome']}  ev={drop['ev']:+.4f}  ep={drop['ep']:+.1f}pp",
                    "reason":   "cross_market_conflict",
                })
                if drop_key == key:
                    break  # this candidate is dropped; skip its remaining conflict checks

        n_cross_conflict_rejected += len(dropped)

        for cand in _fixture_buf:
            key = (cand["market"], cand["outcome"])
            if key in dropped:
                _reject_candidate(
                    cand["match_name"], cand["market"], cand["outcome"],
                    cand["bookmaker"], cand["ref_odds"], cand["impl_p"],
                    cand["model_p"], cand["ep"], "cross_market_conflict",
                    cand["model_quality"], cand["league"], cand["kickoff"],
                )
                continue
            # Same-market contradiction check (different fixture_id for same market/outcome)
            conflict = get_conflicting_bet(cand["fid"], cand["market"], cand["outcome"])
            if conflict:
                existing_rank = _QUALITY_RANK.get(conflict["model_quality"] or "", 0)
                new_rank      = _QUALITY_RANK.get(cand["model_quality"] or "", 0)
                existing_ep   = conflict["edge_pp"] or 0.0
                if new_rank > existing_rank or (new_rank == existing_rank and cand["ep"] > existing_ep):
                    void_bet(conflict["id"])
                else:
                    reject_contradictory += 1
                    continue
            t = _tier(cand["ep"])
            create_bet(
                fixture_id=cand["fid"], match_name=cand["match_name"],
                market=cand["market"], outcome=cand["outcome"],
                bookmaker=cand["bookmaker"], ref_odds=cand["ref_odds"],
                implied_prob=cand["impl_p"], model_prob=cand["model_p"],
                edge_pp=cand["ep"], insight_type=t, reason=cand["reason"],
                league=cand["league"], kickoff_utc=cand["kickoff"],
                coupon_id=None, model_quality=cand["model_quality"],
                debug_json=cand["debug_json"],
            )
            tier_counts[t.split("_")[1]] += 1
            bets_by_market[cand["market"]] = bets_by_market.get(cand["market"], 0) + 1

        _fixture_buf.clear()

    # Sort enriched fixtures before un-enriched ones so the deduplication guard
    # below retains the fixture with real data when two IDs share the same NT key.
    fixtures_to_eval.sort(key=lambda f: (enr_map.get(f["fixture_id"]) is None, f["fixture_id"]))

    for fix in fixtures_to_eval:
        fid       = fix["fixture_id"]
        odds_h    = fix["odds_h"]
        odds_u    = fix["odds_u"]
        odds_b    = fix["odds_b"]
        odds_src  = fix["source"] or "api_football"
        kickoff   = fix["kickoff_utc"]
        home_name = fix["home_name"] or "Home"
        away_name = fix["away_name"] or "Away"
        match_name = f"{home_name} vs {away_name}"

        if not (odds_h and odds_u and odds_b and odds_h > 1 and odds_u > 1 and odds_b > 1):
            reject_bad_odds += 1
            continue

        # Skip if this NT fixture key was already processed by a different DB fixture ID
        if _nt_norm:
            _nt_fkey = f"{_nt_norm(home_name)}|{_nt_norm(away_name)}|{(kickoff or '')[:10]}"
            if _nt_fkey in _processed_nt_keys:
                continue
            _processed_nt_keys.add(_nt_fkey)

        bookmaker = odds_src.split(":")[-1] if ":" in odds_src else odds_src

        enr    = enr_map.get(fid)
        league = enr.get("league_name") if enr else None
        mkt    = mkt_map.get(fid, {})
        pxg    = _pred_xg(pred_map.get(fid))  # AF predictions xG, or None

        try:
            m = Match(number=0, home_team=home_name, away_team=away_name,
                      odds_h=odds_h, odds_u=odds_u, odds_b=odds_b,
                      odds_source=odds_src)
            m.fixture_id = fid
            process_match(m)
            run_model(m, enr)
        except Exception:
            reject_error += 1
            continue

        n_evaluated += 1
        ih, iu, ib = _devig(odds_h, odds_u, odds_b)
        # Match-specific Poisson prior inferred from bookmaker 1X2 vig-free probs
        bk_xg_h, bk_xg_a = bookmaker_implied_xg(ih, iu, ib)

        # ── 1X2 ────────────────────────────────────────────────────────────────
        # Only generated when:
        #   1. enrichment data exists (full_model) — bookmaker prior is the anchor
        #   2. NT Oddsen has matching 1X2 odds — odds and implied prob come from NT
        # af_supported 1X2 skipped: Poisson WDL without bookmaker anchor unreliable.
        # No enrichment → no bet. No NT odds → no bet.
        try:
            if enr:
                probs_1x2   = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}
                quality_1x2 = "full_model"
            elif pxg:
                reject_af_1x2 += 1
                probs_1x2 = None
                quality_1x2 = None
            else:
                reject_no_enr_1x2 += 1
                probs_1x2 = None
                quality_1x2 = None

            if probs_1x2:
                # Require NT Oddsen 1X2 odds (exact date + ±1 day fallback)
                _nt_fix = _nt_find(_nt_map, home_name, away_name, kickoff)

                if _nt_fix is None:
                    reject_no_nt_odds += 1
                else:
                    n_nt_matched["1x2"] += 1
                    nt_h = _nt_fix["H"]
                    nt_u = _nt_fix["U"]
                    nt_b = _nt_fix["B"]
                    nt_ih, nt_iu, nt_ib = _devig(nt_h, nt_u, nt_b)

                    rec       = max(probs_1x2, key=probs_1x2.get)
                    model_p   = probs_1x2[rec]
                    implied_p = {"H": nt_ih, "U": nt_iu, "B": nt_ib}[rec]
                    ep        = round((model_p - implied_p) * 100, 1)
                    ref_odds  = {"H": nt_h, "U": nt_u, "B": nt_b}[rec]
                    utfall = {"H": "Hjemmeseier", "U": "Uavgjort", "B": "Borteseier"}[rec]
                    reason = (
                        f"Modell {model_p*100:.1f}% vs NT Oddsen {implied_p*100:.1f}% "
                        f"(+{ep:.1f}pp). {utfall} til NT-odds {ref_odds:.2f}."
                    )
                    dbg = _json.dumps({
                        "model_quality":     quality_1x2,
                        "model_prob":        round(model_p, 4),
                        "implied_prob":      round(implied_p, 4),
                        "nt_odds_h":         nt_h,
                        "nt_odds_u":         nt_u,
                        "nt_odds_b":         nt_b,
                        "bookmaker_prior_h": round(ih, 4),
                        "bookmaker_prior_u": round(iu, 4),
                        "bookmaker_prior_b": round(ib, 4),
                    })
                    _make_bet(fid, match_name, "1x2", rec, "NT Oddsen", ref_odds,
                              implied_p, model_p, ep, reason, league, kickoff,
                              quality_1x2, debug_json=dbg)
        except Exception:
            reject_error += 1

        # ── BTTS / O/U ─────────────────────────────────────────────────────────
        # NT Oddsen odds used when available; fall back to AF odds_markets.
        # Level 1: enrichment with real goal data + Bayesian-shrunk xG (full_model)
        # Level 2: AF predictions last_5 xG, played >= 5 + shrinkage (af_supported)
        # Level 3: European-average prior (generic_prior) — NO BETS generated
        try:
            btts_mkt = mkt.get("BTTS", {})
            ou_mkt   = mkt.get("OVER_UNDER", {})

            xg_h = xg_a = None   # set in each quality branch; used for all O/U lines
            _n_eff_ou = 0         # effective sample size; drives small-sample caution

            if enr:
                poisson  = market_probs_from_enrichment(enr,
                               prior_xg_home=bk_xg_h, prior_xg_away=bk_xg_a)
                has_data = poisson.get("has_data", False)
                if has_data:
                    qual_ou    = "full_model"
                    xg_h, xg_a = poisson["xg_home"], poisson["xg_away"]
                    btts_yes_p = poisson["btts_yes"]
                    over_p     = poisson["over_2_5"]
                    xg_label   = f"xG {poisson['xg_home']}-{poisson['xg_away']}"
                    _n_eff_ou  = poisson.get("n_eff", 0)
                    dbg_ou     = _json.dumps({
                        "model_quality":      "full_model",
                        "xg_home_raw":        poisson.get("xg_home_raw"),
                        "xg_away_raw":        poisson.get("xg_away_raw"),
                        "xg_home_adjusted":   poisson["xg_home"],
                        "xg_away_adjusted":   poisson["xg_away"],
                        "bk_xg_home_prior":   round(bk_xg_h, 3),
                        "bk_xg_away_prior":   round(bk_xg_a, 3),
                        "sample_size_home":   poisson.get("sample_size_home"),
                        "sample_size_away":   poisson.get("sample_size_away"),
                        "shrinkage_weight":   poisson.get("shrinkage_weight"),
                    })
                elif pxg:
                    qual_ou    = "af_supported"
                    xg_h, xg_a = pxg[0], pxg[1]
                    btts_yes_p = btts_probability(pxg[0], pxg[1])
                    over_p, _  = over_under_probability(pxg[0], pxg[1])
                    xg_label   = f"xG {pxg[0]:.2f}-{pxg[1]:.2f} (AF)"
                    _n_eff_ou  = int(pxg[4])
                    dbg_ou     = _json.dumps({
                        "model_quality":      "af_supported",
                        "xg_home_raw":        round(pxg[2], 2),
                        "xg_away_raw":        round(pxg[3], 2),
                        "xg_home_adjusted":   round(pxg[0], 2),
                        "xg_away_adjusted":   round(pxg[1], 2),
                        "bk_xg_home_prior":   round(bk_xg_h, 3),
                        "bk_xg_away_prior":   round(bk_xg_a, 3),
                        "sample_size_home":   pxg[4],
                        "sample_size_away":   pxg[4],
                        "shrinkage_weight":   pxg[5],
                    })
                else:
                    qual_ou = "generic_prior"
            elif pxg:
                qual_ou    = "af_supported"
                xg_h, xg_a = pxg[0], pxg[1]
                btts_yes_p = btts_probability(pxg[0], pxg[1])
                over_p, _  = over_under_probability(pxg[0], pxg[1])
                xg_label   = f"xG {pxg[0]:.2f}-{pxg[1]:.2f} (AF)"
                _n_eff_ou  = int(pxg[4])
                dbg_ou     = _json.dumps({
                    "model_quality":      "af_supported",
                    "xg_home_raw":        round(pxg[2], 2),
                    "xg_away_raw":        round(pxg[3], 2),
                    "xg_home_adjusted":   round(pxg[0], 2),
                    "xg_away_adjusted":   round(pxg[1], 2),
                    "bk_xg_home_prior":   round(bk_xg_h, 3),
                    "bk_xg_away_prior":   round(bk_xg_a, 3),
                    "sample_size_home":   pxg[4],
                    "sample_size_away":   pxg[4],
                    "shrinkage_weight":   pxg[5],
                })
            else:
                qual_ou = "generic_prior"

            # Skip bet generation when only a generic prior is available
            if qual_ou == "generic_prior":
                reject_generic_prior += 1
            else:
                btts_no_p = round(1 - btts_yes_p, 4)
                under_p   = round(1 - over_p, 4)
                xg_str    = f" {xg_label}." if xg_label else ""
                qual_tag  = " (AF-støttet)" if qual_ou == "af_supported" else ""

                # ── BTTS ── prefer NT Oddsen; fall back to AF odds_markets (unless nt_only)
                _nt_btts = _nt_find(_nt_btts_map, home_name, away_name, kickoff)
                if _nt_btts:
                    ba, bb   = _nt_btts["YES"], _nt_btts["NO"]
                    bkm_btts = "NT Oddsen"
                    n_nt_matched["btts"] += 1
                elif nt_only:
                    reject_no_nt_btts_ou += 1
                    ba = bb = None
                    bkm_btts = None
                else:
                    ba = btts_mkt.get("YES")
                    bb = btts_mkt.get("NO")
                    bkm_btts = btts_mkt.get("bookmaker", bookmaker)

                def _is_plaus(a: float, b: float) -> bool:
                    """True when both legs look like real market prices (not placeholders)."""
                    return (a < _plaus_max and b < _plaus_max
                            and a > _plaus_min and b > _plaus_min)

                if ba and bb and ba > 1 and bb > 1:
                    total_inv     = 1/ba + 1/bb
                    btts_impl_yes = 1/ba / total_inv
                    btts_impl_no  = 1/bb / total_inv
                    mep_yes = round((btts_yes_p - btts_impl_yes) * 100, 1)
                    mep_no  = round((btts_no_p  - btts_impl_no)  * 100, 1)

                    if not _is_plaus(ba, bb):
                        # Placeholder/error price — log both legs and skip
                        reject_nt_placeholder += 1
                        _reject_candidate(match_name, "btts", "yes", bkm_btts, ba,
                                          btts_impl_yes, btts_yes_p, mep_yes,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                        _reject_candidate(match_name, "btts", "no", bkm_btts, bb,
                                          btts_impl_no, btts_no_p, mep_no,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                    else:
                        _src_btts = "NT Oddsen" if bkm_btts == "NT Oddsen" else "marked"
                        dbg_btts = _json.dumps({
                            **_json.loads(dbg_ou),
                            "nt_odds":         {"YES": ba, "NO": bb} if bkm_btts == "NT Oddsen" else None,
                            "nt_implied_prob":  {"YES": round(btts_impl_yes, 4), "NO": round(btts_impl_no, 4)} if bkm_btts == "NT Oddsen" else None,
                            "odds_source":     bkm_btts,
                            "market":          "btts",
                        })
                        _make_bet(fid, match_name, "btts", "yes", bkm_btts, ba,
                                  btts_impl_yes, btts_yes_p, mep_yes,
                                  f"Poisson begge scorer {btts_yes_p*100:.1f}% vs {_src_btts} {btts_impl_yes*100:.1f}% "
                                  f"(+{mep_yes:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_btts,
                                  n_eff=_n_eff_ou)
                        _make_bet(fid, match_name, "btts", "no", bkm_btts, bb,
                                  btts_impl_no, btts_no_p, mep_no,
                                  f"Poisson ikke begge scorer {btts_no_p*100:.1f}% vs {_src_btts} {btts_impl_no*100:.1f}% "
                                  f"(+{mep_no:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_btts,
                                  n_eff=_n_eff_ou)
                elif not (ba and bb) and bkm_btts is not None:
                    # Only count when we actually tried AF fallback and got no odds
                    # (bkm_btts=None means nt_only skip — already counted above)
                    reject_no_btts_ou_odds += 1

                # ── O/U 2.5 ── prefer NT Oddsen; fall back to AF odds_markets (unless nt_only)
                _nt_ou = _nt_find(_nt_ou_map, home_name, away_name, kickoff)
                if _nt_ou:
                    oa, ob = _nt_ou["OVER"], _nt_ou["UNDER"]
                    bkm_ou = "NT Oddsen"
                    n_nt_matched["over_2.5"] += 1
                elif nt_only:
                    reject_no_nt_btts_ou += 1
                    oa = ob = None
                    bkm_ou = None
                else:
                    oa = ou_mkt.get("OVER")
                    ob = ou_mkt.get("UNDER")
                    bkm_ou = ou_mkt.get("bookmaker", bookmaker)

                if oa and ob and oa > 1 and ob > 1:
                    total_inv_ou = 1/oa + 1/ob
                    over_impl    = 1/oa / total_inv_ou
                    under_impl   = 1/ob / total_inv_ou
                    mep_over  = round((over_p  - over_impl)  * 100, 1)
                    mep_under = round((under_p - under_impl) * 100, 1)

                    if not _is_plaus(oa, ob):
                        reject_nt_placeholder += 1
                        _reject_candidate(match_name, "over_2.5", "over", bkm_ou, oa,
                                          over_impl, over_p, mep_over,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                        _reject_candidate(match_name, "over_2.5", "under", bkm_ou, ob,
                                          under_impl, under_p, mep_under,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                    else:
                        _src_ou  = "NT Oddsen" if bkm_ou == "NT Oddsen" else "marked"
                        dbg_ou25 = _json.dumps({
                            **_json.loads(dbg_ou),
                            "nt_odds":        {"OVER": oa, "UNDER": ob} if bkm_ou == "NT Oddsen" else None,
                            "nt_implied_prob": {"OVER": round(over_impl, 4), "UNDER": round(under_impl, 4)} if bkm_ou == "NT Oddsen" else None,
                            "odds_source":    bkm_ou,
                            "market":         "over_2.5",
                        })
                        _make_bet(fid, match_name, "over_2.5", "over", bkm_ou, oa,
                                  over_impl, over_p, mep_over,
                                  f"Poisson over 2,5 mal {over_p*100:.1f}% vs {_src_ou} {over_impl*100:.1f}% "
                                  f"(+{mep_over:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_ou25,
                                  n_eff=_n_eff_ou)
                        _make_bet(fid, match_name, "over_2.5", "under", bkm_ou, ob,
                                  under_impl, under_p, mep_under,
                                  f"Poisson under 2,5 mal {under_p*100:.1f}% vs {_src_ou} {under_impl*100:.1f}% "
                                  f"(+{mep_under:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_ou25,
                                  n_eff=_n_eff_ou)
                elif not (oa and ob) and bkm_ou is not None:
                    reject_no_btts_ou_odds += 1

                # ── O/U 1.5 ── NT Oddsen odds only (no AF fallback)
                _nt_ou15 = _nt_find(_nt_ou15_map, home_name, away_name, kickoff)
                if _nt_ou15:
                    o15a, o15b = _nt_ou15["OVER"], _nt_ou15["UNDER"]
                    n_nt_matched["over_1.5"] += 1
                    over_15_p, under_15_p = over_under_probability(xg_h, xg_a, line=1.5)
                    total_inv_15 = 1/o15a + 1/o15b
                    over15_impl  = 1/o15a / total_inv_15
                    under15_impl = 1/o15b / total_inv_15
                    ep_o15 = round((over_15_p  - over15_impl)  * 100, 1)
                    ep_u15 = round((under_15_p - under15_impl) * 100, 1)
                    if not _is_plaus(o15a, o15b):
                        reject_nt_placeholder += 1
                        _reject_candidate(match_name, "over_1.5", "over", "NT Oddsen", o15a,
                                          over15_impl, over_15_p, ep_o15,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                        _reject_candidate(match_name, "over_1.5", "under", "NT Oddsen", o15b,
                                          under15_impl, under_15_p, ep_u15,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                    else:
                        dbg_ou15 = _json.dumps({
                            **_json.loads(dbg_ou),
                            "nt_odds":        {"OVER": o15a, "UNDER": o15b},
                            "nt_implied_prob": {"OVER": round(over15_impl, 4), "UNDER": round(under15_impl, 4)},
                            "odds_source":    "NT Oddsen",
                            "market":         "over_1.5",
                        })
                        _make_bet(fid, match_name, "over_1.5", "over", "NT Oddsen", o15a,
                                  over15_impl, over_15_p, ep_o15,
                                  f"Poisson over 1,5 mal {over_15_p*100:.1f}% vs NT Oddsen {over15_impl*100:.1f}% "
                                  f"(+{ep_o15:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_ou15,
                                  n_eff=_n_eff_ou)
                        _make_bet(fid, match_name, "over_1.5", "under", "NT Oddsen", o15b,
                                  under15_impl, under_15_p, ep_u15,
                                  f"Poisson under 1,5 mal {under_15_p*100:.1f}% vs NT Oddsen {under15_impl*100:.1f}% "
                                  f"(+{ep_u15:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_ou15,
                                  n_eff=_n_eff_ou)
                elif nt_only:
                    reject_no_nt_btts_ou += 1

                # ── O/U 3.5 ── NT Oddsen odds only (no AF fallback)
                _nt_ou35 = _nt_find(_nt_ou35_map, home_name, away_name, kickoff)
                if _nt_ou35:
                    o35a, o35b = _nt_ou35["OVER"], _nt_ou35["UNDER"]
                    n_nt_matched["over_3.5"] += 1
                    over_35_p, under_35_p = over_under_probability(xg_h, xg_a, line=3.5)
                    total_inv_35 = 1/o35a + 1/o35b
                    over35_impl  = 1/o35a / total_inv_35
                    under35_impl = 1/o35b / total_inv_35
                    ep_o35 = round((over_35_p  - over35_impl)  * 100, 1)
                    ep_u35 = round((under_35_p - under35_impl) * 100, 1)
                    if not _is_plaus(o35a, o35b):
                        reject_nt_placeholder += 1
                        _reject_candidate(match_name, "over_3.5", "over", "NT Oddsen", o35a,
                                          over35_impl, over_35_p, ep_o35,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                        _reject_candidate(match_name, "over_3.5", "under", "NT Oddsen", o35b,
                                          under35_impl, under_35_p, ep_u35,
                                          "nt_placeholder_odds", qual_ou, league, kickoff)
                    else:
                        dbg_ou35 = _json.dumps({
                            **_json.loads(dbg_ou),
                            "nt_odds":        {"OVER": o35a, "UNDER": o35b},
                            "nt_implied_prob": {"OVER": round(over35_impl, 4), "UNDER": round(under35_impl, 4)},
                            "odds_source":    "NT Oddsen",
                            "market":         "over_3.5",
                        })
                        _make_bet(fid, match_name, "over_3.5", "over", "NT Oddsen", o35a,
                                  over35_impl, over_35_p, ep_o35,
                                  f"Poisson over 3,5 mal {over_35_p*100:.1f}% vs NT Oddsen {over35_impl*100:.1f}% "
                                  f"(+{ep_o35:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_ou35,
                                  n_eff=_n_eff_ou)
                        _make_bet(fid, match_name, "over_3.5", "under", "NT Oddsen", o35b,
                                  under35_impl, under_35_p, ep_u35,
                                  f"Poisson under 3,5 mal {under_35_p*100:.1f}% vs NT Oddsen {under35_impl*100:.1f}% "
                                  f"(+{ep_u35:.1f}pp).{xg_str}{qual_tag}",
                                  league, kickoff, qual_ou, debug_json=dbg_ou35,
                                  n_eff=_n_eff_ou)
                elif nt_only:
                    reject_no_nt_btts_ou += 1

        except Exception:
            reject_error += 1

        # Resolve cross-market conflicts for this fixture, then insert survivors.
        _flush_fixture()

    n_created = sum(tier_counts.values())

    # Per-market edge statistics (all evaluated candidates, accepted + rejected)
    market_stats: dict = {}
    for mkt, edges in _market_edge_data.items():
        if edges:
            market_stats[mkt] = {
                "n_evaluated":       len(edges),
                "max_edge":          round(max(edges), 2),
                "avg_edge":          round(sum(edges) / len(edges), 2),
                "n_above_threshold": sum(1 for e in edges if e >= _min_edge),
            }

    # Sort rejected by EV descending (best missed opportunity first), keep top 50
    rejected_candidates.sort(key=lambda c: c.get("ev") or -99, reverse=True)

    return {
        "n_evaluated":     n_evaluated,
        "n_created":       n_created,
        "n_skipped":       reject_edge_small + reject_duplicate,
        "bets_by_market":  bets_by_market,
        "n_nt_matched":    n_nt_matched,
        "market_stats":    market_stats,
        "rejected_candidates": rejected_candidates[:50],
        "rejection_breakdown": {
            "bad_odds":           reject_bad_odds,
            "odds_too_low":       reject_odds_too_low,
            "no_enr_1x2":         reject_no_enr_1x2,
            "af_1x2_skipped":     reject_af_1x2,
            "no_nt_odds_1x2":     reject_no_nt_odds,
            "no_btts_ou_odds":    reject_no_btts_ou_odds,
            "no_nt_btts_ou":      reject_no_nt_btts_ou,
            "nt_placeholder_odds": reject_nt_placeholder,
            "generic_prior":      reject_generic_prior,
            "contradictory":         reject_contradictory,
            "edge_too_small":        reject_edge_small,
            "small_sample_edge_too_low": reject_small_sample,
            "duplicate":             reject_duplicate,
            "cross_market_conflict": n_cross_conflict_rejected,
            "error":                 reject_error,
        },
        "cross_conflict_log": cross_conflict_log,
        "tiers": tier_counts,
        "min_edge_pp": _min_edge,
    }


@app.post("/v1/bets/scan", response_model=ScanResponse)
def scan_and_generate(lookahead_hours: int = 72):
    """
    Trigger a global odds scan then generate Modellspill candidates.

    Flow:
      1. scrape_nt_oddsen_playwright — scrape NT Oddsen 1X2 + BTTS + O/U 2.5 (Playwright headless)
      2. scan_af_market_odds — fetch fixtures + bookmaker odds for 27 leagues (72h window)
      3. generate_global_bet_candidates — run model; all markets prefer NT odds, fall back to AF

    Tiers: A ≥ 8pp | B 5–8pp | C 3–5pp.  Min edge 5pp.  Min odds 1.50.
    1X2 bets only generated when NT Oddsen has matching odds.
    BTTS/O/U: NT odds preferred; AF odds_markets used as fallback.
    NT public percentages are never used in model probability.
    """
    import time as _time
    from ingestion.api_football_odds import scan_af_market_odds
    from ingestion.nt_oddsen_playwright import scrape_nt_oddsen_playwright
    t0 = _time.monotonic()
    nt_summary = scrape_nt_oddsen_playwright(verbose=False)
    scan_summary = scan_af_market_odds(lookahead_hours=lookahead_hours, verbose=False)
    cand_summary = generate_global_bet_candidates()
    duration = round(_time.monotonic() - t0, 2)
    return ScanResponse(
        scan=scan_summary,
        candidates=cand_summary,
        nt_scrape=nt_summary,
        duration_s=duration,
    )
