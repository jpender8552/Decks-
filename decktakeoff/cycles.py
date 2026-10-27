"""Photoreal stills with Blender Cycles from the same Scene the WebGL viewer draws: every Box and mesh becomes real
geometry (merged per material), boards get TimberTech textures from the timbertech-boards renderer (full-length,
several boards per colour, a random slice per board), the yard gets leaf-card canopies, spruce twigs and grass, and
the light is a physical sky with the sun where it really is for the site, date and time.

Run with a Python that has bpy (Blender as a module):
    python -m decktakeoff.cycles JOB.json OUT_DIR [view ...] [--samples 160] [--size 1400x900] [--quick]
        [--cameras=STATIONS.json] [--when=YYYY-MM-DDTHH:MM] [--dusk] [--dusk-when=...] [--dusk-exposure=3] [--led=1] [--glow=1]
--when puts the sun at another local time than spec.site.sun_when; --dusk renders the blue hour of that date (sun -5 deg, or
--dusk-when) with the LED lenses (material keys led_riser / led_cap, or any material dict with an "emission" colour), real
fixture lights and the rooms behind the windows lit. A station with "mode": "dusk" renders at dusk without the flag.

Frames: the scene's plan feet (x along the wall, y into the yard, z up) map to Blender (x, -y, z); 1 Blender unit = 1 ft.
Views are the job's camera stations (geometry.site_model.cameras, then --cameras) or the viewer's generic ones."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import bpy  # noqa: E402  (Blender as a Python module)
import mathutils

IN = 1 / 12.0
SKILL_BOARDS = os.environ.get("TT_BOARDS_SKILL", "/root/.claude/skills/synced/607fe818-1870-48a4-acf4-521f29c0bf01_8ba838c8-b3cb-4abb-8652-1992d2c2ba58/timbertech-boards/scripts")


def B(x, y, z):
    return (x, -y, z)


def _hex(h: str) -> Tuple[float, float, float]:
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple((c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)   # linear for the shader


# ====================================================================== textures (generated, cached in OUT/_tex)
class Tex:
    def __init__(self, out_dir: str):
        self.dir = os.path.join(out_dir, "_tex")
        os.makedirs(self.dir, exist_ok=True)

    def _save(self, name, im: Image.Image) -> str:
        p = os.path.join(self.dir, name)
        im.save(p)
        return p

    def path(self, name):
        p = os.path.join(self.dir, name)
        return p if os.path.exists(p) else None

    def boards(self, collection: str, color: str, n: int = 6, length_in: float = 240, ppi: float = 24) -> List[str]:
        """Full-length TimberTech board textures from the skill renderer (deterministic per board)."""
        out = []
        sys.path.insert(0, SKILL_BOARDS)
        try:
            import render as TT   # the timbertech-boards renderer
        finally:
            sys.path.pop(0)
        for k in range(n):
            nm = f"board_{collection}_{color}_{k}.png".replace(" ", "_").replace("+", "plus")
            p = self.path(nm)
            if not p:
                im = TT.render_board(collection, color, length_in=length_in, ppi=ppi, seed_offset=100 + k)
                p = self._save(nm, im)
            out.append(p)
        return out

    def shingles(self, hexc: str) -> Tuple[str, str]:
        nm = f"shingle_{hexc.strip('#')}.png"
        if self.path(nm):
            return self.path(nm), self.path("h_" + nm)
        S = 2048                                     # 8 ft tile: 256 px / ft
        rng = np.random.default_rng(7)
        base = np.array(_srgb255(hexc), float)
        col = np.zeros((S, S, 3)); hgt = np.zeros((S, S))
        course = int(5.625 * 256 / 12)               # 5-5/8" exposure (architectural shingle)
        y = 0
        row = 0
        while y < S:
            x = -int(rng.integers(0, 300))
            while x < S:
                wtab = int(rng.integers(int(5 * 256 / 12), int(14 * 256 / 12)))
                tone = rng.normal(0, 0.10)
                c = np.clip(base * (1 + tone), 0, 255)
                x0, x1 = max(0, x), min(S, x + wtab - 3)
                if x1 > x0:
                    col[y:y + course, x0:x1] = c
                    # the dimensional laminate: a darker lower band on random tabs
                    if rng.random() < 0.55:
                        sh = int(course * rng.uniform(0.25, 0.5))
                        col[y + course - sh:y + course, x0:x1] *= 0.72
                        hgt[y + course - sh:y + course, x0:x1] -= 0.25
                    hgt[y:y + course, x0:x1] += np.linspace(0.0, 1.0, course)[:, None][: (min(S, y + course) - y)]
                x += wtab
            col[y + course - 4:y + course] *= 0.45          # the shadow line under each course
            hgt[y + course - 4:y + course] -= 0.6
            y += course
            row += 1
        g = rng.normal(0, 1, (S, S))                         # granules
        col *= (1 + 0.10 * g[..., None])
        hgt += 0.15 * g
        col = np.clip(col[:S, :S], 0, 255).astype(np.uint8)
        hgt = hgt[:S, :S]
        hgt = ((hgt - hgt.min()) / (np.ptp(hgt) + 1e-6) * 255).astype(np.uint8)
        return self._save(nm, Image.fromarray(col)), self._save("h_" + nm, Image.fromarray(hgt))

    def pavers(self, hexc: str) -> Tuple[str, str]:
        nm = f"paver_{hexc.strip('#')}.png"
        if self.path(nm):
            return self.path(nm), self.path("h_" + nm)
        S = 1536                                     # 8 ft tile: 192 px / ft, 4" = 64 px
        u = 64
        rng = np.random.default_rng(3)
        base = np.array(_srgb255(hexc), float)
        col = np.zeros((S, S, 3)) + np.array([118, 104, 92.0])        # sand joints
        hgt = np.zeros((S, S))
        for i in range(S // (2 * u)):
            for j in range(S // (2 * u)):
                for k in range(2):
                    c = np.clip(base * (1 + rng.normal(0, 0.09)) + rng.normal(0, 4, 3), 0, 255)
                    if (i + j) % 2:
                        x0, y0, w, h = i * 2 * u, j * 2 * u + k * u, 2 * u, u
                    else:
                        x0, y0, w, h = i * 2 * u + k * u, j * 2 * u, u, 2 * u
                    col[y0 + 3:y0 + h - 3, x0 + 3:x0 + w - 3] = c
                    hgt[y0 + 3:y0 + h - 3, x0 + 3:x0 + w - 3] = 1.0
        g = rng.normal(0, 1, (S, S))
        col *= (1 + 0.06 * g[..., None])
        im = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
        hm = Image.fromarray((np.clip(hgt * 0.85 + 0.15 * (g * 0.1 + 0.5), 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
        return self._save(nm, im), self._save("h_" + nm, hm)

    def brick(self, hexc: str, mortar: str = "#c2b9a6", course_in: float = 8.0 / 3.0, brick_in: float = 8.0) -> Tuple[str, str, float]:
        """Running-bond face brick (house.py "hbrick"): 12 bricks x 36 courses per tile (8 ft wide, 36 courses tall), every
        brick its own tone (buff / tan / a few orange-flashed and darker ones, iron specks, a sandy face), struck mortar joints
        recessed (height map). Returns (colour, height, tile height in ft) — the tile is 8 ft along the wall."""
        nm = f"brick_{hexc.strip('#')}_{mortar.strip('#')}_{course_in:.3f}_{brick_in:.2f}.png"
        th_ft = 36 * course_in / 12.0
        if self.path(nm):
            return self.path(nm), self.path("h_" + nm), th_ft
        S = 2048
        rng = np.random.default_rng(13)
        base = np.array(_srgb255(hexc), float)
        mort = np.array(_srgb255(mortar), float)
        col = np.zeros((S, S, 3)) + mort
        hgt = np.zeros((S, S)) + 0.22
        ch = S / 36.0                                 # px per course
        bw = S / 12.0                                 # px per brick (incl. joint)
        jt = max(3, int(round(0.375 / course_in * ch)))       # 3/8" joints
        yy, xx = np.mgrid[0:int(ch) + 2, 0:int(bw) + 2]
        for r in range(36):
            off = (r % 2) * bw / 2 + rng.uniform(-3, 3)
            y0 = int(round(r * ch)); y1 = int(round((r + 1) * ch)) - jt
            for c in range(12):
                x0 = int(round(c * bw + off)); x1 = int(round((c + 1) * bw + off)) - jt
                # tone: most bricks near the base, some lighter / darker, a few orange-flashed
                k = rng.normal(0, 0.075)
                tint = np.array([1.0, 1.0, 1.0])
                u = rng.random()
                if u < 0.12:
                    tint = np.array([1.06, 0.96, 0.86])            # orange flash
                elif u < 0.2:
                    tint = np.array([0.86, 0.84, 0.82]); k -= 0.06  # darker / browner
                elif u < 0.3:
                    tint = np.array([1.04, 1.04, 1.02]); k += 0.05  # pale
                c_ = np.clip(base * (1 + k) * tint, 0, 255)
                h_, w_ = y1 - y0, x1 - x0
                if h_ <= 2 or w_ <= 2:
                    continue
                # wire-cut face: mottled between a pale cream and a warmer tan (low-frequency blobs), a sandy grain,
                # a little kiln flash toward one end, a few small iron specks
                mot = np.zeros((h_, w_))
                for _ in range(int(rng.integers(2, 5))):
                    cy_, cx_ = rng.uniform(0, h_), rng.uniform(0, w_)
                    sy_, sx_ = rng.uniform(0.3, 0.9) * h_, rng.uniform(0.15, 0.45) * w_
                    mot += rng.uniform(-1, 1) * np.exp(-(((np.arange(h_)[:, None] - cy_) / sy_) ** 2 + ((np.arange(w_)[None, :] - cx_) / sx_) ** 2))
                mot = np.clip(0.5 + 0.5 * mot, 0, 1)[..., None]
                pale = c_ * np.array([1.16, 1.15, 1.12]); warm = c_ * np.array([0.97, 0.88, 0.78])
                patch = warm * (1 - mot) + pale * mot
                patch *= (1 + 0.045 * rng.normal(0, 1, (h_, w_)))[..., None]
                grad = np.linspace(-1, 1, w_)[None, :] * rng.normal(0, 0.04)
                patch *= (1 + grad)[..., None]
                for _ in range(int(rng.integers(0, 4))):
                    sy, sx = int(rng.integers(0, h_)), int(rng.integers(0, w_))
                    patch[sy:sy + 2, sx:sx + 2] *= 0.7
                ey = np.minimum(np.arange(h_), h_ - 1 - np.arange(h_)); ex = np.minimum(np.arange(w_), w_ - 1 - np.arange(w_))
                e = np.minimum.outer(ey, ex)                       # px to the nearest brick edge: rounded arrises
                hb = np.clip(0.55 + e / 4.0, 0, 1.0) + 0.06 * rng.normal(0, 1, (h_, w_))
                cols_ = (np.arange(x0, x1) % S)                     # wrap around the tile edge (seamless)
                col[y0:y1, cols_] = patch
                hgt[y0:y1, cols_] = hb
        g = rng.normal(0, 1, (S, S))
        col *= (1 + 0.03 * g[..., None])
        im = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
        hm = Image.fromarray((np.clip(hgt, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
        return self._save(nm, im), self._save("h_" + nm, hm), th_ft

    def rsawn(self, hexc: str) -> Tuple[str, str]:
        """Rough-sawn plywood / cedar face (house.py siding_texture "rsawn"): fine vertical fibre streaks and saw texture in
        a solid stain, 8 ft tile (the grooves themselves are geometry)."""
        nm = f"rsawn_{hexc.strip('#')}.png"
        if self.path(nm):
            return self.path(nm), self.path("h_" + nm)
        S = 1024
        rng = np.random.default_rng(17)
        base = np.array(_srgb255(hexc), float)
        # vertical streaks: 1-D noise across x, stretched along y, plus fine fibres and a faint cross-saw pattern
        streak = np.cumsum(rng.normal(0, 1, S)); streak = (streak - np.convolve(streak, np.ones(61) / 61, mode="same"))
        streak = streak / (np.abs(streak).max() + 1e-6)
        fib = rng.normal(0, 1, (S // 8, S))
        fib = np.asarray(Image.fromarray(((fib - fib.min()) / np.ptp(fib) * 255).astype(np.uint8)).resize((S, S), Image.BICUBIC)).astype(float) / 255 - 0.5
        saw = np.sin(np.linspace(0, 2 * math.pi * 90, S))[:, None] * rng.normal(0, 1, (1, S)) * 0.15
        v = 0.06 * streak[None, :] + 0.08 * fib + 0.03 * saw + 0.025 * rng.normal(0, 1, (S, S))
        col = np.clip(base[None, None, :] * (1 + v[..., None]), 0, 255)
        im = Image.fromarray(col.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5))
        h = (np.clip(0.5 + 2.5 * v, 0, 1) * 255).astype(np.uint8)
        return self._save(nm, im), self._save("h_" + nm, Image.fromarray(h).filter(ImageFilter.GaussianBlur(0.8)))

    def grass(self) -> Tuple[str, str]:
        nm = "grass2.png"
        if self.path(nm):
            return self.path(nm), self.path("h_" + nm)
        S = 1024                                     # 4 ft tile
        rng = np.random.default_rng(5)
        # irrigated Kentucky bluegrass / fescue: sRGB blade colours sampled from the owner's sunlit lawn (photo 2), not darker
        im = Image.new("RGB", (S, S), (74, 98, 40))
        hm = Image.new("L", (S, S), 60)
        d = ImageDraw.Draw(im); dh = ImageDraw.Draw(hm)
        greens = [(92, 122, 48), (108, 138, 56), (124, 150, 62), (82, 110, 42), (136, 156, 72), (98, 128, 50), (116, 132, 60), (146, 160, 84)]
        for _ in range(60000):
            x, y = rng.uniform(0, S), rng.uniform(0, S)
            L = rng.uniform(6, 22); a = rng.uniform(-0.9, 0.9) + math.pi / 2
            x2, y2 = x + L * math.cos(a), y - L * math.sin(a)
            c = greens[int(rng.integers(len(greens)))]
            d.line([(x, y), (x2, y2)], fill=c, width=int(rng.integers(1, 3)))
            dh.line([(x, y), (x2, y2)], fill=int(rng.uniform(120, 255)), width=1)
        return self._save(nm, im), self._save("h_" + nm, hm)

    def mulch(self, hexc: str) -> Tuple[str, str]:
        nm = f"mulch_{hexc.strip('#')}.png"
        if self.path(nm):
            return self.path(nm), self.path("h_" + nm)
        S = 1024                                     # 4 ft tile
        rng = np.random.default_rng(9)
        base = np.array(_srgb255(hexc), float)
        im = Image.new("RGB", (S, S), tuple(int(v * 0.6) for v in base))
        hm = Image.new("L", (S, S), 40)
        d = ImageDraw.Draw(im); dh = ImageDraw.Draw(hm)
        for _ in range(26000):
            x, y = rng.uniform(0, S), rng.uniform(0, S)
            L = rng.uniform(4, 26); w = rng.uniform(2, 7); a = rng.uniform(0, math.pi)
            dx, dy = L * math.cos(a) / 2, L * math.sin(a) / 2
            c = tuple(int(v) for v in np.clip(base * rng.uniform(0.6, 1.35), 0, 255))
            d.line([(x - dx, y - dy), (x + dx, y + dy)], fill=c, width=int(w))
            dh.line([(x - dx, y - dy), (x + dx, y + dy)], fill=int(rng.uniform(90, 255)), width=int(w))
        return self._save(nm, im), self._save("h_" + nm, hm.filter(ImageFilter.GaussianBlur(0.8)))

    def leaf(self, hexc: str, hexc2: str, name: str, shape: str = "ovate") -> str:
        nm = f"leaf_{name}.png"
        if self.path(nm):
            return self.path(nm)
        S = 256
        rng = np.random.default_rng(int(hashlib.md5(name.encode()).hexdigest()[:6], 16))
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c1 = _srgb255(hexc); c2 = _srgb255(hexc2)
        # 3 leaves per card (a small spray reads fuller than one leaf)
        for k in range(3):
            cx, cy = S * (0.3 + 0.4 * rng.random()), S * (0.3 + 0.4 * rng.random())
            L, Wd = S * rng.uniform(0.32, 0.42), S * rng.uniform(0.14, 0.2)
            a = rng.uniform(0, math.pi)
            pts = []
            for t in np.linspace(0, 2 * math.pi, 40):
                r = (math.sin(t) ** 2) ** 0.5
                px = L / 2 * math.cos(t)
                py = Wd / 2 * math.sin(t) * (1.0 - 0.35 * math.cos(t))
                pts.append((cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a)))
            mix = rng.random()
            c = tuple(int(c1[i] * (1 - mix) + c2[i] * mix) for i in range(3))
            d.polygon(pts, fill=c + (255,))
            d.line([(cx - L / 2 * math.cos(a), cy - L / 2 * math.sin(a)), (cx + L / 2 * math.cos(a), cy + L / 2 * math.sin(a))],
                   fill=tuple(min(255, int(v * 1.25)) for v in c) + (255,), width=2)
        return self._save(nm, im)

    def twig(self, hexc: str, name: str) -> str:
        """A spruce twig card: a stem with short stiff needles, blue-green, alpha cut-out."""
        nm = f"twig_{name}.png"
        if self.path(nm):
            return self.path(nm)
        W_, H_ = 512, 256
        rng = np.random.default_rng(11)
        im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        base = _srgb255(hexc)
        d.line([(10, H_ / 2), (W_ - 10, H_ / 2)], fill=(84, 66, 48, 255), width=4)
        for _ in range(900):
            t = rng.uniform(0.03, 0.97)
            x = 10 + t * (W_ - 20)
            spread = (1 - abs(t - 0.45) * 1.1) * H_ * 0.45
            a = rng.uniform(-1.2, 1.2) + (math.pi if rng.random() < 0.5 else 0)
            L = rng.uniform(0.25, 1.0) * spread
            x2, y2 = x + L * math.sin(a) * 0.4, H_ / 2 + L * math.cos(a)
            c = tuple(int(v) for v in np.clip(np.array(base) * rng.uniform(0.7, 1.3), 0, 255))
            d.line([(x, H_ / 2), (x2, y2)], fill=c + (255,), width=2)
        return self._save(nm, im)


def _srgb255(hexc: str) -> Tuple[int, int, int]:
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ====================================================================== materials
class Mats:
    def __init__(self, scene_materials: Dict[str, dict], tex: Tex, spec):
        self.M = scene_materials
        self.tex = tex
        self.spec = spec
        self.cache: Dict[str, bpy.types.Material] = {}
        self.board_imgs: Dict[str, List[str]] = {}

    # ---- node helpers
    @staticmethod
    def _new(name):
        m = bpy.data.materials.new(name)
        try:
            m.use_nodes = True
        except Exception:
            pass
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs[0], out.inputs[0])
        return m, nt, bsdf, out

    @staticmethod
    def _img(nt, path, non_color=False, closest=False):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            n.image.colorspace_settings.name = "Non-Color"
        n.interpolation = "Closest" if closest else "Linear"
        return n

    def _bump(self, nt, bsdf, height_out, strength=0.2, distance=0.01):
        b = nt.nodes.new("ShaderNodeBump")
        b.inputs["Strength"].default_value = strength
        b.inputs["Distance"].default_value = distance
        nt.links.new(height_out, b.inputs["Height"])
        nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
        return b

    def _tint(self, nt, color_out, bsdf):
        """Multiply by the per-box 'tint' colour attribute (board-to-board / block-to-block tone)."""
        a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_name = "tint"
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = "MULTIPLY"
        sock = lambda coll, ident: next(x for x in coll if x.identifier == ident)
        sock(mx.inputs, "Factor_Float").default_value = 1.0
        nt.links.new(color_out, sock(mx.inputs, "A_Color")); nt.links.new(a.outputs["Color"], sock(mx.inputs, "B_Color"))
        nt.links.new(sock(mx.outputs, "Result_Color"), bsdf.inputs["Base Color"])

    def board(self, key: str, k: int) -> bpy.types.Material:
        """A TimberTech board material: the k-th full-length texture, low-gloss cap, grain bump."""
        name = f"{key}#{k}"
        if name in self.cache:
            return self.cache[name]
        imgs = self.board_imgs.get(key)
        if imgs is None:
            dk = self.spec.decking
            coll, color = dk.collection, dk.color
            if key == "border":
                coll, color = dk.border_collection or dk.collection, dk.border_color or dk.color
            imgs = self.tex.boards(coll, color)
            self.board_imgs[key] = imgs
        m, nt, bsdf, out = self._new(name)
        img = self._img(nt, imgs[k % len(imgs)])
        self._tint(nt, img.outputs["Color"], bsdf)
        # a matte cap (TimberTech: low-gloss): at the low angle of a yard view a glossier cap mirrors the sky and the brown goes grey
        bsdf.inputs["Roughness"].default_value = 0.85
        bsdf.inputs["Specular IOR Level"].default_value = 0.25
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        nt.links.new(img.outputs["Color"], bw.inputs[0])
        self._bump(nt, bsdf, bw.outputs[0], strength=0.12, distance=0.004)
        self.cache[name] = m
        return m

    def get(self, key: str) -> bpy.types.Material:
        if key in self.cache:
            return self.cache[key]
        md = self.M.get(key, {"color": "#999999"})
        if "screen" in key or "fabric" in key or md.get("openness") is not None or md.get("alpha") is not None:
            return self.screen(key, md)          # a motorized screen's fabric (louvered roof option): a see-through weave
        if _emits(key, md):                     # an LED lens (riser / post-cap light): dark by day, glowing at dusk
            return self.emitter(key, md)
        m, nt, bsdf, out = self._new(key)
        col = _hex(md.get("color", "#999999"))
        rough = float(md.get("rough", 0.8) if md.get("rough") is not None else 0.8)
        metal = float(md.get("metal", 0.0) or 0.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        pat = md.get("pattern")
        if md.get("glass") or key in ("glass", "hglass", "nglass"):
            # window glass: clear, thin; a faint tint
            bsdf.inputs["Base Color"].default_value = (0.92, 0.95, 0.97, 1)
            bsdf.inputs["Roughness"].default_value = 0.0
            bsdf.inputs["Transmission Weight"].default_value = 1.0
            bsdf.inputs["IOR"].default_value = 1.45
            if key == "nglass":
                bsdf.inputs["Transmission Weight"].default_value = 0.0
                bsdf.inputs["Base Color"].default_value = (0.02, 0.025, 0.03, 1)
                bsdf.inputs["Roughness"].default_value = 0.05
            else:
                # shadow rays pass the pane (no caustics): the shutters behind the glass get the sun, as they do
                lp = nt.nodes.new("ShaderNodeLightPath"); tr = nt.nodes.new("ShaderNodeBsdfTransparent")
                mx = nt.nodes.new("ShaderNodeMixShader")
                nt.links.new(lp.outputs["Is Shadow Ray"], mx.inputs[0]); nt.links.new(bsdf.outputs[0], mx.inputs[1]); nt.links.new(tr.outputs[0], mx.inputs[2])
                nt.links.new(mx.outputs[0], out.inputs[0])
        elif pat == "shingle":
            c, h = self.tex.shingles(md["color"])
            img = self._img(nt, c); hi = self._img(nt, h, non_color=True)
            nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
            self._bump(nt, bsdf, hi.outputs["Color"], 0.5, 0.03)
            bsdf.inputs["Roughness"].default_value = 0.92
        elif pat == "paver":
            c, h = self.tex.pavers(md["color"])
            img = self._img(nt, c); hi = self._img(nt, h, non_color=True)
            nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
            self._bump(nt, bsdf, hi.outputs["Color"], 0.6, 0.02)
            bsdf.inputs["Roughness"].default_value = 0.85
        elif pat == "grass":
            c, h = self.tex.grass()
            img = self._img(nt, c); hi = self._img(nt, h, non_color=True)
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            tgt = np.array(_srgb255(md["color"]), float); ref = np.array([109, 138, 60.0])
            hsv.inputs["Value"].default_value = float(np.clip(tgt.mean() / ref.mean(), 0.6, 1.4))
            nt.links.new(img.outputs["Color"], hsv.inputs["Color"])
            nt.links.new(hsv.outputs[0], bsdf.inputs["Base Color"])
            self._bump(nt, bsdf, hi.outputs["Color"], 0.5, 0.02)
            bsdf.inputs["Roughness"].default_value = 0.9
        elif pat == "gravel" and key in ("mulch",):
            c, h = self.tex.mulch(md["color"])
            img = self._img(nt, c); hi = self._img(nt, h, non_color=True)
            nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
            self._bump(nt, bsdf, hi.outputs["Color"], 0.8, 0.04)
            bsdf.inputs["Roughness"].default_value = 0.95
        elif pat == "hbrick":
            # the house's face brick: an image tile on world-aligned UVs (8 ft = 1 UV), stretched in v to 36 courses
            c, h, th_ft = self.tex.brick(md["color"], md.get("mortar", "#c2b9a6"), float(md.get("course_in", 8.0 / 3.0)),
                                         float(md.get("brick_in", 8.0)))
            tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = (1.0, 8.0 / th_ft, 1.0)
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
            img = self._img(nt, c); hi = self._img(nt, h, non_color=True)
            nt.links.new(mp.outputs["Vector"], img.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], hi.inputs["Vector"])
            self._tint(nt, img.outputs["Color"], bsdf)
            self._bump(nt, bsdf, hi.outputs["Color"], 0.75, 0.025)
            bsdf.inputs["Roughness"].default_value = 0.93
        elif pat == "rsawn":
            # stained rough-sawn plywood / cedar (T1-11): fibre streaks + a saw texture; the grooves are geometry
            c, h = self.tex.rsawn(md["color"])
            img = self._img(nt, c); hi = self._img(nt, h, non_color=True)
            self._tint(nt, img.outputs["Color"], bsdf)
            self._bump(nt, bsdf, hi.outputs["Color"], 0.18, 0.006)
            bsdf.inputs["Roughness"].default_value = rough
        elif pat in ("lap", "batten", "brick", "stone", "seam", "gravel"):
            # procedural: colour + noise (geometry carries the courses on the measured house)
            nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 18.0; nz.inputs["Detail"].default_value = 6.0
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = tuple(c * 0.9 for c in col) + (1,)
            ramp.color_ramp.elements[1].color = tuple(min(1, c * 1.08) for c in col) + (1,)
            nt.links.new(nz.outputs["Fac"], ramp.inputs[0])
            self._tint(nt, ramp.outputs[0], bsdf)
            self._bump(nt, bsdf, nz.outputs["Fac"], 0.08, 0.01)
        else:
            rgb = nt.nodes.new("ShaderNodeRGB"); rgb.outputs[0].default_value = col + (1,)
            if key.startswith("wblock"):
                # tumbled concrete block: mottled, rough, rounded arrises (bevel), tone per block via the tint
                nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 9.0; nz.inputs["Detail"].default_value = 8.0
                ramp = nt.nodes.new("ShaderNodeValToRGB")
                ramp.color_ramp.elements[0].color = tuple(c * 0.9 for c in col) + (1,)
                ramp.color_ramp.elements[1].color = tuple(min(1, c * 1.07) for c in col) + (1,)
                nt.links.new(nz.outputs["Fac"], ramp.inputs[0])
                self._tint(nt, ramp.outputs[0], bsdf)
                bev = nt.nodes.new("ShaderNodeBevel"); bev.inputs["Radius"].default_value = 0.05
                bmp = nt.nodes.new("ShaderNodeBump"); bmp.inputs["Strength"].default_value = 0.35; bmp.inputs["Distance"].default_value = 0.02
                nt.links.new(nz.outputs["Fac"], bmp.inputs["Height"]); nt.links.new(bev.outputs["Normal"], bmp.inputs["Normal"])
                nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
                bsdf.inputs["Roughness"].default_value = 0.95
            elif key == "dftimber" or md.get("rough_sawn"):
                self._rough_sawn(nt, bsdf, col)
            elif md.get("grain"):
                # wood without a TimberTech texture (framing lumber, cedar fence): a wave-grain procedural
                wv = nt.nodes.new("ShaderNodeTexWave"); wv.wave_type = "BANDS"; wv.inputs["Scale"].default_value = 2.5
                wv.inputs["Distortion"].default_value = 6.0; wv.inputs["Detail"].default_value = 3.0
                mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (0.25, 6.0, 1.0)
                tc = nt.nodes.new("ShaderNodeTexCoord"); nt.links.new(tc.outputs["UV"], mp.inputs[0]); nt.links.new(mp.outputs[0], wv.inputs["Vector"])
                ramp = nt.nodes.new("ShaderNodeValToRGB")
                ramp.color_ramp.elements[0].color = tuple(c * 0.82 for c in col) + (1,)
                ramp.color_ramp.elements[1].color = tuple(min(1, c * 1.1) for c in col) + (1,)
                nt.links.new(wv.outputs["Fac"], ramp.inputs[0])
                self._tint(nt, ramp.outputs[0], bsdf)
                self._bump(nt, bsdf, wv.outputs["Fac"], 0.1, 0.005)
            else:
                self._tint(nt, rgb.outputs[0], bsdf)
                if key.startswith(("siding", "nsiding", "htrim", "hsoffit", "trim", "shutter", "foundation", "concrete")):
                    # painted fibre-cement / trim / concrete: a fine embossed texture, never a perfect CG plane
                    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 60.0 if not key.startswith(("foundation", "concrete")) else 25.0
                    nz.inputs["Detail"].default_value = 8.0
                    self._bump(nt, bsdf, nz.outputs["Fac"], 0.06 if key.startswith(("siding", "nsiding")) else 0.03, 0.004)
                if key in ("railmetal", "steel", "storm") or "powder" in (md.get("label") or "").lower():
                    # textured powder coat (Fulton, Impression Rail Express): a dielectric with a dull sheen, not metal.
                    # Only the coated metal: siding, trim and concrete keep their own roughness and no clear coat.
                    bsdf.inputs["Roughness"].default_value = 0.55
                    bsdf.inputs["Metallic"].default_value = 0.0
                    bsdf.inputs["Coat Weight"].default_value = 0.05
            if key in ("hmetal", "galv", "cable", "well"):
                bsdf.inputs["Metallic"].default_value = 0.9; bsdf.inputs["Roughness"].default_value = 0.38
        self.cache[key] = m
        return m

    def leaf(self, key: str, hexc: str, hexc2: str, twig: bool = False) -> bpy.types.Material:
        name = f"leafcard_{key}"
        if name in self.cache:
            return self.cache[name]
        m, nt, bsdf, out = self._new(name)
        p = self.tex.twig(hexc, key) if twig else self.tex.leaf(hexc, hexc2, key)
        img = self._img(nt, p)
        nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.55
        try:
            bsdf.inputs["Subsurface Weight"].default_value = 0.0
            bsdf.inputs["Transmission Weight"].default_value = 0.0
        except KeyError:
            pass
        # a little translucency: leaves glow when backlit
        tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
        nt.links.new(img.outputs["Color"], tr.inputs["Color"])
        mix = nt.nodes.new("ShaderNodeMixShader"); mix.inputs[0].default_value = 0.25
        nt.links.new(bsdf.outputs[0], mix.inputs[1]); nt.links.new(tr.outputs[0], mix.inputs[2])
        trans = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix2 = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(img.outputs["Alpha"], mix2.inputs[0]); nt.links.new(trans.outputs[0], mix2.inputs[1]); nt.links.new(mix.outputs[0], mix2.inputs[2])
        nt.links.new(mix2.outputs[0], out.inputs[0])
        self.cache[name] = m
        return m

    def emitter(self, key: str, md: dict) -> bpy.types.Material:
        """An LED lens (recessed riser step light, post-cap light): the fixture's housing colour with the light off by day
        (photocell); set_mode("dusk") turns its emission on in the colour the material dict carries (else 3000 K)."""
        m, nt, bsdf, out = self._new(key)
        bsdf.inputs["Base Color"].default_value = _hex(md.get("color") or "#d8d2c4") + (1,)
        bsdf.inputs["Roughness"].default_value = 0.3
        bsdf.inputs["Emission Color"].default_value = _hex(_emit_hex(md) or LED_HEX) + (1,)
        bsdf.inputs["Emission Strength"].default_value = 0.0
        LIGHTS["emitters"].append(bsdf)
        self.cache[key] = m
        return m

    def _rough_sawn(self, nt, bsdf, col):
        """Unfinished rough-sawn Douglas fir (8x8 columns, 6x10 beams): warm tan, matte, a low-contrast flat-sawn grain along
        the member, faint band-saw marks across it, mill-to-mill tone mottling and fibre fuzz. The box UVs run along the
        member (U, in 20 ft) and across the face (V, 0..1), so the grain follows posts and beams alike."""
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["UV"], sep.inputs[0])
        cmb = nt.nodes.new("ShaderNodeCombineXYZ")
        mu = nt.nodes.new("ShaderNodeMath"); mu.operation = "MULTIPLY"; mu.inputs[1].default_value = 20.0   # along: ft
        mv = nt.nodes.new("ShaderNodeMath"); mv.operation = "MULTIPLY"; mv.inputs[1].default_value = 0.65   # across: ~ft
        nt.links.new(sep.outputs["X"], mu.inputs[0]); nt.links.new(sep.outputs["Y"], mv.inputs[0])
        nt.links.new(mu.outputs[0], cmb.inputs["X"]); nt.links.new(mv.outputs[0], cmb.inputs["Y"])
        ft = cmb.outputs[0]
        # grain: bands across the face (varying with V), wandering slowly along the member
        mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (0.12, 1.0, 1.0)
        nt.links.new(ft, mp.inputs[0])
        gr = nt.nodes.new("ShaderNodeTexWave"); gr.wave_type = "BANDS"; gr.bands_direction = "Y"
        gr.inputs["Scale"].default_value = 3.2; gr.inputs["Distortion"].default_value = 5.0
        gr.inputs["Detail"].default_value = 2.5; gr.inputs["Detail Scale"].default_value = 1.2
        nt.links.new(mp.outputs[0], gr.inputs["Vector"])
        # band-saw marks: fine bands across the member (varying along it), about 3/4" apart
        sm = nt.nodes.new("ShaderNodeTexWave"); sm.wave_type = "BANDS"; sm.bands_direction = "X"
        sm.inputs["Scale"].default_value = 10.0; sm.inputs["Distortion"].default_value = 1.5; sm.inputs["Detail"].default_value = 1.0
        nt.links.new(ft, sm.inputs["Vector"])
        # mottling (board-to-board, end-to-end tone) and fibre fuzz
        mo = nt.nodes.new("ShaderNodeTexNoise"); mo.inputs["Scale"].default_value = 0.9; mo.inputs["Detail"].default_value = 3.0
        nt.links.new(ft, mo.inputs["Vector"])
        fz = nt.nodes.new("ShaderNodeTexNoise"); fz.inputs["Scale"].default_value = 140.0; fz.inputs["Detail"].default_value = 6.0
        nt.links.new(ft, fz.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")                 # early / late wood
        ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[1].position = 0.9
        ramp.color_ramp.elements[0].color = tuple(min(1, c * 1.06) for c in col) + (1,)
        ramp.color_ramp.elements[1].color = (col[0] * 0.80, col[1] * 0.76, col[2] * 0.72, 1)
        nt.links.new(gr.outputs["Fac"], ramp.inputs[0])
        mot = nt.nodes.new("ShaderNodeMapRange"); mot.inputs["To Min"].default_value = 0.88; mot.inputs["To Max"].default_value = 1.10
        nt.links.new(mo.outputs["Fac"], mot.inputs["Value"])
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = "MULTIPLY"
        sock = lambda coll, ident: next(x for x in coll if x.identifier == ident)
        sock(mx.inputs, "Factor_Float").default_value = 1.0
        nt.links.new(ramp.outputs[0], sock(mx.inputs, "A_Color")); nt.links.new(mot.outputs[0], sock(mx.inputs, "B_Color"))
        self._tint(nt, sock(mx.outputs, "Result_Color"), bsdf)
        h = nt.nodes.new("ShaderNodeMath"); h.operation = "MULTIPLY_ADD"     # height: saw marks + a little fuzz
        h.inputs[1].default_value = 0.6
        nt.links.new(sm.outputs["Fac"], h.inputs[0]); nt.links.new(fz.outputs["Fac"], h.inputs[2])
        self._bump(nt, bsdf, h.outputs[0], 0.18, 0.004)
        bsdf.inputs["Roughness"].default_value = 0.9
        bsdf.inputs["Specular IOR Level"].default_value = 0.3

    def screen(self, key: str, md: dict) -> bpy.types.Material:
        """A motorized screen's fabric (Phifer PVC-coated polyester mesh / clear vinyl): `openness` of it is open weave
        (fraction, or %; else 1 - `alpha`, the louvered engine's photoreal alpha; else 1 - the viewer's `opacity`; default
        20 % = SunTex 80) that sight and sun pass straight through, the rest matte yarn in the fabric colour. The panel is a
        thin box (two faces in every ray's path), so each face passes sqrt(openness)."""
        m, nt, bsdf, out = self._new(key)
        op = md.get("openness")
        if op is not None:
            op = float(op) / 100.0 if float(op) > 1 else float(op)
        else:
            a = md.get("alpha", md.get("opacity"))
            op = 1.0 - float(a) if a is not None else 0.20
        bsdf.inputs["Base Color"].default_value = _hex(md.get("color") or "#2b2b2b") + (1,)
        bsdf.inputs["Roughness"].default_value = 0.9
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs[0].default_value = math.sqrt(max(0.0, min(1.0, op)))
        nt.links.new(bsdf.outputs[0], mx.inputs[1]); nt.links.new(tr.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs[0])
        self.cache[key] = m
        return m


# ====================================================================== geometry accumulation
class Geo:
    """Merged mesh data for one material: vertices, quads/tris, UVs per loop, a tint per loop."""
    def __init__(self):
        self.v: List[Tuple[float, float, float]] = []
        self.f: List[Tuple[int, ...]] = []
        self.uv: List[Tuple[float, float]] = []
        self.tint: List[Tuple[float, float, float, float]] = []

    def face(self, pts, uvs, tint=(1, 1, 1, 1)):
        i0 = len(self.v)
        self.v += [tuple(p) for p in pts]
        self.f.append(tuple(range(i0, i0 + len(pts))))
        self.uv += [tuple(u) for u in uvs]
        self.tint += [tint] * len(pts)


def _rot_fn(b):
    """Box local (centred) -> scene coordinates, honoring rot / rot_axis (the viewer's convention)."""
    cx, cy, cz = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2, (b["z0"] + b["z1"]) / 2
    r = b.get("rot") or 0.0
    ax = b.get("rot_axis") or "y"
    c, s = math.cos(r), math.sin(r)
    if not r:
        return lambda x, y, z: (cx + x, cy + y, cz + z)
    if ax == "z":       # three rotation.y = -rot about the vertical: in plan, local x turns toward +y by rot
        return lambda x, y, z: (cx + x * c - y * s, cy + x * s + y * c, cz + z)
    if ax == "x":       # three rotation.x = rot about scene x: (Y_t = z, Z_t = y) -> z' = z c - y s, y' = z s + y c
        return lambda x, y, z: (cx + x, cy + z * s + y * c, cz + z * c - y * s)
    # "y": three rotation.z = rot about three Z (= scene y): X_t = x, Y_t = z -> x' = x c - z s, z' = x s + z c
    return lambda x, y, z: (cx + x * c - z * s, cy + y, cz + x * s + z * c)


def add_box(g: Geo, b: dict, uv_mode: str, tile: float = 8.0, board_len: float = 20.0, board_w: float = 5.36 * IN,
            u_off: float = 0.0, tint=(1, 1, 1, 1)):
    """A box as 6 quads with UVs. uv_mode 'board': the grain (longest axis) along U in units of the texture length,
    V across the board face in units of the board width; 'tile': UVs in tiles of `tile` ft; 'none'."""
    w, d, h = b["x1"] - b["x0"], b["y1"] - b["y0"], b["z1"] - b["z0"]
    if w <= 1e-6 or d <= 1e-6 or h <= 1e-6:
        return
    T = _rot_fn(b)
    hx, hy, hz = w / 2, d / 2, h / 2
    dims = {"x": w, "y": d, "z": h}
    grain = max(dims, key=dims.get)
    faces = [  # (normal axis, sign, the 4 corners in local coords, CCW seen from outside in the scene's left-handed frame -> flipped later)
        ("z", 1, [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
        ("z", -1, [(-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz)]),
        ("y", 1, [(-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz)]),
        ("y", -1, [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
        ("x", 1, [(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)]),
        ("x", -1, [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)]),
    ]
    idx = {"x": 0, "y": 1, "z": 2}
    for nax, sgn, corners in faces:
        inplane = [a for a in "xyz" if a != nax]
        if uv_mode == "board":
            if grain in inplane:
                ua, va = grain, [a for a in inplane if a != grain][0]
            else:
                ua, va = inplane
            # U along the grain in texture lengths (+ this board's slice), V across the face: the board's width spans the
            # texture once; a thin side face takes a strip of it; a wide fascia stretches it
            uvs = [((p[idx[ua]] + dims[ua] / 2) / board_len + u_off, 0.01 + 0.98 * (p[idx[va]] + dims[va] / 2) / max(board_w, dims[va]))
                   for p in corners]
        elif uv_mode == "tile":
            ua, va = inplane
            ctr = {"x": (b["x0"] + b["x1"]) / 2, "y": (b["y0"] + b["y1"]) / 2, "z": (b["z0"] + b["z1"]) / 2}
            uvs = [((p[idx[ua]] + ctr[ua]) / tile, (p[idx[va]] + ctr[va]) / tile) for p in corners]
        else:
            uvs = [(0, 0)] * 4
        pts = [B(*T(*p)) for p in corners]
        g.face(pts[::-1], uvs[::-1], tint)                 # the y flip mirrors: reverse the winding to keep normals out


def add_quad_board(g: Geo, b: dict, board_len: float = 20.0, board_w: float = 5.36 * IN, u_off: float = 0.0, tint=(1, 1, 1, 1)):
    """A mitred board: the prism over its plan quad (b["quad"], ft) from z0 to z1, the grain along its first edge."""
    q = [(float(x), float(y)) for x, y in b["quad"]]
    z0, z1 = b["z0"], b["z1"]
    ox, oy = q[0]
    L_ = math.hypot(q[1][0] - ox, q[1][1] - oy) or 1.0
    ux, uy = (q[1][0] - ox) / L_, (q[1][1] - oy) / L_
    wid = max(abs((x - ox) * -uy + (y - oy) * ux) for x, y in q) or board_w
    cx, cy = sum(x for x, _ in q) / 4, sum(y for _, y in q) / 4

    def uv(x, y, z, side=False):
        a = ((x - ox) * ux + (y - oy) * uy) / board_len + u_off
        c = (z - z0) if side else abs((x - ox) * -uy + (y - oy) * ux)
        return (a, 0.01 + 0.98 * c / max(board_w, wid))

    def put(P, out):                     # scene-frame polygon -> Blender, wound so its normal points along `out`
        V = [B(*p) for p in P]
        e1 = [V[1][k] - V[0][k] for k in range(3)]; e2 = [V[2][k] - V[0][k] for k in range(3)]
        nrm = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        o = B(*out)
        side = abs(out[2]) < 0.5
        uvs = [uv(*p, side=side) for p in P]
        if nrm[0] * o[0] + nrm[1] * o[1] + nrm[2] * o[2] < 0:
            V, uvs = V[::-1], uvs[::-1]
        g.face(V, uvs, tint)

    put([(x, y, z1) for x, y in q], (0, 0, 1))
    put([(x, y, z0) for x, y in q], (0, 0, -1))
    for k in range(4):
        (xa, ya), (xb, yb) = q[k], q[(k + 1) % 4]
        mx, my = (xa + xb) / 2 - cx, (ya + yb) / 2 - cy
        put([(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)], (mx, my, 0.0))


def add_tris(g: Geo, pts: List[List[float]], tile: float = 8.0, tint=(1, 1, 1, 1)):
    """Scene-frame triangles with planar UVs: courses horizontal along the slope (like the viewer)."""
    for t in range(0, len(pts) - 2, 3):
        A, Bq, C = (np.array(pts[t + k], float) for k in range(3))
        n = np.cross(Bq - A, C - A)
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n /= ln
        t1 = np.cross(np.array([0, 0, 1.0]), n)
        if np.linalg.norm(t1) < 1e-3:
            t1 = np.array([1.0, 0, 0])
        t1 /= np.linalg.norm(t1)
        t2 = np.cross(n, t1)
        if t2[2] < 0:
            t2 = -t2
        uvs = [(float(P.dot(t1)) / tile, float(P.dot(t2)) / tile) for P in (A, Bq, C)]
        g.face([B(*P) for P in (C, Bq, A)], uvs[::-1], tint)


def add_cyl(g: Geo, b: dict, n=20, tint=(1, 1, 1, 1)):
    cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
    r = (b["x1"] - b["x0"]) / 2
    z0, z1 = b["z0"], b["z1"]
    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        p = [(cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1))]
        g.face([B(p[0][0], p[0][1], z0), B(p[0][0], p[0][1], z1), B(p[1][0], p[1][1], z1), B(p[1][0], p[1][1], z0)][::-1],
               [(k / n, 0), (k / n, 1), ((k + 1) / n, 1), ((k + 1) / n, 0)][::-1], tint)
        g.face([B(cx, cy, z1), B(p[1][0], p[1][1], z1), B(p[0][0], p[0][1], z1)], [(0, 0)] * 3, tint)


def build_object(name: str, g: Geo, mat: bpy.types.Material, collection) -> Optional[bpy.types.Object]:
    if not g.f:
        return None
    me = bpy.data.meshes.new(name)
    me.from_pydata(g.v, [], g.f)
    me.validate(clean_customdata=False)
    uvl = me.uv_layers.new(name="UVMap")
    flat_uv = np.array(g.uv, dtype=np.float32)
    if len(uvl.data) == len(flat_uv):
        uvl.data.foreach_set("uv", flat_uv.ravel())
    ca = me.color_attributes.new(name="tint", type="FLOAT_COLOR", domain="CORNER")
    tints = np.array(g.tint, dtype=np.float32)
    if len(ca.data) == len(tints):
        ca.data.foreach_set("color", tints.ravel())
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


# ====================================================================== vegetation
def _leaf_cloud(n, centre, radii, rng, shell=0.7):
    """n points in an ellipsoid, biased toward the surface (leaves live on the outside of a crown)."""
    u = rng.normal(size=(n, 3)); u /= np.linalg.norm(u, axis=1, keepdims=True)
    r = shell + (1 - shell) * rng.random(n) ** 0.5
    r = np.where(rng.random(n) < 0.25, rng.random(n) ** (1 / 3), r)
    return centre + u * r[:, None] * radii


def add_cards(g: Geo, P: np.ndarray, size: float, rng, up_bias=0.4, aspect=1.0, droop=False):
    """A card (quad) at every point, randomly oriented (biased to face up / outward), UV 0..1."""
    for p in P:
        nrm = rng.normal(size=3); nrm[2] += up_bias * 2; nrm /= np.linalg.norm(nrm)
        t1 = np.cross(nrm, rng.normal(size=3)); t1 /= (np.linalg.norm(t1) + 1e-9)
        t2 = np.cross(nrm, t1)
        if droop:                               # spruce twigs: long axis outward and down
            out = np.array([p[0], p[1], 0.0]); out /= (np.linalg.norm(out) + 1e-9)
        s = size * rng.uniform(0.7, 1.3)
        a, b_ = t1 * s * aspect / 2, t2 * s / 2
        q = [p - a - b_, p + a - b_, p + a + b_, p - a + b_]
        g.face([B(*x) for x in q[::-1]], [(0, 0), (1, 0), (1, 1), (0, 1)][::-1])


# ====================================================================== the build
def build(spec_path: str, out_dir: str, quick: bool = False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from decktakeoff.spec import DeckSpec
    from decktakeoff.layout import build_layout
    from decktakeoff.scene import build_scene
    spec = DeckSpec.from_dict(json.load(open(spec_path)))
    if spec.geometry.parts:                 # a composite (two levels, a wrap): the parts placed in the global frame
        from decktakeoff.composite import build_composite
        sc = build_scene(build_composite(spec)[0].layout)
    else:
        sc = build_scene(build_layout(spec))
    D = sc.to_dict()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    col = scn.collection
    tex = Tex(out_dir)
    mats = Mats(D["materials"], tex, spec)
    rng = np.random.default_rng(21)
    groups: Dict[str, Geo] = {}
    def G(key):
        if key not in groups:
            groups[key] = Geo()
        return groups[key]
    BOARD_KEYS = {k for k, m in D["materials"].items() if m.get("palette")}
    TILE = {"shingle": 8.0, "paver": 8.0, "grass": 4.0, "mulch": 4.0, "gravel": 4.0}
    veg = []
    for b in D["boxes"]:
        mk = b["mat"]
        md = D["materials"].get(mk, {})
        shape = b.get("shape") or "box"
        if b["kind"] == "tree" and shape in ("sphere", "cone"):
            veg.append(b)
            continue
        tone = float(b.get("tone") or 0.0)
        if mk in BOARD_KEYS:
            k = int(rng.integers(0, 6))
            L = max(b["x1"] - b["x0"], b["y1"] - b["y0"], b["z1"] - b["z0"])
            u_off = float(rng.uniform(0, max(0.0, 1.0 - L / 20.0)))
            t = 1.0 + 0.05 * tone
            if shape == "mesh":
                add_tris(G(f"{mk}#{k}"), b["pts"], tile=20.0, tint=(t, t, t, 1))
            elif b.get("quad"):
                add_quad_board(G(f"{mk}#{k}"), b, u_off=u_off, tint=(t, t, t, 1))
            else:
                add_box(G(f"{mk}#{k}"), b, "board", u_off=u_off, tint=(t, t, t, 1))
            continue
        pat = md.get("pattern")
        tile = TILE.get(pat, 8.0)
        tint = (1, 1, 1, 1)
        if mk.startswith("wblock") or mk == "cedar":
            v = float(rng.uniform(0.93, 1.06)); tint = (v, v * float(rng.uniform(0.98, 1.02)), v * float(rng.uniform(0.97, 1.01)), 1)
        sawn = mk == "dftimber" or bool(md.get("rough_sawn"))       # rough-sawn timbers: grain along the member, a tone per piece
        if sawn:
            v = float(rng.uniform(0.92, 1.07)); tint = (v, v * float(rng.uniform(0.97, 1.02)), v * float(rng.uniform(0.95, 1.02)), 1)
        if shape == "mesh":
            add_tris(G(mk), b["pts"], tile=tile, tint=tint)
        elif shape == "cyl":
            add_cyl(G(mk), b, tint=tint)
        else:
            add_box(G(mk), b, "board" if sawn else ("tile" if (pat or md.get("grain")) else "none"), tile=tile, tint=tint,
                    u_off=float(rng.uniform(0, 0.9)) if sawn else 0.0)
    for key, g in groups.items():
        if "#" in key:
            base, k = key.split("#")
            m = mats.board(base, int(k))
        else:
            m = mats.get(key)
        build_object(key, g, m, col)
    # ---- vegetation: crowns (spheres) as leaf-card clouds over a dark core; spruce tiers as twig cards on a cone core
    leaf_cols = {"leaf": ("#5f7f2c", "#86a03a"), "leaf2": ("#7a9a35", "#a3b043"), "shrub": ("#8a3424", "#b24a2e"),
                 "shrub2": ("#58702f", "#7d8f3a"), "spruce": ("#4f6f6c", "#6f908a"), "spruce2": ("#5e7f79", "#7c9c95")}
    vg: Dict[str, Geo] = {}
    core = Geo()
    dens = 0.5 if quick else 1.0
    for b in veg:
        mk = b["mat"]
        cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
        rx, ry = (b["x1"] - b["x0"]) / 2, (b["y1"] - b["y0"]) / 2
        if b["shape"] == "sphere":
            rz = (b["z1"] - b["z0"]) / 2
            cz = (b["z0"] + b["z1"]) / 2
            area = 4 * math.pi * ((rx * ry) ** 1.6 + (rx * rz) ** 1.6 + (ry * rz) ** 1.6) ** (1 / 1.6) / 3 ** (1 / 1.6)
            big = max(rx, ry, rz) > 3.0
            size = 0.55 if big else 0.32
            n = int(area * (14 if big else 30) * dens)
            P = _leaf_cloud(n, np.array([cx, cy, cz]), np.array([rx, ry, rz]), rng)
            if mk.startswith("spruce"):
                add_cards(vg.setdefault("twig_" + mk, Geo()), P, 0.9, rng, up_bias=0.1, aspect=2.0)
            else:
                add_cards(vg.setdefault("leaf_" + mk, Geo()), P, size, rng)
            # the dark core (0.82 of the crown) so the crown never reads see-through
            sb = dict(b, x0=cx - rx * 0.8, x1=cx + rx * 0.8, y0=cy - ry * 0.8, y1=cy + ry * 0.8, z0=cz - rz * 0.8, z1=cz + rz * 0.8)
            _ellipsoid(core, sb)
        else:   # cone tier: twigs on the surface, pointing out and down
            r = rx
            h = b["z1"] - b["z0"]
            n = int(math.pi * r * math.hypot(r, h) * 22 * dens)
            t = rng.random(n) ** 0.7                        # more toward the base
            a = rng.uniform(0, 2 * math.pi, n)
            rr = r * (1 - t) * rng.uniform(0.75, 1.02, n)
            P = np.stack([cx + rr * np.cos(a), cy + rr * np.sin(a), b["z0"] + t * h * 0.98 - rng.uniform(0, 0.3, n)], 1)
            add_cards(vg.setdefault("twig_" + mk, Geo()), P, 1.1, rng, up_bias=-0.2, aspect=2.0)
            _cone(core, b, 0.86)
    for key, g in vg.items():
        base = key.split("_", 1)[1]
        c1, c2 = leaf_cols.get(base, ("#5f7f2c", "#86a03a"))
        build_object(key, g, mats.leaf(base, c1, c2, twig=key.startswith("twig")), col)
    if core.f:
        cm, cnt, cb, _ = Mats._new("crown_core")
        cb.inputs["Base Color"].default_value = _hex("#22301a") + (1,)
        cb.inputs["Roughness"].default_value = 0.95
        build_object("crown_core", core, cm, col)
    return spec, sc, D


def _ellipsoid(g: Geo, b, nu=14, nv=8):
    cx, cy, cz = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2, (b["z0"] + b["z1"]) / 2
    rx, ry, rz = (b["x1"] - b["x0"]) / 2, (b["y1"] - b["y0"]) / 2, (b["z1"] - b["z0"]) / 2
    def P(i, j):
        th = math.pi * j / nv; ph = 2 * math.pi * i / nu
        return B(cx + rx * math.sin(th) * math.cos(ph), cy + ry * math.sin(th) * math.sin(ph), cz + rz * math.cos(th))
    for j in range(nv):
        for i in range(nu):
            g.face([P(i, j), P(i, j + 1), P(i + 1, j + 1), P(i + 1, j)], [(0, 0)] * 4)


def _cone(g: Geo, b, s=1.0, n=16):
    cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
    r = (b["x1"] - b["x0"]) / 2 * s
    z0, z1 = b["z0"], b["z0"] + (b["z1"] - b["z0"]) * s
    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        g.face([B(cx + r * math.cos(a0), cy + r * math.sin(a0), z0), B(cx, cy, z1), B(cx + r * math.cos(a1), cy + r * math.sin(a1), z0)], [(0, 0)] * 3)


# ====================================================================== grass (real blades in the near field)
def _grass_patch(name, rng, n_blades=650, size=1.0):
    """A 1' x 1' patch of blades: a bent two-segment strip each, colour per vertex (darker at the root)."""
    g = Geo()
    greens = [(92, 122, 48), (108, 138, 56), (124, 150, 62), (82, 110, 42), (136, 156, 72), (98, 128, 50), (116, 132, 60), (150, 158, 86)]
    lin = lambda c: tuple(((v / 255) / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4) for v in c)
    for _ in range(n_blades):
        x, y = rng.uniform(-size / 2, size / 2), rng.uniform(-size / 2, size / 2)      # centred: a turned patch stays on its cell
        h = rng.uniform(0.16, 0.30)
        w = rng.uniform(0.010, 0.017)
        a = rng.uniform(0, 2 * math.pi)
        lean = rng.uniform(0.05, 0.55)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy * w / 2, dx * w / 2                    # across the blade
        p0 = (x, y, 0.0)
        p1 = (x + dx * h * lean * 0.35, y + dy * h * lean * 0.35, h * 0.55)
        p2 = (x + dx * h * lean, y + dy * h * lean, h * (1.0 - 0.25 * lean))
        c = lin(greens[int(rng.integers(len(greens)))])
        c0 = (c[0] * 0.45, c[1] * 0.5, c[2] * 0.4, 1.0); c1 = (c[0] * 0.8, c[1] * 0.85, c[2] * 0.75, 1.0); c2 = (c[0], c[1], c[2], 1.0)
        v0l, v0r = (p0[0] - px, p0[1] - py, p0[2]), (p0[0] + px, p0[1] + py, p0[2])
        v1l, v1r = (p1[0] - px * 0.8, p1[1] - py * 0.8, p1[2]), (p1[0] + px * 0.8, p1[1] + py * 0.8, p1[2])
        i0 = len(g.v)
        g.v += [B(*v0l), B(*v0r), B(*v1r), B(*v1l), B(*p2)]
        g.f += [(i0, i0 + 1, i0 + 2, i0 + 3), (i0 + 3, i0 + 2, i0 + 4)]
        g.uv += [(0, 0)] * 7
        g.tint += [c0, c0, c1, c1] + [c1, c1, c2]
    return g


def _grass_mask(spec, D):
    """A test for 'no grass here': the deck and its stairs (+ margin), beds, paver bands, walls, flagstones, the house, fences, trunks."""
    from decktakeoff.landscape import _resample, _in_poly
    sm = spec.geometry.site_model or {}
    polys = []
    walls = {w.get("name"): w for w in sm.get("walls", [])}
    for b in sm.get("beds", []):
        if b.get("wall"):
            w = walls[b["wall"]]
            polys.append(_resample(w["path"], 0.5, smooth=w.get("smooth", True)) + [tuple(q) for q in b.get("close", [])])
        else:
            polys.append([tuple(q) for q in b["poly"]])
    segs = []                                               # (polyline, half width)
    for w in sm.get("walls", []):
        segs.append((_resample(w["path"], 0.5, smooth=w.get("smooth", True)), 0.85))
    for p in sm.get("pavers", []):
        segs.append(([tuple(q[:2]) for q in p["path"]], float(p.get("width_in", 16)) / 12 + 0.15))
    for f in sm.get("fences", []):
        segs.append(([tuple(q[:2]) for q in f["path"]], 0.35))
    discs = [(f["at"][0], f["at"][1], max(f.get("size", [3.0, 2.2])) / 2 + 0.15) for f in sm.get("flagstones", [])]
    discs += [(t["at"][0], t["at"][1], 0.9) for t in sm.get("trees", []) if t.get("type", "deciduous") != "shrub"]
    discs += [(t["at"][0], t["at"][1], float(t.get("radius", 2.0)) * 0.8) for t in sm.get("trees", []) if t.get("type") == "shrub"]
    boxes = [(b["x0"] - 0.35, b["x1"] + 0.35, b["y0"] - 0.35, b["y1"] + 0.35) for b in D["boxes"] if b["kind"] in ("tread", "riser", "stringer") or (b.get("tag") or "").startswith("box step")]
    out = [tuple(p) for p in (spec.geometry.outline or [])]
    def seg_d(x, y, pl):
        best = 9e9
        for (ax, ay), (bx, by) in zip(pl, pl[1:]):
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy or 1e-9
            t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            best = min(best, math.hypot(x - (ax + vx * t), y - (ay + vy * t)))
        return best
    def blocked(x, y):
        if y < 0.4:                                         # the house side
            return True
        if out and (_in_poly(x, y, out) or seg_d(x, y, out + out[:1]) < 0.6):
            return True
        if any(_in_poly(x, y, P) for P in polys):
            return True
        if any(seg_d(x, y, pl) < hw for pl, hw in segs):
            return True
        if any(math.hypot(x - cx, y - cy) < r for cx, cy, r in discs):
            return True
        if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in boxes):
            return True
        return False
    return blocked


def add_grass(spec, D, cams: Dict[str, dict], names: List[str], col, reach: float = 34.0, cell: float = 1.0):
    """Instance blade patches on the lawn within `reach` ft of the cameras that will render (and in front of them)."""
    from decktakeoff.landscape import Grade
    sm = spec.geometry.site_model or {}
    gm = sm.get("grade", {})
    grade = Grade(gm.get("points", [[0, 0, 0]]))
    x0, x1, y0, y1 = gm.get("extent", [-40, 60, -12, 36])
    blocked = _grass_mask(spec, D)
    rng = np.random.default_rng(31)
    patches = []
    mat = bpy.data.materials.new("grass_blades")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    attr = nt.nodes.new("ShaderNodeAttribute"); attr.attribute_name = "tint"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent"); nt.links.new(attr.outputs["Color"], tr.inputs["Color"])
    mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs[0].default_value = 0.3
    nt.links.new(bsdf.outputs[0], mx.inputs[1]); nt.links.new(tr.outputs[0], mx.inputs[2]); nt.links.new(mx.outputs[0], out.inputs[0])
    for k in range(3):
        g = _grass_patch(f"grass{k}", rng)
        me = bpy.data.meshes.new(f"grass_patch_{k}")
        me.from_pydata(g.v, [], g.f)
        ca = me.color_attributes.new(name="tint", type="FLOAT_COLOR", domain="CORNER")
        ca.data.foreach_set("color", np.array(g.tint, dtype=np.float32).ravel())
        me.materials.append(mat)
        patches.append(me)
    stations = []
    for nm in names:
        c = cams.get(nm)
        if not c:
            continue
        px, py = c["pos"][0], c["pos"][1]
        ax, ay = c["at"][0] - px, c["at"][1] - py
        L = math.hypot(ax, ay) or 1.0
        stations.append((px, py, ax / L, ay / L, math.radians(float(c.get("fov", 40))) * 0.5 * 1.7))
    n = 0
    xs = np.arange(x0, x1, cell); ys = np.arange(y0, y1, cell)
    for x in xs:
        for y in ys:
            cx, cy = x + cell / 2, y + cell / 2
            ok = False
            for px, py, dx, dy, half in stations:
                vx, vy = cx - px, cy - py
                dd = math.hypot(vx, vy)
                if dd > reach or dd < 0.5:
                    continue
                ang = math.acos(max(-1.0, min(1.0, (vx * dx + vy * dy) / dd)))
                if ang <= half or dd < 4.0:
                    ok = True
                    break
            if not ok or blocked(cx, cy):
                continue
            ob = bpy.data.objects.new(f"grass_{n}", patches[int(rng.integers(3))])
            ob.location = B(cx, cy, grade(cx, cy) - 0.02)
            ob.rotation_euler = (0, 0, float(rng.integers(4)) * math.pi / 2 + float(rng.uniform(-0.05, 0.05)))
            ob.scale = (cell, cell, float(rng.uniform(0.85, 1.15)))
            col.objects.link(ob)
            n += 1
    print(f"grass: {n} patches", flush=True)
    return n


# ====================================================================== light, camera, render
def setup_world(D, spec, sky_strength=0.2, sun_strength=5.0, fill_strength=0.065, fill_sat=0.5):
    scn = bpy.context.scene
    sun = D["meta"].get("sun") or [-0.5, 0.5, 0.7]
    v = mathutils.Vector(B(*sun)).normalized()                  # toward the sun, Blender frame
    w = bpy.data.worlds.new("sky"); scn.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.asin(max(-1, min(1, v.z)))
    sky.sun_rotation = math.atan2(v.x, v.y)       # 0 = +Y, positive toward +X (verified against the sun lamp's shadows)
    sky.altitude = 1700.0                         # Centennial, CO: ~5,850 ft
    sky.air_density = 1.0
    sky.aerosol_density = 1.0
    # Two skies. The camera sees the model's blue sky at sky_strength. Everything else is lit by the same sky, dimmer and pulled
    # halfway to grey: measured on a white plane, the bare model at 0.2 gave R 0.26 / G 0.52 / B 1.03 against the sun's 1.00 /
    # 0.96 / 0.89 — half the light on a horizontal surface and four times bluer than the sun, so white trim in full sun came
    # out blue and the deck brown went grey. A clear sky at ~5,850 ft is ~10-15% of the light on the ground (a daylight
    # white balance reads sunlit white as white); fill 0.065 at half saturation gives ~20% (G) and sunlit white neutral.
    bg = nt.nodes.new("ShaderNodeBackground"); bg.inputs["Strength"].default_value = sky_strength
    hs = nt.nodes.new("ShaderNodeHueSaturation"); hs.inputs["Saturation"].default_value = fill_sat
    fill = nt.nodes.new("ShaderNodeBackground"); fill.inputs["Strength"].default_value = fill_strength
    lp = nt.nodes.new("ShaderNodeLightPath"); mx = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0]); nt.links.new(sky.outputs[0], hs.inputs["Color"]); nt.links.new(hs.outputs[0], fill.inputs[0])
    nt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0]); nt.links.new(fill.outputs[0], mx.inputs[1]); nt.links.new(bg.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs[0])
    ld = bpy.data.lights.new("sun", "SUN")
    ld.energy = sun_strength
    ld.angle = math.radians(0.53)
    ld.color = _sun_rgb(math.degrees(math.asin(max(-1, min(1, v.z)))))   # (1.0, 0.955, 0.89) from 30 deg up: late-summer sun at ~5,850 ft
    ob = bpy.data.objects.new("sun", ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
    LIGHTS["modes"]["day"] = dict(world=w, sun=ob, energy=sun_strength)


# ---------------------------------------------------------------------- time of day: the sun at a local time, blue hour, the lights
LED_HEX = "#ffc78a"           # an LED lens's light when its material dict names none: 3000 K seen at a twilight white balance (sRGB)
LED_LENS = 4.0                # a lens's emission strength at dusk (x --led): it reads as a bright point, it lights almost nothing itself
# Fixture light power from the fixture's lumens (its material dict's "lumens", else the defaults below). The sun lamp's 5 W/m^2 stands
# for ~100,000 lux, and at -5 deg the sky model at strength 1.0 is ~160x brighter than real twilight (~7 lux) on that scale, so a
# fixture keeps the real ratio to the sky at lm x 10.76 (ft units) / 20,000 x 160 = 0.086 W per lumen (x --led).
LM_W = 0.086
LM_RISER, LM_CAP, LM_STRIP_PER_FT = 50.0, 100.0, 150.0   # a recessed riser light, a post-cap light, an LED strip (per ft)
LANTERN_W = 6.0               # a coach lantern on the house
ROOM_HEX, ROOM_GLOW = "#ffb06a", 0.06     # the rooms behind the glass at dusk: 2700 K interior light (emission strength, x --glow)
LIGHTS = dict(emitters=[], fixtures=[], modes={}, mode="day")   # what set_mode() switches between day and dusk


def _emit_hex(md: dict) -> str:
    """The emission colour a material dict carries (the lighting agent's LED lenses), '' when none."""
    for k in ("emission", "emit", "emissive", "glow"):
        v = md.get(k)
        if isinstance(v, str) and v.startswith("#"):
            return v
    return ""


def _emits(key: str, md: dict) -> bool:
    return key in ("led_riser", "led_cap") or bool(_emit_hex(md))


def _sun_rgb(el_deg: float) -> Tuple[float, float, float]:
    """The direct sun's colour by its height: the late-summer midday sun above 30 deg, warming toward the horizon (longer air
    path) — a 15 deg morning sun is ~(1.0, 0.89, 0.74), a 5 deg one ~(1.0, 0.80, 0.58)."""
    hi, lo = (1.0, 0.955, 0.89), (1.0, 0.78, 0.55)
    t = max(0.0, min(1.0, (30.0 - el_deg) / 27.0)) ** 1.5
    return tuple(a + (b - a) * t for a, b in zip(hi, lo))


def _mountain_offset(when, base: float) -> float:
    """The site's UTC offset on that date: Mountain time follows DST (2nd Sunday of March to 1st Sunday of November) when
    the spec's offset is -6 / -7; any other offset is taken as given."""
    from datetime import datetime, timedelta
    if base not in (-6.0, -7.0):
        return base
    mar, nov = datetime(when.year, 3, 8), datetime(when.year, 11, 1)
    start, end = mar + timedelta(days=(6 - mar.weekday()) % 7), nov + timedelta(days=(6 - nov.weekday()) % 7)
    return -6.0 if start <= when < end else -7.0


def sun_at(spec, when: str):
    """Unit vector toward the sun (plan frame) at a local date-time 'YYYY-MM-DDTHH:MM' for the job's site; None without a
    site position. The same NOAA approximation the viewer uses (scene.sun_vector), DST-aware for Mountain time."""
    import dataclasses
    from datetime import datetime
    from decktakeoff.scene import sun_vector
    s = spec.site
    if s.lat is None or s.lon is None or s.rear_azimuth_deg is None:
        return None
    return sun_vector(dataclasses.replace(s, sun_when=when, utc_offset_h=_mountain_offset(datetime.fromisoformat(when), float(s.utc_offset_h))))


def dusk_time(spec, date: str, el_deg: float = -5.0) -> str:
    """The local time (ISO) on that date's evening when the sun has sunk to el_deg: -5 deg is the blue hour, ~25 min after
    sunset — the sky still deep blue, dark enough that the deck lights carry the picture."""
    from datetime import datetime, timedelta
    t = datetime.fromisoformat(f"{date}T15:00")
    while t.hour < 23:
        v = sun_at(spec, t.isoformat(timespec="minutes"))
        if v is None or math.degrees(math.asin(max(-1.0, min(1.0, v[2])))) <= el_deg:
            break
        t += timedelta(minutes=1)
    return t.isoformat(timespec="minutes")


def sun_caption(spec, when: str, v) -> str:
    """'Jun 21, 8:30 AM - sun ENE (70 deg), 37 deg up' for a render's caption / log."""
    from datetime import datetime
    if not v:
        return ""
    rel = math.degrees(math.atan2(-v[0], v[1]))
    az = (spec.site.rear_azimuth_deg + rel) % 360
    el = math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))
    pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    lab = datetime.fromisoformat(when).strftime("%b %-d, %-I:%M %p")
    hgt = f"{el:.0f}° up" if el >= 0 else f"{-el:.0f}° below the horizon"
    return f"{lab} — sun {pts[int((az + 11.25) // 22.5) % 16]} ({az:.0f}°), {hgt}"


