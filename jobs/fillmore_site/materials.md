# 7303 S Fillmore Cir, Centennial CO 80122 — materials: verification and unit prices

Prepared 27 Oct 2026 (research only; no repo files were edited). Owner decisions are taken as given. The coordinator's owner changes of 27 Oct (lighting, inset-stair step-face skirt, louvered roof) are in section 6.

**Flags:**
- **V** = verified. That means a manufacturer site or published document, a Decks & Docks (D&D) quote or order, or the engine pricebook where the pricebook itself cites D&D.
- **E** = estimate: scaled, interpolated, retail or list benchmark, or a pricebook "est." line.
- **U** = unverified or open.

D&D documents found in Gmail (quotes and orders from Henry Frederick's branch) count as D&D quotes and are cited by number. Two of them (959545, 959790) are on the **CASH50** account, not GSEXT1, and they are marked that way.

> Read first: **every D&D quote here expired the day it was issued.** Quote 979610 was dated 09/11/2026 and expired 09/11/2026. Re-quote with Henry before you order.

---

## 0. Sources (cited by tag)

| Tag | Document | Date | Location |
|---|---|---|---|
| S1 | D&D Quote **979610**, GSEXT1, taken by Henry Frederick (Parkview, 11215 W Center Ave) | 09/11/2026 | Drive "Quote 979610.pdf" (id 1zBo-VNSw5koRhJfVRmrnnjHTLnwBP6hU); same PDF at repo `jobs/parkview_photos/quote_979610.pdf` |
| S2 | D&D Sales Order **6622045**, GSEXT1 ("Hoegar") | order 07/09/2026; first issue 15 Jul (has the drink-rail kit), revised 16 Jul | Gmail, from hfrederick@decks-docks.com (msgs 19f678f0e9222b50 and 19f6b5a32d680d7a) |
| S3 | D&D Sales Order **6645370**, GSEXT1 (1044 E Fremont Cir N, Centennial) | order 07/15/2026 | Gmail msg 19fa970e99d89569 |
| S4 | Henry Frederick "Pricing" e-mails plus D&D Quote **959545** (CASH50) | 7–8 Jul 2026 | Gmail thread 19f3df45d4742aad |
| S5 | D&D Quote **959790** (CASH50, frame takeoff) | 07/08/2026 | same thread |
| S6 | D&D Quotes 968400 / 968434 / 968477, GSEXT1 (Olde Mill Types 1–3) | 08/05/2026 | Drive "D&D Type 1/2/3 deck.pdf" |
| S7 | "Pricing Sheet To Fit GS" | modified 14 Jul 2026 | Drive 1gY0Vadbtg-nYRsgbvaHov5K7fptmuazmTJhHqn18FYo |
| S8 | "GSX_Subcontractor_Labor_Rates" (Base and Add-On tabs) | modified 14 Jul 2026 | Drive 1sPDRPFk0dJDuP71G2pwFTAmeuS8hy8YlvcB1m1l0STg |
| S9 | GSX "Build SOP's" | 2026 | Drive 1iheHxp0G3bpzk0fEQK6vkcmkMPmTPi11ab-k5btl8xY |
| S10 | **TimberTech 2026 Product Guide** (decking, fasteners, IRX, lighting SKUs) | PDF built 7 Nov 2025 | assets.timbertech.com/content/dam/wp-content/Timbertech-Product-Guide-2026-web.pdf |
| S11 | TimberTech Vintage pages: shop.timbertech.com/products/decking/azek-vintage and timbertech.com/product/azek-vintage-collection/ | fetched 27 Oct 2026 | web |
| S12 | TimberTech "Cortex for Advanced PVC" page (shop.timbertech.com/product/cortex-fastener-pack-azek/) | fetched 27 Oct 2026 | web |
| S13 | TimberTech **IRX Drink Rail Installation Guide** (TimberTech-irx-drink-rail-instructions-01-31-20.pdf) | ©2019, file 31 Jan 2020 | assets.timbertech.com/content/dam/wp-content/ |
| S14 | TimberTech IRX Order Form 2023 (cdn.domanbm.com) and TimberTech Rail Order Guide 2024 (shop.timbertech.com) | 2022 / 2024 | web |
| S15 | TimberTech IRX product page (shop.timbertech.com/product/impressionrail-express/) | fetched 27 Oct 2026 | web |
| S16 | Pin Foundations: Residential Load Chart DOC0008 (2018), **ICC-ES ESR-1895** (reissued Dec 2025), Installation Manual (2020), Brackets & Bits DOC0020 (2018), Product Matrix DOC0028 (2018) | as noted | diamondpiers.com |
| S17 | Simpson Strong-Tie catalog **C-C-2026**: ABA/ABU/ABW pp. 76–77 and CCQ/ECCQ pp. 98–99 | 2026 | buildsite.com product-data PDFs |
| S18 | Simpson CPTZ concealed post tie (catalog C-C-2021 page) | 2021 | fastenersplus.com PDF |
| S19 | Retail benchmarks: toolnut.com (CCQ68SDS2.5 $123.99, ECCQ68SDS2.5 $123.99, ABU88RZ $86.99, ECB88 $156.99); deckstore.com; thedeckstoreonline.com; kent.ca | fetched 27 Oct 2026 | web |
| S20 | TimberTech lighting: Metal-Railing Lighting Installation Guide, 150W Power Pack guide, LED Lantern Post Cap and Recessed Riser pages | current | assets.timbertech.com, timbertech.com |
| S21 | Lumbermens Inc. "Lighting – TimberTech by AZEK" list prices | effective 06/01/2026 | lumbermens-inc.com price page |
| S22 | Suncoast Louvered Roof page and brochure (SC-Louvered-Roof-Digital, Oct 2026) | Oct 2026 | suncoastenclosures.com |
| S23 | City of Centennial Building FAQ: 2021 IRC; Sec. 18-2-30 amendments set 30 psf non-reducible roof snow and 115 mph wind | fetched 27 Oct 2026 | centennialco.gov |
| S24 | Repo engine: `decktakeoff/data/pricebook.json` (as_of 2026-09-08), `catalog.py`, `takeoff.py`, `layout.py`, `spec.py`; skill timbertech-boards `scripts/catalog.py` and `references/lineup.md` (verified 9 Sep 2026) | — | /home/user/Decks-, /root/.claude/skills/... |

---

## 1. TimberTech Advanced PVC Vintage, English Walnut: product facts

| Question | Answer | Flag | Source |
|---|---|---|---|
| Current colour? | **Yes.** It is one of the six current Vintage colours: Coastline, English Walnut, Mahogany, Weathered Teak, Dark Hickory, Cypress. It is also in the skill catalog (`BOARDS` entry ("Vintage","English Walnut"), palette #2f2019…#a08874, identical in the repo `BOARDS_PALETTE`). | V | S10, S11, S24 |
| Board sizes (actual) | Standard **5.5" x 1"** (1x6). Narrow 3.5" x 1" (1x4). Wide 7.25" x 1" (1x8). MAX 1.5" thick is **Coastline only**. | V | S10, S11 |
| Lengths, 1x6 square-shoulder | **16' and 20' only** (ADB15516EW, ADB15520EW). **No 12' square-shoulder exists.** | V | S10 (the 12' column shows "—"); S11; Jade to Henry 21 Jul 2026: "square is only available in 16' and 20'" (Gmail 19f864dd2ec2e64a) |
| Lengths, 1x6 grooved | **12', 16', 20'** (AGB15512EW, AGB15516EW, AGB15520EW) | V | S10, S11 |
| Lengths, 1x4 / 1x8 square-shoulder | 16' and 20' (ADB13516EW / ADB13520EW; ADB172516EW / ADB172520EW) | V | S10 |
| **24'?** | **No.** No 24' Vintage board of any profile appears in the 2026 guide or on the product pages. | V | S10, S11 |
| Grooved vs square for this job | Every board is face-screwed with Cortex and plugged. That means **square-shoulder 16/20** for the field, picture frame, breakers, treads and the drink rail. GSX precedent from Hoegar, 24 Jul 2026: Henry wrote "they don't make 12' sq. stick with gv?" and Jade answered "Yes, please". So any 12' piece can be **12' grooved**, but only where the groove is hidden (field rows). Never use grooved on a picture-frame edge, a stair nosing or the drink rail (the drink rail must be square-shoulder full profile, S13). SOP note: "Only use grooved boards for the first board on a tread" (S9). Read that as the back board of a tread; the nosing board stays square. | V / E (reading) | Gmail 19f95671791bffd5 and 19f959ca97063977; S9; S13 |
| Matching fascia | **1/2" x 11-3/4" x 12'**, 12' only, **ADR5117512EW** | V | S10, S11 |
| Matching riser | **3/4" x 7-1/4" x 12'**, **ARISER72512EW** (D&D's description reads "3/4x8x12'") | V | S10, S1 |
| **Cortex plug colour name** | **"Vintage English Walnut".** Cortex for Advanced PVC, 100 SF loose **CTX100SFEW**, 300 SF loose CTX300SFEW, 100 SF collated **CTC100SFEW**, 300 SF collated CTC300SFEW. Plug packs (screws sold separately): CTC80PCEW (80 plugs) and CTC400PCEW (400 plugs). Kits: 100 SF = 350 screws + 400 plugs; 300 SF = 1,050 screws + 1,200 plugs. Screws are carbon steel; a 316SS screw option exists (CTS350SS25). | V | S10 p.16–17, S12 |
| TOPLoc colour for EW (fascia) | **Brown.** TimberTech's TOPLoc colour key: "Brown: Mahogany, English Walnut". Fascia screws **ATLOCFAS30B** (30 LF, 100 screws); deck screws ATLOC100B / ATLOC300B. | V | S10 |
| Warranty | **Limited Lifetime Product + 50-Year Limited Fade & Stain** | V | S11 |
| Fire | Ignition Resistant (ASTM E2632), Class A flame spread (E84), WUI compliant | V | S11 |
| Joist spacing | GSX standard is 12" OC for PVC (the owner already chose 12" OC). TimberTech's page defers to the install guide; only MAX is "up to 24" OC". | V | S24 catalog `oc=12`, S11 |
| Cortex coverage at 12" OC | 2 screws per board per joist means about 4.2 screws/SF. The "100 SF" kit (350 screws) therefore covers only about **83 SF at 12" OC**. The engine already counts by screws (350/box), which is correct. | E (arithmetic) | S10, S24 |

---

## 2. Impression Rail Express (IRX), Black, vertical balusters, with drink rail

### 2.1 Components (36" rail)

