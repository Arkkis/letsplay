"""Turn an edit decision list (edits/*.json) into a frame-accurate timeline for Remotion (work/<vod>/epN.props.json,
the render's input props; src/edit.json and src/thumb.json are only a neutral example for type-checking and Studio)
plus a YouTube description with chapters (out/<playlist>/<name>.description.txt).

Ranges are trimmed to speech, loud game moments, visual action and audio events (laughs, screams) unless flagged "full"
(or the EDL has "mode": "speedrun"); silences longer than trimming.MERGE_GAP are jump-cut. A speed flag ("x4"
fast-forward, "x0.5" slow motion) keeps the range whole and plays it at that rate.
Times in the EDL are VOD times (m:ss or h:mm:ss). The prepared episode source (public/<vod>-ep<n>.mp4, made by
`lp.py prep`) starts at the episode's part start, so source frames are offset by it.
"""
import hashlib, json, os, re, subprocess, sys
from difflib import SequenceMatcher
import numpy as np
from media import GRADE, partner_span, video_encoder
from trimming import fix_words, loud_db, merge, motion_thr, real_words, trim
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import CFG, about_partner, out_dir, text, translation_text

FPS = 60
SKIP_TRANSITION = 45  # source seconds skipped before a whoosh transition is used
TITLE_S, LOWER_THIRD_S, CARD_S = 2.5, 5, 3.5  # TITLE_S: RULEBOOK 5.1b (1.5 s was too fast to read; viewers left on 3.5 s)
CAPTION_F, ZOOM_HOLD_F, ZOOM_SPACING_F, EFFECT_SEARCH_S = 132, 110, 240, 30
WORD_F = 7  # caption word cadence when a word can't be matched to speech
PUNCH_SPACING_F, PUNCH_RISE_DB = 15 * FPS, 10  # audio-reactive punch-ins: at most one per 15 s, on a sharp loudness rise
XFADE_F, LEAD_F = 5, 9  # audio crossfade over every cut; J-cut lead when the next clip opens with speech
RECAP_FADE_F, RECAP_GAP_F = 18, 30  # the recap fades to black and holds it, so "previously" and the cold open don't blur together
TALK_GAP, TALK_PAD = 0.6, 0.25  # music bed ducking: speech stretches merged and padded (seconds)

edl = json.load(open(sys.argv[1]))
work = f"work/{edl['vod']}"
segments = json.load(open(f"{work}/transcript.json"))["segments"]
words = [w for s in segments for w in s["words"]]
rms = np.load(f"{work}/rms100ms.npy")
said = fix_words(real_words(words, rms), edl.get("wordFixes"))  # subtitles: no ghosts, proof-read spellings; the trim keeps every word so a ghost never changes a cut
ocr_effects = json.load(open(f"{work}/effects.json")) if os.path.exists(f"{work}/effects.json") else []
events = json.load(open(f"{work}/events.json")) if os.path.exists(f"{work}/events.json") else []
motion = np.load(f"{work}/motion.npz")["game"] if os.path.exists(f"{work}/motion.npz") else None
parts = json.load(open(f"{work}/parts.json"))
part = parts[edl["episode"] - 1]
OFF = part["prepStart"]  # VOD second where the prepared source begins
meta = json.load(open(f"{work}/meta.json"))
if meta.get("game") == "chaosmod":
    from games.chaosmod import effects_lib
    EFFECT_LABEL = json.load(open(os.path.join(os.path.dirname(effects_lib.__file__), "labels.json")))
    EFFECT_LABEL = EFFECT_LABEL.get(CFG["language"], EFFECT_LABEL["en"])
elif edl.get("effects") and not edl.get("effectLabel"):
    sys.exit("effects need a game module (ingest with --game chaosmod) or an \"effectLabel\" for hand-placed banners")
else:
    effects_lib, EFFECT_LABEL = None, ""
EFFECT_LABEL = edl.get("effectLabel", EFFECT_LABEL)  # hand-placed banners (no OCR) bring their own label
style = json.load(open("src/styles.json"))[edl.get("style", "hype")]
speedrun = edl.get("mode") == "speedrun"  # never jump-cut a run: every range is kept whole
LOUD = edl.get("loudDb", loud_db(rms, part["start"], part["end"]))
MOTION = (motion, motion_thr(motion, part["start"], part["end"])) if motion is not None else None


