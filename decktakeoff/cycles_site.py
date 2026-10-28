"""Photoreal yard hardscape and house materials for the Cycles stills (decktakeoff.cycles): the flagstone steppers, the
tumbled-block retaining wall and edging, the cedar privacy fences, the bark-mulch bed and the bare soil, the house (lap
siding, white trim, plantation shutters behind double-pane glass, the door, fascia + gutters, the foundation, galvanized
metal), the concrete pier footings, the neighbors' houses and the asphalt-shingle roofs.

Hooked at the top of Mats.get (two lines):
    from decktakeoff import cycles_site; m = cycles_site.material(self, key, md)
    if m is not None: return m
material() returns a finished bpy material for the keys below and None for every other key (the deck boards, the
HardieTrim, the rail, the LED lenses, the brick border, the lawn, the plants and the leaves keep their own materials).

Textures: CC0 photo scans from Poly Haven and ambientCG (README.md beside them), found in $DECK_SITE_TEXTURES, else
decktakeoff/data/site_textures (CC0 files listed in that folder's README.md). A missing texture
never fails a render: that layer falls back to procedural noise. Every texture is tinted to its scene material's color:
the albedo is color x (texture / its own mean), so the scan brings the grain, mottling and relief and the yard model
keeps its colors (two photo-matched tweaks, documented at PHOTO_MATCH).

Coordinates: cycles.build() merges every material's boxes into one mesh at the origin, so Object coordinates are world
feet. Boxes in uv_mode "none" (block, siding, trim) carry no UVs; here each face is projected in its own plane (a wall
face: along the face horizontally x height; a top face: plan x, y) at real-world scale, and every face (each is its own
mesh island) gets its own random offset, so no two blocks or siding boards show the same piece of the scan. The cedar
boxes have 8 ft tile UVs (uv_mode "tile"); the roofs and gables are add_tris planes (UV x 8 = ft, V up the slope).
"""
from __future__ import annotations

import colorsys
import math
import os
from typing import Callable, Dict, Optional, Tuple

import numpy as np
from PIL import Image

import bpy

_HERE = os.path.dirname(os.path.abspath(__file__))
TEXTURE_DIRS = [d for d in (os.environ.get("DECK_SITE_TEXTURES"),
                            os.path.join(_HERE, "data", "site_textures")) if d]

# The scans (CC0; README.md) and one texture repeat in feet: true size (granular concrete 2.4 m, mulch 1.4 m), except the
# flagstone (2 m scan spread to 15': its fine pitting read as granite; the owner's Lyons sandstone is smooth) and the
# bitumen granules (3', stylized).
TEX = {
    "flag":   ("ph_worn_rock_natural_01_diff_2k.jpg", "ph_worn_rock_natural_01_rough_2k.jpg", "ph_worn_rock_natural_01_disp_2k.jpg", 15.0),
    "block":  ("ph_granular_concrete_diff_2k.jpg", "ph_granular_concrete_rough_2k.jpg", "ph_granular_concrete_disp_2k.jpg", 7.87),
    "wood":   ("acg_Wood059_2K_Color.jpg", "acg_Wood059_2K_Roughness.jpg", "acg_Wood059_2K_Displacement.jpg", 3.0),
    "mulch":  ("acg_Ground048_2K_Color.jpg", "acg_Ground048_2K_Roughness.jpg", "acg_Ground048_2K_Displacement.jpg", 4.6),
    "soil":   ("acg_Ground103_1K_Color.jpg", "acg_Ground103_1K_Roughness.jpg", "acg_Ground103_1K_Displacement.jpg", 6.0),
    "bitumen": ("ph_bitumen_diff_1k.jpg", "ph_bitumen_rough_1k.jpg", "ph_bitumen_disp_1k.jpg", 3.0),
}

# Photo match (the owner's photos, 25 Oct, sampled 28 Oct): sunlit block tops q04 / q10 median hue 18-24 deg, saturation
# 0.20-0.24 (the model's four blocks: 0.24-0.33, the first one reads pink); sunlit flagstones q03 #dbb9a2 / #e0bea5, hue
# 24-25, saturation 0.26 (the model's 0.34). (hue shift deg, saturation x, value x) on the scene color, in sRGB HSV.
PHOTO_MATCH = {"wblock": (3.0, 0.80, 1.0), "flag": (0.0, 0.76, 1.02)}


