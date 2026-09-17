"""3D / plan scene from a Layout: every stick, board, post, footing and rail part as an axis-aligned box (feet),
tagged with a material and a build phase. The Three.js viewer, the rendered stills and the SVG sheets all draw
from this one list, so the drawings and the model can never disagree.

Coordinates: x along the house, left to right facing the house from the yard; y from the reference house wall
toward the yard; z up from grade. Deck top = height_in / 12."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from .catalog import BOARDS_PALETTE, RAIL_SYSTEMS, actual, decking_facts, parse_beam
from .layout import Layout, NOSE, OVERHANG_NO_FASCIA, RAIL_POST_INSET
from .spec import DeckSpec

PHASES = {1: "Footings", 2: "Posts", 3: "Stone bases", 4: "Beams", 5: "Frame", 6: "Decking", 7: "Rail", 8: "Furnishings"}
IN = 1 / 12.0


@dataclass
class Box:
    kind: str          # house | wall | privacy | ground | gravel | footing | base | post | stone | cap | beam | ledger | joist | rim | block | doubler | board | border | fascia | railpost | toprail | cable | baluster | botrail | drink | tub | stringer | tread
    x0: float; x1: float; y0: float; y1: float; z0: float; z1: float
    mat: str
    phase: int = 0
    tag: str = ""
    shape: str = "box"  # box | cyl
    tone: float = 0.0   # per-board tone jitter (-1..1)
    rot: float = 0.0    # radians about the box centre: stair stringers / stair rails (axis below); 0 = axis-aligned
    rot_axis: str = "y" # "y": run along x (viewer rotation.z) | "x": run along y (viewer rotation.x)


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


def _palette(collection: str, color: str) -> List[str]:
    return BOARDS_PALETTE.get((collection, color), ["#8f6a42", "#a07a4d", "#b58a58", "#c49a68", "#d2ad7b"])


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
        timber=dict(color=wood, grain=True, rough=0.85, label=("Douglas fir #1, dark walnut oil" if oiled else "Douglas fir #1, unfinished") if timber else "#1 SYP pressure-treated"),
        deck=dict(color=pal[len(pal) // 2], palette=pal, grain=True, rough=0.7, label=f"{spec.decking.brand} {spec.decking.collection} {spec.decking.color}"),
        border=dict(color=bpal[len(bpal) // 2], palette=bpal, grain=True, rough=0.7, label=f"{spec.decking.border_collection or spec.decking.collection} {spec.decking.border_color or spec.decking.color}"),
        drink=dict(color=dpal[len(dpal) // 2], palette=dpal, grain=True, rough=0.7),
        fascia=(dict(color="#4b3f34", pattern="lap", rough=0.8, label=f"HardieTrim {spec.extras.hardie_skirt}") if spec.extras.hardie_skirt
                else dict(color=pal[max(0, len(pal) // 2 - 1)], palette=pal, grain=True, rough=0.7)),
        hardie=dict(color="#4b3f34", pattern="lap", rough=0.8, label="James Hardie ColorPlus Timber Bark"),
        soffit=dict(color="#4b3f34", pattern="batten", rough=0.85, label="HardieSoffit cedarmill Timber Bark"),
        steel=dict(color="#141416", metal=0.55, rough=0.5, label="black powder-coat"),
        cable=dict(color="#b8bcc2", metal=0.9, rough=0.35),
        concrete=dict(color="#b9b4aa", rough=0.95),
        stone=dict(color="#8c8478", pattern="stone", rough=0.95, label="ledgestone veneer"),
        brick=dict(color="#8e4a3a", pattern="brick", rough=0.95, label="brick"),
        stonecap=dict(color="#a8a297", rough=0.9),
        house=(dict(color="#d9d0bf", rough=0.95, label="stucco") if spec.geometry.house_finish == "stucco"
               else dict(color="#8e4a3a", pattern="brick", rough=0.95, label="brick") if spec.geometry.house_finish == "brick"
               else dict(color="#5b544d" if timber else "#cfc6b4", pattern="lap", rough=0.9)),
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
    )


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
    add("ground", -80, W + 80, y_min - 60, y_front + 90, -0.6, 0.0, "ground")
    for z in L.zones:   # weed barrier + rock under the deck footprint only
        add("gravel", z.x0 * IN - 0.5, (z.x0 + z.W) * IN + 0.5, z.wall_y * IN, (z.wall_y + z.D) * IN + 0.5, 0.0, 0.04, "gravel")
    depth_back = 26.0
    H_house = zt + 9.5                      # one storey above the deck floor
    door_h = 6.75
    if spec.geometry.house_blocks:
        draw_house_from_spec(add, spec, zt, H_house)
    else:
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
            else:
                add("base", x - pb_ / 2 - 0.02, x + pb_ / 2 + 0.02, y - pb_ / 2 - 0.02, y + pb_ / 2 + 0.02, base_top, base_top + 0.12, "steel", 2)
                add("post", x - pb_ / 2, x + pb_ / 2, y - pb_ / 2, y + pb_ / 2, base_top + 0.1, top - bd_, "timber", 2, tag=f"P{pi + 1}")
            add("cap", x - pb_ / 2 - 0.03, x + pb_ / 2 + 0.03, y - bw_ / 2 - 0.03, y + bw_ / 2 + 0.03, top - bd_ - 0.02, top - bd_ + 0.35, "steel", 4)
            if spec.extras.stone_bases:
                add("stone", x - 1.0, x + 1.0, y - 1.0, y + 1.0, 0.0, 3.0, "stone", 3)
                add("stonecap", x - 1.08, x + 1.08, y - 1.08, y + 1.08, 3.0, 3.17, "stonecap", 3)

    # ---------------- frame per zone
    for zi, z in enumerate(L.zones):
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
        flush_mid = sorted([b for b in fr.beams if b.kind == "flush" and b.cl_y < z.D - 3], key=lambda b: b.cl_y)
        bays: List[Tuple[float, float]] = []
        ya = yw + rear_t
        for b in flush_mid:
            bays.append((ya, yw + (b.cl_y - b.width / 2) * IN - 0.02)); ya = yw + (b.cl_y + b.width / 2) * IN + 0.02
        bays.append((ya, yf - rim_t))
        xs = [x0 + jx * IN for jx in fr.joist_x] + [x0 + px * IN for px in fr.pf_x]
        for dx, Ld, lab in L.divider_x:
            if x0 - 0.05 <= dx * IN <= x0 + W_z + 0.05 and (dx * IN < x0 + W_z - 0.05 or zi == len(L.zones) - 1):
                xs += [dx * IN - jb, dx * IN + jb]
        for xj in xs:
            for (ya_, yb_) in bays:
                add("joist", xj - jb / 2, xj + jb / 2, ya_, yb_, jbot, jtop, "timber", 5)
        for k in range(fr.rim_plies):
            add("rim", x0 + k * jb, x0 + (k + 1) * jb, yw + rear_t, yf - rim_t, jbot, jtop, "timber", 5, tag="side rim")
            add("rim", x0 + W_z - (k + 1) * jb, x0 + W_z - k * jb, yw + rear_t, yf - rim_t, jbot, jtop, "timber", 5, tag="side rim")
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
    for zi, z in enumerate(L.zones):
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
    for dx, Ld, lab in L.divider_x:
        x = dx * IN
        add("border", x - bw / 2, x + bw / 2, y_front - Ld * IN, y_front + edge, zt - bt, zt, "border", 6, tag=lab, tone=tone())
    fixed = B

    # ---------------- rail
    rl = L.rail
    if rl:
        sysd = RAIL_SYSTEMS.get(rl.system, RAIL_SYSTEMS["Fulton"])
        cable = sysd.get("cable", False)
        pw = sysd["post_w"] * IN
        h = rl.height * IN
        # posts on a curved run move onto the curve (inset RP), so the rail between them follows the outline without a kink
        RP_ = 2.5 * IN
        shift: Dict[Tuple[float, float], Tuple[float, float]] = {}
        for e in L.edges:
            if not e.exposed:
                continue
            ex0, ey0, ex1, ey1 = e.x0 * IN, e.y0 * IN, e.x1 * IN, e.y1 * IN
            cv = outline_path(spec, (ex0, ey0), (ex1, ey1))
            if not cv or abs(ey1 - ey0) > 0.05:
                continue     # only front (x-running) runs curve
            poly_ = [(ex0, ey0)] + cv + [(ex1, ey1)]
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
        for p in rl.posts:
            x, y = sh(p.x * IN, p.y * IN)
            add("railpost", x - pw / 2, x + pw / 2, y - pw / 2, y + pw / 2, zt, zt + h, "steel", 7, tag=p.kind)
            add("railcap", x - pw / 2 - 0.03, x + pw / 2 + 0.03, y - pw / 2 - 0.03, y + pw / 2 + 0.03, zt + h, zt + h + 0.06, "steel", 7)
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
                    B.append(rot_box("toprail", p0, q0, p1, q1, zt + h - 0.08, zt + h, "steel", 7, 0.12))
                    if cable:
                        for k in range(10):
                            zc = zt + 0.3 + k * 0.27
                            B.append(rot_box("cable", p0, q0, p1, q1, zc - 0.01, zc + 0.01, "cable", 7, 0.02))
                    else:
                        B.append(rot_box("botrail", p0, q0, p1, q1, zt + 0.25, zt + 0.33, "steel", 7, 0.12))
                        n_ = int(math.hypot(p1 - p0, q1 - q0) / (4 * IN))
                        for k in range(1, n_):
                            t_ = k / n_
                            bx_, by_ = p0 + (p1 - p0) * t_, q0 + (q1 - q0) * t_
                            add("baluster", bx_ - 0.03, bx_ + 0.03, by_ - 0.03, by_ + 0.03, zt + 0.33, zt + h - 0.08, "steel", 7)
                continue
            horiz = abs(yb - ya) < 0.01
            if horiz:
                x0_, x1_ = min(xa, xb), max(xa, xb); y0_, y1_ = ya - 0.06, ya + 0.06
            else:
                x0_, x1_ = xa - 0.06, xa + 0.06; y0_, y1_ = min(ya, yb), max(ya, yb)
            add("toprail", x0_, x1_, y0_, y1_, zt + h - 0.08, zt + h, "steel", 7)
            if cable:
                for k in range(10):
                    zc = zt + 0.3 + k * 0.27
                    if horiz:
                        add("cable", x0_, x1_, ya - 0.01, ya + 0.01, zc - 0.01, zc + 0.01, "cable", 7)
                    else:
                        add("cable", xa - 0.01, xa + 0.01, y0_, y1_, zc - 0.01, zc + 0.01, "cable", 7)
            else:
                add("botrail", x0_, x1_, y0_, y1_, zt + 0.25, zt + 0.33, "steel", 7)
                n = int(((x1_ - x0_) if horiz else (y1_ - y0_)) / (4 * IN))
                for k in range(1, n):
                    t = k * 4 * IN
                    if horiz:
                        add("baluster", x0_ + t - 0.03, x0_ + t + 0.03, ya - 0.03, ya + 0.03, zt + 0.33, zt + h - 0.08, "steel", 7)
                    else:
                        add("baluster", xa - 0.03, xa + 0.03, y0_ + t - 0.03, y0_ + t + 0.03, zt + 0.33, zt + h - 0.08, "steel", 7)
            if spec.railing.drink_rail:
                if horiz:
                    add("drink", x0_ - pw / 2, x1_ + pw / 2, ya - bw / 2, ya + bw / 2, zt + h + 0.06, zt + h + 0.06 + bt, "drink", 7, tone=tone())
                else:
                    add("drink", xa - bw / 2, xa + bw / 2, y0_ - pw / 2, y1_ + pw / 2, zt + h + 0.06, zt + h + 0.06 + bt, "drink", 7, tone=tone())

    # ---------------- stairs: stringers (rotated boxes), treads, closed risers, stair rail, landing pad
    for st in L.stairs:
        g = st.geo
        rise, run, width = g.riser_in * IN, g.tread_in * IN, st.width * IN
        n_r, n_t = g.risers, g.treads
        total_run = g.total_run_in * IN
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
        else:
            zn = side.split(":")[1] if ":" in side else None
            zz = next((q for q in L.zones if q.name == zn), L.zones[0]); direction = "+y"
            u0 = (zz.wall_y + zz.D) * IN + edge; v_a = zz.x0 * IN + st.opening.start_in * IN
        v_b = v_a + width
        theta = math.atan2(zt, total_run)
        def sb(kind, ua, ub, va, vb, za, zb, mat, phase, tag="", rot=0.0, tone_=0.0):
            if direction == "+x":
                add(kind, u0 + ua, u0 + ub, va, vb, za, zb, mat, phase, tag=tag, rot=-rot, rot_axis="y", tone=tone_)
            elif direction == "-x":
                add(kind, u0 - ub, u0 - ua, va, vb, za, zb, mat, phase, tag=tag, rot=rot, rot_axis="y", tone=tone_)
            else:
                add(kind, va, vb, u0 + ua, u0 + ub, za, zb, mat, phase, tag=tag, rot=rot, rot_axis="x", tone=tone_)
        # stringers: a 2x12 along the slope, centred under the nosing line
        depth = 11.25 * IN
        slope_len = math.hypot(total_run, zt)
        nst = max(2, st.stringers)
        for i in range(nst):
            v = v_a + 0.75 * IN + (width - 1.5 * IN) * i / (nst - 1)
            zc = zt / 2 - (depth / 2) / math.cos(theta) - 1.5 * IN
            sb("stringer", total_run / 2 - slope_len / 2, total_run / 2 + slope_len / 2, v - 0.75 * IN, v + 0.75 * IN, zc - depth / 2, zc + depth / 2, "timber", 5, tag=f"stringer {st.side}", rot=theta)
        for k in range(1, n_r + 1):
            ztop = zt - k * rise
            # riser board k at the back of tread k (the last riser sits at the pad)
            sb("riser", (k - 1) * run - 0.9 * IN, (k - 1) * run, v_a, v_b, ztop, ztop + rise - 0.02, "fascia", 6, tone_=tone())
            if k <= n_t:
                sb("tread", (k - 1) * run, k * run + NOSE * IN, v_a - 0.02, v_b + 0.02, ztop - bt, ztop, "deck", 6, tag=f"tread {k}", tone_=tone())
        # stair rail on the open side(s): posts top and bottom, a sloped top rail, a baluster per tread
        if st.stair_rail_sides and L.rail:
            sysd = RAIL_SYSTEMS.get(L.rail.system, RAIL_SYSTEMS["Fulton"])
            pw = sysd["post_w"] * IN
            hr = L.rail.height * IN
            sides = [v_b - pw / 2 - 0.02] if st.stair_rail_sides == 1 else [v_a + pw / 2 + 0.02, v_b - pw / 2 - 0.02]
            for vc in sides:
                for u_, zb_ in ((0.25, zt - rise), (total_run - 0.25, 0.0)):
                    sb("railpost", u_ - pw / 2, u_ + pw / 2, vc - pw / 2, vc + pw / 2, zb_, zb_ + hr + 0.3, "steel", 7, tag="stair post")
                rail_len = math.hypot(total_run - 0.5, zt - rise)
                zc = (zt - rise) / 2 + hr + 0.1
                sb("toprail", total_run / 2 - rail_len / 2, total_run / 2 + rail_len / 2, vc - 0.06, vc + 0.06, zc - 0.05, zc + 0.05, "steel", 7, rot=theta)
                if spec.railing.drink_rail:
                    sb("drink", total_run / 2 - rail_len / 2, total_run / 2 + rail_len / 2, vc - bw / 2, vc + bw / 2, zc + 0.06, zc + 0.06 + bt, "drink", 7, rot=theta, tone_=tone())
                if RAIL_SYSTEMS.get(L.rail.system, {}).get("cable"):
                    # horizontal cable infill runs parallel to the slope, 3-1/8" apart, plus a mid post on a run over 6'
                    n_c = int((hr - 0.25) / (3.125 * IN))
                    for i in range(1, n_c + 1):
                        zc_ = (zt - rise) / 2 + i * 3.125 * IN + 0.1
                        sb("cable", total_run / 2 - rail_len / 2, total_run / 2 + rail_len / 2, vc - 0.01, vc + 0.01, zc_ - 0.01, zc_ + 0.01, "cable", 7, rot=theta)
                    if rail_len > 6.5:
                        u_ = total_run / 2
                        sb("railpost", u_ - pw / 2, u_ + pw / 2, vc - pw / 2, vc + pw / 2, (zt - rise) / 2, (zt - rise) / 2 + hr + 0.3, "steel", 7, tag="stair post")
                else:
                    for k in range(1, n_t + 1):
                        for frac in (0.3, 0.7):
                            u_ = (k - 1) * run + frac * run
                            ztop = zt - k * rise
                            sb("baluster", u_ - 0.03, u_ + 0.03, vc - 0.03, vc + 0.03, ztop, ztop + hr - 0.02, "steel", 7)
        # mid-run carrier: (2)2x6 under the stringers on two posts and footings — the stringer run is over 6'
        if st.mid_support:
            um = st.mid_run_in * IN
            z_under = zt - (um / total_run) * zt - 1.5 * IN - depth / math.cos(theta) + 0.3   # underside of the stringers at mid-run
            zc_top = z_under - 0.02
            sb("beam", um - 1.5 * IN, um + 1.5 * IN, v_a - 0.25, v_b + 0.25, zc_top - 5.5 * IN, zc_top, "timber", 4, tag=f"stair carrier {st.side}")
            for vp in (v_a + 0.25, v_b - 0.25):
                sb("post", um - pb_ / 2, um + pb_ / 2, vp - pb_ / 2, vp + pb_ / 2, 0.55, zc_top - 5.5 * IN, "timber", 2, tag="stair carrier post")
                sb("base", um - pb_ / 2 - 0.02, um + pb_ / 2 + 0.02, vp - pb_ / 2 - 0.02, vp + pb_ / 2 + 0.02, 0.45, 0.57, "steel", 2)
                sb("footing", um - 0.55, um + 0.55, vp - 0.55, vp + 0.55, -0.1, 0.45, "concrete", 1, tag="stair footing")
        # landing pad
        sb("footing", total_run - 0.4, total_run + 3.6, v_a - 0.5, v_b + 0.5, -0.3, 0.02, "concrete", 1, tag=f"landing pad {st.side}")

    # ---------------- an existing stucco parapet on the open edges (stays; nothing in the takeoff)
    if spec.railing.existing_parapet:
        for e in L.edges:
            if not e.exposed:
                continue
            ex0, ey0, ex1, ey1 = e.x0 * IN, e.y0 * IN, e.x1 * IN, e.y1 * IN
            L_ = ((ex1 - ex0) ** 2 + (ey1 - ey0) ** 2) ** 0.5
            if L_ < 0.1:
                continue
            curve = outline_path(spec, (ex0, ey0), (ex1, ey1))
            if curve:
                pts_ = [(ex0, ey0)] + curve + [(ex1, ey1)]
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
        fixed = apply_outline(fixed, spec, zt, jbot, jtop, jb, bt, fas_t if fascia else 0.0)
    if spec.geometry.house_walls:
        for wseg in spec.geometry.house_walls:
            fixed.append(angled_wall(*wseg, z0=0.0, z1=H_house))
    meta = dict(job=spec.job, address=f"{spec.site.address}, {spec.site.city}".strip(", "), sf=L.deck_sf, height=spec.geometry.height_in,
                zones=[dict(name=z.name, label=z.label, x0=z.x0 * IN, W=z.W * IN, wall_y=z.wall_y * IN, D=z.D * IN, front=(z.wall_y + z.D) * IN, ledger=bool(z.frame.ledger)) for z in L.zones],
                edge=edge, timber=timber, oiled=spec.framing.finish == "oil",
                outline=[list(p) for p in spec.geometry.outline] if spec.geometry.outline else None,
                step_text=step_captions(L))
    return Scene(fixed, zt, W, y_min, y_front, materials_for(spec), meta)


def _rail_pairs(rl) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Post pairs that carry a section, per run. A run's posts are tagged 'side N'; the corner post shared with the
    neighbouring run lives in that run's list, so every collinear CORNER post is added back before pairing, and a gap
    between two posts is a section only when its length matches one of the run's sections (an opening otherwise)."""
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
        pts2 = list(pts)
        for c in corners:
            if (horiz and abs(c[1] - pts[0][1]) < 0.02) or (vert and not horiz and abs(c[0] - pts[0][0]) < 0.02):
                if not any(abs(c[0] - q[0]) < 0.02 and abs(c[1] - q[1]) < 0.02 for q in pts2):
                    pts2.append((c[0], c[1], "CORNER"))
        pts2.sort(key=(lambda q: q[0]) if horiz else (lambda q: q[1]))
        ctcs = [sec.ctc for sec in rl.sections if sec.side == run]
        for a, b in zip(pts2, pts2[1:]):
            d = (abs(b[0] - a[0]) if horiz else abs(b[1] - a[1])) * 12
            hit = next((i for i, c in enumerate(ctcs) if abs(c - d) < 1.5), None)
            if hit is None and ctcs:
                continue            # an opening (concrete step, stair) — no panel
            if hit is not None:
                ctcs.pop(hit)
            pairs.append(((a[0], a[1]), (b[0], b[1])))
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
           2: f"Step 2 · Posts — {s.framing.post_size} {'Douglas fir #1' if s.is_timber else '#2 GC'} on {'black' if s.framing.hardware_finish == 'black' else 'ZMAX'} bases",
           3: "Step 3 · Stone column bases — 2'x2' x 3' ledgestone with 24\" caps" if s.extras.stone_bases else "Step 3 · (no stone bases)",
           4: f"Step 4 · Beams — {beams}",
           5: f"Step 5 · Frame — {s.framing.joist_size} joists at {L.frame.spacing:g}\", rims, ledger" + (", blocking over the beam" if L.frame.blocking_rows_y else ""),
           6: f"Step 6 · Decking — {s.decking.brand} {s.decking.collection} {s.decking.color}" + (f", {s.decking.border_color} border" if s.decking.border_color else "") + (", hidden fasteners" if (s.decking.fastener_system or '') != 'Cap-Tor xd face screw' else ""),
           7: (f"Step 7 · Rail — {L.rail.system} {L.rail.height:g}\" {L.rail.color}" + (", drink rail on top" if s.railing.drink_rail else "")) if L.rail else ("Step 7 · Rail — existing stucco parapet stays" if s.railing.existing_parapet else "Step 7 · (no rail)"),
           8: "Step 8 · Your room" + (" — hot tub" if s.extras.hot_tub else "")}
    return out


