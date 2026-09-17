"""Prescriptive deck engineering per 2021 IRC R507 / AWC DCA6 (40 psf live + 10 psf dead, L/360).
Tables are transcribed from IRC Tables R507.6 (joists), R507.5 (beams), R507.4 (posts), R507.3.1 (footings)
and R507.9.1.3(1) (ledger fasteners). Values are inches. Where a job falls outside the tables the engine
scales for load and FLAGS engineering — it never silently invents a span.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .catalog import LUMBER, parse_beam

LIVE_PSF = 40.0
DEAD_PSF = 10.0
TABLE_TOTAL_PSF = LIVE_PSF + DEAD_PSF       # tables are built for 50 psf total
HOT_TUB_PSF = 100.0

# ------------------------------------------------------------- joists: Table R507.6 (allowable span, in)
# species group -> size -> {spacing: span}
_J = lambda a, b, c: {12: a, 16: b, 24: c}
JOIST_SPAN = {
    "SYP": {"2x6": _J(119, 108, 91), "2x8": _J(157, 142, 116), "2x10": _J(194, 168, 137), "2x12": _J(216, 198, 162)},
    "DF":  {"2x6": _J(114, 104, 86), "2x8": _J(150, 133, 109), "2x10": _J(188, 163, 133), "2x12": _J(216, 189, 154)},
    "SPF": {"2x6": _J(114, 104, 86), "2x8": _J(150, 133, 109), "2x10": _J(188, 163, 133), "2x12": _J(216, 189, 154)},
    "HF":  {"2x6": _J(114, 104, 86), "2x8": _J(150, 133, 109), "2x10": _J(188, 163, 133), "2x12": _J(216, 189, 154)},
    "CEDAR": {"2x6": _J(106, 96, 84), "2x8": _J(140, 127, 104), "2x10": _J(179, 156, 127), "2x12": _J(209, 181, 148)},
}
# max cantilever past a drop beam: 1/4 of the back-span (R507.5 / R507.6 footnote), and never more than the
# joist can carry as a full-load overhang; DCA6 also caps at nominal depth in feet
CANTILEVER_RATIO = 0.25

# ------------------------------------------------------------- beams: Table R507.5 (allowable beam span, in)
# indexed by joist span (ft) 6, 8, 10, 12, 14, 16, 18
BEAM_JOIST_SPANS = [6, 8, 10, 12, 14, 16, 18]
_B = lambda *v: list(v)
BEAM_SPAN = {
    "SYP": {
        "(2)2x6": _B(83, 71, 64, 58, 54, 51, 48), "(2)2x8": _B(105, 91, 81, 74, 69, 64, 60),
        "(2)2x10": _B(124, 108, 96, 88, 81, 76, 72), "(2)2x12": _B(146, 127, 113, 103, 96, 90, 84),
        "(3)2x6": _B(98, 89, 80, 73, 68, 63, 60), "(3)2x8": _B(130, 114, 102, 93, 86, 80, 76),
        "(3)2x10": _B(156, 135, 120, 110, 102, 95, 90), "(3)2x12": _B(183, 159, 142, 129, 120, 112, 106),
        "4x6": _B(77, 66, 59, 54, 50, 47, 44), "4x8": _B(101, 87, 78, 71, 66, 62, 58),
        "4x10": _B(119, 103, 92, 84, 78, 73, 68), "4x12": _B(137, 119, 106, 97, 90, 84, 79),
    },
    "DF": {
        "(2)2x6": _B(65, 56, 50, 46, 42, 40, 37), "(2)2x8": _B(82, 71, 64, 58, 54, 49, 44),
        "(2)2x10": _B(100, 87, 78, 71, 66, 61, 56), "(2)2x12": _B(116, 101, 90, 82, 76, 71, 67),
        "(3)2x6": _B(88, 80, 72, 66, 61, 57, 54), "(3)2x8": _B(116, 102, 91, 83, 77, 72, 68),
        "(3)2x10": _B(144, 125, 112, 102, 94, 88, 83), "(3)2x12": _B(167, 145, 129, 118, 109, 102, 97),
        "4x6": _B(62, 53, 47, 43, 39, 36, 34), "4x8": _B(80, 69, 62, 56, 52, 48, 44),
        "4x10": _B(94, 81, 73, 66, 61, 57, 53), "4x12": _B(109, 94, 84, 77, 71, 67, 62),
    },
}
BEAM_SPAN["SPF"] = BEAM_SPAN["DF"]
BEAM_SPAN["HF"] = BEAM_SPAN["DF"]
BEAM_SPAN["CEDAR"] = BEAM_SPAN["DF"]
# 6x beams are not in R507.5 — treat 6x10 ≈ (3)2x10, 6x12 ≈ (3)2x12 (same section modulus class); flagged as engineered.
BEAM_ALIAS = {"6x10": "(3)2x10", "6x12": "(3)2x12", "6x8": "(3)2x8", "3x10": "(2)2x10", "3x12": "(2)2x12"}

# ------------------------------------------------------------- posts: Table R507.4 (max height, in)
POST_MAX_HEIGHT = {"4x4": 81, "4x6": 96, "6x6": 168, "8x8": 168}

# ------------------------------------------------------------- ledger: Table R507.9.1.3(1) on-centre spacing (in) by joist span (ft)
LEDGER_LAG_SPACING = {  # 1/2" lag screws
    6: 30, 8: 23, 10: 18, 12: 15, 14: 13, 16: 11, 18: 10}
LEDGER_BOLT_SPACING = {  # 1/2" through-bolts
    6: 36, 8: 36, 10: 34, 12: 29, 14: 24, 16: 21, 18: 19}
# LedgerLOK (FastenMaster ESR-1078): GSX standard is 2 rows, 2" from top/bottom, staggered 12" OC -> one screw every 12" of ledger

# ------------------------------------------------------------- stairs: IRC R311.7
RISER_MAX = 7.75
TREAD_MIN = 10.0
STAIR_WIDTH_MIN = 36.0
HANDRAIL_MIN_RISERS = 4
GUARD_TRIGGER_HEIGHT = 30.0      # R312.1.1: guards where the walking surface is > 30" above grade within 36"
GUARD_HEIGHT_RES = 36.0
GUARD_HEIGHT_COMM = 42.0
STRINGER_MAX_SPAN_CUT = 72.0     # DCA6: cut 2x12 stringers, 6'-0" max horizontal span between supports
STRINGER_OC_COMPOSITE = 12.0     # TimberTech: stair treads need 12" OC max stringer spacing (composite & PVC)
STRINGER_OC_WOOD = 16.0


def _interp_table(x: float, xs: List[float], ys: List[float]) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


def design_load_psf(ground_snow_psf: float, hot_tub: bool = False) -> Tuple[float, str]:
    """Total design load and why. IRC tables are good for live 40 psf or snow <= 40 psf."""
    if hot_tub:
        return HOT_TUB_PSF + DEAD_PSF, "hot tub — 100 psf live"
    ll = max(LIVE_PSF, float(ground_snow_psf or 0))
    why = "40 psf live governs" if ll == LIVE_PSF else f"ground snow {ground_snow_psf:g} psf governs over 40 psf live"
    return ll + DEAD_PSF, why


def load_factor(total_psf: float) -> float:
    """Scale factor on tabulated spans for loads above the table's 50 psf (bending governs: span ∝ 1/sqrt(w))."""
    if total_psf <= TABLE_TOTAL_PSF:
        return 1.0
    return math.sqrt(TABLE_TOTAL_PSF / total_psf)


