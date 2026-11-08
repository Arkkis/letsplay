"""Let's play pipeline driver. Every step is resumable: outputs that already exist are kept.

  lp.py assemble <slug> --game G.mp4 [--cam C] [--guest-cam C] [--guest-game G] (--kdenlive P | --offset role=m:ss ...)
                                                separate gameplay/webcam recordings (yours and a co-op partner's), aligned in
                                                Kdenlive, → one VOD footage/<slug>.mp4 + per-mic loudness for speakers
  lp.py ingest <vod.mp4> [--slug S] [--game G]  copy VOD, transcribe, loudness map, language per 10 s (+ game module,
                                                e.g. --game chaosmod: GTA V Chaos Mod effect OCR)
  lp.py split <slug> [--target 25] [--parts N]  split into episodes of ~target edited minutes at speech gaps → work/<slug>/parts.json
  lp.py speakers <slug> [--host B --guest B]    co-op stream with two webcams: who says each line (B = x,y,w,h lower-face box;
                                                an assembled VOD needs no boxes: its two mics tell)
  lp.py context <slug> <ep>                     transcript + effects + English stretches + loud moments, for writing the EDL
  lp.py draft <slug> <ep> [--force]             first-pass EDL: ranges without cutscenes, effects with names, chapters, metadata
  lp.py faces <slug> <ep>                       contact sheet of the episode's liveliest webcam moments (thumbnail face)
  lp.py frames <slug> <t> [<t> ...]             contact sheet of VOD frames at the given times
  lp.py prep <slug> <ep|all>                    graded episode source at native resolution → public/<slug>-ep<ep>.mp4
                                                (assembled: one file per track, webcams cut out when assembled --cutout)
  lp.py see <edits/x.json>                      frame check by a local vision model (Ollama): what each chapter span, caption,
                                                cold-open hit, Short and the thumbnail show, and whether the label names it
  lp.py check <edits/x.json>                    build the timeline and render a grid of check stills
  lp.py script <edits/x.json>                   the finished edit as a timed script (speech, cuts, captions, banners) to review
  lp.py shorts <edits/x.json>                   (re)render the EDL's Shorts → out/<playlist>/shorts/ (a full render does this too)
  lp.py render <edits/x.json> [--patch [R]]     build, render, master to −14 LUFS, thumbnail → out/<playlist>/<output>.{mp4,jpg,description.txt}
                                                --patch: re-render only changed parts and splice them into the existing mp4
  lp.py stats <session-id>                      token use, wall time and tool activity of a Claude Code session
  lp.py publish <edits/x.json> [--at ISO|--now] wait for the user's Studio upload, then apply details, subtitles, playlist;
                                                schedule/publish only with an explicit --at/--now (the user's go)
  lp.py retention <edits/x.json>                YouTube audience retention of the published episode mapped onto the script
  lp.py look <edits/x.json> [m:ss ...] [--short K] [--last S]   frames of the rendered episode or Short → work/<vod>/epN-look.png
  lp.py at <edits/x.json> <m:ss> ... [--vod]    episode time ↔ VOD time, with the line said there
"""
import argparse, json, os, re, shutil, subprocess, sys, time, wave
_VENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv")
_VPY = os.path.join(_VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(_VENV, "bin", "python")
if os.path.exists(_VPY) and os.path.realpath(sys.prefix) != os.path.realpath(_VENV):  # run with the wrong Python: Whisper and its CUDA wheels live in .venv
    os.execv(_VPY, [_VPY, *sys.argv])
from difflib import SequenceMatcher
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from media import GRADE, partner_span, video_encoder
from trimming import MOTION_FPS, fix_words, loud_db, merge, motion_thr, real_words, trim
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import CFG, about_partner, out_dir, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
PY = sys.executable  # the venv's interpreter: the driver is run as .venv/bin/python (Linux, macOS) or .venv\Scripts\python (Windows)
TMP = f"{ROOT}/.tmp"  # Remotion copies public/ into TMPDIR; /tmp is a small RAM disk
PREP_BEFORE, PREP_AFTER = 5, 15  # source margin around an episode, seconds
LOUD_DB = -20
EDIT_RATIO = CFG.get("edit_ratio", 0.87)  # finished episode length / auto-trimmed length (0.87 measured on a GTA V stream)
CONCURRENCY = max(1, (os.cpu_count() or 2) // 2)
GAMES = ("chaosmod",)


def game_lib(slug):
    """The game module's effect library for a VOD ingested with --game chaosmod, else None."""
    if meta(slug).get("game") != "chaosmod":
        return None
    from games.chaosmod import effects_lib
    return effects_lib


def gpu_env():
    """CUDA libraries shipped as pip wheels (nvidia-cublas/cudnn) for faster-whisper, when present."""
    import glob
    if os.name == "nt":  # Windows wheels put the DLLs in nvidia/*/bin and load them through PATH
        key = next((k for k in os.environ if k.upper() == "PATH"), "PATH")
        libs = glob.glob(f"{sys.prefix}/Lib/site-packages/nvidia/*/bin")
        return {key: os.pathsep.join(libs + [os.environ.get(key, "")])} if libs else {}
    libs = glob.glob(f"{sys.prefix}/lib/python3*/site-packages/nvidia/*/lib")
    return {"LD_LIBRARY_PATH": ":".join(libs + [os.environ.get("LD_LIBRARY_PATH", "")])} if libs else {}


TILE_W = 480  # contact-sheet tile width: readable, and small images keep a session's context (and cost) down
SPLIT_WINDOW, MIN_PAUSE = 6 * 60, 3.0  # a cut lands in the nearest pause of MIN_PAUSE s within the window


def run(*cmd, env=None):
    print("$", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), check=True, env={**os.environ, **(env or {})})


def probe_duration(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]))


def probe_size(path):
    """Width and height; graphics are laid out at 1920x1080 and rendered at the VOD's own size, so it must be 16:9."""
    w, h = map(int, subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                             "stream=width,height", "-of", "csv=p=0", path], text=True).strip().split(","))
    if abs(w / h - 16 / 9) > 0.01:
        sys.exit(f"{path} is {w}x{h}; only 16:9 VODs are supported")
    return w, h


def meta(slug):
    return json.load(open(f"work/{slug}/meta.json"))


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def slug_of(path):
    """VOD file name → slug, via config vod_name_pattern (groups m, d, y, title):
    '[1-31-24] Name - Example Game.mp4' → 'example-game-2024-01-31'. Unmatched names use the whole file name."""
    name = os.path.splitext(os.path.basename(path))[0]
    m = re.match(CFG.get("vod_name_pattern", "(?!)"), name)
    y = m and (int(m["y"]) + 2000 if int(m["y"]) < 100 else int(m["y"]))
    title, date = (m["title"], f"{y}-{int(m['m']):02}-{int(m['d']):02}") if m else (name, "")
    title = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{title}-{date}".strip("-")


def cam_rect(slug):
    """The webcam rect: where `assemble` put yours, else config "cam"."""
    p = f"work/{slug}/assemble.json"
    return json.load(open(p))["boxes"].get("cam") if os.path.exists(p) else CFG.get("cam")


