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
    ("coupons",        "omsetning        REAL"),
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


# Phase 9 — generation-based historical tracking (auto-saved on every optimize call)
_DDL_PHASE9_TABLES = """
CREATE TABLE IF NOT EXISTS coupon_generations (
    generation_id    TEXT    PRIMARY KEY,
    coupon_id        TEXT    NOT NULL REFERENCES coupons(coupon_id),
    strategy         TEXT    NOT NULL CHECK(strategy IN ('safe','balanced','jackpot')),
    budget           REAL    NOT NULL,
    row_count        INTEGER NOT NULL,
    p_win            REAL,
    pvr              REAL,
    n_singles        INTEGER,
    n_halvdekk       INTEGER,
    n_heldekk        INTEGER,
    fixtures_4of4    INTEGER NOT NULL DEFAULT 0,
    fixtures_3of4    INTEGER NOT NULL DEFAULT 0,
    fixtures_2of4    INTEGER NOT NULL DEFAULT 0,
    fixtures_1of4    INTEGER NOT NULL DEFAULT 0,
    fixtures_0of4    INTEGER NOT NULL DEFAULT 0,
    generated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    status           TEXT    NOT NULL DEFAULT 'live'
                     CHECK(status IN ('live','frozen','evaluated')),
    frozen_at        TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gen_unique_day
    ON coupon_generations(coupon_id, strategy, budget, date(generated_at));

CREATE TABLE IF NOT EXISTS generation_picks (
    pick_id                  TEXT    PRIMARY KEY,
    generation_id            TEXT    NOT NULL REFERENCES coupon_generations(generation_id),
    fixture_id               TEXT    NOT NULL REFERENCES fixtures(fixture_id),
    match_number             INTEGER NOT NULL,
    pick                     TEXT    NOT NULL CHECK(pick IN ('H','U','B')),
    coverage_type            TEXT    NOT NULL CHECK(coverage_type IN ('single','half_cover','full_cover')),
    selected_outcomes        TEXT    NOT NULL DEFAULT '[]',
    confidence               REAL    NOT NULL,
    model_prob_h             REAL,
    model_prob_u             REAL,
    model_prob_b             REAL,
    pub_prob_h               REAL,
    pub_prob_u               REAL,
    pub_prob_b               REAL,
    value_h                  REAL,
    value_u                  REAL,
    value_b                  REAL,
    crowd_disagreement_score REAL,
    odds_source              TEXT,
    has_af_data              INTEGER NOT NULL DEFAULT 0,
    UNIQUE (generation_id, match_number)
);

CREATE TABLE IF NOT EXISTS generation_results (
    generation_id     TEXT    PRIMARY KEY REFERENCES coupon_generations(generation_id),
    correct_picks     INTEGER,
    covered_picks     INTEGER,
    all_correct       INTEGER NOT NULL DEFAULT 0,
    evaluation_status TEXT    NOT NULL DEFAULT 'pending'
                      CHECK(evaluation_status IN ('pending','partial','complete')),
    actual_payout_nok REAL,
    evaluated_at      TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_gen_coupon   ON coupon_generations(coupon_id);
CREATE INDEX IF NOT EXISTS idx_gen_strategy ON coupon_generations(strategy);
CREATE INDEX IF NOT EXISTS idx_gp_gen       ON generation_picks(generation_id);
CREATE INDEX IF NOT EXISTS idx_gp_fixture   ON generation_picks(fixture_id);
CREATE INDEX IF NOT EXISTS idx_gr_status    ON generation_results(evaluation_status);
"""


# Phase 9 freeze migration — adds status/frozen_at to existing coupon_generations rows,
# drops the old day-scoped unique index, and creates two partial indexes:
#   1. live records: unique per (coupon, strategy, budget, day)
#   2. frozen/evaluated: unique per (coupon, strategy, budget) — one snapshot per combo
_PHASE9_FREEZE_COLUMNS: list[tuple[str, str]] = [
    ("coupon_generations", "status    TEXT NOT NULL DEFAULT 'live' CHECK(status IN ('live','frozen','evaluated'))"),
    ("coupon_generations", "frozen_at TEXT"),
]

_DDL_PHASE9_FREEZE_INDEXES = """
DROP INDEX IF EXISTS idx_gen_unique_day;
CREATE UNIQUE INDEX IF NOT EXISTS idx_gen_live_day
    ON coupon_generations(coupon_id, strategy, budget, date(generated_at))
    WHERE status = 'live';
CREATE UNIQUE INDEX IF NOT EXISTS idx_gen_frozen_unique
    ON coupon_generations(coupon_id, strategy, budget)
    WHERE status IN ('frozen', 'evaluated');
"""


def _add_phase9_freeze_columns(conn) -> None:
    for table, col_def in _PHASE9_FREEZE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists


