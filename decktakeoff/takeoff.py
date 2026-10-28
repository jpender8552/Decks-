"""Layout -> the takeoff: every line written the way Decks & Docks sells it, with NET (drawing count),
ORDER (PO quantity) and a one-line reason wherever they differ. Overage is explicit and small.

Quantities are accumulated across zones first (Q), then turned into lines once — so a three-zone deck gets one
cull per lumber length, not three. Two standards are encoded: dimensional (Jason Ct: 2x SYP, double rims, hangers
both ends, EdgeClips, Fulton) and timber (Eagle's Nest: 4x10 DF#1 on 6x12 / 8x8, caissons, Cortex, IRX)."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from . import engineering as eng
from .catalog import (rail_system_for, STOCK_LENGTHS_FT, deck_lengths, DOUBLE_HANGER, FASCIA, H25_NAILS, HANGER_FOR_JOIST, HANGER_NAILS, LUMBER_STOCK_FT, POST_BASE, POST_BASE_SCREWS,
                      POST_CAP_SCREWS, PRICEBOOK, SPECIES_NAMES, TIMBER_BASE, actual, decking_facts, default_fastener_system, parse_beam,
                      RAIL_SYSTEMS)
from .layout import OVERHANG_NO_FASCIA, NOSE, Layout, ZoneLayout, BeamLine, build_layout, LEDGER_T, RIM_PLY
from .spec import post_words, post_base_sku, covers_of, DeckSpec
from .units import ftin

CATEGORIES = ["Lumber", "Footings", "Hardware", "Flashing & waterproofing", "Decking", "Fasteners", "Fascia", "Rail", "Stairs", "Benches", "Planters", "Porch cover", "Shade sail", "Lighting", "Finish", "Site"]
BOARD_STOCK_IN = {12: 144.0, 16: 192.0, 20: 240.0}


@dataclass
class Line:
    category: str
    item: str            # as D&D sells it
    net: float
    order: float
    unit: str
    why: str             # "exact", "+2", "+1 cull", "330 clips needed · 360 supplied"
    unit_cost: float = 0.0
    source: str = ""
    sku: str = ""
    note: str = ""

    @property
    def ext(self) -> float:
        return round(self.order * self.unit_cost, 2)


@dataclass
class CutPiece:
    member: str
    nominal: str
    length_in: float
    qty: int
    note: str = ""


@dataclass
class Takeoff:
    spec: DeckSpec
    layout: Layout
    lines: List[Line]
    cut_list: List[CutPiece]
    schedule: Dict[str, str]          # fastener / connector schedule text
    summary: Dict[str, object]
    notes: List[str] = field(default_factory=list)
    joist_lf: float = 0.0             # LF of joist-size lumber (joists, rims, ledgers, blocking, doublers)
    timber_sf: float = 0.0            # timber surface for the oil option (every face that shows)
    model_lines: List[Line] = field(default_factory=list)   # the engine's own counts when the order came from the owner's quote
    order_ref: str = ""                                     # "Decks & Docks quote 979610"

    def __post_init__(self):          # extras.lights: the Lighting lines, once per takeoff (a composite redoes them for the whole job)
        from .lighting import finish_takeoff; finish_takeoff(self)

    def by_category(self) -> Dict[str, List[Line]]:
        out = defaultdict(list)
        for ln in self.lines:
            out[ln.category].append(ln)
        return {c: out[c] for c in CATEGORIES if out.get(c)}

    def material_total(self) -> float:
        return round(sum(l.ext for l in self.lines), 2)


# ------------------------------------------------------------------ helpers
def _hardie_words(spec) -> str:
    """The Hardie color named in extras.hardie_skirt ("4/4 x 12 Arctic White" -> "Arctic White")."""
    w = (spec.extras.hardie_skirt or "").split()
    return " ".join(w[-2:]) if len(w) > 1 else (spec.extras.hardie_skirt or "")


def _sku(d: dict, color: str = "", height: float = 36) -> str:
    """A pricebook entry's SKU in the job's color: "{c}" the IRX finish letter (B / W / BR), "{cc}" TimberTech's board color code
    (DO, AL), "{h}" the rail height — a White rail orders AZTIX36UNLP6W, never the Black ...B it was quoted as. A color with no
    known code gets no SKU (never a part number for the wrong color)."""
    from .catalog import COLOR_CODES
    s, c = (d or {}).get("sku") or "", (color or "").lower()
    fin = "W" if "white" in c else "BR" if "bronze" in c else "B" if "black" in c else ""
    if ("{c}" in s and not fin) or ("{cc}" in s and (color or "") not in COLOR_CODES):
        return ""
    return s.replace("{c}", fin).replace("{cc}", COLOR_CODES.get(color or "", "")).replace("{h}", f"{height:g}")


def _post_key(sysn: str, key: str, height: float) -> str:
    """The post a rail height takes (IRX order form 2023): over a 36" rail the level posts are the 3x3x43" kit (post_kit|42) and
    the stair posts the 48" sleeve (post_kit|48); a 36" rail, or a system without those entries, keeps its own key."""
    if height <= 36.5:
        return key
    alt = f"{sysn}|post_kit|{48 if key.endswith('|STAIR') else 42}"
    return alt if alt in PRICEBOOK["rail"] else key


def _h_src(d: dict, src: str, height: float) -> str:
    """The source of a rail kit whose SKU carries the rail height ("{h}"): over a 36" rail the price on file is the 36" kit's."""
    return f"EST — ask D&D: the {height:g}\" kit at the 36\" kit's price ({src})" if height > 36.5 and "{h}" in ((d or {}).get("sku") or "") else src


def _cortex(coll: str, color: str, field: bool = False) -> Tuple[dict, str, str]:
    """The Cortex kit a board takes, how its line reads and the kit: a composite board the 100 LF composite kit in its color
    (CTC100LFDO, 100 LF collated: 224 screws + 300 plugs) — a Cortex-screwed composite field the 300 SF collated kit (CTC300SFDO,
    1,050 screws + 1,200 plugs) — Advanced PVC the collated 350 ct kit."""
    mat = decking_facts(coll)["material"]
    if mat == "Composite" and field and "Cortex_TimberTech_300sf" in PRICEBOOK["decking"]:
        return PRICEBOOK["decking"]["Cortex_TimberTech_300sf"], f"Cortex for TimberTech Composite ({coll}), {color} plugs", "300 SF collated kit, 1,050 screws + 1,200 plugs"
    if mat == "Composite":
        return PRICEBOOK["decking"]["Cortex_TimberTech_100lf"], f"Cortex for TimberTech Composite ({coll}), {color} plugs", "100 LF collated kit, 224 screws + 300 plugs"
    return PRICEBOOK["decking"]["Cortex_TimberTech_350"], f"Cortex for TimberTech {mat}, {color} plugs", "350 ct / 100 SF"


def _riser_rips(st, tread_t: float) -> List[float]:
    """HardieTrim riser rip heights, top riser first (James Hardie TR1509 09/25): the rise less the tread less a 1/4" open gap over
    the tread below (Fig. 2 / 5); the bottom riser of a stair landing on soil holds 2" off it (Fig. 3) — a box step's bottom riser
    stops 1/4" over the hardscape / compacted base the box sits on (Fig. 2)."""
    soil = st.landing == "grade" and getattr(st, "build", "stringers") != "box"
    return [round(st.geo.riser_in - tread_t - (2.0 if soil and k == st.riser_pieces - 1 else 0.25), 3) for k in range(st.riser_pieces)]


def _price(section: str, key: str):
    d = PRICEBOOK.get(section, {}).get(key)
    if not d:
        return 0.0, "no price on file"
    return float(d.get("each", d.get("per_lf", 0.0))), d.get("source", "")


def _desc(section: str, key: str, default: str) -> str:
    return PRICEBOOK.get(section, {}).get(key, {}).get("desc", default)


def _item(section: str, key: str, default_desc: str = "") -> Tuple[str, float, str]:
    d = PRICEBOOK.get(section, {}).get(key) or {}
    return d.get("desc", default_desc or key), float(d.get("each", d.get("per_lf", 0.0))), d.get("source", "no price on file")


def stair_name(ss, st=None) -> str:
    """A stair as the client reads it: its own name, else from the side it leaves."""
    if getattr(ss, "name", None):
        return ss.name
    side = getattr(ss, "side", "") or ""
    if side.startswith("step:"):
        return side                      # renamed to "<zone> side, toward the <zone>" once the takeoff is built
    box = st is not None and getattr(st, "build", "") == "box"
    base = "Box step" if box else "Stair"
    if side in ("front", "") or side.startswith("front:"):
        return f"{base} at the front"
    if side in ("left", "end:left"):
        return f"{base} on the left end"
    if side in ("right", "end:right"):
        return f"{base} on the right end"
    return base


def inches_frac(v: float, frac: int = 16) -> str:
    n = round(v * frac)
    whole, rem = divmod(int(n), frac)
    if rem == 0:
        return f'{whole}"'
    g = math.gcd(rem, frac)
    return f'{whole}-{rem // g}/{frac // g}"'


def _lumber_price(nominal: str, stock_ft: int, timber: bool = False):
    key = f"{nominal}_DF#1" if (timber or nominal not in PRICEBOOK["lumber"]) and f"{nominal}_DF#1" in PRICEBOOK["lumber"] else nominal
    d = PRICEBOOK["lumber"].get(key)
    if not d:
        return 0.0, "no price on file"
    ln = d.get("lengths", {}).get(str(stock_ft))          # D&D's documented price for this length, else the per-LF estimate
    return (float(ln["each"]), ln["source"]) if ln else (round(d["per_lf"] * stock_ft, 2), d["source"])


def _stock_for_piece(nominal: str, length_in: float) -> int:
    for s in LUMBER_STOCK_FT.get(nominal, [8, 10, 12, 16, 20]):
        if length_in <= s * 12 + 0.01:
            return s
    return LUMBER_STOCK_FT.get(nominal, [20])[-1]


def pack_plan(pieces: List[Tuple[str, float, str]], kerf: float = 0.25, short_stock_ft: int = 12, price=None, known=None) -> List[Tuple[str, int, List[Tuple[float, str, int]]]]:
    """The cut plan, one (nominal, stock_ft, [(length_in, label, index in pieces), ...]) per board. A piece over 8' gets the shortest
    stock that fits, one to a board; the shorter pieces (blocks, short rims) fill those boards' offcuts first — longest first, each
    into the tightest offcut that takes it — and only then open new `short_stock_ft` boards (first fit). With price(nominal, stock_ft)
    a length is dropped when cutting its pieces from the next length up already in the order costs less than that length's cull
    (1 per length): two 10' joists come from 12' stock, but fifteen 14' joists never move up to 20' to carry a rim in the offcut.
    known(nominal, stock_ft): the lengths a piece may move up to (D&D's documented prices) — a lone 16' never moves onto an EST 24'."""
    plan: List[Tuple[str, int, List[Tuple[float, str, int]]]] = []
    by_nom: Dict[str, List[Tuple[float, str, int]]] = defaultdict(list)
    for i, (nom, L, label) in enumerate(pieces):
        by_nom[nom].append((L, label, i))
    for nom, lst in by_nom.items():
        longs = [p for p in lst if p[0] > 96]
        shorts = sorted((p for p in lst if p[0] <= 96), key=lambda t: -t[0])
        def cut(drop=None):
            bd = []                                       # [stock_ft, room left (in), pieces]
            for p in longs:
                st = _stock_for_piece(nom, p[0])
                while drop and st in drop:                # a dropped length: the length up it moves to
                    st = drop[st]
                bd.append([st, st * 12.0 - p[0] - kerf, [p]])
            n_long = len(bd)
            for p in shorts:
                fit = [b for b in bd[:n_long] if b[1] >= p[0] + kerf - 1e-9]
                b = min(fit, key=lambda b: b[1]) if fit else next((b for b in bd[n_long:] if b[1] >= p[0] + kerf - 1e-9), None)
                if b is None:
                    b = [short_stock_ft, short_stock_ft * 12.0, []]; bd.append(b)
                b[1] -= p[0] + kerf; b[2].append(p)
            return bd
        boards = cut()
        if price:
            open_, drop = sorted({b[0] for b in boards}), {}
            for s in open_:
                up = min((u for u in open_ if u > s and (known is None or known(nom, u))), default=None)   # the next length up in the order, priced
                n_s = sum(1 for b in boards if b[0] == s)
                if up and s != short_stock_ft and n_s * (price(nom, up) - price(nom, s)) < price(nom, s):     # (the short stock stays)
                    drop[s] = up
                    boards = cut(drop)
        plan += [(nom, b[0], b[2]) for b in boards]
    return plan


def pack_lumber(pieces: List[Tuple[str, float, str]], kerf: float = 0.25, short_stock_ft: int = 12, price=None, known=None) -> Dict[Tuple[str, int], Tuple[int, List[str]]]:
    """pieces: (nominal, length_in, label), cut per pack_plan. Returns {(nominal, stock_ft): (count, one label per board)}, in the order
    the pieces first call for each length (a long piece's own stock first, the short stock after)."""
    out: Dict[Tuple[str, int], Tuple[int, List[str]]] = {}
    first: Dict[Tuple[str, int], Tuple[int, int]] = {}
    for nom, st, cut_ in pack_plan(pieces, kerf, short_stock_ft, price, known):
        c, labels = out.get((nom, st), (0, []))
        own = [cut_[0][1]] if cut_[0][0] > 96 else []          # a long piece's board reads by it first, then what its offcut gives
        out[(nom, st)] = (c + 1, labels + [", ".join(own + sorted({lab for _, lab, _ in cut_} - set(own)))])
        first[(nom, st)] = min([first.get((nom, st), (2, 0))] + [((0 if L > 96 else 1), i) for L, _, i in cut_])
    return {k: out[k] for k in sorted(out, key=lambda k: first[k])}


def pack_boards(pieces: List[Tuple[str, float]], stocks=(16, 20), kerf: float = 0.125) -> Dict[int, List[List[Tuple[str, float]]]]:
    """Pack deck-board pieces (label, length) first-fit-decreasing into the longest stock, then relabel each board
    with the shortest stock that holds it. Returns {stock_ft: [[pieces in board], ...]}."""
    cap = max(stocks) * 12
    split = []
    for label, L in pieces:             # a piece longer than the longest stock is two (or more) boards, joined over a bearing point
        n = int(math.ceil(L / (cap - kerf))) if L > cap else 1
        split += [(f"{label} ({i + 1} of {n})" if n > 1 else label, L / n) for i in range(n)]
    pieces = split
    bins: List[List[Tuple[str, float]]] = []
    for label, L in sorted(pieces, key=lambda t: -t[1]):
        L = min(L, cap)
        for b in bins:
            if sum(x[1] + kerf for x in b) + L + kerf <= cap:
                b.append((label, L)); break
        else:
            bins.append([(label, L)])
    out: Dict[int, List[List[Tuple[str, float]]]] = defaultdict(list)
    for b in bins:
        used = sum(x[1] + kerf for x in b)
        st = next((s for s in sorted(stocks) if used <= s * 12 - 2.0 + 1e-6), max(stocks))   # within 2" of a stock length -> step up
        out[st].append(b)
    return out


def repack_boards(packed: Dict[int, List[List[Tuple[str, float]]]], stocks=(16, 20), kerf: float = 0.125) -> Dict[int, List[List[Tuple[str, float]]]]:
    """pack_boards' cut plan bettered two boards at a time: every split of a pair's pieces is tried and kept when the pair takes less
    stock, so a long piece can drop to a shorter board (Prentice square edge: 7 x 20' + 16' -> 6 x 20' + 2 x 16'). Same rules: kerf
    per piece, a board within 2" of a length steps up."""
    def need(b):
        used = sum(x[1] + kerf for x in b)
        if used > max(stocks) * 12 + 1e-6 and len(b) > 1:     # a lone piece is a whole board (a full-length 12' fascia)
            return None
        return next((s for s in sorted(stocks) if used <= s * 12 - 2.0 + 1e-6), max(stocks)) if b else 0
    bins = [list(b) for _, v in sorted(packed.items()) for b in v]
    better = True
    while better:
        better = False
        for i in range(len(bins)):
            for j in range(i + 1, len(bins)):
                pcs = bins[i] + bins[j]
                if len(pcs) > 12:
                    continue
                best, keep = need(bins[i]) + need(bins[j]), None
                for m in range(1, 2 ** len(pcs)):            # every split, all on one board included
                    a = [p for k, p in enumerate(pcs) if m >> k & 1]; b = [p for k, p in enumerate(pcs) if not m >> k & 1]
                    na, nb = need(a), need(b)
                    if na is not None and nb is not None and na + nb < best - 1e-9:
                        best, keep = na + nb, (a, b)
                if keep:
                    bins[i], bins[j], better = keep[0], keep[1], True
        bins = [b for b in bins if b]
    out: Dict[int, List[List[Tuple[str, float]]]] = defaultdict(list)
    for b in sorted(bins, key=lambda b: -sum(x[1] for x in b)):
        out[need(b)].append(sorted(b, key=lambda x: -x[1]))
    return out


def _offcut_spare(packed: Dict[int, List[List[Tuple[str, float]]]], longest: float, kerf: float = 0.125) -> float:
    """The longest offcut of a cut plan when it already holds the longest piece (that offcut is the spare), else 0."""
    o = max([s * 12 - sum(x[1] + kerf for x in b) for s, bs in packed.items() for b in bs] or [0.0])
    return o if o >= longest + kerf else 0.0


def field_lengths(spec: DeckSpec) -> tuple:
    """The stocks a field row may be cut from: the line's own profile, plus the lengths it is sold in grooved only when the field is
    face-screwed with Cortex (owner: "you can use 12' grooved even with cortex" — the groove never shows between field boards)."""
    c, p = spec.decking.collection, spec.decking.profile
    own = deck_lengths(c, p)
    if p == "square" and (spec.decking.fastener_system or default_fastener_system(c, p)) == "Cortex":
        return tuple(sorted(set(own) | set(deck_lengths(c, "grooved"))))
    return own


def field_profile(spec: DeckSpec, stock: int) -> str:
    """The profile a field board of this stock is ordered in: the line's own, else grooved (a length sold grooved only)."""
    return spec.decking.profile if stock in deck_lengths(spec.decking.collection, spec.decking.profile) else "grooved"


def _deck_base(spec: DeckSpec, black: bool = False) -> str:
    """The deck's post base on a caisson: TIMBER_BASE by post size, the R-series ABU88 for a rough 8x8."""
    bkeys = TIMBER_BASE.get(spec.framing.post_size, ("ABU66Z_black", "ABU66Z"))
    bkey = bkeys[0] if black else bkeys[1]
    return "ABU88RZ" if (bkey == "ABU88Z" and spec.framing.post_rough) else bkey


def site_lines(spec: DeckSpec, deck_sf: float) -> List[Line]:
    """The job's site lines (demo, site extras) — once per job: a composite adds them once, not once per part."""
    out = []
    if spec.extras.demo_existing:
        sf_demo = spec.extras.demo_sf or deck_sf
        out.append(Line("Site", "Demo existing deck + haul-off", sf_demo, sf_demo, "SF", "labor line — field verify the existing deck", 0.0, "labor"))
    for x in spec.extras.site_extras:
        out.append(Line("Site", x.get("item", "site extra"), 1, 1, "ea", "at cost", float(x.get("cost", 0)), "at cost"))
    return out


def _summarize_labels(labels: List[str]) -> str:
    cnt = Counter(labels)
    return " · ".join(f"{v} {k}" if v > 1 else k for k, v in cnt.items())


def _hw(key: str, black: bool) -> Tuple[str, float, str, str]:
    """hardware line: (desc, unit cost, source, sku) — black powder-coat variant when the job calls for it."""
    k = f"{key}_black" if black and f"{key}_black" in PRICEBOOK["hardware"] else key
    d = PRICEBOOK["hardware"].get(k) or PRICEBOOK["footings"].get(k) or {"desc": f"Simpson {key}", "each": 0.0, "source": "no price on file"}
    return d.get("desc", f"Simpson {key}"), float(d.get("each", 0.0)), d.get("source", ""), key


# ------------------------------------------------------------------ quantities across zones
@dataclass
class Q:
    lumber: List[Tuple[str, float, str]] = field(default_factory=list)
    cuts: List[CutPiece] = field(default_factory=list)
    n_joists: int = 0
    hangers_single: int = 0
    hangers_double: int = 0
    hangers_skew: int = 0          # 45-degree skewed hangers (joists into an angled rim)
    hangers_skew_double: int = 0
    hangers_field: int = 0         # field-skewable hangers (joists into a bay face at the house's own angle)
    hangers_field_double: int = 0
    bay_angles: str = ""
    h25: int = 0
    ledger_len: float = 0.0
    ledger_fasteners: int = 0
    ledger_rule: str = ""
    n_blocks: int = 0
    block_rows: int = 0
    rss_lam: int = 0
    tape_joist_lf: float = 0.0       # single-member tops (2" on dimensional; 4" on 4x timber)
    tape_wide_lf: float = 0.0        # rims / beams (4")
    tape_block_lf: float = 0.0
    field_boards: Counter = field(default_factory=Counter)      # stock_ft -> boards
    field_rows: int = 0
    field_piece_note: List[str] = field(default_factory=list)
    rip_strips: List[float] = field(default_factory=list)
    border_pieces: List[Tuple[str, float]] = field(default_factory=list)
    fascia_pieces: List[Tuple[str, float]] = field(default_factory=list)
    clips: int = 0
    bearing_points: int = 0
    gaps: int = 0
    first_row: int = 0
    border_screws: int = 0
    fascia_screws: int = 0
    timber_ends: int = 0
    joist_lf: float = 0.0
    front_flush: bool = False
    n_zones: int = 0


def _field_runs(spec: DeckSpec, L: Layout, z: ZoneLayout, zi: int) -> List[Tuple[int, float, str]]:
    """(rows, run length, label) for the field boards of one zone, split by dividers. Rows past a boundary divider that
    stops well short of this zone's wall run to the zone line (Eagle's Nest C2)."""
    dk = z.decking
    bw, gap = dk.bw, dk.gap
    edge = dk.deck_w and (dk.deck_w - z.W) / 2          # overhang / fascia per side
    pf = spec.geometry.picture_frame
    zones = L.zones
    left_bound = right_bound = None
    for x, Ld, lab in L.divider_x:
        if abs(x - z.x0) < 0.6 and zi > 0:
            left_bound = Ld
        if abs(x - (z.x0 + z.W)) < 0.6 and zi < len(zones) - 1:
            right_bound = Ld
    mids = sorted(x for x, Ld, lab in L.divider_x if z.x0 + 0.6 < x < z.x0 + z.W - 0.6)
    # x extents of the field: outer end borders on exposed ends, divider boards on zone lines
    def trim(side_is_end: bool, bound: Optional[float], y: float) -> float:
        if side_is_end:
            return (bw + gap) if pf else 0.0
        if bound is None:
            return 0.0
        return (bw + gap) if (y <= bound + 0.5 or bound >= z.D - 24) else 0.0
    rows_out: Dict[Tuple[float, ...], int] = {}
    for i in range(dk.rows):
        y = gap + bw + gap + i * (bw + gap) + bw / 2 if pf else i * (bw + gap) + bw / 2     # from the front edge
        lt = trim(zi == 0, left_bound, y)
        rt = trim(zi == len(zones) - 1, right_bound, y)
        xs = [z.x0 - edge + lt] + [m for m in mids] + [z.x0 + z.W + edge - rt]
        runs = tuple(round(b - a - (bw + gap if 0 < k < len(xs) - 1 else 0) - (bw / 2 + gap if k == 1 and mids else 0) - (bw / 2 if k == len(xs) - 2 and mids and k >= 1 else 0), 2)
                     for k, (a, b) in enumerate(zip(xs, xs[1:])))
        rows_out[runs] = rows_out.get(runs, 0) + 1
    out = []
    for runs, n in rows_out.items():
        for k, r in enumerate(runs):
            out.append((n, r, f"{z.name}{k + 1 if len(runs) > 1 else ''}"))
    return out


def _accumulate_field_plan(Q_: Q, spec: DeckSpec, L: Layout) -> None:
    """Field boards from the outline plan: every row segment is one board (no butt joints), rips are whole boards ripped."""
    P = L.plan
    fr0 = L.zones[0].frame
    cortex = (spec.decking.fastener_system or default_fastener_system(spec.decking.collection, spec.decking.profile)) == "Cortex"
    cut_groups: Dict[Tuple[int, int, bool], int] = {}
    for r in P.rows:
        key = (r.panel, int(round(r.length)), r.rip)
        cut_groups[key] = cut_groups.get(key, 0) + 1
        crossings = int(round(r.length / fr0.spacing)) + 2
        Q_.clips += crossings * (2 if cortex else 1)
        Q_.bearing_points += crossings
    # cut the rows from stock: the short rows beside the steps and the bay come two or three to a board
    packed = pack_boards([(f"panel {r.panel + 1}", r.length + 0.25) for r in P.rows], stocks=field_lengths(spec))
    for stock, boards in sorted(packed.items()):
        Q_.field_boards[stock] += len(boards)
        multi = sum(1 for b in boards if len(b) > 1)
        Q_.field_piece_note.append(f"{len(boards)} x {stock}'" + (f" ({multi} cut into 2-3 rows)" if multi else ""))
    Q_.field_piece_note.append(" · ".join(f"panel {i + 1} {n} rows" for i, (_, _, n, _) in enumerate(P.panels)) + " · every row one piece")
    for (pi, ln, rip), n in sorted(cut_groups.items()):
        Q_.cuts.append(CutPiece(f"Field boards panel {pi + 1}" + (" (rip)" if rip else ""), f"{spec.decking.collection} {spec.decking.color}", float(ln), n,
                                "one board wall to border, no joints" + ("; ripped to fit the border / the house" if rip else "")))
    Q_.field_rows += P.n_rows