def ingest(a):
    slug = a.slug or slug_of(a.vod)
    w, vod = f"work/{slug}", f"footage/{slug}.mp4"
    os.makedirs(w, exist_ok=True)
    if not os.path.exists(vod):
        shutil.copyfile(a.vod, vod)
    (width, height), dur = probe_size(vod), probe_duration(vod)
    game = a.game or ("chaosmod" if a.chaos else None) or (json.load(open(f"{w}/meta.json")).get("game") if os.path.exists(f"{w}/meta.json") else None)
    json.dump({"width": width, "height": height, "duration": dur, "game": game}, open(f"{w}/meta.json", "w"))
    if not os.path.exists(f"{w}/audio16k.wav"):
        run("ffmpeg", "-nostdin", "-v", "error", "-i", vod, "-vn", "-ac", "1", "-ar", "16000", f"{w}/audio16k.wav")
    if not os.path.exists(f"{w}/transcript.json"):
        run(PY, "scripts/transcribe.py", f"{w}/audio16k.wav", f"{w}/transcript.json", CFG["language"], env=gpu_env())
    if not os.path.exists(f"{w}/rms100ms.npy"):
        wf = wave.open(f"{w}/audio16k.wav")
        x = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
        b = wf.getframerate() // 10
        x = x[:len(x) // b * b].reshape(-1, b)
        np.save(f"{w}/rms100ms.npy", 20 * np.log10(np.sqrt((x ** 2).mean(1)) + 1e-9))
    if not os.path.exists(f"{w}/lang10s.json"):
        run(PY, "scripts/langid.py", f"{w}/audio16k.wav", f"{w}/lang10s.json", env=gpu_env())
    if not os.path.exists(f"{w}/events.json"):  # laughs, screams, bangs: what the transcript can't show
        run(PY, "scripts/audio_events.py", f"{w}/audio16k.wav", f"{w}/events.json")
    if not os.path.exists(f"{w}/motion.npz"):  # visual action in the game and liveliness in the webcam (config "cam")
        run(PY, "scripts/motion.py", slug, ",".join(map(str, cam_rect(slug) or [])))
    if game == "chaosmod" and not os.path.exists(f"{w}/effects.json"):
        game_lib(slug)  # fails early with instructions if the effect name list hasn't been built yet
        run(PY, "games/chaosmod/ocr_effects.py", vod, 0, dur, f"{w}/effects.json")
    print(f"ingested {slug}: {dur / 60:.0f} min")


def events(slug, lo=0, hi=1e9):
    """Audio events [[start, end, kind, score], ...] in lo–hi from audio_events.py ([] before an ingest made them)."""
    path = f"work/{slug}/events.json"
    return [e for e in json.load(open(path)) if lo <= e[0] < hi] if os.path.exists(path) else []


def motion(slug):
    """(game motion, face motion) arrays at MOTION_FPS from motion.py, or (None, None)."""
    path = f"work/{slug}/motion.npz"
    if not os.path.exists(path):
        return None, None
    m = np.load(path)
    return m["game"], (m["face"] if len(m["face"]) else None)


def game_motion(slug, lo, hi):
    """trim()'s motion argument for the range: (array, threshold) or None."""
    g, _ = motion(slug)
    return (g, motion_thr(g, lo, hi)) if g is not None else None


def split(a):
    """Cut where the auto-trimmed running time reaches each episode's share, snapped to a speech pause nearby."""
    w = f"work/{a.slug}"
    dur = meta(a.slug)["duration"]
    S = json.load(open(f"{w}/transcript.json"))["segments"]
    words = [x for s in S for x in s["words"]]
    rms = np.load(f"{w}/rms100ms.npy")
    kept = np.zeros(int(dur) + 1)
    for x, y in trim(words, rms, 0, dur, loud_db(rms, 0, dur), game_motion(a.slug, 0, dur), events(a.slug)):
        kept[int(x):int(y)] += 1
    cum = np.cumsum(kept)
    n = a.parts or max(1, round(cum[-1] * EDIT_RATIO / (a.target * 60)))
    gaps = [(S[i + 1]["start"] - S[i]["end"], (S[i]["end"] + S[i + 1]["start"]) / 2) for i in range(len(S) - 1)]
    cuts = [0.0]
    for k in range(1, n):
        target = float(np.searchsorted(cum, k * cum[-1] / n))
        near = [g for g in gaps if abs(g[1] - target) < SPLIT_WINDOW] or [(0, target)]
        pauses = [g for g in near if g[0] >= MIN_PAUSE]  # nearest real pause, else the longest gap in the window
        cuts.append(round(min(pauses, key=lambda g: abs(g[1] - target))[1] if pauses else max(near)[1], 2))
    cuts.append(dur)
    parts = [{"part": i, "start": x, "end": y, "prepStart": max(0.0, x - PREP_BEFORE), "prepEnd": min(dur, y + PREP_AFTER)}
             for i, (x, y) in enumerate(zip(cuts, cuts[1:]), 1)]
    json.dump(parts, open(f"{w}/parts.json", "w"), indent=1)
    for p in parts:
        k = cum[int(p["end"]) - 1] - (cum[int(p["start"]) - 1] if p["start"] else 0)
        print(f"episode {p['part']}: {fmt(p['start'])}–{fmt(p['end'])} raw {(p['end'] - p['start']) / 60:.0f} min, "
              f"≈{k * EDIT_RATIO / 60:.0f} min edited")


def part(slug, ep):
    return json.load(open(f"work/{slug}/parts.json"))[ep - 1]


FOREIGN_RUN = 3  # consecutive 10 s windows in another language than the commentary: a cutscene or mission dialogue


def effect_events(slug, lo, hi):
    """(time, real effect name) for each activation in [lo, hi): OCR spellings mapped to mod names, junk dropped,
    one entry per effect per 90 s."""
    lib = game_lib(slug)
    if not lib or not os.path.exists(f"work/{slug}/effects.json"):
        return []
    out, last = [], {}
    for t, ocr in json.load(open(f"work/{slug}/effects.json")):
        name = lo <= t < hi and lib.canonical(ocr)
        if name and t - last.get(name, -999) > 90:
            out.append((t, name))
        if name:
            last[name] = t
    return out


def lang_windows(slug):
    """[(t, {language: probability})] per 10 s window (older files store [t, en, fi])."""
    rows = json.load(open(f"work/{slug}/lang10s.json"))
    return [(r[0], r[1] if isinstance(r[1], dict) else {"en": r[1], "fi": r[2]}) for r in rows]


def foreign_runs(slug, lo, hi):
    """Stretches where another language than the commentary's dominates (story cutscenes, mission dialogue):
    [start, end, language] in VOD seconds."""
    if not os.path.exists(f"work/{slug}/lang10s.json"):
        return []
    own, runs, cur = CFG["language"], [], []
    for t, probs in lang_windows(slug) + [(1e9, {})]:
        other = max(((p, l) for l, p in probs.items() if l != own), default=(0, ""))
        if lo - 10 < t < hi and probs.get(own, 0) < 0.3 and other[0] > 0.5:
            cur.append((t, other[1]))
            continue
        if len(cur) >= FOREIGN_RUN:
            runs.append([max(lo, cur[0][0]), min(hi, cur[-1][0] + 10), max(set(l for _, l in cur), key=[l for _, l in cur].count)])
        cur = []
    return runs


def repeat_runs(segments):
    """Whisper hallucination loops: a long line 3+ times, or any line 6+ times, within a minute. Short real repeats
    ("Mä pääsen. Mä pääsen.") don't count."""
    runs = []
    for i, s in enumerate(segments):
        same = [x for x in segments[i:i + 15] if x["text"] == s["text"] and x["start"] - s["start"] < 60]
        if len(same) >= 6 or (len(same) >= 3 and len(s["text"]) >= 25):
            runs.append([s["start"], same[-1]["end"]])
    return merge(runs, 5)


def context(a):
    w, p = f"work/{a.slug}", part(a.slug, a.ep)
    lo, hi = p["start"], p["end"]
    segments = [s for s in json.load(open(f"{w}/transcript.json"))["segments"] if lo <= s["start"] < hi]
    spk = speakers(a.slug)
    talk = []  # speech merged into utterances (same speaker, < 1 s apart); the end time is where a cut after it can go
    for x in segments:
        who = spk.get(x["start"], "host")
        if talk and x["start"] - talk[-1][1] < 1.0 and who == talk[-1][3]:
            talk[-1][1:3] = [x["end"], talk[-1][2] + " " + x["text"]]
        else:
            talk.append([x["start"], x["end"], x["text"], who])
    mark = {"host": "", "guest": "[GUEST] ", "?": "[?] "}
    rows = [(x, f"–{fmt(y)} {mark[who]}{'[TO GUEST] ' if spk and who == 'host' and about_partner(text) else ''}{text}") for x, y, text, who in talk]
    lib = game_lib(a.slug)
    rows += [(t, f"[EFFECT] {n} — {lib.desc(n) or '(no description yet)'}") for t, n in effect_events(a.slug, lo, hi)]
    rows += [(x, f"[{lang.upper()} {fmt(x)}–{fmt(y)}] cutscene or mission dialogue; transcript lines here are unreliable")
             for x, y, lang in foreign_runs(a.slug, lo, hi)]
    if (sp := partner_span(a.slug)) and (sp[0] > lo or sp[1] < hi):  # partner in the call, but not on tape
        rows += [(x, f"[NO PARTNER TRACKS {fmt(x)}–{fmt(y)}] the co-op partner's mic, cam and game weren't recorded here, but "
                     "they're in the call: the streamer's lines may answer someone the viewer can't hear, there are no [GUEST] "
                     "lines, and the episode needs a \"notes\" banner saying so")
                 for x, y in ((lo, min(hi, sp[0])), (max(lo, sp[1]), hi)) if y > x]
    rows += [(x, f"[REPEATS {fmt(x)}–{fmt(y)}] transcript loops here: hallucinated, not what was said") for x, y in repeat_runs(segments)]
    rms = np.load(f"{w}/rms100ms.npy")
    loud = [[t, t + 5, rms[t * 10:(t + 5) * 10].max(initial=-99)] for t in range(int(lo), int(hi), 5)]
    loud = [x for x in loud if x[2] > LOUD_DB]
    for x, y in merge([x[:2] for x in loud], 0.1):  # loud game moments, merged into stretches
        rows.append((x, f"[LOUD {fmt(x)}–{fmt(y)} peak {max(p for a, b, p in loud if x <= a < y):.0f} dB]"))
    rows += [(x, f"[{kind.upper()} {fmt(x)}–{fmt(y)}]") for x, y, kind, _ in events(a.slug, lo, hi)]
    rows += [(x, f"[ACTION {fmt(x)}–{fmt(y)}]") for x, y in action_runs(a.slug, lo, hi)]
    rows += [(x, f"[FACE {fmt(x)}–{fmt(y)}]") for x, y in face_runs(a.slug, lo, hi)]
    out = f"{w}/ep{a.ep}.context.txt"
    with open(out, "w") as fh:
        fh.write(f"# episode {a.ep}: VOD {fmt(lo)}–{fmt(hi)} ({(hi - lo) / 60:.1f} min raw). Times are VOD m:ss; speech lines "
                 "show start –end. [EFFECT] lists what OCR read; effects it missed (flipped/hidden HUD) are still on the vote "
                 "list in `frames` — look names up in games/chaosmod/names.json. [LAUGH] [SCREAM] [BANG] are heard, not "
                 "transcribed; [ACTION] is heavy on-screen motion; [FACE] the webcam's liveliest moments (reactions)."
                 + (" [GUEST] lines are the co-op partner talking (their gameplay is not in this stream), [?] unclear, "
                    "[TO GUEST] the streamer talking to the partner about the partner's game: nothing of it is on screen."
                    if spk else "") + "\n")
        fh.writelines(f"{fmt(t)} {txt}\n" for t, txt in sorted(rows))
    print(out, len(rows), "lines")


def action_runs(slug, lo, hi):
    """Stretches of heavy game motion (above the range's 95th percentile), ≥ 2 s, merged over 1 s gaps."""
    g, _ = motion(slug)
    if g is None:
        return []
    thr = motion_thr(g, lo, hi)
    hits = [i / MOTION_FPS for i in np.nonzero(g[int(lo * MOTION_FPS):int(hi * MOTION_FPS)] > thr)[0]]
    return [[x, y] for x, y in merge([[lo + t, lo + t + 1 / MOTION_FPS] for t in hits], 1.0) if y - x >= 2]


FACE_WINDOWS = 20  # [FACE] lines per episode: the webcam's liveliest 2 s windows


def face_runs(slug, lo, hi):
    _, f = motion(slug)
    if f is None:
        return []
    n = 2 * MOTION_FPS
    win = [(f[i:i + n].mean(), i / MOTION_FPS) for i in range(int(lo * MOTION_FPS), int(hi * MOTION_FPS) - n, n)]
    top = sorted(t for _, t in sorted(win, reverse=True)[:FACE_WINDOWS])
    return merge([[t, t + 2] for t in top], 0.1)


def speakers(slug):
    """Transcript segment start → "host" / "guest" / "?" from `lp.py speakers`; {} for single-streamer VODs."""
    path = f"work/{slug}/speakers.json"
    return {x["start"]: x["spk"] for x in json.load(open(path))["segments"]} if os.path.exists(path) else {}


def guest_share(slug, a, b):
    """Share of the talking in VOD a–b done by the co-op guest (by duration)."""
    path = f"work/{slug}/speakers.json"
    if not os.path.exists(path):
        return 0.0
    segs = [x for x in json.load(open(path))["segments"] if a <= x["start"] < b and x["spk"] != "?"]
    total = sum(x["end"] - x["start"] for x in segs)
    return sum(x["end"] - x["start"] for x in segs if x["spk"] == "guest") / total if total else 0.0


def speakers_cmd(a):
    if not (a.host and a.guest) and not os.path.exists(f"work/{a.slug}/mics.npz"):
        sys.exit("give --host and --guest lower-face boxes (only a VOD built by `assemble` has separate mics)")
    run(PY, "scripts/speakers.py", a.slug, *([a.host, a.guest] if a.host and a.guest else []))


def sibling_edl(slug, ep):
    """The nearest other episode's EDL of the same VOD, to copy series metadata from."""
    edls = [json.load(open(f"edits/{f}")) for f in os.listdir("edits") if f.endswith(".json")]
    eps = sorted(((abs(e["episode"] - ep), e["episode"]), e) for e in edls if e.get("vod") == slug and e["episode"] != ep)
    return eps[0][1] if eps else None


def partner_note(slug, lo, hi, at):
    """{"notes": [...]} when the co-op partner's tracks start late or end early inside VOD lo–hi: they're in the call but the
    viewer can't hear or see them there ({from}/{until} become episode times at build). {} otherwise."""
    sp = partner_span(slug)
    if not sp or (sp[0] <= lo and hi <= sp[1]):
        return {}
    ph = {"from": "{from}", "until": "{until}"}
    body = (text("partner_note_none") if sp[1] <= lo or hi <= sp[0] else
            ", ".join(text(k, **ph) for k, on in (("partner_note_from", sp[0] > lo), ("partner_note_until", sp[1] < hi)) if on))
    return {"notes": [[fmt(at), text("partner_note"), body, 8]]}


def draft(a):
    """First-pass EDL to curate: everything mechanical filled in, everything editorial marked TODO."""
    path = f"edits/{a.slug}-ep{a.ep}.json"
    if os.path.exists(path) and not a.force:
        sys.exit(f"{path} exists (use --force to overwrite)")
    w, p, n_parts = f"work/{a.slug}", part(a.slug, a.ep), len(json.load(open(f"work/{a.slug}/parts.json")))
    lo, hi = p["start"], p["end"]
    segments = json.load(open(f"{w}/transcript.json"))["segments"]
    words = [x for s in segments for x in s["words"]]
    rms = np.load(f"{w}/rms100ms.npy")
    skip = [r[:2] for r in foreign_runs(a.slug, lo, hi)] + repeat_runs([s for s in segments if lo <= s["start"] < hi])
    ev = events(a.slug, lo, hi)
    kept = [k for k in trim(words, rms, lo, hi, loud_db(rms, lo, hi), game_motion(a.slug, lo, hi), ev)
            if not any(x < k[1] and k[0] < y for x, y in skip)]
    blocks = [b for b in merge(kept, 8.0) if b[1] - b[0] >= 4]
    # intro: the first ~45 s of talk; cold open candidates: the liveliest moments later on (loudness while talking,
    # laughs and screams heard, action on screen, the webcam moving)
    intro, rest = [], []
    for b in blocks:
        (intro if sum(y - x for x, y in intro) < 40 and b[0] < lo + 120 else rest).append(b)
    g, f = motion(a.slug)
    W = 8
    def liveliness(t):
        talk = any(w["start"] < t + W and w["end"] > t for w in words if t - 1 < w["start"] < t + W + 1)
        score = rms[int(t * 10):int((t + W) * 10)].mean() + (10 if talk else -50)
        score += sum({"laugh": 15, "scream": 10, "bang": 3}[k] * s for x, y, k, s in ev if t <= x < t + W)
        if g is not None:
            score += 4 * (g[int(t * MOTION_FPS):int((t + W) * MOTION_FPS)].mean() / (np.median(g[int(lo * MOTION_FPS):int(hi * MOTION_FPS)]) + 1e-6) - 1)
        if f is not None:
            score += 3 * (f[int(t * MOTION_FPS):int((t + W) * MOTION_FPS)].mean() / (np.median(f[int(lo * MOTION_FPS):int(hi * MOTION_FPS)]) + 1e-6) - 1)
        return score
    cands = sorted((t for b in rest if b[0] > lo + 180 for t in np.arange(b[0], b[1] - W, 2.0)), key=liveliness, reverse=True)
    picks = []
    for t in cands:
        if all(abs(t - u) >= 60 for u in picks):
            picks.append(float(t))
        if len(picks) == 8:
            break
    cold = sorted(picks[:3]) or [rest[0][0]]
    effects, last_t = [], -99
    for t, name in effect_events(a.slug, lo, hi):
        if t - last_t >= 4 and any(x - 2 <= t < y for x, y in rest):
            effects.append([fmt(t), name, game_lib(a.slug).desc(name) or "TODO"])
            last_t = t
    chapters, last_c = [["0:00", "Intro"]], -999
    for t, name, _ in effects:
        tt = sum(float(v) * 60 ** i for i, v in enumerate(reversed(t.split(":"))))
        if tt - last_c >= 90:  # a candidate only: the editor moves it to where the story beat starts and names it
            chapters.append([t, f"TODO (near {name})"])
            last_c = tt
    sib = sibling_edl(a.slug, a.ep) or {}
    copy = lambda k, d: json.loads(json.dumps(sib.get(k, d)))
    title = copy("title", {"kicker": "TODO", "title": "TODO", "tagline": "TODO"})
    title.update(episode=text("episode", n=a.ep), bg=fmt(cold[0]))
    thumb = copy("thumb", {"bgZoom": 1.2, "bgOrigin": "60% 50%", "tag": "TODO"})
    thumb.update(bg=fmt(cold[0]), face=fmt(cold[0]), tag=re.sub(r"#\d+", f"#{a.ep}", thumb.get("tag", "TODO")), text="TODO")
    output = re.sub(r"\d+$", str(a.ep), sib["output"]) if sib.get("output") else text("episode_title", series="TODO", n=a.ep)
    e = {"vod": a.slug, "episode": a.ep, "output": output, "style": sib.get("style", "hype"),
         "playlist": sib.get("playlist", "TODO"), "tags": sib.get("tags", []),
         "cam": sib.get("cam", cam_rect(a.slug)), "thumb": thumb, "title": title,
         "lowerThird": {**copy("lowerThird", {"text": CFG["channel"], "sub": "TODO"}), "at": fmt(rest[0][0] + 3)},
         **({"recap": "auto"} if a.ep > 1 else {}),
         "coldOpen": [[fmt(t), fmt(t + 6), "full"] for t in cold], "intro": [[fmt(x), fmt(y)] for x, y in intro],
         "main": [[fmt(x), fmt(y)] for x, y in rest], **(partner_note(a.slug, blocks[0][0], blocks[-1][1], rest[0][0] + 1 if rest else blocks[0][0]) if blocks else {}), "effects": effects, "captions": [], "faceZooms": [], "gameZooms": [],
         "chapters": chapters, "endFreeze": {"text": text("to_be_continued") if a.ep < n_parts else text("the_end"), "seconds": 2.5},
         "endScreen": {"seconds": 15, "title": text("coming_next", n=a.ep + 1) if a.ep < n_parts else text("thanks"),
                       "cta": text("subscribe")},
         "shorts": [], "description": "TODO", "en": {"title": "TODO", "description": "TODO", "chapters": ["TODO"] * len(chapters)}}
    json.dump(e, open(path, "w"), indent=1, ensure_ascii=False)
    raw = sum(y - x for x, y in kept if x >= rest[0][0]) if rest else 0
    # contact sheet of the decision points: the liveliest moments (cold open / Shorts candidates) and chapter candidates
    sheet_file = sheet(a.slug, [fmt(t + 2) for t in picks] + [t for t, _ in chapters[1:11]], f"work/{a.slug}/ep{a.ep}-draft.jpg")
    print(f"{path}: {len(rest)} main ranges (~{raw * EDIT_RATIO / 60:.0f} min after trimming), {len(effects)} effects "
          f"({sum(x[2] == 'TODO' for x in effects)} need a description), {len(chapters)} chapters, "
          f"{len(skip)} English/hallucinated stretches left out. TODO: cut weak ranges, captions, zooms, chapter labels, "
          "thumbnail, title/description.\n"
          f"liveliest moments (cold open montage = first 3; Shorts candidates): {', '.join(fmt(t) for t in picks)}\n"
          f"{sheet_file}: those moments, then the chapter candidates")


def script(a):
    """The finished edit as a timed script, for reviewing it the way a viewer meets it: kept speech per clip in output
    time, jump cuts and whoosh transitions, captions, banners, zooms, chapters. Written to work/<vod>/epN.script.txt."""
    edl, e = build(a.edl)
    fps, w = e["fps"], f"work/{edl['vod']}"
    off = part(edl["vod"], edl["episode"])["prepStart"]
    segments, spk = json.load(open(f"{w}/transcript.json"))["segments"], speakers(edl["vod"])
    rows = []
    for c in e["clips"]:
        if "file" in c:  # recap: cut from another episode's footage
            rows.append((c["from"], f"~~ whoosh ~~ [recap {c['dur'] / fps:.0f} s from {c['file']}]"))
            continue
        a0, a1 = c["src"] / fps + off, (c["src"] + c["dur"] * c.get("rate", 1)) / fps + off
        said = " ".join(("[GUEST] " if spk.get(s["start"]) == "guest" else "") + " ".join(x["word"].strip() for x in s["words"] if a0 <= x["start"] < a1)
                        for s in segments if any(a0 <= x["start"] < a1 for x in s["words"]))
        cut = ("~~ whoosh ~~ " if c.get("whoosh") else "| ") + (f"(x{c['rate']:g}) " if "rate" in c else "")
        rows.append((c["from"], f"{cut}[{c['section']} {fmt(a0)}] {said}"))
    for c in e["clips"] if e.get("guest") else []:  # co-op view switches
        for x, y in e["guest"]["pov"]:
            for s, txt in ((x, ">> PARTNER'S VIEW"), (y, "<< OWN VIEW")):
                if "file" not in c and c["src"] < s < c["src"] + round(c["dur"] * c.get("rate", 1)):
                    rows.append((c["from"] + round((s - c["src"]) / c.get("rate", 1)), f"   {txt}"))
            if "file" not in c and x <= c["src"] < y:
                rows.append((c["from"], "   (partner's view)"))
    rows += [(c["at"], f"   CAPTION {c['text']}") for c in e["captions"]]
    rows += [(x["at"], f"   BANNER {x['name']} — {x['fi']}") for x in e["effects"]]
    rows += [(z["at"], "   FACE ZOOM") for z in e["faceZooms"]] + [(z["at"], "   GAME ZOOM") for z in e["gameZooms"]]
    rows += [(p["at"], "   PUNCH") for p in e.get("punches", [])]
    rows += [(c["at"], f"   CHAPTER CARD {c['label']}") for c in e.get("cards", [])]
    rows += [(e["title"]["from"], "== TITLE CARD =="), (e["lowerThird"]["from"], "   LOWER THIRD"),
             (e["freeze"]["from"], f"== FREEZE {e['freeze']['text']} =="), (e["end"]["from"], "== END SCREEN ==")]
    if e.get("bed"):
        rows.append((e["introEnd"], f"   MUSIC BED {e['bed']['track']} (ducked under speech) until the freeze"))
    desc = open(f"{out_dir(edl)}/{edl['output']}.description.txt").read()
    rows += [(round(sum(float(v) * 60 ** i for i, v in enumerate(reversed(m[0].split(":")))) * fps), f"## CHAPTER {m[1]}")
             for m in re.findall(r"^(\d+:\d\d) (.+)$", desc, re.M)]
    out = f"{w}/ep{edl['episode']}.script.txt"
    with open(out, "w") as fh:
        fh.writelines(f"{fmt(f / fps)} {txt}\n" for f, txt in sorted(rows, key=lambda r: r[0]))
    print(out, f"{e['duration'] / fps / 60:.1f} min")


def speller(lang):
    """Spell check for the commentary language through libvoikko (Finnish; apt `libvoikko1 voikko-fi`; Arch: `pacman -S
    libvoikko` plus the prebuilt dict.zip unzipped into ~/.voikko/5/mor-standard/, voikko-fi is AUR-only and needs foma),
    or None when it isn't installed: then only rarity and Whisper's confidence flag words."""
    import ctypes, ctypes.util
    if lang != "fi" or not (name := ctypes.util.find_library("voikko")):
        return None
    lib = ctypes.CDLL(name)
    lib.voikkoInit.restype, lib.voikkoInit.argtypes = ctypes.c_void_p, [ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_char_p]
    lib.voikkoSpellCstr.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    err = ctypes.c_char_p()
    h = lib.voikkoInit(ctypes.byref(err), b"fi", None)
    return (lambda w: lib.voikkoSpellCstr(h, w.encode()) == 1) if h else None


SUSPECT_P = 0.45  # Whisper word confidence under this is a suspect
SUSPECT_RARE = 2  # ...and so is a word the speller rejects that the whole stream says at most this often (colloquial words repeat; mishearings don't)


def subtitle_suspects(edl, segments):
    """Subtitle cues holding a likely mishearing: a word Whisper was unsure of, or one the speller rejects that is rare in
    the whole transcript. Names in the EDL (title, tags, lower third, wordFixes) are never suspects."""
    cues = json.load(open(f"work/{edl['vod']}/ep{edl['episode']}.subs.json"))
    bare = lambda x: re.sub(r"^\W+|\W+$", "", x).lower()
    count = {}
    for seg in segments:
        for w in seg["words"]:
            count[bare(w["word"])] = count.get(bare(w["word"]), 0) + 1
    known = {bare(x) for x in re.findall(r"[\w-]+", json.dumps([edl.get("title"), edl.get("tags"), edl.get("lowerThird"), edl.get("wordFixes"),
                                                                 CFG.get("channel"), CFG.get("transcript_prompt")], ensure_ascii=False))}
    spell = speller(CFG["language"])
    out = []
    for c in cues:
        bad = []
        for w in c["words"]:
            b = bare(w["word"])
            if not b or b.isdigit() or b in known:
                continue
            unsure = w.get("p", 1) < SUSPECT_P
            wrong = spell is not None and not all(spell(x) for x in b.split("-") if x) and count.get(b, 0) <= SUSPECT_RARE
            if unsure or wrong:
                bad.append(w["word"].strip() + (f" ({w['p']:.2f})" if unsure else ""))
        if bad:
            out.append((c, bad))
    return out, spell is not None


def proof(a):
    """Proof-read before `check`: a second Whisper pass over just the line of every caption and the whole of every Short
    (a fresh decode without the surrounding context), printed beside the transcript's words and the caption text.
    Caption words heard in neither decode are flagged, and so are transcript words of a Short that the second pass
    doesn't hear (those become the Short's cues and the subtitles): fix them with "wordFixes" in the EDL or by rewriting
    the caption. Written to work/<vod>/epN.proof.txt."""
    if a.read:
        import hashlib
        edl, e = build(a.edl)
        text = proof_text(edl, e)
        open(f"work/{edl['vod']}/ep{edl['episode']}.text.txt", "w").write(text)
        open(proof_stamp(edl), "w").write(hashlib.sha1(text.encode()).hexdigest())
        return print(f"proof-read text stamped: {proof_stamp(edl)}")
    edl = json.load(open(a.edl))
    w = f"work/{edl['vod']}"
    segments = json.load(open(f"{w}/transcript.json"))["segments"]
    bare = lambda x: re.sub(r"[^\w]", "", x.lower())
    items = []  # (label, start, end, transcript words, caption text or None)
    for t, match, text in edl.get("captions", []):
        t0 = parse_time(t)
        near = [s for s in segments if abs(s["start"] - t0) < 8 and match.lower() in s["text"].lower()]
        if not near:
            items.append((f"CAPTION {t} '{match}'", None, None, [], text))
            continue
        s = min(near, key=lambda s: abs(s["start"] - t0))
        items.append((f"CAPTION {t}", s["start"], s["end"], [x["word"].strip() for x in s["words"]], text))
    for k, sh in enumerate(edl.get("shorts", []), 1):
        for x, y in sh.get("ranges") or [[sh["from"], sh["to"]]]:
            a0, b0 = parse_time(x), parse_time(y)
            said = [x["word"].strip() for s in segments for x in s["words"] if a0 <= x["start"] < b0]
            items.append((f"SHORT {k} ({x}–{y})", a0, b0, said, None))
    run(PY, "scripts/build_edit.py", a.edl)  # the subtitle cues of this build (work/<vod>/epN.subs.json)
    suspects, spelled = subtitle_suspects(edl, segments)
    windows = [[max(0.0, s - 0.3), e + 0.4] for _, s, e, _, _ in items if s is not None]
    windows += [[max(0.0, c["words"][0]["start"] - 0.3), c["words"][-1]["end"] + 0.4] for c, _ in suspects]
    tmp = f".tmp/{edl['vod']}-ep{edl['episode']}-proof.json"
    os.makedirs(".tmp", exist_ok=True)
    json.dump(windows, open(tmp, "w"))
    run(PY, "scripts/proof_pass.py", f"{w}/audio16k.wav", tmp, tmp, CFG["language"], env=gpu_env())
    second = iter(json.load(open(tmp)))
    lines = []
    for label, s, e, said, text in items:
        if s is None:
            lines += [label, "  !! match word not found within 8 s of its time", ""]
            continue
        heard = next(second)
        lines += [f"{label}  [{fmt(s)}–{fmt(e)}]", f"  transcript: {' '.join(said)}", f"  2nd pass:   {heard}"]
        pool = {bare(x) for x in said} | {bare(x) for x in heard.split()} | {bare(x) for x in (edl.get("wordFixes") or {}).values()}  # a fixed spelling counts as heard
        if text is not None:
            lines.append(f"  caption:    {text}")
            if miss := [x for x in text.split() if bare(x) and bare(x) not in pool]:
                lines.append(f"  !! not heard in either decode: {' '.join(miss)}")
        else:
            h = {bare(x) for x in heard.split()}
            if diff := [x for x in said if bare(x) and bare(x) not in h]:
                lines.append(f"  ?? transcript words the 2nd pass doesn't hear (they become cues/subtitles): {' '.join(diff)}")
        lines.append("")
    lines += [f"== SUBTITLE SUSPECTS ({len(suspects)} cues; " + ("speller + " if spelled else "no speller installed: ")
              + f"Whisper confidence < {SUSPECT_P}): the 2nd pass beside each; map real mishearings in \"wordFixes\"", ""]
    for c, bad in suspects:
        lines += [f"SUB {c['n']} {fmt(c['at'])}  [VOD {fmt(c['words'][0]['start'])}]", f"  subtitle:   {c['text']}",
                  f"  2nd pass:   {next(second)}", f"  ?? {' · '.join(bad)}", ""]
    out = f"{w}/ep{edl['episode']}.proof.txt"
    open(out, "w").write("\n".join(lines))
    print("\n".join(lines))
    print(out)
    edl, e = build(a.edl)
    text_file = f"{w}/ep{edl['episode']}.text.txt"
    open(text_file, "w").write(proof_text(edl, e))
    print(f"{text_file}: read it whole (both languages), fix every mishearing, misspelling and stiff translation, then `lp.py proof {a.edl} --read`")


def proof_text(edl, e):
    """Every word the viewer reads, from this build: on-screen text, the Shorts, the subtitles and both languages'
    title/description/chapters. `proof` writes it to work/<vod>/epN.text.txt for a full proof-read (RULEBOOK 8.7)."""
    out = f"{out_dir(edl)}/{edl['output']}"
    tr = CFG.get("translation")
    lines = [f"== ON SCREEN ({CFG['language']})", f"title: {' · '.join(str(v) for k, v in edl['title'].items() if k not in ('bg',))}",
             f"lower third: {e['lowerThird']['text']} · {e['lowerThird']['sub']}"
             + (f" / {e['lowerThird']['guest']['text']} · {e['lowerThird']['guest'].get('sub', '')}" if e["lowerThird"].get("guest") else "")]
    lines += [f"note {fmt(n['at'] / e['fps'])}: {n['name']} · {n['fi']}" for n in e.get("notes") or []]
    lines += [f"effect {fmt(x['at'] / e['fps'])}: {x['name']} · {x.get('fi', '')}" for x in e["effects"]]
    lines += [f"caption {fmt(c['at'] / e['fps'])}: {c['text']}" for c in e["captions"]]
    lines += [f"card {fmt(c['at'] / e['fps'])}: {c['label']}" for c in e.get("cards") or []]
    for k, sh in enumerate(build_shorts(edl, e)[0], 1):
        sh = sh["short"]
        lines += ["", f"== SHORT {k}: {sh['title']} · {sh['cta']}"] + [f"  {c['text']}" for c in sh["captions"]]
    lines += ["", f"== DESCRIPTION ({CFG['language']})", open(f"{out}.description.txt").read().strip()]
    if tr and os.path.exists(f"{out}.{tr}.json"):
        t = json.load(open(f"{out}.{tr}.json"))
        lines += ["", f"== TRANSLATION ({tr})", f"title: {t['title']}", f"youtubeTitle: {(edl.get(tr) or {}).get('youtubeTitle', '')}", t["description"].strip()]
    srt = f"{out}.{CFG['language']}.srt"
    if not os.path.exists(srt):  # config "subtitles": false
        return "\n".join(lines) + "\n"
    lines += ["", f"== SUBTITLES ({CFG['language']}.srt)"]
    for cue in open(srt).read().strip().split("\n\n"):
        n, times, *txt = cue.split("\n")
        lines.append(f"{n:>4} {times[:8]}  {' '.join(txt)}")
    return "\n".join(lines) + "\n"


def proof_stamp(edl):
    return state_path(edl, "proofread.txt")


def require_proofread(edl, e):
    """Render only text that was proof-read: the hash `proof --read` stamped must match this build's text."""
    import hashlib
    h = hashlib.sha1(proof_text(edl, e).encode()).hexdigest()
    if not os.path.exists(proof_stamp(edl)) or open(proof_stamp(edl)).read().strip() != h:
        sys.exit(f"the text changed since it was proof-read (or never was): `lp.py proof {edl_path_of(edl)}`, read "
                 f"work/{edl['vod']}/ep{edl['episode']}.text.txt whole, fix it, then `lp.py proof {edl_path_of(edl)} --read`")
    return h


def edl_path_of(edl):
    return f"edits/{edl['vod']}-ep{edl['episode']}.json"


VISION = CFG.get("vision_model", "gemma4:12b")  # local Ollama vision model for `see` (qwen2.5vl:7b answered gibberish on Ollama 0.32)
SEE_W = 960  # frame width sent to the model (~660 image tokens each)


def ask_vision(images, prompt, labelled):
    """One question to the local vision model about a few frames → {"scene", "label_en", "concrete", "visible", "why"} (Ollama structured output)."""
    import base64, urllib.error, urllib.request
    props = {"scene": {"type": "string"}}
    if labelled:
        props |= {"label_en": {"type": "string"}, "concrete": {"type": "string", "enum": ["yes", "no"]}, "visible": {"type": "string", "enum": ["yes", "no", "unclear"]}, "why": {"type": "string"}}
    body = {"model": VISION, "stream": False, "think": False, "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 300},  # 4 frames ≈ 2.7k tokens; the 4k default cut answers off
            "format": {"type": "object", "properties": props, "required": list(props)},
            "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(open(f, "rb").read()).decode() for f in images]}]}
    url = CFG.get("ollama_url", "http://localhost:11434")
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(f"{url}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=900))
    except urllib.error.URLError as x:
        sys.exit(f"Ollama at {url} failed: {x}. Install Ollama and run `ollama pull {VISION}` (config \"vision_model\" picks another).")
    try:
        return json.loads(r["message"]["content"])
    except json.JSONDecodeError:
        return {"scene": r["message"]["content"].replace("\n", " "), "concrete": "yes", "visible": "unclear", "why": "the model's answer was not valid JSON"}


def view_file(edl, t):
    """The footage the viewer sees at VOD time t: the co-op partner's view inside the EDL's "pov" spans."""
    guest = any(parse_time(a) <= t < parse_time(b) for a, b in edl.get("pov", []))
    return f"footage/{edl['vod']}{'-guest' if guest else ''}.mp4"


def see(a):
    """Frame check before `check` (RULEBOOK 7.2) by a local vision model: a few frames across every chapter span, caption,
    cold-open hit, Short and the thumbnail; it says what the game screen shows across them and whether the label names
    something actually visible. !! = not visible, ?? = unclear: look at the row sheet named on the line, then relabel or drop.
    Written to work/<vod>/epN.see.txt, row sheets to work/<vod>/see/."""
    edl = json.load(open(a.edl))
    slug, cam = edl["vod"], edl.get("cam")
    en = (edl.get(CFG.get("translation", "")) or {}).get("chapters", [])
    main_end = max(parse_time(r[1]) for r in edl["main"])
    items = []  # (key, title, label, [times], spoken)
    across = lambda a0, b0, n: [a0 + (b0 - a0) * (k + 0.5) / n for k in range(n)]
    chapters = [(parse_time(t), lab) for t, lab in edl.get("chapters", [])]
    for i, (t, lab) in enumerate(chapters):
        if t == 0:
            continue
        end = chapters[i + 1][0] if i + 1 < len(chapters) else main_end
        tr = f" ({en[i]})" if i < len(en) and en[i] != lab else ""
        items.append((f"chapter{i}", f"CHAPTER {fmt(t)}–{fmt(end)} \"{lab}\"{tr}", lab + tr, [t + 1] + across(t, end, 3 if end - t > 20 else 1), False))  # the card's own moment, then the span
    for i, (t, _, text) in enumerate(edl.get("captions", [])):
        items.append((f"caption{i + 1}", f"CAPTION {t} \"{text}\"", text, [parse_time(t), parse_time(t) + 3], True))
    for i, r in enumerate(edl.get("coldOpen", [])):
        items.append((f"coldopen{i + 1}", f"COLD OPEN {r[0]}–{r[1]}", None, across(parse_time(r[0]), parse_time(r[1]), 2), False))
    for i, sh in enumerate(edl.get("shorts", [])):
        rs = [(parse_time(x), parse_time(y)) for x, y in sh.get("ranges") or [[sh["from"], sh["to"]]]]
        lab = sh["title"] + (f" ({sh['onScreen']})" if sh.get("onScreen") else "")
        items.append((f"short{i + 1}", f"SHORT {i + 1} {', '.join(f'{fmt(x)}–{fmt(y)}' for x, y in rs)} \"{lab}\"", lab, [t for x, y in rs for t in across(x, y, 2)], False))
    if (th := edl.get("thumb")) and th.get("bg"):
        items.append(("thumb", f"THUMBNAIL {th['bg']} \"{th.get('text', '')}\"", th.get("text"), [parse_time(th["bg"])], False))
    d, tmp = f"work/{slug}/see", f".tmp/see-{slug}-ep{edl['episode']}"
    os.makedirs(d, exist_ok=True), os.makedirs(tmp, exist_ok=True)
    mask = f"drawbox={cam[0]}:{cam[1]}:{cam[2]}:{cam[3]}:black:fill," if cam else ""
    lines, flagged = [], 0
    for key, title, label, times, spoken in items:
        files = []
        for k, t in enumerate(times):
            f = f"{tmp}/{key}-{k}.jpg"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", view_file(edl, t), "-frames:v", "1", "-vf", f"{mask}scale={SEE_W}:-2", "-q:v", "4", f], check=True)
            files.append(f)
        row = f"{d}/ep{edl['episode']}-{key}.jpg"
        draw = ";".join(f"[{k}:v]drawtext=text='{fmt(t).replace(':', '.')}':x=6:y=6:fontsize=26:fontcolor=yellow:box=1:boxcolor=black[v{k}]" for k, t in enumerate(times))
        stack = f"{''.join(f'[v{k}]' for k in range(len(times)))}hstack=inputs={len(times)}" if len(times) > 1 else "[v0]null"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *[x for f in files for x in ("-i", f)], "-filter_complex", f"{draw};{stack},scale=1440:-2", row], check=True)
        prompt = (f"{len(times)} frames in time order from one stretch of a video game stream ({edl.get('playlist', 'a game')}). Ignore the stream "
                  "overlay (chat, alerts, black boxes). scene: in at most 15 words, what the game screen shows across the frames: place, vehicles, "
                  "action, on-screen text.")
        if label and spoken:  # a caption is a quote of what the streamer says: most of it is talk with nothing to see
            prompt += (f" The streamer says \"{label}\" here ({CFG['language']}; shown as a caption). label_en: its literal English "
                       "translation. concrete: yes only if the line names a concrete on-screen thing or event that should be seen right "
                       "now (a vehicle, place, object, crash, on-screen text); no for talk, jokes, feelings, plans, remarks about the "
                       "stream or about people. visible: when concrete, yes if that thing is seen in these frames, no if it is not, "
                       "unclear if you can't tell; when not concrete, unclear. why: one short reason, naming what is seen instead when no.")
        elif label:
            prompt += (f" The editor's label for this stretch is \"{label}\" ({CFG['language']}). label_en: its literal English translation. "
                       "visible: yes if the concrete thing it names (a vehicle, place, object, event, on-screen text) is seen in these frames; "
                       "no if that concrete thing is not seen; unclear if the label names nothing concrete (a quote, a feeling, a mission or "
                       "person name), if you can't translate it, or if you can't tell. concrete: yes. why: one short reason, naming what is seen instead when no.")
        r = ask_vision(files, prompt, bool(label))
        lines += [f"{title}   {row}", f"  scene: {r.get('scene', '').strip()}"]
        if label:
            v = r.get("visible", "unclear") if r.get("concrete", "yes") == "yes" else "talk"
            flagged += v == "no"
            lines.append(f"  {'ok' if v == 'yes' else '!! NOT VISIBLE' if v == 'no' else '-- talk, nothing to see' if v == 'talk' else '?? unclear'} (read as \"{r.get('label_en', '').strip()}\"): {r.get('why', '').strip()}")
        lines.append("")
        print("\n".join(lines[-3 - bool(label):]), flush=True)
    import urllib.request  # unload the model now: Whisper (proof) needs the GPU memory next, and Ollama would keep it for minutes
    urllib.request.urlopen(urllib.request.Request(f"{CFG.get('ollama_url', 'http://localhost:11434')}/api/generate", json.dumps({"model": VISION, "keep_alive": 0}).encode(), {"Content-Type": "application/json"}))
    lines.append(f"{flagged} of {sum(1 for i in items if i[2])} labels name something the model doesn't see (model {VISION}; "
                 "its reading of the label is in quotes: a mistranslation voids the verdict, the scene line still counts)")
    out = f"work/{slug}/ep{edl['episode']}.see.txt"
    open(out, "w").write("\n".join(lines) + "\n")
    print(lines[-1], out, sep="\n")


def faces(a):
    """Liveliest webcam moments (movement in the face area, 4 fps), one per 20 s, as a contact sheet."""
    p = part(a.slug, a.ep)
    own = f"edits/{a.slug}-ep{a.ep}.json"  # this episode's cam first: siblings may not exist yet when episodes run in parallel
    sib = (json.load(open(own)) if os.path.exists(own) else None) or sibling_edl(a.slug, a.ep) or {}
    if not sib.get("cam"):
        sys.exit(f"no \"cam\" in {own} or a sibling EDL: set it (webcam rect in VOD pixels) before running faces")
    x, y, cw, ch = sib["cam"]
    _, face = motion(a.slug)
    mz = np.load(f"work/{a.slug}/motion.npz") if face is not None else None
    if face is not None and list(mz["cam"]) == list(sib["cam"]):  # ingest already measured this webcam
        scores = [(float(face[i]), i / MOTION_FPS) for i in range(int(p["start"] * MOTION_FPS), min(len(face), int(p["end"] * MOTION_FPS)))]
    else:
        fx, fy, fw, fh = x + cw // 6, y + ch // 12, cw * 2 // 3, ch * 2 // 3  # face region inside the cam
        proc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(p["start"]), "-t", str(p["end"] - p["start"]), "-i",
                                 f"footage/{a.slug}.mp4", "-vf", f"fps=4,crop={fw}:{fh}:{fx}:{fy},format=gray", "-f", "rawvideo", "-"],
                                stdout=subprocess.PIPE)
        prev, scores, i = None, [], 0
        while (buf := proc.stdout.read(fw * fh)):
            cur = np.frombuffer(buf, np.uint8).astype(np.int16)
            if prev is not None:
                scores.append((float(np.abs(cur - prev).mean()), p["start"] + i / 4))
            prev, i = cur, i + 1
    picks = []
    for sc, t in sorted(scores, reverse=True):
        if all(abs(t - u) > 20 for u in picks):
            picks.append(t)
        if len(picks) == 15:
            break
    d = f"work/{a.slug}/faces"
    os.makedirs(d, exist_ok=True)
    tiles = []
    for k, t in enumerate(picks):
        f = f"{d}/ep{a.ep}-{k:02}.jpg"
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", f"footage/{a.slug}.mp4", "-frames:v", 1, "-vf",
            f"crop={cw}:{ch}:{x}:{y},scale=290:-2,drawtext=text='{fmt(t).replace(':', '.')}':x=5:y=5:fontsize=20:fontcolor=yellow:box=1:boxcolor=black", f)
        tiles.append(f)
    sheet = f"work/{a.slug}/ep{a.ep}-faces.jpg"
    th = round(290 * ch / cw / 2) * 2
    layout = "|".join(f"{k % 5 * 290}_{k // 5 * th}" for k in range(len(tiles)))
    run("ffmpeg", "-nostdin", "-v", "error", "-y", *[v for f in tiles for v in ("-i", f)], "-filter_complex",
        f"xstack=inputs={len(tiles)}:layout={layout}", sheet)
    print(sheet, "times:", ", ".join(fmt(t) for t in picks))


