"""Build the POC dataset from SummEval's expert annotations.

Downloads the annotations (MIT license, Fabbri et al. 2021), then deterministically:
  1. sets aside a held-out pool of summaries the three experts scored identically,
     which is the only place the revised rubric's worked examples may come from;
  2. samples the evaluation set from the remaining summaries;
  3. writes the batch file the judge scores and the expert ratings `calibrate` reads.

Run from the repo root:  python poc/prepare.py
"""

from __future__ import annotations  # modern type hints on Python 3.10

import csv  # expert ratings in calibrate's CSV format
import hashlib  # verify the download is the expected file
import json  # SummEval and batch files are JSONL
import random  # seeded sampling
import ssl  # certificate checks for the download
import urllib.request  # download without extra dependencies
from pathlib import Path  # file paths

URL = (
    "https://storage.googleapis.com/sfr-summarization-repo-research/model_annotations.aligned.jsonl"
)
SEED = 2026  # fixed, so the sample is reproducible
SAMPLE_SIZE = 200  # summaries in the evaluation set (two rubrics x 200 = 400 judge calls)
DIMENSION = "coherence"  # judged from the summary alone; SummEval omits source articles

HERE = Path(__file__).resolve().parent  # the poc/ folder
DATA = HERE / "data"  # outputs go here
CACHE = HERE / ".cache" / "model_annotations.aligned.jsonl"  # raw download, not committed


def download() -> list[dict]:  # fetch once, then reuse the cached copy
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL}")
        context = ssl.create_default_context()  # the system's trusted certificates
        try:  # python.org's macOS build ships without them; certifi (a dependency) has a copy
            import certifi

            context.load_verify_locations(certifi.where())
        except ImportError:
            pass
        with urllib.request.urlopen(URL, context=context) as resp:  # noqa: S310 - fixed URL
            CACHE.write_bytes(resp.read())
    raw = CACHE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()  # recorded so others can confirm the same input
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    print(f"{len(rows)} annotated summaries, sha256 {digest[:16]}...")
    return rows, digest


def main() -> None:
    rows, digest = download()
    items = []  # one record per summary
    for r in rows:
        scores = [a[DIMENSION] for a in r["expert_annotations"]]  # three experts
        items.append(
            {
                "id": f"{r['id']}:{r['model_id']}",  # article id + system id: unique per summary
                "output": r["decoded"],  # the summary text, as distributed (lowercased, tokenized)
                "scores": scores,
            }
        )
    items.sort(key=lambda x: x["id"])  # stable order before any randomness
    rng = random.Random(SEED)

    # 1. held-out pool: unanimous expert scores, used only for worked examples
    unanimous = [x for x in items if len(set(x["scores"])) == 1]
    held_out = []  # up to 2 per level, chosen at random
    for level in range(1, 6):
        pool = [x for x in unanimous if x["scores"][0] == level]
        held_out += rng.sample(pool, min(2, len(pool)))
    held_ids = {x["id"] for x in held_out}

    # 2. evaluation sample: everything else, sampled at random
    remaining = [x for x in items if x["id"] not in held_ids]
    sample = sorted(rng.sample(remaining, SAMPLE_SIZE), key=lambda x: x["id"])

    # 3. write outputs
    DATA.mkdir(exist_ok=True)
    with (DATA / "sample.jsonl").open("w", encoding="utf-8") as f:  # what the judge scores
        for x in sample:
            f.write(json.dumps({"id": x["id"], "output": x["output"]}) + "\n")
    with (DATA / "expert-ratings.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "rater", "criterion", "score"])
        for x in sample:
            for n, s in enumerate(x["scores"], start=1):
                w.writerow([x["id"], f"expert{n}", DIMENSION, s])
    with (DATA / "held-out-examples.jsonl").open("w", encoding="utf-8") as f:
        for x in held_out:
            f.write(
                json.dumps({"id": x["id"], "score": x["scores"][0], "output": x["output"]}) + "\n"
            )
    (DATA / "SOURCE.md").write_text(
        "# Data source\n\n"
        "Derived from the SummEval expert annotations: Fabbri, Kryściński, McCann, Xiong, Socher, "
        'and Radev, "SummEval: Re-evaluating Summarization Evaluation", TACL 2021. '
        "Annotations released under the MIT license at https://github.com/Yale-LILY/SummEval.\n\n"
        f"- Download: {URL}\n- SHA-256: `{digest}`\n- Seed: {SEED}\n"
        f"- Dimension: {DIMENSION} (1-5, three expert annotators per summary)\n"
        f"- Evaluation sample: {len(sample)} summaries\n"
        f"- Held-out example pool: {len(held_out)} summaries with unanimous expert scores, "
        "excluded from the sample\n\n"
        "Regenerate with `python poc/prepare.py`.\n",
        encoding="utf-8",
    )
    print(f"wrote {len(sample)} sample items and {len(held_out)} held-out examples to {DATA}")


if __name__ == "__main__":
    main()
