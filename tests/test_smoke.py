"""Smoke tests that need no media: every CLI command parses, and the example EDL builds into a sane timeline."""
import json, os, shutil, subprocess, sys, tempfile, unittest
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = {**os.environ, "LETSPLAY_CONFIG": os.path.join(ROOT, "config.example.json")}
COMMANDS = "ingest split context draft faces frames prep check script shorts render publish stats".split()


class Smoke(unittest.TestCase):
    def test_cli_parses(self):
        for c in COMMANDS:
            r = subprocess.run([sys.executable, "scripts/lp.py", c, "-h"], cwd=ROOT, env=ENV, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"lp.py {c} -h: {r.stderr}")
        self.assertIn("--patch", subprocess.run([sys.executable, "scripts/lp.py", "render", "-h"], cwd=ROOT, env=ENV,
                                                capture_output=True, text=True).stdout)

    def test_example_edl_builds(self):
        edl = json.load(open(os.path.join(ROOT, "examples", "edit-example.json")))
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, "work", edl["vod"])
            os.makedirs(w)
            os.makedirs(os.path.join(d, "src"))
            os.makedirs(os.path.join(d, "edits"))
            shutil.copy(os.path.join(ROOT, "src", "styles.json"), os.path.join(d, "src"))
            # 2 minutes of speech: one word per second ("word0", "word1", …), segments of five words
            words = [{"start": t + 0.1, "end": t + 0.6, "word": f" word{t}"} for t in range(120)]
            segs = [{"start": words[i]["start"], "end": words[i + 4]["end"], "text": " ".join(x["word"].strip() for x in words[i:i + 5]),
                     "words": words[i:i + 5]} for i in range(0, 120, 5)]
            json.dump({"segments": segs}, open(os.path.join(w, "transcript.json"), "w"))
            np.save(os.path.join(w, "rms100ms.npy"), np.full(1200, -40.0))
            json.dump([{"part": 1, "start": 0, "end": 120, "prepStart": 0, "prepEnd": 120}], open(os.path.join(w, "parts.json"), "w"))
            json.dump({"width": 1280, "height": 720, "duration": 120, "game": None}, open(os.path.join(w, "meta.json"), "w"))
            path = os.path.join(d, "edits", "example.json")
            json.dump(edl, open(path, "w"))
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_edit.py"), path], cwd=d, env=ENV,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            e = json.load(open(os.path.join(w, "ep1.props.json")))["edit"]
            self.assertEqual(e["fps"], 60)
            self.assertGreater(e["duration"], 60 * 60)  # content + title + freeze + end screen, over a minute
            self.assertEqual([c["text"] for c in e["captions"]], ["WORD FORTY", "NINETY!"])
            self.assertTrue(all(c["dur"] > 0 for c in e["clips"]))
            desc = open(os.path.join(d, "out", edl["playlist"], f"{edl['output']}.description.txt")).read()
            self.assertIn("0:00 Intro", desc)
            self.assertTrue(os.path.getsize(os.path.join(d, "out", edl["playlist"], f"{edl['output']}.en.srt")) > 0)


if __name__ == "__main__":
    unittest.main()
