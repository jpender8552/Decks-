"""The build set: drawing sheets (SVG), the 3D model, rendered stills, and the step-by-step build pages —
all from one Layout. Writes a folder; returns the pieces so the service and the artifact page can embed them."""
from __future__ import annotations

import base64
import html as _html
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .drawings import all_sheets, sheet, sheet_meta, T, R, LN, esc, INK, GOLD, MUTE
from .layout import Layout
from .scene import build_scene, Scene, PHASES
from .takeoff import Takeoff
from .catalog import parse_beam, RAIL_SYSTEMS
from .spec import covers_of, post_words, post_base_sku
from .units import ftin
from .viewer import viewer_html

STEP_VIEWS = {1: "step1", 2: "step2", 3: "step3", 4: "step4", 5: "step5", 6: "step6", 7: "step7", 8: "step8"}


def step_sheets(t: Takeoff, L: Layout) -> List[dict]:
    """Build steps generalized from the takeoff: what goes in, how to build it, what to check — per phase."""
    s = L.spec
    timber = s.is_timber
    lines = t.lines
    def items(pred, n=7):
        return [f"({l.net:g}) {l.item}" for l in lines if pred(l)][:n]
    fr = L.frame
    n_posts = L.n_footings
    ft = s.framing.footing_type
    steps = []
    # 1 footings
    steps.append(dict(n=1, code="T-400", title="Footings", still="step1",
        goes_in=items(lambda l: l.category == "Footings" and "Stone" not in l.item and "post base" not in l.item.lower()),   # the bases go in with the posts
        how=[f"Call 811 and locate before any hole or pin. Strip the existing deck first." if s.extras.demo_existing else "Call 811 and locate before any hole or pin.",
             "Pull the beam lines from the house wall: " + "; ".join(f"{bl.label} at {ftin(bl.y)} from the reference wall, posts at " + " / ".join(ftin(x) for x in bl.posts_x) for bl in L.beam_lines) + "."
             + (f" Edge posts {L.edge_posts[0].label}-{L.edge_posts[-1].label} at the outline corners, under both rims (S-100 schedule)." if getattr(L, "edge_posts", None) else ""),
             {"caisson": f"Auger {n_posts} holes {int(fr.footing_dia_in)}\" x {ftin(fr.footing_depth_in)} (frost {ftin(s.site.frost_depth_in)}), tube to 6\" above grade, cage in, pour, set the 5/8\" anchors wet. Cure 2 days.",
              "diamond_pier": f"Set {n_posts} Diamond Pier heads level at grade on undisturbed soil and drive the 4 pins in each; caps on.",
              "concrete": f"Dig and form {n_posts} piers {int(fr.footing_dia_in)}\" x {ftin(fr.footing_depth_in)}, pour, set the standoff bases wet.",
              "existing": (f"The {n_posts} existing caissons and columns stay. Expose each caisson top, check plumb and cracking, photograph; the engineer confirms the column and caisson before the new beams land on them."
                           if s.framing.existing_posts else
                           f"The {n_posts} existing caissons stay. Chip each top level, drill and epoxy-set two 5/8\" rods per base (SET-3G), set the standoff bases; the engineer confirms caisson capacity for the new loads.")}[ft]],
        check=["Footings on the layout within 1/2\"; bearing on undisturbed soil" if ft != "existing" else "Every existing caisson sound, level and on the beam line; engineer's sign-off in the file",
               "Frost depth met" if ft not in ("diamond_pier", "existing") else ("Pins fully driven, heads level" if ft == "diamond_pier" else "Epoxy cured before load"), "Photos before backfill"]))
    steps.append(dict(n=2, code="T-401", title="Posts", still="step2",
        goes_in=items(lambda l: l.category == "Lumber" and s.framing.post_size in l.item) + items(lambda l: "post base" in l.item.lower() or "anchor" in l.item.lower() or "to the edge posts" in l.item),
        how=([f"The existing stucco columns stay. Strip the old beam off each column top, check the column core and its bearing; new column caps / saddles per the engineer, then the beams land on them."]
             if s.framing.existing_posts else
             [f"{s.framing.post_size} posts on the bases; cut so the beam top lands at "
              + {frozenset({"drop"}): "the joist bottom (drop beams)", frozenset({"flush"}): "the joist top (flush beams)"}.get(
                  frozenset(b_.kind for b_ in s.framing.beams), "the joist bottom (drop beam) or the joist top (flush beam)")
              + ": " + " / ".join(f"{bl.label} posts {ftin(bl.post_len)}" for bl in L.beam_lines) + " — field-measure each.",
              "Plumb both ways, brace, then the caps go on with the beams."]
             + ([f"Edge posts {L.edge_posts[0].label}-{L.edge_posts[-1].label}: one under each outline corner, top cut to the rim bottom ({ftin(L.edge_post_len)} nominal); "
                 "the rims land on them with (2) A35Z per rim — the rims span post to post as flush beams."] if getattr(L, "edge_posts", None) else [])
             + (["Seal every cut end before it goes up."] if timber and s.framing.end_grain_seal else [])),
        check=["Posts plumb to a string; tops on the beam line", "Every cut end sealed" if timber else "No post in ground contact without a standoff"]))
    if s.extras.stone_bases:
        steps.append(dict(n=3, code="T-402", title="Stone column bases", still="step3",
            goes_in=items(lambda l: "Stone" in l.item),
            how=["Mason after the posts and before the beams or after the frame — owner's call on access. Cement board wrap, lath, scratch, ledgestone, 24\" cap.", "Keep the cap 1/2\" clear of the post; caulk the joint."],
            check=["Stone plumb and square to the deck; caps level", "Sample color approved by the homeowner"]))
    if s.framing.system == "steel":
        steps[-1] = dict(n=2, code="T-401", title="Posts", still="step2",
            goes_in=items(lambda l: "HSS" in l.item or "pier-head" in l.item.lower() or "side bracket" in l.item.lower() or "ABA66" in l.item or "deck posts" in l.item or "saddle" in l.item),
            how=[(f"Deck-only piers: 6x6 {post_words(s)} posts on {post_base_sku(s)} bases, galvanized steel saddles on top carrying the boxed beams, cut so the beam top lands at the joist top (flush beams): "
                  if s.framing.steel_deck_post == "wood" else "Deck-only piers: 3x3 galvanized HSS stubs on the pier-head brackets, cut so the boxed steel beam top lands at the joist top (flush beams): ")
                 + " / ".join(f"{bl.label} {ftin(bl.post_len)}" for bl in L.beam_lines) + " — field-measure each.",
                 f"Where a roof-cover post lands on the deck beam line it stands on the same Diamond Pier on an {post_base_sku(s)} base; the 6x6 {post_words(s)} post runs up to the cover beam and the deck beam bolts to it with the steel side bracket.",
                 "Plumb both ways and brace until the beams are on."],
            check=["Posts plumb to a string; tops on the beam line", "Every bracket and saddle fastened: thru-bolts and #12 screws per the engineer"])
    import re as _re
    is_beam = lambda l: l.category == "Lumber" and (("beam" in (l.why or "").lower() and "stringer" not in (l.why or "").lower())
                                                    or bool(_re.match(r"^(6x(8|10|12|14)|4x12)x", l.item)) or ("4x10x" in l.item and not timber))
    caps = sorted({bl.cap_mid for bl in L.beam_lines if bl.cap_mid})
    two_by = any(parse_beam(bl.size)[0] >= 2 and parse_beam(bl.size)[1].startswith("2x") for bl in L.beam_lines)
    steps.append(dict(n=4, code="T-403", title="Beams", still="step4",
        goes_in=items(is_beam) + items(lambda l: "cap" in l.item.lower() and l.category == "Hardware") + items(lambda l: l.item.startswith("Simpson SD10212")),
        how=[f"{bl.label}: {ftin(bl.length)} " + (f"in {len(bl.pieces)} pieces spliced over posts" if len(bl.pieces) > 1 else "one piece") + f", {bl.n_posts} posts @ {ftin(max((b - a) for a, b in zip(bl.posts_x, bl.posts_x[1:])) if bl.n_posts > 1 else bl.length)} max" for bl in L.beam_lines]
            + ["Crown up, strung straight, caps screwed off with the " + ("SDS screws in the box." if any(c.startswith("CCQ") for c in caps) else "SD screws (SD10212).")]
            + ([f"Built-up beam: laminate the plies with GRK RSS 3-1/8\", 2 rows 2\" from top and bottom, staggered @ 12\" OC, before it goes up; "
                f"a 1/2\" shim in each {caps[0] if caps else 'BC46Z'} (the (2)2x is 3\" in the 3-9/16\" seat)."] if two_by else [])
            + ([f"Two-ply beam: through-bolt the plies with 1/2\" HDG bolts, 2 rows 2\" from top and bottom, staggered @ 24\" OC, a pair 6\" from each end — before it goes up."]
               if any(parse_beam(bl.size)[0] == 2 and parse_beam(bl.size)[1].startswith("4x") for bl in L.beam_lines) else [])
            + ([f"Knee braces once the beam is capped: 4x4 at 45°, {ftin(s.framing.knee_leg_in)} legs, one along the beam toward mid-span and one toward the house up to a {s.framing.joist_size} block between two joists (set the block with the frame) — 1/2\" through-bolt each end, then pull the temporary bracing."]
               if s.framing.knee_braces else []),
        check=[{frozenset({"drop"}): "Beam top = joist bottom (drop beams), crown up", frozenset({"flush"}): "Beam top = joist top (flush beams), crown up"}.get(
                   frozenset(b_.kind for b_ in s.framing.beams), "Beam top = joist bottom (drop) / joist top (flush)"), "Splices land on a post; caps fully fastened"] + (["Every knee brace bolted both ends; posts still plumb"] if s.framing.knee_braces else [])))
    if s.framing.knee_braces:
        steps[-1]["goes_in"] = steps[-1]["goes_in"] + items(lambda l: "knee brace" in l.item or "1/2\" x 8\"" in l.item)
    if s.framing.system == "steel":
        steps[-1] = dict(n=4, code="T-403", title="Beams", still="step4",
            goes_in=items(lambda l: "boxed beams" in l.item or "side bracket" in l.item.lower()),
            how=[f"{bl.label}: {ftin(bl.length)} one piece, {bl.n_posts} posts @ {ftin(max((b - a) for a, b in zip(bl.posts_x, bl.posts_x[1:])) if bl.n_posts > 1 else bl.length)} max" for bl in L.beam_lines]
                + ["Box two C sections toe-to-toe, #12 self-drilling screws per the engineer's pattern; set flush with the joist tops; brackets to the stubs and cover posts."],
            check=["Beam top = joist top (flush)", "Brackets fully fastened; cut ends cold-galvanized"])
    steps.append(dict(n=5, code="T-404", title="Frame", still="step5",
        goes_in=items(lambda l: l.category == "Lumber" and s.framing.joist_size in l.item and not is_beam(l), 6)
                + items(lambda l: l.category in ("Hardware", "Flashing & waterproofing") and any(k in l.item for k in ("hanger", "LedgerLOK", "H2.5", "Vycor", "flashing", "G-Tape", "membrane", "DTT1Z"))
                        or (l.category == "Hardware" and l.item.startswith("GRK RSS") and "100 ct" in l.item), 14),
        how=[t.schedule.get("Ledger", "Ledger per the schedule."),
             "; ".join(f"{z.name}: {len(z.frame.joist_x)} joists @ {z.frame.spacing:g}\" OC x {ftin(z.frame.joist_len)}" for z in L.zones) + ". Crown up, hangers at the ledger" + (", both faces of the flush beam" if any(b.kind == "flush" for b in L.beam_lines) else "") + ".",
             t.schedule.get("Blocking", "Blocking one row over the beam, staggered."), t.schedule.get("Joist tape", "Tape every joist top.")],
        check=["Frame square: diagonals within 1/8\"", "Every hanger fully nailed; ledger fasteners per the schedule", "Tape continuous; photos of the ledger, hangers and footings before decking"]))
    if s.framing.system == "steel":
        steps[-1] = dict(n=5, code="T-404", title="Frame", still="step5",
            goes_in=items(lambda l: l.category == "Lumber" and ("C-joist" in l.item or "track" in l.item or "ledger angle" in l.item))
                    + items(lambda l: l.category in ("Hardware", "Flashing & waterproofing") and any(k in l.item for k in ("clip angle", "self-drilling", "Structural screw", "tension tie", "Vycor", "flashing", "poly", "gravel")), 8),
            how=[t.schedule.get("Ledger", "Ledger per the schedule."),
                 "; ".join(f"{z.name}: {len(z.frame.joist_x) + len(z.frame.pf_x)} CEMCO {__import__('decktakeoff.steel', fromlist=['names']).names(s)['joist']} C-joists @ {z.frame.spacing:g}\" OC x {ftin(z.frame.joist_len)}" for z in L.zones)
                 + ". Joists seat on the ledger angle and clip to the ledger track and the boxed beams with clip angles, 4 #12 screws per leg.",
                 "Track caps every joist end at the rims; picture-frame and breaker joists doubled where the borders land.",
                 "Gravel over 6-mil poly under the frame before the decking (2\" min. clear at the walkway low end).",
                 t.schedule.get("Steel frame", "")],
            check=["Frame square: diagonals within 1/8\"", "Every clip fully screwed; ledger screws per the schedule", "Cut ends cold-galvanized; photos of the ledger, clips and footings before decking"])
    steps.append(dict(n=6, code="T-405", title="Decking", still="step6",
        goes_in=items(lambda l: l.category in ("Decking", "Fasteners", "Fascia"), 14),
        how=[t.schedule.get("Field", ""), t.schedule.get("Face screws", "Borders first, then the field."),
             (L.plan.summary() if L.plan is not None else "Rows per zone: " + " · ".join(f"{z.name} {z.decking.rows}" for z in L.zones)) + ". Borders and breakers first, then the field rows from the outer edge toward the house."],
        check=[f"{ftin(s.deck_gap)} gaps held", "No cut end shows at the outer edge", "Color: every board from the same run"]))
    steps.append(dict(n=7, code="T-406", title="Rail", still="step7",
        goes_in=items(lambda l: l.category == "Rail", 10) + items(lambda l: l.category == "Hardware" and ("rail posts" in (l.why or "") or "HeadLOK" in l.item)),
        how=[t.schedule.get("Rail", "")] + (["Drink rail on TimberTech drink-rail brackets, mitred at every turn, plugs color-matched."] if s.railing.drink_rail else []),
        check=[f"Top of rail {L.rail.height:g}\" above the decking; posts plumb" if L.rail else "—",
               "Cables tensioned, no 4\" sphere passes" if RAIL_SYSTEMS.get(s.railing.system, {}).get("cable") else "Balusters under 4\" clear"]))
    # stairs and the box step (their own crew day), then the built-ins — the order lines that go in with each
    from .takeoff import inches_frac
    if s.stairs and L.stairs:
        how_ = []
        for ss_, sl_ in zip(s.stairs, L.stairs):
            nm_, g_ = getattr(ss_, "name", None) or "Stair", sl_.geo
            if getattr(sl_, "build", "") == "box":
                how_.append(f"{nm_}: {g_.risers} risers @ {inches_frac(g_.riser_in)} — a framed 2x6 box {ftin(sl_.width)} wide on a 4\" compacted 3/4\" base, "
                            "screwed to the rim (RSS), fascia on the front and both ends, decked in the field board; no stringers.")
            else:
                oc_ = sl_.width / max(1, sl_.stringers - 1)
                how_.append(f"{nm_}: {g_.risers} risers @ {inches_frac(g_.riser_in)}, {g_.treads} tread{'s' if g_.treads != 1 else ''} @ {inches_frac(g_.tread_in)} — "
                            f"{sl_.stringers} 2x12 stringers @ {oc_:.0f}\" OC on LSCZ connectors at the rim"
                            + (", fascia skirts both sides stepped under each tread" if getattr(sl_, "skirts", False) else "") + ", closed risers, treads Cortex 2 per stringer per board.")
        if any(getattr(ss_, "landing", "") == "grade" for ss_ in s.stairs):
            how_.append("Each stair lands on grade: 36\" of firm, level ground at the bottom, as wide as the stair (no pad in this scope).")
        steps.append(dict(n=8, code="T-407", title="Stairs" + (" and the box step" if any(getattr(sl_, "build", "") == "box" for sl_ in L.stairs) else ""), still="yard",
            goes_in=items(lambda l: (l.category == "Lumber" and any(k in (l.why or "") for k in ("stair", "box step")))
                          or (l.category == "Stairs" and "door step" not in l.item.lower()) or (l.category == "Hardware" and ("stair" in l.item.lower() or "box step" in l.item.lower())), 14),
            how=how_,
            check=["Risers within 3/8\" of each other; treads level, nosings straight", "Landing at the bottom firm and level, 36\" deep", "Skirts and fascia tight; plugs set flush"]))
    if s.geometry.benches or s.geometry.planters or getattr(s.geometry, "door_step", None):
        how_ = []
        for bn in (s.geometry.benches or []):
            nb_ = bn.get("name") or ""
            how_.append(f"{nb_ if 'bench' in nb_.lower() else ('Bench, ' + nb_ if nb_ else 'Bench')}: {bn.get('seat_in', 17):g}\" seat, {bn.get('depth_in', 17):g}\" deep" + (f", back to {bn.get('back_in', 34):g}\"" if bn.get("back", True) else "")
                        + " — 4x4 back posts bolted through the rim (2 x 1/2\" carriage bolts each), 4x4 front legs, 2x6 seat rails with supports @ 16\" OC, every post wrapped in deck board; "
                        "three seat boards (the outer two in the frame color), a front apron, three back slats; Cortex throughout.")
        for pl in (s.geometry.planters or []):
            np_ = pl.get("name") or ""
            how_.append(f"{np_ if 'planter' in np_.lower() else ('Planter, ' + np_ if np_ else 'Planter')}: {pl.get('width_in', 17):g}\" x {pl.get('height_in', 17):g}\" — treated 2x4 walls (studs 12\" OC, top and bottom plates), 7/16\" OSB, "
                        "6-mil liner over a drainage mat, deck-board skin on every side, picture-frame cap; Cortex.")
        if getattr(s.geometry, "door_step", None):
            how_.append("Door step: the framed 2x6 box on the deck at the door, decked, riser board and returns.")
        steps.append(dict(n=9, code="T-408", title="Built-ins — " + ", ".join(w for w, on in (("benches", s.geometry.benches), ("planter" + ("s" if len(s.geometry.planters or []) > 1 else ""), s.geometry.planters),
                                                                                            ("door step", getattr(s.geometry, "door_step", None))) if on), still="corner",
            goes_in=items(lambda l: l.category in ("Benches", "Planters") or "door step" in l.item.lower(), 14),
            how=how_,
            check=["Bench seats level at the seat height, backs plumb, posts tight to the rim", "Planter liner lapped and drained before any soil", "No screw head showing; plugs flush"]))
    if s.geometry.cover or s.geometry.covers:
        from .takeoff import cover_size
        along, out, area = cover_size(s)
        ss = s.extras.cover_roof.lower().startswith("standing")
        steps.append(dict(n=8, code="T-407", title="Porch cover", still="step8",
            goes_in=items(lambda l: l.category == "Porch cover", 14),
            how=[f"Cover ledger on the house at the top of the pitch, LedgerLOK 2 rows; 6x6 {post_words(s)} posts "
                 + (f"on {post_base_sku(s)} bases on the Diamond Piers (shared with the deck beam where they line up)" if any(c_.get("footing") in ("diamond_pier", "deck_pier") for c_ in covers_of(s)) else "on the deck over blocked joists")
                 + f", " + " / ".join(f"{c_['name'].lower()}: {c_.get('beam', '(2)2x10')} beam on {'BC46Z' if c_.get('beam', '').startswith('4x') else 'AC6Z'} caps" for c_ in covers_of(s)) + "; 2x8 rafters @ 16\" OC with H2.5AZ ties and the overhang; 2x8 sub-fascia and OSB. Cover framing is wood (SYP 2x8 rafters, Douglas fir posts" + ("; Douglas fir 4x beam" if any(c_.get("beam", "").startswith("4x") for c_ in covers_of(s)) else "") + ").",
                 ("High-temp self-adhered underlayment over every sheet, headwall flashing counterflashed into the house wall, eave trim, then the 24 ga snap-lock panels one piece eave to headwall — clips 18\" OC on each seam, no face screws in the field; rake trim and closures last; snow retention bar clamped to the seams 12-18\" above the low eave, the full width."
                  if ss else "Synthetic underlayment, drip edge, starter, architectural shingles 6 nails each, step flashing at the house wall.")]
                + ([f"5\" K gutter on the low eave, hangers 24\" OC, 1/16\" per foot toward the outlets; 2x3 downspouts strapped to the cover posts, offset past the deck edge, down the deck post to a splash block 3'+ from the footing."] if s.extras.cover_gutters else [])
                + ([f"Ceiling: {s.extras.cover_soffit} panels 6\" OC stainless ring-shank at every rafter; " + (f"{s.extras.cover_fascia} fascia and rakes over the 2x8 sub-fascia, color-matched trim screws." if s.extras.cover_fascia else "")] if s.extras.cover_soffit else ["1x6 T&G ceiling, blind-nailed."]),
            check=["Ledger flashed and counterflashed — hose test before the ceiling closes", "Posts plumb over blocking, beam level, rafters tied",
                   "Panels straight, seams engaged full length, no oil-canning; snow bar continuous" if ss else "Shingles straight, ridge cap sealed",
                   "Gutter falls to the outlets, downspouts discharge away from the footings" if s.extras.cover_gutters else "Water sheds clear of the deck edge"]))
    steps[-1]["check"] = steps[-1]["check"] + ["End of construction"]     # on whichever step is built last
    for i, st_ in enumerate(steps):          # numbered as built: the phase numbers skip (no stone bases, no cover)
        st_["n"], st_["code"] = i + 1, f"T-4{i:02d}"
    return steps


