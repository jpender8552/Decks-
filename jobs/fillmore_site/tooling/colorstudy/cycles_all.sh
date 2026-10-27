#!/bin/bash
# Photoreal (Cycles) yard-station hero per palette, one Blender at a time (flock), quick quality: 40 samples, 1100x708.
S=/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad; CS=$S/fillmore/colorstudy
cd /home/user/Decks-
for p in ${*:-gray black recommended existing}; do
  pb=1; [ $p = existing ] && pb=0
  rm -rf $CS/cycles/$p/yard.jpg
  PAINTED_BRICK=$pb flock $S/blender.lock $S/bvenv/bin/python $CS/tools/cycles_palette.py $CS/specs/$p.json $CS/cycles/$p yard \
     --samples=40 --size=1100x708 --cameras=$S/fillmore/render/cameras.json --when=2026-06-21T10:30 --foliage=summer > $CS/cycles/$p.log 2>&1
  echo "$(date -u +%H:%M:%S) $p: $(grep -h '^rendered' $CS/cycles/$p.log | cut -c1-90)"
done
