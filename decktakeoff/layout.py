"""Turn a DeckSpec into geometry: where every joist, rim, beam, post, footing, board, rail post and stringer goes.
All numbers are inches in the plan convention documented in spec.py."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import engineering as eng
from .catalog import (DECKING, FASCIA, NOSE, RAIL_SYSTEMS, RISER, STOCK_LENGTHS_FT, actual, decking_facts,
                      parse_beam, FOOTING_CAPACITY_LB)
from .spec import DeckSpec, RailOpening
from .units import ftin

PF_INSET = 5.25       # picture-frame joist centre from the frame face for 2x framing (1-1/2" gap inboard of a double rim)
RIM_PLY = 1.5
CAISSON_STANDOFF = 7.0  # caisson 6" above grade + 1" standoff base (Eagle's Nest: post = 96 - 1 - 9.25 - 11.5 - 7 = 67.25")
OVERHANG_NO_FASCIA = 1.5   # boards overhang the exposed rim 1-1/2" when there is no fascia (Eagle's Nest)
BLOCK_MAX_SPACING = 48.0   # timber frames: a blocking row so no unblocked joist run between supports exceeds 4' 
LEDGER_T = 1.5
RAIL_POST_INSET = 2.5 # 2" Fulton post against the inside of the OUTER rim ply -> centre 2.5" in from the frame face
BEAM_HOLD_IN = 0.5    # drop beam held 1/2" inside the rim faces
POST_END_OVERHANG = 12.0   # beam overhang past the end posts
DP_STANDOFF = 4.5     # pier head + ABA66Z above grade
CONC_STANDOFF = 2.0


@dataclass
class BeamLayout:
    kind: str                  # drop | flush
    size: str
    species: str
    plies: int
    width: float
    depth: float
    cl_y: float                # centreline from the house face
    length: float
    x0: float
    posts_x: List[float]
    post_spacing: float
    back_span: float           # joist span on the house side of this beam (support to support)
    cantilever: float          # joists past this beam (drop beams only)
    trib_depth: float          # tributary depth the beam carries
    check: eng.SpanCheck
    cap: str
    label: str = ""
    post_len: float = 0.0


@dataclass
class BeamLine:
    """A beam line across one or more zones (a drop beam at the same setback in adjacent zones is one continuous beam)."""
    kind: str
    size: str
    species: str
    plies: int
    width: float
    depth: float
    y: float                     # plan y of the CL (from the reference wall; fronts are collinear in multi-zone plans)
    x0: float
    x1: float
    zones: List[str]
    posts_x: List[float]
    post_zone: List[str]
    post_loads: List[float]
    post_len: float
    pieces: List[Tuple[float, float]]     # (x0, x1) of each beam piece, spliced over posts
    cap_mid: str
    cap_end: str
    label: str = ""

    @property
    def length(self) -> float:
        return self.x1 - self.x0

    @property
    def n_posts(self) -> int:
        return len(self.posts_x)


@dataclass
class FrameLayout:
    W: float
    D: float
    joist_size: str
    joist_species: str
    spacing: float
    joist_len: float
    joist_x: List[float]
    pf_x: List[float]
    ledger: bool
    rim_plies: int
    beams: List[BeamLayout]
    blocking_rows_y: List[float]
    n_blocks_per_row: int
    block_len: float
    joist_checks: List[eng.SpanCheck]
    post_size: str
    post_len: float
    post_height_check: Tuple[bool, float]
    n_posts: int
    footing_type: str
    footing_model: str
    footing_load_lb: float
    footing_capacity_lb: float
    footing_dia_in: float
    footing_depth_in: float
    total_psf: float
    load_note: str
    joist_bays: int = 0        # number of joist runs between supports (1 = ledger->beam only, 2 = flush mid beam)
    hangers_single: int = 0    # LUS-type single joist hangers
    hangers_double: int = 0    # HUCQ double hangers (rim ends)
    h25_ties: int = 0
    notes: List[str] = field(default_factory=list)


@dataclass
class DeckingLayout:
    collection: str
    color: str
    material: str
    bw: float
    bt: float
    gap: float
    fascia_t: float
    deck_w: float             # outside of fascia + nose, along the house
    deck_d: float
    direction: str
    picture_frame: bool
    field_len: float          # length of a field board (before cutting to length)
    rows: int                 # field rows
    row_pieces: int           # pieces per row (butt joints)
    piece_len: float
    stock_ft: int
    last_row_dev: float       # +: squeeze, -: slack at the last gap
    border_pieces: List[Tuple[str, float]]
    fascia_pieces: List[Tuple[str, float]]
    bearing_points: int       # joists (incl PF) each field board crosses
    gaps: int
    clips: int
    first_row_screws: int
    border_screws: int
    fascia_screws: int
    sf: float
    notes: List[str] = field(default_factory=list)


@dataclass
class RailPost:
    x: float
    y: float
    kind: str      # END | LINE | CORNER | STAIR
    tag: str


@dataclass
class RailSection:
    side: str
    ctc: float
    panel_stock_in: int
    cut_len: float
    kind: str = "level"


@dataclass
class RailLayout:
    system: str
    color: str
    height: float
    posts: List[RailPost]
    sections: List[RailSection]
    rail_lf: float           # deck-edge LF of actual rail (labor)
    perimeter_lf: float
    openings: List[RailOpening]
    notes: List[str] = field(default_factory=list)


@dataclass
class StairLayout:
    side: str
    width: float
    geo: eng.StairGeometry
    tread_boards_per_tread: int
    tread_pieces: int
    riser_pieces: int
    stringers: int
    stringer_stock_ft: int
    stair_rail_sides: int
    stair_sections: List[RailSection]
    stair_posts: int
    landing: str
    opening: RailOpening
    notes: List[str] = field(default_factory=list)
    mid_support: bool = False            # carrier beam on 2 posts + 2 footings at mid-run under the stringers (stringer run over 6')
    mid_run_in: float = 0.0              # horizontal distance from the top riser to the carrier CL


@dataclass
class Edge:
    """One straight run of the deck's outer outline (plan coordinates; y grows toward the yard)."""
    name: str            # "front:A" | "step:C-B" | "end:left" | "end:right"
    x0: float
    y0: float
    x1: float
    y1: float
    exposed: bool = True     # False along a privacy wall / house

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


@dataclass
class ZoneLayout:
    name: str
    label: str
    x0: float                # left frame face of the zone along the house
    wall_y: float            # this zone's house wall (0 = reference wall; negative = recessed)
    W: float
    D: float
    frame: FrameLayout
    decking: DeckingLayout
    hot_tub: bool = False


