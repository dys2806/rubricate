"""SARIF 2.1.0 output for lint results, so findings show up as GitHub code-scanning annotations."""

from __future__ import annotations  # modern type hints on Python 3.10

from pathlib import Path  # turn report paths into SARIF artifact URIs
from typing import Any  # JSON-shaped output

from rubricate import __version__  # reported as the tool version
from rubricate.lint import ERROR, RULES, LintReport  # rule catalog and results

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"  # where validators find the schema
SCHEMA_RULE_ID = "schema"  # rule id used for structural problems found by `validate`
INFO_URI = "https://github.com/dys2806/rubricate"  # tool home page
RULES_URI = INFO_URI + "/blob/main/docs/lint-rules.md"  # rule reference


def _level(severity: str) -> str:  # rubricate severity -> SARIF level
    return "error" if severity == ERROR else "warning"


def _uri(path: Path) -> str:  # relative paths stay relative (GitHub resolves them from the repo)
    return path.as_uri() if path.is_absolute() else path.as_posix()


def _location(path: Path, line: int | None) -> dict[str, Any]:  # one place in one file
    physical: dict[str, Any] = {"artifactLocation": {"uri": _uri(path)}}
    if line:  # SARIF lines are 1-based; leave the region out when the line is unknown
        physical["region"] = {"startLine": line}
    return {"physicalLocation": physical}


def _rule_descriptors() -> list[dict[str, Any]]:  # the schema check first, then every lint rule
    schema = {
        "id": SCHEMA_RULE_ID,
        "name": "schema-error",
        "shortDescription": {"text": "the rubric must follow the rubricate spec"},
        "helpUri": INFO_URI + "/blob/main/docs/spec.md",
        "defaultConfiguration": {"level": "error"},
    }
    rules = [
        {
            "id": rule.code,
            "name": rule.name,
            "shortDescription": {"text": rule.summary},
            "helpUri": RULES_URI,
            "defaultConfiguration": {"level": _level(rule.severity)},
        }
        for rule in RULES
    ]
    return [schema, *rules]


def to_sarif(reports: list[LintReport]) -> dict[str, Any]:  # one SARIF log for the whole run
    descriptors = _rule_descriptors()
    index = {d["id"]: i for i, d in enumerate(descriptors)}  # rule id -> position in the list
    results: list[dict[str, Any]] = []
    for report in reports:
        for err in report.schema_errors:  # structural problems
            text = f"{err.path}: {err.message}" if err.path else err.message
            results.append(
                {
                    "ruleId": SCHEMA_RULE_ID,
                    "ruleIndex": index[SCHEMA_RULE_ID],
                    "level": "error",
                    "message": {"text": text},
                    "locations": [_location(report.path, err.line)],
                }
            )
        for f in report.findings:  # rule findings
            results.append(
                {
                    "ruleId": f.code,
                    "ruleIndex": index[f.code],
                    "level": _level(f.severity),
                    "message": {"text": f"{f.path}: {f.message}"},
                    "locations": [_location(report.path, f.line)],
                }
            )
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "rubricate",
                        "version": __version__,
                        "informationUri": INFO_URI,
                        "rules": descriptors,
                    }
                },
                "results": results,
            }
        ],
    }
