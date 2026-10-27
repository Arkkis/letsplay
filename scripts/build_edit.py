"""Turn an edit decision list (edits/*.json) into a frame-accurate timeline for Remotion (work/<vod>/epN.props.json,
the render's input props; src/edit.json and src/thumb.json are only a neutral example for type-checking and Studio)
plus a YouTube description with chapters (out/<name>.description.txt).

Ranges are trimmed to speech + loud game moments unless flagged "full" (or the EDL has "mode": "speedrun");
silences longer than trimming.MERGE_GAP are jump-cut.
Times in the EDL are VOD times (m:ss or h:mm:ss). The prepared episode source (public/<vod>-ep<n>.mp4, made by
`lp.py prep`) starts at the episode's part start, so source frames are offset by it.
"""
import json, os, re, sys
from difflib import SequenceMatcher
import numpy as np
from trimming import loud_db, trim
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import CFG, text, translation_text

FPS = 60
SKIP_TRANSITION = 45  # source seconds skipped before a whoosh transition is used
TITLE_S, LOWER_THIRD_S = 3.5, 5
CAPTION_F, ZOOM_HOLD_F, ZOOM_SPACING_F, EFFECT_SEARCH_S = 132, 110, 240, 30

edl = json.load(open(sys.argv[1]))
work = f"work/{edl['vod']}"
segments = json.load(open(f"{work}/transcript.json"))["segments"]
words = [w for s in segments for w in s["words"]]
rms = np.load(f"{work}/rms100ms.npy")
ocr_effects = json.load(open(f"{work}/effects.json")) if os.path.exists(f"{work}/effects.json") else []
part = json.load(open(f"{work}/parts.json"))[edl["episode"] - 1]
OFF = part["prepStart"]  # VOD second where the prepared source begins
meta = json.load(open(f"{work}/meta.json"))
if meta.get("game") == "chaosmod":
    from games.chaosmod import effects_lib
    EFFECT_LABEL = json.load(open(os.path.join(os.path.dirname(effects_lib.__file__), "labels.json")))
    EFFECT_LABEL = EFFECT_LABEL.get(CFG["language"], EFFECT_LABEL["en"])
elif edl.get("effects"):
    sys.exit("effects need a game module: ingest the VOD with --game chaosmod")
else:
    effects_lib, EFFECT_LABEL = None, ""
style = json.load(open("src/styles.json"))[edl.get("style", "hype")]
speedrun = edl.get("mode") == "speedrun"  # never jump-cut a run: every range is kept whole
LOUD = edl.get("loudDb", loud_db(rms, part["start"], part["end"]))


def sec(t):
    s = 0.0
    for part in t.split(":"):
        s = s * 60 + float(part)
    return s


def word_safe(a, b):
    """Never start or end inside a word: drop a word cut at the head, finish a word cut at the tail."""
    for w in words:
        if w["start"] < a < w["end"]:
            a = w["end"] + 0.02
        if w["start"] < b < w["end"]:
            b = w["end"] + 0.12
    return a, b


clips, cursor = [], 0


def add(section, ranges):
    global cursor
    for r in ranges:
        a, b = word_safe(sec(r[0]), sec(r[1]))
        for x, y in ([[a, b]] if speedrun or "full" in r[2:] else trim(words, rms, a, b, LOUD)):
            d = round((y - x) * FPS)
            clips.append({"section": section, "src": round((x - OFF) * FPS), "dur": d, "from": cursor})
            cursor += d


add("cold", edl["coldOpen"])
title = {**edl["title"], "from": cursor, "dur": round(TITLE_S * FPS), "bg": round((sec(edl["title"]["bg"]) - OFF) * FPS)}
cursor += title["dur"]
add("intro", edl["intro"])
intro_end = cursor
add("main", edl["main"])

for prev, c in zip(clips, clips[1:]):
    c["whoosh"] = c["src"] - (prev["src"] + prev["dur"]) > SKIP_TRANSITION * FPS or c["section"] != prev["section"]


def clip_at(f_out):
    return next(c for c in clips if c["from"] <= f_out < c["from"] + c["dur"])


def place(t, snap=0.0):
    """All output frames where source second t is shown; optionally snap forward to the next clip start."""
    f = (t - OFF) * FPS
    hits = [c["from"] + round(f - c["src"]) for c in clips if c["src"] <= f < c["src"] + c["dur"]]
    if not hits and snap:
        nxt = [c for c in clips if 0 < c["src"] - f <= snap * FPS]
        hits = [min(nxt, key=lambda c: c["src"])["from"]] if nxt else []
    if not hits:
        print(f"warning: {t:.1f}s is outside kept footage")
    return hits


