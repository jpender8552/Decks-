"""The GSX job page — one template for every job, two audiences.

    internal: the takeoff + build set page (Eagle's Nest layout): reads, flags, the order, schedule, stack, quote, renders,
              isometrics, drawings, build set, live 3D.
    customer: the proposal: black cover with the hero render and the price, then reads, what it is, renders, isometrics,
              explosions, structure, drawings (no internal block), materials without prices, fastening, build steps,
              investment, live 3D. Nothing internal, no names.

render_page(spec, out_dir, mode) writes page.html + files.json (the render files the page references as r/<key>-<still>.jpg)
and, with pdf=True, page.pdf (a print version: cover locked to one page, sheets expanded, the 3D swapped for a still).
"""
import html, json, math, re, shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .spec import DeckSpec
from .report import quote_markdown
from .units import ftin
from .takeoff import CATEGORIES, inches_frac
from .catalog import rail_name, beam_words, beam_species_words
from .pricing import gc_name
from . import proposal_look as PL

E = html.escape
CDN = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
FONT = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,300;6..12,400;6..12,600;6..12,700;6..12,800;6..12,900&display=swap">'
CAP = {"yard": "From the yard", "corner": "From the front corner", "ondeck": "Standing on the deck", "under": "Under the deck — posts, beams, footings",
       "iso": "Isometric from the stair corner", "iso2": "Isometric from the open corner", "isolow": "Low isometric", "underiso": "Isometric from under the frame",
       "exploded": "Exploded — every layer", "exploded2": "Exploded — from the open corner", "exploded-corner": "Exploded — from the front corner", "exploded-low": "Exploded — low angle",
       "frame-iso2": "Frame only — joists, rims, beams, ledger", "rail-iso2": "Through the rail", "structure-underiso": "Posts and beams on the footings", "plan": "Plan from above"}
CAP0 = dict(CAP)
CAP_NO_BEAM = {"under": "Under the deck — posts, footings", "frame-iso2": "Frame only — joists, rims, ledger",
               "structure-underiso": "Posts on the footings, the doubled rims on the posts"}


def money(v, cents=False):
    return f"${v:,.2f}" if cents else f"${v:,.0f}"


def qfmt(v):
    return f"{v:g}"


def table(header, rows, cls="", aligns=None):
    aligns = aligns or ["l"] * len(header)
    th = "".join(f'<th class="{"num" if a == "r" else ""}">{E(h)}</th>' for h, a in zip(header, aligns))
    trs = []
    for r in rows:
        tds = "".join(f'<td class="{"num" if a == "r" else ""}">{c}</td>' for c, a in zip(r, aligns))
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def md_to_html(md):
    """tiny markdown: headings, bold, bullets, numbered, tables, paragraphs."""
    out, i, lines = [], 0, md.split("\n")
    def inline(s):
        s = E(s)
        while "**" in s:
            a = s.find("**"); b = s.find("**", a + 2)
            if b < 0: break
            s = s[:a] + "<b>" + s[a + 2:b] + "</b>" + s[b + 2:]
        return s
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h3 class='qh1'>{inline(ln[2:])}</h3>")
        elif ln.startswith("## "):
            out.append(f"<h4>{inline(ln[3:])}</h4>")
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            head, body = rows[0], rows[1:]
            out.append('<div class="tw"><table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td class='{'num' if (j == len(r) - 1 and len(r) == 2 and len(c.strip()) < 16 and c.strip().lstrip('*').lstrip('$').lstrip('-')[:1].isdigit() and not any(ch.isalpha() for ch in c.replace('mo','').replace('SF','').replace('LF',''))) else ''}'>{inline(c)}</td>" for j, c in enumerate(r)) + "</tr>" for r in body) + "</tbody></table></div>")
            continue
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif ln[:2].rstrip(".").isdigit() and ". " in ln[:4]:
            items = []
            while i < len(lines) and lines[i][:2].rstrip(".").isdigit() and ". " in lines[i][:4]:
                items.append(f"<li>{inline(lines[i].split('. ', 1)[1])}</li>"); i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "".join(out)



CSS = """<style>
:root {
  --ink:#141414; --ink-2:#534d45; --ink-3:#8a8172; --ground:#fbf9f4; --paper:#ffffff; --line:#d9d2c3; --band:#000000; --band-ink:#ffffff;
  --gold:#d49e1b; --gold-ink:#7a5300; --sand:#ecddb6; --stop:#b3261e; --eng:#9a6a00; --code:#3f5d8a; --check:#6f6a5a; --info:#9b9384; --accent:#46534e;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --ink:#f2ede2; --ink-2:#cfc6b3; --ink-3:#9a9182; --ground:#121110; --paper:#1b1916; --line:#3a352d; --band:#000000; --band-ink:#ffffff;
  --gold:#e0ac2a; --gold-ink:#e0ac2a; --sand:#3a331f; --stop:#ff7b70; --eng:#e0ac2a; --code:#8fb0e6; --check:#b7ae9b; --info:#8a8375; --accent:#9fb3aa;
} }
:root[data-theme="dark"] {
  --ink:#f2ede2; --ink-2:#cfc6b3; --ink-3:#9a9182; --ground:#121110; --paper:#1b1916; --line:#3a352d; --band:#000000; --band-ink:#ffffff;
  --gold:#e0ac2a; --gold-ink:#e0ac2a; --sand:#3a331f; --stop:#ff7b70; --eng:#e0ac2a; --code:#8fb0e6; --check:#b7ae9b; --info:#8a8375; --accent:#9fb3aa;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--ground); color:var(--ink); font-family:"Nunito Sans", "Segoe UI", system-ui, sans-serif; font-size:16px; line-height:1.5; font-variant-numeric: tabular-nums; }
.band { background:var(--band); color:var(--band-ink); padding-block:22px 26px; padding-inline:20px; }
.band .in { max-width:960px; margin:0 auto; display:flex; flex-direction:column; gap:6px; }
.band .kick { color:var(--gold); font-weight:800; font-size:12px; letter-spacing:.14em; text-transform:uppercase; }
.band h1 { margin:0; font-size:clamp(26px, 5vw, 40px); font-weight:900; line-height:1.05; text-wrap:balance; }
.band p { margin:4px 0 0; color:#ecddb6; max-width:62ch; font-weight:300; }
.wrap { max-width:960px; margin:0 auto; padding-inline:16px; padding-block:18px 60px; }
.tabs { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; margin-bottom:14px; }
.tab { text-align:left; background:var(--paper); border:1px solid var(--line); border-radius:6px; padding:12px 14px; cursor:pointer; color:var(--ink); font:inherit; display:flex; flex-direction:column; gap:2px; }
.tab .tn { font-weight:800; font-size:17px; } .tab .ts { color:var(--ink-3); font-size:13px; }
.tab.on { border-color:var(--gold); box-shadow: inset 0 0 0 2px var(--gold); }
.tab:focus-visible { outline:3px solid var(--gold); outline-offset:2px; }
.strip { display:grid; grid-template-columns:repeat(6, 1fr); gap:0; border-top:2px solid var(--gold); border-bottom:1px solid var(--line); margin-bottom:22px; }
.strip > div { padding:12px 10px; display:flex; flex-direction:column; gap:2px; border-right:1px solid var(--line); }
.strip > div:last-child { border-right:0; }
.sl { font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3); font-weight:700; }
.sv { font-size:clamp(17px, 2.6vw, 22px); font-weight:900; }
.kicker { font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--gold-ink); font-weight:800; margin:34px 0 10px; padding-bottom:6px; border-bottom:1px solid var(--line); display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }
.tag { font-weight:600; letter-spacing:.06em; color:var(--ink-3); text-transform:none; font-size:12px; }
h3 { font-size:15px; font-weight:800; margin:18px 0 6px; }
.reads { margin:0; display:grid; gap:6px 14px; grid-template-columns: 96px 1fr; }
.reads div { display:contents; }
.reads dt { color:var(--ink-3); font-weight:700; font-size:13px; padding-top:2px; }
.reads dd { margin:0; }
.notes { margin:12px 0 0; padding-left:18px; color:var(--ink-2); font-size:14px; }
.notes li { margin:2px 0; }
.tw { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th { text-align:left; font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3); padding:6px 8px 6px 0; border-bottom:1px solid var(--ink-3); font-weight:700; }
td { padding:6px 8px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }
td.num, th.num { text-align:right; white-space:nowrap; }
table.order td:nth-child(4) { min-width:220px; }
table.ledger td { padding:7px 8px 7px 0; }
table.ledger tr:nth-child(8) td, table.ledger tr:nth-child(10) td { background:var(--sand); }
.flags { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:6px; }
.flags li { display:grid; grid-template-columns:82px 84px 1fr; gap:8px; align-items:baseline; font-size:14px; padding:6px 0; border-bottom:1px solid var(--line); }
.sev { font-size:11px; font-weight:800; letter-spacing:.08em; padding:2px 6px; border-radius:3px; color:#fff; text-align:center; }
.sev-stop .sev { background:var(--stop); } .sev-engineer .sev { background:var(--eng); } .sev-code .sev { background:var(--code); }
.sev-check .sev { background:var(--check); } .sev-info .sev { background:var(--info); }
.topic { color:var(--ink-3); font-weight:700; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
.flags em { color:var(--ink-3); font-style:normal; font-size:12px; }
details { margin-top:14px; } summary { cursor:pointer; font-weight:800; font-size:15px; }
.fine { color:var(--ink-3); font-size:13px; }
.quote { background:var(--paper); border:1px solid var(--line); padding:18px 18px 8px; margin-top:8px; }
.quote .qh1 { font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--gold-ink); margin:0 0 4px; }
.quote h4 { font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-3); margin:22px 0 6px; }
.quote p { margin:6px 0; max-width:66ch; }
.quote ul, .quote ol { padding-left:20px; margin:6px 0; }
.quote li { margin:3px 0; }
.how { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
.how pre { background:var(--paper); border:1px solid var(--line); padding:12px; overflow-x:auto; font-size:13px; margin:6px 0; }
.how p { margin:4px 0; max-width:60ch; }
.how ul { padding-left:18px; margin:6px 0; }
.job[hidden] { display:none; }
footer { margin-top:40px; border-top:1px solid var(--gold); padding-top:10px; color:var(--ink-3); font-size:12px; display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }
@media (max-width: 640px) {
  .strip { grid-template-columns:repeat(3, 1fr); } .strip > div:nth-child(3) { border-right:0; }
  .reads { grid-template-columns: 1fr; } .reads dt { padding-top:8px; }
  .flags li { grid-template-columns: 82px 1fr; } .flags .topic { grid-column:2; } .flags .txt { grid-column: 1 / -1; }
  .how { grid-template-columns:1fr; }
}
@media (prefers-reduced-motion: no-preference) { .tab { transition: border-color .15s; } }
</style>
<style>
.gal{display:grid;grid-template-columns:1fr 1fr;gap:12px;} figure{margin:0;} figure img{width:100%;height:auto;display:block;border:1px solid var(--line);}
figcaption{font-size:12px;color:var(--ink-3);margin-top:4px;}
.sheets .sheet{border:1px solid var(--line);margin:0 0 8px;background:var(--paper);} .sheets summary{cursor:pointer;padding:8px 10px;font-size:14px;} .sheets summary b{color:var(--gold-ink);margin-right:8px;}
.sheets svg{width:100%;height:auto;display:block;border-top:1px solid var(--line);}
.step{display:grid;grid-template-columns:1.15fr 1fr;gap:16px;margin:0 0 18px;padding:0 0 16px;border-bottom:1px solid var(--line);}
.step h3{margin:0 0 4px;font-size:15px;} .step h4{margin:8px 0 2px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold-ink);} .step ul{margin:0;padding-left:18px;font-size:13.5px;} .step li{margin:2px 0;}
.v3d-root{height:520px;min-height:0;} .nav{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0;} .nav a{font-size:12px;font-weight:700;color:var(--gold-ink);text-decoration:none;border:1px solid var(--line);padding:4px 8px;border-radius:3px;background:var(--paper);}
.cover{background:#000;color:#fff;padding:56px 20px 48px;} .cover .in{max-width:960px;margin:0 auto;}
.cover .kick{font-size:11px;letter-spacing:.28em;text-transform:uppercase;color:var(--gold);font-weight:800;}
.cover h1{font-size:clamp(38px,6.5vw,68px);line-height:.98;letter-spacing:-.02em;font-weight:900;margin:16px 0 12px;color:#fff;}
.cover .who{color:#9b9b95;font-size:14px;margin:0 0 24px;}
.pricebar{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#26282c;border:1px solid #26282c;margin:0 0 26px;} .pricebar div{background:#000;padding:16px 18px;}
.pricebar .l{display:block;font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;color:#9b9b95;font-weight:800;} .pricebar .v{display:block;font-size:32px;font-weight:900;letter-spacing:-.02em;margin-top:4px;color:#fff;} .pricebar .s{display:block;font-size:12px;color:#9b9b95;}
.cover .herofig{display:block;width:100%;height:auto;border:1px solid #26282c;} .cover .lede{font-size:16.5px;font-weight:300;line-height:1.55;color:#e6e6e2;margin:22px 0 0;max-width:900px;}
@media (max-width:640px){.gal,.step{grid-template-columns:1fr;} .v3d-root{height:400px;} .strip{grid-template-columns:repeat(2,1fr);} .pricebar{grid-template-columns:1fr;}}
</style>"""

PRINT_CSS = """<style>
@page{size:Letter;margin:0;}
body{background:#f7f3ea;} .wrap{max-width:none;padding:0 0.5in 0.4in;} .band{padding:0.6in 0.6in 0.4in;}
.cover{height:11in;overflow:hidden;box-sizing:border-box;padding:0.7in 0.6in 0.4in;break-after:page;page-break-after:always;} .cover h1{font-size:54px;margin:12px 0 8px;} .cover .who{margin-bottom:18px;} .pricebar{margin-bottom:20px;} .cover .herofig{max-height:4.4in;object-fit:cover;} .cover .lede{font-size:13px;line-height:1.45;margin-top:16px;}
.kicker{break-after:avoid;page-break-after:avoid;margin-top:26px;} figure{break-inside:avoid;page-break-inside:avoid;} .gal{gap:10px;}
.step{break-inside:avoid;page-break-inside:avoid;} .sheets .sheet{break-inside:avoid;page-break-inside:avoid;} .sheets summary{list-style:none;} .sheets summary::-webkit-details-marker{display:none;}
table{font-size:11.5px;} tr{break-inside:avoid;page-break-inside:avoid;} .quote{break-before:page;page-break-before:always;}
h2.pb{break-before:page;page-break-before:always;} footer{padding-bottom:0.4in;} .strip{break-inside:avoid;}
</style>"""


def _reads(t, L, sm, n_piers, customer):
    reads = [("Frame", sm["finished_frame"]), ("Deck", sm["finished_deck"] + f" · {sm['deck_sf']:g} SF · {sm['height']} above grade")]
    for z in sm.get("zones") or []:
        reads.append(("Zone", z))
    reads += [("Joists", sm["joists"]), ("Rims", sm["rims"])]
    for b in sm["beams"]:
        reads.append(("Beam", b))
    posts = sm["posts"]
    if customer and t.order_ref:
        posts = f"{L.n_footings} x {t.spec.framing.post_size} on {posts.split(' on ')[-1]} — {n_piers} ordered"
    reads += [("Posts", posts), ("Load", sm["design_load"]), ("Decking", sm["decking"]), ("Rail", sm["rail"])]
    for s_ in sm["stairs"]:
        reads.append(("Stair", s_))
    return '<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in reads) + "</dl>"


def _order_internal(t):
    out = []
    if t.order_ref:
        out.append('<h2 class="kicker">The order <span class="tag">' + E(t.order_ref) + " · as quoted</span></h2>")
        for cat, lines in t.by_category().items():
            out.append(f"<h3>{E(cat)}</h3>")
            rows = [[E(l.sku), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item), money(l.unit_cost, True), money(l.ext, True)] for l in lines]
            rows.append(["", "", "", f"<i>{E(cat)} subtotal</i>", "", f"<b>{money(sum(l.ext for l in lines), True)}</b>"])
            out.append(table(["SKU", "Qty", "Unit", "Item", "Unit", "Ext"], rows, "order", ["l", "r", "l", "l", "r", "r"]))
        if t.model_lines:
            out.append('<details><summary>Model cross-check — what the engine counts from the drawing (the order above governs)</summary>')
            by = {}
            for l in t.model_lines:
                by.setdefault(l.category, []).append(l)
            for cat in CATEGORIES:
                if cat in by:
                    out.append(f"<h3>{E(cat)}</h3>")
                    out.append(table(["NET", "ORDER", "Unit", "Item", "Why"], [[qfmt(l.net), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item), E(l.why)] for l in by[cat]], "order", ["r", "r", "l", "l", "l"]))
            out.append("</details>")
    else:
        out.append('<h2 class="kicker">The order <span class="tag">Decks &amp; Docks · GSEXT1 · ship to the job</span></h2>')
        for cat, lines in t.by_category().items():
            out.append(f"<h3>{E(cat)}</h3>")
            out.append(table(["NET", "ORDER", "Unit", "Item", "Why"], [[qfmt(l.net), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item), E(l.why)] for l in lines], "order", ["r", "r", "l", "l", "l"]))
    return "".join(out)


