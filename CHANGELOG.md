# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Rubric spec v0.1 ([docs/spec.md](docs/spec.md)) with a bundled JSON Schema: scored criteria with anchored scales and worked examples, and pass/fail assertions with `blocker`/`warning` severity.
- `rubricate.spec` module: `load_rubric()` reads `.rubric.yaml` files and `validate()` reports schema errors with readable paths such as `criteria[0].scale`.
- Example rubric: `examples/refund-agent.rubric.yaml`.
- Project scaffold: Python package (`src/rubricate`), `rubricate` CLI with `--version`, test suite, and CI across Python 3.10–3.13.
- README with the project pitch, positioning, and roadmap.