@dataclass
class SpanCheck:
    member: str
    size: str
    species: str
    spacing_in: float
    actual_in: float
    allowable_in: float
    table_allowable_in: float
    load_psf: float
    ok: bool
    note: str = ""

    @property
    def utilization(self) -> float:
        return self.actual_in / self.allowable_in if self.allowable_in else 9.9


def joist_allowable(size: str, species: str, spacing: float, total_psf: float = TABLE_TOTAL_PSF) -> Tuple[float, float]:
    sp = species if species in JOIST_SPAN else "DF"
    tbl = JOIST_SPAN[sp].get(size)
    if tbl is None:
        raise ValueError(f"no joist span data for {size}")
    xs = [12, 16, 24]
    table = _interp_table(spacing, xs, [tbl[12], tbl[16], tbl[24]])
    return table * load_factor(total_psf), table


def check_joist(size: str, species: str, spacing: float, span_in: float, total_psf: float) -> SpanCheck:
    allow, table = joist_allowable(size, species, spacing, total_psf)
    note = ""
    if total_psf > TABLE_TOTAL_PSF:
        note = f"table span {table:.0f}\" scaled x{load_factor(total_psf):.2f} for {total_psf:g} psf — engineer to confirm"
    return SpanCheck("joist", size, species, spacing, span_in, allow, table, total_psf, span_in <= allow + 0.5, note)


