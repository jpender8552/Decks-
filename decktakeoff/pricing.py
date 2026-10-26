"""GSX pricing model — the Eagle's Nest standard (handoff v32, 8 Sep 2026):
  materials at quoted / EST unit costs × 1.15 (owner), sales tax 4% on factored materials
  labor per the GSX Subcontractor Labor Rates card (rev 14 Jul 2026), base rates + add-ons, no timber / steel / PVC up-charges
  general conditions itemized and carried AT COST, no margin
  sell (check or ACH) = (materials × 1.15 + tax + labor) ÷ (1 − GM) + GC ;  GM target 42.5%, floor 40%
  financed (retail) = sell ÷ 0.93 ; 12 / 18 months no payments, or 6.99% × 10 yr (monthly shown)
  engineering (stamped set) outside the price: a range at cost, no markup; the homeowner owns the set
  options = full installed deltas: cost delta ÷ (1 − GM), both prices
Jason Ct (dimensional) uses the same engine with tax 8.5% destination, factor 1.0, GM 45% and $4/SF GC set on the job."""
from __future__ import annotations
from .units import ftin

import math
import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .catalog import PRICEBOOK, RAIL_SYSTEMS, tax_rate_for
from .spec import covers_of, DeckSpec
from .takeoff import Takeoff


@dataclass
class OptionPrice:
    name: str
    financed: float          # signed: + adder, - deduct
    check: float
    cost: float
    note: str = ""


@dataclass
class Pricing:
    materials: float             # raw
    material_factor: float
    materials_factored: float
    tax_rate: float
    tax: float
    labor_lines: List[Tuple[str, float, str, float, float]]   # (item, qty, unit, rate, ext)
    labor: float
    gc_lines: List[Tuple[str, float, str]]                     # (item, amount, why)
    gc: float
    work: float                  # materials factored + tax + labor (carries the margin)
    cost: float                  # work + GC
    gm: float
    sell: float                  # check or ACH
    sell_floor: float            # at the 40% GM floor
    retail: float                # financed
    monthly: float
    gp: float
    commission: float
    allocation: List[Tuple[str, float]]     # what the price includes (sell values, sums to sell)
    categories: Dict[str, float]
    sell_per_sf: float = 0.0
    engineering: Optional[Tuple[float, float]] = None
    options: List[OptionPrice] = field(default_factory=list)
    dealer_fee_note: str = ""
    gc_base: float = 0.0
    gc_extras: List[Tuple[str, float]] = field(default_factory=list)
    rail_note: str = ""          # "rail at $120/LF, the rest at 45% GM" when the rail sells at a fixed rate


BUILTIN_AT_GM = 0.40          # the owner's built-in section prices carry 40%: materials (factored, taxed) + labor = 60% of the sell


def _factor_rate(s) -> Tuple[float, float]:
    pb = PRICEBOOK
    factor = s.extras.material_factor if s.extras.material_factor is not None else pb.get("material_factor", 1.0)
    if s.site.tax_rate is not None:
        rate = float(s.site.tax_rate)
    elif pb.get("tax_mode", "flat") == "destination":
        rate = tax_rate_for(s.site.city)
    else:
        rate = pb.get("tax_rate", 0.04)
    return factor, rate


def builtin_sells(s) -> List[Tuple[str, str, int, float]]:
    """(category, label, sections, sell) for built-ins the owner prices per section (extras.builtin_sell)."""
    from .scene import bench_segments, planter_segments
    bs = s.extras.builtin_sell or {}
    out = []
    if s.geometry.benches and bs.get("bench"):
        n = len(bench_segments(s))
        out.append(("Benches", f"Built-in benches — {n} sections, 17\" seat, back, 4x4 posts wrapped in deck board", n, float(bs["bench"]) * n))
    if s.geometry.planters and bs.get("planter"):
        n = len(planter_segments(s))
        out.append(("Planters", f"Built-in planter{'s' if n > 1 else ''} — 17\" x 17\", deck board on all sides, picture-frame cap", n, float(bs["planter"]) * n))
    return out


