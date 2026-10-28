"""Vector axonometrics of the scene for the drawing sheets: the same boxes the 3D model is built from, projected
(isometric from a chosen corner, or a straight elevation), painted back to front, with numbered callouts on leaders
and a key. Exploded views lift each build phase (and each layer of a roof cover) like the 3D viewer does."""
from __future__ import annotations

import heapq
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


BUILT_IN = ("bench", "planter", "door step")     # board-kind boxes that are built-ins, not the deck surface


def _rank(b: Box) -> float:
    """Paint class when looking down. The parts of a measured house model (siding, trim, shutters...) paint after its walls
    and before the deck: a siding course runs the width of the wall, so its center can sit in front of a planter or bench."""
    r = RANK.get(b.kind)
    if r is not None:
        return r
    return -1.5 if getattr(b, "layer", "") == "house" else 0


def _plan_poly(cs):
    """A box's plan outline (its top face) from its 8 corners, in order around."""
    return [(cs[i][0], cs[i][1]) for i in FACES[5]]


def _overlap(P, Q) -> bool:
    """Two convex plan outlines overlap (separating axis test; touching is not overlapping)."""
    for poly in (P, Q):
        for i in range(len(poly)):
            (x0, y0), (x1, y1) = poly[i - 1], poly[i]
            nx, ny = y0 - y1, x1 - x0
            a = [nx * x + ny * y for x, y in P]; b = [nx * x + ny * y for x, y in Q]
            if max(a) <= min(b) + 1e-6 or max(b) <= min(a) + 1e-6:
                return False
    return True


def _area2(P) -> float:
    """Twice the signed area of a plan or view polygon (counterclockwise is positive)."""
    return sum(P[i - 1][0] * P[i][1] - P[i][0] * P[i - 1][1] for i in range(len(P)))


def _convex_clip(P, Q):
    """The part of convex polygon P inside convex polygon Q (Sutherland-Hodgman; either winding)."""
    if _area2(Q) < 0:
        Q = Q[::-1]
    out = list(P)
    for i in range(len(Q)):
        (ax, ay), (bx, by) = Q[i - 1], Q[i]
        inp, out = out, []
        if not inp:
            break
        for j in range(len(inp)):
            p, q = inp[j - 1], inp[j]
            sp = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
            sq = (bx - ax) * (q[1] - ay) - (by - ay) * (q[0] - ax)
            if sq >= 0:
                if sp < 0:
                    out.append((p[0] + (q[0] - p[0]) * sp / (sp - sq), p[1] + (q[1] - p[1]) * sp / (sp - sq)))
                out.append(q)
            elif sp >= 0:
                out.append((p[0] + (q[0] - p[0]) * sp / (sp - sq), p[1] + (q[1] - p[1]) * sp / (sp - sq)))
    return out


def _plane(F3, view):
    """A face's plane as depth along the view at a view-plane point: (n.r, n.u, n.d, n.q0), or None for a face seen edge-on."""
    nx = sum((F3[i - 1][1] - F3[i][1]) * (F3[i - 1][2] + F3[i][2]) for i in range(len(F3)))      # Newell's normal
    ny = sum((F3[i - 1][2] - F3[i][2]) * (F3[i - 1][0] + F3[i][0]) for i in range(len(F3)))
    nz = sum((F3[i - 1][0] - F3[i][0]) * (F3[i - 1][1] + F3[i][1]) for i in range(len(F3)))
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln < 1e-12:
        return None
    nx, ny, nz = nx / ln, ny / ln, nz / ln
    nd = nx * view.d[0] + ny * view.d[1] + nz * view.d[2]
    if abs(nd) < 1e-6:
        return None
    q0 = [sum(q[k] for q in F3) / len(F3) for k in range(3)]
    return (nx * view.r[0] + ny * view.r[1] + nz * view.r[2], nx * view.u[0] + ny * view.u[1] + nz * view.u[2], nd, nx * q0[0] + ny * q0[1] + nz * q0[2])


