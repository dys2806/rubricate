"""Tests for loading rubric files and validating them against the JSON Schema."""

import copy  # deep copies so each test mutates its own rubric
from pathlib import Path  # builds paths to files in the repo

import pytest  # fixtures and parametrized tests

from rubricate.spec import load_rubric, load_schema, validate  # functions under test

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"  # the repo's examples/ folder


@pytest.fixture  # gives each test a fresh copy of the example rubric
def rubric():
    # parsed refund-agent example, copied so tests can't affect each other
    return copy.deepcopy(load_rubric(EXAMPLES / "refund-agent.rubric.yaml"))


def test_schema_is_bundled_and_parses():  # the schema ships inside the package
    assert load_schema()["title"] == "rubricate rubric"  # loaded and is the right file


def test_yaml_integer_scale_keys_are_normalized(rubric):  # YAML `1:` keys become strings
    assert set(rubric["criteria"][0]["scale"]) == {"1", "3", "5"}  # JSON Schema needs string keys


# run once for every example rubric in the repo
@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.rubric.yaml")))
def test_all_examples_are_valid(path):  # shipped examples must always pass
    assert validate(load_rubric(path)) == []  # no schema errors


def test_missing_required_field_is_reported(rubric):  # `subject` is required
    del rubric["subject"]  # remove it
    errors = validate(rubric)  # validate the broken rubric
    assert any("subject" in e.message for e in errors)  # the error names the missing field


def test_wrong_spec_version_is_rejected(rubric):  # files must declare a version we understand
    rubric["spec"] = "9.9"  # an unknown version
    assert [e.path for e in validate(rubric)] == ["spec"]  # exactly one error, at the spec field


def test_scale_needs_at_least_two_levels(rubric):  # a one-level scale can't discriminate
    rubric["criteria"][0]["scale"] = {"1": "Only level"}  # shrink the scale
    assert any(e.path == "criteria[0].scale" for e in validate(rubric))  # flagged at the scale


def test_non_integer_scale_key_is_rejected(rubric):  # levels must be whole numbers
    rubric["criteria"][0]["scale"]["high"] = "Not a number"  # add a bad key
    assert any(e.path == "criteria[0].scale" for e in validate(rubric))  # flagged at the scale


def test_assertion_requires_a_rule(rubric):  # assertions are useless without a rule
    del rubric["criteria"][2]["rule"]  # remove the rule from approval_gate
    assert any(e.path == "criteria[2]" for e in validate(rubric))  # flagged on that criterion


def test_assertion_rejects_scale(rubric):  # assertions are pass/fail, not scored
    rubric["criteria"][2]["scale"] = {"1": "a", "5": "b"}  # mix up the two kinds
    assert any(e.path == "criteria[2]" for e in validate(rubric))  # flagged as an unknown field


def test_unknown_severity_is_rejected(rubric):  # only blocker and warning exist
    rubric["criteria"][2]["severity"] = "critical"  # an unsupported value
    assert any(e.path == "criteria[2].severity" for e in validate(rubric))  # flagged at severity


def test_bad_identifier_is_rejected(rubric):  # ids must be lowercase slugs
    rubric["id"] = "Refund Agent"  # spaces and capitals
    assert [e.path for e in validate(rubric)] == ["id"]  # exactly one error, at id


def test_zero_weight_is_rejected(rubric):  # weight must be positive
    rubric["criteria"][0]["weight"] = 0  # zero weight would silently drop the criterion
    assert any(e.path == "criteria[0].weight" for e in validate(rubric))  # flagged at weight
