"""Turn a DeckSpec into geometry: where every joist, rim, beam, post, footing, board, rail post and stringer goes.
All numbers are inches in the plan convention documented in spec.py."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import engineering as eng
from .catalog import (rail_system_for, DECKING, FASCIA, NOSE, RAIL_SYSTEMS, RISER, STOCK_LENGTHS_FT, actual, decking_facts,
                      parse_beam, FOOTING_CAPACITY_LB, pier_capacity_lb)
from .spec import DeckSpec, RailOpening
from .units import ftin

PF_INSET = 5.25       # picture-frame joist center from the frame face for 2x framing (1-1/2" gap inboard of a double rim)
RIM_PLY = 1.5
CAISSON_STANDOFF = 7.0  # caisson 6" above grade + 1" standoff base (Eagle's Nest: post = 96 - 1 - 9.25 - 11.5 - 7 = 67.25")
OVERHANG_NO_FASCIA = 1.5   # boards overhang the exposed rim 1-1/2" when there is no fascia (Eagle's Nest)
BLOCK_MAX_SPACING = 48.0   # timber frames: a blocking row so no unblocked joist run between supports exceeds 4' 
LEDGER_T = 1.5
RAIL_POST_INSET = 2.5 # 2" Fulton post against the inside of the OUTER rim ply -> center 2.5" in from the frame face
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
    cl_y: float                # centerline from the house face
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
    # the rail layouts set .roof = (x, y) of the roof post (an attribute, not a field) where a louvered-roof post IS the rail post


@dataclass
class RailSection:
    side: str
    ctc: float
    panel_stock_in: int
    cut_len: float
    kind: str = "level"
    p0: Optional[Tuple[float, float]] = None     # the two posts that carry this section (inches, plan frame) when the layout knows them
    p1: Optional[Tuple[float, float]] = None


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
    flight_rails: List[int] = field(default_factory=list)      # rail sides per flight, top down
    landing_sections: List[RailSection] = field(default_factory=list)   # level guard on the landings' open sides
    landing_posts: int = 0
    landing_rail_lf: float = 0.0
    carrier_flights: List[int] = field(default_factory=list)   # flights (top down) that get a mid-run carrier on two posts
    carrier_fracs: List[float] = field(default_factory=lambda: [0.5])   # where the carriers sit along each such flight's run (0 = top riser)
    build: str = "stringers"            # "stringers" | "box" (framed 2x6 box step, no stringers)
    skirts: bool = False                 # stepped fascia skirts on both open sides
    inset: bool = False                  # recessed in a notch of the outline (layout.inset_notch): the notch's framing is counted with the frame
    notch: Optional[dict] = None         # the notch it sits in (inches, plan frame) — inset_notch() plus the posts and the foot carrier
    notch_posts: int = 0                 # posts at the notch's outer corners (header ends + the stringer-foot carrier), each on a footing
    notch_post_len: float = 0.0
    handrail: str = ""                   # "" | "each flight" | "guard posts" (Stair.handrail)
    handrail_side: str = "right"
    handrail_lf: float = 0.0             # graspable handrail length, all flights
    lands_on: str = ""                   # the composite part a "deck" landing stair lands on (set by composite.build_composite)
    option: str = ""                     # the option this stair belongs to (Stair.option)
    landing_footings: int = 0            # landing posts standing on the deck's own footings (Stair.landing_footing "deck"): 4 per landing
    landing_post_h: List[float] = field(default_factory=list)   # per landing: its frame bottom above the stair's foot (in)
    own_footings: int = 0                # posts on the stair's own 12" caissons (Stair.landing_footing "caisson12"): landing + carrier posts


@dataclass
class RowSeg:
    """One field board: a y band and an x run (inches, plan frame). Ends: border | divider | house | cut (angled house wall)."""
    y0: float
    y1: float
    x0: float
    x1: float
    panel: int
    rip: bool = False
    left: str = "border"
    right: str = "border"

    @property
    def length(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class FieldPlan:
    """Boards laid from the deck's true outline: rows on one grid per panel (the strips between breaker boards), every
    board one piece wall to border, borders on every exposed edge, breakers only where a run would exceed the longest stock."""
    rows: List[RowSeg] = field(default_factory=list)
    borders: List[Tuple[float, float, float, float, str]] = field(default_factory=list)   # exposed outline edges (x0, y0, x1, y1, kind) inches
    dividers: List[Tuple[float, float, float, str]] = field(default_factory=list)         # (x, y_lo, y_hi, label) inches
    panels: List[Tuple[float, float, int, float]] = field(default_factory=list)           # (x0, x1, rows, y_top)
    notes: List[str] = field(default_factory=list)
    dropped: int = 0
    dropped_at: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return max((n for _, _, n, _ in self.panels), default=0)

    def summary(self) -> str:
        parts = [f"panel {i + 1} ({ftin(a)}–{ftin(b)}) {n} rows" for i, (a, b, n, _) in enumerate(self.panels)]
        rips = sum(1 for r in self.rows if r.rip)
        return "Rows per panel: " + " · ".join(parts) + (f" · {rips} ripped piece{'s' if rips != 1 else ''}" if rips else " · no rips") + (f" · {len(self.dividers)} breaker{'s' if len(self.dividers) != 1 else ''}" if self.dividers else " · no breakers")


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
    plan: Optional[FieldPlan] = None      # outline-laid decking (multi-zone plans with an outline and breakers)
    outline_edges: List[Edge] = field(default_factory=list)   # the outline polygon's sides ("edge:N") when the rail or a stair names them
    edge_posts: List["EdgePost"] = field(default_factory=list)   # posts under the rims (outline corners) carrying the front
    edge_post_len: float = 0.0

    @property
    def deck_sf(self) -> float:
        """Sold square footage: over the fascia when there is one (Jason Ct 187), frame area when the rim is exposed (Eagle's Nest 617.2)."""
        if not self.zones:
            return self.decking.sf
        if self.spec.geometry.outline:      # a true outline (curves, bay facets, notches): its polygon area is the sold square footage
            pts = [(float(x), float(y)) for x, y in self.spec.geometry.outline]
            a = 0.0
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
                a += x0 * y1 - x1 * y0
            return round(abs(a) / 2.0, 1)
        if self.spec.decking.fascia:
            return int(round(sum(z.decking.deck_w * z.decking.deck_d for z in self.zones) / 144.0))
        return round(sum(z.W * z.D for z in self.zones) / 144.0, 1)

    @property
    def outer_edge_lf(self) -> float:
        return round(sum(e.length for e in self.edges if e.exposed) / 12.0, 1)

    @property
    def stair_support_posts(self) -> int:
        return (sum(2 * max(1, len(st.carrier_flights)) * max(1, len(st.carrier_fracs)) for st in self.stairs if st.mid_support and not getattr(st, "own_footings", 0))
                + sum(getattr(st, "landing_footings", 0) for st in self.stairs if not getattr(st, "own_footings", 0)))   # landing posts on the deck's own footings
                                                                                                                         # (a stair on its own 12" caissons counts none here)

    @property
    def n_footings(self) -> int:
        """Every post that needs a footing: beam-line posts plus the mid-stair carrier posts and the landing posts on the deck's footings."""
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
    if k > 1 and spec.geometry.outline and direction == "parallel" and (dk.dividers or dk.divider_x_ft):
        notes.append(f"field run {ftin(field_len)} is over a {STOCK_LENGTHS_FT[-1]}' board: the outline plan lays it in panels between breaker boards, every board one piece (no butt joints)")
    elif k > 1:
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
    if f["material"] == "Composite" and f.get("profile") == "scalloped" and not f.get("cortex_ok"):
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
    if not ledger and not any((not b.zones) or (zone in b.zones) for b in declared):
        # freestanding with nothing declared for this zone: a rear drop beam 12" in from the rear rim face mirrors the front beam
        from .spec import Beam as _B
        rear = _B(kind="drop", size=declared[0].size if declared else ("6x12" if timber else "4x10"), species=declared[0].species if declared else "DF", setback_in=12.0)
        rear.position_in = 12.0 + parse_beam(rear.size)[2] / 2
        declared = [rear] + declared
        rear_auto = rear
    else:
        rear_auto = None
        if not ledger:
            notes.append("freestanding zone framed on its declared beam; no ledger" + (" — lateral bracing per the engineer" if spec.extras.engineered else ""))
    # a front flush beam IS the front rim: the frame's front thickness is the beam's width (a 7" (2)4x, not the 3" rim)
    for b in declared:
        if b.kind == "flush" and not (b.setback_in or 0) and b.position_in is None and (not zone or not b.zones or zone in b.zones):
            front_t = max(front_t, parse_beam(b.size)[2])
    joist_len = D - rear_t - front_t
    # resolve centerlines
    cls = []
    engineered = spec.extras.engineered
    for b in declared:
        if zone and b.zones and zone not in b.zones:
            continue
        plies, nom, bwid, bdep = parse_beam(b.size)
        if b.position_in is not None and (not zone or b is rear_auto):
            cl = float(b.position_in)
        elif b.kind == "flush":
            cl = D - (b.setback_in or 0.0) - (0.0 if (b.setback_in or 0) > 0 else max(front_t, bwid) / 2)   # flush: setback = CL back from the rim face; at the front its outer face is the frame face
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
    front_sup = bool(spec.framing.edge_posts_ft)      # the front rim stands on edge posts: the last span ends on it, no cantilever
    for idx, (cl, b) in enumerate(cls):
        plies, nom, bwid, bdep = parse_beam(b.size)
        is_last = idx == len(cls) - 1
        if b.kind == "flush" and abs(cl - (D - front_t / 2)) < 1.0:
            cantilever = 0.0
        elif front_sup and is_last:
            cantilever = 0.0
            fs_ = (D - front_t) - cl                  # the span from this beam to the rim on the edge posts
            if fs_ > 6:
                joist_checks.append(eng.check_timber_joist(jsize, jsp_key, spacing, fs_, total_psf) if timber
                                    else eng.check_joist(jsize, jsp, spacing, fs_, total_psf))
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
        nxt = (cls[idx + 1][0] - cl) if not is_last else (((D - front_t) - cl) if front_sup else 0.0)
        trib = back / 2 + (cantilever if (is_last and not front_sup) else nxt / 2)
        if not ledger and idx == 0:
            trib = nxt / 2 + (cl - 0)     # rear beam carries the rear overhang plus half the first span
        front_flush = b.kind == "flush" and abs(cl - (D - max(front_t, parse_beam(b.size)[2]) / 2)) < 1.0
        length = W - 2 * BEAM_HOLD_IN if b.kind == "drop" else (W if front_flush else W - 2 * rim_t)
        # beam span table: joist span including the cantilever (IRC R507.5)
        span_for_table = (max(back, nxt) if front_sup else back + cantilever) if is_last else back
        bsp_key = "DF#1" if (timber and b.species == "DF") else b.species
        if timber:
            allow_b, bgov = eng.timber_allowable_span(b.size, bsp_key, total_psf * max(trib, 36) / 12.0, repetitive=False)
            bnote = ""
        else:
            allow_b, table_b, bnote = eng.beam_allowable(b.size, b.species, max(span_for_table, 72), total_psf)
        posts, sp = _place_posts(length, allow_b, b.post_spacing_max_in)
        x0 = BEAM_HOLD_IN if b.kind == "drop" else (0.0 if (b.kind == "flush" and abs(cl - (D - front_t / 2)) < 1.0) else rim_t)
        if b.posts_x_ft:          # the owner placed the posts: positions from the left frame face
            posts = sorted(float(px) * 12 - x0 for px in b.posts_x_ft)
            sp = max([q - p_ for p_, q in zip(posts, posts[1:])] + [0.0])
            if len(posts) < 2 or sp > allow_b + 0.5:
                notes.append(f"{b.size} {b.species} beam: owner-placed posts give a {ftin(sp)} span against {ftin(allow_b)} allowable — engineer confirms")
        chk = (eng.check_timber_beam(b.size, bsp_key, max(trib, 36), sp, total_psf) if timber
               else eng.check_beam(b.size, b.species, span_for_table, sp, total_psf))
        if bnote and bnote not in (chk.note or ""):
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
        notes.append("no beam — joists span the ledger to the front rim, carried on the edge posts" if front_sup else
                     "no beam — joists span ledger to front rim; front rim must be carried (posts under a flush front beam)")
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
    standoff = {"diamond_pier": DP_STANDOFF, "concrete": CONC_STANDOFF, "caisson": CAISSON_STANDOFF, "existing": CAISSON_STANDOFF}.get(fr.footing_type, CONC_STANDOFF)
    if fr.footing_type == "caisson":            # the caisson top (framing.caisson_above_in, 6" default) + the 1" standoff base
        standoff = float(fr.caisson_above_in) + CAISSON_STANDOFF - 6.0
    for bl in beams:
        bl.post_len = max(6.0, g.height_in - dk["thick"] - (jd if bl.kind == "drop" else 0.0) - bl.depth - standoff)
    post_len = max([bl.post_len for bl in beams], default=max(6.0, g.height_in - dk["thick"] - jd - standoff))
    if timber:
        cap_post = eng.timber_post_capacity_lb(fr.post_size, "DF#1", post_len)
        ph_ok = (worst_load <= cap_post, cap_post)
    else:
        ph_ok = eng.post_ok(fr.post_size, post_len)
    cap_lb = pier_capacity_lb(fr.footing_model, spec.site.soil_bearing_psf) if fr.footing_type == "diamond_pier" else 0
    if fr.footing_type == "concrete":
        dia = eng.concrete_footing_diameter(worst_load, spec.site.soil_bearing_psf)
        depth = spec.site.frost_depth_in + 6
    elif fr.footing_type in ("caisson", "existing"):
        dia = float(fr.caisson_dia_in)
        depth = float(fr.caisson_depth_in) if fr.caisson_depth_in else spec.site.frost_depth_in + 2
        cap_lb = math.pi * (dia / 24) ** 2 * spec.site.soil_bearing_psf + math.pi * dia / 12 * depth / 12 * 400.0   # end bearing + ~400 psf skin friction (estimate; engineer sizes)
    else:
        dia, depth = 0.0, 50.0
    model = fr.footing_model if fr.footing_type == "diamond_pier" else fr.footing_type
    if fr.footing_type == "diamond_pier" and worst_load > cap_lb and spec.framing.footing_model_lock:
        notes.append(f"post load {worst_load:,.0f} lb exceeds {model} ({cap_lb:,.0f} lb) — the owner's pier model stays: add posts (shorter beam spans)")
    elif fr.footing_type == "diamond_pier" and worst_load > cap_lb:
        if worst_load <= pier_capacity_lb("DP-75/63", spec.site.soil_bearing_psf):
            model = "DP-75/63"; cap_lb = pier_capacity_lb(model, spec.site.soil_bearing_psf)
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
def _split_run(total_ctc: float, panel_max_cut: float, post_w: float, allow: float, ctc_cap: Optional[float] = None) -> int:
    max_ctc = panel_max_cut + post_w + 2 * allow
    if ctc_cap:                         # the maker's maximum post spacing (IRX: 96" c-c) governs when the panel would allow more
        max_ctc = min(max_ctc, ctc_cap)
    return max(1, int(math.ceil(total_ctc / max_ctc - 1e-9)))


def rail_layout(spec: DeckSpec, W: float, D: float, extra_openings: List[RailOpening],
                fixed_pts: Optional[List[Tuple[float, float, float]]] = None) -> Optional[RailLayout]:
    r = spec.railing
    if not r.system or r.system.lower() == "none" or not r.sides:
        return None
    sysd = rail_system_for(r)
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
            # post centers at the segment ends, inset RP from the frame face at run ends and at openings
            p0, p1 = a + RP, b - RP          # post pocket sits inside the rail section, never in the opening
            p0 = max(RP, min(p0, end - RP)); p1 = max(RP, min(p1, end - RP))
            # louvered-roof posts on this run's post line (louvered.rail_points): fixed rail posts; one within 14" of an end takes it
            roof_t, roof_id = {}, {}
            if fixed_pts:
                (ax_, ay_), (bx_, by_) = to_xy(0.0), to_xy(1.0)
                for fp in fixed_pts:
                    t_ = (fp[0] - ax_) * (bx_ - ax_) + (fp[1] - ay_) * (by_ - ay_)
                    w_ = float(fp[2]) if len(fp) > 2 else 6.0
                    if abs((fp[0] - ax_) * (by_ - ay_) - (fp[1] - ay_) * (bx_ - ax_)) <= w_ / 2 + 12.0 and p0 - 14 <= t_ <= p1 + 14:   # through it or within 12": it is the post there
                        roof_t[round(t_, 3)] = w_
                        roof_id[round(t_, 3)] = (round(fp[0], 1), round(fp[1], 1))
                for t_ in sorted(roof_t):
                    if abs(t_ - p0) <= 14:
                        p0 = t_
                    elif abs(t_ - p1) <= 14:
                        p1 = t_
            if p1 - p0 < 12:
                continue
            k0 = "CORNER" if (abs(a - start) < 0.01 and corner_at_start) else "END"
            k1 = "CORNER" if (abs(b - end) < 0.01 and corner_at_end) else "END"
            fixed = sorted({p0, p1} | {t_ for t_ in roof_t if p0 < t_ < p1})
            xs = []
            for fa, fb in zip(fixed, fixed[1:]):
                n = _split_run(fb - fa, max(panels.values()), post_w, allow, sysd.get("max_ctc"))
                ctc = (fb - fa) / n
                xs += [fa + i * ctc for i in range(n)]
                cut = ctc - post_w - 2 * allow - sum((w_ - post_w) / 2 for t_, w_ in roof_t.items() if min(abs(t_ - fa), abs(t_ - fb)) < 0.6)
                stock = next((st for st, mx in sorted(panels.items()) if cut <= mx + 1e-6), max(panels))
                for _ in range(n):
                    sections.append(RailSection(side, round(ctc, 2), stock, round(cut, 2)))
            xs.append(fixed[-1])
            n = len(xs) - 1
            for i, s in enumerate(xs):
                kind = k0 if i == 0 else k1 if i == n else "LINE"
                pp_ = add_post(*to_xy(s), kind, f"{side} {i+1}")
                hit = [t_ for t_ in roof_t if abs(s - t_) < 0.6]
                if hit:
                    pp_.roof = roof_id[hit[0]]
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


def rail_layout_edges(spec: DeckSpec, edges: List[Edge], stair_openings: List[RailOpening], forced_x: Optional[List[float]] = None,
                      fixed_pts: Optional[List[Tuple[float, float, float]]] = None) -> Optional[RailLayout]:
    """Rail along named outline edges (multi-zone plans). Posts at the ends of every selected edge and evenly between at
    the system's max post spacing; a post shared by two selected edges is a CORNER."""
    r = spec.railing
    if not r.system or r.system.lower() == "none":
        return None
    sysd = rail_system_for(r)
    panels, post_w, allow = sysd["panels"], sysd["post_w"], sysd["bracket_allow"]
    max_ctc = sysd.get("max_ctc", max(panels.values()) + post_w + 2 * allow)
    RP = RAIL_POST_INSET
    exposed = [e for e in edges if e.exposed]
    if r.existing_parapet:          # the parapet is the guard on every deck edge; the system is only for the stairs
        sel, missing = [], set()
    elif r.edges:
        sel = [e for e in exposed if e.name in r.edges]
        missing = set(r.edges) - {e.name for e in exposed}
    else:
        sel, missing = exposed, set()
    # collinear neighbors (a zone front continuing straight into the next) are one run
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

    def _inset_line(q):
        Lq = q.length; ux_, uy_ = (q.x1 - q.x0) / Lq, (q.y1 - q.y0) / Lq
        return q.x0 + uy_ * RP, q.y0 - ux_ * RP, ux_, uy_          # inward (uy, -ux), RP in

    def _corner_t(a_, b_):
        """Where the rail lines of two runs that share a corner meet, as a distance along b_ from its start (a 45-degree
        corner: 0.41 x RP; square: RP; an inside corner: negative). None when they don't share the corner."""
        if abs(a_.x1 - b_.x0) > 0.6 or abs(a_.y1 - b_.y0) > 0.6:
            return None
        px, py, ux_, uy_ = _inset_line(a_); qx, qy, vx, vy = _inset_line(b_)
        den = vx * uy_ - vy * ux_
        if abs(den) < 1e-9:
            return None
        return ((px - qx) * uy_ - (py - qy) * ux_) / den

    for ri, e in enumerate(sel):
        L = e.length
        ux, uy = (e.x1 - e.x0) / L, (e.y1 - e.y0) / L
        t_first = _corner_t(sel[ri - 1], e) if ri > 0 else None
        t_last = None
        if ri + 1 < len(sel):
            nb = sel[ri + 1]
            tb = _corner_t(e, nb)            # along nb from its start; the same point measured along e from e's end:
            if tb is not None:
                qx, qy, vx, vy = _inset_line(nb)
                cx_, cy_ = qx + vx * tb, qy + vy * tb
                px_, py_, _, _ = _inset_line(e)
                t_last = (cx_ - px_) * ux + (cy_ - py_) * uy
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
            p0 = (t_first if (t_first is not None and a < 0.5) else a + RP)
            p1 = (t_last if (t_last is not None and b > L - 0.5) else b - RP)
            # louvered-roof posts on this run's post line (louvered.rail_points): each is a fixed rail post, one within 14" of
            # a segment end takes that end's place; a divider post within 24" of one is dropped (the roof post is the post there)
            roof_t, roof_id = {}, {}
            for fp in (fixed_pts or []):
                t_ = (fp[0] - e.x0) * ux + (fp[1] - e.y0) * uy
                w_ = float(fp[2]) if len(fp) > 2 else 6.0
                if abs((fp[0] - e.x0) * nx + (fp[1] - e.y0) * ny - RP) <= w_ / 2 + 12.0 and p0 - 14 <= t_ <= p1 + 14:   # through it or within 12": it is the post there
                    roof_t[round(t_, 3)] = w_
                    roof_id[round(t_, 3)] = (round(fp[0], 1), round(fp[1], 1))
            for t_ in sorted(roof_t):
                if abs(t_ - p0) <= 14:
                    p0 = t_
                elif abs(t_ - p1) <= 14:
                    p1 = t_
            if p1 - p0 < 12:
                continue
            # fixed posts: segment ends + any divider line that falls on this run (posts on the divider lines)
            fixed = [p0, p1]
            if forced_x and abs(uy) < 1e-6:            # a run along the front: t is x
                fixed += [fx - e.x0 for fx in forced_x if p0 + 12 < fx - e.x0 < p1 - 12 and all(abs(fx - e.x0 - t_) >= 24 for t_ in roof_t)]
            fixed += [t_ for t_ in roof_t if p0 < t_ < p1]
            fixed = sorted(set(round(v, 3) for v in fixed))
            ts = []
            for fa, fb in zip(fixed, fixed[1:]):
                n = max(1, int(math.ceil((fb - fa) / max_ctc - 1e-9)))
                ts += [fa + (fb - fa) * k / n for k in range(n)]
            ts.append(fixed[-1])
            placed = []
            for i, t in enumerate(ts):
                kind = "END" if i in (0, len(ts) - 1) else "LINE"
                placed.append(add_post(e.x0 + ux * t + nx * RP, e.y0 + uy * t + ny * RP, kind, f"{e.name} {i + 1}"))
                hit = [t_ for t_ in roof_t if abs(t - t_) < 0.6]
                if hit:
                    placed[-1].roof = roof_id[hit[0]]      # which roof post (x, y): two runs ending in one corner post name the same one
            for (fa, fb), (pa, pb) in zip(zip(ts, ts[1:]), zip(placed, placed[1:])):
                ctc = fb - fa
                cut = ctc - post_w - 2 * allow - sum((w_ - post_w) / 2 for t_, w_ in roof_t.items() if min(abs(t_ - fa), abs(t_ - fb)) < 0.6)
                stock = next((st for st, mx in sorted(panels.items()) if cut <= mx + 1e-6), max(panels))
                sections.append(RailSection(e.name, round(ctc, 2), stock, round(cut, 2), p0=(pa.x, pa.y), p1=(pb.x, pb.y)))
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


def outline_poly_edges(spec: DeckSpec) -> List[Edge]:
    """Every side of the outline polygon as its own edge, "edge:1" .. "edge:N" in the polygon's order (inches). The polygon
    runs like the zone outline (left end toward the yard, fronts left to right, right end back to the house); sides on the
    house (inside a house block, on a house wall, or along the y = 0 wall line) are not exposed."""
    pts = [(float(x) * 12, float(y) * 12) for x, y in spec.geometry.outline]
    kinds = _edge_kinds(spec, pts)
    out = []
    for i, (a, b) in enumerate(zip(pts, pts[1:] + pts[:1])):
        on_wall = abs(a[1]) < 0.5 and abs(b[1]) < 0.5
        out.append(Edge(f"edge:{i + 1}", a[0], a[1], b[0], b[1], exposed=kinds[i] != "house" and not on_wall))
    return out


@dataclass
class OutlineFrame:
    """The frame of a polygon-outline deck as one continuous field (inches, plan frame): what the drawings show and
    what the takeoff counts. End supports: ledger | beam | rim | rim45 | bay45 (a 45-degree rim takes a skewed hanger)."""
    joists: List[Tuple[float, float, float, str, str, str]] = field(default_factory=list)    # (x, y_a, y_b, end_a, end_b, label)
    rims: List[Tuple[int, int, float, float, float, float]] = field(default_factory=list)     # (side index, ply, x0, y0, x1, y1) ply centerlines
    ledgers: List[Tuple[float, float, float, float]] = field(default_factory=list)            # ledger centerlines on the main wall
    ledger_blocks: List[Tuple[float, float, float, float]] = field(default_factory=list)
    blocks: List[Tuple[float, float, float, float, str]] = field(default_factory=list)        # blocking centerlines
    side_kind: List[str] = field(default_factory=list)                                        # per outline side
    notes: List[str] = field(default_factory=list)
    rim_to_ledger: int = 0                                                                     # doubled rim ends hung on a ledger
    rim_ledger: List[str] = field(default_factory=list)                                         # each of them by the angle it meets: square | skew45 | field
    notch_hangers: int = 0       # inset-stair notches: concealed-flange double hangers (trimmer ends, headers on the trimmer)
    notches: List[dict] = field(default_factory=list)   # per framed notch: side, trimmer (x, y_a, y_b, ends), headers, PF joist


def _col_cross(poly, x) -> List[Tuple[float, int]]:
    ys = []
    n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if (xa > x) != (xb > x):
            ys.append((ya + (x - xa) * (yb - ya) / (xb - xa), i))
    ys.sort()
    return ys


def _inset_inward(poly, d):
    """_inset_polygon with the inward side checked (the sign convention depends on the plan frame's handedness)."""
    q = _inset_polygon(poly, d)
    a0 = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1])))
    a1 = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(q, q[1:] + q[:1])))
    if a1 > a0 + 1e-6:                      # grew: offset the other way
        q = _inset_polygon(poly, [-v for v in d])
    return q


