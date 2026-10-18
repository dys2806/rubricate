# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `rubricate score --resume` continues a batch where it stopped, keeping finished items and retrying failures; batches stop after 10 failures in a row with the reason.
- `rubricate score --rpm N` throttles batch requests to stay under provider rate limits.
- Pre-registered proof of concept in `poc/`: baseline vs. lint-revised coherence rubric on a SummEval sample, with a deterministic data builder, a paired bootstrap comparison, and a one-command runner. Results to follow.
- `rubricate calibrate` command: per-criterion Krippendorff's alpha among human raters, plus quadratic weighted kappa, exact and within-one agreement, and bias for the judge against the human median. Verdicts say whether to fix the anchors or the judge. Reads human ratings as CSV and judge scores from `score --batch` output. Guide in [docs/calibration.md](docs/calibration.md).
- Agreement statistics in plain Python (`rubricate.agreement`), tested against published reference values.
- Hand-made sample ratings in `examples/ratings/`.
- `rubricate score` command: grades a single response or a JSONL batch against a rubric with a Gemini judge. Structured JSON replies are validated (every criterion scored once, scores within the scale), with retries and backoff for rate limits. Optional extra: `pip install rubricate[gemini]`. Guide in [docs/scoring.md](docs/scoring.md).
- Live judge test (`pytest -m live`), run only when `GEMINI_API_KEY` is set; CI uses the `GEMINI_API_KEY` repository secret if present, on one Python version.
- `rubricate check` command: verifies agent traces against a rubric's assertions, deterministically and offline. Check kinds `requires_before`, `forbidden`, `required`, and `max_calls`, with `where` conditions on tool arguments. Failed blockers exit `1`; warnings fail only with `--strict`. Guide in [docs/assertions.md](docs/assertions.md).
- Trace format (`.jsonl` or `.json`) for agent runs: messages, tool calls, and tool results.
- Example traces in `examples/traces/refund-runs.jsonl`; the refund-agent rubric gains machine-checkable `approval_gate` and `lookup_budget` assertions.
- Lint rule R005 `overlapping-anchors`: flags neighboring score levels whose anchors are identical, differ only by degree words ("mostly" vs. "fully"), or share most of their wording.
- `rubricate lint` text output ends with a per-rule breakdown (`by rule: R003 x4, R005 x2`).
- `rubricate lint` command with four rules: R001 duplicate ids, R002 examples scored off the scale (errors), R003 levels without examples, R004 vague anchor wording (warnings). Supports `--strict`, `--ignore`, `--list-rules`, and `--format json`. Rule reference in [docs/lint-rules.md](docs/lint-rules.md).
- `examples/lint-demo/weak-support.rubric.yaml`, a deliberately weak rubric for trying the linter.
- `rubricate validate` command: checks files or folders, reports each problem as `file:line: location: message` in plain language, supports `--format json`, and exits `0`/`1`/`2` for valid/invalid/usage errors.
- Rubric spec v0.1 ([docs/spec.md](docs/spec.md)) with a bundled JSON Schema: scored criteria with anchored scales and worked examples, and pass/fail assertions with `blocker`/`warning` severity.
- `rubricate.spec` module: `load_rubric()` reads `.rubric.yaml` files and `validate()` reports schema errors with readable paths such as `criteria[0].scale`.
- Example rubric: `examples/refund-agent.rubric.yaml`.
- Project scaffold: Python package (`src/rubricate`), `rubricate` CLI with `--version`, test suite, and CI across Python 3.10–3.13.
- README with the project pitch, positioning, and roadmap.
