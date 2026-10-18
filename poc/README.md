# POC: does fixing lint findings make an LLM judge agree more with experts?

**Status: pre-registered, not yet run.** This file was committed before any judge scores were collected. The results section will be added in a separate commit, whatever the outcome.

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

*Not yet run.*