def outline_side_faces(spec: DeckSpec, edges: List["Edge"], rim_t: float, jb: float) -> Tuple[List[str], List[float]]:
    """Per outline side: what frames it (rim | rim45 | ledger | bayfront | bay45) and how far the framing's inside face
    sits from the line — a 2-ply rim on open sides, the ledger on the straight main wall, 1/2" off a bay front (the
    header beam stands off it), a 2-ply rim 1/2" off an angled bay face."""
    kinds = []
    bay_led = spec.geometry.bay_ledger
    for e in edges:
        horiz, vert = abs(e.y1 - e.y0) < 0.5, abs(e.x1 - e.x0) < 0.5
        if e.exposed:
            kinds.append("rim" if (horiz or vert) else "rim45")
        elif abs(e.y0) < 0.5 and abs(e.y1) < 0.5:
            kinds.append("ledger")
        elif horiz:
            kinds.append("ledger" if bay_led else "bayfront")
        else:
            kinds.append("ledger45" if bay_led else "bay45")       # a ledger on an angled bay face: joists land in skewed hangers
    face = {"rim": rim_t, "rim45": rim_t, "ledger": jb, "ledger45": jb, "bayfront": 0.5, "bay45": rim_t + 0.5}
    return kinds, [face[k] for k in kinds]


