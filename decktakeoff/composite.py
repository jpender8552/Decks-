"""Composite decks: a deck that wraps a corner of the house is two or more PARTS, each a normal rectangle / zone set on its
own wall, placed in one global frame by an axis-aligned transform. Each part is taken off with the ordinary engine; the
lines, cut list, schedules and flags merge; the 3D scene composes the parts in the global frame with the house drawn from
its measured footprint."""
from __future__ import annotations

import copy
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .flags import Flag, run_flags
from .layout import Layout, RailPost
from .spec import DeckSpec
from .takeoff import CutPiece, Line, Takeoff, build_takeoff


@dataclass
class Placement:
    ox: float = 0.0; oy: float = 0.0
    xx: float = 1.0; xy: float = 0.0
    yx: float = 0.0; yy: float = 1.0

    def pt(self, x: float, y: float) -> Tuple[float, float]:
        return (self.ox + self.xx * x + self.xy * y, self.oy + self.yx * x + self.yy * y)

    def box(self, x0, x1, y0, y1) -> Tuple[float, float, float, float]:
        xs, ys = zip(*(self.pt(x, y) for x in (x0, x1) for y in (y0, y1)))
        return (min(xs), max(xs), min(ys), max(ys))

    @property
    def swaps(self) -> bool:
        return abs(self.xx) < 0.5     # the local x axis maps onto global y


@dataclass
class Part:
    name: str
    spec: DeckSpec
    takeoff: Takeoff
    flags: List[Flag]
    placement: Placement

    @property
    def layout(self) -> Layout:
        return self.takeoff.layout


class CompositeRail:
    def __init__(self, parts: List[Part]):
        rails = [p.layout.rail for p in parts if p.layout.rail]
        r0 = rails[0]
        self.system, self.color, self.height = r0.system, r0.color, r0.height
        self.posts = []
        for p in parts:
            if p.layout.rail:
                for q in p.layout.rail.posts:
                    gx, gy = p.placement.pt(q.x / 12.0, q.y / 12.0)
                    self.posts.append(RailPost(gx * 12.0, gy * 12.0, q.kind, f"{p.name}: {q.tag}"))
        self.sections = [s for r in rails for s in r.sections]
        self.rail_lf = round(sum(r.rail_lf for r in rails), 1)
        self.perimeter_lf = round(sum(r.perimeter_lf for r in rails), 1)
        self.openings = [o for r in rails for o in r.openings]
        self.notes = [n for r in rails for n in r.notes]


class CompositeLayout:
    """Duck-types Layout for pricing, flags, the 3D scene, the build steps and the reports."""
    def __init__(self, spec: DeckSpec, parts: List[Part]):
        self.spec = spec
        self.parts = parts
        L0 = parts[0].layout
        self.frame, self.decking = L0.frame, L0.decking
        self.rail = CompositeRail(parts) if any(p.layout.rail for p in parts) else None
        self.stairs = [st for p in parts for st in p.layout.stairs]
        self.zones = [z for p in parts for z in p.layout.zones]
        self.beam_lines = [bl for p in parts for bl in p.layout.beam_lines]
        self.divider_x = []
        self.edges = []
        self.multi = True
        self.notes = [f"{p.name}: {n}" for p in parts for n in p.layout.notes]
        self.wall_lf = round(sum(p.layout.wall_lf for p in parts), 1)
        self.plan = None                    # each part lays its own field (its sheets show it); the steps list rows per zone
        self.outline_edges = []
        self.edge_posts = [ep for p in parts for ep in getattr(p.layout, "edge_posts", [])]
        self.edge_post_len = max([getattr(p.layout, "edge_post_len", 0.0) for p in parts] or [0.0])
        xs, ys = [], []
        for p in parts:
            L = p.layout
            for z in L.zones:
                x0, x1, y0, y1 = p.placement.box(z.x0 / 12, (z.x0 + z.W) / 12, z.wall_y / 12, (z.wall_y + z.D) / 12)
                xs += [x0, x1]; ys += [y0, y1]
        self.bbox = (min(xs), max(xs), min(ys), max(ys))
        self.finished_w = (self.bbox[1] - self.bbox[0]) * 12
        self.finished_d = (self.bbox[3] - self.bbox[2]) * 12

    @property
    def deck_sf(self) -> float:
        return round(sum(p.layout.deck_sf for p in self.parts), 1)

    @property
    def outer_edge_lf(self) -> float:
        return round(sum(p.layout.outer_edge_lf for p in self.parts), 1)

    @property
    def n_footings(self) -> int:
        return sum(p.layout.n_footings for p in self.parts)

    @property
    def stair_support_posts(self) -> int:
        return sum(p.layout.stair_support_posts for p in self.parts)


