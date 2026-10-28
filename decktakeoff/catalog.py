"""Product knowledge: decking lines, rail systems, lumber, connectors, footings.
Facts here come from the TimberTech 2026 lineup (verified 9 Sep 2026), Simpson Strong-Tie catalog,
FastenMaster ESR, Pin Foundations chart, and the GSX standards. Prices live in data/pricebook.json."""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

with open(DATA / "pricebook.json") as f:
    PRICEBOOK = json.load(f)

# ---------------------------------------------------------------- decking
# collection -> facts. width/thickness are actual inches. gap = GSX field gap. oc = joist spacing at GSX.
DECKING = {
    "Vintage":  dict(material="PVC", width=5.5, thick=1.0, gap=0.1875, oc=12, profile="full", cap="4-sided",
                     warranty="TimberTech lifetime limited product warranty and 50-year limited fade & stain warranty (residential; fade & stain prorated from year 11; labor not covered)", fire="Ignition Resistant, Class A, WUI", wui=True, class_a=True,
                     colors=["Weathered Teak", "Cypress", "Coastline", "Mahogany", "English Walnut", "Dark Hickory"]),
    "Landmark": dict(material="PVC", width=5.5, thick=1.0, gap=0.1875, oc=12, profile="full", cap="4-sided",
                     warranty="TimberTech lifetime limited product warranty and 50-year limited fade & stain warranty (residential; fade & stain prorated from year 11; labor not covered)", fire="Ignition Resistant, Class A, WUI", wui=True, class_a=True,
                     colors=["French White Oak", "American Walnut", "Castle Gate", "Boardwalk"]),
    "Harvest+": dict(material="PVC", width=5.5, thick=1.0, gap=0.1875, oc=12, profile="full", cap="4-sided",
                     warranty="TimberTech lifetime limited product warranty and 50-year limited fade & stain warranty (residential; fade & stain prorated from year 11; labor not covered)", fire="Class A, WUI (not Ignition Resistant)", wui=True, class_a=True,
                     colors=["Toasted Wheat", "Timber Gray"]),
    "Harvest":  dict(material="PVC", width=5.5, thick=1.0, gap=0.1875, oc=12, profile="full", cap="4-sided",
                     warranty="TimberTech lifetime limited product warranty and 50-year limited fade & stain warranty (residential; fade & stain prorated from year 11; labor not covered)", fire="Class B, WUI", wui=True, class_a=False,
                     colors=["Slate Gray", "Kona", "Brownstone"]),
    "Legacy":   dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="full", cap="4-sided + Mold Guard",
                     warranty="TimberTech 30-year limited product warranty and 30-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)", fire="Class C, not WUI", wui=False, class_a=False,
                     colors=["Whitewash Cedar", "Ashwood", "Pecan", "Tigerwood", "Mocha", "Espresso"]),
    "Reserve":  dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="full", cap="4-sided",
                     warranty="TimberTech 30-year limited product warranty and 30-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)", fire="Class C, not WUI", wui=False, class_a=False,
                     colors=["Antique Leather", "Dark Roast", "Driftwood", "Reclaimed Chestnut"]),
    "Terrain+": dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="scalloped", cap="4-sided",
                     warranty="TimberTech 30-year limited product warranty and 30-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)", fire="Not Class A; WUI status contradictory on timbertech.com — confirm with dealer", wui=False, class_a=False,
                     colors=["Dark Oak", "Natural White Oak", "Weathered Oak"], cortex_ok=True),   # TimberTech: "the first scalloped-profile board to be compatible with ... CORTEX"
    "Terrain":  dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="full", cap="4-sided",
                     warranty="TimberTech 30-year limited product warranty and 30-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)", fire="Class C, not WUI", wui=False, class_a=False,
                     colors=["Silver Maple", "Brown Oak"], cortex_ok=False),
    "Premier+": dict(material="Composite", width=5.36, thick=0.89, gap=0.1875, oc=16, profile="full", cap="3-sided",
                     # Premier+: the 30 / 30 years this catalog held; its own warranty is not among the downloaded documents (no proration stated)
                     warranty="TimberTech 30-year limited product warranty and 30-year limited fade & stain warranty (residential; labor not covered)", fire="Not rated for fire zones", wui=False, class_a=False,
                     colors=["Natural Oak"]),
    "Prime+":   dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="scalloped", cap="3-sided",
                     warranty="TimberTech 25-year limited product warranty and 25-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)", fire="Not rated for fire zones", wui=False, class_a=False,
                     colors=["Coconut Husk", "Sea Salt Gray", "Dark Cocoa"], cortex_ok=False),
    "Prime":    dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="scalloped", cap="3-sided",
                     warranty="TimberTech 25-year limited product warranty and 25-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)", fire="Not rated (see Premier for WUI)", wui=False, class_a=False,
                     colors=["Dark Teak", "Maritime Gray"], cortex_ok=False),
    "Premier":  dict(material="Composite", width=5.36, thick=0.89, gap=0.1875, oc=16, profile="full", cap="3-sided",
                     warranty="TimberTech 25-year limited product warranty and 25-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)", fire="WUI compliant on square-shoulder boards only", wui=True, class_a=False,
                     colors=["Dark Teak", "Maritime Gray"]),
    # generic fallbacks
    "Wood":     dict(material="Wood", width=5.5, thick=1.0, gap=0.125, oc=16, profile="full", cap="none",
                     warranty="none", fire="Untreated wood: not WUI", wui=False, class_a=False, colors=["Cedar", "PT"]),
}
STOCK_LENGTHS_FT = [12, 16, 20]
# lines that don't come in every GSX stock length, by (collection, profile). Vintage square-shoulder: 12 / 16 / 20' — the owner
# buys 12' (27 Oct 2026), whatever the 2026 product guide lists; grooved 12 / 16 / 20'
DECK_LENGTHS_FT = {("Vintage", "square"): (16, 20), ("Vintage", "grooved"): (12, 16, 20),   # D&D: every 12' Vintage is grooved (AZV1612EWG)
                   ("Terrain+", "square"): (16, 20), ("Reserve", "square"): (16, 20)}     # 2026 guide: TC5416DO / TC5420DO, RC5416AL / RC5420AL — no 12' square shoulder
