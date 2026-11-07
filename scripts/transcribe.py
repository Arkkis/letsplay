"""Transcript with word timestamps. usage: transcribe.py <audio16k.wav> <out.json> [language]
Beam search, no conditioning on the previous segment (the source of hallucination loops) and config "transcript_prompt"
(a line of the streamer's slang and swearing) as the initial prompt, which steers Whisper to colloquial spelling. Each word keeps Whisper's confidence "p" (0–1) for `proof`'s suspect list."""
import json, sys
from whisper_model import CFG, load

src, out = sys.argv[1], sys.argv[2]
segs, info = load().transcribe(src, vad_filter=True, word_timestamps=True, language=sys.argv[3] if len(sys.argv) > 3 else None,
                               beam_size=5, condition_on_previous_text=False, initial_prompt=CFG.get("transcript_prompt") or None)
data = {"language": info.language, "duration": info.duration,
        "segments": [{"start": s.start, "end": s.end, "text": s.text.strip(),
                      "words": [{"start": w.start, "end": w.end, "word": w.word, "p": round(w.probability, 2)} for w in s.words]} for s in segs]}
json.dump(data, open(out, "w"), ensure_ascii=False)
print(info.language, len(data["segments"]))
