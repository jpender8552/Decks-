# 7303 S Fillmore Cir, Centennial — owner decisions (decision log)

Read this before asking the owner anything about this job. Every line is the owner's own call (Jade, 26–27 Oct 2026).
Specs: `jobs/fillmore_centennial*.json` (base, _lighting, _yardstair, _yardstair_alt, _roof, _roof_screens, _all).

## Client and meeting
- Client: Andie Jones (buyer; the Alison C Kelman Trust is the seller). Lead via Colorado Deck Experts (GSX is the parent).
- Documents carry **GS Exterior Experts** branding. No promo / no "25% off".
- Proposal meeting: **Thu 29 Oct 2026, 4–5 pm Mountain** (Google Meet). Client documents final Wed 28 Oct evening.

## Pricing (the owner's own numbers — never estimate around them)
- **Margin: 40% on everything except the louvered roof and screens** (owner 27 Oct, latest). The rail, the stairs, the landings
  and the lights all price at their real cost / 0.6 — the fixed-rate rules (IRX $120/LF, $682/riser, landing $140/SF, $200 a
  light) are NOT used on this job (`extras.rail_sell_per_lf` 0, `extras.stair_rule` false, no `lights.sell_each`).
- **At cost, outside the 40%:** dumpster + portable toilet **$800**; **engineering** and **permit / plan review** billed at cost.
- Labor: the GSX card only (`GSX_Subcontractor_Labor_Rates` rev 14 Jul 2026). No day rates, hours or per-diem.
  Demo $2/SF (no column-demo line, no skirting line). Caisson $150/hole + large-footing (20"+) $150. Stairs $150 a riser,
  railing included.
- Slab openings for the upper caissons: **$200 each** (`extras.labor_extras`: 3 in the base, 4 in the roof version).
- Lighting install: **$25 a fixture**, the transformer and runs included (pricebook `lighting_fixture_each`).
- A stair is stringers, treads, risers, fascia, railing and some blocking with joist tape — no mid-run carrier, no pad.
  A landing is its own scope (frame, decking, posts, caissons, guard).
- Louvered roof: **$175/SF → $35,000** (Suncoast, black, 20' x 10'). **Screens are not in the $175/SF: $15,000** (front + right end).

## Structure
- **Ledgered** on all three walls (B/C ledger at the 2-ft cantilevered floor = engineer's detail), not free-standing.
- **Max spans, fewest columns, larger caissons** (owner 27 Oct: "You have way too many post", "I'd rather make the caissons
  larger for fewer post. Max spans"). **6x10 DF #1** drop beams on **8x8 DF #1 rough** columns (owner: "Yes use DF#1" — the calc
  uses DF-L No.1, Fb 1,350 psi), 2x10 TrueFrame @ 12" with joist tape.
- **The base is designed WITHOUT the roof; the roof has its own structure and its own document** (owner: "Do beams with and
  without roof cover... don't do the caissons or spans based on the roof for the base. I made that clear").
  - BASE, 8 columns on **24" x 42" caissons** (end bearing alone carries every column: max 4,179 lb vs 4,712):
    L1 x 2.6 / 15.0 / 26.85, A2 x 1.0 / 5.5, U1 x 32.77 / 46.17 / 59.52 (13'-4" spans, overhangs at L/4 — 3 columns is the
    6x10's deflection limit on U1; L1 and A2 are at their minimum).
  - ROOF VERSION (_roof / _roof_screens / _all), 9 columns: U1 x 29.97 / 39.87 / 49.94 / 62.60 with a column under each roof
    post, **30" x 42" caissons** under the upper level. Its deck structure is priced into Option 3 at the 40% margin.
  - Roof version + Option 2B (clash fix, 27 Oct; roof size, price and takeoff unchanged): U1 sits 2" toward the house (setback 3¼"), U1-1 and the left roof post 2" right (x 29.80 → 29.97), the left downspout runs 1'-3" along the patio, so the column clears the 2B flight by 2" — don't move them back.
  - **Roof + 2B both sold: pour the two together** (owner 27 Oct, "pour the two together"): U1-1's 30" caisson reaches ~8" under the back corner of 2B's foot, so the caisson and 2B's landing pad go in as one placement, the pad's top flush with the caisson top and the slab; the 2B stringers bear on it. The column does not move off the roof's corner.
- **Caissons flush with the patio slab** where they go through it (upper row); lower row 7" above the beds.
- **Never wet-set** (owner 27 Oct: "We don't wet set. ABU is meant to be placed once cured"): ABU88RZ / ABU66RZ go on after
  the cure on 5/8" Titen HD screw anchors drilled into the concrete (2 per ABU88, 1 per ABU66).
- **No knee braces** (owner 27 Oct): the lateral system is the house attachment (R507.9.2) + the deck diaphragm — PE confirms.
- Deck columns: 8x8 Douglas fir rough on **Simpson ABU88RZ**. **Stair landing posts: 6x6 rough on ABU66RZ** on their own
  12" x 42" caissons.
- Measured heights: upper 8'-6¾", lower 5'-5¾" above the slab.

## Decking and rail
- TimberTech Vintage English Walnut; every field row one full-length board (no splices), **divider boards**, one picture frame.
- **12' grooved** is fine in the field under Cortex; **never 12' for the picture frame or dividers** (16/20' square edge).
- Offcuts become stair treads. Fascia may be spliced. Cortex plugged through the face; TOPLoc on the fascia.
- IRX black, vertical balusters. **No drink rail** (owner 27 Oct: "take off the drink rail"): the posts keep their caps, and
  Option 1's post lights are LED cap lights.

## Site, demo and electrical (owner 27 Oct)
- **Access is good**: no Bad Access line.
- **Outdoor outlet is fine**: not in the price; the proposal's "still to confirm" line stays as worded.
- **Old brick-column footings: the owner has a plan** — nothing priced or assumed for them (no break-out line).

## Options
- **The base has only the stair between the levels (upper to lower) — never a stair to the ground.** Both yard stairs
  (2 and 2B) are EXTRA, one or the other (owner 27 Oct, repeated: "Get it right"). The base price line reads
  "Stair between the levels".
- **Lights are à la carte extras — never in the base** (owner 27 Oct: "No the lights are not in base price, they're extras. I
  never said that. I said to charge. They're a La carte"). Option 1 = riser + post accent lights; the yard stairs' lights are
  the add-on under each stair option. 40% margin; no per-light sell price in client text; $25 a fixture is the install labor.
- Option 2 stairs to the yard: **show both** — 2 = the owner's horseshoe (7 + 3 risers, 9' x 4' landing), 2B = along the deck
  (1 + 9 risers, rail on the yard side only — the flight runs along the deck face). One or the other. **No mid-run
  carrier** (stair `mid_support` false); the horseshoe's foot is on grade (no pad); 2B's foot is on a pad flush with the patio (below).
  - 2B's foot (27 Oct, lead): since the flight turned the other way (owner) it comes down at the patio's front edge, the back 9" of its width over the slab. It lands on a 4" concrete pad poured flush with the slab (rise 65.8" to the slab top, 10 risers @ 6.58") — never half on the slab, half on the lawn (a 4.8" uneven bottom riser).
- Option 3 louvered roof (own document), roof-line mount, 8'-11" clear; **the gutter LED strip is in the $35,000** (owner:
  "I have that in the bid"); plus its own deck structure (above). Option 3a screens $15,000.

## Styling
- **Outer outdoor furniture** (owner 27 Oct: "style with furniture and make it all outer.com outdoor furniture"), styling only — never
  priced, never in the drawings: teak frames with Pacific Fog Gray cushions. Lower level B: Teak L Sectional 4-Seat, Teak Coffee
  Table, 2 Teak Armchairs. Upper C: Teak + Aluminum Extendable Dining Table with 595 dining chairs (4 armless + 2 arm). Upper D:
  2 Teak Armchairs + Teak Side Table.
- **Exterior color study** is a separate document (not the main proposal). **Andie wants the house tan or cream** (owner 27 Oct),
  so the study is tan and cream, in Sherwin-Williams colors, with the buff brick left unpainted in every palette: Cream (SW 7012
  Creamy, body and trim), Light tan (SW 7036 Accessible Beige, SW 7008 Alabaster trim), Khaki (SW 6150 Universal Khaki, Creamy
  trim); recommended Creamy with SW 6258 Tricorn Black fascia, gutters and downspouts, deck English Walnut as proposed (Vintage
  Dark Hickory shown for comparison). The earlier dark study (gray / charcoal / black, recommended charcoal + Mahogany deck) is
  superseded; it is in the color study page's version history. The main proposal still shows today's colors.

## Renders
- Photoreal: the TimberTech skill's wire-brushed Vintage texture + greyscale relief maps; English Walnut from TimberTech's swatch;
  June 21 10:30 hero, summer foliage.
