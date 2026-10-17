"""Tests for agent traces and `rubricate check` (trajectory assertions)."""

import json  # parse JSON output
from pathlib import Path  # repo paths

import pytest  # fixtures, parametrize

from rubricate.check import FAIL, PASS, UNCHECKED, check_trace, evaluate  # code under test
from rubricate.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main  # the CLI
from rubricate.spec import load_rubric  # the example rubric
from rubricate.trace import TraceError, load_traces, parse_trace  # trace loading

ROOT = Path(__file__).resolve().parent.parent
RUBRIC = ROOT / "examples" / "refund-agent.rubric.yaml"
TRACES = ROOT / "examples" / "traces" / "refund-runs.jsonl"


def run(*calls):  # helper: a trace made of tool calls, e.g. run(("issue_refund", {"amount": 5}))
    steps = [{"type": "tool_call", "name": n, "args": a} for n, a in calls]
    return parse_trace({"id": "t", "steps": steps}, "test")


GATE = {  # the refund example's approval rule
    "kind": "requires_before",
    "tool": "issue_refund",
    "requires": "human_approval",
    "where": {"amount": {"gt": 100}},
}


# ---------------------------------------------------------------- check kinds


def test_requires_before():
    ok, *_ = evaluate(GATE, run(("human_approval", {}), ("issue_refund", {"amount": 150})))
    assert ok  # approval came first
    ok, detail, step = evaluate(GATE, run(("issue_refund", {"amount": 150})))
    assert not ok and step == 0 and "no earlier human_approval" in detail
    ok, *_ = evaluate(GATE, run(("issue_refund", {"amount": 50})))
    assert ok  # under the threshold: approval not needed


def test_approval_after_the_refund_does_not_count():  # order matters
    ok, *_ = evaluate(GATE, run(("issue_refund", {"amount": 150}), ("human_approval", {})))
    assert not ok


def test_forbidden_required_and_max_calls():
    trace = run(("search", {}), ("search", {}), ("delete_account", {"user": "u1"}))
    assert not evaluate({"kind": "forbidden", "tool": "delete_account"}, trace)[0]
    assert evaluate({"kind": "required", "tool": "search"}, trace)[0]
    assert not evaluate({"kind": "required", "tool": "escalate"}, trace)[0]
    assert evaluate({"kind": "max_calls", "tool": "search", "max": 2}, trace)[0]
    assert not evaluate({"kind": "max_calls", "max": 2}, trace)[0]  # no tool: all calls count


@pytest.mark.parametrize(
    "where, expected",
    [
        ({"amount": {"gte": 100}}, True),
        ({"amount": {"lt": 100}}, False),
        ({"customer.tier": {"in": ["gold", "platinum"]}}, True),  # dotted path into nested args
        ({"customer.tier": {"eq": "silver"}}, False),
        ({"currency": {"eq": "USD"}}, False),  # missing argument never matches
        ({"note": {"gt": 5}}, False),  # text can't be compared to a number
    ],
)
def test_where_conditions(where, expected):
    trace = run(("issue_refund", {"amount": 100, "note": "x", "customer": {"tier": "gold"}}))
    assert (
        evaluate({"kind": "required", "tool": "issue_refund", "where": where}, trace)[0] is expected
    )


# ---------------------------------------------------------------- the refund example


def test_refund_example_outcomes():
    rubric = load_rubric(RUBRIC)
    results = {t.id: check_trace(rubric, t) for t in load_traces(TRACES)}
    assert results["run-approved"].blocked is False
    assert results["run-skipped-approval"].blocked is True  # the headline demo
    assert results["run-small-refund"].blocked is False  # $18 needs no approval
    assert results["run-retry-loop"].warnings == 1  # 4 lookups, budget 3


def test_assertion_without_check_is_unchecked():
    rubric = load_rubric(RUBRIC)
    del rubric["criteria"][2]["check"]  # approval_gate becomes plain language only
    status = {r.id: r.status for r in check_trace(rubric, run()).results}
    assert status == {"approval_gate": UNCHECKED, "lookup_budget": PASS}


def test_final_message():
    trace = load_traces(TRACES)[1]  # run-skipped-approval
    assert trace.final_message.startswith("Done! I've refunded")


# ---------------------------------------------------------------- trace loading


def test_bad_traces_report_their_location(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"steps": []}\n{"steps": [{"type": "tool_call"}]}\n', encoding="utf-8")
    with pytest.raises(TraceError, match=r"bad\.jsonl:2: step 0 \(tool_call\) needs a tool"):
        load_traces(bad)


def test_json_file_with_one_run(tmp_path):
    single = tmp_path / "one.json"
    single.write_text(json.dumps({"id": "solo", "steps": []}), encoding="utf-8")
    assert [t.id for t in load_traces(single)] == ["solo"]


# ---------------------------------------------------------------- CLI


def test_cli_blocks_on_failed_blocker(capsys):
    assert main(["check", str(RUBRIC), str(TRACES)]) == EXIT_INVALID
    out = capsys.readouterr().out
    assert "run-skipped-approval: BLOCKED" in out
    assert "4 run(s) checked: 1 blocked, 1 with warnings" in out


def test_cli_warnings_pass_unless_strict(tmp_path):
    lines = [ln for ln in TRACES.read_text().splitlines() if '"run-retry-loop"' in ln]
    only_warning = tmp_path / "w.jsonl"
    only_warning.write_text(lines[0] + "\n", encoding="utf-8")
    assert main(["check", str(RUBRIC), str(only_warning)]) == EXIT_OK
    assert main(["check", "--strict", str(RUBRIC), str(only_warning)]) == EXIT_INVALID


def test_cli_json(capsys):
    main(["check", "--format", "json", str(RUBRIC), str(TRACES)])
    payload = json.loads(capsys.readouterr().out)
    blocked = {r["trace"]: r["blocked"] for r in payload}
    assert blocked["run-skipped-approval"] is True
    gate = payload[1]["results"][0]
    assert gate["status"] == FAIL and gate["step"] == 3


def test_cli_rubric_without_assertions_is_usage_error(capsys):
    weak = ROOT / "examples" / "lint-demo" / "weak-support.rubric.yaml"
    assert main(["check", str(weak), str(TRACES)]) == EXIT_USAGE
    assert "no assertions" in capsys.readouterr().err
