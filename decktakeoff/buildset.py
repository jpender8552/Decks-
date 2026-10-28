"""The build set: drawing sheets (SVG), the 3D model, rendered stills, and the step-by-step build pages —
all from one Layout. Writes a folder; returns the pieces so the service and the artifact page can embed them."""
from __future__ import annotations

import base64
import html as _html
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .drawings import all_sheets, sheet, sheet_meta, T, R, LN, esc, INK, GOLD, MUTE, inch
from .drawings import (ledger_words, ledger_count, _ledgerlok_line, dtt_count, dtt_words, irx_surface, irx_posts, rail_extras, corner45, foot_block_bays, drink_between, drink_over,
                       drink_board, divider_words, decking_words, hardie_fastening, _stair_pairs)   # the makers' rules, worded once
from .layout import Layout, box_step_words
from .scene import build_scene, Scene, PHASES, box_step_free_ends
from .takeoff import Takeoff
from .catalog import parse_beam, RAIL_SYSTEMS, decking_facts, default_fastener_system
from .flags import tread_oc_max, FIG10_LINES
from .spec import covers_of, post_words, post_base_sku
from .units import ftin
from .viewer import viewer_html

STEP_VIEWS = {1: "step1", 2: "step2", 3: "step3", 4: "step4", 5: "step5", 6: "step6", 7: "step7", 8: "step8"}
# office checks — an order gap, a maker's written OK, a design over a maker's limit: the internal build set only, never a client or supplier page
OFFICE_CHECK = re.compile(r"(Order: |Get James Hardie |TimberTech's written OK |LedgerLOK at FastenMaster's spacing: |.+: tread supports @ \d+\" OC — over the )")
_NW = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}      # small counts in the crew text, in words


