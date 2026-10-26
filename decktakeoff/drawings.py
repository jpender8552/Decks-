"""SVG drawing sheets from the scene boxes + layout — the same geometry the 3D model is built from.
Sheets: G-001 general notes & design criteria (the permit-set sheet) · S-100 foundation plan · S-101 framing plan ·
A-101 decking plan · A-201 rail plan + elevation · A-301 section + front elevation · D-501 details.
Every sheet: 1000 x 700 field, GSX title block, cream ground, ink / gold. Design intent; the stamped set governs."""
from __future__ import annotations

import html as _html
import math
import re
import textwrap
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from .catalog import RAIL_SYSTEMS, decking_facts, actual, rail_name
from .layout import Layout
from .spec import post_words, post_base_sku
from .scene import Scene, Box, build_scene
from .units import ftin

INK, GOLD, CREAM, SAND, MUTE = "#111111", "#d49e1b", "#f7f2e8", "#e9dfcf", "#6b665e"
FILL = dict(timber="#c9a06a", timber_dk="#a87e4c", deck="#c4c2bd", border="#3a3a3c", steel="#1c1c1e", railmetal="#2b2621", concrete="#cfcbc2", stone="#9a948b",
            house="#eee6d6", glass="#a9c6da", ground="#8a9a5e", gravel="#a39c90", water="#3f9fd0", tub="#4a4238", privacy="#b8b0a2", roof="#3a2f2a", fascia="#b08a5a", drink="#3a3a3c", cable="#888", hanger="#333")
W_, H_ = 1000, 700
IN = 1 / 12.0


def esc(t): return _html.escape(str(t), quote=True)
def T(x, y, s, size=11, w=600, anchor="start", fill=INK, rot=0):
    tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{w}" text-anchor="{anchor}" fill="{fill}"{tr}>{esc(s)}</text>'
def R(x, y, w, h, fill, stroke=INK, sw=0.8, extra=""):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{max(h, 0):.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'
def LN(x0, y0, x1, y1, stroke=INK, sw=0.8, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
def C(x, y, r, fill, stroke=INK, sw=0.8, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
def PG(pts, fill, stroke=INK, sw=0.8):
    return f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def sheet(num: str, title: str, sub: str, body: List[str], scale_note: str, meta: dict) -> str:
    hdr = [R(0, 0, W_, 46, INK, "none", 0), T(18, 30, num, 22, 900, fill=GOLD), T(110, 22, title.upper(), 15, 900, fill="#f3ead9"),
           T(110, 39, textwrap.shorten(sub, 110, placeholder="…"), 9.5, 400, fill="#d8cfbf"),
           T(W_ - 18, 20, textwrap.shorten(meta["job_line"], 70, placeholder="…"), 9.5, 700, "end", "#d8cfbf"),
           T(W_ - 18, 36, meta["rev_line"], 8.5, 400, "end", "#b8b0a2")]
    ftr = [LN(0, H_ - 34, W_, H_ - 34, GOLD, 2), T(18, H_ - 14, scale_note, 9.5, 600, fill=MUTE),
           T(W_ - 18, H_ - 14, meta["footer"], 8.6, 400, "end", MUTE)]
    cid = f"clip{num.replace('-', '')}"
    return (f'<svg viewBox="0 0 {W_} {H_}" xmlns="http://www.w3.org/2000/svg" font-family="Nunito Sans, -apple-system, Helvetica, Arial, sans-serif">'
            f'<rect width="{W_}" height="{H_}" fill="{CREAM}"/><defs><clipPath id="{cid}"><rect x="0" y="0" width="{W_}" height="{H_ - 52 - 36}"/></clipPath></defs>'
            + "".join(hdr) + f'<g transform="translate(0,52)" clip-path="url(#{cid})">' + "".join(body) + "</g>" + "".join(ftr) + "</svg>")


# ------------------------------------------------------------------ projections
def plan_xform(x0, x1, y0, y1, px0, py0, pw, ph):
    """plan: x to the right, y (toward the yard) DOWN the sheet, house at the top."""
    sc = min(pw / (x1 - x0), ph / (y1 - y0))
    return (lambda x: px0 + (x - x0) * sc), (lambda y: py0 + (y - y0) * sc), sc


def elev_xform(x0, x1, z0, z1, px0, py0, pw, ph):
    sc = min(pw / (x1 - x0), ph / (z1 - z0))
    return (lambda x: px0 + (x - x0) * sc), (lambda z: py0 + (z1 - z) * sc), sc


_MAT_COLORS: Dict[str, str] = {}


_STEEL = {"on": False}


def fill_for(b: Box) -> str:
    if _STEEL["on"] and b.kind in ("joist", "rim", "ledger", "block", "beam", "post", "doubler", "stringer"):
        return "#a7adb2" if b.kind != "beam" else "#8d949a"           # CEMCO galvanized steel
    if b.kind in ("cpost", "cbeam", "cledger", "rafter"):
        return FILL["timber"] if b.kind != "cbeam" else FILL["timber_dk"]
    if b.kind in ("joist", "rim", "ledger", "block", "beam", "post", "doubler", "brace"):
        return FILL["timber"] if b.kind != "beam" else FILL["timber_dk"]
    if b.mat in ("deck", "border", "drink", "fascia") and b.mat in _MAT_COLORS:
        return _MAT_COLORS[b.mat]
    return FILL.get(b.mat, FILL.get(b.kind, "#bbb"))


def draw_plan_boxes(o, X, Y, sc, boxes: List[Box], kinds, stroke=INK, sw=0.4, dash=""):
    for b in sorted([b for b in boxes if b.kind in kinds], key=lambda q: (q.z0, q.z1)):
        f = fill_for(b)
        if b.shape == "cyl":
            o.append(C(X((b.x0 + b.x1) / 2), Y((b.y0 + b.y1) / 2), (b.x1 - b.x0) / 2 * sc, f, stroke, sw, dash))
        elif b.rot and b.rot_axis == "z":     # a mitred piece along an angled edge: rotate about its centre in plan
            cx, cy = X((b.x0 + b.x1) / 2), Y((b.y0 + b.y1) / 2)
            o.append(f'<g transform="rotate({math.degrees(b.rot):.2f} {cx:.1f} {cy:.1f})">' + R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, f, stroke, sw, f'stroke-dasharray="{dash}"' if dash else "") + "</g>")
        else:
            o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, f, stroke, sw, f'stroke-dasharray="{dash}"' if dash else ""))


def draw_elev_boxes(o, X, Z, sc, boxes: List[Box], kinds, stroke=INK, sw=0.4):
    """front elevation: viewer in the yard looking at the house; nearer (larger y) drawn last."""
    for b in sorted([b for b in boxes if b.kind in kinds], key=lambda q: (q.y1, q.z0)):
        if b.rot and b.rot_axis == "y":        # a member rotated in the x-z plane (a knee brace): draw it at its angle
            cx, cz = X((b.x0 + b.x1) / 2), Z((b.z0 + b.z1) / 2)
            o.append(f'<g transform="rotate({-math.degrees(b.rot):.2f} {cx:.1f} {cz:.1f})">' + R(X(b.x0), Z(b.z1), (b.x1 - b.x0) * sc, (b.z1 - b.z0) * sc, fill_for(b), stroke, sw) + "</g>")
        elif b.rot and b.rot_axis == "x":      # rotated in the y-z plane: its x-z silhouette
            from .axo import corners
            cs = corners(b)
            zs = [q[2] for q in cs]
            o.append(R(X(b.x0), Z(max(zs)), (b.x1 - b.x0) * sc, (max(zs) - min(zs)) * sc, fill_for(b), stroke, sw))
        else:
            o.append(R(X(b.x0), Z(b.z1), (b.x1 - b.x0) * sc, (b.z1 - b.z0) * sc, fill_for(b), stroke, sw))


def dim_h(o, X, y, xa, xb, lab, size=8.5, up=True):
    o.append(LN(X(xa), y, X(xb), y, INK, 0.8)); o.append(LN(X(xa), y - 4, X(xa), y + 4)); o.append(LN(X(xb), y - 4, X(xb), y + 4))
    o.append(T((X(xa) + X(xb)) / 2, y - 4 if up else y + 11, lab, size, 700, "middle"))


def dim_v(o, Y, x, ya, yb, lab, size=8.5, left=True):
    o.append(LN(x, Y(ya), x, Y(yb), INK, 0.8)); o.append(LN(x - 4, Y(ya), x + 4, Y(ya))); o.append(LN(x - 4, Y(yb), x + 4, Y(yb)))
    o.append(T(x - 5 if left else x + 13, (Y(ya) + Y(yb)) / 2, lab, size, 700, "middle", rot=-90))


def house_outline(o, X, Y, sc, S: Scene):
    bx0, bx1, by0, by1 = plan_bounds(S)
    for b in S.boxes:
        if b.kind == "house":      # clipped to the plan window: a big house must not run over the notes column
            x0_, x1_, y0_, y1_ = max(b.x0, bx0), min(b.x1, bx1), max(b.y0, by0 - 2.0), min(b.y1, by1)
            if x1_ > x0_ and y1_ > y0_:
                o.append(R(X(x0_), Y(y0_), (x1_ - x0_) * sc, (y1_ - y0_) * sc, FILL["house"], INK, 1.4))
    for b in S.boxes:
        if b.kind == "wall":
            if b.rot and b.rot_axis == "z":
                cx, cy = X((b.x0 + b.x1) / 2), Y((b.y0 + b.y1) / 2)
                o.append(f'<g transform="rotate({math.degrees(b.rot):.2f} {cx:.1f} {cy:.1f})">' + R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, FILL["house"], INK, 1.2) + "</g>")
            else:
                o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, FILL["house"], INK, 1.2))
        if b.kind == "privacy":
            o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, FILL["privacy"], "#7a7267", 0.8))
            lbl = "EXISTING STUCCO PARAPET — stays" if "parapet" in (b.tag or "") else "PRIVACY / LOT WALL — nothing fastens, no rail"
            horiz = (b.x1 - b.x0) > (b.y1 - b.y0)
            if horiz:
                o.append(T(X((b.x0 + b.x1) / 2), Y((b.y0 + b.y1) / 2) + 3, lbl, 7, 700, "middle", MUTE))
            else:
                o.append(T(X((b.x0 + b.x1) / 2) - 8, Y((b.y0 + b.y1) / 2), lbl, 7, 700, "middle", MUTE, rot=-90))
    for z in S.meta["zones"]:
        o.append(T(X(z["x0"] + z["W"] / 2), Y(z["wall_y"]) - 16, (f"HOUSE — {z['name']}" if z.get("ledger", True) else f"OPEN — {z['name']} (rear beam, no ledger)"), 8, 800, "middle", "#a89b84"))


def deck_outline(S: Scene) -> List[Tuple[float, float]]:
    if S.meta.get("outline"):
        return [tuple(p) for p in S.meta["outline"]]
    zs = S.meta["zones"]
    pts = [(zs[0]["x0"], zs[0]["wall_y"])]
    for z in zs:
        pts += [(z["x0"], z["front"]), (z["x0"] + z["W"], z["front"])]
    pts.append((zs[-1]["x0"] + zs[-1]["W"], zs[-1]["wall_y"]))
    for z in reversed(zs):
        pts += [(z["x0"] + z["W"], z["wall_y"]), (z["x0"], z["wall_y"])]
    return pts


def plan_bounds(S: Scene):
    """The plan window: the deck plus 3-4' of margin, widened to take in stairs and landings that run past the frame."""
    x0, x1, y0, y1 = -3.0, S.W + 3.0, S.y_min - 4.0, S.y_front + 4.0
    for b in S.boxes:
        if b.tag and (b.tag.startswith("tread") or b.tag.startswith("landing") or "stair" in b.tag or "lower deck" in b.tag):
            x0, x1, y0, y1 = min(x0, b.x0 - 2.0), max(x1, b.x1 + 2.0), min(y0, b.y0 - 2.0), max(y1, b.y1 + 2.0)
    return x0, x1, y0, y1


# ------------------------------------------------------------------ sheets
def sheet_notes(L: Layout, S: Scene, t, flags, meta, index: Optional[List[Tuple[str, str]]] = None) -> str:
    """G-001. index: [(num, title)] of the sheets actually in the set (built last by all_sheets); None -> the standard list."""
    s = L.spec
    o = []
    o.append(T(24, 24, "PROJECT", 9, 800, fill=GOLD))
    lines = textwrap.wrap(f"{s.job}", 92) + [f"{s.site.address}, {s.site.city} {s.site.state} {s.site.zip}".strip(", "), f"Prepared for {s.client}" if s.client else "",
             f"{L.deck_sf:g} SF · {ftin(s.geometry.height_in)} above grade · {len(L.zones)} zone{'s' if len(L.zones) > 1 else ''}"]
    y = 40
    for ln in [x for x in lines if x]:
        o.append(T(24, y, ln, 10, 600)); y += 14
    o.append(T(24, y + 12, "DESIGN CRITERIA", 9, 800, fill=GOLD)); y += 28
    cover = bool(s.geometry.cover or s.geometry.covers)
    crit = [("Deck live load", "40 psf uniform (IRC Table R301.5); guards 200 lb concentrated / 50 plf"),
            ("Ground snow", f"{s.site.ground_snow_psf:g} psf (ground; deck design uses the larger of snow and live)" + (" — snow governs" if s.site.ground_snow_psf > 40 else " — 40 psf live governs") + (f"; {s.site.snow_note}" if s.site.snow_note else "")),
            ("Dead load", "10 psf deck" + ((" · 15 psf porch cover (standing seam steel on sheathing, Hardie soffit; 12 psf actual, 15 used) carried on the deck posts" if s.extras.cover_roof.lower().startswith("standing") else " · 15 psf porch cover (shingles, sheathing, Hardie soffit) carried on the deck posts") if cover else "")),
            ("Roof snow (cover)", f"{s.site.ground_snow_psf:g} psf flat-roof design snow" + (" (PPRBD minimum 30 psf)" if "colorado springs" in (s.site.city or "").lower() else "") + ", sliding snow off the house roof + drift at the house wall per ASCE 7 Ch. 7" if cover else "—"),
            ("Design total", f"{max(z.frame.total_psf for z in L.zones):g} psf on the deck" + (" (hot-tub bay 110 psf)" if s.extras.hot_tub else "") + (" · cover posts add roof snow + dead to the deck frame and footings (engineered)" if cover else "")),
            ("Wind", s.site.wind_note or f"{s.site.wind_speed_mph:g} mph Vult, Exposure C, Risk Cat. II (ASCE 7-16) — confirm special wind region"), ("Frost depth", ftin(s.site.frost_depth_in) + " (footings bear below)"),
            ("Soil bearing", f"{s.site.soil_bearing_psf:,.0f} psf presumptive (IRC R401.4.1) — no soils report"), ("Seismic", s.site.seismic_design_category),
            ("Wildfire (WUI)", ("Ignition-resistant construction: Class A / WUI-listed decking (TimberTech Advanced PVC), noncombustible rail (steel), fiber-cement skirt, soffit and fascia, "
                                "26 ga flashing at every wall, " + ("Class A noncombustible standing seam steel roof on the cover with metal eave / rake / headwall trims" if (cover and s.extras.cover_roof.lower().startswith("standing")) else "Class A roof on the cover") + "; under-deck kept clear of combustibles (Colorado Springs WUI Code / IWUIC 504)") if s.site.wui_fire_zone else "not in a WUI zone"),
            ("Codes", (s.site.code_basis + "; " + ("Tables R507.5 / R507.6 / R507.4 / R507.9" if s.framing.system == "dimensional" else
                                                    "timber members outside the tables: stamped design" if s.is_timber else "cold-formed steel frame per AISI S240, engineered"))
                       if s.site.code_basis else
                       ((("2021 IRC as amended by Pikes Peak Regional Building Dept; IRC R507 decks; ASCE 7-16 loads; IWUIC / Colorado Springs Wildland-Urban Interface Code; "
                          if "colorado springs" in (s.site.city or "").lower() else
                          f"2021 IRC as adopted by {s.site.city or 'the jurisdiction'}; IRC R507 decks; ASCE 7-16 loads; " + ("IWUIC where mapped; " if s.site.wui_fire_zone else ""))
                         + ("timber members outside the tables: stamped design" if s.is_timber else "Tables R507.5 / R507.6 / R507.4 / R507.9")))),
            ("Engineering", ("Stamped structural set by a Colorado PE required — the stamped set governs" if s.extras.engineered
                             else ("Stamped structural set by a Colorado PE, provided by GSX and billed at cost with the permit" if s.extras.engineering_note else "Prescriptive; no engineering required by this design")))]
    for k, v in crit:
        for i, ln in enumerate(textwrap.wrap(v, 92)[:3]):
            o.append(T(24, y, k if i == 0 else "", 8.5, 800)); o.append(T(150, y, ln, 8.5, 400)); y += 12
        y += 1
    o.append(T(24, y + 12, "STRUCTURE", 9, 800, fill=GOLD)); y += 28
    sm = t.summary
    bls_ = L.beam_lines or []
    if len(bls_) > 2:          # many beam lines: count, size, posts, worst load — every line is on S-100 / S-101
        worst = max((max(b_.post_loads) for b_ in bls_ if getattr(b_, "post_loads", None)), default=0)
        beams_txt = (f"{len(bls_)} {' / '.join(sorted({b_.kind for b_ in bls_}))} beam lines, {' / '.join(sorted({b_.size + ' ' + b_.species for b_ in bls_}))}, "
                     f"{sum(len(b_.posts_x) for b_ in bls_)} posts" + (f" (worst {worst:,.0f} lb)" if worst else "") + " — S-100 / S-101")
    else:
        beams_txt = "; ".join(sm["beams"])
    struct = [("Footings", sm["posts"].split(" on ")[-1]), ("Posts", sm["posts"].split(" on ")[0]), ("Beams", beams_txt), ("Joists", sm["joists"]), ("Rims", sm["rims"]),
              ("Ledger", t.schedule.get("Ledger", "—")), ("Decking", sm["decking"]), ("Rail", sm["rail"])]
    for k, v in struct:
        for i, ln in enumerate(textwrap.wrap(v, 96)[:2]):
            o.append(T(24 if i == 0 else 150, y, k if i == 0 else "", 8.5, 800)); o.append(T(150, y, ln, 8.5, 400)); y += 12
    # right column: sheet index + flags + setbacks
    x2 = 600
    o.append(T(x2, 24, "SHEET INDEX", 9, 800, fill=GOLD))
    yy = 40
    from .spec import covers_of
    idx = [("G-001", "General notes · design criteria")] + ([SHEET_INDEX_EXTRA[0]] if (s.site.plan and s.site.plan.get("parcel")) else []) + [
        ("A-001", "Isometric · renders"), ("A-002", "Isometric — assembled, labeled"), ("A-003", "Isometric — exploded, labeled"), ("S-100", "Foundation plan"),
        ("S-101", "Framing plan"), ("S-102", "Structure isometric, labeled"), ("A-101", "Decking plan")] + ([("A-201", "Railing plan + elevation")] if L.rail else []) + [
        ("A-202", "Elevations"), ("A-301", "Section + front elevation")] + ([SHEET_INDEX_EXTRA[1], ("A-402", "Roof covers — exploded isometric")] if covers_of(s) else []) + [
        ("D-501", "Details")] + ([("D-502", "Connection details — steel frame")] if s.framing.system == "steel" else []) + (
        [("D-503", "Connection details — roof covers")] if s.geometry.covers else []) + [("T-400", "Build steps (build set)"), ("T-700", "Order + schedules (takeoff)")]
    if index is not None:
        idx = index
    for num, title in idx:
        o.append(T(x2, yy, num, 8.5, 800, fill=GOLD)); o.append(T(x2 + 52, yy, title, 8.5, 500)); yy += 13
    o.append(T(x2, yy + 12, "SITE", 9, 800, fill=GOLD)); yy += 28
    site = []
    if s.site.rear_setback_required_ft is not None or s.site.deck_to_rear_line_ft is not None:
        site.append(f"Rear / front lot line: deck edge {s.site.deck_to_rear_line_ft if s.site.deck_to_rear_line_ft is not None else '?'}' from the line, " + (f"{s.site.rear_setback_required_ft:g}' required" if s.site.rear_setback_required_ft is not None else "setback per the PUD — Planning to confirm (C-100)"))
    if s.site.side_setback_required_ft is not None or s.site.deck_to_side_line_ft is not None:
        site.append(f"Side lot line: deck edge {s.site.deck_to_side_line_ft if s.site.deck_to_side_line_ft is not None else '?'}' from the line, " + (f"{s.site.side_setback_required_ft:g}' required" if s.site.side_setback_required_ft is not None else "setback per the PUD — Planning to confirm (C-100)"))
    site += [f"Easement: {e}" for e in s.site.easements]
    if s.site.notes:
        site += textwrap.wrap(s.site.notes, 70)
    if not site:
        site = ["Setbacks not on file — verify the plat / ILC before layout"]
    for ln in site:
        for k_, w_ in enumerate(textwrap.wrap(ln, 74)[:3]):
            o.append(T(x2 + (8 if k_ else 0), yy, w_, 8, 400)); yy += 12
    if flags is not None:
        o.append(T(x2, yy + 12, "FLAGS (INTERNAL — remove before the permit submittal)", 9, 800, fill=GOLD)); yy += 28
        for f in [f for f in flags if f.severity in ("STOP", "ENGINEER", "CODE")][:14]:
            o.append(T(x2, yy, f.severity, 7.5, 800, fill="#b3261e" if f.severity == "STOP" else GOLD)); o.append(T(x2 + 62, yy, textwrap.shorten(f.text, 66, placeholder="…"), 7.8, 400)); yy += 11.5
    return sheet("G-001", "General notes · design criteria", "Loads, codes, structure summary, sheet index, site — the permit-set cover", o, "No scale", meta)


def sheet_foundation(L: Layout, S: Scene, meta) -> str:
    from .spec import covers_of
    from .takeoff import cover_posts_x
    o = []
    x0, x1, y0, y1 = plan_bounds(S)
    X, Y, sc = plan_xform(x0, x1, y0 - 2, y1, 40, 24, 640, 560)
    house_outline(o, X, Y, sc, S)
    o.append(PG([(X(x), Y(y)) for x, y in deck_outline(S)], "none", INK, 1.2))
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("beam",), INK, 0.9, "6 3")
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("stone",), "#7a7267", 0.6)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("footing",), INK, 0.9)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("post",), INK, 0.7)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("cpost",), INK, 0.7)
    n = 0
    rows = []
    for bl in L.beam_lines:
        for px, zn, ld in zip(bl.posts_x, bl.post_zone, bl.post_loads):
            n += 1
            x, y = px * IN, bl.y * IN
            o.append(T(X(x), Y(y) - 12 * (1 if bl.kind == "drop" else -1) - (0 if bl.kind == "drop" else 4), f"P{n}", 8, 800, "middle"))
            shared = [c for c in covers_of(L.spec) if c.get("footing") == "deck_pier" and any(abs(cx - px / 12.0) < 1.0 for cx in cover_posts_x(c))]
            rows.append((f"P{n}", ftin(px), ftin(bl.y), zn + (" +cover" if shared else ""), f"{ld:,.0f} lb" + (" +roof" if shared else "")))
    if any(st.mid_support for st in L.stairs):
        for b in [q for q in S.boxes if q.tag == "stair footing"]:
            n += 1
            cx_, cy_ = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
            o.append(T(X(cx_), Y(cy_) - 12, f"P{n}", 8, 800, "middle"))
            rows.append((f"P{n}", ftin(cx_ * 12), ftin(cy_ * 12), "stair", "carrier"))
    for b in [q for q in S.boxes if q.tag == "landing footing"]:
        n += 1
        cx_, cy_ = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
        o.append(T(X(cx_), Y(cy_) - 12, f"P{n}", 8, 800, "middle"))
        rows.append((f"P{n}", ftin(cx_ * 12), ftin(cy_ * 12), "stair", "landing"))
    for bl in L.beam_lines:                 # beam lines are in inches; the plan transform takes feet
        o.append(T(X(bl.x0 * IN) + 4, Y(bl.y * IN) - 6, bl.label, 7.5, 800, fill=MUTE))
    # dims: beam lines from the front, zone widths
    zs = S.meta["zones"]
    dim_h(o, X, Y(S.y_front) + 16, zs[0]["x0"], zs[-1]["x0"] + zs[-1]["W"], ftin(S.W * 12) + " along the house", up=False)
    for z in zs:
        dim_h(o, X, Y(S.y_front) + 32, z["x0"], z["x0"] + z["W"], f"{z['name']} {ftin(z['W'] * 12)}", up=False)
    used_x = []
    for bl in sorted(L.beam_lines, key=lambda b: -b.y):      # to the front rim of the beam's own zone(s); dims that would stack step out
        zf = max((z["front"] for z in zs if z["name"] in (bl.zones or [])), default=S.y_front)
        xd = X(bl.x1 * IN) + 10
        while any(abs(xd - u) < 14 for u in used_x):
            xd += 16
        used_x.append(xd)
        dim_v(o, Y, xd, bl.y * IN, zf, f"{ftin((zf - bl.y * IN) * 12)} to rim face", left=False)
    # schedule
    sx = 710
    o.append(T(sx, 24, "FOOTING SCHEDULE", 9, 800, fill=GOLD))
    ft = L.frame
    desc = {"caisson": f"{int(ft.footing_dia_in)}\" drilled caisson x {ftin(ft.footing_depth_in)} + 6\" above grade, (4) #4 verticals + #3 ties, 5/8\" x 8\" cast-in anchor",
            "diamond_pier": f"Diamond Pier {ft.footing_model} (head + 4 x 50\" pins), 3,300 lb allowable",
            "concrete": f"{int(ft.footing_dia_in)}\" concrete pier x {ftin(ft.footing_depth_in)}, wet-set standoff base",
            "existing": ("Existing caissons and columns stay — verify plumb, bearing and condition; new column caps (engineered)" if L.spec.framing.existing_posts
                         else "Existing caissons stay — tops chipped level, standoff bases on epoxy-set 5/8\" rods (engineer confirms capacity)")}[L.spec.framing.footing_type]
    yy = 40
    for ln in textwrap.wrap(desc, 44):
        o.append(T(sx, yy, ln, 8, 500)); yy += 11
    yy += 6
    hdr = ("ID", "x", "y", "zone", "load")
    xs = [sx, sx + 30, sx + 90, sx + 150, sx + 190]
    for h, xx in zip(hdr, xs):
        o.append(T(xx, yy, h.upper(), 7.5, 800, fill=MUTE))
    yy += 4; o.append(LN(sx, yy, sx + 250, yy, MUTE, 0.6)); yy += 11
    for r in rows[:22]:
        for v, xx in zip(r, xs):
            o.append(T(xx, yy, v, 8, 500))
        yy += 11.5
    o.append(T(sx, yy + 10, "x from the left frame face facing the house; y from the reference wall.", 7.2, 400, fill=MUTE))
    o.append(T(sx, yy + 21, f"Frost {ftin(L.spec.site.frost_depth_in)} · soil {L.spec.site.soil_bearing_psf:,.0f} psf · worst post {max(z.frame.footing_load_lb for z in L.zones):,.0f} lb", 7.2, 400, fill=MUTE))
    if L.spec.framing.system == "steel":
        for k_, ln_ in enumerate([(f"Deck-only piers: 6x6 {post_words(L.spec)} post on {post_base_sku(L.spec)}, steel saddle to the beam (D-502 / 3)."
                                   if L.spec.framing.steel_deck_post == "wood" else "Deck-only piers: 3x3 galvanized HSS stub on a pier-head bracket (D-502 / 3)."),
                                  f"+cover: the 6x6 {post_words(L.spec)} roof-cover post stands on this pier",
                                  f"({post_base_sku(L.spec)}) and carries the deck beam on a steel side bracket (D-502 / 4);",
                                  "roof load adds — the engineer sizes the pier.",
                                  f"Beams: boxed CEMCO {L.spec.framing.steel_joist}, flush (D-502 / 2)."]):
            o.append(T(sx, yy + 36 + k_ * 11, ln_, 7.2, 500))
    return sheet("S-100", "Foundation plan", "Footings, posts and beam lines with the footing schedule; beams dashed (below the joists)", o, "Plan · not to scale · house at the top · dimensions govern", meta)


