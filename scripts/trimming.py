"""Silence trimming shared by the edit build and the episode splitter: keep speech and loud game moments, jump-cut the rest."""
import numpy as np

MERGE_GAP = 1.5       # silences shorter than this stay in
PAD_BEFORE, PAD_AFTER = 0.3, 0.45
MIN_CLIP, FILL_GAP = 2.0, 6.0  # clips shorter than MIN_CLIP absorb a neighbouring gap up to FILL_GAP to avoid flash cuts


def loud_db(rms, a, b):
    """Loud-moment threshold: −26 dB, raised to the range's 90th percentile when game audio is loud throughout (music games)."""
    return max(-26.0, float(np.percentile(rms[int(a * 10):int(b * 10)], 90)))


def merge(iv, gap):
    out = []
    for a, b in sorted(iv):
        if out and a - out[-1][1] < gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def absorb_short(kept):
    changed = True
    while changed:
        changed = False
        for i, (x, y) in enumerate(kept):
            if y - x >= MIN_CLIP:
                continue
            gaps = [(kept[i][0] - kept[i - 1][1], i - 1) if i else None, (kept[i + 1][0] - y, i) if i + 1 < len(kept) else None]
            gaps = [g for g in gaps if g and g[0] <= FILL_GAP]
            if gaps:
                j = min(gaps)[1]
                kept[j:j + 2] = [[kept[j][0], kept[j + 1][1]]]
                changed = True
                break
    return [k for k in kept if k[1] - k[0] > 0.6]


def trim(words, rms, a, b, loud):
    iv = [[w["start"] - PAD_BEFORE, w["end"] + PAD_AFTER] for w in words if w["end"] > a and w["start"] < b]
    hits = np.nonzero(rms[int(a * 10):int(b * 10)] > loud)[0]
    iv += [[a + i / 10 - 0.3, a + i / 10 + 0.4] for i in hits]
    return absorb_short([[max(x, a), min(y, b)] for x, y in merge(iv, MERGE_GAP)])
