"""Cycles still of one palette spec with the brick painted (uniform paint over the brick faces, recessed joints in the same
paint), else exactly decktakeoff.cycles. Run with the bpy venv:  $S/bvenv/bin/python cycles_palette.py SPEC OUT views... --opts"""
import sys
sys.path.insert(0, "/home/user/Decks-")
import numpy as np
from PIL import Image, ImageFilter
import decktakeoff.cycles as C


def painted_brick(self, hexc, mortar="#c2b9a6", course_in=8.0 / 3.0, brick_in=8.0):
    nm = f"pbrick_{hexc.strip('#')}_{course_in:.3f}_{brick_in:.2f}.png"
    th_ft = 36 * course_in / 12.0
    if self.path(nm):
        return self.path(nm), self.path("h_" + nm), th_ft
    S = 2048
    rng = np.random.default_rng(13)
    base = np.array(C._srgb255(hexc), float)
    col = np.zeros((S, S, 3)) + base * 0.97          # the joints take the same paint (the recess shades them)
    hgt = np.zeros((S, S)) + 0.22
    ch, bw = S / 36.0, S / 12.0
    jt = max(3, int(round(0.375 / course_in * ch)))
    for r in range(36):
        off = (r % 2) * bw / 2 + rng.uniform(-3, 3)
        y0 = int(round(r * ch)); y1 = int(round((r + 1) * ch)) - jt
        for c in range(12):
            x0 = int(round(c * bw + off)); x1 = int(round((c + 1) * bw + off)) - jt
            h_, w_ = y1 - y0, x1 - x0
            if h_ <= 2 or w_ <= 2:
                continue
            patch = np.zeros((h_, w_, 3)) + base * (1 + rng.normal(0, 0.012))
            patch *= (1 + 0.025 * rng.normal(0, 1, (h_, w_)))[..., None]          # the sandy face under the paint
            ey = np.minimum(np.arange(h_), h_ - 1 - np.arange(h_)); ex = np.minimum(np.arange(w_), w_ - 1 - np.arange(w_))
            e = np.minimum.outer(ey, ex)
            hb = np.clip(0.55 + e / 4.0, 0, 1.0) + 0.06 * rng.normal(0, 1, (h_, w_))
            cols_ = np.arange(x0, x1) % S
            col[y0:y1, cols_] = patch
            hgt[y0:y1, cols_] = hb
    col *= (1 + 0.015 * rng.normal(0, 1, (S, S)))[..., None]
    im = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
    hm = Image.fromarray((np.clip(hgt, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
    return self._save(nm, im), self._save("h_" + nm, hm), th_ft


import os
if os.environ.get("PAINTED_BRICK", "1") != "0":
    C.Tex.brick = painted_brick
C.main(sys.argv[1:])