def phrase_time(t, match):
    near = [s for s in segments if abs(s["start"] - t) < 8 and match.lower() in s["text"].lower()]
    if not near:
        missing.append(f"caption '{match}' not found within 8 s of {t // 60:.0f}:{t % 60:04.1f}")
        return None
    s = min(near, key=lambda s: abs(s["start"] - t))
    w = next((w for w in s["words"] if match.split()[0].lower() in w["word"].lower()), s["words"][0])
    return w["start"]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def ocr_match(key, text):
    """OCR drops letters at the crop edge and merges words, so accept containment or a close fuzzy match."""
    return key in text or (len(text) >= 0.75 * len(key) and text in key) or SequenceMatcher(None, key, text).ratio() > 0.85


def effect_time(t, effect):
    """Activation time of an effect from the OCR log, nearest to the EDL's rough time."""
    key = norm(effect)
    hits = [e[0] for e in ocr_effects if abs(e[0] - t) < EFFECT_SEARCH_S
            and ((effects_lib and effects_lib.canonical(e[1]) == effect) or ocr_match(key, norm(e[1])))]
    if not hits:
        print(f"warning: no OCR activation for {effect} near {t:.0f}s, using EDL time")
        return t
    return min(hits, key=lambda h: abs(h - t))


def zooms(times):
    """Space zooms apart and end each one at its clip's cut at the latest (hard out on the cut)."""
    out = []
    for f in sorted(f for t in times for f in place(sec(t), snap=2)):
        if out and f - out[-1]["at"] < ZOOM_SPACING_F:
            print(f"warning: dropped zoom at {f / FPS:.1f}s (too close to previous)")
            continue
        c = clip_at(f)
        end = min(f + ZOOM_HOLD_F, c["from"] + c["dur"])
        out.append({"at": f, "end": end, "hard": end == c["from"] + c["dur"]})
    return out


if effects_lib:
    effects_lib.learn(edl["effects"])  # new one-line descriptions go into the library for later episodes
effects = [{"at": f, "name": n, "fi": fi if fi and fi != "TODO" else effects_lib.desc(n)}
           for t, n, fi in edl["effects"] for f in place(effect_time(sec(t), n), snap=12)]
missing = []
caption_times = [(phrase_time(sec(t), match), text) for t, match, text in edl["captions"]]
missing += [f"chapter at {t} is still a draft label: {label}" for t, label in edl["chapters"] if label.startswith("TODO")]
missing += [f"effect '{n}' has no description" for _, n, fi in edl["effects"] if not (fi and fi != "TODO") and not effects_lib.desc(n)]
if missing:  # report every problem at once
    sys.exit("\n".join(missing))
captions = sorted(({"at": f, "text": text} for t, text in caption_times for f in place(t, snap=1)), key=lambda c: c["at"])
for prev, c in zip(captions, captions[1:]):
    c["slot"] = prev.get("slot", 0) + 1 if c["at"] - prev["at"] < CAPTION_F else 0

last = clips[-1]
freeze = {"from": cursor, "dur": round(edl["endFreeze"]["seconds"] * FPS), "src": last["src"] + last["dur"] - 1, "text": edl["endFreeze"]["text"]}
cursor += freeze["dur"]
end = {"from": cursor, "dur": round(edl["endScreen"]["seconds"] * FPS), **{k: v for k, v in edl["endScreen"].items() if k != "seconds"}}
cursor += end["dur"]
lt = place(sec(edl["lowerThird"]["at"]), snap=5)[0]

# Compositions are laid out at 1920x1080 and rendered at the VOD's native size, so VOD pixels map to layout units.
cam = edl["cam"] and [round(v * 1920 / meta["width"]) for v in edl["cam"]]  # null: no webcam in this stream
if not cam and edl["faceZooms"]:
    sys.exit("faceZooms need a webcam; set \"cam\" or empty the list")
out = {"fps": FPS, "duration": cursor, "source": f"{edl['vod']}-ep{edl['episode']}.mp4", "cam": cam,
       "style": edl.get("style", "hype"), "clips": clips, "title": title, "introEnd": intro_end,
       "freeze": freeze, "end": end, "lowerThird": {**edl["lowerThird"], "from": lt, "dur": LOWER_THIRD_S * FPS},
       "effects": effects, "captions": captions, "faceZooms": zooms(edl["faceZooms"]), "gameZooms": zooms(edl["gameZooms"]),
       "text": {"effect_label": EFFECT_LABEL, "next_episode": text("next_episode"), "playlist": text("playlist")}}
