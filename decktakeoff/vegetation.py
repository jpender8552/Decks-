"""Procedural trees and shrubs for the photoreal renderer (cycles.py), built from the yard model's tree entries
(geometry.site_model.trees: type, at, height, radius, crown_base, stems, stem_r, lean, mats, name).

landscape.py draws every crown as spheres and cones - fine for the plan viewer, topiary in a photograph. Here:
- deciduous trees (maple, cottonwoods): a branch skeleton grown by space colonisation (Runions et al. 2007) into an
  irregular, lobed crown envelope, the pipe model for the limb radii, leaf-cluster cards at the twig ends - an open,
  irregular crown with sky through it;
- Colorado blue spruce: whorls of drooping branches on a narrow cone, needle sprays along every branch, a dark core;
- pines: fewer, longer, upswept whorled limbs with needle tufts at their ends;
- shrubs: multi-stem bushes (space colonisation in a mound); junipers: dense mounds of scale-leaf sprays.
Everything is numpy arrays in the plan frame (x along the wall, y into the yard, z up, feet): per material key a list
of (V (n,3), Q (m,4) quads wound by the right-hand rule outward, UV per loop (4m,2), COL per loop (4m,4)). The card
textures (alpha cut-outs) are drawn here too. No bpy: cycles.py turns the arrays into meshes."""
from __future__ import annotations

import hashlib
import math
import os
from typing import Callable, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

Part = Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


# ====================================================================== textures
def _rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def _leaf_poly(shape: str, L: float, W: float, n: int = 28) -> List[Tuple[float, float]]:
    """A leaf outline from its petiole (0, 0) toward +x, length L, width W."""
    pts = []
    for t in np.linspace(0, 1, n):
        if shape == "deltoid":          # cottonwood: a broad triangle, flat-ish base, long tip
            w = W * (0.9 * (t / 0.28) ** 0.7 if t < 0.28 else 0.9 * (1 - (t - 0.28) / 0.72) ** 1.15)
        elif shape == "palmate":        # maple: a lobed round leaf
            w = W * (math.sin(math.pi * t) ** 0.6) * (0.78 + 0.22 * abs(math.cos(t * math.pi * 2.5)))
        elif shape == "lance":          # sumac leaflets
            w = W * 0.55 * math.sin(math.pi * t) ** 0.9
        else:                           # ovate
            w = W * math.sin(math.pi * t ** 0.85) ** 0.8
        pts.append((t * L, w / 2))
    return pts + [(x, -y) for x, y in reversed(pts)]


