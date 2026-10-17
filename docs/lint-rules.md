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

## R001 `duplicate-id`

Two criteria with the same id make results ambiguous: scores, reports, and exports key on the id.

## R002 `example-off-scale`

An example scored `4` on a `1 / 3 / 5` scale teaches raters a level that doesn't exist. Either add the level to the scale or re-score the example.

## R003 `level-without-example`

Anchors alone are interpreted differently by different raters and judge models. A worked example per level is the cheapest way to raise agreement.

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
