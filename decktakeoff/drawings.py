"""SVG drawing sheets from the scene boxes + layout — the same geometry the 3D model is built from.
Sheets: G-001 general notes & design criteria (the permit-set sheet) · S-100 foundation plan · S-101 framing plan ·
A-101 decking plan · A-201 rail plan + elevation · A-301 section + front elevation · D-501 details.
Every sheet: 1000 x 700 field, GSX title block, cream ground, ink / gold. Design intent; the stamped set governs."""
from __future__ import annotations

import html as _html
import math
import re
import textwrap
from .catalog import HANGER_FOR_JOIST
from datetime import date
from types import SimpleNamespace as _NS
from typing import Callable, Dict, List, Optional, Tuple

from .catalog import RAIL_SYSTEMS, decking_facts, actual, rail_name
from .layout import Layout
from .spec import post_words, post_base_sku, covers_of
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
def TH(*a, halo=CREAM, **k):
    """T() with a paper-colored halo, for a label that crosses linework."""
    return T(*a, **k).replace("<text ", f'<text stroke="{halo}" stroke-width="2.4" stroke-linejoin="round" paint-order="stroke" ', 1)
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
    body = list(body) + _PANEL.pop("labels", [])     # callout words still pending from the last detail panel
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
    crit = _design_criteria(L)
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
    eps_ = getattr(L, "edge_posts", None) or []
    struct = [("Footings", sm["posts"].split(" on ")[-1]), ("Posts", sm["posts"].split(" on ")[0]), ("Beams", beams_txt), ("Joists", sm["joists"]), ("Rims", sm["rims"])]
    if eps_:
        struct.append(("Edge posts", f"{len(eps_)} under the doubled rims at the outline corners ({eps_[0].label}-{eps_[-1].label}, worst {max(e.load for e in eps_):,.0f} lb): "
                                     f"the rims span post to post as flush beams, no cantilever — S-100"))
    struct += [("Ledger", t.schedule.get("Ledger", "—")), ("Decking", sm["decking"]), ("Rail", sm["rail"])]
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
    site = _site_lines(s)
    for ln in site:
        for k_, w_ in enumerate(textwrap.wrap(ln, 74)[:3]):
            o.append(T(x2 + (8 if k_ else 0), yy, w_, 8, 400)); yy += 12
    if flags is not None:
        o.append(T(x2, yy + 12, "FLAGS (INTERNAL — remove before the permit submittal)", 9, 800, fill=GOLD)); yy += 28
        for f in [f for f in flags if f.severity in ("STOP", "ENGINEER", "CODE")][:14]:
            o.append(T(x2, yy, f.severity, 7.5, 800, fill="#b3261e" if f.severity == "STOP" else GOLD)); o.append(T(x2 + 62, yy, textwrap.shorten(f.text, 66, placeholder="…"), 7.8, 400)); yy += 11.5
    return sheet("G-001", "General notes · design criteria", "Loads, codes, structure summary, sheet index, site — the permit-set cover", o, "No scale", meta)


def sheet_general_notes(L, meta) -> Optional[str]:
    """G-002: the job's numbered general notes (site.general_notes, or site.plan["general_notes"]) — the jurisdiction's
    requirements the permit reviewer reads; None when the job has none."""
    s = L.spec
    notes = getattr(s.site, "general_notes", None) or (s.site.plan or {}).get("general_notes") or []
    if not notes:
        return None
    o = [T(24, 24, "GENERAL NOTES", 9, 800, fill=GOLD)]
    wrapped = [textwrap.wrap(str(n), 80) for n in notes]
    half = sum(len(w) for w in wrapped) / 2
    x, y, acc = 24, 46, 0
    for i, w in enumerate(wrapped):
        if x == 24 and acc >= half and i > 0:
            x, y = 506, 46
        o.append(T(x, y, f"{i + 1}.", 9.2, 800, fill=GOLD))
        for j, ln in enumerate(w):
            o.append(T(x + 24, y + j * 13, ln, 9, 400))
        y += 13 * len(w) + 9
        acc += len(w)
    return sheet("G-002", "General notes", "The jurisdiction's requirements for this work — read with G-001 and the details", o, "No scale", meta)


def _design_criteria(L) -> List[Tuple[str, str]]:
    """G-001's design-criteria rows (label, text) for the job: loads, wind, frost, soil, seismic, wildfire, codes, engineering.
    A louvered roof built into the set adds its roof-snow / dead-load / post-reaction wording; the job's own rows
    (site.design_criteria, or site.plan["design_criteria"]: [[label, text], ...]) replace the engine's row of the same
    label (matched on the words before any parenthesis) or are added."""
    s = L.spec
    rows = list(_design_criteria_engine(L))
    key = lambda k: str(k).split(" (")[0].strip().lower()
    roof = __import__("decktakeoff.louvered", fromlist=["has_roofs"]).has_roofs(s) and not (s.geometry.cover or s.geometry.covers)
    if hasattr(L, "parts") and s.framing.footing_type == "diamond_pier":          # the head sits in a dug hole (ESR-1895 4.2)
        rows = [(k, ftin(s.site.frost_depth_in) + " (Diamond Piers: frost protection by the pin design per ICC-ES ESR-1895; the head sits in a dug hole on "
                 "undisturbed soil)") if k == "Frost depth" else (k, v) for k, v in rows]
    for lab, txt in (getattr(s.site, "design_criteria", None) or (s.site.plan or {}).get("design_criteria") or []):
        if key(lab) == "roof snow" and not (roof or s.geometry.cover or s.geometry.covers):
            continue                                                  # a roof-snow row prints only when the set has a roof
        hit = next((i for i, (k, _) in enumerate(rows) if key(k) == key(lab)), None)
        if hit is not None:
            rows[hit] = (str(lab), str(txt))
        else:
            after = next((i for i, (k, _) in enumerate(rows) if key(k) == "dead load"), None) if key(lab) == "roof snow" else None
            rows.insert(after + 1 if after is not None else len(rows), (str(lab), str(txt)))
    if roof:                                                          # a louvered roof built into the set
        out = []
        for k, v in rows:
            if key(k) == "dead load" and "louvered" not in v:
                v += " · louvered roof dead load and post reactions per the roof engineer, carried on the deck posts and piers"
            if key(k) == "design total" and "roof post" not in v:
                v += " · the roof posts add snow + dead + wind uplift to the deck frame and piers (engineered)"
            out.append((k, v))
            if key(k) == "dead load" and not any(key(k2) == "roof snow" for k2, _ in rows):
                out.append(("Roof snow (louvered roof)", f"{s.site.ground_snow_psf:g} psf non-reducible roof snow + sliding snow off the house roof and drift at the wall "
                                                         "(ASCE 7-16 Ch. 7) — louvered roof, engineered"))
        rows = out
    return rows


def _design_criteria_engine(L) -> List[Tuple[str, str]]:
    s = L.spec
    cover = bool(s.geometry.cover or s.geometry.covers)
    crit = [("Deck live load", "40 psf uniform (IRC Table R301.5); guards 200 lb concentrated / 50 plf"),
            ("Ground snow", f"{s.site.ground_snow_psf:g} psf (ground; deck design uses the larger of snow and live)" + (" — snow governs" if s.site.ground_snow_psf > 40 else " — 40 psf live governs") + (f"; {s.site.snow_note}" if s.site.snow_note else "")),
            ("Dead load", "10 psf deck" + ((" · 15 psf porch cover (standing seam steel on sheathing, Hardie soffit; 12 psf actual, 15 used) carried on the deck posts" if s.extras.cover_roof.lower().startswith("standing") else " · 15 psf porch cover (shingles, sheathing, Hardie soffit) carried on the deck posts") if cover else "")),
            ("Roof snow (cover)", f"{s.site.ground_snow_psf:g} psf flat-roof design snow" + (" (PPRBD minimum 30 psf)" if "colorado springs" in (s.site.city or "").lower() else "") + ", sliding snow off the house roof + drift at the house wall per ASCE 7 Ch. 7" if cover else "—"),
            ("Design total", f"{max(z.frame.total_psf for z in L.zones):g} psf on the deck" + (" (hot-tub bay 110 psf)" if s.extras.hot_tub else "") + (" · cover posts add roof snow + dead to the deck frame and footings (engineered)" if cover else "")),
            ("Wind", s.site.wind_note or f"{s.site.wind_speed_mph:g} mph Vult, Exposure C, Risk Cat. II (ASCE 7-16) — confirm special wind region"), ("Frost depth", ftin(s.site.frost_depth_in) + (" (Diamond Piers are frost-protected by the pin design; no excavation)" if s.framing.footing_type == "diamond_pier" else " (footings bear below)")),
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
    return [(k, v) for k, v in crit if not (k == "Roof snow (cover)" and v.strip() in ("—", "-", ""))]   # no cover: no roof-snow row


def _site_lines(s) -> List[str]:
    """G-001's site lines: setbacks and the deck's distances to the lot lines, easements, the site notes. The job's own
    lines (site.site_lines, or site.plan["site_lines"]) replace the generated setback / easement lines."""
    own = getattr(s.site, "site_lines", None) or (s.site.plan or {}).get("site_lines")
    if own:
        return [str(x) for x in own] + (textwrap.wrap(s.site.notes, 70) if s.site.notes else [])
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
    return site


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
    eps_ = getattr(L, "edge_posts", None) or []
    for ep in eps_:                         # under the rims at the outline corners: label inside the deck, toward the house
        o.append(TH(X(ep.x * IN), Y(ep.y * IN) - 9, ep.label, 7.5, 800, "middle", fill="#3f5d8a"))
        rows.append((ep.label, ftin(ep.x), ftin(ep.y), f"{ep.zone} rim", f"{ep.load:,.0f} lb"))
    for bl in L.beam_lines:                 # beam lines are in inches; the plan transform takes feet
        o.append(TH(X(bl.x0 * IN) + 4, Y(bl.y * IN) - 6, bl.label, 7.5, 800, fill=MUTE))
    # dims: beam lines from the front, zone widths
    zs = S.meta["zones"]
    dim_h(o, X, Y(S.y_front) + 16, zs[0]["x0"], zs[-1]["x0"] + zs[-1]["W"], ftin(S.W * 12) + " along the house", up=False)
    for z in zs:
        dim_h(o, X, Y(S.y_front) + 32, z["x0"], z["x0"] + z["W"], f"{z['name']} {ftin(z['W'] * 12)}", up=False)
    used_x = []
    for bl in sorted(L.beam_lines, key=lambda b: -b.y):      # to the front rim of the beam's own zone(s); dims that would stack step out
        zf = max((z["front"] for z in zs if z["name"] in (bl.zones or [])), default=S.y_front)
        xd = X(bl.x1 * IN) + 10
        while any(abs(xd - u) < 14 for u in used_x) or any(abs(xd - X(e_.x * IN)) < 16 and bl.y * IN - 2.5 <= e_.y * IN <= zf + 0.1
                                                           for e_ in (getattr(L, "edge_posts", None) or [])):
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
    if eps_:
        for k_, ln_ in enumerate(textwrap.wrap(f"E = edge post under both doubled rims at an outline corner: the rims span "
                                               f"post to post as {L.zones[0].frame.rim_plies}-ply flush beams, so nothing cantilevers past a flush beam. "
                                               "Rims tied to each post with (4) A35Z (D-502).", 62)):
            o.append(T(sx, yy + 32 + k_ * 10, ln_, 7.2, 500, fill="#3f5d8a"))
        yy += 12 + 10 * len(textwrap.wrap("x" * 200, 62))
    o.append(T(sx, yy + 21, f"Frost {ftin(L.spec.site.frost_depth_in)} · soil {L.spec.site.soil_bearing_psf:,.0f} psf · worst post {max(z.frame.footing_load_lb for z in L.zones):,.0f} lb", 7.2, 400, fill=MUTE))
    if L.spec.framing.system == "steel":
        for k_, ln_ in enumerate([(f"Deck-only piers: 6x6 {post_words(L.spec)} post on {post_base_sku(L.spec)}, steel saddle to the beam (D-502 / 3)."
                                   if L.spec.framing.steel_deck_post == "wood" else "Deck-only piers: 3x3 galvanized HSS stub on a pier-head bracket (D-502 / 3)."),
                                  f"+cover: the 6x6 {post_words(L.spec)} roof-cover post stands on this pier",
                                  f"({post_base_sku(L.spec)}) and carries the deck beam on a steel side bracket (D-502 / 4);",
                                  "roof load adds — the engineer sizes the pier.",
                                  f"Beams: boxed CEMCO {L.spec.framing.steel_joist}, flush (D-502 / 2)."]):
            o.append(T(sx, yy + 36 + k_ * 11, ln_, 7.2, 500))
    return sheet("S-100", "Foundation plan", ("Footings, posts and beam lines with the footing schedule; beams dashed" + (" (below the joists)" if any(b_.kind == "drop" for b_ in L.beam_lines) else "")
                                              if L.beam_lines else "Footings and posts with the footing schedule") + (f"; edge posts {eps_[0].label}-{eps_[-1].label} under the rims" if eps_ else ""), o, "Plan · not to scale · house at the top · dimensions govern", meta)


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
        o.append(TH(X(bl.x0 * IN) + 6, Y(bl.y * IN) - 5, bl.label + suf, 7.5, 800, fill="#3f5d8a"))
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
              + "; ".join(f"{_bl_short(b_)} {ftin(b_.length)}, {len(b_.posts_x)} posts" for b_ in bls_)) if len(bls_) > 2 else "; ".join(t.summary["beams"])
    notes = [t.summary["joists"], t.summary["rims"], t.schedule.get("Ledger", ""), t.schedule.get("Blocking", "blocking one row over the beam, staggered"),
             t.schedule.get("Joist tape", ""), beams_]
    hw = [f"{l.item}: {l.net:g}" for l in t.lines if l.category == "Hardware" and l.unit == "ea"][:8]
    yy = 40
    for n in notes + ["Connectors:"] + hw:
        for ln in textwrap.wrap(n, 40)[:5]:
            o.append(T(nx, yy, ln, 7.6, 400)); yy += 10.5
        yy += 3
    return sheet("S-101", "Framing plan", "Ledger, joists, rims, blocking" + (", beams" if L.beam_lines else ", edge posts" if getattr(L, "edge_posts", None) else "") + "; every member in the model — the cut list is on T-600", o, "Plan · not to scale · house at the top · dimensions govern", meta)


def sheet_decking(L: Layout, S: Scene, t, meta) -> str:
    o = []
    x0, x1, y0, y1 = plan_bounds(S)
    X, Y, sc = plan_xform(x0, x1, y0 - 2, y1, 40, 24, 700, 560)
    house_outline(o, X, Y, sc, S)
    draw_plan_boxes(o, X, Y, sc, S.boxes, ("fascia",), "#777", 0.3)
    if L.plan is not None:       # the field: an end that butts a frame board or a breaker runs under it (the frame, drawn over it,
        from .scene import Box   # reads as the mitred cut); an end at a house wall stops at its cut length
        P_ = L.plan
        bw_in = decking_facts(L.spec.decking.collection)["width"]
        def _seg_d(px, py, x0_, y0_, x1_, y1_):
            dx, dy = x1_ - x0_, y1_ - y0_
            tt = max(0.0, min(1.0, ((px - x0_) * dx + (py - y0_) * dy) / (dx * dx + dy * dy or 1.0)))
            return math.hypot(x0_ + tt * dx - px, y0_ + tt * dy - py)
        def _butts(xe, ym):
            return (any(_seg_d(xe, ym, *b_[:4]) < 1.6 * bw_in for b_ in P_.borders)
                    or any(abs(xe - x_) < 1.6 * bw_in and lo_ - 1 <= ym <= hi_ + 1 for x_, lo_, hi_, _ in P_.dividers))
        field = []
        for r in P_.rows:
            ym = (r.y0 + r.y1) / 2
            field.append(Box("board", (r.x0 - (bw_in / 2 if _butts(r.x0, ym) else 0)) * IN, (r.x1 + (bw_in / 2 if _butts(r.x1, ym) else 0)) * IN,
                             r.y0 * IN, r.y1 * IN, 0.0, 0.0, "deck", 6))
        draw_plan_boxes(o, X, Y, sc, field + [b for b in S.boxes if b.kind == "board" and not (b.tag or "").startswith("pf field")], ("board",), "#8f8f8c", 0.25)
    else:
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
    notes = [(f"Deck surface {ftin(s.geometry.height_in)} above grade; guard {L.rail.height:g}\" where the drop exceeds 30\"" if s.geometry.height_in > 30
              else f"Deck surface {ftin(s.geometry.height_in)} above grade — under 30\", no guard required (IRC R312.1); the {L.rail.height:g}\" rail is the owner's choice") if L.rail else f"Deck surface {ftin(s.geometry.height_in)} above grade",
             (f"{len(L.beam_lines)} {' / '.join(sorted({b_.kind for b_ in L.beam_lines}))} beam lines, {' / '.join(sorted({b_.size + ' ' + b_.species for b_ in L.beam_lines}))} — every line on S-100 / S-101"
              if len(L.beam_lines or []) > 2 else "; ".join(t.summary["beams"])),
             f"Posts {t.summary['posts']}", t.schedule.get("Ledger", ""), t.schedule.get("Joist tape", "")]
    for n in notes:
        for ln in textwrap.wrap(n, 62)[:3]:
            o.append(T(nx, yy, ln, 7.6, 400)); yy += 10.5
        yy += 3
    return sheet("A-301", "Section + front elevation", "Cut through the deepest zone; heights to grade, frost line" + (", cantilever" if any(b_.cantilever > 0.5 for z in L.zones if z.frame for b_ in z.frame.beams) else "") + (", guard" if L.rail else ""), o, "Section left · elevation right · not to a common scale", meta)


def sheet_details(L: Layout, S: Scene, t, meta, panel6: Optional[Tuple[str, Callable]] = None, base: Optional[str] = None) -> str:
    """Schematic details drawn from the job's own parameters. panel6 = (title, draw(o, note)): the caller's own special
    condition in panel 6 (a composite deck's step between its levels); None -> hot-tub bay / flush beam / blocking.
    base = the post base the order carries (the composite passes it; None -> post_base_sku)."""
    o = []
    s = L.spec
    timber = s.is_timber
    jb, jd = L.frame.joist_size, None
    def frame_(x, y, w, h, num, title):
        o.append(R(x, y, w, h, "#fff", INK, 0.8)); o.append(R(x, y, w, 18, INK, "none", 0)); o.append(T(x + 8, y + 13, f"{num}  {title}", 9, 800, fill=GOLD))
    def note(x, y, w, txt):
        yy = y
        for ln in textwrap.wrap(txt, int(w / 4.6)):
            o.append(TH(x, yy, ln, 7.2, 400, halo="#fff")); yy += 9.5
        return yy
    # 1 ledger
    frame_(20, 20, 300, 290, "1", "LEDGER AT THE HOUSE")
    o.append(R(40, 60, 40, 200, FILL["house"], INK, 1.0)); o.append(T(60, 165, "house rim", 7, 700, "middle", MUTE, rot=-90))
    o.append(R(80, 80, 6, 160, "#3f5d8a", "none", 0)); o.append(TH(83, 76, "membrane 12\" up the wall", 6.5, 600, "middle", halo="#fff"))
    o.append(R(86, 100, 22, 60, FILL["timber"], INK, 0.8)); o.append(T(97, 132, "ledger", 6.5, 700, "middle", INK, rot=-90))
    o.append(R(108, 100, 120, 60, FILL["timber"], INK, 0.6)); o.append(T(168, 133, f"{L.frame.joist_size} joist in {'LUS410Z' if timber else (L.spec.framing.hanger or HANGER_FOR_JOIST.get(L.frame.joist_size, 'LUS210Z'))}", 7, 700, "middle"))
    o.append(R(86, 92, 150, 6, FILL["deck"], INK, 0.5)); o.append(TH(140, 89, "decking", 6.5, 600, "middle", halo="#fff"))
    o.append(LN(80, 100, 112, 100, GOLD, 2)); o.append(LN(112, 100, 196, 80, INK, 0.5)); o.append(TH(198, 82, "flashing over the ledger,", 6.5, 600, halo="#fff")); o.append(TH(198, 90, "under the cladding", 6.5, 600, halo="#fff"))
    for yy in (112, 148):
        o.append(LN(58, yy, 108, yy, INK, 1.4)); o.append(C(108, yy, 2.2, INK))
    note(40, 275, 270, t.schedule.get("Ledger", "") + (" · 26 ga wall flashing (WUI)" if s.site.wui_fire_zone else ""))
    # 2 post / beam / cap
    bl = L.beam_lines[0] if L.beam_lines else None
    eps_ = getattr(L, "edge_posts", None) or []
    edge_only = (not bl) and bool(eps_)        # no beam: the doubled rims stand on edge posts
    frame_(340, 20, 300, 290, "2", "POST · RIM · TIES" if edge_only else "POST · BEAM · CAP")
    o.append(R(470, 120, 40, 138, FILL["timber"], INK, 0.9)); o.append(T(490, 195, f"{s.framing.post_size} " + ("edge post" if edge_only else "post"), 7, 700, "middle", INK, rot=-90))
    o.append(R(400, 70, 180, 50, FILL["timber_dk"], INK, 0.9))
    o.append(T(490, 100, (f"{L.frame.rim_plies}-ply {s.framing.joist_size} rim = flush beam" if edge_only else f"{bl.size if bl else ''} {'drop' if (bl and bl.kind == 'drop') else 'flush'} beam"), 7.5, 700, "middle"))
    if edge_only:
        for ax in (458, 506):
            o.append(R(ax, 112, 16, 4, FILL["steel"], INK, 0.5)); o.append(R(ax + (0 if ax < 490 else 12), 112, 4, 18, FILL["steel"], INK, 0.5))
        o.append(T(530, 132, "(4) A35Z — no cap", 6.5, 600))
    else:
        o.append(R(462, 112, 56, 16, FILL["steel"], INK, 0.6)); o.append(T(530, 126, (bl.cap_end if bl else "cap") + (" black" if s.framing.hardware_finish == "black" else ""), 6.5, 600))
    if edge_only:
        o.append(T(400, 64, "joists hang on the rim's inside face (LUS)", 6.5, 600))
    elif bl and bl.kind == "drop":
        o.append(R(400, 56, 180, 14, FILL["timber"], INK, 0.5)); o.append(T(400, 52, "joists bear on the beam, H2.5AZ each", 6.5, 600))
    else:
        o.append(T(400, 64, "joists hang on both faces (LUS)", 6.5, 600))
    bls_ = L.beam_lines or []
    if len(bls_) > 2:          # many beam lines: the count, the size and the worst post — the lines themselves are on S-100 / S-101
        worst = max((max(b_.post_loads) for b_ in bls_ if getattr(b_, "post_loads", None)), default=0)
        note(360, 275, 270, f"{len(bls_)} {' / '.join(sorted({b_.kind for b_ in bls_}))} {' / '.join(sorted({b_.size + ' ' + b_.species for b_ in bls_}))} beam lines, "
                            f"{sum(len(b_.posts_x) for b_ in bls_)} posts" + (f", worst post {worst:,.0f} lb" if worst else "") + " (S-100 / S-101)."
                            + (" Plies on RSS screws, 2 rows @ 12\"; caps with a 1/2\" shim." if any(b_.size.startswith("(2)2x") for b_ in bls_) else ""))
    elif edge_only:
        note(360, 275, 270, f"{len(eps_)} edge posts {eps_[0].label}-{eps_[-1].label} under the rim corners (S-100), worst {max(e.load for e in eps_):,.0f} lb; "
                            f"the rims span post to post as flush beams; no interior beam.")
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
        o.append(R(800, 190, 40, 14, FILL["concrete"], INK, 0.9)); o.append(T(852, 212, "Diamond Pier head", 6.5, 600))
        for dx, dy in ((-1, 1), (1, 1), (-0.5, 1), (0.5, 1)):
            o.append(LN(820, 204, 820 + dx * 60, 204 + 90, INK, 1.2))
        o.append(T(852, 240, f"4 x 50\" pins · {L.frame.footing_model}", 6.5, 600)); o.append(R(806, 180, 28, 10, FILL["steel"], INK, 0.6))
        if base and base.startswith("ABU88"):            # the ABU88's second 5/8" anchor goes into the pier head
            o.append(T(852, 176, f"{base} on the pier bolt", 6.5, 600)); o.append(T(852, 185, "+ a 5/8\" anchor into the head", 6.5, 600))
        else:
            o.append(T(852, 188, f"{base or post_base_sku(s)} on the pier bolt", 6.5, 600))
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
    o.append(R(405, 470, 215, 30, FILL["timber"], INK, 0.6)); o.append(T(512, 488, "rim", 7, 700, "middle"))
    o.append(R(397, 456, 60, 14, FILL["border"], INK, 0.5)); o.append(T(427, 452, "border", 6.5, 600, "middle"))
    for k in range(3):
        o.append(R(461 + k * 54, 456, 50, 14, FILL["deck"], INK, 0.4))
    o.append(T(540, 452, f"field · {ftin(s.deck_gap)} gaps", 6.5, 600, "middle"))
    o.append(LN(397, 470, 397, 500, GOLD, 1.5)); o.append(T(393, 520, f"overhang {ftin(S.meta['edge'] * 12)}" + ("" if s.decking.fascia else " — no fascia"), 6.5, 600, "end"))
    if s.decking.fascia:
        o.append(R(399, 470, 6, 30, FILL["fascia"], INK, 0.5)); o.append(T(393, 490, "fascia", 6.5, 600, "end"))
    note(360, 560, 270, t.schedule.get("Field", "")[:160] + (" · Cortex screws + plugs on the borders and dividers (2 per bearing) and the stair treads"
                                                          if (s.decking.border_fastener or "").lower().startswith("cortex") else ""))
    # 6 zone-specific
    if panel6 is not None:                    # the caller draws the special condition (a composite deck: the step between its levels)
        frame_(660, 330, 320, 270, "6", panel6[0])
        panel6[1](o, note)
    else:
        frame_(660, 330, 320, 270, "6", "HOT-TUB BAY" if s.extras.hot_tub else ("FLUSH BEAM" if any(b.kind == "flush" for b in L.beam_lines) else "BLOCKING"))
    if panel6 is not None:
        pass
    elif s.extras.hot_tub:
        note(680, 360, 290, f"Tub bay in zone {s.extras.hot_tub_zone or 'A'}: {ftin(s.extras.hot_tub_bay_in)} square against the house — sister a joist to every joist across the bay, block between, design 100 psf; engineer confirms. Owner's electrician: 50A GFCI circuit + disconnect.")
    elif any(b.kind == "flush" for b in L.beam_lines):
        note(680, 360, 290, "Flush beam: top of beam = top of joists. Joists hang on both faces in LUS hangers; opposing hangers per Simpson"
                            + (" and the stamped set." if s.extras.engineered else "'s installation notes."))
    else:
        note(680, 360, 290, t.schedule.get("Blocking", "Blocking one row over the beam, staggered up and down so every block can be end-nailed."))
    return sheet("D-501", "Details", "Ledger · " + ("post / rim / ties" if edge_only else "post / beam / cap") + " · footing · rail post · deck edge · the job's special condition", o, "Schematic details, not to scale", meta)


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


