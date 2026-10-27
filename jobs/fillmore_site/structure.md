# 7303 S Fillmore Cir, Centennial CO 80122: structural review of the deck rebuild

Reviewer notes for the GSX build set and permit set. Written 2026-10-27. This is a pre-engineering review; it is not a stamped design. The calculations are in
`/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad/fillmore/scripts/` (`structure_calc.py`, `final_loads.py`), and the source documents are saved in `.../fillmore/refs/`.

**Plan frame (feet).**
- x runs along the main rear wall, starting at the arm's open (left) side, x = 0.
- y runs out from the main rear wall (y = 0) into the yard. The outer frame face is at y = 10.0. D's wall sits at y = −2.0.
- The arm's door wall is at y ≈ −13.5.

**Parts.**
- Lower part = A + B. Its deck surface is the reference (0), about 9 ft above the yard at the outer edge.
- Upper part = C + D, at +36". Its surface is about 12 ft above the walk-out patio slab.

## 0. Decisions at a glance

1. **The upper beam U1 sits under the outer rim.** Its centerline is at y = 9'-8", 4" inside the rim face (face setback about 1¼").
   - The owner's louvered-roof posts stand on the rail line, so each roof post lands directly on U1 and on an 8x8 column. No load goes through cantilevered joists.
   - The alternative is a second column under each roof post. That column would be about 1.6 ft from the beam-line pier, inside Pin Foundations' 3-ft minimum spacing.
   - Joists then span 9'-6½" (C) and 11'-6½" (D). Beam and pier loads drop because there is no cantilever lever.
   - The columns land on the old brick-column line at the patio edge, so the covered patio stays open.
   - The inset stair notch frames prescriptively.
2. **The lower beam L1 keeps the GSX setback, limited by L/4.** Its centerline is at y = 8'-1", and its face is 1'-8¼" back from the rim face.
   - A face 2'-0" back would give a 2'-2¾" cantilever on a 7'-7½" back-span. That exceeds L/4 and the IRC Table R507.6 limit of 2'-0" at an 8' back-span.
3. **At the level change (x = 29.167) the two parts have their own column lines; there is no shared post.**
   - L1 ends over a column at x = 27.2. U1 starts over the roof-post column at x = 29.8. The two piers are 3.04 ft apart.
   - The only links between the levels are the stair and two small notch-corner posts on B's right rim (§5).
4. **The inset stair stays at the owner's default:** notch x 29.167 → 33.083, y 3'-0" → 7'-0".
   - This position leaves the required 36" landing at C's slider (R311.3.1).
   - It also gives the outer tail joists a 2'-6½" back-span against a 4" cantilever.
5. **Arm A gets no ledger on the house side.** The chimney and the tall-window wall are brick (R507.9.1.1, plus Centennial's handout note on attaching to masonry).
   - The joists run front-to-back. They hang from a ledger on the wood-framed door wall, cross a new 6x10 cross-beam A2 at y = −3'-0", and continue to L1.
6. **There are 12 Diamond Piers.**
   - DP-75 under the two roof posts and at L1 x = 18.5; DP-50/50 everywhere else.
   - The simpler choice is DP-75 everywhere: one ⅝" bolt and one 8x8 base detail.
7. **The 8x8 base needs an engineer (§8.3).** No catalog Simpson 8x8 post base fits a Diamond Pier.
   - ABU88, APB88, APVB88 and CPT88 all need two anchors.
   - The pier head has one cast-in bolt: ½" on the DP-50, ⅝" on the DP-75.

## 1. Basis

| Item | Value | Source |
|---|---|---|
| Code | 2021 IRC as amended by Centennial Ord. 2023-O-06 | Ordinance (verified) |
| Ground snow | 30 psf. Roof snow is 30 psf, non-reducible (Centennial FAQ). | Ord. Table R301.2(1), p. 7 (verified on the rendered page) |
| Wind | 115 mph Vult. Topographic effects NO, special wind region NO, wind-borne debris NO. | Same |
| Seismic / weathering / frost | SDC B, severe weathering, **frost line 36 in.** | Same |
| Deck load | 40 psf live + 10 psf dead (the 30 psf ground snow is lower and is not concurrent) | IRC R507, Table R507.6 note a |
| Soil | Buick loam, 3–5% slopes (Arapahoe soil layer 389/390). USDA OSD lists it as fine-silty with a clay-loam Bt, i.e. CL/ML, so **1,500 psf presumptive.** | IRC Table R401.4.1. Use the Diamond Pier "silts/clays" column. |
| Amendment R109.1.1 | Foundation inspection "after poles or piers are set" must be by a **Colorado PE or architect**, with a stamped report. | Ordinance text (verified). This applies to the piers. |
| Amendment R105.2 | Item 10 (deck permit exemption) is deleted, so every deck needs a permit. | Ordinance |

Material values, NDS 2018 Supplement Table 4D, DF-L No.1, with wet-service factors for timbers:
- 6x10 is a Beams & Stringers size: Fb 1,350, Fv 170, Fc⊥ 625 (×0.67 wet), E 1.6×10⁶.
- 8x8 is a Posts & Timbers size: Fc 1,000 (×0.91 wet), Emin 580,000.
- C_D = 1.0, because occupancy live load governs.
- 6x10 is taken as S4S 5½ × 9½ (S = 82.7 in³, I = 393 in⁴). That is conservative if the stock is rough.

## 2. Recommended framing plan (numbers for the composite engine)

### 2.1 Lower part (A + B), deck surface 0

| Element | Location | Size / connection | Spans |
|---|---|---|---|
| Ledger B | main wall y = 0, x 7.583 → 29.167 | 2x10 PT, LedgerLOK 2 rows staggered 12" OC (23 screws), flashed, **2 × DTT2Z** (within 24" of each end) | — |
| Ledger A (arm door wall) | y ≈ −13'-6", x 0 → 5.833 (wood-framed wall with siding; the slider is here) | 2x10 PT, LedgerLOK (7), flashed, **2 × DTT2Z**. **Not on the brick.** | — |
| Joists | all run in y (perpendicular to the main wall), 2x10 #1 SYP TrueFrame @ 12" OC, joist tape | LUS210Z at the ledgers; H2.5AZ at every joist on A2 and L1; double rims in HUCQ210-2-SDS | B: 7'-11½" span + 1'-11" cantilever. A front: A2 → L1 11'-1" + 1'-11". Arm: door ledger → A2 10'-4½". |
| **Beam L1** | 6x10 DF#1 drop. **CL y = 8'-1"** (face 20¼" back from the rim face). x 0.04 → 29.125. | 2 pieces spliced over x = 9.8 (≈9'-9" and 19'-4": 10' and 20' stock) | Columns at **x = 1.1, 9.8, 18.5, 27.2** (3 spans of 8'-8½"). Overhang 1'-0¾" left, 1'-11" right. |
| **Beam A2** (arm cross-beam) | 6x10 DF#1 drop. **CL y = −3'-0"**, i.e. 10'-6" out from the door wall. x 0.04 → 7.54. | one piece (8' stock) | Columns at **x = 1.0, 4.9** (span 3'-11"). Overhang 2'-7¾" toward the house (engineered, §6). |
| Strip in front of the chimney (x 5.83–7.58, y −5.5 → −3.0) | — | Joists run continuous over A2 and back-cantilever 2'-4" to a doubled 2x10 rim 2" off the chimney face | IRC back-span 11'-1" allows a cantilever of about 2'-9" |
| Columns | 8x8 DF#1 rough, about 6'-9" tall. A2 columns: field-measure. | Caps CCQ68SDS2.5 (W2 = 8" for rough). Base: §8.3. | — |
| Piers | DP-50/50 at L1 1.1, 9.8, 27.2 and A2 1.0, 4.9. **DP-75 at L1 18.5.** | Loads in §9 | — |