def sec(t):
    s = 0.0
    for part in t.split(":"):
        s = s * 60 + float(part)
    return s


def word_safe(a, b):
    """Never start or end inside a word: drop a word cut at the head, finish a word cut at the tail (one word only:
    Whisper's words often abut, and stepping on through them would drop whole phrases)."""
    w = next((w for w in words if w["start"] < a < w["end"]), None)
    if w:
        a = w["end"]
    w = next((w for w in words if w["start"] < b < w["end"]), None)
    if w:
        b = w["end"] + 0.12
    return a, b


clips, cursor = [], 0


def add(section, ranges):
    global cursor
    for r in ranges:
        a, b = word_safe(sec(r[0]), sec(r[1]))
        rate = next((float(f[1:]) for f in r[2:] if f.startswith("x")), 1.0)
        for x, y in ([[a, b]] if speedrun or rate != 1 or "full" in r[2:] else trim(words, rms, a, b, LOUD, MOTION, events)):
            d = round((y - x) * FPS / rate)
            clips.append({"section": section, "src": round((x - OFF) * FPS), "dur": d, "from": cursor, **({"rate": rate} if rate != 1 else {})})
            cursor += d


def recap_ranges():
    """'Previously': the EDL's own ranges, or "auto" = the previous episode's cold open (VOD times, any part)."""
    r = edl.get("recap")
    if r == "auto":
        prev = f"edits/{edl['vod']}-ep{edl['episode'] - 1}.json"
        if not os.path.exists(prev):
            sys.exit(f"recap \"auto\" needs the previous episode's EDL ({prev})")
        r = [x[:2] for x in json.load(open(prev))["coldOpen"]]
    return [[sec(a), sec(b)] for a, b in r] if r else []


def recap_file(ranges):
    """The recap's own graded source (public/<vod>-epN-recap.mp4): the ranges back to back, cut from the raw VOD,
    because the prepared episode source only holds this episode's part. Rebuilt when the ranges change."""
    name = f"{edl['vod']}-ep{edl['episode']}-recap.mp4"
    src, cuts, grade = f"footage/{edl['vod']}.mp4", ranges, f"{GRADE},"
    # Separate-track streams: footage/ is only the analysis reference (plain webcam boxes), so take the previous episode's
    # cold open from its rendered output instead (cut-outs, captions and all), when its clips are those ranges.
    prev = f"edits/{edl['vod']}-ep{edl['episode'] - 1}.json"
    if os.path.exists(f"work/{edl['vod']}/assemble.json") and os.path.exists(prev):
        p = json.load(open(prev))
        props, mp4 = f"work/{edl['vod']}/ep{p['episode']}.props.json", f"{out_dir(p)}/{p['output']}.mp4"
        if os.path.exists(props) and os.path.exists(mp4):
            pe = json.load(open(props))
            cold = [c for c in pe.get("edit", pe)["clips"] if c.get("section") == "cold"]
            if len(cold) == len(ranges) and all(abs(c["dur"] - (b - a) * FPS) <= 2 for c, (a, b) in zip(cold, ranges)):
                src, cuts, grade = mp4, [[c["from"] / FPS, (c["from"] + c["dur"]) / FPS] for c in cold], ""
    key = hashlib.md5(json.dumps([src, cuts]).encode()).hexdigest()[:8]
    out, tag = f"public/{name}", f"public/{name}.{key}"
    if not (os.path.exists(out) and os.path.exists(tag)):
        inputs = [x for a, b in cuts for x in ("-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src)]
        graph = "".join(f"[{i}:v][{i}:a]" for i in range(len(cuts))) + f"concat=n={len(cuts)}:v=1:a=1[v0][a];[v0]{grade}fps={FPS}[v]"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                        *video_encoder(), "-g", "60", "-c:a", "aac", "-b:a", "256k", out], check=True)
        for f in [f for f in os.listdir("public") if f.startswith(name + ".")]:
            os.remove(f"public/{f}")
        open(tag, "w").close()
    return name


recap = recap_ranges()
if recap:
    src_f, name = 0, recap_file(recap)
    for a, b in recap:
        d = round((b - a) * FPS)
        clips.append({"section": "recap", "file": name, "src": src_f, "dur": d, "from": cursor})
        src_f += d
        cursor += d
    clips[-1]["fade"] = RECAP_FADE_F  # the recap ends on a fade to black and a beat of silence before the episode's own cold open
    cursor += RECAP_GAP_F
