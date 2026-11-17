#!/usr/bin/env python3
"""Does a VLM see the people? Score a Gemini model against the human labels for a hat clip.

Samples frames from one eye of the clip, asks the model about each frame on its own ("is anyone
visible, and how many?"), and scores the answers against the clip's people labels: the CSV listed in
eval/clips.json (one row per person: appears_s, leaves_s, notes), or eval/labels/<clip>.json from
label_server.py. Frames are extracted once and shared across models; answers are cached in
results.jsonl, so an interrupted run resumes where it stopped.

  python3 eval/vlm_eval.py test-1                              # full run: 300 frames, 20 per request
  python3 eval/vlm_eval.py test-1 --model gemini-2.5-flash     # another model on the same frames
  python3 eval/vlm_eval.py test-1 --batch 1                    # one frame per request (needs a paid key)
  python3 eval/vlm_eval.py test-1 --score-only                 # re-score after editing labels (no API calls)

Batching: the free Gemini tier allows 20 requests per model per day, so by default each request carries
20 frames. Frames in one request come from across the whole clip (~15 s apart), so the model can't
follow a person from one frame to the next; it's still told to judge each frame on its own.

Ground truth for a sampled frame at time t
  present    someone is in view: appears_s <= t < leaves_s for at least one person.
  not scored t falls in a gap the notes mark (e.g. "hidden behind pillar ~84-85s"), only people whose
             notes say "intermittent" are in view, it is within 2 s of an appear time the notes call
             "approximate", or presence changes within --edge seconds of t (labels are +/-0.25 s).
  count      number of people in view; scored only on frames with people where it is certain.

Needs ffmpeg and GEMINI_KEY (or GEMINI_API_KEY) in the environment or in .env.local.
"""
import argparse
import concurrent.futures as cf
import csv
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from common import ApiError, QuotaExhausted, fmt, rel  # noqa: E402

DEFAULT_MODEL = "gemini-3-flash-preview"
APPROX_EDGE = 2.0  # seconds of slack around appear times the labels call approximate

PROMPT = """This image is one frame from a camera worn on the head (a first-person view).

Is at least one person visible in this frame?
- Count any real person, or any visible part of one (head, torso, legs, an arm), even if they are small, far away, partly hidden, blurry, or seen through glass.
- Do not count the camera wearer's own body: their hands, arms, legs or feet near the bottom edge of the frame.
- Do not count people who appear only in posters, photos, screens, statues or mirror reflections.

Answer in JSON."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "person_visible": {"type": "BOOLEAN"},
        "num_people": {"type": "INTEGER", "description": "number of distinct people visible; 0 if none"},
        "where": {"type": "STRING", "description": "briefly, where the people are in the frame; empty if none"},
    },
    "required": ["person_visible", "num_people", "where"],
    "propertyOrdering": ["person_visible", "num_people", "where"],
}


# ---------------------------------------------------------------- ground truth

def load_people(path):
    """People rows: label, start, end, n (people in the row), gaps, soft (intermittent), approx_start."""
    people = []
    if path.endswith(".csv"):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                notes = r.get("notes") or ""
                gaps = [(float(a), float(b)) for a, b in
                        re.findall(r"~\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*s", notes)]
                people.append({
                    "label": r["label"], "desc": r.get("description", ""), "scene": r.get("scene", ""),
                    "start": float(r["appears_s"]), "end": float(r["leaves_s"]), "n": 1, "gaps": gaps,
                    "soft": "intermittent" in notes.lower(), "approx_start": "approximate" in notes.lower(),
                    "notes": notes})
        return people, {"source": rel(path), "complete": True}
    with open(path) as f:
        doc = json.load(f)
    for i, iv in enumerate(doc.get("intervals", [])):
        person = iv["kind"] == "person"
        people.append({
            "label": "%s%d" % (iv["kind"], i + 1), "desc": iv.get("note", ""), "scene": "",
            # labeler intervals include their end frame; make it exclusive like the CSV
            "start": iv["start"], "end": iv["end"] + 1 / 30.0, "n": iv.get("count") if person else None,
            "gaps": [], "soft": not person, "approx_start": False, "notes": iv.get("note", "")})
    return people, {"source": rel(path), "complete": bool(doc.get("complete"))}


def in_view(t, people):
    """(definite, uncertain) people in view at t."""
    definite, unsure = [], []
    for p in people:
        lo = p["start"] - (APPROX_EDGE if p["approx_start"] else 0)
        if not (lo <= t < p["end"]):
            continue
        if p["soft"] or any(a <= t <= b for a, b in p["gaps"]) or \
                (p["approx_start"] and t < p["start"] + APPROX_EDGE):
            unsure.append(p)
        else:
            definite.append(p)
    return definite, unsure


def truth(t, people, edge):
    """(present, count, reason): present is True/False, or None when the frame isn't scored."""
    def at(tt):
        d, u = in_view(tt, people)
        present = True if d else (None if u else False)
        count = None if (u or any(p["n"] is None for p in d)) else sum(p["n"] for p in d)
        return present, count
    present, count = at(t)
    if present is None:
        return None, None, "uncertain"
    if edge:
        around = [at(t - edge), at(t + edge)]
        if any(a[0] != present for a in around):
            return None, None, "edge"
        if any(a[1] != count for a in around):
            count = None
    return present, count, ""


