"""Silence trimming shared by the edit build and the episode splitter: keep speech, loud game moments, visual action and
audio events (laughs, screams, bangs); jump-cut the rest. A pause after a punchline, a question or a laugh is kept as
comedic timing, and shots are at least MIN_CLIP long."""
import re
import numpy as np

MERGE_GAP = 1.5       # silences shorter than this stay in
PAD_BEFORE, PAD_AFTER = 0.3, 0.45
BEAT_PAD = 1.2        # pause kept after an exclamation or question (the beat after a punchline)
EVENT_PAD = 0.6       # kept after a laugh / scream / bang
MIN_CLIP, FILL_GAP = 4.0, 6.0  # clips shorter than MIN_CLIP absorb a neighbouring gap up to FILL_GAP to avoid flash cuts
MOTION_FPS, MOTION_PCT = 5, 98  # visual action: game motion above this percentile of the range
GHOST_LONG, GHOST_DB = 1.2, 12  # a word over GHOST_LONG s whose second half is GHOST_DB quieter than speech was never said


def real_words(words, rms):
    """Transcript words without Whisper's ghosts: zero-length words and stretched words over silence (a quiet segment
    end becomes "Ei saakelis." at 34:40.0–34:42.6 with "Ei" 0 s long), which would otherwise be captioned."""
    peak = lambda a, b: rms[int(a * 10):int(b * 10) + 1].max(initial=-120)
    level = float(np.median([peak(w["start"], w["end"]) for w in words])) if words else 0
    return [w for w in words if w["end"] - w["start"] >= 0.05
            and not (w["end"] - w["start"] > GHOST_LONG and peak((w["start"] + w["end"]) / 2, w["end"]) < level - GHOST_DB)]


def fix_words(words, fixes):
    """Transcript words with the EDL's "wordFixes" applied ({"heard": "said"}, matched on the bare lower-case word, trailing
    punctuation kept): proof-read spellings for the Short cues and the subtitle file without editing the transcript."""
    if not fixes:
        return words
    table = {k.lower(): v for k, v in fixes.items()}
    out = []
    for w in words:
        m = re.match(r"^(\s*)(.*?)([.,!?…]*)$", w["word"])
        fixed = table.get(m.group(2).lower())
        out.append({**w, "word": f"{m.group(1)}{fixed}{m.group(3)}"} if fixed else w)
    return out


def loud_db(rms, a, b):
    """Loud-moment threshold: −26 dB, raised to the range's 90th percentile when game audio is loud throughout (music games)."""
    return max(-26.0, float(np.percentile(rms[int(a * 10):int(b * 10)], 90)))


def motion_thr(motion, a, b):
    """Action threshold: the range's 98th percentile of game motion (None without a motion file)."""
    m = motion[int(a * MOTION_FPS):int(b * MOTION_FPS)] if motion is not None else None
    return float(np.percentile(m, MOTION_PCT)) if m is not None and len(m) else None


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


def trim(words, rms, a, b, loud, motion=None, events=()):
    """Kept [start, end] stretches of VOD range a–b. motion: (array at MOTION_FPS, threshold) or None;
    events: [[start, end, kind, score], ...] from audio_events.py (laughs are not in the transcript: keep them)."""
    iv = [[w["start"] - PAD_BEFORE, w["end"] + (BEAT_PAD if w["word"].strip()[-1:] in "!?" else PAD_AFTER)]
          for w in words if w["end"] > a and w["start"] < b]
    hits = np.nonzero(rms[int(a * 10):int(b * 10)] > loud)[0]
    iv += [[a + i / 10 - 0.3, a + i / 10 + 0.4] for i in hits]
    if motion is not None and motion[1] is not None:
        m, thr = motion
        hits = np.nonzero(m[int(a * MOTION_FPS):int(b * MOTION_FPS)] > thr)[0]
        iv += [[a + i / MOTION_FPS - 0.3, a + i / MOTION_FPS + 0.5] for i in hits]
    iv += [[x - 0.2, y + EVENT_PAD] for x, y, kind, _ in events if y > a and x < b]
    return absorb_short([[max(x, a), min(y, b)] for x, y in merge(iv, MERGE_GAP)])
