"""Tests for `rubricate init` and the starter rubric."""  # docstring for the test module

from pathlib import Path  # building paths inside pytest's tmp_path

import pytest  # parametrize

from rubricate.cli import main  # the function behind the `rubricate` command
from rubricate.lint import lint_file  # the starter must lint clean
from rubricate.spec import check_file  # ...and validate
from rubricate.starter import DEFAULT_ID, rubric_id_for, starter_rubric


def test_init_writes_a_rubric_that_passes_strict_lint(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # the default path is relative to the working folder
    assert main(["init"]) == 0
    path = tmp_path / "starter.rubric.yaml"
    assert path.is_file()
    assert "wrote starter.rubric.yaml" in capsys.readouterr().out
    assert check_file(path).ok  # valid against the schema
    report = lint_file(path, frozenset())
    assert report.errors == 0 and report.warnings == 0  # what `lint --strict` needs
    assert main(["lint", "--strict", str(path)]) == 0


def test_starter_has_a_scored_criterion_and_a_checkable_assertion():
    text = starter_rubric()
    assert "scale:" in text and "examples:" in text  # anchors and worked examples
    assert "type: assertion" in text and "check:" in text  # enforceable by `rubricate check`


def test_init_refuses_to_overwrite_without_force(tmp_path, capsys):
    path = tmp_path / "mine.rubric.yaml"
    path.write_text("keep me", encoding="utf-8")
    assert main(["init", str(path)]) == 2
    assert "already exists" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "keep me"  # untouched
    assert main(["init", str(path), "--force"]) == 0
    assert "id: mine" in path.read_text(encoding="utf-8")


def test_init_into_a_folder_uses_the_default_name(tmp_path):
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "starter.rubric.yaml").is_file()


def test_init_does_not_create_missing_folders(tmp_path, capsys):
    assert main(["init", str(tmp_path / "nope" / "x.rubric.yaml")]) == 2
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("support.rubric.yaml", "support"),
        ("Support Bot.rubric.yaml", "support-bot"),
        ("rag_faithfulness.yaml", "rag_faithfulness"),
        ("2024.rubric.yaml", DEFAULT_ID),  # ids must start with a letter
        ("!!!.rubric.yaml", DEFAULT_ID),
    ],
)
def test_rubric_id_comes_from_the_file_name(name, expected):
    assert rubric_id_for(Path(name)) == expected
