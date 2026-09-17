# Decks — deck takeoff service

Give it a drawing or a picture plus a few lines of details, get back the complete takeoff:
foundations, framing (ledger, joists, double rims, picture-frame joists, drop or flush beams, posts, blocking),
hardware and connections, flashing and waterproofing, decking, fasteners, fascia, railing, stairs and risers —
every line written the way Decks & Docks sells it with **NET** (drawing count), **ORDER** (PO quantity) and the
reason they differ. It also flags setbacks, engineering triggers, snow, wind, fire (WUI), frost, guards and stair
code, and carries the GSX pricing model (sell / retail / monthly) for the bid.

Two GSX jobs are the standards the engine is held to, both as regression tests:

- **Eagle's Nest** (`examples/eagles_nest.json`, `tests/test_eagles_nest.py`) — the standard, rebuilt from the
  Session-Handoff v32 model. A jogged three-zone 617.2 SF timber-frame deck: DF #1 4x10 joists at 12" on one
  continuous 6x12 drop beam 3' back (6 posts) and a 6x12 flush beam in the deep wing (2 posts), 8 caissons with stone
  column bases, black hardware, Vintage Coastline square-shoulder on Cortex with a Dark Hickory border and dividers,
  IRX cable rail on 9 bays with a drink rail, hot-tub bay, 80 psf Summit County snow, WUI practice, engineered. The
  engine reproduces the handoff's order and lands within 1% of its $123,291 check / $132,571 financed, with the
  option menu priced both ways.
- **Jason Ct** (`examples/jason_ct.json`, `tests/test_jason_ct.py`) — the dimensional-lumber standard: 12 x 16 on
  2x10 SYP, drop 4x10 beam, Diamond Piers, Prime+ on EdgeClips, Fulton rail. Reproduced line for line.

Every framing, fastening and pricing rule is written down in `docs/standards.md`.

## Quick start

```bash
pip install -e ".[dev]"          # engine has no runtime deps; service/intake extras are optional

# from a spec file
python -m decktakeoff examples/jason_ct.json --price --out out/jason_ct

# from plain-English details
python -m decktakeoff --details "11'9 x 15'7.5 in Thornton, 30 in high, Prime+ Coconut Husk, Fulton black, 4 steps on the right, demo old deck" --price

# from a drawing / photo (Claude reads it; needs ANTHROPIC_API_KEY or `ant auth login`)
python -m decktakeoff --image drawing.png --details "Prime+ Coconut Husk, Fulton black, deck is 30 in above grade" --out out/job

# the client quote (Eagle's Nest format)
python -m decktakeoff examples/eagles_nest.json --quote

# the build set: drawing sheets, 3D model, renders and build steps (add --no-render without Chromium)
python -m decktakeoff examples/eagles_nest.json --price --out out/eagles_nest --buildset

# HTTP service
uvicorn decktakeoff.service:app --port 8000
#   POST /takeoff    {"spec": {...}} or {"details": "..."}  (+ "price": true, "gsx": true)
#   POST /intake     multipart image + details            -> spec read from the drawing + takeoff
#   POST /spec/parse {"details": "..."}                   -> DeckSpec JSON
```

Outputs (`--out DIR`): `takeoff.md` (design reads, order by category, fastener/connector schedule, cut list, flags,
pricing), `takeoff.json` (everything, machine-readable), `order.csv` (the D&D order), `spec.json` (the resolved spec),
`quote.md` (the client quote, with `--price`) and `gsx_job_block.py` — the geometry + BOM block that drops straight
into the `gsx-deck-docs` build-set / proposal PDF pipeline.

## Build set, permit set, 3D

`--buildset` writes `OUT/buildset/`:

