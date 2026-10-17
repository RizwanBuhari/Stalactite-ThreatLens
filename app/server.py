"""ThreatLens web app, served from the LinuxONE notebook container.

    python app/server.py [--socket run/threatlens.sock]

The server listens on a Unix socket inside the project folder, so no network
port is opened. Reach it from a laptop with SSH forwarding:
    ssh -N -L 8050:/home/linux1/shared/threatlens/run/threatlens.sock linux1@<server>
then open http://localhost:8050
"""

import argparse
import csv
import io
import json
import os
import platform
import random
import re
import socketserver
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from importlib import metadata
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
DESIGN = ROOT / "design"
REVIEWS = ROOT / "outputs" / "reviews"
sys.path.insert(0, str(ROOT / "src"))

from threatlens.explain import Explainer  # noqa: E402
from threatlens.granite import Granite  # noqa: E402
from threatlens.model import TechniqueRanker  # noqa: E402
from threatlens.redact import redact  # noqa: E402

MAX_BODY = 200_000
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
        ".json": "application/json"}
EXPORT_FIELDS = ["review_id", "saved_utc", "analyst", "technique_id", "technique_name", "decision",
                 "corrected_to", "corrected_name", "model_score", "model_rank", "evidence", "note",
                 "passage_redacted"]


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class App:
    def __init__(self):
        t0 = time.perf_counter()
        path = ROOT / "models" / "threatlens_final.joblib"
        if not path.exists():
            path = ROOT / "models" / "baseline_tfidf_lr.joblib"
        self.model_path = path
        self.model = TechniqueRanker.load(path)
        self.explainer = Explainer(self.model)
        self.load_seconds = round(time.perf_counter() - t0, 1)
        self.techniques = {}
        with open(ROOT / "data" / "processed" / "techniques.csv", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                self.techniques[r["technique_id"]] = r
        self.granite = Granite()
        meta = ROOT / "models" / "threatlens_final.json"
        self.model_meta = json.loads(meta.read_text()) if meta.exists() else {}
        self.samples = self._samples()
        REVIEWS.mkdir(parents=True, exist_ok=True)

    def _samples(self):
        demo = [{"title": "PowerShell + credential dumping",
                 "text": "The attackers used PowerShell to download additional tools, then dumped credentials from LSASS memory."}]
        path = ROOT / "data" / "processed" / "external_test.csv"
        with open(path, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f)
                    if r["source_dataset"] == "cisa" and r["eval_clean"] == "yes" and 18 <= int(r["word_count"]) <= 45]
        for r in random.Random(2026).sample(rows, 6):
            demo.append({"title": f"CISA advisory {r['document_id'].split(':')[-1]}", "text": r["text"],
                         "reference_labels": r["technique_ids"]})
        return demo

    def technique(self, tid):
        t = self.techniques.get(tid, {})
        return {"technique_id": tid, "name": t.get("full_name") or t.get("name", ""),
                "tactics": [x.replace("-", " ").title().replace(" And ", " and ")
                            for x in t.get("tactics", "").split(";") if x],
                "description": t.get("description", ""), "url": t.get("url", "")}

    @staticmethod
    def summary(description):
        first = re.split(r"(?<=[.!?])\s", description.strip(), maxsplit=1)[0]
        return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first)

    # --- API ---------------------------------------------------------------------------
    def health(self):
        cpu = Path("/proc/cpuinfo").read_text() if Path("/proc/cpuinfo").exists() else ""
        features = next((l for l in cpu.splitlines() if l.startswith("features")), "")
        def ver(p):
            try:
                return metadata.version(p)
            except metadata.PackageNotFoundError:
                return None
        return {"status": "ok", "platform": platform.machine(), "python": platform.python_version(),
                "cpus": os.cpu_count(), "nnpa": "nnpa" in features.split(),
                "model": self.model_path.name, "labels": len(self.model.labels_),
                "model_load_seconds": self.load_seconds, "model_meta": self.model_meta,
                "granite": {"available": self.granite.available, "file": self.granite.path.name,
                            "loaded": self.granite._llm is not None},
                "libraries": {p: ver(p) for p in ("scikit-learn", "numpy", "llama_cpp_python", "ibm-zdnn-plugin")}}

    def analyze(self, body):
        text = str(body.get("text", "")).strip()
        if not text:
            raise ValueError("Paste a sentence or short passage first.")
        if len(text) > 20_000:
            raise ValueError("Passage too long: keep it under 20,000 characters.")
        masked, counts = redact(text)
        t0 = time.perf_counter()
        sentences, top, alts = self.explainer.suggest(masked, k=3)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        threshold = self.model.threshold
        suggestions = []
        for rank, s in enumerate(top, start=1):
            info = self.technique(s["technique_id"])
            suggestions.append({**info, "rank": rank, "score": s["score"],
                                "confidence": "high" if s["score"] >= 0.6 else "medium" if s["score"] >= threshold else "low",
                                "summary": self.summary(info["description"]),
                                "evidence": s["evidence"], "evidence_terms": s["evidence_terms"],
                                "sentence_index": s["sentence_index"]})
        alternatives = [{**self.technique(a["technique_id"]), "score": a["score"]} for a in alts]
        return {"passage_redacted": masked, "redactions": counts, "sentences": sentences,
                "suggestions": suggestions, "alternatives": alternatives,
                "latency_ms": ms, "threshold": threshold, "platform": platform.machine()}

    def explain(self, body):
        if not self.granite.available:
            raise ValueError("Granite model file not found on this server.")
        tid = str(body.get("technique_id", ""))
        if tid not in self.techniques:
            raise ValueError("Unknown technique.")
        evidence, _ = redact(str(body.get("evidence", ""))[:1000])
        info = self.technique(tid)
        return self.granite.explain(evidence, tid, info["name"], self.summary(info["description"]))

    def search(self, q):
        q = q.strip().lower()
        hits = [self.technique(t) for t, r in self.techniques.items()
                if not q or q in t.lower() or q in (r.get("full_name") or "").lower()]
        return hits[:25]

    def save_review(self, body):
        decisions = body.get("decisions") or []
        if not decisions:
            raise ValueError("Nothing to save: review at least one suggestion.")
        passage, _ = redact(str(body.get("passage", ""))[:20_000])   # never store unmasked text
        clean = []
        for d in decisions[:20]:
            tid = str(d.get("technique_id", ""))
            corrected = str(d.get("corrected_to") or "")
            clean.append({
                "technique_id": tid, "technique_name": self.technique(tid)["name"],
                "decision": str(d.get("decision", "pending"))[:20],
                "corrected_to": corrected if corrected in self.techniques else "",
                "corrected_name": self.technique(corrected)["name"] if corrected in self.techniques else "",
                "model_score": d.get("score"), "model_rank": d.get("rank"),
                "evidence": redact(str(d.get("evidence", ""))[:2000])[0],
                "note": redact(str(d.get("note", ""))[:2000])[0]})
        review = {"review_id": uuid.uuid4().hex[:10], "saved_utc": now(),
                  "analyst": re.sub(r"[^\w .-]", "", str(body.get("analyst", "Analyst")))[:40] or "Analyst",
                  "passage_redacted": passage, "decisions": clean}
        (REVIEWS / f"review_{review['review_id']}.json").write_text(json.dumps(review, indent=2))
        return review

    def reviews(self):
        out = []
        for p in sorted(REVIEWS.glob("review_*.json"), reverse=True):
            try:
                out.append(json.loads(p.read_text()))
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda r: r["saved_utc"], reverse=True)

    def export_csv(self):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
        w.writeheader()
        for r in self.reviews():
            for d in r["decisions"]:
                w.writerow({"review_id": r["review_id"], "saved_utc": r["saved_utc"], "analyst": r["analyst"],
                            "passage_redacted": r["passage_redacted"], **d})
        return buf.getvalue()

    def evaluation(self):
        m = ROOT / "outputs" / "metrics" / "baseline_metrics.json"
        data = json.loads(m.read_text()) if m.exists() else {}
        ex = ROOT / "outputs" / "metrics" / "baseline_examples.csv"
        examples = []
        if ex.exists():
            with open(ex, encoding="utf-8", newline="") as f:
                rows = [r for r in csv.DictReader(f) if r["eval_clean"] == "yes" and len(r["text"]) < 220]
            rng = random.Random(7)
            for flag in ("True", "False"):
                for r in rng.sample([r for r in rows if r["hit_in_top3"] == flag], 4):
                    examples.append({"hit": flag == "True", "text": r["text"], "gold": r["gold"],
                                     "gold_names": r["gold_names"], "top3": r["top3"].split(";"),
                                     "names": [self.technique(t)["name"] for t in r["top3"].split(";")]})
        stats = ROOT / "data" / "processed" / "stats.json"
        return {"metrics": data, "examples": examples,
                "corpus": json.loads(stats.read_text()) if stats.exists() else {}}


