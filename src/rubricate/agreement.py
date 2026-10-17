"""Agreement statistics for rubric scores. Pure Python, no numpy needed."""

from __future__ import annotations  # modern type hints on Python 3.10

from collections import Counter, defaultdict  # tallies of values and pairs
from collections.abc import Iterable, Mapping, Sequence  # input types
from itertools import permutations  # ordered pairs of values within one item


def krippendorff_alpha(
    units: Iterable[Sequence[float]],  # one list of scores per item, from any number of raters
    level: str = "ordinal",  # "ordinal" (rubric levels) or "interval" (equal-spaced numbers)
) -> float | None:
    """Krippendorff's alpha: 1 = perfect agreement, 0 = chance, < 0 = worse than chance.

    Handles any number of raters and missing ratings. Returns None when there is no
    variation at all (every rater gave every item the same score), where alpha is undefined.
    """
    coincidence: Counter[tuple[float, float]] = Counter()  # weighted pairs of values
    for values in units:  # each item
        m = len(values)  # how many raters scored it
        if m < 2:  # a single rating can't agree or disagree with anything
            continue
        for a, b in permutations(values, 2):  # every ordered pair of ratings on this item
            coincidence[(a, b)] += 1 / (m - 1)  # each item contributes m values in total
    if not coincidence:  # nothing pairable
        return None
    totals: Counter[float] = Counter()  # how often each value occurs among pairable ratings
    for (a, _), w in coincidence.items():
        totals[a] += w
    n = sum(totals.values())  # number of pairable ratings
    values = sorted(totals)  # the distinct score values used
    delta = _distance(level, values, totals)  # squared distance between two values
    observed = sum(w * delta(a, b) for (a, b), w in coincidence.items()) / n
    expected = sum(totals[a] * totals[b] * delta(a, b) for a in values for b in values) / (
        n * (n - 1)
    )
    if expected == 0:  # every rating is identical: agreement is trivial, alpha undefined
        return None
    return 1 - observed / expected  # 1 minus (actual disagreement / chance disagreement)


def _distance(level: str, values: list[float], totals: Mapping[float, float]):
    if level == "interval":  # equal spacing: distance is the plain difference
        return lambda a, b: (a - b) ** 2
    if level == "ordinal":  # rank-based: distance grows with how many ratings lie between
        index = {v: i for i, v in enumerate(values)}  # position of each value

        def ordinal(a: float, b: float) -> float:
            lo, hi = sorted((index[a], index[b]))  # walk from the lower to the higher value
            between = sum(totals[values[g]] for g in range(lo, hi + 1))  # ratings in range
            return (between - (totals[a] + totals[b]) / 2) ** 2

        return ordinal
    raise ValueError(f"unknown level {level!r}; use 'ordinal' or 'interval'")


def quadratic_weighted_kappa(a: Sequence[int], b: Sequence[int], lo: int, hi: int) -> float | None:
    """Cohen's kappa between two raters, with disagreements weighted by squared distance.

    1 = perfect agreement, 0 = chance. Returns None when it's undefined (no variation).
    """
    if len(a) != len(b) or not a:  # need paired ratings
        return None
    k = hi - lo + 1  # number of possible scores
    observed = [[0.0] * k for _ in range(k)]  # confusion matrix of the two raters
    for x, y in zip(a, b, strict=True):
        observed[x - lo][y - lo] += 1
    n = len(a)
    row = [sum(r) for r in observed]  # how often rater A used each score
    col = [sum(observed[i][j] for i in range(k)) for j in range(k)]  # same for rater B
    num = den = 0.0  # weighted observed and expected disagreement
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2 if k > 1 else 0.0  # quadratic weight
            num += w * observed[i][j]
            den += w * row[i] * col[j] / n  # what chance alone would produce
    if den == 0:  # one rater used a single score: kappa undefined
        return None
    return 1 - num / den


def median(values: Sequence[float]) -> float:  # middle value (mean of the two middles if even)
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def group_by_item(rows: Iterable[tuple[str, str, int]]) -> dict[str, dict[str, int]]:
    """(item, rater, score) rows -> {item: {rater: score}}."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for item, rater, score in rows:
        out[item][rater] = score
    return dict(out)