def sheet(slug, times, out_file, view=""):
    """Contact sheet of VOD frames at the given m:ss times, three per row (view "-guest": the co-op partner's view)."""
    out = f"work/{slug}/frames"
    os.makedirs(out, exist_ok=True)
    tiles = []
    for t in times:
        f = f"{out}/{t.replace(':', '_')}.jpg"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(parse_time(t)), "-i", f"footage/{slug}{view}.mp4", "-frames:v", "1",
                        "-vf", f"scale={TILE_W}:-2,drawtext=text='{t.replace(':', '.')}':x=6:y=6:fontsize=22:fontcolor=yellow:box=1:boxcolor=black", f], check=True)
        tiles.append(f)
    cols = min(3, len(tiles))
    inputs = [x for f in tiles for x in ("-i", f)]
    layout = "|".join(f"{i % cols * TILE_W}_{i // cols * TILE_W * 9 // 16}" for i in range(len(tiles)))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex",
                    f"xstack=inputs={len(tiles)}:layout={layout}:fill=black" if len(tiles) > 1 else "null", out_file], check=True)
    return out_file


def frames(a):
    view = "-guest" if a.guest else ""
    print(sheet(a.slug, a.times, f"work/{a.slug}/frames/sheet{view}-{a.times[0].replace(':', '_')}-{len(a.times)}.jpg", view))  # one file per request


