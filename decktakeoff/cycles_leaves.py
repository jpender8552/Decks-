"""Fallen autumn leaves for the photoreal renderer (decktakeoff.cycles): late October on the Front Range.

    add_leaves(D, spec, col, tex_dir, rng_seed=29, density=1.0) -> int      (the number of leaves placed)

cycles.build() calls it last (after the plants, before the grass), unless --leaves=0 or --foliage=summer; --leaves=N
scales every count (1.5: a week later, 0.5: early in the fall).

Real leaves, not confetti: photo-scanned fall leaves (ambientCG LeafSet atlases, CC0: elm / green-ash-type leaflets in
yellow, tan, brown and a few still greenish; maples in yellow, orange and red) cut out one leaf per atlas cell, plus
procedural honey locust leaflets (the Front Range's street tree), each on its own curled / cupped mesh (a 9 x 7 grid
with cup, curl, twist and a little random bend, the dry tan and brown ones curled hardest), a few lying underside up
(paler, through the material's Backfacing). The material is a thin leaf: the scan's color x a per-leaf tint (albedo
calibrated to a real leaf's), its normal map (the veins), its roughness (matte to a little waxy), a translucent lobe
(backlit edges glow) and the scan's alpha.

Where they lie (a seeded, deterministic layout; `density` scales every count):
  - a sparse scatter on the deck boards (30 at density 1, clumped, more toward the edges);
  - small drifts against rail posts, the house wall and its inside corners, and against the riser of every step, plus a
    few loose on the treads and box steps;
  - more in the planting beds (mulch, ground cover) and along the lawn's edges (walls, edging, pavers, the stair);
  - a scatter in the lawn, denser under the big tree, nested into the grass.
Every leaf rests ON what is under it: each vertex is ray-cast down onto the scene's own surfaces (deck boards, treads,
mulch, pavers, the lawn), the leaf is set on its lowest opaque point, tilted to a sloped ground, draped over leaves
placed before it (a height map of their opaque parts), some lean on the face they drifted against, and a leaf whose mesh
would touch anything else (posts, balusters, risers, skirts, walls, siding, splash blocks, lights) is thrown out.

Plan feet (x along the house, y into the yard, z up) as in cycles.py; Blender is (x, -y, z). No import of cycles.py
(it may be running as __main__): this module builds its own BVHs from the meshes already in the collection.

Assets (ambientCG LeafSet006/007/008/011/021/027/028, 2K JPG: Color, Opacity, NormalGL, Roughness, Scattering):
$DECK_LEAF_ASSETS, else decktakeoff/data/leaves; without them every leaf is a procedural honey
locust leaflet (a warning is printed). LAST["placed"] keeps the last layout (zone, class, center, rest gap) for checks."""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
import os
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import bpy
import mathutils
from mathutils.bvhtree import BVHTree

__all__ = ["add_leaves"]
LAST: Dict[str, list] = {}       # the last layout, for checks: one dict per leaf (zone, class, center, rest gap, nest)

_HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIRS = [os.environ.get("DECK_LEAF_ASSETS") or "", os.path.join(_HERE, "data", "leaves")]

# the scanned sets (ambientCG, CC0): what grows in a Centennial yard and what it reads as, the long side of a cell (ft:
# blade + petiole), the color class when the whole set is one ("" = per leaf), the roughness range (fresh -> waxier)
ATLASES = {
    "LeafSet007": dict(species="elm", size=(0.27, 0.40), cat="yellow", rough=(0.42, 0.75)),   # golden elm / ash leaflets
    "LeafSet006": dict(species="elm", size=(0.26, 0.38), cat="green", rough=(0.40, 0.72)),    # still greenish, spotted
    "LeafSet008": dict(species="elm", size=(0.25, 0.37), cat="", rough=(0.55, 0.85)),         # tan, dried
    "LeafSet011": dict(species="elm", size=(0.28, 0.40), cat="brown", rough=(0.58, 0.88)),    # brown, dry
    "LeafSet021": dict(species="maple", size=(0.46, 0.60), cat="yellow", rough=(0.45, 0.78)),  # yellow maple, long petioles
    "LeafSet027": dict(species="maple", size=(0.45, 0.58), cat="", rough=(0.42, 0.75)),      # maples turning (green-orange-red)
    "LeafSet028": dict(species="maple", size=(0.35, 0.48), cat="", rough=(0.40, 0.72)),      # Norway / Freeman maple
}
# "mostly yellows and tans, some orange and brown, a few still greenish"
CAT_W = {"yellow": 0.40, "tan": 0.19, "orange": 0.12, "brown": 0.18, "green": 0.07, "red": 0.04}
DRY = {"green": 0.1, "yellow": 0.3, "orange": 0.4, "red": 0.4, "tan": 0.75, "brown": 0.9, "locust": 0.45}
ALBEDO_MAX = 0.50        # a sunlit leaf's brightest channel, linear (the scans are exposed bright: a yellow leaf ~ 0.5)
EPS = 0.0025             # ft a leaf's lowest point floats above what it rests on (0.8 mm: contact, no z-fighting)
VEG = ("plants_", "leaf_", "twig_", "crown_core", "grass", "leaves_", "cam_")
SUPPORT = {"deck": "deck", "border": "deck", "lawn": "ground", "ground": "ground", "mulch": "bed", "groundcover": "bed",
           "soil": "bed", "paver": "hard", "flag": "hard", "flag2": "hard", "gravel": "hard"}


# ====================================================================== the leaf library (scans + procedural)
def _asset_dir() -> Optional[str]:
    for d in ASSET_DIRS:
        if d and os.path.isfile(os.path.join(d, "LeafSet007", "LeafSet007_2K-JPG_Opacity.jpg")):
            return d
    return None


def _label(mask: np.ndarray) -> List[np.ndarray]:
    """Connected components (8-way) of a boolean mask -> a list of (n, 2) pixel arrays (row, col)."""
    H, W = mask.shape
    seen = np.zeros_like(mask, bool)
    comps = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        seen[y0, x0] = True
        q, pts = deque([(y0, x0)]), []
        while q:
            y, x = q.popleft()
            pts.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
        comps.append(np.array(pts))
    return comps


def _srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _classify(aid: str, rgb: np.ndarray) -> str:
    h, s, v = colorsys.rgb_to_hsv(*(np.clip(rgb, 0, 255) / 255.0))
    h *= 360.0
    fixed = ATLASES[aid]["cat"]
    if fixed:
        return fixed
    if aid == "LeafSet008":
        return "yellow" if (h >= 40 and s > 0.6) else "tan"
    if v < 0.5:
        return "brown"
    if h >= 55:
        return "green"
    if h < 25:
        return "red"
    if h < 42:
        return "orange"
    return "yellow"


