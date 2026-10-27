"""3D / plan scene from a Layout: every stick, board, post, footing and rail part as an axis-aligned box (feet),
tagged with a material and a build phase. The Three.js viewer, the rendered stills and the SVG sheets all draw
from this one list, so the drawings and the model can never disagree.

Coordinates: x along the house, left to right facing the house from the yard; y from the reference house wall
toward the yard; z up from grade. Deck top = height_in / 12."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from .catalog import rail_system_for, BOARDS_PALETTE, RAIL_SYSTEMS, actual, decking_facts, parse_beam
from .layout import Layout, NOSE, OVERHANG_NO_FASCIA, RAIL_POST_INSET
from .spec import COVER_DEFAULTS, DeckSpec, covers_of, post_words, post_base_sku

PHASES = {1: "Footings", 2: "Posts", 3: "Stone bases", 4: "Beams", 5: "Frame", 6: "Decking", 7: "Rail", 8: "Furnishings"}
IN = 1 / 12.0


@dataclass
class Box:
    kind: str          # house | wall | privacy | ground | gravel | footing | base | post | stone | cap | beam | ledger | joist | rim | block | doubler | board | border | fascia | railpost | toprail | cable | baluster | botrail | drink | tub | stringer | tread | brace
    x0: float; x1: float; y0: float; y1: float; z0: float; z1: float
    mat: str
    phase: int = 0
    tag: str = ""
    shape: str = "box"  # box | cyl | sphere (ellipsoid in the bounds) | cone (base at z0, apex at z1) | mesh
    tone: float = 0.0   # per-board tone jitter (-1..1)
    rot: float = 0.0    # radians about the box centre: stair stringers / stair rails (axis below); 0 = axis-aligned
    rot_axis: str = "y" # "y": run along x (viewer rotation.z) | "x": run along y (viewer rotation.x)
    xg: float = 0.0     # extra lift in the exploded view (ft) on top of the phase gap: layers within one phase pull apart
    pts: Optional[list] = None   # shape "mesh": triangle vertices [[x, y, z], ...] in plan feet (3 per triangle) — shade sails
    layer: str = ""              # "site": the yard (lawn, beds, walls, plants, fences, neighbours) — the 3D views draw it, the drawing sheets leave it out
    quad: Optional[list] = None  # a mitred board's true top outline, 4 plan points [x, y] (ft): the photoreal pass builds the prism from it, the viewer keeps the box


@dataclass
class Scene:
    boxes: List[Box]
    deck_top: float
    W: float               # along the house (ft)
    y_min: float           # deepest wall (plan y, ft; negative)
    y_front: float         # outer edge y (ft) — max front
    materials: Dict[str, dict]
    meta: dict

    def to_dict(self) -> dict:
        return dict(boxes=[asdict(b) for b in self.boxes], deck_top=self.deck_top, W=self.W, x_min=getattr(self, 'x_min', 0.0), y_min=self.y_min, y_front=self.y_front,
                    materials=self.materials, meta=self.meta, phases=PHASES)


def _line_x(p, d, q, e):
    """Where p + t d meets q + s e (None when parallel)."""
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return (p[0] + t * d[0], p[1] + t * d[1])


def _mitred_quads(borders, poly, sgn, edge, bw):
    """The true top outline of each picture-frame border (plan inches): the outer face `edge` past its side, the inner face
    `bw` in from that; each end cut on the bisector where the next border joins it, else along the outline side it dies
    into (the house wall or a bay face)."""
    segs = []
    for x0, y0, x1, y1, *_ in borders:
        L_ = math.hypot(x1 - x0, y1 - y0)
        u = ((x1 - x0) / L_, (y1 - y0) / L_)
        segs.append(((x0, y0), (x1, y1), u, (-u[1] * sgn, u[0] * sgn)))

    def along(P_, u):                    # the outline side through vertex P_ that does not run along u
        m = len(poly)
        for k in range(m):
            for v, w in ((poly[k], poly[(k + 1) % m]), (poly[(k + 1) % m], poly[k])):
                if math.hypot(v[0] - P_[0], v[1] - P_[1]) < 0.5:
                    L_ = math.hypot(w[0] - v[0], w[1] - v[1])
                    d = ((w[0] - v[0]) / L_, (w[1] - v[1]) / L_)
                    if abs(d[0] * u[1] - d[1] * u[0]) > 1e-3:
                        return d
        return (-u[1], u[0])             # nothing there: a square cut

    def off(P_, n, k):
        return (P_[0] + n[0] * k, P_[1] + n[1] * k)

    quads = []
    for i, (A, B_, u, n) in enumerate(segs):
        pts = {}
        for end, P_ in (("a", A), ("b", B_)):
            nb = [s for j, s in enumerate(segs) if j != i and math.hypot((s[1] if end == "a" else s[0])[0] - P_[0], (s[1] if end == "a" else s[0])[1] - P_[1]) < 0.5]
            for face, k in (("o", -edge), ("i", bw - edge)):
                q = _line_x(off(P_, n, k), u, off(P_, nb[0][3], k), nb[0][2]) if nb else _line_x(off(P_, n, k), u, P_, along(P_, u))
                pts[face + end] = q or off(P_, n, k)
        quads.append([pts["oa"], pts["ob"], pts["ib"], pts["ia"]])
    return quads


def _palette(collection: str, color: str) -> List[str]:
    return BOARDS_PALETTE.get((collection, color), ["#8f6a42", "#a07a4d", "#b58a58", "#c49a68", "#d2ad7b"])


HARDIE_HEX = {"timber bark": "#4b3f34", "arctic white": "#ecebe4", "cobble stone": "#a9a296", "navajo beige": "#cdbd9f", "khaki brown": "#8a7558",
              "monterey taupe": "#8d8578", "iron gray": "#4c5154", "aged pewter": "#6e6c66", "mountain sage": "#8d9581", "light mist": "#dcdcd3",
              "sail cloth": "#e6e1d2", "evening blue": "#3d4a5c", "night gray": "#3b3d3f", "deep ocean": "#2f4a5a"}


def _hardie_hex(name: str) -> str:
    return HARDIE_HEX.get((name or "timber bark").lower().replace("(color tbd)", "").strip() or "timber bark", "#4b3f34")


def sun_vector(site) -> Optional[Tuple[float, float, float]]:
    """Unit vector toward the sun in the plan frame (x along the house, y out to the yard, z up) at site.sun_when, from the
    site's latitude / longitude (NOAA solar-position approximation, good to ~0.5 deg) and the bearing the deck faces."""
    if site.lat is None or site.lon is None or site.rear_azimuth_deg is None:
        return None
    from datetime import datetime
    when = datetime.fromisoformat(site.sun_when)
    n = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60.0
    g = 2 * math.pi / 365.0 * (n - 1 + (hour - 12) / 24.0)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hour * 60 + eqt + 4 * site.lon - 60 * site.utc_offset_h           # true solar time, minutes
    ha = math.radians(tst / 4 - 180)
    lat = math.radians(site.lat)
    cos_z = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
    zen = math.acos(max(-1.0, min(1.0, cos_z)))
    el = math.pi / 2 - zen
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(lat) - math.tan(decl) * math.cos(lat))) + 180.0   # from north, clockwise
    rel = math.radians(az - site.rear_azimuth_deg)
    return (-math.sin(rel) * math.cos(el), math.cos(rel) * math.cos(el), math.sin(el))


def sun_study_stills(site, view: str = "corner") -> List[Tuple[str, dict, str]]:
    """(still name, viewer params, caption) for the sun study: the hero date at 9, 12, 3 and 6, plus a winter afternoon.
    Empty when the site has no position. The caption names the clock time and the sun's compass bearing / height."""
    import dataclasses
    from datetime import datetime
    if site.lat is None or site.lon is None or site.rear_azimuth_deg is None:
        return []
    date_ = site.sun_when.split("T")[0]
    year = date_.split("-")[0]
    out = []
    for d_, t_, off in [(date_, "09:00", site.utc_offset_h), (date_, "12:00", site.utc_offset_h), (date_, "15:00", site.utc_offset_h), (date_, "18:00", site.utc_offset_h),
                        (f"{year}-12-21", "15:00", -7.0)]:
        v = sun_vector(dataclasses.replace(site, sun_when=f"{d_}T{t_}", utc_offset_h=off))
        if not v or v[2] <= 0.03:
            continue
        rel = math.degrees(math.atan2(-v[0], v[1]))
        az = (site.rear_azimuth_deg + rel) % 360
        el = math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))
        pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        dt = datetime.fromisoformat(f"{d_}T{t_}")
        lab = dt.strftime("%b %-d · %-I:%M %p").replace(":00", "")
        nm = f"sun-{dt.strftime('%m%d')}-{t_.replace(':', '')}"
        out.append((nm, dict(view=view, sun=",".join(f"{c:.4f}" for c in v)), f"{lab} — sun {pts[int((az + 11.25) // 22.5) % 16]}, {el:.0f}° up"))
    return out


def sun_study(site, times=("09:00", "12:00", "15:00", "18:00")) -> List[Tuple[str, Tuple[float, float, float]]]:
    """(label, vector) for the hero date at several clock times — the sun stills."""
    import dataclasses
    date_ = site.sun_when.split("T")[0]
    out = []
    for t in times:
        v = sun_vector(dataclasses.replace(site, sun_when=f"{date_}T{t}"))
        if v and v[2] > 0.05:
            out.append((t, v))
    return out


