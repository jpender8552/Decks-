"""The build set: drawing sheets (SVG), the 3D model, rendered stills, and the step-by-step build pages —
all from one Layout. Writes a folder; returns the pieces so the service and the artifact page can embed them."""
from __future__ import annotations

import base64
import html as _html
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .drawings import all_sheets, sheet, sheet_meta, T, R, LN, esc, INK, GOLD, MUTE
from .layout import Layout
from .scene import build_scene, Scene, PHASES
from .takeoff import Takeoff
from .units import ftin
from .viewer import viewer_html

STEP_VIEWS = {1: "step1", 2: "step2", 3: "step3", 4: "step4", 5: "step5", 6: "step6", 7: "step7", 8: "step8"}


def step_sheets(t: Takeoff, L: Layout) -> List[dict]:
    """Build steps generalized from the takeoff: what goes in, how to build it, what to check — per phase."""
    s = L.spec
    timber = s.is_timber
    lines = t.lines
    def items(pred, n=7):
        return [f"({l.net:g}) {l.item}" for l in lines if pred(l)][:n]
    fr = L.frame
    n_posts = L.n_footings
    ft = s.framing.footing_type
    steps = []
    # 1 footings
    steps.append(dict(n=1, code="T-400", title="Footings", still="step1",
        goes_in=items(lambda l: l.category == "Footings" and "Stone" not in l.item),
        how=[f"Call 811 and locate before any hole or pin. Strip the existing deck first." if s.extras.demo_existing else "Call 811 and locate before any hole or pin.",
             "Pull the beam lines from the house wall: " + "; ".join(f"{bl.label} at {ftin(bl.y)} from the reference wall, posts at " + " / ".join(ftin(x) for x in bl.posts_x) for bl in L.beam_lines) + ".",
             {"caisson": f"Auger {n_posts} holes {int(fr.footing_dia_in)}\" x {ftin(fr.footing_depth_in)} (frost {ftin(s.site.frost_depth_in)}), tube to 6\" above grade, cage in, pour, set the 5/8\" anchors wet. Cure 2 days.",
              "diamond_pier": f"Set {n_posts} Diamond Pier heads level at grade on undisturbed soil and drive the 4 pins in each; caps on.",
              "concrete": f"Dig and form {n_posts} piers {int(fr.footing_dia_in)}\" x {ftin(fr.footing_depth_in)}, pour, set the standoff bases wet.",
              "existing": (f"The {n_posts} existing caissons and columns stay. Expose each caisson top, check plumb and cracking, photograph; the engineer confirms the column and caisson before the new beams land on them."
                           if s.framing.existing_posts else
                           f"The {n_posts} existing caissons stay. Chip each top level, drill and epoxy-set two 5/8\" rods per base (SET-3G), set the standoff bases; the engineer confirms caisson capacity for the new loads.")}[ft]],
        check=["Footings on the layout within 1/2\"; bearing on undisturbed soil" if ft != "existing" else "Every existing caisson sound, level and on the beam line; engineer's sign-off in the file",
               "Frost depth met" if ft not in ("diamond_pier", "existing") else ("Pins fully driven, heads level" if ft == "diamond_pier" else "Epoxy cured before load"), "Photos before backfill"]))
    steps.append(dict(n=2, code="T-401", title="Posts", still="step2",
        goes_in=items(lambda l: l.category == "Lumber" and s.framing.post_size in l.item) + items(lambda l: "post base" in l.item.lower() or "anchor" in l.item.lower()),
        how=([f"The existing stucco columns stay. Strip the old beam off each column top, check the column core and its bearing; new column caps / saddles per the engineer, then the beams land on them."]
             if s.framing.existing_posts else
             [f"{s.framing.post_size} posts on the bases; cut so the beam top lands at the joist bottom (drop beam) or the joist top (flush beam): " + " / ".join(f"{bl.label} posts {ftin(bl.post_len)}" for bl in L.beam_lines) + " — field-measure each.",
              "Plumb both ways, brace, then the caps go on with the beams."] + (["Seal every cut end before it goes up."] if timber and s.framing.end_grain_seal else [])),
        check=["Posts plumb to a string; tops on the beam line", "Every cut end sealed" if timber else "No post in ground contact without a standoff"]))
    if s.extras.stone_bases:
        steps.append(dict(n=3, code="T-402", title="Stone column bases", still="step3",
            goes_in=items(lambda l: "Stone" in l.item),
            how=["Mason after the posts and before the beams or after the frame — owner's call on access. Cement board wrap, lath, scratch, ledgestone, 24\" cap.", "Keep the cap 1/2\" clear of the post; caulk the joint."],
            check=["Stone plumb and square to the deck; caps level", "Sample color approved by the homeowner"]))
    steps.append(dict(n=4, code="T-403", title="Beams", still="step4",
        goes_in=items(lambda l: l.category == "Lumber" and ("6x" in l.item or "4x10x" in l.item and not timber or "4x12" in l.item)) + items(lambda l: "cap" in l.item.lower() and l.category == "Hardware"),
        how=[f"{bl.label}: {ftin(bl.length)} " + (f"in {len(bl.pieces)} pieces spliced over posts" if len(bl.pieces) > 1 else "one piece") + f", {bl.n_posts} posts @ {ftin(max((b - a) for a, b in zip(bl.posts_x, bl.posts_x[1:])) if bl.n_posts > 1 else bl.length)} max" for bl in L.beam_lines]
            + ["Crown up, strung straight, caps screwed off with the SDS screws in the box."],
        check=["Beam top = joist bottom (drop) / joist top (flush)", "Splices land on a post; caps fully fastened"]))
    steps.append(dict(n=5, code="T-404", title="Frame", still="step5",
        goes_in=items(lambda l: l.category == "Lumber" and s.framing.joist_size in l.item, 6) + items(lambda l: l.category in ("Hardware", "Flashing & waterproofing") and any(k in l.item for k in ("hanger", "LedgerLOK", "H2.5", "Vycor", "flashing", "G-Tape", "membrane")), 8),
        how=[t.schedule.get("Ledger", "Ledger per the schedule."),
             "; ".join(f"{z.name}: {len(z.frame.joist_x)} joists @ {z.frame.spacing:g}\" OC x {ftin(z.frame.joist_len)}" for z in L.zones) + ". Crown up, hangers at the ledger" + (", both faces of the flush beam" if any(b.kind == "flush" for b in L.beam_lines) else "") + ".",
             t.schedule.get("Blocking", "Blocking one row over the beam, staggered."), t.schedule.get("Joist tape", "Tape every joist top.")],
        check=["Frame square: diagonals within 1/8\"", "Every hanger fully nailed; ledger fasteners per the schedule", "Tape continuous; photos of the ledger, hangers and footings before decking"]))
    steps.append(dict(n=6, code="T-405", title="Decking", still="step6",
        goes_in=items(lambda l: l.category in ("Decking", "Fasteners", "Fascia")),
        how=[t.schedule.get("Field", ""), t.schedule.get("Face screws", "Borders first, then the field."),
             (L.plan.summary() if L.plan is not None else "Rows per zone: " + " · ".join(f"{z.name} {z.decking.rows}" for z in L.zones)) + ". Borders and breakers first, then the field rows from the outer edge toward the house."],
        check=[f"{ftin(s.deck_gap)} gaps held", "No cut end shows at the outer edge", "Color: every board from the same run"]))
    steps.append(dict(n=7, code="T-406", title="Rail", still="step7",
        goes_in=items(lambda l: l.category == "Rail"),
        how=[t.schedule.get("Rail", "")] + (["Drink rail on TimberTech drink-rail brackets, mitred at every turn, plugs color-matched."] if s.railing.drink_rail else []),
        check=[f"Top of rail {L.rail.height:g}\" above the decking; posts plumb" if L.rail else "—", "Cables tensioned / balusters under 4\" clear", "End of construction"]))
    if s.geometry.cover:
        from .takeoff import cover_size
        along, out, area = cover_size(s)
        ss = s.extras.cover_roof.lower().startswith("standing")
        steps.append(dict(n=8, code="T-407", title="Porch cover", still="step8",
            goes_in=items(lambda l: l.category == "Porch cover", 14),
            how=[f"Cover ledger on the house at the top of the pitch, LedgerLOK 2 rows; 6x6 cedar posts on the deck over blocked joists, (2)2x10 beam at the rail line; 2x8 rafters @ 16\" OC with hurricane ties, {out + 1.5:.1f}' with the 18\" overhang; 2x8 sub-fascia and OSB.",
                 ("High-temp self-adhered underlayment over every sheet, headwall flashing counterflashed into the house wall, eave trim, then the 24 ga snap-lock panels one piece eave to headwall — clips 18\" OC on each seam, no face screws in the field; rake trim and closures last; snow retention bar clamped to the seams 12-18\" above the low eave, the full width."
                  if ss else "Synthetic underlayment, drip edge, starter, architectural shingles 6 nails each, step flashing at the house wall.")]
                + ([f"5\" K gutter on the low eave, hangers 24\" OC, 1/16\" per foot toward the outlets; 2x3 downspouts strapped to the cover posts, offset past the deck edge, down the deck post to a splash block 3'+ from the footing."] if s.extras.cover_gutters else [])
                + ([f"Ceiling: {s.extras.cover_soffit} panels 6\" OC stainless ring-shank at every rafter; " + (f"{s.extras.cover_fascia} fascia and rakes over the 2x8 sub-fascia, color-matched trim screws." if s.extras.cover_fascia else "")] if s.extras.cover_soffit else ["1x6 T&G ceiling, blind-nailed."]),
            check=["Ledger flashed and counterflashed — hose test before the ceiling closes", "Posts plumb over blocking, beam level, rafters tied",
                   "Panels straight, seams engaged full length, no oil-canning; snow bar continuous" if ss else "Shingles straight, ridge cap sealed",
                   "Gutter falls to the outlets, downspouts discharge away from the footings" if s.extras.cover_gutters else "Water sheds clear of the deck edge"]))
    return steps