def video_dur(video):
    """The video stream's length (the file's can be longer: AAC audio runs a frame or two past the picture)."""
    return float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=duration", "-of", "csv=p=0", video],
                                capture_output=True, text=True).stdout)


def look_sheet(edl, video, times, name="look"):
    """Frames of a rendered file at the given seconds, 3 to a row → work/<vod>/epN-<name>.png (times printed in order)."""
    d = f"{TMP}/look"
    os.makedirs(d, exist_ok=True)
    dur = video_dur(video)
    times = [min(max(0.0, t), dur - 0.1) for t in times]
    files = []
    for i, t in enumerate(times):
        f, pre = f"{d}/{i}.png", max(0.0, t - 2)  # seek 2 s early, then decode to the frame: a fast seek near the end finds nothing
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{pre:.3f}", "-i", video, "-ss", f"{t - pre:.3f}", "-frames:v", "1", "-vf", "scale=640:-2", f)
        files.append(f)
    cols = min(3, len(files))
    w, h = (int(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                            files[0]], capture_output=True, text=True).stdout.strip().split(","))
    sheet = f"work/{edl['vod']}/ep{edl['episode']}-{name}.png"
    layout = "|".join(f"{i % cols * w}_{i // cols * h}" for i in range(len(files)))
    run("ffmpeg", "-nostdin", "-v", "error", "-y", *[x for f in files for x in ("-i", f)], "-filter_complex",
        f"xstack=inputs={len(files)}:layout={layout}:fill=black" if len(files) > 1 else "null", sheet)
    print(sheet, " ".join(fmt(t) for t in times))
    return sheet