# ====================================================================== small helpers
def _lin1(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _srgb(hexc: str) -> Tuple[float, float, float]:
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _lin(hexc: str) -> Tuple[float, float, float]:
    return tuple(_lin1(c) for c in _srgb(hexc))


def _adjust(hexc: str, dh: float = 0.0, ks: float = 1.0, kv: float = 1.0) -> Tuple[float, float, float]:
    """The scene color moved in sRGB HSV (hue + dh degrees, saturation x ks, value x kv), returned linear."""
    h, s, v = colorsys.rgb_to_hsv(*_srgb(hexc))
    r, g, b = colorsys.hsv_to_rgb((h + dh / 360.0) % 1.0, min(1.0, s * ks), min(1.0, v * kv))
    return tuple(_lin1(c) for c in (r, g, b))


def _tex_path(name: str) -> Optional[str]:
    for d in TEXTURE_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


_MEAN: Dict[str, Tuple[float, float, float]] = {}


def _mean_linear(path: str) -> Tuple[float, float, float]:
    """The texture's mean color in scene-linear RGB (what Cycles sees after the sRGB decode): the tint divides by it."""
    if path not in _MEAN:
        a = np.asarray(Image.open(path).convert("RGB").resize((256, 256), Image.BILINEAR), np.float32) / 255.0
        a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
        _MEAN[path] = tuple(float(max(1e-4, v)) for v in a.reshape(-1, 3).mean(0))
    return _MEAN[path]


class _G:
    """A small node-graph builder: every method returns an output socket, and a number (or a tuple) is accepted wherever
    a socket is - it becomes that input's default value."""

    def __init__(self, nt):
        self.nt = nt
        self._geo = self._tc = self._tint = None

    def node(self, kind: str, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def put(self, sock, v):
        if v is None:
            return
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        else:
            sock.default_value = v

    # ---- scalars
    def math(self, op: str, a, b=None, c=None, clamp: bool = False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            self.put(n.inputs[i], v)
        return n.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def madd(self, a, b, c):
        return self.math("MULTIPLY_ADD", a, b, c)

    def lerp(self, a, b, t):
        """a + (b - a) t for scalars."""
        return self.madd(self.math("SUBTRACT", b, a), t, a)

    def rng(self, x, a, b, lo, hi, interp: str = "LINEAR"):
        n = self.node("ShaderNodeMapRange", interpolation_type=interp, clamp=True)
        self.put(n.inputs["Value"], x)
        for k, v in (("From Min", a), ("From Max", b), ("To Min", lo), ("To Max", hi)):
            self.put(n.inputs[k], v)
        return n.outputs["Result"]

    # ---- vectors / colors (a color is linked as a vector and back; Blender converts)
    def vmath(self, op: str, a, b=None, c=None, scale=None, out: str = "Vector"):
        n = self.node("ShaderNodeVectorMath", operation=op)
        for i, v in enumerate((a, b, c)):
            self.put(n.inputs[i], v)
        if scale is not None:
            self.put(n.inputs["Scale"], scale)
        return n.outputs[out]

    def vec(self, x, y, z=0.0):
        n = self.node("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.put(n.inputs[i], v)
        return n.outputs[0]

    def sep(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.put(n.inputs[0], v)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def cmul(self, a, b):
        return self.vmath("MULTIPLY", a, b)

    def cscale(self, a, s):
        return self.vmath("SCALE", a, scale=s)

    def clerp(self, a, b, t):
        """Colors: a + (b - a) t, t a scalar socket or number."""
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type="MIX", clamp_result=False)
        sk = lambda ident: next(x for x in n.inputs if x.identifier == ident)
        self.put(sk("Factor_Float"), t)
        self.put(sk("A_Color"), a if isinstance(a, bpy.types.NodeSocket) else tuple(a) + (1.0,) * (4 - len(a)))
        self.put(sk("B_Color"), b if isinstance(b, bpy.types.NodeSocket) else tuple(b) + (1.0,) * (4 - len(b)))
        return next(x for x in n.outputs if x.identifier == "Result_Color")

    def contrast(self, var, k):
        """1 + (var - 1) k: a normalized texture's variation scaled by k (per channel)."""
        return self.vmath("MULTIPLY_ADD", var, (k, k, k), (1.0 - k,) * 3)

    # ---- inputs
    def geo(self):
        if self._geo is None:
            self._geo = self.node("ShaderNodeNewGeometry")
        return self._geo

    def obj(self):
        if self._tc is None:
            self._tc = self.node("ShaderNodeTexCoord")
        return self._tc.outputs["Object"]

    def uv(self):
        if self._tc is None:
            self._tc = self.node("ShaderNodeTexCoord")
        return self._tc.outputs["UV"]

    def tint(self):
        """The per-box tint color attribute cycles.build() writes (block-to-block, board-to-board tone)."""
        if self._tint is None:
            self._tint = self.node("ShaderNodeAttribute", attribute_name="tint")
        return self._tint.outputs["Color"]

    def island(self):
        return self.geo().outputs["Random Per Island"]

    # ---- textures
    def noise(self, v, scale, detail=2.0, rough=0.5, dist=0.0, out="Fac"):
        n = self.node("ShaderNodeTexNoise")
        self.put(n.inputs["Vector"], v)
        for k, val in (("Scale", scale), ("Detail", detail), ("Roughness", rough), ("Distortion", dist)):
            self.put(n.inputs[k], val)
        return n.outputs[out]

    def voronoi(self, v, scale, rand=1.0, feature="F1", out="Distance"):
        n = self.node("ShaderNodeTexVoronoi", feature=feature)
        self.put(n.inputs["Vector"], v)
        self.put(n.inputs["Scale"], scale)
        self.put(n.inputs["Randomness"], rand)
        return n.outputs[out]

    def white(self, v, out="Value"):
        n = self.node("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
        self.put(n.inputs["Vector"], v)
        return n.outputs[out]

    def wave(self, v, scale, dist=2.0, detail=2.0, direction="X", out="Fac"):
        n = self.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction=direction)
        self.put(n.inputs["Vector"], v)
        for k, val in (("Scale", scale), ("Distortion", dist), ("Detail", detail)):
            self.put(n.inputs[k], val)
        return n.outputs[out]

    def image(self, path: str, v, non_color: bool = False):
        n = self.node("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            n.image.colorspace_settings.name = "Non-Color"
        n.interpolation = "Linear"
        n.extension = "REPEAT"
        self.put(n.inputs["Vector"], v)
        return n.outputs["Color"]

    def scan(self, name: str, v, contrast: float = 1.0, layers: str = "crh"):
        """A scan's (variation, roughness, height) at texture coordinates v: the color divided by its own mean (so it
        multiplies a scene color), the roughness and height maps raw (0..1). None for a layer not asked for (layers: c, r,
        h) or whose file is missing."""
        c, r, h, _ = TEX[name]
        pc, pr, ph = (_tex_path(f) if k in layers else None for f, k in ((c, "c"), (r, "r"), (h, "h")))
        var = None
        if pc:
            m = _mean_linear(pc)
            var = self.cmul(self.image(pc, v), (1.0 / m[0], 1.0 / m[1], 1.0 / m[2]))
            if abs(contrast - 1.0) > 1e-6:
                var = self.contrast(var, contrast)
        rough = self.sep(self.image(pr, v, True))[0] if pr else None
        height = self.sep(self.image(ph, v, True))[0] if ph else None
        return var, rough, height

    # ---- shading
    def bump(self, height, distance, strength=1.0, normal=None):
        n = self.node("ShaderNodeBump")
        self.put(n.inputs["Strength"], strength)
        self.put(n.inputs["Distance"], distance)
        self.put(n.inputs["Height"], height)
        self.put(n.inputs["Normal"], normal)
        return n.outputs["Normal"]

    def bevel(self, radius, samples: int = 4):
        n = self.node("ShaderNodeBevel")
        try:
            n.samples = samples
        except Exception:
            pass
        self.put(n.inputs["Radius"], radius)
        return n.outputs["Normal"]

    # ---- coordinates
    def face_plane(self):
        """(u, v) in feet in each face's own plane: a wall face -> (along the face horizontally, z); a top / bottom face ->
        (plan x, plan y). Returns (u, v, is_vertical)."""
        px, py, pz = self.sep(self.obj())
        nx, ny, nz = self.sep(self.geo().outputs["Normal"])
        L = self.math("MAXIMUM", self.math("SQRT", self.add(self.mul(nx, nx), self.mul(ny, ny))), 1e-4)
        u_wall = self.math("DIVIDE", self.math("SUBTRACT", self.mul(nx, py), self.mul(ny, px)), L)
        vert = self.math("LESS_THAN", self.math("ABSOLUTE", nz), 0.7)
        return self.lerp(px, u_wall, vert), self.lerp(py, pz, vert), vert


def _set(bsdf, **kw):
    """Principled inputs by name (spaces as underscores); a name this Blender lacks is skipped."""
    for k, v in kw.items():
        nm = k.replace("_", " ")
        if nm in bsdf.inputs:
            bsdf.inputs[nm].default_value = v


def _new(mats, key):
    m, nt, bsdf, out = mats._new(key)
    return m, nt, bsdf, out, _G(nt)


# ====================================================================== the materials
def flagstone(mats, key, md):
    """Colorado buff-rose flagstone (Lyons sandstone, natural cleft): a sandstone scan tinted to the stone's color (photo
    matched), soft bedding streaks across the stone, a darker iron speckle, the cleft face's relief and its matte, slightly
    varied sheen. Plan coordinates (ft): flag and flag2 take the scan turned and shifted, so neighboring stones differ."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _adjust(md.get("color", "#c8a184"), *PHOTO_MATCH["flag"])
    px, py, pz = g.sep(g.obj())
    a = math.radians(37.0 if key.endswith("2") else 0.0)
    ox = 2.7 if key.endswith("2") else 0.0
    u = g.add(g.madd(px, math.cos(a), g.mul(py, -math.sin(a))), ox)
    v = g.add(g.madd(px, math.sin(a), g.mul(py, math.cos(a))), ox * 0.6)
    T = TEX["flag"][3]
    var, rough, height = g.scan("flag", g.vec(g.mul(u, 1.0 / T), g.mul(v, 1.0 / T)), contrast=0.7)
    col = g.cscale(base, 1.0) if var is None else g.cmul(var, base)
    # bedding streaks: soft bands across the stone, a few inches apart, wandering
    band = g.wave(g.vec(u, g.mul(v, 0.35), pz), 0.9, dist=3.0, detail=2.0, direction="X")
    col = g.cscale(col, g.rng(band, 0.0, 1.0, 0.93, 1.05))
    # broad clouds (rose vs buff) and an iron speckle
    cloud = g.noise(g.obj(), 0.7, 3.0, 0.5)
    col = g.clerp(g.cmul(col, (0.97, 0.99, 1.02)), g.cmul(col, (1.06, 0.96, 0.9)), g.rng(cloud, 0.3, 0.7, 0.0, 1.0))
    iron = g.rng(g.noise(g.obj(), 26.0, 2.0, 0.5), 0.25, 0.2, 0.0, 1.0)
    col = g.cscale(col, g.rng(iron, 0.0, 1.0, 1.0, 0.8))
    g.put(bsdf.inputs["Base Color"], col)
    g.put(bsdf.inputs["Roughness"], g.rng(rough, 0.3, 1.0, 0.72, 0.95) if rough is not None else 0.88)
    _set(bsdf, Specular_IOR_Level=0.42)
    h = g.add(g.mul(height if height is not None else g.noise(g.obj(), 3.0, 6.0), 1.0), g.mul(g.noise(g.obj(), 1.4, 3.0), 0.8))
    g.put(bsdf.inputs["Normal"], g.bump(h, 0.008))
    return m


def tumbled_block(mats, key, md):
    """Tumbled segmental wall block (dry-cast concrete, tumbled): a granular concrete scan at its real size on every face
    (each face its own piece of it), blotchy mottling a few inches across, small dark pits, the block's own tone (the
    tint), a dusty gray-brown patina on the faces that grows toward the soil, tops a touch paler; an uneven face and the
    arrises knocked round unevenly (a noise-driven bevel radius, 3/8"-1")."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _adjust(md.get("color", "#c99d86"), *PHOTO_MATCH["wblock"])
    u, v, vert = g.face_plane()
    r = g.island()
    uo = g.add(u, g.mul(r, 41.3))
    vo = g.add(v, g.mul(g.math("FRACT", g.mul(r, 17.7)), 23.1))
    T = TEX["block"][3]
    var, rough, height = g.scan("block", g.vec(g.mul(uo, 1.0 / T), g.mul(vo, 1.0 / T)), contrast=1.45)
    P = g.obj()
    col = g.cmul(base, var) if var is not None else g.cscale(base, 1.0)
    # mottling: blotches of a darker, browner tone and paler, cooler patches
    mot = g.noise(P, 2.6, 4.0, 0.6, 0.4)
    col = g.clerp(g.cmul(col, (0.80, 0.77, 0.76)), g.cmul(col, (1.08, 1.09, 1.11)), g.rng(mot, 0.3, 0.72, 0.0, 1.0))
    # aggregate speckle and pits
    speck = g.noise(P, 48.0, 2.0, 0.7)
    pv = g.vec(uo, vo, g.mul(r, 9.0))
    pit = g.rng(g.voronoi(pv, 10.0, 1.0), 0.06, 0.13, 1.0, 0.0)                          # ~1/4" pits ...
    pit = g.mul(pit, g.math("GREATER_THAN", g.sep(g.voronoi(pv, 10.0, 1.0, out="Color"))[0], 0.8))   # ... in 1 cell of 5
    col = g.cscale(col, g.mul(g.rng(speck, 0.3, 0.7, 0.95, 1.05), g.rng(pit, 0.0, 1.0, 1.0, 0.6)))
    # weathering: the faces carry a dusty gray-brown patina, heavier low on the wall (soil splash), the tops paler
    pz = g.sep(P)[2]
    grime = g.mul(vert, g.add(0.12, g.rng(pz, -0.5, 0.5, 0.38, 0.0)))
    dusty = g.cmul(col, (0.84, 0.82, 0.78))
    col = g.clerp(col, g.vmath("ADD", g.cscale(dusty, 0.85), g.cscale((0.16, 0.14, 0.12), 0.15)), grime)
    col = g.cscale(col, g.lerp(1.04, 1.0, vert))
    col = g.cmul(col, g.tint())
    g.put(bsdf.inputs["Base Color"], col)
    g.put(bsdf.inputs["Roughness"], g.rng(rough, 0.4, 1.0, 0.86, 0.98) if rough is not None else 0.94)
    _set(bsdf, Specular_IOR_Level=0.4)
    h = g.add(g.mul(g.noise(P, 4.5, 4.0, 0.6), 0.55), g.mul(speck, 0.12))
    if height is not None:
        h = g.add(h, g.mul(height, 0.35))
    h = g.math("SUBTRACT", h, g.mul(pit, 0.5))
    bev = g.bevel(g.rng(g.noise(P, 1.7, 2.0), 0.3, 0.7, 0.03, 0.085))
    g.put(bsdf.inputs["Normal"], g.bump(h, 0.02, normal=bev))
    return m


def cedar_fence(mats, key, md):
    """Cedar privacy fence (1x6 pickets, 2x4 rails, 4x4 posts): a rough-sawn wood scan with its grain up the boards,
    every board its own slice of it and its own color (the cedar mix: redder, more golden, a few grayer boards), knots,
    a soft weathering to gray toward the top, a matte sawn face. The fence boxes carry 8 ft tile UVs: UV x 8 = ft."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#9b7a5c"))
    weathered = key == "cedar_old"
    uu, vv, _ = g.sep(g.uv())
    u, v = g.mul(uu, 8.0), g.mul(vv, 8.0)                       # ft: u across / along the fence, v = height
    t = g.tint()
    rc = g.white(g.cscale(t, 137.17), out="Color")              # three per-board randoms from the box's tint
    r1, r2, r3 = g.sep(rc)
    T = TEX["wood"][3]
    # the scan's grain runs along its x: map x to the height (the board's length), y across, a slice per board
    tx = g.mul(g.add(v, g.mul(r1, 31.0)), 1.0 / T)
    ty = g.mul(g.add(u, g.mul(r2, 17.0)), 1.0 / T)
    var, rough, height = g.scan("wood", g.vec(tx, ty), contrast=1.25)
    col = g.cmul(base, var) if var is not None else g.cscale(base, 1.0)
    # the board's own color: redder / more golden / grayer
    red = g.cmul(col, (1.10, 0.95, 0.86))
    gold = g.cmul(col, (1.04, 1.03, 0.88))
    col = g.clerp(col, red, g.rng(r3, 0.55, 1.0, 0.0, 0.9))
    col = g.clerp(col, gold, g.rng(r3, 0.0, 0.3, 0.8, 0.0))
    lum = g.vmath("DOT_PRODUCT", col, (0.2126, 0.7152, 0.0722), out="Value")
    gray = g.vec(g.mul(lum, 0.98), g.mul(lum, 1.0), g.mul(lum, 1.03))
    gray_amt = g.add(g.rng(r1, 0.82, 1.0, 0.0, 0.45), 0.55 if weathered else 0.0)
    col = g.clerp(col, gray, g.math("MINIMUM", gray_amt, 0.85))
    col = g.cscale(col, g.rng(r2, 0.0, 1.0, 0.88, 1.10))
    # knots: elongated along the grain, on some boards
    kv = g.vec(g.mul(u, 3.2), g.mul(v, 0.55), g.mul(r1, 7.0))
    kd = g.voronoi(kv, 1.3, 1.0)
    knot = g.mul(g.rng(kd, 0.07, 0.02, 0.0, 1.0), g.math("GREATER_THAN", r2, 0.35))
    col = g.clerp(col, g.cmul(col, (0.45, 0.38, 0.33)), g.mul(knot, 0.85))
    # weathering: the sun-bleached gray climbs the upper boards a little; splash darkening low
    pz = g.sep(g.obj())[2]
    col = g.cscale(col, g.rng(pz, -1.0, 0.0, 0.86, 1.0))
    g.put(bsdf.inputs["Base Color"], g.cmul(col, t))
    g.put(bsdf.inputs["Roughness"], g.rng(rough, 0.2, 1.0, 0.78, 0.95) if rough is not None else 0.88)
    _set(bsdf, Specular_IOR_Level=0.35)
    h = g.mul(height, 1.0) if height is not None else g.noise(g.obj(), 40.0, 3.0)
    h = g.math("SUBTRACT", h, g.mul(knot, 0.4))
    g.put(bsdf.inputs["Normal"], g.bump(h, 0.004))
    return m


def _ground(mats, key, md, scan: str, relief: float, contrast: float = 1.0, rough_range=(0.86, 1.0)):
    """A ground cover from a scan in plan coordinates, sampled twice (the second turned and scaled, blended by a slow
    noise) so the repeat never shows, with broad lighter / darker patches."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#4b3326"))
    px, py, pz = g.sep(g.obj())
    T = TEX[scan][3]
    var1, r1, h1 = g.scan(scan, g.vec(g.mul(px, 1.0 / T), g.mul(py, 1.0 / T)), contrast)
    a = math.radians(53.0)
    u2 = g.madd(px, math.cos(a) / (T * 0.83), g.mul(py, -math.sin(a) / (T * 0.83)))
    v2 = g.madd(px, math.sin(a) / (T * 0.83), g.add(g.mul(py, math.cos(a) / (T * 0.83)), 0.37))
    var2, r2, h2 = g.scan(scan, g.vec(u2, v2), contrast)
    w = g.rng(g.noise(g.obj(), 0.22, 2.0), 0.4, 0.6, 0.0, 1.0)
    if var1 is not None:
        col = g.cmul(base, g.clerp(var1, var2, w))
    else:
        col = g.cscale(base, g.rng(g.noise(g.obj(), 6.0, 6.0), 0.3, 0.7, 0.7, 1.3))
    col = g.cscale(col, g.rng(g.noise(g.obj(), 0.35, 3.0), 0.3, 0.7, 0.86, 1.12))
    g.put(bsdf.inputs["Base Color"], col)
    if r1 is not None:
        g.put(bsdf.inputs["Roughness"], g.rng(g.lerp(r1, r2, w), 0.0, 1.0, *rough_range))
    else:
        bsdf.inputs["Roughness"].default_value = rough_range[1]
    _set(bsdf, Specular_IOR_Level=0.35)
    h = g.lerp(h1, h2, w) if h1 is not None else g.noise(g.obj(), 8.0, 6.0)
    g.put(bsdf.inputs["Normal"], g.bump(h, relief))
    return m


def mulch(mats, key, md):
    """Shredded bark mulch: a mulch-bed scan, tinted to the bed's color, chunky relief (~1/2")."""
    return _ground(mats, key, md, "mulch", 0.035, contrast=1.1)


def soil(mats, key, md):
    """Bare soil (under the deck after the demo): a dry dirt scan with pebbles, tinted to the soil color."""
    return _ground(mats, key, md, "soil", 0.02, contrast=1.0)


def _lap_walls(spec):
    """The house model's lap-sided wall planes and where their courses fall: [(ax, ay, bx, by, z_lo, z_hi, phase)] in the
    plan frame (ft), phase = a course's bottom edge modulo the exposure. house.py starts a wall's courses at z0 + 1/4' and
    a gable's at its eave line (its first drip one exposure up)."""
    hm = getattr(getattr(spec, "geometry", None), "house_model", None) or {}
    exp = float(hm.get("exposure_in", 7.0)) / 12.0
    out = []
    for w in hm.get("walls", []):
        if w.get("cladding", "lap") != "lap":
            continue
        (ax, ay), (bx, by) = w["a"], w["b"]
        z0, z1 = float(w.get("z0", 0.0)), float(w.get("z1", 9.0))
        out.append((ax, ay, bx, by, z0 - 0.3, z1, (z0 + 0.25) % exp))
        if w.get("gable"):
            out.append((ax, ay, bx, by, z1, float(w["gable"]["z"]) + 0.1, z1 % exp))
    for gb in hm.get("gables", []):
        (ax, ay), (bx, by) = gb["a"], gb["b"]
        out.append((ax, ay, bx, by, float(gb["z"]), float(gb["peak_z"]) + 0.1, float(gb["z"]) % exp))
    return exp, out


def _course(g, exp, walls):
    """f: 0 at a lap course's butt (bottom) edge rising to 1 under the next lap, and `on` (1 on a lap wall's face, 0 off
    it - the downspouts, the slab behind). Each wall plane is tested in the shader (its face within 0.09' of the line)."""
    px, py, pz = g.sep(g.obj())
    x, y = px, g.mul(py, -1.0)                                  # Blender (x, -y, z) -> the plan frame
    best = max(walls, key=lambda w: math.hypot(w[2] - w[0], w[3] - w[1]) * (w[5] - w[4])) if walls else None
    phase, on = (best[6] if best else 0.0), 0.0
    for ax, ay, bx, by, zlo, zhi, ph in walls:
        L = math.hypot(bx - ax, by - ay) or 1.0
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = -uy, ux
        d = g.madd(x, nx, g.madd(y, ny, -(ax * nx + ay * ny)))
        sa = g.madd(x, ux, g.madd(y, uy, -(ax * ux + ay * uy)))
        m = g.math("LESS_THAN", g.math("ABSOLUTE", d), 0.09)
        m = g.mul(m, g.mul(g.math("GREATER_THAN", sa, -0.06), g.math("LESS_THAN", sa, L + 0.06)))
        m = g.mul(m, g.mul(g.math("GREATER_THAN", pz, zlo), g.math("LESS_THAN", pz, zhi)))
        if best is not None and abs(ph - best[6]) > 0.002:
            phase = g.lerp(phase, ph, m)
        on = g.math("MAXIMUM", on, m)
    f = g.math("FRACT", g.mul(g.math("SUBTRACT", pz, phase), 1.0 / exp))
    return f, on


def siding(mats, key, md):
    """Painted fiber-cement lap siding (HardiePlank-type, 7" exposure; the courses and drips are geometry): each course's
    face leans out to its butt edge (5/16" over the exposure, the bump) and darkens toward the lap above it (the owner's
    photos show both on every course), a satin paint film over the plank's embossed cedar grain (the wood scan's relief,
    along the course), every plank its own faint tone (12' planks, butt joints staggered course to course: a fine caulked
    line), a slow waviness, a breath of dust low on the wall. The downspouts share the key (painted to match, as on the
    house): no courses on them."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#bcbba8"))
    P = g.obj()
    px, py, pz = g.sep(P)
    u, v, _ = g.face_plane()
    r = g.island()
    col = g.cscale(base, 1.0)
    # 12' planks: a joint every 12' along each course, staggered by the course's own random
    s = g.mul(g.add(u, g.mul(r, 87.7)), 1.0 / 12.0)
    fp = g.math("FRACT", s)
    jd = g.mul(g.math("MINIMUM", fp, g.math("SUBTRACT", 1.0, fp)), 12.0)      # ft to the nearest joint
    joint = g.rng(jd, 0.006, 0.016, 1.0, 0.0)
    f = on = None
    exp, walls = _lap_walls(mats.spec)
    if key == "sidinglap" or not walls:
        joint = 0.0
    else:
        # joints only on a lap wall's face (not the downspouts) and not on the gable triangles (one face over many courses)
        f, on = _course(g, exp, walls)
        joint = g.mul(g.mul(joint, on), g.math("LESS_THAN", pz, 19.85))
    plank = g.white(g.vec(g.math("FLOOR", s), r, 0.37))
    tone = g.rng(plank, 0.0, 1.0, 0.972, 1.028)
    warm = g.rng(g.white(g.vec(g.math("FLOOR", s), r, 1.91)), 0.0, 1.0, -1.0, 1.0)
    col = g.cmul(col, g.vec(g.add(tone, g.mul(warm, 0.006)), tone, g.math("SUBTRACT", tone, g.mul(warm, 0.008))))
    # slow tonal drift (sun fading, the paint's lot), a little dust low on the wall
    col = g.cscale(col, g.rng(g.noise(P, 0.09, 3.0), 0.3, 0.7, 0.975, 1.02))
    col = g.cscale(col, g.rng(pz, 0.6, 2.4, 0.93, 1.0))
    if f is not None:
        col = g.cscale(col, g.lerp(1.0, 0.55, joint))
        col = g.cscale(col, g.lerp(1.0, g.rng(f, 0.5, 1.0, 1.0, 0.84, "SMOOTHSTEP"), on))         # shade under the lap
    g.put(bsdf.inputs["Base Color"], col)
    # satin paint: low sheen, a little patchy
    g.put(bsdf.inputs["Roughness"], g.rng(g.noise(P, 0.6, 2.0), 0.3, 0.7, 0.5, 0.62))
    _set(bsdf, Specular_IOR_Level=0.5)
    # relief (ft): the embossed grain (along the course), the paint's orange peel, a slow waviness, the joint's groove
    T = TEX["wood"][3]
    _, _, grain = g.scan("wood", g.vec(g.mul(g.add(u, g.mul(r, 13.0)), 1.0 / (T * 0.8)), g.mul(v, 1.0 / (T * 0.8))), layers="h")
    h = g.mul(grain if grain is not None else g.noise(g.vec(g.mul(u, 0.3), g.mul(v, 12.0), 0.0), 8.0, 4.0), 0.0007)
    h = g.add(h, g.mul(g.noise(P, 140.0, 2.0), 0.00012))
    h = g.add(h, g.mul(g.noise(g.vec(g.mul(u, 0.35), g.mul(v, 1.2), 0.0), 0.9, 2.0), 0.012))
    if f is not None:
        h = g.math("SUBTRACT", h, g.mul(joint, 0.004))
        h = g.add(h, g.mul(g.mul(g.math("SUBTRACT", 1.0, f), 0.026), on))   # the plank leans out 5/16" at its butt
    g.put(bsdf.inputs["Normal"], g.bump(h, 1.0))
    return m


def paint(mats, key, md, rough=(0.38, 0.5), grain=False, dirt_sills=True, bevel=0.0):
    """Painted trim (casings, corner boards, frames, sashes, soffits, shutters; the neighbors' trim): the color with a
    +-1 % piece-to-piece tone, a faint orange peel, satin to semi-gloss sheen, sills and other up-facing faces a shade
    dustier; optional eased arrises (bevel, ft)."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#f3f1ea"))
    P = g.obj()
    r = g.island()
    nz = g.sep(g.geo().outputs["Normal"])[2]
    col = g.cscale(base, g.rng(r, 0.0, 1.0, 0.985, 1.012))
    col = g.cscale(col, g.rng(g.noise(P, 0.15, 3.0), 0.3, 0.7, 0.985, 1.01))
    if dirt_sills:
        col = g.cmul(col, g.clerp((1.0, 1.0, 1.0), (0.95, 0.94, 0.92), g.math("GREATER_THAN", nz, 0.7)))
    g.put(bsdf.inputs["Base Color"], col)
    g.put(bsdf.inputs["Roughness"], g.rng(g.noise(P, 1.3, 2.0), 0.3, 0.7, rough[0], rough[1]))
    _set(bsdf, Specular_IOR_Level=0.5)
    h = g.mul(g.noise(P, 160.0, 2.0), 0.00012)
    if grain:
        h = g.add(h, g.mul(g.noise(g.vec(g.mul(g.sep(P)[0], 2.0), g.mul(g.sep(P)[1], 2.0), g.mul(g.sep(P)[2], 40.0)), 12.0, 3.0), 0.0002))
    nrm = g.bevel(bevel) if bevel else None
    g.put(bsdf.inputs["Normal"], g.bump(h, 1.0, normal=nrm))
    return m


def window_glass(mats, key, md):
    """Double-pane low-e window glass: clear with a faint green-gray cast in transmission, a stronger reflection than one
    bare pane (two panes and the coating, ~1.5x), a faintly cool reflection, and the slight haze of a real pane (water
    spots, film) in soft patches. Shadow rays pass it, as before: the sun reaches the shutters behind it."""
    m, nt, bsdf, out, g = _new(mats, key)
    _set(bsdf, Base_Color=(0.93, 0.955, 0.94, 1.0), Transmission_Weight=1.0, IOR=1.52, Specular_IOR_Level=0.66,
         Specular_Tint=(0.93, 0.97, 1.0, 1.0))
    g.put(bsdf.inputs["Roughness"], g.rng(g.noise(g.obj(), 2.5, 3.0), 0.45, 0.75, 0.0, 0.035))
    lp = g.node("ShaderNodeLightPath")
    tr = g.node("ShaderNodeBsdfTransparent")
    mx = g.node("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Shadow Ray"], mx.inputs[0])
    nt.links.new(bsdf.outputs[0], mx.inputs[1])
    nt.links.new(tr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs[0])
    return m