def step_sheets(t: Takeoff, L: Layout) -> List[dict]:
    """Build steps generalized from the takeoff: what goes in, how to build it, what to check — per phase."""
    if hasattr(L, "parts"):                 # two levels / a wrap: each phase once for the whole deck, every level named in it
        return composite_step_sheets(t, L)
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
             ("Pull the beam lines from the house wall: " + "; ".join(f"{bl.label} at {ftin(bl.y)} from the reference wall, posts at " + " / ".join(ftin(x) for x in bl.posts_x) for bl in L.beam_lines) + "." if L.beam_lines else "Lay out from the house wall.")
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
             ([f"{s.framing.post_size} posts on the bases; cut so the beam top lands at "
              + {frozenset({"drop"}): "the joist bottom (drop beams)", frozenset({"flush"}): "the joist top (flush beams)"}.get(
                  frozenset(b_.kind for b_ in s.framing.beams), "the joist bottom (drop beam) or the joist top (flush beam)")
              + ": " + " / ".join(f"{bl.label} posts {ftin(bl.post_len)}" for bl in L.beam_lines) + " — field-measure each.",
              "Plumb both ways, brace, then the caps go on with the beams."] if L.beam_lines else ["Plumb both ways and brace until the rims are on."])
             + ([f"Edge posts {L.edge_posts[0].label}-{L.edge_posts[-1].label}: one under each outline corner, top cut to the rim bottom ({ftin(L.edge_post_len)} nominal); "
                 "the rims land on them with (2) A35Z per rim — the rims span post to post as flush beams."] if getattr(L, "edge_posts", None) else [])
             + (["Seal every cut end before it goes up."] if timber and s.framing.end_grain_seal else [])),
        check=["Posts plumb to a string; tops on the beam line" if L.beam_lines else "Posts plumb; tops at the rim bottom, level to a string around the outline",
               "Every cut end sealed" if timber else "No post in ground contact without a standoff"]))
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
    if not L.beam_lines and s.framing.system != "steel":
        steps.pop()                        # no beam lines: the doubled rims on the edge posts are the beams — they go up with the frame
    if s.framing.system == "steel":
        steps[-1] = dict(n=4, code="T-403", title="Beams", still="step4",
            goes_in=items(lambda l: "boxed beams" in l.item or "side bracket" in l.item.lower()),
            how=[f"{bl.label}: {ftin(bl.length)} one piece, {bl.n_posts} posts @ {ftin(max((b - a) for a, b in zip(bl.posts_x, bl.posts_x[1:])) if bl.n_posts > 1 else bl.length)} max" for bl in L.beam_lines]
                + ["Box two C sections toe-to-toe, #12 self-drilling screws per the engineer's pattern; set flush with the joist tops; brackets to the stubs and cover posts."],
            check=["Beam top = joist top (flush)", "Brackets fully fastened; cut ends cold-galvanized"])
    fsys_ = s.decking.fastener_system or default_fastener_system(s.decking.collection, s.decking.profile)
    lat_ = [dtt_words(dtt_count(t), per=s.framing.lateral_ties) + ("; the engineer's detail governs." if s.extras.engineered else ".")] if dtt_count(t) else []
    fchk_ = _frame_order_checks(t, L)        # the counts the makers' spacing changes, against the order
    steps.append(dict(n=5, code="T-404", title="Frame", still="step5",
        goes_in=items(lambda l: l.category == "Lumber" and s.framing.joist_size in l.item and not is_beam(l), 6)
                + items(lambda l: l.category == "Lumber" and s.framing.joist_size not in l.item and "rail post" in (l.why or ""), 2)     # the IRX post blocking: cut with the frame
                + items(lambda l: l.category in ("Hardware", "Flashing & waterproofing") and any(k in l.item for k in ("hanger", "LedgerLOK", "H2.5", "Vycor", "flashing", "G-Tape", "membrane", "DTT1Z"))
                        or (l.category == "Hardware" and l.item.startswith("GRK RSS")), 20),
        how=[ledger_words(t, L) or "Ledger per the schedule."] + lat_
            + ([f"Doubled rims first: laminate the plies with GRK RSS 3-1/8\", 2 rows @ 12\" staggered, set them on the edge posts crown up and mitered at every corner, "
                f"(2) A35Z per rim at each post — the rims span post to post as flush beams. Then the joists hang between the ledger and the rims."]
               if (getattr(L, "edge_posts", None) and not L.beam_lines) else [])
            + ["; ".join(f"{z.name}: {len(z.frame.joist_x)} joists @ {z.frame.spacing:g}\" OC x {ftin(z.frame.joist_len)}" for z in L.zones) + ". Crown up, hangers at the ledger" + (", both faces of the flush beam" if any(b.kind == "flush" for b in L.beam_lines) else "") + ".",
             t.schedule.get("Blocking", "Blocking one row over the beam, staggered."), t.schedule.get("Joist tape", "Tape every joist top.")]
            + ([divider_words(L, fsys_) + " (TimberTech install guide p.7, p.10)."] if L.divider_x else [])
            + ([_post_blocking(t, L)] if irx_surface(L.rail) else []),
        check=(["Rims level all round at the joist top; every A35Z fully nailed"] if (getattr(L, "edge_posts", None) and not L.beam_lines) else [])
              + ["Frame square: diagonals within 1/8\"", "Every hanger fully nailed; ledger fasteners per the schedule", "Tape continuous; photos of the ledger, hangers and footings before decking"]
              + (["At least 1-1/2\" between grade and the bottom of every joist and rim (TimberTech); the skirt, a brick border or mulch never seals the underside"] if s.decking.brand == "TimberTech" else [])
              + fchk_))
    if s.framing.system == "steel":
        steps[-1] = dict(n=5, code="T-404", title="Frame", still="step5",
            goes_in=items(lambda l: l.category == "Lumber" and ("C-joist" in l.item or "track" in l.item or "ledger angle" in l.item))
                    + items(lambda l: l.category in ("Hardware", "Flashing & waterproofing") and any(k in l.item for k in ("clip angle", "self-drilling", "Structural screw", "tension tie", "Vycor", "flashing", "poly", "gravel")), 8),
            how=[t.schedule.get("Ledger", "Ledger per the schedule."),
                 "; ".join(f"{z.name}: {len(z.frame.joist_x) + len(z.frame.pf_x)} CEMCO {__import__('decktakeoff.steel', fromlist=['names']).names(s)['joist']} C-joists @ {z.frame.spacing:g}\" OC x {ftin(z.frame.joist_len)}" for z in L.zones)
                 + ". Joists seat on the ledger angle and clip to the ledger track and the boxed beams with clip angles, 4 #12 screws per leg.",
                 "Track caps every joist end at the rims; picture-frame joists doubled where the borders land"
                 + (f"; {divider_words(L, short=True)}." if L.divider_x else "."),
                 "Gravel over 6-mil poly under the frame before the decking (2\" min. clear at the walkway low end).",
                 t.schedule.get("Steel frame", "")],
            check=["Frame square: diagonals within 1/8\"", "Every clip fully screwed; ledger screws per the schedule", "Cut ends cold-galvanized; photos of the ledger, clips and footings before decking"])
    rough_, fix_ = _lighting_steps(t, L)      # low-voltage lights: the rough-in with the frame, the fixtures after the rail and the stairs
    if rough_:
        steps.append(rough_)
    hk_ = bool(s.extras.hardie_skirt)        # HardieTrim fascia goes on in its own step, after the stairs
    bare_ = "the bare track rim" if s.framing.system == "steel" else "the bare, taped rim"
    tt_ = decking_facts(s.decking.collection)["material"] == "Composite" and s.decking.brand == "TimberTech"
    steps.append(dict(n=6, code="T-405", title="Decking", still="step6",
        goes_in=items(lambda l: l.category in (("Decking", "Fasteners") if hk_ else ("Decking", "Fasteners", "Fascia")), 14),
        how=(decking_words(t, L) if tt_ else [t.schedule.get("Field", ""), t.schedule.get("Face screws", "Borders first, then the field.")])
            + [(L.plan.summary() if L.plan is not None else "Rows per zone: " + " · ".join(f"{z.name} {z.decking.rows}" for z in L.zones)) + ". Borders and breakers first, then the field rows from the outer edge toward the house."],
        check=[f"{ftin(s.deck_gap)} gaps held", "No cut end shows at the outer edge", "Color: every board from the same run"]
              + (["Every field-board end on a full 1-1/2\" of joist, with its own clip"] if (tt_ and fsys_ == "CONCEALoc") else [])
              + (["TimberTech's written OK for Cortex in Terrain+ in the file (877-275-2935) before the first Cortex screw — else TOPLoc, 5/32\" pilot"]
                 if (s.decking.collection == "Terrain+" and "Cortex" in (fsys_, s.decking.border_fastener or "")) else [])
              + (["TimberTech's written OK for Cap-Tor xd on the first and last field rows in the file — its CONCEALoc instructions name TOPLoc for Composite (5/32\" pilot); else TOPLoc"]
                 if (tt_ and fsys_ == "CONCEALoc") else [])))
    irx_ = _irx_rail(t, L) if irx_surface(L.rail) else None
    steps.append(dict(n=7, code="T-406", title="Rail", still="step7",
        goes_in=items(lambda l: l.category == "Rail", 10) + items(lambda l: l.category == "Hardware" and ("rail posts" in (l.why or "") or "HeadLOK" in l.item)),
        how=irx_[0] if irx_ else [t.schedule.get("Rail", "")] + (["Drink rail on TimberTech drink-rail brackets, mitered at every turn, plugs color-matched."] if s.railing.drink_rail else []),
        check=[f"Top of rail {L.rail.height:g}\" above the decking; posts plumb" if L.rail else "—",
               "Cables tensioned, no 4\" sphere passes" if RAIL_SYSTEMS.get(s.railing.system, {}).get("cable") else "Balusters under 4\" clear"] + (irx_[1] if irx_ else [])))
    # stairs and the box step (their own crew day), then the built-ins — the order lines that go in with each
    from .takeoff import inches_frac
    if s.stairs and L.stairs:
        how_, chk_, mxs_ = [], [], []
        cxt_ = tt_ and "Cortex" in (fsys_, s.decking.border_fastener or "")      # TimberTech composite treads on Cortex: the install guide's stair rules
        for ss_, sl_ in zip(s.stairs, L.stairs):
            nm_, g_ = getattr(ss_, "name", None) or "Stair", sl_.geo
            oc_, mx_ = _tread_supports(t, sl_, nm_), tread_oc_max(s, sl_)   # what carries the treads, as built; the tread line's max (the stair layout's own)
            mxs_.append((oc_, mx_))
            if getattr(sl_, "build", "") == "box":
                how_.append(f"{nm_}: {g_.risers} risers @ {inches_frac(g_.riser_in)} — a framed 2x6 box {ftin(sl_.width)} wide on a 4\" compacted 3/4\" base, "
                            + (f"screwed to {bare_} (RSS) before any HardieTrim goes on" if hk_ else "screwed to the rim (RSS), " + box_step_words(s, box_step_free_ends(s, L.stairs, sl_), treads=False))
                            + ((f", {sl_.cross_members} cross members" if getattr(sl_, "cross_members", 0) else ", cross members") + f" @ {inches_frac(oc_, 8)} OC" if oc_ else "")
                            + (", decked in the tread board" if tt_ else ", decked in the field board") + "; no stringers.")
            else:
                how_.append(f"{nm_}: {g_.risers} risers @ {inches_frac(g_.riser_in)}, {g_.treads} tread{'s' if g_.treads != 1 else ''} @ {inches_frac(g_.tread_in)} — "
                            f"{sl_.stringers} 2x12 stringers @ {oc_:.0f}\" OC on LSCZ connectors " + (f"to {bare_} before any HardieTrim goes on" if hk_ else "at the rim")
                            + (", fascia skirts both sides stepped under each tread" if (getattr(sl_, "skirts", False) and not hk_) else "") + ("" if hk_ else ", closed risers")
                            + f", treads {'Cortex' if 'Cortex' in (fsys_, s.decking.border_fastener or '') else 'Cap-Tor xd'} 2 per stringer per board.")    # Prime+: no Cortex (standards)
            if mx_ and oc_ and oc_ > mx_ + 0.25:
                chk_.append(f"{nm_}: tread supports @ {oc_:.0f}\" OC — over the {mx_:g}\" max for {s.decking.collection} treads: close them to {mx_:g}\""
                            + (" or add 2x6 blocking per CCRR-0128 Figure 10 for a 16\" span" if s.decking.collection in FIG10_LINES else ""))
        ok_ = [mx for oc, mx in mxs_ if mx and oc and oc <= mx + 0.25]
        if cxt_:      # the max goes in the crew's line only where every stair is framed to it (an over-limit layout: the office check)
            how_.append(f"Treads: square-shouldered {s.decking.collection} boards on Cortex — 7/32\" pilots, the setting tool in a drill, 2 per stringer or cross member per board, 3/4\" from edges and ends; "
                        "no CONCEALoc on stairs; the front edge flush with the riser face" + (f"; supports @ {min(ok_):g}\" OC max" if (ok_ and len(ok_) == len(mxs_)) else "") + ".")
        if hk_:
            how_.append("The HardieTrim risers and skirts go on in the HardieTrim step, after the stairs.")
        if any(getattr(ss_, "landing", "") == "grade" for ss_ in s.stairs):
            how_.append("Each stair lands on grade: 36\" of firm, level ground at the bottom, as wide as the stair (no pad in this scope).")
        steps.append(dict(n=8, code="T-407", title="Stairs" + ((" and the box steps" if sum(1 for sl_ in L.stairs if getattr(sl_, "build", "") == "box") > 1 else " and the box step")
                                                             if any(getattr(sl_, "build", "") == "box" for sl_ in L.stairs) else ""), still="yard",
            goes_in=items(lambda l: (l.category == "Lumber" and any(k in (l.why or "") for k in ("stair", "box step")))
                          or (l.category == "Stairs" and "door step" not in l.item.lower() and not (hk_ and _hardie_line(l)))   # HardieTrim risers and nails: the HardieTrim step
                          or (l.category == "Hardware" and ("stair" in l.item.lower() or "box step" in l.item.lower())), 14),
            how=how_,
            check=["Risers within 3/8\" of each other; treads level, " + ("front edges flush with the riser faces" if tt_ else "nosings straight"), "Landing at the bottom firm and level, 36\" deep",
                   "Plugs set flush" if hk_ else "Skirts and fascia tight; plugs set flush"] + chk_))
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
            how_.append("Door step: the framed 2x6 box on the deck at the door, decked, " + ("HardieTrim riser" if s.extras.hardie_skirt else "riser board") + " and returns.")
        steps.append(dict(n=9, code="T-408", title=("Door step" if not (s.geometry.benches or s.geometry.planters) else "Built-ins — " + ", ".join(w for w, on in (("benches", s.geometry.benches), ("planter" + ("s" if len(s.geometry.planters or []) > 1 else ""), s.geometry.planters),
                                                                                            ("door step", getattr(s.geometry, "door_step", None))) if on)), still="corner",
            goes_in=items(lambda l: l.category in ("Benches", "Planters") or "door step" in l.item.lower(), 14),
            how=how_,
            check=(["Bench seats level at the seat height, backs plumb, posts tight to the rim"] if s.geometry.benches else [])
                  + (["Planter liner lapped and drained before any soil"] if s.geometry.planters else [])
                  + (["Door step level, tight to the threshold, riser plumb"] if getattr(s.geometry, "door_step", None) else [])
                  + ["No screw head showing; plugs flush"]))
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
                + ([f"Ceiling: {s.extras.cover_soffit} panels 6\" OC stainless ring-shank at every rafter; " + (f"{s.extras.cover_fascia} fascia and rakes over the 2x8 sub-fascia, 2-1/2\" 16-ga 316SS ring-shank finish nails, 3 every 16\" (James Hardie TR1509 Table 2)." if s.extras.cover_fascia else "")] if s.extras.cover_soffit else ["1x6 T&G ceiling, blind-nailed."]),
            check=["Ledger flashed and counterflashed — hose test before the ceiling closes", "Posts plumb over blocking, beam level, rafters tied",
                   "Panels straight, seams engaged full length, no oil-canning; snow bar continuous" if ss else "Shingles straight, ridge cap sealed",
                   "Gutter falls to the outlets, downspouts discharge away from the footings" if s.extras.cover_gutters else "Water sheds clear of the deck edge"]))
    if fix_:                                  # the light fixtures: after the rail and the stairs, tested before the risers and fascia close
        steps.append(fix_)
    hs_ = _hardie_step(t, L)                  # HardieTrim fascia, risers and skirts: after the stairs (James Hardie TR1509)
    if hs_:
        steps.append(hs_)
    steps[-1]["check"] = steps[-1]["check"] + ["End of construction"]     # on whichever step is built last
    for i, st_ in enumerate(steps):          # numbered as built: the phase numbers skip (no stone bases, no cover)
        st_["n"], st_["code"] = i + 1, f"T-4{i:02d}"
    _shared_lines(steps, t)
    return steps