### 2.2 Upper part (C + D), +36"

| Element | Location | Size / connection | Spans |
|---|---|---|---|
| Ledger C | y = 0, x 29.167 → 50.167, on the band **above** the walk-out brick veneer | 2x10 PT, LedgerLOK (22), flashed, **2 × DTT2Z** | — |
| Ledger D | y = −2.0, x 50.167 → 63.083 | 2x10 PT, LedgerLOK (14), **2 × DTT2Z** | — |
| Joists | in y, 2x10 #1 SYP @ 12" OC | LUS210Z at the ledgers, H2.5AZ on U1 | C: 9'-6½" + 4" cantilever. D: 11'-6½" + 4". |
| **Beam U1** | 6x10 DF#1 drop. **CL y = 9'-8"** (from C's wall; 11'-8" from D's wall). Outer face about 1¼" inside the rim face. x 29.21 → 63.04. | 2 pieces spliced over x = 46.0 (16'-9½" and 17'-0½": 18'/20' stock) | Columns at **x = 29.80 (roof post), 38.0, 46.0, 49.80 (roof post), 54.1, 62.6**. Spans 8'-2½", 8'-0", 3'-9½", 4'-3½", 8'-6". Overhang 7" left, 5¼" right. |
| Stair notch | x 29.167 → 33.083, y 3'-0" → 7'-0" | Framing in §5 | — |
| Columns | 8x8 DF#1 rough, about 10'-3" tall (pier head flush with the slab plus 1" standoff) | Caps CCQ68SDS2.5 (W2 = 8"). Base: §8.3. | — |
| Piers | **DP-75 at 29.80 and 49.80** (roof posts); DP-50/50 at the others | Loads in §9 | — |

Engine spec values. In the spec, `setback_in` on a drop beam is the beam face measured back from the front rim face, and `posts_x_ft` is in the global frame from A's open side.

```json
"lower": {"framing": {"post_size": "8x8", "post_species": "DF#1", "post_rough": true, "footing_type": "diamond_pier", "footing_model": "DP-50/50",
  "beams": [{"kind": "drop", "size": "6x10", "species": "DF", "setback_in": 20.25, "zones": ["A", "B"], "posts_x_ft": [1.1, 9.8, 18.5, 27.2]},
            {"kind": "drop", "size": "6x10", "species": "DF", "zones": ["A"], "posts_x_ft": [1.0, 4.9],
             "_note": "arm cross-beam A2: CL y = -3.0 ft (126 in out from the arm's door wall); beam x 0.04-7.54"}]}},
"upper": {"framing": {"post_size": "8x8", "post_species": "DF#1", "post_rough": true, "footing_type": "diamond_pier", "footing_model": "DP-50/50",
  "beams": [{"kind": "drop", "size": "6x10", "species": "DF", "setback_in": 1.25, "zones": ["C", "D"], "posts_x_ft": [29.8, 38.0, 46.0, 49.8, 54.1, 62.6]}]},
  "_dp75_at_x": [29.8, 49.8], "_lower_dp75_at_x": [18.5]}
```

Checks on the engine values:
- L1: setback 20.25" gives CL 120 − 20.25 − 2.75 = 97" = 8'-1". The engine's L/4 limit is (120 − 1.5)/5 = 23.7" and the cantilever is 23", so the engine will not move the beam.
- U1: setback 1.25" gives CL 116" from C's wall and 140" from D's wall, the same plan line. The two zones merge into one beam line.

## 3. Joists: 2x10 #1 SYP @ 12" OC (IRC 2021 Table R507.6)

Table R507.6 allows a **16'-2"** span for Southern Pine 2x10 @ 12", based on No. 2 with the wet-service factor; the TrueFrame #1 joists do better. The maximum cantilever is set by the back-span: 8' gives 2'-0", 10' gives 2'-6", 12' gives 3'-0", 14' gives 3'-4". R507.6 also caps the cantilever at ¼ of the joist span.

| Zone / run | Back-span | Cantilever | Limit | Result |
|---|---|---|---|---|
| B: ledger → L1 → rim | 7'-11½" | 1'-11" | 1'-11.9" (L/4 and table) | OK (c/L 0.24) |
| A front: A2 → L1 → rim | 11'-1" | 1'-11" | about 2'-9" | OK |
| A arm: door ledger → A2 | 10'-4½" | — | 16'-2" | OK |
| A strip in front of the chimney: L1 → A2, cantilever back to the chimney | 11'-1" | 2'-4" (back) | about 2'-9" | OK |
| C: ledger → U1 | 9'-6½" | 4" | 2'-4" | OK |
| D: ledger (y −2) → U1 | 11'-6½" | 4" | 2'-10" | OK |
| C notch tails, house side: ledger → inner header | 2'-9" | — | — | OK |
| C notch tails, outer: outer header → U1 | 2'-6½" | 4" | 7½" | OK |