# Phase 10 — extended enrichment: logos, points, W/D/L, per-match averages,
# clean sheets, streaks, and AF comparison ratings from /predictions.
_PHASE10_COLUMNS: list[tuple[str, str]] = [
    # From /standings — full table row per team
    ("fixture_stat_enrichment", "home_points   INTEGER"),
    ("fixture_stat_enrichment", "away_points   INTEGER"),
    ("fixture_stat_enrichment", "home_played   INTEGER"),
    ("fixture_stat_enrichment", "away_played   INTEGER"),
    ("fixture_stat_enrichment", "home_wins     INTEGER"),
    ("fixture_stat_enrichment", "home_draws    INTEGER"),
    ("fixture_stat_enrichment", "home_losses   INTEGER"),
    ("fixture_stat_enrichment", "away_wins     INTEGER"),
    ("fixture_stat_enrichment", "away_draws    INTEGER"),
    ("fixture_stat_enrichment", "away_losses   INTEGER"),
    # Team logos — populated from /standings team.logo (fallback: /fixtures teams.logo)
    ("fixture_stat_enrichment", "home_logo_url TEXT"),
    ("fixture_stat_enrichment", "away_logo_url TEXT"),
    # From /teams/statistics — per-match averages
    ("fixture_stat_enrichment", "home_avg_goals_for     REAL"),
    ("fixture_stat_enrichment", "away_avg_goals_for     REAL"),
    ("fixture_stat_enrichment", "home_avg_goals_against REAL"),
    ("fixture_stat_enrichment", "away_avg_goals_against REAL"),
    # From /teams/statistics — clean sheets and streaks
    ("fixture_stat_enrichment", "home_clean_sheets  INTEGER"),
    ("fixture_stat_enrichment", "away_clean_sheets  INTEGER"),
    ("fixture_stat_enrichment", "home_streak_wins   INTEGER"),
    ("fixture_stat_enrichment", "away_streak_wins   INTEGER"),
    ("fixture_stat_enrichment", "home_streak_draws  INTEGER"),
    ("fixture_stat_enrichment", "away_streak_draws  INTEGER"),
    ("fixture_stat_enrichment", "home_streak_losses INTEGER"),
    ("fixture_stat_enrichment", "away_streak_losses INTEGER"),
    # From /predictions comparison — AF pre-computed relative ratings (0.0–1.0)
    ("fixture_stat_enrichment", "api_comparison_att_home   REAL"),
    ("fixture_stat_enrichment", "api_comparison_att_away   REAL"),
    ("fixture_stat_enrichment", "api_comparison_def_home   REAL"),
    ("fixture_stat_enrichment", "api_comparison_def_away   REAL"),
    ("fixture_stat_enrichment", "api_comparison_form_home  REAL"),
    ("fixture_stat_enrichment", "api_comparison_form_away  REAL"),
    ("fixture_stat_enrichment", "api_comparison_total_home REAL"),
    ("fixture_stat_enrichment", "api_comparison_total_away REAL"),
]


def _add_phase10_columns(conn) -> None:
    for table, col_def in _PHASE10_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists


# Phase 11 — recent form matches as JSON (for pip tooltips)
_PHASE11_COLUMNS: list[tuple[str, str]] = [
    ("fixture_stat_enrichment", "home_recent_matches TEXT"),
    ("fixture_stat_enrichment", "away_recent_matches TEXT"),
]


def _add_phase11_columns(conn) -> None:
    for table, col_def in _PHASE11_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists


# Phase 12 — recent fixture statistics aggregated from /fixtures/statistics
# (possession, shots, corners, fouls, cards, pass accuracy, xG per team over last N matches)
_PHASE12_COLUMNS: list[tuple[str, str]] = [
    ("fixture_stat_enrichment", "home_recent_fixture_stats TEXT"),
    ("fixture_stat_enrichment", "away_recent_fixture_stats TEXT"),
]


def _add_phase12_columns(conn) -> None:
    for table, col_def in _PHASE12_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists


# Phase 13 — league size + venue-specific goal averages / clean sheets
_PHASE13_COLUMNS: list[tuple[str, str]] = [
    ("fixture_stat_enrichment", "league_size INTEGER"),
    ("fixture_stat_enrichment", "home_avg_goals_for_home REAL"),
    ("fixture_stat_enrichment", "home_avg_goals_against_home REAL"),
    ("fixture_stat_enrichment", "away_avg_goals_for_away REAL"),
    ("fixture_stat_enrichment", "away_avg_goals_against_away REAL"),
    ("fixture_stat_enrichment", "home_clean_sheets_home INTEGER"),
    ("fixture_stat_enrichment", "away_clean_sheets_away INTEGER"),
]


