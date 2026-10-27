"""The yard around the deck, built from a measured site model (geometry.site_model): a graded lawn (a heightfield
interpolated from spot grades), raised beds behind a segmental retaining wall, single-course block edging, brick paver
borders, flagstones, trees, shrubs, cedar privacy fences on the lot lines and the neighbours' houses as massing. Box and
mesh geometry only, so the WebGL viewer and the photoreal renderer draw the same yard.

Opt-in pieces (a model without the key draws exactly as before): ground areas of their own material inside the graded
extent (native grass on a creek bank, the creek) and polygon holes (the house); a bed drawn as a concrete slab (a level
top, its exposed edge down to the lawn, sawcut joints) or as ground cover (low leafy mounds over the soil); split-rail
fences with welded-wire mesh and spaced-picket fences, any fence in its own wood; pines; a deciduous crown in its own
leaf materials; a neighbour house turned to its own axis, with a brick base.

Frame: the deck's plan frame in feet (x along the rear wall from the deck's left end, y out into the yard, z up from the
reference grade at the main stair; the deck top is the spec height)."""
from __future__ import annotations

import math
import random
from typing import Callable, Dict, List, Sequence, Tuple

IN = 1 / 12.0

DEFAULT_COLORS = dict(lawn="#6d8a3c", mulch="#4b3326", soil="#5d4a36", groundcover="#3f5a2c", block="#c99d86", block2="#d3b499",
                      block3="#ad9483", block4="#bea291", brick="#9b4b3b", brick2="#b0624c", flag="#c8a184", flag2="#b38f76",
                      cedar="#9b7a5c", bark="#5a4637", leaf="#93a03c", leaf2="#c2b043", spruce="#5d7f7b", spruce2="#6f9089",
                      shrub="#8c3b2a", shrub2="#5f7537", rock="#a39b8f", well="#9ea3a6",
                      concrete="#b5b0a6", joint="#6f6a62", ivy="#35502a", ivy2="#4a6a34", pine="#4b6a33", pine2="#637f3c",
                      rail="#7a6b5b", wire="#3c3d3a", picket="#4e3f33", cedar_old="#6e5a4b", meadow="#8b8a50", water="#4e5d55")

# materials only a model that uses them gets (a model without them keeps exactly the material set it had)
_EXTRA = dict(concrete_slab=("concrete", dict(rough=0.92, label="concrete patio slab")),
              concrete_joint=("joint", dict(rough=0.95)),
              ivy=("ivy", dict(rough=0.85, label="ground cover (vinca / ivy)")), ivy2=("ivy2", dict(rough=0.85)),
              spruce_pine=("pine", dict(rough=0.9, label="pine")), spruce_pine2=("pine2", dict(rough=0.9)),
              rail=("rail", dict(grain=True, rough=0.95, label="split-rail fence")),
              wire=("wire", dict(metal=0.5, rough=0.55, label="welded-wire mesh")),
              picket=("picket", dict(grain=True, rough=0.9, label="stained picket fence")),
              cedar_old=("cedar_old", dict(grain=True, rough=0.95, label="weathered cedar privacy fence")),
              meadow=("meadow", dict(pattern="grass", rough=1.0, label="native grass")),
              water=("water", dict(rough=0.12, label="creek")))


def _used_keys(model: dict) -> set:
    """Every material key the model names, and the ones its pieces draw with by default."""
    keys = set()
    def walk(v):
        if isinstance(v, str):
            keys.add(v)
        elif isinstance(v, dict):
            for w in v.values():
                walk(w)
        elif isinstance(v, (list, tuple)):
            for w in v:
                walk(w)
    walk({k: v for k, v in model.items() if k not in ("cameras", "colors")})
    for b in model.get("beds", []):
        if b.get("joints"):
            keys.add("concrete_joint")
        if b.get("edge") is not None and "mat" not in b:
            keys.add("concrete_slab")
        if b.get("mounds") is not None:
            keys.update((b.get("mounds") or {}).get("mats", ["ivy", "ivy2"]))
    for f in model.get("fences", []):
        st = f.get("style", "privacy")
        if st == "split_rail":
            keys.add(f.get("mat", "rail"))
            if f.get("mesh"):
                keys.add((f.get("mesh") or {}).get("mat", "wire") if isinstance(f.get("mesh"), dict) else "wire")
        elif st == "picket":
            keys.add(f.get("mat", "picket"))
    for t in model.get("trees", []):
        if t.get("type") == "pine":
            keys.update(t.get("mats", ["spruce_pine", "spruce_pine2"]))
    for a in model.get("grade", {}).get("areas", []):
        keys.add(a.get("mat", "meadow"))
    return keys


