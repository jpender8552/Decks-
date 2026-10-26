"""The homeowner proposal's look: a full-bleed photoreal hero over deep black with the GS gold logo, a launch band of
the deck's numbers and the price, and the price wheel (every part of the price broken out on a donut). The rest of the
page keeps the shared styles; everything here is scoped to body.proposal."""
from __future__ import annotations

import html
import math
import re
from pathlib import Path

from .catalog import BOARDS_PALETTE, rail_name
from .units import ftin

E = html.escape

FONT = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Saira+Semi+Condensed:wght@400;500;600;700;800&display=swap">'

# categorical order for the wheel, validated on the black panel (adjacent pairs and the wrap back to the first slot):
# CVD separation >= 8.4, normal vision >= 19.3, every slot >= 3:1 against #050608
WHEEL = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]

RAIL_HEX = {"black": "#141414", "white": "#f1f0ea", "bronze": "#5a4632", "gray": "#7a7c7e", "grey": "#7a7c7e"}

CSS = """<style>
/* Launch manifest: the photoreal deck full-bleed over deep black, a condensed wide-tracked display face, the GS gold
   gradient as the one accent; the deck's numbers read like telemetry; the price wheel sits on a black panel. */
:root { --space:#050608; --space-line:rgba(244,242,236,.16); --space-ink:#f4f2ec; --space-mute:#a9a69e; --space-soft:#d9d6ce;
  --gold-a:#d49e1b; --gold-b:#ffe28d; --display:"Saira Semi Condensed", "Arial Narrow", "Nunito Sans", sans-serif; }
body.proposal .kicker { font-family:var(--display); font-weight:700; font-size:14px; letter-spacing:.24em; color:var(--ink); position:relative; }
body.proposal .kicker::after { content:""; position:absolute; left:0; bottom:-2px; width:44px; height:3px; background:linear-gradient(90deg, var(--gold-a), var(--gold-b)); }
body.proposal .kicker .tag { font-family:"Nunito Sans", system-ui, sans-serif; letter-spacing:.04em; }
.manifest { background:var(--space); color:var(--space-ink); }
.hero { position:relative; overflow:hidden; }
.hero .hero-img { display:block; width:100%; max-width:100%; height:clamp(340px, 54vw, 660px); object-fit:cover; object-position:50% 45%; border:0; }
.hero-shade { position:absolute; inset:0; background:linear-gradient(180deg, rgba(5,6,8,.84) 0%, rgba(5,6,8,.18) 17%, rgba(5,6,8,0) 36%, rgba(5,6,8,.3) 60%, rgba(5,6,8,.9) 88%, #050608 100%); }
.hero-top, .hero-title { position:absolute; left:0; right:0; }
.hero-top { top:0; } .hero-title { bottom:0; }
.hin { max-width:1040px; margin:0 auto; padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); }
.hero-top .hin { display:flex; align-items:center; justify-content:space-between; gap:16px; padding-block:20px; }
.gslogo { display:block; height:48px; width:auto; }
.mission { font-family:var(--display); font-weight:600; font-size:12px; letter-spacing:.32em; text-transform:uppercase; color:var(--space-ink); text-align:right; }
.hero-title .hin { display:flex; flex-direction:column; gap:10px; padding-block:0 22px; }
.eyebrow { font-family:var(--display); font-weight:600; font-size:13px; letter-spacing:.34em; text-transform:uppercase; color:var(--gold-b); }
.manifest h1 { font-family:var(--display); font-weight:800; text-transform:uppercase; letter-spacing:.02em; line-height:.9; font-size:clamp(40px, 8vw, 92px); margin:0; color:#ffffff; text-wrap:balance; }
.manifest .who { margin:0; font-size:14px; color:var(--space-mute); letter-spacing:.03em; }
.launch .hin { display:flex; flex-direction:column; gap:24px; padding-block:6px 40px; }
.telemetry { display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); border-top:1px solid var(--space-line); }
.telemetry > div { display:flex; flex-direction:column; gap:6px; padding:14px 12px 0 0; min-width:0; }
.telemetry > div + div { padding-left:14px; border-left:1px solid var(--space-line); }
.tv { font-family:var(--display); font-weight:700; font-size:clamp(22px, 3vw, 34px); line-height:1; color:#ffffff; font-variant-numeric:tabular-nums; white-space:nowrap; }
.tl { font-size:10.5px; letter-spacing:.2em; text-transform:uppercase; color:var(--space-mute); font-weight:700; }
.prices { display:grid; grid-template-columns:1.3fr 1fr 1fr; gap:1px; background:var(--space-line); border:1px solid var(--space-line); }
.prices.one { grid-template-columns:1fr; }
.prices > div { background:var(--space); padding:18px 20px; display:flex; flex-direction:column; gap:6px; min-width:0; }
.pl { font-family:var(--display); font-weight:600; font-size:12px; letter-spacing:.28em; text-transform:uppercase; color:var(--space-mute); }
.pv { font-family:var(--display); font-weight:800; font-size:clamp(30px, 4.4vw, 48px); line-height:1; color:#ffffff; font-variant-numeric:tabular-nums; }
.prices .lead .pv { background:linear-gradient(100deg, var(--gold-a) 0%, var(--gold-b) 55%, var(--gold-a) 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
.ps { font-size:12.5px; color:var(--space-mute); }
.chips { display:flex; flex-wrap:wrap; gap:12px 28px; }
.chip { display:flex; align-items:center; gap:12px; min-width:0; }
.chip i { flex:none; width:38px; height:24px; border-radius:2px; border:1px solid rgba(244,242,236,.3); display:block; }
.chip span { display:flex; flex-direction:column; gap:1px; font-size:14px; color:var(--space-ink); }
.chip b { font-family:var(--display); font-weight:600; font-size:11px; letter-spacing:.22em; text-transform:uppercase; color:var(--space-mute); }
.launch .lede { margin:0; max-width:72ch; font-size:16px; line-height:1.6; font-weight:300; color:var(--space-soft); }
.invest { background:var(--space); color:var(--space-ink); padding:30px clamp(16px, 4vw, 40px) 30px; margin-top:12px; display:flex; flex-direction:column; gap:24px; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.inv-head { display:flex; flex-direction:column; gap:8px; }
.inv-head h3 { font-family:var(--display); font-weight:800; font-size:clamp(26px, 4vw, 40px); text-transform:uppercase; letter-spacing:.02em; line-height:1; margin:0; color:#ffffff; }
.inv-grid { display:grid; grid-template-columns:minmax(0, 300px) minmax(0, 1fr); gap:32px; align-items:center; }
.wheel { margin:0; }
.wheel svg { display:block; width:100%; max-width:300px; height:auto; margin:0 auto; }
.wheel path { fill:none; stroke-width:30; }
.wheel .wc-v { font-family:var(--display); font-weight:800; font-size:30px; fill:#ffffff; }
.wheel .wc-l { font-family:"Nunito Sans", system-ui, sans-serif; font-weight:700; font-size:10px; letter-spacing:.2em; fill:#a9a69e; }
.inv-grid.hover .wheel path:not(.on) { opacity:.32; }
.inv-grid .wheel path.on { stroke-width:36; }
.legend { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; min-width:0; }
.legend li { display:grid; grid-template-columns:14px minmax(0, 1fr) auto 48px; gap:12px; align-items:center; padding:9px 6px; border-bottom:1px solid var(--space-line); font-size:14.5px; color:var(--space-ink); }
.legend li i { width:14px; height:14px; border-radius:3px; display:block; }
.legend .lv { font-family:var(--display); font-weight:700; font-size:17px; font-variant-numeric:tabular-nums; text-align:right; }
.legend .lp { color:var(--space-mute); text-align:right; font-size:13px; font-variant-numeric:tabular-nums; }
.legend li.on { background:rgba(244,242,236,.07); }
.legend li[tabindex]:focus-visible { outline:2px solid var(--gold-b); outline-offset:-2px; }
.legend li.total { border-bottom:0; font-weight:800; padding-top:12px; }
.legend li.total .lv { font-size:20px; }
.terms { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:1px; background:var(--space-line); border:1px solid var(--space-line); }
.terms.one { grid-template-columns:1fr; }
.invest .opts td:first-child { min-width:220px; }
.terms > div { background:var(--space); padding:14px 16px; display:flex; flex-direction:column; gap:4px; }
.terms .tv { font-size:24px; }
.terms .lead .tv { background:linear-gradient(100deg, var(--gold-a), var(--gold-b) 60%, var(--gold-a)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.invest h4 { font-family:var(--display); font-weight:700; font-size:13px; letter-spacing:.24em; text-transform:uppercase; color:var(--gold-b); margin:0 0 8px; }
.invest p { margin:0; max-width:70ch; color:var(--space-soft); }
.invest .opts table { color:var(--space-ink); }
.invest .opts th { color:var(--space-mute); border-bottom-color:rgba(244,242,236,.4); }
.invest .opts td { border-bottom-color:var(--space-line); }
.invest .opts h3 { display:none; }
@media (max-width:760px) {
  .telemetry { grid-template-columns:repeat(3, minmax(0, 1fr)); row-gap:16px; }
  .telemetry > div:nth-child(4) { padding-left:0; border-left:0; }
  .prices { grid-template-columns:1fr; }
  .terms { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .inv-grid { grid-template-columns:1fr; }
  .gslogo { height:36px; }
  .hero-title { position:relative; bottom:auto; margin-top:-64px; }
  .mission { letter-spacing:.2em; font-size:11px; }
}
@media (prefers-reduced-motion:no-preference) { .wheel path { transition:stroke-width .15s, opacity .15s; } }
</style>"""

