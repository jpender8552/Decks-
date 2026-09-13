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
                     warranty="Limited Lifetime product / 50-yr fade & stain", fire="Ignition Resistant, Class A, WUI", wui=True, class_a=True,
                     colors=["Weathered Teak", "Cypress", "Coastline", "Mahogany", "English Walnut", "Dark Hickory"]),
    "Landmark": dict(material="PVC", width=5.5, thick=1.0, gap=0.1875, oc=12, profile="full", cap="4-sided",
                     warranty="Limited Lifetime product / 50-yr fade & stain", fire="Ignition Resistant, Class A, WUI", wui=True, class_a=True,
                     colors=["French White Oak", "American Walnut", "Castle Gate", "Boardwalk"]),
    "Harvest+": dict(material="PVC", width=5.5, thick=1.0, gap=0.1875, oc=12, profile="full", cap="4-sided",
                     warranty="Limited Lifetime product / 50-yr fade & stain", fire="Class A, WUI (not Ignition Resistant)", wui=True, class_a=True,
                     colors=["Toasted Wheat", "Timber Gray"]),
    "Harvest":  dict(material="PVC", width=5.5, thick=1.0, gap=0.1875, oc=12, profile="full", cap="4-sided",
                     warranty="Limited Lifetime product / 50-yr fade & stain", fire="Class B, WUI", wui=True, class_a=False,
                     colors=["Slate Gray", "Kona", "Brownstone"]),
    "Legacy":   dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="full", cap="4-sided + Mold Guard",
                     warranty="30-yr product / 30-yr fade & stain", fire="Class C, not WUI", wui=False, class_a=False,
                     colors=["Whitewash Cedar", "Ashwood", "Pecan", "Tigerwood", "Mocha", "Espresso"]),
    "Reserve":  dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="full", cap="4-sided",
                     warranty="30-yr product / 30-yr fade & stain", fire="Class C, not WUI", wui=False, class_a=False,
                     colors=["Antique Leather", "Dark Roast", "Driftwood", "Reclaimed Chestnut"]),
    "Terrain+": dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="full", cap="4-sided",
                     warranty="30-yr product / 30-yr fade & stain", fire="Not Class A; WUI status contradictory on timbertech.com — confirm with dealer", wui=False, class_a=False,
                     colors=["Dark Oak", "Natural White Oak", "Weathered Oak"]),
    "Terrain":  dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="full", cap="4-sided",
                     warranty="30-yr product / 30-yr fade & stain", fire="Class C, not WUI", wui=False, class_a=False,
                     colors=["Silver Maple", "Brown Oak"], cortex_ok=False),
    "Premier+": dict(material="Composite", width=5.36, thick=0.89, gap=0.1875, oc=16, profile="full", cap="3-sided",
                     warranty="30-yr product / 30-yr fade & stain", fire="Not rated for fire zones", wui=False, class_a=False,
                     colors=["Natural Oak"]),
    "Prime+":   dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="scalloped", cap="3-sided",
                     warranty="25-yr product / 25-yr fade & stain", fire="Not rated for fire zones", wui=False, class_a=False,
                     colors=["Coconut Husk", "Sea Salt Gray", "Dark Cocoa"], cortex_ok=False),
    "Prime":    dict(material="Composite", width=5.36, thick=0.94, gap=0.1875, oc=16, profile="scalloped", cap="3-sided",
                     warranty="25-yr product / 25-yr fade & stain", fire="Not rated (see Premier for WUI)", wui=False, class_a=False,
                     colors=["Dark Teak", "Maritime Gray"], cortex_ok=False),
    "Premier":  dict(material="Composite", width=5.36, thick=0.89, gap=0.1875, oc=16, profile="full", cap="3-sided",
                     warranty="25-yr product / 25-yr fade & stain", fire="WUI compliant on square-shoulder boards only", wui=True, class_a=False,
                     colors=["Dark Teak", "Maritime Gray"]),
    # generic fallbacks
    "Wood":     dict(material="Wood", width=5.5, thick=1.0, gap=0.125, oc=16, profile="full", cap="none",
                     warranty="none", fire="Untreated wood: not WUI", wui=False, class_a=False, colors=["Cedar", "PT"]),
}
STOCK_LENGTHS_FT = [12, 16, 20]
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
}
LUMBER_STOCK_FT = {"2x6": [8, 10, 12, 14, 16, 20], "2x8": [8, 10, 12, 14, 16, 20], "2x10": [8, 10, 12, 14, 16, 20, 24],
                   "2x12": [8, 10, 12, 14, 16, 20, 24], "4x8": [8, 10, 12, 16, 20], "4x10": [8, 10, 12, 16, 20], "4x12": [8, 10, 12, 16, 20],
                   "6x6": [8, 10, 12, 16], "6x8": [8, 10, 12, 16], "6x10": [8, 10, 12, 16, 20], "6x12": [8, 10, 12, 16, 20],
                   "8x8": [8, 10, 12, 16], "8x10": [8, 10, 12, 16], "8x12": [8, 10, 12, 16]}
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
HANGER_FOR_JOIST = {"2x6": "LUS26Z", "2x8": "LUS28Z", "2x10": "LUS28Z", "2x12": "LUS210Z",
                    "4x8": "LUS48Z", "4x10": "LUS410Z", "4x12": "LUS410Z"}