def episodes(people):
    """Merge overlapping people spans into stretches of 'someone is in view'."""
    out = []
    for p in sorted(people, key=lambda p: p["start"]):
        if out and p["start"] <= out[-1]["end"]:
            out[-1]["end"] = max(out[-1]["end"], p["end"])
            out[-1]["people"].append(p["label"])
        else:
            out.append({"start": p["start"], "end": p["end"], "people": [p["label"]]})
    return out


# ---------------------------------------------------------------- frames + model

def extract_frames(video, info, eye, step, outdir):
    """Every `step`-th frame of the chosen eye as JPEG. Cached via frames.json."""
    index = os.path.join(outdir, "frames.json")
    if os.path.exists(index):
        with open(index) as f:
            return json.load(f)["frames"]
    os.makedirs(outdir, exist_ok=True)
    crop = common.crop_filter(info, eye)
    vf = "select=not(mod(n\\,%d))" % step + ("," + crop if crop else "")
    print("Extracting every %d-th frame (%s eye) from %s ..." % (step, eye, rel(video)), flush=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-hwaccel", "videotoolbox", "-i", video, "-vf", vf,
                    "-fps_mode", "vfr", "-q:v", "2", os.path.join(outdir, "f%05d.jpg")], check=True)
    files = sorted(glob.glob(os.path.join(outdir, "f*.jpg")))
    frames = [{"file": os.path.basename(p), "frame": i * step, "t": round(i * step / info["fps"], 4)}
              for i, p in enumerate(files)]
    with open(index, "w") as f:
        json.dump({"source": rel(video), "eye": eye, "step": step, "fps": info["fps"], "frames": frames}, f, indent=1)
    print("  %d frames -> %s" % (len(frames), rel(outdir)), flush=True)
    return frames


BATCH_PROMPT = """These %d images are separate frames from a camera worn on the head (a first-person view), each taken at a different moment. Judge each frame on its own.

For each frame: is at least one person visible?
- Count any real person, or any visible part of one (head, torso, legs, an arm), even if they are small, far away, partly hidden, blurry, or seen through glass.
- Do not count the camera wearer's own body: their hands, arms, legs or feet near the bottom edge of the frame.
- Do not count people who appear only in posters, photos, screens, statues or mirror reflections.

Answer in JSON with one entry per frame, using the frame numbers shown."""

BATCH_SCHEMA = {
    "type": "OBJECT",
    "properties": {"frames": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": dict({"frame": {"type": "INTEGER"}}, **SCHEMA["properties"]),
        "required": ["frame"] + SCHEMA["required"],
        "propertyOrdering": ["frame"] + SCHEMA["propertyOrdering"]}}},
    "required": ["frames"],
}


