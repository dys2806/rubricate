"""Tests for agreement statistics and `rubricate calibrate`."""

import json  # parse JSON output
from pathlib import Path  # repo paths

import pytest  # fixtures, approx

from rubricate.agreement import krippendorff_alpha, quadratic_weighted_kappa  # the math
from rubricate.calibrate import CalibrationError, calibrate, load_human_ratings  # the report
from rubricate.cli import EXIT_OK, EXIT_USAGE, main  # the CLI
from rubricate.spec import load_rubric  # the example rubric

ROOT = Path(__file__).resolve().parent.parent
RUBRIC = ROOT / "examples" / "refund-agent.rubric.yaml"
RATINGS = ROOT / "examples" / "ratings" / "refund-human-ratings.csv"

# Krippendorff's worked example (4 raters, 12 items, missing values). Published results:
# ordinal alpha = 0.815, interval alpha = 0.849.
A = [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None]
B = [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3]
C = [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None]
D = [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None]
UNITS = [[r[i] for r in (A, B, C, D) if r[i] is not None] for i in range(12)]


# ---------------------------------------------------------------- statistics


def test_alpha_matches_krippendorffs_published_example():
    assert krippendorff_alpha(UNITS, "ordinal") == pytest.approx(0.8154, abs=1e-4)
    assert krippendorff_alpha(UNITS, "interval") == pytest.approx(0.8491, abs=1e-4)


def test_alpha_edge_cases():
    assert krippendorff_alpha([[3, 3], [3, 3]]) is None  # no variation: undefined
    assert krippendorff_alpha([[1, 1], [5, 5], [3, 3]]) == pytest.approx(1.0)  # perfect
    assert krippendorff_alpha([[1], [2]]) is None  # nothing to compare


def test_weighted_kappa_matches_reference():
    # reference value from scikit-learn's cohen_kappa_score(weights="quadratic")
    kappa = quadratic_weighted_kappa([1, 2, 3, 4, 5, 3, 2, 1], [1, 2, 4, 4, 5, 2, 2, 2], 1, 5)
    assert kappa == pytest.approx(0.8909, abs=1e-4)
    assert quadratic_weighted_kappa([3, 3], [3, 3], 1, 5) is None  # undefined


# ---------------------------------------------------------------- report


def test_sample_ratings_flag_the_weak_criterion():
    rubric = load_rubric(RUBRIC)
    rows = {r.criterion: r for r in calibrate(rubric, load_human_ratings(RATINGS, rubric))}
    assert rows["policy_accuracy"].human_alpha > 0.8  # raters agree
    assert rows["tone"].human_alpha < 0.667  # raters split
    assert rows["tone"].verdict == "humans disagree: tighten the anchors"


def test_judge_comparison():
    rubric = load_rubric(RUBRIC)
    human = [(f"i{n}", r, "policy_accuracy", s) for n, s in enumerate([1, 3, 5, 5]) for r in "ab"]
    judge = {("i0", "policy_accuracy"): 1, ("i1", "policy_accuracy"): 4,
             ("i2", "policy_accuracy"): 5, ("i3", "policy_accuracy"): 5}  # fmt: skip
    row = calibrate(rubric, human, judge)[0]
    assert row.judge_items == 4 and row.exact == 0.75 and row.within_one == 1.0
    assert row.bias == pytest.approx(0.25)  # judge scored one item a point higher


@pytest.mark.parametrize(
    "line, message",
    [
        ("i1,ana,made_up,3", "unknown criterion"),
        ("i1,ana,tone,9", "outside tone's scale"),
        ("i1,ana,tone,high", "isn't a whole number"),
    ],
)
def test_bad_ratings_point_at_the_line(tmp_path, line, message):
    path = tmp_path / "r.csv"
    path.write_text(f"item,rater,criterion,score\n{line}\n", encoding="utf-8")
    with pytest.raises(CalibrationError, match=rf"r\.csv:2: .*{message}"):
        load_human_ratings(path, load_rubric(RUBRIC))


# ---------------------------------------------------------------- CLI


def test_cli_text_and_json(capsys):
    assert main(["calibrate", str(RUBRIC), "--human", str(RATINGS)]) == EXIT_OK
    assert "humans disagree: tighten the anchors" in capsys.readouterr().out
    main(["calibrate", str(RUBRIC), "--human", str(RATINGS), "--format", "json"])
    payload = {r["criterion"]: r for r in json.loads(capsys.readouterr().out)}
    assert payload["policy_accuracy"]["items"] == 12 and payload["policy_accuracy"]["raters"] == 3


def test_cli_reads_score_batch_output(tmp_path, capsys):  # the format `score --batch` writes
    scores = tmp_path / "scores.jsonl"
    lines = [
        {
            "id": "r01",
            "criteria": [{"id": "policy_accuracy", "score": 5}, {"id": "tone", "score": 4}],
        },
        {"id": "r02", "error": "rate limited"},  # failed items are skipped, not guessed
    ]
    scores.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    args = ["calibrate", str(RUBRIC), "--human", str(RATINGS), "--judge-scores", str(scores)]
    assert main(args + ["--format", "json"]) == EXIT_OK
    rows = {r["criterion"]: r for r in json.loads(capsys.readouterr().out)}
    assert rows["policy_accuracy"]["judge_items"] == 1


def test_cli_missing_columns_is_usage_error(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("item,score\ni1,3\n", encoding="utf-8")
    assert main(["calibrate", str(RUBRIC), "--human", str(bad)]) == EXIT_USAGE
    assert "missing column(s) rater, criterion" in capsys.readouterr().err
