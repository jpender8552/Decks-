"""Motorized aluminum louvered roofs over a deck — the Suncoast Louvered Roof (suncoastenclosures.com/louvered-roof).

A roof is one dict in geometry.louvered_roofs, in the plan frame (feet: x along the house left to right as you face it
from the yard, y from the house wall toward the yard) with heights in feet above grade (the scene's z). DEFAULTS lists
every key. The frame is level: perimeter beams with the integrated gutter, motor-zone dividers, 8" blades on 8" centres
turning about their own long axis, 6x6 posts base-plated on the deck, and on an attached roof a house-side beam on wall
brackets at the soffit / roof line (no posts at the house).

Where a post stands on the deck's rail line it IS the rail post there: the rail layout takes it as a fixed post
(rail_points -> layout.rail_layout_edges), the scene draws no rail post there and the takeoff drops that rail post kit
and adds the post-mount brackets the panels hang on (takeoff_hook).

Prices are sell prices (check / ACH), outside the deck's cost stack: `price` (fixed) or `price_per_sf` x the roof area.
`priced` "own" = its own document only (roof_pricing); "option" = also an option on the deck's quote (option_prices).

Frames: geometry.louvered_roofs on a composite job is in the global frame; composite._sub_spec hands each part a copy in
the part's frame (part_roofs, marked "_global") so the part's rail layout and takeoff see the posts, while the composite
scene draws the roof once, globally. A roof declared inside a part's own geometry is in that part's frame."""
from __future__ import annotations

import copy
import math
from typing import Dict, List, Optional, Tuple

from .units import ftin

IN = 1 / 12.0
LAYER = "louvered"              # every roof box carries this layer: the deck's drawing sheets leave it out, the 3D views draw it
PHASE = 8                       # built after the deck (the viewer's "your room" step); the exploded views lift it with phase 8
MAT, LED_MAT = "lvmetal", "lvled"
ANGLE_RANGE = (0.0, 140.0)      # Suncoast: the blades turn through 140 degrees (0 = closed flat)
MOTOR_SF = 150.0                # one motor (one zone) controls up to 150 SF
BLADE_SPAN_MAX_FT = 14.0        # a blade spans up to 14' (snow-load dependent)
FRAMES = [("2x8", 2.0, 8.0, 15.0), ("2x10", 2.0, 10.0, 18.0), ("4x8", 4.0, 8.0, 22.0)]   # Suncoast frame: max span between posts (ft)
SNAP_FT = 14.0 / 12             # a default post this close to the deck's rail corner post takes the corner (the roof slides over)
DIVIDER_CLEAR_IN = 24.0         # a breaker-line rail post closer than this to a roof post is dropped (the roof post is the post there)
BRACKET_OC_FT = 2.0             # house-side beam wall brackets
GUTTER_W, GUTTER_H = 2.5 * IN, 3.5 * IN
HEX = {"black": "#141416", "linen": "#e9e3d3", "grey": "#6b6e70", "gray": "#6b6e70", "tan": "#b9a68a", "white": "#ecebe6",
       "mocha": "#5a4636", "bronze": "#4b3b2c"}

DEFAULTS = dict(
    name="Louvered roof", brand="Suncoast", product="Louvered Roof", color="black",
    x0=None, x1=None, y0=None, y1=None,     # ft, plan frame: the outside faces of the perimeter beams
    attach="house",                         # "house" (house-side beam on wall brackets, no posts there) | "freestanding" (posts all round)
    z_attach=None,                          # ft above grade: top of the house-side beam = the soffit / roof line (None -> deck under the roof + 9')
    z_top=None,                             # ft above grade: top of the (level) frame (None -> z_attach; freestanding: deck + 9')
    louver_dir=None,                        # blade long axis "x" (along the house) | "y" (out from the house); None -> across the short side
    blade_in=8.0, spacing_in=8.0,           # blade width and centre-to-centre spacing
    blade_t_in=1.25, motor_t_in=2.0,        # blade / motor-blade thickness
    angle_deg=45.0,                         # how open to draw them: 0 closed (flat) .. 90 on edge .. 140 (Suncoast max), the +x / +y edge rising
    zones=None,                             # motor zones (one motor blade each); None -> ceil(area / 150 SF)
    posts=None,                             # [[x, y], ...] post centres (ft); None -> the outer corners (both ends of the front beam), on the
                                            #   deck's rail-post line when the roof's outer edge is at the deck edge (and all four corners freestanding)
    post_in=6.0, plate_in=7.0,              # 6x6 aluminum post, square base plate
    post_inset_in=None,                     # post centre in from the deck's frame face on a rail line (None -> the rail post inset, 2-1/2")
    snap=True,                              # a default post within 14" of the deck's rail corner post takes the corner (the roof slides to it)
    beam=None,                              # [w_in, h_in] perimeter frame; None -> by the longest post-to-post span (2x8 15', 2x10 18', 4x8 22')
    gutter=True, lights=True,               # integrated gutter; LED light strip in the gutter's light track
    downspouts="post",                      # "post" (hidden inside the posts, outlet at the base) | "external" (2x3 on the post face) | "none"
    price=None, price_per_sf=None,          # sell (check / ACH): fixed, or $/SF x the roof area
    priced="own",                           # "own" (its own document; the deck's price does not change) | "option" (also an option on the deck's quote)
    build=None,                             # built into the deck's model (3D, rail posts, takeoff)? None -> unless priced "option" (an option leaves the base deck as is)
    option_name=None,                       # the option's name on the deck's quote (None -> "<brand> louvered roof — W x D")
    screens=None,                           # retractable screens (an option): [{side "front" | "left" | "right", drop 0 (up in the cassette) .. 1
                                            #   (fully down), fabric "mesh" | "vinyl", color, bottom (z the bottom bar stops at), mount, price / price_per_lf}]
    screens_priced=None,                    # None -> as the roof ("own" | "option")
    note="",
)
SCREEN_DEFAULTS = dict(side="front", drop=0.0, fabric="mesh", color="black",
                       bottom=None,           # ft above grade where the bottom bar lands fully down (None -> the deck under the screen)
                       mount="inside",        # "inside": cassette under the frame inside the posts, fabric inside the rail, bar on the deck |
                                              # "outside": cassette face-mounted on the beam's outer face, fabric outside the rail
                       from_ft=None, to_ft=None,   # the screen's extent along its side (plan ft; None -> the frame's inside between beams)
                       housing_in=5.5,        # Suncoast 5.5" square housing: spans to 22', drops to 11' (7" round housing: 30' / 22')
                       price=None, price_per_lf=None, name=None)
SCREEN_EST_PER_LF = 275.0       # ESTIMATE until the owner sets it: sell $/LF of screen width, motorized, mesh, installed
SCREEN_MAT = "lvfabric"
HEM_H, HEM_T, TRACK_W, TRACK_D = 2.0 * IN, 1.25 * IN, 1.25 * IN, 2.0 * IN
FABRIC = {"mesh": dict(opacity=0.62, alpha=0.62, rough=0.9), "vinyl": dict(opacity=0.28, alpha=0.22, rough=0.12)}


# ================================================================== frames: a roof in the global frame <-> a part's frame
def _pl(part: dict) -> Tuple[float, float, float, float, float, float]:
    pl = (part or {}).get("placement", {}) or {}
    o = pl.get("origin", [0, 0])
    return float(o[0]), float(o[1]), float(pl.get("xx", 1)), float(pl.get("xy", 0)), float(pl.get("yx", 0)), float(pl.get("yy", 1))


def _map_roof(r: dict, f) -> dict:
    """The roof with every plan point put through f(x, y) -> (x', y')."""
    q = copy.deepcopy(r)
    if all(r.get(k) is not None for k in ("x0", "x1", "y0", "y1")):
        pts = [f(float(r[a]), float(r[b])) for a in ("x0", "x1") for b in ("y0", "y1")]
        q["x0"], q["x1"] = min(p[0] for p in pts), max(p[0] for p in pts)
        q["y0"], q["y1"] = min(p[1] for p in pts), max(p[1] for p in pts)
    if r.get("posts"):
        q["posts"] = [list(f(float(a), float(b))) for a, b in r["posts"]]
    ax = f(1.0, 0.0); o = f(0.0, 0.0)
    if r.get("louver_dir") in ("x", "y") and abs(ax[0] - o[0]) < 0.5:          # the frame turns 90 degrees: the blade axis swaps
        q["louver_dir"] = "y" if r["louver_dir"] == "x" else "x"
    return q


def part_roofs(roofs: Optional[List[dict]], part: dict) -> List[dict]:
    """composite._sub_spec: the job's roofs (global frame) in this part's frame, marked "_global" (the part's rail and
    takeoff use their posts; the part does not draw or price them — the composite scene draws them once), followed by
    the roofs the part declares in its own geometry (its own frame)."""
    ox, oy, xx, xy, yx, yy = _pl(part)
    det = xx * yy - xy * yx or 1.0

    def to_local(x, y):
        dx, dy = x - ox, y - oy
        return ((yy * dx - xy * dy) / det, (-yx * dx + xx * dy) / det)
    out = []
    for r in roofs or []:
        q = _map_roof(r, to_local)
        q["_global"] = True
        out.append(q)
    out += [copy.deepcopy(r) for r in ((part or {}).get("geometry") or {}).get("louvered_roofs") or [] if not r.get("_global")]
    return out


def roofs_of(spec) -> List[dict]:
    """Every roof on the job, in the job's frame (a composite's global frame): the job-level roofs, then the roofs its
    parts declare in their own geometry (moved into the global frame). Raw dicts (resolve() fills the defaults)."""
    g = spec.geometry
    out = [dict(r) for r in (getattr(g, "louvered_roofs", None) or []) if not r.get("_global")]
    for pd in g.parts or []:
        ox, oy, xx, xy, yx, yy = _pl(pd)
        for r in ((pd.get("geometry") or {}).get("louvered_roofs") or []):
            out.append(_map_roof(r, lambda x, y: (ox + xx * x + xy * y, oy + yx * x + yy * y)))
    return out


