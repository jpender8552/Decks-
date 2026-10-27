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
RAIL_POST_INSET_FT = 2.5 * IN   # layout.RAIL_POST_INSET in feet (the post centre in from the frame face)
HEX = {"black": "#141416", "linen": "#e9e3d3", "grey": "#6b6e70", "gray": "#6b6e70", "tan": "#b9a68a", "white": "#ecebe6",
       "mocha": "#5a4636", "bronze": "#4b3b2c"}

DEFAULTS = dict(
    name="Louvered roof", brand="Suncoast", product="Louvered Roof", color="black",
    x0=None, x1=None, y0=None, y1=None,     # ft, plan frame: the outside faces of the perimeter frame (the price's area)
    attach="house",                         # "house" (no posts at the house) | "freestanding" (posts all round); "house_roofline" / "house_wall"
                                            #   / "house_fascia" also set house_mount
    house_mount="roof",                     # "roof": the house-side beam bears on flashed stand-off brackets @ 24" on the existing roof over the
                                            #   wall line, lagged into the rafters (research: the eave over C is too low for a wall ledger) |
                                            #   "wall": wall brackets under the soffit | "fascia": hung at the fascia line (set y0 there)
    clear_ft=8.333,                         # the frame's underside above the deck (8'-4"); z_attach / z_top override it
    z_attach=None,                          # ft above grade: top of the house-side beam (an attached roof's frame top)
    z_top=None,                             # ft above grade: top of the (level) frame
    louver_dir=None,                        # blade long axis "x" (parallel to the house) | "y"; None -> "x" attached, the short side freestanding
    blade_in=8.0, spacing_in=8.0,           # blade width and centre-to-centre spacing
    blade_t_in=1.5, motor_t_in=2.25,        # blade / motor-blade thickness
    pivot_drop_in=3.0,                      # blade pivots this far below the frame top
    angle_deg=45.0,                         # how open to draw them: 0 closed (flat) .. 90 on edge .. 140 (Suncoast max), the +x / +y edge rising
    zones=None,                             # motor zones (one motor blade each); None -> ceil(area / 150 SF)
    posts=None,                             # [[x, y], ...] post centres (ft); None -> flush under the frame's outer corners (both ends of the front
                                            #   beam; all four freestanding)
    post_in=6.0, plate_in=10.0,             # 6x6 aluminum post, square base plate (~10" x 10" x 1/2", Suncoast to specify)
    edge_clear_in=2.0,                      # a post at the deck edge keeps its outer faces this far inside the edge (the plate on the framing);
                                            #   the frame's front pulls in to suit and a post near a deck corner slides to it (snap)
    snap=True,
    beam=None, front_beam=None, frame_beam=None,   # [w_in, h_in]: all beams / the front beam (None -> by its post-to-post span: 2x8 15',
                                            #   2x10 18', 4x8 22') / house, side and divider beams (None -> by their spans, 2x8 to 15')
    gutter=True, lights=True,               # integrated gutter; LED light strip in the gutter's light track
    downspouts="post",                      # "post" (inside the posts, through the deck, a black leader down the post below, piped to the lawn) |
                                            #   "external" (2x3 on the post face) | "none"
    house_clear_ft=None,                    # end screens stop at the house gutter line (y); None -> 1.4' attached by the roof line / fascia
    price=None, price_per_sf=None,          # sell (check / ACH): fixed, or $/SF x the roof area
    priced="own",                           # "own" (its own document; the deck's price does not change) | "option" (also an option on the deck's quote)
    build=None,                             # built into the deck's model (3D, rail posts, takeoff)? None -> unless priced "option" (an option leaves the base deck as is)
    option_name=None,                       # the option's name on the deck's quote (None -> "<brand> louvered roof — W x D")
    screens=None,                           # retractable screens (an option): [{side "front" | "left" | "right", drop 0 (up in the cassette) .. 1
                                            #   (fully down), fabric "mesh" | "vinyl", density, color, bottom, mount, price / price_per_lf}]
    screens_priced=None,                    # None -> as the roof ("own" | "option")
    note="",
)
SCREEN_DEFAULTS = dict(side="front", drop=0.0, fabric="mesh", density=90, color="black",
                       bottom=None,           # ft above grade where the bottom bar lands fully down (None -> the deck under the screen's line)
                       mount="inside",        # "inside": housing under the frame inboard of the posts, fabric inside the rail, the bar on the
                                              #   deck (research F1) | "outside": housing face-mounted on the beam's outer face (the left-end
                                              #   alternate L2: fabric outside the step face, down to the lower deck)
                       from_ft=None, to_ft=None,   # the screen's extent along its side (plan ft; None -> post face to post face / the gutter line)
                       housing_in=None,       # None -> Suncoast 5.5" square (to 22' wide, 11' drop), else the 7" round (to 30' / 22')
                       track_post=None,       # a slim 2x2 track post at the screen's house end: None -> where the end screen stops short of the house
                       fixed_panel=None,      # a fixed screen panel from the house to the gutter line: None -> with the track post
                       price=None, price_per_lf=None, name=None)
# ESTIMATE until the owner / Suncoast Denver prices screens (research.md 5.5: front 19' $6.5-9.5k, right end $4-6k, L2 +$5.5-8.5k)
SCREEN_EST = dict(per_screen=1500.0, per_lf=350.0, track_post=500.0, fixed_panel=400.0, round_housing=1500.0)
SCREEN_EST_PER_LF = SCREEN_EST["per_lf"]
SCREEN_MAT = "lvfabric"
HEM_H, HEM_T, TRACK_W, TRACK_D = 2.0 * IN, 1.25 * IN, 1.25 * IN, 2.0 * IN
FABRIC = {"mesh": dict(rough=0.9), "vinyl": dict(rough=0.12)}   # mesh: Phifer SunTex `density` % (55-99, default 80); vinyl: clear


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


def _pick_frame(q: dict, key: str, span: float) -> Tuple[str, float, float, float]:
    """(label, w_in, h_in, max span) of a beam: the spec's [w, h] (key, else `beam`), else the lightest Suncoast frame for the span."""
    v = q.get(key) or q.get("beam")
    if v:
        w_in, h_in = float(v[0]), float(v[1])
        lim = max([f[3] for f in FRAMES if f[1] <= w_in and f[2] <= h_in] or [FRAMES[0][3]])
        return f"{w_in:g}x{h_in:g}", w_in, h_in, lim
    f = next((f for f in FRAMES if f[3] >= span - 1e-6), FRAMES[-1])
    return f[0], f[1], f[2], f[3]


