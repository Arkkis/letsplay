"""Build names.json, the list of real Chaos Mod effect names, from the ChaosModV source code (GPL-3.0, so the list is
generated on your machine rather than shipped). usage: build_names.py [path to an unpacked ChaosModV source tree]
Without a path it downloads the current master from GitHub."""
import glob, io, json, os, re, sys, tarfile, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LEGACY = {"Random Waypoint": False}  # names of older mod versions (2022) that were renamed since

src = sys.argv[1] if len(sys.argv) > 1 else None
tmp = None
if not src:
    tmp = tempfile.mkdtemp()
    url = "https://codeload.github.com/gta-chaos-mod/ChaosModV/tar.gz/refs/heads/master"
    tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(url).read()), mode="r:gz").extractall(tmp, filter="data")
    src = tmp
names = {}
for f in glob.glob(os.path.join(src, "**", "Effects", "**", "*.cpp"), recursive=True):
    for name in re.findall(r'\.Name\s*=\s*"([^"]+)"', open(f, errors="ignore").read()):
        names[name] = {"meta": f"{os.sep}Meta{os.sep}" in f}  # meta effects are shown with a "(Meta)" suffix
names.update({k: {"meta": v} for k, v in LEGACY.items() if k not in names})
if not names:
    sys.exit(f"no effect names found under {src}")
json.dump(dict(sorted(names.items())), open(os.path.join(HERE, "names.json"), "w"), indent=0)
print(f"{len(names)} effect names → {os.path.join(HERE, 'names.json')}")
