"""Load rubric files and check them against the rubricate JSON Schema."""  # module docstring

from __future__ import annotations  # modern type hints on Python 3.10

import json  # parses the bundled JSON Schema file
from dataclasses import dataclass  # lightweight container for validation errors
from functools import lru_cache  # load the schema once, then reuse it
from importlib import resources  # reads files shipped inside the installed package
from pathlib import Path  # filesystem paths that work on every OS
from typing import Any  # "any type" marker for parsed YAML data

import yaml  # PyYAML: turns .rubric.yaml text into Python dicts and lists
from jsonschema import Draft202012Validator  # validator matching the schema's draft version

SPEC_VERSION = "0.1"  # the spec version this release of rubricate understands


@dataclass(frozen=True)  # immutable so errors can be safely shared and compared
class SchemaError:  # one problem found in a rubric file
    path: str  # where in the file the problem is, e.g. "criteria[0].scale"
    message: str  # human-readable explanation of what's wrong

    def __str__(self) -> str:  # how the error prints in CLI output
        # root-level errors have no path, so print just the message
        return f"{self.path}: {self.message}" if self.path else self.message


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
    # simplify each library error into a path + message pair
    return [SchemaError(_format_path(e.absolute_path), e.message) for e in errors]
