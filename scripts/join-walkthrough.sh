#!/usr/bin/env bash
# Joins the recorded walkthrough scenes (web/e2e/walkthrough.spec.ts, WALK=1) into one MP4.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/docs/walkthrough"
S="$DIR/scenes"
files=(01-citizen-report 02-team-review 03-citizen-progress 04-agency-fix 05-neighbour-verifies 06-team-resolves 07-citizen-resolved)
inputs=(); filters=""; i=0
for f in "${files[@]}"; do
  inputs+=(-i "$S/$f.webm")
  if [[ "$f" =~ citizen|neighbour ]]; then   # phone scenes: centre on the brand petrol background
    filters+="[$i:v]fps=25,scale=-2:800,pad=1280:800:(ow-iw)/2:0:color=#123F46,setsar=1[v$i];"
  else
    filters+="[$i:v]fps=25,scale=1280:800,setsar=1[v$i];"
  fi
  i=$((i+1))
done
for ((j=0; j<i; j++)); do filters+="[v$j]"; done
filters+="concat=n=$i:v=1:a=0[out]"
ffmpeg -v error -y "${inputs[@]}" -filter_complex "$filters" -map "[out]" \
  -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -movflags +faststart "$DIR/aawen-walkthrough.mp4"
echo "$DIR/aawen-walkthrough.mp4"
