from db.connection import get_conn

# Base schema — tables that exist from the start.
_DDL_BASE = """
CREATE TABLE IF NOT EXISTS teams (
    team_id        TEXT PRIMARY KEY,
    external_id    INTEGER,
    name_canonical TEXT NOT NULL,
    name_local     TEXT,
    gender         TEXT NOT NULL CHECK(gender IN ('men','women')),
    age_group      TEXT NOT NULL DEFAULT 'senior',
    team_type      TEXT NOT NULL CHECK(team_type IN ('national','club')),
    country_iso    TEXT NOT NULL,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS competitions (
    competition_id TEXT PRIMARY KEY,
    external_id    INTEGER,
    name_canonical TEXT NOT NULL,
    gender         TEXT NOT NULL CHECK(gender IN ('men','women')),
    age_group      TEXT NOT NULL DEFAULT 'senior',
    country_iso    TEXT,
    confederation  TEXT,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fixtures (
    fixture_id     TEXT PRIMARY KEY,
    home_team_id   TEXT REFERENCES teams(team_id),
    away_team_id   TEXT REFERENCES teams(team_id),
    competition_id TEXT REFERENCES competitions(competition_id),
    kickoff_utc    TEXT NOT NULL,
    matchday       INTEGER,
    venue          TEXT,
    external_id    INTEGER UNIQUE,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS odds (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id),
    source     TEXT NOT NULL,
    odds_h     REAL NOT NULL,
    odds_u     REAL NOT NULL,
    odds_b     REAL NOT NULL,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coupons (
    coupon_id    TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    deadline_utc TEXT NOT NULL,
    week         INTEGER,
    year         INTEGER,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coupon_fixtures (
    coupon_id    TEXT NOT NULL REFERENCES coupons(coupon_id),
    fixture_id   TEXT NOT NULL REFERENCES fixtures(fixture_id),
    match_number INTEGER NOT NULL,
    PRIMARY KEY (coupon_id, fixture_id)
);

CREATE INDEX IF NOT EXISTS idx_odds_fixture   ON odds(fixture_id, source, fetched_at);
CREATE INDEX IF NOT EXISTS idx_fixtures_ko    ON fixtures(kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_cf_coupon      ON coupon_fixtures(coupon_id);
CREATE INDEX IF NOT EXISTS idx_coupons_week   ON coupons(week, year);
"""

# New tables added in Phase 1 — idempotent via IF NOT EXISTS.
_DDL_PHASE1_TABLES = """
CREATE TABLE IF NOT EXISTS team_aliases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id    TEXT NOT NULL REFERENCES teams(team_id),
    alias      TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    source     TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(alias_norm, source)
);

CREATE TABLE IF NOT EXISTS coupon_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id TEXT NOT NULL,
    event     TEXT NOT NULL,
    detail    TEXT,
    logged_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_aliases_norm ON team_aliases(alias_norm);
"""

# Columns added in Phase 1.  ALTER TABLE silently skips if column exists.
_PHASE1_COLUMNS: list[tuple[str, str]] = [
    # (table, column_definition)
    ("teams",          "nt_team_id       TEXT"),
    ("teams",          "betradar_id      INTEGER"),
    ("fixtures",       "nt_match_id      TEXT"),
    ("fixtures",       "betradar_match_id INTEGER"),
    ("fixtures",       "arrangement_name TEXT"),
    ("fixtures",       "source           TEXT"),
    ("fixtures",       "confidence       TEXT"),
    ("coupons",        "nt_game_day_id   TEXT"),
    ("coupons",        "day_type         TEXT"),
    ("coupons",        "source           TEXT"),
    ("coupons",        "confidence       TEXT"),
    ("coupons",        "content_hash     TEXT"),
    ("coupons",        "last_synced_at   TEXT"),
    ("coupons",        "updated_at       TEXT"),
    # Tips percentages — stored separately from odds; never used as probability baseline.
    ("coupon_fixtures", "arrangement_name TEXT"),
    ("coupon_fixtures", "expert_h         REAL"),
    ("coupon_fixtures", "expert_u         REAL"),
    ("coupon_fixtures", "expert_b         REAL"),
    ("coupon_fixtures", "public_h         REAL"),
    ("coupon_fixtures", "public_u         REAL"),
    ("coupon_fixtures", "public_b         REAL"),
]

