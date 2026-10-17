# Data source

Derived from the SummEval expert annotations: Fabbri, Kryściński, McCann, Xiong, Socher, and Radev, "SummEval: Re-evaluating Summarization Evaluation", TACL 2021. Annotations released under the MIT license at https://github.com/Yale-LILY/SummEval.

- Download: https://storage.googleapis.com/sfr-summarization-repo-research/model_annotations.aligned.jsonl
- SHA-256: `f0d4166e0cdeb439b387c4449634b067b7e9f721b9ef4c2b722f6b7550d3d6ab`
- Seed: 2026
- Dimension: coherence (1-5, three expert annotators per summary)
- Evaluation sample: 200 summaries
- Held-out example pool: 10 summaries with unanimous expert scores, excluded from the sample

Regenerate with `python poc/prepare.py`.
