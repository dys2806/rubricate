"""Agent traces: the recorded steps of one agent run (messages, tool calls, tool results)."""

from __future__ import annotations  # modern type hints on Python 3.10

import json  # traces are stored as JSON
from dataclasses import dataclass, field  # small records
from pathlib import Path  # filesystem paths
from typing import Any  # free-form tool arguments

STEP_TYPES = ("message", "tool_call", "tool_result")  # the kinds of step a trace can hold


class TraceError(ValueError):  # a trace file that can't be read, with a precise location
    pass


@dataclass(frozen=True)
class Step:  # one thing that happened during the run
    index: int  # position in the run, starting at 0
    type: str  # "message", "tool_call", or "tool_result"
    name: str | None = None  # tool name, for tool steps
    args: dict[str, Any] = field(default_factory=dict)  # tool arguments, for tool calls
    role: str | None = None  # "user" or "assistant", for messages
    content: Any = None  # message text or tool output


@dataclass(frozen=True)
class Trace:  # one complete agent run
    id: str  # run identifier, carried into every report
    steps: list[Step]  # what happened, in order

    def tool_calls(self, name: str | None = None) -> list[Step]:  # calls, optionally one tool
        return [s for s in self.steps if s.type == "tool_call" and (name is None or s.name == name)]

    @property
    def final_message(self) -> str | None:  # the agent's last reply, for judge scoring
        for step in reversed(self.steps):  # search from the end
            if step.type == "message" and step.role == "assistant":
                return step.content if isinstance(step.content, str) else json.dumps(step.content)
        return None  # the agent never replied


def parse_trace(data: Any, where: str) -> Trace:  # turn one JSON object into a Trace
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise TraceError(f'{where}: a trace needs a "steps" list')
    steps = []  # validated steps
    for i, raw in enumerate(data["steps"]):  # check each step's shape
        if not isinstance(raw, dict) or raw.get("type") not in STEP_TYPES:
            raise TraceError(f"{where}: step {i} needs a type of {', '.join(STEP_TYPES)}")
        if raw["type"] in ("tool_call", "tool_result") and not isinstance(raw.get("name"), str):
            raise TraceError(f'{where}: step {i} ({raw["type"]}) needs a tool "name"')
        args = raw.get("args", {})  # tool arguments default to none
        if not isinstance(args, dict):
            raise TraceError(f'{where}: step {i} "args" must be an object')
        content = raw.get("content", raw.get("output"))  # tool results may use "output"
        steps.append(Step(i, raw["type"], raw.get("name"), args, raw.get("role"), content))
    return Trace(str(data.get("id", where)), steps)  # default id: where it came from


def load_traces(path: str | Path) -> list[Trace]:  # read a .json (one run) or .jsonl (many)
    path = Path(path)  # accept str or Path
    text = path.read_text(encoding="utf-8")  # raw file contents
    if path.suffix == ".jsonl":  # one run per line
        traces = []
        for n, line in enumerate(text.splitlines(), start=1):  # 1-based line numbers
            if not line.strip():  # blank lines are fine
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceError(f"{path}:{n}: not valid JSON ({exc.msg})") from exc
            traces.append(parse_trace(data, f"{path}:{n}"))
        return traces
    try:  # a single JSON document: one run, or a list of runs
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TraceError(f"{path}:{exc.lineno}: not valid JSON ({exc.msg})") from exc
    items = data if isinstance(data, list) else [data]  # normalize to a list
    return [parse_trace(item, f"{path}[{i}]") for i, item in enumerate(items)]
