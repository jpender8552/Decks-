"""Cold-formed steel deck framing (CEMCO light-gauge members) — the order rewritten from the dimensional takeoff.

The layout engine sizes the frame as if it were lumber at the same depth (a 600S162-54 C-joist reads as the "600S" size). This
module then swaps the wood items for steel ones:
  * joist-size lumber            -> the job's C-joists (600S162-54 by default), G90 (joists, picture-frame joists, blocking)
  * rims / ledgers               -> 600T track (one ply; the track caps the joist ends), ledger track on a steel ledger angle
  * beams                        -> boxed pairs of C-joists (C + C toe-to-toe, screwed), engineer sizes the gauge
  * posts on the piers           -> 3" x 3" galvanized steel post stubs on the Diamond Pier bracket
  * hangers / nails / SDS / tape -> clip angles, #12 self-drilling hex-washer screws; no joist tape (steel does not rot)
  * stair stringers              -> steel stringers

No CEMCO deck span table was found, so the steel prices are ESTIMATES (per LF, Front Range supply, 2026) and the members
are sized by the engineer of record — every steel line says so.
"""
from __future__ import annotations

import math
import re
from typing import List

from .catalog import actual

# estimated supply prices, per LF unless noted
PRICE = dict(
    joist=2.40,          # 600S162-54 C-joist, 16 ga, G90
    track=2.05,          # 600T track, 54 mil, G90
    beam=2.40,           # 600S162-54, used in boxed pairs (the engineer may heavier the gauge)
    angle=2.60,          # 2x2 / 3x3 ledger angle 14 ga
    post=14.0,           # 3x3 HSS 11 ga galvanized stub, each (cut to height)
    pier_bracket=38.0,   # pier-head bracket / post base, each
    clip=3.25,           # clip angle, each
    tek_500=58.0,        # #12-14 x 1" hex washer self-drilling, 500 ct
    tek_ledger_50=74.0,  # 1/4" x 3-1/2" lag-tek / structural screw into the rim board, 50 ct
    stringer=95.0,       # 2-step steel stringer, each
    touchup=24.0,        # cold-galv spray, each
)
SRC = "est. — CFS supply (Front Range), confirm with the CEMCO dealer"
DEPTH = {"2x6": '6"', "2x8": '7-1/4"', "2x10": '9-1/4"', "2x12": '11-1/4"', "600S": '6"', "800S": '8"', "1000S": '10"'}
MILS_GA = {"33": "20 ga", "43": "18 ga", "54": "16 ga", "68": "14 ga", "97": "12 ga"}

_LUMBER = re.compile(r"^(\d+x\d+|\d+S)x(\d+)\b")


def names(s) -> dict:
    """How the steel members read on every page: depth, joist / track designations, gauge."""
    j = s.framing.steel_joist or "600S162-54"
    mils = j.split("-")[-1] if "-" in j else "54"
    ga = MILS_GA.get(mils, f"{mils} mil")
    depth = DEPTH.get(s.framing.joist_size, f'{int(j[:len(j) - len(j.lstrip("0123456789"))]) / 100:g}"' if j[0].isdigit() else '6"')
    trk = s.framing.steel_track or "600T"
    return dict(depth=depth, joist=j, track=trk, ga=ga, mils=mils,
                joist_txt=f"CEMCO {j} C-joist ({depth}, {mils} mil / {ga}, G90)", track_txt=f"CEMCO {trk} track ({mils} mil / {ga}, G90)",
                beam_txt=f"boxed CEMCO {j} (2 C toe-to-toe, G90)")


def _lf(line) -> float:
    m = _LUMBER.match(line.item)
    return line.order * int(m.group(2)) if m else 0.0


