"""Tests for `rubricate score`: prompts, reply validation, the CLI, and a live judge call."""

import copy  # fresh rubric per test
import json  # parse CLI JSON output
import os  # check whether a real API key is available
from pathlib import Path  # paths to repo files

import pytest  # fixtures, markers, skips

from rubricate.cli import EXIT_OK, EXIT_USAGE, main  # the CLI
from rubricate.judge import JudgeError  # raised on any judge problem
from rubricate.score import build_prompt, parse_response, response_schema  # pure functions
from rubricate.spec import load_rubric  # load the example rubric

ROOT = Path(__file__).resolve().parent.parent  # repo root
EXAMPLE = ROOT / "examples" / "refund-agent.rubric.yaml"  # 2 scored criteria + 1 assertion
HAS_KEY = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))  # live?


@pytest.fixture
def rubric():  # a fresh copy of the example for each test
    return copy.deepcopy(load_rubric(EXAMPLE))


def reply(policy=5, tone=3):  # the shape a judge returns, for testing validation logic only
    return {
        "scores": [
            {"id": "policy_accuracy", "score": policy, "rationale": "Cites section 4.2."},
            {"id": "tone", "score": tone, "rationale": "Apologizes twice."},
        ]
    }


# ---------------------------------------------------------------- prompt and schema


def test_prompt_contains_anchors_examples_and_response(rubric):
    prompt = build_prompt(rubric, "Refunds within 30 days.", input_text="Can I return this?")
    assert "## Criterion `policy_accuracy`" in prompt  # every scored criterion
    assert "- 3: States the window and amount correctly" in prompt  # anchors, in order
    assert "Example scored 1:" in prompt and "Why:" in prompt  # worked examples + rationale
    assert "Can I return this?" in prompt  # the original input
    assert prompt.rstrip().endswith("Grade the response on every criterion above.")


def test_prompt_excludes_assertions(rubric):  # assertions aren't graded by the judge
    assert "approval_gate" not in build_prompt(rubric, "x")


def test_schema_restricts_ids_to_scored_criteria(rubric):
    ids = response_schema(rubric)["properties"]["scores"]["items"]["properties"]["id"]["enum"]
    assert ids == ["policy_accuracy", "tone"]  # no assertion ids


# ---------------------------------------------------------------- reply validation


def test_valid_reply_and_weighted_score(rubric):
    result = parse_response(rubric, reply(policy=5, tone=3), "gemini:test")
    assert [c.score for c in result.criteria] == [5, 3]  # both criteria
    assert result.skipped == ["approval_gate", "lookup_budget"]  # assertions reported as skipped
    # policy 5/5 -> 1.0 at weight 0.5; tone 3 on 1..5 -> 0.5 at weight 0.2
    assert result.weighted == pytest.approx((0.5 * 1.0 + 0.2 * 0.5) / 0.7)


def test_in_between_score_is_allowed(rubric):  # 1/3/5 scale, judge gives 4
    assert parse_response(rubric, reply(policy=4), "j").criteria[0].score == 4


@pytest.mark.parametrize("bad", [0, 6, 3.5, "5", True, None])
def test_out_of_range_or_non_integer_score_is_rejected(rubric, bad):
    with pytest.raises(JudgeError, match="outside the scale"):
        parse_response(rubric, reply(policy=bad), "j")


def test_missing_criterion_is_rejected(rubric):
    data = reply()
    data["scores"].pop()  # drop tone
    with pytest.raises(JudgeError, match="did not score criterion 'tone'"):
        parse_response(rubric, data, "j")


def test_duplicate_and_unknown_criteria_are_rejected(rubric):
    dup = reply()
    dup["scores"].append(dup["scores"][0])  # policy twice
    with pytest.raises(JudgeError, match="more than once"):
        parse_response(rubric, dup, "j")
    extra = reply()
    extra["scores"].append({"id": "made_up", "score": 3, "rationale": ""})
    with pytest.raises(JudgeError, match="unknown criteria: made_up"):
        parse_response(rubric, extra, "j")


# ---------------------------------------------------------------- CLI (no model calls)


def test_missing_key_is_a_clear_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # make sure no key is visible
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert main(["score", str(EXAMPLE), "--output", "hi"]) == EXIT_USAGE
    err = capsys.readouterr().err
    assert "GEMINI_API_KEY" in err or "pip install" in err  # tells the user what to do


def test_invalid_rubric_is_refused(tmp_path, capsys):  # never grade against a broken rubric
    bad = tmp_path / "bad.rubric.yaml"
    bad.write_text('spec: "0.1"\nid: x\n', encoding="utf-8")
    assert main(["score", str(bad), "--output", "hi"]) == EXIT_USAGE
    assert "fix the rubric first" in capsys.readouterr().err


def test_malformed_batch_is_refused(tmp_path, capsys):
    batch = tmp_path / "b.jsonl"
    batch.write_text('{"output": "ok"}\n{"input": "no output field"}\n', encoding="utf-8")
    assert main(["score", str(EXAMPLE), "--batch", str(batch)]) == EXIT_USAGE
    assert f"{batch}:2:" in capsys.readouterr().err  # points at the bad line


def test_unknown_provider_is_refused(capsys):
    assert main(["score", str(EXAMPLE), "--output", "hi", "--judge", "nope:x"]) == EXIT_USAGE
    assert "unknown judge provider" in capsys.readouterr().err


# ---------------------------------------------------------------- live: real Gemini call


@pytest.mark.live
@pytest.mark.skipif(not HAS_KEY, reason="set GEMINI_API_KEY to run the live judge test")
def test_live_gemini_scores_a_strong_and_a_weak_reply(capsys):
    strong = (
        "Under section 4.2 of our refund policy, you can get a full refund within 30 days "
        "of purchase as long as you have the receipt. Sorry the blender arrived cracked."
    )
    weak = "You can return it anytime for a full refund!"
    results = {}
    for name, text in (("strong", strong), ("weak", weak)):
        assert main(["score", str(EXAMPLE), "--output", text, "--format", "json"]) == EXIT_OK
        results[name] = json.loads(capsys.readouterr().out)
    policy = {k: v["criteria"][0]["score"] for k, v in results.items()}  # policy_accuracy
    assert policy["strong"] > policy["weak"]  # a real judge must rank them correctly
    assert results["strong"]["judge"].startswith("gemini:")