def beam_allowable(size: str, species: str, joist_span_in: float, total_psf: float = TABLE_TOTAL_PSF) -> Tuple[float, float, str]:
    """Allowable beam span (post to post) for a beam carrying joists of `joist_span_in` (ledger-to-beam span
    plus the cantilever, per R507.5 footnote). Returns (allowable, table value, note)."""
    sp = species if species in BEAM_SPAN else "DF"
    key = size.replace(" ", "")
    note = ""
    if key in BEAM_ALIAS:
        note = f"{key} not in IRC R507.5 — treated as {BEAM_ALIAS[key]}; engineer to confirm"
        key = BEAM_ALIAS[key]
    row = BEAM_SPAN[sp].get(key)
    if row is None:
        raise ValueError(f"no beam span data for {size} {species}")
    js_ft = joist_span_in / 12.0
    table = _interp_table(js_ft, BEAM_JOIST_SPANS, row)
    if js_ft > BEAM_JOIST_SPANS[-1]:
        note = (note + "; " if note else "") + f"joist span {js_ft:.1f}' exceeds the 18' table limit — engineered beam"
    return table * load_factor(total_psf), table, note


def check_beam(size: str, species: str, joist_span_in: float, post_spacing_in: float, total_psf: float) -> SpanCheck:
    allow, table, note = beam_allowable(size, species, joist_span_in, total_psf)
    if total_psf > TABLE_TOTAL_PSF:
        note = (note + "; " if note else "") + f"scaled x{load_factor(total_psf):.2f} for {total_psf:g} psf"
    return SpanCheck("beam", size, species, post_spacing_in, post_spacing_in, allow, table, total_psf, post_spacing_in <= allow + 0.5, note)


def post_ok(size: str, height_in: float) -> Tuple[bool, float]:
    mx = POST_MAX_HEIGHT.get(size, 0)
    return height_in <= mx, mx


def footing_load_lb(post_spacing_in: float, trib_depth_in: float, total_psf: float) -> float:
    return post_spacing_in / 12.0 * trib_depth_in / 12.0 * total_psf


def concrete_footing_diameter(load_lb: float, soil_psf: float, min_in: float = 12.0) -> float:
    """Round pier diameter (in) for a bearing load, rounded up to the next 2\"; forms come 12/16/18/24."""
    area_sf = load_lb / soil_psf
    d = math.sqrt(4 * area_sf / math.pi) * 12
    d = max(min_in, math.ceil(d / 2.0) * 2)
    for f in (12, 16, 18, 24, 30):
        if d <= f:
            return float(f)
    return float(math.ceil(d))


def ledger_fastener_count(ledger_len_in: float, joist_span_in: float, fastener: str) -> Tuple[int, str]:
    """Count + rule. LedgerLOK: 2 rows staggered 12" OC = one screw per 12" + 1 (GSX standard). Lags/bolts: IRC table, 2 rows staggered."""
    js_ft = joist_span_in / 12.0
    if fastener.lower().startswith("ledgerlok"):
        n = int(math.ceil(ledger_len_in / 12.0 - 1e-9)) + 1
        return n, "LedgerLOK 2 rows 2\" from top/bottom, staggered 12\" OC, first 3\" from each end"
    tbl = LEDGER_BOLT_SPACING if "bolt" in fastener.lower() else LEDGER_LAG_SPACING
    keys = sorted(tbl)
    k = next((kk for kk in keys if js_ft <= kk), keys[-1])
    sp = tbl[k]
    n = int(math.ceil(ledger_len_in / sp)) * 2 + 2   # two staggered rows, one at each end of each row
    return n, f"IRC R507.9.1.3 — 1/2\" {'bolts' if 'bolt' in fastener.lower() else 'lags'} @ {sp}\" OC, 2 rows staggered (joist span {js_ft:.0f}')"