def sheet_framing(L: Layout, S: Scene, t, meta) -> str:
    o = []
    x0, x1, y0, y1 = plan_bounds(S)
    X, Y, sc = plan_xform(x0, x1, y0 - 2, y1, 40, 24, 700, 560)
    house_outline(o, X, Y, sc, S)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("beam",), "#3f5d8a", 1.0, "6 3")
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("ledger",), INK, 0.6)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("joist",), INK, 0.35)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("block",), INK, 0.35)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("rim",), INK, 0.7)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("post",), INK, 0.7)
    for b in S.boxes:
        if b.kind == "beam" and b.tag and b.kind == "beam":
            pass
    for bl in L.beam_lines:
        suf = "" if bl.label.upper().startswith(("FLUSH", "DROP")) else (" (below)" if bl.kind == "drop" else " (flush)")
        o.append(T(X(bl.x0 * IN) + 6, Y(bl.y * IN) - 5, bl.label + suf, 7.5, 800, fill="#3f5d8a"))
    zs = S.meta["zones"]
    jlab = L.spec.framing.steel_joist if L.spec.framing.system == "steel" else L.frame.joist_size
    for zl, z in zip(L.zones, zs):
        fr = zl.frame
        o.append(T(X(z["x0"] + z["W"] / 2), Y(z["front"]) - 10, f"{z['name']}: {len(fr.joist_x)} field + {len(fr.pf_x)} PF {jlab} @ {fr.spacing:g}\" OC · {ftin(fr.joist_len)}", 7.5, 800, "middle"))
    for dx, Ld, lab in L.divider_x:
        o.append(T(X(dx * IN), Y(S.y_front) + 8, f"doubled joist · {lab}", 6.5, 700, "middle", MUTE))
    dim_h(o, X, Y(S.y_front) + 22, zs[0]["x0"], zs[-1]["x0"] + zs[-1]["W"], ftin(S.W * 12), up=False)
    for z in zs:
        dim_v(o, Y, X(z["x0"] + z["W"]) - 8, z["wall_y"], z["front"], f"{z['name']} {ftin(z['D'] * 12)}")
    # notes rail
    nx = 760
    o.append(T(nx, 24, "FRAMING NOTES", 9, 800, fill=GOLD))
    bls_ = L.beam_lines or []
    beams_ = (f"{len(bls_)} {' / '.join(sorted({b_.kind for b_ in bls_}))} beam lines, {' / '.join(sorted({b_.size + ' ' + b_.species for b_ in bls_}))}: "
              + "; ".join(f"{b_.label.split()[-1]} {ftin(b_.length)}, {len(b_.posts_x)} posts" for b_ in bls_)) if len(bls_) > 2 else "; ".join(t.summary["beams"])
    notes = [t.summary["joists"], t.summary["rims"], t.schedule.get("Ledger", ""), t.schedule.get("Blocking", "blocking one row over the beam, staggered"),
             t.schedule.get("Joist tape", ""), beams_]
    hw = [f"{l.item}: {l.net:g}" for l in t.lines if l.category == "Hardware" and l.unit == "ea"][:8]
    yy = 40
    for n in notes + ["Connectors:"] + hw:
        for ln in textwrap.wrap(n, 40)[:5]:
            o.append(T(nx, yy, ln, 7.6, 400)); yy += 10.5
        yy += 3
    return sheet("S-101", "Framing plan", "Ledger, joists, rims, blocking, beams; every member in the model — the cut list is on T-600", o, "Plan · not to scale · house at the top · dimensions govern", meta)


def sheet_decking(L: Layout, S: Scene, t, meta) -> str:
    o = []
    x0, x1, y0, y1 = plan_bounds(S)
    X, Y, sc = plan_xform(x0, x1, y0 - 2, y1, 40, 24, 700, 560)
    house_outline(o, X, Y, sc, S)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("fascia",), "#777", 0.3)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("board",), "#8f8f8c", 0.25)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("border",), "#222", 0.3)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("railpost",), INK, 0.5)
    zs = S.meta["zones"]
    if L.plan is None:
        for zl, z in zip(L.zones, zs):
            dk = zl.decking
            o.append(T(X(z["x0"] + z["W"] / 2), Y((z["wall_y"] + z["front"]) / 2), f"{z['name']} · {dk.rows} rows", 9, 800, "middle", "#fff"))
        for dx, Ld, lab in L.divider_x:
            o.append(T(X(dx * IN), Y(S.y_front) + 8, lab, 6.5, 700, "middle", MUTE))
    else:
        for i, (a, b, n, y_top) in enumerate(L.plan.panels):
            rows_p = [r for r in L.plan.rows if r.panel == i]
            ymid = (min(r.y0 for r in rows_p) + max(r.y1 for r in rows_p)) / 2 * IN if rows_p else y_top * IN / 2
            o.append(T(X((a + b) / 2 * IN), Y(ymid), f"panel {i + 1} · {n} rows", 9, 800, "middle", "#fff"))
        xm_ = (min(d_[0] for d_ in L.plan.dividers) + max(d_[0] for d_ in L.plan.dividers)) / 2 if L.plan.dividers else 0
        for x, y_lo, y_hi, lab in L.plan.dividers:          # inside the panel between the breakers, light on the boards
            left_ = x <= xm_ and len(L.plan.dividers) > 1
            o.append(T(X(x * IN) + (5 if left_ else -5), Y(y_hi * IN) - (14 if left_ else 25), f"breaker {lab} · {ftin(y_hi - y_lo)}", 6.5, 700, "start" if left_ else "end", "#f3ecdc"))
    dim_h(o, X, Y(S.y_front) + 22, -S.meta["edge"], S.W + S.meta["edge"], ftin((S.W + 2 * S.meta["edge"]) * 12) + " over the edge boards", up=False)
    nx = 760
    o.append(T(nx, 24, "DECKING", 9, 800, fill=GOLD))
    s = L.spec
    f = decking_facts(s.decking.collection)
    notes = [f"Field: {s.decking.brand} {s.decking.collection} {s.decking.color}, {f['width']:g}\" x {f['thick']:g}\", {ftin(s.deck_gap)} gaps",
             f"Border{' & dividers' if L.divider_x else ''}: {s.decking.border_collection or s.decking.collection} {s.decking.border_color or s.decking.color}" if s.geometry.picture_frame else "No picture frame",
             f"Boards run {'parallel to' if s.geometry.board_direction == 'parallel' else 'out from'} the house; edge overhang {ftin(S.meta['edge'] * 12)}" + (" over the fascia" if s.decking.fascia else " — no fascia, rim exposed"),
             t.schedule.get("Field", ""), t.schedule.get("Picture frame + stairs", ""), t.schedule.get("Face screws", ""),
             (L.plan.summary() + " — every board one piece wall to border, no butt joints" if L.plan is not None else
              "Rows per zone: " + " · ".join(f"{z.name} {z.decking.rows}" for z in L.zones) + (" (rip at the house)" if any(z.decking.last_row_dev < -0.5 for z in L.zones) else " (no rips)"))]
    yy = 40
    for n in [n_ for n_ in notes if n_]:
        for ln in textwrap.wrap(n, 40)[:8]:
            o.append(T(nx, yy, ln, 7.6, 400)); yy += 10.5
        yy += 3
    return sheet("A-101", "Decking plan", "Every board, border and divider as it lays; rail posts shown for the pockets", o, "Plan · not to scale · house at the top · dimensions govern", meta)


def sheet_rail(L: Layout, S: Scene, t, meta) -> str:
    o = []
    rl = L.rail
    x0, x1, y0, y1 = plan_bounds(S)
    X, Y, sc = plan_xform(x0, x1, y0 - 2, y1, 40, 24, 700, 300)
    o.append(PG([(X(x), Y(y)) for x, y in deck_outline(S)], FILL["deck"], INK, 1.0))
    house_outline(o, X, Y, sc, S)
    if rl:
        placed = []                         # posts 18" apart beside a stair: the second label steps down a line
        for i, p in enumerate(rl.posts):
            x, y = p.x * IN, p.y * IN
            o.append(R(X(x) - 3, Y(y) - 3, 6, 6, INK, INK, 0.5))
            below = y > (S.y_min + S.y_front) / 2
            lx, ly = X(x), (Y(y) + 14 if below else Y(y) - 6)
            while any(abs(lx - a_) < 30 and abs(ly - b_) < 8 for a_, b_ in placed):
                ly += 9 if below else -9
            placed.append((lx, ly))
            o.append(T(lx, ly, f"RP{i + 1} {p.kind[0]}", 6.5, 800, "middle"))
        for sec in rl.sections:
            pass
    # elevation of the outer edge (x-z), rail only
    Xe, Z, sce = elev_xform(-2.0, S.W + 2.0, S.deck_top - 1.2, S.deck_top + 4.4, 40, 350, 700, 230)
    o.append(LN(Xe(-2), Z(S.deck_top), Xe(S.W + 2), Z(S.deck_top), INK, 1.2))
    draw_elev_boxes(o, Xe, Z, sce, [b for b in S.boxes if b.kind in ("rim", "fascia") and b.y1 >= S.y_front - 0.3], ("rim", "fascia"), INK, 0.4)
    draw_elev_boxes(o, Xe, Z, sce, [b for b in S.boxes if b.kind in ("railpost", "toprail", "cable", "baluster", "botrail", "drink", "railcap") and b.y1 >= S.y_front - 0.5], ("railpost", "toprail", "cable", "baluster", "botrail", "drink", "railcap"), "none", 0)
    if rl:
        front_posts = [p for p in rl.posts if abs(p.y * IN - S.y_front) < 0.4]
        xs = sorted(p.x * IN for p in front_posts)
        for a, b in zip(xs, xs[1:]):
            dim_h(o, Xe, Z(S.deck_top) + 18, a, b, ftin((b - a) * 12), 7.5, up=False)
        dim_v(o, Z, Xe(-1.2), S.deck_top, S.deck_top + rl.height * IN, f"{rl.height:g}\"")
    nx = 760
    o.append(T(nx, 24, "RAILING", 9, 800, fill=GOLD))
    yy = 40
    notes = [t.summary["rail"], t.schedule.get("Rail", "")]
    if rl:
        side_ = lambda v: re.sub(r"^edge:(\d+)$", r"side \1", v)          # outline sides read as A-100 numbers them
        notes.append("Bays: " + " · ".join(f"{side_(s_.side)} {ftin(s_.ctc)}" for s_ in rl.sections[:12]) + (" (sides as numbered on A-100)" if any(s_.side.startswith("edge:") for s_ in rl.sections) else ""))
        notes.append("Guard 36\" min above the deck; openings under 4\" (IRC R312). Rail LF for labor = deck-edge LF of actual rail.")
    for n in notes:
        for ln in textwrap.wrap(n, 40)[:6]:
            o.append(T(nx, yy, ln, 7.6, 400)); yy += 10.5
        yy += 3
    return sheet("A-201", "Railing plan + elevation", "Post IDs and types (E end · L line · C corner), bay lengths, outer-edge elevation", o, "Plan above · elevation of the outer edge below", meta)


def sheet_section(L: Layout, S: Scene, t, meta) -> str:
    o = []
    s = L.spec
    deep = max(L.zones, key=lambda z: z.D)
    xc = (deep.x0 + deep.W / 2) * IN
    # section: y-z at x = xc, viewer looking along -x (house on the left)
    Yv, Z, sc = elev_xform(deep.wall_y * IN - 3.0, S.y_front + 4.0, -max(4.0, L.frame.footing_depth_in / 12 + 1), S.deck_top + 4.5, 40, 24, 560, 560)
    cut = [b for b in S.boxes if b.x0 <= xc <= b.x1 or b.kind in ("post", "footing", "stone", "cap", "base", "railpost", "brace")]
    near = [b for b in cut if b.kind in ("post", "footing", "stone", "cap", "base") and abs((b.x0 + b.x1) / 2 - xc) < 12]
    braces = [b for b in cut if b.kind == "brace" and b.rot_axis == "x"]
    if not any(b.kind == "joist" for b in cut):     # the cut falls between joists: show the one just behind it
        js_ = [b for b in S.boxes if b.kind == "joist"]
        if js_:
            jn = min(js_, key=lambda b: abs((b.x0 + b.x1) / 2 - xc))
            xc = (jn.x0 + jn.x1) / 2
            cut = [b for b in S.boxes if b.x0 <= xc <= b.x1 or b.kind in ("post", "footing", "stone", "cap", "base", "railpost", "brace")]
    o.append(R(Yv(deep.wall_y * IN - 3.0), Z(0), (S.y_front + 7.0 - deep.wall_y * IN) * sc, (max(4.0, L.frame.footing_depth_in / 12 + 1)) * sc, "#e0d7c2", "none", 0))
    o.append(LN(Yv(deep.wall_y * IN - 3.0), Z(0), Yv(S.y_front + 4.0), Z(0), INK, 1.0))
    o.append(T(Yv(deep.wall_y * IN - 2.6), Z(0) + 10, "grade", 7.5, 700, "start", MUTE))
    o.append(LN(Yv(deep.wall_y * IN - 3.0), Z(-s.site.frost_depth_in / 12), Yv(S.y_front + 4.0), Z(-s.site.frost_depth_in / 12), "#3f5d8a", 0.8, "4 3"))
    o.append(T(Yv(S.y_front + 3.5), Z(-s.site.frost_depth_in / 12) - 3, f"frost {ftin(s.site.frost_depth_in)}", 7.5, 700, "end", "#3f5d8a"))
    house = [b for b in S.boxes if b.kind == "house" and b.x0 <= xc <= b.x1]
    for b in house:
        o.append(R(Yv(b.y0), Z(b.z1), (b.y1 - b.y0) * sc, (b.z1 - b.z0) * sc, FILL["house"], INK, 1.2))
    for b in sorted(near + [q for q in cut if q.kind in ("ledger", "joist", "rim", "block", "beam", "board", "border", "fascia", "drink", "toprail", "cable", "baluster", "botrail", "railpost", "railcap", "tub", "water")], key=lambda q: q.z0):
        if b.kind in ("joist",) and not (b.x0 <= xc <= b.x1):
            continue
        f = fill_for(b)
        o.append(R(Yv(b.y0), Z(b.z1), (b.y1 - b.y0) * sc, (b.z1 - b.z0) * sc, f, INK if b.kind not in ("cable",) else "none", 0.5 if b.kind != "board" else 0.3))
    for b in braces[:1]:
        cy_, cz_ = Yv((b.y0 + b.y1) / 2), Z((b.z0 + b.z1) / 2)
        o.append(f'<g transform="rotate({math.degrees(b.rot):.2f} {cy_:.1f} {cz_:.1f})">' + R(Yv(b.y0), Z(b.z1), (b.y1 - b.y0) * sc, (b.z1 - b.z0) * sc, fill_for(b), INK, 0.5) + "</g>")
        o.append(T(cy_ - 8, cz_ + 22, "4x4 knee brace", 6.8, 700, "end"))
    dim_v(o, Z, Yv(S.y_front + 2.6), 0, S.deck_top, f"{ftin(s.geometry.height_in)} deck", left=False)      # short labels: the two dims stack
    if L.rail:
        dim_v(o, Z, Yv(S.y_front + 2.6), S.deck_top, S.deck_top + L.rail.height * IN, f"guard {L.rail.height:g}\"", left=False)
    for bl in L.beam_lines:
        if bl.x0 <= xc * 12 <= bl.x1:
            dim_h(o, Yv, Z(S.deck_top) - 14, bl.y * IN, S.y_front, ftin((S.y_front - bl.y * IN) * 12) + (" cantilever" if bl.kind == "drop" else ""), 7.5)
    o.append(T(Yv(deep.wall_y * IN - 1.5), Z(S.deck_top + 3.5), f"SECTION through zone {deep.name} at {ftin(deep.W / 2)} — looking toward the left end", 8.5, 800))
    # front elevation (x-z) in the right panel
    Xe, Ze, sce = elev_xform(-4.0, S.W + 4.0, -1.0, S.deck_top + 12.0, 620, 60, 370, 300)
    el = []                                 # clipped to its own frame: a measured two-storey house is wider and taller than the deck
    draw_elev_boxes(el, Xe, Ze, sce, S.boxes, ("house", "wall", "privacy", "roof", "glass"), INK, 0.5)
    draw_elev_boxes(el, Xe, Ze, sce, S.boxes, ("footing", "stone", "stonecap", "base", "post", "brace", "cap", "beam", "rim", "fascia", "joist", "ledger", "cpost", "cbeam", "hardie", "ssroof"), INK, 0.35)
    draw_elev_boxes(el, Xe, Ze, sce, S.boxes, ("board", "border", "railpost", "toprail", "cable", "baluster", "botrail", "drink", "railcap"), "none", 0)
    o.append('<defs><clipPath id="a301el"><rect x="610" y="52" width="390" height="318"/></clipPath></defs>')
    o.append('<g clip-path="url(#a301el)">' + "".join(el) + "</g>")
    o.append(T(620, 44, "FRONT ELEVATION — from the yard", 8.5, 800))
    o.append(LN(Xe(-4), Ze(0), Xe(S.W + 4), Ze(0), INK, 1.0))
    dim_h(o, Xe, Ze(0) + 16, 0, S.W, ftin(S.W * 12), 7.5, up=False)
    nx = 620
    o.append(T(nx, 400, "SECTION NOTES", 9, 800, fill=GOLD))
    yy = 416
    notes = [f"Deck surface {ftin(s.geometry.height_in)} above grade; guard {L.rail.height:g}\" where the drop exceeds 30\"" if L.rail else f"Deck surface {ftin(s.geometry.height_in)} above grade",
             (f"{len(L.beam_lines)} {' / '.join(sorted({b_.kind for b_ in L.beam_lines}))} beam lines, {' / '.join(sorted({b_.size + ' ' + b_.species for b_ in L.beam_lines}))} — every line on S-100 / S-101"
              if len(L.beam_lines or []) > 2 else "; ".join(t.summary["beams"])),
             f"Posts {t.summary['posts']}", t.schedule.get("Ledger", ""), t.schedule.get("Joist tape", "")]
    for n in notes:
        for ln in textwrap.wrap(n, 62)[:3]:
            o.append(T(nx, yy, ln, 7.6, 400)); yy += 10.5
        yy += 3
    return sheet("A-301", "Section + front elevation", "Cut through the deepest zone; heights to grade, frost line, cantilever, guard", o, "Section left · elevation right · not to a common scale", meta)


