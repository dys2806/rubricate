"""Tests for `rubricate export`."""

from pathlib import Path  # repo paths

import yaml  # parse the exported config

from rubricate.cli import EXIT_OK, EXIT_USAGE, main  # the CLI
from rubricate.export import to_promptfoo  # the exporter
from rubricate.spec import load_rubric  # example rubrics

ROOT = Path(__file__).resolve().parent.parent
REFUND = ROOT / "examples" / "refund-agent.rubric.yaml"


def exported(threshold=None):  # helper: parsed promptfoo assertions for the refund rubric
    return yaml.safe_load(to_promptfoo(load_rubric(REFUND), threshold))["defaultTest"]["assert"]


def test_one_llm_rubric_per_scored_criterion():
    asserts = exported()
    assert [a["metric"] for a in asserts] == ["policy_accuracy", "tone"]  # assertions left out
    assert all(a["type"] == "llm-rubric" for a in asserts)
    assert [a["weight"] for a in asserts] == [0.5, 0.2]  # rubric weights carried over


def test_rubric_text_keeps_anchors_examples_and_score_mapping():
    text = exported()[0]["value"]
    assert "- 3: States the window and amount correctly" in text  # anchors in order
    assert "Example scored 1:" in text and "Why:" in text  # worked examples
    assert "score = (level - 1) / 4" in text  # 1-5 mapped onto promptfoo's 0-1 scale


def test_threshold_is_optional():
    assert "threshold" not in exported()[0]
    assert exported(0.75)[0]["threshold"] == 0.75


def test_skipped_assertions_are_named_in_the_header():
    header = to_promptfoo(load_rubric(REFUND)).split("\ndefaultTest:")[0]  # comment block
    assert "Not exported: approval_gate, lookup_budget" in header


def test_cli_writes_file(tmp_path, capsys):
    out = tmp_path / "rubric.promptfoo.yaml"
    assert main(["export", str(REFUND), "--to", "promptfoo", "-o", str(out)]) == EXIT_OK
    assert yaml.safe_load(out.read_text())["defaultTest"]["assert"][1]["metric"] == "tone"


def test_cli_rejects_bad_threshold_and_broken_rubric(tmp_path, capsys):
    assert main(["export", str(REFUND), "--to", "promptfoo", "--threshold", "2"]) == EXIT_USAGE
    bad = tmp_path / "bad.rubric.yaml"
    bad.write_text('spec: "0.1"\nid: x\n', encoding="utf-8")
    assert main(["export", str(bad), "--to", "promptfoo"]) == EXIT_USAGE