_PHASE1_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_teams_nt       ON teams(nt_team_id)       WHERE nt_team_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_teams_br       ON teams(betradar_id)      WHERE betradar_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_fixtures_nt    ON fixtures(nt_match_id)   WHERE nt_match_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_fixtures_br    ON fixtures(betradar_match_id) WHERE betradar_match_id IS NOT NULL;
"""


def _add_columns(conn) -> None:
    """Add new columns to existing tables, skipping any that already exist."""
    for table, col_def in _PHASE1_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists — safe to ignore


# Phase 2 tables — history, predictions, evaluations
_DDL_PHASE2_TABLES = """
CREATE TABLE IF NOT EXISTS match_results (
    result_id     TEXT PRIMARY KEY,
    fixture_id    TEXT NOT NULL REFERENCES fixtures(fixture_id),
    home_score    INTEGER NOT NULL,
    away_score    INTEGER NOT NULL,
    result_1x2    TEXT NOT NULL CHECK(result_1x2 IN ('H','U','B')),
    result_source TEXT NOT NULL DEFAULT 'manual',
    final_status  TEXT NOT NULL DEFAULT 'confirmed'
                  CHECK(final_status IN ('confirmed','pending','abandoned')),
    updated_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(fixture_id)
);

CREATE TABLE IF NOT EXISTS coupon_predictions (
    prediction_id     TEXT PRIMARY KEY,
    coupon_id         TEXT NOT NULL REFERENCES coupons(coupon_id),
    fixture_id        TEXT NOT NULL REFERENCES fixtures(fixture_id),
    match_number      INTEGER NOT NULL,
    recommended_pick  TEXT NOT NULL,
    coverage_type     TEXT NOT NULL
                      CHECK(coverage_type IN ('single','half_cover','full_cover')),
    selected_outcomes TEXT NOT NULL,
    confidence        REAL NOT NULL,
    implied_prob_h    REAL NOT NULL,
    implied_prob_u    REAL NOT NULL,
    implied_prob_b    REAL NOT NULL,
    odds_h            REAL,
    odds_u            REAL,
    odds_b            REAL,
    odds_source       TEXT,
    model_version     TEXT NOT NULL DEFAULT 'v1',
    created_at        TEXT DEFAULT (datetime('now')),
    UNIQUE(coupon_id, fixture_id)
);

