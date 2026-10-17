"""Tests for lint rules and the `rubricate lint` command."""

import copy  # fresh rubric per test
import json  # parse --format json output
from pathlib import Path  # paths to repo files

import pytest  # fixtures

from rubricate.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main  # the CLI
from rubricate.lint import RULES, lint_data, lint_file  # the rule engine
from rubricate.spec import load_rubric  # load example rubrics

ROOT = Path(__file__).resolve().parent.parent  # repo root
GOOD = ROOT / "examples" / "refund-agent.rubric.yaml"  # a rubric that should lint clean
WEAK = ROOT / "examples" / "lint-demo" / "weak-support.rubric.yaml"  # one full of problems


@pytest.fixture
def rubric():  # a fresh copy of the clean example for each test
    return copy.deepcopy(load_rubric(GOOD))


def codes(findings):  # helper: just the rule codes, in order
    return [f.code for f in findings]


def test_good_example_is_clean():  # the flagship example must model best practice
    report = lint_file(GOOD)  # lint it
    assert report.findings == [] and report.schema_errors == []  # nothing to report


def test_rule_codes_and_names_are_unique():  # codes are a public contract
    assert len({r.code for r in RULES}) == len(RULES)  # no duplicate codes
    assert len({r.name for r in RULES}) == len(RULES)  # no duplicate names


def test_duplicate_id(rubric):  # R001
    rubric["criteria"][1]["id"] = "policy_accuracy"  # reuse the first id
    findings = lint_data(rubric)  # run all rules
    assert "R001" in codes(findings)  # caught
    hit = next(f for f in findings if f.code == "R001")  # the finding itself
    assert hit.path == "criteria[1].id" and "criteria[0]" in hit.message  # points to both


def test_example_off_scale(rubric):  # R002
    rubric["criteria"][0]["examples"][0]["score"] = 4  # 4 isn't a level on a 1/3/5 scale
    hit = next(f for f in lint_data(rubric) if f.code == "R002")  # find it
    assert hit.path == "criteria[0].examples[0].score"  # exact location
    assert "levels: 1, 3, 5" in hit.message  # tells the user what's allowed


def test_level_without_example(rubric):  # R003
    rubric["criteria"][0]["examples"] = rubric["criteria"][0]["examples"][:1]  # keep only score 1
    paths = [f.path for f in lint_data(rubric) if f.code == "R003"]  # missing levels
    assert paths == ["criteria[0].scale.3", "criteria[0].scale.5"]  # exactly 3 and 5


def test_assertions_are_skipped_by_scale_rules(rubric):  # assertions have no scale
    rubric["criteria"] = [rubric["criteria"][2]]  # only the approval_gate assertion
    assert lint_data(rubric) == []  # nothing to say about it


@pytest.mark.parametrize(  # vague words caught as whole words, any case
    "anchor, word",
    [
        ("The reply is Good.", "good"),
        ("Mostly appropriate", "appropriate"),
        ("high quality", "high quality"),
    ],
)
def test_vague_anchor(rubric, anchor, word):  # R004
    rubric["criteria"][0]["scale"]["3"] = anchor  # replace a concrete anchor
    hit = next(f for f in lint_data(rubric) if f.code == "R004")  # find it
    assert f"'{word}'" in hit.message  # names the offending word


def test_vague_anchor_ignores_word_parts(rubric):  # "goodwill" is not "good"
    rubric["criteria"][0]["scale"]["3"] = "Mentions the goodwill credit and the receipt rule."
    assert "R004" not in codes(lint_data(rubric))  # no false positive


def test_ignore_by_code_and_name(rubric):  # users can turn rules off
    rubric["criteria"][0]["examples"] = []  # triggers R003 three times
    assert "R003" not in codes(lint_data(rubric, frozenset({"R003"})))  # by code
    assert "R003" not in codes(lint_data(rubric, frozenset({"level-without-example"})))  # by name


def test_weak_demo_has_line_numbers():  # every finding points to a line
    report = lint_file(WEAK)  # the deliberately weak rubric
    assert report.schema_errors == []  # structure is fine...
    assert {"R001", "R002", "R003", "R004"} <= set(codes(report.findings))  # ...quality is not
    assert all(f.line for f in report.findings)  # each finding has a line


def test_schema_errors_stop_rules(tmp_path):  # rules assume a structurally valid rubric
    bad = tmp_path / "bad.rubric.yaml"  # missing required fields
    bad.write_text('spec: "0.1"\nid: x\n', encoding="utf-8")
    report = lint_file(bad)  # lint it
    assert report.schema_errors and report.findings == []  # schema only


# ---------------------------------------------------------------- CLI


def test_cli_clean_file_exits_zero(capsys):
    assert main(["lint", str(GOOD)]) == EXIT_OK  # clean
    assert "clean" in capsys.readouterr().out  # says so


def test_cli_errors_exit_one(capsys):  # R001/R002 are errors
    assert main(["lint", str(WEAK)]) == EXIT_INVALID  # fails the run
    out = capsys.readouterr().out
    assert "R001 error" in out and "R004 warning" in out  # both kinds shown
    assert f"{WEAK}:" in out  # file:line prefix


def test_cli_warnings_pass_unless_strict(tmp_path, capsys):  # warnings don't fail by default
    path = tmp_path / "w.rubric.yaml"  # valid rubric with only a vague anchor and no examples
    path.write_text(
        'spec: "0.1"\nid: w\nsubject: response\ncriteria:\n'
        "  - id: c\n    question: q?\n    scale:\n      1: Bad\n      5: Cites the source\n",
        encoding="utf-8",
    )
    assert main(["lint", str(path)]) == EXIT_OK  # warnings only: pass
    assert main(["lint", "--strict", str(path)]) == EXIT_INVALID  # strict: fail


def test_cli_ignore_flag(tmp_path):  # --ignore can silence the warnings entirely
    path = tmp_path / "w.rubric.yaml"
    path.write_text(
        'spec: "0.1"\nid: w\nsubject: response\ncriteria:\n'
        "  - id: c\n    question: q?\n    scale:\n      1: Bad\n      5: Cites the source\n",
        encoding="utf-8",
    )
    assert main(["lint", "--strict", "--ignore", "R003,vague-anchor", str(path)]) == EXIT_OK


def test_cli_unknown_ignore_is_usage_error(capsys):  # typos shouldn't silently do nothing
    assert main(["lint", "--ignore", "R999", str(GOOD)]) == EXIT_USAGE
    assert "unknown rule" in capsys.readouterr().err


def test_cli_list_rules(capsys):  # the rule catalog
    assert main(["lint", "--list-rules"]) == EXIT_OK
    out = capsys.readouterr().out
    assert all(r.code in out for r in RULES)  # every rule listed


def test_cli_json(capsys):  # machine-readable
    main(["lint", "--format", "json", str(WEAK)])
    payload = json.loads(capsys.readouterr().out)  # valid JSON
    assert payload[0]["errors"] >= 2 and payload[0]["warnings"] >= 1  # counts present
    assert all(f["line"] for f in payload[0]["findings"])  # lines present