def sheet_site(L: Layout, S: Scene, t, meta, outlines: Optional[List[tuple]] = None, marks: Optional[List[tuple]] = None) -> Optional[str]:
    """C-100 site plan: the parcel and the house from the county GIS (plan frame, feet), the new decks, roof covers and
    stairs, distances to the lot lines, the reference setbacks, north arrow, street, lot coverage and the parcel facts.
    outlines: [(polygon, label[, (x, y) label point])] when the deck is drawn as several pieces (the levels of a composite
    deck); None -> the scene's one outline. marks: [(rects [(x0, x1, y0, y1)], label, color, posts [(x, y)])] other new
    work drawn dashed with its distance to the rear lot line (a louvered roof, an option stair). A composite (outlines
    given) draws the setback lines over the deck with short tags and keys them in the right column, wraps long labels,
    and lists the deck label in the right column; setback_ref["lines"] = [{"d", "label", "color", "dash"}] adds offset
    lines (a steps limit)."""
    s = L.spec
    sp = s.site.plan or {}
    if not sp.get("parcel"):
        return None
    comp = outlines is not None
    marks = marks or []
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
    sb_lines = []                                        # a composite: the offset lines, drawn over the decks with short tags
    if ref.get("rear") and sp.get("setback_offset"):     # the rear setback as an offset of the rear lot line (a sloped / jogged rear line)
        cxp, cyp = sum(xs) / len(xs), sum(ys) / len(ys)
        rear_edges = [(a, b) for a, b in zip(par, par[1:] + par[:1]) if a[1] > 0 and b[1] > 0 and abs(b[0] - a[0]) > abs(b[1] - a[1]) and math.hypot(b[0] - a[0], b[1] - a[1]) > 1.0]
        lines_ = [(ref["rear"], ref.get("rear_label") or f"{ref['rear']}' rear setback", "#8a6d2a", "6 4")]
        if ref.get("rear_deck"):            # where a low deck may reach (a projection allowance into the rear setback)
            lines_.append((ref["rear_deck"], ref.get("rear_deck_label") or f"{ref['rear_deck']}' — deck projection limit", "#b3261e", "2 3"))
        for ex in ref.get("lines") or []:   # more offset lines (a steps limit): {"d": 15, "label": "...", "color": "#2f6f8f", "dash": "8 3"}
            lines_.append((float(ex["d"]), ex.get("label") or f"{float(ex['d']):g}' from the rear lot line", ex.get("color") or "#2f6f8f", ex.get("dash") or "8 3"))
        t_lab = float(sp.get("rear_label_t", 0.16))
        for d, lab_, col_, dash_ in lines_:
            best = None
            segs = []
            for a, b in rear_edges:
                ln_ = math.hypot(b[0] - a[0], b[1] - a[1]); nx_, ny_ = -(b[1] - a[1]) / ln_, (b[0] - a[0]) / ln_
                if (cxp - a[0]) * nx_ + (cyp - a[1]) * ny_ < 0:
                    nx_, ny_ = -nx_, -ny_
                p0, p1 = (a[0] + nx_ * d, a[1] + ny_ * d), (b[0] + nx_ * d, b[1] + ny_ * d)
                segs.append((p0, p1))
                if not comp:
                    o.append(LN(X(p0[0]), Y(p0[1]), X(p1[0]), Y(p1[1]), col_, 0.9, dash_))
                if best is None or ln_ > best[0]:
                    best = (ln_, p0, p1)
            if comp:
                sb_lines.append((d, lab_, col_, dash_, segs, best))
            elif best:
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
        o.append(T(X(cx), Y(cy), "EXISTING HOUSE", 9, 900, "middle", MUTE))
        hl = sp.get("house_label", "one-story + garage (no work)")
        for k_, ln_ in enumerate(textwrap.wrap(hl, 44)[:4] if comp else [hl]):      # a composite wraps a long label
            o.append(T(X(cx), Y(cy) + 12 + k_ * 9.5, ln_, 7.5, 600, "middle", MUTE))
    # decks
    outs = [tuple(e) for e in outlines] if outlines else [(deck_outline(S), None)]
    for e in outs:
        o.append(PG([(X(x), Y(y)) for x, y in e[0]], FILL["deck"], INK, 1.2))
    out = [p for e in outs for p in e[0]]
    if comp:
        pass                                                       # each level is named after the stairs are drawn (the deck label: right column)
    elif sp.get("deck_label") and sp.get("deck_label_inside"):     # inside the deck (a setback line runs under its front)
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
    treads_ = [(X(b.x0), X(b.x1), Y(b.y0), Y(b.y1)) for b in S.boxes if b.kind == "tread"] if comp else []
    for e in (outs if comp else []):                               # a composite: each level named on it, at its label point
        if len(e) > 1 and e[1]:
            lx_, ly_ = e[2] if len(e) > 2 and e[2] else (sum(q[0] for q in e[0]) / len(e[0]), sum(q[1] for q in e[0]) / len(e[0]))
            ls_ = str(e[1]).split("\n")
            cx_, cy_ = X(lx_), Y(ly_)
            hw_, hh_ = max(len(w) for w in ls_) * 2.1 + 3, len(ls_) * 4.5 + 2
            for _ in range(40):                                    # clear of a stair drawn on the level (an inset stair)
                hit = [r for r in treads_ if r[0] < cx_ + hw_ and r[1] > cx_ - hw_ and r[2] < cy_ + hh_ and r[3] > cy_ - hh_]
                if not hit:
                    break
                cx_ += 2 if sum(r[0] + r[1] for r in hit) / (2 * len(hit)) < cx_ else -2
            for k_, w in enumerate(ls_):
                o.append(T(cx_, cy_ + 3 + (k_ - (len(ls_) - 1) / 2) * 9, w, 6.8, 900, "middle", "#f3ead9"))
    # other new work drawn dashed (a louvered roof, an option stair), then (a composite) the setback lines over everything
    for rects, lab_, col_, posts_ in marks:
        for x0_, x1_, y0_, y1_ in rects:
            o.append(R(X(x0_), Y(y0_), (x1_ - x0_) * sc, (y1_ - y0_) * sc, "none", col_, 1.1, 'stroke-dasharray="5 3"'))
        for px_, py_ in posts_:
            o.append(R(X(px_) - 2.2, Y(py_) - 2.2, 4.4, 4.4, col_, INK, 0.5))
    for d, lab_, col_, dash_, segs, best in sb_lines:
        for p0, p1 in segs:
            o.append(LN(X(p0[0]), Y(p0[1]), X(p1[0]), Y(p1[1]), col_, 1.0, dash_))
        if best:                                                   # a short tag at the line's left end; the key is in the right column
            _, p0, p1 = best
            q0, q1 = (p0, p1) if X(p0[0]) < X(p1[0]) else (p1, p0)
            ux, uy = X(q1[0]) - X(q0[0]), Y(q1[1]) - Y(q0[1])
            n_ = math.hypot(ux, uy) or 1.0
            o.append(TH(X(q0[0]) + ux / n_ * 16, Y(q0[1]) + uy / n_ * 16 - 3, f"{d:g}'", 7.2, 900, "start", col_))
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
    for rects, lab_, col_, posts_ in marks:                       # each mark's corner nearest the rear lot line
        pts_ = [(x_, y_) for x0_, x1_, y0_, y1_ in rects for x_ in (x0_, x1_) for y_ in (y0_, y1_)]
        if pts_:
            bm = min(pts_, key=lambda q: (nearest(q[0], q[1], rear_pred) or (9e9, None))[0])
            probes.append(((lab_, bm[0], bm[1]), rear_pred))
    lx_, rx_ = min(p[0] for p in out), max(p[0] for p in out)
    left_pred = lambda a, b: side_pred(a, b) and (a[0] + b[0]) / 2 < lx_
    right_pred = lambda a, b: side_pred(a, b) and (a[0] + b[0]) / 2 > rx_
    for pred_ in (left_pred, right_pred):       # the deck corner nearest each side line (the lines are not parallel to the deck)
        bv = min(out, key=lambda q: (nearest(q[0], q[1], pred_) or (9e9, None))[0])
        probes.append((("deck edge", bv[0], bv[1]), pred_))
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
        for k_, w in enumerate(textwrap.wrap(ln, 84) if comp else [ln]):          # a composite wraps a long line
            o.append(T(x2 + (8 if k_ else 0), yy, w, 8.5, 500)); yy += 12
    if comp and sp.get("deck_label"):
        o.append(T(x2, yy + 10, "NEW DECK", 9, 800, fill=GOLD)); yy += 26
        for w in textwrap.wrap(re.sub(r"^NEW DECK\s*[—-]\s*", "", sp["deck_label"]), 84):
            o.append(T(x2, yy, w, 8.5, 500)); yy += 12
    o.append(T(x2, yy + 10, "LOT COVERAGE", 9, 800, fill=GOLD)); yy += 26
    for k, v in sp.get("coverage") or []:
        o.append(T(x2, yy, k, 8, 700)); o.append(T(x2 + 445, yy, textwrap.shorten(v, 54, placeholder="…"), 8, 500, "end")); yy += 12
    o.append(T(x2, yy + 10, "SETBACKS", 9, 800, fill=GOLD)); yy += 26
    sb = [f"Decks are 30\" or less above grade — not held to the principal setbacks (city deck handout)",
          f"Roof covers: part of the principal structure — they replace the two existing covers in place; the 2024 aerial shows the existing main roof ~1'-5\" shallower: field-verify the existing post line",
          (ref.get("label") or "")]
    if sp.get("setback_notes"):
        sb = list(sp["setback_notes"])
    elif comp:                                                     # a composite: the G-001 site lines (no parcel notes) + the reference
        nl = set(textwrap.wrap(s.site.notes, 70)) if s.site.notes else set()
        sb = [x for x in _site_lines(s) if x not in nl] + [ref.get("label") or ""]
    sb += [f"Measured (red): to the nearest lot line from the new work — GIS, not survey"]
    for ln in [x for x in sb if x]:
        for w in textwrap.wrap(ln, 80):
            o.append(T(x2, yy, w, 8, 500)); yy += 11.5
    if comp and (sb_lines or marks):                               # the key to the lines on the plan
        yy += 4
        for d, lab_, col_, dash_, segs, best in sb_lines:
            o.append(LN(x2, yy - 3, x2 + 22, yy - 3, col_, 1.4, dash_))
            for k_, w in enumerate(textwrap.wrap(lab_, 72)):
                o.append(T(x2 + 30, yy, w, 8, 700 if k_ == 0 else 500, fill=col_)); yy += 11.5
        for rects, lab_, col_, posts_ in marks:
            o.append(R(x2, yy - 8, 22, 7, "none", col_, 1.1, 'stroke-dasharray="4 2"'))
            for k_, w in enumerate(textwrap.wrap(lab_, 72)):
                o.append(T(x2 + 30, yy, w, 8, 700 if k_ == 0 else 500, fill=col_)); yy += 11.5
    o.append(T(x2, yy + 10, "SITE WORK", 9, 800, fill=GOLD)); yy += 26
    work = ["Remove the two decks, the two roof covers and the box step; haul off", "Diamond Pier foundations (no excavation spoils), 6-mil poly + 2\" gravel under the decks",
            ("New concrete landing pad at the stair" if any(st_.landing == "concrete pad" for st_ in s.stairs) else "Stair lands on grade (no pad)"), "Roof drainage: covers shed to grade at the low eave, away from the house", "Call 811 before the piers; protect the lawn and the owner's blinds"]
    if comp:                                                       # a composite's own default list (the job's site_work wins)
        work = [w for w in ("Remove the existing deck and haul off" if s.extras.demo_existing else "",
                            "Diamond Pier foundations: each precast head set in a dug hole on undisturbed soil, 4 pins driven through it"
                            if s.framing.footing_type == "diamond_pier" else "Footings per S-100",
                            "Call 811 before the footings", "Protect the lawn, beds and hardscape along the work") if w]
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


def _bl_short(b_):
    """A beam line's name without its type and size: the zones and any position word ("R (front)")."""
    z = "+".join(b_.zones)
    return b_.label[b_.label.rfind(" " + z) + 1:] if z and (" " + z) in b_.label else b_.label.split()[-1]


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
    customer=True leaves the internal flags block off G-001. A composite deck (two levels, a wrap) gets whole-deck sheets
    in the global frame (composite_sheets)."""
    if hasattr(L, "parts"):
        return composite_sheets(L, t, flags, scene, customer=customer)
    if customer:
        flags = None
    S = scene or build_scene(L)
    S_roof = S                          # a louvered roof has its own sheet (A-403, louvered.sheet); the deck sheets leave it out
    if any(getattr(b, "layer", "") in ("site", "louvered") for b in S.boxes):      # the yard model is for the 3D views, not the drawing sheets
        import dataclasses as _dc
        S = _dc.replace(S, boxes=[b for b in S.boxes if getattr(b, "layer", "") not in ("site", "louvered")])
    _MAT_COLORS.clear()
    for k in ("deck", "border", "drink", "fascia"):
        if k in S.materials:
            _MAT_COLORS[k] = S.materials[k]["color"]
    FILL["deck"] = _MAT_COLORS.get("deck", FILL["deck"]); FILL["border"] = _MAT_COLORS.get("border", FILL["border"])
    meta = sheet_meta(L, customer=customer)
    _STEEL["on"] = L.spec.framing.system == "steel"
    out = [("G-001", "General notes · design criteria", "")]              # built last, from the sheets actually in the set
    gn = sheet_general_notes(L, meta)                                      # the job's own numbered notes, when it has them
    if gn:
        out.append(("G-002", "General notes", gn))
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
    lv = __import__("decktakeoff.louvered", fromlist=["sheet"]).sheet(L, S_roof, t, meta)      # None without a louvered roof
    if lv:
        out.append(("A-403", "Louvered roof — plan, section, post", lv))
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


def _stair_pairs(L) -> list:
    """(stair spec, stair layout) for every stair of the job: a composite deck's stairs live in its parts."""
    if hasattr(L, "parts"):
        return [(ss, sl) for p in L.parts for ss, sl in zip(p.spec.stairs or [], p.layout.stairs or [])]
    return list(zip(L.spec.stairs or [], L.stairs or []))


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
    for ss, st in _stair_pairs(L):
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
    return _axo_sheet("A-002", "Isometric — assembled, labeled", "Everything you see called out: piers, decking, picture frame, skirt, stair" + (", roof covers" if covers_of(L.spec) else "") + ", finishes", L, S, t, meta, bx, fit=fit, key=key,
                      note=("House shown for context only (no work). The CEMCO steel deck frame under the decking is called out on S-102 and A-003; cover framing is wood: 2x8 rafters, "
                            + ", ".join(f"{c_['name'].lower()} {c_.get('beam', '(2)2x10')} beam" for c_ in __import__('decktakeoff.spec', fromlist=['covers_of']).covers_of(L.spec)) + ", 6x6 Douglas fir posts.")
                      if L.spec.framing.system == "steel" else "House shown for context only (the deck work only). The frame under the decking is called out on S-102 and A-003.")


def sheet_iso_exploded(L: Layout, S: Scene, t, meta) -> str:
    bx = [b for b in S.boxes if (b.kind not in ("ground", "glass") and not _house(b)) or (b.tag or "").startswith("blind") or (b.tag or "") == "snow retention bar"]
    cov = any(b.kind in ("cpost", "rafter", "ssroof") for b in bx)
    sub = "Each build layer lifted in order: piers · posts" + (" + knee braces" if any(b.kind == "brace" for b in bx) else "") + (" · beams" if (L.beam_lines or (L.frame and L.frame.beams)) else "") + " · frame · decking" + (" · stair" if any(b.kind in ("tread", "stringer") for b in bx) else "") + (" · rail" if L.rail else "") + (" · roof covers layer by layer" if cov else "")
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
            + ("; field-skewable hangers on the bay faces" if "field-skewable" in items else "")
            + ("; the doubled rims stand on the edge posts with A35Z ties" if getattr(L, "edge_posts", None) else "")
            + ("; double rims in concealed-flange hangers" if "concealed" in items else "") + ".")
    return _axo_sheet("S-102", "Structure isometric — frame, labeled", "Piers, post bases, posts" + (", knee braces" if any(b.kind == "brace" for b in bx) else "") + (", post caps, beam" if bls else ", A35Z rim ties" if getattr(L, "edge_posts", None) else "") + ("s" if len(bls) > 1 else "") + ", joists, "
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
            dk_ = f"DECK · {ftin(zt * 12)} AFG"; wt_ = len(dk_) * 3.9 + 8          # the tag sized to its words
            o.append(LN(hx - 40, y, hx, y, "#b3261e", 0.9, "3 2")); o.append(R(hx - 40 - wt_, y - 11, wt_, 10, CREAM, "#b3261e", 0.5)); o.append(T(hx - 44, y - 3, dk_, 6.4, 800, "end", "#b3261e"))
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
             "Heights AFG = above finished grade at the " + ("beam line" if L.beam_lines else "posts") + "; field-verify grade before setting the piers",
             ]
    from .spec import covers_of as _cov
    if _cov(s):
        notes += ["Clear heights are to the underside of the beam / ledger above the deck surface",
                  "Roof covers: black standing seam on 2x8 rafters, Hardie fascia / rakes / soffit; slope to the yard"]
    if s.framing.system == "steel":
        notes.append("Deck frame: CEMCO cold-formed steel; HardieTrim skirt covers the track rims")
    else:
        bls_ = L.beam_lines or []
        bl_ = bls_[0] if bls_ else None
        notes.append(f"Deck frame: {s.framing.joist_size} {s.framing.joist_grade} @ {L.frame.spacing:g}\" OC"
                     + ((f" on {len(bls_)} {' / '.join(sorted({b_.kind for b_ in bls_}))} beam lines, {' / '.join(sorted({b_.size + ' ' + b_.species.replace('DF#1', 'DF #1') for b_ in bls_}))}, "
                         f"{sum(b_.n_posts for b_ in bls_)} posts" + (f" + {len(L.edge_posts)} edge posts under the rims" if getattr(L, "edge_posts", None) else "")
                         + " (S-100 / S-101)") if len(bls_) > 1 else
                        (f" on a {bl_.size} {bl_.species.replace('DF#1', 'DF #1')} {bl_.kind} beam, {bl_.n_posts} posts" if bl_ else ""))
                     + (" with 4x4 knee braces both ways" if s.framing.knee_braces else ""))
    if L.rail and s.geometry.height_in > 30:
        notes.append(f"Guard {L.rail.height:g}\" min. on every open side — the surface is {ftin(s.geometry.height_in)} above grade (IRC R312.1)")
    elif L.rail:
        notes.append(f"No guard required (IRC R312.1: the surface is {ftin(s.geometry.height_in)} above grade, under 30\"); {L.rail.system} {L.rail.height:g}\" rail on the sides the owner chose")
    else:
        notes.append("No guard required: every walking surface is under 30\" above grade (IRC R312.1)")
    yy = 358
    for n_ in notes:
        o.append(T(20, yy, "· " + n_, 7.6, 500)); yy += 12
    return sheet("A-202", "Elevations", "Front from the yard and both ends, drawn from the model — deck" + (" and roof-cover heights" if _cov(s) else " heights"), o, "Elevations · orthographic · not to scale · heights govern", meta)