def labor_lines_for(t: Takeoff) -> List[Tuple[str, float, str, float, str]]:
    """(line, qty, unit, rate, note) per the rate card."""
    s, L = t.spec, t.layout
    lr = dict(PRICEBOOK["labor"]); lr.update(s.extras.labor_rates or {})
    sf = L.deck_sf
    timber = s.is_timber
    n_posts = L.n_footings
    lab = []
    if s.extras.demo_existing:
        lab.append(("Demolition — existing deck", s.extras.demo_sf or sf, "SF", lr["demo_per_sf"], "base rate; field verify the existing deck"))
    ft = s.framing.footing_type
    if ft == "diamond_pier":
        n_piers = n_posts
        if t.order_ref:   # the owner's quoted order governs: every pier on it gets set
            q = sum(l.order for l in t.lines if "diamond pier" in l.item.lower())
            n_piers = int(q) if q else n_posts
        lab.append(("Diamond Pier install", n_piers, "pier", lr["diamond_pier_each"], "rate card" + (" · count from the quoted order" if n_piers != n_posts else "")))
    elif ft == "caisson":
        lab.append((f"Caissons {int(L.frame.footing_dia_in)}\" x {L.frame.footing_depth_in / 12:.1f}' (frost {s.site.frost_depth_in:g}\")", n_posts, "hole", lr["caisson_each"], "base rate"))
        if L.frame.footing_dia_in >= 20:
            lab.append(("Large footings 20\" add-on", n_posts, "footing", lr["large_footing_addon_each"], "rate card add-on"))
    elif ft == "existing":
        if not s.framing.existing_posts:
            lab.append(("Set standoff bases on the existing caissons (epoxy anchors)", n_posts, "ea", 45.0, "EST — no rate-card line"))
    else:
        lab.append(("Concrete piers (dig, form, pour)", n_posts, "pier", lr["concrete_footing_each"], "rate card"))
    lab.append(("Frame", sf, "SF", lr["frame_per_sf"], "base rate" + (" — no larger-timber / 12\" OC up-charge (owner 7 Sep 2026)" if timber else "")))
    lab.append((f"Decking{' (no fascia)' if not s.decking.fascia else ' & fascia'}", sf, "SF", lr["decking_fascia_per_sf"], "base rate" + (" — no PVC up-charge" if s.decking.collection in ("Vintage", "Landmark", "Harvest+", "Harvest") else "")))
    if L.rail:
        cable = RAIL_SYSTEMS.get(L.rail.system, {}).get("cable", False)
        lab.append(("Railing", L.rail.rail_lf, "LF", lr["rail_per_lf"], "base rate"))
        if cable:
            lab.append(("Cable rail add-on", L.rail.rail_lf, "LF", lr["cable_rail_addon_per_lf"], "rate card add-on"))
        if s.railing.drink_rail:
            lab.append(("Drink rail add-on", L.rail.rail_lf, "LF", lr["drink_rail_per_lf"], "rate card add-on"))
    n_beam_lines = len(L.beam_lines)
    n_extra = s.extras.extra_beam_sets if s.extras.extra_beam_sets is not None else max(0, n_beam_lines - 1)
    if n_extra > 0:
        lab.append(("Extra beam set", n_extra, "set", lr["extra_beam_set"], "rate card add-on" + (" · job-set count" if s.extras.extra_beam_sets is not None else "")))
    lab = [x for x in lab if x[3] and x[1]]      # a zero rate (job override) or a zero count drops the line
    if s.extras.hot_tub:
        lab.append(("Hot-tub bay framing + coordination with the tub set / electrician", 1, "ea", lr["hot_tub_bay_each"], "EST"))
    if s.extras.stone_bases:
        lab.append((f"Stone column bases 2' x 2' x 3' — {n_posts} posts (mason)", n_posts, "ea", lr["stone_base_each"], "EST"))
    if timber and s.framing.end_grain_seal and s.framing.finish != "oil":
        lab.append(("Seal every cut end (base — no oil)", 1, "lot", lr["seal_cut_ends_lot"], "EST"))
    if timber and s.framing.finish == "oil":
        lab.append(("Timber oil — pre-oil the 4x10 joists / rims / ledgers on horses, coat 1 all faces", round(t.joist_lf), "LF", lr["oil_pre_oil_per_lf"], "EST — no rate-card line"))
        lab.append(("Timber oil — posts + beams 2 coats, coat 2 on the whole frame in place, end-grain seal, touch-up", 1, "lot", lr["oil_in_place_lot"] + lr["seal_cut_ends_lot"], "EST"))
    import re as _re
    for ss_, st in zip(list(s.stairs) + [None] * len(L.stairs), L.stairs):       # the stair by its name, else by the side it leaves
        nm_ = getattr(ss_, "name", None) or _re.sub(r"\bedge:(\d+)", r"side \1", f"Stairs ({st.side})")
        lab.append((f"{nm_}" + (f" — {len(st.geo.flights)} flights" if len(st.geo.flights) > 1 else ""), st.geo.risers, "riser", lr["stairs_per_riser"], "rate card"))
        if st.landing_rail_lf:
            lab.append((f"Landing guard rail ({nm_})", st.landing_rail_lf, "LF", lr["rail_per_lf"], "base rate"))
    for ss in s.stairs:
        for lw, ld in ss.landings or []:
            sf_l = float(lw) * float(ld) / 144
            lab.append((f"Stair landing {ftin(float(lw))} x {ftin(float(ld))} — frame, deck, 4 footings", round(sf_l, 1), "SF", lr["frame_per_sf"] + lr["decking_fascia_per_sf"] + 40.0, "EST — frame + decking rate + footings"))
    _covs = covers_of(s)
    if _covs and s.extras.cover_labor_total is not None:
        lab.append((f"Porch cover — {'both roof covers' if len(_covs) > 1 else 'roof cover'}: posts, ledger, beam, rafters, sheathing, roofing, Hardie, set on the piers",
                    1, "lot", float(s.extras.cover_labor_total), "owner-set total, roofing included"))
    for _c in _covs:
        from .takeoff import cover_size, cover_posts_x
        along, out, area = cover_size(s, _c)
        nm = "Porch cover" + (f" ({_c['name']})" if len(_covs) > 1 else "")
        if s.extras.cover_labor_total is not None:
            if s.extras.demo_covers:
                lab.append((f"{nm} — tear off the existing roof cover and haul", round(area), "SF", lr.get("cover_demo_per_sf", 3.0), "ESTIMATE — no cover demo rate on the card; confirm"))
            continue
        lab.append((f"{nm} — frame, sheath, roof, ceiling", round(area), "SF", lr["cover_per_sf"], "ESTIMATE — no cover rate on the card; confirm"))
        if _c.get("footing", "deck") == "diamond_pier":
            lab.append((f"{nm} — Diamond Pier install at the cover posts", len(cover_posts_x(_c)), "pier", lr["diamond_pier_each"], "rate card"))
        elif _c.get("footing") == "deck_pier":
            lab.append((f"{nm} — set the cover posts on the shared deck piers, bracket the deck beam to them", len(cover_posts_x(_c)), "post", 45.0, "EST"))
        else:
            lab.append((f"{nm} — post blocking in the deck frame", 1, "lot", lr["cover_post_blocking_lot"], "est."))
        if s.extras.cover_roof.lower().startswith("standing"):
            lab.append((f"{nm} — standing seam steel in place of shingles (panels, trims, headwall, snow bar)", round(area), "SF", lr["cover_standing_seam_adder_per_sf"], "ESTIMATE — metal roofer's install rate; confirm"))
        if s.extras.cover_gutters:
            lab.append((f"{nm} — 5\" gutter + downspouts hung", round(along), "LF", lr["gutters_per_lf"], "ESTIMATE — gutter sub; confirm"))
        if s.extras.demo_covers:
            lab.append((f"{nm} — tear off the existing roof cover and haul", round(area), "SF", lr.get("cover_demo_per_sf", 3.0), "ESTIMATE — no cover demo rate on the card; confirm"))
    if s.extras.under_deck_gravel:
        lab.append(("Under-deck prep — 6-mil poly + 2\" gravel", round(t.layout.deck_sf), "SF", lr.get("under_deck_gravel_per_sf", 1.5), "ESTIMATE — confirm"))
    if s.framing.system == "steel" and lr.get("steel_frame_premium_per_sf"):     # rate card: no steel up-charge unless the job sets one
        lab.append(("Steel frame premium — cut, clip and screw cold-formed members", round(t.layout.deck_sf), "SF", lr["steel_frame_premium_per_sf"], "ESTIMATE — no steel rate on the card; confirm with the framer"))
    fixed_cats = {c for c, *_ in builtin_sells(s)}
    if s.geometry.benches and "Benches" not in fixed_cats:
        from .scene import bench_segments
        blf = sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1, *_ in bench_segments(s))
        lab.append(("Built-in benches — frame, seat, apron and back (rebuilt in the existing footprint)", round(blf, 1), "LF", lr.get("bench_per_lf", 75.0),
                    "rate card" if "bench_per_lf" in lr else "ESTIMATE — no bench rate on the card; confirm"))
    if fixed_cats:
        factor, rate = _factor_rate(s)
        for cat, label, n, sell in builtin_sells(s):
            mats = sum(l.ext for l in t.lines if l.category == cat) * factor * (1 + rate)
            lab.append((f"{label}: build and install", 1, "lot", round(max(0.0, sell * (1 - BUILTIN_AT_GM) - mats), 2),
                        f"owner-set: ${sell / n:,.0f} per section at {BUILTIN_AT_GM:.0%}, less its materials"))
    if getattr(s.geometry, "door_step", None):
        lab.append(("Door step — frame, deck and riser (the existing step rebuilt)", 1, "lot", lr.get("door_step_lot", 250.0), "ESTIMATE — confirm"))
    for sl in s.geometry.sails or []:
        n_p = len(sl.get("posts", []))
        deck_m = sl.get("mount") == "deck_rail"
        lab.append(((f"Shade sail — {n_p} steel post{'s' if n_p != 1 else ''} base-plated on the deck as the rail corner{'s' if n_p != 1 else ''}, blocking, house anchors, hang and tension" if deck_m else
                     f"Shade sail — {n_p} steel posts set in augered footings (lift + auger rental), house anchors, hang and tension") if n_p else "Shade sail — house anchors, hang and tension",
                    1, "lot", float(sl.get("labor_lot", 900.0 + (350.0 if deck_m else 750.0) * n_p)), "ESTIMATE — no sail rate on the card; confirm"))
    if s.extras.blinds_reinstall and _covs:
        lab.append(("Take down, store and rehang the owner's roll-down blinds on the new beams", 1, "lot", lr.get("blinds_reinstall_lot", 250.0), "ESTIMATE — confirm"))
    return lab


