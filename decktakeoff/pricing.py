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

import json
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


def sell_per_sf_rule(s) -> Optional[Tuple[float, object]]:
    """extras.sell_per_sf -> (rate, options_gm) or None. A number is the owner's check/ACH price per deck SF; a dict
    {"rate": 175, "options_gm": 0.45 | "effective"} also says what margin the options price at (default: the job margin)."""
    v = getattr(s.extras, "sell_per_sf", None)
    if not v:
        return None
    if isinstance(v, dict):
        r = v.get("rate") or v.get("sell")
        return (float(r), v.get("options_gm")) if r else None
    return (float(v), None)


def _monthly(retail: float) -> float:
    r = PRICEBOOK["finance_rate"] / 12
    n = PRICEBOOK["finance_years"] * 12
    return retail * r / (1 - (1 + r) ** -n)


def option_delta(base: "Pricing", other: "Pricing") -> Tuple[float, float, float]:
    """An option against a proposal: the whole installed difference (check, financed, monthly) — normally the two prices'
    difference. Against a deck sold per SF the rate prices only deck area (a stair to the yard would come out at $0), so the
    option is priced from the engine's cost math instead — work delta / (1 - the job margin), financed / 0.93 — the same
    way price_options prices extras.options on that deck."""
    if not getattr(base, "per_sf", 0.0):
        return other.sell - base.sell, other.retail - base.retail, other.monthly - base.monthly
    ls_ = getattr(other, "light_sell", 0.0) - getattr(base, "light_sell", 0.0)          # lights at their set price each (extras.lights.sell_each)
    lw_ = getattr(other, "light_work", 0.0) - getattr(base, "light_work", 0.0)
    check = round((other.work - base.work - lw_) / (1 - base.options_gm) + ls_)
    retail = round(check / PRICEBOOK["retail_factor"])
    return check, retail, _monthly(retail)


def fixed_terms(spec, check: float) -> Tuple[float, float, float]:
    """(check, financed, monthly) for a price the owner set outright — financed and monthly the way the deck's price gets them."""
    check = round(float(check))
    retail = round(check * (1 + spec.extras.retail_markup)) if spec.extras.retail_markup is not None else round(check / PRICEBOOK["retail_factor"])
    return check, retail, _monthly(retail)


@dataclass
class AddonPrice:
    """A separately sold item with its own document (the louvered roof): the owner's price per SF x its area, or a set price."""
    name: str
    sf: float
    rate: float                  # $/SF of the item's area (0 when the price is set outright)
    sell: float                  # check or ACH
    retail: float                # financed
    monthly: float
    basis: str = ""              # how the price was set, for the internal pages ("200 SF x $175/SF")


def roof_size_ft(roof: dict) -> Tuple[float, float]:
    """(along the house, out from the house) in feet for a louvered roof dict — its x/y extents, else its width / depth keys."""
    if all(k in roof for k in ("x0", "x1", "y0", "y1")):
        return abs(float(roof["x1"]) - float(roof["x0"])), abs(float(roof["y1"]) - float(roof["y0"]))
    w = roof.get("width_ft", roof.get("width", roof.get("length_ft")))
    d = roof.get("depth_ft", roof.get("depth", roof.get("projection_ft")))
    if w is None and roof.get("width_in"):
        w = float(roof["width_in"]) / 12
    if d is None and roof.get("depth_in"):
        d = float(roof["depth_in"]) / 12
    return float(w or 0), float(d or 0)


def price_louvered(spec, roof: dict, name: str = "Louvered roof") -> AddonPrice:
    """The louvered roof's own price: roof["price"] when the owner set it, else roof["price_per_sf"] x its area (roof["sf"], else
    along x out). Sold on its own, outside the deck's price and margin; financed and monthly the way the deck's price gets them."""
    w, d = roof_size_ft(roof)
    sf = float(roof.get("sf") or round(w * d, 1))
    rate = float(roof.get("price_per_sf") or 0.0)
    if roof.get("price"):
        sell, basis = float(roof["price"]), "owner-set price"
    elif rate:
        if all(roof.get(k) is not None for k in ("x0", "x1", "y0", "y1")):      # the louvered engine's own rule, so every document agrees
            from .louvered import roof_sell
            sell = roof_sell(roof)
        else:
            sell = rate * sf
        basis = f"{sf:g} SF x ${rate:,.2f}/SF"
    else:
        raise ValueError("louvered roof has neither price nor price_per_sf")
    c, f, m = fixed_terms(spec, sell)
    return AddonPrice(roof.get("name") or name, sf, rate, c, f, m, basis)


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


