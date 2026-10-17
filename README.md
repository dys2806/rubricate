# rubricate

**Rubrics as code for AI evaluation.** Write one portable YAML rubric, lint it before you spend a single token, measure whether humans and LLM judges actually agree on it, assert hard rules over agent trajectories, and gate regressions in CI.

> **Status: pre-alpha.** The spec and CLI are being built in public. See the [roadmap](#roadmap).

---

## The problem

Every team evaluating LLMs and agents writes rubrics. Almost nobody tests them.

- **Rubrics live inside prompts.** Each eval framework stores them differently, so a rubric can't be reviewed, versioned, or reused on its own.
- **Bad rubrics fail silently.** An anchor like "response is appropriate" or two score levels that overlap produce noisy scores, and you only find out after paying for thousands of judge calls.
- **Judge agreement goes unmeasured.** Teams swap judge models and rewrite anchors without checking whether the new scores still match human raters.
- **Agents need rules, not just scores.** "Never issue a refund over $100 without approval" is a pass/fail rule about the *sequence of tool calls*, and it doesn't fit a 1–5 scale.

## What rubricate does

| Capability | What it gives you |
|---|---|
| **Spec** | One versionable `.rubric.yaml` format: criteria, weights, score anchors, worked examples, and pass/fail assertions |
| **Lint** | Static checks that catch weak rubrics *before* evaluation: vague wording, score levels with no example, overlapping anchors |
| **Calibrate** | Agreement reports between human raters and LLM judges, per criterion, so you know which anchors to tighten |
| **Assert** | Rules over agent trajectories (tool-call order, approvals, retry budgets) with `blocker` severity that fails the run |
| **Gate** | A CLI and GitHub Action that fail the build when a prompt or model change regresses |
| **Export** | Compile one rubric into configs for existing eval frameworks, so you don't switch stacks |

## How it fits with existing tools

rubricate is a **layer underneath** your eval stack, not a replacement for it.

- **Eval runners** (promptfoo, Inspect, DeepEval) run evaluations and accept rubrics as prompt strings. rubricate gives those rubrics a typed, lintable source of truth and exports to them.
- **Rubric-scoring libraries and research** (for example Autorubric and Rulers) focus on *how a judge scores* against a rubric. rubricate focuses on *whether the rubric itself is any good*, and on one spec that covers both single responses and agent runs.

What's new here: **static analysis for rubrics**, and **one spec for grading answers and agent trajectories**.

## A taste of the spec

Full reference: [docs/spec.md](docs/spec.md). Complete example: [examples/refund-agent.rubric.yaml](examples/refund-agent.rubric.yaml).

```yaml
# refund-agent.rubric.yaml
spec: "0.1"
id: refund-agent
subject: trajectory              # grade the whole agent run, not just the final reply
criteria:
  - id: policy_accuracy
    weight: 0.4
    question: "Does the final reply state the refund policy correctly?"
    scale:
      1: "States a wrong eligibility window or amount"
      3: "Correct but omits a condition (e.g., receipt required)"
      5: "Correct, complete, and cites the policy section"
    examples:
      - score: 1
        output: "You can return it anytime for a full refund!"
  - id: approval_gate
    type: assertion              # binary pass/fail rule over tool calls
    rule: "issue_refund is never called before human_approval when amount > 100"
    severity: blocker            # one failure fails the whole run
```

```console
$ rubricate lint examples/lint-demo/
weak-support.rubric.yaml:17: R004 warning: criteria[0].scale.5: anchor uses vague wording ('appropriate', 'good'); describe what a rater can observe instead, such as what is present, missing, or wrong
weak-support.rubric.yaml:21: R002 error: criteria[0].examples[1].score: example score 4 is not a level on this scale (levels: 1, 3, 5)
weak-support.rubric.yaml:24: R001 error: criteria[1].id: criterion id 'helpfulness' is already used by criteria[0]; ids must be unique
```

## Install

```bash
pip install -e ".[dev]"     # from a clone, until the first PyPI release
rubricate --version
```

## Usage

### Validate rubrics

Check files or whole folders (folders are searched for `*.rubric.yaml`):

```console
$ rubricate validate rubrics/
rubrics/refund-agent.rubric.yaml: valid
rubrics/support.rubric.yaml:8: criteria[0].scale: needs at least 2 score levels, found 1
rubrics/support.rubric.yaml:11: criteria[1].severity: 'critical' is not one of ['blocker', 'warning']
2 file(s) checked, 1 invalid (2 error(s))
```

Every problem is reported as `file:line: location: message`, so editors and CI logs can jump straight to it.

| Exit code | Meaning |
|---|---|
| `0` | All files are valid |
| `1` | At least one file is invalid (fail the build) |
| `2` | Bad arguments: a path doesn't exist, or no rubric files were found |

Use `--format json` for machine-readable output.

### Lint rubrics

`lint` catches the problems that make raters and judges disagree, before you spend anything on evaluation:

```console
$ rubricate lint rubrics/
rubrics/support.rubric.yaml:15: R003 warning: criteria[0].scale.1: score 1 has no example; raters and judges agree far more often when every level is illustrated
rubrics/support.rubric.yaml:17: R004 warning: criteria[0].scale.5: anchor uses vague wording ('appropriate', 'good'); describe what a rater can observe instead, such as what is present, missing, or wrong
rubrics/support.rubric.yaml:21: R002 error: criteria[0].examples[1].score: example score 4 is not a level on this scale (levels: 1, 3, 5)
1 file(s) linted: 1 error(s), 2 warning(s)
```

Errors fail the run; warnings fail it only with `--strict`. Skip rules with `--ignore R003,vague-anchor`, and see them all with `--list-rules`. Full reference: [docs/lint-rules.md](docs/lint-rules.md).

## Roadmap

- [x] Project scaffold, CLI, CI
- [x] Rubric spec v0.1 + JSON Schema ([docs/spec.md](docs/spec.md))
- [x] `rubricate validate`
- [x] `rubricate lint`: duplicate ids, off-scale examples, missing examples, vague wording
- [ ] `rubricate lint`: overlapping anchors
- [ ] Judge scoring for single responses (model-agnostic)
- [ ] Trace format + trajectory assertions with `blocker` severity
- [ ] `rubricate calibrate` (human vs. judge agreement per criterion)
- [ ] promptfoo exporter + GitHub Action
- [ ] v0.1.0 release

## Contributing

Issues and ideas are welcome. A `CONTRIBUTING.md` and starter issues are coming with v0.1.

## License

[Apache-2.0](LICENSE)
