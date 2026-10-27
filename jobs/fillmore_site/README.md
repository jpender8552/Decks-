# 7303 S Fillmore Cir, Centennial CO 80122: site research for the deck replacement

Researched 2026-10-26/27 (owner first name Andie). Status tags: **V** = verified from the cited public source; **E** = estimated or derived (method and tolerance given); **U** = unverified or third-party.

Short names used below:
- `AC` = https://gis.arapahoegov.com/arcgis/rest/services/ArapaMAP/MapServer (Arapahoe County ArapaMAP)
- `DEM` = https://gis.arapahoegov.com/arcgis/rest/services/County_DEM/ImageServer (county LiDAR DEM)
- `CEN` = https://maps.centennialco.gov/arcgis/rest/services (City of Centennial GIS)
- `ASR` = https://parcelsearch.arapahoegov.com/PPINum.aspx?PPINum=2077-25-3-08-024 (assessor record)
- Site photos = `../fillmore_photos/all/u01..u20` (taken 2026-10-26; phone GPS is 15-25 m off, so it was not used)

Every URL used is listed in section 13. Raw responses are in `downloads/`, my scripts are in `scripts/`, and intermediate views are in `work/`. No downloaded file was executed.

**Other agents share this folder.** This research owns `README.md` and the files listed in section 14 only. The plan frame here and the BRIEF.md frame differ only by an x-offset: **x_brief = x + 7.583**. Both have y = 0 on the main rear wall and +y into the yard. The BRIEF frame puts x = 0 at the arm's open side.

---
## 1. Location and jurisdiction
| Item | Value | Status / source |
|---|---|---|
| Address point | lat **39.5843223**, lon **-104.9523515** (EPSG:2232 E 3154351.79, N 1638182.98); ZIP 80122-1942 | V, AC layer 2 |
| Jurisdiction | **City of Centennial** (incorporated), not unincorporated Arapahoe County. Council District 2. | V, AC 375/140 `JURISDICTION=CENTENNIAL`; CEN Parcels; AC 352 (unincorporated zoning) returns nothing |
| Building department | City of Centennial Building Division, 13133 E Arapahoe Rd, Centennial CO 80112, 303-325-8000, buildingdivision@centennialco.gov. Permits go through EnerGov self-service. | V, deck handout copy and permit links |
| Fire / school / water / sanitation | South Metro Fire Rescue; Littleton SD 6; South-East Englewood Water District; South Arapahoe Sanitation; SEMSWA stormwater | V, AC 355/353, CEN Special_Districts 1-9 |
| FEMA flood | **Zone X (area of minimal flood hazard)**, DFIRM 08005C, FLD_AR_ID 08005C_3623 | V, AC 380 |
| Nearby floodplain | Rear lot line backs onto the Big Dry Creek greenbelt. City FHAD 100-yr floodplain is **13.3 ft** beyond the parcel and **26.5 ft** from the deck (ground about 5558). FEMA AE floodway is 16.9 ft from the parcel and 30 ft from the deck. The EnerGov floodplain-review flag for this parcel is "N/A (20261026)". | V for the layers, E for distances (GIS lines, +/-3 ft) |
| Wildfire / WUI | **Not WUI** (`WUI=No`). No county Wildfire Resiliency, city Fire Intensity or Fire Structure Risk feature at the parcel. | V, CEN Parcels and Energov 28; AC 431; CEN Fire_Intensity_Classification; Hosted/Fire_Structure_Risk 1-3 |
| Airport influence area | none | V, CEN Airport_Influence_Area |
| Soils | **BxC Buick loam, 3-5% slopes** (consociation; prime farmland if irrigated) | V, AC 389/390 |
| Ground elevation | **5570 ft** NAVD88 at the address point (DEM pixel 5570; bilinear 5570.1). The roof-print attribute says 5565 (2020/2022 layers) or 5569 (2018). | V, DEM identify; AC 64/65/66 |
| Sales tax (destination) | **6.75%** = state 2.90 + RTD 1.00 + SCFD 0.10 + Arapahoe County 0.25 + Centennial 2.50 | V, AC 385 and salestaxrates.pdf ("2026 combined", updated 01/2026) |

