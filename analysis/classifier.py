from models.match import Match

# Thresholds — tune these as you gather real-world results
BANKER_THRESHOLD = 0.60      # Top prob >= 60%  → very high confidence single
UNCERTAIN_THRESHOLD = 0.45   # Top prob <  45%  → no clear favourite
FULL_COVER_SPREAD = 0.10     # top - bottom < 10% → three outcomes nearly equal
HALF_COVER_SPREAD = 0.13     # top - second < 13% → two outcomes nearly equal

_LABELS = {
    "banker":     "Banker",
    "uncertain":  "Uncertain",
    "full_cover": "Full Cover",
    "half_cover": "Half Cover",
    "standard":   "Standard",
}


def classify_match(match: Match) -> None:
    """
    Assign a classification to a match based on its probability distribution.

    banker     — one outcome dominates; safe single pick
    uncertain  — no clear favourite; all three outcomes plausible
    full_cover — three probabilities tightly bunched; cover all three
    half_cover — two outcomes are close; cover the top two
    standard   — one outcome leads but not with banker-level confidence
    """
    probs = sorted([match.prob_h, match.prob_u, match.prob_b], reverse=True)
    top, second, bottom = probs

    if top >= BANKER_THRESHOLD:
        match.classification = "banker"
    elif top < UNCERTAIN_THRESHOLD:
        match.classification = "uncertain"
    elif (top - bottom) < FULL_COVER_SPREAD:
        match.classification = "full_cover"
    elif (top - second) < HALF_COVER_SPREAD:
        match.classification = "half_cover"
    else:
        match.classification = "standard"


def classification_label(cls: str) -> str:
    return _LABELS.get(cls, cls)
