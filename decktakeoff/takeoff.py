"""Layout -> the takeoff: every line written the way Decks & Docks sells it, with NET (drawing count),
ORDER (PO quantity) and a one-line reason wherever they differ. Overage is explicit and small.

Quantities are accumulated across zones first (Q), then turned into lines once — so a three-zone deck gets one
cull per lumber length, not three. Two standards are encoded: dimensional (Jason Ct: 2x SYP, double rims, hangers
both ends, EdgeClips, Fulton) and timber (Eagle's Nest: 4x10 DF#1 on 6x12 / 8x8, caissons, Cortex, IRX)."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from . import engineering as eng
from .catalog import (DOUBLE_HANGER, FASCIA, H25_NAILS, HANGER_FOR_JOIST, HANGER_NAILS, LUMBER_STOCK_FT, POST_BASE, POST_BASE_SCREWS,
                      POST_CAP_SCREWS, PRICEBOOK, SPECIES_NAMES, TIMBER_BASE, actual, decking_facts, default_fastener_system, parse_beam,
                      RAIL_SYSTEMS)
from .layout import Layout, ZoneLayout, BeamLine, build_layout, LEDGER_T, RIM_PLY
from .spec import DeckSpec
from .units import ftin

CATEGORIES = ["Lumber", "Footings", "Hardware", "Flashing & waterproofing", "Decking", "Fasteners", "Fascia", "Rail", "Stairs", "Porch cover", "Finish", "Site"]
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


def _lumber_price(nominal: str, stock_ft: int, timber: bool = False):
    key = f"{nominal}_DF#1" if timber and f"{nominal}_DF#1" in PRICEBOOK["lumber"] else nominal
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
    flush_mid = [b for b in fr.beams if b.kind == "flush" and b.cl_y < z.D - 3]
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
    # ---- decking: field boards per run, rips, cortex per run
    runs = _field_runs(spec, L, z, zi) if L.multi else [(dk.rows, dk.field_len, z.name)]
    for n_rows, run_len, lab in runs:
        k = max(1, int(math.ceil(run_len / 240.0)))
        piece = run_len / k
        stock = next((s for s in (12, 16, 20) if piece <= s * 12 + 0.01), 20)
        Q_.field_boards[stock] += n_rows * k
        Q_.field_piece_note.append(f"{lab}: {n_rows} rows @ {ftin(piece)}" + (f" x {k}" if k > 1 else ""))
        Q_.cuts.append(CutPiece(f"Field boards run {lab}", f"{spec.decking.collection} {spec.decking.color}", piece, n_rows * k, "boards run parallel to the house" if dk.direction == "parallel" else "boards run out from the house"))
        # bearing points in this run: joists within + the two ends (rim/divider cluster)
        crossings = int(round(run_len / fr.spacing)) + 2
        if (spec.decking.fastener_system or default_fastener_system(spec.decking.collection, spec.decking.profile)) == "Cortex":
            Q_.clips += n_rows * crossings * 2
        else:
            Q_.clips += n_rows * crossings
        Q_.bearing_points += crossings
    Q_.field_rows += dk.rows
    if dk.last_row_dev < -0.5:
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
    cuts = Qz.cuts
    if Qz.front_flush:
        notes.append("front flush beam IS the front rim — joists hang into it, posts under it, no separate rim plies")
    # ---- multi-zone picture frame: outer border segmented at the dividers, end borders, dividers
    if L.multi and spec.geometry.picture_frame:
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
        Qz.lumber += [("2x12", st.geo.stringer_len_in, "stair stringer")] * st.stringers
        cuts.append(CutPiece(f"Stair stringers ({st.side})", "2x12", st.geo.stringer_len_in, st.stringers,
                             f"{st.geo.risers} risers @ {st.geo.riser_in:.3f}\" · {st.geo.treads} treads @ {st.geo.tread_in:.2f}\" · stringers {eng.STRINGER_OC_COMPOSITE:g}\" OC"))
        Qz.lumber += [("2x6", st.width + 3, "stair kicker/hanger board")] * 2
    # rail post blocks (timber / IRX: 10-1/2" blocks at every rail post)
    n_rail_posts = (len(rl.posts) if rl else 0) + sum(s.stair_posts for s in stairs)
    if rl and timber:
        Qz.lumber += [(jsize, 10.5, "rail post block")] * len(rl.posts)

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
    for (nom, st), (n, labels) in pack_lumber(beam_pieces).items():
        sp = spec.framing.beams[0].species if spec.framing.beams else "DF"
        uc, src = _lumber_price(nom, st, timber)
        desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if timber else SPECIES_NAMES.get(sp, sp)}"
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  ({_summarize_labels(labels)}: " + " · ".join(bl.label for bl in L.beam_lines) + ")", uc, src))
    for st_ in L.stairs:
        if st_.mid_support:
            post_pieces += [(spec.framing.post_size, zt_post := (st_.geo.total_rise_in / 2.0 + 6.0), "stair carrier post")] * 2
            cuts.append(CutPiece(f"Stair carrier posts ({st_.side})", spec.framing.post_size, st_.geo.total_rise_in / 2.0, 2, "under the stringers at mid-run — field-measure"))
            car = "2x6" if not timber else "4x6"
            uc, src = _lumber_price(car, 12, timber)
            lines.append(Line("Lumber", f"{car}x12 {'#1 KDAT' if not timber else 'DF #1'} — stair carrier (2 ply) + blocking between stringers at mid-run ({st_.side})", 3, 3, "ea",
                              f"exact  (2 ply x {ftin(st_.width + 6)} carrier + {st_.stringers - 1} blocks; 1 spare)", uc, src))
            cuts.append(CutPiece(f"Stair carrier ({st_.side})", car, st_.width + 6, 2, "2 ply, notched stringers bear on it; hurricane tie each stringer"))
    for (nom, st), (n, labels) in pack_lumber(post_pieces, short_stock_ft=8).items():
        uc, src = _lumber_price(nom, st, timber)
        desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if timber else '#2 GC'}"
        lens = sorted(set(ftin(bl.post_len) for bl in L.beam_lines))
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  (yields {n_posts} posts at ~{' / '.join(lens)})", uc, src))
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

    # ================= HARDWARE / CONNECTORS
    hanger = HANGER_FOR_JOIST.get(jsize, "LUS28Z")
    d_, uc, src, sku = _hw(hanger, black)
    n_flush = sum(1 for bl in L.beam_lines if bl.kind == "flush" and not bl.label.startswith("FRONT"))
    why = (f"exact  (joists at the ledgers + rim ends" + (f" + both faces of the flush beam" if n_flush else "") + ")") if timber \
        else f"exact  ({Qz.n_joists} joists x {Qz.hangers_single // max(1, Qz.n_joists)} ends)"
    lines.append(Line("Hardware", d_, Qz.hangers_single, Qz.hangers_single, "ea", why, uc, src, sku))
    if Qz.hangers_double:
        dh = DOUBLE_HANGER.get(jsize, "HUCQ210-2-SDS")
        d_, uc, src, sku = _hw(dh, black)
        lines.append(Line("Hardware", d_, Qz.hangers_double, Qz.hangers_double, "ea",
                          "exact  (doubled joists under the dividers, hung rims at the flush beam)" if timber else "exact  (2 side rims x 2 ends) — confirm stock", uc, src, sku))
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
            n_dtt = spec.framing.lateral_ties * (len(L.zones) if L.multi else 1)
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
        if timber or RAIL_SYSTEMS.get(rl.system, {}).get("cable"):
            d = PRICEBOOK["hardware"]["HeadLOK6_50"]
            need = 4 * n_rail_posts
            boxes = int(math.ceil(need / d["count"]))
            lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need} needed  ({n_rail_posts} rail posts x 4)", d["each"], d["source"]))
        else:
            nb = 2 * n_rail_posts
            d_, uc, src, sku = _hw("bolt_7/16x4.5", black)
            lines.append(Line("Hardware", d_, nb, nb + 2, "ea", f"+2  ({n_rail_posts} rail posts x 2)", uc, src))
    for st in stairs:
        d = PRICEBOOK["hardware"]["LSCZ"]
        lines.append(Line("Hardware", d["desc"], st.stringers, st.stringers, "ea", f"exact  ({st.side} stair, 1 per stringer at the rim)", d["each"], d["source"], "LSCZ"))
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
            sc_ = PRICEBOOK["cover"]["hardie_trim_screws_100"]
            lines.append(Line("Fascia", sc_["desc"], -(-scr // 100), -(-scr // 100), "box", f"{scr} color-matched screws, pre-drilled, 2 per joist line", sc_["each"], sc_["source"]))
            tu = PRICEBOOK["cover"]["hardie_touchup"]
            lines.append(Line("Fascia", tu["desc"], 1, 1, "kit", "cut ends", tu["each"], tu["source"]))
        else:
            lines.append(Line("Fascia", f"{brand} {coll} Fascia {spec.decking.fascia_color or color} {fas['thick']:g}x{fas['width']:g}x12", nf, nf + 1, "ea", why, uc, src))
        for name, Lf in Qz.fascia_pieces:
            cuts.append(CutPiece(name.capitalize(), "fascia", Lf, 1, "flush under the board nose; full board at the front corners, short piece at the house"))
    elif not spec.decking.fascia:
        notes.append("no fascia — the rim is the finished edge under a 1-1/2\" board overhang" + (" (timber, end grain sealed)" if timber else ""))

    # ================= FASTENERS
    fsys = spec.decking.fastener_system or default_fastener_system(coll, spec.decking.profile)
    face = Qz.first_row + Qz.border_screws + Qz.fascia_screws
    stair_face = sum(st.tread_pieces * st.stringers * 2 + st.riser_pieces * st.stringers * 2 for st in stairs)
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
    if face + stair_face:
        d = PRICEBOOK["decking"]["CapTor_xd_350"]
        tot = face + stair_face
        boxes = max(1, int(math.ceil(tot / d["count"])))
        lines.append(Line("Fasteners", f"Starborn Cap-Tor xd 2-3/4\" Epoxy {color} 350 ct", boxes, boxes, "box",
                          f"{tot} screws needed  (first row {Qz.first_row} · border {Qz.border_screws} · fascia {Qz.fascia_screws}" + (f" · stairs {stair_face}" if stair_face else "") + ")", d["each"], d["source"]))
        sched["Face screws"] = ("Cap-Tor xd color-matched ONLY at: first row 1 per joist on the house edge · borders 2 per bearing point @ 16\" · "
                                "fascia 2 at each board end then alternate top/bottom every 12\", pre-drilled" + (" · stair treads 2 per stringer per board" if stairs else ""))

    # ================= RAIL
    if rl:
        sysn = rl.system
        sysd = RAIL_SYSTEMS.get(sysn, RAIL_SYSTEMS["Fulton"])
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
                lines.append(Line("Rail", d_ if "Fulton Rail 8'" in d_ or "panel" in d_.lower() else f"{rname} Rail {stock_in // 12}' x {rl.height:g}\" {kind} panel {rl.color}", n, n, "ea",
                                  f"exact  (cut to {' / '.join(cuts_txt)})", uc, src))
            if timber and f"{sysn}|post_kit" in PRICEBOOK["rail"]:
                d_, uc, src = _item("rail", f"{sysn}|post_kit")
                lines.append(Line("Rail", d_, len(rl.posts), len(rl.posts), "kit", f"exact  ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))})", uc, src))
            else:
                for kind, n in sorted(pk.items()):
                    uc, src = _price("rail", f"{sysn}|post|{kind}")
                    lines.append(Line("Rail", f"{rname} 2\" {kind} post {rl.height:g}\" {rl.color} w/ brackets, cap, skirt", n, n, "ea", "exact", uc, src))
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
                lines.append(Line("Stairs", f"{rname} 2\" STAIR post {rl.color} w/ brackets, cap ({st.side} stair)", st.stair_posts, st.stair_posts, "ea", "exact  (top + bottom of each rail side)", uc, src))
            if st.geo.handrail_required and st.stair_rail_sides:
                uc, src = _price("rail", f"{sysn}|handrail_kit")
                lines.append(Line("Stairs", f"{sysn} graspable handrail kit ({st.side} stair)", 1, 1, "ea", "exact  (4+ risers — IRC R311.7.8)", uc, src))
        if spec.geometry.cover:
            lines += cover_lines(spec)
        if not timber:
            uc, src = _price("rail", "touchup_paint")
            lines.append(Line("Rail", "Rust-Oleum flat black touch-up (cut ends)", 1, 1, "ea", "exact", uc, src))
        sched["Rail"] = (f"{sysn} {rl.height:g}\" — {len(rl.posts)} posts ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))})"
                         + (f", {len(rl.sections)} bays at " + " / ".join(sorted(set(ftin(s_.ctc) for s_ in rl.sections))) + " CTC (8' kits cut to bay), posts on the divider lines, no bottom rail; HeadLOK 6\" x 4 per post" if cable
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

    # ================= SITE
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
        posts=f"{n_posts} x {spec.framing.post_size} on " + (
            fr0.footing_model if ft == "diamond_pier" else f"{int(fr0.footing_dia_in)}\" {'caissons' if ft == 'caisson' else 'concrete piers'} {ftin(fr0.footing_depth_in)} deep") + (" with stone column bases" if spec.extras.stone_bases else ""),
        design_load=f"{max(z.frame.total_psf for z in L.zones):g} psf ({fr0.load_note})" + (" · engineered" if spec.extras.engineered else ""),
        decking=f"{brand} {coll} {color} — {Qz.field_rows} rows {'parallel to' if dk0.direction == 'parallel' else 'perpendicular to'} the house"
                + (f", picture frame{' & dividers' if L.divider_x else ''} in {bcoll} {bcolor}" if spec.geometry.picture_frame else "") + f", {ftin(spec.deck_gap)} gaps, {fsys}",
        rail=("Existing stucco parapet stays — no rail in this scope" if spec.railing.existing_parapet else f"{rl.system} {rl.height:g}\" {rl.color}: {len(rl.sections)} bays, {len(rl.posts)} posts, {rl.rail_lf} LF" + (" + drink rail" if spec.railing.drink_rail else "") if rl else "none"),
        stairs=[f"{s_.side}: {s_.geo.risers} risers @ {s_.geo.riser_in:.2f}\", {s_.geo.treads} treads, {s_.stringers} stringers, {ftin(s_.width)} wide" for s_ in stairs],
        material_cost=round(sum(l.ext for l in lines), 2),
    )
    return Takeoff(spec, L, lines, cuts, sched, summary, notes, joist_lf, timber_sf)



def cover_size(spec) -> Tuple[float, float, float]:
    """(along the house ft, out from the house ft, roof area SF) of the porch cover rectangle [x0, x1, y0, y1, slope]."""
    c = spec.geometry.cover
    x0, x1, y0, y1 = c[:4]
    slope = c[4] if len(c) > 4 else "+y"
    along = (y1 - y0) if slope in ("+x", "-x") else (x1 - x0)
    out = (x1 - x0) if slope in ("+x", "-x") else (y1 - y0)
    return along, out, along * (out + 1.5)


def cover_lines(spec) -> List[Line]:
    """Porch cover over the deck: shed roof, ledger on the house, 2x8 rafters @ 16", (2)2x10 beam on 6x6 cedar posts at the rail line,
    OSB, underlayment, then architectural shingles + drip edge OR a standing seam steel roof (24 ga snap-lock panels on high-temp
    underlayment, eave / rake / headwall trims, snow retention bar), 5" K gutter + downspouts when asked, T&G or Hardie ceiling.
    Every price is an estimate until D&D / the metal supplier quotes it."""
    import math as _m
    along, out, area = cover_size(spec)
    out_lines: List[Line] = []
    def L_(item, net, order, unit, why, key=None, section="cover", per=None):
        if key:
            d_ = PRICEBOOK[section][key]; uc, src = d_["each"], d_.get("source", "est.")
            item = item or d_.get("desc", key)
        else:
            uc, src = per, "est."
        out_lines.append(Line("Porch cover", item, net, order, unit, why, uc, src))
    n_posts = max(2, int(_m.ceil(along / 8.5)) + 1)
    post_len = 10
    L_(f"6x6 x {post_len}' Western red cedar post (cover)", n_posts, n_posts, "ea", f"exact  ({n_posts} posts at the rail line, ≤ 8'-6\" OC)", per=PRICEBOOK["cover"]["cedar_6x6_lf"]["each"] * post_len)
    beam_pcs = int(_m.ceil(along / 16)) * 2
    L_(f"2x10x16 #1 SYP — cover beam (2 ply)", beam_pcs, beam_pcs, "ea", f"+0  ((2)2x10 x {along:.1f}' at the posts)", per=PRICEBOOK["lumber"]["2x10"]["per_lf"] * 16)
    ledger_pcs = int(_m.ceil(along / 16))
    L_(f"2x10x16 #1 SYP — cover ledger on the house", ledger_pcs, ledger_pcs, "ea", "exact", per=PRICEBOOK["lumber"]["2x10"]["per_lf"] * 16)
    n_r = int(along / (16 / 12)) + 1
    r_len = 12 if out + 1.5 <= 12 else 14
    L_(f"2x8x{r_len} #1 SYP — cover rafters @ 16\" OC", n_r, n_r + 1, "ea", f"+1 cull  ({n_r} rafters, {out + 1.5:.1f}' with the overhang)", per=PRICEBOOK["lumber"]["2x8"]["per_lf"] * r_len)
    fascia_lf = along + 2 * (out + 1.5)
    fpcs = int(_m.ceil(fascia_lf / 16))
    L_(f"2x8x16 #1 SYP — cover fascia / sub-fascia", fpcs, fpcs + 1, "ea", f"+1  ({fascia_lf:.0f} LF)", per=PRICEBOOK["lumber"]["2x8"]["per_lf"] * 16)
    sheets = int(_m.ceil(area / 32 * 1.1))
    L_(None, sheets, sheets, "sheet", f"{area:.0f} SF + 10% cuts", key="osb_7_16_sheet")
    ss = spec.extras.cover_roof.lower().startswith("standing")
    if not ss:
        L_(None, 1, 1, "roll", f"{area:.0f} SF", key="underlayment_roll")
    if ss:
        color = spec.extras.cover_roof_color or "color TBD"
        panel_len = out + 1.5
        n_panels = int(_m.ceil(along / (16 / 12)))
        L_(f"Standing seam roof — 24 ga steel 16\" snap-lock panels x {panel_len:.1f}' ({color}, PVDF), {n_panels} panels", round(area), round(area * 1.05), "SF", f"{n_panels} panels x {panel_len:.1f}' + 5% (one-piece eave to headwall, no end laps)", key="ss_panel_sf")
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
        L_(f"Cover fascia + rakes — HardieTrim 4/4 x 7-1/4 x 12' rustic ColorPlus {spec.extras.cover_fascia.split()[-2]} {spec.extras.cover_fascia.split()[-1]} over the 2x8 sub-fascia", nfb, nfb + 1, "ea", f"+1  ({fascia_lf:.0f} LF: front {along:.0f}' + two rakes {out + 1.5:.1f}')", key="hardie_trim_4_4x7_25_rustic_12ft")
        L_(None, 1, 1, "box", "color-matched trim screws", key="hardie_trim_screws_100")
    L_(None, n_posts, n_posts, "ea", "exact", key="post_base_6x6")
    L_(None, n_posts, n_posts, "ea", "exact", key="post_cap_6x6")
    L_(None, n_r, n_r, "ea", "one per rafter at the beam", key="rafter_tie")
    lok = int(_m.ceil(along / 16 * 2)) * 16 // 16 * 2
    L_("FastenMaster LedgerLOK 6\" — cover ledger, 2 rows staggered 16\" OC", int(_m.ceil(along / 16 * 12 * 2)), int(_m.ceil(along / 16 * 12 * 2)), "ea", f"{along:.0f} LF x 2 rows @ 16\"", per=PRICEBOOK["hardware"]["LedgerLOK6_50"]["each"] / 50 if "each" in PRICEBOOK["hardware"]["LedgerLOK6_50"] else 1.2)
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
