"""Calibration: do humans agree with each other, and does the judge agree with them?"""

from __future__ import annotations  # modern type hints on Python 3.10

import csv  # human ratings come as CSV
import json  # judge scores come as JSONL from `rubricate score --batch`
from dataclasses import asdict, dataclass  # report rows
from pathlib import Path  # filesystem paths
from typing import Any  # parsed rubric data

from rubricate.agreement import (  # the statistics
    krippendorff_alpha,
    median,
    quadratic_weighted_kappa,
)

# Krippendorff's conventional thresholds: >= 0.800 reliable, 0.667-0.800 tentative only.
ALPHA_RELIABLE = 0.800
ALPHA_TENTATIVE = 0.667
JUDGE_KAPPA_OK = 0.600  # judge-vs-human agreement below this means the judge isn't usable yet

CSV_COLUMNS = ("item", "rater", "criterion", "score")  # one row per rating ("long" format)


class CalibrationError(ValueError):  # bad input, with the file and line
    pass


@dataclass(frozen=True)
class CriterionReport:  # agreement numbers for one criterion
    criterion: str
    items: int  # items with at least two human ratings
    raters: int  # distinct human raters
    human_alpha: float | None  # agreement among humans (the ceiling for any judge)
    judge_items: int  # items scored by both the judge and at least one human
    judge_kappa: float | None  # judge vs. the human median, quadratic-weighted kappa
    exact: float | None  # share of items where the judge matched the human median exactly
    within_one: float | None  # share within one point of the human median
    bias: float | None  # judge mean minus human mean: positive = judge scores higher
    verdict: str  # plain-language next step

    def to_dict(self) -> dict[str, Any]:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def load_human_ratings(path: Path, rubric: dict[str, Any]) -> list[tuple[str, str, str, int]]:
    """Read item,rater,criterion,score rows and check them against the rubric."""
    scales = _scales(rubric)  # criterion -> (lo, hi)
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise CalibrationError(f"{path}: missing column(s) {', '.join(missing)}")
        for n, row in enumerate(reader, start=2):  # line 1 is the header
            crit = row["criterion"].strip()
            if crit not in scales:
                raise CalibrationError(f"{path}:{n}: unknown criterion {crit!r}")
            try:
                score = int(row["score"])
            except ValueError as exc:
                raise CalibrationError(
                    f"{path}:{n}: score {row['score']!r} isn't a whole number"
                ) from exc
            lo, hi = scales[crit]
            if not lo <= score <= hi:
                raise CalibrationError(
                    f"{path}:{n}: score {score} is outside {crit}'s scale {lo}-{hi}"
                )
            rows.append((row["item"].strip(), row["rater"].strip(), crit, score))
    if not rows:
        raise CalibrationError(f"{path}: no ratings found")
    return rows


def load_judge_scores(path: Path) -> dict[tuple[str, str], int]:
    """Read `rubricate score --batch` output: {(item, criterion): score}."""
    out = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CalibrationError(f"{path}:{n}: not valid JSON ({exc.msg})") from exc
        if "error" in rec:  # the judge failed on this item: leave it out, don't guess
            continue
        for c in rec.get("criteria", []):
            out[(str(rec["id"]), c["id"])] = int(c["score"])
    return out


def _scales(rubric: dict[str, Any]) -> dict[str, tuple[int, int]]:  # scored criteria ranges
    out = {}
    for c in rubric["criteria"]:
        if c.get("type", "scored") == "scored":
            levels = sorted(int(k) for k in c["scale"])
            out[c["id"]] = (levels[0], levels[-1])
    return out


def _verdict(alpha: float | None, kappa: float | None, judged: bool) -> str:
    if alpha is None:
        return "not enough variation to measure"
    if alpha < ALPHA_TENTATIVE:  # humans can't apply it consistently: fix the rubric first
        return "humans disagree: tighten the anchors"
    if not judged:
        return "humans agree" if alpha >= ALPHA_RELIABLE else "humans agree (tentative)"
    if kappa is None or kappa < JUDGE_KAPPA_OK:  # rubric is fine, the judge isn't following it
        return "judge disagrees with humans"
    return "ok" if alpha >= ALPHA_RELIABLE else "ok (human agreement tentative)"


def calibrate(
    rubric: dict[str, Any],
    human: list[tuple[str, str, str, int]],
    judge: dict[tuple[str, str], int] | None = None,
) -> list[CriterionReport]:
    scales = _scales(rubric)
    reports = []
    for crit, (lo, hi) in scales.items():  # in rubric order
        by_item: dict[str, list[int]] = {}  # item -> human scores
        raters = set()
        for item, rater, c, score in human:
            if c == crit:
                by_item.setdefault(item, []).append(score)
                raters.add(rater)
        units = [v for v in by_item.values() if len(v) >= 2]  # only items humans can compare on
        alpha = krippendorff_alpha(units, "ordinal") if units else None
        pairs = []  # (judge score, human median) per item
        if judge:
            for item, scores in by_item.items():
                if (item, crit) in judge:
                    pairs.append((judge[(item, crit)], median(scores)))
        kappa = exact = within = bias = None
        if pairs:
            j = [p[0] for p in pairs]
            h = [p[1] for p in pairs]
            rounded = [int(x + 0.5) for x in h]  # round half up to a whole level for kappa
            kappa = quadratic_weighted_kappa(j, rounded, lo, hi)
            exact = sum(a == b for a, b in zip(j, rounded, strict=True)) / len(pairs)
            within = sum(abs(a - b) <= 1 for a, b in zip(j, h, strict=True)) / len(pairs)
            bias = sum(j) / len(j) - sum(h) / len(h)
        reports.append(
            CriterionReport(
                crit,
                len(units),
                len(raters),
                alpha,
                len(pairs),
                kappa,
                exact,
                within,
                bias,
                _verdict(alpha, kappa, bool(judge)),
            )
        )
    return reports
