from dataclasses import dataclass


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
