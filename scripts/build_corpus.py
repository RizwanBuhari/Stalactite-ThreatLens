"""Build the unified ThreatLens corpus from every raw source.

Run from the project root inside the notebook container:
    python scripts/build_corpus.py

Writes to data/processed/:
    corpus.csv                 every kept sentence, one row each, with its split
    train.csv val.csv test.csv external_test.csv   the same rows, split apart
    techniques.csv             pinned ATT&CK Enterprise reference + per-split counts
    label_changes.csv          raw IDs that were remapped or dropped
    dropped.csv                rows removed and why
    stats.json                 counts used in the README and the pitch
    ThreatLens_corpus.xlsx     all of the above in one workbook
"""

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from threatlens.attack import AttackReference  # noqa: E402
from threatlens.leakage import LeakStripper, drop_definitions, is_heading  # noqa: E402
from threatlens.sources import load_annoctr, load_cisa, load_ttpm  # noqa: E402
from threatlens.textclean import clean_text, dedupe_key, word_count  # noqa: E402
from threatlens.xlsx import write_xlsx  # noqa: E402

RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
MITRE = ROOT / "data" / "reference" / "mitre" / "enterprise-attack.json"
MIN_WORDS, MAX_WORDS = 4, 300
SHINGLE = 8                       # words per n-gram for the near-duplicate check
CLEAN_MAX_OVERLAP = 0.5           # held-out rows below this overlap form the eval_clean subset
SPLIT_PRIORITY = ["external_test", "test", "val", "train"]  # a duplicate goes to the strictest split
SPLITS = ["train", "val", "test", "external_test"]

COLUMNS = ["sample_id", "split", "text", "technique_ids", "technique_names", "parent_ids",
           "tactics", "n_labels", "source_dataset", "annotation_type", "document_id",
           "source_split", "raw_technique_ids", "label_changes", "train_ngram_overlap",
           "eval_clean", "word_count", "attack_version_source", "licence", "origin_url", "report_date",
           "source_record_ids", "text_hash"]