def sheet_details(L: Layout, S: Scene, t, meta) -> str:
    """Schematic details drawn from the job's own parameters."""
    o = []
    s = L.spec
    timber = s.is_timber
    jb, jd = L.frame.joist_size, None
    def frame_(x, y, w, h, num, title):
        o.append(R(x, y, w, h, "#fff", INK, 0.8)); o.append(R(x, y, w, 18, INK, "none", 0)); o.append(T(x + 8, y + 13, f"{num}  {title}", 9, 800, fill=GOLD))
    def note(x, y, w, txt):
        yy = y
        for ln in textwrap.wrap(txt, int(w / 4.6)):
            o.append(T(x, yy, ln, 7.2, 400)); yy += 9.5
        return yy
    # 1 ledger
    frame_(20, 20, 300, 290, "1", "LEDGER AT THE HOUSE")
    o.append(R(40, 60, 40, 200, FILL["house"], INK, 1.0)); o.append(T(60, 165, "house rim", 7, 700, "middle", MUTE, rot=-90))
    o.append(R(80, 80, 6, 160, "#3f5d8a", "none", 0)); o.append(T(83, 76, "membrane 12\" up the wall", 6.5, 600, "middle"))
    o.append(R(86, 100, 22, 60, FILL["timber"], INK, 0.8)); o.append(T(97, 132, "ledger", 6.5, 700, "middle", INK, rot=-90))
    o.append(R(108, 100, 120, 60, FILL["timber"], INK, 0.6)); o.append(T(168, 133, f"{L.frame.joist_size} joist in {('LUS' + ('410Z' if timber else '28Z'))}", 7, 700, "middle"))
    o.append(R(86, 92, 150, 6, FILL["deck"], INK, 0.5)); o.append(T(160, 89, "decking", 6.5, 600, "middle"))
    o.append(LN(80, 100, 112, 100, GOLD, 2)); o.append(T(120, 98, "flashing over the ledger, under the cladding", 6.5, 600))
    for yy in (112, 148):
        o.append(LN(58, yy, 108, yy, INK, 1.4)); o.append(C(108, yy, 2.2, INK))
    note(40, 275, 270, t.schedule.get("Ledger", "") + (" · 26 ga wall flashing (WUI)" if s.site.wui_fire_zone else ""))
    # 2 post / beam / cap
    frame_(340, 20, 300, 290, "2", "POST · BEAM · CAP")
    bl = L.beam_lines[0] if L.beam_lines else None
    o.append(R(470, 120, 40, 150, FILL["timber"], INK, 0.9)); o.append(T(490, 200, f"{s.framing.post_size} post", 7, 700, "middle", INK, rot=-90))
    o.append(R(400, 70, 180, 50, FILL["timber_dk"], INK, 0.9)); o.append(T(490, 100, f"{bl.size if bl else ''} {'drop' if (bl and bl.kind == 'drop') else 'flush'} beam", 7.5, 700, "middle"))
    o.append(R(462, 112, 56, 16, FILL["steel"], INK, 0.6)); o.append(T(530, 126, (bl.cap_end if bl else "cap") + (" black" if s.framing.hardware_finish == "black" else ""), 6.5, 600))
    if bl and bl.kind == "drop":
        o.append(R(400, 56, 180, 14, FILL["timber"], INK, 0.5)); o.append(T(400, 52, "joists bear on the beam, H2.5AZ each", 6.5, 600))
    else:
        o.append(T(400, 64, "joists hang on both faces (LUS)", 6.5, 600))
    bls_ = L.beam_lines or []
    if len(bls_) > 2:          # many beam lines: the count, the size and the worst post — the lines themselves are on S-100 / S-101
        worst = max((max(b_.post_loads) for b_ in bls_ if getattr(b_, "post_loads", None)), default=0)
        note(360, 275, 270, f"{len(bls_)} {' / '.join(sorted({b_.kind for b_ in bls_}))} {' / '.join(sorted({b_.size + ' ' + b_.species for b_ in bls_}))} beam lines, "
                            f"{sum(len(b_.posts_x) for b_ in bls_)} posts" + (f", worst post {worst:,.0f} lb" if worst else "") + " (S-100 / S-101)."
                            + (" Plies on RSS screws, 2 rows @ 12\"; caps with a 1/2\" shim." if any(b_.size.startswith("(2)2x") for b_ in bls_) else ""))
    else:
        note(360, 275, 270, "; ".join(t.summary["beams"])[:150])
    # 3 footing / base
    frame_(660, 20, 320, 290, "3", "FOOTING · POST BASE")
    ft = s.framing.footing_type
    o.append(LN(680, 200, 960, 200, INK, 1.0)); o.append(T(950, 196, "grade", 6.5, 600, "end", MUTE))
    if ft == "caisson":
        o.append(R(790, 190, 60, 110, FILL["concrete"], INK, 0.9)); o.append(T(820, 250, f"{int(L.frame.footing_dia_in)}\" caisson", 7, 700, "middle", INK, rot=-90))
        for xx in (800, 812, 828, 840):
            o.append(LN(xx, 195, xx, 295, "#3f5d8a", 1.0))
        o.append(LN(680, 200 + L.spec.site.frost_depth_in / 12 * 25, 960, 200 + L.spec.site.frost_depth_in / 12 * 25, "#3f5d8a", 0.8, "4 3")); o.append(T(690, 196 + L.spec.site.frost_depth_in / 12 * 25, f"frost {ftin(L.spec.site.frost_depth_in)}", 6.5, 600, fill="#3f5d8a"))
        o.append(R(796, 180, 48, 10, FILL["steel"], INK, 0.6)); o.append(T(852, 188, "post base, 5/8\" cast-in anchor", 6.5, 600))
        if s.extras.stone_bases:
            o.append(R(770, 110, 100, 80, "none", "#7a7267", 1.0, 'stroke-dasharray="4 3"')); o.append(T(880, 150, "stone veneer 2'x2' x 3' + cap", 6.5, 600))
    elif ft == "diamond_pier":
        o.append(R(800, 190, 40, 14, FILL["concrete"], INK, 0.9)); o.append(T(852, 200, "Diamond Pier head", 6.5, 600))
        for dx, dy in ((-1, 1), (1, 1), (-0.5, 1), (0.5, 1)):
            o.append(LN(820, 204, 820 + dx * 60, 204 + 90, INK, 1.2))
        o.append(T(852, 240, f"4 x 50\" pins · {L.frame.footing_model}", 6.5, 600)); o.append(R(806, 180, 28, 10, FILL["steel"], INK, 0.6)); o.append(T(852, 188, f"{post_base_sku(s)} on the pier bolt", 6.5, 600))
    else:
        o.append(R(790, 200, 60, 90, FILL["concrete"], INK, 0.9)); o.append(T(852, 240, f"{int(L.frame.footing_dia_in)}\" pier x {ftin(L.frame.footing_depth_in)}", 6.5, 600))
    o.append(R(806, 90, 28, 90, FILL["timber"], INK, 0.8)); o.append(T(820, 140, "post", 6.5, 700, "middle", INK, rot=-90))
    # 4 rail post / guard
    frame_(20, 330, 300, 270, "4", "RAIL POST · GUARD")
    rl = L.rail
    o.append(R(40, 470, 240, 14, FILL["deck"], INK, 0.6)); o.append(R(40, 484, 240, 30, FILL["timber"], INK, 0.6)); o.append(T(160, 502, "rim" + ("" if timber else " (2-ply, inner ply pocketed)"), 7, 700, "middle"))
    o.append(R(240, 380, 8, 104, FILL["steel"], INK, 0.6)); o.append(T(252, 392, f"{rl.system if rl else 'rail'} post {rl.height if rl else 36:g}\"", 6.5, 600))
    o.append(LN(180, 388, 240, 388, INK, 1.4)); o.append(T(176, 386, "top rail", 6.5, 600, "end"))
    if rl and RAIL_SYSTEMS.get(rl.system, {}).get("cable"):
        for k in range(10):
            o.append(LN(120, 470 - k * 8, 240, 470 - k * 8, "#888", 0.6))
        o.append(T(116, 430, "cables 3\" OC · no bottom rail", 6.5, 600, "end"))
    else:
        for k in range(1, 12):
            o.append(LN(120 + k * 10, 392, 120 + k * 10, 466, INK, 1.0))
    if s.railing.drink_rail:
        o.append(R(200, 374, 60, 6, FILL["border"], INK, 0.5)); o.append(T(196, 378, "drink rail", 6.5, 600, "end"))
    note(40, 560, 270, t.schedule.get("Rail", ""))
    # 5 decking edge
    frame_(340, 330, 300, 270, "5", "DECK EDGE · BORDER")
    o.append(R(360, 470, 240, 30, FILL["timber"], INK, 0.6)); o.append(T(480, 488, "rim", 7, 700, "middle"))
    o.append(R(352, 456, 60, 14, FILL["border"], INK, 0.5)); o.append(T(382, 452, "border", 6.5, 600, "middle"))
    for k in range(3):
        o.append(R(416 + k * 62, 456, 58, 14, FILL["deck"], INK, 0.4))
    o.append(T(500, 452, f"field · {ftin(s.deck_gap)} gaps", 6.5, 600, "middle"))
    o.append(LN(352, 470, 352, 500, GOLD, 1.5)); o.append(T(348, 520, f"overhang {ftin(S.meta['edge'] * 12)}" + ("" if s.decking.fascia else " — no fascia"), 6.5, 600, "end"))
    if s.decking.fascia:
        o.append(R(354, 470, 6, 30, FILL["fascia"], INK, 0.5)); o.append(T(348, 490, "fascia", 6.5, 600, "end"))
    note(360, 560, 270, t.schedule.get("Field", "")[:160] + (" · Cortex screws + plugs on the borders and dividers (2 per bearing) and the stair treads"
                                                          if (s.decking.border_fastener or "").lower().startswith("cortex") else ""))
    # 6 zone-specific
    frame_(660, 330, 320, 270, "6", "HOT-TUB BAY" if s.extras.hot_tub else ("FLUSH BEAM" if any(b.kind == "flush" for b in L.beam_lines) else "BLOCKING"))
    if s.extras.hot_tub:
        note(680, 360, 290, f"Tub bay in zone {s.extras.hot_tub_zone or 'A'}: {ftin(s.extras.hot_tub_bay_in)} square against the house — sister a joist to every joist across the bay, block between, design 100 psf; engineer confirms. Owner's electrician: 50A GFCI circuit + disconnect.")
    elif any(b.kind == "flush" for b in L.beam_lines):
        note(680, 360, 290, "Flush beam: top of beam = top of joists. Joists hang on both faces in LUS hangers; opposing hangers per Simpson and the stamped set.")
    else:
        note(680, 360, 290, t.schedule.get("Blocking", "Blocking one row over the beam, staggered up and down so every block can be end-nailed."))
    return sheet("D-501", "Details", "Ledger · post / beam / cap · footing · rail post · deck edge · the job's special condition", o, "Schematic details, not to scale", meta)


def sheet_details_steel(L: Layout, S: Scene, t, meta) -> str:
    """D-501 for a cold-formed steel frame: ledger track, joist clips, boxed beam on the shared pier, the pier, the deck edge
    with the Hardie skirt, and the under-deck / low-clearance condition. Schematic — the engineer's details govern."""
    o = []
    s = L.spec
    G = "#a7adb2"
    def frame_(x, y, w, h, num, title):
        o.append(R(x, y, w, h, "#fff", INK, 0.8)); o.append(R(x, y, w, 18, INK, "none", 0)); o.append(T(x + 8, y + 13, f"{num}  {title}", 9, 800, fill=GOLD))
    def note(x, y, w, txt):
        yy = y
        for ln in textwrap.wrap(txt, int(w / 4.6)):
            o.append(T(x, yy, ln, 7.2, 400)); yy += 9.5
        return yy
    def chan(x, y, w, h, lip=6, face="right"):     # a C section in elevation: web + flanges
        o.append(R(x, y, w, h, G, INK, 0.8))
        o.append(LN(x + (w - lip if face == "right" else lip), y + 3, x + (w - lip if face == "right" else lip), y + h - 3, "#6f757a", 0.6))
    # 1 ledger
    frame_(20, 20, 300, 290, "1", "STEEL LEDGER AT THE HOUSE")
    o.append(R(40, 60, 40, 200, FILL["house"], INK, 1.0)); o.append(T(60, 165, "house rim board", 7, 700, "middle", MUTE, rot=-90))
    o.append(R(80, 80, 5, 160, "#3f5d8a", "none", 0)); o.append(T(83, 76, "membrane 12\" up the wall", 6.5, 600, "middle"))
    o.append(R(85, 100, 8, 60, G, INK, 0.8)); o.append(T(89, 176, "ledger track", 6.5, 700, "middle"))
    o.append(R(93, 150, 26, 6, "#7b8186", INK, 0.6)); o.append(T(122, 172, "3x3 ledger angle (seat)", 6.5, 600))
    chan(93, 100, 130, 50)
    o.append(T(160, 128, f"{s.framing.steel_joist} C-joist", 7, 700, "middle"))
    o.append(R(93, 92, 150, 7, FILL["deck"], INK, 0.5)); o.append(T(170, 89, "decking", 6.5, 600, "middle"))
    o.append(LN(80, 100, 100, 100, GOLD, 2)); o.append(T(104, 84, "flashing over the track", 6.5, 600))
    for yy in (112, 140):
        o.append(LN(58, yy, 93, yy, INK, 1.4)); o.append(C(93, yy, 2.2, INK))
    note(40, 275, 270, t.schedule.get("Ledger", ""))
    # 2 joist clip
    frame_(340, 20, 300, 290, "2", "JOIST TO TRACK / BEAM")
    o.append(R(380, 70, 14, 160, G, INK, 0.8)); o.append(T(387, 245, "track or boxed beam", 6.5, 700, "middle"))
    chan(394, 110, 200, 70)
    o.append(T(494, 150, f"{s.framing.steel_joist} C-joist", 7.5, 700, "middle"))
    o.append(R(394, 118, 26, 54, "#7b8186", INK, 0.7)); o.append(T(430, 196, "clip angle 1-1/2 x 1-1/2 x 7\", 16 ga", 6.5, 600))
    for yy in (126, 142, 158):
        o.append(C(400, yy, 1.8, INK)); o.append(C(414, yy, 1.8, INK))
    note(360, 275, 270, "#12-14 self-drilling hex-washer screws, 4 per leg minimum (clip to joist web, clip to track / beam web) — the engineer's clip schedule governs. Cut ends and field holes cold-galvanized.")
    # 3 boxed beam on the shared pier
    frame_(660, 20, 320, 290, "3", "BOXED BEAM · SHARED PIER")
    o.append(R(790, 90, 40, 190, FILL["timber"], INK, 0.9)); o.append(T(810, 200, "6x6 cover post (to the roof beam)", 6.5, 700, "middle", INK, rot=-90))
    o.append(R(700, 120, 90, 50, G, INK, 0.9)); o.append(R(830, 120, 90, 50, G, INK, 0.9))
    o.append(T(745, 148, "boxed C beam", 6.5, 700, "middle")); o.append(T(875, 148, "boxed C beam", 6.5, 700, "middle"))
    o.append(R(776, 112, 68, 66, "none", "#3f5d8a", 1.2)); o.append(T(810, 108, "steel side bracket, (2) 1/2\" thru-bolts", 6.5, 600, "middle", "#3f5d8a"))
    o.append(R(786, 280, 48, 10, FILL["steel"], INK, 0.6))
    note(680, 275 - 10, 290, f"Where a cover post lands on the deck beam line it stands on the deck's Diamond Pier ({post_base_sku(s)} on the pier bolt) and carries the deck beam on a steel side bracket; elsewhere {('a 6x6 ' + post_words(s) + ' post on ' + post_base_sku(s) + ' with a steel saddle') if s.framing.steel_deck_post == 'wood' else 'a 3x3 HSS stub on a pier-head bracket'}. Engineer sizes the pier for roof + deck and the uplift hold-down.")
    # 4 footing
    frame_(20, 330, 300, 270, "4", "DIAMOND PIER")
    o.append(LN(40, 470, 300, 470, INK, 1.0)); o.append(T(296, 466, "grade", 6.5, 600, "end", MUTE))
    o.append(R(150, 458, 40, 14, FILL["concrete"], INK, 0.9)); o.append(T(196, 456, "pier head", 6.5, 600))
    for dx in (-1, -0.5, 0.5, 1):
        o.append(LN(170, 472, 170 + dx * 60, 560, INK, 1.2))
    o.append(R(160, 448, 20, 10, FILL["steel"], INK, 0.6)); o.append(R(164, 380, 12, 68, G, INK, 0.7)); o.append(T(160, 414, "post / stub", 6.5, 700, "end"))
    note(40, 575, 270, f"{L.frame.footing_model} (4 pins) — no excavation; frost-protected by the pins (submit the evaluation report). 811 locate first.")
    # 5 deck edge
    frame_(340, 330, 300, 270, "5", "DECK EDGE · HARDIE SKIRT")
    o.append(R(400, 470, 10, 40, G, INK, 0.7)); o.append(T(405, 525, "track", 6.5, 700, "middle"))
    chan(410, 470, 180, 40)
    o.append(R(392, 456, 60, 14, FILL["border"], INK, 0.5)); o.append(T(422, 452, "picture frame", 6.5, 600, "middle"))
    for k in range(2):
        o.append(R(456 + k * 62, 456, 58, 14, FILL["deck"], INK, 0.4))
    o.append(R(384, 470, 8, 46, "#f2efe8", INK, 0.6)); o.append(T(380, 494, "HardieTrim skirt", 6.5, 600, "end"))
    note(360, 545, 270, f"{s.decking.brand} {s.decking.collection} {s.decking.color}: hidden fasteners in the field, the picture frame face-fastened with color-matched plugs — every screw the maker's steel-frame screw for 14–18 ga. HardieTrim skirt on furring screwed to the track.")
    # 6 under the deck / low clearance
    frame_(660, 330, 320, 270, "6", "UNDER THE DECK · LOW END")
    o.append(LN(680, 520, 960, 520, INK, 1.0))
    o.append(R(680, 512, 280, 8, FILL["gravel"], "none", 0)); o.append(LN(680, 520, 960, 520, "#3f5d8a", 1.2, "3 2"))
    o.append(T(690, 540, "2\" gravel over 6-mil poly, sloped away from the house", 6.5, 600))
    chan(700, 470, 240, 30)
    o.append(R(700, 456, 240, 14, FILL["deck"], INK, 0.5))
    hmin = s.geometry.height_min_in
    clear = (hmin - 1.0 - actual(s.framing.joist_size)[1]) if hmin is not None else None
    o.append(LN(950, 500, 950, 512, "#b3261e", 1.2)); o.append(T(955, 510, "2\" min.", 6.5, 800, fill="#b3261e"))
    note(680, 565, 290, (f"Walkway low point: {hmin:g}\" surface to grade leaves {clear:.2f}\" under the frame — dig out / regrade to 2\" min. under that run before the poly." if clear is not None and clear < 2 else "Keep 2\" min. between the frame and the gravel."))
    return sheet("D-501", "Details — steel frame", "Steel ledger · joist clips · boxed beam on the shared pier · Diamond Pier · deck edge · under the deck", o, "Schematic details, not to scale · the engineer's details govern", meta)


def sheet_site(L: Layout, S: Scene, t, meta) -> Optional[str]:
    """C-100 site plan: the parcel and the house from the county GIS (plan frame, feet), the new decks, roof covers and
    stairs, distances to the lot lines, the reference setbacks, north arrow, street, lot coverage and the parcel facts."""
    s = L.spec
    sp = s.site.plan or {}
    if not sp.get("parcel"):
        return None
    from .spec import covers_of
    par = [tuple(p) for p in sp["parcel"]]
    xs, ys = [p[0] for p in par], [p[1] for p in par]
    X, Y, sc = plan_xform(min(xs) - 6, max(xs) + 6, min(ys) - 8, max(ys) + 6, 30, 14, 470, 580)
    o = []
    o.append(R(X(min(xs) - 6), Y(min(ys) - 8), (max(xs) - min(xs) + 12) * sc, (max(ys) - min(ys) + 14) * sc, "#e3e8d6", "none", 0))
    o.append(PG([(X(x), Y(y)) for x, y in par], "#dfe6cc", INK, 1.6))
    # the street side
    if sp.get("street"):
        top = min(ys)
        o.append(T(X((min(xs) + max(xs)) / 2), Y(top) - 10, sp["street"], 10, 900, "middle", MUTE))
    # reference setbacks (dashed), offset inward from the rear / side lines
    ref = sp.get("setback_ref") or {}
    rear_y = min(p[1] for p in par if p[1] > 0)
    if ref.get("rear") and sp.get("setback_offset"):     # the rear setback as an offset of the rear lot line (a sloped / jogged rear line)
        cxp, cyp = sum(xs) / len(xs), sum(ys) / len(ys)
        rear_edges = [(a, b) for a, b in zip(par, par[1:] + par[:1]) if a[1] > 0 and b[1] > 0 and abs(b[0] - a[0]) > abs(b[1] - a[1]) and math.hypot(b[0] - a[0], b[1] - a[1]) > 1.0]
        lines_ = [(ref["rear"], ref.get("rear_label") or f"{ref['rear']}' rear setback", "#8a6d2a", "6 4")]
        if ref.get("rear_deck"):            # where a low deck may reach (a projection allowance into the rear setback)
            lines_.append((ref["rear_deck"], ref.get("rear_deck_label") or f"{ref['rear_deck']}' — deck projection limit", "#b3261e", "2 3"))
        t_lab = float(sp.get("rear_label_t", 0.16))
        for d, lab_, col_, dash_ in lines_:
            best = None
            for a, b in rear_edges:
                ln_ = math.hypot(b[0] - a[0], b[1] - a[1]); nx_, ny_ = -(b[1] - a[1]) / ln_, (b[0] - a[0]) / ln_
                if (cxp - a[0]) * nx_ + (cyp - a[1]) * ny_ < 0:
                    nx_, ny_ = -nx_, -ny_
                p0, p1 = (a[0] + nx_ * d, a[1] + ny_ * d), (b[0] + nx_ * d, b[1] + ny_ * d)
                o.append(LN(X(p0[0]), Y(p0[1]), X(p1[0]), Y(p1[1]), col_, 0.9, dash_))
                if best is None or ln_ > best[0]:
                    best = (ln_, p0, p1)
            if best:
                _, p0, p1 = best
                ang = math.degrees(math.atan2(-(Y(p1[1]) - Y(p0[1])), X(p1[0]) - X(p0[0])))
                # one line: its label 22 px into the lot (as before); two lines: the setback's above it, the projection limit's below
                dy_ = (22 if len(lines_) == 1 else -5) if col_ == "#8a6d2a" else 11
                mx_, my_ = X(p0[0]) + (X(p1[0]) - X(p0[0])) * t_lab, Y(p0[1]) + (Y(p1[1]) - Y(p0[1])) * t_lab + dy_
                o.append(f'<g transform="rotate({-ang if abs(ang) < 90 else 180 - ang:.1f} {mx_:.1f} {my_:.1f})">' + T(mx_, my_, lab_, 6.8, 700, "middle", col_) + "</g>")
    elif ref.get("rear"):
        o.append(LN(X(min(xs)), Y(rear_y - ref["rear"]), X(max(xs)), Y(rear_y - ref["rear"]), "#8a6d2a", 0.9, "6 4"))
        o.append(T(X(max(xs)) - 4, Y(rear_y - ref["rear"]) - 4, ref.get("rear_label") or f"{ref['rear']}' R-L rear setback (reference)", 7.5, 700, "end", "#8a6d2a"))
    # house footprint (existing, hatched)
    fp = sp.get("footprint") or []
    if fp:
        o.append('<defs><pattern id="hatchC" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#b9ad97" stroke-width="1.2"/></pattern></defs>')
        o.append(PG([(X(x), Y(y)) for x, y in fp], "url(#hatchC)", INK, 1.3))
        cx = sum(p[0] for p in fp) / len(fp); cy = sum(p[1] for p in fp) / len(fp)
        o.append(T(X(cx), Y(cy), "EXISTING HOUSE", 9, 900, "middle", MUTE)); o.append(T(X(cx), Y(cy) + 12, sp.get("house_label", "one storey + garage (no work)"), 7.5, 600, "middle", MUTE))
    # decks
    out = deck_outline(S)
    o.append(PG([(X(x), Y(y)) for x, y in out], FILL["deck"], INK, 1.2))
    if sp.get("deck_label") and sp.get("deck_label_inside"):     # inside the deck (a setback line runs under its front)
        cxd, cyd = sum(q[0] for q in out) / len(out), sum(q[1] for q in out) / len(out)
        for k_, ln_ in enumerate(textwrap.wrap(sp["deck_label"], 34)[:3]):
            o.append(T(X(cxd), Y(cyd) - 4 + k_ * 9, ln_, 7, 900, "middle", INK))
    elif sp.get("deck_label"):          # one label for the whole deck, below its front edge
        o.append(T(X(sum(q[0] for q in out) / len(out)), Y(max(q[1] for q in out)) + 12, sp["deck_label"], 7.2, 900, "middle", INK))
    else:
        for z in S.meta["zones"]:
            deep = z["front"] - z["wall_y"] > 6
            o.append(T(X(z["x0"] + z["W"] / 2), (Y((z["wall_y"] + z["front"]) / 2) + 3) if deep else Y(z["front"]) + 10, f"DECK {z['name']}", 7, 900, "middle", "#f3ead9" if deep else INK))
    # stairs / landings
    for b in S.boxes:
        if b.kind in ("tread",) or (b.tag and b.tag.startswith("landing pad")) or b.mat == "concrete" and b.kind == "pad":
            o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, FILL["concrete"], INK, 0.6))
    # other work on the lot under its own permit (context): a grey outline with its label
    for oth in sp.get("others") or []:
        poly = [tuple(q) for q in oth["poly"]]
        o.append(PG([(X(x), Y(y)) for x, y in poly], "#d9d4c9", "#8b8478", 1.0).replace("/>", ' stroke-dasharray="4 3"/>', 1))
        o.append(T(X(sum(q[0] for q in poly) / len(poly)), Y(min(q[1] for q in poly)) - 5 + oth.get("label_dy", 0), oth.get("label", "other deck"), 6.6, 800, "middle", "#6d675d"))
    # shade sails: the sail outline dashed, its posts solid
    for sl in s.geometry.sails or []:
        Pc = [(float(c[0]), float(c[1])) for c in sl["corners"]]
        o.append(PG([(X(x), Y(y)) for x, y in Pc], "none", "#3f5d8a", 1.1).replace("/>", ' stroke-dasharray="5 3"/>', 1))
        for k in sl.get("posts", []):
            x, y = Pc[k]
            o.append(C(X(x), Y(y), 3.2, "#3f5d8a", INK, 0.6))
        o.append(T(X(sum(p[0] for p in Pc) / len(Pc)), Y(max(p[1] for p in Pc)) + 12, "SHADE SAIL — " + (f"{len(sl.get('posts', []))} post{'s' if len(sl.get('posts', [])) != 1 else ''} at the deck rail corner{'s' if len(sl.get('posts', [])) != 1 else ''}" if sl.get("mount") == "deck_rail" else f"{len(sl.get('posts', []))} steel posts"), 6.6, 800, "middle", "#3f5d8a"))
    # roof covers: roof edge dashed, posts
    from .takeoff import cover_posts_x
    for c in covers_of(s):
        ov = float(c.get("overhang_ft", 1.0))
        o.append(R(X(c["x0"] - 0.4), Y(c["y0"]), (c["x1"] - c["x0"] + 0.8) * sc, (c["y1"] - c["y0"] + ov) * sc, "none", "#1c1c1e", 1.2, 'stroke-dasharray="5 3"'))
        for px in cover_posts_x(c):
            o.append(R(X(px - 0.25), Y(c["y1"] - 0.25), 0.5 * sc, 0.5 * sc, INK, INK, 0.5))
    # distances to the lot lines
    def seg_dist(px, py, a, b):
        ax, ay = a; bx, by = b; dx, dy = bx - ax, by - ay
        tt = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(ax + tt * dx - px, ay + tt * dy - py), (ax + tt * dx, ay + tt * dy)
    edges = [(a, b) for a, b in zip(par, par[1:] + par[:1]) if math.hypot(b[0] - a[0], b[1] - a[1]) > 0.01]
    def nearest(px, py, pred):
        best = None
        for a, b in edges:
            if pred(a, b):
                d, q = seg_dist(px, py, a, b)
                if best is None or d < best[0]:
                    best = (d, q)
        return best
    rear_pred = lambda a, b: a[1] > 0 and b[1] > 0
    side_pred = lambda a, b: abs(a[0] - b[0]) < abs(a[1] - b[1]) * 0.5
    probes = []
    for c in covers_of(s):
        ov = float(c.get("overhang_ft", 1.0))
        probes.append((("cover roof edge", (c["x0"] + c["x1"]) / 2, c["y1"] + ov), rear_pred))
    deck_front = max(p[1] for p in out)
    xf = [p[0] for p in out if abs(p[1] - deck_front) < 0.01]
    if not covers_of(s):
        # the outline corner nearest the rear line (a shaped deck's front-edge midpoint can sit off the deck)
        best_v = min(out, key=lambda q: (nearest(q[0], q[1], rear_pred) or (9e9, None))[0])
        probes.append((("deck edge", best_v[0], best_v[1]), rear_pred))
    lx_, rx_ = min(p[0] for p in out), max(p[0] for p in out)
    probes.append((("deck edge", lx_, max(p[1] for p in out if abs(p[0] - lx_) < 0.01) / 2), lambda a, b: side_pred(a, b) and (a[0] + b[0]) / 2 < lx_))
    probes.append((("deck edge", rx_, max(p[1] for p in out if abs(p[0] - rx_) < 0.01) / 2), lambda a, b: side_pred(a, b) and (a[0] + b[0]) / 2 > rx_))
    for (lab, px, py), pred in probes:
        nb = nearest(px, py, pred)
        if not nb:
            continue
        d, (qx, qy) = nb
        o.append(LN(X(px), Y(py), X(qx), Y(qy), "#b3261e", 0.9))
        o.append(C(X(px), Y(py), 1.8, "#b3261e", "none", 0))
        mx, my = (X(px) + X(qx)) / 2, (Y(py) + Y(qy)) / 2
        o.append(R(mx - 30, my - 8, 60, 11, CREAM, "none", 0)); o.append(T(mx, my + 1, f"{ftin(round(d * 12))}", 8, 900, "middle", "#b3261e"))
    # lot line labels
    ll = sp.get("lot_lines") or {}
    if ll.get("rear") and sp.get("setback_offset"):
        re_ = [(a, b) for a, b in zip(par, par[1:] + par[:1]) if a[1] > 0 and b[1] > 0 and abs(b[0] - a[0]) > abs(b[1] - a[1])]
        if re_:
            a, b = max(re_, key=lambda e: math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1]))
            mx_, my_ = X(a[0] + (b[0] - a[0]) * 0.6), Y(a[1] + (b[1] - a[1]) * 0.6)
            ang = math.degrees(math.atan2(Y(b[1]) - Y(a[1]), X(b[0]) - X(a[0])))
            ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
            o.append(f'<g transform="rotate({ang:.1f} {mx_:.1f} {my_:.1f})">' + T(mx_, my_ + 12, ll["rear"], 7.2, 800, "middle", MUTE) + "</g>")
    elif ll.get("rear"):
        o.append(T(X(min(xs) + (max(xs) - min(xs)) * 0.72), Y(rear_y) + 13 + (sp.get("rear_label_dy", 0)), ll["rear"], 7.5, 800, "middle", MUTE))
    if ll.get("left"):
        o.append(T(X(min(xs)) - 6, Y((min(ys) + max(ys)) / 2), ll["left"], 7.5, 800, "middle", MUTE, rot=-90))
    if ll.get("right"):
        o.append(T(X(max(xs)) + 12, Y((min(ys) + max(ys)) / 2), ll["right"], 7.5, 800, "middle", MUTE, rot=90))
    # north arrow: bearing 0 in the plan frame
    if s.site.rear_azimuth_deg is not None:
        r_ = math.radians(s.site.rear_azimuth_deg)
        nx, ny = math.sin(r_), math.cos(r_)
        ax0, ay0 = 470, 60
        o.append(C(ax0, ay0, 22, CREAM, INK, 0.8))
        o.append(f'<polygon points="{ax0 + nx * 20:.1f},{ay0 + ny * 20:.1f} {ax0 - ny * 6:.1f},{ay0 + nx * 6:.1f} {ax0 + nx * -8:.1f},{ay0 + ny * -8:.1f} {ax0 + ny * 6:.1f},{ay0 - nx * 6:.1f}" fill="{INK}"/>')
        o.append(T(ax0 + nx * 31, ay0 + ny * 31 + 4, "N", 11, 900, "middle"))
    lg = ([("#1c1c1e", "dash", "new roof cover — roof edge incl. overhang")] if covers_of(s) else []) + [(FILL["deck"], "fill", f"new deck ({s.decking.brand}, {'steel' if s.framing.system == 'steel' else 'wood'} frame)"), ("#b3261e", "line", "distance to the lot line (GIS)")]
    for k_, (col, kind, lab) in enumerate(lg):
        lx, ly = 250, 588 + k_ * 12
        if kind == "fill":
            o.append(R(lx, ly - 7, 14, 8, col, INK, 0.5))
        elif kind == "dash":
            o.append(R(lx, ly - 7, 14, 8, "none", col, 1.0, 'stroke-dasharray="3 2"'))
        else:
            o.append(LN(lx, ly - 3, lx + 14, ly - 3, col, 1.2))
        o.append(T(lx + 20, ly, lab, 7.5, 600))
    # scale bar (20')
    o.append(R(40, 590, 20 * sc, 5, INK, INK, 0.5)); o.append(R(40 + 10 * sc, 590, 10 * sc, 5, CREAM, INK, 0.5))
    o.append(T(40, 606, "0", 7, 700)); o.append(T(40 + 20 * sc, 606, "20'", 7, 700, "middle"))
    # right column
    x2 = 540
    yy = 24
    o.append(T(x2, yy, "PARCEL", 9, 800, fill=GOLD)); yy += 16
    for ln in [f"{s.site.address}, {s.site.city} {s.site.state} {s.site.zip}"] + list(sp.get("info") or []):
        o.append(T(x2, yy, ln, 8.5, 500)); yy += 12
    o.append(T(x2, yy + 10, "LOT COVERAGE", 9, 800, fill=GOLD)); yy += 26
    for k, v in sp.get("coverage") or []:
        o.append(T(x2, yy, k, 8, 700)); o.append(T(x2 + 445, yy, textwrap.shorten(v, 54, placeholder="…"), 8, 500, "end")); yy += 12
    o.append(T(x2, yy + 10, "SETBACKS", 9, 800, fill=GOLD)); yy += 26
    sb = [f"Decks are 30\" or less above grade — not held to the principal setbacks (city deck handout)",
          f"Roof covers: part of the principal structure — they replace the two existing covers in place; the 2024 aerial shows the existing main roof ~1'-5\" shallower: field-verify the existing post line",
          (ref.get("label") or "")]
    if sp.get("setback_notes"):
        sb = list(sp["setback_notes"])
    sb += [f"Measured (red): to the nearest lot line from the new work — GIS, not survey"]
    for ln in [x for x in sb if x]:
        for w in textwrap.wrap(ln, 80):
            o.append(T(x2, yy, w, 8, 500)); yy += 11.5
    o.append(T(x2, yy + 10, "SITE WORK", 9, 800, fill=GOLD)); yy += 26
    work = ["Remove the two decks, the two roof covers and the box step; haul off", "Diamond Pier foundations (no excavation spoils), 6-mil poly + 2\" gravel under the decks",
            ("New concrete landing pad at the stair" if any(st_.landing == "concrete pad" for st_ in s.stairs) else "Stair lands on grade (no pad)"), "Roof drainage: covers shed to grade at the low eave, away from the house", "Call 811 before the piers; protect the lawn and the owner's blinds"]
    for ln in (sp.get("site_work") or work):
        for j, w in enumerate(textwrap.wrap(ln, 84)):
            o.append(T(x2, yy, ("· " if j == 0 else "  ") + w, 8, 500)); yy += 11.5
    if sp.get("source"):
        yy += 6
        for w in textwrap.wrap(sp["source"], 86):
            o.append(T(x2, yy, w, 7.2, 500, fill=MUTE)); yy += 10
    return sheet("C-100", "Site plan", "Parcel, existing house, " + ("new decks and roof covers" if covers_of(s) else "the new deck") + ", distances to the lot lines, setbacks", o, "Plan · approx. 1\" = 20' at full size · GIS lines, not a survey", meta)


