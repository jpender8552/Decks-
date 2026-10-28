"""The GSX job page — one template for every job, two audiences.

    internal: the takeoff + build set page (Eagle's Nest layout): reads, flags, the order, schedule, cut list, renders,
              isometrics, drawings, build set, live 3D. No pricing: the cost stack (mode="cost") is its own one or two pages.
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
from .report import quote_markdown, timeline_of, engine_timeline, payment_schedule, materials_rows, client_allocation, price_holds_through
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
CLIENT_FOOT = "Renders show the design. We confirm every measurement on site before we build, and sample boards set the colors."   # the client documents' fine print


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
h2.kicker:has(+ .quote){break-before:page;page-break-before:always;} h2.kicker + .quote{break-before:auto;page-break-before:auto;}
.gal{display:block;} .gal figure{display:inline-block;width:calc(50% - 6px);vertical-align:top;margin:0 0 10px;} .gal figure:nth-child(odd){margin-right:8px;}
h2.pb{break-before:page;page-break-before:always;} footer{padding-bottom:0.4in;} .strip{break-inside:avoid;}
@page sheet{size:Letter landscape;margin:0.3in 0.2in;}
.sheets{page:sheet;} h2.kicker:has(+ .sheets){page:sheet;} .sheets .sheet{break-before:page;page-break-before:always;margin:0;border:0;}
.sheets .sheet:first-child{break-before:auto;page-break-before:auto;} .sheets .sheet svg{width:100%;height:auto;max-height:7.3in;display:block;}
</style>"""

# the internal documents (takeoff + build set, the supplier take-off, the cost stack: <body class="doc">): page margins with a
# running footer (named pages, so the proposal's full-bleed pages keep theirs), headings kept with what follows, short tables
# and blocks whole, at least 3 rows either side of a split, one column grid down the order, no disclosure markers
DOC_CSS = """<style>
.strip.n4 { grid-template-columns:repeat(4, 1fr); } body.doc h1 .nw { white-space:nowrap; } body.doc .band h1.long { font-size:clamp(22px, 4vw, 30px); }
@media (max-width: 640px) { .strip.n4 { grid-template-columns:repeat(2, 1fr); } body.doc h1 .nw { white-space:normal; } }
@media print {
  body.doc { --ink-3:#6b665e; } body.doc .sev-info .sev { background:#7a7366; }      /* small gray type and the INFO badge at 4.5:1 or better */
  body.doc > header.band, body.doc > main.wrap { page:doc; }
  body.doc .sheets, body.doc h2.kicker:has(+ .sheets) { page:docsheet; }
  body.doc .sheets summary { display:none; } body.doc .sheets .sheet svg { max-height:7.05in; margin:0 auto; }
  body.doc summary { list-style:none; font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--gold-ink); font-weight:800; margin:18px 0 6px; }
  body.doc summary::-webkit-details-marker { display:none; }
  body.doc h2.kicker, body.doc h3, body.doc h4, body.doc summary { break-after:avoid; page-break-after:avoid; }
  body.doc .keep, body.doc .strip, body.doc .gal { break-inside:avoid; page-break-inside:avoid; }
  body.doc tbody tr:nth-child(-n+2):not(:last-child), body.doc dl.reads > div:nth-child(-n+2):not(:last-child), body.doc .flags li:nth-child(-n+2):not(:last-child),
  body.doc .notes li:nth-child(-n+2):not(:last-child), body.doc .step li:first-child:not(:last-child) { break-after:avoid; page-break-after:avoid; }
  body.doc tbody tr:nth-last-child(-n+2):not(:first-child), body.doc dl.reads > div:nth-last-child(-n+2):not(:first-child), body.doc .flags li:nth-last-child(-n+2):not(:first-child),
  body.doc .notes li:nth-last-child(-n+2):not(:first-child), body.doc .step li:last-child:not(:first-child) { break-before:avoid; page-break-before:avoid; }
  body.doc dl.reads { display:block; } body.doc dl.reads > div { display:grid; grid-template-columns:96px 1fr; gap:0 14px; margin:0 0 6px; break-inside:avoid; }
  body.doc .flags { display:block; } body.doc .flags li { break-inside:avoid; } body.doc .notes li { break-inside:avoid; }
  body.doc table.netorder { table-layout:fixed; } body.doc table.netorder th:nth-child(1) { width:7%; } body.doc table.netorder th:nth-child(2) { width:8%; }
  body.doc table.netorder th:nth-child(3) { width:7%; } body.doc table.netorder th:nth-child(4) { width:40%; } body.doc table.netorder td { overflow-wrap:anywhere; }
  body.doc .step { border-bottom:0; padding-bottom:0; margin-bottom:22px; grid-template-columns:0.82fr 1.18fr; gap:14px; }
  body.doc .step ul { font-size:11.5px; line-height:1.36; } body.doc .step li { margin:1px 0; } body.doc .step h4 { margin:6px 0 1px; }
  body.doc footer { margin-top:18px; padding-bottom:0; break-inside:avoid; } body.doc main.wrap { padding-bottom:0; }
}
</style>"""


def _foot(name: str, n: int = 64) -> str:
    """A running footer's job name: no parenthetical, cut at a clean break (", ", " · ", " — ") within n characters."""
    j = re.sub(r"\s*\([^)]*\)", "", name or "").strip()
    while len(j) > n:
        cut = max(j.rfind(", ", 0, n), j.rfind(" · ", 0, n), j.rfind(" — ", 0, n))
        if cut <= 0:
            return j[:n - 1].rstrip() + "…"
        j = j[:cut]
    return j


def _page_box(sel: str, size: str, margin: str, left: str, pad: str, bg: str = "#f7f3ea", important: bool = True) -> str:
    """One @page rule with the running footer: the job and the document on the left, "page n of N" on the right. Size and
    margin are !important for render_page's documents (render_pdf adds PRINT_CSS's generic @page, margin 0, after these and
    Chromium lets it win); important=False where a wrapper's later @page must win (render_permit_set: messner_ext's sheet size)."""
    q = '"' + left.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
    imp = " !important" if important else ""
    box = "font-family:'Nunito Sans','Segoe UI',system-ui,sans-serif; font-size:7.5pt; font-weight:600; color:#6b665e; letter-spacing:.03em; vertical-align:middle;"
    return (f'@page {sel} {{ size:{size}{imp}; margin:{margin}{imp}; background:{bg}; @bottom-left {{ content:{q}; {box} padding-left:{pad}; }} '
            f'@bottom-right {{ content:"page " counter(page) " of " counter(pages); {box} padding-right:{pad}; white-space:nowrap; }} }}')


def _doc_page_css(left: str) -> str:
    """The internal documents' pages: Letter portrait with 0.5 in top and 0.6 in bottom margins (the first page's band runs to
    the top edge), the drawing sheets on Letter landscape, cream to the paper edge, the running footer on every page."""
    return ("<style>@media print { " + _page_box("doc", "Letter", "0.5in 0 0.6in", left, "0.5in") + " @page doc:first { margin-top:0 !important; } "
            + _page_box("docsheet", "Letter landscape", "0.4in 0.3in 0.55in", left, "0") + " }</style>")


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


def _part_no(sku: str) -> bool:
    """A maker's or the yard's part number (AZTDL3X3LEDCAP, CLOCFAST, LUS210Z), not one of the pricebook's own keys (lv_staples_100)."""
    return bool(re.fullmatch(r"[A-Z0-9][A-Z0-9./-]{2,}", sku or ""))


def _order_internal(t):
    out = []
    if t.order_ref:
        out.append('<h2 class="kicker">The order <span class="tag">' + E(t.order_ref) + " · as quoted</span></h2>")
        for cat, lines in t.by_category().items():           # quantities only: the prices live in the cost stack
            out.append(f"<h3>{E(cat)}</h3>")
            out.append(table(["SKU", "Qty", "Unit", "Item"], [[E(l.sku), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item)] for l in lines], "order", ["l", "r", "l", "l"]))
        if t.model_lines:
            out.append('<details><summary>Model cross-check — what the engine counts from the drawing (the order above governs)</summary>')
            by = {}
            for l in t.model_lines:
                by.setdefault(l.category, []).append(l)
            for cat in CATEGORIES:
                if cat in by:
                    out.append(f"<h3>{E(cat)}</h3>")
                    out.append(table(["NET", "ORDER", "Unit", "Item", "Why"], [[qfmt(l.net), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item), E(l.why)] for l in by[cat]], "order netorder", ["r", "r", "l", "l", "l"]))
            out.append("</details>")
    else:
        out.append('<h2 class="kicker">The order <span class="tag">Decks &amp; Docks · GSEXT1 · ship to the job</span></h2>')
        for cat, lines in t.by_category().items():
            out.append(f"<h3>{E(cat)}</h3>")
            out.append(table(["NET", "ORDER", "Unit", "Item", "Why"], [[qfmt(l.net), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item), E(l.why)] for l in lines], "order netorder", ["r", "r", "l", "l", "l"]))
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


def _m(v, cents=False) -> str:
    """Money with a true minus sign ahead of the dollar sign: −$820.60, never $-820.60."""
    return ("−" if round(v, 2 if cents else 0) < 0 else "") + money(abs(v), cents)


def _pct(v) -> str:
    """A margin the way the owner says it: 30%, 42.5%, 28.4% (a loss with a true minus sign)."""
    s_ = f"{100 * v:.1f}".replace("-", "−")
    return (s_[:-2] if s_.endswith(".0") else s_) + "%"


def _mw(v) -> str:
    """An amount the owner set, as he set it: $1,000 whole, $820.60 with its cents."""
    return money(v, round(v, 2) != round(v))


def _h1(name: str) -> str:
    """An internal document's <h1>: it breaks after a " · ", never before the dot, and a short part (24 characters or less, "19105
    E Prentice Cir", "Deck Replacement") stays whole on a page or a wide screen; a long part wraps as text does, and on a phone
    every part wraps (DOC_CSS). A long job line (over 64 characters, the CLI's default name) drops its parenthesis (the
    materials; the <title> keeps the whole name) and sets smaller (h1.long)."""
    n = re.sub(r"\s*\([^()]*\)", "", name or "").strip() if len(name or "") > 64 else (name or "")
    xs = n.split(" · ")
    pt = [E(x) + ("&nbsp;·" if i < len(xs) - 1 else "") for i, x in enumerate(xs)]
    return (('<h1 class="long">' if len(n) > 64 else "<h1>") + " ".join(f'<span class="nw">{v}</span>' if len(x) <= 24 else v for x, v in zip(xs, pt))
            + "</h1>")


_M1 = r"[+−-]?\$\s?\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s?[KkM]\b)?(?:/[A-Za-z]+\b)?"          # $17.8K, $2/SF, -$820.60, $100k
_MONEY = rf"(?:[~≈]\s*)?{_M1}(?:\s*(?:–|-|to)\s*(?:[~≈]\s*)?{_M1})?"                     # with ≈ / ~ ahead, a range
_SRC = r"(?:\s+(?:from|per|on|in) the [^;,()]*?(?:quote|pricebook|price list|invoice)(?: note)?)?"   # where the figure came from
_PRICE_ONLY = {"no", "pricebook", "price", "priced", "key", "quote", "quoted", "note", "from", "per", "the", "d&d", "cost", "at", "each", "ea", "about",
               "approx", "total", "->", "→", "=", "+", "~", "≈", "and", "or", "a", "of", "est", "sell", "budget"}


def _strip_money(s: str) -> str:
    """A flag's words without its dollar figures: "the owner's $15,000" reads "the owner's price", "the card's $2/SF" "the card's
    rate"; any other figure goes with its "at" / "≈" and where it came from ("$193.48 from the D&D quote note"); a clause, or a
    parenthesis, left with nothing but price words ("no pricebook key", "($100k -> ~$3,015)") goes whole. Parentheses stay paired."""
    s = re.sub(rf"\b([Tt]he (?:[\w&]+['’]s |D&D )?){_MONEY}{_SRC}", lambda m: m.group(1) + ("rate" if "/" in m.group(0) else "price"), s)
    s = re.sub(rf"\s*(?:\b(?:at|for|of|about|approx\.?|around)\s+)?{_MONEY}{_SRC}", "\x00", s)

    def bare(c, cut=True):                   # price words only, once the figures are out (outside a parenthesis: one a figure was cut from)
        return (not cut or "\x00" in c) and all(w.strip(".,:;()'\"").lower() in _PRICE_ONLY | {""} for w in c.replace("\x00", " ").split())

    def paren(m):                            # a parenthesis that held a figure keeps only its clauses with words of their own
        parts = [c for c in m.group(2).split(";") if not bare(c, False)]
        return (m.group(1) + "(" + ";".join(parts).strip() + ")") if parts else ""

    def split0(x, sep):                      # split at sep outside any parenthesis
        out, depth, cur = [], 0, ""
        for ch in x:
            depth += (ch == "(") - (ch == ")")
            if ch == sep and depth == 0:
                out.append(cur); cur = ""
            else:
                cur += ch
        return out + [cur]
    for _ in range(3):                       # innermost first
        s = re.sub(r"(\s*)\(([^()]*\x00[^()]*)\)", paren, s)
    s = ";".join(",".join(p for p in split0(c, ",") if not bare(p)) for c in split0(s, ";") if not bare(c))
    s = re.sub(r"\(\s*\x00\s*", "(", s)
    s = re.sub(r"\s*\x00\s*(?=[;,.:)]|$)", "", s)
    s = re.sub(r"\s*\x00\s*", " ", s).replace("$", "")
    s = re.sub(r"[;,:]\s*(?=[;.])", "", s).strip(" ;,:")
    return s[:1].upper() + s[1:] if s else s


