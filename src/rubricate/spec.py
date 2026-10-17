"""Load rubric files and check them against the rubricate JSON Schema."""  # module docstring

from __future__ import annotations  # modern type hints on Python 3.10

import json  # parses the bundled JSON Schema file
from dataclasses import dataclass, field, replace  # lightweight containers for results
from functools import lru_cache  # load the schema once, then reuse it
from importlib import resources  # reads files shipped inside the installed package
from pathlib import Path  # filesystem paths that work on every OS
from typing import Any  # "any type" marker for parsed YAML data

import yaml  # PyYAML: turns .rubric.yaml text into Python dicts and lists
from jsonschema import Draft202012Validator  # validator matching the schema's draft version

from rubricate.locate import compose, line_for  # map error locations to line numbers

SPEC_VERSION = "0.1"  # the spec version this release of rubricate understands


@dataclass(frozen=True)  # immutable so errors can be safely shared and compared
class SchemaError:  # one problem found in a rubric file
    path: str  # where in the file the problem is, e.g. "criteria[0].scale"
    message: str  # human-readable explanation of what's wrong
    parts: tuple[str | int, ...] = ()  # the same location as raw steps, used to find the line
    line: int | None = None  # 1-based line number in the source file, when known

    def __str__(self) -> str:  # how the error prints in CLI output
        # root-level errors have no path, so print just the message
        return f"{self.path}: {self.message}" if self.path else self.message


@dataclass(frozen=True)  # result of checking one file on disk
class FileReport:
    path: Path  # the file that was checked
    errors: list[SchemaError] = field(default_factory=list)  # problems found; empty means valid
    data: Any = field(default=None, repr=False)  # parsed rubric, kept so later checks reuse it
    root: Any = field(default=None, repr=False)  # YAML node tree, kept for line-number lookups

    @property
    def ok(self) -> bool:  # True when the file passed every check
        return not self.errors  # valid if there are no errors


@lru_cache(maxsize=1)  # the schema never changes at runtime, so read it only once
def load_schema() -> dict[str, Any]:  # returns the JSON Schema as a dict
    # the schema file shipped inside the installed package
    schema_file = resources.files("rubricate") / "schema" / "rubric.schema.json"
    text = schema_file.read_text(encoding="utf-8")  # read it as UTF-8 text
    return json.loads(text)  # parse JSON into a Python dict


def _normalize(data: Any) -> Any:  # makes YAML output match what JSON Schema expects
    if isinstance(data, dict):  # for mappings...
        # ...YAML int keys (1:, 3:) become strings ("1", "3")
        return {str(k): _normalize(v) for k, v in data.items()}
    if isinstance(data, list):  # for sequences...
        return [_normalize(item) for item in data]  # ...normalize each item
    return data  # strings, numbers, bools pass through unchanged


def load_rubric(path: str | Path) -> dict[str, Any]:  # read a .rubric.yaml file from disk
    text = Path(path).read_text(encoding="utf-8")  # load the raw file text
    data = yaml.safe_load(text)  # parse YAML safely (no arbitrary object construction)
    return _normalize(data)  # return a JSON-compatible dict


def _format_path(parts: Any) -> str:  # turns ["criteria", 0, "scale"] into "criteria[0].scale"
    out = ""  # build the path string piece by piece
    for part in parts:  # walk each step of the path
        if isinstance(part, int):  # list positions...
            out += f"[{part}]"  # ...print as [index]
        else:  # dict keys...
            out += f".{part}" if out else str(part)  # ...print as .key (no leading dot)
    return out  # the finished path


def validate(data: Any) -> list[SchemaError]:  # check parsed rubric data against the schema
    validator = Draft202012Validator(load_schema())  # build a validator for the bundled schema
    errors = sorted(  # sort so output order is stable between runs
        validator.iter_errors(data),  # collect every violation, not just the first
        key=lambda e: list(map(str, e.absolute_path)),  # order by location in the file
    )
    return [  # simplify each library error into path, message, and raw location steps
        SchemaError(_format_path(e.absolute_path), _friendly(e), tuple(e.absolute_path))
        for e in errors
    ]


def _friendly(err: Any) -> str:  # rewrite common jsonschema messages in plain language
    parts = list(err.absolute_path)  # where the error is, as raw steps
    last = parts[-1] if parts else None  # the field the error is about
    if err.validator == "const" and last == "spec":  # wrong spec version
        return f"unsupported spec version {err.instance!r}; this rubricate reads {SPEC_VERSION!r}"
    if err.validator == "pattern" and last == "scale":  # bad key inside a scale
        return f"score level {err.instance!r} must be a whole number (0, 1, 2, ...)"
    if err.validator == "pattern":  # every other pattern in the schema is an identifier
        return (
            f"{err.instance!r} is not a valid id: start with a lowercase letter and use "
            "only lowercase letters, digits, '-' or '_'"
        )
    if err.validator == "minProperties" and last == "scale":  # too few levels
        return f"needs at least {err.validator_value} score levels, found {len(err.instance)}"
    if err.validator == "required":  # missing field: jsonschema's wording is already clear
        return err.message  # e.g. "'rule' is a required property"
    if err.validator == "additionalProperties":  # unknown or misplaced field
        return err.message.replace("Additional properties are not allowed", "unknown field(s)")
    return err.message  # fall back to the library's own wording


def check_file(path: str | Path) -> FileReport:  # validate one file and attach line numbers
    path = Path(path)  # accept str or Path
    text = path.read_text(encoding="utf-8")  # raw text, needed for both parsing and line lookup
    try:  # YAML syntax errors are reported, not raised
        data = _normalize(yaml.safe_load(text))  # parse into plain data for the schema check
        root = compose(text)  # parse again into nodes that remember their line numbers
    except yaml.YAMLError as exc:  # malformed YAML (bad indentation, unclosed quote, ...)
        mark = getattr(exc, "problem_mark", None)  # where PyYAML noticed the problem, if known
        line = mark.line + 1 if mark is not None else None  # convert 0-based to 1-based
        problem = getattr(exc, "problem", None) or str(exc)  # short description of the problem
        return FileReport(path, [SchemaError("", f"YAML syntax error: {problem}", (), line)])
    if data is None:  # an empty file parses to None
        return FileReport(path, [SchemaError("", "file is empty", (), 1)])
    errors = [  # schema errors, each tagged with the line it points at
        replace(err, line=line_for(root, err.parts)) for err in validate(data)
    ]
    errors.sort(key=lambda e: (e.line or 0, e.path))  # report in file order, top to bottom
    return FileReport(path, errors, data, root)  # keep the parse for the linter