def outline_framing(spec: DeckSpec, L) -> Optional[OutlineFrame]:
    """One continuous joist field under a polygon outline: joists at each zone's layout positions (picture-frame joists
    only along the deck's own side edges, a pair of joists either side of every divider line), clipped to the outline
    inset by the rims / ledger, split at the flush beam lines; 2-ply mitered rims on every open side and 1/2" off any
    angled house face that cannot take a ledger (a cantilevered bay); the ledger on the straight main wall only; a ledger
    block where an angled rim dies into the main wall; blocking under every 45-degree picture-frame border."""
    if not getattr(L, "outline_edges", None) or not spec.geometry.outline:
        return None
    of = OutlineFrame()
    jb, jd = actual(spec.framing.joist_size)
    plies = L.zones[0].frame.rim_plies
    rim_t = plies * jb
    poly = [(float(x) * 12, float(y) * 12) for x, y in spec.geometry.outline]
    E = L.outline_edges
    n = len(poly)
    of.side_kind, faces = outline_side_faces(spec, E, rim_t, jb)
    face = dict(zip(of.side_kind, faces))
    ins = _inset_inward(poly, faces)
    # flush beam lines (absolute CL y, x range, width)
    beams = [(ln.y, ln.x0, ln.x1, ln.width) for ln in L.beam_lines if ln.kind == "flush"]
    # joist positions
    xs: List[Tuple[float, str]] = []
    last = len(L.zones) - 1
    for zi, z in enumerate(L.zones):
        xs += [(z.x0 + jx, "joist") for jx in z.frame.joist_x]
        if z.frame.pf_x:
            if zi == 0:
                xs.append((z.x0 + z.frame.pf_x[0], "PF joist"))
            if zi == last:
                xs.append((z.x0 + z.frame.pf_x[-1], "PF joist"))
    for dx, Ld, lab in (L.divider_x or []):
        xs += [(dx - jb, f"divider joist {lab}"), (dx + jb, f"divider joist {lab}")]
    xs.sort()
    for X, lab in xs:
        cr = _col_cross(ins, X)
        for (ya, ia), (yb, ib) in zip(cr[0::2], cr[1::2]):
            cuts = sorted((c - w / 2, c + w / 2) for c, bx0, bx1, w in beams if bx0 - 0.5 <= X <= bx1 + 0.5 and ya + 1.0 < c < yb - 1.0)
            ends = [(ya, of.side_kind[ia])]
            for lo, hi in cuts:
                ends += [(lo, "beam"), (hi, "beam")]
            ends.append((yb, of.side_kind[ib]))
            for (a, ea), (b, eb) in zip(ends[0::2], ends[1::2]):
                if b - a >= 4.0:
                    of.joists.append((X, a, b, ea, eb, lab))
    # rims: ply centerlines along every open side and every angled bay face (mitered: each ply its own inset polygon)
    for k in range(plies):
        off = {"rim": (k + 0.5) * jb, "rim45": (k + 0.5) * jb, "bay45": 0.5 + (k + 0.5) * jb, "ledger": 0.0, "ledger45": 0.0, "bayfront": 0.0}
        q = _inset_inward(poly, [off[t] for t in of.side_kind])
        for i in range(n):
            if of.side_kind[i] in ("rim", "rim45", "bay45"):
                (x0, y0), (x1, y1) = q[i], q[(i + 1) % n]
                of.rims.append((i, k, x0, y0, x1, y1))
    # ledger: centerline on the main wall between the neighboring rims' faces
    qL = _inset_inward(poly, [(jb / 2 if t in ("ledger", "ledger45") else face[t]) for t in of.side_kind])
    for i in range(n):
        if of.side_kind[i] in ("ledger", "ledger45"):
            (x0, y0), (x1, y1) = qL[i], qL[(i + 1) % n]
            of.ledgers.append((x0, y0, x1, y1))
    # a doubled rim that dies into a ledger hangs on it in a double hanger chosen by the angle the two meet at: square
    # (concealed flange), 45 degrees (skewed), anything else (a bay face at the house's own angle: field-skewable)
    for i in range(n):
        j = (i + 1) % n
        a, b = of.side_kind[i], of.side_kind[j]
        if not ({a, b} & {"rim", "rim45"} and {a, b} & {"ledger", "ledger45"}):
            continue
        (xa, ya), (xb, yb), (xc, yc) = poly[i], poly[j], poly[(j + 1) % n]
        ang = abs(math.degrees(math.atan2(yb - ya, xb - xa) - math.atan2(yc - yb, xc - xb))) % 180
        ang = min(ang, 180 - ang)                     # the acute angle between the rim and the ledger line
        of.rim_ledger.append("square" if ang > 87 else "skew45" if abs(ang - 45) <= 3 else "field")
    of.rim_to_ledger = len(of.rim_ledger)
    # an angled rim that dies into the main wall where no ledger runs (beside a bay): a 24" ledger block on the wall
    for i in range(n):
        j = (i + 1) % n
        a, b = of.side_kind[i], of.side_kind[j]
        vx, vy = poly[j]
        if abs(vy) < 0.5 and {a, b} == {"rim45", "bay45"}:
            of.ledger_blocks.append((vx, jb / 2, vx + 24.0, jb / 2))
            of.notes.append(f"angled rims meet the main wall at {ftin(vx)} beside the bay: a 24\" {spec.framing.joist_size} ledger block (3 LedgerLOKs, flashed) carries them in a skewed double hanger")
    # blocking under the 45-degree picture-frame borders: a line 1-1/2" inside the rim, one block per joist bay
    if spec.geometry.picture_frame:
        pf_off = rim_t + 1.5 + jb / 2
        qb = _inset_inward(poly, [(pf_off if t == "rim45" else face[t]) for t in of.side_kind])
        jx_all = sorted(X for X, lab in xs)
        for i in range(n):
            if of.side_kind[i] != "rim45":
                continue
            (x0, y0), (x1, y1) = qb[i], qb[(i + 1) % n]
            if x1 < x0:
                x0, y0, x1, y1 = x1, y1, x0, y0
            cuts = [x0] + [X for X in jx_all if x0 + 1.0 < X < x1 - 1.0] + [x1]
            for a, b in zip(cuts, cuts[1:]):
                if b - a < 2.0:
                    continue
                ya = y0 + (y1 - y0) * (a - x0) / (x1 - x0); yb = y0 + (y1 - y0) * (b - x0) / (x1 - x0)
                of.blocks.append((a, ya, b, yb, f"PF block side {i + 1}"))
    _frame_notches(spec, of, poly, ins, jb, plies)        # inset stairs: trimmer, headers, PF joist in the notch they sit in
    n_sk = sum((ea in ("rim45", "bay45")) + (eb in ("rim45", "bay45")) for _, _, _, ea, eb, _ in of.joists)
    n_bf = sum((ea == "ledger45") + (eb == "ledger45") for _, _, _, ea, eb, _ in of.joists)
    of.notes.append(f"outline frame: {len(of.joists)} joist pieces, {sum(b - a for _, a, b, *_ in of.joists) / 12:.0f} LF; "
                    f"{n_sk} joist ends on 45-degree rims (skewed hangers)" + (f", {n_bf} on the bay faces (field-skewable hangers)" if n_bf else "")
                    + f"; {len(of.blocks)} blocks under the angled borders")
    return of