def fascia(mats, key, md):
    """Prefinished aluminum fascia wrap and K-style gutters: baked enamel, a satin sheen, faint run-off streaks down the
    gutter faces and a fine orange peel."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#2e463b"))
    P = g.obj()
    px, py, pz = g.sep(P)
    streak = g.noise(g.vec(g.mul(px, 6.0), g.mul(py, 6.0), g.mul(pz, 0.4)), 1.0, 3.0)
    col = g.cscale(base, g.rng(streak, 0.3, 0.7, 0.92, 1.06))
    g.put(bsdf.inputs["Base Color"], col)
    g.put(bsdf.inputs["Roughness"], g.rng(streak, 0.3, 0.7, 0.34, 0.46))
    _set(bsdf, Specular_IOR_Level=0.5)
    g.put(bsdf.inputs["Normal"], g.bump(g.mul(g.noise(P, 150.0, 2.0), 0.0001), 1.0))
    return m


def concrete(mats, key, md):
    """Cast concrete (the foundation strip, the pier footings): the granular concrete scan in each face's plane at its
    real size, tinted to the scene color, a few form stains, darker toward the soil."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#a9a59c"))
    u, v, vert = g.face_plane()
    r = g.island()
    T = TEX["block"][3]
    var, rough, height = g.scan("block", g.vec(g.mul(g.add(u, g.mul(r, 29.0)), 1.0 / T), g.mul(v, 1.0 / T)), contrast=1.3)
    P = g.obj()
    col = g.cmul(base, var) if var is not None else g.cscale(base, 1.0)
    col = g.cscale(col, g.rng(g.noise(P, 1.2, 4.0, 0.6), 0.3, 0.72, 0.86, 1.06))
    col = g.cscale(col, g.rng(g.sep(P)[2], -0.4, 0.5, 0.8, 1.0))
    g.put(bsdf.inputs["Base Color"], col)
    g.put(bsdf.inputs["Roughness"], g.rng(rough, 0.4, 1.0, 0.82, 0.96) if rough is not None else 0.92)
    _set(bsdf, Specular_IOR_Level=0.4)
    h = height if height is not None else g.noise(P, 30.0, 4.0)
    g.put(bsdf.inputs["Normal"], g.bump(h, 0.004))
    return m


