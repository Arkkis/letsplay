"""A webcam's background made transparent: an alpha matte video of the person, frame for frame with the source
(Robust Video Matting, MobileNetV3 fp16 on the GPU: temporally stable edges, hair included). Mattes at the source's
height up to 720p (internal pass at 1/4), with a contrast curve that clears the faint halo a black-keyed source leaves;
`assemble --cutout` scales it to the webcam box and merges it as the alpha channel.
  matte.py <src> <out.mp4> <ss> <t>   (t = 0: to the end) → gray H.264, full range, the source's frame rate
Runs in its own uv environment with onnxruntime-gpu (assemble starts it), so the pipeline's CPU onnxruntime stays as is."""
import json, os, queue, subprocess, sys, threading, urllib.request
import numpy as np
import onnxruntime as ort

MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "rvm_mobilenetv3_fp16.onnx")
URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp16.onnx"
MAX_H, RATIO = 720, 0.25
LUT = (np.arange(256) / 255).astype(np.float16)


def main(src, out, ss, t):
    if not os.path.exists(MODEL):
        urllib.request.urlretrieve(URL, MODEL + ".part")
        os.rename(MODEL + ".part", MODEL)
    v = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                            "stream=width,height,r_frame_rate", "-of", "json", src]))["streams"][0]
    H = min(MAX_H, v["height"]) // 2 * 2
    w = round(v["width"] * H / v["height"] / 2) * 2
    dur = ["-t", t] if float(t) else []
    dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-ss", ss, *dur, "-i", src, "-an", "-fps_mode", "passthrough",
                            "-vf", f"scale={w}:{H},format=gbrp", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{H}",
                            "-r", v["r_frame_rate"], "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "gray",
                            "-color_range", "pc", out + ".part.mp4"], stdin=subprocess.PIPE)
    frames = queue.Queue(8)

    def feed():  # decoding and the fp16 conversion run beside the GPU
        size = w * H * 3
        while len(buf := dec.stdout.read(size)) == size:
            frames.put(LUT[np.frombuffer(buf, np.uint8).reshape(3, H, w)[[2, 0, 1]]][None])  # gbrp planes → rgb
        frames.put(None)
    threading.Thread(target=feed, daemon=True).start()
    ort.preload_dlls()
    sess = ort.InferenceSession(MODEL, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    rec, ratio, n = [np.zeros((1, 1, 1, 1), np.float16)] * 4, np.array([RATIO], np.float32), 0
    while (x := frames.get()) is not None:
        _, pha, *rec = sess.run(None, {"src": x, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3], "downsample_ratio": ratio})
        a = np.clip((pha[0, 0].astype(np.float32) - 0.55) * 3 + 0.5, 0, 1)
        enc.stdin.write((a * 255 + 0.5).astype(np.uint8).tobytes())
        n += 1
        if n % 54000 == 0:
            print(f"{os.path.basename(src)}: {n} frames matted", flush=True)
    enc.stdin.close()
    if dec.wait() or enc.wait():
        sys.exit(f"matting {src} failed")
    os.rename(out + ".part.mp4", out)


if __name__ == "__main__":
    main(*sys.argv[1:5])
