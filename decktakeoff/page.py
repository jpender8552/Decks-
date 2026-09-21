"""The GSX job page — one template for every job, two audiences.

    internal: the takeoff + build set page (Eagle's Nest layout): reads, flags, the order, schedule, stack, quote, renders,
              isometrics, drawings, build set, live 3D.
    customer: the proposal: black cover with the hero render and the price, then reads, what it is, renders, isometrics,
              explosions, structure, drawings (no internal block), materials without prices, fastening, build steps,
              investment, live 3D. Nothing internal, no names.

render_page(spec, out_dir, mode) writes page.html + files.json (the render files the page references as r/<key>-<still>.jpg)
and, with pdf=True, page.pdf (a print version: cover locked to one page, sheets expanded, the 3D swapped for a still).
"""
import html, json, re, shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .spec import DeckSpec
from .report import quote_markdown
from .units import ftin
from .takeoff import CATEGORIES

E = html.escape
CDN = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
FONT = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,300;6..12,400;6..12,600;6..12,700;6..12,800;6..12,900&display=swap">'
CAP = {"yard": "From the yard", "corner": "From the front corner", "ondeck": "Standing on the deck", "under": "Under the deck — posts, beams, footings",
       "iso": "Isometric from the stair corner", "iso2": "Isometric from the open corner", "isolow": "Low isometric", "underiso": "Isometric from under the frame",
       "exploded": "Exploded — every layer", "exploded2": "Exploded — from the open corner", "exploded-corner": "Exploded — from the front corner", "exploded-low": "Exploded — low angle",
       "frame-iso2": "Frame only — joists, rims, beams, ledger", "rail-iso2": "Through the rail", "structure-underiso": "Posts and beams on the footings", "plan": "Plan from above"}


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


def _stack(p):
    out = ['<h2 class="kicker">The stack <span class="tag">internal</span></h2>']
    stack = [("Materials (raw)", money(p.materials, True)), (f"Materials × {p.material_factor:g}", money(p.materials_factored, True)),
             (f"Sales tax {p.tax_rate:.2%}" + (" on factored materials" if p.material_factor != 1 else ""), money(p.tax, True)), ("Labor (rate card)", money(p.labor, True)),
             ("Work — carries the margin", money(p.work, True)), ("General conditions at cost", money(p.gc, True)), ("Cost", money(p.cost, True)),
             (f"Sell — check or ACH at {p.gm:.1%} GM", f"<b>{money(p.sell)}</b> · {money(p.sell_per_sf, True)}/SF"), ("Sell at the 40% floor", money(p.sell_floor)),
             ("Financed", f"<b>{money(p.retail)}</b> · {money(p.monthly)}/mo at 6.99% × 10 yr"), ("Gross profit", money(p.gp))]
    if p.engineering:
        stack.append(("Engineering — outside the price, at cost", f"{money(p.engineering[0])}–{money(p.engineering[1])}"))
    out.append('<div class="tw"><table class="ledger"><tbody>' + "".join(f"<tr><td>{k}</td><td class='num'>{v}</td></tr>" for k, v in stack) + "</tbody></table></div>")
    out.append("<h3>Labor</h3>")
    out.append(table(["Line", "Qty", "Unit", "Rate", "Ext"], [[E(i), qfmt(q), E(u), money(r, True), money(e, True)] for i, q, u, r, e in p.labor_lines], "", ["l", "r", "l", "r", "r"]))
    if p.gc_lines:
        out.append("<h3>General conditions — at cost, no margin</h3>")
        out.append(table(["Item", "Amount", "Why"], [[E(i), money(a), E(why)] for i, a, why in p.gc_lines], "", ["l", "r", "l"]))
    out.append("<h3>What the price includes — sell values</h3>")
    out.append(table(["Item", "Value"], [[E(k), money(v)] for k, v in p.allocation] + [["<b>Total, check or ACH</b>", f"<b>{money(p.sell)}</b>"], ["<b>Total, financed</b>", f"<b>{money(p.retail)}</b>"]], "", ["l", "r"]))
    if p.options:
        out.append("<h3>Options — full installed deltas</h3>")
        out.append(table(["Option", "Cost Δ", "Check / ACH", "Financed"], [[E(o.name), f"{o.cost:+,.0f}", f"{o.check:+,.0f}", f"{o.financed:+,.0f}"] for o in p.options], "", ["l", "r", "r", "r"]))
    return "".join(out)


