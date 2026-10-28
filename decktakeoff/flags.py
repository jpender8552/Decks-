"""Site and code flags — the things a takeoff must shout about before anyone orders material.
Setbacks, engineering triggers, snow, wind, fire (WUI), frost, guards, stairs, ledger conditions.
INTERNAL: these never appear in client documents (GSX standard: no permit/AHJ wording unless Jade asks)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

from . import engineering as eng
from .catalog import decking_facts, actual, default_fastener_system
from .layout import Layout
from .units import ftin

SEV = {"STOP": 0, "ENGINEER": 1, "CODE": 2, "CHECK": 3, "INFO": 4}


@dataclass
class Flag:
    severity: str        # STOP | ENGINEER | CODE | CHECK | INFO
    topic: str           # setback | engineering | snow | wind | fire | frost | guard | stairs | ledger | footing | product | geometry
    text: str
    ref: str = ""        # code section / source


FIG10_LINES = ("Terrain", "Terrain+", "Prime", "Prime+", "Classic")     # CCRR-0128 Table 1 note 7: their 16" tread span needs the Figure 10 2x6 blocking


def tread_oc_max(s, st=None) -> Optional[float]:
    """The widest spacing of what carries a stair tread (stringers, box-step cross members) for the job's tread line: the stair
    layout's own (support_oc), else engineering.tread_support_oc, else TimberTech composite's own numbers — Terrain / Terrain+ 8"
    (CCRR-0128 Table 1), any other TimberTech composite line 9" (TimberTech FAQ). None for any other board."""
    if getattr(st, "support_oc", 0):
        return float(st.support_oc)
    wood = decking_facts(s.decking.collection)["material"] == "Wood"
    if hasattr(eng, "tread_support_oc"):
        return float(eng.tread_support_oc(s.decking.collection, wood)[0])
    if s.decking.brand != "TimberTech" or decking_facts(s.decking.collection)["material"] != "Composite":
        return None
    return 8.0 if (s.decking.collection or "").startswith("Terrain") else 9.0


