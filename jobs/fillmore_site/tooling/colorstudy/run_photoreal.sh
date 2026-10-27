#!/bin/bash
# Exterior color study, 7303 S Fillmore Cir: the photoreal stills, then the final page and PDF, in one go. Queue it yourself:
#     bash /tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad/fillmore/colorstudy/tools/run_photoreal.sh
#     DRY_RUN=1 bash .../run_photoreal.sh      echoes every command, runs nothing
#   1. make_specs.py   specs/*.json from the current job (furniture included); a spec that does not change keeps its mtime
#   2. cycles_all.sh   the seven Cycles stills the page reads: yard x5 (gray, charcoal, black, recommended, existing) and the upper
#                      deck x2 (charcoal_up, recommended_up). Each under  nice -n 19 flock $S/blender.lock,  output in cycles/run.log
#   3. build_colorstudy.py with the Letter PDF (nice -n 19), only when all seven stills exist; then a check that the page holds them
# Estimate: about 15 minutes of Blender once the lock is yours. The old logs: 5 yards at about 2.0 min and 2 upper decks at about
# 1.5 min = 13 to 14 min; the furniture is 6% more scene boxes and a few more shader nodes, so 5 to 10% more. Then under a minute for
# the page and PDF. Waiting for the main queue's lock is on top. Everything is logged in cycles/run.log.
# Stopped or failed part-way: run it again, the stills that finished are kept (cycles_all.sh) and only the rest renders.
S=/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad; CS=$S/fillmore/colorstudy
LOG=$CS/cycles/run.log; JOB=/home/user/Decks-/jobs/fillmore_centennial.json
mkdir -p "$CS/cycles"
say() { echo "$@"; [ -n "$DRY_RUN" ] || echo "$@" >> "$LOG"; }
T0=$SECONDS
say "##### run_photoreal.sh $(date -u +%FT%TZ)${DRY_RUN:+ (dry run: nothing is executed)}"

# 1. specs
if [ -n "$DRY_RUN" ]; then echo "[dry run] python3 -B $CS/tools/make_specs.py"
else python3 -B "$CS/tools/make_specs.py" 2>&1 | tee -a "$LOG"; [ "${PIPESTATUS[0]}" -eq 0 ] || { say "make_specs.py failed, stopping"; exit 1; }; fi
old3=$(find "$CS/renders" -name '*.jpg' ! -newer "$JOB" 2>/dev/null | wc -l)
[ "$old3" -eq 0 ] || say "WARNING: $old3 three.js stills in renders/ are older than the job file; run tools/render_palettes.py to refresh them if the change shows"

# 2. the Cycles stills
DRY_RUN=$DRY_RUN bash "$CS/tools/cycles_all.sh"; rc=$?
if [ $rc -ne 0 ]; then say "some Cycles stills are missing: not building the page. Run this again, the finished ones are kept."; exit 1; fi

# 3. page and PDF
cd /home/user/Decks- || exit 1
if [ -n "$DRY_RUN" ]; then
  echo "[dry run] nice -n 19 python3 -B $CS/tools/build_colorstudy.py >> $LOG 2>&1"
  echo "[dry run] then: cmp each cycles still with its r/ copy, and check the PDF is newer than page.html"
  exit 0
fi
say "$(date -u +%H:%M:%S) building the page and PDF"
nice -n 19 python3 -B "$CS/tools/build_colorstudy.py" >> "$LOG" 2>&1 || { say "build_colorstudy.py failed, see $LOG"; exit 1; }
n=0
for pair in gray/yard:cs-gray-yard charcoal/yard:cs-charcoal-yard black/yard:cs-black-yard recommended/yard:cs-recommended-yard \
            existing/yard:cs-today-yard charcoal_up/upper_deck:cs-deck-english-walnut-upper recommended_up/upper_deck:cs-deck-mahogany-upper; do
  cmp -s "$CS/cycles/${pair%%:*}.jpg" "$CS/r/${pair##*:}.jpg" && n=$((n + 1)) || say "NOT in the page: cycles/${pair%%:*}.jpg"
done
pdf=$(ls "$CS"/*.pdf 2>/dev/null | head -1)
[ -n "$pdf" ] && [ "$pdf" -nt "$CS/page.html" ] && say "pdf: $pdf" || say "WARNING: no PDF newer than page.html"
say "$(date -u +%H:%M:%S) done: $n/7 photoreal stills in the page, $(((SECONDS - T0) / 60)) min in all"
[ $n -eq 7 ]