def _order_customer(t):
    out = ['<h2 class="kicker pb">Materials <span class="tag">every piece' + (", as ordered" if t.order_ref else "") + "</span></h2>"]
    cats = t.by_category()
    for cat in CATEGORIES:
        if cat in cats:
            out.append(f"<h3>{E(cat)}</h3>")
            if t.order_ref:
                out.append(table(["Qty", "Unit", "Item", "SKU"], [[f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item), E(l.sku)] for l in cats[cat]], "order", ["r", "l", "l", "l"]))
            else:
                out.append(table(["Qty", "Unit", "Item"], [[f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item)] for l in cats[cat]], "order", ["r", "l", "l"]))
    return "".join(out)


def _stack(p, sold: float = None):
    out = ['<h2 class="kicker" id="g-stack">' + (f"The stack — cost + margin <span class=\"tag\">sold at {money(sold)} · internal</span>" if sold else 'The stack <span class="tag">internal</span>') + '</h2>']
    stack = [("Materials (raw)", money(p.materials, True)), (f"Materials × {p.material_factor:g}", money(p.materials_factored, True)),
             (f"Sales tax {p.tax_rate:.2%}" + (" on factored materials" if p.material_factor != 1 else ""), money(p.tax, True)), ("Labor (rate card)", money(p.labor, True)),
             ("Work — carries the margin", money(p.work, True)), (gc_name(p.gc_lines, "General conditions") + " at cost", money(p.gc, True)), ("Cost", money(p.cost, True)),
             (f"Sell — check or ACH at {p.gm:.1%} GM" + (f" ({p.rail_note})" if p.rail_note else ""), f"<b>{money(p.sell)}</b> · {money(p.sell_per_sf, True)}/SF"), ("Sell at the 40% floor" + (" (the deck at 40%, rail at its rate)" if p.rail_note else ""), money(p.sell_floor)),
             ("Financed", f"<b>{money(p.retail)}</b> · {money(p.monthly)}/mo at 6.99% × 10 yr"), ("Gross profit", money(p.gp))]
    if sold:
        stack[7] = ("SOLD — check or ACH", f"<b>{money(p.sell)}</b> · {money(p.sell_per_sf, True)}/SF")
        stack += [("Margin on the sold price (gross profit ÷ sell, GC at cost)", f"<b>{p.gp / p.sell:.1%}</b>"),
                  ("Margin on the work (the GM the engine prices with)", f"{p.gm:.1%}"),
                  ("Markup on cost", f"{p.gp / p.cost:.1%}"),
                  ("Commission 10% of sell", money(p.commission)), ("Gross profit after commission", f"<b>{money(p.gp - p.commission)}</b> · {(p.gp - p.commission) / p.sell:.1%} of sell")]
    if p.engineering:
        stack.append(("Engineering — outside the price, at cost", f"{money(p.engineering[0])}–{money(p.engineering[1])}"))
    out.append('<div class="tw"><table class="ledger"><tbody>' + "".join(f"<tr><td>{k}</td><td class='num'>{v}</td></tr>" for k, v in stack) + "</tbody></table></div>")
    out.append("<h3>Labor</h3>")
    out.append(table(["Line", "Qty", "Unit", "Rate", "Ext"], [[E(i), qfmt(q), E(u), money(r, True), money(e, True)] for i, q, u, r, e in p.labor_lines], "", ["l", "r", "l", "r", "r"]))
    if p.gc_lines:
        out.append(f"<h3>{E(gc_name(p.gc_lines, 'General conditions'))} — at cost, no margin</h3>")
        out.append(table(["Item", "Amount", "Why"], [[E(i), money(a), E(why)] for i, a, why in p.gc_lines], "", ["l", "r", "l"]))
    out.append("<h3>What the price includes — sell values</h3>")
    out.append(table(["Item", "Value"], [[E(k), money(v)] for k, v in p.allocation] + [["<b>Total, check or ACH</b>", f"<b>{money(p.sell)}</b>"], ["<b>Total, financed</b>", f"<b>{money(p.retail)}</b>"]], "", ["l", "r"]))
    if p.options:
        out.append("<h3>Options — full installed deltas</h3>")
        out.append(table(["Option", "Cost Δ", "Check / ACH", "Financed"], [[E(o.name), f"{o.cost:+,.0f}", f"{o.check:+,.0f}", f"{o.financed:+,.0f}"] for o in p.options], "", ["l", "r", "r", "r"]))
    return "".join(out)


def _cost_stack(p, t):
    """The sold job: what it costs to build, everything in, no margin lines."""
    tax_raw = round(p.materials * p.tax_rate, 2)
    total = round(p.materials + tax_raw + p.labor + p.gc, 2)
    out = ['<h2 class="kicker">Cost to build <span class="tag">materials at invoice · labor at the rate card · site services at cost</span></h2>']
    rows = [("Materials — every line of the order", money(p.materials, True)), (f"Sales tax {p.tax_rate:.2%} on materials", money(tax_raw, True)),
            ("Labor", money(p.labor, True)), (gc_name(p.gc_lines, "Site & project services") + " at cost", money(p.gc, True)), ("<b>Total cost to build</b>", f"<b>{money(total, True)}</b>")]
    out.append('<div class="tw"><table class="ledger"><tbody>' + "".join(f"<tr><td>{k}</td><td class='num'>{v}</td></tr>" for k, v in rows) + "</tbody></table></div>")
    cats = t.by_category()
    out.append("<h3>Materials by category</h3>")
    out.append(table(["Category", "Lines", "Cost"], [[E(c), str(len(ls)), money(sum(l.ext for l in ls), True)] for c, ls in cats.items()] + [["<b>Materials</b>", "", f"<b>{money(p.materials, True)}</b>"]], "", ["l", "r", "r"]))
    out.append("<h3>Labor</h3>")
    out.append(table(["Line", "Qty", "Unit", "Rate", "Ext"], [[E(i), qfmt(q), E(u), money(r, True), money(e, True)] for i, q, u, r, e in p.labor_lines] + [["<b>Labor</b>", "", "", "", f"<b>{money(p.labor, True)}</b>"]], "", ["l", "r", "l", "r", "r"]))
    if p.gc_lines:
        out.append(f"<h3>{E(gc_name(p.gc_lines, 'Site & project services'))} — at cost</h3>")
        out.append(table(["Item", "Amount", "Why"], [[E(i), money(a), E(why)] for i, a, why in p.gc_lines], "", ["l", "r", "l"]))
    if p.engineering:
        out.append(f"<p><b>Engineering and permit</b> — {money(p.engineering[0])} to {money(p.engineering[1])}, billed at cost on top of the above.</p>")
    return "".join(out), total, tax_raw


def _gallery(key, names, have):
    return '<div class="gal">' + "".join(f'<figure><img src="r/{key}-{n}.jpg" alt="{E(CAP.get(n, n))}" loading="lazy"><figcaption>{E(CAP.get(n, n))}</figcaption></figure>' for n in names if n in have) + "</div>"


def _steps(key, steps, cap, customer):
    out = []
    for st in steps:
        title = f"Step {st['n']} · {E(st['title'])}" if customer else f"{st['code']} · Step {st['n']} · {E(st['title'])}"
        fc = re.sub(r"^Step \d+ · ", f"Step {st['n']} · ", cap[st["still"]])     # the model's phase number -> the step as built (phases skip)
        out.append(f'<div class="step"><figure><img src="r/{key}-{st["still"]}.jpg" alt="step {st["n"]}" loading="lazy"><figcaption>{E(fc)}</figcaption></figure>'
                   f'<div><h3>{title}</h3><h4>Goes in</h4><ul>' + "".join(f"<li>{E(g)}</li>" for g in st["goes_in"]) + "</ul>"
                   + '<h4>How</h4><ul>' + "".join(f"<li>{E(h)}</li>" for h in st["how"] if h) + "</ul><h4>Check</h4><ul>" + "".join(f"<li>{E(c)}</li>" for c in st["check"]) + "</ul></div></div>")
    return "".join(out)


def _reads_levels(t, L, sm):
    """At a glance for a deck on two or more levels: each level with its size and height, the decking, the rail, every stair by
    its name (the inset stair, its skirt), the lights, the frame and the columns."""
    from .report import levels_of, lights_of, stair_words, composite_frame_words
    from .pricing import stair_specs
    s = t.spec
    lv = levels_of(t)
    reads = [("Deck", f"{L.deck_sf:g} SF on {'two' if len(lv) == 2 else len(lv)} levels, {ftin(L.finished_w)} along the house"
              + (f", {ftin(abs(lv[1]['height_in'] - lv[0]['height_in']))} between the levels" if len(lv) == 2 else ""))]
    for v in lv:
        reads.append((v["name"], f"{v['sf']:g} SF · {ftin(v['height_in'])} above grade · "
                      + " and ".join(f"{z.name} {ftin(z.W)} x {ftin(z.D)}" for z in v["zones"])))
    fsys = s.decking.fastener_system or "hidden"
    brk = any(v["part"].layout.divider_x or (v["part"].layout.plan and v["part"].layout.plan.dividers) for v in lv)
    decking = f"{s.decking.brand} {s.decking.collection} {s.decking.color}"
    if s.geometry.picture_frame:
        decking += (f", picture frame{' and breaker boards' if brk else ''} in "
                    + (f"{s.decking.border_collection or s.decking.collection} {s.decking.border_color}" if s.decking.border_color else "the same color"))
    decking += f", matching fascia · {fsys} fasteners" + (" with color-matched plugs" if fsys == "Cortex" else "")
    rl = L.rail
    rail = (f"{s.decking.brand} {rail_name(rl.system)}, {rl.color}, {rl.height:g}\" · {rl.rail_lf:g} LF"
            + (f" · {s.railing.drink_rail_collection + ' ' if s.railing.drink_rail_collection else ''}{s.railing.drink_rail_color} drink rail on top" if s.railing.drink_rail else "")) if rl else "None"
    reads += [("Decking", decking), ("Rail", rail)]
    for ss, st in zip(stair_specs(t), L.stairs):
        reads.append((getattr(ss, "name", None) or "Stair", stair_words(ss, st, True)))
    from .report import step_face_words
    if step_face_words(t):
        reads.append(("Step face", step_face_words(t)))
    lt = lights_of(t)
    if lt["total"]:
        reads.append(("Lighting", ", ".join(x for x in ((f"{lt['riser']} riser lights" if lt["riser"] else ""), (f"{lt['post_cap']} post-cap lights" if lt["post_cap"] else ""),
                                                        (f"{lt['other']} more" if lt["other"] else "")) if x) + " · LED, low voltage"))
    n_p = int(sum(l.order for l in t.lines if l.item.lower().startswith("diamond pier"))) or L.n_footings
    found = f"{n_p} Diamond Pier foundations" if s.framing.footing_type == "diamond_pier" else sm["posts"].split(" on ")[-1]
    reads += [("Structure", composite_frame_words(t).rstrip(".") + f"; {found}"), ("Design load", sm["design_load"].replace(" · engineered", ", stamped by a Colorado engineer"))]
    return '<dl class="reads levels">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in reads) + "</dl>"