def leaf_atlas(path: str, shape: str, c1: str, c2: str, seed: int = 1, S: int = 512) -> str:
    """A 2x2 atlas of leaf clusters (S px tiles, transparent): a forked twig with 8-14 leaves on petioles, each leaf a
    tone between c1 and c2 (some darker, some lighter: sun and shade, top and underside), a lighter midrib."""
    if os.path.exists(path):
        return path
    rng = np.random.default_rng(seed)
    A = Image.new("RGBA", (2 * S, 2 * S), (0, 0, 0, 0))
    a, b = _rgb(c1), _rgb(c2)
    for tile in range(4):
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        twig = (92, 74, 58, 255)
        x0, y0 = S * 0.08, S * (0.5 + rng.uniform(-0.08, 0.08))
        ang0 = rng.uniform(-0.25, 0.25)
        stems = [((x0, y0), ang0, S * 0.8)]
        for _ in range(2):                                   # two side forks
            t = rng.uniform(0.25, 0.6)
            sx, sy = x0 + math.cos(ang0) * S * 0.8 * t, y0 + math.sin(ang0) * S * 0.8 * t
            stems.append(((sx, sy), ang0 + rng.choice([-1, 1]) * rng.uniform(0.5, 0.9), S * rng.uniform(0.3, 0.45)))
        leaves = []
        for (sx, sy), ang, L in stems:
            ex, ey = sx + math.cos(ang) * L, sy + math.sin(ang) * L
            d.line([(sx, sy), (ex, ey)], fill=twig, width=max(2, S // 140))
            nl = int(rng.integers(3, 6))
            for k in range(nl):
                t = 0.3 + 0.7 * (k + rng.uniform(0, 0.8)) / nl
                px, py = sx + math.cos(ang) * L * t, sy + math.sin(ang) * L * t
                side = 1 if k % 2 else -1
                la = ang + side * rng.uniform(0.5, 1.2)
                if k == nl - 1:
                    la = ang + rng.uniform(-0.2, 0.2)
                leaves.append((px, py, la))
        rng.shuffle(leaves)
        for px, py, la in leaves:
            pet = S * rng.uniform(0.03, 0.07) * (2.0 if shape == "deltoid" else 1.0)
            qx, qy = px + math.cos(la) * pet, py + math.sin(la) * pet
            d.line([(px, py), (qx, qy)], fill=twig, width=max(1, S // 220))
            Ll = S * rng.uniform(0.17, 0.25) * (0.8 if shape == "lance" else 1.0)
            Wl = Ll * {"deltoid": 0.95, "palmate": 1.0, "lance": 0.5}.get(shape, 0.62)
            rot = la + rng.uniform(-0.2, 0.2)
            cr, sr = math.cos(rot), math.sin(rot)
            poly = [(qx + x * cr - y * sr, qy + x * sr + y * cr) for x, y in _leaf_poly(shape, Ll, Wl)]
            m = rng.random()
            shade = rng.choice([0.72, 0.85, 1.0, 1.0, 1.08])
            col = np.clip((a * (1 - m) + b * m) * shade, 0, 255)
            d.polygon(poly, fill=tuple(int(v) for v in col) + (255,))
            # the half away from the light a touch darker (the leaf's fold), a lighter midrib
            half = [(qx, qy)] + [(qx + x * cr - y * sr, qy + x * sr + y * cr) for x, y in _leaf_poly(shape, Ll, Wl)[:28]]
            d.polygon(half, fill=tuple(int(v) for v in col * 0.9) + (255,))
            d.line([(qx, qy), (qx + Ll * 0.92 * cr, qy + Ll * 0.92 * sr)], fill=tuple(int(min(255, v * 1.18)) for v in col) + (255,), width=max(1, S // 300))
        im = im.filter(ImageFilter.SMOOTH)
        A.paste(im, ((tile % 2) * S, (tile // 2) * S))
    A.save(path)
    return path


def spray_tex(path: str, c1: str, c2: str, seed: int = 3, W: int = 512, H: int = 256, scale_leaf: bool = False) -> str:
    """A spruce branchlet (W x H, transparent): a twig along +u with side shoots, dense short stiff needles all round
    (foreshortened), blue-green with silvery lights; scale_leaf: a juniper's soft scale-leaf spray instead."""
    if os.path.exists(path):
        return path
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    a, b = _rgb(c1), _rgb(c2)
    cy = H / 2
    axes = [((8, cy), 0.0, W - 20)]
    for k in range(7):
        t = 0.12 + 0.12 * k + rng.uniform(-0.03, 0.03)
        side = 1 if k % 2 else -1
        axes.append(((8 + t * (W - 20), cy), side * rng.uniform(0.6, 0.95), (W - 20) * (1 - t) * rng.uniform(0.35, 0.55)))
    for (sx, sy), ang, L in axes:
        ex, ey = sx + math.cos(ang) * L, sy + math.sin(ang) * L
        d.line([(sx, sy), (ex, ey)], fill=(88, 72, 56, 255), width=3 if L > W * 0.5 else 2)
        n = int(L * (1.6 if scale_leaf else 2.4))
        for _ in range(n):
            t = rng.uniform(0.02, 1.0)
            px, py = sx + math.cos(ang) * L * t, sy + math.sin(ang) * L * t
            taper = 1.0 - 0.55 * t
            if scale_leaf:
                r = rng.uniform(3, 7) * taper
                m = rng.random(); col = np.clip((a * (1 - m) + b * m) * rng.uniform(0.75, 1.12), 0, 255)
                d.ellipse([px - r, py - r * 0.7, px + r, py + r * 0.7], fill=tuple(int(v) for v in col) + (255,))
                continue
            na = ang + rng.choice([-1, 1]) * rng.uniform(0.35, 1.4) + rng.uniform(-0.2, 0.2)
            nl = rng.uniform(9, 17) * taper * (1.0 if L > W * 0.5 else 0.85)
            qx, qy = px + math.cos(na) * nl, py + math.sin(na) * nl
            m = rng.random()
            col = (a * (1 - m) + b * m) * rng.uniform(0.7, 1.15)
            if rng.random() < 0.12:
                col = col * 0.6 + np.array([200, 214, 216]) * 0.4          # the glaucous wax catching light
            d.line([(px, py), (qx, qy)], fill=tuple(int(v) for v in np.clip(col, 0, 255)) + (255,), width=2)
    im.save(path)
    return path


def tuft_tex(path: str, c1: str, c2: str, seed: int = 5, S: int = 512) -> str:
    """A pine needle tuft seen from the side (S x S, transparent): long needles fanning forward from a short twig end
    at the left-centre, darker toward the twig."""
    if os.path.exists(path):
        return path
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    a, b = _rgb(c1), _rgb(c2)
    ox, oy = S * 0.12, S * 0.5
    d.line([(0, oy + 6), (ox + S * 0.25, oy)], fill=(96, 70, 48, 255), width=7)
    for _ in range(420):
        t = rng.uniform(0.0, 0.32)
        px, py = ox + t * S, oy + rng.uniform(-3, 3)
        ang = rng.normal(0, 0.55)
        L = S * rng.uniform(0.3, 0.55) * (1 - 0.5 * abs(ang) / 1.6)
        qx, qy = px + math.cos(ang) * L, py + math.sin(ang) * L
        m = rng.random()
        col = np.clip((a * (1 - m) + b * m) * rng.uniform(0.7, 1.15), 0, 255)
        d.line([(px, py), ((px + qx) / 2 + rng.uniform(-4, 4), (py + qy) / 2 + rng.uniform(-4, 4)), (qx, qy)],
               fill=tuple(int(v) for v in col) + (255,), width=2)
    im.save(path)
    return path


# ====================================================================== geometry helpers
def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def tubes(p0, p1, r0, r1, k: int, tint=(1.0, 1.0, 1.0, 1.0)) -> Part:
    """Tapered k-sided prisms p0 -> p1 (arrays (m,3), radii (m,)), outward quads; UV: u round the stem, v along it (ft)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    m = len(p0)
    d = p1 - p0
    L = np.maximum(np.linalg.norm(d, axis=1), 1e-6)
    d = d / L[:, None]
    up = np.where(np.abs(d[:, 2:3]) > 0.9, np.array([[1.0, 0, 0]]), np.array([[0, 0, 1.0]]))
    e1 = _unit(np.cross(d, up)); e2 = np.cross(d, e1)
    ang = 2 * math.pi * np.arange(k) / k
    cs, sn = np.cos(ang)[None, :, None], np.sin(ang)[None, :, None]
    ring = cs * e1[:, None, :] + sn * e2[:, None, :]
    R0 = p0[:, None, :] + np.asarray(r0, float)[:, None, None] * ring
    R1 = p1[:, None, :] + np.asarray(r1, float)[:, None, None] * ring
    V = np.concatenate([R0, R1], axis=1).reshape(-1, 3)
    base = (np.arange(m) * 2 * k)[:, None]
    j = np.arange(k)[None, :]
    jn = (j + 1) % k
    Q = np.stack([base + j, base + jn, base + k + jn, base + k + j], axis=-1).reshape(-1, 4)
    u0 = np.broadcast_to(j / k, (m, k)); u1 = np.broadcast_to((j + 1) / k, (m, k))
    v1 = np.broadcast_to(L[:, None], (m, k))
    UV = np.stack([np.stack([u0, np.zeros_like(u0)], -1), np.stack([u1, np.zeros_like(u1)], -1),
                   np.stack([u1, v1], -1), np.stack([u0, v1], -1)], axis=2).reshape(-1, 2)
    COL = np.tile(np.asarray(tint, float), (len(Q) * 4, 1))
    return V, Q, UV, COL


def cards(C, N, T, w, h, tiles, tint) -> Part:
    """Quads centred at C (n,3) facing N, long axis T (unit, normal to N), width w along T, height h; tiles (n,4) =
    (u0, v0, du, dv) of the texture each card shows; tint (n,4) per card."""
    C, N, T = (np.asarray(x, float) for x in (C, N, T))
    Bv = _unit(np.cross(N, T))
    T = _unit(np.cross(Bv, N))
    a = T * (np.asarray(w, float)[:, None] / 2); b = Bv * (np.asarray(h, float)[:, None] / 2)
    V = np.stack([C - a - b, C + a - b, C + a + b, C - a + b], axis=1).reshape(-1, 3)
    n = len(C)
    Q = np.arange(4 * n).reshape(n, 4)
    tl = np.asarray(tiles, float)
    u0, v0, du, dv = tl[:, 0], tl[:, 1], tl[:, 2], tl[:, 3]
    UV = np.stack([np.stack([u0, v0], -1), np.stack([u0 + du, v0], -1), np.stack([u0 + du, v0 + dv], -1),
                   np.stack([u0, v0 + dv], -1)], axis=1).reshape(-1, 2)
    COL = np.repeat(np.asarray(tint, float), 4, axis=0)
    return V, Q, UV, COL


def _rand_perp(N, rng):
    r = rng.normal(size=N.shape)
    return _unit(np.cross(N, r))


def _atlas_tiles(n, rng):
    k = rng.integers(0, 4, n)
    return np.stack([(k % 2) * 0.5, (k // 2) * 0.5, np.full(n, 0.5), np.full(n, 0.5)], 1)


def _tints(n, rng, dark, spread=0.1, warm=0.04):
    """Per-card tint: brightness (1 - dark: deeper in the crown is darker) with a little per-card hue drift."""
    v = (1.0 - dark) * rng.uniform(1 - spread, 1 + spread, n)
    h = rng.uniform(-warm, warm, n)
    return np.stack([v * (1 + h), v, v * (1 - h), np.ones(n)], 1)


# ====================================================================== space colonisation
def colonise(rng, trunks: List[np.ndarray], A: np.ndarray, D: float, di: float, dk: float, tropism=(0.0, 0.0, 0.1),
             grow_from_z: float = -1e9, max_iter: int = 160, max_nodes: int = 12000):
    """Grow a branch skeleton from the trunk polylines toward the attraction points A. Returns node positions P (n,3),
    parent index (n,) (-1 for a root) and a trunk flag (n,)."""
    P, par, trunk = [], [], []
    for poly in trunks:
        for i, p in enumerate(poly):
            P.append(p); par.append(len(P) - 2 if i else -1); trunk.append(True)
    P = np.array(P, float); par = np.array(par, int); trunk = np.array(trunk, bool)
    nA = len(A)
    alive = np.ones(nA, bool)
    near_d = np.full(nA, np.inf); near_i = np.full(nA, -1)
    kids = np.zeros(len(P), int)
    kid_dir = np.zeros((len(P), 3, 3))
    new_idx = np.nonzero(P[:, 2] >= grow_from_z)[0]
    tro = np.asarray(tropism, float)
    for _ in range(max_iter):
        if new_idx.size:
            ai = np.nonzero(alive)[0]
            if ai.size == 0:
                break
            Pn = P[new_idx]
            for s in range(0, len(ai), 4096):
                aa = ai[s:s + 4096]
                dd = np.linalg.norm(A[aa, None, :] - Pn[None, :, :], axis=2)
                j = dd.argmin(1); dm = dd[np.arange(len(aa)), j]
                upd = dm < near_d[aa]
                near_d[aa[upd]] = dm[upd]; near_i[aa[upd]] = new_idx[j[upd]]
        alive &= ~(near_d < dk)
        act = alive & (near_d < di)
        if not act.any() or len(P) >= max_nodes:
            break
        idx = np.nonzero(act)[0]
        nodes = near_i[idx]
        dirs = _unit(A[idx] - P[nodes])
        uniq, inv = np.unique(nodes, return_inverse=True)
        S = np.zeros((len(uniq), 3)); np.add.at(S, inv, dirs)
        S = _unit(_unit(S) + tro)
        ok = kids[uniq] < 3
        for c in range(3):                                   # no second child the way one already went
            has = kids[uniq] > c
            ok &= ~(has & (np.einsum("ij,ij->i", kid_dir[uniq, c], S) > 0.94))
        uniq, S = uniq[ok], S[ok]
        if not len(uniq):
            break
        newP = P[uniq] + D * S
        c = kids[uniq]
        kid_dir[uniq, np.minimum(c, 2)] = S
        kids[uniq] += 1
        base = len(P)
        P = np.vstack([P, newP]); par = np.concatenate([par, uniq]); trunk = np.concatenate([trunk, np.zeros(len(uniq), bool)])
        kids = np.concatenate([kids, np.zeros(len(uniq), int)])
        kid_dir = np.concatenate([kid_dir, np.zeros((len(uniq), 3, 3))])
        new_idx = np.arange(base, len(P))
    return P, par, trunk


def pipe_radii(par: np.ndarray, r_tip: float, gamma: float = 2.4) -> np.ndarray:
    """Pipe model: a tip has r_tip; a parent r = (sum of children r^gamma)^(1/gamma). Children come after parents."""
    n = len(par)
    acc = np.zeros(n)
    has_kid = np.zeros(n, bool)
    has_kid[par[par >= 0]] = True
    acc[~has_kid] = r_tip ** gamma
    for i in range(n - 1, 0, -1):
        p = par[i]
        if p >= 0:
            acc[p] += acc[i]
    return acc ** (1.0 / gamma)


def smooth_nodes(P, par, fixed, passes=2):
    """Laplacian smoothing along the branches (a node with one child moves toward the mid of its parent and child)."""
    n = len(P)
    child = np.full(n, -1); cnt = np.zeros(n, int)
    for i in range(n):
        p = par[i]
        if p >= 0:
            cnt[p] += 1
            child[p] = i
    m = (~fixed) & (par >= 0) & (cnt == 1)
    idx = np.nonzero(m)[0]
    for _ in range(passes):
        P[idx] = 0.5 * P[idx] + 0.25 * (P[par[idx]] + P[child[idx]])
    return P


# ====================================================================== the plants
class Plants:
    """Collects the parts of every plant by material key. colors(kind) -> (c1, c2) sRGB for a foliage kind."""

    def __init__(self, tex_dir: str, colors: Callable[[str], Tuple[str, str]], seed: int = 17, detail_at=None):
        self.parts: Dict[str, List[Part]] = {}
        self.tex: Dict[str, str] = {}
        self.dir = tex_dir
        self.colors = colors
        self.rng = np.random.default_rng(seed)
        self.detail_at = detail_at or (lambda x, y: 1.0)
        os.makedirs(tex_dir, exist_ok=True)

    def add(self, key: str, part: Part):
        if len(part[1]):
            self.parts.setdefault(key, []).append(part)

    def merged(self) -> Dict[str, Part]:
        out = {}
        for k, ps in self.parts.items():
            off = 0; Vs, Qs, UVs, Cs = [], [], [], []
            for V, Q, UV, C in ps:
                Vs.append(V); Qs.append(Q + off); UVs.append(UV); Cs.append(C); off += len(V)
            out[k] = (np.vstack(Vs), np.vstack(Qs), np.vstack(UVs), np.vstack(Cs))
        return out

    def _texture(self, kind: str, maker, *args) -> str:
        c1, c2 = self.colors(kind)
        h = hashlib.md5(f"{kind}|{c1}|{c2}|v1".encode()).hexdigest()[:8]
        key = f"{kind}"
        if key not in self.tex:
            self.tex[key] = maker(os.path.join(self.dir, f"veg_{kind}_{h}.png"), *args, c1, c2) if args else \
                maker(os.path.join(self.dir, f"veg_{kind}_{h}.png"), c1, c2)
        return key

    # ------------------------------------------------------------------ deciduous
    def deciduous(self, t: dict, z0: float):
        rng = self.rng
        x, y = (float(v) for v in t["at"])
        H = float(t.get("height", 20)); R = float(t.get("radius", 7)); stems = int(t.get("stems", 1))
        cb = float(t.get("crown_base", H * 0.35))
        lx, ly = (float(v) for v in t.get("lean", [0.0, 0.0]))
        name = (t.get("name") or "").lower()
        cotton = "cottonwood" in name
        det = float(self.detail_at(x, y))
        kind = "cottonwood" if cotton else ("maple" if "maple" in name else "broadleaf")
        shape = "deltoid" if cotton else ("palmate" if kind == "maple" else "ovate")
        leafkey = self._texture(kind, lambda p, c1, c2: leaf_atlas(p, shape, c1, c2, seed=11 if cotton else 7))
        zc0, ztop = z0 + cb, z0 + H
        Rz = (ztop - zc0) / 2
        cx, cy, cz = x + lx, y + ly, zc0 + Rz
        # the envelope: a main ellipsoid + lobes on its upper / outer part (an irregular, lobed crown)
        lobes = [(cx, cy, cz, R * 0.78, Rz * 0.85)]
        for k in range(int(rng.integers(6, 10))):
            a = rng.uniform(0, 2 * math.pi); f = rng.uniform(0.35, 0.72)
            zz = cz + Rz * rng.uniform(-0.35, 0.7)
            lobes.append((cx + R * f * math.cos(a), cy + R * f * math.sin(a), zz, R * rng.uniform(0.32, 0.55), Rz * rng.uniform(0.3, 0.5)))
        D = max(0.8, R / 13.0) / max(0.55, det) ** 0.5
        n_att = int(np.clip(math.pi * R * R * Rz * 1.3 / (1.5 * D) ** 3 * (0.6 + 0.4 * det), 400, 4500))
        box = np.array([[cx - R * 1.3, cy - R * 1.3, zc0], [cx + R * 1.3, cy + R * 1.3, ztop]])
        pts = []
        while sum(len(p) for p in pts) < n_att:
            q = box[0] + rng.random((n_att * 3, 3)) * (box[1] - box[0])
            inside = np.zeros(len(q), bool)
            for (ex, ey, ez, er, erz) in lobes:
                inside |= ((q[:, 0] - ex) ** 2 + (q[:, 1] - ey) ** 2) / er ** 2 + (q[:, 2] - ez) ** 2 / erz ** 2 < 1
            inside &= q[:, 2] > zc0 + 0.6
            pts.append(q[inside])
        A = np.vstack(pts)[:n_att]
        # clumping: thin the points in a few random pockets (sky gaps in the crown)
        for _ in range(int(rng.integers(4, 8))):
            pc = A[rng.integers(len(A))]
            A = A[np.linalg.norm(A - pc, axis=1) > R * rng.uniform(0.12, 0.22)]
        trunks = []
        stem_r = float(t.get("stem_r", 0.22 + R * 0.03))
        for s in range(stems):
            a = 2 * math.pi * s / stems + rng.uniform(-0.4, 0.4)
            lean = (R * 0.28 if stems > 1 else 0.0) * rng.uniform(0.7, 1.1)
            top = np.array([x + lx * 0.6 + lean * math.cos(a), y + ly * 0.6 + lean * math.sin(a), zc0 + Rz * 0.25])
            bot = np.array([x + 0.15 * math.cos(a) * (stems > 1), y + 0.15 * math.sin(a) * (stems > 1), z0 - 0.3])
            n = max(3, int(np.linalg.norm(top - bot) / D))
            tt = np.linspace(0, 1, n + 1)[:, None]
            bend = np.sin(math.pi * tt) * np.array([rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 0.0])
            trunks.append(bot + (top - bot) * tt + bend)
        P, par, trk = colonise(rng, trunks, A, D, di=max(5.0, R * 0.55), dk=1.7 * D,
                               tropism=(0, 0, 0.18 if cotton else 0.1), grow_from_z=zc0 - 1.0)
        r = pipe_radii(par, 0.02)
        roots = np.nonzero(par < 0)[0]
        f = stem_r / max(1e-6, max(r[roots]))
        r = np.maximum(r * f, 0.03)
        P = smooth_nodes(P, par, trk, passes=2)
        self._branches(P, par, r, det, tint=(0.95, 0.93, 0.9, 1) if cotton else (1, 1, 1, 1))
        # leaves: cluster cards at the thin ends
        thin = (r < 0.03 * f * 2.6 + 0.02) & ~trk
        tips = np.nonzero(thin)[0]
        crown_area = math.pi * R * R
        card = (1.25 if R > 9 else 1.0) / max(0.6, det) ** 0.35
        n_cards = int(3.6 * crown_area * (0.7 + 0.3 * det) / (card * card * 0.42))
        if not len(tips):
            return
        pick = tips[rng.integers(0, len(tips), n_cards)]
        C = P[pick] + rng.normal(0, 0.45 * D, (n_cards, 3))
        out = _unit(np.c_[C[:, 0] - cx, C[:, 1] - cy, (C[:, 2] - cz) * 0.6])
        Nn = _unit(rng.normal(size=(n_cards, 3)) + 0.7 * out + np.array([0, 0, 0.55]))
        T = _rand_perp(Nn, rng)
        s = card * rng.uniform(0.75, 1.25, n_cards)
        depth = np.clip(1 - np.sqrt(((C[:, 0] - cx) ** 2 + (C[:, 1] - cy) ** 2) / R ** 2 + ((C[:, 2] - cz) / Rz) ** 2), 0, 1)
        self.add(f"leaf:{leafkey}", cards(C, Nn, T, s, s, _atlas_tiles(n_cards, rng), _tints(n_cards, rng, 0.35 * depth)))

    def _branches(self, P, par, r, det, tint=(1, 1, 1, 1), key="bark"):
        i = np.nonzero(par >= 0)[0]
        p = par[i]
        rmin = 0.035 if det > 0.7 else 0.06
        for lo, hi, k in ((rmin, 0.12, 4), (0.12, 0.35, 6), (0.35, 99, 9)):
            m = (r[i] >= lo) & (r[i] < hi)
            if m.any():
                self.add(key, tubes(P[p[m]], P[i[m]], r[p[m]] * 0.98, r[i[m]], k, tint))

    # ------------------------------------------------------------------ spruce
    def spruce(self, t: dict, z0: float):
        rng = self.rng
        x, y = (float(v) for v in t["at"])
        H = float(t.get("height", 28)); R = float(t.get("radius", 7)); cb = float(t.get("crown_base", 1.0))
        det = float(self.detail_at(x, y))
        key = self._texture("spruce", lambda p, c1, c2: spray_tex(p, c1, c2, seed=3))
        ztop = z0 + H
        self.add("bark", tubes([[x, y, z0 - 0.3]], [[x, y, ztop - 0.3]], [0.5 * R / 9], [0.06], 8, (0.85, 0.85, 0.85, 1)))
        Cs, Ns, Ts, Ws, Hs, Ds = [], [], [], [], [], []
        seg0, seg1, rr0, rr1 = [], [], [], []
        z = z0 + cb
        k0 = rng.uniform(0, 6.28)
        dz = 0.95 / max(0.6, det) ** 0.5
        wi = 0
        core_r = []
        while z < ztop - 0.6:
            f = (z - z0 - cb) / max(1.0, H - cb)                      # 0 at the lowest whorl, 1 at the top
            Rz = R * (1.0 - f) ** 0.92 + 0.35
            core_r.append((z, Rz))
            nb = int(rng.integers(5, 8))
            for b in range(nb):
                az = k0 + wi * 2.39996 + 2 * math.pi * b / nb + rng.uniform(-0.25, 0.25)
                L = Rz * rng.uniform(0.82, 1.08)
                if L < 0.4:
                    continue
                e0 = math.radians(-14 + 44 * f ** 1.4 + rng.uniform(-6, 6))
                droop = math.radians(16 * (1 - f) + rng.uniform(-4, 4))
                ca, sa = math.cos(az), math.sin(az)
                ns = 6
                tt = np.linspace(0, 1, ns + 1)
                el = e0 - droop * tt ** 1.6 + math.radians(10) * np.clip((tt - 0.8) / 0.2, 0, 1)
                stepL = L / ns
                pts = [np.array([x + 0.25 * ca, y + 0.25 * sa, z])]
                for j in range(ns):
                    e = el[j]
                    pts.append(pts[-1] + stepL * np.array([math.cos(e) * ca, math.cos(e) * sa, math.sin(e)]))
                pts = np.array(pts)
                br = 0.025 + 0.06 * L / max(R, 1)
                seg0 += list(pts[:-1]); seg1 += list(pts[1:]); rr0 += list(np.linspace(br, 0.012, ns + 1)[:-1]); rr1 += list(np.linspace(br, 0.012, ns + 1)[1:])
                # sprays along the branch, both sides, alternating, from 15% out; and a terminal one
                ns_ = max(2, int(L * 5.0 * min(1.0, det + 0.25)))
                ts = np.sort(rng.uniform(0.15, 1.0, ns_))
                bp = np.array([np.interp(ts, tt, pts[:, c]) for c in range(3)]).T
                fwd = _unit(np.gradient(bp, axis=0) + 1e-6) if len(bp) > 1 else np.array([[ca, sa, 0.0]])
                side = np.where(np.arange(ns_) % 2 == 0, 1.0, -1.0)
                lat = _unit(np.cross(fwd, np.array([0, 0, 1.0])) * side[:, None])
                spread = rng.uniform(0.6, 1.1, ns_)[:, None]
                dirn = _unit(fwd * np.cos(spread) + lat * np.sin(spread) + np.array([0, 0, -0.25]) * (1 - f))
                size = (0.75 + 0.55 * rng.random(ns_)) * (0.55 + 0.45 * min(1.0, L / 3.0)) / max(0.6, det) ** 0.3
                nrm = _unit(np.array([0, 0, 1.0]) + rng.normal(0, 0.35, (ns_, 3)) - 0.3 * dirn)
                Cs.append(bp + dirn * size[:, None] * 0.5); Ns.append(nrm); Ts.append(dirn); Ws.append(size); Hs.append(size * 0.5)
                Ds.append(np.clip(1 - ts, 0, 1) * 0.35 + 0.1)
                # curtain: a few hanging sprays under the outer half (the dense skirt of a blue spruce)
                nc = max(1, ns_ // 3)
                tc = rng.uniform(0.45, 1.0, nc)
                cp = np.array([np.interp(tc, tt, pts[:, c]) for c in range(3)]).T
                dn = _unit(np.array([ca, sa, 0.0]) * 0.55 + np.array([0, 0, -1.0]) + rng.normal(0, 0.2, (nc, 3)))
                sz = (0.6 + 0.4 * rng.random(nc)) / max(0.6, det) ** 0.3
                Cs.append(cp + dn * sz[:, None] * 0.5); Ns.append(_unit(np.cross(dn, np.array([0, 0, 1.0])) + rng.normal(0, 0.3, (nc, 3))))
                Ts.append(dn); Ws.append(sz); Hs.append(sz * 0.5); Ds.append(np.full(nc, 0.25))
            z += dz * rng.uniform(0.85, 1.15)
            wi += 1
        # the leader
        lp = np.array([[x, y, ztop - 1.6 + 0.4 * j] for j in range(4)])
        Cs.append(lp + np.array([0, 0, 0.3])); Ns.append(_unit(rng.normal(size=(4, 3)) * np.array([1, 1, 0.2]))); Ts.append(np.tile([0, 0, 1.0], (4, 1)))
        Ws.append(np.full(4, 0.9)); Hs.append(np.full(4, 0.45)); Ds.append(np.zeros(4))
        self.add("bark", tubes(np.array(seg0), np.array(seg1), np.array(rr0), np.array(rr1), 4, (0.8, 0.8, 0.8, 1)))
        C = np.vstack(Cs); n = len(C)
        tiles = np.tile([0.0, 0.0, 1.0, 1.0], (n, 1))
        self.add(f"spray:{key}", cards(C, np.vstack(Ns), np.vstack(Ts), np.concatenate(Ws), np.concatenate(Hs), tiles,
                                       _tints(n, rng, np.concatenate(Ds), spread=0.12, warm=0.03)))
        # the dark core: a cone at ~55% of the crown radius (blocks the see-through a real spruce does not have)
        zs = np.array([c[0] for c in core_r]); rs = np.array([c[1] for c in core_r]) * 0.55
        if len(zs) > 2:
            ring = 12
            a = 2 * math.pi * np.arange(ring) / ring
            prof_z = np.linspace(zs[0], zs[-1], 10); prof_r = np.interp(prof_z, zs, rs)
            V = np.array([[x + rr * math.cos(q), y + rr * math.sin(q), zz] for zz, rr in zip(prof_z, prof_r) for q in a])
            Q = np.array([[i * ring + j, i * ring + (j + 1) % ring, (i + 1) * ring + (j + 1) % ring, (i + 1) * ring + j]
                          for i in range(len(prof_z) - 1) for j in range(ring)])
            self.add("core", (V, Q, np.zeros((len(Q) * 4, 2)), np.ones((len(Q) * 4, 4))))

    # ------------------------------------------------------------------ pine
    def pine(self, t: dict, z0: float):
        rng = self.rng
        x, y = (float(v) for v in t["at"])
        H = float(t.get("height", 35)); R = float(t.get("radius", 9)); cb = float(t.get("crown_base", 4.0))
        det = float(self.detail_at(x, y))
        key = self._texture("pine", lambda p, c1, c2: tuft_tex(p, c1, c2, seed=5))
        ztop = z0 + H
        self.add("bark", tubes([[x, y, z0 - 0.3]], [[x, y, ztop - 0.5]], [float(t.get("stem_r", 0.7))], [0.08], 10, (1.05, 0.88, 0.75, 1)))
        tiers = int(t.get("tiers", 6)) * 2
        seg0, seg1, rr0, rr1 = [], [], [], []
        ends = []
        for i in range(tiers):
            f = i / max(1, tiers - 1)
            z = z0 + cb + (H - cb - 2.0) * f + rng.uniform(-0.4, 0.4)
            prof = (math.sin(math.pi * (0.25 + 0.75 * f)) if f > 0.0 else 0.75) * (1.0 - 0.25 * f)
            Lw = max(1.0, R * 0.95 * prof)
            nb = int(rng.integers(3, 6))
            for b in range(nb):
                az = i * 2.4 + 2 * math.pi * b / nb + rng.uniform(-0.35, 0.35)
                L = Lw * rng.uniform(0.75, 1.1)
                e0 = math.radians(rng.uniform(5, 30) + 20 * f)
                ca, sa = math.cos(az), math.sin(az)
                p0 = np.array([x, y, z])
                mid = p0 + L * 0.55 * np.array([math.cos(e0) * ca, math.cos(e0) * sa, math.sin(e0) - 0.15])
                end = p0 + L * np.array([math.cos(e0) * ca, math.cos(e0) * sa, math.sin(e0) * 0.6 + 0.12])
                br = 0.06 + 0.16 * L / max(R, 1)
                seg0 += [p0, mid]; seg1 += [mid, end]; rr0 += [br, br * 0.6]; rr1 += [br * 0.6, br * 0.25]
                # side shoots off the outer 60%, each ending in a tuft cluster; a cluster at the end
                ends.append((end, np.array([ca, sa, 0.35])))
                for _ in range(int(rng.integers(2, 5))):
                    tt = rng.uniform(0.4, 0.9)
                    sp = p0 + (end - p0) * tt
                    sd = _unit(np.array([ca, sa, 0.0]) + np.array([-sa, ca, 0.0]) * rng.uniform(-1.1, 1.1) + np.array([0, 0, rng.uniform(0.0, 0.6)]))
                    sl = L * rng.uniform(0.2, 0.35)
                    se = sp + sd * sl
                    seg0.append(sp); seg1.append(se); rr0.append(br * 0.3); rr1.append(br * 0.12)
                    ends.append((se, sd))
        self.add("bark", tubes(np.array(seg0), np.array(seg1), np.array(rr0), np.array(rr1), 5, (1.0, 0.85, 0.72, 1)))
        # tufts: each end carries a cluster of crossed tuft cards pointing out and up
        Cs, Ns, Ts, Ws = [], [], [], []
        per = max(4, int(9 * min(1.0, det + 0.2)))
        for e, d in ends:
            d = _unit(d)
            n = per
            off = rng.normal(0, 0.55, (n, 3)) * np.array([1, 1, 0.6])
            base = e + off
            fwd = _unit(np.tile(d, (n, 1)) + rng.normal(0, 0.45, (n, 3)) + np.array([0, 0, 0.35]))
            nr = _rand_perp(fwd, rng)
            s = rng.uniform(1.0, 1.5, n) / max(0.6, det) ** 0.3
            Cs.append(base + fwd * s[:, None] * 0.38); Ns.append(nr); Ts.append(fwd); Ws.append(s)
        C = np.vstack(Cs); n = len(C)
        Wv = np.concatenate(Ws)
        dist = np.sqrt((C[:, 0] - x) ** 2 + (C[:, 1] - y) ** 2) / max(R, 1)
        self.add(f"tuft:{key}", cards(C, np.vstack(Ns), np.vstack(Ts), Wv, Wv, np.tile([0.0, 0.0, 1.0, 1.0], (n, 1)),
                                      _tints(n, rng, 0.3 * np.clip(1 - dist, 0, 1), spread=0.12, warm=0.03)))

    # ------------------------------------------------------------------ shrubs
    def shrub(self, t: dict, z0: float):
        rng = self.rng
        x, y = (float(v) for v in t["at"])
        r = float(t.get("radius", 2.0)); h = float(t.get("height", 3.5))
        name = (t.get("name") or "").lower()
        mat = t.get("mat", "shrub")
        det = float(self.detail_at(x, y))
        if "juniper" in name or mat.startswith("spruce"):
            key = self._texture("juniper", lambda p, c1, c2: spray_tex(p, c1, c2, seed=9, scale_leaf=True))
            n = int(np.clip(math.pi * r * r * h * 9 * (0.6 + 0.4 * det), 120, 2500))
            u = _unit(rng.normal(size=(n, 3)))
            rad = 0.55 + 0.45 * rng.random(n) ** 0.5
            C = np.c_[x + u[:, 0] * rad * r, y + u[:, 1] * rad * r, z0 + np.abs(u[:, 2]) * rad * h * 0.95]
            dirn = _unit(np.c_[u[:, 0], u[:, 1], np.abs(u[:, 2]) * 0.6 + 0.2])
            Nn = _rand_perp(dirn, rng)
            s = rng.uniform(0.7, 1.1, n)
            self.add(f"spray:{key}", cards(C, Nn, dirn, s, s * 0.5, np.tile([0.0, 0.0, 1.0, 1.0], (n, 1)), _tints(n, rng, 0.3 * (1 - rad), 0.1, 0.03)))
            ring = 10
            a = 2 * math.pi * np.arange(ring) / ring
            V = np.array([[x + 0.6 * r * math.cos(q) * math.cos(ph), y + 0.6 * r * math.sin(q) * math.cos(ph), z0 + 0.7 * h * math.sin(ph)]
                          for ph in np.linspace(0, math.pi / 2 * 0.95, 4) for q in a])
            Q = np.array([[i * ring + j, i * ring + (j + 1) % ring, (i + 1) * ring + (j + 1) % ring, (i + 1) * ring + j] for i in range(3) for j in range(ring)])
            self.add("core", (V, Q, np.zeros((len(Q) * 4, 2)), np.ones((len(Q) * 4, 4))))
            return
        kind = "sumac" if "sumac" in name else ("shrub2" if mat in ("leaf", "leaf2") else "shrub")
        shape = "lance" if kind == "sumac" else "ovate"
        leafkey = self._texture(kind, lambda p, c1, c2: leaf_atlas(p, shape, c1, c2, seed=13))
        cz = z0 + h * 0.55
        n_att = int(np.clip(math.pi * r * r * h * 10, 200, 1500))
        q = rng.random((n_att * 4, 3)) * 2 - 1
        q = q[(q ** 2).sum(1) < 1][:n_att]
        A = np.c_[x + q[:, 0] * r, y + q[:, 1] * r, cz + q[:, 2] * h * 0.5]
        A = A[A[:, 2] > z0 + 0.5]
        trunks = []
        for s in range(int(rng.integers(4, 7))):
            a = rng.uniform(0, 2 * math.pi)
            b0 = np.array([x + 0.25 * math.cos(a), y + 0.25 * math.sin(a), z0 - 0.1])
            b1 = b0 + np.array([0.6 * math.cos(a), 0.6 * math.sin(a), h * 0.3])
            trunks.append(np.array([b0, (b0 + b1) / 2, b1]))
        D = max(0.35, r / 7)
        P, par, trk = colonise(rng, trunks, A, D, di=max(1.5, r * 0.8), dk=1.6 * D, tropism=(0, 0, 0.15))
        rr = pipe_radii(par, 0.012)
        rr = np.maximum(rr * (0.06 / max(1e-6, rr[par < 0].max())), 0.012)
        P = smooth_nodes(P, par, trk, 1)
        self._branches(P, par, rr, max(det, 0.8), tint=(0.85, 0.8, 0.75, 1))
        tips = np.nonzero(rr < 0.03)[0]
        if not len(tips):
            tips = np.arange(len(P))
        card = 0.65
        n_cards = int(4.5 * math.pi * r * r * (h / 3.0) ** 0.5 / (card * card * 0.42))
        pick = tips[rng.integers(0, len(tips), n_cards)]
        C = P[pick] + rng.normal(0, 0.35 * D, (n_cards, 3))
        out = _unit(np.c_[C[:, 0] - x, C[:, 1] - y, (C[:, 2] - cz) * 0.8])
        Nn = _unit(rng.normal(size=(n_cards, 3)) + 0.6 * out + np.array([0, 0, 0.5]))
        s = card * rng.uniform(0.75, 1.25, n_cards)
        depth = np.clip(1 - np.sqrt(((C[:, 0] - x) ** 2 + (C[:, 1] - y) ** 2) / r ** 2), 0, 1)
        self.add(f"leaf:{leafkey}", cards(C, Nn, _rand_perp(Nn, rng), s, s, _atlas_tiles(n_cards, rng), _tints(n_cards, rng, 0.3 * depth)))

    def plant(self, t: dict, z0: float):
        kind = t.get("type", "deciduous")
        {"spruce": self.spruce, "pine": self.pine, "shrub": self.shrub}.get(kind, self.deciduous)(t, z0)


def plant_textures(P: Plants) -> Dict[str, str]:
    """texture key -> file path (the keys the parts' material names carry after the ':')."""
    return dict(P.tex)
