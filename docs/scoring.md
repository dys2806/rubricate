# Scoring with an LLM judge

`rubricate score` grades responses against a rubric using an LLM judge. Unlike `validate` and `lint`, which run offline, scoring calls a model API, so you need your own API key. Calls are billed to (or counted against the free tier of) whoever owns the key.

## Setup (Gemini, free tier)

1. Create a key at [Google AI Studio](https://aistudio.google.com/apikey). The free tier needs no credit card.
2. Install Gemini support and set the key on your own machine:

```bash
pip install -e ".[gemini]"          # or: pip install 'rubricate[gemini]' once released
export GEMINI_API_KEY=your-key       # never commit this or paste it into a file in the repo
```

> **Free-tier notes.** The free tier is rate-limited to a few requests per minute and a daily cap; rubricate retries rate-limited calls with backoff. Check Google's current terms for how free-tier inputs may be used. Don't send private or confidential data to a free-tier key.

## Grade one response

Real output from `gemini-3.8-flash` (wording and scores can vary between runs and models):

```console
$ rubricate score examples/refund-agent.rubric.yaml \
    --input "My blender arrived cracked. Can I get a refund?" \
    --output "Under section 4.2 you can get a full refund within 30 days with the receipt."
policy_accuracy      5/5  The response names section 4.2, specifies the 30-day window, full refund amount, and the receipt requirement.
tone                 1/5  The reply completely ignores the customer's specific issue of the blender arriving cracked.
approval_gate        skipped (assertion; verify with `rubricate check` on agent traces)
lookup_budget        skipped (assertion; verify with `rubricate check` on agent traces)
weighted score: 71%  (judge: gemini:gemini-3.8-flash)
```

The reply is accurate but never acknowledges the cracked blender, so it earns full marks on policy and the lowest tone level. The weighted score combines both by their rubric weights (0.5 and 0.2).

Add `--format json` for machine-readable output. `--output-file reply.txt` reads the response from a file.

## Grade a batch

Put one response per line in a JSONL file:

```json
{"id": "t1", "input": "Can I return this?", "output": "Yes, within 30 days with a receipt."}
{"id": "t2", "output": "You can return it anytime!"}
```

```bash
rubricate score examples/refund-agent.rubric.yaml --batch replies.jsonl --out scores.jsonl
```

Each output line carries the input's `id`, every criterion's score and rationale, and a `weighted` total from 0 to 1. A response the judge can't grade is recorded with an `error` field and the run continues; the command exits `1` if any item failed. Results are written as they arrive, so an interrupted run keeps what it finished.

## How scoring works

- **One call per response.** The judge sees every scored criterion, its anchors in order, and its worked examples, then returns a score and a one-line rationale per criterion.
- **Structured output.** The judge must reply in a fixed JSON shape, with criterion ids restricted to the rubric's own.
- **Validated replies.** rubricate rejects any reply that skips a criterion, scores one twice, invents one, or gives a score outside the scale. In-between integers (a 4 on a 1/3/5 scale) are allowed.
- **Deterministic settings.** Temperature is 0, to make scores as repeatable as the model allows.
- **Assertions are skipped.** Pass/fail rules about agent behavior are checked deterministically from traces with `rubricate check` ([assertions.md](assertions.md)), not by a judge.
- **Weighted total.** Each criterion is normalized to 0–1 on its own scale, then averaged using the rubric's weights.

## Choosing the judge

`--judge provider:model`. The default is `gemini:gemini-3.8-flash`. Any Gemini model id works, e.g. `--judge gemini:gemini-3.5-flash-lite`. More providers are planned.

## Testing

Unit tests cover prompt construction and reply validation without calling a model. One live test calls Gemini for real and runs only when `GEMINI_API_KEY` is set, locally or as a repository secret in CI:

```bash
GEMINI_API_KEY=your-key pytest -m live
```