| Component | TimberTech SKU (Black) | Notes | D&D price | Flag / source |
|---|---|---|---|---|
| Level panel 8' | **AZTIX36UNLP8B** | Universal panel kit: 20 balusters, bottom rail cover, foot block, brackets and hardware. **Top rail not included.** Actual panel length 91.3". | **$293.91** | V S2 (GSEXT1 9 Jul 2026). The CASH50 quote 959545 had $275.52 (S4). |
| Level panel 6' | **AZTIX36UNLP6B** | 15 balusters, actual length 69.4" | **$211.35** | V S2 |
| Stair panel 8' | **AZTIX36UNSP8B** | Panel, panel cover, hardware, foot block; top rail not included | **$227.50** | V S2 |
| Stair panel 6' | AZTIX36UNSP6B | — | ~$163.59 | E (8' stair price × the 6'/8' level ratio 0.719) |
| Post kit 38" (level, 36" rail) | **AZTIX3X3PK38B** | Post, cap, skirt. **Fasteners to the deck are not included.** | **$82.20** | V S2. CASH50 959545 had $86.11. |
| Post kit 43-1/2" (36" **stair**) | **AZTIX3X3PK43B** | TimberTech: "43.5" for a 42" railing or 36" stair" | ~$94.86 | E (interpolated between the D&D 38" and 48" prices) |
| Post kit 48" (42" stair, or the "tall post" per SOP) | AZTIX3X3PK48B | — | **$105.22** | V S2 |
| **Drink rail: panel cover** (replaces the top rail) | **AZTBULKIXBR8B / AZTBULKIXBR6B** | "Universal Panel Cover for Drink Rail and Open Mid-Rail" | not quoted, ~$45 / ~$36 | E (kent.ca lists an 8' black IRX drink-rail top cover at CAD 42.99) |
| **Drink rail: clip kit** | **AZTIXDRCKITB** | 12 clips plus screws. 6 clips per 8' panel, 4 per 6' panel, so one kit covers two 8' or three 6' panels. | **$127.00** per kit | V S2 (first issue; the 16 Jul revision removed it for that job) |
| **Drink rail: board** | **ADB15516EW** (Vintage EW 1x6x16 square-shoulder); ADB15520EW where a run needs it | Full-profile square-shoulder only, never scalloped. Use a single 16' board rather than two 8' pieces. | $123.04 | V (Vintage 16' square, S1) |
| Drink rail: post inserts (over-the-post only) | AZTIX3X3PPLG (8-pack, "works for all colors") | The older guide uses field-cut 4x4 wood inserts | not quoted (~$40/pk) | E/U |
| Top rail (stairs, or any run without drink rail) | Classic AZTIXCSTR8B / 6B; Modern AZTIXMDTR8B / 6B | — | Classic **$91.70 / $76.94**; Modern not quoted | V S1 lines 47–48 / E |
| Graspable stair handrail (4+ risers, IRC R311.7.8) | AZTIXADA94RB pipe 1.5" x 94" + AZTIXADA90WRB 90° wall return | — | **$100.24** + **$35.82** each | V S2 |
|  | or AZTIXADAPR90DRKB (pipe rail + 90° return kit) + AZTIXADAPREKB (extension) | — | **$180.63** + **$193.48** | V S1 lines 49–50 |
| Touch-up paint + bracket jig | **AZTIXACCKITB** | TimberTech: "order at least 1 per job" | **$38.09** | V S1 line 51, S14 |
| Post fastening into blocking | FastenMaster HeadLOK 4-1/2" (412HL, each) | SOP: "Always use head lox into a block" | **$1.29** each | V S2, S9 |
| Panel end into a non-IRX post or wall (the 2 louvered-roof posts) | **AZTIXWBKTKITB** Wall Mount Kit | — | not quoted | U (S10 SKU) |

Is the Modern top rail in the $275.52 / $293.91 panel price? **No.** TimberTech says "TOP RAIL NOT INCL." (S10, S14), and D&D sells top rails as separate lines (S1). This resolves the open question in `jobs/prentice_centennial*.json`.

### 2.2 How the drink rail mounts on IRX (TimberTech guide S13, plus S10 / S14)

1. Order the drink-rail parts **in place of the Classic or Modern top rail**. Snap the **Universal Panel Cover** (AZTBULKIXBR; the 2019 guide calls it the "bottom rail cover, inverted") onto the panel's top support rail.
2. Screw the **drink-rail clips** up into the support rail with #8 x 3/4" self-drilling screws: 6 clips per 8' panel and 4 per 6' panel, **18" max apart**, with the first clip inside the first baluster at each end.
3. Centre the **deck board** on the cover. Pre-drill 1/8" holes 3/4" deep into the board's underside, then fasten through the clips with #8 x 3/4" SS MOD truss K-lath screws.
4. **Over-the-post:**
   - Cut the posts level, within 1/4" of the cover tops.
   - Put an insert in each post (AZTIX3X3PPLG, or a cut 4x4 per the 2019 guide).
   - Put board seams **on post centres** (boards up to 16') and mitre at the corners.
   - Drive **(3) 2-1/2" Cortex or TOPLoc screws on each side of a joint** into the insert, at least 3/4" from edges and ends. Pre-drill.
   - Leave no gap at joints, avoid butt joints, and install the boards cool.
5. **Between-the-post:** cut the board between the posts; the **post caps go on** (S13 step 5).
6. Limits:
   - Only **3" posts** work with the drink rail.
   - It does not work with glass infill or the open mid-rail.
   - Don't use 3.5" boards over-the-post, or 7.25" boards between-the-post.
   - On stairs (over-the-post), butt the board to the top post and overhang the bottom post by about 1-1/2".

### 2.3 Post spacing and heights

- **Max 96" post centre to centre for 8' panels and 72" for 6' panels, with 3" posts.** S13: "8' and 6' Rails are designed not to exceed 8' and 6' from center of post to center of post, using 3" posts." (V)
- Actual panel lengths are 91.31" (8') and 69.43" (6') (S15, V).
- Post heights: 38" for a 36" level rail; 43.5" for a 36" stair; 48" for a 42" stair (S15, V).
- For fascia-mounted stair posts, a TimberTech fascia-mount guide quoted in search results gives 70" OC. I did not open that guide (U); it does not apply to surface-mounted posts.
- Warranty: 25-year limited (S15, V).
- SOP: "IRX has trouble racking on stairs, may need to adjust the tabs", and "tall post at the bottom and tall post at mid point if over 12 risers" (S9).

### 2.4 Things that need a decision

- **Post-cap lights on every post vs. the drink cap.** An over-the-post drink rail covers the post tops, so no cap and no cap light can go there. To light every post, the drink rail must be **between-the-post** (S13 step 5 installs post caps). The alternative is a post-side Small Accent Light (AZTIXLEDACCB) on the level runs. (V for the mechanics, E for the recommendation.) See section 6.2 (Option 1).
- **Engine naming.** `RAIL_SYSTEMS["Impression Rail Express"]` and `["IRX"]` are the **cable** system (catalog.py line 169). The Fillmore spec must use **`"IRX Baluster"`** or the engine will order cable kits (S24).

---

## 3. Unit prices, line by line

All prices are D&D to GSEXT1 unless the flag says otherwise. Prices are before the material factor and tax.

### 3.1 Decking, fascia, risers (Vintage English Walnut)

D&D prices Vintage the same in every colour: Henry gave one Vintage $/LF in S4, and S1/S2 show the same SKU pattern. The Weathered Teak and Dark Hickory lines below therefore stand in for English Walnut.

| Line | Unit | Price | Flag | Source (date) |
|---|---|---|---|---|
| Vintage 1x6x16 square-shoulder (EW = ADB15516EW) | ea | **$123.04** ($7.69/LF) | V | S1 line 1 AZV1616WT (11 Sep 2026) |
| Vintage 1x6x20 square-shoulder (ADB15520EW) | ea | **$153.80** ($7.69/LF) | V | S1 line 2 AZV1620WT |
| (history) Vintage 1x6x16 / x20 square, Dark Hickory | ea | $130.05 / $159.60 | V | S2 (9 Jul 2026), higher than S1 |
| Vintage 1x6x12 grooved (AGB15512EW) | ea | ~$92.28 | E | 12' × $7.69/LF |
| Vintage 1x6x16 / x20 grooved (AGB15516EW / AGB15520EW) | ea | ~$123.04 / ~$153.80 | E | D&D prices grooved the same as square elsewhere: Landmark FWO 1x6x20 square and grooved both $138.60 (S2); Reserve DW 1x6x20 square and grooved both $112.15 (S3) |
| Vintage 1x6x**12 square** | — | **not manufactured** | V | S10, S11, Jade 21 Jul 2026 |
| Vintage fascia 1/2 x 11-3/4 x 12' (ADR5117512EW) | ea | **$171.38** ($14.28/LF) | V | S1 line 3 AZVFASCIA12WT. S2 (Jul): $186.77 |
| Vintage riser 3/4 x 7-1/4 x 12' (ARISER72512EW) | ea | **$121.69** ($10.14/LF) | V | S1 line 4 AZVRISER12WT. S2 (Jul): $132.62 |
| Reference: Henry's Vintage $/LF (deck / fascia / riser) | LF | $7.11 / $13.15 / $9.35 | V | S4 e-mail, 8 Jul 2026 |
| Reference: GS Pricing Sheet (Vintage $/LF; fascia $/LF; stair sheet "Decking is 12' $84") | — | $7.00; $13.15; $84 | V | S7 (14 Jul 2026). The $84 assumes a 12' Vintage square board, which doesn't exist. |
| Pricebook today: Vintage 12/16/20 square $84 / $112 / $140 ("PS"); grooved $86.40–144 est.; fascia $96 est.; riser $62 est.; per_lf $7.00 | — | — | E | S24. Fascia is under by $75 per board and riser by $60. |

### 3.2 Deck fasteners

| Line | Unit | Price | Flag | Source |
|---|---|---|---|---|
| **Cortex for TimberTech Advanced PVC, collated 100 SF**, Vintage EW plugs (**CTC100SFEW**: 350 screws, 400 plugs, 3 bits) | box | **$175.00** | V (the Dark Hickory SKU CTC100SFDH; EW is the same product) | S2 (9 Jul 2026) |
| Cortex 300 SF collated (CTC300SFEW) | box | ~$498 | E | 100 SF price × 2.85, the D&D TOPLoc 300/100 SF price ratio in S1 |
| Cortex plug packs CTC80PCEW / CTC400PCEW | pk | not quoted | U | S10 |
| **TOPLoc fascia screws, Brown (ATLOCFAS30B)**, 30 LF pack, 100 screws + bit | pk | **$59.90** | V (Light Tan SKU ATLOCFAS30LT, same product) | S1 line 7. S2 (Jul): ATLOCFAS30DH $47.09 |
| Reference only: 979610 lines 5–6 are **TOPLoc for PVC 100 SF $157.29 / 300 SF $448.21 (Light Tan)**. **They are not Cortex.** | — | — | V | S1 PDF. `jobs/parkview_deck.json` relabels them "CORTEX-100-WT / CORTEX-300-WT", which is wrong. |
| Pricebook today: Cortex_TimberTech_350 $98 EST | box | — | E | S24. Under by $77 per box. |

### 3.3 Rail (IRX Black)

See the table in 2.1. In short:
- 8' level panel **$293.91**, 6' level **$211.35**, 8' stair **$227.50**
- 38" post **$82.20**, 48" post **$105.22**, 43.5" post ~$94.86 (E)
- Drink-rail clip kit **$127.00 per 12 clips**
- Classic top rail 8' / 6' **$91.70 / $76.94**
- ADA handrail parts **$100.24 / $35.82**, or kits **$180.63 / $193.48**
- Touch-up kit **$38.09**
- Panel covers ~$45 / ~$36 (E)

GSX labor (S8): rail **$20/LF** plus **drink rail +$5/LF**. Sell rule in the pricebook: IRX $120/LF at 40% GM (S24). The field playbook quotes IRX at $125/LF and drink rail at about $33/LF sell.

### 3.4 Framing lumber

| Line | Unit | Price | Flag | Source |
|---|---|---|---|---|
| 2x10x12 #1 True Frame Joist GC (210N12TFJ) | ea | **$43.93** ($3.66/LF) | V | S1 line 10 |
| 2x10x16 TFJ (210N16TFJ) | ea | **$62.03** ($3.88/LF) | V | S1 line 12 |
| 2x10x20 TFJ (210N20TFJ) | ea | **$81.55** ($4.08/LF) | V | S1 line 18 |
| (history) 2x10x12 / 16 / 20 | ea | $45.95 / $60.40 / $81.24 (S3, 15 Jul); $40.40 / $56.60 / $72.00 (S2, 9 Jul) | V | — |
| 2x10x14 / x18 / x24 | ea | not quoted | U | (the catalog lists 24' stock for 2x10) |
| 2x12x16 TFJ (stringer stock) | ea | **$77.06** ($4.82/LF) | V | S1 line 11 |
| 2x12x12 / 2x12x20 TFJ | ea | **$52.86 / $98.24** | V | S3 (15 Jul). S2: $52.65 / $105.26 |
| 2x6x12 #1 KDAT GC | ea | **$21.90** | V | S1 line 13 |
| 2x4x12 / 2x4x16 #1 KDAT GC (furring) | ea | **$13.68 / $18.76** | V | S1 lines 14–15 |

SOP framing notes (S9): block every 4' for PVC; G-Tape on every 2x member; stringers at 12" OC; H2.5 at drop beams.

### 3.5 Timbers (columns and the drop beam)

| Line | Unit | Price | Flag | Source |
|---|---|---|---|---|
| **8x8 Douglas fir #1 rough**, 8 / 10 / 12 / 16 ft | ea | **~$159 / ~$198 / ~$238 / ~$318** (~$19.85/LF) | **E** | Not on any D&D document. Scaled at the same $/board-foot as D&D's 6x6x10 DF RGH at $111.64 (S3, S5), which is $3.72/BF. D&D's 6x6x8 DF RGH at $70.98 / $63.45 (S2) is $2.64–2.96/BF, giving a low case of about $14–16/LF. Henry to quote "8x8 DF #1 RGH" for 8/10/12. The SKU pattern suggests 88DF12RGH (U). |
| **6x10 Douglas fir #1**, 12 / 16 / 20 ft | ea | **~$223 / ~$298 / ~$372** (~$18.60/LF) | **E** | Not quoted. 5 BF/LF × $3.72/BF. Henry to quote. |
| Pricebook today: 8x8_DF#1 $12.50/LF (EST, "8x8x8 $100"); 6x10_DF#1 $13.00/LF (est.) | — | — | E | S24. Both are probably 35–60% low. |

Rough-sawn sizes: GSX treats D&D "DF RGH" as full-dimension (ABA66RZ / AC6RZ were sold with the 6x6 RGH in S5). Assume an 8x8 RGH measures about 8.0" (U, measure it), which drives the base and cap choice in section 4.

### 3.6 Footings, bases, caps, connectors

| Line | Unit | Price | Flag | Source |
|---|---|---|---|---|
| **Diamond Pier DP-50** (D&D DP1000 "Diamond Pier Deck Footing DP50") | ea | **$165.61** | V | S1 line 33. The pin length is not on the line; confirm 50" pins. |
| **Diamond Pier DP-75/63** | ea | ~$257 | **E** | DP-50 × 1.55 (the pricebook's own ratio is 215/135 = 1.59). Not quoted; Henry to quote. Retail: deckstore.com lists both sizes at $249, sold out (S19). |
| Simpson **CCQ68SDS2.5** (6x beam on 8x post, intermediate) | ea | ~$124 | E | toolnut $123.99 (S19). Pricebook $142 EST. |
| Simpson **ECCQ68SDS2.5** (beam-end posts) | ea | ~$124 | E | toolnut $123.99. Pricebook $118 EST. |
| CCQ68 / ECCQ68 with a custom **W2 = 8"** for a full-rough 8x8 | ea | ? (special order) | U | S17: "For rough-cut lumber sizes, provide dimensions. An optional W2 dimension may be specified." |
| Simpson **ECB88HDG** elevated column base (single 1/2" centre anchor option) | ea | ~$157 | E | toolnut ECB88 $156.99 (S19). See section 4. |
| Simpson ABU88RZ (rough 8x8; needs **2** anchors) | ea | ~$87 | E | toolnut $86.99. Not a Diamond Pier part. |
| Custom HDG 8x8 standoff base for the DP-75 5/8" bolt | ea | ~$225 | E/U | fabricator; PFI and an engineer must approve |
| LUS210Z | ea | **$2.43** | V | S1 line 19 |
| HUC2102-2Z (concealed double 2x10, for the notch header and trimmers) | ea | **$37.96** | V | S1 line 20. D&D quotes HUC, not HUCQ. |
| H2.5AZ | ea | **$0.83** | V | S1 line 21 |
| LSCZ | ea | **$2.93** | V | S1 line 25 |
| DTT2Z | ea | **$13.81** | V | S1 line 26 |
| DTT1Z | ea | **$4.86** | V | S2 |
| FastenMaster LedgerLOK 5" (50) | box | **$77.25** | V | S1 line 27 |
| Camo 3" PRO-FIT hanger nail, 5 lb | box | **$20.29** | V | S1 line 29 |
| Camo 1-1/2" x .148 PRO-FIT, collated (1M) | box | **$51.95** | V | S1 line 30 (a 5 lb box of the 1-1/2" is $22.74, S6) |
| Camo 3" #9 deck screw (350) | box | **$32.07** | V | S1 line 31 |
| Simpson SD9212R100R (#9 x 2-1/2", 100) | box | **$30.73** | V | S2 |
| FastenMaster ThruLOK 8" (24) | box | **$118.51** | V | S3 |

### 3.7 Joist tape and flashing

| Line | Unit | Price | Flag | Source |
|---|---|---|---|---|
| Nichigo G-Tape 3035 **2" x 65'** (joists) | roll | **$18.60** | V | S1 line 8 |
| G-Tape 3035 **4" x 65'** (rims) | roll | **$36.60** | V | S1 line 9 |
| G-Tape 3040 **9" x 65'** with liner (tops of the 6x10 beam, which is 5-1/2" wide; 4" tape doesn't cover it) | roll | **$84.17** | V | S1 line 32. A 6" roll is not quoted: pricebook est. $62 (E). |
| Grace Vycor Plus 12" x 75' | roll | **$73.03** | V | S2 |
| Deck ledger flashing 8' (3x3) | ea | **$12.00** | V | S2 |

### 3.8 Labor basis (GSX card, S8)

**Base rates (V):**
- Frame $10/SF
- Decking & fascia $8/SF
- Railing $20/LF
- Stairs $150/riser
- Demo $2/SF

**Add-ons (V):**
- Drink rail $5/LF
- Diamond Pier, replacing the caisson price: $50/pier
- **Stone/stucco column demo $50/LF**. This covers the brick columns: count column height × columns, owner to confirm it applies to brick.
- Skirting $10/LF
- 12" OC +$1/SF
- PVC deck +$1/SF
- Larger timbers +$2/SF
- 13'–15' height +$2/SF. The upper level at about 12' is below this band.

The pricebook says the owner dropped the steel, larger-timber, PVC and 12"-OC up-charges on 7 Sep 2026 (S24). Confirm that still holds for Fillmore.

---

## 4. 8x8 columns on Diamond Piers, and the cap for a 6x10 drop beam

### 4.1 DP-50 vs DP-75 (V: S16)

| | DP-50/50 | DP-75/63 |
|---|---|---|
| Head | 10 x 10 x 11", about 50 lb | 11 x 11 x 12", about 75 lb |
| **Top plinth** | **5-5/8" square** | **5-5/8" square** |
| Embedded anchor bolt | **1/2"** A307, galvanized | **5/8"** |
| Pins | 4 × 1" Sch 40 × 50" | 4 × 1-1/4" × 63" |
| Bearing, 1,500 psf silts/clays (the soil the Centennial jobs assume) | **3,300 lb** | **4,200 lb** |
| Bearing, 2,000 psf sands/gravels | 4,400 lb | 6,400 lb |
| Uplift / lateral | 1,200 / 600 lb | 1,600 / 600 lb |
| Frost rating | 48" | 60" |
| Concrete head limit | 4,500 lb | 6,500 lb |
| Price | **$165.61** (V, S1) | ~$257 (E) |

**Engine error:**
- `FOOTING_CAPACITY_LB["DP-75/63"] = 6000` (catalog.py line 133) and pricebook `capacity_lb: 6000` give DP-75/63 the wrong capacity.
- At 1,500 psf the chart says **4,200 lb**. The 6,000 figure matches neither soil column; it is close to the 2,000 psf value (6,400 lb).
- `layout.py` lines 678 and 1404 auto-upgrade to DP-75/63 up to 6,000 lb. A pier loaded at 4,201–6,000 lb on clay is therefore passed as adequate when it is not. (V)
- Centennial frost depth: the jobs use 36", which is fine for both piers (U: the city FAQ doesn't state it; confirm with Centennial Building).

### 4.2 The 8x8 base: what actually fits a Diamond Pier

- **ABA88Z does not exist.** The Simpson ABA series stops at ABA66Z / ABA66RZ (S17, V).
- **ABU88Z** (7-1/2") and **ABU88RZ** (8" rough) need **(2) 5/8" anchors**. Loads: ABU88Z 4,120 lb uplift / 22,405 lb down; ABU88RZ 4,045 / 19,870 (S17, V). APB88 / APB88R (Outdoor Accents, black) and CPT88Z (2 × 1/2", S18) also use **two** anchors (APB from retailer listings, U).
- A Diamond Pier gives **one** bolt on a **5-5/8"** plinth. The manual says the bracket must be "fully supported by the concrete" (S16). PFI's bracket note: single-bolt DP-75 brackets "generally come in three sizes corresponding to 4x4, 4x6, or 6x6 lumber", and 4-bolt piers need custom HDG brackets (DOC0020, V). The 4-bolt versions: DP-75 4B has (4) 1/2" bolts at 4-1/2" OC; DP-200E has a 9x9 plinth and (4) 5/8" or 3/4" bolts at 7-1/2" OC (DOC0028, V).
- **The only off-the-shelf single-centre-anchor 8x8 base I found is the Simpson ECB88 / ECB88HDG**:
  - one 1/2" centre anchor with (2) 1/2" cut washers
  - 2" elevated, 1" standoff
  - fits a **nominal (7-1/2") 8x8 only**
  
  Simpson lists Titen HD / SET-3G concrete anchors for it, not a cast-in bolt, and the footprint against the 5-5/8" plinth is unchecked (U).
- **Recommendation:** hold this connection for Jade and the engineer (and PFI). The owner's columns stay 8x8. Three ways to do it:
  - **(a)** S4S 8x8 at the base on an **ECB88HDG** over a **DP-50**, but only if the post loads are ≤ 3,300 lb and PFI and Simpson accept the cast-in 1/2" bolt.
  - **(b)** **DP-75/63** (4,200 lb) with a **custom HDG 8x8 standoff base** on its 5/8" bolt. About $257 + $225 per post (E). Needed if the posts carry more than 3,300 lb or are full 8" rough.
  - **(c)** DP-200E (4B) with a custom bracket, engineered.
- The engine has **no 8x8 base for Diamond Piers**. `POST_BASE` lacks "8x8", so the takeoff writes **ABA66Z / ABA66RZ** under 8x8 posts (takeoff.py lines 748–751). (V)

### 4.3 The cap for a 6x10 on an 8x8: **CCQ68SDS2.5 / ECCQ68SDS2.5**

- **CCQ68SDS2.5** (S17, V):
  - W1 5-1/2" (beam width 5-1/4 or 5-1/2"), W2 7-1/2" (post), L 11", H 7"
  - 16 + 14 SDS 1/4 x 2-1/2" screws, included
  - DF/SP allowable: 6,785 lb uplift / 37,815 lb down
  - **7 ga** (Simpson: "CCQ6, ECCQ6 — 7 gauge"); beam must be at least 7" deep (the 6x10 is 9-1/2")
  - Use it at **intermediate and spliced** posts. Uplift values don't apply to splices, so the designer details those.
- **ECCQ68SDS2.5** (L 8-1/2"; 3,785 lb uplift / 25,780 lb down) goes at **beam ends**. Simpson: "For end conditions, specify ECCQ."
- **Full-rough 8" posts:** order with the **optional W2 = 8"** (Simpson: provide dimensions for rough-cut lumber).
- **Why not BC8 or CCQ88:**
  - **BC8** is an 8x-beam-on-8x-post cap: W1 = W2 = 7-1/2", 18 ga, light-duty, nailed (S19 listings, E/V). A 5-1/2" beam in a 7-1/2" seat doesn't fit.
  - **CCQ88SDS2.5** is also an 8x beam seat (W1 7-1/2").
  - CC68 (bolted) is the older line; Simpson marks CCQ as preferred.
- **Engine:** in dimensional mode `cap_mid = cap_end = post_cap(...)` (layout.py line 1381), so it writes **CCQ68 at every post, ends included**. It also adds 10 SD screws per CCQ, which already ships with its SDS screws (`POST_CAP_SCREWS` has no CCQ entry).

---

## 5. Price list by category (for the takeoff)

These are the lines with V numbers to load now. Items still E: 8x8 / 6x10 DF timbers, DP-75, CCQ68 / ECCQ68, the 8x8 base, IRX panel covers and post inserts, the 6' stair panel and 43.5" post, and Cortex 300 SF.

- Vintage EW 16' / 20' square **$123.04 / $153.80**; fascia **$171.38**; riser **$121.69**
- Cortex PVC 100 SF **$175.00**; TOPLoc fascia 30 LF **$59.90**
- IRX 8' / 6' level **$293.91 / $211.35**; 8' stair **$227.50**; 38" post **$82.20**; 48" post **$105.22**; drink-rail clip kit **$127.00**; Classic top rail 8' / 6' **$91.70 / $76.94**; ADA parts **$100.24 / $35.82**; touch-up kit **$38.09**
- 2x10 x12 / x16 / x20 **$43.93 / $62.03 / $81.55**; 2x12 x12 / x16 / x20 **$52.86 / $77.06 / $98.24**
- DP-50 **$165.61**
- LUS210Z **$2.43**; HUC2102-2Z **$37.96**; H2.5AZ **$0.83**; LSCZ **$2.93**; DTT1Z **$4.86**; DTT2Z **$13.81**
- G-Tape 2" / 4" / 9" **$18.60 / $36.60 / $84.17**

---

## 6. Bid structure (owner, 27 Oct 2026) and the owner changes

The owner splits the bid this way:
- **BASE:** two levels, IRX rail and drink rail, **the inset stair between levels and its vertical skirt**, and demo.
- **OPTION 1:** lighting (riser and post-cap lights, transformer, wire, labor).
- **OPTION 1 add-on:** lighting for the yard stair. This only applies if Option 2 is taken too.
- **OPTION 2:** stairs to the ground (the yard stair).
- **OPTION 3:** the louvered roof at an owner-set **$35,000**.

Each option below is a self-contained list so it can be priced on its own. All totals are materials **before** the 1.15 material factor and sales tax. Counts are **E** (taken from the shared brief's plan frame and the owner's counts) until the engine's layout runs. Prices carry their own flags.

**One rule for all the lighting:** there are **no lighting SKUs or prices** in any D&D quote or order (S1–S6), in Drive, in Henry's mail, or in the pricebook (S24). The lighting prices are therefore **E**: TimberTech-by-AZEK list prices effective 1 Jun 2026 (S21) and The Deck Store retail.

### 6.1 BASE add-ins: inset stair between the levels, and its vertical step-face skirt

**Demo** is in the base. It is labor only on the GSX card: $2/SF demo, plus **$50/LF "Stone/Stucco Column Demo"** for the brick columns (S8, V; owner to confirm it covers brick). The dumpster is in the general conditions (pricebook template: 20 yd, $650).

**Step-face skirt.** Vintage EW fascia installed **vertically** on 2x furring; the lattice is gone. The face is 36" high and about 10' (120") long including the notch cheeks (owner). Panels are cut to about 34-3/4" (36" less the 1" upper decking and a 1/4" drainage gap). The cheeks are cut to the step profile, which only makes them shorter.

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| **Vintage EW fascia 1/2 x 11-3/4 x 12' (ADR5117512EW)**, vertical, cut to about 34-3/4" | 4 | $171.38 | $685.52 | count E: 120" / 11.75" means 11 panels; 4 cuts per 12' board, so 3 boards plus 1 spare; price V S1 |
| **TOPLoc fascia screws, Brown (ATLOCFAS30B)**, 100 per pack | 1 | $59.90 | $59.90 | about 66 needed (11 panels × 3 nailer rows × 2), pre-drilled; price V S1 (LT SKU). Not Cortex (see note) |
| **2x4x12 #1 KDAT GC** furring and blocking | 6 | $13.68 | $82.08 | count E: 3 nailer rows × 10' + studs at 16" + cheek backing, about 54 LF, plus 1 cull; price V S1 |
| Simpson SD9212R100R #9 x 2-1/2" (100), furring | 1 | $30.73 | $30.73 | V S2 |
| G-Tape 2" on the furring faces | 1 | $18.60 | $18.60 | V S1 (optional) |
| **Skirt materials** | | | **$876.83** | before the 1.15 material factor and tax |

- Fascia fasteners: TimberTech lists **TOPLoc** for Advanced PVC fascia and has no Cortex fascia kit (S10, S11, V). A Cortex counterbore and plug won't fit 1/2" stock (E).
- Labor: GSX "Skirting $10/LF" add-on × 10 LF = **$100** (V rate, S8; owner to confirm it applies).

**Inset stair.** 5 risers at about 7.2" each (owner; IRC max 7-3/4"), 4 treads at about 11", 48" wide, inside a 4' notch in the upper level's left face at B|C.

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| 2x12x12 #1 TFJ stringers (5 at 12" OC, about 69" each, 2 per stick) | 3 | $52.86 | $158.58 | count E; price V S3 |
| Vintage EW 1x6x20 square (ADB15520EW): treads, 4 treads × 2 boards × 48", 4 per 20' board | 2 | $153.80 | $307.60 | count E; price V S1 |
| Vintage EW 1x6x16 square (ADB15516EW): tread spare | 1 | $123.04 | $123.04 | V S1 |
| Vintage EW riser 3/4 x 7-1/4 x 12' (ARISER72512EW): 5 risers × 48", 2 per board | 3 | $121.69 | $365.07 | count E; price V S1 |
| Simpson HUC2102-2Z at the notch header and trimmers | 4 | $37.96 | $151.84 | count E; price V S1 |
| Simpson LSCZ (1 per stringer) | 5 | $2.93 | $14.65 | V S1 |
| ADA handrail pipe AZTIXADA94RB (5 risers: IRC R311.7.8 needs one side), wall-mounted on a cheek over blocking | 1 | $100.24 | $100.24 | V S2 |
| ADA 90° wall return AZTIXADA90WRB | 2 | $35.82 | $71.64 | V S2 |
| Cortex PVC 100 SF collated, EW plugs (CTC100SFEW): about 130 stair screws (the engine drops stair screws in Cortex mode, G8) | 1 | $175.00 | $175.00 | V S2 price; count E |
| **Inset-stair materials** | | | **$1,467.66** | before the 1.15 material factor and tax |

- Labor: stairs $150/riser × 5 = **$750** (V rate, S8).
- Guard: IRX runs along the upper-level face beside the notch (36" drop). It is part of the deck rail. The notch sides drop at most about 28.8" to the treads (E reading).
- Riser lights go in Option 1, not here.
- **Base add-ins total (skirt + inset stair):** **$2,344.49** materials, plus **$850** labor (stairs $750 + skirting $100).

### 6.2 OPTION 1: lighting for the base deck and the inset stair (priced on its own)

**IRX-compatible products** (TimberTech 2026 guide p.39, "Impression Rail Express Lighting", V):

| Use | Product | SKU (Black) | Spec (S20) | Price | Flag |
|---|---|---|---|---|---|
| **Post-cap light, every IRX post** (recommended) | 3" LED Lantern Post Cap Light | **AZTDL3X3LANCAPB** | Listed for IRX 3" x 3" posts in Black; 12V AC, 2700K, dimmable, instant-on; 5-yr warranty | ~$136 each | E (S21 4" lantern list $135.69; The Deck Store "as low as $129.99") |
| alternatives | 3"x3" Perimeter Light Post Cap / 3"x3" Indirect-Concealed Down-Light Post Cap / 3" Post Cap Light | AZTIXLIGPCB / AZTIXLIGDCB / AZTDL3X3LEDCAP | — | not found | U |
| post side (only if the drink rail runs over the posts) | Small Accent Light | AZTIXLEDACCB | — | not found | U |
| **Riser light, every riser** | Recessed LED Riser Light, Matte Black | **AZTDLRECRISERMB** | 2-3/4" H x 5-3/4" W, **1/2" deep in the riser** (fits the 3/4" Vintage riser), stands 3/16" proud, 6' lead, 12V, 2700K | $88.24 list | E (S21; The Deck Store $94.99) |
| Transformer | 100W 12V, photocell + timer | **AZTDL100TRAN** | **90 W max recommended load; 60 W max on one run** (S20) | $135.15 list | E (S21; The Deck Store $137.99) |
| Transformer (larger, not needed here) | 150W PowerPack / dimmer with remote | AZTDL150PPR | Timer, photo eye, dimmer; maximum load not stated (U, plan ≤ 135 W) | $373.95 list | E |
| Wire | 16/2 AWG, 100' | **AZTDLLEDWIRE** | Daisy-chain from the transformer; never loop back; polarity doesn't matter | $112.13 list | E |
| Connectors | Silicone-filled outdoor wire nuts | — | Splices go in the cavity under the post cap (the "junction box"); leave slack at each post top; drill a 3/4" wire hole | ~$20 per 25 | E |

**Sizing rules** (S20, V):
- Post cap 4 W, riser 2 W.
- **W = 4 × posts + 2 × risers.**
- ≤ 90 W per 100 W transformer, and ≤ 60 W per run (15 post caps or 30 risers).
- The transformer plugs into a **GFCI-protected, hooded (in-use) receptacle**.
- Secondary wire is for shallow burial under 6"; don't put it on a dimmer circuit.

**Base quantities (E):**
- Rail about 104 LF: lower about 52 (arm A's open side 22.8' + A/B front 29.2'); upper about 52 (C/D front 33.9' + D's right end 12' + step face 10' less the 4' notch).
- That gives about 8 + 9 posts at ≤ 96" centres, less the **2 louvered-roof posts** that replace IRX posts. Carry **about 17 posts** (range 15–19).
- **5 riser lights** for the inset stair.
- Load ≈ 17 × 4 + 5 × 2 = **78 W**: **one AZTDL100TRAN** on **2 runs** (lower and upper).

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| **3" LED Lantern Post Cap Light, Black (AZTDL3X3LANCAPB)**, one per IRX post (about 15–19; the 2 roof posts excluded) | 17 | $136.00 | $2,312.00 | count E (rail ≈ 104 LF, 8' bays); price E (S21 4" lantern list $135.69) |
| **Recessed LED Riser Light, Matte Black (AZTDLRECRISERMB)**, inset stair | 5 | $88.24 | $441.20 | count = owner; price E (S21 list) |
| **TimberTech 100W 12V transformer, photocell + timer (AZTDL100TRAN)**: about 78 W (17 × 4 + 5 × 2) on 2 runs | 1 | $135.15 | $135.15 | sizing V (S20 rules); price E (S21 list) |
| 16/2 AWG low-voltage wire, 100' (AZTDLLEDWIRE) | 2 | $112.13 | $224.26 | count E; price E (S21 list) |
| Silicone-filled outdoor wire nuts, 25-pack | 2 | $20.00 | $40.00 | E |
| **Option 1 lighting materials** | | | **$3,152.61** | before the 1.15 material factor and tax |

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| Fixture install (drill 3/4" hole, pull wire, splice, mount) | 22 | $50.00 | $1,100.00 | E market basis; there is no lighting line on the GSX card (S8) |
| Transformer: mount, set photocell / timer | 1 | $175.00 | $175.00 | E |
| **Option 1 lighting labor** | | | **$1,275.00** | labor (no material factor or tax) |

- **Option 1 total:** **$3,152.61** materials + **$1,275.00** labor (E).
  - The range for 15–19 posts is $2,880.61–$3,424.61 materials.
  - Add **$250–$450** (E) for an electrician if no exterior GFCI in-use receptacle is near the transformer spot.
- Labor reference: HomeWyse's May 2026 national all-in retail of $298–$481 per light, materials included, is a ceiling, not crew pay.
- Wiring goes in during framing (3/4" holes through the blocking and decking under each post).
- **Design condition:** a post-cap light on **every** post needs the drink rail **between the posts** on the level runs. Over-the-post boards cover the post tops (S13; section 2.4). Between-the-post uses the same post kits and needs no post inserts.

### 6.3 OPTION 1 add-on: lighting the yard stair (only with Options 1 and 2)

- 13–14 riser lights (owner) and about 10 stair and landing posts (E).
- Load ≈ 10 × 4 + 14 × 2 = **68 W**. Put it on **its own AZTDL100TRAN**: the base unit is already at about 78 W of its 90 W.

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| Recessed LED Riser Light, Matte Black (AZTDLRECRISERMB), yard stair (13–14 risers) | 14 | $88.24 | $1,235.36 | count = owner; price E (S21) |
| 3" LED Lantern Post Cap Light, Black (AZTDL3X3LANCAPB), yard-stair and landing posts | 10 | $136.00 | $1,360.00 | count E; price E |
| Second AZTDL100TRAN for the yard-stair circuit (about 10 × 4 + 14 × 2 = 68 W) | 1 | $135.15 | $135.15 | sizing V (S20); price E |
| 16/2 wire, 100' (AZTDLLEDWIRE) | 1 | $112.13 | $112.13 | E |
| Wire nuts, 25-pack | 1 | $20.00 | $20.00 | E |
| **Add-on materials** | | | **$2,862.64** | before the 1.15 material factor and tax |

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| Fixture install | 24 | $50.00 | $1,200.00 | E |
| Transformer | 1 | $175.00 | $175.00 | E |
| **Add-on labor** | | | **$1,375.00** | labor (no material factor or tax) |

- **Add-on total:** **$2,862.64** materials + **$1,375.00** labor (E).
- With 13 risers: −$88.24 materials and −$50 labor.

### 6.4 OPTION 2: stairs to the ground (yard stair)

Layout from the brief (E):
- A 4'-wide flight 1 drops off the lower level's outer edge (opening at about x 19.17–23.17, y = 10) to a **9' wide × 4' deep landing**.
- Flight 2 switches back toward the house alongside flight 1 and lands on grade.
- 14 risers (7 + 7, about 7.7" each for about 9' of rise), 12 treads at about 11".
- The landing is at about 54" above grade, on **4 posts and 4 Diamond Piers**.
- IRX on both sides of both flights plus a landing guard (far 9' edge and the two 4' sides).
- **ADA graspable handrail** on one side of each flight (7 risers each, IRC R311.7.8).
- **36" hard surface at the bottom** (SOP and playbook: "not grass").

The stairs agent's engine takeoff supersedes these counts.

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| 2x12x16 #1 TFJ stringers (2 flights × 5 at 12" OC, about 95" each, 2 per stick) | 5 | $77.06 | $385.30 | count E; price V S1 |
| 2x10x12 #1 TFJ landing frame (9' × 4': rims + 11 joists at 12") | 7 | $43.93 | $307.51 | count E (engine landing formula); price V S1 |
| 6x6x8 Douglas fir RGH landing posts (4 posts about 42", 2 per stick) | 2 | $70.98 | $141.96 | count E; price V S2. Alternate: 8x8 to match the columns, see the note below |
| Diamond Pier DP-50 landing footings | 4 | $165.61 | $662.44 | V S1 |
| Simpson ABA66RZ rough 6x6 post base on the pier bolt | 4 | $28.97 | $115.88 | V S5 (CASH50) |
| Simpson AC6RZ rough 6x post cap | 4 | $16.40 | $65.60 | V S5 (CASH50); the stairs agent confirms the cap |
| Simpson LUS210Z (landing joists, 2 each) | 22 | $2.43 | $53.46 | V S1 |
| Simpson LSCZ (1 per stringer) | 10 | $2.93 | $29.30 | V S1 |
| Vintage EW 1x6x20 square (ADB15520EW): treads, 12 treads × 2 boards × 48", 4 per board, + 1 spare | 7 | $153.80 | $1,076.60 | count E; price V S1 |
| Vintage EW 1x6x20 square: landing decking with picture frame (about 36 SF) | 6 | $153.80 | $922.80 | count E; price V S1 |
| Vintage EW riser 12' (ARISER72512EW): 14 risers × 48", 2 per board | 7 | $121.69 | $851.83 | count E; price V S1 |
| Vintage EW fascia 12' (ADR5117512EW): stepped skirts both sides of both flights (SOP: no exposed ends) + landing fascia + 1 spare | 5 | $171.38 | $856.90 | count E; price V S1 |
| Cortex PVC 100 SF collated EW (about 530 screws: treads, risers, landing) | 2 | $175.00 | $350.00 | count E; price V S2 |
| TOPLoc fascia screws, Brown (ATLOCFAS30B) | 2 | $59.90 | $119.80 | count E; price V S1 |
| G-Tape 2" (stringers, landing joists) | 2 | $18.60 | $37.20 | V S1 |
| IRX 36" 8' stair panel, Black (AZTIX36UNSP8B): both sides of both flights | 4 | $227.50 | $910.00 | count E; price V S2 |
| IRX 36" 6' level panel, Black (AZTIX36UNLP6B), cut: landing guard (9' far edge + two 4' sides) | 4 | $211.35 | $845.40 | count E; price V S2 |
| IRX Classic top rail 8' (AZTIXCSTR8B): stair sections (panels ship without a top rail) | 4 | $91.70 | $366.80 | V S1 (Modern E) |
| IRX Classic top rail 6' (AZTIXCSTR6B): landing guard | 4 | $76.94 | $307.76 | V S1 |
| IRX post kit 43-1/2" (AZTIX3X3PK43B), 36" stair | 6 | $94.86 | $569.16 | count E; price E (interpolated) |
| IRX post kit 48" (AZTIX3X3PK48B): the SOP's tall posts at the bottom of each flight | 4 | $105.22 | $420.88 | count E; price V S2 |
| ADA handrail kit AZTIXADAPR90DRKB (one side per flight; 7 risers each) | 2 | $180.63 | $361.26 | V S1 (add an extension AZTIXADAPREKB $193.48 if the run needs it) |
| FastenMaster HeadLOK 4-1/2" (4 per post) | 40 | $1.29 | $51.60 | V S2 |
| Bottom landing hard surface, 36" min (pavers or concrete; playbook "~$200"; pricebook pad $350 est.) | 1 | $275.00 | $275.00 | E |
| Misc screws (SD9212R100R box + structural screws) | 1 | $60.73 | $60.73 | E |
| Credit: the lower-level rail at the 4' opening (about one 6' level panel) | -1 | $211.35 | −$211.35 | E (the engine adjusts the deck rail) |
| **Option 2 materials** | | | **$9,933.82** | before the 1.15 material factor and tax |

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| Stairs, per riser (GSX card) | 14 | $150.00 | $2,100.00 | V rate S8 |
| Railing, per LF (stair rails about 28 LF + landing guard 17 LF) | 45 | $20.00 | $900.00 | V rate; LF E |
| Frame, per SF (landing 36 SF) | 36 | $10.00 | $360.00 | V rate |
| Decking & fascia, per SF (landing) | 36 | $8.00 | $288.00 | V rate |
| Diamond Pier, per pier | 4 | $50.00 | $200.00 | V rate |
| **Option 2 labor** | | | **$3,848.00** | labor (no material factor or tax) |

- **Option 2 total:** **$9,933.82** materials + **$3,848.00** labor (E counts; prices V except the 43-1/2" posts, the hard surface and misc).
- **Landing posts:** carried as **6x6 DF rough on DP-50 with ABA66RZ bases** (GSX standard; fits the pier's 1/2" bolt). To use **8x8 to match the deck columns**, add about **+$176** for posts (2 × ~$159 vs 2 × $70.98) and about **+$784** for bases (4 custom 8x8 bases ~$225 vs ABA66RZ $28.97). Same Diamond Pier caveat as section 4.2.
- Engine trap: for landing posts that aren't 6x6, the takeoff writes **ABA44Z** bases (takeoff.py, landing loop).
- **Cross-check:** the GS Pricing Sheet's Vintage stair rule ($409 cost per riser incl. $150 labor and "Railing is 2' $100", S7) gives 14 × $409 = $5,726. That is well under the itemized list, because the per-riser rule has no 9' × 4' landing on 4 piers and no IRX on both flights plus a landing guard.

### 6.5 OPTION 3: Suncoast louvered roof (separate document; owner-set $35,000 = $175/SF × 200 SF)

**Suncoast facts** (S22, V):
- 6x6 structural aluminium posts; frames are 2x8 (spans up to 15'), 2x10 (18') or 4x8 (22').
- Blades span up to 14' depending on snow load; Gaposa motor; **Black** is a standard colour.
- Downspouts run **inside the posts** (or outside).
- Optional heaters are 1,600–4,000 W; rain and wind sensors are available.
- **No** deck or house attachment details are published. Get Suncoast's install drawings and **post reactions (down and uplift)**.

**Owner's structure** (brief):
- **Exactly 2 roof posts** on the upper deck's **outer edge, on the rail line**, at about x 29.6 and 49.6, y ≈ 10.
- They **replace the IRX posts** there, and the IRX sections end into them.
- The house side hangs at the **soffit / roof line**, with no posts at the house.

**Loads:** Centennial uses 30 psf non-reducible roof snow and 115 mph wind (S23, V). The outer beam carries about 30 psf × 100 SF ≈ 3,000 lb plus dead load, so about **1,500–1,800 lb down per post**, plus uplift with the louvres closed (E). A rim on the GSX 2' drop-beam cantilever **cannot carry a roof post**. Each roof post needs a **deck post and pier directly under it**, or the 6x10 beam brought out to the rim there. The structure agent decides.

**Open question for the owner or Jade:** are these GSX-side items **inside the $35,000** or added to it? They are listed so they can be priced either way.

| Line | Qty | Unit price | Ext. | Flag / basis |
|---|---|---|---|---|
| 8x8 DF #1 rough x10, a deck post directly under each roof post (if the base frame has none there) | 2 | $199.00 | $398.00 | E (structure agent decides) |
| Diamond Pier DP-75/63 under each (roof + deck load) | 2 | $257.00 | $514.00 | E |
| Custom HDG 8x8 standoff base (DP-75 5/8" bolt) | 2 | $225.00 | $450.00 | E/U (see section 4.2) |
| Simpson ECCQ68SDS2.5 or CCQ68SDS2.5 cap at those posts | 2 | $124.00 | $248.00 | E |
| 2x10x12 TFJ solid blocking / doubled joists under each base plate | 2 | $43.93 | $87.86 | V S1 |
| FastenMaster ThruLOK 8" (24): base plates through decking into the blocking (4 per post) | 1 | $118.51 | $118.51 | V S3 |
| Simpson DTT2Z uplift tie, blocking to the post / beam below (engineer to size) | 2 | $13.81 | $27.62 | V S1 price; spec E |
| Grace Vycor Plus 12" x 75' behind the house attachment | 1 | $73.03 | $73.03 | V S2 |
| Deck ledger / Z flashing 8' over the attachment | 3 | $12.00 | $36.00 | V S2 |
| FastenMaster LedgerLOK 5" (50), wall or ledger mount (if not on Suncoast brackets) | 1 | $77.25 | $77.25 | V S1 |
| Polyurethane sealant | 2 | $12.00 | $24.00 | E |
| Downspout routing from the 2 posts to grade (3" PVC or 2x3 + elbows) | 2 | $80.00 | $160.00 | E |
| IRX Wall Mount Kit AZTIXWBKTKITB, panel ends into the roof posts | 4 | $35.00 | $140.00 | U/E (not quoted) |
| Credit: 2 IRX post kits replaced by the roof posts | -2 | $82.20 | −$164.40 | V S2 |
| **GSX-side materials (worst case)** | | | **$2,189.87** | before the 1.15 material factor and tax |

- If the base frame already has a post and pier under each roof post, Option 3's GSX side shrinks to the **pier upgrade (DP-50 to DP-75, +$91.39 each), blocking, bolts, uplift ties, house flashing, downspout routing and IRX wall-mount kits, less the 2 IRX post credits**: about **$762.65** (E).
- If Option 1 is taken, there are also 2 fewer post-cap lights (−$272).
- Power for the motor (and any heater or lights) is by an electrician (U). The louvered-roof engine agent owns the model (S/fillmore/louvered/).

---

## 7. What the engine is missing for this job

### 7.1 Pricebook: exact entries to add or replace (same shape as the existing ones)

Also **delete** `"TimberTech|Vintage|12|square"`. The product doesn't exist, so the engine should never price it.

```json
{
  "decking": {
    "TimberTech|Vintage|16|square": {"each": 123.04, "source": "D&D quote 979610 (GSEXT1, H. Frederick) 11 Sep 2026 — AZV1616WT; one price for all Vintage colors (English Walnut = ADB15516EW)"},
    "TimberTech|Vintage|20|square": {"each": 153.8, "source": "D&D quote 979610 11 Sep 2026 — AZV1620WT (English Walnut = ADB15520EW)"},
    "TimberTech|Vintage|12|grooved": {"each": 92.28, "source": "EST — 12' x $7.69/LF (D&D 979610); AGB15512EW not quoted"},
    "TimberTech|Vintage|16|grooved": {"each": 123.04, "source": "EST — D&D prices grooved = square (Landmark 1x6x20 sq/grv both $138.60 SO 6622045; Reserve 1x6x20 sq/grv both $112.15 SO 6645370); AGB15516EW"},
    "TimberTech|Vintage|20|grooved": {"each": 153.8, "source": "EST — grooved = square at D&D; AGB15520EW"},
    "TimberTech|Vintage|fascia": {"each": 171.38, "source": "D&D quote 979610 11 Sep 2026 — AZVFASCIA12WT 1/2 x 11-3/4 x 12' (English Walnut = ADR5117512EW)"},
    "TimberTech|Vintage|riser": {"each": 121.69, "source": "D&D quote 979610 11 Sep 2026 — AZVRISER12WT 3/4 x 7-1/4 x 12' (English Walnut = ARISER72512EW)"},
    "TimberTech|Vintage|per_lf": {"each": 7.69, "source": "D&D quote 979610 11 Sep 2026 ($123.04 / 16', $153.80 / 20')"},
    "Cortex_TimberTech_350": {"each": 175.0, "source": "D&D SO 6622045 (GSEXT1) 9 Jul 2026 — CTC100SFDH; English Walnut = CTC100SFEW", "count": 350, "desc": "Cortex for TimberTech Advanced PVC, collated 100 SF (350 screws, 400 plugs, 3 bits), color-matched plugs"},
    "TOPLoc_PVC_fascia_100": {"each": 59.9, "source": "D&D quote 979610 11 Sep 2026 — ATLOCFAS30LT; English Walnut = ATLOCFAS30B (Brown)", "count": 100, "desc": "TimberTech TOPLoc fascia screws for Advanced PVC fascia, 30 LF pack (100 screws, 1 bit), color-matched"}
  },
  "rail": {
    "IRX Baluster|panel|8|level": {"each": 293.91, "source": "D&D SO 6622045 (GSEXT1) 9 Jul 2026 — AZTIX36UNLP8B (CASH50 quote 959545 7 Jul 2026: $275.52)", "desc": "TimberTech Impression Rail Express 36\" 8' level universal panel kit, 20 vertical aluminum balusters, bottom rail cover, foot block, brackets (top rail not incl.), {color}"},
    "IRX Baluster|panel|6|level": {"each": 211.35, "source": "D&D SO 6622045 9 Jul 2026 — AZTIX36UNLP6B", "desc": "TimberTech Impression Rail Express 36\" 6' level universal panel kit, 15 vertical aluminum balusters, bottom rail cover, foot block, brackets (top rail not incl.), {color}"},
    "IRX Baluster|panel|8|stair": {"each": 227.5, "source": "D&D SO 6622045 9 Jul 2026 — AZTIX36UNSP8B", "desc": "TimberTech Impression Rail Express 36\" 8' stair universal panel kit, 20 balusters, panel cover, foot block, hardware (top rail not incl.), {color}"},
    "IRX Baluster|panel|6|stair": {"each": 163.59, "source": "EST — 8' stair $227.50 x (6'/8' level 211.35/293.91); AZTIX36UNSP6B not quoted", "desc": "TimberTech Impression Rail Express 36\" 6' stair universal panel kit, 15 balusters (top rail not incl.), {color}"},
    "IRX Baluster|post|END": {"each": 82.2, "source": "D&D SO 6622045 9 Jul 2026 — AZTIX3X3PK38B"},
    "IRX Baluster|post|LINE": {"each": 82.2, "source": "D&D SO 6622045 9 Jul 2026 — AZTIX3X3PK38B"},
    "IRX Baluster|post|CORNER": {"each": 82.2, "source": "D&D SO 6622045 9 Jul 2026 — AZTIX3X3PK38B"},
    "IRX Baluster|post|STAIR": {"each": 94.86, "source": "EST — AZTIX3X3PK43B (43-1/2\" post for a 36\" stair) interpolated between D&D 38\" $82.20 and 48\" $105.22 (SO 6622045)"},
    "IRX Baluster|post_kit": {"each": 82.2, "source": "D&D SO 6622045 9 Jul 2026 — AZTIX3X3PK38B (CASH50 quote 959545: $86.11)", "desc": "TimberTech Impression Rail Express 3\" x 3\" x 38\" post kit (post, cap, skirt) for a 36\" rail, {color}"},
    "IRX Baluster|post_kit|48": {"each": 105.22, "source": "D&D SO 6622045 9 Jul 2026 — AZTIX3X3PK48B", "desc": "TimberTech Impression Rail Express 3\" x 3\" x 48\" post kit (post, cap, skirt), {color}"},
    "IRX Baluster|top_rail|8": {"each": 91.7, "source": "D&D quote 979610 11 Sep 2026 — Classic AZTIXCSTR8B (Modern AZTIXMDTR8B not quoted)", "desc": "TimberTech Impression Rail Express top rail 8' (Classic; Modern priced alike — confirm), {color}"},
    "IRX Baluster|top_rail|6": {"each": 76.94, "source": "D&D quote 979610 11 Sep 2026 — Classic AZTIXCSTR6B (Modern AZTIXMDTR6B not quoted)", "desc": "TimberTech Impression Rail Express top rail 6' (Classic; Modern priced alike — confirm), {color}"},
    "IRX Baluster|panel_cover|8": {"each": 45.0, "source": "EST — AZTBULKIXBR8B not quoted; Henry to quote", "desc": "TimberTech Impression Rail Express 8' universal panel cover for drink rail (replaces the top rail), {color}"},
    "IRX Baluster|panel_cover|6": {"each": 36.0, "source": "EST — AZTBULKIXBR6B not quoted; Henry to quote", "desc": "TimberTech Impression Rail Express 6' universal panel cover for drink rail (replaces the top rail), {color}"},
    "IRX Baluster|handrail_kit": {"each": 180.63, "source": "D&D quote 979610 11 Sep 2026 — AZTIXADAPR90DRKB ADA pipe rail + 90-degree return kit (extension AZTIXADAPREKB $193.48)", "desc": "TimberTech Impression aluminum ADA graspable handrail, pipe rail + 90-degree return kit, {color}"},
    "IRX Baluster|accessory_kit": {"each": 38.09, "source": "D&D quote 979610 11 Sep 2026 — AZTIXACCKITB", "desc": "TimberTech Impression Rail Express touch-up paint + bracket jig, {color} (at least 1 per job)"},
    "IRX Baluster|post_insert_8": {"each": 40.0, "source": "EST — AZTIX3X3PPLG not quoted (over-the-post drink rail only)", "desc": "TimberTech Impression Rail Express drink-rail 3\" post insert, 8-pack"}
  },
  "hardware": {
    "irx baluster_drink_rail_bracket_kit": {"each": 63.5, "source": "D&D SO 6622045 (first issue) 9 Jul 2026 — AZTIXDRCKITB $127.00 per 12 clips; the takeoff orders one per bay, so priced per 8' bay (6 clips)", "desc": "TimberTech Impression Rail Express drink rail clips + screws, black — 6 per 8' bay / 4 per 6' bay (kit AZTIXDRCKITB = 12 clips)"},
    "LUS210Z": {"each": 2.43, "source": "D&D quote 979610 11 Sep 2026", "desc": "Simpson LUS210Z face-mount hanger 2x10/2x12"},
    "HUC210-2Z": {"each": 37.96, "source": "D&D quote 979610 11 Sep 2026 — HUC2102-2Z (D&D does not quote HUCQ210-2-SDS)", "desc": "Simpson HUC210-2Z concealed-flange double 2x10 hanger"},
    "H2.5AZ": {"each": 0.83, "source": "D&D quote 979610 11 Sep 2026", "desc": "Simpson H2.5AZ hurricane tie (joists to the drop beam, hidden)"},
    "LSCZ": {"each": 2.93, "source": "D&D quote 979610 11 Sep 2026", "desc": "Simpson LSCZ adjustable stair-stringer connector"},
    "DTT1Z": {"each": 4.86, "source": "D&D SO 6622045 9 Jul 2026", "desc": "Simpson DTT1Z lateral tie kit w/ SDS screws"},
    "DTT2Z": {"each": 13.81, "source": "D&D quote 979610 11 Sep 2026", "desc": "Simpson DTT2Z deck tension tie"},
    "gtape_2": {"each": 18.6, "source": "D&D quote 979610 11 Sep 2026 — GT265DFT", "desc": "Nichigo G-Tape 3035 2\" x 65' black", "lf": 65},
    "gtape_4": {"each": 36.6, "source": "D&D quote 979610 11 Sep 2026 — GT465DFT", "desc": "Nichigo G-Tape 3035 4\" x 65' black", "lf": 65},
    "gtape_9": {"each": 84.17, "source": "D&D quote 979610 11 Sep 2026 — GT965DFT", "desc": "Nichigo G-Tape 3040 9\" x 65' black w/ liner (6x beam tops)", "lf": 65},
    "CCQ68SDS2.5": {"each": 124.0, "source": "EST — retail $123.99 (toolnut.com, 27 Oct 2026); not on a D&D quote", "desc": "Simpson CCQ68SDS2.5 column cap, 6x beam on 8x post (SDS screws incl.)"},
    "ECCQ68SDS2.5": {"each": 124.0, "source": "EST — retail $123.99 (toolnut.com, 27 Oct 2026); not on a D&D quote", "desc": "Simpson ECCQ68SDS2.5 end column cap, 6x beam on 8x post (SDS screws incl.)"},
    "CCQ68SDS2.5_W2-8": {"each": 150.0, "source": "EST — custom W2 = 8\" for a rough 8x8 (Simpson: optional W2 may be specified); confirm price + lead time", "desc": "Simpson CCQ68SDS2.5 column cap, W2 = 8\" (rough 8x8 post)"},
    "HeadLOK4.5_each": {"each": 1.29, "source": "D&D SO 6622045 9 Jul 2026 — 412HL", "desc": "FastenMaster HeadLOK 4-1/2\" (each) — IRX post bases into blocking"},
    "ThruLOK8_24": {"each": 118.51, "source": "D&D SO 6645370 15 Jul 2026 — FMTHR008-24", "desc": "FastenMaster ThruLOK 8\" (24 ct)", "count": 24}
  },
  "footings": {
    "DP-50/50": {"each": 165.61, "source": "D&D quote 979610 11 Sep 2026 — DP1000 'Diamond Pier Deck Footing DP50' (pin length not on the line: confirm 50\")", "desc": "Diamond Pier DP-50/50 (10x10x11 head, 1/2\" anchor bolt, 4 x 50\" pins, plugs, caps)", "capacity_lb": 3300, "capacity_source": "PFI Residential Load Chart DOC0008 (2018), 1500 psf silts/clays (4400 lb in 2000 psf sands/gravels)"},
    "DP-75/63": {"each": 257.0, "source": "EST — D&D DP-50 $165.61 x 1.55; Henry to quote", "desc": "Diamond Pier DP-75/63 (11x11x12 head, 5/8\" anchor bolt, 4 x 63\" 1-1/4\" pins, plugs, caps)", "capacity_lb": 4200, "capacity_source": "PFI Residential Load Chart DOC0008 (2018), 1500 psf silts/clays (6400 lb only in 2000 psf sands/gravels)"},
    "ECB88HDG": {"each": 157.0, "source": "EST — retail ECB88 $156.99 (toolnut.com, 27 Oct 2026)", "desc": "Simpson ECB88HDG elevated column base 8x8 (S4S 7-1/2\"), single 1/2\" center anchor option — on a DP-50 bolt only with PFI/engineer acceptance"},
    "ABU88RZ": {"each": 87.0, "source": "EST — retail $86.99 (toolnut.com, 27 Oct 2026)", "desc": "Simpson ABU88RZ adjustable standoff post base, rough 8x8 — needs (2) 5/8\" anchors: concrete footings only, NOT a single-bolt Diamond Pier"},
    "DP_base_8x8_custom": {"each": 225.0, "source": "EST — fabricated HDG standoff base for an 8x8 on the DP-75 5/8\" bolt; PFI + engineer to approve", "desc": "Custom HDG 8x8 standoff post base, single 5/8\" anchor (Diamond Pier DP-75)"}
  },
  "lumber": {
    "2x10": {"per_lf": 3.88, "source": "D&D quote 979610 11 Sep 2026 (2x10x12 $43.93 / x16 $62.03 / x20 $81.55)"},
    "2x12": {"per_lf": 4.82, "source": "D&D quote 979610 11 Sep 2026 (2x12x16 $77.06); SO 6645370 2x12x12 $52.86 / x20 $98.24"},
    "2x6": {"per_lf": 1.83, "source": "D&D quote 979610 11 Sep 2026 (2x6x12 #1 KDAT GC $21.90)"},
    "2x4": {"per_lf": 1.14, "source": "D&D quote 979610 11 Sep 2026 (2x4x12 #1 KDAT GC $13.68)"},
    "8x8_DF#1": {"per_lf": 19.85, "source": "EST — $3.72/BF from D&D 6x6x10 DF RGH $111.64 (SO 6645370, 15 Jul 2026); Henry to quote 8x8 DF #1 rough 8/10/12"},
    "6x10_DF#1": {"per_lf": 18.6, "source": "EST — 5 BF/LF x $3.72/BF (D&D 6x6x10 DF RGH); Henry to quote"}
  },
  "lighting": {
    "_note": "new section — the takeoff has no Lighting category yet; watts per TimberTech 150W PowerPack chart (post cap 4 W, riser 2 W); 100W transformer: 90 W max load, 60 W max per run",
    "AZTDL3X3LANCAPB": {"each": 136.0, "source": "EST — TimberTech 3\" LED Lantern Post Cap (IRX); Lumbermens list 4\" lantern $135.69 eff. 1 Jun 2026; not on a D&D quote", "desc": "TimberTech 3\" LED Lantern Post Cap Light for Impression Rail Express, Black, 12V, 2700K", "watts": 4},
    "AZTDLRECRISERMB": {"each": 88.24, "source": "EST — Lumbermens list eff. 1 Jun 2026 (The Deck Store $94.99); not on a D&D quote", "desc": "TimberTech Recessed LED Riser Light, Matte Black, 12V, 2700K, 6' lead", "watts": 2},
    "AZTDL100TRAN": {"each": 135.15, "source": "EST — Lumbermens list eff. 1 Jun 2026 (The Deck Store $137.99)", "desc": "TimberTech 100W 12V transformer with photocell + timer (90 W max load, 60 W max per run)", "watts_max": 90},
    "AZTDL150PPR": {"each": 373.95, "source": "EST — Lumbermens list eff. 1 Jun 2026 (The Deck Store $301.99)", "desc": "TimberTech 150W PowerPack / dimmer transformer with remote, timer, photo eye (GFCI hooded receptacle required)"},
    "AZTDLLEDWIRE": {"each": 112.13, "source": "EST — Lumbermens list eff. 1 Jun 2026", "desc": "TimberTech 16/2 AWG low-voltage wire, 100'", "lf": 100},
    "wirenut_silicone_25": {"each": 20.0, "source": "EST", "desc": "Silicone-filled outdoor wire nuts, 25 pk"}
  },
  "labor": {
    "lighting_fixture_each": 50.0,
    "lighting_transformer_each": 175.0,
    "_lighting_note": "EST market basis — no lighting line on GSX_Subcontractor_Labor_Rates (checked 27 Oct 2026)"
  }
}
```

### 7.2 Code-level gaps (catalog / takeoff / layout): no JSON can fix these

1. **Vintage lengths.** `STOCK_LENGTHS_FT = [12, 16, 20]` is global. As a result the engine writes "**Vintage … 1x6x12 Square Edge**" for several lines:
   - field packing (takeoff.py line 289)
   - rips at the house (12' stock on non-timber jobs, line 1001)
   - stair treads (line 1021)
   - landing decking (line 793)
   - benches, planters, door step (lines 1044–1101)
   
   None of these boards exist. Add per-collection, per-profile lengths: `DECKING["Vintage"]["lengths"] = {"square": [16, 20], "grooved": [12, 16, 20]}`. The skill catalog already says "SS 16/20; grooved 12/16/20".
2. **8x8 on Diamond Piers.** `POST_BASE` has no "8x8", so the takeoff falls back to ABA66Z / ABA66RZ (takeoff.py lines 748–751). Stair-landing posts that aren't 6x6 get **ABA44Z** (takeoff.py line 789). See section 4.2 for what to use.
3. **DP-75/63 capacity** is 6,000 lb in both catalog.py line 133 and the pricebook. It should be **4,200 lb at 1,500 psf** (S16); the auto-upgrade in layout.py lines 678 and 1404 depends on it.
4. **Caps.**
   - Dimensional mode puts the same cap at every post (layout.py line 1381), so **CCQ68 lands at beam ends** where it should be ECCQ68.
   - `POST_CAP_SCREWS` lacks CCQ / ECCQ, so 10 SD screws per cap get ordered even though the caps ship with their own.
   - There is no rough-8x8 (W2 = 8") variant.
   - The post line reads "8x8x.. Douglas Fir #1 timber (**S4S**, end grain sealed) **rough**" (takeoff.py line 669), which contradicts itself.
5. **IRX Baluster post spacing.** The single-zone `rail_layout` allows up to 94 + 3 + 0.5 = **97.5" post spacing** (layout.py lines 704 and 761). TimberTech's maximum is 96". The panel stock values `{72: 70.0, 96: 94.0}` are longer than the actual panels (69.43" / 91.31", S15). `rail_layout_edges` correctly uses `max_ctc = 96`.
6. **Drink rail on IRX.**
   - The takeoff adds the **top rail** (takeoff.py line 1232) **and** the drink-rail board. It should swap the top rail for the **Universal Panel Cover** (AZTBULKIXBR8B / 6B).
   - It orders one clip kit **per bay** (lines 1271–1272), but a kit holds 12 clips: 6 per 8' bay, 4 per 6' bay.
   - `spec.Railing` has no over-the-post / between-the-post choice and no post inserts.
7. **IRX stair sections get no top rail line** (the stair loop only adds panels and posts). Stair **posts** are priced as 38" posts; a 36" stair needs **43.5"** (AZTIX3X3PK43B).
8. **Cortex mode drops two screw counts.** It sets `face = 0; stair_face = 0` (takeoff.py lines 1155–1179). On a Cortex job **no fascia screws** (TOPLoc) and **no stair-tread or riser Cortex** get ordered. The fascia screw pattern (layout.py line 422) is also the composite pattern; Vintage fascia takes TOPLoc fascia screws in Brown.
9. **Rail-system naming.** `RAIL_SYSTEMS["Impression Rail Express"]` is the cable system (catalog.py line 169). Use "IRX Baluster".
10. **Not modeled:** lighting (no category, lines or transformer sizing); the inset-stair notch; vertical PVC fascia cladding; louvered-roof post blocking.
11. **Smaller items.**
    - `DOUBLE_HANGER` = HUCQ210-2-SDS, which D&D doesn't quote; D&D quotes **HUC2102-2Z** at $37.96.
    - IRX touch-up is the TimberTech **AZTIXACCKITB** ($38.09), not the $8 Rust-Oleum line.
    - The pricebook IRX Baluster prices came from the **CASH50** quote, not GSEXT1.
    - `jobs/parkview_deck.json` labels TOPLoc as Cortex.

---

## 8. Summary

**Key prices** (GSEXT1 unless noted; V unless marked E):

| Category | Line | Price |
|---|---|---|
| Vintage | 1x6 square 16' / 20' | **$123.04 / $153.80** ($7.69/LF), quote 979610, 11 Sep 2026 |
| | 12' grooved | ~$92 (E) |
| | **No 12' square and no 24'** | — |
| | Fascia 1/2 x 11-3/4 x 12' | **$171.38** |
| | Riser | **$121.69** |
| Fasteners | Cortex PVC 100 SF collated (CTC100SFEW, EW plugs) | **$175.00** |
| | TOPLoc fascia (ATLOCFAS30B, Brown) | **$59.90** |
| IRX Black | 8' / 6' level panel | **$293.91 / $211.35** |
| | 8' stair panel | **$227.50** |
| | 38" / 48" post | **$82.20 / $105.22** |
| | 43.5" stair post | ~$94.86 (E) |
| | Drink-rail clip kit (12 clips) | **$127.00** |
| | Classic top rail 8' / 6' | **$91.70 / $76.94** |
| | ADA handrail parts | **$100.24 / $35.82** |
| | Touch-up kit | **$38.09** |
| | Panel cover | ~$45 (E) |
| Framing | 2x10 TFJ x12 / x16 / x20 | **$43.93 / $62.03 / $81.55** |
| | 2x12 TFJ x12 / x16 / x20 | **$52.86 / $77.06 / $98.24** |
| | G-Tape 2" / 4" / 9" | **$18.60 / $36.60 / $84.17** |
| | LUS210Z | **$2.43** |
| | DTT1Z / DTT2Z | **$4.86 / $13.81** |
| Footings | DP-50 | **$165.61** |
| | DP-75/63 | ~$257 (E) |
| Caps | CCQ68SDS2.5 / ECCQ68SDS2.5 | ~$124 each (E, retail) |
| Timbers | 8x8 DF #1 rough | ~$19.85/LF (E) |
| | 6x10 DF #1 | ~$18.60/LF (E) |
| Lighting (E, list) | 3" IRX lantern post cap | ~$136 |
| | Recessed riser, black | $88.24 |
| | 100 W transformer | $135.15 |
| | 150 W PowerPack | $373.95 |
| | 16/2 wire, 100' | $112.13 |
**Bid roll-ups** (section 6; materials before the 1.15 factor and tax; counts E):

| Bid part | Materials | Labor | Notes |
|---|---|---|---|
| BASE add-ins: step-face skirt + inset stair | **$2,344.49** ($876.83 + $1,467.66) | **$850** (stairs 5 × $150 + skirting $100) | the deck, rail, drink rail and demo come from the engine run |
| OPTION 1: lighting, base deck + inset stair (about 17 post caps, 5 risers, one 100 W) | **$3,152.61** | **$1,275** (E) | + $250–450 if a GFCI in-use receptacle must be added |
| OPTION 1 add-on: yard-stair lighting (14 risers, about 10 post caps, a second 100 W) | **$2,862.64** | **$1,375** (E) | only with Options 1 + 2 |
| OPTION 2: yard stair (2 flights, 14 risers, 9' × 4' landing on 4 DP-50s, IRX both sides) | **$9,933.82** | **$3,848** (GSX card rates) | 8x8 landing posts instead of 6x6: about +$960 |
| OPTION 3: louvered roof, GSX-side items only | **$2,189.87** worst case / **$762.65** if the base frame has posts there | — | Suncoast roof itself is owner-set at $35,000: confirm whether these are inside it |

**Gaps and flags to act on:**
0. **Bid structure:** base, Options 1–3 and the yard-stair lighting add-on each have their own list in section 6, so each can be priced on its own.
1. **Every quote expired the day it was issued.** Re-quote, and get the E items quoted: 8x8 and 6x10 DF, DP-75, CCQ68 / ECCQ68, the IRX panel cover, post insert, 6' stair panel and 43.5" post, Cortex 300 SF, and the lighting.
2. **The 8x8-to-Diamond-Pier connection is unresolved.** There is no ABA88Z; every Simpson 8x8 base needs 2 anchors except the ECB88 (1/2" centre anchor, 7-1/2" only); the DP plinth is 5-5/8". Jade, PFI and an engineer need to pick one. The engine also uses the wrong DP-75 capacity (6,000 lb instead of 4,200 lb at 1,500 psf) and has no 8x8 DP base.
3. **CCQ68 / ECCQ68 is the cap**, with W2 = 8" if the posts are full rough. BC8 and CCQ88 are 8x-beam caps and don't fit a 6x beam.
4. **Engine fixes needed:**
   - Vintage 12' square boards that don't exist
   - drink rail doubled with the top rail, and clip kits per bay
   - IRX stair posts and stair top rails
   - Cortex mode dropping the fascia and stair screws
   - "Impression Rail Express" mapping to cable
   - IRX post spacing up to 97.5" in single-zone layouts
5. **Owner decision:** post-cap lights on every post require a **between-the-post** drink rail.
6. **Lighting:** size from the post count with W = 4 × posts + 2 × risers, using ≤ 90 W per 100 W transformer and ≤ 60 W per run. A GFCI hooded receptacle is required. There is no GSX labor rate: about $50 per fixture plus $150–200 per transformer (E).
7. **Louvered roof:** the owner wants **2 roof posts on the upper rail line** that replace IRX posts, with the house side at the soffit. Get Suncoast's post reactions and attachment detail. GSX supplies:
   - a **deck post and pier directly under each roof post** (likely DP-75/63)
   - blocking, through-bolts and uplift ties
   - IRX wall-mount kits where the rail meets the roof posts (and credits 2 IRX posts)
   - house flashing (Vycor, ledger / Z flashing, sealant)
   - the downspout discharge from the 2 posts
