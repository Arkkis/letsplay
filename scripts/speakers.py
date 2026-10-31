"""Who speaks each transcript line on a co-op stream with two webcams: the streamer ("host") or the partner ("guest").

Both voices share one audio track and voice embeddings can't tell them apart, so it reads the webcams: mouth movement
(frame difference at 10 fps) in a box over each person's lower face, each normalised by its own median. The clearly
livelier mouth during a line is the speaker; "?" when neither is.
  speakers.py <slug> <host x,y,w,h> <guest x,y,w,h>   (lower-face boxes in VOD pixels)
  → work/<slug>/speakers.json: {"host": box, "guest": box, "segments": [{"start", "end", "spk": "host"|"guest"|"?"}]}
"""
import json, os, subprocess, sys
import numpy as np

FPS, SIDE, LEAD = 10, 32, 1.15


def motion(slug, boxes):
    """Per-frame mouth movement for each box, from one decode of the VOD."""
    w = f"work/{slug}"
    outs = [f"{w}/.mouth{i}.raw" for i in range(len(boxes))]
    crops = ";".join(f"[s{i}]crop={b[2]}:{b[3]}:{b[0]}:{b[1]},scale={SIDE}:{SIDE}[o{i}]" for i, b in enumerate(boxes))
    graph = f"fps={FPS},format=gray,split={len(boxes)}" + "".join(f"[s{i}]" for i in range(len(boxes))) + ";" + crops
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", f"footage/{slug}.mp4", "-filter_complex", graph]
    for i, o in enumerate(outs):
        cmd += ["-map", f"[o{i}]", "-f", "rawvideo", o]
    subprocess.run(cmd, check=True)
    res = []
    for o in outs:
        f = np.fromfile(o, np.uint8).reshape(-1, SIDE, SIDE).astype(np.int16)
        m = np.r_[0, np.abs(np.diff(f, axis=0)).mean((1, 2))]
        res.append(m / max(np.median(m), 1e-3))
        os.remove(o)
    return res


def main(slug, host, guest):
    boxes = [[int(v) for v in b.split(",")] for b in (host, guest)]
    h, g = motion(slug, boxes)
    out = []
    for s in json.load(open(f"work/{slug}/transcript.json"))["segments"]:
        i, j = int(s["start"] * FPS), max(int(s["end"] * FPS), int(s["start"] * FPS) + 1)
        mh, mg = h[i:j].mean(), g[i:j].mean()
        out.append({"start": s["start"], "end": s["end"], "spk": "host" if mh >= LEAD * mg else "guest" if mg >= LEAD * mh else "?"})
    json.dump({"host": boxes[0], "guest": boxes[1], "segments": out}, open(f"work/{slug}/speakers.json", "w"))
    n = {k: sum(x["spk"] == k for x in out) for k in ("host", "guest", "?")}
    print(f"speakers: host {n['host']}, guest {n['guest']}, unclear {n['?']} lines")


if __name__ == "__main__":
    main(*sys.argv[1:4])