def _gallery(key, names, have):
    return '<div class="gal">' + "".join(f'<figure><img src="r/{key}-{n}.jpg" alt="{E(CAP.get(n, n))}" loading="lazy"><figcaption>{E(CAP.get(n, n))}</figcaption></figure>' for n in names if n in have) + "</div>"


def _steps(key, steps, cap, customer):
    out = []
    for st in steps:
        title = f"Step {st['n']} · {E(st['title'])}" if customer else f"{st['code']} · Step {st['n']} · {E(st['title'])}"
        out.append(f'<div class="step"><figure><img src="r/{key}-{st["still"]}.jpg" alt="step {st["n"]}" loading="lazy"><figcaption>{E(cap[st["still"]])}</figcaption></figure>'
                   f'<div><h3>{title}</h3><h4>Goes in</h4><ul>' + "".join(f"<li>{E(g)}</li>" for g in st["goes_in"]) + "</ul>"
                   + '<h4>How</h4><ul>' + "".join(f"<li>{E(h)}</li>" for h in st["how"] if h) + "</ul><h4>Check</h4><ul>" + "".join(f"<li>{E(c)}</li>" for c in st["check"]) + "</ul></div></div>")
    return "".join(out)


def _reads_lite(t, L, sm):
    """The homeowner's at-a-glance: what it is, not how it is framed."""
    s = t.spec
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
        rail = f"{s.decking.brand} {rl.system} {rl.color}, {rl.height:g}\" · {rl.rail_lf:g} LF"
    else:
        rail = "None"
    stairs = []
    for st, ss in zip(L.stairs, s.stairs):
        g = st.geo
        txt = f"{g.risers} risers at {g.riser_in:.1f}\", {ftin(st.width)} wide"
        if len(g.flights) > 1:
            lands = " and ".join(f"{ftin(a)} x {ftin(b)}" for a, b in ss.landings) if ss.landings else "a landing"
            turn = {"switchback": "turn back", "left": "turn left", "right": "turn right", "straight": "continue"}.get(ss.turn, ss.turn)
            txt += ": " + " then ".join(f"{fg.risers} down" for fg in g.flights[:1]) + f" to the {lands} landing, {turn}, " + " then ".join(f"{fg.risers} down" for fg in g.flights[1:]) + " to the lower level"
            if st.landing_rail_lf:
                txt += f" · guard rail on the landings"
        stairs.append(txt)
    fr = L.zones[0].frame
    beams = sorted({b.size for b in s.framing.beams}) if s.framing.beams else []
    structure = f"{s.framing.joist_size} {'pressure-treated' if not s.is_timber else 'Douglas fir'} frame at {fr.spacing:g}\" on centre" + (f", {' / '.join(beams)} Douglas fir beams" if beams else "") + f"; {sm['posts']}"
    reads = [("Deck", deck), ("Decking", decking), ("Rail", rail)] + [("Stair", x) for x in stairs] + [("Structure", structure), ("Design load", sm["design_load"].replace(" · engineered", ", stamped by a Colorado engineer"))]
    return '<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in reads) + "</dl>"


def _options_table(p, options):
    """Full installed deltas against this proposal: [(label, other pricing)]."""
    if not options:
        return ""
    def d(v):
        return ("+" if v >= 0 else "−") + money(abs(v))
    rows = [[E(lab), d(q.sell - p.sell), d(q.retail - p.retail), d(q.monthly - p.monthly) + "/mo"] for lab, q in options]
    return ('<h3>Options</h3><p>Each line is the whole difference, installed, against the price above.</p>'
            + table(["Option", "Check or ACH", "Financed", "Monthly"], rows, "", ["l", "r", "r", "r"]))