def _money_clauses(s: str) -> str:
    """The clauses of a flag that carry a dollar figure (split at ";" and at a sentence's end, outside any parenthesis): the cost
    stack's half of a flag the takeoff prints without its figures."""
    out, depth, cur = [], 0, ""
    for i, ch in enumerate(s or ""):
        depth += (ch == "(") - (ch == ")")
        cur += ch
        if depth == 0 and (ch == ";" or (ch == "." and s[i + 1:i + 2] in ("", " "))):
            out.append(cur); cur = ""
    keep = "; ".join(c.strip(" ;.") for c in out + [cur] if "$" in c)
    return (keep[:1].upper() + keep[1:] + ".") if keep else (s or "")


def _no_money(f):
    """A flag for the takeoff, which carries no pricing: its dollar figures go (_strip_money) and it points to the cost stack,
    which lists the clauses that carry them (_money_clauses). -> (flag, whether it had money)."""
    if "$" not in f.text and "$" not in (f.ref or ""):
        return f, False
    from dataclasses import replace
    keep = _strip_money(f.text)
    keep = (keep + ("" if keep.endswith((".", "!", "?")) else ".") + " ") if keep else ""
    return replace(f, text=keep + "Its cost note is in the cost stack.", ref=_strip_money(f.ref) if "$" in (f.ref or "") else f.ref), True


def _sheet_letters(sheets) -> str:
    """The series in a drawing set, in set order: "G · C · S · A · D"."""
    have = [n[:1] for n, *_ in sheets]
    return " · ".join(dict.fromkeys([c for c in "GCSAD" if c in have] + have))


def _ledger(rows) -> str:
    """A money column: [(label HTML, amount, row class)] — "sub" a subtotal, "big" the price."""
    return ('<div class="tw"><table class="stack keep"><tbody>' + "".join(f'<tr class="{c}"><td>{k}</td><td class="num">{v}</td></tr>' for k, v, c in rows)
            + "</tbody></table></div>")


def _labor_rows(t, p) -> Tuple[str, list, str]:
    """The labor at the rate card, then the owner's change on lines of its own — the card credits he asked for (the under-3'
    credit) and extras.labor_adjust / labor_total spread over the lines above — footing to the labor in the price. A line not at
    the card's own rate is tagged: owner rate, owner-set, estimate, job rate (extras.labor_rates).
    -> (title, rows, footnote). Every Ext is the printed qty x the printed rate."""
    from .pricing import labor_lines_for
    x = t.spec.extras
    card, fin = labor_lines_for(t), p.labor_lines
    std, note_of, rate_of = {}, {c[0]: str(c[4] or "") for c in card}, {c[0]: c[3] for c in card}
    if x.labor_rates:                        # the card's lines without the job's own rates: which lines they changed
        lr_ = x.labor_rates
        try:
            x.labor_rates = {}
            std = {c[0]: c[3] for c in labor_lines_for(t)}
        finally:
            x.labor_rates = lr_

    def line(i):
        n, r = note_of.get(i, ""), rate_of.get(i)
        w_ = ("owner-set" if n.startswith("owner-set") else "owner rate" if n.startswith("owner rate") else "estimate" if re.match(r"(?i)est(imate)?\b", n)
              else "job rate" if std and r is not None and (i not in std or abs(std[i] - r) > 1e-9) else "")
        return E(i) + (f' <span class="cs-tag">{w_}</span>' if w_ else "")
    tail = ["<b>Labor in the price</b>", "", "", "", f"<b>{_m(p.labor, True)}</b>"]
    if len(card) != len(fin) or any(c[0] != f[0] or c[1] != f[1] for c, f in zip(card, fin)):    # not the card's lines: as priced
        return "Labor", [[line(i), qfmt(q), E(u), _m(r, True), _m(e, True)] for i, q, u, r, e in fin] + [tail], ""
    plus, cred = [c for c in card if c[3] >= 0], [c for c in card if c[3] < 0]   # the card's credits apply only on the owner's word
    card_tot = round(sum(round(q * r, 2) for i, q, u, r, n in plus), 2)
    cred_tot = round(sum(round(q * r, 2) for i, q, u, r, n in cred), 2)
    spread = round(p.labor - card_tot - cred_tot, 2)          # labor_adjust / labor_total on the lines above, as applied
    adj, tot = float(x.labor_adjust or 0), x.labor_total
    rows = [[line(i), qfmt(q), E(u), _m(r, True), _m(round(q * r, 2), True)] for i, q, u, r, n in plus]
    if not cred and abs(spread) < 0.005:
        return "Labor — rate card", rows + [tail], ""
    k = next((f[3] / c[3] for c, f in zip(card, fin) if c[3] > 0 and abs(f[3] - c[3]) > 1e-9), 1.0)
    each = ("−" if k < 1 else "+") + f"{abs(k - 1):.1%}"
    cut = -(cred_tot + adj)
    who = f"The owner's {_mw(abs(cut))} {'cut' if cut >= 0 else 'add'}" if tot is None else "The owner's change"
    title = (f"Labor — rate card, scaled to the owner's {_mw(tot)} total" if tot is not None else
             f"Labor — rate card, {'less' if cut >= 0 else 'plus'} the owner's {_mw(abs(cut))} {'cut' if cut >= 0 else 'add'}")
    parts = len(cred) + (abs(spread) >= 0.005)
    rows.append(["<b>Before the owner's change</b>", "", "", "", f"<b>{_m(card_tot, True)}</b>"])
    for j, (i, q, u, r, n) in enumerate(cred, 1):
        rows.append([f"{who}{f', {j} of {parts}' if parts > 1 else ''}: {E(i)}", qfmt(q), E(u), _m(r, True), _m(round(q * r, 2), True)])
    if abs(spread) >= 0.005:
        lots = ", the owner-set lots as set" if any(n.startswith("owner-set") for i, q, u, r, n in plus) else ""
        what = (f"scaled to the owner's {_mw(tot)} total, {each} on each line above{lots}" if tot is not None else
                f"{money(abs(adj), True)} spread over the lines above in proportion, {each} on each{lots}")
        rows.append([f"{who}{f', {parts} of {parts}' if parts > 1 else ''}: {what}", "", "", "", _m(spread, True)])
    note = (f"The spread applies as {_m(spread, True)} against the {_m(adj, True)} set: the engine rounds each scaled rate to 4 places."
            if tot is None and adj and abs(spread - adj) >= 0.005 else "")
    return title, rows + [tail], note


COST_CSS = """<style>
/* the cost stack (mode="cost"): one or two Letter pages — the sell, the stack, how the sell is set, labor, what the price includes */
.cs-hero { display:grid; grid-template-columns:minmax(0, 1.15fr) minmax(0, 1fr); gap:16px 30px; margin-top:16px; align-items:end; }
.cs-hero .l { display:block; font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--gold); font-weight:800; }
.cs-hero .v { display:block; font-size:clamp(46px, 8vw, 66px); font-weight:900; letter-spacing:-.02em; line-height:1; margin:6px 0 8px; color:#fff; }
.cs-hero .v2 { display:block; font-size:26px; font-weight:900; line-height:1.1; margin:3px 0 3px; color:#fff; }
.cs-hero .s { display:block; font-size:12.5px; line-height:1.4; color:#ecddb6; font-weight:400; }
.cs-side { display:grid; gap:14px; }
table.stack td { padding:6px 8px 6px 0; } table.stack td.num { width:9em; }
table.stack tr.sub td { font-weight:800; border-top:1px solid var(--ink-3); }
table.stack tr.big td { font-weight:900; font-size:16px; background:var(--sand); }
.cs-two { display:grid; grid-template-columns:minmax(0, 1fr) minmax(0, 1fr); gap:0 26px; align-items:start; }
.cs-note { color:var(--ink-2); font-size:14px; margin:10px 0 0; max-width:88ch; }
.cs-notes { margin:8px 0 0; padding-left:18px; color:var(--ink-2); font-size:13px; } .cs-notes li { margin:3px 0; }
.cs-tag { margin-left:6px; font-size:.78em; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); white-space:nowrap; }
@media (max-width:640px) { .cs-hero, .cs-two { grid-template-columns:1fr; } }
@media print {
  body.doc.cs .band { padding:0.42in 0.5in 0.3in; } body.doc.cs .band h1 { font-size:30px; } body.doc.cs .band h1.long { font-size:24px; } body.doc.cs .cs-hero .v { font-size:60px; }
  body.doc.cs .kicker { margin:14px 0 6px; } body.doc.cs h3 { margin:10px 0 3px; font-size:13px; }
  body.doc.cs table { font-size:10.5px; line-height:1.3; } body.doc.cs td, body.doc.cs th { padding-top:2px; padding-bottom:2px; }
  body.doc.cs table.stack tr.big td { font-size:12.5px; } body.doc.cs .cs-note { font-size:11.5px; } body.doc.cs .cs-notes { font-size:10.5px; }
  body.doc.cs footer { font-size:9.5px; margin-top:10px; padding-top:6px; } body.doc.cs footer span:first-child { display:none; }   /* the running footer names GSX */
}
</style>"""


