# Sample ratings

`refund-human-ratings.csv` is a small, hand-made sample for trying `rubricate calibrate`. It is not data from a study. Three raters score twelve replies on the refund-agent rubric: they mostly agree on `policy_accuracy` and split on `tone`, so the report shows both a reliable criterion and one whose anchors need work.

```bash
rubricate calibrate examples/refund-agent.rubric.yaml --human examples/ratings/refund-human-ratings.csv
```

Format: one row per rating, with columns `item,rater,criterion,score`.
