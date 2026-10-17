"""Quality rules for rubrics: problems a schema can't catch but a careful reviewer would."""

from __future__ import annotations  # modern type hints on Python 3.10

import re  # word matching for the vague-wording and overlap rules
from collections.abc import Callable, Iterator  # types for rule functions and their results
from dataclasses import dataclass, field  # small immutable records
from itertools import pairwise  # (1, 3), (3, 5): neighboring score levels
from pathlib import Path  # filesystem paths
from typing import Any  # parsed YAML data

from rubricate.locate import line_for  # map a location in the rubric back to a line number
from rubricate.spec import FileReport, SchemaError, check_file  # structure check runs first

ERROR = "error"  # the rubric is broken or self-contradictory: fails the run
WARNING = "warning"  # the rubric works but will likely produce noisy scores


@dataclass(frozen=True)  # one problem found by a rule
class Finding:
    code: str  # stable rule id, e.g. "R003", for ignoring and documentation
    severity: str  # ERROR or WARNING
    path: str  # readable location, e.g. "criteria[0].scale.3"
    message: str  # what's wrong and how to fix it
    parts: tuple[str | int, ...] = ()  # raw location steps, used to find the line
    line: int | None = None  # 1-based line number, filled in after the rule runs


@dataclass(frozen=True)  # metadata for one rule, shown by `rubricate lint --list-rules`
class Rule:
    code: str  # stable id
    name: str  # short kebab-case name
    severity: str  # default severity
    summary: str  # one-line description
    check: Callable[[dict[str, Any]], Iterator[Finding]]  # the function that finds problems


@dataclass(frozen=True)  # everything lint found in one file
class LintReport:
    path: Path  # the file that was linted
    schema_errors: list[SchemaError] = field(default_factory=list)  # structural problems, if any
    findings: list[Finding] = field(default_factory=list)  # rule findings (empty if schema failed)

    @property
    def errors(self) -> int:  # count of error-severity problems (schema errors count as errors)
        return len(self.schema_errors) + sum(f.severity == ERROR for f in self.findings)

    @property
    def warnings(self) -> int:  # count of warning-severity findings
        return sum(f.severity == WARNING for f in self.findings)


def _path(parts: tuple[str | int, ...]) -> str:  # ("criteria", 0, "scale") -> "criteria[0].scale"
    out = ""  # build the string step by step
    for part in parts:  # walk each step
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out  # finished readable path


def _finding(code: str, sev: str, parts: tuple[str | int, ...], message: str) -> Finding:
    return Finding(code, sev, _path(parts), message, parts)  # helper so rules stay short


def _scored(rubric: dict[str, Any]) -> Iterator[tuple[int, dict[str, Any]]]:  # scored criteria only
    for i, crit in enumerate(rubric.get("criteria", [])):  # every criterion with its index
        if crit.get("type", "scored") == "scored":  # assertions have no scale or examples
            yield i, crit  # hand back position and criterion


# ---------------------------------------------------------------- rules


def duplicate_ids(rubric: dict[str, Any]) -> Iterator[Finding]:  # R001
    seen: dict[str, int] = {}  # criterion id -> index where it first appeared
    for i, crit in enumerate(rubric.get("criteria", [])):  # check every criterion
        cid = crit.get("id")  # this criterion's id
        if cid in seen:  # already used earlier in the file
            yield _finding(
                "R001",
                ERROR,
                ("criteria", i, "id"),
                f"criterion id {cid!r} is already used by criteria[{seen[cid]}]; "
                "ids must be unique",
            )
        else:
            seen[cid] = i  # remember the first use


def example_off_scale(rubric: dict[str, Any]) -> Iterator[Finding]:  # R002
    for i, crit in _scored(rubric):  # only scored criteria have examples
        levels = {int(k) for k in crit.get("scale", {})}  # valid score levels
        for j, ex in enumerate(crit.get("examples", [])):  # each worked example
            if ex.get("score") not in levels:  # the example uses a score the scale doesn't define
                yield _finding(
                    "R002",
                    ERROR,
                    ("criteria", i, "examples", j, "score"),
                    f"example score {ex.get('score')} is not a level on this scale "
                    f"(levels: {', '.join(map(str, sorted(levels)))})",
                )


def level_without_example(rubric: dict[str, Any]) -> Iterator[Finding]:  # R003
    for i, crit in _scored(rubric):  # every scored criterion
        covered = {ex.get("score") for ex in crit.get("examples", [])}  # levels that have examples
        for key in sorted(crit.get("scale", {}), key=int):  # each defined level, in order
            if int(key) not in covered:  # nobody showed what this level looks like
                yield _finding(
                    "R003",
                    WARNING,
                    ("criteria", i, "scale", key),
                    f"score {key} has no example; raters and judges agree far more often "
                    "when every level is illustrated",
                )


# Words that sound like criteria but leave the rater to guess what "good" means.
VAGUE_WORDS = (
    "good",
    "bad",
    "great",
    "poor",
    "nice",
    "fine",
    "okay",
    "ok",
    "decent",
    "appropriate",
    "inappropriate",
    "adequate",
    "inadequate",
    "reasonable",
    "sufficient",
    "insufficient",
    "satisfactory",
    "acceptable",
    "proper",
    "suitable",
    "high quality",
    "low quality",
    "somewhat",
    "fairly",
)
_VAGUE_RE = re.compile(  # one case-insensitive pattern that matches any vague word as a whole word
    r"\b(" + "|".join(re.escape(w) for w in VAGUE_WORDS) + r")\b", re.IGNORECASE
)


