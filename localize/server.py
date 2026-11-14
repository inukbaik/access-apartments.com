"""HTTP localization service for the glasses app and the phone test page. Standard library only.

    python -m localize.server --token <secret>              # listens on 0.0.0.0:8765
    python -m localize.server --token <secret> --save-frames  # also keep every frame in data/frames/

Endpoints (every call needs ?token=<secret> when the server has a token):
    GET  /                                  phone test page (camera -> /localize -> speech)
    POST /localize?session=<id>[&floor=Floor%203]
                                            body: one JPEG/PNG (Content-Type image/jpeg) -> JSON
    POST /reset?session=<id>                forget that session's frames            -> {"ok": true}
    GET  /view/<pano_id>/<heading>.jpg      the reference view a result points at
    GET  /health                            index info

Result JSON: see localize/README.md. "status" is "ok" or "unknown"; on "unknown" never tell the
user a position as fact.
"""
import argparse
import hmac
import io
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

from localize.index import CACHE, DEFAULT_EMBED, DEFAULT_MODEL, lt, load_or_build
from localize.locator import Locator

MAX_BODY = 15 * 1024 * 1024
PAGE = Path(__file__).parent / "static" / "index.html"
FRAMES_DIR = Path("data/frames")


def reference_view(model_id, pano_id, heading):
    """Rebuild one of the 8 horizon views from the cached skybox faces, as JPEG bytes."""
    faces = [CACHE / "skybox" / f"{model_id}_scan_{pano_id}_f{i}.jpg" for i in range(1, 5)]
    if not all(f.exists() for f in faces):
        return None
    for h, img in lt.horizon_views([Image.open(f).convert("RGB") for f in faces]):
        if h == heading:
            img.thumbnail((448, 448))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            return buf.getvalue()
    return None


def make_handler(loc, lock, token, save_frames):
    model_id = loc.index.meta["model_id"]

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj, ctype="application/json"):
            body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _parse(self):
            url = urlparse(self.path)
            qs = {k: v[0] for k, v in parse_qs(url.query).items()}
            if token and not hmac.compare_digest(qs.get("token", ""), token):
                self._send(401, {"error": "missing or wrong ?token="})
                return None, None
            return url.path, qs

        def do_GET(self):
            path, qs = self._parse()
            if path is None:
                return
            if path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if path == "/health":
                m = loc.index.meta
                return self._send(200, {"ok": True, "model": m["model_id"], "name": m["name"],
                                        "scan_positions": len(loc.index.panos),
                                        "embed_model": m["embed_model"]})
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "view" and parts[2].endswith(".jpg"):
                pano_id, heading = parts[1], parts[2][:-4]
                if pano_id in loc.index.by_id and heading.isdigit():
                    jpg = reference_view(model_id, pano_id, int(heading))
                    if jpg:
                        return self._send(200, jpg, "image/jpeg")
            self._send(404, {"error": "not found"})

        def do_POST(self):
            path, qs = self._parse()
            if path is None:
                return
            session = qs.get("session", "default")
            if path == "/reset":
                with lock:
                    loc.reset(session)
                return self._send(200, {"ok": True})
            if path != "/localize":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= MAX_BODY:
                return self._send(400, {"error": f"send one image as the request body (got {n} bytes)"})
            raw = self.rfile.read(n)
            try:
                img = Image.open(io.BytesIO(raw))
                img.load()
            except Exception as e:
                return self._send(400, {"error": f"could not read image: {e}"})
            t0 = time.time()
            try:
                with lock:  # one model, one frame at a time
                    result = loc.locate(img, session=session, floor=qs.get("floor"))
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            result["latency_ms"] = int((time.time() - t0) * 1000)
            if save_frames:  # for calibrating the "unknown" rules later; data/ is git-ignored
                d = FRAMES_DIR / "".join(c for c in session if c.isalnum() or c in "-_")
                d.mkdir(parents=True, exist_ok=True)
                stem = f"{time.time():.1f}_{result['status']}_{result['best_guess']['label']}"
                (d / f"{stem}.jpg").write_bytes(raw)
                (d / f"{stem}.json").write_text(json.dumps(result))
            self._send(200, result)

        def log_message(self, fmt, *args):
            print(f"{self.address_string()} {fmt % args}".replace(token or "\0", "***"))

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
    ap.add_argument("--token", default=os.environ.get("LOCALIZE_TOKEN"),
                    help="shared secret required as ?token= (or set LOCALIZE_TOKEN)")
    ap.add_argument("--save-frames", action="store_true", help="keep every frame + result in data/frames/")
    a = ap.parse_args()
    if not a.token:
        print("WARNING: no --token set; anyone who can reach this port can use the service.")

    embedder = lt.Embedder(a.embed_model)
    loc = Locator(load_or_build(a.model, a.embed_model, embedder=embedder), embedder)
    server = ThreadingHTTPServer((a.host, a.port), make_handler(loc, threading.Lock(), a.token, a.save_frames))
    print(f"Localization service on http://{lan_ip()}:{a.port}/?token=...  (local network)")
    print(f"Public HTTPS for the phone:  cloudflared tunnel --url http://localhost:{a.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
