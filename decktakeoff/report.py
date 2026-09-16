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
    w(f"- **Rims** {sm['rims']}" + (" — hung in concealed-flange double hangers" if L.frame.hangers_double else " — hung in HU hangers"))
    for z in sm.get("zones") or []:
        w(f"- **Zone** {z}")
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
        w("| | |")
        w("|---|---:|")
        w(f"| Materials (raw) | ${pricing.materials:,.2f} |")
        w(f"| Materials x {pricing.material_factor:g} | ${pricing.materials_factored:,.2f} |")
        w(f"| Sales tax {pricing.tax_rate:.2%} on factored materials | ${pricing.tax:,.2f} |")
        w(f"| Labor (rate card) | ${pricing.labor:,.2f} |")
        w(f"| Work (carries the margin) | ${pricing.work:,.2f} |")
        w(f"| General conditions at cost | ${pricing.gc:,.2f} |")
        w(f"| Cost | ${pricing.cost:,.2f} |")
        w(f"| **Sell — check or ACH** at {pricing.gm:.1%} GM | **${pricing.sell:,.0f}** (${pricing.sell_per_sf:,.2f}/SF) |")
        w(f"| Sell at the 40% floor | ${pricing.sell_floor:,.0f} |")
        w(f"| **Financed** (÷ 0.93) | **${pricing.retail:,.0f}** · ${pricing.monthly:,.0f}/mo at 6.99% / 10 yr |")
        w(f"| Gross profit | ${pricing.gp:,.0f} |")
        if pricing.engineering:
            w(f"| Engineering (outside the price, at cost) | ${pricing.engineering[0]:,.0f}–${pricing.engineering[1]:,.0f} |")
        w("")
        w("Labor:")
        for i, q, u, r, e in pricing.labor_lines:
            w(f"- {i}: {q:g} {u} × ${r:g} = ${e:,.2f}")
        w("")
        w("General conditions (at cost, no margin):")
        for i, a, why in pricing.gc_lines:
            w(f"- {i}: ${a:,.0f}" + (f" — {why}" if why else ""))
        w("")
        w("What the price includes (sell values): " + " · ".join(f"{k} ${v:,.0f}" for k, v in pricing.allocation))
        if pricing.options:
            w("")
            w("Options (full installed deltas — cost / check / financed):")
            for o in pricing.options:
                w(f"- {o.name}: cost {o.cost:+,.0f} → check {o.check:+,.0f} / financed {o.financed:+,.0f}" + (f" — {o.note}" if o.note else ""))
        if pricing.dealer_fee_note:
            w("")
            w(f"Open: {pricing.dealer_fee_note}")
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