def _shared_lines(steps: List[dict], t: Takeoff) -> None:
    """An order line two steps both list names each step's own share, so a crew staging by step never counts it twice: the 3/8"
    lags (the DTT1Z ties at the frame, the IRX posts at the rail), the GRK RSS boxes (the frame, the box steps), the 2x6 sticks
    the rail post blocking is cut from with the frame (the rest: the box steps and the stair kicker)."""
    at: Dict[str, list] = {}
    for k, st in enumerate(steps):
        for j, g in enumerate(st["goes_in"]):
            at.setdefault(g, []).append((k, j))
    blk = sum(int(c.qty) for c in (getattr(t, "cut_list", None) or []) if c.member.lower().startswith("rail post"))
    for l in getattr(t, "lines", None) or []:
        g, why = f"({l.net:g}) {l.item}", l.why or ""
        where = at.get(g, [])
        if len(where) < 2:
            continue
        code = lambda k: steps[k]["code"]
        first = code(where[0][0])
        later = " / ".join(code(k) for k, _ in where[1:])
        n_dtt = sum(int(v) for v in re.findall(r"(\d+) DTT1Z x 1", why))
        n_post = sum(int(a) * int(b) for a, b in re.findall(r"(\d+) rail posts x (\d+)", why))
        n_need = sum(int(v) for v in re.findall(r"(\d+) needed", why))
        n_box = sum(int(v) for v in re.findall(r"box steps (\d+)", why))
        sep = "; " if " — " in l.item else " — "
        for (k, j) in where:
            ttl = steps[k]["title"]
            if "lag" in l.item.lower() and n_dtt and n_post:          # the DTT1Z ties' lags and the IRX posts'
                steps[k]["goes_in"][j] = (f"({n_dtt} of {l.net:g}) {l.item}{sep}the {n_dtt} for the DTT1Z ties here, the {n_post} for the rail posts at {later}" if ttl == "Frame" else
                                          f"({n_post} of {l.net:g}) {l.item}{sep}the {n_post} for the rail posts (the {n_dtt} for the DTT1Z ties went in with the frame, {first})")
            elif l.item.startswith("GRK RSS") and n_need and n_box:     # boxes: the screws each step drives
                steps[k]["goes_in"][j] = (f"{g}{sep}{n_need - n_box} of the {n_need} screws here, the box steps' {n_box} at {later}" if ttl == "Frame" else
                                          f"({n_box} screws) {l.item}{sep}the box steps' {n_box} of the {n_need}, from the boxes that came with the frame ({first})")
            elif l.category == "Lumber" and "rail post" in why and blk:   # the rail post blocking and the box steps out of the same sticks
                steps[k]["goes_in"][j] = (f"{g}{sep}cut the {blk} rail post blocks from these now; the rest at {later}" if ttl == "Frame" else
                                          f"{g}{sep}the same sticks, less the {blk} rail post blocks cut with the frame ({first})")


def _frame_order_checks(t: Takeoff, L) -> List[str]:
    """Frame-step checks where the makers' rules change a count the order made: LedgerLOK at FastenMaster's Table 1 spacing and
    3-3/4" end distance on every ledger piece, where that is more than the order's 12"-OC count, and the 3/8" lag each DTT1Z takes
    into the house framing (IRC R507.9.2(2)) — each only while the order lacks it."""
    lines = getattr(t, "lines", None) or []
    out = []
    lc, l_ = ledger_count(t, L), _ledgerlok_line(t)
    if lc and l_ is not None:
        m_ = re.search(r"(\d+) ct", l_.item)
        ct = int(m_.group(1)) if m_ else 50
        cap = int(l_.order) * ct
        out.append(f"LedgerLOK at FastenMaster's spacing: {lc[0]} on the {lc[2]} ledger piece{'s' if lc[2] > 1 else ''} (3-3/4\" from each end{' of each' if lc[2] > 1 else ''}) — the order counts {lc[1]} at 12\" OC; "
                   + (f"the {int(l_.order)} x {ct}-ct box{'es' if l_.order > 1 else ''} on the order cover{'' if l_.order > 1 else 's'} it" if lc[0] <= cap
                      else f"order {int(math.ceil(lc[0] / ct))} boxes"))
    n_dtt = dtt_count(t)
    if n_dtt and not L.spec.extras.engineered and not any("lag" in l.item.lower() and ("DTT" in l.item or "lateral" in (l.why or "").lower()) for l in lines):
        out.append(f"Order: ({n_dtt}) 3/8\" lag screws for the DTT1Z ties, long enough for 3\" into the house framing — not on the order")
    return out


def _tread_supports(t: Takeoff, sl, nm: str = "") -> Optional[float]:
    """Center-to-center spacing of what carries a stair's treads: its stringers, or a box step's cross members — the stair layout's
    own count (cross_members), else the order's cut list ("N cross members" on the frame line, or "N per tread" on its own line)."""
    if getattr(sl, "build", "") != "box":
        return sl.width / max(1, sl.stringers - 1)
    n = getattr(sl, "cross_members", 0)
    for c in ([] if n else (getattr(t, "cut_list", None) or [])):
        m = (re.search(r"(\d+) (?:cross members|per tread)", c.note or "")
             if (c.member.startswith("Box step") and any(f"({k})" in c.member for k in (nm, sl.side) if k)) else None)
        if m:
            n = int(m.group(1))
            break
    return (sl.width - 1.5) / (n - 1) if n > 1 else None