# TimberTech's two-letter color codes in the composite model numbers (TC5416DO, RC5416AL, CTC100LFDO) — the order's SKUs
COLOR_CODES = {"Dark Oak": "DO", "Natural White Oak": "NW", "Weathered Oak": "WO",
               "Antique Leather": "AL", "Dark Roast": "DR", "Driftwood": "DW", "Reclaimed Chestnut": "RC"}


def deck_lengths(collection: str, profile: str = "square") -> tuple:
    """The stock lengths (ft) a decking line is sold in, by profile — the GSX 12 / 16 / 20' otherwise."""
    return DECK_LENGTHS_FT.get((collection, profile), tuple(STOCK_LENGTHS_FT))
FASCIA = {"PVC": dict(thick=0.5, width=11.75, length=144.0), "Composite": dict(thick=0.58, width=11.95, length=144.0),
          "Wood": dict(thick=1.0, width=11.25, length=144.0)}
RISER = {"PVC": dict(thick=0.75, width=7.25, length=144.0), "Composite": dict(thick=0.58, width=7.25, length=144.0),
         "Wood": dict(thick=0.75, width=7.25, length=144.0)}
NOSE = 0.47   # board overhang past the fascia face


def decking_material(collection: str) -> str:
    return DECKING.get(collection, DECKING["Wood"])["material"]


def decking_facts(collection: str) -> dict:
    return DECKING.get(collection, DECKING["Wood"])


def default_fastener_system(collection: str, profile: str) -> str:
    """GSX rule: composite grooved = Camo EdgeClip 3/16" 100% hidden; PVC grooved = CONCEALoc; square-shoulder = Cortex plugs
    (Cortex NOT approved on scalloped Prime+/Prime or on Terrain)."""
    f = decking_facts(collection)
    if profile == "grooved":
        return "Camo EdgeClip" if f["material"] == "Composite" else "CONCEALoc"
    if f.get("cortex_ok", True):
        return "Cortex"
    return "Cap-Tor xd face screw"