LEVELS_CSS = """<style>
.reads.levels { grid-template-columns:160px 1fr; }
@media (max-width: 640px) { .reads.levels { grid-template-columns:1fr; } }
@media print { #g-reads + .gal img { max-height:1.8in; object-fit:cover; } .reads.levels { gap:2px 12px; } .reads.levels dd { font-size:12.5px; line-height:1.4; }
  .reads.levels dt { font-size:11px; } #g-what { margin-top:18px; } }
</style>"""


def _reads_lite(t, L, sm):
    """The homeowner's at-a-glance: what it is, not how it is framed."""
    s = t.spec
    if hasattr(L, "parts"):
        return _reads_levels(t, L, sm)
    from .catalog import decking_facts
    fsys = s.decking.fastener_system or "hidden"
    deck = f"{sm['deck_sf']:g} SF · {sm['height']} above grade · {sm['finished_deck']}"
    decking = f"{s.decking.brand} {s.decking.collection} {s.decking.color}"
    if s.geometry.picture_frame and s.decking.border_color:
        decking += f", picture frame{' and breaker boards' if L.divider_x else ''} in {s.decking.border_collection or s.decking.collection} {s.decking.border_color}"
    decking += f" · {fsys} fasteners" + (" with color-matched plugs" if fsys == "Cortex" else "")
    rl = L.rail
    if s.railing.existing_parapet and s.railing.parapet_note:
        rail = s.railing.parapet_note
    elif s.railing.existing_parapet:
        rail = "The existing stucco parapet stays" + (f"; {rl.system} {rl.color} {rl.height:g}\" rail on the new stair and landings" if rl and L.stairs else "")
    elif rl:
        rail = f"{s.decking.brand} {rail_name(rl.system)}, {rl.color}, {rl.height:g}\" · {rl.rail_lf:g} LF"
    else:
        rail = "None"
    stairs = []
    for st, ss in zip(L.stairs, s.stairs):
        g = st.geo
        txt = f"{g.risers} risers at {inches_frac(g.riser_in)}, {ftin(st.width)} wide"
        if len(g.flights) > 1:
            lands = " and ".join(f"{ftin(a)} x {ftin(b)}" for a, b in ss.landings) if ss.landings else "a landing"
            turn = {"switchback": "turn back", "left": "turn left", "right": "turn right", "straight": "continue"}.get(ss.turn, ss.turn)
            txt += ": " + " then ".join(f"{fg.risers} down" for fg in g.flights[:1]) + f" to the {lands} landing, {turn}, " + " then ".join(f"{fg.risers} down" for fg in g.flights[1:]) + " to the lower level"
            if st.landing_rail_lf:
                txt += f" · guard rail on the landings"
        stairs.append((getattr(ss, "name", None) or "Stair", txt))
    fr = L.zones[0].frame
    beams = sorted({b.size for b in s.framing.beams}) if s.framing.beams else []
    structure = (f"CEMCO cold-formed steel frame, {s.framing.steel_joist} C-joists at {fr.spacing:g}\" on center, {s.framing.steel_track} track, boxed {s.framing.steel_joist} beams, all G90; {sm['posts']}" if s.framing.system == "steel" else
                 f"{s.framing.joist_size} {'pressure-treated' if not s.is_timber else 'Douglas fir'} frame at {fr.spacing:g}\" on center"
                 + (f", {beam_words(beams, beam_species_words(s.framing.beams), len(s.framing.beams))}" if beams else "") + f"; {sm['posts']}"
                 + ("; joist tape on every member" if s.framing.joist_tape else ""))
    reads = [("Deck", deck), ("Decking", decking), ("Rail", rail)] + stairs + [("Structure", structure), ("Design load", sm["design_load"].replace(" · engineered", ", stamped by a Colorado engineer"))]
    return '<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in reads) + "</dl>"


def _added_facts(t0, t1) -> list:
    """What an option adds, in the homeowner's words, from the two takeoffs: new stairs, lights, rail, foundations."""
    from .pricing import stair_specs
    from .report import lights_of, stair_words
    rows = []
    s0 = stair_specs(t0)
    for ss, st in zip(stair_specs(t1), t1.layout.stairs):
        if ss not in s0:
            rows.append((getattr(ss, "name", None) or "Stair", stair_words(ss, st, hasattr(t1.layout, "parts"))))
    l0, l1 = lights_of(t0), lights_of(t1)
    if l1["riser"] > l0["riser"]:
        rows.append(("Riser lights", f"{l1['riser'] - l0['riser']} LED lights, one in every riser"))
    if l1["post_cap"] > l0["post_cap"]:
        rows.append(("Post-cap lights", f"{l1['post_cap'] - l0['post_cap']} LED post-cap lights, one on every rail post"))
    if l1["other"] > l0["other"]:
        rows.append(("Lights", f"{l1['other'] - l0['other']} more LED lights"))
    plan = getattr(t1, "lighting", None)
    sw = ""
    if l1["transformer"] and not l0["transformer"] and plan is not None:     # the lighting engine's own words for how it switches
        try:
            from .lighting import _switching
            sw = _switching(plan)
        except Exception:
            sw = ""
    if sw:
        rows.append(("Power", sw[0].upper() + sw[1:] + "; it plugs into an outdoor GFCI outlet with an in-use cover (adding an outlet, if one is needed, is not included)"))
    elif l1["transformer"] and not l0["transformer"]:
        tr = l1["transformer"].lower()
        rows.append(("Power", "low voltage from a transformer" + (" with a photocell and timer" if "photo" in tr and "timer" in tr else
                                                                  (" with a photocell" if "photo" in tr else (" with a timer" if "timer" in tr else "")))))
    r0, r1 = t0.layout.rail, t1.layout.rail
    drl = round(r1.rail_lf - (r0.rail_lf if r0 else 0.0), 1) if r1 else 0.0
    if drl >= 1:
        rows.append(("Rail", f"{drl:g} LF more of the same rail"))
    def piers(t):
        return int(sum(l.order for l in t.lines if l.item.lower().startswith("diamond pier"))) or t.layout.n_footings
    dp = piers(t1) - piers(t0)
    if dp > 0:
        rows.append(("Foundation", f"{dp} more Diamond Pier foundation{'s' if dp != 1 else ''}"))
    return rows


def _sign(v) -> str:
    return ("+" if v >= 0 else "−") + money(abs(v))


def _render_figs(o: dict, rd: Path, key: str, ok: str, files: dict) -> list:
    """The figures for an option's (or add-on's) own renders: o["renders"] = [name | (name, caption)] — stills in
    o["renders_dir"] (default: the page's renders), captions from that folder's captions.json; each file goes in files.json
    as r/<key>-<option>-<name>.jpg."""
    rdir = Path(o["renders_dir"]) if o.get("renders_dir") else rd
    caps = dict(CAP)
    if (rdir / "captions.json").exists():
        caps.update(json.load(open(rdir / "captions.json")))
    figs = []
    for r_ in o.get("renders") or []:
        nm, cp = (r_[0], r_[1]) if isinstance(r_, (list, tuple)) else (r_, None)
        if not (rdir / f"{nm}.jpg").exists():
            continue
        fn = f"r/{key}-{ok}-{nm}.jpg"
        files[fn] = str(rdir / f"{nm}.jpg")
        cp = cp or caps.get(nm, nm)
        figs.append(f'<figure><img src="{fn}" alt="{E(cp)}" loading="lazy"><figcaption>{E(cp)}</figcaption></figure>')
    return figs


def _price_trio(c, f, m, show_fin: bool) -> str:
    """An option's price three ways, as additions to the deck price."""
    if not show_fin:
        return f'<div class="opt-prices one"><div class="lead"><span class="pl">Check or ACH</span><span class="pv">{_sign(c)}</span></div></div>'
    return ('<div class="opt-prices">'
            f'<div class="lead"><span class="pl">Check or ACH</span><span class="pv">{_sign(c)}</span></div>'
            f'<div><span class="pl">Financed</span><span class="pv">{_sign(f)}</span></div>'
            f'<div><span class="pl">Monthly</span><span class="pv">{_sign(m)}</span></div></div>')


