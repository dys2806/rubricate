# Lint rules

`rubricate lint` runs `validate` first, then the rules below. A rubric that fails `validate` is not linted, because the rules assume a structurally valid file.

- **Errors** mean the rubric contradicts itself. They always fail the run (exit `1`).
- **Warnings** mean the rubric works but will likely produce noisy, inconsistent scores. They fail the run only with `--strict`.

Turn a rule off with `--ignore`, by code or name: `rubricate lint --ignore R003,vague-anchor rubrics/`.

| Code | Name | Severity | Checks |
|---|---|---|---|
| R001 | `duplicate-id` | error | Criterion ids are unique |
| R002 | `example-off-scale` | error | Every example's `score` is a level defined on the scale |
| R003 | `level-without-example` | warning | Every score level has at least one example |
| R004 | `vague-anchor` | warning | Anchors avoid words that leave raters guessing |
| R005 | `overlapping-anchors` | warning | Neighboring score levels are clearly distinguishable |

## R001 `duplicate-id`

Two criteria with the same id make results ambiguous: scores, reports, and exports key on the id.

## R002 `example-off-scale`

An example scored `4` on a `1 / 3 / 5` scale teaches raters a level that doesn't exist. Either add the level to the scale or re-score the example.

## R003 `level-without-example`

A worked example shows what a level looks like in practice. Whether examples raise agreement depends on the rubric and the judge, so check a revision with `rubricate calibrate`; in [our SummEval experiment](../poc/README.md#results), a revision that added examples and rewrote anchors lowered judge–expert agreement.

```yaml
scale:
  1: States a wrong eligibility window or refund amount.
  3: States the window and amount correctly but omits a condition.   # R003 if no example scores 3
  5: States everything correctly and names the policy section.
```

## R004 `vague-anchor`

Words like *good*, *appropriate*, *reasonable*, or *somewhat* describe a judgment, not evidence. Two raters reading "the reply is good" will disagree about what qualifies. Describe what a rater can observe instead.

| Instead of | Write |
|---|---|
| The reply is good and appropriate. | Names the customer's specific issue and gives the next step. |
| Somewhat helpful. | Answers the question but omits one required condition. |

Matched words: good, bad, great, poor, nice, fine, okay, ok, decent, appropriate, inappropriate, adequate, inadequate, reasonable, sufficient, insufficient, satisfactory, acceptable, proper, suitable, high quality, low quality, somewhat, fairly. Matching is whole-word and case-insensitive, so "goodwill" is not flagged.

## R005 `overlapping-anchors`

If a rater can't tell two neighboring levels apart, scores between them become a coin flip. R005 compares each pair of adjacent levels (1 and 3, then 3 and 5) and flags three patterns:

| Pattern | Example |
|---|---|
| Identical anchors | `3: Cites the policy.` / `5: Cites the policy.` |
| Differ only by degree words | `3: Mostly correct facts.` / `5: Fully correct facts.` |
| Mostly the same wording (75%+ of meaningful words shared) | `1: States the window and amount with errors.` / `3: States the window and amount without errors.` |

Degree words are words that change *how much* rather than *what*: mostly, partially, fully, completely, largely, very, slightly, somewhat, more, less, many, few, and similar. "Mostly correct" vs. "fully correct" is the most common rubric smell in practice: every rater draws the line in a different place.

**Fix:** name the evidence that separates the levels.

| Instead of | Write |
|---|---|
| 3: Mostly correct facts. | 3: One fact is wrong, but it doesn't change what the user should do. |
| 5: Fully correct facts. | 5: Every fact matches the source documentation. |

Only neighboring levels are compared, and matching ignores case, punctuation, and filler words.
