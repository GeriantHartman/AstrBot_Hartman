"""Small, dependency-free statistics used by the report."""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Sequence


def mean_sd(values: Sequence[float]) -> tuple[float | None, float | None]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], 0.0
    return statistics.fmean(vals), statistics.stdev(vals)


def bootstrap_ci(
    values: Sequence[float],
    *,
    iterations: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260924,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap CI of the mean. Deterministic for a given seed."""
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], vals[0]
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(statistics.fmean(rng.choices(vals, k=n)) for _ in range(iterations))
    lo = means[int((alpha / 2) * iterations)]
    hi = means[min(iterations - 1, int((1 - alpha / 2) * iterations))]
    return lo, hi


def wilson_ci(successes: float, n: int, *, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a proportion (ties may count as 0.5 success)."""
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def sign_test_p(wins: int, losses: int) -> float:
    """Two-sided exact binomial sign test, ties dropped.

    Answers: if both sides were equally good, how likely is a split at least
    this lopsided purely by chance?
    """
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def verdict_value(verdict: str, side: str) -> int:
    """+1 if ``side`` ("A"/"B") won, -1 if it lost, 0 on tie/invalid."""
    verdict = (verdict or "").strip().upper()
    if verdict not in ("A", "B"):
        return 0
    return 1 if verdict == side else -1


def merge_swapped(verdict_order1: str, verdict_order2: str) -> tuple[int, bool]:
    """Merge two pairwise verdicts for arm X.

    Order 1 shows X as "A"; order 2 shows X as "B". Returns (outcome for X in
    {-1, 0, +1}, position_consistent). Consistent means both orders agree —
    including both calling a tie.
    """
    v1 = verdict_value(verdict_order1, "A")
    v2 = verdict_value(verdict_order2, "B")
    total = v1 + v2
    outcome = (total > 0) - (total < 0)
    return outcome, v1 == v2


def win_rate(outcomes: Sequence[int]) -> dict[str, float | int]:
    wins = sum(1 for o in outcomes if o > 0)
    losses = sum(1 for o in outcomes if o < 0)
    ties = sum(1 for o in outcomes if o == 0)
    n = wins + losses + ties
    rate = (wins + 0.5 * ties) / n if n else 0.5
    lo, hi = wilson_ci(wins + 0.5 * ties, n)
    return {
        "n": n,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "win_rate": rate,
        "ci_lo": lo,
        "ci_hi": hi,
        "p_chance": sign_test_p(wins, losses),
    }
