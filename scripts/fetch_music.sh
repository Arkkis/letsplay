#!/bin/sh
# Download the style music (Kevin MacLeod, incompetech.com, CC BY 4.0; credited automatically in every description).
set -e
cd "$(dirname "$0")/../public/music"
get() { [ -s "$1" ] || curl -sfL -o "$1" "https://incompetech.com/music/royalty-free/mp3-royaltyfree/$2.mp3" && echo "$1"; }
get funk.mp3 "Funk%20Game%20Loop"
get elevator.mp3 "Local%20Forecast%20-%20Elevator"
get darkest-child.mp3 "Darkest%20Child"
get ossuary.mp3 "Ossuary%206%20-%20Air"
get carefree.mp3 "Carefree"
get lobby-time.mp3 "Lobby%20Time"
