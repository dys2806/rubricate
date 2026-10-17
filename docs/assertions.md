# Trajectory assertions

Some rules about agents aren't a matter of degree. "Never issue a refund over $100 without approval" either held for a run or it didn't. rubricate checks these rules directly against recorded agent runs (traces). Checks are deterministic and run offline: no model calls, no API key.

```console
$ rubricate check examples/refund-agent.rubric.yaml examples/traces/refund-runs.jsonl
run-approved: ok
  PASS  approval_gate (blocker)
  PASS  lookup_budget (warning)
run-skipped-approval: BLOCKED
  FAIL  approval_gate (blocker): issue_refund called at step 3 where amount > 100 with no earlier human_approval
  PASS  lookup_budget (warning)
run-small-refund: ok
  PASS  approval_gate (blocker)
  PASS  lookup_budget (warning)
run-retry-loop: ok
  PASS  approval_gate (blocker)
  FAIL  lookup_budget (warning): 4 lookup_order calls, budget is 3 (exceeded at step 7)
4 run(s) checked: 1 blocked, 1 with warnings
```

A failed **blocker** fails the run and exits `1`. Failed **warnings** are reported, and fail the command only with `--strict`. Use `--format json` for tooling.

## Writing an assertion

An assertion has a plain-language `rule`, shown in reports, and an optional machine-checkable `check`:

```yaml
- id: approval_gate
  type: assertion
  rule: issue_refund is never called before human_approval when the refund amount is over 100.
  severity: blocker
  check:
    kind: requires_before
    tool: issue_refund
    requires: human_approval
    where:
      amount: { gt: 100 }
```

An assertion without `check` is reported as unchecked, meaning it needs manual review.

### Check kinds

| `kind` | Fields | Passes when |
|---|---|---|
| `requires_before` | `tool`, `requires`, `where`? | Every matching `tool` call comes after at least one `requires` call |
| `forbidden` | `tool`, `where`? | No matching `tool` call happens |
| `required` | `tool`, `where`? | At least one matching `tool` call happens |
| `max_calls` | `max`, `tool`?, `where`? | Matching calls number at most `max`. Without `tool`, every tool call counts |

### Conditions on arguments (`where`)

`where` limits a check to calls whose arguments match every condition. Dotted keys reach into nested arguments.

```yaml
where:
  amount: { gt: 100 }                         # numbers: gt, gte, lt, lte
  currency: { eq: USD }                       # any value: eq, ne
  customer.tier: { in: [gold, platinum] }     # one of a list
```

A call that lacks the argument never matches, and text is never compared to a number.

## Trace format

A trace is one agent run: an `id` and an ordered list of `steps`. Use `.jsonl` for one run per line, or `.json` for a single run or a list of runs.

```json
{
  "id": "run-skipped-approval",
  "steps": [
    {"type": "message", "role": "user", "content": "My blender arrived cracked. Can I get a refund?"},
    {"type": "tool_call", "name": "lookup_order", "args": {"order_id": "A-1042"}},
    {"type": "tool_result", "name": "lookup_order", "output": {"total": 149.99}},
    {"type": "tool_call", "name": "issue_refund", "args": {"order_id": "A-1042", "amount": 149.99}},
    {"type": "message", "role": "assistant", "content": "Done! I've refunded $149.99."}
  ]
}
```

| Step `type` | Fields |
|---|---|
| `message` | `role` (`user` or `assistant`), `content` |
| `tool_call` | `name`, `args` |
| `tool_result` | `name`, `output` (or `content`) |

Step numbers in reports count from 0. Most agent frameworks can export tool calls in this shape with a few lines of code; importers for common trace formats are planned.
