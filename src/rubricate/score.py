"""Score a model response against a rubric with an LLM judge."""

from __future__ import annotations  # modern type hints on Python 3.10

from dataclasses import asdict, dataclass, field  # result records
from typing import Any  # parsed rubric data

from rubricate.judge import Judge, JudgeError  # the model doing the grading

SYSTEM_PROMPT = """\
You are a strict, consistent evaluator. You grade a model response against a rubric.

Rules:
- Grade each criterion independently, using only its question and score anchors.
- Pick the anchor that best matches the evidence in the response. If the response falls
  between two anchors, you may give an integer score between them.
- Use the worked examples to calibrate what each level looks like.
- Base every score on what the response actually says, not on what it might have meant.
- Keep each rationale to one or two sentences that cite the specific evidence.
"""


@dataclass(frozen=True)
class CriterionScore:  # the judge's verdict on one criterion
    id: str  # criterion id from the rubric
    score: int  # the score the judge gave
    rationale: str  # the judge's one-line justification
    min: int  # lowest level on this criterion's scale
    max: int  # highest level on this criterion's scale
    weight: float  # the criterion's weight from the rubric


@dataclass(frozen=True)
class ScoreResult:  # everything about one scored response
    rubric_id: str  # which rubric was used
    judge: str  # which model graded it, e.g. "gemini:gemini-3.8-flash"
    criteria: list[CriterionScore] = field(default_factory=list)  # per-criterion verdicts
    skipped: list[str] = field(default_factory=list)  # assertions: checked in a later release

    @property
    def weighted(self) -> float:  # overall score on a 0..1 scale, weighted by criterion
        total = sum(c.weight for c in self.criteria)  # sum of weights
        if not total:  # no scored criteria
            return 0.0
        return (
            sum(  # each criterion normalized to 0..1, then weighted
                c.weight * (c.score - c.min) / (c.max - c.min) for c in self.criteria
            )
            / total
        )

    def to_dict(self) -> dict[str, Any]:  # JSON-friendly form for output files
        out = asdict(self)  # dataclass fields
        out["weighted"] = round(self.weighted, 4)  # add the overall score
        return out


def _scored_criteria(rubric: dict[str, Any]) -> list[dict[str, Any]]:  # criteria with a scale
    return [c for c in rubric["criteria"] if c.get("type", "scored") == "scored"]


def build_prompt(rubric: dict[str, Any], output: str, input_text: str | None = None) -> str:
    lines: list[str] = []  # the prompt, assembled line by line
    lines.append(f"# Rubric: {rubric.get('title', rubric['id'])}")  # heading
    if rubric.get("description"):  # optional context about the task
        lines.append(rubric["description"].strip())
    for crit in _scored_criteria(rubric):  # one section per criterion
        lines.append("")
        lines.append(f"## Criterion `{crit['id']}`")
        lines.append(f"Question: {crit['question']}")
        lines.append("Score anchors:")
        for level in sorted(crit["scale"], key=int):  # levels in numeric order
            lines.append(f"- {level}: {crit['scale'][level]}")
        for ex in crit.get("examples", []):  # worked examples, if any
            lines.append(f"Example scored {ex['score']}:")
            if ex.get("input"):
                lines.append(f"  Input: {ex['input'].strip()}")
            lines.append(f"  Output: {ex['output'].strip()}")
            if ex.get("rationale"):
                lines.append(f"  Why: {ex['rationale'].strip()}")
    lines.append("")
    if input_text:  # the prompt the response was answering, if known
        lines.append("# Input given to the model")
        lines.append(input_text.strip())
        lines.append("")
    lines.append("# Response to grade")
    lines.append(output.strip())
    lines.append("")
    lines.append("Grade the response on every criterion above.")
    return "\n".join(lines)  # one string for the judge


def response_schema(rubric: dict[str, Any]) -> dict[str, Any]:  # the JSON shape the judge returns
    ids = [c["id"] for c in _scored_criteria(rubric)]  # criteria the judge must grade
    return {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ids},  # only real criterion ids
                        "rationale": {"type": "string"},  # reasoning first...
                        "score": {"type": "integer"},  # ...then the score
                    },
                    "required": ["id", "rationale", "score"],
                },
            }
        },
        "required": ["scores"],
    }


def parse_response(rubric: dict[str, Any], reply: dict[str, Any], judge: str) -> ScoreResult:
    by_id = {}  # criterion id -> the judge's entry
    for entry in reply.get("scores", []):  # each verdict the judge returned
        if entry.get("id") in by_id:  # graded the same criterion twice
            raise JudgeError(f"judge scored criterion {entry['id']!r} more than once")
        by_id[entry.get("id")] = entry
    results = []  # validated per-criterion scores
    for crit in _scored_criteria(rubric):  # every criterion must be graded exactly once
        cid = crit["id"]
        if cid not in by_id:  # judge skipped one
            raise JudgeError(f"judge did not score criterion {cid!r}")
        levels = sorted(int(k) for k in crit["scale"])  # the scale's defined levels
        lo, hi = levels[0], levels[-1]  # its range
        score = by_id[cid].get("score")  # the judge's number
        if not isinstance(score, int) or isinstance(score, bool) or not lo <= score <= hi:
            raise JudgeError(f"judge gave {cid!r} score {score!r}, outside the scale {lo}-{hi}")
        results.append(
            CriterionScore(
                cid,
                score,
                str(by_id[cid].get("rationale", "")).strip(),
                lo,
                hi,
                float(crit.get("weight", 1)),
            )
        )
    extra = set(by_id) - {c["id"] for c in _scored_criteria(rubric)}  # ids not in the rubric
    if extra:
        raise JudgeError(f"judge scored unknown criteria: {', '.join(sorted(map(str, extra)))}")
    skipped = [c["id"] for c in rubric["criteria"] if c.get("type") == "assertion"]  # not graded
    return ScoreResult(rubric["id"], judge, results, skipped)


def score_response(
    rubric: dict[str, Any], output: str, judge: Judge, input_text: str | None = None
) -> ScoreResult:  # the full pipeline: prompt -> judge -> validated scores
    if not _scored_criteria(rubric):  # nothing for a judge to grade
        raise JudgeError("rubric has no scored criteria")
    reply = judge.complete_json(
        SYSTEM_PROMPT, build_prompt(rubric, output, input_text), response_schema(rubric)
    )
    return parse_response(rubric, reply, judge.name)  # reject malformed or out-of-range replies