def galvanized(mats, key, md):
    """Hot-dip galvanized steel (the corrugated window well; the hose bib, the storm door's handle): the zinc spangle -
    crystals an inch or two across, each its own sheen and tone - dulled by weathering."""
    m, nt, bsdf, out, g = _new(mats, key)
    P = g.obj()
    cell = g.voronoi(P, 7.0, 1.0, out="Color")
    cr = g.sep(cell)[0]
    col = g.cscale((0.55, 0.57, 0.59), g.rng(cr, 0.0, 1.0, 0.82, 1.1))
    col = g.cscale(col, g.rng(g.noise(P, 1.5, 3.0), 0.3, 0.7, 0.85, 1.05))
    g.put(bsdf.inputs["Base Color"], col)
    _set(bsdf, Metallic=1.0)
    g.put(bsdf.inputs["Roughness"], g.rng(cr, 0.0, 1.0, 0.3, 0.55))
    g.put(bsdf.inputs["Normal"], g.bump(g.mul(g.noise(P, 90.0, 2.0), 0.0002), 1.0))
    return m


def door_paint(mats, key, md):
    """The entry door slab behind the storm door: an exterior enamel, satin, a faint orange peel."""
    return paint(mats, key, md, rough=(0.3, 0.42), dirt_sills=False)