def _option_blocks(spec, t, p, blocks, key, rd, files) -> dict:
    """Options given as dicts: one block each — its price three ways, what it adds, its own renders, an add-on when it
    combines with another option — and the rows for the investment summary. See render_page for the keys."""
    from . import run
    from .pricing import option_delta, fixed_terms, price_louvered, _monthly
    from .report import lights_of
    show_fin = spec.extras.show_financing
    out, rows = [], []
    tc = tf = 0.0
    for i, o in enumerate(blocks, 1):
        ok = re.sub(r"[^a-z0-9]+", "-", str(o.get("key") or f"opt{i}").lower()).strip("-")
        title, num = o.get("title") or f"Option {i}", o.get("number") or f"Option {i}"
        t2 = None
        if o.get("spec") is not None:            # the deck with this option: an engine delta (on a per-SF deck: cost math at the job margin)
            t2, _, p2 = run(o["spec"])
            c, f, m = option_delta(p, p2)
            basis = f"engine delta: work {p2.work - p.work:+,.0f}" + (f" at the job margin {p.options_gm:.1%} (the deck sells per SF)" if getattr(p, "per_sf", 0)
                                                                      else f", the deck's {p.gm:.1%} margin")
        elif o.get("roof") is not None:          # a louvered roof: its own price per SF x its area (or a set price), outside the deck's margin
            from .louvered import roofs_of, resolve, surfaces_of, scope_words
            rs = o.get("roof_spec") or spec      # the spec that carries the roof (the deck's, or a copy with the roof on it)
            roof = roofs_of(rs)[o["roof"]] if isinstance(o["roof"], int) else o["roof"]
            ap = price_louvered(rs, roof)
            c, f, m = ap.sell, ap.retail, ap.monthly
            basis = f"owner-set: {ap.basis}, sold on its own (outside the deck's cost and margin)"
            if o.get("facts") is None:
                o = dict(o, facts=scope_words(resolve(roof, surfaces_of(t.layout if rs is spec else run(rs)[0].layout))))
        elif o.get("price") is not None:         # a price the owner set outright
            c, f, m = fixed_terms(spec, o["price"])
            basis = "owner-set price"
        else:
            raise ValueError(f"option {title!r}: give spec, roof or price")
        facts = o.get("facts")
        if facts is None:
            facts = _added_facts(t, t2) if t2 is not None else []
        adds = []
        for ai, a in enumerate(o.get("addons") or [], 1):
            note = a.get("note", "")
            ab = "owner-set price"
            if a.get("spec") is not None:       # rides with another option (the lights on the yard stair): the extra over both alone
                ta, _, pa = run(a["spec"])
                tb, _, pb = run(a["against"])
                ca, fa, ma = option_delta(pb, pa)
                ca, fa, ma = ca - c, fa - f, ma - m
                ab = f"engine delta: the two options together, less each alone (work {(pa.work - pb.work) - ((p2.work - p.work) if t2 is not None else 0):+,.0f})"
                if not note and t2 is not None:
                    la, lb, lo, l0 = lights_of(ta), lights_of(tb), lights_of(t2), lights_of(t)
                    xr, xp = (la["riser"] - lb["riser"]) - (lo["riser"] - l0["riser"]), (la["post_cap"] - lb["post_cap"]) - (lo["post_cap"] - l0["post_cap"])
                    note = " and ".join(x for x in ((f"{xr} more riser light{'s' if xr != 1 else ''}" if xr > 0 else ""),
                                                     (f"{xp} more post-cap light{'s' if xp != 1 else ''}" if xp > 0 else "")) if x)
            elif a.get("price") is not None:     # a set price
                ca, fa, ma = fixed_terms(spec, a["price"])
            elif a.get("screens") and o.get("roof") is not None:     # the roof's screens: the louvered engine's price for them
                from .louvered import roof_pricing
                rs = o.get("roof_spec") or spec
                rows_ = roof_pricing(rs, t.layout if rs is spec else run(rs)[0].layout)["roofs"]
                rr = rows_[o["roof"] if isinstance(o["roof"], int) else 0]
                if not rr.get("screens_sell"):
                    raise ValueError("screens add-on: the roof has no screens (louvered_roofs[i].screens)")
                ca, fa, ma = fixed_terms(spec, rr["screens_sell"])
                note = note or "; ".join(x["words"] for x in rr.get("screens") or [])
                ab = _screens_basis(rr)
            else:
                raise ValueError(f"add-on {a.get('label')!r}: give spec + against, price, or screens (on a roof option)")
            adds.append((a.get("label") or "Add-on", ca, fa, ma, note, _render_figs(a, rd, key, f"{ok}-a{ai}", files), ab))
        imgs = _render_figs(o, rd, key, ok, files)
        h = [f'<section class="optblock" id="g-opt-{ok}" aria-labelledby="oh-{ok}"><div class="opt-head"><div class="opt-title">'
             f'<span class="eyebrow">{E(num)}</span><h3 id="oh-{ok}">{E(title)}</h3></div>{_price_trio(c, f, m, show_fin)}</div><div class="opt-body">']
        if o.get("blurb"):
            h.append(f'<p class="opt-blurb">{E(o["blurb"])}</p>')
        if facts and all(isinstance(x, str) for x in facts):     # scope lines (the roof's)
            h.append('<ul class="opt-scope">' + "".join(f"<li>{E(x)}</li>" for x in facts) + "</ul>")
        elif facts:
            h.append('<dl class="reads levels">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in facts) + "</dl>")
        if imgs:
            h.append('<div class="gal">' + "".join(imgs) + "</div>")
        for lab, ca, fa, ma, note, figs, _ab in adds:
            h.append(f'<div class="opt-addon"><div class="oa-line"><b>{E(lab)}</b><span>{_sign(ca)} check or ACH' + (f" · {_sign(fa)} financed · {_sign(ma)}/mo" if show_fin else "") + "</span></div>"
                     + (f'<span class="fine">{E(note)}</span>' if note else "") + ('<div class="gal">' + "".join(figs) + "</div>" if figs else "") + "</div>")
        if o.get("note") or o.get("url"):
            h.append('<p class="opt-note">' + E(o.get("note", "")) + (f' <a href="{E(o["url"])}">{E(o.get("url_text") or o["url"])}</a>' if o.get("url") else "") + "</p>")
        h.append("</div></section>")
        out.append("".join(h))
        rows.append((f"{num} — {title}", c, f, m, False, basis))
        rows += [(lab, ca, fa, ma, True, ab_) for lab, ca, fa, ma, _, _, ab_ in adds]
        tc += c + sum(a[1] for a in adds)
        tf += f + sum(a[2] for a in adds)
    head = ('<h2 class="kicker pb" id="g-options">Options <span class="tag">each priced on its own, added to the deck price · '
            + ("its own renders" if any("<figure>" in x for x in out) else "the whole installed difference") + "</span></h2>")
    return dict(html=head + "".join(out), rows=rows, total=(p.sell + tc, p.retail + tf, _monthly(p.retail + tf)), show_fin=show_fin)


def _options_summary(ob) -> str:
    """The options in the investment section: each one's price three ways (the add-ons under the option they ride with), then
    the deck with every option."""
    show_fin = ob["show_fin"]
    body = [[(f'<span class="sub">{E(lab)}</span>' if sub else E(lab)), _sign(c)] + ([_sign(f), _sign(m) + "/mo"] if show_fin else [])
            for lab, c, f, m, sub, _b in ob["rows"]]
    tc, tf, tm = ob["total"]
    body.append(["<b>The deck with every option</b>", f"<b>{money(tc)}</b>"] + ([f"<b>{money(tf)}</b>", f"<b>{money(tm)}/mo</b>"] if show_fin else []))
    return ("<p>Each line is the whole difference, installed, added to the deck price above.</p>"
            + table(["Option", "Check or ACH"] + (["Financed", "Monthly"] if show_fin else []), body, "optsum", ["l", "r"] + (["r", "r"] if show_fin else [])))


def _options_internal(ob) -> str:
    """The internal set: every option as the proposal prices it, with how each number was made — an engine delta, an
    owner-set price, or an ESTIMATE the owner has not set (the lead confirms it before anything goes to the client)."""
    rows = [[(("&nbsp;&nbsp;" + E(lab)) if sub else f"<b>{E(lab)}</b>"), _sign(c), _sign(f), _sign(m) + "/mo", E(b)] for lab, c, f, m, sub, b in ob["rows"]]
    tc, tf, tm = ob["total"]
    rows.append(["<b>The deck with every option</b>", f"<b>{money(tc)}</b>", f"<b>{money(tf)}</b>", f"<b>{money(tm)}/mo</b>", ""])
    est = [lab for lab, c, f, m, sub, b in ob["rows"] if "ESTIMATE" in b]
    return ('<h2 class="kicker" id="g-options">Options in the proposal <span class="tag">internal · how each price was made</span></h2>'
            + (f'<p><b>ESTIMATE — not set by the owner:</b> {E("; ".join(est))}. Confirm the number before the proposal goes to the client.</p>' if est else "")
            + table(["Option", "Check / ACH", "Financed", "Monthly", "Basis"], rows, "", ["l", "r", "r", "r", "l"]))


def _screens_basis(rr: dict) -> str:
    """How the roof's screens are priced, for the internal set: the owner's price, or the louvered engine's placeholder rate."""
    scr = rr.get("screens") or []
    lf = sum(float(x.get("width_ft") or 0) for x in scr)
    rates = sorted({float(x.get("rate_per_lf") or 0) for x in scr if x.get("rate_per_lf")})
    est = any(x.get("estimate") for x in scr)
    rate = (f"${rates[0]:,.0f}/LF x {lf:.1f} LF of screen" if len(rates) == 1 else f"{lf:.1f} LF of screen")
    return (f"ESTIMATE — the louvered engine's placeholder {rate}; the owner has not set this price" if est else f"set on the roof: {rate}")


def _viewer_link(url: str, note: Optional[str] = None) -> str:
    """The customer documents link to the interactive 3D page instead of embedding the viewer (a PDF keeps the link)."""
    if not url:
        return ""
    return ('<h2 class="kicker" id="g-3d">Interactive 3D <span class="tag">opens in a web browser</span></h2>'
            f'<div class="v3d-link"><p>{E(note or "The deck and its options in 3D, in a web browser.")}</p>'
            f'<a class="v3d-btn" href="{E(url)}">Open the interactive 3D model</a><span class="v3d-url">{E(url)}</span></div>')


def _options_table(p, options):
    """Full installed deltas against this proposal: [(label, other pricing)]."""
    if not options:
        return ""
    from .pricing import option_delta        # the prices' difference; on a deck sold per SF, the engine's cost math at the job margin
    def d(v):
        return ("+" if v >= 0 else "−") + money(abs(v))
    rows = [[E(lab), d(c), d(f), d(m) + "/mo"] for lab, (c, f, m) in ((lab, option_delta(p, q)) for lab, q in options)]
    return ('<h3>Options</h3><p>Each line is the whole difference, installed, against the price above.</p>'
            + table(["Option", "Check or ACH", "Financed", "Monthly"], rows, "", ["l", "r", "r", "r"]))


def render_page(spec: DeckSpec, out_dir: str, mode: str = "internal", key: str = "job", name: Optional[str] = None, sub: str = "",
                lede: str = "", hero: str = "corner", render: bool = True, renders_dir: Optional[str] = None, pdf: bool = False,
                date_line: Optional[str] = None, options: Optional[list] = None, alt_tag: Optional[str] = None, roof: int = 0,
                viewer_url: Optional[str] = None, viewer_note: Optional[str] = None, addon: Optional[dict] = None) -> dict:
    """Build the page. mode = "internal" | "customer" | "proposal" (the customer page without the sheets, schedules and
    step-by-step: cover, at a glance, what it is, renders, isometrics, exploded views, under the deck, investment with
    options, 3D) | "addon" (the louvered roof's own proposal, roofs_of(spec)[roof]: see render_addon; addon = its options).

    options, either form (they can be mixed):
      (label, DeckSpec) — a line in the investment's options table, the whole installed difference; its renders are the
          alt-*.jpg stills in renders_dir, under "The option, rendered" with alt_tag as the tag (the Prentice rail option).
      dict — an option block of its own, before the investment: title, number ("Option 1"), key, blurb, and its price from
          spec (the deck with the option: an engine delta — on a deck sold per SF, the engine's cost math at the job margin),
          roof (a louvered roof: index into louvered.roofs_of(roof_spec or spec), or the roof dict: its own price per SF) or
          price (set outright); facts ([(label, text)] or [line]; None -> worked out from what the option adds); renders
          [name | (name, caption)] from renders_dir (or the option's own renders_dir); addons [dict(label, spec + against |
          price, note, renders, renders_dir)] — e.g. the lights on the yard stair when both are taken, the roof's screens;
          note / url (e.g. the roof's own document). The investment then lists every option and the deck with all of them.
    viewer_url: the customer page links to the interactive 3D page instead of embedding the viewer ("" drops the 3D
    altogether); viewer_note is the line above the button. Returns {"html", "files", "pdf"?, "pricing", "takeoff"}."""
    if mode == "addon":
        return render_addon(spec, out_dir, key=key, name=name, lede=lede, hero=hero, renders_dir=renders_dir, pdf=pdf, date_line=date_line, roof=roof,
                            viewer_url=viewer_url, viewer_note=viewer_note, addon=addon)
    from . import run
    from .buildset import build_set
    from .viewer import viewer_html
    from datetime import date
    proposal = mode == "proposal"
    cost_only = mode == "cost"
    supplier = mode == "supplier"           # the take-off + build set for the supplier: quantities, drawings, steps — no prices
    customer = mode == "customer" or proposal
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    t, flags, p = run(spec)
    L, sm = t.layout, t.summary
    r = build_set(t, flags, str(out / "buildset"), render=render, customer=customer or supplier)
    S = r["scene"]
    rd = Path(renders_dir) if renders_dir else (out / "buildset" / "renders")
    have = {q.stem for q in rd.glob("*.jpg")}
    if spec.geometry.height_in < 30:         # a deck near grade: the views from under it show a rim at the lawn and nothing else
        have -= {"under", "underiso", "structure-underiso"}
    files = {f"r/{key}-{n_}.jpg": str(rd / f"{n_}.jpg") for n_ in have}
    sun_names = sorted(n_ for n_ in have if n_.startswith("sun-"))
    CAP.clear(); CAP.update(CAP0)                # this job's captions only
    if not L.beam_lines:
        CAP.update(CAP_NO_BEAM)
    if (rd / "sun.json").exists():
        CAP.update(json.load(open(rd / "sun.json")))
    if (rd / "captions.json").exists():          # a job's own captions (its camera stations, option renders)
        CAP.update(json.load(open(rd / "captions.json")))
    alt_names = sorted(n_ for n_ in have if n_.startswith("alt-"))
    alt_html = (f'<h2 class="kicker pb" id="g-alt">The option, rendered <span class="tag">{E(alt_tag or "same deck, the optional rail")}</span></h2>'
                + _gallery(key, alt_names, have)) if alt_names else ""
    sun_tag = "the covers and the blinds through the day" if (spec.geometry.covers or spec.geometry.cover) else "shade on the deck through the day"
    sun_html = ('<h2 class="kicker pb" id="g-sun">Sun and shade <span class="tag">the real sun at this address · ' + sun_tag + '</span></h2>'
                + _gallery(key, sun_names, have)) if sun_names else ""
    cap = dict(CAP); cap.update({f"step{n}": S.meta["step_text"][n] for n in range(1, 9)})
    name = name or spec.job
    addr = ", ".join(x for x in (spec.site.address, spec.site.city, f"{spec.site.state} {spec.site.zip}".strip()) if x)
    n_piers = int(sum(l.order for l in t.lines if l.item.lower().startswith("diamond pier"))) or L.n_footings
    today = date_line or date.today().strftime("%B %d, %Y")
    qmd = quote_markdown(t, p)
    o = []
    w = o.append
    w(f'<section class="job" id="job-{key}" data-job="{key}">')
    if supplier:
        w('<h2 class="kicker" id="g-reads">The job</h2>')
        st_txt = "; ".join(sm["stairs"]) if sm["stairs"] else "none"
        w('<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in [
            ("Deck", f"{L.deck_sf:g} SF · {ftin(spec.geometry.height_in)} above grade · {sm['finished_frame']}"), ("Joists", sm["joists"]), ("Rims", sm["rims"]),
            ("Beams", "; ".join(sm["beams"]) or ("none — the doubled rims span post to post on the edge posts" if getattr(L, "edge_posts", None) else "—")), ("Footings / posts", sm["posts"]), ("Decking", sm["decking"]), ("Rail", sm["rail"]), ("Stairs", st_txt)]) + "</dl>")
        w(_gallery(key, ["iso", "iso2"], have))
        w('<h2 class="kicker">Material take-off <span class="tag">NET = counted off the drawings · ORDER = what to pull and ship</span></h2>')
        for cat, lines in t.by_category().items():
            if cat == "Site":
                continue
            w(f"<h3>{E(cat)}</h3>")
            w(table(["NET", "ORDER", "Unit", "Item", "Why"], [[qfmt(l.net), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item), E(l.why)] for l in lines], "order", ["r", "r", "l", "l", "l"]))
        w('<h2 class="kicker">Fastener &amp; connector schedule</h2>')
        w('<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in t.schedule.items()) + "</dl>")
        w('<h2 class="kicker">Cut list</h2>' + table(["Member", "Stock", "Length", "Qty", "Note"], [[E(c.member), E(c.nominal), ftin(c.length_in), str(c.qty), E(c.note)] for c in t.cut_list], "", ["l", "l", "r", "r", "l"]))
        w('<h2 class="kicker pb">Drawing set <span class="tag">G · C · S · A · D sheets</span></h2><div class="sheets">')
        for num, ttl, svg in r["sheets"]:
            w(f'<details class="sheet" open><summary><b>{num}</b> {E(ttl)}</summary>{svg}</details>')
        w("</div>")
        w('<h2 class="kicker pb">Exploded views</h2>')
        w(_gallery(key, ["exploded", "exploded2", "structure-underiso", "frame-iso2"], have))
        w('<h2 class="kicker pb">Build set <span class="tag">T-400 series · goes in · how · check</span></h2>')
        w(_steps(key, r["steps"], cap, False))
        w('<h2 class="kicker">3D model <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>')
        w(viewer_html(S, None, title=f"{name} — 3D", standalone=False, uid=f"v3d-{key}"))
    elif proposal:
        opts = [(lab, run(sp_)[2]) for lab, sp_ in (o_ for o_ in (options or []) if not isinstance(o_, dict))]
        blocks = [o_ for o_ in (options or []) if isinstance(o_, dict)]
        w('<h2 class="kicker" id="g-reads">At a glance</h2>')
        w(_gallery(key, ["yard", "iso2"], have))
        w(_reads_lite(t, L, sm))
        w('<h2 class="kicker" id="g-what">What it is <span class="tag">included in the price</span></h2>')
        inc = qmd[qmd.index("## INCLUDED"):qmd.index("## PLAN")].replace("## INCLUDED — what it is\n", "")
        beams = sorted({b.size for b in spec.framing.beams}) if spec.framing.beams else []
        frame_lite = (f"{sm['joists']}; {sm['rims']}" + ((f"; {beam_words(beams, beam_species_words(spec.framing.beams), len(spec.framing.beams))}" if beams else "") if spec.framing.system != "steel" else "; boxed steel beams")
                      + (("; joist tape on every joist, rim and beam" if L.beam_lines else "; joist tape on every joist and rim") if spec.framing.joist_tape else "") + ".")
        if not hasattr(L, "parts"):           # a deck on two levels already reads its frame level by level, in the homeowner's words
            inc = re.sub(r"\| Frame \| .*? \|\n", f"| Frame | {frame_lite} |\n", inc, count=1)
        w(md_to_html(inc))
        w('<h2 class="kicker pb" id="g-renders">Renders <span class="tag">3D model · design intent</span></h2>')
        w(_gallery(key, ["corner", "corner2", "ondeck", "facade", "isolow", "under"], have))
        w(alt_html)
        w(sun_html)
        w('<h2 class="kicker pb" id="g-iso">Isometrics <span class="tag">the model from four corners</span></h2>')
        w(_gallery(key, ["iso", "iso2", "underiso", "plan"], have))
        w('<h2 class="kicker pb" id="g-exploded">Exploded views <span class="tag">every layer pulled apart</span></h2>')
        w(_gallery(key, ["exploded", "exploded2", "exploded-corner", "exploded-low"], have))
        w('<h2 class="kicker pb" id="g-structure">Under the deck <span class="tag">footings, posts, ' + ("beams, " if L.beam_lines else "") + 'frame</span></h2>')
        w(_gallery(key, ["structure-underiso", "frame-iso2"], have))
        ob = _option_blocks(spec, t, p, blocks, key, rd, files) if blocks else None
        if ob:
            w(ob["html"])
        opt_html = _options_table(p, opts) + (_options_summary(ob) if ob else "")
        if spec.extras.price_breakdown:
            nxt = re.sub(r"^## NEXT STEP\n", "", qmd[qmd.index("## NEXT STEP"):])
            w(PL.wheel(spec, p, opt_html, md_to_html(nxt)).replace('<section class="invest"', '<section class="invest" id="g-investment"', 1))
        else:
            w('<h2 class="kicker pb" id="g-investment">Investment</h2>')
            q2 = qmd[qmd.index("## PRICE"):qmd.index("## INCLUDED")]
            w('<div class="quote" style="break-before:auto;page-break-before:auto">' + md_to_html(q2) + opt_html + md_to_html(qmd[qmd.index("## NEXT STEP"):]) + "</div>")
        if viewer_url is not None:           # the interactive 3D page instead of the embedded viewer (PDF-first documents)
            w(_viewer_link(viewer_url, viewer_note))
        else:
            w('<h2 class="kicker" id="g-3d">3D model <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>')
            w(viewer_html(S, None, title=f"{name} — 3D", standalone=False, uid=f"v3d-{key}"))
    elif customer:
        w('<h2 class="kicker" id="g-reads">At a glance</h2>')
        w(_gallery(key, ["yard", "iso2"], have))
        w(_reads(t, L, sm, n_piers, True))
        w('<h2 class="kicker" id="g-what">What it is <span class="tag">included in the price</span></h2>')
        inc = qmd[qmd.index("## INCLUDED"):qmd.index("## PLAN")].replace("## INCLUDED — what it is\n", "")
        w(md_to_html(inc))
        if spec.extras.engineering_note:
            w(f'<p><b>Engineering and permit.</b> {E(spec.extras.engineering_note)}</p>')
        w('<h2 class="kicker pb" id="g-renders">Renders <span class="tag">3D model · design intent</span></h2>')
        w(_gallery(key, ["corner", "corner2", "ondeck", "facade", "under", "isolow"], have))
        w(alt_html)
        w(sun_html)
        w('<h2 class="kicker pb" id="g-iso">Isometrics <span class="tag">the model from four corners</span></h2>')
        w(_gallery(key, ["iso", "iso2", "isolow", "underiso"], have))
        w('<h2 class="kicker pb" id="g-exploded">Exploded views <span class="tag">every layer pulled apart</span></h2>')
        w(_gallery(key, ["exploded", "exploded2", "exploded-corner", "exploded-low"], have))
        w('<h2 class="kicker pb" id="g-structure">Structure <span class="tag">footings, posts, ' + ("beams, " if L.beam_lines else "") + 'frame, rail</span></h2>')
        w(_gallery(key, ["structure-underiso", "frame-iso2", "under", "rail-iso2"], have))
        w('<h2 class="kicker pb" id="g-sheets">Drawing set <span class="tag">G · S · A · D sheets</span></h2><div class="sheets">')
        for num, ttl, svg in r["sheets"]:
            w(f'<details class="sheet" {"open" if num == "S-101" else ""}><summary><b>{num}</b> {E(ttl)}</summary>{svg}</details>')
        w("</div>")
        w(_gallery(key, ["plan"], have))
        w(_order_customer(t).replace('id="g-materials"', ""))
        w('<h2 class="kicker" id="g-fastening">Fastening &amp; connectors</h2>')
        w('<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in t.schedule.items()) + "</dl>")
        w('<details><summary>Cut list</summary>' + table(["Member", "Stock", "Length", "Qty", "Note"], [[E(c.member), E(c.nominal), ftin(c.length_in), str(c.qty), E(c.note)] for c in t.cut_list], "", ["l", "l", "r", "r", "l"]) + "</details>")
        w('<h2 class="kicker pb" id="g-build">How it\'s built <span class="tag">step by step</span></h2>')
        w(_steps(key, r["steps"], cap, True))
        w('<h2 class="kicker" id="g-investment">Investment</h2>')
        q2 = qmd[:qmd.index("## INCLUDED")] + qmd[qmd.index("## PLAN"):]
        q2 = re.sub(r"## SCHEDULE\n.*?(?=## )", "", q2, flags=re.S)
        w('<div class="quote">' + md_to_html(q2) + "</div>")
        if viewer_url is not None:
            w(_viewer_link(viewer_url, viewer_note))
        else:
            w('<h2 class="kicker" id="g-3d">3D model <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>')
            w(viewer_html(S, None, title=f"{name} — 3D", standalone=False, uid=f"v3d-{key}"))
    else:
        w('<h2 class="kicker" id="g-reads">Design reads</h2>')
        w(_reads(t, L, sm, n_piers, False))
        notes = [n for n in t.notes if not n.startswith(f"{len(L.zones)} zones")]
        if notes:
            w('<ul class="notes">' + "".join(f"<li>{E(n)}</li>" for n in notes) + "</ul>")
        w('<h2 class="kicker" id="g-flags">Site &amp; code flags <span class="tag">internal</span></h2><ul class="flags">')
        for f in flags:
            w(f'<li class="sev-{f.severity.lower()}"><span class="sev">{f.severity}</span><span class="topic">{E(f.topic)}</span><span class="txt">{E(f.text)}{(" <em>" + E(f.ref) + "</em>") if f.ref else ""}</span></li>')
        w("</ul>")
        w(_order_internal(t))
        w('<h2 class="kicker">Fastener &amp; connector schedule</h2>')
        w('<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in t.schedule.items()) + "</dl>")
        w('<details><summary>Cut list</summary>' + table(["Member", "Stock", "Length", "Qty", "Note"], [[E(c.member), E(c.nominal), ftin(c.length_in), str(c.qty), E(c.note)] for c in t.cut_list], "", ["l", "l", "r", "r", "l"]) + "</details>")
        blocks = [o_ for o_ in (options or []) if isinstance(o_, dict)]      # the proposal's option blocks: how each is priced, estimates called out
        if cost_only and not spec.extras.sell_override:      # a bid: the cost stack with its margin (a sold job gets cost-to-build only)
            w(_stack(p, None))
            cats = t.by_category()
            w("<h3>Materials by category</h3>")
            w(table(["Category", "Lines", "Cost"], [[E(c), str(len(ls)), money(sum(l.ext for l in ls), True)] for c, ls in cats.items()] + [["<b>Materials (raw)</b>", "", f"<b>{money(p.materials, True)}</b>"]], "", ["l", "r", "r"]))
            if blocks:
                w(_options_internal(_option_blocks(spec, t, p, blocks, key, rd, {})))
        elif cost_only:
            cost_html, cost_total, tax_raw = _cost_stack(p, t)
            w(cost_html)
        else:
            w(_stack(p, spec.extras.sell_override))
            if blocks:
                w(_options_internal(_option_blocks(spec, t, p, blocks, key, rd, {})))
            w('<h2 class="kicker">The quote <span class="tag">homeowner-facing · facts only</span></h2>')
            w('<div class="quote">' + md_to_html(qmd) + "</div>")
        w('<h2 class="kicker">Renders <span class="tag">3D model · design intent · ' + ("timbers shown with the optional oil finish" if S.meta["timber"] and not S.meta["oiled"] else "frame shown as specified") + "</span></h2>")
        w(_gallery(key, ["yard", "corner", "corner2", "ondeck", "facade", "under"], have))
        w(alt_html)
        w(sun_html)
        w('<h2 class="kicker">Isometrics</h2>')
        w(_gallery(key, ["iso", "iso2", "isolow", "underiso", "plan"], have))
        w('<h2 class="kicker">Exploded</h2>')
        w(_gallery(key, ["exploded", "exploded2", "exploded-corner", "exploded-low"], have))
        w('<h2 class="kicker">Drawing set <span class="tag">G · S · A · D sheets — permit set with G-001 on top</span></h2><div class="sheets">')
        for num, ttl, svg in r["sheets"]:
            w(f'<details class="sheet" {"open" if num == "S-101" else ""}><summary><b>{num}</b> {E(ttl)}</summary>{svg}</details>')
        w("</div>")
        w('<h2 class="kicker">Build set <span class="tag">T-400 series · goes in · how · check</span></h2>')
        w(_steps(key, r["steps"], cap, False))
        w('<h2 class="kicker">3D model <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>')
        w(viewer_html(S, None, title=f"{name} — 3D", standalone=False, uid=f"v3d-{key}"))
    w("</section>")
    section = "".join(o)
    strip = ('<div class="strip"><div><span class="sl">Check or ACH</span><span class="sv">%s</span></div><div><span class="sl">Financed</span><span class="sv">%s</span></div>'
             '<div><span class="sl">Monthly</span><span class="sv">%s</span></div><div><span class="sl">Square feet</span><span class="sv">%g</span></div>'
             '<div><span class="sl">Footings</span><span class="sv">%d</span></div><div><span class="sl">Rail</span><span class="sv">%g LF</span></div></div>'
             % (money(p.sell), money(p.retail), money(p.monthly), L.deck_sf, n_piers, (L.rail.rail_lf if L.rail else 0)))
    if spec.extras.sell_override:
        strip = ('<div class="strip"><div><span class="sl">Sold · check or ACH</span><span class="sv">%s</span></div><div><span class="sl">Cost</span><span class="sv">%s</span></div>'
                 '<div><span class="sl">Gross profit</span><span class="sv">%s</span></div><div><span class="sl">Margin</span><span class="sv">%.1f%%</span></div>'
                 '<div><span class="sl">Financed</span><span class="sv">%s</span></div><div><span class="sl">Square feet</span><span class="sv">%g</span></div></div>'
                 % (money(p.sell), money(p.cost), money(p.gp), 100 * p.gp / p.sell, money(p.retail), L.deck_sf))
    if customer:
        who = ("Prepared for " + spec.client if spec.client else "Prepared for the owner") + (f" · {addr}" if addr else "")
        head = PL.cover(spec, L, sm, p, key, hero, have, name, who, lede, today, n_piers, t=t)
        body = head + '<main class="wrap">' + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Renders and drawings are design intent; dimensions on the sheets govern. Numbers hold 30 days.</span></footer></main>'
        title = f"{name} — Proposal"
    elif supplier:
        strip = ('<div class="strip"><div><span class="sl">Square feet</span><span class="sv">%g</span></div><div><span class="sl">Footings</span><span class="sv">%d</span></div>'
                 '<div><span class="sl">Order lines</span><span class="sv">%d</span></div><div><span class="sl">Height</span><span class="sv">%s</span></div></div>'
                 % (L.deck_sf, n_piers, sum(1 for l in t.lines if l.category != "Site"), ftin(spec.geometry.height_in)))
        head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · material take-off + build set · for Decks &amp; Docks</div><h1>{E(name)}</h1>'
                f'<p>{E(sub or addr)} · {E(today)}</p><p>Account GSEXT1 · ship to {E(addr)} · please quote every line; call Jade Pender 303-550-9558 with substitutions.</p></div></header>')
        body = head + '<main class="wrap">' + strip + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Quantities from the drawings' + ("; the stamped engineering set governs structure" if spec.extras.engineered else "") + '. Quote requested — no pricing on this sheet.</span></footer></main>'
        title = f"{name} — Take-off + Build Set"
    elif cost_only and not spec.extras.sell_override:
        strip = ('<div class="strip"><div><span class="sl">Check or ACH</span><span class="sv">%s</span></div><div><span class="sl">Financed</span><span class="sv">%s</span></div>'
                 '<div><span class="sl">Cost</span><span class="sv">%s</span></div><div><span class="sl">Gross profit</span><span class="sv">%s</span></div>'
                 '<div><span class="sl">Margin</span><span class="sv">%.1f%%</span></div><div><span class="sl">Square feet</span><span class="sv">%g</span></div></div>'
                 % (money(p.sell), money(p.retail), money(p.cost), money(p.gp), 100 * p.gp / p.sell, L.deck_sf))
        head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · cost stack · internal</div><h1>{E(name)}</h1>'
                f'<p>{E(sub or addr)}</p></div></header>')
        body = head + '<main class="wrap">' + strip + section + f'<footer><span>GS Exterior Experts · Deck Division</span><span>Cost stack: materials at the order x {p.material_factor:g}, tax, labor at the rate card, site services at cost; {p.gm:.1%} GM on the work. Internal — not for the homeowner.</span></footer></main>'
        title = f"{name} — Cost Stack"
    elif cost_only:
        tax_raw = round(p.materials * p.tax_rate, 2)
        cost_total = round(p.materials + tax_raw + p.labor + p.gc, 2)
        strip = ('<div class="strip"><div><span class="sl">Cost to build</span><span class="sv">%s</span></div><div><span class="sl">Materials</span><span class="sv">%s</span></div>'
                 '<div><span class="sl">Tax</span><span class="sv">%s</span></div><div><span class="sl">Labor</span><span class="sv">%s</span></div>'
                 '<div><span class="sl">Site services</span><span class="sv">%s</span></div><div><span class="sl">Square feet</span><span class="sv">%g</span></div></div>'
                 % (money(cost_total), money(p.materials), money(tax_raw), money(p.labor), money(p.gc), L.deck_sf))
        head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · sold — cost to build</div><h1>{E(name)}</h1>'
                f'<p>{E(sub or addr)}</p></div></header>')
        body = head + '<main class="wrap">' + strip + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Cost to build: materials at invoice, labor at the rate card, site services at cost. Internal.</span></footer></main>'
        title = f"{name} — Cost to Build"
    else:
        head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · takeoff + build set</div><h1>{E(name)}</h1>'
                f'<p>{E(sub or addr)}</p></div></header>')
        gm_note = (f"sold at {money(p.sell)} · {p.gp / p.sell:.1%} margin on the sold price ({p.gm:.1%} on the work)" if spec.extras.sell_override else
                   f"{p.gm:.1%} GM" + (" (owner-set, under the 40% floor)" if spec.extras.gm_below_floor else ""))
        body = head + '<main class="wrap">' + strip + section + f'<footer><span>GS Exterior Experts · Deck Division</span><span>Prices: rate card · {E(gc_name(p.gc_lines, "GC"))} at cost · {gm_note} · financed ÷ 0.93 unless the job says otherwise. Internal — not for the homeowner.</span></footer></main>'
        title = f"{name} — Takeoff + Build Set"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>{FONT}{CSS}"
            + (PL.FONT + PL.CSS if customer else "") + (LEVELS_CSS if hasattr(L, "parts") else "")
            + (PL.OPTIONS_CSS if customer and (viewer_url is not None or any(isinstance(o_, dict) for o_ in (options or []))) else "")
            + "</head>" + ('<body class="proposal">' if customer else "<body>")
            + body + CDN + "<script>window.addEventListener('load', function(){ window.dispatchEvent(new Event('resize')); });</script>" + (PL.JS if customer else "") + "</body></html>\n")
    # the viewer inlines its own CDN tag: keep one, hoist the viewer script after it
    page = page.replace(CDN, "", 1)
    scripts = re.findall(r"<script>\n\(function\(\)\{\nconst D = .*?\n\}\)\(\);\n</script>", page, flags=re.S)
    for sc in scripts:
        page = page.replace(sc, "", 1)
    page = page.replace(CDN, CDN + "\n" + "\n".join(scripts) + "\n", 1)
    if supplier:
        txt = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
        for bad in ("$", "margin", "Margin", "Check or ACH", "Financed", "rate card"):
            assert bad not in txt, f"supplier sheet carries pricing wording: {bad}"
    if customer:
        txt = re.sub(r"<script.*?</script>", "", page, flags=re.S)
        for bad in ("internal", "INTERNAL", "owner-directed", "rate card", "cost stack", "GM"):
            assert bad not in txt, f"customer page carries internal wording: {bad}"
    (out / "page.html").write_text(page)
    json.dump(files, open(out / "files.json", "w"), indent=1)
    result = dict(html=str(out / "page.html"), files=files, pricing=p, takeoff=t)
    if pdf:
        result["pdf"] = render_pdf(page, files, str(out / "page.pdf"), key, hero="isolow" if "isolow" in have else hero)
    return result


