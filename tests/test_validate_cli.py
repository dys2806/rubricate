"""Tests for `rubricate validate`: exit codes, line numbers, and output formats."""

import json  # parse --format json output
import shutil  # copy example files into a temp folder
from pathlib import Path  # paths to repo files

from rubricate.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main  # code under test

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "refund-agent.rubric.yaml"

# A rubric with three known problems, each on a predictable line
BROKEN = """\
spec: "0.1"
id: Bad Id
subject: response
criteria:
  - id: clarity
    question: Is the answer clear?
    scale:
      1: Confusing
  - id: no_rule
    type: assertion
    severity: critical
"""


def write(tmp_path: Path, name: str, text: str) -> Path:  # helper: create a file in tmp_path
    path = tmp_path / name  # destination file
    path.write_text(text, encoding="utf-8")  # write the content
    return path  # caller passes it to the CLI


def test_valid_example_exits_zero(capsys):  # the shipped example passes
    assert main(["validate", str(EXAMPLE)]) == EXIT_OK  # success exit code
    out = capsys.readouterr().out  # captured stdout
    assert "valid" in out and "0 invalid" in out  # confirmation and summary


def test_invalid_file_exits_one_with_line_numbers(tmp_path, capsys):  # errors point at lines
    path = write(tmp_path, "bad.rubric.yaml", BROKEN)  # the broken rubric
    assert main(["validate", str(path)]) == EXIT_INVALID  # CI-failing exit code
    out = capsys.readouterr().out  # captured stdout
    assert f"{path}:2: id:" in out  # bad id reported on line 2
    assert f"{path}:8: criteria[0].scale:" in out  # one-level scale reported where it starts
    assert f"{path}:11: criteria[1].severity:" in out  # bad severity on line 11
    assert "1 invalid" in out  # summary counts the failed file


def test_missing_field_points_at_parent(tmp_path, capsys):  # required fields can't be pointed at
    path = write(tmp_path, "bad.rubric.yaml", BROKEN)  # `no_rule` lacks `rule`
    main(["validate", str(path)])  # run the check
    assert f"{path}:9: criteria[1]:" in capsys.readouterr().out  # reported on the item's line


def test_yaml_syntax_error_is_reported_not_raised(tmp_path, capsys):  # malformed YAML
    path = write(tmp_path, "syntax.rubric.yaml", "spec: '0.1'\nid: [unclosed\n")  # broken YAML
    assert main(["validate", str(path)]) == EXIT_INVALID  # handled as an invalid file
    assert "YAML syntax error" in capsys.readouterr().out  # clear message


def test_empty_file_is_invalid(tmp_path, capsys):  # an empty file isn't a rubric
    path = write(tmp_path, "empty.rubric.yaml", "")  # zero bytes
    assert main(["validate", str(path)]) == EXIT_INVALID  # fails
    assert "file is empty" in capsys.readouterr().out  # explains why


def test_folder_is_searched_for_rubric_files(tmp_path, capsys):  # directories expand
    nested = tmp_path / "rubrics" / "agents"  # a nested folder
    nested.mkdir(parents=True)  # create it
    shutil.copy(EXAMPLE, nested / "refund-agent.rubric.yaml")  # a valid rubric inside
    write(tmp_path, "notes.yaml", "not: a rubric")  # ignored: doesn't match *.rubric.yaml
    assert main(["validate", str(tmp_path)]) == EXIT_OK  # only the rubric is checked
    assert "1 file(s) checked" in capsys.readouterr().out  # exactly one file found


def test_missing_path_exits_two(tmp_path, capsys):  # typo in a filename
    assert main(["validate", str(tmp_path / "nope.rubric.yaml")]) == EXIT_USAGE  # usage error
    assert "no such file" in capsys.readouterr().err  # explained on stderr


def test_folder_without_rubrics_exits_two(tmp_path, capsys):  # nothing to check
    assert main(["validate", str(tmp_path)]) == EXIT_USAGE  # usage error
    assert "no *.rubric.yaml files found" in capsys.readouterr().err  # explained on stderr


def test_json_output(tmp_path, capsys):  # machine-readable output
    good = EXAMPLE  # one valid file
    bad = write(tmp_path, "bad.rubric.yaml", BROKEN)  # one invalid file
    assert main(["validate", "--format", "json", str(good), str(bad)]) == EXIT_INVALID
    payload = json.loads(capsys.readouterr().out)  # must be valid JSON
    assert [item["valid"] for item in payload] == [True, False]  # one per file, in order
    lines = {e["line"] for e in payload[1]["errors"]}  # every error carries a line
    assert {2, 8, 11} <= lines  # the known problem lines are present