# ---------------------------------------------------------------- lumber
LUMBER = {  # nominal -> (actual b, actual d)
    "2x4": (1.5, 3.5), "2x6": (1.5, 5.5), "2x8": (1.5, 7.25), "2x10": (1.5, 9.25), "2x12": (1.5, 11.25),
    "4x4": (3.5, 3.5), "4x6": (3.5, 5.5), "4x8": (3.5, 7.25), "4x10": (3.5, 9.25), "4x12": (3.5, 11.25),
    "6x6": (5.5, 5.5), "6x8": (5.5, 7.25), "6x10": (5.5, 9.25), "6x12": (5.5, 11.25),
    "8x8": (7.5, 7.5), "8x10": (7.5, 9.5), "8x12": (7.5, 11.5),
    # cold-formed steel C-joists by SSMA depth (steel frame jobs): the layout uses them like a nominal size
    "600S": (1.625, 6.0), "800S": (1.625, 8.0), "1000S": (1.625, 10.0),
}
LUMBER_STOCK_FT = {"2x6": [8, 10, 12, 14, 16, 20], "2x8": [8, 10, 12, 14, 16, 20], "2x10": [8, 10, 12, 14, 16, 20, 24],
                   "2x12": [8, 10, 12, 14, 16, 20, 24], "4x8": [8, 10, 12, 16, 20], "4x10": [8, 10, 12, 16, 20], "4x12": [8, 10, 12, 16, 20],
                   "6x6": [8, 10, 12, 16], "6x8": [8, 10, 12, 16], "6x10": [8, 10, 12, 16, 20], "6x12": [8, 10, 12, 16, 20],
                   "8x8": [8, 10, 12, 16], "8x10": [8, 10, 12, 16], "8x12": [8, 10, 12, 16],
                   "600S": [8, 10, 12, 14, 16, 20], "800S": [8, 10, 12, 14, 16, 20], "1000S": [8, 10, 12, 14, 16, 20]}
SPECIES_NAMES = {"SYP": "#1 True Frame Joist SYP GC", "DF": "Douglas Fir #2", "SPF": "SPF #2", "HF": "Hem-Fir #2", "CEDAR": "Western Cedar #2",
                 "DF#1": "Douglas Fir #1 timber (S4S, end grain sealed)"}


def actual(nominal: str):
    return LUMBER[nominal]


def parse_beam(size: str):
    """'(2)2x10' -> (2, '2x10'); '4x10' -> (1, '4x10'). Returns (plies, nominal, width_in, depth_in)."""
    s = size.replace(" ", "")
    plies = 1
    if s.startswith("(") and ")" in s:
        plies = int(s[1:s.index(")")])
        s = s[s.index(")") + 1:]
    elif "-" in s and s.split("-")[0].isdigit():   # "2-2x10"
        plies, s = int(s.split("-")[0]), s.split("-")[1]
    b, d = LUMBER[s]
    return plies, s, b * plies, d


# ---------------------------------------------------------------- connectors
HANGER_FOR_JOIST = {"2x6": "LUS26Z", "2x8": "LUS28Z", "2x10": "LUS210Z", "2x12": "LUS210Z",
                    "4x8": "LUS48Z", "4x10": "LUS410Z", "4x12": "LUS410Z"}
HANGER_NAILS = {"LUS26Z": (4, 4), "LUS28Z": (6, 4), "LUS210Z": (8, 6),        # (10d 3" into header, 10d x 1-1/2" into joist)
                "LUS48Z": (6, 4), "LUS410Z": (8, 6)}
