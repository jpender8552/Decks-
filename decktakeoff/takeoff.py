"""Layout -> the takeoff: every line written the way Decks & Docks sells it, with NET (drawing count),
ORDER (PO quantity) and a one-line reason wherever they differ. Overage is explicit and small."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from . import engineering as eng
from .catalog import (DOUBLE_HANGER, FASCIA, H25_NAILS, HANGER_FOR_JOIST, HANGER_NAILS, LUMBER_STOCK_FT, POST_BASE, POST_BASE_SCREWS,
                      POST_CAP_SCREWS, PRICEBOOK, RISER, SPECIES_NAMES, actual, decking_facts, default_fastener_system, parse_beam,
                      RAIL_SYSTEMS)
from .layout import Layout, build_layout, LEDGER_T, RIM_PLY
from .spec import DeckSpec
from .units import ftin

CATEGORIES = ["Lumber", "Footings", "Hardware", "Flashing & waterproofing", "Decking", "Fasteners", "Fascia", "Rail", "Stairs", "Site"]


@dataclass
class Line:
    category: str
    item: str            # as D&D sells it
    net: float
    order: float
    unit: str
    why: str             # "exact", "+2", "+1 cull", "330 needed · 360 supplied"
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


def _lumber_price(nominal: str, stock_ft: int):
    d = PRICEBOOK["lumber"].get(nominal)
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
    cnt = defaultdict(int)
    for l in labels:
        cnt[l] += 1
    return " · ".join(f"{v} {k}" if v > 1 else k for k, v in cnt.items())


# ------------------------------------------------------------------ the takeoff
def build_takeoff(spec: DeckSpec) -> Takeoff:
    L = build_layout(spec)
    fr, dk, rl, stairs = L.frame, L.decking, L.rail, L.stairs
    W, D = L.finished_w, L.finished_d
    lines: List[Line] = []
    cuts: List[CutPiece] = []
    notes = list(L.notes) + list(fr.notes) + list(dk.notes)
    sched: Dict[str, str] = {}
    jsize, jsp = fr.joist_size, fr.joist_species
    jb, jd = actual(jsize)
    dkf = decking_facts(spec.decking.collection)
    lsize = spec.ledger_size

    # ================= LUMBER
    pieces: List[Tuple[str, float, str]] = []
    n_field = len(fr.joist_x)
    n_pf = len(fr.pf_x)
    if fr.joist_bays == 1:
        pieces += [(jsize, fr.joist_len, "field joist")] * n_field
        pieces += [(jsize, fr.joist_len, "PF joist")] * n_pf
        cuts.append(CutPiece("Field joists", jsize, fr.joist_len, n_field, f"@ {fr.spacing:g}\" OC, crown up"))
        if n_pf:
            cuts.append(CutPiece("Picture-frame joists", jsize, fr.joist_len, n_pf, "centre 5-1/4\" from each frame face"))
    else:
        # flush mid beam(s): joists run support to support
        sup = [LEDGER_T if fr.ledger else fr.rim_plies * RIM_PLY] + [b.cl_y for b in fr.beams if b.kind == "flush" and b.cl_y < D - 3] + [D - fr.rim_plies * RIM_PLY]
        for a, b in zip(sup, sup[1:]):
            ln = b - a - (1.5 if a > 2 else 0)   # hangers each side of a flush beam: clear span less beam half-widths handled by rounding
            pieces += [(jsize, ln, "joist")] * (n_field + n_pf)
            cuts.append(CutPiece("Joists (bay)", jsize, ln, n_field + n_pf, f"bay {ftin(a)} to {ftin(b)}"))
    # rims
    side_len = fr.joist_len
    for side in ("left", "right"):
        pieces += [(jsize, side_len, f"{side} rim ply")] * fr.rim_plies
    cuts.append(CutPiece("Side rim plies", jsize, side_len, 2 * fr.rim_plies, f"{fr.rim_plies}-ply, laminated on the ground with RSS 2 rows @ 12\" staggered"))
    front_flush = any(b.label.startswith("FRONT FLUSH") for b in fr.beams)
    if front_flush:
        notes.append("front flush beam IS the front rim — joists hang into it, posts under it, no separate rim plies")
    else:
        pieces += [(jsize, W, "front rim ply")] * fr.rim_plies
        cuts.append(CutPiece("Front rim plies", jsize, W, fr.rim_plies, "inner ply takes the hangers; outer ply laminated after"))
    if fr.ledger:
        pieces.append((lsize, W, "ledger"))
        cuts.append(CutPiece("Ledger", lsize, W, 1, "top at deck height less board thickness; membrane behind, Z-flash over"))
    else:
        pieces += [(jsize, W, "rear rim ply")] * fr.rim_plies
        cuts.append(CutPiece("Rear rim plies (freestanding)", jsize, W, fr.rim_plies, ""))
    # blocking
    n_block_rows = len(fr.blocking_rows_y)
    if n_block_rows:
        pieces += [(jsize, fr.block_len, "blocking")] * (fr.n_blocks_per_row * n_block_rows)
        cuts.append(CutPiece("Blocking", jsize, fr.block_len, fr.n_blocks_per_row * n_block_rows,
                             f"{n_block_rows} row{'s' if n_block_rows > 1 else ''} — over the beam" + (" + mid-span (PVC)" if n_block_rows > 1 else "") + ", staggered up/down"))
    # PF blocking for perpendicular boards (front border bears on it)
    if spec.geometry.picture_frame and spec.geometry.board_direction != "parallel":
        pieces += [(jsize, fr.block_len, "PF blocking")] * (n_field + 1)
        cuts.append(CutPiece("Picture-frame blocking", jsize, fr.block_len, n_field + 1, "row 5-1/4\" behind the front rim so the front border ends bear"))
    # beams
    beam_pieces = []
    for b in fr.beams:
        plies, nom, bw, bd = parse_beam(b.size)
        max_stock = LUMBER_STOCK_FT.get(nom, [20])[-1] * 12
        k = max(1, int(math.ceil(b.length / max_stock)))
        seg = b.length / k
        splice = f"; {k} pieces of {ftin(seg)}, splices over posts, staggered ply to ply" if k > 1 else ""
        beam_pieces += [(nom, seg, f"{b.kind} beam")] * (plies * k)
        cuts.append(CutPiece(f"{b.label} beam", nom, seg, plies * k, f"CL {ftin(b.cl_y)} from house; posts at " + " / ".join(ftin(x) for x in b.posts_x) + splice))
    # posts
    post_pieces = [(fr.post_size, fr.post_len + 1.0, "post")] * fr.n_posts
    cuts.append(CutPiece("Posts", fr.post_size, fr.post_len, fr.n_posts, "field-measure each; beam top = joist bottom"))
    # stairs lumber
    for st in stairs:
        pieces += [("2x12", st.geo.stringer_len_in, "stair stringer")] * st.stringers
        cuts.append(CutPiece(f"Stair stringers ({st.side})", "2x12", st.geo.stringer_len_in, st.stringers,
                             f"{st.geo.risers} risers @ {st.geo.riser_in:.3f}\" · {st.geo.treads} treads @ {st.geo.tread_in:.2f}\" · stringers {eng.STRINGER_OC_COMPOSITE:g}\" OC"))
        pieces += [("2x6", st.width + 3, "stair kicker/hanger board")] * 2
    packed = pack_lumber(pieces)
    packed_beam = pack_lumber(beam_pieces)
    packed_post = pack_lumber(post_pieces, short_stock_ft=8)
    for (nom, st), (n, labels) in sorted(packed.items(), key=lambda t: (t[0][0], t[0][1])):
        uc, src = _lumber_price(nom, st)
        desc = f"{nom}x{st} {SPECIES_NAMES.get(jsp, jsp)}" if nom in ("2x6", "2x8", "2x10", "2x12") else f"{nom}x{st}"
        lines.append(Line("Lumber", desc, n, n + 1, "ea", f"+1 cull  ({_summarize_labels(labels)})", uc, src))
    for (nom, st), (n, labels) in packed_beam.items():
        uc, src = _lumber_price(nom, st)
        sp = fr.beams[0].species if fr.beams else "DF"
        lines.append(Line("Lumber", f"{nom}x{st} {SPECIES_NAMES.get(sp, sp)}", n, n, "ea", f"exact  ({_summarize_labels(labels)}: " + " · ".join(f"{b.label} {ftin(b.length)}" for b in fr.beams if parse_beam(b.size)[1] == nom) + ")", uc, src))
    for (nom, st), (n, labels) in packed_post.items():
        uc, src = _lumber_price(nom, st)
        lines.append(Line("Lumber", f"{nom}x{st} #2 GC", n, n, "ea", f"exact  (yields {fr.n_posts} posts at ~{ftin(fr.post_len)})", uc, src))

    # ================= FOOTINGS
    if fr.footing_type == "diamond_pier":
        uc, src = _price("footings", fr.footing_model)
        desc = PRICEBOOK["footings"].get(fr.footing_model, {}).get("desc", f"Diamond Pier {fr.footing_model}")
        lines.append(Line("Footings", desc, fr.n_posts, fr.n_posts, "ea", "exact — confirm stock", uc, src, fr.footing_model,
                          f"{fr.footing_load_lb:,.0f} lb per post vs {fr.footing_capacity_lb:,} lb allowable"))
        base = POST_BASE.get(fr.post_size, {}).get("diamond_pier", "ABA66Z")
        uc, src = _price("footings", base)
        lines.append(Line("Footings", PRICEBOOK["footings"][base]["desc"] + " on the pier bolt", fr.n_posts, fr.n_posts, "ea", "exact", uc, src, base))
    else:
        dia, depth = fr.footing_dia_in, fr.footing_depth_in
        vol_cf = math.pi * (dia / 24) ** 2 * (depth / 12)
        bags = int(math.ceil(vol_cf / 0.6)) * fr.n_posts
        tube = f"sonotube_{int(dia)}" if f"sonotube_{int(dia)}" in PRICEBOOK["footings"] else "sonotube_12"
        uc, src = _price("footings", tube)
        lines.append(Line("Footings", f"{int(dia)}\" form tube x {ftin(depth)} (bearing {ftin(depth - 6)} below grade, frost {ftin(spec.site.frost_depth_in)})", fr.n_posts, fr.n_posts, "ea", "exact", round(uc * depth / 12, 2), src,
                          note=f"{fr.footing_load_lb:,.0f} lb per post on {spec.site.soil_bearing_psf:,.0f} psf soil"))
        uc, src = _price("footings", "concrete_80lb")
        lines.append(Line("Footings", "Concrete mix 80 lb", bags, bags + 2, "bag", f"+2  ({vol_cf:.1f} cf per pier)", uc, src))
        base = POST_BASE.get(fr.post_size, {}).get("concrete", "ABU66Z")
        uc, src = _price("footings", base)
        lines.append(Line("Footings", PRICEBOOK["footings"][base]["desc"] + " wet-set 1/2\" anchor", fr.n_posts, fr.n_posts, "ea", "exact", uc, src, base))
    for st in stairs:
        if st.landing == "concrete pad":
            uc, src = _price("footings", "concrete_pad")
            lines.append(Line("Footings", f"Stair landing pad ({st.side} stair) — 4\" slab, stringers bear on the pad", 1, 1, "ea", "exact", uc, src))

    # ================= HARDWARE / CONNECTORS
    hanger = HANGER_FOR_JOIST.get(jsize, "LUS28Z")
    uc, src = _price("hardware", hanger)
    lines.append(Line("Hardware", PRICEBOOK["hardware"][hanger]["desc"], fr.hangers_single, fr.hangers_single, "ea",
                      f"exact  ({n_field + n_pf} joists x {fr.hangers_single // max(1, n_field + n_pf)} ends)", uc, src, hanger))
    dh = DOUBLE_HANGER.get(jsize, "HUCQ210-2-SDS")
    uc, src = _price("hardware", dh)
    lines.append(Line("Hardware", PRICEBOOK["hardware"][dh]["desc"], fr.hangers_double, fr.hangers_double, "ea", "exact  (2 side rims x 2 ends) — confirm stock", uc, src, dh))
    nh, nj = HANGER_NAILS.get(hanger, (6, 4))
    n3 = fr.hangers_single * nh
    n15 = fr.hangers_single * nj + fr.h25_ties * H25_NAILS
    for key, need in (("nail_3in_5lb", n3), ("nail_1.5in_5lb", n15)):
        d = PRICEBOOK["hardware"][key]
        boxes = max(1, int(math.ceil(need / d["count"])))
        lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{need} needed of ~{boxes * d['count']}", d["each"], d["source"], key))
    if fr.ledger:
        n_ll, rule = eng.ledger_fastener_count(W, fr.beams[0].back_span if fr.beams else fr.joist_len, spec.framing.ledger_fastener)
        if spec.framing.ledger_fastener.lower().startswith("ledgerlok"):
            d = PRICEBOOK["hardware"]["LedgerLOK_50"]
            boxes = int(math.ceil(n_ll / d["count"]))
            lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{n_ll} needed", d["each"], d["source"], "LedgerLOK"))
        else:
            d = PRICEBOOK["hardware"]["lag_1/2x4"]
            lines.append(Line("Hardware", d["desc"], n_ll, n_ll + 2, "ea", "+2", d["each"], d["source"]))
        sched["Ledger"] = f"{lsize} ledger x {ftin(W)} · {rule} · {n_ll} fasteners"
        n_dtt = spec.framing.lateral_ties
        d = PRICEBOOK["hardware"]["DTT1Z"]
        lines.append(Line("Hardware", d["desc"], n_dtt, n_dtt, "ea", "exact  (2 near each end, into house floor framing)", d["each"], d["source"], "DTT1Z"))
    if fr.h25_ties:
        d = PRICEBOOK["hardware"]["H2.5AZ"]
        lines.append(Line("Hardware", d["desc"], fr.h25_ties, fr.h25_ties, "ea", f"exact  ({n_field + n_pf} joists + 2 rims at each drop beam)", d["each"], d["source"], "H2.5AZ"))
    caps = defaultdict(int)
    for b in fr.beams:
        caps[b.cap] += len(b.posts_x)
    sd_screws = 0
    for cap, n in caps.items():
        d = PRICEBOOK["hardware"].get(cap, {"desc": f"Simpson {cap} post cap", "each": 15.0, "source": "est."})
        why = "exact" if not cap.startswith("BC46Z") or all(parse_beam(b.size)[1].startswith("4x") for b in fr.beams) else "exact — (2)2x beam in a 4x cap needs a 1/2\" shim; confirm cap"
        lines.append(Line("Hardware", d["desc"], n, n, "ea", why, d["each"], d["source"], cap))
        sd_screws += n * POST_CAP_SCREWS.get(cap, 10)
    base = POST_BASE.get(fr.post_size, {}).get(fr.footing_type, "ABA66Z")
    sd_screws += fr.n_posts * POST_BASE_SCREWS.get(base, 12)
    d = PRICEBOOK["hardware"]["SD10212_100"]
    boxes = int(math.ceil(sd_screws / d["count"]))
    lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{sd_screws} needed  ({base} {fr.n_posts * POST_BASE_SCREWS.get(base, 12)} · caps {sd_screws - fr.n_posts * POST_BASE_SCREWS.get(base, 12)})", d["each"], d["source"]))
    # structural screws: rim laminations 2 rows @ 12" staggered, blocking 4 each, flush-beam plies
    lam = 0
    for _ in range(2):
        lam += 2 * (int(math.ceil(side_len / 12)) + 1)
    lam += 2 * (int(math.ceil(W / 12)) + 1) * (fr.rim_plies - 1)
    if not fr.ledger:
        lam += 2 * (int(math.ceil(W / 12)) + 1)
    for b in fr.beams:
        if b.plies > 1:
            lam += 2 * (int(math.ceil(b.length / 12)) + 1) * (b.plies - 1)
    blk = 4 * fr.n_blocks_per_row * n_block_rows
    rss = lam + blk
    d = PRICEBOOK["hardware"]["RSS_3-1/8_100"]
    boxes = int(math.ceil(rss / d["count"]))
    lines.append(Line("Hardware", d["desc"], boxes, boxes, "box", f"{rss} needed  (laminations {lam} · blocking {blk})", d["each"], d["source"]))
    if rl and rl.system == "Fulton":
        nb = 2 * len(rl.posts) + 2 * sum(s.stair_posts for s in stairs)
        d = PRICEBOOK["hardware"]["bolt_7/16x4.5"]
        lines.append(Line("Hardware", d["desc"], nb, nb + 2, "ea", f"+2  ({len(rl.posts) + sum(s.stair_posts for s in stairs)} rail posts x 2)", d["each"], d["source"]))
    for st in stairs:
        d = PRICEBOOK["hardware"]["LSCZ"]
        lines.append(Line("Hardware", d["desc"], st.stringers, st.stringers, "ea", f"exact  ({st.side} stair, 1 per stringer at the rim)", d["each"], d["source"], "LSCZ"))

    # ================= FLASHING & WATERPROOFING
    if fr.ledger:
        if W <= 240:
            d = PRICEBOOK["hardware"]["flashing_set"]
            lines.append(Line("Flashing & waterproofing", d["desc"], 1, 1, "set", "exact", d["each"], d["source"]))
        else:
            nz = int(math.ceil(W / 120))
            nm = int(math.ceil(W / 900))
            d = PRICEBOOK["hardware"]["membrane_6x75"]; lines.append(Line("Flashing & waterproofing", d["desc"], nm, nm, "roll", "exact", d["each"], d["source"]))
            d = PRICEBOOK["hardware"]["zflash_10"]; lines.append(Line("Flashing & waterproofing", d["desc"], nz, nz + 1, "ea", "+1  (laps 3\")", d["each"], d["source"]))
            d = PRICEBOOK["hardware"]["end_dam"]; lines.append(Line("Flashing & waterproofing", d["desc"], 2, 2, "ea", "exact", d["each"], d["source"]))
    if spec.framing.joist_tape:
        t2 = (n_field + n_pf) * fr.joist_len * (1 if fr.joist_bays == 1 else 1) + fr.n_blocks_per_row * n_block_rows * fr.block_len + (W if fr.ledger else 0)
        t4 = 2 * side_len + W * (1 if fr.ledger else 2) + sum(b.length for b in fr.beams if b.kind == "drop")
        for key, need in (("gtape_2", t2), ("gtape_4", t4)):
            d = PRICEBOOK["hardware"][key]
            rolls = int(math.ceil(need / 12 / d["lf"]))
            lines.append(Line("Flashing & waterproofing", d["desc"], rolls, rolls, "roll", f"{need / 12:.0f}' needed of {rolls * d['lf']}'", d["each"], d["source"]))
        sched["Joist tape"] = "G-Tape 2\" every joist, PF joist, blocking and the ledger top · 4\" on both rims and the beam(s)"

    # ================= DECKING
    coll, color = spec.decking.collection, spec.decking.color
    brand = spec.decking.brand
    stock = dk.stock_ft
    n_rows = dk.rows * dk.row_pieces
    key = f"{brand}|{coll}|{stock}|{spec.decking.profile}"
    uc, src = _price("decking", key)
    if uc == 0.0:
        lf, src = _price("decking", f"{brand}|{coll}|per_lf")
        uc = round(lf * stock, 2)
    prof = "Grooved" if spec.decking.profile == "grooved" else "Square Edge"
    lines.append(Line("Decking", f"{brand} {coll} {color} 1x6x{stock} {prof}", n_rows, n_rows + 2, "ea",
                      f"+2  ({dk.rows} rows{' x ' + str(dk.row_pieces) + ' pieces' if dk.row_pieces > 1 else ''} cut to {ftin(dk.piece_len)})", uc, src))
    cuts.append(CutPiece("Field boards", f"{coll} {color}", dk.piece_len, n_rows, f"{dk.rows} rows, boards run {'parallel to' if dk.direction == 'parallel' else 'out from'} the house"))
    if dk.picture_frame:
        bstock = defaultdict(list)
        for name, Lb in dk.border_pieces:
            s = next((s for s in (12, 16, 20) if Lb <= s * 12 - 2), 20)
            bstock[s].append((name, Lb))
        for s, lst in sorted(bstock.items()):
            key = f"{brand}|{coll}|{s}|square"
            uc, src = _price("decking", key)
            if uc == 0.0:
                lf, src = _price("decking", f"{brand}|{coll}|per_lf"); uc = round(lf * s, 2)
            lines.append(Line("Decking", f"{brand} {coll} {color} 1x6x{s} Square Edge", len(lst), len(lst) + 1, "ea",
                              f"+1  ({' · '.join(n + ' ' + ftin(l) for n, l in lst)})", uc, src))
        for name, Lb in dk.border_pieces:
            cuts.append(CutPiece(name.capitalize(), f"{coll} {color} square", Lb, 1, "sides full length, front butted between"))
    # stair treads/risers
    for st in stairs:
        per_board = max(1, int(math.floor(144 / (st.width + 0.25))))
        nb = int(math.ceil(st.tread_pieces / per_board))
        key = f"{brand}|{coll}|12|square"
        uc, src = _price("decking", key)
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
    if spec.decking.fascia:
        packed_f = pack_lumber([("fascia", Lf, name) for name, Lf in dk.fascia_pieces], kerf=0.125)
        nf = sum(n for (_, s), (n, _) in packed_f.items())
        uc, src = _price("decking", f"{brand}|{coll}|fascia")
        if uc == 0.0:
            lf, src = _price("decking", "generic_fascia_per_lf"); uc = round(lf * 12, 2)
        fas = FASCIA[dkf["material"]]
        why = "+1  (" + " · ".join(f"{n} {ftin(Lf)}" for n, Lf in dk.fascia_pieces) + ")"
        lines.append(Line("Fascia", f"{brand} {coll} Fascia {spec.decking.fascia_color or color} {fas['thick']:g}x{fas['width']:g}x12", nf, nf + 1, "ea", why, uc, src))
        for name, Lf in dk.fascia_pieces:
            cuts.append(CutPiece(name.capitalize(), "fascia", Lf, 1, "flush under the board nose; full board at the front corners, short piece at the house"))

    # ================= FASTENERS
    fsys = spec.decking.fastener_system or default_fastener_system(coll, spec.decking.profile)
    face = dk.first_row_screws + dk.border_screws + dk.fascia_screws
    stair_face = 0
    for st in stairs:
        stair_face += st.tread_pieces * st.stringers * 2 + st.riser_pieces * st.stringers * 2
    if fsys == "Camo EdgeClip":
        d = PRICEBOOK["decking"]["Camo_EdgeClip_90"]
        boxes = int(math.ceil(dk.clips / d["count"]))
        lines.append(Line("Fasteners", "Camo EdgeClip 3/16\" 410SS Black 90 ct", boxes, boxes, "box", f"{dk.clips} clips needed · {boxes * d['count']} supplied", d["each"], d["source"]))
        sched["Field"] = f"100% hidden — Camo EdgeClip 3/16\" at every joist in every gap ({dk.bearing_points} bearing points x {dk.gaps} gaps = {dk.clips}); board ends clipped on the PF joists, never screwed"
    elif fsys == "CONCEALoc":
        d = PRICEBOOK["decking"]["CONCEALoc_500"]
        boxes = int(math.ceil(dk.clips / d["count"]))
        lines.append(Line("Fasteners", "TimberTech CONCEALoc hidden fastener 500 ct (screws incl.)", boxes, boxes, "box", f"{dk.clips} needed · {boxes * d['count']} supplied", d["each"], d["source"]))
        sched["Field"] = f"CONCEALoc at every joist in every gap ({dk.clips})"
    else:
        n = dk.clips * 2
        d = PRICEBOOK["decking"]["Cortex_2-1/2_100lf"]
        boxes = int(math.ceil(n / d["count"]))
        lines.append(Line("Fasteners", f"Cortex 2-1/2\" plug + screw kit, {color}", boxes, boxes, "box", f"{n} needed (2 per board per joist)", d["each"], d["source"]))
        sched["Field"] = "Cortex 2 per board at every joist, plugged"
    d = PRICEBOOK["decking"]["CapTor_xd_350"]
    tot = face + stair_face
    boxes = max(1, int(math.ceil(tot / d["count"])))
    lines.append(Line("Fasteners", f"Starborn Cap-Tor xd 2-3/4\" Epoxy {color} 350 ct", boxes, boxes, "box",
                      f"{tot} screws needed  (first row {dk.first_row_screws} · border {dk.border_screws} · fascia {dk.fascia_screws}" + (f" · stairs {stair_face}" if stair_face else "") + ")", d["each"], d["source"]))
    sched["Face screws"] = ("Cap-Tor xd color-matched ONLY at: first row 1 per joist on the house edge · borders 2 per bearing point @ 16\" · "
                            "fascia 2 at each board end then alternate top/bottom every 12\", pre-drilled" + (" · stair treads 2 per stringer per board" if stairs else ""))

    # ================= RAIL
    if rl:
        sysn = rl.system
        sec_count = defaultdict(int)
        for s in rl.sections:
            sec_count[(s.panel_stock_in, s.kind)] += 1
        for (stock_in, kind), n in sorted(sec_count.items()):
            key = f"{sysn}|panel|{stock_in // 12}|{kind}"
            uc, src = _price("rail", key)
            cuts_txt = sorted(set(ftin(s.cut_len) for s in rl.sections if s.panel_stock_in == stock_in and s.kind == kind))
            lines.append(Line("Rail", f"{brand} {sysn} Rail {stock_in // 12}' x {rl.height:g}\" {kind} panel {rl.color}", n, n, "ea",
                              f"exact  (cut to {' / '.join(cuts_txt)})", uc, src))
        pk = defaultdict(int)
        for p in rl.posts:
            pk[p.kind] += 1
        for kind, n in sorted(pk.items()):
            uc, src = _price("rail", f"{sysn}|post|{kind}")
            lines.append(Line("Rail", f"{brand} {sysn} 2\" {kind} post {rl.height:g}\" {rl.color} w/ brackets, cap, skirt", n, n, "ea", "exact", uc, src))
        for st in stairs:
            for s in st.stair_sections:
                pass
            sc = defaultdict(int)
            for s in st.stair_sections:
                sc[s.panel_stock_in] += 1
            for stock_in, n in sorted(sc.items()):
                uc, src = _price("rail", f"{sysn}|panel|{stock_in // 12}|stair")
                lines.append(Line("Stairs", f"{brand} {sysn} Rail {stock_in // 12}' x {rl.height:g}\" STAIR panel {rl.color} ({st.side} stair)", n, n, "ea", "exact", uc, src))
            if st.stair_posts:
                uc, src = _price("rail", f"{sysn}|post|STAIR")
                lines.append(Line("Stairs", f"{brand} {sysn} 2\" STAIR post {rl.color} w/ brackets, cap, skirt ({st.side} stair)", st.stair_posts, st.stair_posts, "ea", "exact  (top + bottom of each rail side)", uc, src))
            if st.geo.handrail_required and st.stair_rail_sides:
                uc, src = _price("rail", f"{sysn}|handrail_kit")
                lines.append(Line("Stairs", f"{sysn} graspable handrail kit ({st.side} stair)", 1, 1, "ea", "exact  (4+ risers — IRC R311.7.8)", uc, src))
        uc, src = _price("rail", "touchup_paint")
        lines.append(Line("Rail", "Rust-Oleum flat black touch-up (cut panel ends)", 1, 1, "ea", "exact", uc, src))
        sched["Rail"] = (f"{sysn} {rl.height:g}\" — {len(rl.posts)} posts ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()))}) inside the outer rim ply, "
                         f"inner ply pocketed 2\" wide, (2) 7/16\" x 4-1/2\" HDG bolts per post; brackets and screws ship with the posts")

    # ================= SITE
    if spec.extras.demo_existing:
        lines.append(Line("Site", "Demo existing deck + haul-off", spec.extras.demo_sf or dk.sf, spec.extras.demo_sf or dk.sf, "SF", "labor line", 0.0, "labor"))
    for x in spec.extras.site_extras:
        lines.append(Line("Site", x.get("item", "site extra"), 1, 1, "ea", "at cost", float(x.get("cost", 0)), "at cost"))

    # ================= summary
    summary = dict(
        job=spec.job, client=spec.client, address=spec.site.address,
        finished_frame=f"{ftin(W)} x {ftin(D)} outside to outside",
        finished_deck=f"{ftin(dk.deck_w)} x {ftin(dk.deck_d)} over fascia",
        deck_sf=dk.sf, height=ftin(spec.geometry.height_in),
        joists=f"{n_field} field + {n_pf} PF {jsize} {SPECIES_NAMES.get(jsp, jsp)} @ {fr.spacing:g}\" OC x {ftin(fr.joist_len)}",
        rims=(f"{fr.rim_plies}-ply {jsize} sides; front rim = flush beam" if front_flush else f"{fr.rim_plies}-ply {jsize} front and sides") + ("" if fr.ledger else " and rear (freestanding)"),
        beams=[f"{b.label} CL {ftin(b.cl_y)} from house, {len(b.posts_x)} posts @ {ftin(b.post_spacing)} (allowable {ftin(b.check.allowable_in)}), cantilever {ftin(b.cantilever)}" for b in fr.beams],
        posts=f"{fr.n_posts} x {fr.post_size} ~{ftin(fr.post_len)} on {fr.footing_model if fr.footing_type == 'diamond_pier' else str(int(fr.footing_dia_in)) + chr(34) + ' concrete piers ' + ftin(fr.footing_depth_in) + ' deep'}",
        design_load=f"{fr.total_psf:g} psf ({fr.load_note})",
        decking=f"{brand} {coll} {color} — {dk.rows} rows {'parallel to' if dk.direction == 'parallel' else 'perpendicular to'} the house" + (", picture frame" if dk.picture_frame else ""),
        rail=(f"{rl.system} {rl.height:g}\" {rl.color}: {len(rl.sections)} panels, {len(rl.posts)} posts, {rl.rail_lf} LF" if rl else "none"),
        stairs=[f"{s.side}: {s.geo.risers} risers @ {s.geo.riser_in:.2f}\", {s.geo.treads} treads, {s.stringers} stringers, {ftin(s.width)} wide" for s in stairs],
        material_cost=round(sum(l.ext for l in lines), 2),
    )
    return Takeoff(spec, L, lines, cuts, sched, summary, notes)