def _sub_spec(spec: DeckSpec, part: dict) -> DeckSpec:
    """The part as an ordinary DeckSpec: the job's products, site, framing and extras; the part's geometry, rail edges and stairs."""
    d = spec.to_dict()
    g = dict(d.get("geometry", {}))
    # the job-wide pieces are drawn once, in the global frame, by the composite scene: the measured house and yard, the
    # house blocks, angled walls; a job-level outline is global too (a part brings its own, in its own frame)
    for k in ("parts", "zones", "width", "depth", "width_in", "depth_in", "house_blocks", "house_openings", "cover",
              "house_model", "site_model", "house_walls", "outline"):
        g.pop(k, None)
    g.update(part.get("geometry", {}))
    if d["geometry"].get("louvered_roofs"):     # a job-level roof (global frame): the part sees it in its own frame, marked so it neither draws nor prices it
        from .louvered import part_roofs
        g["louvered_roofs"] = part_roofs(d["geometry"]["louvered_roofs"], part)
    d["geometry"] = g
    r = dict(d.get("railing", {}))
    for k in ("edges", "sides", "openings"):
        r.pop(k, None)
    r.update(part.get("railing", {}))
    d["railing"] = r
    d["stairs"] = part.get("stairs", [])
    dk = dict(d.get("decking", {}))       # a part may set its own decking keys (breaker lines in its own frame: divider_x_ft)
    dk.update(part.get("decking", {}))
    d["decking"] = dk
    d["job"] = f"{spec.job} — {part['name']}"
    return DeckSpec.from_dict(d)


def _stair_foot(p: "Part", st) -> Optional[Tuple[float, float]]:
    """Where a single-flight stair of part p lands: a plan point (global feet) 6" past its bottom riser, centred on its width."""
    L = p.layout
    run = st.geo.total_run_in
    if getattr(st, "inset", False) and st.notch:
        nt = st.notch
        along = nt["out"] - nt["sgn"] * (nt.get("skirt_t", 0.0) + 6.0)
        across = (nt["lo"] + nt["hi"]) / 2
        x, y = (along, across) if nt["axis"] == "x" else (across, along)
        return p.placement.pt(x / 12.0, y / 12.0)
    if len(st.geo.flights) > 1 or not L.zones:
        return None
    side, a0, w = st.side, st.opening.start_in, st.width
    if side in ("left", "end:left"):
        z = L.zones[0]; x, y = z.x0 - run - 6.0, z.wall_y + a0 + w / 2
    elif side in ("right", "end:right"):
        z = L.zones[-1]; x, y = z.x0 + z.W + run + 6.0, z.wall_y + a0 + w / 2
    elif side == "front" or side.startswith("front:"):
        zn = side.split(":")[1] if ":" in side else None
        z = next((q for q in L.zones if q.name == zn), L.zones[0]); x, y = z.x0 + a0 + w / 2, z.wall_y + z.D + run + 6.0
    elif side.startswith("edge:") and getattr(L, "outline_edges", None):
        e = next((q for q in L.outline_edges if q.name == side), None)
        if e is None:
            return None
        ln = e.length or 1.0
        ux, uy = (e.x1 - e.x0) / ln, (e.y1 - e.y0) / ln
        nx, ny = -uy, ux                                   # outward: the outline runs clockwise
        t_ = a0 + w / 2
        x, y = e.x0 + ux * t_ + nx * (run + 6.0), e.y0 + uy * t_ + ny * (run + 6.0)
    else:
        return None
    return p.placement.pt(x / 12.0, y / 12.0)