add("cold", edl["coldOpen"])
title = {**edl["title"], "from": cursor, "dur": round(TITLE_S * FPS), "bg": round((sec(edl["title"]["bg"]) - OFF) * FPS)}
cursor += title["dur"]
add("intro", edl["intro"])
intro_end = cursor
add("main", edl["main"])

def span(c):
    """Source frames a clip covers (more than its output frames when fast-forwarded)."""
    return round(c["dur"] * c.get("rate", 1))


def starts_with_speech(c):
    t = c["src"] / FPS + OFF
    return any(t <= w["start"] < t + 0.6 for w in words)


jumps = 0
for prev, c in zip(clips, clips[1:]):
    c["whoosh"] = "file" in c or "file" in prev or c["src"] - (prev["src"] + span(prev)) > SKIP_TRANSITION * FPS or c["section"] != prev["section"]
    if not c["whoosh"] and c.get("rate", 1) == 1 and prev.get("rate", 1) == 1:
        jumps += 1  # jump cut: alternate a slight punch-in so the cut reads as intended, and lead the audio in when speech opens the clip
        if jumps % 2:
            c["jump"] = True
        if starts_with_speech(c) and c["src"] >= LEAD_F:
            c["lead"] = LEAD_F


def clip_at(f_out):
    return next(c for c in clips if c["from"] <= f_out < c["from"] + c["dur"])


def frames(t, fast=True):
    """All output frames where source second t is shown (fast=False: not in fast-forwarded clips)."""
    f = (t - OFF) * FPS
    return [c["from"] + round((f - c["src"]) / c.get("rate", 1)) for c in clips if "file" not in c
            and c["src"] <= f < c["src"] + span(c) and (fast or c.get("rate", 1) <= 1)]


def place(t, snap=0.0):
    """All output frames where source second t is shown; optionally snap forward to the next clip start."""
    f = (t - OFF) * FPS
    hits = frames(t)
    if not hits and snap:
        nxt = [c for c in clips if "file" not in c and 0 < c["src"] - f <= snap * FPS]
        hits = [min(nxt, key=lambda c: c["src"])["from"]] if nxt else []
    if not hits:
        print(f"warning: {t:.1f}s is outside kept footage")
    return hits


spk_path = f"{work}/speakers.json"
spk = json.load(open(spk_path))["segments"] if os.path.exists(spk_path) else []  # co-op streams (lp.py speakers)


POV = [(sec(a), sec(b)) for a, b in edl.get("pov", [])]  # the partner's view is on screen: their game is seen, the guest rules don't apply


def guest_at(t):
    """True when the co-op partner is the one talking at VOD second t (and their game isn't on screen)."""
    return not any(a <= t < b for a, b in POV) and any(x["spk"] == "guest" and x["start"] - 0.3 <= t < x["end"] + 0.3 for x in spk)


def to_guest_at(t):
    """True when the streamer is talking to the co-op partner about the partner's game at VOD second t (nothing of it on screen)."""
    return bool(spk) and not any(a <= t < b for a, b in POV) and any(s["start"] - 0.3 <= t < s["end"] + 0.3 and not guest_at(s["start"]) and about_partner(s["text"]) for s in segments)


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
    if not ocr_effects:  # hand-placed banner: the EDL time is exact
        return t
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
    effects_lib.learn([e[:3] for e in edl["effects"]])  # new one-line descriptions go into the library for later episodes
effects = [{"at": f, "name": n, "fi": fi if fi and fi != "TODO" else (effects_lib.desc(n) if effects_lib else ""),
            **({"dur": round(secs[0] * FPS)} if secs else {})}  # optional 4th field: seconds on screen
           for t, n, fi, *secs in edl["effects"] for f in place(effect_time(sec(t), n), snap=12)]