@dataclass
class Layout:
    spec: DeckSpec
    frame: FrameLayout            # zone A (single-rectangle decks: the frame)
    decking: DeckingLayout        # zone A
    rail: Optional[RailLayout]
    stairs: List[StairLayout]
    finished_w: float             # total along the house
    finished_d: float             # deepest zone
    notes: List[str]
    zones: List[ZoneLayout] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    multi: bool = False
    beam_lines: List[BeamLine] = field(default_factory=list)
    divider_x: List[Tuple[float, float, str]] = field(default_factory=list)   # (x, length from the front, label) contrast divider boards
    wall_lf: float = 0.0          # LF of house wall that gets membrane + flashing (ledgers + return walls; never a privacy wall)

    @property
    def deck_sf(self) -> float:
        """Sold square footage: over the fascia when there is one (Jason Ct 187), frame area when the rim is exposed (Eagle's Nest 617.2)."""
        if not self.zones:
            return self.decking.sf
        if self.spec.decking.fascia:
            return int(round(sum(z.decking.deck_w * z.decking.deck_d for z in self.zones) / 144.0))
        return round(sum(z.W * z.D for z in self.zones) / 144.0, 1)

    @property
    def outer_edge_lf(self) -> float:
        return round(sum(e.length for e in self.edges if e.exposed) / 12.0, 1)

    @property
    def stair_support_posts(self) -> int:
        return sum(2 for st in self.stairs if st.mid_support)

    @property
    def n_footings(self) -> int:
        """Every post that needs a footing: beam-line posts plus the mid-stair carrier posts."""
        return sum(z.frame.n_posts for z in self.zones) + self.stair_support_posts


# ================================================================== decking first (it sizes the frame)
def _stock_for(length_in: float, step_up_within: float = 2.0) -> int:
    for s in STOCK_LENGTHS_FT:
        if length_in <= s * 12 - step_up_within:
            return s
    return STOCK_LENGTHS_FT[-1]


def size_frame_to_boards(D: float, bw: float, gap: float, fascia_t: float, fit: bool) -> Tuple[float, int, float, str]:
    """Returns (D, rows, last-row deviation, note). deck_d = D + fascia_t + NOSE.
    Rows fill from a 3/16 gap off the house to a 3/16 gap off the front border."""
    deck_d = D + fascia_t + NOSE
    avail = deck_d - bw            # front border takes bw
    exact = (avail - gap) / (bw + gap)
    if fit:
        rows = max(1, int(round(exact)))
        ideal_deck_d = gap + rows * (bw + gap) + bw
        dev = ideal_deck_d - deck_d           # + means boards need more room than we have (squeeze)
        if abs(dev) > 0.5:
            newD = D + dev
            return newD, rows, 0.0, f"frame depth set to {ftin(newD)} (was {ftin(D)}) so all {rows} field rows are full boards — zero rips"
        return D, rows, dev, f"{rows} full rows; last gap {'squeezed' if dev > 0 else 'opened'} {abs(dev):.2f}\" across {rows} gaps — no rip"
    rows = int(math.floor(exact))
    rip = avail - gap - rows * (bw + gap) - gap
    return D, rows, -rip, (f"{rows} full rows + one rip of {rip:.2f}\"" if rip > 0.5 else f"{rows} full rows, {rip:.2f}\" slack")


def decking_layout(spec: DeckSpec, W: float, D: float, n_bearing: int) -> DeckingLayout:
    dk = spec.decking
    f = decking_facts(dk.collection)
    bw, bt, gap = f["width"], f["thick"], spec.deck_gap
    fas = FASCIA[f["material"]]
    ft_ = fas["thick"] if dk.fascia else 0.0
    nose = NOSE if dk.fascia else OVERHANG_NO_FASCIA
    deck_w = W + 2 * (ft_ + nose)
    deck_d = D + ft_ + nose
    pf = spec.geometry.picture_frame
    notes = []
    direction = spec.geometry.board_direction
    if direction == "parallel":
        # field runs along the house between the side borders
        field_len = deck_w - 2 * (bw + gap) if pf else deck_w
        span_len = deck_d - (bw + gap) if pf else deck_d      # depth available for rows (front border)
        # rows computed by size_frame_to_boards (already folded into D); recompute for reporting
        avail = deck_d - (bw if pf else 0)
        rows = int(round((avail - gap) / (bw + gap))) if spec.geometry.fit_frame_to_boards else int(math.floor((avail - gap) / (bw + gap)))
        rows = max(rows, 1)
        dev = (gap + rows * (bw + gap) + (bw if pf else 0)) - deck_d
    else:
        field_len = deck_d - (bw + gap) if pf else deck_d     # boards run out from the house to the front border
        avail = deck_w - (2 * bw if pf else 0)
        rows = int(math.floor((avail - gap) / (bw + gap)))
        dev = (gap + rows * (bw + gap) + (2 * bw if pf else 0)) - deck_w
        rip = -dev - gap
        notes.append(f"perpendicular boards: {rows} full boards across, {'rip ' + format(rip, '.2f') + chr(34) if rip > 0.5 else 'no rip'}")
    # pieces per row
    k = max(1, int(math.ceil(field_len / (STOCK_LENGTHS_FT[-1] * 12 - 1))))
    piece = field_len / k
    stock = _stock_for(piece)
    if k > 1:
        notes.append(f"field boards butt-joint: {k} pieces per row, stagger joints on alternating joists")
    # borders and fascia
    border, fascia = [], []
    if pf:
        if direction == "parallel":
            border += [("left border", deck_d), ("right border", deck_d), ("front border", deck_w)]
        else:
            border += [("left border", deck_d), ("right border", deck_d), ("front border", deck_w)]
    if dk.fascia:
        for name, L in (("left fascia", D + ft_), ("right fascia", D + ft_), ("front fascia", W + 2 * ft_)):
            rem = L
            while rem > 144 + 0.01:
                fascia.append((name, 144.0)); rem -= 144.0
            fascia.append((name, rem))
    # fasteners
    if direction == "parallel":
        bearing = n_bearing
        gaps = rows                       # every row is clipped on its far edge; the last gap is to the front border
        first_row = bearing               # one face screw per joist on the house edge of row 1
    else:
        bearing = int(math.floor((field_len) / spec.joist_spacing)) + 2
        gaps = rows
        first_row = rows                  # one screw per board end at the ledger
    clips = gaps * bearing
    border_screws = 0
    if pf:
        side_pts = int(math.floor(deck_d / 16)) + 2
        border_screws += 2 * side_pts * 2                       # 2 screws every 16" into the rim, both sides
        border_screws += 2 * (n_bearing + 2)                    # front: 2 at every joist + over each side rim
    if spec.decking.fastener_system == "Cortex" or (spec.decking.fastener_system is None and spec.decking.profile == "square"):
        clips = 2 * rows * bearing                              # Cortex: 2 plugs per board at every joist (field); borders counted in border_screws
    fascia_screws = 0
    for _, L in fascia:
        fascia_screws += 4 + max(0, int(math.ceil(L / 12)) - 1)  # 2 at each end, then alternate top/bottom every 12"
    sf = round(deck_w * deck_d / 144.0)
    if f["material"] == "Composite" and f.get("profile") == "scalloped":
        notes.append(f"{dk.collection} is scalloped — Cortex not approved; field is 100% hidden on Camo EdgeClips, board ends clipped on the PF joists")
    return DeckingLayout(dk.collection, dk.color, f["material"], bw, bt, gap, ft_, deck_w, deck_d, direction, pf, field_len, rows, k, piece,
                         stock, dev, border, fascia, bearing, gaps, clips, first_row, border_screws, fascia_screws, sf, notes)


