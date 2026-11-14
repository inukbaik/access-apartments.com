"""HTTP localization service for the glasses app. Standard library only.

    python -m localize.server                 # listens on 0.0.0.0:8765

Endpoints (one session per phone; the session keeps the last few frames for voting):
    POST /localize?session=<id>[&floor=Floor%203]
                                  body: one JPEG/PNG (Content-Type image/jpeg)  -> JSON result
    POST /reset?session=<id>      forget that session's frames                  -> {"ok": true}
    GET  /health                                                                -> index info

Result JSON: see localize/README.md. "status" is "ok" or "unknown"; on "unknown" never tell the
user a position as fact.
"""
import argparse
import io
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image

from localize.index import DEFAULT_EMBED, DEFAULT_MODEL, lt, load_or_build
from localize.locator import Locator

MAX_BODY = 15 * 1024 * 1024


def make_handler(loc, lock):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path == "/health":
                m = loc.index.meta
                return self._send(200, {"ok": True, "model": m["model_id"], "name": m["name"],
                                        "scan_positions": len(loc.index.panos),
                                        "embed_model": m["embed_model"]})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            session = qs.get("session", ["default"])[0]
            floor = qs.get("floor", [None])[0]
            if url.path == "/reset":
                with lock:
                    loc.reset(session)
                return self._send(200, {"ok": True})
            if url.path != "/localize":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= MAX_BODY:
                return self._send(400, {"error": f"send one image as the request body (got {n} bytes)"})
            try:
                img = Image.open(io.BytesIO(self.rfile.read(n)))
                img.load()
            except Exception as e:
                return self._send(400, {"error": f"could not read image: {e}"})
            t0 = time.time()
            try:
                with lock:  # one model, one frame at a time
                    result = loc.locate(img, session=session, floor=floor)
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            result["latency_ms"] = int((time.time() - t0) * 1000)
            self._send(200, result)

        def log_message(self, fmt, *args):
            print(f"{self.address_string()} {fmt % args}")

    return Handler


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--embed-model", default=DEFAULT_EMBED)
    a = ap.parse_args()

    embedder = lt.Embedder(a.embed_model)
    loc = Locator(load_or_build(a.model, a.embed_model, embedder=embedder), embedder)
    server = ThreadingHTTPServer((a.host, a.port), make_handler(loc, threading.Lock()))
    print(f"Localization service on http://{lan_ip()}:{a.port}  (POST /localize, GET /health)")
    server.serve_forever()


if __name__ == "__main__":
    main()
