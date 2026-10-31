"""Let's play pipeline driver. Every step is resumable: outputs that already exist are kept.

  lp.py ingest <vod.mp4> [--slug S] [--game G]  copy VOD, transcribe, loudness map, language per 10 s (+ game module,
                                                e.g. --game chaosmod: GTA V Chaos Mod effect OCR)
  lp.py split <slug> [--target 25] [--parts N]  split into episodes of ~target edited minutes at speech gaps → work/<slug>/parts.json
  lp.py speakers <slug> --host B --guest B      co-op stream with two webcams: who says each line (B = x,y,w,h lower-face box)
  lp.py context <slug> <ep>                     transcript + effects + English stretches + loud moments, for writing the EDL
  lp.py draft <slug> <ep> [--force]             first-pass EDL: ranges without cutscenes, effects with names, chapters, metadata
  lp.py faces <slug> <ep>                       contact sheet of the episode's liveliest webcam moments (thumbnail face)
  lp.py frames <slug> <t> [<t> ...]             contact sheet of VOD frames at the given times
  lp.py prep <slug> <ep|all>                    graded episode source at native resolution → public/<slug>-ep<ep>.mp4
  lp.py check <edits/x.json>                    build the timeline and render a grid of check stills
  lp.py script <edits/x.json>                   the finished edit as a timed script (speech, cuts, captions, banners) to review
  lp.py shorts <edits/x.json>                   (re)render the EDL's Shorts → out/<playlist>/shorts/ (a full render does this too)
  lp.py render <edits/x.json> [--patch [R]]     build, render, master to −14 LUFS, thumbnail → out/<playlist>/<output>.{mp4,jpg,description.txt}
                                                --patch: re-render only changed parts and splice them into the existing mp4
  lp.py stats <session-id>                      token use, wall time and tool activity of a Claude Code session
  lp.py publish <edits/x.json> [--at ISO|--now] wait for the user's Studio upload, then apply details, subtitles, playlist;
                                                schedule/publish only with an explicit --at/--now (the user's go)
"""
import argparse, json, os, re, shutil, subprocess, sys, time, wave
from difflib import SequenceMatcher
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trimming import loud_db, merge, trim
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.config import CFG, out_dir, text

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


def video_encoder():
    """NVENC when this machine has a working NVIDIA encoder, else x264 at the same quality target."""
    ok = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1", "-c:v", "h264_nvenc",
                         "-f", "null", "-"], capture_output=True).returncode == 0
    return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "17", "-b:v", "0"] if ok else ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]
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
    if game == "chaosmod" and not os.path.exists(f"{w}/effects.json"):
        game_lib(slug)  # fails early with instructions if the effect name list hasn't been built yet
        run(PY, "games/chaosmod/ocr_effects.py", vod, 0, dur, f"{w}/effects.json")
    print(f"ingested {slug}: {dur / 60:.0f} min")


def split(a):
    """Cut where the auto-trimmed running time reaches each episode's share, snapped to a speech pause nearby."""
    w = f"work/{a.slug}"
    dur = meta(a.slug)["duration"]
    S = json.load(open(f"{w}/transcript.json"))["segments"]
    words = [x for s in S for x in s["words"]]
    rms = np.load(f"{w}/rms100ms.npy")
    kept = np.zeros(int(dur) + 1)
    for x, y in trim(words, rms, 0, dur, loud_db(rms, 0, dur)):
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
    rows = [(x, f"–{fmt(y)} {mark[who]}{text}") for x, y, text, who in talk]
    lib = game_lib(a.slug)
    rows += [(t, f"[EFFECT] {n} — {lib.desc(n) or '(no description yet)'}") for t, n in effect_events(a.slug, lo, hi)]
    rows += [(x, f"[{lang.upper()} {fmt(x)}–{fmt(y)}] cutscene or mission dialogue; transcript lines here are unreliable")
             for x, y, lang in foreign_runs(a.slug, lo, hi)]
    rows += [(x, f"[REPEATS {fmt(x)}–{fmt(y)}] transcript loops here: hallucinated, not what was said") for x, y in repeat_runs(segments)]
    rms = np.load(f"{w}/rms100ms.npy")
    loud = [[t, t + 5, rms[t * 10:(t + 5) * 10].max(initial=-99)] for t in range(int(lo), int(hi), 5)]
    loud = [x for x in loud if x[2] > LOUD_DB]
    for x, y in merge([x[:2] for x in loud], 0.1):  # loud game moments, merged into stretches
        rows.append((x, f"[LOUD {fmt(x)}–{fmt(y)} peak {max(p for a, b, p in loud if x <= a < y):.0f} dB]"))
    out = f"{w}/ep{a.ep}.context.txt"
    with open(out, "w") as fh:
        fh.write(f"# episode {a.ep}: VOD {fmt(lo)}–{fmt(hi)} ({(hi - lo) / 60:.1f} min raw). Times are VOD m:ss; speech lines "
                 "show start –end. [EFFECT] lists what OCR read; effects it missed (flipped/hidden HUD) are still on the vote "
                 "list in `frames` — look names up in games/chaosmod/names.json."
                 + (" [GUEST] lines are the co-op partner talking (their gameplay is not in this stream), [?] unclear."
                    if spk else "") + "\n")
        fh.writelines(f"{fmt(t)} {txt}\n" for t, txt in sorted(rows))
    print(out, len(rows), "lines")


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
    run(PY, "scripts/speakers.py", a.slug, a.host, a.guest)


