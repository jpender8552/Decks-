#!/bin/bash
# 7303 S Fillmore Cir - the final photoreal set (rendering agent). Run when the house, yard, structure, stairs and roof have
# landed in the assembler's specs ($SPEC_DIR). One Blender at a time across all agents (flock). Every set writes its
# images, a log, renders.json (per image: station, mode, local time, sun) and, at the end, captions.json.
#
#   bash render_final.sh                 # everything into $R/final (about 4 h on 4 cores)
#   bash render_final.sh base roof_open  # only these sets (names below)
#   OUT=$R/final/review DAY="--samples=24 --size=900x579" DUSK="--samples=48 --size=900x579 --dusk-exposure=3.2 --led=1.5" \
#       bash render_final.sh             # the review pass
#
# The matrix (owner: "separate renderings" for the base and each option):
#   base              base bid, day: the owner's photo vantage points + a high three-quarter view + the boards up close (ondeck)
#   yardstair         Option 2, stairs to the yard (the switchback / horseshoe), day
#   yardstair_alt     Option 2B, stairs to the yard along the deck edge, day - the same stations as yardstair
#   lights            Option 1 (riser lights + post accent lights), dusk
#   lights_yardstair  Option 1 with Option 2: the yard stair's lights, dusk
#   roof_open/half/closed   Option 3 louvered roof, louvers open (90) / half open (45) / closed (0), at 10:00, 13:00, 16:00
#   screens_down/half Option 3a screens (front + right end; the left end stays open over the stair) down / half down,
#                     louvers closed, 16:00; "screens up" = roof_closed at 16:00
#   roof_dusk         Option 3 at dusk with its LED strip on (louvers half open)
set -u
S=/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad
REPO=/home/user/Decks-
PY=$S/bvenv/bin/python
R=$S/fillmore/render
OUT=${OUT:-$R/final}                            # a fresh folder: no board textures cached from older palettes
SPEC_DIR=${SPEC_DIR:-$REPO/jobs}                 # the final fillmore_centennial{,_lighting,_yardstair,_yardstair_alt,_roof,_roof_screens}.json
VAR=$R/specs                                    # render variants written by tools/make_variants.py from $SPEC_DIR
HOUSE=${HOUSE:-$S/fillmore/house/house_model.json}   # inlined only into variants whose spec has no house_model yet
CAMS=${CAMS:-$R/cameras.json}                   # camera stations (site_model.cameras format, with "eye" heights)

# The sun. HERO: June 21, 10:30 AM MDT - the rear wall faces NNE (25.25 deg), so the back of the house only sees the sun
# in the morning; at 10:30 the sun is ESE (105 deg), 54 deg up, 80 deg off the wall's normal: it rakes across the siding,
# brick and rail from the arm end and 87 % of the deck is in sun (earlier, the 50-ft spruce and the creek cottonwoods
# shade most of it; after ~10:50 the whole back is in the house's shadow). The roof set moves the sun through the same day;
# dusk = the blue hour of that date (sun 5 deg below the horizon, 8:57 PM). The yard model is in its late-October colours;
# --foliage=summer greens the deciduous canopy so the June sun, the shade and the captions agree (coordinator, option a).
HERO=${HERO:-2026-06-21T10:30}
ROOF_TIMES=${ROOF_TIMES:-"10:00 13:00 16:00"}
SCREEN_TIME=${SCREEN_TIME:-16:00}
COMMON=${COMMON:-"--foliage=summer"}

DAY=${DAY:-"--samples=56 --size=1200x772"}                                                # the Prentice set's quality
DUSK=${DUSK:-"--samples=160 --size=1200x772 --dusk-exposure=3.2 --dusk-el=-5 --led=1.5"}  # many small lights, more samples

SETS="${*:-base yardstair yardstair_alt lights lights_yardstair roof_open roof_half roof_closed screens_down screens_half roof_dusk}"

python3 $R/tools/make_variants.py --spec-dir=$SPEC_DIR --out=$VAR --house=$HOUSE || exit 1
python3 - "$VAR/base.json" <<'EOF'
import json, sys
g = json.load(open(sys.argv[1]))["geometry"]
if not g.get("house_model"):
    print("WARNING: no geometry.house_model in the base variant (and no house_model.json to inline): the renders will have no house.", flush=True)
EOF
mkdir -p $OUT
cd $REPO

run() {   # run SET SPEC VIEWS... [--options]
    local set=$1 spec=$2; shift 2
    if [ ! -f $spec ]; then echo "=== skip $set: no $spec" | tee -a $OUT/render_final.log; return; fi
    mkdir -p $OUT/$set
    echo "=== $(date -u +%H:%M:%S) $set: $*" | tee -a $OUT/render_final.log
    flock $S/blender.lock $PY -m decktakeoff.cycles $spec $OUT/$set "$@" --cameras=$CAMS --when=$HERO $COMMON > $OUT/$set/log.txt 2>&1
    grep -h "^rendered\|Traceback\|Error:" $OUT/$set/log.txt | tee -a $OUT/render_final.log
}
at() {    # at STATION TIMES... -> STATION@T1 STATION@T2 ...
    local st=$1; shift
    for t in $*; do printf "%s@%s " $st $t; done
}

for set in $SETS; do
  case $set in
    base)             run base $VAR/base.json yard yard_left yard_center upper_deck ondeck high34 yard_along lower_deck arm upper_rail $DAY ;;   # the hero (yard) first
    yardstair|yardstair_alt)
                      run $set $VAR/$set.json stair_yard yard yard_left high34 $DAY ;;
    lights)           run lights $VAR/lights.json dusk dusk_deck upper_deck@dusk $DUSK ;;
    lights_yardstair) run lights_yardstair $VAR/lights_yardstair.json dusk_stair dusk $DUSK ;;
    roof_open|roof_half|roof_closed)
                      run $set $VAR/$set.json $(at roof_yard $ROOF_TIMES) $(at roof_deck $ROOF_TIMES) $DAY ;;
    screens_down|screens_half)
                      run $set $VAR/$set.json roof_yard@$SCREEN_TIME roof_deck@$SCREEN_TIME $DAY ;;
    roof_dusk)        run roof_dusk $VAR/roof_half.json roof_yard@dusk roof_deck@dusk $DUSK --led=0.7 --dusk-exposure=3.0 ;;   # the gutter LED strip lights the deck from 9': softer than the riser lights
    *) echo "unknown set $set" ;;
  esac
done

python3 $R/tools/make_captions.py $OUT $CAMS $VAR
echo "=== $(date -u +%H:%M:%S) done: $OUT" | tee -a $OUT/render_final.log
