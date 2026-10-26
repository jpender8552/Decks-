"""The house behind the deck, built from a measured model (geometry.house_model): walls with lap siding and real openings,
windows with sashes, lites and plantation shutters, doors with a security storm door, gable / shed roofs as meshes with
fascia, gutters and downspouts, bays and cantilevered floors, lanterns, window wells. Everything is Box geometry, so the
WebGL viewer and the photoreal renderer draw the same house.

Frame: the deck's plan frame in feet (x along the rear wall from the deck's left end as seen from the yard, y out into the
yard, z above the reference grade). A wall runs from a to b; its outside faces the left-hand normal (-dy, dx), which is the
yard side when walls are listed left to right as seen from the yard."""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

IN = 1 / 12.0

DEFAULT_COLORS = dict(siding="#c9c3a4", trim="#f3f1ea", fascia="#2e463b", roof="#6b655e", door="#ece9df", storm="#141414",
                      foundation="#a9a59c", interior="#3b3632", shutter="#f1efe8", glass="#b4c4cf", gutter="#2e463b", metal="#8f959b")


def materials(model: dict) -> Dict[str, dict]:
    c = dict(DEFAULT_COLORS, **(model.get("colors") or {}))
    return dict(
        siding=dict(color=c["siding"], rough=0.82, label="lap siding"),
        sidinglap=dict(color=c["siding"], rough=0.82),
        htrim=dict(color=c["trim"], rough=0.6, label="trim"),
        hfascia=dict(color=c["fascia"], rough=0.55, label="fascia + gutters"),
        shingle=dict(color=c["roof"], pattern="shingle", rough=0.95, label="asphalt shingles"),
        hdoor=dict(color=c["door"], rough=0.5),
        storm=dict(color=c["storm"], metal=0.5, rough=0.45, label="security storm door"),
        foundation=dict(color=c["foundation"], rough=0.95),
        interior=dict(color=c["interior"], rough=0.95),
        shutter=dict(color=c["shutter"], rough=0.6, label="plantation shutters"),
        hglass=dict(color=c["glass"], metal=0.0, rough=0.05, glass=True, label="glass"),
        hmetal=dict(color=c["metal"], metal=0.85, rough=0.35),
        hsoffit=dict(color=c["trim"], rough=0.7),
    )