def quote_markdown(t: Takeoff, p: Pricing) -> str:
    """Client-facing quote in the Eagle's Nest layout: price, financing, what the price includes, what it is, plan,
    schedule, options, next step. Facts only — no flags, no costs, no margins."""
    s, L, sm = t.spec, t.layout, t.summary
    fr, dk, rl = L.frame, L.decking, L.rail
    out = []
    w = out.append
    pre = " · PRE-ENGINEERING" if s.extras.engineered else ""
    w(f"# QUOTE{pre}")
    w(f"## {s.job}")
    fr_txt = (f"{s.framing.joist_species} #1 timber frame — {s.framing.post_size} posts, {s.framing.beams[0].size if s.framing.beams else ''} beams, "
              f"{s.framing.joist_size} joists at {fr.spacing:g}\"" if s.is_timber else
              f"{s.framing.joist_size} {s.framing.joist_species} frame at {fr.spacing:g}\", {s.framing.beams[0].size if s.framing.beams else ''} beam, {s.framing.post_size} posts")
    n_posts = L.n_footings
    foot = {"caisson": f"{n_posts} caissons", "diamond_pier": f"{n_posts} Diamond Pier footings", "concrete": f"{n_posts} concrete piers"}[s.framing.footing_type]
    w(f"{fr_txt} — on {foot}{' with stone column bases' if s.extras.stone_bases else ''}. "
      f"{s.decking.brand} {s.decking.collection} {s.decking.color} decking"
      + (f" with a {s.decking.border_color} border" if s.decking.border_color and s.decking.border_color != s.decking.color else "")
      + (f", {rl.system} {'cable ' if rl.system == 'IRX' else ''}rail" + (f" with a {s.railing.drink_rail_color} drink rail" if s.railing.drink_rail else "") if rl else "")
      + (", hot-tub bay" + (f" in zone {s.extras.hot_tub_zone}" if s.extras.hot_tub_zone else "") if s.extras.hot_tub else "") + ".")
    w("")
    w(f"**{L.deck_sf} SF** · {len(L.zones)} zone{'s' if len(L.zones) > 1 else ''} · **{ftin(s.geometry.height_in)}** above grade"
      + (", engineered" if s.extras.engineered else "") + f" · **{s.site.ground_snow_psf:g} psf** snow design")
    if s.client or s.site.address:
        w(("Prepared for " + s.client + (f" · {s.site.address}, {s.site.city}" if s.site.address else "")) if s.client else (f"Prepared for the owner of {s.site.address}, {s.site.city}" if s.site.address else "Prepared for the owner"))
    w("")
    w("## PRICE")
    w(f"**Total investment ${p.retail:,.0f}** — financed, no money down")
    w("- 12 months no payments, no down payment")
    w("- 18 months no payments, no down payment")
    w(f"- 6.99% for 10 years — about ${p.monthly:,.0f}/month")
    w(f"**Check or ACH: ${p.sell:,.0f}** (7% savings)")
    w("")
    w("## WHAT THE PRICE INCLUDES")
    w("| Item | Value |")
    w("|---|---:|")
    for k, v in p.allocation:
        w(f"| {k} | ${v:,.0f} |")
    w(f"| **Total, check or ACH** | **${p.sell:,.0f}** |")
    w(f"| **Total, financed** | **${p.retail:,.0f}** |")
    w("")
    if p.engineering:
        lo, hi = p.engineering
        w(f"**Engineering — ${lo:,.0f} to ${hi:,.0f}.** Stamped drawings by a Colorado engineer ({s.site.ground_snow_psf:g} psf snow"
          + (", timber frame" if s.is_timber else "") + (", caissons" if s.framing.footing_type == "caisson" else "") + (", hot-tub bay" if s.extras.hot_tub else "")
          + "). GSX provides the engineer and bills the engineering at cost, with no markup. You own the stamped set. It is separate from the deck price above.")
        w("")
    w("## INCLUDED — what it is")
    w("| Element | Selection |")
    w("|---|---|")
    from .catalog import decking_facts, RAIL_SYSTEMS
    f = decking_facts(s.decking.collection)
    w(f"| Decking | {s.decking.brand} {f['material']} {s.decking.collection}, {s.decking.color}"
      + (f"; picture frame{' and dividers' if s.decking.dividers else ''} in {s.decking.border_collection or s.decking.collection} {s.decking.border_color}" if s.decking.border_color else "")
      + f". {'Square-shoulder' if s.decking.profile == 'square' else 'Grooved'} boards, {ftin(s.deck_gap)} gaps, {'no fascia' if not s.decking.fascia else 'matching fascia'}. {f['fire']}; {f['warranty']}. |")
    if rl:
        rs = RAIL_SYSTEMS.get(rl.system, {})
        w(f"| Railing | {s.decking.brand} {rl.system}{' cable rail' if rs.get('cable') else ' Rail'}, {rl.color}, {rl.height:g}\"{', no bottom rail' if rs.get('cable') else ''}"
          + (f"; {s.railing.drink_rail_color} drink rail on top" if s.railing.drink_rail else "") + f". {rl.rail_lf} LF. |")
    if s.is_timber:
        w(f"| Timbers | Douglas fir #1 {s.framing.post_size} posts, {s.framing.beams[0].size if s.framing.beams else ''} beams, {s.framing.joist_size} joists at {fr.spacing:g}\"; "
          + ("unfinished, end grain sealed" if s.framing.finish != "oil" else "dark walnut oil, two coats, end grain sealed") + (". Tub bay doubled" if s.extras.hot_tub else "") + ". |")
        w("| Finish | " + ("Base: unfinished Douglas fir, which weathers gray. Dark walnut oil finish is priced in Options." if s.framing.finish != "oil" else "Dark walnut oil, two coats on every timber.") + " |")
    else:
        w(f"| Frame | {sm['joists']}; {sm['rims']}; {'; '.join(sm['beams'])}. |")
    if s.extras.stone_bases:
        w(f"| Column bases | Stone veneer 2'x2' x 3' with a 24\" stone cap at all {n_posts} posts. |")
    w(f"| Foundation | {sm['posts'].split(' on ')[-1].capitalize()}" + (f" (frost depth {ftin(s.site.frost_depth_in)})" if s.framing.footing_type in ('caisson', 'concrete') else "") + ". |")
    w(f"| Design load | {s.site.ground_snow_psf:g} psf snow" + (", stamped by a Colorado engineer" if s.extras.engineered else "")
      + (". Colorado Wildfire Resiliency Code practice: Class A decking, noncombustible rail, metal flashing at every wall" if s.site.wui_fire_zone else "") + ". |")
    w(f"| Hardware | {'All visible hardware black powder-coat. ' if s.framing.hardware_finish == 'black' else 'Simpson ZMAX galvanized connectors. '}"
      + f"{s.decking.fastener_system or 'Hidden'} fasteners{' with color-matched plugs' if (s.decking.fastener_system or '') == 'Cortex' else ''}. |")
    w("")
    w("## PLAN")
    if L.multi:
        w(f"{len(L.zones)} zones · {L.deck_sf} SF · {ftin(L.finished_w)} along the house · {ftin(s.geometry.height_in)} above grade"
          + (f" · {rl.rail_lf} LF {rl.color} rail" if rl else ""))
        for z in L.zones:
            w(f"- **{z.name} · {z.label or 'Zone ' + z.name}** — {ftin(z.W)} x {ftin(z.D)}" + (", hot-tub bay against the house" if z.hot_tub else "")
              + (", no rail on the wall side" if any(zz.privacy_wall for zz in s.geometry.zones if zz.name == z.name) else "") + ".")
        w("Zones are named left to right standing in the yard facing the house.")
    else:
        w(f"{sm['finished_frame']} · {L.deck_sf} SF · {ftin(s.geometry.height_in)} above grade" + (f" · {rl.rail_lf} LF rail" if rl else ""))
    for st in sm["stairs"]:
        w(f"- Stair {st}")
    w("")
    w("## SCHEDULE")
    days = _schedule(t)
    for i, d in enumerate(days, 1):
        w(f"{i}. {d}")
    w("")
    if p.options:
        w("## OPTIONS — upgrades and downgrades")
        for o in p.options:
            sign = "add" if o.financed >= 0 else "deduct"
            w(f"- {o.name} — {sign} ${abs(o.financed):,.0f} (${abs(o.check):,.0f} check/ACH)" + (f" — {o.note}" if o.note else ""))
        w("")
    w("## NEXT STEP")
    if s.extras.engineered:
        w("Engineering first. This is a quote: the numbers depend on the stamped engineering, so the first step is engineering. "
          "GSX provides the Colorado engineer and supplies the design package; you pay GSX the engineer's cost at no markup and you own the stamped set. "
          "When the stamped set is in hand, GSX issues a fixed-price proposal on these numbers with the payment terms.")
        w("")
        w("Quote, not a contract: a fixed-price proposal follows the stamped engineering. Quote numbers hold 30 days. Renders and plan are design intent; the stamped engineering set governs structure, dimensions and locations.")
    else:
        w("This is a fixed-price proposal on the selections above. Check or ACH, or financed with approved credit. Numbers hold 30 days.")
    return "\n".join(out)