def vague_anchor(rubric: dict[str, Any]) -> Iterator[Finding]:  # R004
    for i, crit in _scored(rubric):  # every scored criterion
        for key, anchor in crit.get("scale", {}).items():  # each level's anchor text
            words = sorted({m.group(1).lower() for m in _VAGUE_RE.finditer(anchor)})  # matches
            if words:  # at least one vague word
                quoted = ", ".join(f"'{w}'" for w in words)  # e.g. 'good', 'appropriate'
                yield _finding(
                    "R004",
                    WARNING,
                    ("criteria", i, "scale", key),
                    f"anchor uses vague wording ({quoted}); describe what a rater can observe "
                    "instead, such as what is present, missing, or wrong",
                )


# Words that change how much, not what: two anchors separated only by these are a judgment call.
DEGREE_WORDS = frozenset(
    {
        "mostly", "largely", "partially", "partly", "fully", "completely", "entirely",
        "very", "highly", "extremely", "slightly", "somewhat", "fairly", "quite", "really",
        "rather", "mainly", "generally", "usually", "often", "sometimes", "rarely",
        "more", "less", "most", "least", "some", "many", "few", "several",
        "almost", "nearly", "barely", "hardly", "significantly", "minor", "major",
    }
)  # fmt: skip

# Common words that carry no meaning for comparison (kept small and English-only for now).
STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with", "by",
        "is", "are", "be", "it", "its", "this", "that", "as", "at", "from", "has", "have",
        "does", "do", "not", "no", "all", "any", "each", "every", "reply", "response",
        "answer", "output",
    }
)  # fmt: skip

OVERLAP_THRESHOLD = 0.75  # share of wording above which two anchors are hard to tell apart

_WORD_RE = re.compile(r"[a-z0-9']+")  # a "word": letters, digits, apostrophes


def _content_words(text: str) -> set[str]:  # the meaningful words in an anchor
    return {w for w in _WORD_RE.findall(text.lower()) if w not in STOPWORDS}  # minus filler


def overlapping_anchors(rubric: dict[str, Any]) -> Iterator[Finding]:  # R005
    for i, crit in _scored(rubric):  # every scored criterion
        scale = crit.get("scale", {})  # level -> anchor text
        levels = sorted(scale, key=int)  # levels in numeric order
        for low, high in pairwise(levels):  # each pair of neighboring levels
            a, b = scale[low], scale[high]  # their anchor texts
            where = ("criteria", i, "scale", high)  # report on the higher level
            if a.strip().lower() == b.strip().lower():  # word-for-word the same
                yield _finding(
                    "R005", WARNING, where, f"anchors for scores {low} and {high} are identical"
                )
                continue  # nothing more to say about this pair
            wa, wb = _content_words(a), _content_words(b)  # meaningful words on each side
            diff = wa ^ wb  # words that appear on only one side
            if diff and diff <= DEGREE_WORDS:  # they differ only in degree words
                quoted = ", ".join(f"'{w}'" for w in sorted(diff))  # e.g. 'mostly'
                yield _finding(
                    "R005",
                    WARNING,
                    where,
                    f"anchors for scores {low} and {high} differ only by degree words ({quoted}); "
                    "say what is present or missing at each level instead",
                )
                continue
            union = wa | wb  # every meaningful word across both anchors
            share = len(wa & wb) / len(union) if union else 0.0  # Jaccard similarity, 0..1
            if share >= OVERLAP_THRESHOLD:  # mostly the same wording
                yield _finding(
                    "R005",
                    WARNING,
                    where,
                    f"anchors for scores {low} and {high} share {share:.0%} of their wording; "
                    "make the difference between the levels explicit",
                )


RULES: tuple[Rule, ...] = (  # every rule, in the order they run and are documented
    Rule("R001", "duplicate-id", ERROR, "criterion ids must be unique", duplicate_ids),
    Rule(
        "R002",
        "example-off-scale",
        ERROR,
        "example scores must be levels on the scale",
        example_off_scale,
    ),
    Rule(
        "R003",
        "level-without-example",
        WARNING,
        "every score level should have an example",
        level_without_example,
    ),
    Rule(
        "R004", "vague-anchor", WARNING, "anchors should describe observable evidence", vague_anchor
    ),
    Rule(
        "R005",
        "overlapping-anchors",
        WARNING,
        "neighboring score levels should be clearly distinguishable",
        overlapping_anchors,
    ),
)


def lint_data(rubric: dict[str, Any], ignore: frozenset[str] = frozenset()) -> list[Finding]:
    findings: list[Finding] = []  # collected across all rules
    for rule in RULES:  # run each rule...
        if rule.code in ignore or rule.name in ignore:  # ...unless the user turned it off
            continue
        findings.extend(rule.check(rubric))  # add everything this rule found
    return findings  # no line numbers yet; lint_file adds them


def lint_file(path: str | Path, ignore: frozenset[str] = frozenset()) -> LintReport:
    report: FileReport = check_file(path)  # structure first: rules assume a valid rubric
    if not report.ok:  # broken structure: rules would give misleading results
        return LintReport(report.path, report.errors, [])  # report schema problems only
    findings = [  # run the rules and attach line numbers
        Finding(f.code, f.severity, f.path, f.message, f.parts, line_for(report.root, f.parts))
        for f in lint_data(report.data, ignore)
    ]
    findings.sort(key=lambda f: (f.line or 0, f.code))  # file order, top to bottom
    return LintReport(report.path, [], findings)  # done