class _Builder:
    def __init__(self, add_box: Callable, rot_box: Callable, mesh: Callable, model: dict):
        self.add, self.rot, self.mesh, self.m = add_box, rot_box, mesh, model
        self.exp = float(model.get("exposure_in", 7.0)) * IN

    # --------------------------------------------------------------- primitives along a wall
    def frame(self, w: dict):
        (ax, ay), (bx, by) = w["a"], w["b"]
        L = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = -uy, ux
        return ax, ay, ux, uy, nx, ny, L

    def slab(self, w, u0, u1, z0, z1, d0, d1, kind, mat, phase=0, tag=""):
        """A box on the wall: along u0..u1, z0..z1, from d0 to d1 out from the wall face (negative = inside)."""
        ax, ay, ux, uy, nx, ny, L = self.frame(w)
        if abs(uy) < 1e-9:                  # wall along x: the normal is +-y
            xa, xb = sorted((ax + ux * u0, ax + ux * u1))
            ya, yb = sorted((ay + ny * d0, ay + ny * d1))
            self.add(kind, xa, xb, ya, yb, z0, z1, mat, phase, tag=tag)
        elif abs(ux) < 1e-9:                # wall along y: the normal is +-x
            ya, yb = sorted((ay + uy * u0, ay + uy * u1))
            xa, xb = sorted((ax + nx * d0, ax + nx * d1))
            self.add(kind, xa, xb, ya, yb, z0, z1, mat, phase, tag=tag)
        else:                               # an angled wall: a box rotated about z
            dm, th = (d0 + d1) / 2, (d1 - d0)
            p = (ax + ux * u0 + nx * dm, ay + uy * u0 + ny * dm)
            q = (ax + ux * u1 + nx * dm, ay + uy * u1 + ny * dm)
            self.rot(kind, p[0], p[1], q[0], q[1], z0, z1, mat, phase, th, tag=tag)

    # --------------------------------------------------------------- a wall: slab with openings, lap siding, corner boards
    def wall(self, w: dict, openings: List[dict]):
        z0, z1 = float(w.get("z0", 0.0)), float(w.get("z1", 9.0))
        L = self.frame(w)[6]
        gable = w.get("gable")                      # {"at": u of the peak, "z": peak z} -> the wall top is a gable
        ops = sorted([o for o in openings], key=lambda o: o["u0"])
        # the slab (0.45' thick, inside the face) in rectangles around the openings
        def solid(ua, ub, za, zb):
            if ub - ua > 0.01 and zb - za > 0.01:
                self.slab(w, ua, ub, za, zb, -0.45, -0.02, "house", "siding", tag="wall")
        cuts = sorted(set([0.0, L] + [o["u0"] - 0.3 for o in ops] + [o["u1"] + 0.3 for o in ops]))
        cuts = [c for c in cuts if -1e-6 <= c <= L + 1e-6]
        for ua, ub in zip(cuts, cuts[1:]):
            inside = [o for o in ops if o["u0"] - 0.31 <= ua and ub <= o["u1"] + 0.31]
            zs = [z0]
            for o in sorted(inside, key=lambda o: o["z0"]):
                zs += [o["z0"] - 0.3, o["z1"] + 0.3]
            zs.append(z1)
            for za, zb in zip(zs[0::2], zs[1::2]):
                solid(ua, ub, max(z0, za), min(z1, zb))
        # lap courses: a board face per course plus a 3/8" drip at its bottom edge for the shadow line
        zc = z0 + 0.25
        k = 0
        while zc < z1 - 0.05:
            ztop = min(z1, zc + self.exp)
            segs = [(0.0, L)]
            for o in ops:
                if o["z0"] - 0.3 < ztop and o["z1"] + 0.3 > zc:
                    nxt = []
                    for a, b in segs:
                        if o["u1"] + 0.3 <= a or o["u0"] - 0.3 >= b:
                            nxt.append((a, b))
                        else:
                            if o["u0"] - 0.3 > a:
                                nxt.append((a, o["u0"] - 0.3))
                            if o["u1"] + 0.3 < b:
                                nxt.append((o["u1"] + 0.3, b))
                    segs = nxt
            for a, b in segs:
                if b - a < 0.05:
                    continue
                self.slab(w, a, b, zc, ztop, -0.02, 0.02, "siding", "siding", tag="lap course")
                self.slab(w, a, b, zc, zc + 0.045, 0.02, 0.055, "siding", "sidinglap", tag="lap drip")
            zc = ztop
            k += 1
        # the gable triangle above z1: siding courses clipped to the rake lines, as meshes
        if gable:
            self.gable_end(w, float(gable["at"]), float(gable["z"]))
        # corner boards at both ends
        for u in (0.0, L):
            uu = max(0.0, min(L - 0.29, u - 0.0 if u == 0.0 else u - 0.29))
            self.slab(w, uu, uu + 0.29, z0, z1, 0.0, 0.07, "trim", "htrim", tag="corner board")
        # foundation strip below the siding — only under walls that stand on grade (not a cantilevered floor or a bay)
        if 0.05 < z0 < 1.5 and not w.get("no_foundation"):
            self.slab(w, 0.0, L, -0.3, z0, -0.45, 0.0, "house", "foundation", tag="foundation")

    def gable_end(self, w, at, zp):
        ax, ay, ux, uy, nx, ny, L = self.frame(w)
        z1 = float(w.get("z1", 9.0))
        P = lambda u, z, d=0.0: [ax + ux * u + nx * d, ay + uy * u + ny * d, z]
        # the triangle as a mesh just proud of the wall face, siding coloured; lap lines as thin strips
        tri = [P(0.0, z1, 0.01), P(L, z1, 0.01), P(at, zp, 0.01)]
        self.mesh("house", tri, "siding", tag="gable end")
        zc = z1 + self.exp
        while zc < zp - 0.1:
            fl = (zc - z1) / (zp - z1)
            ua, ub = at * fl, L - (L - at) * fl
            if ub - ua > 0.2:
                self.slab(w, ua, ub, zc, zc + 0.045, 0.01, 0.045, "siding", "sidinglap", tag="gable lap drip")
            zc += self.exp

    # --------------------------------------------------------------- openings
    def window(self, w, o):
        u0, u1, z0, z1 = o["u0"], o["u1"], o["z0"], o["z1"]
        tw = float(o.get("trim_in", 3.5)) * IN
        # trim (casing) proud of the siding, sill nose
        self.slab(w, u0 - tw, u1 + tw, z1, z1 + tw, 0.0, 0.08, "trim", "htrim", tag="window head trim")
        self.slab(w, u0 - tw, u1 + tw, z0 - tw, z0, 0.0, 0.1, "trim", "htrim", tag="window sill")
        self.slab(w, u0 - tw, u0, z0, z1, 0.0, 0.08, "trim", "htrim", tag="window side trim")
        self.slab(w, u1, u1 + tw, z0, z1, 0.0, 0.08, "trim", "htrim", tag="window side trim")
        # the vinyl frame and the lites (fractions of the width), glass set back, mullions
        fr = 0.12
        self.slab(w, u0, u1, z1 - fr, z1, -0.2, 0.0, "trim", "htrim", tag="window frame")
        self.slab(w, u0, u1, z0, z0 + fr, -0.2, 0.0, "trim", "htrim", tag="window frame")
        self.slab(w, u0, u0 + fr, z0, z1, -0.2, 0.0, "trim", "htrim", tag="window frame")
        self.slab(w, u1 - fr, u1, z0, z1, -0.2, 0.0, "trim", "htrim", tag="window frame")
        lites = o.get("lites") or [1.0]
        acc, xs = 0.0, []
        for f in lites[:-1]:
            acc += f
            xs.append(u0 + (u1 - u0) * acc)
        for xm in xs:
            self.slab(w, xm - 0.08, xm + 0.08, z0, z1, -0.2, -0.01, "trim", "htrim", tag="window mullion")
        if o.get("meeting_rail"):          # single / double hung
            zm = z0 + (z1 - z0) * float(o["meeting_rail"])
            self.slab(w, u0, u1, zm - 0.06, zm + 0.06, -0.2, -0.01, "trim", "htrim", tag="meeting rail")
        self.slab(w, u0 + fr, u1 - fr, z0 + fr, z1 - fr, -0.16, -0.14, "glass", "hglass", tag="glass")
        if o.get("shutters", True):
            self.shutters(w, u0 + fr, u1 - fr, z0 + fr, z1 - fr, o)
        self.slab(w, u0, u1, z0, z1, -1.6, -1.5, "house", "interior", tag="room")
        if o.get("half_round"):            # an arched transom / gable window: a fan of thin wedges
            pass

    def shutters(self, w, u0, u1, z0, z1, o):
        """Interior plantation shutters seen through the glass: panels about 16" wide with 2" stiles, a divider rail at the
        sash split (or mid-height on a tall window), 3-1/2" louvers (hidden tilt rod) set open so the dark room shows between them."""
        d0, d1 = -0.43, -0.37            # between the glass (-0.15) and the house body's face (-0.45)
        n = max(1, int(round((u1 - u0) / 1.35)))
        st, lv, gap = 2 * IN, 3.5 * IN, 0.6 * IN
        zm = z0 + (z1 - z0) * float(o.get("meeting_rail", 0.5)) if (o.get("meeting_rail") or z1 - z0 > 4.2) else None
        self.slab(w, u0, u1, z0, z0 + st, d0, d1, "shutter", "shutter", tag="shutter rail")
        self.slab(w, u0, u1, z1 - st, z1, d0, d1, "shutter", "shutter", tag="shutter rail")
        if zm is not None:
            self.slab(w, u0, u1, zm - st / 2, zm + st / 2, d0, d1, "shutter", "shutter", tag="shutter divider rail")
        bands = [(z0 + st, zm - st / 2), (zm + st / 2, z1 - st)] if zm is not None else [(z0 + st, z1 - st)]
        for k in range(n + 1):
            uc = u0 + (u1 - u0) * k / n
            a, b = (uc, uc + st) if k == 0 else ((uc - st, uc) if k == n else (uc - st, uc + st))
            self.slab(w, a, b, z0, z1, d0, d1 + 0.01, "shutter", "shutter", tag="shutter stile")
        for k in range(n):
            ua = u0 + (u1 - u0) * k / n + (st if k == 0 else st)
            ub = u0 + (u1 - u0) * (k + 1) / n - st
            for za, zb in bands:
                zc = za + 0.02
                while zc + lv <= zb + 1e-6:
                    self.slab(w, ua, ub, zc, zc + lv - gap, d0 + 0.012, d1 - 0.012, "shutter", "shutter", tag="shutter louver")
                    zc += lv

    def arch_window(self, w, o):
        """A half-round window: centre u, base z, radius r (ft)."""
        uc, zb, r = o["u"], o["z0"], o["r"]
        ax, ay, ux, uy, nx, ny, L = self.frame(w)
        P = lambda u, z, d: [ax + ux * u + nx * d, ay + uy * u + ny * d, z]
        n = 12
        for k in range(n):
            a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
            tri = [P(uc, zb, -0.12), P(uc + r * math.cos(a0), zb + r * math.sin(a0), -0.12), P(uc + r * math.cos(a1), zb + r * math.sin(a1), -0.12)]
            self.mesh("glass", tri, "hglass", tag="arch window glass")
            r2 = r + 0.25
            band = [P(uc + r * math.cos(a0), zb + r * math.sin(a0), 0.06), P(uc + r2 * math.cos(a0), zb + r2 * math.sin(a0), 0.06),
                    P(uc + r2 * math.cos(a1), zb + r2 * math.sin(a1), 0.06), P(uc + r * math.cos(a0), zb + r * math.sin(a0), 0.06),
                    P(uc + r2 * math.cos(a1), zb + r2 * math.sin(a1), 0.06), P(uc + r * math.cos(a1), zb + r * math.sin(a1), 0.06)]
            self.mesh("trim", band, "htrim", tag="arch window trim")
        self.slab(w, uc - r - 0.25, uc + r + 0.25, zb - 0.2, zb, 0.0, 0.08, "trim", "htrim", tag="arch window sill")

    def door(self, w, o):
        u0, u1, z0, z1 = o["u0"], o["u1"], o["z0"], o["z1"]
        tw = 3.5 * IN
        self.slab(w, u0 - tw, u1 + tw, z1, z1 + tw, 0.0, 0.08, "trim", "htrim", tag="door head trim")
        self.slab(w, u0 - tw, u0, z0, z1, 0.0, 0.08, "trim", "htrim", tag="door casing")
        self.slab(w, u1, u1 + tw, z0, z1, 0.0, 0.08, "trim", "htrim", tag="door casing")
        self.slab(w, u0, u1, z0, z1, -0.35, -0.2, "house", "hdoor", tag="entry door")
        if o.get("storm") == "security":
            # black steel security storm door: frame, vertical pickets, a scroll band at the push bar, kick plate
            self.slab(w, u0 + 0.02, u1 - 0.02, z1 - 0.18, z1 - 0.02, -0.05, 0.03, "storm", "storm", tag="storm door frame")
            self.slab(w, u0 + 0.02, u1 - 0.02, z0 + 0.02, z0 + 0.7, -0.05, 0.03, "storm", "storm", tag="storm door kick panel")
            self.slab(w, u0 + 0.02, u0 + 0.16, z0, z1, -0.05, 0.03, "storm", "storm", tag="storm door stile")
            self.slab(w, u1 - 0.16, u1 - 0.02, z0, z1, -0.05, 0.03, "storm", "storm", tag="storm door stile")
            n = int((u1 - u0) / 0.33)
            for k in range(1, n):
                up = u0 + (u1 - u0) * k / n
                self.slab(w, up - 0.025, up + 0.025, z0 + 0.7, z1 - 0.18, -0.04, 0.0, "storm", "storm", tag="storm door picket")
            self.slab(w, u0 + 0.16, u1 - 0.16, z1 - 0.62, z1 - 0.18, -0.045, 0.0, "storm", "storm", tag="storm door top scroll")
            zs = z0 + (z1 - z0) * 0.42
            self.slab(w, u0 + 0.16, u1 - 0.16, zs, zs + 0.45, -0.045, 0.0, "storm", "storm", tag="storm door scroll band")
            self.slab(w, u1 - 0.45, u1 - 0.3, zs + 0.1, zs + 0.18, 0.0, 0.08, "storm", "hmetal", tag="storm door handle")

    # --------------------------------------------------------------- roofs, gutters, extras
    def gable_roof(self, r: dict):
        """rect x0..x1, y0..y1; ridge along y ("axis": "y") at x = ridge_at, or along x at y = ridge_at; eave z, ridge z."""
        x0, x1, y0, y1 = r["rect"]
        ze, zr = float(r["z_eave"]), float(r["z_ridge"])
        th = 0.45
        if r.get("axis", "y") == "y":
            xr = float(r["ridge_at"])
            for xa, xb in ((x0, xr), (xr, x1)):
                za, zb = (ze, zr) if xa == x0 else (zr, ze)
                quad = [[xa, y0, za + th], [xb, y0, zb + th], [xb, y1, zb + th], [xa, y0, za + th], [xb, y1, zb + th], [xa, y1, za + th]]
                self.mesh("roof", quad, "shingle", tag="roof plane")
                under = [[xa, y0, za], [xb, y1, zb], [xb, y0, zb], [xa, y0, za], [xa, y1, za], [xb, y1, zb]]
                self.mesh("roof", under, "hsoffit", tag="roof soffit")
            # fascia along both eaves (x0 and x1 sides), rake boards along the gable ends (y0, y1)
            for xe in (x0, x1):
                self.add("trim", xe - 0.04, xe + 0.04, y0, y1, ze - 0.35, ze + th, "hfascia", 0, tag="fascia")
            for ye in (y0, y1):
                for xa, xb, za, zb in ((x0, xr, ze, zr), (xr, x1, zr, ze)):
                    self.rake(xa, ye, za, xb, ye, zb, th)
        else:
            yr = float(r["ridge_at"])
            for ya, yb in ((y0, yr), (yr, y1)):
                za, zb = (ze, zr) if ya == y0 else (zr, ze)
                quad = [[x0, ya, za + th], [x1, ya, za + th], [x1, yb, zb + th], [x0, ya, za + th], [x1, yb, zb + th], [x0, yb, zb + th]]
                self.mesh("roof", quad, "shingle", tag="roof plane")
            for ye in (y0, y1):
                self.add("trim", x0, x1, ye - 0.04, ye + 0.04, ze - 0.35, ze + th, "hfascia", 0, tag="fascia")
            for xe in (x0, x1):
                for ya, yb, za, zb in ((y0, yr, ze, zr), (yr, y1, zr, ze)):
                    self.rake(xe, ya, za, xe, yb, zb, th)

    def rake(self, xa, ya, za, xb, yb, zb, th):
        """A sloped rake board as a thin mesh strip from (xa, ya, za) to (xb, yb, zb)."""
        hb = 0.55
        quad = [[xa, ya, za - 0.25], [xb, yb, zb - 0.25], [xb, yb, zb + th + 0.05], [xa, ya, za - 0.25], [xb, yb, zb + th + 0.05], [xa, ya, za + th + 0.05]]
        self.mesh("trim", quad, "hfascia", tag="rake board")

    def shed_roof(self, r: dict):
        """rect; low edge on "low" side ("+y" = toward the yard); z_low, z_high; a gutter along the low edge."""
        x0, x1, y0, y1 = r["rect"]
        zl, zh = float(r["z_low"]), float(r["z_high"])
        th = 0.4
        if r.get("low", "+y") == "+y":
            quad = [[x0, y0, zh + th], [x1, y0, zh + th], [x1, y1, zl + th], [x0, y0, zh + th], [x1, y1, zl + th], [x0, y1, zl + th]]
            self.mesh("roof", quad, "shingle", tag="shed roof")
            under = [[x0, y0, zh], [x1, y1, zl], [x1, y0, zh], [x0, y0, zh], [x0, y1, zl], [x1, y1, zl]]
            self.mesh("roof", under, "hsoffit", tag="shed soffit")
            self.add("trim", x0, x1, y1 - 0.04, y1 + 0.04, zl - 0.3, zl + th, "hfascia", 0, tag="fascia")
            if r.get("gutter", True):
                self.add("gutter", x0, x1, y1 + 0.04, y1 + 0.42, zl - 0.15, zl + 0.25, "hfascia", 0, tag="5\" K gutter")
            for xe in (x0, x1):
                self.rake(xe, y0, zh, xe, y1, zl, th)

    def downspout(self, d: dict):
        x, y = d["at"]
        z1 = float(d["z1"])
        z0 = float(d.get("z0", 0.0))
        s = 0.17
        self.add("gutter", x - s, x + s, y, y + 0.22, z0 + 0.6, z1, "htrim" if d.get("color") == "trim" else "siding", 0, tag="downspout")
        self.add("gutter", x - s, x + s, y, y + 1.2, z0, z0 + 0.3, "htrim" if d.get("color") == "trim" else "siding", 0, tag="downspout elbow + splash")

    def lantern(self, d: dict):
        x, y, z = d["at"]
        self.add("storm", x - 0.22, x + 0.22, y + 0.02, y + 0.42, z - 0.55, z + 0.3, "storm", 0, tag="coach lantern")
        self.add("glass", x - 0.16, x + 0.16, y + 0.06, y + 0.38, z - 0.4, z + 0.15, "hglass", 0, tag="lantern glass")
        self.add("storm", x - 0.1, x + 0.1, y, y + 0.08, z - 0.7, z + 0.4, "storm", 0, tag="lantern back plate")

    def window_well(self, d: dict):
        x0, x1 = d["x"]
        dep = float(d.get("depth", 1.6))
        z_top = float(d.get("z_top", 0.4))
        n = 7
        for k in range(n):            # corrugated galvanized half-ring as facets
            a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
            cx, rx = (x0 + x1) / 2, (x1 - x0) / 2
            pa = (cx - rx * math.cos(a0), dep * math.sin(a0)); pb = (cx - rx * math.cos(a1), dep * math.sin(a1))
            self.rot("well", pa[0], pa[1], pb[0], pb[1], z_top - 2.5, z_top, "hmetal", 0, 0.05, tag="window well (corrugated)")
        if d.get("cover"):
            self.add("well", x0 + 0.05, x1 - 0.05, 0.02, dep - 0.05, z_top - 0.02, z_top + 0.03, "storm", 0, tag="window well cover")


