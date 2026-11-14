"""Starter rubric written by `rubricate init`."""  # docstring describing this module

from __future__ import annotations  # lets type hints like `str | None` work on Python 3.10

import re  # turning a file name into a valid rubric id
from pathlib import Path  # filesystem paths that work on every OS

DEFAULT_PATH = Path("starter.rubric.yaml")  # where `rubricate init` writes when given no path
DEFAULT_ID = "starter"  # fallback id when the file name can't be turned into one

# The template passes `rubricate lint --strict`; tests keep it that way.
STARTER_RUBRIC = """\
# Starter rubric from `rubricate init`. Replace the text with your own task.
# Spec: https://github.com/dys2806/rubricate/blob/main/docs/spec.md
spec: "0.1"
id: {rubric_id}
title: Docs question agent
description: >
  Grades a run of an agent that answers product questions using a
  search_docs tool. Rename the criteria and rewrite the anchors for your task.
subject: trajectory

criteria:
  # A scored criterion: each level says what a reply at that score contains,
  # and each level has a worked example so raters and judges read it the same way.
  - id: answer_grounding
    question: Is every claim in the final reply supported by the documentation the agent found?
    scale:
      1: Makes a claim that contradicts the documentation, or answers without citing any page.
      3: Every claim matches the documentation, but at least one claim has no cited page.
      5: Every claim matches the documentation and each one cites the page it came from.
    examples:
      - score: 1
        output: Yes, the free plan includes unlimited projects.
        rationale: The pricing page says the free plan allows 3 projects, and nothing is cited.
      - score: 3
        output: The free plan allows 3 projects, and exports are available on every plan.
        rationale: Both claims are right, but neither names the page it came from.
      - score: 5
        output: >
          The free plan allows 3 projects (Pricing, "Plan limits"), and exports
          are available on every plan (Exports, "Overview").
        rationale: Both claims are right and each cites its page.

  # An assertion: a pass/fail rule that `rubricate check` verifies on agent traces.
  - id: searches_first
    type: assertion
    rule: The agent calls search_docs before it sends its final reply.
    severity: blocker
    check:
      kind: required
      tool: search_docs
"""

_ID_CHARS = re.compile(r"[^a-z0-9_-]+")  # anything not allowed in a rubric id


def rubric_id_for(path: Path) -> str:  # "Support Bot.rubric.yaml" -> "support-bot"
    name = path.name.lower()  # ids are lowercase
    for suffix in (".rubric.yaml", ".rubric.yml", ".yaml", ".yml"):  # drop the extension
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = _ID_CHARS.sub("-", name).strip("-_")  # replace spaces and punctuation with dashes
    if not name or not name[0].isalpha():  # ids must start with a letter
        return DEFAULT_ID
    return name


def starter_rubric(rubric_id: str = DEFAULT_ID) -> str:  # the template text, with its id filled
    return STARTER_RUBRIC.format(rubric_id=rubric_id)