# ================================================================== composite decks
SITE_KINDS = {"house", "wall", "roof", "trim", "glass", "ground", "gravel", "privacy"}


def build_composite_scene(L) -> Scene:
    """Each part's scene in its own frame, moved into the global frame; the house from its measured footprint."""
    spec = L.spec
    zt = spec.geometry.height_in * IN
    B: List[Box] = []
    add = lambda *a, **k: B.append(Box(*a, **k))
    deck_boxes = []
    for p in L.parts:
        S = build_scene(p.layout)
        pl = p.placement
        for b in S.boxes:
            if b.kind in SITE_KINDS:
                continue
            x0, x1, y0, y1 = pl.box(b.x0, b.x1, b.y0, b.y1)
            rot, axis = b.rot, b.rot_axis
            if b.rot and pl.swaps:
                axis = "x" if axis == "y" else "y"; rot = -rot
            nb = Box(b.kind, x0, x1, y0, y1, b.z0, b.z1, b.mat, b.phase, f"{p.name}: {b.tag}" if b.tag else "", b.shape, b.tone, rot, axis)
            B.append(nb); deck_boxes.append(nb)
    x0, x1, y0, y1 = L.bbox
    H_house = zt + 9.5
    # site
    hx0 = min([x0] + [h[0] for h in spec.geometry.house_blocks]); hx1 = max([x1] + [h[1] for h in spec.geometry.house_blocks])
    hy0 = min([y0] + [h[2] for h in spec.geometry.house_blocks]); hy1 = max([y1] + [h[3] for h in spec.geometry.house_blocks])
    add("ground", hx0 - 60, hx1 + 60, hy0 - 40, hy1 + 70, -0.6, 0.0, "ground")
    for p in L.parts:
        for z in p.layout.zones:
            gx0, gx1, gy0, gy1 = p.placement.box(z.x0 * IN - 0.5, (z.x0 + z.W) * IN + 0.5, z.wall_y * IN, (z.wall_y + z.D) * IN + 0.5)
            add("gravel", gx0, gx1, gy0, gy1, 0.0, 0.04, "gravel")
    draw_house_from_spec(add, spec, zt, H_house)
    W = x1 - x0
    # the viewer's camera framing wants the deck's extent: shift nothing, report the bbox
    meta = dict(job=spec.job, address=f"{spec.site.address}, {spec.site.city}".strip(", "), sf=L.deck_sf, height=spec.geometry.height_in,
                zones=[dict(name=f"{p.name} {z.name}", label=z.label, x0=p.placement.box(z.x0 * IN, (z.x0 + z.W) * IN, z.wall_y * IN, (z.wall_y + z.D) * IN)[0],
                            W=abs((p.placement.box(z.x0 * IN, (z.x0 + z.W) * IN, z.wall_y * IN, (z.wall_y + z.D) * IN)[1]) - (p.placement.box(z.x0 * IN, (z.x0 + z.W) * IN, z.wall_y * IN, (z.wall_y + z.D) * IN)[0])),
                            wall_y=0, D=0, front=0) for p in L.parts for z in p.layout.zones],
                edge=0.0, timber=spec.is_timber, oiled=spec.framing.finish == "oil", step_text=step_captions(L), composite=True, bbox=list(L.bbox))
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


