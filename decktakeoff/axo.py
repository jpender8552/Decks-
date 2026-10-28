"""Vector axonometrics of the scene for the drawing sheets: the same boxes the 3D model is built from, projected
(isometric from a chosen corner, or a straight elevation), painted back to front, with numbered callouts on leaders
and a key. Exploded views lift each build phase (and each layer of a roof cover) like the 3D viewer does."""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .scene import Box, Scene

GAP = {1: 0, 2: 0, 3: 0, 4: 5, 5: 9, 6: 14, 7: 19, 8: 23}      # the viewer's exploded lift per phase (ft)
SKIP = {"ground", "gravel", "water", "glass", "trim_house"}
# layered roof-cover parts paint after everything under them when the camera looks down (no z-fighting between slabs and rafters);
# the same for the deck's own layers: grade, piers, posts, beams, joists, then everything on top. A long deck board's center can sit
# behind a joist's, and depth alone would paint the joist over the decking.
RANK = {"house": -2, "roof": -1, "gravel": -0.95, "stepbase": -0.95, "footing": -0.9, "base": -0.9, "post": -0.8, "brace": -0.8, "cap": -0.75,
        "beam": -0.7, "joist": -0.6, "block": -0.6, "ledger": -0.6, "rim": -0.55,
        "rafter": 1, "soffit": 0, "sheath": 2, "underlay": 3, "ssroof": 4, "hardie": 5, "sail": 6}


def _rank(b: Box) -> float:
    """Paint class when looking down. The parts of a measured house model (siding, trim, shutters...) paint after its walls
    and before the deck: a siding course runs the width of the wall, so its center can sit in front of a planter or bench."""
    r = RANK.get(b.kind)
    if r is not None:
        return r
    return -1.5 if getattr(b, "layer", "") == "house" else 0


def _hex(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _shade(c: str, k: float) -> str:
    r, g, b = _hex(c)
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v * k))) for v in (r, g, b))


def _clip_z(poly, z0):
    """Sutherland-Hodgman: keep the part of a 3D polygon at or above z = z0."""
    out = []
    for i in range(len(poly)):
        a, b = poly[i - 1], poly[i]
        ina, inb = a[2] >= z0, b[2] >= z0
        if ina != inb:
            t = (z0 - a[2]) / (b[2] - a[2])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, z0))
        if inb:
            out.append(b)
    return out


def corners(b: Box, lift: float = 0.0) -> List[Tuple[float, float, float]]:
    """The 8 corners in plan feet (x along the house, y to the yard, z up), with the box's rotation about its center. A
    piece with a miter outline (Box.quad, 4 plan points around) is its prism, in the same corner order."""
    q = getattr(b, "quad", None)
    if q and len(q) == 4:
        pick = {(0, 0): q[0], (1, 0): q[1], (1, 1): q[2], (0, 1): q[3]}
        return [(float(pick[(ix, iy)][0]), float(pick[(ix, iy)][1]), (b.z1 if iz else b.z0) + lift) for ix in (0, 1) for iy in (0, 1) for iz in (0, 1)]
    cx, cy, cz = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2
    hx, hy, hz = (b.x1 - b.x0) / 2, (b.y1 - b.y0) / 2, (b.z1 - b.z0) / 2
    out = []
    c, s = math.cos(b.rot or 0.0), math.sin(b.rot or 0.0)
    for dx in (-hx, hx):
        for dy in (-hy, hy):
            for dz in (-hz, hz):
                x, y, z = dx, dy, dz
                if b.rot:
                    if b.rot_axis == "x":          # three rotation.x: (y_up, z_plan) plane
                        z, y = z * c - y * s, z * s + y * c
                    elif b.rot_axis == "z":        # about vertical (three rotation.y = -rot)
                        x, y = x * c - y * s, x * s + y * c
                    else:                          # three rotation.z: (x, z_up) plane
                        x, z = x * c - z * s, x * s + z * c
                out.append((cx + x, cy + y, cz + z + lift))
    return out


FACES = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]   # -x, +x, -y, +y, -z, +z (index = dx*4 + dy*2 + dz)


class View:
    """Orthographic camera: az = compass of the camera around the model in plan degrees (0 = straight out in the yard
    looking at the house, +90 = off the right end), el = height angle (0 = elevation)."""
    def __init__(self, az: float = 35.0, el: float = 30.0):
        a, e = math.radians(az), math.radians(el)
        self.r = (math.cos(a), -math.sin(a), 0.0)
        self.u = (-math.sin(a) * math.sin(e), -math.cos(a) * math.sin(e), math.cos(e))
        self.d = (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))

    def p(self, q):
        return (q[0] * self.r[0] + q[1] * self.r[1] + q[2] * self.r[2], q[0] * self.u[0] + q[1] * self.u[1] + q[2] * self.u[2])

    def depth(self, q):
        return q[0] * self.d[0] + q[1] * self.d[1] + q[2] * self.d[2]