def ask_batch(key, a, frames_dir, batch):
    """One request for one or more frames. Returns a result row per frame."""
    opts = {"media_resolution": a.media_resolution, "thinking": a.thinking}
    try:
        if len(batch) == 1:
            ans, meta = common.gemini_json(key, a.model, [common.image_part(os.path.join(frames_dir, batch[0]["file"])),
                                                          common.text_part(PROMPT)], SCHEMA, **opts)
            answers = {1: ans}
        else:
            parts = []
            for i, fr in enumerate(batch, 1):
                parts += [common.text_part("Frame %d:" % i), common.image_part(os.path.join(frames_dir, fr["file"]))]
            parts.append(common.text_part(BATCH_PROMPT % len(batch)))
            ans, meta = common.gemini_json(key, a.model, parts, BATCH_SCHEMA, **opts)
            answers = {}
            for x in ans.get("frames", []) if isinstance(ans, dict) else []:
                if isinstance(x, dict) and isinstance(x.get("frame"), int):
                    answers.setdefault(x["frame"], x)
    except QuotaExhausted:
        raise
    except ApiError as e:
        return [dict(fr, model=a.model, error=str(e)) for fr in batch]
    rows = []
    for i, fr in enumerate(batch, 1):
        row = dict(fr, model=a.model, batch_size=len(batch), model_version=meta.get("model_version"),
                   finish_reason=meta.get("finish_reason"), latency_s=meta.get("latency_s"),
                   usage=meta.get("usage") if i == 1 else None)  # tokens counted once per request
        x = answers.get(i)
        try:
            row.update(pred=bool(x["person_visible"]), num_people=x.get("num_people"), where=x.get("where") or "")
        except (KeyError, TypeError):
            row["error"] = "no answer for frame %d of %d in the response" % (i, len(batch))
        rows.append(row)
    return rows


def load_results(path):
    rows = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    rows[r["file"]] = r  # last line per frame wins (retries append)
    return rows


