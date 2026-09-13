# GSX deck standards encoded in the engine

Every line is a correction Jade Pender made once and does not want to make again. `decktakeoff` treats these as
defaults and refuses the ones that are rules. **Eagle's Nest is the standard** (quote format, pricing method, timber /
multi-zone / engineered decks); Jason Ct is the dimensional-lumber standard.

## Eagle's Nest (9 Eagle's Nest Ct, Silverthorne — handoff v32, 8 Sep 2026)
Source of record: the Session-Handoff JSON (model.py) and gsx-deck-sell-package/SKILL.md. The engine reproduces its
takeoff and stack: 8 posts / 8 caissons, 96 Coastline boards, 4 x 16' + 2 x 20' Dark Hickory, 9 Cortex boxes, 9 IRX kits,
10 post kits, 5 drink-rail boards, 3 boxes LedgerLOK 6", 2 Vycor, 8 + 8 flashings, 120 bags; labor $24,080.76, GC $7,200,
sell $123,291 (engine within 1%), financed $132,571.
- Plan: zones named left to right facing the house from the yard (C deep wing · B dining terrace at the jog · A lounge).
  The outer (rail) edge is STRAIGHT; the house walls jog (B 2' back, C 16' back). SF sold = frame area (617.2), the 1-1/2"
  board overhang is not counted. 55.2' along the view. Widths are decimal feet (14.6 / 12.6), field verify.