def look(a):
    """Look at the rendered episode or a Short: frames at output times and/or spread over the last seconds."""
    edl = json.load(open(a.edl))
    video = f"{short_name(edl, a.short)}.mp4" if a.short else f"{out_dir(edl)}/{edl['output']}.mp4"
    times = [parse_time(t) for t in a.times]
    if a.last:
        dur = video_dur(video)
        times += [dur - a.last + a.last * i / 3 for i in range(1, 4)]
    if not times:
        sys.exit("give output times (m:ss) and/or --last S")
    look_sheet(edl, video, times, f"short{a.short}-look" if a.short else "look")


def at(a):
    """Episode output time ↔ VOD time, with the transcript line said there (--vod: the times are VOD times)."""
    edl = json.load(open(a.edl))
    e = json.load(open(props_path(edl)))["edit"]
    fps, off = e["fps"], part(edl["vod"], edl["episode"])["prepStart"]
    segs = json.load(open(f"work/{edl['vod']}/transcript.json"))["segments"]
    said = lambda v: next((s["text"] for s in segs if s["start"] - 0.3 <= v <= s["end"] + 0.3), "")
    for t in map(parse_time, a.times):
        if a.vod:
            f = (t - off) * fps
            hits = [c["from"] + (f - c["src"]) / c.get("rate", 1) for c in e["clips"] if "file" not in c and c["src"] <= f < c["src"] + round(c["dur"] * c.get("rate", 1))]
            print(f"VOD {fmt(t)} → episode {', '.join(fmt(h / fps) for h in hits) or 'cut'}  {said(t)}")
        else:
            c = next((c for c in e["clips"] if "file" not in c and c["from"] <= t * fps < c["from"] + c["dur"]), None)
            v = c and off + (c["src"] + (t * fps - c["from"]) * c.get("rate", 1)) / fps
            print(f"episode {fmt(t)} → VOD {fmt(v) if v else '(title/end card)'}  {said(v) if v else ''}")