TIMBER_BEAM_TIE = "A35Z"           # (legacy) framing angle; the Eagle's Nest standard uses H2.5AZ at the drop beam
TIMBER_CAP = {"8x8": ("CCQ68SDS2.5", "ECCQ68SDS2.5"), "6x6": ("CCQ66SDS2.5", "ECCQ66SDS2.5")}   # (intermediate, beam-end) column caps
TIMBER_BASE = {"8x8": ("APB88_black", "ABU88Z"), "6x6": ("ABU66Z_black", "ABU66Z")}                # (black, galvanized)
DOUBLE_HANGER = {"2x8": "HUCQ28-2-SDS", "2x10": "HUCQ210-2-SDS", "2x12": "HUCQ212-2-SDS", "4x8": "HUC410", "4x10": "HUC410", "4x12": "HUC410"}
TRIPLE_HANGER = {"2x10": "HUCQ210-3-SDS"}
H25_NAILS = 10        # H2.5AZ: 5 x 8d x 1-1/2" each leg
# an 8x8: the Simpson ABU88Z adjustable standoff base (ABU88RZ for a rough 8x8) — on a Diamond Pier its second 5/8" anchor is
# drilled into the pier head beside the cast-in bolt (Pin Foundations / the engineer confirm); owner 27 Oct 2026
POST_BASE = {"6x6": {"diamond_pier": "ABA66Z", "concrete": "ABU66Z"}, "4x4": {"diamond_pier": "ABA44Z", "concrete": "ABA44Z"},
             "8x8": {"diamond_pier": "ABU88Z", "concrete": "ABU88Z"}}
POST_BASE_SCREWS = {"ABA66Z": 12, "ABA66RZ": 12, "ABU66Z": 12, "ABA44Z": 8, "DP_base_8x8_custom": 0, "ABU88Z": 0, "ABU88RZ": 0}   # ABU88: (8) 1/4" x 3" SDS, listed on its own line
POST_CAP_SCREWS = {"CCQ76SDS2.5": 0, "BC46Z": 10, "BC6Z": 10, "BCS2-3/6Z": 12, "BCS2-2/4Z": 8,
                   "CCQ68SDS2.5": 0, "ECCQ68SDS2.5": 0, "CCQ66SDS2.5": 0, "ECCQ66SDS2.5": 0, "CCQ88SDS2.5": 0}     # CCQ / ECCQ ship with their SDS screws
# Pin Foundations Residential Load Chart (DOC0008, 2018): 1,500 psf silts / clays; 2,000 psf sands / gravels allow 4,400 / 6,400 lb
FOOTING_CAPACITY_LB = {"DP-50/50": 3300, "DP-75/63": 4200}
FOOTING_CAPACITY_LB_2000 = {"DP-50/50": 4400, "DP-75/63": 6400}


def pier_capacity_lb(model: str, soil_psf: float = 1500.0) -> float:
    """A Diamond Pier's allowable load on this soil (the chart's 1,500 psf column unless the soil is 2,000 psf or better)."""
    return (FOOTING_CAPACITY_LB_2000 if soil_psf >= 2000 else FOOTING_CAPACITY_LB).get(model, 0)


def post_cap(post: str, beam_size: str) -> str:
    plies, nom, w, d = parse_beam(beam_size)
    if post == "8x8":
        return "CCQ68SDS2.5" if nom.startswith("6x") else "CCQ88SDS2.5"
    if post == "6x6":
        if nom.startswith("4x"):
            return "CCQ76SDS2.5" if plies == 2 else "BC46Z"     # (2)4x = 7" seat
        if nom.startswith("6x"):
            return "BC6Z"
        if plies == 3:
            return "BCS2-3/6Z"
        return "BC46Z"          # (2)2x = 3" in a 4x cap with a 1/2" shim — confirm cap
    if post == "4x4":
        return "BCS2-2/4Z"
    return "BC46Z"