# ================================================================== the louvered roof's own document ("make it a whole other document")
def _plan_boxes(L) -> list:
    """The deck's zone rectangles in the job frame (feet): [(level, zone, x0, x1, y0, y1, surface z ft)]."""
    if hasattr(L, "parts"):
        out = []
        for p in L.parts:
            for z in p.layout.zones:
                x0, x1, y0, y1 = p.placement.box(z.x0 / 12, (z.x0 + z.W) / 12, z.wall_y / 12, (z.wall_y + z.D) / 12)
                out.append((p.name, z.name, x0, x1, y0, y1, p.spec.geometry.height_in / 12))
        return out
    return [("Deck", z.name, z.x0 / 12, (z.x0 + z.W) / 12, z.wall_y / 12, (z.wall_y + z.D) / 12, L.spec.geometry.height_in / 12) for z in L.zones]


def _roof_plan_svg(L, q) -> str:
    """Plan (house at the top, the yard below): every deck zone shaded by its level, the house walls, the roof's frame
    hatched with its posts, the size and the level heights. Feet are the drawing units."""
    boxes = _plan_boxes(L)
    xs = [b[2] for b in boxes] + [b[3] for b in boxes] + [q["x0"], q["x1"]]
    ys = [b[4] for b in boxes] + [b[5] for b in boxes] + [q["y0"], q["y1"]]
    x0, x1, y0, y1 = min(xs) - 1.5, max(xs) + 1.5, min(ys) - 3.2, max(ys) + 4.2
    zs = sorted({round(b[6], 3) for b in boxes})
    fill = {z: c for z, c in zip(zs, ["#e7dfd0", "#cbbb9f", "#b5a284", "#a08d70"])}
    f = 'font-family="Nunito Sans, Segoe UI, sans-serif"'
    s = [f'<svg viewBox="{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}" role="img" aria-label="Plan of the deck with the louvered roof">',
         '<defs><pattern id="lvh" width="0.9" height="0.9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
         '<rect width="0.9" height="0.9" fill="rgba(20,20,22,.22)"/><line x1="0" y1="0" x2="0" y2="0.9" stroke="#141416" stroke-width="0.16"/></pattern></defs>']
    for lv, zn, a, b, c, d, z in boxes:
        s.append(f'<rect x="{a:.3f}" y="{c:.3f}" width="{b - a:.3f}" height="{d - c:.3f}" fill="{fill[round(z, 3)]}" stroke="#8a8172" stroke-width="0.08"/>')
        s.append(f'<line x1="{a:.3f}" y1="{c:.3f}" x2="{b:.3f}" y2="{c:.3f}" stroke="#3a352d" stroke-width="0.45"/>')
    s.append(f'<rect x="{q["x0"]:.3f}" y="{q["y0"]:.3f}" width="{q["W"]:.3f}" height="{q["D"]:.3f}" fill="url(#lvh)" stroke="#141416" stroke-width="0.24"/>')
    for pt in q["posts"]:
        h = q["post"] / 2
        s.append(f'<rect x="{pt["x"] - h:.3f}" y="{pt["y"] - h:.3f}" width="{2 * h:.3f}" height="{2 * h:.3f}" fill="#141416"/>')
    cx, cy = (q["x0"] + q["x1"]) / 2, (q["y0"] + q["y1"]) / 2
    s.append(f'<rect x="{cx - 6.6:.2f}" y="{cy - 1.55:.2f}" width="13.2" height="3.1" rx="0.3" fill="#fbf9f4" opacity="0.92"/>')
    s.append(f'<text x="{cx:.2f}" y="{cy - 0.2:.2f}" text-anchor="middle" font-size="1.15" font-weight="800" fill="#141416" {f}>{E(q["name"])}</text>')
    s.append(f'<text x="{cx:.2f}" y="{cy + 1.05:.2f}" text-anchor="middle" font-size="0.95" fill="#3a352d" {f}>{E(ftin(q["W"] * 12))} x {E(ftin(q["D"] * 12))} · {q["area"]:g} SF</text>')
    by_level = {}
    for lv, zn, a, b, c, d, z in boxes:
        e = by_level.setdefault(lv, [a, b, d, z])
        e[0], e[1], e[2] = min(e[0], a), max(e[1], b), max(e[2], d)
    for lv, (a, b, d, z) in by_level.items():
        s.append(f'<text x="{(a + b) / 2:.2f}" y="{d + 1.6:.2f}" text-anchor="middle" font-size="1.0" font-weight="700" fill="#534d45" {f}>{E(lv)} · {E(ftin(z * 12))} above grade</text>')
    s.append(f'<text x="{(x0 + x1) / 2:.2f}" y="{y0 + 1.6:.2f}" text-anchor="middle" font-size="0.95" letter-spacing="0.3" fill="#8a8172" {f}>HOUSE</text>')
    s.append(f'<text x="{(x0 + x1) / 2:.2f}" y="{y1 - 0.6:.2f}" text-anchor="middle" font-size="0.95" letter-spacing="0.3" fill="#8a8172" {f}>YARD</text>')
    s.append("</svg>")
    return "".join(s)