def run_model(a, frames, frames_dir, results_path):
    key = common.load_key()
    done = {k for k, r in load_results(results_path).items() if "pred" in r}
    todo = [f for f in frames if f["file"] not in done]
    if a.limit and len(todo) > a.limit:
        stride = len(todo) / float(a.limit)
        todo = [todo[int(i * stride)] for i in range(a.limit)]
    if not todo:
        print("All %d frames already answered by %s." % (len(frames), a.model))
        return
    # Strided batches: each request holds frames from across the whole clip (about len/n_batches seconds
    # apart), so neighbouring moments never share a request and the model can't track people between them.
    n_batches = -(-len(todo) // a.batch)
    batches = [todo[i::n_batches] for i in range(n_batches)]
    print("Asking %s about %d frame(s) in %d request(s) (%d already done, %d parallel) ..." % (
        a.model, len(todo), len(batches), len(done), a.concurrency), flush=True)
    lock, stop = threading.Lock(), threading.Event()
    out = open(results_path, "a")

    def one(batch):
        if stop.is_set():
            return None
        try:
            rows = ask_batch(key, a, frames_dir, batch)
        except QuotaExhausted as e:
            stop.set()
            return {"quota": str(e)}
        with lock:
            for row in rows:
                out.write(json.dumps(row) + "\n")
            out.flush()
        return rows

    first = one(batches[0])  # alone first, so a bad model name or option fails once, not N times
    if isinstance(first, dict):
        out.close()
        sys.exit(first["quota"])
    if all("pred" not in r for r in first):
        out.close()
        sys.exit("First request failed, stopping: %s" % first[0].get("error"))
    n, errors, quota, t0 = len(first), sum("pred" not in r for r in first), None, time.time()
    with cf.ThreadPoolExecutor(max_workers=a.concurrency) as pool:
        for rows in pool.map(one, batches[1:]):
            if rows is None or isinstance(rows, dict):
                quota = quota or (rows or {}).get("quota")
                continue
            n += len(rows)
            errors += sum("pred" not in r for r in rows)
            print("  %d/%d frames  (%d errors, %.0fs)" % (n, len(todo), errors, time.time() - t0), flush=True)
    out.close()
    if quota:
        print("Stopped after %d of %d frames: %s Rerun the same command later to continue." % (n, len(todo), quota))


# ---------------------------------------------------------------- scoring

def ratio(a, b):
    return round(a / float(b), 4) if b else None


def score(a, frames, frames_dir, results_path, run_dir, people, label_info):
    rows = load_results(results_path)
    answered = [dict(fr, **rows[fr["file"]]) for fr in frames if "pred" in rows.get(fr["file"], {})]
    failed = [dict(fr, **rows[fr["file"]]) for fr in frames if fr["file"] in rows and "pred" not in rows[fr["file"]]]
    tp = fp = fn = tn = 0
    skipped = {}
    misses, false_alarms, counts = [], [], []
    for r in answered:
        present, count, why = truth(r["t"], people, a.edge)
        r["gt_present"], r["gt_count"] = present, count
        if present is None:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        if present and r["pred"]:
            tp += 1
        elif present:
            fn += 1
            misses.append(r)
        elif r["pred"]:
            fp += 1
            false_alarms.append(r)
        else:
            tn += 1
        if present and count is not None and r.get("num_people") is not None:
            counts.append((count, int(r["num_people"])))
    prec, rec = ratio(tp, tp + fp), ratio(tp, tp + fn)
    f1 = round(2 * prec * rec / (prec + rec), 4) if (prec and rec) else (0.0 if (tp + fp + fn) else None)

    eps = []
    for ep in episodes(people):
        inside = [r for r in answered if ep["start"] <= r["t"] < ep["end"]]
        eps.append(dict(ep, samples=len(inside), hits=sum(1 for r in inside if r["pred"]),
                        seen=any(r["pred"] for r in inside) if inside else None))
    per_person = []
    for p in people:
        inside = [r for r in answered if p["start"] <= r["t"] < p["end"]]
        alone = [r for r in inside if [q["label"] for q in in_view(r["t"], people)[0]] == [p["label"]]
                 and not in_view(r["t"], people)[1]]
        per_person.append({"label": p["label"], "desc": p["desc"], "start": p["start"], "end": p["end"],
                           "samples": len(inside), "hits": sum(1 for r in inside if r["pred"]),
                           "alone_samples": len(alone), "alone_hits": sum(1 for r in alone if r["pred"]),
                           "flags": ", ".join(x for x, on in (("intermittent", p["soft"]), ("gap", p["gaps"]),
                                                              ("approx. appear", p["approx_start"])) if on)})
    sampled_eps = [e for e in eps if e["seen"] is not None]
    alone_people = [p for p in per_person if p["alone_samples"]]
    usage = {}
    for r in answered:
        common.add_usage(usage, r.get("usage"))
    summary = {
        "clip": a.clip, "model": a.model,
        "model_versions": sorted({r.get("model_version") for r in answered if r.get("model_version")}),
        "eye": a.eye, "every_s": a.every, "frames_per_request": a.batch, "edge_s": a.edge,
        "media_resolution": a.media_resolution,
        "thinking": a.thinking, "labels": label_info,
        "frames": {"total": len(frames), "answered": len(answered), "failed": len(failed),
                   "scored": tp + fp + fn + tn, "not_scored": skipped},
        "presence": {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec, "f1": f1,
                     "accuracy": ratio(tp + tn, tp + fp + fn + tn),
                     "false_alarm_rate": ratio(fp, fp + tn)},
        "count": {"frames": len(counts),
                  "exact": ratio(sum(1 for g, p in counts if g == p), len(counts)),
                  "within_1": ratio(sum(1 for g, p in counts if abs(g - p) <= 1), len(counts)),
                  "mean_abs_error": ratio(sum(abs(g - p) for g, p in counts), len(counts)),
                  "mean_bias": ratio(sum(p - g for g, p in counts), len(counts))},
        "episodes": {"total": len(eps), "sampled": len(sampled_eps),
                     "seen": sum(1 for e in sampled_eps if e["seen"]),
                     "recall": ratio(sum(1 for e in sampled_eps if e["seen"]), len(sampled_eps))},
        "people_seen_when_alone": {"people": len(alone_people),
                                   "seen": sum(1 for p in alone_people if p["alone_hits"])},
        "usage_tokens": usage,
        "mean_latency_s": ratio(sum(r.get("latency_s", 0) for r in answered), len(answered)),
        "prompt": PROMPT if a.batch == 1 else BATCH_PROMPT % a.batch,
    }
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(run_dir, "frames_scored.jsonl"), "w") as f:
        for r in answered:
            f.write(json.dumps({k: r.get(k) for k in ("file", "t", "gt_present", "gt_count", "pred",
                                                      "num_people", "where")}) + "\n")
    write_report(a, run_dir, frames_dir, summary, eps, per_person, misses, false_alarms, failed)
    pr, ct = summary["presence"], summary["count"]
    print("\n%s on %s (%s eye): presence recall %s, precision %s, F1 %s over %d frames | count exact %s "
          "(MAE %s) | episodes seen %d/%d" % (
              a.model, a.clip, a.eye, pr["recall"], pr["precision"], pr["f1"], summary["frames"]["scored"],
              ct["exact"], ct["mean_abs_error"], summary["episodes"]["seen"], summary["episodes"]["sampled"]))
    print("Report: %s" % rel(os.path.join(run_dir, "report.md")))


