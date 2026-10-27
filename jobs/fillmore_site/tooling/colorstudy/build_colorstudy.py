#!/usr/bin/env python3
"""Exterior Color Study, 7303 S Fillmore Cir (client document, GS Exterior Experts look; separate from the proposal).
Reads the renders made by render_palettes.py (three.js, renders/<palette>/{yard,corner,upper}.jpg) and cycles_all.sh
(photoreal, cycles/<palette>/yard.jpg, cycles/{charcoal,recommended}_up/upper_deck.jpg); writes page.html + r/ + files.json
and the Letter PDF.     python3 build_colorstudy.py [--no-pdf]"""
import html
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "/home/user/Decks-")
from decktakeoff import page as PG                      # noqa: E402
from decktakeoff import proposal_look as PL             # noqa: E402

E = html.escape
CS = Path(__file__).resolve().parent.parent
R3, RC, RO = CS / "renders", CS / "cycles", CS / "r"
ADDRESS = "7303 S Fillmore Cir"
TITLE = f"Exterior Color Study · {ADDRESS}"
PDF_NAME = f"{ADDRESS} - Exterior Color Study.pdf"
TODAY = date.today().strftime("%B %d, %Y").replace(" 0", " ")

# ---------------------------------------------------------------- the colors (Sherwin-Williams values from sherwin-williams.com)
SW = {
    "peppercorn": dict(name="Peppercorn", code="SW 7674", hex="#585858", lrv=10),
    "iron_ore": dict(name="Iron Ore", code="SW 7069", hex="#434341", lrv=6),
    "tricorn": dict(name="Tricorn Black", code="SW 6258", hex="#2F2F30", lrv=3),
}
DECK = {   # TimberTech Vintage board tones: the GSX board catalog (timbertech-boards skill), mid tone of the render palette
    "English Walnut": dict(hex="#634E3E", img="cs-board-english-walnut.jpg"),
    "Mahogany": dict(hex="#8E654E", img="cs-board-mahogany.jpg"),
}
BODY_WHERE = "Siding, brick, foundation strip"
TRIM_WHERE = "Casings, corner boards, bands, fascia, gutters, downspouts, soffits"
PALETTES = [
    dict(key="gray", n="Palette 1", title="Dark gray", body="peppercorn", trim="tricorn", deck="English Walnut",
         blurb="A dark neutral gray body with black trim. Of the three, it is the lightest: the siding grooves, the brick coursing "
               "and the black trim, fascia and rail stand out against the walls."),
    dict(key="charcoal", n="Palette 2", title="Charcoal", body="iron_ore", trim="tricorn", deck="English Walnut",
         blurb="A charcoal body, close to black from the yard, with black trim one step darker. The black rail and trim read as "
               "outlines against the walls."),
    dict(key="black", n="Palette 3", title="Black", body="tricorn", trim="tricorn", deck="English Walnut",
         blurb="One black on every painted surface: siding, brick, trim, fascia, gutters and soffits. The black rail and the trim "
               "blend into the walls; the almond window frames and the deck boards are the contrast."),
]
REC = dict(key="recommended", n="Recommended", title="Charcoal with a Mahogany deck", body="iron_ore", trim="tricorn", deck="Mahogany")
CAP = {
    "yard": "From the yard, in front of the lower level",
    "corner": "From the front corner",
    "upper": "On the upper level, looking back over the lower level",
}
PHOTO = "photoreal render, June 21, 10:30 AM"
MODEL = "3D model"


def chip(color, label, name, sub, where=None, img=None):
    sw = f'<i class="sw" style="background:{color}"></i>' if not img else f'<i class="sw img" style="background:{color} url(r/{img}) center/cover"></i>'
    return (f'<div class="pchip">{sw}<div class="pt"><b>{E(label)}</b><span class="pn">{E(name)}</span><span class="pc">{sub}</span>'
            + (f'<span class="pw">{E(where)}</span>' if where else "") + "</div></div>")