def _cost_doc(spec, t, flags, p, out: Path, key: str, name: Optional[str], renders_dir: Optional[str], pdf: bool, date_line: Optional[str],
              options: Optional[list]) -> dict:
    """mode="cost": the cost stack — Jade's one or two pages: the check / ACH sell large, financed and the monthly with the
    terms, gross profit, the stack (materials, x factor, tax, labor, the work, at-cost items, cost, sell), how the sell is set
    (the job margin, what is given free or priced on its own, the blended margin), the labor with the owner's cut in its
    parts, what the price includes, materials by category, the 40% floor. A sold job (extras.sell_override) reads its sold
    price and its cost to build at invoice. No drawings, no build set, no order; every number from the pricing object."""
    from datetime import date
    from .catalog import PRICEBOOK as PB
    L, s, x = t.layout, spec, spec.extras
    name = name or s.job
    today = date_line or date.today().strftime("%B %d, %Y")
    addr = ", ".join(v for v in (s.site.address, s.site.city, f"{s.site.state} {s.site.zip}".strip()) if v)
    sold = bool(x.sell_override)
    gcn = gc_name(p.gc_lines, "General conditions")
    mat_f, tax, lab, gc = round(p.materials_factored, 2), round(p.tax, 2), round(p.labor, 2), round(p.gc, 2)
    work = round(mat_f + tax + lab, 2)                       # the printed lines foot
    cost = round(work + gc, 2)
    gp = p.sell - cost
    gmj = float(getattr(p, "gm_job", p.gm))
    per_sf = float(getattr(p, "per_sf", 0) or 0)
    free = float(p.light_work) if (getattr(p, "light_work", 0) and not getattr(p, "light_sell", 0)) else 0.0     # lights given free
    n_free = int(getattr(getattr(t, "lighting", None), "n_riser", 0) or 0)
    own_w = max(0.0, p.work - p.margin_work - free)          # the rail at its $/LF, built-ins, lights at a set price, the drink rail
    st_w, st_s = float(getattr(p, "stair_work", 0) or 0), float(getattr(p, "stair_sell", 0) or 0)
    base = round(work - free - own_w - st_w, 2)               # the work at the job margin
    at_gm = base / (1 - gmj)
    own_s = p.sell - at_gm - gc - st_s                         # what the parts priced on their own sell for (and the rounding)
    note = re.sub(r"^blended — |,? everything else at [\d.]+% GM", "", p.rail_note or "")
    note = " · ".join(v for v in note.split(" · ") if v and "riser lights free" not in v and not v.startswith("stairs at the owner's rule"))
    many = " · " in note or bool(re.match(r"(\d+) (?!LF\b|SF\b)", note) and int(re.match(r"\d+", note).group()) > 1)    # "14 lights", "2 bench sections"
    quoted_tax = bool(s.quoted_order and s.quoted_tax is not None)
    gc_at = f" · {gcn.lower()} at cost" if gc else ""         # no at-cost items, no words for them (Parkview)
    fin_rule = (f"check + {x.retail_markup:.1%}" if x.retail_markup is not None else f"check ÷ {PB['retail_factor']:g}") + " on the whole price" + (
        f", the {gcn.lower()} included" if gc else "")
    terms = f"about {money(p.monthly)}/mo at {PB['finance_rate']:.2%} for {PB['finance_years']:g} years, or 12 or 18 months with no payments"
    sell_sub = (f"sold at the owner's price · {money(p.sell_per_sf, True)}/SF" if sold else
                f"the owner's {money(per_sf, True)}/SF × {L.deck_sf:g} SF" if per_sf else
                f"{_pct(gmj)} gross on the work{gc_at} · {money(p.sell_per_sf, True)}/SF")
    head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · cost stack · internal</div>{_h1(name)}'
            f'<p>{" · ".join(v for v in (E(addr), f"{L.deck_sf:g} SF", E(today)) if v)}</p><div class="cs-hero">'
            f'<div><span class="l">{"Sold" if sold else "Sell"} · check or ACH</span><span class="v">{money(p.sell)}</span><span class="s">{E(sell_sub)}</span></div>'
            f'<div class="cs-side"><div><span class="l">Retail · financed</span><span class="v2">{money(p.retail)}</span><span class="s">{E(terms)} · financed = {E(fin_rule)}</span></div>'
            f'<div><span class="l">Gross profit</span><span class="v2">{_m(gp)}</span><span class="s">{_pct(gp / p.sell)} of the {"sold price" if sold else "sell"} · '
            f'{_pct(p.gm)} on the work' + (" (the sell less the at-cost items)" if gc else "") + '</span></div></div></div></div></header>')
    lt, lrows, lnote = _labor_rows(t, p)
    n_lines = sum(1 for l in t.lines if l.category != "Site")
    o = []; w = o.append
    w(f'<section class="job" id="job-{key}">')
    w('<h2 class="kicker" id="g-stack">The stack <span class="tag">materials at cost · tax · labor' + E(gc_at) + ' · internal</span></h2>')
    rows = [(f"Materials — the order at cost, {n_lines} lines" + (f", {E(t.order_ref)}" if t.order_ref else ""), _m(p.materials, True), "")]
    if p.material_factor != 1:
        rows.append((f"× {p.material_factor:g} material factor", _m(mat_f, True), ""))
    rows += [("Sales tax — as quoted" if quoted_tax else f"Sales tax {p.tax_rate:.2%} on the {'factored ' if p.material_factor != 1 else ''}materials", _m(tax, True), ""),
             (f"{E(lt)} (below)", _m(lab, True), ""), ("Work — carries the margin", _m(work, True), "sub")]
    if gc:
        rows.append((f"{E(gcn)} — at cost, no margin", _m(gc, True), ""))
    rows += [("Cost", _m(cost, True), "sub"), (f"{'Sold' if sold else 'Sell'} — check or ACH", money(p.sell), "big"),
             (f"Gross profit — {_pct(gp / p.sell)} of the {'sold price' if sold else 'sell'}", _m(gp), "sub")]
    w(_ledger(rows))
    if sold or per_sf:                       # a set price: the margin is what it carries
        w('<h2 class="kicker" id="g-margin">The margin <span class="tag">' + ("the owner's sold price" if sold else "the owner's price per SF") + "</span></h2>")
        w(f'<p class="cs-note">{"Sold at" if sold else "Set at"} {money(p.sell)}' + (f" (the owner's {money(per_sf, True)}/SF × {L.deck_sf:g} SF)" if per_sf and not sold else "")
          + f": the work carries {_pct(p.gm)} (1 − work ÷ the price" + (" less the at-cost items" if gc else "") + f"); gross profit {_m(gp)} is {_pct(gp / p.sell)} of it"
          + f" and a {_pct(gp / cost)} markup on cost.</p>")
    else:                                    # the job margin on the work, what is given free or priced on its own, the at-cost items
        w('<h2 class="kicker" id="g-margin">How the sell is set <span class="tag">' + f"{_pct(gmj)} gross on the work{E(gc_at)}</span></h2>")
        br = [("Work — carries the margin", _m(work, True), "")]
        if free >= 0.005:
            br.append((f"less the {n_free} riser light{'s' if n_free != 1 else ''}, free to the owner — the cost stays in the job, nothing in the price", _m(-free, True), ""))
        if own_w >= 0.005:
            br.append(("less the work priced on its own" + (f" — {E(note)}" if note else ""), _m(-own_w, True), ""))
        if st_w:
            br.append(("less the stairs at the owner's rule — their cost", _m(-st_w, True), ""))
        if len(br) > 1:
            br.append(("Work at the job margin", _m(base, True), "sub"))
        br.append((f"÷ (1 − {_pct(gmj)}) — {_pct(gmj)} gross on the work", _m(at_gm, True), ""))
        if st_s:
            br.append((f"+ Stairs at the owner's rule — {money(st_s)} sell, {money(st_w)} their cost, {_pct(1 - st_w / st_s)} margin", money(st_s), ""))
        if abs(own_s) >= 1:
            br.append(("+ the parts priced on their own, at their price" + (f" — {E(note)}" if note else ""), money(own_s), ""))
        if gc:
            br.append((f"+ {E(gcn)} at cost", _m(gc, True), ""))
        br.append(("Sell — check or ACH, to the dollar", money(p.sell), "big"))
        w(_ledger(br))
        why = ([f"the {n_free} riser light{'s are' if n_free != 1 else ' is'} free to the owner: {'their' if n_free != 1 else 'its'} {money(free)} cost stays in the job and "
                 "nothing goes in the price"] if free >= 0.005 else []) + ([f"{note} {'are' if many else 'is'} priced on {'their' if many else 'its'} own"]
                                                                        if own_w >= 0.005 and note else []) + (["the stairs sell at the owner's per-riser rule"] if st_s else [])
        why = "; ".join(why)
        w(f'<p class="cs-note">Priced at {_pct(gmj)} gross on the work.' + (f" {E(why[:1].upper() + why[1:])}" if why else "")
          + (f", so the margin on the work blends to {_pct(p.gm)}." if abs(p.gm - gmj) >= 0.0005 else "." if why else "") + f" Gross profit, {_m(gp)}, is {_pct(gp / p.sell)} of the "
          + f"{money(p.sell)} sell" + (f"; the {money(gc)} {E(gcn.lower())} {'are' if gcn.endswith('s') else 'is'} carried at cost." if gc else ".") + "</p>")
    if sold:                                 # what it costs to build: materials and tax at invoice, no factor
        tax_i = tax if quoted_tax else round(p.materials * p.tax_rate, 2)
        tot = round(p.materials + tax_i + lab + gc, 2)
        cb = [("Materials — every line of the order, at invoice", _m(p.materials, True), ""), (f"Sales tax {p.tax_rate:.2%} on the materials" if not quoted_tax else "Sales tax — as quoted", _m(tax_i, True), ""),
              ("Labor", _m(lab, True), "")] + ([(f"{E(gcn)} at cost", _m(gc, True), "")] if gc else []) + [("Cost to build", _m(tot, True), "big")]
        if st_s:
            cb.append((f"of which the stairs — sold at the owner's rule for {money(st_s)}, {_pct(1 - st_w / st_s)} margin", _m(st_w, True), ""))
        w('<h3>Cost to build — materials at invoice, labor' + (", at-cost items" if gc else "") + '</h3>' + _ledger(cb))
    keep = lambda n: "keep" if n <= 12 else ""             # a short table whole; a long one breaks, 3 rows or more either side (DOC_CSS)
    w(f'<h2 class="kicker" id="g-labor">{E(lt)}</h2>')
    w(table(["Line", "Qty", "Unit", "Rate", "Ext"], lrows, keep(len(lrows)), ["l", "r", "l", "r", "r"]))
    if lnote:
        w(f'<p class="cs-note">{E(lnote)}</p>')
    cats = t.by_category()
    w('<div class="cs-two"><div><h3>What the price includes — sell values</h3>'
      + table(["Item", "Value"], [[E(k), money(v)] for k, v in client_allocation(t, p)] + [["<b>Total, check or ACH</b>", f"<b>{money(p.sell)}</b>"], ["<b>Total, financed</b>", f"<b>{money(p.retail)}</b>"]], "keep", ["l", "r"])
      + "</div><div><h3>Materials by category — at cost</h3>"
      + table(["Category", "Lines", "Cost"], [[E(c), str(len(cats.get(c, []))), _m(v, True)] for c, v in p.categories.items()] + [["<b>Materials</b>", "", f"<b>{_m(p.materials, True)}</b>"]], "keep", ["l", "r", "r"])
      + "</div></div>")
    if len(p.gc_lines) > 1:
        w(f"<h3>{E(gcn)} — at cost, no margin</h3>" + table(["Item", "Amount", "Why"], [[E(i), _m(a, True), E(why)] for i, a, why in p.gc_lines], keep(len(p.gc_lines)), ["l", "r", "l"]))
    blocks = [o_ for o_ in (options or []) if isinstance(o_, dict)]      # the proposal's option blocks: how each is priced, estimates called out
    if blocks:
        w(_options_internal(_option_blocks(spec, t, p, blocks, key, Path(renders_dir) if renders_dir else out / "buildset" / "renders", {})))
    if p.options:
        sg = lambda v: ("+" if v >= 0 else "−") + money(abs(v))
        w("<h3>Options — full installed deltas</h3>" + table(["Option", "Cost", "Check / ACH", "Financed"], [[E(o_.name), sg(o_.cost), sg(o_.check), sg(o_.financed)] for o_ in p.options],
                                                             keep(len(p.options)), ["l", "r", "r", "r"]))
    floor = float(PB.get("gm_floor", 0.40))
    held = [v for v, on in (("the riser lights still free", free >= 0.005), ("the parts priced on their own still at their price", own_w >= 0.005),   # sell_floor's terms
                            ("the stairs still at the owner's rule", bool(st_s))) if on]
    notes = [f"At the {_pct(floor)} floor the sell would be {money(p.sell_floor)}" + (f" ({', '.join(held)})" if held else "")
             + (f"; this job is set at {_pct(gmj)}, under the floor, by the owner" if x.gm_below_floor and gmj < floor and not (sold or per_sf) else "") + "."]
    fee = PB.get("dealer_fee_financed")
    if fee and p.dealer_fee_note:
        notes.append(f"Dealer fee — {p.dealer_fee_note}. If the financed price absorbs the {_pct(fee)} fee, a financed sale nets {money(p.retail * (1 - fee))} "
                     f"and gross profit is {_m(p.retail * (1 - fee) - cost)}.")
    if sold:
        notes.append(f"Commission 10% of the sold price: {money(p.commission)}; gross profit after commission {_m(gp - p.commission)} ({_pct((gp - p.commission) / p.sell)} of the sold price).")
    if p.engineering:
        notes.append(f"Engineering — outside the price, at cost: {money(p.engineering[0])}–{money(p.engineering[1])}.")
    w('<h3>Notes</h3><ul class="cs-notes">' + "".join(f"<li>{E(v)}</li>" for v in notes) + "</ul>")
    cnote = [f for f in flags if _no_money(f)[1]]          # the flags whose dollar figures the takeoff leaves out: those clauses here
    if cnote:
        w('<h3>Flags with a cost note — the clauses the takeoff prints without their figures</h3><ul class="cs-notes">'
          + "".join(f"<li><b>{E(f.severity)} · {E(f.topic)}</b> {E(_money_clauses(f.text))}" + (f" <em>{E(_money_clauses(f.ref))}</em>" if "$" in (f.ref or "") else "") + "</li>"
                    for f in cnote) + "</ul>")
    w("</section>")
    lab_w = "labor as priced" if lt == "Labor" else "labor at the " + lt.split(" — ", 1)[1]        # "labor at the rate card, less the owner's $1,000 cut"
    body = (head + '<main class="wrap">' + "".join(o) + '<footer><span>GS Exterior Experts · Deck Division</span><span>Cost stack: materials at the order'
            + (f" × {p.material_factor:g}" if p.material_factor != 1 else "") + f", tax, {E(lab_w)}" + (f", {E(gcn.lower())} at cost" if gc else "")
            + ". Internal — not for the homeowner.</span></footer></main>")
    title = f"{name} — Cost Stack"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>{FONT}{CSS}"
            + DOC_CSS + COST_CSS + _doc_page_css(f"GS Exterior Experts · {_foot(name)} · Cost stack · internal · {today}") + '</head><body class="doc cs">' + body + "</body></html>\n")
    (out / "page.html").write_text(page)
    json.dump({}, open(out / "files.json", "w"), indent=1)
    result = dict(html=str(out / "page.html"), files={}, pricing=p, takeoff=t)
    if pdf:
        result["pdf"] = render_pdf(page, {}, str(out / "page.pdf"), key)
    return result


def _dusk_html(key, have) -> str:
    """The dusk renders (station_dusk stills), when the job has them: the deck at the blue hour with its lights on."""
    names = [n for n in ("corner_dusk", "yard_dusk", "ondeck_dusk", "corner2_dusk", "facade_dusk") if n in have]
    if not names:
        return ""
    return '<h2 class="kicker" id="g-dusk">At dusk <span class="tag">the lights on · design intent</span></h2>' + _gallery(key, names, have)


def _gallery(key, names, have):
    return '<div class="gal">' + "".join(f'<figure><img src="r/{key}-{n}.jpg" alt="{E(CAP.get(n, n))}" loading="lazy"><figcaption>{E(CAP.get(n, n))}</figcaption></figure>' for n in names if n in have) + "</div>"


