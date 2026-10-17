"""Remove answer leakage and layout residue from input text.

A training sentence must describe behaviour, not carry its own label: technique
IDs, '(Technique Name [T1234])' tags, markdown table cells holding the ID or
name, headings and figure captions are all removed or dropped here.
"""

import re

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
TECH_ID = r"T\d{4}(?:\.\d{3})?"

HEADING = re.compile(r"^\s*#{1,6}\s")
# 'Figure 5: ...' / 'Figure 5 Uploading ...' are captions; 'Figure 7 shows how DCRat ...' is a real sentence.
CAPTION = re.compile(r"^[\W_]*((?i:Figure|Fig\.|Table|Image|Screenshot|Exhibit))\s*\d+\s*(?:[:.\-–]|$|(?=[A-Z(\"“]))")
CAPTION_MAX_WORDS = 20
WRAPPED = re.compile(r"^\s*(\*{1,3}|_{1,3}).+\1\s*$")          # whole line in *italics* / **bold**
BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
LIST_MARK = re.compile(r"^\s*(?:[-*+•o]|\d{1,2}[.)])\s+")
BANNER = re.compile(rf"\(?\b(?:Begin\s+|End\s+)?(?:Update[d]?|New)[,:]?\s+(?:on\s+)?(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}\)?:?", re.I)
PAREN_ID = re.compile(rf"\s*\((?:[^()]|\([^()]*\))*?\b{TECH_ID}\b(?:[^()]|\([^()]*\))*\)")
BRACKET_ID = re.compile(rf"\s*\[[^\]]*\b{TECH_ID}\b[^\]]*\]")
PAREN_TACTIC = re.compile(r"\s*\((?:[^()]|\([^()]*\))*?\[\s*TA\d{4}\s*\](?:[^()]|\([^()]*\))*\)")
LOOSE_BRACKET_ID = re.compile(r"\s*\[\s*T\s?A?\s?\d{4}(?:\s?\.\s?\d{3})?\s*\]")
DEFN_TABLE = re.compile(r"\bID\s+Name\s+Description\b.*$")
FOOTNOTE_TAIL = re.compile(r"(?<=[.!?])\d{1,2}$")


def is_heading(raw):
    """True for markdown headings, figure/table captions and short title-like lines."""
    s = raw.strip()
    words = re.findall(r"[A-Za-z][\w'/-]*", s)
    if HEADING.match(s):
        return True
    cap = CAPTION.match(s)
    # Short captions go; long text after a caption is kept, except table dumps that list technique names.
    if cap and (len(words) <= CAPTION_MAX_WORDS or cap.group(1).lower() == "table"):
        return True
    if WRAPPED.match(s) and len(words) <= 20:
        return True
    if 0 < len(words) <= 10 and not re.search(r"[.!?:;)\"”]$", s):
        long_words = [w for w in words if len(w) > 3]
        if long_words and sum(w[0].isupper() for w in long_words) / len(long_words) >= 0.8:
            return True
    return False


class LeakStripper:
    def __init__(self, ref):
        names = set()
        for t in ref.techniques.values():
            names.add(t.name)
            names.add(ref.full_name(t.id))
        names |= set(ref.tactic_names) | {"Enterprise", "Mobile", "ICS"}
        alts = "|".join(re.escape(n) for n in sorted((n for n in names if n), key=len, reverse=True))
        self.name_cell = re.compile(rf"^(?:{alts})$", re.I)
        # 'T1482: Domain Trust Discovery' / 'T1105 - Remote File Copy' -> removed together
        self.id_with_name = re.compile(rf"\b{TECH_ID}\b\s*[:\-–|]?\s*(?:(?:{alts})\b)?", re.I)

    def _table_row(self, s):
        cells = [c.strip() for c in s.strip().strip("|").split("|")]
        keep = []
        for i, c in enumerate(cells):
            if not c or re.fullmatch(TECH_ID, c) or self.name_cell.match(c):
                continue
            # The cell right after an ID cell is the technique's (possibly older) name.
            after_id = i > 0 and re.fullmatch(TECH_ID, cells[i - 1])
            if after_id and len(c.split()) <= 8 and not re.search(r"[.!?]$", c):
                continue
            keep.append(c)
        return "; ".join(keep)

    def strip(self, text):
        s = BOLD.sub(r"\2", text)
        s = LIST_MARK.sub("", s)
        if s.lstrip().startswith("|") or s.rstrip().endswith("|"):
            s = self._table_row(s)
        s = BANNER.sub(" ", s)
        s = DEFN_TABLE.sub("", s)
        s = PAREN_ID.sub("", s)
        s = BRACKET_ID.sub("", s)
        s = PAREN_TACTIC.sub("", s)          # '(Initial Access [TA0001])' also hints at the label
        s = LOOSE_BRACKET_ID.sub("", s)      # '[TA0001]', '[T 1059.001 ]'
        s = re.sub(r"\s*\[?\s*\bTA\d{4}\b\]?", "", s)   # unclosed '[TA0003' or bare 'TA0001'
        s = self.id_with_name.sub(" ", s)
        s = re.sub(r"(?:^|\s)\(\s*[,;]?\s*\)", "", s)   # standalone empty brackets left behind (not 'eval()')
        s = re.sub(r"\s+([,.;:])(?=\s|$)", r"\1", s)     # 'data .' -> 'data.' but keep code like 'PM* .tmp'
        s = re.sub(r"\s+", " ", s).strip(" ;,|-")
        return FOOTNOTE_TAIL.sub("", s)


def drop_definitions(text):
    """CISA tables sometimes paste MITRE's own definition ('Adversaries may ...'): not evidence."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(p for p in parts if not p.startswith("Adversaries may")).strip()
