# Site & code flags — what the engine checks and why

Severity: **STOP** (can't build as drawn) · **ENGINEER** (needs a stamped design) · **CODE** (a requirement to build
in) · **CHECK** (confirm before layout) · **INFO**. All internal — never on a client page.

| Topic | Rule | Reference |
|---|---|---|
| Setbacks | deck edge closer to the property line than the required rear/side setback → STOP; within 1' → CHECK; not entered → CHECK; easements listed → CHECK; HOA → INFO | zoning / plat |
| Snow | ground snow > 40 psf: IRC R507 tables don't apply, spans are scaled by √(50 / (snow + 10)) and flagged ENGINEER; 30–40 psf → INFO | IRC R507.5 / R507.6 |
| Hot tub / roof / privacy wall | 100 psf live (tub), roof and wind loads → ENGINEER | ASCE 7, IRC R507 |
| Joists | span vs Table R507.6 (SYP / DF-HF-SPF / cedar, 12-16-24" OC); over → STOP; > 95% → CHECK | IRC Table R507.6 |
| Beams | post spacing vs Table R507.5 by joist span incl. cantilever; over → STOP; 6x beams aliased and flagged; joist span > 18' → ENGINEER; flush beam shallower than joists → CODE | IRC Table R507.5 |
| Cantilever | > L/4 of the back-span → STOP | IRC R507.5 / R507.6 |
| Posts | 6x6 max 14', 4x4 max 6'-9"; over → STOP; posts > 8' → knee bracing CODE; deck > 10' high → ENGINEER | IRC Table R507.4, DCA6 |
| Freestanding | no ledger lateral path → diagonal bracing / engineered lateral system CODE | IRC R507.9 |
| Footings | Diamond Pier load > capacity → upgrade or STOP; utilities locate CHECK; concrete: bears below frost depth, soil bearing stated → CODE; soil < 1,500 psf → ENGINEER | IRC R403.1.4, R401.4.1, Pin Foundations |
| Ledger | brick/stone veneer → STOP; cantilevered house floor → ENGINEER; verify solid rim → CHECK; DTT1Z x4 → INFO | IRC R507.9.1.1, R507.9.2 |
| Wind | ≥ 140 mph → ENGINEER; ≥ 120 mph → H2.5AZ every joist + uplift caps CODE; else INFO | ASCE 7, IRC R301.2 |
| Fire / WUI | WUI zone and decking not WUI-listed → STOP (Vintage, Landmark, Harvest+ are Class A + WUI; Harvest Class B; Premier square-shoulder only; composites are not); WUI-listed → CODE (under-deck clearance); Terrain+ contradiction → CHECK | IWUIC 504.7, CBC 7A, TimberTech |
| Guards | surface > 30" above grade without guards → STOP; guard < 36" → STOP; missing side → CHECK; opening → CHECK | IRC R312.1 |
| Stairs | riser > 7-3/4", width < 36", run > 6' unsupported, riser < 4" → CHECK/CODE; 4+ risers → handrail CODE; lands on grade → landing CODE; open side > 30" without stair guard → STOP | IRC R311.7, DCA6 |
| Product | PVC > 12" OC or composite > 16" OC → CODE; color not in the current line → CHECK; > 2-ply rims → CHECK | TimberTech install guide |
| Geometry | non-rectangle / notches / multi-level → CHECK (bounding rectangle taken off) | — |

Inputs the engine checks but does not look up: ground snow (psf), basic wind speed (mph, ASCE 7 Vult), frost depth,
soil bearing, WUI zone, setbacks and deck-to-line distances. Colorado Front Range defaults are 30 psf / 115 mph / 36" /
1,500 psf / not WUI.
