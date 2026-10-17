"""Integrity checks for the pre-registered POC data and rubrics."""

import csv  # expert ratings
import json  # sample and held-out files
from pathlib import Path  # repo paths

from rubricate.lint import lint_file  # the rubrics' lint status is part of the design

POC = Path(__file__).resolve().parent.parent / "poc"


def ids(path):  # item ids in a JSONL file
    return [json.loads(line)["id"] for line in path.read_text().splitlines() if line.strip()]


def test_sample_and_held_out_never_overlap():  # examples must not leak into the test set
    sample, held = ids(POC / "data" / "sample.jsonl"), ids(POC / "data" / "held-out-examples.jsonl")
    assert len(sample) == 200 == len(set(sample))
    assert not set(sample) & set(held)


def test_every_sample_item_has_three_expert_ratings():
    counts = {}
    with (POC / "data" / "expert-ratings.csv").open() as f:
        for row in csv.DictReader(f):
            counts[row["item"]] = counts.get(row["item"], 0) + 1
    assert set(counts) == set(ids(POC / "data" / "sample.jsonl"))
    assert set(counts.values()) == {3}


def test_revised_examples_come_from_the_held_out_pool():
    held = {json.loads(x)["output"] for x in (POC / "data" / "held-out-examples.jsonl").open()}
    import yaml  # noqa: PLC0415 - only needed here

    rubric = yaml.safe_load((POC / "rubrics" / "coherence-revised.rubric.yaml").read_text())
    outputs = [e["output"] for e in rubric["criteria"][0]["examples"]]
    assert len(outputs) == 5 and all(o in held for o in outputs)


def test_lint_status_matches_the_design():  # baseline has warnings, revised is clean
    assert lint_file(POC / "rubrics" / "coherence-baseline.rubric.yaml").warnings == 9
    assert lint_file(POC / "rubrics" / "coherence-revised.rubric.yaml").findings == []
