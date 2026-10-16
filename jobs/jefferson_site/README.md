# 281 S Jefferson Ave, Louisville CO 80027 — site research (Oct 16, 2026)

Sources: Boulder County GIS (parcels, address points, 2024 Pictometry roof outlines, 2024 3" ortho), City of Louisville GIS
(zoning, PUDs, floodplain), Louisville Municipal Code (Municode), Louisville Building Safety handouts, USGS design maps.
GIS lines are not a survey.

| Item | Finding | Status |
|---|---|---|
| Parcel | 157517119033 · account R0092293 · Lot 33 Blk 10 Dutch Creek (plat rec. 00492001, 1982) · S17 T1S R69W | verified (county) |
| Lot | 4,678 SF · flood zone X | verified |
| House | 1982 one-storey ranch, 920 SF main + 728 SF unfinished basement + 400 SF garage | verified (assessor) |
| Roof outline 2024 | 1,754 SF incl. eaves and the existing covers (`footprint.json`) | verified |
| Zoning | R-L inside the Dutch Creek PUD (approved 12/15/1981) — the PUD final plan governs (LMC 17.28.230); PUD text not retrievable online | PUD values unverified |
| R-L reference | front 25', rear 25', interior side 7', coverage 30%, height 35' (LMC 17.12.040) | verified code text |
| Decks | 30" or less above grade: not held to the principal setbacks; permit still required for covered decks / covers (city handout 7/7/2025) | verified |
| Codes | 2024 I-codes as adopted by Ord. 1907-2025; IRC R507.1 amended (engineered unless 30" or less); IBC App. I patio covers | verified |
| Loads | 145 mph Vult Exp C · SDC B (SDS 0.17) · frost 36" · elev 5,337' · CZ 5B · snow per the ASCE hazard tool (30 psf on the city's Marshall Fire sheet; county layer 40) | snow unverified |
| Submittal | scaled, stamped plans; site plan with lot lines, north arrow, distances, coverage; Class A decking spec sheet; gravel over 6-mil poly under decks 6' or less up | verified (handout) |
| Orientation | rear wall faces ~299.5° (WNW); rear lot line ~12' past the new main deck | GIS calc |

Files: `parcel.json`, `footprint.json` (EPSG 4326), `aerial.jpg` (Boulder County 2024 ortho, EPSG 3857, ~80 m square),
`aerial_overlay.jpg` (parcel yellow, roof outline red).