def render_addon(spec: DeckSpec, out_dir: str, key: str = "roof", name: Optional[str] = None, lede: str = "", hero: str = "corner",
                 renders_dir: Optional[str] = None, pdf: bool = False, date_line: Optional[str] = None, roof: int = 0,
                 viewer_url: Optional[str] = None, viewer_note: Optional[str] = None, addon: Optional[dict] = None) -> dict:
    """The louvered roof's own proposal, in the deck proposal's look: cover (hero render of the deck with the roof, the
    roof's numbers, its price three ways), what it is, size and placement (a plan), structure, controls / gutters / lights,
    the screens add-on (its own price line and renders), the roof rendered (open and closed), warranty, investment, schedule,
    terms, the link to the interactive 3D page. The roof is louvered.roofs_of(spec)[roof]; its price is its own (price, or
    price_per_sf x its area), financed and monthly the way the deck's price gets them; nothing here touches the deck's price.
    addon (all optional): renders [name | (name, caption)] (default: every roof-*.jpg in renders_dir), screens dict(price,
    renders, words, label) (price overrides the engine's estimate), facts {section: [lines]} over PL.LOUVER_FACTS, schedule
    [lines], exclusions [lines], deck_note (a line on the deck the roof goes on). Returns {"html", "files", "pdf"?, "pricing"}."""
    from . import run
    from .louvered import roofs_of, resolve, surfaces_of, roof_pricing, scope_words, ANGLE_RANGE
    from .pricing import fixed_terms, price_louvered
    from datetime import date
    a = dict(addon or {})
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    t, flags, _p_deck = run(spec)
    L = t.layout
    roofs = roofs_of(spec)
    if not roofs:
        raise ValueError("render_addon: the spec carries no louvered roof (geometry.louvered_roofs)")
    r = roofs[roof]
    q = resolve(r, surfaces_of(L))
    rp = roof_pricing(spec, L)["roofs"][roof]
    ap = price_louvered(spec, r)                     # the same rule the deck proposal's option block uses
    c, f, m = ap.sell, ap.retail, ap.monthly
    show_fin = spec.extras.show_financing
    facts = {k: list(v) for k, v in PL.LOUVER_FACTS.items()}
    facts.update(a.get("facts") or {})
    rd = Path(renders_dir) if renders_dir else out / "renders"
    have = {x.stem for x in rd.glob("*.jpg")} if rd.exists() else set()
    files = {f"r/{key}-{n_}.jpg": str(rd / f"{n_}.jpg") for n_ in have}
    CAP.clear(); CAP.update(CAP0)
    if (rd / "captions.json").exists():
        CAP.update(json.load(open(rd / "captions.json")))
    today = date_line or date.today().strftime("%B %d, %Y")
    addr = ", ".join(x for x in (spec.site.address, spec.site.city, f"{spec.site.state} {spec.site.zip}".strip()) if x)
    name = name or f"{q['name']} · {spec.site.address}".strip(" ·")
    # ---- the screens add-on: the engine's estimate (internal sets say so) unless the job sets the price
    sa = dict(a.get("screens") or {})
    scr = rp.get("screens") or []
    if sa.get("price") is not None:
        sc_c, sc_f, sc_m = fixed_terms(spec, sa["price"])
        sc_est = False
    elif scr:
        sc_c, sc_f, sc_m = fixed_terms(spec, rp["screens_sell"])
        sc_est = bool(rp.get("screens_estimate"))
    else:
        sc_c = sc_f = sc_m = 0
        sc_est = False
    has_screens = bool(sc_c)
    # ---- cover
    title, eyebrow = PL._title_parts(name, spec.site.address)
    eyebrow = " · ".join(x for x in (eyebrow, ", ".join(x for x in (spec.site.city, spec.site.state) if x)) if x)
    rail_posts = sum(1 for pt in q["posts"] if pt["on_rail"])
    tele = [(f"{q['area']:g}", "square feet"), (ftin(q["W"] * 12), "along the house"), (ftin(q["D"] * 12), "out from the house"),
            (ftin(q["clear_ft"] * 12), "clear under the beams"), (str(len(q["blades"])), "louver blades"), (str(len(q["posts"])), "posts on the deck")]
    prices = ([("Check or ACH", money(c), f"{(1 - c / f) * 100:.0f}% below the financed price"), ("Financed", money(f), "no money down"),
               ("Monthly", money(m), "6.99% · 10 years")] if show_fin else [("Price · check or ACH", money(c), "")])
    chips = [(q["hex"], "Roof", f"{q['brand']} {q['product']} · {str(q['color']).capitalize()}")]
    if has_screens and scr:
        sc0 = scr[0]
        chips.append(({"black": "#141416", "white": "#ecebe6"}.get(str(sc0.get("color", "")).lower(), "#3a3a3c"), "Screens (add-on)",
                      ("Clear vinyl" if sc0.get("fabric") == "vinyl" else f"{str(sc0.get('color', '')).capitalize()} mesh")))
    from .catalog import BOARDS_PALETTE
    pal = BOARDS_PALETTE.get((spec.decking.collection, spec.decking.color))
    chips.append((pal[len(pal) // 2] if pal else "#73624a", "On the deck", f"{spec.decking.brand} {spec.decking.collection} · {spec.decking.color}"))
    hero_html = f'<img class="hero-img" src="r/{key}-{hero}.jpg" alt="Rendering of the deck with the louvered roof">' if hero in have else ""
    who = ("Prepared for " + spec.client if spec.client else "Prepared for the owner") + (f" · {addr}" if addr else "")
    head = PL.addon_cover(title, eyebrow, who, today, hero_html, tele, prices, chips, lede, mission=f"{q['brand']} {q['product']} · Proposal")
    o = []; w = o.append
    w(f'<section class="job" id="job-{key}">')
    # ---- what it is
    w('<h2 class="kicker" id="g-what">What it is <span class="tag">' + E(f"{q['brand']} {q['product']}") + "</span></h2>")
    if facts.get("what"):
        w("<ul class='opt-scope'>" + "".join(f"<li>{E(x)}</li>" for x in facts["what"]) + "</ul>")
    w("<h3>This roof</h3><ul class='opt-scope'>" + "".join(f"<li>{E(x)}</li>" for x in scope_words(q)) + "</ul>")
    # ---- size and placement
    under = sorted({f"{b[0]} {b[1]}" for b in _plan_boxes(L) if min(q["x1"], b[3]) - max(q["x0"], b[2]) > 0.5 and min(q["y1"], b[5]) - max(q["y0"], b[4]) > 0.5})
    w('<h2 class="kicker pb" id="g-size">Size and placement <span class="tag">plan · house at the top</span></h2>')
    w(f'<figure class="plan-fig">{_roof_plan_svg(L, q)}<figcaption>The roof (hatched) and its posts over the deck; the darker the deck, the higher the level.</figcaption></figure>')
    reads = [("Size", f"{ftin(q['W'] * 12)} along the house x {ftin(q['D'] * 12)} out from it, {q['area']:g} SF"),
             ("Over", (", ".join(under) if under else "the deck") + (f" — {ftin(q['z_deck'] * 12)} above grade" if q["z_deck"] else "")),
             ("House side", "attached to the house at the soffit / roof line — no posts at the house" if q["attach"] == "house" else "freestanding, posts at every corner"),
             ("Height", f"top of the frame {ftin((q['z_top'] - q['z_deck']) * 12)} above the deck; {ftin(q['clear_ft'] * 12)} clear under the beams")]
    if a.get("deck_note"):
        reads.append(("The deck", a["deck_note"]))
    w('<dl class="reads levels">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in reads) + "</dl>")
    # ---- structure
    w('<h2 class="kicker" id="g-structure">Structure <span class="tag">how it stands</span></h2>')
    st = [("Posts", f"{len(q['posts'])} {q['post'] * 12:g}x{q['post'] * 12:g} aluminum posts on base plates on the deck"
           + (f"; {'both are' if rail_posts == 2 else ('it is' if rail_posts == 1 else f'{rail_posts} are')} the rail post{'s' if rail_posts != 1 else ''} there — the rail panels bracket into {'them' if rail_posts != 1 else 'it'}" if rail_posts else "")),
          ("Frame", f"{q['beam_label']} aluminum perimeter beams with the gutter built in" + (f"; {len(q['xs']) + len(q['ys'])} zone divider beam{'s' if len(q['xs']) + len(q['ys']) != 1 else ''}" if (q['xs'] or q['ys']) else "")),
          ("House side", "the house-side beam is carried on brackets at the soffit / roof line" if q["attach"] == "house" else "posts at every corner")]
    over = _posts_over_columns(L, q)
    if over is not None:
        st.append(("Under the posts", over))
    st += [(k, v) for k, v in (facts.get("structure_rows") or [])]
    w('<dl class="reads levels">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in st) + "</dl>")
    # ---- controls, motor, gutters, lights
    groups = [("Controls and motor", facts.get("controls")), ("Gutters and drainage", facts.get("gutters")), ("Lights", facts.get("lights") if q["lights"] else None),
              ("Sensors and add-ons Suncoast offers", facts.get("accessories"))]
    groups = [(h_, v_) for h_, v_ in groups if v_]
    if groups:
        w('<h2 class="kicker" id="g-controls">Controls, motor, gutters, lights</h2><div class="facts-cols">'
          + "".join(f"<div><h3>{E(h_)}</h3><ul>" + "".join(f"<li>{E(x)}</li>" for x in v_) + "</ul></div>" for h_, v_ in groups) + "</div>")
    # ---- the screens add-on
    if has_screens:
        figs = _render_figs(dict(renders=sa.get("renders") or sorted(n_ for n_ in have if n_.startswith("screens-")), renders_dir=sa.get("renders_dir") or str(rd)),
                            rd, key, "screens", files)
        words = sa.get("words") or ([x["words"] for x in scr] if scr else [])
        w('<section class="optblock" id="g-screens" aria-labelledby="oh-screens"><div class="opt-head"><div class="opt-title">'
          f'<span class="eyebrow">Add-on</span><h3 id="oh-screens">{E(sa.get("label") or "Motorized screens")}</h3></div>{_price_trio(sc_c, sc_f, sc_m, show_fin)}</div><div class="opt-body">'
          + (f'<p class="opt-blurb">{E(sa["blurb"])}</p>' if sa.get("blurb") else "")
          + ("<ul class='opt-scope'>" + "".join(f"<li>{E(x)}</li>" for x in list(words) + list(facts.get("screens") or [])) + "</ul>" if (words or facts.get("screens")) else "")
          + ('<div class="gal">' + "".join(figs) + "</div>" if figs else "") + "</div></section>")
    # ---- the roof rendered (default: every roof-* still, by the time in its name, open before closed)
    def _ord(n_):
        tm = re.findall(r"\d{3,4}", n_)
        return (int(tm[-1]) if tm else 0, 0 if "open" in n_ else 1, n_)
    rn = a.get("renders") or sorted((n_ for n_ in have if n_.startswith("roof-")), key=_ord)
    figs = _render_figs(dict(renders=rn, renders_dir=str(rd)), rd, key, "roof", files)
    if figs:
        w('<h2 class="kicker pb" id="g-renders">The roof, rendered <span class="tag">louvers open and closed through the day · design intent</span></h2>')
        w('<div class="gal">' + "".join(figs) + "</div>")
    # ---- warranty
    if facts.get("warranty"):
        w('<h2 class="kicker" id="g-warranty">Warranty</h2><ul class="opt-scope">' + "".join(f"<li>{E(x)}</li>" for x in facts["warranty"]) + "</ul>")
    # ---- investment, schedule, terms
    rows = [(f"{q['brand']} {q['product']} — {ftin(q['W'] * 12)} x {ftin(q['D'] * 12)}", c, f, m, "item")]
    if has_screens:
        rows.append((sa.get("label") or "Motorized screens", sc_c, sc_f, sc_m, "addon"))
        tf = f + sc_f
        from .pricing import _monthly
        rows.append(("The roof with the screens", c + sc_c, tf, _monthly(tf), "total"))
    terms = ["This is a fixed-price proposal on the selections above. Check or ACH, or financed with approved credit. Numbers hold 30 days.",
             "The roof is priced on its own; the deck's price does not include it."] + list(a.get("terms") or [])
    w(PL.addon_invest(rows, (c, f, m), "".join(f"<p>{E(x)}</p>" for x in terms), title="The roof's price", show_fin=show_fin))
    lvl = next((b[0] for b in _plan_boxes(L) if f"{b[0]} {b[1]}" in under), "")
    sched = a.get("schedule") or ([f"Installed after the deck is built: the roof's posts stand on the new {lvl.lower() if lvl and lvl != 'Deck' else 'deck'}."]
                                  + list(facts.get("schedule") or []))
    if sched:
        w('<h2 class="kicker" id="g-schedule">Schedule</h2><ol class="opt-scope">' + "".join(f"<li>{E(x)}</li>" for x in sched) + "</ol>")
    excl = list(a.get("exclusions") or []) + list(facts.get("exclusions") or [])
    if excl:
        w('<h2 class="kicker" id="g-terms">Not included</h2><ul class="opt-scope">' + "".join(f"<li>{E(x)}</li>" for x in excl) + "</ul>")
    if viewer_url is not None:
        w(_viewer_link(viewer_url, viewer_note))
    w("</section>")
    body = head + '<main class="wrap">' + "".join(o) + ('<footer><span>GS Exterior Experts · Deck Division</span><span>Renders are design intent. '
                                                       f'{E(q["brand"])} product details per the manufacturer. Numbers hold 30 days.</span></footer></main>')
    title_ = f"{name} — Proposal"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title_)}</title>{FONT}{CSS}"
            + PL.FONT + PL.CSS + LEVELS_CSS + PL.OPTIONS_CSS + "</head><body class=\"proposal\">" + body + "</body></html>\n")
    txt = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    for bad in ("internal", "INTERNAL", "rate card", "cost stack", "GM", "ESTIMATE", "estimate"):
        assert bad not in txt, f"roof document carries internal wording: {bad}"
    (out / "page.html").write_text(page)
    json.dump(files, open(out / "files.json", "w"), indent=1)
    pr = dict(roof=dict(sell=c, financed=f, monthly=m, area_sf=q["area"], basis=ap.basis),
              screens=dict(sell=sc_c, financed=sc_f, monthly=sc_m, estimate=sc_est) if has_screens else None)
    result = dict(html=str(out / "page.html"), files=files, pricing=pr, roof=q)
    if pdf:
        result["pdf"] = render_pdf(page, files, str(out / "page.pdf"), key, hero=hero)
    return result


def _posts_over_columns(L, q) -> Optional[str]:
    """Whether each roof post stands over a deck column (a beam-line post or an edge post within 1') — said only when true."""
    cols = []
    parts = L.parts if hasattr(L, "parts") else None
    for p in (parts or [None]):
        Lp = p.layout if p is not None else L
        tr = (lambda x, y: p.placement.pt(x, y)) if p is not None else (lambda x, y: (x, y))
        for bl in Lp.beam_lines:
            cols += [tr(px / 12, bl.y / 12) for px in bl.posts_x]
        for ep in getattr(Lp, "edge_posts", None) or []:
            cols.append(tr(getattr(ep, "x", 0) / 12, getattr(ep, "y", 0) / 12))
    if not q["posts"] or not cols:
        return None
    if all(any(math.hypot(pt["x"] - cx, pt["y"] - cy) <= 1.0 for cx, cy in cols) for pt in q["posts"]):
        return "each post stands over a deck column, so its load goes straight down to a footing"
    return None


def render_pdf(page: str, files: Dict[str, str], pdf_path: str, key: str, hero: str = "isolow") -> str:
    """Print the page to Letter PDF with Chromium: images copied beside a print copy, sheets expanded, 3D swapped for a still."""
    from .render import _chromium
    from playwright.sync_api import sync_playwright
    pdf_path = str(Path(pdf_path).resolve())
    out = Path(pdf_path).parent
    for k, v in files.items():
        (out / k).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(v, out / k)
    p = re.sub(r"<script.*?</script>", "", page, flags=re.S).replace(' loading="lazy"', "")
    p = re.sub(r'<nav class="nav">.*?</nav>', "", p, flags=re.S)
    m = re.search(r'<h2 class="kicker"[^>]*>3D model.*?(?=<footer)', p, flags=re.S)
    if m:
        p = p[:m.start()] + f'<h2 class="kicker">3D model</h2><figure><img src="r/{key}-{hero}.jpg" alt="3D"><figcaption>The interactive 3D model lives at the online version of this document.</figcaption></figure>' + p[m.end():]
    p = p.replace("<details", "<details open").replace("</head>", PRINT_CSS + PL.PRINT_CSS + "</head>")
    (out / "_print.html").write_text(p)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1000, "height": 1300})
        pg.goto("file://" + str(out / "_print.html")); pg.wait_for_timeout(3000)
        pg.emulate_media(media="print")
        pg.pdf(path=pdf_path, format="Letter", print_background=True, prefer_css_page_size=True)
        b.close()
    return pdf_path