def _hardie_line(l) -> bool:
    """An order line the HardieTrim step puts on: the fascia and riser boards, their nails or screws, the touch-up kit."""
    return l.category == "Fascia" or (l.category == "Stairs" and any(k in l.item for k in ("HardieTrim", "finish nail", "ColorPlus")))


def _post_blocking(t: Takeoff, L) -> str:
    """The frame step's IRX post blocking (TimberTech IRX install guide Dia. #3A/#3B: a 2x6 blocking under each post and a 2x6 cross
    block): the order's own cut-list lines for it when it has them, else the detail's words."""
    n = irx_posts(L)[0]
    cs = [c for c in (getattr(t, "cut_list", None) or []) if c.member.lower().startswith("rail post")]
    bev = ", beveled to fit on the 45-degree rims" if corner45(L.rail) else ""
    if cs:
        return ("Rail post blocking (IRX): " + "; ".join(f"{c.qty} {c.nominal} {c.member.split(' (')[0].lower().replace('rail post ', '')} x {ftin(c.length_in)}"
                                                       + (f" — {c.note}" if c.note else "") for c in cs) + bev + " — set now, so all four post lags land in solid 2x.")
    return (f"Rail post blocking (IRX): at each of the {n} posts a 2x6 blocking under the post and a 2x6 cross block between the joists at its back (TimberTech IRX install guide "
            f"Dia. #3A/#3B){bev}, (3) RSS each end — set now, so all four post lags land in solid 2x.")


def _irx_rail(t: Takeoff, L, sch: Optional[str] = None) -> Tuple[List[str], List[str]]:
    """An IRX Baluster rail's how + check lines: TimberTech's IRX install guide (lags into solid blocking, shims, the 5/8" wire hole,
    45-degree corners at 22.5 degrees, foot blocks, caps last) and the IRX drink-rail guide (01-31-20) for a drink rail between the posts
    or over them (posts cut level, wood inserts, seams on post centers, no caps).
    sch = the rail schedule line (a composite deck's merged one): its louvered-roof / shade-sail post notes are kept."""
    s, rl = L.spec, L.rail
    lines = getattr(t, "lines", None) or []
    plan = getattr(t, "lighting", None)
    lights = any(l.category == "Lighting" for l in lines)
    (n, kinds), n45, nfb, drink, over = irx_posts(L), corner45(rl), foot_block_bays(rl), drink_between(s), drink_over(s)
    ex_ = rail_extras((getattr(t, "schedule", None) or {}).get("Rail", "") if sch is None else sch)
    how = [f"{n} posts ({kinds}) surface-mounted over the blocking set with the frame: shims under the base to plumb, 3/16\" pilots "
           "through the decking, (4) 3/8\" x 6\" HDG lag screws with washers per post (IRX install guide)"
           + ("; drill the 5/8\" wire hole at each post center and pull the post's wire loop up through it before the post is fastened" if lights else "") + "."]
    if ex_:
        how.append(ex_.lstrip("; ")[:1].upper() + ex_.lstrip("; ")[1:] + ".")
    if n45:
        how.append(f"The {n45} corner posts on 45-degree turns: each set at 22.5 degrees on the corner bisector with a 22.5-degree bracket pack (AZTIXBKT22KIT); fit them before cutting any panel.")
    how.append(f"Panels cut to the bays" + (f"; a foot block under the middle of each of the {nfb} bays over 4' (two deck screws, one #8 x 3/4\" self-drilling screw from the outside) "
                                           f"before the {'panel cover' if (drink or over) else 'top rail'} goes on" if nfb else "") + ".")
    clips = ("clips 4 per 6' panel, 6 per 8', the first within the first baluster at each end, 18\" max apart, 2 #8 x 3/4\" self-drilling screws each up into the rail; ")
    klath = "#8 x 3/4\" SS K-Lath screws up through the clips into 1/8\" x 3/4\" deep pilots in the board's underside"
    if drink:
        how.append("Drink rail between the posts (IRX drink-rail guide 01-31-20): a universal panel cover on each panel in place of the top rail; " + clips
                   + f"the {drink_board(s)} board cut to fit between the posts with its corners trimmed — not mitered — centered on the cover, embossed face up; "
                   + klath + " — no face screws, no plugs.")
    elif over:
        how.append("Drink rail over the posts (IRX drink-rail guide 01-31-20): every post cut level, its top within 1/4\" of the panel covers; a universal panel cover on each panel in place "
                   "of the top rail; " + clips + "a wood insert cut to fit inside each post; "
                   f"the {drink_board(s)} board mitered at the corner posts, seams on post centers (boards up to 16'), every joint tight — (3) 2-1/2\" Cortex or TOPLoc screws each side "
                   "of a seam into the insert, 3/4\" from the edges and ends, pre-drilled; " + klath + ".")
    caps = lights and getattr(plan, "post_kind", "cap") == "cap" and getattr(plan, "n_cap", 0)
    if not over:                             # over the posts there are no caps: the board covers the post tops
        how.append("Caps last, after the panels" + (" and the drink rail" if drink else "") + (" — the post-cap lights go on with them (Light fixtures step)" if caps else "") + ".")
    check = ["Every post on (4) lags into solid blocking, shimmed plumb"] + (["Corner posts on the bisector, on the 22.5-degree brackets"] if n45 else []) \
        + (["Drink rail level and centered, no face screws; a cap on every post"] if drink else
           ["Post tops level, within 1/4\" of the panel covers; seams on post centers, tight; miters closed"] if over else [])
    post_lag = lambda l: ("lag" in l.item.lower() and "3/8" in l.item and "6\"" in l.item
                          and any(k in f"{l.item} {l.why or ''}".lower() for k in ("rail", "post", "irx")))      # the rail posts' own lags, not the DTT1Z's
    if not any(post_lag(l) for l in lines):
        check.append(f"Order: ({4 * n}) 3/8\" x 6\" HDG lag screws + washers for the posts — not on the order" + (" (it lists HeadLOK 6\")" if any("HeadLOK" in l.item for l in lines) else ""))
    if n45 and not any("BKT22" in l.item.upper() for l in lines):
        check.append(f"Order: ({n45}) AZTIXBKT22KIT 22.5-degree bracket packs — not on the order")
    return how, check