def paint_chip(label, k, where):
    c = SW[k]
    return chip(c["hex"], label, f'{c["name"]}', f'{E(c["code"])} · {c["hex"]} · LRV {c["lrv"]}', where)


def deck_chip(name, note):
    d = DECK[name]
    return chip(d["hex"], "Deck boards", f"TimberTech Vintage · {name}", f"board tone ≈ {d['hex']} · {E(note)}",
                "Field, picture frame, fascia, stair treads and risers", img=d["img"])


RAIL_CHIP = chip("#141416", "Rail", "IRX Baluster · Black", "black powder-coated aluminum", "As proposed")


def chips(p, deck_note):
    one = p["body"] == p["trim"]
    out = [paint_chip("Body and trim" if one else "Body", p["body"], "Every painted surface" if one else BODY_WHERE)]
    if not one:
        out.append(paint_chip("Trim", p["trim"], TRIM_WHERE))
    out += [deck_chip(p["deck"], deck_note), RAIL_CHIP]
    return '<div class="pchips">' + "".join(out) + "</div>"


def fig(src, cap, cls=""):
    return f'<figure class="{cls}"><img src="r/{src}" alt="{E(cap)}" loading="lazy"><figcaption>{E(cap)}</figcaption></figure>'


def copy_img(src: Path, name: str, files: dict) -> str:
    RO.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, RO / name)
    files[f"r/{name}"] = str(RO / name)
    return name


def views(key, files):
    """(name, caption) of the palette's three views: yard (photoreal when rendered, else the 3D model), corner, upper."""
    out = []
    cy = RC / key / "yard.jpg"
    if cy.exists():
        out.append((copy_img(cy, f"cs-{key}-yard.jpg", files), f"{CAP['yard']} · {PHOTO}"))
    else:
        out.append((copy_img(R3 / key / "yard.jpg", f"cs-{key}-yard.jpg", files), f"{CAP['yard']} · {MODEL}"))
    for v in ("corner", "upper"):
        out.append((copy_img(R3 / key / f"{v}.jpg", f"cs-{key}-{v}.jpg", files), f"{CAP[v]} · {MODEL}"))
    return out


def view_block(vs):
    (a, ca), (b, cb), (c, cc) = vs
    return f'<div class="views">{fig(a, ca, "big")}<div class="gal">{fig(b, cb)}{fig(c, cc)}</div></div>'


EXTRA_CSS = """<style>
.pchips { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; }
.pchip { display:flex; flex-direction:column; gap:8px; min-width:0; }
.pchip .sw { display:block; height:64px; border-radius:3px; border:1px solid var(--line); -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.pchip .pt { display:flex; flex-direction:column; gap:1px; min-width:0; }
.pchip b { font-family:var(--display); font-weight:600; font-size:11px; letter-spacing:.22em; text-transform:uppercase; color:var(--ink-3); }
.pchip .pn { font-weight:800; font-size:15px; line-height:1.25; }
.pchip .pc { font-size:12.5px; color:var(--ink-2); font-variant-numeric:tabular-nums; }
.pchip .pw { font-size:12px; color:var(--ink-3); line-height:1.35; margin-top:2px; }
.views { display:flex; flex-direction:column; gap:10px; }
.views .gal { gap:10px; }
.opt-title .eyebrow { font-size:12px; }
.palstrip { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); border-top:1px solid var(--space-line); }
.palstrip > div { display:flex; flex-direction:column; gap:8px; padding:14px 12px 0 0; min-width:0; }
.palstrip > div + div { padding-left:14px; border-left:1px solid var(--space-line); }
.palstrip .sws { display:flex; gap:4px; }
.palstrip .sws i { display:block; height:30px; flex:1 1 0; border-radius:2px; border:1px solid rgba(244,242,236,.28); -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.palstrip .sws i.d { flex:0 0 30%; }
.palstrip .tl { color:var(--gold-b); }
.palstrip .pv2 { font-family:var(--display); font-weight:700; font-size:19px; line-height:1.05; color:#fff; }
.palstrip .ps { font-size:12px; color:var(--space-mute); line-height:1.35; }
.glance { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px; }
.glance figure img { aspect-ratio:1100/708; object-fit:cover; }
.glance figcaption b { color:var(--ink); font-weight:800; }
.legend2 { display:flex; flex-direction:column; gap:10px; padding:4px 0 0; }
.legend2 .row { display:grid; grid-template-columns:repeat(3, 26px) minmax(0, 1fr); gap:6px; align-items:center; font-size:13.5px; }
.legend2 .row i { display:block; height:26px; border-radius:2px; border:1px solid var(--line); -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.legend2 .row span b { font-weight:800; }
.why { margin:0; padding-left:18px; display:flex; flex-direction:column; gap:5px; font-size:15px; }
.compare { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px; }
.compare figure img { aspect-ratio:1100/708; object-fit:cover; }
.fine2 { color:var(--ink-3); font-size:13px; margin:0; max-width:80ch; }
.facts-cols p { margin:4px 0; }
@media (max-width:760px) {
  .pchips { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .palstrip { grid-template-columns:repeat(2, minmax(0, 1fr)); row-gap:14px; }
  .palstrip > div:nth-child(3) { padding-left:0; border-left:0; }
  .glance, .compare { grid-template-columns:1fr; }
}
</style>"""

