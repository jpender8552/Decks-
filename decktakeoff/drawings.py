"""SVG drawing sheets from the scene boxes + layout — the same geometry the 3D model is built from.
Sheets: G-001 general notes & design criteria (the permit-set sheet) · S-100 foundation plan · S-101 framing plan ·
A-101 decking plan · A-201 rail plan + elevation · A-301 section + front elevation · D-501 details.
Every sheet: 1000 x 700 field, GSX title block, cream ground, ink / gold. Design intent; the stamped set governs."""
from __future__ import annotations

import html as _html
import math
import textwrap
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from .catalog import RAIL_SYSTEMS, decking_facts
from .layout import Layout
from .scene import Scene, Box, build_scene
from .units import ftin

INK, GOLD, CREAM, SAND, MUTE = "#111111", "#d49e1b", "#f7f2e8", "#e9dfcf", "#6b665e"
FILL = dict(timber="#c9a06a", timber_dk="#a87e4c", deck="#c4c2bd", border="#3a3a3c", steel="#1c1c1e", concrete="#cfcbc2", stone="#9a948b",
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


def fill_for(b: Box) -> str:
    if b.kind in ("joist", "rim", "ledger", "block", "beam", "post", "doubler"):
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
        o.append(R(X(b.x0), Z(b.z1), (b.x1 - b.x0) * sc, (b.z1 - b.z0) * sc, fill_for(b), stroke, sw))


def dim_h(o, X, y, xa, xb, lab, size=8.5, up=True):
    o.append(LN(X(xa), y, X(xb), y, INK, 0.8)); o.append(LN(X(xa), y - 4, X(xa), y + 4)); o.append(LN(X(xb), y - 4, X(xb), y + 4))
    o.append(T((X(xa) + X(xb)) / 2, y - 4 if up else y + 11, lab, size, 700, "middle"))


def dim_v(o, Y, x, ya, yb, lab, size=8.5, left=True):
    o.append(LN(x, Y(ya), x, Y(yb), INK, 0.8)); o.append(LN(x - 4, Y(ya), x + 4, Y(ya))); o.append(LN(x - 4, Y(yb), x + 4, Y(yb)))
    o.append(T(x - 5 if left else x + 13, (Y(ya) + Y(yb)) / 2, lab, size, 700, "middle", rot=-90))


def house_outline(o, X, Y, sc, S: Scene):
    for b in S.boxes:
        if b.kind == "house":
            o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, FILL["house"], INK, 1.4))
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
        o.append(T(X(z["x0"] + z["W"] / 2), Y(z["wall_y"]) - 6, (f"HOUSE — {z['name']}" if z.get("ledger", True) else f"OPEN — {z['name']} (rear beam, no ledger)"), 8, 800, "middle", "#a89b84"))


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
def sheet_notes(L: Layout, S: Scene, t, flags, meta) -> str:
    s = L.spec
    o = []
    o.append(T(24, 24, "PROJECT", 9, 800, fill=GOLD))
    lines = [f"{s.job}", f"{s.site.address}, {s.site.city} {s.site.state} {s.site.zip}".strip(", "), f"Prepared for {s.client}" if s.client else "",
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
    struct = [("Footings", sm["posts"].split(" on ")[-1]), ("Posts", sm["posts"].split(" on ")[0]), ("Beams", "; ".join(sm["beams"])), ("Joists", sm["joists"]), ("Rims", sm["rims"]),
              ("Ledger", t.schedule.get("Ledger", "—")), ("Decking", sm["decking"]), ("Rail", sm["rail"])]
    for k, v in struct:
        for i, ln in enumerate(textwrap.wrap(v, 96)[:2]):
            o.append(T(24 if i == 0 else 150, y, k if i == 0 else "", 8.5, 800)); o.append(T(150, y, ln, 8.5, 400)); y += 12
    # right column: sheet index + flags + setbacks
    x2 = 600
    o.append(T(x2, 24, "SHEET INDEX", 9, 800, fill=GOLD))
    yy = 40
    from .spec import covers_of
    idx = [(n_, t_) for n_, t_ in SHEET_INDEX if not (n_ == "A-201" and not L.rail)]
    if s.site.plan and s.site.plan.get("parcel"):
        idx.insert(1, SHEET_INDEX_EXTRA[0])
    if covers_of(s):
        idx.insert([n_ for n_, _ in idx].index("A-301") + 1, SHEET_INDEX_EXTRA[1])
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
        o.append(T(x2, yy, textwrap.shorten(ln, 74, placeholder="…"), 8, 400)); yy += 12
    if flags is not None:
        o.append(T(x2, yy + 12, "FLAGS (INTERNAL — remove before the permit submittal)", 9, 800, fill=GOLD)); yy += 28
        for f in [f for f in flags if f.severity in ("STOP", "ENGINEER", "CODE")][:14]:
            o.append(T(x2, yy, f.severity, 7.5, 800, fill="#b3261e" if f.severity == "STOP" else GOLD)); o.append(T(x2 + 62, yy, textwrap.shorten(f.text, 66, placeholder="…"), 7.8, 400)); yy += 11.5
    return sheet("G-001", "General notes · design criteria", "Loads, codes, structure summary, sheet index, site — the permit-set cover", o, "No scale", meta)


def sheet_foundation(L: Layout, S: Scene, meta) -> str:
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
            rows.append((f"P{n}", ftin(px), ftin(bl.y), zn, f"{ld:,.0f} lb"))
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
    for bl in L.beam_lines:
        o.append(T(X(bl.x0) + 4, Y(bl.y * IN) - 6, bl.label, 7.5, 800, fill=MUTE))
    # dims: beam lines from the front, zone widths
    zs = S.meta["zones"]
    dim_h(o, X, Y(S.y_front) + 16, zs[0]["x0"], zs[-1]["x0"] + zs[-1]["W"], ftin(S.W * 12) + " along the house", up=False)
    for z in zs:
        dim_h(o, X, Y(S.y_front) + 32, z["x0"], z["x0"] + z["W"], f"{z['name']} {ftin(z['W'] * 12)}", up=False)
    for bl in L.beam_lines:
        dim_v(o, Y, X(bl.x1) + 10, bl.y * IN, S.y_front, f"{ftin((S.y_front - bl.y * IN) * 12)} to rim face", left=False)
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
        o.append(T(X(bl.x0) + 6, Y(bl.y * IN) + 3, bl.label + (" (below)" if bl.kind == "drop" else " (flush)"), 7.5, 800, fill="#3f5d8a"))
    zs = S.meta["zones"]
    jlab = '7-1/4" steel C' if L.spec.framing.system == "steel" else L.frame.joist_size
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
    notes = [t.summary["joists"], t.summary["rims"], t.schedule.get("Ledger", ""), t.schedule.get("Blocking", "blocking one row over the beam, staggered"),
             t.schedule.get("Joist tape", ""), "; ".join(t.summary["beams"])]
    hw = [f"{l.item}: {l.net:g}" for l in t.lines if l.category == "Hardware" and l.unit == "ea"][:8]
    yy = 40
    for n in notes + ["Connectors:"] + hw:
        for ln in textwrap.wrap(n, 40)[:3]:
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
        for x, y_lo, y_hi, lab in L.plan.dividers:
            o.append(T(X(x * IN), Y(y_hi * IN) + 8, f"breaker {lab} · {ftin(y_hi - y_lo)}", 6.5, 700, "middle", MUTE))
    dim_h(o, X, Y(S.y_front) + 22, -S.meta["edge"], S.W + S.meta["edge"], ftin((S.W + 2 * S.meta["edge"]) * 12) + " over the edge boards", up=False)
    nx = 760
    o.append(T(nx, 24, "DECKING", 9, 800, fill=GOLD))
    s = L.spec
    f = decking_facts(s.decking.collection)
    notes = [f"Field: {s.decking.brand} {s.decking.collection} {s.decking.color}, {f['width']:g}\" x {f['thick']:g}\", {ftin(s.deck_gap)} gaps",
             f"Border{' & dividers' if L.divider_x else ''}: {s.decking.border_collection or s.decking.collection} {s.decking.border_color or s.decking.color}" if s.geometry.picture_frame else "No picture frame",
             f"Boards run {'parallel to' if s.geometry.board_direction == 'parallel' else 'out from'} the house; edge overhang {ftin(S.meta['edge'] * 12)}" + (" over the fascia" if s.decking.fascia else " — no fascia, rim exposed"),
             t.schedule.get("Field", ""), t.schedule.get("Face screws", ""),
             (L.plan.summary() + " — every board one piece wall to border, no butt joints" if L.plan is not None else
              "Rows per zone: " + " · ".join(f"{z.name} {z.decking.rows}" for z in L.zones) + (" (rip at the house)" if any(z.decking.last_row_dev < -0.5 for z in L.zones) else " (no rips)"))]
    yy = 40
    for n in notes:
        for ln in textwrap.wrap(n, 40)[:4]:
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
        for i, p in enumerate(rl.posts):
            x, y = p.x * IN, p.y * IN
            o.append(R(X(x) - 3, Y(y) - 3, 6, 6, INK, INK, 0.5))
            o.append(T(X(x), Y(y) + 14 if y > (S.y_min + S.y_front) / 2 else Y(y) - 6, f"RP{i + 1} {p.kind[0]}", 6.5, 800, "middle"))
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
        notes.append("Bays: " + " · ".join(f"{s_.side} {ftin(s_.ctc)}" for s_ in rl.sections[:12]))
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
    cut = [b for b in S.boxes if b.x0 <= xc <= b.x1 or b.kind in ("post", "footing", "stone", "cap", "base", "railpost")]
    near = [b for b in cut if b.kind in ("post", "footing", "stone", "cap", "base") and abs((b.x0 + b.x1) / 2 - xc) < 12]
    o.append(R(Yv(deep.wall_y * IN - 3.0), Z(0), (S.y_front + 7.0 - deep.wall_y * IN) * sc, (max(4.0, L.frame.footing_depth_in / 12 + 1)) * sc, "#e0d7c2", "none", 0))
    o.append(LN(Yv(deep.wall_y * IN - 3.0), Z(0), Yv(S.y_front + 4.0), Z(0), INK, 1.0))
    o.append(T(Yv(S.y_front + 3.5), Z(0) + 10, "grade", 7.5, 700, "end", MUTE))
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
    dim_v(o, Z, Yv(S.y_front + 2.6), 0, S.deck_top, f"{ftin(s.geometry.height_in)} to the deck surface", left=False)
    if L.rail:
        dim_v(o, Z, Yv(S.y_front + 2.6), S.deck_top, S.deck_top + L.rail.height * IN, f"guard {L.rail.height:g}\"", left=False)
    for bl in L.beam_lines:
        if bl.x0 <= xc * 12 <= bl.x1:
            dim_h(o, Yv, Z(S.deck_top) - 14, bl.y * IN, S.y_front, ftin((S.y_front - bl.y * IN) * 12) + (" cantilever" if bl.kind == "drop" else ""), 7.5)
    o.append(T(Yv(deep.wall_y * IN - 1.5), Z(S.deck_top + 3.5), f"SECTION through zone {deep.name} at {ftin(deep.W / 2)} — looking toward the left end", 8.5, 800))
    # front elevation (x-z) in the right panel
    Xe, Ze, sce = elev_xform(-4.0, S.W + 4.0, -1.0, S.deck_top + 12.0, 620, 60, 370, 300)
    o.append(T(620, 44, "FRONT ELEVATION — from the yard", 8.5, 800))
    draw_elev_boxes(o, Xe, Ze, sce, S.boxes, ("house", "wall", "privacy", "roof", "glass"), INK, 0.5)
    draw_elev_boxes(o, Xe, Ze, sce, S.boxes, ("footing", "stone", "stonecap", "base", "post", "cap", "beam", "rim", "fascia", "joist", "ledger", "cpost", "cbeam", "hardie", "ssroof"), INK, 0.35)
    draw_elev_boxes(o, Xe, Ze, sce, S.boxes, ("board", "border", "railpost", "toprail", "cable", "baluster", "botrail", "drink", "railcap"), "none", 0)
    o.append(LN(Xe(-4), Ze(0), Xe(S.W + 4), Ze(0), INK, 1.0))
    dim_h(o, Xe, Ze(0) + 16, 0, S.W, ftin(S.W * 12), 7.5, up=False)
    nx = 620
    o.append(T(nx, 400, "SECTION NOTES", 9, 800, fill=GOLD))
    yy = 416
    notes = [f"Deck surface {ftin(s.geometry.height_in)} above grade; guard {L.rail.height:g}\" where the drop exceeds 30\"" if L.rail else f"Deck surface {ftin(s.geometry.height_in)} above grade",
             "; ".join(t.summary["beams"]), f"Posts {t.summary['posts']}", t.schedule.get("Ledger", ""), t.schedule.get("Joist tape", "")]
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
        o.append(T(852, 240, f"4 x 50\" pins · {L.frame.footing_model}", 6.5, 600)); o.append(R(806, 180, 28, 10, FILL["steel"], INK, 0.6)); o.append(T(852, 188, "ABA66Z on the pier bolt", 6.5, 600))
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
    note(360, 560, 270, t.schedule.get("Field", "")[:160])
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
    o.append(T(160, 128, "7-1/4\" C-joist, 16 ga", 7, 700, "middle"))
    o.append(R(93, 92, 150, 7, FILL["deck"], INK, 0.5)); o.append(T(170, 89, "decking", 6.5, 600, "middle"))
    o.append(LN(80, 100, 100, 100, GOLD, 2)); o.append(T(104, 84, "flashing over the track", 6.5, 600))
    for yy in (112, 140):
        o.append(LN(58, yy, 93, yy, INK, 1.4)); o.append(C(93, yy, 2.2, INK))
    note(40, 275, 270, t.schedule.get("Ledger", ""))
    # 2 joist clip
    frame_(340, 20, 300, 290, "2", "JOIST TO TRACK / BEAM")
    o.append(R(380, 70, 14, 160, G, INK, 0.8)); o.append(T(387, 245, "track or boxed beam", 6.5, 700, "middle"))
    chan(394, 110, 200, 70)
    o.append(T(494, 150, "7-1/4\" C-joist", 7.5, 700, "middle"))
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
    note(680, 275 - 10, 290, "Where a cover post lands on the deck beam line it stands on the deck's Diamond Pier (ABA66Z on the pier bolt) and carries the deck beam on a steel side bracket; elsewhere a 3x3 HSS stub on a pier-head bracket. Engineer sizes the pier for roof + deck and the uplift hold-down.")
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
    clear = (hmin - 1.0 - 7.25) if hmin is not None else None
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
    if ref.get("rear"):
        o.append(LN(X(min(xs)), Y(rear_y - ref["rear"]), X(max(xs)), Y(rear_y - ref["rear"]), "#8a6d2a", 0.9, "6 4"))
        o.append(T(X(max(xs)) - 4, Y(rear_y - ref["rear"]) - 4, f"{ref['rear']}' R-L rear setback (reference)", 7.5, 700, "end", "#8a6d2a"))
    # house footprint (existing, hatched)
    fp = sp.get("footprint") or []
    if fp:
        o.append('<defs><pattern id="hatchC" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#b9ad97" stroke-width="1.2"/></pattern></defs>')
        o.append(PG([(X(x), Y(y)) for x, y in fp], "url(#hatchC)", INK, 1.3))
        cx = sum(p[0] for p in fp) / len(fp); cy = sum(p[1] for p in fp) / len(fp)
        o.append(T(X(cx), Y(cy), "EXISTING HOUSE", 9, 900, "middle", MUTE)); o.append(T(X(cx), Y(cy) + 12, "one storey + garage (no work)", 7.5, 600, "middle", MUTE))
    # decks
    out = deck_outline(S)
    o.append(PG([(X(x), Y(y)) for x, y in out], FILL["deck"], INK, 1.2))
    for z in S.meta["zones"]:
        deep = z["front"] - z["wall_y"] > 6
        o.append(T(X(z["x0"] + z["W"] / 2), (Y((z["wall_y"] + z["front"]) / 2) + 3) if deep else Y(z["front"]) + 10, f"DECK {z['name']}", 7, 900, "middle", "#f3ead9" if deep else INK))
    # stairs / landings
    for b in S.boxes:
        if b.kind in ("tread",) or (b.tag and b.tag.startswith("landing pad")) or b.mat == "concrete" and b.kind == "pad":
            o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, FILL["concrete"], INK, 0.6))
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
        probes.append((("deck edge", (min(xf) + max(xf)) / 2 + 2.0, deck_front), rear_pred))
    probes.append((("deck edge", min(p[0] for p in out), max(p[1] for p in out if abs(p[0] - min(q[0] for q in out)) < 0.01) / 2), side_pred))
    probes.append((("deck edge", max(p[0] for p in out), max(p[1] for p in out if abs(p[0] - max(q[0] for q in out)) < 0.01) / 2), side_pred))
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
    if ll.get("rear"):
        o.append(T(X((min(xs) + max(xs)) / 2), Y(rear_y) + 13, ll["rear"], 7.5, 800, "middle", MUTE))
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
    lg = [("#1c1c1e", "dash", "new roof cover — roof edge incl. overhang"), (FILL["deck"], "fill", "new deck (TimberTech, steel frame)"), ("#b3261e", "line", "distance to the lot line (GIS)")]
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
    sb += [f"Measured (red): to the nearest lot line from the new work — GIS, not survey"]
    for ln in [x for x in sb if x]:
        for w in textwrap.wrap(ln, 80):
            o.append(T(x2, yy, w, 8, 500)); yy += 11.5
    o.append(T(x2, yy + 10, "SITE WORK", 9, 800, fill=GOLD)); yy += 26
    work = ["Remove the two decks, the two roof covers and the box step; haul off", "Diamond Pier foundations (no excavation spoils), 6-mil poly + 2\" gravel under the decks",
            "New concrete landing pad at the stair", "Roof drainage: covers shed to grade at the low eave, away from the house", "Call 811 before the piers; protect the lawn and the owner's blinds"]
    for ln in work:
        o.append(T(x2, yy, "· " + ln, 8, 500)); yy += 11.5
    if sp.get("source"):
        yy += 6
        for w in textwrap.wrap(sp["source"], 86):
            o.append(T(x2, yy, w, 7.2, 500, fill=MUTE)); yy += 10
    return sheet("C-100", "Site plan", "Parcel, existing house, new decks and roof covers, distances to the lot lines, coverage", o, "Plan · approx. 1\" = 20' at full size · GIS lines, not a survey", meta)


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
        o.append(T(ox, 18, f"{c['name'].upper()} — PLAN", 10, 900, fill=GOLD))
        Xp, Yp, scp = plan_xform(x0 - 1.5, x1 + 1.5, y0 - 1.0, y1 + ov + 1.5, ox, 38, colw - 40, 215)
        o.append(R(Xp(x0 - 1.5), Yp(y0 - 1.0), (x1 - x0 + 3) * scp, 1.0 * scp, FILL["house"], INK, 1.0))
        o.append(T(Xp((x0 + x1) / 2), Yp(y0 - 1.0) - 4, "HOUSE WALL — 2x10 ledger, LedgerLOK 6\" 2 rows @ 16\"", 7, 800, "middle", MUTE))
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
        o.append(T(Xp((x0 + x1) / 2), Yp((y0 + y1) / 2), f"2x8 rafters @ 16\" OC · slope {pitch:.2f}:12 to the yard", 7.5, 800, "middle"))
        o.append(T(Xp((x0 + x1) / 2), Yp((y0 + y1) / 2) + 11, f"{s.extras.cover_roof_color or ''} standing seam, mechanically seamed".strip(), 7.5, 600, "middle"))
        # section
        sy0 = 300
        o.append(T(ox, sy0, f"{c['name'].upper()} — SECTION", 10, 900, fill=GOLD))
        top_z = zt + (hi + 9.25 + 7.25) / 12 + 0.6
        Xs, Zs, scs = elev_xform(y0 - 2.0, y1 + ov + 3.0, -1.8, top_z, ox, sy0 + 8, colw - 40, 205)
        o.append(R(Xs(y0 - 2.0), Zs(0), (y1 + ov + 5) * scs, 1.8 * scs, "#cdbf9f", "none", 0))
        o.append(LN(Xs(y0 - 2.0), Zs(0), Xs(y1 + ov + 3), Zs(0), INK, 1.2))
        o.append(R(Xs(y0 - 2.0), Zs(top_z - 0.1), 2.0 * scs, (top_z - 0.1) * scs, FILL["house"], INK, 1.2))
        o.append(T(Xs(y0 - 1.0), Zs(top_z / 2), "HOUSE", 8, 900, "middle", MUTE, rot=-90))
        o.append(R(Xs(y0), Zs(zt), (y1 - y0 + 0.4) * scs, (1.0 / 12 + 7.25 / 12) * scs, FILL["deck"], INK, 0.8))
        o.append(T(Xs(y0) + 4, Zs(zt) + 10, f"DECK {ftin(s.geometry.height_in)} above grade", 6.5, 800, fill="#f3ead9"))
        zb_hi, zb_lo = zt + hi / 12, zt + lo / 12
        o.append(R(Xs(y0), Zs(zb_hi + 9.25 / 12), 0.13 * scs, 9.25 / 12 * scs, FILL["timber_dk"], INK, 0.6))
        o.append(R(Xs(y1 - 0.25), Zs(zb_lo + 9.25 / 12), 0.5 * scs, 9.25 / 12 * scs, FILL["timber_dk"], INK, 0.6))
        o.append(R(Xs(y1 - 0.23), Zs(zb_lo), 0.46 * scs, (zb_lo - 0.45) * scs, FILL["timber"], INK, 0.6))
        o.append(R(Xs(y1 - 0.45), Zs(0.45), 0.9 * scs, (0.45 + 0.4) * scs, FILL["concrete"], INK, 0.6))
        o.append(T(Xs(y1) + 26, Zs(0.1) + 4, "Diamond Pier (shared with the deck beam)" if c.get("footing") == "deck_pier" else "Diamond Pier", 7, 700))
        for k_ in (-1, 1):
            o.append(LN(Xs(y1), Zs(0), Xs(y1 + k_ * 1.6), Zs(-1.7), INK, 0.7))
        zr0, zr1 = zb_hi + 9.25 / 12, zb_lo + 9.25 / 12 - pitch / 12 * ov
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
                 f"HardieSoffit cedarmill ceiling · HardieTrim fascia + rakes ({s.extras.hardie_color or 'color TBD'}) · H2.5AZ at every rafter · AC6Z caps",
                 "6x6 posts on ABA66Z bases on the Diamond Pier bolt · the engineer's uplift hold-down governs"]
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


