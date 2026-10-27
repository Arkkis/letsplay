"""Spoken-language probabilities per 10 s window (Whisper language ID), top five per window. Long stretches in another
language than the commentary are story cutscenes or mission dialogue. usage: langid.py <audio16k.wav> <out.json>"""
import json, sys, wave
import numpy as np
from whisper_model import load

WIN = 10
model = load()
w = wave.open(sys.argv[1])
sr, out = w.getframerate(), []
while len(buf := w.readframes(WIN * sr)) == WIN * sr * 2:
    probs = sorted(model.detect_language(np.frombuffer(buf, np.int16).astype(np.float32) / 32768)[2], key=lambda x: -x[1])[:5]
    out.append([len(out) * WIN, {lang: round(p, 3) for lang, p in probs}])
json.dump(out, open(sys.argv[2], "w"))
print(len(out), "windows")
