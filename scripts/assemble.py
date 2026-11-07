"""Separately recorded sources, kept as separate tracks. Two jobs:
- assemble(): one reference VOD for `lp.py ingest`, frames and the vision checks: your gameplay full frame, both webcams
  as plain boxes, one mix of the game audio and both mics. With the partner's gameplay (--guest-game) a second reference
  on the same clock, footage/<slug>-guest.mp4: their gameplay full frame (black where it doesn't run), the same webcams.
  --guest-game-box puts their gameplay as a box in your view instead (picture-in-picture, baked, no guest tracks).
- tracks(): per episode (`lp.py prep`), each source cut to the episode on the VOD clock as its own file: your game
  (graded, game audio), the partner's game, each webcam at its box size with its mic. With --cutout the webcams'
  backgrounds are matted (matte.py) for the episode's range only and kept as alpha (VP9 WebM). The render composites
  the tracks: nothing but the reference is baked, so views, boxes and cut-outs stay editable.

The files share no audio to line them up by (game audio only in the gameplay files, each mic only in its webcam file),
so the sync comes from a Kdenlive project where they were aligned by hand (--kdenlive), or --offset role=m:ss (where the
source's 0:00 falls on the gameplay's clock; negative when it started first). A clip cut and re-aligned later in
Kdenlive corrects clock drift: its pieces' offsets are fitted to a line and the source is stretched to it.
→ footage/<slug>.mp4, work/<slug>/assemble.json (sources, sync, boxes, gains, cutout: the track manifest),
work/<slug>/mics.npz (each mic's 100 ms loudness on the VOD clock, gain-matched: `lp.py speakers` labels lines from it)."""
import json, os, shutil, subprocess, sys, xml.etree.ElementTree as ET
import numpy as np
from media import GRADE, video_encoder

MIC_OF = {"cam": "host", "guestcam": "guest"}
OVERLAYS = ("guestgame", "guestcam", "cam")  # drawn in this order, your webcam on top
MIC_DB, GAME_DB = -16, -30  # mic speech peaks (95th percentile of 100 ms RMS) and the game's median, dBFS
PREVIEW_S = 20
MATTE = [shutil.which("uv") or os.path.expanduser("~/.local/bin/uv"), "run", "--no-project", "--with", "onnxruntime-gpu[cuda,cudnn]",
         "--with", "numpy", "python", os.path.join(os.path.dirname(os.path.abspath(__file__)), "matte.py")]


def probe(path):
    j = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
                                            "-of", "json", path]))
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    return {"duration": float(j["format"]["duration"]), "size": (v.get("width"), v.get("height")), "fps": v.get("r_frame_rate"),
            "audio": any(s["codec_type"] == "audio" for s in j["streams"])}


def parse_time(t):
    return sum(float(x) * 60 ** i for i, x in enumerate(reversed(str(t).split(":"))))


def ktime(v, fps):
    """MLT time: frames, clock (00:01:02.345) or SMPTE (00:01:02:20 / ;20)."""
    if ":" not in v and ";" not in v:
        return int(v) / fps
    p = v.replace(";", ":").split(":")
    return sum(float(x) * 60 ** i for i, x in enumerate(reversed(p[:3]))) + float(p[3]) / fps if len(p) == 4 else parse_time(v)


