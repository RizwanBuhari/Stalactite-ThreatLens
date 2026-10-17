"""Local IBM Granite explanations via llama.cpp (the same runtime as the IBM lab).

The model runs inside the LinuxONE container; nothing is sent to an external
AI service. It is loaded on first use and shared by all requests.

A 350M base model copies long multi-action sentences back verbatim, so it is
given only the clause that holds the classifier's evidence words. If it still
echoes the text, a plain evidence-based explanation is returned and labelled so.
"""

import re
import threading
import time
from pathlib import Path

GRANITE_PATH = Path("/home/ibm-user/granite-4.0-h-350m-base-be.f16.gguf")

# Few-shot examples teach "name the action, then why it is this technique".
PROMPT = """Report sentence: copied files to a USB drive
Technique: T1052.001 Exfiltration Over Physical Medium: Exfiltration over USB
Why it matches: Copying the files to a USB drive is exfiltration over a physical USB device.

Report sentence: The malware listed installed security products
Technique: T1518.001 Software Discovery: Security Software Discovery
Why it matches: Listing the installed security products is discovery of the victim's security software.

Report sentence: encrypted the file servers
Technique: T1486 Data Encrypted for Impact
Why it matches: Encrypting the file servers makes the data unusable, which is data encrypted for impact.

Report sentence: {clause}
Technique: {technique_id} {name}
Why it matches:"""

# Split at commas/semicolons and at 'and'/'then' joining two actions ('compressed ... and uploaded ...').
CLAUSE_SPLIT = re.compile(r",\s*(?:and\s+|then\s+)?|;\s*|\s+and then\s+|\s+then\s+|\s+and\s+(?=\w+ed\b)")


def focus_clause(sentence, terms):
    """The clause of the sentence that contains most of the evidence words."""
    parts = [p.strip(" ,;.") for p in CLAUSE_SPLIT.split(sentence) if p.strip(" ,;.")]
    def hits(part):
        return sum(all(w in part.lower() for w in t.lower().split()) for t in terms)
    best = max(parts, key=hits) if parts else sentence
    return best if parts and hits(best) else sentence.strip()


def _words(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def _echoes(text, source):
    """True when the output mostly repeats the source text instead of explaining it."""
    out, src = _words(text), set(_words(source))
    return len(src) > 8 and len(out) > 0 and sum(w in src for w in out) / len(out) > 0.9 and len(out) >= 0.8 * len(src)


def _two_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    complete = [p for p in parts if p.endswith((".", "!", "?"))][:2]
    return " ".join(complete) or text.strip()


class Granite:
    def __init__(self, path=GRANITE_PATH, threads=3):
        self.path, self.threads = Path(path), threads
        self._llm, self._lock = None, threading.Lock()
        self.load_seconds = None

    @property
    def available(self):
        return self.path.exists()

    def _load(self):
        if self._llm is None:
            from llama_cpp import Llama
            t0 = time.perf_counter()
            self._llm = Llama(model_path=str(self.path), n_ctx=2048, n_threads=self.threads, verbose=False)
            self.load_seconds = round(time.perf_counter() - t0, 1)

    def explain(self, evidence, technique_id, name, summary, terms=()):
        clause = focus_clause(evidence[:600], list(terms))
        with self._lock:                       # one generation at a time on 3 CPUs
            self._load()
            t0 = time.perf_counter()
            out = self._llm.create_completion(prompt=PROMPT.format(clause=clause, technique_id=technique_id, name=name),
                                              max_tokens=60, temperature=0, stop=["\n", "Report sentence:"])
            seconds = round(time.perf_counter() - t0, 2)
        text = _two_sentences(out["choices"][0]["text"])
        kind = "granite"
        if not text or _echoes(text, evidence):
            kind = "evidence"                  # Granite only repeated the text: say so and explain plainly
            text = f"The passage says “{clause}”, which fits {name}: {summary[:1].lower() + summary[1:]}"
        return {"text": text, "kind": kind, "focus": clause, "seconds": seconds,
                "model": self.path.name, "load_seconds": self.load_seconds}
