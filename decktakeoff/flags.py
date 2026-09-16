"""Site and code flags — the things a takeoff must shout about before anyone orders material.
Setbacks, engineering triggers, snow, wind, fire (WUI), frost, guards, stairs, ledger conditions.
INTERNAL: these never appear in client documents (GSX standard: no permit/AHJ wording unless Jade asks)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List

from . import engineering as eng
from .catalog import decking_facts, actual
from .layout import Layout
from .units import ftin

SEV = {"STOP": 0, "ENGINEER": 1, "CODE": 2, "CHECK": 3, "INFO": 4}


@dataclass
class Flag:
    severity: str        # STOP | ENGINEER | CODE | CHECK | INFO
    topic: str           # setback | engineering | snow | wind | fire | frost | guard | stairs | ledger | footing | product | geometry
    text: str
    ref: str = ""        # code section / source


def run_flags(L: Layout) -> List[Flag]:
    s, fr, dk, rl = L.spec, L.frame, L.decking, L.rail
    g, site, ex = s.geometry, s.site, s.extras
    F: List[Flag] = []
    add = lambda sev, topic, text, ref="": F.append(Flag(sev, topic, text, ref))

    # ---------------- setbacks / zoning
    for side, req, have in (("rear", site.rear_setback_required_ft, site.deck_to_rear_line_ft),
                            ("side", site.side_setback_required_ft, site.deck_to_side_line_ft)):
        if req is not None and have is not None:
            if have < req:
                add("STOP", "setback", f"{side} setback: deck edge is {have:g}' from the {side} property line, {req:g}' required — shrink the deck, shift it, or get a variance", "zoning")
            elif have - req < 1.0:
                add("CHECK", "setback", f"{side} setback tight: {have:g}' to the line vs {req:g}' required — verify with a survey pin before layout", "zoning")
        elif req is None and have is None:
            add("CHECK", "setback", f"{side} setback not entered — confirm the required {side} setback and the deck-to-line distance before the frame is laid out", "zoning")
    for e in site.easements:
        add("CHECK", "setback", f"easement on record: {e} — no footings or structure inside it", "plat")
    if site.hoa:
        add("INFO", "setback", "HOA — architectural approval before start (color, rail, height)")

    # ---------------- design loads / engineering triggers
    psf, why = fr.total_psf, fr.load_note
    if site.ground_snow_psf > 40:
        add("ENGINEER", "snow", f"ground snow {site.ground_snow_psf:g} psf > 40 psf — IRC R507 span tables do not apply; spans here are scaled estimates, a stamped design is required",
            "IRC R507.5/R507.6 (tables valid to 40 psf snow)")
    elif site.ground_snow_psf > 30:
        add("INFO", "snow", f"ground snow {site.ground_snow_psf:g} psf — within the 40 psf table limit; design load {psf:g} psf")
    if ex.hot_tub:
        add("ENGINEER", "engineering", "hot tub — 100 psf live load; joists 12\" OC, added beam/posts and footings under the tub, engineered design", "IRC R507 / ASCE 7")
    if ex.roof_over:
        add("ENGINEER", "engineering", "roof over the deck — roof snow + deck loads on the posts and footings; engineered")
    if ex.cover_roof.lower().startswith("standing"):
        add("CODE", "snow", "standing seam roof over the deck — metal sheds its snow load onto the deck and the stair below: snow retention bar the full low eave (S-5! ColorGard or equal, seam clamps, no penetrations), sized for the ground snow", "ASCE 7 Ch. 7 / manufacturer")
        add("INFO", "snow", "standing seam on a low-slope shed (~1:12 to 2:12): mechanically seamed or snap-lock rated for the pitch, high-temp self-adhered underlayment under every panel, headwall flashing counterflashed into the house wall")
    if ex.cover_gutters:
        add("INFO", "footing", "gutter downspouts discharge onto splash blocks 3'+ from the deck footings and the house foundation, downhill; no downspout dumping at a post")
    if ex.privacy_wall:
        add("ENGINEER", "engineering", "privacy wall — wind load on the posts and rail attachment; engineered detail")
    for chk in fr.joist_checks:
        if not chk.ok:
            add("STOP", "engineering", f"joist {chk.size} {chk.species} @ {chk.spacing_in:g}\" OC spans {ftin(chk.actual_in)} — allowable {ftin(chk.allowable_in)}: add a beam, go to 2x12, or tighten spacing", "IRC Table R507.6")
        elif chk.utilization > 0.95:
            add("CHECK", "engineering", f"joist span {ftin(chk.actual_in)} is at {chk.utilization:.0%} of allowable {ftin(chk.allowable_in)} — no room to move the beam in", "IRC Table R507.6")
        if chk.note:
            add("ENGINEER", "engineering", f"joist: {chk.note}")
    for b in fr.beams:
        c = b.check
        if not c.ok:
            add("STOP", "engineering", f"{b.label} post spacing {ftin(c.actual_in)} exceeds allowable {ftin(c.allowable_in)} — add a post or upsize the beam", "IRC Table R507.5")
        if c.note:
            add("ENGINEER", "engineering", f"{b.label}: {c.note}", "IRC Table R507.5")
        if b.kind == "drop" and b.cantilever > eng.CANTILEVER_RATIO * b.back_span + 0.5:
            if ex.engineered:
                add("ENGINEER", "engineering", f"cantilever {ftin(b.cantilever)} > L/4 of the {ftin(b.back_span)} back-span — owner-directed, in the stamped set", "IRC R507.5 / R507.6")
            else:
                add("STOP", "engineering", f"cantilever {ftin(b.cantilever)} > L/4 of {ftin(b.back_span)} back-span", "IRC R507.5 / R507.6")
        if b.kind == "flush" and b.depth + 0.01 < actual(fr.joist_size)[1]:
            add("CODE", "engineering", f"flush beam {b.size} is shallower than the {fr.joist_size} joists it carries — beam depth must be >= joist depth", "IRC R507.5 note")
    ok, mx = fr.post_height_check
    if not ok:
        add("STOP", "engineering", f"{fr.post_size} post {ftin(fr.post_len)} exceeds {ftin(mx)} max — go to 6x6/8x8 or brace", "IRC Table R507.4")
    if fr.post_len > 96:
        add("CODE", "engineering", f"posts over 8' ({ftin(fr.post_len)}) — add diagonal knee bracing at each post (both directions at the corners)", "DCA6 / IRC R507.4")
    if g.height_in > 120:
        add("ENGINEER", "engineering", f"deck surface {ftin(g.height_in)} above grade — over 10': lateral bracing and an engineered design")
    if not fr.ledger:
        add("CODE", "engineering", "freestanding deck — no ledger lateral tie; provide diagonal bracing at posts or an engineered lateral system", "IRC R507.9 / R507.4")
    if g.shape != "rectangle" or g.notches:
        add("CHECK", "geometry", f"shape '{g.shape}'{' with ' + str(len(g.notches)) + ' notch(es)' if g.notches else ''} — takeoff is on the bounding rectangle {ftin(L.finished_w)} x {ftin(L.finished_d)}; hand-adjust the deducts")
    if g.levels > 1:
        add("CHECK", "geometry", f"{g.levels} levels — this takeoff covers one level; run one spec per level and add the step-down framing")
    if fr.footing_type == "diamond_pier" and fr.footing_load_lb > fr.footing_capacity_lb:
        add("STOP", "footing", f"post load {fr.footing_load_lb:,.0f} lb exceeds {fr.footing_model} ({fr.footing_capacity_lb:,} lb) — more posts or concrete piers", "Pin Foundations chart")
    if fr.footing_type == "diamond_pier":
        add("CHECK", "footing", f"Diamond Pier: pins 50\" — locate utilities (811) before driving; bearing {fr.footing_load_lb:,.0f} lb/post vs {fr.footing_capacity_lb:,} lb allowable (manufacturer chart, confirm)")
    if fr.footing_type == "concrete":
        add("CODE", "frost", f"concrete piers bear {ftin(fr.footing_depth_in - 6)} below grade — frost depth {ftin(site.frost_depth_in)} for {site.city or 'this jurisdiction'}; confirm the local frost line and soil bearing ({site.soil_bearing_psf:,.0f} psf assumed)", "IRC R403.1.4")
    if site.soil_bearing_psf < 1500:
        add("ENGINEER", "footing", f"soil bearing {site.soil_bearing_psf:,.0f} psf — soils report / engineered footings")

    # ---------------- ledger conditions
    if fr.ledger:
        if ex.ledger_on_brick_veneer:
            add("STOP", "ledger", "ledger cannot attach through brick/stone veneer — freestanding deck or engineered through-bolted standoff", "IRC R507.9.1.1")
        if ex.ledger_on_cantilevered_floor:
            add("ENGINEER", "ledger", "house floor cantilevers past the foundation — ledger attachment to a cantilevered floor needs an engineered detail or a freestanding deck", "IRC R507.9.1")
        add("CHECK", "ledger", "verify the rim board behind the ledger is solid 2x/LVL/engineered rim (not I-joist web or a hollow band) before the ledger fasteners go in", "IRC R507.9.1.1")
        if not s.is_timber:
            add("INFO", "ledger", f"lateral: {s.framing.lateral_ties} x DTT1Z (750 lb each) into house floor framing", "IRC R507.9.2")

    # ---------------- wind
    v = site.wind_speed_mph
    if v >= 140:
        add("ENGINEER", "wind", f"basic wind speed {v:g} mph — uplift on the frame and rail loads; engineered connections (H2.5A at every joist, post-to-beam uplift caps)", "ASCE 7")
    elif v >= 120:
        add("CODE", "wind", f"basic wind speed {v:g} mph — H2.5AZ at every joist to the beam and uplift-rated post caps are required, not optional", "ASCE 7 / IRC R301.2")
    else:
        add("INFO", "wind", f"basic wind speed {v:g} mph — standard connectors")

    # ---------------- fire / WUI
    f = decking_facts(s.decking.collection)
    if site.wui_fire_zone:
        if not f.get("wui"):
            add("STOP", "fire", f"WUI / ignition-resistant zone: {s.decking.brand} {s.decking.collection} is '{f['fire']}' — switch to a WUI-listed line (Vintage, Landmark, Harvest+ are Class A + WUI)", "IWUIC 504.7 / CBC 7A")
        else:
            add("CODE", "fire", f"WUI zone: {s.decking.collection} is {f['fire']} — keep the under-deck area clear of combustibles, 1-hr or noncombustible enclosure may be required", "IWUIC 504.7")
        if s.decking.collection == "Terrain+":
            add("CHECK", "fire", "Terrain+ WUI status contradicts itself on timbertech.com — confirm with the dealer before it goes into a fire zone")
    elif f.get("fire", "").lower().startswith("not"):
        add("INFO", "fire", f"{s.decking.collection}: {f['fire']} — fine outside a WUI zone")
    if site.wui_fire_zone and rl:
        from .catalog import RAIL_SYSTEMS
        if RAIL_SYSTEMS.get(rl.system, {}).get("noncombustible", False):
            add("INFO", "fire", f"{rl.system} rail is noncombustible (Colorado Wildfire Resiliency Code practice: Class A decking, noncombustible rail, metal flashing at every wall)")
        else:
            add("CODE", "fire", f"{rl.system} rail is not noncombustible — WUI practice calls for metal/cable rail", "Colorado Wildfire Resiliency Code")
    if s.is_timber:
        add("ENGINEER", "engineering", "timber frame (DF #1 4x joists, 6x beams, 8x8 posts) is outside the IRC prescriptive tables — spans here are pre-engineering estimates; the stamped set governs sizes, post locations and caissons", "IRC R301.1.3")

    # ---------------- guards & stairs
    hi = max(g.height_in, g.height_high_in or 0)
    if hi > eng.GUARD_TRIGGER_HEIGHT:
        if rl is None or not rl.sections:
            add("STOP", "guard", f"deck surface {ftin(hi)} above grade — guards required on every open side, none specified", "IRC R312.1.1")
        else:
            if rl.height < eng.GUARD_HEIGHT_RES:
                add("STOP", "guard", f"guard height {rl.height:g}\" < 36\" minimum", "IRC R312.1.2")
            missing = {"left", "right", "front"} - set(s.railing.sides)
            if missing:
                add("CHECK", "guard", f"no rail on {', '.join(sorted(missing))} — required unless grade is within 30\" there", "IRC R312.1.1")
            for o in rl.openings:
                if "stair" not in o.reason and "house" not in o.reason.lower() and "wall" not in o.reason.lower():
                    add("CHECK", "guard", f"rail opening on the {o.side} ({ftin(o.length_in)}, {o.reason}) — allowed only if the drop there is 30\" or less", "IRC R312.1.1")
    elif hi > 24 and (rl is None or not rl.sections):
        add("INFO", "guard", f"deck {ftin(hi)} above grade — under 30\", guard not required by IRC (client choice)")
    for st in L.stairs:
        for n in st.notes:
            sev = "CODE" if "handrail" in n or "minimum" in n or "exceeds" in n else "CHECK"
            add(sev, "stairs", f"{st.side} stair: {n}", "IRC R311.7")
        add("INFO", "stairs", f"{st.side} stair: {st.geo.risers} risers @ {st.geo.riser_in:.2f}\" · {st.geo.treads} treads @ {st.geo.tread_in:.2f}\" · run {ftin(st.geo.total_run_in)} · stringers {st.stringers} @ 12\" OC (composite treads)", "IRC R311.7.5 / TimberTech")
        if st.landing == "grade":
            add("CODE", "stairs", f"{st.side} stair lands on grade — a landing is required at the bottom (36\" min in the direction of travel); pour a pad or set pavers", "IRC R311.7.6")
        if st.geo.guard_required and st.stair_rail_sides == 0:
            add("STOP", "stairs", f"{st.side} stair: open side over 30\" — stair guard required", "IRC R312.1")

    # ---------------- product / fastening sanity
    if f["material"] == "PVC" and fr.spacing > 12:
        add("CODE", "product", f"PVC decking at {fr.spacing:g}\" OC — TimberTech Advanced PVC at GSX is 12\" OC", "TimberTech install guide")
    if f["material"] == "Composite" and fr.spacing > 16:
        add("CODE", "product", f"composite at {fr.spacing:g}\" OC exceeds the 16\" residential max", "TimberTech install guide")
    if s.decking.color not in f.get("colors", [s.decking.color]):
        add("CHECK", "product", f"'{s.decking.color}' is not a current {s.decking.collection} color — discontinued or a different line; confirm with D&D")
    if s.framing.rim_plies > 2:
        add("CHECK", "product", f"{s.framing.rim_plies}-ply rims — GSX standard is double rims; never add plies")
    if not (site.rear_setback_required_ft or site.side_setback_required_ft) and not site.address:
        add("INFO", "setback", "no address on the spec — tax rate and jurisdiction defaults used")

    seen, uniq = set(), []
    for f in F:
        if (f.severity, f.text) not in seen:
            seen.add((f.severity, f.text)); uniq.append(f)
    uniq.sort(key=lambda x: SEV.get(x.severity, 9))
    return uniq