def neighbor_siding(mats, key, md):
    """A neighbor's lap siding on its massing box: 7" courses drawn in the material - each course's face leaning out to its
    drip edge (the bump), the shadow line under every drip, a tone per course - with white corner boards and a frieze
    under the eaves found by the bevel (the box's own edges), a little weathering."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#8a8f96"))
    P = g.obj()
    px, py, pz = g.sep(P)
    e = 7.0 / 12.0
    cz = g.mul(pz, 1.0 / e)
    f = g.math("FRACT", cz)                                    # 0 at a course's bottom edge, 1 under the next drip
    course = g.math("FLOOR", cz)
    col = g.cscale(base, g.rng(g.white(g.vec(course, 0.3, 0.7)), 0.0, 1.0, 0.975, 1.025))
    col = g.cscale(col, g.rng(f, 0.86, 1.0, 1.0, 0.62))         # the shadow line under the drip above
    col = g.cscale(col, g.rng(f, 0.0, 0.08, 1.06, 1.0))         # the drip's lit lower edge
    col = g.cscale(col, g.rng(g.noise(P, 0.12, 3.0), 0.3, 0.7, 0.95, 1.04))
    # corner boards and frieze: within ~4" of the box's convex edges (bevel normal vs. the face's)
    nb = g.bevel(0.36, samples=6)
    dev = g.vmath("DOT_PRODUCT", nb, g.geo().outputs["Normal"], out="Value")
    corner = g.rng(dev, 0.9995, 0.996, 0.0, 1.0)
    trim = _lin("#efece4")
    col = g.clerp(col, trim, corner)
    g.put(bsdf.inputs["Base Color"], col)
    g.put(bsdf.inputs["Roughness"], 0.62)
    _set(bsdf, Specular_IOR_Level=0.45)
    h = g.mul(g.math("SUBTRACT", 1.0, f), 0.03)                  # thicker at the drip: each face leans out at its bottom
    h = g.mul(h, g.math("SUBTRACT", 1.0, corner))
    g.put(bsdf.inputs["Normal"], g.bump(h, 1.0))
    return m


def neighbor_glass(mats, key, md):
    """A neighbor's window at 40-70 ft: a dark pane that mirrors the sky, with a hint of curtains / blinds behind."""
    m, nt, bsdf, out, g = _new(mats, key)
    P = g.obj()
    cur = g.rng(g.noise(g.vec(g.mul(g.sep(P)[0], 3.0), g.mul(g.sep(P)[1], 3.0), g.mul(g.sep(P)[2], 0.4)), 1.2, 2.0), 0.35, 0.7, 0.0, 1.0)
    g.put(bsdf.inputs["Base Color"], g.clerp((0.018, 0.02, 0.023), (0.07, 0.065, 0.058), cur))
    _set(bsdf, Roughness=0.03, Specular_IOR_Level=0.6, Metallic=0.0)
    return m