- `sheets/*.svg` — the drawing set, one sheet per system, all generated from the same layout the takeoff counts
  from: **G-001** general notes and design criteria (loads, snow, frost, wind, WUI, the flags), **S-100** foundation
  plan (footing schedule, caisson / pier sizes, post loads), **S-101** framing plan (ledger, joists, beams, posts,
  blocking, hangers called out), **A-101** decking plan (rows, borders, dividers, cuts), **A-201** railing plan and
  elevation (post types, bays, cable / panel schedule), **A-301** section and front elevation, **D-501** details
  (ledger, post-beam-cap, footing, rail post, deck edge, the job's special condition). Every sheet carries the job
  line, the revision line and the "design intent / stamped set governs" footer, so the set is the permit submittal
  for a prescriptive deck and the design-intent set that goes to the engineer on an engineered one.
- `viewer.html` — a self-contained 3D model (three.js): orbit, zoom, preset views (yard, corner, on deck, iso, plan,
  under), build phases one at a time and an exploded view. Works on a phone.
- `renders/*.jpg` — stills from the same model (isometric, yard, corner, on-deck, underside, plan, exploded, one per
  build step). They are 3D model renders that show design intent, materials and colors; they are not photographs.
- `buildset.html` — the crew build set: steps **T-400 … T-406** (footings, posts, stone bases, beams, frame,
  decking, rail), each with the render of that phase, what goes in (from the takeoff), how, and what to check.
- `scene.json` — the model as boxes, for any other renderer.

`decktakeoff.buildset.build_set(takeoff, flags, out_dir, render=True)` does the same from Python.

## What goes in

`DeckSpec` (`decktakeoff/spec.py`) — geometry, site, framing, decking, railing, stairs, extras. Every field has a GSX
default, so a spec can be as small as `{"geometry": {"width": 12, "depth": 16, "height_in": 30}}`. Lengths accept
`15'-7 1/2"`, `11'9`, decimal feet or `187.5in`.

Conventions: plan view with the house at the top; **left / right are as you stand in the yard facing the house**;
width runs along the house, depth runs out from it. Rail openings and stairs are located the same way.

Stairs can be one straight flight or several: `"flights": [7, 6]` is down 7 risers to a landing, then 6 more; `"turn"`
is `switchback` (a horseshoe: flight 2 runs back alongside flight 1, on the `turn_side`) or `straight`; `landings`
lists the platforms between flights (framed on four posts, decked, counted with the stairs); `flight_rails` gives the
rail sides per flight and `landing_guard_lf` the guard on the landings' open sides (defaulted from the landing
perimeter less the stair widths in and out). The riser height is the same in every flight.

## What it decides (and states)

