import unicodedata
from db.connection import get_conn


# ── Name normalization ──────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace. Used for alias matching."""
    nfkd = unicodedata.normalize("NFKD", name.lower().strip())
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_only.split())


# ── Teams ───────────────────────────────────────────────────────────────────────

def upsert_team(
    team_id: str,
    name_canonical: str,
    gender: str,
    age_group: str,
    team_type: str,
    country_iso: str,
    name_local: str = "",
    external_id: int | None = None,
    nt_team_id: str | None = None,
    betradar_id: int | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO teams
                (team_id, external_id, name_canonical, name_local,
                 gender, age_group, team_type, country_iso,
                 nt_team_id, betradar_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                external_id    = COALESCE(excluded.external_id,  external_id),
                name_canonical = excluded.name_canonical,
                name_local     = COALESCE(excluded.name_local,   name_local),
                nt_team_id     = COALESCE(excluded.nt_team_id,   nt_team_id),
                betradar_id    = COALESCE(excluded.betradar_id,  betradar_id)
            """,
            (team_id, external_id, name_canonical, name_local or "",
             gender, age_group, team_type, country_iso,
             nt_team_id, betradar_id),
        )


def find_team_by_nt_id(nt_team_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM teams WHERE nt_team_id = ?", (nt_team_id,)
        ).fetchone()
    return dict(row) if row else None


def find_team_by_external_id(external_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM teams WHERE external_id = ?", (external_id,)
        ).fetchone()
    return dict(row) if row else None


def find_team_by_alias(name: str) -> dict | None:
    """Look up a team by any stored alias (exact normalized match)."""
    norm = normalize_name(name)
    with get_conn() as conn:
        row = conn.execute(
            """SELECT t.* FROM team_aliases a
               JOIN teams t ON t.team_id = a.team_id
               WHERE a.alias_norm = ?
               LIMIT 1""",
            (norm,),
        ).fetchone()
    return dict(row) if row else None


def get_team(team_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM teams WHERE team_id = ?", (team_id,)
        ).fetchone()
    return dict(row) if row else None


def get_competition(competition_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM competitions WHERE competition_id = ?", (competition_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Aliases ─────────────────────────────────────────────────────────────────────

def upsert_alias(team_id: str, alias: str, source: str) -> None:
    """Store a name variant for a team. Safe to call repeatedly."""
    norm = normalize_name(alias)
    if not norm:
        return
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO team_aliases (team_id, alias, alias_norm, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(alias_norm, source) DO UPDATE SET team_id = excluded.team_id""",
            (team_id, alias, norm, source),
        )


# ── Competitions ────────────────────────────────────────────────────────────────

def upsert_competition(
    competition_id: str,
    name_canonical: str,
    gender: str,
    age_group: str = "senior",
    country_iso: str | None = None,
    confederation: str | None = None,
    external_id: int | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO competitions
                (competition_id, external_id, name_canonical,
                 gender, age_group, country_iso, confederation)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(competition_id) DO UPDATE SET
                external_id    = COALESCE(excluded.external_id, external_id),
                name_canonical = excluded.name_canonical
            """,
            (competition_id, external_id, name_canonical,
             gender, age_group, country_iso, confederation),
        )