def stair_specs(t) -> list:
    """The stair specs in the order of t.layout.stairs: a composite deck's stairs live in its parts (the job-level list is empty)."""
    L = t.layout
    if hasattr(L, "parts"):
        return [ss for p in L.parts for ss in p.spec.stairs]
    return list(t.spec.stairs)


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
    for x in s.extras.labor_extras:          # the owner's own price for work the card has no line for
        lab.append((str(x.get("item", "labor")), float(x.get("qty", 1)), str(x.get("unit", "ea")), float(x.get("rate", 0)), "owner-set"))
    for c in s.extras.demo_columns:          # masonry columns out: the card's stone / stucco column demo, per LF of column
        lab.append((f"Demolition — {c.get('what', 'existing columns')} (stone / stucco column demo)", float(c.get("lf", 0)), "LF", lr.get("column_demo_per_lf", 50.0), "rate card add-on"))
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
    for ss_, st in zip(stair_specs(t) + [None] * len(L.stairs), L.stairs):       # the stair by its name, else by the side it leaves
        nm_ = (f"Stairs — {ss_.name}" if getattr(ss_, "name", None) else _re.sub(r"\bedge:(\d+)", r"side \1", f"Stairs ({st.side})"))   # "Stairs" leads: the allocation sums by it
        lab.append((f"{nm_}" + (f" — {len(st.geo.flights)} flights" if len(st.geo.flights) > 1 else ""), st.geo.risers, "riser", lr["stairs_per_riser"],
                    "rate card — railing included (owner: $150 a riser including railing)"))
        if getattr(st, "own_footings", 0):      # its landing + carrier posts on its own 12" caissons: the card's hole, no large-footing add-on
            lab.append((f"{nm_} — 12\" caissons under its landing and carrier posts", st.own_footings, "hole", lr["caisson_each"], "rate card (12\": no large-footing add-on)"))
    for ss in stair_specs(t):
        for lw, ld in ss.landings or []:
            sf_l = float(lw) * float(ld) / 144
            if getattr(ss, "landing_footing", "") in ("deck", "caisson12"):   # its 4 posts stand on the deck's footings or the stair's own caissons (above)
                lab.append((f"Stair landing {ftin(float(lw))} x {ftin(float(ld))} — frame, deck", round(sf_l, 1), "SF", lr["frame_per_sf"] + lr["decking_fascia_per_sf"], "base rate — frame + decking; its footings are in the footing line"))
                continue
            if s.framing.footing_type == "diamond_pier":     # the card's own rates: frame + decking per SF of landing, and $50 a pier for its 4 Diamond Piers
                lab.append((f"Stair landing {ftin(float(lw))} x {ftin(float(ld))} — frame, deck", round(sf_l, 1), "SF", lr["frame_per_sf"] + lr["decking_fascia_per_sf"], "base rate — frame + decking"))
                lab.append((f"Stair landing {ftin(float(lw))} x {ftin(float(ld))} — Diamond Pier install", 4, "pier", lr["diamond_pier_each"], "rate card"))
                continue
            if s.framing.footing_type == "caisson":         # the card: frame + decking per SF of landing, a caisson hole per landing post
                lab.append((f"Stair landing {ftin(float(lw))} x {ftin(float(ld))} — frame, deck", round(sf_l, 1), "SF", lr["frame_per_sf"] + lr["decking_fascia_per_sf"], "base rate — frame + decking"))
                lab.append((f"Stair landing {ftin(float(lw))} x {ftin(float(ld))} — caissons", 4, "hole", lr["caisson_each"], "base rate"))
                continue
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
    lab += __import__("decktakeoff.lighting", fromlist=["labor_lines"]).labor_lines(t, lr)     # extras.lights: fixtures + transformer (ESTIMATE, no card rate)
    return lab


