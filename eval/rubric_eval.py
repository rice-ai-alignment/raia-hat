#!/usr/bin/env python3
"""Score a Gemini model on the clip's rubric: object lists, question checks, and a weighted scorecard.

Reads the rubric markdown listed in eval/clips.json, which has three parts:
  - an object table, one row per timestamp:  | 00:30 | bicycle;trash bins;tree;... |
  - question checks:  **Eval N — Title**, "10 points", "Timestamp: 01:00" (or "01:00–01:10"),
    **Question:** ..., **Ground truth:** ...
  - the category table:  | Category | Weight | What you're evaluating |

What runs
  objects    For each timestamp, the model lists everything it sees in that frame. A judge model
             decides which annotated objects the list contains (synonyms count). Score = recall.
             The annotations aren't exhaustive, so extra objects in the list aren't penalized.
  questions  The model answers each question from the frame at the timestamp, or from one frame per
             second across a time range. A judge model grades the answer against the ground truth.
  scorecard  Each rubric category scores the mean of its evidence (0-1) times its weight:
               Object identification          object recall + its question checks
               Person detection and counting  people-eval presence F1 + exact count rate + its questions
               Uncertainty and hallucination  1 - people-eval false alarm rate (says "person" when nobody's there)
               other categories               their question checks
             The people-eval numbers come from vlm_eval.py for the same model and eye; run that first.
             Categories with no evidence are reported as not covered.

  python3 eval/rubric_eval.py test-1
  python3 eval/rubric_eval.py test-1 --model gemini-2.5-flash --judge gemini-3.1-pro-preview

Requests: object lists go 10 frames per request (--batch), each question is its own request, and the
judge grades all object lists in one request and all questions in another: about 10 requests in all,
to fit the free tier's 20 requests per model per day. Answers and grades are cached (answers.jsonl,
grades.jsonl), so reruns only redo what's missing, and a used-up daily quota stops the run cleanly.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from common import ApiError, QuotaExhausted, fmt, rel  # noqa: E402

DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_JUDGE = "gemini-3.1-pro-preview"

OBJECTS_PROMPT = """This image is one frame from a camera worn on the head (a first-person view).

List the distinct objects and things you can see in it, using short common names (for example "trash bin", "sidewalk", "person"). Include structures, surfaces, plants, vehicles, furniture, signs, devices and people, and the camera wearer's own hands or feet if they are visible. Only list things you can actually see in this frame."""

OBJECTS_SCHEMA = {"type": "OBJECT", "properties": {"objects": {"type": "ARRAY", "items": {"type": "STRING"}}},
                  "required": ["objects"]}

OBJECTS_BATCH_PROMPT = """These %d images are separate frames from a camera worn on the head (a first-person view), taken at different moments.

For each frame, list the distinct objects and things you can see in it, using short common names (for example "trash bin", "sidewalk", "person"). Include structures, surfaces, plants, vehicles, furniture, signs, devices and people, and the camera wearer's own hands or feet if they are visible. Only list things you can actually see in that frame. Use the frame numbers shown."""

OBJECTS_BATCH_SCHEMA = {"type": "OBJECT", "properties": {"frames": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"frame": {"type": "INTEGER"}, "objects": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["frame", "objects"]}}}, "required": ["frames"]}

QA_INTRO_FRAME = "This image is one frame from a camera worn on the head (a first-person view), %s into the recording."
QA_INTRO_RANGE = ("These are frames from a camera worn on the head (a first-person view), one per second "
                  "from %s to %s into the recording, in order.")
QA_ASK = """Question: %s

Answer directly and briefly, based only on what you can see. If you can't tell, say so."""
QA_SCHEMA = {"type": "OBJECT", "properties": {"answer": {"type": "STRING"}}, "required": ["answer"]}

MATCH_PROMPT = """A person annotated the main objects visible in several video frames. A vision model separately listed what it saw in each frame. The frames are given below as JSON.

For each frame, and for each annotated object in it, decide whether the model's list for that frame includes it. Count it as found if the list names the same thing under the same or an equivalent name: a synonym, singular/plural, or a more specific or more general name for the same object (for example "pedestrian" = "person", "trash can" = "trash bins", "pavement" = "sidewalk", "pillars" = "columns", "phone" = "smartphone"). Don't count it if the list only names something related or nearby (for example "building" does not cover "columns", and "road" does not cover "crosswalk").

Return every frame id and every annotated object exactly as given.

%s"""