missing = []
caption_times = [(phrase_time(sec(t), match), text) for t, match, text in edl["captions"]]
missing += [f"chapter at {t} is still a draft label: {label}" for t, label in edl["chapters"] if label.startswith("TODO")]
if edl["intro"] and edl["main"]:  # main must not go back inside the intro's span: the viewer would see those screens twice
    intro_lo, intro_hi = min(sec(x[0]) for x in edl["intro"]), max(sec(x[1]) for x in edl["intro"])
    missing += [f"main range {x[0]}–{x[1]} lies between the intro's ranges ({edl['intro'][0][0]}–{edl['intro'][-1][1]}): the episode "
                "would rewind into the intro and show that stretch twice; drop the range or move it into the intro"
                for x in edl["main"] if sec(x[0]) < intro_hi and sec(x[1]) > intro_lo]
    if sec(edl["main"][0][0]) < intro_lo:
        print(f"warning: main starts at {edl['main'][0][0]}, before the intro ({edl['intro'][0][0]}): the intro is a later explanation "
              "pulled forward, so make sure nothing before it is a menu or cutscene the viewer then sees twice")
# Co-op: the partner's gameplay isn't in this stream, so nothing is put on their lines; the edit follows the streamer.
missing += [f"caption '{txt}' is on a [GUEST] line: captions are for the streamer's own lines" for t, txt in caption_times if t is not None and guest_at(t)]
missing += [f"caption '{txt}' is the streamer talking to the partner about the partner's game ([TO GUEST]): nothing of it is on screen"
            for t, txt in caption_times if t is not None and to_guest_at(t)]
missing += [f"banner '{n}' at {t} is on a [GUEST] line" for t, n, *_ in edl["effects"] if guest_at(sec(t))]
for t, label in edl["chapters"]:
    if guest_at(sec(t)) or to_guest_at(sec(t)):
        print(f"warning: chapter '{label}' at {t} starts on the partner's talk: make sure the label names what happens in this stream")
for t in edl["faceZooms"]:
    if guest_at(sec(t)):
        print(f"warning: face zoom at {t} lands on a [GUEST] line: keep it only if the streamer's face itself is funny or strange there (look with frames)")
missing += [f"effect '{n}' has no description" for _, n, fi, *_ in edl["effects"] if not (fi and fi != "TODO") and not (effects_lib and effects_lib.desc(n))]
for k, sh in enumerate(edl.get("shorts", []), 1):
    if len(sh.get("ranges", [0])) > 2:
        missing.append(f"short {k}: at most two ranges (one internal cut)")
TAIL_S = 0.3  # Whisper's last word often ends early: a range ending within this of a word clips it
fmt_t = lambda s: f"{int(s // 60)}:{s % 60:04.1f}"
for what, rngs in [("cold open", [x[:2] for x in edl["coldOpen"]])] + [(f"short {k}", sh.get("ranges") or [[sh["from"], sh["to"]]])
                                                                        for k, sh in enumerate(edl.get("shorts", []), 1)]:
    for _, t in rngs:
        b = sec(t)
        near = [w for w in words if w["start"] - TAIL_S < b < w["end"] + TAIL_S]
        if near:
            print(f"warning: {what} ends at {t}, on or right after '{near[0]['word'].strip()}' ({fmt_t(near[0]['start'])}–{fmt_t(near[0]['end'])}): "
                  f"leave ≥ {TAIL_S} s after the last word and before the next (word ends from Whisper run early; check the audio)")
INTRO_MAX_S = 25  # RULEBOOK 5.2: about 20 s; the rest of the explanation goes into main where it is relevant
if (n := sum(sec(b) - sec(a) for a, b in edl["intro"])) > INTRO_MAX_S:
    print(f"warning: the intro's ranges run {n:.0f} s: keep it to about 20 s over action and move the rest into main where it fits (RULEBOOK 5.2)")
short_spans = [(sec(x), sec(y)) for sh in edl.get("shorts", []) for x, y in sh.get("ranges") or [[sh["from"], sh["to"]]]]
for a, b, *_ in edl["coldOpen"]:  # RULEBOOK 15.0: every cold-open hit is a Short candidate; one left out says why
    if not any(x < sec(b) and sec(a) < y for x, y in short_spans) and a not in edl.get("notShorts", {}):
        print(f"warning: cold-open hit {a}–{b} is not a Short: make it one, or give the reason in \"notShorts\" (RULEBOOK 15.0)")