# ------------------------------------------------------------------ connection details (permit set)
_PANEL = {"r": 10000.0}


def _detail_note(s) -> str:
    """The detail sheets' scale note: an engineered job's details defer to the engineer of record; a prescriptive one's to the plans."""
    return ("Schematic details, not to scale · the engineer of record's details govern" if s.extras.engineered
            else "Schematic details, not to scale · the plans and the manufacturers' instructions govern")


def _lead(o, ax, ay, tx, ty, txt, size=6.6, anchor_="start", w_=600):
    """A leader from (ax, ay) to a label at (tx, ty); the label wraps to stay inside the current detail panel."""
    o.append(LN(ax, ay, tx, ty - 2, INK, 0.5)); o.append(C(ax, ay, 1.3, INK, "none", 0))
    room = max(14, min(34, int((_PANEL["r"] - 6 - tx) / (size * 0.52))))
    for j, ln in enumerate(textwrap.wrap(txt, room)):    # the words go on top of everything in the panel (see _panel / sheet)
        _PANEL.setdefault("labels", []).append(TH(tx + (2 if anchor_ == "start" else -2), ty + j * 8, ln, size, w_, anchor_, halo="#fff"))


def _panel(o, x, y, w, h, num, title):
    o.extend(_PANEL.pop("labels", []))           # the previous panel's callout words, last, so no line crosses them
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
    hs = L.spec.framing.hanger or HANGER_FOR_JOIST.get(js, "LUS210Z")
    items = " ".join(ln.item for ln in getattr(t, "lines", []))
    js_ = js.replace('x', '')
    rim_h = [w_ for k_, w_ in (("HUCQ", f"HUCQ{js_}-2-SDS concealed-flange"), (f"SUR{js_}-2Z", f"SUR/SUL{js_}-2Z skewed (45°)"),
                               (f"LSSU{js_}-2Z", f"LSSU{js_}-2Z field-skewed (bay face)")) if k_ in items]
    _lead(o, x + 38, y + 62, x + 24, y + 192, ("Double rims at the ledger in Simpson " + " · ".join(rim_h) + " double hangers") if rim_h else
                                             f"Double rim in a Simpson HUCQ{js_}-2-SDS concealed-flange hanger at the ledger")
    _lead(o, x + 186, y + 60, x + 166, y + 192, f"Simpson {hs} face-mount hanger, every joist, 10d HDG in every hole")
    _lead(o, x + 59, y + 120, x + 24, y + 246, "Picture-frame joist 1-1/2\" inboard of the rim")
    _lead(o, x + 42, y + 160, x + 166, y + 246, f"{fr.rim_plies}-ply {js} rim, GRK RSS 3-1/8\", 2 rows @ 12\" staggered")
    # 3 joists over the drop beam / into the flush beam
    flush = bool(bl) and bl.kind == "flush"
    two_by = bsize.startswith(("(2)2x", "(3)2x"))
    plyfast = "plies laminated GRK RSS 3-1/8\", 2 rows @ 12\" staggered" if two_by else "plies through-bolted 1/2\" @ 24\" staggered"
    sb = [b_ for b_ in (s.framing.beams or []) if b_.kind == "flush"]
    setback = min((float(b_.setback_in or 0) for b_ in sb), default=0.0)
    edge_only = (not bl) and bool(getattr(L, "edge_posts", None))       # no beam: the doubled rims on edge posts carry the joists
    rimsz = f"{fr.rim_plies}-ply {js} rim"
    x, y = P[2]; _panel(o, x, y, W3, H2, "3", "JOISTS INTO THE FLUSH BEAM — PLAN + SECTION" if flush else ("JOISTS INTO THE DOUBLED RIM — PLAN + SECTION" if edge_only else "JOISTS ON THE DROP BEAM — SECTION"))
    if edge_only:
        _wood(o, x + 20, y + 40, W3 - 40, 26)
        o.append(LN(x + 20, y + 53, x + W3 - 20, y + 53, INK, 0.5))
        for k in range(5):
            xx = x + 36 + k * 58
            _wood(o, xx, y + 66, 7, 120, dark=True)
            o.append(R(xx - 3, y + 66, 13, 9, "#7b8186", INK, 0.6))
        o.append(T(x + W3 / 2, y + 36, "FRONT OF THE DECK — the doubled rim on the edge posts", 6.6, 800, "middle", MUTE))
        _wood(o, x + 30, y + 214, 120, 46); _wood(o, x + 150, y + 216, 10, 42, dark=True); o.append(R(x + 150, y + 236, 12, 22, "#7b8186", INK, 0.6))
        o.append(R(x + 30, y + 207, 250, 7, FILL["deck"], INK, 0.5)); _wood(o, x + 160, y + 216, 120, 42, dark=True)
        _lead(o, x + 40, y + 70, x + 170, y + 100, f"Simpson {hs} every joist off the rim's inside face, 10d HDG every hole")
        _lead(o, x + 60, y + 238, x + 24, y + 192, f"{rimsz} = the flush beam; plies RSS-screwed 2 rows @ 12\"")
        _lead(o, x + 210, y + 236, x + 236, y + 180, f"{js} joist, top flush with the rim")
        o.append(T(x + 24, y + 278, f"Joists span ledger to rim at {fr.spacing:g}\" OC; the rim spans post to post — no cantilever", 6.6, 700))
    elif flush:
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
        o.append(T(x + 24, y + 278, (f"Joists hang on both faces: from the ledger to the beam, and {ftin(setback)} out to the front rim"
                                     + (" — the rim stands on edge posts (S-100)" if getattr(L, "edge_posts", None) else "") if setback > 3
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
    x, y = P[3]; _panel(o, x, y, W3, H2, "4", "DOUBLED RIM ON THE EDGE POST — ELEVATION" if edge_only else f"{bsize} BEAM ON THE 6x6 — ELEVATION")
    _wood(o, x + 20, y + 60, W3 - 40, 46)
    for k in range(6):
        _bolt(o, x + 36 + k * 48, y + (70 if k % 2 == 0 else 96))
    if edge_only:                       # two A35Z angles each side of the post, rim to post — no cap
        for ax in (x + 122, x + 168):
            o.append(R(ax, y + 96, 14, 4, "#5b6166", INK, 0.5)); o.append(R(ax + (0 if ax < x + 150 else 10), y + 96, 4, 22, "#5b6166", INK, 0.5))
    else:
        o.append(R(x + 128, y + 104, 48, 14, "#5b6166", INK, 0.6)); o.append(R(x + 124, y + 60, 4, 58, "#5b6166", INK, 0.5)); o.append(R(x + 176, y + 60, 4, 58, "#5b6166", INK, 0.5))
    _wood(o, x + 136, y + 106 if edge_only else 118, 32, 180 if edge_only else 168)
    if s.framing.knee_braces:
        o.append(PG([(x + 168, y + 190), (x + 168, y + 176), (x + 240, y + 106), (x + 254, y + 106)], FILL["timber_dk"], INK, 0.7))
        _bolt(o, x + 168 + 6, y + 186); _bolt(o, x + 244, y + 112 - 30 + 30)
    if edge_only:
        _lead(o, x + 128, y + 104, x + 24, y + 140, "(2) Simpson A35Z per rim to the post, 10d x 1-1/2\" HDG every hole — no cap")
        _lead(o, x + 60, y + 72, x + 24, y + 36, f"{rimsz}, GRK RSS 3-1/8\" through the plies, 2 rows 2\" from top / bottom, staggered @ 12\" OC")
        _lead(o, x + 150, y + 220, x + 24, y + 230, f"6x6 {pw} edge post, top cut to the rim bottom, under both rim ends at the corner")
    else:
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
    _lead(o, x + 158, y + 150, x + 24, y + 200, "The Diamond Pier's own 1/2\" galvanized bolt through the base — nothing set in concrete")
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
        o.append(T(x + 20, y + 40, "Post length, top of the standoff base to the " + ("rim" if edge_only else "beam") + " seat", 7.2, 800))
        o.append(T(x + 20, y + 52, "cut in the field to the string line; the " + ("rims sit" if edge_only else "beam tops sit") + " flush with the joists", 6.6, 500, fill=MUTE))
        yy = y + 74
        for t_, a_ in (("Support" if edge_only else "Beam line", 20), ("Posts", 170), ("Post", 230)):
            o.append(T(x + a_, yy, t_.upper(), 6.4, 800, fill=MUTE))
        for bl_ in (L.beam_lines or []):
            yy += 16
            o.append(T(x + 20, yy, bl_.label, 6.8, 700)); o.append(T(x + 170, yy, str(len(bl_.posts_x)), 6.8, 600))
            o.append(T(x + 230, yy, inch(bl_.post_len, 16) if bl_.post_len < 24 else ftin(bl_.post_len), 6.8, 700))
        eps_ = getattr(L, "edge_posts", None) or []
        if eps_:                            # under the rims at the outline corners: the rim's bottom is the seat
            yy += 16
            o.append(T(x + 20, yy, f"EDGE POSTS {eps_[0].label}-{eps_[-1].label} (under the rims)", 6.8, 700)); o.append(T(x + 170, yy, str(len(eps_)), 6.8, 600))
            o.append(T(x + 230, yy, inch(L.edge_post_len, 16) if L.edge_post_len < 24 else ftin(L.edge_post_len), 6.8, 700))
            yy += 16
            for ln_ in textwrap.wrap("Edge post: centred under both rim ends at the corner, post top cut to the rim bottom, (2) Simpson A35Z per rim "
                                     "to the post. The doubled rims span post to post as flush beams — nothing cantilevers past a flush beam.", 78):
                o.append(T(x + 20, yy, ln_, 6.6, 600)); yy += 11
        if any(bl_.post_len < 8 for bl_ in (L.beam_lines or [])):
            yy += 26
            for ln_ in textwrap.wrap("Under 8\" there is little room for the pier head, the standoff base and a post: check the grade at each pier "
                                     "before setting (see the field flags); where it is tight the beam bears on the pier through a bracket, no post.", 78):
                o.append(T(x + 20, yy, ln_, 6.6, 600, fill="#b3261e")); yy += 11
    return sheet("D-502", "Connection details — frame", (f"Ledger{' on the cantilever' if cant else ''} · hangers · joists into the rim · the rim on the edge post · pier + base · " if edge_only else
                 f"Ledger{' on the cantilever' if cant else ''} · hangers · joists {'into' if flush else 'on'} the beam · {bsize} on the cap · pier + base · ")
                 + ("knee braces" if s.framing.knee_braces else "post lengths"), o,
                 _detail_note(s), meta)


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
    _lead(o, x + 165, y + 100, x + 150, y + 40, f"Picture-frame border, {dk} square edge, mitred, {pf_fast} 2 per bearing @ {L.spec.joist_spacing:g}\"")
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
    o.append(R(x + 20, y + 40, W3 - 40, 110, FILL["house"], INK, 0.6)); o.append(T(x + 30, y + 54, "house floor framing (joists run ⟂ or ∥ — engineer)" if s.extras.engineered
                                                                                    else "house floor framing — a floor joist, or blocking where ∥", 6.4, 700, fill=MUTE))
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
    for k, (lab, wd) in enumerate((("joist", 2), ("PF joist", 2), ("block", 2), ("rim (2-ply)", 4)) + ((("beam", 4),) if L.beam_lines else ())):
        xx = x + 30 + k * 56
        _wood(o, xx, y + 90, 3 * 6 * (2 if wd == 4 else 1), 70)
        o.append(R(xx - 2, y + 86, 3 * 6 * (2 if wd == 4 else 1) + 4, 4, "#111", "none", 0))
        o.append(T(xx + 9, y + 176, lab, 6.4, 700, "start")); o.append(T(xx + 9, y + 186, f"{wd}\" tape", 6.4, 800, "start", "#b3261e"))
    tape_txt = ("Nichigo G-Tape 3035 (black) on every top edge before decking, lapped over the ends and down the sides 1/2\"; "
                + (f"one row of {js} blocking over the beam, (3) structural screws each end" if L.beam_lines else f"{js} blocks under the angled borders, (3) structural screws each end"))
    for i, ln in enumerate(textwrap.wrap(tape_txt, 64)[:4]):
        o.append(T(x + 24, y + 222 + i * 10, ln, 6.6, 600))
    # 6 fastening schedule
    x, y = P[5]; _panel(o, x, y, W3, H2, "6", "FASTENING SCHEDULE")
    items = " ".join(ln.item for ln in getattr(t, "lines", []))          # what the order carries: the schedule says the same
    bls = L.beam_lines or []
    kinds = {b.kind for b in bls}
    two_by = any(b.size.startswith(("(2)2x", "(3)2x")) for b in bls)
    four_by = any(b.size.startswith("(2)4x") for b in bls)
    hang = s.framing.hanger or HANGER_FOR_JOIST.get(js, "LUS210Z")
    cap = bls[0].cap_mid if bls else "BC46Z"
    cortex = (s.decking.border_fastener or "").lower().startswith("cortex")
    rows = [("Ledger to house", "LedgerLOK 3-5/8\", 2 rows staggered 12\" OC" + (" — engineer" if s.extras.ledger_on_cantilevered_floor else "")),
            ("Lateral", "(4) DTT1Z, 1/2\" rod into the floor framing"),
            ("Joist to ledger", f"{hang}, 10d HDG every hole")]
    js_ = js.replace('x', '')
    rim_rows = [w_ for k_, w_ in (("HUCQ", f"HUCQ{js_}-2-SDS"), (f"SUR{js_}-2Z", f"SUR/SUL{js_}-2Z (45°)"), (f"LSSU{js_}-2Z", f"LSSU{js_}-2Z (bay)")) if k_ in items]
    rows.append(("Rim to ledger", " · ".join(rim_rows) if rim_rows else f"HUCQ{js_}-2-SDS, SDS screws"))
    if f"SUR{js_}Z" in items:
        rows.append(("Joist to 45° rim", f"SUR/SUL{js_}Z skewed hanger, 10d HDG every hole"))
    if f"LSSU{js_}Z" in items:
        rows.append(("Joist to bay face", f"LSSU{js_}Z bent to the bay's angle, 10d HDG every hole"))
    rows.append(("Rim plies", "GRK RSS 3-1/8\", 2 rows @ 12\" staggered"))
    if bls:
        rows += [("Joist to beam", f"{hang} each side of the flush beam, 10d HDG" if kinds == {"flush"} else "H2.5AZ each joist + rim, 10d x 1-1/2\"" if kinds <= {"drop"}
                  else f"{hang} at flush beams; H2.5AZ at drop beams"),
                 ("Beam plies", "GRK RSS 3-1/8\", 2 rows @ 12\" staggered" if two_by and not four_by else "1/2\" x 8\" HDG bolts, 2 rows staggered @ 24\"" if not two_by
                  else "RSS on the (2)2x, 1/2\" bolts on the (2)4x"),
                 ("Beam to post", f"{cap} cap, SD screws" + (" (1/2\" shim, (2)2x beam)" if two_by and cap.startswith("BC46") else ""))]
    if getattr(L, "edge_posts", None):
        rows.append(("Rim to edge post", "(2) A35Z per rim per post, 10d x 1-1/2\""))
    rows += [("Post to pier", f"{post_base_sku(s)} on the Diamond Pier, SD screws"),
             ("Knee braces", "1/2\" through-bolt each end (x10 / x12 / x6)") if s.framing.knee_braces else ("Blocking", "(3) structural screws each end"),
             ("Field boards", f"{fsys}, every joist, every gap"),
             ("Borders / fascia", ("Borders: Cortex + plugs · fascia: Cap-Tor xd" if cortex else "Cap-Tor xd color-matched, pre-drilled")),
             ("Rail posts", "(4) HeadLOK 6\" into blocking" if rs.get("surface") else "(2) 7/16\" bolts per post")]
    yy = y + 36
    for a, b in rows:
        o.append(T(x + 14, yy, a, 6.8, 800)); o.append(T(x + 106, yy, textwrap.shorten(b, 52, placeholder="…"), 6.6, 500)); yy += 18
        o.append(LN(x + 10, yy - 12, x + W3 - 10, yy - 12, "#e2dccf", 0.5))
    return sheet("D-504", "Connection details — deck edge, rail, lateral", "Rail post mounting · picture frame + fascia · guard bay · DTT1Z lateral ties · joist tape · fastening schedule", o,
                 _detail_note(L.spec), meta)


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
                 _detail_note(L.spec), meta)


# ================================================================== composite (multi-level) decks: whole-deck sheets in the global frame
# A composite deck is two or more parts (the levels of a two-level deck, or the legs of a wrap) placed in one global frame
# (composite.py). These sheets draw the whole deck at once from the composite scene (every box already in the global frame)
# and from each part's layout moved through its placement: one foundation plan numbering every post, one framing plan, one
# decking plan, the rail, the elevations of both levels with the step face, sections through the level change, the labeled
# isometrics of the whole.
BLUE, RED, BROWN = "#3f5d8a", "#b3261e", "#5a4520"


def _rect_union(rects, eps: float = 1e-6) -> List[List[Tuple[float, float]]]:
    """The outline of a union of axis-aligned rectangles [(x0, x1, y0, y1)]: one polygon per connected piece, the largest
    first, collinear points merged."""
    rects = [r for r in rects if r[1] - r[0] > eps and r[3] - r[2] > eps]
    if not rects:
        return []
    xs = sorted({v for r in rects for v in (r[0], r[1])})
    ys = sorted({v for r in rects for v in (r[2], r[3])})
    nx_, ny_ = len(xs) - 1, len(ys) - 1
    cell = [[any(r[0] - eps <= (xs[i] + xs[i + 1]) / 2 <= r[1] + eps and r[2] - eps <= (ys[j] + ys[j + 1]) / 2 <= r[3] + eps for r in rects)
             for j in range(ny_)] for i in range(nx_)]
    ins = lambda i, j: 0 <= i < nx_ and 0 <= j < ny_ and cell[i][j]
    nxt: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for i in range(nx_):
        for j in range(ny_):
            if not cell[i][j]:
                continue
            if not ins(i, j - 1):
                nxt.setdefault((i, j), []).append((i + 1, j))
            if not ins(i + 1, j):
                nxt.setdefault((i + 1, j), []).append((i + 1, j + 1))
            if not ins(i, j + 1):
                nxt.setdefault((i + 1, j + 1), []).append((i, j + 1))
            if not ins(i - 1, j):
                nxt.setdefault((i, j + 1), []).append((i, j))
    loops = []
    while any(nxt.values()):
        start = next(k for k, v in nxt.items() if v)
        loop, cur = [start], start
        while True:
            n = nxt[cur].pop(0)
            if n == start:
                break
            loop.append(n); cur = n
            if not nxt.get(cur):
                break
        pts = [(xs[i], ys[j]) for i, j in loop]
        out = []
        for k, p in enumerate(pts):            # drop the points where the outline runs straight on
            a, b = pts[k - 1], pts[(k + 1) % len(pts)]
            if abs((p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])) > eps:
                out.append(p)
        if len(out) >= 3:
            loops.append(out)
    return sorted(loops, key=lambda q: -abs(_poly_area_in(q)))


def _poly_edges(P):
    return list(zip(P, P[1:] + P[:1]))


def _inside_poly(P, x, y) -> bool:
    c = False
    for (x0, y0), (x1, y1) in _poly_edges(P):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


def _outward(P, a, b) -> Tuple[float, float]:
    """The unit normal of side a-b pointing out of polygon P (plan feet; the sheet's x and y run the same way)."""
    L_ = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    nx, ny = (b[1] - a[1]) / L_, -(b[0] - a[0]) / L_
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if _inside_poly(P, mx + nx * 0.05, my + ny * 0.05):
        nx, ny = -nx, -ny
    return nx, ny


def _lighten(c: str, k: float = 0.55) -> str:
    """The color pushed toward the paper: what stands beyond the cut in a section."""
    h = c.lstrip("#")
    h = "".join(ch * 2 for ch in h) if len(h) == 3 else h[:6]
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return c
    return "#%02x%02x%02x" % (int(r + (0xf7 - r) * k), int(g + (0xf2 - g) * k), int(b + (0xe8 - b) * k))


def _chain(o, M, at, pts, size=6.8, horiz=True, up=True, left=True):
    """A chain of dimensions through pts (feet) along x (horiz) or y, its words in inches; a piece too short for its words
    keeps its ticks and drops the words."""
    for (a, b), lab in zip(zip(pts, pts[1:]), chain_labels([v * 12 for v in pts])):
        if b - a < 0.02:
            continue
        room = abs(M(b) - M(a)) > len(lab) * size * 0.56 + 4
        if horiz:
            dim_h(o, M, at, a, b, lab if room else "", size, up=up)
        else:
            dim_v(o, M, at, a, b, lab if room else "", size, left=left)


def _comp_levels(CL) -> list:
    """Each part of a composite deck in the global frame (feet): its zones, outline, beam lines with their posts, edge posts,
    breakers, deck surface height."""
    out = []
    for i, p in enumerate(CL.parts):
        pl, L = p.placement, p.layout
        zones = []
        for z in L.zones:
            x0, x1, y0, y1 = pl.box(z.x0 * IN, (z.x0 + z.W) * IN, z.wall_y * IN, (z.wall_y + z.D) * IN)
            zones.append(_NS(name=z.name, label=z.label, x0=x0, x1=x1, y0=y0, y1=y1, z=z, ledger=bool(z.frame.ledger)))
        if p.spec.geometry.outline:
            poly = [pl.pt(float(a), float(b)) for a, b in p.spec.geometry.outline]
        else:
            u = _rect_union([(q.x0, q.x1, q.y0, q.y1) for q in zones])
            poly = u[0] if u else []
        beams = []
        for bl in L.beam_lines:
            posts = [_NS(x=pl.pt(px * IN, bl.y * IN)[0], y=pl.pt(px * IN, bl.y * IN)[1], load=ld, zone=zn)
                     for px, ld, zn in zip(bl.posts_x, bl.post_loads, bl.post_zone)]
            beams.append(_NS(bl=bl, label=bl.label, kind=bl.kind, size=bl.size, species=bl.species, a=pl.pt(bl.x0 * IN, bl.y * IN),
                             b=pl.pt(bl.x1 * IN, bl.y * IN), posts=posts, post_len=bl.post_len, length=bl.length, short=_bl_short(bl),
                             zones=bl.zones, pieces=bl.pieces))
        eps_ = [_NS(label=ep.label, x=pl.pt(ep.x * IN, ep.y * IN)[0], y=pl.pt(ep.x * IN, ep.y * IN)[1], load=ep.load, zone=ep.zone)
                for ep in (getattr(L, "edge_posts", None) or [])]
        fy = max(z.wall_y + z.D for z in L.zones) * IN
        divs = [(pl.pt(dx * IN, fy)[0], pl.pt(dx * IN, fy)[1], lab) for dx, Ld, lab in (L.divider_x or [])]
        if L.plan is not None:          # an outline-laid field: its breakers
            divs = [(pl.pt(x * IN, hi * IN)[0], pl.pt(x * IN, hi * IN)[1], lab) for x, lo, hi, lab in L.plan.dividers]
        out.append(_NS(i=i, name=p.name, part=p, pl=pl, L=L, spec=p.spec, t=p.takeoff, top=p.spec.geometry.height_in * IN,
                       h_in=p.spec.geometry.height_in, zones=zones, poly=poly, beams=beams, eps=eps_, divs=divs))
    return out


def _div_word(lab: str, gx: float) -> str:
    """A breaker's name on a whole-deck sheet: a zone line keeps its name (DA/B); one placed by distance ('D@16'-11 1/2"', in its
    part's frame) reads by its distance from the deck's left end."""
    return f"@ {ftin(gx * 12)}" if "@" in lab else lab


def _lv_word(lv) -> str:
    """'Lower level' -> 'lower' (a part named otherwise keeps its name)."""
    return lv.name.split()[0].lower() if lv.name.lower().endswith(" level") else lv.name


def _lv_tag(lv) -> str:
    return f"{lv.name.upper()} · deck {ftin(lv.h_in)} above grade"


def _step_faces(levels) -> list:
    """Where two levels at different heights share an outline side: [(lower, upper, (x0, y0), (x1, y1))], feet."""
    out = []
    for a in levels:
        for b in levels:
            if b.i <= a.i or abs(a.top - b.top) < 0.05:
                continue
            lo, hi = (a, b) if a.top < b.top else (b, a)
            for p0, p1 in _poly_edges(a.poly):
                for q0, q1 in _poly_edges(b.poly):
                    if abs(p0[0] - p1[0]) < 0.02 and abs(q0[0] - q1[0]) < 0.02 and abs(p0[0] - q0[0]) < 0.05:
                        lo_, hi_ = max(min(p0[1], p1[1]), min(q0[1], q1[1])), min(max(p0[1], p1[1]), max(q0[1], q1[1]))
                        if hi_ - lo_ > 0.1:
                            out.append((lo, hi, (p0[0], lo_), (p0[0], hi_)))
                    elif abs(p0[1] - p1[1]) < 0.02 and abs(q0[1] - q1[1]) < 0.02 and abs(p0[1] - q0[1]) < 0.05:
                        lo_, hi_ = max(min(p0[0], p1[0]), min(q0[0], q1[0])), min(max(p0[0], p1[0]), max(q0[0], q1[0]))
                        if hi_ - lo_ > 0.1:
                            out.append((lo, hi, (lo_, p0[1]), (hi_, p0[1])))
    return out


def _plan_rect(b: Box) -> Tuple[float, float, float, float]:
    """A box's footprint in plan; a box tilted in a vertical plane (a stringer, a stair rail) by its true horizontal extent."""
    if b.rot and b.rot_axis in ("x", "y"):
        from .axo import corners
        cs = corners(b)
        return min(q[0] for q in cs), max(q[0] for q in cs), min(q[1] for q in cs), max(q[1] for q in cs)
    return b.x0, b.x1, b.y0, b.y1


def _cdraw(o, X, Y, sc, boxes, kinds, stroke=INK, sw=0.4, dash="", fill=None, pred=None):
    for b in sorted([b for b in boxes if b.kind in kinds and (pred is None or pred(b))], key=lambda q: (q.z0, q.z1)):
        f = fill or fill_for(b)
        ex = f'stroke-dasharray="{dash}"' if dash else ""
        if b.shape == "cyl":
            o.append(C(X((b.x0 + b.x1) / 2), Y((b.y0 + b.y1) / 2), (b.x1 - b.x0) / 2 * sc, f, stroke, sw, dash))
        elif b.rot and b.rot_axis == "z":
            cx, cy = X((b.x0 + b.x1) / 2), Y((b.y0 + b.y1) / 2)
            o.append(f'<g transform="rotate({math.degrees(b.rot):.2f} {cx:.1f} {cy:.1f})">' + R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, f, stroke, sw, ex) + "</g>")
        else:
            x0, x1, y0, y1 = _plan_rect(b)
            o.append(R(X(x0), Y(y0), (x1 - x0) * sc, (y1 - y0) * sc, f, stroke, sw, ex))


