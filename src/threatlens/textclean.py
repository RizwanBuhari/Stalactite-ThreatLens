"""Text normalisation shared by every data source."""

import re
import unicodedata

MD_LINK = re.compile(r"\[([^\]]*)\]\((?:[^()\s]|\([^()]*\))*(?:\s+\"[^\"]*\")?\)")
CITATION = re.compile(r"\(Citation:[^)]*\)")
URL = re.compile(r"(?:https?://|www\.)\S+")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-�]")  # incl. PDF symbol-font glyphs
SPACES = re.compile(r"\s+")


def clean_text(s):
    """Light cleaning that keeps the analyst-visible wording intact."""
    s = unicodedata.normalize("NFKC", str(s))
    s = CONTROL.sub(" ", s)
    s = MD_LINK.sub(r"\1", s)          # [label](url "title") -> label
    s = CITATION.sub("", s)            # MITRE "(Citation: ...)" markers
    s = URL.sub("", s)
    return SPACES.sub(" ", s).strip(" \t\n\"'")


def dedupe_key(s):
    """Case- and punctuation-insensitive key used to find duplicate sentences."""
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def word_count(s):
    return len(re.findall(r"\w+", s))
