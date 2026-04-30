"""
HALT engine v2 — multi-source credibility.

Pure functions. Given a flat place record with google_rating / tripadvisor_rating,
returns a verdict backed by visible proof (sources).

Rules (intentionally simple):
- STOP  = high rating + enough volume + sources agree
- SKIP  = low rating OR sources strongly disagree
- DOUBT = everything in between
"""
import math
from typing import Dict, List, Optional, Tuple

# Thresholds — tune here
STOP_MIN_AVG = 4.25
STOP_MIN_REVIEWS = 80
STOP_MAX_MISMATCH = 0.5

SKIP_MAX_AVG = 3.8
SKIP_MIN_MISMATCH = 1.2


def _source(place: Dict, key_rating: str, key_count: str) -> Optional[Dict]:
    r = place.get(key_rating)
    c = place.get(key_count)
    if r is None or c is None:
        return None
    return {"rating": float(r), "reviews": int(c)}


def extract_sources(place: Dict) -> Dict[str, Dict]:
    """Turns flat fields into a clean sources dict. Omits missing sources."""
    sources: Dict[str, Dict] = {}
    g = _source(place, "google_rating", "google_reviews")
    if g:
        sources["google"] = g
    t = _source(place, "tripadvisor_rating", "tripadvisor_reviews")
    if t:
        sources["tripadvisor"] = t
    return sources


def _weighted_avg(sources: Dict[str, Dict]) -> Tuple[float, int]:
    if not sources:
        return 0.0, 0
    items = list(sources.values())
    # Weight by log of review count — dampens extreme volumes
    weights = [math.log10(max(s["reviews"], 0) + 10) for s in items]
    total_w = sum(weights) or 1.0
    avg = sum(s["rating"] * w for s, w in zip(items, weights)) / total_w
    total = sum(s["reviews"] for s in items)
    return avg, total


def _mismatch(sources: Dict[str, Dict]) -> float:
    ratings = [s["rating"] for s in sources.values()]
    if len(ratings) < 2:
        return 0.0
    return max(ratings) - min(ratings)


def compute_verdict(place: Dict) -> Dict:
    sources = extract_sources(place)

    if not sources:
        return {
            "verdict": "DOUBT",
            "explanation": "No public data available",
            "sources": {},
            "weighted_avg": None,
            "total_reviews": 0,
            "mismatch": None,
        }

    avg, total = _weighted_avg(sources)
    mismatch = _mismatch(sources)
    single_source = len(sources) < 2

    # Decision tree (order matters)
    if avg < SKIP_MAX_AVG or mismatch >= SKIP_MIN_MISMATCH:
        verdict = "SKIP"
        explanation = _explain_skip(avg, mismatch)
    elif (
        avg >= STOP_MIN_AVG
        and total >= STOP_MIN_REVIEWS
        and mismatch < STOP_MAX_MISMATCH
        and not single_source
    ):
        verdict = "STOP"
        explanation = _explain_stop(avg, total)
    else:
        verdict = "DOUBT"
        explanation = _explain_doubt(avg, mismatch, single_source, total)

    return {
        "verdict": verdict,
        "explanation": explanation,
        "sources": sources,
        "weighted_avg": round(avg, 2),
        "total_reviews": total,
        "mismatch": round(mismatch, 2),
    }


def _explain_stop(avg: float, total: int) -> str:
    return f"Consistent {avg:.1f}/5 across sources · {total:,} reviews"


def _explain_doubt(avg: float, mismatch: float, single: bool, total: int) -> str:
    if single:
        return f"Only one source available ({total:,} reviews)"
    if mismatch >= STOP_MAX_MISMATCH:
        return f"Sources disagree (Δ {mismatch:.1f})"
    if avg < STOP_MIN_AVG:
        return f"Rating slightly below threshold ({avg:.1f}/5)"
    return "Mixed signals across platforms"


def _explain_skip(avg: float, mismatch: float) -> str:
    if mismatch >= SKIP_MIN_MISMATCH:
        return f"Strong inconsistency between sources (Δ {mismatch:.1f})"
    return f"Low average rating ({avg:.1f}/5)"
