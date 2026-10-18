"""Compare judge-expert agreement under the baseline and revised rubrics.

Reads the judge's scores for both rubrics and the expert ratings, then reports, for each
rubric, quadratic weighted kappa against the expert median, plus a paired bootstrap
confidence interval for the difference. Run from the repo root after poc/run.sh:

    python poc/compare.py
"""

from __future__ import annotations  # modern type hints on Python 3.10

import csv  # expert ratings
import json  # judge scores and the results file
import random  # bootstrap resampling
import sys  # import rubricate from src/ without installing
from pathlib import Path  # file paths

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))  # use this checkout's rubricate

from rubricate.agreement import krippendorff_alpha, median, quadratic_weighted_kappa  # noqa: E402

SEED = 2026  # same seed as prepare.py
RESAMPLES = 10_000  # bootstrap iterations
LO, HI = 1, 5  # SummEval's scale


def load_judge(path: Path) -> dict[str, int]:  # item id -> judge's coherence score
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if "error" not in rec:  # failed items are excluded, and counted below
            out[rec["id"]] = next(c["score"] for c in rec["criteria"] if c["id"] == "coherence")
    return out


def load_experts(path: Path) -> dict[str, list[int]]:  # item id -> three expert scores
    out: dict[str, list[int]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["item"], []).append(int(row["score"]))
    return out


def kappa(judge: list[int], experts: list[list[int]]) -> float:  # vs. rounded expert median
    target = [int(median(e) + 0.5) for e in experts]
    return quadratic_weighted_kappa(judge, target, LO, HI)


def main() -> None:
    experts = load_experts(HERE / "data" / "expert-ratings.csv")
    base = load_judge(HERE / "results" / "scores-baseline.jsonl")
    rev = load_judge(HERE / "results" / "scores-revised.jsonl")
    ids = sorted(set(base) & set(rev) & set(experts))  # paired: scored under both rubrics
    dropped = len(experts) - len(ids)
    if len(ids) < 20:  # too few paired items to say anything; usually every judge call failed
        raise SystemExit(
            f"Only {len(ids)} items were scored under both rubrics ({dropped} failed). "
            "Check the first error with: head -1 poc/results/scores-baseline.jsonl"
        )
    e = [experts[i] for i in ids]
    b = [base[i] for i in ids]
    r = [rev[i] for i in ids]
    k_base, k_rev = kappa(b, e), kappa(r, e)
    target = [int(median(x) + 0.5) for x in e]  # rounded expert median per item
    rng = random.Random(SEED)
    diffs = []  # bootstrap distribution of (revised - baseline)
    for _ in range(RESAMPLES):
        idx = [rng.randrange(len(ids)) for _ in ids]  # resample items with replacement
        eb = [e[i] for i in idx]
        kb, kr = kappa([b[i] for i in idx], eb), kappa([r[i] for i in idx], eb)
        if kb is not None and kr is not None:
            diffs.append(kr - kb)
    diffs.sort()
    lo, hi = diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]
    results = {
        "items": len(ids),
        "dropped_items": dropped,  # judge errors on either rubric
        "expert_alpha": round(krippendorff_alpha(e), 4),  # the ceiling
        "kappa_baseline": round(k_base, 4),
        "kappa_revised": round(k_rev, 4),
        "kappa_difference": round(k_rev - k_base, 4),
        "difference_95ci": [round(lo, 4), round(hi, 4)],
        "exact_baseline": round(sum(map(int.__eq__, b, target)) / len(ids), 4),
        "exact_revised": round(sum(map(int.__eq__, r, target)) / len(ids), 4),
        "resamples": RESAMPLES,
        "seed": SEED,
    }
    (HERE / "results" / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