def built(r: dict) -> bool:
    """Is this roof built into the deck's model (3D, rail posts, takeoff)? `build`, else unless it is priced as an option."""
    b = r.get("build")
    return bool(b) if b is not None else str(r.get("priced") or "own").lower() != "option"


def has_roofs(spec) -> bool:
    """A built roof anywhere on the job (job level or in a part)."""
    return any(built(r) for r in (getattr(spec.geometry, "louvered_roofs", None) or [])) or \
        any(built(r) for pd in (spec.geometry.parts or []) for r in ((pd.get("geometry") or {}).get("louvered_roofs") or []))


# ================================================================== the deck under a roof
def zone_surfaces(zones, height_in: float) -> List[dict]:
    """Deck surfaces (ft) of a layout's zones (inches, the layout's frame) at the deck top."""
    zt = float(height_in) / 12.0
    return [dict(name=z.name, x0=z.x0 / 12.0, x1=(z.x0 + z.W) / 12.0, y0=z.wall_y / 12.0, y1=(z.wall_y + z.D) / 12.0, z=zt) for z in zones]


def surfaces_of(L) -> List[dict]:
    """Deck surfaces of a Layout (its own frame) or a CompositeLayout (the global frame: every part placed, at its height)."""
    if hasattr(L, "parts"):
        out = []
        for p in L.parts:
            zt = p.spec.geometry.height_in / 12.0
            for z in p.layout.zones:
                x0, x1, y0, y1 = p.placement.box(z.x0 / 12.0, (z.x0 + z.W) / 12.0, z.wall_y / 12.0, (z.wall_y + z.D) / 12.0)
                out.append(dict(name=f"{p.name} {z.name}", x0=x0, x1=x1, y0=y0, y1=y1, z=zt))
        return out
    return zone_surfaces(L.zones, L.spec.geometry.height_in)


def _surface_at(surfaces, x, y, tol=0.35):
    hits = [s for s in surfaces if s["x0"] - tol <= x <= s["x1"] + tol and s["y0"] - tol <= y <= s["y1"] + tol]
    return max(hits, key=lambda s: s["z"]) if hits else None


def _front_corners(surfaces, s) -> List[Tuple[float, int]]:
    """The outline corners on surface s's front edge: (x, inward sign) — a front end that no surface at the same height
    and the same front line continues."""
    out = []
    for xe, sgn in ((s["x0"], 1), (s["x1"], -1)):
        cont = any(t is not s and abs(t["z"] - s["z"]) < 0.05 and abs(t["y1"] - s["y1"]) < 0.05
                   and ((sgn > 0 and abs(t["x1"] - xe) < 0.05) or (sgn < 0 and abs(t["x0"] - xe) < 0.05)) for t in surfaces)
        if not cont:
            out.append((xe, sgn))
    return out


# ================================================================== the roof as built
def _num(v, d):
    return d if v is None else float(v)