def accumulate(Q_: Q, spec: DeckSpec, L: Layout, z: ZoneLayout, zi: int) -> None:
    fr, dk = z.frame, z.decking
    tag = f" ({z.name})" if L.multi else ""
    jsize = fr.joist_size
    jb, jd = actual(jsize)
    timber = spec.is_timber
    lsize = spec.ledger_size
    n_field, n_pf = len(fr.joist_x), len(fr.pf_x)
    # the joists at the breakers, as the 3D draws them (layout.zone_divider_framing): on a breaker's zone line the zone's picture-frame
    # joist moves tight inside its rim (a field joist added only where that opens a bay past the spacing); inside a zone a joist each
    # side of the breaker, its inside face under the board ends (it replaces a joist between), the breaker on blocks between
    n_div_here, n_extra, blk_ = 0, 0, []
    if L.divider_x and not (L.multi and L.outline_edges):           # (an outline frame counts its own: _rims_from_outline)
        from .layout import zone_divider_framing
        jx_, blk_, _ = zone_divider_framing(L, zi)
        n_extra = len(jx_) - n_field - n_pf
        n_field, n_pf, n_div_here = (sum(1 for _, l in jx_ if l == "joist"), sum(1 for _, l in jx_ if l == "PF joist"),
                                     sum(1 for _, l in jx_ if l.startswith("divider")))
    Q_.n_joists += n_field + n_pf + n_div_here
    rear_t = jb if fr.ledger else fr.rim_plies * jb
    # ---- joists (one bay, or hung on both faces of a mid flush beam)
    flush_mid = [b for b in fr.beams if b.kind == "flush" and b.cl_y + b.width / 2 < z.D - 0.5]
    if not flush_mid:
        Q_.lumber += [(jsize, fr.joist_len, "field joist")] * n_field + [(jsize, fr.joist_len, "PF joist")] * n_pf
        Q_.cuts.append(CutPiece(f"Field joists{tag}", jsize, fr.joist_len, n_field, f"@ {fr.spacing:g}\" OC, crown up"))
        if n_pf:
            Q_.cuts.append(CutPiece(f"Picture-frame joists{tag}", jsize, fr.joist_len, n_pf, f"center {ftin(fr.pf_x[0])} from each frame face"))
    else:
        sup = [rear_t] + [b.cl_y for b in flush_mid] + [z.D - fr.rim_plies * jb]
        bws = [0.0] + [b.width for b in flush_mid] + [0.0]
        for i, (a, b) in enumerate(zip(sup, sup[1:])):
            ln = round((b - bws[i + 1] / 2) - (a + bws[i] / 2) - 0.25, 2) if i < len(sup) - 2 else round(b - (a + bws[i] / 2) - 0.25, 2)
            lab = "joist upper (wall to the flush beam)" if i == 0 else "joist lower (flush beam to the rim)"
            Q_.lumber += [(jsize, ln, lab)] * (n_field + n_pf + n_div_here)
            Q_.cuts.append(CutPiece(f"Joists {'upper' if i == 0 else 'lower'}{tag}", jsize, ln, n_field + n_pf + n_div_here,
                                    ("hung on the inner face of the flush beam" if i == 0 else "hung on the outer face of the flush beam, bears the drop beam")
                                    + (f"; {n_div_here} of them divider joists at the breakers" if n_div_here else "")))
    # ---- the divider joists and the blocks under a breaker inside the zone
    if n_div_here and not flush_mid:          # (hung on a mid flush beam they are in the upper / lower joist pieces above)
        Q_.lumber += [(jsize, fr.joist_len, "divider joist")] * n_div_here
        Q_.cuts.append(CutPiece(f"Divider joists{tag}", jsize, fr.joist_len, n_div_here, "at the breakers: on a zone line the picture-frame joist tight inside the rim, "
                                "inside a zone one each side of the breaker line — every field-board end bears a full joist"))
    if blk_:
        Q_.lumber += [(jsize, round(xb - xa, 2), "breaker block") for xa, xb, yc, lab in blk_]
        Q_.n_blocks += len(blk_)
        Q_.cuts.append(CutPiece(f"Breaker blocks{tag}", jsize, max(xb - xa for xa, xb, yc, lab in blk_), len(blk_),
                                f"square cut between the divider joists, @ {min(spec.joist_spacing, 16.0):g}\" OC max; the breaker board rides them"))
    # ---- rims / ledger
    side_len = fr.joist_len
    for side in ("left", "right"):
        Q_.lumber += [(jsize, side_len, f"{side} rim ply")] * fr.rim_plies
    Q_.cuts.append(CutPiece(f"Side rim plies{tag}", jsize, side_len, 2 * fr.rim_plies,
                            f"{fr.rim_plies}-ply, laminated on the ground with RSS 2 rows @ 12\" staggered" if fr.rim_plies > 1 else "single 4x rim"))
    front_flush = any(b.label.startswith("FRONT FLUSH") for b in fr.beams)
    Q_.front_flush = Q_.front_flush or front_flush
    if not front_flush:
        Q_.lumber += [(jsize, z.W, "front rim ply")] * fr.rim_plies
        Q_.cuts.append(CutPiece(f"Front rim plies{tag}", jsize, z.W, fr.rim_plies, "inner ply takes the hangers; outer ply laminated after" if fr.rim_plies > 1 else "single 4x rim, end-nailed"))
    if fr.ledger:
        Q_.lumber.append((lsize, z.W, "ledger"))
        Q_.cuts.append(CutPiece(f"Ledger{tag}", lsize, z.W, 1, "top at deck height less board thickness; membrane behind, flashing over"))
        Q_.ledger_len += z.W
    else:
        Q_.lumber += [(jsize, z.W, "rear rim ply")] * fr.rim_plies
        Q_.cuts.append(CutPiece(f"Rear rim plies (freestanding){tag}", jsize, z.W, fr.rim_plies, ""))
    # ---- blocking
    n_block_rows = len(fr.blocking_rows_y)
    if n_block_rows:
        Q_.lumber += [(jsize, fr.block_len, "blocking")] * (fr.n_blocks_per_row * n_block_rows)
        Q_.n_blocks += fr.n_blocks_per_row * n_block_rows
        Q_.block_rows = max(Q_.block_rows, n_block_rows)
        Q_.cuts.append(CutPiece(f"Blocking{tag}", jsize, fr.block_len, fr.n_blocks_per_row * n_block_rows,
                                f"{n_block_rows} row{'s' if n_block_rows > 1 else ''} at " + ", ".join(ftin(y) for y in fr.blocking_rows_y) + " from the wall"))
    if spec.geometry.picture_frame and spec.geometry.board_direction != "parallel":
        Q_.lumber += [(jsize, fr.block_len, "PF blocking")] * (n_field + 1)
        Q_.cuts.append(CutPiece(f"Picture-frame blocking{tag}", jsize, fr.block_len, n_field + 1, "row behind the front rim so the front border ends bear"))
    # ---- connectors
    if timber:
        # hangers at the ledger (joists + the two rim ends), both faces of a mid flush beam; the front rim is end-nailed and the joists bear the drop beam
        Q_.hangers_single += (n_field + n_pf + n_div_here) * (1 + 2 * len(flush_mid)) + (2 if fr.ledger else 0)      # a divider joist hangs on its own
        Q_.hangers_double += 2 * len(flush_mid)
        Q_.h25 += sum((n_field + n_pf + n_div_here + 2) for b in fr.beams if b.kind == "drop")
    else:
        Q_.hangers_single += fr.hangers_single + n_extra * 2 * (1 + len(flush_mid))      # as the frame hangs its joists: both ends, both beam faces
        Q_.hangers_double += fr.hangers_double
        Q_.h25 += fr.h25_ties + n_extra * sum(1 for b in fr.beams if b.kind == "drop")
    lam = 0
    if fr.rim_plies > 1:
        lam += 2 * 2 * (int(math.ceil(side_len / 12)) + 1)
        lam += 2 * (int(math.ceil(z.W / 12)) + 1) * (fr.rim_plies - 1) * (0 if front_flush else 1)
        if not fr.ledger:
            lam += 2 * (int(math.ceil(z.W / 12)) + 1)
    Q_.rss_lam += lam
    # ---- tape
    Q_.tape_joist_lf += ((n_field + n_pf + n_div_here) * fr.joist_len + (z.W if fr.ledger else 0)) / 12.0
    Q_.tape_wide_lf += (2 * side_len + z.W * (1 if fr.ledger else 2)) / 12.0
    Q_.tape_block_lf += (fr.n_blocks_per_row * n_block_rows * fr.block_len + sum(xb - xa for xa, xb, yc, lab in blk_)) / 12.0
    # ---- timber surface / ends
    if timber:
        pieces_here = (n_field + n_pf + n_div_here) * (2 if flush_mid else 1) + 2 * fr.rim_plies + (0 if front_flush else fr.rim_plies) + (1 if fr.ledger else fr.rim_plies) + fr.n_blocks_per_row * n_block_rows + len(blk_)
        Q_.timber_ends += 2 * pieces_here
    # ---- decking: field boards per run, rips, cortex per run (an outline-laid plan is counted once, after the zones)
    runs = ([] if L.plan is not None else (_field_runs(spec, L, z, zi) if L.multi else [(dk.rows, dk.field_len, z.name)]))
    _dl = field_lengths(spec)
    for n_rows, run_len, lab in runs:
        k = max(1, int(math.ceil(run_len / 240.0)))
        piece = run_len / k
        stock = next((s for s in _dl if piece <= s * 12 + 0.01), _dl[-1])
        n_b, per = n_rows * k, 1
        # short rows: cut 2 or 3 from one longer board when that buys fewer LF (7' rows: two from a 16')
        for m in (2, 3):
            st_m = next((s for s in _dl if m * (piece + 0.25) <= s * 12 + 0.01), None)
            if st_m and int(math.ceil(n_rows * k / m)) * st_m < n_b * stock / per:
                stock, n_b, per = st_m, int(math.ceil(n_rows * k / m)), m
        Q_.field_boards[stock] += n_b
        Q_.field_piece_note.append(f"{lab}: {n_rows} rows @ {ftin(piece)}" + (f" x {k}" if k > 1 else "") + (f", {per} per {stock}' board" if per > 1 else ""))
        Q_.cuts.append(CutPiece(f"Field boards run {lab}", f"{spec.decking.collection} {spec.decking.color}", piece, n_rows * k, "boards run parallel to the house" if dk.direction == "parallel" else "boards run out from the house"))
        # bearing points in this run: joists within + the two ends (rim/divider cluster)
        crossings = int(round(run_len / fr.spacing)) + 2
        if (spec.decking.fastener_system or default_fastener_system(spec.decking.collection, spec.decking.profile)) == "Cortex":
            Q_.clips += n_rows * crossings * 2
        else:
            Q_.clips += n_rows * crossings
        Q_.bearing_points += crossings
    Q_.field_rows += dk.rows if L.plan is None else 0
    if dk.last_row_dev < -0.5 and L.plan is None:
        rip = -dk.last_row_dev - dk.gap
        Q_.rip_strips += [rip] * len(runs)
        Q_.cuts.append(CutPiece(f"Rip at the house{tag}", f"{spec.decking.collection} {spec.decking.color}", runs[0][1], len(runs), f"rip to {rip:.2f}\""))
    Q_.gaps += dk.gaps
    Q_.first_row += dk.first_row_screws
    if not L.multi:
        Q_.border_pieces += [(n, Lb) for n, Lb in dk.border_pieces]
        Q_.border_screws += dk.border_screws
    Q_.fascia_pieces += [(f"{n}{tag}", Lb) for n, Lb in dk.fascia_pieces]
    Q_.fascia_screws += dk.fascia_screws


# ------------------------------------------------------------------ the takeoff
def _rims_from_outline(Q_: Q, spec: DeckSpec, L: Layout) -> None:
    """A polygon outline: the frame comes from layout.outline_framing — one continuous field, what the drawings show.
    Replaces the zone-rectangle joists, rims, ledger, side rims, fascia, hangers and joist tape with the outline's own."""
    from .layout import outline_framing
    OF = outline_framing(spec, L)
    if OF is None:
        return
    jsize = spec.framing.joist_size
    jb, jd = actual(jsize)
    plies = L.zones[0].frame.rim_plies
    drop_lab = ("left rim ply", "right rim ply", "front rim ply", "rear rim ply", "ledger", "field joist", "PF joist", "divider doubler", "divider joist",
                "joist upper (wall to the flush beam)", "joist lower (flush beam to the rim)", "blocking", "PF blocking")
    Q_.lumber = [q for q in Q_.lumber if q[2] not in drop_lab]
    drop_cut = ("Side rim plies", "Front rim plies", "Rear rim plies", "Ledger", "Field joists", "Picture-frame joists", "Joists upper",
                "Joists lower", "Divider doublers", "Blocking", "Picture-frame blocking")
    Q_.cuts = [c for c in Q_.cuts if not c.member.startswith(drop_cut)]
    # joists: every piece at its own length (the packer picks the stock)
    jl = {}
    for X, a, b, ea, eb, lab in OF.joists:
        ln = round(b - a - 0.25, 2)                     # 1/8" at each end
        Q_.lumber.append((jsize, ln, "joist (outline)" if not lab.startswith("divider") else "divider joist"))
        jl.setdefault(lab.split(" D")[0] if lab.startswith("divider") else lab, []).append(ln)
    for lab, lens in jl.items():
        Q_.cuts.append(CutPiece(f"{lab.capitalize()}s (outline)", jsize, max(lens), len(lens),
                                f"{len(lens)} pieces, {min(lens) / 12:.1f}'-{max(lens) / 12:.1f}' — each cut to the outline (bevel 45 at the angled rims), see the framing plan"))
    Q_.n_joists = len(OF.joists)
    Q_.joist_lf = sum(b - a for _, a, b, *_ in OF.joists) / 12.0
    # rims: every ply its own mitered length
    rim_lf = 0.0
    for i, k, x0, y0, x1, y1 in OF.rims:
        ln = round(math.hypot(x1 - x0, y1 - y0), 2)
        rim_lf += ln
        Q_.lumber.append((jsize, ln, "outline rim ply"))
    for i in sorted({r[0] for r in OF.rims}):
        lens = [math.hypot(r[4] - r[2], r[5] - r[3]) for r in OF.rims if r[0] == i]
        if OF.side_kind[i] == "trimmer":     # an inset stair's notch: the inner face is a doubled trimmer the deck's full depth
            Q_.cuts.append(CutPiece(f"Stair-notch trimmer (side {i + 1})", jsize, max(lens), len(lens),
                                    f"{len(lens)}-ply, ledger to the front rim, laminated RSS 2 rows @ 12\"; a double hanger each end; the stringers and both headers hang on it"))
            continue
        Q_.cuts.append(CutPiece(f"Rim side {i + 1} ({OF.side_kind[i]})", jsize, max(lens), len(lens),
                                ("mitered both ends" if OF.side_kind[i] != "rim" else "square / mitered to the neighbors")
                                + (", 1/2\" off the bay face — no ledger on the cantilevered bay" if OF.side_kind[i] == "bay45" else "")
                                + (", plies laminated RSS 2 rows @ 12\" staggered" if plies > 1 else "")))
    # ledger + ledger blocks
    Q_.ledger_len = 0.0
    for x0, y0, x1, y1 in OF.ledgers:
        ln = math.hypot(x1 - x0, y1 - y0)
        Q_.ledger_len += ln
        Q_.lumber.append((spec.ledger_size, round(ln, 2), "ledger"))
        Q_.cuts.append(CutPiece("Ledger (main wall)" if abs(y0) < 1.0 and abs(y1) < 1.0 else "Ledger (bay face)", spec.ledger_size, round(ln, 2), 1,
                                "top at deck height less the board; membrane behind, flashing over; LedgerLOK per the schedule"))
    for x0, y0, x1, y1 in OF.ledger_blocks:
        ln = math.hypot(x1 - x0, y1 - y0)
        Q_.ledger_len += ln
        Q_.lumber.append((spec.ledger_size, round(ln, 2), "ledger block"))
        Q_.cuts.append(CutPiece("Ledger block (beside the bay)", spec.ledger_size, round(ln, 2), 1, "3 LedgerLOKs, flashed; the two angled rims hang from it (skewed double hanger)"))
    # blocking under the 45-degree borders; the blocks that carry each breaker between its two divider joists (and the one at a
    # breaker's end where a divider joist stops short on an angled ledger / rim, beveled to that member)
    blk = [math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1, lab in OF.blocks if not lab.startswith("divider")]
    dbk = [math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1, lab in OF.blocks if lab.startswith("divider block")]
    dbe = [math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1, lab in OF.blocks if lab.startswith("divider end block")]
    Q_.lumber += [(jsize, round(b_ + 1.0, 2), "PF block (angled border)") for b_ in blk]     # +1" for the bevel cuts
    Q_.lumber += [(jsize, round(b_, 2), "breaker block") for b_ in dbk] + [(jsize, round(b_ + 1.0, 2), "breaker end block") for b_ in dbe]
    if blk:
        Q_.cuts.append(CutPiece("Blocks under the 45-degree borders", jsize, max(blk), len(blk), "a line 1-1/2\" inside the rim, one per joist bay, bevel both ends"))
    if dbk:
        Q_.cuts.append(CutPiece("Breaker blocks between the divider joists", jsize, max(dbk), len(dbk),
                                f"square cut, joist face to joist face, @ {min(spec.joist_spacing, 16.0):g}\" OC max from the ledger to 3/4\" under the breaker's end at the front border; the breaker board rides them"))
    if dbe:
        Q_.cuts.append(CutPiece("Breaker end block" + ("s" if len(dbe) > 1 else ""), jsize, max(dbe), len(dbe),
                                "at a breaker's end where one divider joist stops short on an angled ledger or rim: from the other divider joist to that member, beveled to it"))
    Q_.n_blocks = len(blk) + len(dbk) + len(dbe)
    # hangers: every joist end by what it lands on
    Q_.hangers_single = sum((e in ("ledger", "beam", "rim")) for _, _, _, ea, eb, _ in OF.joists for e in (ea, eb))
    Q_.hangers_skew = sum((e in ("rim45", "bay45")) for _, _, _, ea, eb, _ in OF.joists for e in (ea, eb))
    Q_.hangers_field = sum((e == "ledger45") for _, _, _, ea, eb, _ in OF.joists for e in (ea, eb))     # a bay face runs at the house's angle, not 45
    rl_ = list(getattr(OF, "rim_ledger", []))
    Q_.hangers_double = rl_.count("square") + getattr(OF, "notch_hangers", 0)     # + an inset stair notch's trimmer ends and headers
    Q_.hangers_skew_double = 2 * len(OF.ledger_blocks) + rl_.count("skew45")
    Q_.hangers_field_double = rl_.count("field")
    Q_.skew_double_note = ("the two angled rims at the ledger block beside the bay" if OF.ledger_blocks else
                           "the doubled angled rim where it dies into the main-wall ledger" if rl_.count("skew45") == 1 else "the doubled angled rims where they die into the ledger")
    poly_ = [(float(x) * 12, float(y) * 12) for x, y in spec.geometry.outline]
    Q_.bay_angles = " / ".join(sorted({f"{math.degrees(math.atan2(abs(poly_[(i + 1) % len(poly_)][1] - poly_[i][1]), abs(poly_[(i + 1) % len(poly_)][0] - poly_[i][0]))):.0f}°"
                                       for i, k_ in enumerate(OF.side_kind) if k_ == "ledger45"}))
    # skewed hangers by hand (Simpson: SUR when the joist runs off to the right, seen from the joist side facing the header)
    def _side_n(i, px, py):                      # outline side i: its distance to (px, py) and its unit normal toward it
        (ax, ay), (bx, by) = poly_[i], poly_[(i + 1) % len(poly_)]
        L_ = math.hypot(bx - ax, by - ay) or 1.0
        t_ = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L_ ** 2))
        nx, ny = (ay - by) / L_, (bx - ax) / L_
        s_ = 1.0 if (px - ax) * nx + (py - ay) * ny >= 0 else -1.0
        return math.hypot(ax + t_ * (bx - ax) - px, ay + t_ * (by - ay) - py), (s_ * nx, s_ * ny)
    hand_ = lambda d, n: "R" if d[0] * n[1] - d[1] * n[0] > 0 else "L"
    Q_.skew_hands = defaultdict(list)            # "R" / "L" -> the outline side of every skewed joist end
    for X, a, b, ea, eb, _ in OF.joists:
        for y, e, dy in ((a, ea, 1.0), (b, eb, -1.0)):
            if e in ("rim45", "bay45"):
                i = min((k for k, kk in enumerate(OF.side_kind) if kk in ("rim45", "bay45")), key=lambda k: _side_n(k, X, y)[0])
                Q_.skew_hands[hand_((0.0, dy), _side_n(i, X, y)[1])].append(i + 1)
    Q_.skew2_hands = []                          # the skewed doubles: a rim into a ledger at 45 degrees, the rims onto a ledger block
    for i in range(len(poly_)):
        j = (i + 1) % len(poly_)
        ka, kb = OF.side_kind[i], OF.side_kind[j]
        (xa, ya), (xb, yb), (xc, yc) = poly_[i], poly_[j], poly_[(j + 1) % len(poly_)]
        ang = abs(math.degrees(math.atan2(yb - ya, xb - xa) - math.atan2(yc - yb, xc - xb))) % 180
        if {ka, kb} & {"rim", "rim45"} and {ka, kb} & {"ledger", "ledger45"} and abs(min(ang, 180 - ang) - 45) <= 3:
            r_i = ka in ("rim", "rim45")
            d = (xa - xb, ya - yb) if r_i else (xc - xb, yc - yb)
            Lr = math.hypot(*d) or 1.0
            Q_.skew2_hands.append(hand_(d, _side_n(j if r_i else i, xb + 12 * d[0] / Lr, yb + 12 * d[1] / Lr)[1]))
        elif abs(yb) < 0.5 and {ka, kb} == {"rim45", "bay45"}:
            Q_.skew2_hands += [hand_((xa - xb, ya - yb), (0.0, 1.0)), hand_((xc - xb, yc - yb), (0.0, 1.0))]
    # fascia: every open side, its own mitered length
    Q_.fascia_pieces = []
    if spec.decking.fascia:
        from .layout import step_skirt_layout
        sk_ = step_skirt_layout(spec) if getattr(spec.geometry, "step_skirt", None) else None
        skirted = {f_.edge for f_ in sk_.faces} if sk_ else set()          # the step skirt's vertical panels are the fascia there
        for e, kind in zip(L.outline_edges, OF.side_kind):
            if kind in ("rim", "rim45") and e.name not in skirted:
                Q_.fascia_pieces.append((f"fascia {e.name}", round(e.length + 1.5, 2)))
    # joist tape (2" on every joist + the ledger), 4" on rims and beams
    Q_.tape_joist_lf = (sum(b - a for _, a, b, *_ in OF.joists) + Q_.ledger_len) / 12.0
    Q_.tape_wide_lf = (rim_lf / max(1, plies) + sum(ln.length for ln in L.beam_lines if ln.kind != "drop")) / 12.0     # one 4" strip covers a doubled rim's top (drop beams: added with every frame's)
    Q_.tape_block_lf = (sum(blk) + sum(dbk) + sum(dbe)) / 12.0
    Q_.rss_lam = int(rim_lf / plies / 12.0 * 2 + 0.999) * (plies - 1) if plies > 1 else 0
    Q_.outline_notes = OF.notes
    n_bk = len(dbk) + len(dbe)        # a level with breakers and no angled borders leads with its breaker blocks (the build set drops a "0 x" line)
    Q_.outline_block_note = ((f"{len(blk)} x {jsize} blocks under the 45-degree picture-frame borders" + (f" + {n_bk} under the breakers, between the divider joists" if n_bk else "")
                              if blk or not n_bk else f"{n_bk} x {jsize} blocks under the breakers, between the divider joists")
                             + ", (3) structural screws each end"
                             + ("; one row over each flush beam" if L.beam_lines else "; the joists hang at both ends — no mid-span row"))
    Q_.outline_ledgers = list(OF.ledgers)
    Q_.outline_joists, Q_.outline_ledger_blocks = list(OF.joists), list(OF.ledger_blocks)     # the LedgerLOK spacing reads the spans
    Q_.outline_blocks = list(OF.blocks)                       # the breakers' blocks: what their Cortex screws land on


# Simpson LUS face-mount hangers: (face, joist) nails, all 10d (0.148 x 3) — the joist nails driven at 45 degrees into the header (double shear)
LUS_NAILS = {"LUS26Z": (4, 4), "LUS28Z": (6, 4), "LUS210Z": (8, 4)}

# FastenMaster LedgerLOK Table 1 (FMTECH-DECKLEDG, 2x rim): max joist span (ft) -> OC spacing (in) for a DF / SP | Hem-Fir ledger
LEDGERLOK_OC = {40: ((6, 24, 20), (8, 18, 15), (10, 14, 12), (12, 12, 10), (14, 10, 8), (16, 9, 7), (18, 8, 6)),
                60: ((6, 17, 14), (8, 13, 11), (10, 10, 8), (12, 8, 7), (14, 7, 6), (16, 6, 5), (18, 5, 4))}


def ledgerlok_spacing(span_in: float, live_psf: float = 40.0, species: str = "SYP") -> int:
    """LedgerLOK OC spacing (in) for a joist span off the ledger (FastenMaster Table 1, 2x rim), never over the GSX 12" — the one
    table the order, the drawings and the build set read."""
    rows = LEDGERLOK_OC[40 if live_psf <= 40 else 60]
    col = 2 if species in ("HF", "SPF", "CEDAR") else 1
    return min(12, next((r[col] for r in rows if span_in / 12.0 <= r[0] + 1e-6), rows[-1][col]))


def ledger_spans(spec: DeckSpec, L: Layout, ledgers=None, joists=None, blocks=()) -> List[Tuple[float, float, str]]:
    """[(ledger piece length in, longest joist span landing on it in, the piece as the cut list names it: 'main wall', 'bay face',
    'ledger block')]: an outline deck's ledgers and ledger blocks with the outline joists (layout.outline_framing, or the lists the
    takeoff already holds), else every ledgered zone at its joist span (no name)."""
    if ledgers is None and L.multi and getattr(L, "outline_edges", None):
        from .layout import outline_framing
        OF = outline_framing(spec, L)
        if OF is not None:
            ledgers, joists, blocks = list(OF.ledgers), list(OF.joists), list(OF.ledger_blocks)
    if ledgers is None:
        return [(z.W, z.frame.beams[0].back_span if z.frame.beams else z.frame.joist_len, "") for z in L.zones if z.frame.ledger]
    n_led = len(ledgers)
    segs = [[x0, y0, x1, y1, 0.0] for x0, y0, x1, y1 in list(ledgers) + list(blocks or [])]
    def seg_d(px, py, x0, y0, x1, y1, *_):
        L2 = (x1 - x0) ** 2 + (y1 - y0) ** 2 or 1.0
        t_ = max(0.0, min(1.0, ((px - x0) * (x1 - x0) + (py - y0) * (y1 - y0)) / L2))
        return math.hypot(px - x0 - t_ * (x1 - x0), py - y0 - t_ * (y1 - y0))
    for X, a, b, ea, eb, _ in joists or []:
        for y, e in ((a, ea), (b, eb)):
            if e in ("ledger", "ledger45") and segs:
                s_ = min(segs, key=lambda s: seg_d(X, y, *s))
                s_[4] = max(s_[4], b - a)
    name_ = lambda k, s: ("" if not spec.geometry.outline else "ledger block" if k >= n_led else
                          "main wall" if abs(s[1]) < 1.0 and abs(s[3]) < 1.0 else "bay face")      # the cut list's names (no A-100 side number)
    return [(math.hypot(s[2] - s[0], s[3] - s[1]), s[4], name_(k, s)) for k, s in enumerate(segs)]


def ledgerlok_count(segs, live_psf: float = 40.0, species: str = "SYP") -> Tuple[int, str]:
    """segs: [(ledger piece length in, longest joist span on it in[, 'side N'])] (ledger_spans). LedgerLOK 2 rows staggered (V),
    3-3/4" min. from each end, spaced by the joist span per FastenMaster's Table 1 — never wider than the GSX 12". Returns (count,
    rule): the rule leads with the tightest spacing ('staggered 10" OC', as the drawings read it) and names the pieces that open up."""
    n, by_oc = 0, defaultdict(list)
    for ln, span, *nm in segs:
        sp = ledgerlok_spacing(span, live_psf, species)
        n += max(2, int(math.ceil((ln - 7.5) / sp - 1e-9)) + 1)
        by_oc[sp].append((ln, span, nm[0] if nm else ""))
    if not by_oc:
        return 0, "LedgerLOK 2 rows 2\" from top/bottom, staggered 12\" OC, first 3-3/4\" from each end"
    mx_ = lambda g: max(s for _, s, _ in g)
    def opens(g):            # the pieces a wider spacing covers: their lengths and names as the cut list gives them, their longest joists
        return (f" on the {' / '.join(ftin(ln) + (' ' + nm.replace(' ', '-') if nm else '') for ln, _, nm in g)} piece{'s' if len(g) > 1 else ''}"
                + (f" (joists to {ftin(mx_(g))})" if mx_(g) else ""))
    oc0 = min(by_oc)
    return n, (f"LedgerLOK 2 rows 2\" from top/bottom, staggered {oc0}\" OC, first 3-3/4\" from each end "
               f"(FastenMaster Table 1 at {40 if live_psf <= 40 else 60} psf" + (f", joists to {ftin(mx_(by_oc[oc0]))}" if mx_(by_oc[oc0]) else "") + ")"
               + "".join(f"; {oc}\" OC{opens(by_oc[oc])}" for oc in sorted(by_oc)[1:]))