PRINT_EXTRA = """<style>
@page { size:Letter; margin:0.42in 0 0.38in; }
@page :first { margin:0; }
body.proposal .manifest { height:11in; }
body.proposal .hero .hero-img { height:6.75in; }
body.proposal .launch .hin { gap:14px; }
body.proposal .launch .lede { font-size:12.5px; }
.wrap { padding:0 0.5in 0; }
h2.kicker { margin-top:4px; }
.pagebreak { break-before:page; page-break-before:always; }
.optblock { margin-top:0; }
.opt-head { padding:12px 0.18in; }
.opt-head h3 { font-size:28px; }
.opt-body { padding:12px 0.18in 0; gap:10px; }
.opt-blurb, .why { font-size:12.5px; line-height:1.45; }
.pchip .sw { height:0.55in; }
.pchip .pn { font-size:12.5px; } .pchip .pc { font-size:10.5px; } .pchip .pw { font-size:10px; } .pchip b { font-size:9.5px; }
.views .big img { height:4.3in; object-fit:cover; }
.views .gal figure img { height:2.42in; object-fit:cover; }
figcaption { font-size:10px; margin-top:2px; }
.glance { gap:10px; } .glance figure img { height:2.38in; }
.legend2 .row { font-size:11.5px; }
.facts-cols { font-size:12px; } .facts-cols h3 { font-size:13px; margin-top:8px; }
.compare figure img { height:2.38in; object-fit:cover; }
.fine2 { font-size:10.5px; }
footer { margin-top:16px; padding-bottom:0; font-size:10px; }
.palstrip .pv2 { font-size:16px; } .palstrip .ps { font-size:10.5px; } .palstrip .sws i { height:0.32in; }
</style>"""


