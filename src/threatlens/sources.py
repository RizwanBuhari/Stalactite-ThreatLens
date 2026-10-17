"""Loaders that turn each raw dataset into common records.

Every record is a dict with:
  source_dataset, source_record_id, document_id, source_split, text,
  raw_ids (list), annotation_type, attack_version_source, licence,
  origin_url, report_date
"""

import ast
import csv
import json
import re
from pathlib import Path

from .attack import ID_RE, clean_id
from .textclean import clean_text, word_count

SPLIT_NAMES = {"train": "train", "dev": "val", "val": "val", "test": "test"}

TTPM_LICENCE = "CC BY 4.0 (README badge says CC BY-NC-SA 4.0)"
TTPM_URL = "https://github.com/tumeteor/mitre-ttp-mapping (Nguyen et al., EACL 2024)"
TTPM_SETS = {
    "tram": "TRAM (via Nguyen et al.)",
    "procedure": "MITRE procedure examples (Procedure+)",
    "derived_procedure": "Derived procedures (Procedure+)",
    "expert": "Expert-annotated reports (Nguyen et al.)",
}


def _record(**kw):
    base = dict(source_dataset="", source_record_id="", document_id="", source_split="",
                text="", raw_ids=[], annotation_type="", attack_version_source="",
                licence="", origin_url="", report_date="")
    base.update(kw)
    return base


# --- TRAM, Procedure+, Expert (Nguyen et al. TTP-mapping release) ------------------

def load_ttpm(folder):
    folder = Path(folder)
    for name in TTPM_SETS:
        for split in ("train", "dev", "test"):
            path = folder / f"{name}_{split}.tsv"
            with open(path, encoding="utf-8", newline="") as f:
                for i, row in enumerate(csv.DictReader(f, delimiter="\t"), start=1):
                    try:
                        labels = ast.literal_eval(row["labels"])
                    except (ValueError, SyntaxError):
                        labels = ID_RE.findall(row.get("labels") or "")
                    yield _record(
                        source_dataset=name,
                        source_record_id=f"{path.name}:{i}",
                        document_id=f"{name}:{split}:{i}",
                        source_split=SPLIT_NAMES[split],
                        text=row["text1"],
                        raw_ids=list(labels),
                        annotation_type="dataset label",
                        attack_version_source="v12.0",
                        licence=TTPM_LICENCE,
                        origin_url=TTPM_URL,
                    )


# --- AnnoCTR (Bosch, LREC-COLING 2024) ----------------------------------------------

def load_annoctr(folder):
    """One record per sentence, merging every technique linked inside it."""
    folder = Path(folder)
    for split in ("train", "dev", "test"):
        sentences = {}
        with open(folder / "linking_mitre_only" / f"{split}.jsonl", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                m = re.search(r"attack\.mitre\.org/techniques/(T\d{4}(?:/\d{3})?)", r.get("label_link", ""))
                if not m:
                    continue  # malware, groups, tactics, tools: not technique labels
                text = r["_context_left"] + r["mention"] + r["_context_right"]
                key = (r["document"], text)
                s = sentences.setdefault(key, {"ids": [], "types": set()})
                s["ids"].append(clean_id(m.group(1)))
                s["types"].add("explicit" if r["entity_class"] == "CE" else "implicit")
        for n, ((doc, text), s) in enumerate(sentences.items(), start=1):
            yield _record(
                source_dataset="annoctr",
                source_record_id=f"{split}.jsonl:{n}",
                document_id=f"annoctr:{doc}",
                source_split=SPLIT_NAMES[split],
                text=text,
                raw_ids=s["ids"],
                annotation_type="+".join(sorted(s["types"])),
                attack_version_source="2023 (AnnoCTR release)",
                licence="CC BY-SA 4.0",
                origin_url="https://github.com/boschresearch/anno-ctr-lrec-coling-2024",
                report_date=doc.split("_")[1] if doc.count("_") >= 2 else "",
            )


# --- CISA advisories (PDF) ------------------------------------------------------------

BOILERPLATE = re.compile(
    r"^\s*(?:Page\s*\|?\s*\d+\s*(?:of\s*\d+)?.*|\d+\s*|.*\bProduct ID:.*|.*\bTLP:\s*(?:CLEAR|WHITE|GREEN|AMBER).*)$",
    re.I)
TABLE_HEADER = re.compile(r"Technique\s+(?:Title|Name)\s+ID\s+Use", re.I)
ZONE_END = re.compile(r"(?m)^\s*(?:Table\s+\d+\s*[:.].*|[A-Z][A-Z0-9 &/,()\-]{5,})\s*$")
BARE_ID = re.compile(r"(?<![\w\[.])(T\d{4}(?:\.\d{3})?)(?![\w\]])")
BRACKET = re.compile(r"\[([^\]]*T\d{4}[^\]]*)\]")
PAREN_WITH_ID = re.compile(r"\s*\((?:[^()]|\([^()]*\))*?\[[^\]]*T\d{4}[^\]]*\](?:[^()]|\([^()]*\))*\)")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"“])|\s*[•▪●]\s*")
AGENCY_BAR = re.compile(r"(?:\b[A-Z][A-Z-]+\b\s*\|\s*)+\b[A-Z][A-Z-]+\b")
UPDATE_MARK = re.compile(r"\b(?:Begin|End)\s+Update\b")
MAX_CISA_WORDS = 80


