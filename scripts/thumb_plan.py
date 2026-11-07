"""Thumbnail plan for an episode's props (work/<vod>/epN.props.json), run after build_edit.py:
- the webcam frame `thumb.face` cut out with background removal → public/<vod>-ep<N>-face-<frame>.png (edit.faceCut,
  also used by the title card); refused if the person comes out see-through;
- the hook split into lines of at most 9 letters and sized to fit;
- readability measured on the graded, zoomed background under the text: how much to darken behind it (to reach 3:1,
  WCAG large text, capped at 75%), white instead of the headline colour when that can't reach 3:1 or the background is
  yellow/orange, and a dark plate behind the series tag when it is under 4.5:1.
"""
import colorsys, json, os, subprocess, sys
import numpy as np
from PIL import Image, ImageEnhance

CYAN = (0x00, 0xC8, 0xF8)
W, H = 1280, 720
lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
lum = lambda rgb: float(np.dot(lin(np.array(rgb) / 255), [.2126, .7152, .0722]))
ratio = lambda a, b: (max(a, b) + .05) / (min(a, b) + .05)
hexrgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def frame(source, f, fps):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{f / fps:.3f}", "-i", source, "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    from io import BytesIO
    return Image.open(BytesIO(raw)).convert("RGB")


def cutout(img, cam, width, path):
    from rembg import remove, new_session
    k = width / 1920  # props cam is in 1920-wide layout units; the prepared source is at the VOD's native size
    x, y, w, h = (round(v * k) for v in cam)
    cut = remove(img.crop((x, y, x + w, y + h)), session=new_session("birefnet-portrait"))
    a = np.asarray(cut)[..., 3].astype(float)
    a = np.clip((a - 40) * 255 / 150, 0, 255)  # harden the soft mask edge into an opaque subject
    subj = a > 20
    if not subj.any():
        sys.exit(f"thumb.face: no person found in the webcam at that frame; pick another face time")
    seethrough = float(((a < 235) & subj).sum() / subj.sum())
    if seethrough > .08:
        sys.exit(f"thumb.face: the cut-out is {seethrough:.0%} see-through (busy or dark background); pick another face time")
    cut.putalpha(Image.fromarray(a.astype(np.uint8)))
    cut.crop(cut.getbbox()).save(path, optimize=True)


def split(hook, width=9):
    lines = []
    for w in hook.split():
        if lines and len(lines[-1]) + 1 + len(w) <= width:
            lines[-1] += " " + w
        else:
            lines.append(w)
    return lines


def readability(bg, lines, size, head):
    """Darkening and colours for the text block at the top left (the layout of src/Thumbnail.tsx)."""
    longest = max(len(l) for l in lines)
    w = min(.6, longest * .47 * size / 100 + .05)
    h = .09 + .05 + len(lines) * size * 16 / 9 / 100
    a = np.asarray(bg.crop((int(.03 * W), int(.06 * H), int(w * W), int(min(h, .7) * H))), dtype=float) / 255
    p75 = float(np.percentile(np.dot(lin(a), [.2126, .7152, .0722]), 75))
    hh, s, v = np.vectorize(colorsys.rgb_to_hsv)(a[..., 0], a[..., 1], a[..., 2])
    warm = float(((hh > 25 / 360) & (hh < 65 / 360) & (s > .45) & (v > .55)).mean())  # yellow/orange share

    def fit(rgb):
        target = (lum(rgb) + .05) / 3 - .05
        dark = 0 if p75 <= target else min(.75, 1 - target / p75)
        return dark, ratio(lum(rgb), p75 * (1 - dark))
    dark, r = fit(hexrgb(head))
    color = "headline"
    if warm > .15 or (r < 3 and fit((255, 255, 255))[1] >= 3):
        color, (dark, r) = "white", fit((255, 255, 255))
    return {"scrim": round(dark, 2), "color": color, "plate": ratio(lum(CYAN), p75 * (1 - dark)) < 4.5, "contrast": round(r, 1)}


def main(props_path, edl_path):
    props, edl = json.load(open(props_path)), json.load(open(edl_path))
    e, th = props["edit"], props["thumb"]
    source, fps = os.path.join("public", e["source"]), e["fps"]
    head = json.load(open("src/styles.json"))[e["style"]]["headline"]
    if e.get("cam") and th.get("face") is not None:
        name = f"{edl['vod']}-ep{edl['episode']}-face-{th['face']}.png"
        if not os.path.exists(f"public/{name}"):
            own = next((t for t in e.get("tracks") or [] if t["role"] == "cam"), None)  # separate recordings: the webcam's own file
            img = frame(os.path.join("public", own["source"]) if own else source, th["face"], fps)
            cutout(img, [0, 0, 1920, round(1920 * img.height / img.width)] if own else e["cam"], img.width, f"public/{name}")
        e["faceCut"] = name
    bg = frame(source, th["bg"], fps)
    z = th.get("bgZoom", 1)
    ox, oy = (float(v.rstrip("%")) / 100 for v in th.get("bgOrigin", "50% 50%").split())
    if e.get("cam") and not e.get("tracks"):  # zoom just enough that the stream's own webcam leaves the frame (the cut-out replaces it)
        cx, cy = e["cam"][0] / 1920, e["cam"][1] / 1080
        need = min((1 - ox) / (cx - ox) if cx > ox else 9, (1 - oy) / (cy - oy) if cy > oy else 9)
        if need > 1.6:
            print(f"warning: thumbnail background keeps the stream webcam at bgOrigin {th.get('bgOrigin')}; move it up or left")
        z = th["bgZoom"] = round(max(z, min(need, 1.6)), 3)
    x0, y0 = ox * bg.width * (1 - 1 / z), oy * bg.height * (1 - 1 / z)  # what CSS scale(z) around the origin leaves visible
    bg = bg.crop((round(x0), round(y0), round(x0 + bg.width / z), round(y0 + bg.height / z))).resize((W, H), Image.LANCZOS)
    bg = ImageEnhance.Color(ImageEnhance.Contrast(bg).enhance(1.15)).enhance(1.25)
    lines = split(th["text"])
    longest = max(len(l) for l in lines)
    size = min(13.0, (46 if e.get("faceCut") else 80) / (longest * .47), 52 / (len(lines) * 1.69))  # % of thumbnail width
    th.update(lines=lines, size=round(size, 2), **readability(bg, lines, size, head))
    json.dump(props, open(props_path, "w"), ensure_ascii=False)
    print(f"thumbnail: {' / '.join(lines)}, {th['color']}, darkening {th['scrim']:.0%}, contrast {th['contrast']}:1"
          + (", tag on a plate" if th["plate"] else ""))


if __name__ == "__main__":
    main(*sys.argv[1:3])