## 2. Parcel and house (assessor)
| Item | Value | Status |
|---|---|---|
| AIN / Parcel ID | **2077-25-3-08-024** | V, AC 276, ASR |
| PIN | **032153377** | V |
| Legal | **Lot 24 Blk 1 Knolls South 1st Flg**. Subdivision plat reception **R1658716**. | V, ASR; AC 151, CEN Subdivisions |
| Owner of record | **Alison C Kelman Trust**, sole ownership. Mailing address 1091 E Bayaud Ave Unit W3108, Denver CO 80209-2742. | V, ASR |
| Owner name check | "Andie" does not appear in the public record. The city also lists a business entity "Kelman Properties LLC" (2021). Confirm who signs the contract, the permit and the HOA request, since a trust holds title. | U |
| Deed of record | **D8011923**, deed date 01-29-2018 (GIS sale date 2018-02-05), $0, a non-sale transfer. Prior entries: D4102961 10-30-2014 $0; **D4098916 10-17-2014 $585,000**; B6094003 06-21-2006 $448,000; B2052326 2002 $0; A7079455 1997 $0; 1993 $0; 1989 $168,000 and $195,000; 1986 $195,000; 1985 $199,000; 12-01-1980 $161,600 (new). | V, ASR sale list |
| 2026 value | Appraised $901,100 (building $626,100 + land $275,000). Assessed $56,515. 2025 mill levy 114.997. | V |
| Lot area | **8,544.8 sf GIS (0.196 ac)**. Assessor acreage is 0.2030 ac (8,843 sf). Layer 280 GIS_AREA2 is 8,676.7. | V |
| Neighborhood / use | Knolls South (1413); Single Family (PUC 1212), "Traditional" | V |
| Year built | **1981**, effective 1981. **Remodel year 2012.** | V, ASR; AC 280 |
| Style / stories | **Multi-Level** (split-level). The assessor's "Floors" field is 0.00. The MLS says "Stories 2". | V (assessor); U (MLS) |
| Quality / construction | Good (B); "D - Wood or Steel Studs Frame" | V |
| Exterior wall per assessor | **Masonry Veneer** | V. Observed: tan/red brick veneer (lower level, chimney, columns) plus painted vertical wood siding (E from site photos; the listing also says "Brick, warm wood siding") |
| Roof per assessor | **"Wood Shake/Shingle Roof"**. **This record is out of date (flag).** The 2006 assessor photo shows shakes. A re-roof permit (CEN-06-03574) was applied for 2006-10-29. The roof today is dimensional asphalt shingles. | V record; V current roof (MLS front photo); E (site photos u06, u14, u18) |
| Areas | 1st floor **1,663 + 82** (the 82 is a 2 x 41 ft strip along the rear wall at zones B/C); 2nd floor **1,064**; above-grade total **2,809**; basement **822** (819 finished; walkout per MLS); attached garage **552**; covered front porch 144; patio/terrace 40 (20 x 2, under the rear strip) | V, ASR area table; sketch vectors decoded in `assessor_sketch_vectors.json`, every area matches the table |
| Beds / baths | 4 bedrooms / 5.00 baths (assessor). The MLS says 4 beds, 4 baths. | V (assessor); U (MLS) |
| Heat / cooling / fireplaces | Forced air / central air / 1 fireplace (the brick chimney on the arm) | V |
| **Deck records** | **DCK 578 sf**: a 48 x 10 strip along the rear plus the 7 x 14 arm extension that runs back to the arm's door wall. **DCK 156 sf**: 13 x 12 at the WNW end (zone D, where the wall is set back 2 ft). Rear deck total **734 sf**. A third record, **DCK 70 sf** (14 x 5), is the front primary-suite balcony over the garage and is not part of this job. | V, ASR table and sketch (`assessor_sketch.jpg`) |
| Assessor sketch geometry | Rear deck (whole feet): arm 7 wide x 24 from the outer edge to the door wall; B+C 41 x 10 along the 2-ft rear strip; D 13 x 12 with its wall 2 ft back. Outer edge total **61 ft**. The second floor overhangs the last 3 ft of the arm. The sketch top is the rear (NNE) and the arm is on the right of the sketch (ESE). | V (sketch string) |
| Street photo | `assessor_photo_2006.jpg`. The date stamp reads 2006 (day and month not legible). It shows the front and the old shake roof. | V |
| MLS front photo | `listing_MLS6803070_front.jpg` | V (public listing photo) |

## 3. Permit history (Centennial EnerGov, CEN History_EPL, 10 records)
| Date applied | Case | Work class |
|---|---|---|
| 2006-10-29 | CEN-06-03574 | Roof/Re-roof |
| 2010-03-10 | CEN-10-00890 | AC/Water Heater/Furnace |
| 2018-11-08 | RONE-18-03659 | AC/Water Heater/Furnace (issued 11/28/2018, Complete) |
| 2020-01-10 | RONE-20-00105 | Windows/Doors |
| 2026-04-10 | RONE-26-01113 | AC Replacement |
| 2021-12-05 | Kelman Properties LLC | business license entity (LLC) |
| 2021-12-06 / 2024-01-09 / 2024-11-25 / 2025-10-18 | STR-000026-2021, STR-000114-2024, STR-000262-2024 (2 records) | **Short-term rental** licenses (in jurisdiction) |

- **No deck permit is on record** (V).
- The earliest city record for this parcel is from 2006 (Centennial incorporated in 2001). The deck is visible in every ortho back to **1998**, so it predates them (V imagery). County layer 423 (unincorporated residential permits) is empty here.
- Each case links to `https://cityofcentennialco-energovweb.tylerhost.net/apps/selfservice#/permit/<CASEID>`, a JavaScript app that was not opened.

## 4. Zoning, setbacks, deck rules, HOA, code
**Zoning: NC6, Neighborhood Conservation, 6,000 sf minimum** (V, CEN Planning/Official_Zoning/MapServer/0, Code_Year 2011; same on CEN Parcels).
- Setbacks (V, zoning-layer attributes): front **20 ft**; street side 10; side **5 ft**, total sides **12 ft**; rear **20 ft**.
- Maximum height 30 ft; maximum building coverage 37%; minimum lot width 60 ft.

**Deck encroachments: LDC Table 12-3-601 and Sec. 12-3-604.**
- Source: third-party mirror https://www.zoneomics.com/code/centennial-CO/chapter_3 (saved in `downloads/zoneomics_centennial_ch3.html`). **U.** The official pages at centennialco.gov and Municode returned HTTP 403 in this session. Confirm with Centennial Planning.
- **Rear setback, "Decks, four feet or more above grade; balconies":** (A) 12 ft from the setback line toward the lot line; (B) 5 ft from the lot line, subject to 12-3-604. Rule B.2 says the larger distance from the lot line controls.
  - Result: **a deck 4 ft or more above grade must stay at least 8 ft (20 - 12) from the rear lot line.**
  - This deck is about 7-11 ft above grade, so it is in this category.
- Rear setback, decks under 4 ft above grade: 3 ft from the lot line.
- **Side setback:** only "Decks, less than four feet above grade" may encroach: 3 ft from the side lot line, or 0 ft if the adjacent lot is permanent open space. **Decks 4 ft or more above grade get no side encroachment**, so they must meet the 5 ft side setback.
- **Steps 4 ft or less above the point of measurement, needed for access** (all setbacks): (A) 5 ft from the setback line. In this rear yard that means at least **15 ft from the rear lot line**.
  - **Flag for the yard-stair option (BRIEF option 2):** the deck's outer edge is already only 12.8-14.1 ft from the rear lot line. A stair going down from it toward the yard falls inside that 15 ft line. Get Centennial Planning to rule on whether the stair and landing count as "deck at least 4 ft" (8 ft limit) or "steps" (15 ft limit) before it is priced as buildable. U.
