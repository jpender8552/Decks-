"""The house behind the deck, built from a measured model (geometry.house_model): walls with lap siding, vertical-groove
siding (T1-11 / channel boards, real grooves) or brick veneer, painted fields and trim bands, real openings (windows with
sashes, lites, plantation shutters or blinds; sliding patio doors with their panels, tracks and screens; doors with a security
storm door; brick rowlock sills), gable / shed / hip / free-form roofs as meshes with fascia, box soffits, gutters and
downspouts, chimneys, bays and cantilevered floors, lanterns, window wells. Everything is Box geometry, so the WebGL viewer
and the photoreal renderer draw the same house.

Frame: the deck's plan frame in feet (x along the rear wall from the deck's left end as seen from the yard, y out into the
yard, z above the reference grade). A wall runs from a to b; its outside faces the left-hand normal (-dy, dx), which is the
yard side when walls are listed left to right as seen from the yard.

Wall keys beyond a/b/z0/z1: cladding "lap" (default; exposure_in courses) | "vertical" (groove_in spacing, groove_off first
groove from a, relief_in) | "brick" | "plain"; mat (the cladding material); panels [{u0,u1,z0,z1,mat}] (painted fields);
bands [{z0,z1[,u0,u1][,mat][,d]}] (trim boards); corners ["a","b"] + corner_mat; top [[u,z],...] (a sloped / gable top
edge above z1); foundation (bool); thick. Opening keys beyond u0/u1/z0/z1: type window | slider | door | arch | void;
casing (bool), casing_mat, casing_in, frame_mat, sill "trim" | "rowlock" | "none", head "soldier", blinds, shutters,
panels / ops / screen (sliders)."""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

IN = 1 / 12.0

DEFAULT_COLORS = dict(siding="#c9c3a4", trim="#f3f1ea", fascia="#2e463b", roof="#6b655e", door="#ece9df", storm="#141414",
                      foundation="#a9a59c", interior="#3b3632", shutter="#f1efe8", glass="#b4c4cf", gutter="#2e463b", metal="#8f959b")
# colours only the newer features use (painted fields, brick, vinyl frames, screens, blinds, chimney caps)
EXTRA_COLORS = dict(accent="#5c3833", brick="#b8945f", mortar="#c2b9a6", frame="#e6e2d6", screen="#26282a", blind="#ece6d6",
                    cap="#8a8680", soil="#3f3328")


def _shade(hexc: str, k: float) -> str:
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    f = lambda v: max(0, min(255, int(round(v * (1 + k)))))
    return "#%02x%02x%02x" % (f(r), f(g), f(b))