def _index_atlas(adir: str, aid: str, cache: str) -> List[dict]:
    """One record per leaf in a scanned atlas: its pixel rect (a margin around the opaque cell), its long axis, the mean
    color and class, and a <= 64 px opacity mask of the rect. Cached as JSON (the masks are cheap to rebuild)."""
    op_p = os.path.join(adir, aid, f"{aid}_2K-JPG_Opacity.jpg")
    col_p = os.path.join(adir, aid, f"{aid}_2K-JPG_Color.jpg")
    op = Image.open(op_p).convert("L")
    W, H = op.size
    jp = os.path.join(cache, f"leafidx_{aid}_{os.path.getsize(op_p)}.json")
    recs = None
    if os.path.exists(jp):
        try:
            recs = json.load(open(jp))
        except Exception:
            recs = None
    if recs is None:
        f = 4
        small = np.asarray(op.resize((W // f, H // f), Image.BILINEAR)) > 100
        col = np.asarray(Image.open(col_p).convert("RGB").resize((W // f, H // f), Image.BILINEAR), float)
        comps = [c for c in _label(small) if len(c) > 150]
        comps.sort(key=lambda c: (int(c[:, 0].min()) // 40, int(c[:, 1].min())))
        recs = []
        for c in comps:
            (r0, c0), (r1, c1) = c.min(0), c.max(0) + 1
            m = max(2, int(0.03 * max(r1 - r0, c1 - c0)))
            x0, y0 = max(0, (c0 - m) * f), max(0, (r0 - m) * f)
            x1, y1 = min(W, (c1 + m) * f), min(H, (r1 + m) * f)
            rgb = col[c[:, 0], c[:, 1]].mean(0)
            recs.append(dict(px=[int(x0), int(y0), int(x1), int(y1)], rgb=[float(v) for v in rgb], area=int(len(c))))
        json.dump(recs, open(jp, "w"))
    out = []
    for k, r in enumerate(recs):
        x0, y0, x1, y1 = r["px"]
        w, h = x1 - x0, y1 - y0
        sc = 64.0 / max(w, h)
        mw, mh = max(4, int(round(w * sc))), max(4, int(round(h * sc)))
        mask = np.asarray(op.crop((x0, y0, x1, y1)).resize((mw, mh), Image.BILINEAR), np.float32) / 255.0
        lin = _srgb_to_lin(np.array(r["rgb"]) / 255.0)
        out.append(dict(atlas=aid, k=k, px=(x0, y0, x1, y1), img=(W, H), long="x" if w >= h else "y",
                        aspect=max(w, h) / max(1, min(w, h)), mask=mask, cat=_classify(aid, np.array(r["rgb"])),
                        gain=float(min(1.0, ALBEDO_MAX / max(1e-3, float(lin.max())))), species=ATLASES[aid]["species"],
                        size=ATLASES[aid]["size"]))
    return out


def _locust_atlas(tex_dir: str) -> Tuple[str, str, str]:
    """Honey locust leaflets (Gleditsia triacanthos, the Front Range's street tree): 8 small oblong leaflets, entire
    margins, golden yellow to tan, a faint midrib -> (color, opacity, normal) PNGs, 4 x 2 cells of 256 px."""
    tag = "locust_v3"
    paths = tuple(os.path.join(tex_dir, f"{tag}_{m}.png") for m in ("color", "opacity", "normal"))
    if all(os.path.exists(p) for p in paths):
        return paths
    rng = np.random.default_rng(1771)
    S, NX, NY = 256, 4, 2
    col = Image.new("RGB", (S * NX, S * NY), (150, 120, 50))
    opa = Image.new("L", (S * NX, S * NY), 0)
    hgt = Image.new("L", (S * NX, S * NY), 0)
    golds = [(214, 176, 52), (205, 168, 48), (222, 186, 70), (196, 158, 60), (188, 156, 84), (176, 140, 76), (210, 160, 44),
             (200, 178, 92)]
    for k in range(NX * NY):
        ox, oy = (k % NX) * S, (k // NX) * S
        L, Wd = S * rng.uniform(0.74, 0.84), S * rng.uniform(0.30, 0.38)
        asym = rng.uniform(0.85, 1.0)
        pts_u, pts_l = [], []
        for t in np.linspace(0, 1, 60):
            w = Wd / 2 * math.sin(math.pi * min(1.0, t * 1.02)) ** 0.62 * (1 - 0.18 * t)
            x = ox + S * 0.5 - L / 2 + t * L
            pts_u.append((x, oy + S / 2 - w))
            pts_l.append((x, oy + S / 2 + w * asym))
        poly = pts_u + pts_l[::-1]
        base = np.array(golds[k])
        m_im = Image.new("L", (S * NX, S * NY), 0)
        ImageDraw.Draw(m_im).polygon(poly, fill=255)
        opa.paste(255, (0, 0), m_im)
        # mottled color: low-frequency patches, darker margin, a few brown flecks, a lighter midrib
        n = rng.normal(size=(S // 16, S // 16))
        n = np.asarray(Image.fromarray(((n - n.min()) / (np.ptp(n) + 1e-9) * 255).astype(np.uint8)).resize((S, S), Image.BICUBIC), float) / 255.0
        tile = np.clip(base[None, None, :] * (0.88 + 0.22 * n[..., None]), 0, 255)
        cim = Image.fromarray(tile.astype(np.uint8))
        d = ImageDraw.Draw(cim)
        for _ in range(int(rng.integers(2, 9))):
            fx, fy = rng.uniform(S * 0.25, S * 0.75), rng.uniform(S * 0.42, S * 0.58)
            rr = rng.uniform(1.0, 3.0)
            d.ellipse([fx - rr, fy - rr, fx + rr, fy + rr], fill=(120, 84, 40))
        if rng.random() < 0.5:                                      # a browned tip
            tx = S * 0.5 + L / 2
            for j in range(30):
                rr = rng.uniform(4, 12)
                d.ellipse([tx - rr - j, S / 2 - rr, tx + rr - j, S / 2 + rr], fill=(150, 112, 56))
        d.line([(S * 0.5 - L / 2, S / 2), (S * 0.5 + L / 2 * 0.92, S / 2 + 1)], fill=tuple(int(min(255, v * 1.12)) for v in base), width=2)
        cim = cim.filter(ImageFilter.GaussianBlur(0.7))
        local = Image.new("L", (S, S), 0)
        ImageDraw.Draw(local).polygon([(x - ox, y - oy) for x, y in poly], fill=255)
        rim = np.asarray(local.filter(ImageFilter.GaussianBlur(5)), float) / 255.0          # darker toward the margin
        arr = np.asarray(cim, float) * (0.82 + 0.18 * rim[..., None])
        col.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (ox, oy), local)
        hl = Image.new("L", (S, S), 0)
        dh = ImageDraw.Draw(hl)
        dh.line([(S * 0.5 - L / 2, S / 2), (S * 0.5 + L / 2 * 0.92, S / 2 + 1)], fill=255, width=3)
        hgt.paste(hl.filter(ImageFilter.GaussianBlur(1.2)), (ox, oy))
    col = col.filter(ImageFilter.GaussianBlur(0.4))
    h = np.asarray(hgt, float) / 255.0
    gy, gx = np.gradient(h)
    nx, ny, nz = -gx * 2.0, gy * 2.0, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    nrm = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
    col.save(paths[0]); opa.save(paths[1])
    Image.fromarray((nrm * 255).astype(np.uint8)).save(paths[2])
    return paths


def _locust_records(paths) -> List[dict]:
    op = Image.open(paths[1]).convert("L")
    W, H = op.size
    out = []
    for k in range(8):
        x0, y0 = (k % 4) * 256, (k // 4) * 256
        box = (x0 + 18, y0 + 76, x0 + 238, y0 + 180)
        mask = np.asarray(op.crop(box).resize((64, 30), Image.BILINEAR), np.float32) / 255.0
        out.append(dict(atlas="locust", k=k, px=box, img=(W, H), long="x", aspect=(box[2] - box[0]) / (box[3] - box[1]),
                        mask=mask, cat="locust", gain=0.62, species="locust", size=(0.075, 0.11)))
    return out


def _material(name: str, color: str, opacity: str, normal: Optional[str], rough: Optional[str], rr=(0.45, 0.8),
              scatter: Optional[str] = None, nstrength: float = 0.6) -> bpy.types.Material:
    """A thin leaf: base color = scan x per-leaf tint (the albedo calibration folded in), the underside (Backfacing)
    paler and grayer, the scan's normal map (veins), roughness from the scan mapped to `rr`, a translucent lobe (the
    scattering map where the set has one), the scan's opacity as a crisp alpha."""
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    uv = nt.nodes.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"

    def img(path, non_color):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            n.image.colorspace_settings.name = "Non-Color"
        n.interpolation = "Linear"
        L(uv.outputs["UV"], n.inputs["Vector"])
        return n
    ci = img(color, False)
    oi = img(opacity, True)
    tint = nt.nodes.new("ShaderNodeAttribute"); tint.attribute_name = "tint"
    mul = nt.nodes.new("ShaderNodeVectorMath"); mul.operation = "MULTIPLY"
    L(ci.outputs["Color"], mul.inputs[0]); L(tint.outputs["Color"], mul.inputs[1])
    # the underside: paler, grayer (a leaf's abaxial side), shown where the camera sees the back face
    hs = nt.nodes.new("ShaderNodeHueSaturation")
    hs.inputs["Saturation"].default_value = 0.85
    hs.inputs["Value"].default_value = 1.06
    L(mul.outputs["Vector"], hs.inputs["Color"])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mixc = nt.nodes.new("ShaderNodeMix"); mixc.data_type = "RGBA"; mixc.blend_type = "MIX"
    sock = lambda coll, ident: next(x for x in coll if x.identifier == ident)
    L(geo.outputs["Backfacing"], sock(mixc.inputs, "Factor_Float"))
    L(mul.outputs["Vector"], sock(mixc.inputs, "A_Color")); L(hs.outputs["Color"], sock(mixc.inputs, "B_Color"))
    base = sock(mixc.outputs, "Result_Color")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    L(base, bsdf.inputs["Base Color"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    if rough:
        ri = img(rough, True)
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = rr
        L(ri.outputs["Color"], mr.inputs["Value"])
        L(mr.outputs["Result"], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.5 * (rr[0] + rr[1])
    if normal:
        ni = img(normal, True)
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.uv_map = "UVMap"
        nm.inputs["Strength"].default_value = nstrength
        L(ni.outputs["Color"], nm.inputs["Color"])
        L(nm.outputs["Normal"], bsdf.inputs["Normal"])
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    if scatter:
        si = img(scatter, False)
        sm = nt.nodes.new("ShaderNodeVectorMath"); sm.operation = "MULTIPLY"
        L(si.outputs["Color"], sm.inputs[0]); L(tint.outputs["Color"], sm.inputs[1])
        L(sm.outputs["Vector"], tr.inputs["Color"])
    else:
        L(base, tr.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMixShader"); mix.inputs[0].default_value = 0.22
    L(bsdf.outputs[0], mix.inputs[1]); L(tr.outputs[0], mix.inputs[2])
    al = nt.nodes.new("ShaderNodeMapRange")                       # the scan's soft matte -> a crisp leaf edge
    al.inputs["From Min"].default_value, al.inputs["From Max"].default_value = 0.35, 0.65
    L(oi.outputs["Color"], al.inputs["Value"])
    trans = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix2 = nt.nodes.new("ShaderNodeMixShader")
    L(al.outputs["Result"], mix2.inputs[0]); L(trans.outputs[0], mix2.inputs[1]); L(mix.outputs[0], mix2.inputs[2])
    L(mix2.outputs[0], out.inputs[0])
    return m


# ====================================================================== what is under a leaf, what is in its way
class _World:
    """Two BVHs in plan feet from the meshes already built: the surfaces a leaf may rest on (deck boards and treads, the
    lawn, beds, pavers, flagstones) and everything else that is solid (posts, rails, risers, skirts, walls, trim...).
    Vegetation is in neither (a leaf may slip under a shrub)."""

    def __init__(self, col):
        sv, sp, scls, ov, op_ = [], [], [], [], []
        objs = list(getattr(col, "all_objects", col.objects))
        for ob in objs:
            if ob.type != "MESH" or ob.name.startswith(VEG) or not len(ob.data.polygons):
                continue
            me = ob.data
            nv = len(me.vertices)
            co = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3).astype(np.float64)
            Mw = np.array(ob.matrix_world, float)
            co = co @ Mw[:3, :3].T + Mw[:3, 3]
            co[:, 1] *= -1.0                                            # Blender -> plan
            npol = len(me.polygons)
            ls = np.empty(npol, np.int32); lt = np.empty(npol, np.int32)
            me.polygons.foreach_get("loop_start", ls); me.polygons.foreach_get("loop_total", lt)
            vi = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", vi)
            base = ob.name.split("#")[0].split(".")[0]
            cls = SUPPORT.get(base)
            V, P = (sv, sp) if cls else (ov, op_)
            off = sum(len(a) for a in V)
            V.append(co)
            P.extend((vi[s:s + t] + off).tolist() for s, t in zip(ls, lt))
            if cls:
                scls.extend([f"{cls}:{base}"] * npol)
        self.sup = BVHTree.FromPolygons(np.concatenate(sv).tolist(), sp) if sv else None
        self.obs = BVHTree.FromPolygons(np.concatenate(ov).tolist(), op_) if ov else None
        self.cls = scls

    def down(self, x, y, z0, reach=40.0):
        """The support surface under (x, y) below z0: (z, class, normal) or None."""
        if self.sup is None:
            return None
        loc, nrm, idx, _ = self.sup.ray_cast(mathutils.Vector((x, y, z0)), mathutils.Vector((0.0, 0.0, -1.0)), reach)
        if loc is None:
            return None
        n = np.array(nrm, float)
        if n[2] < 0:
            n = -n
        return float(loc[2]), self.cls[idx], n

    def under(self, P: np.ndarray, z0: float, allow: Tuple[str, ...]) -> Optional[np.ndarray]:
        """The support height under every point of P (plan, (n, 3)), rays from z0. A ray into a deck-board gap (3/16")
        or past an edge tries four points 0.02 ft around it and keeps the highest allowed hit. None if any point has
        no allowed support."""
        hz = np.empty(len(P))
        for i, p in enumerate(P):
            h = self.down(p[0], p[1], z0)
            if h is not None and h[1].split(":")[0] not in allow and h[0] > z0 - 0.35:
                return None                                  # another surface (a bed's edge, a step): not a gap
            if h is None or h[1].split(":")[0] not in allow:
                best = None
                for dx, dy in ((0.02, 0.02), (-0.02, -0.02), (0.02, -0.02), (-0.02, 0.02)):
                    g = self.down(p[0] + dx, p[1] + dy, z0)
                    if g is not None and g[1].split(":")[0] in allow and (best is None or g[0] > best):
                        best = g[0]
                if best is None:
                    return None
                hz[i] = best
            else:
                hz[i] = h[0]
        return hz

    def toward(self, p, d, reach=2.0):
        """The first solid (non-support) face from p along horizontal d: (point, outward unit normal) or None."""
        if self.obs is None:
            return None
        loc, nrm, _, _ = self.obs.ray_cast(mathutils.Vector(p), mathutils.Vector(d), reach)
        if loc is None:
            return None
        n = np.array(nrm, float); n[2] = 0.0
        ln = np.linalg.norm(n)
        if ln < 0.5:
            return None
        n /= ln
        if np.dot(n, d) > 0:
            n = -n
        return np.array(loc, float), n

    def collides(self, V: np.ndarray, Q: np.ndarray) -> bool:
        if self.obs is None:
            return False
        t = BVHTree.FromPolygons(V.tolist(), Q.tolist())
        return bool(self.obs.overlap(t))


class _Solids:
    """The scene's solid boxes (posts, columns, the foundation, walls, wall blocks, risers, skirts, fences, splash blocks)
    for a point-in-solid test: a leaf wholly inside one crosses no face, so the BVH overlap would not see it."""
    SKIP = {"board", "border", "tread", "ground", "paver", "stone", "tree", "glass", "roof", "drink", "siding"}

    def __init__(self, D):
        self.P, self.z, self.grid = [], [], {}
        for b in D["boxes"]:
            if b["kind"] in self.SKIP or (b.get("shape") or "box") != "box":
                continue
            if (b.get("rot") or 0.0) and (b.get("rot_axis") or "y") != "z" and not b.get("quad"):
                continue                                      # a tilted member (stringers): never near a resting leaf
            poly = _box_poly(b)
            k = len(self.P)
            self.P.append(poly); self.z.append((b["z0"], b["z1"]))
            (x0, y0), (x1, y1) = poly.min(0), poly.max(0)
            for gx in range(int(math.floor(x0 / 2)), int(math.floor(x1 / 2)) + 1):
                for gy in range(int(math.floor(y0 / 2)), int(math.floor(y1 / 2)) + 1):
                    self.grid.setdefault((gx, gy), []).append(k)

    def inside(self, P: np.ndarray) -> bool:
        for x, y, z in P:
            for k in self.grid.get((int(math.floor(x / 2)), int(math.floor(y / 2))), ()):
                z0, z1 = self.z[k]
                if z0 - 1e-4 <= z <= z1 + 1e-4 and _in_poly(x, y, self.P[k]):
                    return True
        return False


class _LeafMap:
    """The tops of the leaves placed so far (opaque parts only): 1-ft tiles of 0.01-ft cells, max z."""
    C = 0.01
    N = 100

    def __init__(self):
        self.t: Dict[Tuple[int, int], np.ndarray] = {}

    def query(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        ix = np.floor(x / self.C).astype(np.int64); iy = np.floor(y / self.C).astype(np.int64)
        out = np.full(x.shape, -1e9)
        for dx in (-1, 0, 1):                        # a 3x3 neighborhood: never sink into a leaf between samples
            for dy in (-1, 0, 1):
                jx, jy = ix + dx, iy + dy
                tx, ty = jx // self.N, jy // self.N
                for key in set(zip(tx.ravel().tolist(), ty.ravel().tolist())):
                    a = self.t.get(key)
                    if a is None:
                        continue
                    sel = (tx == key[0]) & (ty == key[1])
                    out[sel] = np.maximum(out[sel], a[jx[sel] - key[0] * self.N, jy[sel] - key[1] * self.N])
        return out

    def splat(self, P: np.ndarray):
        ix = np.floor(P[:, 0] / self.C).astype(np.int64); iy = np.floor(P[:, 1] / self.C).astype(np.int64)
        tx, ty = ix // self.N, iy // self.N
        for key in set(zip(tx.tolist(), ty.tolist())):
            sel = (tx == key[0]) & (ty == key[1])
            a = self.t.get(key)
            if a is None:
                a = self.t[key] = np.full((self.N, self.N), -1e9)
            np.maximum.at(a, (ix[sel] - key[0] * self.N, iy[sel] - key[1] * self.N), P[sel, 2])


# ====================================================================== one leaf
NU, NV = 9, 7


def _rot(axis, ang) -> np.ndarray:
    axis = np.asarray(axis, float); axis = axis / (np.linalg.norm(axis) or 1.0)
    return np.array(mathutils.Matrix.Rotation(float(ang), 3, mathutils.Vector(axis)), float)


def _align(n) -> np.ndarray:
    """The rotation taking +z onto unit n."""
    z = np.array([0.0, 0.0, 1.0])
    n = np.asarray(n, float) / np.linalg.norm(n)
    c = float(np.dot(z, n))
    if c > 0.99999:
        return np.eye(3)
    return _rot(np.cross(z, n), math.acos(max(-1.0, min(1.0, c))))


class _Leaf:
    """A leaf's grid in its own frame (S along the long axis, T across, Z its curl), UVs, which vertices are on the
    opaque leaf, and the dense samples of its opaque part (for the height map)."""

    def __init__(self, rec: dict, rng, dry: float, small: bool = False):
        self.rec = rec
        nu, nv = (5, 3) if small else (NU, NV)
        L = float(rng.uniform(*rec["size"]))
        narrow = float(rng.uniform(0.74, 0.95)) if (rec["species"] == "elm" and rng.random() < 0.45) else 1.0   # ash leaflets
        Wd = L / rec["aspect"] * narrow
        a = np.linspace(-1, 1, nu)[:, None] * np.ones((1, nv))
        b = np.ones((nu, 1)) * np.linspace(-1, 1, nv)[None, :]
        # cup across (edges up > 0 / dome < 0), curl along, twist, rolled margins for dry leaves, a soft random bend
        k = 1.0 + 1.6 * dry
        cup = float(rng.normal(0.35, 0.8)) * 0.008 * k * (Wd / 0.1)
        curl = abs(float(rng.normal(0.0, 1.0))) * 0.006 * k * (L / 0.3) * (1 if rng.random() < 0.8 else -1)
        tw = float(rng.normal(0, 1)) * 0.004 * k * (L / 0.3)
        roll = max(0.0, float(rng.normal(dry - 0.35, 0.3))) * 0.02 * (Wd / 0.1) * (1 if rng.random() < 0.75 else -1)
        asym = float(rng.uniform(-0.35, 0.35))
        Z = cup * b ** 2 * (1 + asym * b) + curl * (0.6 * a ** 2 + 0.4 * np.maximum(a, 0) ** 2) + tw * a * b + roll * b ** 4
        for _ in range(2):                                          # low-frequency bend
            fa, fb, ph = rng.uniform(0.6, 1.6), rng.uniform(0.4, 1.2), rng.uniform(0, 2 * math.pi)
            Z = Z + 0.0025 * k * (L / 0.3) * rng.normal() * np.sin(fa * math.pi * a + fb * math.pi * b + ph)
        if small:
            Z = 0.004 * float(rng.normal(0.4, 0.6)) * b ** 2 + 0.002 * rng.normal() * a ** 2
        self.P = np.stack([a * L / 2, b * Wd / 2, Z], -1)            # (nu, nv, 3)
        self.L, self.W, self.nu, self.nv = L, Wd, nu, nv
        # UVs and opacity from the cell
        x0, y0, x1, y1 = rec["px"]
        Wi, Hi = rec["img"]
        if rec["long"] == "x":
            px, py = x0 + (a + 1) / 2 * (x1 - x0), y0 + (b + 1) / 2 * (y1 - y0)
        else:
            px, py = x0 + (b + 1) / 2 * (x1 - x0), y0 + (a + 1) / 2 * (y1 - y0)
        self.UV = np.stack([px / Wi, 1.0 - py / Hi], -1)
        self.solid = self.opaque(a, b, dilate=1) > 0.5
        if not self.solid.any():
            self.solid[:] = True
        aa, bb = np.meshgrid(np.linspace(-1, 1, 44), np.linspace(-1, 1, 30), indexing="ij")
        keep = self.opaque(aa, bb) > 0.5
        self.dense_ab = (aa[keep], bb[keep])

    def opaque(self, a, b, dilate=0):
        M = self.rec["mask"]
        mh, mw = M.shape
        if self.rec["long"] == "x":
            mx, my = (a + 1) / 2 * (mw - 1), (b + 1) / 2 * (mh - 1)
        else:
            mx, my = (b + 1) / 2 * (mw - 1), (a + 1) / 2 * (mh - 1)
        mx = np.clip(np.rint(mx).astype(int), 0, mw - 1); my = np.clip(np.rint(my).astype(int), 0, mh - 1)
        if not dilate:
            return M[my, mx]
        best = np.zeros(np.shape(mx), np.float32)
        for dx in range(-dilate, dilate + 1):
            for dy in range(-dilate, dilate + 1):
                best = np.maximum(best, M[np.clip(my + dy, 0, mh - 1), np.clip(mx + dx, 0, mw - 1)])
        return best

    def dense(self, Pw: np.ndarray) -> np.ndarray:
        """World points over the opaque leaf: bilinear in the placed grid."""
        a, b = self.dense_ab
        fu, fv = (a + 1) / 2 * (self.nu - 1), (b + 1) / 2 * (self.nv - 1)
        i0 = np.clip(np.floor(fu).astype(int), 0, self.nu - 2); j0 = np.clip(np.floor(fv).astype(int), 0, self.nv - 2)
        du, dv = (fu - i0)[:, None], (fv - j0)[:, None]
        return (Pw[i0, j0] * (1 - du) * (1 - dv) + Pw[i0 + 1, j0] * du * (1 - dv) + Pw[i0, j0 + 1] * (1 - du) * dv
                + Pw[i0 + 1, j0 + 1] * du * dv)

    def quad_visible(self) -> np.ndarray:
        """Per quad: does any of the leaf's matte fall inside it (a 5 x 5 sample of the dilated mask)?"""
        ia, ib = np.meshgrid(np.arange(self.nu - 1), np.arange(self.nv - 1), indexing="ij")
        f = np.linspace(0.0, 1.0, 5)
        da, db = np.meshgrid(f, f, indexing="ij")
        a = -1 + 2 * (ia.ravel()[:, None] + da.ravel()[None, :]) / (self.nu - 1)
        b = -1 + 2 * (ib.ravel()[:, None] + db.ravel()[None, :]) / (self.nv - 1)
        return (self.opaque(a, b, dilate=1) > 0.3).any(1)

    def quads(self) -> np.ndarray:
        i, j = np.meshgrid(np.arange(self.nu - 1), np.arange(self.nv - 1), indexing="ij")
        v = (i * self.nv + j).ravel()
        return np.stack([v, v + self.nv, v + self.nv + 1, v + 1], -1)     # CCW from +z in the leaf's (plan) frame


# ====================================================================== the layout
class _Placer:
    def __init__(self, world: _World, lib: Dict[str, List[dict]], seed: int, solids: Optional[_Solids] = None):
        self.w = world
        self.solids = solids
        self.lib = lib
        self.map = _LeafMap()
        self.seed = seed
        self.out: Dict[str, dict] = {}          # material key -> {V, Q, UV, COL}
        self.stats: Dict[str, int] = {}
        self.tries = 0
        self.placed: List[dict] = []

    # ---- choosing a leaf
    def pick(self, rng, weights=None, locust=0.0) -> Tuple[dict, str]:
        if self.lib.get("locust") and rng.random() < locust:
            recs = self.lib["locust"]
            return recs[int(rng.integers(len(recs)))], "locust"
        w = dict(CAT_W)
        if weights:
            for k, v in weights.items():
                w[k] = w.get(k, 0.0) * v
        cats = [c for c in w if self.lib.get(c)]
        p = np.array([w[c] for c in cats]); p /= p.sum()
        c = cats[int(rng.choice(len(cats), p=p))]
        recs = self.lib[c]
        return recs[int(rng.integers(len(recs)))], c

    # ---- one placement attempt
    def place(self, rng, x, y, zone: str, allow: Tuple[str, ...], flat: bool, z_ref: float, *, weights=None, locust=0.12,
              nest=(0.0, 0.0), lean=None, tilt=(18.0, 58.0), gap=(0.003, 0.003), age=0.0, yaw=None) -> bool:
        """Drop one leaf at plan (x, y) onto a surface of a class in `allow`. flat: the support must be one level (deck,
        tread, paver); else the leaf takes the ground's tilt. z_ref: about where the support is (rays start 0.25 ft
        above it). nest: (lo, hi) ft the grass / ground cover holds the leaf up (nested in, not on, the blades). lean: (face
        point, outward normal) of a face the leaf drifted against: it slides up to `gap` ft from it, tipped up `tilt`
        degrees (0, 0: lying flat against its foot)
        of a face the leaf leans on. Returns True if placed."""
        self.tries += 1
        rec, cat = self.pick(rng, weights, locust)
        small = cat == "locust"
        dry = float(np.clip(DRY.get(cat, 0.4) + rng.normal(0, 0.12) + 0.3 * age, 0, 1))
        lf = _Leaf(rec, rng, dry, small=small)
        flip = rng.random() < (0.22 if small else 0.3)
        yaw = float(rng.uniform(0, 2 * math.pi)) if yaw is None else yaw
        R = _rot((0, 0, 1), yaw)
        if flip:
            R = R @ np.diag([1.0, -1.0, -1.0])
        up = np.array([0.0, 0.0, 1.0])
        if not flat:                                   # the ground's tilt under the leaf (4 probes at half its length)
            r_ = 0.5 * lf.L
            pr = [self.w.down(x + r_ * c, y + r_ * s, z_ref + 0.6) for c, s in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            if any(p is None or p[1].split(":")[0] not in allow for p in pr):
                return False
            zx, zy = (pr[0][0] - pr[1][0]) / (2 * r_), (pr[2][0] - pr[3][0]) / (2 * r_)
            up = np.array([-zx, -zy, 1.0]); up /= np.linalg.norm(up)
            if up[2] < math.cos(math.radians(32)):
                return False
            R = _align(up) @ R
        P = lf.P.reshape(-1, 3) @ R.T
        sol = lf.solid.ravel()
        if lean is not None and tilt[1] > 0:           # tip it up against the face it drifted to
            F, n = lean
            th = math.radians(float(rng.uniform(*tilt))) * (0.6 if small else 1.0)
            ax = np.array([-n[1], n[0], 0.0])
            Rl = _rot(ax, th)
            if (Rl @ (-n))[2] < 0:
                Rl = _rot(ax, -th)
            P = P @ Rl.T
        P[:, 0] += x; P[:, 1] += y
        if lean is not None:                           # slide it up to the face: its opaque edge `gap` ft off
            F, n = lean
            dist = (P[:, :2] - F[None, :2]) @ n[:2]
            P[:, :2] += n[None, :2] * (float(rng.uniform(*gap)) - dist[sol].min())
        # what is under every vertex
        hz = self.w.under(P, z_ref + 0.25, allow)
        if hz is None:
            return False
        if flat and (hz.max() - hz.min()) > 0.03:     # straddles a step / an edge
            return False
        if not flat and (hz.max() - hz.min()) > 0.25 + 0.6 * lf.L:
            return False
        under = np.maximum(hz, self.map.query(P[:, 0], P[:, 1]) + 0.0015)
        # rest the rigid leaf on its lowest opaque point (on the main surface; in grass, held up `nest` ft by the blades),
        # then drape it over the leaves below
        sk = float(rng.uniform(*nest)) if nest[1] > 0 else 0.0
        base = float(np.max((hz - P[:, 2])[sol])) + EPS + sk
        Z = P[:, 2] + base
        lift = np.maximum(0.0, under + EPS - Z).reshape(lf.nu, lf.nv)
        for _ in range(3):                             # a leaf bends over what it lies on, it does not spike
            pad = np.pad(lift, 1, mode="edge")
            avg = (pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]) / 4.0
            lift = np.maximum(lift, 0.6 * avg)
        if lift.max() > 0.05:                          # lies on a leaf, not perched on one leaning on a wall
            return False
        P[:, 2] = Z + lift.ravel()
        Q = lf.quads()
        shows = lf.quad_visible()                      # a quad wholly outside the leaf's matte is invisible
        if self.w.collides(P, Q[shows]) or (self.solids is not None and self.solids.inside(P[sol])):
            return False
        Pw = P.reshape(lf.nu, lf.nv, 3)
        self.map.splat(lf.dense(Pw))
        self.placed.append(dict(zone=zone, cat=cat, atlas=rec["atlas"], x=float(P[:, 0].mean()), y=float(P[:, 1].mean()),
                                z=float(P[:, 2].min()), gap=float((P[:, 2] - hz)[sol].min()), nest=sk, lean=lean is not None,
                                flip=bool(flip), L=lf.L))
        # the tint: the albedo calibration, +-7 % per leaf, a little warmer / cooler, older leaves duller and darker
        g = rec["gain"] * float(np.clip(rng.normal(1.0, 0.07), 0.8, 1.2)) * (1.0 - 0.18 * age * float(rng.uniform(0.5, 1)))
        warm = float(rng.normal(0, 0.03))
        tint = (g * (1 + warm), g, g * (1 - warm) * (1.0 - 0.1 * age), 1.0)
        key = rec["atlas"]
        o = self.out.setdefault(key, dict(V=[], Q=[], UV=[], COL=[], n=0))
        off = sum(len(v) for v in o["V"])
        o["V"].append(P.copy()); o["Q"].append(Q + off)
        uv = lf.UV.reshape(-1, 2)
        o["UV"].append(uv[Q].reshape(-1, 2)); o["COL"].append(np.tile(np.array(tint, np.float32), (Q.size, 1)))
        o["n"] += 1
        self.stats[zone] = self.stats.get(zone, 0) + 1
        return True

    def drop(self, rng, n, sampler, tries=40, **kw) -> int:
        """Place n leaves, each from sampler(rng) -> (x, y, place-kwargs) or None, `tries` attempts per leaf."""
        got = 0
        for _ in range(int(n)):
            for _ in range(tries):
                s = sampler(rng)
                if s is None:
                    continue
                x, y, extra = s
                args = dict(kw); args.update(extra)
                if self.place(rng, x, y, **args):
                    got += 1
                    break
        return got


# ====================================================================== the site's features
def _outline(spec) -> np.ndarray:
    o = np.array([[float(p[0]), float(p[1])] for p in (spec.geometry.outline or [])], float)
    return o


def _area(o):
    return 0.5 * float(np.sum(o[:, 0] * np.roll(o[:, 1], -1) - np.roll(o[:, 0], -1) * o[:, 1]))


def _edges(o):
    """(p, q, outward unit normal) per outline edge (edge:k is the k-th, 1-based)."""
    s = 1.0 if _area(o) > 0 else -1.0
    out = []
    for i in range(len(o)):
        p, q = o[i], o[(i + 1) % len(o)]
        d = q - p; d /= (np.linalg.norm(d) or 1.0)
        out.append((p, q, np.array([d[1], -d[0]]) * s))
    return out


def _in_poly(x, y, poly) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _seg_dist(x, y, pl) -> float:
    best = 9e9
    for (ax, ay), (bx, by) in zip(pl, pl[1:]):
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy or 1e-9
        t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
        best = min(best, math.hypot(x - (ax + vx * t), y - (ay + vy * t)))
    return best


def _grass_free(spec, D):
    """Where cycles.add_grass plants no blades (its _grass_mask, re-derived): the deck and stairs + margin, beds, walls,
    pavers, fences, flagstones, trunks. A lawn leaf there lies on the ground; elsewhere it nests into the blades."""
    try:
        from decktakeoff.landscape import _resample
    except Exception:
        _resample = None
    sm = spec.geometry.site_model or {}
    polys, segs = [], []
    walls = {w.get("name"): w for w in sm.get("walls", [])}
    for b in sm.get("beds", []):
        if b.get("wall") and _resample and b["wall"] in walls:
            w = walls[b["wall"]]
            polys.append(list(_resample(w["path"], 0.5, smooth=w.get("smooth", True))) + [tuple(q) for q in b.get("close", [])])
        elif b.get("poly"):
            polys.append([tuple(q) for q in b["poly"]])
    for w in sm.get("walls", []):
        pl = list(_resample(w["path"], 0.5, smooth=w.get("smooth", True))) if _resample else [tuple(q[:2]) for q in w["path"]]
        segs.append((pl, 0.85))
    for p in sm.get("pavers", []):
        segs.append(([tuple(q[:2]) for q in p["path"]], float(p.get("width_in", 16)) / 12 + 0.15))
    for f in sm.get("fences", []):
        segs.append(([tuple(q[:2]) for q in f["path"]], 0.35))
    discs = [(f["at"][0], f["at"][1], max(f.get("size", [3.0, 2.2])) / 2 + 0.15) for f in sm.get("flagstones", [])]
    discs += [(t["at"][0], t["at"][1], 0.9) for t in sm.get("trees", []) if t.get("type", "deciduous") != "shrub"]
    discs += [(t["at"][0], t["at"][1], float(t.get("radius", 2.0)) * 0.8) for t in sm.get("trees", []) if t.get("type") == "shrub"]
    boxes = [(b["x0"] - 0.35, b["x1"] + 0.35, b["y0"] - 0.35, b["y1"] + 0.35) for b in D["boxes"]
             if b["kind"] in ("tread", "riser", "stringer") or (b.get("tag") or "").startswith("box step")]
    out = [tuple(p) for p in (spec.geometry.outline or [])]

    def free(x, y) -> bool:
        if y < 0.4:
            return True
        if out and (_in_poly(x, y, out) or _seg_dist(x, y, out + out[:1]) < 0.6):
            return True
        if any(_in_poly(x, y, P) for P in polys):
            return True
        if any(_seg_dist(x, y, pl) < hw for pl, hw in segs):
            return True
        if any(math.hypot(x - cx, y - cy) < r for cx, cy, r in discs):
            return True
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in boxes)
    return free


def _box_poly(b) -> np.ndarray:
    """A box's plan footprint (its quad, else its rect turned by rot about z)."""
    if b.get("quad"):
        return np.array(b["quad"], float)
    cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
    hx, hy = (b["x1"] - b["x0"]) / 2, (b["y1"] - b["y0"]) / 2
    P = np.array([[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]])
    r = b.get("rot") or 0.0
    if r and (b.get("rot_axis") or "y") == "z":
        c, s = math.cos(r), math.sin(r)
        P = P @ np.array([[c, s], [-s, c]])
    return P + [cx, cy]


# ====================================================================== the entry point
def add_leaves(D: dict, spec, col, tex_dir: str, rng_seed: int = 29, density: float = 1.0) -> int:
    """Fallen leaves on and around the deck (see the module docstring). Deterministic for a given scene, seed and
    density. Returns the number of leaves placed."""
    if density <= 0:
        return 0
    t0 = time.time()
    os.makedirs(tex_dir, exist_ok=True)
    # ---- the library: the scanned sets (if present), the procedural honey locust leaflets
    lib: Dict[str, List[dict]] = {}
    mats: Dict[str, bpy.types.Material] = {}
    adir = _asset_dir()
    if adir:
        for aid, a in ATLASES.items():
            try:
                recs = _index_atlas(adir, aid, tex_dir)
            except Exception as e:                              # a missing / unreadable set: the others still work
                print(f"leaves: {aid} skipped ({e})", flush=True)
                continue
            for r in recs:
                lib.setdefault(r["cat"], []).append(r)
            p = lambda m: os.path.join(adir, aid, f"{aid}_2K-JPG_{m}.jpg")
            mats[aid] = _material(f"leaves_{aid}", p("Color"), p("Opacity"), p("NormalGL"), p("Roughness"), rr=a["rough"],
                                  scatter=p("Scattering") if os.path.exists(p("Scattering")) else None)
    lp = _locust_atlas(tex_dir)
    lib["locust"] = _locust_records(lp)
    mats["locust"] = _material("leaves_locust", lp[0], lp[1], lp[2], None, rr=(0.45, 0.6), nstrength=0.4)
    if not any(lib.get(c) for c in CAT_W):                      # no scans at all: locust leaflets everywhere
        print("leaves: no leaf scans found (DECK_LEAF_ASSETS, decktakeoff/data/leaves): honey locust leaflets only",
              flush=True)
        lib["yellow"] = lib["locust"]
    world = _World(col)
    solids = _Solids(D)
    pl = _Placer(world, lib, rng_seed, solids)
    R = lambda zone: np.random.default_rng([int(rng_seed), int(hashlib.md5(zone.encode()).hexdigest()[:8], 16)])
    dens = float(density)
    n_ = lambda base: int(round(base * dens))
    zt = float(D.get("deck_top", 1.75))
    o = _outline(spec)
    edges = _edges(o) if len(o) >= 3 else []
    opoly = [tuple(p) for p in o]
    xs, ys = (o[:, 0].min(), o[:, 0].max()), (o[:, 1].min(), o[:, 1].max()) if len(o) else ((0, 0), (0, 0))
    deck = ("deck",)
    posts = [b for b in D["boxes"] if b["kind"] == "railpost" and abs(b["z0"] - zt) < 0.3]
    door = [(b["x0"] - 0.5, b["x1"] + 0.5) for b in D["boxes"] if (b.get("tag") or "") == "entry door"]

    def edge_dist(x, y):
        return _seg_dist(x, y, opoly + opoly[:1]) if opoly else 9.0

    # ---- 1. the sparse scatter on the boards: clumps of 1-3, more toward the edges than mid-deck
    rng = R("deck")
    centers = []

    def deck_pt(rng):
        if centers and rng.random() < 0.45:                     # a neighbor of an earlier leaf
            cx, cy = centers[int(rng.integers(len(centers)))]
            x, y = cx + rng.normal(0, 0.45), cy + rng.normal(0, 0.45)
        else:
            for _ in range(60):
                x, y = rng.uniform(*xs), rng.uniform(*ys)
                if _in_poly(x, y, opoly) and rng.random() < 0.35 + 0.65 * math.exp(-edge_dist(x, y) / 2.2):
                    break
            else:
                return None
        if not _in_poly(x, y, opoly):
            return None
        centers.append((x, y))
        return x, y, {}
    pl.drop(rng, n_(30), deck_pt, zone="deck scatter", allow=deck, flat=True, z_ref=zt, locust=0.22)

    # ---- 2. drifts against the rail posts (on the deck side), some leaning on the post
    rng = R("posts")
    for b in posts:
        if rng.random() > 0.8:
            continue
        cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
        dirs = []
        for k in range(16):
            a = 2 * math.pi * k / 16
            px, py = cx + 0.45 * math.cos(a), cy + 0.45 * math.sin(a)
            h = world.down(px, py, zt + 0.15)
            if h and h[1].startswith("deck") and abs(h[0] - zt) < 0.05:
                dirs.append(a)
        if not dirs:
            continue
        a0 = dirs[int(rng.integers(len(dirs)))]
        nleaf = int(rng.integers(3, 7))

        def post_pt(rng, a0=a0, cx=cx, cy=cy):
            a = a0 + rng.normal(0, 0.55)
            d = 0.16 + abs(rng.normal(0, 0.22))
            x, y = cx + d * math.cos(a), cy + d * math.sin(a)
            extra = {}
            if rng.random() < 0.6:
                f = world.toward((x, y, zt + 0.06), (-math.cos(a), -math.sin(a), 0.0), 0.8)
                if f is not None:
                    extra = dict(lean=f, tilt=(18.0, 55.0) if rng.random() < 0.45 else (0.0, 0.0), gap=(0.003, 0.05))
            return x, y, extra
        pl.drop(rng, max(1, round(nleaf * dens)), post_pt, zone="post drifts", allow=deck, flat=True, z_ref=zt, locust=0.2)

    # ---- 3. the house wall: drifts along it and in its inside corners (none at the door)
    rng = R("wall")
    wall_edges = []
    for i, (p, q, n) in enumerate(edges):
        m = (p + q) / 2 - n * 0.3
        f = world.toward((m[0], m[1], zt + 0.08), (n[0], n[1], 0.0), 0.8)
        if f is not None and world.down(m[0], m[1], zt + 0.15) is not None:
            wall_edges.append(i)
    spots = []
    for i in wall_edges:                                       # inside corners: a wall edge meeting another blocked edge
        p, q, n = edges[i]
        for j, vtx in ((i - 1, p), ((i + 1) % len(edges), q)):
            pj, qj, nj = edges[j]
            if float(np.dot(n, nj)) > 0.97:
                continue
            other = pj if j == i - 1 else qj               # the neighbor edge's far end: inside the wall's line = a pocket
            if float(np.dot(other - vtx, n)) > -0.05:
                continue
            bis = -(n + nj); bis /= (np.linalg.norm(bis) or 1.0)
            inside = vtx + bis * 0.5
            near_post = any(math.hypot(vtx[0] - (b["x0"] + b["x1"]) / 2, vtx[1] - (b["y0"] + b["y1"]) / 2) < 0.8 for b in posts)
            if _in_poly(inside[0], inside[1], opoly) and (j in wall_edges or near_post):
                spots.append(("corner", vtx + bis * 0.35, n, nj))
    for i in wall_edges:
        p, q, n = edges[i]
        Lw = float(np.linalg.norm(q - p))
        for _ in range(max(0, int(Lw / 7.0 + rng.random()))):
            t = rng.uniform(0.12, 0.88)
            c = p + (q - p) * t - n * 0.35
            if any(a <= c[0] <= b_ for a, b_ in door) and abs(n[1]) > 0.9:
                continue
            spots.append(("wall", c, n, None))
    seen = set()
    for kind, c, n, nj in spots:
        key = (round(c[0], 1), round(c[1], 1))
        if key in seen:
            continue
        seen.add(key)
        nleaf = int(rng.integers(6, 12)) if kind == "corner" else int(rng.integers(4, 8))
        tang = np.array([-n[1], n[0]])

        def wall_pt(rng, c=c, n=n, nj=nj, tang=tang, kind=kind):
            if kind == "corner":
                pnt = c + rng.normal(0, 0.28, 2)
            else:
                pnt = c + tang * rng.normal(0, 0.55) - n * (abs(rng.normal(0, 0.18)) - 0.2)
            extra = {}
            if rng.random() < 0.7:
                nn_ = (n,) if nj is None else ((n, nj) if rng.random() < 0.5 else (nj, n))
                for nn in nn_:
                    f = world.toward((pnt[0], pnt[1], zt + 0.06), (nn[0], nn[1], 0.0), 1.2)
                    if f is not None:
                        extra = dict(lean=f, tilt=(15.0, 55.0) if rng.random() < 0.4 else (0.0, 0.0), gap=(0.003, 0.06))
                        break
            return float(pnt[0]), float(pnt[1]), extra
        pl.drop(rng, max(1, round(nleaf * dens)), wall_pt, zone="wall drifts", allow=deck, flat=True, z_ref=zt, locust=0.2)

    # ---- 4. the steps: a little drift against each riser (on the tread / ground below it), a few loose on the treads
    rng = R("steps")
    free = _grass_free(spec, D)
    for b in sorted((b for b in D["boxes"] if b["kind"] == "riser"), key=lambda b: b.get("tag") or ""):
        tag = b.get("tag") or ""
        try:
            ei = int(tag.split("edge:")[1].split()[0]) - 1
            n = edges[ei][2]
        except Exception:
            continue
        poly = _box_poly(b)
        prj = poly @ n
        face = poly[np.argsort(prj)[-2:]]                      # the riser's outer face (its two outermost corners)
        if np.linalg.norm(face[1] - face[0]) < 0.5:
            continue
        mid = face.mean(0)
        probe = world.down(mid[0] + n[0] * 0.35, mid[1] + n[1] * 0.35, b["z0"] + 0.3)
        if probe is None:
            continue
        z_low, cls = probe[0], probe[1].split(":")[0]
        allow = ("deck",) if cls == "deck" else ("ground", "hard", "bed")
        flat = cls in ("deck", "hard")
        nleaf = int(rng.integers(4, 8))
        u = (face[1] - face[0]); Lf = float(np.linalg.norm(u)); u /= Lf

        def riser_pt(rng, face=face, u=u, Lf=Lf, n=n, z_low=z_low, flat=flat):
            t = rng.uniform(0.08, 0.92) if rng.random() < 0.6 else float(np.clip(rng.choice([0.1, 0.9]) + rng.normal(0, 0.06), 0.03, 0.97))
            d = 0.1 + abs(rng.normal(0, 0.16))
            pnt = face[0] + u * (t * Lf) + n * d
            extra = {} if flat else dict(nest=(0.0, 0.0) if free(pnt[0], pnt[1]) else (0.03, 0.08))
            if rng.random() < 0.65:
                f = world.toward((pnt[0], pnt[1], z_low + 0.06), (-n[0], -n[1], 0.0), 1.0)
                if f is not None:
                    extra.update(lean=f, tilt=(15.0, 50.0) if rng.random() < 0.4 else (0.0, 0.0), gap=(0.003, 0.05))
            return float(pnt[0]), float(pnt[1]), extra
        pl.drop(rng, max(1, round(nleaf * dens)), riser_pt, zone="riser drifts", allow=allow, flat=flat, z_ref=z_low,
                locust=0.2)
    for b in sorted((b for b in D["boxes"] if b["kind"] == "tread"), key=lambda b: b.get("tag") or ""):
        poly = _box_poly(b)
        lo, hi = poly.min(0), poly.max(0)

        def tread_pt(rng, poly=poly, lo=lo, hi=hi):
            for _ in range(30):
                x, y = rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1])
                if _in_poly(x, y, [tuple(p) for p in poly]):
                    return x, y, {}
            return None
        pl.drop(rng, max(0, round(rng.integers(1, 4) * dens)), tread_pt, zone="treads", allow=deck, flat=True, z_ref=b["z1"],
                locust=0.3)

    # ---- 5. the beds (mulch, ground cover): more leaves, older, clumped, heavier at their edges
    rng = R("beds")
    sm = getattr(spec.geometry, "site_model", None) or {}
    for bed in sm.get("beds", []):
        mk = bed.get("mat", "")
        if mk == "soil":
            continue                                             # the bare soil under the deck: nothing reaches it
        pts = bed.get("poly") or []
        if bed.get("wall"):
            w = next((w for w in sm.get("walls", []) if w.get("name") == bed["wall"]), None)
            pts = [tuple(q[:2]) for q in (w["path"] if w else [])] + [tuple(q) for q in bed.get("close", [])]
        if len(pts) < 3:
            continue
        P = np.array(pts, float)
        lo, hi = P.min(0), P.max(0)
        area = abs(_area(P))
        nbed = n_(min(110.0, 1.1 * area))
        ccs = []

        def bed_pt(rng, lo=lo, hi=hi, ccs=ccs):
            if ccs and rng.random() < 0.5:
                cx, cy = ccs[int(rng.integers(len(ccs)))]
                x, y = cx + rng.normal(0, 0.5), cy + rng.normal(0, 0.5)
            else:
                x, y = rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1])
            h = world.down(x, y, 8.0)
            if h is None or not h[1].startswith("bed"):
                return None
            ccs.append((x, y))
            return x, y, dict(z_ref=h[0])
        nest = (0.0, 0.035) if mk == "groundcover" else (0.0, 0.0)
        pl.drop(rng, nbed, bed_pt, zone="beds", allow=("bed",), flat=False, z_ref=0.0, locust=0.15, nest=nest,
                weights={"brown": 1.5, "tan": 1.25, "green": 0.6}, age=0.35)

    # ---- 6. the lawn's edges: along the walls, the edging, the pavers, the deck's skirt and the stair, some leaning
    rng = R("lawnedge")
    feats = []                                               # (polyline, side sign: +1 = left of the path is the lawn)
    for w in sm.get("walls", []):
        feats.append(([tuple(q[:2]) for q in w["path"]], 1.0 if w.get("outside", "left") == "left" else -1.0, 0.45))
    for p in sm.get("pavers", []):
        feats.append(([tuple(q[:2]) for q in p["path"]], 1.0 if p.get("side", "left") == "left" else -1.0,
                      float(p.get("width_in", 16)) / 12.0))
    for i, (p, q, n) in enumerate(edges):                     # deck edges that meet open ground directly
        m = (p + q) / 2 + n * 0.5
        h = world.down(m[0], m[1], zt)
        if h is not None and h[1].startswith("ground") and not solids.inside(np.array([[m[0], m[1], h[0] + 0.05]])):
            feats.append(([tuple(p), tuple(q)], 0.0, 0.05))
    lens = [sum(math.dist(a, b_) for a, b_ in zip(f[0], f[0][1:])) for f in feats]
    tot = sum(lens) or 1.0

    def edge_pt(rng):
        k = int(rng.choice(len(feats), p=np.array(lens) / tot))
        path, side, off = feats[k]
        s = rng.uniform(0, lens[k])
        for a, b_ in zip(path, path[1:]):
            L_ = math.dist(a, b_)
            if s <= L_:
                break
            s -= L_
        a, b_ = np.array(a, float), np.array(b_, float)
        d = (b_ - a) / (np.linalg.norm(b_ - a) or 1.0)
        left = np.array([-d[1], d[0]])
        if side == 0.0:                                        # a deck edge: the ground side is away from the deck
            m = a + d * s
            left = left if not _in_poly(*(m + left * 0.3), opoly) else -left
            sgn = 1.0
        else:
            sgn = side
        dist = off + 0.05 + abs(rng.normal(0, 0.45))
        pnt = a + d * s + left * sgn * dist
        h = world.down(pnt[0], pnt[1], 8.0)
        if h is None or not (h[1].startswith("ground") or h[1].startswith("hard")):
            return None
        extra = dict(z_ref=h[0], flat=h[1].startswith("hard"))
        if not extra["flat"]:
            extra["nest"] = (0.0, 0.0) if free(pnt[0], pnt[1]) else (0.03, 0.09)
        if dist < off + 0.6 and rng.random() < 0.55:
            f = world.toward((pnt[0], pnt[1], h[0] + 0.07), (-left[0] * sgn, -left[1] * sgn, 0.0), 1.0)
            if f is not None:
                extra.update(lean=f, tilt=(15.0, 50.0) if rng.random() < 0.45 else (0.0, 0.0), gap=(0.003, 0.06))
        return float(pnt[0]), float(pnt[1]), extra
    if feats:
        pl.drop(rng, n_(90), edge_pt, zone="lawn edge", allow=("ground", "hard"), flat=False, z_ref=0.0, locust=0.18,
                weights={"brown": 1.3, "tan": 1.15}, age=0.25)

    # ---- 7. the lawn: a scatter in the yard, denser under the big tree and toward the deck, nested into the blades
    rng = R("lawn")
    trees = [(t["at"][0], t["at"][1], float(t.get("radius", 8))) for t in sm.get("trees", []) if t.get("type", "deciduous") == "deciduous"]
    gx0, gx1 = xs[0] - 14, xs[1] + 12
    gy0, gy1 = ys[1] - 2, ys[1] + 20

    def lawn_pt(rng):
        for _ in range(40):
            x, y = rng.uniform(gx0, gx1), rng.uniform(gy0, gy1)
            w = 0.25 + 0.5 * math.exp(-max(0.0, y - ys[1]) / 6.0)
            for tx, ty, tr in trees:
                w += 0.9 * math.exp(-((x - tx) ** 2 + (y - ty) ** 2) / (2 * (0.8 * tr) ** 2))
            if rng.random() < w / 1.6:
                break
        else:
            return None
        h = world.down(x, y, 8.0)
        if h is None or not h[1].startswith("ground"):
            return None
        return x, y, dict(z_ref=h[0], nest=(0.0, 0.0) if free(x, y) else (0.04, 0.11))
    pl.drop(rng, n_(170), lawn_pt, zone="lawn", allow=("ground",), flat=False, z_ref=0.0, locust=0.2,
            weights={"brown": 1.4, "tan": 1.2}, age=0.4)

    # ---- the meshes: one object per set, smooth shaded, UVs + the per-leaf tint
    n_total = 0
    for key in sorted(pl.out):
        o_ = pl.out[key]
        V = np.concatenate(o_["V"]); Q = np.concatenate(o_["Q"])
        UV = np.concatenate(o_["UV"]).astype(np.float32); COL = np.concatenate(o_["COL"]).astype(np.float32)
        Vb = V.astype(np.float32).copy(); Vb[:, 1] *= -1                  # plan -> Blender (a mirror: reverse the winding)
        Qb = Q[:, ::-1]
        UVb = UV.reshape(-1, 4, 2)[:, ::-1].reshape(-1, 2); COLb = COL.reshape(-1, 4, 4)[:, ::-1].reshape(-1, 4)
        me = bpy.data.meshes.new(f"leaves_{key}")
        me.vertices.add(len(Vb)); me.vertices.foreach_set("co", Vb.ravel())
        me.loops.add(Qb.size); me.polygons.add(len(Qb))
        me.polygons.foreach_set("loop_start", np.arange(0, Qb.size, 4, dtype=np.int32))
        me.polygons.foreach_set("vertices", Qb.astype(np.int32).ravel())
        me.update(calc_edges=True)
        me.uv_layers.new(name="UVMap").data.foreach_set("uv", UVb.ravel())
        me.color_attributes.new(name="tint", type="FLOAT_COLOR", domain="CORNER").data.foreach_set("color", COLb.ravel())
        try:
            me.shade_smooth()
        except Exception:
            me.polygons.foreach_set("use_smooth", np.ones(len(Qb), bool))
        me.materials.append(mats[key])
        ob = bpy.data.objects.new(f"leaves_{key}", me)
        col.objects.link(ob)
        n_total += o_["n"]
    LAST["placed"] = pl.placed
    zs = ", ".join(f"{k} {v}" for k, v in pl.stats.items())
    print(f"leaves: {n_total} ({zs}) from {pl.tries} drops in {time.time() - t0:.1f}s", flush=True)
    return n_total
