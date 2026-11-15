"""Demo web page for the finder. Standard library only. Run from the repo root:

    .venv/bin/python -m finder.web                 # http://localhost:8800
    .venv/bin/python -m finder.web --no-llm        # measurement-based results only (no Ollama)

Endpoints:
    GET  /                          the page (finder/static/index.html)
    POST /api/search                {"request", "lat", "lon", "radius_km", "limit", "use_llm"} -> {"job"}
    GET  /api/job/<id>              {"status": running|done|error, "log": [...], "result": trace}
    GET  /api/evidence/<sid>        floor plans + door photos for one listing (built on first request)
    GET  /evidence/<sid>/<file>     an evidence image
"""
import argparse
import contextlib
import io
import json
import os
import re
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from finder import evidence
from finder.agent import answer
from finder.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, OpenAICompatBackend

PAGE = Path(__file__).parent / "static" / "index.html"
JOBS_DIR = "out/web"
SID_RE = re.compile(r"^[A-Za-z0-9]{6,20}$")
FILE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(png|jpg)$")
TYPES = {".png": "image/png", ".jpg": "image/jpeg"}

PRESETS = [  # demo areas with many scanned listings (from data/models_index.csv)
    {"name": "Los Angeles: USC / W 36th St", "lat": 34.0242, "lon": -118.2991},
    {"name": "Los Angeles: Koreatown", "lat": 34.0636, "lon": -118.2999},
    {"name": "Los Angeles: Hollywood", "lat": 34.1000, "lon": -118.3500},
    {"name": "Houston: Aldine (homes listed as wheelchair accessible)", "lat": 29.8500, "lon": -95.3700},
    {"name": "Houston: Midtown", "lat": 29.7400, "lon": -95.3800},
    {"name": "Houston: Galleria", "lat": 29.7400, "lon": -95.4400},
]


class Job:
    def __init__(self):
        self.id = uuid.uuid4().hex[:10]
        self.status = "running"
        self.log = []
        self.result = None
        self.error = None
        self.started = time.time()


class _Tee(io.TextIOBase):
    """Collects printed lines into the job log (answer() prints its table)."""

    def __init__(self, job):
        self.job, self.buf = job, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.job.log.append(line)
        return len(s)


class App:
    def __init__(self, llm_default, base_url, model, api_key, call_timeout):
        self.jobs = {}
        self.run_lock = threading.Lock()  # one search at a time (stdout capture, shared caches)
        self.evidence_lock = threading.Lock()
        self.llm_default = llm_default
        self.base_url, self.model, self.api_key, self.call_timeout = base_url, model, api_key, call_timeout

    def start(self, req):
        job = Job()
        self.jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, req), daemon=True).start()
        return job

    def _run(self, job, req):
        out_dir = os.path.join(JOBS_DIR, job.id)
        use_llm = bool(req.get("use_llm", self.llm_default))
        backend = (OpenAICompatBackend(self.base_url, self.model, self.api_key, self.call_timeout)
                   if use_llm else None)
        with self.run_lock:
            try:
                with contextlib.redirect_stdout(_Tee(job)):
                    answer(str(req["request"])[:500], float(req["lat"]), float(req["lon"]),
                           float(req.get("radius_km", 1.5)), int(req.get("limit", 10)), backend,
                           out_dir=out_dir, log=job.log.append)
                with open(os.path.join(out_dir, "agent_trace.json")) as f:
                    job.result = json.load(f)
                job.status = "done"
            except Exception as e:  # show the error on the page; never hang the job
                job.error = f"{type(e).__name__}: {e}"
                job.log.append(traceback.format_exc(limit=3))
                job.status = "error"

    def evidence(self, sid):
        path = os.path.join(evidence.OUT, sid, "evidence.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        with self.evidence_lock:
            return evidence.build(sid)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store" if ctype == "application/json" else "max-age=3600")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            parts = path.strip("/").split("/")
            if path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if path in ("/tokens.css", "/base.css"):
                return self._send(200, (PAGE.parent / path[1:]).read_bytes(), "text/css; charset=utf-8")
            if len(parts) == 3 and parts[:2] == ["api", "thumb"] and SID_RE.match(parts[2]):
                try:
                    with open(evidence.thumbnail(parts[2]), "rb") as f:
                        return self._send(200, f.read(), "image/jpeg")
                except Exception as e:
                    return self._send(502, {"error": f"{type(e).__name__}: {e}"})
            if path == "/api/config":
                return self._send(200, {"presets": PRESETS, "llm_default": app.llm_default, "model": app.model})
            if len(parts) == 3 and parts[:2] == ["api", "job"]:
                job = app.jobs.get(parts[2])
                if not job:
                    return self._send(404, {"error": "no such job"})
                return self._send(200, {"status": job.status, "log": job.log, "result": job.result,
                                        "error": job.error, "elapsed_s": round(time.time() - job.started, 1)})
            if len(parts) == 3 and parts[:2] == ["api", "evidence"] and SID_RE.match(parts[2]):
                try:
                    return self._send(200, app.evidence(parts[2]))
                except Exception as e:
                    return self._send(502, {"error": f"{type(e).__name__}: {e}"})
            if len(parts) == 3 and parts[0] == "evidence" and SID_RE.match(parts[1]) and FILE_RE.match(parts[2]):
                f = Path(evidence.OUT) / parts[1] / parts[2]
                if f.exists():
                    return self._send(200, f.read_bytes(), TYPES[f.suffix])
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/search":
                return self._send(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(min(n, 10000)) or b"{}")
                float(req["lat"]), float(req["lon"]), str(req["request"])
            except (ValueError, KeyError, TypeError) as e:
                return self._send(400, {"error": f"bad request: {e}"})
            self._send(200, {"job": app.start(req).id})

        def log_message(self, fmt, *args):
            if "/api/job/" not in self.path:  # polling is noisy
                print(f"{self.address_string()} {fmt % args}")

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--no-llm", action="store_true", help="default to measurement-based results (no agent)")
    ap.add_argument("--base-url", default=os.environ.get("FINDER_LLM_BASE_URL") or DEFAULT_BASE_URL)
    ap.add_argument("--model", default=os.environ.get("FINDER_LLM_MODEL") or DEFAULT_MODEL)
    ap.add_argument("--api-key-env", default="FINDER_LLM_API_KEY")
    ap.add_argument("--call-timeout", type=float, default=45)
    a = ap.parse_args()
    app = App(not a.no_llm, a.base_url, a.model, os.environ.get(a.api_key_env, ""), a.call_timeout)
    server = ThreadingHTTPServer((a.host, a.port), make_handler(app))
    print(f"Finder demo on http://{a.host}:{a.port}/  (agent: {'off' if a.no_llm else a.model + ' at ' + a.base_url})")
    server.serve_forever()


if __name__ == "__main__":
    main()