def sheet_covers(L: Layout, S: Scene, t, meta) -> Optional[str]:
    """A-401 roof covers: a framing plan of each cover (ledger, rafters, beam, posts, panels) and a section through each
    (deck, clear heights at the house and the beam, pitch, overhang, Hardie soffit / fascia, blinds, posts on the piers)."""
    s = L.spec
    from .spec import covers_of
    from .takeoff import cover_posts_x
    cs = covers_of(s)
    if not cs:
        return None
    o = []
    n = len(cs)
    colw = 940 / n
    zt = s.geometry.height_in / 12.0
    for i, c in enumerate(cs):
        ox = 30 + i * colw
        ov = float(c.get("overhang_ft", 1.0))
        x0, x1, y0, y1 = c["x0"], c["x1"], c["y0"], c["y1"]
        hi, lo = float(c.get("clear_high_in") or 100), float(c.get("clear_low_in") or 88)
        pitch = (hi - lo) / max(0.1, (y1 - y0))
        from .catalog import actual as _act
        bdi = _act(c.get("beam", "(2)2x10").split(")")[-1])[1]
        o.append(T(ox, 18, f"{c['name'].upper()} — PLAN", 10, 900, fill=GOLD))
        Xp, Yp, scp = plan_xform(x0 - 1.5, x1 + 1.5, y0 - 1.0, y1 + ov + 1.5, ox, 38, colw - 40, 215)
        o.append(R(Xp(x0 - 1.5), Yp(y0 - 1.0), (x1 - x0 + 3) * scp, 1.0 * scp, FILL["house"], INK, 1.0))
        o.append(T(Xp((x0 + x1) / 2), Yp(y0 - 1.0) - 4, f"HOUSE WALL — {c.get('ledger', '2x10')} ledger, LedgerLOK 6\" 2 rows @ 16\"", 7, 800, "middle", MUTE))
        o.append(R(Xp(x0 - 0.4), Yp(y0), (x1 - x0 + 0.8) * scp, (y1 - y0 + ov) * scp, "#2b2b2e", INK, 1.0, 'fill-opacity="0.12"'))
        k = 0.0
        while x0 - 0.4 + k <= x1 + 0.4 + 0.01:
            xr = min(x0 - 0.4 + k, x1 + 0.4)
            o.append(LN(Xp(xr), Yp(y0), Xp(xr), Yp(y1 + ov), "#8a6d2a", 0.8))
            k += 16 / 12
        o.append(R(Xp(x0 - 0.4), Yp(y1 - 0.25), (x1 - x0 + 0.8) * scp, 0.5 * scp, FILL["timber_dk"], INK, 0.8))
        for px in cover_posts_x(c):
            o.append(R(Xp(px - 0.23), Yp(y1 - 0.23), 0.46 * scp, 0.46 * scp, INK, INK, 0.5))
        dim_h(o, Xp, Yp(y1 + ov) + 18, x0 - 0.4, x1 + 0.4, ftin((x1 - x0 + 0.8) * 12) + " roof", up=False)
        posts = cover_posts_x(c)
        for a, b in zip(posts, posts[1:]):
            dim_h(o, Xp, Yp(y0) + 12, a, b, ftin((b - a) * 12) + " posts", 7.5)
        dim_v(o, Yp, Xp(x1 + 0.4) + 16, y0, y1, ftin((y1 - y0) * 12), left=False)
        dim_v(o, Yp, Xp(x1 + 0.4) + 16, y1, y1 + ov, ftin(ov * 12) + " ovh", 7, left=False)
        o.append(T(Xp((x0 + x1) / 2), Yp((y0 + y1) / 2), f"2x8 wood rafters @ 16\" OC · slope {pitch:.2f}:12 to the yard · {c.get('beam', '(2)2x10')} wood beam", 7.5, 800, "middle"))
        o.append(T(Xp((x0 + x1) / 2), Yp((y0 + y1) / 2) + 11, f"{s.extras.cover_roof_color or ''} standing seam, mechanically seamed".strip(), 7.5, 600, "middle"))
        # section
        sy0 = 300
        o.append(T(ox, sy0, f"{c['name'].upper()} — SECTION", 10, 900, fill=GOLD))
        top_z = zt + (hi + bdi + 7.25) / 12 + 0.6
        Xs, Zs, scs = elev_xform(y0 - 2.0, y1 + ov + 3.0, -1.8, top_z, ox, sy0 + 8, colw - 40, 205)
        o.append(R(Xs(y0 - 2.0), Zs(0), (y1 + ov + 5) * scs, 1.8 * scs, "#cdbf9f", "none", 0))
        o.append(LN(Xs(y0 - 2.0), Zs(0), Xs(y1 + ov + 3), Zs(0), INK, 1.2))
        o.append(R(Xs(y0 - 2.0), Zs(top_z - 0.1), 2.0 * scs, (top_z - 0.1) * scs, FILL["house"], INK, 1.2))
        o.append(T(Xs(y0 - 1.0), Zs(top_z / 2), "HOUSE", 8, 900, "middle", MUTE, rot=-90))
        o.append(R(Xs(y0), Zs(zt), (y1 - y0 + 0.4) * scs, (1.0 / 12 + actual(s.framing.joist_size)[1] / 12) * scs, FILL["deck"], INK, 0.8))
        o.append(T(Xs(y0) + 4, Zs(zt) + 10, f"DECK {ftin(s.geometry.height_in)} above grade", 6.5, 800, fill="#f3ead9"))
        zb_hi, zb_lo = zt + hi / 12, zt + lo / 12
        o.append(R(Xs(y0), Zs(zb_hi + bdi / 12), 0.13 * scs, bdi / 12 * scs, FILL["timber_dk"], INK, 0.6))
        o.append(R(Xs(y1 - 0.25), Zs(zb_lo + bdi / 12), 0.5 * scs, bdi / 12 * scs, FILL["timber_dk"], INK, 0.6))
        o.append(R(Xs(y1 - 0.23), Zs(zb_lo), 0.46 * scs, (zb_lo - 0.45) * scs, FILL["timber"], INK, 0.6))
        o.append(R(Xs(y1 - 0.45), Zs(0.45), 0.9 * scs, (0.45 + 0.4) * scs, FILL["concrete"], INK, 0.6))
        o.append(T(Xs(y1) + 26, Zs(0.1) + 4, "Diamond Pier (shared with the deck beam)" if c.get("footing") == "deck_pier" else "Diamond Pier", 7, 700))
        for k_ in (-1, 1):
            o.append(LN(Xs(y1), Zs(0), Xs(y1 + k_ * 1.6), Zs(-1.7), INK, 0.7))
        zr0, zr1 = zb_hi + bdi / 12, zb_lo + bdi / 12 - pitch / 12 * ov
        o.append(PG([(Xs(y0), Zs(zr0)), (Xs(y1 + ov), Zs(zr1)), (Xs(y1 + ov), Zs(zr1 + 7.25 / 12)), (Xs(y0), Zs(zr0 + 7.25 / 12))], FILL["timber"], INK, 0.7))
        o.append(LN(Xs(y0), Zs(zr0 + 8.5 / 12), Xs(y1 + ov + 0.1), Zs(zr1 + 8.5 / 12), "#1c1c1e", 2.6))
        o.append(LN(Xs(y0), Zs(zr0 - 0.03), Xs(y1 + ov), Zs(zr1 - 0.03), "#efe9dc", 2.0))
        o.append(R(Xs(y1 + ov), Zs(zr1 + 8.5 / 12), 0.1 * scs, 8.5 / 12 * scs, "#f2efe8", INK, 0.6))
        dim_v(o, Zs, Xs(y0) + 14, zt, zb_hi, f"{hi:g}\" clear", 7.5, left=False)
        dim_v(o, Zs, Xs(y1) - 12, zt, zb_lo, f"{lo:g}\" clear", 7.5)
        dim_h(o, Xs, Zs(-1.4), y0, y1, ftin((y1 - y0) * 12) + " to the post line", 7.5, up=False)
        if c.get("blinds"):
            o.append(C(Xs(y1 + 0.05), Zs(zb_lo - 0.15), 2.6, "#7a5c45", INK, 0.5))
            o.append(R(Xs(y1 + 0.02), Zs(zb_lo - 0.2), 2.0, (zb_lo - 0.2 - zt) * scs, "#7a5c45", "none", 0, 'fill-opacity="0.55"'))
            o.append(T(Xs(y1) + 6, Zs(zt + 2.5), "owner's roll-down blinds,", 7, 700))
            o.append(T(Xs(y1) + 6, Zs(zt + 2.5) + 9, "rehung on the new beam", 7, 700))
        notes = [f"Standing seam 24 ga, 16\" panels, 1-1/2\" mechanical (double-lock) seam — rated for {pitch:.2f}:12 · high-temp ice & water underlayment over 7/16\" OSB",
                 "Headwall flashing counterflashed into the siding · color-matched eave / rake trim · snow bar across the low eave",
                 f"HardieSoffit cedarmill ceiling · HardieTrim fascia + rakes ({s.extras.hardie_color or 'color TBD'}) · H2.5AZ at every rafter · post caps per D-503",
                 f"6x6 {post_words(s)} posts on {post_base_sku(s)} bases on the Diamond Pier bolt · {'BC46Z' if c.get('beam', '').startswith('4x') else 'AC6Z'} cap to the {c.get('beam', '(2)2x10')} {'Douglas fir ' if c.get('beam', '').startswith('4x') else ''}beam · the engineer's uplift hold-down governs"]
        yy = sy0 + 236
        for ln in notes:
            for w in textwrap.wrap(ln, int(colw / 5.0)):
                o.append(T(ox, yy, w, 7.4, 500)); yy += 10
    return sheet("A-401", "Roof covers — plan + section", "Lean-to covers: ledger, rafters, beam, posts on the piers, clear heights, pitch, standing seam, Hardie, blinds", o,
                 "Plans and sections not to a common scale · dimensions govern · the stamped set governs", meta)


SHEET_INDEX = [("G-001", "General notes · design criteria"), ("A-001", "Isometric · renders"), ("S-100", "Foundation plan"), ("S-101", "Framing plan"),
               ("A-101", "Decking plan"), ("A-201", "Railing plan + elevation"), ("A-301", "Section + front elevation"), ("D-501", "Details"),
               ("T-400", "Build steps (build set)"), ("T-700", "Order + schedules (takeoff)")]
SHEET_INDEX_EXTRA = [("C-100", "Site plan"), ("A-401", "Roof covers — plan + section")]


def sheet_meta(L: Layout, customer: bool = False) -> dict:
    s = L.spec
    return dict(job_line=f"{s.job} · {s.site.address}, {s.site.city}".strip(" ,·"),
                rev_line=(f"GS Exterior Experts · {date.today().strftime('%B %d, %Y')} · Rev 0" if customer else f"GSX · Jade Pender 303-550-9558 · {date.today().strftime('%B %d, %Y')} · Rev 0 FOR REVIEW"),
                footer=("Design intent. The stamped engineering set governs structure, dimensions and locations. Field verify. Do not scale." if s.extras.engineered
                        else "Design intent per 2021 IRC R507 prescriptive. Field verify. Do not scale.") + (" Oil finish is an option; base timbers unfinished, end grain sealed." if s.is_timber and s.framing.finish != "oil" else ""))


def inch(v: float, frac: int = 8) -> str:
    """Inches to the nearest 1/frac: 68", 47 3/4", 160 7/8"."""
    n = round(v * frac)
    whole, rem = divmod(int(abs(n)), frac)
    sgn = "-" if n < 0 else ""
    if rem == 0:
        return f'{sgn}{whole}"'
    g = math.gcd(rem, frac)
    return f'{sgn}{whole} {rem // g}/{frac // g}"' if whole else f'{sgn}{rem // g}/{frac // g}"'


def chain_labels(pts, frac: int = 8) -> List[str]:
    """Labels for a chain of dimensions that add up: every point rounded from the chain's start, then differenced, as a
    tape read from one end — the segments always sum to the overall (rounding each segment alone can drift 1/8\")."""
    q = [round((p - pts[0]) * frac) / frac for p in pts]
    return [inch(b - a, frac) for a, b in zip(q, q[1:])]