def materials_for(spec: DeckSpec) -> Dict[str, dict]:
    timber = spec.is_timber
    oiled = spec.framing.finish == "oil"
    f = decking_facts(spec.decking.collection)
    pal = _palette(spec.decking.collection, spec.decking.color)
    bpal = _palette(spec.decking.border_collection or spec.decking.collection, spec.decking.border_color or spec.decking.color)
    dpal = _palette(spec.railing.drink_rail_collection or spec.decking.border_collection or spec.decking.collection,
                    spec.railing.drink_rail_color or spec.decking.border_color or spec.decking.color)
    wood = "#6a4225" if (timber and oiled) else ("#a88a5e" if timber else "#b9a479")     # oiled dark walnut · unfinished DF · PT SYP
    return dict(
        timber=(dict(color="#a7adb2", metal=0.6, rough=0.42, label="CEMCO cold-formed steel, G90 galvanized") if spec.framing.system == "steel" else
                dict(color=wood, grain=True, rough=0.85, label=("Douglas fir #1, dark walnut oil" if oiled else "Douglas fir #1, unfinished") if timber else "#1 SYP pressure-treated")),
        ctimber=dict(color="#b98f62", grain=True, rough=0.85, label="cover framing: 6x6 " + post_words(spec) + " posts, beams, SYP rafters"),
        galv=dict(color="#9aa0a6", metal=0.6, rough=0.45, label="galvanized steel"),
        deck=dict(color=pal[len(pal) // 2], palette=pal, grain=True, rough=0.7, label=f"{spec.decking.brand} {spec.decking.collection} {spec.decking.color}"),
        border=dict(color=bpal[len(bpal) // 2], palette=bpal, grain=True, rough=0.7, label=f"{spec.decking.border_collection or spec.decking.collection} {spec.decking.border_color or spec.decking.color}"),
        drink=dict(color=dpal[len(dpal) // 2], palette=dpal, grain=True, rough=0.7),
        fascia=(dict(color=_hardie_hex(spec.extras.hardie_color), pattern="lap", rough=0.8, label=f"HardieTrim {spec.extras.hardie_skirt}") if spec.extras.hardie_skirt
                else dict(color=pal[max(0, len(pal) // 2 - 1)], palette=pal, grain=True, rough=0.7)),
        hardie=dict(color=_hardie_hex(spec.extras.hardie_color), pattern="lap", rough=0.8, label=f"James Hardie ColorPlus {spec.extras.hardie_color or 'Timber Bark'}"),
        soffit=dict(color=_hardie_hex(spec.extras.hardie_color), pattern="batten", rough=0.85, label=f"HardieSoffit cedarmill {spec.extras.hardie_color or 'Timber Bark'}"),
        shade=dict(color="#7a5c45", rough=0.9, opacity=0.82, label="the owner's roll-down blinds (kept)"),
        osb=dict(color="#c9a46a", rough=0.95, label="7/16\" OSB roof sheathing"),
        underlay=dict(color="#3d4651", rough=0.9, label="high-temp self-adhered underlayment"),
        steel=dict(color="#141416", metal=0.55, rough=0.5, label="black powder-coat"),
        sail=dict(color=_sail_hex(spec), rough=0.95, opacity=0.94, label="shade sail fabric"),
        railmetal=dict(color=_rail_hex(spec.railing.color), metal=0.55, rough=0.5, label=f"{spec.railing.color or 'black'} powder-coat"),
        cable=dict(color="#b8bcc2", metal=0.9, rough=0.35),
        concrete=dict(color="#b9b4aa", rough=0.95),
        stone=dict(color="#8c8478", pattern="stone", rough=0.95, label="ledgestone veneer"),
        brick=dict(color="#8e4a3a", pattern="brick", rough=0.95, label="brick"),
        stonecap=dict(color="#a8a297", rough=0.9),
        house=(dict(color="#d9d0bf", rough=0.95, label="stucco") if spec.geometry.house_finish == "stucco"
               else dict(color="#8e4a3a", pattern="brick", rough=0.95, label="brick") if spec.geometry.house_finish == "brick"
               else dict(color=spec.geometry.house_color or ("#5b544d" if timber else "#cfc6b4"), pattern="lap", rough=0.9)),
        trim=dict(color="#24221f" if timber else "#f2efe8", rough=0.8),
        roof=dict(color="#2a2624", rough=0.9),
        privacy=dict(color="#6a625a", pattern="batten", rough=0.9),
        glass=dict(color="#5f7f99", metal=0.6, rough=0.15),
        ssroof=dict(color=_roof_hex(spec.extras.cover_roof_color), pattern="seam", metal=0.55, rough=0.45, label=f"standing seam steel {spec.extras.cover_roof_color or '(color TBD)'}"),
        gutter=dict(color="#4b3f34", metal=0.35, rough=0.5, label=f"5\" K gutter {spec.extras.cover_gutter_color or 'to match the fascia'}"),
        ground=dict(color="#7d9958", pattern="grass", rough=1.0),
        gravel=dict(color="#857b6e", pattern="gravel", rough=1.0),
        water=dict(color="#3a93c6", metal=0.2, rough=0.08),
        tub=dict(color="#3b3531", pattern="batten", rough=0.75),
        tubrim=dict(color="#dad6cf", rough=0.35),
        hanger=dict(color="#1c1c1e" if spec.framing.hardware_finish == "black" else "#8f9498", metal=0.7, rough=0.5),
        **(__import__("decktakeoff.house", fromlist=["materials"]).materials(spec.geometry.house_model) if getattr(spec.geometry, "house_model", None) else {}),
        **(_site_materials(spec.geometry.site_model) if getattr(spec.geometry, "site_model", None) else {}),
        **__import__("decktakeoff.lighting", fromlist=["materials"]).materials(spec),     # led_riser / led_cap / led_housing when extras.lights is on
        **__import__("decktakeoff.louvered", fromlist=["materials"]).materials(spec),     # lvmetal / lvled / lvfabric when the job has a louvered roof
    )


def _site_materials(model: dict) -> Dict[str, dict]:
    from .landscape import materials as _lm, neighbour_materials as _nm
    return dict(_lm(model), **_nm(model))


def build_scene(L) -> Scene:
    if hasattr(L, "parts"):
        return build_composite_scene(L)
    spec = L.spec
    zt = spec.geometry.height_in * IN
    f = decking_facts(spec.decking.collection)
    bw, bt, gap = f["width"] * IN, f["thick"] * IN, spec.deck_gap * IN
    jb, jd = [v * IN for v in actual(spec.framing.joist_size)]
    timber = spec.is_timber
    fascia = spec.decking.fascia
    edge = ((L.decking.fascia_t + NOSE) if fascia else OVERHANG_NO_FASCIA) * IN
    fas_t = L.decking.fascia_t * IN
    jtop = zt - bt
    jbot = jtop - jd
    B: List[Box] = []
    add = lambda *a, **k: B.append(Box(*a, **k))
    W = L.finished_w * IN
    y_min = min(z.wall_y for z in L.zones) * IN
    y_front = max((z.wall_y + z.D) for z in L.zones) * IN
    H_house = zt + 10.0

    # ---------------- site: ground, rock under the deck, the house behind every zone's wall
    site_m = getattr(spec.geometry, "site_model", None)
    if site_m:                              # the measured yard owns the lot; a flat field beyond the fences fills the horizon
        bz = float(site_m.get("beyond_z", -0.9))     # a far field that sits low (a valley, a creek) keeps the box upright and below the yard
        add("ground", -140, W + 140, y_min - 90, y_front + 160, min(-1.6, bz - 0.6), bz, "ground")
    else:
        add("ground", -80, W + 80, y_min - 60, y_front + 90, -0.6, 0.0, "ground")
    for z in (L.zones if not getattr(spec.geometry, "house_model", None) else []):   # weed barrier + rock under the deck footprint only (a measured site: the site model owns the ground)
        add("gravel", z.x0 * IN - 0.5, (z.x0 + z.W) * IN + 0.5, z.wall_y * IN, (z.wall_y + z.D) * IN + 0.5, 0.0, 0.04, "gravel")
    depth_back = 26.0
    H_house = zt + 9.5                      # one storey above the deck floor
    door_h = 6.75
    if getattr(spec.geometry, "house_model", None):
        from .house import build_house
        def _mesh(kind, tri, mat, tag=""):
            xs_ = [q[0] for q in tri]; ys_ = [q[1] for q in tri]; zs_ = [q[2] for q in tri]
            B.append(Box(kind, min(xs_), max(xs_), min(ys_), max(ys_), min(zs_), max(zs_), mat, 0, tag=tag, shape="mesh", pts=[[round(v, 3) for v in q] for q in tri]))
        n_h = len(B)
        build_house(spec.geometry.house_model, add, lambda *a, **k: B.append(rot_box(*a, **k)), _mesh)
        for b_ in B[n_h:]:
            b_.layer = "house"
        if site_m:
            from .landscape import build_site
            n0 = len(B)
            build_site(site_m, add, lambda *a, **k: B.append(rot_box(*a, **k)), _mesh, zt)
            for b_ in B[n0:]:
                b_.layer = "site"
    elif spec.geometry.house_blocks:
        draw_house_from_spec(add, spec, zt, H_house)
    for _c in (spec.geometry.covers or []):
        draw_cover(add, spec, dict(COVER_DEFAULTS, **_c), zt)
    draw_sails(add, spec)
    __import__("decktakeoff.louvered", fromlist=["draw"]).draw(add, L)     # louvered roofs this layout owns (a composite's job-level roof: drawn once there)
    draw_benches(add, spec, zt, fixed_append=lambda b: B.append(b))
    # a deck or roof above this one (existing, drawn for context) and the columns that carry it through this deck
    for ov in (spec.geometry.overhead or []):
        ox0, ox1, oy0, oy1, zu, zo = [float(v) for v in ov[:6]]
        add("house", ox0, ox1, oy0, oy1, zu, zo, "soffit", 8, tag="deck above (existing)")
        add("trim", ox0 - 0.05, ox1 + 0.05, oy1 - 0.08, oy1 + 0.05, zu - 0.9, zo, "house", 8, tag="rim of the deck above")
        add("privacy", ox0, ox1, oy1 - 0.3, oy1 + 0.35, zo, zo + 3.5, "house", 8, tag="parapet of the deck above")
    for tc in (spec.geometry.through_columns or []):
        cx_, cy_, sz = float(tc[0]), float(tc[1]), float(tc[2]) if len(tc) > 2 else 0.67
        z_top = max([float(ov[4]) for ov in (spec.geometry.overhead or [])] + [zt + 8.0])
        add("post", cx_ - sz / 2, cx_ + sz / 2, cy_ - sz / 2, cy_ + sz / 2, 0.0, z_top, "house", 8, tag="existing column through the deck (stays)")
    if not spec.geometry.house_blocks:      # (was a for-else: the stand-in house was drawn over the measured blocks too)
        for zi, z in enumerate(L.zones):
            yw = z.wall_y * IN
            x0h = z.x0 * IN - (3.0 if zi == 0 else 0.0)
            x1h = (z.x0 + z.W) * IN + (3.0 if zi == len(L.zones) - 1 else 0.0)
            add("house", x0h, x1h, yw - depth_back, yw, 0.0, H_house, "house", tag=f"house behind {z.name}")
            add("roof", x0h - 1.0, x1h + 1.0, yw - depth_back - 1.0, yw + 1.0, H_house, H_house + 0.55, "roof")
            add("trim", x0h - 1.0, x1h + 1.0, yw + 0.98, yw + 1.02, H_house - 0.02, H_house + 0.55, "trim", tag="fascia board")
            # a sliding door at deck level in the middle of every zone; windows either side of it on the wide zones
            cx = (z.x0 + z.W / 2) * IN
            dw = 6.0 if z.W > 120 else 3.0
            add("trim", cx - dw / 2 - 0.25, cx + dw / 2 + 0.25, yw - 0.05, yw + 0.06, zt + 0.02, zt + door_h + 0.25, "trim")
            add("glass", cx - dw / 2, cx + dw / 2, yw - 0.02, yw + 0.07, zt + 0.1, zt + door_h, "glass")
            if dw > 4:
                add("trim", cx - 0.06, cx + 0.06, yw - 0.02, yw + 0.08, zt + 0.1, zt + door_h, "trim")
            if z.W > 200:
                for sx in (-1, 1):
                    wx = cx + sx * (z.W * IN / 4 + 1.0)
                    add("trim", wx - 1.75, wx + 1.75, yw - 0.05, yw + 0.06, zt + 2.9, zt + 7.1, "trim")
                    add("glass", wx - 1.5, wx + 1.5, yw - 0.02, yw + 0.07, zt + 3.0, zt + 7.0, "glass")
            if zt >= 7.0:   # walkout level below the deck
                for sx in (-1, 1) if z.W > 200 else (0,):
                    wx = cx + sx * (z.W * IN / 4 + 1.0)
                    add("trim", wx - 1.75, wx + 1.75, yw - 0.05, yw + 0.06, 3.4, 5.6, "trim")
                    add("glass", wx - 1.5, wx + 1.5, yw - 0.02, yw + 0.07, 3.5, 5.5, "glass")
    # the return walls of a recess are the sides of the neighbouring block, drawn so they shade the wing
    for a, b in ([] if spec.geometry.house_blocks else zip(L.zones, L.zones[1:])):
        ya, yb = a.wall_y * IN, b.wall_y * IN
        if abs(ya - yb) > 0.01:
            xb = b.x0 * IN
            if ya < yb:
                add("wall", xb, xb + 0.5, ya, yb, 0.0, H_house, "house", tag=f"return wall {a.name}/{b.name}")
            else:
                add("wall", xb - 0.5, xb, yb, ya, 0.0, H_house, "house", tag=f"return wall {a.name}/{b.name}")
    # a privacy wall is an option in the sell package: shown in the finished room (phase 8), on the deck, along that end
    for zi, z in enumerate(L.zones):
        zl = spec.zone_list[zi]
        if zl.privacy_wall:
            side_x = (z.x0 * IN) if zi == 0 else ((z.x0 + z.W) * IN)
            if getattr(zl, "end_wall", "privacy") == "house":   # the house's own return wall runs the length of this end
                xa, xb = (side_x - 0.6, side_x) if zi == 0 else (side_x, side_x + 0.6)
                add("wall", xa, xb, z.wall_y * IN - 0.6, (z.wall_y + z.D) * IN + 0.6, 0.0, H_house, "house", tag="existing house wall")
                add("roof", xa - 1.0, xb + 1.0, z.wall_y * IN - 1.0, (z.wall_y + z.D) * IN + 1.0, H_house, H_house + 0.55, "roof")
            else:
                xa, xb = (side_x - 0.4, side_x) if zi == 0 else (side_x, side_x + 0.4)
                add("privacy", xa, xb, z.wall_y * IN, (z.wall_y + z.D) * IN, zt - 0.3, zt + 6.75, "privacy", 8, tag="privacy wall (option)")
                add("trim", xa - 0.03, xb + 0.03, z.wall_y * IN, (z.wall_y + z.D) * IN, zt + 6.75, zt + 6.95, "steel", 8, tag="privacy wall cap")

    # ---------------- beams, posts, footings (from the beam lines)
    ft = spec.framing.footing_type
    pb_ = actual(spec.framing.post_size)[0] * IN
    from .takeoff import cover_posts_x
    shared_xy = [(px, float(c["y1"])) for c in covers_of(spec) if c.get("footing") == "deck_pier" for px in cover_posts_x(c)]
    for li, ln in enumerate(L.beam_lines):
        bw_, bd_ = ln.width * IN, ln.depth * IN
        y = ln.y * IN
        top = jbot if ln.kind == "drop" else jtop
        for a, b in ln.pieces:
            add("beam", a * IN, b * IN, y - bw_ / 2, y + bw_ / 2, top - bd_, top, "timber", 4, tag=ln.label)
        for pi, px in enumerate(ln.posts_x):
            x = px * IN
            if ft in ("caisson", "existing"):
                add("footing", x - 10 / 12, x + 10 / 12, y - 10 / 12, y + 10 / 12, -1.0, 0.5, "concrete", 1, tag=f"caisson P{li}-{pi + 1}" + (" (existing)" if ft == "existing" else ""), shape="cyl")
                base_top = 0.5
            elif ft == "diamond_pier":
                add("footing", x - 0.45, x + 0.45, y - 0.45, y + 0.45, -0.2, 0.3, "concrete", 1, tag="Diamond Pier")
                base_top = 0.3
            else:
                add("footing", x - 0.6, x + 0.6, y - 0.6, y + 0.6, -1.0, 0.15, "concrete", 1, shape="cyl")
                base_top = 0.15
            if spec.framing.existing_posts:   # the existing stucco column stays: 16" square, no base
                add("post", x - 0.67, x + 0.67, y - 0.67, y + 0.67, base_top, top - bd_, "house", 2, tag=f"existing column P{pi + 1}")
            elif any(abs(x - cx) < 1.0 and abs(y - cy) < 1.0 for cx, cy in shared_xy):
                add("base", x - 0.27, x + 0.27, y - 0.27, y + 0.27, base_top, base_top + 0.12, "steel", 2)
                continue                      # the 6x6 cover post stands on this pier and carries the beam (drawn with the cover)
            elif spec.framing.system == "steel" and spec.framing.steel_deck_post == "wood":
                hw_ = 0.25 if spec.framing.post_rough else 0.23
                add("base", x - hw_ - 0.02, x + hw_ + 0.02, y - hw_ - 0.02, y + hw_ + 0.02, base_top, base_top + 0.12, "steel", 2)
                add("post", x - hw_, x + hw_, y - hw_, y + hw_, base_top + 0.1, top - bd_, "ctimber", 2, tag=f"P{pi + 1} 6x6 Douglas fir" + (" rough" if spec.framing.post_rough else ""))
            elif spec.framing.system == "steel":
                add("base", x - 0.2, x + 0.2, y - 0.2, y + 0.2, base_top, base_top + 0.1, "galv", 2)
                add("post", x - 0.125, x + 0.125, y - 0.125, y + 0.125, base_top + 0.1, top - bd_, "timber", 2, tag=f"P{pi + 1} 3x3 HSS")
            else:
                add("base", x - pb_ / 2 - 0.02, x + pb_ / 2 + 0.02, y - pb_ / 2 - 0.02, y + pb_ / 2 + 0.02, base_top, base_top + 0.12, "steel", 2)
                add("post", x - pb_ / 2, x + pb_ / 2, y - pb_ / 2, y + pb_ / 2, base_top + 0.1, top - bd_, "timber", 2, tag=f"P{pi + 1}")
            add("cap", x - pb_ / 2 - 0.03, x + pb_ / 2 + 0.03, y - bw_ / 2 - 0.03, y + bw_ / 2 + 0.03, top - bd_ - 0.02, top - bd_ + 0.35, "steel", 4)
            if spec.framing.knee_braces and not spec.framing.existing_posts and spec.framing.system != "steel":
                lg, th = spec.framing.knee_leg_in / 12.0, 3.5 / 12.0
                Lb, zb = lg * math.sqrt(2) + th, top - bd_
                sx = 1 if px * IN < (ln.pieces[0][0] + ln.pieces[-1][1]) * IN / 2 else -1     # along the beam: toward the middle
                cx_ = x + sx * (pb_ / 2 + lg / 2)
                add("brace", cx_ - Lb / 2, cx_ + Lb / 2, y - th / 2, y + th / 2, zb - lg / 2 - th / 2, zb - lg / 2 + th / 2, "timber", 3,
                    tag="4x4 knee brace (along the beam)", rot=sx * math.pi / 4, rot_axis="y")
                zj = top if ln.kind == "drop" else top - bd_      # up to the joist bottoms, toward the house
                cy_ = y - bw_ / 2 - lg / 2
                add("brace", x - th / 2, x + th / 2, cy_ - Lb / 2, cy_ + Lb / 2, zj - lg / 2 - th / 2, zj - lg / 2 + th / 2, "timber", 3,
                    tag="4x4 knee brace (to the joists)", rot=math.pi / 4, rot_axis="x")
            if spec.extras.stone_bases:
                add("stone", x - 1.0, x + 1.0, y - 1.0, y + 1.0, 0.0, 3.0, "stone", 3)
                add("stonecap", x - 1.08, x + 1.08, y - 1.08, y + 1.08, 3.0, 3.17, "stonecap", 3)

    # ---------------- edge posts: under both rim ends at the outline corners (the rims span post to post as flush beams)
    for ep in (getattr(L, "edge_posts", None) or []):
        x, y = ep.x * IN, ep.y * IN
        if ft == "diamond_pier":
            add("footing", x - 0.45, x + 0.45, y - 0.45, y + 0.45, -0.2, 0.3, "concrete", 1, tag="Diamond Pier")
            base_top = 0.3
        else:
            add("footing", x - 0.6, x + 0.6, y - 0.6, y + 0.6, -1.0, 0.15, "concrete", 1, shape="cyl")
            base_top = 0.15
        add("base", x - pb_ / 2 - 0.02, x + pb_ / 2 + 0.02, y - pb_ / 2 - 0.02, y + pb_ / 2 + 0.02, base_top, base_top + 0.12, "steel", 2)
        add("post", x - pb_ / 2, x + pb_ / 2, y - pb_ / 2, y + pb_ / 2, base_top + 0.1, jbot, "timber", 2, tag=f"{ep.label} edge post")

    # ---------------- frame: a polygon outline is framed as one continuous field (the takeoff counts the same members)
    from .layout import outline_framing
    OF = outline_framing(spec, L)
    if OF is not None:
        for x0_, y0_, x1_, y1_ in OF.ledgers + OF.ledger_blocks:
            B.append(rot_box("ledger", x0_ * IN, y0_ * IN, x1_ * IN, y1_ * IN, jbot, jtop, "timber", 5, jb, tag="ledger"))
        for i_, k_, x0_, y0_, x1_, y1_ in OF.rims:
            B.append(rot_box("rim", x0_ * IN, y0_ * IN, x1_ * IN, y1_ * IN, jbot, jtop, "timber", 5, jb, tag=f"rim side {i_ + 1} ply {k_ + 1}"))
        for X_, ya_, yb_, ea_, eb_, lab_ in OF.joists:
            add("joist", X_ * IN - jb / 2, X_ * IN + jb / 2, ya_ * IN, yb_ * IN, jbot, jtop, "timber", 5, tag=lab_)
        for x0_, y0_, x1_, y1_, lab_ in OF.blocks:
            B.append(rot_box("block", x0_ * IN, y0_ * IN, x1_ * IN, y1_ * IN, jbot, jtop, "timber", 5, jb, tag=lab_))
        if fascia:
            # fascia on every open side, outside the rim, mitred at the corners
            Pq = [(float(x), float(y)) for x, y in spec.geometry.outline]
            from .layout import step_skirt_layout
            _sk = step_skirt_layout(spec) if getattr(spec.geometry, "step_skirt", None) else None
            _skirted = {f_.edge for f_ in _sk.faces} if _sk else set()       # the step skirt's vertical panels are the fascia there
            for e_, kind_ in zip(L.outline_edges, OF.side_kind):
                if kind_ not in ("rim", "rim45") or e_.name in _skirted:
                    continue
                ex0, ey0, ex1, ey1 = e_.x0 * IN, e_.y0 * IN, e_.x1 * IN, e_.y1 * IN
                Le = math.hypot(ex1 - ex0, ey1 - ey0); ux_, uy_ = (ex1 - ex0) / Le, (ey1 - ey0) / Le
                nx_, ny_ = -uy_, ux_                    # outward (the outline runs clockwise in the plan frame)
                ox, oy = nx_ * fas_t / 2, ny_ * fas_t / 2
                B.append(rot_box("fascia", ex0 + ox - ux_ * fas_t / 2, ey0 + oy - uy_ * fas_t / 2, ex1 + ox + ux_ * fas_t / 2, ey1 + oy + uy_ * fas_t / 2,
                                 jbot - 0.15, zt - 0.02, "fascia", 6, fas_t, tag=f"fascia side {e_.name}"))
    # ---------------- frame per zone
    for zi, z in enumerate(L.zones if OF is None else []):
        fr = z.frame
        x0, W_z = z.x0 * IN, z.W * IN
        yw = z.wall_y * IN
        yf = yw + z.D * IN
        rim_t = fr.rim_plies * jb
        rear_t = (jb if fr.ledger else rim_t)
        if fr.ledger:
            add("ledger", x0, x0 + W_z, yw, yw + jb, jbot, jtop, "timber", 5, tag=f"ledger {z.name}")
        else:
            for k in range(fr.rim_plies):
                add("rim", x0, x0 + W_z, yw + k * jb, yw + (k + 1) * jb, jbot, jtop, "timber", 5)
        # joist runs: one bay, or split at a mid flush beam
        flush_mid = sorted([b for b in fr.beams if b.kind == "flush" and b.cl_y + b.width / 2 < z.D - 0.5], key=lambda b: b.cl_y)
        bays: List[Tuple[float, float]] = []
        front_beam = [b for b in fr.beams if b.kind == "flush" and b.cl_y + b.width / 2 >= z.D - 0.5]
        front_t = max([rim_t] + [b.width * IN for b in front_beam])     # a front flush beam is the front rim, at its own width
        ya = yw + rear_t
        for b in flush_mid:
            bays.append((ya, yw + (b.cl_y - b.width / 2) * IN - 0.02)); ya = yw + (b.cl_y + b.width / 2) * IN + 0.02
        bays.append((ya, yf - front_t))
        xs = [x0 + jx * IN for jx in fr.joist_x] + [x0 + px * IN for px in fr.pf_x]
        for dx, Ld, lab in L.divider_x:
            if x0 - 0.05 <= dx * IN <= x0 + W_z + 0.05 and (dx * IN < x0 + W_z - 0.05 or zi == len(L.zones) - 1):
                xs += [dx * IN - jb, dx * IN + jb]
        for xj in xs:
            for (ya_, yb_) in bays:
                add("joist", xj - jb / 2, xj + jb / 2, ya_, yb_, jbot, jtop, "timber", 5)
        for k in range(fr.rim_plies):
            add("rim", x0 + k * jb, x0 + (k + 1) * jb, yw + rear_t, yf - front_t, jbot, jtop, "timber", 5, tag="side rim")
            add("rim", x0 + W_z - (k + 1) * jb, x0 + W_z - k * jb, yw + rear_t, yf - front_t, jbot, jtop, "timber", 5, tag="side rim")
            if not any(b.label.startswith("FRONT FLUSH") for b in fr.beams):
                add("rim", x0, x0 + W_z, yf - (k + 1) * jb, yf - k * jb, jbot, jtop, "timber", 5, tag="front rim")
        # blocking
        allx = sorted(set([x0 + rim_t] + xs + [x0 + W_z - rim_t]))
        for by in fr.blocking_rows_y:
            yy = yw + by * IN
            for a, b in zip(allx, allx[1:]):
                if b - a > jb * 1.5:
                    add("block", a + jb / 2, b - jb / 2, yy - jb / 2, yy + jb / 2, jbot, jtop, "timber", 5)
        # fascia
        if fascia:
            add("fascia", x0 - fas_t, x0, yw, yf + fas_t, jbot - 0.15, zt - 0.02, "fascia", 6)
            add("fascia", x0 + W_z, x0 + W_z + fas_t, yw, yf + fas_t, jbot - 0.15, zt - 0.02, "fascia", 6)
            add("fascia", x0 - fas_t, x0 + W_z + fas_t, yf, yf + fas_t, jbot - 0.15, zt - 0.02, "fascia", 6)

    # ---------------- decking
    pf = spec.geometry.picture_frame
    seed = 7
    def tone():
        nonlocal seed
        seed = (seed * 1103515245 + 12345) % (2 ** 31)
        return (seed / 2 ** 31) * 2 - 1
    for zi, z in enumerate(L.zones if L.plan is None else []):
        dk = z.decking
        x0, W_z = z.x0 * IN, z.W * IN
        yw = z.wall_y * IN
        yf = yw + z.D * IN
        y_out = yf + edge
        left_end = zi == 0 and not spec.zone_list[zi].privacy_wall
        right_end = zi == len(L.zones) - 1 and not spec.zone_list[zi].privacy_wall
        xa = x0 - (edge if zi == 0 else 0.0)
        xb = x0 + W_z + (edge if zi == len(L.zones) - 1 else 0.0)
        # boundary dividers (length from the front) and mid dividers in this zone
        bl = next((Ld for dx, Ld, lab in L.divider_x if abs(dx - z.x0) < 0.6 and zi > 0), None)
        br = next((Ld for dx, Ld, lab in L.divider_x if abs(dx - (z.x0 + z.W)) < 0.6 and zi < len(L.zones) - 1), None)
        mids = sorted(dx * IN for dx, Ld, lab in L.divider_x if z.x0 + 0.6 < dx < z.x0 + z.W - 0.6)
        def field_x(y_center: float) -> List[Tuple[float, float]]:
            d_front = y_out - y_center
            lt = (bw + gap) if (left_end and pf) else 0.0
            rt = (bw + gap) if (right_end and pf) else 0.0
            if bl is not None and pf and (d_front * 12 <= bl + 0.5 or bl >= z.D - 24):
                lt = bw / 2 + gap
            if br is not None and pf and (d_front * 12 <= br + 0.5 or br >= z.D - 24):
                rt = bw / 2 + gap
            cuts = [xa + lt] + [m for m in mids] + [xb - rt]
            out = []
            for k, (a, b) in enumerate(zip(cuts, cuts[1:])):
                aa = a + (bw / 2 + gap if 0 < k else 0)
                bb = b - (bw / 2 + gap if k < len(cuts) - 2 else 0)
                out.append((aa, bb))
            return out
        # front border and field rows (from the outer edge inward)
        y1 = y_out
        if pf:
            add("border", xa, xb, y1 - bw, y1, zt - bt, zt, "border", 6, tone=tone())
            y1 -= bw + gap
        for i in range(dk.rows):
            for (a, b) in field_x(y1 - bw / 2):
                add("board", a, b, y1 - bw, y1, zt - bt, zt, "deck", 6, tone=tone())
            y1 -= bw + gap
        rip = y1 - yw
        if rip > 0.04:
            for (a, b) in field_x(y1 - rip / 2):
                add("board", a, b, yw + 0.01, y1, zt - bt, zt, "deck", 6, tone=tone())
        if pf and left_end:
            add("border", xa, xa + bw, yw, y_out, zt - bt, zt, "border", 6, tone=tone())
        if pf and right_end:
            add("border", xb - bw, xb, yw, y_out, zt - bt, zt, "border", 6, tone=tone())
    if L.plan is None:
        for dx, Ld, lab in L.divider_x:
            x = dx * IN
            add("border", x - bw / 2, x + bw / 2, y_front - Ld * IN, y_front + edge, zt - bt, zt, "border", 6, tag=lab, tone=tone())
    else:
        # boards from the outline plan: one piece per row segment, borders along every exposed edge (the curve in mitred segments), breakers
        P = L.plan
        # A row is cut square at its centre crossing of the frame line: on a 45-degree side that leaves a 2.7" gap at one
        # corner and a 2.7" overlap at the other. In the model each end runs half a board under the frame or breaker it
        # butts, and the frame sits 1/32" proud, so the frame covers the end as the mitred cut does (the cut list keeps
        # the true lengths).
        ext, lift = bw / 2, 1 / 384
        for r in P.rows:                 # (an end against a house wall runs into the wall the same way, as a scribed cut)
            add("board", r.x0 * IN - ext, r.x1 * IN + ext, r.y0 * IN, r.y1 * IN, zt - bt, zt, "deck", 6, tag="pf field" + (" rip" if r.rip else ""), tone=tone())
        from .layout import _poly_orient
        poly_in = [(float(x) * 12, float(y) * 12) for x, y in spec.geometry.outline]
        sgn = _poly_orient(poly_in)
        quads = _mitred_quads(P.borders, poly_in, sgn, edge / IN, bw / IN)
        # Boxes that overlap must not share a top face (a coplanar overlap renders black in the photoreal pass and
        # z-fights in the viewer): the breakers sit one lift up, the frame above them by its run (horizontal, vertical,
        # each diagonal), so where two pieces cross the one on top shows.
        for (x0_, y0_, x1_, y1_, _), qd in zip(P.borders, quads):
            L_e = math.hypot(x1_ - x0_, y1_ - y0_) * IN
            ux, uy = (x1_ - x0_) / (L_e / IN), (y1_ - y0_) / (L_e / IN)
            nx, ny = -uy * sgn, ux * sgn                       # inward
            off = bw / 2 - edge                                  # the border's centre line: half a board in from the overhang
            cx, cy = (x0_ + x1_) / 2 * IN + nx * off, (y0_ + y1_) / 2 * IN + ny * off
            lv = lift * (1.5 if abs(y1_ - y0_) < 0.5 else 2.0 if abs(x1_ - x0_) < 0.5 else 2.5 if (x1_ - x0_) * (y1_ - y0_) > 0 else 3.0)
            if abs(y1_ - y0_) < 0.5:
                add("border", cx - L_e / 2 - bw / 2, cx + L_e / 2 + bw / 2, cy - bw / 2, cy + bw / 2, zt - bt + lv, zt + lv, "border", 6, tag="pf border", tone=tone())
            elif abs(x1_ - x0_) < 0.5:
                add("border", cx - bw / 2, cx + bw / 2, cy - L_e / 2 - bw / 2, cy + L_e / 2 + bw / 2, zt - bt + lv, zt + lv, "border", 6, tag="pf border", tone=tone())
            else:
                phi = math.atan2(y1_ - y0_, x1_ - x0_)
                add("border", cx - L_e / 2 - 0.1, cx + L_e / 2 + 0.1, cy - bw / 2, cy + bw / 2, zt - bt + lv, zt + lv, "border", 6, tag="pf border (mitred)", rot=phi, rot_axis="z", tone=tone())
            B[-1].quad = [[px * IN, py * IN] for px, py in qd]
        for x, y_lo, y_hi, lab in P.dividers:
            add("border", x * IN - bw / 2, x * IN + bw / 2, y_lo * IN, y_hi * IN, zt - bt + lift, zt + lift, "border", 6, tag=f"breaker {lab}", tone=tone())
    fixed = B

    # ---------------- rail
    rl = L.rail
    if rl:
        sysd = rail_system_for(spec.railing)
        cable = sysd.get("cable", False)
        pw = sysd["post_w"] * IN
        h = rl.height * IN
        prof = sysd.get("profile") or {}                   # the system's own members (ft): IRX's Modern top rail is wide and flat
        trw, trh = prof.get("top", (0.12, 0.08))
        brw, brh = prof.get("bottom", (0.12, 0.08))
        bal, bal_oc = prof.get("baluster", 0.06), prof.get("baluster_oc_in", 4.0) * IN
        # posts on a curved run move onto the curve (inset RP), so the rail between them follows the outline without a kink
        RP_ = 2.5 * IN
        shift: Dict[Tuple[float, float], Tuple[float, float]] = {}
        for ex0, ex1, ey0 in front_runs(L):
            ey1 = ey0
            if not outline_path(spec, (ex0, ey0), (ex1, ey1)):
                continue     # straight run
            poly_ = outline_path(spec, (ex0, ey0), (ex1, ey1), ends=True)
            def y_at(x):
                for (p0, q0), (p1, q1) in zip(poly_, poly_[1:]):
                    if min(p0, p1) - 1e-6 <= x <= max(p0, p1) + 1e-6 and abs(p1 - p0) > 1e-6:
                        return q0 + (q1 - q0) * (x - p0) / (p1 - p0)
                return None
            for p in rl.posts:
                px_, py_ = p.x * IN, p.y * IN
                if min(ex0, ex1) - 0.05 <= px_ <= max(ex0, ex1) + 0.05 and abs(py_ - (ey0 - RP_)) < 0.3:
                    yy = y_at(px_)
                    if yy is not None:
                        shift[(round(px_, 3), round(py_, 3))] = (px_, yy - RP_)
        def sh(x, y):
            return shift.get((round(x, 3), round(y, 3)), (x, y))
        sail_xy = [(float(sl["corners"][k][0]), float(sl["corners"][k][1])) for sl in (spec.geometry.sails or []) if sl.get("mount") == "deck_rail" for k in sl.get("posts", [])]
        for p in rl.posts:
            x, y = sh(p.x * IN, p.y * IN)
            if any(abs(x - sx) < 0.4 and abs(y - sy) < 0.4 for sx, sy in sail_xy):
                continue                       # the sail post is this corner post
            if getattr(p, "roof", False):
                continue                       # a louvered-roof post is the rail post here (louvered.py draws it)
            over_ = spec.railing.drink_rail and (spec.railing.drink_rail_mount or "between") == "over"
            add("railpost", x - pw / 2, x + pw / 2, y - pw / 2, y + pw / 2, zt, zt + h + (0.06 if over_ else 0.0), "railmetal", 7, tag=p.kind)
            if not over_:          # over-the-post drink rail: the post is cut level under the board, no cap
                add("railcap", x - pw / 2 - 0.03, x + pw / 2 + 0.03, y - pw / 2 - 0.03, y + pw / 2 + 0.03, zt + h, zt + h + 0.06, "railmetal", 7)
        # sections: reconstruct post pairs along each edge run from the post list order
        posts = [(p.x * IN, p.y * IN) for p in rl.posts]
        pairs = _rail_pairs(rl)
        for (xa, ya), (xb, yb) in pairs:
            curve = outline_path(spec, (xa, ya + RP_), (xb, yb + RP_)) if abs(yb - ya) < 0.05 else []
            if curve:
                # a curved run: rail along the outline, inset RP toward the deck; the end posts already sit on the curve
                (xa, ya), (xb, yb) = sh(xa, ya), sh(xb, yb)
                pts_ = [(xa, ya)] + [(px, py - RP_) for px, py in curve] + [(xb, yb)]
                for (p0, q0), (p1, q1) in zip(pts_, pts_[1:]):
                    B.append(rot_box("toprail", p0, q0, p1, q1, zt + h - trh, zt + h, "railmetal", 7, trw))
                    if cable:
                        for k in range(10):
                            zc = zt + 0.3 + k * 0.27
                            B.append(rot_box("cable", p0, q0, p1, q1, zc - 0.01, zc + 0.01, "cable", 7, 0.02))
                    else:
                        B.append(rot_box("botrail", p0, q0, p1, q1, zt + 0.25, zt + 0.25 + brh, "railmetal", 7, brw))
                        n_ = int(math.hypot(p1 - p0, q1 - q0) / bal_oc)
                        for k in range(1, n_):
                            t_ = k / n_
                            bx_, by_ = p0 + (p1 - p0) * t_, q0 + (q1 - q0) * t_
                            add("baluster", bx_ - bal / 2, bx_ + bal / 2, by_ - bal / 2, by_ + bal / 2, zt + 0.25 + brh, zt + h - trh, "railmetal", 7)
                continue
            if abs(yb - ya) > 0.01 and abs(xb - xa) > 0.01:
                # an angled outline side: rails as rotated boxes post to post
                B.append(rot_box("toprail", xa, ya, xb, yb, zt + h - trh, zt + h, "railmetal", 7, trw))
                if cable:
                    for k in range(10):
                        zc = zt + 0.3 + k * 0.27
                        B.append(rot_box("cable", xa, ya, xb, yb, zc - 0.01, zc + 0.01, "cable", 7, 0.02))
                else:
                    B.append(rot_box("botrail", xa, ya, xb, yb, zt + 0.25, zt + 0.25 + brh, "railmetal", 7, brw))
                    n_ = int(math.hypot(xb - xa, yb - ya) / bal_oc)
                    for k in range(1, n_):
                        bx_, by_ = xa + (xb - xa) * k / n_, ya + (yb - ya) * k / n_
                        add("baluster", bx_ - bal / 2, bx_ + bal / 2, by_ - bal / 2, by_ + bal / 2, zt + 0.25 + brh, zt + h - trh, "railmetal", 7)
                if spec.railing.drink_rail:
                    B.append(rot_box("drink", xa, ya, xb, yb, zt + h + 0.06, zt + h + 0.06 + 0.08, "drink", 7, 0.45))
                continue
            horiz = abs(yb - ya) < 0.01
            if horiz:
                x0_, x1_ = min(xa, xb), max(xa, xb); y0_, y1_ = ya - trw / 2, ya + trw / 2
            else:
                x0_, x1_ = xa - trw / 2, xa + trw / 2; y0_, y1_ = min(ya, yb), max(ya, yb)
            add("toprail", x0_, x1_, y0_, y1_, zt + h - trh, zt + h, "railmetal", 7)
            if cable:
                for k in range(10):
                    zc = zt + 0.3 + k * 0.27
                    if horiz:
                        add("cable", x0_, x1_, ya - 0.01, ya + 0.01, zc - 0.01, zc + 0.01, "cable", 7)
                    else:
                        add("cable", xa - 0.01, xa + 0.01, y0_, y1_, zc - 0.01, zc + 0.01, "cable", 7)
            else:
                if horiz:
                    add("botrail", x0_, x1_, ya - brw / 2, ya + brw / 2, zt + 0.25, zt + 0.25 + brh, "railmetal", 7)
                else:
                    add("botrail", xa - brw / 2, xa + brw / 2, y0_, y1_, zt + 0.25, zt + 0.25 + brh, "railmetal", 7)
                n = int(((x1_ - x0_) if horiz else (y1_ - y0_)) / bal_oc)
                for k in range(1, n):
                    t = k * bal_oc
                    if horiz:
                        add("baluster", x0_ + t - bal / 2, x0_ + t + bal / 2, ya - bal / 2, ya + bal / 2, zt + 0.25 + brh, zt + h - trh, "railmetal", 7)
                    else:
                        add("baluster", xa - bal / 2, xa + bal / 2, y0_ + t - bal / 2, y0_ + t + bal / 2, zt + 0.25 + brh, zt + h - trh, "railmetal", 7)
            if spec.railing.drink_rail:
                if horiz:
                    add("drink", x0_ - pw / 2, x1_ + pw / 2, ya - bw / 2, ya + bw / 2, zt + h + 0.06, zt + h + 0.06 + bt, "drink", 7, tone=tone())
                else:
                    add("drink", xa - bw / 2, xa + bw / 2, y0_ - pw / 2, y1_ + pw / 2, zt + h + 0.06, zt + h + 0.06 + bt, "drink", 7, tone=tone())

    # ---------------- the step-face skirt (geometry.step_skirt): vertical fascia panels cut to height, on 2x4 nailers hung from the rim
    from .layout import step_skirt_layout, RAIL_POST_INSET as _RP
    SK = step_skirt_layout(spec) if getattr(spec.geometry, "step_skirt", None) else None
    for f_ in (SK.faces if SK else []):
        Lf_ = math.hypot(f_.x1 - f_.x0, f_.y1 - f_.y0)
        def _strip(a, b, o0, o1, f_=f_, ux_=(f_.x1 - f_.x0) / Lf_, uy_=(f_.y1 - f_.y0) / Lf_):
            """Plan box (feet) of the strip a..b along the side (inches), o0..o1 off it (inches, + outward)."""
            pts = [((f_.x0 + ux_ * p + f_.nx * o) * IN, (f_.y0 + uy_ * p + f_.ny * o) * IN) for p in (a, b) for o in (o0, o1)]
            return min(q[0] for q in pts), max(q[0] for q in pts), min(q[1] for q in pts), max(q[1] for q in pts)
        for i_, pieces in enumerate(f_.panels):
            tn_ = tone()
            for a, b, zb in pieces:
                x0_, x1_, y0_, y1_ = _strip(a, b, 0.0, fas_t / IN)
                add("fascia", x0_, x1_, y0_, y1_, zt + zb * IN, zt + SK.z_top * IN, "fascia", 6, tag=f"step skirt {f_.edge} panel {i_ + 1}", tone=tn_)
        for p, zb in f_.studs:
            x0_, x1_, y0_, y1_ = _strip(p - 1.75, p + 1.75, -1.5, 0.0)
            add("block", x0_, x1_, y0_, y1_, zt + zb * IN, zt + SK.rim_bottom * IN, "timber", 5, tag="step skirt stud")
        for a, b, zc in f_.rows:
            x0_, x1_, y0_, y1_ = _strip(a, b, -1.5, 0.0)
            add("block", x0_, x1_, y0_, y1_, zt + (zc - 1.75) * IN, zt + (zc + 1.75) * IN, "timber", 5, tag="step skirt blocking")

    def draw_inset_stair(st):
        """An inset stair (layout.inset_notch): from the trimmer at the notch's inner face down to the lower level, its bottom
        riser flush with the step skirt; treads and risers between the cheek skirts; stringers hung on the trimmer, bearing on
        the foot carrier between the two notch posts; the graspable handrail on the guard posts along one cheek."""
        nt, g = st.notch, st.geo
        ax, face, sgn = nt["axis"], nt["face"], nt["sgn"]
        r_, run_, R, T = g.riser_in, g.tread_in, g.risers, g.treads
        r_t, s_t, bt_in, jd_in = nt["riser_t"], nt["skirt_t"], bt / IN, jd / IN
        va, vb = nt["lo"] + s_t + 0.125, nt["hi"] - s_t - 0.125
        rs = 1.0 if nt["direction"] in ("-x", "+y") else -1.0            # the stringer / rail pitch, as the flights draw it
        r_ax = "y" if ax == "x" else "x"
        def bx(kind, u0_, u1_, v0_, v1_, z0_, z1_, mat, phase, tag="", rot=0.0, tone_=0.0):
            """Stair-local inches (u from the inner face toward the outer face, v across, z from the deck surface) -> a box."""
            a0, a1 = sorted((face - sgn * u0_, face - sgn * u1_))
            x0_, x1_, y0_, y1_ = (a0, a1, v0_, v1_) if ax == "x" else (v0_, v1_, a0, a1)
            add(kind, x0_ * IN, x1_ * IN, y0_ * IN, y1_ * IN, zt + z0_ * IN, zt + z1_ * IN, mat, phase, tag=tag, rot=rs * rot, rot_axis=r_ax, tone=tone_)
        for k in range(1, R + 1):
            bx("riser", (k - 1) * run_, (k - 1) * run_ + r_t, va, vb, -k * r_, -(k - 1) * r_ - bt_in, "fascia", 6, tag=f"riser {k} {st.side}", tone_=tone())
            if k <= T:
                bx("tread", (k - 1) * run_ + r_t, k * run_ + r_t + NOSE, va, vb, -k * r_ - bt_in, -k * r_, "deck", 6, tag=f"tread {k} {st.side}", tone_=tone())
        # stringers: their top edge under the back of every tread, hung on the trimmer, the heels cut level onto the base ledger
        th = math.atan2(r_, run_)
        dep = 11.25
        l_top = nt["ledger_top"]
        z_edge = lambda u: -r_ - bt_in - 0.25 - (u - r_t) * math.tan(th)
        u_end = min(T * run_, r_t + (-r_ - bt_in - 0.25 - (l_top - 5.5) - dep / math.cos(th)) / math.tan(th))
        Ls, uc = u_end / math.cos(th), u_end / 2
        zc = z_edge(uc) - (dep / 2) / math.cos(th)
        n_s = max(2, st.stringers)
        for i in range(n_s):
            v = va + 0.75 + (vb - va - 1.5) * i / (n_s - 1)
            bx("stringer", uc - Ls / 2, uc + Ls / 2, v - 0.75, v + 0.75, zc - dep / 2, zc + dep / 2, "timber", 5, tag=f"stringer {st.side}", rot=th)
        # the stair base ledger (2-ply PT 2x6 bolted to the lower level's rim face, top flush with it) and the two short PT posts
        # on it under the header / rim corners (structure.md §5.2)
        u_f = nt["depth"]                                                # the face the notch is cut in
        bx("beam", u_f - 3.0, u_f, nt["ledger_lo"], nt["ledger_hi"], l_top - 5.5, l_top, "timber", 4, tag=f"stair base ledger {st.side}")
        pbn, pdn = [v_ * IN for v_ in actual(nt["post_size"])]
        for px, py in nt["posts"]:
            x, y = px * IN, py * IN
            hx, hy = (pbn / 2, pdn / 2) if ax == "x" else (pdn / 2, pbn / 2)
            add("post", x - hx, x + hx, y - hy, y + hy, zt + l_top * IN, jbot, "timber", 2, tag=f"stair notch post {st.side}")
        # the graspable handrail: 34-38" over the nosing line (36"), from above the top riser to above the bottom riser, on
        # brackets off the guard posts along the cheek on its side going down
        if getattr(st, "handrail", "") == "guard posts" and L.rail:
            lo_side = (nt["direction"] in ("-x", "+y")) == ((getattr(st, "handrail_side", "right") or "right") == "right")
            cheek = nt["lo"] if lo_side else nt["hi"]
            sgn_c = 1.0 if lo_side else -1.0                               # into the notch from that cheek
            v_h = cheek + sgn_c * (s_t + 1.75)
            z_n = lambda u: -r_ * (u - r_t - NOSE) / run_
            u_t, u_b = 0.0, T * run_ + r_t
            Lh = math.hypot(u_b - u_t, z_n(u_t) - z_n(u_b))
            um = (u_t + u_b) / 2
            bx("toprail", um - Lh / 2, um + Lh / 2, v_h - 0.75, v_h + 0.75, z_n(um) + 34.5, z_n(um) + 36.0, "railmetal", 7, tag="graspable handrail", rot=th)
            pw_in = rail_system_for(spec.railing)["post_w"]
            line_c = cheek - sgn_c * _RP                                    # the cheek guard's post line, on the deck
            for q in L.rail.posts:
                al, ac = (q.x, q.y) if ax == "x" else (q.y, q.x)
                u_p = sgn * (face - al)
                if abs(ac - line_c) < 1.0 and -1.0 <= u_p <= nt["depth"] + 1.0:
                    v0_, v1_ = sorted((ac + sgn_c * pw_in / 2, v_h))
                    zb_ = z_n(min(max(u_p, u_t), u_b)) + 33.5
                    bx("toprail", u_p - 0.75, u_p + 0.75, v0_, v1_, zb_, zb_ + 1.0, "railmetal", 7, tag="handrail bracket")

    # ---------------- stairs: one or more flights (stringers as rotated boxes, treads, closed risers, stair rail), landings, pad
    house_rects = [tuple(float(v) for v in h[:4]) for h in (spec.geometry.house_blocks or [])]
    def in_house(px, py):
        return any(hx0 <= px <= hx1 and hy0 <= py <= hy1 for hx0, hx1, hy0, hy1 in house_rects)
    for st, ss in zip(L.stairs, spec.stairs):
        _n0 = len(B)                       # this stair's first box: an option stair's boxes carry the option's layer
        if getattr(st, "inset", False) and st.notch:
            draw_inset_stair(st)
            for b_ in (B[_n0:] if getattr(st, "option", "") else []):
                b_.layer = f"option:{st.option}"
            continue
        g = st.geo
        rise, run, width = g.riser_in * IN, g.tread_in * IN, st.width * IN
        side = st.side
        if side in ("right", "end:right"):
            zz = L.zones[-1]; direction = "+x"; u0 = (zz.x0 + zz.W) * IN; v_a = zz.wall_y * IN + st.opening.start_in * IN
        elif side in ("left", "end:left"):
            zz = L.zones[0]; direction = "-x"; u0 = zz.x0 * IN; v_a = zz.wall_y * IN + st.opening.start_in * IN
        elif side.startswith("step:"):
            # the step between two zone fronts: the stair leaves the deeper zone's side edge and runs alongside the shallower zone
            na, nb = side.split(":")[1].split("-")
            za = next(q for q in L.zones if q.name == na); zb = next(q for q in L.zones if q.name == nb)
            u0 = (za.x0 + za.W) * IN
            if zb.D > za.D:
                direction = "-x"; v_a = (za.wall_y + za.D) * IN + edge + st.opening.start_in * IN
            else:
                direction = "+x"; v_a = (zb.wall_y + zb.D) * IN + edge + st.opening.start_in * IN
        elif side.startswith("edge:"):
            # a side of the outline polygon (axis-aligned): the stair leaves it outward, the opening measured from the side's start
            e_ = next(q for q in L.outline_edges if q.name == side)
            if abs(e_.y1 - e_.y0) < 0.5:
                direction = "+y" if e_.x1 > e_.x0 else "-y"
                u0 = e_.y0 * IN + (edge if direction == "+y" else -edge)
                v_a = (min(e_.x0, e_.x1) + (st.opening.start_in if e_.x1 > e_.x0 else abs(e_.x1 - e_.x0) - st.opening.start_in - st.width)) * IN
            else:
                direction = "-x" if e_.y1 > e_.y0 else "+x"
                u0 = e_.x0 * IN
                v_a = (min(e_.y0, e_.y1) + (st.opening.start_in if e_.y1 > e_.y0 else abs(e_.y1 - e_.y0) - st.opening.start_in - st.width)) * IN
        elif side.startswith("wall:"):
            # a freestanding zone's open rear edge: the stair leaves it away from the deck (-y); the opening is measured from the zone's right end
            zn = side.split(":")[1]
            zz = next((q for q in L.zones if q.name == zn), L.zones[0]); direction = "-y"
            u0 = zz.wall_y * IN - edge; v_a = (zz.x0 + zz.W) * IN - st.opening.start_in * IN - width
        else:
            zn = side.split(":")[1] if ":" in side else None
            zz = next((q for q in L.zones if q.name == zn), L.zones[0]); direction = "+y"
            u0 = (zz.wall_y + zz.D) * IN + edge; v_a = zz.x0 * IN + st.opening.start_in * IN
        v_b = v_a + width
        H_st = g.total_rise_in * IN            # the stair's own drop (to a lower deck or a pad), not the deck height
        z_low = zt - H_st
        depth = 11.25 * IN
        REV = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}

        def sbf(dir_, u0_, kind, ua, ub, va, vb, za, zb, mat, phase, tag="", rot=0.0, tone_=0.0):
            """Stair-local (u along the travel from u0_, v across) -> world."""
            if dir_ == "+x":
                add(kind, u0_ + ua, u0_ + ub, va, vb, za, zb, mat, phase, tag=tag, rot=-rot, rot_axis="y", tone=tone_)
            elif dir_ == "-x":
                add(kind, u0_ - ub, u0_ - ua, va, vb, za, zb, mat, phase, tag=tag, rot=rot, rot_axis="y", tone=tone_)
            elif dir_ == "-y":
                add(kind, va, vb, u0_ - ub, u0_ - ua, za, zb, mat, phase, tag=tag, rot=-rot, rot_axis="x", tone=tone_)
            else:
                add(kind, va, vb, u0_ + ua, u0_ + ub, za, zb, mat, phase, tag=tag, rot=rot, rot_axis="x", tone=tone_)

        def world(dir_, u0_, u):
            return u0_ + u if dir_ in ("+x", "+y") else u0_ - u

        def rect_world(dir_, u0_, ua, ub, va, vb):
            """A stair-local rectangle as a world (x0, x1, y0, y1)."""
            wa, wb = sorted((world(dir_, u0_, ua), world(dir_, u0_, ub)))
            return (wa, wb, va, vb) if dir_ in ("+x", "-x") else (va, vb, wa, wb)

        def draw_flight(fg, z_top, dir_, u0_, va_, vb_, rail_sides, tag_, mid):
            """One flight from the walking surface at z_top down fg.risers risers. rail_sides: subset of ("a", "b")."""
            n_r, n_t = fg.risers, fg.treads
            trun = fg.run_in * IN
            H = fg.rise_in * IN
            zb0 = z_top - H
            theta = math.atan2(rise, run) if run > 0 else 0.0     # the tread pitch: stringers and the stair rail run at rise / run
            sb_ = lambda *a, **k: sbf(dir_, u0_, *a, **k)
            # a cut stringer drawn as its uncut board: top edge under the back of every tread, from the rim down past the last riser to the pad
            u_end = trun + run
            slope_len = u_end / math.cos(theta)
            uc = u_end / 2
            z_top_edge = z_top - rise - bt - 0.02 - math.tan(theta) * uc
            box_ = getattr(st, "build", "stringers") == "box"
            skirt_ = box_ or getattr(st, "skirts", False)
            if box_:
                # a framed 2x6 box under each tread (front + back rims, cross members at 16"), on a compacted base — no stringers
                for k in range(1, n_t + 1):
                    zf1 = z_top - k * rise - bt; zf0 = max(zb0, zf1 - 5.5 * IN)
                    ua, ub = (k - 1) * run, k * run - 0.9 * IN
                    sb_("rim", ua, ua + 1.5 * IN, va_, vb_, zf0, zf1, "timber", 4, tag=f"box step frame {tag_}")
                    sb_("rim", ub - 1.5 * IN, ub, va_, vb_, zf0, zf1, "timber", 4, tag=f"box step frame {tag_}")
                    ncm = int(math.ceil(width / (16 * IN))) + 1
                    for i in range(ncm):
                        v = va_ + 0.75 * IN + (width - 1.5 * IN) * i / (ncm - 1)
                        sb_("joist", ua + 1.5 * IN, ub - 1.5 * IN, v - 0.75 * IN, v + 0.75 * IN, zf0, zf1, "timber", 4, tag=f"box step frame {tag_}")
                sb_("stepbase", 0.0, n_t * run, va_, vb_, zb0 - 0.36, zb0 - 0.04, "gravel", 1, tag=f"box step base {tag_}")
            else:
                nst = max(2, st.stringers) if n_t else 0     # a single riser down onto a landing needs no stringers
                for i in range(nst):
                    v = va_ + 0.75 * IN + (width - 1.5 * IN) * i / (nst - 1)
                    zc = z_top_edge - (depth / 2) / math.cos(theta)
                    sb_("stringer", uc - slope_len / 2, uc + slope_len / 2, v - 0.75 * IN, v + 0.75 * IN, zc - depth / 2, zc + depth / 2, "timber", 5, tag=f"stringer {tag_}", rot=theta)
            ov_ = 0.1 if skirt_ else 0.02            # treads run 1" past the skirt faces
            for k in range(1, n_r + 1):
                ztop = z_top - k * rise
                sb_("riser", (k - 1) * run - 0.9 * IN, (k - 1) * run, va_, vb_, ztop, ztop + rise - 0.02, "fascia", 6, tone_=tone())
                if k <= n_t:
                    sb_("tread", (k - 1) * run, k * run + NOSE * IN, va_ - ov_, vb_ + ov_, ztop - bt, ztop, "deck", 6, tag=f"tread {k} {tag_}", tone_=tone())
            if skirt_:
                # stepped fascia skirts on both sides: under each tread, down to 1/2" off grade (a 12" fascia covers up to 12")
                ft_ = 0.58 * IN
                for k in range(1, n_t + 1):
                    ztop = z_top - k * rise
                    zs0 = max(zb0 + (0.005 if box_ else 0.04), ztop - bt - 11.95 * IN)      # a box step sits on its base; a stair skirt holds 1/2" off grade
                    for v0, v1 in ((va_ - ft_, va_), (vb_, vb_ + ft_)):
                        sb_("fascia", (k - 1) * run - 0.9 * IN, k * run, v0, v1, zs0, ztop - bt, "fascia", 6, tag=f"stair skirt {tag_}", tone_=tone())
            if rail_sides and L.rail:
                sysd = rail_system_for(spec.railing)
                pw = sysd["post_w"] * IN
                hr = L.rail.height * IN
                for sd in rail_sides:
                    vc = va_ + pw / 2 + 0.02 if sd == "a" else vb_ - pw / 2 - 0.02
                    for u_, zb_ in ((0.25, z_top - rise), (trun - 0.25, zb0)):
                        sb_("railpost", u_ - pw / 2, u_ + pw / 2, vc - pw / 2, vc + pw / 2, zb_, zb_ + hr + 0.3, "railmetal", 7, tag="stair post")
                    rail_len = math.hypot(trun - 0.5, H - rise)
                    zc = zb0 + (H - rise) / 2 + hr + 0.1
                    sb_("toprail", trun / 2 - rail_len / 2, trun / 2 + rail_len / 2, vc - 0.06, vc + 0.06, zc - 0.05, zc + 0.05, "railmetal", 7, rot=theta)
                    # no drink rail on a stair: the graspable handrail is the stair's top
                    if RAIL_SYSTEMS.get(L.rail.system, {}).get("cable"):
                        n_c = int((hr - 0.25) / (3.125 * IN))
                        for i in range(1, n_c + 1):
                            zc_ = zb0 + (H - rise) / 2 + i * 3.125 * IN + 0.1
                            sb_("cable", trun / 2 - rail_len / 2, trun / 2 + rail_len / 2, vc - 0.01, vc + 0.01, zc_ - 0.01, zc_ + 0.01, "cable", 7, rot=theta)
                        if rail_len > 6.5:
                            u_ = trun / 2
                            sb_("railpost", u_ - pw / 2, u_ + pw / 2, vc - pw / 2, vc + pw / 2, zb0 + (H - rise) / 2, zb0 + (H - rise) / 2 + hr + 0.3, "railmetal", 7, tag="stair post")
                    else:
                        for k in range(1, n_t + 1):
                            for frac in (0.3, 0.7):
                                u_ = (k - 1) * run + frac * run
                                ztop = z_top - k * rise
                                sb_("baluster", u_ - 0.03, u_ + 0.03, vc - 0.03, vc + 0.03, ztop, ztop + hr - 0.02, "railmetal", 7)
            for frac in (st.carrier_fracs or [0.5]) if mid else []:
                # carriers: (2)2x6 under the stringers on two posts and footings — no stringer span over 6'
                um = trun * frac
                z_under = z_top - rise - bt - math.tan(theta) * um - depth / math.cos(theta)
                zc_top = z_under - 0.02
                sb_("beam", um - 1.5 * IN, um + 1.5 * IN, va_ - 0.25, vb_ + 0.25, zc_top - 5.5 * IN, zc_top, "timber", 4, tag=f"stair carrier {st.side}")
                for vp in (va_ + 0.25, vb_ - 0.25):
                    sb_("post", um - pb_ / 2, um + pb_ / 2, vp - pb_ / 2, vp + pb_ / 2, 0.55, zc_top - 5.5 * IN, "timber", 2, tag="stair carrier post")
                    sb_("base", um - pb_ / 2 - 0.02, um + pb_ / 2 + 0.02, vp - pb_ / 2 - 0.02, vp + pb_ / 2 + 0.02, 0.45, 0.57, "steel", 2)
                    sb_("footing", um - 0.55, um + 0.55, vp - 0.55, vp + 0.55, -0.1, 0.45, "concrete", 1, tag="stair footing")
            return zb0, trun

        def draw_landing(rw, z_top, li):
            """A framed, decked landing platform on four posts: rw = world (x0, x1, y0, y1)."""
            x0_, x1_, y0_, y1_ = rw
            # decked in the field board, boards across the landing (parallel with the treads of the flight it serves)
            along_x = direction in ("+y", "-y")
            span = (y1_ - y0_) if along_x else (x1_ - x0_)
            nb_ = max(1, int(round(span / (bw + gap))))
            for i in range(nb_):
                a0 = i * span / nb_; a1 = a0 + span / nb_ - gap
                if along_x:
                    add("board", x0_, x1_, y0_ + a0, y0_ + a1, z_top - bt, z_top, "deck", 6, tag=f"landing {li} {st.side}", tone=tone())
                else:
                    add("board", x0_ + a0, x0_ + a1, y0_, y1_, z_top - bt, z_top, "deck", 6, tag=f"landing {li} {st.side}", tone=tone())
            for (xa_, xb_, ya_, yb_) in ((x0_, x1_, y0_, y0_ + 1.5 * IN), (x0_, x1_, y1_ - 1.5 * IN, y1_), (x0_, x0_ + 1.5 * IN, y0_, y1_), (x1_ - 1.5 * IN, x1_, y0_, y1_)):
                add("rim", xa_, xb_, ya_, yb_, z_top - bt - jd, z_top - bt, "timber", 4, tag=f"landing {li} rim")
            add("fascia", x0_ - fas_t, x1_ + fas_t, y0_ - fas_t, y0_, z_top - bt - jd, z_top, "fascia", 6, tone=tone())
            add("fascia", x0_ - fas_t, x1_ + fas_t, y1_, y1_ + fas_t, z_top - bt - jd, z_top, "fascia", 6, tone=tone())
            add("fascia", x0_ - fas_t, x0_, y0_, y1_, z_top - bt - jd, z_top, "fascia", 6, tone=tone())
            add("fascia", x1_, x1_ + fas_t, y0_, y1_, z_top - bt - jd, z_top, "fascia", 6, tone=tone())
            nj = max(2, int((x1_ - x0_) / (spec.joist_spacing * IN)))
            for j in range(1, nj):
                xj = x0_ + (x1_ - x0_) * j / nj
                add("joist", xj - 0.75 * IN, xj + 0.75 * IN, y0_ + 1.5 * IN, y1_ - 1.5 * IN, z_top - bt - jd, z_top - bt, "timber", 4, tag=f"landing {li} joist")
            ins = max(0.5, pb_ / 2 + 0.1)
            for px in (x0_ + ins, x1_ - ins):
                for py in (y0_ + ins, y1_ - ins):
                    add("post", px - pb_ / 2, px + pb_ / 2, py - pb_ / 2, py + pb_ / 2, 0.55, z_top - bt - jd, "timber", 2, tag=f"landing {li} post")
                    add("base", px - pb_ / 2 - 0.02, px + pb_ / 2 + 0.02, py - pb_ / 2 - 0.02, py + pb_ / 2 + 0.02, 0.45, 0.57, "steel", 2)
                    add("footing", px - 0.55, px + 0.55, py - 0.55, py + 0.55, -0.1, 0.45, "concrete", 1, tag="landing footing")

        def landing_guard(rects, z_top, openings):
            """Level guard on the landings' open sides: the union outline of the landing rectangles less the house side and the flight openings.
            openings: world rectangles (x0, x1, y0, y1) where a flight arrives or leaves — an outline segment inside one is left open."""
            if not L.rail:
                return
            sysd = rail_system_for(spec.railing)
            pw = sysd["post_w"] * IN
            hr = L.rail.height * IN
            xs = sorted({v for r in rects for v in (r[0], r[1])}); ys = sorted({v for r in rects for v in (r[2], r[3])})
            inside = lambda px, py: any(r[0] - 1e-6 <= px <= r[1] + 1e-6 and r[2] - 1e-6 <= py <= r[3] + 1e-6 for r in rects)
            raw = {}      # (axis, line, normal) -> list of intervals along the segment
            for i in range(len(xs) - 1):
                for j in range(len(ys) - 1):
                    xa_, xb_, ya_, yb_ = xs[i], xs[i + 1], ys[j], ys[j + 1]
                    if not inside((xa_ + xb_) / 2, (ya_ + yb_) / 2):
                        continue
                    for (axis, line, a0, a1, nx, ny) in (("x", ya_, xa_, xb_, 0, -1), ("x", yb_, xa_, xb_, 0, 1), ("y", xa_, ya_, yb_, -1, 0), ("y", xb_, ya_, yb_, 1, 0)):
                        mx, my = ((a0 + a1) / 2, line) if axis == "x" else (line, (a0 + a1) / 2)
                        ox, oy = mx + nx * 0.1, my + ny * 0.1
                        if inside(ox, oy) or in_house(ox, oy):
                            continue
                        raw.setdefault((axis, round(line, 4), nx, ny), []).append([a0, a1])
            segs = []
            for (axis, line, nx, ny), ivs in raw.items():
                ivs.sort()
                merged = []
                for a0, a1 in ivs:
                    if merged and a0 <= merged[-1][1] + 1e-6:
                        merged[-1][1] = max(merged[-1][1], a1)
                    else:
                        merged.append([a0, a1])
                # cut the flight openings out of each run
                for a0, a1 in merged:
                    parts = [[a0, a1]]
                    for o in openings:
                        lo, hi = (o[0], o[1]) if axis == "x" else (o[2], o[3])
                        perp = (o[2] - 0.05 <= line <= o[3] + 0.05) if axis == "x" else (o[0] - 0.05 <= line <= o[1] + 0.05)
                        if not perp:
                            continue
                        nxt = []
                        for p0, p1 in parts:
                            if hi <= p0 or lo >= p1:
                                nxt.append([p0, p1]); continue
                            if lo > p0:
                                nxt.append([p0, lo])
                            if hi < p1:
                                nxt.append([hi, p1])
                        parts = nxt
                    for p0, p1 in parts:
                        if p1 - p0 > 0.5:
                            segs.append((axis, line, p0, p1, nx, ny))
            for (axis, line, p0, p1, nx, ny) in segs:
                # posts at both ends inset half a post, a top rail, a baluster every 4"
                c_line = line - nx * (pw / 2 + 0.02) if axis == "y" else line - ny * (pw / 2 + 0.02)
                e0, e1 = p0 + pw / 2, p1 - pw / 2
                for e in (e0, e1):
                    cx, cy = (e, c_line) if axis == "x" else (c_line, e)
                    add("railpost", cx - pw / 2, cx + pw / 2, cy - pw / 2, cy + pw / 2, z_top, z_top + hr + 0.3, "railmetal", 7, tag="landing post")
                if axis == "x":
                    add("toprail", e0, e1, c_line - 0.06, c_line + 0.06, z_top + hr, z_top + hr + 0.1, "railmetal", 7, tag="landing rail")
                else:
                    add("toprail", c_line - 0.06, c_line + 0.06, e0, e1, z_top + hr, z_top + hr + 0.1, "railmetal", 7, tag="landing rail")
                n_b = max(1, int((e1 - e0) / (4 * IN)))
                for i in range(1, n_b):
                    e = e0 + (e1 - e0) * i / n_b
                    cx, cy = (e, c_line) if axis == "x" else (c_line, e)
                    add("baluster", cx - 0.03, cx + 0.03, cy - 0.03, cy + 0.03, z_top + 0.02, z_top + hr - 0.02, "railmetal", 7)

        flights = g.flights
        frails = list(st.flight_rails) + [st.stair_rail_sides] * (len(flights) - len(st.flight_rails))
        LEFT = {"-y": "-x", "+y": "+x", "+x": "-y", "-x": "+y"}     # facing down the flight, the left hand
        RIGHT = {v: k for k, v in LEFT.items()}
        turn = ss.turn or "switchback"
        side_dir = (RIGHT if (ss.turn_side or "left") == "right" else LEFT)[direction] if turn in ("switchback", "straight") else (LEFT if turn == "left" else RIGHT)[direction]
        turn_left = side_dir in ("-x", "-y")          # the landing extends toward the low-v side of the flight
        multi = len(flights) > 1
        # flight 1 from the deck
        def sides_for(n_sides, fi):
            if n_sides >= 2:
                return ("a", "b")
            if n_sides == 1:
                if multi:
                    return ("a",) if turn_left else ("b",)      # the open side is the turn side; the other side is the house or the first flight
                return ("b",)
            return ()
        cur_dir, cur_u0, cur_va, cur_vb, z_cur = direction, u0, v_a, v_b, zt
        openings = []
        land_rects = []
        z_land = None
        for fi, fg in enumerate(flights):
            mid = st.mid_support and fg.run_in >= max(f_.run_in for f_ in flights) - 1e-6
            z_next, trun = draw_flight(fg, z_cur, cur_dir, cur_u0, cur_va, cur_vb, sides_for(frails[fi], fi), f"{st.side}" + (f" flight {fi + 1}" if multi else ""), mid)
            if fi == len(flights) - 1:
                # the bottom: a lower deck or a pad in the last flight's frame
                if st.landing == "deck":
                    if not getattr(st, "lands_on", ""):     # on another part of a composite its own boards are there (a patch would z-fight)
                        sbf(cur_dir, cur_u0, "board", trun - 0.4, trun + 4.0, cur_va - 0.5, cur_vb + 0.5, z_next - bt, z_next, "deck", 6, tag=f"lower deck at the {st.side} stair")
                elif st.landing != "grade":       # a new or existing pad; "grade" lands on the ground
                    sbf(cur_dir, cur_u0, "footing", trun - 0.4, trun + 3.6, cur_va - 0.5, cur_vb + 0.5, z_next - 0.3, z_next + 0.02, "concrete", 1, tag=f"landing pad {st.side}")
                break
            # a landing at the foot of this flight
            lands = [(float(a) * IN, float(b) * IN) for a, b in (ss.landings or [])] or [(width, 3.0)]
            lw, ld = lands[0] if fi == 0 else lands[min(fi, len(lands) - 1)]
            openings.append(rect_world(cur_dir, cur_u0, trun - 0.3, trun + 0.3, cur_va, cur_vb))
            if turn_left:
                sq_va, sq_vb = cur_vb - lw, cur_vb
            else:
                sq_va, sq_vb = cur_va, cur_va + lw
            r1 = rect_world(cur_dir, cur_u0, trun, trun + ld, sq_va, sq_vb)
            rects = [r1]
            draw_landing(r1, z_next, len(land_rects) + 1)
            if turn in ("switchback", "left", "right"):
                # the big landing beside the turn square on the turn side; flight 2 leaves it: back alongside flight 1 (switchback)
                # or straight out of its outer edge (a 90° turn)
                if fi == 0 and len(lands) > 1:
                    lw2, ld2 = lands[1]
                    if turn_left:
                        l_va, l_vb = sq_va - lw2, sq_va
                    else:
                        l_va, l_vb = sq_vb, sq_vb + lw2
                    r2 = rect_world(cur_dir, cur_u0, trun, trun + ld2, l_va, l_vb)
                    draw_landing(r2, z_next, len(land_rects) + 2)
                    rects.append(r2)
                else:
                    l_va, l_vb = sq_va, sq_vb
                if turn == "switchback":
                    n_va, n_vb = (l_va, l_va + width) if turn_left else (l_vb - width, l_vb)
                    openings.append(rect_world(cur_dir, cur_u0, trun - 0.3, trun + 0.3, n_va, n_vb))
                    cur_u0 = world(cur_dir, cur_u0, trun)
                    cur_dir = REV[cur_dir]
                    cur_va, cur_vb = n_va, n_vb
                else:
                    # 90°: flight 2 leaves the outer edge of the landing, its width along the landing from the deck-side line
                    l_edge = l_va if turn_left else l_vb
                    openings.append(rect_world(cur_dir, cur_u0, trun, trun + width, l_edge - 0.3, l_edge + 0.3))
                    n_va, n_vb = sorted((world(cur_dir, cur_u0, trun), world(cur_dir, cur_u0, trun + width)))
                    cur_u0 = l_edge
                    cur_dir = side_dir
                    cur_va, cur_vb = n_va, n_vb
            else:
                # straight through: the next flight leaves the far edge of the landing
                openings.append(rect_world(cur_dir, cur_u0, trun + ld - 0.3, trun + ld + 0.3, cur_va, cur_vb))
                cur_u0 = world(cur_dir, cur_u0, trun + ld)
            land_rects += rects
            z_land = z_next
            if st.landing_rail_lf and (frails[fi] or (fi + 1 < len(frails) and frails[fi + 1])):
                landing_guard(rects, z_next, openings)
            z_cur = z_next
        if getattr(st, "option", ""):
            # an option stair: every box it drew carries layer "option:<name>"; the deck guard it opens is drawn across the
            # opening too, as layer "base:<name>" — a viewer shows one or the other
            for b_ in B[_n0:]:
                b_.layer = f"option:{st.option}"
            if L.rail:
                sysd_ = rail_system_for(spec.railing)
                prof_ = sysd_.get("profile") or {}
                trw_, trh_ = prof_.get("top", (0.12, 0.08))
                brw_, brh_ = prof_.get("bottom", (0.12, 0.08))
                bal_, bal_oc_ = prof_.get("baluster", 0.06), prof_.get("baluster_oc_in", 4.0) * IN
                h_, RPf = L.rail.height * IN, _RP * IN
                horiz_ = direction in ("+y", "-y")
                frame_ = u0 - edge if direction == "+y" else (u0 + edge if direction == "-y" else u0)
                line_ = frame_ + (-RPf if direction in ("+y", "+x") else RPf)
                ea_, eb_ = v_a - RPf, v_b + RPf
                pts_ = [((q.x, q.y) if horiz_ else (q.y, q.x)) for q in L.rail.posts]
                if any(abs(al * IN - e_) < 0.3 and abs(ac * IN - line_) < 0.3 for al, ac in pts_ for e_ in (ea_, eb_)):
                    n1_ = len(B)
                    def _run(kind, w_, z0_, z1_, mat_, tag_="", tone_=0.0):
                        if horiz_:
                            add(kind, ea_, eb_, line_ - w_ / 2, line_ + w_ / 2, z0_, z1_, mat_, 7, tag=tag_, tone=tone_)
                        else:
                            add(kind, line_ - w_ / 2, line_ + w_ / 2, ea_, eb_, z0_, z1_, mat_, 7, tag=tag_, tone=tone_)
                    _run("toprail", trw_, zt + h_ - trh_, zt + h_, "railmetal", f"guard across the {st.side} stair opening (without the option)")
                    _run("botrail", brw_, zt + 0.25, zt + 0.25 + brh_, "railmetal")
                    nb_ = int((eb_ - ea_) / bal_oc_)
                    for k_ in range(1, nb_):
                        t_ = ea_ + (eb_ - ea_) * k_ / nb_
                        bx_ = (t_ - bal_ / 2, t_ + bal_ / 2, line_ - bal_ / 2, line_ + bal_ / 2) if horiz_ else (line_ - bal_ / 2, line_ + bal_ / 2, t_ - bal_ / 2, t_ + bal_ / 2)
                        add("baluster", *bx_, zt + 0.25 + brh_, zt + h_ - trh_, "railmetal", 7)
                    if spec.railing.drink_rail:
                        _run("drink", bw, zt + h_ + 0.06, zt + h_ + 0.06 + bt, "drink", tone_=tone())
                    for b_ in B[n1_:]:
                        b_.layer = f"base:{st.option}"

    # ---------------- an existing stucco parapet on the open edges (stays; nothing in the takeoff)
    if spec.railing.existing_parapet:
        psides = set(spec.railing.parapet_sides or [])
        if psides:
            segs_ = [(e.x0 * IN, e.y0 * IN, e.x1 * IN, e.y1 * IN) for e in L.edges if e.exposed and e.name in psides]
        else:
            runs_ = front_runs(L)
            segs_ = [(a, y, b, y) for a, b, y in runs_] + [(e.x0 * IN, e.y0 * IN, e.x1 * IN, e.y1 * IN) for e in L.edges if e.exposed and abs(e.y1 - e.y0) > 0.05]
        for ex0, ey0, ex1, ey1 in segs_:
            L_ = ((ex1 - ex0) ** 2 + (ey1 - ey0) ** 2) ** 0.5
            if L_ < 0.1:
                continue
            curve = outline_path(spec, (ex0, ey0), (ex1, ey1), ends=True) if abs(ey1 - ey0) < 0.05 else []
            if curve and any(abs(py - ey0) > 0.05 for px, py in curve):
                pts_ = curve
                for (p0, q0), (p1, q1) in zip(pts_, pts_[1:]):
                    seg = math.hypot(p1 - p0, q1 - q0); ph_ = math.atan2(q1 - q0, p1 - p0)
                    nx_, ny_ = math.sin(ph_), -math.cos(ph_)
                    B.append(Box("privacy", (p0 + p1) / 2 - seg / 2, (p0 + p1) / 2 + seg / 2, (q0 + q1) / 2 + ny_ * 0.33 - 0.33, (q0 + q1) / 2 + ny_ * 0.33 + 0.33, zt - 0.3, zt + 3.5, "house", 8, tag="existing stucco parapet (stays)", rot=ph_, rot_axis="z"))
                    B.append(Box("trim", (p0 + p1) / 2 - seg / 2, (p0 + p1) / 2 + seg / 2, (q0 + q1) / 2 + ny_ * 0.33 - 0.38, (q0 + q1) / 2 + ny_ * 0.33 + 0.38, zt + 3.5, zt + 3.62, "stonecap", 8, tag="parapet cap", rot=ph_, rot_axis="z"))
                continue
            ux, uy = (ex1 - ex0) / L_, (ey1 - ey0) / L_
            nx, ny = uy, -ux      # inward normal (clockwise outline)
            th = 0.67             # 8" stucco wall
            cx0, cy0 = ex0 + nx * th / 2, ey0 + ny * th / 2
            cx1, cy1 = ex1 + nx * th / 2, ey1 + ny * th / 2
            xa, xb = min(cx0, cx1) - (th / 2 if abs(ux) < 0.01 else 0), max(cx0, cx1) + (th / 2 if abs(ux) < 0.01 else 0)
            ya, yb = min(cy0, cy1) - (th / 2 if abs(uy) < 0.01 else 0), max(cy0, cy1) + (th / 2 if abs(uy) < 0.01 else 0)
            add("privacy", xa, xb, ya, yb, zt - 0.3, zt + 3.5, "house", 8, tag="existing stucco parapet (stays)")
            add("trim", xa - 0.05, xb + 0.05, ya - 0.05, yb + 0.05, zt + 3.5, zt + 3.62, "stonecap", 8, tag="parapet cap")

    # ---------------- furnishings: hot tub in its zone against the wall
    if spec.extras.hot_tub:
        zn = spec.extras.hot_tub_zone
        z = next((q for q in L.zones if q.name == zn), L.zones[0])
        bay = spec.extras.hot_tub_bay_in * IN
        x0 = z.x0 * IN + (z.W * IN - bay) / 2
        y0 = z.wall_y * IN + 1.0
        add("tub", x0, x0 + bay, y0, y0 + bay, zt, zt + 2.7, "tub", 8, tag="hot tub (by owner)")
        add("tubrim", x0 - 0.05, x0 + bay + 0.05, y0 - 0.05, y0 + bay + 0.05, zt + 2.7, zt + 3.0, "tubrim", 8)
        add("water", x0 + 0.5, x0 + bay - 0.5, y0 + 0.5, y0 + bay - 0.5, zt + 2.75, zt + 2.82, "water", 8)

    if spec.geometry.outline:
        fixed = apply_outline(fixed, spec, zt, jbot, jtop, jb, bt, fas_t if fascia else 0.0, add_rims=OF is None)
    if spec.geometry.house_walls and not getattr(spec.geometry, "house_model", None):     # with a measured house model these only classify the deck's edges
        for wseg in spec.geometry.house_walls:
            fixed.append(angled_wall(*wseg, z0=0.0, z1=H_house))
    fixed += __import__("decktakeoff.lighting", fromlist=["scene_lights"]).scene_lights(fixed, spec)    # extras.lights: a light on every riser + rail-post box (a composite gets them per part)
    meta = dict(job=spec.job, address=f"{spec.site.address}, {spec.site.city}".strip(", "), sf=L.deck_sf, height=spec.geometry.height_in,
                zones=[dict(name=z.name, label=z.label, x0=z.x0 * IN, W=z.W * IN, wall_y=z.wall_y * IN, D=z.D * IN, front=(z.wall_y + z.D) * IN, ledger=bool(z.frame.ledger)) for z in L.zones],
                edge=edge, timber=timber, oiled=spec.framing.finish == "oil",
                outline=[list(p) for p in spec.geometry.outline] if spec.geometry.outline else None,
                step_text=step_captions(L))
    if sun_vector(spec.site):
        meta["sun"] = list(sun_vector(spec.site))
    if getattr(spec.geometry, "site_model", None) and spec.geometry.site_model.get("cameras"):
        meta["cameras"] = spec.geometry.site_model["cameras"]       # measured-site camera stations (inside the lot), plan feet
    if getattr(spec.geometry, "louvered_roofs", None):              # blades / screens a live viewer can turn and run (louvered.descriptors)
        meta["louvered_roofs"] = __import__("decktakeoff.louvered", fromlist=["descriptors"]).descriptors(L)
    return Scene(fixed, zt, W, y_min, y_front, materials_for(spec), meta)


def _rail_pairs(rl) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Post pairs that carry a section, per run. A run's posts are tagged 'side N'; the corner post shared with the
    neighbouring run lives in that run's list, so every collinear CORNER post is added back before pairing, and a gap
    between two posts is a section only when its length matches one of the run's sections (an opening otherwise)."""
    if rl.sections and all(getattr(sec, "p0", None) is not None for sec in rl.sections if sec.kind == "level"):
        # the layout recorded the two posts of every section: draw exactly those
        return [((sec.p0[0] * IN, sec.p0[1] * IN), (sec.p1[0] * IN, sec.p1[1] * IN)) for sec in rl.sections if sec.kind == "level"]
    runs: Dict[str, List[Tuple[float, float, str]]] = {}
    for p in rl.posts:
        run, _, _ = p.tag.rpartition(" ")
        runs.setdefault(run, []).append((p.x * IN, p.y * IN, p.kind))
    corners = [(p.x * IN, p.y * IN) for p in rl.posts if p.kind == "CORNER"]
    pairs = []
    for run, pts in runs.items():
        horiz = len(pts) < 2 or all(abs(q[1] - pts[0][1]) < 0.02 for q in pts)
        vert = len(pts) < 2 or all(abs(q[0] - pts[0][0]) < 0.02 for q in pts)
        if len(pts) < 2:   # a lone post: decide the axis from the corner that shares a coordinate with it
            horiz = any(abs(c[1] - pts[0][1]) < 0.02 and abs(c[0] - pts[0][0]) > 0.02 for c in corners)
            vert = not horiz
        # the run's direction (an angled outline side runs neither along x nor y)
        if horiz:
            ux, uy = 1.0, 0.0
        elif vert:
            ux, uy = 0.0, 1.0
        else:
            ax_, ay_ = min(pts)[:2]; bx_, by_ = max(pts)[:2]
            ln_ = math.hypot(bx_ - ax_, by_ - ay_); ux, uy = (bx_ - ax_) / ln_, (by_ - ay_) / ln_
        ox, oy = pts[0][0], pts[0][1]
        pts2 = list(pts)
        for c in corners:
            if abs((c[0] - ox) * uy - (c[1] - oy) * ux) < 0.02:
                if not any(abs(c[0] - q[0]) < 0.02 and abs(c[1] - q[1]) < 0.02 for q in pts2):
                    pts2.append((c[0], c[1], "CORNER"))
        pts2.sort(key=lambda q: (q[0] - ox) * ux + (q[1] - oy) * uy)
        ctcs = [sec.ctc for sec in rl.sections if sec.side == run]
        for a, b in zip(pts2, pts2[1:]):
            d = math.hypot(b[0] - a[0], b[1] - a[1]) * 12
            hit = next((i for i, c in enumerate(ctcs) if abs(c - d) < 1.5), None)
            if hit is None and ctcs:
                continue            # an opening (concrete step, stair) — no panel
            if hit is not None:
                ctcs.pop(hit)
            pairs.append(((a[0], a[1]), (b[0], b[1])))
    # a run with sections but no posts of its own (a short front spanned corner to corner): pair its corners
    for side in {sec.side for sec in rl.sections} - set(runs):
        ctcs = [sec.ctc for sec in rl.sections if sec.side == side]
        for i, a in enumerate(corners):
            for b in corners[i + 1:]:
                horiz = abs(a[1] - b[1]) < 0.02
                d = (abs(b[0] - a[0]) if horiz else abs(b[1] - a[1])) * 12
                if (horiz or abs(a[0] - b[0]) < 0.02) and any(abs(c - d) < 1.5 for c in ctcs):
                    pairs.append((a, b) if (a[0], a[1]) <= (b[0], b[1]) else (b, a))
                    ctcs.remove(next(c for c in ctcs if abs(c - d) < 1.5))
    return pairs


def step_captions(L: Layout) -> Dict[int, str]:
    s = L.spec
    n_posts = L.n_footings
    ft = {"caisson": f"{n_posts} caissons {int(L.frame.footing_dia_in)}\" x {L.frame.footing_depth_in / 12:.1f}' below frost",
          "diamond_pier": f"{n_posts} Diamond Pier {L.frame.footing_model} driven-pin footings",
          "concrete": f"{n_posts} concrete piers {int(L.frame.footing_dia_in)}\" x {L.frame.footing_depth_in / 12:.1f}'",
          "existing": f"{n_posts} existing caissons stay" + (" with the existing columns" if s.framing.existing_posts else ", new standoff bases")}[s.framing.footing_type]
    beams = " · ".join(f"{bl.label} ({bl.n_posts} posts)" for bl in L.beam_lines)
    out = {1: f"Step 1 · Footings — {ft}",
           2: ((("Step 2 · Posts — 6x6 " + post_words(s) + " deck posts on " + post_base_sku(s) + " bases, steel saddles to the beams" if s.framing.steel_deck_post == "wood" else "Step 2 · Posts — 3x3 galvanized steel stubs on pier-head brackets")
                + ("; 6x6 " + post_words(s) + " cover posts carry the deck beams where they line up" if any(c.get("footing") == "deck_pier" for c in covers_of(s)) else ""))
               if s.framing.system == "steel" else f"Step 2 · Posts — {s.framing.post_size} {'Douglas fir #1' if (s.is_timber or s.framing.post_species.upper().startswith('DF')) else '#2 GC'} on {'black' if s.framing.hardware_finish == 'black' else 'ZMAX'} bases"),
           3: "Step 3 · Stone column bases — 2'x2' x 3' ledgestone with 24\" caps" if s.extras.stone_bases else "Step 3 · (no stone bases)",
           4: f"Step 4 · Beams — {beams}" if beams else "Step 4 · (no beams — the doubled rims on the edge posts carry the joists)" if getattr(L, "edge_posts", None) else "Step 4 · (no beams)",
           5: (f"Step 5 · Frame — CEMCO {__import__('decktakeoff.steel', fromlist=['names']).names(s)['joist']} C-joists at {L.frame.spacing:g}\" OC, {s.framing.steel_track} track rims, ledger track on a steel angle, clip angles, all G90" if s.framing.system == "steel" else
               f"Step 5 · Frame — {s.framing.joist_size} joists at {L.frame.spacing:g}\", rims, ledger" + (", blocking over the beam" if (L.frame.blocking_rows_y and L.beam_lines) else "")),
           6: f"Step 6 · Decking — {s.decking.brand} {s.decking.collection} {s.decking.color}" + (f", {s.decking.border_color} border" if s.decking.border_color else "") + (", hidden fasteners" if (s.decking.fastener_system or '') != 'Cap-Tor xd face screw' else ""),
           7: (f"Step 7 · Rail — {L.rail.system} {L.rail.height:g}\" {L.rail.color}" + (", drink rail on top" if s.railing.drink_rail else "")) if L.rail else ("Step 7 · Rail — existing stucco parapet stays" if s.railing.existing_parapet else "Step 7 · (no rail)"),
           8: ("Step 8 · Roof covers — 6x6 Douglas fir posts, " + covers_of(s)[0].get("beam", "(2)2x10") + " beam, 2x8 rafters, OSB, underlayment, standing seam, Hardie soffit / fascia / rakes"
               if covers_of(s) and s.extras.cover_post_species.upper().startswith("DF") else "Step 8 · Your room" + (" — hot tub" if s.extras.hot_tub else ""))}
    return out


# ================================================================== composite decks
SITE_KINDS = {"house", "wall", "roof", "trim", "glass", "ground", "gravel", "privacy"}


def _place_box(b: Box, pl, prefix: str) -> Box:
    """A part's box moved into the global frame: the bounds, a plan rotation (rot_box items), a vertical-plane rotation
    (stringers, stair rails), a mitred board's outline and a mesh's vertices all go through the part's placement."""
    x0, x1, y0, y1 = pl.box(b.x0, b.x1, b.y0, b.y1)
    rot, axis = b.rot, b.rot_axis
    tag = f"{prefix}: {b.tag}" if b.tag else ""
    if b.rot and axis == "z":               # a box turned in plan about its centre: keep its own extents, turn the centre and the angle
        cx, cy = pl.pt((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
        dx, dy = pl.pt(math.cos(b.rot), math.sin(b.rot)); ox_, oy_ = pl.pt(0.0, 0.0)
        rot = math.atan2(dy - oy_, dx - ox_)
        hl, ht = (b.x1 - b.x0) / 2, (b.y1 - b.y0) / 2
        x0, x1, y0, y1 = cx - hl, cx + hl, cy - ht, cy + ht
    elif b.rot and pl.swaps:
        axis = "x" if axis == "y" else "y"; rot = -rot
    nb = Box(b.kind, x0, x1, y0, y1, b.z0, b.z1, b.mat, b.phase, tag, b.shape, b.tone, rot, axis, b.xg)
    nb.layer = b.layer
    if b.quad:
        nb.quad = [list(pl.pt(q[0], q[1])) for q in b.quad]
    if b.pts:
        nb.pts = [[*pl.pt(q[0], q[1]), q[2]] for q in b.pts]
    return nb


def build_composite_scene(L) -> Scene:
    """Each part's scene in its own frame, moved into the global frame; the house and the yard drawn once, in the global
    frame: the measured house model and site model when the job has them, else the house from its measured footprint."""
    spec = L.spec
    g = spec.geometry
    zt = g.height_in * IN
    B: List[Box] = []
    add = lambda *a, **k: B.append(Box(*a, **k))
    for p in L.parts:
        S = build_scene(p.layout)
        for b in S.boxes:
            if b.kind in SITE_KINDS:       # each part's own ground and stand-in house
                continue
            B.append(_place_box(b, p.placement, p.name))
    __import__("decktakeoff.louvered", fromlist=["draw"]).draw(add, L)     # the job-level louvered roofs, once, in the global frame
    x0, x1, y0, y1 = L.bbox
    H_house = zt + 9.5
    hm, sm = getattr(g, "house_model", None), getattr(g, "site_model", None)
    if hm:
        from .house import build_house
        def _mesh(kind, tri, mat, tag=""):
            xs_ = [q[0] for q in tri]; ys_ = [q[1] for q in tri]; zs_ = [q[2] for q in tri]
            B.append(Box(kind, min(xs_), max(xs_), min(ys_), max(ys_), min(zs_), max(zs_), mat, 0, tag=tag, shape="mesh", pts=[[round(v, 3) for v in q] for q in tri]))
        rb = lambda *a, **k: B.append(rot_box(*a, **k))
        n_h = len(B)
        build_house(hm, add, rb, _mesh)
        for b_ in B[n_h:]:
            b_.layer = "house"
        if sm:
            from .landscape import build_site
            bz = float(sm.get("beyond_z", -0.9))
            add("ground", x0 - 140, x1 + 140, y0 - 90, y1 + 160, min(-1.6, bz - 0.6), bz, "ground")
            n0 = len(B)
            build_site(sm, add, rb, _mesh, zt)
            for b_ in B[n0:]:
                b_.layer = "site"
        else:
            add("ground", x0 - 60, x1 + 60, y0 - 40, y1 + 70, -0.6, 0.0, "ground")
    else:
        hx0 = min([x0] + [h[0] for h in g.house_blocks]); hx1 = max([x1] + [h[1] for h in g.house_blocks])
        hy0 = min([y0] + [h[2] for h in g.house_blocks]); hy1 = max([y1] + [h[3] for h in g.house_blocks])
        add("ground", hx0 - 60, hx1 + 60, hy0 - 40, hy1 + 70, -0.6, 0.0, "ground")
        for p in L.parts:
            for z in p.layout.zones:
                gx0, gx1, gy0, gy1 = p.placement.box(z.x0 * IN - 0.5, (z.x0 + z.W) * IN + 0.5, z.wall_y * IN, (z.wall_y + z.D) * IN + 0.5)
                add("gravel", gx0, gx1, gy0, gy1, 0.0, 0.04, "gravel")
        draw_house_from_spec(add, spec, zt, H_house)
    W = x1 - x0
    def zbox(p, z):
        return p.placement.box(z.x0 * IN, (z.x0 + z.W) * IN, z.wall_y * IN, (z.wall_y + z.D) * IN)
    meta = dict(job=spec.job, address=f"{spec.site.address}, {spec.site.city}".strip(", "), sf=L.deck_sf, height=g.height_in,
                zones=[dict(name=f"{p.name} {z.name}", label=z.label, x0=zbox(p, z)[0], W=zbox(p, z)[1] - zbox(p, z)[0],
                            wall_y=zbox(p, z)[2], D=zbox(p, z)[3] - zbox(p, z)[2], front=zbox(p, z)[3],
                            top=p.spec.geometry.height_in * IN) for p in L.parts for z in p.layout.zones],
                edge=0.0, timber=spec.is_timber, oiled=spec.framing.finish == "oil", step_text=step_captions(L), composite=True, bbox=list(L.bbox))
    if sun_vector(spec.site):
        meta["sun"] = list(sun_vector(spec.site))
    if sm and sm.get("cameras"):
        meta["cameras"] = sm["cameras"]
    if __import__("decktakeoff.louvered", fromlist=["has_roofs"]).has_roofs(spec):    # blades / screens a live viewer can turn and run
        meta["louvered_roofs"] = __import__("decktakeoff.louvered", fromlist=["descriptors"]).descriptors(L)
    S = Scene(B, zt, W, y0, y1, materials_for(spec), meta)
    S.x_min = x0
    return S




def draw_house_from_spec(add, spec, zt, H_house):
    """The house from its measured footprint (blocks, brick chimneys), the doors and windows on the walls facing the deck, and the porch cover."""
    # the house
    for h in spec.geometry.house_blocks:
        bx0, bx1, by0, by1 = h[:4]
        kind_ = str(h[4]).lower() if len(h) > 4 else ""
        brick = kind_ == "brick"
        if kind_ == "brickhouse":   # a brick-clad house block: running-bond brick, eave and roof slab like the sided blocks
            add("house", bx0, bx1, by0, by1, 0.0, H_house, "brick", tag="house (brick)")
            add("roof", bx0 - 1.0, bx1 + 1.0, by0 - 1.0, by1 + 1.0, H_house, H_house + 0.55, "roof")
            continue
        if kind_ == "cantilever":   # an upper floor that overhangs the wall below: [x0, x1, y0, y1, "cantilever", z_underside]
            z0c = float(h[5]) if len(h) > 5 else 8.0
            add("house", bx0, bx1, by0, by1, z0c, H_house, "house", tag="cantilevered floor (overhangs the wall below)")
            add("trim", bx0, bx1, by0, by1, z0c - 0.06, z0c, "trim", tag="cantilever soffit")
            add("roof", bx0 - 1.0, bx1 + 1.0, by0 - 1.0, by1 + 1.0, H_house, H_house + 0.55, "roof")
            continue
        if brick:   # a chimney: brick, taller than the eave, no roof slab; optional [.., "brick", z0, z1]
            z0c = float(h[5]) if len(h) > 5 else 0.0
            z1c = float(h[6]) if len(h) > 6 else H_house + 4.0
            add("house", bx0, bx1, by0, by1, z0c, z1c, "stone", tag="chimney (brick)")
        else:
            add("house", bx0, bx1, by0, by1, 0.0, H_house, "house", tag="house")
            add("roof", bx0 - 1.0, bx1 + 1.0, by0 - 1.0, by1 + 1.0, H_house, H_house + 0.55, "roof")
    for o in spec.geometry.house_openings:
        if len(o) > 5 and str(o[5]).lower() == "x":      # [y0, y1, x_face, z0, z1, "x"]: an opening on a wall that faces +x / -x
            oy0, oy1, xf, z0, z1 = o[:5]
            add("trim", xf - 0.05, xf + 0.06, oy0 - 0.25, oy1 + 0.25, z0 - 0.05, z1 + 0.25, "trim")
            add("glass", xf - 0.02, xf + 0.07, oy0, oy1, z0, z1, "glass")
            n = int((oy1 - oy0) // 3)
            for k in range(1, n + 1):
                my = oy0 + k * (oy1 - oy0) / (n + 1)
                add("trim", xf - 0.02, xf + 0.08, my - 0.06, my + 0.06, z0, z1, "trim")
            continue
        ox0, ox1, yf, z0, z1 = o[:5]
        add("trim", ox0 - 0.25, ox1 + 0.25, yf - 0.05, yf + 0.06, z0 - 0.05, z1 + 0.25, "trim")
        add("glass", ox0, ox1, yf - 0.02, yf + 0.07, z0, z1, "glass")
        if ox1 - ox0 > 4.5:
            n = int((ox1 - ox0) // 3)
            for k in range(1, n + 1):
                mx = ox0 + k * (ox1 - ox0) / (n + 1)
                add("trim", mx - 0.06, mx + 0.06, yf - 0.02, yf + 0.08, z0, z1, "trim")
    # existing cover, reset on the new deck: a shed roof of translucent panels — ledger on the house, rafters sloping down to a
    # beam on two 6x6 posts at the rail line. [x0, x1, y0, y1, "slope"]: slope "+x" = down toward +x (house at x0), "-x", "+y", "-y"
    if spec.geometry.cover:
        c = spec.geometry.cover
        cx0, cx1, cy0, cy1 = c[:4]
        slope = c[4] if len(c) > 4 else "+y"
        hi, lo = zt + 8.4, zt + 7.3
        along_x = slope in ("+x", "-x")
        run = (cx1 - cx0) if along_x else (cy1 - cy0)
        theta = math.atan2(hi - lo, run)
        # posts + beam at the low edge, ledger at the high edge
        if along_x:
            xl, xh = (cx1 - 0.5, cx0 + 0.15) if slope == "+x" else (cx0 + 0.5, cx1 - 0.15)
            n_cp = max(2, int(math.ceil((cy1 - cy0) / 8.5)) + 1)
            for k in range(n_cp):
                py = cy0 + 0.5 + k * (cy1 - cy0 - 1.0) / (n_cp - 1)
                add("post", xl - 0.23, xl + 0.23, py - 0.23, py + 0.23, zt, lo - 0.5, "timber", 8, tag="cover post 6x6 cedar")
            add("beam", xl - 0.25, xl + 0.25, cy0, cy1, lo - 0.5, lo, "timber", 8, tag="cover beam")
            add("ledger", xh - 0.08, xh + 0.08, cy0, cy1, hi - 0.6, hi, "timber", 8, tag="cover ledger")
            n = max(2, int((cy1 - cy0) / 2))
            L_r = math.hypot(run, hi - lo)
            for k in range(n + 1):
                ry = cy0 + k * (cy1 - cy0) / n
                add("joist", (cx0 + cx1) / 2 - L_r / 2, (cx0 + cx1) / 2 + L_r / 2, ry - 0.08, ry + 0.08, (hi + lo) / 2, (hi + lo) / 2 + 0.45, "timber", 8,
                    tag="cover rafter", rot=(-theta if slope == "+x" else theta), rot_axis="y")
            ss = spec.extras.cover_roof.lower().startswith("standing")
            add("ssroof" if ss else "glass", (cx0 + cx1) / 2 - L_r / 2 - 0.3, (cx0 + cx1) / 2 + L_r / 2 + 0.3, cy0 - 0.4, cy1 + 0.4, (hi + lo) / 2 + 0.45, (hi + lo) / 2 + (0.56 if ss else 0.52), "ssroof" if ss else "glass", 8,
                tag="standing seam steel roof" if ss else "cover panels", rot=(-theta if slope == "+x" else theta), rot_axis="y")
        else:
            yl, yh = (cy1 - 0.5, cy0 + 0.15) if slope == "+y" else (cy0 + 0.5, cy1 - 0.15)
            n_cp = max(2, int(math.ceil((cx1 - cx0) / 8.5)) + 1)      # same rule as the takeoff: posts ≤ 8'-6" OC at the rail line
            for k in range(n_cp):
                px = cx0 + 0.5 + k * (cx1 - cx0 - 1.0) / (n_cp - 1)
                add("post", px - 0.23, px + 0.23, yl - 0.23, yl + 0.23, zt, lo - 0.5, "timber", 8, tag="cover post 6x6 cedar")
            add("beam", cx0, cx1, yl - 0.25, yl + 0.25, lo - 0.5, lo, "timber", 8, tag="cover beam")
            add("ledger", cx0, cx1, yh - 0.08, yh + 0.08, hi - 0.6, hi, "timber", 8, tag="cover ledger")
            n = max(2, int((cx1 - cx0) / 2))
            L_r = math.hypot(run, hi - lo)
            for k in range(n + 1):
                rx = cx0 + k * (cx1 - cx0) / n
                add("joist", rx - 0.08, rx + 0.08, (cy0 + cy1) / 2 - L_r / 2, (cy0 + cy1) / 2 + L_r / 2, (hi + lo) / 2, (hi + lo) / 2 + 0.45, "timber", 8,
                    tag="cover rafter", rot=(theta if slope == "+y" else -theta), rot_axis="x")
            ss = spec.extras.cover_roof.lower().startswith("standing")
            add("ssroof" if ss else "glass", cx0 - 0.4, cx1 + 0.4, (cy0 + cy1) / 2 - L_r / 2 - 0.3, (cy0 + cy1) / 2 + L_r / 2 + 0.3, (hi + lo) / 2 + 0.45, (hi + lo) / 2 + (0.56 if ss else 0.52), "ssroof" if ss else "glass", 8,
                tag="standing seam steel roof" if ss else "cover panels", rot=(theta if slope == "+y" else -theta), rot_axis="x")
            if ss:   # snow retention bar 15" up from the low eave
                yb = (cy1 + 0.4 - 1.25) if slope == "+y" else (cy0 - 0.4 + 1.25)
                zb = lo + 0.45 + 0.56 + (1.25 * (hi - lo) / run)
                add("trim", cx0 - 0.3, cx1 + 0.3, yb - 0.08, yb + 0.08, zb, zb + 0.2, "steel", 8, tag="snow retention bar")
            if spec.extras.cover_gutters:   # 5" K gutter on the low eave, 2x3 downspouts strapped to the cover posts and down to grade
                ye = (cy1 + 0.6) if slope == "+y" else (cy0 - 0.6)
                yg0, yg1 = (ye + 0.08, ye + 0.5) if slope == "+y" else (ye - 0.5, ye - 0.08)
                add("gutter", cx0 - 0.4, cx1 + 0.4, yg0, yg1, lo + 0.45 - 0.42, lo + 0.45, "gutter", 8, tag="5\" K gutter")
                for px in (cx0 + 0.5, cx1 - 0.5):
                    xd = px + (0.45 if px < (cx0 + cx1) / 2 else -0.45)
                    add("gutter", xd - 0.1, xd + 0.15, yg0 - 0.05, yg0 + 0.2, 0.0, lo + 0.45 - 0.42, "gutter", 8, tag="2x3 downspout")
            if spec.extras.cover_soffit:      # ceiling under the rafters
                add("soffit", cx0 - 0.4, cx1 + 0.4, (cy0 + cy1) / 2 - L_r / 2 - 0.3, (cy0 + cy1) / 2 + L_r / 2 + 0.3, (hi + lo) / 2 - 0.04, (hi + lo) / 2, "soffit", 8,
                    tag="HardieSoffit ceiling", rot=(theta if slope == "+y" else -theta), rot_axis="x")
            if spec.extras.cover_fascia:      # fascia at the low edge + rakes on both ends
                ye = (cy1 + 0.6) if slope == "+y" else (cy0 - 0.6)
                add("hardie", cx0 - 0.4, cx1 + 0.4, ye - 0.08, ye + 0.08, lo + 0.45 - 0.6, lo + 0.52, "hardie", 8, tag="HardieTrim fascia")
                for xe in (cx0 - 0.4, cx1 + 0.4):
                    add("hardie", xe - 0.08, xe + 0.08, (cy0 + cy1) / 2 - L_r / 2 - 0.3, (cy0 + cy1) / 2 + L_r / 2 + 0.3, (hi + lo) / 2 - 0.15, (hi + lo) / 2 + 0.5, "hardie", 8,
                        tag="HardieTrim rake", rot=(theta if slope == "+y" else -theta), rot_axis="x")


# ================================================================== polygon outlines (angled edges)
DECK_KINDS = {"board", "border", "joist", "rim", "block", "fascia", "ledger", "beam"}


def _inside(poly, x, y) -> bool:
    n = len(poly); inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


def _clip_x(poly, y, x0, x1):
    """The part of the horizontal span [x0, x1] at height y that lies inside the polygon (largest run)."""
    xs = []
    n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if (ya > y) != (yb > y):
            xs.append(xa + (y - ya) * (xb - xa) / (yb - ya))
    xs.sort()
    best = None
    for a, b in zip(xs[0::2], xs[1::2]):
        lo, hi = max(a, x0), min(b, x1)
        if hi - lo > 0.05 and (best is None or hi - lo > best[1] - best[0]):
            best = (lo, hi)
    return best


def _clip_y(poly, x, y0, y1):
    ys = []
    n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if (xa > x) != (xb > x):
            ys.append(ya + (x - xa) * (yb - ya) / (xb - xa))
    ys.sort()
    best = None
    for a, b in zip(ys[0::2], ys[1::2]):
        lo, hi = max(a, y0), min(b, y1)
        if hi - lo > 0.05 and (best is None or hi - lo > best[1] - best[0]):
            best = (lo, hi)
    return best


def apply_outline(boxes: List[Box], spec, zt, jbot, jtop, jb, bt, fas_t, add_rims: bool = True) -> List[Box]:
    """Clip the deck's pieces to the true outline and add mitred rim / fascia along every angled edge."""
    poly = [(float(x), float(y)) for x, y in spec.geometry.outline]
    out: List[Box] = []
    for b in boxes:
        if b.kind == "fascia" and not b.rot:
            # fascia hangs outside the outline by its own thickness: clip it along a line just inside its face, and only where
            # the outline cuts it well short (a zone rectangle's fascia past an angled corner); drop what is left of a sliver
            horiz_ = (b.x1 - b.x0) >= (b.y1 - b.y0)
            cy_, cx_ = (b.y0 + b.y1) / 2, (b.x0 + b.x1) / 2
            best = None
            for sgn_ in (1, -1):
                sp = _clip_x(poly, cy_ + sgn_ * 0.12, b.x0, b.x1) if horiz_ else _clip_y(poly, cx_ + sgn_ * 0.12, b.y0, b.y1)
                if sp and (best is None or sp[1] - sp[0] > best[1] - best[0]):
                    best = sp
            if best is None or best[1] - best[0] < 0.3:
                continue
            lo, hi = (b.x0, b.x1) if horiz_ else (b.y0, b.y1)
            lo2 = best[0] if best[0] - lo > 0.15 else lo
            hi2 = best[1] if hi - best[1] > 0.15 else hi
            if (lo2, hi2) != (lo, hi):
                b = Box(b.kind, lo2, hi2, b.y0, b.y1, b.z0, b.z1, b.mat, b.phase, b.tag + " (angled cut)", b.shape, b.tone) if horiz_ else \
                    Box(b.kind, b.x0, b.x1, lo2, hi2, b.z0, b.z1, b.mat, b.phase, b.tag + " (angled cut)", b.shape, b.tone)
            out.append(b); continue
        if b.kind not in DECK_KINDS or b.rot:
            out.append(b); continue
        if b.tag and (b.tag.startswith("landing") or b.tag.startswith("tread") or "stair" in b.tag or b.tag.startswith("pf ") or b.tag.startswith("breaker")):
            out.append(b); continue          # stairs and landings sit outside the outline; plan-laid boards and borders are already cut to it
        cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
        along_x = (b.x1 - b.x0) >= (b.y1 - b.y0)
        if along_x:
            span = _clip_x(poly, cy, b.x0, b.x1)
            if span is None:
                continue
            if abs(span[0] - b.x0) > 0.02 or abs(span[1] - b.x1) > 0.02:
                b = Box(b.kind, span[0], span[1], b.y0, b.y1, b.z0, b.z1, b.mat, b.phase, b.tag + " (angled cut)", b.shape, b.tone)
        else:
            span = _clip_y(poly, cx, b.y0, b.y1)
            if span is None:
                continue
            if abs(span[0] - b.y0) > 0.02 or abs(span[1] - b.y1) > 0.02:
                b = Box(b.kind, b.x0, b.x1, span[0], span[1], b.z0, b.z1, b.mat, b.phase, b.tag + " (angled cut)", b.shape, b.tone)
        out.append(b)
    # mitred rim (and fascia) pieces along the angled edges
    n = len(poly)
    for i in (range(n) if add_rims else []):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if abs(xa - xb) < 0.01 or abs(ya - yb) < 0.01:
            continue
        L_e = math.hypot(xb - xa, yb - ya); phi = math.atan2(yb - ya, xb - xa)
        cx, cy = (xa + xb) / 2, (ya + yb) / 2
        # the rim sits just inside the edge: offset toward the polygon interior
        nx, ny = -math.sin(phi), math.cos(phi)
        if not _inside(poly, cx + nx * 0.5, cy + ny * 0.5):
            nx, ny = -nx, -ny
        for k in range(spec.framing.rim_plies):
            off = (k + 0.5) * jb
            out.append(Box("rim", cx + nx * off - L_e / 2, cx + nx * off + L_e / 2, cy + ny * off - jb / 2, cy + ny * off + jb / 2, jbot, jtop, "timber", 5,
                           tag=f"angled rim {L_e:.1f}' mitred", rot=phi, rot_axis="z"))
        if fas_t:
            out.append(Box("fascia", cx - nx * fas_t / 2 - L_e / 2, cx - nx * fas_t / 2 + L_e / 2, cy - ny * fas_t / 2 - fas_t / 2, cy - ny * fas_t / 2 + fas_t / 2, jbot - 0.15, zt - 0.02, "fascia", 6,
                           tag=f"angled fascia {L_e:.1f}' mitred", rot=phi, rot_axis="z"))
    return out


def _sail_hex(spec) -> str:
    sl = (spec.geometry.sails or [{}])[0]
    c = str(sl.get("color", "")).lower()
    return SAIL_COLORS.get(c, "#e6e1d2") if 'SAIL_COLORS' in globals() else "#e6e1d2"


def bench_segments(spec):
    """Each bench side as (x0, y0, x1, y1, nx, ny, bench dict) in feet; (nx, ny) points onto the deck."""
    out = []
    for bn in spec.geometry.benches or []:
        P = [(float(x), float(y)) for x, y in bn["path"]]
        for (x0, y0), (x1, y1) in zip(P, P[1:]):
            L_ = math.hypot(x1 - x0, y1 - y0)
            if L_ < 1e-6:
                continue
            ux, uy = (x1 - x0) / L_, (y1 - y0) / L_
            out.append((x0, y0, x1, y1, uy, -ux, bn))
    return out


def planter_segments(spec):
    """Each planter as (x0, y0, x1, y1, nx, ny, planter dict) in feet; (nx, ny) points onto the deck."""
    out = []
    for pl in spec.geometry.planters or []:
        (x0, y0), (x1, y1) = [(float(x), float(y)) for x, y in pl["path"][:2]]
        L_ = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L_, (y1 - y0) / L_
        out.append((x0, y0, x1, y1, uy, -ux, pl))
    return out


def draw_benches(add, spec, zt, fixed_append):
    """Built-in benches on the deck: 4x4 back posts bolted to the rim and 4x4 front legs, every post wrapped in deck
    board; a 2x6 seat bracket at each post pair; three seat boards with the outer two in the picture-frame colour, a
    front apron; three back slats. Planters: a treated 2x4 box skinned in deck board all round, picture-frame cap.
    A box step at the door (the existing step rebuilt): framed, decked, riser fascia."""
    IN_ = 1 / 12
    ins = 2.5 * IN_                     # inside the fascia / rim
    wrap = 5.5 * IN_                    # a 4x4 wrapped in deck board
    prev_end = None
    for x0, y0, x1, y1, nx, ny, bn in bench_segments(spec):
        shared = prev_end is not None and abs(prev_end[0] - x0) < 0.05 and abs(prev_end[1] - y0) < 0.05
        prev_end = (x1, y1)
        dep = float(bn.get("depth_in", 17)) * IN_; seat = float(bn.get("seat_in", 17)) * IN_
        L_ = math.hypot(x1 - x0, y1 - y0); ux, uy = (x1 - x0) / L_, (y1 - y0) / L_
        def pt(t, d):
            return x0 + ux * t + nx * d, y0 + uy * t + ny * d
        n_seat = 3
        for k in range(n_seat):
            d0 = ins + k * (dep / n_seat); d1 = d0 + dep / n_seat - 0.18 * IN_
            a, b = pt(0, (d0 + d1) / 2), pt(L_, (d0 + d1) / 2)
            fixed_append(rot_box("board", a[0], a[1], b[0], b[1], zt + seat - 1 * IN_, zt + seat, "border" if k in (0, n_seat - 1) else "deck", 6, d1 - d0,
                                 tag=f"bench seat {bn.get('name', '')}".strip()))
        a, b = pt(0.05, ins + dep - 0.5 * IN_), pt(L_ - 0.05, ins + dep - 0.5 * IN_)
        fixed_append(rot_box("board", a[0], a[1], b[0], b[1], zt + seat - 6.5 * IN_, zt + seat - 1 * IN_, "border", 6, 1 * IN_, tag="bench apron"))
        n_l = max(2, int(math.ceil(L_ / 3.0)) + 1)          # 36" max: the back slats span between the posts
        for k in range(1 if shared else 0, n_l):
            t = wrap / 2 + (L_ - wrap) * k / (n_l - 1)
            # back post (bolted to the rim, up to the back's top) and front leg, both wrapped
            for d, top, lab in ((ins + wrap / 2, float(bn.get("back_in", 34)) * IN_ if bn.get("back", True) else seat - 1 * IN_, "bench back post (4x4 wrapped)"),
                                (ins + dep - wrap / 2 - 0.6 * IN_, seat - 1 * IN_, "bench front leg (4x4 wrapped)")):
                cx, cy = pt(t, d)
                fixed_append(rot_box("benchpost", cx - ux * wrap / 2, cy - uy * wrap / 2, cx + ux * wrap / 2, cy + uy * wrap / 2, zt, zt + top, "border", 6, wrap, tag=lab))
        if bn.get("back", True):
            top = float(bn.get("back_in", 34)) * IN_
            a, b = pt(0, ins + wrap + 0.6 * IN_), pt(L_, ins + wrap + 0.6 * IN_)
            for k in range(3):
                z0 = zt + seat + 3 * IN_ + k * (top - seat - 3 * IN_) / 3
                fixed_append(rot_box("board", a[0], a[1], b[0], b[1], z0, z0 + 5.36 * IN_, "deck", 6, 1 * IN_, tag="bench back slat"))
    for x0, y0, x1, y1, nx, ny, pl in planter_segments(spec):
        w = float(pl.get("width_in", 17)) * IN_; h = float(pl.get("height_in", 17)) * IN_
        L_ = math.hypot(x1 - x0, y1 - y0); ux, uy = (x1 - x0) / L_, (y1 - y0) / L_
        def pt(t, d):
            return x0 + ux * t + nx * d, y0 + uy * t + ny * d
        t0, t1 = w * 0.6, L_ - w * 0.6       # clear of the house and of the left side's corner
        a, b = pt(t0, ins + w / 2), pt(t1, ins + w / 2)
        fixed_append(rot_box("board", a[0], a[1], b[0], b[1], zt, zt + h - 1 * IN_, "deck", 6, w, tag=f"planter {pl.get('name', '')} (deck board skin)".strip()))
        fixed_append(rot_box("board", a[0], a[1], b[0], b[1], zt + h - 1 * IN_, zt + h, "border", 6, w + 0.75 * IN_, tag="planter picture-frame cap"))
        a2, b2 = pt(t0 + 0.4, ins + w / 2), pt(t1 - 0.4, ins + w / 2)
        fixed_append(rot_box("board", a2[0], a2[1], b2[0], b2[1], zt + h - 2 * IN_, zt + h + 0.2 * IN_, "gravel", 6, w - 6 * IN_, tag="planter soil"))
    ds = getattr(spec.geometry, "door_step", None)
    if ds:
        xa, xb = float(ds["x0"]), float(ds["x1"]); dd = float(ds.get("depth_in", 21)) * IN_; r = float(ds.get("rise_in", 7)) * IN_
        fixed_append(Box("board", xa, xb, 0.0, dd, zt, zt + r, "deck", 6, tag="door step (box, decked)"))
        fixed_append(Box("fascia", xa, xb, dd, dd + 0.05, zt, zt + r, "fascia", 6, tag="door step riser"))


def draw_sails(add, spec):
    """Shade sails: a tensioned hypar between the attachment points (bilinear patch, corners pulled in 6% for the hardware),
    steel posts on concrete footings at the post corners, and the tension cables from each sail corner to its point."""
    for sl in spec.geometry.sails or []:
        P = [tuple(float(v) for v in c) for c in sl["corners"]]
        cx = sum(p[0] for p in P) / len(P); cy = sum(p[1] for p in P) / len(P); cz = sum(p[2] for p in P) / len(P)
        S = [(p[0] + (cx - p[0]) * 0.06, p[1] + (cy - p[1]) * 0.06, p[2] + (cz - p[2]) * 0.06) for p in P]
        if len(S) == 3:
            S = S + [S[2]]
        n = 14
        def at(u, v):
            a = [S[0][i] * (1 - u) + S[1][i] * u for i in range(3)]
            b = [S[3][i] * (1 - u) + S[2][i] * u for i in range(3)]
            q = [a[i] * (1 - v) + b[i] * v for i in range(3)]
            sag = 0.35 * math.sin(math.pi * u) * math.sin(math.pi * v)      # the cloth dishes a little between the corners
            return [q[0], q[1], q[2] - sag]
        tri = []
        for i in range(n):
            for j in range(n):
                u0, u1, v0, v1 = i / n, (i + 1) / n, j / n, (j + 1) / n
                tri += [at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v0), at(u1, v1), at(u0, v1)]
        xs = [p[0] for p in tri]; ys = [p[1] for p in tri]; zs = [p[2] for p in tri]
        add("sail", min(xs), max(xs), min(ys), max(ys), min(zs), max(zs), "sail", 8, tag=sl.get("name", "shade sail"), shape="mesh", pts=tri)
        od = float(sl.get("post_od_in", 6.625)) / 12
        for k, p in enumerate(P):
            q = S[k]
            L_ = math.dist(p, q)
            if L_ > 0.05:
                mx, my, mz = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2
                add("sailcable", mx - 0.02, mx + 0.02, my - 0.02, my + 0.02, mz - 0.02, mz + 0.02, "cable", 8, tag="turnbuckle + cable",
                    shape="mesh", pts=[list(p), list(q), [q[0], q[1], q[2] - 0.04], list(p), [q[0], q[1], q[2] - 0.04], [p[0], p[1], p[2] - 0.04]])
            if k in sl.get("posts", []) and sl.get("mount") == "deck_rail":     # on the deck: the rail's corner post, side-bolted to the rim
                sq = float(sl.get("post_in", 4.0)) / 12
                zd = spec.geometry.height_in / 12
                add("sailpost", p[0] - sq / 2 - 0.12, p[0] + sq / 2 + 0.12, p[1] - sq / 2 - 0.12, p[1] + sq / 2 + 0.12, zd, zd + 0.04, "railmetal", 7, tag="sail post base plate")
                add("sailpost", p[0] - sq / 2, p[0] + sq / 2, p[1] - sq / 2, p[1] + sq / 2, zd + 0.04, p[2] + 0.6, "railmetal", 7,
                    tag=f"{sl.get('post_in', 4)}\" steel sail post on the deck — the rail corner post")
            elif k in sl.get("posts", []):
                fd = float(sl.get("footing_dia_in", 24)) / 12
                add("footing", p[0] - fd / 2, p[0] + fd / 2, p[1] - fd / 2, p[1] + fd / 2, -0.5, 0.15, "concrete", 1, tag="sail post footing", shape="cyl")
                add("sailpost", p[0] - od / 2, p[0] + od / 2, p[1] - od / 2, p[1] + od / 2, 0.15, p[2] + 0.6, "railmetal", 2, tag=f"{sl.get('post_od_in', 6.625)}\" steel sail post", shape="cyl")
            else:
                add("trim", p[0] - 0.15, p[0] + 0.15, p[1] - 0.05, p[1] + 0.12, p[2] - 0.2, p[2] + 0.2, "steel", 8, tag="sail anchor plate on the house")


SAIL_COLORS = {"sand": "#d9cdb0", "desert sand": "#d9cdb0", "white": "#f1efe9", "charcoal": "#4a4c4e", "graphite": "#55585b", "steel grey": "#7d8287",
               "terracotta": "#b5654a", "mocha": "#7b6352", "beige": "#d8ccb4", "bronze": "#6b5340", "black": "#2a2a2c"}


def _rail_hex(color: str) -> str:
    c = (color or "").lower()
    return "#4b3b2c" if "bronze" in c else "#ecebe6" if "white" in c else "#6b6e70" if ("gray" in c or "grey" in c) else "#141416"


def _roof_hex(color: str) -> str:
    c = (color or "").lower()
    for k, v in (("black", "#1c1c1e"), ("charcoal", "#3a3c3f"), ("slate", "#4a4c48"), ("bronze", "#4a3a2a"), ("brown", "#4b3f34"), ("gray", "#6b6e70"), ("grey", "#6b6e70"), ("green", "#2f4a3a"), ("red", "#7a2a22"), ("white", "#e8e6e0")):
        if k in c:
            return v
    return "#3a3c3f"


def _outline_chain(poly, a, b, tol, lo_t, hi_t, ux, uy, L_):
    """Indices of the outline vertices on the polygon chain between points a and b — walking the polygon either way from
    the side nearest a to the side nearest b, the way whose vertices in between stay within tol of the straight a->b and
    inside its span — plus the outer vertices of those two end sides. None when neither way does (the caller then keeps
    every near vertex)."""
    n = len(poly)
    def near(P):
        best = None
        for i in range(n):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
            dx, dy = x1 - x0, y1 - y0
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((P[0] - x0) * dx + (P[1] - y0) * dy) / l2))
            d = math.hypot(x0 + t * dx - P[0], y0 + t * dy - P[1])
            if best is None or d < best[0] - 1e-9:
                best = (d, i)
        return best[1]
    ia, ib = near(a), near(b)
    def ok(v):
        px, py = poly[v]
        t = ((px - a[0]) * ux + (py - a[1]) * uy) / L_
        d = abs((px - a[0]) * -uy + (py - a[1]) * ux)
        return d < tol and lo_t - 0.05 < t < hi_t + 0.05
    fwd = [(ia + 1 + k) % n for k in range((ib - ia) % n)]          # vertices ia+1 .. ib
    back = [(ia - k) % n for k in range((ia - ib) % n)]             # vertices ia .. ib+1
    good = [set(c) | ({ia, (ib + 1) % n} if c is fwd else {(ia + 1) % n, ib}) for c in (fwd, back) if all(ok(v) for v in c)]
    return min(good, key=len) if good else None


def outline_path(spec, a, b, tol=3.0, ends=False):
    """Outline vertices (feet) between points a and b along the straight a->b, within tol ft of it — the curve of a front
    edge. ends=True also returns the vertices at the ends of the run (for interpolation); the default is strictly between.
    Empty when the outline is absent or straight there."""
    poly = [(float(x), float(y)) for x, y in (spec.geometry.outline or [])]
    if not poly:
        return []
    ax, ay = a; bx, by = b
    L_ = math.hypot(bx - ax, by - ay)
    if L_ < 0.1:
        return []
    ux, uy = (bx - ax) / L_, (by - ay) / L_
    lo, hi = (-0.02, 1.02) if ends else (0.02, 0.98)
    # only the outline that actually runs between the two ends can bend the run: a notch or jog elsewhere in the polygon
    # (an inset stair's notch 3' in from a straight front) has vertices within tol of the line but is not on the chain
    chain = _outline_chain(poly, a, b, tol, lo, hi, ux, uy, L_)
    pts = []
    for vi, (px, py) in enumerate(poly):
        if chain is not None and vi not in chain and math.hypot(px - ax, py - ay) > 0.1 and math.hypot(px - bx, py - by) > 0.1:
            continue
        t = ((px - ax) * ux + (py - ay) * uy) / L_
        d = abs((px - ax) * -uy + (py - ay) * ux)
        if lo < t < hi and d < tol and (ends or d > 0.02):
            pts.append((t, px, py))
    pts.sort()
    out = [(px, py) for _, px, py in pts]
    if not ends and not any(abs(py - ay) > 0.05 or abs(py - by) > 0.05 for px, py in out):
        return []      # every vertex sits on the straight line: not a curve
    return out


def front_runs(L):
    """Merged collinear x-running exposed edges (feet): [(x0, x1, y), ...] — the runs a curved outline is measured against."""
    runs = []
    for e in L.edges:
        if not e.exposed or abs(e.y1 - e.y0) > 0.05:
            continue
        y = e.y0 / 12.0; xa, xb = min(e.x0, e.x1) / 12.0, max(e.x0, e.x1) / 12.0
        for r in runs:
            if abs(r[2] - y) < 0.05 and (abs(r[1] - xa) < 0.1 or abs(r[0] - xb) < 0.1):
                r[0], r[1] = min(r[0], xa), max(r[1], xb); break
        else:
            runs.append([xa, xb, y])
    return runs


def rot_box(kind, x0, y0, x1, y1, z0, z1, mat, phase, thick, tag="", tone=0.0) -> Box:
    L_w = math.hypot(x1 - x0, y1 - y0); phi = math.atan2(y1 - y0, x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return Box(kind, cx - L_w / 2, cx + L_w / 2, cy - thick / 2, cy + thick / 2, z0, z1, mat, phase, tag=tag, rot=phi, rot_axis="z", tone=tone)


def angled_wall(x0, y0, x1, y1, z0=0.0, z1=18.0, thick=0.5) -> Box:
    L_w = math.hypot(x1 - x0, y1 - y0); phi = math.atan2(y1 - y0, x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return Box("wall", cx - L_w / 2, cx + L_w / 2, cy - thick / 2, cy + thick / 2, z0, z1, "house", tag="angled house wall", rot=phi, rot_axis="z")



def draw_cover(add, spec, c: dict, zt: float) -> None:
    """A lean-to roof cover (slope +y: high at the house, low at the posts): ledger on the house, (2)2x10 beam on 6x6 posts,
    2x8 rafters at 16" OC with the overhang, sheathing and the roof (standing seam with a snow bar, or shingles), Hardie
    soffit / fascia / rakes when specified, and the owner's roll-down blinds hung under the low beam.
    c: x0, x1 (post line extents), y0 (house wall), y1 (post line), clear_high_in / clear_low_in above the deck."""
    from .takeoff import cover_posts_x
    x0, x1, y0, y1 = float(c["x0"]), float(c["x1"]), float(c["y0"]), float(c["y1"])
    ov = float(c.get("overhang_ft", 1.0))
    from .catalog import actual as _act
    cbeam, cledg = c.get("beam", "(2)2x10"), c.get("ledger", "2x10")
    bd = _act(cbeam.split(")")[-1])[1] / 12             # beam / ledger depth (the ledger matches the beam line)
    rd = 7.25 / 12                                    # 2x8 rafter
    hi_b = zt + float(c.get("clear_high_in") or 100.0) / 12     # bottom of the ledger at the house
    lo_b = zt + float(c.get("clear_low_in") or 88.0) / 12       # bottom of the beam at the posts
    run = (y1 - y0)
    theta = math.atan2((hi_b + bd) - (lo_b + bd), run)
    on_piers = c.get("footing", "deck") in ("diamond_pier", "deck_pier")
    nm = c.get("name", "cover")
    # ledger, beam, posts
    add("cledger", x0 - 0.4, x1 + 0.4, y0, y0 + 0.13, hi_b, hi_b + bd, "ctimber", 8, tag=f"{nm} ledger {cledg}", xg=2.0)
    add("cbeam", x0 - 0.4, x1 + 0.4, y1 - 0.25, y1 + 0.25, lo_b, lo_b + bd, "ctimber", 8, tag=f"{nm} beam {cbeam}", xg=2.0)
    for px in cover_posts_x(c):
        zb = 0.45 if on_piers else zt
        hw_ = 0.25 if spec.framing.post_rough else 0.23
        add("cpost", px - hw_, px + hw_, y1 - hw_, y1 + hw_, zb, lo_b, "ctimber", 8, tag=f"{nm} post 6x6 " + post_words(spec))
        if on_piers and c.get("footing") != "deck_pier":     # a shared pier is drawn with the deck
            add("base", px - 0.27, px + 0.27, y1 - 0.27, y1 + 0.27, 0.33, 0.47, "steel", 1)
            add("footing", px - 0.55, px + 0.55, y1 - 0.55, y1 + 0.55, -0.15, 0.35, "concrete", 1, tag=f"{nm} Diamond Pier")
    # rafters: bottom edge on the ledger top at the house and the beam top at the posts, running past the beam by the overhang
    y_end = y1 + ov
    L_r = (y_end - y0) / math.cos(theta)
    yc = (y0 + y_end) / 2
    z_bot_c = (hi_b + bd) - math.tan(theta) * (yc - y0)      # rafter bottom line at the middle
    zc = z_bot_c + (rd / 2) / math.cos(theta)
    n = max(2, int(round((x1 - x0 + 0.8) / (16 / 12))))
    for k in range(n + 1):
        rx = x0 - 0.4 + 0.06 + k * (x1 - x0 + 0.8 - 0.12) / n
        add("rafter", rx - 0.0625, rx + 0.0625, yc - L_r / 2, yc + L_r / 2, zc - rd / 2, zc + rd / 2, "ctimber", 8, tag=f"{nm} rafter 2x8", rot=theta, rot_axis="x", xg=4.5)
    ss = spec.extras.cover_roof.lower().startswith("standing")
    z_top_c = z_bot_c + rd / math.cos(theta)
    add("ssroof" if ss else "roof", x0 - 0.4, x1 + 0.4, yc - L_r / 2 - 0.05, yc + L_r / 2 + 0.05, z_top_c + 0.02, z_top_c + 0.12, "ssroof" if ss else "roof", 8,
        tag="standing seam steel roof" if ss else "roof", rot=theta, rot_axis="x", xg=9.0)
    add("sheath", x0 - 0.4, x1 + 0.4, yc - L_r / 2 - 0.05, yc + L_r / 2 + 0.05, z_top_c - 0.04, z_top_c, "osb", 8, tag="7/16\" OSB sheathing", rot=theta, rot_axis="x", xg=6.0)
    add("underlay", x0 - 0.4, x1 + 0.4, yc - L_r / 2 - 0.05, yc + L_r / 2 + 0.05, z_top_c, z_top_c + 0.02, "underlay", 8, tag="high-temp ice & water underlayment", rot=theta, rot_axis="x", xg=7.5)
    z_eave_top = (hi_b + bd) - math.tan(theta) * (y_end - y0) + rd / math.cos(theta)
    if ss:   # snow retention bar 15" up the slope from the eave
        yb = y_end - 1.25
        zb = (hi_b + bd) - math.tan(theta) * (yb - y0) + rd / math.cos(theta) + 0.12
        add("trim", x0 - 0.4, x1 + 0.4, yb - 0.06, yb + 0.06, zb, zb + 0.16, "steel", 8, tag="snow retention bar", xg=10.5)
    if spec.extras.cover_soffit:
        add("soffit", x0 - 0.4, x1 + 0.4, yc - L_r / 2, yc + L_r / 2, z_bot_c - 0.05, z_bot_c, "soffit", 8, tag="HardieSoffit ceiling", rot=theta, rot_axis="x", xg=3.2)
    if spec.extras.cover_fascia:
        z_eave_bot = (hi_b + bd) - math.tan(theta) * (y_end - y0)
        add("hardie", x0 - 0.45, x1 + 0.45, y_end, y_end + 0.08, z_eave_bot - 0.12, z_eave_top + 0.12, "hardie", 8, tag="HardieTrim fascia", xg=5.5)
        for xe in (x0 - 0.45, x1 + 0.37):
            add("hardie", xe, xe + 0.08, yc - L_r / 2, yc + L_r / 2, z_bot_c - 0.12, z_bot_c + rd / math.cos(theta) + 0.12, "hardie", 8, tag="HardieTrim rake", rot=theta, rot_axis="x", xg=5.5)
    if spec.extras.cover_gutters:
        add("gutter", x0 - 0.45, x1 + 0.45, y_end + 0.08, y_end + 0.5, z_eave_top - 0.42, z_eave_top, "gutter", 8, tag="5\" K gutter", xg=5.5)
    # the owner's roll-down blinds: a roll under the beam's outer face; some bays lowered
    for bl in c.get("blinds") or []:
        a, b = float(bl.get("from_ft", x0)), float(bl.get("to_ft", x1))
        yb = y1 + 0.32
        zr = lo_b - 0.17
        Lb = b - a
        add("blind", (a + b) / 2 - 0.15, (a + b) / 2 + 0.15, yb - 0.15, yb + 0.15, zr - Lb / 2, zr + Lb / 2, "shade", 8, tag="roll-down blind (kept)", shape="cyl", rot=math.pi / 2)
        low = float(bl.get("lowered", 0.0))
        if low > 0:
            z_bot = zr - low * (zr - zt)
            add("blind", a + 0.05, b - 0.05, yb - 0.02, yb + 0.02, z_bot, zr, "shade", 8, tag="roll-down blind, lowered")
            add("trim", a + 0.05, b - 0.05, yb - 0.04, yb + 0.04, z_bot - 0.05, z_bot, "steel", 8, tag="blind bottom bar")
