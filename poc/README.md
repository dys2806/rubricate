# POC: does fixing lint findings make an LLM judge agree more with experts?

**Status: complete.** The design below was committed before any judge scores were collected; the results were added afterwards in a separate commit. **Outcome: the lint-guided revision made judge–expert agreement worse.**

## Question

`rubricate lint` flags rubric problems that are expected to make scores noisy: missing worked examples, vague anchor wording, and neighboring levels that are hard to tell apart. If those findings matter, fixing them should make an LLM judge agree more closely with expert human raters.

**Hypothesis (H1).** A judge using the lint-revised rubric agrees more with the expert median than the same judge using the baseline rubric, measured by quadratic weighted kappa.

## Design

| | |
|---|---|
| Data | [SummEval](https://github.com/Yale-LILY/SummEval) expert annotations (Fabbri et al., TACL 2021; MIT license). News summaries from 16 systems, each scored 1–5 by three expert annotators |
| Dimension | Coherence. It can be judged from the summary alone; SummEval does not distribute the source articles. It also uses the whole 1–5 range, unlike fluency (83% of expert scores are 5) |
| Sample | 200 summaries drawn at random (seed 2026) from the 1,600 annotated |
| Held-out pool | 10 summaries all three experts scored identically, two per level, excluded from the sample. The revised rubric's examples come only from here |
| Judge | `gemini:gemini-3.5-flash-lite`, temperature 0, one call per summary per rubric (see Amendment 1) |
| Conditions | [Baseline](rubrics/coherence-baseline.rubric.yaml): generic labels, no examples (9 lint warnings). [Revised](rubrics/coherence-revised.rubric.yaml): same question, description and scale, with observable anchors and one example per level (lints clean under `--strict`) |
| Primary metric | Quadratic weighted kappa between the judge and the rounded median of the three experts |
| Secondary | Exact agreement with the expert median; per-rubric `rubricate calibrate` reports |
| Ceiling | Expert agreement on the full dataset: Krippendorff's alpha (ordinal) = 0.55 for coherence. A judge isn't expected to agree with experts much more than they agree with each other |

## Decision rule

Kappa difference = revised − baseline, with a 95% paired bootstrap interval over the 200 items (10,000 resamples, seed 2026).

| Interval | Conclusion |
|---|---|
| Entirely above 0 | H1 supported |
| Contains 0 | No detectable difference at this sample size |
| Entirely below 0 | Revision made agreement worse |

All three outcomes will be reported. Items the judge fails on under either rubric are excluded from the paired comparison and counted.

## Known limitations

- **One dimension, one judge model, one run.** Results may not transfer to other criteria or models. Temperature 0 reduces but doesn't remove run-to-run variation.
- **The revision bundles every fix.** This tests "lint-guided revision" as a whole, not each rule separately. In particular, adding examples also adds context, which may help on its own.
- **Lint coverage gap found during setup.** "Fair" and "Excellent" in the baseline are not on R004's vague-word list, so they weren't flagged. The revision rewrote all anchors anyway. The rule list is left unchanged for this experiment.
- **Text format.** Summaries are lowercased and tokenized as distributed (`-lrb- cnn -rrb-`). Both rubrics see identical text.
- **Modest expert agreement.** With an expert alpha of 0.55, the room for any judge to agree with the experts is limited, and small differences may not be detectable with 200 items.

## Amendments

**Amendment 1 (2026-10-18): judge model.** The original judge, `gemini-3.8-flash`, has a free-tier quota of 20 requests per day, far short of the 400 calls the design needs. The first run stopped after 18 baseline items, and those 18 were discarded without being analyzed. The judge is now `gemini-3.5-flash-lite` (500 requests per day on the free tier). Nothing else changes: data, sample, rubrics, metric, and decision rule are as pre-registered. This amendment was committed before any scores from the new judge existed.

## Reproduce

```bash
pip install -e ".[gemini]"
export GEMINI_API_KEY=your-key       # Gemini free tier is enough
./poc/run.sh                         # about 35 minutes at 12 requests per minute
```

`run.sh` rebuilds the sample (`prepare.py` is deterministic; the source file's SHA-256 is in [data/SOURCE.md](data/SOURCE.md)), lints both rubrics, scores both, runs `calibrate` on each, and writes `results/summary.json` with `compare.py`.

## Results

Run on 2026-10-18 with `gemini-3.5-flash-lite`. All 400 judge calls succeeded; no items were dropped. Raw scores, rationales, and reports are in [results/](results/).

### Pre-registered result

| | Baseline rubric | Revised rubric |
|---|---|---|
| **Weighted kappa vs. expert median (primary)** | **0.625** | **0.534** |
| Exact agreement with expert median | 41.5% | 42.0% |
| Within one point of expert median | 84% | 77% |
| Bias (judge mean − expert mean) | +0.28 | +0.56 |

Kappa difference (revised − baseline): **−0.091**, 95% paired bootstrap interval **[−0.154, −0.031]**.

The interval lies entirely below 0. Under the decision rule, **the revision made agreement worse**. H1 is not supported in this setting.

### Exploratory analysis

*Not pre-registered. These describe what happened, not why, and should be read as hypotheses.*

**The revised rubric shifted the judge upward.** The two rubrics agreed on 113 of 200 items. Where they differed, the revised rubric scored higher 67 times and lower 20 times.

| Score | 1 | 2 | 3 | 4 | 5 | Mean |
|---|---|---|---|---|---|---|
| Experts (rounded median) | 5 | 36 | 64 | 46 | 49 | 3.49 |
| Judge, baseline rubric | 9 | 32 | 31 | 51 | 77 | 3.77 |
| Judge, revised rubric | 5 | 27 | 26 | 36 | 106 | 4.05 |

The shift appears at every expert level, so it isn't confined to a few items:

| Expert level (n) | 1 (5) | 2 (36) | 3 (64) | 4 (46) | 5 (49) |
|---|---|---|---|---|---|
| Mean baseline score | 1.60 | 2.58 | 3.55 | 4.26 | 4.71 |
| Mean revised score | 2.00 | 3.03 | 3.86 | 4.43 | 4.92 |

**A plausible mechanism.** The revised anchors define each level by the *absence* of specific defects ("no repetition or dangling references"). The judge's rationales for the revised rubric mostly restate the level-5 anchor and conclude that no defect is present. For example, summaries the experts rated 2 were given 5 because "every sentence flows logically from the preceding one… with no repetition or dangling references." The experts' notion of coherence also includes whether the summary *builds into a body of information*, which a defect checklist doesn't capture. If this is right, observable anchors written as defect checklists can make a judge more lenient, not more accurate.

**Ruled out: summary length.** The upward shift was the same for short summaries (≤2 sentences, +0.26) and longer ones (≥3 sentences, +0.28).

### What this means for rubricate

- The tool did its job as an instrument: it produced a clean, reproducible measurement, including an unwelcome one. That is the point of `calibrate`.
- It does **not** support claiming that fixing lint findings improves judge agreement. That claim is not made anywhere in the project.
- Lint findings are best read as prompts to revise, not as a recipe. A revision should be checked with `calibrate` against human ratings, which is exactly the workflow this experiment exercised.

### Follow-ups (each would be a new pre-registered experiment)

1. **Ablation.** Revised anchors without examples, and examples without revised anchors, to see which change caused the shift.
2. **Anchor style.** Anchors that describe what a level *contains*, not only which defects are absent.
3. **Other judges and dimensions.** Repeat with a second judge model and a second SummEval dimension (relevance, with source articles).