def prep(a):
    if a.ep == "all":
        for n in range(1, len(json.load(open(f"work/{a.slug}/parts.json"))) + 1):
            prep(argparse.Namespace(slug=a.slug, ep=str(n)))
        return
    a.ep = int(a.ep)
    p = part(a.slug, a.ep)
    off, dur = p["prepStart"], p["prepEnd"] - p["prepStart"]
    if os.path.exists(f"work/{a.slug}/assemble.json"):  # separate recordings: each source its own track, composited at render
        sys.path.insert(0, "scripts")
        for f in __import__("assemble").tracks(a.slug, off, dur, f"public/{a.slug}-ep{a.ep}").values():
            print(f)
        return
    out = f"public/{a.slug}-ep{a.ep}.mp4"
    if os.path.exists(out):
        return print(out, "exists")
    run("ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", off, "-t", dur, "-i", f"footage/{a.slug}.mp4", "-vf", GRADE,
        "-map", "0:v", "-map", "0:a", *video_encoder(), "-g", 60, "-c:a", "aac", "-b:a", "256k",
        "-movflags", "+faststart", "-f", "mp4", out + ".part.mp4")
    os.rename(out + ".part.mp4", out)


def build(edl_path):
    run(PY, "scripts/build_edit.py", edl_path)
    edl = json.load(open(edl_path))
    run(PY, "scripts/thumb_plan.py", props_path(edl), edl_path)  # webcam cut-out + thumbnail readability
    return edl, json.load(open(props_path(edl)))["edit"]


def props_path(edl):
    return f"work/{edl['vod']}/ep{edl['episode']}.props.json"


def scale(edl):
    """Render at the VOD's native size (never upscale); compositions are laid out at 1920x1080."""
    return meta(edl["vod"])["width"] / 1920


def remotion(edl, *args, props=None):
    """Render with this episode's timeline as input props (work/<vod>/epN.props.json), or the given props file."""
    os.makedirs(TMP, exist_ok=True)
    # --timeout: the first frame from a multi-GB track on a cold disk cache takes longer than Remotion's 30 s delayRender limit
    run("npx", "remotion", *args, f"--props={props or props_path(edl)}", "--timeout=180000", "--log=error", env={"TMPDIR": TMP})


