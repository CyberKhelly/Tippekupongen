"""
Lightweight sync state — persisted to data/sync_state.json.
Thread-safe via a module-level lock; safe to call from APScheduler threads
and FastAPI async handlers simultaneously.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

_STATE_FILE = Path("data") / "sync_state.json"
_lock = threading.Lock()

_DEFAULT: dict = {
    "last_nt_refresh_at": None,
    "last_odds_refresh_at": None,
    "last_full_sync_at": None,
    "is_running": False,
    "current_job": None,
    "last_success": None,
    "last_error": None,
    "next_nt_refresh_at": None,
    "next_odds_refresh_at": None,
    "updated_coupon_ids": [],
    "n_public_pct_changes": 0,
    "turnover": {},
}


def load_state() -> dict:
    with _lock:
        if not _STATE_FILE.exists():
            return dict(_DEFAULT)
        try:
            return json.loads(_STATE_FILE.read_text("utf-8"))
        except Exception:
            return dict(_DEFAULT)


def patch_state(**kwargs) -> dict:
    """Update specific fields atomically, leaving other fields untouched."""
    with _lock:
        if _STATE_FILE.exists():
            try:
                state = json.loads(_STATE_FILE.read_text("utf-8"))
            except Exception:
                state = dict(_DEFAULT)
        else:
            state = dict(_DEFAULT)
        state.update(kwargs)
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), "utf-8")
        tmp.replace(_STATE_FILE)
    return state
