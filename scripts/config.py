"""Channel settings (config.json, from config.example.json): names, language, on-screen and description text."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_path = os.environ.get("LETSPLAY_CONFIG") or os.path.join(ROOT, "config.json")
if not os.path.exists(_path):
    raise SystemExit(f"{_path} missing: copy config.example.json to config.json and fill it in")
CFG = json.load(open(_path))


def out_dir(edl):
    """Rendered files of one series: out/<playlist>/, Shorts in its shorts/ (relative to the repository root)."""
    name = edl.get("playlist") if edl.get("playlist") not in (None, "", "TODO") else edl["output"]
    return os.path.join("out", name.replace("/", "-"))


def text(key, **kw):
    """On-screen / description text in the channel's language."""
    return CFG["text"][key].format(**kw)


def translation_text(key, **kw):
    """The same text in the translation language (YouTube localization), or None."""
    tr = CFG.get("translation_text") or {}
    return tr[key].format(**kw) if key in tr else None