def _steps(key, steps, cap, customer):
    out = []
    for st in steps:
        title = f"Step {st['n']} · {E(st['title'])}" if customer else f"{st['code']} · Step {st['n']} · {E(st['title'])}"
        fc = re.sub(r"^Step \d+ · ", f"Step {st['n']} · ", st.get("cap") or cap[st["still"]])     # the model's phase number -> the step as built (phases skip); a step on a borrowed still: its own caption
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
    from .report import rail_product, drink_rail_words
    rail = (f"{rail_product(s, rl.system)}, {rl.color}, {rl.height:g}\" · {rl.rail_lf:g} LF"
            + (f" · {drink_rail_words(s)}" if s.railing.drink_rail else "")) if rl else "None"
    reads += [("Decking", decking), ("Rail", rail)]
    for ss, st in zip(stair_specs(t), L.stairs):
        reads.append((getattr(ss, "name", None) or "Stair", stair_words(ss, st, True)))
    from .report import step_face_words
    if step_face_words(t):
        reads.append(("Step face", step_face_words(t)))
    lt = lights_of(t)
    if lt["total"]:
        from .report import post_light_terms
        reads.append(("Lighting", ", ".join(x for x in ((f"{lt['riser']} riser lights" if lt["riser"] else ""), (f"{lt['post_cap']} {post_light_terms(t)[0]}" if lt["post_cap"] else ""),
                                                        (f"{lt['other']} more" if lt["other"] else "")) if x) + " · LED, low voltage"))
    from .report import foundation_words
    found = foundation_words(t)[2]           # by the spec's footing type: Diamond Piers, caissons (size), concrete piers
    reads += [("Structure", composite_frame_words(t).rstrip(".") + f"; {found}"), ("Design load", sm["design_load"].replace(" · engineered", ", stamped by a Colorado engineer"))]
    return '<dl class="reads levels">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in reads) + "</dl>"


LEVELS_CSS = """<style>
.reads.levels { grid-template-columns:160px 1fr; }
@media (max-width: 640px) { .reads.levels { grid-template-columns:1fr; } }
@media print { #g-reads + .gal img { max-height:1.6in; object-fit:cover; } #g-what + .tw td { padding-top:4px; padding-bottom:4px; } .reads.levels { gap:2px 12px; } .reads.levels dd { font-size:12.5px; line-height:1.4; }
  .reads.levels dt { font-size:11px; } #g-what { margin-top:18px; } }
</style>"""


def _reads_rows(t, L, sm):
    """The homeowner's at-a-glance rows for a deck on one level: [(label, text)]."""
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
        from .report import rail_product, drink_rail_words
        rail = f"{rail_product(s, rl.system)}, {rl.color}, {rl.height:g}\"" + (f"; {drink_rail_words(s)}" if s.railing.drink_rail else "") + f" · {rl.rail_lf:g} LF"
    else:
        rail = "None"
    from .report import stair_groups, stair_rows, frame_words, posts_on_words
    stairs = []
    for grp, row in zip(stair_groups(t), stair_rows(t)):
        if len(grp["members"]) > 1:            # box steps that wrap a corner read as one step, its width along each side
            stairs.append(row)
            continue
        ss, st = grp["members"][0]
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
    from .report import steel_posts_words
    structure = (f"CEMCO cold-formed steel frame, {s.framing.steel_joist} C-joists at {fr.spacing:g}\" on center, {s.framing.steel_track} track, boxed {s.framing.steel_joist} beams, all G90; "
                 + (steel_posts_words(t) or sm['posts']) if s.framing.system == "steel" else
                 frame_words(t, tape=False)[:-1] + "; " + posts_on_words(t) + ("; joist tape on every member" if s.framing.joist_tape else ""))
    return [("Deck", deck), ("Decking", decking), ("Rail", rail)] + stairs + [("Structure", structure), ("Design load", sm["design_load"].replace(" · engineered", ", stamped by a Colorado engineer"))]


def _reads_lite(t, L, sm):
    """The homeowner's at-a-glance: what it is, not how it is framed."""
    if hasattr(L, "parts"):
        return _reads_levels(t, L, sm)
    return '<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in _reads_rows(t, L, sm)) + "</dl>"


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
    if l1["riser"] > l0["riser"]:                # where they go, in the lighting plan's own words (riser_where; box steps that wrap a corner as one)
        from .report import riser_where_words
        rw = riser_where_words(t1) if not l0["riser"] else ""
        rows.append(("Riser lights", f"{l1['riser'] - l0['riser']} {'more ' if l0['riser'] else ''}LED lights" + (f", {rw}" if rw else "")))
    if l1["post_cap"] > l0["post_cap"]:
        from .report import post_light_terms
        _pl, _pw = post_light_terms(t1)          # cap lights, or accent lights below an over-the-post drink rail
        rows.append((_pl[0].upper() + _pl[1:], f"{l1['post_cap'] - l0['post_cap']} LED {_pl}, {_pw}"))
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
    from .report import foundation_words
    dp = foundation_words(t1)[0] - foundation_words(t0)[0]
    if dp > 0:                               # by the spec's footing type
        noun = {"diamond_pier": "Diamond Pier foundation", "caisson": "concrete caisson", "concrete": "concrete pier"}.get(t1.spec.framing.footing_type, "footing")
        rows.append(("Foundation", f"{dp} more {noun}{'s' if dp != 1 else ''}"))
    return rows


def _sign(v) -> str:
    return ("+" if v >= 0 else "−") + money(abs(v))


def _caps_file(p: Path) -> Dict[str, str]:
    """A renders folder's captions.json as {name: caption}: keys with or without ".jpg"; each value the caption, or a dict
    carrying one (the photoreal set's format: {"caption": ..., "view": ...})."""
    if not p.exists():
        return {}
    out = {}
    for k, v in json.load(open(p)).items():
        v = (v.get("caption") or v.get("view") or "") if isinstance(v, dict) else v
        if isinstance(v, str):
            out[k[:-4] if k.lower().endswith(".jpg") else k] = v
    return out


def _render_figs(o: dict, rd: Path, key: str, ok: str, files: dict) -> list:
    """The figures for an option's (or add-on's) own renders: o["renders"] = [name | (name, caption)] — stills in
    o["renders_dir"] (default: the page's renders); a name may run into a subfolder ("roof_closed/roof_yard_1600"), its
    caption then from that folder's captions.json; each file goes in files.json as r/<key>-<option>-<name>.jpg."""
    rdir = Path(o["renders_dir"]) if o.get("renders_dir") else rd
    caps = dict(CAP)
    caps.update(_caps_file(rdir / "captions.json"))
    figs = []
    for r_ in o.get("renders") or []:
        nm, cp = (r_[0], r_[1]) if isinstance(r_, (list, tuple)) else (r_, None)
        f_ = rdir / f"{nm}.jpg"
        if not f_.exists():
            continue
        fn = f"r/{key}-{ok}-{re.sub(r'[^A-Za-z0-9_-]+', '-', nm).strip('-')}.jpg"
        files[fn] = str(f_)
        if not cp and f_.parent != rdir:
            cp = _caps_file(f_.parent / "captions.json").get(f_.stem)
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
    sums = []                                # per block: its number, its group, check and financed with its add-ons
    for i, o in enumerate(blocks, 1):
        ok = re.sub(r"[^a-z0-9]+", "-", str(o.get("key") or f"opt{i}").lower()).strip("-")
        title, num = o.get("title") or f"Option {i}", o.get("number") or f"Option {i}"
        t2 = None
        if o.get("spec") is not None:            # the deck with this option: an engine delta (on a per-SF deck: cost math at the job margin)
            t2, _, p2 = run(o["spec"])
            c, f, m = option_delta(p, p2)
            basis = f"engine delta: work {p2.work - p.work:+,.0f}" + (f" at the job margin {p.options_gm:.1%} (the deck sells per SF)" if getattr(p, "per_sf", 0)
                                                                      else f", the deck's {getattr(p, 'options_gm', p.gm):.1%} margin")    # what an option prices at (not the blend)
        elif o.get("roof") is not None:          # a louvered roof: its own price per SF x its area (or a set price), outside the deck's margin
            from .louvered import roofs_of, resolve, surfaces_of, scope_words
            rs = o.get("roof_spec") or spec      # the spec that carries the roof (the deck's, or a copy with the roof on it)
            roof = roofs_of(rs)[o["roof"]] if isinstance(o["roof"], int) else o["roof"]
            ap = price_louvered(rs, roof)
            c, f, m = ap.sell, ap.retail, ap.monthly
            basis = f"owner-set: {ap.basis}, sold on its own (outside the deck's cost and margin)"
            dw = o.get("deck_work") or {}
            if dw.get("price"):                  # the deck structure the roof needs (its columns / caissons), at the deck's margin, rides in its price
                dc, df_, dm = fixed_terms(spec, dw["price"])
                c, f, m = c + dc, f + df_, m + dm
                basis += f" + {dw.get('label') or 'the deck structure for it'} ${dc:,.0f} at the deck's margin"
            if o.get("facts") is None:
                from .pricing import roof_size_ft
                _w, _d = roof_size_ft(roof)
                o = dict(o, facts=_roof_scope(resolve(roof, surfaces_of(t.layout if rs is spec else run(rs)[0].layout)),
                                              dict(width_ft=_w, depth_ft=_d, area_sf=ap.sf)))
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
                    from .report import post_light_terms
                    _pl = post_light_terms(ta)[0]
                    note = " and ".join(x for x in ((f"{xr} more riser light{'s' if xr != 1 else ''}" if xr > 0 else ""),
                                                     (f"{xp} more {_pl if xp != 1 else _pl[:-1]}" if xp > 0 else "")) if x)
            elif a.get("price") is not None:     # a set price
                ca, fa, ma = fixed_terms(spec, a["price"])
            elif a.get("screens") and o.get("roof") is not None:     # the roof's screens: the louvered engine's price for them
                from .louvered import roof_pricing, roofs_of, resolve, surfaces_of
                rs = o.get("roof_spec") or spec
                Lr = t.layout if rs is spec else run(rs)[0].layout
                rows_ = roof_pricing(rs, Lr)["roofs"]
                rr = rows_[o["roof"] if isinstance(o["roof"], int) else 0]
                if not rr.get("screens_sell"):
                    raise ValueError("screens add-on: the roof has no screens (louvered_roofs[i].screens)")
                ca, fa, ma = fixed_terms(spec, rr["screens_sell"])
                sl = _screen_lines(resolve(roofs_of(rs)[o["roof"]] if isinstance(o["roof"], int) else o["roof"], surfaces_of(Lr)), a.get("open_note"))
                note = note or (". ".join(sl) + "." if sl else "; ".join(x["words"] for x in rr.get("screens") or []))
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
        if o.get("note") or o.get("url"):          # the note (the roof's own document) sits with the words, before the pictures
            h.append('<p class="opt-note">' + E(o.get("note", "")) + (f' <a href="{E(o["url"])}">{E(o.get("url_text") or o["url"])}</a>' if o.get("url") else "") + "</p>")
        if imgs:
            h.append('<div class="gal">' + "".join(imgs) + "</div>")
        for lab, ca, fa, ma, note, figs, _ab in adds:
            h.append(f'<div class="opt-addon"><div class="oa-line"><b>{E(lab)}</b><span>{_sign(ca)} check or ACH' + (f" · {_sign(fa)} financed · {_sign(ma)}/mo" if show_fin else "") + "</span></div>"
                     + (f'<span class="fine">{E(note)}</span>' if note else "") + ('<div class="gal">' + "".join(figs) + "</div>" if figs else "") + "</div>")
        h.append("</div></section>")
        out.append("".join(h))
        rows.append((f"{num} — {title}", c, f, m, False, basis))
        rows += [(lab, ca, fa, ma, True, ab_) for lab, ca, fa, ma, _, _, ab_ in adds]
        sums.append((num, str(o.get("group") or ""), c + sum(a[1] for a in adds), f + sum(a[2] for a in adds)))
    # "the deck with every option": options that share a group (the two yard-stair layouts) are one or the other — the group's
    # first option counts in the total, and every other one gets a total of its own in its place
    first = {}
    for num, g, sc, sf in sums:
        if g and g not in first:
            first[g] = (num, sc, sf)
    tc = sum(sc for _n, g, sc, _f in sums if not g) + sum(v[1] for v in first.values())
    tf = sum(sf for _n, g, _c, sf in sums if not g) + sum(v[2] for v in first.values())
    members = {g: [n for n, gg, _c, _f in sums if gg == g] for g in first}
    alts = [(f"The deck with every option, with {n} in place of {first[g][0]}",
             (p.sell + tc - first[g][1] + sc, p.retail + tf - first[g][2] + sf, _monthly(p.retail + tf - first[g][2] + sf)))
            for n, g, sc, sf in sums if g and first[g][0] != n]
    multi = [g for g in first if len(members[g]) > 1]

    def _both(ns):
        return ("Options " + " and ".join(n[len("Option "):] for n in ns)) if all(n.startswith("Option ") for n in ns) else " and ".join(ns)
    head = ('<h2 class="kicker pb" id="g-options">Options <span class="tag">each priced on its own, added to the deck price · '
            + ("its own renders" if any("<figure>" in x for x in out) else "the whole installed difference") + "</span></h2>")
    return dict(html=head + "".join(out), rows=rows, total=(p.sell + tc, p.retail + tf, _monthly(p.retail + tf)), show_fin=show_fin,
                total_label="The deck with every option" + (", with " + " and ".join(first[g][0] for g in multi) if multi else ""),
                totals=alts, group_note=" ".join(f"{_both(members[g])} are one or the other." for g in multi))