# ================================================================== frame
def _place_posts(beam_len: float, allow: float, override: Optional[float]) -> Tuple[List[float], float]:
    """Posts 12\" in from each beam end (up to 24\", never more than a quarter span, when that saves a post),
    then evenly spaced at or under the allowable span."""
    lim = min(allow, override) if override else allow
    best = None
    for ov in (POST_END_OVERHANG, 18.0, 24.0):
        if ov > lim / 4 + 0.01 and ov > POST_END_OVERHANG:
            continue
        inner = beam_len - 2 * ov
        if inner <= 0:
            return [beam_len / 2], 0.0
        n_spans = max(1, int(math.ceil(inner / lim - 1e-9)))
        if best is None or n_spans < best[0]:
            best = (n_spans, ov, inner)
    n_spans, ov, inner = best
    sp = inner / n_spans
    return [ov + i * sp for i in range(n_spans + 1)], sp


def frame_layout(spec: DeckSpec, W: float, D: float, hot_tub: Optional[bool] = None, zone: str = "") -> FrameLayout:
    fr, g = spec.framing, spec.geometry
    notes = []
    timber = spec.is_timber
    jsize, jsp = fr.joist_size, fr.joist_species
    jsp_key = "DF#1" if (timber and jsp == "DF") else jsp
    spacing = spec.joist_spacing
    jb, jd = actual(jsize)
    tub = spec.extras.hot_tub if hot_tub is None else hot_tub
    total_psf, load_note = eng.design_load_psf(spec.site.ground_snow_psf, tub)
    ledger = g.attachment == "ledger" and not (zone and next((zz.freestanding for zz in spec.zone_list if zz.name == zone), False))
    rim_plies = spec.rim_plies
    rim_t = rim_plies * jb              # timber: one 4x rim; dimensional: 2 x 1-1/2"
    ledger_t = jb
    rear_t = ledger_t if ledger else rim_t
    front_t = rim_t
    joist_len = D - rear_t - front_t
    pf = g.picture_frame and g.board_direction == "parallel"
    pf_inset = rim_t + 1.5 + jb / 2     # 1-1/2" gap inboard of the rim (5-1/4" for 2-ply 2x; 6-3/4" for a 4x rim)
    pf_x = [pf_inset, W - pf_inset] if pf else []
    right_limit = (W - pf_inset - jb) if pf else (W - rim_t - jb)
    joist_x = []
    x = spacing
    while x < right_limit - 1.5 + 1e-6:
        joist_x.append(round(x, 3)); x += spacing
    n_joists = len(joist_x) + len(pf_x)

    # ---- beams: user-declared, then auto-added if the joists can't make the depth
    if timber:
        allow_j, _ = eng.timber_allowable_span(jsize, jsp_key, total_psf * spacing / 12.0, repetitive=True)
    else:
        allow_j, _ = eng.joist_allowable(jsize, jsp, spacing, total_psf)
    beams: List[BeamLayout] = []
    declared = list(fr.beams) if fr.beams else []
    if not ledger:
        # freestanding: a rear drop beam 12" in from the rear rim face mirrors the front beam
        from .spec import Beam as _B
        rear = _B(kind="drop", size=declared[0].size if declared else ("6x12" if timber else "4x10"), species=declared[0].species if declared else "DF", setback_in=12.0)
        rear.position_in = 12.0 + parse_beam(rear.size)[2] / 2
        declared = [rear] + declared
        rear_auto = rear
    else:
        rear_auto = None
    # resolve centrelines
    cls = []
    engineered = spec.extras.engineered
    for b in declared:
        if zone and b.zones and zone not in b.zones:
            continue
        plies, nom, bwid, bdep = parse_beam(b.size)
        if b.position_in is not None and (not zone or b is rear_auto):
            cl = float(b.position_in)
        elif b.kind == "flush":
            cl = D - (b.setback_in or 0.0) - (0.0 if (b.setback_in or 0) > 0 else front_t / 2)   # flush: setback = CL back from the rim face
        else:
            cl = D - (b.setback_in if b.setback_in is not None else 24.0) - bwid / 2
            # cantilever past a drop beam may not exceed 1/4 of the back-span: c <= (D - rear_t) / 5 — unless the job is engineered
            c_max = (D - rear_t) / 5.0
            if D - cl > c_max + 0.01 and not engineered:
                cl_new = D - math.floor(c_max * 2) / 2.0
                notes.append(f"drop beam pulled out to {ftin(D - cl_new - bwid / 2)} back from the rim face (was {ftin(D - cl - bwid / 2)}) so the cantilever stays under L/4 of the back-span")
                cl = cl_new
            elif D - cl > c_max + 0.01:
                notes.append(f"{ftin(D - cl)} cantilever past the drop beam exceeds L/4 of the {ftin(cl - rear_t)} back-span — engineered condition (owner-directed)")
        if cl <= rear_t + 6 or cl > D - 1:
            continue
        cls.append((cl, b))
    cls.sort(key=lambda t: t[0])
    # auto-add intermediate beams if any support-to-support span exceeds the joist allowable
    supports = [rear_t] if ledger else []          # ledger face is a support at y=1.5
    for cl, b in cls:
        supports.append(cl)
    supports = sorted(set(supports))
    # the front rim is a support only if the last beam is a flush front beam; otherwise joists cantilever
    def spans_ok(sups):
        for a, bb in zip(sups, sups[1:]):
            if bb - a > allow_j + 0.5:
                return False
        return True
    if not spans_ok(supports):
        # insert beams between the ledger and the first beam (most common: deep deck)
        base = cls[0][1] if cls else None
        from .spec import Beam as _B
        new = []
        sups = list(supports)
        i = 0
        while i < len(sups) - 1:
            a, bb = sups[i], sups[i + 1]
            if bb - a > allow_j + 0.5:
                n = int(math.ceil((bb - a) / allow_j))
                step = (bb - a) / n
                for k in range(1, n):
                    nb = _B(kind=base.kind if base else "drop", size=base.size if base else ("6x12" if timber else "4x10"), species=base.species if base else "DF")
                    nb.position_in = a + k * step
                    new.append((nb.position_in, nb))
                    sups.insert(i + k, a + k * step)
                i += n
            else:
                i += 1
        for cl, nb in new:
            cls.append((cl, nb))
            notes.append(f"added a {nb.kind} beam at {ftin(cl)} from the house — {jsize} @ {spacing:g}\" OC {jsp} only spans {ftin(allow_j)}")
        cls.sort(key=lambda t: t[0])
    # build beam layouts with checks
    joist_checks = []
    prev_support = rear_t if ledger else None
    n_posts = 0
    worst_load = 0.0
    joist_bays = 1
    for idx, (cl, b) in enumerate(cls):
        plies, nom, bwid, bdep = parse_beam(b.size)
        is_last = idx == len(cls) - 1
        if b.kind == "flush" and abs(cl - (D - front_t / 2)) < 1.0:
            cantilever = 0.0
        else:
            cantilever = (D - cl) if is_last else 0.0
        back = (cl - prev_support) if prev_support is not None else 0.0
        if b.kind == "flush" and not is_last:
            joist_bays += 1
        if back > 0:
            joist_checks.append(eng.check_timber_joist(jsize, jsp_key, spacing, back, total_psf) if timber
                                else eng.check_joist(jsize, jsp, spacing, back, total_psf))
        if cantilever > 0 and b.kind == "drop" and not engineered:
            if cantilever > eng.CANTILEVER_RATIO * back + 0.5:
                notes.append(f"cantilever {ftin(cantilever)} exceeds L/4 of the {ftin(back)} back-span — pull the beam out or engineer it")
        # tributary depth the beam carries: half the back span + half the next span (or the cantilever)
        nxt = (cls[idx + 1][0] - cl) if not is_last else 0.0
        trib = back / 2 + (cantilever if is_last else nxt / 2)
        if not ledger and idx == 0:
            trib = nxt / 2 + (cl - 0)     # rear beam carries the rear overhang plus half the first span
        front_flush = b.kind == "flush" and abs(cl - (D - front_t / 2)) < 1.0
        length = W - 2 * BEAM_HOLD_IN if b.kind == "drop" else (W if front_flush else W - 2 * rim_t)
        # beam span table: joist span including the cantilever (IRC R507.5)
        span_for_table = back + cantilever if is_last else back
        bsp_key = "DF#1" if (timber and b.species == "DF") else b.species
        if timber:
            allow_b, bgov = eng.timber_allowable_span(b.size, bsp_key, total_psf * max(trib, 36) / 12.0, repetitive=False)
            bnote = ""
        else:
            allow_b, table_b, bnote = eng.beam_allowable(b.size, b.species, max(span_for_table, 72), total_psf)
        posts, sp = _place_posts(length, allow_b, b.post_spacing_max_in)
        chk = (eng.check_timber_beam(b.size, bsp_key, max(trib, 36), sp, total_psf) if timber
               else eng.check_beam(b.size, b.species, span_for_table, sp, total_psf))
        if bnote:
            chk.note = (chk.note + "; " if chk.note else "") + bnote
        from .catalog import post_cap, TIMBER_CAP
        cap = TIMBER_CAP.get(fr.post_size, "CCQ88SDS2.5") if timber else post_cap(fr.post_size, b.size)
        x0 = BEAM_HOLD_IN if b.kind == "drop" else (0.0 if front_flush else rim_t)
        beams.append(BeamLayout(b.kind, b.size, b.species, plies, bwid, bdep, cl, length, x0, [x0 + p for p in posts], sp, back, cantilever, trib, chk, cap,
                                label=f"{'DROP' if b.kind == 'drop' else ('FRONT FLUSH' if front_flush else 'FLUSH')} {b.size} {b.species}"))
        n_posts += len(posts)
        worst_load = max(worst_load, eng.footing_load_lb(sp if sp else length, trib, total_psf))
        prev_support = cl
    if not cls:
        notes.append("no beam — joists span ledger to front rim; front rim must be carried (posts under a flush front beam)")
        joist_checks.append(eng.check_timber_joist(jsize, jsp_key, spacing, joist_len, total_psf) if timber
                            else eng.check_joist(jsize, jsp, spacing, joist_len, total_psf))

    # ---- blocking
    rows = 1 if timber else spec.blocking_rows
    block_y = []
    for bl in beams:
        if bl.kind == "drop":
            block_y.append(bl.cl_y)
    if timber:
        # a row wherever an unblocked run between supports (drop beam CL, flush beam face, wall/rim) would exceed 4'; none in the cantilever
        sups = [rear_t] + sorted(b.cl_y for b in beams)
        for a, bb in zip(sups, sups[1:]):
            n = int(math.ceil((bb - a) / BLOCK_MAX_SPACING - 1e-9)) - 1
            for k in range(1, n + 1):
                block_y.append(round(a + (bb - a) * k / (n + 1), 2))
        block_y = sorted(set(block_y))
    elif rows >= 2 and beams:
        # PVC: a second row mid back-span of the deepest bay
        deepest = max(beams, key=lambda b: b.back_span)
        block_y.append(deepest.cl_y - deepest.back_span / 2)
    if not block_y and joist_len > 96:
        block_y.append(rear_t + joist_len / 2)
    n_blocks = max(0, n_joists - 1)
    block_len = spacing - jb

    # ---- posts, footings
    post_b, _ = actual(fr.post_size)
    beam_depth = max([b.depth for b in beams], default=jd)
    dk = decking_facts(spec.decking.collection)
    drop = any(b.kind == "drop" for b in beams)
    standoff = {"diamond_pier": DP_STANDOFF, "concrete": CONC_STANDOFF, "caisson": CAISSON_STANDOFF}.get(fr.footing_type, CONC_STANDOFF)
    for bl in beams:
        bl.post_len = max(6.0, g.height_in - dk["thick"] - (jd if bl.kind == "drop" else 0.0) - bl.depth - standoff)
    post_len = max([bl.post_len for bl in beams], default=max(6.0, g.height_in - dk["thick"] - jd - standoff))
    if timber:
        cap_post = eng.timber_post_capacity_lb(fr.post_size, "DF#1", post_len)
        ph_ok = (worst_load <= cap_post, cap_post)
    else:
        ph_ok = eng.post_ok(fr.post_size, post_len)
    cap_lb = FOOTING_CAPACITY_LB.get(fr.footing_model, 0) if fr.footing_type == "diamond_pier" else 0
    if fr.footing_type == "concrete":
        dia = eng.concrete_footing_diameter(worst_load, spec.site.soil_bearing_psf)
        depth = spec.site.frost_depth_in + 6
    elif fr.footing_type == "caisson":
        dia = float(fr.caisson_dia_in)
        depth = float(fr.caisson_depth_in) if fr.caisson_depth_in else spec.site.frost_depth_in + 2
        cap_lb = math.pi * (dia / 24) ** 2 * spec.site.soil_bearing_psf + math.pi * dia / 12 * depth / 12 * 400.0   # end bearing + ~400 psf skin friction (estimate; engineer sizes)
    else:
        dia, depth = 0.0, 50.0
    model = fr.footing_model if fr.footing_type == "diamond_pier" else fr.footing_type
    if fr.footing_type == "diamond_pier" and worst_load > cap_lb:
        if worst_load <= FOOTING_CAPACITY_LB["DP-75/63"]:
            model = "DP-75/63"; cap_lb = FOOTING_CAPACITY_LB[model]
            notes.append(f"post load {worst_load:,.0f} lb exceeds DP-50/50 (3,300 lb) — upgraded to DP-75/63")
        else:
            notes.append(f"post load {worst_load:,.0f} lb exceeds Diamond Pier capacity — add posts (shorter beam spans) or switch to concrete piers")

    # ---- connectors
    n_end_supports = 2  # ledger/rear rim + front rim
    hangers_single = n_joists * 2 if ledger else n_joists * 2
    for bl in beams:
        if bl.kind == "flush":
            near_front = abs(bl.cl_y - (D - front_t / 2)) < 1.0
            if not near_front:
                hangers_single += n_joists * 2       # joists hang both sides of a mid flush beam
    hangers_double = 0 if timber else 2 * 2           # each 2-ply side rim hangs in a HUCQ at both ends (timber rims are single 4x: HU hangers)
    if timber:
        hangers_single += 2 * 2                       # the two 4x side rims hang in HU hangers at both ends
    h25 = sum((n_joists + 2) for bl in beams if bl.kind == "drop")
    fl = FrameLayout(W, D, jsize, jsp, spacing, joist_len, joist_x, pf_x, ledger, rim_plies, beams, block_y, n_blocks, block_len,
                     joist_checks, fr.post_size, post_len, ph_ok, n_posts, fr.footing_type, model, worst_load, cap_lb, dia, depth,
                     total_psf, load_note, joist_bays, hangers_single, hangers_double, h25, notes)
    return fl