# ---------------------------------------------------------------- railing
RAIL_SYSTEMS = {
    "IRX": dict(panels={72: 70.0, 96: 94.0}, post_w=2.0, bracket_allow=0.0, heights=[36, 42], post_types=["END", "LINE", "CORNER", "STAIR"],
                cable=True, max_ctc=96.0, noncombustible=True,
                note="TimberTech Impression Rail Express cable: aluminum posts, top rail, stainless cable infill, no bottom rail; 8' kits cut to bay, posts on the divider lines"),
    "Fulton": dict(panels={72: 69.5, 96: 93.5}, post_w=2.0, bracket_allow=0.25, heights=[36, 42],
                   post_types=["END", "LINE", "CORNER", "STAIR"], note="2\" steel posts inside the outer rim ply; brackets, caps, skirts and screws ship with the posts"),
    "Impression": dict(panels={72: 70.0, 96: 94.0}, post_w=2.5, bracket_allow=0.25, heights=[36, 42], post_types=["POST"], noncombustible=True, note="aluminum"),
    "Classic Composite": dict(panels={72: 68.0, 96: 92.0}, post_w=5.5, bracket_allow=0.5, heights=[36, 42], post_types=["POST"], noncombustible=False, note="composite sleeve over 4x4"),
}
RAIL_SYSTEMS["Cinch"] = dict(panels={72: 70.0, 96: 94.0}, post_w=2.0, bracket_allow=0.25, heights=[36, 42], post_types=["END", "LINE", "CORNER", "STAIR"],
                             noncombustible=True, max_ctc=96.0, brand="Cinch", colors=["Satin Black", "Bronze"],
                             note="Cinch HD: heavy-gauge galvanized steel, factory-welded and powder-coated panels with the brackets welded on and screws in the box; 2\" posts with welded base, caps and skirts; "
                                  "level and stair panels 6' / 8' cut to bay; Cinch drink-rail bracket kit takes a deck board on top; 15-year finish warranty")
RAIL_SYSTEMS["Fulton"]["noncombustible"] = True
RAIL_SYSTEMS["Fulton"]["max_ctc"] = 96.0
RAIL_SYSTEMS["Impression Rail Express"] = RAIL_SYSTEMS["IRX"]
RAIL_SYSTEMS["IRX Baluster"] = dict(profile=dict(top=(0.22, 0.13), bottom=(0.115, 0.10), baluster=0.0625, baluster_oc_in=4.5),   # Modern top rail 2-5/8" x 1-1/2"; 3/4" balusters, 20 per 8'
                                    panels={72: 70.0, 96: 94.0}, post_w=3.0, bracket_allow=0.25, heights=[36, 42], post_types=["END", "LINE", "CORNER", "STAIR"],
                                    noncombustible=True, surface=True, post_lag=True,       # post_lag: (4) 3/8" x 6" HDG lags + washers per post into solid blocking (IRX install guide), not HeadLOK
                                    display="Impression Rail Express, vertical aluminum balusters, modern top rail", max_ctc=96.0, brand="TimberTech", colors=["Black", "White", "Bronze"],
                                    note="TimberTech Impression Rail Express: 3\" aluminum posts (3\" x 38-1/4\" kits) on surface bases, Modern top rail (sold separately), vertical aluminum balusters, "
                                         "bottom rail; 6' / 8' level kits cut to bay, posts on the divider lines")


def rail_name(system: str) -> str:
    """How a rail system reads in client documents (the catalog key otherwise)."""
    return RAIL_SYSTEMS.get(system, {}).get("display", system)


# the client documents' warranty words — the makers' published limited warranties, residential terms: TimberTech aluminum railing
# (Impression Rail Express, V-102725: 25 years, prorated in years 11-25, no labor), TimberTech lighting (V100123: 5 years, no labor),
# James Hardie trim (30-year substrate, ColorPlus 15-year finish); never "lifetime" for the rail
RAIL_WARRANTY = {k: "TimberTech 25-year limited warranty (residential; prorated from year 11; labor not covered)"
                 for k in ("IRX", "IRX Baluster", "Impression Rail Express")}
RAIL_WARRANTY["Fulton"] = "TimberTech 15-year limited warranty (residential)"        # the owner's proposal template (gsx-deck-docs): 15-yr residential limited
RAIL_WARRANTY["Cinch"] = "Cinch 15-year finish warranty"                                # the Cinch note above
LIGHT_WARRANTY = "TimberTech 5-year limited warranty (labor not covered)"
# TimberTech fastening systems (TOPLoc, CONCEALoc, Cortex) limited warranty 10.01.23: 25 years residential, against corrosion
FASTENER_WARRANTY = "TimberTech 25-year limited warranty against corrosion (residential)"
# ProWood TrueFrame Joist: "backed by ProWood's Lifetime Limited Warranty" (trueframe.html; the consolidated warranty: against rot,
# fungal decay and termite damage, for the end tag's term); Diamond Pier (Pin Foundations): Product Performance Limited Lifetime
# Warranty, to the original owner, for the original structure, once the project is registered within 30 days of completion
TRUEFRAME_WARRANTY = "ProWood lifetime limited warranty against rot, fungal decay and termite damage"
DIAMOND_PIER_WARRANTY = "Diamond Pier product performance limited lifetime warranty (original owner; the project registered within 30 days)"
HARDIE_TRIM_WARRANTY = "James Hardie 30-year limited warranty (substrate) + ColorPlus 15-year limited finish warranty"