def kdenlive_sync(project, files):
    """{role: (d, k)} from a Kdenlive project: source time s plays at timeline time d + k*s."""
    root = ET.parse(project).getroot()
    p = root.find("profile")
    fps = int(p.get("frame_rate_num")) / int(p.get("frame_rate_den"))
    base = root.get("root") or os.path.dirname(os.path.abspath(project))

    def prop(el, name):
        return next((x.text for x in el.findall("property") if x.get("name") == name), None)
    src = {}
    for el in root:
        if el.tag in ("producer", "chain") and (r := prop(el, "kdenlive:originalurl") or prop(el, "resource")):  # originalurl: proxied clips
            src[el.get("id")] = os.path.realpath(os.path.join(base, r))
    pts = {}
    for pl in root.iter("playlist"):
        if pl.get("id") == "main_bin":  # the project bin, not the timeline
            continue
        pos = 0.0
        for el in pl:
            if el.tag == "blank":
                pos += ktime(el.get("length"), fps)
            elif el.tag == "entry":
                a, b = ktime(el.get("in"), fps), ktime(el.get("out"), fps)
                if el.get("producer") in src:
                    pts.setdefault(src[el.get("producer")], set()).add((round(a, 4), round(pos, 4)))
                pos += b - a + 1 / fps
    out = {}
    for role, f in files.items():
        if not (pt := sorted(pts.get(os.path.realpath(f), ()))):
            continue
        a, t = np.array(pt).T
        k, d = np.polyfit(a, t, 1) if np.ptp(t - a) > 1e-3 else (1.0, float((t - a)[0]))
        out[role] = (float(d), float(k))
    return out


def sync_of(a, files):
    """{role: (d, k)} on the gameplay's clock, from --kdenlive and --offset (an --offset wins)."""
    tl = kdenlive_sync(a.kdenlive, files) if a.kdenlive else {}
    if tl and "game" not in tl:
        sys.exit(f"{a.game} is not on the timeline of {a.kdenlive}")
    dg, kg = tl.get("game", (0.0, 1.0))
    sync = {r: ((d - dg) / kg, k / kg) for r, (d, k) in tl.items()}
    for o in a.offset or []:
        r, t = o.split("=", 1)
        sync[r] = (-parse_time(t[1:]) if t.startswith("-") else parse_time(t), 1.0)
    if missing := [r for r in files if r not in sync]:
        sys.exit(f"no sync for {', '.join(missing)}: align the files in Kdenlive and pass --kdenlive <project>, "
                 f"or --offset {missing[0]}=m:ss")
    return sync


def seek(sync, role, dur, S):
    """Input seek and delay so the source lines up with VOD time S; None when it has ended by S."""
    d, k = sync[role]
    ss = max(0.0, (S - d) / k)
    return None if ss >= dur else (ss, max(0.0, d - S))