def gc_lines_for(t: Takeoff) -> Tuple[List[Tuple[str, float, str]], float, List[Tuple[str, float]]]:
    s, L = t.spec, t.layout
    if s.extras.no_general_conditions:
        return [], 0.0, []
    if s.extras.general_conditions:
        return [(g.get("item", "GC"), float(g.get("amount", 0)), g.get("why", "")) for g in s.extras.general_conditions], 0.0, []
    base = PRICEBOOK["general_conditions"]["per_sf"] * L.deck_sf
    extras = [(x.get("item", "site extra"), float(x.get("cost", 0))) for x in s.extras.site_extras]
    return [("General conditions", base, f"${PRICEBOOK['general_conditions']['per_sf']:g}/SF x {L.deck_sf:g} SF")] + [(i, v, "at cost") for i, v in extras], base, extras


def price(t: Takeoff, gm: float = None, tax_rate: float = None, with_options: bool = True) -> Pricing:
    s, L = t.spec, t.layout
    pb = PRICEBOOK
    gm = gm if gm is not None else (s.extras.gm if s.extras.gm is not None else pb["gm_default"])
    if not s.extras.gm_below_floor:
        gm = max(gm, pb["gm_floor"])
    factor = s.extras.material_factor if s.extras.material_factor is not None else pb.get("material_factor", 1.0)
    if tax_rate is not None:
        rate = tax_rate
    elif s.site.tax_rate is not None:
        rate = float(s.site.tax_rate)
    elif pb.get("tax_mode", "flat") == "destination":
        rate = tax_rate_for(s.site.city)
    else:
        rate = pb.get("tax_rate", 0.04)
    # owner rule: a rail system sold per LF at a set margin fixes its installed COST too (rate x (1 - at_gm)): the rail lines'
    # estimated prices scale so materials (factored, taxed) + rail labor land on that cost
    _rule = pb.get("rail_sell_per_lf", {})
    _r0 = s.extras.rail_sell_per_lf if s.extras.rail_sell_per_lf is not None else (_rule.get(L.rail.system) if L.rail else None)
    _fixed = isinstance(_r0, dict)          # {sell, cost}: the owner's installed sell and cost per LF, no scaling
    if _r0 and L.rail and not getattr(t, "_rail_cost_set", False):
        own = (float(_r0["cost"]) if _fixed else float(_r0) * (1 - _rule.get("_at_gm", 0.40))) * L.rail.rail_lf
        r_lab = sum(q * r_ for i, q, u, r_, n in labor_lines_for(t) if i.startswith(("Railing", "Cable rail")))
        r_lines = [l for l in t.lines if l.category == "Rail" and not ("rink rail" in l.item or "drink-rail" in l.item)]
        r_mat = sum(l.ext for l in r_lines) * factor * (1 + rate)
        if r_mat > 0 and own > r_lab:
            k = (own - r_lab) / r_mat
            for l in r_lines:
                l.unit_cost = round(l.unit_cost * k, 4)
                l.source = f"{l.source} · scaled to the owner's " + (f"${float(_r0['cost']):,.0f}/LF installed cost" if _fixed else f"${float(_r0):,.0f}/LF at {_rule.get('_at_gm', 0.40):.0%}")
        t._rail_cost_set = True
    cats: Dict[str, float] = {}
    mat = 0.0
    for ln in t.lines:
        if ln.category == "Site":
            continue
        cats[ln.category] = cats.get(ln.category, 0.0) + ln.ext
        mat += ln.ext
    mat_f = mat * factor
    tax = float(s.quoted_tax) if (s.quoted_order and s.quoted_tax is not None) else mat_f * rate
    lab = labor_lines_for(t)
    if s.extras.labor_total is not None:      # owner-set total labor: owner-set lots stay, every other line scales to make up the rest
        fixed = sum(q * r for i, q, u, r, n in lab if str(n).startswith("owner-set"))
        others = sum(q * r for i, q, u, r, n in lab if not str(n).startswith("owner-set"))
        k = max(0.0, float(s.extras.labor_total) - fixed) / others if others else 1.0
        lab = [(i, q, u, r if str(n).startswith("owner-set") else round(r * k, 4), n if str(n).startswith("owner-set") else f"{n} · scaled to the owner's ${s.extras.labor_total:,.0f} total")
               for i, q, u, r, n in lab]
    labor_lines = [(i, q, u, r, round(q * r, 2)) for i, q, u, r, n in lab]
    labor = sum(x[4] for x in labor_lines)
    gc_lines, gc_base, gc_extras = gc_lines_for(t)
    gc = sum(a for _, a, _ in gc_lines)
    work = mat_f + tax + labor
    cost = work + gc
    # a rail system sold at a fixed installed price per LF: that LF sells at the rate, the rest of the job carries the margin
    rate_lf = s.extras.rail_sell_per_lf
    if rate_lf is None and L.rail:          # 0 on a job = quoted before the rule, keep the margin pricing
        rate_lf = pb.get("rail_sell_per_lf", {}).get(L.rail.system)
    if isinstance(rate_lf, dict):              # owner's fixed installed sell per LF
        rate_lf = float(rate_lf["sell"])
    elif rate_lf:                              # the rate is quoted at the rule's margin (40%): scale it to this job's GM
        rate_lf = float(rate_lf) * (1 - pb.get("rail_sell_per_lf", {}).get("_at_gm", gm)) / (1 - gm)
    rail_sell = round(float(rate_lf) * L.rail.rail_lf, 2) if (rate_lf and L.rail) else 0.0
    rail_work = 0.0
    if rail_sell:
        _lr = sum(e for i, q, u, r_, e in labor_lines if i.startswith(("Railing", "Cable rail")))
        _rm = sum(l.ext for l in t.lines if l.category == "Rail" and not ("rink rail" in l.item or "drink-rail" in l.item))
        rail_work = _rm * factor * (1 + rate) + _lr
    # built-ins the owner prices per section: they sell at that price; their materials + labor come off the margin base
    bsell = builtin_sells(s)
    builtin_sell = sum(v for *_, v in bsell)
    builtin_work = 0.0
    for cat, label, n, sv in bsell:
        builtin_work += sum(l.ext for l in t.lines if l.category == cat) * factor * (1 + rate)
        builtin_work += sum(e for i, q, u, r_, e in labor_lines if i.startswith(label))
    sell = round((work - rail_work - builtin_work) / (1 - gm) + rail_sell + builtin_sell + gc)
    sell_floor = round((work - rail_work - builtin_work) / (1 - pb["gm_floor"]) + rail_sell + builtin_sell + gc)
    gm_base = gm
    if (rail_sell or builtin_sell) and not s.extras.sell_override:
        gm = 1 - work / max(sell - gc, 1)          # the blended margin the job carries
    if s.extras.sell_override:
        sell = round(float(s.extras.sell_override))
        gm = 1 - work / max(sell - gc, 1)          # the margin the override actually carries
    retail = round(sell * (1 + s.extras.retail_markup)) if s.extras.retail_markup is not None else round(sell / pb["retail_factor"])
    r = pb["finance_rate"] / 12
    n = pb["finance_years"] * 12
    monthly = retail * r / (1 - (1 + r) ** -n)
    gp = sell - cost
    comm = 0.10 * sell
    # ---- what the price includes (sell values): components broken out the way the homeowner buys them
    ld = {i: e for i, q, u, rt, e in labor_lines}
    def labsum(*prefixes):
        return sum(v for k, v in ld.items() if any(k.startswith(p) for p in prefixes))
    def mats(pred):
        return sum(l.ext for l in t.lines if l.category != "Site" and pred(l))
    def comp(m, l_):
        return (m * factor * (1 + rate) + l_) / (1 - (gm_base if rail_sell and not s.extras.sell_override else gm))
    stone_m = mats(lambda l: "Stone veneer column base" in l.item)
    drink_m = mats(lambda l: "rink rail" in l.item or "drink-rail" in l.item)
    oil_m = mats(lambda l: l.category == "Finish" and ("oil" in l.item.lower() or "Sprayer" in l.item))
    alloc = []
    if s.extras.demo_existing and not s.is_timber:
        alloc.append(("Demolition & haul-off", round(labsum("Demolition") / (1 - gm))))
    rest = sell - gc - sum(a[1] for a in alloc)
    parts = []
    if s.extras.stone_bases:
        parts.append((f"Stone column bases at all {sum(z.frame.n_posts for z in L.zones)} posts", round(comp(stone_m, labsum("Stone column")))))
    if s.is_timber and s.framing.finish == "oil":
        parts.append(("Dark walnut oil finish, two coats, every timber", round(comp(oil_m, labsum("Timber oil")) - PRICEBOOK["labor"]["seal_cut_ends_lot"] / (1 - gm))))
    if s.railing.drink_rail and L.rail:
        parts.append((f"{s.railing.drink_rail_color or ''} drink rail on the {'cable ' if RAIL_SYSTEMS.get(L.rail.system, {}).get('cable') else ''}rail".strip(), round(comp(drink_m, labsum("Drink rail")))))
    if covers_of(s):
        cover_m = mats(lambda l: l.category == "Porch cover")
        n_cv = len(covers_of(s))
        finish = ("Hardie soffit, fascia and rakes" if (s.extras.cover_soffit or s.extras.cover_fascia) else "T&G ceiling")
        roof = ("standing seam steel roof with snow retention" if s.extras.cover_roof.lower().startswith("standing") else "shingles") + (", gutter and downspouts" if s.extras.cover_gutters else "")
        lead = "Porch cover — shed roof" if n_cv == 1 else f"{n_cv} roof covers — lean-to roofs"
        parts.append((f"{lead} on 6x6 {'Douglas fir' if s.extras.cover_post_species.upper().startswith('DF') else 'cedar'} posts, {roof}, {finish}" + (", existing covers torn off" if s.extras.demo_covers else "") + (", blinds rehung" if s.extras.blinds_reinstall else ""),
                      round(comp(cover_m, labsum("Porch cover") + labsum("Take down, store")))))
    main = rest - sum(v for _, v in parts)
    if s.is_timber:
        label = ("Timber-frame deck: caissons, Douglas fir frame (end grain sealed), " + f"{s.decking.color} decking, "
                 + (f"{L.rail.system} {'cable ' if RAIL_SYSTEMS.get(L.rail.system, {}).get('cable') else ''}rail, " if L.rail else "")
                 + ("black hardware, " if s.framing.hardware_finish == "black" else "") + "site protection, delivery, cleanup")
        alloc.append((label, round(main)))
        alloc += parts
    else:
        frame_m = mats(lambda l: l.category in ("Lumber", "Footings", "Hardware", "Flashing & waterproofing") and "Stone" not in l.item)
        deck_m = mats(lambda l: l.category in ("Decking", "Fasteners", "Fascia"))
        rail_m = mats(lambda l: l.category == "Rail") - drink_m
        stair_m = mats(lambda l: l.category == "Stairs")
        alloc.append(("Foundation & structure", round(comp(frame_m, labsum("Frame", "Diamond Pier", "Caissons", "Large footings", "Concrete piers", "Extra beam", "Hot-tub", "Steel frame", "Under-deck")))))
        alloc.append(("Decking & fascia", round(comp(deck_m, labsum("Decking")))))
        rail_c = (round(rail_sell) if rail_sell else round(comp(rail_m, labsum("Railing", "Cable rail")))) if L.rail else 0
        stair_c = round(comp(stair_m, labsum("Stairs"))) if L.stairs else 0
        if L.rail and (rail_c >= 100 or not L.stairs):
            alloc.append(("Railing", rail_c))
        else:
            stair_c += rail_c            # a parapet deck: the only rail is on the stair, so it rides with the stairs
        if L.stairs:
            alloc.append(("Stairs" + (" & stair rail" if s.railing.existing_parapet else ""), stair_c))
        sail_m = mats(lambda l: l.category == "Shade sail")
        if sail_m:
            _np = sum(len(sl.get('posts', [])) for sl in s.geometry.sails)
            _own = any(sl.get("fabric_by_owner") for sl in s.geometry.sails)
            alloc.append(((f"Shade sail posts + install — {_np} steel post{'s' if _np != 1 else ''}" if _own else f"Shade sail on {_np} steel post{'s' if _np != 1 else ''}") + ((" at the rail corners" if _np != 1 else " at the rail corner") if any(sl.get("mount") == "deck_rail" for sl in s.geometry.sails) else "") + (" (owner supplies the sail)" if _own else ""), round(comp(sail_m, labsum("Shade sail")))))
        alloc += parts
    for cat, label, n, sv in bsell:        # owner-priced built-ins at their section price
        alloc.append((label, round(sv)))
    if gc:
        alloc.append(("Site & project services", round(gc)))
    if s.extras.sell_override:        # scale every component to the set price, then true up the rounding
        tot = sum(a[1] for a in alloc) or 1
        alloc = [(k, round(v * sell / tot)) for k, v in alloc]
    diff = sell - sum(a[1] for a in alloc)
    i = 1 if (s.extras.demo_existing and not s.is_timber) else 0
    alloc[i] = (alloc[i][0], alloc[i][1] + diff)
    engineering = (s.extras.engineering_fee_low, s.extras.engineering_fee_high) if (s.extras.engineered and not s.extras.engineering_included) else None
    pr = Pricing(round(mat, 2), factor, round(mat_f, 2), rate, round(tax, 2), labor_lines, round(labor, 2), gc_lines, round(gc, 2), round(work, 2), round(cost, 2),
                 gm, sell, sell_floor, retail, round(monthly, 2), round(gp, 2), round(comm, 2), alloc, cats, round(sell / L.deck_sf, 2), engineering,
                 [], pb.get("_dealer_fee_note", ""), gc_base, gc_extras)
    if builtin_sell and not s.extras.sell_override:
        pr.rail_note = " · ".join(f"{n} {('bench section' if c == 'Benches' else 'planter')}{'s' if n > 1 else ''} at ${sv / n:,.0f} (${sv:,.0f})" for c, _l, n, sv in bsell)
    if rail_sell and not s.extras.sell_override:
        pr.rail_note = f"blended — {L.rail.rail_lf:g} LF rail at ${float(rate_lf):,.2f}/LF (${rail_sell:,.0f})" + (" · " + pr.rail_note if getattr(pr, 'rail_note', '') else "") + f", everything else at {gm_base:.1%} GM"
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
    """Each option = a full installed delta: a spec change re-run through the engine (materials, labor) and/or a fixed direct
    cost; sell delta = cost delta ÷ (1 − GM), financed = sell ÷ 0.93. Sign: + adder, − deduct."""
    from .takeoff import build_takeoff
    pb = PRICEBOOK
    out = []
    base_dict = t.spec.to_dict()
    base_dict["extras"]["options"] = []
    for o in t.spec.extras.options:
        dcost = 0.0
        note = o.note
        if o.changes:
            try:
                sp2 = DeckSpec.from_dict(_deep_merge(base_dict, o.changes))
                t2 = build_takeoff(sp2)
                p2 = price(t2, gm=gm, tax_rate=base.tax_rate, with_options=False)
                dcost += p2.work - base.work
            except Exception as e:  # an option that can't be built is reported, never silently dropped
                note = (note + "; " if note else "") + f"could not price change: {e}"
        if o.cost:
            dcost += o.cost
        check = round(dcost / (1 - gm))
        out.append(OptionPrice(o.name, round(check / pb["retail_factor"]), check, round(dcost, 2), note))
    return out