def _options_summary(ob) -> str:
    """The options in the investment section: each one's price three ways (the add-ons under the option they ride with), then
    the deck with every option."""
    show_fin = ob["show_fin"]
    body = [[(f'<span class="sub">{E(lab)}</span>' if sub else E(lab)), _sign(c)] + ([_sign(f), _sign(m) + "/mo"] if show_fin else [])
            for lab, c, f, m, sub, _b in ob["rows"]]
    for lab, (tc, tf, tm) in [(ob.get("total_label") or "The deck with every option", ob["total"])] + list(ob.get("totals") or []):
        body.append([f"<b>{E(lab)}</b>", f"<b>{money(tc)}</b>"] + ([f"<b>{money(tf)}</b>", f"<b>{money(tm)}/mo</b>"] if show_fin else []))
    return ("<p>Each line is the whole difference, installed, added to the deck price above." + (f" {E(ob['group_note'])}" if ob.get("group_note") else "") + "</p>"
            + table(["Option", "Check or ACH"] + (["Financed", "Monthly"] if show_fin else []), body, "optsum", ["l", "r"] + (["r", "r"] if show_fin else [])))


def _options_internal(ob) -> str:
    """The internal set: every option as the proposal prices it, with how each number was made — an engine delta, an
    owner-set price, or an ESTIMATE the owner has not set (the lead confirms it before anything goes to the client)."""
    rows = [[(("&nbsp;&nbsp;" + E(lab)) if sub else f"<b>{E(lab)}</b>"), _sign(c), _sign(f), _sign(m) + "/mo", E(b)] for lab, c, f, m, sub, b in ob["rows"]]
    for lab, (tc, tf, tm) in [(ob.get("total_label") or "The deck with every option", ob["total"])] + list(ob.get("totals") or []):
        rows.append([f"<b>{E(lab)}</b>", f"<b>{money(tc)}</b>", f"<b>{money(tf)}</b>", f"<b>{money(tm)}/mo</b>", E(ob.get("group_note") or "")])
    est = [lab for lab, c, f, m, sub, b in ob["rows"] if "ESTIMATE" in b]
    return ('<h2 class="kicker" id="g-options">Options in the proposal <span class="tag">internal · how each price was made</span></h2>'
            + (f'<p><b>ESTIMATE — not set by the owner:</b> {E("; ".join(est))}. Confirm the number before the proposal goes to the client.</p>' if est else "")
            + table(["Option", "Check / ACH", "Financed", "Monthly", "Basis"], rows, "", ["l", "r", "r", "r", "l"]))


def _screens_basis(rr: dict) -> str:
    """How the roof's screens are priced, for the internal set: the owner's price, or the louvered engine's placeholder rate."""
    scr = rr.get("screens") or []
    lf = sum(float(x.get("width_ft") or 0) for x in scr)
    est = any(x.get("estimate") for x in scr)
    what = f"{len(scr)} screen{'s' if len(scr) != 1 else ''}, {lf:.1f} LF (" + ", ".join(f"{x.get('side')} ${float(x.get('sell') or 0):,.0f}" for x in scr) + ")"
    if not est:
        return f"set on the roof: {what}"
    try:
        from .louvered import SCREEN_EST
        rule = " + ".join(f"{k.replace('_', ' ')} ${float(v):,.0f}" for k, v in SCREEN_EST.items())
    except Exception:
        rule = "louvered.py"
    return f"ESTIMATE — the louvered engine's placeholder ({rule}): {what}; the owner has not set this price"


def _viewer_link(url: str, note: Optional[str] = None) -> str:
    """The customer documents link to the interactive 3D page instead of embedding the viewer (a PDF keeps the link)."""
    if not url:
        return ""
    return ('<h2 class="kicker" id="g-3d">Interactive 3D <span class="tag">opens in a web browser</span></h2>'
            f'<div class="v3d-link"><p>{E(note or "The deck and its options in 3D, in a web browser.")}</p>'
            f'<a class="v3d-btn" href="{E(url)}">Open the interactive 3D model</a><span class="v3d-url">{E(url)}</span></div>')


def _confirm_box(spec) -> str:
    """The proposal's "Still to confirm" box (extras.confirm: [lines] or {"title", "intro", "items"}): what the client and we
    settle before the build. It prints on an engineered quote too, where proposal_note does not. A line that opens on a short
    sentence ("HOA approval. ...") sets that sentence in bold."""
    c = getattr(spec.extras, "confirm", None)
    if not c:
        return ""
    c = dict(items=list(c)) if isinstance(c, (list, tuple)) else dict(c)
    items = [str(x).strip() for x in c.get("items") or [] if str(x).strip()]
    if not items:
        return ""

    def li(x):
        head, sep, rest = x.partition(". ")
        return f"<li><b>{E(head)}.</b> {E(rest)}</li>" if sep and len(head.split()) <= 8 else f"<li>{E(x)}</li>"
    return (f'<h2 class="kicker pb" id="g-confirm">{E(c.get("title") or "Still to confirm before we build")}</h2><div class="confirm">'
            + (f"<p>{E(c['intro'])}</p>" if c.get("intro") else "") + '<ul class="opt-scope">' + "".join(li(x) for x in items) + "</ul></div>")


# words a homeowner's timeline never carries (the schedule model scrubs its customer rows; this keeps it that way)
_NOT_FOR_CLIENT = re.compile(r"\b(permits?|permitted|inspect\w*|AHJ|HOA|ACC|811|city|county|building department|engineer of record|Suncoast|"
                             r"dealer\w*|vendor\w*|supplier\w*|D&D|Decks & Docks)\b", re.I)      # "weather permitting" is fine


def _timeline_days(tl: dict) -> int:
    """Working days on site in a customer timeline: its last row's last day, else the number in its title."""
    last = [int(r.get("last_day") or 0) for r in tl.get("rows") or []]
    if last and max(last):
        return max(last)
    m = re.search(r"(\d+)\s+working day", tl.get("title") or "")
    return int(m.group(1)) if m else 0


def _timeline(tl: dict, opts: Optional[list] = None, head: bool = True) -> str:
    """The proposal's Schedule from the job's own timeline (report.timeline_of, or the engine's day plan: engine_timeline): the
    time before day 1 and a bar per stretch of work on the working days it takes (column 0 is before day 1; day d spans [d, d+1)),
    then what each option does to it (opts = [(label, the option's timeline | None, note)]); head=False leaves the heading and
    the title to the page around it. A line with permit / inspection / vendor words stops the build."""
    rows = list(tl.get("rows") or [])
    pre = tl.get("precon") or None
    said = ([pre.get("text", "")] if pre else []) + [r.get("title") or r.get("label") or "" for r in rows] + [tl.get("title") or ""]
    said += [x for _l, o_, n_ in (opts or []) for x in [n_ or ""] + [r.get("title") or r.get("label") or "" for r in ((o_ or {}).get("rows") or [])]]
    for x in said:
        if x and _NOT_FOR_CLIENT.search(x):
            raise ValueError(f"the customer timeline carries permit / inspection / vendor wording: {x!r}")
    nd = _timeline_days(tl)
    xs = [float(v) for r in rows for v in (r.get("gantt_x") or [])] + ([float(v) for v in (pre.get("gantt_x") or [])] if pre else [])
    n = max(int(math.ceil(max(xs) - 1e-9)) if xs else 0, nd + 1)

    def bar(x0, x1, cls=""):
        return f'<i class="{cls}" style="left:{100 * x0 / n:.3f}%;width:{max(0.6, 100 * (x1 - x0) / n):.3f}%"></i>'
    ticks = sorted({1} | set(range(5, n, 5)) | ({nd} if nd % 5 >= 3 else set()))
    items = ['<li class="g-head" aria-hidden="true"><span>Working day</span><span class="g-ticks">'
             + "".join(f'<span style="left:{100 * (d + 0.5) / n:.3f}%">{d}</span>' for d in ticks if 0 < d < n) + "</span></li>"]
    if pre:
        g = pre.get("gantt_x") or [0, 1]
        items.append(f'<li><span class="g-lab"><b>Before day 1</b>{E(pre.get("text", ""))}</span><span class="g-bar">{bar(float(g[0]), float(g[1]), "pre")}</span></li>')
    for r in rows:
        g = r.get("gantt_x") or [r.get("first_day", 1), (r.get("last_day") or r.get("first_day", 1)) + 1]
        items.append(f'<li><span class="g-lab"><b>{E(r.get("days", ""))}</b>{E(r.get("title") or r.get("label") or "")}</span>'
                     f'<span class="g-bar">{bar(float(g[0]), float(g[1]), "" if r.get("option", "base") == "base" else "opt")}</span></li>')
    h = (['<h2 class="kicker pb" id="g-schedule">Schedule <span class="tag">working days on site · the deck as proposed</span></h2>',
          f'<p class="sched-title">{E(tl.get("title") or f"{nd} working days on site, weather permitting")}</p>'] if head else []) + [
         f'<ol class="gantt" style="--n:{n}">' + "".join(items) + "</ol>"]
    ol = []
    for lab, o_, note in opts or []:
        txt = ""
        if o_:
            n2 = _timeline_days(o_)
            add = [r for r in o_.get("rows") or [] if r.get("option", "base") != "base"]
            txt = ((f"{n2} working days on site, {n2 - nd} more" if n2 > nd else f"the deck's {nd} working days stay the same" if n2 == nd else f"{n2} working days on site")
                   + "".join(f"; {r.get('days', '')} — {r.get('label') or r.get('title') or ''}" for r in add))
        txt = "; ".join(x for x in (txt, note) if x)
        if txt:
            ol.append(f"<li><b>{E(lab)}:</b> {E(txt)}</li>")
    if ol:
        h.append('<h3>With the options</h3><ul class="opt-scope sched-opts">' + "".join(ol) + "</ul>")
    return "".join(h)