@dataclass
class FlightGeometry:
    """One straight run of stair between two walking surfaces (deck, landing, pad)."""
    risers: int
    treads: int
    rise_in: float
    run_in: float
    stringer_len_in: float
    stringer_stock_ft: int


@dataclass
class StairGeometry:
    total_rise_in: float
    risers: int
    riser_in: float
    treads: int
    tread_in: float
    total_run_in: float
    stringer_len_in: float
    stringer_stock_ft: int
    stringers: int
    handrail_required: bool
    guard_required: bool
    notes: List[str]
    flights: List[FlightGeometry] = field(default_factory=list)   # top down; one entry for a straight stair


def _stringer_stock(length_in: float) -> int:
    return next((s for s in (8, 10, 12, 14, 16, 20) if s * 12 >= length_in), 20)


def stair_geometry(total_rise_in: float, width_in: float, composite_treads: bool = True, tread_in: float = 10.9,
                   stringer_oc: Optional[float] = None, flights: Optional[List[int]] = None) -> StairGeometry:
    """flights: risers per flight, top down (e.g. [7, 6] — down 7 to a landing, then 6 more). None -> one flight at the code
    minimum riser count. The riser height is the same in every flight (IRC R311.7.5.1: 3/8" max variation in a flight)."""
    notes = []
    flights = [int(f) for f in (flights or []) if int(f) > 0]
    if flights:
        risers = sum(flights)
        if risers < int(math.ceil(total_rise_in / RISER_MAX - 1e-9)):
            notes.append(f"{risers} risers over {total_rise_in:.0f}\" is {total_rise_in / risers:.2f}\" a riser — over 7-3/4\"; add a riser or check the rise")
    else:
        risers = max(1, int(math.ceil(total_rise_in / RISER_MAX - 1e-9)))
        flights = [risers]
    riser = total_rise_in / risers
    treads = risers - len(flights)            # the top tread of every flight is the deck or the landing
    run = treads * tread_in
    oc = stringer_oc or (STRINGER_OC_COMPOSITE if composite_treads else STRINGER_OC_WOOD)
    stringers = int(math.ceil(width_in / oc - 1e-9)) + 1
    fl = []
    for nr in flights:
        nt = nr - 1
        r_ = nt * tread_in
        ln = math.hypot(r_, nr * riser) + 12     # +12" for the top connection and bottom cut
        fl.append(FlightGeometry(nr, nt, round(nr * riser, 3), round(r_, 3), round(ln, 1), _stringer_stock(ln)))
        if r_ > STRINGER_MAX_SPAN_CUT:
            notes.append(f"stringer horizontal run {r_/12:.1f}' > 6' — add an intermediate support/landing or use solid stringers (DCA6)")
    length = max(f.stringer_len_in for f in fl)
    stock = max(f.stringer_stock_ft for f in fl)
    if width_in < STAIR_WIDTH_MIN:
        notes.append(f"stair width {width_in:.0f}\" < 36\" minimum (IRC R311.7.1)")
    if riser > RISER_MAX + 0.01:
        notes.append("riser exceeds 7-3/4\"")
    if riser < 4:
        notes.append("riser under 4\" — check with the deck height; maybe a single step or a landing instead")
    return StairGeometry(total_rise_in, risers, round(riser, 3), treads, tread_in, run, length, stock, stringers,
                         risers >= HANDRAIL_MIN_RISERS, total_rise_in > GUARD_TRIGGER_HEIGHT, notes, fl)