# ================================================================== railing
def _split_run(total_ctc: float, panel_max_cut: float, post_w: float, allow: float) -> int:
    max_ctc = panel_max_cut + post_w + 2 * allow
    return max(1, int(math.ceil(total_ctc / max_ctc - 1e-9)))


def rail_layout(spec: DeckSpec, W: float, D: float, extra_openings: List[RailOpening]) -> Optional[RailLayout]:
    r = spec.railing
    if not r.system or r.system.lower() == "none" or not r.sides:
        return None
    sysd = RAIL_SYSTEMS.get(r.system, RAIL_SYSTEMS["Fulton"])
    panels = sysd["panels"]           # stock -> max cut length
    post_w, allow = sysd["post_w"], sysd["bracket_allow"]
    RP = RAIL_POST_INSET
    openings = list(r.openings) + list(extra_openings)
    posts: List[RailPost] = []
    sections: List[RailSection] = []
    notes = []
    rail_lf = 0.0
    perim = 0.0

    def add_post(x, y, kind, tag):
        for p in posts:
            if abs(p.x - x) < 0.6 and abs(p.y - y) < 0.6:
                if kind == "CORNER" or p.kind == "CORNER":
                    p.kind = "CORNER"
                return p
        p = RailPost(round(x, 2), round(y, 2), kind, tag); posts.append(p); return p

    def build_run(side: str, start: float, end: float, to_xy, corner_at_end: bool, corner_at_start: bool):
        """start/end are along-the-run coordinates (from the house for sides, from the left face for the front)."""
        nonlocal rail_lf, perim
        perim += (end - start)
        ops = sorted([o for o in openings if o.side == side], key=lambda o: o.start_in)
        segs = []
        cur = start
        for o in ops:
            a, b = max(start, o.start_in), min(end, o.start_in + o.length_in)
            if b > cur:
                if a > cur + 1:
                    segs.append((cur, a))
                cur = b
        if end > cur + 1:
            segs.append((cur, end))
        for si, (a, b) in enumerate(segs):
            # post centres at the segment ends, inset RP from the frame face at run ends and at openings
            p0, p1 = a + RP, b - RP          # post pocket sits inside the rail section, never in the opening
            p0 = max(RP, min(p0, end - RP)); p1 = max(RP, min(p1, end - RP))
            if p1 - p0 < 12:
                continue
            k0 = "CORNER" if (abs(a - start) < 0.01 and corner_at_start) else "END"
            k1 = "CORNER" if (abs(b - end) < 0.01 and corner_at_end) else "END"
            n = _split_run(p1 - p0, max(panels.values()), post_w, allow)
            ctc = (p1 - p0) / n
            xs = [p0 + i * ctc for i in range(n + 1)]
            for i, s in enumerate(xs):
                kind = k0 if i == 0 else k1 if i == n else "LINE"
                add_post(*to_xy(s), kind, f"{side} {i+1}")
            cut = ctc - post_w - 2 * allow
            stock = next((st for st, mx in sorted(panels.items()) if cut <= mx + 1e-6), max(panels))
            for _ in range(n):
                sections.append(RailSection(side, round(ctc, 2), stock, round(cut, 2)))
            rail_lf += (b - a)

    if "left" in r.sides:
        build_run("left", 0.0, D, lambda s: (RP, s), corner_at_end="front" in r.sides, corner_at_start=False)
    if "right" in r.sides:
        build_run("right", 0.0, D, lambda s: (W - RP, s), corner_at_end="front" in r.sides, corner_at_start=False)
    if "front" in r.sides:
        build_run("front", 0.0, W, lambda s: (s, D - RP), corner_at_end="right" in r.sides, corner_at_start="left" in r.sides)
    if "rear" in r.sides:   # freestanding decks
        build_run("rear", 0.0, W, lambda s: (s, RP), corner_at_end="right" in r.sides, corner_at_start="left" in r.sides)
    return RailLayout(r.system, r.color, r.height_in, posts, sections, round(rail_lf / 12.0), round(perim / 12.0, 1), openings, notes)