def envelope(path, ss, delay, k, total):
    """100 ms RMS (dB) of the file's audio placed on the VOD clock."""
    af = f"atempo={1 / k:.9f},adelay={delay * 1000:.0f}:all=1,apad"
    proc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{ss:.3f}", "-i", path, "-vn", "-af", af, "-t", f"{total:.3f}",
                             "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], stdout=subprocess.PIPE)
    out, blk = [], 1600 * 600  # a minute at a time
    while (buf := proc.stdout.read(blk * 2)):
        x = np.frombuffer(buf, np.int16).astype(np.float32) / 32768
        x = x[:len(x) // 1600 * 1600].reshape(-1, 1600)
        out.append(20 * np.log10(np.sqrt((x ** 2).mean(1)) + 1e-9))
    if proc.wait():
        sys.exit(f"ffmpeg failed reading {path}")
    env, n = np.concatenate(out)[:int(total * 10)], int(total * 10)
    return np.pad(env, (0, n - len(env)), constant_values=-180)


def levels(files, sync, info, total, w, roles):
    """Gains (dB) that put both mics' speech at MIC_DB and each game's median at GAME_DB; mics.npz on the way."""
    old = json.load(open(f"{w}/assemble.json")) if os.path.exists(f"{w}/assemble.json") else {}
    if os.path.exists(f"{w}/mics.npz") and old.get("sync") == {r: list(v) for r, v in sync.items()} and set(roles) <= set(old["measured"]):
        return old["measured"]  # measured with this sync
    gains, mics = {}, {}
    for r in roles:
        if not info[r]["audio"]:
            sys.exit(f"{files[r]} has no audio")
        ss, delay = seek(sync, r, info[r]["duration"], 0)
        env = envelope(files[r], ss, delay, sync[r][1], total)
        print(f"{r}: measured {len(env) / 600:.0f} min of audio", flush=True)
        live = env[env > -60]
        gains[r] = round(float(MIC_DB - np.percentile(live, 95) if r in MIC_OF else GAME_DB - np.median(live)), 1) if len(live) else 0.0
        if r in MIC_OF:
            mics[MIC_OF[r]] = (env + gains[r]).astype(np.float32)
    np.savez(f"{w}/mics.npz", **mics)
    return gains


def command(files, sync, info, boxes, gains, S, T, out, mattes={}, view="host"):
    """ffmpeg command for VOD time S..S+T: overlays and the audio mix, each source seeked to its own clock.
    mattes: {role: (matte file, source time its first frame is)} → that webcam's background transparent.
    view "guest": the partner's gameplay full frame over black on your clock, with their game audio instead of yours."""
    W, H = info["game"]["size"]
    fv, v = [], "[0:v]"
    if view == "host":
        ins, fa, mix = ["-ss", f"{S:.3f}", "-i", files["game"]], [f"[0:a]aresample=48000,volume={gains['game']}dB[a0]"], "[a0]"
        roles, sound = [r for r in OVERLAYS if r in boxes], set(MIC_OF)
    else:
        ins, fa, mix = ["-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={info['game']['fps']}:d={T:.3f}"], [], ""
        roles, sound, boxes = OVERLAYS, {"guestgame", *MIC_OF}, {**boxes, "guestgame": [0, 0, W, H]}
    for r in [r for r in roles if r in files]:
        if not (sk := seek(sync, r, info[r]["duration"], S)):
            continue
        n, (ss, delay), k = len(ins) // 4, sk, sync[r][1]
        ins += ["-ss", f"{ss:.3f}", "-i", files[r]]
        x, y, bw, bh = boxes[r]
        pts = f"setpts={k:.9f}*(PTS-STARTPTS)+{delay:.3f}/TB[v{n}]"
        if r in mattes:
            ins += ["-ss", f"{ss - mattes[r][1]:.3f}", "-i", mattes[r][0]]
            fv += [f"[{n}:v]scale={bw}:{bh},format=yuva420p[c{n}]", f"[{n + 1}:v]scale={bw}:{bh},format=gray[m{n}]",
                   f"[c{n}][m{n}]alphamerge,{pts}"]
        else:
            fv.append(f"[{n}:v]scale={bw}:{bh},{pts}")
        fv.append(f"{v}[v{n}]overlay={x}:{y}:eof_action=pass[o{n}]")
        v = f"[o{n}]"
        if r in sound:
            fa.append(f"[{n}:a]aresample=48000,atempo={1 / k:.9f},adelay={delay * 1000:.0f}:all=1,volume={gains[r]}dB[a{n}]")
            mix += f"[a{n}]"
    graph = ";".join(fv + [f"{v}format=yuv420p[v]"] + fa + [f"{mix}amix=inputs={len(fa)}:normalize=0:duration={"first" if view == "host" else "longest"},apad,alimiter=limit=0.95[a]"])
    return ["ffmpeg", "-nostdin", "-v", "error", "-stats", "-stats_period", "60", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
            "-t", f"{T:.3f}", *video_encoder(), "-c:a", "aac", "-b:a", "256k", "-f", "mp4", out]


def box(spec, native, W, H, default):
    """x,y,w (height from the source's aspect; never wider than the source: no upscaling) → x,y,w,h, even sizes."""
    x, y, bw = (int(v) for v in spec.split(",")) if spec else default
    nw, nh = native
    bw = min(bw, nw) // 2 * 2
    bh = round(bw * nh / nw) // 2 * 2
    return [max(0, min(x if x >= 0 else W + x - bw, W - bw)), max(0, min(y if y >= 0 else H + y - bh, H - bh)), bw, bh]


def matte(files, sync, info, w, S, T, tag):
    """Alpha mattes of the webcams for VOD time S..S+T (matte.py, both at once on the GPU) → {role: (file, source start)}."""
    mattes, procs = {}, []
    for r in [r for r in MIC_OF if r in files]:
        if not (sk := seek(sync, r, info[r]["duration"], S)) or sk[1] >= T:
            continue
        out, start = f"{w}/matte-{r}-{tag}.mp4", sk[0]
        mattes[r] = (out, start)
        procs.append(subprocess.Popen(MATTE + [files[r], out, f"{start:.3f}", f"{(T - sk[1]) / sync[r][1] + 1:.3f}"]))
    if procs:
        print(f"matting {len(procs)} webcam(s), {T / 60:.0f} min", flush=True)
    if any(p.wait() for p in procs):
        sys.exit("matting failed")
    return mattes


def track_cmd(files, sync, info, boxes, gains, r, S, T, fps, out, matte=None):
    """One source cut to VOD time S..S+T on its own clock: exactly T long (black, or transparent for a cut-out webcam,
    where it doesn't run), at its box size, with its own audio at its gain."""
    W, H = info["game"]["size"]
    ss, delay = seek(sync, r, info[r]["duration"], S)
    k = sync[r][1]
    bw, bh = (W, H) if r in ("game", "guestgame") else boxes[r][2:]
    base = f"color=black{'@0' if matte else ''}:s={bw}x{bh}:r={fps}:d={T:.3f}" + (",format=yuva420p" if matte else "")  # in the source: else alpha is lost
    ins = ["-f", "lavfi", "-i", base, "-ss", f"{ss:.3f}", "-t", f"{(T - delay) / k + 1:.3f}", "-i", files[r]]  # bounded: the matte ends there
    pts = f"setpts={k:.9f}*(PTS-STARTPTS)+{delay:.3f}/TB"
    if matte:
        ins += ["-i", matte[0]]
        fv = [f"[1:v]scale={bw}:{bh},format=yuva420p[c]", f"[2:v]scale={bw}:{bh},format=gray[m]", f"[c][m]alphamerge,{pts}[s]",
              "[0:v][s]overlay=eof_action=pass:format=auto,format=yuva420p[v]"]
        enc = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", "-crf", "24", "-b:v", "0",
               "-auto-alt-ref", "0", "-g", "60", "-c:a", "libopus", "-b:a", "160k", "-f", "webm"]
    else:
        fv = [f"[1:v]scale={bw}:{bh}:flags=lanczos,{pts}[s]", f"[0:v][s]overlay=eof_action=pass" + (f",{GRADE}" if r in ("game", "guestgame") else "") + ",format=yuv420p[v]"]
        enc = [*video_encoder(), "-g", "60", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-f", "mp4"]
    fa = f"[1:a]aresample=48000,atempo={1 / k:.9f},adelay={delay * 1000:.0f}:all=1,volume={gains[r]}dB,alimiter=limit=0.95,apad[a]"
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fv + [fa]), "-map", "[v]", "-map", "[a]",
            "-t", f"{T:.3f}", *enc, out]


