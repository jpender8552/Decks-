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

RAIL_HEX = {"black": "#141414", "white": "#f1f0ea", "bronze": "#5a4632", "gray": "#7a7c7e", "gray": "#7a7c7e"}

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

OPTIONS_CSS = """<style>
/* Options as blocks (each its own price three ways, what it adds, its own renders, its add-ons) and the link to the
   interactive 3D page. Added only to a page that has them. */
.optblock { margin:26px 0 10px; border:1px solid var(--line); background:var(--paper); }
.opt-head { background:var(--space); color:var(--space-ink); padding:18px 20px; display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:14px 24px; align-items:end; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.opt-title { display:flex; flex-direction:column; gap:6px; min-width:0; }
.opt-head h3 { font-family:var(--display); font-weight:800; text-transform:uppercase; letter-spacing:.02em; line-height:1; font-size:clamp(24px, 3.4vw, 36px); margin:0; color:#ffffff; text-wrap:balance; }
.opt-prices { display:grid; grid-template-columns:repeat(3, auto); border:1px solid var(--space-line); }
.opt-prices.one { grid-template-columns:auto; }
.opt-prices > div { padding:10px 16px; display:flex; flex-direction:column; gap:4px; min-width:0; }
.opt-prices > div + div { border-left:1px solid var(--space-line); }
.opt-prices .pv { font-size:clamp(20px, 2.6vw, 28px); white-space:nowrap; }
.opt-prices .lead .pv { background:linear-gradient(100deg, var(--gold-a) 0%, var(--gold-b) 55%, var(--gold-a) 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
.opt-body { padding:16px 20px 20px; display:flex; flex-direction:column; gap:14px; }
.opt-body p { margin:0; max-width:72ch; }
.opt-blurb { font-size:16px; line-height:1.55; }
.opt-scope { margin:0; padding-left:18px; display:flex; flex-direction:column; gap:4px; font-size:15px; }
.opt-addon { border-left:3px solid var(--gold); padding:10px 14px; background:var(--ground); display:flex; flex-direction:column; gap:8px; }
.oa-line { display:flex; flex-wrap:wrap; gap:4px 14px; align-items:baseline; justify-content:space-between; }
.oa-line span { font-variant-numeric:tabular-nums; font-weight:700; }
.opt-note { color:var(--ink-3); font-size:13.5px; }
table.optsum td:first-child { min-width:240px; }
table.optsum .sub { display:block; padding-left:14px; color:var(--space-mute); font-size:13px; }
table.optsum tr.addon td:first-child { padding-left:14px; color:var(--space-soft); }
table.optsum tr.total td { border-top:1px solid rgba(244,242,236,.5); font-weight:800; }
.plan-fig { margin:6px 0 4px; }
.plan-fig svg { display:block; width:100%; height:auto; background:#fbf9f4; border:1px solid var(--line); }
.facts-cols { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:6px 28px; }
.facts-cols h3 { margin:12px 0 4px; }
.facts-cols ul { margin:0; padding-left:18px; } .facts-cols li { margin:3px 0; }
@media (max-width:760px) { .facts-cols { grid-template-columns:1fr; } }
.v3d-link { background:var(--space); color:var(--space-ink); padding:20px; display:flex; flex-direction:column; gap:12px; align-items:flex-start; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.v3d-link p { margin:0; color:var(--space-soft); max-width:70ch; }
.v3d-btn { display:inline-block; font-family:var(--display); font-weight:700; letter-spacing:.16em; text-transform:uppercase; font-size:14px; color:#050608; text-decoration:none;
  background:linear-gradient(100deg, var(--gold-a), var(--gold-b)); padding:12px 18px; border-radius:3px; }
.v3d-btn:focus-visible { outline:2px solid #ffffff; outline-offset:3px; }
.v3d-url { font-size:12.5px; color:var(--space-mute); word-break:break-all; }
@media (max-width:760px) {
  .opt-head { grid-template-columns:1fr; }
  .opt-prices { grid-template-columns:repeat(3, minmax(0, 1fr)); }
  .opt-prices > div { padding:10px 10px; }
  table.optsum td:first-child { min-width:160px; }
}
@media print {
  .optblock + .optblock { break-before:page; page-break-before:always; }
  .optblock { margin-top:0.1in; border:0; break-inside:avoid; page-break-inside:avoid; }
  .opt-head, .opt-body { padding-left:0.18in; padding-right:0.18in; }
  .opt-body { gap:10px; }
  .opt-blurb { font-size:12.5px; }
  .opt-scope { font-size:11.5px; }
  .optblock .gal { gap:8px; }
  .optblock figure img { max-height:2.3in; object-fit:cover; }
  .opt-addon figure img { max-height:1.95in; }
  .opt-addon .fine { font-size:11px; }
  .opt-addon { break-inside:avoid; page-break-inside:avoid; }
  .v3d-link { break-inside:avoid; page-break-inside:avoid; }
  .facts-cols > div { break-inside:avoid; page-break-inside:avoid; }
  .facts-cols, .opt-scope { font-size:12.5px; }
  .plan-fig { break-inside:avoid; page-break-inside:avoid; }
  /* the investment carries the options table too: keep it on one page */
  body.proposal .invest { gap:14px; padding-top:0.22in; padding-bottom:0.22in; }
  body.proposal .invest .inv-head h3 { font-size:26px; }
  body.proposal .invest .inv-grid { gap:20px; grid-template-columns:minmax(0, 2.3in) minmax(0, 1fr); }
  body.proposal .invest .wheel svg { max-width:2.3in; }
  body.proposal .invest .legend li { padding:4px; font-size:11.5px; }
  body.proposal .invest .terms > div { padding:8px 12px; }
  body.proposal .invest table.optsum td, body.proposal .invest table.optsum th { padding-top:3px; padding-bottom:3px; font-size:11px; }
  body.proposal .invest p { font-size:11.5px; line-height:1.45; }
}
</style>"""

CONFIRM_CSS = """<style>
/* The client's "Still to confirm" box (extras.confirm). */
.confirm { border:1px solid var(--line); border-left:3px solid var(--gold); background:var(--paper); padding:14px 18px; display:flex; flex-direction:column; gap:8px; }
.confirm p { margin:0; max-width:72ch; }
.confirm .opt-scope { gap:6px; }
@media print { .confirm { padding:10px 14px; } .confirm .opt-scope { font-size:11.5px; } .confirm li { break-inside:avoid; page-break-inside:avoid; } }
</style>"""

TIMELINE_CSS = """<style>
/* The schedule: the job's own timeline (report.timeline_of) as a Gantt of working days — the time before day 1 in the first
   column, then one bar per stretch of work. Added only to a page that has one. */
.sched-title { font-family:var(--display); font-weight:800; text-transform:uppercase; letter-spacing:.02em; line-height:1.05; font-size:clamp(20px, 2.8vw, 28px); margin:4px 0 6px; }
.gantt { list-style:none; margin:10px 0 8px; padding:0; }
.gantt li { display:grid; grid-template-columns:minmax(0, 46%) minmax(0, 1fr); gap:0 16px; align-items:stretch; border-top:1px solid var(--line); font-size:14px; line-height:1.35; }
.gantt li.g-head { border-top:0; padding:0 0 4px; font-size:10.5px; letter-spacing:.16em; text-transform:uppercase; color:var(--ink-3); font-weight:800; }
.gantt .g-lab { padding:7px 0; }
.gantt .g-lab b { display:block; font-family:var(--display); font-weight:700; font-size:11.5px; letter-spacing:.2em; text-transform:uppercase; color:var(--gold-ink); }
.gantt .g-bar { position:relative; min-height:18px; background-image:linear-gradient(to right, var(--line) 1px, transparent 1px); background-size:calc(100% / var(--n)) 100%;
  -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.gantt .g-bar i { position:absolute; top:50%; height:12px; margin-top:-6px; border-radius:2px; background:linear-gradient(90deg, var(--gold-a), var(--gold-b)); }
.gantt .g-bar i.pre { background:var(--ink-3); }
.gantt .g-bar i.opt { background:var(--accent); }
.gantt .g-ticks { position:relative; height:14px; display:block; }
.gantt .g-ticks span { position:absolute; top:0; transform:translateX(-50%); font-variant-numeric:tabular-nums; letter-spacing:.04em; }
@media (max-width:760px) {
  .gantt li { grid-template-columns:minmax(0, 1fr); }
  .gantt li.g-head > span:first-child { display:none; }
}
@media print {
  .sched-title { font-size:20px; }
  .gantt li { font-size:11px; break-inside:avoid; page-break-inside:avoid; }
  .gantt .g-lab { padding:4px 0; }
  .gantt .g-lab b { font-size:9.5px; }
  .gantt .g-bar i { height:10px; margin-top:-5px; }
  .sched-opts { font-size:11.5px; }
}
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


# ================================================================== brands: whose name, logo and colors the client documents carry
# extras.brand picks one. A brand's assets live in decktakeoff/data/brands/<key>/: brand.json {"name", "short" (who the quote's
# words say does the work: "GSX"), "parent", "footer", "logo" (a file in that folder: .svg inline, .png / .jpg embedded; a
# version that reads on black), "colors": {"accent_a", "accent_b"}}. Without files a brand falls back to its name set in the
# display face and GS's gold. "gs" is the default and renders as always.
BRANDS = {
    "gs": dict(name="GS Exterior Experts", short="GSX", parent="", mission="Deck Division · Proposal", footer="GS Exterior Experts · Deck Division"),
    "cde": dict(name="Colorado Deck Experts", short="Colorado Deck Experts", parent="A GS Exterior Experts company", mission="Proposal",
                footer="Colorado Deck Experts · a GS Exterior Experts company"),
}


def brand_of(spec_or_key) -> dict:
    """The brand for a spec (extras.brand) or a key: the registry entry, then data/brands/<key>/brand.json over it."""
    key = spec_or_key if isinstance(spec_or_key, str) else (getattr(getattr(spec_or_key, "extras", None), "brand", None) or "gs")
    key = str(key or "gs").lower()
    b = dict(BRANDS.get(key) or dict(BRANDS["gs"], name=key, footer=key), key=key)
    d = Path(__file__).with_name("data") / "brands" / key
    if (d / "brand.json").exists():
        import json as _json
        b.update(_json.load(open(d / "brand.json")))
        b["dir"] = str(d)
    return b


def brand_logo(b: dict, height_class: str = "gslogo") -> str:
    """The brand's logo for the black cover: GS's inline SVG; another brand's file (SVG inline, raster embedded); else its name."""
    if b["key"] == "gs" and not b.get("logo"):
        return logo_svg(height_class)
    f = Path(b["dir"]) / b["logo"] if b.get("dir") and b.get("logo") else None
    if f is not None and f.exists():
        if f.suffix.lower() == ".svg":
            s = re.sub(r"<\?xml[^>]*\?>\s*", "", f.read_text())
            s = re.sub(r'id="([^"]+)"', lambda m: f'id="{b["key"]}-{m.group(1)}"', s)
            s = re.sub(r"url\(#([^)]+)\)", lambda m: f'url(#{b["key"]}-{m.group(1)})', s)
            return s.replace("<svg ", f'<svg class="{height_class}" role="img" aria-label="{E(b["name"])}" ', 1)
        import base64
        mime = "image/png" if f.suffix.lower() == ".png" else "image/jpeg"
        return f'<img class="{height_class}" src="data:{mime};base64,{base64.b64encode(f.read_bytes()).decode()}" alt="{E(b["name"])}">'
    return f'<span class="brandmark" role="img" aria-label="{E(b["name"])}">{E(b["name"])}</span>'