def rail_layout_edges(spec: DeckSpec, edges: List[Edge], stair_openings: List[RailOpening], forced_x: Optional[List[float]] = None) -> Optional[RailLayout]:
    """Rail along named outline edges (multi-zone plans). Posts at the ends of every selected edge and evenly between at
    the system's max post spacing; a post shared by two selected edges is a CORNER."""
    r = spec.railing
    if not r.system or r.system.lower() == "none":
        return None
    sysd = RAIL_SYSTEMS.get(r.system, RAIL_SYSTEMS["Fulton"])
    panels, post_w, allow = sysd["panels"], sysd["post_w"], sysd["bracket_allow"]
    max_ctc = sysd.get("max_ctc", max(panels.values()) + post_w + 2 * allow)
    RP = RAIL_POST_INSET
    exposed = [e for e in edges if e.exposed]
    if r.edges:
        sel = [e for e in exposed if e.name in r.edges]
        missing = set(r.edges) - {e.name for e in exposed}
    else:
        sel, missing = exposed, set()
    # collinear neighbours (a zone front continuing straight into the next) are one run
    runs: List[Edge] = []
    for e in sel:
        if runs:
            q = runs[-1]
            same_dir = abs((q.x1 - q.x0) * (e.y1 - e.y0) - (q.y1 - q.y0) * (e.x1 - e.x0)) < 1e-6
            if same_dir and abs(q.x1 - e.x0) < 0.6 and abs(q.y1 - e.y0) < 0.6:
                runs[-1] = Edge(q.name + "+" + e.name.split(":")[-1], q.x0, q.y0, e.x1, e.y1, True)
                continue
        runs.append(Edge(e.name, e.x0, e.y0, e.x1, e.y1, e.exposed))
    sel = runs
    posts: List[RailPost] = []
    sections: List[RailSection] = []
    notes = [f"rail edge '{m}' not on the outline — edges are: " + ", ".join(e.name for e in exposed) for m in sorted(missing)]
    unrailed = [e for e in exposed if r.edges and e.name not in r.edges]
    for e in unrailed:
        notes.append(f"no rail on {e.name} ({ftin(e.length)}) by selection")
    rail_lf = 0.0

    def add_post(x, y, kind, tag):
        for p in posts:
            if abs(p.x - x) < 0.6 and abs(p.y - y) < 0.6:
                p.kind = "CORNER"
                return p
        p = RailPost(round(x, 2), round(y, 2), kind, tag); posts.append(p); return p

    for e in sel:
        L = e.length
        ux, uy = (e.x1 - e.x0) / L, (e.y1 - e.y0) / L
        # inset the post line RP from the frame face (perpendicular, toward the deck): outline runs clockwise from the left end
        nx, ny = uy, -ux          # inward normal: the outline runs clockwise (left end down, fronts left->right, right end up)
        ops = sorted([o for o in list(r.openings) + stair_openings if o.side == e.name or o.side in e.name.replace("+", ",front:").split(",")], key=lambda o: o.start_in)
        segs, cur = [], 0.0
        house_based_flip = abs(e.x1 - e.x0) < 0.01 and e.y1 < e.y0     # an end edge that runs front -> wall: openings are given from the house face
        if house_based_flip:
            ops = sorted(ops, key=lambda o: L - (o.start_in + o.length_in))
        for o in ops:
            if house_based_flip:
                a, b = max(0.0, L - (o.start_in + o.length_in)), min(L, L - o.start_in)
            else:
                a, b = max(0.0, o.start_in), min(L, o.start_in + o.length_in)
            if a > cur + 1:
                segs.append((cur, a))
            cur = max(cur, b)
        if L > cur + 1:
            segs.append((cur, L))
        for a, b in segs:
            p0, p1 = a + RP, b - RP
            if p1 - p0 < 12:
                continue
            # fixed posts: segment ends + any divider line that falls on this run (posts on the divider lines)
            fixed = [p0, p1]
            if forced_x and abs(uy) < 1e-6:            # a run along the front: t is x
                fixed += [fx - e.x0 for fx in forced_x if p0 + 12 < fx - e.x0 < p1 - 12]
            fixed = sorted(set(round(v, 3) for v in fixed))
            ts = []
            for fa, fb in zip(fixed, fixed[1:]):
                n = max(1, int(math.ceil((fb - fa) / max_ctc - 1e-9)))
                ts += [fa + (fb - fa) * k / n for k in range(n)]
            ts.append(fixed[-1])
            for i, t in enumerate(ts):
                kind = "END" if i in (0, len(ts) - 1) else "LINE"
                add_post(e.x0 + ux * t + nx * RP, e.y0 + uy * t + ny * RP, kind, f"{e.name} {i + 1}")
            for fa, fb in zip(ts, ts[1:]):
                ctc = fb - fa
                cut = ctc - post_w - 2 * allow
                stock = next((st for st, mx in sorted(panels.items()) if cut <= mx + 1e-6), max(panels))
                sections.append(RailSection(e.name, round(ctc, 2), stock, round(cut, 2)))
            rail_lf += (b - a)
    perim = sum(e.length for e in exposed)
    return RailLayout(r.system, r.color, r.height_in, posts, sections, round(rail_lf / 12.0, 1), round(perim / 12.0, 1),
                      list(r.openings) + stair_openings, notes)