- Beams: B1 = one continuous 6x12 drop beam 3'-0" (CL) behind the outer rim under all three zones, 6 posts, pieces
  <= 16' spliced over posts; B2 = 6x12 FLUSH beam 12' back in zone C, joists hung on both faces (upper / lower pieces),
  2 posts. Post lengths: 67-1/4" under the drop beam, 76-1/2" under the flush beam (6" caisson above grade).
- Cantilever 3' past B1 with 4' / 6' / 9' back-spans exceeds L/4 in A and B: owner-directed, engineered condition —
  the engine keeps the declared cantilever on engineered jobs and flags it.
- Blocking: 4x10 blocks over the drop beam and wherever an unblocked run between supports would exceed 4'; none in
  the cantilever. Rail-post blocks 10-1/2" at every rail post.
- Dividers: Dark Hickory on every zone line (to the shallower zone's wall — D3 dies at row 18) and mid-zone where a run
  would exceed 16' (D1 splits zone A into two 13'-7" runs). A doubled joist under every divider; rail posts land on the
  divider lines (RP3 / RP5 / RP7). No butt joints in the field.
- Decking rows: 5-1/2" boards, 1/8" gap, border 5-1/2" + gap from the 1-1/2" overhang; rows = floor((depth − 4) / 5.625)
  with a rip at the house (A 14 rows, B 18, C 48). Rip strips are packed into full boards.
- Hardware: LUS410Z at the ledgers, at the two rim ends and on both faces of the flush beam; HUC410 for doubled joists
  and hung rims; H2.5AZ at every member crossing the drop beam; CCQ68 caps on intermediate posts, ECCQ68 on beam-end
  posts; APB88 black bases on 5/8" x 8" cast-in anchors; HeadLOK 6" x 4 per rail post; LedgerLOK 6" 2 rows staggered
  16" = one per 8" of ledgered wall (ledgers + return walls, 71 LF; nothing on the privacy wall).
- Wall: Vycor 12" membrane (75' rolls, laps), aluminum L-flashing 10', and 26 ga galvanized wall flashing 12" (CWRC
  404.3.2) — house walls only. G-Tape 4" on every 4x10 top and the beams, 2" on blocking.
- Caissons: Sonotube 20" x 12' cut to 48" (3 per tube), 15 bags per caisson, (4) #4 verticals + #3 ties, engineer governs.
- Timber frame: Douglas fir #1, 8x8 posts, 6x12 beams, 4x10 joists at 12", single 4x rims, no fascia, end grain sealed,
  unfinished (weathers gray); dark walnut oil, two coats on every timber, is an option. Tub bay doubled.
- Foundation: drilled caissons (20" x 42", rebar, frost 40") with stone-veneer column bases 2'x2' x 3' + 24" cap at every
  post. All visible hardware black powder-coat.
- Decking: TimberTech Advanced PVC Vintage (Coastline), square-shoulder, 1/8" gaps, Cortex with color-matched plugs;
  picture frame and dividers in a contrast color (Dark Hickory); no fascia. Class A / WUI.
- Rail: TimberTech Impression Rail Express cable, matte black, 36", no bottom rail, posts 6' OC, drink rail (contrast
  deck board) on top. Rail only on the named edges (view edge + the end); none along a privacy wall.
- Loads: 80 psf Summit County snow, stamped by a Colorado engineer. Colorado Wildfire Resiliency Code practice: Class A
  decking, noncombustible rail, metal flashing at every wall.
- Quote: total investment (financed, no money down, 12 / 18 months no payments, 6.99% / 10 yr monthly; tagline "Let our
  money work for you, and let your money work in the market.") and check or ACH (7% savings) — never "cash";
  "what the price includes" by scope at SELL values summing to the total; engineering $1,800–3,000 at cost, no markup,
  outside the price, not financed, the homeowner owns the stamped set; options as full installed deltas (both prices);
  payment terms are NOT on the quote (they go on the fixed-price proposal); "quote, not a contract — a fixed-price
  proposal follows the stamped engineering"; schedule in working days (18 for this job) ending "end of construction" —
  no walk-through / sign-off / close-out day.
- Never invent scope: nothing GSX "provides" goes in a document unless Jade said so — no spare boards, plug packs,
  care guides, warranty packets, workmanship warranties, working hours, confirmation promises.
- Voice: customer-facing documents are facts only (what it is, what is included, the price, the sequence); Jade writes
  the sell. No permit / election / RFI / EST / hold-point / vendor language in homeowner documents.
- Colors: Vintage Coastline is a pure neutral gray (no tan); Vintage Dark Hickory is a very dark gray, not brown.

## Framing
- Joists: #1 True Frame Joist SYP ground-contact, 2x10 @ 16" OC unless specified (12" OC for TimberTech Advanced PVC).
- Rims: double front rim, double side rims. Never add plies (a 3- or 4-ply rim is flagged).
- Double rims hang in Simpson HUCQ210-2-SDS concealed-flange double hangers (laminate the pair first, then hang).
  LUS28Z is for single joists only.
- Boards parallel to the house bear on a picture-frame joist set 1-1/2" inboard of the double rim (centre 5-1/4" from
  the frame face). Board ends are clipped there, never screwed.
- Rail posts: 2" Fulton posts inside the outer rim ply, inner ply pocketed 2" wide, post + nut in the 1-1/2" gap before
  the PF joist, (2) 7/16" x 4-1/2" HDG bolts per post.
- Blocking: one row, over the beam (composite). Two rows only for PVC.
- Drop beam: 4x10 DF #2, beam face 2'-0" back from the rim face. Cantilever checked against L/4; beam span from IRC
  R507.5 on the joist span including the cantilever (this is what puts three DP-50s under a 12' beam).
- Flush beam: in-plane, joists hang from both sides in LUS hangers; a flush beam at the front IS the front rim.
- Posts: 6x6 on Simpson ABA66Z bases on the Diamond Pier 1/2" bolt, BC46Z caps to a 4x beam. Post length =
  deck height − board − joist − beam − 4-1/2" standoff, 6" minimum, field-measured.
- Footings: Diamond Pier DP-50/50 (head + 4 x 50" pins), 3,300 lb bearing each (manufacturer chart — confirm).
  Post load = post spacing x (half the back-span + cantilever) x design load. Auto-upgrade to DP-75/63, else flag.
- Ledger: 2x10, LedgerLOK 2 rows 2" from top/bottom staggered 12" OC (count = ceil(L/12) + 1), membrane behind,
  aluminum Z-flash over, end dams, (4) DTT1Z lateral ties.
- Deck sizes are nominal: "12 x 16" is the maximum over the fascia. The frame is sized DOWN to full boards — field
  boards cut to a whole inch under the nominal less the borders, whole rows under the nominal depth — and the finished
  frame dimensions are stated (Jason Ct: 12 x 16 → 11'-9" x 15'-7 1/2" frame, 11'-0" field boards, 33 rows).

## Decking and fastening
- Composite = hidden clips, 16" OC, one blocking row over the beam. PVC = 12" OC, CONCEALoc, Cortex plugs on
  square-shoulder borders.
- Prime+ / Prime are scalloped — Cortex is not approved. Field is 100% hidden: Camo EdgeClip 3/16" at every joist in
  every gap including the picture-frame joists.
- Face screws (Starborn Cap-Tor xd, color-matched) only at: first row (1 per joist, house edge), borders (2 per bearing
  point @ 16"), fascia (2 at each board end, then alternate top/bottom every 12", pre-drilled), stair treads and risers
  (2 per stringer per board).
- G-Tape 2" on every joist, PF joist, blocking and the ledger; 4" on rims and beams.
- Coconut Husk is a warm golden tan.

## Railing (TimberTech Fulton)
- Panels 6' (69-1/2") / 8' (93-1/2"), 2" steel posts with brackets on the post (END / LINE / CORNER); caps, skirts,
  bracket and panel screws ship with the posts — nothing extra to order. Cut = post-to-post CTC − 2-1/2".
- Sides are named standing in the yard facing the house. A section can be omitted for a concrete step; the END post
  moves to the opening.
- Rail labor LF = deck-edge LF of actual rail, not perimeter.

## Stairs
- Riser ≤ 7-3/4", tread = two deck boards + gap + 3/4" nosing, 2x12 stringers @ 12" OC for composite/PVC treads,
  LSCZ at the rim, closed risers in riser board, landing pad at the bottom, handrail at 4+ risers, stair guard over 30".

## Takeoff = the Decks & Docks order
- Every line as D&D sells it, with NET and ORDER and a one-line reason where they differ.
- Overage is explicit and small: field boards +2, 1 spare border, 1 spare fascia, 1 cull per lumber length, 2 spare
  bolts. No attic stock.
- Ship-to is the job address; account GSEXT1; "confirm stock" on DP-50/50 and HUCQ.

## Pricing
- Sell = (materials + tax + labor) / (1 − GM) + general conditions at cost. Default GM 45% (40% floor).
- General conditions are never marked up in the sell. Financed = check/ACH ÷ 0.93 on the whole price (Eagle's Nest:
  $123,291 → $132,571); the pricebook's `retail_mode` can be set back to `gc_at_cost` for the Jason Ct R5 method.
  Show "check or ACH price" and "total investment (financed)" with the 6.99% / 10-yr monthly.
- General conditions are itemized at cost, no margin (PM time, mobilization, 811/survey, dumpster, toilet, delivery,
  equipment, protection, per diem, clean, contingency — Eagle's Nest $7,200). The Jason Ct method ($4/SF + named site
  extras) applies when no itemized list is given.
- Engineering (stamped set) is outside the price, billed at cost with no markup, a range until quoted.
- 12.5% dealer fee on financed quotes is a GSX rule added manually — open whether the retail line absorbs it.
- Labor: frame $10/SF, decking & fascia $8/SF, rail $20/LF, Diamond Pier $50/pier, demo $2/SF, stairs $150/riser.
  Timber: frame $18/SF, PVC + Cortex $9/SF, cable rail $45/LF, drink rail $8/LF, caissons $400, stone bases $600,
  oil $0.40/SF of timber (all `est.` until the labor sheet says otherwise).
- Sales tax is destination-based (Thornton 8.5%). Never the supplier's or GSX's city.

## Documents
- Takeoff carries no pricing for the crew; the internal pricing section is separate. Client documents: facts only.
- No permit / inspection / AHJ / jurisdiction wording in client documents. The flags in this engine are INTERNAL.