def buildset_html(t: Takeoff, sheets: List[Tuple[str, str, str]], steps: List[dict], stills: Dict[str, str], viewer_body: str, title: str) -> str:
    """One page: sheets, isometric renders, build steps, embedded 3D."""
    def img(name):
        p = stills.get(name)
        if not p:
            return ""
        data = base64.standard_b64encode(Path(p).read_bytes()).decode()
        return f'<img src="data:image/jpeg;base64,{data}" alt="{esc(name)}">'
    out = [f"<title>{esc(title)}</title>", '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,300;6..12,400;6..12,700;6..12,900&display=swap">',
           '<style>body{margin:0;background:#f5f1e7;color:#141414;font-family:"Nunito Sans",system-ui,sans-serif;} .wrap{max-width:1040px;margin:0 auto;padding:16px;} h1{font-size:22px;margin:0 0 4px;} .k{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#7a5300;font-weight:800;margin:28px 0 8px;} .sheet{margin:0 0 18px;} .sheet svg{width:100%;height:auto;display:block;border:1px solid #d9d2c3;} img{max-width:100%;display:block;border:1px solid #d9d2c3;} .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;} .step{display:grid;grid-template-columns:1.2fr 1fr;gap:16px;margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid #d9d2c3;} .step h3{margin:0 0 6px;font-size:16px;} .step h4{margin:10px 0 4px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#7a5300;} .step ul{margin:0;padding-left:18px;font-size:14px;} .step li{margin:2px 0;} .v3d-root{height:520px;} @media (max-width:640px){.grid,.step{grid-template-columns:1fr;} .v3d-root{height:380px;}}</style>',
           '<div class="wrap">', f"<h1>{esc(title)}</h1>", '<div class="k">Renders</div>', '<div class="grid">', img("yard"), img("corner"), img("ondeck"), img("under"), "</div>",
           '<div class="k">Isometric · exploded</div>', '<div class="grid">', img("iso"), img("exploded"), "</div>",
           '<div class="k">Drawing set</div>']
    for num, ttl, svg in sheets:
        out.append(f'<div class="sheet" id="{num}">{svg}</div>')
    out.append('<div class="k">Build steps</div>')
    for st in steps:
        out.append(f'<div class="step"><div>{img(st["still"])}</div><div><h3>{st["code"]} · Step {st["n"]} · {esc(st["title"])}</h3>'
                   + '<h4>Goes in</h4><ul>' + "".join(f"<li>{esc(g)}</li>" for g in st["goes_in"]) + "</ul>"
                   + '<h4>How</h4><ul>' + "".join(f"<li>{esc(h)}</li>" for h in st["how"] if h) + "</ul>"
                   + '<h4>Check</h4><ul>' + "".join(f"<li>{esc(c)}</li>" for c in st["check"]) + "</ul></div></div>")
    out.append('<div class="k">3D model — drag to orbit, wheel or pinch to zoom, steps and exploded view below</div>')
    out.append(viewer_body)
    out.append("</div>")
    return "\n".join(out)