def outline_edges(zones: List[ZoneLayout], spec: DeckSpec) -> List[Edge]:
    """Outer outline of a multi-zone plan, left to right facing the house: left end, then for each zone its front and
    the step to the next zone's front, then the right end. Ends along a privacy wall are not exposed."""
    edges: List[Edge] = []
    zl = spec.zone_list
    z0 = zones[0]
    f0 = z0.wall_y + z0.D
    edges.append(Edge("end:left", z0.x0, z0.wall_y, z0.x0, f0, exposed=not zl[0].privacy_wall))
    for i, z in enumerate(zones):
        fy = z.wall_y + z.D
        edges.append(Edge(f"front:{z.name}", z.x0, fy, z.x0 + z.W, fy))
        if i + 1 < len(zones):
            nz = zones[i + 1]
            nfy = nz.wall_y + nz.D
            if abs(nfy - fy) > 0.5:
                edges.append(Edge(f"step:{z.name}-{nz.name}", z.x0 + z.W, fy, z.x0 + z.W, nfy))
    zn = zones[-1]
    fn = zn.wall_y + zn.D
    edges.append(Edge("end:right", zn.x0 + zn.W, fn, zn.x0 + zn.W, zn.wall_y, exposed=not zl[-1].privacy_wall))
    # freestanding zones: the wall line is an open edge too (right to left, closing the clockwise outline)
    for z, zz in zip(reversed(zones), reversed(zl)):
        if zz.freestanding:
            edges.append(Edge(f"wall:{z.name}", z.x0 + z.W, z.wall_y, z.x0, z.wall_y, exposed=True))
    return edges


