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
from .catalog import (rail_system_for, STOCK_LENGTHS_FT, DOUBLE_HANGER, FASCIA, H25_NAILS, HANGER_FOR_JOIST, HANGER_NAILS, LUMBER_STOCK_FT, POST_BASE, POST_BASE_SCREWS,
                      POST_CAP_SCREWS, PRICEBOOK, SPECIES_NAMES, TIMBER_BASE, actual, decking_facts, default_fastener_system, parse_beam,
                      RAIL_SYSTEMS)
from .layout import OVERHANG_NO_FASCIA, NOSE, Layout, ZoneLayout, BeamLine, build_layout, LEDGER_T, RIM_PLY
from .spec import post_words, post_base_sku, covers_of, DeckSpec
from .units import ftin

CATEGORIES = ["Lumber", "Footings", "Hardware", "Flashing & waterproofing", "Decking", "Fasteners", "Fascia", "Rail", "Stairs", "Benches", "Planters", "Porch cover", "Shade sail", "Finish", "Site"]
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

    def by_category(self) -> Dict[str, List[Line]]:
        out = defaultdict(list)
        for ln in self.lines:
            out[ln.category].append(ln)
        return {c: out[c] for c in CATEGORIES if out.get(c)}

    def material_total(self) -> float:
        return round(sum(l.ext for l in self.lines), 2)


# ------------------------------------------------------------------ helpers
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
    return round(d["per_lf"] * stock_ft, 2), d["source"]


def _stock_for_piece(nominal: str, length_in: float) -> int:
    for s in LUMBER_STOCK_FT.get(nominal, [8, 10, 12, 16, 20]):
        if length_in <= s * 12 + 0.01:
            return s
    return LUMBER_STOCK_FT.get(nominal, [20])[-1]


def pack_lumber(pieces: List[Tuple[str, float, str]], kerf: float = 0.25, short_stock_ft: int = 12) -> Dict[Tuple[str, int], Tuple[int, List[str]]]:
    """pieces: (nominal, length_in, label). Long pieces (> 8') get the smallest stock that fits, one per board.
    Short pieces are first-fit-decreasing packed into `short_stock_ft` boards. Returns {(nominal, stock_ft): (count, labels)}."""
    out: Dict[Tuple[str, int], Tuple[int, List[str]]] = {}
    shorts = defaultdict(list)
    for nom, L, label in pieces:
        if L > 96:
            st = _stock_for_piece(nom, L)
            c, labels = out.get((nom, st), (0, []))
            out[(nom, st)] = (c + 1, labels + [label])
        else:
            shorts[nom].append((L, label))
    for nom, lst in shorts.items():
        cap = short_stock_ft * 12
        bins: List[List[float]] = []
        blabels: List[List[str]] = []
        for L, label in sorted(lst, key=lambda t: -t[0]):
            need = L + kerf
            for i, b in enumerate(bins):
                if sum(b) + need <= cap:
                    b.append(need); blabels[i].append(label); break
            else:
                bins.append([need]); blabels.append([label])
        c, labels = out.get((nom, short_stock_ft), (0, []))
        out[(nom, short_stock_ft)] = (c + len(bins), labels + [", ".join(sorted(set(x))) for x in blabels])
    return out


def pack_boards(pieces: List[Tuple[str, float]], stocks=(16, 20), kerf: float = 0.125) -> Dict[int, List[List[Tuple[str, float]]]]:
    """Pack deck-board pieces (label, length) first-fit-decreasing into the longest stock, then relabel each board
    with the shortest stock that holds it. Returns {stock_ft: [[pieces in board], ...]}."""
    cap = max(stocks) * 12
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
    packed = pack_boards([(f"panel {r.panel + 1}", r.length + 0.25) for r in P.rows], stocks=tuple(STOCK_LENGTHS_FT))
    for stock, boards in sorted(packed.items()):
        Q_.field_boards[stock] += len(boards)
        multi = sum(1 for b in boards if len(b) > 1)
        Q_.field_piece_note.append(f"{len(boards)} x {stock}'" + (f" ({multi} cut into 2-3 rows)" if multi else ""))
    Q_.field_piece_note.append(" · ".join(f"panel {i + 1} {n} rows" for i, (_, _, n, _) in enumerate(P.panels)) + " · every row one piece")
    for (pi, ln, rip), n in sorted(cut_groups.items()):
        Q_.cuts.append(CutPiece(f"Field boards panel {pi + 1}" + (" (rip)" if rip else ""), f"{spec.decking.collection} {spec.decking.color}", float(ln), n,
                                "one board wall to border, no joints" + ("; ripped to fit the border / the house" if rip else "")))
    Q_.field_rows += P.n_rows
    if P.dropped:
        Q_.cuts.append(CutPiece("Slivers under 6\" (not laid)", f"{spec.decking.collection} {spec.decking.color}", 0.0, P.dropped, "beside the breakers at the bay — the breaker / border covers"))


