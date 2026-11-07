# Contributing to rubricate

Thanks for helping. Bug reports, rubric examples, docs fixes, and new lint rules are all welcome.

## Set up

```bash
git clone https://github.com/dys2806/rubricate.git
cd rubricate
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,gemini]"
pytest -q                 # everything except the live judge test
ruff check . && ruff format --check .
```

The live judge test calls Gemini for real and only runs when `GEMINI_API_KEY` is set: `pytest -m live`. Never commit an API key; `.gemini-key`, `*.key`, and `.env` files are ignored.

## Making a change

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Keep each pull request to one change, with tests. CI runs lint, formatting, and tests on Python 3.10–3.13.
3. Write the commit message as a plain sentence describing the change ("Add a rule for empty anchors"), with a short body saying why.
4. Update `CHANGELOG.md` under **Unreleased**, and the docs if behavior changes.

## Good places to start

- **Rubric examples.** A well-built `.rubric.yaml` for a real task (RAG faithfulness, code review, support tone), with worked examples, in `examples/`.
- **Lint rules.** Each rule lives in `src/rubricate/lint.py` with a stable code (`R00N`), a test in `tests/test_lint.py`, and a section in `docs/lint-rules.md`. Explain the failure mode it catches and show a before/after fix. Rules should avoid claiming effects on agreement that haven't been measured; [the POC](poc/README.md#results) is a reminder why.
- **Judge providers.** `src/rubricate/judge.py` defines the `Judge` interface. A new provider is a class with `name` and `complete_json`, plus an optional install extra.
- **Exporters.** `src/rubricate/export.py` maps a rubric to another tool's format. Say plainly in the output what doesn't carry over.

## Claims and evidence

rubricate is a measurement tool, so its docs should be careful about what's been shown. Mark results as pre-registered or exploratory, report outcomes that go the wrong way, and don't state that a practice improves agreement unless there's a measurement behind it.

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