def _in_front(a, b, view, planes) -> Optional[int]:
    """Two painted faces (draw's tuples) where they overlap in the view: 1 when a is nearer the eye over the whole overlap, -1 when
    b is, 0 when it changes across the overlap or they lie in one plane (a board under its border), None when they do not overlap."""
    I = _convex_clip(a[2], b[2])
    if len(I) < 3 or abs(_area2(I)) < 4e-4:
        return None
    pa, pb = planes(a), planes(b)
    if pa is None or pb is None:
        return 0
    cx, cy = sum(p[0] for p in I) / len(I), sum(p[1] for p in I) / len(I)
    sgn = set()
    for px, py in [(cx, cy)] + [(0.7 * p[0] + 0.3 * cx, 0.7 * p[1] + 0.3 * cy) for p in I]:
        dd = (pa[3] - px * pa[0] - py * pa[1]) / pa[2] - (pb[3] - px * pb[0] - py * pb[1]) / pb[2]
        sgn.add(1 if dd > 2e-4 else -1 if dd < -2e-4 else 0)
    return sgn.pop() if len(sgn) == 1 else 0


def _elevation_order(polys, view):
    """An elevation (the camera level, nothing looked down on): each face painted by its own depth — exact for the faces square to
    the view — then every face seen at an angle (an angled side's fascia, rim or blocking, a sloped stringer) settled against each face
    it overlaps and shares depth with, by which is nearer the eye where they overlap: a 2x6 block behind an angled fascia stays behind
    it, a stringer behind a closed riser stays behind the riser."""
    dep = [sum(view.depth(q) for q in t[5]) / len(t[5]) for t in polys]
    order = sorted(range(len(polys)), key=lambda k: dep[k])
    pos = {k: i for i, k in enumerate(order)}
    rng = [(min(view.depth(q) for q in t[5]), max(view.depth(q) for q in t[5])) for t in polys]
    pl = {}
    planes = lambda f: pl[id(f)] if id(f) in pl else pl.setdefault(id(f), _plane(f[5], view))
    obl = []
    for k, t in enumerate(polys):
        pk = planes(t)
        if pk is not None and math.sqrt(pk[0] ** 2 + pk[1] ** 2) > 0.02:     # its plane turned off the view's: an oblique face
            obl.append(k)
    if not obl:
        return [polys[k] for k in order]
    box2 = [(min(p[0] for p in t[2]), max(p[0] for p in t[2]), min(p[1] for p in t[2]), max(p[1] for p in t[2])) for t in polys]
    G = 2.0
    grid: Dict[Tuple[int, int], List[int]] = {}
    for k, e in enumerate(box2):
        for gx in range(int(e[0] // G), int(e[1] // G) + 1):
            for gy in range(int(e[2] // G), int(e[3] // G) + 1):
                grid.setdefault((gx, gy), []).append(k)
    after: Dict[int, set] = {}                 # k -> faces that must paint before k
    seen = set()
    for a in obl:
        e = box2[a]
        for gx in range(int(e[0] // G), int(e[1] // G) + 1):
            for gy in range(int(e[2] // G), int(e[3] // G) + 1):
                for b in grid.get((gx, gy), ()):
                    if b == a or (min(a, b), max(a, b)) in seen:
                        continue
                    seen.add((min(a, b), max(a, b)))
                    f = box2[b]
                    if not (f[0] < e[1] and e[0] < f[1] and f[2] < e[3] and e[2] < f[3]):
                        continue
                    if rng[a][1] < rng[b][0] or rng[b][1] < rng[a][0]:      # apart in depth: the depth order already holds
                        continue
                    r = _in_front(polys[a], polys[b], view, planes)
                    if r == 1:
                        after.setdefault(a, set()).add(b)
                    elif r == -1:
                        after.setdefault(b, set()).add(a)
    if not after:
        return [polys[k] for k in order]
    nxt: Dict[int, List[int]] = {}
    need = {k: len(v) for k, v in after.items()}
    for k, v in after.items():
        for b in v:
            nxt.setdefault(b, []).append(k)
    heap = [(pos[k], k) for k in range(len(polys)) if not need.get(k)]
    heapq.heapify(heap)
    done, out = set(), []
    while len(out) < len(polys):
        if not heap:                           # a cycle (faces that cut through each other): the nearest-first of the rest goes
            k = min((k for k in range(len(polys)) if k not in done), key=lambda k: pos[k])
            need[k] = 0
            heapq.heappush(heap, (pos[k], k))
        _, k = heapq.heappop(heap)
        if k in done:
            continue
        done.add(k)
        out.append(polys[k])
        for m in nxt.get(k, ()):
            need[m] -= 1
            if need[m] == 0 and m not in done:
                heapq.heappush(heap, (pos[m], m))
    return out


def _frame_over_field(order, boxes, explode, gaps, view=None):
    """The picture frame and the breakers paint after the field boards whose ends they cover: a long board's center can sit in
    front of a short border's, and depth alone would paint the board's square end over the miter. A field board under a border
    moves up to just before the border's first face, but never past a face it hides: where it overlaps a wall, a parapet, a
    fascia, a blind or another board that it is nearer the eye than (or that it cuts through), it stays just after that face,
    as depth order had it. Every face it moves past is one that stands in front of it (a rail on the deck, a guard) or a border
    over it; every other face keeps its depth-order place."""
    deck = lambda b: not (b.tag or "").split(": ")[-1].startswith(BUILT_IN)
    fld = {i for i, b in enumerate(boxes) if b.kind == "board" and deck(b)}
    brd = {i for i, b in enumerate(boxes) if b.kind == "border" and deck(b)}
    if not fld or not brd:
        return order
    poly = {i: _plan_poly(corners(boxes[i], lift_of(boxes[i], explode, gaps))) for i in fld | brd}
    bb = {i: (min(p[0] for p in poly[i]), max(p[0] for p in poly[i]), min(p[1] for p in poly[i]), max(p[1] for p in poly[i])) for i in poly}
    first = {}
    for k, t in enumerate(order):
        if t[4] in brd and t[4] not in first:
            first[t[4]] = k
    over: Dict[int, set] = {}                # a field board: the borders over its end
    for j in brd:
        a = bb[j]
        for i in fld:
            if (bb[i][0] < a[1] and a[0] < bb[i][1] and bb[i][2] < a[3] and a[2] < bb[i][3]
                    and abs(boxes[i].z1 + lift_of(boxes[i], explode, gaps) - boxes[j].z1 - lift_of(boxes[j], explode, gaps)) < 0.3 and _overlap(poly[i], poly[j])):
                over.setdefault(i, set()).add(j)
    target = {i: min(first.get(j, len(order)) for j in js) - 0.5 for i, js in over.items()}
    moved = [k for k, t in enumerate(order) if t[4] in target and k > target[t[4]]]
    if not moved:
        return order
    if view is None or len(order[0]) < 6:            # no geometry to test against: lift as far as the border
        key = {k: target[order[k][4]] for k in moved}
    else:
        pl = {}
        planes = lambda f: pl[id(f)] if id(f) in pl else pl.setdefault(id(f), _plane(f[5], view))
        box2 = [(min(p[0] for p in t[2]), max(p[0] for p in t[2]), min(p[1] for p in t[2]), max(p[1] for p in t[2])) for t in order]
        G = 2.0
        grid: Dict[Tuple[int, int], List[int]] = {}
        for k, e in enumerate(box2):
            for gx in range(int(e[0] // G), int(e[1] // G) + 1):
                for gy in range(int(e[2] // G), int(e[3] // G) + 1):
                    grid.setdefault((gx, gy), []).append(k)
        near = {}
        for k in moved:
            e = box2[k]
            near[k] = sorted({m for gx in range(int(e[0] // G), int(e[1] // G) + 1) for gy in range(int(e[2] // G), int(e[3] // G) + 1)
                              for m in grid.get((gx, gy), ()) if m != k and box2[m][0] < e[1] and e[0] < box2[m][1] and box2[m][2] < e[3] and e[2] < box2[m][3]})
        lift = dict(target)                          # a board's paint place (a key among the faces' depth-order indices)
        cur = lambda m: lift[order[m][4]] + m * 1e-12 if (order[m][4] in lift and m > lift[order[m][4]]) else float(m)
        memo = {}
        for _ in range(40):
            changed = False
            for k in moved:
                i = order[k][4]
                kf = cur(k)
                lim = None
                for m in near[k]:
                    bm = order[m][4]
                    if bm == i or bm in over[i]:
                        continue
                    km = cur(m)
                    if not (kf < km < k):
                        continue
                    if (k, m) not in memo:
                        memo[(k, m)] = _in_front(order[k], order[m], view, planes)
                    r = memo[(k, m)]
                    if r is None or r < 0:                # apart in the view, or that face stands in front of the board
                        continue
                    lim = km if lim is None else max(lim, km)
                if lim is not None and lim + 1e-4 > lift[i]:
                    lift[i] = lim + 1e-4               # just after the face it hides
                    changed = True
            if not changed:
                break
        key = {k: cur(k) for k in moved}
    return [order[k] for k in sorted(range(len(order)), key=lambda k: key.get(k, k))]


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
         fit_boxes: Optional[Sequence[Box]] = None, record: Optional[list] = None):
    """Paint the boxes into frame (x, y, w, h) on the sheet. Returns (svg strings, to_sheet(point3d) -> (sx, sy), scale).
    record (a list): filled with (box, sheet polygon) for every face in paint order — what anchor_visible reads."""
    polys = []
    pts_all = []
    boxes = [b for b in boxes if (getattr(b, "layer", "") or "") != "styling"]            # styling furniture is never on a sheet
    fit_boxes = None if fit_boxes is None else [b for b in fit_boxes if (getattr(b, "layer", "") or "") != "styling"]
    for bi, b in enumerate(boxes):
        lf = lift_of(b, explode, gaps)
        if b.shape == "mesh" and b.pts:          # shade sail: its own triangles, shaded by how much each faces the light
            col = colors.get(b.mat, "#d9cdb0")
            for k in range(0, len(b.pts) - 2, 3):
                tri = [(q[0], q[1], q[2] + lf) for q in b.pts[k:k + 3]]
                (ax, ay, az), (bx, by, bz), (qx, qy, qz) = tri
                nx, ny, nz = (by - ay) * (qz - az) - (bz - az) * (qy - ay), (bz - az) * (qx - ax) - (bx - ax) * (qz - az), (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
                ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                k_ = 0.8 + 0.25 * abs(nz / ln)
                polys.append((RANK.get("sail", 6) if view.d[2] > 0.05 else 0, sum(view.depth(q) for q in tri) / 3, [view.p(q) for q in tri], _shade(col, k_), bi, tri))
                pts_all += [view.p(q) for q in tri] if fit_boxes is None else []
            continue
        cs = corners(b, lf)
        qp = getattr(b, "qpoly", None)          # a plan outline of 5+ corners (a field board cut to an angled house face): its prism
        if qp:
            top_, bot_ = [(x, y, b.z1 + lf) for x, y in qp], [(x, y, b.z0 + lf) for x, y in qp]
            cs = top_ + bot_
            fl = [top_, bot_[::-1]] + [[bot_[i - 1], bot_[i], top_[i], top_[i - 1]] for i in range(len(qp))]
        else:
            fl = [[cs[i] for i in f] for f in FACES]
        P = [view.p(q) for q in cs]
        clip_z = None if b.kind in ("footing", "base", "house", "ground") else lf     # nothing shows below grade but the piers
        pts_all += P if (fit_boxes is None) else []
        col = colors.get(b.mat, "#b8b2a6")
        ccx, ccy, ccz = (sum(q[k_] for q in cs) / len(cs) for k_ in range(3))
        for face in fl:
            nx = sum((face[i - 1][1] - face[i][1]) * (face[i - 1][2] + face[i][2]) for i in range(len(face)))      # Newell's normal
            ny = sum((face[i - 1][2] - face[i][2]) * (face[i - 1][0] + face[i][0]) for i in range(len(face)))
            nz = sum((face[i - 1][0] - face[i][0]) * (face[i - 1][1] + face[i][1]) for i in range(len(face)))
            cxf = sum(q[0] for q in face) / len(face) - ccx          # out from the piece's own center (a miter
            cyf = sum(q[1] for q in face) / len(face) - ccy          # outline's prism is not centered on its box)
            czf = sum(q[2] for q in face) / len(face) - ccz
            if nx * cxf + ny * cyf + nz * czf < 0:          # make the normal point out of the box
                nx, ny, nz = -nx, -ny, -nz
            if nx * view.d[0] + ny * view.d[1] + nz * view.d[2] <= 1e-9:
                continue
            ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            k = 1.06 if nz / ln > 0.6 else (0.86 if abs(nx / ln) > abs(ny / ln) else 0.72)
            dep = sum(view.depth(q) for q in face) / len(face)
            if clip_z is not None and min(q[2] for q in face) < clip_z - 1e-6:
                face = _clip_z(face, clip_z)
                if len(face) < 3:
                    continue
            polys.append(((_rank(b) if view.d[2] > 0.05 else 0), view.depth(((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2 + lift_of(b, explode, gaps))) * 0.7 + dep * 0.3,
                          [view.p(q) for q in face], _shade(col, k), bi, face))
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
    level = abs(view.d[2]) < 1e-6                 # an elevation: depth order face by face, exact where it matters
    for _, _, P, col, bi, _f in (_elevation_order(polys, view) if level else _frame_over_field(sorted(polys, key=lambda t: (t[0], t[1])), boxes, explode, gaps, view)):
        Q = [T(p) for p in P]
        if record is not None:
            record.append((boxes[bi], Q))
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


def _in_poly(Q, x, y) -> bool:
    c = False
    for i in range(len(Q)):
        (x0, y0), (x1, y1) = Q[i - 1], Q[i]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


class Painted:
    """The painted faces in paint order (draw's record), binned on the sheet: which box shows at a point."""
    def __init__(self, record, cell: float = 12.0):
        self.rec, self.cell, self.grid = record, cell, {}
        for k, (b, Q) in enumerate(record):
            xs, ys = [q[0] for q in Q], [q[1] for q in Q]
            for i in range(int(min(xs) // cell), int(max(xs) // cell) + 1):
                for j in range(int(min(ys) // cell), int(max(ys) // cell) + 1):
                    self.grid.setdefault((i, j), []).append(k)

    def top(self, x: float, y: float):
        """The box painted last at sheet point (x, y); None on bare paper."""
        best = -1
        for k in self.grid.get((int(x // self.cell), int(y // self.cell)), ()):
            if k > best and _in_poly(self.rec[k][1], x, y):
                best = k
        return self.rec[best][0] if best >= 0 else None


def _probe_points(cs, first):
    """Points to try on a box (its 8 corners cs): `first`, then a grid over each of its faces, nearest `first` first."""
    pts = []
    for f in FACES:
        A, B, C_, D = (cs[i] for i in f)
        for s in (0.5, 0.3, 0.7, 0.15, 0.85):
            for t in (0.5, 0.3, 0.7, 0.15, 0.85):
                pts.append(tuple((1 - s) * (1 - t) * A[k] + s * (1 - t) * B[k] + s * t * C_[k] + (1 - s) * t * D[k] for k in range(3)))
    pts.sort(key=lambda q: (q[0] - first[0]) ** 2 + (q[1] - first[1]) ** 2 + (q[2] - first[2]) ** 2)
    return [first] + pts


def anchor_visible(boxes: Sequence[Box], pred: Callable[[Box], bool], painted: "Painted", to_sheet, explode: bool = False, gaps=None,
                   pick: str = "mid", where: Tuple[float, float, float] = (0.5, 0.5, 1.0), spread: float = 1.5) -> Optional[Tuple[float, float, float]]:
    """anchor(), but on the member as painted: the preferred box and spot first, then the next spots and boxes in the pick's
    order, until a point (and a small ring round it) shows that member on top. None when every matching member is hidden."""
    m = [b for b in boxes if pred(b)]
    if not m:
        return None
    m.sort(key=lambda b: ((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2))
    first = anchor(m, lambda b: True, explode, gaps, pick, where)
    b0 = next((b for b in m if anchor([b], lambda q: True, explode, gaps, pick, where) == first), m[len(m) // 2])
    k0 = m.index(b0)
    order = [b0] + sorted((b for b in m if b is not b0), key=lambda b: abs(m.index(b) - k0))
    for sp in (spread, 0.0):                     # a clear spot with room round the dot; else any spot where it shows (a thin rail)
        ring = ((0.0, 0.0), (sp, 0.0), (-sp, 0.0), (0.0, sp), (0.0, -sp)) if sp else ((0.0, 0.0),)
        for b in order[:60]:
            cs = corners(b, lift_of(b, explode, gaps))
            xs, ys, zs = [c[0] for c in cs], [c[1] for c in cs], [c[2] for c in cs]
            want = (min(xs) + (max(xs) - min(xs)) * where[0], min(ys) + (max(ys) - min(ys)) * where[1], min(zs) + (max(zs) - min(zs)) * where[2])
            for q in _probe_points(cs, want):
                sx, sy = to_sheet(q)
                if all(painted.top(sx + dx, sy + dy) is b for dx, dy in ring):
                    return q
    return None


def callouts(items: List[Tuple[int, Tuple[float, float, float], str]], to_sheet, frame: Tuple[float, float, float, float], ink="#111", gold="#b8860b",
             size: float = 7.6, left_x: Optional[float] = None, right_x: Optional[float] = None) -> List[str]:
    """Numbered tags on leaders: anchors left of the drawing's center go to a column on the left, the rest on the right,
    each column sorted top to bottom so the leaders do not cross. Returns svg strings."""
    fx, fy, fw, fh = frame
    lx = left_x if left_x is not None else fx + 14
    rx = right_x if right_x is not None else fx + fw - 14
    mid = fx + fw / 2
    pts = [(it[0], to_sheet(it[1]), it[2], len(it) > 3 and bool(it[3])) for it in items if it[1] is not None]      # (n, q, label[, hidden])
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
        for (n, (ax, ay), lab, hid), y in zip(col, ys):
            tx = xcol
            dash = ' stroke-dasharray="3 2"' if hid else ""          # a member hidden in this view: a dashed leader to where it lies
            out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{tx + (14 if anchor_txt == "start" else -14):.1f}" y2="{y:.1f}" stroke="{ink}" stroke-width="0.6"{dash}/>')
            out.append(f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="1.6" fill="none" stroke="{ink}" stroke-width="0.6"/>' if hid else f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="1.6" fill="{ink}"/>')
            cxn = tx + (8 if anchor_txt == "start" else -8)
            out.append(f'<circle cx="{cxn:.1f}" cy="{y:.1f}" r="8" fill="{gold}" stroke="{ink}" stroke-width="0.6"/>')
            out.append(f'<text x="{cxn:.1f}" y="{y + 3.4:.1f}" font-size="9.5" font-weight="900" text-anchor="middle" fill="#111">{n}</text>')
    return out