PRINT_CSS = """<style>
body.proposal .manifest { height:11in; overflow:hidden; display:flex; flex-direction:column; break-after:page; page-break-after:always; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
body.proposal .hero .hero-img { height:5.9in; }
body.proposal .gslogo { height:0.62in; }
body.proposal .terms { grid-template-columns:repeat(4, minmax(0, 1fr)); }
body.proposal .hin { max-width:none; padding-left:0.6in; padding-right:0.6in; }
body.proposal .hero-top .hin { padding-block:0.32in 0; }
body.proposal .hero-title .hin { padding-block:0 0.12in; }
body.proposal .manifest h1 { font-size:66px; }
body.proposal .launch .hin { padding-block:0.06in 0.35in; gap:16px; }
body.proposal .tv { font-size:25px; }
body.proposal .pv { font-size:36px; }
body.proposal .prices > div { padding:12px 16px; }
body.proposal .launch .lede { font-size:11.5px; line-height:1.5; }
body.proposal .invest { break-before:page; page-break-before:always; break-inside:avoid; page-break-inside:avoid; }
body.proposal .legend li { padding:6px 4px; font-size:12.5px; }
</style>"""

JS = """<script>
document.querySelectorAll('.inv-grid').forEach(function (g) {
  var v = g.querySelector('.wc-v'), l = g.querySelector('.wc-l');
  if (!v || !l) return;
  var v0 = v.textContent, l0 = l.textContent;
  function show(k) {
    g.querySelectorAll('[data-k]').forEach(function (e) { e.classList.toggle('on', e.getAttribute('data-k') === k); });
    g.classList.toggle('hover', k !== null);
    var r = k === null ? null : g.querySelector('li[data-k="' + k + '"]');
    v.textContent = r ? r.getAttribute('data-v') : v0;
    l.textContent = r ? r.getAttribute('data-s') : l0;
  }
  g.querySelectorAll('[data-k]').forEach(function (e) {
    var k = e.getAttribute('data-k');
    e.addEventListener('mouseenter', function () { show(k); });
    e.addEventListener('mouseleave', function () { show(null); });
    e.addEventListener('focus', function () { show(k); });
    e.addEventListener('blur', function () { show(null); });
  });
});
</script>"""