# ================================================================== inset stairs: the notch, its framing, the step-face skirt
NOTCH_POST = "4x4"           # the inset-stair notch's corner posts (PT, on the stair base ledger; structure.md §5.2: 4x4 or 4x6)
SKIRT_GAP_BOTTOM = 0.25      # step-skirt panels stand 1/4" off the lower level's boards
SKIRT_GAP_TREAD = 0.125      # cheek panels stand 1/8" off the treads they meet


def inset_notch(spec: DeckSpec, side: str) -> Optional[dict]:
    """The notch an inset stair sits in, read from the outline: its inner face is the side the stair names ("edge:N"); the
    sides either side of it are the cheeks (parallel, both ending on one face line — the face the notch is cut in).
    Inches, plan frame: axis (the travel axis, "x" or "y"), face / out (the inner and the outer face on that axis), lo / hi
    (the notch's span across it), depth, width, sgn (+1 when the deck lies on the + side of the inner face), direction
    (inner face -> outer face, as the scene names it), i_face / i_cheeks (0-based outline sides), corners (the two outer
    corners). None when the side is not such a notch."""
    if not str(side).startswith("edge:") or not spec.geometry.outline:
        return None
    poly = [(float(x) * 12, float(y) * 12) for x, y in spec.geometry.outline]
    n = len(poly)
    try:
        i = int(str(side).split(":")[1]) - 1
    except ValueError:
        return None
    if n < 6 or not 0 <= i < n:
        return None
    a, b = poly[i], poly[(i + 1) % n]
    pa, nb = poly[(i - 1) % n], poly[(i + 2) % n]
    if abs(a[0] - b[0]) < 0.5:
        k, c = 0, 1                  # the inner face runs along y: the stair travels along x
    elif abs(a[1] - b[1]) < 0.5:
        k, c = 1, 0
    else:
        return None
    if abs(pa[c] - a[c]) > 0.5 or abs(nb[c] - b[c]) > 0.5 or abs(pa[k] - nb[k]) > 0.5:
        return None                  # the neighbors are not two parallel cheeks ending on one face line
    face, out = a[k], pa[k]
    if abs(face - out) < 6.0:
        return None
    sgn = 1.0 if face > out else -1.0
    lo, hi = sorted((a[c], b[c]))
    pt = (lambda al, ac: (al, ac)) if k == 0 else (lambda al, ac: (ac, al))
    return dict(axis="xy"[k], face=face, out=out, lo=lo, hi=hi, depth=abs(face - out), width=hi - lo, sgn=sgn,
                direction=("-" if sgn > 0 else "+") + "xy"[k], i_face=i, i_cheeks=((i - 1) % n, (i + 1) % n),
                corners=[pt(out, lo), pt(out, hi)])


def notch_pt(nt: dict, along: float, across: float) -> Tuple[float, float]:
    """A point given along a notch's travel axis and across it, as plan (x, y) inches."""
    return (along, across) if nt["axis"] == "x" else (across, along)


def _frame_notches(spec: DeckSpec, of: "OutlineFrame", poly, ins, jb: float, plies: int) -> None:
    """Inset stairs: each notch framed as a stair opening at the deck's edge — the inner face a doubled trimmer the deck's
    full depth (ledger to front rim, a concealed-flange double hanger at each end), the cheek rims doubled headers hung on
    it (double hangers), the joists inside the notch's width tails hung on the headers (the outline clip does that), a
    picture-frame joist beside the trimmer under the field ends at the stair's top border. The posts under the headers'
    outer ends and the carrier under the stringer feet go with the stair (StairLayout.notch)."""
    for s in spec.stairs:
        if not getattr(s, "inset", False):
            continue
        nt = inset_notch(spec, s.side)
        if nt is None:
            continue
        if nt["axis"] != "x":
            of.notes.append(f"stair notch on {s.side}: its inner face crosses the joists — framed by the outline rims (the inner-face rim is the header); "
                            "run the cheek rims to the next support as trimmers")
            continue
        i_f, face, sgn = nt["i_face"], nt["face"], nt["sgn"]
        mid = (nt["lo"] + nt["hi"]) / 2
        tri = []
        for k in range(plies):
            X = face + sgn * (k + 0.5) * jb
            cr = _col_cross(ins, X)
            pairs = list(zip(cr[0::2], cr[1::2]))
            before = [p for p in pairs if p[1][0] <= mid]
            after = [p for p in pairs if p[0][0] >= mid]
            (ya, ia) = before[-1][0] if before else (nt["lo"], i_f)
            (yb, ib) = after[0][1] if after else (nt["hi"], i_f)
            tri.append((k, X, ya, yb, of.side_kind[ia], of.side_kind[ib]))
        # the trimmer replaces the inner face's short rim; the cheek rims (headers) stop on its face
        of.rims = [r for r in of.rims if r[0] != i_f] + [(i_f, k, X, ya, X, yb) for k, X, ya, yb, _, _ in tri]
        hdr = []
        for j, r in enumerate(of.rims):
            if r[0] in nt["i_cheeks"]:
                i_, k_, x0, y0, x1, y1 = r
                if abs(x0 - face) < abs(x1 - face):
                    x0 = face
                else:
                    x1 = face
                of.rims[j] = (i_, k_, x0, y0, x1, y1)
                hdr.append(abs(x1 - x0))
        # joists: none inside the trimmer's footprint; a picture-frame joist beside it the deck's full depth
        t_lo, t_hi = sorted((face, face + sgn * plies * jb))
        of.joists = [q for q in of.joists if not (q[0] + jb / 2 > t_lo - 0.25 and q[0] - jb / 2 < t_hi + 0.25)]
        X_pf = face + sgn * (plies * jb + 1.5 + jb / 2)
        cr = _col_cross(ins, X_pf)
        pf = next(((ya, ia, yb, ib) for (ya, ia), (yb, ib) in zip(cr[0::2], cr[1::2]) if ya <= mid <= yb), None)
        if pf is not None:
            of.joists = [q for q in of.joists if abs(q[0] - X_pf) >= jb + 0.25]
            of.joists.append((X_pf, pf[0], pf[2], of.side_kind[pf[1]], of.side_kind[pf[3]], "stair-notch joist"))
            of.joists.sort(key=lambda q: (q[0], q[1]))
        of.side_kind[i_f] = "trimmer"
        of.notch_hangers += 4
        t_len = (tri[0][3] - tri[0][2]) if tri else 0.0
        of.notches.append(dict(side=s.side, trimmer=[(X, ya, yb, ea, eb) for _, X, ya, yb, ea, eb in tri], headers=hdr, pf_joist=X_pf if pf else None))
        of.notes.append(f"stair notch on {s.side} ({ftin(nt['width'])} x {ftin(nt['depth'])}): {plies}-ply {spec.framing.joist_size} trimmer {ftin(t_len)} "
                        f"({tri[0][4] if tri else ''} to {tri[0][5] if tri else ''}) at the top riser, a double hanger at each end; {plies}-ply headers at the cheeks "
                        f"hung on it (double hangers), tail joists hung on the headers; a picture-frame joist beside the trimmer")


@dataclass
class SkirtFace:
    """One outline side of the step face clad in vertical panels (inches; z relative to the deck surface, negative down)."""
    edge: str
    x0: float
    y0: float
    x1: float
    y1: float                 # the outline side; the panels' back face lies on it
    nx: float
    ny: float                 # outward normal
    a0: float                 # the clad span along the side from (x0, y0) — past a notch corner it runs on over the cheek panel's edge
    a1: float
    panels: List[List[Tuple[float, float, float]]] = field(default_factory=list)   # per panel, its pieces (a, b, z_bottom): one, or one per tread it steps over
    studs: List[Tuple[float, float]] = field(default_factory=list)                 # (position along the side, z_bottom): 2x4 nailers hung from the rim, behind the panels
    rows: List[Tuple[float, float, float]] = field(default_factory=list)           # (a, b, z_center): 2x4 blocking rows between the studs, the panels' mid and bottom nailers
    cheek: bool = False


@dataclass
class StepSkirt:
    faces: List[SkirtFace]
    drop: float               # deck surface to the lower level's surface
    panel_w: float
    gap: float
    z_top: float              # panel tops (under the picture-frame board)
    rim_bottom: float         # rim / header bottoms: the nailers hang below them
    notes: List[str] = field(default_factory=list)

    def panel_heights(self) -> List[float]:
        return [round(self.z_top - min(z for _, _, z in p), 2) for f in self.faces for p in f.panels]

    def panel_screws(self) -> int:
        """TimberTech TOPLoc fascia screws, the owner's rule: 2 at each board end, then 2 every 12" on the nailers between."""
        n = 0
        for f in self.faces:
            for p in f.panels:
                h = self.z_top - min(q[2] for q in p)
                n += 4 + 2 * max(0, int(math.ceil((h - 2.0) / 12.0 - 1e-9)) - 1)
        return n

    def furring_pieces(self) -> List[Tuple[float, str]]:
        return ([(round(self.rim_bottom - zb, 2), "skirt stud") for f in self.faces for _, zb in f.studs]
                + [(round(b - a, 2), "skirt blocking") for f in self.faces for a, b, _ in f.rows])


