"""Shared ffmpeg settings: the grade every source gets and the machine's video encoder."""
import subprocess

# Native resolution, never upscaled: lift shadows, light sharpening.
GRADE = "curves=master='0/0 0.12/0.17 0.35/0.42 0.7/0.74 1/1',eq=saturation=1.08,cas=0.3"


def video_encoder():
    """NVENC when this machine has a working NVIDIA encoder, else x264 at the same quality target."""
    ok = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1", "-c:v", "h264_nvenc",
                         "-f", "null", "-"], capture_output=True).returncode == 0
    return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "17", "-b:v", "0"] if ok else ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]


def partner_span(slug):
    """VOD seconds (start, end) where the co-op partner's own tracks (mic, cam, game) exist, from `assemble`; None when
    the VOD has no separate partner tracks. Outside it the partner may still be in the call, unheard and unseen."""
    import json, os
    path = f"work/{slug}/assemble.json"
    if not os.path.exists(path):
        return None
    m = json.load(open(path))
    spans = []
    for r in ("guestcam", "guestgame"):
        if r in m["sources"] and os.path.exists(m["sources"][r]):
            d, k = m["sync"][r]
            dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", m["sources"][r]]))
            spans.append((max(0.0, d), d + dur * k))
    return (min(a for a, _ in spans), max(b for _, b in spans)) if spans else None
