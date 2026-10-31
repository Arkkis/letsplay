"""Visual motion per 0.2 s from one decode of the VOD: the game picture (webcam area masked out) and the webcam itself.
usage: motion.py <slug> [x,y,w,h]   (webcam rect in VOD pixels; omit for no webcam)
→ work/<slug>/motion.npz: game (mean frame difference, 5 Hz), face (same inside the webcam, 5 Hz), cam (the rect used)."""
import os, subprocess, sys
import numpy as np

FPS, W, H, CAM_SIDE = 5, 160, 90, 48


def main(slug, cam):
    w, vod = f"work/{slug}", f"footage/{slug}.mp4"
    meta = __import__("json").load(open(f"{w}/meta.json"))
    graph = f"fps={FPS},format=gray,split=2[a][b];[a]scale={W}:{H}[g]"
    outs = [f"{w}/.motion-game.raw"]
    if cam:
        x, y, cw, ch = cam
        graph += f";[b]crop={cw}:{ch}:{x}:{y},scale={CAM_SIDE}:{CAM_SIDE}[f]"
        outs.append(f"{w}/.motion-face.raw")
    else:
        graph += ";[b]nullsink"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", vod, "-filter_complex", graph, "-map", "[g]", "-f", "rawvideo", outs[0]]
    if cam:
        cmd += ["-map", "[f]", "-f", "rawvideo", outs[1]]
    subprocess.run(cmd, check=True)
    g = np.fromfile(outs[0], np.uint8).reshape(-1, H, W).astype(np.int16)
    mask = np.ones((H, W), bool)
    if cam:
        x, y, cw, ch = cam
        kx, ky = W / meta["width"], H / meta["height"]
        mask[int(y * ky):int((y + ch) * ky) + 1, int(x * kx):int((x + cw) * kx) + 1] = False
    game = np.r_[0, (np.abs(np.diff(g, axis=0)) * mask).sum((1, 2)) / mask.sum()].astype(np.float32)
    face = np.zeros(0, np.float32)
    if cam:
        f = np.fromfile(outs[1], np.uint8).reshape(-1, CAM_SIDE, CAM_SIDE).astype(np.int16)
        face = np.r_[0, np.abs(np.diff(f, axis=0)).mean((1, 2))].astype(np.float32)
    for o in outs:
        os.remove(o)
    np.savez(f"{w}/motion.npz", game=game, face=face, cam=np.array(cam or [], np.int32))
    print(f"{w}/motion.npz: {len(game) / FPS / 60:.0f} min, game motion p50 {np.percentile(game, 50):.1f} p95 {np.percentile(game, 95):.1f}")


if __name__ == "__main__":
    main(sys.argv[1], [int(v) for v in sys.argv[2].split(",")] if len(sys.argv) > 2 and sys.argv[2] else None)