MATCH_SCHEMA = {"type": "OBJECT", "properties": {"frames": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"id": {"type": "STRING"}, "matches": {"type": "ARRAY", "items": {
        "type": "OBJECT", "properties": {"annotated": {"type": "STRING"}, "found": {"type": "BOOLEAN"},
                                         "model_item": {"type": "STRING", "description": "the matching item, or empty"}},
        "required": ["annotated", "found", "model_item"]}}},
    "required": ["id", "matches"]}}}, "required": ["frames"]}

GRADE_PROMPT = """Grade a vision model's answers to questions about first-person video footage, against ground truths written by a person who watched the footage. The items are given below as JSON.

Scoring for each item, out of its points:
- Full points if the answer agrees with the ground truth in substance. Different wording, synonyms and extra correct detail are fine. If the ground truth allows alternatives (for example "two, with a possible third"), any of them is correct.
- Half points if it is partly right: it gets some but not all of the key items, or it hedges between the right answer and a wrong one.
- Zero if it is wrong, contradicts the ground truth, or says it can't tell.

Grade every item id given.

%s"""

GRADE_SCHEMA = {"type": "OBJECT", "properties": {"grades": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {
        "id": {"type": "STRING"}, "score": {"type": "NUMBER"},
        "verdict": {"type": "STRING", "enum": ["correct", "partial", "incorrect"]},
        "reason": {"type": "STRING", "description": "one sentence"}},
    "required": ["id", "score", "verdict", "reason"]}}}, "required": ["grades"]}


# ---------------------------------------------------------------- rubric parsing

def unescape(s):
    return re.sub(r"\\([\\.\-*_#()\[\]+!])", r"\1", s).strip()


def secs(mmss):
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)


def parse_rubric(path):
    with open(path) as f:
        text = f.read()
    objects, categories = [], []
    for line in text.splitlines():
        m = re.match(r"^\|\s*(\d{1,2}:\d{2})\s*\|\s*([^|]+?)\s*\|\s*$", line)
        if m:
            items = [unescape(x) for x in m.group(2).split(";") if x.strip()]
            objects.append({"id": "objects@" + m.group(1), "t": secs(m.group(1)), "ts": m.group(1), "items": items})
            continue
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*\**(\d+)\**\s*\|\s*([^|]*?)\s*\|\s*$", line)
        if m and "total" not in m.group(1).lower():
            categories.append({"name": unescape(m.group(1).strip("* ")), "weight": int(m.group(2)),
                               "what": unescape(m.group(3))})
    evals = []
    blocks = re.split(r"\*\*Eval\s+(\d+)\s*[—–-]\s*(.+?)\*\*", text)
    for i in range(1, len(blocks) - 2, 3):
        n, title, body = blocks[i], unescape(blocks[i + 1]), blocks[i + 2]
        pts = re.search(r"(\d+(?:\.\d+)?)\s*points", body)
        ts = re.search(r"Timestamp:\s*(\d{1,2}:\d{2})(?:\s*[–—-]\s*(\d{1,2}:\d{2}))?", body)
        q = re.search(r"\*\*Question:\*\*\s*(.+)", body)
        gt = re.search(r"\*\*Ground truth:\*\*\s*(.+)", body)
        if not (ts and q and gt):
            print("warning: couldn't parse Eval %s (%s); skipping" % (n, title), file=sys.stderr)
            continue
        evals.append({"id": "eval%s" % n, "n": int(n), "title": title, "points": float(pts.group(1)) if pts else 10.0,
                      "t0": secs(ts.group(1)), "t1": secs(ts.group(2)) if ts.group(2) else None,
                      "ts": ts.group(0).split(":", 1)[1].strip(), "question": unescape(q.group(1)),
                      "truth": unescape(gt.group(1))})
    for e in evals:
        e["category"] = category_for(e["title"], categories)
    return {"path": path, "objects": objects, "categories": categories, "evals": evals}


