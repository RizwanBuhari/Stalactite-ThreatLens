"""Pinned MITRE ATT&CK Enterprise reference: technique lookup and ID normalisation."""

import json
import re
from dataclasses import dataclass, field

ID_RE = re.compile(r"T\d{4}(?:\.\d{3})?")


@dataclass
class Technique:
    id: str
    name: str
    description: str
    url: str
    tactics: list = field(default_factory=list)
    revoked: bool = False
    deprecated: bool = False
    stix_id: str = ""

    @property
    def is_subtechnique(self):
        return "." in self.id

    @property
    def parent_id(self):
        return self.id.split(".")[0]


def clean_id(raw):
    """'t1059/001 ' -> 'T1059.001'; returns None if it is not a technique ID."""
    s = str(raw).strip().upper().replace("/", ".")
    return s if ID_RE.fullmatch(s) else None


class AttackReference:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            objects = json.load(f)["objects"]
        by_stix, self.techniques = {}, {}
        for o in objects:
            if o.get("type") != "attack-pattern":
                continue
            ext = next((r for r in o.get("external_references", [])
                        if r.get("source_name") == "mitre-attack"), None)
            if not ext or not clean_id(ext.get("external_id", "")):
                continue
            t = Technique(
                id=clean_id(ext["external_id"]),
                name=o.get("name", ""),
                description=o.get("description", ""),
                url=ext.get("url", ""),
                tactics=[p["phase_name"] for p in o.get("kill_chain_phases", [])
                         if p.get("kill_chain_name") == "mitre-attack"],
                revoked=bool(o.get("revoked")),
                deprecated=bool(o.get("x_mitre_deprecated")),
                stix_id=o["id"],
            )
            by_stix[t.stix_id] = t
            current = self.techniques.get(t.id)
            # The same ID can appear twice (an old revoked copy and a live one): prefer the live one.
            if current is None or (current.revoked or current.deprecated) and not (t.revoked or t.deprecated):
                self.techniques[t.id] = t
        # Current tactic names plus older ones still printed in advisories.
        self.tactic_names = sorted({o["name"] for o in objects if o.get("type") == "x-mitre-tactic"}
                                   | {"Defense Evasion", "Command and Control"}, key=len, reverse=True)
        self._revoked_by = {o["source_ref"]: o["target_ref"] for o in objects
                            if o.get("type") == "relationship"
                            and o.get("relationship_type") == "revoked-by"}
        self._by_stix = by_stix

    def is_active(self, tid):
        t = self.techniques.get(tid)
        return t is not None and not t.revoked and not t.deprecated

    def normalise(self, raw):
        """Map a raw ID to an active technique ID in this release.

        Returns (new_id or None, status) where status is one of
        'ok', 'revoked', 'deprecated', 'unknown', 'invalid'.
        """
        tid = clean_id(raw)
        if tid is None:
            return None, "invalid"
        t = self.techniques.get(tid)
        if t is None:
            return None, "unknown"
        if self.is_active(tid):
            return tid, "ok"
        if t.revoked:
            stix = t.stix_id
            for _ in range(5):  # follow revoked-by chains
                stix = self._revoked_by.get(stix)
                nxt = self._by_stix.get(stix)
                if nxt is None:
                    break
                if self.is_active(nxt.id):
                    return nxt.id, "revoked"
                stix = nxt.stix_id
            return None, "revoked"
        return None, "deprecated"

    def full_name(self, tid):
        """'Phishing: Spearphishing Attachment' for sub-techniques, plain name otherwise."""
        t = self.techniques.get(tid)
        if t is None:
            return ""
        if t.is_subtechnique and t.parent_id in self.techniques:
            return f"{self.techniques[t.parent_id].name}: {t.name}"
        return t.name

    def active(self):
        return sorted((t for t in self.techniques.values() if self.is_active(t.id)),
                      key=lambda t: t.id)
