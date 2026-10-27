"""Renderers: markdown takeoff sheet, JSON, CSV order, cut list, and the GSX doc-skill job block."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import asdict
from typing import List, Optional

from .flags import Flag, run_flags
from .pricing import Pricing, gc_name, stair_specs
from .takeoff import Takeoff, CATEGORIES
from .units import ftin
from .catalog import rail_name


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
        w(f"| {gc_name(pricing.gc_lines, 'General conditions')} at cost | ${pricing.gc:,.2f} |")
        w(f"| Cost | ${pricing.cost:,.2f} |")
        w(f"| **Sell — check or ACH** at {pricing.gm:.1%} GM" + (f" ({pricing.rail_note})" if pricing.rail_note else "") + f" | **${pricing.sell:,.0f}** (${pricing.sell_per_sf:,.2f}/SF) |")
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
    fr_txt = (f"CEMCO cold-formed steel frame, all G90 — {s.framing.steel_joist} C-joists at {fr.spacing:g}\" OC, {s.framing.steel_track} track rims, boxed {s.framing.steel_joist} beams" if s.framing.system == "steel" else None) or (f"{s.framing.joist_species} #1 timber frame — {s.framing.post_size} posts, {s.framing.beams[0].size if s.framing.beams else ''} beams, "
              f"{s.framing.joist_size} joists at {fr.spacing:g}\"" if s.is_timber else
              f"{s.framing.joist_size} {s.framing.joist_species} frame at {fr.spacing:g}\", " + (f"{' / '.join(sorted({b.size for b in s.framing.beams}))} beam{'s' if len(s.framing.beams) > 1 else ''}, " if s.framing.beams else "")
              + f"{s.framing.post_size} posts")
    lv = levels_of(t)
    if lv:          # a deck on two or more levels says so, and every beam line counts
        _bs = sorted({b.size for b in L.beam_lines})
        fr_txt = (("Two-level" if len(lv) == 2 else f"{len(lv)}-level") + f" deck — {s.framing.joist_size} {s.framing.joist_species} frame at {fr.spacing:g}\", "
                  + (f"{' / '.join(_bs)} beam{'s' if len(L.beam_lines) > 1 else ''}, " if _bs else "") + f"{s.framing.post_size} posts")
    drink_words = (f"{s.railing.drink_rail_collection} {s.railing.drink_rail_color}".strip() if lv and s.railing.drink_rail_collection else s.railing.drink_rail_color)
    n_posts = L.n_footings
    foot = {"caisson": f"{n_posts} caissons", "diamond_pier": f"{n_posts} Diamond Pier footings", "concrete": f"{n_posts} concrete piers",
            "existing": (f"the {n_posts} existing columns and caissons" if s.framing.existing_posts else f"the {n_posts} existing caissons")}[s.framing.footing_type]
    w(f"{fr_txt} — on {foot}{' with stone column bases' if s.extras.stone_bases else ''}. "
      f"{s.decking.brand} {s.decking.collection} {s.decking.color} decking"
      + (f" with a {s.decking.border_color} border" if s.decking.border_color and s.decking.border_color != s.decking.color else "")
      + (f", {rail_words(s, rl.system)}" + ("" if lv and (rail_words(s, rl.system).endswith(" rail") or rail_words(s, rl.system) != rail_name(rl.system))
                                            else f" {'cable ' if rl.system == 'IRX' else ''}rail")
         + (f" with a {drink_words} drink rail" if s.railing.drink_rail else "") if rl else "")
      + (", hot-tub bay" + (f" in zone {s.extras.hot_tub_zone}" if s.extras.hot_tub_zone else "") if s.extras.hot_tub else "")
      + (lambda n: f", {n} lean-to roof cover{'s' if n > 1 else ''} with a {(s.extras.cover_roof_color + ' ') if s.extras.cover_roof_color else ''}{'standing seam' if s.extras.cover_roof.lower().startswith('standing') else 'shingle'} roof" if n else "")(len(__import__('decktakeoff.spec', fromlist=['covers_of']).covers_of(s))) + ".")
    w("")
    if lv:
        w(f"**{L.deck_sf:g} SF** on {'two' if len(lv) == 2 else len(lv)} levels · " + " and ".join(f"**{ftin(v['height_in'])}** ({v['name'].lower()})" for v in lv) + " above grade"
          + (", engineered" if s.extras.engineered else "") + f" · **{sm['design_load'].split(':')[0].split(' (')[0]}** design load")
    else:
        w(f"**{L.deck_sf} SF** · {len(L.zones)} zone{'s' if len(L.zones) > 1 else ''} · **{ftin(s.geometry.height_in)}** above grade"
          + (", engineered" if s.extras.engineered else "") + f" · **{sm['design_load'].split(':')[0].split(' (')[0]}** design load")
    if s.client or s.site.address:
        w(("Prepared for " + s.client + (f" · {s.site.address}, {s.site.city}" if s.site.address else "")) if s.client else (f"Prepared for the owner of {s.site.address}, {s.site.city}" if s.site.address else "Prepared for the owner"))
    w("")
    w("## PRICE")
    if s.extras.show_financing:
        w(f"**Total investment ${p.retail:,.0f}** — financed, no money down")
        w("- 12 months no payments, no down payment")
        w("- 18 months no payments, no down payment")
        w(f"- 6.99% for 10 years — about ${p.monthly:,.0f}/month")
        w(f"**Check or ACH: ${p.sell:,.0f}** ({(1 - p.sell / p.retail) * 100:.0f}% savings)")
    else:
        w(f"**Price: ${p.sell:,.0f}** — check or ACH")
    w("")
    w("## WHAT THE PRICE INCLUDES")
    if s.extras.price_breakdown:
        w("| Item | Value |")
        w("|---|---:|")
        for k, v in p.allocation:
            w(f"| {k} | ${v:,.0f} |")
    else:                                    # owner: no per-item prices to the homeowner — the scope, then the total
        w("| Item | |")
        w("|---|---:|")
        for k, v in p.allocation:
            w(f"| {k} | included |")
    w(f"| **Total, check or ACH** | **${p.sell:,.0f}** |")
    if s.extras.show_financing:
        w(f"| **Total, financed** | **${p.retail:,.0f}** |")
    w("")
    if s.extras.engineering_note and not p.engineering:
        w(f"**Engineering.** {s.extras.engineering_note}")
        w("")
    if p.engineering:
        lo, hi = p.engineering
        w(f"**Engineering — ${lo:,.0f} to ${hi:,.0f}.** Stamped drawings by a Colorado engineer ({s.site.ground_snow_psf:g} psf snow"
          + (", timber frame" if s.is_timber else "") + (", caissons" if s.framing.footing_type == "caisson" else "") + (", hot-tub bay" if s.extras.hot_tub else "")
          + f"). {_company(s)} provides the engineer and bills the engineering at cost, with no markup. You own the stamped set. It is separate from the deck price above.")
        w("")
    w("## INCLUDED — what it is")
    w("| Element | Selection |")
    w("|---|---|")
    _inc0 = len(out)                         # the rows from here are the job's to override (extras.included)
    from .catalog import decking_facts, RAIL_SYSTEMS
    f = decking_facts(s.decking.collection)
    if lv:
        w("| Levels | " + "; ".join(f"{v['name']}: {v['sf']:g} SF, {ftin(v['height_in'])} above grade" for v in lv)
          + (f"; {ftin(abs(lv[1]['height_in'] - lv[0]['height_in']))} between them" if len(lv) == 2 else "") + ". |")
    _brk = any(v["part"].layout.divider_x or (v["part"].layout.plan and v["part"].layout.plan.dividers) for v in lv)
    w(f"| Decking | {s.decking.brand} {f['material']} {s.decking.collection}, {s.decking.color}"
      + (f"; picture frame{' and dividers' if s.decking.dividers else ''} in {s.decking.border_collection or s.decking.collection} {s.decking.border_color}" if s.decking.border_color else "")
      + (f"; picture frame{' and breaker boards' if _brk else ''} in the same {s.decking.color}" if lv and s.geometry.picture_frame and not s.decking.border_color else "")
      + f". {'Square-shoulder' if s.decking.profile == 'square' else 'Grooved'} boards, {ftin(s.deck_gap)} gaps, {'no fascia' if not s.decking.fascia else ('a HardieTrim skirt around the frame (' + s.extras.hardie_color + ')' if (s.extras.hardie_skirt and s.extras.hardie_color) else ('a HardieTrim skirt around the frame' if s.extras.hardie_skirt else 'matching fascia'))}. {(f['fire'] + '; ') if (s.site.wui_fire_zone or f.get('wui')) else ''}{f['warranty']}. |")
    if s.railing.existing_parapet and s.railing.parapet_note:
        w(f"| Railing | {s.railing.parapet_note} |")
    elif rl and s.railing.existing_parapet:
        w(f"| Railing | The existing stucco parapet stays on the deck edges. {s.decking.brand} {rl.system} Rail, {rl.color}, {rl.height:g}\" on the new stair and landings. |")
    elif rl:
        rs = RAIL_SYSTEMS.get(rl.system, {})
        w(f"| Railing | {s.decking.brand} {rail_words(s, rl.system)}{' cable rail' if rs.get('cable') else (' Rail' if rail_name(rl.system) == rl.system else '')}, {rl.color}, {rl.height:g}\"{', no bottom rail' if rs.get('cable') else ''}"
          + (f"; {drink_words} drink rail on top" if s.railing.drink_rail else "") + f". {rl.rail_lf} LF. |")
    if lv and L.stairs:
        w("| Stairs | " + "; ".join(f"{getattr(ss, 'name', None) or 'Stair'}: {stair_words(ss, st, True)}" for ss, st in zip(stair_specs(t), L.stairs)) + ". |")
    if lv and step_face_words(t):
        w(f"| Step face | {step_face_words(t)}. |")
    lt = lights_of(t)
    if lt["total"]:
        _tr = lt["transformer"].lower()
        _pl, _pw = post_light_terms(t)
        w("| Lighting | " + " and ".join(x for x in ((f"{lt['riser']} LED riser lights (one in every riser)" if lt["riser"] else ""),
                                                    (f"{lt['post_cap']} LED {_pl} ({_pw})" if lt["post_cap"] else ""),
                                                    (f"{lt['other']} more LED lights" if lt["other"] else "")) if x)
          + (("; low voltage, on a transformer" + (" with a photocell and timer" if "photo" in _tr and "timer" in _tr else
                                                     (" with a photocell" if "photo" in _tr else (" with a timer" if "timer" in _tr else "")))) if lt["transformer"] else "") + ". |")
    if s.is_timber:
        w(f"| Timbers | Douglas fir #1 {s.framing.post_size} posts, {s.framing.beams[0].size if s.framing.beams else ''} beams, {s.framing.joist_size} joists at {fr.spacing:g}\"; "
          + ("unfinished, end grain sealed" if s.framing.finish != "oil" else "dark walnut oil, two coats, end grain sealed") + (". Tub bay doubled" if s.extras.hot_tub else "") + ". |")
        w("| Finish | " + ("Base: unfinished Douglas fir, which weathers gray. Dark walnut oil finish is priced in Options." if s.framing.finish != "oil" else "Dark walnut oil, two coats on every timber.") + " |")
    elif lv:
        w(f"| Frame | {composite_frame_words(t)} |")
    else:
        w(f"| Frame | {sm['joists']}; {sm['rims']}; {'; '.join(sm['beams'])}. |")
    if s.extras.stone_bases:
        w(f"| Column bases | Stone veneer 2'x2' x 3' with a 24\" stone cap at all {n_posts} posts. |")
    _fd = sm['posts'] if s.framing.footing_type == "existing" else sm['posts'].split(' on ')[-1]
    if s.framing.footing_type == "diamond_pier":
        _np = int(sum(l.order for l in t.lines if l.category == "Footings" and l.item.startswith("Diamond Pier")))
        _fd = f"{_np or L.n_footings} Diamond Pier foundations ({s.framing.footing_model}" + ("; upsized where a cover post and the deck share a pier" if any(l.item.startswith("Upgrade to Diamond Pier") for l in t.lines) else "") + ") — no excavation"
    w(f"| Foundation | {(_fd[0].upper() + _fd[1:]) if _fd else ''}" + (f" (frost depth {ftin(s.site.frost_depth_in)})" if s.framing.footing_type in ('caisson', 'concrete') else "") + ". |")
    w(f"| Design load | {sm['design_load'].replace(' · engineered', '')}" + (", stamped by a Colorado engineer" if s.extras.engineered else "")
      + (". Colorado Wildfire Resiliency Code practice: Class A decking, noncombustible rail, metal flashing at every wall" if s.site.wui_fire_zone else "") + ". |")
    if s.framing.system == "steel":
        w(f"| Hardware | Galvanized steel clip angles and self-drilling screws throughout the frame; {s.decking.brand} {s.decking.fastener_system or 'CONCEALoc'} hidden fasteners in the field "
          "and color-matched plugs on the picture frame, every screw the steel-frame type. |")
    else:
        w(f"| Hardware | {'All visible hardware black powder-coat. ' if s.framing.hardware_finish == 'black' else 'Simpson ZMAX galvanized connectors. '}"
          + f"{s.decking.fastener_system or 'Hidden'} fasteners{' with color-matched plugs' if (s.decking.fastener_system or '') == 'Cortex' else ''}"
          + (f" in the field; Cortex color-matched plugs on the picture frame{', benches' if s.geometry.benches else ''}{' and stairs' if stair_specs(t) else ''}"
             if (s.decking.border_fastener or '') == 'Cortex' and (s.decking.fastener_system or '') != 'Cortex' else "") + "."
          + ((" Color-matched TOPLoc screws on the fascia" + (" and the vertical boards between the levels" if step_face_words(t) else "") + ".")
             if lv and any(l.item.startswith("TimberTech TOPLoc") for l in t.lines) else "") + " |")
    from .spec import covers_of
    _cv = covers_of(s)
    if _cv:
        ss_ = s.extras.cover_roof.lower().startswith("standing")
        roof_ = ((f"{s.extras.cover_roof_color + ' ' if s.extras.cover_roof_color else ''}standing seam steel roof, 24 ga, "
                  + ("mechanically seamed for the low pitch" if s.extras.cover_roof_panel.lower().startswith("mech") else "snap-lock")
                  + ", over high-temp underlayment, with a snow bar across the low eave") if ss_ else "architectural shingles")
        fin_ = ", ".join(x for x in (("James Hardie soffit ceiling" if s.extras.cover_soffit else ""), ("HardieTrim fascia and rakes" if s.extras.cover_fascia else "")) if x)
        heights = "; ".join(f"{c['name']}: {c['clear_high_in']:g}\" clear at the house to {c['clear_low_in']:g}\" at the beam" for c in _cv if c.get("clear_high_in") and c.get("clear_low_in"))
        w(f"| Roof covers | {len(_cv)} lean-to cover{'s' if len(_cv) > 1 else ''} replaced: 6x6 posts on the "
          + {"diamond_pier": "Diamond Pier foundations", "caisson": "caissons", "concrete": "concrete piers"}.get(s.framing.footing_type, "existing caissons")
          + f", a new ledger on the house, 2x8 rafters at 16\", {roof_}"
          + (f"; {fin_}" + (f" in {s.extras.hardie_color}" if s.extras.hardie_color else "") if fin_ else "")
          + (f". {heights}" if heights else "") + (". The roll-down blinds are taken down, stored and rehung on the new beams" if s.extras.blinds_reinstall else "") + ". |")
    site_ = []
    if s.extras.demo_existing:
        site_.append("the existing deck" + (" and roof covers" if s.extras.demo_covers else "") + " removed and hauled off")
    if s.extras.under_deck_gravel:
        site_.append("6-mil poly and 2\" of gravel under the deck")
    if any(st.landing == "concrete pad" for st in stair_specs(t)):
        site_.append("a concrete landing pad at the stair")
    if site_:
        w(f"| Site | {'; '.join(site_)[0].upper() + '; '.join(site_)[1:]}. |")
    if s.extras.exclusions:
        w(f"| Not included | {'; '.join(s.extras.exclusions)}. |")
    out[_inc0:] = _included_rows(out[_inc0:], s)
    w("")
    w("## PLAN")
    if lv:
        w(f"{'Two' if len(lv) == 2 else len(lv)} levels · {L.deck_sf:g} SF · {ftin(L.finished_w)} along the house" + (f" · {rl.rail_lf} LF {rl.color} rail" if rl else ""))
        for v in lv:
            w(f"- **{v['name']}** — {v['sf']:g} SF, {ftin(v['height_in'])} above grade: "
              + "; ".join(f"{z.name} · {z.label or 'Zone ' + z.name}, {ftin(z.W)} x {ftin(z.D)}" for z in v["zones"]) + ".")
        w("Zones are named left to right standing in the yard facing the house.")
        for ss, st in zip(stair_specs(t), L.stairs):
            w(f"- {getattr(ss, 'name', None) or 'Stair'}: {stair_words(ss, st, True)}.")
    elif L.multi:
        w(f"{len(L.zones)} zones · {L.deck_sf} SF · {ftin(L.finished_w)} along the house · {ftin(s.geometry.height_in)} above grade"
          + (f" · {rl.rail_lf} LF {rl.color} rail" if rl else ""))
        for z in L.zones:
            w(f"- **{z.name} · {z.label or 'Zone ' + z.name}** — {ftin(z.W)} x {ftin(z.D)}" + (", hot-tub bay against the house" if z.hot_tub else "")
              + (", no rail on the wall side" if any(zz.privacy_wall for zz in s.geometry.zones if zz.name == z.name) else "") + ".")
        w("Zones are named left to right standing in the yard facing the house.")
    else:
        w(f"{sm['finished_frame']} · {L.deck_sf} SF · {ftin(s.geometry.height_in)} above grade" + (f" · {rl.rail_lf} LF rail" if rl else ""))
    for st in ([] if lv else sm["stairs"]):
        w(f"- {st}")
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
    if s.extras.engineered and s.extras.engineering_included:
        w("Next step: we will get the engineer letter.")
        if s.extras.proposal_note:
            w("")
            w(s.extras.proposal_note)
    elif s.extras.engineered:
        co = _company(s)
        w("Engineering first. This is a quote: the numbers depend on the stamped engineering, so the first step is engineering. "
          f"{co} provides the Colorado engineer and supplies the design package; you pay {co} the engineer's cost at no markup and you own the stamped set. "
          f"When the stamped set is in hand, {co} issues a fixed-price proposal on these numbers with the payment terms.")
        w("")
        w("Quote, not a contract: a fixed-price proposal follows the stamped engineering. Quote numbers hold 30 days. Renders and plan are design intent; the stamped engineering set governs structure, dimensions and locations.")
    else:
        w("This is a fixed-price proposal on the selections above. Check or ACH, or financed with approved credit. Numbers hold 30 days.")
        if s.extras.proposal_note:
            w("")
            w(s.extras.proposal_note)
    return "\n".join(out)


# ================================================================== two-level (composite) decks and lights: how they read to the homeowner
def levels_of(t) -> list:
    """A composite deck's levels in the job's part order: [dict(name, sf, height_in, zones, part)]; [] for an ordinary deck."""
    L = t.layout
    if not hasattr(L, "parts"):
        return []
    return [dict(name=p.name, sf=p.layout.deck_sf, height_in=float(p.spec.geometry.height_in), zones=p.layout.zones, part=p) for p in L.parts]


def columns_of(t) -> int:
    """The posts that carry the deck, each on its own footing (beam-line posts, edge posts, an inset stair's notch posts):
    the columns the homeowner sees."""
    return t.layout.n_footings


def lights_of(t) -> dict:
    """The deck's lights: {"riser", "post_cap", "other", "total", "transformer"} (all 0 / "" without lights) — from the
    lighting plan (lighting.py) when the takeoff has one, else counted off the order."""
    out = dict(riser=0, post_cap=0, other=0, total=0, transformer="")
    plan = getattr(t, "lighting", None)
    if plan is not None and any(l.category == "Lighting" for l in t.lines):
        out.update(riser=int(plan.n_riser), post_cap=int(plan.n_cap), total=int(plan.n_riser + plan.n_cap))
        tr = next((l.item for l in t.lines if l.category == "Lighting" and "transformer" in l.item.lower()), "")
        out["transformer"] = tr or ("transformer" if plan.transformers else "")
        return out
    for l in t.lines:
        it = l.item.lower()
        if l.category != "Lighting" and "light" not in it:
            continue
        if any(k in it for k in ("transformer", "photocell", "timer", "wire", "cable", "connector", "splice", "hub")):
            if "transformer" in it and not out["transformer"]:
                out["transformer"] = l.item
            continue
        if l.unit.lower() not in ("ea", "each", "pc", "pcs"):
            continue
        if "riser" in it or "step" in it:
            out["riser"] += int(l.order)
        elif "post" in it and "cap" in it:
            out["post_cap"] += int(l.order)
        else:
            out["other"] += int(l.order)
    out["total"] = out["riser"] + out["post_cap"] + out["other"]
    return out


def post_light_terms(t) -> tuple:
    """How the post lights read on this job: (plural label, where) — "post accent lights", "on the deck side of every rail post,
    just below the drink rail" when the drink rail runs over the posts (no caps), else "post-cap lights", "on top of every rail
    post" — from the lighting plan (lighting.post_label / post_where)."""
    plan = getattr(t, "lighting", None)
    if plan is not None:
        try:
            from .lighting import post_label, post_where
            return post_label(plan), post_where(plan)
        except Exception:
            pass
    return "post-cap lights", "on top of every rail post"


def stair_words(ss, st, composite: bool = False) -> str:
    """One stair as the homeowner reads it: risers, width, flights and landings, where it lands; an inset stair and its skirt."""
    from .takeoff import inches_frac
    g = st.geo
    txt = f"{g.risers} risers at {inches_frac(g.riser_in)}, {ftin(st.width)} wide"
    if len(g.flights) > 1 and ss is not None:
        lands = " and ".join(f"{ftin(a)} x {ftin(b)}" for a, b in ss.landings) if ss.landings else "a"
        turn = {"switchback": "turn back", "left": "turn left", "right": "turn right", "straight": "continue"}.get(ss.turn, ss.turn)
        txt += f": {g.flights[0].risers} down to the {lands} landing, {turn}, " + " then ".join(f"{fg.risers} down" for fg in g.flights[1:])
    land = getattr(ss, "landing", "") if ss is not None else ""
    if composite:      # where it lands ("... 6 down to the yard" after the flights; ", down to the lower level" on one flight)
        to = {"deck": "to the lower level", "grade": "to the yard", "concrete pad": "to a concrete pad in the yard"}.get(land, "")
        txt += ((" " + to) if (len(g.flights) > 1 and ss is not None) else (", down " + to)) if to else ""
    if ss is not None and getattr(ss, "inset", False):
        txt += ", set into the upper level so the bottom riser is flush with the face between the levels"
    sides = max(list(getattr(st, "flight_rails", None) or []) + [int(getattr(st, "stair_rail_sides", 0) or 0)])
    if sides:
        txt += " · rail on both sides" if sides >= 2 else " · rail on one side"
    elif ss is not None and getattr(ss, "handrail", ""):
        txt += " · a handrail on one side"
    if st.landing_rail_lf:
        txt += " · guard rail on the landing"
    return txt


def step_face_words(t) -> str:
    """The face between two levels when the job clads it (geometry.step_skirt on a part or the job): its height and the
    vertical boards; "" otherwise."""
    s = t.spec
    sk = getattr(s.geometry, "step_skirt", None)
    if not sk and hasattr(t.layout, "parts"):
        sk = next((getattr(p.spec.geometry, "step_skirt", None) for p in t.layout.parts if getattr(p.spec.geometry, "step_skirt", None)), None)
    if not sk:
        return ""
    drop = sk.get("drop_in")
    if drop is None:
        lv = levels_of(t)
        drop = abs(lv[1]["height_in"] - lv[0]["height_in"]) if len(lv) == 2 else None
    inset = any(getattr(ss, "inset", False) for ss in stair_specs(t))
    return ((f"The {ftin(float(drop))} face between the levels" if drop else "The face between the levels") + (" and the inset stair's sides" if inset else "")
            + f" clad in {s.decking.collection} {s.decking.fascia_color or s.decking.color} fascia boards installed vertically")


def composite_frame_words(t) -> str:
    """The frame of a deck on two or more levels, the way the homeowner reads it: joists, rims, beams by level, the columns."""
    s, L = t.spec, t.layout
    lv = levels_of(t)
    fr = L.frame
    wood = "pressure-treated" if not s.is_timber else "Douglas fir"
    out = f"{s.framing.joist_size} {wood} joists at {fr.spacing:g}\" on center, doubled {s.framing.joist_size} rims"
    sizes = sorted({b.size for b in L.beam_lines})
    if sizes:
        kinds = {b.kind for b in L.beam_lines}
        per = ", ".join(f"{len(v['part'].layout.beam_lines)} under the {v['name'].lower()}" for v in lv if v["part"].layout.beam_lines)
        from .catalog import beam_species_words
        out += (f", {' / '.join(sizes)} {beam_species_words(L.beam_lines)} {'drop ' if kinds == {'drop'} else ('flush ' if kinds == {'flush'} else '')}beams"
                + (f" ({per})" if len(lv) > 1 and per else ""))
    from .spec import post_words
    out += f", {columns_of(t)} {s.framing.post_size} {post_words(s)} columns"
    if s.framing.joist_tape:
        out += "; joist tape on every joist, rim" + (" and beam" if L.beam_lines else "")
    return out + "."


def _span(a: int, b: int) -> str:
    return f"Day {a}" if a == b else f"Days {a}–{b}"


def rail_words(s, system: str) -> str:
    """The rail system as the client documents name it (catalog.rail_name), less the "modern top rail" when the drink rail
    runs over the posts (railing.drink_rail_mount "over"): the drink-rail board takes the top rail's place."""
    nm = rail_name(system)
    if getattr(s.railing, "drink_rail", False) and str(getattr(s.railing, "drink_rail_mount", "") or "").lower() == "over":
        nm = re.sub(r",?\s*modern top rail\b", "", nm).strip(" ,")
    return nm


def foundation_words(t) -> tuple:
    """The deck's footings from the spec's footing type, as the client documents count and name them:
    (count, plural noun for a count, words) — Diamond Piers, caissons (diameter x depth), concrete piers, existing caissons."""
    s, L = t.spec, t.layout
    ft = s.framing.footing_type
    n = L.n_footings
    if ft == "diamond_pier":
        n = int(sum(l.order for l in t.lines if l.item.lower().startswith("diamond pier"))) or n
        return n, "Diamond Piers", f"{n} Diamond Pier foundations"
    if ft == "caisson":
        fr = L.frame
        dia = float(getattr(fr, "footing_dia_in", 0) or s.framing.caisson_dia_in)
        dep = getattr(fr, "footing_depth_in", None) or s.framing.caisson_depth_in
        return n, "caissons", f"{n} concrete caissons, {dia:g}\" across" + (f" and {ftin(float(dep))} deep" if dep else "")
    if ft == "concrete":
        return n, "concrete piers", f"{n} concrete piers"
    return n, "existing caissons", (f"the {n} existing columns and caissons" if s.framing.existing_posts else f"the {n} existing caissons")


def _included_rows(rows: List[str], s) -> List[str]:
    """extras.included — the job's own "What it is" rows over the engine's, [{title, text}] in order: a title the engine
    prints replaces that row in place (an empty text drops it); a new title goes in after the previous entry's row (the
    first ones at the top). Markdown table rows: a "|" or a line break in the text reads as "/" and a space."""
    inc = [e for e in (getattr(s.extras, "included", None) or []) if isinstance(e, dict) and str(e.get("title", "")).strip()]
    if not inc:
        return rows
    def title_of(r):
        m = re.match(r"\|\s*(.*?)\s*\|", r)
        return m.group(1).lower() if m else None
    out, cur = list(rows), 0
    for e in inc:
        ttl = str(e["title"]).strip()
        txt = re.sub(r"\s*\n\s*", " ", str(e.get("text") or "")).replace("|", "/").strip()
        i = next((k for k, r in enumerate(out) if title_of(r) == ttl.lower()), None)
        if i is not None and not txt:
            del out[i]; cur = i
        elif i is not None:
            out[i] = f"| {ttl} | {txt} |"; cur = i + 1
        elif txt:
            out.insert(cur, f"| {ttl} | {txt} |"); cur += 1
    return out


def _company(s) -> str:
    """Who the client documents say does the work: "GSX", or under another brand (extras.brand) that brand's name."""
    key = str(getattr(s.extras, "brand", "gs") or "gs").lower()
    if key == "gs":
        return "GSX"
    from .proposal_look import brand_of
    b = brand_of(key)
    return b.get("short") or b.get("name") or "GSX"


def timeline_of(s) -> Optional[dict]:
    """The job's own customer timeline (extras.timeline), or None: a schedule model's customer block — {title, precon {label,
    weeks, text, gantt_x}, rows [{key, option, title, label, days, first_day, last_day, gantt_x}], schedule_lines} — given
    inline, or as "path/to/schedule.json#Scenario" (that scenario's customer block; the first scenario without a name).
    s is a spec, or such a value itself."""
    tl = getattr(s.extras, "timeline", None) if hasattr(s, "extras") else s
    if not tl:
        return None
    if isinstance(tl, str):
        path, _, name = tl.partition("#")
        with open(path) as fh:
            d = json.load(fh)
        if "scenarios" in d:
            sc = d["scenarios"][name] if name else next(iter(d["scenarios"].values()))
            d = sc.get("customer", sc)
        tl = d
    if not isinstance(tl, dict):
        return None
    if hasattr(s, "extras"):                 # a timeline written for other footings than the spec's is out of date: say so, never print it
        ft = s.framing.footing_type
        said = " ".join([str((tl.get("precon") or {}).get("text", ""))] + [str(r.get("title") or r.get("label") or "") for r in tl.get("rows") or []]
                        + [str(x) for x in tl.get("schedule_lines") or []])
        if (ft != "diamond_pier" and re.search(r"(?i)diamond pier", said)) or (ft == "diamond_pier" and re.search(r"(?i)\bcaissons?\b", said)):
            raise ValueError(f"extras.timeline was written for other footings than the spec's ({ft}): re-run the schedule model for this spec, "
                             "or drop extras.timeline to print the generic day rates")
    return tl


def _schedule(t: Takeoff) -> List[str]:
    s, L = t.spec, t.layout
    tl = timeline_of(s)
    if tl and tl.get("schedule_lines"):        # the job's own timeline (a schedule model) instead of the generic day rates
        return list(tl["schedule_lines"])
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
    days.append(f"{_span(d+1, d+fd)} — posts " + ("and beams set" if L.beam_lines else "set, the doubled rims on them") + (" (first coat of oil if the finish option is taken)" if s.is_timber and s.framing.finish != 'oil' else "") + "."); d += fd
    jd = max(2, round(L.deck_sf / 120))
    days.append(f"{_span(d+1, d+jd)} — {'timber ' if s.is_timber else ''}frame, flashing at every wall" + (", tub bay doubled" if s.extras.hot_tub else "") + "."); d += jd
    dd = max(2, round(L.deck_sf / 200))
    days.append(f"{_span(d+1, d+dd)} — decking, borders first."); d += dd
    if L.rail:
        rd = max(1, round(L.rail.rail_lf / 40))
        _rn = rail_words(s, L.rail.system)
        days.append(f"{_span(d+1, d+rd)} — {_rn}" + ("" if hasattr(L, "parts") and (_rn.endswith(" rail") or _rn != rail_name(L.rail.system)) else " rail") + (" and drink rail" if s.railing.drink_rail else "") + (". Owner's electrician and plumber finish the tub circuit" if s.extras.hot_tub else "") + "."); d += rd
    if L.stairs:
        days.append(f"Day {d+1} — stairs" + (" and the box step" if any(getattr(st, 'build', '') == 'box' for st in L.stairs) and len(L.stairs) > 1 else "")
                    + (", the vertical boards on the face between the levels" if step_face_words(t) else "") + "."); d += 1
    lt = lights_of(t)
    if lt["total"]:
        days.append(f"Day {d+1} — low-voltage lighting: " + " and ".join(x for x in (("riser lights" if lt["riser"] else ""), (post_light_terms(t)[0] if lt["post_cap"] else ""),
                                                                                     ("deck lights" if lt["other"] else "")) if x)
                    + (" wired to the transformer" if lt["transformer"] else "") + "."); d += 1
    nb = len(s.geometry.benches or []); npl = len(s.geometry.planters or [])
    if nb or npl:
        bd = max(1, round(nb * 0.75 + npl * 0.5))
        what = " and ".join(x for x in ((f"built-in bench{'es' if nb > 1 else ''}" if nb else ""), (f"planter{'s' if npl > 1 else ''}" if npl else "")) if x)
        days.append(f"{_span(d+1, d+bd)} — {what}, wrapped in the deck boards."); d += bd
    if s.extras.stone_bases:
        days.append(f"Day {d+1} — stone bases and caps; end of construction."); d += 1
    else:
        days.append(f"Day {d+1} — final clean; end of construction."); d += 1
    days[0:0] = []
    return [f"{x}" for x in days] if not s.extras.engineered else days

