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
                       load_lb=max([z.frame.footing_load_lb for z in (L.zones or [])] + [L.frame.footing_load_lb]), capacity_lb=L.frame.footing_capacity_lb, dia_in=L.frame.footing_dia_in, depth_in=L.frame.footing_depth_in),
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


def quote_markdown(t: Takeoff, p: Pricing, today: Optional[str] = None) -> str:
    """Client-facing quote in the Eagle's Nest layout: price, financing, what the price includes, what it is, plan,
    schedule, options, next step. Facts only — no flags, no costs, no margins. today: the document's date ("October 28, 2026";
    default today) — the price holds 30 days from it."""
    s, L, sm = t.spec, t.layout, t.summary
    fr, dk, rl = L.frame, L.decking, L.rail
    out = []
    w = out.append
    pre = " · PRE-ENGINEERING" if s.extras.engineered else ""
    w(f"# QUOTE{pre}")
    w(f"## {s.job}")
    fr_txt = (f"CEMCO cold-formed steel frame, all G90 — {s.framing.steel_joist} C-joists at {fr.spacing:g}\" OC, {s.framing.steel_track} track rims, boxed {s.framing.steel_joist} beams" if s.framing.system == "steel" else None) or (f"{s.framing.joist_species} #1 timber frame — {s.framing.post_size} posts, {s.framing.beams[0].size if s.framing.beams else ''} beams, "
              f"{s.framing.joist_size} joists at {fr.spacing:g}\"" if s.is_timber else
              f"{s.framing.joist_size} {s.framing.joist_species} frame at {fr.spacing:g}\", " + (f"{' / '.join(sorted({b.size for b in L.beam_lines}))} beam{'s' if len(L.beam_lines) > 1 else ''}, " if L.beam_lines else "")
              + f"{s.framing.post_size} posts")
    lv = levels_of(t)
    if lv:          # a deck on two or more levels says so, and every beam line counts
        _bs = sorted({b.size for b in L.beam_lines})
        fr_txt = (("Two-level" if len(lv) == 2 else f"{len(lv)}-level") + f" deck — {s.framing.joist_size} {s.framing.joist_species} frame at {fr.spacing:g}\", "
                  + (f"{' / '.join(_bs)} beam{'s' if len(L.beam_lines) > 1 else ''}, " if _bs else "") + f"{s.framing.post_size} posts")
    n_posts = L.n_footings
    foot = {"caisson": f"{n_posts} caissons", "diamond_pier": f"{_deck_piers(t)} Diamond Pier footings", "concrete": f"{n_posts} concrete piers",
            "existing": (f"the {n_posts} existing columns and caissons" if s.framing.existing_posts else f"the {n_posts} existing caissons")}[s.framing.footing_type]
    _dw = drink_rail_words(s) if s.railing.drink_rail else ""
    w(f"{fr_txt} — on {foot}{' with stone column bases' if s.extras.stone_bases else ''}. "
      f"{s.decking.brand} {s.decking.collection} {s.decking.color} decking"
      + (f" with a {s.decking.border_color} border" if s.decking.border_color and s.decking.border_color != s.decking.color else "")
      + (f", {rail_words(s, rl.system)}" + ("" if (re.search(r"\brail\b", rail_words(s, rl.system), re.I) or (lv and rail_words(s, rl.system) != rail_name(rl.system)))
                                            else f" {'cable ' if rl.system == 'IRX' else ''}rail")
         + (f" with {'an' if _dw[0].lower() in 'aeiou' else 'a'} {_dw}" if _dw else "") if rl else "")
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
        w(f"**Financed price: ${p.retail:,.0f}** — {finance_words(p.monthly)}, with approved credit")
        w("- Also available with approved credit: 12 or 18 months with no payments")
        w(f"**Check or ACH price: ${p.sell:,.0f}** — {(1 - p.sell / p.retail) * 100:.0f}% less than the financed price; it applies to payment by check or ACH")
    else:
        w(f"**Price: ${p.sell:,.0f}** — check or ACH")
    w("")
    w("## WHAT THE PRICE INCLUDES")
    if s.extras.price_breakdown:
        w("| Item | Value |")
        w("|---|---:|")
        for k, v in client_allocation(t, p):
            w(f"| {k} | ${v:,.0f} |")
    else:                                    # owner: no per-item prices to the homeowner — the scope, then the total
        w("| Item | |")
        w("|---|---:|")
        for k, v in client_allocation(t, p):
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
    w(f"| Decking | {s.decking.brand} {s.decking.collection}, {s.decking.color}"     # the line by its name, as the chips and the materials table read it
      + (f"; picture frame{' and dividers' if s.decking.dividers else ''} in {s.decking.border_collection or s.decking.collection} {s.decking.border_color}" if s.decking.border_color else "")
      + (f"; picture frame{' and breaker boards' if _brk else ''} in the same {s.decking.color}" if lv and s.geometry.picture_frame and not s.decking.border_color else "")
      + f". {board_profile_words(t)}{'; ' if ';' in board_profile_words(t) else ', '}{ftin(s.deck_gap)} gaps{'' if (s.decking.fascia and s.extras.hardie_skirt) else (', no fascia' if not s.decking.fascia else ', matching fascia')}. {(f['fire'] + '; ') if (s.site.wui_fire_zone or f.get('wui')) else ''}{f['warranty']}. |")
    if s.decking.fascia and s.extras.hardie_skirt:      # the James Hardie trim on the fascia (and the risers cut from it): its own row
        _hr = hardie_risers(t)
        w(f"| {'Fascia and risers' if _hr else 'Fascia'} | {hardie_words(s)}, on the fascia{' and every riser' if _hr else ''}. |")
    if s.railing.existing_parapet and s.railing.parapet_note:
        w(f"| Railing | {s.railing.parapet_note} |")
    elif rl and s.railing.existing_parapet:
        w(f"| Railing | The existing stucco parapet stays on the deck edges. {s.decking.brand} {rl.system} Rail, {rl.color}, {rl.height:g}\" on the new stair and landings. |")
    elif rl:
        rs = RAIL_SYSTEMS.get(rl.system, {})
        w(f"| Railing | {rail_product(s, rl.system)}{' cable rail' if rs.get('cable') else (' Rail' if rail_name(rl.system) == rl.system else '')}, {rl.color}, {rl.height:g}\"{', no bottom rail' if rs.get('cable') else ''}"
          + (f"; {drink_rail_words(s)}" if s.railing.drink_rail else "") + f". {rl.rail_lf} LF. |")
    if lv and L.stairs:
        w("| Stairs | " + "; ".join(f"{getattr(ss, 'name', None) or 'Stair'}: {stair_words(ss, st, True)}" for ss, st in zip(stair_specs(t), L.stairs)) + ". |")
    if lv and step_face_words(t):
        w(f"| Step face | {step_face_words(t)}. |")
    lt = lights_of(t)
    if lt["total"]:
        _pl, _pw = post_light_terms(t)
        _rw = riser_where_words(t) or "one in every riser"
        w("| Lighting | " + " and ".join(x for x in ((f"{lt['riser']} {riser_finish_words(t)}LED riser lights ({_rw})" if lt["riser"] else ""),
                                                    (f"{lt['post_cap']} LED {_pl} ({_pw})" if lt["post_cap"] else ""),
                                                    (f"{lt['other']} more LED lights" if lt["other"] else "")) if x)
          + (f"; low voltage, on {transformer_words(t)}" if lt["transformer"] else "") + ". |")
    if s.is_timber:
        w(f"| Timbers | Douglas fir #1 {s.framing.post_size} posts, {s.framing.beams[0].size if s.framing.beams else ''} beams, {s.framing.joist_size} joists at {fr.spacing:g}\"; "
          + ("unfinished, end grain sealed" if s.framing.finish != "oil" else "dark walnut oil, two coats, end grain sealed") + (". Tub bay doubled" if s.extras.hot_tub else "") + ". |")
        w("| Finish | " + ("Base: unfinished Douglas fir, which weathers gray. Dark walnut oil finish is priced in Options." if s.framing.finish != "oil" else "Dark walnut oil, two coats on every timber.") + " |")
    elif lv:
        w(f"| Frame | {composite_frame_words(t)} |")
    elif s.framing.system == "steel":
        w(f"| Frame | {'; '.join(x for x in [sm['joists'], sm['rims']] + list(sm['beams']) if x)}. |")
    else:
        w(f"| Frame | {frame_words(t)} |")
    if s.extras.stone_bases:
        w(f"| Column bases | Stone veneer 2'x2' x 3' with a 24\" stone cap at all {n_posts} posts. |")
    _fd = ((posts_on_words(t) if not lv else sm['posts']) if s.framing.footing_type == "existing" else       # caissons by count and size, each level's own
           foundation_words(t)[2] + (" with stone column bases" if s.extras.stone_bases else "") if s.framing.footing_type == "caisson" else sm['posts'].split(' on ')[-1])
    if s.framing.footing_type == "diamond_pier":
        _fd = f"{_deck_piers(t)} {diamond_pier_words(s.framing.footing_model)}" + ("; upsized where a cover post and the deck share a pier" if any(l.item.startswith("Upgrade to Diamond Pier") for l in t.lines) else "")
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
    if s.extras.exclusions:                  # one row, each item a sentence: the job's own words and capitalization
        w(f"| Not included | {'. '.join(x_.strip().rstrip('.') for x_ in s.extras.exclusions)}. |")
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
    for st in ([] if lv else _plan_stair_lines(t)):
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
        w(f"Quote, not a contract: a fixed-price proposal follows the stamped engineering. This quote holds through {price_holds_through(today)}. Renders and plan are design intent; the stamped engineering set governs structure, dimensions and locations.")
    else:
        w("This is a fixed-price proposal on the selections above. The check or ACH price applies to payment by check or ACH"
          + ("; the financed price applies with approved credit" if s.extras.show_financing else "") + f". This price holds through {price_holds_through(today)}.")
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
        if l.category != "Lighting" and not re.search(r"\blights?\b", it):     # a light by the word ("one per flight" is a handrail)
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


def transformer_words(t) -> str:
    """The lights' transformers as the order has them: "a transformer with a photocell and timer", "two transformers, each with a
    photocell and timer"; "" without one."""
    tr = lights_of(t)["transformer"].lower()
    if not tr:
        return ""
    n = int(sum(l.order for l in t.lines if l.category == "Lighting" and "transformer" in l.item.lower())) or 1
    ctl = "a photocell and timer" if "photo" in tr and "timer" in tr else "a photocell" if "photo" in tr else "a timer" if "timer" in tr else ""
    return ("a transformer" + (f" with {ctl}" if ctl else "")) if n == 1 else (f"{_NUM_WORDS.get(n, str(n))} transformers" + (f", each with {ctl}" if ctl else ""))


def light_brand(t) -> str:
    """The maker of every light fixture on the order ("TimberTech"), from the Lighting lines' own names; "" when they differ."""
    fx = {l.item.split()[0] for l in t.lines if l.category == "Lighting" and re.search(r"\blights?\b", l.item.lower())
          and not re.search(r"(?i)transformer|cable|connector|staple|wire|splice|hub|timer|photocell", l.item)}
    return fx.pop() if len(fx) == 1 else ""


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
    """The rail system as the client documents name it (catalog.rail_name), less the "modern top rail" whenever the job has a
    drink rail: the drink-rail board on its brackets takes the top rail's place (the IRX universal panel cover under it), between
    the posts or over them."""
    nm = rail_name(system)
    if getattr(s.railing, "drink_rail", False):
        nm = re.sub(r",?\s*modern top rail\b", "", nm).strip(" ,")
    return nm


def drink_rail_words(s) -> str:
    """The drink rail as the client documents name it: "TimberTech Reserve Antique Leather drink rail between the posts". On
    Impression Rail Express the board sits between the posts or over them (railing.drink_rail_mount); on another rail it lies
    on the drink-rail brackets on top of the rail (the takeoff's own read)."""
    r = s.railing
    board = " ".join(x for x in (s.decking.brand, r.drink_rail_collection or s.decking.collection, r.drink_rail_color or s.decking.color) if x)
    where = (("on top of the posts" if str(r.drink_rail_mount or "").lower() == "over" else "between the posts")
             if str(r.system or "").startswith(("IRX", "Impression")) else "on top of the rail")
    return f"{board} drink rail {where}"


def rail_product(s, system: str) -> str:
    """The rail by its maker and name (rail_words): "TimberTech Impression Rail Express, vertical aluminum balusters", "TimberTech
    Fulton", "Cinch" — the catalog's brand for the rail system, else the decking's."""
    from .catalog import RAIL_SYSTEMS
    nm = rail_words(s, system)
    br = RAIL_SYSTEMS.get(system, {}).get("brand") or s.decking.brand
    return nm if nm.lower().startswith(br.lower()) else f"{br} {nm}"


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
        def size(fr):
            dia = float(getattr(fr, "footing_dia_in", 0) or s.framing.caisson_dia_in)
            dep = getattr(fr, "footing_depth_in", None) or s.framing.caisson_depth_in
            return f"{dia:g}\" across" + (f" and {ftin(float(dep))} deep" if dep else "")
        lv = [(p_.layout.n_footings, p_.name, size(p_.layout.frame)) for p_ in getattr(L, "parts", None) or []]
        if len({sz for _, _, sz in lv}) > 1:     # two levels on caissons of different sizes: each level's own
            return n, "caissons", f"{n} concrete caissons: " + "; ".join(f"{k} under the {nm.lower()}, {sz}" for k, nm, sz in lv)
        return n, "caissons", f"{n} concrete caissons, {size(L.frame)}"
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
        from pathlib import Path as _P
        p_ = _P(path)
        if not p_.is_absolute() and not p_.exists():          # a repo-relative path ("jobs/<job>_site/schedule.json")
            p_ = _P(__file__).resolve().parent.parent / path
        with open(p_) as fh:
            d = json.load(fh)
        if "scenarios" in d:
            sc = d["scenarios"][name] if name else next(iter(d["scenarios"].values()))
            d = sc.get("customer", sc)
        tl = d
    if not isinstance(tl, dict):
        return None
    if hasattr(s, "extras"):                 # a timeline written for other footings than the spec's is out of date: warn, never print it
        ft = s.framing.footing_type
        said = " ".join([str((tl.get("precon") or {}).get("text", ""))] + [str(r.get("title") or r.get("label") or "") for r in tl.get("rows") or []]
                        + [str(x) for x in tl.get("schedule_lines") or []])
        if (ft != "diamond_pier" and re.search(r"(?i)diamond pier", said)) or (ft == "diamond_pier" and re.search(r"(?i)\bcaissons?\b", said)):
            import warnings
            warnings.warn(f"extras.timeline was written for other footings than the spec's ({ft}) and is left out: the proposal prints no "
                          "Schedule and the quote the generic day rates until the schedule model is re-run for this spec", stacklevel=2)
            return None
    return tl


_NUM = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def height_words(t) -> str:
    """The stat's "above grade": where the deck's height is measured — at the stair it lands from when one rises exactly that far
    ("above grade at the center stair"), a box step that drops less never; else plainly."""
    s = t.spec
    for ss, sl in zip(s.stairs or [], getattr(t.layout, "stairs", None) or []):
        g = getattr(sl, "geo", None)
        if g is not None and getattr(sl, "build", "") != "box" and abs(g.risers * g.riser_in - s.geometry.height_in) < 0.5:
            return "above grade at the " + (getattr(ss, "name", None) or "stair").lower()
    return "above grade"


def schedule_rows(t: Takeoff) -> List[dict]:
    """The engine's own day plan at the generic day rates: [dict(first, last, text)] in order, first/last None for the time
    before day 1 (the engineering on an engineered quote). The light wiring runs with the frame; the fixtures go in after the
    rail and the stairs. Box steps that wrap a corner count as one step (stair_groups)."""
    s, L = t.spec, t.layout
    rows = []

    def add(a, b, txt):
        rows.append(dict(first=a, last=b, text=txt))
    if s.extras.engineered:
        add(None, None, "Engineering & ordering (2–3 weeks). Stamped drawings, materials ordered, samples approved.")
    d = 1
    add(d, d, "protection, utilities located" + ((", old deck" + (" and roof covers" if s.extras.demo_covers else "") + " out") if s.extras.demo_existing else ""))
    n_posts, ft = L.n_footings, s.framing.footing_type
    ledger = any(getattr(z.frame, "ledger", True) for z in L.zones)      # a freestanding frame sets no ledger
    if ft == "caisson":
        add(d + 1, d + 2, f"layout, {n_posts} caissons augered and poured"); d += 2
        add(d + 1, d + 2, "concrete cure"); d += 2
    elif ft == "concrete":
        add(d + 1, d + 2, f"layout, {n_posts} piers dug and poured; cure"); d += 2
    elif ft == "existing":                   # the caissons stay: new post bases on them, or the existing columns carry the beams
        add(d + 1, d + 1, (f"layout on the {n_posts} existing columns and caissons" if s.framing.existing_posts else
                           f"layout, new post bases epoxy-set on the {n_posts} existing caissons") + (", ledger set" if ledger else "")); d += 1
    else:                                    # the piers as the quote's Foundation row counts them
        add(d + 1, d + 1, f"layout, {_deck_piers(t)} Diamond Piers driven" + (", ledger set" if ledger else "")); d += 1
    lt = lights_of(t)
    fd = max(2, round(L.deck_sf / 150))
    add(d + 1, d + fd, ("beams set on the existing columns" if ft == "existing" and s.framing.existing_posts else
                        "posts " + ("and beams set" if L.beam_lines else "set, the doubled rims on them"))
        + (" (first coat of oil if the finish option is taken)" if s.is_timber and s.framing.finish != 'oil' else "")); d += fd
    jd = max(2, round(L.deck_sf / 120))
    add(d + 1, d + jd, f"{'timber ' if s.is_timber else ''}frame, flashing at every wall" + (", tub bay doubled" if s.extras.hot_tub else "")
        + ("; the low-voltage wire for the lights pulled through the frame" if lt["total"] else "")); d += jd
    dd = max(2, round(L.deck_sf / 200))
    add(d + 1, d + dd, "decking, borders first"); d += dd
    if L.rail:
        rd = max(1, round(L.rail.rail_lf / 40))
        _rn = rail_words(s, L.rail.system)
        if s.railing.drink_rail:              # the rail by its name, then the drink rail ("Impression Rail Express and the drink rail")
            _rn = _rn.split(",")[0]
        add(d + 1, d + rd, _rn + ("" if (re.search(r"\brail\b", _rn, re.I) or (hasattr(L, "parts") and _rn != rail_name(L.rail.system))) else " rail")
            + (" and the drink rail" if s.railing.drink_rail else "") + (". Owner's electrician and plumber finish the tub circuit" if s.extras.hot_tub else "")); d += rd
    if L.stairs:
        _g = stair_groups(t)
        _nbox = sum(1 for g in _g if g["box"])
        _nbx = sum(len(g["members"]) for g in _g if g["box"])          # box steps mitered into one step are still two box steps to build
        add(d + 1, d + 1, "stairs" + ((f" and the {_NUM.get(_nbx, _nbx)} box steps" if _nbx > 1 else " and the box step") if _nbox and len(_g) > _nbox else "")
            + (", the vertical boards on the face between the levels" if step_face_words(t) else "")); d += 1
    if lt["total"]:
        add(d + 1, d + 1, "low-voltage lighting: " + " and ".join(x for x in (("riser lights" if lt["riser"] else ""), (post_light_terms(t)[0] if lt["post_cap"] else ""),
                                                                              ("deck lights" if lt["other"] else "")) if x)
            + (" set and wired to the transformer" if lt["transformer"] else " set")); d += 1
    nb = len(s.geometry.benches or []); npl = len(s.geometry.planters or [])
    if nb or npl:
        bd = max(1, round(nb * 0.75 + npl * 0.5))
        what = " and ".join(x for x in ((f"built-in bench{'es' if nb > 1 else ''}" if nb else ""), (f"planter{'s' if npl > 1 else ''}" if npl else "")) if x)
        add(d + 1, d + bd, f"{what}, wrapped in the deck boards"); d += bd
    add(d + 1, d + 1, "stone bases and caps; end of construction" if s.extras.stone_bases else "final clean; end of construction")
    return rows


def _schedule(t: Takeoff) -> List[str]:
    tl = timeline_of(t.spec)
    if tl and tl.get("schedule_lines"):        # the job's own timeline (a schedule model) instead of the generic day rates
        return list(tl["schedule_lines"])
    return [(r["text"] if r["first"] is None else f"{_span(r['first'], r['last'])} — {r['text']}.") for r in schedule_rows(t)]


def engine_timeline(t: Takeoff) -> dict:
    """The day plan (schedule_rows) as a customer timeline in timeline_of's shape, for the proposal's Gantt when the job has no
    schedule model of its own: the time before day 1 (the engineering, or the order at signing), then a bar per stretch of work."""
    rows, pre = [], None
    for i, r in enumerate(schedule_rows(t)):
        txt = r["text"][0].upper() + r["text"][1:]
        if r["first"] is None:
            pre = dict(label="Before day 1", text=txt.rstrip("."), gantt_x=[0, 1])
            continue
        rows.append(dict(key=f"d{i}", option="base", title=txt, label=txt, days=_span(r["first"], r["last"]), first_day=r["first"],
                         last_day=r["last"], gantt_x=[r["first"], r["last"] + 1]))
    nd = max((r["last_day"] for r in rows), default=0)
    if pre is None:
        pre = dict(label="Before day 1", text="Materials ordered at signing; we confirm the start date with you", gantt_x=[0, 1])
    return dict(title=f"{nd} working days on site, weather permitting", rows=rows, precon=pre)


# ================================================================== the homeowner's words: one step where box steps wrap a corner,
# the price breakdown's labels, the finance terms, the date the price holds through, the payments, the materials and warranties
def stair_groups(t) -> List[dict]:
    """The stairs as the homeowner reads them, in order: [dict(name, short, box, members=[(stair spec, layout stair)])]. Box steps
    on neighboring outline sides that miter into one step at the corner (scene.box_step_miters) are one step — "Left box step —
    left side" + "Left box step — front angle" read "Left box step (wraps the corner)" (short: "Left box step"); every other
    stair keeps its own name. The crew documents keep every stair by its own name."""
    L = t.layout
    pairs = list(zip(stair_specs(t), L.stairs))
    outline = getattr(t.spec.geometry, "outline", None) or []
    sides = []
    if outline and not hasattr(L, "parts"):
        try:
            from .scene import box_step_miters
            sides = sorted(int(str(k).split(":")[1]) for k in box_step_miters(t.spec, L.stairs) if str(k).startswith("edge:"))
        except Exception:
            sides = []
    n = len(outline)
    root = {i: i for i in sides}
    for i in sides:                          # a chain of neighboring mitered sides is one step
        j = i % n + 1
        if j in root:
            r_, q_ = root[i], root[j]
            root = {k: (r_ if v == q_ else v) for k, v in root.items()}
    groups, by_root = [], {}
    for ss, st in pairs:
        sd = str(getattr(st, "side", "") or getattr(ss, "side", ""))
        box_ = (getattr(st, "build", "") or getattr(ss, "build", "")) == "box" and not (getattr(st, "option", "") or getattr(ss, "option", ""))
        r_ = root.get(int(sd.split(":")[1])) if (box_ and sd.startswith("edge:") and sd.split(":")[1].isdigit()) else None    # only the box steps the miter joins
        if r_ is not None and r_ in by_root:
            by_root[r_]["members"].append((ss, st))
            continue
        g = dict(members=[(ss, st)], box=(getattr(st, "build", "") or getattr(ss, "build", "")) == "box")
        groups.append(g)
        if r_ is not None:
            by_root[r_] = g
    for g in groups:
        names = [getattr(ss, "name", None) or "" for ss, _ in g["members"]]
        if len(names) > 1:
            heads = {nm.split(" — ")[0].strip() for nm in names}
            head = heads.pop() if len(heads) == 1 and "" not in heads else "Box step"
            g["short"], g["name"] = head, f"{head} (wraps the corner{'s' if len(names) > 2 else ''})"
        else:
            g["short"] = g["name"] = names[0]
    return groups


def _widths(mem) -> str:
    """A step that wraps a corner: its width along each side ("6'-1\" along the left side and 5'-8\" along the front angle")."""
    return " and ".join(f"{ftin(st.width)} along the {(getattr(ss, 'name', '') or '').split(' — ', 1)[1]}" if " — " in (getattr(ss, "name", "") or "")
                        else ftin(st.width) for ss, st in mem)


def _plan_stair_lines(t) -> List[str]:
    """The quote's PLAN lines for the stairs: the takeoff's own line for each stair; box steps that wrap a corner as one line."""
    from .takeoff import inches_frac
    lines, out = list(t.summary["stairs"]), []
    at = {id(st): i for i, st in enumerate(t.layout.stairs)}      # a stair's own line by its place in the layout
    for g in stair_groups(t):
        mem = g["members"]
        if len(mem) == 1:
            k = at.get(id(mem[0][1]), len(lines))
            out.append(lines[k] if k < len(lines) else g["name"])
        else:
            geo = mem[0][1].geo
            out.append(f"{g['name']}: {geo.risers} risers @ {inches_frac(geo.riser_in)}, {geo.treads} tread{'s' if geo.treads != 1 else ''}, framed box, {_widths(mem)}")
    return out


def stair_rows(t) -> List[tuple]:
    """The at-a-glance stair rows: [(name, "3 risers at 7\", 5'-7\" wide")] — box steps that wrap a corner as one row."""
    from .takeoff import inches_frac
    out = []
    for g in stair_groups(t):
        mem = g["members"]
        geo = mem[0][1].geo
        out.append((g["name"] or "Stair", f"{geo.risers} risers at {inches_frac(geo.riser_in)}, " + (f"{ftin(mem[0][1].width)} wide" if len(mem) == 1 else _widths(mem))))
    return out


def riser_finish_words(t) -> str:
    """The riser lights' finish and a space ("matte white "), from the lighting plan's riser light; "" without one."""
    plan = getattr(t, "lighting", None)
    if plan is None or not plan.n_riser:
        return ""
    try:
        from .lighting import product
        fin = str(product(plan.cfg, plan.cfg["riser_sku"]).get("finish") or "")
    except Exception:
        fin = ""
    return f"{fin} " if fin else ""


def riser_where_words(t) -> str:
    """Where the riser lights are, in the homeowner's words: the lighting plan's own riser_where when every riser is lit ("one in
    every riser"), else by stair — "3 in the center stair, 2 in the left box step" (box steps that wrap a corner as one step)."""
    plan = getattr(t, "lighting", None)
    if plan is None or not plan.n_riser:
        return ""
    from .lighting import riser_where
    if plan.every_riser:
        return riser_where(plan)
    short = {}
    for g in stair_groups(t):
        for ss, _ in g["members"]:
            short[getattr(ss, "name", None) or ""] = g["short"]
    n = {}
    for nm, nr, k, _ in plan.stairs:
        if nr:
            key = short.get(nm) or nm
            n[key] = n.get(key, 0) + nr * k
    return ", ".join(f"{v} in the {key[0].lower() + key[1:]}" for key, v in n.items())


def client_allocation(t, p) -> List[tuple]:
    """p.allocation in the homeowner's words, the values as they are (they sum to the price): the stairs by their client names
    (box steps that wrap a corner as one step), the free riser lights by where they are ("5 LED riser lights — 3 in the center
    stair, 2 in the left box step — included at no charge"), the drink rail by its board and where it sits."""
    s = t.spec
    cl = {}
    for g in stair_groups(t):
        for ss, _ in g["members"]:
            cl[getattr(ss, "name", None) or ""] = g["name"]
    plan = getattr(t, "lighting", None)
    out = []
    for k, v in p.allocation:
        parts, tail = k.split(" + "), ""
        if parts[-1].endswith(" & stair rail"):
            parts[-1], tail = parts[-1][:-len(" & stair rail")], " & stair rail"
        if all(x in cl for x in parts) and any(cl[x] != x for x in parts):
            k = " + ".join(dict.fromkeys(cl[x] for x in parts)) + tail
        elif v == 0 and plan is not None and plan.n_riser and "riser light" in k and "no charge" in k:
            k = f"{plan.n_riser} LED riser lights — {riser_where_words(t)} — included at no charge"
        elif s.railing.drink_rail and "drink rail" in k.lower() and " + " not in k:
            k = "Drink rail — " + re.sub(r" drink rail (between|on top of) the (posts|rail)$", r", \1 the \2", drink_rail_words(s))
        out.append((k, v))
    return out


def finance_words(monthly: float) -> str:
    """The pricebook's finance terms: "120 monthly payments of $562 at 6.99% APR (10 years)"."""
    from .catalog import PRICEBOOK
    yrs = int(PRICEBOOK["finance_years"])
    return f"{yrs * 12} monthly payments of ${monthly:,.0f} at {round(PRICEBOOK['finance_rate'] * 100, 2):g}% APR ({yrs} years)"


def price_holds_through(today=None, days: int = 30) -> str:
    """The date the price holds through, 30 days from the document's date (a date, or "October 28, 2026"; default today):
    "November 27, 2026"."""
    from datetime import date, datetime, timedelta
    d = today
    if isinstance(today, str):               # the date inside a date line: "October 28, 2026", "Oct 28, 2026", "28 October 2026", "2026-10-28"
        d = None
        for pat, fmts in ((r"[A-Z][a-z]+\.? \d{1,2}, \d{4}", ("%B %d, %Y", "%b %d, %Y")), (r"\d{1,2} [A-Z][a-z]+\.? \d{4}", ("%d %B %Y", "%d %b %Y")),
                          (r"\d{4}-\d{2}-\d{2}", ("%Y-%m-%d",))):
            m = re.search(pat, today)
            for f in (fmts if m else ()):
                try:
                    d = datetime.strptime(m.group(0).replace(".", "").replace("Sept ", "Sep "), f).date()
                    break
                except ValueError:
                    pass
            if d:
                break
    d = (d if isinstance(d, date) else date.today()) + timedelta(days=days)
    return f"{d:%B} {d.day}, {d.year}"


# the payments: the owner's template (gsx-deck-docs build_proposal.py) — 10% at signing, 40% at the material order, 40% with the
# frame complete, 10% at the end of construction — on the check or ACH price
PAYMENTS = [(0.10, "At signing"), (0.40, "At material order"), (0.40, "Frame complete"), (0.10, "End of construction")]


def payment_schedule(sell: float) -> List[tuple]:
    """[(share, milestone, amount)] on the check or ACH price in whole dollars, the last payment taking the rounding (the
    amounts sum to the price)."""
    out, paid = [], 0
    for i, (f, when) in enumerate(PAYMENTS):
        a = round(sell) - paid if i == len(PAYMENTS) - 1 else round(sell * f)
        paid += a
        out.append((f"{f:.0%}", when, a))
    return out


def board_profile_words(t) -> str:
    """The deck boards' profile as the takeoff orders them: "Grooved boards in the field; square-shouldered boards on the picture
    frame, dividers and stair treads" (borders, dividers and treads are square-edge stock), or "Square-shouldered boards"."""
    s, L = t.spec, t.layout
    if s.decking.profile == "square":
        return "Square-shouldered boards"
    where = [x for x, on in (("picture frame", s.geometry.picture_frame), ("dividers", s.decking.dividers or getattr(L, "divider_x", None)),
                             ("stair treads", bool(L.stairs))) if on]
    return "Grooved boards" + ((" in the field; square-shouldered boards on the " + (", ".join(where[:-1]) + " and " + where[-1] if len(where) > 1 else where[0]))
                               if where else "")


def hardie_words(s) -> str:
    """The James Hardie trim as the client documents name it: "James Hardie trim (Hardie Trim), ColorPlus Arctic White" (the color from
    extras.hardie_color or the end of extras.hardie_skirt; none set, or "TBD": "color to be selected")."""
    col = s.extras.hardie_color or re.sub(r"^[\d/ x.\"']+", "", s.extras.hardie_skirt or "").strip()
    return "James Hardie trim (Hardie Trim), ColorPlus " + (col if col and "tbd" not in col.lower() else "(color to be selected)")


def hardie_risers(t) -> bool:
    """The stair risers are cut from the Hardie trim (the takeoff's HardieTrim riser line, with a Hardie skirt)."""
    return bool(t.spec.extras.hardie_skirt) and any(l.item.startswith("HardieTrim") and "riser" in l.item for l in t.lines)


def _deck_piers(t) -> int:
    """The deck's Diamond Piers as the client documents count them (the quote's Foundation row, the day plan, the materials):
    the order's Footings lines, else the layout's footings."""
    return int(sum(l.order for l in t.lines if l.category == "Footings" and l.item.startswith("Diamond Pier"))) or t.layout.n_footings


def diamond_pier_words(model: str) -> str:
    """'DP-50/50' -> 'Diamond Pier DP-50 foundations with 50" steel pins — precast concrete heads, no poured concrete'."""
    m = re.match(r"\s*(DP-\d+)\s*/\s*(\d+)", model or "")
    return (f"Diamond Pier {m.group(1)} foundations with {m.group(2)}\" steel pins" if m else f"Diamond Pier foundations ({model})") + \
        " — precast concrete heads, no poured concrete"


def _joist_product(s) -> tuple:
    """(product, what it is) for the joists: ProWood TrueFrame by name for the SYP 2x8 / 2x10 / 2x12 TrueFrame GSX orders
    ("ProWood TrueFrame 2x10", "#1 Southern Yellow Pine, pressure-treated for ground contact"), else (the size and the wood, "")."""
    sz = s.framing.joist_size
    if (s.framing.joist_species or "").upper().startswith("SYP") and sz in ("2x8", "2x10", "2x12") and "true" in (s.framing.joist_grade or "").lower():
        return f"ProWood TrueFrame {sz}", "#1 Southern Yellow Pine, pressure-treated for ground contact"
    return f"{sz} {'Douglas fir' if s.is_timber else 'pressure-treated'}", ""


def joist_words(s, spacing: float) -> str:
    """The joists in the homeowner's words: 'ProWood TrueFrame 2x10 (#1 Southern Yellow Pine, pressure-treated for ground contact)
    at 12" on center', else '2x10 pressure-treated joists at 16" on center'."""
    prod, what = _joist_product(s)
    return (f"{prod} ({what})" if what else f"{prod} joists") + f" at {spacing:g}\" on center"


def _rim_words(s, sides: bool = False) -> str:
    return f"{({1: 'single', 2: 'doubled', 3: 'tripled'}).get(int(s.rim_plies), f'{s.rim_plies}-ply')} {s.framing.joist_size} {'side ' if sides else ''}rims"


_NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def beam_line_words(t) -> str:
    """The beams by the layout's beam lines (every line counts, as the takeoff orders them): "three 6x12 Douglas fir drop beams",
    "two doubled 2x10 pressure-treated SYP drop beams", "a 4x10 and two 4x12 Douglas fir drop beams", "a doubled 4x10 Douglas fir
    flush beam as the front rim"; "" without beams."""
    from .catalog import beam_species_words
    bl = list(t.layout.beam_lines or [])
    if not bl:
        return ""
    n_of = {}
    for b in bl:
        n_of[b.size] = n_of.get(b.size, 0) + 1
    def size_words(sz, n):
        m = re.match(r"\((\d)\)(.+)", sz)
        nm = (({2: "doubled ", 3: "tripled "}.get(int(m.group(1))) or f"{m.group(1)}-ply ") + m.group(2)) if m else sz
        return (("an" if nm.startswith(("8x", "11")) else "a") if n == 1 else _NUM_WORDS.get(n, str(n))) + " " + nm
    kinds = {b.kind for b in bl}
    front = len(bl) == 1 and bl[0].label.startswith("FRONT FLUSH")
    return (" and ".join(size_words(sz, n) for sz, n in sorted(n_of.items())) + f" {beam_species_words(bl)} "
            + ("drop " if kinds == {"drop"} else "flush " if kinds == {"flush"} else "") + ("beams" if len(bl) > 1 else "beam") + (" as the front rim" if front else ""))


def _frame_parts(t, tape: bool = True) -> list:
    """The frame of a deck on one level, part by part: the rims, the beams (beam_line_words), the joist tape (the joists are
    joist_words)."""
    s, L = t.spec, t.layout
    front = any(b.label.startswith("FRONT FLUSH") for b in L.beam_lines or [])     # a flush beam is the front rim: the rims are the sides
    ledger = any(getattr(z.frame, "ledger", True) for z in L.zones)                # freestanding only when no zone hangs on a ledger
    out = [_rim_words(s, front) + ("" if ledger else " all around (freestanding: no ledger on the house)")]
    out += [beam_line_words(t)] if L.beam_lines else []
    if tape and s.framing.joist_tape:
        out.append("joist tape on every joist, rim and beam" if L.beam_lines else "joist tape on every joist and rim")
    return out


def frame_words(t, tape: bool = True) -> str:
    """The frame of a deck on one level in the homeowner's words: the joists, the rims, the beams, the joist tape."""
    return "; ".join([joist_words(t.spec, t.layout.zones[0].frame.spacing)] + _frame_parts(t, tape)) + "."


def materials_rows(t) -> List[tuple]:
    """The proposal's materials and warranties, every component by name: [(component, product, what it is, warranty)] — the
    decking, the trim, the rail, the lights, then the frame, the posts, the foundations, the connectors, the ledger and its
    flashing and the joist tape as the takeoff orders them; the makers' limited warranty words (catalog) where a maker publishes
    one to the homeowner, "" otherwise. The fasteners as the order has them (the owner's template's hidden-fastener and face-screw
    rows)."""
    from .catalog import decking_facts, RAIL_WARRANTY, LIGHT_WARRANTY, HARDIE_TRIM_WARRANTY, FASTENER_WARRANTY, TRUEFRAME_WARRANTY, DIAMOND_PIER_WARRANTY
    s, L = t.spec, t.layout
    d, rl = s.decking, L.rail
    fs = d.fastener_system or "hidden"
    bp = board_profile_words(t)
    rows = [("Decking", f"{d.brand} {d.collection}, {d.color}",
             f"{decking_facts(d.collection)['material']}; {bp[0].lower() + bp[1:]}" + ("; matching fascia" if d.fascia and not s.extras.hardie_skirt else ""),
             decking_facts(d.collection)["warranty"])]
    if d.border_color and d.border_color != d.color:
        bc = d.border_collection or d.collection
        rows.append(("Picture frame", f"{d.brand} {bc}, {d.border_color}", "Square-shouldered boards around the edge", decking_facts(bc)["warranty"]))
    fl_ = [l for l in t.lines if l.category == "Fasteners"]
    if any("CONCEALoc" in l.item for l in fl_):
        rows.append(("Hidden fasteners", "TimberTech CONCEALoc", "Hidden clips in the field, every joist", FASTENER_WARRANTY))
    cx_ = [l for l in fl_ if l.item.startswith("Cortex")]
    if cx_:
        on_ = re.search(r"— (.+)$", cx_[0].item)
        rows.append(("Face screws", "TimberTech Cortex", "Screws with color-matched plugs" + (f" on the {on_.group(1)}" if on_ else ""), FASTENER_WARRANTY))
    ct_ = next((l for l in fl_ if l.item.startswith("Starborn Cap-Tor") and "step-face skirt" not in l.item), None)
    if ct_ is not None:
        pt_ = [p_.rsplit(" ", 1)[0] for p_ in (re.search(r"\(([^)]*)\)", ct_.why or "") or [None, ""])[1].split(" · ") if p_]
        where_ = {"first row": "the first field row", "border": "the picture frame", "fascia": "the fascia", "stairs": "the stair treads"}
        at_ = [where_.get(p_, p_) for p_ in pt_]
        rows.append(("Face screws", "Starborn Cap-Tor xd", "Color-matched screws" + (" at " + (", ".join(at_[:-1]) + " and " + at_[-1] if len(at_) > 1 else at_[0]) if at_ else ""), ""))
    if d.fascia and s.extras.hardie_skirt:
        hr = hardie_risers(t)                # James Hardie's warranty names trim; a riser is not a listed use until Technical Services OKs it
        rows.append(("Fascia and risers" if hr else "Fascia", hardie_words(s), "On the fascia" + (" and every riser" if hr else ""), HARDIE_TRIM_WARRANTY + (", on the fascia" if hr else "")))
    if rl and not s.railing.existing_parapet:
        from .catalog import RAIL_SYSTEMS
        nm, _, rest = rail_product(s, rl.system).partition(", ")        # the rail's own maker (Cinch), else the decking's
        nm += " cable rail" if RAIL_SYSTEMS.get(rl.system, {}).get("cable") else (" Rail" if rail_name(rl.system) == rl.system else "")
        rows.append(("Railing", f"{nm}, {rl.color}", (rest[0].upper() + rest[1:] + ", " if rest else "") + f"{rl.height:g}\" high; {rl.rail_lf:g} LF",
                     RAIL_WARRANTY.get(rl.system, "")))
        if s.railing.drink_rail:
            dc = s.railing.drink_rail_collection or d.collection
            where = drink_rail_words(s).split(" drink rail ", 1)[-1]
            rows.append(("Drink rail", f"{d.brand} {dc}, {s.railing.drink_rail_color or d.color}", where[0].upper() + where[1:], decking_facts(dc)["warranty"]))
    lt = lights_of(t)
    if lt["total"]:                          # the lights' maker and the transformers as the order has them; the maker's warranty for TimberTech lights
        _pl, br = post_light_terms(t)[0], light_brand(t)
        rows.append(("Lighting", f"{br + ' ' if br else ''}LED lights", "; ".join(x for x in ((f"{lt['post_cap']} {_pl}" if lt["post_cap"] else ""),
                                                                                            (f"{lt['riser']} {riser_finish_words(t)}riser lights" if lt["riser"] else ""),
                                                                                            (f"{lt['other']} more lights" if lt["other"] else "")) if x)
                     + (f"; {transformer_words(t)}" if lt["transformer"] else ""), LIGHT_WARRANTY if br == "TimberTech" else ""))
    from .spec import covers_of
    _cv = covers_of(s)
    if _cv:                                  # the roof covers, in the quote's own words
        rf = (f"{s.extras.cover_roof_color} " if s.extras.cover_roof_color else "") + ("standing seam steel roof, 24 ga" if s.extras.cover_roof.lower().startswith("standing") else "architectural shingle roof")
        rows.append(("Roof cover" + ("s" if len(_cv) > 1 else ""), rf[0].upper() + rf[1:],
                     ("A lean-to cover" if len(_cv) == 1 else f"{str(_NUM_WORDS.get(len(_cv), len(_cv))).capitalize()} lean-to covers") + " on 6x6 posts, a ledger on the house, 2x8 rafters at 16\""
                     + "".join(x for x in (("; James Hardie soffit" if s.extras.cover_soffit else ""), ("; James Hardie trim on the fascia and rakes" if s.extras.cover_fascia else ""))), ""))
    fr, ft = L.zones[0].frame, s.framing.footing_type
    if s.framing.system == "steel":
        rows.append(("Frame", "CEMCO cold-formed steel, G90", f"{s.framing.steel_joist} C-joists at {fr.spacing:g}\" on center; {s.framing.steel_track} track rims; "
                     f"boxed {s.framing.steel_joist} beams; galvanized clip angles and self-drilling screws", ""))
        sp_ = steel_posts_words(t)
        if sp_:
            rows.append(("Posts", f"{s.framing.post_size} {_post_wood(t)}".strip(), sp_[0].upper() + sp_[1:], ""))
    elif s.is_timber:
        rows.append(("Frame", "Douglas fir #1 timbers", f"{s.framing.post_size} posts, {s.framing.beams[0].size if s.framing.beams else ''} beams, "
                     f"{s.framing.joist_size} joists at {fr.spacing:g}\" on center", ""))
    else:
        prod, what = _joist_product(s)
        if hasattr(L, "parts"):              # two levels: the rims, the beams by level and the columns (composite_frame_words) after the joists
            cw = composite_frame_words(t).rstrip(".").split("; joist tape")[0].split(", ", 1)
            body = f"joists at {fr.spacing:g}\" on center" + (f", {cw[1]}" if len(cw) > 1 else "")
        else:
            body = "; ".join([f"joists at {fr.spacing:g}\" on center"] + _frame_parts(t, tape=False))
        rows.append(("Frame", prod, (f"{what}; {body}" if what else body[0].upper() + body[1:]), TRUEFRAME_WARRANTY if prod.startswith("ProWood TrueFrame") else ""))
        if not hasattr(L, "parts") and not (ft == "existing" and s.framing.existing_posts):     # the posts on the bases the order has
            bl_, base = next(((l, m.group(1)) for l in t.lines if l.category in ("Footings", "Lumber") and not re.search(r"(?i)stair|landing|cover", l.item)
                              for m in [re.search(r"\bSimpson (AB\w+)", l.item) or re.match(r"(AB[A-Z]*\d\w*)$", str(getattr(l, "sku", "") or ""))] if m), (None, ""))
            rows.append(("Posts", f"{s.framing.post_size} {_post_wood(t)}".strip(), f"{int(bl_.order) if bl_ is not None else L.n_footings} posts"
                         + (f" on Simpson {base} post bases" if base else "") + (", with 4x4 knee braces" if s.framing.knee_braces else ""), ""))
    fw = foundation_words(t)[2]
    if ft == "diamond_pier":
        m = re.match(r"\s*(DP-\d+)\s*/\s*(\d+)", s.framing.footing_model or "")
        rows.append(("Foundations", f"Diamond Pier {m.group(1) if m else s.framing.footing_model}",
                     f"{_deck_piers(t)} foundations" + (f" with {m.group(2)}\" steel pins" if m else "") + "; precast concrete heads, no poured concrete", DIAMOND_PIER_WARRANTY))
    elif ft in ("caisson", "concrete"):
        fw = fw.replace("concrete ", "", 1)
        rows.append(("Foundations", "Concrete " + ("caissons" if ft == "caisson" else "piers"), fw[0].upper() + fw[1:]
                     + (", with rebar" if any("rebar" in l.item.lower() for l in t.lines if l.category == "Footings") else ""), ""))
    else:                                    # the existing caissons stay (and the existing columns on them)
        rows.append(("Foundations", "Existing caissons", fw[0].upper() + fw[1:] + " stay" + ("" if s.framing.existing_posts else "; new post bases epoxy-set on them"), ""))
    if s.framing.system != "steel":          # the connector kinds on the order (no post bases under existing columns that stay)
        kinds = [k for k, pat in (("hangers", r"hanger"), ("post bases", r"post base|^Simpson AB"), ("column caps", r"(column|post) cap"), ("ties", r"\btie\b|framing angle"))
                 if any(re.search(f"(?i){pat}", l.item) for l in t.lines if l.category in ("Hardware", "Footings", "Lumber"))]
        rows.append(("Connectors", "Simpson Strong-Tie ZMAX", "Galvanized " + (", ".join(kinds[:-1]) + " and " + kinds[-1] if len(kinds) > 1 else (kinds or ["connectors"])[0]), ""))
    if any(getattr(z.frame, "ledger", True) for z in L.zones):       # the deck's ledger on the house: its screws, ties and flashing as the order has them
        if any(re.match(r"(?i)FastenMaster LedgerLOK", l.item) for l in t.lines if l.category != "Porch cover"):
            rows.append(("Ledger fasteners", "FastenMaster LedgerLOK", "Structural screws through the ledger into the house framing"
                         + ("; Simpson DTT1Z lateral ties" if any("DTT1Z" in l.item for l in t.lines) else ""), ""))
        elif s.framing.system == "steel":    # the steel ledger track: its structural screws and the steel-joist tension ties, as the order has them
            ls_ = next((l for l in t.lines if l.category == "Hardware" and "ledger track" in l.item), None)
            tt_ = next((l for l in t.lines if l.category == "Hardware" and "tension tie" in l.item.lower()), None)
            if ls_ is not None or tt_ is not None:
                rows.append(("Ledger fasteners", " + ".join(x for x in ("Structural screws" if ls_ is not None else "", "Simpson DTT2Z" if (tt_ is not None and "DTT2Z" in tt_.item) else
                                                                         "tension ties" if tt_ is not None else "") if x),
                             "; ".join(x for x in ("Through the ledger track into the house rim board" if ls_ is not None else "",
                                                   f"{int(tt_.net)} lateral-load tension ties" if tt_ is not None else "") if x), ""))
        fl = " ".join(l.item for l in t.lines if l.category == "Flashing & waterproofing" and not re.search(r"(?i)G-Tape|poly|gravel", l.item))
        vy_ = re.search(r"Grace Vycor(?: Plus| Deck Protector)?", fl)          # the membrane and the metal by the order's own names
        mem = f"{vy_.group(0)} membrane" if vy_ else ("self-adhered membrane" if re.search(r"(?i)\bSA membrane|self-adhered", fl) else "")
        mt_ = "galvanized" if re.search(r"(?i)galvanized L-flashing", fl) else "aluminum"
        metal = f"{mt_} L-flashing" if "L-flashing" in fl else ("aluminum Z-flashing" if re.search(r"(?i)alum\.? Z\b|Z-flash", fl) else "")
        if mem or metal:
            prod = " + ".join(x for x in (mem, metal) if x)
            rows.append(("Ledger flashing", prod[0].upper() + prod[1:], ("Membrane on the house wall behind the ledger" + (" and the side rims" if "side rims" in fl else "") if mem else "")
                         + (", metal flashing over it" if mem and metal else "Metal flashing over the ledger" if metal else "") + ("; end dams" if "end dams" in fl else ""), ""))
    gt = [l.item for l in t.lines if "G-Tape" in l.item]
    if gt:
        m = re.match(r"(Nichigo G-Tape \S+)", gt[0])
        rows.append(("Joist protection", m.group(1) if m else "Joist tape", ('2" tape on every joist, 4" on the rims' + (" and beams" if L.beam_lines else ""))
                     if any('2"' in x for x in gt) and any('4"' in x for x in gt) else "Tape on every joist, rim" + (" and beam" if L.beam_lines else ""), ""))
    return rows


def steel_posts_words(t) -> str:
    """A steel frame's deck posts as the order has them, in the homeowner's words: "3 posts on galvanized steel beam saddles, on 7
    Diamond Pier foundations; 4 steel side brackets tie the beams to the roof covers' posts"; "" when the order has none."""
    ln = lambda pat: next((l for l in t.lines if re.search(pat, l.item)), None)
    sad, brk = ln(r"(?i)beam saddle"), ln(r"(?i)^Steel side bracket")
    if sad is None and brk is None:
        return ""
    return ("; ".join(x for x in ((f"{int(sad.net)} posts on galvanized steel beam saddles, on {foundation_words(t)[2]}" if sad is not None else f"posts on {foundation_words(t)[2]}"),
                                  (f"{int(brk.net)} steel side brackets tie the beams to the roof covers' posts" if brk is not None and "cover" in brk.item else "")) if x))


def _post_wood(t) -> str:
    """The deck posts' wood as the order has it: "rough-sawn Douglas fir #1", "Douglas fir #1", "pressure-treated"; "" unknown."""
    sz = t.spec.framing.post_size
    it = next((l.item for l in t.lines if l.category == "Lumber" and l.item.startswith(f"{sz}x")), "")
    if re.search(r"(?i)douglas fir", it):
        return ("rough-sawn " if re.search(r"(?i)\brough\b", it) else "") + "Douglas fir" + (" #1" if "#1" in it else "")
    return "pressure-treated" if re.search(r"\b(GC|PT)\b", it) else ""


def posts_on_words(t) -> str:
    """The posts and what they stand on, in the homeowner's words (a deck on one level): "6x6 rough-sawn Douglas fir #1 posts on 11
    Diamond Pier foundations", "6x6 Douglas fir #1 posts with 4x4 knee braces on 2 Diamond Pier foundations", "8x8 Douglas fir #1
    posts on 9 concrete caissons, 20" across and 3'-2" deep"; "the 9 existing columns and caissons stay" (the order sets no new
    post bases under columns that stay)."""
    s = t.spec
    if s.framing.footing_type == "existing" and s.framing.existing_posts:
        return foundation_words(t)[2] + " stay"
    return (" ".join(x for x in (s.framing.post_size, _post_wood(t), "posts") if x) + (" with 4x4 knee braces" if s.framing.knee_braces else "")
            + f" on {foundation_words(t)[2]}" + (", epoxy-set bases" if s.framing.footing_type == "existing" else "") + (" with stone column bases" if s.extras.stone_bases else ""))