def _stair_landings(parts: List["Part"]) -> None:
    """A "deck" stair whose foot falls on another part, at that part's height, lands on it: StairLayout.lands_on names that
    part, and the stair then draws no stand-in boards under its foot (they would z-fight with the part's own decking)."""
    for p in parts:
        for st in p.layout.stairs:
            if st.landing != "deck":
                continue
            foot = _stair_foot(p, st)
            if foot is None:
                continue
            z_low = p.spec.geometry.height_in - st.geo.total_rise_in
            for q in parts:
                if q is p or abs(q.spec.geometry.height_in - z_low) > 6.0:
                    continue
                for z in q.layout.zones:
                    x0, x1, y0, y1 = q.placement.box(z.x0 / 12, (z.x0 + z.W) / 12, z.wall_y / 12, (z.wall_y + z.D) / 12)
                    if x0 - 0.25 <= foot[0] <= x1 + 0.25 and y0 - 0.25 <= foot[1] <= y1 + 0.25:
                        st.lands_on = q.name
                        break
                if getattr(st, "lands_on", ""):
                    break


def build_composite(spec: DeckSpec) -> Tuple[Takeoff, List[Flag]]:
    parts: List[Part] = []
    for pd in spec.geometry.parts:
        sub = _sub_spec(spec, pd)
        t = build_takeoff(sub)
        f = run_flags(t.layout)
        pl = Placement(**{k: float(v) for k, v in pd.get("placement", {}).items() if k in ("xx", "xy", "yx", "yy")},
                       ox=float(pd.get("placement", {}).get("origin", [0, 0])[0]), oy=float(pd.get("placement", {}).get("origin", [0, 0])[1]))
        parts.append(Part(pd["name"], sub, t, f, pl))
    _stair_landings(parts)          # a stair from one level onto another: no stand-in boards under its foot
    # ---- merge the orders: same category + item -> one line, quantities summed, reasons joined
    merged: "OrderedDict[Tuple[str, str], Line]" = OrderedDict()
    for p in parts:
        for ln in p.takeoff.lines:
            key = (ln.category, ln.item)
            if key in merged:
                m = merged[key]
                m.net = round(m.net + ln.net, 3); m.order = round(m.order + ln.order, 3)
                if ln.why and ln.why not in m.why:
                    m.why = f"{m.why} + {p.name}: {ln.why}"
            else:
                c = copy.copy(ln)
                c.why = f"{p.name}: {ln.why}" if ln.why else p.name
                merged[key] = c
    lines = list(merged.values())
    cut = [CutPiece(c.member, c.nominal, c.length_in, c.qty, f"{p.name} · {c.note}".strip(" ·")) for p in parts for c in p.takeoff.cut_list]
    sched: "OrderedDict[str, str]" = OrderedDict()
    for p in parts:
        for k, v in p.takeoff.schedule.items():
            sched[k] = (sched[k] + f"  ||  {p.name}: {v}") if k in sched else f"{p.name}: {v}"
    L = CompositeLayout(spec, parts)
    s0 = parts[0].takeoff.summary
    def joined(key):
        return " · ".join(f"{p.name}: {p.takeoff.summary[key]}" for p in parts if key in p.takeoff.summary)
    summary = dict(s0)
    summary.update(
        finished_frame=f"{len(parts)} parts — " + " · ".join(f"{p.name} {p.takeoff.summary.get('finished_frame', '')}" for p in parts),
        finished_deck=f"{L.deck_sf:g} SF total — " + " · ".join(f"{p.name} {p.layout.deck_sf:g} SF" for p in parts),
        deck_sf=L.deck_sf,
        zones=[f"{p.name} — {z}" for p in parts for z in (p.takeoff.summary.get("zones") or [p.takeoff.summary.get("finished_frame", "")])],
        joists=joined("joists"), rims=s0.get("rims", ""),
        beams=[f"{p.name}: {b}" for p in parts for b in p.takeoff.summary.get("beams", [])],
        posts=joined("posts"), rail=joined("rail"),
        stairs=[f"{p.name}: {st}" for p in parts for st in p.takeoff.summary.get("stairs", [])])
    notes = [f"{p.name}: {n}" for p in parts for n in p.takeoff.notes]
    t = Takeoff(spec, L, lines, cut, dict(sched), summary, notes,
                joist_lf=round(sum(p.takeoff.joist_lf for p in parts), 1), timber_sf=round(sum(p.takeoff.timber_sf for p in parts), 1))
    flags: List[Flag] = []
    seen = set()
    for p in parts:
        for f in p.flags:
            k = (f.severity, f.topic, f.text)
            if k not in seen:
                seen.add(k); flags.append(f)
    return t, flags
