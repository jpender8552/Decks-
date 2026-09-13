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
}
LUMBER_STOCK_FT = {"2x6": [8, 10, 12, 14, 16, 20], "2x8": [8, 10, 12, 14, 16, 20], "2x10": [8, 10, 12, 14, 16, 20, 24],
                   "2x12": [8, 10, 12, 14, 16, 20, 24], "4x8": [8, 10, 12, 16, 20], "4x10": [8, 10, 12, 16, 20], "4x12": [8, 10, 12, 16, 20],
                   "6x6": [8, 10, 12, 16], "6x8": [8, 10, 12, 16], "6x10": [8, 10, 12, 16], "6x12": [8, 10, 12, 16]}
SPECIES_NAMES = {"SYP": "#1 True Frame Joist SYP GC", "DF": "Douglas Fir #2", "SPF": "SPF #2", "HF": "Hem-Fir #2", "CEDAR": "Western Cedar #2"}


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
HANGER_FOR_JOIST = {"2x6": "LUS26Z", "2x8": "LUS28Z", "2x10": "LUS28Z", "2x12": "LUS210Z"}
HANGER_NAILS = {"LUS26Z": (4, 4), "LUS28Z": (6, 4), "LUS210Z": (8, 6)}       # (10d 3" into header, 10d x 1-1/2" into joist)
DOUBLE_HANGER = {"2x8": "HUCQ28-2-SDS", "2x10": "HUCQ210-2-SDS", "2x12": "HUCQ212-2-SDS"}
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
    "Fulton": dict(panels={72: 69.5, 96: 93.5}, post_w=2.0, bracket_allow=0.25, heights=[36, 42],
                   post_types=["END", "LINE", "CORNER", "STAIR"], note="2\" steel posts inside the outer rim ply; brackets, caps, skirts and screws ship with the posts"),
    "Impression": dict(panels={72: 70.0, 96: 94.0}, post_w=2.5, bracket_allow=0.25, heights=[36, 42], post_types=["POST"], note="aluminum"),
    "Classic Composite": dict(panels={72: 68.0, 96: 92.0}, post_w=5.5, bracket_allow=0.5, heights=[36, 42], post_types=["POST"], note="composite sleeve over 4x4"),
}


def tax_rate_for(city: str, override=None) -> float:
    if override is not None:
        return float(override)
    t = PRICEBOOK["tax_rates"]
    return float(t.get((city or "").strip().lower(), t["default"]))
