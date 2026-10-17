"""Evaluate a rubric's assertions against agent traces: deterministic, no model calls."""

from __future__ import annotations  # modern type hints on Python 3.10

import operator  # standard comparison functions (>, <, ==, ...)
from dataclasses import dataclass, field  # result records
from typing import Any  # parsed rubric data

from rubricate.trace import Step, Trace  # recorded agent runs

PASS, FAIL, UNCHECKED = "pass", "fail", "unchecked"  # possible outcomes of one assertion


@dataclass(frozen=True)
class AssertionResult:  # the outcome of one assertion on one run
    id: str  # assertion id from the rubric
    rule: str  # its plain-language rule, for the report
    severity: str  # "blocker" or "warning"
    status: str  # PASS, FAIL, or UNCHECKED (no machine-checkable `check` given)
    detail: str = ""  # why it failed, citing the step
    step: int | None = None  # index of the offending step, when there is one


@dataclass(frozen=True)
class RunResult:  # every assertion on one run
    trace_id: str  # which run
    results: list[AssertionResult] = field(default_factory=list)

    @property
    def blocked(self) -> bool:  # True if any blocker failed: the run fails outright
        return any(r.status == FAIL and r.severity == "blocker" for r in self.results)

    @property
    def warnings(self) -> int:  # failed warning-level assertions
        return sum(r.status == FAIL and r.severity == "warning" for r in self.results)


OPS = {  # comparison name in a `where` condition -> the function that performs it
    "eq": operator.eq,  # equal
    "ne": operator.ne,  # not equal
    "gt": operator.gt,  # greater than
    "gte": operator.ge,  # greater than or equal
    "lt": operator.lt,  # less than
    "lte": operator.le,  # less than or equal
    "in": lambda value, options: value in options,  # one of a list of values
}

_MISSING = object()  # marker for "argument not present"; never equal to any real value


def _get(args: dict[str, Any], dotted: str) -> Any:  # read "customer.tier" from nested args
    value: Any = args  # start at the top
    for key in dotted.split("."):  # step through each level
        if not isinstance(value, dict) or key not in value:
            return _MISSING  # the argument isn't there
        value = value[key]
    return value


def _matches(step: Step, where: dict[str, Any] | None) -> bool:  # do the args meet `where`?
    if not where:  # no conditions: every call matches
        return True
    for arg, conds in where.items():  # every argument condition must hold
        value = _get(step.args, arg)
        if value is _MISSING:  # a call without the argument can't satisfy a condition on it
            return False
        for op, target in conds.items():
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            if op in ("gt", "gte", "lt", "lte") and not numeric:  # can't compare text to 100
                return False
            ok = OPS[op](value, target)  # run the comparison, e.g. value > 100
            if not ok:
                return False
    return True  # every condition held


def _describe(where: dict[str, Any] | None) -> str:  # " where amount > 100", for messages
    if not where:
        return ""
    symbols = {"eq": "==", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "in": "in"}
    parts = [f"{arg} {symbols[op]} {val!r}" for arg, c in where.items() for op, val in c.items()]
    return " where " + " and ".join(parts)


def evaluate(check: dict[str, Any], trace: Trace) -> tuple[bool, str, int | None]:
    kind, where = check["kind"], check.get("where")  # what to test, and on which calls
    cond = _describe(where)  # human-readable filter for messages
    if kind == "requires_before":  # every matching `tool` call must follow a `requires` call
        seen_required = False  # has the prerequisite happened yet?
        for step in trace.steps:  # walk the run in order
            if step.type != "tool_call":
                continue
            if step.name == check["requires"]:
                seen_required = True
            elif step.name == check["tool"] and _matches(step, where) and not seen_required:
                return (
                    False,
                    f"{check['tool']} called at step {step.index}{cond} "
                    f"with no earlier {check['requires']}",
                    step.index,
                )
        return True, "", None
    if kind == "forbidden":  # matching calls must never happen
        hits = [s for s in trace.tool_calls(check["tool"]) if _matches(s, where)]
        if hits:
            return False, f"{check['tool']} called at step {hits[0].index}{cond}", hits[0].index
        return True, "", None
    if kind == "required":  # at least one matching call must happen
        if any(_matches(s, where) for s in trace.tool_calls(check["tool"])):
            return True, "", None
        return False, f"{check['tool']} was never called{cond}", None
    if kind == "max_calls":  # a call budget, for one tool or all tools
        calls = [s for s in trace.tool_calls(check.get("tool")) if _matches(s, where)]
        if len(calls) > check["max"]:
            target = check.get("tool", "tool")
            over = calls[check["max"]]  # the first call past the budget
            return (
                False,
                f"{len(calls)} {target} calls{cond}, budget is {check['max']} "
                f"(exceeded at step {over.index})",
                over.index,
            )
        return True, "", None
    raise ValueError(f"unknown check kind {kind!r}")  # the schema prevents this


def check_trace(rubric: dict[str, Any], trace: Trace) -> RunResult:  # all assertions, one run
    results = []
    for crit in rubric["criteria"]:  # only assertions are checked here
        if crit.get("type") != "assertion":
            continue
        severity = crit.get("severity", "warning")  # schema default
        if "check" not in crit:  # plain-language only: needs a human or a later judge
            results.append(AssertionResult(crit["id"], crit["rule"], severity, UNCHECKED))
            continue
        ok, detail, step = evaluate(crit["check"], trace)
        status = PASS if ok else FAIL
        results.append(AssertionResult(crit["id"], crit["rule"], severity, status, detail, step))
    return RunResult(trace.id, results)