def materials(model: dict) -> Dict[str, dict]:
    c = dict(DEFAULT_COLORS, **(model.get("colors") or {}))
    used = _used_keys(model)
    extra = {k: dict(color=c[ck], **o) for k, (ck, o) in _EXTRA.items() if k in used}
    return dict(extra, **dict(
        lawn=dict(color=c["lawn"], pattern="grass", rough=1.0, label="lawn"),
        mulch=dict(color=c["mulch"], pattern="gravel", rough=1.0, label="shredded bark mulch"),
        groundcover=dict(color=c["groundcover"], pattern="grass", rough=1.0, label="ground cover"),
        wblock=dict(color=c["block"], rough=0.95, label="tumbled segmental wall block"),
        wblock2=dict(color=c["block2"], rough=0.95),
        wblock3=dict(color=c["block3"], rough=0.95),
        wblock4=dict(color=c["block4"], rough=0.95),
        paver=dict(color=c["brick"], pattern="paver", rough=0.9, label="clay brick pavers"),
        flag=dict(color=c["flag"], rough=0.9, label="flagstone"),
        flag2=dict(color=c["flag2"], rough=0.9),
        cedar=dict(color=c["cedar"], grain=True, rough=0.9, label="cedar privacy fence"),
        bark=dict(color=c["bark"], rough=0.95),
        leaf=dict(color=c["leaf"], rough=0.9, label="tree canopy"),
        leaf2=dict(color=c["leaf2"], rough=0.9),
        spruce=dict(color=c["spruce"], rough=0.9, label="blue spruce"),
        spruce2=dict(color=c["spruce2"], rough=0.9),
        shrub=dict(color=c["shrub"], rough=0.9),
        shrub2=dict(color=c["shrub2"], rough=0.9),
        rock=dict(color=c["rock"], pattern="gravel", rough=1.0, label="river rock"),
        soil=dict(color=c["soil"], pattern="gravel", rough=1.0, label="bare soil"),
    )


# ------------------------------------------------------------------ geometry helpers
def _poly_area(P):
    return 0.5 * sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))