- **Nominal size in, frame size out** — "12 x 16" means 12' x 16' max over the fascia. The engine sizes the frame
  DOWN so every field board is a full board cut to a clean length (Jason Ct: 12 x 16 → 11'-9" x 15'-7 1/2" frame,
  11'-0" field boards, 33 rows) and states the finished dimensions. Pass `"size_mode": "frame"` to give
  outside-of-frame dimensions instead. Boards parallel to the house bear on two picture-frame joists set 5-1/4" from each face.
- **Zones** — jogged plans are a list of rectangular zones left to right facing the house, each on its own wall
  (recessed gables via `wall_offset`); the outline (fronts, steps, ends) drives the picture frame and the rail, with a
  divider board on every zone line. Rail goes on the edges you name (`"front:A"`, `"step:C-B"`, `"end:right"`).
- **Joists** #1 SYP 2x10 @ 16" OC (12" for PVC) checked against IRC R507.6; intermediate beams are added automatically
  when the depth is beyond the span, and said so. Timber frames (DF #1 4x10 @ 12", 6x12 beams, 8x8 posts) are checked
  with NDS-style bending and L/360 estimates and always flagged for the stamped set.
- **Beams** drop (4x DF, face 2' back from the rim, cantilever ≤ L/4) or flush (in-plane, joists hang both sides; a
  flush beam at the front *is* the front rim). Post spacing from IRC R507.5 on the joist span including the cantilever.
- **Posts / footings** 6x6 on Diamond Pier DP-50/50 (3,300 lb) via ABA66Z + BC46Z; auto-upgrades to DP-75/63 or flags;
  concrete piers sized from soil bearing and frost depth; drilled caissons (diameter, depth, rebar, ready-mix) with
  optional stone column bases; black powder-coat Outdoor Accents hardware when the job calls for it.
- **Connections** LUS hangers on every joist end, HUCQ concealed-flange doubles for the 2-ply rims, H2.5AZ at drop
  beams, DTT1Z lateral ties, LedgerLOK 2 rows staggered 12" OC, nails/screws counted by connector.
- **Waterproofing** membrane + Z-flash + end dams on the ledger, G-Tape 2" on joists/blocking, 4" on rims and beams.
- **Decking & fasteners** 100% hidden field (Camo EdgeClip on composite, CONCEALoc on PVC), face screws only at the
  first row, borders and fascia — counted per joist, per bearing point and per fascia piece. Cortex is refused on
  scalloped Prime+/Prime.
- **Rail** Fulton 2" steel posts inside the outer rim ply, END / LINE / CORNER typed, 6' and 8' panels chosen and cut
  lengths stated, rail LF = actual rail for labor, openings for concrete steps and stairs. IRX cable rail: posts 6' OC,
  top rail + cable kit per section, no bottom rail, drink-rail board and brackets on top.
- **Stairs** riser count and height (≤ 7-3/4"), tread depth from two deck boards, 2x12 stringers @ 12" OC for composite
  treads, LSCZ connectors, treads/risers, stair panels and posts, handrail when 4+ risers, landing pad.
- **Flags** (internal, never in client documents): setback violations, easements, HOA; engineering when tables don't
  apply (snow > 40 psf, hot tub, roof, > 10' high, spans/cantilevers exceeded, veneer or cantilevered-floor ledgers);
  wind ≥ 120 mph connector requirements; WUI product compliance; frost depth for concrete; guards over 30"; stair
  geometry and landings. See `docs/codes.md`.
- **Pricing** check/ACH = (materials × 1.15 + 4% tax + rate-card labor) ÷ (1 − 42.5% GM) + itemized general
  conditions at cost; financed = check ÷ 0.93 (12 / 18-month no-payment, 6.99% / 10-yr monthly); "what the price
  includes" at sell values summing exactly to the price; options as full installed deltas both ways by re-running the
  engine with the change; engineering shown as a range at cost, outside the price. Factor, tax, GM and GC method are
  per-job overrides (Jason Ct: 1.0 / 8.5% / 45% / $4 per SF).

## Layout

```
decktakeoff/
  spec.py          DeckSpec and friends (inputs, tolerant loader)
  units.py         feet-inches parsing / formatting
  catalog.py       TimberTech lineup, lumber, connectors, rail systems, tax table
  data/pricebook.json   unit costs + sources + labor rates (edit before a bid)
  engineering.py   IRC R507 span / beam / post / footing / ledger tables, stair geometry, snow scaling
  layout.py        geometry: joists, PF joists, beams, posts, footings, decking rows, rail posts, stairs
  takeoff.py       counts -> BOM lines (NET / ORDER / why), cut list, fastener schedule
  flags.py         site & code flags
  pricing.py       GSX pricing model
  report.py        markdown / JSON / CSV / gsx-deck-docs job block
  intake.py        plain-English parser + Claude drawing reader (structured output)
  scene.py         layout -> 3D scene (boxes, materials, phases, house context)
  viewer.py        three.js viewer HTML (orbit, views, phases, exploded)
  render.py        headless Chromium stills of the scene
  drawings.py      SVG drawing sheets G-001 / S-100 / S-101 / A-101 / A-201 / A-301 / D-501
  buildset.py      build steps T-400.. + buildset.html; build_set() writes the whole folder
  data/three.min.js  three.js r128, so renders work offline
  cli.py, service.py
docs/standards.md  the GSX rules the engine encodes
docs/codes.md      the flag rules and their code references
examples/          eagles_nest.json, jason_ct.json (regression fixtures), flush_beam_stairs.json, freestanding_concrete.json
tests/
```

## Honest limits

- One level. Jogged plans are handled as zones; true L-shapes (a wing running along a return wall) are best entered as
  zones with a recessed wall, and multi-level decks are one spec per level.
- Span tables are 2021 IRC prescriptive values; above 40 psf snow or 40 psf live the engine scales and flags for a
  stamped design — it never invents a span.
- Prices marked `est.` in the pricebook are placeholders; pull the latest D&D quote before the number goes on a bid.
- Setback / frost / snow / wind values are inputs — the engine checks them, it does not look them up.


## The job page — one template, every job

`decktakeoff/page.py` builds the document for a job. It is the only page builder; every job runs through it so they look the same.

```
python -m decktakeoff jobs/parkview_deck.json --out out/parkview --page customer --pdf --key pv --lede "One paragraph under the cover image."
python -m decktakeoff examples/eagles_nest.json --out out/eagles --page internal --key eagles
```

- `internal`: the takeoff + build set page (Eagle's Nest layout): design reads, flags, the order (NET / ORDER / why, or the quoted lines with a model cross-check), fastener schedule, cut list, the stack, the quote, renders, isometrics, explosions, drawings, build set, live 3D.
- `customer`: the proposal: black cover (title, prepared for, price bar, hero render, one paragraph), then at a glance, what it is, renders, isometrics, exploded views, structure, drawings without the internal block, materials without prices, fastening, build steps, investment, live 3D. Nothing internal, no names.
- `--pdf` prints a Letter PDF: cover locked to one page, sheets expanded, the 3D swapped for a still.
- The page references its renders as `r/<key>-<still>.jpg`; `files.json` maps each to the file on disk (publish them alongside the page).