def _ledger_runs(segs) -> int:
    """Ledger segments that touch end to end are one ledger (a main wall that wraps a bay): the lateral ties go 2 near each end of a run."""
    segs = list(segs)
    if not segs:
        return 0
    parent = list(range(len(segs)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    ends = [((a, b), (c, d)) for a, b, c, d in segs]
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 6.0 for p in ends[i] for q in ends[j]):
                parent[find(i)] = find(j)
    return len({find(i) for i in range(len(segs))})


def jb_of(nominal: str) -> float:
    return actual(nominal)[0]


def clip_field_edge_screws(L: Layout, joists=None, spacing: float = 16.0) -> int:
    """TimberTech's clip field (CONCEALoc): the first field row against each front border and the last row at the house and the bay
    are face-screwed on their outer edges, 1 per joist (install guide; the build set's decking rule). On an outline plan: every row
    edge no other row of its panel covers for a joist bay or more — the front rows, the house rows, the bay's front face — at each
    joist under it (an angled side's row steps stay clipped); else each zone's front row and house row, at its bearing points."""
    P = getattr(L, "plan", None)
    if P is None or not P.rows or not joists:
        return 2 * sum(z.decking.first_row_screws for z in L.zones)
    n = 0
    for r in P.rows:
        for back in (True, False):
            free = [(r.x0, r.x1)]
            for q in P.rows:
                if q is r or q.panel != r.panel or not (q.x0 < r.x1 and r.x0 < q.x1):
                    continue
                if not ((0 <= r.y0 - q.y1 < 1.0) if back else (0 <= q.y0 - r.y1 < 1.0)):
                    continue
                free = [seg for a_, b_ in free for seg in ((a_, min(b_, q.x0)), (max(a_, q.x1), b_)) if seg[1] - seg[0] > 0.01]
            for a_, b_ in free:
                if b_ - a_ >= 1.5 * spacing:
                    n += sum(1 for j in joists if a_ - 0.01 <= j[0] <= b_ + 0.01 and j[1] < r.y1 + 1.0 and r.y0 - 1.0 < j[2])    # a joist under the board
    return n


def box_cross_members(st) -> int:
    """A box step's cross members per tread: the stair layout's own count where it carries one (the tread line's max spacing), else at 16"."""
    return getattr(st, "cross_members", 0) or int(math.ceil(st.width / 16.0)) + 1


def build_takeoff(spec: DeckSpec) -> Takeoff:
    L = build_layout(spec)
    rl, stairs = L.rail, L.stairs
    W, D = L.finished_w, L.finished_d
    lines: List[Line] = []
    notes = list(L.notes)
    for z in L.zones:
        notes += [f"{z.name}: {n}" if L.multi else n for n in z.frame.notes + z.decking.notes]
    sched: Dict[str, str] = {}
    timber = spec.is_timber
    black = spec.framing.hardware_finish == "black"
    jsize, jsp = spec.framing.joist_size, spec.framing.joist_species
    jb, jd = actual(jsize)
    dkf = decking_facts(spec.decking.collection)
    brand, coll, color = spec.decking.brand, spec.decking.collection, spec.decking.color
    bcoll, bcolor = spec.decking.border_collection or coll, spec.decking.border_color or color
    fr0, dk0 = L.frame, L.decking
    n_posts = L.n_footings
    worst_load = max(z.frame.footing_load_lb for z in L.zones)

    Qz = Q(n_zones=len(L.zones))
    for zi, z in enumerate(L.zones):
        accumulate(Qz, spec, L, z, zi)
    if L.plan is not None:
        _accumulate_field_plan(Qz, spec, L)
    if L.multi and L.outline_edges:
        _rims_from_outline(Qz, spec, L)
        notes += getattr(Qz, 'outline_notes', [])
    cuts = Qz.cuts
    if Qz.front_flush:
        notes.append("front flush beam IS the front rim — joists hang into it, posts under it, no separate rim plies")
    # ---- outline-laid plan: a border piece on every exposed edge (the curve as mitered segments), split at the breakers; the breakers
    if L.plan is not None and spec.geometry.picture_frame:
        edge = (dk0.fascia_t + NOSE) if spec.decking.fascia else OVERHANG_NO_FASCIA
        bw, gap = dk0.bw, dk0.gap
        div_xs = [x for x, _, _, _ in L.plan.dividers]
        opoly = [(float(a_) * 12, float(b_) * 12) for a_, b_ in (spec.geometry.outline or [])]

        def side_of(x0, y0, x1, y1):
            """The outline side (as A-100 numbers it) a border run lies along, else its start point."""
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            for i_, (pa, pb) in enumerate(zip(opoly, opoly[1:] + opoly[:1])):
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                ll = math.hypot(dx, dy) or 1.0
                if abs((mx - pa[0]) * dy - (my - pa[1]) * dx) / ll < 8.0 and -2 <= ((mx - pa[0]) * dx + (my - pa[1]) * dy) / ll <= ll + 2:
                    return f"side {i_ + 1}"
            return f"{ftin(min(x0, x1))},{ftin(min(y0, y1))}"
        for x0, y0, x1, y1, _ in L.plan.borders:
            xa, xb = sorted((x0, x1))
            sd = side_of(x0, y0, x1, y1)
            cuts_x = [xa] + [x for x in div_xs if xa + 1 < x < xb - 1] + [xb]
            if abs(y1 - y0) < 0.5 and len(cuts_x) > 2:
                for k_, (a, b) in enumerate(zip(cuts_x, cuts_x[1:])):
                    Qz.border_pieces.append((f"border {sd} ({k_ + 1} of {len(cuts_x) - 1})", b - a - (bw / 2 + gap) * ((a != xa) + (b != xb))))
            else:
                Qz.border_pieces.append((f"border {sd}", math.hypot(x1 - x0, y1 - y0) + (bw if abs(y1 - y0) > 0.5 and abs(x1 - x0) > 0.5 else edge)))
        for x, y_lo, y_hi, lab in L.plan.dividers:
            Qz.border_pieces.append((f"breaker {lab}", y_hi - y_lo))
        # Cortex: 2 at every bearing — a border at each joist it crosses (the frame's spacing) and both ends; a breaker at each of the
        # blocks it rides between its two divider joists (the outline frame's own count) and both ends
        dblk_ = Counter(b_[4].split()[-1] for b_ in (getattr(Qz, "outline_blocks", None) or []) if b_[4].startswith("divider"))
        Qz.border_screws = sum(2 * ((dblk_[n_.split()[-1]] + 2) if (n_.startswith("breaker ") and dblk_.get(n_.split()[-1])) else (int(math.floor(Lb / fr0.spacing)) + 2))
                               for n_, Lb in Qz.border_pieces)
    # ---- multi-zone picture frame: outer border segmented at the dividers, end borders, dividers
    elif L.multi and spec.geometry.picture_frame:
        edge = (dk0.deck_w - L.zones[0].W) / 2
        bw, gap = dk0.bw, dk0.gap
        front_edges = [e for e in L.edges if e.name.startswith("front")]
        xs = sorted(set([min(e.x0 for e in front_edges) - edge] + [x for x, _, _ in L.divider_x] + [max(e.x1 for e in front_edges) + edge]))
        for a, b in zip(xs, xs[1:]):
            Qz.border_pieces.append((f"outer border {ftin(a)}-{ftin(b)}", b - a - (bw + 2 * gap if 0 < xs.index(a) else 0)))
        for e in L.edges:
            if e.name.startswith("end") and e.exposed:
                Qz.border_pieces.append((f"border {e.name}", e.length + edge))
        for x, Ld, lab in L.divider_x:
            Qz.border_pieces.append((f"divider {lab}", Ld + edge))
        Qz.border_screws = sum(2 * (int(math.floor(Lb / (fr0.spacing if n_.startswith(("outer", "border")) else min(fr0.spacing, 16.0)))) + 2)
                               for n_, Lb in Qz.border_pieces)              # 2 at every joist a border crosses, every divider block (16" max)
    # stairs lumber
    from .scene import box_step_miters
    miters_ = box_step_miters(spec, stairs)         # box steps that wrap a corner: no end skirt at the miter, their treads and risers run long to it
    mstep_ = {s_.side: s_ for s_ in stairs if str(s_.side).startswith("edge:") and getattr(s_, "build", "stringers") == "box" and not getattr(s_, "option", "")}
    miter_of = lambda st: miters_.get(st.side, (0, 0.0)) if mstep_.get(st.side) is st else (0, 0.0)    # a side's miter belongs to its last box step (the one box_step_miters and the scene read), never to another stair on that side
    for st in stairs:
        multi = len(st.geo.flights) > 1
        if getattr(st, "skirts", False):
            # stepped fascia skirts: one piece per side, cut to the step profile from a 12" fascia board — none at a box step's mitered end
            n_sk = 2 - miter_of(st)[0]
            for fg in st.geo.flights:
                if fg.treads and n_sk > 0:
                    Qz.fascia_pieces += [(f"stair skirt ({st.side}, stepped" + (", free end" if n_sk == 1 else "") + ")", round(fg.treads * st.geo.tread_in + 1.0, 1))] * n_sk
                    if dkf["material"] == "PVC":      # PVC skirts take the TOPLoc fascia screws, counted with the rim fascia: 2 at each end + every 12"
                        Qz.fascia_screws += n_sk * (4 + max(0, int(math.ceil((fg.treads * st.geo.tread_in + 1.0) / 12)) - 1))
        if getattr(st, "build", "stringers") == "box":
            # a framed box per tread, as the 3D frames it: 2x6 back + front rims across the width (the front one behind the riser board),
            # cross members between — no stringers, no hanger board; a box mitered to the next box step at a corner: its rims run to the
            # miter line, each long point at the rim's outer face (the box's back face sits fascia + nose off the outline side); only the
            # box step the scene miters on that side (miter_of); a box step with a single riser has no tread box to frame
            if not st.geo.treads:
                continue
            from .layout import hardie_thick as _ht
            r_t_ = _ht(spec) or 0.9                      # the riser board in front of the front rim: HardieTrim at its real thickness, as the 3D sets it
            ncm, cm_ = box_cross_members(st), round(st.geo.tread_in - r_t_ - 3.0, 2)      # the run less the riser board and the two rims
            m_e, m_k = miter_of(st)
            off_ = (dk0.fascia_t + NOSE) if spec.decking.fascia else OVERHANG_NO_FASCIA
            rims_ = []
            for k in range(st.geo.treads):
                ua_, ub_ = off_ + k * st.geo.tread_in, off_ + (k + 1) * st.geo.tread_in - r_t_     # the box's back face / its front rim's face, off the side
                rims_ += [round(st.width + m_e * m_k * (ua_ + 1.5), 2), round(st.width + m_e * m_k * ub_, 2)]
                Qz.lumber += [("2x6", r_, "box step rim") for r_ in rims_[-2:]] + [("2x6", cm_, "box step cross member")] * ncm
            rip_ = f"rip to {st.geo.riser_in - 0.94:.2f}\" (riser less the tread)"
            cuts.append(CutPiece(f"Box step frame ({st.side})", "2x6", max(rims_), 2 * st.geo.treads,
                                 "back + front rims" + (f", mitered to the next box step (long points {' / '.join(ftin(r_) for r_ in sorted(set(rims_)))} back to front)" if m_e else "")
                                 + f", {ncm} cross members between — {rip_}"))
            cuts.append(CutPiece(f"Box step cross members ({st.side})", "2x6", cm_, ncm * st.geo.treads,
                                 f"{ncm} per tread between the rims @ {ftin((st.width - 1.5) / max(1, ncm - 1))} OC ({getattr(st, 'support_oc', 0) or 16:g}\" max), (2) RSS each end — {rip_}"))
            continue
        for fi, fg in enumerate(st.geo.flights):
            if not fg.treads:
                continue            # a single riser down onto a landing: the landing frame takes the riser, no stringers
            Qz.lumber += [("2x12", fg.stringer_len_in, "stair stringer")] * st.stringers
            cuts.append(CutPiece(f"Stair stringers ({st.side}" + (f", flight {fi + 1}" if multi else "") + ")", "2x12", fg.stringer_len_in, st.stringers,
                                 f"{fg.risers} risers @ {st.geo.riser_in:.3f}\" · {fg.treads} treads @ {st.geo.tread_in:.2f}\" · stringers @ {st.width / max(1, st.stringers - 1):.0f}\" OC (max {getattr(st, 'support_oc', 0) or eng.STRINGER_OC_COMPOSITE:g}\")"))
            Qz.lumber += [("2x6", st.width + 3, "stair kicker/hanger board")] * 2
        if getattr(st, "inset", False) and st.notch:
            # the inset stair's foot (structure.md §5.2): a doubled PT 2x6 base ledger through-bolted to the lower level's rim, the
            # stringer heels on it (A35Z each); two short PT posts on it carry the header ends (A35Z both ways)
            nt_ = st.notch
            bl_ = round(nt_["ledger_hi"] - nt_["ledger_lo"], 2)
            Qz.lumber += [("2x6", bl_, "stair base ledger")] * 2 + [(nt_["post_size"], round(st.notch_post_len + 1.0, 2), "stair notch post")] * st.notch_posts
            cuts.append(CutPiece(f"Stair base ledger ({st.side})", "2x6", bl_, 2,
                                 f"2-ply PT, on the lower level's rim face under the notch, top flush with the rim; 1/2\" bolts @ 12\" staggered ({nt_['ledger_bolts']})"))
            cuts.append(CutPiece(f"Stair notch posts ({st.side})", nt_["post_size"], st.notch_post_len, st.notch_posts,
                                 "PT, on the base ledger under the header / rim corners; (2) 1/2\" through-bolts each to the lower rim, A35Z at the top — field-measure"))
            Qz.notch_dh = getattr(Qz, "notch_dh", 0) + 4           # trimmer ends 2 + headers on the trimmer 2
            Qz.a35_stair = getattr(Qz, "a35_stair", 0) + 2 * st.notch_posts + st.stringers
    # the step-face skirt: 2x4 nailers hung below the rim (studs at 16" + blocking rows) behind the vertical panels
    skirt = None
    if getattr(spec.geometry, "step_skirt", None):
        from .layout import step_skirt_layout
        skirt = step_skirt_layout(spec)
        if skirt:
            fp = [(ln_, lab_) for ln_, lab_ in skirt.furring_pieces() if ln_ > 1.0]
            ns_ = sum(1 for _, lab_ in fp if lab_ == "skirt stud")
            if fp:
                Qz.lumber += [("2x4", ln_, lab_) for ln_, lab_ in fp]
                Qz.a35_stair = getattr(Qz, "a35_stair", 0) + ns_
                cuts.append(CutPiece("Step-skirt nailers", "2x4", max(ln_ for ln_, _ in fp), len(fp),
                                     f"{ns_} studs hung from the rim at 16\" (A35Z + 2 structural screws at the top) and {len(fp) - ns_} blocking pieces in rows at mid-height and the bottom, "
                                     "outer faces flush with the rim face"))
            notes += skirt.notes
    # rail post blocks: an IRX post (lagged through its base) gets TimberTech's 2x6 blocking + 2x6 cross block (IRX install guide
    # Dia. #3A/#3B); a timber or HeadLOK-mounted post one block, cut to the joist bay
    n_rail_posts = (len(rl.posts) if rl else 0) + sum(s.stair_posts for s in stairs)
    knee = spec.framing.knee_braces and not timber and not spec.framing.existing_posts and spec.framing.system != "steel"
    n_knee_posts = sum(bl.n_posts for bl in L.beam_lines) if knee else 0
    if knee:
        Qz.lumber += [(jsize, 14.5, "knee-brace block")] * n_knee_posts
    surface_rail = bool(rl) and RAIL_SYSTEMS.get(rl.system, {}).get("surface", False)
    irx_blk_ = bool(rl) and surface_rail and not timber and RAIL_SYSTEMS.get(rl.system, {}).get("post_lag", False)
    if rl and (timber or surface_rail):
        rpb_ = round(fr0.spacing - jb, 2)          # cut to the joist bay: 10-1/2" between 2x joists at 12" OC, 8-1/2" between 4x
        if irx_blk_:
            Qz.lumber += [("2x6", rpb_, "rail post blocking"), ("2x6", rpb_, "rail post cross block")] * len(rl.posts)
            cuts.append(CutPiece("Rail post blocking (IRX)", "2x6", rpb_, len(rl.posts), "under each post, square to the rim, from the rim back to its cross block "
                                 "(TimberTech IRX install guide Dia. #3A/#3B), (3) RSS each end"))
            cuts.append(CutPiece("Rail post cross blocks (IRX)", "2x6", rpb_, len(rl.posts), f"one per post, between the joists at the back of its blocking ({fr0.spacing:g}\" OC bay), (3) RSS each end"))
        else:
            Qz.lumber += [(jsize, rpb_, "rail post block")] * len(rl.posts)
            cuts.append(CutPiece("Rail post blocks", jsize, rpb_, len(rl.posts), f"one per post, between the joists behind the rim ({fr0.spacing:g}\" OC bay)" + ("" if timber else ", (3) RSS each end")))

    # ================= LUMBER
    packed = pack_lumber(Qz.lumber, price=lambda nom_, st_: _lumber_price(nom_, st_, timber and nom_ in ("4x8", "4x10", "4x12"))[0],
                         known=lambda nom_, st_: str(st_) in (PRICEBOOK["lumber"].get(nom_) or {}).get("lengths", {}))     # up only to a length D&D prices
    joist_lf = sum(st * 12 * n for (nom, st), (n, _) in packed.items() if nom == jsize) / 12.0
    for (nom, st), (n, labels) in sorted(packed.items(), key=lambda t: (t[0][0], t[0][1])):
        is_timber_piece = timber and nom in ("4x8", "4x10", "4x12")
        uc, src = _lumber_price(nom, st, is_timber_piece)
        if is_timber_piece:
            desc = f"{nom}x{st} {SPECIES_NAMES['DF#1']}"
        elif nom == "2x6" and jsp == "SYP":       # TrueFrame is made in 2x8 / 2x10 / 2x12 only: D&D's 2x6 is #1 KDAT GC
            desc = f"{nom}x{st} #1 KDAT GC"
        elif nom in ("2x6", "2x8", "2x10", "2x12"):
            desc = f"{nom}x{st} {SPECIES_NAMES.get(jsp, jsp)}"
        elif nom == "2x4":          # the step-skirt nailers (D&D: 2x4 #1 KDAT ground contact)
            desc = f"{nom}x{st} #1 KDAT GC"
        elif nom == "4x4":          # an inset stair's notch posts
            desc = f"{nom}x{st} #2 GC PT"
        else:
            desc = f"{nom}x{st}"
        lines.append(Line("Lumber", desc, n, n + 1, "ea", f"+1 cull  ({_summarize_labels(labels)})", uc, src))
    # beams and posts from the beam lines
    beam_pieces, post_pieces = [], []
    caps_mid, caps_end = 0, 0
    timber_sf = 0.0
    for bl in L.beam_lines:
        plies, nom, bw_, bd_ = parse_beam(bl.size)
        for a, b in bl.pieces:
            beam_pieces += [(nom, b - a, f"{bl.kind} beam")] * plies
        cuts.append(CutPiece(f"{bl.label} beam", nom, bl.length, plies * len(bl.pieces), f"y {ftin(bl.y)}; posts at " + " / ".join(ftin(x) for x in bl.posts_x)
                             + (f"; pieces " + " · ".join(ftin(b - a) for a, b in bl.pieces) + ", spliced over posts" if len(bl.pieces) > 1 else "")))
        if not spec.framing.existing_posts:
            post_pieces += [(spec.framing.post_size, bl.post_len + 1.0, "post")] * bl.n_posts
            cuts.append(CutPiece(f"Posts under {bl.label}", spec.framing.post_size, bl.post_len, bl.n_posts, "field-measure each"))
        caps_end += 2 if bl.n_posts >= 2 else bl.n_posts
        caps_mid += max(0, bl.n_posts - 2)
        timber_sf += plies * 2 * (bw_ + bd_) / 12 * bl.length / 12
    eps_ = getattr(L, "edge_posts", None) or []          # posts under the rims at the outline corners (the rims span post to post)
    if eps_ and not spec.framing.existing_posts:
        post_pieces += [(spec.framing.post_size, L.edge_post_len + 1.0, "edge post")] * len(eps_)
        cuts.append(CutPiece(f"Edge posts {eps_[0].label}-{eps_[-1].label} under the rims", spec.framing.post_size, L.edge_post_len, len(eps_),
                             "field-measure each; centered under both rim ends at the corner, rims tied with A35Z"))
    sp = spec.framing.beams[0].species if spec.framing.beams else "DF"
    df1_beam = sp == "DF#1" and not timber
    for (nom, st), (n, labels) in pack_lumber(beam_pieces, short_stock_ft=8 if df1_beam else 12).items():
        uc, src = _lumber_price(nom, st, timber or df1_beam)
        desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if timber else 'Douglas Fir #1' if df1_beam else SPECIES_NAMES.get(sp, sp)}"
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  ({_summarize_labels(labels)}: " + " · ".join(bl.label for bl in L.beam_lines) + ")", uc, src))
    stair_posts_own = []          # posts on a stair's own 12" caissons (Stair.landing_footing "caisson12"): 6x6 rough (owner), their own line below
    for st_ in L.stairs:
        if st_.mid_support:
            fl_ = st_.geo.flights or []
            idx = st_.carrier_flights or [0]
            fracs = st_.carrier_fracs or [0.5]
            for fi in idx:
                below = sum(f.rise_in for f in fl_[fi + 1:]) if fl_ else 0.0
                f_rise = fl_[fi].rise_in if fl_ else st_.geo.total_rise_in
                for fr_ in fracs:
                    h_c = below + f_rise * (1 - fr_)
                    tagf = f"{st_.side}" + (f", flight {fi + 1}" if len(fl_) > 1 else "") + (f", carrier {fracs.index(fr_) + 1} of {len(fracs)}" if len(fracs) > 1 else "")
                    own_ = getattr(st_, "own_footings", 0)
                    ps_ = "6x6" if own_ else spec.framing.post_size      # owner: a stair landing is 6x6 rough on ABU66RZ
                    (stair_posts_own if own_ else post_pieces).extend([(ps_, h_c + 6.0, "stair carrier post")] * 2)
                    cuts.append(CutPiece(f"Stair carrier posts ({tagf})", ps_, h_c, 2, "under the stringers" + (", on 12\" caissons, ABU66RZ bases" if own_ else "") + " — field-measure"))
                    cuts.append(CutPiece(f"Stair carrier ({tagf})", "2x6" if not timber else "4x6", st_.width + 6, 2, "2 ply, notched stringers bear on it; hurricane tie each stringer"))
            car = "2x6" if not timber else "4x6"
            n_car = len(idx) * len(fracs)
            uc, src = _lumber_price(car, 12, timber)
            lines.append(Line("Lumber", f"{car}x12 {'#1 KDAT' if not timber else 'DF #1'} — stair carrier (2 ply) + blocking between stringers at each carrier ({st_.side}" + (f", {n_car} carriers" if n_car > 1 else "") + ")",
                              3 * n_car, 3 * n_car, "ea", f"exact  (2 ply x {ftin(st_.width + 6)} carrier + {st_.stringers - 1} blocks, 1 spare — per carrier)", uc, src))
        for li_, h_l in enumerate(getattr(st_, "landing_post_h", None) or []):     # landing posts on the deck's own footings (cut with the deck's posts) or on the stair's own 12" caissons
            own_ = getattr(st_, "own_footings", 0)
            ps_ = "6x6" if own_ else spec.framing.post_size
            (stair_posts_own if own_ else post_pieces).extend([(ps_, h_l + 6.0, "stair landing post")] * 4)
            cuts.append(CutPiece(f"Stair landing posts ({st_.side}, landing {li_ + 1})", ps_, h_l, 4, ("on 12\" caissons, ABU66RZ bases" if own_ else "on the deck's footings and post bases") + " — field-measure"))
    for (nom, st), (n, labels) in pack_lumber(post_pieces, short_stock_ft=8).items():
        df1_post = spec.framing.post_species.upper().startswith("DF") and not timber
        uc, src = _lumber_price(nom, st, timber or df1_post)
        if spec.framing.post_rough and df1_post and f"{nom}_DF_rough" in PRICEBOOK["lumber"]:
            uc, src = _lumber_price(f"{nom}_DF_rough", st)          # D&D's Douglas fir rough (the #2 treated price is not this post)
        if spec.framing.post_rough and not timber:       # rough-sawn full dimension: never "S4S" (the timber-frame wording)
            desc = f"{nom}x{st} Douglas Fir #1 rough, full dimension (end grain sealed)" if (df1_post or nom.startswith('8x')) else f"{nom}x{st} #2 GC rough"
        else:
            desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if (timber or nom.startswith('8x')) else 'Douglas Fir #1' if df1_post else '#2 GC'}"
        lens = sorted(set([ftin(bl.post_len) for bl in L.beam_lines] + ([ftin(L.edge_post_len)] if eps_ else [])))
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  (yields {n_posts} posts at ~{' / '.join(lens)})", uc, src))
    for (nom, st), (n, labels) in pack_lumber(stair_posts_own, short_stock_ft=8).items():
        # a stair's own landing / carrier posts on 12" caissons (owner: 6x6 rough on ABU66RZ): Douglas fir rough like the deck's columns,
        # at the rough-DF price on D&D's quote (lumber "<size>_DF_rough"), else per BF at the rate the DF #1 8x8 is built from
        df_ = spec.framing.post_rough or spec.framing.post_species.upper().startswith("DF")
        if df_ and f"{nom}_DF_rough" in PRICEBOOK["lumber"]:
            uc, src = _lumber_price(f"{nom}_DF_rough", st)
        elif not df_ or f"{nom}_DF#1" in PRICEBOOK["lumber"]:
            uc, src = _lumber_price(nom, st, df_)
        else:
            b8 = PRICEBOOK["lumber"].get("8x8_DF#1", {})
            uc, src = round(float(b8.get("per_lf", 0.0)) * 36.0 / 64.0 * st, 2), "EST — DF #1 8x8's $/BF x a 6x6 (" + str(b8.get("source", ""))[:60] + ")"
        desc = f"{nom}x{st} " + ("Douglas Fir #1 rough, full dimension (end grain sealed)" if df_ else "#2 GC PT")
        lines.append(Line("Lumber", desc + " — stair landing and carrier posts on 12\" caissons", n, n, "ea",
                          f"exact  ({sum(1 for p_ in stair_posts_own if p_[0] == nom)} posts at ~" + " / ".join(sorted({ftin(p_[1] - 6.0) for p_ in stair_posts_own if p_[0] == nom})) + ")", uc, src))
    if knee:
        lg = spec.framing.knee_leg_in
        bl_len = lg * math.sqrt(2) + 3.5
        kdf = spec.framing.post_species.upper().startswith("DF")
        for (nom, st), (n, labels) in pack_lumber([("4x4", bl_len, "knee brace")] * (2 * n_knee_posts), short_stock_ft=8).items():
            uc, src = _lumber_price(nom, st, False)
            lines.append(Line("Lumber", f"{nom}x{st} {'Douglas Fir #1' if kdf else '#2 GC'} — knee braces", n, n + 1, "ea",
                              f"+1  ({2 * n_knee_posts} braces at {ftin(bl_len)}, 45° plumb cuts, {ftin(lg)} legs: one along the beam, one up to the joists at every post)", uc, src))
        cuts.append(CutPiece("Knee braces", "4x4", bl_len, 2 * n_knee_posts, f"45° both ends, {ftin(lg)} legs · along the beam toward mid-span + up to a block between the joists"))
        for key, n, why in (("bolt_1/2x10", 2 * n_knee_posts, "brace to the 6x6 post"), ("bolt_1/2x12", n_knee_posts, "brace to the (2)4x beam" if any(parse_beam(b.size)[0] == 2 for b in L.beam_lines) else "brace to the beam"),
                            ("bolt_1/2x6", n_knee_posts, "brace to the joist block")):
            d_, uc, src, sku = _hw(key, black)
            lines.append(Line("Hardware", d_.replace(" (4x ledger)", "") + f" — knee braces ({why})", n, n + 1, "ea", "+1", uc, src))
        sched["Knee braces"] = (f"4x4 {'DF #1' if kdf else '#2 GC'} at 45°, {ftin(lg)} legs, both directions at every post: one along the beam toward mid-span, "
                                f"one toward the house up to a 2x10 block between the joists; (1) 1/2\" through-bolt each end, 2\" min. edge distance")
    if timber:
        pb_, pd_ = actual(spec.framing.post_size)
        timber_sf += sum(bl.n_posts * 4 * pb_ / 12 * bl.post_len / 12 for bl in L.beam_lines)
        timber_sf += joist_lf * (2 * jd + jb) / 12
        Qz.timber_ends += 2 * sum(bl.n_posts + len(bl.pieces) for bl in L.beam_lines)

    # ================= FOOTINGS
    ft = spec.framing.footing_type
    if ft == "existing" or spec.framing.existing_posts:
        base_screws = 0
        if not spec.framing.existing_posts:
            bkeys = TIMBER_BASE.get(spec.framing.post_size, ("ABU66Z_black", "ABU66Z"))
            bkey = bkeys[0] if black else bkeys[1]
            d_, uc, src = _item("footings", bkey)
            lines.append(Line("Footings", d_ + " — on the existing caisson, epoxy-set", n_posts, n_posts, "ea", "exact  (existing caissons stay; tops chipped level)", uc, src, bkey))
            lines.append(Line("Footings", "Simpson SET-3G epoxy + 5/8\" x 8\" threaded rod, 2 per base", n_posts * 2, n_posts * 2, "ea", "exact  (drilled into the existing caisson — engineer confirms embed)", 9.5, "est."))
    elif ft == "diamond_pier":
        model = fr0.footing_model
        uc, src = _price("footings", model)
        lines.append(Line("Footings", _desc("footings", model, f"Diamond Pier {model}"), n_posts, n_posts, "ea", "exact — confirm stock", uc, src, model,
                          f"{worst_load:,.0f} lb per post vs {fr0.footing_capacity_lb:,.0f} lb allowable"))
        base = POST_BASE.get(spec.framing.post_size, {}).get("diamond_pier", "ABA66Z")
        if base == "ABA66Z" and spec.framing.post_rough:
            base = "ABA66RZ"                # a rough-sawn 6x6 is a full 6": the R base, as every drawing calls it
        if base == "ABU88Z" and spec.framing.post_rough:
            base = "ABU88RZ"                # a rough 8x8 takes the R-series ABU88
        uc, src = _price("footings", base)
        lines.append(Line("Footings", _desc("footings", base, base) + " on the pier bolt", n_posts, n_posts, "ea", "exact", uc, src, base,
                          "ABU88: (2) 5/8\" anchors — the cast-in pier bolt + one drilled into the pier head (Pin Foundations / engineer confirm)" if base.startswith("ABU88") else ""))
        if base.startswith("ABU88"):
            d_, uc_, src_ = _item("footings", "abu88_sds_anchor_set", "Simpson SDS 1/4\" x 3\" (8 per base) + 5/8\" x 6\" Titen HD (1 per base, the second anchor in the pier head)")
            lines.append(Line("Footings", d_, n_posts, n_posts, "set", "exact  (one set per ABU88 base)", uc_ or 18.0, src_ or "EST — SDS25300 x 8 + THD62600H x 1"))
        base_screws = n_posts * PRICEBOOK["footings"].get(base, {}).get("screws", POST_BASE_SCREWS.get(base, 12))     # Simpson's count (ABA66: 8)
    elif ft == "caisson":
        dia, depth = fr0.footing_dia_in, fr0.footing_depth_in
        above = float(spec.framing.caisson_above_in)        # 0: poured flush with the slab it is drilled through
        tube_len = depth + above
        vol_cf = math.pi * (dia / 24) ** 2 * (tube_len / 12)
        bags_each = int(math.ceil(vol_cf / 0.6))
        per_tube = max(1, int(math.floor(144 / tube_len)))
        tubes = int(math.ceil(n_posts / per_tube))
        tkey = f"sonotube_{int(dia)}" if f"sonotube_{int(dia)}" in PRICEBOOK["footings"] else "sonotube_20"
        d_, uc, src = _item("footings", tkey, f"Sonotube {int(dia)}\" x 12'")
        lines.append(Line("Footings", f"{d_} — caissons {int(dia)}\" x {ftin(depth)} (frost {ftin(spec.site.frost_depth_in)})", tubes, tubes, "ea",
                          f"exact  ({n_posts} caissons, {per_tube} per tube, " + (f"top {ftin(above)} above grade)" if above else "poured flush with the slab)"), uc, src, note=f"{worst_load:,.0f} lb per post vs ~{fr0.footing_capacity_lb:,.0f} lb (end bearing + skin friction estimate); engineer sets diameter"))
        d_, uc, src = _item("footings", "quikrete_80", "Quikrete 80# concrete mix")
        lines.append(Line("Footings", d_, bags_each * n_posts, bags_each * n_posts, "bag", f"exact  ({bags_each} bags per caisson)", uc, src))
        r4 = int(math.ceil(n_posts * 4 * tube_len / 12 / 20))
        r3 = int(math.ceil(n_posts * (math.pi * (dia - 4) / 12 * 4) / 20))
        d_, uc, src = _item("footings", "rebar4_20"); lines.append(Line("Footings", d_, r4, r4, "ea", "exact — engineer governs", uc, src))
        d_, uc, src = _item("footings", "rebar3_20"); lines.append(Line("Footings", d_, r3, r3, "ea", "exact — engineer governs", uc, src))
        bkeys = TIMBER_BASE.get(spec.framing.post_size, ("ABU66Z_black", "ABU66Z"))
        bkey = bkeys[0] if black else bkeys[1]
        if bkey == "ABU88Z" and spec.framing.post_rough:
            bkey = "ABU88RZ"                # a rough 8x8 (a full 8") takes the R-series ABU88
        n_anc = n_posts * (2 if bkey.startswith("ABU88") else 1)       # an ABU88 bolts down with two 5/8" anchors
        # GSX never wet-sets (owner 27 Oct): the base goes on once the caisson has cured, on anchors drilled through it into the concrete
        d_, uc, src = _item("footings", "titen_hd_58x6"); lines.append(Line("Footings", d_, n_anc, n_anc, "ea", "exact" + (f"  (2 per {bkey})" if n_anc > n_posts else "  (1 per base)"), uc, src))
        d_, uc, src = _item("footings", bkey)
        lines.append(Line("Footings", d_ + " — set on the cured caisson", n_posts, n_posts, "ea", "exact", uc, src, bkey))
        if bkey.startswith("ABU88"):           # both anchors are drilled in after the cure (their own line): the set is only the post screws
            lines.append(Line("Footings", "ABU88 post screws: (8) Simpson SDS 1/4\" x 3\" per base", n_posts, n_posts, "set", "exact  (one set per ABU88 base)", 10.0, "EST — (8) SDS25300 per base"))
        base_screws = 0
    else:
        dia, depth = fr0.footing_dia_in, fr0.footing_depth_in
        vol_cf = math.pi * (dia / 24) ** 2 * (depth / 12)
        bags = int(math.ceil(vol_cf / 0.6)) * n_posts
        tube = f"sonotube_{int(dia)}" if f"sonotube_{int(dia)}" in PRICEBOOK["footings"] else "sonotube_12"
        uc, src = _price("footings", tube)
        lines.append(Line("Footings", f"{int(dia)}\" form tube x {ftin(depth)} (bearing {ftin(depth - 6)} below grade, frost {ftin(spec.site.frost_depth_in)})", n_posts, n_posts, "ea", "exact", round(uc * depth / 12, 2), src,
                          note=f"{worst_load:,.0f} lb per post on {spec.site.soil_bearing_psf:,.0f} psf soil"))
        uc, src = _price("footings", "concrete_80lb")
        lines.append(Line("Footings", "Concrete mix 80 lb", bags, bags + 2, "bag", f"+2  ({vol_cf:.1f} cf per pier)", uc, src))
        base = POST_BASE.get(spec.framing.post_size, {}).get("concrete", "ABU66Z")
        uc, src = _price("footings", base)
        lines.append(Line("Footings", _desc("footings", base, base) + " — set on the cured pier", n_posts, n_posts, "ea", "exact", uc, src, base))
        d_, uc_a, src_a = _item("footings", "titen_hd_58x6")            # never wet-set (owner 27 Oct): one 5/8" anchor drilled in after the cure
        lines.append(Line("Footings", d_, n_posts, n_posts, "ea", "exact  (1 per base)", uc_a, src_a))
        base_screws = n_posts * POST_BASE_SCREWS.get(base, 12)
    if spec.extras.stone_bases:
        d_, uc, src = _item("footings", "stone_base_kit")
        lines.append(Line("Footings", d_, n_posts, n_posts, "ea", f"exact  (all {n_posts} posts)", uc, src))
    for st in stairs:
        if st.landing == "concrete pad":
            uc, src = _price("footings", "concrete_pad")
            lines.append(Line("Footings", f"Stair landing pad ({st.side} stair) — 4\" slab, stringers bear on the pad", 1, 1, "ea", "exact", uc, src))
        n_own = getattr(st, "own_footings", 0)
        if n_own:
            # the stair's own footings (Stair.landing_footing "caisson12", footings agent 27 Oct): 12" caissons to the deck's caisson depth
            # (frost + 2" without one), the deck's top above grade, (4) #4 + #3 ties like the deck's (engineer governs), and an ABU66
            # an ABU66RZ on one 5/8" Titen HD drilled in after the cure under each 6x6 rough landing / carrier post (owner); labor at the card's $150 a hole (pricing)
            dep_s = float(spec.framing.caisson_depth_in or (spec.site.frost_depth_in + 2))
            abv_s = float(spec.framing.caisson_above_in) if spec.framing.footing_type == "caisson" else 6.0
            tl_s = dep_s + abv_s
            bags_s = int(math.ceil(math.pi * (12.0 / 24) ** 2 * (tl_s / 12) / 0.6))
            tag_s = f"{st.side} stair: {st.landing_footings} landing + {n_own - st.landing_footings} carrier posts"
            uc, src = _price("footings", "sonotube_12")
            lines.append(Line("Footings", f"12\" form tube — stair caissons 12\" x {ftin(dep_s)} + {ftin(abv_s)} above grade ({tag_s})", n_own, n_own, "ea",
                              "exact  (one per post, cut to length)", round(uc * tl_s / 12, 2), src))
            d_, uc, src = _item("footings", "quikrete_80", "Quikrete 80# concrete mix")
            lines.append(Line("Footings", d_, bags_s * n_own, bags_s * n_own, "bag", f"exact  ({bags_s} bags per 12\" stair caisson)", uc, src))
            r4_s = int(math.ceil(n_own * 4 * tl_s / 12 / 20)); r3_s = int(math.ceil(n_own * (math.pi * 8 / 12 * 4) / 20))
            d_, uc, src = _item("footings", "rebar4_20"); lines.append(Line("Footings", d_, r4_s, r4_s, "ea", "exact — engineer governs (12\" stair caissons)", uc, src))
            d_, uc, src = _item("footings", "rebar3_20"); lines.append(Line("Footings", d_, r3_s, r3_s, "ea", "exact — engineer governs (12\" stair caissons)", uc, src))
            bk_ = "ABU66RZ" if spec.framing.post_rough else "ABU66Z"     # owner: a stair landing is 6x6 rough on an ABU66RZ (one anchor, after the cure)
            d_, uc, src = _item("footings", "titen_hd_58x6"); lines.append(Line("Footings", d_, n_own, n_own, "ea", f"exact  (1 per {bk_} base, stair caissons)", uc, src))
            d_, uc, src = _item("footings", bk_)
            lines.append(Line("Footings", f"{d_} — stair landing / carrier posts, set on the cured caissons", n_own, n_own, "ea", "exact", uc, src, bk_))
            base_screws += n_own * POST_BASE_SCREWS.get(bk_, 12)
    # intermediate stair landings: a framed platform (joist-size rims + joists at the deck spacing) on four posts, decked in the field board
    for st_s in spec.stairs:
        for li, (lw, ld) in enumerate(st_s.landings or []):
            lw, ld = float(lw), float(ld)
            n_j = int(lw / spec.joist_spacing) + 2
            pcs = int(math.ceil((2 * (lw + ld) / 12 + n_j * ld / 12) / 12)) + 1
            uc, src = _lumber_price(jsize, 12, timber)
            lines.append(Line("Stairs", f"{jsize}x12 {SPECIES_NAMES.get(jsp, jsp)} — landing {li + 1} frame ({ftin(lw)} x {ftin(ld)}, {st_s.side} stair)", pcs, pcs, "ea", f"+1  (rims + {n_j} joists @ {spec.joist_spacing:g}\")", uc, src))
            deck_ft = getattr(st_s, "landing_footing", "") in ("deck", "caisson12")   # its posts, footings and bases: with the deck's, or the stair's own 12" caissons (above)
            if not deck_ft:
                uc, src = _lumber_price(spec.framing.post_size, 8, timber or spec.framing.post_size.startswith("8x"))
                lines.append(Line("Stairs", f"{spec.framing.post_size}x8 — landing {li + 1} posts (4)", 4, 4, "ea", "exact", uc, src))
            if deck_ft:
                pass
            elif spec.framing.footing_type == "diamond_pier":     # the landing sits on the same footing the deck does
                lm_ = spec.framing.footing_model if spec.framing.footing_model in PRICEBOOK["footings"] else fr0.footing_model   # an unpriced spec model: the pier the frame resolved to
                ucp, srcp = _price("footings", lm_)
                lines.append(Line("Stairs", f"Diamond Pier {lm_} — landing {li + 1} footings", 4, 4, "ea", "exact  (one under each landing post)", ucp, srcp))
                lb_ = POST_BASE.get(spec.framing.post_size, {}).get("diamond_pier", "ABA44Z")
                if lb_ == "ABA66Z" and spec.framing.post_rough:
                    lb_ = "ABA66RZ"
                if lb_ == "ABU88Z" and spec.framing.post_rough:
                    lb_ = "ABU88RZ"             # the same rough-8x8 base the deck posts take
                ucb, srcb = _price("footings", lb_)
                lines.append(Line("Stairs", f"{_desc('footings', lb_, 'Simpson ' + lb_)} on the pier bolt — landing {li + 1}", 4, 4, "ea", "exact", ucb, srcb))
                if lb_.startswith("ABU88"):
                    d_, uc_, src_ = _item("footings", "abu88_sds_anchor_set", "Simpson SDS 1/4\" x 3\" (8 per base) + 5/8\" x 6\" Titen HD (1 per base, the second anchor in the pier head)")
                    lines.append(Line("Stairs", f"{d_} — landing {li + 1}", 4, 4, "set", "exact  (one set per ABU88 base)", uc_ or 18.0, src_ or "EST — SDS25300 x 8 + THD62600H x 1"))
            else:
                uc, src = _price("footings", "concrete_pad")
                lines.append(Line("Stairs", f"Landing {li + 1} footings — 4 concrete piers 12\" x frost, bases set after the cure", 4, 4, "ea", "exact", uc * 0.6, src))
            sf_l = lw * ld / 144
            # the landing is decked in the field board, boards across it (parallel with the treads): rows x the landing's width, cut
            # from the shortest stock the line's own profile is sold in (Vintage square edge: 16'); a composite pools these pieces with
            # the field boards ("Field boards ..." cut pieces, composite._pool_decking) and drops this line
            rows_l = max(1, int(round(ld / (dk0.bw + dk0.gap))))
            cuts.append(CutPiece(f"Field boards landing {li + 1} ({st_s.side} stair)", f"{coll} {color}", lw, rows_l, "across the landing, parallel with the treads; fascia on its open sides"))
            tl_ = min(deck_lengths(coll, spec.decking.profile))
            nb = sum(len(v) for v in pack_boards([("landing", lw + 0.25)] * rows_l, stocks=(tl_,)).values())
            uc_l, src_l = _price("decking", f"{brand}|{coll}|{tl_}|{spec.decking.profile}")
            lines.append(Line("Stairs", f"{brand} {coll} {color} 1x6x{tl_} {'Grooved' if spec.decking.profile == 'grooved' else 'Square Edge'} — landing {li + 1} decking ({sf_l:.0f} SF)",
                              nb, nb, "ea", f"exact  ({rows_l} rows @ {ftin(lw)}, {int(tl_ * 12 // (lw + 0.375))} per {tl_}' board)", uc_l, src_l))
            if getattr(st_s, "skirts", False) and spec.decking.fascia:
                # a skirted stair's landing is wrapped in the fascia on all four sides (as the 3D draws it), packed with the deck's fascia
                lp_ = [(f"landing {li + 1} fascia ({st_s.side} stair)", round(lw + 1.0, 1))] * 2 + [(f"landing {li + 1} fascia ({st_s.side} stair)", round(ld, 1))] * 2
                Qz.fascia_pieces += lp_
                if dkf["material"] == "PVC":
                    Qz.fascia_screws += sum(4 + max(0, int(math.ceil(Lp / 12)) - 1) for _, Lp in lp_)

    # ================= HARDWARE / CONNECTORS
    hanger = spec.framing.hanger or HANGER_FOR_JOIST.get(jsize, "LUS210Z")
    d_, uc, src, sku = _hw(hanger, black)
    n_flush = sum(1 for bl in L.beam_lines if bl.kind == "flush" and not bl.label.startswith("FRONT"))
    why = (f"exact  (joists at the ledgers + rim ends" + (f" + both faces of the flush beam" if n_flush else "") + ")") if timber \
        else (f"exact  ({Qz.hangers_single} joist ends on the ledger" + (", the flush beams" if any(bl.kind == "flush" for bl in L.beam_lines) else "") + " and the square rims — framing plan)" if getattr(Qz, 'outline_ledgers', None) is not None
              else f"exact  ({Qz.n_joists} joists x {Qz.hangers_single // max(1, Qz.n_joists)} ends)")
    lines.append(Line("Hardware", d_, Qz.hangers_single, Qz.hangers_single, "ea", why, uc, src, sku))
    if Qz.hangers_double:
        dh = DOUBLE_HANGER.get(jsize, "HUCQ210-2-SDS")
        d_, uc, src, sku = _hw(dh, black)
        lines.append(Line("Hardware", d_, Qz.hangers_double, Qz.hangers_double, "ea",
                          "exact  (the hung rims at the flush beam; a divider joist hangs in a single hanger)" if timber else
                          ("exact  (the doubled rims hung square on the ledger" + (f" · stair notch: the trimmer's 2 ends, the 2 headers on the trimmer" if getattr(Qz, "notch_dh", 0) else "")
                           + ") — confirm stock") if getattr(Qz, "outline_ledgers", None) is not None else "exact  (2 side rims x 2 ends) — confirm stock", uc, src, sku))
    j_ = jsize.replace('2x', '2')
    hands_ = getattr(Qz, "skew_hands", None) or {}
    if Qz.hangers_skew and sum(len(v) for v in hands_.values()) == Qz.hangers_skew:     # D&D ships SUR and SUL apart: one line per hand, 1 spare each
        for h_, w_ in (("R", "right"), ("L", "left")):
            sd_ = sorted(set(hands_.get(h_, [])))
            if sd_:
                n_ = len(hands_[h_])
                lines.append(Line("Hardware", f"Simpson SU{h_}{j_}Z skewed 45-degree hanger, skewed {w_}", n_, n_ + 1, "ea",
                                  f"+1  ({n_} joist ends on the 45-degree rims of side{'s' if len(sd_) > 1 else ''} {', '.join(map(str, sd_))} — the joist runs off to the {w_}, from the framing plan)", 9.5, "est. — confirm D&D stock"))
    elif Qz.hangers_skew:
        lines.append(Line("Hardware", f"Simpson SUR{j_}Z / SUL{j_}Z skewed 45-degree hanger (right / left as the angle runs)", Qz.hangers_skew, Qz.hangers_skew + 2, "ea",
                          f"+2  (joist ends on the 45-degree rims, from the framing plan)", 9.5, "est. — confirm D&D stock"))
    if Qz.hangers_skew_double:
        h2_ = Counter(getattr(Qz, "skew2_hands", []))
        nt2_ = getattr(Qz, 'skew_double_note', 'the two angled rims at the ledger block beside the bay')
        if sum(h2_.values()) == Qz.hangers_skew_double:      # every hand known: one line per hand, as D&D ships them
            for h_, w_ in (("R", "right"), ("L", "left")):
                if h2_.get(h_):
                    lines.append(Line("Hardware", f"Simpson SU{h_}{j_}-2Z skewed double hanger, skewed {w_} — {nt2_}", h2_[h_], h2_[h_], "ea",
                                      f"exact  (the rim runs off to the {w_}, from the framing plan)", 24.0, "est. — confirm D&D stock"))
        else:
            lines.append(Line("Hardware", f"Simpson SUR{j_}-2Z / SUL{j_}-2Z skewed double hanger — {nt2_}", Qz.hangers_skew_double, Qz.hangers_skew_double, "ea",
                              "exact", 24.0, "est. — confirm D&D stock"))
    if getattr(Qz, "hangers_field", 0):
        lines.append(Line("Hardware", f"Simpson LSSU{j_}Z field-skewable hanger — joists on the bay's angled faces, bent to the bay's angle", Qz.hangers_field, Qz.hangers_field + 1, "ea",
                          f"+1  (joist ends on the bay faces, from the framing plan — the faces measure {Qz.bay_angles or 'off 45 degrees'} to the wall on the plan, not a true 45: bend each to fit; one spare bends to either hand)", 9.5, "est. — confirm D&D stock"))
    if getattr(Qz, "hangers_field_double", 0):
        lines.append(Line("Hardware", f"Simpson LSSU{jsize.replace('2x', '2')}-2Z field-skewable double hanger — the doubled rim where it dies into the bay face", Qz.hangers_field_double, Qz.hangers_field_double, "ea",
                          "exact", 24.0, "est. — confirm D&D stock"))
    oe_ = getattr(L, "outline_edges", None) or []
    def a35_at(p):          # the edge posts' A35Z, (2) per rim: both rims at a corner post, the one continuous rim over a mid-span post
        w_ = str(getattr(p, "where", ""))
        if "sides" not in w_:
            return 2
        return 2 * max(1, sum(1 for k in re.findall(r"\d+", w_.split("sides")[-1]) if not oe_ or oe_[int(k) - 1].exposed))
    n_a35e = sum(a35_at(p) for p in (getattr(L, "edge_posts", None) or []))
    # Simpson nail schedules, 10d = 0.148 x 3, 16d = 0.162 x 3-1/2 (SUR/SUL: C-C-2024; LSSU skewed: C-C-2017 p.143, the innermost acute-side face
    # hole left empty): LUS face + joist all 10d (LUS_NAILS); SUR/SUL210 (10) 16d + (10) 10d x 1-1/2; SUR/SUL210-2 (14) 16d + (6) 0.162 x 2-1/2;
    # LSSU210 (9) 10d + (7) 10d x 1-1/2; LSSU210-2 (14) 16d + (12) 10d x 1-1/2; A35Z (12) and H2.5AZ (10) 1-1/2"
    lus_ = hanger in LUS_NAILS
    nh, nj = LUS_NAILS.get(hanger) or HANGER_NAILS.get(hanger, (6, 4))
    n_sk, n_fd = Qz.hangers_skew, getattr(Qz, "hangers_field", 0)
    n_sk2, n_fd2 = Qz.hangers_skew_double, getattr(Qz, "hangers_field_double", 0)
    nail_parts = {"3": [(hanger + (" face + joist" if lus_ else " face"), Qz.hangers_single * (nh + (nj if lus_ else 0))), (f"LSSU{j_}Z face", 9 * n_fd)],
                  "16d": [(f"SUR/SUL{j_}Z face", 10 * n_sk), (f"SUR/SUL{j_}-2Z face", 14 * n_sk2), (f"LSSU{j_}-2Z face", 14 * n_fd2)],
                  "2.5": [(f"SUR/SUL{j_}-2Z joist", 6 * n_sk2)],
                  "1.5": [(f"{hanger} joist", 0 if lus_ else Qz.hangers_single * nj), (f"SUR/SUL{j_}Z joist", 10 * n_sk), (f"LSSU{j_}Z joist", 7 * n_fd),
                          (f"LSSU{j_}-2Z joist", 12 * n_fd2), ("H2.5AZ", Qz.h25 * H25_NAILS),
                          ("A35Z", 12 * (n_a35e + getattr(Qz, "a35_stair", 0)))]}      # + the inset stair's notch posts / stringer feet and the skirt studs
    n_long, n_short = sum(v for _, v in nail_parts["3"]), sum(v for _, v in nail_parts["1.5"])
    if timber:
        # 4x hangers take 16d into the header: from the ring-shank box, with the skewed hangers' face nails, the rim end-nailing and blocking toe-nails
        need16 = n_long + sum(v for _, v in nail_parts["16d"]) + 6 * Qz.n_blocks + 4 * Qz.n_joists
        d = PRICEBOOK["hardware"]["nail_16d_ring_2000"]
        boxes = max(1, int(math.ceil(need16 / d["count"])))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need16} needed — hanger headers, rim end-nailing, blocking toe-nails", d["each"], d["source"]))
        pairs = (("nail_16d_2.5_1lb", "2.5"), ("nail_1.5in_5lb", "1.5"))
    else:
        pairs = (("nail_3in_5lb", "3"), ("nail_16d_5lb", "16d"), ("nail_16d_2.5_1lb", "2.5"), ("nail_1.5in_5lb", "1.5"))
    for key, part in pairs:
        need = sum(v for _, v in nail_parts[part])
        if not need:                                  # nothing on this job takes that nail
            continue
        d = PRICEBOOK["hardware"][key]
        boxes = max(1, int(math.ceil(need / d["count"])))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need} needed of ~{boxes * d['count']}  (" + " · ".join(f"{k} {v}" for k, v in nail_parts[part] if v) + ")", d["each"], d["source"], key))
    hn_ = [w for n_, w in (
        (Qz.hangers_single if lus_ else 0, f"{hanger} ({nh}) 10d face + ({nj}) 10d driven at 45° into the header"),
        (Qz.hangers_double, f"{DOUBLE_HANGER.get(jsize, 'HUCQ210-2-SDS')} on the SDS screws in its box"),
        (n_sk, f"SUR/SUL{j_}Z (10) 16d face + (10) 10d x 1-1/2\" into the joist"),
        (n_sk2, f"SUR/SUL{j_}-2Z (14) 16d face + (6) 0.162\" x 2-1/2\" into the joist"),
        (n_fd, f"LSSU{j_}Z bent to the skew, (9) 10d face (the innermost hole on the acute side stays empty) + (7) 10d x 1-1/2\""),
        (n_fd2, f"LSSU{j_}-2Z bent to the skew, (14) 16d face + (12) 10d x 1-1/2\"")) if n_]
    if hn_ and not timber and spec.framing.system != "steel":     # the hanger nailing the order buys, as Simpson schedules it
        sched["Hangers"] = " · ".join(hn_) + " (Simpson; 10d = 0.148\" x 3\", 16d = 0.162\" x 3-1/2\")"
    if Qz.ledger_len:
        lf = spec.framing.ledger_fastener.lower()
        wall_lf = L.wall_lf / 12.0
        if lf.startswith("ledgerlok"):
            six = "6" in lf or timber
            key = "LedgerLOK6_50" if six else "LedgerLOK_50"
            if timber:
                n_ll = int(math.ceil(wall_lf * 12 / 8.0))          # 2 rows staggered 16" OC on every ledgered wall (ledgers + return walls)
                rule = f"LedgerLOK 6\" 2 rows staggered 16\" OC on {wall_lf:.1f} LF of house wall (ledgers + return walls; nothing on a privacy wall)"
            else:
                # every ledger piece at the longest joist span landing on it (FastenMaster: 12" OC only to 12' spans, 10" to 14')
                ol_ = getattr(Qz, "outline_ledgers", None)
                segs_ = ledger_spans(spec, L, None if ol_ is None else list(ol_), getattr(Qz, "outline_joists", []), list(getattr(Qz, "outline_ledger_blocks", None) or []))
                n_ll, rule = ledgerlok_count(segs_, eng.design_load_psf(spec.site.ground_snow_psf)[0] - eng.DEAD_PSF, jsp)
            d = PRICEBOOK["hardware"][key]
            boxes = int(math.ceil(n_ll / d["count"]))
            lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{n_ll} needed of {boxes * d['count']}", d["each"], d["source"], key))
        elif "bolt" in lf:
            n_ll, rule = eng.ledger_fastener_count(Qz.ledger_len, fr0.beams[0].back_span if fr0.beams else fr0.joist_len, "1/2 bolt")
            key = "bolt_1/2x6" if jb > 2 else "bolt_1/2x8"
            d_, uc, src, sku = _hw(key, black)
            lines.append(Line("Hardware", d_, n_ll, n_ll + 2, "ea", "+2", uc, src, sku))
        else:
            n_ll, rule = eng.ledger_fastener_count(Qz.ledger_len, fr0.beams[0].back_span if fr0.beams else fr0.joist_len, "1/2 lag")
            d = PRICEBOOK["hardware"]["lag_1/2x4"]
            lines.append(Line("Hardware", d["desc"], n_ll, n_ll + 2, "ea", "+2", d["each"], d["source"]))
        Qz.ledger_fasteners = n_ll
        sched["Ledger"] = f"{spec.ledger_size} ledger x {ftin(Qz.ledger_len)} total · {rule} · {n_ll} fasteners"
        if not timber:
            n_ledgers = _ledger_runs(Qz.outline_ledgers) if getattr(Qz, 'outline_ledgers', None) is not None else ((len(L.zones) if L.multi else 1))
            n_dtt = spec.framing.lateral_ties * max(1, n_ledgers)
            d = PRICEBOOK["hardware"]["DTT1Z"]
            lines.append(Line("Hardware", d["desc"], n_dtt, n_dtt, "ea", "exact  (spread evenly along each ledger, one within 24\" of each end — IRC R507.9.2(2))", d["each"], d["source"], "DTT1Z"))
            d = PRICEBOOK["hardware"]["lag_3/8x6"]          # the same 3/8" x 6" lag as the IRX rail posts': one line (the rail adds its posts to it)
            if n_dtt:
                lines.append(Line("Hardware", d["desc"] + " — DTT1Z lateral ties", n_dtt, n_dtt + 2, "ea",
                                  f"+2  ({n_dtt} DTT1Z x 1, through the ledger, 3\" min. into the house framing, predrilled — IRC R507.9.2(2))", d["each"], d["source"]))
    if getattr(L, "edge_posts", None):
        n4_ = sum(1 for p in L.edge_posts if a35_at(p) == 4)
        n_mid = sum(1 for p in L.edge_posts if "sides" not in str(getattr(p, "where", "")))
        n_hs = len(L.edge_posts) - n4_ - n_mid
        d_, uc, src, sku = _hw("A35Z", black)
        lines.append(Line("Hardware", "Simpson A35Z framing angle — the rims to the edge posts", n_a35e, n_a35e + 2, "ea",
                          f"+2  (2 per rim at each post: {n4_} corner posts x 4" + (f" · {n_mid} mid-span under one continuous rim x 2" if n_mid else "")
                          + (f" · {n_hs} where a rim ends at the house x 2" if n_hs else "") + ")", uc, src, sku))
    if Qz.h25:
        d_, uc, src, sku = _hw("H2.5AZ", False)
        lines.append(Line("Hardware", d_, Qz.h25, Qz.h25, "ea", "exact  (every joist, doubler and rim at the drop beam)" if timber else f"exact  ({Qz.n_joists} joists + 2 rims at each drop beam)", uc, src, sku))
    sd_screws = base_screws
    beam_lam = 0
    if timber:
        cm, ce = L.beam_lines[0].cap_mid, L.beam_lines[0].cap_end
        if caps_mid:
            d_, uc, src, sku = _hw(cm, black); lines.append(Line("Hardware", d_, caps_mid, caps_mid, "ea", "exact  (intermediate posts)", uc, src, sku))
        d_, uc, src, sku = _hw(ce, black); lines.append(Line("Hardware", d_, caps_end, caps_end, "ea", "exact  (beam-end posts)", uc, src, sku))
        if black:
            d_, uc, src, sku = _hw("black_shopcoat_lot", False); lines.append(Line("Hardware", d_, 1, 1, "lot", "all visible hardware black", uc, src))
    else:
        caps = Counter()
        for bl in L.beam_lines:
            caps[bl.cap_mid] += bl.n_posts
        for cap, n in caps.items():
            d_, uc, src, sku = _hw(cap, black)
            is_4x = all(parse_beam(bl.size)[1].startswith(("4x", "6x", "8x")) for bl in L.beam_lines)
            why = "exact" if not cap.startswith("BC46Z") or is_4x else "exact — (2)2x beam in a 4x cap needs a 1/2\" shim; confirm cap"
            lines.append(Line("Hardware", d_, n, n, "ea", why, uc, src, sku))
            sd_screws += n * POST_CAP_SCREWS.get(cap, 10)
        nb = 0
        for bl in L.beam_lines:
            plies_, nom_, _, _ = parse_beam(bl.size)
            if plies_ == 2 and nom_.startswith("4x"):
                nb += sum(2 * (int(math.ceil((b - a) / 24.0)) + 1) for a, b in bl.pieces)
            elif plies_ >= 2 and nom_.startswith("2x"):    # a built-up 2x beam: plies laminated like the rims, RSS 2 rows @ 12" staggered
                beam_lam += sum(2 * (int(math.ceil((b - a) / 12.0)) + 1) for a, b in bl.pieces) * (plies_ - 1)
        if beam_lam:
            sched["Beam"] = ("built-up 2x beam plies laminated with GRK RSS 3-1/8\" structural screws, 2 rows 2\" from top and bottom, staggered @ 12\" OC; "
                             "BC46Z cap at each post with SD screws (1/2\" shim: a (2)2x is 3\" in a 3-9/16\" cap)")
        if nb:
            d_, uc, src, sku = _hw("bolt_1/2x8", black)
            lines.append(Line("Hardware", d_, nb, nb + 2, "ea", f"+2  ((2)4x beam plies through-bolted, 2 rows staggered @ 24\" OC, 2\" from top and bottom)", uc, src))
            sched["Beam"] = "(2)4x plies through-bolted with 1/2\" HDG bolts, 2 rows 2\" from top and bottom, staggered @ 24\" OC, a bolt pair 6\" from each end; CCQ cap with SDS screws at each post"
    if sd_screws:
        d = PRICEBOOK["hardware"]["SD10212_100"]
        boxes = int(math.ceil(sd_screws / d["count"]))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{sd_screws} needed  (bases {base_screws}" + (f" · caps {sd_screws - base_screws}" if sd_screws > base_screws else "") + ")", d["each"], d["source"]))
    blk = 0 if timber else 6 * Qz.n_blocks          # (3) each end, as every detail draws it
    rail_blk = (12 if irx_blk_ else 6) * len(rl.posts) if (rl and surface_rail and not timber) else 0      # the post blocking (IRX: blocking + cross block), (3) each end
    box_rss = sum((4 * box_cross_members(st) + 2 * (int(math.ceil(st.width / 16.0)) + 1)) * st.geo.treads for st in stairs
                  if getattr(st, "build", "stringers") == "box")      # (2) each end of every cross member + (2) every 16" to the rim behind
    skirt_rss = (2 * sum(len(f_.studs) for f_ in skirt.faces) + 4 * sum(max(0, sum(1 for p_, _ in f_.studs if a_ - 1 <= p_ <= b_ + 1) - 1) for f_ in skirt.faces for a_, b_, _ in f_.rows)) if skirt else 0
    rss = Qz.rss_lam + beam_lam + blk + rail_blk + box_rss + skirt_rss
    if timber and Qz.n_blocks:
        sched["Blocking"] = f"{Qz.n_blocks} x {jsize} blocks, (3) 16d toe-nails each end"
    elif getattr(Qz, "outline_block_note", None):
        sched["Blocking"] = Qz.outline_block_note
    if rss:                                       # D&D sells the GRK RSS 3-1/8" in boxes of 50 (GRK70191)
        d = PRICEBOOK["hardware"]["RSS_3-1/8_50"]
        boxes = int(math.ceil(rss / d["count"]))
        lines.append(Line("Hardware", d["desc"] + (" — the frame and the box steps" if box_rss else ""), boxes, boxes, "box",       # (the box steps' crew day lists it too)
                          f"{rss} needed  (rim laminations {Qz.rss_lam} · " + (f"beam plies {beam_lam} · " if beam_lam else "") + f"blocking {blk}" + (f" · rail post blocks {rail_blk}" if rail_blk else "")
                          + (f" · box steps {box_rss}" if box_rss else "") + (f" · step-skirt studs + blocking {skirt_rss}" if skirt_rss else "") + f") · {boxes * d['count']} supplied", d["each"], d["source"]))
    if rl and n_rail_posts:
        if surface_rail and not timber and RAIL_SYSTEMS.get(rl.system, {}).get("post_lag"):
            # IRX 3" posts: (4) 3/8" x 6" HDG lags + washers through the base into the blocking (TimberTech IRX install guide, not
            # HeadLOK); a louvered-roof post that is the rail post bolts down through its own base plate. The DTT1Z ties take the
            # same lag: one order line, one +2
            d = PRICEBOOK["hardware"]["lag_3/8x6"]
            rf_ = [p for p in rl.posts if getattr(p, "roof", False)]
            n_rf = len(rf_)                              # rail-post positions on a roof post (a corner roof post ends two runs)
            n_roof = len({(p.roof if isinstance(p.roof, tuple) else (round(p.x / 12, 1), round(p.y / 12, 1))) for p in rf_})    # as louvered.takeoff_hook
            n_lp = n_rail_posts - n_rf
            who_, bolt_ = (("the louvered-roof post", "bolts down through its own base plate") if n_roof == 1 else
                           (f"the {n_roof} louvered-roof posts", "bolt down through their own base plates"))
            rw_ = "" if not n_rf else f"; {who_} {bolt_}" if n_rf == n_roof else f"; {n_rf} rail-post positions are {who_}, which {bolt_}"
            if n_lp > 0:
                irx_ = f"{n_lp} rail post{'s' if n_lp != 1 else ''} x 4 through the base plate into the blocking{rw_}"
                lag_ = next((l for l in lines if l.category == "Hardware" and l.item == d["desc"] + " — DTT1Z lateral ties"), None)
                if lag_ is None:
                    lines.append(Line("Hardware", d["desc"] + " — IRX rail posts", 4 * n_lp, 4 * n_lp + 2, "ea", f"+2  ({irx_})", d["each"], d["source"]))
                else:
                    lag_.item, lag_.net = d["desc"] + " — DTT1Z lateral ties + IRX rail posts", lag_.net + 4 * n_lp
                    lag_.order, lag_.why = lag_.net + 2, lag_.why[:-1] + f" · {irx_})"
        elif timber or RAIL_SYSTEMS.get(rl.system, {}).get("cable") or surface_rail:
            d = PRICEBOOK["hardware"]["HeadLOK6_50"]
            need = 4 * n_rail_posts
            boxes = int(math.ceil(need / d["count"]))
            lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need} needed  ({n_rail_posts} rail posts x 4)", d["each"], d["source"]))
        else:
            nb = 2 * n_rail_posts
            d_, uc, src, sku = _hw("bolt_7/16x4.5", black)
            lines.append(Line("Hardware", d_, nb, nb + 2, "ea", f"+2  ({n_rail_posts} rail posts x 2)", uc, src))
    for st in stairs:
        if getattr(st, "build", "stringers") == "box":           # its RSS screws are counted on the GRK RSS line (box steps)
            cf = st.width * st.geo.treads * st.geo.tread_in * 4.0 / 1728.0 * 1.25
            nbag = int(math.ceil(cf / 0.5))
            lines.append(Line("Stairs", f"3/4\" crushed rock / road base 0.5 cf bag — 4\" compacted bed under the box step ({st.side})", nbag, nbag, "bag",
                              f"exact  ({cf:.1f} cf incl. 25% compaction)", 6.5, "est."))
            continue
        d = PRICEBOOK["hardware"]["LSCZ"]
        n_sc = st.stringers * sum(1 for fg in st.geo.flights if fg.treads)
        lines.append(Line("Hardware", d["desc"], n_sc, n_sc, "ea", f"exact  ({st.side} stair, 1 per stringer at the rim" + (f" — {len(st.geo.flights)} flights" if len(st.geo.flights) > 1 else "") + ")", d["each"], d["source"], "LSCZ"))
        if getattr(st, "inset", False) and st.notch:
            n_a = 2 * st.notch_posts + st.stringers
            d_, uc, src, sku = _hw("A35Z", black)
            lines.append(Line("Hardware", f"Simpson A35Z framing angle — inset stair: the notch posts to the rim and header corners, the stringer heels to the base ledger",
                              n_a, n_a + 2, "ea", f"+2  ({st.notch_posts} posts x 2 + {st.stringers} stringer heels)", uc, src, sku))
            n_b = st.notch["ledger_bolts"] + 2 * st.notch_posts
            d_, uc, src = _item("hardware", "bolt_1/2x8")
            lines.append(Line("Hardware", d_ + " — inset stair: the base ledger and the notch posts through the lower level's rim", n_b, n_b + 2, "ea",
                              f"+2  ({st.notch['ledger_bolts']} in the base ledger @ 12\" staggered + {st.notch_posts} posts x 2)", uc, src))
    if skirt and any(f_.studs for f_ in skirt.faces):
        n_a = sum(len(f_.studs) for f_ in skirt.faces)
        d_, uc, src, sku = _hw("A35Z", black)
        lines.append(Line("Hardware", "Simpson A35Z framing angle — the step-skirt studs to the rim", n_a, n_a + 2, "ea", f"+2  ({n_a} studs, 1 each at the top)", uc, src, sku))
        # its RSS screws (2 per stud top, 2 each end of every blocking piece) are counted on the GRK RSS line
    if spec.extras.hot_tub:
        d_, uc, src, sku = _hw("tub_bay_lot", False)
        lines.append(Line("Hardware", d_, 1, 1, "lot", f"tub bay in zone {spec.extras.hot_tub_zone or 'A'} — RFI to the engineer", uc, src))

    # ================= FLASHING & WATERPROOFING
    wall_lf = L.wall_lf / 12.0
    if Qz.ledger_len:
        if timber or L.multi or Qz.ledger_len > 240:
            d = PRICEBOOK["hardware"]["vycor_12x75"]
            n = int(math.ceil(wall_lf / d["lf"]))
            lines.append(Line("Flashing & waterproofing", d["desc"], n, n, "roll", f"{wall_lf:.0f} LF of house wall with laps — nothing on a privacy wall", d["each"], d["source"]))
            d = PRICEBOOK["hardware"]["lflash_8_galv"]           # D&D's 8' galvanized (LFLASH448G)
            n = int(math.ceil(wall_lf / d["lf"]))
            lines.append(Line("Flashing & waterproofing", d["desc"], n, n, "ea", f"house walls only — {wall_lf:.0f} LF in 8' pieces lapped 3\" ({d['lf']:g}' of wall each); "
                              "it sits on the G-Tape over the ledger, never bare on the treated lumber", d["each"], d["source"], "LFLASH448G"))
            if spec.site.wui_fire_zone:
                d = PRICEBOOK["hardware"]["wui_flash_10"]
                n = int(math.ceil(wall_lf / 10))
                lines.append(Line("Flashing & waterproofing", d["desc"], n, n, "ea", "WUI practice — house walls only", d["each"], d["source"]))
        else:
            d = PRICEBOOK["hardware"]["flashing_set"]
            lines.append(Line("Flashing & waterproofing", d["desc"], 1, 1, "set", "exact", d["each"], d["source"]))
    if spec.framing.joist_tape or timber:
        if timber:
            wide = Qz.tape_joist_lf + Qz.tape_wide_lf + sum(bl.length for bl in L.beam_lines if bl.kind == "drop") / 12.0
            for key, need, what in (("gtape_4", wide, "tops of all 4x10 joists, rims, ledgers, beams"), ("gtape_2", Qz.tape_block_lf, "blocking, laps")):
                d = PRICEBOOK["hardware"][key]
                rolls = int(math.ceil(need * 1.05 / d["lf"]))
                lines.append(Line("Flashing & waterproofing", d["desc"] + f" — {what}", rolls, rolls, "roll", f"{need:.0f}' needed of {rolls * d['lf']}'", d["each"], d["source"]))
            sched["Joist tape"] = "G-Tape 4\" on every 4x10 top (joists, rims, ledgers) and the beams; 2\" on blocking"
        else:
            t2 = Qz.tape_joist_lf + Qz.tape_block_lf
            t4 = Qz.tape_wide_lf + sum(bl.length for bl in L.beam_lines if bl.kind == "drop") / 12.0
            for key, need in (("gtape_2", t2), ("gtape_4", t4)):
                d = PRICEBOOK["hardware"][key]
                rolls = int(math.ceil(need / d["lf"]))
                lines.append(Line("Flashing & waterproofing", d["desc"], rolls, rolls, "roll", f"{need:.0f}' needed of {rolls * d['lf']}'", d["each"], d["source"]))
            sched["Joist tape"] = ("G-Tape 2\" every joist, PF joist, blocking and the ledger top (under the flashing) · 4\" on " + ("both rims and the beam(s)" if L.beam_lines else "the doubled rims")
                                   + (" — one strip covers both plies" if fr0.rim_plies > 1 else ""))

    # ================= DECKING
    prof = "Grooved" if spec.decking.profile == "grooved" else "Square Edge"
    # the field's spares: +2 for the whole field (the standard), on the shortest length ordered that every row fits
    long_f = max([c.length_in + 0.25 for c in cuts if c.member.startswith("Field boards") and "landing" not in c.member] or [0.0])
    sp_f = next((s for s in sorted(Qz.field_boards) if long_f + 0.125 <= s * 12 - 2.0 + 1e-6), max(Qz.field_boards) if Qz.field_boards else 0)
    for stock, n_rows in sorted(Qz.field_boards.items()):
        fp = field_profile(spec, stock)          # a length sold grooved only (Vintage 12'): the grooved board, Cortex through the face
        key = f"{brand}|{coll}|{stock}|{fp}"
        uc, src = _price("decking", key)
        if uc == 0.0:
            lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * stock, 2)
        lines.append(Line("Decking", f"{brand} {coll} {color} 1x6x{stock} {'Grooved' if fp == 'grooved' else 'Square Edge'}", n_rows, n_rows + (2 if stock == sp_f else 0), "ea",
                          (f"+2  (the field's 2 spares, on the {stock}' every row fits · " if stock == sp_f else f"exact  (the field's 2 spares are on the {sp_f}' · ")
                          + " · ".join(n for n in Qz.field_piece_note if n.split(":")[0] and True) + ")"
                          + (f" · {stock}' is sold grooved: field rows only, Cortex through the face" if fp != spec.decking.profile else ""), uc, src))
    if Qz.rip_strips:
        n_rip = len(pack_boards([("rip", s) for s in Qz.rip_strips], stocks=(16,), kerf=0.125)[16]) if False else int(math.ceil(sum(s + 0.125 for s in Qz.rip_strips) / dk0.bw))
        stock = 16 if timber else min(deck_lengths(coll, "square"))
        uc, src = _price("decking", f"{brand}|{coll}|{stock}|square")
        if uc == 0.0:
            lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * stock, 2)
        lines.append(Line("Decking", f"{brand} {coll} {color} 1x6x{stock} Square Edge — rip boards at the house", n_rip, n_rip, "ea",
                          "exact  (" + " · ".join(f"{s:.2f}\"" for s in Qz.rip_strips) + " strips)", uc, src))
    tread_sq = []                                  # stair treads cut from the border boards: square edge, one spare shared with the borders
    tread_cx_ = "Cortex" in ((spec.decking.fastener_system or default_fastener_system(coll, spec.decking.profile)), spec.decking.border_fastener)   # treads on Cortex + plugs
    if spec.geometry.picture_frame and Qz.border_pieces:
        if (bcoll, bcolor) == (coll, color) and spec.decking.profile == "grooved":     # a grooved field board can't be a tread (the nosing shows)
            for st in stairs:
                me_, mk_ = miter_of(st)                  # only the box step the scene miters runs long to the corner
                tread_sq += [(f"tread ({st.side})", round(st.width + me_ * mk_ * (st.geo.treads * st.geo.tread_in + 1.0) + 0.25, 2))] * st.tread_pieces
            L.treads_in_borders = {st.side for st in stairs} if tread_sq else set()      # a composite's field pool leaves these stairs' treads out
        stk_b = tuple(s_ for s_ in ((16, 20) if timber or L.multi else (12, 16, 20)) if s_ in deck_lengths(bcoll, "square")) or deck_lengths(bcoll, "square")
        packed_b = repack_boards(pack_boards(Qz.border_pieces + tread_sq, stocks=stk_b), stk_b) if tread_sq else pack_boards(Qz.border_pieces, stocks=stk_b)
        long_b = max(l for _, l in Qz.border_pieces + tread_sq)
        sp_b = next((s for s in sorted(packed_b) if long_b + 0.125 <= s * 12 - 2.0 + 1e-6), max(packed_b)) if tread_sq else max(packed_b)   # the spare: the shortest board the longest piece fits
        off_b = _offcut_spare(packed_b, long_b) if tread_sq else 0.0                                       # ... unless an offcut already holds it
        what_b = ["borders"] + (["dividers"] if L.divider_x else []) + (["stair treads"] if tread_sq else [])
        for s_, boards in sorted(packed_b.items()):
            key = f"{brand}|{bcoll}|{s_}|square"
            uc, src = _price("decking", key)
            if uc == 0.0:
                lf, src = _price("decking", f"{brand}|{bcoll}|per_lf"); uc = round(lf * s_, 2)
            what = " · ".join(" + ".join(f"{n} {ftin(l)}" for n, l in b) for b in boards)
            sp_ = 1 if (s_ == sp_b and not off_b) else 0
            lines.append(Line("Decking", f"{brand} {bcoll} {bcolor} 1x6x{s_} Square Edge — " + (", ".join(what_b[:-1]) + " & " + what_b[-1] if len(what_b) > 1 else what_b[0]),
                              len(boards), len(boards) + sp_, "ea", ("+1  " + ("(one spare for the borders and treads · " if tread_sq else "(") if sp_ else "exact  (")
                              + what + (f"; the spare is a {ftin(off_b)} offcut" if off_b and s_ == sp_b else "") + ")", uc, src))
            tl_, al_ = (sum(l for b in boards for n, l in b if n.startswith(nm_)) for nm_ in ("tread (", ""))
            if tl_ and al_:                        # the price breakdown: each stair carries its treads' share of the boards they are cut from
                lines[-1].split = {"Decking": 1 - tl_ / al_, "Stairs": tl_ / al_}
        for name, Lb in Qz.border_pieces:
            cuts.append(CutPiece(name.capitalize(), f"{bcoll} {bcolor} square", Lb, 1, "a breaker: on the blocks between its two divider joists (on a zone line, the two rims)"
                                 if name.lower().startswith(("breaker", "divider")) else "miter at the corners"))
    hardie_risers = []                              # (stair, width) riser pieces cut from HardieTrim when there is a Hardie skirt
    for st in stairs:                               # miter_of (stairs lumber): a box step that wraps a corner runs its treads and risers long to the miter
        tl = min(deck_lengths(coll, "square"))        # the shortest square-edge stock the line is sold in (Vintage: 16')
        m_ends, m_k = miter_of(st)
        cut_w = st.width + m_ends * m_k * (st.geo.treads * st.geo.tread_in + 1.0)      # the outer edge of the lowest tread / riser, to the miter
        per_board = max(1, int(math.floor(tl * 12 / (cut_w + 0.25))))
        nb = int(math.ceil(st.tread_pieces / per_board))
        uc, src = _price("decking", f"{brand}|{coll}|{tl}|square")
        if uc == 0.0:
            lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * tl, 2)
        if not tread_sq:                              # else the treads are cut from the border boards (Decking)
            lines.append(Line("Stairs", f"{brand} {coll} {color} 1x6x{tl} Square Edge — treads ({st.side} stair)", nb, nb + 1, "ea",
                              f"+1  ({st.geo.treads} tread{'s' if st.geo.treads != 1 else ''} x 2 boards @ {ftin(st.width)}, {per_board} per board)", uc, src))
        if st.riser_pieces:
            nr = int(math.ceil(st.riser_pieces / max(1, int(math.floor(144 / (cut_w + 0.25))))))     # riser boards are 12' (not the tread stock)
            if spec.extras.hardie_skirt:                # a Hardie skirt: the risers match it, HardieTrim ripped to height (one cut plan with the fascia, below)
                sup_ = st.stringers or int(math.ceil(st.width / 16.0)) + 1     # nailed 2 at every stringer, or every 16" along a box step's front rim (TR1509)
                hardie_risers += [(f"{st.side} stair", cut_w, h_, sup_) for h_ in _riser_rips(st, dkf.get("thick", 1.0))]
            else:
                uc, src = _price("decking", f"{brand}|{coll}|riser")
                if uc == 0.0:
                    lf, src = _price("decking", "generic_riser_per_lf"); uc = round(lf * 12, 2)
                lines.append(Line("Stairs", f"{brand} {coll} {color} riser board 7-1/4\" x 12' ({st.side} stair)", nr, nr, "ea",
                                  f"exact  ({st.geo.risers} risers @ {ftin(st.width)})", uc, src))
        mtxt_ = (f"; mitered at the corner{'s' if m_ends > 1 else ''} to the next box step (outer edge {ftin(cut_w)})" if m_ends else "")
        cuts.append(CutPiece(f"Stair treads ({st.side})", f"{coll} {color} square", st.width, st.tread_pieces, "2 boards per tread, nosing 3/4\" over the riser"
                             + (("; cut from the square-edge border boards" + (", Cortex + plugs" if tread_cx_ else "")) if tread_sq else "") + mtxt_))
        if st.riser_pieces:
            if spec.extras.hardie_skirt:                # James Hardie TR1509 09/25 (valid in CO): clearances, the ripped edge up, every cut sealed
                rr_ = _riser_rips(st, dkf.get("thick", 1.0))
                rnote_ = (f"rip to {inches_frac(rr_[0])} ({inches_frac(st.geo.riser_in)} rise less the {inches_frac(dkf.get('thick', 1.0)).removeprefix('0-')} tread less a 1/4\" gap over the tread below, TR1509 Fig. 2/5)"
                          + (f", the bottom one to {inches_frac(rr_[-1])} (2\" off the soil, TR1509 Fig. 3)" if rr_[-1] != rr_[0] else "")
                          + "; two to an 11-1/4\" width where they fit, factory edge down, Edge Sealer on every cut")
            else:
                rnote_ = f"rip to {st.geo.riser_in:.2f}\" less tread thickness"
            cuts.append(CutPiece(f"Stair risers ({st.side})", "HardieTrim" if spec.extras.hardie_skirt else "riser board", st.width, st.riser_pieces, rnote_ + mtxt_))
    # the step-face skirt: the decking fascia set vertically, cut to height (4 to a 12' board), fastened at every nailer
    if skirt:
        hs = sorted(skirt.panel_heights(), reverse=True)
        rem_ = []                                   # first fit into 12' fascia stock
        for h_ in hs:
            for i_, r_ in enumerate(rem_):
                if r_ >= h_ + 0.125:
                    rem_[i_] -= h_ + 0.125; break
            else:
                rem_.append(144.0 - h_ - 0.125)
        fas_ = FASCIA[dkf["material"]]
        fcol = spec.decking.fascia_color or color
        uc, src = _price("decking", f"{brand}|{coll}|fascia")
        if uc == 0.0:
            lf, src = _price("decking", "generic_fascia_per_lf"); uc = round(lf * 12, 2)
        full_ = sum(1 for h_ in hs if h_ >= max(hs) - 0.01)
        lines.append(Line("Fascia", f"{brand} {coll} Fascia {fcol} {fas_['thick']:g}x{fas_['width']:g}x12 — step-face skirt, set vertically", len(rem_), len(rem_) + 1, "ea",
                          f"+1  ({len(hs)} panels {fas_['width']:g}\" wide: {full_} at {inches_frac(max(hs), 8)} on the step face, {len(hs) - full_} stepped on the stair cheeks; "
                          f"{int(144 // (max(hs) + 0.125))} to a board)", uc, src))
        cuts.append(CutPiece("Step-skirt panels", f"fascia {fcol}", max(hs), len(hs),
                             f"vertical, {fas_['width']:g}\" wide, {skirt.gap:g}\" seams, 1/4\" off the lower deck; the cheek panels cut stepped 1/8\" over the treads"))
        n_ss = skirt.panel_screws()
        if dkf["material"] == "PVC" and "TOPLoc_PVC_fascia_100" in PRICEBOOK["decking"]:
            d = PRICEBOOK["decking"]["TOPLoc_PVC_fascia_100"]
            packs = max(1, int(math.ceil(n_ss / d["count"])))
            lines.append(Line("Fasteners", f"TimberTech TOPLoc fascia screws for Advanced PVC fascia, {fcol} (100 ct, 30 LF) — step-face skirt", packs, packs, "pack",
                              f"{n_ss} screws  ({len(hs)} panels: 2 at each board end + 2 every 12\" on the nailers, pre-drilled) · {packs * d['count']} supplied", d["each"], d["source"]))
        else:
            d = PRICEBOOK["decking"]["CapTor_xd_350"]
            packs = max(1, int(math.ceil(n_ss / d["count"])))
            lines.append(Line("Fasteners", f"Starborn Cap-Tor xd 2-3/4\" Epoxy {fcol} 350 ct — step-face skirt", packs, packs, "box", f"{n_ss} screws (2 per nailer per panel)", d["each"], d["source"]))
        sched["Step skirt"] = (f"vertical fascia panels on 2x4 nailers, TOPLoc fascia screws (color-matched): 2 at each board end, then 2 every 12\" on the nailers, pre-drilled; "
                               f"panels {skirt.gap:g}\" apart, 1/4\" off the lower deck, tight under the picture-frame board")

    # ================= BUILT-INS: benches (4x4 legs wrapped in deck board, 2x4 seat frame) and planters (2x4 box, OSB, deck-board skin)
    from .scene import bench_segments, planter_segments
    bl = min(deck_lengths(coll, "square"))           # built-ins cut from the shortest square-edge stock sold (Vintage: 16')
    uc12, src12 = _price("decking", f"{brand}|{coll}|{bl}|square")
    if uc12 == 0.0:
        lf, src12 = _price("decking", f"{brand}|{coll}|per_lf"); uc12 = round(lf * bl, 2)     # per LF x the stock cut (Terrain+: 16')
    dcx, dcxn, dcxk = _cortex(coll, color)           # the board's own Cortex kit (composite: the 100 LF kit)
    uc44, src44 = _lumber_price("4x4", 8)
    P2X4 = (round(0.85 * 8, 2), "est. — 2x4 PT not on the GS sheet")
    bsegs = bench_segments(spec)
    if bsegs:
        blf = sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1, *_ in bsegs)
        pieces, n_back, n_front, n_cross, rail_lf = [], 0, 0, 0, 0.0
        prev_end = None
        for x0, y0, x1, y1, nx, ny, bn in bsegs:
            Lb_ = math.hypot(x1 - x0, y1 - y0) * 12
            seat, back = float(bn.get("seat_in", 17)), (float(bn.get("back_in", 34)) if bn.get("back", True) else 0.0)
            n_l = max(2, int(math.ceil(Lb_ / 36.0)) + 1)          # posts at 36" max: the back slats span between them
            shared = prev_end is not None and abs(prev_end[0] - x0) < 0.05 and abs(prev_end[1] - y0) < 0.05
            n_back += n_l - (1 if shared else 0)
            n_front += n_l - (1 if shared else 0)
            n_cross += int(math.ceil(Lb_ / 16.0)) + 1                # seat supports at 16" (composite span)
            rail_lf += 2 * Lb_ / 12
            pieces += [("seat", Lb_ + 1)] * 3 + [("apron", Lb_ + 1)] + ([("back slat", Lb_ + 1)] * 3 if back else [])
            pieces += [("post wrap", back - 0.5)] * (4 * n_l) + [("leg wrap", seat - 6.5)] * (4 * n_l)
            prev_end = (x1, y1)
        nb = sum(len(v) for v in pack_boards(pieces, stocks=(bl,)).values())
        lines.append(Line("Benches", f"{brand} {coll} {color} 1x6x{bl} Square Edge — bench seats, aprons, back slats and post wraps ({len(bsegs)} sections, {ftin(blf * 12)})", nb, nb + 1, "ea",
                          f"+1  ({len(pieces)} pieces packed into {bl}' boards)", uc12, src12))
        post_len = 44.0                                          # rim bottom to the back's top
        n44 = int(math.ceil(n_back / 2)) + int(math.ceil(n_front / 8))
        lines.append(Line("Benches", f"4x4x8 #2 GC ground-contact — {n_back} back posts (bolted through the rim, {post_len:.0f}\") + {n_front} front legs (10-1/2\"), all wrapped", n44, n44 + 1, "ea",
                          f"+1  (2 back posts per stick, 8 legs per stick)", uc44, src44))
        n26 = int(math.ceil((rail_lf * 12 + n_cross * 14.0) * 1.1 / (12 * 12)))
        uc26, src26 = _lumber_price("2x6", 12)
        lines.append(Line("Benches", f"2x6x12 #1 KDAT GC — seat rails (front + back) and {n_cross} seat supports at 16\" OC", n26, n26 + 1, "ea",      # no 2x6 TrueFrame: D&D's #1 KDAT
                          f"+1  ({rail_lf:.0f} LF rails + {n_cross} x 14\")", uc26, src26))
        ncx = len(pieces) * 4
        lines.append(Line("Benches", f"{dcxn} — bench seats, aprons, slats, wraps ({dcxk})", -(-ncx // dcx["count"]), -(-ncx // dcx["count"]), "box", f"~{ncx} screws", dcx["each"], dcx["source"], _sku(dcx, color)))
        lines.append(Line("Benches", "1/2\" x 8\" HDG carriage bolt + nut + washer — back posts through the rim", 2 * n_back, 2 * n_back + 2, "ea", f"+2  (2 per back post)", 3.1, "est."))
        d_rss = PRICEBOOK["hardware"]["RSS_3-1/8_50"]
        lines.append(Line("Benches", d_rss["desc"] + " — seat rails and supports", 2, 2, "box", "est.", d_rss["each"], d_rss["source"]))
        notes.append(f"benches: {len(bsegs)} sections, {ftin(blf * 12)} — seat 17\" high x 17\" deep, back to 34\", 4x4 posts at 36\" max wrapped in deck board, seat supports at 16\"; same footprint as the existing benches")
    ds = getattr(spec.geometry, "door_step", None)
    if ds:
        wd = (float(ds["x1"]) - float(ds["x0"])) * 12; dd = float(ds.get("depth_in", 21)); rr = float(ds.get("rise_in", 7))
        rows = int(math.ceil(dd / 5.55))
        hr = bool(spec.extras.hardie_skirt)            # a Hardie skirt: the door-step riser is HardieTrim too
        nb = sum(len(v) for v in pack_boards([("tread", wd + 1)] * rows + ([] if hr else [("riser", wd + 1)]) + [("end", dd + 1)] * 2, stocks=(bl,)).values())
        lines.append(Line("Stairs", f"{brand} {coll} {color} 1x6x{bl} Square Edge — door step tread rows{'' if hr else ', riser'} and returns ({ftin(wd)} x {dd:g}\", {rr:g}\" rise)", nb, nb + 1, "ea", "+1", uc12, src12))
        oc_ds = eng.tread_support_oc(coll, dkf["material"] == "Wood")[0]          # the tread boards span joist to joist: the tread line's max
        if hr:                                          # on the deck: 1/4" over the decking, nailed at the box rim + every joist
            hardie_risers.append(("door step", wd + 1, round(rr - dkf.get("thick", 1.0) - 0.25, 3), int(math.ceil(wd / oc_ds - 1e-9)) + 1))
        n26 = int(math.ceil((2 * wd + (int(math.ceil(wd / oc_ds - 1e-9)) + 1) * dd) * 1.1 / (12 * 12)))
        uc26, src26 = _lumber_price("2x6", 12)
        lines.append(Line("Stairs", f"2x6x12 #1 KDAT GC — door step box (rim + joists at {oc_ds:g}\" max), on the deck", n26, n26 + 1, "ea", "+1", uc26, src26))
        notes.append(f"door step: the existing step at the door rebuilt as a box step {ftin(wd)} x {dd:g}\" deep, {rr:g}\" up to the threshold")
    psegs = planter_segments(spec)
    if psegs:
        plf = sum(math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1, *_ in psegs)
        pieces, studs, plates_lf, osb_sf = [], 0, 0.0, 0.0
        for x0, y0, x1, y1, nx, ny, pl in psegs:
            Lp = math.hypot(x1 - x0, y1 - y0) * 12 - 2 * 0.6 * float(pl.get("width_in", 17))
            w, h = float(pl.get("width_in", 17)), float(pl.get("height_in", 17))
            rows = int(math.ceil((h - 1) / 5.55))
            pieces += [("side", Lp + 1)] * (2 * rows) + [("end", w + 1)] * (2 * rows) + [("cap", Lp + 6)] * 2 + [("cap", w + 6)] * 2
            studs += 2 * (int(math.ceil(Lp / 12)) + 1) + 4
            plates_lf += 2 * 2 * (Lp + w) / 12
            osb_sf += (2 * (Lp + w) * h + Lp * w) / 144
        nb = sum(len(v) for v in pack_boards(pieces, stocks=(bl,)).values())
        lines.append(Line("Planters", f"{brand} {coll} {color} 1x6x{bl} Square Edge — planter skin on all sides + picture-frame cap ({len(psegs)} planter{'s' if len(psegs) > 1 else ''}, {ftin(plf * 12)})", nb, nb + 1, "ea",
                          f"+1  ({len(pieces)} pieces packed into {bl}' boards)", uc12, src12))
        n24 = int(math.ceil((studs * 16 / 12 + plates_lf) / 8 * 1.1))
        lines.append(Line("Planters", "2x4x8 #2 PT — planter walls: studs 12\" OC, top and bottom plates, all treated", n24, n24 + 1, "ea", f"+1  ({studs} studs + {plates_lf:.0f} LF plates)", *P2X4))
        nos = int(math.ceil(osb_sf / 32 * 1.15))
        lines.append(Line("Planters", "7/16\" OSB 4x8 — planter sheathing (walls + bottom), under the deck-board skin", nos, nos, "sheet", f"{osb_sf:.0f} SF", 18.0, "est."))
        lines.append(Line("Planters", "Planter liner — 6-mil poly + drainage mat, stapled inside", 1, 1, "lot", "est.", 45.0, "est."))
        ncx = len(pieces) * 4
        lines.append(Line("Planters", f"{dcxn} — planter skin and cap ({dcxk})", -(-ncx // dcx["count"]), -(-ncx // dcx["count"]), "box", f"~{ncx} screws", dcx["each"], dcx["source"], _sku(dcx, color)))
        notes.append(f"planters: {len(psegs)} — 17\" x 17\" x the side's length, treated 2x4 at 12\" OC with plates, OSB, deck board on all sides, picture-frame cap")

    # ================= ROOF COVERS (with or without a rail)
    _covs = covers_of(spec)
    for _c in _covs:
        lines += cover_lines(spec, _c, tag=_c["name"] if len(_covs) > 1 else "")
        if _c.get("footing") == "deck_pier" and spec.framing.footing_type == "diamond_pier":
            loads = shared_pier_loads(spec, L, _c)
            cap = PRICEBOOK["footings"].get(spec.framing.footing_model, {}).get("capacity_lb", 3300)
            over = [ld for ld in loads if ld[1] + ld[2] > cap]
            if over and spec.framing.footing_model != "DP-75/63":
                up = PRICEBOOK["footings"]["DP-75/63"]["each"] - PRICEBOOK["footings"].get(spec.framing.footing_model, {}).get("each", 0.0)
                lines.append(Line("Footings", f"Upgrade to Diamond Pier DP-75/63 at the shared {_c['name'].lower()} posts (roof + deck on one pier)", len(over), len(over), "ea",
                                  "exact  (" + " · ".join(f"{ftin(x * 12)}: {r + d:,.0f} lb" for x, r, d in over) + f" vs {cap:,.0f} lb)", round(up, 2), "est.", "DP-75/63"))

    # ================= FASCIA
    fpcs_ = list(Qz.fascia_pieces)
    if spec.decking.fascia and fpcs_:
        # a closed-riser stair / box step on an outline side: its top riser is the face there, so the fascia runs only beside the opening
        # (none where a box step takes the whole side); a box step's mitered corner has no end skirt (counted per free end with the
        # stairs lumber, miter_of). The fascia screws come off with the pieces. An open-riser stair leaves the rim to the fascia; an
        # option stair leaves the base fascia whole (the 3D toggles it).
        fscr_ = lambda L_: 4 + max(0, int(math.ceil(L_ / 12)) - 1)     # composite / PVC fascia: 2 at each end, then every 12" (layout)
        oe_, ops_, drop_ = {e.name: e for e in (L.outline_edges or [])}, defaultdict(list), 0
        for st in stairs:
            if st.side in oe_ and st.riser_pieces and not getattr(st, "option", ""):
                ops_[st.side].append((st.opening.start_in, st.opening.start_in + st.width, "box step" if getattr(st, "build", "") == "box" else "stair"))
        for side_, os_ in ops_.items():
            k_ = next((k for k, (n, _) in enumerate(fpcs_) if n == f"fascia {side_}"), None)
            if k_ is None:
                continue
            Le_, cur_, segs_ = oe_[side_].length, 0.0, []
            for a_, b_, _ in sorted(os_):
                if a_ > cur_ + 0.5:
                    segs_.append((cur_, a_))
                cur_ = max(cur_, b_)
            if Le_ > cur_ + 0.5:
                segs_.append((cur_, Le_))
            new_ = [(f"fascia {side_} (" + (f"{j + 1} of {len(segs_)}, " if len(segs_) > 1 else "") + f"beside the {side_} {os_[0][2]})",
                     round(b_ - a_ + 0.75 * ((a_ < 0.5) + (b_ > Le_ - 0.5)), 2)) for j, (a_, b_) in enumerate(segs_)]     # 3/4" per outline corner
            drop_ += fscr_(fpcs_[k_][1]) - sum(fscr_(l_) for _, l_ in new_)
            fpcs_[k_:k_ + 1] = new_
            fg_ = dict(getattr(L, "fascia_gaps", None) or {})     # the 3D stops the fascia at the same openings (scene.py: inches along the edge)
            fg_[side_] = sorted(set(fg_.get(side_, [])) | {(round(a_, 2), round(b_, 2)) for a_, b_, _ in os_})
            L.fascia_gaps = fg_
        Qz.fascia_screws = max(0, Qz.fascia_screws - drop_)
        packed_f = pack_boards(fpcs_, stocks=(12,), kerf=0.125)     # fascia is sold 12': a longer run is 2+ pieces joined on a joist
        nf = sum(len(b) for b in packed_f.values())
        uc, src = _price("decking", f"{brand}|{coll}|fascia")
        if uc == 0.0:
            lf, src = _price("decking", "generic_fascia_per_lf"); uc = round(lf * 12, 2)
        fas = FASCIA[dkf["material"]]
        why = "+1  (" + " · ".join(f"{n} {ftin(Lf)}" for n, Lf in fpcs_) + ")"
        if not spec.extras.hardie_skirt:            # HardieTrim: its own cut plan with the risers (below)
            lines.append(Line("Fascia", f"{brand} {coll} Fascia {spec.decking.fascia_color or color} {fas['thick']:g}x{fas['width']:g}x12", nf, nf + 1, "ea", why, uc, src))
        face_ = decking_facts(spec.decking.collection).get("thick", 1.0) + actual(spec.framing.joist_size)[1] + 1.56   # the frame face + the drop below the rim (as modeled)
        rip_ = (f"ripped to {inches_frac(face_)} (the {spec.framing.joist_size} frame face + 1-1/2\" below the rim); " if fas["width"] > face_ + 0.5 else "")
        for name, Lf in fpcs_:
            cuts.append(CutPiece(name.capitalize(), "fascia", Lf, 1, rip_ + "flush under the board nose; full board at the front corners, short piece at the house"
                                 + ("; 1/4\" off hardscape, 2\" off soil (TR1509 Fig. 2/3), Edge Sealer on every cut" if spec.extras.hardie_skirt else "")))
    elif not spec.decking.fascia:
        notes.append("no fascia — the rim is the finished edge under a 1-1/2\" board overhang" + (" (timber, end grain sealed)" if timber else ""))
    if spec.extras.hardie_skirt and (hardie_risers or (spec.decking.fascia and fpcs_)):
        # HardieTrim per James Hardie TR1509 09/25 (valid in CO): the risers (stair, length, rip height, supports) cut in one plan with the
        # fascia — two to an 11-1/4" width where their heights fit, on the fascia boards' offcuts — so the riser line is the boards they add;
        # 2-1/2" 16-ga Type 316 stainless ring-shank finish nails on a wood frame (screws into steel: TR1509 p.3); the James Hardie touch-up kit seals
        # every field cut (TR1509 p.9)
        hd, hcol = PRICEBOOK["cover"]["hardie_trim_4_4x12_12ft"], _hardie_words(spec)
        full_ = fpcs_ if spec.decking.fascia else []
        nf_ = sum(len(b) for b in repack_boards(pack_boards(full_, stocks=(12,), kerf=0.125), (12,)).values()) if full_ else 0
        rq_, lanes_ = sorted(hardie_risers, key=lambda r: (-r[1], -r[2])), []
        while rq_:
            r0 = rq_.pop(0)
            k_ = min((k for k, r in enumerate(rq_) if r0[2] + r[2] + 0.125 <= 11.25), key=lambda k: abs(rq_[k][1] - r0[1]), default=None)
            r1 = rq_.pop(k_) if k_ is not None else None
            lanes_.append((f"riser {r0[0]}", max(r0[1], r1[1] if r1 else 0.0) + 0.25))
        nc_ = sum(len(b) for b in repack_boards(pack_boards(full_ + lanes_, stocks=(12,), kerf=0.125), (12,)).values()) if lanes_ else nf_
        if full_:
            lines.append(Line("Fascia", f"Deck fascia — HardieTrim 4/4 x 12 x 12' smooth ColorPlus {hcol} (wraps the double rim, in place of the composite fascia)", nf_, nf_ + 1, "ea",
                              "+1  (" + " · ".join(f"{n} {ftin(Lf)}" for n, Lf in full_) + ")", hd["each"], hd["source"]))
        if hardie_risers:
            what = " · ".join(f"{sum(1 for r in hardie_risers if r[0] == k)} @ {ftin(max(r[1] for r in hardie_risers if r[0] == k))} ({k})" for k in dict.fromkeys(r[0] for r in hardie_risers))
            lines.append(Line("Stairs", f"HardieTrim 4/4 x 12 x 12' smooth ColorPlus {hcol} — every riser (stairs" + (" + door step" if ds else "") + "), ripped to height", nc_ - nf_, nc_ - nf_, "ea",
                              f"exact  ({len(hardie_risers)} riser{'s' if len(hardie_risers) != 1 else ''}: {what} — {len(lanes_)} board width{'s' if len(lanes_) != 1 else ''}, "
                              "two risers to a width where they fit"
                              + (f"; one cut plan with the fascia: {nc_} boards for both, {nf_} for the fascia alone" if full_ else "") + ")", hd["each"], hd["source"]))
        n_fa = sum(4 * (int(math.ceil(max(0.0, Lf - 2.0) / 16.0)) + 1) for n, Lf in full_ if not n.startswith("stair skirt"))    # 4 per 16", 1" from each end
        n_sk = sum(2 * (int(math.ceil(max(0.0, Lf - 2.0) / 16.0)) + 1) for n, Lf in full_ if n.startswith("stair skirt"))        # 2 at every support along the skirt
        n_ri = sum(2 * r[3] for r in hardie_risers)
        steel_ = spec.framing.system == "steel"         # TR1509: finish nails into wood only — screws (or ET&F pins) into steel framing
        dn_, cat_ = PRICEBOOK["cover"]["hardie_trim_screws_100" if steel_ else "hardie_finish_nail_316_1000"], ("Fascia" if full_ else "Stairs")
        n_hn, cnt_, ed_ = n_fa + n_sk + n_ri, dn_.get("count", 100), ("3/4\"" if steel_ else "1/2\"")
        bx_ = max(1, int(math.ceil(n_hn / cnt_)))
        lines.append(Line(cat_, dn_["desc"].replace("Timber Bark", hcol) if steel_ else dn_["desc"], bx_, bx_, "box",
                          f"{n_hn} {'screws' if steel_ else 'nails'}  (fascia {n_fa}: 4 per 16\" · skirts {n_sk} + risers {n_ri}: 2 at every stringer / support · {ed_} from the edges, "
                          f"1\" from the ends" + ("; steel frame: screws, not finish nails — TR1509" if steel_ else "") + f") · {bx_ * cnt_:,} supplied", dn_["each"], dn_["source"]))
        tu = PRICEBOOK["cover"]["hardie_touchup"]
        sf_ = (nc_ + (1 if full_ else 0)) * 11.25       # a 12' x 11-1/4" board is 11.25 SF
        nk_ = max(1, int(math.ceil(sf_ / tu.get("sf", 1600))))
        lines.append(Line(cat_, tu["desc"].replace("Timber Bark", hcol), nk_, nk_, "kit", f"exact  (~{sf_:.0f} SF of HardieTrim; Edge Sealer on every field cut, Nail Concealer on the nail heads — TR1509)",
                          tu["each"], tu["source"]))
        sched["HardieTrim"] = ("James Hardie TR1509 09/25: " + ("color-matched 316SS trim screws into the steel framing (finish nails go into wood only)" if steel_ else
                               "2-1/2\" 16-ga Type 316 stainless ring-shank finish nails (2\" min; never a smooth-shank stainless nail)") + f" — 4 per 16\" on the fascia, 2 at every stringer / support on the risers and skirts, "
                               f"{ed_} from the edges, 1\" from the ends; 1/4\" off hardscape and decking, 2\" off soil; risers ripped, factory edge down; "
                               "ColorPlus Edge Sealer on every field cut, Nail Concealer on the heads")

    # one line for every HardieTrim finish nail on the job (the deck's fascia and risers, each roof cover's fascia and rakes): one box count
    dn_ = PRICEBOOK["cover"]["hardie_finish_nail_316_1000"]
    hn_ = [l for l in lines if l.item.startswith(dn_["desc"]) and re.match(r"\d+ nails", l.why or "")]
    if len(hn_) > 1:
        hn_.sort(key=lambda l: l.category == "Porch cover")      # the deck's own line carries them all
        cnt_ = [int(re.match(r"(\d+) nails", l.why).group(1)) for l in hn_]
        part_ = lambda l: re.sub(r"\) · [\d,]+ supplied$", ")", re.sub(r"^\d+ nails\s+", "", l.why)).strip("()")
        bx_ = max(1, int(math.ceil(sum(cnt_) / dn_.get("count", 1000))))
        why_ = (f"{sum(cnt_)} nails  (" + " · ".join(f"{(l.item.split(' — ', 1)[1].lower() if ' — ' in l.item else 'roof cover' if l.category == 'Porch cover' else 'deck')} {c_}: {part_(l)}" for l, c_ in zip(hn_, cnt_))
                + f") · {bx_ * dn_.get('count', 1000):,} supplied")
        hn_[0].item, hn_[0].net, hn_[0].order, hn_[0].why = dn_["desc"], bx_, bx_, why_
        sp_ = {}
        for l, c_ in zip(hn_, cnt_):
            sp_[l.category] = sp_.get(l.category, 0) + c_
        if len(sp_) > 1:                     # one box, two jobs: the price breakdown splits its cost by the nails each part drives
            hn_[0].split = {k_: v_ / sum(cnt_) for k_, v_ in sp_.items()}
        for l in hn_[1:]:
            lines.remove(l)

    # ================= FASTENERS
    fsys = spec.decking.fastener_system or default_fastener_system(coll, spec.decking.profile)
    fas_face = 0 if spec.extras.hardie_skirt else Qz.fascia_screws        # a HardieTrim skirt takes its own trim screws (the Fascia lines), not deck screws
    rim16_ = lambda st: st.stringers or int(math.ceil(st.width / 16.0)) + 1      # a riser's fastening points: every stringer, or a box step's front rim every 16"
    stair_face = sum((st.tread_pieces * (st.stringers or getattr(st, "cross_members", 0) or int(math.ceil(st.width / 16.0)) + 1)
                      + (0 if spec.extras.hardie_skirt else st.riser_pieces * rim16_(st))) * 2 for st in stairs)   # treads: 2 per stringer / box cross member; HardieTrim risers: on the Hardie nails (FASCIA)
    cx_b = (spec.decking.border_fastener or "") == "Cortex"                # picture frame, dividers and stair treads on Cortex plugs
    tt_clip_ = fsys == "CONCEALoc" and dkf["material"] == "Composite" and brand == "TimberTech"
    if tt_clip_:                     # TimberTech's clip field: the first field row against each front border and the last row at the house
        Qz.first_row = clip_field_edge_screws(L, getattr(Qz, "outline_joists", None), fr0.spacing)       # (and the bay), 1 per joist
    face = {"first row": Qz.first_row, "border": Qz.border_screws, "fascia": fas_face, "stairs": stair_face}    # face screws not yet ordered: each fastener below takes its part, Cap-Tor the rest
    if fsys == "Camo EdgeClip":
        d = PRICEBOOK["decking"]["Camo_EdgeClip_90"]
        boxes = int(math.ceil(Qz.clips / d["count"]))
        lines.append(Line("Fasteners", "Camo EdgeClip 3/16\" 410SS Black 90 ct", boxes, boxes, "box", f"{Qz.clips} clips needed · {boxes * d['count']} supplied", d["each"], d["source"]))
        sched["Field"] = f"100% hidden — Camo EdgeClip 3/16\" at every joist in every gap ({Qz.bearing_points} bearing points x {Qz.gaps} gaps = {Qz.clips}); board ends clipped on the PF joists, never screwed"
    elif fsys == "CONCEALoc":
        d = PRICEBOOK["decking"]["CONCEALoc_100SF"]           # D&D sells the 100 SF box (CLOCFAST: 175 clips + screws), no 500 count
        boxes = int(math.ceil(Qz.clips / d["count"]))
        lines.append(Line("Fasteners", d["desc"], boxes, boxes, "box", f"{Qz.clips} clips needed · {boxes * d['count']:,} supplied ({boxes} box{'es' if boxes != 1 else ''} of {d['count']})", d["each"], d["source"], d.get("sku", "")))
        sched["Field"] = f"CONCEALoc at every joist in every gap ({Qz.clips})"
    elif fsys == "Cortex":
        rip_screws = sum(2 * (int(round(r / fr0.spacing)) + 2) for r in [0]) if not Qz.rip_strips else int(len(Qz.rip_strips) * 2 * (Qz.bearing_points / max(1, len(Qz.field_piece_note))))
        n = Qz.clips + rip_screws + stair_face          # stair treads and risers are Cortex face-screwed too, in the field color
        d, cxn_, kit_ = _cortex(coll, color, field=True)    # a composite field: the 300 SF composite kit, not the Advanced PVC 350 ct
        boxes = int(math.ceil(n / d["count"]))
        lines.append(Line("Fasteners", f"{cxn_} ({kit_})", boxes, boxes, "box",
                          f"{n} screws  (2 per board at every bearing point" + (", rips included" if Qz.rip_strips else "")
                          + (f", stair treads{'' if spec.extras.hardie_skirt else ' + risers'} {stair_face}" if stair_face else "")
                          + f") · {boxes * d['count']} supplied", d["each"], d["source"], _sku(d, color)))
        if bcolor != color or Qz.border_screws:
            nb = Qz.border_screws
            d, cxn_, kit_ = _cortex(bcoll, bcolor)
            bboxes = max(1, int(math.ceil(nb / d["count"])))
            lines.append(Line("Fasteners", f"{cxn_} — borders + dividers", bboxes, bboxes, "box", f"{nb} screws", d["each"], d["source"], _sku(d, bcolor)))
        sched["Field"] = f"Cortex face screws with color-matched plugs: 2 per board at every joist and at both ends of every run, color-matched plugs ({n} field + {Qz.border_screws} border/divider)"
        face.update({"first row": 0, "border": 0, "stairs": 0})          # the fascia still takes its own screws (below)
    else:
        takes_ = [k_ for k_ in face if not (cx_b and k_ in ("border", "stairs"))]    # all but what a Cortex border takes (below)
        n = Qz.clips + sum(face[k_] for k_ in takes_)
        d = PRICEBOOK["decking"]["CapTor_xd_350"]
        boxes = int(math.ceil(n / d["count"]))
        lines.append(Line("Fasteners", f"Starborn Cap-Tor xd 2-3/4\" Epoxy {color} 350 ct — face screwed field", boxes, boxes, "box", f"{n} needed", d["each"], d["source"]))
        sched["Field"] = "face screwed, 2 per board at every joist"
        face.update(dict.fromkeys(takes_, 0))
    if cx_b and fsys != "Cortex" and (face["border"] or face["stairs"]):
        d, cxn_, kit_ = _cortex(bcoll, bcolor)          # Terrain+ Dark Oak: CTC100LFDO, the composite 100 LF kit
        nb = face["border"] + face["stairs"]
        bboxes = max(1, int(math.ceil(nb / d["count"])))
        lines.append(Line("Fasteners", f"{cxn_} — picture frame, dividers" + (" and stair treads" if face["stairs"] else ""), bboxes, bboxes, "box",
                          f"{nb} screws  (border/divider {face['border']}" + (f" · stairs {face['stairs']}" if face["stairs"] else "")
                          + f") · {bboxes * d['count']} supplied ({bboxes} x {kit_})", d["each"], d["source"], _sku(d, bcolor)))
        sched["Picture frame + stairs" if face["stairs"] else "Picture frame"] = ("Cortex face screws with color-matched plugs: borders and dividers 2 per bearing point"
                                                                                 + (", stair treads 2 per stringer per board" if face["stairs"] else ""))
        face.update({"border": 0, "stairs": 0})
    if dkf["material"] == "PVC" and face["fascia"] and "TOPLoc_PVC_fascia_100" in PRICEBOOK["decking"]:
        # Advanced PVC fascia takes TimberTech TOPLoc fascia screws (color-matched heads), not deck screws — none under a HardieTrim skirt (fas_face 0)
        d = PRICEBOOK["decking"]["TOPLoc_PVC_fascia_100"]
        packs = max(1, int(math.ceil(face["fascia"] / d["count"])))
        lines.append(Line("Fasteners", f"TimberTech TOPLoc fascia screws for Advanced PVC fascia, {spec.decking.fascia_color or color} (100 ct, 30 LF)", packs, packs, "pack",
                          f"{face['fascia']} screws · {packs * d['count']} supplied", d["each"], d["source"]))
        sched["Fascia"] = "TOPLoc fascia screws, color-matched: 2 at each board end, then alternate top / bottom every 12\" into the rim, pre-drilled"
        face["fascia"] = 0
    tot = sum(face.values())                        # Cap-Tor takes what is left: the total is the sum of the parts it lists, the schedule names the same parts
    if tot:
        d = PRICEBOOK["decking"]["CapTor_xd_350"]
        boxes = max(1, int(math.ceil(tot / d["count"])))
        lines.append(Line("Fasteners", f"Starborn Cap-Tor xd 2-3/4\" Epoxy {color} 350 ct", boxes, boxes, "box",
                          f"{tot} screws needed  (" + " · ".join(f"{k_} {v_}" for k_, v_ in face.items() if v_) + ")", d["each"], d["source"]))
        rule_ = {"first row": (("first row 1 per joist at each front border and the last row at the house" + (" and the bay" if spec.geometry.bay_ledger else ""))
                               if tt_clip_ else "first row 1 per joist on the house edge"),
                 "border": f"borders 2 per bearing point @ {(fr0.spacing if (L.plan is not None or L.multi) else 16):g}\"",
                 "fascia": "fascia 2 at each board end then alternate top/bottom every 12\", pre-drilled", "stairs": "stair treads 2 per stringer per board"}
        sched["Face screws"] = "Cap-Tor xd color-matched ONLY at: " + " · ".join(rule_[k_] for k_, v_ in face.items() if v_)

    # ================= RAIL
    if rl:
        sysn = rl.system
        sysd = rail_system_for(spec.railing)
        cable = sysd.get("cable", False)
        pk = Counter(p.kind for p in rl.posts)
        rbrand = sysd.get("brand", brand)         # rail lines carry the rail maker (Cinch), not the decking brand
        rname = sysn if rbrand == sysn else f"{rbrand} {sysn}"
        if cable:
            kits = Counter(8 if s_.ctc <= 96.01 else 8 for s_ in rl.sections)
            for kft, n in sorted(kits.items()):
                d_, uc, src = _item("rail", f"{sysn}|kit|{kft}")
                lines.append(Line("Rail", d_, n, n, "kit", f"exact  ({n} bays, " + " / ".join(sorted(set(ftin(s_.ctc) for s_ in rl.sections))) + " CTC)", uc, src))
            d_, uc, src = _item("rail", f"{sysn}|post_kit")
            lines.append(Line("Rail", d_, len(rl.posts), len(rl.posts), "kit", f"exact  ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))})", uc, src))
        else:
            sec_count = defaultdict(int)
            for s_ in rl.sections:
                sec_count[(s_.panel_stock_in, s_.kind)] += 1
            for (stock_in, kind), n in sorted(sec_count.items()):
                cuts_txt = sorted(set(ftin(s_.cut_len) for s_ in rl.sections if s_.panel_stock_in == stock_in and s_.kind == kind))
                key = f"{sysn}|panel|{stock_in // 12}|{kind}"
                d_, uc, src = _item("rail", key, f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" {kind} panel {rl.color}")
                d_ = d_.replace("{color}", rl.color).replace("{h}", f"{rl.height:g}")
                lines.append(Line("Rail", d_ if "Fulton Rail 8'" in d_ or "panel" in d_.lower() or " kit" in d_.lower() else f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" {kind} panel {rl.color}", n, n, "ea",
                                  f"exact  (cut to {' / '.join(cuts_txt)})", uc, _h_src(PRICEBOOK["rail"].get(key), src, rl.height), _sku(PRICEBOOK["rail"].get(key), rl.color, rl.height)))
                if f"{sysn}|top_rail|{stock_in // 12}" in PRICEBOOK["rail"] and kind == "level":
                    if spec.railing.drink_rail and f"{sysn}|panel_cover|{stock_in // 12}" in PRICEBOOK["rail"]:
                        # under a drink rail the top rail is replaced by the universal panel cover the drink-rail clips grip (TimberTech guide)
                        d_, uc, src = _item("rail", f"{sysn}|panel_cover|{stock_in // 12}")
                        lines.append(Line("Rail", d_.replace("{color}", rl.color), n, n, "ea", "exact  (one per bay — replaces the top rail under the drink rail)", uc, src,
                                          _sku(PRICEBOOK["rail"][f"{sysn}|panel_cover|{stock_in // 12}"], rl.color)))
                    else:
                        # a top rail sold apart from the infill kit (Impression Rail Express: Modern / Classic profile)
                        d_, uc, src = _item("rail", f"{sysn}|top_rail|{stock_in // 12}")
                        lines.append(Line("Rail", d_.replace("{color}", rl.color), n, n, "ea", "exact  (one per bay, cut with its panel)", uc, src, _sku(PRICEBOOK["rail"][f"{sysn}|top_rail|{stock_in // 12}"], rl.color)))
            if (timber or sysd.get("surface")) and f"{sysn}|post_kit" in PRICEBOOK["rail"]:
                pkk_ = _post_key(sysn, f"{sysn}|post_kit", rl.height)      # a 42" IRX rail: the 43" post kit
                d_, uc, src = _item("rail", pkk_)
                d_ = d_.replace("{color}", rl.color)
                n_sail = sum(len(sl.get("posts", [])) for sl in (spec.geometry.sails or []) if sl.get("mount") == "deck_rail")
                n_rp = len(rl.posts) - n_sail
                lines.append(Line("Rail", d_, n_rp, n_rp, "kit", f"exact  ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))}" + (f"; {n_sail} corner{' is the sail post' if n_sail == 1 else 's are the sail posts'}" if n_sail else "") + ")", uc, src,
                                  _sku(PRICEBOOK["rail"][pkk_], rl.color)))
                if f"{sysn}|bracket_22" in PRICEBOOK["rail"]:
                    # a post on a 45-degree turn sits at 22.5° to both panels: one Level 22.5° Angle Bracket Pack per post (TimberTech IRX guide)
                    n45 = 0
                    for p_ in rl.posts:
                        if p_.kind != "CORNER" or getattr(p_, "roof", False):
                            continue
                        dv_ = [(q_[0] - p_.x, q_[1] - p_.y) for s_ in rl.sections for e_, q_ in ((s_.p0, s_.p1), (s_.p1, s_.p0))
                               if e_ and q_ and math.hypot(e_[0] - p_.x, e_[1] - p_.y) < 0.6]
                        if len(dv_) == 2:
                            c_ = (dv_[0][0] * dv_[1][0] + dv_[0][1] * dv_[1][1]) / ((math.hypot(*dv_[0]) * math.hypot(*dv_[1])) or 1.0)
                            n45 += 125.0 <= math.degrees(math.acos(max(-1.0, min(1.0, c_)))) <= 145.0      # 135° between the two panels
                    if n45:
                        d_, uc, src = _item("rail", f"{sysn}|bracket_22")
                        lines.append(Line("Rail", d_, n45, n45, "pk", f"exact  ({n45} post{'s' if n45 != 1 else ''} on a 45° turn, one pack each)", uc, src, _sku(PRICEBOOK["rail"][f"{sysn}|bracket_22"], rl.color)))
            else:
                n_sail = sum(len(sl.get("posts", [])) for sl in (spec.geometry.sails or []) if sl.get("mount") == "deck_rail")
                for kind, n in sorted(pk.items()):
                    why = "exact"
                    if kind == "CORNER" and n_sail:
                        n, why = max(0, n - n_sail), f"exact  ({n_sail} corner{' is the sail post' if n_sail == 1 else 's are the sail posts'})"
                    if not n:
                        continue
                    pkk_ = _post_key(sysn, f"{sysn}|post|{kind}", rl.height)
                    uc, src = _price("rail", pkk_)
                    lines.append(Line("Rail", f"{rname} {sysd['post_w']:g}\" {kind} post {rl.height:g}\" {rl.color} w/ brackets, cap, skirt", n, n, "ea", why, uc, src, _sku(PRICEBOOK["rail"].get(pkk_), rl.color)))
        if spec.railing.drink_rail:
            dcoll = spec.railing.drink_rail_collection or bcoll
            dcolor = spec.railing.drink_rail_color or bcolor
            # board pieces per rail run (mitered at every turn), packed into 16' boards
            pieces = []
            for run_name, run_lf in Counter({s_.side: 0 for s_ in rl.sections}).items():
                pass
            runs = defaultdict(float)
            for s_ in rl.sections:
                runs[s_.side] += s_.ctc
            for name, Lr in runs.items():
                rem = Lr + 6
                while rem > 192:
                    pieces.append((f"drink rail {name}", 192.0)); rem -= 192
                pieces.append((f"drink rail {name}", rem))
            between_ = (spec.railing.drink_rail_mount or "between") != "over" and f"{sysn}|panel_cover|8" in PRICEBOOK["rail"]
            if between_:                                # between the posts (each keeps its cap): a board per bay, post face to post face, never mitered
                pieces = [(f"drink rail {s_.side}", round(s_.ctc - sysd["post_w"], 2)) for s_ in rl.sections]
            packed_d = pack_boards(pieces, stocks=(16,))
            nb = sum(len(v) for v in packed_d.values())
            uc, src = _price("decking", f"{spec.decking.brand}|{dcoll}|16|square")
            if uc == 0.0:                               # no 16' square-edge price on file for the line: its per-LF price x 16'
                lf, src = _price("decking", f"{spec.decking.brand}|{dcoll}|per_lf"); uc = round(lf * 16, 2)
            on_ = ("on the drink-rail clips over the universal panel covers" if f"{sysn}|panel_cover|8" in PRICEBOOK["rail"] else "laid flat on the top rail")
            sku_d = _sku(PRICEBOOK["decking"].get(f"{spec.decking.brand}|{dcoll}|16|square"), dcolor)
            if between_:                                # the owner's 1 spare: an extra board unless an offcut already holds the longest piece
                off_d = _offcut_spare(packed_d, max([l for _, l in pieces] or [0.0]))
                lines.append(Line("Rail", f"Drink rail — {spec.decking.brand} {dcoll} {dcolor} 1x6x16 Square Edge {on_}, between the posts, {rl.rail_lf} LF", nb, nb + (0 if off_d else 1), "ea",
                                  ("exact  (" if off_d else "+1  (") + f"{len(pieces)} piece{'s' if len(pieces) != 1 else ''} post face to post face: c-c less the {sysd['post_w']:g}\" post, board corners trimmed "
                                  f"at each post, no miters; {nb} board{'s' if nb != 1 else ''}" + (f", the spare is a {ftin(off_d)} offcut" if off_d else "") + "; full-board line only, never scalloped)", uc, src, sku_d))
            else:
                lines.append(Line("Rail", f"Drink rail — {spec.decking.brand} {dcoll} {dcolor} 1x6x16 Square Edge {on_}, {rl.rail_lf} LF, mitered at every turn", nb, nb + 1, "ea", "+1  (full-board line only, never scalloped)", uc, src, sku_d))
            if (spec.railing.drink_rail_mount or "between") == "over" and f"{sysn}|post_insert_8" in PRICEBOOK["rail"]:
                # over the posts: posts cut level within 1/4" of the panel-cover tops, an insert in each, the board's seams on post centers
                n_ins = len(rl.posts)
                pk_ = int(math.ceil(n_ins / 8))
                d_, uc, src = _item("rail", f"{sysn}|post_insert_8")
                lines.append(Line("Rail", d_, pk_, pk_, "pk", f"{n_ins} posts  (drink rail over the posts: posts cut level, (3) 2-1/2\" screws each side of every board joint into the insert)", uc, src))
            kkey = f"{sysn.lower()}_drink_rail_bracket_kit" if f"{sysn.lower()}_drink_rail_bracket_kit" in PRICEBOOK["hardware"] else "drink_rail_bracket_kit"
            d_, uc, src = _item("hardware", kkey)
            d_ = d_.replace("{color}", rl.color)
            kc = PRICEBOOK["hardware"][kkey].get("clips")
            if kc:      # a clip kit (IRX: 12 clips) — 6 clips on an 8' bay, 4 on a 6'
                clips = sum(6 if s_.panel_stock_in >= 96 else 4 for s_ in rl.sections)
                nk = int(math.ceil(clips / kc))
                lines.append(Line("Rail", d_, nk, nk, "kit", f"{clips} clips  (6 per 8' bay, 4 per 6') · {nk * kc} supplied", uc, src, _sku(PRICEBOOK["hardware"][kkey], rl.color)))
            else:
                lines.append(Line("Rail", d_, len(rl.sections), len(rl.sections), "kit", "exact  (one per bay)", uc, src))
        for st in stairs:
            sc = Counter(s_.panel_stock_in for s_ in st.stair_sections)
            for stock_in, n in sorted(sc.items()):
                if cable:
                    uc, src = _price("rail", f"{sysn}|stair_kit|{stock_in // 12}")
                    lines.append(Line("Stairs", f"{rname} stair cable rail kit {stock_in // 12}' ({st.side} stair)", n, n, "kit", "exact", uc, src))
                else:
                    uc, src = _price("rail", f"{sysn}|panel|{stock_in // 12}|stair")
                    lines.append(Line("Stairs", f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" STAIR panel {rl.color} ({st.side} stair)", n, n, "ea", "exact", uc,
                                      _h_src(PRICEBOOK["rail"].get(f"{sysn}|panel|{stock_in // 12}|stair"), src, rl.height),
                                      _sku(PRICEBOOK["rail"].get(f"{sysn}|panel|{stock_in // 12}|stair"), rl.color, rl.height)))
                    if f"{sysn}|top_rail|{stock_in // 12}" in PRICEBOOK["rail"]:      # the stair panel ships without its top rail too
                        d_, uc, src = _item("rail", f"{sysn}|top_rail|{stock_in // 12}")
                        lines.append(Line("Stairs", d_.replace("{color}", rl.color) + f" — stair rail ({st.side} stair)", n, n, "ea", "exact  (one per stair panel, cut on the rake)", uc, src,
                                          _sku(PRICEBOOK["rail"][f"{sysn}|top_rail|{stock_in // 12}"], rl.color)))
            if st.stair_posts:
                skk_ = _post_key(sysn, f"{sysn}|post|STAIR", rl.height)       # a 42" IRX stair: the 48" post sleeve
                uc, src = _price("rail", skk_)
                lines.append(Line("Stairs", f"{rname} {sysd['post_w']:g}\" STAIR post {rl.color} w/ brackets, cap ({st.side} stair)", st.stair_posts, st.stair_posts, "ea",
                                  "exact  (top + bottom of each rail side" + (f", {len(st.geo.flights)} flights" if len(st.geo.flights) > 1 else "") + ")", uc, src,
                                  _sku(PRICEBOOK["rail"].get(skk_), rl.color)))
            if st.landing_sections:
                lc = Counter(s_.panel_stock_in for s_ in st.landing_sections)
                for stock_in, n in sorted(lc.items()):
                    if cable:
                        uc, src = _price("rail", f"{sysn}|kit|{stock_in // 12}")
                        lines.append(Line("Stairs", f"{rname} level cable rail kit {stock_in // 12}' — landing guard ({st.side} stair, {st.landing_rail_lf:g} LF)", n, n, "kit", "exact", uc, src))
                    else:
                        uc, src = _price("rail", f"{sysn}|panel|{stock_in // 12}|level")
                        lines.append(Line("Stairs", f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" LEVEL panel {rl.color} — landing guard ({st.side} stair, {st.landing_rail_lf:g} LF)", n, n, "ea", "exact  (open sides of the landings)", uc,
                                          _h_src(PRICEBOOK["rail"].get(f"{sysn}|panel|{stock_in // 12}|level"), src, rl.height),
                                          _sku(PRICEBOOK["rail"].get(f"{sysn}|panel|{stock_in // 12}|level"), rl.color, rl.height)))
                pkey_ = _post_key(sysn, f"{sysn}|post|{'CORNER' if 'CORNER' in RAIL_SYSTEMS.get(sysn, {}).get('post_types', []) else 'POST'}", rl.height)
                uc, src = _price("rail", pkey_)
                lines.append(Line("Stairs", f"{rname} {sysd['post_w']:g}\" post {rl.color} w/ brackets, cap — landing guard ({st.side} stair)", st.landing_posts, st.landing_posts, "ea", "exact  (bay ends + turn corners)", uc, src,
                                  _sku(PRICEBOOK["rail"].get(pkey_), rl.color)))
            hr_ = getattr(st, "handrail", "")
            if st.geo.handrail_required and (st.stair_rail_sides or hr_):
                uc, src = _price("rail", f"{sysn}|handrail_kit")
                if not hr_:
                    lines.append(Line("Stairs", f"{sysn} graspable handrail kit ({st.side} stair)", 1, 1, "ea", "exact  (4+ risers — IRC R311.7.8)", uc, src))
                else:     # "each flight": one along every railed flight; "guard posts": an inset stair's, bracketed to the guard posts along a cheek
                    n_hr = max(1, sum(1 for r_ in st.flight_rails if r_)) if hr_ == "each flight" else 1
                    d_hr = PRICEBOOK["rail"].get(f"{sysn}|handrail_kit", {}).get("desc")
                    item = (d_hr.replace("{color}", rl.color) if d_hr else f"{sysn} graspable handrail kit")
                    lines.append(Line("Stairs", item + f" ({st.side} stair" + (", one per flight" if hr_ == "each flight" else f", on the guard posts along the {st.handrail_side}-hand cheek") + ")",
                                      n_hr, n_hr, "ea", f"exact  (4+ risers — IRC R311.7.8; {st.handrail_lf:g}' of rail, 34–38\" over the nosings)", uc, src,
                                      _sku(PRICEBOOK["rail"].get(f"{sysn}|handrail_kit"), rl.color)))
                    # a flight's rail longer than the kit's 94" pipe takes an extension kit (pipe + splice) per extra length
                    runs_ = ([math.hypot(fg.run_in, fg.rise_in - st.geo.riser_in) for fg, r_ in zip(st.geo.flights, st.flight_rails) if r_]
                             if hr_ == "each flight" else [st.handrail_lf * 12.0])
                    n_ext = sum(max(0, int(math.ceil(r_in / 94.0 - 1e-6)) - 1) for r_in in runs_)
                    if n_ext and sysn.startswith("IRX"):
                        d_x, uc_x, src_x = _item("rail", f"{sysn}|handrail_ext", f"TimberTech Impression aluminum ADA pipe rail extension kit, {rl.color}")
                        lines.append(Line("Stairs", f"{d_x.replace('{color}', rl.color)} ({st.side} stair)", n_ext, n_ext, "ea",
                                          "exact  (" + " · ".join(f"{r_in / 12:.1f}'" for r_in in runs_) + " of rail per flight, 94\" pipe per kit)",
                                          uc_x or 193.48, src_x if uc_x else "D&D quote 979610 — AZTIXADAPREKB (pricebook IRX Baluster|handrail_kit note)"))
        if spec.railing.post_size_in and rl:
            ps = spec.railing.post_size_in
            for l in lines:
                if l.category in ("Rail", "Stairs") and " post " in l.item and '2"' in l.item:
                    l.item = l.item.replace('2"', f'{ps:g}"')
                    l.note = (l.note + " · " if l.note else "") + f"{ps:g}\" post — confirm the SKU and price with {sysn} (priced at the stock post rate)"
        if f"{sysn}|accessory_kit" in PRICEBOOK["rail"]:      # the maker's touch-up + bracket jig kit (IRX AZTIXACCKITB)
            d_, uc, src = _item("rail", f"{sysn}|accessory_kit")
            lines.append(Line("Rail", d_.replace("{color}", rl.color), 1, 1, "ea", "exact  (cut ends, bracket jig)", uc, src, _sku(PRICEBOOK["rail"][f"{sysn}|accessory_kit"], rl.color)))
        elif not timber:
            uc, src = _price("rail", "touchup_paint")
            tu = "Rust-Oleum flat black touch-up (cut ends)" if "black" in (rl.color or "black").lower() else f"{rbrand} {rl.color} touch-up paint (cut ends)"
            lines.append(Line("Rail", tu, 1, 1, "ea", "exact", uc, src))
        n_sail_ = sum(len(sl.get("posts", [])) for sl in (spec.geometry.sails or []) if sl.get("mount") == "deck_rail")
        sched["Rail"] = (f"{sysn} {rl.height:g}\" — {len(rl.posts)} posts ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))})"
                         + (f"; the {n_sail_} front corners are the shade-sail posts, base-plated on the deck — the panels bracket to them" if n_sail_ else "")
                         + (f", {len(rl.sections)} bays at " + " / ".join(sorted(set(ftin(s_.ctc) for s_ in rl.sections))) + " CTC (8' kits cut to bay), posts on the divider lines, no bottom rail; HeadLOK 6\" x 4 per post" if cable
                            else " surface-mounted on the decking over " + ("a 2x6 blocking and a 2x6 cross block at every post (TimberTech IRX install guide Dia. #3A/#3B), "
                                                                             if irx_blk_ else "a 2x blocking pair between the rim plies and the PF joist at every post, ") + (
                                "(4) 3/8\" x 6\" HDG lag screws with washers per post through the base (TimberTech IRX guide)"
                                + ("; a 22.5° Level Angle Bracket Pack at every post on a 45° turn" if any(l.category == "Rail" and "22.5° Angle Bracket" in l.item for l in lines) else "")
                                if sysd.get("post_lag") and not timber else "(4) HeadLOK 6\" per post through the base") if sysd.get("surface")
                            else " inside the outer rim ply, inner ply pocketed 2\" wide, (2) 7/16\" x 4-1/2\" bolts per post")
                         + (((f"; drink rail board over the posts on the {rbrand} drink-rail clips" + (" and post inserts (posts cut level)" if f"{sysn}|post_insert_8" in PRICEBOOK["rail"] else "")
                              + ", seams on post centers, mitered at every turn") if (spec.railing.drink_rail_mount or "between") == "over"
                             else f"; drink rail board between the posts on the {rbrand} drink-rail clips over the universal panel covers, post face to post face, its corners trimmed at each post (no miters)"
                             if f"{sysn}|panel_cover|8" in PRICEBOOK["rail"] else f"; drink rail board on {rbrand} drink-rail brackets, mitered at every turn") if spec.railing.drink_rail else ""))
        for n in rl.notes:
            notes.append(n)

    # ================= FINISH (timber)
    if timber:
        if spec.framing.end_grain_seal:
            gal = max(1, int(math.ceil(Qz.timber_ends / 500)))
            d_, uc, src = _item("hardware", "end_grain_sealer_gal")
            lines.append(Line("Finish", d_, gal, gal, "gal", f"{Qz.timber_ends} cut ends — base: timbers unfinished, cuts sealed", uc, src))
        if spec.framing.finish == "oil":
            gal = int(math.ceil(timber_sf * 2 / 250 / 5) * 5)
            d_, uc, src = _item("hardware", "timber_oil_gal")
            lines.append(Line("Finish", d_ + f" — 2 coats on ~{timber_sf:,.0f} SF of timber (posts, beams, every 4x10 face that shows)", gal, gal, "gal", f"exact  ({gal // 5} x 5-gal)", uc, src))
            d_, uc, src = _item("hardware", "oil_sundries_lot")
            lines.append(Line("Finish", d_, 1, 1, "lot", "exact", uc, src))
        else:
            notes.append("timbers unfinished — weather to gray; dark walnut oil is an option")

    # ================= SHADE SAILS
    for sl in spec.geometry.sails or []:
        P = [tuple(float(v) for v in c) for c in sl["corners"]]
        nm = sl.get("name", "Shade sail")
        # fabric area: the corner polygon pulled in 6% for the hardware (plan area x the slope)
        cx = sum(p[0] for p in P) / len(P); cy = sum(p[1] for p in P) / len(P)
        Qs = [(p[0] + (cx - p[0]) * 0.06, p[1] + (cy - p[1]) * 0.06) for p in P]
        a_plan = abs(sum(Qs[i][0] * Qs[(i + 1) % len(Qs)][1] - Qs[(i + 1) % len(Qs)][0] * Qs[i][1] for i in range(len(Qs)))) / 2
        dz = max(p[2] for p in P) - min(p[2] for p in P)
        span = max(math.dist(P[i][:2], P[j][:2]) for i in range(len(P)) for j in range(len(P)))
        area = round(a_plan * math.sqrt(1 + (dz / max(span, 1)) ** 2))
        color = sl.get("color", "to be selected")
        if sl.get("fabric_by_owner"):
            lines.append(Line("Shade sail", f"{nm} — {'triangle' if len(P) == 3 else f'{len(P)}-corner'} shade sail, ~{area} SF, {color} — SUPPLIED BY THE OWNER (GSX hangs and tensions it)",
                              1, 1, "ea", "owner-supplied — not ordered", 0.0, "by owner"))
        else:
            lines.append(Line("Shade sail", f"{nm} — custom commercial-grade HDPE shade sail, {'triangle, 3 corners' if len(P) == 3 else f'{len(P)} corners, hypar twist'}, {color}, stainless D-rings, sewn-in perimeter cable",
                              area, area, "SF", "made to the measured attachment points, ~6% under for tensioning", float(sl.get("fabric_price_sf", 14.0)), "EST — sail fabricator to quote"))
        posts = [P[k] for k in sl.get("posts", [])]
        if posts and sl.get("posts_cost_total") is not None:      # owner-set: the posts bought as one lot, nothing else for the sail
            lines.append(Line("Shade sail", f"Sail posts ({len(posts)}) — {sl.get('post_in', 4)}\" steel, {spec.railing.color if spec.railing.system != 'none' else 'black'}, "
                              + ("on base plates on top of the deck, the rail corner posts at the front corners" if sl.get("mount") == "deck_rail" else "on footings"), 1, 1, "lot", "owner's price", float(sl["posts_cost_total"]), "owner"))
            if sl.get("mount") == "deck_rail":
                lines.append(Line("Shade sail", f"{jsize}x8 #1 True Frame — solid blocking under each sail post base plate (rim to PF joist, doubled)", 1, 1, "ea", f"{2 * len(posts)} blocks", _lumber_price(jsize, 8)[0], "GS sheet"))
                lines.append(Line("Shade sail", "1/2\" x 8\" HDG through-bolt + nut + washers — base plates through the decking into the blocking", 4 * len(posts), 4 * len(posts) + 2, "ea", "+2  (4 per post)", 4.2, "est."))
            continue
        if posts and sl.get("mount") == "deck_rail":
            sq = sl.get("post_in", 4); color = spec.railing.color if spec.railing.system != "none" else "black"
            for k, p in enumerate(posts):
                above = p[2] + 0.6 - spec.geometry.height_in / 12
                ln = int(math.ceil(above + 0.5))
                lines.append(Line("Shade sail", f"Steel sail post {sq}\" x {sq}\" x 1/4\" HSS, galvanized + powder coat {color}, pad eye welded at the top, rail-bracket tabs — {ln}' "
                                  f"({ftin(above * 12)} above the deck), 3/8\" base plate", 1, 1, "ea", f"post {k + 1}: the rail corner post at this corner", round(ln * float(sl.get("post_price_lf", 42.0)) + 120.0, 2), "EST — steel fabricator to quote"))
            nb = 3 * len(posts)
            lines.append(Line("Shade sail", "1/2\" x 8\" HDG through-bolt + nut + washers — sail post base plates through the decking into solid blocking", 4 * len(posts), 4 * len(posts) + 2, "ea", "+2  (4 per post)", 4.2, "est."))
            Qz_sail_blocks = 2 * len(posts)
            lines.append(Line("Shade sail", f"{jsize}x8 #1 True Frame — solid blocking behind each sail post (rim to PF joist and the next joist)", 1, 1, "ea", f"{Qz_sail_blocks} blocks", _lumber_price(jsize, 8)[0], "GS sheet"))
        elif posts:
            emb = float(sl.get("post_embed_ft", 7.0)); od = sl.get("post_od_in", 6.625)
            for k, p in enumerate(posts):
                ln = int(math.ceil(p[2] + 0.6 + emb))
                lines.append(Line("Shade sail", f"Steel sail post {od}\" OD sch 40, hot-dip galvanized + powder coat, pad eye welded at the top — {ln}' ({ftin((p[2] + 0.6) * 12)} above grade + {emb:g}' embed)",
                                  1, 1, "ea", f"post {k + 1}, raked 5° away from the sail", round(ln * float(sl.get("post_price_lf", 38.0)), 2), "EST — steel supplier to quote"))
            fd = float(sl.get("footing_dia_in", 24)) / 12
            cy_ = len(posts) * math.pi * (fd / 2) ** 2 * (emb + 0.5) / 27
            lines.append(Line("Shade sail", f"Concrete 4,000 psi — sail post footings {int(fd * 12)}\" dia x {emb + 0.5:g}' (short-load ready-mix)", round(cy_, 2), math.ceil(cy_ * 2) / 2, "CY",
                              f"{len(posts)} footings, engineer to size for the sail wind load", 260.0, "EST"))
        n_house = len(P) - len(posts)
        lines.append(Line("Shade sail", f"Sail hardware: {len(P)} stainless turnbuckles (jaw-jaw), D-shackles, snap hooks" + (f", {n_house} house anchor plates with through-bolts / structural screws into the framing" if n_house else ""),
                          1, 1, "kit", "316 stainless, marine grade", 85.0 * len(P) + 120.0 * n_house, "EST"))
    # ================= SITE
    if spec.extras.under_deck_gravel:
        sf_g = L.deck_sf * 1.1
        rolls = int(math.ceil(sf_g / 1000))
        lines.append(Line("Flashing & waterproofing", "6-mil poly sheeting 10' x 100' — under the decks", rolls, rolls, "roll", f"{sf_g:.0f} SF with laps", 45.0, "est."))
        cy = sf_g * (2.0 / 12) / 27
        lines.append(Line("Flashing & waterproofing", "3/4\" washed gravel, 2\" over the poly — under the decks (delivered)", round(cy, 1), max(1.0, math.ceil(cy * 2) / 2), "CY", f"{sf_g:.0f} SF x 2\"", 85.0, "est."))
    lines += site_lines(spec, L.deck_sf)

    # ================= summary
    zones_txt = [f"{z.name} {z.label}: {ftin(z.W)} x {ftin(z.D)}" + (f", wall set back {ftin(-z.wall_y)}" if z.wall_y < 0 else "") + (" · hot tub" if z.hot_tub else "") for z in L.zones]
    summary = dict(
        job=spec.job, client=spec.client, address=spec.site.address,
        zones=zones_txt if L.multi else [],
        finished_frame=(f"{len(L.zones)} zones, {ftin(W)} along the house, {ftin(D)} at the deepest" if L.multi else f"{ftin(W)} x {ftin(D)} outside to outside"),
        finished_deck=(f"{L.outer_edge_lf} LF of outer edge" if L.multi else f"{ftin(dk0.deck_w)} x {ftin(dk0.deck_d)} over fascia"),
        deck_sf=L.deck_sf, height=ftin(spec.geometry.height_in),
        joists=f"{Qz.n_joists} {jsize} {SPECIES_NAMES['DF#1'] if timber else SPECIES_NAMES.get(jsp, jsp)} @ {fr0.spacing:g}\" OC" + ("" if L.multi else f" x {ftin(fr0.joist_len)}") + (f" — {joist_lf:,.0f} LF incl. rims, ledgers, blocking" if timber else ""),
        rims=(f"{fr0.rim_plies}-ply {jsize} sides; front rim = flush beam" if Qz.front_flush else (f"single {jsize} rims" if timber else f"{fr0.rim_plies}-ply {jsize} front and sides")) + ("" if fr0.ledger else " and rear (freestanding)"),
        beams=[f"{bl.label}: {ftin(bl.length)}, {bl.n_posts} posts at " + " / ".join(ftin(x) for x in bl.posts_x) + f" (worst {max(bl.post_loads):,.0f} lb)" for bl in L.beam_lines],
        posts=((f"the {n_posts} existing stucco columns and caissons stay; new post bases epoxy-set on the caissons" if spec.framing.existing_posts else
                f"{n_posts} x {spec.framing.post_size} on the {n_posts} existing caissons, epoxy-set bases") if ft == "existing" else
               f"{n_posts} x {spec.framing.post_size}" + (" Douglas fir #1" if spec.framing.post_species.upper().startswith("DF") and not timber else "") + (" with 4x4 knee braces" if spec.framing.knee_braces else "") + " on " + (
            fr0.footing_model if ft == "diamond_pier" else f"{int(fr0.footing_dia_in)}\" {'caissons' if ft == 'caisson' else 'concrete piers'} {ftin(fr0.footing_depth_in)} deep") + (" with stone column bases" if spec.extras.stone_bases else "")),
        design_load=(f"{max(z.frame.total_psf for z in L.zones):g} psf ({fr0.load_note})" if spec.extras.hot_tub else eng.design_load_words(spec.site.ground_snow_psf))
                    + (" · engineered" if spec.extras.engineered else ""),
        decking=f"{brand} {coll} {color} — {Qz.field_rows} rows {'parallel to' if dk0.direction == 'parallel' else 'perpendicular to'} the house"
                + (f", picture frame{' & dividers' if L.divider_x else ''} in {bcoll} {bcolor}" if spec.geometry.picture_frame else "") + f", {ftin(spec.deck_gap)} gaps, {fsys}",
        rail=((spec.railing.parapet_note or "Existing stucco parapet stays — no rail in this scope") if spec.railing.existing_parapet else f"{rl.system} {rl.height:g}\" {rl.color}: {len(rl.sections)} bays, {len(rl.posts)} posts, {rl.rail_lf} LF" + (" + drink rail" if spec.railing.drink_rail else "") if rl else "none"),
        stairs=[f"{stair_name(ss, s_)}: {s_.geo.risers} risers @ {inches_frac(s_.geo.riser_in)}, {s_.geo.treads} tread{'s' if s_.geo.treads != 1 else ''}, "
                + (f"framed box, no stringers" if getattr(s_, 'build', '') == 'box' else f"{s_.stringers} stringers") + (", fascia skirts" if getattr(s_, 'skirts', False) and getattr(s_, 'build', '') != 'box' else "")
                + f", {ftin(s_.width)} wide"
                + (" — " + " + ".join(f"{fg.risers} riser{'s' if fg.risers != 1 else ''}" for fg in s_.geo.flights) + f" ({ss.turn})" if len(s_.geo.flights) > 1 else "")
                + ("; landings " + " + ".join(f"{ftin(a)} x {ftin(b)}" for a, b in ss.landings) if ss.landings else "")
                + (f"; landing guard {s_.landing_rail_lf:g} LF" if s_.landing_rail_lf else "")
                for s_, ss in zip(stairs, spec.stairs)],
        material_cost=round(sum(l.ext for l in lines), 2),
    )
    if spec.framing.footing_price and spec.framing.footing_type == "diamond_pier":
        for ln in lines:
            if ln.item.startswith("Diamond Pier") and ln.category in ("Footings", "Porch cover", "Stairs"):
                ln.unit_cost, ln.source = float(spec.framing.footing_price), f"owner ${spec.framing.footing_price:g} each"
    if spec.decking.price_per_lf:
        for ln in lines:
            m_ = re.search(r"\b1x6x(\d+)\b", ln.item)
            if ln.category in ("Decking", "Stairs", "Rail") and m_ and coll in ln.item:
                ln.unit_cost, ln.source = round(spec.decking.price_per_lf * int(m_.group(1)), 2), f"owner ${spec.decking.price_per_lf:g}/LF"
        summary["material_cost"] = round(sum(l.ext for l in lines), 2)
    # a stair off the step between two zones reads by name, not by the edge code
    for st_ in spec.stairs:
        if getattr(st_, "name", None) and not st_.side.startswith("step:"):
            # a named stair reads by its name everywhere (the supplier never sees "edge:6")
            nm_ = st_.name
            def _rn(txt, side=st_.side, nm=nm_):
                # only the stair's own references: "(edge:6 stair)", "(edge:2 box step)", "(edge:6)", "(edge:6, stepped)"
                for pat, rep in ((f"{side} stair", nm), (f"{side} box step", nm), (f"({side})", f"({nm})"), (f"({side},", f"({nm},")):
                    txt = txt.replace(pat, rep)
                return txt
            for ln in lines:
                ln.item, ln.why = _rn(ln.item), _rn(ln.why)
            for c_ in cuts:
                c_.member = _rn(c_.member)
            notes[:] = [_rn(n_) for n_ in notes]
            continue
        if st_.side.startswith("step:"):
            na, nb = st_.side.split(":")[1].split("-")
            zl = {z.name: (z.label.split(" — ")[0] if z.label else z.name) for z in spec.geometry.zones}
            pretty = f"{zl.get(nb, nb).lower()} side, toward the {zl.get(na, na).lower()}"
            for ln in lines:
                ln.item, ln.why = ln.item.replace(st_.side, pretty), ln.why.replace(st_.side, pretty)
            for c_ in cuts:
                c_.member = c_.member.replace(st_.side, pretty)
            summary["stairs"] = [x.replace(st_.side + ":", pretty + ":") for x in summary["stairs"]]
    if spec.geometry.outline:            # outline sides read as the numbered sides of the A-100 dimension plan
        import re as _re
        _side = lambda txt: _re.sub(r"\bedge:(\d+)", r"side \1", txt)
        for ln in lines:
            ln.item, ln.why = _side(ln.item), _side(ln.why)
        for c_ in cuts:
            c_.member = _side(c_.member)
        notes[:] = [_side(n_) for n_ in notes]
    t = Takeoff(spec, L, lines, cuts, sched, summary, notes, joist_lf, timber_sf)
    if spec.geometry.louvered_roofs:      # roof posts that are rail posts: no rail post kit there, wall-mount brackets for the panels
        __import__("decktakeoff.louvered", fromlist=["takeoff_hook"]).takeoff_hook(t)
    if spec.framing.system == "steel":
        from .steel import steel_frame
        steel_frame(t)
    return t



def cover_size(spec, c: Optional[dict] = None) -> Tuple[float, float, float]:
    """(along the house ft, out from the house ft, roof area SF) of a roof cover (the first one when c is None)."""
    c = c or covers_of(spec)[0]
    x0, x1, y0, y1 = c["x0"], c["x1"], c["y0"], c["y1"]
    slope = c.get("slope", "+y")
    along = (y1 - y0) if slope in ("+x", "-x") else (x1 - x0)
    out = (x1 - x0) if slope in ("+x", "-x") else (y1 - y0)
    ov = float(c.get("overhang_ft", 1.0))
    if c.get("legacy"):             # the single `cover` list keeps its original take-off (published jobs price the same)
        return along, out, along * (out + 1.5)
    return along, out, (along + 2 * 0.4) * (out + ov + 0.5)


def shared_pier_loads(spec, L, c: dict) -> List[Tuple[float, float, float]]:
    """(x ft, roof lb, deck lb) at each cover post that stands on a deck beam's pier: roof = ground snow + 15 psf dead on the
    post's tributary roof; deck = the load of the deck-beam post at that x (the nearest within 1')."""
    xs = cover_posts_x(c)
    ov = float(c.get("overhang_ft", 1.0))
    depth = (c["y1"] - c["y0"]) / 2 + ov
    out = []
    for i, x in enumerate(xs):
        left = (x - xs[i - 1]) / 2 if i else (x - c["x0"]) + 0.4
        right = (xs[i + 1] - x) / 2 if i < len(xs) - 1 else (c["x1"] - x) + 0.4
        roof = (left + right) * depth * (spec.site.ground_snow_psf + 15.0)
        deck = 0.0
        for bl in L.beam_lines:
            for px, ld in zip(bl.posts_x, bl.post_loads):
                if abs(px / 12.0 - x) < 1.0:
                    deck = max(deck, ld)
        out.append((x, roof, deck))
    return out


def cover_posts_x(c: dict) -> List[float]:
    """Post centers along the low beam (ft, plan x), ≤ 8'-6" OC, 6" in from each end — or the owner's positions."""
    import math as _m
    if c.get("posts_x_ft"):
        return [float(v) for v in c["posts_x_ft"]]
    x0, x1 = (c["y0"], c["y1"]) if c.get("slope", "+y") in ("+x", "-x") else (c["x0"], c["x1"])
    if c.get("legacy"):
        n = max(2, int(_m.ceil((x1 - x0) / 8.5)) + 1)
        return [x0 + 0.5 + k * (x1 - x0 - 1.0) / (n - 1) for k in range(n)]
    n = max(2, int(_m.ceil((x1 - x0 - 1.0) / 8.5 - 1e-9)) + 1)
    return [x0 + 0.5 + k * (x1 - x0 - 1.0) / (n - 1) for k in range(n)]


def cover_lines(spec, c: Optional[dict] = None, tag: str = "") -> List[Line]:
    """Porch cover over the deck: shed roof, ledger on the house, 2x8 rafters @ 16", (2)2x10 beam on 6x6 cedar posts at the rail line,
    OSB, underlayment, then architectural shingles + drip edge OR a standing seam steel roof (24 ga snap-lock panels on high-temp
    underlayment, eave / rake / headwall trims, snow retention bar), 5" K gutter + downspouts when asked, T&G or Hardie ceiling.
    Every price is an estimate until D&D / the metal supplier quotes it."""
    import math as _m
    c = c or covers_of(spec)[0]
    along, out, area = cover_size(spec, c)
    ov = float(c.get("overhang_ft", 1.0))
    out_lines: List[Line] = []
    def L_(item, net, order, unit, why, key=None, section="cover", per=None):
        if key:
            d_ = PRICEBOOK[section][key]; uc, src = d_["each"], d_.get("source", "est.")
            item = item or d_.get("desc", key)
        else:
            uc, src = per, "est."
        out_lines.append(Line("Porch cover", item, net, order, unit, why, uc, src))
    posts_x = cover_posts_x(c)
    n_posts = len(posts_x)
    on_piers = c.get("footing", "deck") in ("diamond_pier", "deck_pier")
    if c.get("clear_low_in"):
        need = float(c["clear_low_in"]) + (spec.geometry.height_in if on_piers else 0.0) + 2.0    # deck (or grade) to the beam bottom
        post_len = next(v for v in (8, 10, 12, 14, 16) if v * 12 >= need)
    else:
        need, post_len = 0.0, 10
    if spec.extras.cover_post_species.upper().startswith("DF"):
        stock = min(st_ for st_ in (8, 10, 12, 14, 16) if st_ >= post_len)
        ucd, srcd = _lumber_price("6x6", stock, False)
        out_lines.append(Line("Porch cover", f"6x6x{stock} {post_words(spec)} post (cover)", n_posts, n_posts, "ea", f"exact  ({n_posts} posts on the beam line, field-cut)", ucd, srcd))
    else:
        L_(f"6x6 x {post_len}' Western red cedar post (cover)", n_posts, n_posts, "ea",
           f"exact  ({n_posts} posts on the low beam at " + " / ".join(ftin(p * 12) for p in posts_x) + (f"; {ftin(need)} cut length" if need else "") + ")",
           per=PRICEBOOK["cover"]["cedar_6x6_lf"]["each"] * post_len)
    cb = c.get("beam", "(2)2x10"); cb_pl = int(cb[1]) if cb.startswith("(") else 1; cb_nom = cb.split(")")[-1]
    cl = c.get("ledger", "2x10")
    beam_pcs = int(_m.ceil(along / 16)) * cb_pl
    if cb_nom.startswith(("4x", "6x")):        # a solid sawn beam: Douglas fir, one piece where the stock allows
        stk = next((v for v in (8, 10, 12, 14, 16, 20) if v >= along + 0.8), 20)
        n_b = int(_m.ceil((along + 0.8) / stk)) * cb_pl
        L_(f"{cb_nom}x{stk} Douglas fir — cover beam", n_b, n_b, "ea", f"+0  ({cb} x {along + 0.8:.1f}' at the posts, one piece)", per=PRICEBOOK["lumber"][cb_nom]["per_lf"] * stk)
    else:
        L_(f"{cb_nom}x16 #1 SYP — cover beam ({cb_pl} ply)", beam_pcs, beam_pcs, "ea", f"+0  ({cb} x {along:.1f}' at the posts)", per=PRICEBOOK["lumber"][cb_nom]["per_lf"] * 16)
    ledger_pcs = int(_m.ceil(along / 16))
    L_(f"{cl}x16 #1 SYP — cover ledger on the house", ledger_pcs, ledger_pcs, "ea", "exact", per=PRICEBOOK["lumber"][cl]["per_lf"] * 16)
    n_r = int(along / (16 / 12)) + 1
    r_len = next(v for v in (8, 10, 12, 14, 16) if v >= out + ov + 0.5)
    L_(f"2x8x{r_len} #1 SYP — cover rafters @ 16\" OC", n_r, n_r + 1, "ea", f"+1 cull  ({n_r} rafters, {out + ov + 0.5:.1f}' with the overhang)", per=PRICEBOOK["lumber"]["2x8"]["per_lf"] * r_len)
    fascia_lf = along + 2 * (out + ov + 0.5)
    fpcs = int(_m.ceil(fascia_lf / 16))
    L_(f"2x8x16 #1 SYP — cover fascia / sub-fascia", fpcs, fpcs + 1, "ea", f"+1  ({fascia_lf:.0f} LF)", per=PRICEBOOK["lumber"]["2x8"]["per_lf"] * 16)
    sheets = int(_m.ceil(area / 32 * 1.1))
    L_(None, sheets, sheets, "sheet", f"{area:.0f} SF + 10% cuts", key="osb_7_16_sheet")
    ss = spec.extras.cover_roof.lower().startswith("standing")
    if not ss:
        L_(None, 1, 1, "roll", f"{area:.0f} SF", key="underlayment_roll")
    if ss:
        color = spec.extras.cover_roof_color or "color TBD"
        panel_len = out + ov + 0.5
        n_panels = int(_m.ceil(along / (16 / 12)))
        mech = spec.extras.cover_roof_panel.lower().startswith("mech")
        ptype = '1-1/2" mechanically seamed (double-lock, low-slope rated)' if mech else "snap-lock"
        L_(f"Standing seam roof — 24 ga steel 16\" {ptype} panels x {panel_len:.1f}' ({color}, PVDF), {n_panels} panels",
           round(area), round(area * 1.05), "SF", f"{n_panels} panels x {panel_len:.1f}' + 5% (one-piece eave to headwall, no end laps)" + (" — mechanical seam priced at the snap-lock rate; confirm with the metal supplier" if mech else ""), key="ss_panel_sf")
        L_(None, int(_m.ceil(area / 200)), int(_m.ceil(area / 200)), "roll", f"{area:.0f} SF — full coverage under metal (high-temp)", key="ht_underlayment_roll")
        L_(None, int(_m.ceil(along / 10)), int(_m.ceil(along / 10)) + 1, "ea", f"{along:.0f} LF low eave + 1", key="ss_eave_trim_10ft")
        L_(None, int(_m.ceil(2 * panel_len / 10)), int(_m.ceil(2 * panel_len / 10)) + 1, "ea", f"two rakes x {panel_len:.1f}' + 1", key="ss_rake_trim_10ft")
        L_(None, int(_m.ceil(along / 10)), int(_m.ceil(along / 10)) + 1, "ea", f"{along:.0f} LF at the house — counterflash into the siding / brick", key="ss_headwall_flash_10ft")
        L_(None, int(_m.ceil(2 * along / 10)), int(_m.ceil(2 * along / 10)), "ea", "eave + headwall closures", key="ss_closure_10ft")
        n_clips = n_panels * int(_m.ceil(panel_len / 1.5))
        L_(None, int(_m.ceil(n_clips / 250)), int(_m.ceil(n_clips / 250)), "box", f"{n_clips} clips @ 18\" OC on each seam", key="ss_clip_screw_kit_250")
        L_(None, 1, 1, "box", "trims, closures, snow bar", key="ss_trim_screws_250")
        L_(None, 3, 3, "ea", "headwall, eave, rake laps", key="ss_butyl_sealant")
        L_(f"Snow retention — clamp-on bar across the low eave over the deck ({color})", round(along), round(along) + 2, "LF", f"{along:.0f}' — metal sheds 30 psf snow onto the deck and stair below; one bar 12-18\" above the eave", key="snow_guard_bar_lf")
    else:
        bundles = int(_m.ceil(area / 100 * 3 * 1.12))
        L_(None, bundles, bundles, "bundle", f"{area / 100:.1f} sq + 12% waste (starter, ridge cap)", key="shingle_bundle")
        de = int(_m.ceil(fascia_lf / 10))
        L_(None, de, de, "ea", f"{fascia_lf:.0f} LF", key="drip_edge_10ft")
        L_(None, round(along), round(along), "LF", "flashing at the ledger", key="ridge_flash_lf")
    if spec.extras.cover_gutters:
        gcolor = spec.extras.cover_gutter_color or "color to match the fascia"
        n_ds = 2 if along > 20 else 1
        ds_drop = 8.5 + 1.0     # cover post height to grade at the low eave (deck 8' + post), field-verify
        L_(f"Gutter — 5\" K-style aluminum on the low eave, {gcolor} ({along:.0f} LF, 1/16\" per ft fall to the outlets)", int(_m.ceil(along / 10)), int(_m.ceil(along / 10)) + 1, "ea", f"{along:.0f} LF — or one seamless run by the gutter sub", key="gutter_5k_10ft")
        L_(None, 2, 2, "ea", "one each end", key="gutter_end_cap")
        L_(None, n_ds, n_ds, "ea", f"{n_ds} downspout{'s' if n_ds > 1 else ''} — at the cover posts", key="gutter_outlet")
        L_(None, int(_m.ceil(along / 2)) + 1, int(_m.ceil(along / 2)) + 1, "ea", "24\" OC (30 psf snow — 16\" OC if the sub asks)", key="gutter_hanger")
        L_(None, 1, 1, "tube", "end caps, outlets, section laps", key="gutter_seam_sealant")
        L_(f"Downspout — 2x3 aluminum, {gcolor}, strapped to the cover post, down the deck post to a splash block at grade", n_ds * int(_m.ceil(ds_drop * 2 / 10)), n_ds * int(_m.ceil(ds_drop * 2 / 10)), "ea", f"{n_ds} x ~{ds_drop * 2:.0f}' (eave to grade past the deck, 2 offsets) — field-measure", key="downspout_2x3_10ft")
        L_(None, n_ds * 4, n_ds * 4, "ea", "2 offsets at the deck edge + 1 at grade + 1 spare, per drop", key="downspout_elbow")
        L_(None, n_ds * 4, n_ds * 4, "ea", "every 5' on the post", key="downspout_strap")
        L_(None, n_ds, n_ds, "ea", "discharge 3'+ from the footings, downhill", key="splash_block")
    if spec.extras.cover_soffit:
        panels = int(_m.ceil(area / 40 * 1.1))
        L_(f"Porch ceiling — HardieSoffit 4' x 10' cedarmill ColorPlus {spec.extras.cover_soffit.split()[-2]} {spec.extras.cover_soffit.split()[-1]} (non-vented; 1 in 3 vented if the roof is closed)", panels, panels, "panel", f"{area:.0f} SF + 10% cuts", key="hardie_soffit_4x10_cedarmill")
        L_(None, int(_m.ceil(area / 60)), int(_m.ceil(area / 60)), "lb", "stainless ring-shank, 6\" OC at every rafter", key="hardie_soffit_nails_lb")
    else:
        L_(None, round(area), round(area * 1.08), "SF", "+8% waste", key="tg_ceiling_sf")
    if spec.extras.cover_fascia:
        nfb = int(_m.ceil(fascia_lf / 12 * 1.05))
        L_(f"Cover fascia + rakes — HardieTrim 4/4 x 7-1/4 x 12' rustic ColorPlus {spec.extras.cover_fascia.split()[-2]} {spec.extras.cover_fascia.split()[-1]} over the 2x8 sub-fascia", nfb, nfb + 1, "ea", f"+1  ({fascia_lf:.0f} LF: front {along:.0f}' + two rakes {out + ov + 0.5:.1f}')", key="hardie_trim_4_4x7_25_rustic_12ft")
        n_cn = 3 * (int(_m.ceil(fascia_lf * 12 / 16)) + nfb)        # TR1509 Table 2: 7-1/4" trim over a 2x sub-fascia, 3 finish nails every 16"
        dn_ = PRICEBOOK["cover"]["hardie_finish_nail_316_1000"]
        L_(None, int(_m.ceil(n_cn / dn_["count"])), int(_m.ceil(n_cn / dn_["count"])), "box",
           f"{n_cn} nails  (3 per 16\" over the 2x8 sub-fascia, 1\" from the ends — TR1509 Table 2)", key="hardie_finish_nail_316_1000")
    if c.get("footing") == "deck_pier":   # the cover post stands on the deck beam's Diamond Pier and carries the deck beam beside it
        ucb, srcb = _price("footings", "ABA66Z")
        out_lines.append(Line("Porch cover", f"Simpson {post_base_sku(spec)} post base on the shared Diamond Pier bolt — cover post (pier counted with the deck)", n_posts, n_posts, "ea", "exact", ucb, srcb))
    elif on_piers:     # the cover posts run past the deck to their own footing: roof snow and uplift do not ride on the deck frame
        ucp, srcp = _price("footings", spec.framing.footing_model if spec.framing.footing_type == "diamond_pier" else "DP-50/50")
        out_lines.append(Line("Porch cover", f"Diamond Pier {spec.framing.footing_model if spec.framing.footing_type == 'diamond_pier' else 'DP-50/50'} — cover post footing (through the deck)", n_posts, n_posts, "ea", "exact  (one per cover post)", ucp, srcp))
        ucb, srcb = _price("footings", "ABA66Z")
        out_lines.append(Line("Porch cover", f"Simpson {post_base_sku(spec)} post base on the pier bolt — cover post", n_posts, n_posts, "ea", "exact", ucb, srcb))
    else:
        L_(None, n_posts, n_posts, "ea", "exact", key="post_base_6x6")
    if cb_nom.startswith("4x"):
        L_("Simpson BC46Z post cap, 6x6 post to the 4x beam" + (" — sized for a rough 6x6 (R-series), confirm SKU" if spec.framing.post_rough else ""), n_posts, n_posts, "ea", "exact", key="BC46Z", section="hardware")
    else:
        L_(f"Simpson {'AC6RZ' if spec.framing.post_rough else 'AC6Z'} post cap, {'rough ' if spec.framing.post_rough else ''}6x6 to the {c.get('beam', '(2)2x10')} beam", n_posts, n_posts, "ea", "exact", key="post_cap_6x6")
    L_(None, n_r, n_r, "ea", "one per rafter at the beam", key="rafter_tie")
    lok = int(_m.ceil(along / 16 * 2)) * 16 // 16 * 2
    L_("FastenMaster LedgerLOK 6\" — cover ledger, 2 rows staggered 16\" OC", int(_m.ceil(along / 16 * 12 * 2)), int(_m.ceil(along / 16 * 12 * 2)), "ea", f"{along:.0f} LF x 2 rows @ 16\"", per=PRICEBOOK["hardware"]["LedgerLOK6_50"]["each"] / 50 if "each" in PRICEBOOK["hardware"]["LedgerLOK6_50"] else 1.2)
    if tag:
        for l in out_lines:
            l.item = f"{l.item} — {tag}"
    return out_lines


QUOTE_CATEGORY_RULES = [
    ("Stairs", ("riser", "stair", "stringer")),
    ("Footings", ("diamond pier", "post base", "abu66", "aba66", "concrete mix", "quikrete", "titen")),
    ("Flashing & waterproofing", ("g-tape", "flash", "membrane", "vycor")),
    ("Hardware", ("simpson", "ledgerlok", "hanger", "tension tie", "hurricane", "post cap", "anchor")),
    ("Fasteners", ("toploc", "cortex", "camo", "screw", "nail", "clip")),
    ("Fascia", ("fascia",)),
    ("Decking", ("1x6x", "deck board", "vintage", "harvest", "landmark", "prime", "legacy", "reserve")),
    ("Rail", ("rail", "post kit", "cable", "impression", "fulton", "cinch", "touch-up")),
    ("Lumber", ("true frame joist", "kdat", "6x6", "4x4", "#2 - gc", "2x")),
]


def quoted_category(item: str, sku: str = "") -> str:
    t = (item + " " + sku).lower()
    for cat, keys in QUOTE_CATEGORY_RULES:
        if any(k in t for k in keys):
            return cat
    return "Hardware"


def apply_quoted_order(t: Takeoff) -> Takeoff:
    """Replace the engine's lines with the owner's quoted order (NET = ORDER = the quoted qty); keep the engine's counts as model_lines."""
    q = t.spec.quoted_order
    if not q:
        return t
    t.model_lines = list(t.lines)
    t.order_ref = t.spec.quoted_ref
    lines: List[Line] = []
    for d in q:
        cat = d.get("category") or quoted_category(d.get("item", ""), d.get("sku", ""))
        qty = float(d.get("qty", 0))
        lines.append(Line(cat, d.get("item", ""), qty, qty, d.get("unit", "ea"), d.get("why", "as quoted"), float(d.get("unit_cost", 0.0)),
                          d.get("source") or (t.spec.quoted_ref or "quoted"), d.get("sku", ""), d.get("note", "")))
    t.lines = lines
    return t