def run_flags(L: Layout) -> List[Flag]:
    s, fr, dk, rl = L.spec, L.frame, L.decking, L.rail
    g, site, ex = s.geometry, s.site, s.extras
    F: List[Flag] = []
    add = lambda sev, topic, text, ref="": F.append(Flag(sev, topic, text, ref))
    for ff in (getattr(s.extras, "field_flags", None) or []):           # the job's own field reads
        add(ff.get("severity", "CHECK"), ff.get("topic", "field"), ff["text"], ff.get("ref", ""))

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
        if not c.ok and ex.engineered and c.size.replace(" ", "") in eng.BEAM_ALIAS:     # a member outside R507.5 on an engineered job: the proxy row is not the limit
            add("ENGINEER", "engineering", f"{b.label} post spacing {ftin(c.actual_in)} is past the {eng.BEAM_ALIAS[c.size.replace(' ', '')]} table row ({ftin(c.allowable_in)}) the engine uses for a {c.size} — the engineer's NDS check governs (calc package)", "IRC Table R507.5 / NDS")
        elif not c.ok:
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
    for sl in (L.spec.geometry.sails or []):
        n_p = len(sl.get("posts", []))
        if sl.get("mount") == "deck_rail":
            add("ENGINEER", "engineering", f"{sl.get('name', 'Shade sail')}: the sail post{'s stand' if n_p != 1 else ' stands'} on the deck as the rail corner{'s' if n_p != 1 else ''} — base-plated on top of the decking over solid blocking: the sail's wind pull goes through the base plate bolts into the blocking, the frame, the knee-braced 6x6 posts and the house ledger: engineer checks the post-to-rim bolting, the frame and the lateral system for it", "ASCE 7 / IRC R507")
        add("ENGINEER", "engineering", f"{sl.get('name', 'Shade sail')}: sail wind load ({L.spec.site.wind_speed_mph:g} mph) on the {n_p} steel post{'s' if n_p != 1 else ''}{', their footings' if sl.get('mount') != 'deck_rail' else ''} and the house anchors — engineer sizes the posts / footings and the anchor connection into the house framing (not into siding or fascia alone)", "ASCE 7 / IRC R301.2")
        add("CHECK", "site", "shade sail: check whether the county wants a separate permit for the sail structure; the sail must meet the setbacks", "county")
    if fr.post_len > 96 and L.spec.framing.knee_braces:
        add("INFO", "engineering", f"posts {ftin(fr.post_len)}: 4x4 knee braces both directions at every post are in the takeoff — engineer confirms the lateral design", "DCA6 / IRC R507.4")
    elif fr.post_len > 96:
        add("CODE", "engineering", f"posts over 8' ({ftin(fr.post_len)}) — add diagonal knee bracing at each post (both directions at the corners)", "DCA6 / IRC R507.4")
    if g.height_in > 120:
        add("ENGINEER", "engineering", f"deck surface {ftin(g.height_in)} above grade — over 10': lateral bracing and an engineered design")
    if not fr.ledger:
        add("CODE", "engineering", "freestanding deck — no ledger lateral tie; provide diagonal bracing at posts or an engineered lateral system", "IRC R507.9 / R507.4")
    if g.shape != "rectangle" or g.notches:
        add("CHECK", "geometry", f"shape '{g.shape}'{' with ' + str(len(g.notches)) + ' notch(es)' if g.notches else ''} — takeoff is on the bounding rectangle {ftin(L.finished_w)} x {ftin(L.finished_d)}; hand-adjust the deducts")
    if g.levels > 1:
        add("CHECK", "geometry", f"{g.levels} levels — this takeoff covers one level; run one spec per level and add the step-down framing")
    ld_ = max([z.frame.footing_load_lb for z in (getattr(L, "zones", None) or []) if getattr(z, "frame", None) is not None] + [fr.footing_load_lb])   # the worst post on the deck (S-100's)
    if fr.footing_type == "diamond_pier" and ld_ > fr.footing_capacity_lb:
        add("STOP", "footing", f"post load {ld_:,.0f} lb exceeds {fr.footing_model} ({fr.footing_capacity_lb:,} lb) — more posts or concrete piers", "Pin Foundations chart")
    if fr.footing_type == "diamond_pier":
        add("CHECK", "footing", f"Diamond Pier: pins 50\" — locate utilities (811) before driving; bearing {ld_:,.0f} lb/post vs {fr.footing_capacity_lb:,} lb allowable (manufacturer chart, confirm)")
    if fr.footing_type == "existing":
        _worst = max([max(bl.post_loads) for bl in L.beam_lines if bl.post_loads] + [fr.footing_load_lb])
        add("ENGINEER", "footing", f"existing caissons reused — the engineer verifies capacity for the new loads ({_worst:,.0f} lb worst post); core or probe if no record", "IRC R507.3")
        if s.framing.existing_posts:
            add("ENGINEER", "engineering", "existing stucco columns reused — the engineer verifies the column core, its connection to the caisson, and details the new column caps")
    if s.railing.existing_parapet:
        add("CODE", "guard", "existing stucco parapet reused as the guard — verify 36\" min above the new deck surface and 200 lb top-rail load; if the new deck surface rises, the parapet height drops", "IRC R312.1")
        if s.railing.parapet_sides:
            open_edges = [e.name for e in L.edges if e.exposed and e.name not in s.railing.parapet_sides]
            if open_edges:
                hi_ = max(g.height_in, g.height_high_in or 0)
                add("STOP" if hi_ > eng.GUARD_TRIGGER_HEIGHT else "INFO", "guard",
                    f"open edge(s) {', '.join(open_edges)} carry no parapet and no rail — " + (f"{ftin(hi_)} above grade, a guard is required" if hi_ > eng.GUARD_TRIGGER_HEIGHT else f"{ftin(hi_)} above grade, under 30\", no guard required (the way out)"), "IRC R312.1.1")
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
            add("INFO", "ledger", (f"lateral: {s.framing.lateral_ties} tension ties per ledger, steel-joist kit / engineer's detail, into the house floor framing" if s.framing.system == "steel"
                                   else f"lateral: {s.framing.lateral_ties} x DTT1Z (750 lb each) spread evenly along the ledger, one within 24\" of each end, each on a 3/8\" lag 3\" min into the house floor framing"),
                "IRC R507.9.2" if s.framing.system == "steel" else "IRC R507.9.2(2)")

    # ---------------- wind
    v = site.wind_speed_mph
    if v >= 140:
        add("ENGINEER", "wind", f"basic wind speed {v:g} mph — uplift on the frame and rail loads; engineered connections (" + ("clip angles at every joist end, beam-to-post brackets, H2.5AZ at every cover rafter" if s.framing.system == "steel" else "H2.5A at every joist, post-to-beam uplift caps") + ")", "ASCE 7")
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

    if s.railing.post_size_in and rl:
        add("CHECK", "product", f"{s.railing.system} rail on {s.railing.post_size_in:g}\" posts — confirm the post SKU, price and bracket set; the order carries the stock post price", "supplier")
    # ---------------- guards & stairs
    hi = max(g.height_in, g.height_high_in or 0)
    if hi > eng.GUARD_TRIGGER_HEIGHT:
        if rl is None or not rl.sections:
            if not s.railing.existing_parapet:
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
            sev = "CODE" if "handrail" in n or "minimum" in n or "exceeds" in n else ("INFO" if n.startswith("flights:") else "CHECK")
            add(sev, "stairs", f"{st.side} stair: {n}", "IRC R311.7")
        add("INFO", "stairs", f"{st.side} stair: {st.geo.risers} risers @ {st.geo.riser_in:.2f}\" · {st.geo.treads} tread{'s' if st.geo.treads != 1 else ''} @ {st.geo.tread_in:.2f}\" · run {ftin(st.geo.total_run_in)} · "
            + ((f"framed 2x6 box, no stringers, {st.cross_members} cross members a box @ {ftin((st.width - 1.5) / max(1, st.cross_members - 1))} OC" if getattr(st, "cross_members", 0) else "framed 2x6 box, no stringers")
               if getattr(st, "build", "") == "box" else f"stringers {st.stringers} @ {st.width / max(1, st.stringers - 1):.0f}\" OC")
            + (f" ({st.support_oc:g}\" max under {s.decking.collection} treads: {st.support_src})" if getattr(st, "support_oc", 0) else "")
            + ("  — " + " then ".join(f"{fg.risers} risers (run {ftin(fg.run_in)})" for fg in st.geo.flights) + " with a landing between" if len(st.geo.flights) > 1 else ""), "IRC R311.7.5 / TimberTech")
        if len(st.geo.flights) > 1:
            add("CODE", "stairs", f"{st.side} stair landing: 36\" min in the direction of travel and at least as wide as the stair; guard on every open side over 30\" ({st.landing_rail_lf:g} LF counted)" if st.landing_rail_lf else f"{st.side} stair landing: 36\" min in the direction of travel and at least as wide as the stair", "IRC R311.7.6 / R312.1")
        if st.landing == "grade":
            add("CODE", "stairs", f"{st.side} stair lands on grade — the bottom landing is the grade itself: 36\" min in the direction of travel, as wide as the stair, "
                "firm and level (no pad in this scope); if the inspector wants a hard surface there, pavers are an add", "IRC R311.7.6")
        if st.geo.guard_required and st.stair_rail_sides == 0:
            add("STOP", "stairs", f"{st.side} stair: open side over 30\" — stair guard required", "IRC R312.1")
        box_, mx_ = getattr(st, "build", "") == "box", tread_oc_max(s, st)      # what carries the treads vs the tread line's max (the stair layout's own)
        n_ = getattr(st, "cross_members", 0) if box_ else st.stringers
        oc_ = ((st.width - 1.5) if box_ else st.width) / (n_ - 1) if n_ > 1 else 0.0
        if mx_ and oc_ > mx_ + 0.25:
            add("CHECK", "stairs", f"{st.side} stair: {'cross members' if box_ else 'stringers'} @ {oc_:.0f}\" OC — over the {mx_:g}\" max for {s.decking.collection} treads: "
                f"add {'cross members' if box_ else 'stringers'}" + (", or 2x6 blocking per CCRR-0128 Figure 10 for a 16\" span" if s.decking.collection in FIG10_LINES else ""),
                "CCRR-0128 Table 1 / TimberTech")

    # ---------------- roof covers
    from .spec import covers_of
    for c in covers_of(s):
        hi, lo = c.get("clear_high_in"), c.get("clear_low_in")
        run_ft = (c["x1"] - c["x0"]) if c.get("slope", "+y") in ("+x", "-x") else (c["y1"] - c["y0"])
        run_ft += float(c.get("overhang_ft", 1.0))
        if hi is not None and lo is not None and run_ft > 0:
            pitch = (float(hi) - float(lo)) / (run_ft - float(c.get("overhang_ft", 1.0)))     # in per ft
            if ex.cover_roof.lower().startswith("standing"):
                mech = ex.cover_roof_panel.lower().startswith("mech")
                need = 0.5 if mech else 3.0
                if pitch < need - 0.01:
                    add("STOP" if not mech else "ENGINEER", "roof", f"{c['name']}: {pitch:.2f}:12 pitch ({hi:g}\" to {lo:g}\" clear over {ftin((run_ft - float(c.get('overhang_ft', 1.0))) * 12)}) is under the "
                        f"{need:g}:12 minimum for {'mechanically seamed' if mech else 'snap-lock'} panels — raise the house end or switch panels", "panel manufacturer")
                else:
                    add("INFO", "roof", f"{c['name']}: {pitch:.2f}:12 pitch — {'mechanically seamed (double-lock) panels, rated to 1/2:12 by most makers' if mech else 'snap-lock'}; "
                        "high-temp self-adhered underlayment over the whole deck, panels one piece eave to headwall")
                    if mech and pitch < 1.0:
                        add("CHECK", "roof", f"{c['name']}: low-slope metal ({pitch:.2f}:12) — the panel maker's low-slope details (seam sealant, field seaming, no end laps) and warranty; confirm with the metal supplier")
            if float(lo) < 80:
                add("CODE", "roof", f"{c['name']}: {lo:g}\" clear at the beam — under 6'-8\" headroom where people walk out from under it", "IRC R305 (by analogy)")
        if c.get("footing") == "deck_pier":
            from .takeoff import shared_pier_loads
            loads = shared_pier_loads(s, L, c)
            x, w, deck = max(loads, key=lambda t: t[1] + t[2])
            cap = fr.footing_capacity_lb
            add("ENGINEER" if deck + w > 0.9 * cap else "CHECK", "footing",
                f"{c['name']}: cover post + deck beam share a Diamond Pier — worst ~{w:,.0f} lb roof (ground snow {site.ground_snow_psf:g} + 15 psf dead) + {deck:,.0f} lb deck = ~{w + deck:,.0f} lb "
                f"vs {cap:,.0f} lb DP-50/50" + (" — priced as DP-75/63 (6,000 lb) at those posts" if deck + w > cap else "") + f"; uplift at {site.wind_speed_mph:g} mph — engineer confirms the pier and the post-to-pier hold-down", "IBC App. I / ASCE 7")
        # the cover beam in bending between its posts: roof snow + 15 psf dead on half the rafter run plus the overhang
        from .takeoff import cover_posts_x as _cpx
        from .catalog import parse_beam as _pb, actual as _act
        _px = sorted(_cpx(c))
        if len(_px) >= 2:
            span_ft = max(b_ - a_ for a_, b_ in zip(_px, _px[1:]))
            trib = (c["y1"] - c["y0"]) / 2 + float(c.get("overhang_ft", 1.0))
            w_plf = trib * (site.ground_snow_psf + 15.0)
            plies, nom, _, _ = _pb(c.get("beam", "(2)2x10"))
            b_in, d_in = _act(nom)
            S_in3 = plies * b_in * d_in ** 2 / 6
            fb = w_plf * span_ft ** 2 / 8 * 12 / S_in3
            fb_allow = 1200.0       # SYP #2 2x, snow duration + repetitive member, rounded down
            if fb > fb_allow:
                add("ENGINEER", "engineering", f"{c['name']}: {c.get('beam', '(2)2x10')} beam spans {ftin(span_ft * 12)} between posts — about {fb:,.0f} psi bending "
                    f"(~{w_plf:,.0f} plf roof) vs ~{fb_allow:,.0f} psi allowable: upsize to (2)2x12, (3)2x10 or a 3-1/2\" x 9-1/4\" LVL, or add a post — engineer sizes it", "NDS / IRC R802")
            else:
                add("INFO", "engineering", f"{c['name']}: {c.get('beam', '(2)2x10')} beam spans {ftin(span_ft * 12)} — about {fb:,.0f} psi bending vs ~{fb_allow:,.0f} psi allowable")
        add("ENGINEER", "snow", f"{c['name']}: a lean-to under the house eave takes sliding snow off the house roof and drift against the wall — ASCE 7 sliding + drift surcharge on the cover", "ASCE 7-22 7.7 / 7.9")
    # ---------------- steel frame
    if s.framing.system == "steel":
        add("ENGINEER", "engineering", "CEMCO cold-formed steel frame: no prescriptive deck span table in the IRC for CFS — the engineer of record designs joists, beams, clips and the ledger connection (AISI S240 / S100); member sizes here are the same-depth lumber layout", "IRC R507 / AISI S240")
        add("CHECK", "product", f"{s.decking.brand} {s.decking.collection} hidden fasteners and picture-frame screws into steel: use the maker's steel-frame screw (self-drilling, for 14–18 ga) — confirm the fastener and that the decking warranty covers steel framing")
        add("CHECK", "product", "steel frame prices are estimates (no CEMCO dealer quote yet) — get the take-off quoted by the CEMCO dealer before the contract is signed")
    if g.height_min_in is not None:
        dk_t = f["thick"] if "thick" in f else 1.0
        clear = g.height_min_in - dk_t - actual(fr.joist_size)[1]
        if clear < 2.0:
            add("CHECK", "geometry", f"lowest point: {g.height_min_in:g}\" surface to grade leaves {clear:.2f}\" under the {actual(fr.joist_size)[1]:g}\" frame — dig out / regrade to 2\" min. clear (and away from the house) "
                "under that section, or drop to 6\" joists there", "TimberTech / ventilation")
    for af in site.ahj_flags:
        add(*(list(af) + [""] * (4 - len(af)))[:4])

    # ---------------- product / fastening sanity
    if f["material"] == "PVC" and fr.spacing > 12:
        add("CODE", "product", f"PVC decking at {fr.spacing:g}\" OC — TimberTech Advanced PVC at GSX is 12\" OC", "TimberTech install guide")
    if f["material"] == "Composite" and fr.spacing > 16:
        add("CODE", "product", f"composite at {fr.spacing:g}\" OC exceeds the 16\" residential max", "TimberTech install guide")
    if s.decking.color not in f.get("colors", [s.decking.color]):
        add("CHECK", "product", f"'{s.decking.color}' is not a current {s.decking.collection} color — discontinued or a different line; confirm with D&D")
    if s.framing.rim_plies > 2:
        add("CHECK", "product", f"{s.framing.rim_plies}-ply rims — GSX standard is double rims; never add plies")
    if s.decking.collection == "Terrain+" and "Cortex" in (s.decking.fastener_system or "", s.decking.border_fastener or ""):
        add("CHECK", "product", "Cortex in Terrain+: TimberTech's install guide (REV 09/23) lists Terrain and Terrain+ under 'Restricted Cortex Uses' while the Terrain+ product page says "
            "compatible — get TimberTech's written OK before ordering (877-275-2935); the fallback is TOPLoc face screws with a 5/32\" pre-drill", "TimberTech install guide p.12")
    if ex.hardie_skirt:                  # TR1509 p.3: finish nails into a wood frame (ring shank when stainless), screws or ET&F pins into steel
        add("CHECK", "hardie", f"get James Hardie Technical Services' written OK for HardieTrim as deck fascia{' and stair risers' if s.stairs else ''} (not a listed use) before ordering — 800-942-7343; "
            "build to TR1509 (09/25): " + ("color-matched 316SS trim screws (or ET&F pins) into the steel furring / track, 3/4\" from the edges" if s.framing.system == "steel"
                                          else "2-1/2\" 16-ga 316SS ring-shank finish nails, 1/2\" from the edges")
            + f", 2\" over soil or mulch, 1/4\" over {'brick, pavers and treads' if s.stairs else 'brick or pavers'}, never caulked", "James Hardie TR1509")
    if s.decking.brand == "TimberTech" and f["material"] == "Composite" and (s.decking.fastener_system or default_fastener_system(s.decking.collection, s.decking.profile)) == "CONCEALoc":
        add("CHECK", "product", "first and last field rows: TimberTech's CONCEALoc instructions face-fasten them with TOPLoc for Composite (5/32\" pre-drill, 3/4\" from the edge; Cortex or the "
            "L-Bracket also, except Terrain) — the GSX Cap-Tor xd is not named: get TimberTech's written OK for it (877-275-2935) or order TOPLoc", "TimberTech install guide p.9 / IRC R507.2.2")
    if s.decking.brand == "TimberTech" and g.height_in <= 30:
        add("CHECK", "ventilation", "at least 1-1/2\" between grade and the bottom of every joist and rim — the skirt or fascia, a brick border and mulch must not seal the underside", "TimberTech FAQ")
    if not (site.rear_setback_required_ft or site.side_setback_required_ft) and not site.address:
        add("INFO", "setback", "no address on the spec — tax rate and jurisdiction defaults used")

    import re as _re
    for f in F:                          # named stairs read by name; outline sides by their A-100 number
        for st_ in s.stairs:
            if getattr(st_, "name", None):
                f.text = f.text.replace(f"{st_.side} stair", st_.name)
        if g.outline:
            f.text = _re.sub(r"\bedge:(\d+)", r"side \1", f.text)
    seen, uniq = set(), []
    for f in F:
        if (f.severity, f.text) not in seen:
            seen.add((f.severity, f.text)); uniq.append(f)
    uniq.sort(key=lambda x: SEV.get(x.severity, 9))
    return uniq