def gc_name(gc_lines, default: str) -> str:
    """The at-cost bucket named for what is in it when it is one owner-set item (e.g. the dumpster + toilet), else the generic name."""
    return gc_lines[0][0] if len(gc_lines) == 1 and gc_lines[0][0] != "General conditions" else default


def gc_lines_for(t: Takeoff) -> Tuple[List[Tuple[str, float, str]], float, List[Tuple[str, float]]]:
    s, L = t.spec, t.layout
    if s.extras.no_general_conditions:
        return [], 0.0, []
    if s.extras.general_conditions:
        return [(g.get("item", "GC"), float(g.get("amount", 0)), g.get("why", "")) for g in s.extras.general_conditions], 0.0, []
    base = PRICEBOOK["general_conditions"]["per_sf"] * L.deck_sf
    extras = [(x.get("item", "site extra"), float(x.get("cost", 0))) for x in s.extras.site_extras]
    return [("General conditions", base, f"${PRICEBOOK['general_conditions']['per_sf']:g}/SF x {L.deck_sf:g} SF")] + [(i, v, "at cost") for i, v in extras], base, extras


_STAIRLESS: Dict[str, float] = {}       # the stairless takeoff's margin-carrying work, per (spec, gm, tax)


def stair_rule(t: Takeoff, gm: float, tax_rate: float, rate_lf, margin_work: float) -> Tuple[float, float, str]:
    """extras.stair_rule — the owner's stairs (Pricing Sheet To Fit GS): every riser at stair_sell_per_riser, railing included; a
    landing at the deck's no-rail $/SF with its level guard at the rail rule. -> (sell, work, note). The stairs' work is the job's
    margin-carrying work less the same job with its stairs taken out: every line a stair adds (its treads cut from the field, its
    caissons and posts, its fascia, its labor) and nothing the stairs do not."""
    s, L = t.spec, t.layout
    per_riser = PRICEBOOK.get("stair_sell_per_riser", {}).get(s.decking.collection)
    if not (s.extras.stair_rule and per_riser and L.stairs):
        return 0.0, 0.0, ""
    d = s.to_dict()
    d["stairs"] = []
    for part in d.get("geometry", {}).get("parts") or []:
        part["stairs"] = []
    key = json.dumps(d, sort_keys=True, default=str) + f"|{gm}|{tax_rate}"
    if key not in _STAIRLESS:
        s0 = DeckSpec.from_dict(d)
        if s0.geometry.parts:
            from .composite import build_composite
            t0 = build_composite(s0)[0]
        else:
            from .takeoff import build_takeoff
            t0 = build_takeoff(s0)
        _STAIRLESS[key] = price(t0, gm=gm, tax_rate=tax_rate, with_options=False, _stairless=True).margin_work
    psf = float(PRICEBOOK.get("landing_sell_per_sf", {}).get(s.decking.collection)
                or PRICEBOOK.get("deck_sell_per_sf_no_rail", {}).get(s.decking.collection, 0.0))      # the owner's landing rate, else the deck's
    n_r = sum(st.geo.risers for st in L.stairs)
    land_sf = round(sum(float(w) * float(dd) / 144 for ss in stair_specs(t) for w, dd in (ss.landings or [])), 1)
    guard_lf = round(sum(st.landing_rail_lf for st in L.stairs), 1)
    sell = n_r * float(per_riser) + land_sf * psf + (guard_lf * float(rate_lf) if rate_lf else 0.0)
    note = (f"{n_r} stair risers at ${float(per_riser):,.0f}, railing included" + (f"; {land_sf:g} SF of landing at ${psf:,.2f}/SF" if land_sf else "")
            + (f" + its {guard_lf:g} LF guard at ${float(rate_lf):,.0f}/LF" if guard_lf and rate_lf else ""))
    return round(sell, 2), margin_work - _STAIRLESS[key], note