def check(a):
    edl, e = build(a.edl)
    problems = build_shorts(edl, e)[1] + ([] if edl.get("shorts") else ["no shorts picked: add up to 4 to \"shorts\" (RULEBOOK 15.0–15.1)"])
    if problems:
        sys.exit("\n".join(problems))
    first = lambda xs: xs[0]["at"] + 30 if xs else e["clips"][len(e["clips"]) // 3]["from"]
    stack = next((c["at"] + 30 for c in e["captions"] if c.get("slot")), first(e["captions"]))
    card = e["cards"][0]["at"] + 40 if e.get("cards") else e["clips"][len(e["clips"]) // 2]["from"] + 10
    picks = [e["clips"][0]["from"] + 30 if e.get("recap") else e["title"]["from"] + 120, first(e["faceZooms"]), stack, first(e["effects"]) + 10,
             card, e["lowerThird"]["from"] + 40, e["freeze"]["from"] + 90, e["end"]["from"] + 200]
    picks += [n["at"] + 40 for n in e.get("notes") or []][:1]  # a note to the viewer
    if e["lowerThird"].get("guest") and e.get("tracks"):  # co-op tags take turns: the partner's is in the second half
        picks.append(e["lowerThird"]["from"] + e["lowerThird"]["dur"] // 2 + 40)
    d = f"work/{edl['vod']}/check"
    os.makedirs(d, exist_ok=True)
    for f in picks:
        remotion(edl, "still", "src/index.ts", "LetsPlay", f"{d}/{f}.jpg", f"--frame={f}", f"--scale={scale(edl)}")
    inputs = [x for f in picks for x in ("-i", f"{d}/{f}.jpg")]
    sheet = f"work/{edl['vod']}/ep{edl['episode']}-check.jpg"
    w, h = meta(edl["vod"])["width"], meta(edl["vod"])["height"]
    layout = "|".join(f"{i % 2 * w}_{i // 2 * h}" for i in range(len(picks)))
    run("ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", f"xstack=inputs={len(picks)}:layout={layout}:fill=black,scale=1280:-2", sheet)
    print(sheet)


MASTER = "acompressor=threshold=-24dB:ratio=2.5:attack=8:release=180:makeup=2,loudnorm=I=-14:TP=-1:LRA=11"
master = lambda e: f"{MASTER},atrim=end={e['duration'] / e['fps']:.6f}"  # loudnorm can run the audio ~0.1 s past the last frame


SR = 48000
SFX_TAIL = 120  # frames a sound effect may ring on after its element ends


def render(a):
    edl, e = build(a.edl)
    require_proofread(edl, e)
    out = f"{out_dir(edl)}/{edl['output']}"
    common = (f"--concurrency={CONCURRENCY}", f"--scale={scale(edl)}")
    ranges = a.patch and patch_ranges(edl, e, a.patch)
    if ranges:
        render_patch(edl, e, out, common, ranges)
    elif ranges == []:
        print("nothing changed since the last render")
    else:
        raw = f"{out}.raw.mp4"
        remotion(edl, "render", "src/index.ts", "LetsPlay", raw, *common, "--crf=17", "--audio-bitrate=320k")
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", raw, "-vn", "-c:a", "pcm_s16le", "-ar", SR, state_path(edl, "mix.wav"))
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", raw, "-c:v", "copy", "-af", master(e),
            "-ar", SR, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", f"{out}.new.mp4")
        os.remove(raw)
        finish(f"{out}.new.mp4", f"{out}.mp4", edl, e)
    json.dump(e, open(state_path(edl, "rendered.json"), "w"))
    remotion(edl, "still", "src/index.ts", "Thumbnail", f"{out}.jpg")
    render_shorts(edl, e, changed_only=ranges is not None)  # a patch re-renders only the Shorts whose props changed
    if ranges:  # what the patch changed, to look at: work/<vod>/epN-look.png
        look_sheet(edl, f"{out}.mp4", [t for a, b in ranges for t in (a / e["fps"] + 1, (a + b) / 2 / e["fps"])])
    lufs = subprocess.run(["ffmpeg", "-nostdin", "-i", f"{out}.mp4", "-vn", "-af", "ebur128", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    print(f"{out}.mp4  {e['duration'] / 60 / 60:.1f} min  {re.findall(r'I:\s+(-?[\d.]+ LUFS)', lufs)[-1]}")


def state_path(edl, name):
    """Kept per rendered episode: the unmastered audio mix (mix.wav) and the timeline it was rendered from (rendered.json),
    so a patch render can find what changed and splice only that."""
    return f"work/{edl['vod']}/ep{edl['episode']}.{name}"


def parse_time(t):
    return sum(float(x) * 60 ** i for i, x in enumerate(reversed(t.split(":"))))


def item_spans(e):
    """Every timeline element with the output frames it touches (sound effects included), keyed for comparison."""
    spans = []
    for i, c in enumerate(e["clips"]):
        spans.append((f"clip{i}", c, c["from"] - max(20 if c.get("whoosh") else 0, c.get("lead", 0)), c["from"] + c["dur"] + e.get("xfade", 0)))
    for k, n in (("effects", 212), ("captions", 132), ("cards", 210)):
        spans += [(f"{k}{i}", x, x["at"], x["at"] + x.get("dur", n)) for i, x in enumerate(e.get(k, []))]
    if e.get("bed"):  # ducking follows the speech; a change there re-renders that stretch of the bed
        spans += [(f"talk{i}", t, t[0], t[1]) for i, t in enumerate(e["bed"]["talk"])]
    spans += [(f"punch{i}", p, p["at"] - 2, p["at"] + 20) for i, p in enumerate(e.get("punches", []))]
    for k, pre, post in (("faceZooms", 7, 14), ("gameZooms", 18, 24)):
        spans += [(f"{k}{i}", z, z["at"] - pre, z["end"] + post) for i, z in enumerate(e[k])]
    t = e["title"]
    spans.append(("title", [t, e["introEnd"]], t["from"] - 96, e["introEnd"]))  # riser before it, music bed until introEnd
    for k in ("lowerThird", "freeze", "end"):
        spans.append((k, e[k], e[k]["from"], e[k]["from"] + e[k]["dur"]))
    return spans


def patch_ranges(edl, e, spec):
    """Output frame ranges to re-render: changed timeline elements (auto), 'end' (freeze + end screen) and/or explicit
    m:ss-m:ss output-time ranges for changes that are not in the timeline data (component design, styles).
    None means a full render is needed."""
    if not os.path.exists(f"{out_dir(edl)}/{edl['output']}.mp4") or not os.path.exists(state_path(edl, "mix.wav")):
        print("no previous render with a kept mix: full render")
        return None
    ranges, fps = [], e["fps"]
    for part in spec.split(","):
        if part == "end":
            ranges.append((e["freeze"]["from"], e["duration"]))
        elif part != "auto":
            a, b = part.split("-")
            ranges.append((int(parse_time(a) * fps), int(parse_time(b) * fps)))
    old = json.load(open(state_path(edl, "rendered.json"))) if os.path.exists(state_path(edl, "rendered.json")) else None
    if "auto" in spec.split(","):
        if old is None:
            print("no record of the previous timeline: full render")
            return None
        if any(old.get(k) != e.get(k) for k in ("fps", "source", "cam", "style", "tracks")):
            print("source, webcam or style changed: full render")
            return None
        pv = lambda x: {tuple(sp) for sp in (x.get("guest") or {}).get("pov", [])}
        for a, b in pv(old) ^ pv(e):  # a changed "pov" span: re-render every clip that shows any of it
            ranges += [(c["from"], c["from"] + c["dur"] + e.get("xfade", 0)) for c in e["clips"]
                       if "file" not in c and c["src"] < b and a < c["src"] + c["dur"] + e.get("xfade", 0)]
        if old["duration"] != e["duration"]:  # timing shifted: everything after the first difference moves
            first = min((min(s1[2], s2[2]) for s1, s2 in zip(item_spans(old), item_spans(e)) if s1[1] != s2[1]), default=0)
            ranges.append((max(0, first), e["duration"]))
        else:
            before, after = {k: (v, a, b) for k, v, a, b in item_spans(old)}, {k: (v, a, b) for k, v, a, b in item_spans(e)}
            for k in before.keys() | after.keys():
                if before.get(k, (None,))[0] != after.get(k, (None,))[0]:
                    for v in (before.get(k), after.get(k)):
                        if v:
                            ranges.append((v[1], v[2]))
    ranges = [(max(0, a), min(e["duration"], b + SFX_TAIL)) for a, b in ranges]
    merged = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def video_pts(path):
    """Presentation times of every video packet (no decode), with the keyframe flag, in file order."""
    return [(float(l.split(",")[0]), "K" in l.split(",")[1]) for l in subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", path],
        text=True).splitlines()]


def keyframes(path, fps):
    """Keyframe frame index → its exact pts string, for seeking with stream copy."""
    return {round(t * fps): f"{t:.6f}" for t, k in video_pts(path) if k}


def sync_error(path, total, fps):
    """Why the file's clocks are wrong, or None: the video must have exactly `total` frames at exactly 1/fps each (every
    presentation time equal to its frame index / fps) and the audio must run as long as the video. Any patch or render
    whose seams drifted, duplicated or squashed timestamps fails this and is thrown away."""
    pts = sorted(t for t, _ in video_pts(path))
    if len(pts) != total:
        return f"{len(pts)} video frames, expected {total}"
    off = max(abs(t - i / fps) for i, t in enumerate(pts))
    if off > 0.5 / fps:
        return f"video timestamps drift up to {off:.3f} s from their frame index"
    adur = float(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=duration",
                                          "-of", "csv=p=0", path], text=True))
    if abs(adur - total / fps) > 0.1:
        return f"audio is {adur:.2f} s, video {total / fps:.2f} s"
    return None


def finish(new, old, edl, e):
    """Install a rendered episode file only when its video and audio clocks agree; otherwise keep the old file."""
    err = sync_error(new, e["duration"], e["fps"])
    if err:
        os.remove(new)
        sys.exit(f"render rejected: {err}; {old} left as it was")
    os.replace(new, old)


def render_patch(edl, e, out, common, ranges):
    """Re-render only the given output frame ranges and splice them into the existing episode file.

    Video: each range widens to the old file's keyframes (closed GOPs), so the unchanged pieces are stream-copied;
    pieces are cut by frame count in decode order, never by time (B-frames), and carry no audio (an audio stream's
    priming offset would shift the concat's timestamps). Audio: the kept unmastered mix with the
    re-rendered ranges' audio spliced in sample-exactly (48000/fps samples per frame), then mastered as a whole so the
    loudness is identical and there is no seam. The result must have exactly the timeline's frame count, else the old
    file is left untouched."""
    old, fps, total = f"{out}.mp4", e["fps"], e["duration"]
    work_tmp = f"{TMP}/{edl['vod']}-ep{edl['episode']}"
    os.makedirs(work_tmp, exist_ok=True)
    keys = keyframes(old, fps)
    segs = []
    for a, b in ranges:  # widen to keyframes: start at one at or before a, end at one at or after b (or the end)
        a = max(k for k in keys if k <= a)
        b = min(min((k for k in keys if k >= b), default=total), total)  # old keyframes may lie past a shorter new end
        if segs and a <= segs[-1][1]:
            segs[-1][1] = max(segs[-1][1], b)
        else:
            segs.append([a, b])
    print("re-rendering", ", ".join(f"{fmt(a / fps)}–{fmt(b / fps)}" for a, b in segs),
          f"({sum(b - a for a, b in segs) / total:.0%} of the episode)")
    pieces, audio, cursor, tmp = [], [], 0, []
    for i, (a, b) in enumerate(segs):
        if a > cursor:
            pieces.append(("old", cursor, a))
        pieces.append(("new", a, b))
        cursor = b
    if cursor < total:
        pieces.append(("old", cursor, total))
    spf = SR // fps
    for i, (kind, a, b) in enumerate(pieces):
        f = f"{work_tmp}/piece{i}.mp4"
        tmp.append(f)
        if kind == "new":
            av = f"{work_tmp}/piece{i}.av.mp4"
            remotion(edl, "render", "src/index.ts", "LetsPlay", av, *common, "--crf=17", "--audio-bitrate=320k", f"--frames={a}-{b - 1}")
            w = f"{work_tmp}/piece{i}.wav"
            run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", av, "-vn", "-ar", SR, "-af", f"apad=whole_len={(b - a) * spf},atrim=end_sample={(b - a) * spf}",
                "-c:a", "pcm_s16le", w)
            # video only: the AAC priming of the piece's own audio (2048 samples) would make the concat demuxer shift the whole picture by 43 ms
            run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", av, "-an", "-c:v", "copy", f)
            tmp += [av, w]
            audio.append(w)
        else:
            seek = ["-ss", keys[a]] if a else []  # the keyframe's own pts: a computed time could miss it and copy pre-roll
            run("ffmpeg", "-nostdin", "-v", "error", "-y", *seek, "-i", old, "-map", "0:v", "-c", "copy", "-frames:v", b - a, f)
            got = video_pts(f)
            if len(got) != b - a or not got[0][1]:
                sys.exit(f"piece {a}-{b} of {old} came out as {len(got)} frames{'' if got[0][1] else ' not starting on a keyframe'}; {old} left unchanged")
            w = f"{work_tmp}/piece{i}.wav"
            run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", state_path(edl, "mix.wav"), "-af",
                f"atrim=start_sample={a * spf}:end_sample={b * spf},asetpts=N/SR/TB", "-c:a", "pcm_s16le", w)
            tmp.append(w)
            audio.append(w)
    lst, mix_new, new = f"{work_tmp}/concat.txt", f"{work_tmp}/mix.wav", f"{out}.new.mp4"
    with open(lst, "w") as fh:  # explicit durations: the next piece starts exactly where this one's frames end, never at a rounded file duration
        fh.writelines(f"file '{os.path.abspath(f'{work_tmp}/piece{i}.mp4')}'\nduration {(b - a) / fps:.6f}\n" for i, (_, a, b) in enumerate(pieces))
    run("ffmpeg", "-nostdin", "-v", "error", "-y", *[x for w in audio for x in ("-i", w)], "-filter_complex",
        "".join(f"[{i}:a]" for i in range(len(audio))) + f"concat=n={len(audio)}:v=0:a=1", "-c:a", "pcm_s16le", mix_new)
    run("ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-i", mix_new, "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-af", master(e), "-ar", SR, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", new)
    finish(new, old, edl, e)
    os.replace(mix_new, state_path(edl, "mix.wav"))
    for f in tmp + [lst]:
        os.remove(f)


LINK_TODO = "(link)"  # replaced by the episode's URL once it is known
SHORT_HOLD_S = 1.0  # a Short ends on its last frame held (Short.tsx Hold): never a dead stop on the last word
SHORT_MIN, SHORT_MAX = 8, 60  # seconds; under a minute is where Shorts perform best


def effect_label(edl):
    """The banner's small label: the EDL's own (hand-placed banners), else the game module's (e.g. "CHAOS EFFECT"), or ''."""
    if edl.get("effectLabel"):
        return edl["effectLabel"]
    if not game_lib(edl["vod"]):
        return ""
    labels = json.load(open("games/chaosmod/labels.json"))
    return labels.get(CFG["language"], labels["en"])


def short_name(edl, k):
    return f"{out_dir(edl)}/shorts/{edl['output']} - Short {k}"


CUE_WORDS, CUE_SPAN = 4, 1.6  # Shorts are watched muted: every line is captioned, a few words at a time


def short_cues(words, clips, fps, off):
    """Word-by-word captions for every spoken word inside a Short's clips: {at, text, words, dur} in Short frames."""
    shown = [(c["from"] + round((w["start"] - off) * fps) - c["src"], max(1, round((w["end"] - w["start"]) * fps)), w["word"].strip(), w.get("glued"))
             for c in clips for w in words if c["src"] <= (w["start"] - off) * fps < c["src"] + c["dur"]]
    cues = []
    for at, d, word, glued in shown:  # glued: the rest of a phrase wordFix, kept on its first word's cue
        cur = cues[-1] if cues else None
        if cur and glued or cur and len(cur["words"]) < CUE_WORDS and at - cur["at"] <= CUE_SPAN * fps and at - cur["end"] < 0.5 * fps and cur["text"][-1:] not in ".?!":
            cur["words"].append(at - cur["at"])
            cur["text"] += " " + word
            cur["end"] = at + d
        else:
            cues.append({"at": at, "end": at + d, "text": word, "words": [0]})
    for cue, nxt in zip(cues, cues[1:] + [None]):
        cue["text"] = cue["text"].upper()
        cue["dur"] = min(cue.pop("end") - cue["at"] + 45, nxt["at"] - cue["at"] if nxt else 10 ** 6)
    return cues


def build_shorts(edl, e):
    """Props for each Short in the EDL: one VOD stretch (from–to) or two ("ranges", one internal cut), every spoken word
    captioned, with the episode's own captions (shown big) and banners that fall in it."""
    fps, p = e["fps"], part(edl["vod"], edl["episode"])
    off = p["prepStart"]
    vod_time = lambda f: next(((c["src"] + (f - c["from"]) * c.get("rate", 1)) / fps + off for c in e["clips"]
                               if "file" not in c and c["from"] <= f < c["from"] + c["dur"]), None)
    tag = re.sub(r"\s*#\d+$", "", edl["thumb"].get("tag", ""))
    words = fix_words(real_words([w for s in json.load(open(f"work/{edl['vod']}/transcript.json"))["segments"] for w in s["words"]],
                                 np.load(f"work/{edl['vod']}/rms100ms.npy")), edl.get("wordFixes"))
    out, problems = [], []
    for k, sh in enumerate(edl.get("shorts", []), 1):
        ranges = [[parse_time(x), parse_time(y)] for x, y in sh.get("ranges") or [[sh["from"], sh["to"]]]]
        label = ", ".join(f"{fmt(x)}–{fmt(y)}" for x, y in ranges)
        total = sum(y - x for x, y in ranges)
        if not SHORT_MIN <= total <= SHORT_MAX - SHORT_HOLD_S or any(x < p["prepStart"] or y > p["prepEnd"] or y <= x for x, y in ranges):
            problems.append(f"short {k} ({label}): must total {SHORT_MIN}–{SHORT_MAX - SHORT_HOLD_S:g} s (+ {SHORT_HOLD_S:g} s end hold) inside this episode's footage")
            continue
        seen = lambda x, y: any(parse_time(a) <= x and y <= parse_time(b) for a, b in edl.get("pov", []))  # in the partner's view
        if (g := max(0 if seen(x, y) else guest_share(edl["vod"], x, y) for x, y in ranges)) > 0.35:
            msg = f"short {k} ({label}): {g:.0%} of the talking is the co-op guest, whose gameplay isn't in this stream"
            if not sh.get("onScreen"):  # the labels are mouth-motion guesses: an "onScreen" note says the frames were checked
                problems.append(msg + "; pick a moment of the streamer's own, or say what the streamer's screen shows in \"onScreen\"")
                continue
            print(f"warning: {msg}; kept because onScreen = {sh['onScreen']!r}")
        if (sp := partner_span(edl["vod"])) and any(x < sp[0] or y > sp[1] for x, y in ranges):
            print(f"warning: short {k} ({label}): the co-op partner's mic isn't recorded here, though they're in the call: "
                  "a Short has no note banner, so make sure it doesn't answer or react to someone the viewer can't hear")
        clips, cur = [], 0
        for x, y in ranges:
            d = round((y - x) * fps)
            clips.append({"src": round((x - off) * fps), "dur": d, "from": cur})
            cur += d
        def short_frame(t):
            return next((c["from"] + round((t - off) * fps) - c["src"] for c in clips if c["src"] <= (t - off) * fps < c["src"] + c["dur"] - fps), None)
        def inside(items, key):
            seen, res = set(), []
            for x in items:
                t = vod_time(x["at"])
                f = short_frame(t) if t is not None else None
                if f is not None and x[key] not in seen:  # cold-open repeats map to the same moment
                    seen.add(x[key])
                    res.append({**x, "at": f})
            return res
        big = inside(e["captions"], "text")
        cues = [c for c in short_cues(words, clips, fps, off)  # a cue whose words run into a big caption would say them twice
                if not any(b["at"] - 10 < c["at"] + max(1, c["dur"] - 45) and c["at"] < b["at"] + b["dur"] for b in big)]
        captions = sorted(cues + [{**b, "big": True} for b in big], key=lambda c: c["at"])
        out.append({"short": {"source": e["source"], "fps": fps, "style": e["style"], "clips": clips, "dur": cur + round(SHORT_HOLD_S * fps), "hold": round(SHORT_HOLD_S * fps),
                              "cropX": sh.get("cropX", 420), "cam": e["cam"], "title": sh["title"],
                              "tag": tag, "cta": text("full_episode", episode=edl["title"].get("episode", "")).strip(),
                              "text": {"channel": CFG["channel"], "from_stream": edl.get("fromStream") or text("from_stream"), "partner": edl["lowerThird"].get("guest"),
                                       "effect_label": effect_label(edl)},
                              "captions": captions, "effects": inside(e["effects"], "name"), "guest": e.get("guest"), "tracks": e.get("tracks")}})
    return out, problems


def render_shorts(edl, e, changed_only=False):
    """Render the Shorts; changed_only (a patch render) skips a Short whose props and file are unchanged since its last
    render. A change in Short.tsx alone isn't seen: `lp.py shorts` renders them all."""
    shorts, problems = build_shorts(edl, e)
    if problems:
        sys.exit("\n".join(problems))
    os.makedirs(f"{out_dir(edl)}/shorts", exist_ok=True)
    yt_id = json.load(open(state_path(edl, "youtube.json")))["id"] if os.path.exists(state_path(edl, "youtube.json")) else None
    for k, props in enumerate(shorts, 1):
        pf, name = state_path(edl, f"short{k}.props.json"), short_name(edl, k)
        if changed_only and os.path.exists(f"{name}.mp4") and os.path.exists(pf) and json.load(open(pf)) == props:
            print(f"short {k} unchanged")
            continue
        json.dump(props, open(pf, "w"), ensure_ascii=False)
        raw = f"{name}.raw.mp4"
        remotion(edl, "render", "src/index.ts", "Short", raw, f"--concurrency={CONCURRENCY}", "--crf=17", "--audio-bitrate=320k",
                 f"--scale={scale(edl)}", props=pf)
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", raw, "-c:v", "copy", "-af", MASTER, "-ar", SR, "-c:a", "aac",
            "-b:a", "320k", "-movflags", "+faststart", f"{name}.mp4")
        os.remove(raw)
        sh = edl["shorts"][k - 1]
        link = f"https://youtu.be/{yt_id}" if yt_id else LINK_TODO
        with open(f"{name}.txt", "w") as fh:
            fh.write(f"{sh['title'].capitalize()} – {edl['output'].rsplit(' - ', 1)[0]} #shorts\n\n{text('short_description', output=edl['output'], link=link)}\n\n"
                     + " ".join("#" + re.sub(r"\W", "", t) for t in edl.get("tags", [])[:5]) + "\n")
        print(f"{name}.mp4  {props['short']['dur'] / e['fps']:.0f} s")