def _lighting_steps(t: Takeoff, L) -> Tuple[Optional[dict], Optional[dict]]:
    """The lights in two steps when the order has Lighting lines (lighting.py's plan): the rough-in with the frame — TimberTech: the
    wiring goes in before the posts are secured — and the fixtures after the rail and the stairs, tested before the risers and
    fascia close it in. Two runs from the transformer when the plan's one run drops more than lighting.V_DROP_NOTE at its end."""
    lt = [l for l in t.lines if l.category == "Lighting"]
    if not lt:
        return None, None
    from .lighting import V_DROP_NOTE, product, post_label, post_where
    s = L.spec
    hk = bool(s.extras.hardie_skirt)
    plan = getattr(t, "lighting", None)
    cfg = getattr(plan, "cfg", None) or {}
    runs = list(getattr(plan, "runs", []) or [])
    tr = list(getattr(plan, "transformers", []) or [])
    split = len(runs) == 1 and runs[0].drop_v > V_DROP_NOTE
    frm = "from the transformer" + ("s" if len(tr) > 1 else "")
    nr = 2 if split else max(1, len(runs))
    nrw = f"{_NW.get(nr, nr)} run{'s' if nr > 1 else ''}"         # the runs in words, however the plan splits them
    runs_txt = f"{nrw} {frm}" + (f" (one run would drop about {runs[0].drop_v:.1f} V at its far end)" if split else "")
    n_riser, n_cap = getattr(plan, "n_riser", 0), getattr(plan, "n_cap", 0)
    wire = lambda l: any(k in l.item.lower() for k in ("cable", "staple"))
    rough = dict(n=0, code="T-4xx", title="Lighting rough-in", still="step5",     # the frame still: on every page, at any height — with its own caption
        cap="Step 5 · Lighting rough-in — the 12/2 runs stapled under the frame, before the decking",
        goes_in=[f"({l.net:g}) {l.item}" for l in lt if wire(l)][:4],
        how=[f"With the frame, before any decking or fascia: the 12/2 low-voltage cable (~{getattr(plan, 'wire_lf', 0):,} LF on the order) as {runs_txt}, stapled under the frame with the "
             f"insulated staples every 18\", clear of the joist tops and every screw line; a loop left on the house wall above the outdoor GFCI outlet for the transformer{'s' if len(tr) > 1 else ''}."]
            + ([f"A wire loop at each of the {n_cap} rail post locations, up beside the post blocking, for the 5/8\" hole at the post center — TimberTech: the wiring goes in before "
                "the posts are secured."] if n_cap else [])
            + ([f"Into each lit stair under the rim's bottom edge — never through the fascia{' or the HardieTrim' if hk else ''} — and along the stringers or the box frame to each of the "
                f"{n_riser} riser-light spots."] if n_riser else []),
        check=["Cable stapled clear of every joist top and screw line", "A loop at every post location and in every lit stair before the decking goes on", "Photos of the runs before decking"])
    how = []
    if n_cap:
        how.append(f"{post_label(plan, n_cap)} {post_where(plan)}: " + ("a 3/8\" wire hole behind each light, the lead down inside the post to the run under the deck, two #8 x 3/4\" screws."
                   if getattr(plan, "post_kind", "cap") == "accent" else "the lead down inside the post to its loop, spliced in a silicone-filled wire nut; the light takes the post's cap."))
    if n_riser:
        how.append(f"{n_riser} riser lights: " + ("cut each HardieTrim riser for its housing before it goes up — a fiber-cement blade in the jig saw, outdoors — and seal the cut with the ColorPlus "
                   "edge coater; 2x backing on the stair framing behind each housing; the lead behind the riser to its loop." if hk else
                   "cut each riser board for the housing before it goes on; the lead behind the riser to the run."))
    how.append(f"{len(tr) or 1} transformer{'s' if len(tr) > 1 else ''}" + (f" ({', '.join(tr)})" if tr else "") + " on the house wall above the outdoor GFCI outlet, the photocell clear of "
               f"every house light (the coach lantern, a porch light); timer set {cfg.get('timer', 'dusk + 6 h')}.")
    if tr and plan is not None:
        mx = sum(float(product(cfg, k).get("watts_max") or product(cfg, k).get("watts", 0)) for k in tr)
        nom = " + ".join(f"{float(product(cfg, k).get('watts', 0)):g} W" for k in tr)
        how.append(f"Load {plan.load_w:.0f} W against {mx:g} W, the TimberTech maximum on the {nom} transformer{'s' if len(tr) > 1 else ''} (not the nameplate); "
                   + f"{nrw} {frm}, none over {float(cfg.get('run_max_w', 60)):g} W.")
    how.append("Splices in silicone-filled wire nuts; test every light — about 11 V or more at the far end of each run — before the "
               + ("HardieTrim risers and fascia close the stairs and the rim." if hk else "risers, skirts and fascia close it in."))
    fix = dict(n=0, code="T-4xx", title="Light fixtures", still="yard", goes_in=[f"({l.net:g}) {l.item}" for l in lt if not wire(l)][:8], how=how,
               check=["Every light on at dusk and off on the timer", "About 11 V or more at the far end of each run; no open splice", "Transformer on a GFCI outlet with an in-use cover"])
    return rough, fix


def _hardie_step(t: Takeoff, L) -> Optional[dict]:
    """HardieTrim fascia, risers and skirts as their own step after the stairs, per James Hardie TR1509 (09/25) and its best-practice
    guide: the frame's connections go on the bare rim first, then the trim — ripped for its clearances, fastened (finish nails into
    a wood frame, screws or ET&F pins into steel — TR1509 p.3), sealed, touched up. A composite deck's stairs come from its parts."""
    s = L.spec
    if not s.extras.hardie_skirt:
        return None
    lines = getattr(t, "lines", None) or []
    lit = any(l.category == "Lighting" and "riser" in l.item.lower() for l in lines)
    steel = s.framing.system == "steel"                # a steel track rim: screws into the furring, no joist tape behind the miters
    bare_ = "the bare track rim" if steel else "the bare, taped rim"
    sts = [(ss, sl) for ss, sl in _stair_pairs(L) if not getattr(ss, "option", "")]
    box = [sl for _, sl in sts if getattr(sl, "build", "") == "box"]
    strg = [sl for _, sl in sts if getattr(sl, "build", "") != "box"]
    skirt = [getattr(ss, "name", None) or "the stair" for ss, sl in sts if getattr(sl, "skirts", False) and getattr(sl, "build", "") != "box"]
    Es = [getattr(p.layout, "outline_edges", None) or [] for p in L.parts] if hasattr(L, "parts") else [getattr(L, "outline_edges", None) or []]
    turns = [min(d, 360 - d) for E in Es for a, b in zip(E, E[1:] + E[:1]) if a.exposed and b.exposed
             for d in [abs(math.degrees(math.atan2(b.y1 - b.y0, b.x1 - b.x0) - math.atan2(a.y1 - a.y0, a.x1 - a.x0))) % 360]]
    cut = (["22.5-degree miters at the 45-degree turns"] if any(30 < d < 60 for d in turns) else []) + (["45-degree miters at the square corners"] if (not any(Es) or any(75 < d < 105 for d in turns)) else [])
    frame = " and ".join(w for w, on in (("the stair stringers (LSCZ)", strg), ("the box-step frames (RSS)", box)) if on)
    oe_ = {e.name: e for e in (getattr(L, "outline_edges", None) or []) if e.exposed}     # an outline side a box step takes whole: its riser is the face (no fascia)
    full_ = []
    for nm_, gs_ in sorted((getattr(L, "fascia_gaps", None) or {}).items()):
        cur_, cov_ = 0.0, 0.0
        for a_, b_ in sorted(gs_):
            cov_ += max(0.0, b_ - max(a_, cur_)); cur_ = max(cur_, b_)
        if nm_ in oe_ and cov_ >= math.hypot(oe_[nm_].x1 - oe_[nm_].x0, oe_[nm_].y1 - oe_[nm_].y0) - 1.0:
            full_.append(nm_.split(":")[-1])
    fas_ = "the fascia on every rim side" + (f" but side{'s' if len(full_) > 1 else ''} {' and '.join(full_)} (the box step{'s' if len(full_) > 1 else ''}' riser{'s are' if len(full_) > 1 else ' is'} the face there)" if full_ else "")
    free_ = [box_step_free_ends(s, [sl_ for _, sl_ in _stair_pairs(L)], sl) for sl in box]
    ends_ = "ends" if all(f_ == 2 for f_ in free_) else "free ends (none at a mitered corner)"
    what = "; ".join(w for w in (fas_, "every stair riser" if sts else "", f"the stepped skirts both sides of the {', '.join(skirt)}" if skirt else "",
                                 f"the box-step fronts and {ends_}" if box else "") if w)
    ed = "3/4\"" if steel else "1/2\""                # TR1509 p.3: finish nails 1/2" from the edges, every other fastener 3/4"; 1" from the ends
    check = ["HardieTrim gaps open: " + ("1/4\" over treads/brick" if sts else "1/4\" over brick/pavers") + ", 2\" over soil/mulch",
             f"{'Screws' if steel else 'Nails'} {ed} from the edges and 1\" from the ends, snug, no laminate left; every cut edge sealed",
             f"Get James Hardie Technical Services' written OK for HardieTrim as deck fascia{' and stair risers' if sts else ''} (not a listed use) before ordering — 800-942-7343"]
    nails = [l for l in lines if "finish nail" in l.item.lower()]
    if not steel and not nails:              # a steel frame keeps the order's trim screws (TR1509: no finish nails into steel)
        check.append("Order: 2-1/2\" 16-ga 316SS ring-shank finish nails for the HardieTrim — not on the order" + (" (it lists trim screws)" if any("trim screw" in l.item.lower() for l in lines) else ""))
    elif not steel and not any("ring" in l.item.lower() for l in nails):
        check.append("Order: ring-shank 316SS finish nails for the HardieTrim (TR1509 p.3: stainless nails ring shank, not smooth) — the order's finish nails don't say ring shank")
    return dict(n=0, code="T-4xx", title="HardieTrim fascia, risers and skirts" if sts else "HardieTrim fascia", still="corner",
        goes_in=[f"({l.net:g}) {l.item}" for l in lines if _hardie_line(l)][:8],
        how=[(f"Order of work: {frame} are already on {bare_}" if frame else f"Order of work: every frame connection is made on {bare_} first")
             + f" — nothing structural goes through the HardieTrim. Then {what}.",
             "Rip each piece for its side's clearance: 2\" min above soil or mulch, 1/4\" min above " + ("brick, pavers and treads" if sts else "brick or pavers") + " — the gap stays open, never caulked.",
             f"{'Fasten' if steel else 'Nail'} with {hardie_fastening(s)}: 4 per 16\" on the fascia" + (", 2 every 16\" on the stair skirts" if skirt else "")
             + (", 2 per stringer on the stair risers" if strg else "") + (f", 2 every 16\" on the box-step fronts and {ends_.split(' (')[0]}" if box else "")
             + f", {ed} from the edges and 1\" from the ends, driven snug through the laminate (James Hardie TR1509" + (" p.3: no finish nails into steel" if steel else "") + ").",
             "Corners: " + (" and ".join(cut) + " (each miter half its corner's turn)" if cut else "each miter half its corner's turn")
             + "; edge-seal every cut with the ColorPlus edge coater before the piece goes up" + ("." if steel else "; a G-Tape patch on the rim behind each miter."),
             *(["Risers: factory edge down, 1/4\" open above each tread" + (", the riser lights already in their cut-outs" if lit else "") + "."] if sts else []),
             "Touch-up: the Hardie ColorPlus touch-up kit only, dime-size spots at most (anything bigger: a new piece), above 40F; no caulk or paint on the face.",
             "Peel the laminate right after " + ("fastening" if steel else "nailing") + " each piece. Cut outdoors with a Hardie blade on a saw with a vacuum; no dry sweeping."],
        check=check)