def _box_frame(b):
    """A box's centre and its local x / y / z unit axes in the plan frame (rot / rot_axis honoured), as numpy vectors."""
    T = _rot_fn(b)
    c = np.array(T(0.0, 0.0, 0.0))
    return c, [np.array(T(*e)) - c for e in ((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0))]


def add_fixture_lights(D, col) -> int:
    """Real lights at the LED fixtures so the risers throw light on the treads and the post caps on the posts, rails and
    deck (an emissive lens alone lights almost nothing): a spot from every riser light aimed out of the riser and 50 deg
    down; four small points under every post-cap light, one off each face; a downward area light under any other emitter
    (e.g. a roof's LED strip); a point in front of each coach lantern. Hidden until set_mode("dusk")."""
    treads = [b for b in D["boxes"] if b["kind"] == "tread"]

    def light(kind, p, d, energy, rgb, size=0.04, spot=130.0, blend=0.7):
        ld = bpy.data.lights.new(f"fx{len(LIGHTS['fixtures'])}", kind)
        ld.energy = energy
        ld.color = rgb
        ld.shadow_soft_size = size
        if kind == "SPOT":
            ld.spot_size = math.radians(spot)
            ld.spot_blend = blend
        ob = bpy.data.objects.new(ld.name, ld)
        col.objects.link(ob)
        ob.location = B(*[float(q) for q in p])
        if d is not None:
            ob.rotation_euler = mathutils.Vector(B(*[float(q) for q in d])).to_track_quat("-Z", "Y").to_euler()
        ob.hide_render = True
        ob["base_energy"] = energy
        LIGHTS["fixtures"].append(ob)

    for b in D["boxes"]:
        mk = b["mat"]
        md = D["materials"].get(mk, {})
        tag = (b.get("tag") or "").lower()
        if "coach lantern" in tag:
            light("POINT", ((b["x0"] + b["x1"]) / 2, b["y1"] + 0.25, (b["z0"] + b["z1"]) / 2 - 0.1), None, LANTERN_W, _hex(ROOM_HEX), size=0.12)
            continue
        if not _emits(mk, md):
            continue
        rgb = _hex(_emit_hex(md) or LED_HEX)
        c, (ux, uy, uz) = _box_frame(b)
        hx, hy, hz = (b["x1"] - b["x0"]) / 2, (b["y1"] - b["y0"]) / 2, (b["z1"] - b["z0"]) / 2
        what = f"{mk} {b['kind']} {tag} {md.get('light') or ''}"
        if "cap" in what or "post" in what:
            for u, h in ((ux, hx), (-ux, hx), (uy, hy), (-uy, hy)):
                light("POINT", c + u * (h + 0.04) - uz * (hz - 0.02), None, LM_W * float(md.get("lumens") or LM_CAP) / 4, rgb, size=0.03)
            continue
        if "riser" not in what and "step" not in what:
            # any other emitter (an LED strip in a roof's gutter track, a puck): an area light on its underside facing down,
            # its lumens from the dict, else 150 lm per ft of strip
            L_ = 2 * max(hx, hy)
            light("AREA", c - uz * (hz + 0.01), -uz, LM_W * float(md.get("lumens") or LM_STRIP_PER_FT * max(0.25, L_)), rgb)
            ob = LIGHTS["fixtures"][-1]
            ob.data.shape = "RECTANGLE"; ob.data.size = max(0.05, 2 * hx); ob.data.size_y = max(0.05, 2 * hy)
            continue
        # a riser light: out of the riser along the lens's thin horizontal axis, toward the tread it lights (the next tread
        # down, else away from the tread above)
        u, h = (ux, hx) if hx <= hy else (uy, hy)
        zc = c[2]
        below = [t for t in treads if zc - 1.3 <= t["z1"] <= zc + 0.05]
        above = [t for t in treads if t["z1"] > zc + 0.05]
        tc = lambda t: np.array([(t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2, t["z1"]])
        sgn = 1.0
        if below:
            t = min(below, key=lambda t: np.hypot(*(tc(t) - c)[:2]))
            sgn = 1.0 if float(np.dot(tc(t) - c, u)) >= 0 else -1.0
        elif above:
            t = min(above, key=lambda t: np.hypot(*(tc(t) - c)[:2]))
            sgn = -1.0 if float(np.dot(tc(t) - c, u)) >= 0 else 1.0
        out = u * sgn
        aim = out * math.cos(math.radians(50)) - uz * math.sin(math.radians(50))
        light("SPOT", c + out * (h + 0.03), aim, LM_W * float(md.get("lumens") or LM_RISER), rgb, size=0.04)
    n = len(LIGHTS["fixtures"])
    if n:
        print(f"fixture lights: {n}", flush=True)
    return n


def setup_dusk(D, spec, sun_vec, sky_strength=1.0, fill_strength=1.0, fill_sat=0.85, sun_strength=5.0):
    """Twilight: the same physical sky (Blender's multiple-scattering model holds a sun below the horizon: deep blue
    overhead, the afterglow low on the sunset side), seen by the camera and lighting the scene at full strength (no
    daylight fill trick); a warm, weak sun lamp only while the sun is still up. set_mode("dusk") switches to it."""
    scn = bpy.context.scene
    v = mathutils.Vector(B(*sun_vec)).normalized()
    el = math.asin(max(-1, min(1, v.z)))
    w = bpy.data.worlds.new("dusk")
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = el
    sky.sun_rotation = math.atan2(v.x, v.y)
    sky.altitude = 1700.0
    sky.air_density = 1.0
    sky.aerosol_density = 1.0
    bg = nt.nodes.new("ShaderNodeBackground"); bg.inputs["Strength"].default_value = sky_strength
    hs = nt.nodes.new("ShaderNodeHueSaturation"); hs.inputs["Saturation"].default_value = fill_sat
    fill = nt.nodes.new("ShaderNodeBackground"); fill.inputs["Strength"].default_value = fill_strength
    lp = nt.nodes.new("ShaderNodeLightPath"); mx = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0]); nt.links.new(sky.outputs[0], hs.inputs["Color"]); nt.links.new(hs.outputs[0], fill.inputs[0])
    nt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0]); nt.links.new(fill.outputs[0], mx.inputs[1]); nt.links.new(bg.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs[0])
    ob = None
    if el > 0:
        ld = bpy.data.lights.new("sun_dusk", "SUN")
        ld.energy = sun_strength * min(1.0, math.sin(el) / math.sin(math.radians(12)))
        ld.angle = math.radians(0.53)
        ld.color = _sun_rgb(math.degrees(el))
        ob = bpy.data.objects.new("sun_dusk", ld)
        scn.collection.objects.link(ob)
        ob.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
        ob.hide_render = True
    LIGHTS["modes"]["dusk"] = dict(world=w, sun=ob)