def sheet_dimensions(L: Layout, S: Scene, t, meta) -> Optional[str]:
    """A-100: the deck outline with every side in inches, chain dimensions along the house and the front, the depths,
    the stairs, built-ins and dividers — inches throughout, the overall width in feet and inches."""
    if not S.meta.get("outline"):
        return None
    s = L.spec
    P = [(float(a) * 12, float(b) * 12) for a, b in S.meta["outline"]]          # inches, plan frame
    n = len(P)
    xs = [p[0] for p in P]; ys = [p[1] for p in P]
    Wd, Dp = max(xs) - min(xs), max(ys) - min(ys)
    o = []
    top = []                                             # labels drawn last, over the strips and fills
    # inches -> sheet: deck left end at px 70, house line at y 110
    sc = min(590 / Wd, 330 / Dp)
    X = lambda x: 92 + (x - min(xs)) * sc
    Y = lambda y: 122 + (y - min(ys)) * sc
    kinds = {}
    for e in L.outline_edges or []:
        kinds[e.name] = e
    rail_edges = set(s.railing.edges or []) if s.railing and s.railing.edges else set()
    bench_paths = [b.get("path") for b in (s.geometry.benches or [])]
    plant_paths = [b.get("path") for b in (s.geometry.planters or [])]
    def on_path(a, b, paths):
        for pth in paths:
            if not pth:
                continue
            q = [(u * 12, v * 12) for u, v in pth]
            for (u0, v0), (u1, v1) in zip(q, q[1:]):
                if (math.hypot(a[0] - u0, a[1] - v0) < 3 and math.hypot(b[0] - u1, b[1] - v1) < 3) or (math.hypot(a[0] - u1, a[1] - v1) < 3 and math.hypot(b[0] - u0, b[1] - v0) < 3):
                    return True
        return False
    stair_by_edge = {st.side: st for st in s.stairs}
    # the house wall and the bay (the polygon's sides that lie on the house)
    o.append(LN(X(min(xs)) - 40, Y(0), X(max(xs)) + 40, Y(0), "#8a8172", 5))
    o.append(T(X(min(xs)) - 36, Y(0) - 44, "HOUSE (rear wall) — deck to house along the top chain", 8, 800, fill="#8a8172"))
    o.append(PG([(X(x), Y(y)) for x, y in P], "#efe3cc", INK, 2.2))
    rows = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        L_ = math.hypot(b[0] - a[0], b[1] - a[1])
        if L_ < 0.5:
            continue
        name = f"edge:{i + 1}"
        e = kinds.get(name)
        house_side = e is not None and not e.exposed
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        ux, uy = (b[0] - a[0]) / L_, (b[1] - a[1]) / L_
        nx, ny = uy, -ux                                     # outward for the polygon's winding (house at the top)
        if _poly_area_in(P) > 0:
            nx, ny = -nx, -ny
        what = ("house / ledger" if (house_side and abs(a[1]) < 0.5 and abs(b[1]) < 0.5) else ("house — bay face" if house_side else
                ("RAIL" if name in rail_edges else ("bench" if on_path((a[0] / 12, a[1] / 12), (b[0] / 12, b[1] / 12), []) or on_path(a, b, bench_paths) else
                 ("planter" if on_path(a, b, plant_paths) else "open")))))
        if name in stair_by_edge:
            st = stair_by_edge[name]
            what += f" + stair {inch(st.width_in)} wide"
        ang = math.degrees(math.atan2(Y(b[1]) - Y(a[1]), X(b[0]) - X(a[0])))
        if ang > 90: ang -= 180
        if ang < -90: ang += 180
        builtin = what.startswith(("bench", "planter"))
        covered = ((abs(a[0] - b[0]) < 0.5 and (abs(a[0] - min(xs)) < 0.5 or abs(a[0] - max(xs)) < 0.5))
                   or (abs(a[1] - b[1]) < 0.5 and abs(a[1] - max(ys)) < 0.5))          # a side chain already carries it
        if not house_side and not (builtin and covered):     # house sides read off the chain along the house
            k_ = -14 if builtin else 13                      # a bench / planter fills the inside: label it outside
            tx, ty = X(mx) + nx * k_, Y(my) + ny * k_ + 3
            top.append(T(tx, ty, inch(L_), 9.5, 900, "middle", INK, rot=ang))
            if name in rail_edges:                           # the owner's sketch marks rail with a blue R: so does this sheet
                segs_ = [(0.0, L_)]
                if name in stair_by_edge:                    # rail only on the stubs beside the stair
                    st_ = stair_by_edge[name]
                    p0_ = float(st_.position_in or 0.0)
                    segs_ = [(0.0, p0_), (p0_ + float(st_.width_in), L_)]
                for s0_, s1_ in segs_:
                    if s1_ - s0_ > 0.5:
                        o.append(LN(X(a[0] + ux * s0_), Y(a[1] + uy * s0_), X(a[0] + ux * s1_), Y(a[1] + uy * s1_), "#1f4fb5", 3.2))
                top.append(T(X(mx) + nx * 27, Y(my) + ny * 27 + 4, "R", 11, 900, "middle", "#1f4fb5"))
            kn = 36 if builtin else -22                      # the side number: inside past a bench / planter strip, else outside
            o.append(T(X(mx) + nx * kn, Y(my) + ny * kn + 3, str(i + 1), 7, 800, "middle", GOLD))
        rows.append((i + 1, inch(L_), ftin(L_), what))
    # chain dimensions: along the front (every corner's x) and along the house (where the deck meets it)
    fx = sorted(set(round(x, 2) for x, y in P if y > max(ys) - 40 or x in (min(xs), max(xs))))
    hx = sorted(set(round(x, 2) for x, y in P if abs(y) < 0.5) | {round(min(xs), 2), round(max(xs), 2)})
    yb = Y(max(ys)) + 40
    for (xa, xb), lab in zip(zip(fx, fx[1:]), chain_labels(fx)):
        dim_h(o, X, yb, xa, xb, lab, 8, up=True)
    dim_h(o, X, yb + 30, min(xs), max(xs), f"{inch(Wd)} = {ftin(Wd)} overall", 10.5, up=False)
    yt = Y(0) - 26
    for (xa, xb), lab in zip(zip(hx, hx[1:]), chain_labels(hx)):
        dim_h(o, X, yt, xa, xb, lab, 8, up=True)
    # the bay (house sides off the wall line): its corners along x, and how far it stands out
    bay = [(x, y) for x, y in P if 0.5 < y < 60 and any(abs(y - y2) < 0.5 and abs(x - x2) > 1 for x2, y2 in P)]
    hpts = [(x, y) for x, y in P if abs(y) < 0.5]
    if bay:
        by_ = bay[0][1]
        bxs = sorted(set(round(x, 2) for x, y in bay))
        x_l = max((x for x, y in hpts if x < bxs[0]), default=None); x_r = min((x for x, y in hpts if x > bxs[-1]), default=None)
        if x_l is not None and x_r is not None:
            chain = [x_l] + bxs + [x_r]
            for (xa, xb), lab in zip(zip(chain, chain[1:]), chain_labels(chain)):
                dim_h(o, X, Y(by_) + 16, xa, xb, lab, 7, up=False)
            dim_v(o, Y, X(bxs[0]) + 10, 0, by_, inch(by_), 6.5, left=False)
            o.append(T((X(x_l) + X(x_r)) / 2, Y(by_) + 40, "BOX BAY (house) — deck runs around it", 7, 800, "middle", "#8a8172"))
    # depths: the left end, the deepest corners, the centre front
    def depth_at(xq):
        hits = [y for (x0_, y0_), (x1_, y1_) in zip(P, P[1:] + P[:1]) for y in [y0_, y1_] if False]
        return max((y for x, y in P if abs(x - xq) < 0.5), default=None)
    zfront = sorted(set(round(y, 2) for x, y in P))
    dim_v(o, Y, X(min(xs)) - 78, 0, max(ys), f"{inch(max(ys))} deep", 9, left=True)
    left_pts = sorted(set(round(y, 2) for x, y in P if abs(x - min(xs)) < 0.5) | {0.0, round(max(ys), 2)})
    for (ya, yb_), lab in zip(zip(left_pts, left_pts[1:]), chain_labels(left_pts)):
        dim_v(o, Y, X(min(xs)) - 22, ya, yb_, lab, 7.5, left=True)
    right_pts = sorted(set(round(y, 2) for x, y in P if abs(x - max(xs)) < 0.5) | {0.0, round(max(ys), 2)})
    for (ya, yb_), lab in zip(zip(right_pts, right_pts[1:]), chain_labels(right_pts)):
        dim_v(o, Y, X(max(xs)) + 16, ya, yb_, lab, 7.5, left=False)
    # the centre notch depth
    notch = [(x, y) for x, y in P if 0.5 < y < max(ys) - 0.5 and min(xs) + 1 < x < max(xs) - 1]
    if notch:
        ny_ = min(y for x, y in notch if y > Dp * 0.5) if any(y > Dp * 0.5 for x, y in notch) else None
        if ny_:
            xs_n = [x for x, y in notch if abs(y - ny_) < 0.5]
            xm = (min(xs_n) + max(xs_n)) / 2
            o.append(LN(X(xm) - 30, Y(0), X(xm) - 30, Y(ny_), MUTE, 0.6, "3 3"))
            o.append(T(X(xm) - 33, (Y(0) + Y(ny_)) / 2 + 30, f"{inch(ny_)} house to the center front", 7.5, 700, "middle", MUTE, rot=-90))
    # dividers
    for k_, dx in enumerate(s.decking.divider_x_ft or []):
        xi = float(dx) * 12
        y_end = max((y for x, y in P if abs(x - xi) < 1.0), default=Dp)
        o.append(LN(X(xi), Y(0), X(xi), Y(y_end), GOLD, 1.4, "6 3"))
        o.append(T(X(xi) + (-4 if k_ == 0 else 4), Y(y_end) - 10, f"divider {inch(xi)} from the left end", 7, 700, "end" if k_ == 0 else "start", "#9a7414"))
    # stairs and the box step: their footprints from the scene treads
    for b in S.boxes:
        if b.kind == "tread":
            o.append(R(X(b.x0 * 12), Y(b.y0 * 12), (b.x1 - b.x0) * 12 * sc, (b.y1 - b.y0) * 12 * sc, "#d7c3a0", INK, 0.6))
    for st in s.stairs:
        e = kinds.get(st.side)
        if e is None:
            continue
        Le = math.hypot(e.x1 - e.x0, e.y1 - e.y0)
        p0 = float(st.position_in or 0.0); p1 = p0 + float(st.width_in)
        if abs(e.y1 - e.y0) < 0.5:          # a front side: chain under it
            xa_, xb_ = min(e.x0, e.x1), max(e.x0, e.x1)
            yy_ = Y(e.y0) + 14
            pts_ = [xa_] + [v for v in (xa_ + p0, xa_ + p1) if xa_ + 0.5 < v < xb_ - 0.5] + [xb_]
            for (a_, b_), lab in zip(zip(pts_, pts_[1:]), chain_labels(pts_)):
                dim_h(o, X, yy_, a_, b_, lab, 7, up=False)
        elif abs(e.x1 - e.x0) < 0.5:        # a side wall: chain beside it
            ya_, yb_ = min(e.y0, e.y1), max(e.y0, e.y1)
            xx_ = X(e.x0) - 46
            pts_ = [ya_] + [v for v in (ya_ + p0, ya_ + p1) if ya_ + 0.5 < v < yb_ - 0.5] + [yb_]
            for (a_, b_), lab in zip(zip(pts_, pts_[1:]), chain_labels(pts_)):
                dim_v(o, Y, xx_, a_, b_, lab, 7, left=True)
    for st, sl in zip(s.stairs, L.stairs):
        g = sl.geo
        lab = (f"{'BOX STEP' if getattr(sl, 'build', '') == 'box' else 'STAIR'} {inch(st.width_in)} wide · {g.risers} risers @ {inch(g.riser_in, 16)} · "
               f"{g.treads} tread{'s' if g.treads != 1 else ''} @ {inch(g.tread_in, 16)}")
        e = kinds.get(st.side)
        if e is not None:
            mx = (e.x0 + e.x1) / 2; my = (e.y0 + e.y1) / 2
            if abs(e.y1 - e.y0) < 0.5:
                o.append(T(X(mx), Y(my) + 52, lab, 7.5, 800, "middle", "#5a4520"))
            else:
                o.append(T(X(mx) - 62, Y(my), lab, 7.2, 800, "middle", "#5a4520", rot=-90))
    # built-ins: benches and the planter as 17" strips inside their sides
    for b in S.boxes:
        if (b.tag or "").startswith(("bench seat", "planter")) and b.kind in ("board", "border", "fascia") and False:
            pass
    for nm, items in (("BENCH", s.geometry.benches or []), ("PLANTER", s.geometry.planters or [])):
        for it in items:
            pth = [(u * 12, v * 12) for u, v in it.get("path", [])]
            dep = float(it.get("depth_in", it.get("width_in", 17)))
            for (u0, v0), (u1, v1) in zip(pth, pth[1:]):
                Lb = math.hypot(u1 - u0, v1 - v0)
                if Lb < 1:
                    continue
                ux, uy = (u1 - u0) / Lb, (v1 - v0) / Lb
                # inward = toward the polygon centroid
                cx_, cy_ = sum(xs) / n, sum(ys) / n
                nx, ny = -uy, ux
                if (cx_ - u0) * nx + (cy_ - v0) * ny < 0:
                    nx, ny = -nx, -ny
                quad = [(u0, v0), (u1, v1), (u1 + nx * dep, v1 + ny * dep), (u0 + nx * dep, v0 + ny * dep)]
                o.append(PG([(X(a), Y(b_)) for a, b_ in quad], "#cdb48f", INK, 0.6))
                ang = math.degrees(math.atan2(Y(v1) - Y(v0), X(u1) - X(u0)))
                if ang > 90: ang -= 180
                if ang < -90: ang += 180
                o.append(T(X((u0 + u1) / 2 + nx * dep / 2), Y((v0 + v1) / 2 + ny * dep / 2) + 3,
                           f"{nm} {inch(dep)} deep" + (f" x {inch(float(it.get('seat_in', 17)))} high" if nm == "BENCH" else f" x {inch(float(it.get('height_in', 17)))} high"),
                           6.5, 800, "middle", "#4a3a20", rot=ang))
    ds = getattr(s.geometry, "door_step", None)
    if ds:
        x0d, x1d = float(ds["x0"]) * 12, float(ds["x1"]) * 12
        dd = float(ds.get("depth_in", 21))
        o.append(R(X(x0d), Y(0), (x1d - x0d) * sc, dd * sc, "#e0cfae", INK, 0.6))
        o.append(T(X((x0d + x1d) / 2), Y(dd / 2) + 3, f"DOOR STEP {inch(x1d - x0d)} x {inch(dd)} · {inch(float(ds.get('rise_in', 7)))} up", 6.5, 800, "middle", "#4a3a20"))
    # the side table
    tx0 = 752
    o.append(T(tx0, 24, "EVERY SIDE — INCHES", 9, 800, fill=GOLD))
    yy = 40
    o.append(T(tx0, yy, "#", 7.5, 800)); o.append(T(tx0 + 22, yy, "inches", 7.5, 800)); o.append(T(tx0 + 86, yy, "ft-in", 7.5, 800)); o.append(T(tx0 + 140, yy, "what", 7.5, 800))
    yy += 12
    for k, li, fi, what in rows:
        o.append(T(tx0, yy, str(k), 8, 700, fill=GOLD)); o.append(T(tx0 + 22, yy, li, 8, 800)); o.append(T(tx0 + 86, yy, fi, 7.5, 500, fill=MUTE))
        o.append(T(tx0 + 140, yy, textwrap.shorten(what, 30, placeholder="…"), 7.2, 500)); yy += 11.5
    yy += 10
    for ln in [f"Overall: {inch(Wd)} = {ftin(Wd)} wide x {inch(Dp)} = {ftin(Dp)} deep (house to the outer front corners).",
               f"Deck surface {inch(s.geometry.height_in)} above the stair landing grade; picture frame overhangs the fascia 1\".",
               "Sides measured at the outside face of the picture frame / fascia line, corner to corner.",
               "Verify in the field before ordering: the house line, the bay and the rear-lot-line distance (see C-100)."]:
        for w_ in textwrap.wrap(ln, 44):
            o.append(T(tx0, yy, w_, 7.4, 400)); yy += 10
        yy += 3
    o += top
    return sheet("A-100", "Dimension plan — inches", "Every side of the deck in inches, the overall width in feet and inches", o,
                 "Plan · not to scale · house at the top · inches govern", meta)


def _poly_area_in(P) -> float:
    return 0.5 * sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))


def all_sheets(L: Layout, t, flags, scene: Optional[Scene] = None, customer: bool = False) -> List[Tuple[str, str, str]]:
    """[(num, title, svg)] — everything except A-001 (renders) and T-400 (build steps), which the build set adds.
    customer=True leaves the internal flags block off G-001."""
    if customer:
        flags = None
    S = scene or build_scene(L)
    if any(getattr(b, "layer", "") == "site" for b in S.boxes):      # the yard model is for the 3D views, not the drawing sheets
        import dataclasses as _dc
        S = _dc.replace(S, boxes=[b for b in S.boxes if getattr(b, "layer", "") != "site"])
    _MAT_COLORS.clear()
    for k in ("deck", "border", "drink", "fascia"):
        if k in S.materials:
            _MAT_COLORS[k] = S.materials[k]["color"]
    FILL["deck"] = _MAT_COLORS.get("deck", FILL["deck"]); FILL["border"] = _MAT_COLORS.get("border", FILL["border"])
    meta = sheet_meta(L, customer=customer)
    _STEEL["on"] = L.spec.framing.system == "steel"
    out = [("G-001", "General notes · design criteria", "")]              # built last, from the sheets actually in the set
    site = sheet_site(L, S, t, meta)
    if site:
        out.append(("C-100", "Site plan", site))
    dims = sheet_dimensions(L, S, t, meta)
    if dims:
        out.append(("A-100", "Dimension plan — inches", dims))
    out += [("A-002", "Isometric — assembled, labeled", sheet_iso_assembled(L, S, t, meta)),
            ("A-003", "Isometric — exploded, labeled", sheet_iso_exploded(L, S, t, meta)),
            ("S-100", "Foundation plan", sheet_foundation(L, S, meta)),
            ("S-101", "Framing plan", sheet_framing(L, S, t, meta)),
            ("S-102", "Structure isometric, labeled", sheet_iso_structure(L, S, t, meta)),
            ("A-101", "Decking plan", sheet_decking(L, S, t, meta))]
    if L.rail:
        out.append(("A-201", "Railing plan + elevation", sheet_rail(L, S, t, meta)))
    out.append(("A-202", "Elevations", sheet_elevations(L, S, t, meta)))
    out.append(("A-301", "Section + front elevation", sheet_section(L, S, t, meta)))
    cov = sheet_covers(L, S, t, meta)
    if cov:
        out.append(("A-401", "Roof covers — plan + section", cov))
    cx = sheet_iso_covers(L, S, t, meta)
    if cx:
        out.append(("A-402", "Roof covers — exploded isometric, labeled", cx))
    out.append(("D-501", "Details", sheet_details_steel(L, S, t, meta) if L.spec.framing.system == "steel" else sheet_details(L, S, t, meta)))
    if L.spec.framing.system == "steel":
        out.append(("D-502", "Connection details — steel frame", sheet_details_steel_connections(L, S, t, meta)))
    elif L.spec.framing.system == "dimensional" and getattr(L.spec.extras, "connection_details", False):
        out.append(("D-502", "Connection details — frame", sheet_details_wood_connections(L, S, t, meta)))
        out.append(("D-504", "Connection details — deck edge, rail, lateral", sheet_details_edge_rail(L, S, t, meta)))
    if L.spec.geometry.covers:
        dc = sheet_details_cover_connections(L, S, t, meta)
        if dc:
            out.append(("D-503", "Connection details — roof covers", dc))
    index = [("G-001", "General notes · design criteria")]
    for num, ttl, _ in out[1:]:
        if num == "A-002":
            index.append(("A-001", "Isometric · renders"))
        index.append((num, ttl))
    index += [("T-400", "Build steps (build set)"), ("T-700", "Order + schedules (takeoff)")]
    out[0] = ("G-001", "General notes · design criteria", sheet_notes(L, S, t, flags, meta, index=index))
    return out


# ------------------------------------------------------------------ labeled axonometrics (permit set)
def _axo_colors(S: Scene) -> Dict[str, str]:
    cols = {k: v.get("color", "#b8b2a6") for k, v in S.materials.items()}
    cols.update(house="#ece6da", roof="#4a4440", trim="#f4f1ea", concrete="#c9c4ba", steel="#3a3c40", galv="#a7adb2")
    return cols


_BUILT_IN = ("bench", "planter", "door step")       # board-kind boxes that are built-ins, not the deck field


def _a(word: str) -> str:
    """The article before a part number read letter by letter: 'an ABA66RZ', 'a PBS66'."""
    return "an" if word[:1].upper() in "AEFHILMNORSX" else "a"


def member_key(L: Layout, S: Scene, t) -> List[Tuple[str, Callable[[Box], bool], Tuple[float, float, float], str]]:
    """(label, which boxes, where on the box, pick) for every member the job has, in build order — the callout key."""
    s = L.spec
    steel = s.framing.system == "steel"
    dk = f"{s.decking.brand} {s.decking.collection} {s.decking.color}"
    hc = s.extras.hardie_color or ""
    post_sp = post_words(s)
    fr = s.framing
    bls = getattr(L, "beam_lines", None) or (L.frame.beams if L.frame else [])
    kinds = {b.kind for b in bls}
    caps = sorted({c for b in bls for c in (getattr(b, "cap_mid", None) or getattr(b, "cap", None),) if c})
    beam_lab = (f"{' / '.join(sorted({f'{b.size} {b.species}' for b in bls}))} {next(iter(kinds)) if len(kinds) == 1 else ''} beam{'s' if len(bls) > 1 else ''}".replace("  ", " ")
                + (f", {' / '.join(caps)} post caps" if caps else "")) if bls else "Beam"
    sp_ = f"{fr.joist_species} " if fr.joist_species else ""
    rule = ((getattr(t, "schedule", None) or {}).get("Ledger") or "")       # the takeoff's fastening rule, so the key and the order agree
    oc = re.search(r'staggered (\d+)" OC', rule)
    lf_ = (fr.ledger_fastener or "LedgerLOK").lower()
    led_lab = (f"{fr.ledger_size or fr.joist_size} ledger — "
               + ("LedgerLOK" if lf_.startswith("ledgerlok") else "1/2\" through-bolts" if "bolt" in lf_ else "1/2\" lags")
               + (f", 2 rows staggered {oc.group(1)}\" OC" if oc else "") + "; membrane + L-flashing")
    sts = []
    for ss, st in zip(s.stairs or [], L.stairs or []):
        nm = getattr(ss, "name", None) or ""
        if getattr(st, "build", "") == "box":
            sts.append(f"{nm or 'box step'}: {st.geo.risers} risers, framed box")
        else:
            oc = f" @ {st.width / max(1, st.stringers - 1):.0f}\" OC" if st.stringers > 1 else ""
            sts.append(f"{nm or 'stair'}: {st.geo.risers} risers, {getattr(ss, 'stringer_size', '') or '2x12'} stringers{oc}")
    stair_lab = ("; ".join(sts) + f"; {s.decking.collection} treads, closed risers") if sts else "Stair"
    from .spec import covers_of
    _cv0 = (covers_of(s) or [{}])[0]
    ks = [
        (f"Diamond Pier {L.frame.footing_model} — head + 4 driven pins (frost-protected, no excavation)", lambda b: b.kind == "footing" and "Diamond" in (b.tag or ""), (0.5, 0.5, 1.0), "first"),
        ((f"6x6 {post_words(s)} deck post on {post_base_sku(s)}, steel saddle to the boxed beam" if s.framing.steel_deck_post == "wood" else "3x3 galvanized HSS post stub on a pier-head bracket") if steel else f"{s.framing.post_size} {post_words(s) if s.framing.post_species else ''} post on {_a(post_base_sku(s))} {post_base_sku(s)} standoff base".replace("  ", " "), lambda b: b.kind == "post", (0.5, 0.5, 0.6), "first"),
        (f"4x4 {'DF #1' if s.framing.post_species.upper().startswith('DF') else ''} knee brace at 45°, both directions, through-bolted".replace("  ", " "), lambda b: b.kind == "brace", (0.5, 0.5, 0.5), "first"),
        ((f"Boxed CEMCO {s.framing.steel_joist} beam (2 C toe-to-toe, G90), flush" if steel else beam_lab), lambda b: b.kind == "beam", (0.3, 0.5, 1.0), "last"),
        ((f"CEMCO {s.framing.steel_joist} C-joist, G90, @ {L.frame.spacing:g}\" OC — clip angles each end" if steel
          else f"{fr.joist_size} {sp_}joist" + (f" ({fr.joist_grade})" if fr.joist_grade else "") + (f" @ {L.frame.spacing:g}\" OC" if L.frame else "") + (", joist tape" if fr.joist_tape else "")),
         lambda b: b.kind == "joist", (0.5, 0.6, 1.0), "mid"),
        ((f"CEMCO {s.framing.steel_track} track rim, G90 (caps the joist ends)" if steel
          else (f"Double {fr.joist_size} rim, plies laminated (RSS screws 2 rows @ 12\")" if fr.rim_plies > 1 else f"{fr.joist_size} rim")), lambda b: b.kind == "rim", (0.5, 0.5, 1.0), "last"),
        (("Steel ledger track + 3x3 ledger angle on the house rim, flashed" if steel
          else led_lab), lambda b: b.kind == "ledger", (0.4, 0.5, 1.0), "last"),
        (("Steel blocking at the breaker / picture-frame joists" if steel else f"{fr.joist_size} blocking — picture frame + divider rows"), lambda b: b.kind == "block", (0.5, 0.5, 1.0), "mid"),
        (f"{dk} field decking, hidden fasteners", lambda b: b.kind == "board" and not (b.tag or "").startswith(_BUILT_IN), (0.35, 0.5, 1.0), "mid"),
        (f"Picture frame + breaker boards — {dk}", lambda b: b.kind == "border", (0.5, 0.5, 1.0), "last"),
        ((f"HardieTrim skirt {hc}".strip() if s.extras.hardie_skirt else
          f"{s.decking.brand} {s.decking.collection} fascia, {s.decking.fascia_color or s.decking.color}, over the rim" if s.decking.fascia else "Fascia"),
         lambda b: b.kind == "fascia", (0.5, 0.5, 0.5), "last"),
        (f"Stair — steel stringers, {s.decking.collection} treads, closed risers, lands on grade" if steel else stair_lab, lambda b: b.kind in ("tread", "stringer"), (0.5, 0.5, 1.0), "first"),
        (f"{rail_name(s.railing.system)} rail, {s.railing.color}, {s.railing.height_in:g}\"" if (s.railing and L.rail) else "Rail", lambda b: b.kind in ("toprail",), (0.5, 0.5, 1.0), "mid"),
        (f"Built-in bench — 4x4 posts bolted through the rim, all wrapped in {dk}", lambda b: b.kind == "benchpost" or (b.tag or "").startswith("bench seat"), (0.5, 0.5, 1.0), "mid"),
        (f"Planter — treated 2x4 box, OSB, {dk} skin, picture-frame cap", lambda b: (b.tag or "").startswith("planter") and "soil" not in (b.tag or ""), (0.5, 0.5, 1.0), "mid"),
        ("Gravel over 6-mil poly under the decks", lambda b: b.kind == "gravel", (0.3, 0.6, 1.0), "first"),
        ("Box step bed — 4\" compacted 3/4\" crushed rock / road base", lambda b: b.kind == "stepbase", (0.5, 0.5, 1.0), "first"),
        (f"6x6 {post_sp} cover post on {post_base_sku(s)} (shared Diamond Pier)", lambda b: b.kind == "cpost", (0.5, 0.5, 0.45), "last"),
        (f"{_cv0.get('beam', '(2)2x10')} cover beam, " + ("Douglas fir, BC46Z cap" if _cv0.get('beam', '').startswith('4x') else "wood, AC6Z cap"), lambda b: b.kind == "cbeam", (0.7, 0.5, 0.5), "last"),
        (f"{_cv0.get('ledger', '2x10')} cover ledger, wood, LedgerLOK 6\" 2 rows, headwall flashed", lambda b: b.kind == "cledger", (0.5, 0.5, 0.5), "last"),
        ("2x8 rafters @ 16\" OC, wood, H2.5AZ at the beam", lambda b: b.kind == "rafter", (0.5, 0.5, 0.5), "mid"),
        ("7/16\" OSB roof sheathing", lambda b: b.kind == "sheath", (0.2, 0.5, 1.0), "last"),
        ("High-temp self-adhered underlayment", lambda b: b.kind == "underlay", (0.4, 0.5, 1.0), "last"),
        (f"{s.extras.cover_roof_color} standing seam, 24 ga, mechanically seamed".strip(), lambda b: b.kind == "ssroof", (0.7, 0.4, 1.0), "last"),
        ("Snow retention bar, clamped to the seams", lambda b: (b.tag or "") == "snow retention bar", (0.8, 0.5, 1.0), "last"),
        (f"HardieTrim fascia + rakes {hc}".strip(), lambda b: b.kind == "hardie", (0.5, 0.5, 0.5), "mid"),
        (f"HardieSoffit cedarmill ceiling {hc}".strip(), lambda b: b.kind == "soffit", (0.5, 0.5, 0.0), "last"),
        ("Existing roll-down blinds (stay)", lambda b: b.kind == "blind", (0.5, 0.5, 0.3), "last"),
    ]
    return [k for k in ks if any(k[1](b) for b in S.boxes)]


