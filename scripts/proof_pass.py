"""Second Whisper pass over short windows of a 16 kHz mono wav, for proof-reading captions and Shorts.
usage: proof_pass.py <audio16k.wav> <windows.json: [[start, end], ...] seconds> <out.json> [language]
Each window is decoded on its own (no context from the rest of the stream), with the config's transcript prompt."""
import json, sys, wave
import numpy as np
from whisper_model import CFG, load

src, win, out = sys.argv[1:4]
lang = sys.argv[4] if len(sys.argv) > 4 else None
wf = wave.open(src)
rate = wf.getframerate()
audio = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
model = load()
texts = []
for a, b in json.load(open(win)):
    segs, _ = model.transcribe(audio[int(a * rate):int(b * rate)], language=lang, beam_size=5, condition_on_previous_text=False,
                               initial_prompt=CFG.get("transcript_prompt") or None)
    texts.append(" ".join(s.text.strip() for s in segs))
json.dump(texts, open(out, "w"), ensure_ascii=False)
print(len(texts))
