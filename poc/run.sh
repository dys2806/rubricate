#!/usr/bin/env bash
# Runs the POC end to end. Needs GEMINI_API_KEY set in your shell (never commit it).
# 400 judge calls at 8 per minute: about 50 minutes, within Gemini's free tier.
set -euo pipefail                       # stop on the first error
cd "$(dirname "$0")/.."                 # run from the repo root

PY="$(command -v python || command -v python3)"   # macOS ships python3 only
if ! command -v rubricate >/dev/null; then        # usually means the venv isn't active
  echo "rubricate not found. Activate the project's venv first: source .venv/bin/activate" >&2
  exit 1
fi
if [ -z "${GEMINI_API_KEY:-}" ]; then              # fail fast instead of 400 failed calls
  echo "GEMINI_API_KEY is not set. Run: export GEMINI_API_KEY='your-key'" >&2
  exit 1
fi

JUDGE="${JUDGE:-gemini:gemini-3.8-flash}"   # override with JUDGE=gemini:<model> ./poc/run.sh
RPM="${RPM:-8}"                             # requests per minute, under the free-tier limit
mkdir -p poc/results

"$PY" poc/prepare.py                   # rebuild the sample (deterministic)
rubricate lint poc/rubrics/coherence-baseline.rubric.yaml | tee poc/results/lint-baseline.txt || true
rubricate lint --strict poc/rubrics/coherence-revised.rubric.yaml | tee poc/results/lint-revised.txt

for v in baseline revised; do           # score the same 200 summaries under each rubric
  rubricate score "poc/rubrics/coherence-$v.rubric.yaml" \
    --batch poc/data/sample.jsonl --judge "$JUDGE" --rpm "$RPM" \
    --out "poc/results/scores-$v.jsonl" || true   # keep going if a few items fail; compare.py reports them
  if ! grep -q '"criteria"' "poc/results/scores-$v.jsonl"; then   # nothing scored at all: stop
    echo "Every judge call failed for the $v rubric. First error:" >&2
    head -1 "poc/results/scores-$v.jsonl" | cut -c1-400 >&2
    exit 1
  fi
  rubricate calibrate "poc/rubrics/coherence-$v.rubric.yaml" \
    --human poc/data/expert-ratings.csv --judge-scores "poc/results/scores-$v.jsonl" \
    | tee "poc/results/calibrate-$v.txt"
done

"$PY" poc/compare.py                   # paired comparison with a bootstrap interval