CREATE TABLE IF NOT EXISTS coupon_evaluations (
    evaluation_id     TEXT PRIMARY KEY,
    coupon_id         TEXT NOT NULL REFERENCES coupons(coupon_id) UNIQUE,
    total_rows        INTEGER NOT NULL,
    stake_nok         REAL NOT NULL,
    total_fixtures    INTEGER NOT NULL DEFAULT 12,
    correct_picks     INTEGER,
    system_covered    INTEGER,
    all_12_correct    INTEGER,
    hit_rate          REAL,
    cover_rate        REAL,
    evaluation_status TEXT NOT NULL
                      CHECK(evaluation_status IN ('pending','partial','complete')),
    evaluated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_predictions_coupon  ON coupon_predictions(coupon_id);
CREATE INDEX IF NOT EXISTS idx_predictions_fixture ON coupon_predictions(fixture_id);
CREATE INDEX IF NOT EXISTS idx_results_fixture     ON match_results(fixture_id);
"""


# Phase 3 — odds movement and CLV tracking
_DDL_PHASE3_TABLES = """
CREATE TABLE IF NOT EXISTS odds_snapshots (
    snapshot_id        TEXT PRIMARY KEY,
    fixture_id         TEXT NOT NULL REFERENCES fixtures(fixture_id),
    bookmaker          TEXT NOT NULL,
    market             TEXT NOT NULL DEFAULT 'h2h',
    odds_h             REAL NOT NULL,
    odds_u             REAL NOT NULL,
    odds_b             REAL NOT NULL,
    implied_prob_h     REAL NOT NULL,
    implied_prob_u     REAL NOT NULL,
    implied_prob_b     REAL NOT NULL,
    fetched_at         TEXT NOT NULL,
    source             TEXT NOT NULL,
    is_closing_snapshot INTEGER NOT NULL DEFAULT 0,
    UNIQUE(fixture_id, bookmaker, market, fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_fixture ON odds_snapshots(fixture_id, bookmaker, market);
CREATE INDEX IF NOT EXISTS idx_snapshots_time    ON odds_snapshots(fixture_id, fetched_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_closing ON odds_snapshots(fixture_id, bookmaker, is_closing_snapshot);
"""


# Phase 4B — API-Football enrichment
_DDL_PHASE4B_TABLES = """
CREATE TABLE IF NOT EXISTS api_football_fixture_links (
    fixture_id                TEXT PRIMARY KEY REFERENCES fixtures(fixture_id),
    api_football_fixture_id   INTEGER NOT NULL,
    api_football_league_id    INTEGER NOT NULL,
    api_football_season       INTEGER NOT NULL,
    api_football_home_team_id INTEGER,
    api_football_away_team_id INTEGER,
    match_confidence          REAL NOT NULL,
    matched_at                TEXT DEFAULT (datetime('now')),
    UNIQUE(api_football_fixture_id)
);

CREATE TABLE IF NOT EXISTS fixture_stat_enrichment (
    fixture_id              TEXT PRIMARY KEY REFERENCES fixtures(fixture_id),
    has_api_football_data   INTEGER NOT NULL DEFAULT 0,
    api_football_fixture_id INTEGER,
    api_football_league_id  INTEGER,
    api_football_season     INTEGER,
    league_name             TEXT,
    home_position           INTEGER,
    away_position           INTEGER,
    home_form               TEXT,
    away_form               TEXT,
    home_last_5             TEXT,
    away_last_5             TEXT,
    home_last_10            TEXT,
    away_last_10            TEXT,
    home_home_record        TEXT,
    away_away_record        TEXT,
    home_goals_for          INTEGER,
    home_goals_against      INTEGER,
    away_goals_for          INTEGER,
    away_goals_against      INTEGER,
    api_prediction_home     REAL,
    api_prediction_draw     REAL,
    api_prediction_away     REAL,
    api_prediction_advice   TEXT,
    updated_at              TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_af_links_af_fixture ON api_football_fixture_links(api_football_fixture_id);
CREATE INDEX IF NOT EXISTS idx_enrichment_updated  ON fixture_stat_enrichment(updated_at);
"""


# Phase 5 — unified prediction engine model output cache
_DDL_PHASE5_TABLES = """
CREATE TABLE IF NOT EXISTS fixture_model_output (
    fixture_id               TEXT PRIMARY KEY REFERENCES fixtures(fixture_id),
    model_version            TEXT NOT NULL DEFAULT 'v5',
    -- Final model output
    prob_h                   REAL NOT NULL,
    prob_u                   REAL NOT NULL,
    prob_b                   REAL NOT NULL,
    confidence               REAL NOT NULL,
    recommendation           TEXT NOT NULL,
    -- Bookmaker prior (audit)
    bm_prob_h                REAL NOT NULL,
    bm_prob_u                REAL NOT NULL,
    bm_prob_b                REAL NOT NULL,
    -- Stats adjustment audit
    home_edge                REAL,
    stats_adj_pp             REAL,
    stats_signals            TEXT,    -- JSON array of signal names
    has_af_data              INTEGER NOT NULL DEFAULT 0,
    -- Expert adjustment audit
    expert_adj_h             REAL,
    expert_adj_u             REAL,
    expert_adj_b             REAL,
    has_expert_tips          INTEGER NOT NULL DEFAULT 0,
    -- Public / crowd signals
    pub_prob_h               REAL,
    pub_prob_u               REAL,
    pub_prob_b               REAL,
    value_h                  REAL,
    value_u                  REAL,
    value_b                  REAL,
    crowd_disagreement_score REAL,
    crowd_pressure_pick      TEXT,
    has_public_tips          INTEGER NOT NULL DEFAULT 0,
    computed_at              TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_model_output_computed ON fixture_model_output(computed_at);
"""


# Model-estimated priors — for fixtures with no bookmaker odds.
# NOT used for CLV. NOT a bookmaker source.
_DDL_ESTIMATED_PRIOR = """
CREATE TABLE IF NOT EXISTS fixture_estimated_prior (
    fixture_id   TEXT PRIMARY KEY REFERENCES fixtures(fixture_id),
    estimated_h  REAL NOT NULL,
    estimated_u  REAL NOT NULL,
    estimated_b  REAL NOT NULL,
    signals_used TEXT,           -- JSON array e.g. ["form","standings","nt_expert"]
    confidence   REAL,           -- 0.0–1.0
    source       TEXT NOT NULL DEFAULT 'model_estimated',
    computed_at  TEXT DEFAULT (datetime('now'))
);
"""


# Phase 8 — automated evaluation pipeline
_DDL_PHASE8_TABLES = """
CREATE TABLE IF NOT EXISTS coupon_save_snapshot (
    snapshot_id  TEXT PRIMARY KEY,
    coupon_id    TEXT NOT NULL REFERENCES coupons(coupon_id),
    strategy     TEXT NOT NULL,
    budget_nok   REAL NOT NULL,
    total_rows   INTEGER NOT NULL,
    p_win        REAL,
    pvr          REAL,
    saved_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(coupon_id)
);

CREATE TABLE IF NOT EXISTS pick_evaluations (
    pick_eval_id  TEXT PRIMARY KEY,
    coupon_id     TEXT NOT NULL REFERENCES coupons(coupon_id),
    fixture_id    TEXT NOT NULL REFERENCES fixtures(fixture_id),
    match_number  INTEGER NOT NULL,
    result_1x2    TEXT CHECK(result_1x2 IN ('H','U','B')),
    covered       INTEGER,
    model_correct INTEGER,
    nt_correct    INTEGER,
    cds           REAL,
    cds_bucket    TEXT,
    value_rec     REAL,
    vi_bucket     TEXT,
    edge_pp       REAL,
    edge_bucket   TEXT,
    coverage_type TEXT,
    is_conviction INTEGER,
    evaluated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(coupon_id, fixture_id)
);

CREATE INDEX IF NOT EXISTS idx_pick_evals_coupon  ON pick_evaluations(coupon_id);
CREATE INDEX IF NOT EXISTS idx_pick_evals_fixture ON pick_evaluations(fixture_id);
CREATE INDEX IF NOT EXISTS idx_snap_coupon        ON coupon_save_snapshot(coupon_id);
"""

# New columns added in Phase 8 — idempotent via try/except.
_PHASE8_COLUMNS: list[tuple[str, str]] = [
    # Crowd signal snapshot frozen at prediction-save time
    ("coupon_predictions", "pub_prob_h               REAL"),
    ("coupon_predictions", "pub_prob_u               REAL"),
    ("coupon_predictions", "pub_prob_b               REAL"),
    ("coupon_predictions", "value_h                  REAL"),
    ("coupon_predictions", "value_u                  REAL"),
    ("coupon_predictions", "value_b                  REAL"),
    ("coupon_predictions", "crowd_disagreement_score REAL"),
    # Extended aggregate evaluation
    ("coupon_evaluations", "strategy                 TEXT"),
    ("coupon_evaluations", "budget_nok               REAL"),
    ("coupon_evaluations", "pvr_at_save              REAL"),
    ("coupon_evaluations", "p_win_at_save            REAL"),
    ("coupon_evaluations", "n_nt_correct             INTEGER"),
    ("coupon_evaluations", "nt_hit_rate              REAL"),
    ("coupon_evaluations", "actual_payout_nok        REAL"),
    ("coupon_evaluations", "n_matches_evaluated      INTEGER"),
]


def _add_phase8_columns(conn) -> None:
    for table, col_def in _PHASE8_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_DDL_BASE)
        conn.executescript(_DDL_PHASE1_TABLES)
        _add_columns(conn)
        conn.executescript(_PHASE1_INDEXES)
        conn.executescript(_DDL_PHASE2_TABLES)
        conn.executescript(_DDL_PHASE3_TABLES)
        conn.executescript(_DDL_PHASE4B_TABLES)
        conn.executescript(_DDL_PHASE5_TABLES)
        conn.executescript(_DDL_ESTIMATED_PRIOR)
        conn.executescript(_DDL_PHASE8_TABLES)
        _add_phase8_columns(conn)