def render_page(spec: DeckSpec, out_dir: str, mode: str = "internal", key: str = "job", name: Optional[str] = None, sub: str = "",
                lede: str = "", hero: str = "corner", render: bool = True, renders_dir: Optional[str] = None, pdf: bool = False,
                date_line: Optional[str] = None, options: Optional[list] = None) -> dict:
    """Build the page. mode = "internal" | "customer" | "proposal" (the customer page without the sheets, schedules and
    step-by-step: cover, at a glance, what it is, renders, isometrics, exploded views, under the deck, investment with
    options, 3D). options = [(label, DeckSpec)] priced as full installed deltas. Returns {"html", "files", "pdf"?, "pricing", "takeoff"}."""
    from . import run
    from .buildset import build_set
    from .viewer import viewer_html
    from datetime import date
    proposal = mode == "proposal"
    customer = mode == "customer" or proposal
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    t, flags, p = run(spec)
    L, sm = t.layout, t.summary
    r = build_set(t, flags, str(out / "buildset"), render=render, customer=customer)
    S = r["scene"]
    rd = Path(renders_dir) if renders_dir else (out / "buildset" / "renders")
    files = {f"r/{key}-{q.stem}.jpg": str(q) for q in rd.glob("*.jpg")}
    have = {q.stem for q in rd.glob("*.jpg")}
    cap = dict(CAP); cap.update({f"step{n}": S.meta["step_text"][n] for n in range(1, 9)})
    name = name or spec.job
    addr = ", ".join(x for x in (spec.site.address, spec.site.city, f"{spec.site.state} {spec.site.zip}".strip()) if x)
    n_piers = int(sum(l.order for l in t.lines if "diamond pier" in l.item.lower())) or L.n_footings
    today = date_line or date.today().strftime("%B %d, %Y")
    qmd = quote_markdown(t, p)
    o = []
    w = o.append
    w(f'<section class="job" id="job-{key}" data-job="{key}">')
    if proposal:
        opts = [(lab, run(sp_)[2]) for lab, sp_ in (options or [])]
        w('<h2 class="kicker" id="g-reads">At a glance</h2>')
        w(_gallery(key, ["yard", "iso2"], have))
        w(_reads_lite(t, L, sm))
        w('<h2 class="kicker" id="g-what">What it is <span class="tag">included in the price</span></h2>')
        inc = qmd[qmd.index("## INCLUDED"):qmd.index("## PLAN")].replace("## INCLUDED — what it is\n", "")
        beams = sorted({b.size for b in spec.framing.beams}) if spec.framing.beams else []
        frame_lite = f"{sm['joists']}; {sm['rims']}" + (f"; {' / '.join(beams)} Douglas fir beams" if beams else "") + "."
        inc = re.sub(r"\| Frame \| .*? \|\n", f"| Frame | {frame_lite} |\n", inc, count=1)
        w(md_to_html(inc))
        w('<h2 class="kicker pb" id="g-renders">Renders <span class="tag">3D model · design intent</span></h2>')
        w(_gallery(key, ["corner", "ondeck", "isolow", "under"], have))
        w('<h2 class="kicker pb" id="g-iso">Isometrics <span class="tag">the model from four corners</span></h2>')
        w(_gallery(key, ["iso", "iso2", "underiso", "plan"], have))
        w('<h2 class="kicker pb" id="g-exploded">Exploded views <span class="tag">every layer pulled apart</span></h2>')
        w(_gallery(key, ["exploded", "exploded2", "exploded-corner", "exploded-low"], have))
        w('<h2 class="kicker pb" id="g-structure">Under the deck <span class="tag">footings, posts, beams, frame</span></h2>')
        w(_gallery(key, ["structure-underiso", "frame-iso2"], have))
        w('<h2 class="kicker pb" id="g-investment">Investment</h2>')
        q2 = qmd[qmd.index("## PRICE"):qmd.index("## INCLUDED")]
        w('<div class="quote">' + md_to_html(q2) + _options_table(p, opts) + md_to_html(qmd[qmd.index("## NEXT STEP"):]) + "</div>")
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
        w(_gallery(key, ["corner", "ondeck", "under", "isolow"], have))
        w('<h2 class="kicker pb" id="g-iso">Isometrics <span class="tag">the model from four corners</span></h2>')
        w(_gallery(key, ["iso", "iso2", "isolow", "underiso"], have))
        w('<h2 class="kicker pb" id="g-exploded">Exploded views <span class="tag">every layer pulled apart</span></h2>')
        w(_gallery(key, ["exploded", "exploded2", "exploded-corner", "exploded-low"], have))
        w('<h2 class="kicker pb" id="g-structure">Structure <span class="tag">footings, posts, beams, frame, rail</span></h2>')
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
        w(_stack(p))
        w('<h2 class="kicker">The quote <span class="tag">homeowner-facing · facts only</span></h2>')
        w('<div class="quote">' + md_to_html(qmd) + "</div>")
        w('<h2 class="kicker">Renders <span class="tag">3D model · design intent · timbers shown ' + ("with the optional oil finish" if S.meta["timber"] and not S.meta["oiled"] else "as specified") + "</span></h2>")
        w(_gallery(key, ["yard", "corner", "ondeck", "under"], have))
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
    if customer:
        who = ("Prepared for " + spec.client if spec.client else "Prepared for the owner") + (f" · {addr}" if addr else "") + f" · {today}"
        head = (f'<header class="cover"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · Proposal</div><h1>{E(name)}</h1><p class="who">{E(who)}</p>'
                f'<div class="pricebar"><div><span class="l">Check or ACH</span><span class="v">{money(p.sell)}</span></div><div><span class="l">Financed</span><span class="v">{money(p.retail)}</span><span class="s">no money down</span></div>'
                f'<div><span class="l">Monthly</span><span class="v">{money(p.monthly)}</span><span class="s">6.99% · 10 years</span></div></div>'
                + (f'<img class="herofig" src="r/{key}-{hero}.jpg" alt="rendering">' if hero in have else "")
                + (f'<p class="lede">{E(lede)}</p>' if lede else "") + "</div></header>")
        body = head + '<main class="wrap">' + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Renders and drawings are design intent; dimensions on the sheets govern. Numbers hold 30 days.</span></footer></main>'
        title = f"{name} — Proposal"
    else:
        head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · takeoff + build set</div><h1>{E(name)}</h1>'
                f'<p>{E(sub or addr)}</p></div></header>')
        body = head + '<main class="wrap">' + strip + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Prices: rate card · GC at cost · 42.5% GM · financed ÷ 0.93 unless the job says otherwise. Internal — not for the homeowner.</span></footer></main>'
        title = f"{name} — Takeoff + Build Set"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>{FONT}{CSS}</head><body>"
            + body + CDN + "<script>window.addEventListener('load', function(){ window.dispatchEvent(new Event('resize')); });</script></body></html>\n")
    # the viewer inlines its own CDN tag: keep one, hoist the viewer script after it
    page = page.replace(CDN, "", 1)
    scripts = re.findall(r"<script>\n\(function\(\)\{\nconst D = .*?\n\}\)\(\);\n</script>", page, flags=re.S)
    for sc in scripts:
        page = page.replace(sc, "", 1)
    page = page.replace(CDN, CDN + "\n" + "\n".join(scripts) + "\n", 1)
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
    p = p.replace("<details", "<details open").replace("</head>", PRINT_CSS + "</head>")
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
        frame_lite = f"{b['sm']['joists']}; {b['sm']['rims']}" + (f"; {' / '.join(beams)} Douglas fir beams" if beams else "") + "."
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
