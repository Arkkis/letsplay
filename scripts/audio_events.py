"""Audio events the transcript can't show: laughter, screams and bangs (explosions, crashes), from YAMNet (AudioSet
classes) over the whole VOD. usage: audio_events.py <audio16k.wav> <out.json>
→ [[start, end, kind, score], ...] with kind laugh | scream | bang, merged runs, VOD seconds.
The model (Apache 2.0, ONNX export of Google's YAMNet) is fetched once into models/."""
import csv, json, os, sys, urllib.request, wave
import numpy as np
import onnxruntime as ort

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = f"{ROOT}/models/yamnet.onnx"
URL = "https://huggingface.co/zeropointnine/yamnet-onnx/resolve/main/"
HOP, CHUNK = 0.48, 600  # YAMNet scores one 0.96 s window every 0.48 s; audio is fed in 10 min chunks
KINDS = {"laugh": (["Laughter", "Giggle", "Chuckle, chortle", "Belly laugh", "Snicker"], 0.15),
         "scream": (["Screaming", "Shout", "Yell"], 0.2),
         "bang": (["Explosion", "Smash, crash", "Shatter", "Crushing", "Breaking"], 0.3)}


def model():
    if not os.path.exists(MODEL):
        os.makedirs(os.path.dirname(MODEL), exist_ok=True)
        for f in ("yamnet.onnx", "yamnet_class_map.csv"):
            urllib.request.urlretrieve(URL + f, f"{ROOT}/models/{f}")
    names = [r[2] for r in csv.reader(open(f"{ROOT}/models/yamnet_class_map.csv"))][1:]
    return ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"]), names


def main(wav, out):
    sess, names = model()
    idx = {k: [names.index(n) for n in ns] for k, (ns, _) in KINDS.items()}
    w = wave.open(wav)
    sr, n = w.getframerate(), w.getnframes()
    scores = {k: [] for k in KINDS}
    for start in range(0, n, CHUNK * sr):
        w.setpos(start)
        buf = np.frombuffer(w.readframes(CHUNK * sr), np.int16).astype(np.float32) / 32768
        if len(buf) < sr:
            break
        s = sess.run(None, {"waveform": buf})[0]
        for k in KINDS:
            scores[k] += list(s[:, idx[k]].sum(1))
    events = []
    for k, (_, thr) in KINDS.items():
        run = None
        for i, v in enumerate(scores[k] + [0.0]):
            t = i * HOP
            if v >= thr:
                run = [run[0], t + 0.96, max(run[2], v)] if run else [t, t + 0.96, v]
            elif run:
                events.append([round(run[0], 2), round(run[1], 2), k, round(float(run[2]), 2)])
                run = None
    events.sort()
    json.dump(events, open(out, "w"))
    print(out, {k: sum(e[2] == k for e in events) for k in KINDS})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