def shorts(a):
    edl, e = build(a.edl)
    require_proofread(edl, e)
    render_shorts(edl, e)


def publish(a):
    """Wait for the user's Studio upload of this episode (matched by length, ±2 s), then fill it in: details, thumbnail,
    subtitles, English translation, playlist. The video id is kept in work/<vod>/epN.youtube.json. Visibility changes
    only with --at/--now, which the user must have asked for."""
    import youtube_mcp as yt
    edl = json.load(open(a.edl))
    out, state = f"{out_dir(edl)}/{edl['output']}.mp4", state_path(edl, "youtube.json")
    length = probe_duration(out)
    e = json.load(open(props_path(edl)))["edit"]  # the description, subtitles and translation come from this build; they must match the mp4
    if abs(e["duration"] / e["fps"] - length) > 1:
        sys.exit(f"{out} is {length:.0f} s but the current build is {e['duration'] / e['fps']:.0f} s: its description/subtitles don't fit the "
                 "rendered file (a later build rewrote them). Re-render (--patch) or rebuild the EDL that was rendered before publishing.")
    vid = json.load(open(state))["id"] if os.path.exists(state) else None
    taken = {json.load(open(f"work/{d}/{f}"))["id"] for d in os.listdir("work") if os.path.isdir(f"work/{d}")
             for f in os.listdir(f"work/{d}") if f.endswith(".youtube.json")} - {vid}
    iso = lambda d: sum(int(n) * {"H": 3600, "M": 60, "S": 1}[u] for n, u in re.findall(r"(\d+)([HMS])", d))
    while not vid:
        match = [v for v in yt.list_videos(10) if v["id"] not in taken and abs(iso(v["duration"]) - length) <= 2]
        if match:
            vid = match[0]["id"]
            json.dump({"id": vid}, open(state, "w"))
            break
        print("waiting for the upload to appear…", flush=True)
        time.sleep(30)
    print(yt.apply_episode(vid, edl["output"], tags=edl.get("tags") or None))
    if edl.get("playlist"):
        print(yt.add_to_playlist(vid, edl["playlist"]))
    if a.at or a.now:
        print(yt.set_visibility(vid, "public", a.at))
    print(f"https://youtu.be/{vid}  end screen and game title are set in Studio")
    publish_shorts(edl, vid, taken | {vid}, iso)


def publish_shorts(edl, episode_id, taken, iso):
    """Match the Shorts the user uploaded (by length, ±1 s) and fill in title, description (linking the episode), tags.
    Waits until every Short is found; ids go to work/<vod>/epN.shorts.json. They stay private until the user's go."""
    import youtube_mcp as yt
    names = [short_name(edl, k) for k in range(1, len(edl.get("shorts", [])) + 1)]
    names = [n for n in names if os.path.exists(f"{n}.mp4")]
    state = state_path(edl, "shorts.json")
    ids = json.load(open(state)) if os.path.exists(state) else {}
    while len(ids) < len(names):
        vids = [v for v in yt.list_videos(20) if v["id"] not in taken | set(ids.values())]
        for n in names:
            if n in ids:
                continue
            length = probe_duration(f"{n}.mp4")
            m = [v for v in vids if abs(iso(v["duration"]) - length) <= 1]
            key = re.sub(r"\W+", " ", os.path.basename(n)).strip().lower()  # Studio titles the upload after the file: same-length Shorts don't swap
            m.sort(key=lambda v: re.sub(r"\W+", " ", v["title"]).strip().lower() != key)
            if m:
                ids[n] = m[0]["id"]
                vids.remove(m[0])
                json.dump(ids, open(state, "w"), indent=1)
                title, _, rest = open(f"{n}.txt").read().partition("\n")
                desc = rest.strip().replace(LINK_TODO, f"https://youtu.be/{episode_id}")
                y = yt.yt()
                yt.update_snippet(y, m[0]["id"], title=title[:100], description=desc, categoryId=yt.GAMING,
                                  tags=edl.get("tags") or None, defaultLanguage=CFG["language"], defaultAudioLanguage=CFG["language"])
                yt.update_status(y, m[0]["id"], selfDeclaredMadeForKids=False, containsSyntheticMedia=False)
                print(f"short {os.path.basename(n)}: https://youtube.com/shorts/{m[0]['id']}")
        if len(ids) < len(names):
            print(f"waiting for {len(names) - len(ids)} Short upload(s)…", flush=True)
            time.sleep(30)


def retention(a):
    """Audience retention of the published episode (YouTube Analytics) on the edit's own timeline: the curve in 10 %
    steps and the sharpest drops with the script lines playing there. Written to work/<vod>/epN.retention.txt."""
    import youtube_mcp as yt
    edl = json.load(open(a.edl))
    state = state_path(edl, "youtube.json")
    if not os.path.exists(state):
        sys.exit("episode not published yet (no work/<vod>/epN.youtube.json)")
    vid = json.load(open(state))["id"]
    rows = yt.retention(vid)
    if not rows:
        sys.exit("no retention data yet: YouTube needs a public video and a few days of views")
    length = probe_duration(f"{out_dir(edl)}/{edl['output']}.mp4")
    script_rows = []
    if os.path.exists(state_path(edl, "script.txt")):
        for line in open(state_path(edl, "script.txt")):
            m = re.match(r"(\d+:\d+\.\d) (.*)", line)
            if m:
                script_rows.append((parse_time(m[1]), m[2]))
    lines = [f"# {edl['output']} ({vid}): audience retention, {len(rows)} points over {length / 60:.1f} min",
             "position  watched  vs similar videos"]
    for ratio, watched, rel in rows:
        if round(ratio * 100) % 10 == 0:
            lines.append(f"{fmt(ratio * length):>8}  {watched:6.0%}  {rel}")
    drops = sorted(((rows[i][1] - rows[i + 1][1], rows[i][0] * length) for i in range(len(rows) - 1)), reverse=True)[:8]
    lines.append("\nsharpest drops (lost share of viewers per step, output time, what plays there):")
    for d, t in sorted(drops, key=lambda x: x[1]):
        near = [f"      {fmt(s)} {txt}" for s, txt in script_rows if t - 8 <= s < t + 8][:4]
        lines += [f"  -{d:.1%} at {fmt(t)}"] + near
    out = state_path(edl, "retention.txt")
    open(out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(out)


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
s = sub.add_parser("ingest"); s.add_argument("vod"); s.add_argument("--slug"); s.add_argument("--game", choices=GAMES)
s.add_argument("--chaos", action="store_true", help=argparse.SUPPRESS)  # old spelling of --game chaosmod
s = sub.add_parser("split"); s.add_argument("slug"); s.add_argument("--target", type=float, default=25)
s.add_argument("--parts", type=int, help="fixed episode count, e.g. 1 for a speedrun VOD")
for c in ("context", "faces"):
    s = sub.add_parser(c); s.add_argument("slug"); s.add_argument("ep", type=int)
s = sub.add_parser("prep"); s.add_argument("slug"); s.add_argument("ep", help="episode number or 'all'")
s = sub.add_parser("stats"); s.add_argument("session", help="session id (prefix) or .jsonl path")
s = sub.add_parser("draft"); s.add_argument("slug"); s.add_argument("ep", type=int); s.add_argument("--force", action="store_true")
s = sub.add_parser("publish"); s.add_argument("edl")
g = s.add_mutually_exclusive_group(); g.add_argument("--at", help="schedule: ISO time, e.g. 2026-10-30T16:00:00+02:00")
g.add_argument("--now", action="store_true", help="make public immediately")
s = sub.add_parser("frames"); s.add_argument("slug"); s.add_argument("times", nargs="+")
s.add_argument("--guest", action="store_true", help="the co-op partner's view (footage/<slug>-guest.mp4)")
s = sub.add_parser("look"); s.add_argument("edl"); s.add_argument("times", nargs="*", metavar="M:SS")
s.add_argument("--short", type=int, metavar="K", help="Short K instead of the episode"); s.add_argument("--last", type=float, metavar="S", help="3 frames over the last S seconds")
s = sub.add_parser("at"); s.add_argument("edl"); s.add_argument("times", nargs="+", metavar="M:SS")
s.add_argument("--vod", action="store_true", help="the times are VOD times: where they land in the episode")
s = sub.add_parser("speakers"); s.add_argument("slug"); s.add_argument("--host"); s.add_argument("--guest")
s = sub.add_parser("assemble"); s.add_argument("slug"); s.add_argument("--game", required=True, help="your gameplay recording (the clock)")
for f in ("--cam", "--guest-cam", "--guest-game"):
    s.add_argument(f)
s.add_argument("--kdenlive", help="Kdenlive project with the files aligned on its timeline")
s.add_argument("--offset", action="append", metavar="ROLE=M:SS", help="cam/guestcam/guestgame: where its 0:00 is on the gameplay clock (-m:ss if it started first)")
for f in ("--cam-box", "--guest-cam-box", "--guest-game-box"):
    s.add_argument(f, metavar="X,Y,W", help="box in gameplay pixels, height from the source's aspect; negative X/Y count from the right/bottom")
s.add_argument("--gain", action="append", metavar="ROLE=DB", help="game/cam/guestcam: dB on top of the measured level")
s.add_argument("--preview", metavar="M:SS", help="only a 20 s clip from there → work/<slug>/assemble-preview.mp4")
s.add_argument("--cutout", action="store_true", help="webcam backgrounds transparent (GPU matting; boxes side by side on the bottom edge)")
for c in ("check", "script", "shorts", "retention", "proof", "see", "render"):
    s = sub.add_parser(c); s.add_argument("edl")
    if c == "proof":
        s.add_argument("--read", action="store_true", help="the text file was read whole and fixed: stamp it so render accepts it")
s.add_argument("--patch", nargs="?", const="auto", metavar="RANGES",
               help="re-render only what changed and splice it in: auto (default; diff against the last render), end, "
                    "m:ss-m:ss output-time ranges, comma-separated (e.g. auto,end or 12:30-13:10)")
a = ap.parse_args()
{"stats": lambda a: run(PY, "scripts/session_stats.py", a.session), "ingest": ingest, "split": split, "context": context, "draft": draft, "faces": faces, "frames": frames, "prep": prep, "speakers": speakers_cmd, "assemble": lambda a: __import__("assemble").assemble(a),
 "check": check, "render": render, "look": look, "at": at, "script": script, "proof": proof, "see": see, "shorts": shorts, "publish": publish, "retention": retention}[a.cmd](a)
