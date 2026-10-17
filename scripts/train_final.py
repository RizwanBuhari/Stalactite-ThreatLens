"""Train the model the app serves: train + val, with the settings chosen on val.

    python scripts/train_final.py

Reported metrics stay the ones from scripts/train_baseline.py (test and CISA
were never used for training or tuning). This model only adds the val rows.
Writes models/threatlens_final.joblib and models/threatlens_final.json.
"""

import csv
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from threatlens.model import TechniqueRanker, split_ids  # noqa: E402


def main():
    tuned = json.loads((ROOT / "outputs" / "metrics" / "baseline_metrics.json").read_text())
    rows = []
    for split in ("train", "val"):
        with open(ROOT / "data" / "processed" / f"{split}.csv", encoding="utf-8", newline="") as f:
            rows += list(csv.DictReader(f))
    model = TechniqueRanker(C=tuned["C"], min_support=tuned["min_support"])
    model.fit([r["text"] for r in rows], [split_ids(r["technique_ids"]) for r in rows])
    model.threshold = tuned["threshold"]
    (ROOT / "models").mkdir(exist_ok=True)
    model.save(ROOT / "models" / "threatlens_final.joblib")
    meta = {
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "platform": f"{platform.machine()} / Python {platform.python_version()}",
        "trained_on": "train + val", "rows": len(rows), "C": model.C, "threshold": model.threshold,
        "min_support": model.min_support, "labels": len(model.labels_), "features": model.n_features_,
        "fit_seconds": round(model.fit_seconds_, 1),
        "reported_metrics": "outputs/metrics/baseline_metrics.json (model trained on train only)",
    }
    (ROOT / "models" / "threatlens_final.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
