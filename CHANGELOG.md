# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