def buildset_html(t: Takeoff, sheets: List[Tuple[str, str, str]], steps: List[dict], stills: Dict[str, str], viewer_body: str, title: str) -> str:
    """One page: sheets, isometric renders, build steps, embedded 3D."""
    def img(name):
        p = stills.get(name)
        if not p:
            return ""
        data = base64.standard_b64encode(Path(p).read_bytes()).decode()
        return f'<img src="data:image/jpeg;base64,{data}" alt="{esc(name)}">'
    out = [f"<title>{esc(title)}</title>", '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,300;6..12,400;6..12,700;6..12,900&display=swap">',
           '<style>body{margin:0;background:#f5f1e7;color:#141414;font-family:"Nunito Sans",system-ui,sans-serif;} .wrap{max-width:1040px;margin:0 auto;padding:16px;} h1{font-size:22px;margin:0 0 4px;} .k{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#7a5300;font-weight:800;margin:28px 0 8px;} .sheet{margin:0 0 18px;} .sheet svg{width:100%;height:auto;display:block;border:1px solid #d9d2c3;} img{max-width:100%;display:block;border:1px solid #d9d2c3;} .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;} .step{display:grid;grid-template-columns:1.2fr 1fr;gap:16px;margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid #d9d2c3;} .step h3{margin:0 0 6px;font-size:16px;} .step h4{margin:10px 0 4px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#7a5300;} .step ul{margin:0;padding-left:18px;font-size:14px;} .step li{margin:2px 0;} .v3d-root{height:520px;} @media (max-width:640px){.grid,.step{grid-template-columns:1fr;} .v3d-root{height:380px;}}</style>',
           '<div class="wrap">', f"<h1>{esc(title)}</h1>", '<div class="k">Renders</div>', '<div class="grid">', img("yard"), img("corner"), img("ondeck"), img("under"), "</div>",
           '<div class="k">Isometric · exploded</div>', '<div class="grid">', img("iso"), img("exploded"), "</div>",
           '<div class="k">Drawing set</div>']
    for num, ttl, svg in sheets:
        out.append(f'<div class="sheet" id="{num}">{svg}</div>')
    out.append('<div class="k">Build steps</div>')
    for st in steps:
        out.append(f'<div class="step"><div>{img(st["still"])}</div><div><h3>{st["code"]} · Step {st["n"]} · {esc(st["title"])}</h3>'
                   + '<h4>Goes in</h4><ul>' + "".join(f"<li>{esc(g)}</li>" for g in st["goes_in"]) + "</ul>"
                   + '<h4>How</h4><ul>' + "".join(f"<li>{esc(h)}</li>" for h in st["how"] if h) + "</ul>"
                   + '<h4>Check</h4><ul>' + "".join(f"<li>{esc(c)}</li>" for c in st["check"]) + "</ul></div></div>")
    out.append('<div class="k">3D model — drag to orbit, wheel or pinch to zoom, steps and exploded view below</div>')
    out.append(viewer_body)
    out.append("</div>")
    return "\n".join(out)


