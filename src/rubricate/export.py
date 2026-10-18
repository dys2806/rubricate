"""Export a rubric to other eval tools, so it can be used without switching stacks."""

from __future__ import annotations  # modern type hints on Python 3.10

from typing import Any  # parsed rubric data

import yaml  # promptfoo configs are YAML


class _Dumper(yaml.SafeDumper):  # YAML writer that keeps multi-line text readable
    pass


def _str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:  # strings with newlines -> `|`
    style = "|" if "\n" in value else None  # block style keeps line breaks as written
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)  # use it for every string


def _rubric_text(crit: dict[str, Any]) -> str:  # one criterion as grader instructions
    levels = sorted(crit["scale"], key=int)  # "1", "3", "5" in numeric order
    lo, hi = int(levels[0]), int(levels[-1])  # scale range
    lines = [crit["question"], "", f"Score anchors ({lo}-{hi}):"]
    lines += [f"- {k}: {crit['scale'][k]}" for k in levels]  # every anchor, in order
    for ex in crit.get("examples", []):  # worked examples, if the rubric has them
        lines += ["", f"Example scored {ex['score']}:", ex["output"].strip()]
        if ex.get("rationale"):
            lines.append(f"Why: {ex['rationale'].strip()}")
    lines += [
        "",
        f"Choose the level ({lo}-{hi}) whose anchor best matches the output; integers between "
        "anchors are allowed. Report it as score = (level - "
        f"{lo}) / {hi - lo}, so {lo} is 0.0 and {hi} is 1.0. State the level in your reason.",
    ]
    return "\n".join(lines)


def to_promptfoo(rubric: dict[str, Any], threshold: float | None = None) -> str:
    """Build a promptfoo config fragment: one `llm-rubric` assertion per scored criterion."""
    asserts = []  # promptfoo assertions, in rubric order
    skipped = []  # assertions that promptfoo can't express the same way
    for crit in rubric["criteria"]:
        if crit.get("type") == "assertion":
            skipped.append(crit["id"])
            continue
        item: dict[str, Any] = {
            "type": "llm-rubric",  # promptfoo's model-graded rubric assertion
            "metric": crit["id"],  # named metric, so results roll up per criterion
            "weight": float(crit.get("weight", 1)),  # same weighting as the rubric
            "value": _rubric_text(crit),
        }
        if threshold is not None:  # minimum 0-1 score for the assertion to pass
            item["threshold"] = threshold
        asserts.append(item)
    header = [  # comment block at the top of the exported file
        f"# Exported by rubricate from rubric '{rubric['id']}' (spec {rubric['spec']}).",
        "# Edit the .rubric.yaml and re-export; changes made here are lost on the next export.",
        "# Merge `defaultTest` into your promptfooconfig.yaml, or reference it with `file://`.",
    ]
    if skipped:  # tell users plainly what didn't come across
        header += [
            f"# Not exported: {', '.join(skipped)}. Trajectory assertions have no exact promptfoo",
            "# equivalent; check them with `rubricate check RUBRIC TRACES` in CI instead.",
        ]
    body = yaml.dump(  # stable, readable YAML
        {"defaultTest": {"assert": asserts}},
        Dumper=_Dumper,
        sort_keys=False,  # keep type/metric/weight/value order
        allow_unicode=True,
        width=100,
    )
    return "\n".join(header) + "\n" + body


EXPORTERS = {"promptfoo": to_promptfoo}  # target name -> function