def beam_words(sizes, species: str = "Douglas fir", n: int = 1) -> str:
    """'a doubled 4x10 Douglas fir beam' / '4x10 / 4x12 Douglas fir beams' — client wording for the beam list (n beams)."""
    sizes = list(sizes)
    if len(sizes) == 1:
        sz = sizes[0]
        if n > 1:
            return f"{n} {sz} {species} beams"
        if sz.startswith("(2)4x") or sz.startswith("(2)6x"):
            return f"a doubled {sz[3:]} {species} beam"
        return f"{sz} {species} beam"
    return f"{' / '.join(sizes)} {species} beams"


def beam_species_words(beams) -> str:
    """How the beams' wood reads: SYP beams are the pressure-treated TrueFrame stock, everything else Douglas fir."""
    sp = {(getattr(b, "species", None) or "DF").upper() for b in beams}
    return "pressure-treated SYP" if sp and all(x.startswith("SYP") for x in sp) else "Douglas fir"


def tax_rate_for(city: str, override=None) -> float:
    if override is not None:
        return float(override)
    t = PRICEBOOK["tax_rates"]
    return float(t.get((city or "").strip().lower(), t["default"]))


# render palettes (dark -> light) per board — from the timbertech-boards skill catalog (Jade-calibrated: Coastline pure gray,
# Dark Hickory very dark gray not brown, Coconut Husk warm golden tan)
BOARDS_PALETTE = {
    ("Vintage", "Weathered Teak"): ["#7a6650", "#917b62", "#a58f74", "#b6a186", "#c5b196", "#d1bfa5", "#dccdb6"],
    ("Vintage", "Cypress"): ["#5c3324", "#74432f", "#89523b", "#9b6147", "#ad7256", "#bd8567", "#cc9979"],
    ("Vintage", "Coastline"): ["#5f5e5b", "#6f6e6c", "#7e7d7b", "#8b8a88", "#979694", "#a3a2a0", "#afaeac"],
    ("Vintage", "Mahogany"): ["#4f3325", "#664434", "#7b5541", "#8e654e", "#a0775d", "#b18a6f", "#c19c81"],
    ("Vintage", "English Walnut"): ["#402e20", "#4f3a2b", "#5a4537", "#634e3e", "#6f5647", "#7e6554", "#917766"],   # swatch-sampled 27 Oct 2026 (median #614b3c); the description-only palette read rosy-mauve
    ("Vintage", "Dark Hickory"): ["#2c2a29", "#333234", "#3a3a3c", "#454546", "#525253", "#5e5e5f", "#6a6a6b"],
    ("Landmark", "French White Oak"): ["#8f8168", "#a89a80", "#b8aa8f", "#c7b99f", "#d5c9b1", "#e2d8c3"],
    ("Landmark", "American Walnut"): ["#211610", "#2e1f16", "#3b2a1e", "#493627", "#574232", "#66503e"],
    ("Landmark", "Castle Gate"): ["#2a2927", "#373634", "#454341", "#524f4d", "#605c5a", "#6e6a67"],
    ("Landmark", "Boardwalk"): ["#948878", "#a89c8b", "#b7ab9a", "#c4b9a8", "#d0c6b5", "#dbd2c2"],
    ("Harvest+", "Toasted Wheat"): ["#a48a63", "#b59b74", "#c4ab86", "#d1ba97", "#dcc8a8"],
    ("Harvest+", "Timber Gray"): ["#66625d", "#75716c", "#85817c", "#95918c", "#a5a19c"],
    ("Harvest", "Slate Gray"): ["#727474", "#7b7d7d", "#838585"], ("Harvest", "Kona"): ["#4b3427", "#55402f", "#5e4836"], ("Harvest", "Brownstone"): ["#a27e58", "#ad8961", "#b7946b"],
    ("Legacy", "Whitewash Cedar"): ["#9b8b72", "#b0a089", "#c0b19b", "#cfc2ad", "#dcd1be", "#e7dfcf"],
    ("Legacy", "Ashwood"): ["#7d786f", "#918b82", "#a39d94", "#b3ada4", "#c2bdb4", "#cfcac2"],
    ("Legacy", "Pecan"): ["#6a4826", "#835b33", "#9a6f41", "#b08552", "#c39a66", "#d2ad7c"],
    ("Legacy", "Tigerwood"): ["#3e2412", "#5b3519", "#8a5a2e", "#b07a44", "#cc985a", "#dcae72"],
    ("Legacy", "Mocha"): ["#3f2a1e", "#52392a", "#654a38", "#785b47", "#8a6c56", "#9c7e67"],
    ("Legacy", "Espresso"): ["#1f1a18", "#2c2523", "#3a322f", "#48403c", "#564d48", "#635a54"],
    ("Reserve", "Antique Leather"): ["#4f3520", "#6a4a30", "#845f41", "#9c7553", "#b08a66", "#c19c78"],
    ("Reserve", "Dark Roast"): ["#26190f", "#3a2a1f", "#4c3a2d", "#5e4a3b", "#6e5a4a", "#7d6a5a"],
    ("Reserve", "Driftwood"): ["#5c5954", "#77736c", "#979289", "#aea9a1", "#bdb8b0", "#cac6bf", "#d6d2cb"],
    ("Reserve", "Reclaimed Chestnut"): ["#6e5238", "#88694c", "#a08260", "#b39674", "#c3a888", "#d0b99c"],
    ("Terrain+", "Dark Oak"): ["#6c553c", "#6e573e", "#796248", "#846c51", "#856e51"],   # 28 Oct: TimberTech's swatch read color-managed (its files are Adobe RGB): p03 / p10 / median / p90 / p97
    ("Terrain+", "Natural White Oak"): ["#ad966a", "#b8a275", "#bfaa7d", "#c5b085", "#cdb98e"],
    ("Terrain+", "Weathered Oak"): ["#85806d", "#8e8977", "#96907f", "#9d9786", "#a5a08e"],
    ("Terrain", "Silver Maple"): ["#8a8a88", "#959593", "#a0a09e", "#aaaaa8"], ("Terrain", "Brown Oak"): ["#6b4d36", "#76573e", "#816147", "#8b6b50"],
    ("Premier+", "Natural Oak"): ["#8f6f4c", "#a1825d", "#b09069", "#bd9e78", "#c9ac88"],
    ("Prime+", "Coconut Husk"): ["#8f6a42", "#a07a4d", "#b58a58", "#c49a68", "#d2ad7b"],
    ("Prime+", "Sea Salt Gray"): ["#777774", "#868683", "#959592", "#a3a3a0", "#b0b0ad"],
    ("Prime+", "Dark Cocoa"): ["#3b2a20", "#4a3428", "#5b4234", "#6a5040", "#775c4a"],
    ("Prime", "Dark Teak"): ["#4c3a2d", "#544133", "#5a4636"], ("Prime", "Maritime Gray"): ["#6b6f70", "#727677", "#787c7d"],
    ("Premier", "Dark Teak"): ["#4c3a2d", "#544133", "#5a4636"], ("Premier", "Maritime Gray"): ["#6b6f70", "#727677", "#787c7d"],
    ("Wood", "Cedar"): ["#9c6b3f", "#ad7a49", "#bd8a57", "#caa06c", "#d6b283"], ("Wood", "PT"): ["#9a8a5e", "#ab9a6a", "#b9a979", "#c6b78a", "#d1c49a"],
}


def rail_system_for(spec_railing) -> dict:
    """The rail system's numbers for a job, with the job's post size applied (a 3" post shortens every panel cut)."""
    d = dict(RAIL_SYSTEMS.get(spec_railing.system, RAIL_SYSTEMS["Fulton"]))
    if getattr(spec_railing, "post_size_in", None):
        d["post_w"] = float(spec_railing.post_size_in)
    return d