def main(argv):
    files = {}
    for nm in ("cs-board-english-walnut.jpg", "cs-board-mahogany.jpg"):
        files[f"r/{nm}"] = str(RO / nm)
    pal_views = {p["key"]: views(p["key"], files) for p in PALETTES + [REC]}
    today = None
    if (RC / "existing" / "yard.jpg").exists():
        today = (copy_img(RC / "existing" / "yard.jpg", "cs-today-yard.jpg", files), f"{CAP['yard']} · {PHOTO}")
    else:
        today = (copy_img(R3 / "existing" / "yard.jpg", "cs-today-yard.jpg", files), f"{CAP['yard']} · {MODEL}")
    up = {}
    for k, nm in (("charcoal_up", "English Walnut"), ("recommended_up", "Mahogany")):
        q = RC / k / "upper_deck.jpg"
        src = q if q.exists() else R3 / ("charcoal" if k.startswith("charcoal") else "recommended") / "upper.jpg"
        up[nm] = (copy_img(src, f"cs-deck-{nm.lower().replace(' ', '-')}-upper.jpg", files),
                  f"{CAP['upper']} · {PHOTO if q.exists() else MODEL}")
    hero = pal_views["recommended"][0][0]

    o = []; w = o.append
    w("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>")
    w(f"<title>{E(TITLE)}</title>")
    w(PG.FONT + PL.FONT + PG.CSS + PL.CSS + PL.OPTIONS_CSS + EXTRA_CSS + "</head>")
    w('<body class="proposal">')
    # ------------------------------------------------------------ cover
    w('<header class="manifest"><div class="hero">')
    w(f'<img class="hero-img" src="r/{hero}" alt="Rendering of the house in charcoal with the new deck in Mahogany">')
    w('<div class="hero-shade"></div><div class="hero-top"><div class="hin">' + PL.logo_svg()
      + f'<span class="mission">Exterior Color Study<br>{E(TODAY)}</span></div></div>')
    w('<div class="hero-title"><div class="hin"><span class="eyebrow">Exterior Color Study · Centennial, CO</span>'
      f'<h1>{E(ADDRESS)}</h1><p class="who">Prepared for Andie Jones · 7303 S Fillmore Cir, Centennial, CO 80122</p></div></div></div>')
    w('<div class="launch"><div class="hin"><div class="palstrip">')
    for p in PALETTES + [REC]:
        b, t = SW[p["body"]], SW[p["trim"]]
        nm = "Recommended" if p is REC else p["title"]
        sub = (f'{b["code"]} {b["name"]} + {t["name"]} trim · Vintage Mahogany deck' if p is REC else
               (f'{b["code"]} {b["name"]}' + ("" if p["body"] == p["trim"] else f' · {t["name"]} trim')))
        w(f'<div><div class="sws"><i style="background:{b["hex"]}"></i><i style="background:{t["hex"]}"></i>'
          f'<i class="d" style="background:{DECK[p["deck"]]["hex"]}"></i></div><span class="tl">{E(p["n"] if p is not REC else "Our pick")}</span>'
          f'<span class="pv2">{E(nm)}</span><span class="ps">{E(sub)}</span></div>')
    w("</div>")
    w('<p class="lede">Three dark exterior palettes for the house with the new deck: dark gray, charcoal and black, in '
      'Sherwin-Williams colors. Each palette has its paint chips and renders from the yard, the front corner and the upper deck. '
      'The last section is the palette we recommend: charcoal, with the deck boards in TimberTech Vintage Mahogany instead of '
      'English Walnut. The cover shows it. Painting is not part of the GS Exterior Experts deck proposal; this study is for '
      'choosing colors.</p>')
    w("</div></div></header>")
    w('<main class="wrap">')
    # ------------------------------------------------------------ at a glance
    w('<h2 class="kicker" id="g-glance">At a glance <span class="tag">the same view in every palette</span></h2>')
    w('<div class="glance">')
    w(f'<figure><img src="r/{today[0]}" alt="Today"><figcaption><b>Today\'s colors</b>, with the new deck · {E(today[1])}</figcaption></figure>')
    for p in PALETTES + [REC]:
        v = pal_views[p["key"]][0]
        w(f'<figure><img src="r/{v[0]}" alt="{E(p["title"])}"><figcaption><b>{E(p["n"] + " · " + p["title"] if p is not REC else "Recommended · " + p["title"])}</b> · {E(v[1])}</figcaption></figure>')
    w('<div class="legend2" aria-label="The palettes">')
    for p in PALETTES + [REC]:
        b, t = SW[p["body"]], SW[p["trim"]]
        w(f'<div class="row"><i style="background:{b["hex"]}"></i><i style="background:{t["hex"]}"></i><i style="background:{DECK[p["deck"]]["hex"]}"></i>'
          f'<span><b>{E(p["n"] if p is not REC else "Recommended")} · {E(p["title"])}</b> — body {E(b["code"] + " " + b["name"])}, '
          f'trim {E(t["code"] + " " + t["name"])}, deck TimberTech Vintage {E(p["deck"])}</span></div>')
    w("</div>")
    w("</div>")
    # ------------------------------------------------------------ what gets painted
    w('<h2 class="kicker pagebreak" id="g-painted">What gets painted <span class="tag">the same in every palette</span></h2>')
    w('<div class="facts-cols">')
    w("<div><h3>Body color</h3><ul><li>The vertical-groove wood siding on every wall (today a red-brown stain)</li>"
      "<li>The brick veneer: the walk-out level, the chimney and the wall at the arm end (today buff brick)</li>"
      "<li>The foundation strip below the siding</li></ul></div>")
    w("<div><h3>Trim color</h3><ul><li>Window and door casings and corner boards</li>"
      "<li>The trim bands at the sill and floor lines, the dentil band over the brick and the accent panel at the family-room slider (today maroon)</li>"
      "<li>Fascia, gutters and downspouts</li><li>The box soffits under the eaves</li></ul></div>")
    w("<div><h3>The brick: painted to match</h3><p>The brick takes the body color, so the walk-out level and the siding above "
      "it read as one color. Limewash was the other option: it is a thin lime coat that lets the brick show through in patches, "
      "so the brick would not match the solid siding color. Painted brick needs a masonry paint, and it does not easily go back "
      "to bare brick.</p></div>")
    w("<div><h3>Not painted</h3><ul><li>The roof shingles</li><li>The almond vinyl window and slider frames</li>"
      "<li>The concrete patio</li><li>The new deck as proposed: TimberTech boards, the black IRX rail, the posts and beams</li></ul></div>")
    w("</div>")
    w('<h3>Reading the chips</h3><ul class="opt-scope">'
      "<li>Every paint is a Sherwin-Williams color, with its color number and the hex value Sherwin-Williams publishes for it</li>"
      "<li>LRV (light reflectance value) is the share of light a color reflects, from 0 (black) to 100 (white). A lower LRV is "
      "darker and absorbs more of the sun's heat</li>"
      "<li>The back of the house faces north-northeast: it gets direct sun only on summer mornings (on June 21, until about 10:50 AM). "
      "The photoreal renders are at 10:30 AM on June 21, with the sun raking across the back</li>"
      "<li>The deck chip is the TimberTech board, rendered; its tone is approximate</li>"
      "<li>Screens and paper do not show paint exactly. Look at painted samples on the house, in sun and in shade, before choosing</li></ul>")
    w('<h3>Before choosing</h3><ul class="opt-scope">'
      "<li>Ask the Tiffany HOA whether a color change needs its approval; if it does, the paint colors can go in with the deck request</li>"
      "<li>Put painted samples of the body and trim colors on the siding and on the brick, and hold the TimberTech samples against them</li>"
      "<li>Painting is by others: it is not part of the GS Exterior Experts deck proposal</li></ul>")
    # ------------------------------------------------------------ the palettes
    for i, p in enumerate(PALETTES):
        b = SW[p["body"]]
        w(f'<section class="optblock pagebreak" id="p-{p["key"]}"><div class="opt-head"><div class="opt-title">'
          f'<span class="eyebrow">{E(p["n"])}</span><h3>{E(p["title"])}</h3></div>'
          f'<span class="mission">{E(b["code"])} {E(b["name"])}</span></div><div class="opt-body">')
        w(f'<p class="opt-blurb">{E(p["blurb"])}</p>')
        w(chips(p, "as proposed"))
        w(view_block(pal_views[p["key"]]))
        w("</div></section>")
    # ------------------------------------------------------------ recommended
    b, t = SW[REC["body"]], SW[REC["trim"]]
    w(f'<section class="optblock pagebreak" id="p-recommended"><div class="opt-head"><div class="opt-title">'
      f'<span class="eyebrow">Recommended</span><h3>{E(REC["title"])}</h3></div>'
      f'<span class="mission">{E(b["code"])} {E(b["name"])}<br>{E(t["code"])} {E(t["name"])}</span></div><div class="opt-body">')
    w('<ul class="why">'
      f"<li>Iron Ore (LRV {b['lrv']}) is darker than Peppercorn (LRV {SW['peppercorn']['lrv']}) and lighter than Tricorn Black "
      f"(LRV {t['lrv']}): from the yard it reads near-black, and the siding grooves and the brick coursing still show</li>"
      "<li>The Tricorn Black trim, fascia and gutters are one step darker than the walls, so the windows and the roof edge stay outlined</li>"
      "<li>The black IRX rail stays visible against charcoal; on a black house it blends into the wall (Palette 3)</li>"
      f"<li>The deck in Vintage Mahogany (board tone ≈ {DECK['Mahogany']['hex']}) is lighter and warmer than English Walnut "
      f"(≈ {DECK['English Walnut']['hex']}), which is close to Iron Ore in darkness. Against the charcoal, the Mahogany boards, "
      "fascia and stairs read as wood</li>"
      "<li>Same TimberTech Vintage collection: the board size, fasteners and layout in the proposal stay the same. The HOA "
      "request would carry a Mahogany sample in place of English Walnut</li></ul>")
    w(chips(REC, "in place of English Walnut"))
    w(view_block(pal_views["recommended"]))
    w("</div></section>")
    w('<h2 class="kicker pagebreak" id="g-deck">The deck color <span class="tag">charcoal house, both boards, same view</span></h2>')
    w('<div class="compare">' + fig(up["English Walnut"][0], f"Vintage English Walnut (as proposed) · {up['English Walnut'][1]}")
      + fig(up["Mahogany"][0], f"Vintage Mahogany (recommended) · {up['Mahogany'][1]}")
      + fig(pal_views["charcoal"][0][0], f"Vintage English Walnut (as proposed) · {pal_views['charcoal'][0][1]}")
      + fig(pal_views["recommended"][0][0], f"Vintage Mahogany (recommended) · {pal_views['recommended'][0][1]}") + "</div>")
    w('<div class="facts-cols"><div><h3>What changes with Mahogany</h3><ul><li>Field boards, the picture frame and breaker boards</li>'
      "<li>The fascia over the rim joists and the step skirt between the levels</li><li>Stair treads and risers</li></ul></div>"
      "<div><h3>What stays the same</h3><ul><li>TimberTech Vintage square-shoulder boards and the same fasteners</li>"
      "<li>The black IRX rail, the framing, the stairs and every dimension in the proposal</li></ul></div></div>")
    w(f'<footer><span>{E(PL.brand_footer("gs"))}</span><span>Renders are design intent. Paint colors per Sherwin-Williams; board tones '
      "per the GSX TimberTech catalog. Colors on screen and paper differ from paint.</span></footer>")
    w("</main></body></html>")
    page = "".join(o)
    (CS / "page.html").write_text(page)
    json.dump(files, open(CS / "files.json", "w"), indent=1)
    print(f"page: {CS / 'page.html'} ({len(page) // 1024} KB, {len(files)} images)")
    if "--no-pdf" not in argv:
        print("pdf:", print_pdf(page, CS / PDF_NAME))


def print_pdf(page: str, pdf_path: Path) -> str:
    from decktakeoff.render import _chromium
    from playwright.sync_api import sync_playwright
    p = re.sub(r"<script.*?</script>", "", page, flags=re.S).replace(' loading="lazy"', "")
    p = p.replace("</head>", PG.PRINT_CSS + PL.PRINT_CSS + PRINT_EXTRA + "</head>")
    (CS / "_print.html").write_text(p)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1000, "height": 1300})
        pg.goto("file://" + str(CS / "_print.html")); pg.wait_for_timeout(2500)
        pg.emulate_media(media="print")
        pg.pdf(path=str(pdf_path), format="Letter", print_background=True, prefer_css_page_size=True)
        b.close()
    return str(pdf_path)


if __name__ == "__main__":
    main(sys.argv[1:])
