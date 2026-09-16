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


def _sub_spec(spec: DeckSpec, part: dict) -> DeckSpec:
    """The part as an ordinary DeckSpec: the job's products, site, framing and extras; the part's geometry, rail edges and stairs."""
    d = spec.to_dict()
    g = dict(d.get("geometry", {}))
    for k in ("parts", "zones", "width", "depth", "width_in", "depth_in", "house_blocks", "house_openings", "cover"):
        g.pop(k, None)
    g.update(part.get("geometry", {}))
    d["geometry"] = g
    r = dict(d.get("railing", {}))
    for k in ("edges", "sides", "openings"):
        r.pop(k, None)
    r.update(part.get("railing", {}))
    d["railing"] = r
    d["stairs"] = part.get("stairs", [])
    d["job"] = f"{spec.job} — {part['name']}"
    return DeckSpec.from_dict(d)


def build_composite(spec: DeckSpec) -> Tuple[Takeoff, List[Flag]]:
    parts: List[Part] = []
    for pd in spec.geometry.parts:
        sub = _sub_spec(spec, pd)
        t = build_takeoff(sub)
        f = run_flags(t.layout)
        pl = Placement(**{k: float(v) for k, v in pd.get("placement", {}).items() if k in ("xx", "xy", "yx", "yy")},
                       ox=float(pd.get("placement", {}).get("origin", [0, 0])[0]), oy=float(pd.get("placement", {}).get("origin", [0, 0])[1]))
        parts.append(Part(pd["name"], sub, t, f, pl))
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