def step_skirt_layout(spec: DeckSpec) -> Optional[StepSkirt]:
    """geometry.step_skirt: the face between two levels (and an inset stair's notch cheeks) clad in the decking fascia set
    VERTICALLY — panels the fascia's width, cut to height, 1/8" seams — on 2x4 nailers: the rim at the top, studs hung from
    the rim at <= 16" with blocking rows at mid-height and at the bottom. Panels are laid out from the notch corners, so the
    full panels frame the stair and the cut panels land at the far ends; a face panel at a notch corner runs on over the
    cheek panel's edge. On a cheek every panel stops 1/8" above the tread it meets (cut stepped over a riser line)."""
    sk = spec.geometry.step_skirt
    if not sk or not spec.geometry.outline:
        return None
    f = decking_facts(spec.decking.collection)
    fas = FASCIA[f["material"]]
    fas_t, bt = fas["thick"], f["thick"]
    jd = actual(spec.framing.joist_size)[1]
    drop = float(sk.get("drop_in", 36.0))
    gap = float(sk.get("gap_in", 0.125))
    oc = float(sk.get("stud_oc_in", 16.0))
    w = float(sk.get("panel_in", fas["width"]))
    z_top, rim_bot = -bt, -(bt + jd)
    pb = actual(spec.framing.post_size)[0]
    notes: List[str] = []
    # the inset stairs' notches: their cheeks step down with the treads; their posts take the corner nailer's place
    nts = []
    tread_w = 2 * f["width"] + spec.deck_gap + NOSE
    for s in spec.stairs:
        if getattr(s, "inset", False):
            nt = inset_notch(spec, s.side)
            if nt is not None:
                r_t = RISER[f["material"]]["thick"] if s.closed_risers else 0.0
                rise_ = s.total_rise_in or drop
                geo_ = eng.stair_geometry(rise_, nt["width"], True, tread_w, flights=s.flights or None)
                run_ = (nt["depth"] + fas_t - r_t) / max(1, geo_.treads)
                if not eng.TREAD_MIN <= run_ <= tread_w + 1.0:
                    run_ = tread_w
                pbn, pdn = actual(NOTCH_POST)
                a_c = nt["out"] + nt["sgn"] * pbn / 2
                nts.append((nt, run_, geo_.riser_in, r_t, geo_.treads, [notch_pt(nt, a_c, nt["lo"] - pdn / 2), notch_pt(nt, a_c, nt["hi"] + pdn / 2)]))
    edges = {e.name: e for e in outline_poly_edges(spec)}
    names = list(sk.get("edges") or [])
    if not names:
        for nt, *_ in nts:          # default: the cheeks and every open side on the face line the notch is cut in
            names += [f"edge:{i + 1}" for i in nt["i_cheeks"]]
            k_ = 0 if nt["axis"] == "x" else 1
            names += [e.name for e in edges.values() if e.exposed and abs((e.x0, e.y0)[k_] - nt["out"]) < 0.6 and abs((e.x1, e.y1)[k_] - nt["out"]) < 0.6]
    faces: List[SkirtFace] = []
    for name in dict.fromkeys(names):
        e = edges.get(name)
        if e is None or not e.exposed or e.length < 2.0:
            notes.append(f"step skirt: {name} is not an open outline side — skipped")
            continue
        if abs(e.x1 - e.x0) > 0.5 and abs(e.y1 - e.y0) > 0.5:
            notes.append(f"step skirt: {name} is angled — vertical panels are laid on square sides only; skipped")
            continue
        L_ = e.length
        ux, uy = (e.x1 - e.x0) / L_, (e.y1 - e.y0) / L_
        nx, ny = -uy, ux                                       # outward: the outline runs clockwise, inward is (uy, -ux)
        idx = int(name.split(":")[1]) - 1
        cheek = next((t for t in nts if idx in t[0]["i_cheeks"]), None)
        a0, a1 = 0.0, L_
        start_end = False                                      # lay the panels from the side's end (True) or its start
        for t in nts:
            for cx, cy in t[0]["corners"]:
                if math.hypot(e.x0 - cx, e.y0 - cy) < 0.6:
                    a0 = 0.0 if cheek else -fas_t
                elif math.hypot(e.x1 - cx, e.y1 - cy) < 0.6:
                    a1 = L_ if cheek else L_ + fas_t
                    start_end = True
        sf = SkirtFace(name, e.x0, e.y0, e.x1, e.y1, nx, ny, a0, a1, cheek=cheek is not None)
        def along_u(p, t=cheek):
            """Distance from the notch's inner face at position p along this side (cheeks)."""
            nt = t[0]
            px, py = e.x0 + ux * p, e.y0 + uy * p
            return abs((px if nt["axis"] == "x" else py) - nt["face"])
        def floor_z(p, t=cheek):
            if t is None:
                return -drop
            nt, run_, rise_, r_t, T, _ = t
            k = min(T, max(1, int(math.floor((along_u(p) - r_t) / run_)) + 1))
            return -k * rise_
        # panels
        spans, pos = [], (a1 if start_end else a0)
        while (pos > a0 + 0.05) if start_end else (pos < a1 - 0.05):
            if start_end:
                a, b = max(a0, pos - w), pos; pos = a - gap
            else:
                a, b = pos, min(a1, pos + w); pos = b + gap
            spans.append((a, b))
        if len(spans) > 1 and spans[-1][1] - spans[-1][0] < 3.0:
            # a sliver at the far end: rip the last full panel and the sliver to two equal panels instead
            (pa, pb_), (qa, qb) = spans[-2], spans[-1]
            lo_, hi_ = min(pa, qa), max(pb_, qb)
            half = (hi_ - lo_ - gap) / 2
            spans[-2:] = sorted([(lo_, lo_ + half), (hi_ - half, hi_)], reverse=start_end)
        for a, b in spans:
            cuts = [a, b]
            if cheek is not None:
                nt, run_, rise_, r_t, T, _ = cheek
                ua, ub = along_u(a), along_u(b)
                for k in range(1, T):
                    u_k = k * run_ + r_t                       # where the floor drops from tread k to tread k + 1
                    if min(ua, ub) < u_k < max(ua, ub):        # the panel steps over that riser line: cut it there
                        cuts.append(a + (u_k - ua) / (ub - ua) * (b - a))
            cuts = sorted(set(round(c, 4) for c in cuts))
            gap_ = SKIRT_GAP_TREAD if cheek is not None else SKIRT_GAP_BOTTOM
            sf.panels.append([(p0, p1, floor_z((p0 + p1) / 2) + gap_) for p0, p1 in zip(cuts, cuts[1:]) if p1 - p0 > 0.05])
        # nailers below the rim: studs <= oc apart (not where a notch post stands), blocking rows at mid-height and the bottom
        n_iv = max(1, int(math.ceil((L_ - 3.5) / oc - 1e-9)))
        posts = [p for t in nts for p in t[5]]
        for i in range(n_iv + 1):
            p = 1.75 + (L_ - 3.5) * i / n_iv
            px, py = e.x0 + ux * p - nx * 0.75, e.y0 + uy * p - ny * 0.75
            if any(abs(px - qx) < actual(NOTCH_POST)[1] / 2 + 2.0 and abs(py - qy) < actual(NOTCH_POST)[1] / 2 + 2.0 for qx, qy in posts):
                continue                    # the notch post backs the panels there
            # on the step face a stud runs down past the lower level's surface and laps its rim (2 structural screws); on a
            # cheek it hangs from the header and stops 1/2" over the tread
            zb = floor_z(p) + 0.5 if cheek is not None else -(drop + bt + jd)
            if rim_bot - zb >= 4.0:
                sf.studs.append((round(p, 2), round(zb, 2)))
        if sf.studs:
            # blocking rows: one at the panels' bottom, more between it and the rim so no fastening line is over 12" from the next
            z_b, z_s = -drop + SKIRT_GAP_BOTTOM + 1.75, z_top - 1.0     # the bottom row; the top screws (in the rim)
            n_g = max(1, int(math.ceil((z_s - z_b) / 12.0 - 1e-9)))
            z_rows = [round(z_s - (z_s - z_b) * k / n_g, 2) for k in range(1, n_g + 1)]
            z_rows = [z for z in z_rows if z < rim_bot - 0.5]               # lines inside the rim's depth fasten to the rim
            st_pos = sorted(p for p, _ in sf.studs)
            for zc in z_rows:
                run_a = None
                for p0, p1 in zip(st_pos, st_pos[1:]):
                    ok = floor_z(p0) < zc - 1.95 and floor_z(p1) < zc - 1.95 and p1 - p0 <= oc + 8.0
                    if ok and run_a is None:
                        run_a = p0
                    if not ok and run_a is not None:
                        sf.rows.append((round(run_a + 0.75, 2), round(p0 - 0.75, 2), round(zc, 2))); run_a = None
                if run_a is not None:
                    sf.rows.append((round(run_a + 0.75, 2), round(st_pos[-1] - 0.75, 2), round(zc, 2)))
        faces.append(sf)
    if not faces:
        return None
    sk_ = StepSkirt(faces, drop, w, gap, z_top, rim_bot, notes)
    hs = sk_.panel_heights()
    sk_.notes.append(f"step skirt: {len(hs)} vertical {spec.decking.collection} {spec.decking.fascia_color or spec.decking.color} fascia panels "
                     f"({w:g}\" wide, cut to height, {gap:g}\" seams; {', '.join(f.edge for f in faces)}), tallest {inches_frac_(max(hs))}, "
                     f"on {sum(len(f.studs) for f in faces)} 2x4 nailers hung from the rim at {oc:g}\" and blocking rows at mid-height and the bottom")
    return sk_


def inches_frac_(v: float) -> str:
    n = round(v * 8)
    whole, rem = divmod(int(n), 8)
    return f'{whole}"' if rem == 0 else f'{whole}-{rem // math.gcd(rem, 8)}/{8 // math.gcd(rem, 8)}"'