# ================================================================== stairs
def stair_layouts(spec: DeckSpec, W: float, D: float, dkl: DeckingLayout) -> List[StairLayout]:
    out = []
    f = decking_facts(spec.decking.collection)
    composite = f["material"] != "Wood"
    tread_w = 2 * dkl.bw + dkl.gap + NOSE          # two deck boards + gap + nosing over the riser
    for s in spec.stairs:
        rise = s.total_rise_in if s.total_rise_in else spec.geometry.height_in
        geo = eng.stair_geometry(rise, s.width_in, composite, tread_w)
        pieces_per_board = max(1, int(math.floor(144 / (s.width_in + 0.25))))
        tread_pieces = geo.treads * 2
        riser_pieces = geo.risers if s.closed_risers else 0
        # stair rail: one section per side along the slope
        slope_len = math.hypot(geo.total_run_in, geo.total_rise_in - geo.riser_in)
        sysd = RAIL_SYSTEMS.get(spec.railing.system, RAIL_SYSTEMS["Fulton"])
        secs = []
        n = max(1, int(math.ceil(slope_len / (max(sysd["panels"].values()) + 2))))
        for _ in range(s.rails):
            for _ in range(n):
                cut = slope_len / n - sysd["post_w"] - 2 * sysd["bracket_allow"]
                stock = next((st for st, mx in sorted(sysd["panels"].items()) if cut <= mx + 1e-6), max(sysd["panels"]))
                secs.append(RailSection("stair " + s.side, round(slope_len / n, 2), stock, round(cut, 2), kind="stair"))
        stair_posts = s.rails * (n + 1) if s.rails else 0
        pos = s.position_in if s.position_in is not None else ((W - s.width_in) / 2 if s.side == "front" else (0.0 if s.side.startswith("step:") else (D - s.width_in - 12)))
        opening = RailOpening(s.side, pos, s.width_in, f"stair {s.width_in:.0f}\" wide")
        notes = list(geo.notes)
        if geo.handrail_required:
            notes.append(f"{geo.risers} risers — graspable handrail 34–38\" on at least one side (IRC R311.7.8)")
        mid = s.mid_support if s.mid_support is not None else geo.total_run_in > 72.0
        if mid:
            notes.append(f"stringer run {geo.total_run_in / 12:.1f}' — carrier beam on two {spec.framing.post_size} posts and footings at mid-run under the stringers")
        out.append(StairLayout(s.side, s.width_in, geo, 2, tread_pieces, riser_pieces, geo.stringers, geo.stringer_stock_ft, s.rails, secs, stair_posts,
                               s.landing, opening, notes, mid, round(geo.total_run_in / 2.0, 1) if mid else 0.0))
    return out


# ================================================================== beam lines across zones
def _place_posts_line(x0: float, x1: float, boundaries: List[float], allow_by_seg: List[float], end_in: float) -> List[float]:
    """Posts end_in from each end, at every zone boundary, then evenly within each segment at or under that segment's allowable span."""
    fixed = [x0 + end_in] + [b for b in boundaries if x0 + end_in + 12 < b < x1 - end_in - 12] + [x1 - end_in]
    fixed = sorted(set(round(v, 3) for v in fixed))
    out = []
    for i, (a, b) in enumerate(zip(fixed, fixed[1:])):
        allow = allow_by_seg[min(i, len(allow_by_seg) - 1)]
        n = max(1, int(math.ceil((b - a) / allow - 1e-9)))
        out += [a + (b - a) * k / n for k in range(n)]
    out.append(fixed[-1])
    return out


def build_beam_lines(spec: DeckSpec, zl: List[ZoneLayout]) -> List[BeamLine]:
    from .catalog import post_cap, TIMBER_CAP
    timber = spec.is_timber
    lines: List[BeamLine] = []
    # group per-zone beams by (kind, size, species, offset from the front) and merge adjacent zones
    used = set()
    for zi, z in enumerate(zl):
        front = z.wall_y + z.D
        for bi, b in enumerate(z.frame.beams):
            if (zi, bi) in used:
                continue
            key = (b.kind, b.size, b.species, round(z.wall_y + b.cl_y, 1))     # absolute CL y: only collinear beams merge into one line
            members = [(zi, bi, z, b)]
            used.add((zi, bi))
            zj = zi + 1
            while zj < len(zl):
                zz = zl[zj]
                m = next(((zj, bj, zz, bb) for bj, bb in enumerate(zz.frame.beams)
                          if (zj, bj) not in used and (bb.kind, bb.size, bb.species, round(zz.wall_y + bb.cl_y, 1)) == key), None)
                if not m:
                    break
                members.append(m); used.add((m[0], m[1])); zj += 1
            first, last = members[0][2], members[-1][2]
            hold = BEAM_HOLD_IN if b.kind == "drop" else first.frame.rim_plies * actual(first.frame.joist_size)[0]
            x0 = first.x0 + hold
            x1 = last.x0 + last.W - hold
            boundaries = [m[2].x0 for m in members[1:]]
            allow_by_seg = [m[3].check.allowable_in for m in members]
            end_in = 18.0 if timber else POST_END_OVERHANG
            posts = _place_posts_line(x0, x1, boundaries, allow_by_seg, end_in)
            # zone of each post (boundary posts belong to the zone on the left) and its load
            pz, loads = [], []
            for i, px in enumerate(posts):
                zone = next((m[2] for m in members if m[2].x0 <= px <= m[2].x0 + m[2].W + 0.01), members[-1][2])
                bl = next(m[3] for m in members if m[2] is zone)
                left = (px - posts[i - 1]) / 2 if i > 0 else (px - x0)
                right = (posts[i + 1] - px) / 2 if i < len(posts) - 1 else (x1 - px)
                pz.append(zone.name)
                loads.append((left + right) / 12.0 * bl.trib_depth / 12.0 * zone.frame.total_psf)
            # pieces: extend across posts while a piece stays within 16' (timber) / 20' (dimensional); splice over a post
            max_piece = 192.0 if timber else 240.0
            pieces, a = [], x0
            for px in posts[1:]:
                if px - a > max_piece:
                    # splice at the previous post
                    prev = max(q for q in posts if q < px and q - a <= max_piece)
                    pieces.append((a, prev)); a = prev
            pieces.append((a, x1))
            if timber:
                cap_mid, cap_end = TIMBER_CAP.get(spec.framing.post_size, ("CCQ68SDS2.5", "ECCQ68SDS2.5"))
            else:
                cap_mid = cap_end = post_cap(spec.framing.post_size, b.size)
            plies, nom, bw, bd = parse_beam(b.size)
            lines.append(BeamLine(b.kind, b.size, b.species, plies, bw, bd, key[3],
                                  x0, x1, [m[2].name for m in members], posts, pz, loads, b.post_len, pieces, cap_mid, cap_end,
                                  label=f"{'DROP' if b.kind == 'drop' else 'FLUSH'} {b.size} {b.species} " + "+".join(m[2].name for m in members)))
    # write the line results back onto the zone frames (posts, worst load) so per-zone sums stay right
    for z in zl:
        z.frame.n_posts = 0
        z.frame.footing_load_lb = 0.0
    for ln in lines:
        for zn, ld in zip(ln.post_zone, ln.post_loads):
            z = next(q for q in zl if q.name == zn)
            z.frame.n_posts += 1
            z.frame.footing_load_lb = max(z.frame.footing_load_lb, ld)
    for z in zl:
        fr = z.frame
        if fr.footing_type == "diamond_pier" and fr.footing_load_lb > fr.footing_capacity_lb and fr.footing_load_lb <= FOOTING_CAPACITY_LB["DP-75/63"]:
            fr.footing_model = "DP-75/63"; fr.footing_capacity_lb = FOOTING_CAPACITY_LB["DP-75/63"]
    return lines