def build_house(model: dict, add: Callable, rot_box: Callable, add_mesh: Callable) -> None:
    b = _Builder(add, rot_box, add_mesh, model)
    walls = model.get("walls", [])
    ops_by_wall: Dict[int, List[dict]] = {}
    for o in model.get("openings", []):
        ops_by_wall.setdefault(int(o["wall"]), []).append(o)
    for i, w in enumerate(walls):
        cut = [o for o in ops_by_wall.get(i, []) if o.get("type", "window") != "arch"]
        b.wall(w, cut)
        for o in ops_by_wall.get(i, []):
            t = o.get("type", "window")
            if t == "door":
                b.door(w, o)
            elif t == "arch":
                b.arch_window(w, o)
            elif t == "void":
                continue                # an open bay / a passage: the wall is cut, nothing drawn in it
            else:
                b.window(w, o)
    for g in model.get("gables", []):           # a gable end above an eave line: {a, b, z, peak_u, peak_z}
        b.gable_end({"a": g["a"], "b": g["b"], "z1": g["z"]}, float(g["peak_u"]), float(g["peak_z"]))
    for s in model.get("soffits", []):          # undersides of cantilevered floors / bays
        x0, x1, y0, y1, z = s
        add("trim", x0, x1, y0, y1, z - 0.08, z, "hsoffit", 0, tag="soffit")
    for m in model.get("masses", []):           # solid bodies behind the walls (blocks the light)
        x0, x1, y0, y1, z0, z1 = m
        add("house", x0, x1, y0, y1, z0, z1, "interior", 0, tag="house body")
    for r in model.get("roofs", []):
        if r.get("type") == "shed":
            b.shed_roof(r)
        else:
            b.gable_roof(r)
    for d in model.get("downspouts", []):
        b.downspout(d)
    for d in model.get("lanterns", []):
        b.lantern(d)
    for d in model.get("window_wells", []):
        b.window_well(d)
    for bx in model.get("boxes", []):          # small fixtures: outlets, hose bibs, meters
        x0, x1, y0, y1, z0, z1 = bx["box"]
        add("trim", x0, x1, y0, y1, z0, z1, bx.get("mat", "htrim"), 0, tag=bx.get("name", "fixture"))
    for c in model.get("columns", []):          # pilasters / porch columns: [x0, x1, y0, y1, z0, z1]
        x0, x1, y0, y1, z0, z1 = c
        add("trim", x0, x1, y0, y1, z0, z1, "htrim", 0, tag="column")