def build_set(t: Takeoff, flags, out_dir: str, render: bool = True, customer: bool = False) -> dict:
    """Write drawings (SVG + HTML), viewer.html, renders/, buildset.html. Returns paths + in-memory pieces."""
    L = t.layout
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    S = build_scene(L)
    if hasattr(L, "parts"):     # composite: the drawing sheets are per part (each in its own frame); the 3D and the steps are the whole deck
        sheets = []
        for i, p in enumerate(L.parts):
            tag = chr(65 + i)
            for num, ttl, svg in all_sheets(p.layout, p.takeoff, p.flags, build_scene(p.layout), customer=customer):
                if num == "G-001" and i > 0:
                    continue
                sheets.append((num if num == "G-001" else f"{num}-{tag}", f"{ttl} — {p.name}", svg))
    else:
        sheets = all_sheets(L, t, flags, S, customer=customer)
    (out / "sheets").mkdir(exist_ok=True)
    for num, ttl, svg in sheets:
        (out / "sheets" / f"{num}.svg").write_text(svg)
    stills: Dict[str, str] = {}
    if render:
        try:
            from .render import render_stills
            from .scene import sun_study_stills
            sun = sun_study_stills(L.spec.site)
            stills = render_stills(S, str(out / "renders"), extra=[(n_, q_) for n_, q_, _ in sun])
            if sun:
                json.dump({n_: c_ for n_, _, c_ in sun}, open(out / "renders" / "sun.json", "w"), indent=1)
        except Exception as e:  # no browser / no three.js on this machine: the set still builds without stills
            stills = {}
            (out / "renders_error.txt").write_text(str(e))
    viewer_full = viewer_html(S, None, title=f"{L.spec.job} — 3D")
    (out / "viewer.html").write_text(viewer_full)
    steps = step_sheets(t, L)
    page = buildset_html(t, sheets, steps, stills, viewer_html(S, None, title=f"{L.spec.job} — 3D", standalone=False), f"{L.spec.job} — build set")
    (out / "buildset.html").write_text("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'></head><body>" + page + "</body></html>")
    (out / "scene.json").write_text(json.dumps(S.to_dict()))
    return dict(sheets=sheets, steps=steps, stills=stills, scene=S, viewer=str(out / "viewer.html"), buildset=str(out / "buildset.html"))