- Table notes: no encroachment into utility easements or onto abutting property. **Easements are unknown.** Get the plat, reception R1658716 (link in section 13; not downloaded).
- Sec. 12-3-604:
  - No deck surface may be higher than the second-floor level. OK here: the deck is at main-floor level.
  - Decks reached from upper floors may not sit on the *sides* of a building within 15 ft of a side lot line if they open a view into an abutting single-family back yard. The arm is inside a rear notch, and the ESE neighbor parcel is the HOA tract, so this should not apply. U.
  - Patios may cover up to 60% of the rear yard.
- Alternative rear setback for lots that back onto permanent open space (Sec. 12-3-302 F.2): this applies to buildings (reductions up to 50%/30%) and is not needed for the deck. U.

**HOA: Tiffany HOA**, registered, **mandatory** membership (V, CEN Parcels `HOA`; CEN HOAs layer `HOA_CA=MAND`, link http://www.tiffanyhoa.org/).
- Mail: PO Box 3392, Centennial CO 80161. Email: contact@tiffanyhoa.org. Managed through PayHOA. (V, HOA website)
- ACC members listed on the website (V):
  - Tom Gardinier, 720-937-7408, t_gardinier@yahoo.com
  - Jon Wisson (ACC and HOA Board), 720-635-6524, jwisson@comcast.net
  - Steve Jenkins, sjenk112@aol.com
  - Doug Coventry (ACC approvals), 303-515-0263, douglascoventry@aol.com
- The ACC request form `projectrevform-rev13.docx` lists Tim Carter (720-839-1440, TimCarter80122@gmail.com) and Doug Coventry (V). The county HOA layer still shows "Wood, Tom (303) 721-8412" (U, probably stale).
- The MLS lists "HOA 420" with no period given (U).
- Rules from the ACC Governing Master Document, board-approved 17 June 2026 (`downloads/tiffany_hoa_acc_governing_2026-06-17.pdf`, V):
  - Decks and patios are "structure additions" and need written ACC approval **before work starts**.
  - Submit the official request form at least **3 weeks** ahead, with drawings, color and material samples. Allow up to 3 weeks for the response.
  - Materials and colors must match the existing home.
  - Contact potentially impacted neighbors before submitting.
  - The homeowner must get the city permit, plus any variance before ACC approval.
  - Request a final ACC review after completion and final inspections.
  - Board permission is needed if a project abuts the HOA perimeter fence or park. This lot abuts the HOA tract on the ESE side and the SSPRD greenbelt at the rear. The deck itself is 12+ ft from both.
  - The "Backyard structures" section also requires 811 locates.

**Adopted code: 2021 IRC with Centennial amendments, Ordinance 2023-O-06** (V, from `downloads/centennial_ord_2023-O-06_copy_from_prentice_job_2026-10-25.pdf`).
- About the copy: the prior job downloaded it from centennialco.gov on 2026-10-25. Today centennialco.gov returns an Akamai 403. Whether the city has since adopted 2024 codes could not be checked (U).
- **R105.2 item 10 is deleted**, so every deck needs a permit.
- **R109.1.1:** foundation and pier inspections are made by a Colorado-licensed PE or architect, who provides a stamped report.
- **R401.2:** where soils reports show the need, foundations must be designed and stamped by a Colorado design professional.
- Table R301.2(1) (V, ordinance page 7):

| Criterion | Value |
|---|---|
| Ground snow load | 30 psf |
| Wind | 115 mph (no topographic effect, special wind region or debris zone) |
| Seismic Design Category | B |
| Weathering | Severe |
| **Frost depth** | **36 in** |
| Termite | Slight to moderate |
| Winter design temperature | 1 deg F |
| Ice barrier | Yes |
| FIRM date | 08/01/97 |
| Air freezing index | 1000 |
| Mean annual temperature | 45 deg F |

**City deck handout "Residential Uncovered Decks & Porches"** (V, `downloads/centennial_deck_handout_copy_from_prentice_job_2026-10-25.pdf`, pages 3-5 read):
- Site/plot plan showing setbacks, easements and distances to property lines. No structures on easements.
- **"If deck or porch will be attached to a masonry (brick) wall, provide detail on fasteners."** **"Attachment to cantilevers or veneers may require Engineer's approval."**
  - This house has brick veneer, and the assessor's 2 x 41 ft first-floor strip at B/C reads as a 2 ft cantilever over the walk-out wall (E). The ledger at B/C will need an engineer or a free-standing design.
- 36 in guards, 4 in sphere rule.
- Electrical outlet required on the deck.
- Flashing behind the wall covering.
- Beam splices over posts with 1-1/2 in bearing.
- Piers: 8 in minimum diameter, at least 36 in deep or below frost, 1/2 in anchor bolt embedded 7 in, post 8 in above grade.
- **6'-8" clearance required under the deck for walk-out basements or patios.**
- Stairs: 36 in minimum width; maximum rise 7-3/4 in; minimum run 10 in; stairs must be illuminated; handrail 34-38 in on 4 or more risers; composite treads may need 4 or more stringers.

## 5. Geometry files (county stereo roof print and parcel)
- `parcel.json` (EPSG:4326) and `parcel_2232.geojson` (EPSG:2232, US ft): parcel polygon (V, AC 279).
  - Lot lines in the house frame: rear (NNE) **79.7 ft** plus an 8.5 ft jog, against the SSPRD greenbelt 2077-25-3-14-001.
  - WNW side 103.3 ft, against 7313 S Fillmore 2077-25-3-08-023.
  - ESE side 102.2 ft, against the **Tiffany HOA tract 2077-25-3-08-035**, a 10 ft strip from the street to the greenbelt.
  - Front: about 80 ft of curved frontage on S Fillmore Cir.
- `footprint.json` (EPSG:4326) and `footprint_2232.geojson` (EPSG:2232): building roof print (V, AC 66, identical in AC 64/65 and CEN Planimetrics_2024 layer 6).
  - Building_ID 814393, **3,522.5 sf, Bldg_Height 28 ft**, Ground_Elevation 5565, created 2015-11-30, DRCOG stereo-compiled eave outline.
  - **The roof print includes the elevated deck.** Its NNE edge (vertex 1 to vertex 2, **62.81 ft**) and its ESE edge down to the 1.47 ft step at 19.48 ft are the deck's outer boundary, not a roof edge: the orthos show deck boards and furniture there. Because it is stereo-compiled, it has no building lean, so it is used as the absolute anchor for the deck plane.
- `deck_sketch.json` (EPSG:4326) and `deck_sketch_2232.geojson` (EPSG:2232): owner-sketch deck outline placed in the plan frame (E).

## 6. Orthophotos
- `aerial_YYYY.jpg` for **2026, 2024, 2022, 2020, 2018, 2016, 2014, 2012, 2010, 2008, 2006, 2004, 2002, 2000 and 1998**.
  - AC layers 437, 422, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410 (V).
  - All use the same bbox, **EPSG:2232 [3154229, 1638053, 3154479, 1638303] (250 x 250 ft)**, at 2000 x 2000 px = **0.125 ft/px**. The export limit is 4096 px, and 0.125 ft/px already oversamples the 3 in imagery about 2x.
  - Bbox in lon/lat, and the source, are in `aerial_bbox.json`.
- Layer 437 ("2026") and layer 422 ("2024") both carry the description "captured in the first week of March 2024, 3-inch". Their pixels differ (radiometric reprocessing), but they are the same capture.
- Clearest views of the deck: **2010, 2012 and 2014** (uniform deck stain, little furniture); **2018 and 2022** are also good. In **2024 and 2026 the arm is hidden** under the ESE maple, and 2016/2020 are in deep shadow.
- **Building lean:** these are not true orthos. Deck-level features shift 0-3.5 ft from year to year and roof-level features shift more. So this job:
  - measures only within one image at deck level (lengths, the level break), and
  - takes absolute position from the stereo roof print.
- The deck exists in the same footprint, with the same level break, in every year from **1998** to 2026 (V).

## 7. Terrain (County_DEM, 2 ft, NAVD88 ft, integer values; CEN 1 ft contours)
- The DEM is a "County Digital Elevation Model derived from multiple years of LiDAR" (2022 credit). It is in **integer feet**, so vertical resolution is about 1 ft.
- The city 1 ft contours match the county 1/2/5 ft contours to within 0.2 ft (Hausdorff).
- Under the deck the DEM is a **flat 5568 terrace from the wall out to y = 9**. That is read as the **walk-out patio slab at about 5568.0** (E, +/-0.5). From there the lawn slopes away from the house; beyond the rear lot line the greenbelt drops steeply to the creek.
- The rear lawn falls about **1-3 ft (typically 1.5-2 ft)** across the 13-14 ft between the deck edge and the rear lot line, roughly 10-15%.
- Elevations by station (plan frame; DEM bilinear / contour-interpolated, ft). **E +/-0.5-1**:

| Station | at wall (y=0; D: y=-2; A: door wall y=-13.5) | y=10 (deck edge) | y=15 | y=20 | y=25 | rear lot line (y~23-24) | y=30 |
|---|---|---|---|---|---|---|---|
| A arm x=-3.8 | 5569.0 / 5569.5 | 5567.0 / 5566.4 | 5566.1 | 5565.0 | 5564.4 | 5564.9 | 5563.6 |
| B x=5 | 5568.0 / 5568.2 | 5567.9 / 5567.0 | 5566.4 | 5566.0 | 5564.7 | 5565.0 | 5563.0 |
| B x=15 | 5568.0 / 5568.3 | 5568.0 / 5567.2 | 5567.0 | 5566.2 | 5565.1 | 5565.6 | 5563.2 |
| C x=26 | 5568.0 / 5568.4 | 5567.0 / 5567.3 | 5567.0 | 5566.0 | 5565.3 | 5566.0 | 5564.0 |
| C x=37 | 5568.0 / 5568.5 | 5567.0 / 5567.1 | 5567.0 | 5566.1 | 5565.0 | 5565.8 | 5563.7 |
| D x=46 | 5568.0 / 5568.0 | 5567.0 / 5566.7 | 5567.0 | 5566.0 | 5564.4 | 5565.9 | 5561.8 |
| D x=53 | 5568.0 / 5567.4 | 5567.0 / 5566.3 | 5566.1 | 5565.9 | 5564.8 | 5565.6 | 5561.7 |

- Relative to the patio slab (z = 0 at 5568, as in BRIEF.md), the ground is at:
  - z = 0 to -1.7 at the deck's outer edge (y = 10), typically **-0.5 to -1.0**
  - -1.0 to -2.4 at y = 15
  - -1.8 to -3.5 at y = 20
  - -2.7 to -5.0 at y = 25
  - -2.0 to -4.4 at the rear lot line (typically about -2.5)
- Along the house, the grade at the wall is level to within about 0.5 ft from the arm to D.
- **Deck heights:** public data gives no deck-surface elevation (there is no DSM). The owner says 9-12 ft above rear grade, and the BRIEF placeholders are upper z = 10.25 and lower z = 7.25. Field-measure. The orthos only confirm that the C/D level is higher: the eave shadow band on the deck is narrower over C/D than over B (2010: 1.45 vs 1.7 ft; 2012: 2.15 vs 2.9 ft; 2014: 3.35 vs 4.5 ft). That fits a 3 ft step if the eave is about 11-12 ft above the B surface (E).
- Files: `terrain_samples.csv`, `terrain_profiles.png`, `plan_overlay_terrain_2018_unregistered.png` (1 ft contours on the plan; orange = 5 ft index), `plan_frame.json` -> `terrain`. Raw data: `downloads/dem_2ft_aligned.tif`, `downloads/cen_contours.json`, `downloads/contours_34x.json`.
- 100-yr floodplain edge (city FHAD) is about **26.5 ft from the deck at ground about 5558**, roughly 9 ft below the deck-edge grade (E).

## 8. Listings
**Xome works.** 7303 S Fillmore Circle is **For Sale - Active, MLS# 6803070 (REcolorado), list price $925,000.** (V, Xome listing page, "last updated 10/21/2026")
- List date 2026-10-01, 25 days on market.
- An earlier search-engine snippet showed **$950,000** with **3,628 sq ft**; Xome now shows 3,631 sq ft. The assessor's 2,809 above grade + 819 finished basement = 3,628. U.
- Listed by Armie James, Atlas Real Estate Group, 303-242-8980.
- Facts given: 4 beds, 4 baths ("2 Full/ Half"), 2 stories, 0.2 ac lot, built 1981, HOA 420, 2-car garage.
- Description (V, quoted in part):
  - "backs directly to the Dry Creek corridor"
  - "private backyard gate provides direct access to Dry Creek Trail"
  - "An eat-in nook opens directly to the rear deck"
  - "family room features soaring ceilings and a dramatic floor-to-ceiling brick fireplace"
  - "finished walkout basement ... opening to a covered patio framed by brick columns"
  - "full-length rear deck extending across the back of the residence"
- `imageCount` is 40, but Xome serves only photo 1, the front elevation, saved as `listing_MLS6803070_front.jpg`. URLs `_1` to `_5` return a "Photo currently not available" placeholder (deleted). **No rear-deck, interior or floor-plan listing photo was obtainable.**
- **Flag:** the house is actively for sale. Confirm with Andie who will own the house during permitting and construction.

Blocked or unavailable sources (HTTP status recorded; nothing was fabricated):

| Site | Result |
|---|---|
| Zillow | **403** |
| Redfin | **403** (autocomplete); WebFetch 405; street sitemap 202 with an empty body |
| Realtor.com | **429**; WebFetch blocked |
| Homes.com | 403 |
| Trulia | 403 |
| Movoto | 403 |
| Estately | redirected to /map with no data |
| Compass | redirected to login |
| Airbnb | 200, generic search page (the parcel holds city STR licenses, but no listing could be tied to the address; not used) |

## 9. Rear direction, arm end and rear wall line
- **Rear = NNE, the creek/greenbelt side.** The street, garage and front door face SSW. (V: assessor sketch with the garage at the front, roof-print shape, orthos, MLS)
  - Outward normal of the rear wall: **25.25 deg true** (24.90 deg grid + 0.35 deg convergence). E +/-1 deg, from the stereo roof-print edge.
- **Arm (zone A) is at the ESE end, which is the LEFT end when you stand in the rear yard facing the house** (facing about 205 deg). Rationale:
  - The assessor sketch draws the rear at the top with the arm on the right of the sketch, which is ESE.
  - The roof print's ESE corner has the arm.
  - Photos u19/u20 show the arm, chimney and maple at the left end; u12 shows the right (D) end.
  - (V/E)
- **Rear wall line (B/C, y = 0)** runs on bearing **295.25 deg true** (+x, toward WNW). Points (E +/-1 ft):

| Point (plan x, y) | EPSG:2232 E, N | lat, lon |
|---|---|---|
| origin (0, 0) | 3154380.77, 1638188.32 | 39.5843365, -104.9522486 |
| B/C wall WNW end (42.58, 0) | 3154342.15, 1638206.26 | 39.5843863, -104.9523852 |
| D wall (42.58, -2) | 3154341.31, 1638204.44 | |
| D wall WNW end (55.50, -2) | 3154329.59, 1638209.88 | |
| outer edge, arm corner (-7.58, 10) = roof-print vertex 2 | 3154391.86, 1638194.20 | |
| outer edge, D corner (55.50, 10) | 3154334.64, 1638220.76 | 39.5844263, -104.9524115 |
| arm door wall (-7.58..0, -13.5) | 3154381.96, 1638172.89 to 3154375.09, 1638176.08 | |

- **The walls are not visible in any ortho**; they are under the eaves.
  - The B/C wall is placed 10.0 ft inside the stereo outer edge (owner dimension).
  - The arm's side wall is placed 7'-7" inside the stereo arm edge (owner dimension).
  - Check: the stereo roof print puts the rear eave 9.39 ft inside the outer edge, and the orthos give 8.5-10.5 ft depending on year. So a 10 ft deck implies a small B/C eave overhang (about 0.6-1.0 ft), and the D wall (2 ft further back) has about 2.6 ft. This is plausible from photos u07 and u14 but unverified.

## 10. Existing deck: imagery vs owner sketch
Description (V/E from orthos and site photos):
- Two-level wood deck, solid-stained gray (reddish-brown stain through 2014; gray from 2016 on), on **brick columns** along the outer edge, with gray/charcoal wood rails (sunburst panels in places).
- **C+D (WNW half) is the upper level** above the covered walk-out patio. **A+B is about 3 ft lower** (owner; about 5 risers in u07/u08/u18).
- Between them, at the B/C line, is a stair of about 3.5 ft at the outer edge, plus a guard along the level break, with lattice below. Its exact footprint is not resolvable from the imagery.
- The arm runs along the ESE wing's brick side wall to a slider in the inside corner, under a 2nd-floor overhang. The **tan-brick chimney mass, with a tall window, juts into the arm** (u04, u20).

Measurements. "Ortho" means the mean +/- SD of 2008, 2010, 2012, 2014, 2018 and 2022, measured within each image at deck level (`scripts/measure.py`, `deck_measurements.json`). "Stereo" means the county roof print.

| Dimension | Owner sketch | Assessor sketch | Imagery | Agreement |
|---|---|---|---|---|
| Outer-edge length, total | **63'-1"** (63.08) | 61 | **62.81 stereo; 62.70 +/- 0.39 ortho** (n=6; years range 62.14-63.34) | Owner vs imagery **+0.3 ft**, OK. **Assessor is 1.8 ft short (flag; its sketch rounds to whole feet).** |
| Level break B/C from the arm end (A + B) | 29'-2" (29.17) | n/a | **29.1 +/- 1.0** (62.81 - 33.69) | OK, within 0.1 ft |
| Level break B/C from the D end (C + D) | 33'-11" (33.92) | n/a | **33.69 +/- 0.98** (n=4: 34.25, 34.01, 32.23, 34.28) | OK, within 0.2 ft |
| A, arm width | 7'-7" | 7 | **not measurable**: the side wall is under the eave. 5.4 +/- 1 ft is visible outside the eave (2014). | Consistent if the side eave overhangs about 2 ft. U; field-verify. |
| A, outer edge to door wall | 23'-6" | 24 | Stereo step 19.48 ft (visible end at the 2nd-floor overhang) + 3 ft overhang (assessor) + about 1 ft eave = **about 23.5 +/- 1.5** | OK |
| A, side wall: 2'-4" (door to chimney) + 5' chimney + 5'-6" | 12'-10" | 14 (12 + 2) | Chimney-stack centroid (6 orthos) at **y = -9.7 +/- 1.1 ft** (SD; biased about 1 ft toward the sunlit faces) and **1.7 +/- 0.8 ft into the arm**. Owner-sketch chimney center is y = -8.7 (door wall at -13.5) or -8.0 (BRIEF's -12.83). | **Flag: the owner's numbers are 8 in inconsistent.** 23'-6" - 10' = 13'-6", but the side-wall pieces sum to 12'-10". The imagery cannot tell which piece is off. The plan places the door wall at y = -13.5 (23'-6") and measures the chimney 2'-4" from the door wall, leaving 6'-2" to the rear corner (sketch says 5'-6"). BRIEF.md uses -12.83. Field-verify. |
| Chimney projection into the arm | 1'-9" (7'-7" - 5'-10" clear) | not shown | Stack centroid 1.7 +/- 0.8 ft into the arm | Consistent (U) |
| B width | 21'-7" | (B+C = 41) | B/C break 29.1 - A 7.58 = **21.5 +/- 1** | OK |
| C width | 21' | (B+C = 41) | C + D = 33.69; with D = 12'-11", C = **20.8 +/- 1** | OK |
| D width | 12'-11" | 13 | The wall step is not visible (under the eave) | U |
| **B + C along the 2-ft rear strip (where the wall steps back for D)** | **42'-7"** | **41** | not visible | **Flag: owner vs assessor differ by 1.6 ft.** The break position fits the owner; the wall-step location is unverified. Field-verify where the D wall setback starts. |
| Depth at B/C (wall to outer edge) | 10' | 10 | Wall hidden. Eave is 9.39 ft (stereo) / 9.9 +/- 0.5 ft (ortho) inside the outer edge, so depth = 9.4-9.9 + eave overhang. | Consistent if the overhang is about 0.6-1.0 ft. If the sketch's 13'-6" side wall is wrong instead, depth could be about 10'-8". Field-verify. |
| Depth at D | 12' | 12 | **The outer edge is one straight line across D and C in every year** (no jog) | OK, consistent with 10 + 2 |
| Wall setback at D | 2' | 2 (sketch: D wall 2 ft behind the 2-ft rear strip) | not visible | V (assessor) and owner agree |
| C/D higher than A/B by | about 3 ft | n/a | 2010 eave-shadow width changes at the break; photos u07/u08/u18 show about 5 risers | OK (E) |
| Area | 759 sf gross (750 net of the chimney) | 578 + 156 = 734 sf | stereo outline 62.81 x 10-12 + arm, about 750 | OK |

**Nothing measurable disagrees with the owner's sketch by more than about 1 ft.** Open items:
1. The assessor's total (61 ft) and its B+C (41 ft) are short.
2. The owner's arm side-wall pieces do not add up (8 in).
3. Arm width and wall depths cannot be measured from the air; they are hidden under the eaves.

**Plan frame:**
- Origin = rear-wall corner where the main rear wall (B) meets the arm's side wall.
- +x along the rear wall away from the arm (295.25 deg true, WNW). +y into the yard (25.25 deg true, NNE).
- Plotted with +y down, the plan reads like the owner's sketch: house at the top, arm at the left.
- Transform from EPSG:2232 (also in `plan_frame.json`):
  - u = (E - 3154334.89)*0.907041 + (N - 1638220.65)*(-0.421042)
  - v = (E - 3154334.89)*0.421042 + (N - 1638220.65)*0.907041
  - x = 55.223 - u
  - y = v + 10
- In this frame the owner-sketch deck (E) is:
  - outer edge y = 10 from x = -7.58 (arm) to x = 55.50 (D end)
  - B/C wall y = 0 for x = 0 to 42.58; D wall y = -2 for x = 42.58 to 55.50
  - arm x = -7.58 to 0, door wall y = -13.5
  - chimney x = -1.75 to 0, y = -11.17 to -6.17
  - B/C break x = 21.58
- BRIEF frame: add 7.583 to x. For example, the B/C break is at x_brief = 29.17 and the deck runs from x_brief = 0 to 63.08. `plan_frame.json` -> `brief_frame` has the outline, zones, rear lot line, parcel and roof print in that frame.

**Overlays.** Each has a 10 ft grid, parcel (yellow), roof print (red), estimated walls (white dashed), owner-sketch deck (lime), traced deck as visible in the orthos (cyan dashed: outer edge, ends, arm, eave limits), measured B/C break (magenta dotted), approximate stair (magenta), chimney (orange) with its measured stack centroid (orange circle), the 20 ft rear setback, and the 8 ft deck limit.
- `plan_overlay_2010.png`, `_2012`, `_2014`, `_2018`, `_2022`: each image is shifted (offset printed in the title) so that its deck plane registers to the stereo frame.
- `plan_overlay_2026_unregistered.png` and `plan_overlay_terrain_2018_unregistered.png` (with 1 ft contours) show the raw ortho.

## 11. Deck to lot lines, against the setbacks (E +/-2 ft; GIS parcel lines are not a survey)
| Lot line | Deck (owner outline on stereo anchors) | Requirement for a deck at least 4 ft high | Margin |
|---|---|---|---|
| Rear (NNE, SSPRD greenbelt) | **12.8 ft at the D/WNW end to 14.1 ft at the arm/ESE end** (rear line is skewed 1.2 deg to the deck) | at least 8 ft (20 ft setback less the 12 ft allowance) | **+4.8 to +6.1 ft: complies.** It lies inside the 20 ft setback, which the LDC allows for these decks. |
| WNW side (7313 S Fillmore) | **8.8 ft** (D zone; 8.8-9.9 along D) | at least 5 ft (no encroachment allowed) | +3.8 ft |
| ESE side (Tiffany HOA tract) | **12.3 ft** (arm; 12.3-13.7) | at least 5 ft | +7.3 ft |
| Front (S Fillmore Cir) | 64.7 ft | n/a | n/a |

- House roof print without the deck: 22.2 ft from the rear line, 5.1 ft WNW, 6.9 ft ESE, 24.9 ft front.
- **Replacing the same footprint keeps every margin.** Do not push the outer edge more than about 4.8 ft further toward the rear line.
- The yard-stair option needs a ruling (section 4).

## 12. Yard, fences, trees, grade (site photos u01-u20 with the orthos; E)
- **Rear lot line (greenbelt): cedar split-rail fence with black welded-wire mesh.** This is the HOA "hog-pen" style. Photos u08/u09; the listing mentions a rear gate to the Dry Creek Trail.
  - Beyond it the greenbelt drops toward Big Dry Creek, with cottonwoods (u08). The DEM drops from about 5565 at the line to about 5556-5561 within 15 ft beyond it.
- **WNW side: solid weathered cedar privacy fence**, about 6 ft, running from the house back to the rear corner, where it meets the split rail (u02, u13, u17).
- **ESE side:** a wood privacy fence with a gate beyond the arm (u19), and a low dark picket fence and gate near the blue spruce (u12). The 10 ft HOA tract lies beyond it.
- Trees:
  - A **large maple at the ESE (arm) end**, whose canopy hangs over the arm (u19, u20, u03; it hides the arm in the 2024/2026 orthos).
  - A **large blue spruce** in the ESE part of the rear yard (u01, u12).
  - A **large ponderosa pine** near the WNW rear corner (u02, u09, u13).
  - A **tall cottonwood** beside the D end on the WNW side (u07, u13, u14; its bare crown shows in the leaf-off March 2018 ortho at about x 60-75, y -20 to +5).
  - Expect protection and pruning work for the maple at the arm and the cottonwood at D.
- Grade and under-deck conditions:
  - Under the upper level (C/D) is a **covered concrete walk-out patio** (u02, u11, u16). Its slab is about 5568 (E). Brick columns stand at its outer edge, and it has a basement slider and windows.
  - Under the lower level (A/B) are ivy and groundcover beds and a sloped bed toward the arm (u12, u17).
  - The lawn slopes away from the patio edge to the rear fence (u01, u02, u13): about 1-3 ft over 13-14 ft (DEM).
  - Along the house the grade is close to level (within 0.5 ft).

## 13. URLs used
County GIS (Arapahoe):
- https://gis.arapahoegov.com/arcgis/rest/services?f=json
- `AC?f=json` and `AC/layers?f=json` (layer list in `scripts/layer_list.txt`)
- `AC/2/query?where=Full_Address LIKE '7303 S FILLMORE%'&outFields=*&outSR=4326&f=json`
- `AC/<L>/query?geometry=-104.95235152721645,39.58432226980324&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=false&f=json`, for L = 64, 65, 66, 81, 140, 142, 149, 151, 152, 166, 266, 276, 277, 278, 279, 280, 283, 285, 287, 288, 289, 313, 322, 327, 351, 352, 353, 355, 366, 373, 374, 375, 379, 380, 385, 389, 390, 419, 423, 431 (`downloads/L<L>.json`)
- `AC/{279,66,65,64}/query?...&returnGeometry=true&outSR={2232,4326}` (`downloads/G*.json`)
- `AC/276/query` with envelope 3154179,1638003,3154529,1638353 (neighbors)
- `AC/380/query` with envelope (FEMA, `downloads/E380.json`, `G380_2232.json`)
- `AC/{345,346,347,348,349}/query` with envelope 3154229,1638053,3154479,1638303 (contours)
- `AC/{343,348,349,393,448}?f=json`
- `AC/export?bbox=3154229,1638053,3154479,1638303&bboxSR=2232&imageSR=2232&size=2000,2000&dpi=96&format=jpg&transparent=false&layers=show:<437|422|398|399|400|401|402|403|404|405|406|407|408|409|410>&f=image`
- `DEM?f=json`
- `DEM/exportImage?bbox=3154229.13,1638053.5,3154479.13,1638303.5&bboxSR=2232&imageSR=2232&size=125,125&format=tiff&pixelType=S32&interpolation=RSP_NearestNeighbor&f=image` (also `f=json`)
- `DEM/identify?geometry={"x":3154351.79,"y":1638182.98,"spatialReference":{"wkid":2232}}&geometryType=esriGeometryPoint&f=json`
- `DEM/info/metadata?f=json`
- https://gis.arapahoegov.com/arcgis/rest/services/{Terrain_WGS1984,Aerials,ATMS_Aerials}/ImageServer?f=json and .../{Eagleview,HistoricService,ACSO_Aerials,Aerials,AerialMap_WGS,Pictometry_WFS}/MapServer?f=json (checked, not used)
- https://gis.arapahoegov.com/mapsandphotos/salestaxrates.pdf

Assessor:
- `ASR` (GET, plus 2 ASP.NET postbacks `ucParcelHeader$btnSketch` / `$btnPhoto`)
- https://parcelsearch.arapahoegov.com/ParcelSketch.aspx?Pin=032153377&Sketch=... (full URL in `scripts/sketch_url.txt`)
- https://parcelsearch.arapahoegov.com/ParcelPhoto.aspx?PPINum=2077-25-3-08-024

City of Centennial GIS (`CEN`):
- `CEN?f=json`
- `CEN/{Planning,Energov,Hosted,Custom}?f=json`
- `CEN/<svc>/MapServer?f=json` for Planimetrics_2024, Contours, Parcels, History_EPL, EPL_Permit, Floodplain, Fire_Intensity_Classification, HOAs_Civic_Associations_and_Neighborhoods, Special_Districts, Subdivisions, DRAPP_2018, DRAPP_2020, Planning/Official_Zoning, Energov/Energov_v1
- Point queries (same point geometry as AC):
  - Parcels/MapServer/0
  - Planning/Official_Zoning/MapServer/0
  - History_EPL/MapServer/0 (plus `where=SPATIALID='2077-25-3-08-024'`)
  - Floodplain/MapServer/0 (plus envelope and geometry)
  - Fire_Intensity_Classification/MapServer/0
  - HOAs_Civic_Associations_and_Neighborhoods/MapServer/0
  - Subdivisions/MapServer/0
  - Special_Districts/MapServer/1-9
  - Airport_Influence_Area/MapServer/0
  - Current_Land_Use/MapServer/0
  - Hosted/Fire_Structure_Risk/FeatureServer/1-3
  - Hosted/EPL_Parcels/FeatureServer/0
  - Energov/Energov_v1/MapServer/{1,3,13,14,15,20,23,26,27,28} (3 also by envelope)
- Envelope queries: Planimetrics_2024/MapServer/{0,1,2,6,8} and Contours/MapServer/0

City website and code:
- https://www.centennialco.gov/Government/Departments/Community-Development/Zoning (403)
- https://www.centennialco.gov/Government/Departments/Community-Development/Land-Development-Code (403)
- https://library.municode.com/co/centennial/codes/land_development_code (403)
- https://www.centennialco.gov/files/sharedassets/public/documents/building/residential-uncovered-decks-and-porches.pdf (403 today; the 2026-10-25 copy was used)
- https://www.centennialco.gov/files/content/public/government/departments/city-clerk/ordinances-resolutions-public-hearings/ordinance-2023-o-06.pdf (403 today; the 2026-10-25 copy was used)
- https://www.zoneomics.com/code/centennial-CO/chapter_3 (third-party LDC mirror, U)

HOA:
- http://www.tiffanyhoa.org/ (redirects to https), plus /about.html, /architectural-control-committee.html, /board-of-directors.html, /contact.html, /hoa-covenants--policies.html
- https://www.tiffanyhoa.org/uploads/1/4/2/7/142739647/tiffany_hoa_acc_governing_master_document_-_board_approved_17june26.pdf
- https://www.tiffanyhoa.org/uploads/1/4/2/7/142739647/projectrevform-rev13.docx

Listings:
- https://www.xome.com/realestate/co/centennial?page=4 (card)
- https://www.xome.com/realestate/7303-s-fillmore-circle-centennial-co-80122-l426536187 (301, then ...-L426536187, 200)
- https://xomesearch.propertiescdn.com/ListingImages/comlmls/images/0/0/6803070.jpg?cb=63928220520 (and `_1`..`_5`.jpg placeholders)
- https://www.zillow.com/homes/7303-S-Fillmore-Cir-Centennial,-CO-80122_rb/ (403)
- https://www.redfin.com/stingray/do/location-autocomplete?location=7303%20S%20Fillmore%20Cir%20Centennial%20CO%2080122&v=2 (403)
- https://www.redfin.com/CO/Centennial/7303-S-Fillmore-Cir-80122/home/ (405)
- https://www.redfin.com/sitemap/26043/CO/Arapahoe-County/Southglenn/street/Fillmore+Cir (202, empty)
- https://www.realtor.com/realestateandhomes-detail/7303-S-Fillmore-Cir_Centennial_CO_80122_M00000-00000 (429)
- https://www.homes.com/property/7303-s-fillmore-cir-centennial-co/ (403)
- https://www.trulia.com/home/7303-s-fillmore-cir-centennial-co-80122 (403)
- https://www.movoto.com/address/7303-s-fillmore-cir-centennial-co-80122/ (403)
- https://www.estately.com/search?q=7303+S+Fillmore+Cir+Centennial+CO (redirect to /map)
- https://www.compass.com/search/?q=... (redirect to login)
- https://www.airbnb.com/s/7303-S-Fillmore-Cir--Centennial--CO/homes (200, generic)
- Also web searches for the address, the MLS number and the LDC section.

Not fetched:
- Deed: https://arapahoe.co.publicsearch.us/results?department=RP&searchType=quickSearch&searchValue=D8011923
- Plat: https://arapahoe.co.publicsearch.us/results?department=RP&searchType=quickSearch&searchValue=R1658716
- EnerGov permit pages (JavaScript app)

## 14. Files (this agent's)
- `README.md`
- `parcel.json`, `parcel_2232.geojson`
- `footprint.json`, `footprint_2232.geojson`
- `deck_sketch.json`, `deck_sketch_2232.geojson`
- `plan_frame.json`
- `deck_measurements.json`
- `assessor_sketch.jpg`, `assessor_sketch_vectors.json`, `assessor_photo_2006.jpg`
- `listing_MLS6803070_front.jpg`
- `aerial_{1998,2000,2002,2004,2006,2008,2010,2012,2014,2016,2018,2020,2022,2024,2026}.jpg`, `aerial_bbox.json`
- `plan_overlay_{2010,2012,2014,2018,2022}.png`, `plan_overlay_2026_unregistered.png`, `plan_overlay_terrain_2018_unregistered.png`
- `terrain_profiles.png`, `terrain_samples.csv`
- `downloads/` (raw), `scripts/` (mine: ptquery.sh, showattrs.py, html2text.py, postback.py, extract_dataimg.py, export_aerials.sh, inspect.py, rectify.py, zoomgrid.py, strips.py, profiles.py, profplot.py, measure.py, compute.py, sketch_decode.py), `work/` (intermediate rectified views)

To rebuild, run from any directory with `python3 -I`: `scripts/measure.py <dir>`, then `scripts/compute.py <dir>`.

## Caveats
- Positions are +/-1 ft within the deck and +/-2 ft relative to lot lines. County parcel lines are not a survey. Get an ILC if margins matter.
- Wall lines, arm width, chimney position and deck heights are hidden or not in public data. Tape and laser them in the field.
- LDC encroachment text comes from a third-party mirror, and the city site was blocked in this session. Confirm the deck (8 ft) and step (15 ft) limits with Centennial Planning. Get easements from the plat.
- Code status (2021 IRC, Ord. 2023-O-06) was read from a 2026-10-25 copy. Check whether a newer code is in force.
