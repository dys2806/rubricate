#!/usr/bin/env bash
# Runs the POC end to end. Needs GEMINI_API_KEY set in your shell (never commit it).
# 400 judge calls at 8 per minute: about 50 minutes, within Gemini's free tier.
set -euo pipefail                       # stop on the first error
cd "$(dirname "$0")/.."                 # run from the repo root

JUDGE="${JUDGE:-gemini:gemini-3.8-flash}"   # override with JUDGE=gemini:<model> ./poc/run.sh
RPM="${RPM:-8}"                             # requests per minute, under the free-tier limit
mkdir -p poc/results

python poc/prepare.py                   # rebuild the sample (deterministic)
rubricate lint poc/rubrics/coherence-baseline.rubric.yaml | tee poc/results/lint-baseline.txt || true
rubricate lint --strict poc/rubrics/coherence-revised.rubric.yaml | tee poc/results/lint-revised.txt

for v in baseline revised; do           # score the same 200 summaries under each rubric
  rubricate score "poc/rubrics/coherence-$v.rubric.yaml" \
    --batch poc/data/sample.jsonl --judge "$JUDGE" --rpm "$RPM" \
    --out "poc/results/scores-$v.jsonl" || true   # keep going if a few items fail; compare.py reports them
  rubricate calibrate "poc/rubrics/coherence-$v.rubric.yaml" \
    --human poc/data/expert-ratings.csv --judge-scores "poc/results/scores-$v.jsonl" \
    | tee "poc/results/calibrate-$v.txt"
done

python poc/compare.py                   # paired comparison with a bootstrap interval