def _axo_sheet(num, title, sub, L, S, t, meta, boxes, explode=False, gaps=None, az=35.0, el=28.0, key=None, fit=None, note=""):
    from .axo import View, draw, anchor, callouts
    cols = _axo_colors(S)
    frame = (20, 6, 700, 600)
    o = [f'<defs><clipPath id="ax{num.replace("-", "")}"><rect x="{frame[0]}" y="{frame[1]}" width="{frame[2]}" height="{frame[3]}"/></clipPath></defs>']
    polys, to_sheet, sc = draw(boxes, cols, View(az, el), (frame[0] + 70, frame[1], frame[2] - 140, frame[3]), explode=explode, gaps=gaps, fit_boxes=fit)
    o.append(f'<g clip-path="url(#ax{num.replace("-", "")})">' + "".join(polys) + "</g>")
    key = key if key is not None else member_key(L, S, t)
    items = []
    for i, (lab, pred, where, pick) in enumerate(key, 1):
        q = anchor(boxes, pred, explode, gaps, pick, where)
        if q is not None:
            items.append((i, q, lab))
    o += callouts(items, to_sheet, frame)
    # the key
    kx = 735
    o.append(T(kx, 22, "KEY", 9, 800, fill=GOLD))
    yy = 38
    for i, q, lab in items:
        o.append(C(kx + 6, yy - 3, 6, GOLD, INK, 0.5)); o.append(T(kx + 6, yy, str(i), 6.8, 900, "middle"))
        for j, ln in enumerate(textwrap.wrap(lab, 40)[:4]):
            o.append(T(kx + 18, yy + j * 9.5, ln, 7.4, 600 if j == 0 else 400))
        yy += 9.5 * min(4, len(textwrap.wrap(lab, 40))) + 5
    if note:
        yy += 6
        for ln in textwrap.wrap(note, 46):
            o.append(T(kx, yy, ln, 7.2, 400, fill=MUTE)); yy += 9.5
    return sheet(num, title, sub, o, "Axonometric · not to scale · the model the plans are drawn from", meta)


def _house(b: Box) -> bool:
    """The house, drawn for context only: the simple wall blocks, or every part of a measured house model."""
    return b.kind in ("house", "roof", "trim") or getattr(b, "layer", "") == "house"


def sheet_iso_assembled(L: Layout, S: Scene, t, meta) -> str:
    bx = [b for b in S.boxes if b.kind not in ("ground", "glass", "stringer")]     # closed risers hide the stringers
    fit = [b for b in bx if not _house(b) or (b.tag or "") in ("snow retention bar",)]
    hidden = ("post", "beam", "joist", "rim", "ledger", "block", "gravel", "stepbase", "sheath", "underlay")
    key = [k for k in member_key(L, S, t) if not any(k[1](b) for b in S.boxes if b.kind in hidden)]
    return _axo_sheet("A-002", "Isometric — assembled, labeled", "Everything you see called out: piers, decking, picture frame, skirt, stair, roof covers, finishes", L, S, t, meta, bx, fit=fit, key=key,
                      note=("House shown for context only (no work). The CEMCO steel deck frame under the decking is called out on S-102 and A-003; cover framing is wood: 2x8 rafters, "
                            + ", ".join(f"{c_['name'].lower()} {c_.get('beam', '(2)2x10')} beam" for c_ in __import__('decktakeoff.spec', fromlist=['covers_of']).covers_of(L.spec)) + ", 6x6 Douglas fir posts.")
                      if L.spec.framing.system == "steel" else "House shown for context only (the deck work only). The frame under the decking is called out on S-102 and A-003.")


def sheet_iso_exploded(L: Layout, S: Scene, t, meta) -> str:
    bx = [b for b in S.boxes if (b.kind not in ("ground", "glass") and not _house(b)) or (b.tag or "").startswith("blind") or (b.tag or "") == "snow retention bar"]
    cov = any(b.kind in ("cpost", "rafter", "ssroof") for b in bx)
    sub = "Each build layer lifted in order: piers · posts" + (" + knee braces" if any(b.kind == "brace" for b in bx) else "") + " · beams · frame · decking" + (" · stair" if any(b.kind in ("tread", "stringer") for b in bx) else "") + (" · rail" if L.rail else "") + (" · roof covers layer by layer" if cov else "")
    return _axo_sheet("A-003", "Isometric — exploded, labeled", sub, L, S, t, meta, bx, explode=True, az=35, el=24,
                      note="Layers lifted in build order." + (" Roof covers pulled apart: posts, beam + ledger, rafters, soffit, sheathing, underlayment, standing seam, snow bar, Hardie trim." if cov else " Lifts are for clarity only; every member returns straight down to its place."))


def sheet_iso_covers(L: Layout, S: Scene, t, meta) -> Optional[str]:
    ck = ("cpost", "cbeam", "cledger", "rafter", "sheath", "underlay", "ssroof", "soffit", "hardie", "blind")
    bx = [b for b in S.boxes if b.kind in ck or (b.tag or "") == "snow retention bar" or (b.tag or "") == "blind bottom bar"]
    if not bx:
        return None
    key = [k for k in member_key(L, S, t) if any(k[1](b) for b in bx)]
    return _axo_sheet("A-402", "Roof covers — exploded isometric, labeled", "Both lean-to covers pulled apart layer by layer", L, S, t, meta, bx, explode=True, gaps={8: 0.0}, az=-38, el=26, key=key,
                      note="Lifts are for clarity only. Order of work: posts on " + post_base_sku(L.spec) + " bases, beams on their post caps, ledger on LedgerLOK, rafters with H2.5AZ, soffit, OSB, underlayment, panels, trims, snow bar.")


def sheet_iso_structure(L: Layout, S: Scene, t, meta) -> str:
    bx = [b for b in S.boxes if b.kind in ("footing", "base", "post", "brace", "cap", "beam", "joist", "rim", "ledger", "block", "cpost", "stringer", "gravel")]
    key = [k for k in member_key(L, S, t) if any(k[1](b) for b in bx)]
    if L.spec.framing.system == "steel":
        return _axo_sheet("S-102", "Structure isometric — steel frame, labeled", "Piers, stubs, cover posts at the shared piers, boxed beams, C-joists, track rims, ledger track, blocking", L, S, t, meta, bx, az=-32, el=32, key=key,
                          note="Decking, covers and house removed to show the frame. Every joist end clips to the track, ledger track or boxed beam; the engineer's clip schedule governs.")
    bls = getattr(L, "beam_lines", None) or (L.frame.beams if L.frame else [])
    kinds = {b.kind for b in bls}
    items = " ".join(ln.item.lower() for ln in getattr(t, "lines", []))
    ledger = any(b.kind == "ledger" for b in bx)
    hang = " and ".join(w for w, on in (("the ledger", ledger), ("the flush beams", "flush" in kinds)) if on)
    note = ("Decking, rail and house removed to show the frame. " + (f"Joists hang from {hang} in face-mount hangers" if hang else "Joists")
            + ("; they bear on the drop beam with H2.5AZ ties" if "drop" in kinds else "")
            + ("; skewed 45° hangers where joists meet the angled rims" if "skewed" in items else "")
            + ("; double rims in concealed-flange hangers" if "concealed" in items else "") + ".")
    return _axo_sheet("S-102", "Structure isometric — frame, labeled", "Piers, post bases, posts" + (", knee braces" if any(b.kind == "brace" for b in bx) else "") + ", post caps, beam" + ("s" if len(bls) > 1 else "") + ", joists, "
                      + ("double rims" if L.spec.framing.rim_plies > 1 else "rims") + (", ledger" if ledger else "") + ", blocking", L, S, t, meta, bx, az=-32, el=32, key=key, note=note)


def sheet_elevations(L: Layout, S: Scene, t, meta) -> str:
    """A-201: front elevation (from the yard) and both end elevations, drawn from the model, with the heights called out."""
    from .axo import View, draw
    s = L.spec
    cols = _axo_colors(S)
    bx = [b for b in S.boxes if b.kind not in ("ground", "glass")]
    fit = [b for b in bx if not _house(b)]
    o = []
    zt = s.geometry.height_in / 12.0
    views = [("FRONT ELEVATION — from the yard", 0.0, (20, 14, 600, 300)), ("RIGHT END ELEVATION", 90.0, (640, 14, 340, 300)), ("LEFT END ELEVATION", -90.0, (640, 330, 340, 270))]
    for ttl, az, fr in views:
        polys, to_sheet, sc = draw(bx, cols, View(az, 0.0), (fr[0], fr[1] + 16, fr[2], fr[3] - 30), fit_boxes=fit)
        cid = f"el{int(az + 180)}"
        o.append(f'<defs><clipPath id="{cid}"><rect x="{fr[0]}" y="{fr[1] + 14}" width="{fr[2]}" height="{fr[3] - 20}"/></clipPath></defs>')
        o.append(T(fr[0], fr[1] + 8, ttl, 9, 800, fill=GOLD))
        o.append(f'<g clip-path="url(#{cid})">' + "".join(polys) + "</g>")
        gx0 = to_sheet((min(b.x0 for b in fit) - 2, max(b.y1 for b in fit) + 2, 0))[0] if az == 0 else fr[0]
        gy = to_sheet((0, 0, 0))[1]
        o.append(LN(fr[0], gy, fr[0] + fr[2], gy, INK, 1.2)); o.append(T(fr[0] + 4, gy + 10, "GRADE", 6.5, 800, fill=MUTE))
        # heights at the right of each view
        hx = fr[0] + fr[2] - 8
        marks = [("DECK", zt)]
        from .spec import covers_of
        for c in covers_of(s):
            if c.get("clear_low_in") is not None:
                marks.append((f"{c['name'].split()[0].upper()} CLEAR @ BEAM {c['clear_low_in']:g}\"", zt + float(c["clear_low_in"]) / 12))
            if c.get("clear_high_in") is not None:
                marks.append((f"{c['name'].split()[0].upper()} CLEAR @ HOUSE {c['clear_high_in']:g}\"", zt + float(c["clear_high_in"]) / 12))
        if az == 0:
            y = to_sheet((0, 0, zt))[1]
            o.append(LN(hx - 40, y, hx, y, "#b3261e", 0.9, "3 2")); o.append(R(hx - 96, y - 11, 54, 10, CREAM, "#b3261e", 0.5)); o.append(T(hx - 44, y - 3, f"DECK · {ftin(zt * 12)} AFG", 6.4, 800, "end", "#b3261e"))
            for c in covers_of(s):
                if c.get("clear_low_in") is None:
                    continue
                xa = to_sheet((float(c["x0"]), float(c["y1"]), 0))[0]
                for k_, (lab_, inch) in enumerate((("CLEAR @ BEAM", c["clear_low_in"]),)):
                    z = zt + float(inch) / 12
                    yv = to_sheet((0, 0, z))[1]
                    o.append(LN(xa - 4, yv, xa + 30, yv, "#b3261e", 0.9, "3 2"))
                    lab_txt = f"{c['name'].split()[0].upper()} {lab_} {float(inch):g}\" · {ftin(z * 12)} AFG"
                    o.append(R(xa + 1, yv + 2, len(lab_txt) * 3.5 + 4, 10, CREAM, "#b3261e", 0.5)); o.append(T(xa + 3, yv + 9.5, lab_txt, 6.2, 800, "start", "#b3261e"))
    o.append(T(20, 330 + 12, "NOTES", 9, 800, fill=GOLD))
    notes = [f"Deck surface {ftin(s.geometry.height_in)} above grade (walkway low point {ftin(s.geometry.height_min_in)})" if s.geometry.height_min_in else f"Deck surface {ftin(s.geometry.height_in)} above grade",
             "Heights AFG = above finished grade at the beam line; field-verify grade before setting the piers",
             ]
    from .spec import covers_of as _cov
    if _cov(s):
        notes += ["Clear heights are to the underside of the beam / ledger above the deck surface",
                  "Roof covers: black standing seam on 2x8 rafters, Hardie fascia / rakes / soffit; slope to the yard"]
    if s.framing.system == "steel":
        notes.append("Deck frame: CEMCO cold-formed steel; HardieTrim skirt covers the track rims")
    else:
        bl_ = L.beam_lines[0] if L.beam_lines else None
        notes.append(f"Deck frame: {s.framing.joist_size} {s.framing.joist_grade} @ {L.frame.spacing:g}\" OC" + (f" on a {bl_.size} {bl_.species.replace('DF#1', 'DF #1')} drop beam, {bl_.n_posts} posts" if bl_ else "")
                     + (" with 4x4 knee braces both ways" if s.framing.knee_braces else ""))
    if L.rail:
        notes.append(f"Guard {L.rail.height:g}\" min. on every open side — the surface is {ftin(s.geometry.height_in)} above grade (IRC R312.1)")
    else:
        notes.append("No guard required: every walking surface is under 30\" above grade (IRC R312.1)")
    yy = 358
    for n_ in notes:
        o.append(T(20, yy, "· " + n_, 7.6, 500)); yy += 12
    return sheet("A-202", "Elevations", "Front from the yard and both ends, drawn from the model — deck and roof-cover heights", o, "Elevations · orthographic · not to scale · heights govern", meta)


# ------------------------------------------------------------------ connection details (permit set)
_PANEL = {"r": 10000.0}


def _lead(o, ax, ay, tx, ty, txt, size=6.6, anchor_="start", w_=600):
    """A leader from (ax, ay) to a label at (tx, ty); the label wraps to stay inside the current detail panel."""
    o.append(LN(ax, ay, tx, ty - 2, INK, 0.5)); o.append(C(ax, ay, 1.3, INK, "none", 0))
    room = max(14, min(34, int((_PANEL["r"] - 6 - tx) / (size * 0.52))))
    for j, ln in enumerate(textwrap.wrap(txt, room)):
        o.append(T(tx + (2 if anchor_ == "start" else -2), ty + j * 8, ln, size, w_, anchor_))


def _panel(o, x, y, w, h, num, title):
    _PANEL["r"] = x + w
    o.append(R(x, y, w, h, "#fff", INK, 0.8)); o.append(R(x, y, w, 17, INK, "none", 0))
    o.append(T(x + 8, y + 12.5, f"{num}  {title}", 8.6, 800, fill=GOLD))


def _cee(o, x, y, w, h, lip=5, open_right=True, fill="#a7adb2"):
    """A C-section in section view: web + two flanges + lips (cold-formed steel)."""
    t_ = 2.2
    o.append(R(x, y, t_, h, fill, INK, 0.6) if open_right else R(x + w - t_, y, t_, h, fill, INK, 0.6))
    o.append(R(x, y, w, t_, fill, INK, 0.6)); o.append(R(x, y + h - t_, w, t_, fill, INK, 0.6))
    lx = x + w - t_ if open_right else x
    o.append(R(lx, y, t_, lip, fill, INK, 0.6)); o.append(R(lx, y + h - lip, t_, lip, fill, INK, 0.6))


def _screw(o, x, y, horiz=True):
    o.append(C(x, y, 1.6, INK, "none", 0))
    o.append(LN(x - 4, y, x + 4, y, INK, 0.6) if horiz else LN(x, y - 4, x, y + 4, INK, 0.6))


def sheet_details_steel_connections(L: Layout, S: Scene, t, meta) -> str:
    """D-502: every steel-frame connection drawn and labeled."""
    s = L.spec
    G = "#a7adb2"
    dk = f"{s.decking.brand} {s.decking.collection} {s.decking.color}"
    o = []
    W3, H2 = 316, 296
    P = [(14 + i * (W3 + 8), 8 + j * (H2 + 8)) for j in range(2) for i in range(3)]
    # 1 ledger track at the house
    x, y = P[0]; _panel(o, x, y, W3, H2, "1", "LEDGER TRACK AT THE HOUSE — SECTION")
    o.append(R(x + 20, y + 40, 46, 220, FILL["house"], INK, 1.0)); o.append(T(x + 43, y + 250, "house rim", 6.4, 700, "middle", MUTE))
    o.append(R(x + 66, y + 40, 4, 220, "#3f5d8a", "none", 0))
    o.append(R(x + 70, y + 92, 5, 66, G, INK, 0.6))
    _cee(o, x + 80, y + 96, 150, 58, open_right=False)
    o.append(R(x + 75, y + 152, 32, 4, "#7b8186", INK, 0.6)); o.append(R(x + 75, y + 152, 4, 18, "#7b8186", INK, 0.6))
    o.append(R(x + 70, y + 86, 190, 7, FILL["deck"], INK, 0.5))
    o.append(f'<polyline points="{x + 40},{y + 70} {x + 70},{y + 80} {x + 70},{y + 88} {x + 84},{y + 88}" fill="none" stroke="{GOLD}" stroke-width="2"/>')
    for yy in (108, 136):
        o.append(LN(x + 30, y + yy, x + 75, y + yy, INK, 1.2)); o.append(C(x + 75, y + yy, 2, INK))
    o.append(R(x + 84, y + 104, 14, 40, "#7b8186", INK, 0.6))
    for yy in (112, 124, 136):
        _screw(o, x + 91, y + yy)
    _lead(o, x + 60, y + 70, x + 150, y + 36, "Z-flashing over the track, under the siding (lapped over the membrane)")
    _lead(o, x + 68, y + 200, x + 120, y + 210, "Self-adhered membrane, 12\" up the wall behind the track")
    _lead(o, x + 72, y + 120, x + 120, y + 178, f"{s.framing.steel_track} ledger track, G90 — 1/4\" x 3-1/2\" structural screws, 2 rows staggered 16\" OC into the rim (engineer)")
    _lead(o, x + 100, y + 154, x + 170, y + 240, "3x3 x 14 ga ledger angle — joist seat")
    _lead(o, x + 91, y + 124, x + 236, y + 130, "Clip angle, #12 screws, 4 per leg")
    _lead(o, x + 200, y + 120, x + 236, y + 160, f"{s.framing.steel_joist} C-joist, G90 @ {L.frame.spacing:g}\" OC")
    _lead(o, x + 210, y + 89, x + 236, y + 60, f"{dk} decking, hidden fasteners")
    # 2 joist to boxed beam
    x, y = P[1]; _panel(o, x, y, W3, H2, "2", "JOIST TO BOXED BEAM — SECTION")
    _cee(o, x + 136, y + 100, 22, 70, open_right=True); _cee(o, x + 158, y + 100, 22, 70, open_right=False)
    _cee(o, x + 30, y + 100, 104, 70, open_right=False); _cee(o, x + 182, y + 100, 104, 70, open_right=True)
    for xx in (124, 186):
        o.append(R(x + xx, y + 112, 12, 44, "#7b8186", INK, 0.6))
        for yy in (120, 132, 144):
            _screw(o, x + xx + 6, y + yy)
    for yy in (108, 162):
        _screw(o, x + 158, y + yy, horiz=False)
    o.append(R(x + 20, y + 93, 276, 7, FILL["deck"], INK, 0.5))
    _lead(o, x + 158, y + 170, x + 120, y + 214, f"Boxed beam: two {s.framing.steel_joist} C, toe-to-toe, #12 screws @ 12\" OC top and bottom (engineer)")
    _lead(o, x + 130, y + 132, x + 24, y + 40, "Clip angle 1-1/2 x 1-1/2 x 7\" 16 ga each joist end")
    _lead(o, x + 192, y + 120, x + 200, y + 40, "#12-14 self-drilling hex-washer screws, 4 per leg")
    _lead(o, x + 250, y + 140, x + 220, y + 250, "C-joists @ 12\" OC both sides, flush with the beam top")
    # 3 boxed beam on HSS stub / pier
    wood_post = s.framing.steel_deck_post == "wood"
    x, y = P[2]; _panel(o, x, y, W3, H2, "3", "BEAM ON 6x6 POST + DIAMOND PIER" if wood_post else "BEAM ON HSS STUB + DIAMOND PIER")
    o.append(LN(x + 20, y + 200, x + W3 - 20, y + 200, INK, 1.0)); o.append(T(x + W3 - 24, y + 196, "grade", 6.4, 700, "end", MUTE))
    o.append(R(x + 128, y + 190, 60, 18, FILL["concrete"], INK, 0.9))
    for dx in (-60, -24, 24, 60):
        o.append(LN(x + 158, y + 208, x + 158 + dx, y + 285, INK, 1.1))
    o.append(R(x + 140, y + 178, 36, 12, FILL["steel"], INK, 0.6))
    o.append(R(x + 144, y + 112, 28, 66, FILL["timber"], INK, 0.8) if wood_post else R(x + 150, y + 112, 16, 66, G, INK, 0.8))
    o.append(R(x + 140, y + 106, 36, 6, FILL["steel"], INK, 0.6))
    o.append(R(x + 60, y + 50, 196, 56, G, INK, 0.9)); o.append(LN(x + 158, y + 50, x + 158, y + 106, INK, 0.6))
    o.append(R(x + 50, y + 43, 216, 7, FILL["deck"], INK, 0.5))
    _lead(o, x + 158, y + 196, x + 196, y + 238, f"Diamond Pier {L.frame.footing_model}: head + 4 pins driven, no excavation")
    _lead(o, x + 176, y + 184, x + 214, y + 160, f"Simpson {post_base_sku(s)} on the pier bolt" if wood_post else "Pier-head post bracket on the pier bolt")
    _lead(o, x + 156, y + 140, x + 24, y + 150, f"6x6 {post_words(s)} deck post" if wood_post else "3x3 x 11 ga HSS stub, hot-dip galvanized")
    _lead(o, x + 176, y + 108, x + 214, y + 124, "Galvanized steel beam saddle, thru-bolted to the post, #12 screws into the beam (engineer)" if wood_post else "Welded cap plate, (4) #12 screws up into the beam (engineer)")
    _lead(o, x + 90, y + 78, x + 24, y + 30, f"Boxed {s.framing.steel_joist} beam, flush with the joists")
    # 4 shared pier: cover post carries the deck beam
    x, y = P[3]; _panel(o, x, y, W3, H2, "4", "SHARED PIER — COVER POST + DECK BEAM")
    o.append(LN(x + 20, y + 230, x + W3 - 20, y + 230, INK, 1.0))
    o.append(R(x + 128, y + 220, 60, 18, FILL["concrete"], INK, 0.9))
    for dx in (-50, -20, 20, 50):
        o.append(LN(x + 158, y + 238, x + 158 + dx, y + 290, INK, 1.1))
    o.append(R(x + 138, y + 210, 40, 10, FILL["steel"], INK, 0.6))
    o.append(R(x + 144, y + 30, 28, 180, FILL["timber"], INK, 0.9))
    o.append(R(x + 60, y + 120, 84, 52, G, INK, 0.9)); o.append(R(x + 172, y + 120, 84, 52, G, INK, 0.9))
    o.append(R(x + 132, y + 114, 52, 64, "none", "#3f5d8a", 1.3))
    for yy in (132, 158):
        o.append(LN(x + 128, y + yy, x + 188, y + yy, INK, 1.4))
    o.append(R(x + 50, y + 113, 94, 7, FILL["deck"], INK, 0.5)); o.append(R(x + 172, y + 113, 94, 7, FILL["deck"], INK, 0.5))
    _lead(o, x + 158, y + 60, x + 190, y + 40, f"6x6 {post_words(s)} cover post — runs up to the roof-cover beam")
    _lead(o, x + 132, y + 140, x + 24, y + 40, "Steel side bracket, 11 ga galvanized, (2) 1/2\" thru-bolts")
    _lead(o, x + 100, y + 150, x + 24, y + 196, "Boxed steel deck beam bears on the bracket")
    _lead(o, x + 178, y + 214, x + 200, y + 256, f"Simpson {post_base_sku(s)} on the Diamond Pier bolt (pier upsized to DP-75/63 where roof + deck exceed the DP-50)")
    _lead(o, x + 240, y + 116, x + 210, y + 90, "Picture-frame board notched around the post, 1/4\" gap")
    # 5 deck edge
    x, y = P[4]; _panel(o, x, y, W3, H2, "5", "DECK EDGE — TRACK RIM, BORDER, HARDIE SKIRT")
    o.append(R(x + 196, y + 90, 6, 70, G, INK, 0.7)); _cee(o, x + 60, y + 92, 136, 66, open_right=True)
    o.append(R(x + 150, y + 82, 56, 9, FILL["border"], INK, 0.5)); o.append(R(x + 50, y + 82, 98, 9, FILL["deck"], INK, 0.5))
    o.append(R(x + 202, y + 98, 5, 52, "#8d949a", INK, 0.5)); o.append(R(x + 207, y + 88, 7, 92, "#f2efe8", INK, 0.6))
    o.append(LN(x + 30, y + 240, x + W3 - 20, y + 240, INK, 1.0)); o.append(R(x + 30, y + 232, W3 - 50, 8, FILL["gravel"], "none", 0)); o.append(LN(x + 30, y + 240, x + W3 - 20, y + 240, "#3f5d8a", 1.2, "3 2"))
    o.append(LN(x + 230, y + 180, x + 230, y + 232, "#b3261e", 0.8)); o.append(T(x + 234, y + 210, "2\" min. to gravel", 6.4, 800, fill="#b3261e"))
    _lead(o, x + 176, y + 86, x + 170, y + 40, f"Picture-frame border, {dk}, face-fastened, color-matched plugs")
    _lead(o, x + 100, y + 86, x + 24, y + 40, "Field boards, CONCEALoc clips on the steel-frame screw")
    _lead(o, x + 199, y + 130, x + 236, y + 70, f"{s.framing.steel_track} track rim caps the joist ends, #12 screws each flange")
    _lead(o, x + 204, y + 140, x + 236, y + 120, "Galvanized hat-channel furring, screwed to the track")
    _lead(o, x + 211, y + 168, x + 236, y + 168, f"HardieTrim skirt {s.extras.hardie_color}".strip())
    _lead(o, x + 120, y + 236, x + 24, y + 270, "2\" gravel over 6-mil poly, sloped away from the house")
    # 6 stair at the step edge
    x, y = P[5]; _panel(o, x, y, W3, H2, "6", "STAIR OFF THE MAIN DECK — SECTION")
    st_ = L.stairs[0] if L.stairs else None
    rz = st_.geo.riser_in if st_ else 7.5
    o.append(LN(x + 20, y + 230, x + W3 - 20, y + 230, INK, 1.0))
    o.append(R(x + 196, y + 140, 100, 8, FILL["deck"], INK, 0.5)); o.append(R(x + 190, y + 148, 6, 50, G, INK, 0.7))
    o.append(PG([(x + 190, y + 148), (x + 106, y + 230), (x + 120, y + 230), (x + 190, y + 162)], G, INK, 0.7))
    o.append(R(x + 140, y + 182, 52, 8, FILL["deck"], INK, 0.5)); o.append(R(x + 186, y + 148, 4, 34, "#f2efe8", INK, 0.5)); o.append(R(x + 136, y + 190, 4, 40, "#f2efe8", INK, 0.5))
    o.append(R(x + 188, y + 156, 10, 18, "#7b8186", INK, 0.6))
    dim_v(o, lambda v: v, x + 300, y + 140, y + 230, f"{ftin(rz * 2)} total rise", 6.6, left=False)
    _lead(o, x + 165, y + 186, x + 40, y + 60, f"Treads: {dk}, 2 boards, color-matched plugs")
    _lead(o, x + 138, y + 210, x + 40, y + 110, f"Closed risers: {dk} riser board")
    _lead(o, x + 150, y + 210, x + 210, y + 260, "Galvanized steel stringers @ 12\" OC, clipped to the track rim")
    _lead(o, x + 193, y + 165, x + 230, y + 100, "Clip angle stringer-to-rim, #12 screws")
    _lead(o, x + 110, y + 230, x + 24, y + 270, f"Lands on compacted grade, no pad · {st_.geo.risers if st_ else 2} risers @ {rz:.2f}\" · tread {st_.geo.tread_in if st_ else 11:.2f}\"")
    return sheet("D-502", "Connection details — CEMCO steel deck frame", "Ledger track · joist clips · boxed beam · post on the pier · shared pier · deck edge · stair", o,
                 "Schematic details, not to scale · the engineer of record's details and screw schedule govern", meta)