def money(v):
    return f"${v:,.0f}"


def logo_svg(height_class: str = "gslogo") -> str:
    """The GS Exterior Experts reversed gradient logo, inline (its gradient id made unique on the page)."""
    p = Path(__file__).with_name("data") / "gs-logo-reversed.svg"
    if not p.exists():
        return '<span class="mission">GS Exterior Experts</span>'
    s = p.read_text()
    s = re.sub(r"<\?xml[^>]*\?>\s*", "", s)
    s = s.replace('id="linear-gradient"', 'id="gsxLogoGrad"').replace("url(#linear-gradient)", "url(#gsxLogoGrad)")
    s = s.replace('id="Layer_2"', "").replace('id="Layer_1-2"', "")
    s = s.replace(".cls-", ".gsx-").replace('class="cls-', 'class="gsx-')
    return s.replace("<svg ", f'<svg class="{height_class}" role="img" aria-label="GS Exterior Experts" ', 1)


def _title_parts(name: str, address: str):
    """'Deck Replacement · 19105 E Prentice Cir · White IRX option' -> ('19105 E Prentice Cir', 'Deck Replacement · White IRX option')."""
    if address and address in name:
        rest = [q.strip() for q in name.replace(address, "").split("·")]
        return address, " · ".join(q for q in rest if q)
    return name, ""