def write_report(a, run_dir, frames_dir, s, eps, per_person, misses, false_alarms, failed):
    link = lambda r: "[%s](%s/%s)" % (r["file"], os.path.relpath(frames_dir, run_dir), r["file"])  # noqa: E731
    pr, ct, fr = s["presence"], s["count"], s["frames"]
    L = ["# People: %s on %s" % (a.model, a.clip), ""]
    if not s["labels"]["complete"]:
        L += ["> **Labels are not marked complete**, so these numbers are provisional.", ""]
    L += ["Labels: `%s`. %d frames, one every %gs from the %s eye, %s: %d answered, %d failed, %d scored. "
          "Not scored: %s." % (s["labels"]["source"], fr["total"], a.every, a.eye,
                               "one per request" if a.batch == 1 else
                               "%d per request (each request mixes frames from across the clip)" % a.batch,
                               fr["answered"], fr["failed"],
                               fr["scored"], ", ".join("%d %s" % (v, k) for k, v in fr["not_scored"].items()) or "none"),
          "", "| Metric | Value |", "|---|---|",
          "| Presence recall (frames with people where it said yes) | %s |" % pr["recall"],
          "| Presence precision (yes answers that were right) | %s |" % pr["precision"],
          "| Presence F1 | %s |" % pr["f1"],
          "| False alarm rate (yes on frames with nobody) | %s |" % pr["false_alarm_rate"],
          "| TP / FP / FN / TN | %d / %d / %d / %d |" % (pr["tp"], pr["fp"], pr["fn"], pr["tn"]),
          "| Count exact / within 1 (%d frames with people) | %s / %s |" % (ct["frames"], ct["exact"], ct["within_1"]),
          "| Count mean abs error / bias (+ = overcounts) | %s / %s |" % (ct["mean_abs_error"], ct["mean_bias"]),
          "| Stretches with people where it said yes at least once | %d of %d |" % (
              s["episodes"]["seen"], s["episodes"]["sampled"]),
          "| People seen on frames where they were alone in view | %d of %d |" % (
              s["people_seen_when_alone"]["seen"], s["people_seen_when_alone"]["people"]),
          "| Tokens | %s |" % ", ".join("%s %s" % (k, v) for k, v in s["usage_tokens"].items()),
          "", "## People", "",
          "`samples` = sampled frames inside the person's span; `alone` = of those, frames where nobody else was in view.",
          "", "| who | in view | samples | said yes | alone: said yes | flags | description |", "|---|---|---|---|---|---|---|"]
    for p in per_person:
        L.append("| %s | %s–%s | %d | %d | %s | %s | %s |" % (
            p["label"], fmt(p["start"]), fmt(p["end"]), p["samples"], p["hits"],
            "%d/%d" % (p["alone_hits"], p["alone_samples"]) if p["alone_samples"] else "–", p["flags"], p["desc"]))
    L += ["", "## Stretches with someone in view", "", "| from | to | people | samples | said yes |", "|---|---|---|---|---|"]
    for e in eps:
        L.append("| %s | %s | %s | %d | %s |" % (fmt(e["start"]), fmt(e["end"]), ", ".join(e["people"]),
                                                 e["samples"], "%d" % e["hits"] if e["samples"] else "not sampled"))
    L += ["", "## Misses (someone in view, model said no)", ""]
    L += ["- %s %s (labeled %s in view)" % (fmt(r["t"]), link(r), r["gt_count"] if r["gt_count"] is not None else "≥1")
          for r in misses] or ["None."]
    L += ["", "## False alarms (nobody labeled, model said yes)", ""]
    L += ['- %s %s: %s people, "%s"' % (fmt(r["t"]), link(r), r.get("num_people"), r.get("where", ""))
          for r in false_alarms] or ["None."]
    if failed:
        L += ["", "## Failed requests (rerun the same command to retry)", ""]
        L += ["- %s %s: %s" % (fmt(r["t"]), r["file"], r.get("error", "")[:200]) for r in failed]
    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", help="clip name from eval/clips.json, e.g. test-1")
    ap.add_argument("--labels", help="people labels: CSV or label_server JSON (default: from eval/clips.json)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model id (default %(default)s)")
    ap.add_argument("--eye", choices=["left", "right", "both"],
                    help="which camera to show the model (default: the eye the labels were made on)")
    ap.add_argument("--every", type=float, default=1.0, help="seconds between sampled frames (default 1)")
    ap.add_argument("--edge", type=float, default=0.25,
                    help="don't score frames where presence changes within this many seconds (default 0.25)")
    ap.add_argument("--media-resolution", choices=["low", "medium", "high"], help="Gemini image detail level")
    ap.add_argument("--thinking", help="thinking level (e.g. low/high) or token budget (e.g. 0, 512)")
    ap.add_argument("--tag", default="", help="suffix for the output folder, e.g. to compare settings")
    ap.add_argument("--limit", type=int, help="only ask about this many frames (spread over the clip)")
    ap.add_argument("--batch", type=int, default=20,
                    help="frames per request (default 20, to fit the free tier's 20 requests/day; 1 = one frame per request)")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--score-only", action="store_true", help="don't call the model; just re-score")
    a = ap.parse_args()

    clip = common.clip_config(a.clip)
    video = clip.get("video")
    if not video or not os.path.isfile(video):
        sys.exit("video for %s not found (add it to eval/clips.json)" % a.clip)
    a.eye = a.eye or clip.get("labeled_eye") or "right"
    info = common.probe(video)
    step = max(1, int(round(a.every * info["fps"])))
    clip_dir = os.path.join(common.HERE, "out", a.clip)
    frames_dir = os.path.join(clip_dir, "frames-%s-every%df" % (a.eye, step))
    run_name = "-".join(x for x in [a.model, a.eye, "every%df" % step,
                                    "media_" + a.media_resolution if a.media_resolution else "",
                                    "think_" + a.thinking if a.thinking else "",
                                    "batch%d" % a.batch if a.batch > 1 else "", a.tag] if x)
    run_dir = os.path.join(clip_dir, "people", run_name)
    os.makedirs(run_dir, exist_ok=True)
    results_path = os.path.join(run_dir, "results.jsonl")

    frames = extract_frames(video, info, a.eye, step, frames_dir)
    if not a.score_only:
        run_model(a, frames, frames_dir, results_path)

    labels = a.labels or clip.get("humans") or os.path.join(common.HERE, "labels", a.clip + ".json")
    if not os.path.exists(labels):
        print("\nNo people labels for %s: answers are saved; rerun with --score-only once labeled." % a.clip)
        return
    people, label_info = load_people(labels)
    score(a, frames, frames_dir, results_path, run_dir, people, label_info)


if __name__ == "__main__":
    main()