def apply_outline(boxes: List[Box], spec, zt, jbot, jtop, jb, bt, fas_t) -> List[Box]:
    """Clip the deck's pieces to the true outline and add mitred rim / fascia along every angled edge."""
    poly = [(float(x), float(y)) for x, y in spec.geometry.outline]
    out: List[Box] = []
    for b in boxes:
        if b.kind not in DECK_KINDS or b.rot or b.kind == "fascia":   # fascia hangs outside the outline by its own thickness: never clip it
            out.append(b); continue
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
    for i in range(n):
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


def _roof_hex(color: str) -> str:
    c = (color or "").lower()
    for k, v in (("black", "#1c1c1e"), ("charcoal", "#3a3c3f"), ("slate", "#4a4c48"), ("bronze", "#4a3a2a"), ("brown", "#4b3f34"), ("gray", "#6b6e70"), ("grey", "#6b6e70"), ("green", "#2f4a3a"), ("red", "#7a2a22"), ("white", "#e8e6e0")):
        if k in c:
            return v
    return "#3a3c3f"


def outline_path(spec, a, b, tol=3.0):
    """Outline vertices (feet) strictly between points a and b along the straight a->b, within tol ft of it — the curve of a
    front edge. Empty when the outline is absent or straight there."""
    poly = [(float(x), float(y)) for x, y in (spec.geometry.outline or [])]
    if not poly:
        return []
    ax, ay = a; bx, by = b
    L_ = math.hypot(bx - ax, by - ay)
    if L_ < 0.1:
        return []
    ux, uy = (bx - ax) / L_, (by - ay) / L_
    pts = []
    for px, py in poly:
        t = ((px - ax) * ux + (py - ay) * uy) / L_
        d = abs((px - ax) * -uy + (py - ay) * ux)
        if 0.02 < t < 0.98 and d < tol and d > 0.02:
            pts.append((t, px, py))
    pts.sort()
    return [(px, py) for _, px, py in pts]


def rot_box(kind, x0, y0, x1, y1, z0, z1, mat, phase, thick, tag="", tone=0.0) -> Box:
    L_w = math.hypot(x1 - x0, y1 - y0); phi = math.atan2(y1 - y0, x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return Box(kind, cx - L_w / 2, cx + L_w / 2, cy - thick / 2, cy + thick / 2, z0, z1, mat, phase, tag=tag, rot=phi, rot_axis="z", tone=tone)


def angled_wall(x0, y0, x1, y1, z0=0.0, z1=18.0, thick=0.5) -> Box:
    L_w = math.hypot(x1 - x0, y1 - y0); phi = math.atan2(y1 - y0, x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return Box("wall", cx - L_w / 2, cx + L_w / 2, cy - thick / 2, cy + thick / 2, z0, z1, "house", tag="angled house wall", rot=phi, rot_axis="z")
