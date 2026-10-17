"""Local IBM Granite explanations via llama.cpp (the same runtime as the IBM lab).

The model runs inside the LinuxONE container; nothing is sent to an external
AI service. It is loaded on first use and shared by all requests.
"""

import re
import threading
import time
from pathlib import Path

GRANITE_PATH = Path("/home/ibm-user/granite-4.0-h-350m-base-be.f16.gguf")

# Few-shot prompt that anchors the answer to the report text ("The report says ...");
# without it the small base model drifts into generic claims about the technique.
PROMPT = """Report sentence: The actors sent emails with malicious Word attachments to employees.
Technique: T1566.001 Phishing: Spearphishing Attachment
Why it matches: The report says the actors emailed malicious attachments to employees, which is spearphishing with an attachment.

Report sentence: The malware queried the registry to list installed security products.
Technique: T1518.001 Software Discovery: Security Software Discovery
Why it matches: The report says the malware listed installed security products, which is discovery of security software.

Report sentence: {evidence}
Technique: {technique_id} {name}
Why it matches: The report says"""


def _two_sentences(text):
    """Keep at most two complete sentences; a small base model tends to run on."""
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

    def explain(self, evidence, technique_id, name, summary):
        with self._lock:                       # one generation at a time on 3 CPUs
            self._load()
            prompt = PROMPT.format(evidence=evidence[:600], technique_id=technique_id, name=name)
            t0 = time.perf_counter()
            out = self._llm.create_completion(prompt=prompt, max_tokens=60, temperature=0,
                                              stop=["\n", "Report sentence:"])
            text = _two_sentences("The report says " + out["choices"][0]["text"].strip())
            return {"text": text, "seconds": round(time.perf_counter() - t0, 2),
                    "model": self.path.name, "load_seconds": self.load_seconds}
