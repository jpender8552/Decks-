"""Renderers: markdown takeoff sheet, JSON, CSV order, cut list, and the GSX doc-skill job block."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from typing import List, Optional

from .flags import Flag, run_flags
from .pricing import Pricing
from .takeoff import Takeoff, CATEGORIES
from .units import ftin


def _q(v: float) -> str:
    return f"{v:g}"


def takeoff_markdown(t: Takeoff, flags: Optional[List[Flag]] = None, pricing: Optional[Pricing] = None) -> str:
    s, L, sm = t.spec, t.layout, t.summary
    fr, dk, rl = L.frame, L.decking, L.rail
    out = []
    w = out.append
    w(f"# Takeoff — {s.job}" + (f" · {s.client}" if s.client else ""))
    if s.site.address:
        w(f"{s.site.address}{', ' + s.site.city if s.site.city else ''}{' ' + s.site.state if s.site.state else ''}")
    w("")
    w("## Design reads")
    w(f"- **Frame** {sm['finished_frame']} · deck over fascia {sm['finished_deck']} · {sm['deck_sf']} SF · surface {sm['height']} above grade")
    w(f"- **Joists** {sm['joists']}")
    w(f"- **Rims** {sm['rims']} — hung in concealed-flange double hangers")
    for b in sm["beams"]:
        w(f"- **Beam** {b}")
    w(f"- **Posts / footings** {sm['posts']}")
    w(f"- **Design load** {sm['design_load']}")
    w(f"- **Decking** {sm['decking']}")
    w(f"- **Rail** {sm['rail']}")
    for st in sm["stairs"]:
        w(f"- **Stair** {st}")
    for n in t.notes:
        w(f"- {n}")
    w("")
    if rl:
        w("## Rail posts (standing in the yard facing the house; x from the left frame face, y from the house)")
        for p in rl.posts:
            w(f"- {p.tag}: {p.kind} at x {ftin(p.x)}, y {ftin(p.y)}")
        w("")
    w("## Order (Decks & Docks, account GSEXT1, ship to job)")
    w("")
    for cat, lines in t.by_category().items():
        w(f"### {cat}")
        w("| NET | ORDER | Unit | Item | Why |")
        w("|---:|---:|---|---|---|")
        for ln in lines:
            w(f"| {_q(ln.net)} | {_q(ln.order)} | {ln.unit} | {ln.item} | {ln.why} |")
        w("")
    w("## Fastener & connector schedule")
    for k, v in t.schedule.items():
        w(f"- **{k}** — {v}")
    w("")
    w("## Cut list")
    w("| Member | Stock | Length | Qty | Note |")
    w("|---|---|---:|---:|---|")
    for c in t.cut_list:
        w(f"| {c.member} | {c.nominal} | {ftin(c.length_in)} | {c.qty} | {c.note} |")
    w("")
    if flags is not None:
        w("## Site & code flags (INTERNAL — not for the homeowner)")
        if not flags:
            w("- none")
        for f in flags:
            w(f"- **{f.severity}** · {f.topic}: {f.text}" + (f" _({f.ref})_" if f.ref else ""))
        w("")
    if pricing is not None:
        w("## Pricing (INTERNAL)")
        w(f"- Materials ${pricing.materials:,.2f} · tax {pricing.tax_rate:.2%} ${pricing.tax:,.2f} · labor ${pricing.labor:,.2f} · GC ${pricing.gc:,.2f} (at cost)")
        for i, q, u, r, e in pricing.labor_lines:
            w(f"  - {i}: {q:g} {u} × ${r:g} = ${e:,.2f}")
        w(f"- **Sell (check or ACH) ${pricing.sell:,.0f}** at {pricing.gm:.1%} GM · floor ${pricing.sell_floor:,.0f} at 40% · GP ${pricing.gp:,.0f}")
        w(f"- **Retail (financed) ${pricing.retail:,.0f}** · ${pricing.monthly:,.0f}/mo at 6.99% / 10 yr")
        w("- What the price includes: " + " · ".join(f"{k} ${v:,.0f}" for k, v in pricing.allocation))
        w("")
    return "\n".join(out)


def takeoff_json(t: Takeoff, flags: Optional[List[Flag]] = None, pricing: Optional[Pricing] = None) -> dict:
    L = t.layout
    d = dict(
        spec=t.spec.to_dict(),
        summary=t.summary,
        notes=t.notes,
        lines=[dict(asdict(l), ext=l.ext) for l in t.lines],
        cut_list=[asdict(c) for c in t.cut_list],
        schedule=t.schedule,
        layout=dict(
            frame=dict(W=L.frame.W, D=L.frame.D, joist_x=L.frame.joist_x, pf_x=L.frame.pf_x, joist_len=L.frame.joist_len,
                       beams=[dict(kind=b.kind, size=b.size, species=b.species, cl_y=b.cl_y, length=b.length, posts_x=b.posts_x, post_spacing=b.post_spacing,
                                   back_span=b.back_span, cantilever=b.cantilever, allowable=b.check.allowable_in, ok=b.check.ok, cap=b.cap) for b in L.frame.beams],
                       blocking_rows_y=L.frame.blocking_rows_y, post_len=L.frame.post_len, footing=dict(type=L.frame.footing_type, model=L.frame.footing_model,
                       load_lb=L.frame.footing_load_lb, capacity_lb=L.frame.footing_capacity_lb, dia_in=L.frame.footing_dia_in, depth_in=L.frame.footing_depth_in),
                       joist_checks=[asdict(c) for c in L.frame.joist_checks]),
            decking=dict(rows=L.decking.rows, field_len=L.decking.field_len, stock_ft=L.decking.stock_ft, deck_w=L.decking.deck_w, deck_d=L.decking.deck_d,
                         clips=L.decking.clips, face_screws=dict(first_row=L.decking.first_row_screws, border=L.decking.border_screws, fascia=L.decking.fascia_screws),
                         sf=L.decking.sf),
            rail=(dict(posts=[asdict(p) for p in L.rail.posts], sections=[asdict(x) for x in L.rail.sections], rail_lf=L.rail.rail_lf,
                       openings=[asdict(o) for o in L.rail.openings]) if L.rail else None),
            stairs=[dict(side=s.side, width=s.width, geometry=asdict(s.geo), stringers=s.stringers, tread_pieces=s.tread_pieces, riser_pieces=s.riser_pieces,
                         stair_posts=s.stair_posts, landing=s.landing) for s in L.stairs],
        ),
    )
    if flags is not None:
        d["flags"] = [asdict(f) for f in flags]
    if pricing is not None:
        d["pricing"] = asdict(pricing)
    return d


def order_csv(t: Takeoff) -> str:
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["Category", "Item", "NET", "ORDER", "Unit", "Why", "Unit cost", "Ext", "Source", "SKU"])
    for ln in t.lines:
        wr.writerow([ln.category, ln.item, ln.net, ln.order, ln.unit, ln.why, ln.unit_cost, ln.ext, ln.source, ln.sku])
    return buf.getvalue()


def gsx_job_block(t: Takeoff) -> str:
    """The geometry + BOM block for gsx-deck-docs/scripts/common.py (the build-set / proposal PDF pipeline)."""
    L, s = t.layout, t.spec
    fr, dk, rl = L.frame, L.decking, L.rail
    b0 = fr.beams[0] if fr.beams else None
    lines = ["# ---- generated by decktakeoff: paste into gsx-deck-docs/scripts/common.py job block ----",
             f"FW = {fr.W:.2f}", f"FD = {fr.D:.2f}", f"DECK_H = {s.geometry.height_in:.1f}",
             f"JOIST_X = {fr.joist_x}", f"PF_X = {fr.pf_x}",
             f"BEAM_CL = {b0.cl_y:.2f}" if b0 else "BEAM_CL = None",
             f"POST_X = {[round(x, 2) for x in b0.posts_x]}" if b0 else "POST_X = []",
             f"BLOCK_Y = {[round(y, 2) for y in fr.blocking_rows_y]}",
             f"N_ROWS = {dk.rows}",
             f"RAIL_POSTS = {[(p.x, p.y, p.kind[0]) for p in rl.posts] if rl else []}",
             f"RAIL_LF = {rl.rail_lf if rl else 0}",
             "BOM = ["]
    catmap = {"Flashing & waterproofing": "Hardware", "Fasteners": "Decking", "Fascia": "Decking", "Stairs": "Rail", "Site": "Hardware"}
    for ln in t.lines:
        cat = catmap.get(ln.category, ln.category)
        lines.append(f"    ({cat!r}, {ln.item!r}, {ln.order:g}, {ln.unit!r}, {ln.unit_cost:.2f}, {ln.source!r}, {ln.net:g}, {ln.why!r}),")
    lines.append("]")
    return "\n".join(lines)