# ================================================================== stairs
def stair_layouts(spec: DeckSpec, W: float, D: float, dkl: DeckingLayout) -> List[StairLayout]:
    out = []
    f = decking_facts(spec.decking.collection)
    composite = f["material"] != "Wood"
    tread_w = 2 * dkl.bw + dkl.gap + NOSE          # two deck boards + gap + nosing over the riser
    for s in spec.stairs:
        # an inset stair takes its width and its run from the notch it sits in: the treads span cheek skirt to cheek skirt and
        # the bottom riser lands flush with the skirt on the face the notch is cut in
        nt = inset_notch(spec, s.side) if getattr(s, "inset", False) else None
        ins_notes: List[str] = []
        if getattr(s, "inset", False) and nt is None:
            ins_notes.append(f"inset stair on {s.side}: that outline side is not a notch face (two parallel cheeks either side of it) — drawn and counted as an ordinary stair")
        if nt is not None:
            import copy as _copy
            skirt_t = FASCIA[f["material"]]["thick"] if spec.decking.fascia else 0.0
            r_t = RISER[f["material"]]["thick"] if s.closed_risers else 0.0
            clear = round((nt["width"] - 2 * skirt_t) * 8) / 8          # to the 1/8": the outline is in feet
            if abs(clear - s.width_in) > 0.5:
                ins_notes.append(f"inset stair: the notch is {ftin(nt['width'])} wide, so the treads run {ftin(clear)} between the cheek skirts (the stair asks {ftin(s.width_in)})")
            s = _copy.copy(s)
            s.width_in = clear
        rise = s.total_rise_in if s.total_rise_in else spec.geometry.height_in
        geo = eng.stair_geometry(rise, s.width_in, composite, tread_w, flights=s.flights or None)
        if nt is not None:
            run_fit = (nt["depth"] + skirt_t - r_t) / max(1, geo.treads)
            if eng.TREAD_MIN <= run_fit <= tread_w + 1.0:
                geo = eng.stair_geometry(rise, s.width_in, composite, round(run_fit, 3), flights=s.flights or None)
            else:
                ins_notes.append(f"inset stair: the notch is {ftin(nt['depth'])} deep — {geo.treads} treads would run {run_fit:.2f}\"; make it "
                                 f"{ftin(geo.treads * tread_w + r_t - skirt_t)} deep for {tread_w:.2f}\" treads (bottom riser flush with the skirt)")
            geo.guard_required = False         # its sides are the notch cheeks (walls); the deck's own guard runs round the notch
        pieces_per_board = max(1, int(math.floor(144 / (s.width_in + 0.25))))
        tread_pieces = geo.treads * 2
        riser_pieces = geo.risers if s.closed_risers else 0
        sysd = rail_system_for(spec.railing)
        # rail sides per flight: the spec's list, else `rails` on every flight
        frails = [int(r) for r in (s.flight_rails or [])][:len(geo.flights)]
        frails += [s.rails] * (len(geo.flights) - len(frails))
        # stair rail: one or more sections per rail side along each flight's slope
        secs = []
        stair_posts = 0
        for fi, (fg, nr_sides) in enumerate(zip(geo.flights, frails)):
            slope_len = math.hypot(fg.run_in, fg.rise_in - geo.riser_in)
            n = max(1, int(math.ceil(slope_len / (max(sysd["panels"].values()) + 2))))
            tagf = f"stair {s.side}" + (f" flight {fi + 1}" if len(geo.flights) > 1 else "")
            for _ in range(nr_sides):
                for _ in range(n):
                    cut = slope_len / n - sysd["post_w"] - 2 * sysd["bracket_allow"]
                    stock = next((st for st, mx in sorted(sysd["panels"].items()) if cut <= mx + 1e-6), max(sysd["panels"]))
                    secs.append(RailSection(tagf, round(slope_len / n, 2), stock, round(cut, 2), kind="stair"))
            stair_posts += nr_sides * (n + 1)
        # landing guard: level panels along the landings' open sides (the landing is a walking surface over 30")
        land_secs = []; land_posts = 0; land_lf = 0.0
        g_land = -float(s.landing_grade_in) if getattr(s, "landing_grade_in", None) is not None and s.landing_grade_in < 0 else 0.0   # a yard falling away under the landing
        if s.landings and geo.guard_required and (rise - geo.flights[0].rise_in) + g_land > eng.GUARD_TRIGGER_HEIGHT and any(frails):
            if s.landing_guard_lf is not None:
                land_lf = float(s.landing_guard_lf)
            else:
                land_lf = sum(max(0.0, 2 * (float(a) + float(b)) - 2 * s.width_in) for a, b in s.landings) / 12
            if land_lf > 0:
                max_ctc = max(sysd["panels"].values()) + sysd["post_w"] + 2 * sysd["bracket_allow"]
                nb = max(1, int(math.ceil(land_lf * 12 / max_ctc - 1e-9)))
                ctc = land_lf * 12 / nb
                cut = ctc - sysd["post_w"] - 2 * sysd["bracket_allow"]
                stock = next((st for st, mx in sorted(sysd["panels"].items()) if cut <= mx + 1e-6), max(sysd["panels"]))
                land_secs = [RailSection(f"landing {s.side}", round(ctc, 2), stock, round(cut, 2), kind="level")] * nb
                land_posts = nb + 1 + max(0, len(s.landings) - 1)      # a post at each bay end plus one per turn corner
        pos = s.position_in if s.position_in is not None else ((W - s.width_in) / 2 if s.side == "front" else (0.0 if s.side.startswith("step:") else (D - s.width_in - 12)))
        opening = RailOpening(s.side, pos, s.width_in, f"stair {s.width_in:.0f}\" wide")
        notes = list(geo.notes)
        if geo.handrail_required:
            notes.append(f"{geo.risers} risers — graspable handrail 34–38\" on at least one side (IRC R311.7.8)")
        if len(geo.flights) > 1:
            notes.append("flights: " + " · ".join(f"{fg.risers} risers / {fg.treads} treads, run {fg.run_in / 12:.1f}'" for fg in geo.flights)
                         + f" — {s.turn} at the landing" + (f"; landing guard {land_lf:.0f} LF" if land_lf else ""))
        longest = max(fg.run_in for fg in geo.flights)
        mid = s.mid_support if s.mid_support is not None else longest > 72.0
        carriers = [i for i, fg in enumerate(geo.flights) if fg.run_in >= longest - 1e-6] if mid else []
        # DCA6: a cut stringer spans 6' between supports — as many carriers as the run needs, evenly spaced
        n_car = max(1, int(math.ceil(longest / eng.STRINGER_MAX_SPAN_CUT - 1e-9)) - 1) if mid else 0
        fracs = [round(j / (n_car + 1), 4) for j in range(1, n_car + 1)] if mid else [0.5]
        if mid:      # the carriers are the intermediate supports DCA6 asks for
            notes = [n for n in notes if not n.startswith("stringer horizontal run") and not n.startswith("stringer run")]
            notes.append(f"stringer run {longest / 12:.1f}' — {n_car} carrier{'s' if n_car > 1 else ''} under the stringers"
                         + (f" at the {'third' if n_car == 2 else 'quarter' if n_car == 3 else 'mid'} points" if n_car > 1 else " at mid-run")
                         + f", each on two {spec.framing.post_size} posts and footings ({longest / (n_car + 1) / 12:.1f}' spans)"
                         + (f" — under each of {len(carriers)} flights" if len(carriers) > 1 else "")
                         + f"; {2 * n_car * max(1, len(carriers))} posts and footings in all")
        box = (s.build or "stringers") == "box"
        if box:
            notes = [n for n in notes if "stringer" not in n]
            notes.append(f"{geo.treads} framed 2x6 box{'es' if geo.treads > 1 else ''} {s.width_in:.0f}\" wide on a 4\" compacted 3/4\" base, fastened to the rim — no stringers;"
                         " fascia on the front and both ends, decked in the field board")
        elif s.skirts:
            notes.append("fascia skirts on both sides of the stair, stepped under each tread — the stringers never show")
        out.append(StairLayout(s.side, s.width_in, geo, 2, tread_pieces, riser_pieces, 0 if box else geo.stringers, geo.stringer_stock_ft, max(frails) if frails else s.rails, secs, stair_posts,
                               s.landing, opening, notes, mid and not box, (round(longest / 2.0, 1) if mid else 0.0) if not box else 0.0, frails, land_secs, land_posts, round(land_lf, 1),
                               carriers if not box else [], fracs, build="box" if box else "stringers", skirts=bool(s.skirts) or box))
        sl = out[-1]
        sl.handrail, sl.handrail_side, sl.option = getattr(s, "handrail", "") or "", getattr(s, "handrail_side", "") or "right", getattr(s, "option", "") or ""
        lft_ = getattr(s, "landing_footing", "") or ""
        if lft_ in ("deck", "caisson12") and s.landings and len(geo.flights) > 1:
            # the landing posts stand on the deck's own footings: counted with the deck's posts (Layout.n_footings, the post lumber) —
            # or ("caisson12") on the stair's own 12" caissons with its carrier posts (own_footings, below)
            sl.landing_footings = 4 * len(s.landings)
            for li in range(len(s.landings)):
                fi = min(li, len(geo.flights) - 2)               # the flight this landing is the foot of (a turn square + its big landing share one level)
                below = sum(fg.rise_in for fg in geo.flights[fi + 1:]) - float(getattr(s, "landing_grade_in", None) or 0.0)   # + the yard's fall under it
                sl.landing_post_h.append(round(below - f["thick"] - actual(spec.framing.joist_size)[1], 2))
        if lft_ == "caisson12":
            sl.own_footings = sl.landing_footings + (2 * max(1, len(sl.carrier_flights)) * max(1, len(sl.carrier_fracs)) if sl.mid_support else 0)
        if sl.handrail == "each flight":
            sl.handrail_lf = round(sum(math.hypot(fg.run_in, fg.rise_in - geo.riser_in) for fg, r_ in zip(geo.flights, frails) if r_) / 12.0, 1)
        if nt is not None:
            # structure.md §5.2: the header ends and the stringer heels come down onto the lower level's rim — a doubled PT 2x6 stair
            # base ledger through-bolted to its upper-level face, top flush with it, and two short PT posts on that ledger under the
            # header / rim corners. No new footings (the walk-out slab is below).
            pb, pd = actual(NOTCH_POST)
            jd_ = actual(spec.framing.joist_size)[1]
            a_c = nt["out"] + nt["sgn"] * pb / 2                                 # the posts' center line, on the base ledger
            sl.inset, sl.notch_posts, sl.notch_post_len = True, 2, round(rise - jd_, 2)    # base ledger top (lower joist tops) to the header bottom
            sl.notch = dict(nt, post_size=NOTCH_POST, post_line=a_c, posts=[notch_pt(nt, a_c, nt["lo"] - pd / 2), notch_pt(nt, a_c, nt["hi"] + pd / 2)],
                            skirt_t=skirt_t, riser_t=r_t, run=geo.tread_in, ledger_lo=nt["lo"] - 6.0, ledger_hi=nt["hi"] + 6.0,
                            ledger_top=-(rise + f["thick"]), ledger_bolts=int(math.ceil((nt["width"] + 12.0) / 12.0)) + 1)
            if sl.handrail in ("guard posts", ""):
                sl.handrail = "guard posts"
                fg = geo.flights[0]
                sl.handrail_lf = round(math.hypot(fg.run_in + r_t, fg.rise_in - geo.riser_in) / 12.0, 1)
            sl.notes += [f"inset in the {ftin(nt['width'])} x {ftin(nt['depth'])} notch on {s.side}: the stringers hang on the trimmer at the top riser (LSCZ) and their heels "
                         f"bear on a (2)2x6 PT stair base ledger through-bolted to the lower level's rim; {NOTCH_POST} PT posts ({ftin(sl.notch_post_len)}) on that ledger carry "
                         f"the header ends (structure.md §5.2); the cheeks are clad in the step skirt, the deck's picture-frame board is the top nosing"]
            if geo.handrail_required:
                sl.notes.append(f"graspable handrail on the {sl.handrail_side} going down, bracketed to the deck guard's posts along that cheek, 34–38\" over the nosings, "
                                f"top riser to bottom riser ({sl.handrail_lf:g}' of rail)")
        sl.notes += ins_notes
    return out


# ================================================================== beam lines across zones
def _place_posts_line(x0: float, x1: float, boundaries: List[float], allow_by_seg: List[float], end_in: float) -> List[float]:
    """Posts end_in from each end, at every zone boundary, then evenly within each segment at or under that segment's allowable span."""
    fixed = [x0 + end_in] + [b for b in boundaries if x0 + end_in + 36 < b < x1 - end_in - 36] + [x1 - end_in]   # a boundary post only when it is 3'+ from an end post
    fixed = sorted(set(round(v, 3) for v in fixed))
    out = []
    for i, (a, b) in enumerate(zip(fixed, fixed[1:])):
        allow = allow_by_seg[min(i, len(allow_by_seg) - 1)]
        n = max(1, int(math.ceil((b - a) / allow - 1e-9)))
        out += [a + (b - a) * k / n for k in range(n)]
    out.append(fixed[-1])
    return out


@dataclass
class EdgePost:
    """A post under the doubled rim at an outline corner (or mid-side): the rim spans post to post as a flush beam."""
    x: float              # plan inches, post center
    y: float
    zone: str
    load: float           # lb, tributary
    label: str = ""       # E1, E2, ...
    where: str = ""       # "corner sides 3/4" | "side 6"


