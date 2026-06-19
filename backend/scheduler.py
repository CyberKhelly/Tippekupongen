"""
APScheduler background jobs for automatic data refresh.

Refresh schedule (self-throttled — all jobs run on a 5-min tick):
  NT coupon data (public %, turnover):
    - > 3 h to deadline   → refresh every 60 min
    - 30 min – 3 h        → refresh every 15 min
    - < 30 min            → refresh every 5 min
    - past deadline        → skip
  Pinnacle odds:
    - every 3 hours

Never starts a second job while one is running (_run_lock).
Does NOT call sync.py commands that contain sys.exit().
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend.sync_state import load_state, patch_state

logger = logging.getLogger("tippeqpongen.scheduler")

_scheduler: BackgroundScheduler | None = None
_run_lock = threading.Lock()


# ── Time helpers ─────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _secs_since(iso: str | None) -> float:
    dt = _parse_iso(iso)
    if dt is None:
        return float("inf")
    return max(0.0, (_now() - dt).total_seconds())


def _current_week_year() -> tuple[int, int]:
    iso = datetime.now().isocalendar()
    return iso.week, iso.year


# ── DB helpers ────────────────────────────────────────────────────────────────

def _secs_to_earliest_deadline() -> float:
    """Seconds until the earliest upcoming coupon deadline (inf if none)."""
    try:
        from db.coupon import list_coupons
        week, year = _current_week_year()
        coupons = list_coupons(week=week, year=year)
        if not coupons:
            return float("inf")
        now = _now()
        min_secs = float("inf")
        for c in coupons:
            dl = c.get("deadline_utc")
            if dl:
                dt = _parse_iso(dl)
                if dt and dt > now:
                    min_secs = min(min_secs, (dt - now).total_seconds())
        return min_secs
    except Exception:
        return float("inf")


def _snapshot_public_tips() -> dict[str, tuple]:
    """Read current public tip percentages for diff comparison."""
    try:
        from db.connection import get_conn
        week, year = _current_week_year()
        conn = get_conn()
        rows = conn.execute(
            """SELECT cf.fixture_id, cf.public_h, cf.public_u, cf.public_b
               FROM coupon_fixtures cf
               JOIN coupons c ON c.coupon_id = cf.coupon_id
               WHERE c.week=? AND c.year=?""",
            (week, year),
        ).fetchall()
        conn.close()
        return {r["fixture_id"]: (r["public_h"], r["public_u"], r["public_b"]) for r in rows}
    except Exception:
        return {}


def _count_tip_changes(before: dict[str, tuple]) -> int:
    """Compare snapshot against current DB values; return number changed."""
    try:
        from db.connection import get_conn
        week, year = _current_week_year()
        conn = get_conn()
        rows = conn.execute(
            """SELECT cf.fixture_id, cf.public_h, cf.public_u, cf.public_b
               FROM coupon_fixtures cf
               JOIN coupons c ON c.coupon_id = cf.coupon_id
               WHERE c.week=? AND c.year=?""",
            (week, year),
        ).fetchall()
        conn.close()
        changed = 0
        for r in rows:
            fid = r["fixture_id"]
            after = (r["public_h"], r["public_u"], r["public_b"])
            if before.get(fid) != after:
                changed += 1
        return changed
    except Exception:
        return 0


def _get_turnover() -> dict[str, float]:
    """Read omsetning for all currently active coupons."""
    try:
        from db.coupon import list_active_coupons
        return {
            c["coupon_id"]: c["omsetning"]
            for c in list_active_coupons()
            if c.get("omsetning") is not None
        }
    except Exception:
        return {}


def _get_active_coupon_ids() -> list[str]:
    try:
        from db.coupon import list_coupons
        week, year = _current_week_year()
        return [c["coupon_id"] for c in list_coupons(week=week, year=year)]
    except Exception:
        return []


# ── Required interval based on deadline proximity ────────────────────────────

def _required_nt_interval(deadline_secs: float) -> int:
    if deadline_secs <= 30 * 60:
        return 5 * 60
    if deadline_secs <= 3 * 3600:
        return 15 * 60
    return 60 * 60


# ── Core sync functions (called by scheduler AND endpoint background tasks) ───

def do_nt_refresh(*, force: bool = False) -> dict:
    """
    Refresh NT coupon data (public tip %, deadline, turnover).
    Returns a summary dict.

    Raises RuntimeError if a job is already running.
    Does NOT call sys.exit under any circumstances.
    """
    state = load_state()
    if state.get("is_running") and not force:
        raise RuntimeError("A sync job is already running")

    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("A sync job is already running")

    summary: dict = {"ok": False, "n_changes": 0, "coupon_ids": []}
    try:
        patch_state(is_running=True, current_job="nt_refresh")
        week, year = _current_week_year()
        before = _snapshot_public_tips()

        from ingestion.norsk_tipping import ingest_game_days
        ok = ingest_game_days(week=week, year=year)

        now_iso = _iso(_now())
        n_changes = _count_tip_changes(before) if ok else 0
        turnover = _get_turnover()
        coupon_ids = _get_active_coupon_ids()

        deadline_secs = _secs_to_earliest_deadline()
        next_interval = _required_nt_interval(deadline_secs)
        next_nt = _iso(_now() + timedelta(seconds=next_interval))

        if ok:
            logger.info("NT refresh ok — %d public%% change(s), coupons=%s", n_changes, coupon_ids)
            patch_state(
                is_running=False, current_job=None,
                last_nt_refresh_at=now_iso,
                last_success=True, last_error=None,
                n_public_pct_changes=n_changes,
                turnover=turnover,
                updated_coupon_ids=coupon_ids,
                next_nt_refresh_at=next_nt,
            )
        else:
            logger.warning("NT refresh returned no coupons")
            patch_state(
                is_running=False, current_job=None,
                last_nt_refresh_at=now_iso,
                last_success=False,
                last_error="NT API returned no coupons",
                next_nt_refresh_at=next_nt,
            )
        summary = {"ok": ok, "n_changes": n_changes, "coupon_ids": coupon_ids}
    except Exception as exc:
        logger.exception("NT refresh failed: %s", exc)
        patch_state(is_running=False, current_job=None,
                    last_success=False, last_error=str(exc)[:300])
        raise
    finally:
        _run_lock.release()
    return summary


def do_odds_refresh(*, force: bool = False) -> dict:
    """
    Refresh Pinnacle odds for all active coupons.
    Raises RuntimeError if a job is already running.
    """
    state = load_state()
    if state.get("is_running") and not force:
        raise RuntimeError("A sync job is already running")

    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("A sync job is already running")

    summary: dict = {"ok": False, "n_fixtures": 0}
    try:
        from config import ODDS_API_KEY
        if not ODDS_API_KEY:
            now_iso = _iso(_now())
            patch_state(
                last_odds_refresh_at=now_iso,
                next_odds_refresh_at=_iso(_now() + timedelta(hours=3)),
            )
            return {"ok": True, "n_fixtures": 0, "note": "ODDS_API_KEY not set"}

        patch_state(is_running=True, current_job="odds_refresh")
        week, year = _current_week_year()

        from db.coupon import list_coupons
        from ingestion.odds_api import ingest_odds_for_coupon
        coupons = list_coupons(week=week, year=year)
        n_total = 0
        for c in coupons:
            n_total += ingest_odds_for_coupon(c["coupon_id"])

        now_iso = _iso(_now())
        next_odds = _iso(_now() + timedelta(hours=3))
        logger.info("Odds refresh ok — %d fixture(s) updated", n_total)
        patch_state(
            is_running=False, current_job=None,
            last_odds_refresh_at=now_iso,
            last_success=True, last_error=None,
            next_odds_refresh_at=next_odds,
        )
        summary = {"ok": True, "n_fixtures": n_total}
    except Exception as exc:
        logger.exception("Odds refresh failed: %s", exc)
        patch_state(is_running=False, current_job=None,
                    last_success=False, last_error=str(exc)[:300])
        raise
    finally:
        _run_lock.release()
    return summary


def do_daily_sync(*, force: bool = False) -> dict:
    """
    Full daily sync: NT + odds + enrichment + estimated priors.
    Delegates to sync.cmd_daily (safe — no sys.exit in that function).
    """
    state = load_state()
    if state.get("is_running") and not force:
        raise RuntimeError("A sync job is already running")

    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("A sync job is already running")

    summary: dict = {"ok": False}
    try:
        patch_state(is_running=True, current_job="daily_sync")
        week, year = _current_week_year()
        before = _snapshot_public_tips()

        from sync import cmd_daily
        cmd_daily(week, year)

        now_iso = _iso(_now())
        n_changes = _count_tip_changes(before)
        turnover = _get_turnover()
        coupon_ids = _get_active_coupon_ids()

        logger.info("Daily sync complete — %d tip change(s)", n_changes)
        patch_state(
            is_running=False, current_job=None,
            last_nt_refresh_at=now_iso,
            last_odds_refresh_at=now_iso,
            last_full_sync_at=now_iso,
            last_success=True, last_error=None,
            n_public_pct_changes=n_changes,
            turnover=turnover,
            updated_coupon_ids=coupon_ids,
            next_nt_refresh_at=_iso(_now() + timedelta(hours=1)),
            next_odds_refresh_at=_iso(_now() + timedelta(hours=3)),
        )
        summary = {"ok": True, "n_changes": n_changes, "coupon_ids": coupon_ids}
    except Exception as exc:
        logger.exception("Daily sync failed: %s", exc)
        patch_state(is_running=False, current_job=None,
                    last_success=False, last_error=str(exc)[:300])
        raise
    finally:
        _run_lock.release()
    return summary


# ── APScheduler job wrappers (called every 5 min / 3 h) ──────────────────────

def _nt_check_job() -> None:
    """
    Runs every 5 min. Self-throttles based on time-to-deadline and
    last refresh time — skips unless sufficient time has passed.
    """
    state = load_state()
    if state.get("is_running"):
        return

    deadline_secs = _secs_to_earliest_deadline()
    if deadline_secs == float("inf"):
        return

    required = _required_nt_interval(deadline_secs)
    elapsed = _secs_since(state.get("last_nt_refresh_at"))
    if elapsed < required:
        return

    try:
        do_nt_refresh(force=True)
    except Exception:
        pass


def _odds_check_job() -> None:
    """Runs every 3 h. Self-throttles."""
    state = load_state()
    if state.get("is_running"):
        return
    if _secs_since(state.get("last_odds_refresh_at")) < 3 * 3600:
        return
    try:
        do_odds_refresh(force=True)
    except Exception:
        pass


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    from db.schema import init_db
    init_db()

    _scheduler = BackgroundScheduler(
        job_defaults={"misfire_grace_time": 120, "coalesce": True},
        timezone="UTC",
    )
    _scheduler.add_job(_nt_check_job, "interval", minutes=5, id="nt_check")
    _scheduler.add_job(_odds_check_job, "interval", hours=3, id="odds_check")
    _scheduler.start()
    logger.info("Scheduler started — NT check every 5 min (adaptive), odds every 3 h")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