def accumulate(Q_: Q, spec: DeckSpec, L: Layout, z: ZoneLayout, zi: int) -> None:
    fr, dk = z.frame, z.decking
    tag = f" ({z.name})" if L.multi else ""
    jsize = fr.joist_size
    jb, jd = actual(jsize)
    timber = spec.is_timber
    lsize = spec.ledger_size
    n_field, n_pf = len(fr.joist_x), len(fr.pf_x)
    Q_.n_joists += n_field + n_pf
    rear_t = jb if fr.ledger else fr.rim_plies * jb
    # ---- joists (one bay, or hung on both faces of a mid flush beam)
    flush_mid = [b for b in fr.beams if b.kind == "flush" and b.cl_y + b.width / 2 < z.D - 0.5]
    if not flush_mid:
        Q_.lumber += [(jsize, fr.joist_len, "field joist")] * n_field + [(jsize, fr.joist_len, "PF joist")] * n_pf
        Q_.cuts.append(CutPiece(f"Field joists{tag}", jsize, fr.joist_len, n_field, f"@ {fr.spacing:g}\" OC, crown up"))
        if n_pf:
            Q_.cuts.append(CutPiece(f"Picture-frame joists{tag}", jsize, fr.joist_len, n_pf, f"centre {ftin(fr.pf_x[0])} from each frame face"))
    else:
        sup = [rear_t] + [b.cl_y for b in flush_mid] + [z.D - fr.rim_plies * jb]
        bws = [0.0] + [b.width for b in flush_mid] + [0.0]
        for i, (a, b) in enumerate(zip(sup, sup[1:])):
            ln = round((b - bws[i + 1] / 2) - (a + bws[i] / 2) - 0.25, 2) if i < len(sup) - 2 else round(b - (a + bws[i] / 2) - 0.25, 2)
            lab = "joist upper (wall to the flush beam)" if i == 0 else "joist lower (flush beam to the rim)"
            Q_.lumber += [(jsize, ln, lab)] * (n_field + n_pf)
            Q_.cuts.append(CutPiece(f"Joists {'upper' if i == 0 else 'lower'}{tag}", jsize, ln, n_field + n_pf,
                                    "hung on the inner face of the flush beam" if i == 0 else "hung on the outer face of the flush beam, bears the drop beam"))
    # ---- doubled joists under dividers (one extra ply each) — multi-zone plans with dividers
    n_div_here = sum(1 for x, Ld, lab in L.divider_x if z.x0 - 0.6 <= x < z.x0 + z.W - 0.6 or (zi == len(L.zones) - 1 and abs(x - (z.x0 + z.W)) < 0.6))
    if n_div_here:
        Q_.lumber += [(jsize, fr.joist_len, "divider doubler")] * n_div_here
        Q_.cuts.append(CutPiece(f"Divider doublers{tag}", jsize, fr.joist_len, n_div_here, "sister a joist on the divider line so both board edges bear"))
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
        Q_.hangers_single += (n_field + n_pf) + (2 if fr.ledger else 0) + 2 * (n_field + n_pf) * len(flush_mid)
        Q_.hangers_double += n_div_here + 2 * len(flush_mid)
        Q_.h25 += sum((n_field + n_pf + n_div_here + 2) for b in fr.beams if b.kind == "drop")
    else:
        Q_.hangers_single += fr.hangers_single
        Q_.hangers_double += fr.hangers_double
        Q_.h25 += fr.h25_ties
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
    Q_.tape_block_lf += fr.n_blocks_per_row * n_block_rows * fr.block_len / 12.0
    # ---- timber surface / ends
    if timber:
        pieces_here = (n_field + n_pf + n_div_here) * (2 if flush_mid else 1) + 2 * fr.rim_plies + (0 if front_flush else fr.rim_plies) + (1 if fr.ledger else fr.rim_plies) + fr.n_blocks_per_row * n_block_rows
        Q_.timber_ends += 2 * pieces_here
    # ---- decking: field boards per run, rips, cortex per run (an outline-laid plan is counted once, after the zones)
    runs = ([] if L.plan is not None else (_field_runs(spec, L, z, zi) if L.multi else [(dk.rows, dk.field_len, z.name)]))
    for n_rows, run_len, lab in runs:
        k = max(1, int(math.ceil(run_len / 240.0)))
        piece = run_len / k
        stock = next((s for s in (12, 16, 20) if piece <= s * 12 + 0.01), 20)
        n_b, per = n_rows * k, 1
        # short rows: cut 2 or 3 from one longer board when that buys fewer LF (7' rows: two from a 16')
        for m in (2, 3):
            st_m = next((s for s in (12, 16, 20) if m * (piece + 0.25) <= s * 12 + 0.01), None)
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
    drop_lab = ("left rim ply", "right rim ply", "front rim ply", "rear rim ply", "ledger", "field joist", "PF joist", "divider doubler",
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
    # rims: every ply its own mitred length
    rim_lf = 0.0
    for i, k, x0, y0, x1, y1 in OF.rims:
        ln = round(math.hypot(x1 - x0, y1 - y0), 2)
        rim_lf += ln
        Q_.lumber.append((jsize, ln, "outline rim ply"))
    for i in sorted({r[0] for r in OF.rims}):
        lens = [math.hypot(r[4] - r[2], r[5] - r[3]) for r in OF.rims if r[0] == i]
        Q_.cuts.append(CutPiece(f"Rim side {i + 1} ({OF.side_kind[i]})", jsize, max(lens), len(lens),
                                ("mitred both ends" if OF.side_kind[i] != "rim" else "square / mitred to the neighbours")
                                + (", 1/2\" off the bay face — no ledger on the cantilevered bay" if OF.side_kind[i] == "bay45" else "")
                                + (", plies laminated RSS 2 rows @ 12\" staggered" if plies > 1 else "")))
    # ledger + ledger blocks
    Q_.ledger_len = 0.0
    for x0, y0, x1, y1 in OF.ledgers:
        ln = math.hypot(x1 - x0, y1 - y0)
        Q_.ledger_len += ln
        Q_.lumber.append((spec.ledger_size, round(ln, 2), "ledger"))
        Q_.cuts.append(CutPiece("Ledger (main wall)", spec.ledger_size, round(ln, 2), 1, "top at deck height less the board; membrane behind, flashing over; LedgerLOK per the schedule"))
    for x0, y0, x1, y1 in OF.ledger_blocks:
        ln = math.hypot(x1 - x0, y1 - y0)
        Q_.ledger_len += ln
        Q_.lumber.append((spec.ledger_size, round(ln, 2), "ledger block"))
        Q_.cuts.append(CutPiece("Ledger block (beside the bay)", spec.ledger_size, round(ln, 2), 1, "3 LedgerLOKs, flashed; the two angled rims hang from it (skewed double hanger)"))
    # blocking under the 45-degree borders
    blk = [math.hypot(x1 - x0, y1 - y0) for x0, y0, x1, y1, lab in OF.blocks]
    Q_.lumber += [(jsize, round(b_ + 1.0, 2), "PF block (angled border)") for b_ in blk]     # +1" for the bevel cuts
    if blk:
        Q_.cuts.append(CutPiece("Blocks under the 45-degree borders", jsize, max(blk), len(blk), "a line 1-1/2\" inside the rim, one per joist bay, bevel both ends"))
    Q_.n_blocks = len(blk)
    # hangers: every joist end by what it lands on
    Q_.hangers_single = sum((e in ("ledger", "beam", "rim")) for _, _, _, ea, eb, _ in OF.joists for e in (ea, eb))
    Q_.hangers_skew = sum((e in ("rim45", "bay45")) for _, _, _, ea, eb, _ in OF.joists for e in (ea, eb))
    Q_.hangers_double = 0
    Q_.hangers_skew_double = 2 * len(OF.ledger_blocks)
    # fascia: every open side, its own mitred length
    Q_.fascia_pieces = []
    if spec.decking.fascia:
        for e, kind in zip(L.outline_edges, OF.side_kind):
            if kind in ("rim", "rim45"):
                Q_.fascia_pieces.append((f"fascia {e.name}", round(e.length + 1.5, 2)))
    # joist tape (2" on every joist + the ledger), 4" on rims and beams
    Q_.tape_joist_lf = (sum(b - a for _, a, b, *_ in OF.joists) + Q_.ledger_len) / 12.0
    Q_.tape_wide_lf = (rim_lf + sum(ln.length * ln.plies / ln.plies for ln in L.beam_lines)) / 12.0
    Q_.tape_block_lf = sum(blk) / 12.0
    Q_.rss_lam = int(rim_lf / plies / 12.0 * 2 + 0.999) * (plies - 1) if plies > 1 else 0
    Q_.outline_notes = OF.notes
    Q_.outline_ledgers = list(OF.ledgers)


def jb_of(nominal: str) -> float:
    return actual(nominal)[0]


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
    # ---- outline-laid plan: a border piece on every exposed edge (the curve as mitred segments), split at the breakers; the breakers
    if L.plan is not None and spec.geometry.picture_frame:
        edge = (dk0.fascia_t + NOSE) if spec.decking.fascia else OVERHANG_NO_FASCIA
        bw, gap = dk0.bw, dk0.gap
        div_xs = [x for x, _, _, _ in L.plan.dividers]
        for x0, y0, x1, y1, _ in L.plan.borders:
            xa, xb = sorted((x0, x1))
            cuts_x = [xa] + [x for x in div_xs if xa + 1 < x < xb - 1] + [xb]
            if abs(y1 - y0) < 0.5 and len(cuts_x) > 2:
                for a, b in zip(cuts_x, cuts_x[1:]):
                    Qz.border_pieces.append((f"border {ftin(a)}-{ftin(b)}", b - a - (bw / 2 + gap) * ((a != xa) + (b != xb))))
            else:
                Qz.border_pieces.append((f"border {ftin(xa)},{ftin(min(y0, y1))}", math.hypot(x1 - x0, y1 - y0) + (bw if abs(y1 - y0) > 0.5 and abs(x1 - x0) > 0.5 else edge)))
        for x, y_lo, y_hi, lab in L.plan.dividers:
            Qz.border_pieces.append((f"breaker {lab}", y_hi - y_lo))
        Qz.border_screws = sum(2 * (int(math.floor(Lb / 16)) + 2) for _, Lb in Qz.border_pieces)
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
        Qz.border_screws = sum(2 * (int(math.floor(Lb / 16)) + 2) for _, Lb in Qz.border_pieces)
    # stairs lumber
    for st in stairs:
        multi = len(st.geo.flights) > 1
        if getattr(st, "skirts", False):
            # stepped fascia skirts: one piece per side, cut to the step profile from a 12" fascia board
            for fg in st.geo.flights:
                Qz.fascia_pieces += [(f"stair skirt ({st.side}, stepped)", round(fg.treads * st.geo.tread_in + 1.0, 1))] * 2
        if getattr(st, "build", "stringers") == "box":
            # a framed box per tread: 2x6 front + back rims across the width, cross members at 16" — no stringers, no hanger board
            ncm = int(math.ceil(st.width / 16.0)) + 1
            for k in range(st.geo.treads):
                Qz.lumber += [("2x6", st.width, "box step rim")] * 2 + [("2x6", round(st.geo.tread_in - 3.6, 1), "box step cross member")] * ncm
            cuts.append(CutPiece(f"Box step frame ({st.side})", "2x6", st.width, 2 * st.geo.treads,
                                 f"front + back rims, {ncm} cross members @ 16\" between — rip to {st.geo.riser_in - 0.94:.2f}\" (riser less the tread)"))
            continue
        for fi, fg in enumerate(st.geo.flights):
            Qz.lumber += [("2x12", fg.stringer_len_in, "stair stringer")] * st.stringers
            cuts.append(CutPiece(f"Stair stringers ({st.side}" + (f", flight {fi + 1}" if multi else "") + ")", "2x12", fg.stringer_len_in, st.stringers,
                                 f"{fg.risers} risers @ {st.geo.riser_in:.3f}\" · {fg.treads} treads @ {st.geo.tread_in:.2f}\" · stringers {eng.STRINGER_OC_COMPOSITE:g}\" OC"))
            Qz.lumber += [("2x6", st.width + 3, "stair kicker/hanger board")] * 2
    # rail post blocks (timber / IRX: 10-1/2" blocks at every rail post)
    n_rail_posts = (len(rl.posts) if rl else 0) + sum(s.stair_posts for s in stairs)
    knee = spec.framing.knee_braces and not timber and not spec.framing.existing_posts and spec.framing.system != "steel"
    n_knee_posts = sum(bl.n_posts for bl in L.beam_lines) if knee else 0
    if knee:
        Qz.lumber += [(jsize, 14.5, "knee-brace block")] * n_knee_posts
    surface_rail = bool(rl) and RAIL_SYSTEMS.get(rl.system, {}).get("surface", False)
    if rl and (timber or surface_rail):
        Qz.lumber += [(jsize, 10.5 if timber else 14.5, "rail post block")] * len(rl.posts)

    # ================= LUMBER
    packed = pack_lumber(Qz.lumber)
    joist_lf = sum(st * 12 * n for (nom, st), (n, _) in packed.items() if nom == jsize) / 12.0
    for (nom, st), (n, labels) in sorted(packed.items(), key=lambda t: (t[0][0], t[0][1])):
        is_timber_piece = timber and nom in ("4x8", "4x10", "4x12")
        uc, src = _lumber_price(nom, st, is_timber_piece)
        if is_timber_piece:
            desc = f"{nom}x{st} {SPECIES_NAMES['DF#1']}"
        elif nom in ("2x6", "2x8", "2x10", "2x12"):
            desc = f"{nom}x{st} {SPECIES_NAMES.get(jsp, jsp)}"
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
    sp = spec.framing.beams[0].species if spec.framing.beams else "DF"
    df1_beam = sp == "DF#1" and not timber
    for (nom, st), (n, labels) in pack_lumber(beam_pieces, short_stock_ft=8 if df1_beam else 12).items():
        uc, src = _lumber_price(nom, st, timber or df1_beam)
        desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if timber else 'Douglas Fir #1' if df1_beam else SPECIES_NAMES.get(sp, sp)}"
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  ({_summarize_labels(labels)}: " + " · ".join(bl.label for bl in L.beam_lines) + ")", uc, src))
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
                    post_pieces += [(spec.framing.post_size, h_c + 6.0, "stair carrier post")] * 2
                    cuts.append(CutPiece(f"Stair carrier posts ({tagf})", spec.framing.post_size, h_c, 2, "under the stringers — field-measure"))
                    cuts.append(CutPiece(f"Stair carrier ({tagf})", "2x6" if not timber else "4x6", st_.width + 6, 2, "2 ply, notched stringers bear on it; hurricane tie each stringer"))
            car = "2x6" if not timber else "4x6"
            n_car = len(idx) * len(fracs)
            uc, src = _lumber_price(car, 12, timber)
            lines.append(Line("Lumber", f"{car}x12 {'#1 KDAT' if not timber else 'DF #1'} — stair carrier (2 ply) + blocking between stringers at each carrier ({st_.side}" + (f", {n_car} carriers" if n_car > 1 else "") + ")",
                              3 * n_car, 3 * n_car, "ea", f"exact  (2 ply x {ftin(st_.width + 6)} carrier + {st_.stringers - 1} blocks, 1 spare — per carrier)", uc, src))
    for (nom, st), (n, labels) in pack_lumber(post_pieces, short_stock_ft=8).items():
        df1_post = spec.framing.post_species.upper().startswith("DF") and not timber
        uc, src = _lumber_price(nom, st, timber or df1_post)
        desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if (timber or nom.startswith('8x')) else 'Douglas Fir #1' if df1_post else '#2 GC'}"
        lens = sorted(set(ftin(bl.post_len) for bl in L.beam_lines))
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  (yields {n_posts} posts at ~{' / '.join(lens)})", uc, src))
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
        uc, src = _price("footings", base)
        lines.append(Line("Footings", _desc("footings", base, base) + " on the pier bolt", n_posts, n_posts, "ea", "exact", uc, src, base))
        base_screws = n_posts * POST_BASE_SCREWS.get(base, 12)
    elif ft == "caisson":
        dia, depth = fr0.footing_dia_in, fr0.footing_depth_in
        above = 6.0
        tube_len = depth + above
        vol_cf = math.pi * (dia / 24) ** 2 * (tube_len / 12)
        bags_each = int(math.ceil(vol_cf / 0.6))
        per_tube = max(1, int(math.floor(144 / tube_len)))
        tubes = int(math.ceil(n_posts / per_tube))
        tkey = f"sonotube_{int(dia)}" if f"sonotube_{int(dia)}" in PRICEBOOK["footings"] else "sonotube_20"
        d_, uc, src = _item("footings", tkey, f"Sonotube {int(dia)}\" x 12'")
        lines.append(Line("Footings", f"{d_} — caissons {int(dia)}\" x {ftin(depth)} + {ftin(above)} above grade (frost {ftin(spec.site.frost_depth_in)})", tubes, tubes, "ea",
                          f"exact  ({n_posts} caissons, {per_tube} per tube)", uc, src, note=f"{worst_load:,.0f} lb per post vs ~{fr0.footing_capacity_lb:,.0f} lb (end bearing + skin friction estimate); engineer sets diameter"))
        d_, uc, src = _item("footings", "quikrete_80", "Quikrete 80# concrete mix")
        lines.append(Line("Footings", d_, bags_each * n_posts, bags_each * n_posts, "bag", f"exact  ({bags_each} bags per caisson)", uc, src))
        r4 = int(math.ceil(n_posts * 4 * tube_len / 12 / 20))
        r3 = int(math.ceil(n_posts * (math.pi * (dia - 4) / 12 * 4) / 20))
        d_, uc, src = _item("footings", "rebar4_20"); lines.append(Line("Footings", d_, r4, r4, "ea", "exact — engineer governs", uc, src))
        d_, uc, src = _item("footings", "rebar3_20"); lines.append(Line("Footings", d_, r3, r3, "ea", "exact — engineer governs", uc, src))
        d_, uc, src = _item("footings", "anchor_5/8x8"); lines.append(Line("Footings", d_, n_posts, n_posts, "ea", "exact", uc, src))
        bkeys = TIMBER_BASE.get(spec.framing.post_size, ("ABU66Z_black", "ABU66Z"))
        bkey = bkeys[0] if black else bkeys[1]
        d_, uc, src = _item("footings", bkey)
        lines.append(Line("Footings", d_, n_posts, n_posts, "ea", "exact", uc, src, bkey))
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
        lines.append(Line("Footings", _desc("footings", base, base) + " wet-set 1/2\" anchor", n_posts, n_posts, "ea", "exact", uc, src, base))
        base_screws = n_posts * POST_BASE_SCREWS.get(base, 12)
    if spec.extras.stone_bases:
        d_, uc, src = _item("footings", "stone_base_kit")
        lines.append(Line("Footings", d_, n_posts, n_posts, "ea", f"exact  (all {n_posts} posts)", uc, src))
    for st in stairs:
        if st.landing == "concrete pad":
            uc, src = _price("footings", "concrete_pad")
            lines.append(Line("Footings", f"Stair landing pad ({st.side} stair) — 4\" slab, stringers bear on the pad", 1, 1, "ea", "exact", uc, src))
    # intermediate stair landings: a framed platform (joist-size rims + joists at the deck spacing) on four posts, decked in the field board
    for st_s in spec.stairs:
        for li, (lw, ld) in enumerate(st_s.landings or []):
            lw, ld = float(lw), float(ld)
            n_j = int(lw / spec.joist_spacing) + 2
            pcs = int(math.ceil((2 * (lw + ld) / 12 + n_j * ld / 12) / 12)) + 1
            uc, src = _lumber_price(jsize, 12, timber)
            lines.append(Line("Stairs", f"{jsize}x12 {SPECIES_NAMES.get(jsp, jsp)} — landing {li + 1} frame ({ftin(lw)} x {ftin(ld)}, {st_s.side} stair)", pcs, pcs, "ea", f"+1  (rims + {n_j} joists @ {spec.joist_spacing:g}\")", uc, src))
            uc, src = _lumber_price(spec.framing.post_size, 8, timber or spec.framing.post_size.startswith("8x"))
            lines.append(Line("Stairs", f"{spec.framing.post_size}x8 — landing {li + 1} posts (4)", 4, 4, "ea", "exact", uc, src))
            if spec.framing.footing_type == "diamond_pier":     # the landing sits on the same footing the deck does
                ucp, srcp = _price("footings", spec.framing.footing_model)
                lines.append(Line("Stairs", f"Diamond Pier {spec.framing.footing_model} — landing {li + 1} footings", 4, 4, "ea", "exact  (one under each landing post)", ucp, srcp))
                ucb, srcb = _price("footings", "ABA66Z" if spec.framing.post_size == "6x6" else "ABA44Z")
                lines.append(Line("Stairs", f"Simpson {'ABA66Z' if spec.framing.post_size == '6x6' else 'ABA44Z'} post base on the pier bolt — landing {li + 1}", 4, 4, "ea", "exact", ucb, srcb))
            else:
                uc, src = _price("footings", "concrete_pad")
                lines.append(Line("Stairs", f"Landing {li + 1} footings — 4 concrete piers 12\" x frost, wet-set bases", 4, 4, "ea", "exact", uc * 0.6, src))
            sf_l = lw * ld / 144
            dk = decking_facts(spec.decking.collection)
            nb = int(math.ceil(sf_l / (dk["width"] / 12 * 12) * 1.1))
            lines.append(Line("Stairs", f"{spec.decking.brand} {spec.decking.collection} {spec.decking.color} 1x6x12 — landing {li + 1} decking ({sf_l:.0f} SF)", nb, nb, "ea", "+10% cuts", *_price("decking", f"{spec.decking.brand}|{spec.decking.collection}|12|{spec.decking.profile}")))

    # ================= HARDWARE / CONNECTORS
    hanger = HANGER_FOR_JOIST.get(jsize, "LUS28Z")
    d_, uc, src, sku = _hw(hanger, black)
    n_flush = sum(1 for bl in L.beam_lines if bl.kind == "flush" and not bl.label.startswith("FRONT"))
    why = (f"exact  (joists at the ledgers + rim ends" + (f" + both faces of the flush beam" if n_flush else "") + ")") if timber \
        else (f"exact  ({Qz.hangers_single} joist ends on the ledger, the flush beams and the square rims — framing plan)" if getattr(Qz, 'outline_ledgers', None) is not None
              else f"exact  ({Qz.n_joists} joists x {Qz.hangers_single // max(1, Qz.n_joists)} ends)")
    lines.append(Line("Hardware", d_, Qz.hangers_single, Qz.hangers_single, "ea", why, uc, src, sku))
    if Qz.hangers_double:
        dh = DOUBLE_HANGER.get(jsize, "HUCQ210-2-SDS")
        d_, uc, src, sku = _hw(dh, black)
        lines.append(Line("Hardware", d_, Qz.hangers_double, Qz.hangers_double, "ea",
                          "exact  (doubled joists under the dividers, hung rims at the flush beam)" if timber else "exact  (2 side rims x 2 ends) — confirm stock", uc, src, sku))
    if Qz.hangers_skew:
        lines.append(Line("Hardware", f"Simpson SUR{jsize.replace('2x', '2')}Z / SUL{jsize.replace('2x', '2')}Z skewed 45-degree hanger (right / left as the angle runs)", Qz.hangers_skew, Qz.hangers_skew + 2, "ea",
                          f"+2  (joist ends on the 45-degree rims, from the framing plan)", 9.5, "est. — confirm D&D stock"))
    if Qz.hangers_skew_double:
        lines.append(Line("Hardware", f"Simpson SUR{jsize.replace('2x', '2')}-2Z / SUL{jsize.replace('2x', '2')}-2Z skewed double hanger — the two angled rims at the ledger block beside the bay", Qz.hangers_skew_double, Qz.hangers_skew_double, "ea",
                          "exact", 24.0, "est. — confirm D&D stock"))
    nh, nj = HANGER_NAILS.get(hanger, (6, 4))
    n_long = Qz.hangers_single * nh
    n_short = Qz.hangers_single * nj + Qz.h25 * H25_NAILS
    if timber:
        # 4x hangers take 16d into the header: from the ring-shank box, with the rim end-nailing and blocking toe-nails
        need16 = n_long + 6 * Qz.n_blocks + 4 * Qz.n_joists
        d = PRICEBOOK["hardware"]["nail_16d_ring_2000"]
        boxes = max(1, int(math.ceil(need16 / d["count"])))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need16} needed — hanger headers, rim end-nailing, blocking toe-nails", d["each"], d["source"]))
        pairs = (("nail_1.5in_5lb", n_short),)
    else:
        pairs = (("nail_3in_5lb", n_long), ("nail_1.5in_5lb", n_short))
    for key, need in pairs:
        d = PRICEBOOK["hardware"][key]
        boxes = max(1, int(math.ceil(need / d["count"])))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need} needed of ~{boxes * d['count']}", d["each"], d["source"], key))
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
                n_ll, rule = eng.ledger_fastener_count(Qz.ledger_len, fr0.beams[0].back_span if fr0.beams else fr0.joist_len, "LedgerLOK")
            d = PRICEBOOK["hardware"][key]
            boxes = int(math.ceil(n_ll / d["count"]))
            lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{n_ll} needed", d["each"], d["source"], key))
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
            n_ledgers = len(getattr(Qz, 'outline_ledgers', [])) if getattr(Qz, 'outline_ledgers', None) is not None else ((len(L.zones) if L.multi else 1))
            n_dtt = spec.framing.lateral_ties * max(1, n_ledgers)
            d = PRICEBOOK["hardware"]["DTT1Z"]
            lines.append(Line("Hardware", d["desc"], n_dtt, n_dtt, "ea", "exact  (2 near each end of every ledger, into house floor framing)", d["each"], d["source"], "DTT1Z"))
    if Qz.h25:
        d_, uc, src, sku = _hw("H2.5AZ", False)
        lines.append(Line("Hardware", d_, Qz.h25, Qz.h25, "ea", "exact  (every joist, doubler and rim at the drop beam)" if timber else f"exact  ({Qz.n_joists} joists + 2 rims at each drop beam)", uc, src, sku))
    sd_screws = base_screws
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
        if nb:
            d_, uc, src, sku = _hw("bolt_1/2x8", black)
            lines.append(Line("Hardware", d_, nb, nb + 2, "ea", f"+2  ((2)4x beam plies through-bolted, 2 rows staggered @ 24\" OC, 2\" from top and bottom)", uc, src))
            sched["Beam"] = "(2)4x plies through-bolted with 1/2\" HDG bolts, 2 rows 2\" from top and bottom, staggered @ 24\" OC, a bolt pair 6\" from each end; CCQ cap with SDS screws at each post"
    if sd_screws:
        d = PRICEBOOK["hardware"]["SD10212_100"]
        boxes = int(math.ceil(sd_screws / d["count"]))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{sd_screws} needed  (bases {base_screws} · caps {sd_screws - base_screws})", d["each"], d["source"]))
    blk = 0 if timber else 4 * Qz.n_blocks
    rss = Qz.rss_lam + blk
    if timber and Qz.n_blocks:
        sched["Blocking"] = f"{Qz.n_blocks} x {jsize} blocks, (3) 16d toe-nails each end"
    if rss:
        d = PRICEBOOK["hardware"]["RSS_3-1/8_100"]
        boxes = int(math.ceil(rss / d["count"]))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{rss} needed  (laminations {Qz.rss_lam} · blocking {blk})", d["each"], d["source"]))
    if rl and n_rail_posts:
        if timber or RAIL_SYSTEMS.get(rl.system, {}).get("cable") or surface_rail:
            d = PRICEBOOK["hardware"]["HeadLOK6_50"]
            need = 4 * n_rail_posts
            boxes = int(math.ceil(need / d["count"]))
            lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need} needed  ({n_rail_posts} rail posts x 4)", d["each"], d["source"]))
        else:
            nb = 2 * n_rail_posts
            d_, uc, src, sku = _hw("bolt_7/16x4.5", black)
            lines.append(Line("Hardware", d_, nb, nb + 2, "ea", f"+2  ({n_rail_posts} rail posts x 2)", uc, src))
    for st in stairs:
        if getattr(st, "build", "stringers") == "box":
            lines.append(Line("Hardware", "GRK RSS #10 x 3-1/8\" structural screw — box step frame, and the box to the deck rim (bag of 50)", 1, 1, "bag",
                              f"exact  ({st.side} box step)", 22.0, "est."))
            cf = st.width * st.geo.treads * st.geo.tread_in * 4.0 / 1728.0 * 1.25
            nbag = int(math.ceil(cf / 0.5))
            lines.append(Line("Stairs", f"3/4\" crushed rock / road base 0.5 cf bag — 4\" compacted bed under the box step ({st.side})", nbag, nbag, "bag",
                              f"exact  ({cf:.1f} cf incl. 25% compaction)", 6.5, "est."))
            continue
        d = PRICEBOOK["hardware"]["LSCZ"]
        n_sc = st.stringers * len(st.geo.flights)
        lines.append(Line("Hardware", d["desc"], n_sc, n_sc, "ea", f"exact  ({st.side} stair, 1 per stringer at the rim" + (f" — {len(st.geo.flights)} flights" if len(st.geo.flights) > 1 else "") + ")", d["each"], d["source"], "LSCZ"))
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
            d = PRICEBOOK["hardware"]["lflash_10"]
            n = int(math.ceil(wall_lf / 10))
            lines.append(Line("Flashing & waterproofing", d["desc"], n, n, "ea", "house walls only", d["each"], d["source"]))
            if spec.site.wui_fire_zone:
                d = PRICEBOOK["hardware"]["wui_flash_10"]
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
            sched["Joist tape"] = "G-Tape 2\" every joist, PF joist, blocking and the ledger top · 4\" on both rims and the beam(s)"

    # ================= DECKING
    prof = "Grooved" if spec.decking.profile == "grooved" else "Square Edge"
    for stock, n_rows in sorted(Qz.field_boards.items()):
        key = f"{brand}|{coll}|{stock}|{spec.decking.profile}"
        uc, src = _price("decking", key)
        if uc == 0.0:
            lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * stock, 2)
        lines.append(Line("Decking", f"{brand} {coll} {color} 1x6x{stock} {prof}", n_rows, n_rows + 2, "ea",
                          "+2  (" + " · ".join(n for n in Qz.field_piece_note if n.split(":")[0] and True) + ")", uc, src))
    if Qz.rip_strips:
        n_rip = len(pack_boards([("rip", s) for s in Qz.rip_strips], stocks=(16,), kerf=0.125)[16]) if False else int(math.ceil(sum(s + 0.125 for s in Qz.rip_strips) / dk0.bw))
        stock = 16 if timber else 12
        uc, src = _price("decking", f"{brand}|{coll}|{stock}|square")
        if uc == 0.0:
            lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * stock, 2)
        lines.append(Line("Decking", f"{brand} {coll} {color} 1x6x{stock} Square Edge — rip boards at the house", n_rip, n_rip, "ea",
                          "exact  (" + " · ".join(f"{s:.2f}\"" for s in Qz.rip_strips) + " strips)", uc, src))
    if spec.geometry.picture_frame and Qz.border_pieces:
        packed_b = pack_boards(Qz.border_pieces, stocks=(16, 20) if timber or L.multi else (12, 16, 20))
        for s_, boards in sorted(packed_b.items()):
            key = f"{brand}|{bcoll}|{s_}|square"
            uc, src = _price("decking", key)
            if uc == 0.0:
                lf, src = _price("decking", f"{brand}|{bcoll}|per_lf"); uc = round(lf * s_, 2)
            what = " · ".join(" + ".join(f"{n} {ftin(l)}" for n, l in b) for b in boards)
            lines.append(Line("Decking", f"{brand} {bcoll} {bcolor} 1x6x{s_} Square Edge — {'borders & dividers' if L.divider_x else 'borders'}", len(boards), len(boards) + (1 if s_ == max(packed_b) else 0), "ea",
                              (f"+1  " if s_ == max(packed_b) else "exact  ") + f"({what})", uc, src))
        for name, Lb in Qz.border_pieces:
            cuts.append(CutPiece(name.capitalize(), f"{bcoll} {bcolor} square", Lb, 1, "mitre at the corners; dividers on the doubled joist"))
    for st in stairs:
        per_board = max(1, int(math.floor(144 / (st.width + 0.25))))
        nb = int(math.ceil(st.tread_pieces / per_board))
        uc, src = _price("decking", f"{brand}|{coll}|12|square")
        if uc == 0.0:
            lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * 12, 2)
        lines.append(Line("Stairs", f"{brand} {coll} {color} 1x6x12 Square Edge — treads ({st.side} stair)", nb, nb + 1, "ea",
                          f"+1  ({st.geo.treads} treads x 2 boards @ {ftin(st.width)}, {per_board} per board)", uc, src))
        if st.riser_pieces:
            nr = int(math.ceil(st.riser_pieces / per_board))
            uc, src = _price("decking", f"{brand}|{coll}|riser")
            if uc == 0.0:
                lf, src = _price("decking", "generic_riser_per_lf"); uc = round(lf * 12, 2)
            lines.append(Line("Stairs", f"{brand} {coll} {color} riser board 7-1/4\" x 12' ({st.side} stair)", nr, nr, "ea",
                              f"exact  ({st.geo.risers} risers @ {ftin(st.width)})", uc, src))
        cuts.append(CutPiece(f"Stair treads ({st.side})", f"{coll} {color} square", st.width, st.tread_pieces, "2 boards per tread, nosing 3/4\" over the riser"))
        if st.riser_pieces:
            cuts.append(CutPiece(f"Stair risers ({st.side})", "riser board", st.width, st.riser_pieces, f"rip to {st.geo.riser_in:.2f}\" less tread thickness"))

    # ================= BUILT-INS: benches (4x4 legs wrapped in deck board, 2x4 seat frame) and planters (2x4 box, OSB, deck-board skin)
    from .scene import bench_segments, planter_segments
    uc12, src12 = _price("decking", f"{brand}|{coll}|12|square")
    if uc12 == 0.0:
        lf, src12 = _price("decking", f"{brand}|{coll}|per_lf"); uc12 = round(lf * 12, 2)
    dcx = PRICEBOOK["decking"]["Cortex_TimberTech_350"]
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
        nb = sum(len(v) for v in pack_boards(pieces, stocks=(12,)).values())
        lines.append(Line("Benches", f"{brand} {coll} {color} 1x6x12 Square Edge — bench seats, aprons, back slats and post wraps ({len(bsegs)} sections, {ftin(blf * 12)})", nb, nb + 1, "ea",
                          f"+1  ({len(pieces)} pieces packed into 12' boards)", uc12, src12))
        post_len = 44.0                                          # rim bottom to the back's top
        n44 = int(math.ceil(n_back / 2)) + int(math.ceil(n_front / 8))
        lines.append(Line("Benches", f"4x4x8 #2 GC ground-contact — {n_back} back posts (bolted through the rim, {post_len:.0f}\") + {n_front} front legs (10-1/2\"), all wrapped", n44, n44 + 1, "ea",
                          f"+1  (2 back posts per stick, 8 legs per stick)", uc44, src44))
        n26 = int(math.ceil((rail_lf * 12 + n_cross * 14.0) * 1.1 / (12 * 12)))
        uc26, src26 = _lumber_price("2x6", 12)
        lines.append(Line("Benches", f"2x6x12 #1 True Frame — seat rails (front + back) and {n_cross} seat supports at 16\" OC", n26, n26 + 1, "ea",
                          f"+1  ({rail_lf:.0f} LF rails + {n_cross} x 14\")", uc26, src26))
        ncx = len(pieces) * 4
        lines.append(Line("Benches", f"Cortex for TimberTech, {color} plugs — bench seats, aprons, slats, wraps (350 ct)", -(-ncx // dcx["count"]), -(-ncx // dcx["count"]), "box", f"~{ncx} screws", dcx["each"], dcx["source"]))
        lines.append(Line("Benches", "1/2\" x 8\" HDG carriage bolt + nut + washer — back posts through the rim", 2 * n_back, 2 * n_back + 2, "ea", f"+2  (2 per back post)", 3.1, "est."))
        lines.append(Line("Benches", "GRK RSS #10 x 3-1/8\" structural screw — seat rails and supports (bag of 50)", 2, 2, "bag", "est.", 22.0, "est."))
        notes.append(f"benches: {len(bsegs)} sections, {ftin(blf * 12)} — seat 17\" high x 17\" deep, back to 34\", 4x4 posts at 36\" max wrapped in deck board, seat supports at 16\"; same footprint as the existing benches")
    ds = getattr(spec.geometry, "door_step", None)
    if ds:
        wd = (float(ds["x1"]) - float(ds["x0"])) * 12; dd = float(ds.get("depth_in", 21)); rr = float(ds.get("rise_in", 7))
        rows = int(math.ceil(dd / 5.55))
        nb = sum(len(v) for v in pack_boards([("tread", wd + 1)] * rows + [("riser", wd + 1)] + [("end", dd + 1)] * 2, stocks=(12,)).values())
        lines.append(Line("Stairs", f"{brand} {coll} {color} 1x6x12 Square Edge — door step tread rows, riser and returns ({ftin(wd)} x {dd:g}\", {rr:g}\" rise)", nb, nb + 1, "ea", "+1", uc12, src12))
        n26 = int(math.ceil((2 * wd + (int(math.ceil(wd / 16)) + 1) * dd) * 1.1 / (12 * 12)))
        uc26, src26 = _lumber_price("2x6", 12)
        lines.append(Line("Stairs", f"2x6x12 #1 True Frame — door step box (rim + joists at 16\"), on the deck", n26, n26 + 1, "ea", "+1", uc26, src26))
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
        nb = sum(len(v) for v in pack_boards(pieces, stocks=(12,)).values())
        lines.append(Line("Planters", f"{brand} {coll} {color} 1x6x12 Square Edge — planter skin on all sides + picture-frame cap ({len(psegs)} planter{'s' if len(psegs) > 1 else ''}, {ftin(plf * 12)})", nb, nb + 1, "ea",
                          f"+1  ({len(pieces)} pieces packed into 12' boards)", uc12, src12))
        n24 = int(math.ceil((studs * 16 / 12 + plates_lf) / 8 * 1.1))
        lines.append(Line("Planters", "2x4x8 #2 PT — planter walls: studs 12\" OC, top and bottom plates, all treated", n24, n24 + 1, "ea", f"+1  ({studs} studs + {plates_lf:.0f} LF plates)", *P2X4))
        nos = int(math.ceil(osb_sf / 32 * 1.15))
        lines.append(Line("Planters", "7/16\" OSB 4x8 — planter sheathing (walls + bottom), under the deck-board skin", nos, nos, "sheet", f"{osb_sf:.0f} SF", 18.0, "est."))
        lines.append(Line("Planters", "Planter liner — 6-mil poly + drainage mat, stapled inside", 1, 1, "lot", "est.", 45.0, "est."))
        ncx = len(pieces) * 4
        lines.append(Line("Planters", f"Cortex for TimberTech, {color} plugs — planter skin and cap (350 ct)", -(-ncx // dcx["count"]), -(-ncx // dcx["count"]), "box", f"~{ncx} screws", dcx["each"], dcx["source"]))
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
    if spec.decking.fascia and Qz.fascia_pieces:
        packed_f = pack_lumber([("fascia", Lf, name) for name, Lf in Qz.fascia_pieces], kerf=0.125)
        nf = sum(n for (_, s_), (n, _) in packed_f.items())
        uc, src = _price("decking", f"{brand}|{coll}|fascia")
        if uc == 0.0:
            lf, src = _price("decking", "generic_fascia_per_lf"); uc = round(lf * 12, 2)
        fas = FASCIA[dkf["material"]]
        why = "+1  (" + " · ".join(f"{n} {ftin(Lf)}" for n, Lf in Qz.fascia_pieces) + ")"
        if spec.extras.hardie_skirt:
            hd = PRICEBOOK["cover"]["hardie_trim_4_4x12_12ft"]
            lines.append(Line("Fascia", f"Deck skirt — HardieTrim 4/4 x 12 x 12' smooth ColorPlus {spec.extras.hardie_skirt.split()[-2] + ' ' + spec.extras.hardie_skirt.split()[-1] if len(spec.extras.hardie_skirt.split()) > 1 else spec.extras.hardie_skirt} (wraps the double rim, in place of the composite fascia)", nf, nf + 1, "ea", why, hd["each"], hd["source"]))
            scr = int(-(-nf * 12 * 2 // 12)) * 2 + 20     # 2 screws per bearing point @ 12" plus corners
            hcol = " ".join(spec.extras.hardie_skirt.split()[-2:]) if len(spec.extras.hardie_skirt.split()) > 1 else spec.extras.hardie_skirt
            sc_ = PRICEBOOK["cover"]["hardie_trim_screws_100"]
            lines.append(Line("Fascia", sc_["desc"].replace("Timber Bark", hcol), -(-scr // 100), -(-scr // 100), "box", f"{scr} color-matched screws, pre-drilled, 2 per joist line", sc_["each"], sc_["source"]))
            tu = PRICEBOOK["cover"]["hardie_touchup"]
            lines.append(Line("Fascia", tu["desc"].replace("Timber Bark", hcol), 1, 1, "kit", "cut ends", tu["each"], tu["source"]))
        else:
            lines.append(Line("Fascia", f"{brand} {coll} Fascia {spec.decking.fascia_color or color} {fas['thick']:g}x{fas['width']:g}x12", nf, nf + 1, "ea", why, uc, src))
        for name, Lf in Qz.fascia_pieces:
            cuts.append(CutPiece(name.capitalize(), "fascia", Lf, 1, "flush under the board nose; full board at the front corners, short piece at the house"))
    elif not spec.decking.fascia:
        notes.append("no fascia — the rim is the finished edge under a 1-1/2\" board overhang" + (" (timber, end grain sealed)" if timber else ""))

    # ================= FASTENERS
    fsys = spec.decking.fastener_system or default_fastener_system(coll, spec.decking.profile)
    face = Qz.first_row + Qz.border_screws + Qz.fascia_screws
    stair_face = sum((st.tread_pieces + st.riser_pieces) * (st.stringers or int(math.ceil(st.width / 16.0)) + 1) * 2 for st in stairs)
    if fsys == "Camo EdgeClip":
        d = PRICEBOOK["decking"]["Camo_EdgeClip_90"]
        boxes = int(math.ceil(Qz.clips / d["count"]))
        lines.append(Line("Fasteners", "Camo EdgeClip 3/16\" 410SS Black 90 ct", boxes, boxes, "box", f"{Qz.clips} clips needed · {boxes * d['count']} supplied", d["each"], d["source"]))
        sched["Field"] = f"100% hidden — Camo EdgeClip 3/16\" at every joist in every gap ({Qz.bearing_points} bearing points x {Qz.gaps} gaps = {Qz.clips}); board ends clipped on the PF joists, never screwed"
    elif fsys == "CONCEALoc":
        d = PRICEBOOK["decking"]["CONCEALoc_500"]
        boxes = int(math.ceil(Qz.clips / d["count"]))
        lines.append(Line("Fasteners", "TimberTech CONCEALoc hidden fastener 500 ct (screws incl.)", boxes, boxes, "box", f"{Qz.clips} needed · {boxes * d['count']} supplied", d["each"], d["source"]))
        sched["Field"] = f"CONCEALoc at every joist in every gap ({Qz.clips})"
    elif fsys == "Cortex":
        rip_screws = sum(2 * (int(round(r / fr0.spacing)) + 2) for r in [0]) if not Qz.rip_strips else int(len(Qz.rip_strips) * 2 * (Qz.bearing_points / max(1, len(Qz.field_piece_note))))
        n = Qz.clips + rip_screws
        d = PRICEBOOK["decking"]["Cortex_TimberTech_350"]
        boxes = int(math.ceil(n / d["count"]))
        lines.append(Line("Fasteners", f"Cortex for TimberTech {dkf['material']}, {color} plugs (350 ct / 100 SF)", boxes, boxes, "box",
                          f"{n} screws  (2 per board at every bearing point" + (", rips included" if Qz.rip_strips else "") + f") · {boxes * d['count']} supplied", d["each"], d["source"]))
        if bcolor != color or Qz.border_screws:
            nb = Qz.border_screws
            bboxes = max(1, int(math.ceil(nb / d["count"])))
            lines.append(Line("Fasteners", f"Cortex for TimberTech {dkf['material']}, {bcolor} plugs — borders + dividers", bboxes, bboxes, "box", f"{nb} screws", d["each"], d["source"]))
        sched["Field"] = f"Cortex face screws with color-matched plugs: 2 per board at every joist and at both ends of every run, color-matched plugs ({n} field + {Qz.border_screws} border/divider)"
        face = 0; stair_face = 0
    else:
        n = Qz.clips
        d = PRICEBOOK["decking"]["CapTor_xd_350"]
        boxes = int(math.ceil((n + face + stair_face) / d["count"]))
        lines.append(Line("Fasteners", f"Starborn Cap-Tor xd 2-3/4\" Epoxy {color} 350 ct — face screwed field", boxes, boxes, "box", f"{n + face + stair_face} needed", d["each"], d["source"]))
        sched["Field"] = "face screwed, 2 per board at every joist"
        face = 0; stair_face = 0
    if (spec.decking.border_fastener or "") == "Cortex" and fsys != "Cortex" and (Qz.border_screws or stair_face):
        d = PRICEBOOK["decking"]["Cortex_TimberTech_350"]
        nb = Qz.border_screws + stair_face
        bboxes = max(1, int(math.ceil(nb / d["count"])))
        lines.append(Line("Fasteners", f"Cortex for TimberTech {dkf['material']}, {bcolor} plugs — picture frame, dividers and stair treads", bboxes, bboxes, "box",
                          f"{nb} screws  (border/divider {Qz.border_screws}" + (f" · stairs {stair_face}" if stair_face else "") + f") · {bboxes * d['count']} supplied", d["each"], d["source"]))
        sched["Picture frame + stairs"] = "Cortex face screws with color-matched plugs: borders and dividers 2 per bearing point, stair treads 2 per stringer per board"
        face -= Qz.border_screws; stair_face = 0
    if face + stair_face:
        d = PRICEBOOK["decking"]["CapTor_xd_350"]
        tot = face + stair_face
        boxes = max(1, int(math.ceil(tot / d["count"])))
        lines.append(Line("Fasteners", f"Starborn Cap-Tor xd 2-3/4\" Epoxy {color} 350 ct", boxes, boxes, "box",
                          f"{tot} screws needed  (first row {Qz.first_row} · border {0 if (spec.decking.border_fastener or '') == 'Cortex' else Qz.border_screws} · fascia {Qz.fascia_screws}" + (f" · stairs {stair_face}" if stair_face else "") + ")", d["each"], d["source"]))
        cx_b = (spec.decking.border_fastener or "") == "Cortex"
        sched["Face screws"] = ("Cap-Tor xd color-matched ONLY at: first row 1 per joist on the house edge · " + ("" if cx_b else "borders 2 per bearing point @ 16\" · ")
                                + "fascia 2 at each board end then alternate top/bottom every 12\", pre-drilled" + (" · stair treads 2 per stringer per board" if stairs and not cx_b else ""))

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
                d_ = d_.replace("{color}", rl.color)
                lines.append(Line("Rail", d_ if "Fulton Rail 8'" in d_ or "panel" in d_.lower() or " kit" in d_.lower() else f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" {kind} panel {rl.color}", n, n, "ea",
                                  f"exact  (cut to {' / '.join(cuts_txt)})", uc, src))
                if f"{sysn}|top_rail|{stock_in // 12}" in PRICEBOOK["rail"] and kind == "level":
                    # a top rail sold apart from the infill kit (Impression Rail Express: Modern / Classic profile)
                    d_, uc, src = _item("rail", f"{sysn}|top_rail|{stock_in // 12}")
                    lines.append(Line("Rail", d_.replace("{color}", rl.color), n, n, "ea", "exact  (one per bay, cut with its panel)", uc, src))
            if (timber or sysd.get("surface")) and f"{sysn}|post_kit" in PRICEBOOK["rail"]:
                d_, uc, src = _item("rail", f"{sysn}|post_kit")
                d_ = d_.replace("{color}", rl.color)
                n_sail = sum(len(sl.get("posts", [])) for sl in (spec.geometry.sails or []) if sl.get("mount") == "deck_rail")
                n_rp = len(rl.posts) - n_sail
                lines.append(Line("Rail", d_, n_rp, n_rp, "kit", f"exact  ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))}" + (f"; {n_sail} corner{' is the sail post' if n_sail == 1 else 's are the sail posts'}" if n_sail else "") + ")", uc, src))
            else:
                n_sail = sum(len(sl.get("posts", [])) for sl in (spec.geometry.sails or []) if sl.get("mount") == "deck_rail")
                for kind, n in sorted(pk.items()):
                    why = "exact"
                    if kind == "CORNER" and n_sail:
                        n, why = max(0, n - n_sail), f"exact  ({n_sail} corner{' is the sail post' if n_sail == 1 else 's are the sail posts'})"
                    if not n:
                        continue
                    uc, src = _price("rail", f"{sysn}|post|{kind}")
                    lines.append(Line("Rail", f"{rname} {sysd['post_w']:g}\" {kind} post {rl.height:g}\" {rl.color} w/ brackets, cap, skirt", n, n, "ea", why, uc, src))
        if spec.railing.drink_rail:
            dcoll = spec.railing.drink_rail_collection or bcoll
            dcolor = spec.railing.drink_rail_color or bcolor
            # board pieces per rail run (mitred at every turn), packed into 16' boards
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
            packed_d = pack_boards(pieces, stocks=(16,))
            nb = sum(len(v) for v in packed_d.values())
            uc, src = _price("decking", f"{spec.decking.brand}|{dcoll}|16|square")
            lines.append(Line("Rail", f"Drink rail — {spec.decking.brand} {dcoll} {dcolor} 1x6x16 Square Edge laid flat on the top rail, {rl.rail_lf} LF, mitred at every turn", nb, nb + 1, "ea", "+1  (full-board line only, never scalloped)", uc, src))
            d_, uc, src = _item("hardware", f"{sysn.lower()}_drink_rail_bracket_kit" if f"{sysn.lower()}_drink_rail_bracket_kit" in PRICEBOOK["hardware"] else "drink_rail_bracket_kit")
            lines.append(Line("Rail", d_, len(rl.sections), len(rl.sections), "kit", "exact  (one per bay)", uc, src))
        for st in stairs:
            sc = Counter(s_.panel_stock_in for s_ in st.stair_sections)
            for stock_in, n in sorted(sc.items()):
                if cable:
                    uc, src = _price("rail", f"{sysn}|stair_kit|{stock_in // 12}")
                    lines.append(Line("Stairs", f"{rname} stair cable rail kit {stock_in // 12}' ({st.side} stair)", n, n, "kit", "exact", uc, src))
                else:
                    uc, src = _price("rail", f"{sysn}|panel|{stock_in // 12}|stair")
                    lines.append(Line("Stairs", f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" STAIR panel {rl.color} ({st.side} stair)", n, n, "ea", "exact", uc, src))
            if st.stair_posts:
                uc, src = _price("rail", f"{sysn}|post|STAIR")
                lines.append(Line("Stairs", f"{rname} {sysd['post_w']:g}\" STAIR post {rl.color} w/ brackets, cap ({st.side} stair)", st.stair_posts, st.stair_posts, "ea",
                                  "exact  (top + bottom of each rail side" + (f", {len(st.geo.flights)} flights" if len(st.geo.flights) > 1 else "") + ")", uc, src))
            if st.landing_sections:
                lc = Counter(s_.panel_stock_in for s_ in st.landing_sections)
                for stock_in, n in sorted(lc.items()):
                    if cable:
                        uc, src = _price("rail", f"{sysn}|kit|{stock_in // 12}")
                        lines.append(Line("Stairs", f"{rname} level cable rail kit {stock_in // 12}' — landing guard ({st.side} stair, {st.landing_rail_lf:g} LF)", n, n, "kit", "exact", uc, src))
                    else:
                        uc, src = _price("rail", f"{sysn}|panel|{stock_in // 12}|level")
                        lines.append(Line("Stairs", f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" LEVEL panel {rl.color} — landing guard ({st.side} stair, {st.landing_rail_lf:g} LF)", n, n, "ea", "exact  (open sides of the landings)", uc, src))
                uc, src = _price("rail", f"{sysn}|post|{'CORNER' if 'CORNER' in RAIL_SYSTEMS.get(sysn, {}).get('post_types', []) else 'POST'}")
                lines.append(Line("Stairs", f"{rname} {sysd['post_w']:g}\" post {rl.color} w/ brackets, cap — landing guard ({st.side} stair)", st.landing_posts, st.landing_posts, "ea", "exact  (bay ends + turn corners)", uc, src))
            if st.geo.handrail_required and st.stair_rail_sides:
                uc, src = _price("rail", f"{sysn}|handrail_kit")
                lines.append(Line("Stairs", f"{sysn} graspable handrail kit ({st.side} stair)", 1, 1, "ea", "exact  (4+ risers — IRC R311.7.8)", uc, src))
        if spec.railing.post_size_in and rl:
            ps = spec.railing.post_size_in
            for l in lines:
                if l.category in ("Rail", "Stairs") and " post " in l.item and '2"' in l.item:
                    l.item = l.item.replace('2"', f'{ps:g}"')
                    l.note = (l.note + " · " if l.note else "") + f"{ps:g}\" post — confirm the SKU and price with {sysn} (priced at the stock post rate)"
        if not timber:
            uc, src = _price("rail", "touchup_paint")
            tu = "Rust-Oleum flat black touch-up (cut ends)" if "black" in (rl.color or "black").lower() else f"{rbrand} {rl.color} touch-up paint (cut ends)"
            lines.append(Line("Rail", tu, 1, 1, "ea", "exact", uc, src))
        n_sail_ = sum(len(sl.get("posts", [])) for sl in (spec.geometry.sails or []) if sl.get("mount") == "deck_rail")
        sched["Rail"] = (f"{sysn} {rl.height:g}\" — {len(rl.posts)} posts ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))})"
                         + (f"; the {n_sail_} front corners are the shade-sail posts, base-plated on the deck — the panels bracket to them" if n_sail_ else "")
                         + (f", {len(rl.sections)} bays at " + " / ".join(sorted(set(ftin(s_.ctc) for s_ in rl.sections))) + " CTC (8' kits cut to bay), posts on the divider lines, no bottom rail; HeadLOK 6\" x 4 per post" if cable
                            else " surface-mounted on the decking over a 2x blocking pair between the rim plies and the PF joist at every post, (4) HeadLOK 6\" per post through the base" if sysd.get("surface")
                            else " inside the outer rim ply, inner ply pocketed 2\" wide, (2) 7/16\" x 4-1/2\" bolts per post")
                         + (f"; drink rail board on {rbrand} drink-rail brackets, mitred at every turn" if spec.railing.drink_rail else ""))
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
    if spec.extras.demo_existing:
        sf_demo = spec.extras.demo_sf or L.deck_sf
        lines.append(Line("Site", "Demo existing deck + haul-off", sf_demo, sf_demo, "SF", "labor line — field verify the existing deck", 0.0, "labor"))
    for x in spec.extras.site_extras:
        lines.append(Line("Site", x.get("item", "site extra"), 1, 1, "ea", "at cost", float(x.get("cost", 0)), "at cost"))

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
        design_load=f"{max(z.frame.total_psf for z in L.zones):g} psf ({fr0.load_note})" + (" · engineered" if spec.extras.engineered else ""),
        decking=f"{brand} {coll} {color} — {Qz.field_rows} rows {'parallel to' if dk0.direction == 'parallel' else 'perpendicular to'} the house"
                + (f", picture frame{' & dividers' if L.divider_x else ''} in {bcoll} {bcolor}" if spec.geometry.picture_frame else "") + f", {ftin(spec.deck_gap)} gaps, {fsys}",
        rail=((spec.railing.parapet_note or "Existing stucco parapet stays — no rail in this scope") if spec.railing.existing_parapet else f"{rl.system} {rl.height:g}\" {rl.color}: {len(rl.sections)} bays, {len(rl.posts)} posts, {rl.rail_lf} LF" + (" + drink rail" if spec.railing.drink_rail else "") if rl else "none"),
        stairs=[f"{stair_name(ss, s_)}: {s_.geo.risers} risers @ {inches_frac(s_.geo.riser_in)}, {s_.geo.treads} tread{'s' if s_.geo.treads != 1 else ''}, "
                + (f"framed box, no stringers" if getattr(s_, 'build', '') == 'box' else f"{s_.stringers} stringers") + (", fascia skirts" if getattr(s_, 'skirts', False) and getattr(s_, 'build', '') != 'box' else "")
                + f", {ftin(s_.width)} wide"
                + (" — " + " + ".join(f"{fg.risers} risers" for fg in s_.geo.flights) + f" ({ss.turn})" if len(s_.geo.flights) > 1 else "")
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
        if st_.side.startswith("step:"):
            na, nb = st_.side.split(":")[1].split("-")
            zl = {z.name: (z.label.split(" — ")[0] if z.label else z.name) for z in spec.geometry.zones}
            pretty = f"{zl.get(nb, nb).lower()} side, toward the {zl.get(na, na).lower()}"
            for ln in lines:
                ln.item, ln.why = ln.item.replace(st_.side, pretty), ln.why.replace(st_.side, pretty)
            for c_ in cuts:
                c_.member = c_.member.replace(st_.side, pretty)
            summary["stairs"] = [x.replace(st_.side + ":", pretty + ":") for x in summary["stairs"]]
    t = Takeoff(spec, L, lines, cuts, sched, summary, notes, joist_lf, timber_sf)
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
    """Post centres along the low beam (ft, plan x), ≤ 8'-6" OC, 6" in from each end — or the owner's positions."""
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
        L_(None, 1, 1, "box", "color-matched trim screws", key="hardie_trim_screws_100")
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
