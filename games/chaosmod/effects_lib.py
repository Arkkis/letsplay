"""GTA V Chaos Mod effects: real effect names (names.json, built by build_names.py) and one-line descriptions in the
channel's language (descriptions.<lang>.json, which grows as episodes are written). Maps noisy OCR text to real names."""
import json, os, re
from difflib import SequenceMatcher
from scripts.config import CFG

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES_PATH = os.path.join(HERE, "names.json")
DESC_PATH = os.path.join(HERE, f"descriptions.{CFG['language']}.json")
if not os.path.exists(NAMES_PATH):
    raise SystemExit(f"{NAMES_PATH} missing: run `games/chaosmod/build_names.py` once with the venv's Python")
NAMES = json.load(open(NAMES_PATH))
DESC = json.load(open(DESC_PATH)) if os.path.exists(DESC_PATH) else {}


def key(s):
    """OCR-tolerant comparison key: letters and digits only, l/I confusion folded, meta suffix dropped."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(?meta\)?\s*$", "", s.lower(), flags=re.I)).replace("l", "i")


KEYS = {key(n): n for n in NAMES}


def clipped(k, kb):
    """OCR cut letters off the start of the name ('skePreviousEffects' for 'Re-Invoke Previous Effects')."""
    m = SequenceMatcher(None, k, kb).find_longest_match(0, len(k), 0, len(kb))
    return m.size >= max(10, 0.75 * len(k)) and m.b + m.size == len(kb)


def canonical(ocr):
    """Real effect name (with ' (Meta)' for meta effects) for an OCR string, or None if it isn't an effect."""
    k = key(ocr)
    if len(k) < 4:
        return None
    best = KEYS.get(k) or max(KEYS.items(), key=lambda kv: SequenceMatcher(None, k, kv[0]).ratio())[1]
    kb = key(best)
    if not (k == kb or (len(k) >= max(8, 0.6 * len(kb)) and k in kb) or SequenceMatcher(None, k, kb).ratio() > 0.85
            or clipped(k, kb)):
        return None
    return best + (" (Meta)" if NAMES[best]["meta"] else "")


def base(name):
    return re.sub(r"\s*\(Meta\)$", "", name)


def desc(name):
    """The one-line description of an effect in the channel's language, or ''."""
    return DESC.get(base(name), "")


def learn(effects):
    """Remember descriptions written in an EDL ([time, name, description], ...) for effects that have none yet."""
    new = {base(n): d for _, n, d in effects if d and d != "TODO" and not DESC.get(base(n))}
    if new:
        DESC.update(new)
        json.dump(dict(sorted(DESC.items())), open(DESC_PATH, "w"), ensure_ascii=False, indent=0)