def shingles(mats, key, md):
    """Architectural (laminated) asphalt shingles, procedural in the roof plane (UV x 8 = ft, V up the slope): 5-5/8"
    courses, tabs of random width with a darker laminate tooth on some, a soft tone per tab and a blended granule color,
    the shadow line under each course's butt edge, the bitumen scan's granule grain; matte."""
    m, nt, bsdf, out, g = _new(mats, key)
    base = _lin(md.get("color", "#6b655e"))
    uu, vv, _ = g.sep(g.uv())
    u, v = g.mul(uu, 8.0), g.mul(vv, 8.0)
    e = 5.625 / 12.0
    cv = g.mul(v, 1.0 / e)
    course = g.math("FLOOR", cv)
    fv = g.math("FRACT", cv)                                   # 0 at the course's butt (lower) edge
    # tabs: a 1-D Voronoi along the course (random widths ~6-15"), offset per course
    tv = g.vec(g.add(g.mul(u, 1.0 / 0.85), g.mul(course, 7.13)), g.mul(course, 3.7), 0.0)
    tab = g.voronoi(tv, 1.0, 0.85, out="Color")
    t1, t2, t3 = g.sep(tab)
    col = g.cscale(base, g.rng(t1, 0.0, 1.0, 0.88, 1.1))
    col = g.clerp(col, g.cmul(col, (1.05, 1.0, 0.94)), g.rng(t2, 0.6, 1.0, 0.0, 1.0))
    tooth = g.mul(g.math("LESS_THAN", fv, g.rng(t3, 0.0, 1.0, 0.0, 0.55)), g.math("GREATER_THAN", t3, 0.45))
    col = g.cscale(col, g.lerp(1.0, 0.8, tooth))
    col = g.cscale(col, g.rng(fv, 0.0, 0.07, 0.55, 1.0))       # the butt edge's shadow line
    T = TEX["bitumen"][3]
    var, rough, height = g.scan("bitumen", g.vec(g.mul(u, 1.0 / T), g.mul(v, 1.0 / T)), contrast=1.0)
    if var is not None:
        lum = g.vmath("DOT_PRODUCT", var, (0.2126, 0.7152, 0.0722), out="Value")
        col = g.cscale(col, g.rng(lum, 0.6, 1.4, 0.85, 1.15))
    col = g.cscale(col, g.rng(g.white(g.vec(g.mul(u, 40.0), g.mul(v, 40.0), 0.0)), 0.0, 1.0, 0.92, 1.08))
    col = g.cscale(col, g.rng(g.noise(g.vec(u, v, 0.0), 0.12, 3.0), 0.3, 0.7, 0.9, 1.07))
    g.put(bsdf.inputs["Base Color"], col)
    bsdf.inputs["Roughness"].default_value = 0.93
    _set(bsdf, Specular_IOR_Level=0.35)
    h = g.add(g.mul(fv, 0.02), g.mul(tooth, -0.004))
    g.put(bsdf.inputs["Normal"], g.bump(h, 1.0))
    return m