def brand_mission(b: dict, today: str, doc: str = "Deck Division · Proposal") -> str:
    """The top-right line of the cover (HTML): the document's name over the date; under another brand its parent line first."""
    if b["key"] == "gs":
        return f"{E(doc)}<br>{E(today)}"
    return (f"{E(b['parent'])}<br>" if b.get("parent") else "") + f"{E(doc)} · {E(today)}"


def brand_footer(spec_or_key) -> str:
    return brand_of(spec_or_key).get("footer") or BRANDS["gs"]["footer"]


def brand_css(spec_or_key) -> str:
    """A brand's colors and its text mark (nothing for GS)."""
    b = brand_of(spec_or_key)
    if b["key"] == "gs" and not b.get("colors"):
        return ""
    c = b.get("colors") or {}
    root = "".join(f"--{k}:{v};" for k, v in (("gold-a", c.get("accent_a")), ("gold-b", c.get("accent_b"))) if v)
    lp = float(b.get("logo_px") or 72)          # a wordmark logo reads larger than GS's emblem (brand.json "logo_px")
    sel = ".hero-top img.gslogo,.hero-top svg.gslogo"
    logo = (f"{sel}{{height:{lp:g}px;width:auto;}}@media (max-width:760px){{{sel}{{height:{round(lp * 0.72)}px;}}.mission{{letter-spacing:.1em;font-size:10px;}}}}"
            f"@media print{{body.proposal .hero-top img.gslogo,body.proposal .hero-top svg.gslogo{{height:{lp / 96 * 1.15:.2f}in;}}}}") if b.get("logo") else ""
    return ("<style>" + (f":root{{{root}}}" if root else "") + logo
            + ".brandmark{font-family:var(--display);font-weight:800;font-size:20px;letter-spacing:.14em;text-transform:uppercase;color:#ffffff;"
              "line-height:1.05;max-width:16ch;display:block;border-left:3px solid var(--gold-a);padding-left:10px;}"
            + "</style>")


def _title_parts(name: str, address: str):
    """'Deck Replacement · 19105 E Prentice Cir · White IRX option' -> ('19105 E Prentice Cir', 'Deck Replacement · White IRX option')."""
    if address and address in name:
        rest = [q.strip() for q in name.replace(address, "").split("·")]
        return address, " · ".join(q for q in rest if q)
    return name, ""


def _levels_tele(spec, L, t, n_piers) -> list:
    """Telemetry for a deck on two or more levels: SF, each level's height, the columns, the rail, the lights."""
    from .report import levels_of, columns_of, lights_of
    tele = [(f"{L.deck_sf:,.0f}", "square feet")] + [(ftin(v["height_in"]), v["name"].lower()) for v in levels_of(t)]    # each level's height above grade
    tele.append((str(columns_of(t)), f"{spec.framing.post_size} columns"))
    if L.rail:
        tele.append((f"{L.rail.rail_lf:g}'", f"{L.rail.color.lower()} rail"))
    lt = lights_of(t)
    if lt["total"]:
        tele.append((str(lt["total"]), "LED lights"))
    else:
        tele.append((ftin(L.finished_w), "across the house"))
    return tele