def _cwindow(levels, S, pad=3.0, front_pad=4.0, back_pad=3.0, boxes=None):
    """The plan window: every level's outline, the stairs and landings, with margins (feet)."""
    xs = [p[0] for lv in levels for p in lv.poly]
    ys = [p[1] for lv in levels for p in lv.poly]
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - back_pad, max(ys) + front_pad
    for b in (boxes if boxes is not None else S.boxes):
        t_ = b.tag or ""
        if b.kind in ("tread", "stringer", "riser") or ("landing" in t_ and b.kind in ("board", "footing", "post")):
            bx0, bx1, by0, by1 = _plan_rect(b)
            x0, x1, y0, y1 = min(x0, bx0 - 1.5), max(x1, bx1 + 1.5), min(y0, by0 - 1.5), max(y1, by1 + front_pad * 0.6)
    return x0, x1, y0, y1


def _cxform(win, px0, py0, pw, ph, valign="top"):
    """Plan transform centred across the box (x right, y toward the yard down the sheet)."""
    x0, x1, y0, y1 = win
    sc = min(pw / (x1 - x0), ph / (y1 - y0))
    ox = px0 + (pw - (x1 - x0) * sc) / 2
    oy = py0 + ((ph - (y1 - y0) * sc) / 2 if valign == "middle" else 0.0)
    return (lambda x: ox + (x - x0) * sc), (lambda y: oy + (y - y0) * sc), sc


def _house_rects(S, levels, win):
    """The house footprint near the deck (plan, feet, clipped to the window): the job's measured blocks, else the house
    boxes of the measured model, else a band behind every zone that is ledgered to the house. (x0, x1, y0, y1, kind)"""
    top = max(lv.top for lv in levels)
    rects = []
    job = getattr(S, "_job_spec", None)
    for h in ((job.geometry.house_blocks if job is not None else []) or []):
        rects.append((float(h[0]), float(h[1]), float(h[2]), float(h[3]), str(h[4]).lower() if len(h) > 4 else ""))
    if not rects:
        for b in S.boxes:
            if b.kind in ("house", "wall") and b.shape != "mesh" and b.z0 < top + 2 and b.z1 > 0.5:
                rects.append((b.x0, b.x1, b.y0, b.y1, "brick" if "chimney" in (b.tag or "") else ""))
    if not rects:
        for lv in levels:
            for z in lv.zones:
                if z.ledger:
                    rects.append((z.x0, z.x1, win[2] - 2.0, z.y0, ""))
    x0w, x1w, y0w, y1w = win
    clip = []
    for x0, x1, y0, y1, k in rects:
        a, b, c, d = max(x0, x0w - 1), min(x1, x1w + 1), max(y0, y0w - 1), min(y1, y1w)
        if b - a > 0.05 and d - c > 0.05:
            clip.append((a, b, c, d, k))
    return clip