# ------------------------------------------------------------- solid-sawn timber (pre-engineering estimate, NDS-style)
# Douglas Fir-Larch reference design values (NDS supplement). Dimension lumber (2"-4" thick) #1; Beams & Stringers (5"+ thick) #1;
# Posts & Timbers #1. Fb/E in psi. Adjusted: Cd 1.15 (snow), Cr 1.15 (repetitive joists), CF size factor approximated.
TIMBER_DESIGN = {
    "DF#1": {"dim": dict(Fb=1000, E=1.7e6, Fv=180), "bs": dict(Fb=1350, E=1.6e6, Fv=170), "pt": dict(Fc=1200, E=1.6e6)},
    "DF":   {"dim": dict(Fb=900, E=1.6e6, Fv=180), "bs": dict(Fb=875, E=1.3e6, Fv=170), "pt": dict(Fc=700, E=1.3e6)},
    "SYP":  {"dim": dict(Fb=1250, E=1.6e6, Fv=175), "bs": dict(Fb=1350, E=1.5e6, Fv=165), "pt": dict(Fc=1100, E=1.5e6)},
}
CD_SNOW = 1.15
CR_REP = 1.15


def _cf(depth_in: float, width_in: float) -> float:
    """NDS size factor (dimension lumber) / B&S depth factor approximation."""
    if width_in >= 5:
        return min(1.0, (12.0 / depth_in) ** (1 / 9)) if depth_in > 12 else 1.0
    return {3.5: 1.5, 5.5: 1.4, 7.25: 1.2, 9.25: 1.1, 11.25: 1.0}.get(depth_in, 1.0)


def timber_allowable_span(size: str, species: str, w_plf: float, repetitive: bool, defl: float = 360.0) -> Tuple[float, str]:
    """Simply supported allowable span (in) for a solid-sawn member under a uniform load, bending vs L/defl.
    Returns (span, governing)."""
    plies, nom, b, d = parse_beam(size)
    grp = "bs" if b >= 5 else "dim"
    v = TIMBER_DESIGN.get(species, TIMBER_DESIGN["DF#1"])[grp]
    Fb = v["Fb"] * CD_SNOW * _cf(d, b) * (CR_REP if repetitive and b < 5 else 1.0)
    S = plies * b * d * d / 6.0
    I = plies * b * d ** 3 / 12.0
    w = w_plf / 12.0                                   # lb/in
    L_bend = math.sqrt(8 * Fb * S / w)                 # M = wL^2/8 <= Fb*S
    L_defl = (384 * v["E"] * I / (5 * defl * w)) ** (1 / 3)   # 5wL^4/384EI <= L/defl
    if L_bend <= L_defl:
        return L_bend, "bending"
    return L_defl, f"L/{defl:.0f} deflection"


def check_timber_joist(size: str, species: str, spacing: float, span_in: float, total_psf: float) -> SpanCheck:
    w = total_psf * spacing / 12.0
    allow, gov = timber_allowable_span(size, species, w, repetitive=True)
    return SpanCheck("joist", size, species, spacing, span_in, allow, allow, total_psf, span_in <= allow + 0.5,
                     f"timber pre-engineering estimate ({gov} governs) — stamped design required")


def check_timber_beam(size: str, species: str, trib_depth_in: float, post_spacing_in: float, total_psf: float) -> SpanCheck:
    w = total_psf * trib_depth_in / 12.0
    allow, gov = timber_allowable_span(size, species, w, repetitive=False)
    return SpanCheck("beam", size, species, post_spacing_in, post_spacing_in, allow, allow, total_psf, post_spacing_in <= allow + 0.5,
                     f"timber pre-engineering estimate ({gov} governs) — stamped design required")


def timber_post_capacity_lb(size: str, species: str, height_in: float) -> float:
    """NDS column capacity (Euler-adjusted Fc') for a solid post."""
    b, d = LUMBER[size]
    v = TIMBER_DESIGN.get(species, TIMBER_DESIGN["DF#1"])["pt"]
    Fc = v["Fc"] * CD_SNOW
    le_d = height_in / min(b, d)
    FcE = 0.822 * v["E"] / le_d ** 2
    c = 0.8
    r = FcE / Fc
    Cp = (1 + r) / (2 * c) - math.sqrt(((1 + r) / (2 * c)) ** 2 - r / c)
    return Fc * Cp * b * d
