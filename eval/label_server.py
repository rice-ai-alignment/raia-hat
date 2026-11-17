#!/usr/bin/env python3
"""Local labeling tool for hat clips.

Serves label.html and the original hat clip (with HTTP Range, so seeking works; the hat's HEVC has
a keyframe every 4 frames and plays natively in Chrome/Safari on macOS), and saves the labels to
eval/labels/<clip>.json on every change. Listens on 127.0.0.1 only.

  python3 eval/label_server.py test-1        # plays the clip from eval/clips.json; open http://127.0.0.1:8765

Label times are seconds on the clip's own timeline.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import common  # noqa: E402
CLIP_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def probe(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height:format=duration", "-of", "json", path])
    d = json.loads(out)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"fps": round(float(num) / float(den), 3), "duration": float(d["format"]["duration"]),
            "width": st["width"], "height": st["height"],
            # hat clips are 3840x1080: left and right eye side by side
            "side_by_side": st["width"] >= 3 * st["height"]}


def make_handler(cfg, labels_path):
    html_path = os.path.join(HERE, "label.html")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet: only log label saves and errors
            pass

        def _json(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                with open(html_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/config":
                self._json({k: v for k, v in cfg.items() if not k.startswith("_")})
            elif path == "/api/labels":
                if os.path.exists(labels_path):
                    with open(labels_path) as f:
                        self._json(json.load(f))
                else:
                    self._json({})
            elif path == "/video":
                self._send_video(cfg["_video_path"])
            else:
                self.send_error(404)

        def do_PUT(self):
            if self.path.split("?", 1)[0] != "/api/labels":
                return self.send_error(404)
            try:
                n = int(self.headers.get("Content-Length", "0"))
                doc = json.loads(self.rfile.read(n))
                ivs = doc.get("intervals")
                if not isinstance(ivs, list):
                    raise ValueError("intervals must be a list")
                clean = []
                for iv in ivs:
                    kind = iv.get("kind")
                    if kind not in ("person", "unsure"):
                        raise ValueError("bad kind %r" % kind)
                    s, e = float(iv["start"]), float(iv["end"])
                    if e < s:
                        s, e = e, s
                    count = iv.get("count")
                    clean.append({
                        "kind": kind, "start": round(s, 4), "end": round(e, 4),
                        "count": int(count) if count not in (None, "") else None,
                        "note": str(iv.get("note") or ""),
                    })
                clean.sort(key=lambda iv: (iv["start"], iv["end"]))
            except (ValueError, KeyError, TypeError) as ex:
                return self._json({"error": str(ex)}, 400)
            out = {
                "clip": cfg["clip"], "source": cfg["source"],
                "fps": cfg["fps"], "duration": cfg["duration"],
                "complete": bool(doc.get("complete")),
                "definition": cfg["definition"],
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "intervals": clean,
            }
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(labels_path), suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(out, f, indent=2)
                f.write("\n")
            os.replace(tmp, labels_path)
            print("saved %d interval(s)%s -> %s" % (
                len(clean), " [complete]" if out["complete"] else "", os.path.relpath(labels_path)), flush=True)
            self._json({"ok": True, "updated_at": out["updated_at"]})

        do_POST = do_PUT  # navigator.sendBeacon (flush on tab close) can only POST

        def _send_video(self, path):
            size = os.path.getsize(path)
            start, end, status = 0, size - 1, 200
            rng = self.headers.get("Range")
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
                if m and (m.group(1) or m.group(2)):
                    if m.group(1) == "":
                        start = max(0, size - int(m.group(2)))
                    else:
                        start = int(m.group(1))
                        if m.group(2):
                            end = min(int(m.group(2)), size - 1)
                    if start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % size)
                        self.end_headers()
                        return
                    status = 206
            self.send_response(status)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if status == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    left -= len(chunk)

    return Handler


DEFINITION = (
    "person: any real person other than the wearer, or any visible part of one, even small, distant, "
    "partly hidden, blurry or behind glass. Not the wearer's own hands/arms/legs/feet. "
    "unsure: too tiny/blurry to tell, or people only in posters/photos/screens/statues/reflections "
    "(unsure time is excluded from scoring)."
)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", help="clip name, e.g. test-1")
    ap.add_argument("--video", help="clip to label (default: the clip's video in eval/clips.json)")
    ap.add_argument("--eye", default="right", choices=["left", "right", "both"],
                    help="eye shown first (switch in the page); right is the default since the left lens is smudged")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    if not CLIP_RE.match(a.clip):
        sys.exit("bad clip name")
    video = os.path.abspath(a.video or common.clip_config(a.clip).get("video") or os.path.join(ROOT, a.clip + ".mp4"))
    if not os.path.isfile(video):
        sys.exit("video not found: %s" % video)
    os.makedirs(os.path.join(HERE, "labels"), exist_ok=True)
    labels_path = os.path.join(HERE, "labels", a.clip + ".json")
    cfg = dict(probe(video), clip=a.clip, eye=a.eye, source=os.path.relpath(video, ROOT),
               definition=DEFINITION, _video_path=video)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(cfg, labels_path))
    print("Labeling %s (%s, %.1fs @ %g fps). Open http://127.0.0.1:%d  (Ctrl-C to stop)" % (
        a.clip, cfg["source"], cfg["duration"], cfg["fps"], a.port), flush=True)
    print("Labels save to %s" % os.path.relpath(labels_path), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
