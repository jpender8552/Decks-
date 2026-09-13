"""GSX pricing model. Sell = (materials + tax + labor) / (1 - GM) + general conditions at cost.
General conditions are NEVER marked up, in sell or retail. Retail (financed) = (sell - GC) / 0.93 + GC.
Labor from GSX_Subcontractor_Labor_Rates. Tax is destination-based (delivery address)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .catalog import PRICEBOOK, tax_rate_for
from .takeoff import Takeoff


@dataclass
class Pricing:
    materials: float
    tax_rate: float
    tax: float
    labor_lines: List[Tuple[str, float, str, float, float]]   # (item, qty, unit, rate, ext)
    labor: float
    gc_base: float
    gc_extras: List[Tuple[str, float]]
    gc: float
    gm: float
    sell: float
    sell_floor: float          # at the 40% GM floor
    retail: float
    monthly: float
    gp: float
    commission: float
    allocation: List[Tuple[str, float]]
    categories: Dict[str, float]


def price(t: Takeoff, gm: float = None, tax_rate: float = None) -> Pricing:
    s, L = t.spec, t.layout
    pb = PRICEBOOK
    gm = gm if gm is not None else (s.extras.gm if s.extras.gm is not None else pb["gm_default"])
    gm = max(gm, pb["gm_floor"]) if gm < pb["gm_floor"] else gm
    rate = tax_rate_for(s.site.city, tax_rate if tax_rate is not None else s.site.tax_rate)
    cats: Dict[str, float] = {}
    mat = 0.0
    for ln in t.lines:
        if ln.category == "Site":
            continue
        cats[ln.category] = cats.get(ln.category, 0.0) + ln.ext
        mat += ln.ext
    tax = mat * rate
    lr = pb["labor"]
    sf = L.decking.sf
    lab = []
    lab.append(("Frame (GSX crew schedule)", sf, "SF", lr["frame_per_sf"]))
    lab.append(("Decking & fascia", sf, "SF", lr["decking_fascia_per_sf"]))
    if L.rail:
        lab.append(("Railing", L.rail.rail_lf, "LF", lr["rail_per_lf"]))
    if L.frame.footing_type == "diamond_pier":
        lab.append(("Diamond Pier install (replaces caisson)", L.frame.n_posts, "pier", lr["diamond_pier_each"]))
    else:
        lab.append(("Concrete piers (dig, form, pour)", L.frame.n_posts, "pier", lr["concrete_footing_each"]))
    for st in L.stairs:
        lab.append((f"Stairs ({st.side})", st.geo.risers, "riser", lr["stairs_per_riser"]))
    if s.extras.demo_existing:
        lab.append(("Demo existing deck + haul-off", s.extras.demo_sf or sf, "SF", lr["demo_per_sf"]))
    labor_lines = [(i, q, u, r, round(q * r, 2)) for i, q, u, r in lab]
    labor = sum(x[4] for x in labor_lines)
    gc_base = pb["general_conditions"]["per_sf"] * sf
    extras = [(x.get("item", "site extra"), float(x.get("cost", 0))) for x in s.extras.site_extras]
    gc = gc_base + sum(v for _, v in extras)
    sell = round((mat + tax + labor) / (1 - gm) + gc)
    sell_floor = round((mat + tax + labor) / (1 - pb["gm_floor"]) + gc)
    retail = round((sell - gc) / pb["retail_factor"] + gc)
    r = pb["finance_rate"] / 12
    n = pb["finance_years"] * 12
    monthly = retail * r / (1 - (1 + r) ** -n)
    gp = sell - gc - mat - tax - labor
    comm = 0.10 * sell
    # client allocation: sell values by scope, GC at cost, summing exactly to sell
    ld = {i: e for i, q, u, rt, e in labor_lines}
    frame_mat = sum(cats.get(c, 0.0) for c in ("Lumber", "Footings", "Hardware", "Flashing & waterproofing"))
    frame_lab = ld.get("Frame (GSX crew schedule)", 0) + ld.get("Diamond Pier install (replaces caisson)", 0) + ld.get("Concrete piers (dig, form, pour)", 0)
    deck_mat = cats.get("Decking", 0) + cats.get("Fasteners", 0) + cats.get("Fascia", 0)
    rail_mat = cats.get("Rail", 0)
    stair_mat = cats.get("Stairs", 0)
    stair_lab = sum(v for k, v in ld.items() if k.startswith("Stairs"))
    alloc = []
    if s.extras.demo_existing:
        alloc.append(("Demolition & haul-off", round(ld.get("Demo existing deck + haul-off", 0) / (1 - gm))))
    alloc.append(("Foundation & structure", round((frame_mat * (1 + rate) + frame_lab) / (1 - gm))))
    alloc.append(("Decking & fascia", round((deck_mat * (1 + rate) + ld.get("Decking & fascia", 0)) / (1 - gm))))
    if L.rail:
        alloc.append(("Railing", round((rail_mat * (1 + rate) + ld.get("Railing", 0)) / (1 - gm))))
    if L.stairs:
        alloc.append(("Stairs", round((stair_mat * (1 + rate) + stair_lab) / (1 - gm))))
    alloc.append(("Site & project services", round(gc)))
    diff = sell - sum(a[1] for a in alloc)
    i = 1 if s.extras.demo_existing else 0
    alloc[i] = (alloc[i][0], alloc[i][1] + diff)
    return Pricing(round(mat, 2), rate, round(tax, 2), labor_lines, round(labor, 2), gc_base, extras, gc, gm, sell, sell_floor, retail,
                   round(monthly, 2), round(gp, 2), round(comm, 2), alloc, cats)