# ------------------------------------------------------------------ wood-frame connection details (permit set)
def _bolt(o, x, y, r=2.2):
    o.append(C(x, y, r, "#fff", INK, 0.7)); o.append(C(x, y, 0.8, INK, "none", 0))


def _wood(o, x, y, w, h, dark=False, sw=0.7):
    o.append(R(x, y, w, h, FILL["timber_dk"] if dark else FILL["timber"], INK, sw))


def _grid6():
    W3, H2 = 316, 296
    return W3, H2, [(14 + i * (W3 + 8), 8 + j * (H2 + 8)) for j in range(2) for i in range(3)]


def sheet_details_wood_connections(L: Layout, S: Scene, t, meta) -> str:
    """D-502: the frame's connections, each drawn and labeled — ledger, hangers, beam, post, pier, knee braces."""
    s = L.spec
    fr = L.frame
    dk = f"{s.decking.brand} {s.decking.collection} {s.decking.color}"
    js = s.framing.joist_size
    bl = L.beam_lines[0] if L.beam_lines else None
    bsize = bl.size if bl else "4x10"
    bsp = (s.framing.beams[0].species if s.framing.beams else "DF").replace("DF#1", "DF #1")
    cap = bl.cap_mid if bl else "BC46Z"
    pw = post_words(s) if s.framing.post_species or s.framing.post_rough else "#2 GC"
    cant = s.extras.ledger_on_cantilevered_floor
    W3, H2, P = _grid6()
    o = []
    # 1 ledger at the house
    x, y = P[0]; _panel(o, x, y, W3, H2, "1", "LEDGER ON THE CANTILEVERED FLOOR — SECTION" if cant else "LEDGER AT THE HOUSE — SECTION")
    if cant:
        o.append(R(x + 24, y + 150, 20, 92, FILL["house"], INK, 0.9)); o.append(T(x + 37, y + 236, "wall below", 6, 700, "middle", MUTE, rot=-90))
        _wood(o, x + 24, y + 120, 82, 30)
        o.append(LN(x + 44, y + 158, x + 112, y + 158, "#b3261e", 0.8)); o.append(T(x + 78, y + 168, "2'-0\" cantilever", 6.4, 800, "middle", "#b3261e"))
    else:
        o.append(R(x + 40, y + 150, 66, 92, FILL["house"], INK, 0.9))
        _wood(o, x + 40, y + 120, 66, 30)
    o.append(R(x + 90, y + 40, 22, 80, FILL["house"], INK, 0.8))
    _wood(o, x + 106, y + 120, 6, 30, dark=True)
    o.append(R(x + 112, y + 114, 2.5, 46, "#3f5d8a", "none", 0))
    _wood(o, x + 115, y + 120, 9, 30)
    _wood(o, x + 124, y + 121, 172, 29)
    o.append(R(x + 122, y + 128, 6, 22, "#7b8186", INK, 0.6))
    o.append(R(x + 112, y + 112, 186, 7, FILL["deck"], INK, 0.5))
    o.append(f'<polyline points="{x + 100},{y + 100} {x + 114},{y + 106} {x + 114},{y + 112} {x + 126},{y + 112}" fill="none" stroke="{GOLD}" stroke-width="2"/>')
    for yy in (126, 144):
        o.append(LN(x + 84, y + yy, x + 124, y + yy, INK, 1.1)); o.append(C(x + 124, y + yy, 1.8, INK))
    o.append(LN(x + 52, y + 135, x + 212, y + 135, "#5b6166", 1.2, "4 2"))
    o.append(R(x + 48, y + 130, 8, 10, "#5b6166", INK, 0.5)); o.append(R(x + 208, y + 130, 8, 10, "#5b6166", INK, 0.5))
    _lead(o, x + 106, y + 103, x + 130, y + 32, "Z-flashing over the ledger, under the siding, lapped over the membrane")
    _lead(o, x + 236, y + 116, x + 236, y + 72, f"{dk} decking")
    _lead(o, x + 260, y + 140, x + 236, y + 100, f"{js} joist @ {fr.spacing:g}\" OC")
    _lead(o, x + 52, y + 135, x + 24, y + 40, "DTT1Z lateral tie, 4 per ledger: 1/2\" rod deck joist to floor joist, 750 lb")
    _lead(o, x + 113, y + 156, x + 140, y + 178, "Self-adhered membrane behind the ledger, lapped under the flashing")
    _lead(o, x + 120, y + 146, x + 140, y + 206, f"{s.ledger_size} ledger, LedgerLOK 3-5/8\" 2 rows staggered 12\" OC" + (" into solid blocking in the cantilever bay" if cant else ""))
    if cant:
        o.append(R(x + 14, y + 250, W3 - 28, 36, "#fff6e0", "#b3261e", 0.8))
        for j, w in enumerate(textwrap.wrap("ENGINEER: Arapahoe County bars a ledger on a cantilevered floor without engineer approval. The stamped detail governs: ledger into the blocked cantilever joists, or a freestanding beam on posts at the house.", 76)):
            o.append(T(x + 20, y + 261 + j * 8.5, w, 6.4, 700, fill="#b3261e"))
    # 2 hangers — plan at the ledger and the side rim
    x, y = P[1]; _panel(o, x, y, W3, H2, "2", "HANGERS — PLAN AT THE LEDGER + SIDE RIM")
    o.append(R(x + 20, y + 30, W3 - 40, 18, FILL["house"], INK, 0.8)); o.append(T(x + W3 / 2, y + 42, "HOUSE", 6.6, 800, "middle", MUTE))
    _wood(o, x + 20, y + 48, W3 - 40, 8, dark=True)
    _wood(o, x + 30, y + 56, 8, 120); _wood(o, x + 38, y + 56, 8, 120)
    _wood(o, x + 56, y + 56, 6, 120)
    for k in range(3):
        _wood(o, x + 120 + k * 60, y + 56, 6, 120)
    for xx in [56] + [120 + k * 60 for k in range(3)]:
        o.append(R(x + xx - 3, y + 56, 12, 9, "#7b8186", INK, 0.6))
    o.append(R(x + 28, y + 56, 20, 11, "#5b6166", INK, 0.6))
    o.append(LN(x + 46, y + 150, x + 56, y + 150, "#b3261e", 0.8)); o.append(T(x + 51, y + 146, "1-1/2\"", 6.2, 800, "middle", "#b3261e"))
    o.append(LN(x + 123, y + 140, x + 183, y + 140, "#b3261e", 0.8)); o.append(T(x + 153, y + 136, f"{fr.spacing:g}\" OC", 6.6, 800, "middle", "#b3261e"))
    hs = "LUS28Z" if js in ("2x8", "2x10") else "LUS210Z"
    items = " ".join(ln.item for ln in getattr(t, "lines", []))
    skew2 = "-2Z" in items and "skewed" in items and "HUCQ" not in items
    _lead(o, x + 38, y + 62, x + 24, y + 192, (f"Angled double rims in Simpson SUR/SUL{js.replace('x', '')}-2Z skewed double hangers at the ledger" if skew2 else
                                              f"Double rim in a Simpson HUCQ{js.replace('x', '')}-2-SDS concealed-flange hanger at the ledger"))
    _lead(o, x + 186, y + 60, x + 166, y + 192, f"Simpson {hs} face-mount hanger, every joist, 10d HDG in every hole")
    _lead(o, x + 59, y + 120, x + 24, y + 246, "Picture-frame joist 1-1/2\" inboard of the rim")
    _lead(o, x + 42, y + 160, x + 166, y + 246, f"{fr.rim_plies}-ply {js} rim, GRK RSS 3-1/8\", 2 rows @ 12\" staggered")
    # 3 joists over the drop beam / into the flush beam
    flush = bool(bl) and bl.kind == "flush"
    two_by = bsize.startswith(("(2)2x", "(3)2x"))
    plyfast = "plies laminated GRK RSS 3-1/8\", 2 rows @ 12\" staggered" if two_by else "plies through-bolted 1/2\" @ 24\" staggered"
    sb = [b_ for b_ in (s.framing.beams or []) if b_.kind == "flush"]
    setback = min((float(b_.setback_in or 0) for b_ in sb), default=0.0)
    x, y = P[2]; _panel(o, x, y, W3, H2, "3", "JOISTS INTO THE FLUSH BEAM — PLAN + SECTION" if flush else "JOISTS ON THE DROP BEAM — SECTION")
    if flush:
        _wood(o, x + 20, y + 40, W3 - 40, 26)                          # the (2)4x10 in plan, the front of the deck
        o.append(LN(x + 20, y + 53, x + W3 - 20, y + 53, INK, 0.5))
        for k in range(5):
            xx = x + 36 + k * 58
            _wood(o, xx, y + 66, 7, 120, dark=True)
            o.append(R(xx - 3, y + 66, 13, 9, "#7b8186", INK, 0.6))
        for k in range(5):
            _bolt(o, x + 50 + k * 56, y + (47 if k % 2 else 59))
        o.append(T(x + W3 / 2, y + 36, (f"THE FLUSH BEAM — {ftin(setback)} inside the front rim" if setback > 3 else "FRONT OF THE DECK — the beam is the front rim"), 6.6, 800, "middle", MUTE))
        _wood(o, x + 30, y + 214, 120, 46); _wood(o, x + 150, y + 216, 10, 42, dark=True); o.append(R(x + 150, y + 236, 12, 22, "#7b8186", INK, 0.6))
        o.append(R(x + 30, y + 207, 250, 7, FILL["deck"], INK, 0.5)); _wood(o, x + 160, y + 216, 120, 42, dark=True)
        _lead(o, x + 40, y + 70, x + 170, y + 100, f"Simpson LUS hanger every joist off the {bsize} beam face, 10d HDG every hole")
        _lead(o, x + 60, y + 238, x + 24, y + 196, (f"{bsize} {bsp} flush beam, {plyfast}" if setback > 3 else f"{bsize} {bsp} flush beam = front rim, {plyfast}"))
        _lead(o, x + 210, y + 236, x + 236, y + 180, f"{js} joist, top flush with the beam")
        o.append(T(x + 24, y + 278, (f"Joists hang on both faces: from the ledger to the beam, and {ftin(setback)} out to the front rim" if setback > 3
                                     else "No cantilever: the beam carries the front edge, joists hang both ends"), 6.6, 700))
    else:
        o.append(R(x + 20, y + 74, W3 - 40, 7, FILL["deck"], INK, 0.5))
        for k in range(5):
            xx = x + 36 + k * 58
            _wood(o, xx, y + 81, 7, 44)
            o.append(R(xx + 7, y + 120, 6, 12, "#7b8186", INK, 0.5))
            if k < 4:
                _wood(o, xx + 7, y + 83, 51, 40, dark=True)
        o.append(R(x + 36, y + 79, 248, 2.5, "#111", "none", 0))
        _wood(o, x + 24, y + 125, W3 - 48, 46)
        o.append(LN(x + 24, y + 148, x + W3 - 24, y + 148, INK, 0.5))
        for k in range(5):
            _bolt(o, x + 50 + k * 56, y + (136 if k % 2 else 160))
        _lead(o, x + 66, y + 104, x + 24, y + 40, f"Blocking row over the beam, {js}, (3) 3\" screws each end")
        _lead(o, x + 41, y + 126, x + 24, y + 210, "Simpson H2.5AZ every joist + rim to the beam (hidden, inside face)")
        _lead(o, x + 160, y + 160, x + 150, y + 210, f"{bsize} {bsp} drop beam — plies through-bolted 1/2\" HDG, 2 rows staggered @ 24\" OC, 2\" from top / bottom")
        _lead(o, x + 200, y + 80, x + 200, y + 40, "G-Tape 2\" on every joist and block, 4\" on rims and the beam")
        o.append(T(x + 24, y + 262, "Joists bear the full beam width", 6.6, 700))
        o.append(T(x + 24, y + 274, f"Cantilever {ftin(L.frame.beams[0].cantilever) if L.frame.beams else ''} past the beam — over L/4: engineer", 6.6, 700))
    # 4 beam on the post cap
    x, y = P[3]; _panel(o, x, y, W3, H2, "4", f"{bsize} BEAM ON THE 6x6 — ELEVATION")
    _wood(o, x + 20, y + 60, W3 - 40, 46)
    for k in range(6):
        _bolt(o, x + 36 + k * 48, y + (70 if k % 2 == 0 else 96))
    o.append(R(x + 128, y + 104, 48, 14, "#5b6166", INK, 0.6)); o.append(R(x + 124, y + 60, 4, 58, "#5b6166", INK, 0.5)); o.append(R(x + 176, y + 60, 4, 58, "#5b6166", INK, 0.5))
    _wood(o, x + 136, y + 118, 32, 168)
    if s.framing.knee_braces:
        o.append(PG([(x + 168, y + 190), (x + 168, y + 176), (x + 240, y + 106), (x + 254, y + 106)], FILL["timber_dk"], INK, 0.7))
        _bolt(o, x + 168 + 6, y + 186); _bolt(o, x + 244, y + 112 - 30 + 30)
    _lead(o, x + 150, y + 108, x + 24, y + 140, f"Simpson {cap} column cap" + (" — 7\" seat for the (2)4x, SDS screws (confirm SKU / engineer)" if cap.startswith("CCQ7") else
                                                                          ", SD screws — 1/2\" shim: a (2)2x is 3\" in the 3-9/16\" seat" if two_by and cap.startswith("BC46") else ""))
    _lead(o, x + 60, y + 72, x + 24, y + 36, ("GRK RSS 3-1/8\" through the plies, 2 rows 2\" from top / bottom, staggered @ 12\" OC" if two_by
                                             else "1/2\" x 8\" HDG bolts, 2 rows staggered @ 24\" OC, a pair 6\" from each end"))
    _lead(o, x + 150, y + 220, x + 24, y + 230, f"6x6 {pw} post")
    if s.framing.knee_braces:
        _lead(o, x + 210, y + 150, x + 236, y + 180, "4x4 knee brace at 45°, 1/2\" through-bolt each end (see 6)")
    # 5 post base on the pier
    x, y = P[4]; _panel(o, x, y, W3, H2, "5", "POST BASE ON THE DIAMOND PIER — SECTION")
    o.append(LN(x + 20, y + 170, x + W3 - 20, y + 170, INK, 1.0)); o.append(T(x + W3 - 24, y + 166, "grade", 6.4, 700, "end", MUTE))
    o.append(PG([(x + 120, y + 160), (x + 196, y + 160), (x + 186, y + 186), (x + 130, y + 186)], FILL["concrete"], INK, 0.9))
    for dx in (-70, -30, 30, 70):
        o.append(LN(x + 158, y + 184, x + 158 + dx, y + 282, INK, 1.2))
    o.append(R(x + 154, y + 146, 8, 16, "#5b6166", INK, 0.5))
    o.append(R(x + 136, y + 140, 44, 8, "#5b6166", INK, 0.6)); o.append(R(x + 136, y + 110, 4, 34, "#5b6166", INK, 0.5)); o.append(R(x + 176, y + 110, 4, 34, "#5b6166", INK, 0.5))
    _wood(o, x + 140, y + 36, 36, 104)
    o.append(LN(x + 186, y + 140, x + 186, y + 148, "#b3261e", 0.8)); o.append(T(x + 190, y + 146, "1\" standoff", 6.2, 800, fill="#b3261e"))
    _lead(o, x + 158, y + 174, x + 210, y + 210, f"Diamond Pier {fr.footing_model}: precast head + 4 x 50\" pins driven at the factory angles — no excavation; frost-protected")
    _lead(o, x + 158, y + 150, x + 24, y + 200, "Pier-head bolt / anchor per Diamond Pier")
    _lead(o, x + 178, y + 128, x + 210, y + 110, f"Simpson {post_base_sku(s)} adjustable standoff base, SD screws")
    _lead(o, x + 158, y + 80, x + 24, y + 60, f"6x6 {pw} post, cut ends sealed")
    # 6 knee braces
    x, y = P[5]; _panel(o, x, y, W3, H2, "6", "KNEE BRACES — BOTH DIRECTIONS" if s.framing.knee_braces else "POST HEIGHT")
    if s.framing.knee_braces:
        _wood(o, x + 20, y + 50, 140, 30)
        _wood(o, x + 40, y + 80, 22, 200)
        o.append(PG([(x + 62, y + 160), (x + 62, y + 144), (x + 126, y + 80), (x + 142, y + 80)], FILL["timber_dk"], INK, 0.7))
        _bolt(o, x + 68, y + 156); _bolt(o, x + 132, y + 72 + 14)
        o.append(T(x + 90, y + 44, "along the beam", 6.8, 800, "middle"))
        _wood(o, x + 176, y + 44, 120, 8, dark=True); o.append(T(x + 236, y + 38, "toward the house", 6.8, 800, "middle"))
        _wood(o, x + 262, y + 52, 30, 26)
        _wood(o, x + 266, y + 78, 22, 200)
        o.append(PG([(x + 266, y + 160), (x + 266, y + 144), (x + 214, y + 52), (x + 198, y + 52)], FILL["timber_dk"], INK, 0.7))
        _wood(o, x + 186, y + 52, 26, 26)
        _bolt(o, x + 260, y + 154); _bolt(o, x + 203, y + 64)
        _lead(o, x + 100, y + 120, x + 70, y + 210, f"4x4 {pw.replace('Douglas fir #1', 'DF #1')} brace at 45°, {ftin(s.framing.knee_leg_in)} legs, 1/2\" x 10\" bolt at the post, 1/2\" x 12\" at the (2)4x beam")
        _lead(o, x + 199, y + 66, x + 70, y + 236, f"{js} block between two joists takes the brace top, 1/2\" x 6\" bolt; block screwed (3) each end")
        o.append(T(x + 24, y + 274, f"Posts {ftin(fr.post_len)}: braces both ways at every post (engineer)", 6.6, 700))
    else:
        o.append(T(x + 20, y + 40, "Post length, top of the standoff base to the beam seat", 7.2, 800))
        o.append(T(x + 20, y + 52, "cut in the field to the string line; the beam tops sit flush with the joists", 6.6, 500, fill=MUTE))
        yy = y + 74
        for t_, a_ in (("Beam line", 20), ("Posts", 170), ("Post", 230)):
            o.append(T(x + a_, yy, t_.upper(), 6.4, 800, fill=MUTE))
        for bl_ in (L.beam_lines or []):
            yy += 16
            o.append(T(x + 20, yy, bl_.label, 6.8, 700)); o.append(T(x + 170, yy, str(len(bl_.posts_x)), 6.8, 600))
            o.append(T(x + 230, yy, inch(bl_.post_len, 16) if bl_.post_len < 24 else ftin(bl_.post_len), 6.8, 700))
        if any(bl_.post_len < 8 for bl_ in (L.beam_lines or [])):
            yy += 26
            for ln_ in textwrap.wrap("Under 8\" there is little room for the pier head, the standoff base and a post: check the grade at each pier "
                                     "before setting (see the field flags); where it is tight the beam bears on the pier through a bracket, no post.", 78):
                o.append(T(x + 20, yy, ln_, 6.6, 600, fill="#b3261e")); yy += 11
    return sheet("D-502", "Connection details — frame", f"Ledger{' on the cantilever' if cant else ''} · hangers · joists {'into' if flush else 'on'} the beam · {bsize} on the cap · pier + base · "
                 + ("knee braces" if s.framing.knee_braces else "post lengths"), o,
                 "Schematic details, not to scale · the engineer of record's details govern", meta)


