"""Shared helpers for the hat VLM evals: the clip registry, frame extraction, and Gemini calls.

Python stdlib + ffmpeg only.
"""
import base64
import http.client
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"


class ApiError(Exception):
    pass


class QuotaExhausted(ApiError):
    """A daily quota is used up: retrying today won't help, so runs stop instead."""


def _quota_message(model, msg):
    limit = re.search(r"limit: (\d+)", msg)
    wait = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", msg)
    resets = ""
    if wait:
        mins = int(wait.group(1) or 0) * 60 + int(wait.group(2) or 0) + float(wait.group(3)) / 60
        resets = " It resets in about %dh%02dm." % (mins // 60, mins % 60)
    tier = " on the free tier" if "free_tier" in msg.lower() or "free tier" in msg.lower() else ""
    return ("The daily request quota for %s is used up%s (limit %s per day).%s Enable billing on the key's "
            "Google AI Studio project, or try another model." % (model, tier, limit.group(1) if limit else "?", resets))


def clip_config(clip):
    """The clip's entry in eval/clips.json with paths made absolute; falls back to data/<clip>.mp4."""
    reg = {}
    path = os.path.join(HERE, "clips.json")
    if os.path.exists(path):
        with open(path) as f:
            reg = json.load(f)
    c = dict(reg.get(clip, {}))
    if "video" not in c:
        for cand in ("data/%s.mp4" % clip, "%s.mp4" % clip):
            if os.path.exists(os.path.join(ROOT, cand)):
                c["video"] = cand
                break
    for k in ("video", "humans", "rubric"):
        if c.get(k):
            c[k] = os.path.join(ROOT, c[k])
    return c


def rel(path):
    return os.path.relpath(path, ROOT)


def load_key():
    for k in ("GEMINI_KEY", "GEMINI_API_KEY"):
        if os.environ.get(k):
            return os.environ[k]
    p = os.path.join(ROOT, ".env.local")
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                k, _, v = line.partition("=")
                if k.strip() in ("GEMINI_KEY", "GEMINI_API_KEY") and v.strip():
                    return v.strip().strip("'\"")
    sys.exit("No Gemini key: set GEMINI_KEY, or add `GEMINI_KEY=...` to .env.local")


def probe(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height:format=duration", "-of", "json", path])
    d = json.loads(out)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"fps": float(num) / float(den), "duration": float(d["format"]["duration"]),
            "width": st["width"], "height": st["height"]}


def crop_filter(info, eye):
    """ffmpeg crop for one eye of a side-by-side stereo frame (hat: 3840x1080); '' for mono or both."""
    w, h = info["width"], info["height"]
    if w < 3 * h or eye == "both":
        return ""
    return "crop=%d:%d:%d:0" % (w // 2, h, 0 if eye == "left" else w // 2)


def extract_frame(video, info, t, eye, out_path):
    """The first frame at or after t seconds, one eye, as JPEG (cached)."""
    if not os.path.exists(out_path):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        vf = crop_filter(info, eye)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % t, "-i", video, "-frames:v", "1"]
                       + (["-vf", vf] if vf else []) + ["-q:v", "2", out_path], check=True)
    return out_path


def image_part(path):
    with open(path, "rb") as f:
        return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f.read()).decode()}}


def text_part(s):
    return {"text": s}


def gemini(key, model, parts, schema=None, media_resolution=None, thinking=None, retries=6, timeout=240):
    """One generateContent call. Returns (answer_text, meta). Retries 429/5xx/network errors."""
    gen = {}
    if schema:
        gen["responseMimeType"] = "application/json"
        gen["responseSchema"] = schema
    if media_resolution:
        gen["mediaResolution"] = "MEDIA_RESOLUTION_" + media_resolution.upper()
    if thinking:
        gen["thinkingConfig"] = ({"thinkingBudget": int(thinking)} if thinking.lstrip("-").isdigit()
                                 else {"thinkingLevel": thinking})
    body = json.dumps({"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}).encode()
    delay = 2.0
    for attempt in range(retries + 1):
        req = urllib.request.Request(API % model, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": key})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:2000]
            if e.code == 429 and re.search(r"per ?day", msg, re.I):
                raise QuotaExhausted(_quota_message(model, msg))
            if e.code in (408, 429, 500, 502, 503, 504) and attempt < retries:
                hint = re.search(r"retry in ([\d.]+)s", msg)  # per-minute limits say how long to wait
                time.sleep(min(float(hint.group(1)), 90) + random.random() if hint else delay + random.random())
                delay = min(delay * 2, 60)
                continue
            raise ApiError("HTTP %d: %s" % (e.code, msg[:600]))
        except (urllib.error.URLError, socket.timeout, OSError, http.client.HTTPException) as e:
            # socket.timeout (a read timeout) isn't TimeoutError on Python 3.9, and isn't wrapped in URLError
            if attempt < retries:
                time.sleep(delay + random.random())
                delay = min(delay * 2, 60)
                continue
            raise ApiError("network: %s" % e)
    usage = resp.get("usageMetadata") or {}
    meta = {"latency_s": round(time.time() - t0, 2), "model_version": resp.get("modelVersion"),
            "usage": {k: usage.get(k) for k in ("promptTokenCount", "candidatesTokenCount",
                                                "thoughtsTokenCount", "totalTokenCount")}}
    cands = resp.get("candidates") or []
    if not cands:
        raise ApiError("no answer; promptFeedback=%s" % json.dumps(resp.get("promptFeedback"))[:300])
    meta["finish_reason"] = cands[0].get("finishReason")
    text = "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts", [])
                   if not p.get("thought"))
    return text, meta


def gemini_json(key, model, parts, schema, **kw):
    text, meta = gemini(key, model, parts, schema=schema, **kw)
    try:
        return json.loads(text), meta
    except ValueError:
        raise ApiError("unparseable answer (finish_reason=%s): %r" % (meta.get("finish_reason"), text[:300]))


def add_usage(total, usage):
    for k, v in (usage or {}).items():
        total[k] = total.get(k, 0) + (v or 0)
    return total


def fmt(t):
    m = int(t // 60)
    return "%d:%05.2f" % (m, t - 60 * m)