# Co-op whose partner tracks (mic, cam, game) start late or end early: the streamer still talks to the partner there, so
# the viewer hears half a conversation. The episode needs a note saying so ("notes": {from}/{until} = where they start/end).
PARTNER = partner_span(edl["vod"])
shown = [c for c in clips if "file" not in c and c["section"] in ("intro", "main")]
vod_f = lambda t: (t - OFF) * FPS
mmss = lambda f: f"{int(f / FPS // 60)}:{int(f / FPS % 60):02}"
partner_at = {}  # "from" / "until": episode m:ss where the partner's tracks start / end inside this episode
if PARTNER and shown:
    a, b = vod_f(PARTNER[0]), vod_f(PARTNER[1])
    if shown[0]["src"] < a:
        after = [c for c in shown if c["src"] + c["dur"] * c.get("rate", 1) > a]
        if after:
            c = after[0]
            partner_at["from"] = mmss(c["from"] + max(0, (a - c["src"]) / c.get("rate", 1)))
    if shown[-1]["src"] + shown[-1]["dur"] * shown[-1].get("rate", 1) > b:
        before = [c for c in shown if c["src"] < b]
        if before:
            c = before[-1]
            partner_at["until"] = mmss(c["from"] + min(c["dur"], (b - c["src"]) / c.get("rate", 1)))
    gone = shown[0]["src"] < a or shown[-1]["src"] + shown[-1]["dur"] * shown[-1].get("rate", 1) > b
    if gone and not edl.get("notes"):
        where = (f"until {partner_at['from']}" if "from" in partner_at else "") + (" and " if len(partner_at) == 2 else "") + \
                (f"after {partner_at['until']}" if "until" in partner_at else "") or "in this whole episode"
        missing.append(f"the co-op partner's mic and game aren't recorded {where} (episode time), but they're in the call: add a "
                       "\"notes\" banner at the first gameplay clip saying so, e.g. [\"<time>\", \"Puhun <partner> kanssa\", "
                       "\"Hänen mikkinsä ja pelikuvansa mukana vasta {from} alkaen\", 8], and a line in the descriptions")
notes = []
for t, title_txt, body, *secs in edl.get("notes", []):
    keys = set(re.findall(r"\{(\w+)\}", title_txt + body))
    if keys - set(partner_at):
        missing.append(f"note at {t}: {', '.join('{' + k + '}' for k in sorted(keys - set(partner_at)))} has no time in this episode "
                       f"(the partner's tracks {'start/end' if PARTNER else 'are not separate tracks'} outside it)")
        continue
    for f in place(sec(t), snap=12)[:1]:
        notes.append({"at": f, "name": title_txt.format(**partner_at), "fi": body.format(**partner_at), "dur": round((secs[0] if secs else 8) * FPS)})
partner_times = lambda txt: re.sub(r"\{(from|until)\}", lambda m: partner_at.get(m.group(1), m.group(0)), txt)  # descriptions too
if missing:  # report every problem at once
    sys.exit("\n".join(missing))


def word_timing(t, at, text):
    """Caption start and each word's frame offset from it: a word appears when it is spoken (the caption starts at its
    first spoken word, up to 3 s before the matched one), else WORD_F after the previous word."""
    spoken = [w for w in words if t - 3 <= w["start"] < t + 8]
    shown = text.split()
    times = [None] * len(shown)
    m = SequenceMatcher(None, [norm(w) for w in shown], [norm(w["word"]) for w in spoken], autojunk=False)
    for i, j, n in m.get_matching_blocks():
        for k in range(n):
            times[i + k] = next((f for f in frames(spoken[j + k]["start"]) if -3 * FPS <= f - at < 8 * FPS), None)
    start = min([at] + [x for x in times if x is not None])
    out = []
    for x in times:
        out.append(max(x - start if x is not None else (out[-1] + WORD_F if out else 0), out[-1] if out else 0))
    return start, out


captions = []
for t, txt in caption_times:
    for f in place(t, snap=1):
        f, w = word_timing(t, f, txt)
        captions.append({"at": f, "text": txt, "words": w, "dur": max(CAPTION_F, w[-1] + 60)})
captions.sort(key=lambda c: c["at"])
for prev, c in zip(captions, captions[1:]):
    c["slot"] = prev.get("slot", 0) + 1 if c["at"] - prev["at"] < prev["dur"] else 0