def _option_timelines(spec, tl: dict, blocks) -> list:
    """Each option block's line for the Schedule: [(label, its timeline | None, note)]. An option's timeline is its own
    "timeline" key (a customer block or "schedule.json#Scenario"), else its spec's extras.timeline when that is not the
    deck's; "timeline_note" adds words (the roof: when it goes up). An add-on gets a line only with its own timeline or note
    ("timeline_label" names it, e.g. "Options 1 and 2 together")."""
    out, later = [], []                      # the options in order, then the add-ons (they combine options)
    for i, o in enumerate(blocks or [], 1):
        mine = timeline_of(o["timeline"]) if o.get("timeline") else None
        if mine is None:
            sp = o.get("spec") if o.get("spec") is not None else o.get("roof_spec")
            cand = timeline_of(sp) if sp is not None and sp is not spec else None
            mine = cand if cand and cand != tl else None
        if mine or o.get("timeline_note"):
            out.append((f"{o.get('number') or f'Option {i}'} — {o.get('title') or ''}".rstrip(" —"), mine, o.get("timeline_note") or ""))
        for a in o.get("addons") or []:
            at = timeline_of(a["timeline"]) if a.get("timeline") else None
            if at or a.get("timeline_note"):
                later.append((a.get("timeline_label") or a.get("label") or "Add-on", at, a.get("timeline_note") or ""))
    return out + later


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
    if cost_only:                            # the cost stack: a document of its own, one or two pages, no build set
        return _cost_doc(spec, t, flags, p, out, key, name, renders_dir, pdf, date_line, options)
    if not (customer or supplier):           # the takeoff carries no money: a flag's dollar clauses go to the cost stack
        flags = [_no_money(f)[0] for f in flags]
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
    CAP.update(_caps_file(rd / "captions.json"))  # a job's own captions (its camera stations, option renders)
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
    qmd = quote_markdown(t, p, today)        # the price holds 30 days from the document's date
    holds = ("This quote holds through " if spec.extras.engineered else "This price holds through ") + price_holds_through(today) + "."
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
            w(table(["NET", "ORDER", "Unit", "Item", "Why"], [[qfmt(l.net), f"<b>{qfmt(l.order)}</b>", E(l.unit), E(l.item) + (f" · part no. {E(l.sku)}" if _part_no(l.sku) else ""), E(l.why)] for l in lines],
                    "order netorder", ["r", "r", "l", "l", "l"]))      # the maker's part number where the order carries one (not an internal pricebook key)
        w('<h2 class="kicker">Fastener &amp; connector schedule</h2>')
        w('<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in t.schedule.items()) + "</dl>")
        w('<h2 class="kicker">Cut list</h2>' + table(["Member", "Stock", "Length", "Qty", "Note"], [[E(c.member), E(c.nominal), ftin(c.length_in), str(c.qty), E(c.note)] for c in t.cut_list], "", ["l", "l", "r", "r", "l"]))
        w(f'<h2 class="kicker pb">Drawing set <span class="tag">{_sheet_letters(r["sheets"])} sheets</span></h2><div class="sheets">')
        for num, ttl, svg in r["sheets"]:
            w(f'<details class="sheet" open><summary><b>{num}</b> {E(ttl)}</summary>{svg}</details>')
        w("</div>")
        w('<h2 class="kicker pb">Exploded views</h2>')
        w(_gallery(key, [n_ for n_ in ("exploded", "exploded2", "structure-underiso", "frame-iso2", "exploded-corner", "exploded-low") if n_ in have][:4], have))
        w('<h2 class="kicker pb">Build set <span class="tag">T-400 series · goes in · how · check</span></h2>')
        w(_steps(key, r["steps"], cap, False))
        w('<h2 class="kicker">3D model <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>')
        w(viewer_html(S, None, title=f"{name} — 3D", standalone=False, uid=f"v3d-{key}"))
    elif proposal:
        # the photo-led proposal (proposal_look): one deliberate page per section, the photoreal renders large, the views
        # placed by name (PL.plan_views), the price after the pictures; the cover and the back cover go on in the page shell
        opts = [(lab, run(sp_)[2]) for lab, sp_ in (o_ for o_ in (options or []) if not isinstance(o_, dict))]
        blocks = [o_ for o_ in (options or []) if isinstance(o_, dict)]
        V = PL.plan_views(have, hero, PL.photoreal_names(rd, have))
        foot = PL.brand_footer(spec)
        inc = qmd[qmd.index("## INCLUDED"):qmd.index("## PLAN")].replace("## INCLUDED — what it is\n", "")
        beams = sorted({b.size for b in spec.framing.beams}) if spec.framing.beams else []
        frame_lite = (f"{sm['joists']}; {sm['rims']}" + ((f"; {beam_words(beams, beam_species_words(spec.framing.beams), len(spec.framing.beams))}" if beams else "") if spec.framing.system != "steel" else "; boxed steel beams")
                      + (("; joist tape on every joist, rim and beam" if L.beam_lines else "; joist tape on every joist and rim") if spec.framing.joist_tape else "") + ".")
        if not hasattr(L, "parts") and spec.framing.system == "steel":   # the quote reads a wood frame (report.frame_words) and two levels in the homeowner's words already
            inc = re.sub(r"\| Frame \| .*? \|\n", f"| Frame | {frame_lite} |\n", inc, count=1)
        inc_rows = PL.md_rows(inc)
        light_note = next((r[1] for r in inc_rows if len(r) >= 2 and r[0].strip().lower() == "lighting"), "")
        w(PL.pp_overview(spec, L, key, V["overview"], CAP, lede, n_piers, t=t, foot=foot))
        for i, names in enumerate(V["day"]):
            w(PL.pp_photos(key, names, CAP, "By day", foot=foot, sid="g-renders" if i == 0 else ""))
        if alt_html:
            w(f'<section class="pg pp-flow flow"><div class="pin">{alt_html}</div></section>')
        w(PL.pp_above(key, V["aerial"], V["plan"], V["sun"], CAP, ("the real sun at this address · " + sun_tag) if V["sun"] else "", foot=foot))
        w(PL.pp_more(key, V["more"], CAP, foot=foot))
        w(PL.pp_included(key, V["detail"], CAP, inc_rows, foot=foot, excl=list(spec.extras.exclusions or [])))
        big = next((n for n in ("exploded", "exploded-corner", "exploded2", "exploded-low") if n in have), None)
        small = [n for n in ("frame-iso2", "structure-underiso", "exploded-corner", "exploded2", "under", "underiso") if n in have and n != big][:2]
        reads = (_reads_levels(t, L, sm) if hasattr(L, "parts") else
                 '<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in _reads_rows(t, L, sm) if k not in ("Decking", "Rail")) + "</dl>")
        w(PL.pp_built(key, big, small, CAP, reads, foot=foot))
        w(PL.pp_materials(materials_rows(t), foot=foot))
        ob = _option_blocks(spec, t, p, blocks, key, rd, files) if blocks else None
        if ob:
            w(f'<section class="pg pp-flow flow"><div class="pin">{ob["html"]}</div></section>')
        tl = timeline_of(spec) or engine_timeline(t)    # the job's own timeline (a schedule model), else the engine's own day plan
        pays = None if spec.extras.engineered else payment_schedule(p.sell)   # an engineered quote gets its payment terms with the fixed-price proposal
        w(PL.pp_schedule(tl.get("title") or f"{_timeline_days(tl)} working days on site, weather permitting", _timeline(tl, _option_timelines(spec, tl, blocks), head=False),
                         pays, foot=foot))
        for i, names in enumerate(V["night"]):     # after dark: the last pictures before the price
            w(PL.pp_photos(key, names, CAP, "After dark", night=True, note=light_note if i == 0 else "", foot=foot, sid="g-dusk" if i == 0 else ""))
        opt_html = _options_table(p, opts) + (_options_summary(ob) if ob else "")
        nxt = md_to_html(re.sub(r"^## NEXT STEP\n", "", qmd[qmd.index("## NEXT STEP"):]))
        if spec.extras.price_breakdown:
            w(PL.pp_invest(spec, p, opt_html, nxt, foot=foot, alloc=client_allocation(t, p)))
        else:
            q2 = qmd[qmd.index("## PRICE"):qmd.index("## INCLUDED")]
            w('<section class="pg pp-flow flow" id="g-investment"><div class="pin"><h2 class="kicker">Investment</h2><div class="quote" style="break-before:auto;page-break-before:auto">'
              + md_to_html(q2) + opt_html + md_to_html(qmd[qmd.index("## NEXT STEP"):]) + "</div></div></section>")
        cb = _confirm_box(spec)              # the client's "Still to confirm" box (extras.confirm), outside the scope and the price
        if cb:
            w(f'<section class="pg pp-flow flow"><div class="pin">{cb}</div></section>')
        w(PL.pp_company(spec, foot=foot))    # who is building it: the company, the credentials, who to call
        if viewer_url is not None:           # the interactive 3D page instead of the embedded viewer (PDF-first documents)
            if viewer_url:
                w(f'<section class="pg pp-flow pp-3d"><div class="pin">{_viewer_link(viewer_url, viewer_note)}</div></section>')
        else:                                # the live viewer on the web page; print leaves it out (the back cover points to it)
            w('<section class="pg pp-flow pp-3d"><div class="pin"><h2 class="kicker" id="g-3d">3D model <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>'
              + viewer_html(S, None, title=f"{name} — 3D", standalone=False, uid=f"v3d-{key}") + "</div></section>")
        w(PL.pp_back(spec, key, V["back"], CAP, today, viewer_url or None, f"{CLIENT_FOOT} {holds}"))
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
        w(_gallery(key, ["corner", "corner2", "ondeck", "detail", "facade", "under", "isolow"], have))
        w(_dusk_html(key, have))
        w(alt_html)
        w(sun_html)
        w('<h2 class="kicker pb" id="g-iso">Isometrics <span class="tag">the model from above</span></h2>')
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
            w('<h3>Layout notes</h3><ul class="notes">' + "".join(f"<li>{E(n[:1].upper() + n[1:])}</li>" for n in notes) + "</ul>")
        w('<h2 class="kicker" id="g-flags">Site &amp; code flags <span class="tag">internal</span></h2><ul class="flags">')
        for f in flags:
            w(f'<li class="sev-{f.severity.lower()}"><span class="sev">{f.severity}</span><span class="topic">{E(f.topic)}</span><span class="txt">{E(f.text)}{(" <em>" + E(f.ref) + "</em>") if f.ref else ""}</span></li>')
        w("</ul>")
        w(_order_internal(t))                # quantities only: no pricing in the takeoff + build set (the cost stack carries it)
        w('<h2 class="kicker">Fastener &amp; connector schedule</h2>')
        w('<dl class="reads">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in t.schedule.items()) + "</dl>")
        w('<h2 class="kicker">Cut list</h2>' + table(["Member", "Stock", "Length", "Qty", "Note"], [[E(c.member), E(c.nominal), ftin(c.length_in), str(c.qty), E(c.note)] for c in t.cut_list], "", ["l", "l", "r", "r", "l"]))
        w('<h2 class="kicker">Renders <span class="tag">3D model · design intent · ' + ("timbers shown with the optional oil finish" if S.meta["timber"] and not S.meta["oiled"] else "frame shown as specified") + "</span></h2>")
        w(_gallery(key, ["yard", "corner", "corner2", "ondeck", "detail", "facade", "under"], have))
        w(_dusk_html(key, have))
        w(alt_html)
        w(sun_html)
        w('<h2 class="kicker">Isometrics</h2>')
        w(_gallery(key, ["iso", "iso2", "isolow", "underiso", "plan"], have))
        w('<h2 class="kicker">Exploded</h2>')
        w(_gallery(key, ["exploded", "exploded2", "exploded-corner", "exploded-low"], have))
        w(f'<h2 class="kicker">Drawing set <span class="tag">{_sheet_letters(r["sheets"])} sheets</span></h2><div class="sheets">')
        for num, ttl, svg in r["sheets"]:
            w(f'<details class="sheet" {"open" if num == "S-101" else ""}><summary><b>{num}</b> {E(ttl)}</summary>{svg}</details>')
        w("</div>")
        w('<h2 class="kicker">Build set <span class="tag">T-400 series · goes in · how · check</span></h2>')
        w(_steps(key, r["steps"], cap, False))
        w('<h2 class="kicker">3D model <span class="tag">drag to orbit · wheel or pinch to zoom · steps · exploded</span></h2>')
        w(viewer_html(S, None, title=f"{name} — 3D", standalone=False, uid=f"v3d-{key}"))
    w("</section>")
    section = "".join(o)
    lp_ = getattr(t, "lighting", None)            # the crew's numbers on the takeoff's cover: no prices
    n_r = sum(st.geo.risers for st in L.stairs)
    strip = ('<div class="strip">' + "".join(f'<div><span class="sl">{a}</span><span class="sv">{v}</span></div>' for a, v in (
        ("Square feet", f"{L.deck_sf:g}"), ("Height", ftin(spec.geometry.height_in)), ("Footings", n_piers), ("Rail", f"{L.rail.rail_lf:g} LF" if L.rail else "none"),
        ("Stair risers", n_r or "none"), ("Lights", lp_.fixtures) if getattr(lp_, "fixtures", 0) else ("Order lines", sum(1 for l in t.lines if l.category != "Site")))) + "</div>")
    if proposal:
        who = ("Prepared for " + spec.client if spec.client else "Prepared for the owner") + (f" · {addr}" if addr else "")
        head = PL.pp_cover(spec, key, V["cover"], CAP, name, who, today)
        body = head + '<main class="pdoc">' + section + "</main>"
        title = f"{name} — Proposal"
    elif customer:
        who = ("Prepared for " + spec.client if spec.client else "Prepared for the owner") + (f" · {addr}" if addr else "")
        head = PL.cover(spec, L, sm, p, key, hero, have, name, who, lede, today, n_piers, t=t)
        body = head + '<main class="wrap">' + section + f'<footer><span>{E(PL.brand_footer(spec))}</span><span>{E(CLIENT_FOOT)} {E(holds)}</span></footer></main>'
        title = f"{name} — Proposal"
    elif supplier:
        strip = ('<div class="strip n4"><div><span class="sl">Square feet</span><span class="sv">%g</span></div><div><span class="sl">Footings</span><span class="sv">%d</span></div>'
                 '<div><span class="sl">Order lines</span><span class="sv">%d</span></div><div><span class="sl">Height</span><span class="sv">%s</span></div></div>'
                 % (L.deck_sf, n_piers, sum(1 for l in t.lines if l.category != "Site"), ftin(spec.geometry.height_in)))
        head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · take-off + build set for Decks &amp; Docks</div>{_h1(name)}'
                f'<p>{E(sub or addr)} · {E(today)}</p><p>Account GSEXT1 · ship to {E(addr)} · please quote every line; call Jade Pender 303-550-9558 with substitutions.</p></div></header>')
        body = head + '<main class="wrap">' + strip + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Quantities from the drawings' + ("; the stamped engineering set governs structure" if spec.extras.engineered else "") + '. Quote requested — no pricing on this sheet.</span></footer></main>'
        title = f"{name} — Decks & Docks Take-off + Build Set"
    else:
        head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · takeoff + build set</div>{_h1(name)}'
                f'<p>{E(sub or addr)}</p></div></header>')
        body = head + '<main class="wrap">' + strip + section + '<footer><span>GS Exterior Experts · Deck Division</span><span>Takeoff + build set: quantities, drawings and build steps; no pricing (the cost stack carries it). Internal — not for the homeowner.</span></footer></main>'
        title = f"{name} — Takeoff + Build Set"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>{FONT}{CSS}"
            + ((PL.FONT + PL.CSS + PL.brand_css(spec)) if customer else "") + (LEVELS_CSS if hasattr(L, "parts") else "")     # Saira for the headings (owner)
            + (PL.OPTIONS_CSS if customer and (viewer_url is not None or any(isinstance(o_, dict) for o_ in (options or []))) else "")
            + (PL.TIMELINE_CSS if proposal else "") + (PL.CONFIRM_CSS if proposal and getattr(spec.extras, "confirm", None) else "")
            + (PL.PP_CSS if proposal else "")
            + "</head>" + ('<body class="proposal pp">' if proposal else '<body class="proposal">' if customer else "<body>")
            + body + CDN + "<script>window.addEventListener('load', function(){ window.dispatchEvent(new Event('resize')); });</script>" + (PL.JS if customer else "") + "</body></html>\n")
    # the viewer inlines its own CDN tag: keep one, hoist the viewer script after it
    page = page.replace(CDN, "", 1)
    scripts = re.findall(r"<script>\n\(function\(\)\{\nconst D = .*?\n\}\)\(\);\n</script>", page, flags=re.S)
    for sc in scripts:
        page = page.replace(sc, "", 1)
    page = page.replace(CDN, CDN + "\n" + "\n".join(scripts) + "\n", 1)
    if not customer:                         # the internal documents: page margins, a running footer, page breaks (DOC_CSS)
        page = page.replace("</head>", DOC_CSS + _doc_page_css(f"GS Exterior Experts · {_foot(name)} · " + ("Decks & Docks take-off · account GSEXT1" if supplier else "Takeoff + Build Set")
                                                               + f" · {today}") + "</head>", 1).replace("<body>", '<body class="doc">', 1)
        txt = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
        for bad in ("$", "Check or ACH", "Financed", "Gross profit", "rate card") + (("margin", "Margin") if supplier else ()):
            assert bad not in txt, f"{'supplier sheet' if supplier else 'takeoff + build set'} carries pricing wording: {bad}"
    if customer:
        txt = re.sub(r"<script.*?</script>", "", page, flags=re.S)
        txt = re.sub(r"data:[a-z]+/[a-z+.-]+;base64,[A-Za-z0-9+/=]+", "", txt)     # an embedded logo's bytes are not words
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


