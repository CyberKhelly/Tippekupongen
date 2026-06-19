"""
TippeQpongen FastAPI backend.

Run from the project root:
    uvicorn backend.main:app --reload --port 8000

Streamlit continues to run independently on its own port:
    streamlit run app.py

Both use the same analysis/, db/, data/, models/ modules — no duplication.
"""
from __future__ import annotations

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
    CouponDetail,
    CouponListItem,
    CouponMatchRaw,
    CouponShape,
    MatchResult,
    OptimizeRequest,
    OptimizeResponse,
    PayoutSimulation,
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
        ))

    payout: PayoutSimulation | None = None
    if req.omsetning and req.omsetning > 0:
        sim = simulate_payout(
            matches, picks, total_rows, req.omsetning,
            cost_per_row=req.cost_per_row,
        )
        if sim.get("n_winning_sims", 0) > 0:
            payout = PayoutSimulation(**sim)

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


@app.post("/v1/sync/full", response_model=SyncAccepted)
def sync_full(background_tasks: BackgroundTasks):
    """Alias for daily sync (NT + odds + enrichment + estimated priors)."""
    state = load_state()
    if state.get("is_running"):
        raise HTTPException(status_code=409, detail="A sync job is already running")
    from backend.scheduler import do_daily_sync
    background_tasks.add_task(do_daily_sync, force=True)
    return SyncAccepted(accepted=True, message="Full sync started in background")