def category_for(title, categories):
    words = lambda s: {w for w in re.findall(r"[a-z]+", s.lower()) if len(w) > 3}  # noqa: E731
    best = max(categories, key=lambda c: len(words(title) & words(c["name"])), default=None)
    return best["name"] if best and words(title) & words(best["name"]) else None


# ---------------------------------------------------------------- running

class Cache:
    """Append-only jsonl keyed by id; the last line per id wins."""

    def __init__(self, path):
        self.path, self.rows, self.lock = path, {}, threading.Lock()
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        self.rows[r["id"]] = r

    def ok(self, id_):
        return id_ in self.rows and "error" not in self.rows[id_]

    def put(self, row):
        with self.lock:
            self.rows[row["id"]] = row
            with open(self.path, "a") as f:
                f.write(json.dumps(row) + "\n")


def run_parallel(fn, tasks, concurrency, what):
    """Run fn over tasks (each returns a list of rows); stop as soon as a daily quota runs out."""
    if not tasks:
        return
    print("%s: %d request(s) ..." % (what, len(tasks)), flush=True)
    stop, quota = threading.Event(), []

    def guarded(task):
        if stop.is_set():
            return None
        try:
            return fn(task)
        except QuotaExhausted as e:
            stop.set()
            quota.append(str(e))
            return None
    first = guarded(tasks[0])
    if quota:
        sys.exit(quota[0])
    if all("error" in r for r in first):
        sys.exit("First request failed, stopping: %s" % first[0]["error"])
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(guarded, tasks[1:]))
    errors = sum(1 for rows in [first] + results if rows for r in rows if "error" in r)
    if quota:
        sys.exit("Stopped: %s Rerun the same command later; finished answers are kept." % quota[0])
    if errors:
        print("  %d item(s) failed (rerun to retry)" % errors, flush=True)