def price(t: Takeoff, gm: float = None, tax_rate: float = None, with_options: bool = True, _stairless: bool = False) -> Pricing:
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
    if s.extras.labor_adjust:                 # the owner's labor change ($, negative cuts): owner-set lots stay, the card lines share it in proportion
        adj = float(s.extras.labor_adjust)
        others = sum(q * r for i, q, u, r, n in lab if not str(n).startswith("owner-set"))
        k = max(0.0, others + adj) / others if others else 1.0
        lab = [(i, q, u, r if str(n).startswith("owner-set") else round(r * k, 4), n if str(n).startswith("owner-set") else
                f"{n} · {'less' if adj < 0 else 'plus'} the owner's ${abs(adj):,.0f} labor {'cut' if adj < 0 else 'add'} ({k - 1:+.1%} on every card line)")
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
    # lights the owner prices per light, installed (extras.lights.sell_each): they sell at that price; their work comes off the margin base
    light_sell, light_work = __import__("decktakeoff.lighting", fromlist=["fixed_sell"]).fixed_sell(t, labor_lines, factor, rate)
    # the drink rail at the owner's installed price (extras.drink_rail_sell): it sells at that price; its work comes off the margin base
    drink_sell, drink_work = 0.0, 0.0
    if s.extras.drink_rail_sell and s.railing.drink_rail and L.rail:
        drink_sell = float(s.extras.drink_rail_sell)
        drink_work = (sum(l.ext for l in t.lines if l.category != "Site" and ("rink rail" in l.item or "drink-rail" in l.item)) * factor * (1 + rate)
                      + sum(e for i, q, u, r_, e in labor_lines if i.startswith("Drink rail")))
    margin_work = work - rail_work - builtin_work - light_work - drink_work
    # stairs the owner prices per riser (extras.stair_rule): they sell at that price; their work comes off the margin base
    stair_sell, stair_work, stair_note = (0.0, 0.0, "") if _stairless else stair_rule(t, gm, rate, rate_lf, margin_work)
    sell = round((margin_work - stair_work) / (1 - gm) + rail_sell + builtin_sell + light_sell + stair_sell + drink_sell + gc)
    sell_floor = round((margin_work - stair_work) / (1 - pb["gm_floor"]) + rail_sell + builtin_sell + light_sell + stair_sell + drink_sell + gc)
    gm_base = gm
    # an owner-set sell: sell_override (the price), else extras.sell_per_sf (the price per deck SF x the deck's SF); either way the
    # allocation scales to it and the margin is what that price carries
    psf = None if s.extras.sell_override else sell_per_sf_rule(s)
    set_sell = s.extras.sell_override or (round(psf[0] * L.deck_sf) if psf else None)
    if (rail_sell or builtin_sell or light_sell or light_work or stair_sell or drink_sell) and not set_sell:
        gm = 1 - work / max(sell - gc, 1)          # the blended margin the job carries (free lights included)
    if set_sell:
        sell = round(float(set_sell))
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
        return (m * factor * (1 + rate) + l_) / (1 - (gm_base if (rail_sell or light_sell or light_work or stair_sell or drink_sell) and not set_sell else gm))
    stone_m = mats(lambda l: "Stone veneer column base" in l.item)
    drink_m = mats(lambda l: "rink rail" in l.item or "drink-rail" in l.item)
    oil_m = mats(lambda l: l.category == "Finish" and ("oil" in l.item.lower() or "Sprayer" in l.item))
    alloc = []
    if s.extras.demo_existing and not s.is_timber:
        alloc.append(("Demolition & haul-off", round(labsum("Demolition") / (1 - (gm if set_sell else gm_base)))))
    rest = sell - gc - sum(a[1] for a in alloc)
    parts = []
    if s.extras.stone_bases:
        parts.append((f"Stone column bases at all {sum(z.frame.n_posts for z in L.zones)} posts", round(comp(stone_m, labsum("Stone column")))))
    if s.is_timber and s.framing.finish == "oil":
        parts.append(("Dark walnut oil finish, two coats, every timber", round(comp(oil_m, labsum("Timber oil")) - PRICEBOOK["labor"]["seal_cut_ends_lot"] / (1 - gm))))
    if s.railing.drink_rail and L.rail:
        parts.append(((f"Drink rail — {s.railing.drink_rail_collection or ''} {s.railing.drink_rail_color or ''}".replace("  ", " ").strip() if hasattr(L, "parts") else   # two-level jobs read the board
                       f"{s.railing.drink_rail_color or ''} drink rail on the {'cable ' if RAIL_SYSTEMS.get(L.rail.system, {}).get('cable') else ''}rail".strip()), round(drink_sell) if drink_sell and not set_sell else round(comp(drink_m, labsum("Drink rail")))))
    if covers_of(s):
        cover_m = mats(lambda l: l.category == "Porch cover")
        n_cv = len(covers_of(s))
        finish = ("Hardie soffit, fascia and rakes" if (s.extras.cover_soffit or s.extras.cover_fascia) else "T&G ceiling")
        roof = ("standing seam steel roof with snow retention" if s.extras.cover_roof.lower().startswith("standing") else "shingles") + (", gutter and downspouts" if s.extras.cover_gutters else "")
        lead = "Porch cover — shed roof" if n_cv == 1 else f"{n_cv} roof covers — lean-to roofs"
        parts.append((f"{lead} on 6x6 {'Douglas fir' if s.extras.cover_post_species.upper().startswith('DF') else 'cedar'} posts, {roof}, {finish}" + (", existing covers torn off" if s.extras.demo_covers else "") + (", blinds rehung" if s.extras.blinds_reinstall else ""),
                      round(comp(cover_m, labsum("Porch cover") + labsum("Take down, store")))))
    parts += __import__("decktakeoff.lighting", fromlist=["allocation"]).allocation(t, mats, labsum, comp)     # extras.lights: what is lit, at its sell value
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
        stair_c = (round(stair_sell) if stair_sell else round(comp(stair_m, labsum("Stairs")))) if L.stairs else 0
        if L.rail and (rail_c >= 100 or not L.stairs):
            alloc.append(("Railing", rail_c))
        else:
            stair_c += rail_c            # a parapet deck: the only rail is on the stair, so it rides with the stairs
        if L.stairs:
            _snm = [getattr(ss_, "name", "") for ss_ in stair_specs(t)]
            _slab = " + ".join(dict.fromkeys(_snm)) if (_snm and all(_snm)) else "Stairs"      # named stairs read by name ("Stair between the levels")
            alloc.append((_slab + (" & stair rail" if s.railing.existing_parapet else ""), stair_c))
        sail_m = mats(lambda l: l.category == "Shade sail")
        if sail_m:
            _np = sum(len(sl.get('posts', [])) for sl in s.geometry.sails)
            _own = any(sl.get("fabric_by_owner") for sl in s.geometry.sails)
            alloc.append(((f"Shade sail posts + install — {_np} steel post{'s' if _np != 1 else ''}" if _own else f"Shade sail on {_np} steel post{'s' if _np != 1 else ''}") + ((" at the rail corners" if _np != 1 else " at the rail corner") if any(sl.get("mount") == "deck_rail" for sl in s.geometry.sails) else "") + (" (owner supplies the sail)" if _own else ""), round(comp(sail_m, labsum("Shade sail")))))
        alloc += parts
    for cat, label, n, sv in bsell:        # owner-priced built-ins at their section price
        alloc.append((label, round(sv)))
    if gc:
        alloc.append((gc_name(gc_lines, "Site & project services"), round(gc)))
    if set_sell:        # scale every component to the set price, then true up the rounding
        tot = sum(a[1] for a in alloc) or 1
        alloc = [(k, round(v * sell / tot)) for k, v in alloc]
    diff = sell - sum(a[1] for a in alloc)
    i = 1 if (s.extras.demo_existing and not s.is_timber) else 0
    alloc[i] = (alloc[i][0], alloc[i][1] + diff)
    engineering = (s.extras.engineering_fee_low, s.extras.engineering_fee_high) if (s.extras.engineered and not s.extras.engineering_included) else None
    pr = Pricing(round(mat, 2), factor, round(mat_f, 2), rate, round(tax, 2), labor_lines, round(labor, 2), gc_lines, round(gc, 2), round(work, 2), round(cost, 2),
                 gm, sell, sell_floor, retail, round(monthly, 2), round(gp, 2), round(comm, 2), alloc, cats, round(sell / L.deck_sf, 2), engineering,
                 [], pb.get("_dealer_fee_note", ""), gc_base, gc_extras)
    pr.per_sf = psf[0] if psf else 0.0      # attributes, not fields: takeoff.json of every existing job stays as it was
    pr.gm_job = gm_base
    # the options' margin: on a per-SF deck the per-SF price says nothing about an option (a stair adds no deck SF), so an option
    # prices from the engine's cost math at the job margin (gm_base) unless sell_per_sf names options_gm ("effective" = the margin
    # the per-SF price carries); otherwise the margin the price carries, as always
    pr.options_gm = ((gm if psf[1] == "effective" else float(psf[1])) if psf[1] is not None else gm_base) if psf else gm
    if psf:
        pr.rail_note = f"the owner's ${psf[0]:,.2f}/SF x {L.deck_sf:g} SF"
    if builtin_sell and not set_sell:
        pr.rail_note = " · ".join(f"{n} {('bench section' if c == 'Benches' else 'planter')}{'s' if n > 1 else ''} at ${sv / n:,.0f} (${sv:,.0f})" for c, _l, n, sv in bsell)
    if rail_sell and not set_sell:
        pr.rail_note = f"blended — {L.rail.rail_lf:g} LF rail at ${float(rate_lf):,.2f}/LF (${rail_sell:,.0f})" + (" · " + pr.rail_note if getattr(pr, 'rail_note', '') else "") + f", everything else at {gm_base:.1%} GM"
    pr.light_sell, pr.light_work = light_sell, light_work      # attributes (option_delta, price_options): the lights at their set price
    pr.margin_work = margin_work                               # the work that carries the job margin (before the owner's stair rule)
    pr.stair_sell, pr.stair_work = stair_sell, stair_work
    if stair_sell and not set_sell:
        pr.rail_note = (pr.rail_note + " · " if getattr(pr, "rail_note", "") else "") + (f"stairs at the owner's rule: {stair_note} (${stair_sell:,.0f}; their cost "
                        f"${stair_work:,.0f}, {1 - stair_work / stair_sell:.0%} margin)")
    if light_sell and not set_sell:
        _lp = t.lighting
        pr.rail_note = (pr.rail_note + " · " if getattr(pr, "rail_note", "") else "") + (f"{_lp.fixtures} lights at ${float(_lp.cfg['sell_each']):,.0f} installed (${light_sell:,.0f}; "
                        f"their cost ${light_work:,.0f}, {1 - light_work / light_sell:.0%} margin)" + ("" if rail_sell else f", everything else at {gm_base:.1%} GM"))
    if light_work and not light_sell and not set_sell:      # the riser lights as a gift: their cost in the job, nothing in the price
        _lp = t.lighting
        pr.rail_note = (pr.rail_note + " · " if getattr(pr, "rail_note", "") else "") + f"{_lp.n_riser} riser lights free (their cost ${light_work:,.0f})"
    if drink_sell and not set_sell:
        pr.rail_note = (pr.rail_note + " · " if getattr(pr, "rail_note", "") else "") + (f"drink rail at ${drink_sell:,.0f} installed (its cost ${drink_work:,.0f}, "
                        f"{1 - drink_work / drink_sell:.0%} margin)")
    if with_options and s.extras.options:
        pr.options = price_options(t, pr, pr.options_gm)
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
        lset = (0.0, 0.0)            # (sell, work) of lights the option adds at their set price each
        note = o.note
        if o.changes:
            try:
                sp2 = DeckSpec.from_dict(_deep_merge(base_dict, o.changes))
                t2 = build_takeoff(sp2)
                p2 = price(t2, gm=gm, tax_rate=base.tax_rate, with_options=False)
                dcost += p2.work - base.work
                lset = (getattr(p2, "light_sell", 0.0) - getattr(base, "light_sell", 0.0), getattr(p2, "light_work", 0.0) - getattr(base, "light_work", 0.0))
            except Exception as e:  # an option that can't be built is reported, never silently dropped
                note = (note + "; " if note else "") + f"could not price change: {e}"
        if o.cost:
            dcost += o.cost
        check = round((dcost - lset[1]) / (1 - gm) + lset[0])     # lights at their set price each (none: dcost / (1 - GM) as always)
        out.append(OptionPrice(o.name, round(check / pb["retail_factor"]), check, round(dcost, 2), note))
    return out
