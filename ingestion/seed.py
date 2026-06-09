"""
Seed the database from existing flat-file coupon data.

Converts data/*.py coupon modules into the SQLite schema.
Run once per week, or re-run to update — fully idempotent.

Usage:
    python sync.py                        # seeds current week automatically
    python sync.py --seed-only            # seeds only, no API calls
"""
import importlib

from db.schema import init_db
from db.registry import upsert_team, upsert_competition
from db.coupon import upsert_coupon, upsert_fixture, upsert_odds, add_coupon_fixture


# ── Team registry ───────────────────────────────────────────────────────────────
# Maps Norwegian display names (as used in data files) to canonical slugs.
# gender + age_group + team_type are EXPLICIT — never inferred from name strings.
# Add new teams here when new coupon data files are created.

TEAM_REGISTRY: dict[str, dict] = {
    # International men's senior national teams
    "Deutschland":     dict(team_id="ger-m-senior",  name="Germany",             gender="men", age_group="senior", team_type="national", country_iso="DE"),
    "Norge":           dict(team_id="nor-m-senior",  name="Norway",              gender="men", age_group="senior", team_type="national", country_iso="NO"),
    "Østerrike":       dict(team_id="aut-m-senior",  name="Austria",             gender="men", age_group="senior", team_type="national", country_iso="AT"),
    "Slovenia":        dict(team_id="svn-m-senior",  name="Slovenia",            gender="men", age_group="senior", team_type="national", country_iso="SI"),
    "Polen":           dict(team_id="pol-m-senior",  name="Poland",              gender="men", age_group="senior", team_type="national", country_iso="PL"),
    "Frankrike":       dict(team_id="fra-m-senior",  name="France",              gender="men", age_group="senior", team_type="national", country_iso="FR"),
    "Ukraina":         dict(team_id="ukr-m-senior",  name="Ukraine",             gender="men", age_group="senior", team_type="national", country_iso="UA"),
    "Island":          dict(team_id="isl-m-senior",  name="Iceland",             gender="men", age_group="senior", team_type="national", country_iso="IS"),
    "Skottland":       dict(team_id="sco-m-senior",  name="Scotland",            gender="men", age_group="senior", team_type="national", country_iso="GB-SCT"),
    "Israel":          dict(team_id="isr-m-senior",  name="Israel",              gender="men", age_group="senior", team_type="national", country_iso="IL"),
    "Italia":          dict(team_id="ita-m-senior",  name="Italy",               gender="men", age_group="senior", team_type="national", country_iso="IT"),
    "Serbia":          dict(team_id="srb-m-senior",  name="Serbia",              gender="men", age_group="senior", team_type="national", country_iso="RS"),
    "Tyrkia":          dict(team_id="tur-m-senior",  name="Turkey",              gender="men", age_group="senior", team_type="national", country_iso="TR"),
    "Nord-Irland":     dict(team_id="nir-m-senior",  name="Northern Ireland",    gender="men", age_group="senior", team_type="national", country_iso="GB-NIR"),
    "Danmark":         dict(team_id="den-m-senior",  name="Denmark",             gender="men", age_group="senior", team_type="national", country_iso="DK"),
    "Sverige":         dict(team_id="swe-m-senior",  name="Sweden",              gender="men", age_group="senior", team_type="national", country_iso="SE"),
    "Irland":          dict(team_id="irl-m-senior",  name="Ireland",             gender="men", age_group="senior", team_type="national", country_iso="IE"),
    "Nederland":       dict(team_id="ned-m-senior",  name="Netherlands",         gender="men", age_group="senior", team_type="national", country_iso="NL"),
    "Spania":          dict(team_id="esp-m-senior",  name="Spain",               gender="men", age_group="senior", team_type="national", country_iso="ES"),
    "England":         dict(team_id="eng-m-senior",  name="England",             gender="men", age_group="senior", team_type="national", country_iso="GB-ENG"),
    "Belgia":          dict(team_id="bel-m-senior",  name="Belgium",             gender="men", age_group="senior", team_type="national", country_iso="BE"),
    "Tunisia":         dict(team_id="tun-m-senior",  name="Tunisia",             gender="men", age_group="senior", team_type="national", country_iso="TN"),
    "Portugal":        dict(team_id="por-m-senior",  name="Portugal",            gender="men", age_group="senior", team_type="national", country_iso="PT"),
    "Chile":           dict(team_id="chi-m-senior",  name="Chile",               gender="men", age_group="senior", team_type="national", country_iso="CL"),
    "Romania":         dict(team_id="rou-m-senior",  name="Romania",             gender="men", age_group="senior", team_type="national", country_iso="RO"),
    "Wales":           dict(team_id="wal-m-senior",  name="Wales",               gender="men", age_group="senior", team_type="national", country_iso="GB-WLS"),
    "Albania":         dict(team_id="alb-m-senior",  name="Albania",             gender="men", age_group="senior", team_type="national", country_iso="AL"),
    "Luxemburg":       dict(team_id="lux-m-senior",  name="Luxembourg",          gender="men", age_group="senior", team_type="national", country_iso="LU"),
    "USA":             dict(team_id="usa-m-senior",  name="USA",                 gender="men", age_group="senior", team_type="national", country_iso="US"),
    "Panama":          dict(team_id="pan-m-senior",  name="Panama",              gender="men", age_group="senior", team_type="national", country_iso="PA"),
    "Bosnia-Herz.":    dict(team_id="bih-m-senior",  name="Bosnia & Herzegovina",gender="men", age_group="senior", team_type="national", country_iso="BA"),
    "Sveits":          dict(team_id="sui-m-senior",  name="Switzerland",         gender="men", age_group="senior", team_type="national", country_iso="CH"),
    "Australia":       dict(team_id="aus-m-senior",  name="Australia",           gender="men", age_group="senior", team_type="national", country_iso="AU"),
    "Bolivia":         dict(team_id="bol-m-senior",  name="Bolivia",             gender="men", age_group="senior", team_type="national", country_iso="BO"),
    "New Zealand":     dict(team_id="nzl-m-senior",  name="New Zealand",         gender="men", age_group="senior", team_type="national", country_iso="NZ"),
    "Qatar":           dict(team_id="qat-m-senior",  name="Qatar",               gender="men", age_group="senior", team_type="national", country_iso="QA"),
    "El Salvador":     dict(team_id="slv-m-senior",  name="El Salvador",         gender="men", age_group="senior", team_type="national", country_iso="SV"),
    "Brasil":          dict(team_id="bra-m-senior",  name="Brazil",              gender="men", age_group="senior", team_type="national", country_iso="BR"),
    "Egypt":           dict(team_id="egy-m-senior",  name="Egypt",               gender="men", age_group="senior", team_type="national", country_iso="EG"),
    "Argentina":       dict(team_id="arg-m-senior",  name="Argentina",           gender="men", age_group="senior", team_type="national", country_iso="AR"),
    "Honduras":        dict(team_id="hon-m-senior",  name="Honduras",            gender="men", age_group="senior", team_type="national", country_iso="HN"),
    "Marokko":         dict(team_id="mar-m-senior",  name="Morocco",             gender="men", age_group="senior", team_type="national", country_iso="MA"),
    "Kroatia":         dict(team_id="cro-m-senior",  name="Croatia",             gender="men", age_group="senior", team_type="national", country_iso="HR"),
    "Hellas":          dict(team_id="gre-m-senior",  name="Greece",              gender="men", age_group="senior", team_type="national", country_iso="GR"),
    "Ecuador":         dict(team_id="ecu-m-senior",  name="Ecuador",             gender="men", age_group="senior", team_type="national", country_iso="EC"),
    "Guatemala":       dict(team_id="gtm-m-senior",  name="Guatemala",           gender="men", age_group="senior", team_type="national", country_iso="GT"),
    "Colombia":        dict(team_id="col-m-senior",  name="Colombia",            gender="men", age_group="senior", team_type="national", country_iso="CO"),
    "Jordan":          dict(team_id="jor-m-senior",  name="Jordan",              gender="men", age_group="senior", team_type="national", country_iso="JO"),
    # Norwegian clubs (lower league)
    "Varhaug":         dict(team_id="varhaug-m-senior",         name="Varhaug",         gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Hinna":           dict(team_id="hinna-m-senior",           name="Hinna",           gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Salangen":        dict(team_id="salangen-m-senior",        name="Salangen",        gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Ulfstind":        dict(team_id="ulfstind-m-senior",        name="Ulfstind",        gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Ranheim":         dict(team_id="ranheim-m-senior",         name="Ranheim",         gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Strømmen":        dict(team_id="strommen-m-senior",        name="Strømmen",        gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Rosseland":       dict(team_id="rosseland-m-senior",       name="Rosseland",       gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Staal Jørpeland": dict(team_id="staal-jorpeland-m-senior", name="Staal Jørpeland", gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Stryn":           dict(team_id="stryn-m-senior",           name="Stryn",           gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Florø":           dict(team_id="floro-m-senior",           name="Florø",           gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Ready":           dict(team_id="ready-m-senior",           name="Ready",           gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Union C. Berner": dict(team_id="union-berner-m-senior",    name="Union C. Berner", gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Frøya":           dict(team_id="froya-m-senior",           name="Frøya",           gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Gneist":          dict(team_id="gneist-m-senior",          name="Gneist",          gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Stordal":         dict(team_id="stordal-m-senior",         name="Stordal",         gender="men", age_group="senior", team_type="club", country_iso="NO"),
    "Langevåg":        dict(team_id="langevag-m-senior",        name="Langevåg",        gender="men", age_group="senior", team_type="club", country_iso="NO"),
}

COMPETITION_REGISTRY: dict[str, dict] = {
    "international-friendly-m": dict(
        name="International Friendly",
        gender="men",
        age_group="senior",
        country_iso=None,
        confederation=None,
    ),
    "nff-lower-m": dict(
        name="NFF Lower Divisions",
        gender="men",
        age_group="senior",
        country_iso="NO",
        confederation="UEFA",
    ),
}

_CLUB_IDS = {meta["team_id"] for meta in TEAM_REGISTRY.values() if meta["team_type"] == "club"}


def _resolve_team_id(name_local: str) -> str:
    entry = TEAM_REGISTRY.get(name_local)
    if entry is None:
        raise KeyError(
            f"Unknown team: {name_local!r}\n"
            f"Add it to TEAM_REGISTRY in ingestion/seed.py"
        )
    return entry["team_id"]


def _resolve_competition(home_id: str, away_id: str) -> str:
    if home_id in _CLUB_IDS or away_id in _CLUB_IDS:
        return "nff-lower-m"
    return "international-friendly-m"


def seed_from_flat_file(module_path: str, week: int, year: int) -> None:
    """
    Load a data/*.py coupon module and insert all data into SQLite.
    Idempotent — safe to re-run.

    Args:
        module_path: Python import path, e.g. "data.coupon_week23_2026"
        week:        ISO week number
        year:        Calendar year
    """
    init_db()

    from db.registry import upsert_alias

    # Sync team and competition registries first; seed aliases for both
    # Norwegian display names and canonical English names.
    for name_local, meta in TEAM_REGISTRY.items():
        upsert_team(
            team_id=meta["team_id"],
            name_canonical=meta["name"],
            name_local=name_local,
            gender=meta["gender"],
            age_group=meta["age_group"],
            team_type=meta["team_type"],
            country_iso=meta["country_iso"],
        )
        upsert_alias(meta["team_id"], name_local,   "nt")
        upsert_alias(meta["team_id"], meta["name"], "manual")

    for comp_id, meta in COMPETITION_REGISTRY.items():
        upsert_competition(
            competition_id=comp_id,
            name_canonical=meta["name"],
            gender=meta["gender"],
            age_group=meta["age_group"],
            country_iso=meta["country_iso"],
            confederation=meta["confederation"],
        )

    module = importlib.import_module(module_path)
    coupons: dict = module.COUPONS
    total_fixtures = 0
    errors: list[str] = []

    for coupon_key, coupon_data in coupons.items():
        coupon_id = f"{coupon_key}-{week:02d}-{year}"
        upsert_coupon(coupon_id, coupon_data["label"], coupon_data["deadline"], week, year)

        for match_number, (home_name, away_name, oh, ou, ob) in enumerate(
            coupon_data["matches"], 1
        ):
            try:
                home_id = _resolve_team_id(home_name)
                away_id = _resolve_team_id(away_name)
            except KeyError as exc:
                errors.append(str(exc))
                continue

            comp_id = _resolve_competition(home_id, away_id)
            fixture_id = upsert_fixture(
                home_team_id=home_id,
                away_team_id=away_id,
                competition_id=comp_id,
                kickoff_utc=coupon_data["deadline"],
            )
            upsert_odds(fixture_id, "manual", oh, ou, ob)
            add_coupon_fixture(coupon_id, fixture_id, match_number)
            total_fixtures += 1

    if errors:
        print(f"  ⚠ {len(errors)} unknown team(s) — add them to TEAM_REGISTRY:")
        for e in errors:
            print(f"    {e}")

    print(
        f"  Seeded week {week}/{year} from {module_path}: "
        f"{total_fixtures} fixtures across {len(coupons)} coupons."
    )