def tracks(slug, S, T, prefix):
    """Episode tracks for VOD time S..S+T → {role: file}: <prefix>.mp4 (your game), <prefix>-guest.mp4 (the partner's
    game), <prefix>-cam / -guestcam (.webm with alpha when cut out, else .mp4). A source not running in the range is left out."""
    w = f"work/{slug}"
    cfg = json.load(open(f"{w}/assemble.json"))
    files, sync, boxes, gains = cfg["sources"], {r: tuple(v) for r, v in cfg["sync"].items()}, cfg["boxes"], cfg["gains"]
    info = {r: probe(f) for r, f in files.items()}
    fps, cut = info["game"]["fps"], cfg.get("cutout")
    roles = [r for r in ("game", "guestgame", "cam", "guestcam") if r in files and (r != "guestgame" or "guestgame" not in boxes)]
    roles = [r for r in roles if (sk := seek(sync, r, info[r]["duration"], S)) and sk[1] < T]
    ext = lambda r: ".webm" if cut and r in MIC_OF else ".mp4"
    outs = {r: f"{prefix}{'' if r == 'game' else '-guest' if r == 'guestgame' else '-' + r}{ext(r)}" for r in roles}
    todo = [r for r in roles if not os.path.exists(outs[r])]
    mattes = matte({r: files[r] for r in todo}, sync, info, w, S, T, os.path.basename(prefix)) if cut else {}
    procs = [(r, subprocess.Popen(track_cmd(files, sync, info, boxes, gains, r, S, T, fps, outs[r] + ".part", mattes.get(r)))) for r in todo]
    if bad := [r for r, p in procs if p.wait()]:
        sys.exit(f"track {', '.join(bad)} failed")
    for r in todo:
        os.rename(outs[r] + ".part", outs[r])
    for m, _ in mattes.values():
        os.remove(m)
    return outs