HANGER_NAILS = {"LUS26Z": (4, 4), "LUS28Z": (6, 4), "LUS210Z": (8, 6),        # (10d 3" into header, 10d x 1-1/2" into joist)
                "LUS48Z": (6, 4), "LUS410Z": (8, 6)}
TIMBER_BEAM_TIE = "A35Z"           # (legacy) framing angle; the Eagle's Nest standard uses H2.5AZ at the drop beam
TIMBER_CAP = {"8x8": ("CCQ68SDS2.5", "ECCQ68SDS2.5"), "6x6": ("CCQ66SDS2.5", "ECCQ66SDS2.5")}   # (intermediate, beam-end) column caps
TIMBER_BASE = {"8x8": ("APB88_black", "ABU88Z"), "6x6": ("ABU66Z_black", "ABU66Z")}                # (black, galvanized)
DOUBLE_HANGER = {"2x8": "HUCQ28-2-SDS", "2x10": "HUCQ210-2-SDS", "2x12": "HUCQ212-2-SDS", "4x8": "HUC410", "4x10": "HUC410", "4x12": "HUC410"}
TRIPLE_HANGER = {"2x10": "HUCQ210-3-SDS"}
H25_NAILS = 10        # H2.5AZ: 5 x 8d x 1-1/2" each leg
POST_BASE = {"6x6": {"diamond_pier": "ABA66Z", "concrete": "ABU66Z"}, "4x4": {"diamond_pier": "ABA44Z", "concrete": "ABA44Z"}}
POST_BASE_SCREWS = {"ABA66Z": 12, "ABU66Z": 12, "ABA44Z": 8}
POST_CAP_SCREWS = {"BC46Z": 10, "BC6Z": 10, "BCS2-3/6Z": 12, "BCS2-2/4Z": 8}
FOOTING_CAPACITY_LB = {"DP-50/50": 3300, "DP-75/63": 6000}


def post_cap(post: str, beam_size: str) -> str:
    plies, nom, w, d = parse_beam(beam_size)
    if post == "6x6":
        if nom.startswith("4x"):
            return "BC46Z"
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
RAIL_SYSTEMS["Fulton"]["noncombustible"] = True
RAIL_SYSTEMS["Fulton"]["max_ctc"] = 96.0
RAIL_SYSTEMS["Impression Rail Express"] = RAIL_SYSTEMS["IRX"]


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
    ("Vintage", "English Walnut"): ["#2f2019", "#40302a", "#54413a", "#68524a", "#7c6357", "#8f7565", "#a08874"],
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
    ("Terrain+", "Dark Oak"): ["#3f2f24", "#4e3b2e", "#5c4838", "#6a5543", "#775f4c"],
    ("Terrain+", "Natural White Oak"): ["#a8946f", "#b9a683", "#c7b494", "#d3c2a4", "#dccdb2"],
    ("Terrain+", "Weathered Oak"): ["#6f665b", "#7f776c", "#8f877b", "#9d968a", "#aaa398"],
    ("Terrain", "Silver Maple"): ["#8a8a88", "#959593", "#a0a09e", "#aaaaa8"], ("Terrain", "Brown Oak"): ["#6b4d36", "#76573e", "#816147", "#8b6b50"],
    ("Premier+", "Natural Oak"): ["#8f6f4c", "#a1825d", "#b09069", "#bd9e78", "#c9ac88"],
    ("Prime+", "Coconut Husk"): ["#8f6a42", "#a07a4d", "#b58a58", "#c49a68", "#d2ad7b"],
    ("Prime+", "Sea Salt Gray"): ["#777774", "#868683", "#959592", "#a3a3a0", "#b0b0ad"],
    ("Prime+", "Dark Cocoa"): ["#3b2a20", "#4a3428", "#5b4234", "#6a5040", "#775c4a"],
    ("Prime", "Dark Teak"): ["#4c3a2d", "#544133", "#5a4636"], ("Prime", "Maritime Gray"): ["#6b6f70", "#727677", "#787c7d"],
    ("Premier", "Dark Teak"): ["#4c3a2d", "#544133", "#5a4636"], ("Premier", "Maritime Gray"): ["#6b6f70", "#727677", "#787c7d"],
    ("Wood", "Cedar"): ["#9c6b3f", "#ad7a49", "#bd8a57", "#caa06c", "#d6b283"], ("Wood", "PT"): ["#9a8a5e", "#ab9a6a", "#b9a979", "#c6b78a", "#d1c49a"],
}
