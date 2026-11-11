"""Tests for SARIF output from `rubricate lint --format sarif`."""

import json  # parse the CLI output
from pathlib import Path  # paths to repo files

from rubricate.cli import EXIT_INVALID, EXIT_OK, main  # the CLI
from rubricate.lint import RULES, lint_file  # the rule engine
from rubricate.sarif import SCHEMA_RULE_ID, to_sarif  # the converter

ROOT = Path(__file__).resolve().parent.parent  # repo root
GOOD = ROOT / "examples" / "refund-agent.rubric.yaml"  # lints clean
WEAK = ROOT / "examples" / "lint-demo" / "weak-support.rubric.yaml"  # full of problems


def test_log_shape():  # the fields GitHub code scanning requires
    log = to_sarif([lint_file(WEAK)])
    assert log["version"] == "2.1.0" and "$schema" in log
    driver = log["runs"][0]["tool"]["driver"]
    assert driver["name"] == "rubricate"
    ids = [r["id"] for r in driver["rules"]]
    assert ids == [SCHEMA_RULE_ID, *(r.code for r in RULES)]  # every rule is described


def test_results_match_findings():  # one result per finding, same rule, level, and line
    report = lint_file(WEAK)
    results = to_sarif([report])["runs"][0]["results"]
    assert len(results) == len(report.findings)
    rules = to_sarif([report])["runs"][0]["tool"]["driver"]["rules"]
    for result, finding in zip(results, report.findings, strict=True):
        assert result["ruleId"] == finding.code
        assert rules[result["ruleIndex"]]["id"] == finding.code  # index points at the right rule
        assert result["level"] == ("error" if finding.severity == "error" else "warning")
        location = result["locations"][0]["physicalLocation"]
        assert location["region"]["startLine"] == finding.line
        assert finding.message in result["message"]["text"]


def test_relative_paths_stay_relative(monkeypatch):  # GitHub resolves them from the repo root
    monkeypatch.chdir(ROOT)  # lint from the repo root, as CI does
    report = lint_file(Path("examples/lint-demo/weak-support.rubric.yaml"))
    location = to_sarif([report])["runs"][0]["results"][0]["locations"][0]
    assert location["physicalLocation"]["artifactLocation"]["uri"] == (
        "examples/lint-demo/weak-support.rubric.yaml"
    )


def test_schema_errors_are_results(tmp_path):  # a broken rubric still produces annotations
    bad = tmp_path / "bad.rubric.yaml"
    bad.write_text('spec: "0.1"\nid: x\n', encoding="utf-8")
    results = to_sarif([lint_file(bad)])["runs"][0]["results"]
    assert results and all(r["ruleId"] == SCHEMA_RULE_ID for r in results)
    assert all(r["level"] == "error" for r in results)
    assert results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].startswith(
        "file://"
    )  # absolute paths become file URIs


def test_cli_sarif(capsys):  # same exit codes as the other formats
    assert main(["lint", "--format", "sarif", str(WEAK)]) == EXIT_INVALID
    log = json.loads(capsys.readouterr().out)
    assert log["runs"][0]["results"]
    assert main(["lint", "--format", "sarif", str(GOOD)]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["runs"][0]["results"] == []  # clean file