# ================================================================== several decks in one homeowner document
EXTRA_CSS = """<style>
.short{list-style:none;margin:0;padding:0;display:grid;gap:10px;} .short li{display:grid;grid-template-columns:150px 1fr;gap:12px;font-size:16px;line-height:1.45;} .short b{color:var(--ink-3);font-size:12px;letter-spacing:.14em;text-transform:uppercase;padding-top:4px;font-weight:800;}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start;} .two .reads{grid-template-columns:86px 1fr;}
.bigtab td,.bigtab th{font-size:16px;padding:12px 10px;} .bigtab tr.total td{font-weight:900;font-size:19px;border-top:2px solid var(--ink);}
.deckhead{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:8px 0 12px;} .deckhead .price{font-size:26px;font-weight:900;letter-spacing:-.01em;} .deckhead .sub{color:var(--ink-3);font-size:13px;}
@media (max-width:640px){.two{grid-template-columns:1fr;} .short li{grid-template-columns:1fr;gap:2px;}}
</style>"""


def render_combined(parts: list, out_dir: str, key: str, name: str, lede: str, hero_from: int = 0, hero: str = "corner",
                    short: Optional[list] = None, pdf: bool = False, date_line: Optional[str] = None) -> dict:
    """One homeowner document for several decks. parts = [dict(spec, renders_dir, key, title, blurb, options=[(label, DeckSpec)])].
    Sections: cover (both prices), the short version, one block per deck (two pictures, at a glance, what it is), the choices,
    the pictures (isometrics and exploded views), investment (per deck, both, options), next step, 3D."""
    from . import run
    from .buildset import build_set
    from .viewer import viewer_html
    from datetime import date
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    built = []
    files: Dict[str, str] = {}
    for pt in parts:
        t, flags, p = run(pt["spec"])
        r = build_set(t, flags, str(out / f"buildset-{pt['key']}"), render=False, customer=True)
        rd = Path(pt["renders_dir"])
        have = {q.stem for q in rd.glob("*.jpg")}
        files.update({f"r/{pt['key']}-{q.stem}.jpg": str(q) for q in rd.glob("*.jpg")})
        opts = [(lab, run(sp_)[2]) for lab, sp_ in pt.get("options", [])]
        built.append(dict(pt, t=t, p=p, L=t.layout, sm=t.summary, S=r["scene"], have=have, opts=opts, qmd=quote_markdown(t, p)))
    spec0 = parts[0]["spec"]
    addr = ", ".join(x for x in (spec0.site.address, spec0.site.city, f"{spec0.site.state} {spec0.site.zip}".strip()) if x)
    today = date_line or date.today().strftime("%B %d, %Y")
    sell = sum(b["p"].sell for b in built); retail = sum(b["p"].retail for b in built); monthly = sum(b["p"].monthly for b in built)
    hk = parts[hero_from]["key"]
    o = []; w = o.append
    w(f'<section class="job" id="job-{key}">')
    # the short version
    w('<h2 class="kicker" id="g-short">The short version</h2>')
    if short:
        w('<ul class="short">' + "".join(f"<li><b>{E(a)}</b><span>{E(b)}</span></li>" for a, b in short) + "</ul>")
    # one block per deck
    for b in built:
        p = b["p"]
        w(f'<h2 class="kicker pb" id="g-{b["key"]}">{E(b["title"])}</h2>')
        w(f'<div class="deckhead"><span class="price">{money(p.sell)}</span><span class="sub">check or ACH · {money(p.retail)} financed · {money(p.monthly)} a month</span></div>')
        if b.get("blurb"):
            w(f'<p>{E(b["blurb"])}</p>')
        w(_gallery(b["key"], ["yard", "iso2"], b["have"]))
        w(_reads_lite(b["t"], b["L"], b["sm"]))
        qmd = b["qmd"]
        inc = qmd[qmd.index("## INCLUDED"):qmd.index("## PLAN")].replace("## INCLUDED — what it is\n", "")
        sp_ = b["spec"]
        beams = sorted({bm.size for bm in sp_.framing.beams}) if sp_.framing.beams else []
        frame_lite = f"{b['sm']['joists']}; {b['sm']['rims']}" + (f"; {beam_words(beams)}" if beams else "") + "."
        inc = re.sub(r"\| Frame \| .*? \|\n", f"| Frame | {frame_lite} |\n", inc, count=1)
        w('<h3>What it is</h3>' + md_to_html(inc))
    # the choices
    if any(b["opts"] for b in built):
        w('<h2 class="kicker pb" id="g-choices">Your choices</h2>')
        for b in built:
            if b["opts"]:
                w(f'<p><b>{E(b["title"])}.</b> The price above keeps everything that stays. Each line below is the whole difference, installed, to replace that item instead. Pick any, or all.</p>')
                w(_options_table(b["p"], b["opts"]).replace("<h3>Options</h3><p>Each line is the whole difference, installed, against the price above.</p>", ""))
    # the pictures
    w('<h2 class="kicker pb" id="g-pictures">The pictures <span class="tag">3D model · design intent</span></h2>')
    for b in built:
        w(f'<h3>{E(b["title"])}</h3>')
        w(_gallery(b["key"], ["corner", "ondeck", "iso", "underiso"], b["have"]))
        w(_gallery(b["key"], ["exploded", "exploded-corner"], b["have"]))
    # investment
    w('<h2 class="kicker pb" id="g-investment">Investment</h2><div class="quote">')
    rows = [[E(b["title"]), money(b["p"].sell), money(b["p"].retail), money(b["p"].monthly)] for b in built]
    w('<div class="tw"><table class="bigtab"><thead><tr><th>Deck</th><th class="num">Check or ACH</th><th class="num">Financed</th><th class="num">Monthly</th></tr></thead><tbody>'
      + "".join(f"<tr><td>{r_[0]}</td><td class='num'>{r_[1]}</td><td class='num'>{r_[2]}</td><td class='num'>{r_[3]}</td></tr>" for r_ in rows)
      + f"<tr class='total'><td>Both decks</td><td class='num'>{money(sell)}</td><td class='num'>{money(retail)}</td><td class='num'>{money(monthly)}</td></tr></tbody></table></div>")
    w('<p>Financed: no money down, 12 or 18 months with no payments, then 6.99% for 10 years. Check or ACH saves 7%. Each deck can be done on its own at its own price.</p>')
    for b in built:
        if b["opts"]:
            w(f'<h3>{E(b["title"])} — choices</h3>' + _options_table(b["p"], b["opts"]).replace("<h3>Options</h3>", ""))
    qmd0 = built[0]["qmd"]
    eng = re.search(r"\*\*Engineering — .*?\n", qmd0)
    if eng:
        w(md_to_html(eng.group(0)))
    w(md_to_html(qmd0[qmd0.index("## NEXT STEP"):]))
    w("</div>")
    w('<h2 class="kicker" id="g-3d">3D models <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>')
    for b in built:
        w(f'<h3>{E(b["title"])}</h3>')
        w(viewer_html(b["S"], None, title=f"{b['title']} — 3D", standalone=False, uid=f"v3d-{b['key']}"))
    w("</section>")
    section = "".join(o)
    who = "Prepared for the owner" + (f" · {addr}" if addr else "") + f" · {today}"
    have0 = built[hero_from]["have"]
    head = (f'<header class="cover"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · Proposal</div><h1>{E(name)}</h1><p class="who">{E(who)}</p>'
            f'<div class="pricebar"><div><span class="l">Both decks · check or ACH</span><span class="v">{money(sell)}</span></div><div><span class="l">Financed</span><span class="v">{money(retail)}</span><span class="s">no money down</span></div>'
            f'<div><span class="l">Monthly</span><span class="v">{money(monthly)}</span><span class="s">6.99% · 10 years</span></div></div>'
            + (f'<img class="herofig" src="r/{hk}-{hero}.jpg" alt="rendering">' if hero in have0 else "")
            + (f'<p class="lede">{E(lede)}</p>' if lede else "") + "</div></header>")
    body = head + '<main class="wrap">' + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Renders and drawings are design intent; dimensions on the sheets govern. Numbers hold 30 days.</span></footer></main>'
    title = f"{name} — Proposal"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>{FONT}{CSS}{EXTRA_CSS}</head><body>"
            + body + CDN + "<script>window.addEventListener('load', function(){ window.dispatchEvent(new Event('resize')); });</script></body></html>\n")
    page = page.replace(CDN, "", 1)
    scripts = re.findall(r"<script>\n\(function\(\)\{\nconst D = .*?\n\}\)\(\);\n</script>", page, flags=re.S)
    for sc in scripts:
        page = page.replace(sc, "", 1)
    page = page.replace(CDN, CDN + "\n" + "\n".join(scripts) + "\n", 1)
    txt = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    for bad in ("internal", "INTERNAL", "owner-directed", "rate card", "cost stack", "GM"):
        assert bad not in txt, f"customer page carries internal wording: {bad}"
    (out / "page.html").write_text(page)
    json.dump(files, open(out / "files.json", "w"), indent=1)
    result = dict(html=str(out / "page.html"), files=files, sell=sell, retail=retail, monthly=monthly)
    if pdf:
        result["pdf"] = render_pdf(page, files, str(out / "page.pdf"), hk, hero="isolow" if "isolow" in have0 else hero)
    return result