def build_set(t: Takeoff, flags, out_dir: str, render: bool = True, customer: bool = False) -> dict:
    """Write drawings (SVG + HTML), viewer.html, renders/, buildset.html. Returns paths + in-memory pieces."""
    L = t.layout
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    S = build_scene(L)
    if hasattr(L, "parts"):     # composite: the drawing sheets are per part (each in its own frame); the 3D and the steps are the whole deck
        sheets = []
        for i, p in enumerate(L.parts):
            tag = chr(65 + i)
            for num, ttl, svg in all_sheets(p.layout, p.takeoff, p.flags, build_scene(p.layout), customer=customer):
                if num == "G-001" and i > 0:
                    continue
                sheets.append((num if num == "G-001" else f"{num}-{tag}", f"{ttl} — {p.name}", svg))
    else:
        sheets = all_sheets(L, t, flags, S, customer=customer)
    (out / "sheets").mkdir(exist_ok=True)
    for num, ttl, svg in sheets:
        (out / "sheets" / f"{num}.svg").write_text(svg)
    stills: Dict[str, str] = {}
    if render:
        try:
            from .render import render_stills
            stills = render_stills(S, str(out / "renders"))
        except Exception as e:  # no browser / no three.js on this machine: the set still builds without stills
            stills = {}
            (out / "renders_error.txt").write_text(str(e))
    viewer_full = viewer_html(S, None, title=f"{L.spec.job} — 3D")
    (out / "viewer.html").write_text(viewer_full)
    steps = step_sheets(t, L)
    page = buildset_html(t, sheets, steps, stills, viewer_html(S, None, title=f"{L.spec.job} — 3D", standalone=False), f"{L.spec.job} — build set")
    (out / "buildset.html").write_text("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'></head><body>" + page + "</body></html>")
    (out / "scene.json").write_text(json.dumps(S.to_dict()))
    return dict(sheets=sheets, steps=steps, stills=stills, scene=S, viewer=str(out / "viewer.html"), buildset=str(out / "buildset.html"))