def lift_of(b: Box, explode: bool, gaps: Optional[Dict[int, float]] = None) -> float:
    if not explode:
        return 0.0
    g = gaps or GAP
    return g.get(b.phase, 0.0) + (b.xg or 0.0)


def draw(boxes: Sequence[Box], colors: Dict[str, str], view: View, frame: Tuple[float, float, float, float], explode: bool = False,
         gaps: Optional[Dict[int, float]] = None, stroke: str = "#1b1b1d", sw: float = 0.35, pad: float = 0.04,
         fit_boxes: Optional[Sequence[Box]] = None):
    """Paint the boxes into frame (x, y, w, h) on the sheet. Returns (svg strings, to_sheet(point3d) -> (sx, sy), scale)."""
    polys = []
    pts_all = []
    boxes = [b for b in boxes if (getattr(b, "layer", "") or "") != "styling"]            # styling furniture is never on a sheet
    fit_boxes = None if fit_boxes is None else [b for b in fit_boxes if (getattr(b, "layer", "") or "") != "styling"]
    for b in boxes:
        lf = lift_of(b, explode, gaps)
        if b.shape == "mesh" and b.pts:          # shade sail: its own triangles, shaded by how much each faces the light
            col = colors.get(b.mat, "#d9cdb0")
            for k in range(0, len(b.pts) - 2, 3):
                tri = [(q[0], q[1], q[2] + lf) for q in b.pts[k:k + 3]]
                (ax, ay, az), (bx, by, bz), (qx, qy, qz) = tri
                nx, ny, nz = (by - ay) * (qz - az) - (bz - az) * (qy - ay), (bz - az) * (qx - ax) - (bx - ax) * (qz - az), (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
                ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                k_ = 0.8 + 0.25 * abs(nz / ln)
                polys.append((RANK.get("sail", 6) if view.d[2] > 0.05 else 0, sum(view.depth(q) for q in tri) / 3, [view.p(q) for q in tri], _shade(col, k_)))
                pts_all += [view.p(q) for q in tri] if fit_boxes is None else []
            continue
        cs = corners(b, lf)
        P = [view.p(q) for q in cs]
        clip_z = None if b.kind in ("footing", "base", "house", "ground") else lf     # nothing shows below grade but the piers
        pts_all += P if (fit_boxes is None) else []
        col = colors.get(b.mat, "#b8b2a6")
        for fi, f in enumerate(FACES):
            q0, q1, q2 = cs[f[0]], cs[f[1]], cs[f[2]]
            ux, uy, uz = q1[0] - q0[0], q1[1] - q0[1], q1[2] - q0[2]
            vx, vy, vz = q2[0] - q0[0], q2[1] - q0[1], q2[2] - q0[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            cxf = sum(cs[i][0] for i in f) / 4 - sum(q[0] for q in cs) / 8          # out from the piece's own center (a miter
            cyf = sum(cs[i][1] for i in f) / 4 - sum(q[1] for q in cs) / 8          # outline's prism is not centered on its box)
            czf = sum(cs[i][2] for i in f) / 4 - sum(q[2] for q in cs) / 8
            if nx * cxf + ny * cyf + nz * czf < 0:          # make the normal point out of the box
                nx, ny, nz = -nx, -ny, -nz
            if nx * view.d[0] + ny * view.d[1] + nz * view.d[2] <= 1e-9:
                continue
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            k = 1.06 if nz / ln > 0.6 else (0.86 if abs(nx / ln) > abs(ny / ln) else 0.72)
            dep = sum(view.depth(cs[i]) for i in f) / 4
            face = [cs[i] for i in f]
            if clip_z is not None and min(q[2] for q in face) < clip_z - 1e-6:
                face = _clip_z(face, clip_z)
                if len(face) < 3:
                    continue
            polys.append(((_rank(b) if view.d[2] > 0.05 else 0), view.depth(((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2 + lift_of(b, explode, gaps))) * 0.7 + dep * 0.3,
                          [view.p(q) for q in face], _shade(col, k)))
    if fit_boxes is not None:
        for b in fit_boxes:
            pts_all += [view.p(q) for q in corners(b, lift_of(b, explode, gaps))]
    if not pts_all:
        return [], (lambda q: (0, 0)), 1.0
    xs, ys = [p[0] for p in pts_all], [p[1] for p in pts_all]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    fx, fy, fw, fh = frame
    sc = min(fw * (1 - 2 * pad) / max(x1 - x0, 1e-6), fh * (1 - 2 * pad) / max(y1 - y0, 1e-6))
    ox = fx + (fw - (x1 - x0) * sc) / 2 - x0 * sc
    oy = fy + (fh - (y1 - y0) * sc) / 2 + y1 * sc
    T = lambda p: (ox + p[0] * sc, oy - p[1] * sc)
    out = []
    for _, _, P, col in sorted(polys, key=lambda t: (t[0], t[1])):
        Q = [T(p) for p in P]
        pts = " ".join(f"{q[0]:.1f},{q[1]:.1f}" for q in Q)
        area = abs(sum(Q[i][0] * Q[(i + 1) % len(Q)][1] - Q[(i + 1) % len(Q)][0] * Q[i][1] for i in range(len(Q)))) / 2
        per = sum(math.hypot(Q[(i + 1) % len(Q)][0] - Q[i][0], Q[(i + 1) % len(Q)][1] - Q[i][1]) for i in range(len(Q))) or 1.0
        if 4 * area / per < 1.6:            # a hairline face (a baluster, a cable): edged in its own shade, or the ink outline reads as its color
            out.append(f'<polygon points="{pts}" fill="{col}" stroke="{_shade(col, 0.8)}" stroke-width="0.3" stroke-linejoin="round"/>')
        else:
            out.append(f'<polygon points="{pts}" fill="{col}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"/>')
    to_sheet = lambda q: T(view.p(q))
    return out, to_sheet, sc


def anchor(boxes: Sequence[Box], pred: Callable[[Box], bool], explode: bool = False, gaps=None, pick: str = "mid",
           where: Tuple[float, float, float] = (0.5, 0.5, 1.0)) -> Optional[Tuple[float, float, float]]:
    """A 3D point on the boxes that match: the middle one (or the first / last), at the relative spot `where` of its extent."""
    m = [b for b in boxes if pred(b)]
    if not m:
        return None
    m.sort(key=lambda b: ((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2))
    if pick == "front":         # the one nearest the yard (nothing built in front of it), the most central of those
        ymax = max(b_.y1 for b_ in m)
        xs_ = [((b_.x0 + b_.x1) / 2) for b_ in m]
        xc = (min(xs_) + max(xs_)) / 2
        b = min((b_ for b_ in m if b_.y1 >= ymax - 0.5), key=lambda b_: abs((b_.x0 + b_.x1) / 2 - xc))
    else:
        b = {"first": m[0], "last": m[-1]}.get(pick, m[len(m) // 2])
    cs = corners(b, lift_of(b, explode, gaps))
    xs, ys, zs = [c[0] for c in cs], [c[1] for c in cs], [c[2] for c in cs]
    return (min(xs) + (max(xs) - min(xs)) * where[0], min(ys) + (max(ys) - min(ys)) * where[1], min(zs) + (max(zs) - min(zs)) * where[2])


def callouts(items: List[Tuple[int, Tuple[float, float, float], str]], to_sheet, frame: Tuple[float, float, float, float], ink="#111", gold="#b8860b",
             size: float = 7.6, left_x: Optional[float] = None, right_x: Optional[float] = None) -> List[str]:
    """Numbered tags on leaders: anchors left of the drawing's center go to a column on the left, the rest on the right,
    each column sorted top to bottom so the leaders do not cross. Returns svg strings."""
    fx, fy, fw, fh = frame
    lx = left_x if left_x is not None else fx + 14
    rx = right_x if right_x is not None else fx + fw - 14
    mid = fx + fw / 2
    pts = [(n, to_sheet(q), lab) for n, q, lab in items if q is not None]
    L = sorted([p for p in pts if p[1][0] < mid], key=lambda p: p[1][1])
    R = sorted([p for p in pts if p[1][0] >= mid], key=lambda p: p[1][1])
    out = []
    for col, xcol, anchor_txt in ((L, lx, "start"), (R, rx, "end")):
        if not col:
            continue
        gap = min(19.0, (fh - 16) / max(1, len(col)))
        ys = [min(max(p[1][1], fy + 10), fy + fh - 10) for p in col]      # each label as level with its anchor as it can be
        for i in range(1, len(ys)):
            ys[i] = max(ys[i], ys[i - 1] + gap)
        over = ys[-1] - (fy + fh - 10)
        if over > 0:
            ys = [v - over for v in ys]
            for i in range(len(ys) - 2, -1, -1):
                ys[i] = min(ys[i], ys[i + 1] - gap)
        for (n, (ax, ay), lab), y in zip(col, ys):
            tx = xcol
            out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{tx + (14 if anchor_txt == "start" else -14):.1f}" y2="{y:.1f}" stroke="{ink}" stroke-width="0.6"/>')
            out.append(f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="1.6" fill="{ink}"/>')
            cxn = tx + (7 if anchor_txt == "start" else -7)
            out.append(f'<circle cx="{cxn:.1f}" cy="{y:.1f}" r="7" fill="{gold}" stroke="{ink}" stroke-width="0.6"/>')
            out.append(f'<text x="{cxn:.1f}" y="{y + 2.8:.1f}" font-size="7.5" font-weight="900" text-anchor="middle" fill="#111">{n}</text>')
    return out
