"""Train and evaluate the ThreatLens baseline on LinuxONE.

    python scripts/train_baseline.py [--grid 1,4,16] [--min-support 3]

Tuning (C, decision threshold) uses the validation split only. Test and the
CISA external test are scored once with the chosen settings.

Writes:
    models/baseline_tfidf_lr.joblib
    outputs/metrics/baseline_metrics.json
    outputs/metrics/baseline_report.md
    outputs/metrics/baseline_examples.csv   CISA hits and misses for the demo
"""

import argparse
import csv
import json
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from threatlens.metrics import best_threshold, evaluate, parent_ranking, to_parent  # noqa: E402
from threatlens.model import TechniqueRanker, split_ids  # noqa: E402

DATA, MODELS, OUT = ROOT / "data" / "processed", ROOT / "models", ROOT / "outputs" / "metrics"


def load(split):
    with open(DATA / f"{split}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def score_block(model, scores, rows, threshold):
    """Technique- and parent-level metrics for one set of rows."""
    gold = [split_ids(r["technique_ids"]) for r in rows]
    tech = evaluate(scores, model.labels_, gold, threshold)
    ps, parents = parent_ranking(scores, model.labels_, 5)
    par = evaluate(ps, parents, [to_parent(g) for g in gold], threshold)
    known = set(model.labels_)
    tech["coverage"] = round(sum(bool(set(g) & known) for g in gold) / max(len(gold), 1), 4)
    return {"technique": tech, "parent": par}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="1,4,16")
    ap.add_argument("--min-support", type=int, default=3)
    args = ap.parse_args()

    train, val, test, ext = load("train"), load("val"), load("test"), load("external_test")
    tx, ty = [r["text"] for r in train], [split_ids(r["technique_ids"]) for r in train]
    print(f"train={len(train)} val={len(val)} test={len(test)} external_test={len(ext)}", flush=True)

    val_gold = [split_ids(r["technique_ids"]) for r in val]
    tuning, best = [], None
    for C in [float(c) for c in args.grid.split(",")]:
        m = TechniqueRanker(C=C, min_support=args.min_support).fit(tx, ty)
        s = m.scores([r["text"] for r in val])
        h3 = evaluate(s, m.labels_, val_gold, 0.5, ks=(3,))["hit@3"]
        tuning.append({"C": C, "val_hit@3": h3, "fit_seconds": round(m.fit_seconds_, 1)})
        print(f"C={C:<5} val hit@3={h3:.4f}  fit {m.fit_seconds_:.0f}s  labels={len(m.labels_)}", flush=True)
        if best is None or h3 > best[0]:
            best = (h3, m, s)
    _, model, val_scores = best
    model.threshold = best_threshold(val_scores, model.labels_, val_gold)
    print(f"chosen C={model.C}, threshold={model.threshold}", flush=True)

    results = {}
    for name, rows in [("val", val), ("test", test), ("external_test", ext)]:
        s = val_scores if name == "val" else model.scores([r["text"] for r in rows])
        clean = [i for i, r in enumerate(rows) if r["eval_clean"] == "yes"]
        results[name] = {"all": score_block(model, s, rows, model.threshold),
                         "clean": score_block(model, s[clean], [rows[i] for i in clean], model.threshold)}
        if name == "test":
            by_src = {}
            for src in sorted({r["source_dataset"] for r in rows}):
                idx = [i for i, r in enumerate(rows) if r["source_dataset"] == src]
                by_src[src] = score_block(model, s[idx], [rows[i] for i in idx], model.threshold)
            results["test_by_source"] = by_src
        if name == "external_test":
            ext_scores = s

    # Latency: one sentence at a time, as the UI calls it.
    sample = random.Random(0).sample([r["text"] for r in ext], 200)
    model.rank(sample[:5])                                   # warm-up
    t0 = time.perf_counter()
    for t in sample:
        model.rank([t])
    per_sentence_ms = (time.perf_counter() - t0) / len(sample) * 1000
    t0 = time.perf_counter()
    model.scores([r["text"] for r in ext])
    batch_per_sec = len(ext) / (time.perf_counter() - t0)

    # Demo material: CISA rows where the right technique is / is not in the top 3.
    top = np.argsort(-ext_scores, axis=1)[:, :3]
    examples = []
    for i, r in enumerate(ext):
        preds = [model.labels_[j] for j in top[i]]
        gold = split_ids(r["technique_ids"])
        examples.append({"sample_id": r["sample_id"], "hit_in_top3": bool(set(preds) & set(gold)),
                         "gold": r["technique_ids"], "gold_names": r["technique_names"],
                         "top3": ";".join(preds),
                         "top3_scores": ";".join(f"{ext_scores[i, j]:.3f}" for j in top[i]),
                         "eval_clean": r["eval_clean"], "text": r["text"]})

    MODELS.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    model.save(MODELS / "baseline_tfidf_lr.joblib")
    with open(OUT / "baseline_examples.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(examples[0]))
        w.writeheader()
        w.writerows(examples)

    report = {
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "platform": f"{platform.machine()} / Python {platform.python_version()}",
        "model": "TF-IDF (word 1-2 + char 3-5 n-grams) + one-vs-rest logistic regression",
        "C": model.C, "threshold": model.threshold, "min_support": model.min_support,
        "labels_in_model": len(model.labels_), "features": model.n_features_,
        "fit_seconds": round(model.fit_seconds_, 1), "tuning": tuning,
        "latency_ms_per_sentence": round(per_sentence_ms, 2),
        "batch_sentences_per_second": round(batch_per_sec, 1),
        "results": results,
    }
    (OUT / "baseline_metrics.json").write_text(json.dumps(report, indent=2))

    lines = [f"# ThreatLens baseline results ({report['built_utc']} UTC, {report['platform']})", "",
             f"Model: {report['model']}; C={model.C}; threshold={model.threshold} (tuned on val); "
             f"{len(model.labels_)} techniques with >= {model.min_support} training examples; "
             f"fit {report['fit_seconds']} s; {report['latency_ms_per_sentence']} ms per sentence.", "",
             "| Split | Subset | Level | Rows | Hit@1 | Hit@3 | Hit@5 | Recall@3 | Micro-F1 | Macro-F1 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for split in ("val", "test", "external_test"):
        for subset in ("all", "clean"):
            for level in ("technique", "parent"):
                m = results[split][subset][level]
                lines.append(f"| {split} | {subset} | {level} | {m['rows']} | {m['hit@1']:.3f} | {m['hit@3']:.3f} | "
                             f"{m['hit@5']:.3f} | {m['recall@3']:.3f} | {m['micro_f1']:.3f} | {m['macro_f1']:.3f} |")
    lines += ["", "Test split by source (all rows):", "",
              "| Source | Rows | Hit@3 technique | Hit@3 parent |", "|---|---|---|---|"]
    for src, b in results["test_by_source"].items():
        lines.append(f"| {src} | {b['technique']['rows']} | {b['technique']['hit@3']:.3f} | {b['parent']['hit@3']:.3f} |")
    (OUT / "baseline_report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