last = clips[-1]
freeze = {"from": cursor, "dur": round(edl["endFreeze"]["seconds"] * FPS), "src": last["src"] + span(last) - 1, "text": edl["endFreeze"]["text"]}
cursor += freeze["dur"]
end = {"from": cursor, "dur": round(edl["endScreen"]["seconds"] * FPS), **{k: v for k, v in edl["endScreen"].items() if k != "seconds"}}
cursor += end["dur"]
asm = f"work/{edl['vod']}/assemble.json"
boxes = json.load(open(asm))["boxes"] if os.path.exists(asm) else {}
tracks = [{"role": r, "source": f, "box": [round(v * 1920 / meta["width"]) for v in boxes[r]], "alpha": f.endswith(".webm")}
          for r in ("guestcam", "cam") for f in (f"{edl['vod']}-ep{edl['episode']}-{r}{x}" for x in (".webm", ".mp4"))
          if r in boxes and os.path.exists(f"public/{f}")]  # your webcam drawn last, on top
lt = place(sec(edl["lowerThird"]["at"]), snap=5)[0]
# Two name tags over separate webcam tracks take turns (LetsPlay.tsx), each for the usual time.
LT_F = LOWER_THIRD_S * FPS * (2 if edl["lowerThird"].get("guest") and {"cam", "guestcam"} <= {t["role"] for t in tracks} else 1)

# Compositions are laid out at 1920x1080 and rendered at the VOD's native size, so VOD pixels map to layout units.
cam = edl["cam"] and [round(v * 1920 / meta["width"]) for v in edl["cam"]]  # null: no webcam in this stream
if not cam and edl["faceZooms"]:
    sys.exit("faceZooms need a webcam; set \"cam\" or empty the list")
face_zooms, game_zooms = zooms(edl["faceZooms"]), zooms(edl["gameZooms"])


def punches():
    """Punch-ins on the loudest sharp rises in the part's audio (screams, explosions), strongest first, kept clear of
    zooms, banners, cuts and each other."""
    a, b = int(part["start"] * 10), int(part["end"] * 10)
    thr = np.percentile(rms[a:b], 99.5)
    peaks = [i for i in range(a + 5, b - 5) if rms[i] > thr and rms[i] == rms[i - 5:i + 6].max() and rms[i] - rms[i - 5:i].min() > PUNCH_RISE_DB
             and not guest_at(i / 10)]  # no punch-ins on the co-op partner's shouting
    busy = [(z["at"] - 60, z["end"] + 30) for z in face_zooms + game_zooms] + [(e["at"] - 30, e["at"] + 90) for e in effects]
    busy += [(c["from"] - 20, c["from"] + 20) for c in clips if c.get("whoosh")] + [(title["from"] - 30, intro_end)]
    out = []
    for i in sorted(peaks, key=lambda i: -rms[i]):
        for f in frames(i / 10 - 0.1, fast=False):  # land just before the peak so the push hits with it
            if not any(x <= f < y for x, y in busy) and all(abs(f - p) >= PUNCH_SPACING_F for p in out):
                out.append(f)
    return [{"at": f} for f in sorted(out)]


# YouTube chapters: first must be 0:00, each at least 10 s apart (and editorially ~2 min). Keep the EDL index to pair English labels.
CHAPTER_MIN_S = 90
chapters = [(0, 0)]
for i, (t, label) in enumerate(edl["chapters"][1:], 1):
    f = place(sec(t), snap=30)[0] if t not in ("end",) else end["from"]
    if f / FPS - chapters[-1][0] >= 10:
        if f / FPS - chapters[-1][0] < CHAPTER_MIN_S:
            print(f"warning: chapter '{label}' at {t} comes {f / FPS - chapters[-1][0]:.0f} s after the previous one: "
                  f"a chapter is a story beat of about 2–3 min, so merge it into its neighbour (rule 11.1)")
        chapters.append((f / FPS, i))
    else:
        print(f"warning: chapter '{label}' at {t} lands at {f / FPS:.1f} s, under 10 s after the previous one, and is dropped"
              + (" (its time is inside the cold open: move it past that range)" if f < title["from"] else ""))
fmt = lambda s: f"{int(s // 60)}:{int(s % 60):02}"

