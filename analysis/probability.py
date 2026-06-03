from models.match import Match


def process_match(match: Match) -> None:
    """
    Convert decimal odds to normalized probabilities and set recommendation.

    Steps:
      1. Compute raw implied probability: 1 / odds
      2. Sum the three raw probabilities (will be > 1.0 due to bookmaker margin)
      3. Divide each by the sum to normalize to exactly 1.0
      4. Pick the outcome with the highest normalized probability
    """
    raw_h = 1.0 / match.odds_h
    raw_u = 1.0 / match.odds_u
    raw_b = 1.0 / match.odds_b
    total = raw_h + raw_u + raw_b

    match.prob_h = raw_h / total
    match.prob_u = raw_u / total
    match.prob_b = raw_b / total

    probs = {"H": match.prob_h, "U": match.prob_u, "B": match.prob_b}
    match.recommendation = max(probs, key=probs.get)
    match.confidence = max(probs.values())