# ================================================================== permit set: the drawing sheets only, no money anywhere
PERMIT_CSS = """<style>
.sheet-page{margin:0 0 28px;} .sheet-page svg{width:100%;height:auto;display:block;border:1px solid var(--line);background:#fff;}
.index{columns:2;column-gap:28px;font-size:14px;} .index li{break-inside:avoid;}
@media print{@page{size:Letter landscape;margin:0.3in;} .band{padding:0.35in 0.5in;} .wrap{padding:0 0.2in;} .sheet-page{break-after:page;page-break-after:always;margin:0;} .sheet-page svg{border:0;max-height:7.6in;}
  .cover-list{break-after:page;page-break-after:always;} h2.kicker{margin-top:10px;} figure{break-inside:avoid;} .gal{gap:8px;}}
</style>"""


def _unbrand(html_: str) -> str:
    """A plain set: no company name, no person, no phone — the drawings, colors and dates stay."""
    for pat in (r"GS Exterior Experts · Deck Division · Jade Pender 303-550-9558", r"GS Exterior Experts · Deck Division · ", r" · GS Exterior Experts · Deck Division",
                r"GSX · Jade Pender 303-550-9558 · ", r"GS Exterior Experts · ", r"GS Exterior Experts", r"Jade Pender 303-550-9558 · ", r"Jade Pender 303-550-9558",
                r"Jade Pender", r"303-550-9558", r"GSX · ", r", provided by GSX", r" by GSX", r"GSX "):
        html_ = re.sub(pat, "", html_)
    return html_


def _no_engineering(html_: str) -> str:
    """A set with no engineering wording: the footers, the G-001 row and the callouts that defer to an engineer go."""
    for pat, rep in ((r"Design intent\. The stamped engineering set governs structure, dimensions and locations\. ", ""),
                     (r"Design intent; the stamped engineering set governs\.", ""),
                     (r" · the engineer of record&#x27;s details govern", ""), (r" · the engineer of record's details govern", ""),
                     (r" · the stamped set governs", ""), (r" ?\(engineered\)", ""), (r" · engineered", ""), (r", engineered", ""),
                     (r" · the engineer&#x27;s uplift hold-down governs", ""), (r" · the engineer's uplift hold-down governs", ""),
                     (r" — over L/4: engineer", ""), (r" — engineer\)", ")"), (r" \(engineer\)", ""),
                     (r'<text[^>]*>Engineering</text><text[^>]*>[^<]*</text>', "")):
        html_ = re.sub(pat, rep, html_)
    return html_


def render_permit_set(parts: list, out_dir: str, key: str, name: str, sub: str = "", pdf: bool = False, date_line: Optional[str] = None,
                      renders: Optional[dict] = None, unbranded: bool = False, no_engineering: bool = False) -> dict:
    """parts = [dict(spec, title)]. Sheets G · S · A · D for every part, one sheet per landscape page, then a few 3D views for the
    reviewer. Nothing financial: no prices, no quote, no stack. renders = {title: [(caption, jpg path), ...]} (optional)."""
    from . import run
    from .buildset import build_set
    from datetime import date
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    today = date_line or date.today().strftime("%B %d, %Y")
    spec0 = parts[0]["spec"]
    addr = ", ".join(x for x in (spec0.site.address, spec0.site.city, f"{spec0.site.state} {spec0.site.zip}".strip()) if x)
    files: Dict[str, str] = {}
    o = []; w = o.append
    index = []
    sheet_html = []
    for pi, pt in enumerate(parts):
        t, flags, p = run(pt["spec"])
        r = build_set(t, flags, str(out / f"buildset-{pi + 1}"), render=False, customer=True)   # no internal flags block on G-001
        for num, ttl, svg in r["sheets"]:
            svg = re.sub(r"GS Exterior Experts · ([A-Z][a-z]+ \d{1,2}, \d{4}) · Rev 0", r"GSX · Jade Pender 303-550-9558 · \1 · Rev 0 · PERMIT SET", svg)
            svg = re.sub(r"<text[^>]*>(?:T-400|T-700)</text>\s*<text[^>]*>[^<]*</text>", "", svg)   # the build-set and takeoff sheets are not in a permit set
            index.append((pt["title"], num, ttl))
            sheet_html.append(f'<div class="sheet-page" id="s-{pi + 1}-{num}"><h3>{E(pt["title"])} · {num} · {E(ttl)}</h3>{svg}</div>')
    w(f'<section class="job" id="job-{key}">')
    w('<div class="cover-list"><h2 class="kicker" id="g-index">Sheet index</h2><ol class="index">' + "".join(f"<li>{E(a)} · <b>{b}</b> {E(c)}</li>" for a, b, c in index) + "</ol>")
    eng_any = any(pt_["spec"].extras.engineered for pt_ in parts) and not no_engineering
    w('<p>' + ("Design intent. The stamped engineering set governs structure, dimensions and locations. " if eng_any else "Design intent per the 2021 IRC R507 prescriptive provisions. ")
      + 'Field verify. Do not scale. This set carries no pricing.</p></div>')
    w("".join(sheet_html))
    if renders:
        w('<h2 class="kicker" id="g-views">3D views <span class="tag">design intent</span></h2>')
        for gi, (ttl, items) in enumerate(renders.items()):
            w(f"<h3>{E(ttl)}</h3><div class=\"gal\">")
            for cap, path in items:
                fn = f"r/{key}-{Path(path).stem}.jpg" if len(renders) == 1 else f"r/{key}{gi + 1}-{Path(path).stem}.jpg"   # one file per deck
                files[fn] = str(Path(path).resolve())
                w(f'<figure><img src="{fn}" alt="{E(cap)}" loading="lazy"><figcaption>{E(cap)}</figcaption></figure>')
            w("</div>")
    w("</section>")
    head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · permit set</div><h1>{E(name)}</h1>'
            f'<p>{E(sub or addr)} · {E(today)}</p></div></header>')
    body = head + '<main class="wrap">' + "".join(o) + '<footer><span>GS Exterior Experts · Deck Division · Jade Pender 303-550-9558</span><span>Permit set — drawings only. ' + ("Design intent; the stamped engineering set governs." if eng_any else "Design intent; 2021 IRC R507 prescriptive.") + '</span></footer></main>'
    title = f"{name} — Permit Set"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>{FONT}{CSS}{PERMIT_CSS}</head><body>"
            + body + "</body></html>\n")
    if unbranded:
        page = _unbrand(page)
        page = page.replace('<span>Permit set — drawings only.', '<span>Permit set — drawings only.').replace("<footer><span></span>", "<footer><span>Permit set</span>")
    if no_engineering:
        page = _no_engineering(page)
    txt = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    if no_engineering:
        left = re.findall(r"[^<>]{0,60}(?:ngineer|stamped|Stamped|PE required)[^<>]{0,60}", re.sub(r"<style.*?</style>", "", txt, flags=re.S))
        assert not left, f"engineering wording left: {left[:3]}"
    for bad in ("$", "financ", "Check or ACH", "gross profit", "rate card"):
        assert bad not in txt, f"permit set carries money wording: {bad}"
    if unbranded:
        for bad in ("GS Exterior", "GSX", "Jade", "303-550"):
            assert bad not in re.sub(r"<style.*?</style>", "", txt, flags=re.S), f"unbranded permit set still names: {bad}"
    (out / "page.html").write_text(page)
    json.dump(files, open(out / "files.json", "w"), indent=1)
    result = dict(html=str(out / "page.html"), files=files, sheets=len(index))
    if pdf:
        from .render import _chromium
        from playwright.sync_api import sync_playwright
        for k, v in files.items():
            (out / k).parent.mkdir(parents=True, exist_ok=True); shutil.copy(v, out / k)
        (out / "_print.html").write_text(page.replace(' loading="lazy"', ""))
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
            pg = b.new_page(viewport={"width": 1400, "height": 1000})
            pg.goto("file://" + str(out / "_print.html")); pg.wait_for_timeout(2000)
            pg.emulate_media(media="print")
            pg.pdf(path=str(out / "page.pdf"), format="Letter", landscape=True, print_background=True, prefer_css_page_size=True)
            b.close()
        result["pdf"] = str(out / "page.pdf")
    return result
