"""OCR the chaos-mod active-effect list (right side) at 2 fps; log when each effect name first appears.

Fast path: the list only changes when an effect starts or ends, so OCR runs only on frames whose white-text mask
in the name column differs from the last OCR'd frame. The VOD is scanned in parallel chunks.
usage: ocr_effects.py <vod> <start_s> <dur_s> <out.json>
"""
import json, os, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

W, H, X, Y = 240, 340, 940, 130  # name column of the frame scaled to 1280x720 for analysis, above the webcam (timer bars to its right change constantly)
FPS, CHANGED_PX, CHUNK_S = 2, 120, 300


def scan(start, dur):
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)  # one thread per worker; workers run in parallel
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-threads", "2", "-ss", str(start), "-t", str(dur), "-i", sys.argv[1],
           "-vf", f"fps={FPS},scale=1280:720,crop={W}:{H}:{X}:{Y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    seen, events, names, last, i, runs = {}, [], set(), None, 0, 0
    while (buf := p.stdout.read(W * H * 3)):
        t = start + i / FPS
        img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        mask = img.min(axis=2) > 190  # white effect names
        if last is None or np.count_nonzero(mask ^ last) > CHANGED_PX:
            names = {r[1].strip() for r in (ocr(img, use_cls=False)[0] or []) if r[2] > 0.8 and len(r[1].strip()) > 3}
            last, runs = mask, runs + 1
        for n in names:
            if t - seen.get(n, -999) > 20:  # new activation unless seen in the last 20 s
                events.append([round(t, 1), n])
            seen[n] = t
        i += 1
    return events, runs, i


if __name__ == "__main__":
    start, dur, out = float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    chunks = [(s, min(CHUNK_S, start + dur - s)) for s in np.arange(start, start + dur, CHUNK_S)]
    with ProcessPoolExecutor(min(len(chunks), os.cpu_count() - 2)) as ex:
        res = list(ex.map(scan, *zip(*chunks)))
    events = [e for ev, _, _ in res for e in ev]
    # an effect active across a chunk boundary is logged again at the next chunk's start; drop those repeats
    events = [e for k, e in enumerate(events) if not any(f[1] == e[1] and 0 < e[0] - f[0] <= 20 + CHUNK_S for f in events[:k]
                                                          if any(e[0] == c for c, _ in chunks))]
    json.dump(events, open(out, "w"), indent=0)
    print(len(events), "activations;", sum(r for _, r, _ in res), "of", sum(n for _, _, n in res), "frames OCR'd")