def _draw_house(o, X, Y, sc, S, levels, win, hid, label=True):
    """The existing house in plan, hatched, under the deck; brick masses (a chimney) go on top (_draw_bricks)."""
    rects = _house_rects(S, levels, win)
    o.append(f'<defs><pattern id="{hid}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             f'<rect width="7" height="7" fill="#efe8da"/><line x1="0" y1="0" x2="0" y2="7" stroke="#d3c8b3" stroke-width="1.1"/></pattern></defs>')
    for poly in _rect_union([r[:4] for r in rects if r[4] not in ("cantilever", "brick")]):
        o.append(PG([(X(x), Y(y)) for x, y in poly], f"url(#{hid})", INK, 1.3))
    for r in rects:
        if r[4] == "cantilever":
            o.append(R(X(r[0]), Y(r[2]), (r[1] - r[0]) * sc, (r[3] - r[2]) * sc, "none", "#8a8172", 0.8, 'stroke-dasharray="4 3"'))
    if label:
        best = None
        for lv in levels:
            for z in lv.zones:
                if z.ledger and (best is None or (z.x1 - z.x0) > (best.x1 - best.x0)):
                    best = z
        if best is not None:
            o.append(TH(X((best.x0 + best.x1) / 2), Y(best.y0) - 9, "EXISTING HOUSE — no work", 7.6, 800, "middle", "#8a8172", halo="#efe8da"))
    return rects


def _draw_bricks(o, X, Y, sc, rects):
    for r in rects:
        if r[4] == "brick":
            o.append(R(X(r[0]), Y(r[2]), (r[1] - r[0]) * sc, (r[3] - r[2]) * sc, "#c9b29b", INK, 0.9))
            if (r[1] - r[0]) * sc > 12:
                o.append(T(X((r[0] + r[1]) / 2) + 2, Y((r[2] + r[3]) / 2), "chimney", 6.0, 800, "middle", "#5d4c3c", rot=-90 if (r[3] - r[2]) > (r[1] - r[0]) else 0))


def _draw_levels(o, X, Y, levels, fills=None, sw=1.2):
    for lv in levels:
        o.append(PG([(X(x), Y(y)) for x, y in lv.poly], (fills[lv.i] if fills else "none"), INK, sw))


def _draw_steps(o, X, Y, steps, lab=True, size=6.6):
    """The step faces between levels: a heavy gold line along each; the rise named once, on the longest piece."""
    for lo, hi, a, b in steps:
        o.append(LN(X(a[0]), Y(a[1]), X(b[0]), Y(b[1]), GOLD, 3.0))
    if lab and steps:
        lo, hi, a, b = max(steps, key=lambda s_: math.hypot(s_[3][0] - s_[2][0], s_[3][1] - s_[2][1]))
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if abs(a[0] - b[0]) < 0.02:
            o.append(TH(X(mx) - 6, Y(my), f"STEP {inch(hi.h_in - lo.h_in)}", size, 900, "middle", "#8a6510", rot=-90))
        else:
            o.append(TH(X(mx), Y(my) - 5, f"STEP {inch(hi.h_in - lo.h_in)}", size, 900, "middle", "#8a6510"))


def _level_tags(o, X, Y, levels, size=8.2, dy=13, fill=INK, halo=CREAM):
    for lv in levels:
        z = max(lv.zones, key=lambda q: (q.x1 - q.x0) if (q.x1 - q.x0) > (q.y1 - q.y0) * 0.8 else 0)
        o.append(TH(X((z.x0 + z.x1) / 2), Y(z.y0) + dy, _lv_tag(lv), size, 900, "middle", fill, halo=halo))


def _notes_cols(o, x, y, w, items, size=7.4, lh=10.0, gap=3.0, ymax=606.0, cols=1, colgap=18, cw_k=0.56):
    """Wrapped notes in one or more columns from (x, y), a column break only between paragraphs; ('#', text) is a heading
    (kept with the paragraph after it). Returns the bottom y."""
    cw = (w - colgap * (cols - 1)) / cols
    chars = max(20, int(cw / (size * cw_k)))
    paras = []
    for it in items:
        if isinstance(it, tuple) and it[0] == "#":
            paras.append(("#", [it[1]])); continue
        if not it:
            continue
        ls = textwrap.wrap(str(it), chars)
        paras.append(("p", [ln if k == 0 else "  " + ln for k, ln in enumerate(ls)]))
    hgt = lambda p: 14 if p[0] == "#" else len(p[1]) * lh + gap
    target = sum(hgt(p) for p in paras) / max(1, cols)
    yy, ci, acc, ybot = y, 0, 0.0, y
    for k, p in enumerate(paras):
        if cols > 1 and ci < cols - 1 and k > 0 and paras[k - 1][0] != "#" and acc + hgt(p) / 2 > target * (ci + 1):
            ci += 1; yy = y
        xx = x + ci * (cw + colgap)
        if p[0] == "#":
            o.append(T(xx, yy + 2, p[1][0], 8.6, 800, fill=GOLD)); yy += 14
        else:
            for ln in p[1]:
                if yy < ymax:
                    o.append(T(xx, yy, ln, size, 400))
                yy += lh
            yy += gap
        acc += hgt(p)
        ybot = max(ybot, yy)
    return ybot


def _leaders(o, items, x_col, anchor="start", y_min=6.0, y_max=600.0, lh=8.6, size=6.6, chars=38, gap=4.0):
    """Labels stacked in a column at x_col, each on a leader to its anchor point, top to bottom without overlaps.
    items = [(ax, ay, text)]."""
    rows = []
    for ax, ay, txt in sorted(items, key=lambda q: q[1]):
        lines = textwrap.wrap(txt, chars) or [""]
        rows.append([max(ay, y_min), lines, ax, ay])
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        rows[i][0] = max(rows[i][0], prev[0] + lh * len(prev[1]) + gap)
    over = (rows[-1][0] + lh * len(rows[-1][1])) - y_max if rows else 0
    if over > 0:
        rows[-1][0] -= over
        for i in range(len(rows) - 2, -1, -1):
            rows[i][0] = min(rows[i][0], rows[i + 1][0] - lh * len(rows[i][1]) - gap)
    for y, lines, ax, ay in rows:
        o.append(LN(ax, ay, x_col, y - 3, INK, 0.5)); o.append(C(ax, ay, 1.4, INK, "none", 0))
        for j, ln in enumerate(lines):
            o.append(TH(x_col + (2 if anchor == "start" else -2), y + j * lh, ln, size, 700 if j == 0 else 500, anchor))


_STAIR_TAG = re.compile(r"^(?:(?P<part>[^:]+): )?(?:tread \d+|stringer|stair skirt|landing \d+) (?P<side>.+?)(?: flight \d+)?$")


def _stair_groups(S, levels, boxes=None) -> list:
    """The stairs in the model, one group per (part, stair side): its treads, stringers, risers, skirts and landing boards,
    the footprint, the stair's layout + spec from its part, whether it is cut into a level (inset) and the option it is in."""
    groups: Dict[Tuple[str, str], list] = {}
    for b in (boxes if boxes is not None else S.boxes):
        m = _STAIR_TAG.match(b.tag or "")
        if m and b.kind in ("tread", "stringer", "fascia", "board"):
            groups.setdefault((m.group("part") or "", m.group("side")), []).append(b)
    out = []
    for (part, side), bx in groups.items():
        lv = next((q for q in levels if q.name == part), levels[0])
        sl, ss = None, None
        for ss_, sl_ in zip(lv.spec.stairs or [], lv.L.stairs or []):
            if sl_.side == side:
                sl, ss = sl_, ss_
        rs = [_plan_rect(b) for b in bx if b.kind in ("tread", "board")]
        if not rs:
            continue
        risers = [b for b in (boxes if boxes is not None else S.boxes) if b.kind == "riser"
                  and any(r[0] - 0.2 <= (b.x0 + b.x1) / 2 <= r[1] + 0.2 and r[2] - 0.2 <= (b.y0 + b.y1) / 2 <= r[3] + 0.2 for r in rs)]
        fp = (min(r[0] for r in rs), max(r[1] for r in rs), min(r[2] for r in rs), max(r[3] for r in rs))
        tr = [_plan_rect(b) for b in bx if b.kind == "tread"]
        cx, cy = (fp[0] + fp[1]) / 2, (fp[2] + fp[3]) / 2
        bb = (min(p[0] for p in lv.poly), max(p[0] for p in lv.poly), min(p[1] for p in lv.poly), max(p[1] for p in lv.poly))
        out.append(_NS(lv=lv, side=side, boxes=bx + risers, fp=fp, treads=tr, st=sl, ss=ss,
                       name=(getattr(ss, "name", None) or "Stair") if ss else "Stair",
                       option=(getattr(ss, "option", "") or "") if ss else "",
                       # cut into its level: the spec says so, or the stair stands inside the level's extent (a notch in its outline)
                       inset=bool(getattr(ss, "inset", False)) or (bb[0] + 0.05 < cx < bb[1] - 0.05 and bb[2] + 0.05 < cy < bb[3] - 0.05)))
    return out


def _stair_words(g) -> str:
    st = g.st
    if not st:
        return g.name
    gg = st.geo
    return f"{g.name}: {inch(st.width, 8)} wide · {gg.risers} risers @ {inch(gg.riser_in, 16)} · {gg.treads} tread{'s' if gg.treads != 1 else ''} @ {inch(gg.tread_in, 16)}"


_NUM = re.compile(r"\d+(?:[,./]\d+)*(?:'-\d+(?: \d+/\d+)?\"|\"|')?")


def _merge_texts(texts: List[str], names: List[str]) -> str:
    """One text for the levels' texts: identical -> said once; the same words with different numbers -> the numbers side by
    side after the level names ('lower / upper: 2x10 ledger x 29'-2" / 33'-11" total ...'); else each level's own."""
    texts = [t_ for t_ in texts if t_]
    if not texts:
        return ""
    if len(set(texts)) == 1:
        return texts[0]
    sks = [_NUM.sub("\x00", t_) for t_ in texts]
    nums = [_NUM.findall(t_) for t_ in texts]
    if len(set(sks)) == 1 and len({len(n_) for n_ in nums}) == 1 and len(texts) == len(names):
        pieces = sks[0].split("\x00")
        out = pieces[0]
        for i, piece in enumerate(pieces[1:]):
            vals = [n_[i] for n_ in nums]
            out += (vals[0] if len(set(vals)) == 1 else " / ".join(vals)) + piece
        return f"{' / '.join(names)}: {out}"
    return " · ".join(f"{nm}: {t_}" for nm, t_ in zip(names, texts))


def _merged_schedule(t, levels) -> dict:
    """The composite takeoff's schedule with the levels' texts merged (_merge_texts)."""
    out = {}
    names = [_lv_word(lv) for lv in levels]
    for k in (t.schedule or {}):
        texts = [lv.t.schedule.get(k, "") for lv in levels]
        out[k] = _merge_texts(texts, names) if all(texts) else " · ".join(f"{nm}: {t_}" for nm, t_ in zip(names, texts) if t_)
    return out


# ------------------------------------------------------------------ G-001 (whole deck)
def sheet_notes_composite(CL, S, t, flags, meta, levels, steps, index) -> str:
    s = CL.spec
    o = []
    o.append(T(24, 24, "PROJECT", 9, 800, fill=GOLD))
    lv_txt = " · ".join(f"{lv.name} ({' + '.join(z.name for z in lv.zones)}) {lv.L.deck_sf:g} SF, {ftin(lv.h_in)} above grade" for lv in levels)
    lines = textwrap.wrap(f"{s.job}", 92) + [f"{s.site.address}, {s.site.city} {s.site.state} {s.site.zip}".strip(", "), f"Prepared for {s.client}" if s.client else ""]
    y = 40
    for ln in [x for x in lines if x]:
        o.append(T(24, y, ln, 10, 600)); y += 14
    for ln in textwrap.wrap(f"{CL.deck_sf:g} SF in {len(levels)} levels: {lv_txt}", 104):
        o.append(T(24, y, ln, 8.8, 600)); y += 12
    o.append(T(24, y + 12, "DESIGN CRITERIA", 9, 800, fill=GOLD)); y += 28
    for k, v in _design_criteria(CL):
        for i, ln in enumerate(textwrap.wrap(v, 92)[:3]):
            o.append(T(24, y, k if i == 0 else "", 8.3, 800)); o.append(T(150, y, ln, 8.3, 400)); y += 11.6
        y += 1
    o.append(T(24, y + 12, "STRUCTURE", 9, 800, fill=GOLD)); y += 28
    fr = s.framing
    n_ft = sum(len(b.posts) for lv in levels for b in lv.beams) + sum(len(lv.eps) for lv in levels)
    bls = [b for lv in levels for b in lv.beams]
    worst = max((p.load for b in bls for p in b.posts), default=0)
    ms = _merged_schedule(t, levels)
    groups = [g for g in _stair_groups(S, levels) if not g.option]
    struct = [("Footings", f"{n_ft} " + (f"Diamond Pier {CL.frame.footing_model}" if fr.footing_type == "diamond_pier" else fr.footing_type.replace("_", " ") + " footings")
                           + " — " + " · ".join(f"{_lv_word(lv)} {sum(len(b.posts) for b in lv.beams) + len(lv.eps)}" for lv in levels)),
              ("Posts", f"{fr.post_size} {post_words(s)} on {_post_base_name(s, t)} bases: " + " · ".join(f"{_lv_word(lv)} " + " / ".join(sorted({ftin(b.post_len) for b in lv.beams})) for lv in levels if lv.beams)),
              ("Beams", f"{len(bls)} {' / '.join(sorted({b.kind for b in bls}))} beam lines, {' / '.join(sorted({b.size + ' ' + b.species for b in bls}))}, {n_ft} posts"
                        + (f" (worst {worst:,.0f} lb)" if worst else "") + " — " + "; ".join(f"{_lv_word(lv)} " + ", ".join(b.short for b in lv.beams) for lv in levels if lv.beams) + " (S-100 / S-101)"),
              ("Joists", t.summary.get("joists", "")), ("Rims", t.summary.get("rims", "")), ("Ledger", ms.get("Ledger", "—"))]
    if steps:
        lo, hi = steps[0][0], steps[0][1]
        struct.append(("Level change", f"The {hi.name.lower()} is {inch(hi.h_in - lo.h_in)} above the {lo.name.lower()}; each level stands on its own posts and beams"
                                       + "".join(" — " + _stair_words(g) + (", cut into the " + g.lv.name.lower() if g.inset else "") for g in groups if g.st and g.st.landing == "deck")
                                       + " (S-101 / A-301)"))
    struct += [("Decking", t.summary.get("decking", "")), ("Rail", t.summary.get("rail", ""))]
    for k, v in struct:
        for i, ln in enumerate(textwrap.wrap(v, 96)[:3]):
            o.append(T(24, y, k if i == 0 else "", 8.3, 800)); o.append(T(150, y, ln, 8.3, 400)); y += 11.6
    x2 = 600
    o.append(T(x2, 24, "SHEET INDEX", 9, 800, fill=GOLD))
    yy = 40
    for num, title in index:
        o.append(T(x2, yy, num, 8.5, 800, fill=GOLD)); o.append(T(x2 + 52, yy, title, 8.5, 500)); yy += 13
    o.append(T(x2, yy + 12, "SITE", 9, 800, fill=GOLD)); yy += 28
    for ln in _site_lines(s):
        for k_, w_ in enumerate(textwrap.wrap(ln, 74)[:3]):
            o.append(T(x2 + (8 if k_ else 0), yy, w_, 8, 400)); yy += 12
    if flags is not None:
        o.append(T(x2, yy + 12, "FLAGS (INTERNAL — remove before the permit submittal)", 9, 800, fill=GOLD)); yy += 28
        for f in [f for f in flags if f.severity in ("STOP", "ENGINEER", "CODE")][:14]:
            o.append(T(x2, yy, f.severity, 7.5, 800, fill=RED if f.severity == "STOP" else GOLD)); o.append(T(x2 + 62, yy, textwrap.shorten(f.text, 66, placeholder="…"), 7.8, 400)); yy += 11.5
    return sheet("G-001", "General notes · design criteria", "Loads, codes, the structure of both levels, sheet index, site — the permit-set cover", o, "No scale", meta)


# ------------------------------------------------------------------ A-100 dimension plan (whole deck, inches)
def _side_kind(lv, a, b, levels, steps, house, rail_pts, groups):
    """What an outline side of a level is: house / ledger, house wall, step, stair, rail, open."""
    horiz, vert = abs(a[1] - b[1]) < 0.02, abs(a[0] - b[0]) < 0.02
    lo_, hi_ = (min(a[0], b[0]), max(a[0], b[0])) if horiz else (min(a[1], b[1]), max(a[1], b[1]))
    for z in lv.zones:
        if z.ledger and horiz and abs(a[1] - z.y0) < 0.05 and lo_ < z.x1 - 0.1 and hi_ > z.x0 + 0.1:
            return "house / ledger"
    for lo, hi, p, q in steps:
        if (vert and abs(p[0] - q[0]) < 0.02 and abs(p[0] - a[0]) < 0.05 and min(p[1], q[1]) < hi_ - 0.1 and max(p[1], q[1]) > lo_ + 0.1) or \
           (horiz and abs(p[1] - q[1]) < 0.02 and abs(p[1] - a[1]) < 0.05 and min(p[0], q[0]) < hi_ - 0.1 and max(p[0], q[0]) > lo_ + 0.1):
            return f"step ({inch(hi.h_in - lo.h_in)} {'down' if lv is hi else 'up'})"
    for g in groups:
        x0, x1, y0, y1 = g.fp
        if g.lv is lv and ((vert and (abs(a[0] - x0) < 0.4 or abs(a[0] - x1) < 0.4) and y0 < hi_ - 0.1 and y1 > lo_ + 0.1)
                           or (horiz and (abs(a[1] - y0) < 0.4 or abs(a[1] - y1) < 0.4) and x0 < hi_ - 0.1 and x1 > lo_ + 0.1)):
            if g.st and (abs((hi_ - lo_) * 12 - g.st.width) < 3 or not g.inset):
                return f"stair {inch(g.st.width)}" + (" (option)" if g.option else "")
    for x0, x1, y0, y1, k in house:
        if vert and (abs(a[0] - x0) < 0.6 or abs(a[0] - x1) < 0.6) and y0 < hi_ - 0.1 and y1 > lo_ + 0.1:
            return "house wall"
        if horiz and (abs(a[1] - y0) < 0.6 or abs(a[1] - y1) < 0.6) and x0 < hi_ - 0.1 and x1 > lo_ + 0.1:
            return "house wall"
    n = sum(1 for px, py in rail_pts if (horiz and abs(py - a[1]) < 0.5 and lo_ - 0.3 <= px <= hi_ + 0.3) or (vert and abs(px - a[0]) < 0.5 and lo_ - 0.3 <= py <= hi_ + 0.3))
    return "RAIL" if n >= 1 else "open"


def _step_face_elevation(o, frame, levels, steps, groups, boxes, cols):
    """The step face seen from the lower level, dimensioned in inches: the skirt runs, the stair opening, the rise, the risers."""
    from .axo import View, draw
    if not steps:
        return False
    lo, hi = steps[0][0], steps[0][1]
    segs = [(a, b) for l_, h_, a, b in steps if l_ is lo and h_ is hi]
    vert = abs(segs[0][0][0] - segs[0][1][0]) < 0.02
    xs_ = segs[0][0][0] if vert else segs[0][0][1]
    probe = (segs[0][0][0] + 0.3, (segs[0][0][1] + segs[0][1][1]) / 2) if vert else ((segs[0][0][0] + segs[0][1][0]) / 2, segs[0][0][1] + 0.3)
    look = 1 if _inside_poly(hi.poly, *probe) else -1
    az = (-90.0 if look > 0 else 90.0) if vert else (180.0 if look > 0 else 0.0)
    along = [v for a, b in segs for v in ((a[1], b[1]) if vert else (a[0], b[0]))]
    u0, u1 = min(along), max(along)
    def near_(q):
        c0, c1 = (q.x0, q.x1) if vert else (q.y0, q.y1)
        a0, a1 = (q.y0, q.y1) if vert else (q.x0, q.x1)
        inside = (c1 >= xs_ - 0.2 and c0 <= xs_ + 7.0) if look > 0 else (c0 <= xs_ + 0.2 and c1 >= xs_ - 7.0)
        return inside and a1 >= u0 - 0.6 and a0 <= u1 + 0.6 and q.z1 > lo.top + 0.02 and not _house(q)
    near = [q for q in boxes if near_(q) and q.kind not in ("ground", "gravel", "glass")]
    fit = [q for q in near if q.z0 >= lo.top - 0.6 and q.kind not in ("post",)] or near
    fx, fy, fw, fh = frame
    polys, to_sheet, sc = draw(near, cols, View(az, 0.0), (fx + 70, fy + 14, fw - 150, fh - 34), fit_boxes=fit)
    P = (lambda u, z: to_sheet((xs_, u, z))) if vert else (lambda u, z: to_sheet((u, xs_, z)))
    cid = "cstepel"                             # nothing below the lower deck's surface: the face is what shows
    o.append(f'<defs><clipPath id="{cid}"><rect x="{fx}" y="{fy + 10}" width="{fw}" height="{max(1.0, P(u0, lo.top)[1] - fy - 10):.1f}"/></clipPath></defs>')
    o.append(f'<g clip-path="url(#{cid})">' + "".join(polys) + "</g>")
    zl, zh = lo.top, hi.top
    o.append(LN(fx + 6, P(u0, zl)[1], fx + fw - 6, P(u0, zl)[1], INK, 1.0))
    o.append(T(fx + fw - 8, P(u0, zl)[1] + 10, f"{_lv_word(lo)} deck surface", 6.4, 800, "end", MUTE))
    pts = sorted({round(v, 4) for v in along})
    yb = P(u0, zl)[1] + 22
    for (a_, b_), lab in zip(zip(pts, pts[1:]), chain_labels([v * 12 for v in pts])):
        x_a, x_b = P(a_, zl)[0], P(b_, zl)[0]
        o.append(LN(min(x_a, x_b), yb, max(x_a, x_b), yb, INK, 0.8)); o.append(LN(x_a, yb - 4, x_a, yb + 4)); o.append(LN(x_b, yb - 4, x_b, yb + 4))
        o.append(T((x_a + x_b) / 2, yb - 4, lab, 7.6, 800, "middle"))
    for a_, b_ in zip(pts, pts[1:]):           # name each run: skirt or the stair opening
        mid = (a_ + b_) / 2
        is_skirt = any((min(a[1], b[1]) - 0.05 <= mid <= max(a[1], b[1]) + 0.05) if vert else (min(a[0], b[0]) - 0.05 <= mid <= max(a[0], b[0]) + 0.05) for a, b in segs)
        o.append(T(P(mid, zl)[0], yb + 11, "skirt" if is_skirt else "stair opening", 6.4, 700, "middle", MUTE))
    xd = max(P(u0, zl)[0], P(u1, zl)[0]) + 16
    o.append(LN(xd, P(u0, zl)[1], xd, P(u0, zh)[1], INK, 0.8)); o.append(LN(xd - 4, P(u0, zl)[1], xd + 4, P(u0, zl)[1])); o.append(LN(xd - 4, P(u0, zh)[1], xd + 4, P(u0, zh)[1]))
    o.append(T(xd + 5, (P(u0, zl)[1] + P(u0, zh)[1]) / 2 + 3, f"{inch(hi.h_in - lo.h_in)} rise", 7.4, 800))
    g = next((g for g in groups if g.st is not None and g.st.landing == "deck"), None)
    if g:
        gg = g.st.geo
        o.append(T(xd + 5, (P(u0, zl)[1] + P(u0, zh)[1]) / 2 + 13, f"{gg.risers} risers @ {inch(gg.riser_in, 16)}", 6.8, 600))
    return True


def sheet_dimensions_composite(CL, S, levels, steps, meta, boxes_all=None) -> str:
    o, top = [], []
    allb = boxes_all if boxes_all is not None else S.boxes
    groups = _stair_groups(S, levels, allb)
    win = _cwindow(levels, S, pad=0.8, back_pad=0.8, front_pad=1.0, boxes=allb)
    X, Y, sc = _cxform(win, 92, 52, 596, 300)
    house = _draw_house(o, X, Y, sc, S, levels, (win[0] - 4, win[1] + 4, win[2] - 4, win[3]), "hhA100", label=False)
    fills = {lv.i: ("#efe3cc" if k % 2 == 0 else "#e2cfab") for k, lv in enumerate(sorted(levels, key=lambda q: q.top))}
    _draw_levels(o, X, Y, levels, fills=fills, sw=2.0)
    _draw_bricks(o, X, Y, sc, house)
    for g in groups:                            # the stairs and their landings from the model's treads; an option dashed
        for b in g.boxes:
            if b.kind in ("tread", "board"):
                x0_, x1_, y0_, y1_ = _plan_rect(b)
                o.append(R(X(x0_), Y(y0_), (x1_ - x0_) * sc, (y1_ - y0_) * sc, "none" if g.option else "#d7c3a0", BROWN if g.option else INK, 0.6,
                           'stroke-dasharray="3 2"' if g.option else ""))
    _draw_steps(o, X, Y, steps, lab=True, size=7.0)
    for lv in levels:                           # zone lines inside each level, dashed, with the zone letters
        for z in lv.zones:
            for z2 in lv.zones:
                if z2 is not z and abs(z2.x0 - z.x1) < 0.02:
                    ya, yb = max(z.y0, z2.y0), min(z.y1, z2.y1)
                    o.append(LN(X(z.x1), Y(ya), X(z.x1), Y(yb), "#9a8a6a", 0.8, "5 3"))
            o.append(TH(X(z.x0) + 8, Y(z.y0) + 22, z.name, 15, 900, "start", "#b59a62", halo=fills[lv.i]))
        zt_ = max(lv.zones, key=lambda q: (q.x1 - q.x0))
        o.append(TH(X((zt_.x0 + zt_.x1) / 2) + 10, Y(zt_.y0) + 12, f"{lv.name.upper()} · {ftin(lv.h_in)} above grade", 6.8, 800, "middle", "#7a6a48", halo=fills[lv.i]))
    rail_pts = [(p.x * IN, p.y * IN) for p in (CL.rail.posts if CL.rail else [])]
    xmin_all = min(p[0] for lv in levels for p in lv.poly); xmax_all = max(p[0] for lv in levels for p in lv.poly)
    rows, notches = [], {}
    for lv in levels:
        P = lv.poly
        pre = lv.name[0].upper()
        bb = (min(p[0] for p in P), max(p[0] for p in P), min(p[1] for p in P), max(p[1] for p in P))
        for k, (a, b) in enumerate(_poly_edges(P)):
            Lft = math.hypot(b[0] - a[0], b[1] - a[1])
            if Lft < 0.05:
                continue
            what = _side_kind(lv, a, b, levels, steps, house, rail_pts, groups)
            nx, ny = _outward(P, a, b)
            ux, uy = (b[0] - a[0]) / Lft, (b[1] - a[1]) / Lft
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            ang = math.degrees(math.atan2(Y(b[1]) - Y(a[1]), X(b[0]) - X(a[0])))
            ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
            sid = f"{pre}{k + 1}"
            vert_end = abs(a[0] - b[0]) < 0.02 and (abs(a[0] - xmin_all) < 0.05 or abs(a[0] - xmax_all) < 0.05)
            ox_, oy_ = mx + nx * 0.4, my + ny * 0.4
            notch = (not what.startswith(("house", "step")) and Lft < 8.0 and bb[0] < ox_ < bb[1] and bb[2] < oy_ < bb[3])   # a side facing into a notch
            if what == "RAIL":
                o.append(LN(X(a[0]) + nx * 3, Y(a[1]) + ny * 3, X(b[0]) + nx * 3, Y(b[1]) + ny * 3, "#1f4fb5", 2.6))
            if notch:
                notches.setdefault(lv.i, []).append((sid, a, b, Lft))
            elif not what.startswith(("house", "step")):
                if not vert_end:
                    top.append(TH(X(mx) + nx * 11, Y(my) + ny * 11 + 3, inch(Lft * 12), 8.4, 900, "middle", INK, rot=ang))
                top.append(TH(X(mx) + nx * (22 if not vert_end else 9) + ux * (0 if not vert_end else 14), Y(my) + ny * (22 if not vert_end else 9) + uy * (0 if not vert_end else 14) + 3,
                              sid, 6.6, 800, "middle", GOLD))
            rows.append((sid, inch(Lft * 12), ftin(Lft * 12), what))
    for li, sides in notches.items():           # a notch's sides named together, beside the notch on its open side
        lv = levels[li]
        nxs = [v for _, a, b, _ in sides for v in (a[0], b[0])]; nys = [v for _, a, b, _ in sides for v in (a[1], b[1])]
        nb = (min(nxs), max(nxs), min(nys), max(nys))
        ids = [sd for sd, _, _, _ in sides]
        w_in, d_in = (nb[3] - nb[2]) * 12, (nb[1] - nb[0]) * 12
        open_left = not any(abs(a[0] - b[0]) < 0.02 and abs(a[0] - nb[0]) < 0.05 for _, a, b, _ in sides)
        g = next((g for g in groups if g.lv is lv and g.inset and nb[0] - 0.3 <= (g.fp[0] + g.fp[1]) / 2 <= nb[1] + 0.3), None)
        txt = [f"{ids[0]}-{ids[-1]}: NOTCH {inch(w_in)} wide x {inch(d_in)} deep"] + ([_stair_words(g).replace(": ", " — ", 1), "cut into the " + lv.name.lower()] if g else [])
        xa = X(nb[0]) - 10 if open_left else X(nb[1]) + 10
        ya = Y((nb[2] + nb[3]) / 2) - 4
        o.append(LN(xa + (6 if open_left else -6), ya + 2, X(nb[0] if open_left else nb[1]) + (2 if open_left else -2), Y((nb[2] + nb[3]) / 2), BROWN, 0.6))
        for j, ln in enumerate(txt):
            top.append(TH(xa, ya + j * 9, ln, 6.8 if j == 0 else 6.2, 900 if j == 0 else 600, "end" if open_left else "start", BROWN))
    yf = max(p[1] for lv in levels for p in lv.poly)
    allx = sorted({round(v, 4) for lv in levels for z in lv.zones for v in (z.x0, z.x1)})
    ybase = max([Y(yf)] + [Y(g.fp[3]) for g in groups if g.fp[3] > yf + 0.1])
    yb = ybase + 34
    for (a_, b_), lab in zip(zip(allx, allx[1:]), chain_labels([v * 12 for v in allx])):
        dim_h(o, X, yb, a_, b_, lab, 8, up=True)
    dim_h(o, X, yb + 26, allx[0], allx[-1], f"{inch((allx[-1] - allx[0]) * 12)} = {ftin((allx[-1] - allx[0]) * 12)} overall", 10, up=False)
    zs = sorted([z for lv in levels for z in lv.zones], key=lambda q: q.x0)
    for z, side in ((zs[0], -1), (zs[-1], 1)):
        pts = sorted({round(z.y0, 4), round(z.y1, 4)} | ({0.0} if z.y0 < -0.05 and z.y1 > 0.05 else set()))
        xx = X(z.x0) - 24 if side < 0 else X(z.x1) + 20
        for (a_, b_), lab in zip(zip(pts, pts[1:]), chain_labels([v * 12 for v in pts])):
            dim_v(o, Y, xx, a_, b_, lab, 7.6, left=side < 0)
        if len(pts) > 2:
            dim_v(o, Y, xx + side * 30, pts[0], pts[-1], f"{inch((pts[-1] - pts[0]) * 12)} deep", 8.2, left=side < 0)
        if z.y0 < -0.05:
            o.append(LN(X(z.x0) if side < 0 else X(z.x1), Y(0), xx + side * 4, Y(0), MUTE, 0.5, "2 2"))
    for g in groups:
        x0_, x1_, y0_, y1_ = g.fp
        words = _stair_words(g) + (" · OPTION" + (f": {g.option}" if g.option else "") if g.option else "")
        if g.inset:
            if g.lv.i not in notches:
                top.append(TH((X(x0_) + X(x1_)) / 2, Y(y1_) + 12, words, 6.6, 800, "middle", BROWN))
            continue
        lvp = g.lv.poly
        best = None
        for a, b in _poly_edges(lvp):
            if abs(a[1] - b[1]) < 0.02 and min(a[0], b[0]) - 0.1 <= (x0_ + x1_) / 2 <= max(a[0], b[0]) + 0.1:
                d = min(abs(a[1] - y0_), abs(a[1] - y1_))
                if best is None or d < best[0]:
                    best = (d, "h", a, b)
            if abs(a[0] - b[0]) < 0.02 and min(a[1], b[1]) - 0.1 <= (y0_ + y1_) / 2 <= max(a[1], b[1]) + 0.1:
                d = min(abs(a[0] - x0_), abs(a[0] - x1_))
                if best is None or d < best[0]:
                    best = (d, "v", a, b)
        if best is None:
            continue
        _, kind, a, b = best
        if kind == "h":
            ea, eb = sorted((a[0], b[0]))
            op = [v for v in (x0_, x1_) if ea + 0.05 < v < eb - 0.05]
            pts = [ea] + op + [eb]
            far = y1_ if abs(a[1] - y0_) < abs(a[1] - y1_) else y0_
            yy_ = Y(far) + 14 if far > a[1] else Y(far) - 14
            _chain(o, X, yy_, pts, 6.8, horiz=True, up=far < a[1])
            dim_v(o, Y, X(x1_) + 12, min(a[1], far), max(a[1], far), f"{inch(abs(far - a[1]) * 12)} out", 6.8, left=False)
            top.append(TH((X(x0_) + X(x1_)) / 2, yy_ + (12 if far > a[1] else -10), words, 6.6, 800, "middle", BROWN))
        else:
            ea, eb = sorted((a[1], b[1]))
            op = [v for v in (y0_, y1_) if ea + 0.05 < v < eb - 0.05]
            pts = [ea] + op + [eb]
            far = x0_ if abs(a[0] - x1_) < abs(a[0] - x0_) else x1_
            xx_ = X(far) - 12 if far < a[0] else X(far) + 12
            _chain(o, Y, xx_, pts, 6.8, horiz=False, left=far < a[0])
            dim_h(o, X, Y(y0_) - 8, min(a[0], far), max(a[0], far), f"run {inch(abs(far - a[0]) * 12)}", 6.6)
            top.append(TH((X(x0_) + X(x1_)) / 2, Y(y0_) - 20, words, 6.6, 800, "middle", BROWN))
    lg_y = yb + 44
    o.append(T(96, lg_y, "House hatched (no work) · levels shaded · blue = rail sides (R on the owner's sketch) · gold = the step between the levels"
               + (" · dashed = option" if any(g.option for g in groups) else ""), 7.0, 600, fill=MUTE))
    if steps:
        o.append(T(20, lg_y + 22, f"STEP FACE — from the {steps[0][0].name.lower()}, inches", 8.6, 800, fill=GOLD))
        _step_face_elevation(o, (20, lg_y + 24, 700, 612 - lg_y - 26), levels, steps, [g for g in groups if not g.option], S.boxes, _axo_colors(S))
    tx0 = 760
    o.append(T(tx0, 24, "EVERY SIDE — INCHES", 9, 800, fill=GOLD))
    yy = 40
    o.append(T(tx0, yy, "#", 7.5, 800)); o.append(T(tx0 + 24, yy, "inches", 7.5, 800)); o.append(T(tx0 + 80, yy, "ft-in", 7.5, 800)); o.append(T(tx0 + 128, yy, "what", 7.5, 800))
    yy += 12
    cur = None
    for sid, li, fi, what in rows:
        if sid[0] != cur:
            cur = sid[0]
            lvn = next(lv for lv in levels if lv.name[0].upper() == cur)
            o.append(T(tx0, yy + 2, f"{lvn.name.upper()} · {ftin(lvn.h_in)}", 7, 900, fill=MUTE)); yy += 12
        o.append(T(tx0, yy, sid, 8, 700, fill=GOLD)); o.append(T(tx0 + 24, yy, li, 8, 800)); o.append(T(tx0 + 80, yy, fi, 7.4, 500, fill=MUTE))
        o.append(T(tx0 + 128, yy, textwrap.shorten(what, 30, placeholder="…"), 7.0, 500)); yy += 11.2
    yy += 8
    notes = [f"Overall {inch((allx[-1] - allx[0]) * 12)} = {ftin((allx[-1] - allx[0]) * 12)} along the house.",
             "Sides at the outside face of the frame (fascia / picture-frame line), corner to corner; x from the deck's left end, y from the main rear wall.",
             "Verify in the field before ordering: the house lines, the arm's door wall and the step face."]
    _notes_cols(o, tx0, yy, 230, notes, size=7.2, lh=9.6)
    o += top
    return sheet("A-100", "Dimension plan — inches", "Every side of both levels in inches, the overall in feet and inches, the step face and the stairs", o,
                 "Plan · not to scale · house at the top · inches govern", meta)


# ------------------------------------------------------------------ S-100 foundation plan (both levels)
def _post_rows(levels, boxes) -> list:
    """Footing / post schedule rows in build order: every beam-line post of every level, the edge posts, then the stair
    carriers and landings (from the model)."""
    rows, n = [], 0
    for lv in levels:
        for bm in lv.beams:
            for p in bm.posts:
                n += 1
                rows.append(_NS(id=f"P{n}", lv=lv, line=bm.short, x=p.x, y=p.y, post=bm.post_len, load=p.load, kind=bm.kind))
        for ep in lv.eps:
            rows.append(_NS(id=ep.label, lv=lv, line=f"{ep.zone} rim (edge)", x=ep.x, y=ep.y, post=lv.L.edge_post_len, load=ep.load, kind="edge"))
    for b in boxes:
        t_ = (b.tag or "")
        if b.kind == "footing" and ("stair footing" in t_ or "landing footing" in t_):
            n += 1
            cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
            lv = next((q for q in levels if t_.startswith(q.name + ":")), None)
            rows.append(_NS(id=f"P{n}", lv=lv, line="stair " + ("landing" if "landing" in t_ else "carrier"), x=cx, y=cy, post=None, load=None, kind="stair"))
    return rows


def sheet_foundation_composite(CL, S, levels, steps, meta, boxes_all=None) -> str:
    s = CL.spec
    o = []
    win = _cwindow(levels, S, back_pad=3.0, front_pad=3.0)
    X, Y, sc = _cxform(win, 30, 4, 940, 360)
    house = _draw_house(o, X, Y, sc, S, levels, win, "hhS100")
    _draw_levels(o, X, Y, levels, fills={lv.i: "#f3ecdf" for lv in levels}, sw=1.2)
    _draw_bricks(o, X, Y, sc, house)
    _draw_steps(o, X, Y, steps)
    _cdraw(o, X, Y, sc, S.boxes, ("beam",), INK, 0.9, "6 3", pred=lambda b: "carrier" not in (b.tag or ""))
    _cdraw(o, X, Y, sc, S.boxes, ("footing",), INK, 0.9)
    _cdraw(o, X, Y, sc, S.boxes, ("post",), INK, 0.7)
    opt = [b for b in (boxes_all or []) if (getattr(b, "layer", "") or "").startswith("option:") and b.kind in ("footing", "post")]
    _cdraw(o, X, Y, sc, opt, ("footing", "post"), BROWN, 0.6, "2 2", fill="none")
    rows = _post_rows(levels, S.boxes)
    for r in rows:
        o.append(TH(X(r.x), Y(r.y) - 9, r.id, 7.4, 800, "middle", fill=(BLUE if r.kind == "edge" else INK)))
    for lv in levels:
        for bm in lv.beams:
            o.append(TH(X(min(bm.a[0], bm.b[0])) + 3, Y(bm.a[1]) + 13, f"{bm.short} · {bm.size} {bm.kind}", 6.4, 800, fill=MUTE))
    _level_tags(o, X, Y, levels)
    ft = CL.frame
    desc = {"caisson": f"{int(ft.footing_dia_in)}\" drilled caisson x {ftin(ft.footing_depth_in)} + 6\" above grade, (4) #4 verticals + #3 ties, 5/8\" x 8\" cast-in anchor",
            "diamond_pier": f"Diamond Pier {ft.footing_model}: precast head set in a dug hole on undisturbed soil + 4 driven pins (ICC-ES ESR-1895); {_post_base_name(s, CL.parts[0].takeoff)} base on the pier bolt"
                            + (" + a 5/8\" anchor into the head" if _post_base_name(s, CL.parts[0].takeoff).startswith("ABU88") else ""),
            "concrete": f"{int(ft.footing_dia_in)}\" concrete pier x {ftin(ft.footing_depth_in)}, wet-set standoff base",
            "existing": "Existing caissons stay — verify plumb, bearing and condition (engineer)"}[s.framing.footing_type]
    y0 = 384
    o.append(T(30, y0, "FOOTING + POST SCHEDULE", 9, 800, fill=GOLD))
    o.append(T(200, y0, textwrap.shorten(desc.split(":")[0] + (f" · {_post_base_name(s, CL.parts[0].takeoff)} post bases" if s.framing.footing_type == "diamond_pier" else ""), 140, placeholder="…"), 7.4, 600))
    hdr = ("ID", "level", "line", "x", "y", "post", "load")
    cols = [0, 28, 74, 150, 206, 262, 310]
    per = 17
    for ti in range(min(2, max(1, math.ceil(len(rows) / per)))):
        tx = 30 + ti * 372
        yy = y0 + 16
        for h, dx in zip(hdr, cols):
            o.append(T(tx + dx, yy, h.upper(), 7, 800, fill=MUTE))
        yy += 4; o.append(LN(tx, yy, tx + 352, yy, MUTE, 0.6)); yy += 10.5
        for r in rows[ti * per:(ti + 1) * per]:
            vals = (r.id, (_lv_word(r.lv) if r.lv else "—"), r.line, ftin(r.x * 12), ftin(r.y * 12), (ftin(r.post) if r.post else "—"), (f"{r.load:,.0f} lb" if r.load else "—"))
            for v, dx in zip(vals, cols):
                o.append(T(tx + dx, yy, textwrap.shorten(str(v), 15, placeholder="…"), 7.2, 500))
            yy += 10.4
    notes = [("#", "FOUNDATION NOTES"), desc + ".",
             "x from the deck's left end, y from the main rear wall toward the yard (the plan frame of every sheet).",
             f"Post = top of the post base to the beam seat — field-measure each to the string line before cutting.",
             f"{len(rows)} footings: " + " · ".join(f"{_lv_word(lv)} {sum(len(b.posts) for b in lv.beams) + len(lv.eps)}" for lv in levels)
             + (f" · stairs {sum(1 for r in rows if r.kind == 'stair')}" if any(r.kind == "stair" for r in rows) else ""),
             f"Frost {ftin(s.site.frost_depth_in)} · soil {s.site.soil_bearing_psf:,.0f} psf presumptive · worst post {max((r.load or 0) for r in rows):,.0f} lb."]
    if opt:
        notes.append("Dashed brown: the option's footings and posts (not in this scope unless the option is taken).")
    _notes_cols(o, 790, y0 - 2, 190, notes, size=7.2, lh=9.6)
    sub = "Both levels: %d footings and posts numbered in one schedule; beams dashed%s" % (len(rows), " (below the joists)" if any(b.kind == "drop" for lv in levels for b in lv.beams) else "")
    return sheet("S-100", "Foundation plan", sub, o, "Plan · not to scale · house at the top · dimensions govern", meta)


# ------------------------------------------------------------------ S-101 framing plan (both levels)
def _gap_mid(z, beams_y) -> float:
    """The middle of the longest clear run across a zone between its ends and its beam lines (plan y, feet)."""
    ys = sorted([z.y0, z.y1] + [y for y in beams_y if z.y0 < y < z.y1])
    a, b = max(zip(ys, ys[1:]), key=lambda q: q[1] - q[0])
    return (a + b) / 2


def sheet_framing_composite(CL, S, t, levels, steps, meta) -> str:
    o = []
    win = _cwindow(levels, S, back_pad=3.0, front_pad=4.0)
    X, Y, sc = _cxform(win, 30, 4, 940, 368)
    house = _draw_house(o, X, Y, sc, S, levels, win, "hhS101")
    _cdraw(o, X, Y, sc, S.boxes, ("beam",), BLUE, 1.0, "6 3", pred=lambda b: "carrier" not in (b.tag or ""))
    _cdraw(o, X, Y, sc, S.boxes, ("ledger",), INK, 0.6)
    _cdraw(o, X, Y, sc, S.boxes, ("joist",), INK, 0.35)
    _cdraw(o, X, Y, sc, S.boxes, ("block",), INK, 0.35)
    _cdraw(o, X, Y, sc, S.boxes, ("rim", "doubler", "header"), INK, 0.7)
    _cdraw(o, X, Y, sc, S.boxes, ("stringer",), BROWN, 0.6)
    _cdraw(o, X, Y, sc, S.boxes, ("beam",), BROWN, 0.6, pred=lambda b: "carrier" in (b.tag or ""))
    _cdraw(o, X, Y, sc, S.boxes, ("post",), INK, 0.7)
    _draw_bricks(o, X, Y, sc, house)
    _draw_steps(o, X, Y, steps)
    for lv in levels:
        for bm in lv.beams:
            full = f"{bm.short} · {bm.size} {bm.kind}" + (" (below)" if bm.kind == "drop" else "")
            room = abs(bm.b[0] - bm.a[0]) * sc - 8
            o.append(TH(X(min(bm.a[0], bm.b[0])) + 4, Y(bm.a[1]) - 5, full if len(full) * 3.7 < room else bm.short, 6.6, 800, fill=BLUE))
    jlab = CL.spec.framing.steel_joist if CL.spec.framing.system == "steel" else CL.frame.joist_size
    for lv in levels:
        by = [bm.a[1] for bm in lv.beams if abs(bm.a[1] - bm.b[1]) < 0.01]
        for z in lv.zones:
            fr = z.z.frame
            txt = f"{z.name}: {len(fr.joist_x)} + {len(fr.pf_x)} PF {jlab} @ {fr.spacing:g}\" · {ftin(fr.joist_len)}"
            if (z.x1 - z.x0) * sc < len(txt) * 3.7:     # a narrow zone (the arm): the label turns along it, in its longest clear bay
                txt = f"{z.name}: {len(fr.joist_x)}+{len(fr.pf_x)} PF @ {fr.spacing:g}\" · {ftin(fr.joist_len)}"
                o.append(TH(X((z.x0 + z.x1) / 2), Y(_gap_mid(z, by)), txt, 6.4, 800, "middle", rot=-90))
            else:
                o.append(TH(X((z.x0 + z.x1) / 2), Y(z.y1) - 9, txt, 6.6, 800, "middle"))
        for dx, dy, lab in lv.divs:
            o.append(T(X(dx), Y(dy) + 9, f"doubled joist · {_div_word(lab, dx)}", 5.8, 700, "middle", MUTE))
    _level_tags(o, X, Y, levels)
    allx = [p[0] for lv in levels for p in lv.poly]
    yb = Y(max(p[1] for lv in levels for p in lv.poly)) + 24
    zx = sorted({round(v, 4) for lv in levels for z in lv.zones for v in (z.x0, z.x1)})
    for (a, b), lab in zip(zip(zx, zx[1:]), chain_labels([v * 12 for v in zx])):
        dim_h(o, X, yb, a, b, f"{lab} = {ftin((b - a) * 12)}", 7.0, up=True)
    dim_h(o, X, yb + 16, min(allx), max(allx), f"{ftin((max(allx) - min(allx)) * 12)} overall", 7.8, up=False)
    zs = sorted([z for lv in levels for z in lv.zones], key=lambda q: q.x0)
    for z in zs:
        if z is zs[0]:
            dim_v(o, Y, X(z.x0) - 10, z.y0, z.y1, f"{z.name} {ftin((z.y1 - z.y0) * 12)}", 6.6, left=True)
        elif z is zs[-1]:
            dim_v(o, Y, X(z.x1) + 10, z.y0, z.y1, f"{z.name} {ftin((z.y1 - z.y0) * 12)}", 6.6, left=False)
        else:
            dim_v(o, Y, X(z.x1) - 9, z.y0, z.y1, f"{z.name} {ftin((z.y1 - z.y0) * 12)}", 6.4)
    items = [("#", "FRAMING NOTES")]
    ms = _merged_schedule(t, levels)
    for lv in levels:
        items.append(f"{lv.name} ({' + '.join(z.name for z in lv.zones)}), deck {ftin(lv.h_in)} above grade: {lv.t.summary.get('joists', '')}; "
                     f"{lv.t.summary.get('rims', '')}; beams " + "; ".join(f"{b.short} {ftin(b.length)} on {len(b.posts)} posts" for b in lv.beams) + ".")
    items.append(f"Ledgers: {ms.get('Ledger', '')}")
    groups = [g for g in _stair_groups(S, levels) if not g.option]
    if steps:
        lo, hi = steps[0][0], steps[0][1]
        items.append(f"Level change: the {hi.name.lower()} frames {inch(hi.h_in - lo.h_in)} above the {lo.name.lower()}, each on its own posts and beams; the {hi.name.lower()}'s rim "
                     f"on the step face carries the skirt, the {lo.name.lower()}'s rim runs beside it (A-301)."
                     + "".join(f" {_stair_words(g)}: " + ("cut into the " + g.lv.name.lower() + " — the notch framed with doubled trimmers and a doubled header, the stringers hung from it"
                                                          if g.inset else "stringers hung from the rim") + "." for g in groups if g.st and g.st.landing == "deck"))
    items += [v for v in (ms.get("Blocking", "Blocking one row over the beam, staggered."), ms.get("Joist tape", "")) if not re.search(r"(^|\s|: )0 x ", v)]
    hw = [f"{l.item}: {l.net:g}" for l in t.lines if l.category == "Hardware" and l.unit == "ea"][:8]
    items += ["Connectors, both levels: " + " · ".join(hw)]
    _notes_cols(o, 30, 400, 940, items, size=7.1, lh=9.4, cols=2)
    return sheet("S-101", "Framing plan", "Both levels: ledgers, joists, rims, blocking, beams, the level change" + (", the stair framing" if any(b.kind == "stringer" for b in S.boxes) else "")
                 + " — cut list on T-600", o, "Plan · not to scale · house at the top · dimensions govern", meta)


# ------------------------------------------------------------------ A-101 decking plan (both levels)
def sheet_decking_composite(CL, S, t, levels, steps, meta) -> str:
    s = CL.spec
    o = []
    win = _cwindow(levels, S, back_pad=3.0, front_pad=3.5)
    X, Y, sc = _cxform(win, 30, 4, 940, 368)
    house = _draw_house(o, X, Y, sc, S, levels, win, "hhA101")
    _cdraw(o, X, Y, sc, S.boxes, ("fascia",), "#777", 0.3)
    _cdraw(o, X, Y, sc, S.boxes, ("board",), "#8f8f8c", 0.25)
    _cdraw(o, X, Y, sc, S.boxes, ("border",), "#222", 0.3)
    _cdraw(o, X, Y, sc, S.boxes, ("tread",), BROWN, 0.3)
    _cdraw(o, X, Y, sc, S.boxes, ("railpost",), INK, 0.5)
    _draw_bricks(o, X, Y, sc, house)
    _draw_steps(o, X, Y, steps, lab=False)
    for lv in levels:
        if lv.L.plan is not None:
            P_ = lv.L.plan
            for i, (a, b, n, y_top) in enumerate(P_.panels):
                rows_p = [r for r in P_.rows if r.panel == i]
                ym = (min(r.y0 for r in rows_p) + max(r.y1 for r in rows_p)) / 2 * IN if rows_p else y_top * IN / 2
                cx, cy = lv.pl.pt((a + b) / 2 * IN, ym)
                o.append(TH(X(cx), Y(cy) + 3, f"panel {i + 1} · {n} rows", 8, 800, "middle", "#fff", halo="#3a302a"))
        else:
            for z in lv.zones:
                o.append(TH(X((z.x0 + z.x1) / 2), Y((z.y0 + z.y1) / 2) + 3, f"{z.name} · {z.z.decking.rows} rows", 8.2, 800, "middle", "#fff", halo="#3a302a",
                            rot=(-90 if (z.x1 - z.x0) < 9 and (z.y1 - z.y0) > 14 else 0)))
        for dx, dy, lab in lv.divs:
            o.append(TH(X(dx), Y(max(dy, max(p[1] for p in lv.poly))) + 12, f"breaker {_div_word(lab, dx)}", 6.4, 800, "middle", INK))
    if steps:
        lo, hi, a, b = max(steps, key=lambda s_: max(s_[2][1], s_[3][1]))
        o.append(TH(X(a[0]), Y(max(a[1], b[1])) + 12, "picture frame both sides of the step", 6.4, 800, "middle", "#8a6510"))
    for lv in levels:                       # the level tag on the boards, near the house
        z = max(lv.zones, key=lambda q: (q.x1 - q.x0) if (q.x1 - q.x0) > (q.y1 - q.y0) * 0.8 else 0)
        o.append(TH(X((z.x0 + z.x1) / 2), Y(z.y0) + 14, _lv_tag(lv), 7.6, 900, "middle", "#fff", halo="#3a302a"))
    allx = [p[0] for lv in levels for p in lv.poly]
    yf = max(p[1] for lv in levels for p in lv.poly)
    from .layout import NOSE
    edge = (CL.parts[0].layout.decking.fascia_t + NOSE) * IN if s.decking.fascia else 1.5 * IN
    dim_h(o, X, Y(yf) + 26, min(allx) - edge, max(allx) + edge, f"{ftin((max(allx) - min(allx) + 2 * edge) * 12)} over the edge boards", 7.6, up=False)
    f = decking_facts(s.decking.collection)
    ms = _merged_schedule(t, levels)
    items = [("#", "DECKING"),
             f"Field: {s.decking.brand} {s.decking.collection} {s.decking.color}, {f['width']:g}\" x {f['thick']:g}\", {ftin(s.deck_gap)} gaps; boards run "
             f"{'parallel to' if s.geometry.board_direction == 'parallel' else 'out from'} the house on both levels",
             (f"Picture frame + breakers: {s.decking.border_collection or s.decking.collection} {s.decking.border_color or s.decking.color} on every open edge, "
              "on both sides of the step between the levels and at the breakers " + ", ".join(_div_word(lab, dx) for lv in levels for dx, _, lab in lv.divs)) if s.geometry.picture_frame else "No picture frame",
             ms.get("Field", ""), ms.get("Face screws", ""), ms.get("Picture frame + stairs", "")]
    for lv in levels:
        items.append(f"{lv.name}: " + (lv.L.plan.summary() if lv.L.plan is not None else "rows per zone " + " · ".join(f"{z.name} {z.z.decking.rows}" for z in lv.zones)
                                        + (" (rip at the house)" if any(z.z.decking.last_row_dev < -0.5 for z in lv.zones) else " (no rips)"))
                     + (f"; fascia {s.decking.fascia_color or s.decking.color} over the rims" if s.decking.fascia else ""))
    _notes_cols(o, 30, 400, 940, items, size=7.2, lh=9.6, cols=2)
    return sheet("A-101", "Decking plan", "Both levels: every board, border and breaker as it lays; rail posts shown for the pockets", o,
                 "Plan · not to scale · house at the top · dimensions govern", meta)


# ------------------------------------------------------------------ A-201 rail plan + elevation (both levels)
def _side_words(side: str, lv, steps) -> str:
    """A rail run's side as it reads: 'front', 'left end', 'step face', 'side U3'."""
    if side.startswith("front"):
        return "front"
    if side in ("end:left", "left"):
        return "step" if any(hi is lv and abs(a[0] - min(p[0] for p in lv.poly)) < 0.05 for lo, hi, a, b in steps) else "left end"
    if side in ("end:right", "right"):
        return "step" if any(hi is lv and abs(a[0] - max(p[0] for p in lv.poly)) < 0.05 for lo, hi, a, b in steps) else "right end"
    m = re.match(r"edge:(\d+)", side)
    if m:
        return f"side {lv.name[0].upper()}{m.group(1)}"
    return side


def _seg_dist(px, py, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t_ = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
    return math.hypot(a[0] + t_ * dx - px, a[1] + t_ * dy - py)


def sheet_rail_composite(CL, S, t, levels, steps, meta) -> str:
    s = CL.spec
    rl = CL.rail
    o = []
    win = _cwindow(levels, S, back_pad=2.0, front_pad=3.0)
    X, Y, sc = _cxform(win, 30, 4, 940, 268)
    house = _draw_house(o, X, Y, sc, S, levels, win, "hhA201", label=False)
    _draw_levels(o, X, Y, levels, fills={lv.i: ("#ece3d2" if lv.top == min(q.top for q in levels) else "#e2d5bd") for lv in levels}, sw=1.0)
    _draw_bricks(o, X, Y, sc, house)
    _draw_steps(o, X, Y, steps, lab=False)
    _cdraw(o, X, Y, sc, S.boxes, ("toprail",), "#1b1b1b", 0.4, fill="#2b2621")
    _cdraw(o, X, Y, sc, S.boxes, ("tread",), BROWN, 0.3, fill="#d7c3a0")
    placed = []
    if rl:
        for i, p in enumerate(rl.posts):
            x, y = p.x * IN, p.y * IN
            o.append(R(X(x) - 3, Y(y) - 3, 6, 6, INK, INK, 0.5))
            lv = next((q for q in levels if _inside_poly(q.poly, x, y)), levels[0])
            best = min(_poly_edges(lv.poly), key=lambda e: _seg_dist(x, y, e[0], e[1]))
            nx, ny = _outward(lv.poly, *best)
            if abs(nx) > abs(ny):
                lx, ly, anc = X(x) + nx * 7, Y(y) + 3, ("start" if nx > 0 else "end")
            else:
                lx, ly, anc = X(x), Y(y) + (13 if ny > 0 else -6), "middle"
            while any(abs(lx - a_) < 24 and abs(ly - b_) < 8 for a_, b_ in placed):
                ly += 8 if ny >= 0 else -8
            placed.append((lx, ly))
            o.append(TH(lx, ly, f"RP{i + 1} {p.kind[0]}", 6.0, 800, anc))
    _level_tags(o, X, Y, levels, size=7.4, dy=14)
    zlo = min(lv.top for lv in levels) - 1.4
    zhi = max(lv.top for lv in levels) + (rl.height * IN if rl else 3.0) + 1.0
    x0w, x1w = win[0], win[1]
    k = min(940 / (x1w - x0w), 150 / (zhi - zlo))
    Xe, Z, sce = elev_xform(x0w, x1w, zlo, zhi, 30 + (940 - (x1w - x0w) * k) / 2, 300, 940, 150)
    yf = max(p[1] for lv in levels for p in lv.poly)
    front = [b for b in S.boxes if b.kind in ("rim", "fascia", "railpost", "toprail", "cable", "baluster", "botrail", "drink", "railcap", "board", "border", "light", "fixture")
             and b.y1 >= yf - 0.6 and not b.rot]
    draw_elev_boxes(o, Xe, Z, sce, [b for b in front if b.kind in ("rim", "fascia", "board", "border")], ("rim", "fascia", "board", "border"), INK, 0.3)
    draw_elev_boxes(o, Xe, Z, sce, [b for b in front if b.kind not in ("rim", "fascia", "board", "border")],
                    ("railpost", "toprail", "cable", "baluster", "botrail", "drink", "railcap", "light", "fixture"), "none", 0)
    o.append(T(30, 290, "FRONT OF THE RAIL — from the yard, each level at its own height", 8.4, 800, fill=GOLD))
    if rl:
        for lv in levels:
            fp = sorted(p.x * IN for p in rl.posts if abs(p.y * IN - yf) < 0.6 and _inside_poly(lv.poly, p.x * IN, p.y * IN - 0.1))
            ztop = lv.top
            yd = Z(ztop + rl.height * IN) - 12
            for a, b in zip(fp, fp[1:]):
                dim_h(o, Xe, yd, a, b, ftin((b - a) * 12), 6.2, up=True)
            if fp:
                right = lv.top == max(q.top for q in levels)
                xh = Xe(fp[-1]) + 10 if right else Xe(fp[0]) - 10
                dim_v(o, Z, xh, ztop, ztop + rl.height * IN, f"{rl.height:g}\"", 6.4, left=not right)
                o.append(T((Xe(fp[0]) + Xe(fp[-1])) / 2, Z(ztop - 1.35) + 9, f"{_lv_word(lv).upper()} DECK · {ftin(lv.h_in)} above grade", 6.8, 800, "middle", RED))
    ms = _merged_schedule(t, levels)
    items = [("#", "RAILING"), t.summary.get("rail", ""), ms.get("Rail", "")]
    if rl:
        for lv in levels:
            if lv.L.rail:
                runs: Dict[str, List[float]] = {}
                for s_ in lv.L.rail.sections:
                    runs.setdefault(_side_words(s_.side, lv, steps), []).append(s_.ctc)
                items.append(f"{lv.name} bays: " + " · ".join(f"{k_} " + " / ".join(ftin(c) for c in v) for k_, v in runs.items()))
        items.append("Guard 36\" min. above each walking surface on every open side — both levels stand over 30\" above grade, and the step between them is guarded "
                     "except at the stair; openings under 4\" (IRC R312). Rail LF for labor = deck-edge LF of actual rail.")
        if s.railing.drink_rail:
            items.append(f"Drink rail: {getattr(s.railing, 'drink_rail_collection', '') or s.decking.collection} {getattr(s.railing, 'drink_rail_color', '') or s.decking.color} on drink-rail brackets, mitred at every turn.")
    _notes_cols(o, 30, 470, 940, items, size=7.1, lh=9.4, cols=2)
    return sheet("A-201", "Railing plan + elevation", "Both levels: post IDs and types (E end · L line · C corner), the runs, the front at both heights", o,
                 "Plan above · elevation of the front below · not to scale", meta)


# ------------------------------------------------------------------ section / elevation helpers
def _hull(pts):
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in pts))
    if len(pts) <= 2:
        return pts
    def cross(o_, a, b):
        return (a[0] - o_[0]) * (b[1] - o_[1]) - (a[1] - o_[1]) * (b[0] - o_[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def _section(o, boxes, axis, at, look, U, V, depth=4.0, near=(), near_tol=1.2, skip=("ground", "gravel", "glass", "water")):
    """A section-elevation from the model: the boxes the plane `axis` = at cuts, solid with a heavy outline; the boxes beyond it
    (in the look direction, within `depth`) lighter behind them. axis 'x' projects on (y, z), axis 'y' on (x, z); U / V map
    those to the sheet (a mirrored U for a view the other way). Returns (cut, [(distance, box)])."""
    from .axo import corners
    cut, beyond = [], []
    k = 0 if axis == "x" else 1
    for b in boxes:
        if b.kind in skip or b.shape == "mesh" or getattr(b, "layer", "") in ("site", "louvered"):
            continue
        cs = corners(b) if b.rot else None
        d0, d1 = (min(q[k] for q in cs), max(q[k] for q in cs)) if cs else ((b.x0, b.x1) if axis == "x" else (b.y0, b.y1))
        mid = (d0 + d1) / 2
        if d0 - 1e-6 <= at <= d1 + 1e-6 or (b.kind in near and abs(mid - at) < near_tol):
            cut.append(b)
        else:
            dist = (d0 - at) if look > 0 else (at - d1)
            if 0 < dist <= depth:
                beyond.append((dist, b))
    def poly(b):
        cs = corners(b)
        return _hull([(U(q[1]), V(q[2])) if axis == "x" else (U(q[0]), V(q[2])) for q in cs])
    for dist, b in sorted(beyond, key=lambda q: (-q[0], q[1].z0)):
        o.append(PG(poly(b), _lighten(fill_for(b), 0.45 + min(0.3, dist / depth * 0.3)), "#9a9184", 0.35))
    for b in sorted(cut, key=lambda q: (q.kind in ("board", "border", "tread", "riser", "fascia", "light", "fixture"), q.z0)):
        o.append(PG(poly(b), fill_for(b), INK, 0.7 if b.kind not in ("baluster", "cable") else 0.2))
    return cut, beyond


# ------------------------------------------------------------------ A-202 elevations (both levels, the step face, the columns)
def sheet_elevations_composite(CL, S, t, levels, steps, meta) -> str:
    from .axo import View, draw
    s = CL.spec
    cols = _axo_colors(S)
    bx = [b for b in S.boxes if b.kind not in ("ground", "glass")]
    fit = [b for b in bx if not _house(b)]
    o = []
    views = [("FRONT ELEVATION — from the yard", 0.0, (20, 14, 600, 300)), ("RIGHT END ELEVATION", 90.0, (640, 14, 340, 300)),
             ("LEFT END ELEVATION", -90.0, (640, 326, 340, 284))]
    for ttl, az, fr in views:
        polys, to_sheet, sc = draw(bx, cols, View(az, 0.0), (fr[0], fr[1] + 16, fr[2], fr[3] - 30), fit_boxes=fit)
        cid = f"cel{int(az + 180)}"
        o.append(f'<defs><clipPath id="{cid}"><rect x="{fr[0]}" y="{fr[1] + 14}" width="{fr[2]}" height="{fr[3] - 20}"/></clipPath></defs>')
        o.append(T(fr[0], fr[1] + 8, ttl, 9, 800, fill=GOLD))
        o.append(f'<g clip-path="url(#{cid})">' + "".join(polys) + "</g>")
        gy = to_sheet((0, 0, 0))[1]
        o.append(LN(fr[0], gy, fr[0] + fr[2], gy, INK, 1.2)); o.append(T(fr[0] + 4, gy + 10, "GRADE", 6.5, 800, fill=MUTE))
        if az == 0:
            for lv in levels:               # each level's surface, tagged over its own deck
                xs_ = [p[0] for p in lv.poly]
                y_ = to_sheet((max(xs_), 10, lv.top))[1]
                tag = f"{_lv_word(lv).upper()} DECK · {ftin(lv.h_in)} AFG"
                wt = len(tag) * 3.9 + 8
                xa = to_sheet(((min(xs_) + max(xs_)) / 2, 10, lv.top))[0]
                o.append(LN(xa - wt / 2 - 6, y_, xa + wt / 2 + 6, y_, RED, 0.9, "3 2"))
                o.append(R(xa - wt / 2, y_ + 3, wt, 10, CREAM, RED, 0.5)); o.append(T(xa, y_ + 11, tag, 6.4, 800, "middle", RED))
            posts = [b for b in bx if b.kind == "post" and not (b.tag or "").endswith(("carrier post", "landing post"))]
            if posts:
                n_ = sum(len(b.posts) for lv in levels for b in lv.beams)
                p_ = sorted(posts, key=lambda b: b.x0)[len(posts) // 2]
                ax_, ay_ = to_sheet(((p_.x0 + p_.x1) / 2, p_.y1, p_.z0 + (p_.z1 - p_.z0) * 0.3))
                o.append(LN(ax_, ay_, ax_ + 18, gy + 14, INK, 0.5)); o.append(C(ax_, ay_, 1.4, INK, "none", 0))
                o.append(TH(ax_ + 20, gy + 17, f"{n_} {s.framing.post_size} {post_words(s)} columns on {_post_base_name(s, t)} bases + Diamond Piers"
                            if s.framing.footing_type == "diamond_pier" else f"{n_} {s.framing.post_size} {post_words(s)} columns", 6.6, 700))
    if steps:
        lo, hi = steps[0][0], steps[0][1]
        o.append(T(20, 334, f"STEP FACE — seen from the {lo.name.lower()} ({inch(hi.h_in - lo.h_in)} up)", 9, 800, fill=GOLD))
        groups = [g for g in _stair_groups(S, levels) if not g.option]
        _step_face_view(o, (20, 336, 600, 196), levels, steps, groups, bx, cols, s, t)
    notes = [" · ".join(f"{lv.name}: surface {ftin(lv.h_in)} above grade" for lv in levels),
             "Heights AFG = above finished grade at the beam line; field-verify grade before setting the piers",
             f"Deck frame: {s.framing.joist_size} {s.framing.joist_grade} @ {CL.frame.spacing:g}\" OC on {sum(len(lv.beams) for lv in levels)} "
             f"{' / '.join(sorted({b.kind for lv in levels for b in lv.beams}))} beam lines, {sum(len(b.posts) for lv in levels for b in lv.beams)} "
             f"{s.framing.post_size} columns (S-100 / S-101)"]
    if CL.rail:
        notes.append(f"Guard {CL.rail.height:g}\" min. on every open side of both levels and along the step except at the stair (IRC R312.1)")
    yy = 548 if steps else 354
    for n_ in notes:
        o.append(T(20, yy, "· " + n_, 7.4, 500)); yy += 11.5
    return sheet("A-202", "Elevations", "Front from the yard, both ends and the step face, drawn from the model — both deck heights and the columns", o,
                 "Elevations · orthographic · not to scale · heights govern", meta)


def _step_face_view(o, fr, levels, steps, groups, bx, cols, s, t=None):
    """The step face from the lower level: the skirt, the stair (cut into the upper level or off its face), the upper rail."""
    from .axo import View, draw
    lo, hi = steps[0][0], steps[0][1]
    segs = [(a, b) for l_, h_, a, b in steps if l_ is lo and h_ is hi]
    vert = abs(segs[0][0][0] - segs[0][1][0]) < 0.02
    xs_ = segs[0][0][0] if vert else segs[0][0][1]
    probe = (segs[0][0][0] + 0.3, (segs[0][0][1] + segs[0][1][1]) / 2) if vert else ((segs[0][0][0] + segs[0][1][0]) / 2, segs[0][0][1] + 0.3)
    look = 1 if _inside_poly(hi.poly, *probe) else -1
    az = (-90.0 if look > 0 else 90.0) if vert else (180.0 if look > 0 else 0.0)
    along = [v for a, b in segs for v in ((a[1], b[1]) if vert else (a[0], b[0]))]
    u0, u1 = min(along), max(along)
    def keep(q):
        c0, c1 = (q.x0, q.x1) if vert else (q.y0, q.y1)
        a0, a1 = (q.y0, q.y1) if vert else (q.x0, q.x1)
        side = (c1 >= xs_ - 0.2 and c0 <= xs_ + 6.0) if look > 0 else (c0 <= xs_ + 0.2 and c1 >= xs_ - 6.0)
        return side and a1 >= u0 - 0.8 and a0 <= u1 + 0.8 and q.z1 > lo.top + 0.02 and not _house(q)
    near = [q for q in bx if keep(q)]
    fit = [q for q in near if q.z0 >= lo.top - 0.5 and q.kind != "post"] or near
    polys, to_sheet, sc = draw(near, cols, View(az, 0.0), (fr[0] + 170, fr[1] + 14, fr[2] - 340, fr[3] - 34), fit_boxes=fit)
    P = (lambda u, z: to_sheet((xs_, u, z))) if vert else (lambda u, z: to_sheet((u, xs_, z)))
    o.append(f'<defs><clipPath id="celstep"><rect x="{fr[0]}" y="{fr[1] + 8}" width="{fr[2]}" height="{max(1.0, P(u0, lo.top)[1] - fr[1] - 8):.1f}"/></clipPath></defs>')
    o.append(f'<g clip-path="url(#celstep)">' + "".join(polys) + "</g>")
    yl = P(u0, lo.top)[1]
    o.append(LN(fr[0] + 150, yl, fr[0] + fr[2] - 150, yl, INK, 1.0)); o.append(T(fr[0] + fr[2] - 152, yl + 10, f"{_lv_word(lo)} deck surface", 6.4, 800, "end", MUTE))
    items = []
    sk = [q for q in near if (q.kind == "skirt" or "skirt" in (q.tag or "")) and "stair skirt" not in (q.tag or "")]
    if sk:
        q = max(sk, key=lambda b_: (b_.z1 - b_.z0))
        vertical = any("vertical" in (b_.tag or "") for b_ in sk) or (q.z1 - q.z0) > max(q.x1 - q.x0, q.y1 - q.y0)
        items.append((*to_sheet(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2, (q.z0 + q.z1) / 2)),
                      f"Step skirt: {s.decking.collection} {s.decking.fascia_color or s.decking.color} fascia boards" + (", installed vertically" if vertical else "")))
    else:
        fa = [q for q in near if q.kind == "fascia" and q.z1 > hi.top - 0.3 and (q.z1 - q.z0) > 0.5]
        if fa:
            q = fa[0]
            items.append((*to_sheet(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2, (q.z0 + q.z1) / 2)), f"{s.decking.collection} fascia over the {hi.name.lower()}'s rim"))
    tr = [q for q in near if q.kind == "tread"]
    g = next((g for g in groups if g.st is not None and g.st.landing == "deck"), None)
    if tr:
        q = sorted(tr, key=lambda b_: b_.z0)[len(tr) // 2]
        items.append((*to_sheet(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2, q.z1)), (_stair_words(g) + (" — cut into the upper level" if g.inset else "")) if g else "Stair between the levels"))
    lt = [q for q in near if q.kind == "light" and "riser" in (q.tag or "")]
    if lt:
        q = lt[0]
        items.append((*to_sheet(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2, (q.z0 + q.z1) / 2)), "LED riser light in every riser (low voltage)"))
    rp = [q for q in near if q.kind == "toprail" and q.z0 > hi.top]
    if rp:
        q = rp[0]
        items.append((*to_sheet(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2, q.z1)), f"{rail_name(s.railing.system)} {s.railing.height_in:g}\" {s.railing.color}"))
    cl = [q for q in near if q.kind == "light" and ("cap" in (q.tag or "") or "accent" in (q.tag or ""))]
    if cl:
        q = cl[0]
        items.append((*to_sheet(((q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2, q.z1)), _light_words(t)[1]))
    L_ = [it for it in items if it[0] < fr[0] + fr[2] / 2]; R_ = [it for it in items if it[0] >= fr[0] + fr[2] / 2]
    _leaders(o, L_, fr[0] + 4, "start", y_min=fr[1] + 18, y_max=fr[1] + fr[3] - 4, chars=30)
    _leaders(o, R_, fr[0] + fr[2] - 4, "end", y_min=fr[1] + 18, y_max=fr[1] + fr[3] - 4, chars=30)
    xd = max(P(u0, lo.top)[0], P(u1, lo.top)[0]) + 14
    dim_v(o, lambda z: P(u0, z)[1], xd, lo.top, hi.top, f"{inch(hi.h_in - lo.h_in)}", 6.6, left=False)


# ------------------------------------------------------------------ A-301 sections through the level change
def sheet_section_composite(CL, S, t, levels, steps, meta) -> str:
    s = CL.spec
    o = []
    bx = [b for b in S.boxes if b.kind not in ("ground", "glass") and getattr(b, "layer", "") not in ("site", "louvered")]
    groups = [g for g in _stair_groups(S, levels) if not g.option]
    rl = CL.rail
    lo = min(levels, key=lambda q: q.top); hi = max(levels, key=lambda q: q.top)
    st = steps[0] if steps else None
    zmax = hi.top + (rl.height * IN if rl else 3.0) + 1.0
    v0 = -1.2
    xs_ = st[2][0] if st else lo.zones[-1].x1
    gs = next((g for g in groups if g.st is not None and g.st.landing == "deck"), groups[0] if groups else None)
    # ---- SECTION A: y-z, through the lower level next to the step, looking toward the upper level (+x)
    fr = (20, 18, 560, 356)
    js = [b for b in bx if b.kind == "joist" and b.x1 <= xs_ - 0.15 and b.z1 < lo.top + 0.05 and b.z1 > lo.top - 1.2]
    jn = max(js, key=lambda b: b.x1) if js else None
    xc = (jn.x0 + jn.x1) / 2 if jn else xs_ - 0.6
    ys = [p[1] for lv in levels for p in lv.poly]
    u0, u1 = -4.0, max(ys) + 2.5
    scA = min(fr[2] / (u1 - u0), fr[3] / (zmax - v0))
    oxA = fr[0] + (fr[2] - (u1 - u0) * scA) / 2
    U = lambda y: oxA + (y - u0) * scA
    V = lambda z: fr[1] + fr[3] - (z - v0) * scA
    o.append(T(20, 10, "SECTION A — through the lower level beside the step, looking toward the upper level", 8.6, 800, fill=GOLD))
    o.append(f'<defs><clipPath id="secA"><rect x="{fr[0]}" y="{fr[1]}" width="{fr[2]}" height="{fr[3]}"/></clipPath>'
             f'<pattern id="hhA301" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="#efe8da"/>'
             f'<line x1="0" y1="0" x2="0" y2="7" stroke="#d3c8b3" stroke-width="1.1"/></pattern></defs><g clip-path="url(#secA)">')
    o.append(R(fr[0], V(0), fr[2], (0 - v0) * scA, "#e0d7c2", "none", 0))
    if not any(b.kind in ("house", "wall") and b.x0 <= xc <= b.x1 for b in bx):        # the house wall for context
        o.append(R(U(u0), V(zmax), U(0) - U(u0), V(0) - V(zmax), "url(#hhA301)", INK, 1.0))
    cutA, beyA = _section(o, bx, "x", xc, 1, U, V, depth=6.0, near=("post", "footing", "base", "cap"))
    o.append("</g>")
    o.append(LN(fr[0], V(0), fr[0] + fr[2], V(0), INK, 1.0)); o.append(T(fr[0] + fr[2] - 4, V(0) + 10, "grade", 6.6, 700, "end", MUTE))
    o.append(TH(U(-0.3), V(zmax) + 12, "HOUSE", 7.6, 900, "end", "#8a8172", halo="#efe8da")); o.append(T(U(u1) - 4, V(zmax) + 12, "YARD", 7.6, 900, "end", "#8a8172"))
    for k_, lv in enumerate(sorted(levels, key=lambda q: q.top)):
        dim_v(o, V, U(u1) - 10 - 20 * k_, 0, lv.top, f"{ftin(lv.h_in)}", 6.6, left=True)
    items = []
    def at(b, fu=0.5, fz=0.5):
        from .axo import corners
        cs = corners(b)
        uu = min(q[1] for q in cs) + (max(q[1] for q in cs) - min(q[1] for q in cs)) * fu
        zz = min(q[2] for q in cs) + (max(q[2] for q in cs) - min(q[2] for q in cs)) * fz
        return U(uu), V(zz)
    lab = lambda b, d: (b.tag.split(": ")[-1] if b.tag else d)
    q = [b for b in cutA if b.kind == "beam"]
    if q:
        items.append((*at(q[0]), f"{lo.name}: {lab(q[0], 'beam')} — in section"))
    q = [b for d, b in beyA if b.kind == "beam" and b.z1 > lo.top]
    if q:
        items.append((*at(q[0], 0.5, 0.5), f"{hi.name}: {lab(q[0], 'beam')} — beyond"))
    q = [b for b in cutA if b.kind == "joist"]
    if q:
        items.append((*at(q[0], 0.62, 0.5), f"{lo.name}: {s.framing.joist_size} joist @ {CL.frame.spacing:g}\" OC, ledger to the front rim"))
    q = [b for d, b in beyA if b.kind == "joist" and b.z1 > lo.top + 0.5]
    if q:
        items.append((*at(q[0], 0.3, 0.5), f"{hi.name}: {s.framing.joist_size} joists — beyond"))
    q = [b for b in cutA if b.kind == "ledger"]
    if q:
        items.append((*at(q[0]), f"{s.framing.joist_size} ledger, LedgerLOK 2 rows, membrane + flashing"))
    q = [b for d, b in beyA if (b.kind == "skirt" or "skirt" in (b.tag or "")) and "stair skirt" not in (b.tag or "")]
    if q:
        items.append((*at(max(q, key=lambda b_: b_.z1 - b_.z0)), "Step skirt: fascia boards, vertical — beyond"))
    q = [b for d, b in beyA if b.kind == "tread"]
    if q:
        items.append((*at(sorted(q, key=lambda b_: b_.z0)[0], 0.5, 1.0), (gs.name if gs else "Stair") + " — beyond"))
    q = [b for b in cutA if b.kind == "post"] or [b for d, b in beyA if b.kind == "post"]
    if q:
        items.append((*at(q[0], 0.5, 0.45), f"{s.framing.post_size} {post_words(s)} column"))
    q = [b for b in cutA if b.kind == "footing"] or [b for d, b in beyA if b.kind == "footing"]
    if q:
        items.append((*at(q[0], 0.5, 1.0), f"Diamond Pier {CL.frame.footing_model} + {_post_base_name(s, t)} base" if s.framing.footing_type == "diamond_pier" else "Footing"))
    q = [b for b in cutA if b.kind in ("toprail", "drink") and b.z0 < hi.top]
    if q:
        items.append((*at(q[0], 0.5, 1.0), f"{rail_name(s.railing.system)} {s.railing.height_in:g}\"" + (" + drink rail" if s.railing.drink_rail else "")))
    LA = [it for it in items if it[0] < U(5.0)]; RA = [it for it in items if it[0] >= U(5.0)]
    _leaders(o, LA, fr[0] + 4, "start", y_min=fr[1] + 22, y_max=V(lo.top) - 4, chars=30)
    _leaders(o, RA, fr[0] + fr[2] - 4, "end", y_min=fr[1] + 22, y_max=V(0) - 8, chars=30)
    if st:
        dim_v(o, V, U(u0) + 14, lo.top, hi.top, f"{inch(hi.h_in - lo.h_in)}", 6.6, left=False)
    # ---- SECTION B: x-z through the stair, looking toward the yard (+y; x runs right to left)
    frB = (600, 18, 384, 356)
    yc = ((gs.fp[2] + gs.fp[3]) / 2) if gs else (max(ys) - 3.0)
    w0, w1 = xs_ - 8.0, xs_ + 8.0
    scB = min(frB[2] / (w1 - w0), frB[3] / (zmax - v0))
    oxB = frB[0] + (frB[2] - (w1 - w0) * scB) / 2
    UB = lambda x: oxB + (w1 - x) * scB                     # mirrored: looking toward the yard
    VB = lambda z: frB[1] + frB[3] - (z - v0) * scB
    o.append(T(600, 10, "SECTION B — through the stair, looking toward the yard", 8.6, 800, fill=GOLD))
    o.append(f'<defs><clipPath id="secB"><rect x="{frB[0]}" y="{frB[1]}" width="{frB[2]}" height="{frB[3]}"/></clipPath></defs><g clip-path="url(#secB)">')
    o.append(R(frB[0], VB(0), frB[2], (0 - v0) * scB, "#e0d7c2", "none", 0))
    inwin = [b for b in bx if b.x1 >= w0 - 1 and b.x0 <= w1 + 1]
    cutB, beyB = _section(o, inwin, "y", yc, 1, UB, VB, depth=6.0, near=("footing", "base"), near_tol=0.3)
    o.append("</g>")
    o.append(LN(frB[0], VB(0), frB[0] + frB[2], VB(0), INK, 1.0))
    o.append(T(frB[0] + 4, frB[1] + 12, f"cut at {ftin(yc * 12)} from the house wall", 6.6, 700, fill=MUTE))
    o.append(TH(UB(xs_) + 6, VB(lo.top) - 4, _lv_word(lo).upper(), 7.2, 900, "start", MUTE)); o.append(TH(UB(xs_) - 6, VB(hi.top) - 4, _lv_word(hi).upper(), 7.2, 900, "end", MUTE))
    if st:
        dim_v(o, VB, UB(xs_) + 22, lo.top, hi.top, inch(hi.h_in - lo.h_in), 6.6, left=False)
    itB = []
    def atB(b, fu=0.5, fz=0.5):
        from .axo import corners
        cs = corners(b)
        xx_ = min(q[0] for q in cs) + (max(q[0] for q in cs) - min(q[0] for q in cs)) * fu
        xx_ = min(max(xx_, w0 + 0.6), w1 - 0.6)
        zz = min(q[2] for q in cs) + (max(q[2] for q in cs) - min(q[2] for q in cs)) * fz
        return UB(xx_), VB(zz)
    for lv in (lo, hi):
        q = [b for d, b in beyB if b.kind == "beam" and lv.top - 2.2 < b.z1 < lv.top and _inside_poly(lv.poly, min(max((b.x0 + b.x1) / 2, w0), w1), (b.y0 + b.y1) / 2)]
        if q:
            itB.append((*atB(q[0], 0.5 if lv is lo else 0.6), f"{lv.name}: {lv.beams[0].size} {lv.beams[0].species} {lv.beams[0].kind} beam — beyond" if lv.beams else "beam"))
        q = [b for d, b in beyB if b.kind == "post" and lv.top - 2.5 < b.z1 < lv.top and _inside_poly(lv.poly, (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2 - 0.3)]
        if q:
            b = min(q, key=lambda b_: abs((b_.x0 + b_.x1) / 2 - xs_))
            itB.append((*atB(b, 0.5, 0.4), f"{lv.name}: {s.framing.post_size} column — beyond"))
    q = [b for b in cutB if b.kind == "stringer"]
    if q:
        itB.append((*atB(q[0]), "2x12 stringer (cut), closed risers"))
    q = [b for b in cutB if b.kind == "tread"]
    if q:
        itB.append((*atB(sorted(q, key=lambda b_: b_.z0)[len(q) // 2], 0.5, 1.0),
                    f"Treads: {gs.st.geo.risers} risers @ {inch(gs.st.geo.riser_in, 16)}, {gs.st.geo.treads} treads @ {inch(gs.st.geo.tread_in, 16)}" if gs and gs.st else "treads"))
    q = [b for b in cutB if b.kind == "joist" and b.z1 > lo.top + 0.5]
    if q:
        itB.append((*atB(q[len(q) // 2], 0.5, 1.0), f"{hi.name}: {s.framing.joist_size} joists in section"))
    q = [b for b in cutB if b.kind in ("header", "rim", "doubler") and b.z1 > lo.top + 0.5]
    if q and gs and gs.inset:
        itB.append((*atB(q[0]), "Notch framing: doubled header + trimmers"))
    q = [b for b in cutB if (b.kind == "skirt" or "skirt" in (b.tag or "")) and "stair skirt" not in (b.tag or "")]
    if q:
        itB.append((*atB(q[0]), "Step skirt (vertical boards)"))
    LB = [it for it in itB if it[0] < frB[0] + frB[2] / 2]; RB = [it for it in itB if it[0] >= frB[0] + frB[2] / 2]
    _leaders(o, LB, frB[0] + 4, "start", y_min=VB(lo.top - 1.6), y_max=VB(0) - 6, chars=26)
    _leaders(o, RB, frB[0] + frB[2] - 4, "end", y_min=VB(lo.top - 1.6), y_max=VB(0) - 6, chars=26)
    # ---- key plan: where the cuts are
    kx, ky, kw, kh = 780, 392, 200, 120
    xs_all = [p[0] for lv in levels for p in lv.poly]
    win = (min(xs_all) - 1, max(xs_all) + 1, min(ys) - 1, max(ys) + 1)
    Xk, Yk, sck = _cxform(win, kx, ky + 12, kw, kh - 12, "middle")
    o.append(T(kx, ky + 4, "KEY PLAN — the cuts", 8, 800, fill=GOLD))
    _draw_levels(o, Xk, Yk, levels, fills={lv.i: ("#ece3d2" if lv is lo else "#d9c7a5") for lv in levels}, sw=0.8)
    for g in groups:
        o.append(R(Xk(g.fp[0]), Yk(g.fp[2]), (g.fp[1] - g.fp[0]) * sck, (g.fp[3] - g.fp[2]) * sck, "#bfa77d", INK, 0.4))
    for lo_, hi_, a, b in steps:
        o.append(LN(Xk(a[0]), Yk(a[1]), Xk(b[0]), Yk(b[1]), GOLD, 2.0))
    o.append(LN(Xk(xc), Yk(min(ys) - 0.6), Xk(xc), Yk(max(ys) + 0.6), RED, 1.0, "4 2"))
    o.append(T(Xk(xc) + 3, Yk(max(ys) + 0.6) + 8, "A →", 7, 900, "start", RED))
    o.append(LN(Xk(w0), Yk(yc), Xk(w1), Yk(yc), RED, 1.0, "4 2"))
    o.append(T(Xk(w1) + 3, Yk(yc) + 3, "B ↓", 7, 900, "start", RED))
    items_n = [("#", "SECTION NOTES")]
    for lv in levels:
        items_n.append(f"{lv.name}: surface {ftin(lv.h_in)} above grade; " + "; ".join(f"{b.short} {b.size} {b.species} {b.kind} beam on {len(b.posts)} posts {ftin(b.post_len)}" for b in lv.beams))
    if st:
        items_n.append(f"Level change: the {hi.name.lower()} stands {inch(hi.h_in - lo.h_in)} above the {lo.name.lower()}; each level on its own beams and columns, "
                       f"the two rims side by side at the step, the skirt over the {hi.name.lower()}'s rim from deck to deck.")
    for g in groups:
        if g.st is not None:
            items_n.append(_stair_words(g) + ("; cut into the " + g.lv.name.lower() + ", its bottom riser at the step face" if g.inset else "") + ".")
    if rl:
        items_n.append(f"Guard {rl.height:g}\" min. on every open side of both levels; graspable handrail where the stair has 4 or more risers (IRC R311.7.8).")
    _notes_cols(o, 20, 392, 740, items_n, size=7.2, lh=9.6, cols=2)
    return sheet("A-301", "Sections through the level change", "Both levels in section: lower and upper beams and joists, the step skirt and the stair, a key plan", o,
                 "Sections · from the model · not to a common scale · dimensions govern", meta)


def _post_base_name(s, t) -> str:
    """The post base the order carries: its Simpson SKU, or 'custom standoff' for a made-to-order base (a rough 8x8 on a
    Diamond Pier); post_base_sku() when the order has no base line."""
    for l in getattr(t, "lines", None) or []:
        if l.category == "Footings" and "base" in l.item.lower():
            sku = getattr(l, "sku", "") or ""
            return sku if re.match(r"^[A-Z]{2,}\d", sku) else "custom standoff"
    return post_base_sku(s)


def _composite_key(CL, S, t) -> list:
    """member_key for a composite deck, worded for what this job carries: the field fastener as ordered (Cortex face screws +
    plugs are not hidden fasteners), the post base the order carries, the step skirt and the lights when the model has them."""
    s = CL.spec
    base, std = _post_base_name(s, t), post_base_sku(s)
    cortex = (s.decking.fastener_system or "").lower().startswith("cortex")
    out = []
    for lab, pred, where, pick in member_key(CL, S, t):
        if cortex and lab.endswith("field decking, hidden fasteners"):
            lab = lab.replace("hidden fasteners", "Cortex face screws + color-matched plugs")
        if base != std:
            lab = lab.replace(f"{_a(std)} {std} standoff base", f"a {base} base").replace(std, base)
        lab = lab.replace("head + 4 driven pins (frost-protected, no excavation)", "precast head in a dug hole + 4 driven pins (frost-protected)")
        out.append((lab, pred, where, pick))
    skirt = lambda b: (b.kind == "skirt" or "skirt" in (b.tag or "")) and "stair skirt" not in (b.tag or "")
    out.append((f"Step skirt — {s.decking.collection} {s.decking.fascia_color or s.decking.color} fascia boards installed vertically", skirt, (0.5, 0.5, 0.5), "mid"))
    out.append((_light_words(t)[0], lambda b: b.kind == "light", (0.5, 0.5, 0.5), "mid"))
    return [k for k in out if any(k[1](b) for b in S.boxes)]


def _light_words(t) -> Tuple[str, str]:
    """(key label, step-face label) for the job's lights, worded from lighting.py's plan (t.lighting): a drink rail over the
    posts makes the post lights accent lights on the post's deck side, else cap lights."""
    plan = getattr(t, "lighting", None)
    if plan is None:
        return "LED lights, low voltage", "LED post light on every rail post"
    from .lighting import post_label, post_where
    bits = (["LED riser lights"] if plan.n_riser else []) + ([("" if plan.n_riser else "LED ") + post_label(plan)] if plan.n_cap else [])
    return (" + ".join(bits) or "LED lights") + ", low voltage", f"LED {post_label(plan, 1)[2:]} {post_where(plan)}"


def sheet_iso_assembled_composite(CL, S, t, meta) -> str:
    bx = [b for b in S.boxes if b.kind not in ("ground", "glass", "stringer")]     # closed risers hide the stringers
    fit = [b for b in bx if not _house(b)]
    hidden = ("post", "beam", "joist", "rim", "ledger", "block", "gravel", "stepbase", "sheath", "underlay")
    key = [k for k in _composite_key(CL, S, t) if not any(k[1](b) for b in S.boxes if b.kind in hidden)]
    return _axo_sheet("A-002", "Isometric — assembled, labeled", "Both levels, everything you see: piers, columns, decking, picture frame, step skirt, stair, rail", CL, S, t, meta, bx,
                      fit=fit, key=key, note="House shown for context only (the deck work only). The frame under the decking is called out on S-102 and A-003.")


def sheet_iso_exploded_composite(CL, S, t, meta) -> str:
    bx = [b for b in S.boxes if b.kind not in ("ground", "glass") and not _house(b)]
    sub = ("Both levels, each build layer lifted in order: piers · posts · beams · frame · decking" + (" · stair" if any(b.kind in ("tread", "stringer") for b in bx) else "")
           + (" · rail" if CL.rail else ""))
    return _axo_sheet("A-003", "Isometric — exploded, labeled", sub, CL, S, t, meta, bx, explode=True, az=35, el=24, key=_composite_key(CL, S, t),
                      note="Layers lifted in build order. Lifts are for clarity only; every member returns straight down to its place.")


def sheet_iso_structure_composite(CL, S, t, meta) -> str:
    bx = [b for b in S.boxes if b.kind in ("footing", "base", "post", "brace", "cap", "beam", "joist", "rim", "ledger", "block", "stringer", "gravel", "header", "doubler")]
    key = [k for k in _composite_key(CL, S, t) if any(k[1](b) for b in bx)]
    kinds = {b.kind for p in CL.parts for b in p.layout.beam_lines}
    items = " ".join(ln.item.lower() for ln in getattr(t, "lines", []))
    note = ("Decking, rail and house removed to show the frame of both levels, each on its own posts and beams. Joists hang from the ledgers in face-mount hangers"
            + ("; they bear on the drop beams with H2.5AZ ties" if "drop" in kinds else "") + ("; joists hang on both faces of the flush beams" if "flush" in kinds else "")
            + ("; double rims in concealed-flange hangers" if "concealed" in items else "") + ".")
    return _axo_sheet("S-102", "Structure isometric — frame, labeled", "Both levels: piers, post bases, columns, beams, joists, rims, ledgers, blocking, the stair stringers",
                      CL, S, t, meta, bx, az=-32, el=32, key=key, note=note)


def _panel_level_change(o, note, CL, levels, steps):
    """D-501 panel 6 for a two-level deck: the step between the levels in section — the lower deck's border and rim, the upper
    level's rim on its own posts, the skirt boards over it from deck to deck on furring, the picture frame nosing over the skirt."""
    s = CL.spec
    lo, hi = steps[0][0], steps[0][1]
    rise = hi.h_in - lo.h_in
    sk = getattr(hi.spec.geometry, "step_skirt", None) or getattr(lo.spec.geometry, "step_skirt", None) or {}
    gap, oc = float(sk.get("gap_in", 0.125)), float(sk.get("stud_oc_in", 16))
    fas = _MAT_COLORS.get("fascia", FILL["fascia"])
    yl, yu = 530.0, 530.0 - min(110.0, rise * 2.4)
    deck, border, wood = FILL["deck"], FILL["border"], FILL["timber"]
    # the lower level: field, the border at the step, its doubled rim, joists beyond
    o.append(R(676, yl - 6, 92, 6, deck, INK, 0.5)); o.append(R(769, yl - 6, 27, 6, border, INK, 0.5))
    o.append(R(676, yl, 108, 22, _lighten(wood, 0.35), INK, 0.4)); o.append(R(784, yl, 6, 22, wood, INK, 0.6)); o.append(R(790, yl, 6, 22, wood, INK, 0.6))
    # the upper level: the border nosing over the skirt, field, its doubled rim (face on the step line, x 804), joists beyond
    o.append(R(794, yu - 6, 36, 6, border, INK, 0.5)); o.append(R(830, yu - 6, 130, 6, deck, INK, 0.5))
    o.append(R(804, yu, 6, 22, wood, INK, 0.6)); o.append(R(810, yu, 6, 22, wood, INK, 0.6)); o.append(R(816, yu, 144, 22, _lighten(wood, 0.35), INK, 0.4))
    # the skirt on furring, deck to deck, 1/2" off the lower decking
    o.append(R(800, yu, 4, yl - 2 - yu, _lighten(wood, 0.15), INK, 0.5))
    o.append(R(797, yu + 1, 3, yl - 7.2 - (yu + 1), fas, INK, 0.6))
    dim_v(o, lambda v: v, 966, yu, yl, f"{inch(rise)}", 6.6, left=True)
    note(680, 362, 290, f"Each level on its own posts and beams; the rims stand side by side at the step. The skirt covers the face from deck to deck: "
                        f"{s.decking.collection} {s.decking.fascia_color or s.decking.color} fascia boards cut to height and installed vertically, {inch(gap, 16)} gaps, "
                        f"on 2x4 furring @ {oc:g}\" OC fastened to the upper rim; the upper picture frame overhangs it 1\".")
    _lead(o, 798, (yu + yl) / 2, 690, yu + 6, "Step skirt — fascia boards, vertical")
    _lead(o, 802, yu + 40, 690, yu + 34, "2x4 furring behind the skirt")
    _lead(o, 813, yu + 11, 850, yu + 46, f"{hi.name}: 2-ply {s.framing.joist_size} rim")
    _lead(o, 812, yu - 3, 850, yu - 16, "Picture frame nosing, 1\" over the skirt")
    _lead(o, 787, yl + 12, 850, yl + 26, f"{lo.name}: 2-ply {s.framing.joist_size} rim")
    _lead(o, 781, yl - 3, 690, yl + 30, "Border / breaker at the step")


# ------------------------------------------------------------------ the composite set
def _site_marks(S0) -> list:
    """C-100 marks for a composite deck (sheet_site `marks`), from the full scene: a louvered roof built into the set (its
    frame outline and posts) and each option's stair (its treads and landings), drawn dashed."""
    out = []
    lv = [b for b in S0.boxes if getattr(b, "layer", "") == "louvered" and b.kind in ("lvbeam", "lvgutter", "lvblade")]
    if lv:
        posts = [((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2) for b in S0.boxes
                 if getattr(b, "layer", "") == "louvered" and b.kind == "lvpost" and "aluminum post" in (b.tag or "")]
        out.append(([(min(b.x0 for b in lv), max(b.x1 for b in lv), min(b.y0 for b in lv), max(b.y1 for b in lv))],
                    "Louvered roof over the upper level, on 2 posts at the deck rail (A-403)", "#1c1c1e", posts))
    opts: Dict[str, Dict[str, list]] = {}
    for b in S0.boxes:
        ly = getattr(b, "layer", "") or ""
        if not ly.startswith("option:"):
            continue
        tg = (b.tag or "").split(": ")[-1]
        m = re.match(r"landing \d+", tg)
        if b.kind == "tread" or m:
            opts.setdefault(ly[7:], {}).setdefault(m.group(0) if m else f"t{len(opts.get(ly[7:], {}))}", []).append(b)
    for name, grp in opts.items():
        rects = [(min(b.x0 for b in bs), max(b.x1 for b in bs), min(b.y0 for b in bs), max(b.y1 for b in bs)) for bs in grp.values()]
        out.append((rects, f"Option — {name} (priced separately)", "#7a3e9d", []))
    return out


def composite_sheets(CL, t, flags, scene: Optional[Scene] = None, customer: bool = False, only=None) -> List[Tuple[str, str, str]]:
    """[(num, title, svg)] for a composite (multi-level) deck: whole-deck sheets in the global frame."""
    import dataclasses as _dc
    if customer:
        flags = None
    S0 = scene or build_scene(CL)
    x_min = getattr(S0, "x_min", 0.0)
    # the drawing sheets: no yard, no louvered roof (its own sheet), no option (A-100 / S-100 show it dashed), no stand-in
    # landing board on the level a stair lands on (the level is there)
    allb = [b for b in S0.boxes if getattr(b, "layer", "") not in ("site", "louvered") and not (b.tag or "").split(": ")[-1].startswith("lower deck at the")]
    keep = [b for b in allb if not (getattr(b, "layer", "") or "").startswith("option:")]
    S = _dc.replace(S0, boxes=keep)
    S.x_min = x_min
    S._job_spec = CL.spec
    _MAT_COLORS.clear()
    for k in ("deck", "border", "drink", "fascia"):
        if k in S.materials:
            _MAT_COLORS[k] = S.materials[k]["color"]
    FILL["deck"] = _MAT_COLORS.get("deck", FILL["deck"]); FILL["border"] = _MAT_COLORS.get("border", FILL["border"])
    meta = sheet_meta(CL, customer=customer)
    _STEEL["on"] = CL.spec.framing.system == "steel"
    levels = _comp_levels(CL)
    steps = _step_faces(levels)
    want = lambda n: only is None or n in only
    out = [("G-001", "General notes · design criteria", "")]
    gn = sheet_general_notes(CL, meta) if want("G-002") else None           # the job's own numbered notes, when it has them
    if gn:
        out.append(("G-002", "General notes", gn))
    if want("C-100") and CL.spec.site.plan and CL.spec.site.plan.get("parcel"):
        big = lambda lv: max(lv.zones, key=lambda q: (q.x1 - q.x0) * (q.y1 - q.y0))          # the level's label: on its biggest zone
        site = sheet_site(CL, S, t, meta, outlines=[(lv.poly, f"{lv.name.upper()}\n{ftin(lv.h_in)} above grade", ((big(lv).x0 + big(lv).x1) / 2, big(lv).y0 + (big(lv).y1 - big(lv).y0) * 0.68))
                                                    for lv in levels], marks=_site_marks(S0))
        if site:
            out.append(("C-100", "Site plan", site))
    if want("A-100"):
        out.append(("A-100", "Dimension plan — inches", sheet_dimensions_composite(CL, S, levels, steps, meta, boxes_all=allb)))
    if want("A-002"):
        out.append(("A-002", "Isometric — assembled, labeled", sheet_iso_assembled_composite(CL, S, t, meta)))
    if want("A-003"):
        out.append(("A-003", "Isometric — exploded, labeled", sheet_iso_exploded_composite(CL, S, t, meta)))
    if want("S-100"):
        out.append(("S-100", "Foundation plan", sheet_foundation_composite(CL, S, levels, steps, meta, boxes_all=allb)))
    if want("S-101"):
        out.append(("S-101", "Framing plan", sheet_framing_composite(CL, S, t, levels, steps, meta)))
    if want("S-102"):
        out.append(("S-102", "Structure isometric, labeled", sheet_iso_structure_composite(CL, S, t, meta)))
    if want("A-101"):
        out.append(("A-101", "Decking plan", sheet_decking_composite(CL, S, t, levels, steps, meta)))
    if want("A-201") and CL.rail:
        out.append(("A-201", "Railing plan + elevation", sheet_rail_composite(CL, S, t, levels, steps, meta)))
    if want("A-202"):
        out.append(("A-202", "Elevations", sheet_elevations_composite(CL, S, t, levels, steps, meta)))
    if want("A-301"):
        out.append(("A-301", "Sections through the level change" if steps else "Sections", sheet_section_composite(CL, S, t, levels, steps, meta)))
    if want("A-403"):
        lvr = __import__("decktakeoff.louvered", fromlist=["sheet"]).sheet(CL, S0, t, meta)      # None without a louvered roof
        if lvr:
            out.append(("A-403", "Louvered roof — plan, section, post", lvr))
    if want("D-501"):
        from .layout import NOSE, OVERHANG_NO_FASCIA
        L0 = CL.parts[0].layout
        edge = ((L0.decking.fascia_t + NOSE) if CL.spec.decking.fascia else OVERHANG_NO_FASCIA) * IN
        ms = _merged_schedule(t, levels)
        led = ms.get("Ledger", "")
        if len(led) > 150 and " · " in led:            # the panel holds three lines: the rule and the lengths, not the fastener count
            led = led.rsplit(" · ", 1)[0]
        ms["Ledger"] = led
        for k_ in ("Field", "Rail"):                     # the counts are on T-700; the panels keep the rule
            ms[k_] = re.sub(r"\s*\([^)]*\d[^)]*\)", "", ms.get(k_, ""))
        tm = _NS(schedule=ms, summary=t.summary, lines=t.lines)
        p6 = (("STEP BETWEEN THE LEVELS", lambda o_, note_: _panel_level_change(o_, note_, CL, levels, steps)) if steps else None)
        out.append(("D-501", "Details", sheet_details(CL, _NS(meta=dict(edge=edge)), tm, meta, panel6=p6, base=_post_base_name(CL.spec, t))))
    index = [("G-001", "General notes · design criteria")]
    for num, ttl, _ in out[1:]:
        if num == "A-002":
            index.append(("A-001", "Isometric · renders"))
        index.append((num, ttl))
    index += [("T-400", "Build steps (build set)"), ("T-700", "Order + schedules (takeoff)")]
    if want("G-001"):
        out[0] = ("G-001", "General notes · design criteria", sheet_notes_composite(CL, S, t, flags, meta, levels, steps, index))
    else:
        out = out[1:]
    return out