def set_mode(mode: str, led: float = 1.0, glow: float = 1.0):
    """Day (sun + daylight fill, LED lenses dark, fixture lights off) or dusk (twilight sky, lenses and fixture lights on,
    the rooms behind the windows lit)."""
    m = LIGHTS["modes"].get(mode)
    if not m:
        return
    bpy.context.scene.world = m["world"]
    for k, mm in LIGHTS["modes"].items():
        if mm.get("sun") is not None:
            mm["sun"].hide_render = k != mode
    dusk = mode == "dusk"
    for bsdf in LIGHTS["emitters"]:
        bsdf.inputs["Emission Strength"].default_value = LED_LENS * led if dusk else 0.0
    for ob in LIGHTS["fixtures"]:
        ob.hide_render = not dusk
        if "base_energy" in ob.keys():
            ob.data.energy = float(ob["base_energy"]) * led
    room = bpy.data.materials.get("interior")      # the house model's rooms behind the glass (house.py "interior")
    if room is not None:
        bsdf = next((n for n in room.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
            bsdf.inputs["Emission Color"].default_value = _hex(ROOM_HEX) + (1,)
            bsdf.inputs["Emission Strength"].default_value = ROOM_GLOW * glow if dusk else 0.0
    LIGHTS["mode"] = mode


def set_sun(v):
    """Move the day sun (sky model + sun lamp) to plan-frame direction v without rebuilding the scene: one Blender run
    renders a station at several times of day (the louvered roof's shade moving across the deck)."""
    m = LIGHTS["modes"].get("day")
    if not m or v is None:
        return
    vb = mathutils.Vector(B(*v)).normalized()
    el = math.asin(max(-1, min(1, vb.z)))
    for n in m["world"].node_tree.nodes:
        if n.type == "TEX_SKY":
            n.sun_elevation = el
            n.sun_rotation = math.atan2(vb.x, vb.y)
    m["sun"].rotation_euler = vb.to_track_quat("Z", "Y").to_euler()
    m["sun"].data.color = _sun_rgb(math.degrees(el))
    m["sun"].data.energy = m.get("energy", 5.0) if el > 0 else 0.0
    LIGHTS["sun_now"] = tuple(v)


def standing_z(D, spec, x: float, y: float) -> float:
    """The walking surface under a camera station: the top of the deck board / tread under (x, y), else the yard's grade
    (geometry.site_model), else 0. Stations with an "eye" height follow the deck and the grade as they change."""
    tops = [b["z1"] for b in D["boxes"] if b["kind"] in ("board", "border", "tread") and not b.get("rot")
            and b["x0"] - 0.25 <= x <= b["x1"] + 0.25 and b["y0"] - 0.25 <= y <= b["y1"] + 0.25]
    if tops:
        return max(tops)
    sm = getattr(spec.geometry, "site_model", None) if spec is not None else None
    if sm:
        from decktakeoff.landscape import grade_at
        return float(grade_at(sm, x, y))
    return 0.0


def camera(name, pos, at, fov_v_deg, size):
    scn = bpy.context.scene
    cd = bpy.data.cameras.new(name)
    cd.sensor_fit = "VERTICAL"
    cd.angle_y = math.radians(fov_v_deg)
    cd.clip_start = 0.3; cd.clip_end = 3000
    ob = bpy.data.objects.new(name, cd)
    scn.collection.objects.link(ob)
    ob.location = B(*pos)
    d = mathutils.Vector(B(*at)) - mathutils.Vector(B(*pos))
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def generic_views(D) -> Dict[str, dict]:
    """The viewer's generic stations (plan feet) when the job has no camera stations of its own."""
    W = D["W"]; x0 = D.get("x_min", 0.0); zt = D["deck_top"]
    cx, cy = x0 + W / 2, (D["y_min"] + D["y_front"]) / 2
    span = max(W, D["y_front"] - D["y_min"], 24)
    yf = D["y_front"]
    return {
        "yard": dict(pos=[cx + span * 0.1, yf + span * 1.0, zt + 6.0], at=[cx, cy, zt - 0.6], fov=40),
        "corner": dict(pos=[x0 + W + span * 0.5, yf + span * 0.5, zt + 6.5], at=[cx, cy, zt - 1.0], fov=40),
        "iso": dict(pos=[cx + span * 0.95, yf + span * 0.8, zt + span * 0.7], at=[cx, cy, zt - 2], fov=40),
        "iso2": dict(pos=[cx - span * 0.95, yf + span * 0.8, zt + span * 0.7], at=[cx, cy, zt - 2], fov=40),
        "ondeck": dict(pos=[x0 + min(W - 2, 2.5), yf - 2.2, zt + 5.6], at=[x0 + W * 0.92, yf - min(6, span * 0.3), zt + 0.4], fov=40),
    }


def render_views(D, out_dir, names, samples=160, size=(1400, 900), quick=False, exposure=0.75, modes=None, default_mode="day",
                 spec=None, date=None):
    """Render the named stations. A name may carry a time: "station@16:00" (that clock time on `date`, or a full
    "@YYYY-MM-DDTHH:MM") renders it with the sun moved there -> station_1600.jpg; "station@dusk" renders it at dusk ->
    station_dusk.jpg. A station may carry its own "mode" ("day" | "dusk"), "exposure" and "samples"; else the mode's
    settings (modes = {mode: {exposure, samples, led, glow}}), else the arguments. Writes OUT/renders.json: per image the
    station, mode, local time and the sun (for captions)."""
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.02 if quick else 0.012
    scn.cycles.use_denoising = True
    try:
        scn.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    scn.cycles.max_bounces = 8
    scn.cycles.diffuse_bounces = 3
    scn.cycles.glossy_bounces = 3
    scn.cycles.transmission_bounces = 6
    scn.cycles.transparent_max_bounces = 24
    scn.cycles.caustics_reflective = False
    scn.cycles.caustics_refractive = False
    scn.cycles.blur_glossy = 1.0
    scn.render.resolution_x, scn.render.resolution_y = size
    scn.render.resolution_percentage = 100
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    # Khronos PBR Neutral keeps a board's hue and saturation where AgX greys it (the deck colour is the point of the
    # picture); +0.75 EV is a photographer's exposure for a sunlit yard with the fill sky (the shade stays readable)
    scn.view_settings.view_transform = "Khronos PBR Neutral"
    scn.view_settings.look = "None"
    scn.view_settings.exposure = exposure
    cams = dict(generic_views(D))
    cams.update(D["meta"].get("cameras") or {})
    done = {}
    base_sun = D["meta"].get("sun")
    side = os.path.join(out_dir, "renders.json")
    try:
        log = json.load(open(side))
    except Exception:
        log = {}
    for tok in names:
        nm, _, at_ = tok.partition("@")
        c = cams.get(nm)
        if not c:
            print("no camera", nm); continue
        mode = "dusk" if at_ == "dusk" else (c.get("mode") or default_mode)
        ms = (modes or {}).get(mode, {})
        if mode != LIGHTS["mode"] and mode in LIGHTS["modes"]:
            set_mode(mode, led=float(ms.get("led", 1.0)), glow=float(ms.get("glow", 1.0)))
        out_nm, iso = nm, LIGHTS.get("dusk_when" if mode == "dusk" else "base_when")
        if at_ and at_ != "dusk" and spec is not None:
            iso = at_ if "T" in at_ else f"{date or spec.site.sun_when.split('T')[0]}T{at_}"
            set_sun(sun_at(spec, iso) or base_sun)
            out_nm = f"{nm}_{iso.split('T')[1].replace(':', '')}"
        elif mode == "dusk":
            out_nm = f"{nm}_dusk" if at_ == "dusk" else nm
        elif base_sun and LIGHTS.get("sun_now") not in (None, tuple(base_sun)):
            set_sun(base_sun)
        scn.view_settings.exposure = float(c.get("exposure", ms.get("exposure", exposure)))
        scn.cycles.samples = int(c.get("samples", ms.get("samples", samples)))
        pos = list(c["pos"])
        if c.get("eye") is not None:            # a person's eye height above whatever they stand on (the deck, else the yard)
            pos[2] = standing_z(D, spec, pos[0], pos[1]) + float(c["eye"])
        cam = camera(f"cam_{out_nm}", pos, c["at"], float(c.get("fov", 40)), size)
        scn.camera = cam
        scn.render.filepath = os.path.join(out_dir, f"{out_nm}.jpg")
        t = time.time()
        bpy.ops.render.render(write_still=True)
        done[out_nm] = scn.render.filepath
        sv = LIGHTS.get("dusk_sun") if mode == "dusk" else (LIGHTS.get("sun_now") or base_sun)
        log[f"{out_nm}.jpg"] = dict(station=nm, mode=mode, when=iso, sun=[round(q, 4) for q in sv] if sv else None,
                                    sun_caption=sun_caption(spec, iso, sv) if (spec is not None and iso and sv) else "")
        try:
            json.dump(log, open(side, "w"), indent=1)
        except Exception:
            pass
        print(f"rendered {out_nm} ({LIGHTS['mode']}, {scn.cycles.samples} samples, {scn.view_settings.exposure:+.2f} EV"
              f"{', ' + log[f'{out_nm}.jpg']['sun_caption'] if log[f'{out_nm}.jpg']['sun_caption'] else ''}) in {time.time() - t:.0f}s -> {scn.render.filepath}", flush=True)
    return done


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opts = {a.split("=")[0]: (a.split("=")[1] if "=" in a else True) for a in argv if a.startswith("--")}
    spec_path, out_dir = args[0], args[1]
    names = args[2:] or ["yard", "corner", "ondeck"]
    os.makedirs(out_dir, exist_ok=True)
    quick = bool(opts.get("--quick"))
    samples = int(opts.get("--samples", 48 if quick else 160))
    size = tuple(int(v) for v in str(opts.get("--size", "1400x900")).split("x"))
    t = time.time()
    spec, sc, D = build(spec_path, out_dir, quick=quick)
    if opts.get("--cameras"):               # camera stations from a file (the site_model.cameras format), over the job's own
        cj = json.load(open(opts["--cameras"]))
        cj = cj.get("cameras", cj)
        D["meta"]["cameras"] = dict(D["meta"].get("cameras") or {}, **{k: v for k, v in cj.items() if isinstance(v, dict) and "pos" in v})
    when = opts.get("--when") or spec.site.sun_when       # --when=YYYY-MM-DDTHH:MM: the sun at another local time than spec.site.sun_when
    if opts.get("--when") and sun_at(spec, when):
        D["meta"]["sun"] = list(sun_at(spec, when))
    print("sun:", sun_caption(spec, when, D["meta"].get("sun")) or "no site position (default sun)", flush=True)
    LIGHTS["base_when"] = when
    setup_world(D, spec, sky_strength=float(opts.get("--sky", 0.2)), sun_strength=float(opts.get("--sun", 5.0)),
                fill_strength=float(opts.get("--fill", 0.065)), fill_sat=float(opts.get("--fill-sat", 0.5)))
    cams = dict(generic_views(D)); cams.update(D["meta"].get("cameras") or {})
    default_mode = "dusk" if opts.get("--dusk") else "day"
    stations = list(dict.fromkeys(n.partition("@")[0] for n in names))
    if any(n.endswith("@dusk") or (cams.get(n.partition("@")[0]) or {}).get("mode", default_mode) == "dusk" for n in names):
        # the blue hour of the hero date (or --dusk-when): sun --dusk-el (default -5 deg), the LED fixtures and the rooms lit
        dw = opts.get("--dusk-when") or dusk_time(spec, when.split("T")[0], float(opts.get("--dusk-el", -5.0)))
        vd = sun_at(spec, dw) or (-0.6, -0.79, -0.087)
        LIGHTS["dusk_when"], LIGHTS["dusk_sun"] = dw, tuple(vd)
        print("dusk:", sun_caption(spec, dw, vd) or dw, flush=True)
        setup_dusk(D, spec, vd, sky_strength=float(opts.get("--dusk-sky", 1.0)), fill_strength=float(opts.get("--dusk-fill", 1.0)),
                   fill_sat=float(opts.get("--dusk-fill-sat", 0.85)), sun_strength=float(opts.get("--sun", 5.0)))
        add_fixture_lights(D, bpy.context.scene.collection)
    if getattr(spec.geometry, "site_model", None) and not opts.get("--no-grass"):
        add_grass(spec, D, cams, stations, bpy.context.scene.collection, reach=float(opts.get("--grass-reach", 34.0)))
    print(f"scene built in {time.time() - t:.0f}s: {len(bpy.data.objects)} objects", flush=True)
    if opts.get("--blend"):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "scene.blend"))
    modes = dict(day=dict(exposure=float(opts.get("--exposure", 0.75)), samples=samples),
                 dusk=dict(exposure=float(opts.get("--dusk-exposure", 3.0)), samples=int(opts.get("--dusk-samples", samples)),
                           led=float(opts.get("--led", 1.0)), glow=float(opts.get("--glow", 1.0))))
    render_views(D, out_dir, names, samples=samples, size=size, quick=quick, exposure=float(opts.get("--exposure", 0.75)),
                 modes=modes, default_mode=default_mode, spec=spec, date=when.split("T")[0])


if __name__ == "__main__":
    main(sys.argv[1:])