def build_edge_posts(spec: DeckSpec, zl: List[ZoneLayout], lines: List[BeamLine]) -> Tuple[List[EdgePost], float, List[str]]:
    """Posts under the rims at the owner's outline points. Each sits under both rim ends at a corner (center half a post in
    from each side line); its load is half the rim to the next support each way (posts, or the house where a rim dies
    into it) times half the joist span ending on that rim. Every rim run between supports is checked as a doubled flush beam."""
    pts = spec.framing.edge_posts_ft or []
    if not pts or not spec.geometry.outline:
        return [], 0.0, []
    notes: List[str] = []
    poly = [(float(x) * 12, float(y) * 12) for x, y in spec.geometry.outline]
    n = len(poly)
    jb, jd = actual(spec.framing.joist_size)
    plies = zl[0].frame.rim_plies
    pb = actual(spec.framing.post_size)[0]
    d = pb / 2
    total_psf = max(z.frame.total_psf for z in zl)
    seg = []                                   # cumulative perimeter length at each vertex
    acc = 0.0
    for i in range(n):
        seg.append(acc)
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        acc += math.hypot(x1 - x0, y1 - y0)
    per = acc
    def normal(i):                             # inward normal of side i (the outline runs clockwise)
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        L_ = math.hypot(x1 - x0, y1 - y0) or 1.0
        ux, uy = (x1 - x0) / L_, (y1 - y0) / L_
        return uy, -ux
    open_ = [e.exposed for e in outline_poly_edges(spec)]
    house = lambda i: not open_[i]             # a side on the house (main wall, bay faces): not a rim the posts carry
    placed = []                                # (s along the perimeter, x, y, where)
    for px, py in pts:
        X, Y = float(px) * 12, float(py) * 12
        vi = min(range(n), key=lambda i: math.hypot(poly[i][0] - X, poly[i][1] - Y))
        if math.hypot(poly[vi][0] - X, poly[vi][1] - Y) <= 6.0:
            a_, b_ = normal((vi - 1) % n), normal(vi)
            k = 1.0 + a_[0] * b_[0] + a_[1] * b_[1]
            cx, cy = poly[vi][0] + d * (a_[0] + b_[0]) / k, poly[vi][1] + d * (a_[1] + b_[1]) / k
            placed.append((seg[vi], cx, cy, f"corner, sides {(vi - 1) % n + 1}/{vi + 1}"))
            continue
        best = None
        for i in range(n):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
            L_ = math.hypot(x1 - x0, y1 - y0)
            if L_ < 1:
                continue
            t = max(0.0, min(1.0, ((X - x0) * (x1 - x0) + (Y - y0) * (y1 - y0)) / L_ ** 2))
            qx, qy = x0 + t * (x1 - x0), y0 + t * (y1 - y0)
            dist = math.hypot(qx - X, qy - Y)
            if best is None or dist < best[0]:
                best = (dist, i, t, qx, qy, L_)
        dist, i, t, qx, qy, L_ = best
        nx_, ny_ = normal(i)
        placed.append((seg[i] + t * L_, qx + nx_ * d, qy + ny_ * d, f"side {i + 1}"))
    placed.sort()
    # supports along the perimeter: the posts, plus the house where an open side dies into it
    sup = [(s, "post") for s, *_ in placed]
    for i in range(n):
        if house(i) and not house((i - 1) % n):
            sup.append((seg[i], "house"))
        if house(i) and not house((i + 1) % n):
            sup.append((seg[(i + 1) % n], "house"))
    sup.sort()
    def joist_span_at(x, y):
        """Distance from this point back to the nearest support: a beam line over it, else the house (ledger)."""
        behind = [ln.y for ln in lines if ln.x0 - 6 <= x <= ln.x1 + 6 and ln.y < y - 6]
        return y - (max(behind) if behind else 0.0)
    out = []
    zone_of = lambda x: next((z.name for z in zl if z.x0 - 0.5 <= x <= z.x0 + z.W + 0.5), zl[-1].name)
    for k, (s, x, y, where) in enumerate(placed):
        si = next(j for j, (ss, kind) in enumerate(sup) if abs(ss - s) < 1e-6 and kind == "post")
        prev_s = sup[si - 1][0] if si > 0 else sup[-1][0] - per
        next_s = sup[si + 1][0] if si + 1 < len(sup) else sup[0][0] + per
        trib_len = (s - prev_s) / 2 + (next_s - s) / 2
        load = total_psf * trib_len * max(joist_span_at(x, y), 12.0) / 2 / 144.0
        out.append(EdgePost(x, y, zone_of(x), round(load, 0), f"E{k + 1}", where))
    # the rims between supports, each a doubled flush beam
    size = f"({plies}){spec.framing.joist_size}"
    for (s0, k0), (s1, k1) in zip(sup, sup[1:] + [(sup[0][0] + per, sup[0][1])]):
        span = s1 - s0
        sm_ = (s0 + s1) / 2 % per
        i = max(j for j in range(n) if seg[j] <= sm_ + 1e-6)
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        L_ = math.hypot(x1 - x0, y1 - y0) or 1.0
        t = (sm_ - seg[i]) / L_
        mx, my = x0 + t * (x1 - x0), y0 + t * (y1 - y0)
        if house(i):
            continue
        js = joist_span_at(mx, my)
        allow, _, _ = eng.beam_allowable(size, spec.framing.joist_species, max(js, 72), total_psf)
        if span - pb > allow + 0.5:
            notes.append(f"rim run on side {i + 1}: {ftin(span - pb)} between supports against {ftin(allow)} for a {size} — add an edge post")
    g = spec.geometry
    dk_t = decking_facts(spec.decking.collection)["thick"]
    standoff = {"diamond_pier": DP_STANDOFF, "concrete": CONC_STANDOFF, "caisson": CAISSON_STANDOFF, "existing": CAISSON_STANDOFF}.get(spec.framing.footing_type, CONC_STANDOFF)
    if spec.framing.footing_type == "caisson":
        standoff = float(spec.framing.caisson_above_in) + CAISSON_STANDOFF - 6.0
    post_len = max(6.0, g.height_in - dk_t - jd - standoff)
    # the zone frames count them: footings, worst load
    for z in zl:
        mine = [e for e in out if e.zone == z.name]
        z.frame.n_posts += len(mine)
        if mine:
            z.frame.footing_load_lb = max(z.frame.footing_load_lb, max(e.load for e in mine))
    notes.append(f"{len(out)} edge posts under the doubled rims (" + ", ".join(f"{e.label} {e.where}" for e in out)
                 + f"): the rims span post to post as flush beams, so the front is carried without a cantilever")
    return out, post_len, notes


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
            if spec.framing.footing_type == "diamond_pier" and spec.framing.footing_model_lock:
                cap_ = pier_capacity_lb(spec.framing.footing_model, spec.site.soil_bearing_psf)
                allow_by_seg = [min(a_, cap_ / max(1e-6, m[3].trib_depth / 12.0 * m[2].frame.total_psf) * 12.0) if cap_ else a_
                                for a_, m in zip(allow_by_seg, members)]
            end_in = 18.0 if timber else POST_END_OVERHANG
            explicit = None
            for bb in spec.framing.beams:
                if not bb.posts_x_ft or bb.kind != b.kind or bb.size != b.size or (bb.zones and members[0][2].name not in bb.zones):
                    continue
                zf = members[0][2]
                exp_cl = zf.D - (bb.setback_in or 0) - (0.0 if bb.kind == "flush" else parse_beam(bb.size)[2] / 2)
                if bb.setback_in is not None and abs(exp_cl - b.cl_y) > 2.0:
                    continue          # another beam in this zone (a rear header vs the front beam)
                explicit = bb.posts_x_ft
                break
            if spec.geometry.outline:
                # a polygon outline: the beam runs only where the deck is, to the inside face of the rims
                pin = [(float(px) * 12, float(py) * 12) for px, py in spec.geometry.outline]
                jb_ = actual(first.frame.joist_size)[0]
                _, faces_b = outline_side_faces(spec, outline_poly_edges(spec), first.frame.rim_plies * jb_, jb_)
                ins_b = _inset_inward(pin, faces_b)
                xs_b = [xx for xx, _ in _row_cross(ins_b, key[3])]
                spans_b = [(p_, q_) for p_, q_ in zip(xs_b[0::2], xs_b[1::2]) if min(q_, x1) - max(p_, x0) > 12.0]
                if spans_b:
                    sb = max(spans_b, key=lambda t_: min(t_[1], x1) - max(t_[0], x0))
                    x0, x1 = max(x0, sb[0]), min(x1, sb[1])
            if explicit:
                posts = sorted(px * 12.0 for px in explicit if x0 - 1 <= px * 12.0 <= x1 + 1)
                spans = [b_ - a_ for a_, b_ in zip(posts, posts[1:])]
                if spans and max(spans) > min(allow_by_seg) + 0.5:
                    pass    # span-table exceedance is reported through the beam check / flags; the engineer sizes it
            else:
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
            if timber or (spec.framing.post_size in TIMBER_CAP and parse_beam(b.size)[1].startswith("6x")):
                # a 6x beam on 8x8 / 6x6 posts: CCQ mid-line, ECCQ at a beam end (the end cap is a different part)
                cap_mid, cap_end = TIMBER_CAP.get(spec.framing.post_size, ("CCQ68SDS2.5", "ECCQ68SDS2.5"))
            else:
                cap_mid = cap_end = post_cap(spec.framing.post_size, b.size)
            plies, nom, bw, bd = parse_beam(b.size)
            lines.append(BeamLine(b.kind, b.size, b.species, plies, bw, bd, key[3],
                                  x0, x1, [m[2].name for m in members], posts, pz, loads, b.post_len, pieces, cap_mid, cap_end,
                                  label=f"{'DROP' if b.kind == 'drop' else 'FLUSH'} {b.size} {b.species} " + "+".join(m[2].name for m in members)))
    # two beam lines in the same zone(s) would read the same on every sheet and in the quote: name them from the house out
    from collections import Counter
    for lab, n in Counter(ln.label for ln in lines).items():
        if n > 1:
            same = sorted((ln for ln in lines if ln.label == lab), key=lambda q: q.y)
            for i, ln in enumerate(same):
                ln.label += (" (house side)" if i == 0 else " (front)") if n == 2 else f" ({i + 1} of {n} from the house)"
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
        if (fr.footing_type == "diamond_pier" and not spec.framing.footing_model_lock and fr.footing_load_lb > fr.footing_capacity_lb
                and fr.footing_load_lb <= pier_capacity_lb("DP-75/63", spec.site.soil_bearing_psf)):
            fr.footing_model = "DP-75/63"; fr.footing_capacity_lb = pier_capacity_lb("DP-75/63", spec.site.soil_bearing_psf)
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


# ================================================================== decking from the outline (continuous boards, breakers only where needed)
def _poly_orient(poly: List[Tuple[float, float]]) -> float:
    a = 0.0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        a += x0 * y1 - x1 * y0
    return 1.0 if a > 0 else -1.0


def _inset_polygon(poly: List[Tuple[float, float]], d: List[float]) -> List[Tuple[float, float]]:
    """Offset every edge inward by its own distance and re-intersect the neighbors (a simple polygon)."""
    n = len(poly)
    sgn = _poly_orient(poly)
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        L_ = math.hypot(x1 - x0, y1 - y0)
        if L_ < 1e-9:
            lines.append(None); continue
        ux, uy = (x1 - x0) / L_, (y1 - y0) / L_
        nx, ny = -uy * sgn, ux * sgn
        lines.append((x0 + nx * d[i], y0 + ny * d[i], ux, uy))
    out = []
    for i in range(n):
        a, b = lines[i - 1], lines[i]
        if a is None or b is None:
            out.append(poly[i]); continue
        px, py, ux, uy = a; qx, qy, vx, vy = b
        den = ux * vy - uy * vx
        if abs(den) < 1e-9:
            out.append((qx, qy)); continue
        t = ((qx - px) * vy - (qy - py) * vx) / den
        out.append((px + ux * t, py + uy * t))
    return out


def _poly_inside(poly, x, y) -> bool:
    n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


def _row_cross(poly, y) -> List[Tuple[float, int]]:
    xs = []
    n = len(poly)
    for i in range(n):
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        if (ya > y) != (yb > y):
            xs.append((xa + (y - ya) * (xb - xa) / (yb - ya), i))
    xs.sort()
    return xs


def _edge_kinds(spec: DeckSpec, poly_in: List[Tuple[float, float]]) -> List[str]:
    """house | border for every outline edge: the house side is inside a house block or on an angled house wall."""
    blocks = [tuple(float(v) * 12 for v in h[:4]) for h in (spec.geometry.house_blocks or []) if not (len(h) > 4 and str(h[4]) == "cantilever")]   # an overhang above is not a wall at the deck
    walls = [tuple(float(v) * 12 for v in w[:4]) for w in (spec.geometry.house_walls or [])]
    sgn = _poly_orient(poly_in)
    kinds = []
    n = len(poly_in)
    for i in range(n):
        (x0, y0), (x1, y1) = poly_in[i], poly_in[(i + 1) % n]
        L_ = math.hypot(x1 - x0, y1 - y0)
        if L_ < 1e-9:
            kinds.append("border"); continue
        ux, uy = (x1 - x0) / L_, (y1 - y0) / L_
        nx, ny = -uy * sgn, ux * sgn            # inward
        mx, my = (x0 + x1) / 2 - nx * 2.0, (y0 + y1) / 2 - ny * 2.0     # 2" outside the edge
        house = any(bx0 - 0.5 <= mx <= bx1 + 0.5 and by0 - 0.5 <= my <= by1 + 0.5 for bx0, bx1, by0, by1 in blocks)
        if not house:
            for wx0, wy0, wx1, wy1 in walls:
                wl = math.hypot(wx1 - wx0, wy1 - wy0) or 1e-9
                t = max(0.0, min(1.0, ((mx - wx0) * (wx1 - wx0) + (my - wy0) * (wy1 - wy0)) / wl ** 2))
                if math.hypot(mx - (wx0 + t * (wx1 - wx0)), my - (wy0 + t * (wy1 - wy0))) < 4.0:
                    house = True; break
        kinds.append("house" if house else "border")
    return kinds


