# Rubric spec v0.1

A rubricate rubric is a YAML (or JSON) file, by convention named `<name>.rubric.yaml`. It is validated against [`rubric.schema.json`](../src/rubricate/schema/rubric.schema.json).

The spec is pre-1.0. Fields may change between minor versions, and every file declares the version it targets.

## Top level

| Field | Required | Type | Meaning |
|---|---|---|---|
| `spec` | yes | `"0.1"` | Spec version the file targets |
| `id` | yes | slug | Stable identifier: lowercase letters, digits, `-`, `_` |
| `title` | no | string | Human-readable name |
| `description` | no | string | What the rubric evaluates and when to use it |
| `subject` | yes | `response` \| `trajectory` | A single model reply, or a full agent run (messages and tool calls) |
| `criteria` | yes | list | One or more criteria (below) |

## Criteria

Each criterion is one of two kinds, chosen by `type`.

### Scored criterion (`type: scored`, the default)

Graded on a numeric scale. Every level has a written **anchor** that describes what that score looks like.

| Field | Required | Type | Meaning |
|---|---|---|---|
| `id` | yes | slug | Unique within the rubric |
| `question` | yes | string | What the rater or judge answers |
| `weight` | no | number > 0 | Relative importance when combining scores. Default `1` |
| `scale` | yes | map | Score level (non-negative integer) to anchor text. At least 2 levels |
| `examples` | no | list | Worked examples: `score`, `output`, optional `input` and `rationale` |

Scales don't have to be contiguous. `1 / 3 / 5` is common: raters may still give a 2 or 4 when an output falls between anchors.

### Assertion (`type: assertion`)

A pass/fail rule, usually about what an agent did: which tools it called, in what order, with what arguments.

| Field | Required | Type | Meaning |
|---|---|---|---|
| `id` | yes | slug | Unique within the rubric |
| `type` | yes | `assertion` | Marks this as a pass/fail rule |
| `rule` | yes | string | The rule in plain language |
| `severity` | no | `blocker` \| `warning` | `blocker` fails the whole evaluation. Default `warning` |

In v0.1 the `rule` is plain language. A machine-checkable form for trajectory checks comes in a later version.

## What the schema does not check

The schema checks structure. Quality checks are the linter's job (`rubricate lint`, coming next), including:

- criterion ids that repeat
- examples whose `score` isn't a level on the scale
- vague anchor wording ("good", "appropriate", "reasonable")
- scale levels with no example
- anchors that overlap

## Example

See [`examples/refund-agent.rubric.yaml`](../examples/refund-agent.rubric.yaml).
