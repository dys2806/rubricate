# Integrations

## GitHub Action

Run `validate`, `lint`, and `check` on every pull request. A broken rubric, or an agent run that breaks a blocker rule, fails the build.

```yaml
# .github/workflows/rubrics.yml
name: Rubrics
on: [pull_request]

jobs:
  rubricate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dys2806/rubricate@main          # pin to a release tag once one exists
        with:
          rubrics: rubrics/                   # files or folders, space-separated
          traces: traces/latest-runs.jsonl    # optional: agent runs to check
          strict: "false"                     # "true" also fails on warnings
```

| Input | Required | Default | Meaning |
|---|---|---|---|
| `rubrics` | yes | | Rubric files or folders to validate and lint |
| `traces` | no | | Trace files to check. Each is checked against every rubric *file* in `rubrics` that has assertions |
| `strict` | no | `false` | Fail on lint warnings and failed warning-level assertions too |
| `python-version` | no | `3.12` | Python used to run rubricate |

What fails the build:

| Step | Fails when |
|---|---|
| Validate | Any rubric breaks the spec |
| Lint | Any lint error (R001, R002), or any warning with `strict: "true"` |
| Check | Any failed `blocker` assertion, or a failed `warning` with `strict: "true"` |

The action needs no API key: none of these steps call a model. To score with a judge in CI, run `rubricate score` in your own step and pass the key from a repository secret.

This repository runs its own action on every push; see the `action` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## promptfoo

Keep the rubric as the source of truth and export it into [promptfoo](https://www.promptfoo.dev/) instead of rewriting it as prompt strings.

```bash
rubricate export rubrics/support.rubric.yaml --to promptfoo -o support.promptfoo.yaml
```

Each scored criterion becomes one `llm-rubric` assertion:

```yaml
defaultTest:
  assert:
  - type: llm-rubric
    metric: policy_accuracy        # named metric: results roll up per criterion
    weight: 0.5                    # the criterion's rubric weight
    value: |-
      Does the final reply state the refund policy correctly?

      Score anchors (1-5):
      - 1: States a wrong eligibility window or refund amount.
      - 3: States the window and amount correctly but omits a condition, such as the receipt requirement.
      - 5: States the window, amount, and every condition correctly, and names the policy section.

      Example scored 1:
      You can return it anytime for a full refund!
      ...
      Choose the level (1-5) whose anchor best matches the output; ... Report it as score = (level - 1) / 4 ...
```

Merge `defaultTest` into your `promptfooconfig.yaml`. Add `--threshold 0.75` to set a minimum 0–1 score for each assertion to pass; without it, promptfoo's grader decides pass or fail.

**What doesn't export.** Trajectory assertions (`type: assertion`) have no exact promptfoo equivalent, so they're listed in a comment at the top of the file instead. Check them with `rubricate check` or the GitHub Action above.

**Scores are on promptfoo's scale.** promptfoo's `llm-rubric` works in 0–1, so the exported instructions map each level onto that range (on a 1–5 scale, level 3 is 0.5). Scores from promptfoo and from `rubricate score` use different prompts and graders, so don't compare them directly without running `rubricate calibrate` on both.