def resolve(r: dict, surfaces: Optional[List[dict]] = None) -> dict:
    """Everything about one roof, in its frame (ft): the frame rectangle as built (edge clearance, corner snap), the beams,
    motor zones, blades (pivot, length, zone), posts (centre, deck height, which rail lines run through them), heights and
    clearances, the house brackets / stand-offs, the screens."""
    from .layout import RAIL_POST_INSET
    surfaces = surfaces or []
    q = dict(DEFAULTS)
    q.update({k: v for k, v in (r or {}).items() if v is not None})
    x0, x1 = sorted((float(q["x0"]), float(q["x1"])))
    y0, y1 = sorted((float(q["y0"]), float(q["y1"])))
    W_nom, D_nom = x1 - x0, y1 - y0         # the size as sold (the price's area); the built frame can differ by an edge clearance / snap
    notes: List[str] = []
    p = float(q["post_in"]) * IN
    rp = RAIL_POST_INSET * IN
    ec = float(q.get("edge_clear_in") if q.get("edge_clear_in") is not None else 2.0) * IN
    att = str(q["attach"]).lower()
    house = att.startswith("house")
    mount = str(q.get("house_mount") or "roof").lower()
    for k_, m_ in (("roofline", "roof"), ("roof_line", "roof"), ("wall", "wall"), ("fascia", "fascia"), ("soffit", "fascia")):
        if house and att.endswith(k_):
            mount = m_
    under = [s for s in surfaces if min(x1, s["x1"]) - max(x0, s["x0"]) > 0.1 and min(y1, s["y1"]) - max(y0, s["y0"]) > 0.1]
    z_deck = max((s["z"] for s in under), default=0.0)
    zs_ = {round(s_["z"], 3) for s_ in under}          # the deck the roof stands on: under its footprint, and what continues it
    own = [s_ for s_ in surfaces if round(s_["z"], 3) in zs_] if under else []
    explicit = bool(q.get("posts"))
    shift = 0.0

    def front_of(x):                          # the deck front under a front post at x, when the roof's front is near it
        s_ = _surface_at(own, x, y1, tol=0.6)
        return s_ if (s_ is not None and abs(s_["y1"] - y1) <= 1.0) else None

    if explicit:
        posts = [(float(a), float(b)) for a, b in q["posts"]]
    else:
        # posts at the deck edge keep their outer faces `edge_clear` inside it; the frame's front lines up with them
        s_f = front_of((x0 + x1) / 2) or front_of(x0 + p / 2) or front_of(x1 - p / 2)
        if s_f is not None and y1 > s_f["y1"] - ec + 1e-6:
            if y1 - (s_f["y1"] - ec) > 0.6 * IN:
                notes.append(f"the frame's front at y {s_f['y1'] - ec:.3f}: the posts' outer faces {ec * 12:g}\" inside the deck edge (the plates bear on the framing)")
            y1 = s_f["y1"] - ec
        if q.get("snap", True):               # a front post near a deck corner slides to it: outer face `edge_clear` inside the side edge
            def corner_d(px):
                s_ = front_of(px)
                if s_ is None:
                    return None
                ds = [xe + sgn * (ec + p / 2) - px for xe, sgn in _front_corners(surfaces, s_)]
                ds = [d for d in ds if abs(d) <= SNAP_FT]
                return min(ds, key=abs) if ds else None
            dl, dr = corner_d(x0 + p / 2), corner_d(x1 - p / 2)
            if dl is not None and dr is not None and (abs(dl) > 0.01 or abs(dr) > 0.01):
                x0, x1 = x0 + dl, x1 + dr
                notes.append(f"the frame fits between the deck's corners: x {x0:.3f}-{x1:.3f} ({ftin((x1 - x0) * 12)}), both posts are the corner rail posts")
            else:
                d_ = dl if dl is not None else dr
                if d_ is not None and abs(d_) > 0.01:
                    shift = d_
                    x0, x1 = x0 + shift, x1 + shift
                    notes.append(f"frame at x {x0:.3f}-{x1:.3f}: its corner post is the rail's corner post ({ftin(abs(shift) * 12)} "
                                 f"{'left' if shift < 0 else 'right'} of the x {x0 - shift:.3f}-{x1 - shift:.3f} asked for)")
        posts = [(x0 + p / 2, y1 - p / 2), (x1 - p / 2, y1 - p / 2)]
        if not house:
            posts = [(x0 + p / 2, y0 + p / 2), (x1 - p / 2, y0 + p / 2)] + posts
    W, D = x1 - x0, y1 - y0

    # ---- beams: the front by its post-to-post span; the house, side and divider beams by theirs
    ymax = max(pt[1] for pt in posts) if posts else y1
    front = sorted((pt for pt in posts if abs(pt[1] - ymax) < 0.6), key=lambda t: t[0])
    span = max([b[0] - a[0] for a, b in zip(front, front[1:])] + [0.0])
    flabel, fw_in, fh_in, flim = _pick_frame(q, "front_beam", span)
    if not explicit and span > flim + 1e-6 and len(front) == 2:      # posts added under the front beam
        n_b = int(math.ceil(span / flim - 1e-9))
        (ax, ay), (bx, by) = front
        mids = [(ax + (bx - ax) * k / n_b, ay) for k in range(1, n_b)]
        posts = posts + mids
        notes.append(f"{len(mids)} post{'s' if len(mids) > 1 else ''} added under the front beam: {span:.1f}' exceeds the {flabel} frame's {flim:g}' span")
        front = sorted(front + mids, key=lambda t: t[0])
        span = max(b[0] - a[0] for a, b in zip(front, front[1:]))
    blabel, bw_in, bh_in, blim = _pick_frame(q, "frame_beam", D - p / 2)
    if not house:                            # freestanding: the rear beam spans like the front
        blabel, bw_in, bh_in, blim = flabel, fw_in, fh_in, flim
    w_f, h_f, w_b, h_b = fw_in * IN, fh_in * IN, bw_in * IN, bh_in * IN
    hmax = max(h_f, h_b)

    # ---- heights: the frame is level
    if q.get("z_top") is not None:
        z_top = float(q["z_top"])
    elif house and q.get("z_attach") is not None:
        z_top = float(q["z_attach"])
    else:
        z_top = z_deck + float(q.get("clear_ft") or 8.333) + hmax
    z_bot = z_top - hmax                     # the frame's underside (its deepest beam)
    z_piv = z_top - float(q.get("pivot_drop_in") or 3.0) * IN

    # ---- motor zones and blades (blade ends over the gutters, blades stacked between the gutters)
    area = W * D
    ldir = q.get("louver_dir") or ("x" if house else ("y" if D <= W else "x"))
    n_motor = int(q["zones"]) if q.get("zones") else max(1, int(math.ceil(area / MOTOR_SF - 1e-9)))
    if ldir == "y":
        n_y = max(1, int(math.ceil((D - w_b - w_f) / BLADE_SPAN_MAX_FT - 1e-9)))
        n_x = max(1, int(math.ceil(n_motor / n_y)))
    else:
        n_x = max(1, int(math.ceil((W - 2 * w_b) / BLADE_SPAN_MAX_FT - 1e-9)))
        n_y = max(1, int(math.ceil(n_motor / n_x)))
    xs = [x0 + W * k / n_x for k in range(1, n_x)]          # divider beams along y at these x
    ys = [y0 + D * k / n_y for k in range(1, n_y)]          # cross beams along x at these y
    xb = [x0 + w_b] + [v for x_ in xs for v in (x_ - w_b / 2, x_ + w_b / 2)] + [x1 - w_b]
    yb = [y0 + w_b] + [v for y_ in ys for v in (y_ - w_b / 2, y_ + w_b / 2)] + [y1 - w_f]
    cells = [dict(x0=xb[2 * i], x1=xb[2 * i + 1], y0=yb[2 * j], y1=yb[2 * j + 1]) for j in range(n_y) for i in range(n_x)]
    bwid, sp = float(q["blade_in"]) * IN, float(q["spacing_in"]) * IN
    ang = max(ANGLE_RANGE[0], min(ANGLE_RANGE[1], float(q["angle_deg"])))
    blades = []
    for zi, c in enumerate(cells):
        a0, a1 = (c["x0"], c["x1"]) if ldir == "y" else (c["y0"], c["y1"])     # stacking axis
        l0, l1 = (c["y0"], c["y1"]) if ldir == "y" else (c["x0"], c["x1"])     # long axis
        a0, a1 = a0 + GUTTER_W, a1 - GUTTER_W
        n = max(1, int(math.floor((a1 - a0) / sp + 1e-6)))
        off = (a1 - a0 - n * sp) / 2
        c["n_blades"] = n
        c["motor"] = n // 2
        for i in range(n):
            s_ = a0 + off + sp / 2 + i * sp
            ctr = (s_, (l0 + l1) / 2) if ldir == "y" else ((l0 + l1) / 2, s_)
            blades.append(dict(zone=zi, i=i, motor=(i == n // 2), pivot=[ctr[0], ctr[1], z_piv], length=(l1 - l0) - 2 * GUTTER_W))

    # ---- posts as built: the deck under each, and the rail lines that run through it (then it IS the rail post there)
    pts = []
    for (px, py) in posts:
        s_ = _surface_at(own, px, py)
        zd = s_["z"] if s_ else z_deck
        rails = []
        if s_ is not None:
            yr = s_["y1"] - rp
            if abs(py - yr) <= p / 2 + 1e-6:
                rails.append("front")
                for xe, sgn in _front_corners(surfaces, s_):
                    if abs(px - (xe + sgn * rp)) <= p / 2 + 1e-6:
                        rails.append("side")
        pts.append(dict(x=px, y=py, z_deck=zd, on_rail=bool(rails), rails=rails, edge_y=(s_["y1"] if s_ else None), surface=s_["name"] if s_ else ""))
    if not under:
        notes.append("no deck surface under the roof: the posts stand at z = 0")
    clear = z_bot - z_deck
    brackets = [x0 + 0.5 + k * BRACKET_OC_FT for k in range(int((W - 1.0) / BRACKET_OC_FT) + 1)] if house else []
    hc = q.get("house_clear_ft")
    hc = float(hc) if hc is not None else (y0 + 1.4 if (house and mount in ("roof", "fascia")) else y0 + w_b)
    res = dict(src=r, name=q["name"], brand=q["brand"], product=q["product"], color=q["color"], hex=HEX.get(str(q["color"]).lower(), "#141416"),
               x0=x0, x1=x1, y0=y0, y1=y1, W=W, D=D, area=round(area, 2), shift=shift, attach="house" if house else "freestanding",
               house_mount=mount if house else None, W_nom=W_nom, D_nom=D_nom, area_nom=round(W_nom * D_nom, 2),
               beam_label=flabel, frame_label=blabel, w_f=w_f, h_f=h_f, w_b=w_b, h_b=h_b, span_ft=round(span, 2), span_max_ft=flim,
               z_deck=z_deck, z_attach=z_top if house else None, z_top=z_top, z_bot=z_bot, z_pivot=z_piv, clear_ft=clear,
               louver_dir=ldir, blade_w=bwid, blade_t=float(q["blade_t_in"]) * IN, motor_t=float(q["motor_t_in"]) * IN, spacing=sp,
               angle_deg=ang, zones=cells, n_zones=len(cells), xs=xs, ys=ys, blades=blades, posts=pts, post=p, edge_clear=ec,
               plate=float(q["plate_in"]) * IN, gutter=bool(q["gutter"]), lights=bool(q["lights"]), downspouts=str(q.get("downspouts") or "none"),
               brackets=brackets, house_clear=hc, notes=notes, price=q.get("price"), price_per_sf=q.get("price_per_sf"), priced=str(q.get("priced") or "own"),
               option_name=q.get("option_name"), note=q.get("note", ""), global_=bool(r.get("_global")))
    res["screens"] = _screens(res, q.get("screens") or [], surfaces)
    res["screens_priced"] = str(q.get("screens_priced") or res["priced"])
    return res


def _screens(q: dict, screens: List[dict], surfaces: List[dict]) -> List[dict]:
    """Retractable screens as built (research.md 5): per side the housing, the fabric plane and its extent, the top (housing
    underside), the bottom stop, the drop, a slim track post and a fixed panel where an end screen stops at the house gutter.
    "inside" (default): the front screen inboard of the rail between the posts' faces, tracks on the posts' house-side faces,
    the bar on the deck; an end screen under its side beam from the gutter line to the front post. "outside": the housing
    face-mounted on the beam's outer face (the left-end alternate: outside the step face, down to the lower deck)."""
    out = []
    x0, x1, y0, y1, p = q["x0"], q["x1"], q["y0"], q["y1"], q["post"]
    w_f, w_b = q["w_f"], q["w_b"]
    zf_bot, zb_bot = q["z_top"] - q["h_f"], q["z_top"] - q["h_b"]
    front_posts = sorted([pt for pt in q["posts"] if pt["y"] > (y0 + y1) / 2], key=lambda pt: pt["x"])
    y_in = min([pt["y"] - p / 2 for pt in front_posts] or [y1 - w_f])       # the front posts' house-side faces
    hc = q["house_clear"]
    for k, s in enumerate(screens):
        sd = dict(SCREEN_DEFAULTS)
        sd.update({kk: v for kk, v in (s or {}).items() if v is not None})
        side = str(sd["side"]).lower()
        inside = str(sd["mount"]).lower() != "outside"
        hs = float(sd["housing_in"]) * IN if sd.get("housing_in") else 5.5 * IN
        if side == "front":
            plane = "y"
            if inside:
                line = y_in - TRACK_D / 2
                a, b = ((front_posts[0]["x"] + p / 2, front_posts[-1]["x"] - p / 2) if len(front_posts) > 1 else (x0 + w_b, x1 - w_b))
                zh1 = zf_bot
            else:
                line, (a, b), zh1 = y1 + hs / 2, (x0, x1), zf_bot + 2.0 * IN
        elif side in ("left", "right"):
            plane = "x"
            sgn, xe = (1, x0) if side == "left" else (-1, x1)
            if inside:
                line, (a, b), zh1 = xe + sgn * (w_b + hs / 2), (hc, y_in), zb_bot
            else:
                line, (a, b), zh1 = xe - sgn * hs / 2, (hc, y1), zb_bot + 2.0 * IN
        else:
            continue
        if sd.get("from_ft") is not None:
            a = float(sd["from_ft"])
        if sd.get("to_ft") is not None:
            b = float(sd["to_ft"])
        a, b = min(a, b), max(a, b)
        mid = ((a + b) / 2, line) if plane == "y" else (line, (a + b) / 2)
        sf = _surface_at(surfaces, mid[0], mid[1], tol=0.05)
        bottom = float(sd["bottom"]) if sd.get("bottom") is not None else (sf["z"] if sf else q["z_deck"])
        width = b - a
        if not sd.get("housing_in") and (width > 22.0 or (zh1 - hs) - bottom > 11.0):
            hs = 7.0 * IN                     # Suncoast's 7" round housing: to 30' wide and a 22' drop
            if plane == "y":
                line = (y_in - TRACK_D / 2) if inside else (y1 + hs / 2)
            else:
                line = (xe + sgn * (w_b + hs / 2)) if inside else (xe - sgn * hs / 2)
        zh0 = zh1 - hs
        drop = max(0.0, min(1.0, float(sd.get("drop") or 0.0)))
        cass = (a, b, line - hs / 2, line + hs / 2) if plane == "y" else (line - hs / 2, line + hs / 2, a, b)
        tp = sd.get("track_post")
        if tp is None and plane == "x" and a > y0 + w_b + 0.1:           # an end screen short of the house: a slim track post at its end
            tp = [line, a]
        fp = sd.get("fixed_panel")
        if fp is None and tp is not None and plane == "x":
            fp = [y0, a]
        fab = str(sd["fabric"]).lower()
        fab = fab if fab in FABRIC else "mesh"
        price_known = sd.get("price") is not None or sd.get("price_per_lf") is not None
        if sd.get("price") is not None:
            sell, rate = float(sd["price"]), None
        elif sd.get("price_per_lf") is not None:
            sell, rate = float(sd["price_per_lf"]) * width, float(sd["price_per_lf"])
        else:
            rate = SCREEN_EST["per_lf"]
            sell = (SCREEN_EST["per_screen"] + rate * width + (SCREEN_EST["track_post"] if tp else 0.0) + (SCREEN_EST["fixed_panel"] if fp else 0.0)
                    + (SCREEN_EST["round_housing"] if hs > 6.0 * IN else 0.0))
        out.append(dict(index=k, side=side, mount="inside" if inside else "outside", plane=plane, line=line,
                        a=([a, line] if plane == "y" else [line, a]), b=([b, line] if plane == "y" else [line, b]), width=width,
                        z_top=zh0, z_bottom=bottom, max_drop=zh0 - bottom, drop=drop,
                        cassette=dict(x0=cass[0], x1=cass[1], y0=cass[2], y1=cass[3], z0=zh0, z1=zh1), housing=hs,
                        track_post=(list(tp) if tp else None), track_post_top=(zb_bot if plane == "x" else zf_bot),
                        fixed_panel=(list(fp) if fp else None), fixed_top=q["z_deck"] + max(6.5, q["clear_ft"] - 1.0),
                        fabric=fab, density=float(sd.get("density") or 90), color=str(sd["color"]),
                        name=sd.get("name") or f"{side} screen", sell=round(sell, 2), estimate=not price_known, rate=rate))
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
        # openness: the open weave the photoreal pass lets sight and sun through (cycles Mats.screen); opacity: the WebGL viewer's
        dens = float(scr[0].get("density") or 80.0)
        openness = 0.85 if fab == "vinyl" else max(0.01, min(0.45, 1.0 - dens / 100.0))
        opacity = 0.28 if fab == "vinyl" else round(0.45 + 0.4 * (min(99.0, max(55.0, dens)) - 55.0) / 45.0, 3)
        out[SCREEN_MAT] = dict(color=hexc, rough=FABRIC[fab]["rough"], opacity=opacity, openness=round(openness, 3),
                               label=("Suncoast retractable screen, clear vinyl" if fab == "vinyl" else f"Suncoast retractable screen, Phifer SunTex {dens:g} {sc} mesh"))
    return out


def draw_roof(add, q: dict) -> None:
    """The boxes of one resolved roof (layer "louvered", phase 8). add(kind, x0, x1, y0, y1, z0, z1, mat, phase, **kw)."""
    def A(kind, x0, x1, y0, y1, z0, z1, mat=MAT, tag="", **k):
        add(kind, x0, x1, y0, y1, z0, z1, mat, PHASE, tag=f"{q['name']}: {tag}" if tag else q["name"], layer=LAYER, **k)
    x0, x1, y0, y1 = q["x0"], q["x1"], q["y0"], q["y1"]
    wf, hf, wb, hb = q["w_f"], q["h_f"], q["w_b"], q["h_b"]
    zt = q["z_top"]
    zbf, zbb = zt - hf, zt - hb
    fl, bl = q["beam_label"], q["frame_label"]
    house = q["attach"] == "house"
    mount = q.get("house_mount") or "roof"
    # the beams: the house-side and front beams run the full length; the sides and dividers fit between them
    A("lvbeam", x0, x1, y0, y0 + wb, zbb, zt, tag=((f"house-side {bl} beam on flashed stand-off brackets on the existing roof (roof-line mount)" if mount == "roof" else
                                                    f"house-side {bl} beam on wall brackets under the soffit" if mount == "wall" else f"house-side {bl} beam hung at the fascia line")
                                                   if house else f"rear {bl} beam"))
    A("lvbeam", x0, x1, y1 - wf, y1, zbf, zt, tag=f"front {fl} beam, integrated gutter, on {len([p_ for p_ in q['posts'] if p_['y'] > (y0 + y1) / 2])} posts")
    A("lvbeam", x0, x0 + wb, y0 + wb, y1 - wf, zbb, zt, tag=f"side {bl} beam, integrated gutter")
    A("lvbeam", x1 - wb, x1, y0 + wb, y1 - wf, zbb, zt, tag=f"side {bl} beam, integrated gutter")
    for xd in q["xs"]:
        A("lvbeam", xd - wb / 2, xd + wb / 2, y0 + wb, y1 - wf, zbb, zt, tag=f"zone divider {bl} beam (carries the blade ends), gutters both sides")
    for yd in q["ys"]:
        A("lvbeam", x0 + wb, x1 - wb, yd - wb / 2, yd + wb / 2, zbb, zt, tag=f"cross {bl} beam, gutters both sides")
    # the gutter round every zone, on the beams' inner faces at their bottom; the LED strip in its light track
    gz0, gz1 = zbb, zbb + GUTTER_H
    for c in q["zones"]:
        cx0, cx1, cy0, cy1 = c["x0"], c["x1"], c["y0"], c["y1"]
        if q["gutter"]:
            A("lvgutter", cx0, cx1, cy0, cy0 + GUTTER_W, gz0, gz1, tag="integrated gutter")
            A("lvgutter", cx0, cx1, cy1 - GUTTER_W, cy1, gz0, gz1, tag="integrated gutter")
            A("lvgutter", cx0, cx0 + GUTTER_W, cy0 + GUTTER_W, cy1 - GUTTER_W, gz0, gz1, tag="integrated gutter")
            A("lvgutter", cx1 - GUTTER_W, cx1, cy0 + GUTTER_W, cy1 - GUTTER_W, gz0, gz1, tag="integrated gutter")
        if q["lights"]:
            e, t_ = GUTTER_W + 0.01, 0.04
            for (a0, a1, b0, b1) in ((cx0 + e, cx1 - e, cy0 + e - t_, cy0 + e), (cx0 + e, cx1 - e, cy1 - e, cy1 - e + t_),
                                     (cx0 + e - t_, cx0 + e, cy0 + e, cy1 - e), (cx1 - e, cx1 - e + t_, cy0 + e, cy1 - e)):
                A("lvled", a0, a1, b0, b1, gz0 - 0.02, gz0 + 0.02, mat=LED_MAT, tag="LED light strip")
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
        top = zbf if py > (y0 + y1) / 2 else zbb
        rail = " — the rail post here (the rail panels end into it on wall-mount brackets)" if pt["on_rail"] else ""
        A("lvplate", px - pl / 2, px + pl / 2, py - pl / 2, py + pl / 2, zd, zd + 0.04, tag="base plate, through-bolted into solid blocking over the post below")
        A("lvpost", px - p / 2 - 0.02, px + p / 2 + 0.02, py - p / 2 - 0.02, py + p / 2 + 0.02, zd + 0.04, zd + 0.36, tag="post base cover")
        A("lvpost", px - p / 2, px + p / 2, py - p / 2, py + p / 2, zd + 0.04, top, tag=f"{q['post'] * 12:g}x{q['post'] * 12:g} aluminum post{rail}")
        out_y = 1 if py > (y0 + y1) / 2 else -1
        if q["downspouts"] == "post" and zd > 2.0:
            # inside the post, through a sleeve in the plate, decking and blocking; a black leader down the deck post below to the
            # patio level, then solid pipe out past the deck edge to the lawn (>= 5' from the foundation)
            lx = px + 0.45
            A("lvdown", lx - 0.11, lx + 0.11, py - 0.11, py + 0.11, 0.2, zd - 0.95, tag="downspout leader from inside the post, down the deck post below")
            ye = (pt.get("edge_y") or py) + 2.0
            A("lvdown", lx - 0.11, lx + 0.11, min(py, ye), max(py, ye), 0.0, 0.2, tag="downspout piped out to the lawn")
        elif q["downspouts"] == "external":
            yo = py + out_y * p / 2
            ya, yb_ = sorted((yo, yo + out_y * 0.21))
            A("lvdown", px - 0.12, px + 0.12, ya, yb_, zd + 0.35, top + 0.15, tag="2x3 downspout on the post")
            A("lvdown", px - 0.12, px + 0.12, min(yb_, yb_ + out_y * 0.35), max(yb_, yb_ + out_y * 0.35) if out_y > 0 else ya, zd + 0.12, zd + 0.35, tag="downspout kick-out")
    # the house side: stand-offs on the roof (roof-line mount) or brackets on the wall / fascia
    for bx in q["brackets"]:
        if mount == "roof":
            A("lvbracket", bx - 0.09, bx + 0.09, y0 + wb / 2 - 0.09, y0 + wb / 2 + 0.09, zbb - 0.42, zbb, tag="stand-off bracket, lagged into a rafter over solid blocking")
            A("lvbracket", bx - 0.22, bx + 0.22, y0 + wb / 2 - 0.22, y0 + wb / 2 + 0.22, zbb - 0.45, zbb - 0.42, tag="stand-off flashing boot")
        else:
            A("lvbracket", bx - 0.125, bx + 0.125, y0, y0 + 0.03, zbb - 0.45, zbb, tag="wall bracket (into the wall framing)")
            A("lvbracket", bx - 0.125, bx + 0.125, y0, y0 + wb - 0.02, zbb - 0.03, zbb, tag="wall bracket seat")
    for sc in q.get("screens") or []:
        draw_screen(A, sc)


def draw_screen(A, sc: dict) -> None:
    """One retractable screen (the screens option): the housing, a track at each end, the fabric down to the drop and the
    bottom bar; a slim track post and a fixed panel where an end screen stops at the house gutter. Fabric and bar are kind
    "lvscreen" (a live viewer hides them and draws its own); the fixed panel is "lvfixed", the tracks "lvtrack"."""
    nm = f"screen ({sc['side']}) — screens option"
    c = sc["cassette"]
    A("lvcassette", c["x0"], c["x1"], c["y0"], c["y1"], c["z0"], c["z1"], tag=f"{nm}: {sc['housing'] * 12:g}\" housing, motor inside")
    zt, zb = sc["z_top"], sc["z_bottom"]
    zh = zt - HEM_H - sc["drop"] * (sc["max_drop"] - HEM_H)          # the bottom bar's underside
    ln = sc["line"]
    if sc["plane"] == "y":
        a, b = sc["a"][0], sc["b"][0]
        for e, sg in ((a, 1), (b, -1)):
            A("lvtrack", min(e, e + sg * TRACK_W), max(e, e + sg * TRACK_W), ln - TRACK_D / 2, ln + TRACK_D / 2, zb, zt, tag=f"{nm}: zipper track")
        a_, b_ = a + TRACK_W, b - TRACK_W
        if zt - (zh + HEM_H) > 0.01:
            A("lvscreen", a_, b_, ln - 0.01, ln + 0.01, zh + HEM_H, zt, mat=SCREEN_MAT, tag=f"{nm}: {sc['fabric']} fabric")
        A("lvscreen", a_, b_, ln - HEM_T / 2, ln + HEM_T / 2, zh, zh + HEM_H, tag=f"{nm}: bottom bar")
    else:
        a, b = sc["a"][1], sc["b"][1]
        for e, sg in ((a, 1), (b, -1)):
            A("lvtrack", ln - TRACK_D / 2, ln + TRACK_D / 2, min(e, e + sg * TRACK_W), max(e, e + sg * TRACK_W), zb, zt, tag=f"{nm}: zipper track")
        a_, b_ = a + TRACK_W, b - TRACK_W
        if zt - (zh + HEM_H) > 0.01:
            A("lvscreen", ln - 0.01, ln + 0.01, a_, b_, zh + HEM_H, zt, mat=SCREEN_MAT, tag=f"{nm}: {sc['fabric']} fabric")
        A("lvscreen", ln - HEM_T / 2, ln + HEM_T / 2, a_, b_, zh, zh + HEM_H, tag=f"{nm}: bottom bar")
    if sc.get("track_post"):
        tx, ty = sc["track_post"]
        A("lvtrack", tx - 1.0 * IN, tx + 1.0 * IN, ty - 1.0 * IN, ty + 1.0 * IN, zb, sc["track_post_top"], tag=f"{nm}: 2x2 track post at the gutter line")
    if sc.get("fixed_panel"):
        fa, fb = sorted(sc["fixed_panel"])
        if sc["plane"] == "x":
            A("lvfixed", ln - 0.01, ln + 0.01, fa, fb - 1.0 * IN, zb, sc["fixed_top"], mat=SCREEN_MAT, tag=f"{nm}: fixed screen panel under the eave")
        else:
            A("lvfixed", fa, fb, ln - 0.01, ln + 0.01, zb, sc["fixed_top"], mat=SCREEN_MAT, tag=f"{nm}: fixed screen panel")


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
            frame=dict(x0=q["x0"], x1=q["x1"], y0=q["y0"], y1=q["y1"], z_top=q["z_top"], z_bottom=q["z_bot"],
                       front_beam=q["beam_label"], front_w=q["w_f"], front_h=q["h_f"], frame_beam=q["frame_label"], frame_w=q["w_b"], frame_h=q["h_b"],
                       attach=q["attach"], house_mount=q["house_mount"], z_attach=q["z_attach"], dividers_x=q["xs"], dividers_y=q["ys"]),
            zones=[dict(x0=c["x0"], x1=c["x1"], y0=c["y0"], y1=c["y1"], blades=c["n_blades"], motor_blade=c["motor"]) for c in q["zones"]],
            posts=[dict(x=pt["x"], y=pt["y"], z0=pt["z_deck"], z1=q["z_bot"], size=q["post"], rail_post=pt["on_rail"]) for pt in q["posts"]],
            z_deck=q["z_deck"], clear_ft=q["clear_ft"],
            screens=[dict(side=sc["side"], a=sc["a"], b=sc["b"], plane=sc["plane"], line=sc["line"], z_top=sc["z_top"], z_bottom=sc["z_bottom"],
                          max_drop=sc["max_drop"], down_default=sc["drop"], thick=0.02, hem=dict(h=HEM_H, t=HEM_T, mat=MAT), track_w=TRACK_W,
                          mat=SCREEN_MAT, box_kind="lvscreen", fabric=sc["fabric"], color=sc["color"], mount=sc["mount"],
                          cassette=sc["cassette"], track_post=sc["track_post"], fixed_panel=sc["fixed_panel"], fixed_kind="lvfixed",
                          tag=f"{q['name']}: screen ({sc['side']}) — screens option")
                     for sc in q["screens"]]))
    return out


# ================================================================== rail integration
def rail_points(spec, zones) -> List[Tuple[float, float, float]]:
    """layout.build_layout: (x, y, post size) in inches, the layout's frame, of the roof posts that stand on a deck-edge rail
    line — rail_layout_edges makes each a fixed rail post (one near a run's end takes that end)."""
    return _rail_points(spec, zone_surfaces(zones, spec.geometry.height_in))


def rail_points_rect(spec, W: float, D: float) -> List[Tuple[float, float, float]]:
    """rail_points for a one-rectangle deck (W x D inches from the left frame face and the house)."""
    return _rail_points(spec, [dict(name="A", x0=0.0, x1=W / 12.0, y0=0.0, y1=D / 12.0, z=spec.geometry.height_in / 12.0)])


def _rail_points(spec, surf: List[dict]) -> List[Tuple[float, float, float]]:
    roofs = [r for r in (getattr(spec.geometry, "louvered_roofs", None) or []) if built(r)]
    if not roofs:
        return []
    out = []
    for r in roofs:
        q = resolve(r, surf)
        out += [(pt["x"] * 12.0, pt["y"] * 12.0, q["post"] * 12.0) for pt in q["posts"] if pt["on_rail"]]
    return out


IRX_WALL_KIT = dict(each=35.0, sku="AZTIXWBKTKITB", source="EST — not on a D&D quote yet (materials.md: AZTIXWBKTKITB ~$35)",
                    desc="TimberTech Impression Rail Express Wall Mount Kit AZTIXWBKTKITB, {color} — a rail panel end into a Suncoast roof post")


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
    n = len(roof)                                   # rail post positions taken by roof posts (a corner roof post ends two runs)
    n_roof = len({(p.roof if isinstance(p.roof, tuple) else (round(p.x / 12, 1), round(p.y / 12, 1))) for p in roof})
    words = (f"{n} {'is a' if n == 1 else 'are'} louvered-roof post{'s' if n != 1 else ''}" if n == n_roof else
             f"{n} rail post positions are the {n_roof} louvered-roof posts")
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
                ln.why = f"{need} needed  ({n_rp} rail posts x 4; the {n_roof} roof post{'s' if n_roof != 1 else ''} bolt down through their own base plates)"
    t.lines[:] = [ln for ln in t.lines if not (ln.order == 0 and ln.net == 0 and ln.category in ("Rail", "Hardware") and ("post" in ln.item.lower() or "HeadLOK" in ln.item))]
    ends = 0
    rxy = [(p.x, p.y) for p in roof]
    for s_ in rl.sections:
        for e in (s_.p0, s_.p1):
            if e is not None and any(abs(e[0] - a) < 0.6 and abs(e[1] - b) < 0.6 for a, b in rxy):
                ends += 1
    ends = ends or 2 * n_roof
    color = rl.color or "black"
    t.lines.append(Line("Rail", IRX_WALL_KIT["desc"].replace("{color}", color), ends, ends, "kit",
                        f"exact  ({ends} panel end{'s' if ends != 1 else ''} on the {n_roof} roof post{'s' if n_roof != 1 else ''})", IRX_WALL_KIT["each"], IRX_WALL_KIT["source"],
                        IRX_WALL_KIT["sku"]))
    ids = sorted({(p.roof if isinstance(p.roof, tuple) else (p.x, p.y)) for p in roof})
    xs = ", ".join(ftin(i_[0]) for i_ in ids)
    if "Rail" in t.schedule:
        t.schedule["Rail"] += (f"; {words} at {xs} from the left end of this level: the 6x6 aluminum post is base-plated on the deck over solid "
                               f"blocking / the column below and the rail panels hang on wall-mount brackets screwed into it")
    t.notes.append(f"louvered roof: {words} at {xs} — no rail post kit there; {ends} wall-mount bracket kits")
    # a rail post left standing next to a roof post: its surface base must clear the roof post's base plate
    try:
        surf = zone_surfaces(t.layout.zones, t.spec.geometry.height_in)
        for r in [r_ for r_ in (t.spec.geometry.louvered_roofs or []) if built(r_)]:
            q = resolve(r, surf)
            half = q["plate"] * 12 / 2
            for pt in q["posts"]:
                cx, cy = pt["x"] * 12, pt["y"] * 12
                for rp_ in rl.posts:
                    if getattr(rp_, "roof", False):
                        continue
                    hb = rail_base_in(rl.system) / 2
                    ox = (half + hb) - abs(rp_.x - cx)
                    oy = (half + hb) - abs(rp_.y - cy)
                    if ox > 0 and oy > 0:
                        t.notes.append(f"louvered roof: the rail post at {ftin(rp_.x)}, {ftin(rp_.y)} ({rp_.kind}) sits {ftin(min(ox, oy))} into the roof post's "
                                       f"{q['plate'] * 12:g}\" base plate at {ftin(cx)}, {ftin(cy)} — trim / notch the plate or move the post")
    except Exception:            # a check, never a failure
        pass


def rail_base_in(system: str) -> float:
    """The footprint of a surface-mount rail post's base (in): IRX's 3" post on its ~5" base; 2" posts ~4"."""
    return 5.0 if "IRX" in (system or "") or "Impression" in (system or "") else 4.0


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
    W_, D_ = ftin(q["W_nom"] * 12), ftin(q["D_nom"] * 12)
    out = [f"{q['brand']} {q['product']}, motorized, {W_} x {D_} ({q['area_nom']:g} SF), {str(q['color']).lower()} powder-coated aluminum",
           f"{n_bl} louver blades, {q['blade_w'] * 12:g}\" wide on {q['spacing'] * 12:g}\" centres, in {nz} motor zone{'s' if nz != 1 else ''} "
           f"(one Gaposa motor blade each); the blades turn from closed to {ANGLE_RANGE[1]:g} degrees open by remote or app",
           f"Aluminum frame with the integrated gutter round every zone: {q['beam_label']} front beam, {q['frame_label']} house, side" + (" and divider" if q["xs"] or q["ys"] else "") + " beams"
           + (f"; {len(q['xs']) + len(q['ys'])} zone divider beam{'s' if len(q['xs']) + len(q['ys']) != 1 else ''}" if (q['xs'] or q['ys']) else ""),
           ((f"House side: the beam bears on flashed stand-off brackets on the existing roof over the wall line, lagged into the rafters — no posts at the house"
             if q["house_mount"] == "roof" else "House side: the beam hangs on brackets on the house wall under the soffit — no posts at the house"
             if q["house_mount"] == "wall" else "House side: the beam hangs at the fascia line — no posts at the house")
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
        rows.append(dict(name=q["name"], brand=q["brand"], product=q["product"], color=q["color"], width_ft=q["W_nom"], depth_ft=q["D_nom"],
                         area_sf=round(roof_area_sf(r), 2), built=dict(width_ft=round(q["W"], 4), depth_ft=round(q["D"], 4), area_sf=q["area"]),
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
    return q.get("option_name") or f"{q['brand']} louvered roof — {ftin(q['W_nom'] * 12)} x {ftin(q['D_nom'] * 12)}, motorized, {str(q['color']).lower()}"


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
                                   f"{q['area_nom']:g} SF" + (f" at ${float(r['price_per_sf']):,.0f}/SF" if r.get("price_per_sf") is not None and r.get("price") is None else "")
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
    brackets), section A through the house wall, the roof and the deck (heights, clearance, the attachment), and detail 1:
    the post on the deck edge (base plate over solid blocking / the column below, the rail brackets into the post). None
    when the job has no roof built. S is the full scene (the roof boxes included)."""
    from .drawings import (T, TH, R, LN, C, PG, sheet as _sheet, plan_xform, elev_xform, dim_h, dim_v, INK, GOLD, MUTE, FILL,
                           _panel, _lead)
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
    x0, x1, y0, y1, p = q["x0"], q["x1"], q["y0"], q["y1"], q["post"]
    w, wf, hf, wb, hb = q["w_b"], q["w_f"], q["h_f"], q["w_b"], q["h_b"]
    h = max(hf, hb)
    zd, zt, zb = q["z_deck"], q["z_top"], q["z_bot"]
    mount = q.get("house_mount") or "roof"
    BLACK, HOUSE, DECK = "#1d1d1f", FILL["house"], FILL["deck"]
    rp = RAIL_POST_INSET * IN
    front_posts = sorted([pt for pt in q["posts"] if pt["y"] > (y0 + y1) / 2], key=lambda pt: pt["x"])
    jd = actual(spec.framing.joist_size)[1] * IN if spec.framing.joist_size else 9.25 * IN
    fp0 = front_posts[0] if front_posts else None
    ins = (fp0["edge_y"] - (fp0["y"] + p / 2)) if (fp0 and fp0.get("edge_y") is not None) else q["edge_clear"]   # the post's outer face inside the frame face
    ins_txt = f"{ins * 12:.2g}\"" if abs(ins * 12 - round(ins * 12)) > 0.05 else f"{round(ins * 12):g}\""

    # ---------------------------------------------------------------- plan
    _panel(o, 14, 4, 560, 336, "PLAN", f"{q['brand'].upper()} LOUVERED ROOF OVER THE DECK")
    px0, px1, py0, py1 = x0 - 2.5, x1 + 2.5, y0 - 2.2, y1 + 4.2
    X, Y, sc = plan_xform(px0, px1, py0, py1, 30, 26, 528, 300)
    o.append(R(X(px0), Y(py0), (px1 - px0) * sc, (y0 - py0) * sc, HOUSE, INK, 0.8))
    o.append(T(X(px0) + 6, Y(py0) + 11, "HOUSE WALL", 7.2, 900, fill=MUTE))
    for s_ in surf:                      # the deck under and around the roof, clipped to the panel
        a0, a1, b0, b1 = max(s_["x0"], px0), min(s_["x1"], px1), max(s_["y0"], y0), min(s_["y1"], py1)
        if a1 - a0 > 0.05 and b1 - b0 > 0.05:
            o.append(R(X(a0), Y(b0), (a1 - a0) * sc, (b1 - b0) * sc, DECK, INK, 0.8, 'fill-opacity="0.5"'))
    for s_ in surf:
        a0, a1 = max(s_["x0"], px0), min(s_["x1"], px1)
        if a1 - a0 > 4.0 and s_["y1"] < py1:
            o.append(T(X((a0 + a1) / 2), Y(s_["y1"]) + 22, f"{s_['name'].upper()} · DECK {ftin(s_['z'] * 12)}", 6.4, 800, "middle", MUTE))
    for b in [b for b in S.boxes if getattr(b, "layer", "") == LAYER and b.kind == "lvbeam"]:
        o.append(R(X(b.x0), Y(b.y0), (b.x1 - b.x0) * sc, (b.y1 - b.y0) * sc, BLACK, BLACK, 0.4))
    for bl in q["blades"]:
        px_, py_, _ = bl["pivot"]
        L_ = bl["length"] / 2
        a_, b_ = ((X(px_), Y(py_ - L_)), (X(px_), Y(py_ + L_))) if q["louver_dir"] == "y" else ((X(px_ - L_), Y(py_)), (X(px_ + L_), Y(py_)))
        o.append(LN(*a_, *b_, "#3c3c40", 2.6 if bl["motor"] else 0.8))
    # the rail line on the deck edge (under the front beam): IRX posts hollow, the roof posts solid on their plates
    rails = [b for b in S.boxes if b.kind == "railpost" and px0 <= (b.x0 + b.x1) / 2 <= px1 and y0 <= (b.y0 + b.y1) / 2 <= py1]
    for yr in sorted({round(pt["y"], 2) for pt in front_posts if pt["on_rail"]}):
        xs_r = [(b.x0 + b.x1) / 2 for b in rails if abs((b.y0 + b.y1) / 2 - yr) < 0.1] + [pt["x"] for pt in front_posts]
        o.append(LN(X(max(px0, min(xs_r) - 0.0)), Y(yr), X(min(px1, max(xs_r + [px1]))), Y(yr), GOLD, 1.3, "5 3"))
    for b in rails:
        cx_, cy_ = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
        o.append(R(X(cx_) - 3, Y(cy_) - 3, 6, 6, "#fff", INK, 0.9))
    for pt in q["posts"]:
        pl_ = q["plate"]
        o.append(R(X(pt["x"] - pl_ / 2), Y(pt["y"] - pl_ / 2), pl_ * sc, pl_ * sc, "#fff", INK, 0.8))
        o.append(R(X(pt["x"] - p / 2), Y(pt["y"] - p / 2), p * sc, p * sc, BLACK, INK, 0.5))
    for sc in q["screens"]:                # the screens option: the fabric line and its cassette, dashed
        (ax_, ay_), (bx_, by_) = sc["a"], sc["b"]
        o.append(LN(X(ax_), Y(ay_), X(bx_), Y(by_), "#5b6e8c", 2.0, "2 2"))
        side_ = sc["plane"] == "x"
        right_ = side_ and ax_ > (x0 + x1) / 2
        o.append(TH((X((ax_ + bx_) / 2) + (-4 if right_ else 4)) if side_ else X(ax_ + (bx_ - ax_) * 0.78), (Y(ay_ + (by_ - ay_) * 0.22) if side_ else Y(ay_) - 4),
                    f"{sc['side']} screen (option)", 6.0, 800, ("end" if right_ else "start") if side_ else "middle", "#3d4f6b", halo="#fff"))
    for zi, c in enumerate(q["zones"]):
        cx_, cy_ = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        o.append(TH(X(cx_), Y(cy_) - 4, f"ZONE {zi + 1}", 8.4, 900, "middle", halo="#fff"))
        o.append(TH(X(cx_), Y(cy_) + 8, f"{c['n_blades']} blades · 1 motor blade (heavy line)", 6.6, 700, "middle", halo="#fff"))
    o.append(TH(X(x0) + 8, Y(y0 + w) + 11, ((f"house-side {q['frame_label']} beam on stand-offs on the roof @ {BRACKET_OC_FT * 12:g}\" OC (roof-line mount) — no posts at the house"
                                              if mount == "roof" else f"house-side {q['frame_label']} beam on wall brackets @ {BRACKET_OC_FT * 12:g}\" OC — no posts at the house")
                                             if q["attach"] == "house" else f"rear {q['frame_label']} beam"), 6.6, 700, halo="#fff"))
    o.append(TH(X(x0) + 8, Y(y1 - wf) - 6, f"front {q['beam_label']} beam · {q['frame_label']} sides" + (" + divider" if q["xs"] else "") + " · gutter + LED all round", 6.6, 700, halo="#fff"))
    # dimensions: zones in the house band, the frame and post spans below, the depth at the right
    if len(q["zones"]) > 1 and q["louver_dir"] == "y":
        edges_ = [x0] + list(q["xs"]) + [x1]
        for zi, (a_, b_) in enumerate(zip(edges_, edges_[1:])):
            dim_h(o, X, Y(y0) - 8, a_, b_, f"zone {zi + 1}: {ftin((b_ - a_) * 12)}", 6.8)
    if len(front_posts) > 1:
        for a_, b_ in zip(front_posts, front_posts[1:]):
            dim_h(o, X, Y(py1) - 26, a_["x"], b_["x"], f"{ftin((b_['x'] - a_['x']) * 12)} post to post", 7.2)
    dim_h(o, X, Y(py1) - 8, x0, x1, f"{ftin(q['W'] * 12)} frame · {q['area_nom']:g} SF", 8)
    dim_v(o, Y, X(x1) + 18, y0, y1, ftin(q["D"] * 12), 8, left=False)
    if front_posts:
        fp = front_posts[0]
        cxp, cyp = X(fp["x"]) + 16, Y(fp["y"]) + 13
        o.append(C(cxp, cyp, 6.5, "#fff", INK, 0.8)); o.append(T(cxp, cyp + 3, "1", 7.2, 900, "middle"))
    rail_n = sum(1 for pt in q["posts"] if pt["on_rail"])
    if rail_n:
        o.append(T(X((x0 + x1) / 2), Y(y1) + 11, f"rail line (gold): the {rail_n} roof post{'s are' if rail_n != 1 else ' is'} the rail post{'s' if rail_n != 1 else ''} there — rail posts hollow", 6.5, 700, "middle"))
    # the section cut A (through zone 1, across the house wall)
    z0_ = q["zones"][0]
    xa = (z0_["x0"] + z0_["x1"]) / 2 + (q["spacing"] / 2 if q["louver_dir"] == "y" else 0.0)
    o.append(LN(X(xa), Y(py0) + 5, X(xa), Y(y1) + 2, GOLD, 1.0, "6 3"))
    for yy_ in (Y(py0) + 5,):
        o.append(C(X(xa), yy_, 6.5, GOLD, INK, 0.6)); o.append(T(X(xa), yy_ + 3, "A", 7, 900, "middle", "#fff"))

    # ---------------------------------------------------------------- section A
    _panel(o, 584, 4, 402, 336, "A", "SECTION — HOUSE WALL, ROOF, DECK")
    sy0, sy1 = y0 - 2.4, y1 + 4.6
    z_lo, z_hi = zd - 3.2, zt + 3.4
    Xs, Zs, scs = elev_xform(sy0, sy1, z_lo, z_hi, 596, 26, 330, 304)
    z_sof = zd + max(6.67, q["clear_ft"] - 1.08)          # the existing soffit (research: about 7'-3" above the deck; field verify)
    pitch = 4.0 / 12
    eave_y = y0 + 1.5
    z_eave = z_sof + 0.35
    def roof_z(yy):
        return z_eave + (eave_y - yy) * pitch
    o.append(R(Xs(sy0), Zs(z_sof), (y0 - sy0) * scs, (z_sof - z_lo) * scs, HOUSE, INK, 0.9))
    o.append(T(Xs((sy0 + y0) / 2) + 3, Zs((zd + z_sof) / 2), "HOUSE", 8, 900, "middle", MUTE, rot=-90))
    o.append(PG([(Xs(sy0), Zs(roof_z(sy0))), (Xs(eave_y), Zs(z_eave)), (Xs(eave_y), Zs(z_sof)), (Xs(sy0), Zs(z_sof))], "#cfc6b4", INK, 0.7))
    o.append(R(Xs(eave_y), Zs(z_eave + 0.05), 0.42 * scs, 0.45 * scs, "#9a948b", INK, 0.5))       # the existing gutter
    yf = max((s_["y1"] for s_ in surf if abs(s_["z"] - zd) < 0.01 and s_["x0"] - 0.1 <= (x0 + x1) / 2 <= s_["x1"] + 0.1), default=y1 + q["edge_clear"])
    o.append(R(Xs(y0), Zs(zd), (yf - y0 + 0.08) * scs, 0.1 * scs, DECK, INK, 0.7))
    o.append(R(Xs(y0), Zs(zd - 0.1), (yf - y0) * scs, jd * scs, FILL["timber"], INK, 0.6))
    py = front_posts[0]["y"] if front_posts else y1 - p / 2
    o.append(R(Xs(py - 0.33), Zs(zd - 0.1 - jd), 0.67 * scs, (zd - 0.1 - jd - z_lo) * scs, FILL["timber"], INK, 0.6, 'stroke-dasharray="4 2" fill-opacity="0.5"'))
    o.append(R(Xs(y0), Zs(zt), wb * scs, hb * scs, BLACK, INK, 0.5))
    o.append(R(Xs(y1 - wf), Zs(zt), wf * scs, hf * scs, BLACK, INK, 0.5))
    zbb = zt - hb
    if q["attach"] == "house" and mount == "roof":           # stand-off brackets from the house roof up to the house beam
        ys_ = y0 + wb / 2
        o.append(R(Xs(ys_ - 0.08), Zs(zbb), 0.16 * scs, max(1.0, (zbb - roof_z(ys_)) * scs), BLACK, INK, 0.4))
        o.append(LN(Xs(ys_ - 0.25), Zs(roof_z(ys_ - 0.25)), Xs(ys_ + 0.25), Zs(roof_z(ys_ + 0.25)), INK, 2.2))
    elif q["attach"] == "house":
        o.append(R(Xs(y0), Zs(zbb), 0.05 * scs + 1, 0.42 * scs, BLACK, INK, 0.3))
        o.append(R(Xs(y0), Zs(zbb), (wb - 0.02) * scs, 0.04 * scs + 1, BLACK, INK, 0.3))
    o.append(R(Xs(py - p / 2), Zs(zt - hf), p * scs, (zt - hf - zd) * scs, BLACK, INK, 0.5))
    o.append(R(Xs(py - q["plate"] / 2), Zs(zd + 0.05), q["plate"] * scs, 0.05 * scs + 1, "#555", INK, 0.4))
    ang = math.radians(q["angle_deg"])
    if q["louver_dir"] == "y":            # the blades run along the cut: the next blade seen lengthwise
        ext = abs(q["blade_w"] / 2 * math.sin(ang)) + q["blade_t"] / 2
        o.append(R(Xs(y0 + wb + 0.05), Zs(q["z_pivot"] + ext), (q["D"] - wb - wf - 0.1) * scs, 2 * ext * scs, "#77777c", INK, 0.4))
    else:                                  # the blades cut across, each at its angle
        for bl in [b for b in q["blades"] if b["zone"] == 0]:
            cy_, cz_ = bl["pivot"][1], bl["pivot"][2]
            pts_ = [(cy_ + u * math.cos(ang) - v * math.sin(ang), cz_ + u * math.sin(ang) + v * math.cos(ang)) for u, v in blade_profile(q["blade_w"], q["blade_t"])]
            o.append(PG([(Xs(a_), Zs(b_)) for a_, b_ in pts_], "#3c3c40", INK, 0.3))
    rh = float(spec.railing.height_in or 36.0) * IN          # the rail, cut at A: top rail, bottom rail, a baluster, the drink rail on top
    yr = yf - rp
    o.append(R(Xs(yr - 0.11), Zs(zd + rh), 0.22 * scs, 0.13 * scs, "#8a8a90", INK, 0.4))
    o.append(R(Xs(yr - 0.06), Zs(zd + 0.38), 0.12 * scs, 0.09 * scs, "#8a8a90", INK, 0.4))
    o.append(R(Xs(yr - 0.03), Zs(zd + rh - 0.13), 0.06 * scs, (rh - 0.13 - 0.38) * scs, "#8a8a90", INK, 0.3))
    if spec.railing.drink_rail:
        o.append(R(Xs(yr - 0.23), Zs(zd + rh + 0.21), 0.46 * scs, 0.08 * scs, DECK, INK, 0.4))
    for sc in q["screens"]:                # a front screen inboard of the rail: housing under the front beam, fabric to the deck
        if sc["plane"] == "y":
            c_ = sc["cassette"]
            o.append(R(Xs(c_["y0"]), Zs(c_["z1"]), (c_["y1"] - c_["y0"]) * scs, (c_["z1"] - c_["z0"]) * scs, "#2c2c30", INK, 0.4))
            o.append(LN(Xs(sc["line"]), Zs(c_["z0"]), Xs(sc["line"]), Zs(sc["z_bottom"] + 0.1), "#5b6e8c", 1.2, "3 2"))
    xr = 596 + 330 + 8
    dim_v(o, Zs, xr, zd, zb, f"{ftin((zb - zd) * 12)} clear", 7, left=False)
    dim_v(o, Zs, xr, zb, zt, f"{h * 12:g}\"", 6.2, left=False)
    dim_v(o, Zs, xr + 22, zd, zt, f"{ftin((zt - zd) * 12)} deck to top", 7, left=False)
    dim_h(o, Xs, Zs(zt + 1.05), y0, y1, f"{ftin(q['D'] * 12)} wall to front of frame", 7)
    o.append(T(Xs(y1) + 8, Zs(zt) + 9, f"TOP OF FRAME {ftin(zt * 12)}", 6.2, 800, "start", MUTE))
    o.append(T(Xs(yf) + 8, Zs(zd) - 4, f"DECK {ftin(zd * 12)}", 6.2, 800, "start", MUTE))
    o.append(T(Xs(yf) + 8, Zs(zd) + 6, "above the patio" if zd > 3 else "above grade", 6.0, 600, "start", MUTE))
    _lead(o, Xs(eave_y + 0.2), Zs(z_eave - 0.1), Xs(y0 + 2.6), Zs(zt + 3.15), "existing eave + gutter, soffit ~7'-3\" over the deck: field verify", 6.2)
    if q["attach"] == "house":
        _lead(o, Xs(y0 + wb / 2), Zs(zbb - 0.12), Xs(y0 + 1.2), Zs(zb - 1.1),
              (f"house-side {q['frame_label']} beam on flashed stand-offs @ {BRACKET_OC_FT * 12:g}\" OC, lagged into the rafters over solid blocking (roof-line mount)"
               if mount == "roof" else f"house-side {q['frame_label']} beam on wall brackets @ {BRACKET_OC_FT * 12:g}\" OC into the wall framing"), 6.2)
    _lead(o, Xs((y0 + y1) / 2), Zs(q["z_pivot"] - 0.1), Xs(y0 + 2.4), Zs(zb - 2.9), f"{q['blade_w'] * 12:g}\" blades on {q['spacing'] * 12:g}\" centres, drawn {q['angle_deg']:g}° open (0 to {ANGLE_RANGE[1]:g}°)", 6.2)
    _lead(o, Xs(py), Zs(zd + 3.6), Xs(y0 + 3.4), Zs(zd + 3.5), f"{p * 12:g}x{p * 12:g} aluminum post, {ins_txt} inside the frame face: the rail post, downspout inside", 6.2)
    _lead(o, Xs(yr - 0.11), Zs(zd + rh - 0.06), Xs(y0 + 3.4), Zs(zd + 1.3), "rail (cut) ends into the post on wall-mount brackets", 6.2)
    _lead(o, Xs(py), Zs(zd - 1.6), Xs(y0 + 3.4), Zs(zd - 1.7), "deck post + pier directly under the roof post (framing plan)", 6.2)

    # ---------------------------------------------------------------- detail 1: the post on the deck edge
    _panel(o, 584, 346, 402, 260, "1", "THE ROOF POST ON THE DECK EDGE — IT IS THE RAIL POST")
    k_ = 3.8                                 # px per inch
    jd_in = jd * 12
    zbase = jd_in + 1.0                      # the deck surface over the rim (inches above the rim's bottom)
    pl_in, p_in = q["plate"] * 12, p * 12
    rh_in = float(spec.railing.height_in or 36.0)
    # (a) elevation from the yard: the post on the deck, the rail panels both sides, the rim and fascia, the column below
    ex, ez = 706, 584
    def EX(v): return ex + v * k_
    def EZ(v): return ez - v * k_
    o.append(T(EX(-28), 380, "ELEVATION", 6.6, 900, fill=MUTE)); o.append(T(EX(-28), 389, "from the yard", 6.0, 700, fill=MUTE))
    o.append(R(EX(-28), EZ(jd_in + 1.0), 56 * k_, (jd_in + 1.0) * k_, DECK, INK, 0.6))
    o.append(T(EX(-27), EZ(jd_in / 2) + 2, "fascia over the doubled rim", 5.8, 700))
    o.append(R(EX(-3.75), EZ(0), 7.5 * k_, 2.5 * k_, FILL["timber"], INK, 0.6, 'stroke-dasharray="3 2"'))
    o.append(R(EX(-28), EZ(zbase), 56 * k_, 1.0 * k_, DECK, INK, 0.6))
    for sg in (-1, 1):                      # the rail panels, bracketed into the post's sides
        xa_, xb_ = sorted((sg * p_in / 2, sg * 27.5))
        o.append(R(EX(xa_), EZ(zbase + rh_in), (xb_ - xa_) * k_, 1.6 * k_, "#3a3a3e", INK, 0.4))
        o.append(R(EX(xa_), EZ(zbase + 4.4), (xb_ - xa_) * k_, 1.1 * k_, "#3a3a3e", INK, 0.4))
        if spec.railing.drink_rail:
            o.append(R(EX(xa_), EZ(zbase + rh_in + 2.6), (xb_ - xa_) * k_, 1.0 * k_, DECK, INK, 0.4))
        xv = xa_ + 2.6
        while xv < xb_ - 0.5:
            o.append(R(EX(xv), EZ(zbase + rh_in - 1.6), 0.75 * k_, (rh_in - 1.6 - 4.4) * k_, "#3a3a3e", "none", 0))
            xv += 4.5
        bx_ = sg * p_in / 2 + (0 if sg > 0 else -1.4)
        o.append(R(EX(bx_), EZ(zbase + rh_in + 0.6), 1.4 * k_, 2.6 * k_, INK, INK, 0.3))
        o.append(R(EX(bx_), EZ(zbase + 5.0), 1.4 * k_, 2.0 * k_, INK, INK, 0.3))
    o.append(R(EX(-pl_in / 2), EZ(zbase + 0.5), pl_in * k_, 0.5 * k_ + 1, "#555", INK, 0.5))
    o.append(R(EX(-p_in / 2 - 0.25), EZ(zbase + 4.0), (p_in + 0.5) * k_, 3.5 * k_, "#2c2c30", INK, 0.5))
    o.append(R(EX(-p_in / 2), EZ(zbase + 44.0), p_in * k_, 40.0 * k_, BLACK, INK, 0.6))
    o.append(R(EX(-1.5), EZ(zbase + 2.4), 3.0 * k_, 1.8 * k_, "#55555a", INK, 0.4))
    _lead(o, EX(p_in / 2 + 0.7), EZ(zbase + rh_in - 0.6), EX(10), EZ(zbase + rh_in + 8.5), "wall-mount brackets: top and bottom rail into the post", 5.8)
    _lead(o, EX(0.5), EZ(zbase + 3.2), EX(10), EZ(zbase + 15.5), "downspout outlet (it runs inside the post)", 5.8)
    _lead(o, EX(-pl_in / 2 + 0.6), EZ(zbase + 0.3), EX(-27), EZ(zbase + 13.0), f"{pl_in:g}\" base plate + base cover", 5.8)
    _lead(o, EX(-2.5), EZ(-1.0), EX(10), EZ(-0.5), "column / beam under the post (framing plan)", 5.8)
    # (b) section through the deck edge: the post centre on the rail line, the plate over solid blocking
    sx, sz = 952, 584
    def SX(v): return sx + v * k_
    def SZ(v): return sz - v * k_
    rp_in = rp * 12
    pc_in = (ins + p / 2) * 12                    # the post centre, in from the frame face
    o.append(T(SX(-30), 380, "SECTION", 6.6, 900, fill=MUTE))
    o.append(R(SX(-30), SZ(jd_in), 24.0 * k_, jd_in * k_, FILL["timber"], INK, 0.5, 'fill-opacity="0.55"'))
    o.append(R(SX(-6.0), SZ(jd_in), 3.0 * k_, jd_in * k_, FILL["timber_dk"], INK, 0.6))
    o.append(R(SX(-3.0), SZ(jd_in), 3.0 * k_, jd_in * k_, FILL["timber"], INK, 0.6))
    o.append(R(SX(0), SZ(jd_in + 1.0), 0.5 * k_ + 1, (jd_in + 1.0) * k_, DECK, INK, 0.5))
    o.append(R(SX(-30), SZ(zbase), 30.97 * k_, 1.0 * k_, DECK, INK, 0.6))
    for bx in (-pc_in - pl_in / 2 + 0.9, -pc_in + pl_in / 2 - 0.9):
        o.append(LN(SX(bx), SZ(zbase + 0.6), SX(bx), SZ(zbase - jd_in * 0.8), INK, 1.4))
    o.append(R(SX(-pc_in - pl_in / 2), SZ(zbase + 0.5), pl_in * k_, 0.5 * k_ + 1, "#555", INK, 0.5))
    o.append(R(SX(-pc_in - p_in / 2), SZ(zbase + 28.0), p_in * k_, 27.5 * k_, BLACK, INK, 0.6))
    o.append(LN(SX(-rp_in), SZ(zbase + 30.0), SX(-rp_in), SZ(zbase + 1.0), GOLD, 1.2, "4 2"))
    o.append(T(SX(-18), SZ(jd_in / 2) + 2, "solid blocking", 5.8, 800, "middle"))
    for d_, lab_, z_ in ((ins * 12, f"{ins_txt} post face", zbase + 31.0), (rp_in, f"{ftin(rp_in)} rail line", zbase + 34.5)):
        o.append(LN(SX(0), SZ(z_), SX(-d_), SZ(z_), INK, 0.6)); o.append(LN(SX(0), SZ(z_ + 1.0), SX(0), SZ(z_ - 1.0), INK, 0.6))
        o.append(LN(SX(-d_), SZ(z_ + 1.0), SX(-d_), SZ(z_ - 1.0), INK, 0.6))
        o.append(T(SX(-d_) - 3, SZ(z_) + 3, lab_, 5.8, 800, "end"))
    _lead(o, SX(-rp_in), SZ(zbase + 20), SX(-29), SZ(zbase + 25), "the rail line (gold) runs into the post: the panels end on its faces", 5.8)
    _lead(o, SX(-pc_in + pl_in / 2 - 0.9), SZ(zbase - 3.0), SX(-29), SZ(zbase + 13), "through-bolts into the blocking; tie-down to the post below", 5.8)

    # ---------------------------------------------------------------- what it is
    _panel(o, 14, 346, 560, 260, "", "WHAT IT IS")
    loads = post_loads(q, snow_psf=float(spec.site.ground_snow_psf or 30))
    notes = scope_words(q) + [
        f"Frame {q['beam_label']} aluminum (Suncoast spans: 2x8 to 15', 2x10 to 18', 4x8 to 22' between posts); the longest span here is {ftin(q['span_ft'] * 12)}.",
        f"Blades span up to {BLADE_SPAN_MAX_FT:g}' (snow-load dependent); one motor blade per zone, up to {MOTOR_SF:g} SF a motor.",
        f"Each post carries about {int(round(max(x['total_lb'] for x in loads) / 50.0) * 50):,} lb ({max(x['trib_sf'] for x in loads):.0f} SF at 6 psf dead + {spec.site.ground_snow_psf:g} psf snow): the framing under it takes it down to the footings. Suncoast's engineering for the site's snow and wind governs the roof.",
        "House side: the brackets go into the wall framing — field verify the eave, the wall and the framing behind it; flashed and sealed at every fastener.",
    ] + ([("Screens option — " + ", ".join(f"{sc['side']} {ftin(sc['width'] * 12)}" for sc in q["screens"]) + f" wide, {ftin(max(sc['max_drop'] for sc in q['screens']) * 12)} drop, "
           + ("clear vinyl" if q["screens"][0]["fabric"] == "vinyl" else f"{q['screens'][0]['color']} mesh") + f"; {q['screens'][0]['housing'] * 12:g}\" housings under the frame "
           + ("inside the rail" if q["screens"][0]["mount"] == "inside" else "on the beams' outer faces") + ", side tracks, a bottom bar down to the deck")] if q["screens"] else []) + list(q["notes"])
    yy = 371
    for ln in notes:
        for k2, w_ in enumerate(textwrap.wrap(ln, 112)):
            o.append(T(26 if k2 == 0 else 33, yy, ("· " if k2 == 0 else "") + w_, 7.1, 500)); yy += 9.6
        yy += 2.4
        if yy > 598:
            break
    return _sheet("A-403", f"{q['brand']} louvered roof — plan, section, post", "The roof over the deck: frame, zones, blades, posts on the rail line, the house beam on its brackets; heights; the post on the deck edge", o,
                  "Plan and section not to a common scale · dimensions govern · Suncoast's shop drawings and engineering govern the roof", meta)
