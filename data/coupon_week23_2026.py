"""
Tippekupongen uke 23, 2026
===========================
Manual source file for fixture data and prefilled odds.

HOW TO UPDATE
-------------
Each match is a tuple: (home_team, away_team, odds_H, odds_U, odds_B)

Odds are decimal format (e.g. 1.75 = 7/4 = -133 moneyline).
Update odds from Norsk Tipping Oddsen or another bookmaker before use.

Sources
-------
- Fixtures: tippetips.info, tippestudio.no
- Odds: estimated from market data — replace with live bookmaker odds

Format
------
COUPONS = {
    "key": {
        "label":    display name shown in the dropdown,
        "deadline": submission deadline as a string,
        "matches":  list of 12 (home, away, odds_h, odds_u, odds_b) tuples,
    }
}
"""

COUPONS = {

    # ── Midtukekupongen ────────────────────────────────────────────────────────
    # Fixtures: confirmed against tippetips.info + tippestudio.no
    # Odds: estimated pre-WC friendly market rates — update from bookmaker
    "midtuke": {
        "label":    "Midtuke — frist fre. 5. juni 17:55",
        "deadline": "2026-06-05 17:55",
        "matches": [
            # home                away            H      U      B
            ("Deutschland",      "Norge",         1.60,  3.90,  6.00),
            ("Østerrike",        "Slovenia",      1.80,  3.40,  4.50),
            ("Polen",            "Frankrike",     4.00,  3.50,  1.90),
            ("Ukraina",          "Island",        1.95,  3.30,  3.90),
            ("Skottland",        "Israel",        2.10,  3.25,  3.30),
            ("Italia",           "Serbia",        1.75,  3.50,  4.50),
            ("Tyrkia",           "Nord-Irland",   1.60,  3.80,  5.50),
            ("Danmark",          "Sverige",       2.35,  3.10,  2.95),
            ("Irland",           "Nederland",     4.50,  3.50,  1.80),
            ("Spania",           "England",       2.20,  3.30,  3.10),
            ("Varhaug",          "Hinna",         1.80,  3.40,  4.50),
            ("Salangen",         "Ulfstind",      2.00,  3.30,  3.80),
        ],
    },

    # ── Lørdagskupongen ────────────────────────────────────────────────────────
    # Fixtures: pre-World Cup international friendlies (June 6, 2026)
    # Source: tippestudio.no — UPDATE fixtures if incorrect
    # Odds: estimated — update from bookmaker before use
    "lordag": {
        "label":    "Lørdag — frist lør. 6. juni 14:55",
        "deadline": "2026-06-06 14:55",
        "matches": [
            # home                away               H      U      B
            ("Belgia",           "Tunisia",          1.40,  4.20,  8.00),
            ("Portugal",         "Chile",            1.55,  3.90,  6.00),
            ("Romania",          "Wales",            2.20,  3.10,  3.20),
            ("Albania",          "Luxemburg",        1.75,  3.50,  4.50),
            ("USA",              "Deutschland",      2.40,  3.20,  2.90),
            ("Panama",           "Bosnia-Herz.",     2.50,  3.10,  2.80),
            ("Sveits",           "Australia",        2.10,  3.25,  3.30),
            ("Bolivia",          "Skottland",        2.30,  3.20,  2.95),
            ("England",          "New Zealand",      1.35,  4.50,  9.00),
            ("Qatar",            "El Salvador",      2.20,  3.10,  3.20),
            ("Brasil",           "Egypt",            1.45,  4.00,  7.00),
            ("Argentina",        "Honduras",         1.40,  4.20,  8.00),
        ],
    },

    # ── Søndagskupongen ────────────────────────────────────────────────────────
    # Fixtures: mix of international friendlies + Norwegian lower league
    # Source: tippestudio.no — UPDATE fixtures if incorrect
    # Odds: estimated — update from bookmaker before use
    "sondag": {
        "label":    "Søndag — frist søn. 7. juni 15:55",
        "deadline": "2026-06-07 15:55",
        "matches": [
            # home                away               H      U      B
            ("Marokko",          "Norge",            1.85,  3.50,  4.20),
            ("Danmark",          "Ukraina",          1.90,  3.40,  4.00),
            ("Kroatia",          "Slovenia",         1.75,  3.50,  4.50),
            ("Hellas",           "Italia",           4.00,  3.50,  1.90),
            ("Ecuador",          "Guatemala",        1.60,  3.80,  5.50),
            ("Colombia",         "Jordan",           1.50,  4.00,  6.50),
            ("Ranheim",          "Strømmen",         1.90,  3.40,  4.00),
            ("Rosseland",        "Staal Jørpeland",  2.20,  3.20,  3.10),
            ("Stryn",            "Florø",            2.10,  3.25,  3.30),
            ("Ready",            "Union C. Berner",  1.95,  3.30,  3.90),
            ("Frøya",            "Gneist",           2.30,  3.20,  2.95),
            ("Stordal",          "Langevåg",         2.00,  3.35,  3.70),
        ],
    },
}