class Handler(BaseHTTPRequestHandler):
    server_version = "ThreatLens/1.0"
    app: App = None

    def address_string(self):
        return "ssh-tunnel"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{now()} {fmt % args}\n")

    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else (
            json.dumps(body).encode() if ctype == "application/json" else body.encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _static(self, base, rel):
        path = (base / rel).resolve()
        if not str(path).startswith(str(base.resolve())) or not path.is_file():
            return self._send(404, {"error": "not found"})
        self._send(200, path.read_bytes(), MIME.get(path.suffix, "application/octet-stream"))

    def do_GET(self):
        url = urlparse(self.path)
        p, q = url.path, parse_qs(url.query)
        try:
            if p == "/api/health":
                return self._send(200, self.app.health())
            if p == "/api/samples":
                return self._send(200, self.app.samples)
            if p == "/api/techniques":
                return self._send(200, self.app.search(q.get("q", [""])[0]))
            if p == "/api/reviews":
                return self._send(200, self.app.reviews())
            if p == "/api/evaluation":
                return self._send(200, self.app.evaluation())
            if p == "/api/export":
                fmt = q.get("format", ["csv"])[0]
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
                if fmt == "json":
                    return self._send(200, json.dumps(self.app.reviews(), indent=2), "application/json",
                                      {"Content-Disposition": f'attachment; filename="threatlens_reviews_{stamp}.json"'})
                return self._send(200, self.app.export_csv(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="threatlens_reviews_{stamp}.csv"'})
            if p.startswith("/design/"):
                return self._static(DESIGN, p[len("/design/"):])
            if p in ("/", "/index.html"):
                return self._static(STATIC, "index.html")
            return self._static(STATIC, p.lstrip("/"))
        except Exception as e:  # noqa: BLE001
            self.log_message("error %s", e)
            return self._send(500, {"error": "server error"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(413, {"error": "request too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"error": "invalid JSON"})
        routes = {"/api/analyze": self.app.analyze, "/api/explain": self.app.explain,
                  "/api/reviews": self.app.save_review}
        fn = routes.get(urlparse(self.path).path)
        if fn is None:
            return self._send(404, {"error": "not found"})
        try:
            return self._send(200, fn(body))
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self.log_message("error %s", e)
            return self._send(500, {"error": "server error"})


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default=str(ROOT / "run" / "threatlens.sock"))
    args = ap.parse_args()
    sock = Path(args.socket)
    sock.parent.mkdir(exist_ok=True)
    if sock.exists():
        sock.unlink()
    Handler.app = App()
    server = Server(str(sock), Handler)
    os.chmod(sock, 0o666)        # the SSH daemon (host user) must be able to connect
    (sock.parent / "server.pid").write_text(str(os.getpid()))
    print(f"{now()} ThreatLens ready on {sock} (model {Handler.app.model_path.name}, "
          f"loaded in {Handler.app.load_seconds}s, {platform.machine()})", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        sock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
