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