# On-screen chapter cards where each chapter (after the first) starts, moved past a caption or the lower third if they
# would overlap, dropped if that takes them more than 10 s into the chapter.
cards = []
if edl.get("chapterCards", True):
    busy = [(c["at"], c["at"] + c["dur"]) for c in captions] + [(lt, lt + LT_F)] + [(n["at"], n["at"] + n["dur"]) for n in notes]
    for s, i in chapters[1:]:
        f = round(s * FPS)
        for a, b in sorted(busy):
            if a < f + CARD_S * FPS and f < b:
                f = b + 10
        if f - s * FPS <= 10 * FPS and f + CARD_S * FPS <= freeze["from"]:
            cards.append({"at": f, "dur": round(CARD_S * FPS), "n": len(cards) + 2, "label": edl["chapters"][i][1]})
        else:
            print(f"warning: no chapter card for '{edl['chapters'][i][1]}' (no free spot in its first 10 s)")

# Music bed under the main part, ducked under speech (styles.json "bed"; EDL "bed": false | true | "<track>").
bed_track = edl.get("bed", True)
bed_track = (style.get("bed") if bed_track is True else bed_track) or None
bed = None
if bed_track:
    talk = merge([[c["from"] + (w["start"] - OFF - c["src"] / FPS) * FPS / c.get("rate", 1) - TALK_PAD * FPS,
                   c["from"] + (w["end"] - OFF - c["src"] / FPS) * FPS / c.get("rate", 1) + TALK_PAD * FPS]
                  for w in words for c in clips if "file" not in c and c["src"] <= (w["start"] - OFF) * FPS < c["src"] + span(c)], TALK_GAP * FPS)
    bed = {"track": bed_track, "talk": [[round(a), round(b)] for a, b in talk]}

pov = [[round((sec(a) - OFF) * FPS), round((sec(b) - OFF) * FPS)] for a, b in edl.get("pov", [])]  # co-op: the partner's view
guest_src = f"{edl['vod']}-ep{edl['episode']}-guest.mp4"
if pov and not os.path.exists(f"public/{guest_src}"):
    sys.exit(f"\"pov\" needs the partner's view: public/{guest_src} (assemble with --guest-game, then lp.py prep)")
if bad := [r for r, (a, b) in zip(edl.get("pov", []), pov) if not 0 <= a < b <= (part["prepEnd"] - OFF) * FPS]:
    sys.exit(f"\"pov\" spans outside this episode's footage or reversed: {bad}")
POV_SLIVER_S = 1.0  # a view switch this close to a range edge flashes the other view for a moment before the cut
if slivers := [f"pov edge {t} lies {min(sec(t) - sec(a), sec(b) - sec(t)):.1f} s inside the range {a}–{b}: the other view "
               "flashes up before the cut; move the edge onto or past the range edge"
               for t in [x for span in edl.get("pov", []) for x in span] for a, b, *_ in edl["coldOpen"] + edl["intro"] + edl["main"]
               if 0 < sec(t) - sec(a) < POV_SLIVER_S or 0 < sec(b) - sec(t) < POV_SLIVER_S]:
    sys.exit("\n".join(slivers))
# Separate recordings (assemble): the webcams are their own tracks (prep), drawn over the game at their boxes.
out = {"fps": FPS, "duration": cursor, "tracks": tracks or None, "guest": {"source": guest_src, "pov": pov} if pov else None, "source": f"{edl['vod']}-ep{edl['episode']}.mp4", "cam": cam,
       "style": edl.get("style", "hype"), "clips": clips, "xfade": XFADE_F, "title": title, "introEnd": intro_end,
       "freeze": freeze, "end": end, "lowerThird": {**edl["lowerThird"], "from": lt, "dur": LT_F},
       "effects": effects, "notes": notes, "captions": captions, "faceZooms": face_zooms, "gameZooms": game_zooms,
       "punches": punches(), "cards": cards, "bed": bed,
       "recap": {"text": text("previously"), "sub": text("episode", n=edl["episode"] - 1)} if recap else None,
       "text": {"effect_label": EFFECT_LABEL, "note_label": CFG["text"].get("note", "NOTE"), "next_episode": text("next_episode" if edl["episode"] < len(parts) else "watch_next"),
                "playlist": text("playlist"), "chapter": CFG["text"]["chapter"]}}
th = edl["thumb"]
thumb = {**th, "bg": round((sec(th["bg"]) - OFF) * FPS), "face": th.get("face") and round((sec(th["face"]) - OFF) * FPS)}
json.dump({"edit": out, "thumb": thumb}, open(f"{work}/ep{edl['episode']}.props.json", "w"), ensure_ascii=False)