def materials(model: dict) -> Dict[str, dict]:
    c = dict(DEFAULT_COLORS)
    c.update(EXTRA_COLORS)
    c.update(model.get("colors") or {})
    out = dict(
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
        hsoffit=dict(color=c.get("soffit") or c["trim"], rough=0.7),
    )
    tex = model.get("siding_texture")            # "rsawn": rough-sawn plywood / cedar grain on the siding (photoreal + viewer)
    if tex or model.get("siding_label"):
        out["siding"] = dict(out["siding"], label=model.get("siding_label") or out["siding"]["label"], **({"pattern": tex} if tex else {}))
    course = float(model.get("brick_course_in", 8.0 / 3.0))
    out.update(
        siding2=dict(color=c["accent"], rough=0.82, label="painted siding (accent)", **({"pattern": tex} if tex else {})),
        hgroove=dict(color=_shade(c["siding"], -0.55), rough=0.95),
        haccent=dict(color=c["accent"], rough=0.62, label="accent trim"),
        hbrick=dict(color=c["brick"], mortar=c["mortar"], pattern="hbrick", rough=0.92, course_in=course,
                    brick_in=float(model.get("brick_len_in", 8.0)), label="brick veneer"),
        hframe=dict(color=c["frame"], rough=0.45, label="vinyl window + door frames"),
        hscreen=dict(color=c["screen"], rough=0.9, opacity=0.6, label="insect screen"),
        hblind=dict(color=c["blind"], rough=0.6, label="blinds"),
        hcap=dict(color=c["cap"], rough=0.85, label="chimney cap"),
        hsoil=dict(color=c["soil"], rough=1.0, label="bed / soil at the house"),
    )
    return out


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
        if w.get("cladding", "lap") != "lap":
            return self.wall_v2(w, openings)
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

    # --------------------------------------------------------------- vertical-groove / brick / plain walls
    @staticmethod
    def margin(o) -> float:
        """How far the wall's cladding stops short of an opening: the casing width (+ a hair) when it has a casing, else
        nothing (brick returns to the frame)."""
        if o.get("type") == "void":
            return 0.0
        if not o.get("casing", True):
            return 0.0
        return float(o.get("casing_in", o.get("trim_in", 3.5))) * IN + 0.01

    @staticmethod
    def _top_at(top, u, z1):
        """The wall's top edge at u: the piecewise-linear `top` [[u, z], ...] or the flat z1."""
        if not top:
            return z1
        pts = sorted((float(a), float(b)) for a, b in top)
        if u <= pts[0][0]:
            return pts[0][1]
        for (ua, za), (ub, zb) in zip(pts, pts[1:]):
            if ua <= u <= ub:
                return za + (zb - za) * (u - ua) / max(1e-9, ub - ua)
        return pts[-1][1]

    def _upper(self, w, ua, ub, z1, d0, d1, kind, mat, tag):
        """The part of a strip (u ua..ub) above z1 up to the sloped top: a box to the lower corner, a mesh quad above it."""
        top = w.get("top")
        if not top:
            return
        ta, tb = self._top_at(top, ua, z1), self._top_at(top, ub, z1)
        lo = min(ta, tb)
        if lo - z1 > 0.01:
            self.slab(w, ua, ub, z1, lo, d0, d1, kind, mat, tag=tag)
        if abs(ta - tb) > 0.005:
            ax, ay, ux, uy, nx, ny, L = self.frame(w)
            P = lambda u, z, d: [ax + ux * u + nx * d, ay + uy * u + ny * d, z]
            if ta > tb:
                tri = [P(ua, lo, d1), P(ub, lo, d1), P(ua, ta, d1)]
            else:
                tri = [P(ua, lo, d1), P(ub, lo, d1), P(ub, tb, d1)]
            self.mesh(kind, tri, mat, tag=tag)

    def wall_v2(self, w: dict, openings: List[dict]):
        clad = w.get("cladding", "vertical")
        z0, z1 = float(w.get("z0", 0.0)), float(w.get("z1", 9.0))
        ax, ay, ux, uy, nx, ny, L = self.frame(w)
        th = float(w.get("thick", 0.45))
        ops = sorted([o for o in openings], key=lambda o: o["u0"])
        face = 0.0 if clad in ("brick", "plain") else -0.02          # the slab's face: the cladding itself, or the groove bottoms
        slab_mat = w.get("mat") or {"brick": "hbrick", "plain": "siding", "vertical": "hgroove"}[clad]
        if clad == "vertical":
            slab_mat = w.get("groove_mat", "hgroove")
        # the slab in rectangles around the openings (each opening's own margin)
        cuts = sorted(set([0.0, L] + [o["u0"] - self.margin(o) for o in ops] + [o["u1"] + self.margin(o) for o in ops]))
        cuts = [c for c in cuts if -1e-6 <= c <= L + 1e-6]
        for ua, ub in zip(cuts, cuts[1:]):
            if ub - ua < 0.005:
                continue
            inside = [o for o in ops if o["u0"] - self.margin(o) - 1e-6 <= ua and ub <= o["u1"] + self.margin(o) + 1e-6]
            zs = [z0]
            for o in sorted(inside, key=lambda o: o["z0"]):
                zs += [o["z0"] - self.margin(o), o["z1"] + self.margin(o)]
            zs.append(z1)
            for za, zb in zip(zs[0::2], zs[1::2]):
                za, zb = max(z0, za), min(z1, zb)
                if zb - za > 0.005:
                    self.slab(w, ua, ub, za, zb, -th, face, "house", slab_mat, tag="wall")
            self._upper(w, ua, ub, z1, -th, face, "house", slab_mat, "wall (gable / rake)")
        if clad == "vertical":
            self.vertical_boards(w, ops, z0, z1, L)
        # painted fields on brick / plain walls sit proud of the face as panels
        if clad in ("brick", "plain"):
            for p in w.get("panels", []):
                self.slab(w, p["u0"], p["u1"], p["z0"], p["z1"], 0.0, float(p.get("d", 0.06)), "trim", p.get("mat", "haccent"),
                          tag=p.get("name", "panel"))
        for bd in w.get("bands", []):           # horizontal trim boards, stopped at the openings (casings) they would cross
            d0, d1 = (0.0, float(bd["d"])) if isinstance(bd.get("d"), (int, float)) else tuple(bd.get("d", (0.0, 0.06)))
            segs = [(float(bd.get("u0", 0.0)), float(bd.get("u1", L)))]
            for o in ops:
                m = self.margin(o)
                if o["z0"] - m < bd["z1"] and o["z1"] + m > bd["z0"]:
                    segs = [s for a, b in segs for s in ((a, min(b, o["u0"] - m)), (max(a, o["u1"] + m), b)) if s[1] - s[0] > 0.01]
            for a, b in segs:
                self.slab(w, a, b, bd["z0"], bd["z1"], d0, d1, "trim", bd.get("mat", "haccent"), tag=bd.get("name", "trim band"))
            if bd.get("dentils"):                # blocks along the band: {w_in, h_in, oc_in, z0, mat}
                dn = bd["dentils"]
                dw, oc = float(dn.get("w_in", 4.0)) * IN, float(dn.get("oc_in", 6.0)) * IN
                dz0 = float(dn.get("z0", bd["z0"])); dz1 = dz0 + float(dn.get("h_in", 2.5)) * IN
                for a, b in segs:
                    u = a + (oc - dw) / 2
                    while u + dw <= b + 1e-6:
                        self.slab(w, u, u + dw, dz0, dz1, d1, d1 + 0.06, "trim", dn.get("mat", "siding"), tag="dentil block")
                        u += oc
        cw = float(w.get("corner_in", 3.5)) * IN
        for end in w.get("corners", []):        # corner boards
            ua = 0.0 if end == "a" else L - cw
            ztop = max(self._top_at(w.get("top"), ua, z1), self._top_at(w.get("top"), ua + cw, z1)) if w.get("top") else z1
            self.slab(w, ua, ua + cw, z0, min(z1, ztop), 0.0, 0.07, "trim", w.get("corner_mat", "haccent"), tag="corner board")
        if w.get("foundation"):
            fz = float(w.get("foundation_z", z0))
            self.slab(w, 0.0, L, fz - float(w.get("foundation_h", 0.8)), fz, -th, 0.01, "house", "foundation", tag="foundation")

    def vertical_boards(self, w, ops, z0, z1, L):
        """Vertical-groove siding as real geometry: a board face between every pair of grooves, standing `relief_in` proud of
        the groove bottoms (the slab face), split around the openings (their casings) and at painted-field edges."""
        s = float(w.get("groove_in", 8.0)) * IN
        gw = float(w.get("groove_w_in", 0.375)) * IN
        rel = float(w.get("relief_in", 0.3)) * IN
        d0, d1 = -0.02, -0.02 + rel
        off = float(w.get("groove_off", s)) % s
        panels = w.get("panels", [])
        gs = []
        g = off
        while g < L - 1e-6:
            if g > 1e-6:
                gs.append(g)
            g += s
        edges = [0.0] + [x for g in gs for x in (g - gw / 2, g + gw / 2)] + [L]
        strips = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]
        for sa, sb in strips:
            if sb - sa < 0.01:
                continue
            # split the strip at opening and panel u-edges that fall inside it
            cuts = {sa, sb}
            for o in ops:
                m = self.margin(o)
                for c in (o["u0"] - m, o["u1"] + m):
                    if sa < c < sb:
                        cuts.add(c)
            for p in panels:
                for c in (p["u0"], p["u1"]):
                    if sa < c < sb:
                        cuts.add(c)
            cuts = sorted(cuts)
            for pa, pb in zip(cuts, cuts[1:]):
                if pb - pa < 0.004:
                    continue
                pm = (pa + pb) / 2
                blocked = sorted([(o["z0"] - self.margin(o), o["z1"] + self.margin(o)) for o in ops
                                  if o["u0"] - self.margin(o) < pm < o["u1"] + self.margin(o)])
                ivs, zc = [], z0
                for ba, bb in blocked:
                    if ba > zc:
                        ivs.append((zc, min(ba, z1)))
                    zc = max(zc, bb)
                if zc < z1:
                    ivs.append((zc, z1))
                for za, zb in ivs:
                    # split at the painted fields' z-edges (fields cover this strip when its middle is inside their u-range)
                    zcuts = {za, zb}
                    for p in panels:
                        if p["u0"] < pm < p["u1"]:
                            for c in (p["z0"], p["z1"]):
                                if za < c < zb:
                                    zcuts.add(c)
                    zcuts = sorted(zcuts)
                    for qa, qb in zip(zcuts, zcuts[1:]):
                        if qb - qa < 0.004:
                            continue
                        zm = (qa + qb) / 2
                        mat = w.get("mat", "siding")
                        for p in panels:
                            if p["u0"] < pm < p["u1"] and p["z0"] < zm < p["z1"]:
                                mat = p.get("mat", "siding2")
                        self.slab(w, pa, pb, qa, qb, d0, d1, "siding", mat, tag="vertical siding board")
                # the gable / rake part above z1
                if w.get("top") and not any(o["u0"] - self.margin(o) < pm < o["u1"] + self.margin(o) and o["z1"] >= z1 for o in ops):
                    mat = w.get("mat", "siding")
                    for p in panels:
                        if p["u0"] < pm < p["u1"] and p["z1"] > z1:
                            mat = p.get("mat", "siding2")
                    self._upper(w, pa, pb, z1, d0, d1, "siding", mat, "vertical siding board (gable)")

    # --------------------------------------------------------------- openings
    def window(self, w, o):
        u0, u1, z0, z1 = o["u0"], o["u1"], o["z0"], o["z1"]
        tw = float(o.get("casing_in", o.get("trim_in", 3.5))) * IN
        cm, fm = o.get("casing_mat", "htrim"), o.get("frame_mat", "htrim")
        dset = float(o.get("set_back", 0.0))           # the frame set back into a brick opening
        # trim (casing) proud of the siding, sill nose
        if o.get("casing", True):
            self.slab(w, u0 - tw, u1 + tw, z1, z1 + tw, 0.0, 0.08, "trim", cm, tag="window head trim")
            if o.get("sill", "trim") == "trim":
                self.slab(w, u0 - tw, u1 + tw, z0 - tw, z0, 0.0, 0.1, "trim", cm, tag="window sill")
            self.slab(w, u0 - tw, u0, z0, z1, 0.0, 0.08, "trim", cm, tag="window side trim")
            self.slab(w, u1, u1 + tw, z0, z1, 0.0, 0.08, "trim", cm, tag="window side trim")
        self.brick_details(w, o)
        # the vinyl frame and the lites (fractions of the width), glass set back, mullions
        fr = float(o.get("frame_in", 1.44)) * IN if o.get("frame_in") else 0.12
        self.slab(w, u0, u1, z1 - fr, z1, -0.2 - dset, 0.0 - dset, "trim", fm, tag="window frame")
        self.slab(w, u0, u1, z0, z0 + fr, -0.2 - dset, 0.0 - dset, "trim", fm, tag="window frame")
        self.slab(w, u0, u0 + fr, z0, z1, -0.2 - dset, 0.0 - dset, "trim", fm, tag="window frame")
        self.slab(w, u1 - fr, u1, z0, z1, -0.2 - dset, 0.0 - dset, "trim", fm, tag="window frame")
        lites = o.get("lites") or [1.0]
        acc, xs = 0.0, []
        for f in lites[:-1]:
            acc += f
            xs.append(u0 + (u1 - u0) * acc)
        mw = float(o.get("mullion_in", 1.92)) * IN if o.get("mullion_in") else 0.08
        for xm in xs:
            self.slab(w, xm - mw, xm + mw, z0, z1, -0.2 - dset, -0.01 - dset, "trim", fm, tag="window mullion")
        if o.get("meeting_rail"):          # single / double hung
            zm = z0 + (z1 - z0) * float(o["meeting_rail"])
            self.slab(w, u0, u1, zm - 0.06, zm + 0.06, -0.2 - dset, -0.01 - dset, "trim", fm, tag="meeting rail")
        if o.get("sash_in"):               # sliding / hung sashes: a frame around every lite (the sash stiles and rails)
            sw = float(o["sash_in"]) * IN
            edges = [u0 + fr] + xs + [u1 - fr]
            for a_, b_ in zip(edges, edges[1:]):
                a2 = a_ + (mw if a_ in xs else 0.0); b2 = b_ - (mw if b_ in xs else 0.0)
                self.slab(w, a2, b2, z1 - fr - sw, z1 - fr, -0.17 - dset, -0.05 - dset, "trim", fm, tag="sash rail")
                self.slab(w, a2, b2, z0 + fr, z0 + fr + sw, -0.17 - dset, -0.05 - dset, "trim", fm, tag="sash rail")
                self.slab(w, a2, a2 + sw, z0 + fr, z1 - fr, -0.17 - dset, -0.05 - dset, "trim", fm, tag="sash stile")
                self.slab(w, b2 - sw, b2, z0 + fr, z1 - fr, -0.17 - dset, -0.05 - dset, "trim", fm, tag="sash stile")
        self.slab(w, u0 + fr, u1 - fr, z0 + fr, z1 - fr, -0.16 - dset, -0.14 - dset, "glass", "hglass", tag="glass")
        if o.get("blinds"):
            self.blinds(w, u0 + fr, u1 - fr, z0 + fr, z1 - fr, o, dset)
        elif o.get("shutters", True):
            self.shutters(w, u0 + fr, u1 - fr, z0 + fr, z1 - fr, o)
        if o.get("interior", True):
            self.slab(w, u0, u1, z0, z1, -1.6, -1.5, "house", "interior", tag="room")
        if o.get("half_round"):            # an arched transom / gable window: a fan of thin wedges
            pass

    def brick_details(self, w, o):
        """Brick around an opening: a rowlock sill (bricks on edge, pitched, projecting 1-1/4") and an optional soldier course."""
        u0, u1, z0, z1 = o["u0"], o["u1"], o["z0"], o["z1"]
        if o.get("sill") == "rowlock":
            ext = float(o.get("sill_ext_in", 2.0)) * IN
            h = float(o.get("sill_h_in", 4.5)) * IN
            self.slab(w, u0 - ext, u1 + ext, z0 - h, z0, -0.25, float(o.get("sill_proj_in", 1.25)) * IN, "trim",
                      o.get("sill_mat", "hbrick"), tag="brick rowlock sill")
        if o.get("head") == "soldier":
            self.slab(w, u0 - 0.04, u1 + 0.04, z1, z1 + 7.625 * IN, -0.02, 0.012, "trim", o.get("head_mat", "hbrick"), tag="brick soldier course")

    def blinds(self, w, u0, u1, z0, z1, o, dset=0.0):
        """Horizontal blinds just behind the glass: 1" slats tilted half open, a head rail; lowered to o["blinds"] (fraction)."""
        frac = float(o["blinds"]) if isinstance(o["blinds"], (int, float)) and not isinstance(o["blinds"], bool) else 1.0
        d0, d1 = -0.3 - dset, -0.24 - dset
        self.slab(w, u0, u1, z1 - 0.12, z1, d0, d1 + 0.02, "shutter", "hblind", tag="blind head rail")
        zb = z1 - (z1 - z0) * frac
        zc = z1 - 0.12 - 0.07
        while zc > zb + 0.02:
            self.slab(w, u0 + 0.02, u1 - 0.02, zc - 0.022, zc, d0, d1, "shutter", "hblind", tag="blind slat")
            zc -= 0.085

    def slider(self, w, o):
        """A sliding patio door (u0..u1 frame outside, z0 = sill bottom, z1 = head top): a vinyl / aluminium frame, n panels
        ("ops": X = sliding on the inner track, O = fixed on the outer track), stiles and rails, glass, a pull on the sliding
        panel, an insect screen on the outermost track over the sliding panel, the casing around it, the room behind."""
        u0, u1, z0, z1 = o["u0"], o["u1"], o["z0"], o["z1"]
        tw = float(o.get("casing_in", o.get("trim_in", 3.5))) * IN
        cm, fm = o.get("casing_mat", "htrim"), o.get("frame_mat", "htrim")
        ds = float(o.get("set_back", 0.0))
        if o.get("casing", True):
            self.slab(w, u0 - tw, u1 + tw, z1, z1 + tw, 0.0, 0.08, "trim", cm, tag="slider head casing")
            self.slab(w, u0 - tw, u0, z0, z1, 0.0, 0.08, "trim", cm, tag="slider casing")
            self.slab(w, u1, u1 + tw, z0, z1, 0.0, 0.08, "trim", cm, tag="slider casing")
        self.brick_details(w, o)
        fr = float(o.get("frame_in", 1.75)) * IN
        D0, D1 = -0.42 - ds, 0.0 - ds
        self.slab(w, u0, u1, z1 - fr, z1, D0, D1, "trim", fm, tag="slider frame head")
        self.slab(w, u0, u0 + fr, z0, z1, D0, D1, "trim", fm, tag="slider frame jamb")
        self.slab(w, u1 - fr, u1, z0, z1, D0, D1, "trim", fm, tag="slider frame jamb")
        self.slab(w, u0, u1, z0, z0 + 0.11, D0, D1 + 0.04, "trim", fm, tag="slider sill + track")
        ops = (o.get("ops") or "XO").upper()
        n = len(ops)
        ia, ib = u0 + fr, u1 - fr
        ov = float(o.get("overlap_in", 1.5)) * IN
        pw = (ib - ia + ov * (n - 1)) / n
        st, rt, rb = 2.0 * IN, 2.25 * IN, 3.5 * IN
        zb, zt = z0 + 0.11, z1 - fr
        for i, op in enumerate(ops):
            pa = ia + i * (pw - ov)
            pb = pa + pw
            dt = (-0.3, -0.2) if op == "X" else (-0.17, -0.07)
            dt = (dt[0] - ds, dt[1] - ds)
            msl = st + (0.5 * IN if (i > 0) else 0.0)          # meeting stiles a little heavier
            msr = st + (0.5 * IN if (i < n - 1) else 0.0)
            self.slab(w, pa, pa + msl, zb, zt, dt[0], dt[1], "trim", fm, tag="slider panel stile")
            self.slab(w, pb - msr, pb, zb, zt, dt[0], dt[1], "trim", fm, tag="slider panel stile")
            self.slab(w, pa, pb, zt - rt, zt, dt[0], dt[1], "trim", fm, tag="slider panel rail")
            self.slab(w, pa, pb, zb, zb + rb, dt[0], dt[1], "trim", fm, tag="slider panel rail")
            gm = (dt[0] + dt[1]) / 2
            self.slab(w, pa + msl, pb - msr, zb + rb, zt - rt, gm - 0.01, gm + 0.01, "glass", "hglass", tag="slider glass")
            if op == "X":
                # the pull + lock sit on the stile that closes against the jamb (the outer end of an end panel)
                hu = (pb - msr / 2) if (i == n - 1 and n > 1) else (pa + msl / 2)
                zh = z0 + 3.1
                self.slab(w, hu - 0.035, hu + 0.035, zh - 0.25, zh + 0.25, dt[1], dt[1] + 0.06, "trim", o.get("handle_mat", "storm"), tag="slider pull")
                if o.get("screen", True):
                    sa, sb = pa - 0.02, pb + 0.02
                    s0, s1 = -0.06 - ds, -0.035 - ds
                    self.slab(w, sa, sb, zb, zb + 0.09, s0, s1, "trim", fm, tag="screen frame")
                    self.slab(w, sa, sb, zt - 0.09, zt, s0, s1, "trim", fm, tag="screen frame")
                    self.slab(w, sa, sa + 0.09, zb, zt, s0, s1, "trim", fm, tag="screen frame")
                    self.slab(w, sb - 0.09, sb, zb, zt, s0, s1, "trim", fm, tag="screen frame")
                    self.slab(w, sa + 0.09, sb - 0.09, zb + 0.09, zt - 0.09, s0 + 0.008, s1 - 0.008, "glass", "hscreen", tag="screen mesh")
        if o.get("blinds"):
            self.blinds(w, ia, ib, zb, zt, dict(o, blinds=o["blinds"]), ds + 0.2)
        if o.get("interior", True):
            self.slab(w, u0, u1, z0, z1, -1.6, -1.5, "house", "interior", tag="room")


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

    # --------------------------------------------------------------- general roofs: shed (any low side), hip, free planes
    @staticmethod
    def _out(s):
        return {"+y": (0.0, 1.0), "-y": (0.0, -1.0), "+x": (1.0, 0.0), "-x": (-1.0, 0.0)}[s] if isinstance(s, str) else tuple(s)

    def poly(self, pts, kind, mat, tag, lift=0.0):
        """A planar polygon (3D points, CCW seen from its front) as a triangle fan mesh."""
        p0 = pts[0]
        tri = []
        for i in range(1, len(pts) - 1):
            tri += [p0, pts[i], pts[i + 1]]
        self.mesh(kind, [[float(x), float(y), float(z) + lift] for x, y, z in tri], mat, tag=tag)

    def eave(self, a, b, z, out, fh=0.6, th=0.2, soffit=None, gutter=True, fascia_mat="hfascia", soffit_mat="hsoffit",
             gutter_mat="hfascia", tag="eave"):
        """An eave along the axis-aligned line a->b (the fascia's outer face), roof top at z + th: the fascia board, the
        5" K gutter hung on it, and a level box soffit `soffit` ft deep back toward the wall."""
        ox, oy = self._out(out)
        (xa, ya), (xb, yb) = a, b
        x0, x1 = sorted((xa, xb)); y0, y1 = sorted((ya, yb))
        def band(d0, d1, za, zb, kind, mat, tg):
            if abs(oy) > 0.5:        # eave along x
                ys = sorted((ya + oy * d0, ya + oy * d1))
                self.add(kind, x0, x1, ys[0], ys[1], za, zb, mat, 0, tag=tg)
            else:
                xs = sorted((xa + ox * d0, xa + ox * d1))
                self.add(kind, xs[0], xs[1], y0, y1, za, zb, mat, 0, tag=tg)
        band(-0.07, 0.0, z - fh, z + th, "trim", fascia_mat, f"{tag}: fascia")
        if gutter:
            gt = z + th - 0.04                      # the gutter's top lip just under the roof edge
            band(0.0, 0.40, gt - 0.40, gt - 0.34, "gutter", gutter_mat, f"{tag}: K gutter bottom")
            band(0.33, 0.40, gt - 0.40, gt, "gutter", gutter_mat, f"{tag}: K gutter face")
            band(0.36, 0.43, gt - 0.07, gt + 0.01, "gutter", gutter_mat, f"{tag}: K gutter lip")
            band(0.0, 0.03, gt - 0.40, gt, "gutter", gutter_mat, f"{tag}: K gutter back")
        if soffit:
            band(-float(soffit), -0.07, z - fh, z - fh + 0.05, "roof", soffit_mat, f"{tag}: soffit")

    def shed_any(self, r: dict):
        """A shed roof whose low edge is on any side ("-y", "+x", "-x"): planes, fascia + gutter on the low edge, rakes."""
        x0, x1, y0, y1 = r["rect"]
        zl, zh = float(r["z_low"]), float(r["z_high"])
        th = float(r.get("th", 0.2))
        low = r["low"]
        c = {"+x": ((x1, y0, zl), (x1, y1, zl), (x0, y1, zh), (x0, y0, zh)),
             "-x": ((x0, y1, zl), (x0, y0, zl), (x1, y0, zh), (x1, y1, zh)),
             "-y": ((x0, y0, zl), (x1, y0, zl), (x1, y1, zh), (x0, y1, zh))}[low]
        # CCW from above: order the four corners counter-clockwise in plan
        pts = list(c)
        cx_, cy_ = sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4
        pts.sort(key=lambda p: math.atan2(p[1] - cy_, p[0] - cx_))
        self.poly(pts, "roof", r.get("mat", "shingle"), r.get("name", "shed roof"), lift=th)
        a_, b_ = c[0][:2], c[1][:2]
        self.eave(a_, b_, zl, low, fh=float(r.get("fascia_h", 0.6)), th=th, soffit=r.get("soffit"), gutter=r.get("gutter", True), tag=r.get("name", "shed roof"))
        for p, q in ((c[1], c[2]), (c[3], c[0])):
            self.rake(p[0], p[1], p[2], q[0], q[1], q[2], th)

    def hip_roof(self, r: dict):
        """A hip roof over the eave outline rect (fascia line): ridge along "axis" ("x" or "y"), pitch rise/12 (or z_ridge),
        hipped ends listed in "hips" (default both; a missing end is a gable with rake boards), fascia + gutter + box soffit
        on every eave, a ridge cap."""
        x0, x1, y0, y1 = [float(v) for v in r["rect"]]
        ze = float(r["z_eave"]); th = float(r.get("th", 0.2)); fh = float(r.get("fascia_h", 0.6))
        axis = r.get("axis", "x")
        mat = r.get("mat", "shingle")
        hips = r.get("hips", ["x0", "x1"] if axis == "x" else ["y0", "y1"])
        if axis == "x":
            half = (y1 - y0) / 2; ym = (y0 + y1) / 2
            zr = float(r["z_ridge"]) if "z_ridge" in r else ze + float(r["pitch"]) / 12.0 * half
            run = (zr - ze) / (float(r["pitch"]) / 12.0) if "pitch" in r else half
            xa = x0 + (run if "x0" in hips else 0.0); xb = x1 - (run if "x1" in hips else 0.0)
            if xa > xb:
                xa = xb = (x0 + x1) / 2
            self.poly([(x0, y1, ze), (x1, y1, ze), (xb, ym, zr), (xa, ym, zr)][::-1], "roof", mat, "roof plane (front)", lift=th)
            self.poly([(x1, y0, ze), (x0, y0, ze), (xa, ym, zr), (xb, ym, zr)][::-1], "roof", mat, "roof plane (back)", lift=th)
            if "x0" in hips:
                self.poly([(x0, y0, ze), (x0, y1, ze), (xa, ym, zr)][::-1], "roof", mat, "roof plane (hip end)", lift=th)
            if "x1" in hips:
                self.poly([(x1, y1, ze), (x1, y0, ze), (xb, ym, zr)][::-1], "roof", mat, "roof plane (hip end)", lift=th)
            eaves = [((x0, y1), (x1, y1), "+y"), ((x0, y0), (x1, y0), "-y")]
            eaves += [((x0, y0), (x0, y1), "-x")] if "x0" in hips else []
            eaves += [((x1, y0), (x1, y1), "+x")] if "x1" in hips else []
            rakes = ([] if "x0" in hips else [((x0, y0, ze), (x0, ym, zr)), ((x0, ym, zr), (x0, y1, ze))]) + \
                    ([] if "x1" in hips else [((x1, y0, ze), (x1, ym, zr)), ((x1, ym, zr), (x1, y1, ze))])
            ridge = ((xa, ym), (xb, ym))
        else:
            half = (x1 - x0) / 2; xm = (x0 + x1) / 2
            zr = float(r["z_ridge"]) if "z_ridge" in r else ze + float(r["pitch"]) / 12.0 * half
            run = (zr - ze) / (float(r["pitch"]) / 12.0) if "pitch" in r else half
            ya = y0 + (run if "y0" in hips else 0.0); yb = y1 - (run if "y1" in hips else 0.0)
            if ya > yb:
                ya = yb = (y0 + y1) / 2
            self.poly([(x1, y0, ze), (x1, y1, ze), (xm, yb, zr), (xm, ya, zr)][::-1], "roof", mat, "roof plane (side)", lift=th)
            self.poly([(x0, y1, ze), (x0, y0, ze), (xm, ya, zr), (xm, yb, zr)][::-1], "roof", mat, "roof plane (side)", lift=th)
            if "y0" in hips:
                self.poly([(x0, y0, ze), (x1, y0, ze), (xm, ya, zr)], "roof", mat, "roof plane (hip end)", lift=th)
            if "y1" in hips:
                self.poly([(x1, y1, ze), (x0, y1, ze), (xm, yb, zr)], "roof", mat, "roof plane (hip end)", lift=th)
            eaves = [((x0, y0), (x0, y1), "-x"), ((x1, y0), (x1, y1), "+x")]
            eaves += [((x0, y0), (x1, y0), "-y")] if "y0" in hips else []
            eaves += [((x0, y1), (x1, y1), "+y")] if "y1" in hips else []
            rakes = ([] if "y0" in hips else [((x0, y0, ze), (xm, y0, zr)), ((xm, y0, zr), (x1, y0, ze))]) + \
                    ([] if "y1" in hips else [((x0, y1, ze), (xm, y1, zr)), ((xm, y1, zr), (x1, y1, ze))])
            ridge = ((xm, ya), (xm, yb))
        skip = set(r.get("no_eave", []))           # eaves hidden against another roof / a wall
        for a_, b_, o_ in eaves:
            if o_ in skip:
                continue
            self.eave(a_, b_, ze, o_, fh=fh, th=th, soffit=r.get("soffit", 1.0), gutter=o_ not in set(r.get("no_gutter", [])),
                      tag=r.get("name", "hip roof"))
        for p, q in rakes:
            self.rake(p[0], p[1], p[2], q[0], q[1], q[2], th)
        (ra, rb) = ridge
        if abs(ra[0] - rb[0]) + abs(ra[1] - rb[1]) > 0.05:
            w_ = 0.42
            if axis == "x":
                self.add("roof", min(ra[0], rb[0]), max(ra[0], rb[0]), ra[1] - w_ / 2, ra[1] + w_ / 2, zr + th - 0.05, zr + th + 0.08, mat, 0, tag="ridge cap")
            else:
                self.add("roof", ra[0] - w_ / 2, ra[0] + w_ / 2, min(ra[1], rb[1]), max(ra[1], rb[1]), zr + th - 0.05, zr + th + 0.08, mat, 0, tag="ridge cap")

    def planes_roof(self, r: dict):
        """A free-form roof: "faces" (3D polygons, CCW from above), "eaves" [{a, b, z, out, soffit, gutter}],
        "rakes" [[p, q]], "ridges" [[p, q]] (caps)."""
        th = float(r.get("th", 0.2)); mat = r.get("mat", "shingle")
        for f in r.get("faces", []):
            pts = f["pts"] if isinstance(f, dict) else f
            self.poly(pts, "roof", (f.get("mat", mat) if isinstance(f, dict) else mat), r.get("name", "roof plane"), lift=th)
        for e in r.get("eaves", []):
            self.eave(e["a"], e["b"], float(e["z"]), e["out"], fh=float(e.get("fascia_h", r.get("fascia_h", 0.6))), th=th,
                      soffit=e.get("soffit", r.get("soffit")), gutter=e.get("gutter", True), tag=r.get("name", "roof"))
        for p, q in r.get("rakes", []):
            self.rake(p[0], p[1], p[2], q[0], q[1], q[2], th)
        for p, q in r.get("ridges", []):
            L_ = math.hypot(q[0] - p[0], q[1] - p[1])
            if L_ < 0.05:
                continue
            ux_, uy_ = (q[0] - p[0]) / L_, (q[1] - p[1]) / L_
            nx_, ny_ = -uy_ * 0.21, ux_ * 0.21
            zt = max(p[2], q[2]) + th
            quad = [[p[0] + nx_, p[1] + ny_, p[2] + th - 0.02], [q[0] + nx_, q[1] + ny_, q[2] + th - 0.02], [q[0], q[1], q[2] + th + 0.08],
                    [p[0] + nx_, p[1] + ny_, p[2] + th - 0.02], [q[0], q[1], q[2] + th + 0.08], [p[0], p[1], p[2] + th + 0.08],
                    [p[0], p[1], p[2] + th + 0.08], [q[0], q[1], q[2] + th + 0.08], [q[0] - nx_, q[1] - ny_, q[2] + th - 0.02],
                    [p[0], p[1], p[2] + th + 0.08], [q[0] - nx_, q[1] - ny_, q[2] + th - 0.02], [p[0] - nx_, p[1] - ny_, p[2] + th - 0.02]]
            self.mesh("roof", quad, mat, tag="ridge / hip cap")

    def chimney(self, c: dict):
        """A masonry chimney: the stack (brick) from z0 to z1, a cast crown overhanging it, a flue pipe with a rain cap."""
        x0, x1, y0, y1 = [float(v) for v in c["rect"]]
        z0, z1 = float(c.get("z0", 0.0)), float(c["z1"])
        self.add("house", x0, x1, y0, y1, z0, z1, c.get("mat", "hbrick"), 0, tag=c.get("name", "chimney"))
        ov = float(c.get("cap_over_in", 2.0)) * IN
        ch = float(c.get("cap_h_in", 4.0)) * IN
        if c.get("cap", True):
            self.add("trim", x0 - ov, x1 + ov, y0 - ov, y1 + ov, z1, z1 + ch, c.get("cap_mat", "hcap"), 0, tag="chimney crown")
        fl = c.get("flue")
        if fl:
            fx, fy = fl.get("at", [(x0 + x1) / 2, (y0 + y1) / 2])
            r_ = float(fl.get("d_in", 8.0)) * IN / 2
            fhh = float(fl.get("h_in", 14.0)) * IN
            self.add("trim", fx - r_, fx + r_, fy - r_, fy + r_, z1 + ch, z1 + ch + fhh, "hmetal", 0, tag="flue pipe", shape="cyl")
            self.add("trim", fx - r_ * 1.7, fx + r_ * 1.7, fy - r_ * 1.7, fy + r_ * 1.7, z1 + ch + fhh, z1 + ch + fhh + 0.06, "hmetal", 0, tag="flue rain cap")
            self.add("trim", fx - r_ * 1.25, fx + r_ * 1.25, fy - r_ * 1.25, fy + r_ * 1.25, z1 + ch + fhh + 0.06, z1 + ch + fhh + 0.3, "hmetal", 0, tag="flue rain cap", shape="cyl")

    def wbox(self, x, y, out, a0, a1, o0, o1, z0, z1, kind, mat, tag):
        """A box beside a wall point (x, y): along-wall a0..a1, outward o0..o1 (the wall's outside is `out`)."""
        ox, oy = self._out(out)
        if abs(oy) > 0.5:
            ys = sorted((y + oy * o0, y + oy * o1))
            self.add(kind, x + a0, x + a1, ys[0], ys[1], z0, z1, mat, 0, tag=tag)
        else:
            xs = sorted((x + ox * o0, x + ox * o1))
            self.add(kind, xs[0], xs[1], y + a0, y + a1, z0, z1, mat, 0, tag=tag)

    def downspout(self, d: dict):
        if d.get("out", "+y") != "+y" or d.get("mat"):
            return self.downspout_v2(d)
        x, y = d["at"]
        z1 = float(d["z1"])
        z0 = float(d.get("z0", 0.0))
        s = 0.17
        self.add("gutter", x - s, x + s, y, y + 0.22, z0 + 0.6, z1, "htrim" if d.get("color") == "trim" else "siding", 0, tag="downspout")
        self.add("gutter", x - s, x + s, y, y + 1.2, z0, z0 + 0.3, "htrim" if d.get("color") == "trim" else "siding", 0, tag="downspout elbow + splash")

    def downspout_v2(self, d: dict):
        """A 2x3 downspout standing off a wall facing `out`, an elbow + splash block (or a kick-out) at the bottom."""
        x, y = d["at"]
        z1, z0 = float(d["z1"]), float(d.get("z0", 0.0))
        out = d.get("out", "+y"); mat = d.get("mat", "hfascia")
        self.wbox(x, y, out, -0.125, 0.125, 0.02, 0.2, z0 + 0.45, z1, "gutter", mat, "downspout")
        self.wbox(x, y, out, -0.125, 0.125, 0.02, 0.75, z0 + 0.1, z0 + 0.45, "gutter", mat, "downspout elbow")
        if d.get("strap", True):
            for zz in (z0 + 0.3 * (z1 - z0), z0 + 0.7 * (z1 - z0)):
                self.wbox(x, y, out, -0.15, 0.15, 0.0, 0.22, zz, zz + 0.06, "gutter", mat, "downspout strap")

    def lantern(self, d: dict):
        if d.get("out", "+y") != "+y" or d.get("style"):
            return self.lantern_v2(d)
        x, y, z = d["at"]
        self.add("storm", x - 0.22, x + 0.22, y + 0.02, y + 0.42, z - 0.55, z + 0.3, "storm", 0, tag="coach lantern")
        self.add("glass", x - 0.16, x + 0.16, y + 0.06, y + 0.38, z - 0.4, z + 0.15, "hglass", 0, tag="lantern glass")
        self.add("storm", x - 0.1, x + 0.1, y, y + 0.08, z - 0.7, z + 0.4, "storm", 0, tag="lantern back plate")

    def lantern_v2(self, d: dict):
        """A black coach lantern on a wall facing `out`: back plate, arm, a tapered cage with seeded-glass panes, a cap."""
        x, y, z = d["at"]
        out = d.get("out", "+y")
        self.wbox(x, y, out, -0.11, 0.11, 0.0, 0.06, z - 0.62, z + 0.18, "storm", "storm", "lantern back plate")
        self.wbox(x, y, out, -0.035, 0.035, 0.06, 0.32, z - 0.30, z - 0.22, "storm", "storm", "lantern arm")
        self.wbox(x, y, out, -0.2, 0.2, 0.16, 0.56, z - 0.42, z - 0.36, "storm", "storm", "lantern base")
        self.wbox(x, y, out, -0.16, 0.16, 0.2, 0.52, z - 0.36, z + 0.2, "glass", "hglass", "lantern glass")
        for a0, a1, o0, o1 in ((-0.18, -0.15, 0.18, 0.54), (0.15, 0.18, 0.18, 0.54), (-0.18, 0.18, 0.18, 0.21), (-0.18, 0.18, 0.51, 0.54)):
            self.wbox(x, y, out, a0, a1, o0, o1, z - 0.36, z + 0.2, "storm", "storm", "lantern cage")
        self.wbox(x, y, out, -0.22, 0.22, 0.14, 0.58, z + 0.2, z + 0.3, "storm", "storm", "lantern cap")
        self.wbox(x, y, out, -0.12, 0.12, 0.25, 0.47, z + 0.3, z + 0.42, "storm", "storm", "lantern cap")
        self.wbox(x, y, out, -0.08, 0.08, 0.28, 0.44, z - 0.30, z + 0.05, "glass", "hglass", "lantern chimney glass")

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
            elif t == "slider":
                b.slider(w, o)
            elif t == "arch":
                b.arch_window(w, o)
            elif t == "void":
                continue                # an open bay / a passage: the wall is cut, nothing drawn in it
            else:
                b.window(w, o)
    for g in model.get("gables", []):           # a gable end above an eave line: {a, b, z, peak_u, peak_z}
        b.gable_end({"a": g["a"], "b": g["b"], "z1": g["z"]}, float(g["peak_u"]), float(g["peak_z"]))
    for s in model.get("soffits", []):          # undersides of cantilevered floors / bays
        if isinstance(s, dict):
            x0, x1, y0, y1 = s["rect"]; z = float(s["z"])
            add("trim", x0, x1, y0, y1, z - float(s.get("t", 0.08)), z, s.get("mat", "hsoffit"), 0, tag=s.get("name", "soffit"))
            continue
        x0, x1, y0, y1, z = s
        add("trim", x0, x1, y0, y1, z - 0.08, z, "hsoffit", 0, tag="soffit")
    for m in model.get("masses", []):           # solid bodies behind the walls (blocks the light)
        x0, x1, y0, y1, z0, z1 = m
        add("house", x0, x1, y0, y1, z0, z1, "interior", 0, tag="house body")
    for r in model.get("roofs", []):
        t = r.get("type")
        if t == "shed":
            if r.get("low", "+y") == "+y":
                b.shed_roof(r)
            else:
                b.shed_any(r)
        elif t == "hip":
            b.hip_roof(r)
        elif t == "planes":
            b.planes_roof(r)
        else:
            b.gable_roof(r)
    for c in model.get("chimneys", []):
        b.chimney(c)
    for g in model.get("gutters", []):          # free-standing eave runs: {a, b, z (roof top at the edge - th), out, ...}
        b.eave(g["a"], g["b"], float(g["z"]), g["out"], fh=float(g.get("fascia_h", 0.6)), th=float(g.get("th", 0.2)),
               soffit=g.get("soffit"), gutter=g.get("gutter", True), tag=g.get("name", "eave"))
    for bl in model.get("blocks", []):         # solid pieces in a material: brick piers, sills, trim boxes, flashing
        x0, x1, y0, y1, z0, z1 = bl["box"]
        add(bl.get("kind", "house"), x0, x1, y0, y1, z0, z1, bl.get("mat", "hbrick"), 0, tag=bl.get("name", "block"))
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