# ====================================================================== dispatch
def _builder(key: str, md: dict) -> Optional[Callable]:
    if key in ("flag", "flag2"):
        return flagstone
    if key.startswith("wblock"):
        return tumbled_block
    if key in ("cedar", "cedar_old"):
        return cedar_fence
    if key == "mulch":
        return mulch
    if key in ("soil", "hsoil"):
        return soil
    if key in ("siding", "sidinglap") and md.get("pattern") in (None, "lap"):
        return siding                           # a rough-sawn (T1-11) siding keeps cycles.py's rsawn texture
    if key == "htrim":
        return lambda mats, k, d: paint(mats, k, d, rough=(0.36, 0.48))
    if key == "hsoffit":
        return lambda mats, k, d: paint(mats, k, d, rough=(0.55, 0.68), dirt_sills=False)
    if key == "shutter":
        return lambda mats, k, d: paint(mats, k, d, rough=(0.42, 0.55), grain=True, dirt_sills=False)
    if key.startswith("ntrim"):
        return lambda mats, k, d: paint(mats, k, d, rough=(0.5, 0.62))
    if key == "hglass":
        return window_glass
    if key == "hfascia":
        return fascia
    if key in ("foundation", "concrete", "concrete_slab"):
        return concrete
    if key == "hmetal":
        return galvanized
    if key == "hdoor":
        return door_paint
    if key.startswith("nsiding") and md.get("pattern") == "lap":
        return neighbor_siding
    if key == "nglass":
        return neighbor_glass
    if key == "shingle" or (key.startswith("nroof") and md.get("pattern") == "shingle"):
        return shingles
    return None


def material(mats, key: str, md: dict) -> Optional[bpy.types.Material]:
    """The improved material for a yard-hardscape / house key (cached on mats like Mats.get's own), else None.
    DECK_SITE_OFF=1 in the environment renders the old materials (an A/B switch)."""
    if os.environ.get("DECK_SITE_OFF"):
        return None
    if key in mats.cache:
        return mats.cache[key]
    b = _builder(key, md or {})
    if b is None:
        return None
    m = b(mats, key, md or {})
    mats.cache[key] = m
    return m
