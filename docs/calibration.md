# Calibration

A judge's scores only mean something if they track human judgment, and human judgment only means something if humans agree with each other. `rubricate calibrate` measures both, criterion by criterion, so you know which anchors to fix and whether the judge can be trusted.

```console
$ rubricate calibrate examples/refund-agent.rubric.yaml --human examples/ratings/refund-human-ratings.csv
criterion            items raters   alpha  verdict
policy_accuracy         12      3    0.93  humans agree
tone                    12      3   -0.04  humans disagree: tighten the anchors
alpha = agreement among humans (Krippendorff; >= 0.80 reliable, < 0.67 unreliable).
```

The sample data is hand-made for demonstration; see [examples/ratings](../examples/ratings).

## Inputs

**Human ratings** (`--human`): a CSV with one row per rating.

```csv
item,rater,criterion,score
r01,ana,policy_accuracy,5
r01,ben,policy_accuracy,5
r01,ana,tone,4
```

Every criterion must be a scored criterion in the rubric, and every score must be a whole number within its scale. Raters don't have to score every item.

**Judge scores** (`--judge-scores`, optional): the JSONL file written by `rubricate score --batch`. Its `id`s must match the CSV's `item` column. Items the judge failed on are left out rather than guessed.

```bash
rubricate score my.rubric.yaml --batch replies.jsonl --out scores.jsonl
rubricate calibrate my.rubric.yaml --human ratings.csv --judge-scores scores.jsonl
```

## The numbers

| Column | Meaning |
|---|---|
| `items` | Items with at least two human ratings for this criterion |
| `raters` | Distinct human raters |
| `alpha` | Krippendorff's alpha (ordinal) among humans. 1 is perfect agreement, 0 is chance |
| `kappa` | Quadratic weighted kappa between the judge and the human median (rounded to a level) |
| `exact` | Share of items where the judge matched the rounded human median |
| `+/-1` | Share within one point of the human median |
| `bias` | Judge mean minus human mean. Positive means the judge scores higher |

**Why these statistics.** Krippendorff's alpha handles any number of raters, missing ratings, and ordered scales, which is exactly what rubric ratings look like. Weighted kappa treats a judge that's off by one point as closer than one that's off by four. Both are implemented in plain Python and tested against published reference values.

## Verdicts

| Verdict | Condition | What to do |
|---|---|---|
| `humans disagree: tighten the anchors` | alpha < 0.667 | The rubric is the problem. Run `rubricate lint`, add examples, make anchors observable. Don't trust any judge on this criterion yet |
| `humans agree (tentative)` | 0.667 ≤ alpha < 0.800 | Usable for exploration, not for decisions |
| `humans agree` | alpha ≥ 0.800 | Reliable |
| `judge disagrees with humans` | humans agree, but kappa < 0.60 | The rubric works for people; the judge isn't following it. Try more examples, a stronger model, or per-criterion prompts |
| `ok` | humans agree and kappa ≥ 0.60 | The judge can stand in for humans on this criterion |

The alpha thresholds follow Krippendorff's conventional guidance (0.800 reliable, 0.667 the lowest acceptable for tentative conclusions). The kappa threshold is a practical default, not a standard; tighten it for high-stakes decisions.

**Human agreement is the ceiling.** A judge can't be expected to agree with humans more than humans agree with each other, so fix low-alpha criteria before tuning the judge.

## Output

`--format json` returns one object per criterion with every number above and the verdict.
