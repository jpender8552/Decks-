# Decks — deck takeoff service

Give it a drawing or a picture plus a few lines of details, get back the complete takeoff:
foundations, framing (ledger, joists, double rims, picture-frame joists, drop or flush beams, posts, blocking),
hardware and connections, flashing and waterproofing, decking, fasteners, fascia, railing, stairs and risers —
every line written the way Decks & Docks sells it with **NET** (drawing count), **ORDER** (PO quantity) and the
reason they differ. It also flags setbacks, engineering triggers, snow, wind, fire (WUI), frost, guards and stair
code, and carries the GSX pricing model (sell / retail / monthly) for the bid.

The engine reproduces the approved 9528 Jason Ct hand takeoff line for line (`tests/test_jason_ct.py`) and encodes
every framing, fastening and pricing rule in `docs/standards.md`.

## Quick start

```bash
pip install -e ".[dev]"          # engine has no runtime deps; service/intake extras are optional

# from a spec file
python -m decktakeoff examples/jason_ct.json --price --out out/jason_ct

# from plain-English details
python -m decktakeoff --details "11'9 x 15'7.5 in Thornton, 30 in high, Prime+ Coconut Husk, Fulton black, 4 steps on the right, demo old deck" --price

# from a drawing / photo (Claude reads it; needs ANTHROPIC_API_KEY or `ant auth login`)
python -m decktakeoff --image drawing.png --details "Prime+ Coconut Husk, Fulton black, deck is 30 in above grade" --out out/job

# HTTP service
uvicorn decktakeoff.service:app --port 8000
#   POST /takeoff    {"spec": {...}} or {"details": "..."}  (+ "price": true, "gsx": true)
#   POST /intake     multipart image + details            -> spec read from the drawing + takeoff
#   POST /spec/parse {"details": "..."}                   -> DeckSpec JSON
```

Outputs (`--out DIR`): `takeoff.md` (design reads, order by category, fastener/connector schedule, cut list, flags,
pricing), `takeoff.json` (everything, machine-readable), `order.csv` (the D&D order), `spec.json` (the resolved spec)
and `gsx_job_block.py` — the geometry + BOM block that drops straight into the `gsx-deck-docs` build-set / proposal
PDF pipeline.

## What goes in

`DeckSpec` (`decktakeoff/spec.py`) — geometry, site, framing, decking, railing, stairs, extras. Every field has a GSX
default, so a spec can be as small as `{"geometry": {"width": 12, "depth": 16, "height_in": 30}}`. Lengths accept
`15'-7 1/2"`, `11'9`, decimal feet or `187.5in`.

Conventions: plan view with the house at the top; **left / right are as you stand in the yard facing the house**;
width runs along the house, depth runs out from it. Rail openings and stairs are located the same way.

## What it decides (and states)

- **Frame sized to the decking** — the depth is nudged so every field board is a full board (zero rips); the finished
  dimensions are stated. Boards parallel to the house bear on two picture-frame joists set 5-1/4" from each face.
- **Joists** #1 SYP 2x10 @ 16" OC (12" for PVC) checked against IRC R507.6; intermediate beams are added automatically
  when the depth is beyond the span, and said so.
- **Beams** drop (4x DF, face 2' back from the rim, cantilever ≤ L/4) or flush (in-plane, joists hang both sides; a
  flush beam at the front *is* the front rim). Post spacing from IRC R507.5 on the joist span including the cantilever.
- **Posts / footings** 6x6 on Diamond Pier DP-50/50 (3,300 lb) via ABA66Z + BC46Z; auto-upgrades to DP-75/63 or flags;
  concrete piers sized from soil bearing and frost depth when specified.
- **Connections** LUS hangers on every joist end, HUCQ concealed-flange doubles for the 2-ply rims, H2.5AZ at drop
  beams, DTT1Z lateral ties, LedgerLOK 2 rows staggered 12" OC, nails/screws counted by connector.
- **Waterproofing** membrane + Z-flash + end dams on the ledger, G-Tape 2" on joists/blocking, 4" on rims and beams.
- **Decking & fasteners** 100% hidden field (Camo EdgeClip on composite, CONCEALoc on PVC), face screws only at the
  first row, borders and fascia — counted per joist, per bearing point and per fascia piece. Cortex is refused on
  scalloped Prime+/Prime.
- **Rail** Fulton 2" steel posts inside the outer rim ply, END / LINE / CORNER typed, 6' and 8' panels chosen and cut
  lengths stated, rail LF = actual rail for labor, openings for concrete steps and stairs.
- **Stairs** riser count and height (≤ 7-3/4"), tread depth from two deck boards, 2x12 stringers @ 12" OC for composite
  treads, LSCZ connectors, treads/risers, stair panels and posts, handrail when 4+ risers, landing pad.
- **Flags** (internal, never in client documents): setback violations, easements, HOA; engineering when tables don't
  apply (snow > 40 psf, hot tub, roof, > 10' high, spans/cantilevers exceeded, veneer or cantilevered-floor ledgers);
  wind ≥ 120 mph connector requirements; WUI product compliance; frost depth for concrete; guards over 30"; stair
  geometry and landings. See `docs/codes.md`.
- **Pricing** sell = (materials + destination tax + labor) / (1 − GM) + general conditions at cost; retail (financed)
  = (sell − GC) / 0.93 + GC; 6.99% / 10-yr monthly; client allocation summing exactly to the sell.

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
  cli.py, service.py
docs/standards.md  the GSX rules the engine encodes
docs/codes.md      the flag rules and their code references
examples/          jason_ct.json (regression fixture), flush_beam_stairs.json, freestanding_concrete.json
tests/
```

## Honest limits

- Rectangles (one level). L-shapes and multi-level decks are taken off on the bounding rectangle and flagged.
- Span tables are 2021 IRC prescriptive values; above 40 psf snow or 40 psf live the engine scales and flags for a
  stamped design — it never invents a span.
- Prices marked `est.` in the pricebook are placeholders; pull the latest D&D quote before the number goes on a bid.
- Setback / frost / snow / wind values are inputs — the engine checks them, it does not look them up.
