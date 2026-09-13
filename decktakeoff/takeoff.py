"""Layout -> the takeoff: every line written the way Decks & Docks sells it, with NET (drawing count),
ORDER (PO quantity) and a one-line reason wherever they differ. Overage is explicit and small.

Quantities are accumulated across zones first (Q), then turned into lines once — so a three-zone deck gets one
cull per lumber length, not three."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from . import engineering as eng
from .catalog import (DOUBLE_HANGER, FASCIA, H25_NAILS, HANGER_FOR_JOIST, HANGER_NAILS, LUMBER_STOCK_FT, POST_BASE, POST_BASE_SCREWS,
                      POST_CAP_SCREWS, PRICEBOOK, RISER, SPECIES_NAMES, TIMBER_BASE, TIMBER_BEAM_TIE, actual, decking_facts,
                      default_fastener_system, parse_beam, RAIL_SYSTEMS)
from .layout import Layout, ZoneLayout, build_layout, LEDGER_T, RIM_PLY
from .spec import DeckSpec
from .units import ftin

CATEGORIES = ["Lumber", "Footings", "Hardware", "Flashing & waterproofing", "Decking", "Fasteners", "Fascia", "Rail", "Stairs", "Finish", "Site"]


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


def _summarize_labels(labels: List[str]) -> str:
    cnt = Counter(labels)
    return " · ".join(f"{v} {k}" if v > 1 else k for k, v in cnt.items())


def _hw(key: str, black: bool) -> Tuple[str, float, str, str]:
    """hardware line: returns (desc, unit cost, source, sku) — black powder-coat variant when the job calls for it."""
    k = f"{key}_black" if black and f"{key}_black" in PRICEBOOK["hardware"] else key
    d = PRICEBOOK["hardware"].get(k) or PRICEBOOK["footings"].get(k) or {"desc": f"Simpson {key}", "each": 0.0, "source": "no price on file"}
    return d.get("desc", f"Simpson {key}"), float(d.get("each", 0.0)), d.get("source", ""), key


# ------------------------------------------------------------------ quantities across zones
@dataclass
class Q:
    lumber: List[Tuple[str, float, str]] = field(default_factory=list)
    beams: List[Tuple[str, float, str]] = field(default_factory=list)
    posts: List[Tuple[str, float, str]] = field(default_factory=list)
    cuts: List[CutPiece] = field(default_factory=list)
    n_joists: int = 0
    hangers_single: int = 0
    hangers_double: int = 0
    h25: int = 0
    timber_ties: int = 0
    ledger_len: float = 0.0
    ledger_fasteners: int = 0
    ledger_rule: str = ""
    n_posts: int = 0
    post_len: float = 0.0
    caps: Counter = field(default_factory=Counter)
    footing_load: float = 0.0
    footing_cap: float = 0.0
    footing_dia: float = 0.0
    footing_depth: float = 0.0
    n_blocks: int = 0
    block_rows: int = 0
    rss_lam: int = 0
    tape2: float = 0.0
    tape4: float = 0.0
    wall_lf: float = 0.0
    field_boards: Counter = field(default_factory=Counter)      # stock_ft -> boards
    field_rows: int = 0
    field_piece_note: List[str] = field(default_factory=list)
    border_pieces: List[Tuple[str, float]] = field(default_factory=list)
    divider_pieces: List[Tuple[str, float]] = field(default_factory=list)
    fascia_pieces: List[Tuple[str, float]] = field(default_factory=list)
    clips: int = 0
    bearing_points: int = 0
    gaps: int = 0
    first_row: int = 0
    border_screws: int = 0
    fascia_screws: int = 0
    deck_sf: float = 0.0
    timber_ends: int = 0
    timber_sf: float = 0.0
    tub_joists: List[Tuple[str, float, str]] = field(default_factory=list)
    front_flush: bool = False
    n_zones: int = 0


def accumulate(Q_: Q, spec: DeckSpec, z: ZoneLayout, dk_material: str) -> None:
    fr, dk = z.frame, z.decking
    tag = f" ({z.name})" if Q_.n_zones > 1 or spec.geometry.zones else ""
    jsize = fr.joist_size
    jb, jd = actual(jsize)
    timber = spec.is_timber
    lsize = spec.ledger_size
    n_field, n_pf = len(fr.joist_x), len(fr.pf_x)
    Q_.n_joists += n_field + n_pf
    # ---- joists
    if fr.joist_bays == 1:
        Q_.lumber += [(jsize, fr.joist_len, "field joist")] * n_field + [(jsize, fr.joist_len, "PF joist")] * n_pf
        Q_.cuts.append(CutPiece(f"Field joists{tag}", jsize, fr.joist_len, n_field, f"@ {fr.spacing:g}\" OC, crown up"))
        if n_pf:
            Q_.cuts.append(CutPiece(f"Picture-frame joists{tag}", jsize, fr.joist_len, n_pf, f"centre {ftin(fr.pf_x[0])} from each frame face"))
    else:
        rear_t = jb if fr.ledger else fr.rim_plies * jb
        sup = [rear_t] + [b.cl_y for b in fr.beams if b.kind == "flush" and b.cl_y < z.D - 3] + [z.D - fr.rim_plies * jb]
        for a, b in zip(sup, sup[1:]):
            ln = b - a - (1.5 if a > 2 else 0)
            Q_.lumber += [(jsize, ln, "joist")] * (n_field + n_pf)
            Q_.cuts.append(CutPiece(f"Joists (bay){tag}", jsize, ln, n_field + n_pf, f"bay {ftin(a)} to {ftin(b)}"))
    # ---- rims / ledger
    side_len = fr.joist_len
    for side in ("left", "right"):
        Q_.lumber += [(jsize, side_len, f"{side} rim ply")] * fr.rim_plies
    Q_.cuts.append(CutPiece(f"Side rim plies{tag}", jsize, side_len, 2 * fr.rim_plies,
                            f"{fr.rim_plies}-ply, laminated on the ground with RSS 2 rows @ 12\" staggered" if fr.rim_plies > 1 else "single 4x rim, hung in HU hangers"))
    front_flush = any(b.label.startswith("FRONT FLUSH") for b in fr.beams)
    Q_.front_flush = Q_.front_flush or front_flush
    if not front_flush:
        Q_.lumber += [(jsize, z.W, "front rim ply")] * fr.rim_plies
        Q_.cuts.append(CutPiece(f"Front rim plies{tag}", jsize, z.W, fr.rim_plies, "inner ply takes the hangers; outer ply laminated after" if fr.rim_plies > 1 else "single 4x rim"))
    if fr.ledger:
        Q_.lumber.append((lsize, z.W, "ledger"))
        Q_.cuts.append(CutPiece(f"Ledger{tag}", lsize, z.W, 1, "top at deck height less board thickness; membrane behind, flashing over"))
        Q_.ledger_len += z.W
        n_ll, rule = eng.ledger_fastener_count(z.W, fr.beams[0].back_span if fr.beams else fr.joist_len, spec.framing.ledger_fastener)
        Q_.ledger_fasteners += n_ll
        Q_.ledger_rule = rule
        Q_.wall_lf += z.W
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
                                f"{n_block_rows} row{'s' if n_block_rows > 1 else ''} — over the beam" + (" + mid-span (PVC)" if n_block_rows > 1 else "") + ", staggered up/down"))
    if spec.geometry.picture_frame and spec.geometry.board_direction != "parallel":
        Q_.lumber += [(jsize, fr.block_len, "PF blocking")] * (n_field + 1)
        Q_.cuts.append(CutPiece(f"Picture-frame blocking{tag}", jsize, fr.block_len, n_field + 1, "row behind the front rim so the front border ends bear"))
    # ---- hot-tub bay: doubled joists across the bay
    if z.hot_tub and spec.extras.hot_tub:
        bay = spec.extras.hot_tub_bay_in
        n_extra = int(math.floor(bay / fr.spacing)) + 1
        Q_.tub_joists += [(jsize, fr.joist_len, "tub bay doubling")] * n_extra
        Q_.cuts.append(CutPiece(f"Hot-tub bay doubling{tag}", jsize, fr.joist_len, n_extra, f"sister a joist to each joist across the {ftin(bay)} bay against the house"))
    # ---- beams / posts
    for b in fr.beams:
        plies, nom, bw, bd = parse_beam(b.size)
        max_stock = LUMBER_STOCK_FT.get(nom, [20])[-1] * 12
        k = max(1, int(math.ceil(b.length / max_stock)))
        seg = b.length / k
        splice = f"; {k} pieces of {ftin(seg)}, splices over posts, staggered ply to ply" if k > 1 else ""
        Q_.beams += [(nom, seg, f"{b.kind} beam")] * (plies * k)
        Q_.cuts.append(CutPiece(f"{b.label} beam{tag}", nom, seg, plies * k, f"CL {ftin(b.cl_y)} from house; posts at " + " / ".join(ftin(x) for x in b.posts_x) + splice))
        Q_.caps[b.cap] += len(b.posts_x)
        Q_.timber_sf += plies * 2 * (bw + bd) / 12 * b.length / 12 if timber else 0
    Q_.posts += [(fr.post_size, fr.post_len + 1.0, "post")] * fr.n_posts
    Q_.cuts.append(CutPiece(f"Posts{tag}", fr.post_size, fr.post_len, fr.n_posts, "field-measure each; beam top = joist bottom"))
    Q_.n_posts += fr.n_posts
    Q_.post_len = max(Q_.post_len, fr.post_len)
    Q_.footing_load = max(Q_.footing_load, fr.footing_load_lb)
    Q_.footing_cap = fr.footing_capacity_lb
    Q_.footing_dia = max(Q_.footing_dia, fr.footing_dia_in)
    Q_.footing_depth = max(Q_.footing_depth, fr.footing_depth_in)
    # ---- connectors
    Q_.hangers_single += fr.hangers_single
    Q_.hangers_double += fr.hangers_double
    if timber:
        Q_.timber_ties += 2 * sum((n_field + n_pf) for b in fr.beams if b.kind == "drop")
    else:
        Q_.h25 += fr.h25_ties
    lam = 0
    if fr.rim_plies > 1:
        lam += 2 * 2 * (int(math.ceil(side_len / 12)) + 1)
        lam += 2 * (int(math.ceil(z.W / 12)) + 1) * (fr.rim_plies - 1) * (0 if front_flush else 1)
        if not fr.ledger:
            lam += 2 * (int(math.ceil(z.W / 12)) + 1)
    for b in fr.beams:
        if b.plies > 1:
            lam += 2 * (int(math.ceil(b.length / 12)) + 1) * (b.plies - 1)
    Q_.rss_lam += lam
    # ---- tape
    Q_.tape2 += (n_field + n_pf) * fr.joist_len + fr.n_blocks_per_row * n_block_rows * fr.block_len + (z.W if fr.ledger else 0)
    Q_.tape4 += 2 * side_len + z.W * (1 if fr.ledger else 2) + sum(b.length for b in fr.beams if b.kind == "drop")
    # ---- timber surface / ends
    if timber:
        pieces_here = (n_field + n_pf) + 2 * fr.rim_plies + (0 if front_flush else fr.rim_plies) + (1 if fr.ledger else fr.rim_plies) + fr.n_blocks_per_row * n_block_rows
        Q_.timber_ends += 2 * pieces_here + 2 * sum(len(b.posts_x) for b in fr.beams) + 2 * len(fr.beams)
        Q_.timber_sf += ((n_field + n_pf) * fr.joist_len + 2 * side_len + z.W * 2) * 2 * (jb + jd) / 144
        pb_, pd_ = actual(fr.post_size)
        Q_.timber_sf += fr.n_posts * 4 * pb_ / 12 * fr.post_len / 12
    # ---- decking
    Q_.field_rows += dk.rows
    Q_.field_boards[dk.stock_ft] += dk.rows * dk.row_pieces
    Q_.field_piece_note.append(f"{z.name}: {dk.rows} rows" + (f" x {dk.row_pieces} pieces" if dk.row_pieces > 1 else "") + f" @ {ftin(dk.piece_len)}")
    Q_.cuts.append(CutPiece(f"Field boards{tag}", f"{spec.decking.collection} {spec.decking.color}", dk.piece_len, dk.rows * dk.row_pieces,
                            f"{dk.rows} rows, boards run {'parallel to' if dk.direction == 'parallel' else 'out from'} the house"))
    Q_.border_pieces += [(f"{n}{tag}", Lb) for n, Lb in dk.border_pieces]
    Q_.fascia_pieces += [(f"{n}{tag}", Lb) for n, Lb in dk.fascia_pieces]
    Q_.clips += dk.clips
    Q_.bearing_points += dk.bearing_points
    Q_.gaps += dk.gaps
    Q_.first_row += dk.first_row_screws
    Q_.border_screws += dk.border_screws
    Q_.fascia_screws += dk.fascia_screws
    Q_.deck_sf += dk.deck_w * dk.deck_d / 144.0


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

    Qz = Q(n_zones=len(L.zones))
    for z in L.zones:
        accumulate(Qz, spec, z, dkf["material"])
    cuts = Qz.cuts
    if Qz.front_flush:
        notes.append("front flush beam IS the front rim — joists hang into it, posts under it, no separate rim plies")
    # multi-zone: the picture frame follows the outline (every outer edge, one piece), and one divider per zone boundary
    if L.multi and spec.geometry.picture_frame:
        Qz.border_pieces = [(f"border {e.name}", e.length + 2 * dk0.fascia_t) for e in L.edges]
        Qz.border_screws = sum(2 * (int(math.floor(e.length / 16)) + 2) for e in L.edges)
        if spec.decking.dividers:
            for a, b in zip(L.zones, L.zones[1:]):
                Ld = min(a.wall_y + a.D, b.wall_y + b.D) - max(a.wall_y, b.wall_y)
                Qz.divider_pieces.append((f"divider {a.name}/{b.name}", Ld))
    # stairs lumber
    for st in stairs:
        Qz.lumber += [("2x12", st.geo.stringer_len_in, "stair stringer")] * st.stringers
        cuts.append(CutPiece(f"Stair stringers ({st.side})", "2x12", st.geo.stringer_len_in, st.stringers,
                             f"{st.geo.risers} risers @ {st.geo.riser_in:.3f}\" · {st.geo.treads} treads @ {st.geo.tread_in:.2f}\" · stringers {eng.STRINGER_OC_COMPOSITE:g}\" OC"))
        Qz.lumber += [("2x6", st.width + 3, "stair kicker/hanger board")] * 2

    # ================= LUMBER
    packed = pack_lumber(Qz.lumber + Qz.tub_joists)
    packed_beam = pack_lumber(Qz.beams)
    packed_post = pack_lumber(Qz.posts, short_stock_ft=8)
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
    for (nom, st), (n, labels) in packed_beam.items():
        sp = spec.framing.beams[0].species if spec.framing.beams else "DF"
        uc, src = _lumber_price(nom, st, timber)
        desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if timber else SPECIES_NAMES.get(sp, sp)}"
        beams_txt = " · ".join(f"{b.label}{' (' + z.name + ')' if L.multi else ''} {ftin(b.length)}" for z in L.zones for b in z.frame.beams if parse_beam(b.size)[1] == nom)
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  ({_summarize_labels(labels)}: {beams_txt})", uc, src))
    for (nom, st), (n, labels) in packed_post.items():
        uc, src = _lumber_price(nom, st, timber)
        desc = f"{nom}x{st} {SPECIES_NAMES['DF#1'] if timber else '#2 GC'}"
        lines.append(Line("Lumber", desc, n, n, "ea", f"exact  (yields {Qz.n_posts} posts at ~{ftin(Qz.post_len)})", uc, src))

    # ================= FOOTINGS
    ft = spec.framing.footing_type
    n_posts = Qz.n_posts
    if ft == "diamond_pier":
        model = fr0.footing_model
        uc, src = _price("footings", model)
        lines.append(Line("Footings", _desc("footings", model, f"Diamond Pier {model}"), n_posts, n_posts, "ea", "exact — confirm stock", uc, src, model,
                          f"{Qz.footing_load:,.0f} lb per post vs {Qz.footing_cap:,.0f} lb allowable"))
        base = POST_BASE.get(spec.framing.post_size, {}).get("diamond_pier", "ABA66Z")
        uc, src = _price("footings", base)
        lines.append(Line("Footings", _desc("footings", base, base) + " on the pier bolt", n_posts, n_posts, "ea", "exact", uc, src, base))
        base_screws = n_posts * POST_BASE_SCREWS.get(base, 12)
    elif ft == "caisson":
        dia, depth = Qz.footing_dia, Qz.footing_depth
        vol_cf = math.pi * (dia / 24) ** 2 * (depth / 12)
        cy = vol_cf * n_posts / 27
        lines.append(Line("Footings", f"Drilled caisson {int(dia)}\" x {ftin(depth)} with rebar (frost {ftin(spec.site.frost_depth_in)}) — auger, cage, pour", n_posts, n_posts, "ea", "exact — per stamped set",
                          0.0, "labor", note=f"{Qz.footing_load:,.0f} lb per post vs ~{Qz.footing_cap:,.0f} lb (end bearing + skin friction estimate)"))
        uc, src = _price("footings", "caisson_rebar_set")
        lines.append(Line("Footings", _desc("footings", "caisson_rebar_set", "caisson rebar"), n_posts, n_posts, "set", "exact", uc, src))
        uc, src = _price("footings", "concrete_cy")
        cyo = math.ceil(cy * 4 + 1) / 4
        lines.append(Line("Footings", _desc("footings", "concrete_cy", "ready-mix"), round(cy, 2), cyo, "cy", f"{vol_cf:.1f} cf per caisson + 1/4 cy waste", uc, src))
        base = TIMBER_BASE.get(spec.framing.post_size, "ABU66Z") if timber else POST_BASE.get(spec.framing.post_size, {}).get("concrete", "ABU66Z")
        d_, uc, src, sku = _hw(base, black)
        lines.append(Line("Footings", d_ + " wet-set / epoxy anchor", n_posts, n_posts, "ea", "exact", uc, src, sku))
        base_screws = n_posts * POST_BASE_SCREWS.get(base, 12)
    else:
        dia, depth = Qz.footing_dia, Qz.footing_depth
        vol_cf = math.pi * (dia / 24) ** 2 * (depth / 12)
        bags = int(math.ceil(vol_cf / 0.6)) * n_posts
        tube = f"sonotube_{int(dia)}" if f"sonotube_{int(dia)}" in PRICEBOOK["footings"] else "sonotube_12"
        uc, src = _price("footings", tube)
        lines.append(Line("Footings", f"{int(dia)}\" form tube x {ftin(depth)} (bearing {ftin(depth - 6)} below grade, frost {ftin(spec.site.frost_depth_in)})", n_posts, n_posts, "ea", "exact", round(uc * depth / 12, 2), src,
                          note=f"{Qz.footing_load:,.0f} lb per post on {spec.site.soil_bearing_psf:,.0f} psf soil"))
        uc, src = _price("footings", "concrete_80lb")
        lines.append(Line("Footings", "Concrete mix 80 lb", bags, bags + 2, "bag", f"+2  ({vol_cf:.1f} cf per pier)", uc, src))
        base = POST_BASE.get(spec.framing.post_size, {}).get("concrete", "ABU66Z")
        uc, src = _price("footings", base)
        lines.append(Line("Footings", _desc("footings", base, base) + " wet-set 1/2\" anchor", n_posts, n_posts, "ea", "exact", uc, src, base))
        base_screws = n_posts * POST_BASE_SCREWS.get(base, 12)
    if spec.extras.stone_bases:
        uc, src = _price("footings", "stone_base_kit")
        lines.append(Line("Footings", _desc("footings", "stone_base_kit", "stone column base"), n_posts, n_posts, "ea", "exact  (one per post)", uc, src))
    for st in stairs:
        if st.landing == "concrete pad":
            uc, src = _price("footings", "concrete_pad")
            lines.append(Line("Footings", f"Stair landing pad ({st.side} stair) — 4\" slab, stringers bear on the pad", 1, 1, "ea", "exact", uc, src))

    # ================= HARDWARE / CONNECTORS
    hanger = HANGER_FOR_JOIST.get(jsize, "LUS28Z")
    d_, uc, src, sku = _hw(hanger, black)
    ends = Qz.hangers_single // max(1, Qz.n_joists)
    lines.append(Line("Hardware", d_, Qz.hangers_single, Qz.hangers_single, "ea",
                      f"exact  ({Qz.n_joists} joists x {ends} ends" + (" + rim ends" if timber else "") + ")", uc, src, sku))
    if Qz.hangers_double:
        dh = DOUBLE_HANGER.get(jsize, "HUCQ210-2-SDS")
        d_, uc, src, sku = _hw(dh, black)
        lines.append(Line("Hardware", d_, Qz.hangers_double, Qz.hangers_double, "ea", "exact  (2 side rims x 2 ends) — confirm stock", uc, src, sku))
    nh, nj = HANGER_NAILS.get(hanger, (6, 4))
    n_long = Qz.hangers_single * nh
    n_short = Qz.hangers_single * nj + Qz.h25 * H25_NAILS + Qz.timber_ties * 12
    long_key = "nail_16d_5lb" if hanger.startswith("HU") else "nail_3in_5lb"
    if timber:
        n_long += 6 * Qz.n_blocks          # blocking toe-nails
    for key, need in ((long_key, n_long), ("nail_1.5in_5lb", n_short)):
        d = PRICEBOOK["hardware"][key]
        boxes = max(1, int(math.ceil(need / d["count"])))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need} needed of ~{boxes * d['count']}", d["each"], d["source"], key))
    if Qz.ledger_len:
        lf = spec.framing.ledger_fastener.lower()
        if lf.startswith("ledgerlok"):
            d = PRICEBOOK["hardware"]["LedgerLOK_50"]
            boxes = int(math.ceil(Qz.ledger_fasteners / d["count"]))
            lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{Qz.ledger_fasteners} needed", d["each"], d["source"], "LedgerLOK"))
        elif "bolt" in lf:
            key = "bolt_1/2x6" if jb > 2 else "bolt_1/2x8"
            d_, uc, src, sku = _hw(key, black)
            lines.append(Line("Hardware", d_, Qz.ledger_fasteners, Qz.ledger_fasteners + 2, "ea", "+2", uc, src, sku))
        else:
            d = PRICEBOOK["hardware"]["lag_1/2x4"]
            lines.append(Line("Hardware", d["desc"], Qz.ledger_fasteners, Qz.ledger_fasteners + 2, "ea", "+2", d["each"], d["source"]))
        sched["Ledger"] = f"{spec.ledger_size} ledger x {ftin(Qz.ledger_len)} total · {Qz.ledger_rule} · {Qz.ledger_fasteners} fasteners"
        n_dtt = spec.framing.lateral_ties * (len(L.zones) if L.multi else 1)
        d = PRICEBOOK["hardware"]["DTT1Z"]
        lines.append(Line("Hardware", d["desc"], n_dtt, n_dtt, "ea", "exact  (2 near each end of every ledger, into house floor framing)", d["each"], d["source"], "DTT1Z"))
    if Qz.h25:
        d = PRICEBOOK["hardware"]["H2.5AZ"]
        lines.append(Line("Hardware", d["desc"], Qz.h25, Qz.h25, "ea", f"exact  ({Qz.n_joists} joists + 2 rims at each drop beam)", d["each"], d["source"], "H2.5AZ"))
    if Qz.timber_ties:
        d_, uc, src, sku = _hw(TIMBER_BEAM_TIE, black)
        lines.append(Line("Hardware", d_, Qz.timber_ties, Qz.timber_ties, "ea", "exact  (2 per joist at every beam — engineer may substitute)", uc, src, sku))
    sd_screws = base_screws
    for cap, n in Qz.caps.items():
        d_, uc, src, sku = _hw(cap, black)
        is_4x = all(parse_beam(b.size)[1].startswith(("4x", "6x", "8x")) for z in L.zones for b in z.frame.beams)
        why = "exact" if timber or not cap.startswith("BC46Z") or is_4x else "exact — (2)2x beam in a 4x cap needs a 1/2\" shim; confirm cap"
        lines.append(Line("Hardware", d_, n, n, "ea", why, uc, src, sku))
        sd_screws += 0 if cap.startswith("CCQ") else n * POST_CAP_SCREWS.get(cap, 10)
    d = PRICEBOOK["hardware"]["SD10212_100"]
    boxes = int(math.ceil(sd_screws / d["count"]))
    lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{sd_screws} needed  (bases {base_screws} · caps {sd_screws - base_screws})", d["each"], d["source"]))
    blk = 0 if timber else 4 * Qz.n_blocks
    rss = Qz.rss_lam + blk
    if timber and Qz.n_blocks:
        sched["Blocking"] = f"{Qz.n_blocks} x 4x10 blocks over the beams, (3) 16d toe-nails each end (from the 16d boxes above)"
    if rss:
        d = PRICEBOOK["hardware"]["RSS_3-1/8_100"]
        boxes = int(math.ceil(rss / d["count"]))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{rss} needed  (laminations {Qz.rss_lam} · blocking {blk})", d["each"], d["source"]))
    n_rail_posts = (len(rl.posts) if rl else 0) + sum(s.stair_posts for s in stairs)
    if rl and n_rail_posts:
        nb = 2 * n_rail_posts
        d_, uc, src, sku = _hw("bolt_7/16x4.5", black)
        lines.append(Line("Hardware", d_, nb, nb + 2, "ea", f"+2  ({n_rail_posts} rail posts x 2)", uc, src))
    for st in stairs:
        d = PRICEBOOK["hardware"]["LSCZ"]
        lines.append(Line("Hardware", d["desc"], st.stringers, st.stringers, "ea", f"exact  ({st.side} stair, 1 per stringer at the rim)", d["each"], d["source"], "LSCZ"))

    # ================= FLASHING & WATERPROOFING
    if Qz.ledger_len:
        if Qz.ledger_len <= 240 and not timber:
            d = PRICEBOOK["hardware"]["flashing_set"]
            lines.append(Line("Flashing & waterproofing", d["desc"], 1, 1, "set", "exact", d["each"], d["source"]))
        else:
            nz = int(math.ceil(Qz.ledger_len / 120))
            nm = int(math.ceil(Qz.ledger_len / 900))
            d = PRICEBOOK["hardware"]["membrane_6x75"]; lines.append(Line("Flashing & waterproofing", d["desc"], nm, nm, "roll", "exact", d["each"], d["source"]))
            key = "wall_flashing_10" if timber else "zflash_10"
            d = PRICEBOOK["hardware"][key]; lines.append(Line("Flashing & waterproofing", d["desc"], nz, nz + 1, "ea", "+1  (laps 3\") — metal flashing at every wall", d["each"], d["source"]))
            d = PRICEBOOK["hardware"]["end_dam"]; lines.append(Line("Flashing & waterproofing", d["desc"], 2 * len(L.zones), 2 * len(L.zones), "ea", "exact", d["each"], d["source"]))
    if spec.framing.joist_tape:
        for key, need in (("gtape_2", Qz.tape2), ("gtape_4", Qz.tape4)):
            d = PRICEBOOK["hardware"][key]
            rolls = int(math.ceil(need / 12 / d["lf"]))
            lines.append(Line("Flashing & waterproofing", d["desc"], rolls, rolls, "roll", f"{need / 12:.0f}' needed of {rolls * d['lf']}'", d["each"], d["source"]))
        sched["Joist tape"] = "G-Tape 2\" every joist, PF joist, blocking and the ledger top · 4\" on both rims and the beam(s)"

    # ================= DECKING
    for stock, n_rows in sorted(Qz.field_boards.items()):
        key = f"{brand}|{coll}|{stock}|{spec.decking.profile}"
        uc, src = _price("decking", key)
        if uc == 0.0:
            lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * stock, 2)
        prof = "Grooved" if spec.decking.profile == "grooved" else "Square Edge"
        lines.append(Line("Decking", f"{brand} {coll} {color} 1x6x{stock} {prof}", n_rows, n_rows + 2, "ea",
                          "+2  (" + " · ".join(Qz.field_piece_note) + ")", uc, src))
    if spec.geometry.picture_frame:
        bstock = defaultdict(list)
        for name, Lb in Qz.border_pieces + Qz.divider_pieces:
            s_ = next((s for s in (12, 16, 20) if Lb <= s * 12 - 2), 20)
            if Lb > 240:
                # long border: 20' pieces + remainder
                k = int(Lb // 240)
                bstock[20] += [(name, 240.0)] * k
                rem = Lb - 240 * k
                if rem > 1:
                    bstock[next((s for s in (12, 16, 20) if rem <= s * 12 - 2), 20)].append((name, rem))
            else:
                bstock[s_].append((name, Lb))
        for s_, lst in sorted(bstock.items()):
            key = f"{brand}|{bcoll}|{s_}|square"
            uc, src = _price("decking", key)
            if uc == 0.0:
                lf, src = _price("decking", f"{brand}|{bcoll}|per_lf"); uc = round(lf * s_, 2)
            lines.append(Line("Decking", f"{brand} {bcoll} {bcolor} 1x6x{s_} Square Edge — borders{' & dividers' if Qz.divider_pieces else ''}", len(lst), len(lst) + 1, "ea",
                              f"+1  ({' · '.join(n + ' ' + ftin(l) for n, l in lst)})", uc, src))
        for name, Lb in Qz.border_pieces:
            cuts.append(CutPiece(name.capitalize(), f"{bcoll} {bcolor} square", Lb, 1, "sides full length, front butted between"))
        for name, Lb in Qz.divider_pieces:
            cuts.append(CutPiece(name.capitalize(), f"{bcoll} {bcolor} square", Lb, 1, "divider board on the zone line, wall to front border"))
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
        lines.append(Line("Fascia", f"{brand} {coll} Fascia {spec.decking.fascia_color or color} {fas['thick']:g}x{fas['width']:g}x12", nf, nf + 1, "ea", why, uc, src))
        for name, Lf in Qz.fascia_pieces:
            cuts.append(CutPiece(name.capitalize(), "fascia", Lf, 1, "flush under the board nose; full board at the front corners, short piece at the house"))
    elif not spec.decking.fascia:
        notes.append("no fascia — rims are the finished edge" + (" (timber, end grain sealed)" if timber else ""))

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
        n = Qz.clips + face + stair_face                       # everything plugged: field, borders, dividers
        d = PRICEBOOK["decking"]["Cortex_TimberTech_100lf"]
        boxes = int(math.ceil(n / d["count"]))
        lines.append(Line("Fasteners", f"Cortex for TimberTech 2-1/2\" plug + screw kit 100 LF, {color}" + (f" + {bcolor} plugs for borders" if bcolor != color else ""),
                          boxes, boxes, "box", f"{n} screws/plugs needed  (field {Qz.clips} · borders/first row {face}" + (f" · stairs {stair_face}" if stair_face else "") + f") · {boxes * d['count']} supplied", d["each"], d["source"]))
        sched["Field"] = f"Cortex hidden fasteners: 2 per board at every joist, color-matched plugs ({Qz.bearing_points} bearing points x {Qz.field_rows} rows x 2)"
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
        sec_count = defaultdict(int)
        for s_ in rl.sections:
            sec_count[(s_.panel_stock_in, s_.kind)] += 1
        for (stock_in, kind), n in sorted(sec_count.items()):
            cuts_txt = sorted(set(ftin(s_.cut_len) for s_ in rl.sections if s_.panel_stock_in == stock_in and s_.kind == kind))
            if cable:
                uc, src = _price("rail", f"{sysn}|toprail|{stock_in // 12}")
                lines.append(Line("Rail", f"{brand} {sysn} top rail {stock_in // 12}' {rl.color}", n, n, "ea", f"exact  (cut to {' / '.join(cuts_txt)})", uc, src))
                uc, src = _price("rail", f"{sysn}|cable_kit|{stock_in // 12}")
                lines.append(Line("Rail", _desc("rail", f"{sysn}|cable_kit|{stock_in // 12}", f"{sysn} cable infill kit {stock_in // 12}'"), n, n, "kit", "exact  (one per section, no bottom rail)", uc, src))
            else:
                uc, src = _price("rail", f"{sysn}|panel|{stock_in // 12}|{kind}")
                lines.append(Line("Rail", f"{brand} {sysn} Rail {stock_in // 12}' x {rl.height:g}\" {kind} panel {rl.color}", n, n, "ea",
                                  f"exact  (cut to {' / '.join(cuts_txt)})", uc, src))
        pk = Counter(p.kind for p in rl.posts)
        for kind, n in sorted(pk.items()):
            uc, src = _price("rail", f"{sysn}|post|{kind}")
            lines.append(Line("Rail", f"{brand} {sysn} 2\" {kind} post {rl.height:g}\" {rl.color} w/ brackets, cap" + ("" if cable else ", skirt"), n, n, "ea", "exact", uc, src))
        if spec.railing.drink_rail:
            dcoll = spec.railing.drink_rail_collection or bcoll
            dcolor = spec.railing.drink_rail_color or bcolor
            lf_total = rl.rail_lf * 12
            nb = int(math.ceil(lf_total / 236)) if lf_total > 190 else int(math.ceil(lf_total / 140))
            stock = 20 if lf_total > 190 else 12
            uc, src = _price("decking", f"{brand}|{dcoll}|{stock}|square")
            if uc == 0.0:
                lf, src = _price("decking", f"{brand}|{dcoll}|per_lf"); uc = round(lf * stock, 2)
            lines.append(Line("Rail", f"{brand} {dcoll} {dcolor} 1x6x{stock} Square Edge — drink rail cap", nb, nb + 1, "ea", f"+1  ({rl.rail_lf} LF, mitred corners)", uc, src))
            nbr = int(math.ceil(lf_total / 24)) + len(rl.posts)
            d_, uc, src, sku = _hw("drink_rail_bracket", True)
            lines.append(Line("Rail", d_, nbr, nbr + 4, "ea", "+4  (24\" OC + one at every post)", uc, src))
            uc, src = _price("decking", "Cortex_TimberTech_100lf")
            lines.append(Line("Rail", f"Cortex plugs + screws for the drink rail, {dcolor}", 1, 1, "box", f"{nbr * 2} needed", uc, src))
        for st in stairs:
            sc = Counter(s_.panel_stock_in for s_ in st.stair_sections)
            for stock_in, n in sorted(sc.items()):
                if cable:
                    uc, src = _price("rail", f"{sysn}|stair_cable_kit|{stock_in // 12}")
                    lines.append(Line("Stairs", f"{brand} {sysn} stair top rail + cable kit {stock_in // 12}' ({st.side} stair)", n, n, "kit", "exact", uc, src))
                else:
                    uc, src = _price("rail", f"{sysn}|panel|{stock_in // 12}|stair")
                    lines.append(Line("Stairs", f"{brand} {sysn} Rail {stock_in // 12}' x {rl.height:g}\" STAIR panel {rl.color} ({st.side} stair)", n, n, "ea", "exact", uc, src))
            if st.stair_posts:
                uc, src = _price("rail", f"{sysn}|post|STAIR")
                lines.append(Line("Stairs", f"{brand} {sysn} 2\" STAIR post {rl.color} w/ brackets, cap ({st.side} stair)", st.stair_posts, st.stair_posts, "ea", "exact  (top + bottom of each rail side)", uc, src))
            if st.geo.handrail_required and st.stair_rail_sides:
                uc, src = _price("rail", f"{sysn}|handrail_kit")
                lines.append(Line("Stairs", f"{sysn} graspable handrail kit ({st.side} stair)", 1, 1, "ea", "exact  (4+ risers — IRC R311.7.8)", uc, src))
        uc, src = _price("rail", "touchup_paint")
        lines.append(Line("Rail", "Rust-Oleum flat black touch-up (cut ends)", 1, 1, "ea", "exact", uc, src))
        sched["Rail"] = (f"{sysn} {rl.height:g}\" — {len(rl.posts)} posts ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))})"
                         + (f", posts {sysd.get('max_ctc', 96):g}\" OC max, cable infill, no bottom rail" if cable else " inside the outer rim ply, inner ply pocketed 2\" wide")
                         + ", (2) 7/16\" x 4-1/2\" bolts per post" + ("; drink rail board on top, mitred at corners" if spec.railing.drink_rail else ""))
        for n in rl.notes:
            notes.append(n)

    # ================= FINISH (timber)
    if timber:
        if spec.framing.end_grain_seal:
            gal = max(1, int(math.ceil(Qz.timber_ends / 400)))
            d = PRICEBOOK["hardware"]["end_grain_sealer_gal"]
            lines.append(Line("Finish", d["desc"], gal, gal, "gal", f"{Qz.timber_ends} cut ends", d["each"], d["source"]))
        if spec.framing.finish == "oil":
            gal = int(math.ceil(Qz.timber_sf * 2 / 200))
            d = PRICEBOOK["hardware"]["timber_oil_gal"]
            lines.append(Line("Finish", d["desc"] + " — 2 coats every timber", gal, gal + 1, "gal", f"+1  ({Qz.timber_sf:,.0f} SF of timber x 2 coats)", d["each"], d["source"]))
        else:
            notes.append("timbers unfinished — weather to gray; dark walnut oil is an option")

    # ================= SITE
    if spec.extras.demo_existing:
        sf_demo = spec.extras.demo_sf or L.deck_sf
        lines.append(Line("Site", "Demo existing deck + haul-off", sf_demo, sf_demo, "SF", "labor line", 0.0, "labor"))
    for x in spec.extras.site_extras:
        lines.append(Line("Site", x.get("item", "site extra"), 1, 1, "ea", "at cost", float(x.get("cost", 0)), "at cost"))

    # ================= summary
    zones_txt = [f"{z.name} {z.label}: {ftin(z.W)} x {ftin(z.D)}" + (f", wall recessed {ftin(-z.wall_y)}" if z.wall_y < 0 else "") + (" · hot tub" if z.hot_tub else "") for z in L.zones]
    summary = dict(
        job=spec.job, client=spec.client, address=spec.site.address,
        zones=zones_txt if L.multi else [],
        finished_frame=(f"{len(L.zones)} zones, {ftin(W)} along the house, {ftin(D)} at the deepest" if L.multi else f"{ftin(W)} x {ftin(D)} outside to outside"),
        finished_deck=(f"{L.outer_edge_lf} LF of outer edge" if L.multi else f"{ftin(dk0.deck_w)} x {ftin(dk0.deck_d)} over fascia"),
        deck_sf=L.deck_sf, height=ftin(spec.geometry.height_in),
        joists=f"{Qz.n_joists} {jsize} {SPECIES_NAMES['DF#1'] if timber else SPECIES_NAMES.get(jsp, jsp)} @ {fr0.spacing:g}\" OC" + ("" if L.multi else f" x {ftin(fr0.joist_len)}"),
        rims=(f"{fr0.rim_plies}-ply {jsize} sides; front rim = flush beam" if Qz.front_flush else (f"single {jsize} rims" if timber else f"{fr0.rim_plies}-ply {jsize} front and sides")) + ("" if fr0.ledger else " and rear (freestanding)"),
        beams=[f"{b.label}{' (' + z.name + ')' if L.multi else ''} CL {ftin(b.cl_y)} from house, {len(b.posts_x)} posts @ {ftin(b.post_spacing)} (allowable {ftin(b.check.allowable_in)}), cantilever {ftin(b.cantilever)}" for z in L.zones for b in z.frame.beams],
        posts=f"{Qz.n_posts} x {spec.framing.post_size} ~{ftin(Qz.post_len)} on " + (
            fr0.footing_model if ft == "diamond_pier" else f"{int(Qz.footing_dia)}\" {'caissons' if ft == 'caisson' else 'concrete piers'} {ftin(Qz.footing_depth)} deep") + (" with stone column bases" if spec.extras.stone_bases else ""),
        design_load=f"{max(z.frame.total_psf for z in L.zones):g} psf ({fr0.load_note})" + (" · engineered" if spec.extras.engineered else ""),
        decking=f"{brand} {coll} {color} — {Qz.field_rows} rows {'parallel to' if dk0.direction == 'parallel' else 'perpendicular to'} the house"
                + (f", picture frame{' & dividers' if Qz.divider_pieces else ''} in {bcoll} {bcolor}" if spec.geometry.picture_frame else "") + f", {spec.deck_gap:g}\" gaps, {fsys}",
        rail=(f"{rl.system} {rl.height:g}\" {rl.color}: {len(rl.sections)} sections, {len(rl.posts)} posts, {rl.rail_lf} LF" + (" + drink rail" if spec.railing.drink_rail else "") if rl else "none"),
        stairs=[f"{s_.side}: {s_.geo.risers} risers @ {s_.geo.riser_in:.2f}\", {s_.geo.treads} treads, {s_.stringers} stringers, {ftin(s_.width)} wide" for s_ in stairs],
        material_cost=round(sum(l.ext for l in lines), 2),
    )
    return Takeoff(spec, L, lines, cuts, sched, summary, notes)