def resolve(r: dict, surfaces: Optional[List[dict]] = None) -> dict:
    """Everything about one roof, in its frame (ft): the frame rectangle (after a snap), beams, motor zones, blades (pivot,
    length, zone), posts (centre, deck height, whether it is a rail post), heights and clearances, the house brackets."""
    from .layout import RAIL_POST_INSET
    surfaces = surfaces or []
    q = dict(DEFAULTS)
    q.update({k: v for k, v in (r or {}).items() if v is not None})
    x0, x1 = sorted((float(q["x0"]), float(q["x1"])))
    y0, y1 = sorted((float(q["y0"]), float(q["y1"])))
    W, D = x1 - x0, y1 - y0
    notes: List[str] = []
    p = float(q["post_in"]) * IN
    rp = _num(q.get("post_inset_in"), RAIL_POST_INSET) * IN
    house = str(q["attach"]).lower().startswith("house")
    under = [s for s in surfaces if min(x1, s["x1"]) - max(x0, s["x0"]) > 0.1 and min(y1, s["y1"]) - max(y0, s["y0"]) > 0.1]
    z_deck = max((s["z"] for s in under), default=0.0)

    # ---- posts: explicit, or the outer corners (on the rail line at a deck edge), snapped to the rail corner post
    shift = 0.0
    explicit = bool(q.get("posts"))

    def front_line(x):
        s = _surface_at(surfaces, x, y1, tol=0.6)
        if s is not None and abs(s["y1"] - y1) <= 1.0:
            return s, s["y1"] - rp
        return None, y1 - p / 2

    def default_posts(xa, xb):
        pts = []
        for x in (xa + p / 2, xb - p / 2):
            s, yf = front_line(x)
            pts.append((x, yf))
        if not house:
            pts = [(xa + p / 2, y0 + p / 2), (xb - p / 2, y0 + p / 2)] + pts
        return pts

    if explicit:
        posts = [(float(a), float(b)) for a, b in q["posts"]]
    else:
        posts = default_posts(x0, x1)
        if q.get("snap", True):
            best = None
            for (px, py) in posts:
                s, yf = front_line(px)
                if s is None or abs(py - yf) > 1e-6:
                    continue
                for xe, sgn in _front_corners(surfaces, s):
                    xc = xe + sgn * rp
                    d = xc - px
                    if 0.01 < abs(d) <= SNAP_FT and (best is None or abs(d) < abs(best)):
                        best = d
            if best is not None:
                shift = best
                x0, x1 = x0 + shift, x1 + shift
                posts = default_posts(x0, x1)
                notes.append(f"the roof slid {ftin(abs(shift) * 12)} {'left' if shift < 0 else 'right'} so its corner post is the rail corner post: "
                             f"frame x {x0:.3f}-{x1:.3f}")

    # ---- frame size: by the longest post-to-post span the beams carry
    front = sorted((pt for pt in posts if abs(pt[1] - max(pp[1] for pp in posts)) < 0.6), key=lambda t: t[0])
    span = max([b[0] - a[0] for a, b in zip(front, front[1:])] + [0.0])
    if not house:
        span = max(span, D - p)
    else:
        span = max(span, D - p / 2)          # the side beams: house beam to the front post
    if q.get("beam"):
        bw_in, bh_in = float(q["beam"][0]), float(q["beam"][1])
        lim = max([f[3] for f in FRAMES if f[1] <= bw_in and f[2] <= bh_in] or [FRAMES[0][3]])
        flabel = f"{bw_in:g}x{bh_in:g}"
    else:
        f_ = next((f for f in FRAMES if f[3] >= span - 1e-6), FRAMES[-1])
        flabel, bw_in, bh_in, lim = f_
    if not explicit and span > lim + 1e-6 and len(front) == 2:      # add posts under the front beam
        n_b = int(math.ceil(span / lim - 1e-9))
        (ax, ay), (bx, by) = front
        mids = [(ax + (bx - ax) * k / n_b, ay) for k in range(1, n_b)]
        posts = posts + mids
        notes.append(f"{len(mids)} post{'s' if len(mids) > 1 else ''} added under the front beam: {span:.1f}' exceeds the {flabel} frame's {lim:g}' span")
        front = sorted(front + mids, key=lambda t: t[0])
        span = max(b[0] - a[0] for a, b in zip(front, front[1:]))
    w, h = bw_in * IN, bh_in * IN

    # ---- heights
    z_attach = _num(q.get("z_attach"), z_deck + 9.0)
    z_top = _num(q.get("z_top"), z_attach if house else z_deck + 9.0)
    z_bot = z_top - h
    z_piv = z_top - h / 2

    # ---- motor zones and blades
    area = W * D
    ldir = q.get("louver_dir") or ("y" if D <= W else "x")
    n_motor = int(q["zones"]) if q.get("zones") else max(1, int(math.ceil(area / MOTOR_SF - 1e-9)))
    if ldir == "y":
        n_y = max(1, int(math.ceil((D - 2 * w) / BLADE_SPAN_MAX_FT - 1e-9)))
        n_x = max(1, int(math.ceil(n_motor / n_y)))
    else:
        n_x = max(1, int(math.ceil((W - 2 * w) / BLADE_SPAN_MAX_FT - 1e-9)))
        n_y = max(1, int(math.ceil(n_motor / n_x)))
    xs = [x0 + W * k / n_x for k in range(1, n_x)]          # divider beams along y at these x
    ys = [y0 + D * k / n_y for k in range(1, n_y)]          # cross beams along x at these y
    xb = [x0 + w] + [v for x_ in xs for v in (x_ - w / 2, x_ + w / 2)] + [x1 - w]
    yb = [y0 + w] + [v for y_ in ys for v in (y_ - w / 2, y_ + w / 2)] + [y1 - w]
    cells = [dict(x0=xb[2 * i], x1=xb[2 * i + 1], y0=yb[2 * j], y1=yb[2 * j + 1]) for j in range(n_y) for i in range(n_x)]
    bwid, sp = float(q["blade_in"]) * IN, float(q["spacing_in"]) * IN
    ang = max(ANGLE_RANGE[0], min(ANGLE_RANGE[1], float(q["angle_deg"])))
    blades = []
    for zi, c in enumerate(cells):
        a0, a1 = (c["x0"], c["x1"]) if ldir == "y" else (c["y0"], c["y1"])     # stacking axis
        l0, l1 = (c["y0"], c["y1"]) if ldir == "y" else (c["x0"], c["x1"])     # long axis
        n = max(1, int(math.floor((a1 - a0) / sp + 1e-6)))
        off = (a1 - a0 - n * sp) / 2
        c["n_blades"] = n
        c["motor"] = n // 2
        for i in range(n):
            s_ = a0 + off + sp / 2 + i * sp
            ctr = (s_, (l0 + l1) / 2) if ldir == "y" else ((l0 + l1) / 2, s_)
            blades.append(dict(zone=zi, i=i, motor=(i == n // 2), pivot=[ctr[0], ctr[1], z_piv], length=(l1 - l0) - 0.04))
    # ---- posts as built
    pts = []
    for (px, py) in posts:
        s = _surface_at(surfaces, px, py)
        zd = s["z"] if s else z_deck
        on_rail = bool(s) and abs(py - (s["y1"] - rp)) < 0.5 / 12 + 1e-6
        pts.append(dict(x=px, y=py, z_deck=zd, on_rail=on_rail, surface=s["name"] if s else ""))
    if not under:
        notes.append("no deck surface under the roof: the posts stand at z = 0")
    clear = z_bot - z_deck
    brackets = [x0 + 0.5 + k * BRACKET_OC_FT for k in range(int((W - 1.0) / BRACKET_OC_FT) + 1)] if house else []
    res = dict(src=r, name=q["name"], brand=q["brand"], product=q["product"], color=q["color"], hex=HEX.get(str(q["color"]).lower(), "#141416"),
                x0=x0, x1=x1, y0=y0, y1=y1, W=W, D=D, area=round(area, 2), shift=shift, attach="house" if house else "freestanding",
                beam=(bw_in, bh_in), beam_label=flabel, span_ft=round(span, 2), span_max_ft=lim, w=w, h=h,
                z_deck=z_deck, z_attach=z_attach, z_top=z_top, z_bot=z_bot, z_pivot=z_piv, clear_ft=clear,
                louver_dir=ldir, blade_w=bwid, blade_t=float(q["blade_t_in"]) * IN, motor_t=float(q["motor_t_in"]) * IN, spacing=sp,
                angle_deg=ang, zones=cells, n_zones=len(cells), xs=xs, ys=ys, blades=blades, posts=pts, post=p,
                plate=float(q["plate_in"]) * IN, gutter=bool(q["gutter"]), lights=bool(q["lights"]), downspouts=str(q.get("downspouts") or "none"),
                brackets=brackets, notes=notes, price=q.get("price"), price_per_sf=q.get("price_per_sf"), priced=str(q.get("priced") or "own"),
                option_name=q.get("option_name"), note=q.get("note", ""), global_=bool(r.get("_global")))
    res["screens"] = _screens(res, q.get("screens") or [], surfaces)
    res["screens_priced"] = str(q.get("screens_priced") or res["priced"])
    return res


def _screens(q: dict, screens: List[dict], surfaces: List[dict]) -> List[dict]:
    """Retractable screens as built: per side the cassette, the fabric plane and its extent, the top (cassette underside),
    the bottom stop and the drop. "inside": the cassette hangs under the frame just inside the posts and the fabric comes
    down inside the rail onto the deck; "outside": the cassette is face-mounted on the beam's outer face."""
    out = []
    x0, x1, y0, y1, w, p = q["x0"], q["x1"], q["y0"], q["y1"], q["w"], q["post"]
    front_posts = [pt for pt in q["posts"] if pt["y"] > (y0 + y1) / 2]
    for k, s in enumerate(screens):
        sd = dict(SCREEN_DEFAULTS)
        sd.update({kk: v for kk, v in (s or {}).items() if v is not None})
        side = str(sd["side"]).lower()
        hs = float(sd["housing_in"]) * IN
        inside = str(sd["mount"]).lower() != "outside"
        if side == "front":
            if inside:
                yin = min([pt["y"] - p / 2 for pt in front_posts] or [y1 - w])
                c = yin - hs / 2
                ext = (x0 + w, x1 - w)
            else:
                c = y1 + hs / 2
                ext = (x0, x1)
            plane, line = "y", c
        elif side in ("left", "right"):
            sgn = 1 if side == "left" else -1
            xe = x0 if side == "left" else x1
            if inside:
                c = xe + sgn * (p + hs / 2)
                fr = [sd2 for sd2 in screens if str((sd2 or {}).get("side", "front")).lower() == "front"]
                yin = min([pt["y"] - p / 2 for pt in front_posts] or [y1 - w])
                ext = (y0 + w, (yin - hs) if fr else yin)
            else:
                c = xe - sgn * hs / 2
                ext = (y0, y1)
            plane, line = "x", c
        else:
            continue
        a, b = ext
        if sd.get("from_ft") is not None:
            a = float(sd["from_ft"])
        if sd.get("to_ft") is not None:
            b = float(sd["to_ft"])
        a, b = min(a, b), max(a, b)
        mid = ((a + b) / 2, line) if plane == "y" else (line, (a + b) / 2)
        sf = _surface_at(surfaces, mid[0], mid[1], tol=1.0)
        bottom = float(sd["bottom"]) if sd.get("bottom") is not None else (sf["z"] if sf else q["z_deck"])
        if inside:
            hz0, hz1 = q["z_bot"] - hs, q["z_bot"]
        else:
            hz1 = q["z_bot"] + 2.0 * IN
            hz0 = hz1 - hs
        drop = max(0.0, min(1.0, float(sd.get("drop") or 0.0)))
        max_drop = hz0 - bottom
        if plane == "y":
            pa, pb = [a, line], [b, line]
            cass = (a, b, line - hs / 2, line + hs / 2)
        else:
            pa, pb = [line, a], [line, b]
            cass = (line - hs / 2, line + hs / 2, a, b)
        fab = str(sd["fabric"]).lower()
        width = b - a
        price_known = sd.get("price") is not None or sd.get("price_per_lf") is not None
        sell = (float(sd["price"]) if sd.get("price") is not None else
                float(sd.get("price_per_lf") if sd.get("price_per_lf") is not None else SCREEN_EST_PER_LF) * width)
        out.append(dict(index=k, side=side, mount="inside" if inside else "outside", plane=plane, line=line, a=pa, b=pb, width=width,
                        z_top=hz0, z_bottom=bottom, max_drop=max_drop, drop=drop, cassette=dict(x0=cass[0], x1=cass[1], y0=cass[2], y1=cass[3], z0=hz0, z1=hz1),
                        housing=hs, fabric=fab if fab in FABRIC else "mesh", color=str(sd["color"]),
                        name=sd.get("name") or f"{side} screen", sell=round(sell, 2), estimate=not price_known,
                        rate=(None if sd.get("price") is not None else float(sd.get("price_per_lf") if sd.get("price_per_lf") is not None else SCREEN_EST_PER_LF))))
    return out


# ================================================================== the blade's section
def blade_profile(width: float, thick: float) -> List[Tuple[float, float]]:
    """The blade's section about its pivot (ft): u across the blade, v through it — a shallow lens, crowned on top."""
    a, b = width / 2, width / 2 * 0.74
    return [(-a, 0.0), (-b, thick * 0.5), (b, thick * 0.5), (a, 0.0), (b, -thick * 0.32), (-b, -thick * 0.32)]


def blade_tris(pivot, axis: str, length: float, width: float, thick: float, angle_deg: float) -> List[List[float]]:
    """Triangles (plan ft, z up) of one blade turned angle_deg about its long axis: 0 = flat; the +x edge (y-blades) / +y
    edge (x-blades) rises as the angle grows. Wound outward."""
    th = math.radians(angle_deg)
    c, s = math.cos(th), math.sin(th)
    px, py, pz = pivot
    prof = [(u * c - v * s, u * s + v * c) for u, v in blade_profile(width, thick)]     # (across, up)

    def P(k, end):
        a_, up = prof[k]
        t = (end - 0.5) * length
        return [px + a_, py + t, pz + up] if axis == "y" else [px + t, py + a_, pz + up]
    tris = []
    n = len(prof)
    for k in range(n):
        k2 = (k + 1) % n
        tris += [[P(k, 0), P(k2, 0), P(k2, 1)], [P(k, 0), P(k2, 1), P(k, 1)]]
    for end in (0, 1):
        for k in range(1, n - 1):
            tris.append([P(0, end), P(k, end), P(k + 1, end)])
    out = []
    for A, B_, C_ in tris:                         # outward: the normal points away from the pivot
        n_ = [(B_[1] - A[1]) * (C_[2] - A[2]) - (B_[2] - A[2]) * (C_[1] - A[1]),
              (B_[2] - A[2]) * (C_[0] - A[0]) - (B_[0] - A[0]) * (C_[2] - A[2]),
              (B_[0] - A[0]) * (C_[1] - A[1]) - (B_[1] - A[1]) * (C_[0] - A[0])]
        cen = [(A[i] + B_[i] + C_[i]) / 3 - pivot[i] for i in range(3)]
        if sum(n_[i] * cen[i] for i in range(3)) < 0:
            B_, C_ = C_, B_
        out += [[round(v, 4) for v in A], [round(v, 4) for v in B_], [round(v, 4) for v in C_]]
    return out


# ================================================================== 3D
def materials(spec) -> Dict[str, dict]:
    """The roof's materials (empty when the job has no roof): powder-coated aluminum in the roof's color (the label carries
    "powder-coat", so the photoreal pass gives it the rail's satin powder coat) and the LED strip in the gutter's light track."""
    roofs = [r for r in roofs_of(spec) + [r for r in (getattr(spec.geometry, "louvered_roofs", None) or []) if r.get("_global")] if built(r)]
    if not roofs:
        return {}
    col = str(roofs[0].get("color") or "black")
    out = {MAT: dict(color=HEX.get(col.lower(), "#141416"), metal=0.55, rough=0.5, label=f"Suncoast {col.lower()} powder-coat aluminum"),
           LED_MAT: dict(color="#f3eadb", rough=0.4, label="LED light strip in the gutter's light track (warm white)", emit="#ffd8a8")}
    scr = [s_ for r in roofs for s_ in (r.get("screens") or [])]
    if scr:
        fab = str(scr[0].get("fabric") or "mesh").lower()
        fab = fab if fab in FABRIC else "mesh"
        sc = str(scr[0].get("color") or ("clear" if fab == "vinyl" else "black")).lower()
        hexc = "#dfe6e8" if fab == "vinyl" else {"black": "#1b1c1e", "grey": "#55585a", "gray": "#55585a", "white": "#e6e4de", "linen": "#d8cfbd",
                                                  "tan": "#a99677", "mocha": "#4d3d31"}.get(sc, "#1b1c1e")
        # opacity: the WebGL viewer's transparency; alpha: the photoreal pass's Principled BSDF alpha (see-through mesh / clear vinyl)
        out[SCREEN_MAT] = dict(color=hexc, rough=FABRIC[fab]["rough"], opacity=FABRIC[fab]["opacity"], alpha=FABRIC[fab]["alpha"],
                               label=("Suncoast retractable screen, clear vinyl" if fab == "vinyl" else f"Suncoast retractable screen, Phifer {sc} mesh"))
    return out


def draw_roof(add, q: dict) -> None:
    """The boxes of one resolved roof (layer "louvered", phase 8). add(kind, x0, x1, y0, y1, z0, z1, mat, phase, **kw)."""
    def A(kind, x0, x1, y0, y1, z0, z1, mat=MAT, tag="", **k):
        add(kind, x0, x1, y0, y1, z0, z1, mat, PHASE, tag=f"{q['name']}: {tag}" if tag else q["name"], layer=LAYER, **k)
    x0, x1, y0, y1, w, h = q["x0"], q["x1"], q["y0"], q["y1"], q["w"], q["h"]
    zt, zb = q["z_top"], q["z_bot"]
    bl = q["beam_label"]
    # perimeter beams (the house-side and front beams run the full length; the sides fit between them)
    A("lvbeam", x0, x1, y0, y0 + w, zb, zt, tag=(f"house-side {bl} beam on wall brackets at the soffit / roof line" if q["attach"] == "house" else f"rear {bl} beam"))
    A("lvbeam", x0, x1, y1 - w, y1, zb, zt, tag=f"front {bl} beam, integrated gutter")
    A("lvbeam", x0, x0 + w, y0 + w, y1 - w, zb, zt, tag=f"side {bl} beam, integrated gutter")
    A("lvbeam", x1 - w, x1, y0 + w, y1 - w, zb, zt, tag=f"side {bl} beam, integrated gutter")
    for xd in q["xs"]:
        A("lvbeam", xd - w / 2, xd + w / 2, y0 + w, y1 - w, zb, zt, tag=f"zone divider {bl} beam, gutters both sides")
    for yd in q["ys"]:
        A("lvbeam", x0 + w, x1 - w, yd - w / 2, yd + w / 2, zb, zt, tag=f"cross {bl} beam, gutters both sides")
    # the gutter round every zone, on the beams' inner faces at their bottom; the LED strip in its light track
    gz0, gz1 = zb, zb + GUTTER_H
    for c in q["zones"]:
        cx0, cx1, cy0, cy1 = c["x0"], c["x1"], c["y0"], c["y1"]
        if q["gutter"]:
            A("lvgutter", cx0, cx1, cy0, cy0 + GUTTER_W, gz0, gz1, tag="integrated gutter")
            A("lvgutter", cx0, cx1, cy1 - GUTTER_W, cy1, gz0, gz1, tag="integrated gutter")
            A("lvgutter", cx0, cx0 + GUTTER_W, cy0 + GUTTER_W, cy1 - GUTTER_W, gz0, gz1, tag="integrated gutter")
            A("lvgutter", cx1 - GUTTER_W, cx1, cy0 + GUTTER_W, cy1 - GUTTER_W, gz0, gz1, tag="integrated gutter")
        if q["lights"]:
            e, t_ = GUTTER_W + 0.01, 0.05
            for (a0, a1, b0, b1) in ((cx0 + e, cx1 - e, cy0 + e - t_, cy0 + e), (cx0 + e, cx1 - e, cy1 - e, cy1 - e + t_),
                                     (cx0 + e - t_, cx0 + e, cy0 + e, cy1 - e), (cx1 - e, cx1 - e + t_, cy0 + e, cy1 - e)):
                A("lvled", a0, a1, b0, b1, gz0 - 0.02, gz0 + 0.03, mat=LED_MAT, tag="LED light strip")
    # blades: each a mesh turned about its own long axis
    for b in q["blades"]:
        t_ = q["motor_t"] if b["motor"] else q["blade_t"]
        tri = blade_tris(b["pivot"], q["louver_dir"], b["length"], q["blade_w"], t_, q["angle_deg"])
        xs_ = [v[0] for v in tri]; ys_ = [v[1] for v in tri]; zs_ = [v[2] for v in tri]
        A("lvblade", min(xs_), max(xs_), min(ys_), max(ys_), min(zs_), max(zs_),
          tag=f"{'motor blade (Gaposa motor inside)' if b['motor'] else 'louver blade'} — zone {b['zone'] + 1}, blade {b['i'] + 1}", shape="mesh", pts=tri)
    # posts on base plates; the base cover; the downspout
    p, pl = q["post"], q["plate"]
    for pt in q["posts"]:
        px, py, zd = pt["x"], pt["y"], pt["z_deck"]
        rail = " — the rail post here (the rail panels bracket into it)" if pt["on_rail"] else ""
        A("lvplate", px - pl / 2, px + pl / 2, py - pl / 2, py + pl / 2, zd, zd + 0.04, tag="post base plate, bolted through the decking into the structure below")
        A("lvpost", px - p / 2 - 0.02, px + p / 2 + 0.02, py - p / 2 - 0.02, py + p / 2 + 0.02, zd + 0.04, zd + 0.36, tag="post base cover")
        A("lvpost", px - p / 2, px + p / 2, py - p / 2, py + p / 2, zd + 0.04, zb, tag=f"{q['post'] * 12:g}x{q['post'] * 12:g} aluminum post{rail}")
        out_y = 1 if py > (y0 + y1) / 2 else -1
        if q["downspouts"] == "post":
            yo = py + out_y * p / 2
            A("lvdown", px - 0.09, px + 0.09, min(yo, yo + out_y * 0.3), max(yo, yo + out_y * 0.3), zd + 0.12, zd + 0.3, tag="downspout outlet (the downspout runs inside the post)")
        elif q["downspouts"] == "external":
            yo = py + out_y * p / 2
            ya, yb_ = sorted((yo, yo + out_y * 0.21))
            A("lvdown", px - 0.12, px + 0.12, ya, yb_, zd + 0.35, zb + 0.15, tag="2x3 downspout on the post")
            A("lvdown", px - 0.12, px + 0.12, min(yb_, yb_ + out_y * 0.35), max(yb_, yb_ + out_y * 0.35) if out_y > 0 else ya, zd + 0.12, zd + 0.35, tag="downspout kick-out")
    # the house-side beam's wall brackets
    for bx in q["brackets"]:
        A("lvbracket", bx - 0.125, bx + 0.125, y0, y0 + 0.03, zb - 0.45, zb, tag="wall bracket (into the wall framing)")
        A("lvbracket", bx - 0.125, bx + 0.125, y0, y0 + w - 0.02, zb - 0.03, zb, tag="wall bracket seat")
    for sc in q.get("screens") or []:
        draw_screen(A, sc)


def draw_screen(A, sc: dict) -> None:
    """One retractable screen (the screens option): the cassette, a side track at each end, the fabric down to the drop
    and the bottom bar. Fabric and bar are kind "lvscreen" (a live viewer hides them and draws its own)."""
    nm = f"screen ({sc['side']}) — screens option"
    c = sc["cassette"]
    A("lvcassette", c["x0"], c["x1"], c["y0"], c["y1"], c["z0"], c["z1"], tag=f"{nm}: {sc['housing'] * 12:g}\" housing, motor inside")
    zt, zb = sc["z_top"], sc["z_bottom"]
    zh = zt - HEM_H - sc["drop"] * (sc["max_drop"] - HEM_H)          # the bottom bar's underside
    if sc["plane"] == "y":
        ln, (a, b) = sc["line"], (sc["a"][0], sc["b"][0])
        for e, sg in ((a, 1), (b, -1)):
            A("lvtrack", min(e, e + sg * TRACK_W), max(e, e + sg * TRACK_W), ln - TRACK_D / 2, ln + TRACK_D / 2, zb, zt, tag=f"{nm}: side track")
        a_, b_ = a + TRACK_W, b - TRACK_W
        if zt - (zh + HEM_H) > 0.01:
            A("lvscreen", a_, b_, ln - 0.01, ln + 0.01, zh + HEM_H, zt, mat=SCREEN_MAT, tag=f"{nm}: {sc['fabric']} fabric")
        A("lvscreen", a_, b_, ln - HEM_T / 2, ln + HEM_T / 2, zh, zh + HEM_H, tag=f"{nm}: bottom bar")
    else:
        ln, (a, b) = sc["line"], (sc["a"][1], sc["b"][1])
        for e, sg in ((a, 1), (b, -1)):
            A("lvtrack", ln - TRACK_D / 2, ln + TRACK_D / 2, min(e, e + sg * TRACK_W), max(e, e + sg * TRACK_W), zb, zt, tag=f"{nm}: side track")
        a_, b_ = a + TRACK_W, b - TRACK_W
        if zt - (zh + HEM_H) > 0.01:
            A("lvscreen", ln - 0.01, ln + 0.01, a_, b_, zh + HEM_H, zt, mat=SCREEN_MAT, tag=f"{nm}: {sc['fabric']} fabric")
        A("lvscreen", ln - HEM_T / 2, ln + HEM_T / 2, a_, b_, zh, zh + HEM_H, tag=f"{nm}: bottom bar")


def draw(add, L) -> List[dict]:
    """Hook for scene.build_scene / build_composite_scene: draw the roofs this layout owns in its frame — a part skips the
    job-level roofs it was handed in its frame (the composite scene draws those once, globally). Returns them resolved."""
    roofs = [r for r in (getattr(L.spec.geometry, "louvered_roofs", None) or []) if not r.get("_global") and built(r)]
    if not roofs:
        return []
    surf = surfaces_of(L)
    out = []
    for r in roofs:
        q = resolve(r, surf)
        draw_roof(add, q)
        out.append(q)
    return out


def descriptors(L) -> List[dict]:
    """scene.meta["louvered_roofs"]: per roof what a live viewer needs to turn the blades and run the screens, in the
    scene's frame (plan ft, z up). Angle rule: 0 = closed (chord horizontal, crown up); +angle = right-hand rotation about
    the blade's "axis" through its pivot — a section point (u across, v up) sits at pivot + (u cos a - v sin a) * across +
    (u sin a + v cos a) * [0, 0, 1]. Blade boxes: kind "lvblade" (each its own mesh), screens' fabric + bottom bar: kind
    "lvscreen"; every roof box has layer "louvered" (a roof a part declares itself has its tags prefixed "<part name>: ")."""
    spec = L.spec
    roofs = roofs_of(spec) if hasattr(L, "parts") else [r for r in (getattr(spec.geometry, "louvered_roofs", None) or []) if not r.get("_global")]
    roofs = [r for r in roofs if built(r)]
    if not roofs:
        return []
    surf = surfaces_of(L)
    out = []
    for r in roofs:
        q = resolve(r, surf)
        ydir = q["louver_dir"] == "y"
        ax = [0.0, -1.0, 0.0] if ydir else [1.0, 0.0, 0.0]        # right-hand rotation about this axis = the static meshes' sense
        acr = [1.0, 0.0, 0.0] if ydir else [0.0, 1.0, 0.0]
        out.append(dict(
            name=q["name"], brand=q["brand"], product=q["product"], color=q["color"], hex=q["hex"], layer=LAYER, phase=PHASE,
            angle_min_deg=ANGLE_RANGE[0], angle_open_deg=90.0, angle_max_deg=ANGLE_RANGE[1], angle_default_deg=q["angle_deg"],
            blade_mat=MAT, box_kind="lvblade", louver_dir=q["louver_dir"], axis=ax, across=acr, up=[0.0, 0.0, 1.0],
            rotation="right-hand about axis through the pivot; point (u, v) -> pivot + (u cos a - v sin a) * across + (u sin a + v cos a) * up; a = 0 closed flat, crown up",
            profile=[list(t) for t in blade_profile(q["blade_w"], q["blade_t"])], motor_profile=[list(t) for t in blade_profile(q["blade_w"], q["motor_t"])],
            blades=[dict(pivot=[round(v, 4) for v in b["pivot"]], axis=ax, length=round(b["length"], 4), width=q["blade_w"],
                         thick=(q["motor_t"] if b["motor"] else q["blade_t"]), offset=[0.0, 0.0], motor=b["motor"], zone=b["zone"], index=b["i"],
                         tag=f"{q['name']}: {'motor blade (Gaposa motor inside)' if b['motor'] else 'louver blade'} — zone {b['zone'] + 1}, blade {b['i'] + 1}")
                    for b in q["blades"]],
            frame=dict(x0=q["x0"], x1=q["x1"], y0=q["y0"], y1=q["y1"], z_top=q["z_top"], z_bottom=q["z_bot"], beam_w=q["w"], beam_h=q["h"],
                       beam=q["beam_label"], attach=q["attach"], z_attach=q["z_attach"], dividers_x=q["xs"], dividers_y=q["ys"]),
            zones=[dict(x0=c["x0"], x1=c["x1"], y0=c["y0"], y1=c["y1"], blades=c["n_blades"], motor_blade=c["motor"]) for c in q["zones"]],
            posts=[dict(x=pt["x"], y=pt["y"], z0=pt["z_deck"], z1=q["z_bot"], size=q["post"], rail_post=pt["on_rail"]) for pt in q["posts"]],
            z_deck=q["z_deck"], clear_ft=q["clear_ft"],
            screens=[dict(side=sc["side"], a=sc["a"], b=sc["b"], plane=sc["plane"], line=sc["line"], z_top=sc["z_top"], z_bottom=sc["z_bottom"],
                          max_drop=sc["max_drop"], down_default=sc["drop"], thick=0.02, hem=dict(h=HEM_H, t=HEM_T, mat=MAT), track_w=TRACK_W,
                          mat=SCREEN_MAT, box_kind="lvscreen", fabric=sc["fabric"], color=sc["color"], mount=sc["mount"],
                          cassette=sc["cassette"], tag=f"{q['name']}: screen ({sc['side']}) — screens option")
                     for sc in q["screens"]]))
    return out


# ================================================================== rail integration
def rail_points(spec, zones) -> List[Tuple[float, float, float]]:
    """layout.build_layout: (x, y, post size) in inches, the layout's frame, of the roof posts that stand on a deck-edge rail
    line — rail_layout_edges makes each a fixed rail post (one near a run's end takes that end)."""
    roofs = [r for r in (getattr(spec.geometry, "louvered_roofs", None) or []) if built(r)]
    if not roofs:
        return []
    surf = zone_surfaces(zones, spec.geometry.height_in)
    out = []
    for r in roofs:
        q = resolve(r, surf)
        out += [(pt["x"] * 12.0, pt["y"] * 12.0, q["post"] * 12.0) for pt in q["posts"] if pt["on_rail"]]
    return out


IRX_WALL_KIT = dict(each=42.0, source="EST — confirm the Impression Rail Express wall-mount bracket kit with D&D",
                    desc="TimberTech Impression Rail Express wall-mount bracket kit, {color} — a rail panel end into a Suncoast roof post")


def takeoff_hook(t) -> None:
    """takeoff.build_takeoff: the rail posts that are roof posts come off the rail post kits (and their 4 HeadLOKs), and
    every panel end that lands on a roof post gets a wall-mount bracket kit. No roof post on the rail: nothing changes."""
    from .takeoff import Line
    rl = t.layout.rail
    if not rl:
        return
    roof = [p for p in rl.posts if getattr(p, "roof", False)]
    if not roof:
        return
    from collections import Counter
    pk = Counter(p.kind for p in roof)
    n = len(roof)
    words = f"{n} {'is a' if n == 1 else 'are'} louvered-roof post{'s' if n != 1 else ''}"
    for ln in t.lines:
        if ln.category != "Rail":
            continue
        low = ln.item.lower()
        if "post kit" in low:
            ln.net, ln.order = max(0, ln.net - n), max(0, ln.order - n)
            ln.why = f"{ln.why}; {words} (Suncoast 6x6 aluminum)"
        else:
            for kind, k in pk.items():
                if f" {kind.lower()} post " in low:
                    ln.net, ln.order = max(0, ln.net - k), max(0, ln.order - k)
                    ln.why = f"{ln.why}; {k} {kind} {'is a' if k == 1 else 'are'} louvered-roof post{'s' if k != 1 else ''}"
    for ln in t.lines:
        if ln.category == "Hardware" and "HeadLOK" in ln.item and "rail posts x 4" in ln.why:
            import re
            from .catalog import PRICEBOOK
            m = re.search(r"\((\d+) rail posts x 4\)", ln.why)
            if m:
                n_rp = max(0, int(m.group(1)) - n)
                cnt = PRICEBOOK["hardware"]["HeadLOK6_50"].get("count", 50)
                need = 4 * n_rp
                ln.net = ln.order = int(math.ceil(need / cnt)) if need else 0
                ln.why = f"{need} needed  ({n_rp} rail posts x 4; the {n} roof post{'s' if n != 1 else ''} bolt down through their own base plates)"
    t.lines[:] = [ln for ln in t.lines if not (ln.order == 0 and ln.net == 0 and ln.category in ("Rail", "Hardware") and ("post" in ln.item.lower() or "HeadLOK" in ln.item))]
    ends = 0
    rxy = [(p.x, p.y) for p in roof]
    for s_ in rl.sections:
        for e in (s_.p0, s_.p1):
            if e is not None and any(abs(e[0] - a) < 0.6 and abs(e[1] - b) < 0.6 for a, b in rxy):
                ends += 1
    ends = ends or 2 * n
    color = rl.color or "black"
    t.lines.append(Line("Rail", IRX_WALL_KIT["desc"].replace("{color}", color), ends, ends, "kit",
                        f"exact  ({ends} panel end{'s' if ends != 1 else ''} on the {n} roof post{'s' if n != 1 else ''})", IRX_WALL_KIT["each"], IRX_WALL_KIT["source"]))
    xs = ", ".join(ftin(p.x) for p in roof)
    if "Rail" in t.schedule:
        t.schedule["Rail"] += (f"; {words} at {xs} from the left end of this level: the 6x6 aluminum post is base-plated on the deck over solid "
                               f"blocking / the column below and the rail panels hang on wall-mount brackets screwed into it")
    t.notes.append(f"louvered roof: {words} at {xs} — no rail post kit there; {ends} wall-mount bracket kits")


# ================================================================== prices (sell = check / ACH)
def roof_area_sf(r: dict) -> float:
    return abs(float(r["x1"]) - float(r["x0"])) * abs(float(r["y1"]) - float(r["y0"]))


def roof_sell(r: dict) -> float:
    """The roof's sell price (check / ACH): `price`, else `price_per_sf` x the roof area; 0 when neither is set."""
    if r.get("price") is not None:
        return round(float(r["price"]), 2)
    if r.get("price_per_sf") is not None:
        return round(float(r["price_per_sf"]) * roof_area_sf(r), 2)
    return 0.0


def _finance(spec, sell: float) -> Tuple[float, float]:
    from .catalog import PRICEBOOK as pb
    retail = round(sell * (1 + spec.extras.retail_markup)) if spec.extras.retail_markup is not None else round(sell / pb["retail_factor"])
    r = pb["finance_rate"] / 12
    n = pb["finance_years"] * 12
    return retail, round(retail * r / (1 - (1 + r) ** -n), 2)


def scope_words(q: dict) -> List[str]:
    """What the roof is, line by line (facts, customer wording)."""
    nz = q["n_zones"]
    n_bl = len(q["blades"])
    rail_posts = sum(1 for p in q["posts"] if p["on_rail"])
    W_, D_ = ftin(q["W"] * 12), ftin(q["D"] * 12)
    out = [f"{q['brand']} {q['product']}, motorized, {W_} x {D_} ({q['area']:g} SF), {str(q['color']).lower()} powder-coated aluminum",
           f"{n_bl} louver blades, {q['blade_w'] * 12:g}\" wide on {q['spacing'] * 12:g}\" centres, in {nz} motor zone{'s' if nz != 1 else ''} "
           f"(one Gaposa motor blade each); the blades turn from closed to {ANGLE_RANGE[1]:g} degrees open by remote or app",
           f"{q['beam_label']} aluminum perimeter frame with the integrated gutter round every zone"
           + (f"; {len(q['xs']) + len(q['ys'])} zone divider beam{'s' if len(q['xs']) + len(q['ys']) != 1 else ''}" if (q['xs'] or q['ys']) else ""),
           (f"House side: the beam hangs on the house wall on brackets at the soffit / roof line — no posts at the house"
            if q["attach"] == "house" else "Freestanding on posts at every corner"),
           f"{len(q['posts'])} {q['post'] * 12:g}x{q['post'] * 12:g} aluminum posts on base plates on the deck"
           + (f"; {'both are' if rail_posts == 2 else ('it is' if rail_posts == 1 else f'{rail_posts} are')} the rail post{'s' if rail_posts != 1 else ''} at the deck edge — the rail panels bracket into {'them' if rail_posts != 1 else 'it'}" if rail_posts else ""),
           f"Top of the frame {ftin((q['z_top'] - q['z_deck']) * 12)} above the deck; {ftin(q['clear_ft'] * 12)} clear under the beams"]
    if q["downspouts"] == "post":
        out.append("Downspouts run inside the posts")
    elif q["downspouts"] == "external":
        out.append("2x3 downspouts on the posts")
    if q["lights"]:
        out.append("LED light strip in the gutter's light track")
    return out


def roof_pricing(spec, L=None) -> dict:
    """The roof's own price for its own document (and the option line): per roof the area, $/SF, sell (check / ACH),
    financed and monthly, plus the scope lines; totals. Uses the deck under the roof when a layout is given."""
    surf = surfaces_of(L) if L is not None else []
    rows = []
    for r in roofs_of(spec):
        q = resolve(r, surf)
        sell = roof_sell(r)
        fin, mo = _finance(spec, sell)
        scr = [dict(name=sc["name"], side=sc["side"], width_ft=round(sc["width"], 2), drop_ft=round(sc["max_drop"], 2), fabric=sc["fabric"], color=sc["color"],
                    mount=sc["mount"], sell=sc["sell"], rate_per_lf=sc["rate"], estimate=sc["estimate"],
                    words=f"Motorized retractable screen, {sc['side']}: {ftin(sc['width'] * 12)} wide, {ftin(sc['max_drop'] * 12)} drop, "
                          + ("clear vinyl" if sc["fabric"] == "vinyl" else f"{sc['color']} mesh") + f", {sc['housing'] * 12:g}\" housing, side tracks, weighted bottom bar")
               for sc in q["screens"]]
        s_sell = round(sum(x["sell"] for x in scr), 2)
        s_fin, s_mo = _finance(spec, s_sell)
        rows.append(dict(name=q["name"], brand=q["brand"], product=q["product"], color=q["color"], width_ft=q["W"], depth_ft=q["D"], area_sf=q["area"],
                         price_per_sf=(float(r["price_per_sf"]) if r.get("price_per_sf") is not None and r.get("price") is None else None),
                         sell=sell, financed=fin, monthly=mo, priced=q["priced"], option_name=option_name(q), scope=scope_words(q),
                         frame=dict(x0=q["x0"], x1=q["x1"], y0=q["y0"], y1=q["y1"], z_top=q["z_top"], z_deck=q["z_deck"], clear_ft=q["clear_ft"]),
                         screens=scr, screens_sell=s_sell, screens_financed=s_fin, screens_monthly=s_mo, screens_estimate=any(x["estimate"] for x in scr),
                         screens_priced=q["screens_priced"], notes=q["notes"]))
    sell = round(sum(x["sell"] for x in rows), 2)
    fin, mo = _finance(spec, sell)
    s_sell = round(sum(x["screens_sell"] for x in rows), 2)
    s_fin, s_mo = _finance(spec, s_sell)
    w_fin, w_mo = _finance(spec, sell + s_sell)
    return dict(roofs=rows, sell=sell, financed=fin, monthly=mo, screens_sell=s_sell, screens_financed=s_fin, screens_monthly=s_mo,
                with_screens=dict(sell=round(sell + s_sell, 2), financed=w_fin, monthly=w_mo))


def option_name(q: dict) -> str:
    return q.get("option_name") or f"{q['brand']} louvered roof — {ftin(q['W'] * 12)} x {ftin(q['D'] * 12)}, motorized, {str(q['color']).lower()}"


def option_prices(spec, gm: float) -> list:
    """pricing.price: the roofs priced "option" as options on the deck's quote — check = the roof's sell, financed = sell
    / 0.93 (or the job's retail markup), cost = sell x (1 - GM). [] when no roof is an option."""
    from .pricing import OptionPrice
    out = []
    for r in roofs_of(spec):
        q = resolve(r, [])
        if q["priced"] == "option":
            sell = round(roof_sell(r))
            fin, _ = _finance(spec, sell)
            out.append(OptionPrice(option_name(q), fin, sell, round(sell * (1 - gm), 2),
                                   f"{q['area']:g} SF" + (f" at ${float(r['price_per_sf']):,.0f}/SF" if r.get("price_per_sf") is not None and r.get("price") is None else "")
                                   + " — its own document has the detail"))
        if q["screens"] and q["screens_priced"] == "option":
            sell = round(sum(sc["sell"] for sc in q["screens"]))
            fin, _ = _finance(spec, sell)
            sides = " + ".join(f"{sc['side']} {ftin(sc['width'] * 12)}" for sc in q["screens"])
            est = any(sc["estimate"] for sc in q["screens"])
            out.append(OptionPrice(f"Motorized screens on the louvered roof — {sides}", fin, sell, round(sell * (1 - gm), 2),
                                   ("ESTIMATE — " if est else "") + f"{len(q['screens'])} screen{'s' if len(q['screens']) != 1 else ''}, with the louvered roof"))
    return out


# ================================================================== loads (for the structure under the posts)
def post_loads(q: dict, dead_psf: float = 6.0, snow_psf: float = 30.0) -> List[dict]:
    """Rough gravity reactions per post (lb): the frame's tributary area at (dead + snow) — an attached roof puts half
    its depth on the house beam. For the framing under the posts; Suncoast's engineering governs."""
    n = max(1, len(q["posts"]))
    trib = q["area"] / 2.0 / n if q["attach"] == "house" else q["area"] / n
    return [dict(x=pt["x"], y=pt["y"], trib_sf=round(trib, 1), dead_lb=round(trib * dead_psf), snow_lb=round(trib * snow_psf),
                 total_lb=round(trib * (dead_psf + snow_psf))) for pt in q["posts"]]


# ================================================================== the drawing sheet (A-403)
def sheet(L, S, t, meta) -> Optional[str]:
    """A-403: the louvered roof over the deck — the plan (frame, zones, blades, posts on the rail line, the house beam on its
    brackets), section A through the house wall, the roof and the deck (heights, clearances, the attachment), and detail 1:
    the post on the deck edge (base plate over solid blocking / the column below, the rail panels bracketed into the post).
    None when the job has no roof built. S is the full scene (the roof boxes included)."""
    from .drawings import (T, TH, R, LN, C, PG, sheet as _sheet, plan_xform, elev_xform, dim_h, dim_v, INK, GOLD, MUTE, FILL,
                           _panel, _lead, _PANEL)
    from .layout import RAIL_POST_INSET
    from .catalog import actual
    import textwrap
    spec = L.spec
    roofs = [r for r in roofs_of(spec) if built(r)] if hasattr(L, "parts") else \
        [r for r in (getattr(spec.geometry, "louvered_roofs", None) or []) if not r.get("_global") and built(r)]
    if not roofs:
        return None
    surf = surfaces_of(L)
    q = resolve(roofs[0], surf)
    o: List[str] = []
    x0, x1, y0, y1, w, h, p = q["x0"], q["x1"], q["y0"], q["y1"], q["w"], q["h"], q["post"]
    zd, zt, zb = q["z_deck"], q["z_top"], q["z_bot"]
    BLACK, HOUSE, DECK = "#1d1d1f", FILL["house"], FILL["deck"]
    rp = RAIL_POST_INSET * IN
    front_posts = sorted([pt for pt in q["posts"] if pt["y"] > (y0 + y1) / 2], key=lambda pt: pt["x"])

    # ---------------------------------------------------------------- plan
    _panel(o, 14, 4, 560, 336, "PLAN", f"{q['brand'].upper()} LOUVERED ROOF OVER THE DECK")
    px0, px1, py0, py1 = x0 - 3.0, x1 + 3.0, y0 - 2.6, y1 + 3.4
    X, Y, sc = plan_xform(px0, px1, py0, py1, 34, 30, 520, 290)
    o.append(R(X(px0), Y(py0), (px1 - px0) * sc, (y0 - py0) * sc, HOUSE, INK, 0.8))
    o.append(T(X(px0) + 6, Y(y0) - 6, "HOUSE WALL", 7.5, 900, fill=MUTE))
    for s in surf:                       # the deck under and around the roof, clipped to the panel
        a0, a1, b0, b1 = max(s["x0"], px0), min(s["x1"], px1), max(s["y0"], y0), min(s["y1"], py1)
        if a1 - a0 > 0.05 and b1 - b0 > 0.05:
            o.append(R(X(a0), Y(b0), (a1 - a0) * sc, (b1 - b0) * sc, DECK, INK, 0.8, 'fill-opacity="0.55"'))
    for s in surf:
        a0, a1 = max(s["x0"], px0), min(s["x1"], px1)
        if a1 - a0 > 2.5 and s["y1"] < py1:
            o.append(T(X((a0 + a1) / 2), Y(s["y1"]) + 11, f"{s['name'].upper()} · deck {ftin(s['z'] * 12)}", 6.6, 800, "middle", MUTE))
    rails = [b for b in S.boxes if b.kind == "railpost" and px0 <= (b.x0 + b.x1) / 2 <= px1 and py0 <= (b.y0 + b.y1) / 2 <= py1]
    ys_rail = sorted({round((b.y0 + b.y1) / 2, 2) for b in rails})
    for yr in ys_rail:
        xs_r = [(b.x0 + b.x1) / 2 for b in rails if abs((b.y0 + b.y1) / 2 - yr) < 0.05] + [pt["x"] for pt in front_posts if abs(pt["y"] - yr) < 0.1]
        if len(xs_r) > 1:
            o.append(LN(X(min(xs_r)), Y(yr), X(max(xs_r)), Y(yr), INK, 1.4))
    for b in rails:
        o.append(R(X(b.x0), Y(b.y0), max(2.5, (b.x1 - b.x0) * sc), max(2.5, (b.y1 - b.y0) * sc), INK, INK, 0.4))
    # the frame: beams, the zone dividers, the blades
    for b in [b for b in S.boxes if getattr(b, "layer", "") == LAYER and b.kind == "lvbeam"]:
        o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, BLACK, BLACK, 0.4))
    for bl in q["blades"]:
        px_, py_, _ = bl["pivot"]
        L_ = bl["length"] / 2
        if q["louver_dir"] == "y":
            o.append(LN(X(px_), Y(py_ - L_), X(px_), Y(py_ + L_), "#3c3c40", 2.4 if bl["motor"] else 0.9))
        else:
            o.append(LN(X(px_ - L_), Y(py_), X(px_ + L_), Y(py_), "#3c3c40", 2.4 if bl["motor"] else 0.9))
    for zi, c in enumerate(q["zones"]):
        cx_, cy_ = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        o.append(TH(X(cx_), Y(cy_) - 4, f"ZONE {zi + 1}", 8, 900, "middle", halo="#fff"))
        o.append(TH(X(cx_), Y(cy_) + 7, f"{c['n_blades']} blades · 1 motor blade", 6.6, 700, "middle", halo="#fff"))
    # posts on their plates
    for pt in q["posts"]:
        pl_ = q["plate"]
        o.append(R(X(pt["x"] - pl_ / 2), Y(pt["y"] - pl_ / 2), pl_ * sc, pl_ * sc, "#fff", INK, 0.7))
        o.append(R(X(pt["x"] - p / 2), Y(pt["y"] - p / 2), p * sc, p * sc, BLACK, INK, 0.5))
    # dimensions
    dim_h(o, X, Y(py1) - 8, x0, x1, f"{ftin(q['W'] * 12)} frame", 8)
    if len(front_posts) > 1:
        for a_, b_ in zip(front_posts, front_posts[1:]):
            dim_h(o, X, Y(py1) - 26, a_["x"], b_["x"], f"{ftin((b_['x'] - a_['x']) * 12)} post to post", 7.4)
    for zi, c in enumerate(q["zones"]):
        if len(q["zones"]) > 1:
            dim_h(o, X, Y(y0) + 14, c["x0"] - (w if zi == 0 else w / 2), c["x1"] + (w if zi == len(q["zones"]) - 1 else w / 2), f"zone {zi + 1} {ftin(((c['x1'] - c['x0']) + (w if zi in (0, len(q['zones']) - 1) else 0) + w / 2) * 12)}", 6.8)
    dim_v(o, Y, X(x1) + 22, y0, y1, f"{ftin(q['D'] * 12)}", 8, left=False)
    if front_posts:
        fp = front_posts[0]
        o.append(C(X(fp["x"]) - 16, Y(fp["y"]) + 16, 7, "#fff", INK, 0.8)); o.append(T(X(fp["x"]) - 16, Y(fp["y"]) + 19, "1", 7.5, 900, "middle"))
    # the section cut A (through zone 1, across the house wall)
    xa = (q["zones"][0]["x0"] + q["zones"][0]["x1"]) / 2 + (q["spacing"] / 2 if q["louver_dir"] == "y" else 0)
    o.append(LN(X(xa), Y(py0) + 4, X(xa), Y(py1) - 36, GOLD, 1.1, "6 3"))
    for yy_ in (Y(py0) + 4, Y(py1) - 36):
        o.append(C(X(xa), yy_, 6.5, GOLD, INK, 0.6)); o.append(T(X(xa), yy_ + 3, "A", 7, 900, "middle", "#fff"))
    o.append(TH(X(x0) + 6, Y(y0 + w) + 12, f"house-side {q['beam_label']} beam on wall brackets @ {BRACKET_OC_FT * 12:g}\" OC — no posts at the house"
               if q["attach"] == "house" else f"rear {q['beam_label']} beam", 6.6, 700, halo="#fff"))
    o.append(TH(X(x0) + 6, Y(y1 - w) - 5, f"front {q['beam_label']} beam · integrated gutter", 6.6, 700, halo="#fff"))
    rail_n = sum(1 for pt in q["posts"] if pt["on_rail"])
    if rail_n:
        o.append(TH(X((x0 + x1) / 2), Y(py1) - 42, f"the {rail_n} roof post{'s are' if rail_n != 1 else ' is'} the rail post{'s' if rail_n != 1 else ''} on the deck edge (rail line {ftin(rp * 12)} in from the frame face)", 6.6, 700, "middle", halo="#fff"))

    # ---------------------------------------------------------------- section A
    _panel(o, 584, 4, 402, 336, "A", "SECTION — HOUSE WALL, ROOF, DECK")
    sy0, sy1 = y0 - 3.2, y1 + 3.6
    z_lo = max(0.0, zd - 3.5)
    Xs, Zs, scs = elev_xform(sy0, sy1, z_lo - 0.6, zt + 2.6, 600, 28, 300, 300)
    o.append(R(Xs(sy0), Zs(zt + 2.2), (y0 - sy0) * scs, (zt + 2.2 - (z_lo - 0.6)) * scs, HOUSE, INK, 0.9))
    o.append(T(Xs((sy0 + y0) / 2), Zs((zt + z_lo) / 2), "HOUSE", 8, 900, "middle", MUTE, rot=-90))
    soff = 1.0
    o.append(PG([(Xs(y0 - 0.3), Zs(zt + 0.05)), (Xs(y0 + soff), Zs(zt + 0.05)), (Xs(y0 + soff), Zs(zt + 0.6)), (Xs(y0 - 0.3), Zs(zt + 1.2))], "#cfc6b4", INK, 0.7))
    _lead(o, Xs(y0 + soff * 0.6), Zs(zt + 0.4), Xs(y0 + 2.6), Zs(zt + 2.15), "existing eave: soffit / roof line (field verify)", 6.3)
    # the deck: decking + frame band, the rail, the column below the roof post
    jd = actual(spec.framing.joist_size)[1] * IN if spec.framing.joist_size else 9.25 * IN
    yf = max((s["y1"] for s in surf if s["z"] == zd and s["x0"] - 0.1 <= xa <= s["x1"] + 0.1), default=y1)
    o.append(R(Xs(y0), Zs(zd), (yf - y0 + 0.08) * scs, 0.1 * scs, DECK, INK, 0.7))
    o.append(R(Xs(y0), Zs(zd - 0.1), (yf - y0) * scs, jd * scs, FILL["timber"], INK, 0.6))
    o.append(R(Xs(yf - 0.25), Zs(zd - 0.1 - jd), 0.25 * scs, 1.0 * scs, FILL["timber_dk"], INK, 0.4, 'stroke-dasharray="3 2"'))
    py = front_posts[0]["y"] if front_posts else y1 - p / 2
    o.append(R(Xs(py - 0.33), Zs(zd - 0.1 - jd - 0.05), 0.67 * scs, max(0.1, zd - 0.15 - jd - z_lo + 0.6) * scs, FILL["timber"], INK, 0.6, 'stroke-dasharray="4 2"'))
    _lead(o, Xs(py), Zs(zd - 2.2), Xs(py) + 26, Zs(zd - 2.6), "column / beam under the roof post — per the framing plan", 6.2)
    # the roof
    o.append(R(Xs(y0), Zs(zt), w * scs, h * scs, BLACK, INK, 0.5))
    o.append(R(Xs(y1 - w), Zs(zt), w * scs, h * scs, BLACK, INK, 0.5))
    o.append(PG([(Xs(y0), Zs(zb)), (Xs(y0 + 0.03), Zs(zb)), (Xs(y0 + 0.03), Zs(zb - 0.42)), (Xs(y0), Zs(zb - 0.42))], BLACK))
    o.append(R(Xs(y0), Zs(zb), (w - 0.02) * scs, 0.035 * scs, BLACK, INK, 0.3))
    o.append(R(Xs(py - p / 2), Zs(zb), p * scs, (zb - zd) * scs, BLACK, INK, 0.5))
    o.append(R(Xs(py - q["plate"] / 2), Zs(zd + 0.04), q["plate"] * scs, 0.04 * scs + 1, "#555", INK, 0.4))
    ang = math.radians(q["angle_deg"])
    if q["louver_dir"] == "y":            # blades run along the cut: one seen lengthwise beyond the cut
        ext = abs(q["blade_w"] / 2 * math.sin(ang)) + q["blade_t"] / 2
        o.append(R(Xs(y0 + w + 0.05), Zs(q["z_pivot"] + ext), (q["D"] - 2 * w - 0.1) * scs, 2 * ext * scs, "#6d6d72", INK, 0.4, 'fill-opacity="0.75"'))
    else:                                  # blades cut across: each blade's section at its angle
        for bl in q["blades"]:
            if bl["zone"] != 0:
                continue
            cy_, cz_ = bl["pivot"][1], bl["pivot"][2]
            pts_ = [(cy_ + u * math.cos(ang) - v * math.sin(ang), cz_ + u * math.sin(ang) + v * math.cos(ang)) for u, v in blade_profile(q["blade_w"], q["blade_t"])]
            o.append(PG([(Xs(a_), Zs(b_)) for a_, b_ in pts_], "#3c3c40", INK, 0.3))
    # the rail tying into the post
    rh = (spec.railing.height_in or 36.0) * IN
    o.append(R(Xs(py - p / 2 - 0.45), Zs(zd + rh), 0.45 * scs, 0.12 * scs, BLACK, INK, 0.3, 'fill-opacity="0.6"'))
    o.append(R(Xs(py - p / 2 - 0.45), Zs(zd + 0.4), 0.45 * scs, 0.1 * scs, BLACK, INK, 0.3, 'fill-opacity="0.6"'))
    if spec.railing.drink_rail:
        o.append(R(Xs(py - 0.23), Zs(zd + rh + 0.2), 0.46 * scs, 0.08 * scs, DECK, INK, 0.4))
    # heights
    dim_v(o, Zs, Xs(sy1) - 6, z_lo - 0.6 if z_lo <= 0.01 else z_lo, zd, (f"{ftin(zd * 12)} above the patio" if z_lo <= 0.01 else ""), 6.6, left=True)
    dim_v(o, Zs, Xs(sy1) - 6, zd, zb, f"{ftin((zb - zd) * 12)} clear", 7, left=True)
    dim_v(o, Zs, Xs(sy1) - 6, zb, zt, f"{h * 12:g}\"", 6.4, left=True)
    dim_v(o, Zs, Xs(y0) + 12, zd, zt, f"{ftin((zt - zd) * 12)} deck to top of frame", 6.6, left=False)
    dim_h(o, Xs, Zs(zt) - 12, y0, y1, ftin(q["D"] * 12), 7.2)
    o.append(T(Xs(sy1) - 4, Zs(zt) + 3, f"TOP OF FRAME {ftin(zt * 12)}", 6.4, 800, "end", MUTE))
    o.append(T(Xs(sy1) - 4, Zs(zd) - 3, f"DECK {ftin(zd * 12)}", 6.4, 800, "end", MUTE))
    _lead(o, Xs(y0 + w / 2), Zs(zb - 0.3), Xs(y0 + 1.2), Zs(zb - 1.3), f"house-side {q['beam_label']} beam on wall brackets @ {BRACKET_OC_FT * 12:g}\" OC into the wall framing", 6.2)
    _lead(o, Xs(y1 - w / 2), Zs(zt - h / 2), Xs(y1 - 3.6), Zs(zt + 1.2), f"front {q['beam_label']} beam, integrated gutter + LED strip", 6.2)
    _lead(o, Xs(py), Zs(zd + 4.5), Xs(py) - 74, Zs(zd + 5.6), f"{p * 12:g}x{p * 12:g} aluminum post = the rail post, downspout inside", 6.2)
    _lead(o, Xs((y0 + y1) / 2), Zs(q["z_pivot"]), Xs((y0 + y1) / 2) - 40, Zs(zb - 0.9), f"{q['blade_w'] * 12:g}\" blades @ {q['spacing'] * 12:g}\", drawn {q['angle_deg']:g}° open (0-{ANGLE_RANGE[1]:g}°)", 6.2)

    # ---------------------------------------------------------------- detail 1: the post on the deck edge
    _panel(o, 584, 346, 402, 260, "1", "POST ON THE DECK EDGE — THE RAIL POST")
    dx0, dz0, s1 = 640, 590, 13.0           # px per inch
    def DX(v): return dx0 + v * s1 * 0.55
    def DZ(v): return dz0 - v * s1 * 0.55
    # deck edge: rim plies, blocking, decking, fascia (inches from the frame face, z from the frame bottom)
    jd_in = jd * 12
    o.append(R(DX(-3.0), DZ(jd_in), 3.0 * s1 * 0.55, jd_in * s1 * 0.55, FILL["timber"], INK, 0.7))
    o.append(R(DX(-6.0), DZ(jd_in), 3.0 * s1 * 0.55, jd_in * s1 * 0.55, FILL["timber_dk"], INK, 0.6))
    o.append(R(DX(-24.0), DZ(jd_in), 18.0 * s1 * 0.55, jd_in * s1 * 0.55, FILL["timber"], INK, 0.5, 'fill-opacity="0.55"'))
    o.append(T(DX(-15), DZ(jd_in / 2), "solid blocking", 6.2, 800, "middle"))
    o.append(R(DX(0), DZ(jd_in + 1.0), 0.5 * s1 * 0.55, (jd_in + 1.0) * s1 * 0.55, DECK, INK, 0.5))
    o.append(R(DX(-26.0), DZ(jd_in + 1.0), 26.97 * s1 * 0.55, 1.0 * s1 * 0.55, DECK, INK, 0.6))
    zbase = jd_in + 1.0
    pin = rp * 12
    pc = -pin                                # post centre, inches from the frame face (negative = inboard)
    pl_in, p_in = q["plate"] * 12, p * 12
    o.append(R(DX(pc - pl_in / 2), DZ(zbase + 0.5), pl_in * s1 * 0.55, 0.5 * s1 * 0.55, "#555", INK, 0.6))
    o.append(R(DX(pc - p_in / 2), DZ(zbase + 22), p_in * s1 * 0.55, 21.5 * s1 * 0.55, BLACK, INK, 0.6))
    o.append(R(DX(pc - p_in / 2 - 0.25), DZ(zbase + 4.3), (p_in + 0.5) * s1 * 0.55, 3.8 * s1 * 0.55, "#2a2a2e", INK, 0.5))
    for bx in (pc - pl_in / 2 + 0.8, pc + pl_in / 2 - 0.8):
        o.append(LN(DX(bx), DZ(zbase + 0.6), DX(bx), DZ(zbase - jd_in * 0.85), INK, 1.4))
        o.append(R(DX(bx) - 2.5, DZ(zbase + 0.9), 5, 2.5, INK, INK, 0.3))
    o.append(R(DX(pc - p_in / 2 - 4.0), DZ(zbase + 21.0), 4.0 * s1 * 0.55, 1.4 * s1 * 0.55, BLACK, INK, 0.3, 'fill-opacity="0.65"'))
    o.append(R(DX(pc - p_in / 2 - 4.0), DZ(zbase + 4.5), 4.0 * s1 * 0.55, 1.0 * s1 * 0.55, BLACK, INK, 0.3, 'fill-opacity="0.65"'))
    o.append(R(DX(pc + p_in / 2), DZ(zbase + 2.4), 3.0 * s1 * 0.55, 1.6 * s1 * 0.55, "#444", INK, 0.4))
    o.append(T(DX(pc) + 2, DZ(zbase + 23.5), "post continues to the front beam", 6.2, 700, "middle", MUTE))
    _lead(o, DX(pc + pl_in / 2 - 0.3), DZ(zbase + 0.25), DX(4.5), DZ(zbase + 8.0), f"{pl_in:g}\" base plate on the decking, through-bolted into solid blocking / the column below", 6.0)
    _lead(o, DX(pc), DZ(zbase + 3.0), DX(4.5), DZ(zbase + 14.0), "base cover over the plate and bolts", 6.0)
    _lead(o, DX(pc + p_in / 2 + 1.5), DZ(zbase + 1.6), DX(4.5), DZ(zbase + 4.0), "downspout outlet (the downspout runs inside the post)", 6.0)
    _lead(o, DX(pc - p_in / 2 - 2.0), DZ(zbase + 21.7), DX(-24), DZ(zbase + 27.5), "rail top rail on a wall-mount bracket into the post", 6.0)
    _lead(o, DX(pc - p_in / 2 - 2.0), DZ(zbase + 5.0), DX(-24), DZ(zbase + 12.0), "bottom rail bracket into the post", 6.0)
    _lead(o, DX(-1.5), DZ(jd_in * 0.5), DX(-25), DZ(-3.5), f"doubled {spec.framing.joist_size or '2x10'} rim + fascia", 6.0)
    o.append(LN(DX(0), DZ(-1.5), DX(pc), DZ(-1.5), INK, 0.6)); o.append(LN(DX(0), DZ(-0.6), DX(0), DZ(-2.4), INK, 0.6)); o.append(LN(DX(pc), DZ(-0.6), DX(pc), DZ(-2.4), INK, 0.6))
    o.append(T((DX(0) + DX(pc)) / 2, DZ(-1.5) + 9, f"{ftin(pin)} — post centre on the rail line", 6.0, 700, "middle"))

    # ---------------------------------------------------------------- notes
    _panel(o, 14, 346, 560, 260, "", "WHAT IT IS")
    loads = post_loads(q, snow_psf=float(spec.site.ground_snow_psf or 30))
    notes = scope_words(q) + [
        f"Frame {q['beam_label']} aluminum (Suncoast spans: 2x8 to 15', 2x10 to 18', 4x8 to 22' between posts); longest span here {ftin(q['span_ft'] * 12)}.",
        f"Blades span up to {BLADE_SPAN_MAX_FT:g}' (snow-load dependent); one motor blade per zone, {MOTOR_SF:g} SF a motor at most.",
        f"Posts carry ~{max(x['total_lb'] for x in loads):,} lb each ({max(x['trib_sf'] for x in loads):g} SF at {6:g} psf dead + {spec.site.ground_snow_psf:g} psf snow) — the framing under each post is sized for it; Suncoast's engineering for the site's snow and wind governs the roof.",
        "House side: the brackets go into the wall framing (field verify the soffit, the wall and the framing behind it); flashing and sealant at every fastener.",
    ] + [n for n in q["notes"]]
    yy = 372
    for ln in notes:
        for k_, w_ in enumerate(textwrap.wrap(ln, 108)):
            o.append(T(26 if k_ == 0 else 34, yy, ("· " if k_ == 0 else "") + w_, 7.2, 500)); yy += 10
        yy += 2
        if yy > 596:
            break
    return _sheet("A-403", f"{q['brand']} louvered roof — plan, section, post", "The roof over the deck: frame, zones, blades, posts on the rail line, the house beam on its brackets; heights; the post on the deck edge", o,
                  "Plan and section not to a common scale · dimensions govern · Suncoast's shop drawings and engineering govern the roof", meta)
