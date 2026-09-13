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
        return dict(boxes=[asdict(b) for b in self.boxes], deck_top=self.deck_top, W=self.W, y_min=self.y_min, y_front=self.y_front,
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
        deck=dict(color=pal[len(pal) // 2], palette=pal, grain=True, rough=0.75, label=f"{spec.decking.brand} {spec.decking.collection} {spec.decking.color}"),
        border=dict(color=bpal[len(bpal) // 2], palette=bpal, grain=True, rough=0.75, label=f"{spec.decking.border_collection or spec.decking.collection} {spec.decking.border_color or spec.decking.color}"),
        drink=dict(color=dpal[len(dpal) // 2], palette=dpal, grain=True, rough=0.75),
        fascia=dict(color=pal[len(pal) // 2 - 1], grain=True, rough=0.75),
        steel=dict(color="#1c1c1e", metal=0.6, rough=0.45, label="black powder-coat"),
        cable=dict(color="#c9ccd0", metal=0.9, rough=0.3),
        concrete=dict(color="#c8c4bb", rough=0.95),
        stone=dict(color="#9a948b", rough=0.95, label="ledgestone veneer"),
        stonecap=dict(color="#b3ada2", rough=0.9),
        house=dict(color="#2a2624" if timber else "#d6c9a8", rough=0.9),
        roof=dict(color="#2b2422", rough=0.9),
        privacy=dict(color="#b8b0a2", rough=0.95),
        glass=dict(color="#7fa6c7", metal=0.2, rough=0.1),
        ground=dict(color="#7f9a5c", rough=1.0),
        gravel=dict(color="#a39c90", rough=1.0),
        water=dict(color="#3f9fd0", metal=0.1, rough=0.1),
        tub=dict(color="#4a4238", rough=0.7),
        hanger=dict(color="#1c1c1e" if spec.framing.hardware_finish == "black" else "#8f9498", metal=0.7, rough=0.5),
    )


def build_scene(L: Layout) -> Scene:
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

    # ---------------- site: ground, gravel, house, walls
    add("ground", -60, W + 60, y_min - 40, y_front + 60, -0.6, 0.0, "ground")
    add("gravel", -1, W + 1, y_min, y_front + 1.5, 0.0, 0.05, "gravel")
    # the house: a block behind every zone's wall (the walls jog, so the blocks step), each with its own roof and a 1-1/2' eave
    depth_back = 26.0
    for zi, z in enumerate(L.zones):
        yw = z.wall_y * IN
        x0h = z.x0 * IN - (3.0 if zi == 0 else 0.0)
        x1h = (z.x0 + z.W) * IN + (3.0 if zi == len(L.zones) - 1 else 0.0)
        add("house", x0h, x1h, yw - depth_back, yw, 0.0, H_house, "house", tag=f"house behind {z.name}")
        add("roof", x0h - 1.5, x1h + 1.5, yw - depth_back - 1.5, yw + 1.5, H_house, H_house + 0.8, "roof")
        cx = (z.x0 + z.W / 2) * IN
        gw = 6.0 if z.W > 200 else 3.5
        add("glass", cx - gw / 2, cx + gw / 2, yw - 0.02, yw + 0.02, zt + 0.1, zt + 6.8 if z.W > 200 else zt + 5.0, "glass")
        add("glass", cx - gw / 2, cx + gw / 2, yw - 0.02, yw + 0.02, max(0.5, zt - 6.0), max(0.5, zt - 6.0) + min(3.5, zt - 1.5) if zt > 4 else 0.5, "glass")
    # the walls of a recess between zones are the sides of the neighbouring block (drawn explicitly so they cast shadows into the wing)
    for a, b in zip(L.zones, L.zones[1:]):
        ya, yb = a.wall_y * IN, b.wall_y * IN
        if abs(ya - yb) > 0.01:
            xb = b.x0 * IN
            if ya < yb:   # a is recessed: b's block face at x = xb spans a's recess
                add("wall", xb, xb + 0.5, ya, yb, 0.0, H_house, "house", tag=f"return wall {a.name}/{b.name}")
            else:
                add("wall", xb - 0.5, xb, yb, ya, 0.0, H_house, "house", tag=f"return wall {a.name}/{b.name}")
    for zi, z in enumerate(L.zones):
        zl = spec.zone_list[zi]
        if zl.privacy_wall:
            side_x = (z.x0 * IN) if zi == 0 else ((z.x0 + z.W) * IN)
            add("privacy", side_x - 0.5 if zi == 0 else side_x, side_x if zi == 0 else side_x + 0.5, z.wall_y * IN, (z.wall_y + z.D) * IN + 1.0, 0.0, zt + 6.5, "privacy", tag="privacy / lot wall")

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
            if ft == "caisson":
                add("footing", x - 10 / 12, x + 10 / 12, y - 10 / 12, y + 10 / 12, -1.0, 0.5, "concrete", 1, tag=f"caisson P{li}-{pi + 1}", shape="cyl")
                base_top = 0.5
            elif ft == "diamond_pier":
                add("footing", x - 0.45, x + 0.45, y - 0.45, y + 0.45, -0.2, 0.3, "concrete", 1, tag="Diamond Pier")
                base_top = 0.3
            else:
                add("footing", x - 0.6, x + 0.6, y - 0.6, y + 0.6, -1.0, 0.15, "concrete", 1, shape="cyl")
                base_top = 0.15
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
        for p in rl.posts:
            x, y = p.x * IN, p.y * IN
            add("railpost", x - pw / 2, x + pw / 2, y - pw / 2, y + pw / 2, zt, zt + h, "steel", 7, tag=p.kind)
            add("railcap", x - pw / 2 - 0.03, x + pw / 2 + 0.03, y - pw / 2 - 0.03, y + pw / 2 + 0.03, zt + h, zt + h + 0.06, "steel", 7)
        # sections: reconstruct post pairs along each edge run from the post list order
        posts = [(p.x * IN, p.y * IN) for p in rl.posts]
        pairs = _rail_pairs(rl)
        for (xa, ya), (xb, yb) in pairs:
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

    # ---------------- furnishings: hot tub in its zone against the wall
    if spec.extras.hot_tub:
        zn = spec.extras.hot_tub_zone
        z = next((q for q in L.zones if q.name == zn), L.zones[0])
        bay = spec.extras.hot_tub_bay_in * IN
        x0 = z.x0 * IN + (z.W * IN - bay) / 2
        y0 = z.wall_y * IN + 1.0
        add("tub", x0, x0 + bay, y0, y0 + bay, zt, zt + 3.0, "tub", 8, tag="hot tub (by owner)")
        add("water", x0 + 0.4, x0 + bay - 0.4, y0 + 0.4, y0 + bay - 0.4, zt + 2.7, zt + 2.85, "water", 8)

    meta = dict(job=spec.job, address=f"{spec.site.address}, {spec.site.city}".strip(", "), sf=L.deck_sf, height=spec.geometry.height_in,
                zones=[dict(name=z.name, label=z.label, x0=z.x0 * IN, W=z.W * IN, wall_y=z.wall_y * IN, D=z.D * IN, front=(z.wall_y + z.D) * IN) for z in L.zones],
                edge=edge, timber=timber, oiled=spec.framing.finish == "oil",
                step_text=step_captions(L))
    return Scene(fixed, zt, W, y_min, y_front, materials_for(spec), meta)


def _rail_pairs(rl) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Consecutive post pairs along each run, from the post tags ('front:C+B 3', 'end:right 2', ...)."""
    runs: Dict[str, List[Tuple[int, float, float]]] = {}
    for p in rl.posts:
        run, _, idx = p.tag.rpartition(" ")
        runs.setdefault(run, []).append((int(idx), p.x * IN, p.y * IN))
    pairs = []
    for run, pts in runs.items():
        pts.sort()
        # a CORNER post is shared: it was merged into the earlier run, so re-attach the run's first post if missing
        for (i, x, y), (j, x2, y2) in zip(pts, pts[1:]):
            pairs.append(((x, y), (x2, y2)))
    # corner joins: a run whose first index is 2 starts at a merged corner post — find the corner post
    for run, pts in runs.items():
        if pts and pts[0][0] > 1:
            corner = [p for p in rl.posts if p.kind == "CORNER"]
            if corner:
                c = min(corner, key=lambda p: math.hypot(p.x * IN - pts[0][1], p.y * IN - pts[0][2]))
                pairs.append(((c.x * IN, c.y * IN), (pts[0][1], pts[0][2])))
    return pairs


def step_captions(L: Layout) -> Dict[int, str]:
    s = L.spec
    n_posts = sum(z.frame.n_posts for z in L.zones)
    ft = {"caisson": f"{n_posts} caissons {int(L.frame.footing_dia_in)}\" x {L.frame.footing_depth_in / 12:.1f}' below frost",
          "diamond_pier": f"{n_posts} Diamond Pier {L.frame.footing_model} driven-pin footings",
          "concrete": f"{n_posts} concrete piers {int(L.frame.footing_dia_in)}\" x {L.frame.footing_depth_in / 12:.1f}'"}[s.framing.footing_type]
    beams = " · ".join(f"{bl.label} ({bl.n_posts} posts)" for bl in L.beam_lines)
    out = {1: f"Step 1 · Footings — {ft}",
           2: f"Step 2 · Posts — {s.framing.post_size} {'Douglas fir #1' if s.is_timber else '#2 GC'} on {'black' if s.framing.hardware_finish == 'black' else 'ZMAX'} bases",
           3: "Step 3 · Stone column bases — 2'x2' x 3' ledgestone with 24\" caps" if s.extras.stone_bases else "Step 3 · (no stone bases)",
           4: f"Step 4 · Beams — {beams}",
           5: f"Step 5 · Frame — {s.framing.joist_size} joists at {L.frame.spacing:g}\", rims, ledger" + (", blocking over the beam" if L.frame.blocking_rows_y else ""),
           6: f"Step 6 · Decking — {s.decking.brand} {s.decking.collection} {s.decking.color}" + (f", {s.decking.border_color} border" if s.decking.border_color else "") + (", hidden fasteners" if (s.decking.fastener_system or '') != 'Cap-Tor xd face screw' else ""),
           7: (f"Step 7 · Rail — {L.rail.system} {L.rail.height:g}\" {L.rail.color}" + (", drink rail on top" if s.railing.drink_rail else "")) if L.rail else "Step 7 · (no rail)",
           8: "Step 8 · Your room" + (" — hot tub" if s.extras.hot_tub else "")}
    return out