def _schedule(t: Takeoff) -> List[str]:
    s, L = t.spec, t.layout
    days = []
    if s.extras.engineered:
        days.append("Engineering & ordering (2–3 weeks). Stamped drawings, materials ordered, samples approved.")
    d = 1
    days.append(f"Day {d} — protection, utilities located (811)" + (", old deck out" if s.extras.demo_existing else "") + ".")
    n_posts = L.n_footings
    if s.framing.footing_type == "caisson":
        days.append(f"Days {d+1}–{d+2} — layout, {n_posts} caissons augered and poured."); d += 2
        days.append(f"Days {d+1}–{d+2} — concrete cure."); d += 2
    elif s.framing.footing_type == "concrete":
        days.append(f"Days {d+1}–{d+2} — layout, {n_posts} piers dug and poured; cure."); d += 2
    else:
        days.append(f"Day {d+1} — layout, {n_posts} Diamond Piers driven, ledger set."); d += 1
    fd = max(2, round(L.deck_sf / 150))
    days.append(f"Days {d+1}–{d+fd} — posts and beams set" + (" (first coat of oil if the finish option is taken)" if s.is_timber and s.framing.finish != 'oil' else "") + "."); d += fd
    jd = max(2, round(L.deck_sf / 120))
    days.append(f"Days {d+1}–{d+jd} — {'timber ' if s.is_timber else ''}frame, flashing at every wall" + (", tub bay doubled" if s.extras.hot_tub else "") + "."); d += jd
    dd = max(2, round(L.deck_sf / 200))
    days.append(f"Days {d+1}–{d+dd} — decking, borders first."); d += dd
    if L.rail:
        rd = max(1, round(L.rail.rail_lf / 40))
        days.append(f"Days {d+1}–{d+rd} — {L.rail.system} rail" + (" and drink rail" if s.railing.drink_rail else "") + (". Owner's electrician and plumber finish the tub circuit" if s.extras.hot_tub else "") + "."); d += rd
    if L.stairs:
        days.append(f"Day {d+1} — stairs."); d += 1
    if s.extras.stone_bases:
        days.append(f"Day {d+1} — stone bases and caps; end of construction."); d += 1
    else:
        days.append(f"Day {d+1} — final clean; end of construction."); d += 1
    days[0:0] = []
    return [f"{x}" for x in days] if not s.extras.engineered else days