def composite_captions(L) -> Dict[int, str]:
    """scene.step_captions for a composite deck (two levels, a wrap): the 3D viewer's phase captions for the whole deck —
    footings and posts per level, the beam lines by level, both frames and the rise between them, the decking as fastened,
    the rail and the step guard, the louvered roof / lights in the finished deck."""
    from .drawings import _comp_levels, _step_faces, _post_base_name, _lv_word
    s = L.spec
    fr = s.framing
    levels = _comp_levels(L)
    faces = _step_faces(levels)
    per = lambda f: " · ".join(f"{_lv_word(lv)} {f(lv)}" for lv in levels)
    n_lv = lambda lv: sum(len(b.posts) for b in lv.beams) + len(lv.eps)
    ft = {"diamond_pier": f"Diamond Pier {L.frame.footing_model} footings", "caisson": f"{int(L.frame.footing_dia_in)}\" x {ftin(L.frame.footing_depth_in)} drilled caissons",
          "concrete": "concrete piers", "existing": "existing caissons"}.get(fr.footing_type, "footings")
    bls = [b for lv in levels for b in lv.beams]
    fs = (s.decking.fastener_system or "").lower()
    fast = "Cortex face screws + color-matched plugs" if fs.startswith("cortex") else ("face screws" if ("cap-tor" in fs or "screw" in fs) else "hidden fasteners")
    rise = (faces[0][1].h_in - faces[0][0].h_in) if faces else 0.0
    live = [ss for p in L.parts for ss in (p.spec.stairs or []) if not getattr(ss, "option", "")]
    roof = __import__("decktakeoff.louvered", fromlist=["has_roofs"]).has_roofs(s)
    lights = __import__("decktakeoff.lighting", fromlist=["lights_of"]).lights_of(s) is not None
    rl = L.rail
    return {1: f"Step 1 · Footings — {sum(n_lv(lv) for lv in levels)} {ft}: {per(n_lv)}",
            2: f"Step 2 · Posts — {fr.post_size} {post_words(s)} columns on {_post_base_name(s, L.parts[0].takeoff)} bases: {per(lambda lv: sum(len(b.posts) for b in lv.beams))}",
            3: "Step 3 · Stone column bases — 2'x2' x 3' ledgestone with 24\" caps" if s.extras.stone_bases else "Step 3 · (no stone bases)",
            4: (f"Step 4 · Beams — {len(bls)} {' / '.join(sorted({b.size + ' ' + b.species for b in bls}))} {' / '.join(sorted({b.kind for b in bls}))} beam lines: "
                + "; ".join(f"{_lv_word(lv)} " + ", ".join(b.short for b in lv.beams) for lv in levels if lv.beams)) if bls else "Step 4 · (no beams)",
            5: f"Step 5 · Frame — {fr.joist_size} joists at {L.frame.spacing:g}\" OC on both levels, rims, ledgers"
               + (f"; the {_lv_word(faces[0][1])} level {inch(rise)} above the {_lv_word(faces[0][0])}" if faces else "")
               + ("; the stair notch framed" if any(getattr(ss, "inset", False) for ss in live) else ""),
            6: f"Step 6 · Decking — {s.decking.brand} {s.decking.collection} {s.decking.color}, picture frame + breakers, {fast}"
               + ("; the stair and the step skirt" if (faces and live) else "; the step skirt" if faces else "; the stairs" if live else ""),
            7: ((f"Step 7 · Rail — {rl.system} {rl.height:g}\" {rl.color}" + ((", drink rail on top" if (s.railing.drink_rail_mount or "between") == "over" else ", drink rail between the posts") if s.railing.drink_rail else "")
                 + ("; the step between the levels guarded except at the stair" if faces else "")) if rl else "Step 7 · (no rail)"),
            8: "Step 8 · Your deck" + (" — the louvered roof" if roof else "") + (" and the lights" if (roof and lights) else " — the lights" if lights else "")}


