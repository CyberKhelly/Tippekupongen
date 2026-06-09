from dataclasses import dataclass, field


@dataclass
class Match:
    number: int
    home_team: str
    away_team: str
    odds_h: float
    odds_u: float
    odds_b: float
    prob_h: float = 0.0
    prob_u: float = 0.0
    prob_b: float = 0.0
    confidence: float = 0.0
    recommendation: str = ""
    classification: str = ""
    # Phase 1: identity fields — populated when data comes from DB
    home_team_id: str | None = field(default=None, repr=False)
    away_team_id: str | None = field(default=None, repr=False)
    fixture_id: str | None   = field(default=None, repr=False)
    competition_id: str | None = field(default=None, repr=False)
    odds_source: str = field(default="", repr=False)

    # ── Phase 5: bookmaker prior (audit copy, set by run_model) ───────────────
    bm_prob_h: float = field(default=0.0, repr=False)
    bm_prob_u: float = field(default=0.0, repr=False)
    bm_prob_b: float = field(default=0.0, repr=False)

    # ── Phase 5: stats adjustment audit ──────────────────────────────────────
    home_edge:    float = field(default=0.0,  repr=False)
    stats_adj_pp: float = field(default=0.0,  repr=False)   # signed pp applied to H (opposite on B)
    stats_signals: list = field(default_factory=list, repr=False)
    has_af_data:  bool  = field(default=False, repr=False)

    # ── Phase 5: expert adjustment audit ─────────────────────────────────────
    expert_adj_h:  float = field(default=0.0,  repr=False)  # pp contribution of expert tips to H
    expert_adj_u:  float = field(default=0.0,  repr=False)
    expert_adj_b:  float = field(default=0.0,  repr=False)
    has_expert_tips: bool = field(default=False, repr=False)

    # ── Phase 5: public / crowd signals ──────────────────────────────────────
    pub_prob_h: float | None = field(default=None, repr=False)
    pub_prob_u: float | None = field(default=None, repr=False)
    pub_prob_b: float | None = field(default=None, repr=False)
    value_h: float | None    = field(default=None, repr=False)  # (model − public) in pp
    value_u: float | None    = field(default=None, repr=False)
    value_b: float | None    = field(default=None, repr=False)
    # TVD(model, public) × 100 — 0 = perfect alignment, ~50 = maximum disagreement
    crowd_disagreement_score: float | None = field(default=None, repr=False)
    # outcome most overplayed by public vs model (most negative value_*)
    crowd_pressure_pick: str | None = field(default=None, repr=False)
    has_public_tips: bool = field(default=False, repr=False)

    @property
    def label(self) -> str:
        return f"{self.home_team} - {self.away_team}"

    @property
    def overround(self) -> float:
        """Sum of raw implied probabilities. Above 1.0 = bookmaker margin."""
        return (1 / self.odds_h) + (1 / self.odds_u) + (1 / self.odds_b)

    @property
    def margin_pct(self) -> float:
        return (self.overround - 1.0) * 100
