# 7303 S Fillmore Cir — shared brief for every agent (read this first)

S = /tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad
Repo = /home/user/Decks- (Python package `decktakeoff`; GSX deck takeoff / documents / 3D engine)

## The job (owner's words in quotes)
7303 S Fillmore Cir, Centennial CO 80122 — owner Andie. "Replace the same footprint... Full rebuild." Elevated two-level deck
across the back of a split-level house with a walk-out patio under the upper level.

Base bid:
- Frame: 2x10 SYP TrueFrame joists @ 12" OC with joist tape; 6x10 Douglas fir DROP beams; 8x8 Douglas fir rough columns
  ("instead of brick columns" — the existing brick columns come out); Diamond Pier footings.
- Decking: TimberTech Vintage (PVC) English Walnut — "no butt joints", breaker boards on the zone lines A|B, B|C, C|D (the
  owner's sketch, u05); "All Cortex plugged and screwed through the face" (field included); "Normal fascia" (English Walnut).
- Rail: TimberTech Impression Rail Express (IRX), black, vertical balusters, with a drink rail (Vintage English Walnut cap).
- Inter-level stair (upper -> lower): "inset them like this project" — the stair is recessed into the upper level (a notch cut
  into the upper level's left face at the B|C line; bottom riser flush with the step face); the whole step face between the
  levels (36") is a skirt of Vintage English Walnut fascia boards installed VERTICALLY (no lattice).
- Lighting: "step lighting on risers and post cap lights" — a recessed LED light in every riser, an LED post-cap light on every
  rail post (low voltage, transformer + photocell/timer).
- Demo of the existing deck.

Option (priced inside the proposal and rendered): stair from the lower level to the yard — "roughly (staring at the house) 6' ish
from the stairs going to the lower level, down to a 9' landing (4' wide stairs) then horseshoe back towards the house": 4'-wide
flight 1 out from the lower level's outer edge (its right side ~6' left of the step face x=29.167, i.e. opening x ≈ 19.17–23.17),
a 9'-wide x 4'-deep landing, flight 2 switching back toward the house alongside flight 1, to grade.

Separate document: "a black louvered roof over the main section attaching to the soffit or roof line of the current [house].
This is a 20x10 section of the upper deck" — Suncoast Louvered Roof (https://suncoastenclosures.com/louvered-roof/), black,
over zone C (x ≈ 29.6–49.6, y 0–10).

Renders: photorealistic, the real house and yard, the sun at the address at a stated date/time (and a dusk view with the lights on).

LOUVERED ROOF STRUCTURE (owner): "the post should integrate with the railing. So those become the railing post in the section or
where they tie in. It sits on top of the deck with 2 post and connect to the house." — exactly 2 roof posts, standing on the upper
deck at its OUTER edge on the rail line (the roof's outer corners, about x 29.6 and 49.6, y ≈ 10); they replace the IRX rail posts
there (the IRX sections terminate into them); the house side is attached at the soffit/roof line (no posts at the house).

OWNER DECISIONS (27 Oct, later): drink rail OVER the posts (no post caps -> the lighting option uses post-side accent lights);
lights sell at $200 each installed, margin included (all-in); "12' boards do exist" (Vintage square 12/16/20' — the engine
has them); "We need DP-50": Diamond Pier DP-50/50 everywhere, framing.footing_model_lock = true (the engine adds posts / shortens
spacing instead of upgrading; DP-50 = 3,300 lb at 1,500 psf per the Pin Foundations chart).
SITE (README.md): the house is FOR SALE (MLS 6803070, listed 1 Oct 2026); owner of record Alison C Kelman Trust; rear faces NNE;
brick veneer + a 2' cantilevered floor along B/C (ledger may need an engineer, or a free-standing deck); Tiffany HOA approval
(3 weeks, drawings + samples); yard-stair zoning question (steps <= 4' above grade only to 15' from the rear line; the deck edge
is 12.8–14.1' from it).

PRICING (owner, confirmed): the louvered roof sells at $175/SF of roof area — 20' x 10' = 200 SF = $35,000, in its own document.
The deck is priced by the engine (cost + 40% gross margin, extras.gm = 0.4); the yard-stair option as an engine delta.

## DELIVERABLE STRUCTURE (owner, latest — this overrides anything above that conflicts)
"Remember, we're doing a base deck with railing with two levels. Then we have options for lighting, stairs to the ground, the
louvered roof. Want everything broken out, including separate renderings."
- BASE BID: the two-level deck with IRX rail + drink rail, the inset stair between the levels with its vertical-board skirt,
  demo. NO lighting in the base.
- OPTION 1 — LIGHTING: LED riser lights (every riser) + LED post-cap lights (every rail post), transformer/photocell/timer, wire,
  labor. Priced as its own line (engine delta at the job margin). If the yard stair is also chosen, its risers/posts add lights:
  show that add-on amount separately.
- OPTION 2 — STAIRS TO THE GROUND (the switchback yard stair). Priced as an engine delta.
- OPTION 3 — LOUVERED ROOF: $175/SF x 200 SF = $35,000; also its own whole document.
- OPTION 3a — ROOF SCREENS (owner: "Show an option for screens to come down on the louvered roof. I want to control it on the
  3-d."): motorized retractable screens on the roof's open sides (front 20', both 10' ends), its own price line under the roof
  (price not set by the owner yet — estimate, flagged), renders down/up, an up/down control in the 3D page.
- SEPARATE RENDERINGS for each: base (day), base + yard stair, lighting at night (lights lit), louvered roof with the louvers
  OPEN and CLOSED at several times of day (the shade moving on the deck).
- 3D: "don't worry about the 3-d that I can spin and zoom and see everything. It often doesn't work and I do PDFs." Instead: ONE
  simple interactive 3D page — toggles base / + stairs / + lights / + louvered roof; a time-of-day slider (real sun at the address,
  shade and shadows), the louvers open/close and stop at any angle, lights glowing at night; no framing layers, no exploded views.
  The documents are PDF-first; the customer proposal links to the interactive page instead of embedding the old viewer.

## Plan frame (feet) — every agent uses this
- x along the house, LEFT to RIGHT as you stand in the yard facing the house; x = 0 at the deck's left end (arm A's open side).
- y from the main rear wall (behind zones B and C; y = 0) toward the yard; the deck's outer edge is y = 10.
- z up from the top of the walk-out patio slab under the upper level (z = 0). Placeholders until photo_measure.md lands:
  upper deck surface z = 10.25, lower deck surface z = 7.25 (36" apart — the owner's sketch says "3' ↑").
- Zones (owner's sketch u05; 63' overall):
  - A  x 0–7.583: an arm 7'-7" wide reaching back to a slider in a "door wall" at y ≈ -12.833 (sketch jogs 2'-4" + 5' + 5'-6";
    the sketch's 23'-6" on A's left side would put it at -13.5 — to be resolved from photos/aerials). Its right side is the house's
    side wall at x = 7.583 with a brick chimney mass bumping 1'-9" into A: x 5.833–7.583 for y -5.5 to -10.5.
  - B  x 7.583–29.167 (21'-7"): lower level, 10' deep.
  - C  x 29.167–50.167 (21'): upper level (+36"), 10' deep.
  - D  x 50.167–63.083 (12'-11"): upper level, its house wall set back 2' (y = -2), 12' deep.
- Lower level = A + B; upper level = C + D.

## Engine facts
- A two-level deck is a COMPOSITE: geometry.parts = [lower part (zones A, B; origin [0, 0]), upper part (zones C, D; origin
  [29.1667, 0])]. Each part is an ordinary zone deck (its own height_in, outline, rail edges, stairs) taken off by the normal
  engine; composite.py merges the lines; scene.build_composite_scene places each part's boxes in the global frame and draws
  geometry.house_model / geometry.site_model ONCE in the global frame. Stairs belong to the part they leave (landing "deck" =
  lands on the other level).
- Draft spec that runs end to end (placeholder numbers): $S/fillmore/draft/fillmore_draft.json;
  `python3 $S/fillmore/draft/run_draft.py <spec.json>` prints the takeoff summary + flags.
- Documents: `from decktakeoff.page import render_page, render_permit_set`;
  render_page(spec, out_dir, mode="internal"|"proposal"|"supplier"|"cost", key="x", name="...", sub="...", render=False, pdf=False)
  render_permit_set([dict(spec=spec, title="...")], out_dir, key="xk", name="...", sub="...", pdf=False)
- 3D: `from decktakeoff.composite import build_composite; from decktakeoff.scene import build_scene;
  sc = build_scene(build_composite(spec)[0].layout)`; WebGL stills: `decktakeoff.render.render_stills(sc, out_dir, which=["yard","iso"])`.
- Photoreal: `$S/bvenv/bin/python -m decktakeoff.cycles <spec.json> <out_dir> yard corner --quick --samples=24 --size=960x620`.
  Blender is CPU-heavy: ALWAYS run it as `flock $S/blender.lock <command>` (one Blender at a time across all agents) and in the
  background; only the rendering and house agents run Cycles.
- Tests: `cd /home/user/Decks- && python3 -m pytest -q tests` (43 pass).
- Skills with GSX standards (read if your work touches them): /root/.claude/skills/synced/*/gsx-deck-docs/references/standards.md,
  /root/.claude/skills/synced/*/timbertech-boards/ (TimberTech catalog + board renderer).

## Photos (the owner's, all of the back of this house)
$S/fillmore_photos/all/u01..u20 (contact sheets sheet_a/b/c.jpg). u05 = the owner's dimension sketch. u01/u02 from the yard
(lower level on brick columns; upper level on 5 brick columns over the walk-out patio), u03/u04/u10/u20 on the lower level and arm
A, u06/u07/u18 upper level, u07/u08/u09 the inter-level stair, u11/u16 under the upper level (patio, existing framing), u12/u13/u17
from the right side of the yard, u14/u15 the D end, u19 the left end. Reference photos of the inset-stair look the owner wants are
described above (a recessed 3-riser stair in a vertical-board skirt, riser lights).

## Agents and who owns what (edit only what you own)
| Agent | Owns (repo) | Writes to |
|---|---|---|
| site research (GIS, parcel, orthos, terrain, zoning) | — | $S/fillmore/README.md |
| photo measure | — | $S/fillmore/photo_measure.md |
| structure | — | $S/fillmore/structure.md |
| materials + pricing | — | $S/fillmore/materials.md |
| house model | house.py; cycles.py Tex + texture/material code for brick & siding; viewer.py patternTex | $S/fillmore/house/ |
| landscape / yard | landscape.py | $S/fillmore/site/ |
| louvered roof research | — | $S/fillmore/louvered/research.md |
| louvered roof engine | NEW decktakeoff/louvered.py + one-line hooks (spec.py field, scene.py call, takeoff/pricing call, drawings sheet) | $S/fillmore/louvered/ |
| stairs (inset stair, step-face skirt, yard stair option) | layout.py stair code; scene.py stair section (+ skirt); takeoff.py stair lines; composite.py stair landing | $S/fillmore/stairs/ |
| lighting (riser + post-cap lights) | NEW decktakeoff/lighting.py + one-line hooks in scene.py / takeoff.py / pricing.py | $S/fillmore/lighting/ |
| drawings + build set for two-level decks | drawings.py, buildset.py | $S/fillmore/drawings/ |
| rendering (cameras, sun/time, dusk, Cycles QA) | cycles.py world/lights/cameras/main + emission materials (NOT Tex/brick/siding code) | $S/fillmore/render/ |
| proposals + pricing mechanics | page.py, proposal_look.py, report.py, pricing.py | $S/fillmore/docs/ |
| permit / zoning / code research | — | $S/fillmore/permit/ |
| footings | — (recommends engine changes) | $S/fillmore/footings/ |
| decking layout (boards, breakers, no butt joints) | layout.py decking functions only if needed | $S/fillmore/decking/ |
| 3D configurator (interactive page: options, time of day, louvers, night lights) | NEW decktakeoff/configurator.py (+ its JS) | $S/fillmore/configurator/ |
| spec assembler (base + option specs from everyone's outputs) | — | $S/fillmore/spec/ |
| demo + logistics + site protection | — | $S/fillmore/demo/ |
| schedule (lead times, permit, crew days) | — | $S/fillmore/schedule/ |
| estimate cross-check (independent price check) | — | $S/fillmore/estimate/ |
| engineering calc package | NEW decktakeoff/calcs.py (+ one hook for a calc sheet) | $S/fillmore/calcs/ |
| color check (Vintage English Walnut, IRX black) | — | $S/fillmore/color/ |
| customer copy (proposal + roof document text) | — | $S/fillmore/copy/ |
| hub + publishing prep | — | $S/fillmore/publish/ |
The lead (main session) owns jobs/fillmore_centennial*.json, composite.py outside the stair landing, and integration.

## Rules
- Never run git commit / push / checkout / stash / reset. The lead commits.
- Many agents edit this repo at the same time: change shared files ONLY with the Edit tool (small exact replacements), re-read
  the region right before each edit, never rewrite a whole engine file, stay inside what you own. If an import fails in a file you
  don't own, wait a minute and retry — never "fix" another agent's half-finished edit.
- Keep every existing job (jobs/*.json, examples/*.json) producing the same output; run the tests before you finish.
- Read the other agents' output files when they exist; don't redo their work.
- Customer-facing text: facts only, no sales language, no permit/AHJ wording unless the task is the permit set.
- Finish with a short report: what you changed (files, functions, spec keys), what you produced (paths), what's still open.