def composite_step_sheets(t: Takeoff, L) -> List[dict]:
    """Build steps for a composite deck (two levels, a wrap): every phase once for the whole deck, each level's beam lines,
    posts and ledger named and placed in the deck's frame (x from its left end, y out from the main rear wall — the frame of
    the S-100 schedule), the level change, every part's stairs and the step skirt, the lights when the job has them."""
    import re as _re
    from .drawings import _comp_levels, _step_faces, _merged_schedule, _post_base_name
    from .takeoff import inches_frac
    s = L.spec
    timber = s.is_timber
    lines = t.lines
    def items(pred, n=7):
        return [f"({l.net:g}) {l.item}" for l in lines if pred(l)][:n]
    levels = _comp_levels(L)
    faces = _step_faces(levels)
    ms = _merged_schedule(t, levels)
    fr = L.frame
    ft = s.framing.footing_type
    n_posts = L.n_footings
    lw = lambda lv: lv.name.lower()
    hi, lo = max(levels, key=lambda q: q.top), min(levels, key=lambda q: q.top)
    rise = hi.h_in - lo.h_in
    per = " + ".join(f"{sum(len(b.posts) for b in lv.beams) + len(lv.eps)} {lw(lv)}" for lv in levels)
    steps = []
    # 1 footings
    to_posts = lambda l: (not l.item.startswith("Diamond Pier") and ("post base" in l.item.lower() or "post screws" in l.item.lower() or "fastener set" in l.item.lower() or ("anchor" in l.item.lower() and "cast-in" not in l.item.lower()) or "to the edge posts" in l.item))   # the bases and their fasteners go in with the posts
    from .drawings import _post_rows, _slab_posts, _id_run
    sl_ids, sl_name = _slab_posts(s, _post_rows(levels, []))           # footings in a slab: saw-cut openings (S-100's IDs)
    lay = "; ".join(f"{lv.name} {bm.short} {ftin(bm.a[1] * 12)} out, posts at x " + " / ".join(ftin(p.x * 12) for p in bm.posts) for lv in levels for bm in lv.beams)
    steps.append(dict(n=1, code="T-400", title="Footings", still="step1",
        goes_in=items(lambda l: l.category == "Footings" and "Stone" not in l.item and not to_posts(l)),
        how=["Call 811 and locate before any " + ("hole or pin." if ft == "diamond_pier" else "digging.") + (" Strip the existing deck first." if s.extras.demo_existing else ""),
             "Lay out in the deck's frame — x from its left end, y out from the main rear wall (the S-100 schedule): " + lay + ".",
             {"caisson": f"Auger {n_posts} holes ({per}) {int(fr.footing_dia_in)}\" x {ftin(fr.footing_depth_in)} (frost {ftin(s.site.frost_depth_in)}), tube to 6\" above grade, cage in, pour, set the 5/8\" anchors wet. Cure 2 days.",
              "diamond_pier": f"Set {n_posts} Diamond Pier heads ({per}) level at grade on undisturbed soil and drive the 4 pins in each; caps on.",
              "concrete": f"Dig and form {n_posts} piers ({per}) {int(fr.footing_dia_in)}\" x {ftin(fr.footing_depth_in)}, pour, set the standoff bases wet.",
              "existing": f"The {n_posts} existing caissons stay ({per}); the engineer confirms each before the new beams land on them."}[ft]]
            + ([f"{_id_run(sl_ids)} stand in the {sl_name.lower()}: saw-cut and lift out the slab at each " + ("before drilling." if ft == "caisson" else "first.")]
               if sl_ids and ft != "existing" else []),
        check=["Footings on the layout within 1/2\"; bearing on undisturbed soil" if ft != "existing" else "Every existing caisson sound, level and on the beam line",
               "Frost depth met" if ft not in ("diamond_pier", "existing") else ("Pins fully driven, heads level" if ft == "diamond_pier" else "Epoxy cured before load"),
               "Photos before backfill"]))
    # 2 posts
    kinds = {b.kind for lv in levels for b in lv.beams}
    seat = {frozenset({"drop"}): "the joist bottom (drop beams)", frozenset({"flush"}): "the joist top (flush beams)"}.get(frozenset(kinds), "the joist bottom (drop beam) or the joist top (flush beam)")
    plen = " · ".join(f"{lw(lv)} " + ", ".join(b.short for b in lv.beams) + " " + " / ".join(sorted({ftin(b.post_len) for b in lv.beams})) for lv in levels if lv.beams)
    steps.append(dict(n=2, code="T-401", title="Posts", still="step2",
        goes_in=items(lambda l: l.category == "Lumber" and s.framing.post_size in l.item)
                + items(to_posts),
        how=[f"{s.framing.post_size} {post_words(s)} posts on the {_post_base_name(s, t)} bases, cut so the beam top lands at {seat}: {plen} — field-measure each"
             + (f"; the {lw(hi)}'s posts stand {inch(rise)} taller than the {lw(lo)}'s." if faces else "."),
             "Plumb both ways, brace, then the caps go on with the beams."]
            + ([f"Knee braces: 4x4 at 45°, {ftin(s.framing.knee_leg_in)} legs, both directions at every post; 1/2\" through-bolt each end."] if s.framing.knee_braces else [])
            + (["Seal every cut end before it goes up."] if timber and s.framing.end_grain_seal else []),
        check=["Posts plumb to a string; tops on each level's beam line", "Every cut end sealed" if timber else "No post in ground contact without a standoff"]))
    if s.extras.stone_bases:
        steps.append(dict(n=3, code="T-402", title="Stone column bases", still="step3", goes_in=items(lambda l: "Stone" in l.item),
            how=["Mason after the posts and before the beams or after the frame — owner's call on access. Cement board wrap, lath, scratch, ledgestone, 24\" cap.", "Keep the cap 1/2\" clear of the post; caulk the joint."],
            check=["Stone plumb and square to the deck; caps level", "Sample color approved by the homeowner"]))
    # 4 beams
    is_beam = lambda l: l.category == "Lumber" and (("beam" in (l.why or "").lower() and "stringer" not in (l.why or "").lower())
                                                    or bool(_re.match(r"^(6x(8|10|12|14)|4x12)x", l.item)) or ("4x10x" in l.item and not timber))
    caps = sorted({b.bl.cap_mid for lv in levels for b in lv.beams if b.bl.cap_mid})
    sizes = [_re.match(r"\((\d)\)(\dx)", b.size) for lv in levels for b in lv.beams]
    two_by = any(m and m.group(2) == "2x" for m in sizes)
    two_ply4 = any(m and m.group(1) == "2" and m.group(2) == "4x" for m in sizes)
    if any(lv.beams for lv in levels):
        bhow = [f"{lv.name} {bm.short}: {bm.size} {ftin(bm.length)} " + (f"in {len(bm.pieces)} pieces spliced over posts" if len(bm.pieces) > 1 else "one piece")
                + f", {len(bm.posts)} posts @ {ftin(max((q.x - p.x) for p, q in zip(bm.posts, bm.posts[1:])) * 12) if len(bm.posts) > 1 else ftin(bm.length)} max"
                for lv in levels for bm in lv.beams]
        steps.append(dict(n=4, code="T-403", title="Beams", still="step4",
            goes_in=items(is_beam) + items(lambda l: "cap" in l.item.lower() and l.category == "Hardware") + items(lambda l: l.item.startswith("Simpson SD10212")),
            how=bhow + ["Crown up, strung straight, caps screwed off with the " + ("SDS screws in the box." if any(c.startswith("CCQ") for c in caps) else "SD screws (SD10212).")]
                + (["Built-up beam: laminate the plies with GRK RSS 3-1/8\", 2 rows 2\" from top and bottom, staggered @ 12\" OC, before it goes up."] if two_by else [])
                + (["Two-ply beam: through-bolt the plies with 1/2\" HDG bolts, 2 rows 2\" from top and bottom, staggered @ 24\" OC, a pair 6\" from each end."] if two_ply4 else []),
            check=[{frozenset({"drop"}): "Beam top = joist bottom (drop beams), crown up", frozenset({"flush"}): "Beam top = joist top (flush beams), crown up"}.get(
                       frozenset(kinds), "Beam top = joist bottom (drop) / joist top (flush)"), "Splices land on a post; caps fully fastened"]))
    # 5 frame, both levels and the level change
    js = s.framing.joist_size
    ztxt = "; ".join(f"{z.name}: {len(z.z.frame.joist_x)} joists @ {z.z.frame.spacing:g}\" OC x {ftin(z.z.frame.joist_len)}" for lv in levels for z in lv.zones)
    stairs = [(p, ss, sl) for p in L.parts for ss, sl in zip(p.spec.stairs or [], p.layout.stairs or []) if not getattr(ss, "option", "")]
    low1 = lambda w: (w[0].lower() + w[1:]) if w.lower().startswith(("stair", "box step")) else w
    notch = [f"the notch for the {low1(ss.name or 'stair')} in the {p.name.lower()}" for p, ss, sl in stairs if getattr(ss, "inset", False) or str(sl.side).startswith("edge:")]
    fhow = [f"Ledgers: {ledger_words(t, L, ms.get('Ledger', 'per the schedule'))}."]
    fhow += [dtt_words(dtt_count(t), per=s.framing.lateral_ties) + ("; the engineer's detail governs." if s.extras.engineered else ".")] if dtt_count(t) else []
    fhow += [f"{ztxt}. Crown up, hangers at the ledger" + (", both faces of the flush beam" if "flush" in kinds else "") + "."]
    if faces:
        fhow.append(f"The {lw(hi)} frames {inch(rise)} above the {lw(lo)}: build the {lw(lo)} first, then the {lw(hi)}; the two rims stand side by side at the step, "
                    f"each level on its own posts — nothing of the {lw(hi)} bears on the {lw(lo)}." + (f" Frame {notch[0]} with doubled trimmers and a doubled header, joists into the header in hangers." if notch else ""))
    fhow += [v for v in (ms.get("Blocking", "Blocking one row over the beam, staggered."), ms.get("Joist tape", "Tape every joist top.")) if v and not _re.search(r"(^|\s|: )0 x ", v)]
    if irx_surface(L.rail):                   # IRX posts lag into solid 2x: the blocking goes in with the frame
        fhow.append(_post_blocking(t, L))
    steps.append(dict(n=5, code="T-404", title="Frame", still="step5",
        goes_in=items(lambda l: l.category == "Lumber" and js in l.item and not is_beam(l), 6)
                + items(lambda l: l.category == "Lumber" and js not in l.item and "rail post" in (l.why or ""), 2)       # the IRX post blocking: cut with the frame
                + items(lambda l: l.category in ("Hardware", "Flashing & waterproofing") and any(k in l.item for k in ("hanger", "LedgerLOK", "H2.5", "Vycor", "flashing", "G-Tape", "membrane", "DTT1Z"))
                        or (l.category == "Hardware" and l.item.startswith("GRK RSS")), 20),
        how=fhow,
        check=["Each level square: diagonals within 1/8\"", f"The {lw(hi)}'s deck {inch(rise)} above the {lw(lo)}'s, measured at the step" if faces else "Frame level",
               "Every hanger fully nailed; ledger fasteners per the schedule", "Tape continuous; photos of the ledgers, hangers and footings before decking"]))
    rough_, fix_ = _lighting_steps(t, L)      # low-voltage lights: the rough-in with the frame, the fixtures after the rail and the stairs
    if rough_:
        steps.append(rough_)
    # 6 decking
    rows = "; ".join(f"{lv.name}: " + (lv.L.plan.summary() if lv.L.plan is not None else "rows per zone " + " · ".join(f"{z.name} {z.z.decking.rows}" for z in lv.zones)) for lv in levels)
    steps.append(dict(n=6, code="T-405", title="Decking", still="step6",
        goes_in=items(lambda l: l.category in (("Decking", "Fasteners") if s.extras.hardie_skirt else ("Decking", "Fasteners", "Fascia")) and "skirt" not in l.item.lower(), 14),
        how=[ms.get("Field", ""), ms.get("Face screws", "Borders first, then the field."),
             rows + ". Borders and breakers first" + (" — on both sides of the step between the levels" if faces else "") + ", then the field rows from the outer edge toward the house."],
        check=[f"{ftin(s.deck_gap)} gaps held", "No cut end shows at an outer edge or at the step", "Color: every board from the same run"]))
    # 7 rail
    rl = L.rail
    irx_ = _irx_rail(t, L, ms.get("Rail", "")) if irx_surface(rl) else None
    steps.append(dict(n=7, code="T-406", title="Rail", still="step7",
        goes_in=items(lambda l: l.category == "Rail", 10) + items(lambda l: l.category == "Hardware" and ("rail posts" in (l.why or "") or "HeadLOK" in l.item)),
        how=(irx_[0] if irx_ else [ms.get("Rail", "")] + (["Drink rail on TimberTech drink-rail brackets, mitered at every turn, plugs color-matched."]
                                                         if (s.railing.drink_rail and "drink rail" not in ms.get("Rail", "").lower()) else []))
            + ([f"The step between the levels is guarded along the {lw(hi)}'s edge except at the stair opening."] if (faces and rl) else []),
        check=[f"Top of rail {rl.height:g}\" above each level's decking; posts plumb" if rl else "—",
               "Cables tensioned, no 4\" sphere passes" if RAIL_SYSTEMS.get(s.railing.system, {}).get("cable") else "Balusters under 4\" clear"] + (irx_[1] if irx_ else [])))
    # 8 the stairs and the step skirt
    skirt = next((getattr(p.spec.geometry, "step_skirt", None) for p in L.parts if getattr(p.spec.geometry, "step_skirt", None)), None)
    if stairs or faces:
        shw = []
        for p, ss, sl in stairs:
            nm, g = getattr(ss, "name", None) or "Stair", sl.geo
            if getattr(sl, "build", "") == "box":
                shw.append(f"{nm}: {g.risers} risers @ {inches_frac(g.riser_in)} — a framed 2x6 box {ftin(sl.width)} wide on a 4\" compacted base, "
                           + box_step_words(p.spec, box_step_free_ends(p.spec, p.layout.stairs, sl)) + ".")
                continue
            inset = getattr(ss, "inset", False) or str(sl.side).startswith("edge:")
            oc_ = sl.width / max(1, sl.stringers - 1)
            shw.append(f"{nm}: {g.risers} risers @ {inches_frac(g.riser_in)}, {g.treads} tread{'s' if g.treads != 1 else ''} @ {inches_frac(g.tread_in)} — {sl.stringers} 2x12 stringers @ {oc_:.0f}\" OC"
                       + (f" hung from the notch header in the {p.name.lower()}, the bottom riser at the step face, the feet on the {lw(lo)} deck" if (inset and sl.landing == "deck") else " on LSCZ connectors at the rim")
                       + (", fascia skirts both sides stepped under each tread" if getattr(sl, "skirts", False) else "") + ", closed risers" + (" (HardieTrim: the HardieTrim step)" if s.extras.hardie_skirt else "") + ", treads Cortex 2 per stringer per board.")
        if faces:
            sk = skirt or {}
            rule = next((p.takeoff.schedule["Step skirt"] for p in L.parts if (getattr(p.takeoff, "schedule", None) or {}).get("Step skirt")), "")   # the order's own rule
            shw.append(f"Step skirt: the face between the levels in {s.decking.collection} {s.decking.fascia_color or s.decking.color} fascia — "
                       + (rule if rule else f"boards cut to height and installed vertically, {inch(float(sk.get('gap_in', 0.125)), 16)} gaps, on 2x4 nailers @ "
                          f"{float(sk.get('stud_oc_in', 16)):g}\" OC fastened to the {lw(hi)}'s rim, 1/2\" off the {lw(lo)}'s decking") + f"; the {lw(hi)}'s picture frame over its top.")
        if any(sl.landing == "grade" for p, ss, sl in stairs):
            shw.append("Each stair that lands on grade: 36\" of firm, level ground at the bottom, as wide as the stair (no pad in this scope).")
        steps.append(dict(n=8, code="T-407", title=("Stairs and the step skirt" if faces and stairs else "The step skirt" if faces else "Stairs"), still="yard",
            goes_in=items(lambda l: (l.category == "Lumber" and any(k in (l.why or "") for k in ("stair", "box step", "skirt")))
                          or (l.category == "Stairs" and "door step" not in l.item.lower()) or (l.category == "Hardware" and ("stair" in l.item.lower() or "box step" in l.item.lower()))
                          or (l.category in ("Fascia", "Stairs", "Lumber") and ("skirt" in l.item.lower() or "furring" in l.item.lower())), 14),
            how=shw,
            check=["Risers within 3/8\" of each other; treads level, nosings straight", "Skirt boards plumb, gaps even, clear of the lower decking" if faces else "Landing at the bottom firm and level, 36\" deep",
                   "Plugs set flush"]))
    if fix_:
        steps.append(fix_)
    hs_ = _hardie_step(t, L)
    if hs_:
        steps.append(hs_)
    steps[-1]["check"] = steps[-1]["check"] + ["End of construction"]
    for i, st_ in enumerate(steps):
        st_["n"], st_["code"] = i + 1, f"T-4{i:02d}"
    _shared_lines(steps, t)
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
    sheets = all_sheets(L, t, flags, S, customer=customer)      # a composite deck (two levels, a wrap): whole-deck sheets in the global frame
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
    if customer:                              # a client / supplier page: the office checks stay in the internal set
        for st_ in steps:
            st_["check"] = [c for c in st_["check"] if not OFFICE_CHECK.match(c)]
    page = buildset_html(t, sheets, steps, stills, viewer_html(S, None, title=f"{L.spec.job} — 3D", standalone=False), f"{L.spec.job} — build set")
    (out / "buildset.html").write_text("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'></head><body>" + page + "</body></html>")
    (out / "scene.json").write_text(json.dumps(S.to_dict()))
    return dict(sheets=sheets, steps=steps, stills=stills, scene=S, viewer=str(out / "viewer.html"), buildset=str(out / "buildset.html"))
