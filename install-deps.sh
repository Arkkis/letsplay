#!/bin/sh
# Install the let's play pipeline's dependencies on Linux or macOS (Windows: install-deps.ps1). Safe to re-run.
# usage: sh install-deps.sh
set -e
cd "$(dirname "$0")"
have() { command -v "$1" >/dev/null 2>&1; }
step() { printf '\n==> %s\n' "$*"; }

case "$(uname -s)" in
  Darwin)
    have brew || { echo "Homebrew is required: https://brew.sh" >&2; exit 1; }
    step "System tools (Homebrew)"
    brew install ffmpeg node python@3.12
    PY="$(brew --prefix python@3.12)/bin/python3.12"
    ;;
  Linux)
    if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
    if have apt-get; then PM="$SUDO apt-get install -y"; PY_PKG=python3.12
    elif have dnf; then PM="$SUDO dnf install -y"; PY_PKG=python3.12
    elif have pacman; then PM="$SUDO pacman -S --needed --noconfirm"; PY_PKG=python312
    elif have zypper; then PM="$SUDO zypper install -y"; PY_PKG=python312
    else echo "No supported package manager (apt, dnf, pacman, zypper): install ffmpeg, Node 20+, Python 3.12 by hand." >&2; exit 1; fi
    step "System tools ($PM)"
    MISSING=""
    have ffmpeg || MISSING="$MISSING ffmpeg"
    have npm || MISSING="$MISSING nodejs npm"
    have python3.12 || MISSING="$MISSING $PY_PKG"
    [ -z "$MISSING" ] || $PM $MISSING
    PY=python3.12
    ;;
  *)
    echo "Unsupported system: use install-deps.ps1 on Windows." >&2; exit 1
    ;;
esac

"$PY" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' || { echo "Python 3.12 is required ($PY)." >&2; exit 1; }
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' || { echo "Node 20+ is required." >&2; exit 1; }

step "Python packages (.venv)"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

step "Node packages"
npm install

step "Config and style music"
if [ ! -f config.json ]; then
  cp config.example.json config.json
  echo "Created config.json: set your channel name, VOD folder and language."
fi
sh scripts/fetch_music.sh

step "Done. Next: edit config.json, then npm test (see README.md for YouTube sign-in, optional)."