def assemble(a):
    files = {r: os.path.abspath(f) for r, f in (("game", a.game), ("cam", a.cam), ("guestcam", a.guest_cam), ("guestgame", a.guest_game)) if f}
    w, vod = f"work/{a.slug}", f"footage/{a.slug}.mp4"
    os.makedirs(w, exist_ok=True)
    if os.path.exists(vod) and not a.preview:
        return print(f"{vod} exists")
    info = {r: probe(f) for r, f in files.items()}
    W, H = info["game"]["size"]
    if abs(W / H - 16 / 9) > 0.01:
        sys.exit(f"{a.game} is {W}x{H}; only 16:9 gameplay is supported")
    sync, total = sync_of(a, files), info["game"]["duration"]
    m, cw = W // 60, W // 5  # margin, default webcam width
    views = ["host", "guest"] if "guestgame" in files and not a.guest_game_box else ["host"]  # partner's gameplay: a second view, or a box
    cams = ((-m, H, cw), (-(2 * m + cw), H, cw)) if a.cutout else ((-m, -m, cw), (-m, -(2 * m + round(cw * 9 / 16)), cw))  # cut-outs: side by side on the bottom edge
    boxes = {r: box(spec, info[r]["size"], W, H, dflt) for r, spec, dflt in (
        ("cam", a.cam_box, cams[0]), ("guestcam", a.guest_cam_box, cams[1]),
        ("guestgame", a.guest_game_box, None)) if r in files and (r != "guestgame" or a.guest_game_box)}
    for r, (d, k) in sync.items():
        print(f"{r}: 0:00 at {d:+.3f} s on the gameplay clock" + (f", drift {(k - 1) * 3600:+.3f} s/h" if k != 1 else ""))
    measured = levels(files, sync, info, total, w, ["game", *(["guestgame"] if "guest" in views else []), *(r for r in MIC_OF if r in files)])
    gains = dict(measured)
    for r, g in (x.split("=", 1) for x in a.gain or []):  # your adjustment on top of the measured level
        gains[r] += float(g)
    json.dump({"sources": files, "sync": {r: list(v) for r, v in sync.items()}, "boxes": boxes, "measured": measured, "gains": gains, "cutout": a.cutout},
              open(f"{w}/assemble.json", "w"), indent=1)
    S = parse_time(a.preview) if a.preview else None
    mattes = matte(files, sync, info, w, S, PREVIEW_S, "preview") if a.cutout and a.preview else {}  # the full reference stays plain boxes
    outs = {"host": f"{w}/assemble-preview.mp4" if a.preview else vod, "guest": f"{w}/assemble-preview-guest.mp4" if a.preview else f"footage/{a.slug}-guest.mp4"}
    procs = [subprocess.Popen(command(files, sync, info, boxes, gains, S or 0, PREVIEW_S if a.preview else total,
                                      outs[v] + ".part.mp4", mattes, v)) for v in views]  # both views at once
    if any(p.wait() for p in procs):
        sys.exit("assembly failed")
    for v in views:
        os.rename(outs[v] + ".part.mp4", outs[v])
    if a.preview:
        return print(f"{', '.join(outs[v] for v in views)}: {PREVIEW_S} s from {a.preview}; check layout and lip sync, then run without --preview")
    print(f"{vod}: {total / 3600:.1f} h. Next: lp.py ingest {vod} --slug {a.slug}" + (" ; lp.py speakers " + a.slug if "guestcam" in files else ""))