Notes:
- PVC decking (Vintage) on the 12" layout is GSX standard.
- Blocking: one row over every beam, which gives the R507.6.2 lateral restraint at bearings. Add a second row mid back-span (the engine's PVC rule).

## 4. Beams: 6x10 DF#1 (outside IRC R507.5, so they need an engineer)

The 2021 IRC Table R507.5 lists only 1-, 2- and 3-ply 2x beams. A 6x10 is outside the table and needs an NDS calculation and a short PE letter.

- The engine's placeholder (6x10 treated as a (3)2x10 DF row) gives 9'-5" at a 9.9' joist span. That is conservative.
- NDS simple-span allowables (CD 1.0, wet B&S, beam self-weight included):

| Line | w (plf) | Bending | L/360 (live) | L/240 (total) | Shear | **Allowable span** | Longest span used |
|---|---|---|---|---|---|---|---|
| L1 over B | 319 | 15.3' | 15.6' | 16.4' | 38.7' | **15.3'** | 8.7' |
| L1 over A front | 394 | 13.8' | 14.5' | 15.3' | 31.7' | **13.8'** | 8.7' |
| U1 over C | 268 | 16.7' | 16.6' | 17.3' | 45.8' | **16.6'** | 8.2' |
| U1 over D | 318 | 15.3' | 15.6' | 16.4' | 38.9' | **15.3'** | 8.5' |
| A2 | 541 | 11.7' | 13.0' | 13.7' | 23.5' | **11.7'** | 3.9' + 2.6' overhang |

Spliced continuous analysis of the real layouts:
- Peak bending stress: L1 510 psi, U1 317 psi, A2 216 psi, against Fb′ 1,350.
- Deflection ≤ 0.08". Bearing on the 7½" cap is under 100 psi, against Fc⊥′ 419.
- **The 6x10 is far from its limit. Pier capacity, not the beam, sets the post spacing.** A DP-50/50 at 3,300 lb carries roughly 9–10 ft of L1 tributary.

Detailing:
- Splices land over columns (R507.5.2; Centennial handout). Each beam end gets at least 3¾" on the cap.
- Strap each splice (MSTC40 or 2 × CS16, both faces). Simpson's cap uplift values do not apply at splices.
- Beam overhangs past end columns are within span/4 (R507.5 footnote), except A2 (§6).

## 5. Level change at x = 29.167, the inset stair, and the step-face skirt

### 5.1 How the two edges are carried

- **B's right edge.** B's double rim (x 28.917–29.167) hangs in HUCQ210-2-SDS from B's ledger. It bears on L1's end; L1 overhangs its x = 27.2 column by 1'-11".
- **C's left edge.** C's double rim (x 29.167–29.417) hangs from C's ledger and bears on U1's end; U1 overhangs its x = 29.8 roof-post column by 7".
- The two rims touch in plan along x = 29.167. They are 26¾" apart vertically.
- Neither ledger can extend past the line: the house band changes level there, and the C section's lower wall is brick veneer.
- **Why not one shared post.**
  - L1 (y 8'-1") and U1 (y 9'-8") are not on one line, so a stacked column cannot work.
  - A continuous post carrying B's beam on a side hanger is a non-catalog connection. DCA6 does not accept beams bolted to post sides.
  - Two standard columns 3.04 ft apart (at least PFI's 3 ft) cost less and are fully conventional.

### 5.2 Notch framing: C level, 4'-0" wide (y 3'-0" → 7'-0") × 3'-11" deep (x 29.167 → 33.083)

C's joists run in y, so the notch's inner face is parallel to the joists and its two sides cross them.

| Member | Size | Support / hardware |
|---|---|---|
| **Trimmer** at the inner face, x 33.083–33.333 | doubled 2x10 #1 SYP, from the ledger (y 0) to U1 (y 9'-8") | HUCQ210-2-SDS at the ledger; H2.5AZ per ply on U1. Carries both header ends and the stringer tops (about 660 lb in all). M ≈ 1,900 ft-lb → fb ≈ 530 psi, OK. |
| **Inner header**, y 2'-9" → 3'-0" | doubled 2x10, x 29.167 → 33.083 | Hung on the trimmer in HUCQ210-2-SDS. The left end bears on corner post P1. Carries 3 tail joists (LUS210Z) from the ledger. |
| **Outer header**, y 7'-0" → 7'-3" | doubled 2x10, same x run | Hung on the trimmer in HUCQ210-2-SDS. The left end bears on corner post P2. Carries 3 tail joists (LUS210Z), which span 2'-6½" to U1 and cantilever 4". |
| C left-rim pieces | doubled 2x10, y 0 → 2'-9" and y 7'-3" → 10' | The house-side piece hangs from C's ledger and dies into the inner header at P1. The outer piece runs from the outer header over U1 to the front rim. |
| **Corner posts P1 (y ≈ 2'-8") and P2 (y ≈ 7'-4")** | 4x4 or 4x6 PT/DF#1, about 27" tall, on the C side of B's rim, hidden behind the skirt | Each stands on the stair base ledger (next row) and is bolted to B's right rim (2 × ½" through-bolts). Its top bears under the header end (A35Z / LTP4). Loads are about 260 lb (P1) and 170 lb (P2). |
| **Stair base ledger** | doubled PT 2x6 (or one PT 4x6) on the outer (C-side) face of B's right rim, y 2'-6" → 7'-6", top flush with the rim | ½" through-bolts @ 12" staggered. It carries the 5 stringer heels (A35Z each) and P1/P2. |
| Stringers | 5 × 2x12 #1 SYP cut stringers, about 11½" OC (TimberTech treads need ≤ 12" OC). Throat 5.1" at 7.2/11.75. Horizontal run 3'-11", within DCA6's 6'-0" cut-stringer limit. | Top: Simpson LSCZ to the trimmer face. Bottom: heels on the stair base ledger. The bottom riser board is flush with the step face, from B's deck surface up to tread 4. |

B's right rim then works as a small flush beam from B's ledger to L1:
- It carries the stair foot (about 390 lb over y 3–7) plus P1 and P2.
- M ≈ 1,180 ft-lb → fb ≈ 330 psi on the 2-ply 2x10. OK.
- The reaction at its ledger hanger is about 440 lb, against roughly 250–320 lb for an ordinary joist. That is joist-scale, not the beam load R507.9.1.1 prohibits.
- The PE should confirm.

**Location of the stair: keep y 3'-0" → 7'-0".**
- C's slider is at the left end of C's wall. The 3'-0" strip is exactly the 36" landing R311.3.1 requires; shift the notch to 3'-3" → 7'-3" if the door is in front of it and more margin is wanted.
- A notch at the outer corner (like the existing stair) is ruled out: it would sit on the roof's left post and on U1's x = 29.8 column.
- A notch against the house is ruled out: it would sit in front of the door.

### 5.3 Step-face skirt: 36" from B's surface up to C's surface

- Vertical fascia boards go on **PT 2x4 nailers @ 16" OC**.
- Each nailer screws to the outer face of **C's left rim** at the top and **bears on top of B's right double rim** at the bottom (toe-screwed plus an A35Z), with a mid-height PT 2x4 blocking row.
- The skirt face lands at about x 28.98. B's last board ends against it over B's rim and picture-frame joist.
- Leave a ¼" gap above B's decking for drainage.
- At the notch, the corner posts P1 and P2 back the skirt's ends. The notch side faces (headers above the treads) get fascia.
- At U1's left end (y ≈ 9.4–9.9), screw the skirt to the beam's end face.
- The skirt is non-structural and bears only on B's rim.

### 5.4 Stair code items

| Item | Value | Code |
|---|---|---|
| Risers / treads | 5 risers @ 7.2"; 4 treads @ about 11¾" (run 47") | R311.7.5.1 (max 7¾"), R311.7.5.2 (min 10") |
| Width | 48" clear between the header faces | R311.7.1 (min 36") |
| Handrail | Required (4 or more risers). One side minimum, 34–38" above the nosings, graspable. A drink cap is **not** graspable. | R311.7.8 |
| Guards | Along both notch sides on C's deck, 36" minimum: C's surface is 36" above B within 36" horizontally. Also along C's step face at y 0–3 and 7–10. | R312.1.1, R312.1.2 |
| Landings | Top is C's deck; bottom is B's deck (36" or more in the direction of travel) | R311.7.6 |
| Light | Artificial light at the top landing (Centennial handout also requires it) | R303.8 |
| Headroom | Open to the sky / louvered roof | R311.7.2 |

## 6. Arm A framing (x 0–7.583, y −13.5 → 10)

The photos (u20, z21) show what each wall is:
- The **door wall is wood-framed with siding**. It can take a ledger; verify the band below the slider threshold.
- The **chimney (x 5.833, y −10.5 → −5.5) and the tall-window wall (x 7.583, y −5.5 → 0) are full-height brick**. No ledger is allowed on them (R507.9.1.1).

The framing:
1. **Joists run in y**, front to back, the same direction as B; the boards run in x as they do now. They bear on:
   - the **door-wall ledger** (y −13'-6");
   - **A2** (6x10 DF#1 drop, CL y −3'-0", columns at x 1.0 and 4.9);
   - **L1** (y 8'-1"), with the 1'-11" front cantilever.
   - Spans are 10'-4½" and 11'-1". Splice the joists over A2.
2. **A2's house-side column sits at x 4.9**, 2'-8" (32") from the brick face, so the Diamond Pier pins clear the house foundation.
   - PFI Table 2 needs 21" of horizontal pin reach for 50" pins set at 45°, plus the projection of the house footing.
   - The beam then overhangs 2'-7¾" toward the house. That exceeds the span/4 guideline, so it is an engineered condition.
   - Checks: fb 216 psi. Column loads are 1,570 and 2,580 lb. With live load on the overhang only, the far column sees about 25 lb of uplift, which the cap and base cover.
   - If the PE prefers a column closer to the wall (x ≈ 6.25 meets span/4), that column is within 5 ft of the house foundation. DCA6 requires it to bear at the house-footing elevation, so it needs an engineered deep footing, not a Diamond Pier.
3. **Strip in front of the chimney (x 5.83–7.58, y −5.5 → −3.0):**
   - The joists run continuous over A2 and cantilever back 2'-4" to a doubled 2x10 rim held 2" off the chimney face.
   - That is within the table cantilever for an 11'-1" back-span (about 2'-9"). Nothing touches the brick.
   - A doubled 2x10 trimmer at x ≈ 5.70, from the door ledger to A2, carries the board ends at the chimney's side face.
4. **Possible nook behind the chimney (x 5.83–7.58, y −12.8 → −10.5):**
   - The photos suggest the chimney's brick returns to the door wall, in which case there is no nook.
   - If a nook exists, it cannot hang on brick. Frame it from a ledger on the wood-framed door wall plus a header detailed by the engineer, or leave it undecked and guarded.
5. **Lateral:** 2 × DTT2Z at the door ledger, in addition to B's two, because the arm is a 23-ft wing.

## 7. Louvered roof (Suncoast, about 20' × 10'): post loads and load path

### 7.1 Post loads per front post

Each front post takes about 50 sf (half the roof goes to the house). Values are ASD.

| Load | Per post |
|---|---|
| Dead: 6 psf × 50 sf | 300 lb |
| Snow: 30 psf (Centennial non-reducible roof snow; ASCE 7-16 flat-roof p_f = 0.7·1.0·1.2·1.0·30 = 25.2 psf) | 1,500 lb |
| Sliding snow off the shingled house roof (ASCE 7-16 §7.9; slope over 2:12; 0.4·p_f·W over 15 ft, W ≈ 14 ft assumed, reduced for the 10-ft roof) ≈ 11 psf | about 560 lb |
| **Gravity design (D + S)** | **2,400 lb down** |
| Wind uplift, net 0.6D + 0.6W. Vult 115 mph, Kzt 1.0 (city: no topographic effect), h ≈ 21 ft, qh = 20–26 psf (strength) for Exposure B/C. | **550–760 lb**, using GCp_net ≈ −1.2 over the whole roof |
| Wind uplift at corner-zone coefficients (GCp ≈ −2.0) | **1,030–1,390 lb**, so design the hold-down chain for **1,400 lb** |
| Lateral | Suncoast's engineering must state base shear and moment. The deck provides **pinned** bases only. |

Suncoast's stamped engineering governs the roof itself. The deck design must then accept its stated reactions:
- The deck has room for a roof reaction up to about **2,900 lb down** per post (DP-75 limit, below) and **1,400 lb up**.

### 7.2 Choice: move U1 out under the rim, with a column directly under each roof post

**Rejected option A: a separate column plus blocking under each roof post, with U1 left at 8'-1".**
- The extra column would be 1.6 ft from the U1 pier at the same x. That breaks PFI's 3-ft minimum spacing (13% capacity loss per close pier, and the pins clash).
- Without that column, the roof post would load the joists' 1'-7" cantilever with 2,400 lb down and 1,400 lb up. The joists and the ledger hangers cannot take that.

**Chosen option B, checked:**
- **Columns:**
  - x 29.80: 1,260 lb deck + 2,400 lb roof = **3,660 lb** → DP-75 (87% of 4,200).
  - x 49.80: 1,170 + 2,400 = **3,570 lb** → DP-75 (85%).
  - Neighbouring spans are kept short (3'-9½" and 4'-3½" at 49.8) to hold this.
- **Beam:** the roof post sits on the column centerline, so there is no added bending. Cap bearing is about 89 psi.
- **8x8 column:** about 10'-3" tall, P_allow ≈ 44,000 lb (S4S), against 3,660 lb.
- **Uplift at the pier:** about 1,400 − 0.6 × (≈450 lb deck dead load and self-weight) ≈ 1,130 lb. The DP-75 uplift rating is 1,400–1,600 lb (PFI chart, field-test values). ESR-1895 §5.6 does not evaluate uplift, so the PE accepts this.

### 7.3 Post base attachment through the decking

Roof posts sit at **x 29.80 and 49.80, y 9'-8"**: 20'-0" on center, 4" inside the rim face and about 1½" inboard of the IRX post line. That keeps an 8"–9" base plate on the deck. The IRX rail sections bracket into the roof posts.

1. **Block solid** under the base plate. Fit 2-ply 2x10 PT blocks between the joists or rims on both sides of the post, sitting directly on U1 over the column.
   - Fasten the blocks to the joists with (4) ¼"×3½" SDS per end.
   - Tie each block and the flanking joists to U1 with H2.5AZ.
   - Add a CS16 strap (or MSTC40) from the block-out down U1's outer face to the 8x8, so the uplift path is continuous.
2. **Bearing pad.** Cut the PVC boards back around the plate with about ⅛" gap. Set a solid PT pad flush with the decking on the blocking so the plate bears on wood, not on PVC.
3. **Fasteners:** (4) ½" HDG A307 through-bolts with 2"×2"×3/16" plate washers under the blocking, or Suncoast's specified anchors if larger.
   - Four bolts carry 1,400 lb of uplift easily.
   - **Do not use the deck as a fixed (moment) base.** The roof's lateral system must be the house attachment, its own frame, or knee braces. If Suncoast insists on fixed bases, the PE must design that connection.
4. **Load path.** Uplift goes: blocking → H2.5AZ / CS16 → U1 → CCQ68 cap (6,785 lb uplift) → 8x8 → base (§8.3, must take 1,400 lb) → DP-75 ⅝" bolt → pier.
5. **House side.** The roof's back edge (about 205 plf down and 75 plf up) must go into the wall framing (top plates, header or band), not the soffit framing. Sliding snow from the house roof lands on the back edge. The PE or Suncoast checks this.

## 8. Columns (8x8 DF#1 rough)

### 8.1 Height and capacity

| Line | Approx. length (top of pier + base to underside of beam) | NDS P_allow (S4S / rough) | Max load |
|---|---|---|---|
| L1 (lower; deck 9' above grade; head mid-buried, about 6" proud, + 1" base) | about 6'-9" | 48,600 / 55,700 lb | 3,280 lb |
| A2 (arm) | field-measure, likely 6–8' | over 48,000 lb | 2,580 lb |
| U1 (upper, on the slab; head top flush with the slab + 1") | about 10'-3" | 44,100 / 51,400 lb | 3,660 lb |

- IRC Table R507.4 (2021) allows an 8x8 of DF or SP up to **14'-0"** at every tributary area to 160 sf (40 psf live; measured from the underside of the beam to the top of the pier). Our tributary areas are 40–55 sf. OK.
- The engine's `timber_post_capacity` uses E instead of Emin, Fc 1,200 (the Dense No.1 value) and CD 1.15, so it overstates capacity by about 65%. This does not govern here; see §14.

### 8.2 Bracing

- The IRC does not require knee braces on a ledger-attached deck that has the R507.9.2 lateral connection. The deck diaphragm and the ties brace the column tops.
- Simpson states that post bases do not resist rotation and that columns must be top-supported. These are.
- **Recommendation:**
  - Add knee braces **only at the end columns** of each line: L1 at x 1.1 and 27.2; U1 at x 29.8 (brace toward +x) and 62.6.
  - Use 4x6 DF#1 at 45° with legs about 30–36", fastened with ½" through-bolts or 3/8" structural screws kept clear of the joint.
  - Put the braces in the beam plane, and perpendicular to the beam where a corner joist or block is available.
  - **Do not brace interior columns.** AWC's DCA6 FAQ says knee braces stiffen the frame and overload interior posts.
  - They are worth adding here because the columns are 7–10 ft on pinned pier bases, the deck is 63 ft long, and the upper level carries a roof. The PE makes the final call.

### 8.3 Caps and bases (Simpson)

**Caps:**
- Use **CCQ68SDS2.5** at every column: W1 5½" (6x beam), W2 7½". It is rated 6,785 lb uplift and 37,815 lb down (DF/SP).
- Every beam overhangs its end column, so no ECCQ caps are needed. ECCQ68SDS2.5 (3,785 / 25,780 lb) applies only if a beam ends flush on a column.
- For **rough 8x8 (8" actual)**, order W2 = 8". If the 6x10 is rough, order W1 = 6". Simpson's catalog says: "For rough-cut lumber sizes, provide dimensions."

**Bases: a problem to settle before ordering.**
- Each Diamond Pier head has **one** cast-in galvanized bolt at its center: ½" on the DP-50, ⅝" on the DP-75 (ESR-1895 §3.2.2).
- Every catalog Simpson 8x8 base needs **two** anchors:
  - ABU88Z / ABU88RZ: (2) ⅝", rated 4,120 / 4,045 lb uplift.
  - APB88 and APVB88: (2) ⅝".
  - CPT88Z: (2) ½".
- Pin Foundations markets the pier for 4x4 and 6x6 posts.
- Options, for the PE or PFI to choose:
  1. A bracket approved by Pin Foundations, if they offer one for 8x8.
  2. An **engineer-detailed hot-dip-galvanized steel standoff base**: a ⅜" plate with a ⅝" center hole for the **DP-75** bolt, a 1" standoff, and side straps or a knife plate through-bolted into the 8x8.
  3. Turn a 5½" tenon (6" if rough) on the bottom of the 8x8 and seat it in an **ABU66Z / ABU66RZ** (one ⅝" anchor; 1,905–2,475 lb uplift) on a DP-75. The tenon still has about 27 kips of bearing capacity.
- Any of these must carry the roof uplift (1,400 lb) at x 29.8 and 49.8.
- **Do not hang an ABU88 on one bolt.**

**Durability:**
- Keep the 1" standoff, with the pier head 6" or more above soil (or flush with the slab plus the 1" standoff) so no untreated DF touches concrete or soil (ESR-1895 §5.2; IRC R317).
- Seal every cut end.

## 9. Footings: Diamond Piers

### 9.1 Pier capacities and loads

Capacities for 1,500 psf silts/clays are from the PFI load chart (DOC0008/01.2018) and ICC-ES ESR-1895 (reissued Dec 2025):

| Model | Bearing | Frost zone | Uplift | Lateral |
|---|---|---|---|---|
| DP-50/36 | 2,700 lb | 24" (**not enough for the 36" frost line**) | 600 | 600 |
| DP-50/50 | 3,300 lb chart (ESR: 2.4 sf × 1,500 = 3,600) | 48" | 1,200 | 600 |
| DP-75/50 | 3,750 lb chart* (ESR: 2.8 sf → 4,200) | 48" | 1,400* | 600 |
| DP-75/63 | 4,200 lb chart | 60" | 1,600 | 600 |

*Interpolated by PFI. Bearing is at a factor of safety of 2. ESR-1895 does **not** evaluate uplift or lateral capacity (§5.6), so the PE accepts those chart values. Frost protection is approved by the code official per R507.3.3 using PFI's frost-zone ratings (ESR §5.3).

Design load per column is the larger of the tributary load and the spliced-continuous reaction:

| Line | x | Design load | Pier | Note |
|---|---|---|---|---|
| L1 | 1.1 | 2,130 lb | DP-50/50 | about 1.5 ft from the old arm-corner brick column |
| L1 | 9.8 | 2,930 lb | DP-50/50 (89%) | splice column |
| L1 | 18.5 | 3,280 lb | **DP-75** (78%) | 100% of a DP-50/50 |
| L1 | 27.2 | 2,250 lb | DP-50/50 | in the bed about 1.5–2 ft from the slab's buried left edge; set pins at 45° |
| A2 | 1.0 | 1,570 lb | DP-50/50 | watch the side-yard fence posts (pin reach up to 29") |
| A2 | 4.9 | 2,580 lb | DP-50/50 | 32" from the brick; see §6 |
| U1 | 29.80 | 3,660 lb | **DP-75** (87%) | roof post; on the slab near its left and outer edges |
| U1 | 38.0 | 2,700 lb | DP-50/50 | on the slab |
| U1 | 46.0 | 1,580 lb | DP-50/50 | splice column; 3.8 ft from 49.8 |
| U1 | 49.80 | 3,570 lb | **DP-75** (85%) | roof post |
| U1 | 54.1 | 2,770 lb | DP-50/50 | on the slab |
| U1 | 62.6 | 1,490 lb | DP-50/50 | on the slab |

### 9.2 Spacing, frost and soil

- **Spacing:** every pair is at least 3 ft center to center. The tightest is L1 27.2 to U1 29.8 at 3.04 ft. If the field moves either pier, re-check; closer piers lose 13% each.
- **Pin setback from obstacles** (PFI Table 2): 50" pins need 29" if a pin points straight at the obstacle, or 21" at 45°; 63" pins need 38" / 27". Add a 6" safety zone for utilities. Call 811 before driving.
- **Soil cautions:** PFI excludes highly expansive soil, ponding soil, and loose backfill next to foundations.
  - Keep downspouts and irrigation off the bed piers.
  - If the Bt clay proves expansive, a soils check is required (Centennial R401.2 amendment).
- **Frost:** DP-50/50 and DP-75 both cover the 36" frost line.

### 9.3 Piers on the existing patio slab (all six U1 columns)

1. A post may **never bear on the 4" slab-on-grade**. The slab is not a footing.
2. Saw-cut a 24" × 24" opening (or core 20" or more) through the slab at each column.
3. Set the pier in native soil:
   - head top flush with the slab, which is allowed if the top stays accessible;
   - drive the pins;
   - keep the slab isolated from the head with ½" expansion-joint material. PFI: slabs "MUST NOT interfere … expansion joints may be used."
4. Probe for a **thickened slab edge** about 1 ft outboard of the U1 line. Orient the pins diagonally, or cut the thickened edge locally, so no pin strikes it.
5. Moving the columns off the slab is not practical. The slab runs about 1–1.5 ft past the column line, so the beam would have to sit outside the deck.

### 9.4 Old brick-column footings

- The photos show about five brick columns under C+D at roughly 8-ft centers (estimated x ≈ 30, 38, 46, 54, 62, ±1.5 ft) and about four along B plus the arm corner (estimated x ≈ 0.5, 9, 18, 26.5), all at y ≈ 9.3–9.5. **Field-measure them.**
- The U1 layout above deliberately falls on that rhythm: 29.8, 38.0, 46.0, 54.1 and 62.6, plus the roof column at 49.8.
- Wherever a new pier is within 3 ft of an old footing, the old footing must be **broken out below the pin zone**. Alternatively, the PE may accept a sound frost-depth old footing under the new 8x8 (ABU88RZ on two ⅝" epoxy anchors). That also solves §8.3, but it departs from "Diamond Piers everywhere".
- Remove the brick columns completely. Do not let the new deck rest on them.

## 10. Ledgers and lateral ties

- **Ledger type:** 2x10 PT. Use LedgerLOK (FastenMaster, ICC-ES ESR-1078) at the GSX pattern: 2 rows 2" from top and bottom, staggered, one screw per 12".
  - For comparison, IRC Table R507.9.1.3(1) spaces ½" lags at 23" (8' joist span), 18" (10') and 15" (12'). Confirm against ESR-1078's own table at plan review.
- **Never on brick.** R507.9.1.1: "shall not be supported on stone or masonry veneer". Centennial's handout asks for a fastener detail whenever a deck attaches to brick, and this design attaches to none.
  - **B ledger:** goes on the main-floor band through the siding.
  - **C ledger:** goes on the band **above** the walk-out brick veneer (u16 shows an orange band above the brick). Verify the veneer stops below it.
  - **Arm ledger:** goes on the door wall; verify the band at the slider.
  - Use membrane, Z-flashing and end dams throughout.
- **Lateral connection (R507.9.2):** 2 devices of 1,500 lb within 24" of each end, or 4 devices of 750 lb, per deck.
  - Specify **8 × DTT2Z**: 2 on B, 2 on the arm door ledger, 2 on C (one near x 29.2–31.2), and 2 on D (one near x 61–63).
  - Each tie needs **interior access** to a house floor joist or blocking, so expect to open the walk-out ceilings.
- **Hangers:** LUS210Z on single joists; HUCQ210-2-SDS on double rims and trimmers. No beam or girder hangs on any ledger (R507.9.1.1). The largest ledger reaction is about 440 lb, at B's right rim.

## 11. Optional stairs down to the yard (R311.7)

| From | Rise (field-measure at the foot; the yard falls away) | Risers / treads | Run at 11" | Notes |
|---|---|---|---|---|
| Lower deck (B edge or arm side) | about 108" | 15 @ 7.20" / 14, or 14 @ 7.71" / 13 | 12'-10" / 11'-11" | One flight is legal (max 151", R311.7.3), but a cut 2x12 needs support every 6'-0" (DCA6). Use a mid-run 6x10 or (2)2x10 support on 2 piers, or two flights with a 4'×4' landing on piers (R311.7.6). |
| Upper deck (D edge) | about 144" | 20 @ 7.20" / 19, or 19 @ 7.58" / 18 | 17'-5" / 16'-6" | One flight is legal but long. Use about 10 + 10 risers with a landing at least 36" deep on 4 piers. |

For any yard stair:
- Width 36" or more; 4 stringers at 36" wide, 5 at 42–48" (12" OC for PVC treads).
- Closed risers. Treads under 11" need a ¾–1¼" nosing (R311.7.5.3).
- Handrail on at least one side, graspable, 34–38".
- Guards on open sides more than 30" up: 34" minimum above the nosings, 4⅜" sphere rule.
- Headroom 6'-8".
- Bottom landing 36" deep by the stair width, on a pad or pavers (confirm with Centennial).
- Light at the top landing.

## 12. Guards, IRX, and the drink cap

- **Where:** guards are required wherever the walking surface is more than 30" above the grade or floor below within 36" (R312.1.1). That covers all outer edges, the arm's open side (x 0), C's step face (36"), the notch sides, and stair sides.
- **Height:** 36" minimum on decks, measured to the **top of the drink cap**; 34" on stairs above the nosing line (R312.1.2).
- **Openings:** 4" sphere; 4⅜" on stairs; 6" triangle at the stair's riser, tread and bottom rail (R312.1.3).
- **Loads:** 200 lb concentrated at the top in any direction, and 50 lb on 1 sf of infill, not concurrent (Table R301.5). The 200 lb applies at the cap, which is about 1½" higher than the bare rail, so the post base moment rises about 4%.
- **Posts:** IRX 3" aluminum posts on GSX doubled 2x10 PT blocking between joists, with **(4) ⅜" × 6" construction lags** per TimberTech's IRX instructions. Pre-drill the PVC and shim under the base.
- **Drink cap:**
  - Use only TimberTech's **IRX drink-rail hardware kit**. TimberTech says the system is tested as a whole and should not be mixed with other systems or fasteners.
  - Hold the post spacing to the kit's limit.
  - Gap the PVC cap's butt joints for PVC movement.
  - Leave the cap off the stair sections, which need a graspable handrail instead.
- **Cable infill:** tension per TimberTech so the 4" sphere rule holds under load.
- **Roof posts as rail posts:** attach IRX rail ends to the Suncoast posts with IRX brackets, with fasteners approved by both manufacturers. Otherwise, set an IRX end post next to each roof post.

## 13. Items for the engineer and field checks

1. **6x10 DF#1 beams (not in R507.5).** Needs an NDS calculation and a PE letter, including A2's 2'-7¾" overhang (§4, §6).
2. **8x8 base on a Diamond Pier.** There is no catalog part; the PE or PFI must detail it (§8.3). The PE must also accept the PFI uplift and lateral values, which ESR-1895 §5.6 does not evaluate.
3. **Louvered roof.**
   - Get Suncoast's stamped design for 30 psf roof snow plus sliding snow, 115 mph, and the house-side attachment.
   - Get its post reactions. The deck limits are about 2,900 lb down and 1,400 lb up per post. Bases are pinned.
   - The PE signs off the post-base and blocking detail (§7.3).
4. **Arm.** No ledger on the brick. A2's house-side pier is 32" from the brick: verify the foundation depth there, because a deep basement wall triggers the DCA6 5-ft rule. Frame any nook behind the chimney per §6.
5. **Level change.** The notch corner posts and stair base ledger load B's right rim, with about 440 lb at its ledger hanger. The PE confirms this non-table detail.
6. **Slab and old footings.** Saw-cut and isolate the slab, check for a thickened edge, and locate and break out old brick-column footings within 3 ft of a new pier (§9).
7. **Untreated DF#1 timbers outdoors.**
   - R507.2.1 calls for preservative-treated or "approved naturally durable" wood, and Douglas fir is neither.
   - Get the building official's acceptance in writing at plan review. The usual basis is the R317.1 item 7 dry-climate exception plus standoff bases.
   - Otherwise, specify treated DF timbers.
8. **Centennial R109.1.1.** The pier inspection must be done by a Colorado PE or architect with a stamped report. Budget for it.
9. **Ledger bands and interior access.** Verify B's band, C's band above the veneer, and the arm door band. The DTT2Z ties need access from inside.
10. **Geometry to measure:**
    - deck height at each column;
    - grade under the arm;
    - old column centers;
    - slab edges;
    - where C's slider sits relative to the notch;
    - the nook behind the chimney;
    - the house roof slope and run above C (it sets the sliding snow).

## 14. Engine notes for the coordinator

| Where | Finding | Suggested fix |
|---|---|---|
| `catalog.FOOTING_CAPACITY_LB["DP-75/63"] = 6000` | **Unconservative** for 1,500 psf soils. 6,400 applies only in 2,000 psf sands and gravels; silts/clays get 4,200. | Use 4,200 (`DP-75/63`, or `DP-75/50` per ESR 2025). Keep DP-50/50 at 3,300. |
| `engineering.TIMBER_DESIGN["DF#1"]["pt"]["Fc"] = 1200` | 1,200 psi is the Dense No.1 value. No.1 Posts & Timbers is **1,000 psi**. | Set Fc 1000 and add Emin 580,000. |
| `engineering.timber_post_capacity_lb` | Uses E in the Euler term, not Emin, and ignores the 0.91 wet factor. | Use Emin with CM. Capacity drops about 40%; it still passes here. |
| `engineering.CD_SNOW = 1.15` applied to timber decks | With 40 psf live load governing, C_D = 1.0. | Use 1.0 unless snow governs. |
| `catalog.TIMBER_BASE["8x8"]` = ABU88Z / APB88 | These need (2) ⅝" anchors and **cannot mount on a Diamond Pier**. | Add a flag for footing_type diamond_pier + 8x8 posts. |
| `catalog.LUMBER["6x10"] = (5.5, 9.25)` | Timbers dress to 9½" deep. | Use 9.5 (minor; the current value is conservative). |
| `layout.DP_STANDOFF = 4.5` | PFI sets the head to its midpoint, about 5½–6" proud, and the base adds 1". | Use about 7" in soil and about 1" when the head is flush with a slab. |

## 15. Summary

**Beams and joists.**
- The lower part keeps a GSX drop beam, **L1 (6x10 DF#1) at y 8'-1"**, on four 8x8 columns at **x 1.1, 9.8, 18.5, 27.2**.
- The arm gets its own cross-beam, **A2 at y −3'-0"**, on columns at **x 1.0 and 4.9**. The arm's joists run front-to-back from a ledger on its wood-framed door wall. Nothing hangs on the brick chimney or the brick wall.
- The upper part's single beam, **U1, moves out under the rim (y 9'-8")** so the two louvered-roof posts stand directly on columns. U1 has six columns at **x 29.8 (roof post), 38.0, 46.0, 49.8 (roof post), 54.1, 62.6**.
- All joists are 2x10 SYP @ 12" and span at most 11'-6½" (limit 16'-2"). Cantilevers are within L/4 and IRC Table R507.6.
- The 6x10 DF#1 beams run at about 25–40% of their NDS capacity (spans 3.8–8.7 ft against allowables of 11.7–16.6 ft). Pier capacity, not the beam, sets post spacing.

**Level change.** The two levels meet on two separate column lines 3 ft apart. The inset stair is in a 4'-0" × 3'-11" notch at y 3'–7': a doubled trimmer, doubled headers, two small corner posts, and a stair base ledger on B's rim. The step-face skirt hangs on PT nailers that bear on B's rim.

**Piers.** There are 12 Diamond Piers, sized for 1,500 psf soil:
- DP-75 under both roof posts (about 3,600 lb each) and at L1 x 18.5 (3,280 lb).
- DP-50/50 at the rest (≤ 2,930 lb).
- The six U1 piers go through saw-cut, isolated openings in the patio slab, on the old brick-column line.

**Must be engineered or confirmed:**
- the 6x10 beams and A2's overhang;
- a non-catalog 8x8-to-Diamond-Pier base, since every Simpson 8x8 base needs two anchors;
- Suncoast's roof reactions and its pinned-base post detail (deck limits about 2,900 lb down and 1,400 lb up per post);
- the untreated-DF approval;
- Centennial's PE pier inspection.

**Code numbers that stand as is:** stair 5 × 7.2" risers / 4 × 11¾" treads with a graspable handrail; IRX guards 36" to the top of the drink cap, posts on doubled blocking with 3/8"×6" lags; 8 × DTT2Z ties.

## Sources

- Centennial Ord. 2023-O-06 (Table R301.2(1); R109.1.1; R105.2), saved at `.../prentice/downloads/centennial_ord_2023-O-06.pdf`. Centennial "Residential Uncovered Decks & Porches" handout, at `.../prentice/downloads/centennial_deck_handout.pdf`.
- 2021 IRC deck tables R507.3.1, R507.4, R507.5 and R507.6, as reproduced in the WA SBCC / WABO comment (Chappell, 2019): https://sbcc.wa.gov/sites/default/files/2020-01/Chappell_IRC%20Deck%20Table_092419.pdf. Saved at `.../fillmore/refs/chappell_irc_deck.pdf`.
- ICC-ES ESR-1895, Diamond Pier DP-50 & DP-75 (reissued Dec 2025): https://www.icc-es.org/wp-content/uploads/report-directory/ESR-1895.pdf. Saved at `.../fillmore/refs/ESR-1895.pdf`.
- Pin Foundations Residential Diamond Pier Load Chart, DOC0008/01.2018: https://res.cloudinary.com/amerhart/image/upload/Documents/Product/Residential%20Diamond%20Pier%20Load%20Chart. Installation Manual, DOC0007/02.2018: https://res.cloudinary.com/amerhart/image/upload/Documents/Product/Diamond%20Pier%202018%20(Installation).pdf. Both saved in `.../fillmore/refs/`.
- Simpson Strong-Tie catalog C-C-2026, CCQ/ECCQ table: https://www.buildsite.com/pdf/simpsonstrongtie/CCQECCQ-Column-Caps-Product-Data-2970102.pdf. ABA/ABU/ABW table: https://www.buildsite.com/pdf/simpsonstrongtie/ABAABUABW-Adjustable-and-Standoff-Post-Bases-Product-Data-2970078.pdf. CPTZ table: https://www.fastenersplus.com/cdn/shop/files/CPTZ_Concealed_Post_Tie.pdf. APB88/APVB88 anchors per retailer listings (2 × ⅝").
- AWC FAQ on knee brace locations: https://awc.org/faq/what-are-the-requirements-for-locations-of-diagonal-knee-braces. DCA6-style 5-ft footing rule as reproduced by Everett WA: https://lfportal.everettwa.gov/WebLink/0/doc/1003584/Page31.aspx.
- TimberTech Impression Rail Express installation guides: https://www.timbertech.com/wp-content/uploads/2020/03/impression-rail-express-installation-guide.pdf and https://www.timbertech.com/wp-content/uploads/2020/03/impression-rail-express-open-mid-rail-installation-guide.pdf (4 × ⅜"×6" lags into blocking).
- USDA Official Series Description, BUICK: https://soilseries.sc.egov.usda.gov/OSD_Docs/B/BUICK.html.
- NDS 2018 Supplement Table 4D (DF-L timber values) and ASCE 7-16 Ch. 7 and Ch. 26/30 are cited from the standards. Suncoast published no ratings online, so its stamped engineering is required.