def cover(spec, L, sm, p, key, hero, have, name, who, lede, today, n_piers) -> str:
    """The launch manifest: hero render, title, the deck's numbers, the materials, the price."""
    title, eyebrow = _title_parts(name, spec.site.address)
    place = ", ".join(x for x in (spec.site.city, spec.site.state) if x)
    eyebrow = " · ".join(x for x in (eyebrow, place) if x)
    fr = L.zones[0].frame
    flush = all(b.kind == "flush" for b in (L.beam_lines or []))
    tele = [(f"{L.deck_sf:,.0f}", "square feet"), (ftin(L.finished_w), "across the house"), (ftin(spec.geometry.height_in), "above grade"),
            (spec.framing.joist_size, f"joists @ {fr.spacing:g}\" OC" + (", all flush" if flush else "")), (str(n_piers), "Diamond Piers")]
    rl = L.rail
    if rl:
        tele.append((f"{rl.rail_lf:g}'", f"{rl.color.lower()} rail"))
    elif L.stairs:
        tele.append((str(sum(st.geo.risers for st in L.stairs)), "risers"))
    pal = BOARDS_PALETTE.get((spec.decking.collection, spec.decking.color))
    chips = [(pal[len(pal) // 2] if pal else "#73624a", "Decking", f"{spec.decking.brand} {spec.decking.collection} · {spec.decking.color}")]
    if spec.decking.border_color and spec.decking.border_color != spec.decking.color:
        bp = BOARDS_PALETTE.get((spec.decking.border_collection or spec.decking.collection, spec.decking.border_color))
        chips.append((bp[len(bp) // 2] if bp else "#5a4632", "Picture frame", f"{spec.decking.border_collection or spec.decking.collection} · {spec.decking.border_color}"))
    if rl:
        chips.append((RAIL_HEX.get(rl.color.lower(), "#141414"), "Rail", f"{spec.decking.brand} {rail_name(rl.system)} · {rl.color}"))
    if spec.extras.show_financing:
        prices = (f'<div class="prices"><div class="lead"><span class="pl">Check or ACH</span><span class="pv">{money(p.sell)}</span><span class="ps">{(1 - p.sell / p.retail) * 100:.0f}% below the financed price</span></div>'
                  f'<div><span class="pl">Financed</span><span class="pv">{money(p.retail)}</span><span class="ps">no money down</span></div>'
                  f'<div><span class="pl">Monthly</span><span class="pv">{money(p.monthly)}</span><span class="ps">6.99% · 10 years</span></div></div>')
    else:
        prices = f'<div class="prices one"><div class="lead"><span class="pl">Price · check or ACH</span><span class="pv">{money(p.sell)}</span></div></div>'
    img = (f'<img class="hero-img" src="r/{key}-{hero}.jpg" alt="Rendering of the finished deck">' if hero in have else "")
    return ('<header class="manifest"><div class="hero">' + img + '<div class="hero-shade"></div>'
            f'<div class="hero-top"><div class="hin">{logo_svg()}<span class="mission">Deck Division · Proposal<br>{E(today)}</span></div></div>'
            f'<div class="hero-title"><div class="hin">' + (f'<span class="eyebrow">{E(eyebrow)}</span>' if eyebrow else "")
            + f'<h1>{E(title)}</h1><p class="who">{E(who)}</p></div></div></div>'
            '<div class="launch"><div class="hin">'
            '<div class="telemetry">' + "".join(f'<div><span class="tv">{E(v)}</span><span class="tl">{E(k)}</span></div>' for v, k in tele) + "</div>"
            + prices
            + '<div class="chips">' + "".join(f'<div class="chip"><i style="background:{c}"></i><span><b>{E(k)}</b>{E(v)}</span></div>' for c, k, v in chips) + "</div>"
            + (f'<p class="lede">{E(lede)}</p>' if lede else "") + "</div></div></header>")


def _arc(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
    x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
    return f"M{x0:.2f} {y0:.2f}A{r} {r} 0 {1 if a1 - a0 > 180 else 0} 1 {x1:.2f} {y1:.2f}"


def wheel(spec, p, options_html: str, next_html: str) -> str:
    """Investment: the price wheel (every part of the price, largest first from twelve o'clock), the legend with the
    dollars and the share, the financing terms, the options and the next step."""
    items = sorted(((k, v) for k, v in p.allocation if v > 0), key=lambda kv: -kv[1])
    if len(items) > len(WHEEL):
        rest = sum(v for _, v in items[len(WHEEL) - 1:])
        items = items[:len(WHEEL) - 1] + [("Everything else", rest)]
    total = sum(v for _, v in items) or 1.0
    cx = cy = 120
    r, gap = 92, 1.4                       # the ring's centre line; a 2px surface gap between wedges
    a, paths, rows = -90.0, [], []
    for i, (k, v) in enumerate(items):
        sweep = 360.0 * v / total
        a0, a1 = a + gap / 2, a + sweep - gap / 2
        if a1 - a0 < 0.6:
            a1 = a0 + 0.6
        share = f"{100 * v / total:.0f}%" if v / total >= 0.01 else "<1%"
        paths.append(f'<path d="{_arc(cx, cy, r, a0, a1)}" stroke="{WHEEL[i]}" data-k="{i}"><title>{E(k)}: {money(v)} ({share})</title></path>')
        rows.append(f'<li data-k="{i}" data-v="{money(v)}" data-s="{E(share)} of the price" tabindex="0"><i style="background:{WHEEL[i]}"></i>'
                    f'<span>{E(k)}</span><span class="lv">{money(v)}</span><span class="lp">{share}</span></li>')
        a += sweep
    rows.append(f'<li class="total"><i></i><span>Total, check or ACH</span><span class="lv">{money(p.sell)}</span><span class="lp">100%</span></li>')
    svg = (f'<svg viewBox="0 0 240 240" role="img" aria-label="Price wheel: {E(", ".join(f"{k} {money(v)}" for k, v in items))}">'
           + "".join(paths)
           + f'<text class="wc-v" x="{cx}" y="{cy + 6}" text-anchor="middle">{money(p.sell)}</text>'
           + f'<text class="wc-l" x="{cx}" y="{cy + 26}" text-anchor="middle">CHECK OR ACH</text></svg>')
    if spec.extras.show_financing:
        terms = ('<div class="terms">'
                 f'<div class="lead"><span class="pl">Check or ACH</span><span class="tv">{money(p.sell)}</span><span class="ps">{(1 - p.sell / p.retail) * 100:.0f}% savings</span></div>'
                 f'<div><span class="pl">Total investment</span><span class="tv">{money(p.retail)}</span><span class="ps">financed, no money down</span></div>'
                 f'<div><span class="pl">About</span><span class="tv">{money(p.monthly)}/mo</span><span class="ps">6.99% for 10 years</span></div>'
                 '<div><span class="pl">Or</span><span class="tv">12 or 18 mo</span><span class="ps">no payments, no down payment</span></div></div>')
    else:
        terms = f'<div class="terms one"><div class="lead"><span class="pl">Price · check or ACH</span><span class="tv">{money(p.sell)}</span></div></div>'
    return ('<section class="invest" aria-labelledby="inv-h"><div class="inv-head"><span class="eyebrow">Investment</span>'
            '<h3 id="inv-h">Where every dollar goes</h3></div>'
            f'<div class="inv-grid"><figure class="wheel">{svg}</figure><ol class="legend">' + "".join(rows) + "</ol></div>"
            + terms
            + (f'<div class="opts"><h4>Options</h4>{options_html}</div>' if options_html else "")
            + (f'<div><h4>Next step</h4>{next_html}</div>' if next_html else "") + "</section>")