th = edl["thumb"]
thumb = {**th, "bg": round((sec(th["bg"]) - OFF) * FPS), "face": th.get("face") and round((sec(th["face"]) - OFF) * FPS)}
json.dump({"edit": out, "thumb": thumb}, open(f"{work}/ep{edl['episode']}.props.json", "w"), ensure_ascii=False)

def credit_lines(tr):
    """Music and sound credits in the channel's language (tr=text) or the translation language (tr=translation_text)."""
    songs = f" {tr('and')} ".join(f'"{m}"' for m in style["music"])
    return "\n".join([tr("music", songs=songs), tr("license"), tr("sfx")])


credits = (edl.get("credits") or credit_lines(text)).strip()

# YouTube chapters: first must be 0:00, each at least 10 s apart. Keep the EDL index to pair English labels.
chapters = [(0, 0)]
for i, (t, label) in enumerate(edl["chapters"][1:], 1):
    f = place(sec(t), snap=30)[0] if t not in ("end",) else end["from"]
    if f / FPS - chapters[-1][0] >= 10:
        chapters.append((f / FPS, i))
fmt = lambda s: f"{int(s // 60)}:{int(s % 60):02}"


def description(text, labels, credit):
    return text.strip() + "\n\n" + "\n".join(f"{fmt(s)} {labels[i]}" for s, i in chapters) + "\n\n" + credit + "\n"


os.makedirs("out", exist_ok=True)
with open(f"out/{edl['output']}.description.txt", "w") as fh:
    fh.write(description(edl["description"], [l for _, l in edl["chapters"]], credits))
# Title/description in the translation language (config "translation", e.g. "en") for YouTube localizations; the EDL's
# "<lang>.chapters" lists labels in the EDL's chapter order.
TR = CFG.get("translation")
if TR and TR in edl:
    tr = edl[TR]
    assert len(tr["chapters"]) == len(edl["chapters"]), f"{TR}.chapters must match chapters one to one"
    json.dump({"title": tr["title"], "description": description(tr["description"], tr["chapters"], credit_lines(translation_text))},
              open(f"out/{edl['output']}.{TR}.json", "w"), ensure_ascii=False, indent=1)


def srt_time(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


# Subtitles (commentary language) on the edited timeline: every transcript word shown in a clip, grouped into short cues.
CUE_GAP, CUE_CHARS, CUE_S, LINE = 0.7, 84, 5.0, 42
shown = sorted((c["from"] / FPS + w["start"] - c["src"] / FPS, w["end"] - w["start"], w["word"].strip())
               for w in words for c in clips if c["src"] <= w["start"] * FPS - OFF * FPS and (w["end"] - OFF) * FPS <= c["src"] + c["dur"])
cues = []
for t, d, text in shown:
    cur = cues[-1] if cues else None
    if (not cur or t - cur[1] > CUE_GAP or len(cur[2]) + len(text) > CUE_CHARS or t + d - cur[0] > CUE_S
            or cur[2][-1:] in ".?!"):
        cues.append([t, t + d, text])
    else:
        cur[1], cur[2] = t + d, cur[2] + " " + text


def wrap(text):
    if len(text) <= LINE:
        return text
    cut = min((i for i, ch in enumerate(text) if ch == " "), key=lambda i: abs(i - len(text) / 2))
    return text[:cut] + "\n" + text[cut + 1:]


with open(f"out/{edl['output']}.{CFG['language']}.srt", "w") as fh:
    nxt = [c[0] for c in cues[1:]] + [cursor / FPS]  # hold short cues for 1 s, but never into the next one
    fh.writelines(f"{n}\n{srt_time(a)} --> {srt_time(min(max(b, a + 1.0), z))}\n{wrap(text)}\n\n"
                  for n, ((a, b, text), z) in enumerate(zip(cues, nxt), 1))

print(f"{len(clips)} clips (<2s: {sum(c['dur'] < 120 for c in clips)}), {cursor / FPS / 60:.1f} min total, "
      f"effects={len(effects)} captions={len(captions)} faceZooms={len(out['faceZooms'])} gameZooms={len(out['gameZooms'])} chapters={len(chapters)}")