def sheet_details_edge_rail(L: Layout, S: Scene, t, meta) -> Optional[str]:
    """D-504: deck edge, picture frame, rail post mounting, guard bay, tape and the fastening schedule."""
    s = L.spec
    rl = L.rail
    fr = L.frame
    js = s.framing.joist_size
    dk = f"{s.decking.brand} {s.decking.collection} {s.decking.color}"
    from .catalog import RAIL_SYSTEMS as _RS, default_fastener_system
    rs = _RS.get(rl.system, {}) if rl else {}
    fsys = s.decking.fastener_system or default_fastener_system(s.decking.collection, s.decking.profile)
    W3, H2, P = _grid6()
    o = []
    rname = ("TimberTech Impression Rail Express" if rl and rl.system.startswith("IRX") else (rl.system if rl else ""))
    pf_fast = "Cortex screws + color-matched plugs" if (s.decking.border_fastener or "").lower().startswith("cortex") else "Cap-Tor xd color-matched"
    # 1 rail post on the deck edge
    surface = bool(rs.get("surface"))
    pw = float(rs.get("post_w", 2.0))
    pmat = "steel" if "steel" in (rs.get("note") or "") else "aluminum"
    x, y = P[0]; _panel(o, x, y, W3, H2, "1", "RAIL POST — SURFACE MOUNT ON BLOCKING" if surface else "RAIL POST AT THE RIM — SECTION")
    if surface:
        _wood(o, x + 200, y + 160, 9, 40); _wood(o, x + 209, y + 160, 9, 40)
        _wood(o, x + 160, y + 160, 9, 40)
        _wood(o, x + 169, y + 162, 31, 36, dark=True)
        o.append(R(x + 218, y + 156, 6, 52, FILL["fascia"] if "fascia" in FILL else FILL["deck"], INK, 0.5))
        o.append(R(x + 150, y + 152, 74, 8, FILL["border"], INK, 0.5)); o.append(R(x + 40, y + 152, 108, 8, FILL["deck"], INK, 0.5))
        o.append(R(x + 168, y + 146, 40, 6, FILL["railmetal"], INK, 0.6)); o.append(R(x + 180, y + 40, 16, 106, FILL["railmetal"], INK, 0.6))
        for xx in (172, 202):
            o.append(LN(x + xx, y + 146, x + xx, y + 196, INK, 1.0)); o.append(C(x + xx, y + 146, 1.6, INK))
        if rl:
            dim_v(o, lambda v: v, x + 150, y + 40, y + 152, f"{rl.height:g}\"", 6.6, left=True)
        _lead(o, x + 188, y + 60, x + 230, y + 50, f"{rname} {pw:g}\" {pmat} post, {rl.color if rl else ''}")
        _lead(o, x + 188, y + 149, x + 230, y + 96, "Post base on the decking, (4) FastenMaster HeadLOK 6\" through the base into the blocking")
        _lead(o, x + 184, y + 180, x + 24, y + 230, f"{js} blocking pair between the rim and the PF joist at every post, (3) RSS each end — guard 200 lb point load")
    else:
        # the post inside the outer rim ply: the inner ply pocketed to the post's width, two bolts through the outer ply and
        # the post, the nut in the 1-1/2" gap before the PF joist; the fascia covers the bolt heads
        _wood(o, x + 209, y + 160, 9, 40)                                         # outer rim ply
        o.append(R(x + 200, y + 160, 9, 40, "none", INK, 0.6, 'stroke-dasharray="3 2"'))   # inner ply, pocketed at the post (behind the cut)
        _wood(o, x + 182, y + 160, 9, 40)                                         # PF joist, 1-1/2" inboard
        o.append(R(x + 218, y + 156, 6, 52, FILL["fascia"] if "fascia" in FILL else FILL["deck"], INK, 0.5))
        o.append(R(x + 150, y + 152, 47, 8, FILL["border"], INK, 0.5)); o.append(R(x + 209, y + 152, 15, 8, FILL["border"], INK, 0.5))
        o.append(R(x + 40, y + 152, 108, 8, FILL["deck"], INK, 0.5))
        o.append(R(x + 197, y + 40, 12, 156, FILL["railmetal"], INK, 0.6))       # the post, down to the rim's lower bolt
        for yy in (172, 188):
            o.append(LN(x + 218, y + yy, x + 192, y + yy, INK, 1.4)); o.append(R(x + 191, y + yy - 2.5, 4, 5, "#5b6166", INK, 0.4))
        if rl:
            dim_v(o, lambda v: v, x + 150, y + 40, y + 152, f"{rl.height:g}\"", 6.6, left=True)
        _lead(o, x + 203, y + 60, x + 230, y + 50, f"{rname} {pw:g}\" {pmat} post, {rl.color if rl else ''} — through the decking, inside the outer rim ply")
        _lead(o, x + 214, y + 172, x + 236, y + 120, f"(2) 7/16\" x 4-1/2\" HDG bolts through the outer ply and the post, washer + nut in the gap")
        _lead(o, x + 204, y + 196, x + 24, y + 236, f"Inner rim ply pocketed {pw:g}\" wide at the post")
        _lead(o, x + 186, y + 186, x + 24, y + 206, "PF joist 1-1/2\" inboard of the rim: the nut sits in the gap")
    _lead(o, x + 60, y + 156, x + 24, y + 40, f"Field boards, {fsys} hidden fasteners")
    _lead(o, x + 214, y + 200, x + 236, y + 240, f"Double rim {js}, fascia over" + ("" if surface else " — it hides the bolt heads"))
    # 2 deck edge
    x, y = P[1]; _panel(o, x, y, W3, H2, "2", "DECK EDGE — PICTURE FRAME + FASCIA")
    _wood(o, x + 170, y + 110, 10, 60); _wood(o, x + 180, y + 110, 10, 60); _wood(o, x + 140, y + 110, 9, 60)
    o.append(R(x + 190, y + 104, 5, 70, FILL["deck"], INK, 0.5))
    o.append(R(x + 134, y + 101, 62, 9, FILL["border"], INK, 0.5)); o.append(R(x + 30, y + 101, 102, 9, FILL["deck"], INK, 0.5))
    o.append(R(x + 140, y + 108, 9, 2.5, "#111", "none", 0)); o.append(R(x + 170, y + 108, 20, 2.5, "#111", "none", 0))
    for xx in (160, 186):
        o.append(LN(x + xx, y + 96, x + xx, y + 120, INK, 0.9))
    o.append(R(x + 128, y + 104, 4, 6, "#5b6166", INK, 0.4))
    _lead(o, x + 165, y + 100, x + 150, y + 40, f"Picture-frame border, {dk} square edge, mitred, {pf_fast} 2 per bearing @ 16\"")
    _lead(o, x + 130, y + 106, x + 24, y + 60, f"{fsys} clip in every gap at every joist (3/16\" gap)")
    _lead(o, x + 193, y + 150, x + 236, y + 140, f"{s.decking.collection} fascia, pre-drilled, 2 screws at each end then alternating @ 12\"")
    _lead(o, x + 145, y + 140, x + 24, y + 200, "PF joist 1-1/2\" inboard of the rim carries the border's inside edge")
    _lead(o, x + 180, y + 110, x + 236, y + 210, "G-Tape 4\" on the rim tops, 2\" on the joists")
    # 3 guard bay
    x, y = P[2]; _panel(o, x, y, W3, H2, "3", "GUARD — ONE BAY, ELEVATION")
    if rl:
        bay = max(s_.ctc for s_ in rl.sections)
        o.append(R(x + 20, y + 230, W3 - 40, 8, FILL["deck"], INK, 0.5))
        for xx in (40, W3 - 56):
            o.append(R(x + xx, y + 70, 12, 160, FILL["railmetal"], INK, 0.6))
        o.append(R(x + 52, y + 70, W3 - 108, 10, FILL["railmetal"], INK, 0.6)); o.append(R(x + 52, y + 214, W3 - 108, 6, FILL["railmetal"], INK, 0.6))
        n = 18
        for k in range(1, n):
            bx = x + 52 + k * (W3 - 108) / n
            o.append(R(bx - 1.2, y + 80, 2.4, 134, FILL["railmetal"], "none", 0))
        dim_h(o, lambda v: v, y + 258, x + 46, x + W3 - 50, f"bay {ftin(max(s_.ctc for s_ in rl.sections))} CTC max", 6.6, up=False)
        dim_v(o, lambda v: v, x + 30, y + 70, y + 230, f"{rl.height:g}\" min.", 6.4, left=True)
        o.append(C(x + 120, y + 150, 10, "none", "#b3261e", 0.8, "2 2")); o.append(R(x + 132, y + 145, 72, 12, "#fff", "none", 0)); o.append(T(x + 134, y + 154, "4\" sphere won't pass", 6.4, 800, fill="#b3261e"))
        o.append(T(x + 160, y + 228, "under 4\" at the bottom rail", 6.2, 700, "middle", "#b3261e"))
        _lead(o, x + 150, y + 75, x + 150, y + 40, f"Modern top rail, {rl.color}" if rs.get("surface") else f"{rname} level panel: top rail, balusters, bottom rail, {rl.color}")
        _lead(o, x + 90, y + 110, x + 40, y + 40, "Vertical square aluminum balusters" if rs.get("surface") else "Balusters (in the panel)")
        o.append(T(x + 24, y + 276, "Guard: 200 lb point load at the top, 50 lb on 1 SF of infill", 6.4, 700))
        o.append(T(x + 24, y + 286, "(IRC Table R301.5) — submit the rail code report", 6.4, 700))
    # 4 lateral tie plan
    x, y = P[3]; _panel(o, x, y, W3, H2, "4", "LATERAL LOAD — DTT1Z TIES (PLAN)")
    o.append(R(x + 20, y + 40, W3 - 40, 110, FILL["house"], INK, 0.6)); o.append(T(x + 30, y + 54, "house floor framing (joists run ⟂ or ∥ — engineer)", 6.4, 700, fill=MUTE))
    for k in range(5):
        o.append(R(x + 40 + k * 56, y + 60, 5, 90, FILL["timber_dk"], INK, 0.4))
    _wood(o, x + 20, y + 150, W3 - 40, 8, dark=True)
    for k in range(6):
        _wood(o, x + 36 + k * 50, y + 158, 6, 64)
    for xx in (36, 86, 236, 286):
        o.append(LN(x + xx + 3, y + 100, x + xx + 3, y + 200, "#5b6166", 1.4)); o.append(R(x + xx - 2, y + 196, 10, 8, "#5b6166", INK, 0.5)); o.append(R(x + xx - 2, y + 96, 10, 8, "#5b6166", INK, 0.5))
    o.append(T(x + 160, y + 216, "deck joists", 6.4, 700, "middle", MUTE))
    _lead(o, x + 89, y + 200, x + 24, y + 240, f"(4) Simpson DTT1Z, 2 near each end of the ledger: 1/2\" threaded rod through the ledger and the band into a floor joist (or blocking) inside — 750 lb each (IRC R507.9.2)")
    # 5 G-tape
    x, y = P[4]; _panel(o, x, y, W3, H2, "5", "JOIST TAPE + BLOCKING")
    for k, (lab, wd) in enumerate((("joist", 2), ("PF joist", 2), ("block", 2), ("rim (2-ply)", 4), ("beam", 4))):
        xx = x + 30 + k * 56
        _wood(o, xx, y + 90, 3 * 6 * (2 if wd == 4 else 1), 70)
        o.append(R(xx - 2, y + 86, 3 * 6 * (2 if wd == 4 else 1) + 4, 4, "#111", "none", 0))
        o.append(T(xx + 9, y + 176, lab, 6.4, 700, "start")); o.append(T(xx + 9, y + 186, f"{wd}\" tape", 6.4, 800, "start", "#b3261e"))
    o.append(T(x + 24, y + 230, "Nichigo G-Tape 3035 (black) on every top edge before decking, lapped over the ends and", 6.6, 600))
    o.append(T(x + 24, y + 240, f"down the sides 1/2\"; one row of {js} blocking over the beam, (3) structural screws each end", 6.6, 600))
    # 6 fastening schedule
    x, y = P[5]; _panel(o, x, y, W3, H2, "6", "FASTENING SCHEDULE")
    items = " ".join(ln.item for ln in getattr(t, "lines", []))          # what the order carries: the schedule says the same
    bls = L.beam_lines or []
    kinds = {b.kind for b in bls}
    two_by = any(b.size.startswith(("(2)2x", "(3)2x")) for b in bls)
    four_by = any(b.size.startswith("(2)4x") for b in bls)
    hang = "LUS28Z" if js in ("2x8", "2x10") else "LUS210Z"
    cap = bls[0].cap_mid if bls else "BC46Z"
    cortex = (s.decking.border_fastener or "").lower().startswith("cortex")
    rows = [("Ledger to house", "LedgerLOK 3-5/8\", 2 rows staggered 12\" OC" + (" — engineer" if s.extras.ledger_on_cantilevered_floor else "")),
            ("Lateral", "(4) DTT1Z, 1/2\" rod into the floor framing"),
            ("Joist to ledger", f"{hang}, 10d HDG every hole")]
    if "HUCQ" in items or not ("-2Z" in items and "skewed" in items):
        rows.append(("Rim to ledger", f"HUCQ{js.replace('x', '')}-2-SDS, SDS screws"))
    else:
        rows.append(("Rim to ledger", f"SUR/SUL{js.replace('x', '')}-2Z skewed double hanger (45° rims)"))
    if "SUR" in items:
        rows.append(("Joist to 45° rim", f"SUR/SUL{js.replace('x', '')}Z skewed hanger, 10d HDG every hole"))
    rows += [("Rim plies", "GRK RSS 3-1/8\", 2 rows @ 12\" staggered"),
             ("Joist to beam", f"{hang} each side of the flush beam, 10d HDG" if kinds == {"flush"} else "H2.5AZ each joist + rim, 10d x 1-1/2\"" if kinds <= {"drop"}
              else f"{hang} at flush beams; H2.5AZ at drop beams"),
             ("Beam plies", "GRK RSS 3-1/8\", 2 rows @ 12\" staggered" if two_by and not four_by else "1/2\" x 8\" HDG bolts, 2 rows staggered @ 24\"" if not two_by
              else "RSS on the (2)2x, 1/2\" bolts on the (2)4x"),
             ("Beam to post", f"{cap} cap, SD screws" + (" (1/2\" shim, (2)2x beam)" if two_by and cap.startswith("BC46") else "")),
             ("Post to pier", f"{post_base_sku(s)} on the Diamond Pier, SD screws"),
             ("Knee braces", "1/2\" through-bolt each end (x10 / x12 / x6)") if s.framing.knee_braces else ("Blocking", "(3) structural screws each end"),
             ("Field boards", f"{fsys}, every joist, every gap"),
             ("Borders / fascia", ("Borders: Cortex + plugs · fascia: Cap-Tor xd" if cortex else "Cap-Tor xd color-matched, pre-drilled")),
             ("Rail posts", "(4) HeadLOK 6\" into blocking" if rs.get("surface") else "(2) 7/16\" bolts per post")]
    yy = y + 36
    for a, b in rows:
        o.append(T(x + 14, yy, a, 6.8, 800)); o.append(T(x + 106, yy, textwrap.shorten(b, 52, placeholder="…"), 6.6, 500)); yy += 18
        o.append(LN(x + 10, yy - 12, x + W3 - 10, yy - 12, "#e2dccf", 0.5))
    return sheet("D-504", "Connection details — deck edge, rail, lateral", "Rail post mounting · picture frame + fascia · guard bay · DTT1Z lateral ties · joist tape · fastening schedule", o,
                 "Schematic details, not to scale · the engineer of record's details govern", meta)


def sheet_details_cover_connections(L: Layout, S: Scene, t, meta) -> Optional[str]:
    """D-503: every roof-cover connection drawn and labeled."""
    s = L.spec
    from .spec import covers_of
    cvs = covers_of(s)
    if not cvs:
        return None
    c0 = cvs[0]
    cb, cl = c0.get("beam", "(2)2x10"), c0.get("ledger", "2x10")
    post = f"6x6 {post_words(s)}"
    hc = s.extras.hardie_color or ""
    roof = f"{s.extras.cover_roof_color} 24 ga standing seam".strip()
    WD, WD2 = FILL["timber"], FILL["timber_dk"]
    o = []
    W3, H2 = 316, 296
    P = [(14 + i * (W3 + 8), 8 + j * (H2 + 8)) for j in range(2) for i in range(3)]
    # 1 ledger at the house (headwall)
    x, y = P[0]; _panel(o, x, y, W3, H2, "1", "COVER LEDGER + HEADWALL — SECTION")
    o.append(R(x + 20, y + 30, 50, 250, FILL["house"], INK, 1.0)); o.append(T(x + 45, y + 270, "house wall", 6.4, 700, "middle", MUTE))
    o.append(R(x + 70, y + 30, 4, 200, "#3f5d8a", "none", 0))
    o.append(R(x + 74, y + 130, 16, 56, WD2, INK, 0.7))
    o.append(PG([(x + 90, y + 126), (x + 290, y + 140), (x + 290, y + 182), (x + 90, y + 168)], WD, INK, 0.7))
    o.append(PG([(x + 90, y + 120), (x + 290, y + 134), (x + 290, y + 140), (x + 90, y + 126)], "#c9a46a", INK, 0.5))
    o.append(LN(x + 90, y + 117, x + 290, y + 131, "#1c1c1e", 3))
    o.append(f'<polyline points="{x + 50},{y + 80} {x + 74},{y + 92} {x + 74},{y + 116} {x + 104},{y + 118}" fill="none" stroke="{GOLD}" stroke-width="2"/>')
    o.append(PG([(x + 90, y + 168), (x + 290, y + 182), (x + 290, y + 186), (x + 90, y + 172)], "#f2efe8", INK, 0.5))
    for yy in (142, 172):
        o.append(LN(x + 34, y + yy, x + 88, y + yy, INK, 1.2)); o.append(C(x + 88, y + yy, 2, INK))
    _lead(o, x + 82, y + 160, x + 120, y + 230, f"{cl} ledger — FastenMaster LedgerLOK 6\", 2 rows staggered 16\" OC into the house framing")
    _lead(o, x + 72, y + 210, x + 24, y + 286, "Membrane behind the ledger")
    _lead(o, x + 74, y + 100, x + 110, y + 40, "Headwall flashing with Z-closure, counterflashed under the siding")
    _lead(o, x + 200, y + 125, x + 200, y + 60, f"{roof}, 1-1/2\" mechanical seam")
    _lead(o, x + 240, y + 135, x + 236, y + 96, "High-temp underlayment over 7/16\" OSB")
    _lead(o, x + 200, y + 160, x + 214, y + 200, "2x8 rafter @ 16\" OC bears on the ledger, H2.5AZ / LS70 each")
    _lead(o, x + 250, y + 182, x + 236, y + 250, f"HardieSoffit cedarmill ceiling {hc}".strip())
    # 2 eave at the beam
    x, y = P[1]; _panel(o, x, y, W3, H2, "2", "EAVE AT THE BEAM — SECTION")
    o.append(R(x + 120, y + 150, 30, 130, WD, INK, 0.9)); o.append(R(x + 112, y + 110, 46, 40, WD2, INK, 0.8)); o.append(LN(x + 135, y + 110, x + 135, y + 150, INK, 0.6))
    o.append(R(x + 112, y + 146, 46, 8, FILL["steel"], INK, 0.6))
    o.append(PG([(x + 20, y + 90), (x + 250, y + 102), (x + 250, y + 132), (x + 20, y + 120)], WD, INK, 0.7))
    o.append(R(x + 250, y + 98, 8, 38, WD2, INK, 0.6)); o.append(R(x + 258, y + 92, 6, 50, "#f2efe8", INK, 0.6))
    o.append(LN(x + 20, y + 85, x + 268, y + 98, "#1c1c1e", 3)); o.append(f'<polyline points="{x + 268},{y + 98} {x + 270},{y + 108}" fill="none" stroke="#1c1c1e" stroke-width="2"/>')
    o.append(R(x + 200, y + 84, 10, 8, FILL["steel"], INK, 0.6))
    o.append(PG([(x + 20, y + 120), (x + 250, y + 132), (x + 250, y + 136), (x + 20, y + 124)], "#f2efe8", INK, 0.5))
    o.append(C(x + 140, y + 116, 2.4, INK))
    _lead(o, x + 135, y + 130, x + 24, y + 160, f"{cb} beam on the posts")
    _lead(o, x + 150, y + 150, x + 180, y + 180, ("Simpson BC46Z post cap" if cb.startswith("4x") else "Simpson AC6Z post cap") + (" (rough-6x6 R-series)" if s.framing.post_rough else ""))
    _lead(o, x + 135, y + 220, x + 180, y + 230, f"{post} post")
    _lead(o, x + 140, y + 116, x + 24, y + 40, "H2.5AZ hurricane tie each rafter to the beam")
    _lead(o, x + 205, y + 88, x + 170, y + 40, "Snow retention bar clamped to the seams, 12–18\" up from the eave")
    _lead(o, x + 254, y + 118, x + 236, y + 60, "2x8 sub-fascia")
    _lead(o, x + 262, y + 140, x + 236, y + 270, f"HardieTrim fascia {hc}, color-matched trim screws".strip())
    _lead(o, x + 268, y + 104, x + 286, y + 70, "Eave drip trim, hemmed panel")
    _lead(o, x + 60, y + 124, x + 24, y + 260, "HardieSoffit ceiling on the rafter undersides, 12\" overhang")
    # 3 post base
    x, y = P[2]; _panel(o, x, y, W3, H2, "3", "COVER POST BASE + DECK PENETRATION")
    o.append(LN(x + 20, y + 230, x + W3 - 20, y + 230, INK, 1.0))
    o.append(R(x + 128, y + 220, 60, 18, FILL["concrete"], INK, 0.9))
    for dx in (-50, -20, 20, 50):
        o.append(LN(x + 158, y + 238, x + 158 + dx, y + 290, INK, 1.1))
    o.append(R(x + 138, y + 208, 40, 12, FILL["steel"], INK, 0.6)); o.append(R(x + 144, y + 30, 28, 178, WD, INK, 0.9))
    o.append(R(x + 40, y + 160, 100, 8, FILL["border"], INK, 0.5)); o.append(R(x + 176, y + 160, 100, 8, FILL["border"], INK, 0.5))
    o.append(R(x + 40, y + 168, 104, 40, "#a7adb2", INK, 0.6)); o.append(R(x + 172, y + 168, 104, 40, "#a7adb2", INK, 0.6))
    _lead(o, x + 158, y + 214, x + 200, y + 258, f"Simpson {post_base_sku(s)} standoff base on the Diamond Pier bolt")
    _lead(o, x + 158, y + 236, x + 24, y + 270, "Diamond Pier — shared with the deck beam where they line up")
    _lead(o, x + 158, y + 80, x + 190, y + 50, f"{post} post through the deck, plumb both ways")
    _lead(o, x + 150, y + 164, x + 24, y + 120, "Picture-frame border boxes the post, 1/4\" gap all round")
    _lead(o, x + 200, y + 190, x + 236, y + 150, "Steel blocking at the post opening (see D-502 / 4)")
    # 4 rake
    x, y = P[3]; _panel(o, x, y, W3, H2, "4", "RAKE EDGE — SECTION ACROSS THE SLOPE")
    o.append(R(x + 60, y + 110, 14, 70, WD, INK, 0.7)); o.append(R(x + 100, y + 110, 14, 70, WD, INK, 0.7)); o.append(R(x + 140, y + 110, 14, 70, WD, INK, 0.7))
    o.append(R(x + 40, y + 102, 200, 8, "#c9a46a", INK, 0.6)); o.append(LN(x + 40, y + 98, x + 240, y + 98, "#1c1c1e", 3))
    o.append(R(x + 160, y + 106, 12, 76, WD2, INK, 0.6)); o.append(R(x + 172, y + 96, 7, 92, "#f2efe8", INK, 0.6))
    o.append(f'<polyline points="{x + 150},{y + 94} {x + 186},{y + 94} {x + 186},{y + 112}" fill="none" stroke="#1c1c1e" stroke-width="2"/>')
    o.append(R(x + 40, y + 180, 140, 4, "#f2efe8", INK, 0.5))
    _lead(o, x + 120, y + 98, x + 40, y + 40, f"{roof} panel, last seam at the rake")
    _lead(o, x + 186, y + 100, x + 210, y + 50, "Rake / gable trim, color-matched, cleated")
    _lead(o, x + 166, y + 150, x + 210, y + 140, "2x8 rake sub-fascia on the end rafter")
    _lead(o, x + 176, y + 170, x + 210, y + 200, f"HardieTrim rake {hc}".strip())
    _lead(o, x + 107, y + 150, x + 40, y + 230, "2x8 rafters @ 16\" OC")
    _lead(o, x + 80, y + 182, x + 40, y + 268, "HardieSoffit ceiling")
    # 5 standing seam panel
    x, y = P[4]; _panel(o, x, y, W3, H2, "5", "STANDING SEAM PANEL + CLIP")
    o.append(R(x + 20, y + 170, 276, 10, "#c9a46a", INK, 0.6)); o.append(R(x + 20, y + 166, 276, 4, "#3d4651", INK, 0.4))
    for xx in (40, 190):
        o.append(f'<polyline points="{x + xx},{y + 166} {x + xx + 100},{y + 166} {x + xx + 106},{y + 120} {x + xx + 112},{y + 120} {x + xx + 112},{y + 166}" fill="none" stroke="#1c1c1e" stroke-width="2"/>')
    o.append(R(x + 144, y + 124, 6, 46, FILL["steel"], INK, 0.6)); o.append(C(x + 147, y + 168, 2, INK))
    o.append(R(x + 20, y + 180, 14, 60, WD, INK, 0.6)); o.append(R(x + 130, y + 180, 14, 60, WD, INK, 0.6)); o.append(R(x + 240, y + 180, 14, 60, WD, INK, 0.6))
    dim_h(o, lambda v: v, y + 108, x + 40, x + 150, "16\" panel", 6.6)
    _lead(o, x + 150, y + 120, x + 200, y + 50, "1-1/2\" seam, mechanically double-locked (rated to 1/2:12)")
    _lead(o, x + 147, y + 150, x + 200, y + 90, "Concealed clip @ 18\" OC each seam, pancake-head screws")
    _lead(o, x + 60, y + 168, x + 24, y + 70, "High-temp self-adhered underlayment, full coverage")
    _lead(o, x + 80, y + 176, x + 24, y + 260, "7/16\" OSB on the rafters")
    _lead(o, x + 247, y + 210, x + 236, y + 270, "2x8 rafters @ 16\" OC")
    # 6 blinds + beam face
    x, y = P[5]; _panel(o, x, y, W3, H2, "6", "EXISTING BLINDS AT THE BEAM")
    o.append(R(x + 110, y + 70, 50, 44, WD2, INK, 0.8)); o.append(R(x + 160, y + 64, 7, 56, "#f2efe8", INK, 0.6)); o.append(R(x + 118, y + 114, 34, 160, WD, INK, 0.8))
    o.append(C(x + 186, y + 128, 9, "#7a5c45", INK, 0.6)); o.append(R(x + 168, y + 116, 10, 8, FILL["steel"], INK, 0.5))
    o.append(R(x + 184, y + 137, 4, 120, "#7a5c45", "none", 0, 'fill-opacity="0.55"')); o.append(R(x + 180, y + 255, 12, 4, FILL["steel"], INK, 0.4))
    o.append(R(x + 20, y + 274, 276, 8, FILL["deck"], INK, 0.5))
    _lead(o, x + 186, y + 128, x + 214, y + 80, "Existing roll-down blind — taken down and rehung on the new beam (stays, no new blinds)")
    _lead(o, x + 172, y + 120, x + 214, y + 150, "Owner's brackets into the beam face through the HardieTrim, sealed")
    _lead(o, x + 135, y + 90, x + 24, y + 40, f"{cb} beam")
    _lead(o, x + 163, y + 80, x + 24, y + 140, f"HardieTrim beam wrap {hc}".strip())
    _lead(o, x + 135, y + 200, x + 24, y + 210, f"{post} post")
    return sheet("D-503", "Connection details — roof covers (wood framing)", "Ledger + headwall · eave at the beam · post base · rake · standing seam + clip · blinds", o,
                 "Schematic details, not to scale · the engineer of record's details govern", meta)
