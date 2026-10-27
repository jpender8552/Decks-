#!/bin/bash
# Photoreal (Cycles) stills of the exterior color study, one Blender at a time: every still build_colorstudy.py reads.
# Owner 27 Oct ("super shady and dark and low view ... more views and with more sun"): June 21 at 8:00 AM, when the morning
# sun is on the back walls (they face north-northeast: at 10:30 the sun only grazes them), and three raised stations that see
# the walls over the deck rail (cameras.json: cs_front, cs_left, cs_right).
#   name               spec             stills (cycles/<name>/)                   page use
#   cream, beige, khaki, recommended    cs_front, cs_left, cs_right               each palette's page; cs_front at a glance
#   recommended_dh     recommended_dh   cs_front                                  the deck color page (Dark Hickory)
#   recommended_up     recommended      upper_deck                                the deck color page (English Walnut)
#   recommended_dh_up  recommended_dh   upper_deck                                the deck color page (Dark Hickory)
#   existing           existing         cs_front                                  today's colors, at a glance
# The brick is painted only for a palette with "brick_painted" true in palettes.json (the tan and cream study: none).
# Each runs as  nice -n 19 flock $S/blender.lock <bpy python> cycles_palette.py SPEC OUT views...  logged to cycles/run.log.
# Quality: 40 samples, 1100x708, summer foliage, the stations of cameras.json.
#     bash cycles_all.sh [name ...]      default: all, the cover and deck-color stills first
#     DRY_RUN=1   print the commands, run nothing          FORCE=1   re-render stills newer than their spec
#     WHEN=2026-06-21T08:00  the local date and time of the sun
# Stills newer than their spec and the cameras file are kept, so a stopped run picks up where it stopped. The old stills of a
# name are deleted just before its render. A spec without furniture is refused. Exit 1 if any still is missing at the end.
S=/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad; CS=$S/fillmore/colorstudy
LOCK=$S/blender.lock; PY=$S/bvenv/bin/python; LOG=$CS/cycles/run.log; CAMS=$CS/cameras.json
WHEN=${WHEN:-2026-06-21T08:00}
ALL="recommended recommended_up recommended_dh recommended_dh_up cream beige khaki existing"
cd /home/user/Decks- || exit 1
mkdir -p "$CS/cycles"
failed=""
for j in ${*:-$ALL}; do
  case $j in
    *_up)                        p=${j%_up}; views="upper_deck" ;;
    recommended_dh|existing)     p=$j;       views="cs_front" ;;
    cream|beige|khaki|recommended) p=$j;     views="cs_front cs_left cs_right" ;;
    *) echo "$j: not one of: $ALL"; failed="$failed $j"; continue ;;
  esac
  spec=$CS/specs/$p.json; out=$CS/cycles/$j
  pb=$(python3 -c "import json,sys; print(int(bool(json.load(open(sys.argv[1])).get(sys.argv[2], {}).get('brick_painted', True))))" "$CS/palettes.json" "$p")
  if [ ! -f "$spec" ]; then echo "$j: no spec $spec (python3 $CS/tools/make_specs.py)"; failed="$failed $j"; continue; fi
  if [ -z "$ALLOW_NO_FURNITURE" ] && ! grep -q '"furniture": \[{' "$spec"; then
    echo "$j: $spec has no geometry.furniture (python3 $CS/tools/make_specs.py, or ALLOW_NO_FURNITURE=1)"; failed="$failed $j"; continue
  fi
  fresh=1
  for v in $views; do jpg=$out/$v.jpg; { [ -s "$jpg" ] && [ "$jpg" -nt "$spec" ] && [ "$jpg" -nt "$CAMS" ]; } || fresh=0; done
  if [ -z "$FORCE" ] && [ $fresh -eq 1 ]; then echo "$(date -u +%H:%M:%S) $j: newer than its spec, kept"; continue; fi
  cmd=(nice -n 19 flock "$LOCK" env PAINTED_BRICK=$pb "$PY" "$CS/tools/cycles_palette.py" "$spec" "$out" $views
       --samples=40 --size=1100x708 --cameras="$CAMS" --when="$WHEN" --foliage=summer)
  if [ -n "$DRY_RUN" ]; then echo "[dry run] ${cmd[*]} >> $LOG 2>&1"; continue; fi
  for v in $views; do rm -f "$out/$v.jpg"; done
  t0=$SECONDS
  { echo "=== $(date -u +%FT%TZ) $j (queued)"; echo "+ ${cmd[*]}"; } >> "$LOG"
  "${cmd[@]}" >> "$LOG" 2>&1; rc=$?
  miss=""; for v in $views; do [ -s "$out/$v.jpg" ] || miss="$miss $v"; done
  if [ $rc -eq 0 ] && [ -z "$miss" ]; then
    echo "$(date -u +%H:%M:%S) $j: rendered ($views), $((SECONDS - t0))s from queued to done" | tee -a "$LOG"
  else
    echo "$(date -u +%H:%M:%S) $j: FAILED (exit $rc, missing:$miss), see $LOG" | tee -a "$LOG"; failed="$failed $j"
  fi
done
[ -z "$failed" ] || { echo "not rendered:$failed"; exit 1; }