def shingles(text):
    w = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def main():
    ref = AttackReference(MITRE)
    print(f"ATT&CK reference: {len(ref.active())} active techniques")

    records = []
    records += list(load_ttpm(RAW / "ttpm"))
    records += list(load_annoctr(RAW / "annoctr"))
    records += list(load_cisa(RAW / "cisa" / "pdf", RAW / "cisa" / "manifest.csv", ref))
    print("raw records:", dict(Counter(r["source_dataset"] for r in records)))

    dropped, change_log, stripped = [], Counter(), Counter()
    stripper = LeakStripper(ref)
    kept = []
    for r in records:
        raw_text = r["text"]
        before = clean_text(raw_text)
        text = stripper.strip(before)
        if r["source_dataset"] == "cisa":
            text = drop_definitions(text)
        r["text"] = clean_text(text)
        if r["text"] != before:
            stripped[r["source_dataset"]] += 1
        wc = word_count(r["text"])
        ids, changes = [], []
        for raw in dict.fromkeys(r["raw_ids"]):          # de-duplicate, keep order
            new, status = ref.normalise(raw)
            change_log[(str(raw).strip(), status, new or "", r["source_dataset"])] += 1
            if status != "ok":
                changes.append(f"{raw}->{new}" if new else f"{raw} dropped ({status})")
            if new and new not in ids:
                ids.append(new)
        reason = ("heading or caption" if is_heading(raw_text)
                  else "too short" if wc < MIN_WORDS else "too long" if wc > MAX_WORDS
                  else "no valid technique label" if not ids else "")
        if reason:
            dropped.append({"source_dataset": r["source_dataset"], "source_record_id": r["source_record_id"],
                            "reason": reason, "raw_technique_ids": ";".join(map(str, r["raw_ids"])),
                            "text": r["text"][:300]})
            continue
        r.update(ids=ids, changes=changes, wc=wc, key=dedupe_key(r["text"]))
        kept.append(r)

    # Merge exact duplicates (case/punctuation-insensitive) across all sources.
    groups = defaultdict(list)
    for r in kept:
        groups[r["key"]].append(r)
    merged = []
    for rs in groups.values():
        first = rs[0]
        split = min((r["source_split"] for r in rs), key=SPLIT_PRIORITY.index)
        ids = list(dict.fromkeys(i for r in rs for i in r["ids"]))
        uniq = lambda field: list(dict.fromkeys(r[field] for r in rs if r[field]))  # noqa: E731
        merged.append({
            "split": split,
            "text": first["text"],
            "ids": ids,
            "source_dataset": "|".join(sorted(set(r["source_dataset"] for r in rs))),
            "annotation_type": "|".join(uniq("annotation_type")),
            "document_id": "|".join(uniq("document_id")[:5]),
            "source_split": "|".join(uniq("source_split")),
            "raw_technique_ids": ";".join(dict.fromkeys(str(i) for r in rs for i in r["raw_ids"])),
            "label_changes": "; ".join(dict.fromkeys(c for r in rs for c in r["changes"])),
            "word_count": first["wc"],
            "attack_version_source": "|".join(uniq("attack_version_source")),
            "licence": "|".join(uniq("licence")),
            "origin_url": (uniq("origin_url") or [""])[0],
            "report_date": (uniq("report_date") or [""])[0],
            "source_record_ids": "|".join(uniq("source_record_id")[:5]),
            "n_merged": len(rs),
        })
    merged.sort(key=lambda m: (SPLITS.index(m["split"]), m["source_dataset"]))

    # Near-duplicate check: share of a held-out row's 8-word n-grams that also occur in training text.
    train_shingles = set()
    for m in merged:
        if m["split"] == "train":
            train_shingles |= shingles(m["text"])
    for n, m in enumerate(merged, start=1):
        sh = shingles(m["text"])
        m["train_ngram_overlap"] = (0.0 if m["split"] == "train" or not sh
                                    else round(len(sh & train_shingles) / len(sh), 3))
        m["eval_clean"] = "" if m["split"] == "train" else ("yes" if m["train_ngram_overlap"] < CLEAN_MAX_OVERLAP else "no")
        ids = m["ids"]
        m.update(
            sample_id=f"TL-{n:06d}",
            technique_ids=";".join(ids),
            technique_names=";".join(ref.full_name(i) for i in ids),
            parent_ids=";".join(dict.fromkeys(i.split(".")[0] for i in ids)),
            tactics=";".join(dict.fromkeys(t for i in ids for t in ref.techniques[i].tactics)),
            n_labels=len(ids),
            text_hash=hashlib.sha1(m["text"].encode("utf-8")).hexdigest()[:12],
        )

    OUT.mkdir(parents=True, exist_ok=True)

    def write_csv(path, header, rows):
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    write_csv(OUT / "corpus.csv", COLUMNS, merged)
    for s in SPLITS:
        write_csv(OUT / f"{s}.csv", COLUMNS, [m for m in merged if m["split"] == s])

    counts = {s: Counter(i for m in merged if m["split"] == s for i in m["ids"]) for s in SPLITS}
    techniques = []
    for t in ref.active():
        desc = re.sub(r"\(Citation:[^)]*\)", "", t.description.split("\n\n")[0]).strip()
        techniques.append({
            "technique_id": t.id, "name": t.name, "full_name": ref.full_name(t.id),
            "tactics": ";".join(t.tactics), "is_subtechnique": t.is_subtechnique,
            "parent_id": t.parent_id, "url": t.url, "description": desc[:600],
            **{f"{s}_count": counts[s][t.id] for s in SPLITS},
        })
    tech_cols = list(techniques[0].keys())
    write_csv(OUT / "techniques.csv", tech_cols, techniques)

    changes = [{"raw_id": k[0], "status": k[1], "mapped_to": k[2], "source_dataset": k[3], "count": v}
               for k, v in sorted(change_log.items()) if k[1] != "ok"]
    write_csv(OUT / "label_changes.csv", ["raw_id", "status", "mapped_to", "source_dataset", "count"], changes)
    write_csv(OUT / "dropped.csv", ["source_dataset", "source_record_id", "reason", "raw_technique_ids", "text"], dropped)

    by_src_split = Counter((src, m["split"]) for m in merged for src in m["source_dataset"].split("|"))
    train_ids = set(counts["train"])
    stats = {
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "attack_reference_active_techniques": len(ref.active()),
        "raw_records": dict(Counter(r["source_dataset"] for r in records)),
        "dropped": dict(Counter(d["reason"] for d in dropped)),
        "kept_before_dedupe": len(kept),
        "unique_rows": len(merged),
        "rows_merged_as_duplicates": len(kept) - len(merged),
        "rows_per_split": dict(Counter(m["split"] for m in merged)),
        "rows_per_source_and_split": {f"{a}/{b}": c for (a, b), c in sorted(by_src_split.items())},
        "distinct_techniques_per_split": {s: len(counts[s]) for s in SPLITS},
        "label_assignments_per_split": {s: sum(counts[s].values()) for s in SPLITS},
        "multi_label_rows": sum(1 for m in merged if m["n_labels"] > 1),
        "rows_with_leakage_or_markup_removed": dict(stripped),
        "eval_clean_rows": {s: sum(1 for m in merged if m["split"] == s and m["eval_clean"] == "yes")
                            for s in ("val", "test", "external_test")},
        "train_techniques_with_lt5_examples": sum(1 for c in counts["train"].values() if c < 5),
        "held_out_techniques_unseen_in_train": {s: len(set(counts[s]) - train_ids) for s in ("val", "test", "external_test")},
        "held_out_rows_with_overlap_ge_0.5": {s: sum(1 for m in merged if m["split"] == s and m["train_ngram_overlap"] >= 0.5)
                                             for s in ("val", "test", "external_test")},
        "label_changes": dict(Counter(c["status"] for c in changes for _ in range(c["count"]))),
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2))

    readme = [
        ["Workbook", "ThreatLens unified ATT&CK Enterprise corpus (Team Stalactite, IBM Z Datathon 2026)"],
        ["Built (UTC)", stats["built_utc"]],
        ["Built by", "scripts/build_corpus.py on IBM LinuxONE (notebook container)"],
        ["Label space", f"MITRE ATT&CK Enterprise, pinned bundle data/reference/mitre/enterprise-attack.json ({len(ref.active())} active techniques)"],
        ["One row", "one sentence or short passage with every technique it describes (multi-label, ';'-separated)"],
        ["split", "train / val / test come from each dataset's own split; external_test = CISA advisories, never used for training"],
        ["Duplicates", "identical sentences (ignoring case and punctuation) are merged; a duplicate always goes to its strictest split, so no exact test sentence is in train"],
        ["train_ngram_overlap", "share of the row's 8-word phrases that also occur in training text (near-duplicate warning; 0 for train rows)"],
        ["eval_clean", f"yes = held-out row with train_ngram_overlap < {CLEAN_MAX_OVERLAP}; report metrics on all held-out rows AND on eval_clean = yes"],
        ["Leakage removed", "technique IDs, '(Name [T1234])' tags, markdown table cells with the ID/name, MITRE definitions pasted into CISA tables, update banners; headings and figure captions dropped (src/threatlens/leakage.py)"],
        ["label_changes", "IDs remapped from older ATT&CK versions (revoked -> replacement) or dropped (deprecated/unknown)"],
        ["Sources", "AnnoCTR (CC BY-SA 4.0); TRAM, Procedure+, Expert from Nguyen et al. EACL 2024; CISA advisories (US Government work); see data/SOURCES.md"],
    ]
    summary = [[k, json.dumps(v) if isinstance(v, (dict, list)) else v] for k, v in stats.items()]
    W = {"text": 90, "technique_names": 45, "tactics": 30, "document_id": 40, "origin_url": 35, "licence": 30}
    corpus_widths = [W.get(c, 16) for c in COLUMNS]
    write_xlsx(OUT / "ThreatLens_corpus.xlsx", [
        ("README", ["item", "value"], readme, [24, 140]),
        ("summary", ["metric", "value"], summary, [42, 140]),
        ("corpus", COLUMNS, [[m[c] for c in COLUMNS] for m in merged], corpus_widths),
        ("techniques", tech_cols, [[t[c] for c in tech_cols] for t in techniques],
         [12, 30, 45, 30, 10, 10, 40, 90, 10, 10, 10, 14]),
        ("label_changes", ["raw_id", "status", "mapped_to", "source_dataset", "count"],
         [list(c.values()) for c in changes], None),
        ("dropped", ["source_dataset", "source_record_id", "reason", "raw_technique_ids", "text"],
         [list(d.values()) for d in dropped], [16, 30, 22, 30, 90]),
    ])
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
