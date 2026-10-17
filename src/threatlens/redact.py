"""Mask sensitive values before a passage is analysed, stored or exported.

Threat reports name the victim's infrastructure: IP addresses, domains, emails,
file hashes, user folders. ThreatLens masks them first, so saved reviews and
exports never contain them ("innovation without exposure").
"""

import re

DOT = r"(?:\.|\[\.\]|\(\.\))"           # also defanged dots: 1.2.3[.]4, evil(.)com
TLDS = ("com|net|org|io|info|biz|xyz|top|online|site|club|ru|cn|ir|kp|uk|de|fr|nl|co|us|eu|"
        "gov|edu|mil|int|me|tk|cc|su|in|br|jp|kr|tw|hk|sg|ae|sa")

PATTERNS = [
    ("URL", re.compile(r"\b(?:h(?:tt|xx)ps?|ftp)\[?:\]?//\S+", re.I)),
    ("EMAIL", re.compile(rf"\b[\w.+-]+(?:@|\[@\]|\[at\])[A-Za-z0-9-]+(?:{DOT}[A-Za-z0-9-]+)+\b", re.I)),
    ("HASH", re.compile(r"\b(?:[a-f0-9]{64}|[a-f0-9]{40}|[a-f0-9]{32})\b", re.I)),
    ("IP", re.compile(rf"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:{DOT}(?:25[0-5]|2[0-4]\d|1?\d?\d)){{3}}(?::\d{{2,5}})?\b")),
    ("DOMAIN", re.compile(rf"\b(?:[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?{DOT})+(?:{TLDS})\b", re.I)),
    ("USER", re.compile(r"(?<=[A-Za-z]:\\Users\\)[^\\\s\"']+", re.I)),
    ("USER", re.compile(r"(?<=/home/)[^/\s\"']+")),
]


def redact(text):
    """Returns (masked_text, counts_by_type)."""
    counts = {}
    for label, pat in PATTERNS:
        text, n = pat.subn(f"[{label}]", text)
        if n:
            counts[label] = counts.get(label, 0) + n
    return text, counts