def sibling_edl(slug, ep):
    """The nearest other episode's EDL of the same VOD, to copy series metadata from."""
    edls = [json.load(open(f"edits/{f}")) for f in os.listdir("edits") if f.endswith(".json")]
    eps = sorted(((abs(e["episode"] - ep), e["episode"]), e) for e in edls if e.get("vod") == slug and e["episode"] != ep)
    return eps[0][1] if eps else None


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
    kept = [k for k in trim(words, rms, lo, hi, loud_db(rms, lo, hi)) if not any(x < k[1] and k[0] < y for x, y in skip)]
    blocks = [b for b in merge(kept, 8.0) if b[1] - b[0] >= 4]
    # intro: the first ~45 s of talk; cold open: the liveliest 12 s later on (loudness while talking)
    intro, rest = [], []
    for b in blocks:
        (intro if sum(y - x for x, y in intro) < 40 and b[0] < lo + 120 else rest).append(b)
    def liveliness(t):
        talk = any(w["start"] < t + 12 and w["end"] > t for w in words if t - 1 < w["start"] < t + 13)
        return rms[int(t * 10):int((t + 12) * 10)].mean() + (10 if talk else -50)
    cands = [t for b in rest if b[0] > lo + 180 for t in np.arange(b[0], b[1] - 12, 2.0)]
    cold = max(cands, key=liveliness) if cands else rest[0][0]
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
    title.update(episode=text("episode", n=a.ep), bg=fmt(cold))
    thumb = copy("thumb", {"bgZoom": 1.2, "bgOrigin": "60% 50%", "tag": "TODO"})
    thumb.update(bg=fmt(cold), face=fmt(cold), tag=re.sub(r"#\d+", f"#{a.ep}", thumb.get("tag", "TODO")), text="TODO")
    output = re.sub(r"\d+$", str(a.ep), sib["output"]) if sib.get("output") else text("episode_title", series="TODO", n=a.ep)
    e = {"vod": a.slug, "episode": a.ep, "output": output, "style": sib.get("style", "hype"),
         "playlist": sib.get("playlist", "TODO"), "tags": sib.get("tags", []),
         "cam": sib.get("cam", [990, 480, 290, 240]), "thumb": thumb, "title": title,
         "lowerThird": {**copy("lowerThird", {"text": CFG["channel"], "sub": "TODO"}), "at": fmt(rest[0][0] + 3)},
         "coldOpen": [[fmt(cold), fmt(cold + 12), "full"]], "intro": [[fmt(x), fmt(y)] for x, y in intro],
         "main": [[fmt(x), fmt(y)] for x, y in rest], "effects": effects, "captions": [], "faceZooms": [], "gameZooms": [],
         "chapters": chapters, "endFreeze": {"text": text("to_be_continued") if a.ep < n_parts else text("the_end"), "seconds": 2.5},
         "endScreen": {"seconds": 15, "title": text("coming_next", n=a.ep + 1) if a.ep < n_parts else text("thanks"),
                       "cta": text("subscribe")},
         "shorts": [], "description": "TODO", "en": {"title": "TODO", "description": "TODO", "chapters": ["TODO"] * len(chapters)}}
    json.dump(e, open(path, "w"), indent=1, ensure_ascii=False)
    raw = sum(y - x for x, y in kept if x >= rest[0][0]) if rest else 0
    print(f"{path}: {len(rest)} main ranges (~{raw * EDIT_RATIO / 60:.0f} min after trimming), {len(effects)} effects "
          f"({sum(x[2] == 'TODO' for x in effects)} need a description), {len(chapters)} chapters, "
          f"{len(skip)} English/hallucinated stretches left out. TODO: cut weak ranges, captions, zooms, chapter labels, "
          "thumbnail, title/description.")