def cover(spec, L, sm, p, key, hero, have, name, who, lede, today, n_piers, t=None) -> str:
    """The launch manifest: hero render, title, the deck's numbers, the materials, the price."""
    title, eyebrow = _title_parts(name, spec.site.address)
    place = ", ".join(x for x in (spec.site.city, spec.site.state) if x)
    eyebrow = " · ".join(x for x in (eyebrow, place) if x)
    br = brand_of(spec)
    fr = L.zones[0].frame
    flush = all(b.kind == "flush" for b in (L.beam_lines or []))
    tele = [(f"{L.deck_sf:,.0f}", "square feet"), (ftin(L.finished_w), "across the house"), (ftin(spec.geometry.height_in), "above grade"),
            (spec.framing.joist_size, f"joists @ {fr.spacing:g}\" OC" + (", all flush" if flush else "")),
            (str(n_piers), {"diamond_pier": "Diamond Piers", "caisson": "caissons", "concrete": "concrete piers"}.get(spec.framing.footing_type, "existing caissons"))]
    rl = L.rail
    if hasattr(L, "parts") and t is not None:      # two levels: each level's height, the columns, the rail, the lights
        tele = _levels_tele(spec, L, t, n_piers)
    elif rl:
        tele.append((f"{rl.rail_lf:g}'", f"{rl.color.lower()} rail"))
    elif L.stairs:
        tele.append((str(sum(st.geo.risers for st in L.stairs)), "risers"))
    pal = BOARDS_PALETTE.get((spec.decking.collection, spec.decking.color))
    chips = [(pal[len(pal) // 2] if pal else "#73624a", "Decking", f"{spec.decking.brand} {spec.decking.collection} · {spec.decking.color}")]
    if spec.decking.border_color and spec.decking.border_color != spec.decking.color:
        bp = BOARDS_PALETTE.get((spec.decking.border_collection or spec.decking.collection, spec.decking.border_color))
        chips.append((bp[len(bp) // 2] if bp else "#5a4632", "Picture frame", f"{spec.decking.border_collection or spec.decking.collection} · {spec.decking.border_color}"))
    if rl:
        from .report import rail_words
        chips.append((RAIL_HEX.get(rl.color.lower(), "#141414"), "Rail", f"{spec.decking.brand} {rail_words(spec, rl.system)} · {rl.color}"))
    if rl and spec.railing.drink_rail and hasattr(L, "parts"):
        dc = spec.railing.drink_rail_collection or spec.decking.collection
        dp = BOARDS_PALETTE.get((dc, spec.railing.drink_rail_color or spec.decking.color))
        chips.append((dp[len(dp) // 2] if dp else "#5a4632", "Drink rail", f"{dc} · {spec.railing.drink_rail_color or spec.decking.color}"))
    if spec.extras.show_financing:
        prices = (f'<div class="prices"><div class="lead"><span class="pl">Check or ACH</span><span class="pv">{money(p.sell)}</span><span class="ps">{(1 - p.sell / p.retail) * 100:.0f}% below the financed price</span></div>'
                  f'<div><span class="pl">Financed</span><span class="pv">{money(p.retail)}</span><span class="ps">no money down</span></div>'
                  f'<div><span class="pl">Monthly</span><span class="pv">{money(p.monthly)}</span><span class="ps">6.99% · 10 years</span></div></div>')
    else:
        prices = f'<div class="prices one"><div class="lead"><span class="pl">Price · check or ACH</span><span class="pv">{money(p.sell)}</span></div></div>'
    img = (f'<img class="hero-img" src="r/{key}-{hero}.jpg" alt="Rendering of the finished deck">' if hero in have else "")
    return ('<header class="manifest"><div class="hero">' + img + '<div class="hero-shade"></div>'
            f'<div class="hero-top"><div class="hin">{brand_logo(br)}<span class="mission">'
            + brand_mission(br, today, "Deck Division · Proposal" if br["key"] == "gs" else (br.get("mission") or "Proposal")) + '</span></div></div>'
            f'<div class="hero-title"><div class="hin">' + (f'<span class="eyebrow">{E(eyebrow)}</span>' if eyebrow else "")
            + f'<h1>{E(title)}</h1><p class="who">{E(who)}</p></div></div></div>'
            '<div class="launch"><div class="hin">'
            '<div class="telemetry">' + "".join(f'<div><span class="tv">{E(v)}</span><span class="tl">{E(k)}</span></div>' for v, k in tele) + "</div>"
            + prices
            + '<div class="chips">' + "".join(f'<div class="chip"><i style="background:{c}"></i><span><b>{E(k)}</b>{E(v)}</span></div>' for c, k, v in chips) + "</div>"
            + (f'<p class="lede">{E(lede)}</p>' if lede else "") + "</div></div></header>")


# The Suncoast Louvered Roof as the homeowner reads it: product facts only, from $S/fillmore/louvered/research.md section 1 and
# 5.1 (Suncoast's louvered-roof page and Oct 2026 brochure [S1, S2], care guide [S5], warranty page [S4], retractable-screens
# page and brochure [S13, S14]) — the items research.md marks V (read in the source). A job overrides any list through
# render_addon(addon=dict(facts=...)); what the price includes (engineering, electrical, sensors) is the job's to say (exclusions).
LOUVER_FACTS = dict(
    what=[              # what the product is
        "Structural aluminum frame, beams, posts and blades, powder-coated (AAMA 2604)",
        "8\" blades on 8\" spacing with weather stripping on every blade: closed, they seal against rain and drain into the gutters; "
        "open, they turn up to 140 degrees",
        "A motor in one blade of each zone (one motor for up to 150 SF): no arms, levers or pistons outside the frame",
        "Each roof is made to order by Suncoast",
    ],
    controls=[          # motor, remote / app
        "Gaposa motors; the motors and electrical parts are CSA approved",
        "A hand-held remote, one channel per zone, each with a programmable preset angle",
        "Optional: a Wi-Fi module and app (schedules, control from anywhere), voice control through Alexa or Google Assistant, "
        "and a module for Control4 and other home automation",
    ],
    gutters=[           # the integrated gutter, downspouts
        "A gutter runs around each zone, inside the frame; the blades drain into it and water flows freely from zone to zone",
        "The downspouts can run hidden inside the posts",
        "The gutters are cleaned by hand or with a shop vacuum",
    ],
    lights=[            # the LED light track (a roof that carries the strip: louvered_roofs[i].lights)
        "The gutter carries a light track and a wire chase for an LED light strip; pot, rope and track lights can be added",
    ],
    lights_option=[     # the same, listed with the maker's options when the roof does not carry the strip
        "An LED light strip in the gutter's built-in light track and wire chase; pot, rope and track lights",
    ],
    accessories=[       # sensors and add-ons the maker offers (not in the price unless the job says so)
        "Rain and wind sensors can be built into the controls: rain closes the blades, and the screens can retract on their own in high wind",
        "Heaters (1,600 to 4,000 W), fans and an accessory beam for them can be added",
    ],
    screens=[           # the retractable screens: product facts (the job's screen sizes come from the louvered engine)
        "Gaposa motor with obstacle detection, on the roof's remote and app",
        "Phifer mesh held in zipper side tracks; a weighted, sealed bottom bar",
        "Rated for wind up to 65 mph; they can retract automatically in higher winds",
    ],
    warranty=[          # Suncoast's warranty page (the brochures still print "limited lifetime"; the page's terms are these)
        "Aluminum structure and the powder-coat finish: 15 years",
        "Motors, remotes and electronics: 5 years",
        "Screen mesh: 10 years; retractable vinyl screen components, welds, stitching and spline: 1 year",
        "Material defects, for the original purchaser; labor, removal and reinstallation are not covered. Weather beyond the design "
        "limits, normal fading and electronic accessories (heaters, lights, fans) are excluded",
    ],
    schedule=[],        # lead time: ask Suncoast Denver (research.md 7) — the job adds it
    exclusions=[],      # what the roof's price does not include: the job's (engineering / permit, electrical, sensors — research.md 6)
    structure_rows=[],  # extra (label, text) rows for the structure section
)


def addon_cover(title, eyebrow, who, today, hero_html, tele, prices, chips, lede, mission="Proposal", brand=None) -> str:
    """The launch-manifest cover for a separately sold item (the louvered roof's own document): the same look as the deck's
    cover — hero render, title, the item's numbers, its price three ways (prices = [(label, value, sub)]), the materials.
    brand: a brand_of() dict (default GS)."""
    br = brand or brand_of("gs")
    lead = ' class="lead"'
    pr = ('<div class="prices' + (" one" if len(prices) == 1 else "") + '">'
          + "".join(f'<div{lead if i == 0 else ""}><span class="pl">{E(l_)}</span><span class="pv">{E(v_)}</span>'
                    + (f'<span class="ps">{E(s_)}</span>' if s_ else "") + "</div>" for i, (l_, v_, s_) in enumerate(prices)) + "</div>")
    return ('<header class="manifest"><div class="hero">' + hero_html + '<div class="hero-shade"></div>'
            f'<div class="hero-top"><div class="hin">{brand_logo(br)}<span class="mission">{brand_mission(br, today, mission)}</span></div></div>'
            f'<div class="hero-title"><div class="hin">' + (f'<span class="eyebrow">{E(eyebrow)}</span>' if eyebrow else "")
            + f'<h1>{E(title)}</h1><p class="who">{E(who)}</p></div></div></div>'
            '<div class="launch"><div class="hin">'
            '<div class="telemetry">' + "".join(f'<div><span class="tv">{E(v)}</span><span class="tl">{E(k)}</span></div>' for v, k in tele) + "</div>"
            + pr
            + '<div class="chips">' + "".join(f'<div class="chip"><i style="background:{c}"></i><span><b>{E(k)}</b>{E(v)}</span></div>' for c, k, v in chips) + "</div>"
            + (f'<p class="lede">{E(lede)}</p>' if lede else "") + "</div></div></header>")


def addon_invest(rows, terms, next_html: str, title: str = "The price", show_fin: bool = True) -> str:
    """Investment for a separately sold item: its price three ways and the financing (terms = (check, financed, monthly)),
    then each line (rows = [(label, check, financed, monthly, kind)], kind "item" | "addon" | "total") and the next step."""
    c, f, m = terms
    if show_fin:
        tg = ('<div class="terms">'
              f'<div class="lead"><span class="pl">Check or ACH</span><span class="tv">{money(c)}</span><span class="ps">{(1 - c / f) * 100:.0f}% savings</span></div>'
              f'<div><span class="pl">Total investment</span><span class="tv">{money(f)}</span><span class="ps">financed, no money down</span></div>'
              f'<div><span class="pl">About</span><span class="tv">{money(m)}/mo</span><span class="ps">6.99% for 10 years</span></div>'
              '<div><span class="pl">Or</span><span class="tv">12 or 18 mo</span><span class="ps">no payments, no down payment</span></div></div>')
    else:
        tg = f'<div class="terms one"><div class="lead"><span class="pl">Price · check or ACH</span><span class="tv">{money(c)}</span></div></div>'

    def cell(v, kind):
        return ("+" if kind == "addon" else "") + money(v)
    head = "<tr><th>Item</th><th class='num'>Check or ACH</th>" + ("<th class='num'>Financed</th><th class='num'>Monthly</th>" if show_fin else "") + "</tr>"
    body = "".join(f"<tr class='{kind}'><td>{('<b>' + E(lab) + '</b>') if kind == 'total' else E(lab)}</td><td class='num'>{cell(cc, kind)}</td>"
                   + (f"<td class='num'>{cell(ff, kind)}</td><td class='num'>{cell(mm, kind)}/mo</td>" if show_fin else "") + "</tr>"
                   for lab, cc, ff, mm, kind in rows)
    return ('<section class="invest" id="g-investment" aria-labelledby="inv-h"><div class="inv-head"><span class="eyebrow">Investment</span>'
            f'<h3 id="inv-h">{E(title)}</h3></div>' + tg
            + f'<div class="opts"><div class="tw"><table class="optsum"><thead>{head}</thead><tbody>{body}</tbody></table></div></div>'
            + (f'<div><h4>Next step</h4>{next_html}</div>' if next_html else "") + "</section>")


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
    r, gap = 92, 1.4                       # the ring's center line; a 2px surface gap between wedges
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


# ================================================================== the photo-led proposal (render_page mode="proposal")
# One deliberate Letter page per section, the photoreal renders large: cover (one image, the address, the date — no price),
# your deck (the overview: image, the lede, the numbers, the materials), the day views as full-bleed spreads, an after-dark
# spread of the dusk views, the views from above with the plan and the sun study, what's included, how it's built, the
# investment (two ways to pay, then where every dollar goes) and a back cover. The slots fill themselves from the view
# names in the renders folder (plan_views), so a new shoot (left, leftfront, stairfront, ..._dusk) lands without edits.
# Everything is scoped to body.pp; the customer page, the add-on document and the combined document keep their look.

PP_HERO_POS = {                      # object-position for the crops of the known views (the deck sits low in most frames)
    "yard": "50% 74%", "yard_dusk": "50% 72%", "corner": "70% 70%", "corner_dusk": "74% 70%", "corner2": "50% 66%",
    "ondeck": "50% 72%", "ondeck_dusk": "50% 72%", "facade": "50% 82%", "isolow": "50% 70%", "detail": "50% 0%",
    "iso": "50% 60%", "iso2": "50% 62%", "left": "50% 66%", "leftfront": "50% 66%", "leftlow": "50% 66%",
    "stairfront": "50% 70%", "ondeck_left": "50% 72%", "door": "50% 66%", "aerial_left": "50% 60%",
}
PP_TECH_PREFIX = ("exploded", "frame-", "structure-", "rail-", "step", "sun-", "alt-")
PP_TECH_NAMES = {"plan", "under", "underiso"}
PP_DAY = ["yard", "left", "corner", "corner2", "leftfront", "stairfront", "ondeck", "ondeck_left", "door", "facade", "leftlow", "isolow"]
PP_AERIAL = ["aerial_left", "iso2", "iso", "aerial", "aerial_right"]
PP_DUSK = ["corner_dusk", "yard_dusk", "left_dusk", "leftfront_dusk", "stairfront_dusk", "ondeck_dusk", "ondeck_left_dusk",
           "door_dusk", "corner2_dusk", "facade_dusk", "leftlow_dusk", "aerial_left_dusk", "detail_dusk"]
PP_CAPS = {                          # fallback captions for the shoot's station names (a job's captions.json wins)
    "left": "From the left side of the yard", "leftfront": "From the front left of the yard", "leftlow": "Low view from the left",
    "stairfront": "In front of the center stair", "ondeck_left": "Standing on the deck, the left side", "door": "From the back door",
    "aerial_left": "From above, the left side", "detail": "Up close", "facade": "The whole back of the house",
    "corner2": "From the left corner of the yard",
}
# the price wheel on black: one gold hue, brightest for the largest share (validated as an ordinal ramp on #050608:
# monotone lightness, adjacent steps >= 0.06 L apart, the darkest step 2.35:1 against the panel)
PP_WHEEL = ["#fddb6f", "#ecc24e", "#dcaa26", "#c99200", "#b47c00", "#9e6600", "#895200", "#743e00"]
HARDIE_HEX = {"arctic white": "#f1f0ea", "timber bark": "#5d4b3c", "iron gray": "#53565a", "cobble stone": "#a59c8b",
              "navajo beige": "#c9b99b", "khaki brown": "#8a7660", "monterey taupe": "#8f8574", "aged pewter": "#6f6e69"}


def jpeg_size(path) -> tuple:
    """(width, height) of a JPEG from its SOF marker, or None — no imaging library needed."""
    try:
        with open(path, "rb") as fh:
            if fh.read(2) != b"\xff\xd8":
                return None
            while True:
                b = fh.read(1)
                while b and b != b"\xff":
                    b = fh.read(1)
                while b == b"\xff":
                    b = fh.read(1)
                if not b:
                    return None
                m = b[0]
                if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                    continue
                ln = int.from_bytes(fh.read(2), "big")
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    d = fh.read(5)
                    return int.from_bytes(d[3:5], "big"), int.from_bytes(d[1:3], "big")
                fh.seek(ln - 2, 1)
    except OSError:
        return None


def photoreal_names(rd, have) -> set:
    """The stills in the renders folder that are photoreal (Cycles): the names its renders.json lists when the folder has
    one, else every still that is not a WebGL viewer still (a viewer name at the viewer's 1400 x 900)."""
    import json as _json
    rd = Path(rd)
    if (rd / "renders.json").exists():
        try:
            return {k[:-4] if k.endswith(".jpg") else k for k in _json.load(open(rd / "renders.json"))} & set(have)
        except Exception:
            pass
    from .render import STILLS
    webgl = {n for n, _ in STILLS}
    return {n for n in have if not (n in webgl and jpeg_size(rd / f"{n}.jpg") == (1400, 900)) and not n.startswith("sun-")}


def _kind(n: str) -> str:
    if n.startswith(PP_TECH_PREFIX) or n in PP_TECH_NAMES:
        return "tech"
    if n.endswith(("_dusk", "_night")):
        return "dusk"
    if n.startswith("detail"):
        return "detail"
    if n.startswith("aerial") or (n.startswith("iso") and not n.startswith("isolow")):
        return "aerial"
    return "day"


def _ordered(names, pref) -> list:
    names = list(dict.fromkeys(names))
    return [n for n in dict.fromkeys(pref) if n in names] + sorted(n for n in names if n not in pref)


def _chunks(xs: list, max_pages: int) -> tuple:
    """Spread pages: two, three, two images ... (a lone last image gets a page of its own); the rest left over."""
    out, i, pat = [], 0, [2, 3]
    while i < len(xs) and len(out) < max_pages:
        rem, k = len(xs) - i, pat[len(out) % 2]
        if rem <= 3 and rem != k:
            k = rem
        if rem == 4 and k == 3:
            k = 2
        out.append(xs[i:i + k])
        i += k
    return out, xs[i:]


def plan_views(have, hero: str, photo: set) -> dict:
    """Which still goes where. have = the still names in the renders folder, photo = the photoreal ones (the big slots take
    only those when there are any). The cover takes the hero's dusk view when the shoot has three or more dusk views (else
    the hero by day); the overview the view from the yard; then the day spreads (2, 3, 2 images), the after-dark spreads
    (2, 3), the back cover the next dusk view, the views from above, a close-up for what's included, and the rest (up to
    six) on a page of more views."""
    use = (lambda n: n in photo) if photo else (lambda n: True)
    pool = {k: [] for k in ("day", "dusk", "detail", "aerial", "tech")}
    for n in have:
        pool[_kind(n)].append(n)
    day = _ordered([n for n in pool["day"] if use(n)], [hero] + PP_DAY)
    dusk = _ordered([n for n in pool["dusk"] if use(n)], [f"{hero}_dusk"] + PP_DUSK)
    hd = f"{hero}_dusk"
    if hd in dusk and len(dusk) >= 3:
        cover = hd
    else:
        cover = hero if hero in day else (day[0] if day else (dusk[0] if dusk else None))
    day = [n for n in day if n != cover]
    dusk = [n for n in dusk if n != cover]
    over = next((n for n in ["yard", hero] + day if n in day), None)
    day = [n for n in day if n != over]
    aer = _ordered([n for n in pool["aerial"] if use(n)] or pool["aerial"], PP_AERIAL)
    det = _ordered([n for n in pool["detail"] if use(n)], ["detail"])
    detail = det[0] if det else None
    day_pages, day_rest = _chunks(day, 3)
    night_pages, night_rest = _chunks(dusk, 2)
    back = night_rest[0] if night_rest else None
    more = (day_rest + night_rest[1:] + det[1:] + aer[3:])[:6]
    return dict(cover=cover, overview=over, day=day_pages, night=night_pages, back=back, aerial=aer[:3], detail=detail,
                more=more if len(more) >= 2 else [], plan="plan" if "plan" in have else None,
                sun=sorted(n for n in have if n.startswith("sun-")))


def pp_caption(n: str, caps: dict) -> str:
    if n in caps:
        return caps[n]
    if n.endswith("_dusk"):
        base = caps.get(n[:-5]) or PP_CAPS.get(n[:-5])
        return f"At dusk, {base[0].lower() + base[1:]}" if base else "At dusk"
    return PP_CAPS.get(n, n.replace("_", " ").replace("-", " ").capitalize())


def _img(key: str, n: str, caps: dict, cls: str = "", pos: str = "") -> str:
    p = pos or PP_HERO_POS.get(n, "50% 62%")
    return (f'<img class="{cls}" src="r/{key}-{n}.jpg" alt="{E(pp_caption(n, caps))}" loading="lazy" '
            f'style="object-position:{p}">')


def _fig(key: str, n: str, caps: dict, cls: str = "") -> str:
    return f'<figure class="ph {cls}">{_img(key, n, caps)}<figcaption>{E(pp_caption(n, caps))}</figcaption></figure>'


def _folio(left: str, right: str = "") -> str:
    return f'<div class="folio"><span>{E(left)}</span><span>{E(right)}</span></div>'


_SWATCH = {}


def board_swatch(collection: str, color: str, boards: int = 1) -> str:
    """A small rendered swatch of a TimberTech board (the timbertech-boards renderer, seeded by the board's name, so the
    same board looks the same in every document) as a data URI; "" when the renderer is not on this machine."""
    k = (collection, color, boards)
    if k in _SWATCH:
        return _SWATCH[k]
    uri = ""
    try:
        import base64, io, os, sys
        skill = os.environ.get("TT_BOARDS_SKILL", "/root/.claude/skills/synced/607fe818-1870-48a4-acf4-521f29c0bf01_8ba838c8-b3cb-4abb-8652-1992d2c2ba58/timbertech-boards/scripts")
        if os.path.isdir(skill):
            sys.path.insert(0, skill)
            try:
                import render as TT              # the timbertech-boards renderer
            finally:
                sys.path.pop(0)
            from PIL import Image
            pal = BOARDS_PALETTE.get((collection, color))
            if pal:                              # the engine catalog's palette wins over the skill's copy (as in cycles.py)
                TT.C.BOARDS = [(b[0], b[1], b[2], list(pal)) + tuple(b[4:]) if (b[0], b[1]) == (collection, color) else b for b in TT.C.BOARDS]
            ims = [TT.render_board(collection, color, length_in=18, ppi=20, seed_offset=100 + i).convert("RGB") for i in range(boards)]
            w, h, gap = ims[0].width, ims[0].height, 3
            out = Image.new("RGB", (w, h * boards + gap * (boards - 1)), (20, 18, 16))
            for i, im in enumerate(ims):
                out.paste(im, (0, i * (h + gap)))
            buf = io.BytesIO()
            out.save(buf, "JPEG", quality=86)
            uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        uri = ""
    _SWATCH[k] = uri
    return uri


def materials(spec, L) -> list:
    """The overview's materials: [(label, name, css background)] — decking (a rendered board strip), picture frame, rail,
    drink rail, the HardieTrim skirt."""
    from .report import rail_words
    rows = []
    d = spec.decking

    def bg(coll, color, boards=1):
        uri = board_swatch(coll, color, boards)
        pal = BOARDS_PALETTE.get((coll, color))
        flat = pal[len(pal) // 2] if pal else "#73624a"
        return f"url({uri}) center/cover, {flat}" if uri else flat
    rows.append(("Decking", f"{d.brand} {d.collection} · {d.color}", bg(d.collection, d.color, 3)))
    if d.border_color and d.border_color != d.color:
        rows.append(("Picture frame", f"{d.border_collection or d.collection} · {d.border_color}", bg(d.border_collection or d.collection, d.border_color)))
    rl = L.rail
    if rl:
        rows.append(("Rail", f"{d.brand} {rail_words(spec, rl.system)} · {rl.color}", RAIL_HEX.get(rl.color.lower(), "#141414")))
        if spec.railing.drink_rail:
            dc = spec.railing.drink_rail_collection or d.collection
            dcol = spec.railing.drink_rail_color or d.color
            rows.append(("Drink rail", f"{d.brand} {dc} · {dcol}", bg(dc, dcol)))
    hs = getattr(spec.extras, "hardie_skirt", None)
    if hs:
        hc = getattr(spec.extras, "hardie_color", "") or re.sub(r"^[\d/ x.\"']+", "", hs).strip() or "Timber Bark"
        rows.append(("Fascia", f"James Hardie HardieTrim · {hc}", HARDIE_HEX.get(hc.lower(), "#cfc8bb")))
    return rows


def telemetry(spec, L, n_piers, t=None) -> list:
    """The deck's numbers for the overview strip: [(value, label)]."""
    fr = L.zones[0].frame
    flush = all(b.kind == "flush" for b in (L.beam_lines or []))
    tele = [(f"{L.deck_sf:,.0f}", "square feet"), (ftin(L.finished_w), "across the house"), (ftin(spec.geometry.height_in), "above grade"),
            (spec.framing.joist_size, f"joists @ {fr.spacing:g}\" OC" + (", all flush" if flush and L.beam_lines else "")),
            (str(n_piers), {"diamond_pier": "Diamond Piers", "caisson": "caissons", "concrete": "concrete piers"}.get(spec.framing.footing_type, "existing caissons"))]
    if hasattr(L, "parts") and t is not None:
        return _levels_tele(spec, L, t, n_piers)
    if L.rail:
        tele.append((f"{L.rail.rail_lf:g}'", f"{L.rail.color.lower()} rail"))
    elif L.stairs:
        tele.append((str(sum(st.geo.risers for st in L.stairs)), "risers"))
    return tele


def _split_lede(lede: str) -> tuple:
    """(standfirst, body): the lede's first sentence set large, the rest as the body."""
    lede = (lede or "").strip()
    m = re.search(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", lede)
    if m and 40 <= m.start() <= 220:
        return lede[:m.start()], lede[m.end():]
    return (lede, "") if len(lede) <= 220 else ("", lede)


# Run by page.render_pdf in the print layout before the PDF is made: a page section that runs past its Letter page takes
# the tighter classes it names in data-fit, one at a time, until it fits (the overview's "tight", the investment's "dense").
FIT_JS = """() => { var H = 11 * 96 + 1, n = 0;
  document.querySelectorAll('[data-fit]').forEach(function (el) {
    var steps = el.getAttribute('data-fit').split(' ');
    for (var i = 0; i < steps.length; i++) {
      if (Math.max(el.scrollHeight, el.getBoundingClientRect().height) <= H) break;
      el.classList.add(steps[i]); n++;
    }
  });
  return n; }"""


def pp_cover(spec, key, img, caps, name, who, today) -> str:
    """Page 1: one full-bleed image, the logo and the date, the address. No price on the cover."""
    title, eyebrow = _title_parts(name, spec.site.address)
    place = ", ".join(x for x in (spec.site.city, spec.site.state) if x)
    eyebrow = " · ".join(x for x in (eyebrow, place) if x)
    br = brand_of(spec)
    mission = brand_mission(br, today, "Deck Division · Proposal" if br["key"] == "gs" else (br.get("mission") or "Proposal"))
    pic = _img(key, img, caps, "pc-img") if img else ""
    return ('<header class="pp-cover pg" id="g-cover"><div class="pc-hero">' + pic + '<div class="pc-shade"></div>'
            f'<div class="pc-top">{brand_logo(br)}<span class="mission">{mission}</span></div></div>'
            '<div class="pc-title">' + (f'<span class="eyebrow">{E(eyebrow)}</span>' if eyebrow else "")
            + f'<h1>{E(title)}</h1><p class="who">{E(who)}</p></div>'
            + f'<div class="pc-foot"><span>{E(brand_footer(spec))}</span><span>{E(pp_caption(img, caps)) if img else ""}</span></div></header>')


def pp_overview(spec, L, key, img, caps, lede, n_piers, t=None, foot="") -> str:
    """Page 2, your deck: the view from the yard, the lede (its first sentence large), the numbers, the materials."""
    stand, body = _split_lede(lede)
    tele = telemetry(spec, L, n_piers, t)
    mats = materials(spec, L)
    h = [f'<section class="pg pp-over flow{"" if (stand or body) else " nolede"}" data-fit="tight tighter" id="g-reads" aria-label="The project">']
    if img:
        h.append(f'<figure class="po-fig">{_img(key, img, caps)}<figcaption>{E(pp_caption(img, caps))}</figcaption></figure>')
    h.append('<div class="pin"><span class="eyebrow">The project</span>')
    if stand:
        h.append(f'<p class="stand">{E(stand)}</p>')
    h.append('<div class="stats">' + "".join(f'<div><span class="sv">{E(v)}</span><span class="sl">{E(k)}</span></div>' for v, k in tele) + "</div>")
    h.append('<div class="po-cols">' + (f'<div class="po-lede"><p>{E(body)}</p></div>' if body else "")
             + '<div class="po-mat"><h3>Materials</h3><ul>'
             + "".join(f'<li><i style="background:{c}"></i><span><b>{E(k)}</b>{E(v)}</span></li>' for k, v, c in mats) + "</ul></div></div>")
    h.append("</div>" + _folio(foot, "The project") + "</section>")
    return "".join(h)


def pp_photos(key, names, caps, label: str, night: bool = False, note: str = "", foot: str = "", sid: str = "") -> str:
    """A spread: one image (solo), two stacked at full width (duo) or three wide strips (trio), edge to edge; the section
    label and a line of facts over the first image."""
    kind = {1: "solo", 2: "duo"}.get(len(names), "trio")
    h = [f'<section class="pg pp-photo {kind}{" night" if night else ""}"' + (f' id="{sid}"' if sid else "") + f' aria-label="{E(label)}">']
    for i, n in enumerate(names):
        h.append(_fig(key, n, caps, f"ph-{i}"))
    h.append(f'<div class="ph-label"><span class="eyebrow">{E(label)}</span>' + (f"<p>{E(note)}</p>" if note else "") + "</div>")
    h.append(_folio(foot, label) + "</section>")
    return "".join(h)


def _sheet(eyebrow: str, title: str, tag: str = "", cls: str = "", sid: str = "", label: str = "") -> str:
    return (f'<section class="pg pp-sheet {cls}"' + (f' id="{sid}"' if sid else "") + f' aria-label="{E(label or eyebrow)}"><div class="pin">'
            f'<header class="sh"><span class="eyebrow">{E(eyebrow)}</span><h2>{E(title)}</h2>' + (f'<p class="tag">{E(tag)}</p>' if tag else "") + "</header>")


def pp_above(key, aerial, plan, suns, caps, sun_tag: str, foot: str = "") -> str:
    """The views from above (up to three) with the plan, then the sun study in one row."""
    cells = list(aerial) + ([plan] if plan else [])
    if not cells and not suns:
        return ""
    h = [_sheet("The site", "From above", cls="pp-above", sid="g-iso")]
    if cells:
        if len(cells) >= 3:
            h.append(_fig(key, cells[0], caps, "big") + f'<div class="grid g{len(cells) - 1}">' + "".join(_fig(key, n, caps) for n in cells[1:]) + "</div>")
        else:
            h.append(f'<div class="grid g{len(cells)}">' + "".join(_fig(key, n, caps) for n in cells) + "</div>")
    if suns:
        h.append(f'<div class="sun"><h3>Sun and shade <span>{E(sun_tag)}</span></h3><div class="sunrow n{min(len(suns), 5)}">'
                 + "".join(_fig(key, n, caps) for n in suns[:5]) + "</div></div>")
    h.append("</div>" + _folio(foot, "From above") + "</section>")
    return "".join(h)


def md_rows(md: str) -> list:
    """A markdown table's body rows: [[cell, ...]] (the header and the rule dropped)."""
    rows = []
    for ln in md.splitlines():
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
    return rows[1:]


def _inline(s: str) -> str:
    s = E(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def pp_included(key, img, caps, rows, foot: str = "") -> str:
    """What's included: a close-up across the top, then every row of the price's scope as a card."""
    n = len([r for r in rows if len(r) >= 2])
    h = [f'<section class="pg pp-sheet pp-inc flow {"rows-s" if n <= 8 else "rows-m" if n <= 10 else "rows-l"}{"" if img else " noimg"}" data-fit="rows-m rows-l" id="g-what" aria-label="What\'s included">']
    if img:
        h.append(f'<figure class="pi-fig">{_img(key, img, caps)}<figcaption>{E(pp_caption(img, caps))}</figcaption></figure>')
    h.append('<div class="pin"><header class="sh"><span class="eyebrow">What\'s included</span><h2>Included in the price</h2></header>'
             '<div class="cards">' + "".join(f'<div class="card"><h3>{_inline(r[0])}</h3><p>{_inline(r[1])}</p></div>' for r in rows if len(r) >= 2) + "</div>")
    h.append("</div>" + _folio(foot, "What's included") + "</section>")
    return "".join(h)


def pp_built(key, big, small, caps, reads_html: str, foot: str = "") -> str:
    """How it's built: the exploded view large, two views of the frame, the deck's reads."""
    if not big and not small and not reads_html:
        return ""
    long_ = reads_html.count("<dt>") > 7
    if long_:
        small = []
    h = [_sheet("How it's built", "Every layer, pulled apart", cls="pp-built flow" + (" long" if long_ else ""), sid="g-exploded").replace('<section ', '<section data-fit="long" ', 1)]
    if big:
        h.append(_fig(key, big, caps, "big"))
    if small:
        h.append(f'<div class="grid g{len(small)}">' + "".join(_fig(key, n, caps) for n in small) + "</div>")
    if reads_html:
        h.append(f'<div class="reads-box">{reads_html}</div>')
    h.append("</div>" + _folio(foot, "How it's built") + "</section>")
    return "".join(h)


def pp_more(key, names, caps, foot: str = "") -> str:
    if not names:
        return ""
    return (_sheet("Renders", "More views", cls="pp-more", sid="g-more") + '<div class="grid g6">' + "".join(_fig(key, n, caps) for n in names)
            + "</div></div>" + _folio(foot, "More views") + "</section>")


def _label_split(k: str) -> tuple:
    """A price line as (head, qualifier): "Lighting — 9 post-cap lights, ..." -> ("Lighting", "9 post-cap lights, ..."); a line
    that joins several items with "+" stays whole."""
    if " — " in k and "+" not in k:
        head, _, sub = k.rpartition(" — ")
        return head, sub
    return k, ""


def pp_invest(spec, p, options_html: str, next_html: str, foot: str = "") -> str:
    """Investment on black: the two ways to pay, then where every dollar goes (a gold wheel, largest share brightest, the
    legend with each part's dollars and share; what is included at no charge listed with it), the options, the next step."""
    show_fin = spec.extras.show_financing
    if show_fin:
        ways = ('<div class="ways">'
                f'<div class="way lead"><span class="wl">Check or ACH</span><span class="wv">{money(p.sell)}</span>'
                f'<span class="ws">{(1 - p.sell / p.retail) * 100:.0f}% below the financed price</span></div>'
                f'<div class="way"><span class="wl">Financed · no money down</span><span class="wv">{money(p.retail)}</span>'
                f'<span class="ws">About <b>{money(p.monthly)}/month</b> at 6.99% for 10 years</span>'
                '<span class="ws">Or 12 or 18 months with no payments, no down payment</span></div></div>')
        title = "Two ways to pay"
    else:
        ways = f'<div class="ways one"><div class="way lead"><span class="wl">Price · check or ACH</span><span class="wv">{money(p.sell)}</span></div></div>'
        title = "The price"
    paid = sorted(((k, v) for k, v in p.allocation if v > 0), key=lambda kv: -kv[1])
    free = [k for k, v in p.allocation if v <= 0]
    if len(paid) > len(PP_WHEEL):
        rest = sum(v for _, v in paid[len(PP_WHEEL) - 1:])
        paid = paid[:len(PP_WHEEL) - 1] + [("Everything else", rest)]
    total = sum(v for _, v in paid) or 1.0
    cx = cy = 120
    r, gap = 96, 1.6
    a, paths, rows = -90.0, [], []
    for i, (k, v) in enumerate(paid):
        sweep = 360.0 * v / total
        a0, a1 = a + gap / 2, a + sweep - gap / 2
        if a1 - a0 < 0.6:
            a1 = a0 + 0.6
        share = f"{100 * v / total:.0f}%" if v / total >= 0.01 else "<1%"
        head, sub = _label_split(k)
        paths.append(f'<path d="{_arc(cx, cy, r, a0, a1)}" stroke="{PP_WHEEL[i]}" data-k="{i}"><title>{E(k)}: {money(v)} ({share})</title></path>')
        rows.append(f'<li data-k="{i}" data-v="{money(v)}" data-s="{E(share)} of the price" tabindex="0"><i style="background:{PP_WHEEL[i]}"></i>'
                    f'<span class="ll">{E(head)}' + (f'<em>{E(sub)}</em>' if sub else "") + f'</span><span class="lv">{money(v)}</span><span class="lp">{share}</span></li>')
        a += sweep
    for k in free:                            # a part at $0 (the riser lights): listed, no wedge
        head, sub = _label_split(k)
        rows.append(f'<li class="free"><i></i><span class="ll">{E(head)}' + (f'<em>{E(sub)}</em>' if sub else "") + '</span><span class="lv">$0</span><span class="lp"></span></li>')
    rows.append(f'<li class="total"><i></i><span class="ll">Total, check or ACH</span><span class="lv">{money(p.sell)}</span><span class="lp">100%</span></li>')
    svg = (f'<svg viewBox="0 0 240 240" role="img" aria-label="Price wheel: {E(", ".join(f"{k} {money(v)}" for k, v in paid))}">'
           + "".join(paths)
           + f'<text class="wc-v" x="{cx}" y="{cy + 7}" text-anchor="middle">{money(p.sell)}</text>'
           + f'<text class="wc-l" x="{cx}" y="{cy + 28}" text-anchor="middle">CHECK OR ACH</text></svg>')
    return (f'<section class="pg pp-invest flow{" has-opts" if options_html else ""}" data-fit="dense" id="g-investment" aria-labelledby="inv-h"><div class="pin">'
            f'<header class="sh"><span class="eyebrow">Investment</span><h2 id="inv-h">{title}</h2></header>' + ways
            + '<div class="where"><h3>Where every dollar goes</h3>'
            + f'<div class="inv-grid"><figure class="wheel">{svg}</figure><ol class="legend">' + "".join(rows) + "</ol></div></div>"
            + (f'<div class="opts"><h3>Options</h3>{options_html}</div>' if options_html else "")
            + (f'<div class="next"><h3>Next step</h3>{next_html}</div>' if next_html else "")
            + "</div>" + _folio(foot, "Investment") + "</section>")


def pp_back(spec, key, img, caps, today, viewer_url=None, foot_note: str = "") -> str:
    """The back cover: a dusk view when one is left, the logo, the fine print."""
    br = brand_of(spec)
    online = (f'The interactive 3D model: <a href="{E(viewer_url)}">{E(viewer_url)}</a>' if viewer_url else
              "The interactive 3D model lives at the online version of this document.")
    return (f'<footer class="pg pp-back{"" if img else " bare"}" aria-label="Back cover">' + (f'<div class="pb-hero">{_img(key, img, caps, "pb-img")}<div class="pc-shade"></div></div>' if img else "")
            + f'<div class="pb-in">{brand_logo(br)}<p class="pb-name">{E(brand_footer(spec))}</p>'
            + f'<p class="pb-fine">{E(foot_note)}</p><p class="pb-fine">{online}</p></div></footer>')


PP_CSS = """<style>
/* The photo-led proposal: black, cream and GS gold, Nunito Sans throughout; one deliberate page per section in print. */
body.pp { --display:"Nunito Sans", "Segoe UI", system-ui, sans-serif; --pp-black:#050608; --pp-cream:#f7f3ea;
  --pp-gold:#d49e1b; --pp-gold-hi:#ffe28d; --pp-gold-text:#e9b23c; --pp-mute-dk:#a9a69e; --pp-line-dk:rgba(244,242,236,.16);
  margin:0; background:var(--ground); }
.pp main.pdoc { display:block; }
.pp .pg { position:relative; display:block; }
.pp .pg.flow, .pp .pp-flow { display:flow-root; }
.pp .pin { max-width:980px; margin:0 auto; padding:0 16px; }
.pp .eyebrow { display:block; font-family:var(--display); font-weight:800; font-size:12px; letter-spacing:.3em; text-transform:uppercase; color:var(--gold-ink); }
.pp .sh { display:flex; flex-direction:column; gap:6px; margin:0 0 18px; }
.pp .sh h2 { font-family:var(--display); font-weight:900; font-size:clamp(28px, 4.4vw, 40px); line-height:1.02; letter-spacing:-.015em; margin:0; color:var(--ink); }
.pp .sh .tag { margin:0; color:var(--ink-3); font-size:14px; }
.pp figure { margin:0; }
.pp .ph { position:relative; overflow:hidden; }
.pp .ph img, .pp .po-fig img, .pp .pi-fig img { display:block; width:100%; height:auto; object-fit:cover; border:0; }
.pp figcaption { font-size:12.5px; color:var(--ink-3); margin-top:6px; }
.pp .folio { display:none; }
/* cover */
.pp-cover { background:var(--pp-black); color:#f4f2ec; position:relative; overflow:hidden; }
.pp-cover .pc-hero { position:relative; }
.pp-cover .pc-img { display:block; width:100%; aspect-ratio:8.5/8.7; max-height:94vh; object-fit:cover; }
.pp .pc-shade { position:absolute; inset:0; background:linear-gradient(180deg, rgba(5,6,8,.8) 0%, rgba(5,6,8,0) 20%, rgba(5,6,8,0) 62%, rgba(5,6,8,.72) 86%, #050608 100%); }
.pp-cover .pc-top { position:absolute; top:0; left:0; right:0; display:flex; justify-content:space-between; align-items:flex-start; gap:16px; padding:22px max(16px, 4vw); }
.pp-cover .gslogo, .pp-back .gslogo { display:block; height:56px; width:auto; }
.pp-cover .mission { font-family:var(--display); font-weight:700; font-size:11px; letter-spacing:.3em; text-transform:uppercase; color:#f4f2ec; text-align:right; line-height:1.8; }
.pp-cover .pc-title { position:relative; margin-top:-22vw; padding:0 max(16px, 4vw) 28px; display:flex; flex-direction:column; gap:12px; }
.pp-cover .eyebrow { color:var(--pp-gold-hi); }
.pp-cover h1 { font-family:var(--display); font-weight:900; font-size:clamp(40px, 8.4vw, 84px); line-height:.94; letter-spacing:-.02em; margin:0; color:#fff; text-wrap:balance; }
.pp-cover .who { margin:0; color:var(--pp-mute-dk); font-size:15px; }
.pp-cover .pc-foot { display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; padding:14px max(16px, 4vw) 22px; border-top:1px solid var(--pp-line-dk); margin:0 max(16px, 4vw); padding-left:0; padding-right:0;
  font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--pp-mute-dk); }
/* overview */
.pp-over { background:var(--ground); padding-bottom:40px; }
.pp-over .po-fig { position:relative; }
.pp-over .po-fig img { aspect-ratio:8.5/5.1; max-height:78vh; }
.pp .po-fig figcaption, .pp .pi-fig figcaption, .pp .ph figcaption { position:absolute; left:0; right:0; bottom:0; margin:0; padding:40px max(16px, 4vw) 14px;
  color:#fff; font-size:12.5px; font-weight:600; letter-spacing:.02em; background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.55)); }
.pp-over .pin { padding-top:30px; display:flex; flex-direction:column; gap:20px; }
.pp-over .stand { margin:0; font-family:var(--display); font-weight:700; font-size:clamp(19px, 2.6vw, 24px); line-height:1.32; color:var(--ink); max-width:46ch; text-wrap:pretty; }
.pp .stats { display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); border-top:2px solid var(--pp-gold); }
.pp .stats > div { display:flex; flex-direction:column; gap:4px; padding:12px 10px 0 0; min-width:0; }
.pp .stats > div + div { padding-left:12px; border-left:1px solid var(--line); }
.pp .stats .sv { font-family:var(--display); font-weight:900; font-size:clamp(20px, 2.8vw, 28px); line-height:1; color:var(--ink); white-space:nowrap; }
.pp .stats .sl { font-size:10.5px; letter-spacing:.16em; text-transform:uppercase; color:var(--ink-3); font-weight:800; line-height:1.35; }
.pp-over .po-cols { display:grid; grid-template-columns:minmax(0, 1.55fr) minmax(0, 1fr); gap:28px; align-items:start; }
.pp-over .po-lede p { margin:0; font-size:15px; line-height:1.6; color:var(--ink-2); font-weight:400; }
.pp-over .po-mat h3 { margin:0 0 10px; font-size:11px; letter-spacing:.22em; text-transform:uppercase; color:var(--gold-ink); font-weight:800; }
.pp-over .po-mat ul { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:10px; }
.pp-over .po-mat li { display:grid; grid-template-columns:64px minmax(0, 1fr); gap:12px; align-items:center; }
.pp-over .po-mat i { display:block; width:64px; height:40px; border-radius:2px; box-shadow:inset 0 0 0 1px rgba(0,0,0,.18); }
.pp-over .po-mat span { display:flex; flex-direction:column; gap:1px; font-size:14px; line-height:1.3; color:var(--ink); font-weight:600; }
.pp-over .po-mat b { font-size:10px; letter-spacing:.2em; text-transform:uppercase; color:var(--ink-3); font-weight:800; }
/* spreads */
.pp-photo { background:var(--ground); display:flex !important; flex-direction:column; gap:6px; }
.pp-photo.night { background:var(--pp-black); }
.pp-photo .ph img { aspect-ratio:1500/965; }
.pp-photo.trio .ph img { aspect-ratio:8.5/3.6; }
.pp-photo.solo .ph img { aspect-ratio:8.5/6.6; }
.pp-photo .ph-label { position:absolute; top:0; left:0; right:0; padding:22px max(16px, 4vw) 60px; background:linear-gradient(180deg, rgba(5,6,8,.62), rgba(5,6,8,0)); }
.pp-photo.night .ph-label { background:linear-gradient(180deg, rgba(5,6,8,.8) 0%, rgba(5,6,8,.45) 60%, rgba(5,6,8,0) 100%); }
.pp-photo .ph-label .eyebrow { color:#fff; }
.pp-photo .ph-label p { margin:8px 0 0; max-width:62ch; color:#f4f2ec; font-size:14px; line-height:1.45; font-weight:600; }
/* sheets (cream pages with a header) */
.pp-sheet { background:var(--ground); padding:56px 0 48px; }
.pp .grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
.pp .grid.g1 { grid-template-columns:1fr; }
.pp .grid .ph img { aspect-ratio:1500/965; }
.pp-sheet .ph figcaption { position:static; background:none; padding:0; margin-top:6px; color:var(--ink-3); font-size:12px; font-weight:600; letter-spacing:0; }
.pp .sun { margin-top:26px; }
.pp .sun h3, .pp .where h3, .pp .opts h3, .pp .next h3 { margin:0 0 10px; font-size:11px; letter-spacing:.22em; text-transform:uppercase; color:var(--gold-ink); font-weight:800; }
.pp .sun h3 span { letter-spacing:.02em; text-transform:none; color:var(--ink-3); font-weight:600; margin-left:8px; }
.pp .sunrow { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:8px; }
.pp .sunrow.n4 { grid-template-columns:repeat(4, minmax(0, 1fr)); } .pp .sunrow.n3 { grid-template-columns:repeat(3, minmax(0, 1fr)); }
.pp .sunrow.n2 { grid-template-columns:repeat(2, minmax(0, 1fr)); } .pp .sunrow.n1 { grid-template-columns:minmax(0, 1fr); }
.pp-sheet .big img { aspect-ratio:1500/965; }
.pp-above .big + .grid { margin-top:14px; }
.pp .grid.g3 { grid-template-columns:repeat(3, minmax(0, 1fr)); }
.pp .sunrow .ph img { aspect-ratio:1400/900; }
.pp-inc { padding-top:0; }
.pp-inc .pi-fig { position:relative; margin-bottom:30px; }
.pp-inc .pi-fig img { aspect-ratio:8.5/4.4; max-height:64vh; }
.pp .cards { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px; }
.pp .card { background:var(--paper); border-top:3px solid var(--pp-gold); padding:14px 16px 16px; }
.pp .card h3 { margin:0 0 6px; font-size:11px; letter-spacing:.2em; text-transform:uppercase; color:var(--gold-ink); font-weight:800; }
.pp .card p { margin:0; font-size:14px; line-height:1.5; color:var(--ink); }
.pp-built .big img { aspect-ratio:1400/900; }
.pp-built .grid { margin-top:14px; }
.pp-built .reads-box { margin-top:22px; border-top:2px solid var(--pp-gold); padding-top:14px; }
.pp-built .reads-box .reads { grid-template-columns:150px 1fr; font-size:14px; }
/* investment */
.pp-invest { background:var(--pp-black); color:#f4f2ec; padding:56px 0 48px; margin:0; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.pp-invest .eyebrow { color:var(--pp-gold-hi); }
.pp-invest .sh h2 { color:#fff; }
.pp-invest .ways { display:grid; grid-template-columns:minmax(0, 1fr) minmax(0, 1.25fr); gap:14px; margin-bottom:34px; }
.pp-invest .ways.one { grid-template-columns:minmax(0, 1fr); }
.pp-invest .way { border:1px solid var(--pp-line-dk); padding:20px 22px; display:flex; flex-direction:column; gap:6px; }
.pp-invest .way.lead { border-color:var(--pp-gold); box-shadow:inset 0 3px 0 var(--pp-gold); }
.pp-invest .wl { font-size:11px; letter-spacing:.24em; text-transform:uppercase; color:var(--pp-mute-dk); font-weight:800; }
.pp-invest .wv { font-family:var(--display); font-weight:900; font-size:clamp(38px, 6vw, 56px); line-height:1; letter-spacing:-.02em; color:#fff; font-variant-numeric:tabular-nums; margin:4px 0 6px; }
.pp-invest .way.lead .wv { color:var(--pp-gold-text); }
.pp .opt-prices .lead .pv, .pp .prices .lead .pv, .pp .terms .lead .tv { background:none; -webkit-text-fill-color:currentColor; color:var(--pp-gold-text); }
.pp-invest .ws { font-size:14px; color:#d9d6ce; line-height:1.45; }
.pp-invest .ws b { color:#fff; font-weight:800; }
.pp-invest h3 { color:var(--pp-gold-hi) !important; }
.pp-invest .inv-grid { display:grid; grid-template-columns:minmax(0, 260px) minmax(0, 1fr); gap:34px; align-items:center; }
.pp-invest .wheel svg { display:block; width:100%; max-width:260px; height:auto; margin:0 auto; }
.pp-invest .wheel path { fill:none; stroke-width:24; }
.pp-invest .wheel .wc-v { font-family:var(--display); font-weight:900; font-size:30px; fill:#ffffff; }
.pp-invest .wheel .wc-l { font-family:"Nunito Sans", system-ui, sans-serif; font-weight:800; font-size:9.5px; letter-spacing:.24em; fill:#a9a69e; }
.pp-invest .inv-grid.hover .wheel path:not(.on) { opacity:.3; }
.pp-invest .inv-grid .wheel path.on { stroke-width:30; }
.pp-invest .legend { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; min-width:0; }
.pp-invest .legend li { display:grid; grid-template-columns:12px minmax(0, 1fr) auto 44px; gap:12px; align-items:baseline; padding:9px 4px; border-bottom:1px solid var(--pp-line-dk); font-size:14.5px; color:#f4f2ec; }
.pp-invest .legend li i { width:12px; height:12px; border-radius:2px; display:block; align-self:center; }
.pp-invest .legend .ll { display:flex; flex-direction:column; gap:2px; min-width:0; }
.pp-invest .legend .ll em { font-style:normal; font-size:12.5px; color:var(--pp-mute-dk); }
.pp-invest .legend .lv { font-family:var(--display); font-weight:800; font-size:16px; font-variant-numeric:tabular-nums; text-align:right; }
.pp-invest .legend .lp { color:var(--pp-mute-dk); text-align:right; font-size:13px; font-variant-numeric:tabular-nums; }
.pp-invest .legend li.on { background:rgba(244,242,236,.07); }
.pp-invest .legend li[tabindex]:focus-visible { outline:2px solid var(--pp-gold-hi); outline-offset:-2px; }
.pp-invest .legend li.free i { background:transparent; box-shadow:inset 0 0 0 1px var(--pp-gold); }
.pp-invest .legend li.total { border-bottom:0; border-top:1px solid rgba(244,242,236,.5); font-weight:800; padding-top:12px; }
.pp-invest .legend li.total .lv { font-size:20px; color:var(--pp-gold-text); }
.pp-invest .opts, .pp-invest .next { margin-top:30px; }
.pp-invest .next { border-top:1px solid var(--pp-line-dk); padding-top:16px; }
.pp-invest .next p, .pp-invest .opts p { margin:0 0 6px; max-width:72ch; color:#d9d6ce; font-size:15px; line-height:1.55; }
.pp-invest .opts table { color:#f4f2ec; }
.pp-invest .opts th { color:var(--pp-mute-dk); border-bottom-color:rgba(244,242,236,.4); }
.pp-invest .opts td { border-bottom-color:var(--pp-line-dk); }
.pp-invest .opts .optsum .sub { color:var(--pp-mute-dk); font-size:.94em; }
/* back cover */
.pp-back { background:var(--pp-black); color:#f4f2ec; position:relative; overflow:hidden; margin:0; border:0; padding:0 0 48px; display:block; }
.pp-back .pb-hero { position:relative; }
.pp-back .pb-img { display:block; width:100%; aspect-ratio:8.5/6.4; max-height:80vh; object-fit:cover; }
.pp-back .pb-in { display:flex; flex-direction:column; align-items:center; text-align:center; gap:10px; padding:36px 16px 0; }
.pp-back.bare { padding:120px 0; }
.pp-back .pb-name { margin:6px 0 0; font-family:var(--display); font-weight:800; font-size:13px; letter-spacing:.3em; text-transform:uppercase; color:#f4f2ec; }
.pp-back .pb-fine { margin:0; font-size:12.5px; color:var(--pp-mute-dk); max-width:70ch; }
.pp-back .pb-fine a { color:var(--pp-gold-hi); }
/* the rest of the proposal's blocks (options, schedule, confirm, the option renders, 3D) sit on cream sheets */
.pp .pp-flow { background:var(--ground); padding:48px 0 40px; }
.pp .pp-flow .gal { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
@media (max-width:760px) {
  .pp .stats { grid-template-columns:repeat(3, minmax(0, 1fr)); row-gap:14px; }
  .pp .stats > div:nth-child(4) { padding-left:0; border-left:0; }
  .pp-over .po-cols, .pp-invest .ways, .pp-invest .inv-grid, .pp .cards { grid-template-columns:minmax(0, 1fr); }
  .pp .grid, .pp .pp-flow .gal { grid-template-columns:minmax(0, 1fr); }
  .pp .sunrow { grid-template-columns:repeat(3, minmax(0, 1fr)); }
  .pp-cover .pc-img { aspect-ratio:4/5; }
  .pp-cover .pc-title { margin-top:-38vw; }
  .pp-cover .gslogo { height:40px; }
  .pp-cover .mission { letter-spacing:.18em; font-size:10px; }
  .pp-photo.trio .ph img { aspect-ratio:16/9; }
}
@media print {
  @page { size:Letter; margin:0; }
  body.pp { background:var(--pp-cream); }
  .pp .pg { width:8.5in; height:11in; overflow:hidden; break-after:page; page-break-after:always; break-inside:avoid; margin:0; }
  .pp .pg.flow { height:auto; min-height:11in; overflow:visible; break-inside:auto; }
  .pp .pg:last-child { break-after:auto; page-break-after:auto; }
  .pp .pin { max-width:none; padding:0 0.6in; }
  .pp .folio { display:flex; justify-content:space-between; position:absolute; left:0.6in; right:0.6in; bottom:0.32in; font-size:8px; letter-spacing:.2em;
    text-transform:uppercase; color:#8a8172; font-weight:700; }
  .pp .eyebrow { font-size:9.5px; }
  .pp .sh { margin-bottom:0.16in; }
  .pp .sh h2 { font-size:30px; }
  .pp .sh .tag { font-size:11px; }
  /* cover */
  .pp-cover .pc-img { aspect-ratio:auto; height:8.7in; max-height:none; }
  .pp-cover .pc-top { padding:0.42in 0.6in 0; }
  .pp-cover .gslogo { height:0.66in; }
  .pp-cover .mission { font-size:8.5px; }
  .pp-cover .pc-title { position:absolute; left:0.6in; right:0.6in; bottom:1.0in; margin:0; padding:0; gap:0.1in; }
  .pp-cover .eyebrow { font-size:10px; }
  .pp-cover h1 { font-size:64px; }
  .pp-cover .who { font-size:12.5px; }
  .pp-cover .pc-foot { position:absolute; left:0.6in; right:0.6in; bottom:0.42in; margin:0; padding:0.12in 0 0; font-size:7.5px; }
  /* overview */
  .pp-over { padding:0 0 0.62in; }
  .pp-over .po-fig img { aspect-ratio:auto; height:5.05in; max-height:none; }
  .pp .po-fig figcaption, .pp .pi-fig figcaption, .pp .ph figcaption { padding:0.4in 0.6in 0.16in; font-size:9px; }
  .pp-over .pin { padding-top:0.32in; gap:0.2in; }
  .pp-over .stand { font-size:17px; line-height:1.34; max-width:none; }
  .pp .stats > div { padding-top:0.1in; }
  .pp .stats .sv { font-size:23px; }
  .pp .stats .sl { font-size:7.5px; }
  .pp-over .po-cols { gap:0.32in; }
  .pp-over .po-lede p { font-size:11.2px; line-height:1.58; }
  .pp-over .po-mat h3 { font-size:8.5px; margin-bottom:0.08in; }
  .pp-over .po-mat ul { gap:0.09in; }
  .pp-over .po-mat li { grid-template-columns:0.62in minmax(0, 1fr); gap:0.1in; }
  .pp-over .po-mat i { width:0.62in; height:0.36in; }
  .pp-over .po-mat span { font-size:10.5px; }
  .pp-over .po-mat b { font-size:7px; }
  .pp-over.tight .po-fig img { height:4.2in; }
  .pp-over.nolede .po-fig img { height:6.3in; }
  .pp-over.tighter .po-fig img { height:3.4in; }
  .pp-over.tighter .po-lede p { font-size:9.6px; line-height:1.45; }
  .pp-over.tighter .po-cols { grid-template-columns:minmax(0, 1.9fr) minmax(0, 1fr); }
  .pp-over.tight .pin { padding-top:0.24in; gap:0.14in; }
  .pp-over.tight .po-lede p { font-size:10.2px; line-height:1.5; }
  .pp-over.tight .stand { font-size:15px; }
  /* spreads */
  .pp-photo { gap:0.06in; }
  .pp-photo .ph img { aspect-ratio:auto; height:5.47in; }
  .pp-photo.trio .ph img { height:3.62in; }
  .pp-photo.solo .ph img { height:8.2in; }
  .pp-photo .ph-label { padding:0.42in 0.6in 0.7in; }
  .pp-photo .ph-label .eyebrow { font-size:10px; }
  .pp-photo .ph-label p { font-size:11px; max-width:5.6in; }
  .pp-photo .folio { color:rgba(255,255,255,.78); z-index:2; }
  .pp-photo .ph figcaption { padding-bottom:0.2in; }
  .pp-photo .ph:last-of-type figcaption { padding-bottom:0.55in; }
  /* sheets */
  .pp-sheet { padding:0.62in 0 0.7in; }
  .pp .grid { gap:0.16in 0.14in; }
  .pp .grid .ph figcaption, .pp-sheet .big figcaption, .pp .sunrow .ph figcaption { font-size:8.5px; margin-top:0.05in; }
  .pp .sunrow .ph figcaption { font-size:7.5px; line-height:1.3; }
  .pp-above .big img { aspect-ratio:auto; height:4.55in; }
  .pp-above .big + .grid { margin-top:0.16in; }
  .pp .sun { margin-top:0.26in; }
  .pp .sun h3, .pp .where h3, .pp .opts h3, .pp .next h3 { font-size:8.5px; margin-bottom:0.08in; }
  .pp .sun h3 span { font-size:8.5px; }
  .pp .sunrow { gap:0.07in; }
  .pp-inc { padding-top:0; }
  .pp-inc.noimg { padding-top:0.62in; }
  .pp-inc .pi-fig { margin-bottom:0.3in; }
  .pp-inc .pi-fig img { aspect-ratio:auto; height:4.7in; max-height:none; }
  .pp-inc.rows-m .pi-fig img { height:3.6in; } .pp-inc.rows-l .pi-fig img { height:2.6in; }
  .pp .cards { gap:0.12in; }
  .pp .card { padding:0.14in 0.17in 0.16in; break-inside:avoid; background:#fffdf8; }
  .pp .card h3 { font-size:8.5px; margin-bottom:0.06in; }
  .pp .card p { font-size:11px; line-height:1.48; }
  .pp-built .reads-box { margin-top:0.2in; padding-top:0.12in; }
  .pp-built.long .big img { aspect-ratio:auto; height:4.3in; object-fit:cover; }
  .pp-built.long .grid { display:none; }
  .pp-built .reads-box .reads { grid-template-columns:1.3in 1fr; gap:3px 12px; font-size:10px; }
  .pp-built .reads-box .reads dt { font-size:8.5px; }
  /* investment */
  .pp-invest { padding:0.62in 0 0.75in; }
  .pp-invest .ways { gap:0.14in; margin-bottom:0.42in; }
  .pp-invest .way { padding:0.22in 0.24in 0.24in; }
  .pp-invest .wl { font-size:8.5px; }
  .pp-invest .wv { font-size:50px; }
  .pp-invest .ws { font-size:11px; }
  .pp-invest .inv-grid { grid-template-columns:2.7in minmax(0, 1fr); gap:0.36in; }
  .pp-invest .wheel svg { max-width:2.7in; }
  .pp-invest .legend li { font-size:11.2px; padding:0.085in 0.03in; gap:0.1in; grid-template-columns:9px minmax(0, 1fr) auto 0.36in; }
  .pp-invest .legend li i { width:9px; height:9px; }
  .pp-invest .legend .ll em { font-size:9.2px; }
  .pp-invest .legend .lv { font-size:12.5px; }
  .pp-invest .legend .lp { font-size:9.5px; }
  .pp-invest .legend li.total .lv { font-size:15px; }
  .pp-invest .opts, .pp-invest .next { margin-top:0.3in; }
  .pp-invest .next p, .pp-invest .opts p { font-size:12px; }
  .pp-invest .opts table { font-size:10px; }
  .pp-invest .folio { color:#a9a69e; }
  .pp-invest:not(.has-opts) .pin { display:flex; flex-direction:column; min-height:9.6in; }
  .pp-invest:not(.has-opts) .next { margin-top:auto; padding-top:0.18in; }
  .pp-invest.has-opts { padding-top:0.5in; }
  .pp-invest.has-opts .sh { margin-bottom:0.12in; }
  .pp-invest.has-opts .ways { margin-bottom:0.24in; }
  .pp-invest.has-opts .way { padding:0.14in 0.2in 0.16in; }
  .pp-invest.has-opts .wv { font-size:40px; }
  .pp-invest.has-opts .inv-grid { grid-template-columns:2.1in minmax(0, 1fr); gap:0.3in; }
  .pp-invest.has-opts .wheel svg { max-width:2.1in; }
  .pp-invest.has-opts .legend li { padding:0.05in 0.03in; font-size:10.5px; }
  .pp-invest.has-opts .opts, .pp-invest.has-opts .next { margin-top:0.2in; }
  .pp-invest.has-opts .next p, .pp-invest.has-opts .opts p { font-size:10.5px; line-height:1.45; }
  .pp-invest.has-opts .opts td, .pp-invest.has-opts .opts th { padding-top:3px; padding-bottom:3px; font-size:10px; }
  .pp-invest.dense { padding-top:0.42in; padding-bottom:0.5in; }
  .pp-invest.dense .sh h2 { font-size:26px; }
  .pp-invest.dense .ways { margin-bottom:0.16in; }
  .pp-invest.dense .way { padding:0.1in 0.18in 0.12in; gap:3px; }
  .pp-invest.dense .wv { font-size:34px; margin:2px 0 3px; }
  .pp-invest.dense .ws { font-size:10px; }
  .pp-invest.dense .inv-grid { grid-template-columns:1.8in minmax(0, 1fr); }
  .pp-invest.dense .wheel svg { max-width:1.8in; }
  .pp-invest.dense .legend li { padding:0.03in 0.03in; font-size:10px; }
  .pp-invest.dense .legend .ll em { font-size:8.5px; }
  .pp-invest.dense .opts, .pp-invest.dense .next { margin-top:0.14in; }
  .pp-invest.dense .next p, .pp-invest.dense .opts p { font-size:10px; }
  /* an option's head: the title across the top, its prices under it */
  body.pp .opt-head { grid-template-columns:minmax(0, 1fr); gap:0.1in; align-items:start; }
  body.pp .opt-head h3 { font-size:26px; }
  body.pp .opt-prices { justify-self:start; }
  /* back cover */
  .pp-back { padding:0; }
  .pp-back .pb-img { aspect-ratio:auto; height:6.6in; max-height:none; }
  .pp-back .pb-in { position:absolute; left:0.6in; right:0.6in; bottom:0.9in; padding:0; gap:0.1in; }
  .pp-back.bare .pb-in { bottom:auto; top:50%; transform:translateY(-50%); }
  .pp-back .gslogo { height:0.9in; margin-bottom:0.12in; }
  .pp-back .pb-name { font-size:10px; }
  .pp-back .pb-fine { font-size:9px; }
  /* the other blocks */
  .pp .pp-flow { padding:0.62in 0 0.6in; }
  .pp .pp-flow h2.kicker { break-before:auto; page-break-before:auto; margin-top:0; }
  .pp .pp-flow .gal { display:grid; gap:0.14in; }
  .pp .pp-flow .gal figure { width:auto; margin:0; display:block; }
  .pp .pp-3d { display:none; }
}
</style>"""


def _scope(css: str) -> str:
    """Every .pp rule under body.pp, so it outranks the shared proposal styles (CSS, PRINT_CSS, OPTIONS_CSS)."""
    return re.sub(r"(?m)(^\s*|,\s*)\.pp(?=[ -])", lambda m: m.group(1) + "body.pp" + ("" if css[m.end()] == " " else " .pp"), css)


PP_CSS = _scope(PP_CSS)
