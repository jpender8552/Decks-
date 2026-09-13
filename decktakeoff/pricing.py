"""GSX pricing model (Eagle's Nest standard).
  sell (check or ACH) = (materials + destination tax + labor) / (1 - GM) + general conditions at cost
  financed            = sell / 0.93  (retail_mode "uniform"; "gc_at_cost" keeps GC out of the 7%)
  monthly             = financed at 6.99% / 10 yr; 12- and 18-month no-payment programs
Options are priced both ways by re-running the engine with the option's changes applied (delta), plus any fixed cost.
Engineering, when the job is engineered, is billed at cost with no markup and shown separately."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .catalog import PRICEBOOK, tax_rate_for
from .spec import DeckSpec, Option
from .takeoff import Takeoff


@dataclass
class OptionPrice:
    name: str
    financed: float          # signed: + adder, - deduct
    check: float
    note: str = ""


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
    sell: float                # check or ACH
    sell_floor: float          # at the 40% GM floor
    retail: float              # financed
    monthly: float
    gp: float
    commission: float
    allocation: List[Tuple[str, float]]     # what the price includes (check/ACH values, sums to sell)
    categories: Dict[str, float]
    retail_mode: str = "uniform"
    engineering: Optional[Tuple[float, float]] = None
    options: List[OptionPrice] = field(default_factory=list)


def labor_lines_for(t: Takeoff) -> List[Tuple[str, float, str, float]]:
    s, L = t.spec, t.layout
    lr = PRICEBOOK["labor"]
    sf = L.deck_sf
    timber = s.is_timber
    pvc_cortex = (s.decking.fastener_system == "Cortex") or (s.decking.profile == "square" and s.decking.fastener_system is None)
    lab = []
    if timber:
        lab.append(("Timber frame (DF #1, black hardware)", sf, "SF", lr["timber_frame_per_sf"]))
    else:
        lab.append(("Frame (GSX crew schedule)", sf, "SF", lr["frame_per_sf"]))
    if pvc_cortex:
        lab.append(("Decking, borders & Cortex plugs", sf, "SF", lr["pvc_cortex_decking_per_sf"]))
    else:
        lab.append(("Decking & fascia", sf, "SF", lr["decking_fascia_per_sf"]))
    if L.rail:
        from .catalog import RAIL_SYSTEMS
        cable = RAIL_SYSTEMS.get(L.rail.system, {}).get("cable", False)
        lab.append(("Cable rail" if cable else "Railing", L.rail.rail_lf, "LF", lr["cable_rail_per_lf"] if cable else lr["rail_per_lf"]))
        if s.railing.drink_rail:
            lab.append(("Drink rail", L.rail.rail_lf, "LF", lr["drink_rail_per_lf"]))
    n_posts = sum(z.frame.n_posts for z in L.zones)
    ft = s.framing.footing_type
    if ft == "diamond_pier":
        lab.append(("Diamond Pier install (replaces caisson)", n_posts, "pier", lr["diamond_pier_each"]))
    elif ft == "caisson":
        lab.append(("Caissons (auger, rebar, pour)", n_posts, "ea", lr["caisson_each"]))
    else:
        lab.append(("Concrete piers (dig, form, pour)", n_posts, "pier", lr["concrete_footing_each"]))
    if s.extras.stone_bases:
        lab.append(("Stone column bases (mason)", n_posts, "ea", lr["stone_base_each"]))
    if timber and s.framing.finish == "oil":
        lab.append(("Timber oil finish, 2 coats", round(_timber_sf(t)), "SF", lr["oil_finish_per_sf_timber"]))
    if s.extras.hot_tub:
        lab.append(("Hot-tub bay doubling", 1, "ea", lr["hot_tub_bay_each"]))
    if timber and s.geometry.attachment == "ledger":
        wall_lf = sum(z.W for z in L.zones) / 12.0
        lab.append(("Metal flashing at every wall", round(wall_lf), "LF", lr["wall_flashing_per_lf"]))
    for st in L.stairs:
        lab.append((f"Stairs ({st.side})", st.geo.risers, "riser", lr["stairs_per_riser"]))
    if s.extras.demo_existing:
        lab.append(("Demo existing deck + haul-off", s.extras.demo_sf or sf, "SF", lr["demo_per_sf"]))
    return lab


def _timber_sf(t: Takeoff) -> float:
    for ln in t.lines:
        if ln.category == "Finish" and "oil" in ln.item.lower():
            # why: "+1  (1,234 SF of timber x 2 coats)"
            try:
                return float(ln.why.split("(")[1].split(" SF")[0].replace(",", ""))
            except Exception:
                pass
    # fall back: estimate from joists + beams
    return sum(z.frame.joist_len * (len(z.frame.joist_x) + len(z.frame.pf_x)) for z in t.layout.zones) * 2 * (3.5 + 9.25) / 144


def price(t: Takeoff, gm: float = None, tax_rate: float = None, with_options: bool = True) -> Pricing:
    s, L = t.spec, t.layout
    pb = PRICEBOOK
    gm = gm if gm is not None else (s.extras.gm if s.extras.gm is not None else pb["gm_default"])
    gm = max(gm, pb["gm_floor"])
    rate = tax_rate_for(s.site.city, tax_rate if tax_rate is not None else s.site.tax_rate)
    cats: Dict[str, float] = {}
    mat = 0.0
    for ln in t.lines:
        if ln.category == "Site":
            continue
        cats[ln.category] = cats.get(ln.category, 0.0) + ln.ext
        mat += ln.ext
    tax = mat * rate
    lab = labor_lines_for(t)
    labor_lines = [(i, q, u, r, round(q * r, 2)) for i, q, u, r in lab]
    labor = sum(x[4] for x in labor_lines)
    sf = L.deck_sf
    gc_base = pb["general_conditions"]["per_sf"] * sf
    extras = [(x.get("item", "site extra"), float(x.get("cost", 0))) for x in s.extras.site_extras]
    gc = gc_base + sum(v for _, v in extras)
    mode = pb.get("retail_mode", "uniform")
    sell = round((mat + tax + labor) / (1 - gm) + gc)
    sell_floor = round((mat + tax + labor) / (1 - pb["gm_floor"]) + gc)
    retail = round(sell / pb["retail_factor"]) if mode == "uniform" else round((sell - gc) / pb["retail_factor"] + gc)
    r = pb["finance_rate"] / 12
    n = pb["finance_years"] * 12
    monthly = retail * r / (1 - (1 + r) ** -n)
    gp = sell - gc - mat - tax - labor
    comm = 0.10 * sell
    # client allocation: check/ACH values by scope, GC at cost, summing exactly to sell
    ld = {i: e for i, q, u, rt, e in labor_lines}
    def labsum(*prefixes):
        return sum(v for k, v in ld.items() if any(k.startswith(p) for p in prefixes))
    frame_mat = sum(cats.get(c, 0.0) for c in ("Lumber", "Footings", "Hardware", "Flashing & waterproofing", "Finish"))
    stone_mat = sum(l.ext for l in t.lines if "Stone column base" in l.item)
    frame_mat -= stone_mat
    frame_lab = labsum("Frame", "Timber frame", "Diamond Pier", "Caissons", "Concrete piers", "Hot-tub", "Metal flashing", "Timber oil")
    deck_mat = cats.get("Decking", 0) + cats.get("Fasteners", 0) + cats.get("Fascia", 0)
    deck_lab = labsum("Decking")
    drink_mat = sum(l.ext for l in t.lines if "drink rail" in l.item.lower())
    rail_mat = cats.get("Rail", 0) - drink_mat
    rail_lab = labsum("Railing", "Cable rail")
    drink_lab = labsum("Drink rail")
    stair_mat = cats.get("Stairs", 0)
    stair_lab = labsum("Stairs")
    alloc = []
    if s.extras.demo_existing:
        alloc.append(("Demolition & haul-off", round(ld.get("Demo existing deck + haul-off", 0) / (1 - gm))))
    core = (frame_mat + deck_mat + rail_mat) * (1 + rate) + frame_lab + deck_lab + rail_lab
    if s.is_timber:
        alloc.append((f"{'Timber-frame' if s.is_timber else ''} deck: caissons, frame, decking, rail, hardware, site protection, delivery, cleanup".replace("  ", " "), round(core / (1 - gm))))
    else:
        alloc.append(("Foundation & structure", round((frame_mat * (1 + rate) + frame_lab) / (1 - gm))))
        alloc.append(("Decking & fascia", round((deck_mat * (1 + rate) + deck_lab) / (1 - gm))))
        if L.rail:
            alloc.append(("Railing", round((rail_mat * (1 + rate) + rail_lab) / (1 - gm))))
    if s.extras.stone_bases:
        alloc.append((f"Stone column bases at all {sum(z.frame.n_posts for z in L.zones)} posts", round((stone_mat * (1 + rate) + labsum("Stone column")) / (1 - gm))))
    if s.railing.drink_rail and L.rail:
        alloc.append((f"{s.railing.drink_rail_color or ''} drink rail on the rail".strip(), round((drink_mat * (1 + rate) + drink_lab) / (1 - gm))))
    if L.stairs:
        alloc.append(("Stairs", round((stair_mat * (1 + rate) + stair_lab) / (1 - gm))))
    alloc.append(("Site & project services", round(gc)))
    diff = sell - sum(a[1] for a in alloc)
    i = 1 if s.extras.demo_existing else 0
    alloc[i] = (alloc[i][0], alloc[i][1] + diff)
    engineering = (s.extras.engineering_fee_low, s.extras.engineering_fee_high) if s.extras.engineered else None
    pr = Pricing(round(mat, 2), rate, round(tax, 2), labor_lines, round(labor, 2), gc_base, extras, gc, gm, sell, sell_floor, retail,
                 round(monthly, 2), round(gp, 2), round(comm, 2), alloc, cats, mode, engineering)
    if with_options and s.extras.options:
        pr.options = price_options(t, pr, gm)
    return pr


def _deep_merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def price_options(t: Takeoff, base: Pricing, gm: float) -> List[OptionPrice]:
    """Each option re-runs the engine with its changes and prices the delta both ways; fixed costs are marked up like
    any other direct cost. Sign: + adder, - deduct."""
    from .takeoff import build_takeoff
    pb = PRICEBOOK
    out = []
    base_dict = t.spec.to_dict()
    base_dict["extras"]["options"] = []
    for o in t.spec.extras.options:
        delta_sell = 0.0
        note = o.note
        if o.changes:
            try:
                sp2 = DeckSpec.from_dict(_deep_merge(base_dict, o.changes))
                t2 = build_takeoff(sp2)
                p2 = price(t2, gm=gm, tax_rate=base.tax_rate, with_options=False)
                delta_sell += p2.sell - base.sell
            except Exception as e:  # an option that can't be built is reported, never silently dropped
                note = (note + "; " if note else "") + f"could not price change: {e}"
        if o.cost:
            delta_sell += o.cost / (1 - gm)
        check = round(delta_sell)
        financed = round(check / pb["retail_factor"]) if base.retail_mode == "uniform" else round(check / pb["retail_factor"])
        out.append(OptionPrice(o.name, financed, check, note))
    return out
