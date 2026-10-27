#!/bin/sh
# Prepare an edit source at native resolution (never upscale): lift shadows, light sharpening.
# usage: prep_source.sh <in> <start_s> <dur_s> <out> [extra ffmpeg output args]
in=$1 ss=$2 t=$3 out=$4; shift 4
exec ffmpeg -nostdin -loglevel error -y -ss "$ss" -t "$t" -i "$in" \
  -vf "curves=master='0/0 0.12/0.17 0.35/0.42 0.7/0.74 1/1',eq=saturation=1.08,cas=0.3" "$@" "$out"