def script(a):
    """The finished edit as a timed script, for reviewing it the way a viewer meets it: kept speech per clip in output
    time, jump cuts and whoosh transitions, captions, banners, zooms, chapters. Written to work/<vod>/epN.script.txt."""
    edl, e = build(a.edl)
    fps, w = e["fps"], f"work/{edl['vod']}"
    off = part(edl["vod"], edl["episode"])["prepStart"]
    segments, spk = json.load(open(f"{w}/transcript.json"))["segments"], speakers(edl["vod"])
    rows = []
    for c in e["clips"]:
        a0, a1 = c["src"] / fps + off, (c["src"] + c["dur"] * c.get("rate", 1)) / fps + off
        said = " ".join(("[GUEST] " if spk.get(s["start"]) == "guest" else "") + " ".join(x["word"].strip() for x in s["words"] if a0 <= x["start"] < a1)
                        for s in segments if any(a0 <= x["start"] < a1 for x in s["words"]))
        cut = ("~~ whoosh ~~ " if c.get("whoosh") else "| ") + (f"(x{c['rate']:g}) " if "rate" in c else "")
        rows.append((c["from"], f"{cut}[{c['section']} {fmt(a0)}] {said}"))
    rows += [(c["at"], f"   CAPTION {c['text']}") for c in e["captions"]]
    rows += [(x["at"], f"   BANNER {x['name']} — {x['fi']}") for x in e["effects"]]
    rows += [(z["at"], "   FACE ZOOM") for z in e["faceZooms"]] + [(z["at"], "   GAME ZOOM") for z in e["gameZooms"]]
    rows += [(p["at"], "   PUNCH") for p in e.get("punches", [])]
    rows += [(e["title"]["from"], "== TITLE CARD =="), (e["lowerThird"]["from"], "   LOWER THIRD"),
             (e["freeze"]["from"], f"== FREEZE {e['freeze']['text']} =="), (e["end"]["from"], "== END SCREEN ==")]
    desc = open(f"{out_dir(edl)}/{edl['output']}.description.txt").read()
    rows += [(round(sum(float(v) * 60 ** i for i, v in enumerate(reversed(m[0].split(":")))) * fps), f"## CHAPTER {m[1]}")
             for m in re.findall(r"^(\d+:\d\d) (.+)$", desc, re.M)]
    out = f"{w}/ep{edl['episode']}.script.txt"
    with open(out, "w") as fh:
        fh.writelines(f"{fmt(f / fps)} {txt}\n" for f, txt in sorted(rows, key=lambda r: r[0]))
    print(out, f"{e['duration'] / fps / 60:.1f} min")


def faces(a):
    """Liveliest webcam moments (movement in the face area, 4 fps), one per 20 s, as a contact sheet."""
    p = part(a.slug, a.ep)
    own = f"edits/{a.slug}-ep{a.ep}.json"  # this episode's cam first: siblings may not exist yet when episodes run in parallel
    sib = (json.load(open(own)) if os.path.exists(own) else None) or sibling_edl(a.slug, a.ep) or {}
    if not sib.get("cam"):
        sys.exit(f"no \"cam\" in {own} or a sibling EDL: set it (webcam rect in VOD pixels) before running faces")
    x, y, cw, ch = sib["cam"]
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