def _in_poly(x, y, P):
    c = False
    n = len(P)
    for i in range(n):
        (x1, y1), (x2, y2) = P[i], P[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def triangulate(P: Sequence[Sequence[float]]) -> List[Tuple[int, int, int]]:
    """Ear clipping for a simple polygon (either winding). Returns index triples."""
    idx = list(range(len(P)))
    if _poly_area(P) < 0:
        idx.reverse()
    out = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        n = len(idx)
        for k in range(n):
            a, b, c = idx[(k - 1) % n], idx[k], idx[(k + 1) % n]
            (ax, ay), (bx, by), (cx, cy) = P[a][:2], P[b][:2], P[c][:2]
            if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= 1e-9:
                continue                                    # reflex
            ok = True
            for j in idx:
                if j in (a, b, c):
                    continue
                px, py = P[j][:2]
                d1 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                d2 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                d3 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                if d1 >= 0 and d2 >= 0 and d3 >= 0:
                    ok = False
                    break
            if ok:
                out.append((a, b, c))
                idx.pop(k)
                break
        else:
            break
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def _resample(path: Sequence[Sequence[float]], step: float, smooth: bool = True) -> List[Tuple[float, float]]:
    """Points every `step` along a polyline; with smooth=True the corners are rounded (Chaikin, 3 passes) first."""
    pts = [tuple(p[:2]) for p in path]
    if smooth and len(pts) > 2:
        for _ in range(3):
            q = [pts[0]]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                q += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
            q.append(pts[-1])
            pts = q
    out = [pts[0]]
    carry = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-9:
            continue
        s = step - carry
        while s <= L + 1e-9:
            out.append((x0 + (x1 - x0) * s / L, y0 + (y1 - y0) * s / L))
            s += step
        carry = L - (s - step)
    if math.hypot(out[-1][0] - pts[-1][0], out[-1][1] - pts[-1][1]) > step * 0.3:
        out.append(pts[-1])
    return out


class Grade:
    """Spot grades -> a smooth lawn surface (inverse-distance weighting, power 2, a small smoothing radius)."""
    def __init__(self, points: Sequence[Sequence[float]], power: float = 2.0):
        self.P = [tuple(float(v) for v in p) for p in points]
        self.p = power

    def __call__(self, x: float, y: float) -> float:
        num = den = 0.0
        for px, py, pz in self.P:
            d2 = (x - px) ** 2 + (y - py) ** 2 + 4.0
            w = 1.0 / d2 ** (self.p / 2)
            num += w * pz
            den += w
        return num / den if den else 0.0


# ------------------------------------------------------------------ the builder
class _Site:
    def __init__(self, model: dict, add: Callable, rot: Callable, mesh: Callable, zt: float):
        self.m, self.add, self.rot, self.mesh, self.zt = model, add, rot, mesh, zt
        self.g = Grade(model.get("grade", {}).get("points", [[0, 0, 0]]))
        self.rng = random.Random(int(model.get("seed", 7)))

    def tube(self, p0, p1, r0, r1, mat, kind="tree", tag="", n=7):
        """A tapered prism from p0 to p1 (any direction) as mesh triangles."""
        ax, ay, az = (p1[i] - p0[i] for i in range(3))
        L = math.sqrt(ax * ax + ay * ay + az * az) or 1e-6
        ax, ay, az = ax / L, ay / L, az / L
        ux, uy, uz = (1.0, 0.0, 0.0) if abs(ax) < 0.9 else (0.0, 1.0, 0.0)
        # e1 = u x a, e2 = a x e1
        e1 = (uy * az - uz * ay, uz * ax - ux * az, ux * ay - uy * ax)
        l1 = math.sqrt(sum(v * v for v in e1)); e1 = tuple(v / l1 for v in e1)
        e2 = (ay * e1[2] - az * e1[1], az * e1[0] - ax * e1[2], ax * e1[1] - ay * e1[0])
        ring = lambda c, r, k: [c[i] + r * (math.cos(2 * math.pi * k / n) * e1[i] + math.sin(2 * math.pi * k / n) * e2[i]) for i in range(3)]
        tri = []
        for k in range(n):
            a0, a1 = ring(p0, r0, k), ring(p0, r0, k + 1)
            b0, b1 = ring(p1, r1, k), ring(p1, r1, k + 1)
            tri += [a0, a1, b1, a0, b1, b0]
        self.mesh(kind, tri, mat, tag=tag)

    # ---------------------------------------------------------- lawn
    def lawn(self):
        gm = self.m.get("grade", {})
        x0, x1, y0, y1 = gm.get("extent", [-40, 60, -12, 36])
        res = float(gm.get("res", 1.0))
        holes = [h for h in gm.get("holes", [])]          # rectangles with no lawn (the house)
        nx, ny = int(math.ceil((x1 - x0) / res)), int(math.ceil((y1 - y0) / res))
        Z = [[self.g(x0 + i * res, y0 + j * res) for i in range(nx + 1)] for j in range(ny + 1)]
        tri = []
        for j in range(ny):
            for i in range(nx):
                xa, xb, ya, yb = x0 + i * res, x0 + (i + 1) * res, y0 + j * res, y0 + (j + 1) * res
                if any(hx0 <= xa and xb <= hx1 and hy0 <= ya and yb <= hy1 for hx0, hx1, hy0, hy1 in holes):
                    continue
                p00, p10, p11, p01 = [xa, ya, Z[j][i]], [xb, ya, Z[j][i + 1]], [xb, yb, Z[j + 1][i + 1]], [xa, yb, Z[j + 1][i]]
                tri += [p00, p10, p11, p00, p11, p01]
        self.mesh("ground", tri, "lawn", tag="lawn")

    # ---------------------------------------------------------- flat areas
    def flat(self, poly, z, mat, kind="ground", tag="", lift=0.0, follow=False):
        P = [tuple(p[:2]) for p in poly]
        tri = []
        for a, b, c in triangulate(P):
            for k in (a, b, c):
                zz = (self.g(*P[k]) + lift) if follow else z
                tri.append([P[k][0], P[k][1], zz])
        self.mesh(kind, tri, mat, tag=tag)

    def beds(self):
        walls = {w.get("name"): w for w in self.m.get("walls", [])}
        for b in self.m.get("beds", []):
            if b.get("wall"):                     # the bed runs to the wall's (smoothed) face line, then closes back along `close`
                w = walls[b["wall"]]
                poly = _resample(w["path"], 0.5, smooth=w.get("smooth", True)) + [tuple(q) for q in b.get("close", [])]
            else:
                poly = b["poly"]
            self.flat(poly, float(b.get("z", 0.0)), b.get("mat", "mulch"), "ground", tag=b.get("name", "bed"),
                      lift=float(b.get("lift", 0.04)), follow=b.get("z") is None)

    # ---------------------------------------------------------- segmental block walls and edging
    def wall(self, w: dict):
        """Tumbled segmental block, running bond. `path` is the TOP course's outside face line; lower courses step out by
        the setback (batter). Courses run down to `bury` below the lawn on the low (outside) face, so the wall grows where
        the lawn falls away. top_z: a level top (retaining wall); None: `exposed_in` above the lawn (edging)."""
        bl, bh, bd = (float(v) * IN for v in w.get("block_in", [11.5, 4.0, 8.0]))
        st = _resample(w["path"], (bl + 0.25 * IN) / 2, smooth=w.get("smooth", True))      # half-block stations
        top = w.get("top_z")
        bury = float(w.get("bury", 0.25))
        setback = float(w.get("setback_in", 0.6)) * IN
        mats = ["wblock", "wblock2", "wblock3", "wblock4"]
        side = 1.0 if w.get("outside", "left") == "left" else -1.0
        trim = 0.18 * IN                                      # tumbled: a hair short so the joints read
        def course_count(x, y, nx, ny):
            g_out = self.g(x + nx * bd, y + ny * bd)
            z_top = float(top) if top is not None else g_out + float(w.get("exposed_in", 3.0)) * IN
            return z_top, max(1, int(math.ceil((z_top - (g_out - bury)) / bh - 1e-6)))
        n_max = 0
        segs = []
        for c_par in (0, 1):
            for k in range(c_par, len(st) - 2, 2):
                (xa, ya), (xb, yb) = st[k], st[k + 2]
                L = math.hypot(xb - xa, yb - ya)
                if L < 0.3 * bl:
                    continue
                ux, uy = (xb - xa) / L, (yb - ya) / L
                nx, ny = -uy * side, ux * side
                mx, my = (xa + xb) / 2, (ya + yb) / 2
                z_top, n_c = course_count(mx, my, nx, ny)
                segs.append((c_par, xa, ya, xb, yb, ux, uy, nx, ny, z_top, n_c))
        for c_par, xa, ya, xb, yb, ux, uy, nx, ny, z_top, n_c in segs:
            for c in range(c_par, n_c, 2):                    # course c (0 = top) uses the stations of its parity
                zc1 = z_top - c * bh
                zc0 = zc1 - bh + 0.015
                off = setback * c                             # lower courses step out
                cxa, cya = xa + nx * (off - bd / 2), ya + ny * (off - bd / 2)
                cxb, cyb = xb + nx * (off - bd / 2), yb + ny * (off - bd / 2)
                mat = mats[self.rng.randrange(len(mats))]
                self.rot("wblock", cxa + ux * trim, cya + uy * trim, cxb - ux * trim, cyb - uy * trim, zc0, zc1, mat, 0, bd, tag=w.get("name", "wall block"))

    def walls(self):
        for w in self.m.get("walls", []):
            self.wall(w)

    # ---------------------------------------------------------- brick paver bands
    def pavers(self):
        for p in self.m.get("pavers", []):
            path = [tuple(q[:2]) for q in p["path"]]
            wd = float(p.get("width_in", 16)) * IN
            side = 1.0 if p.get("side", "left") == "left" else -1.0
            lift = float(p.get("lift", 0.03))
            # offset polyline (mitred) for the outer edge
            def nrm(a, b):
                L = math.hypot(b[0] - a[0], b[1] - a[1]); return (-(b[1] - a[1]) / L * side, (b[0] - a[0]) / L * side)
            outer = []
            for i, q in enumerate(path):
                if i == 0:
                    n_ = nrm(path[0], path[1]); outer.append((q[0] + n_[0] * wd, q[1] + n_[1] * wd))
                elif i == len(path) - 1:
                    n_ = nrm(path[-2], path[-1]); outer.append((q[0] + n_[0] * wd, q[1] + n_[1] * wd))
                else:
                    n1, n2 = nrm(path[i - 1], q), nrm(q, path[i + 1])
                    bx, by = n1[0] + n2[0], n1[1] + n2[1]; bl_ = math.hypot(bx, by)
                    cosh = (n1[0] * bx + n1[1] * by) / bl_
                    outer.append((q[0] + bx / bl_ * wd / cosh, q[1] + by / bl_ * wd / cosh))
            poly = path + outer[::-1]
            self.flat(poly, 0.0, "paver", "paver", tag=p.get("name", "brick paver border"), lift=lift, follow=True)

    # ---------------------------------------------------------- flagstones
    def flagstones(self):
        for k, f in enumerate(self.m.get("flagstones", [])):
            x, y = f["at"]; a, b = f.get("size", [3.0, 2.2]); th = math.radians(f.get("rot", 0.0))
            n = 9
            pts = []
            for i in range(n):
                t = 2 * math.pi * i / n
                r = 1.0 + self.rng.uniform(-0.12, 0.08)
                px, py = a / 2 * r * math.cos(t), b / 2 * r * math.sin(t)
                pts.append((x + px * math.cos(th) - py * math.sin(th), y + px * math.sin(th) + py * math.cos(th)))
            self.flat(pts, 0.0, "flag" if k % 2 == 0 else "flag2", "stone", tag="flagstone", lift=0.06, follow=True)

    # ---------------------------------------------------------- plants
    def tree(self, t: dict):
        x, y = t["at"]
        z0 = self.g(x, y) if t.get("z") is None else float(t["z"])
        kind = t.get("type", "deciduous")
        if kind == "spruce":
            H = float(t.get("height", 28)); R = float(t.get("radius", 7))
            self.tube([x, y, z0 - 0.2], [x, y, z0 + H * 0.9], 0.45, 0.08, "bark", tag="spruce trunk")
            n = int(t.get("tiers", 6))
            for i in range(n):
                zb = z0 + 1.0 + i * (H - 2.0) / n * 0.95
                r = R * (1.0 - i / (n + 0.6)) * self.rng.uniform(0.94, 1.04)
                h = (H - 1.0) / n * 1.9
                self.add("tree", x - r, x + r, y - r, y + r, zb, zb + h, "spruce" if i % 2 else "spruce2", 0, tag="spruce", shape="cone")
            return
        if kind == "shrub":
            r = float(t.get("radius", 2.0)); h = float(t.get("height", 3.5))
            for i in range(int(t.get("lobes", 3))):
                ox, oy = self.rng.uniform(-r * 0.35, r * 0.35), self.rng.uniform(-r * 0.35, r * 0.35)
                rr = r * self.rng.uniform(0.6, 0.85)
                self.add("tree", x + ox - rr, x + ox + rr, y + oy - rr, y + oy + rr, z0 - 0.1, z0 + h * self.rng.uniform(0.8, 1.0),
                         t.get("mat", "shrub") if i % 2 == 0 else t.get("mat2", t.get("mat", "shrub")), 0, tag=t.get("name", "shrub"), shape="sphere")
            return
        # deciduous, multi-stem: stems lean out from the base, the canopy is a cluster of overlapping blobs
        H = float(t.get("height", 20)); R = float(t.get("radius", 7)); stems = int(t.get("stems", 1))
        zc = z0 + float(t.get("crown_base", H * 0.35))
        tops = []
        for s in range(stems):
            a = 2 * math.pi * s / stems + self.rng.uniform(-0.4, 0.4)
            lean = (R * 0.45 if stems > 1 else 0.0) * self.rng.uniform(0.7, 1.1)
            lx_, ly_ = (float(v) for v in t.get("lean", [0.0, 0.0]))
            tx, ty = x + lx_ * 0.8 + lean * math.cos(a), y + ly_ * 0.8 + lean * math.sin(a)
            tz = z0 + H * self.rng.uniform(0.72, 0.85)
            r0 = float(t.get("stem_r", 0.22)) * (1.0 if stems == 1 else 0.7)
            self.tube([x + 0.15 * math.cos(a), y + 0.15 * math.sin(a), z0 - 0.2], [tx, ty, tz], r0, r0 * 0.35, "bark", tag="tree stem")
            tops.append((tx, ty, tz))
        n_blob = int(t.get("blobs", 9))
        cz = zc + (H - (zc - z0)) * 0.5
        lx, ly = (float(v) for v in t.get("lean", [0.0, 0.0]))     # the crown's centre off the trunk (a tree leaning off a wall)
        for i in range(n_blob):
            a = 2 * math.pi * i / n_blob + self.rng.uniform(-0.3, 0.3)
            rr = R * self.rng.uniform(0.45, 0.75)
            dd = R * self.rng.uniform(0.25, 0.55)
            bx, by = x + lx + dd * math.cos(a), y + ly + dd * math.sin(a)
            bz = cz + self.rng.uniform(-0.25, 0.3) * (H - (zc - z0))
            hz = rr * self.rng.uniform(0.8, 1.1)
            self.add("tree", bx - rr, bx + rr, by - rr, by + rr, bz - hz, bz + hz, "leaf" if i % 3 else "leaf2", 0, tag=t.get("name", "tree canopy"), shape="sphere")
        self.add("tree", x + lx - R * 0.55, x + lx + R * 0.55, y + ly - R * 0.55, y + ly + R * 0.55, cz + 0.2 * H - R * 0.5, cz + 0.2 * H + R * 0.5, "leaf", 0, tag="tree canopy top", shape="sphere")

    def plants(self):
        for t in self.m.get("trees", []):
            self.tree(t)

    # ---------------------------------------------------------- cedar privacy fence
    def fences(self):
        for f in self.m.get("fences", []):
            path = [tuple(q[:2]) for q in f["path"]]
            Hf = float(f.get("height", 6.0))
            pk = 5.5 * IN
            for (xa, ya), (xb, yb) in zip(path, path[1:]):
                L = math.hypot(xb - xa, yb - ya)
                if L < 0.1:
                    continue
                ux, uy = (xb - xa) / L, (yb - ya) / L
                nx, ny = -uy, ux
                side = 1.0 if f.get("face", "left") == "left" else -1.0
                # posts at 8' max
                nb = max(1, int(math.ceil(L / 8.0)))
                for i in range(nb + 1):
                    px, py = xa + ux * L * i / nb, ya + uy * L * i / nb
                    gz = self.g(px, py)
                    self.rot("fence", px - ux * 1.75 * IN, py - uy * 1.75 * IN, px + ux * 1.75 * IN, py + uy * 1.75 * IN,
                             gz - 0.3, gz + Hf + 0.25, "cedar", 0, 3.5 * IN, tag="fence post 4x4")
                # rails on the back side, pickets on the face side
                for zr in (0.7, Hf / 2 + 0.2, Hf - 0.6):
                    gz = min(self.g(xa, ya), self.g(xb, yb))
                    off = -side * (1.75 + 0.75) * IN
                    self.rot("fence", xa + nx * off, ya + ny * off, xb + nx * off, yb + ny * off,
                             gz + zr, gz + zr + 3.5 * IN, "cedar", 0, 1.5 * IN, tag="fence rail 2x4")
                npk = int(L / (pk + 0.12 * IN))
                off = side * (1.75 + 0.3) * IN
                for i in range(npk):
                    s0 = i * (pk + 0.12 * IN)
                    qx, qy = xa + ux * (s0 + pk / 2), ya + uy * (s0 + pk / 2)
                    gz = self.g(qx, qy)
                    tone = self.rng.uniform(-1, 1)
                    self.rot("fence", xa + ux * s0 + nx * off, ya + uy * s0 + ny * off, xa + ux * (s0 + pk) + nx * off, ya + uy * (s0 + pk) + ny * off,
                             gz + 0.12, gz + Hf + 0.1 * self.rng.uniform(-0.2, 0.2), "cedar", 0, 0.6 * IN, tag="fence picket 1x6", tone=tone)

    # ---------------------------------------------------------- neighbours (massing)
    def neighbours(self):
        for nb in self.m.get("neighbours", []):
            x0, x1, y0, y1 = nb["rect"]
            ze, zr = float(nb.get("eave", 19.0)), float(nb.get("ridge", 26.0))
            zg = float(nb.get("z", self.g((x0 + x1) / 2, (y0 + y1) / 2)))
            mat = nb.get("mat", "nsiding")
            self.add("house", x0, x1, y0, y1, zg - 0.5, ze, mat, 0, tag=nb.get("name", "neighbour house"))
            # windows on the face toward the deck: dark glass in white trim
            for w in nb.get("windows", []):
                fx0, fx1, fy0, fy1, wz0, wz1 = w
                self.add("trim", fx0 - 0.25, fx1 + 0.25, fy0 - 0.02, fy1 + 0.02, wz0 - 0.25, wz1 + 0.25, nb.get("trim_mat", "ntrim"), 0, tag="neighbour window trim")
                self.add("glass", fx0, fx1, fy0 - 0.05, fy1 + 0.05, wz0, wz1, "nglass", 0, tag="neighbour window")
            ax = nb.get("axis", "x")
            th = 0.4
            if ax == "x":                       # ridge along x at the middle of y
                ym = (y0 + y1) / 2
                for ya, yb, za, zb in ((y0 - 1.2, ym, ze - 0.4, zr), (ym, y1 + 1.2, zr, ze - 0.4)):
                    quad = [[x0 - 1.2, ya, za + th], [x1 + 1.2, ya, za + th], [x1 + 1.2, yb, zb + th], [x0 - 1.2, ya, za + th], [x1 + 1.2, yb, zb + th], [x0 - 1.2, yb, zb + th]]
                    self.mesh("roof", quad, nb.get("roof_mat", "nroof"), tag="neighbour roof")
                for xe in (x0, x1):
                    self.mesh("house", [[xe, y0, ze], [xe, y1, ze], [xe, ym, zr]], mat, tag="neighbour gable")
            else:
                xm = (x0 + x1) / 2
                for xa, xb, za, zb in ((x0 - 1.2, xm, ze - 0.4, zr), (xm, x1 + 1.2, zr, ze - 0.4)):
                    quad = [[xa, y0 - 1.2, za + th], [xb, y0 - 1.2, zb + th], [xb, y1 + 1.2, zb + th], [xa, y0 - 1.2, za + th], [xb, y1 + 1.2, zb + th], [xa, y1 + 1.2, za + th]]
                    self.mesh("roof", quad, nb.get("roof_mat", "nroof"), tag="neighbour roof")
                for ye in (y0, y1):
                    self.mesh("house", [[x0, ye, ze], [x1, ye, ze], [xm, ye, zr]], mat, tag="neighbour gable")


def neighbour_materials(model: dict) -> Dict[str, dict]:
    out = {}
    for i, nb in enumerate(model.get("neighbours", [])):
        out[nb.get("mat", "nsiding")] = dict(color=nb.get("siding", "#8a8f96"), pattern="lap", rough=0.9)
        out[nb.get("roof_mat", "nroof")] = dict(color=nb.get("roof", "#5d5853"), pattern="shingle", rough=0.95)
        out[nb.get("trim_mat", "ntrim")] = dict(color=nb.get("trim", "#efece4"), rough=0.7)
    out.setdefault("nglass", dict(color="#3a4652", metal=0.3, rough=0.1))
    return out


def build_site(model: dict, add: Callable, rot_box: Callable, add_mesh: Callable, zt: float) -> None:
    s = _Site(model, add, rot_box, add_mesh, zt)
    s.lawn()
    s.beds()
    s.pavers()
    s.walls()
    s.flagstones()
    s.plants()
    s.fences()
    s.neighbours()


def grade_at(model: dict, x: float, y: float) -> float:
    return Grade(model.get("grade", {}).get("points", [[0, 0, 0]]))(x, y)
