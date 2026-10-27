#!/bin/bash
# Photoreal (Cycles) stills of the exterior color study, one Blender at a time: the seven stills build_colorstudy.py reads.
#   name             spec          still                                    station      brick
#   recommended      recommended   cycles/recommended/yard.jpg              yard         painted
#   recommended_up   recommended   cycles/recommended_up/upper_deck.jpg     upper_deck   painted
#   charcoal         charcoal      cycles/charcoal/yard.jpg                 yard         painted
#   charcoal_up      charcoal      cycles/charcoal_up/upper_deck.jpg        upper_deck   painted
#   gray, black      same name     cycles/<name>/yard.jpg                   yard         painted
#   existing         existing      cycles/existing/yard.jpg                 yard         the house's own buff brick
# Each runs as  nice -n 19 flock $S/blender.lock <bpy python> cycles_palette.py ...  and appends its output to cycles/run.log.
# Quality and look as published: 40 samples, 1100x708, summer foliage, June 21 10:30 AM, the stations of cameras.json (a copy of the
# fillmore/render stations the published stills used). The specs carry geometry.furniture; decktakeoff.cycles draws it by default.
#     bash cycles_all.sh [name ...]      default: all seven, the cover and deck-color stills first
#     DRY_RUN=1   print the commands, run nothing
#     FORCE=1     also re-render a still that is newer than its spec
# A still newer than its spec and the cameras copy is kept, so a stopped run picks up where it stopped (make_specs.py leaves an
# unchanged spec alone). The old still is deleted just before its render, so a failed one cannot stay on the page as if it were new.
# A spec without furniture is refused (ALLOW_NO_FURNITURE=1 to render it anyway). Exit 1 if any named still is missing at the end.
S=/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad; CS=$S/fillmore/colorstudy
LOCK=$S/blender.lock; PY=$S/bvenv/bin/python; LOG=$CS/cycles/run.log; CAMS=$CS/cameras.json
ALL="recommended recommended_up charcoal charcoal_up gray black existing"
cd /home/user/Decks- || exit 1
mkdir -p "$CS/cycles"
failed=""
for j in ${*:-$ALL}; do
  case $j in
    *_up)     p=${j%_up}; st=upper_deck; pb=1 ;;
    existing) p=$j;       st=yard;       pb=0 ;;
    gray|charcoal|black|recommended) p=$j; st=yard; pb=1 ;;
    *) echo "$j: not one of: $ALL"; failed="$failed $j"; continue ;;
  esac
  spec=$CS/specs/$p.json; out=$CS/cycles/$j; jpg=$out/$st.jpg
  if [ ! -f "$spec" ]; then echo "$j: no spec $spec (python3 $CS/tools/make_specs.py)"; failed="$failed $j"; continue; fi
  if [ -z "$ALLOW_NO_FURNITURE" ] && ! grep -q '"furniture": \[{' "$spec"; then
    echo "$j: $spec has no geometry.furniture (python3 $CS/tools/make_specs.py, or ALLOW_NO_FURNITURE=1)"; failed="$failed $j"; continue
  fi
  if [ -z "$FORCE" ] && [ -s "$jpg" ] && [ "$jpg" -nt "$spec" ] && [ "$jpg" -nt "$CAMS" ]; then
    echo "$(date -u +%H:%M:%S) $j: newer than its spec, kept ($jpg)"; continue
  fi
  cmd=(nice -n 19 flock "$LOCK" env PAINTED_BRICK=$pb "$PY" "$CS/tools/cycles_palette.py" "$spec" "$out" $st
       --samples=40 --size=1100x708 --cameras="$CAMS" --when=2026-06-21T10:30 --foliage=summer)
  if [ -n "$DRY_RUN" ]; then
    echo "[dry run] rm -f $jpg"; echo "[dry run] ${cmd[*]} >> $LOG 2>&1"; continue
  fi
  rm -f "$jpg"
  n0=$(stat -c %s "$LOG" 2>/dev/null || echo 0); t0=$SECONDS
  { echo "=== $(date -u +%FT%TZ) $j (queued)"; echo "+ ${cmd[*]}"; } >> "$LOG"
  "${cmd[@]}" >> "$LOG" 2>&1; rc=$?
  if [ $rc -eq 0 ] && [ -s "$jpg" ]; then
    rt=$(tail -c +$((n0 + 1)) "$LOG" | sed -n 's/^rendered .* in \([0-9]*s\) -> .*/\1/p' | tail -1)
    echo "$(date -u +%H:%M:%S) $j: rendered, Blender render ${rt:-?}, $((SECONDS - t0))s from queued to done" | tee -a "$LOG"
  else
    echo "$(date -u +%H:%M:%S) $j: FAILED (exit $rc, no $jpg), see $LOG" | tee -a "$LOG"; failed="$failed $j"
  fi
done
[ -z "$failed" ] || { echo "not rendered:$failed"; exit 1; }