def credit_lines(tr):
    """Music and sound credits in the channel's language (tr=text) or the translation language (tr=translation_text)."""
    songs = f" {tr('and')} ".join(f'"{m}"' for m in style["music"] + ([style["bedTitle"]] if bed and style.get("bedTitle") else []))
    return "\n".join([tr("music", songs=songs), tr("license"), tr("sfx")])


credits = (edl.get("credits") or credit_lines(text)).strip()


def description(text, labels, credit):
    return text.strip() + "\n\n" + "\n".join(f"{fmt(s)} {labels[i]}" for s, i in chapters) + "\n\n" + credit + "\n"


OUT = out_dir(edl)
os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/{edl['output']}.description.txt", "w") as fh:
    fh.write(description(partner_times(edl["description"]), [l for _, l in edl["chapters"]], credits))
# Title/description in the translation language (config "translation", e.g. "en") for YouTube localizations; the EDL's
# "<lang>.chapters" lists labels in the EDL's chapter order.
TR = CFG.get("translation")
if TR and TR in edl:
    tr = edl[TR]
    assert len(tr["chapters"]) == len(edl["chapters"]), f"{TR}.chapters must match chapters one to one"
    json.dump({"title": tr["title"], "description": description(partner_times(tr["description"]), tr["chapters"], credit_lines(translation_text))},
              open(f"{OUT}/{edl['output']}.{TR}.json", "w"), ensure_ascii=False, indent=1)


def srt_time(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


# Subtitles (commentary language) on the edited timeline: every transcript word shown in a clip, grouped into short cues.
CUE_GAP, CUE_CHARS, CUE_S, LINE = 0.7, 84, 5.0, 42
shown = sorted(((c["from"] / FPS + (w["start"] - OFF - c["src"] / FPS) / c.get("rate", 1), (w["end"] - w["start"]) / c.get("rate", 1), w["word"].strip(), w)
                for w in said for c in clips if "file" not in c and c.get("rate", 1) <= 1 and c["src"] <= (w["start"] - OFF) * FPS and (w["end"] - OFF) * FPS <= c["src"] + span(c)),
               key=lambda x: x[0])
cues = []
for t, d, text, w in shown:
    cur = cues[-1] if cues else None
    if (not cur or t - cur[1] > CUE_GAP or len(cur[2]) + len(text) > CUE_CHARS or t + d - cur[0] > CUE_S
            or cur[2][-1:] in ".?!"):
        cues.append([t, t + d, text, [w]])
    else:
        cur[1], cur[2] = t + d, cur[2] + " " + text
        cur[3].append(w)
# The cues with their VOD words (time, Whisper confidence) for `proof`'s suspect list.
json.dump([{"n": n, "at": a, "text": text, "words": ws} for n, (a, _, text, ws) in enumerate(cues, 1)],
          open(f"{work}/ep{edl['episode']}.subs.json", "w"), ensure_ascii=False)


def wrap(text):
    if len(text) <= LINE:
        return text
    cut = min((i for i, ch in enumerate(text) if ch == " "), key=lambda i: abs(i - len(text) / 2))
    return text[:cut] + "\n" + text[cut + 1:]


SRT = f"{OUT}/{edl['output']}.{CFG['language']}.srt"
if not CFG.get("subtitles", True):  # config "subtitles": false: the channel publishes no subtitle track
    if os.path.exists(SRT):
        os.remove(SRT)
else:
    with open(SRT, "w") as fh:
        nxt = [c[0] for c in cues[1:]] + [cursor / FPS]  # hold short cues for 1 s, but never into the next one
        fh.writelines(f"{n}\n{srt_time(a)} --> {srt_time(min(max(b, a + 1.0), z))}\n{wrap(text)}\n\n"
                      for n, ((a, b, text, _), z) in enumerate(zip(cues, nxt), 1))

print(f"{len(clips)} clips (<2s: {sum(c['dur'] < 120 for c in clips)}), {cursor / FPS / 60:.1f} min total, "
      f"effects={len(effects)} captions={len(captions)} faceZooms={len(face_zooms)} gameZooms={len(game_zooms)} punches={len(out['punches'])} "
      f"chapters={len(chapters)} cards={len(cards)} bed={bed_track or 'off'}" + (f" recap={len(recap)} ranges" if recap else ""))