def all_sheets(L: Layout, t, flags, scene: Optional[Scene] = None, customer: bool = False) -> List[Tuple[str, str, str]]:
    """[(num, title, svg)] — everything except A-001 (renders) and T-400 (build steps), which the build set adds.
    customer=True leaves the internal flags block off G-001."""
    if customer:
        flags = None
    S = scene or build_scene(L)
    _MAT_COLORS.clear()
    for k in ("deck", "border", "drink", "fascia"):
        if k in S.materials:
            _MAT_COLORS[k] = S.materials[k]["color"]
    FILL["deck"] = _MAT_COLORS.get("deck", FILL["deck"]); FILL["border"] = _MAT_COLORS.get("border", FILL["border"])
    meta = sheet_meta(L, customer=customer)
    out = [("G-001", "General notes · design criteria", sheet_notes(L, S, t, flags, meta))]
    site = sheet_site(L, S, t, meta)
    if site:
        out.append(("C-100", "Site plan", site))
    out += [("S-100", "Foundation plan", sheet_foundation(L, S, meta)),
            ("S-101", "Framing plan", sheet_framing(L, S, t, meta)),
            ("A-101", "Decking plan", sheet_decking(L, S, t, meta))]
    if L.rail:
        out.append(("A-201", "Railing plan + elevation", sheet_rail(L, S, t, meta)))
    out.append(("A-301", "Section + front elevation", sheet_section(L, S, t, meta)))
    cov = sheet_covers(L, S, t, meta)
    if cov:
        out.append(("A-401", "Roof covers — plan + section", cov))
    out.append(("D-501", "Details", sheet_details_steel(L, S, t, meta) if L.spec.framing.system == "steel" else sheet_details(L, S, t, meta)))
    return out