def build_dividers(spec: DeckSpec, zl: List[ZoneLayout], max_run_in: float = 192.0) -> List[Tuple[float, float, str]]:
    """Divider boards: one on every zone boundary (to the shallower zone's wall) and mid-zone splits so no field run is
    longer than a 16' board. Returns (x, length from the front edge, label)."""
    out = []
    if not spec.decking.dividers:
        return out
    for a, b in zip(zl, zl[1:]):
        Ld = min(a.wall_y + a.D, b.wall_y + b.D) - max(a.wall_y, b.wall_y)
        out.append((b.x0, Ld, f"D{a.name}/{b.name}"))
    for z in zl:
        k = int(math.ceil(z.W / max_run_in - 1e-9))
        for i in range(1, k):
            out.append((z.x0 + z.W * i / k, z.D, f"D{z.name}{i}"))
    return sorted(out)


# ================================================================== whole layout
def _floor_to(x: float, step: float) -> float:
    return math.floor(x / step + 1e-9) * step


def frame_from_nominal(nom_w: float, nom_d: float, bw: float, gap: float, fascia_t: float, pf: bool, direction: str) -> Tuple[float, float, int, str]:
    """GSX rule: a "12x16 deck" is 12' x 16' MAX over the fascia. Size the frame down so every field board is a full
    board and the field boards cut to a clean length. Returns (W, D, rows, note)."""
    edge = fascia_t + (NOSE if fascia_t else 0.0)
    if direction == "parallel":
        # width: field board length rounded down to a whole inch (Jason Ct: 12' -> 11'-0" field boards, 11'-9" frame)
        deck_w_max = nom_w
        field = _floor_to(deck_w_max - (2 * (bw + gap) if pf else 0.0), 1.0)   # borders sit inside the nominal; fascia is under the nose
        W = round((field + (2 * (bw + gap) if pf else 0.0) - 2 * edge) * 16) / 16.0   # to 1/16"
        # depth: whole rows under the nominal, front border on top, frame rounded down to 1/2"
        rows = int(math.floor((nom_d - (bw if pf else 0.0) - gap) / (bw + gap) + 1e-9))
        D = _floor_to(gap + rows * (bw + gap) + (bw if pf else 0.0) - edge, 0.5)
        note = (f"nominal {ftin(nom_w)} x {ftin(nom_d)} -> frame {ftin(W)} x {ftin(D)}: field boards cut to {ftin(field)}, "
                f"{rows} full rows, deck over fascia {ftin(W + 2 * edge)} x {ftin(D + edge)}")
    else:
        rows = int(math.floor((nom_w - (2 * bw if pf else 0.0) - gap) / (bw + gap) + 1e-9))
        W = _floor_to(gap + rows * (bw + gap) + (2 * bw if pf else 0.0) - 2 * edge, 0.5)
        D = _floor_to(nom_d - edge, 0.5)
        note = f"nominal {ftin(nom_w)} x {ftin(nom_d)} -> frame {ftin(W)} x {ftin(D)}: {rows} full boards across, boards run out from the house"
    return W, D, rows, note


def build_layout(spec: DeckSpec) -> Layout:
    g = spec.geometry
    f = decking_facts(spec.decking.collection)
    gap = spec.deck_gap
    fas_t = FASCIA[f["material"]]["thick"] if spec.decking.fascia else 0.0
    notes = []
    if g.zones:
        # ---- multi-zone: zone dimensions are frame dimensions as drawn; each zone framed on its own wall
        zl: List[ZoneLayout] = []
        x = 0.0
        for z in g.zones:
            W, D = float(z.width_in), float(z.depth_in)
            tub = bool(spec.extras.hot_tub and (spec.extras.hot_tub_zone in (None, "", z.name)))
            fr = frame_layout(spec, W, D, hot_tub=tub, zone=z.name)
            dk = decking_layout(spec, W, D, len(fr.joist_x) + len(fr.pf_x))
            zl.append(ZoneLayout(z.name, z.label, x, -float(z.wall_offset_in), W, D, fr, dk, tub))
            x += W
        edges = outline_edges(zl, spec)
        deepest = max(zl, key=lambda q: q.D)
        st = stair_layouts(spec, deepest.W, deepest.D, deepest.decking)
        lines = build_beam_lines(spec, zl)
        divs = build_dividers(spec, zl)
        rl = rail_layout_edges(spec, edges, [q.opening for q in st], forced_x=[d[0] for d in divs])
        notes.append(f"{len(zl)} zones, {sum(q.W for q in zl) / 12:.1f}' along the house, outline "
                     + " · ".join(f"{e.name} {ftin(e.length)}" for e in edges if e.exposed))
        for ln in lines:
            notes.append(f"{ln.label}: {ftin(ln.length)} long, {ln.n_posts} posts at " + " / ".join(ftin(px) for px in ln.posts_x)
                         + (f"; pieces " + " · ".join(ftin(b - a) for a, b in ln.pieces) if len(ln.pieces) > 1 else ""))
        wall_lf = sum(q.W for q in zl if q.frame.ledger) + sum(abs(a.wall_y - b.wall_y) for a, b in zip(zl, zl[1:]) if a.frame.ledger and b.frame.ledger)
        L = Layout(spec, zl[0].frame, zl[0].decking, rl, st, x, deepest.D, notes, zl, edges, True, lines, divs, wall_lf)
        return L
    W, D = float(g.width_in), float(g.depth_in)
    if g.size_mode == "nominal":
        W, D, rows, note = frame_from_nominal(W, D, f["width"], gap, fas_t, g.picture_frame, g.board_direction)
        notes.append(note)
    elif g.board_direction == "parallel":
        D2, rows, dev, note = size_frame_to_boards(D, f["width"], gap, fas_t, g.fit_frame_to_boards)
        notes.append(note)
        D = D2
    fr = frame_layout(spec, W, D)
    n_bearing = len(fr.joist_x) + len(fr.pf_x)
    dk = decking_layout(spec, W, D, n_bearing)
    st = stair_layouts(spec, W, D, dk)
    rl = rail_layout(spec, W, D, [q.opening for q in st])
    zl = [ZoneLayout("A", "", 0.0, 0.0, W, D, fr, dk, bool(spec.extras.hot_tub))]
    edges = outline_edges(zl, spec)
    lines = [BeamLine(b.kind, b.size, b.species, b.plies, b.width, b.depth, b.cl_y, b.x0, b.x0 + b.length, ["A"], list(b.posts_x), ["A"] * len(b.posts_x),
                      [fr.footing_load_lb] * len(b.posts_x), b.post_len, [(b.x0, b.x0 + b.length)], b.cap, b.cap, b.label) for b in fr.beams]
    return Layout(spec, fr, dk, rl, st, W, D, notes, zl, edges, False, lines, [], W if fr.ledger else 0.0)