def _add_phase13_columns(conn) -> None:
    for table, col_def in _PHASE13_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists


# Phase 14 — Oddstips: multi-market odds storage + paper bet tracking
# odds_markets uses a row-per-selection design:
#   one row per (fixture_id, market_key, selection)
#   market_key: "1X2" | "BTTS" | "OVER_UNDER"
#   selection:  "HOME"/"DRAW"/"AWAY" | "YES"/"NO" | "OVER"/"UNDER"
#   line:       2.5 for OVER_UNDER, NULL otherwise
_DDL_PHASE14_TABLES = """
CREATE TABLE IF NOT EXISTS odds_markets (
    id              TEXT PRIMARY KEY,
    fixture_id      TEXT NOT NULL REFERENCES fixtures(fixture_id),
    af_fixture_id   INTEGER,
    bookmaker       TEXT NOT NULL,
    market_name     TEXT NOT NULL,
    market_key      TEXT NOT NULL,
    selection       TEXT NOT NULL,
    line            REAL,
    odds            REAL NOT NULL,
    source          TEXT NOT NULL DEFAULT 'api_football',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(fixture_id, market_key, selection)
);

CREATE TABLE IF NOT EXISTS model_bets (
    id              TEXT PRIMARY KEY,
    coupon_id       TEXT,
    fixture_id      TEXT NOT NULL REFERENCES fixtures(fixture_id),
    match_name      TEXT NOT NULL,
    league          TEXT,
    kickoff_utc     TEXT,
    market          TEXT NOT NULL DEFAULT '1x2',
    outcome         TEXT NOT NULL,
    bookmaker       TEXT NOT NULL,
    ref_odds        REAL NOT NULL,
    implied_prob    REAL NOT NULL,
    model_prob      REAL NOT NULL,
    edge_pp         REAL NOT NULL,
    stake_nok       REAL NOT NULL,
    expected_value  REAL NOT NULL,
    insight_type    TEXT,
    risk_level      TEXT NOT NULL DEFAULT 'medium',
    reason          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','won','lost','void')),
    result_outcome  TEXT,
    closing_odds    REAL,
    clv             REAL,
    profit_nok      REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    settled_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_odds_markets_fixture    ON odds_markets(fixture_id, market_key);
CREATE INDEX IF NOT EXISTS idx_odds_markets_market_key ON odds_markets(market_key);
CREATE INDEX IF NOT EXISTS idx_model_bets_fixture   ON model_bets(fixture_id);
CREATE INDEX IF NOT EXISTS idx_model_bets_status    ON model_bets(status);
CREATE INDEX IF NOT EXISTS idx_model_bets_created   ON model_bets(created_at);
CREATE INDEX IF NOT EXISTS idx_model_bets_coupon    ON model_bets(coupon_id);
"""


_DDL_PREDICTIONS = """
CREATE TABLE IF NOT EXISTS api_football_predictions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id                  TEXT NOT NULL REFERENCES fixtures(fixture_id),
    af_fixture_id               INTEGER NOT NULL,
    prediction_winner_id        INTEGER,
    prediction_winner_name      TEXT,
    prediction_winner_comment   TEXT,
    prediction_win_or_draw      INTEGER,
    prediction_under_over       TEXT,
    prediction_goals_home       REAL,
    prediction_goals_away       REAL,
    advice                      TEXT,
    percent_home                TEXT,
    percent_draw                TEXT,
    percent_away                TEXT,
    comparison_json             TEXT,
    raw_json                    TEXT,
    fetched_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(fixture_id)
);
CREATE INDEX IF NOT EXISTS idx_af_predictions_fixture ON api_football_predictions(fixture_id);
CREATE INDEX IF NOT EXISTS idx_af_predictions_af_id   ON api_football_predictions(af_fixture_id);
"""


def _migrate_phase14_odds_markets(conn) -> None:
    """
    Drop odds_markets if it has the old row-per-market schema (odds_a column).
    The new schema is row-per-selection — incompatible, but the table was always empty.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(odds_markets)").fetchall()]
    if cols and "odds_a" in cols:
        conn.execute("DROP TABLE IF EXISTS odds_markets")
        conn.execute("DROP INDEX IF EXISTS idx_odds_markets_fixture")


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
        conn.executescript(_DDL_PHASE9_TABLES)
        _add_phase9_freeze_columns(conn)
        conn.executescript(_DDL_PHASE9_FREEZE_INDEXES)
        _add_phase10_columns(conn)
        _add_phase11_columns(conn)
        _add_phase12_columns(conn)
        _add_phase13_columns(conn)
        _migrate_phase14_odds_markets(conn)
        conn.executescript(_DDL_PHASE14_TABLES)
        conn.executescript(_DDL_PREDICTIONS)