def _roof_plan_svg(L, q, size=None) -> str:
    """Plan (house at the top, the yard below): every deck zone shaded by its level, the house walls, the roof's frame
    hatched with its posts, the size (size = (W, D, SF) as sold; default the frame as built) and the level heights. Feet are
    the drawing units."""
    sW, sD, sA = size or (q["W"], q["D"], q["area"])
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
    s.append(f'<text x="{cx:.2f}" y="{cy + 1.05:.2f}" text-anchor="middle" font-size="0.95" fill="#3a352d" {f}>{E(ftin(sW * 12))} x {E(ftin(sD * 12))} · {sA:g} SF</text>')
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
    renders, words, label, open_note) (price overrides the engine's estimate; words default to the engine's screens; open_note
    says why an open side stays open), facts {section: [lines]} over PL.LOUVER_FACTS, schedule [lines], exclusions [lines],
    deck_note (a line on the deck the roof goes on). Returns {"html", "files", "pdf"?, "pricing"}."""
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
    # the size as sold (the roof's x / y extents, what the price is per SF of); the frame as built (q) can differ by a post inset
    Wp, Dp, Ap = float(rp.get("width_ft") or q["W"]), float(rp.get("depth_ft") or q["D"]), float(rp.get("area_sf") or q["area"])
    facts = {k: list(v) for k, v in PL.LOUVER_FACTS.items()}
    facts.update(a.get("facts") or {})
    rd = Path(renders_dir) if renders_dir else out / "renders"
    have = {x.stem for x in rd.glob("*.jpg")} if rd.exists() else set()
    files = {f"r/{key}-{n_}.jpg": str(rd / f"{n_}.jpg") for n_ in have}
    CAP.clear(); CAP.update(CAP0)
    CAP.update(_caps_file(rd / "captions.json"))
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
    # the deck structure the roof needs (its own beams / columns / caissons, owner 27 Oct: the base is designed without the roof):
    # addon["deck_work"] = dict(label, price, note) — priced at the deck's margin, required with the roof, so it rides in the roof's price
    dw = a.get("deck_work") or {}
    dw_c, dw_f, dw_m = fixed_terms(spec, dw["price"]) if dw.get("price") else (0.0, 0.0, 0.0)
    if dw_c:
        c, f, m = c + dw_c, f + dw_f, m + dw_m
    # ---- cover
    title, eyebrow = PL._title_parts(name, spec.site.address)
    eyebrow = " · ".join(x for x in (eyebrow, ", ".join(x for x in (spec.site.city, spec.site.state) if x)) if x)
    rail_posts = sum(1 for pt in q["posts"] if pt["on_rail"])
    tele = [(f"{Ap:g}", "square feet"), (ftin(Wp * 12), "along the house"), (ftin(Dp * 12), "out from the house"),
            (ftin(q["clear_ft"] * 12), "clear under the beams"), (str(len(q["blades"])), "louver blades"), (str(len(q["posts"])), "posts on the deck")]
    prices = ([("Check or ACH", money(c), f"{(1 - c / f) * 100:.0f}% less than the financed price"), ("Financed price", money(f), "with approved credit"),
               ("Monthly", money(m), PL._fin_short())] if show_fin else [("Price · check or ACH", money(c), "")])
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
    head = PL.addon_cover(title, eyebrow, who, today, hero_html, tele, prices, chips, lede, mission=f"{q['brand']} {q['product']} · Proposal",
                          brand=PL.brand_of(spec))
    o = []; w = o.append
    w(f'<section class="job" id="job-{key}">')
    # ---- what it is
    w('<h2 class="kicker" id="g-what">What it is <span class="tag">' + E(f"{q['brand']} {q['product']}") + "</span></h2>")
    if facts.get("what"):
        w("<ul class='opt-scope'>" + "".join(f"<li>{E(x)}</li>" for x in facts["what"]) + "</ul>")
    w("<h3>This roof</h3><ul class='opt-scope'>" + "".join(f"<li>{E(x)}</li>" for x in _roof_scope(q, rp)) + "</ul>")
    # ---- controls, motor, gutters, lights (the product, with what it is: page 2 of the PDF)
    # the LED strip is the roof's when the roof carries it (louvered_roofs[i].lights); otherwise it is one of the maker's options
    groups = [("Controls and motor", facts.get("controls")), ("Gutters and drainage", facts.get("gutters")), ("Lights", facts.get("lights") if q["lights"] else None),
              (f"Options {q['brand']} offers", list(facts.get("accessories") or []) + ([] if q["lights"] else list(facts.get("lights_option") or [])))]
    groups = [(h_, v_) for h_, v_ in groups if v_]
    if groups:
        w('<h2 class="kicker" id="g-controls">Controls, gutters' + (", lights" if q["lights"] else "") + ' and options</h2><div class="facts-cols">'
          + "".join(f"<div><h3>{E(h_)}</h3><ul>" + "".join(f"<li>{E(x)}</li>" for x in v_) + "</ul></div>" for h_, v_ in groups) + "</div>")
    # ---- size and placement
    under = sorted({f"{b[0]} {b[1]}" for b in _plan_boxes(L) if min(q["x1"], b[3]) - max(q["x0"], b[2]) > 0.5 and min(q["y1"], b[5]) - max(q["y0"], b[4]) > 0.5})
    w('<h2 class="kicker pb" id="g-size">Size and placement <span class="tag">plan · house at the top</span></h2>')
    w(f'<figure class="plan-fig">{_roof_plan_svg(L, q, (Wp, Dp, Ap))}<figcaption>The roof (hatched) and its posts over the deck; the darker the deck, the higher the level.</figcaption></figure>')
    reads = [("Size", f"{ftin(Wp * 12)} along the house x {ftin(Dp * 12)} out from it, {Ap:g} SF"),
             ("Over", (" and ".join(dict.fromkeys(("the deck" if u.split(" ")[0] == "Deck" else "the " + u.rsplit(" ", 1)[0].lower()) for u in under)) if under else "the deck")
              + (f" — {ftin(q['z_deck'] * 12)} above grade" if q["z_deck"] else "")),
             ("House side", _house_side(q, short=True)),
             ("Height", f"top of the frame {ftin((q['z_top'] - q['z_deck']) * 12)} above the deck; {ftin(q['clear_ft'] * 12)} clear under the beams")]
    if a.get("deck_note"):
        reads.append(("The deck", a["deck_note"]))
    w('<dl class="reads levels">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in reads) + "</dl>")
    # ---- structure
    w('<h2 class="kicker" id="g-structure">Structure <span class="tag">how it stands</span></h2>')
    st = [("Posts", _us_words(f"{len(q['posts'])} {q['post'] * 12:g}x{q['post'] * 12:g} aluminum posts on base plates on the deck"
           + (f"; {'both are' if rail_posts == 2 else ('it is' if rail_posts == 1 else f'{rail_posts} are')} the rail post{'s' if rail_posts != 1 else ''} there — the rail panels bracket into {'them' if rail_posts != 1 else 'it'}" if rail_posts else ""))),
          ("Frame", f"{q['beam_label']} aluminum perimeter beams with the gutter built in" + (f"; {len(q['xs']) + len(q['ys'])} zone divider beam{'s' if len(q['xs']) + len(q['ys']) != 1 else ''}" if (q['xs'] or q['ys']) else "")),
          ("House side", _house_side(q))]
    over = _posts_over_columns(L, q)
    if over is not None:
        st.append(("Under the posts", over))
    st += [(k, v) for k, v in (facts.get("structure_rows") or [])]
    w('<dl class="reads levels">' + "".join(f"<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>" for k, v in st) + "</dl>")
    # ---- the screens add-on
    if has_screens:
        figs = _render_figs(dict(renders=sa.get("renders") or sorted(n_ for n_ in have if n_.startswith("screens-")), renders_dir=sa.get("renders_dir") or str(rd)),
                            rd, key, "screens", files)
        words = sa.get("words") or _screen_lines(q, sa.get("open_note")) or ([x["words"] for x in scr] if scr else [])
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
    rows = [(f"{q['brand']} {q['product']} — {ftin(Wp * 12)} x {ftin(Dp * 12)}", c - dw_c, f - dw_f, m - dw_m, "item")]
    if dw_c:
        rows.append((dw.get("label") or "The deck structure for the roof", dw_c, dw_f, dw_m, "item"))
        rows.append(("The roof, with its deck structure", c, f, m, "total"))
    if has_screens:
        rows.append((sa.get("label") or "Motorized screens", sc_c, sc_f, sc_m, "addon"))
        tf = f + sc_f
        from .pricing import _monthly
        rows.append(("The roof with the screens", c + sc_c, tf, _monthly(tf), "total"))
    terms = ["This is a fixed-price proposal on the selections above. The check or ACH price applies to payment by check or ACH"
             + ("; the financed price applies with approved credit" if show_fin else "") + f". This price holds through {price_holds_through(today)}.",
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
    body = head + '<main class="wrap">' + "".join(o) + (f'<footer><span>{E(PL.brand_footer(spec))}</span><span>Renders show the design. '
                                                       f'{E(q["brand"])} product details per the manufacturer. This price holds through {E(price_holds_through(today))}.</span></footer></main>')
    title_ = f"{name} — Proposal"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title_)}</title>{FONT}{CSS}"
            + PL.FONT + PL.CSS + PL.brand_css(spec) + LEVELS_CSS + PL.OPTIONS_CSS + "</head><body class=\"proposal\">" + body + "</body></html>\n")
    txt = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    txt = re.sub(r"data:[a-z]+/[a-z+.-]+;base64,[A-Za-z0-9+/=]+", "", txt)        # an embedded logo's bytes are not words
    for bad in ("internal", "INTERNAL", "rate card", "cost stack", "GM", "ESTIMATE", "estimate"):
        assert bad not in txt, f"roof document carries internal wording: {bad}"
    (out / "page.html").write_text(page)
    json.dump(files, open(out / "files.json", "w"), indent=1)
    pr = dict(roof=dict(sell=c, financed=f, monthly=m, area_sf=Ap, basis=ap.basis),
              screens=dict(sell=sc_c, financed=sc_f, monthly=sc_m, estimate=sc_est) if has_screens else None)
    result = dict(html=str(out / "page.html"), files=files, pricing=pr, roof=q)
    if pdf:
        result["pdf"] = render_pdf(page, files, str(out / "page.pdf"), key, hero=hero)
    return result


def _roof_scope(q, rp: Optional[dict] = None) -> list:
    """The louvered engine's scope lines for the roof, with the size as sold (what the price per SF is of) where the engine
    quotes the frame as built (a post set on the rail line can make the frame a hair deeper)."""
    from .louvered import scope_words
    lines = scope_words(q)
    if rp and rp.get("area_sf") and abs(float(rp["area_sf"]) - float(q["area"])) > 0.01:
        built = f"{ftin(q['W'] * 12)} x {ftin(q['D'] * 12)} ({q['area']:g} SF)"
        sold = f"{ftin(float(rp['width_ft']) * 12)} x {ftin(float(rp['depth_ft']) * 12)} ({float(rp['area_sf']):g} SF)"
        lines = [x.replace(built, sold) for x in lines]
    return [_us_words(x) for x in lines]


_NUM_WORD = {"1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
# British spellings a job's own words (a color, a name, a note) can carry in, and the homeowner's American ones
_US_SPELL = {"centre": "center", "centres": "centers", "centred": "centered", "centring": "centering", "centreline": "centerline",
             "centrelines": "centerlines", "colour": "color", "colours": "colors", "coloured": "colored", "grey": "gray", "greys": "grays",
             "greyer": "grayer", "neighbour": "neighbor", "neighbours": "neighbors", "neighbouring": "neighboring", "metre": "meter",
             "metres": "meters", "litre": "liter", "litres": "liters", "mitre": "miter", "mitres": "miters", "mitred": "mitered",
             "mitring": "mitering", "aluminium": "aluminum", "fibre": "fiber", "fibres": "fibers", "storey": "story", "storeys": "stories",
             "towards": "toward"}
_US_RE = re.compile(r"\b(" + "|".join(_US_SPELL) + r")\b", re.I)


def _us_spell(m) -> str:
    """One British word in American spelling, its case kept ("Centre" -> "Center", "GREY" -> "GRAY")."""
    w = m.group(0)
    us = _US_SPELL[w.lower()]
    return us.upper() if w.isupper() else us.capitalize() if w[0].isupper() else us


def _us_words(x: str) -> str:
    """The homeowner's spelling of an engine line: US spellings ("centres" -> "centers", "grey" -> "gray", "round every" ->
    "around every"), and a line that would open on two numbers ("2 6x6 posts") opens on a word."""
    x = _US_RE.sub(_us_spell, x)
    x = re.sub(r"\bround (every|each)\b", r"around \1", x)
    return re.sub(r"^([1-9]) (?=\d)", lambda m: _NUM_WORD[m.group(1)] + " ", x)


def _house_side(q: dict, short: bool = False) -> str:
    """How the roof meets the house, by the louvered engine's house_mount: the roof line (flashed stand-offs on the existing
    roof, above the soffit), the wall under the soffit, or the fascia line. short: the size-and-placement read."""
    if q["attach"] != "house":
        return "freestanding, posts at every corner" if short else "posts at every corner"
    m = q.get("house_mount") or "roof"
    if short:
        return {"roof": "attached at the roof line, above the soffit — no posts at the house",
                "wall": "attached to the house wall under the soffit — no posts at the house",
                "fascia": "attached at the fascia line — no posts at the house"}.get(m, "attached to the house — no posts at the house")
    try:                                     # the louvered engine's own sentence for how this roof meets the house, when it has one
        from .louvered import scope_words
        hs = next((x[len("House side: "):] for x in scope_words(q) if x.startswith("House side: ")), "")
        if hs:
            hs = re.sub(r"\s+—\s+no posts at the house$", "", hs)
            return hs[0].lower() + hs[1:]
    except Exception:
        pass
    try:
        from .louvered import BRACKET_OC_FT
        oc = f" about every {BRACKET_OC_FT * 12:g}\""
    except Exception:
        oc = ""
    return {"roof": f"the house-side beam bears on flashed stand-off brackets{oc} on the existing roof over the wall line, each lagged into a rafter over solid blocking",
            "wall": "the house-side beam is carried on brackets on the house wall under the soffit",
            "fascia": "the house-side beam hangs at the fascia line"}.get(m, "the house-side beam is carried on brackets at the house")


def _screen_lines(q: dict, open_note=None) -> list:
    """The roof's screens in the homeowner's words, from the louvered engine's resolved screens (q["screens"]): where each
    runs and its size, the track post and fixed panel at the eave, the mesh and housing; then each open side of an attached
    roof (open_note: why — a string for every open side, or {side: words})."""
    scr = q.get("screens") or []
    if not scr:
        return []
    on_rail = any(p_.get("on_rail") for p_ in q["posts"])
    out = []
    for sc in scr:
        size = f"{ftin(sc['width'] * 12)} wide with a {ftin(sc['max_drop'] * 12)} drop"
        onto = "onto the deck" if abs(float(sc["z_bottom"]) - float(q["z_deck"])) < 0.1 else "to the level below"
        if sc["side"] == "front":
            where = ((("on the house side of the rail" if on_rail else "inside the posts") + (", between the two posts" if len(q["posts"]) == 2 else ""))
                     if sc["mount"] == "inside" else "outside the front beam")
            txt = f"Front: one screen, {size}, {where}; it comes down {onto}"
        else:
            txt = (f"{sc['side'].capitalize()} end: {size}" + (", from the front post back to a slim track post at the eave" if sc.get("track_post") else "")
                   + f"; it comes down {onto}" + ("; a fixed screen panel closes the strip under the eave" if sc.get("fixed_panel") else ""))
        fab = "clear vinyl" if sc["fabric"] == "vinyl" else f"{str(sc['color']).lower()} mesh"
        out.append(f"{txt} — {fab}, {sc['housing'] * 12:g}\" housing")
    if q["attach"] == "house":
        have_ = {sc["side"] for sc in scr}
        for s_ in (x for x in ("front", "left", "right") if x not in have_):
            why = open_note.get(s_) if isinstance(open_note, dict) else open_note
            out.append(f"The {s_ if s_ == 'front' else s_ + ' end'} stays open" + (f": {why}" if why else ""))
    return out


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
    if m and 'class="proposal pp"' not in p:
        p = p[:m.start()] + f'<h2 class="kicker">3D model</h2><figure><img src="r/{key}-{hero}.jpg" alt="3D"><figcaption>The interactive 3D model lives at the online version of this document.</figcaption></figure>' + p[m.end():]
    p = p.replace("<details", "<details open").replace("</head>", PRINT_CSS + PL.PRINT_CSS + "</head>")
    (out / "_print.html").write_text(p)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1000, "height": 1300})
        pg.goto("file://" + str(out / "_print.html")); pg.wait_for_timeout(3000)
        pg.emulate_media(media="print")
        if 'class="proposal pp"' in p:       # the photo-led proposal: a page that runs long takes its tighter classes first
            pg.evaluate(PL.FIT_JS)
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
        built.append(dict(pt, t=t, p=p, L=t.layout, sm=t.summary, S=r["scene"], have=have, opts=opts, qmd=quote_markdown(t, p, date_line)))
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
        if sp_.framing.system == "steel":    # the quote reads a wood frame in the homeowner's words already (report.frame_words), as render_page
            frame_lite = (f"{b['sm']['joists']}; {b['sm']['rims']}; boxed steel beams"
                          + (("; joist tape on every joist, rim and beam" if b["L"].beam_lines else "; joist tape on every joist and rim") if sp_.framing.joist_tape else "") + ".")
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
    w(f'<p>Financed price, with approved credit: {E(PL._fin_short())}. Also available with approved credit: 12 or 18 months with no payments. '
      f'The check or ACH price is {(1 - sell / retail) * 100:.0f}% less than the financed price and applies to payment by check or ACH. Each deck can be done on its own at its own price.</p>')
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
    head = (f'<header class="cover"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · Proposal</div><h1>{E(name).replace(" · ", "&nbsp;· ")}</h1><p class="who">{E(who)}</p>'
            f'<div class="pricebar"><div><span class="l">Both decks · check or ACH</span><span class="v">{money(sell)}</span></div><div><span class="l">Financed price</span><span class="v">{money(retail)}</span><span class="s">with approved credit</span></div>'
            f'<div><span class="l">Monthly</span><span class="v">{money(monthly)}</span><span class="s">{E(PL._fin_short())}</span></div></div>'
            + (f'<img class="herofig" src="r/{hk}-{hero}.jpg" alt="rendering">' if hero in have0 else "")
            + (f'<p class="lede">{E(lede)}</p>' if lede else "") + "</div></header>")
    body = head + '<main class="wrap">' + section + f'<footer><span>GS Exterior Experts · Deck Division</span><span>{E(CLIENT_FOOT)} This price holds through {E(price_holds_through(today))}.</span></footer></main>'
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
@media print{.band{padding:0.35in 0.5in;} .wrap{padding:0 0.2in;} .sheet-page{break-after:page;page-break-after:always;margin:0;} .sheet-page svg{border:0;max-height:7.25in;margin:0 auto;}
  .solo .sheet-page h3{display:none;} .solo .sheet-page svg{max-height:7.6in;} .sheet-page:last-child{break-after:auto;page-break-after:auto;}
  .cover-list{break-after:page;page-break-after:always;} h2.kicker{margin-top:10px;} footer{display:none;}}
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
        L0 = t.layout if pi == 0 else L0         # the render sheets carry the first part's sheet band
        r = build_set(t, flags, str(out / f"buildset-{pi + 1}"), render=False, customer=True)   # no internal flags block on G-001
        r["sheets"] = list(r["sheets"]) + (__import__("decktakeoff.calcs", fromlist=["calc_sheets"]).calc_sheets(pt["spec"] if pt["calcs"] is True else pt["calcs"]) if pt.get("calcs") else [])   # structural calcs S-901… when the part asks: calcs=True or a calcs.Package (calcs agent)
        for num, ttl, svg in r["sheets"]:
            svg = re.sub(r"GS Exterior Experts · ([A-Z][a-z]+ \d{1,2}, \d{4}) · Rev 0", r"GSX · Jade Pender 303-550-9558 · \1 · Rev 0 · PERMIT SET", svg)
            svg = re.sub(r"<text[^>]*>(?:T-400|T-700)</text>\s*<text[^>]*>[^<]*</text>", "", svg)   # the build-set and takeoff sheets are not in a permit set
            svg = re.sub(r" — the cut list is on T-\d+", "", svg)                                  # nor is the cut list
            index.append((pt["title"], num, ttl))
            sheet_html.append(f'<div class="sheet-page" id="s-{pi + 1}-{num}"><h3>{E(pt["title"])} · {num} · {E(ttl)}</h3>{svg}</div>')
    w(f'<section class="job{" solo" if len(parts) == 1 else ""}" id="job-{key}">')
    n_v = sum(len(v) for v in (renders or {}).values())
    if renders:
        index.append((parts[0]["title"], "A-001" if n_v == 1 else f"A-001.1–.{n_v}", f"Isometric · renders ({n_v} 3D view{'s' if n_v != 1 else ''}, design intent)"))
    w('<div class="cover-list"><h2 class="kicker" id="g-index">Sheet index</h2><ol class="index">' + "".join(f"<li>{E(a)} · <b>{b}</b> {E(c)}</li>" for a, b, c in index) + "</ol>")
    eng_any = any(pt_["spec"].extras.engineered for pt_ in parts) and not no_engineering
    w('<p>' + ("Design intent. The stamped engineering set governs structure, dimensions and locations. " if eng_any else "Design intent per the 2021 IRC R507 prescriptive provisions. ")
      + 'Field verify. Do not scale. This set carries no pricing.</p></div>')
    w("".join(sheet_html))
    if renders:
        # the 3D views as sheets A-001.1, .2 …: one view to a landscape page, with the drawing sheets' band and footer
        from .drawings import sheet as _sheet, sheet_meta
        meta, k = sheet_meta(L0, customer=True), 0
        w('<span id="g-views"></span>')
        for gi, (ttl, items) in enumerate(renders.items()):
            for cap, path in items:
                k += 1
                fn = f"r/{key}-{Path(path).stem}.jpg" if len(renders) == 1 else f"r/{key}{gi + 1}-{Path(path).stem}.jpg"   # one file per deck
                files[fn] = str(Path(path).resolve())
                num = "A-001" if n_v == 1 else f"A-001.{k}"
                svg = _sheet(num, "Isometric · renders", f"{cap} · 3D view of the model, design intent · {k} of {n_v}",
                             [f'<image href="{E(fn)}" x="18" y="6" width="964" height="600" preserveAspectRatio="xMidYMid meet"/>'],
                             "3D view · design intent · not to scale · the drawing sheets govern", meta)
                svg = re.sub(r"GS Exterior Experts · ([A-Z][a-z]+ \d{1,2}, \d{4}) · Rev 0", r"GSX · Jade Pender 303-550-9558 · \1 · Rev 0 · PERMIT SET", svg)
                w(f'<div class="sheet-page" id="s-r{k}"><h3>{E(parts[0]["title"] if len(renders) == 1 and len(parts) == 1 else ttl)} · {num} · Isometric · renders</h3>{svg}</div>')
    w("</section>")
    head = (f'<header class="band"><div class="in"><div class="kick">GS Exterior Experts · Deck Division · permit set</div><h1>{E(name).replace(" · ", "&nbsp;· ")}</h1>'
            f'<p>{E(sub or addr)} · {E(today)}</p></div></header>')
    body = head + '<main class="wrap">' + "".join(o) + '<footer><span>GS Exterior Experts · Deck Division · Jade Pender 303-550-9558</span><span>Permit set — drawings only. ' + ("Design intent; the stamped engineering set governs." if eng_any else "Design intent; 2021 IRC R507 prescriptive.") + '</span></footer></main>'
    title = f"{name} — Permit Set"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>{FONT}{CSS}{PERMIT_CSS}"
            + "<style>@media print { " + _page_box("", "Letter landscape", "0.35in 0.3in 0.55in", f"{_foot(name)} · permit set · {today}", "0", "#fbf9f4", important=False)
            + " }</style></head><body>"
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