def _tidy(text, ids, ref):
    """Remove layout residue around a CISA passage: agency bars, update markers,
    tactic headings at either end, and the technique's own title at the start
    (that title would hand the model its answer)."""
    text = UPDATE_MARK.sub(" ", AGENCY_BAR.sub(" ", text))
    text = re.sub(r"(?:\s*\|\s*[A-Z][\w&.-]*)+\s*$", "", text)       # "... | Treasury | FinCEN"
    text = re.sub(r"^\s*(?:[A-Z][\w&.-]*\s*\|\s*)+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ;,")
    titles = [n for i in ids for n in (ref.full_name(i),
              ref.techniques[i].name if i in ref.techniques else "") if n]
    lead = "|".join(re.escape(n) for n in sorted(set(titles) | set(ref.tactic_names), key=len, reverse=True))
    tactics = "|".join(re.escape(n) for n in ref.tactic_names)
    for _ in range(3):
        before = text
        text = re.sub(rf"^(?:{lead})\b[\s:,-]*(?=[A-Z0-9\"“(])", "", text)
        text = re.sub(rf"(?<=[.!?)\"”])\s+(?:{tactics})$", "", text)
        text = text.strip(" ;,")
        if text == before:
            break
    return text


def _pdf_text(path):
    from pypdf import PdfReader  # imported here so other loaders work without pypdf
    lines = []
    for page in PdfReader(str(path)).pages:
        for line in (page.extract_text() or "").splitlines():
            if line.strip() and not (BOILERPLATE.match(line) and len(line) < 100):
                lines.append(line.rstrip())
    # PDF extraction sometimes splits an ID inside its citation: '[T1 197]' -> '[T1197]'
    return re.sub(r"\[T(\d)\s+(\d{3}(?:\.\d{3})?)\]", r"[T\1\2]", "\n".join(lines))


def _strip_suffix(segment, names):
    """Remove the next table row's technique title from the end of a 'Use' cell."""
    for name in names:
        tokens = re.findall(r"\w+", name)
        if not tokens:
            continue
        pat = re.compile(r"\W*".join(map(re.escape, tokens)) + r"[\W]*$", re.I)
        m = pat.search(segment)
        if m:
            return segment[:m.start()]
    return segment


def _table_rows(text, ref):
    """Yield (use_text, [ids]) from 'Technique Title | ID | Use' tables."""
    headers = list(TABLE_HEADER.finditer(text))
    for h, header in enumerate(headers):
        end = headers[h + 1].start() if h + 1 < len(headers) else len(text)
        zone = text[header.end():end]
        stop = ZONE_END.search(zone)
        if stop:
            zone = zone[:stop.start()]
        zone = re.sub(r"\s*\n\s*", " ", zone)
        ids = list(BARE_ID.finditer(zone))
        pending = []
        for i, m in enumerate(ids):
            seg_end = ids[i + 1].start() if i + 1 < len(ids) else len(zone)
            seg = zone[m.end():seg_end]
            if i + 1 < len(ids):
                nxt = ids[i + 1].group(1)
                t = ref.techniques.get(nxt)
                seg = _strip_suffix(seg, [ref.full_name(nxt), t.name if t else ""])
            seg = seg.strip(" ;,")
            pending.append(m.group(1))
            if word_count(seg) >= 4:
                yield seg, pending
                pending = []


def _inline_sentences(text, ref):
    """Yield (sentence_without_citations, [ids]) for sentences citing [Txxxx]."""
    flat = re.sub(r"\s*\n\s*", " ", text)
    # A tactic heading between two bullets ("...tools Credential Access The actors...") is a boundary.
    tactics = "|".join(re.escape(n) for n in ref.tactic_names)
    flat = re.sub(rf"(?<=[a-z0-9)\]])\s+(?:{tactics})\s+(?=[A-Z])", ". ", flat)
    for sent in SENT_SPLIT.split(flat):
        brackets = BRACKET.findall(sent)
        if not brackets or re.search(r"ATT&CK\s+IDs?\b", sent):
            continue  # no citation, or a footnote list of IDs rather than a behaviour sentence
        ids = [i for b in brackets for i in ID_RE.findall(b)]
        cleaned = PAREN_WITH_ID.sub("", sent)
        cleaned = re.sub(r"\s*\[[^\]]*T\d{4}[^\]]*\]", "", cleaned)
        cleaned = re.sub(r"\s+([,.;:])(?=\s|$)", r"\1", cleaned).strip(" ,;:")
        if word_count(cleaned) >= 5:
            yield cleaned, ids


def load_cisa(folder, manifest_path, ref):
    folder = Path(folder)
    with open(manifest_path, encoding="utf-8", newline="") as f:
        manifest = [r for r in csv.DictReader(f) if r["status"] == "use"]
    for row in manifest:
        text = _pdf_text(folder / row["file"])
        headers = list(TABLE_HEADER.finditer(text))
        # Inline citations are taken only outside the tables, so rows are not counted twice.
        outside = text[:headers[0].start()] if headers else text
        found = [(t, ids, "CISA ATT&CK table row") for t, ids in _table_rows(text, ref)]
        found += [(t, ids, "CISA inline citation") for t, ids in _inline_sentences(outside, ref)]
        found = [(_tidy(t, ids, ref), ids, kind) for t, ids, kind in found]
        found = [f for f in found if MAX_CISA_WORDS >= word_count(f[0]) >= 4]
        for n, (t, ids, kind) in enumerate(found, start=1):
            yield _record(
                source_dataset="cisa",
                source_record_id=f"{row['file']}:{n}",
                document_id=f"cisa:{row['document_group']}",
                source_split="external_test",
                text=t,
                raw_ids=ids,
                annotation_type=kind,
                attack_version_source="as published in advisory",
                licence="US Government work (public domain)",
                origin_url=row.get("source_url") or (
                    f"https://www.cisa.gov/news-events/cybersecurity-advisories/{row['advisory_id'].lower()}"
                    if row.get("advisory_id", "").startswith("AA") else ""),
                report_date=row.get("report_date", ""),
            )