def frames(a):
    out = f"work/{a.slug}/frames"
    os.makedirs(out, exist_ok=True)
    tiles = []
    for t in a.times:
        f = f"{out}/{t.replace(':', '_')}.jpg"
        secs = sum(float(x) * 60 ** i for i, x in enumerate(reversed(t.split(":"))))
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", secs, "-i", f"footage/{a.slug}.mp4", "-frames:v", "1",
            "-vf", f"scale={TILE_W}:-2,drawtext=text='{t.replace(':', '.')}':x=6:y=6:fontsize=22:fontcolor=yellow:box=1:boxcolor=black", f)
        tiles.append(f)
    cols = min(3, len(tiles))
    sheet = f"{out}/sheet-{a.times[0].replace(':', '_')}-{len(tiles)}.jpg"  # one file per request, never overwritten
    inputs = [x for f in tiles for x in ("-i", f)]
    layout = "|".join(f"{i % cols * TILE_W}_{i // cols * TILE_W * 9 // 16}" for i in range(len(tiles)))
    run("ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex",
        f"xstack=inputs={len(tiles)}:layout={layout}:fill=black" if len(tiles) > 1 else "null", sheet)
    print(sheet)


def prep(a):
    if a.ep == "all":
        for n in range(1, len(json.load(open(f"work/{a.slug}/parts.json"))) + 1):
            prep(argparse.Namespace(slug=a.slug, ep=str(n)))
        return
    a.ep = int(a.ep)
    p, out = part(a.slug, a.ep), f"public/{a.slug}-ep{a.ep}.mp4"
    if os.path.exists(out):
        return print(out, "exists")
    off, dur = p["prepStart"], p["prepEnd"] - p["prepStart"]
    # native resolution, never upscaled: lift shadows, light sharpening
    run("ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", off, "-t", dur, "-i", f"footage/{a.slug}.mp4",
        "-vf", "curves=master='0/0 0.12/0.17 0.35/0.42 0.7/0.74 1/1',eq=saturation=1.08,cas=0.3",
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
    run("npx", "remotion", *args, f"--props={props or props_path(edl)}", "--log=error", env={"TMPDIR": TMP})


def check(a):
    edl, e = build(a.edl)
    problems = build_shorts(edl, e)[1] + ([] if edl.get("shorts") else ["no shorts picked: add 2–4 to \"shorts\""])
    if problems:
        sys.exit("\n".join(problems))
    first = lambda xs: xs[0]["at"] + 30 if xs else e["clips"][len(e["clips"]) // 3]["from"]
    stack = next((c["at"] + 30 for c in e["captions"] if c.get("slot")), first(e["captions"]))
    picks = [e["title"]["from"] + 120, first(e["faceZooms"]), stack, first(e["effects"]) + 10,
             e["clips"][len(e["clips"]) // 2]["from"] + 10, e["lowerThird"]["from"] + 40, e["freeze"]["from"] + 90, e["end"]["from"] + 200]
    d = f"work/{edl['vod']}/check"
    os.makedirs(d, exist_ok=True)
    for f in picks:
        remotion(edl, "still", "src/index.ts", "LetsPlay", f"{d}/{f}.jpg", f"--frame={f}", f"--scale={scale(edl)}")
    inputs = [x for f in picks for x in ("-i", f"{d}/{f}.jpg")]
    sheet = f"work/{edl['vod']}/ep{edl['episode']}-check.jpg"
    w, h = meta(edl["vod"])["width"], meta(edl["vod"])["height"]
    layout = "|".join(f"{i % 2 * w}_{i // 2 * h}" for i in range(8))
    run("ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", f"xstack=inputs=8:layout={layout},scale=1280:-2", sheet)
    print(sheet)


MASTER = "acompressor=threshold=-24dB:ratio=2.5:attack=8:release=180:makeup=2,loudnorm=I=-14:TP=-1:LRA=11"


SR = 48000
SFX_TAIL = 120  # frames a sound effect may ring on after its element ends


def render(a):
    edl, e = build(a.edl)
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
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", raw, "-c:v", "copy", "-af", MASTER,
            "-ar", SR, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", f"{out}.mp4")
        os.remove(raw)
    json.dump(e, open(state_path(edl, "rendered.json"), "w"))
    remotion(edl, "still", "src/index.ts", "Thumbnail", f"{out}.jpg")
    if not ranges:  # full render: the Shorts too (a patch leaves them alone; `lp.py shorts` re-renders them)
        render_shorts(edl, e)
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
        spans.append((f"clip{i}", c, c["from"] - (20 if c.get("whoosh") else 0), c["from"] + c["dur"]))
    for k, n in (("effects", 212), ("captions", 132)):
        spans += [(f"{k}{i}", x, x["at"], x["at"] + x.get("dur", n)) for i, x in enumerate(e[k])]
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
        if any(old.get(k) != e.get(k) for k in ("fps", "source", "cam", "style")):
            print("source, webcam or style changed: full render")
            return None
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


def keyframes(path, fps):
    return [round(float(l.split(",")[0]) * fps) for l in subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", path],
        text=True).splitlines() if "K" in l.split(",")[1]]


def render_patch(edl, e, out, common, ranges):
    """Re-render only the given output frame ranges and splice them into the existing episode file.

    Video: each range widens to the old file's keyframes (closed GOPs), so the unchanged pieces are stream-copied;
    pieces are cut by frame count in decode order, never by time (B-frames). Audio: the kept unmastered mix with the
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
        b = min((k for k in keys if k >= b), default=total)
        if segs and a <= segs[-1][1]:
            segs[-1][1] = max(segs[-1][1], b)
        else:
            segs.append([a, b])
    print("re-rendering", ", ".join(f"{a / fps / 60:.0f}:{a / fps % 60:04.1f}–{b / fps / 60:.0f}:{b / fps % 60:04.1f}" for a, b in segs),
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
            remotion(edl, "render", "src/index.ts", "LetsPlay", f, *common, "--crf=17", "--audio-bitrate=320k", f"--frames={a}-{b - 1}")
            w = f"{work_tmp}/piece{i}.wav"
            run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", f, "-vn", "-ar", SR, "-af", f"apad=whole_len={(b - a) * spf},atrim=end_sample={(b - a) * spf}",
                "-c:a", "pcm_s16le", w)
            tmp.append(w)
            audio.append(w)
        else:
            seek = ["-ss", f"{a / fps:.6f}"] if a else []
            run("ffmpeg", "-nostdin", "-v", "error", "-y", *seek, "-i", old, "-map", "0:v", "-c", "copy", "-frames:v", b - a, f)
            w = f"{work_tmp}/piece{i}.wav"
            run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", state_path(edl, "mix.wav"), "-af",
                f"atrim=start_sample={a * spf}:end_sample={b * spf},asetpts=N/SR/TB", "-c:a", "pcm_s16le", w)
            tmp.append(w)
            audio.append(w)
    lst, mix_new, new = f"{work_tmp}/concat.txt", f"{work_tmp}/mix.wav", f"{out}.new.mp4"
    with open(lst, "w") as fh:
        fh.writelines(f"file '{os.path.abspath(f)}'\n" for f in tmp if f.endswith(".mp4"))
    run("ffmpeg", "-nostdin", "-v", "error", "-y", *[x for w in audio for x in ("-i", w)], "-filter_complex",
        "".join(f"[{i}:a]" for i in range(len(audio))) + f"concat=n={len(audio)}:v=0:a=1", "-c:a", "pcm_s16le", mix_new)
    run("ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-i", mix_new, "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-af", MASTER, "-ar", SR, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", new)
    frames = int(subprocess.check_output(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v", "-show_entries",
                                          "stream=nb_read_packets", "-of", "csv=p=0", new], text=True))
    if frames != total:
        sys.exit(f"patch produced {frames} frames, expected {total}; {old} left unchanged")
    os.replace(new, old)
    os.replace(mix_new, state_path(edl, "mix.wav"))
    for f in tmp + [lst]:
        os.remove(f)


LINK_TODO = "(link)"  # replaced by the episode's URL once it is known
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


def build_shorts(edl, e):
    """Props for each Short in the EDL: a continuous VOD stretch, with the episode's captions and banners that fall in it."""
    fps, off = e["fps"], part(edl["vod"], edl["episode"])["prepStart"]
    vod_time = lambda f: next(((c["src"] + (f - c["from"]) * c.get("rate", 1)) / fps + off for c in e["clips"] if c["from"] <= f < c["from"] + c["dur"]), None)
    tag = re.sub(r"\s*#\d+$", "", edl["thumb"].get("tag", ""))
    out, problems = [], []
    for k, sh in enumerate(edl.get("shorts", []), 1):
        a, b = parse_time(sh["from"]), parse_time(sh["to"])
        p = part(edl["vod"], edl["episode"])
        if not SHORT_MIN <= b - a <= SHORT_MAX or a < p["prepStart"] or b > p["prepEnd"]:
            problems.append(f"short {k} ({sh['from']}–{sh['to']}): must be {SHORT_MIN}–{SHORT_MAX} s inside this episode's footage")
            continue
        if (g := guest_share(edl["vod"], a, b)) > 0.35:
            problems.append(f"short {k} ({sh['from']}–{sh['to']}): {g:.0%} of the talking is the co-op guest, whose gameplay "
                            "isn't in this stream; pick a moment of the streamer's own")
            continue
        def inside(items, key):
            seen, res = set(), []
            for x in items:
                t = vod_time(x["at"])
                if t is not None and a <= t < b - 1 and x[key] not in seen:  # cold-open repeats map to the same moment
                    seen.add(x[key])
                    res.append({**x, "at": round((t - a) * fps)})
            return res
        out.append({"short": {"source": e["source"], "fps": fps, "style": e["style"], "src": round((a - off) * fps),
                              "dur": round((b - a) * fps), "cropX": sh.get("cropX", 420), "cam": e["cam"], "title": sh["title"],
                              "tag": tag, "cta": text("full_episode", episode=edl["title"].get("episode", "")).strip(),
                              "text": {"channel": CFG["channel"], "from_stream": text("from_stream"),
                                       "effect_label": effect_label(edl)},
                              "captions": inside(e["captions"], "text"), "effects": inside(e["effects"], "name")}})
    return out, problems


def render_shorts(edl, e):
    shorts, problems = build_shorts(edl, e)
    if problems:
        sys.exit("\n".join(problems))
    os.makedirs(f"{out_dir(edl)}/shorts", exist_ok=True)
    yt_id = json.load(open(state_path(edl, "youtube.json")))["id"] if os.path.exists(state_path(edl, "youtube.json")) else None
    for k, props in enumerate(shorts, 1):
        pf, name = state_path(edl, f"short{k}.props.json"), short_name(edl, k)
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
            fh.write(f"{sh['title'].capitalize()[:90]} #shorts\n\n{text('short_description', output=edl['output'], link=link)}\n\n"
                     + " ".join("#" + re.sub(r"\W", "", t) for t in edl.get("tags", [])[:5]) + "\n")
        print(f"{name}.mp4  {props['short']['dur'] / e['fps']:.0f} s")


def shorts(a):
    edl, e = build(a.edl)
    render_shorts(edl, e)


def publish(a):
    """Wait for the user's Studio upload of this episode (matched by length, ±2 s), then fill it in: details, thumbnail,
    subtitles, English translation, playlist. The video id is kept in work/<vod>/epN.youtube.json. Visibility changes
    only with --at/--now, which the user must have asked for."""
    import youtube_mcp as yt
    edl = json.load(open(a.edl))
    out, state = f"{out_dir(edl)}/{edl['output']}.mp4", state_path(edl, "youtube.json")
    length = probe_duration(out)
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
s = sub.add_parser("speakers"); s.add_argument("slug"); s.add_argument("--host", required=True); s.add_argument("--guest", required=True)
for c in ("check", "script", "shorts", "render"):
    s = sub.add_parser(c); s.add_argument("edl")
s.add_argument("--patch", nargs="?", const="auto", metavar="RANGES",
               help="re-render only what changed and splice it in: auto (default; diff against the last render), end, "
                    "m:ss-m:ss output-time ranges, comma-separated (e.g. auto,end or 12:30-13:10)")
a = ap.parse_args()
{"stats": lambda a: run(PY, "scripts/session_stats.py", a.session), "ingest": ingest, "split": split, "context": context, "draft": draft, "faces": faces, "frames": frames, "prep": prep, "speakers": speakers_cmd,
 "check": check, "render": render, "script": script, "shorts": shorts, "publish": publish}[a.cmd](a)
