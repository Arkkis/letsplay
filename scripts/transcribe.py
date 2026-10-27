"""Transcript with word timestamps. usage: transcribe.py <audio16k.wav> <out.json> [language]"""
import json, sys
from whisper_model import load

src, out = sys.argv[1], sys.argv[2]
segs, info = load().transcribe(src, vad_filter=True, word_timestamps=True, language=sys.argv[3] if len(sys.argv) > 3 else None)
data = {"language": info.language, "duration": info.duration,
        "segments": [{"start": s.start, "end": s.end, "text": s.text.strip(),
                      "words": [{"start": w.start, "end": w.end, "word": w.word} for w in s.words]} for s in segs]}
json.dump(data, open(out, "w"), ensure_ascii=False)
print(info.language, len(data["segments"]))