def steel_frame(t) -> None:
    """Rewrite a dimensional Takeoff in place for a cold-formed steel frame."""
    from .takeoff import Line, CutPiece  # noqa: F401  (Line used below)
    s, L = t.spec, t.layout
    jsize = s.framing.joist_size
    N = names(s)
    dep = N["depth"]
    beam_noms = set()
    ren = {}
    for bl in L.beam_lines:
        beam_noms.add(bl.size)
        ren[f"{bl.size} {bl.species}"] = f"boxed {N['joist']}"
        bl.label = bl.label.replace(f"{bl.size} {bl.species}", f"boxed {N['joist']}")
    def steelify(txt: str) -> str:
        for a_, b_ in ren.items():
            txt = txt.replace(a_, b_)
        return txt.replace(f"{jsize} @", f"{N['joist']} @").replace(f"{jsize} joists", f"{N['joist']} C-joists").replace(f"{jsize} SYP", N["joist"]).replace(f"PF {jsize}", f"PF {N['joist']}")
    # LF by role from the layout
    track_lf = L.outer_edge_lf if L.multi else 2 * (L.finished_w + L.finished_d) / 12.0
    ledger_lf = L.wall_lf / 12.0
    beam_lf = sum(bl.length for bl in L.beam_lines) / 12.0
    n_posts = L.n_footings
    lumber_joist_lf = 0.0
    keep: List = []
    n_stringers = 0
    for ln in t.lines:
        if ln.category == "Lumber":
            m = _LUMBER.match(ln.item)
            nom = m.group(1) if m else ""
            if nom == jsize or "stair carrier" in ln.item:
                lumber_joist_lf += _lf(ln)
                continue
            if "beam" in ln.why or nom.startswith(("4x", "6x", "8x")) or "post" in ln.why or "posts" in ln.why:
                continue                                    # beams + posts: replaced from the layout below
            if nom == "2x12":
                n_stringers += ln.net
                continue
            if nom == "2x6":                                # stair kicker boards
                continue
            keep.append(ln)
        elif ln.category == "Stairs" and "landing" in ln.item and "frame" in ln.item:
            continue
        elif ln.category == "Hardware" and any(k in ln.item for k in ("hanger", "Hanger", "LUS", "HUC", "nail", "Nail", "H2.5", "SDS", "RSS", "Strong-Drive", "BC4", "BC6", "post cap", "Post Cap", "LedgerLOK", "lag", "bolt", "LSCZ", "SD10212", "DTT")) \
                and "rail" not in ln.why.lower():
            continue
        elif ln.category == "Flashing & waterproofing" and "Tape" in ln.item:
            continue
        elif ln.category == "Footings" and ("ABA" in ln.item or "ABU" in ln.item or "post base" in ln.item.lower()):
            continue
        else:
            keep.append(ln)
    joist_lf = max(0.0, lumber_joist_lf - track_lf - ledger_lf)

    def ad(item, net, order, unit, why, uc, note=""):
        out.append(Line("Lumber", item, net, order, unit, why, uc, SRC, note=note))

    out: List = []
    jl = int(math.ceil(joist_lf * 1.05))
    ad(f"{N['joist_txt']} — joists, PF joists, blocking", round(joist_lf), jl, "LF",
       f"+5%  (cut to length by the supplier where possible) — {L.frame.spacing:g}\" OC", PRICE["joist"], "member gauge per the engineer")
    tl = int(math.ceil((track_lf + ledger_lf) * 1.05))
    ad(f"{N['track_txt']} — rims (single ply, caps the joist ends) + ledger track", round(track_lf + ledger_lf), tl, "LF",
       f"+5%  ({track_lf:.0f} LF rim + {ledger_lf:.0f} LF ledger)", PRICE["track"])
    if ledger_lf:
        al = int(math.ceil(ledger_lf * 1.1))
        ad("Steel ledger angle 3\" x 3\" 14 ga G90 — joist seats on the ledger track", round(ledger_lf), al, "LF", "+10%", PRICE["angle"])
    if beam_lf:
        bl_ = int(math.ceil(beam_lf * 2 * 1.05))
        ad(f"CEMCO {N['joist']} C, G90 — boxed beams (2 C toe-to-toe)", round(beam_lf * 2), bl_, "LF",
           "+5%  (" + " · ".join(f"{b.label} {b.length / 12:.1f}'" for b in L.beam_lines) + ")", PRICE["beam"], "engineer sizes the beam gauge / depth")
    from .spec import covers_of
    from .takeoff import cover_posts_x
    n_shared = sum(len(cover_posts_x(c)) for c in covers_of(s) if c.get("footing") == "deck_pier")
    if n_shared:
        ad("Steel side bracket, 11 ga galvanized — deck beam bolted to the 6x6 cover post (shared pier)", n_shared, n_shared, "ea",
           "exact  (one per shared post, (2) 1/2\" thru-bolts + #12 screws into the beam)", 32.0)
        n_posts = max(0, n_posts - n_shared)
    if n_posts and not s.framing.existing_posts:
        ad("Steel post stub 3\" x 3\" x 11 ga HSS, hot-dip galvanized, cap plate welded — cut to height", n_posts, n_posts, "ea",
           "exact  (one per deck-only pier; " + " / ".join(sorted(set(f'{b.post_len:.0f}"' for b in L.beam_lines))) + " clear)", PRICE["post"])
        ad("Pier-head post bracket for the Diamond Pier bolt (steel post)", n_posts, n_posts, "ea", "exact", PRICE["pier_bracket"])
    n_clip = sum(z.frame.hangers_single for z in L.zones) or 2 * int(math.ceil(joist_lf / max(1.0, L.frame.joist_len / 12.0)))
    out_hw = []
    out_hw.append(Line("Hardware", "Steel clip angle 1-1/2\" x 1-1/2\" x 7\" 16 ga G90 — joist to track / beam", n_clip, n_clip + 6, "ea", "+6  (2 per joist end where it frames into a beam or ledger)", PRICE["clip"], SRC))
    n_tek = 8 * n_clip + int(joist_lf * 2) + int(track_lf * 2) + int(beam_lf * 8) + 8 * n_posts
    boxes = int(math.ceil(n_tek / 500))
    out_hw.append(Line("Hardware", "#12-14 x 1\" hex-washer self-drilling screw, Climaseal, 500 ct", boxes, boxes, "box", f"{n_tek} needed  (clips, track, boxed beams, post brackets)", PRICE["tek_500"], SRC))
    if ledger_lf:
        n_ll = int(math.ceil(ledger_lf * 12 / 8))
        bx = int(math.ceil(n_ll / 50))
        out_hw.append(Line("Hardware", "Structural screw 1/4\" x 3-1/2\" through the ledger track into the house rim board (or per the engineer)", bx, bx, "box", f"{n_ll} needed — 2 rows staggered 16\" OC", PRICE["tek_ledger_50"], SRC))
    if ledger_lf:
        n_lat = s.framing.lateral_ties * len(L.zones)
        out_hw.append(Line("Hardware", "Lateral-load tension tie for steel joists (Simpson DTT2Z w/ steel-joist kit or the engineer's detail) — IRC R507.9.2 equivalent", n_lat, n_lat, "ea", "exact  (2 near each end of every ledger)", 28.0, SRC))
    out_hw.append(Line("Hardware", "Cold-galvanizing spray (cut ends, field drilling)", 2, 2, "ea", "lot", PRICE["touchup"], SRC))
    if n_stringers:
        out_hw.append(Line("Stairs", "Steel stair stringer, galvanized, pre-formed to the riser / tread", n_stringers, n_stringers, "ea", "exact", PRICE["stringer"], SRC))
    # put the steel framing where the lumber was
    first_other = next((i for i, l in enumerate(keep) if l.category != "Lumber"), len(keep))
    t.lines = keep[:first_other] + out + keep[first_other:]
    hw_at = next((i for i, l in enumerate(t.lines) if l.category == "Hardware"), len(t.lines))
    t.lines[hw_at:hw_at] = out_hw
    for c in t.cut_list:
        if c.nominal == jsize:
            c.nominal = N["joist"]
        elif c.nominal in (s.framing.post_size,):
            c.nominal = "3x3 HSS"
        elif c.nominal == "2x12":
            c.nominal = "steel stringer"
    t.schedule.pop("Joist tape", None)
    t.schedule.pop("Blocking", None)
    if "Ledger" in t.schedule:
        t.schedule["Ledger"] = f"{N['track']} ledger track + 3x3 ledger angle, 1/4\" structural screws 2 rows staggered 16\" OC into the rim board (engineer confirms) · flashing and membrane as for wood"
    t.schedule["Steel frame"] = (f"{N['joist']} C-joists @ {L.frame.spacing:g}\" OC · single-ply {N['track']} track rims · boxed {N['joist']} beams · all G90 · clip angles with #12 self-drilling screws "
                                 "(4 per leg) · cut ends cold-galvanized · no joist tape needed")
    t.summary["beams"] = [steelify(b_) for b_ in t.summary["beams"]]
    t.notes = [steelify(n_) for n_ in t.notes]
    L.notes[:] = [steelify(n_) for n_ in L.notes]
    for z in L.zones:
        z.frame.notes[:] = [steelify(n_) for n_ in z.frame.notes]
        for b in z.frame.beams:
            b.label = steelify(b.label)
            if getattr(b, "check", None) is not None and b.check.note:
                b.check.note = b.check.note.replace(f"{b.size} not in IRC R507.5 — treated as", f"boxed {N['joist']}: no IRC beam table for steel — laid out as")
    for c in t.cut_list:
        c.member, c.note = steelify(c.member), steelify(c.note)
        if c.member.startswith("Posts under"):
            c.member = c.member.replace("Posts under", "Steel post stubs / cover posts under")
    for ln in t.lines:
        if ln.category in ("Lumber", "Hardware", "Footings"):
            ln.why = steelify(ln.why)
    sm = t.summary
    sm["joists"] = f"{N['joist_txt']} @ {L.frame.spacing:g}\" OC"
    sm["rims"] = f"single-ply {N['track']} track rims (G90)" + (f" and {N['track']} ledger track on a steel angle" if ledger_lf else "")
    sm["posts"] = sm["posts"].replace(f"{L.n_footings} x {s.framing.post_size}", f"{n_posts} x 3x3 galvanized steel post stubs" + (f" + {n_shared} cover posts carrying the deck beam" if n_shared else ""))
    sm["material_cost"] = round(sum(l.ext for l in t.lines), 2)
    t.notes.append("Frame is CEMCO cold-formed steel: the layout is sized as the equivalent-depth lumber, then the engineer of record "
                   "designs the members (gauge, beam build-up, clip schedule). Steel prices are estimates until the CEMCO dealer quotes.")
    t.joist_lf = joist_lf
