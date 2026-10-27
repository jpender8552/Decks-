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
- Slab openings for the upper caissons: **$200 each** (`extras.labor_extras`).
- Lighting install: **$25 a fixture**, the transformer and runs included (pricebook `lighting_fixture_each`).
- A stair is stringers, treads, risers, fascia, railing and some blocking with joist tape — no mid-run carrier, no pad.
  A landing is its own scope (frame, decking, posts, caissons, guard).
- Louvered roof: **$175/SF → $35,000** (Suncoast, black, 20' x 10'). **Screens are not in the $175/SF: $15,000** (front + right end).

## Structure
- **Ledgered** on all three walls (B/C ledger at the 2-ft cantilevered floor = engineer's detail), not free-standing.
- **20" x 42" concrete caissons** (no Diamond Piers). Upper row through saw-cut openings in the patio slab, poured flush;
  lower row 7" above the beds.
- Deck columns: 8x8 Douglas fir rough on **Simpson ABU88RZ** (two cast-in 5/8" anchors).
- **Stair landing posts: 6x6 rough on ABU66RZ** (one cast-in anchor) on their own 12" x 42" caissons.
- 6x10 DF #1 drop beams; 2x10 TrueFrame @ 12" with joist tape. Measured heights: upper 8'-6¾", lower 5'-5¾" above the slab.

## Decking and rail
- TimberTech Vintage English Walnut; every field row one full-length board (no splices), **divider boards**, one picture frame.
- **12' grooved** is fine in the field under Cortex; **never 12' for the picture frame or dividers** (16/20' square edge).
- Offcuts become stair treads. Fascia may be spliced. Cortex plugged through the face; TOPLoc on the fascia.
- IRX black, vertical balusters, drink rail **over the posts**.

## Options
- Option 1 lighting (riser + post accent lights).
- Option 2 stairs to the yard: **show both** — 2 = the owner's horseshoe (7 + 3 risers, 9' x 4' landing), 2B = along the deck
  (1 + 9 risers, rail on the yard side only — the flight runs along the deck face). One or the other. **No mid-run
  carrier** (stair `mid_support` false); the stair foot is on grade (no pad).
- Option 3 louvered roof (own document), roof-line mount, 8'-11" clear; Option 3a screens $15,000.

## Renders
- Photoreal: the TimberTech skill's wire-brushed Vintage texture + greyscale relief maps; English Walnut from TimberTech's swatch;
  June 21 10:30 hero, summer foliage.