def chunks(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip")
    ap.add_argument("--rubric", help="rubric markdown (default: from eval/clips.json)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="model under test (default %(default)s)")
    ap.add_argument("--judge", default=DEFAULT_JUDGE, help="grading model (default %(default)s)")
    ap.add_argument("--eye", choices=["left", "right", "both"], help="default: the eye the labels were made on")
    ap.add_argument("--media-resolution", choices=["low", "medium", "high"])
    ap.add_argument("--thinking", help="thinking level or budget for the model under test")
    ap.add_argument("--tag", default="")
    ap.add_argument("--batch", type=int, default=10,
                    help="object-list frames per request (default 10, to fit the free tier; 1 = one per request)")
    ap.add_argument("--concurrency", type=int, default=3)
    a = ap.parse_args()

    clip = common.clip_config(a.clip)
    video, rubric_path = clip.get("video"), a.rubric or clip.get("rubric")
    if not (video and os.path.isfile(video)):
        sys.exit("video for %s not found (add it to eval/clips.json)" % a.clip)
    if not (rubric_path and os.path.isfile(rubric_path)):
        sys.exit("rubric for %s not found (add it to eval/clips.json or pass --rubric)" % a.clip)
    a.eye = a.eye or clip.get("labeled_eye") or "right"
    info = common.probe(video)
    rubric = parse_rubric(rubric_path)
    print("Rubric %s: %d object timestamps, %d question checks, %d categories" % (
        rel(rubric_path), len(rubric["objects"]), len(rubric["evals"]), len(rubric["categories"])))
    for e in rubric["evals"]:
        print("  Eval %d (%s @ %s) -> %s" % (e["n"], e["title"], e["ts"], e["category"] or "NO CATEGORY"))

    clip_dir = os.path.join(common.HERE, "out", a.clip)
    frames_dir = os.path.join(clip_dir, "frames-%s-rubric" % a.eye)
    run_name = "-".join(x for x in [a.model, a.eye, "media_" + a.media_resolution if a.media_resolution else "",
                                    "think_" + a.thinking if a.thinking else "", a.tag] if x)
    run_dir = os.path.join(clip_dir, "rubric", run_name)  # batch size is recorded per answer, not in the name
    os.makedirs(run_dir, exist_ok=True)
    answers, grades = Cache(os.path.join(run_dir, "answers.jsonl")), Cache(os.path.join(run_dir, "grades.jsonl"))
    frame = lambda t: common.extract_frame(video, info, t, a.eye, os.path.join(frames_dir, "t%06.1f.jpg" % t))  # noqa: E731
    key = common.load_key()
    opts = {"media_resolution": a.media_resolution, "thinking": a.thinking}

    # 1. the model under test: object lists in batches of --batch frames, questions one per request
    def answer(task):
        kind, items = task
        try:
            if kind == "objects":
                if len(items) == 1:
                    ans, meta = common.gemini_json(key, a.model, [common.image_part(frame(items[0]["t"])),
                                                                  common.text_part(OBJECTS_PROMPT)], OBJECTS_SCHEMA, **opts)
                    lists = {1: ans.get("objects", [])}
                else:
                    parts = []
                    for i, o in enumerate(items, 1):
                        parts += [common.text_part("Frame %d:" % i), common.image_part(frame(o["t"]))]
                    parts.append(common.text_part(OBJECTS_BATCH_PROMPT % len(items)))
                    ans, meta = common.gemini_json(key, a.model, parts, OBJECTS_BATCH_SCHEMA, **opts)
                    lists = {x["frame"]: x.get("objects", []) for x in ans.get("frames", [])
                             if isinstance(x, dict) and isinstance(x.get("frame"), int)}
                rows = []
                for i, o in enumerate(items, 1):
                    row = dict(meta, id=o["id"], batch_size=len(items), usage=meta["usage"] if i == 1 else None)
                    if i in lists:
                        row["objects"] = [str(x) for x in lists[i]]
                    else:
                        row["error"] = "no list for frame %d of %d in the response" % (i, len(items))
                    rows.append(row)
            else:
                item = items[0]
                if item["t1"] is None:
                    parts = [common.image_part(frame(item["t0"])),
                             common.text_part(QA_INTRO_FRAME % fmt(item["t0"]) + "\n\n" + QA_ASK % item["question"])]
                else:
                    parts = []
                    for t in range(item["t0"], item["t1"] + 1):
                        parts += [common.text_part("Frame at %s:" % fmt(t)), common.image_part(frame(t))]
                    parts.append(common.text_part(QA_INTRO_RANGE % (fmt(item["t0"]), fmt(item["t1"])) + "\n\n" +
                                                  QA_ASK % item["question"]))
                ans, meta = common.gemini_json(key, a.model, parts, QA_SCHEMA, **opts)
                rows = [dict(meta, id=item["id"], answer=str(ans.get("answer", "")))]
        except QuotaExhausted:
            raise
        except ApiError as e:
            rows = [{"id": i["id"], "error": str(e)} for i in items]
        for row in rows:
            row["model"] = a.model
            answers.put(row)
        return rows

    obj_todo = [o for o in rubric["objects"] if not answers.ok(o["id"])]
    qa_todo = [e for e in rubric["evals"] if not answers.ok(e["id"])]
    run_parallel(answer, [("objects", c) for c in chunks(obj_todo, a.batch)] + [("qa", [e]) for e in qa_todo],
                 a.concurrency, "Asking %s" % a.model)

    # 2. the judge: all object lists in one request, all questions in another (text only).
    #    An item is regraded whenever its answer or the judge model changes.
    def answer_ref(i):
        ans = answers.rows[i["id"]]
        return ans.get("objects", ans.get("answer"))

    def needs_grade(i):
        g = grades.rows.get(i["id"])
        return answers.ok(i["id"]) and not (g and "error" not in g and g.get("judge") == a.judge
                                            and g.get("answer_ref") == answer_ref(i))

    def grade(task):
        kind, items = task
        try:
            if kind == "objects":
                payload = [{"id": o["id"], "annotated": o["items"], "model_list": answers.rows[o["id"]]["objects"]}
                           for o in items]
                g, meta = common.gemini_json(key, a.judge, [common.text_part(MATCH_PROMPT % json.dumps(payload, indent=1))],
                                             MATCH_SCHEMA)
                by_id = {x.get("id"): x for x in g.get("frames", []) if isinstance(x, dict)}
                rows = []
                for o in items:
                    x = by_id.get(o["id"])
                    if not x:
                        rows.append({"id": o["id"], "error": "judge returned no grade for this frame"})
                        continue
                    found = {str(m.get("annotated", "")).strip().lower(): m for m in x.get("matches", [])}
                    matches = [{"annotated": it, "found": bool(found.get(it.lower(), {}).get("found")),
                                "model_item": found.get(it.lower(), {}).get("model_item", "")} for it in o["items"]]
                    rows.append({"id": o["id"], "matches": matches,
                                 "score": sum(m["found"] for m in matches) / float(len(matches))})
            else:
                payload = [{"id": e["id"], "question": e["question"], "ground_truth": e["truth"],
                            "answer": answers.rows[e["id"]]["answer"], "points": e["points"]} for e in items]
                g, meta = common.gemini_json(key, a.judge, [common.text_part(GRADE_PROMPT % json.dumps(payload, indent=1))],
                                             GRADE_SCHEMA)
                by_id = {x.get("id"): x for x in g.get("grades", []) if isinstance(x, dict)}
                rows = []
                for e in items:
                    x = by_id.get(e["id"])
                    if not x:
                        rows.append({"id": e["id"], "error": "judge returned no grade for this question"})
                        continue
                    pts = max(0.0, min(e["points"], float(x.get("score", 0))))
                    rows.append({"id": e["id"], "points": pts, "score": pts / e["points"],
                                 "verdict": x.get("verdict"), "reason": x.get("reason", "")})
            for i, row in enumerate(rows):
                if i == 0 and "error" not in row:
                    row.update({k: v for k, v in meta.items()})
        except QuotaExhausted:
            raise
        except (ApiError, KeyError, TypeError, ValueError) as e:
            rows = [{"id": i["id"], "error": str(e)} for i in items]
        by_item = {i["id"]: i for i in items}
        for row in rows:
            row.update(judge=a.judge, answer_ref=answer_ref(by_item[row["id"]]))
            grades.put(row)
        return rows

    tasks = []
    for kind, pool in (("objects", rubric["objects"]), ("qa", rubric["evals"])):
        todo = [i for i in pool if needs_grade(i)]
        if todo:
            tasks.append((kind, todo))
    run_parallel(grade, tasks, a.concurrency, "Grading with %s" % a.judge)

    report(a, clip_dir, run_dir, frames_dir, rubric, answers, grades)


# ---------------------------------------------------------------- scorecard + report

def report(a, clip_dir, run_dir, frames_dir, rubric, answers, grades):
    g = lambda i: grades.rows.get(i["id"]) if grades.ok(i["id"]) else None  # noqa: E731
    obj_scores = [g(o)["score"] for o in rubric["objects"] if g(o)]
    obj_recall = sum(obj_scores) / len(obj_scores) if obj_scores else None

    found = sorted(glob.glob(os.path.join(clip_dir, "people", "%s-%s-every30f*" % (a.model, a.eye), "summary.json")),
                   key=os.path.getmtime)
    people_dir = os.path.dirname(found[-1]) if found else os.path.join(clip_dir, "people", "%s-%s-every30f" % (a.model, a.eye))
    people = None
    if found:
        with open(found[-1]) as f:
            people = json.load(f)

    evidence = {c["name"]: [] for c in rubric["categories"]}

    def add(cat_word, name, value):
        for c in rubric["categories"]:
            if cat_word in c["name"].lower() and value is not None:
                evidence[c["name"]].append((name, value))
                return
    add("object", "object recall over %d timestamps" % len(obj_scores), obj_recall)
    if people:
        add("person", "people eval: presence F1", people["presence"]["f1"])
        add("person", "people eval: exact count rate", people["count"]["exact"])
        far = people["presence"]["false_alarm_rate"]
        add("hallucination", "people eval: 1 − false alarm rate", None if far is None else 1 - far)
    for e in rubric["evals"]:
        if e["category"] and g(e):
            evidence[e["category"]].append(("Eval %d: %s" % (e["n"], e["title"]), g(e)["score"]))

    rows, total, covered = [], 0.0, 0
    for c in rubric["categories"]:
        ev = evidence[c["name"]]
        if ev:
            s = sum(v for _, v in ev) / len(ev)
            total += s * c["weight"]
            covered += c["weight"]
        rows.append((c, ev, sum(v for _, v in ev) / len(ev) if ev else None))
    all_w = sum(c["weight"] for c in rubric["categories"])

    L = ["# Rubric: %s on %s" % (a.model, a.clip), "",
         "Model under test `%s`, judge `%s`, %s eye. Rubric `%s`." % (a.model, a.judge, a.eye, rel(rubric["path"])), ""]
    if not people:
        L += ["> No people-eval summary for this model and eye yet (`%s`); person and hallucination "
              "categories use only the question checks. Run `python3 eval/vlm_eval.py %s --model %s --eye %s` first." % (
                  rel(people_dir), a.clip, a.model, a.eye), ""]
    if people:
        L += ["Person and hallucination evidence from `%s`." % rel(people_dir), ""]
    L += ["## Scorecard", "",
          "**%.1f of %d points** on the categories with evidence (%d of %d weight covered; %.0f%% of covered)." % (
              total, covered, covered, all_w, 100 * total / covered if covered else 0), "",
          "| Category | Weight | Score (0–1) | Points | Evidence |", "|---|---|---|---|---|"]
    for c, ev, s in rows:
        L.append("| %s | %d | %s | %s | %s |" % (
            c["name"], c["weight"], "%.2f" % s if s is not None else "not covered",
            "%.1f" % (s * c["weight"]) if s is not None else "–",
            "; ".join("%s = %.2f" % (n, v) for n, v in ev) or "no evals yet"))
    L += ["", "Each category is the plain mean of its evidence. Object recall can't penalize extra objects, "
          "because the annotations list only the main things in each frame.", "",
          "## Question checks", "", "| Eval | Time | Question | Ground truth | Model's answer | Points | Judge |",
          "|---|---|---|---|---|---|---|"]
    for e in rubric["evals"]:
        ans, gr = answers.rows.get(e["id"], {}), g(e)
        L.append("| %d %s | %s | %s | %s | %s | %s | %s |" % (
            e["n"], e["title"], e["ts"], e["question"], e["truth"],
            (ans.get("answer") or ans.get("error", "no answer")).replace("|", "/").replace("\n", " "),
            "%g / %g" % (gr["points"], e["points"]) if gr else "–",
            ("%s: %s" % (gr["verdict"], gr["reason"])).replace("|", "/") if gr else "not graded"))
    L += ["", "## Objects", "", "Found / annotated per timestamp; missing items in bold. Frames: `%s`." % rel(frames_dir), "",
          "| Time | Found | Annotated objects | Model listed |", "|---|---|---|---|"]
    for o in rubric["objects"]:
        ans, gr = answers.rows.get(o["id"], {}), g(o)
        if gr:
            ann = ", ".join(m["annotated"] if m["found"] else "**%s**" % m["annotated"] for m in gr["matches"])
            found = "%d/%d" % (sum(m["found"] for m in gr["matches"]), len(gr["matches"]))
        else:
            ann, found = ", ".join(o["items"]), "–"
        L.append("| %s | %s | %s | %s |" % (o["ts"], found, ann, ", ".join(ans.get("objects", [])) or ans.get("error", "")))
    usage_m, usage_j = {}, {}
    for r in answers.rows.values():
        common.add_usage(usage_m, r.get("usage"))
    for r in grades.rows.values():
        common.add_usage(usage_j, r.get("usage"))
    L += ["", "Tokens, model under test: %s. Judge: %s." % (
        ", ".join("%s %s" % kv for kv in usage_m.items()), ", ".join("%s %s" % kv for kv in usage_j.items()))]
    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    summary = {"clip": a.clip, "model": a.model, "judge": a.judge, "eye": a.eye,
               "points": round(total, 2), "covered_weight": covered, "total_weight": all_w,
               "categories": [{"name": c["name"], "weight": c["weight"], "score": s,
                               "evidence": [{"name": n, "value": v} for n, v in ev]} for c, ev, s in rows],
               "object_recall": obj_recall,
               "evals": [{"id": e["id"], "points": g(e)["points"] if g(e) else None, "of": e["points"]}
                         for e in rubric["evals"]]}
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("\n%s on %s: %.1f / %d points on covered categories (%d of %d weight covered); object recall %s" % (
        a.model, a.clip, total, covered, covered, all_w, "%.2f" % obj_recall if obj_recall is not None else "n/a"))
    print("Report: %s" % rel(os.path.join(run_dir, "report.md")))


if __name__ == "__main__":
    main()