def build_field_plan(spec: DeckSpec, zl: List[ZoneLayout], dkl: DeckingLayout) -> Optional[FieldPlan]:
    """Rows from the outline. Panels between breakers each carry their own row grid from their outermost front edge."""
    if not spec.geometry.outline or spec.geometry.board_direction != "parallel":
        return None
    poly = [(float(x) * 12, float(y) * 12) for x, y in spec.geometry.outline]
    if len(poly) < 3:
        return None
    bw, gap = dkl.bw, dkl.gap
    edge = (dkl.fascia_t + NOSE) if spec.decking.fascia else OVERHANG_NO_FASCIA   # board overhang past the frame (fascia + nose)
    pf = spec.geometry.picture_frame
    kinds = _edge_kinds(spec, poly)
    inset = _inset_polygon(poly, [((bw + gap - edge) if (pf and k == "border") else (-edge if k == "border" else 0.0)) for k in kinds])
    xs_all = [x for x, _ in poly]; ys_all = [y for _, y in poly]
    xmin, xmax, ymin, ymax = min(xs_all), max(xs_all), min(ys_all), max(ys_all)
    stock_max = max(STOCK_LENGTHS_FT) * 12.0
    trim_d = bw / 2 + gap                   # a field board stops this short of a breaker line
    # ---- breaker lines: explicit, else only where a raw row would exceed the longest stock, on zone (house-corner) lines
    plan = FieldPlan()
    if spec.decking.divider_x_ft:
        div_x = sorted(float(v) * 12 for v in spec.decking.divider_x_ft)
    elif spec.decking.dividers:
        cands = sorted({z.x0 for z in zl[1:]})
        div_x: List[float] = []
        raw_rows = []
        yy = ymax - 0.5
        while yy > ymin:
            xs = _row_cross(poly, yy)
            for (a, _), (b, _) in zip(xs[0::2], xs[1::2]):
                raw_rows.append((b - a, a, b))
            yy -= bw + gap
        for _, a, b in sorted(raw_rows, reverse=True):
            cuts = sorted(x for x in div_x if a - 6 <= x <= b + 6)
            start = a
            for c in cuts + [b]:
                if c <= start + 6:            # a breaker already sits at (or within 6" of) this end
                    start = max(start, c); continue
                # a board between two breaker lines is the line spacing less a half board and a gap at each end
                allow = stock_max + (2 * trim_d if start != a else trim_d)
                while c - start > allow:
                    ok = [x for x in cands if start + 24 < x <= start + allow and x < c - 24]
                    x_new = max(ok) if ok else start + (c - start) / math.ceil((c - start) / allow)
                    allow = stock_max + 2 * trim_d
                    x_new = round(x_new * 2) / 2
                    div_x.append(x_new); div_x.sort()
                    start = x_new
                start = c
    else:
        div_x = []
    bounds = [xmin] + div_x + [xmax]

    def _on_deck(xb: float, y: float) -> bool:
        """A breaker line lies on the deck at y: inside the outline, or on its edge (a breaker on a house-wall line). A breaker
        set off a house corner stops at the corner; behind it the rows end at the house wall."""
        if _poly_inside(poly, xb, y):
            return True
        for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
            dx, dy = bx - ax, by - ay
            t_ = max(0.0, min(1.0, ((xb - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy or 1e-9)))
            if math.hypot(ax + t_ * dx - xb, ay + t_ * dy - y) < 0.6:
                return True
        return False
    # ---- rows per panel
    for pi, (pa, pb) in enumerate(zip(bounds, bounds[1:])):
        # the panel's outermost front: the outline's highest y inside the panel (vertices and the crossings at its sides)
        ys_p = [y for x, y in poly if pa - 0.01 <= x <= pb + 0.01]
        for xb in (pa, pb):
            for i in range(len(poly)):
                (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
                if (x0 > xb) != (x1 > xb):
                    ys_p.append(y0 + (xb - x0) * (y1 - y0) / (x1 - x0))
        y_top = (max(ys_p) if ys_p else ymax) + edge
        y1 = y_top - ((bw + gap) if pf else 0.0)
        n_rows = 0
        lo = pa + (trim_d if pi > 0 else -edge - 1.0)
        hi = pb - (trim_d if pi < len(bounds) - 2 else -edge - 1.0)
        while y1 > ymin - bw:
            yc = y1 - bw / 2
            xs = _row_cross(inset, yc)
            got = False
            for (a, ia), (b, ib) in zip(xs[0::2], xs[1::2]):
                x0_, x1_ = max(a, lo), min(b, hi)
                if x1_ - x0_ < 6.0:
                    if x1_ - x0_ > 0.5:
                        plan.dropped += 1
                        plan.dropped_at.append((round((x0_ + x1_) / 2, 1), round(yc, 1)))
                    continue
                xm = (x0_ + x1_) / 2
                top_in = _poly_inside(inset, xm, y1 - 0.05)
                bot_in = _poly_inside(inset, xm, y1 - bw + 0.05)
                yb0, yb1 = y1 - bw, y1
                rip = False
                if top_in and not bot_in:
                    lo_y, hi_y = y1 - bw, y1
                    for _ in range(24):
                        m = (lo_y + hi_y) / 2
                        if _poly_inside(inset, xm, m): hi_y = m
                        else: lo_y = m
                    yb0 = hi_y; rip = True
                elif bot_in and not top_in:
                    lo_y, hi_y = y1 - bw, y1
                    for _ in range(24):
                        m = (lo_y + hi_y) / 2
                        if _poly_inside(inset, xm, m): lo_y = m
                        else: hi_y = m
                    yb1 = lo_y; rip = True
                elif not top_in and not bot_in:
                    continue
                if yb1 - yb0 < 1.0:
                    continue
                at_l = abs(x0_ - lo) < 0.05 and pi > 0 and _on_deck(pa, yc)
                at_r = abs(x1_ - hi) < 0.05 and pi < len(bounds) - 2 and _on_deck(pb, yc)
                left = "divider" if at_l else ("house" if kinds[ia] == "house" else "border")
                right = "divider" if at_r else ("house" if kinds[ib] == "house" else "border")
                for k_, (i_, x_) in (("l", (ia, x0_)), ("r", (ib, x1_))):
                    (ex0, ey0), (ex1, ey1) = poly[i_], poly[(i_ + 1) % len(poly)]
                    if kinds[i_] == "house" and abs(ex0 - ex1) > 0.5 and abs(ey0 - ey1) > 0.5:
                        if k_ == "l" and left == "house": left = "cut"
                        if k_ == "r" and right == "house": right = "cut"
                plan.rows.append(RowSeg(round(yb0, 3), round(yb1, 3), round(x0_, 3), round(x1_, 3), pi, rip, left, right))
                got = True
            if got:
                n_rows += 1
            y1 -= bw + gap
        plan.panels.append((pa, pb, n_rows, y_top))
    # ---- breakers: from the panel front down to the last row that runs past the line
    for k, x in enumerate(div_x):
        y_hi = max(plan.panels[k][3], plan.panels[k + 1][3])
        # a breaker never runs past the outline: where the two sides' fronts differ at the line (a notch corner), stop at the nearer
        tops = []
        for xs_ in (x - 1.0, x + 1.0):
            ys_ = sorted(ay + (xs_ - ax) * (by - ay) / (bx - ax) for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]) if (ax > xs_) != (bx > xs_))
            if ys_:
                tops.append(ys_[-1])
        if len(tops) == 2:
            y_hi = min(y_hi, min(tops))
        y_lo = y_hi - bw - gap
        for r in plan.rows:
            if (r.x0 + 1.0 < x < r.x1 - 1.0) or (r.right == "divider" and abs(r.x1 - (x - trim_d)) < 0.1) or (r.left == "divider" and abs(r.x0 - (x + trim_d)) < 0.1):
                y_lo = min(y_lo, r.y0)
        lab = next((f"D{a.name}/{b.name}" for a, b in zip(zl, zl[1:]) if abs(b.x0 - x) < 0.6), f"D@{ftin(x)}")
        plan.dividers.append((x, y_lo, y_hi, lab))
    # ---- borders on every exposed edge
    if pf:
        for i, k in enumerate(kinds):
            if k == "border":
                (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
                if math.hypot(x1 - x0, y1 - y0) > 0.5:
                    plan.borders.append((x0, y0, x1, y1, "border"))
    if plan.dropped:
        plan.notes.append(f"{plan.dropped} sliver{'s' if plan.dropped != 1 else ''} under 6\" beside the breakers / bay {'are' if plan.dropped != 1 else 'is'} not laid as {'boards' if plan.dropped != 1 else 'a board'} (the border or breaker covers)")
    long_ = [q for q in plan.rows if q.length > stock_max - 2.0]
    if long_:
        plan.notes.append(f"{len(long_)} row{'s' if len(long_) != 1 else ''} over a {max(STOCK_LENGTHS_FT)}' board (longest {ftin(max(q.length for q in long_))}) — add a breaker line")
    return plan


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
        if g.outline:
            poly = [(float(x) * 12, float(y) * 12) for x, y in g.outline]
            def _inside(x, y):
                c = False
                for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
                    if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                        c = not c
                return c
            for e in edges:
                if not e.exposed or e.length < 1:
                    continue
                ux, uy = (e.x1 - e.x0) / e.length, (e.y1 - e.y0) / e.length
                nx, ny = uy, -ux           # inward normal: the outline runs clockwise
                # five points along the edge, 12" inside it: the edge is real if any of them is deck
                hits = [_inside(e.x0 + (e.x1 - e.x0) * t + nx * 12, e.y0 + (e.y1 - e.y0) * t + ny * 12) for t in (0.1, 0.3, 0.5, 0.7, 0.9)]
                if not any(hits):
                    e.exposed = False
        deepest = max(zl, key=lambda q: q.D)
        st = stair_layouts(spec, deepest.W, deepest.D, deepest.decking)
        lines = build_beam_lines(spec, zl)
        eposts, epost_len, ep_notes = build_edge_posts(spec, zl, lines)
        divs = build_dividers(spec, zl)
        plan = build_field_plan(spec, zl, zl[0].decking) if (spec.decking.dividers or spec.decking.divider_x_ft) else None
        if plan is not None:
            divs = [(x, y_hi - y_lo, lab) for x, y_lo, y_hi, lab in plan.dividers]
            notes.append(plan.summary())
            notes += plan.notes
        oedges = outline_poly_edges(spec) if (g.outline and any(str(n).startswith("edge:") for n in (spec.railing.edges or []) + [q.side for q in spec.stairs])) else []
        rl = rail_layout_edges(spec, oedges or edges, [q.opening for q in st], forced_x=[d[0] for d in divs],
                               fixed_pts=(__import__("decktakeoff.louvered", fromlist=["rail_points"]).rail_points(spec, zl) if spec.geometry.louvered_roofs else None))
        notes.append(f"{len(zl)} zones, {sum(q.W for q in zl) / 12:.1f}' along the house, outline "
                     + " · ".join(f"{e.name} {ftin(e.length)}" for e in edges if e.exposed))
        for ln in lines:
            notes.append(f"{ln.label}: {ftin(ln.length)} long, {ln.n_posts} posts at " + " / ".join(ftin(px) for px in ln.posts_x)
                         + (f"; pieces " + " · ".join(ftin(b - a) for a, b in ln.pieces) if len(ln.pieces) > 1 else ""))
        wall_lf = sum(q.W for q in zl if q.frame.ledger) + sum(abs(a.wall_y - b.wall_y) for a, b in zip(zl, zl[1:]) if a.frame.ledger and b.frame.ledger)
        L = Layout(spec, zl[0].frame, zl[0].decking, rl, st, x, deepest.D, notes, zl, edges, True, lines, divs, wall_lf)
        L.plan = plan
        L.outline_edges = oedges
        L.edge_posts, L.edge_post_len = eposts, epost_len
        L.notes += ep_notes
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
    rl = rail_layout(spec, W, D, [q.opening for q in st],
                     fixed_pts=(__import__("decktakeoff.louvered", fromlist=["rail_points_rect"]).rail_points_rect(spec, W, D) if spec.geometry.louvered_roofs else None))
    zl = [ZoneLayout("A", "", 0.0, 0.0, W, D, fr, dk, bool(spec.extras.hot_tub))]
    edges = outline_edges(zl, spec)
    lines = [BeamLine(b.kind, b.size, b.species, b.plies, b.width, b.depth, b.cl_y, b.x0, b.x0 + b.length, ["A"], list(b.posts_x), ["A"] * len(b.posts_x),
                      [fr.footing_load_lb] * len(b.posts_x), b.post_len, [(b.x0, b.x0 + b.length)], b.cap, b.cap, b.label) for b in fr.beams]
    return Layout(spec, fr, dk, rl, st, W, D, notes, zl, edges, False, lines, [], W if fr.ledger else 0.0)
