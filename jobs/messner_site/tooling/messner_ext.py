"""Messner as-built permit set — the job-local extension (149 Morning Sun Ave, Mill Valley, Marin County; owner Adam Messner).

A one-off. The GSX engine (decktakeoff/) is NOT changed for this job: everything here wraps it at runtime, only inside
`with active(spec):` — build_messner.py is the only thing that enters that block, and leaving it puts every patched name
and every patched catalog number back. A spec without the `_mx` job fields builds exactly as the engine always does, even
inside the block. The core reads the job spec as usual (unknown keys are ignored), the extension reads the same JSON again
for its own keys, and a job-local extra JSON (messner_extra.json) is deep-merged over both.

Job fields (in the spec's own blocks or the extra JSON; every one defaults to the engine's behaviour):
  railing.post_kind           "fascia": every deck guard post on the outside face of the rim / fascia on the system's fascia-mount
                              bracket — its centre the fascia + the bracket standoff + half a post outboard of the frame face, its foot
                              flush with the bracket's at the rim's bottom edge, its top at the guard height over the deck (IRX:
                              3" x 52" fascia post kits, 6' panels only at 72.43" max on centre, 70" on the stairs)
  railing.fascia_standoff_in  fascia face to the post's inner face (0.75" — the bracket plate, clear of the 0.47" board nose)
  railing.infill              deck runs: "glass" (tempered safety-glass panels in a top rail and a bottom-rail channel between the
                              posts, CRC R308.4.4) | "" (the system's own: IRX horizontal cable)
  railing.glass_note          the glazing as recorded ("1/4\\" tempered, permanently labeled ...")
  railing.stair_infill        "vertical": the stair and landing guards in vertical cable at 3" clear (a 4" sphere cannot pass) between a
                              bottom rail and the top rail on the rake | "rake" (the engine's: the deck infill run on the rake)
  railing.stair_handrail      the graspable handrail on the stairs, apart from the guard: "both" (every railed side) | "one" | "none"
  framing.joist_ties          "H2.5A" (or "H2.5AZ"): that hurricane tie at every joist-to-beam bearing — tagged on S-101 with the
                              count, called out in the A-301 section and detailed on D-505 / 3
  framing.lateral_tie_model   "DTT2Z" (2 x 1,500 lb, CRC R507.9.2) | "DTT1Z" (4 x 750 lb)
  framing.lateral_ties        devices per ledger (None -> 2 for the DTT2Z, 4 for the DTT1Z)
  framing.lateral_tie_positions_ft   x of each device along the house as built (ft from the left frame face); [] -> within 24" of
                              each end, on the first joists in from the ends
  framing.blocking_midspan    a solid blocking row at mid-span of every joist span too (the row over each drop beam is always there)
  framing.knee_brace_size     "4x4" | "4x6" | "6x6" (the engine draws 4x4)
  framing.knee_brace_bolts    how each end is bolted, as built ("(2) 1/2\\" x 7-1/2\\" HDG through-bolts each end")
  extras.as_built             an existing deck documented as built (a legalization): G-001's scope and as-built note, AS-BUILT on
                              every title block, the notes from the code and the record — no new-work, sales or house-standard words
  extras.as_built_note        G-001's as-built line ("" -> dimensions and members field-verified from the as-built survey and photos)
  extras.keep_connection_details   as built, the engine's D-502 / D-504 (GSX fastening rules) leave the set; true keeps them
  site.codes                  the adopted codes G-001 lists, one per entry (["2022 California Residential Code (CRC)", ...])
  site.design_criteria        G-001's criteria: a dict of values (live_psf, dead_psf, guard_lb, snow_psf, wind_vult_mph, wind_exposure,
                              risk_category, seismic_sdc, ss, s1, sds, sd1, site_class, footing_min_in, soil_psf; any other key is a
                              row of its own) or [[label, text], ...] rows over the engine's
  site.wui (or wui_fire_zone) WUI notes on G-001: CRC R337, the decking per R337.9 (site.wui_listing, as recorded), the rail
  brand                       {"dir": "jobs/messner_site/brand"} (default: brand.json, logo.svg / logo-ink.svg there, plus the
                              private lines_append file kept out of the repo) or {"name", "short", "lines", "logo"}
  photos                      [{"img": path, "caption": str, "callouts": [{"x": 0..1, "y": 0..1, "label": str}]}] -> A-501.. sheets
"""
from __future__ import annotations

import base64
import contextlib
import copy
import html as _html
import io
import json
import math
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent              # jobs/messner_site/tooling
SITE_DIR = HERE.parent                              # jobs/messner_site
REPO = SITE_DIR.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import decktakeoff                                  # noqa: E402
from decktakeoff import buildset as BS, catalog as CAT, drawings as DW, layout as LY, page as PG, scene as SC, takeoff as TK   # noqa: E402
from decktakeoff.scene import Box, rot_box          # noqa: E402
from decktakeoff.spec import DeckSpec, RailOpening  # noqa: E402
from decktakeoff.units import ftin                  # noqa: E402

IN = 1 / 12.0
PRIVATE_BRAND = Path(os.environ.get("MESSNER_BRAND_PRIVATE") or
                     "/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad/messner/brand/private.json")
VERT_CLEAR_IN, VERT_DIA_IN = 3.0, 0.1875            # vertical cable: 3" clear between 3/16" cables, so a 4" sphere cannot pass
HANDRAIL_IN = 36.0                                  # graspable handrail over the nosing line (CRC R311.7.8.1: 34-38")
GLAZING = dict(color="#a9c6da", opacity=0.34, metal=0.1, rough=0.08, label="tempered safety-glass infill panel")

# Fascia-mount facts by rail system (TimberTech Impression Rail Express 3" Fascia Mount Post & Bracket installation guide, 2021, and
# the 2024 rail order guide): the 3" x 52" fascia post kit (post, cap, base insert) in a straight / outside-corner / inside-corner
# bracket kit (bracket + fascia footblock), the bracket's bottom flush with the post's, (4) #14 x 1-1/2" screws bracket to post,
# 6' panels only at 72.43" max on centre, 70" on the stairs, a corner bracket paired with a straight one at the panel's other end.
# The bracket-to-rim fastening is not in the published text we hold: the sheets say "per the manufacturer's installation instructions".
FASCIA_MOUNT = {
    "IRX": dict(post_w=3.0, standoff_in=0.75, post_len_in=52.0, max_ctc=72.43, stair_max_ctc=70.0, panels={72: 70.0},
                name="TimberTech Impression Rail Express", post_kit="3\" x 52\" fascia-mount post kit (post, cap, base insert) AZTIX3X3FP52{c}",
                bracket="fascia-mount bracket kit (bracket + fascia footblock)", skus=dict(straight="AZTIX3X3FBS{c}", outside="AZTIX3X3FBOC{c}", inside="AZTIX3X3FBIC{c}"),
                post_screws="(4) #14 x 1-1/2\" screws bracket to post (supplied)",
                rim_fastening="bracket to the rim and the solid blocking per the manufacturer's installation instructions"),
}
FASCIA_DEFAULT = dict(standoff_in=0.75, name="", post_kit="fascia-mount post", bracket="fascia-mount bracket", skus={},
                      post_screws="the maker's bracket-to-post screws", rim_fastening="bracket to the rim and the solid blocking per the manufacturer's installation instructions")
COLOR_CODE = {"black": "B", "matte black": "B", "white": "W", "bronze": "BR", "dark bronze": "BR"}


# ============================================================================ the job fields
@dataclass
class Ext:
    post_kind: str = ""
    fascia_standoff_in: Optional[float] = None
    infill: str = ""
    glass_note: str = ""
    stair_infill: str = "rake"
    stair_handrail: str = "both"
    joist_ties: str = ""
    lateral_tie_model: str = "DTT1Z"
    lateral_ties: Optional[int] = None
    lateral_tie_positions_ft: List[float] = field(default_factory=list)
    blocking_midspan: bool = False
    knee_brace_size: str = ""
    knee_brace_bolts: str = ""
    as_built: bool = False
    as_built_note: str = ""
    keep_connection_details: bool = False
    codes: List[str] = field(default_factory=list)
    design_criteria: Any = None
    wui: Optional[bool] = None
    wui_listing: str = ""
    brand: Any = None
    photos: List[dict] = field(default_factory=list)
    code_edition: str = ""                      # "2025": the 2025 CRC / CWUIC section numbers (SECTIONS); "" -> the 2022 CRC (or the IRC)
    verify: Any = field(default_factory=dict)   # field-verify items {key: what}: marked (V) where the sheets show them, listed on G-001 (VERIFY_KEYS)
    joist_tie_lines: str = "all"                # where the hurricane ties are: "all" drop beams | "outer" (only the outermost beam line)
    fascia_fastening: str = ""                  # the fascia bracket's fastening as built (over the maker's words)
    stair_guard_in: Optional[float] = None      # the stair guard's height over the nosing line (None -> the deck guard's)
    beam_notes: List[str] = field(default_factory=list)     # one line per beam, from the house out ("B1: the house-side joists hang from a header on it")
    notes: List[dict] = field(default_factory=list)         # the general notes, [{"head", "items": [...]}] -> G-002 (+ G-003 ...)
    site_plan: dict = field(default_factory=dict)           # {"json": siteplan.json (merged into site.plan), "svg": C-100.svg (the site plan sheet)}
    knee_brace_layout: dict = field(default_factory=dict)   # the braces as built, by beam line from the house: {"inner": {"single": [post index, ...],
                                                            #   "y": [...]}, "outer": {...}} — single: one brace toward mid-span, y: both ways along the
                                                            #   beam; {} -> the engine's (both ways at every post). Braces stay in the beam's plane.
    footing_words: str = ""                                 # S-100's footing description as built (over the engine's sizing words)

    @property
    def fascia(self) -> bool:
        return (self.post_kind or "") == "fascia"

    @property
    def glass(self) -> bool:
        return (self.infill or "") == "glass"

    @property
    def vertical(self) -> bool:
        return (self.stair_infill or "") == "vertical"

    @property
    def tie_model(self) -> str:
        return (self.lateral_tie_model or "DTT1Z").upper()

    @property
    def tie_count(self) -> int:
        return int(self.lateral_ties) if self.lateral_ties is not None else (2 if self.tie_model.startswith("DTT2") else 4)

    @property
    def tie_lb(self) -> str:
        return "1,500" if self.tie_model.startswith("DTT2") else "750"

    @property
    def brace(self) -> str:
        return self.knee_brace_size or "4x4"

    @property
    def joist_tie(self) -> str:
        return self.joist_ties or "H2.5AZ"

    @property
    def callouts(self) -> bool:
        """The S-101 / A-301 hardware callouts and D-505: on whenever the job uses any of the hardware or guard options."""
        return bool(self.joist_ties or self.lateral_ties is not None or self.tie_model != "DTT1Z" or self.lateral_tie_positions_ft or self.blocking_midspan
                    or self.knee_brace_size or self.knee_brace_bolts or self.fascia or self.glass or self.vertical)


_FIELDS = {"railing": ("post_kind", "fascia_standoff_in", "infill", "glass_note", "stair_infill", "stair_handrail", "fascia_fastening", "stair_guard_in"),
           "framing": ("joist_ties", "lateral_tie_model", "lateral_ties", "lateral_tie_positions_ft", "blocking_midspan", "knee_brace_size", "knee_brace_bolts",
                       "joist_tie_lines", "beam_notes", "knee_brace_layout", "footing_words"),
           "extras": ("as_built", "as_built_note", "keep_connection_details", "verify", "notes"),
           "site": ("codes", "design_criteria", "wui", "wui_listing", "as_built", "code_edition", "site_plan")}

# the code sections the sheets cite, by edition (2025: the 2025 CRC renumbered the guards, stairs, handrails, glazing and lighting
# sections, and moved the wildfire rules to the 2025 CWUIC)
SECTIONS = {
    "2022": dict(code="2022 CRC", guard="R312.1", guard_where="R312.1.1", guard_height="R312.1.2", openings="R312.1.3", glazing="R308.4.4", glazing_mark="R308.1",
                 stairs="R311.7", stair_width="R311.7.1", handrail="R311.7.8", stair_light="R303.7", wui="CRC R337", wui_deck="CRC R337.9", wui_flash="",
                 footing_depth="R403.1.4", ledger="R507.9.1.3", ledger_flash="R507.2.4", asce="ASCE 7-16"),
    "2025": dict(code="2025 CRC", guard="R321.1", guard_where="R321.1.1", guard_height="R321.1.2", openings="R321.1.3", glazing="R324.4.4", glazing_mark="R324.1",
                 stairs="R318.7", stair_width="R318.7.1", handrail="R320", stair_light="R325.7", wui="CWUIC Ch. 5", wui_deck="CWUIC 504.7.3", wui_flash="CWUIC 504.7.3.1",
                 footing_depth="R507.3.2", ledger="R507.9.1.3", ledger_flash="R507.9.1.5 / R703.4", asce="ASCE 7-22"),
}
# field-verify keys (extras.verify): where each is marked (V)
VERIFY_KEYS = ("deck_edge", "height", "border_color", "ledger", "ledger_flashing", "beam_positions", "species", "splices", "post_stations", "post_lengths",
               "post_caps", "knee_brace_bolts", "footings", "lateral_ties", "joist_ties", "guard_system", "guard_blocking", "glass_marks", "stair_landing", "stair_base")


def _merge(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def ext_from(merged: dict, base_dir: Optional[Path] = None) -> Ext:
    """The job fields from a spec dict (its blocks + top-level "brand" / "photos"); photo paths resolve against base_dir."""
    kw: Dict[str, Any] = {}
    for blk, names in _FIELDS.items():
        b = merged.get(blk) or {}
        for n in names:
            if n in b:
                kw[n] = b[n]
    if not kw.get("wui") and (merged.get("site") or {}).get("wui_fire_zone"):
        kw["wui"] = True
    for k in ("brand", "photos"):
        if k in merged:
            kw[k] = merged[k]
    if isinstance(kw.get("verify"), list):
        kw["verify"] = {str(k): "" for k in kw["verify"]}
    ph = []
    for p in kw.get("photos") or []:
        p = dict(p)
        img = Path(str(p.get("img", "")))
        if not img.is_absolute():
            img = next((q for q in ((base_dir or REPO) / img, REPO / img) if q.exists()), (base_dir or REPO) / img)
        p["img"] = str(img)
        ph.append(p)
    kw["photos"] = ph
    return Ext(**kw)


def load_job(spec_path, extra_path=None, extra: Optional[dict] = None) -> Tuple[DeckSpec, Ext]:
    """The job: the core DeckSpec (the engine reads it as always) with the job fields attached as spec._mx. The core fields the
    extension drives are set here: the tie count (framing.lateral_ties), the WUI flag, the post kind."""
    spec_path = Path(spec_path)
    raw = json.load(open(spec_path))
    ex = json.load(open(extra_path)) if extra_path else (extra or {})
    merged = _merge(raw, ex)
    ext = ext_from(merged, Path(extra_path).resolve().parent if extra_path else spec_path.resolve().parent)
    if isinstance(ext.notes, str):                               # the notes in a file of their own, beside the spec
        nf = Path(ext.notes) if Path(ext.notes).is_absolute() else spec_path.resolve().parent / ext.notes
        d = json.load(open(nf))
        ext.notes = d.get("notes", []) if isinstance(d, dict) else d
    spec = DeckSpec.from_dict(merged)
    if ext.lateral_ties is not None or ext.tie_model != "DTT1Z":
        spec.framing.lateral_ties = ext.tie_count
    if ext.wui:
        spec.site.wui_fire_zone = True
    if ext.fascia:
        spec.railing.post_kind = "fascia"
    sp_json = Path(str((ext.site_plan or {}).get("json") or ""))
    if str(sp_json) and sp_json.is_file():                       # the site-plan agent's plan frame: the engine's C-100 draws it
        d = json.load(open(sp_json))
        d = d.get("plan", d)
        if isinstance(d, dict) and d.get("parcel"):
            spec.site.plan = _merge(spec.site.plan or {}, d)
    spec._mx = ext
    return spec, ext


def _ext(spec) -> Optional[Ext]:
    return getattr(spec, "_mx", None) if spec is not None else None


def _ca(spec, ext: Optional[Ext] = None) -> bool:
    """A California job: the sheets cite the 2022 CRC where the engine cites the IRC."""
    ext = ext or _ext(spec)
    st = (spec.site.state or "").strip().upper()
    return st in ("CA", "CALIFORNIA") or any("california" in c.lower() or "(crc)" in c.lower() for c in ((ext.codes if ext else []) or []))


def _code(spec) -> str:
    return "CRC" if _ca(spec) else "IRC"


def _ed(spec) -> str:
    ext = _ext(spec)
    if ext and ext.code_edition:
        return str(ext.code_edition)
    return "2025" if any("2025" in c for c in ((ext.codes if ext else []) or [])) else "2022"


def _sec(spec, key: str) -> str:
    """A code section as this job cites it ("R321.1.2"); California only — the IRC keeps the engine's own."""
    return SECTIONS.get(_ed(spec), SECTIONS["2022"]).get(key, "") if _ca(spec) else SECTIONS["2022"].get(key, "")


def _v(key: str) -> str:
    """ (V) when the job lists `key` among its field-verify items."""
    ext = _CTX.get("ext")
    return " (V)" if ext is not None and key in (ext.verify or {}) else ""


# ============================================================================ the brand (PCG): brand.json + logos + the private line
def load_brand(src=None) -> dict:
    """The permit set's brand: {name, short, legal_name, lines, footer, logo_dark / logo_ink (data URIs), accent_a / accent_b}.
    src: None / {"dir": ...} -> jobs/messner_site/brand/ (brand.json, the logos), the private lines_append merged in when that
    file exists (its contact line is never written into the repo); or a dict with the brand itself. No logo: a text mark."""
    if isinstance(src, dict) and (src.get("name") or src.get("short")) and not src.get("dir"):
        d, base = dict(src), REPO
    else:
        bdir = Path((src or {}).get("dir") if isinstance(src, dict) else (src or (SITE_DIR / "brand")))
        bdir = bdir if bdir.is_absolute() else REPO / bdir
        f = bdir / "brand.json"
        d, base = (json.load(open(f)) if f.exists() else {"name": "PCG", "short": "PCG"}), bdir
    lines = [str(x) for x in (d.get("lines") or [])]
    if PRIVATE_BRAND.exists():
        try:
            lines += [str(x) for x in (json.load(open(PRIVATE_BRAND)).get("lines_append") or []) if str(x) not in lines]
        except Exception:
            pass

    def logo(key):
        p = d.get(key)
        if not p:
            return None
        p = Path(p) if Path(p).is_absolute() else base / p
        if not p.exists():
            return None
        mime = {".svg": "image/svg+xml", ".png": "image/png"}.get(p.suffix.lower(), "image/jpeg")
        return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"
    c = d.get("colors") or {}
    name = d.get("name") or d.get("short") or "PCG"
    return dict(name=name, short=d.get("short") or name, legal_name=d.get("legal_name") or name, lines=lines,
                footer=d.get("footer") or " · ".join(lines[:2]) or name, logo_dark=logo("logo"), logo_ink=logo("logo_ink") or logo("logo"),
                aspect=float(d.get("logo_aspect") or 2.014), accent_a=c.get("accent_a") or "#1F4E79", accent_b=c.get("accent_b") or "#2E75B6")


# ============================================================================ runtime patches, active only inside `with active(spec)`
_CTX: Dict[str, Any] = {}


@contextlib.contextmanager
def active(spec: DeckSpec, brand: Optional[dict] = None, date_line: Optional[str] = None):
    """Patch the engine for this job; everything goes back on exit (the names, and the rail system's catalog numbers)."""
    ext = _ext(spec)
    saved: List[Tuple[Any, str, Any]] = []

    def patch(obj, name, new):
        saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, new)
    rs_key = spec.railing.system
    rs_saved = dict(CAT.RAIL_SYSTEMS.get(rs_key) or {})
    prev_ctx = dict(_CTX)
    try:
        _CTX.clear()
        _CTX.update(ext=ext, spec=spec, brand=brand or load_brand(ext.brand if ext else None), date=date_line or date.today().strftime("%B %d, %Y"),
                    renders=bool(prev_ctx.get("renders")), orig=dict(sheet=DW.sheet, sheet_meta=DW.sheet_meta))
        if ext and ext.fascia and rs_key in CAT.RAIL_SYSTEMS:
            fm = fascia_mount(spec)          # the fascia numbers into the system's own entry (IRX and its alias share the dict)
            CAT.RAIL_SYSTEMS[rs_key].update({k: fm[k] for k in ("post_w", "max_ctc", "stair_max_ctc", "panels") if k in fm})
        bl = _wrap_layout(LY.build_layout)
        patch(LY, "build_layout", bl); patch(TK, "build_layout", bl)
        bt = _wrap_takeoff(TK.build_takeoff)
        patch(TK, "build_takeoff", bt); patch(decktakeoff, "build_takeoff", bt)
        bs = _wrap_scene(SC.build_scene)
        for m in (SC, DW, BS):
            patch(m, "build_scene", bs)
        for m in (DW, BS):
            patch(m, "sheet", mx_sheet)
            patch(m, "sheet_meta", mx_sheet_meta)
        patch(DW, "member_key", _wrap_member_key(DW.member_key))
        al = _wrap_all_sheets(DW.all_sheets)
        patch(DW, "all_sheets", al); patch(BS, "all_sheets", al)
        yield ext
    finally:
        for obj, name, val in reversed(saved):
            setattr(obj, name, val)
        if rs_key in CAT.RAIL_SYSTEMS:
            CAT.RAIL_SYSTEMS[rs_key].clear(); CAT.RAIL_SYSTEMS[rs_key].update(rs_saved)
        _CTX.clear(); _CTX.update(prev_ctx)


def fascia_mount(spec) -> dict:
    """The fascia-mount facts for the job's rail system, the job's standoff over the system's, SKUs in the rail's color."""
    ext = _ext(spec)
    key = "IRX" if spec.railing.system in ("IRX", "Impression Rail Express") else spec.railing.system
    d = dict(FASCIA_DEFAULT, **FASCIA_MOUNT.get(key, {}))
    if ext and ext.fascia_standoff_in is not None:
        d["standoff_in"] = float(ext.fascia_standoff_in)
    if ext and ext.fascia_fastening:
        d["rim_fastening"] = ext.fascia_fastening
    c = COLOR_CODE.get((spec.railing.color or "black").strip().lower(), "B")
    d["post_kit"] = d["post_kit"].replace("{c}", c)
    d["skus"] = {k: v.replace("{c}", c) for k, v in (d.get("skus") or {}).items()}
    return d


def fascia_offset_in(spec) -> float:
    """Frame face to a fascia post's centre (inches): the fascia board + the bracket standoff + half the post."""
    sysd = CAT.rail_system_for(spec.railing)
    fas_t = CAT.FASCIA[CAT.decking_facts(spec.decking.collection)["material"]]["thick"] if spec.decking.fascia else 0.0
    return fas_t + fascia_mount(spec)["standoff_in"] + sysd["post_w"] / 2.0


# ---------------------------------------------------------------------------- layout
def _wrap_layout(orig):
    def build_layout(spec):
        L = orig(spec)
        ext = _ext(spec)
        if ext is None or hasattr(L, "parts"):
            return L
        if ext.fascia and L.rail:
            _fascia_rail(spec, L)
        if (ext.fascia or ext.vertical) and L.rail:
            _stair_sections(spec, L)
        if ext.blocking_midspan:
            _midspan_blocking(spec, L)
        L._mx_ties = tie_positions(spec, L)
        return L
    return build_layout


def _offset_edges(edges, g: float):
    """Every edge moved g outward (the outline runs clockwise: outward is (-uy, ux)); neighbours that share a corner are cut to
    meet, an edge next to the house keeps its end on the house line. Returns (edges, {name: extension at the start})."""
    pts = []
    for e in edges:
        Le = e.length or 1.0
        ux, uy = (e.x1 - e.x0) / Le, (e.y1 - e.y0) / Le
        nx, ny = -uy, ux
        pts.append([e.x0 + nx * g, e.y0 + ny * g, e.x1 + nx * g, e.y1 + ny * g, ux, uy])
    n = len(edges)
    cyc = n > 2 and abs(edges[0].x0 - edges[-1].x1) < 0.6 and abs(edges[0].y0 - edges[-1].y1) < 0.6
    ext0 = {}
    out = [list(p) for p in pts]
    for i in range(n):
        j = i + 1 if i + 1 < n else (0 if cyc else None)
        if j is None or not (edges[i].exposed and edges[j].exposed):
            continue
        if abs(edges[i].x1 - edges[j].x0) > 0.6 or abs(edges[i].y1 - edges[j].y0) > 0.6:
            continue
        a, b = pts[i], pts[j]
        den = a[4] * b[5] - a[5] * b[4]
        if abs(den) < 1e-9:
            continue                           # collinear: the plain offset points already meet
        t = ((b[0] - a[0]) * b[5] - (b[1] - a[1]) * b[4]) / den
        cx, cy = a[0] + a[4] * t, a[1] + a[5] * t
        out[i][2], out[i][3] = cx, cy
        out[j][0], out[j][1] = cx, cy
    new = []
    for e, p, q in zip(edges, pts, out):
        ext0[e.name] = (q[0] - p[0]) * p[4] + (q[1] - p[1]) * p[5]     # negative: the start moved back (a convex corner)
        new.append(LY.Edge(e.name, q[0], q[1], q[2], q[3], e.exposed))
    return new, ext0


def _fascia_rail(spec, L) -> None:
    """Re-lay the deck guard on the fascia post line: the engine's own rail layout run on the frame grown outward by the post's
    offset, so every corner post lands outside its corner, every free end stays 2-1/2" from the house and every stair opening
    keeps its side; the bays stay under the bracket's 72.43" (IRX 6' panels). Deck-edge LF stays the engine's."""
    old = L.rail
    d = fascia_offset_in(spec)
    g = LY.RAIL_POST_INSET + d
    sp = copy.copy(spec)
    sp.railing = copy.copy(spec.railing)
    if not L.multi:
        sides = spec.railing.sides or []
        gl, gr, gf = (g if "left" in sides else 0.0), (g if "right" in sides else 0.0), (g if "front" in sides else 0.0)
        sh = lambda o: RailOpening(o.side, o.start_in + (gl if o.side == "front" else 0.0), o.length_in, o.reason)
        sp.railing.openings = [sh(o) for o in spec.railing.openings]
        rl = LY.rail_layout(sp, L.finished_w + gl + gr, L.finished_d + gf, [sh(st.opening) for st in L.stairs])
        for p in rl.posts:
            p.x = round(p.x - gl, 2)
    else:
        edges = L.outline_edges or L.edges
        off, e0 = _offset_edges(edges, g)
        first = {}                              # a collinear run's openings are measured from its first edge's start
        for i, e in enumerate(edges):
            pv = edges[i - 1] if i else None
            coll = pv is not None and abs((pv.x1 - pv.x0) * (e.y1 - e.y0) - (pv.y1 - pv.y0) * (e.x1 - e.x0)) < 1e-6 and abs(pv.x1 - e.x0) < 0.6 and abs(pv.y1 - e.y0) < 0.6
            first[e.name] = first[pv.name] if coll else e.name
        flip = {e.name: abs(e.x1 - e.x0) < 0.01 and e.y1 < e.y0 for e in edges}
        sh = lambda o: RailOpening(o.side, o.start_in + (0.0 if flip.get(o.side) else -e0.get(first.get(o.side, o.side), 0.0)), o.length_in, o.reason)
        sp.railing.openings = [sh(o) for o in spec.railing.openings]
        rl = LY.rail_layout_edges(sp, off, [sh(st.opening) for st in L.stairs], forced_x=[dv[0] for dv in L.divider_x])
    rl.rail_lf, rl.perimeter_lf, rl.openings = old.rail_lf, old.perimeter_lf, old.openings
    rl.notes = list(old.notes) + [f"fascia-mounted posts {ftin(d)} out from the frame face (fascia + {fascia_mount(spec)['standoff_in']:g}\" bracket + half the post)"]
    L.rail = rl


def _stair_sections(spec, L) -> None:
    """The stair guards at the maker's stair post spacing (IRX: 70" on centre), per flight and side, as the engine counts them."""
    sysd = CAT.rail_system_for(spec.railing)
    cap = sysd.get("stair_max_ctc") or 70.0
    for st in L.stairs:
        secs, posts = [], 0
        for fi, (fg, nr) in enumerate(zip(st.geo.flights, st.flight_rails or [st.stair_rail_sides] * len(st.geo.flights))):
            slope = math.hypot(fg.run_in, fg.rise_in - st.geo.riser_in)
            n = max(1, int(math.ceil(slope / (max(sysd["panels"].values()) + 2))), int(math.ceil(slope / cap - 1e-9)))
            tag = f"stair {st.side}" + (f" flight {fi + 1}" if len(st.geo.flights) > 1 else "")
            for _ in range(int(nr)):
                for _ in range(n):
                    cut = slope / n - sysd["post_w"] - 2 * sysd["bracket_allow"]
                    stock = next((s_ for s_, mx in sorted(sysd["panels"].items()) if cut <= mx + 1e-6), max(sysd["panels"]))
                    secs.append(LY.RailSection(tag, round(slope / n, 2), stock, round(cut, 2), kind="stair"))
            posts += int(nr) * (n + 1)
        if secs:
            st.stair_sections, st.stair_posts = secs, posts


def _midspan_blocking(spec, L) -> None:
    """framing.blocking_midspan: a solid row at mid-span of every joist span (house to beam, beam to beam), none in a cantilever."""
    jb = CAT.actual(spec.framing.joist_size)[0]
    for z in L.zones:
        fr = z.frame
        sups = sorted({jb if fr.ledger else fr.rim_plies * jb} | {b.cl_y for b in fr.beams})
        rows = list(fr.blocking_rows_y)
        spans = list(zip(sups, sups[1:]))
        if str(_ext(spec).blocking_midspan).lower() == "house":    # only the house-side bay (ledger to the first beam)
            spans = spans[:1]
        for a, b in spans:
            m = round((a + b) / 2, 2)
            if b - a > 24 and not any(abs(r - m) < 6 for r in rows):
                rows.append(m)
        fr.blocking_rows_y[:] = sorted(rows)


def tie_positions(spec, L) -> List[Tuple[float, float]]:
    """(x, wall y) of each R507.9.2 device, inches: as built when given, else on the first joists in from each end of every
    ledgered zone, within 24" of the end — one per end for 2 devices, two per end for 4."""
    ext = _ext(spec)
    zl = [z for z in L.zones if z.frame.ledger]
    if not zl or ext is None:
        return []
    if ext.lateral_tie_positions_ft:
        out = []
        for xf in ext.lateral_tie_positions_ft:
            x = float(xf) * 12.0
            z = next((q for q in zl if q.x0 - 0.5 <= x <= q.x0 + q.W + 0.5), zl[0])
            out.append((x, z.wall_y))
        return out
    per_end = max(1, ext.tie_count // 2)
    runs: List[list] = []
    for z in zl:                                                  # adjacent ledgered zones on one wall line: one ledger run
        if runs and abs(runs[-1][-1].wall_y - z.wall_y) < 0.5 and abs(runs[-1][-1].x0 + runs[-1][-1].W - z.x0) < 0.5:
            runs[-1].append(z)
        else:
            runs.append([z])
    out = []
    for run in runs:
        js = sorted(x for z in run for x in (z.x0 + q for q in z.frame.joist_x + z.frame.pf_x))
        a, b = run[0].x0, run[-1].x0 + run[-1].W
        lo = [x for x in js if 0 < x - a <= 24.0][-per_end:] or [a + 12.0]
        hi = [x for x in js if 0 < b - x <= 24.0][:per_end] or [b - 12.0]
        out += [(round(x, 2), run[0].wall_y) for x in lo + hi]
    return out


# ---------------------------------------------------------------------------- takeoff (the BOM wording and the schedule)
def _wrap_takeoff(orig):
    def build_takeoff(spec):
        t = orig(spec)
        if _ext(spec) is not None and not hasattr(t.layout, "parts"):
            _mx_takeoff(t, spec, _ext(spec))
        return t
    return build_takeoff


def _rail_words(spec, L) -> str:
    """The guard as built, for the schedule and the sheets."""
    ext = _ext(spec)
    rl = L.rail
    fm = fascia_mount(spec)
    sysn = fm["name"] or CAT.rail_name(spec.railing.system)
    infill = "tempered safety-glass panels in a top rail and a bottom-rail channel" if ext.glass else ("horizontal stainless cable" if CAT.RAIL_SYSTEMS.get(spec.railing.system, {}).get("cable") else "the system's infill")
    out = [f"{sysn} {spec.railing.color} aluminum guard {rl.height:g}\" — {len(rl.posts)} posts, {len(rl.sections)} bays at " + " / ".join(sorted({ftin(s_.ctc) for s_ in rl.sections})) + " CTC; " + infill]
    if ext.fascia:
        out.append(f"posts fascia-mounted outside the rim on the {fm['bracket']}, {fm['standoff_in']:g}\" off the fascia, the bracket's foot at the rim's bottom edge; "
                   f"{fm['post_screws']}; {fm['rim_fastening']}; solid 2x blocking between the joists behind every post")
    if ext.glass:
        out.append(ext.glass_note or "glazing in a guard is a hazardous location: safety glazing, each lite permanently labeled (" + _code(spec) + " R308.4.4 / R308.1)")
    if ext.vertical and any(st.stair_rail_sides for st in L.stairs):
        out.append("stair and landing guards: vertical cable at 3\" clear between a bottom rail and the top rail" + ("" if ext.stair_handrail == "none" else ", a separate graspable handrail 34-38\" over the nosings"))
    out.append(f"guard: 200 lb concentrated at the top in any direction, infill 50 lb on 1 SF ({_code(spec)} Table R301.5)")
    return "; ".join(out)


def _mx_takeoff(t, spec, ext: Ext) -> None:
    L = t.layout
    jsize = spec.framing.joist_size
    n_dtt = n_tie = 0
    for ln in t.lines:
        if ln.sku == "DTT1Z" and ext.tie_model != "DTT1Z" and ext.tie_model in CAT.PRICEBOOK["hardware"]:
            d = CAT.PRICEBOOK["hardware"][ext.tie_model]
            ln.item, ln.unit_cost, ln.source, ln.sku = d["desc"] + " — lateral load connection", d["each"], d["source"], ext.tie_model
        if ln.sku in ("DTT1Z", "DTT2Z"):
            if getattr(L, "_mx_ties", None):
                ln.net = ln.order = len(L._mx_ties)                 # the devices where they are: per ledger run, not per zone
            n_dtt = ln.net
            ln.why = (f"exact  ({ext.tie_count} per ledger" + (" at the positions as built" if ext.lateral_tie_positions_ft else ", within 24\" of each end")
                      + f", through the ledger and band into a house floor joist — {_code(spec)} R507.9.2, {ext.tie_lb} lb each)")
        if ln.sku == "H2.5AZ" and ext.joist_tie_lines == "outer":
            yo = max(bl.y for bl in L.beam_lines if bl.kind == "drop")
            n_o = sum(len(z.frame.joist_x) + len(z.frame.pf_x) + 2 for z in L.zones for bl in L.beam_lines
                      if bl.kind == "drop" and abs(bl.y - yo) < 0.5 and z.name in bl.zones and any(abs(z.wall_y + b.cl_y - yo) < 0.5 for b in z.frame.beams))
            ln.net = ln.order = n_o
            ln.why = f"exact  ({n_o:g}: every joist and both rims at the outer beam; the inner beam's joists hang from a header)"
        if ln.sku == "H2.5AZ":
            n_tie = ln.net
            if ext.joist_ties and ext.joist_ties.upper() != "H2.5AZ":
                ln.item, ln.sku, ln.source = ln.item.replace("H2.5AZ", ext.joist_ties), ext.joist_ties, ln.source + " (priced as the H2.5AZ)"
            ln.why = ln.why.replace("at each drop beam)", "at each drop beam — every joist-to-beam bearing)")
            if ext.joist_tie_lines == "outer":
                ln.why = ln.why.replace("— every joist-to-beam bearing", "")
        if ext.fascia and ln.category == "Rail" and "post kit" in ln.item:
            fm = fascia_mount(spec)
            pk = {k: sum(1 for p in L.rail.posts if p.kind == k) for k in ("CORNER", "END", "LINE")}
            ln.item = (f"{fm['name'] or CAT.rail_name(spec.railing.system)} {fm['post_kit']} on the {fm['bracket']}: "
                       + " · ".join(x for x in (f"{pk['END'] + pk['LINE']} straight {fm['skus'].get('straight', '')}".strip(), f"{pk['CORNER']} outside corner {fm['skus'].get('outside', '')}".strip() if pk["CORNER"] else "") if x))
            ln.net = ln.order = len(L.rail.posts)
            ln.why = f"exact  ({', '.join(f'{v} {k}' for k, v in sorted(pk.items()) if v)}) — fascia-mounted, solid 2x blocking behind each post"
        if ext.fascia and "HeadLOK" in ln.item:
            ln.item = ln.item.replace("rail posts 4 ea", "fascia-mount brackets into the rim and the solid blocking")
            ln.why = ln.why.replace("needed", "allowance").replace(" x 4)", " x 4 — the bracket's fastening per the manufacturer's installation instructions)")
        if ext.glass and ln.category == "Rail" and "Cable Rail kit" in ln.item:
            ln.item = (f"{fascia_mount(spec)['name'] or 'Impression Rail Express'} glass infill kit 6' x {spec.railing.height_in:g}\" {spec.railing.color} — tempered safety-glass panel, "
                       "top rail, bottom-rail channel, hardware (cut to bay)")
            ln.note = (ln.note + " · " if ln.note else "") + "priced at the cable kit's rate until the glass kit is quoted"
        if ext.vertical and ln.category == "Stairs" and ("stair cable rail kit" in ln.item or "level cable rail kit" in ln.item):
            lvl = "level cable rail kit" in ln.item
            ln.item = re.sub(r"(?:stair|level) cable rail kit (\d+)'", lambda m: f"vertical cable {'level' if lvl else 'stair'} panel kit {m.group(1)}' — bottom rail, vertical "
                             "cables at 3\" clear, hardware, footblock (top rail sold separately)", ln.item)
        if ext.brace != "4x4" and ln.category == "Lumber" and ln.item.startswith("4x4x") and "knee braces" in ln.item:
            stock = int(re.match(r"4x4x(\d+)", ln.item).group(1))
            uc, src = TK._lumber_price(ext.brace, stock, False)
            ln.item, ln.unit_cost, ln.source = ln.item.replace("4x4x", f"{ext.brace}x", 1), uc, src
        if ext.knee_brace_bolts and ln.category == "Hardware" and "— knee braces (" in ln.item:
            ln.category = "_drop"                               # the bolts as built go on one line below
        if ext.as_built and spec.framing.rim_plies == 1 and ln.category == "Hardware" and "HUCQ" in ln.item:
            ln.category = "_gone"                               # a single rim as built: no concealed-flange double hangers
    t.lines = [ln for ln in t.lines if ln.category != "_gone"]
    if ext.knee_brace_bolts and any(ln.category == "_drop" for ln in t.lines):
        n_br = 2 * sum(bl.n_posts for bl in L.beam_lines)
        if ext.knee_brace_layout:
            n_br = sum(len(v.get("single") or []) + 2 * len(v.get("y") or []) for v in ext.knee_brace_layout.values())
        m = re.match(r"\((\d+)\)", ext.knee_brace_bolts.strip())
        nb = n_br * 2 * (int(m.group(1)) if m else 1)
        if ext.knee_brace_layout:
            sm_ = t.summary
            if isinstance(sm_.get("posts"), str):
                sm_["posts"] = re.sub(r"with \w+ knee braces", f"with {n_br} {ext.brace} knee braces in the beam planes", sm_["posts"])
            t.schedule["Knee braces"] = (f"{n_br} {ext.brace} braces at 45° in the planes of the beams, " + "; ".join(
                f"{k} row: " + ", ".join(x for x in ((f"single at posts {', '.join(str(i + 1) for i in v.get('single') or [])}" if v.get("single") else ""),
                                                      (f"both ways at posts {', '.join(str(i + 1) for i in v.get('y') or [])}" if v.get("y") else "")) if x)
                for k, v in ext.knee_brace_layout.items()) + f"; {ext.knee_brace_bolts}")
        uc, src = TK._item("hardware", "bolt_1/2x8")[1:]
        t.lines = [ln for ln in t.lines if ln.category != "_drop"]
        if m:                                                   # a bolt count as built: one line; unknown connections stay off the order
            t.lines.append(TK.Line("Hardware", f"Knee-brace bolts as built: {ext.knee_brace_bolts}", nb, nb + 2, "ea", f"+2  ({n_br} braces x 2 ends)", uc, src))
    if ext.fascia and L.rail:
        n_blk = 2 * len(L.rail.posts)
        blen = L.frame.spacing - CAT.actual(jsize)[0]
        per = max(1, int(96 // (blen + 0.25)))
        nb = int(math.ceil(n_blk / per))
        uc, src = TK._lumber_price(jsize, 8)
        t.lines.append(TK.Line("Lumber", f"{jsize}x8 {CAT.SPECIES_NAMES.get(spec.framing.joist_species, spec.framing.joist_species)} — solid blocking behind the fascia-mounted guard posts",
                               nb, nb + 1, "ea", f"+1  ({n_blk} blocks at {ftin(blen)}: 2 per post between the joists, tight to the rim; {per} per 8')", uc, src))
    if ext.stair_handrail != "none":
        # the graspable handrail apart from the guard: one per railed side of every flight ("both"), or one per flight ("one")
        for st in L.stairs:
            n_hr = sum((int(r) if ext.stair_handrail == "both" else min(1, int(r))) for r in (st.flight_rails or [st.stair_rail_sides] * len(st.geo.flights)))
            for ln in t.lines:
                if ln.category == "Stairs" and "graspable handrail kit" in ln.item and f"({st.side} stair" in ln.item and n_hr:
                    ln.net = ln.order = n_hr
                    ln.why = f"exact  ({n_hr} runs: " + ("both sides of every flight" if ext.stair_handrail == "both" else "one side of every flight") + f", 34-38\" over the nosings — {_code(spec)} R311.7.8)"
    sch = t.schedule
    if ext.knee_brace_size or ext.knee_brace_bolts:
        k = sch.get("Knee braces", "")
        sch["Knee braces"] = re.sub(r"^4x4", ext.brace, k).replace("(1) 1/2\" through-bolt each end", ext.knee_brace_bolts or "(1) 1/2\" through-bolt each end")
    if L.rail:
        sch["Rail"] = _rail_words(spec, L)
    if n_tie:
        sch["Joist ties"] = (f"{ext.joist_tie} at every joist-to-beam bearing on the outer beam: {n_tie:g} ties, the tie's nails in every hole" if ext.joist_tie_lines == "outer" else
                             f"{ext.joist_tie} at every joist-to-beam bearing: {n_tie:g} ties (every joist and both rims at each drop beam), the tie's nails in every hole")
    if n_dtt:
        sch["Lateral"] = (f"{n_dtt:g} x {ext.tie_model}, {ext.tie_lb} lb each, " + ("at the positions as built" if ext.lateral_tie_positions_ft else "within 24\" of each end of the deck")
                          + f", through the ledger and band into a house floor joist ({_code(spec)} R507.9.2)")
    rows = sorted({r for z in L.zones for r in z.frame.blocking_rows_y})
    sch["Blocking"] = (f"Solid {jsize} blocking rows at " + ", ".join(ftin(r) for r in rows) + " from the house (over each beam" + ((", mid-span of the house-side bay" if str(ext.blocking_midspan).lower() == "house" else ", mid-span") if ext.blocking_midspan else "") + ")"
                       + ("; 2 blocks behind each fascia post" if ext.fascia else ""))
    if ext.as_built:
        _as_built_schedule(t, spec, ext)
    sm = t.summary
    if isinstance(sm.get("posts"), str) and ext.brace != "4x4":
        sm["posts"] = sm["posts"].replace("with 4x4 knee braces", f"with {ext.brace} knee braces")
    if L.rail:
        fm = fascia_mount(spec)
        sm["rail"] = (f"{fm['name'] or CAT.rail_name(spec.railing.system)} {L.rail.height:g}\" {spec.railing.color}" + (", glass infill" if ext.glass else "")
                      + (", fascia-mounted posts" if ext.fascia else "") + f": {len(L.rail.sections)} bays, {len(L.rail.posts)} posts, {L.rail.rail_lf:g} LF"
                      + ("; stairs in vertical cable" if ext.vertical else ""))


def _as_built_schedule(t, spec, ext: Ext) -> None:
    """As built: the notes say what the code asks and what was recorded — the engine's house fastening choices (its screws, tapes and
    clips) come off the sheets; a hidden-fastener or fascia system is the maker's, installed per its instructions."""
    sch, code = t.schedule, _code(spec)
    lf = (spec.framing.ledger_fastener or "").lower()
    led = sch.get("Ledger", "")
    m = re.search(r"@ (\d+)\" OC", led)
    words = "1/2\" through-bolts with washers" if "bolt" in lf else "1/2\" lag screws with washers" if "lag" in lf else "fasteners as recorded"
    if led:
        sch["Ledger"] = (f"{spec.ledger_size} ledger to the house band: {words}" + (f" @ {m.group(1)}\" OC" if m else "") + f", 2 rows staggered ({code} R507.9.1.3); "
                         f"flashed at the wall ({code} R507.2.4)")
    fsys = spec.decking.fastener_system or CAT.default_fastener_system(spec.decking.collection, spec.decking.profile)
    if "Field" in sch:
        sch["Field"] = f"{spec.decking.brand} {spec.decking.collection} on {fsys} hidden fasteners at every joist, per the manufacturer's installation instructions"
    for k in ("Face screws", "Fascia", "Picture frame + stairs"):
        if k in sch:
            sch[k] = {"Face screws": "Face-fastened boards (the picture frame, the first row, the stair treads) with the decking maker's color-matched screws, per its instructions",
                      "Fascia": f"{spec.decking.collection} fascia over the rim with the maker's fascia screws, per its instructions",
                      "Picture frame + stairs": "Picture frame and stair treads face-fastened per the decking maker's instructions"}[k]
    if not spec.framing.joist_tape:
        sch.pop("Joist tape", None)


# ---------------------------------------------------------------------------- the scene (3D boxes the sheets and the model share)
def _wrap_scene(orig):
    def build_scene(L):
        S = orig(L)
        if _ext(getattr(L, "spec", None)) is not None and not hasattr(L, "parts"):
            _mx_scene(S, L, _ext(L.spec))
        return S
    return build_scene


def _rake_fn(b: Box):
    """For a rotated stair-rail box: (axis "x" | "y", along-coordinate centre, its half-run in plan, z at an along coordinate)."""
    if b.rot_axis == "x":
        ac, half, k = (b.y0 + b.y1) / 2, (b.y1 - b.y0) / 2 * math.cos(b.rot), -math.tan(b.rot)
    else:
        ac, half, k = (b.x0 + b.x1) / 2, (b.x1 - b.x0) / 2 * math.cos(b.rot), math.tan(b.rot)
    zc = (b.z0 + b.z1) / 2
    return b.rot_axis, ac, half, (lambda a: zc + (a - ac) * k)


def _mx_scene(S, L, ext: Ext) -> None:
    spec = L.spec
    B = S.boxes
    if ext.as_built:
        B[:] = [b for b in B if b.kind != "gravel"]
    zt = spec.geometry.height_in * IN
    dk = CAT.decking_facts(spec.decking.collection)
    bt = dk["thick"] * IN
    jd = CAT.actual(spec.framing.joist_size)[1] * IN
    jbot = zt - bt - jd
    rl = L.rail
    sysd = CAT.rail_system_for(spec.railing)
    pw = sysd["post_w"] * IN
    h = (rl.height if rl else spec.railing.height_in) * IN
    prof = sysd.get("profile") or {}
    trw, trh = prof.get("top", (0.12, 0.08))
    brw, brh = prof.get("bottom", (0.12, 0.08))
    add = lambda *a, **k: B.append(Box(*a, **k))
    # ---- fascia-mounted deck posts: the foot down to the rim's bottom edge, the bracket between the fascia face and the post
    if ext.fascia and rl:
        fas_t = CAT.FASCIA[dk["material"]]["thick"] * IN if spec.decking.fascia else 0.0
        out = fascia_offset_in(spec) * IN
        posts = [(p.x * IN, p.y * IN) for p in rl.posts]
        for b in B:
            if b.kind == "railpost" and abs(b.z0 - zt) < 0.02 and any(abs((b.x0 + b.x1) / 2 - x) < 0.05 and abs((b.y0 + b.y1) / 2 - y) < 0.05 for x, y in posts):
                b.z0, b.tag = jbot, (b.tag or "") + " fascia-mount"
        for e in [e for e in (L.outline_edges or L.edges) if e.exposed and e.length > 1]:
            ex0, ey0, ex1, ey1 = e.x0 * IN, e.y0 * IN, e.x1 * IN, e.y1 * IN
            Le = math.hypot(ex1 - ex0, ey1 - ey0); ux, uy = (ex1 - ex0) / Le, (ey1 - ey0) / Le
            if abs(ux) > 1e-6 and abs(uy) > 1e-6:
                continue                         # an angled side: posts drawn, no bracket
            nx, ny = -uy, ux
            for x, y in posts:
                dd, tt = (x - ex0) * nx + (y - ey0) * ny, (x - ex0) * ux + (y - ey0) * uy
                if abs(dd - out) > 0.1 or not (-out - 0.1 <= tt <= Le + out + 0.1) or out - pw / 2 <= fas_t + 0.005:
                    continue
                xs = [ex0 + ux * a_ + nx * c_ for a_ in (max(0.0, tt - pw / 2), min(Le, tt + pw / 2)) for c_ in (fas_t, out - pw / 2)]
                ys = [ey0 + uy * a_ + ny * c_ for a_ in (max(0.0, tt - pw / 2), min(Le, tt + pw / 2)) for c_ in (fas_t, out - pw / 2)]
                add("railbracket", min(xs), max(xs), min(ys), max(ys), jbot, zt - bt - 0.02, "railmetal", 7, tag="fascia-mount bracket")
    # ---- glass infill on the deck runs: the cable comes out; a bottom-rail channel and a glass panel go in every bay
    if ext.glass and rl:
        B[:] = [b for b in B if not (b.kind == "cable" and (not b.rot or b.rot_axis == "z") and b.z0 >= zt - 0.01)]
        S.materials["glazing"] = dict(GLAZING)
        for (xa, ya), (xb, yb) in SC._rail_pairs(rl):
            Ls = math.hypot(xb - xa, yb - ya)
            if Ls < 2 * pw:
                continue
            ux, uy = (xb - xa) / Ls, (yb - ya) / Ls
            a0, a1 = pw / 2 + 0.03, Ls - pw / 2 - 0.03
            p0, p1 = (xa + ux * a0, ya + uy * a0), (xa + ux * a1, ya + uy * a1)
            if abs(uy) < 1e-6 or abs(ux) < 1e-6:
                hz = abs(uy) < 1e-6
                xr = (min(p0[0], p1[0]), max(p0[0], p1[0])) if hz else (xa - brw / 2, xa + brw / 2)
                yr = (ya - brw / 2, ya + brw / 2) if hz else (min(p0[1], p1[1]), max(p0[1], p1[1]))
                add("botrail", *xr, *yr, zt + 0.25, zt + 0.25 + brh, "railmetal", 7, tag="bottom-rail channel")
                xg = xr if hz else (xa - 0.02, xa + 0.02)
                yg = (ya - 0.02, ya + 0.02) if hz else yr
                add("glasspanel", *xg, *yg, zt + 0.25 + brh, zt + h - trh - 0.01, "glazing", 7, tag="tempered glass infill panel")
            else:
                B.append(rot_box("botrail", p0[0], p0[1], p1[0], p1[1], zt + 0.25, zt + 0.25 + brh, "railmetal", 7, brw, tag="bottom-rail channel"))
                B.append(rot_box("glasspanel", p0[0], p0[1], p1[0], p1[1], zt + 0.25 + brh, zt + h - trh - 0.01, "glazing", 7, 0.04, tag="tempered glass infill panel"))
    # ---- the stairs: vertical cable between a bottom rail and the top rail on the rake, posts at 70", a graspable handrail
    if ext.vertical or ext.stair_handrail != "none":
        _stair_guards(S, L, ext, zt, pw, h)
    # ---- knee braces as built: only in the beam planes, at the posts the job names (framing.knee_brace_layout)
    if ext.knee_brace_layout and spec.framing.knee_braces:
        B[:] = [b for b in B if b.kind != "brace"]
        kb_, kd_ = [v * IN for v in CAT.actual(ext.brace)]
        lg = spec.framing.knee_leg_in * IN
        Lb = lg * math.sqrt(2) + kd_
        lines = sorted([bl for bl in L.beam_lines if bl.kind == "drop"], key=lambda q: q.y)
        named = {"inner": lines[0] if lines else None, "outer": lines[-1] if lines else None}
        for key, lay in ext.knee_brace_layout.items():
            bl = named.get(key)
            if bl is None:
                continue
            y, zb = bl.y * IN, (zt - bt - jd) - bl.depth * IN
            xs = sorted(bl.posts_x)
            mid = (bl.x0 + bl.x1) / 2
            for kind_, idx in (("single", lay.get("single") or []), ("y", lay.get("y") or [])):
                for i in idx:
                    if not 0 <= i < len(xs):
                        continue
                    x = xs[i] * IN
                    dirs = [1 if xs[i] < mid else -1] if kind_ == "single" else [1, -1]
                    for sx in dirs:
                        cx = x + sx * (CAT.actual(spec.framing.post_size)[0] * IN / 2 + lg / 2)
                        B.append(Box("brace", cx - Lb / 2, cx + Lb / 2, y - kb_ / 2, y + kb_ / 2, zb - lg / 2 - kd_ / 2, zb - lg / 2 + kd_ / 2, "timber", 3,
                                     tag=f"{ext.brace} knee brace (along the beam, as built)", rot=sx * math.pi / 4, rot_axis="y"))
    # ---- knee braces in the job's stock
    if ext.brace != "4x4" and not ext.knee_brace_layout:
        b_, d_ = [v * IN for v in CAT.actual(ext.brace)]
        for b in B:
            if b.kind == "brace" and "knee brace" in (b.tag or ""):
                cx, cy, cz = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2
                if b.rot_axis == "y":
                    Lb = b.x1 - b.x0 - (b.z1 - b.z0) + d_
                    b.x0, b.x1, b.y0, b.y1 = cx - Lb / 2, cx + Lb / 2, cy - b_ / 2, cy + b_ / 2
                else:
                    Lb = b.y1 - b.y0 - (b.z1 - b.z0) + d_
                    b.y0, b.y1, b.x0, b.x1 = cy - Lb / 2, cy + Lb / 2, cx - b_ / 2, cx + b_ / 2
                b.z0, b.z1 = cz - d_ / 2, cz + d_ / 2
                b.tag = b.tag.replace("4x4", ext.brace)


def _stair_guards(S, L, ext: Ext, zt: float, pw: float, h: float) -> None:
    """Every stair-rail run (a top rail on the rake): its rake cables become vertical cables at 3" clear between a new bottom rail
    and the top rail, intermediate posts at the stair spacing (70"), and a graspable handrail on brackets inside the guard, 36"
    over the nosing line. The landing guards' pickets become vertical cable with a bottom rail as well."""
    B = S.boxes
    sysd = CAT.rail_system_for(L.spec.railing)
    cap = (sysd.get("stair_max_ctc") or 70.0) * IN
    pitch = (VERT_CLEAR_IN + VERT_DIA_IN) * IN
    hr = h
    treads = [b for b in B if b.kind == "tread"]
    tops = [b for b in B if b.kind == "toprail" and b.rot and b.rot_axis in ("x", "y") and "handrail" not in (b.tag or "")]
    dz = ((ext.stair_guard_in or hr * 12) / 12.0 - hr)            # the stair guard's own height (railing.stair_guard_in) over the engine's
    if abs(dz) > 1e-6:
        for b in B:
            if b in tops or (b.kind == "railpost" and (b.tag or "") == "stair post"):
                b.z1 += dz
                if b in tops:
                    b.z0 += dz
    first_side = {}
    for tr in tops:                                               # one handrail per flight: the first rail of each flight's pair
        k_ = (round(tr.rot, 3), tr.rot_axis, round((tr.y0 + tr.y1) / 2 if tr.rot_axis == "x" else (tr.x0 + tr.x1) / 2, 1))
        first_side.setdefault(k_, tr)
    drop, new = set(), []
    for i_run, tr in enumerate(tops):
        ax, ac, half, z_top = _rake_fn(tr)
        vc = (tr.x0 + tr.x1) / 2 if ax == "x" else (tr.y0 + tr.y1) / 2       # the guard's line across the stair
        lo, hi = ac - half, ac + half                                           # the end posts' centres
        z_tread = lambda a, z_top=z_top: z_top(a) - hr - dz - 0.1                # the tread line (the engine's top rail is hr + 0.1 over it)
        along = lambda b: ((b.y0 + b.y1) / 2) if ax == "x" else ((b.x0 + b.x1) / 2)
        across = lambda b: ((b.x0 + b.x1) / 2) if ax == "x" else ((b.y0 + b.y1) / 2)
        mk = (lambda kind, a0, a1, c0, c1, z0, z1, mat, tag="", rot=0.0: Box(kind, c0, c1, a0, a1, z0, z1, mat, 7, tag=tag, rot=rot, rot_axis="x")) if ax == "x" else \
             (lambda kind, a0, a1, c0, c1, z0, z1, mat, tag="", rot=0.0: Box(kind, a0, a1, c0, c1, z0, z1, mat, 7, tag=tag, rot=rot, rot_axis="y"))
        if ext.vertical:
            for k, b in enumerate(B):
                if b.kind == "cable" and b.rot and abs(b.rot - tr.rot) < 1e-6 and b.rot_axis == ax and abs(across(b) - vc) < 0.05 and lo - 0.3 <= along(b) <= hi + 0.3:
                    drop.add(k)
                if b.kind == "railpost" and (b.tag or "") == "stair post" and abs(across(b) - vc) < 0.05 and lo + 0.3 < along(b) < hi - 0.3:
                    drop.add(k)                  # the engine's mid post: the posts go in at the stair spacing below
            zb = lambda a: z_tread(a) + 0.35                                       # bottom rail 4" over the tread line (a 6" sphere: R312.1.3)
            new.append(mk("botrail", tr.y0 if ax == "x" else tr.x0, tr.y1 if ax == "x" else tr.x1, vc - 0.05, vc + 0.05, zb(ac) - 0.04, zb(ac) + 0.04, "railmetal", "stair bottom rail", tr.rot))
            n_sec = max(1, int(math.ceil((hi - lo) / math.cos(tr.rot) / cap - 1e-9)))
            for k in range(1, n_sec):
                a = lo + (hi - lo) * k / n_sec
                new.append(mk("railpost", a - pw / 2, a + pw / 2, vc - pw / 2, vc + pw / 2, z_tread(a), z_top(a) + 0.1, "railmetal", "stair post"))
            posts_a = [lo + (hi - lo) * k / n_sec for k in range(n_sec + 1)]
            a = lo + pw / 2 + pitch
            while a < hi - pw / 2 - 0.02:
                if all(abs(a - pa) > pw / 2 + 0.01 for pa in posts_a):
                    new.append(mk("cable", a - 0.008, a + 0.008, vc - 0.008, vc + 0.008, zb(a) + 0.04, z_top(a) - 0.05, "cable", "vertical stair cable"))
                a += pitch
        k_ = (round(tr.rot, 3), tr.rot_axis, round(ac, 1))
        if ext.stair_handrail != "none" and (ext.stair_handrail == "both" or first_side.get(k_) is tr):
            near = [t_ for t_ in treads if lo - 0.5 <= along(t_) <= hi + 0.5]
            if near:
                mid = sum(across(t_) for t_ in near) / len(near)
                sgn = 1.0 if mid > vc else -1.0                                    # toward the treads: the handrail is inside the guard
                vh = vc + sgn * (pw / 2 + 2.25 * IN)
                zh = lambda a: z_tread(a) + HANDRAIL_IN * IN
                new.append(mk("toprail", tr.y0 if ax == "x" else tr.x0, tr.y1 if ax == "x" else tr.x1, vh - 0.0625, vh + 0.0625, zh(ac) - 0.0625, zh(ac) + 0.0625, "railmetal",
                              "graspable handrail", tr.rot))
                n_br = max(2, int(math.ceil((hi - lo) / (48 * IN))) + 1)
                for k in range(n_br):
                    a = lo + 0.4 + (hi - lo - 0.8) * k / (n_br - 1)
                    c0, c1 = sorted((vc + sgn * pw / 2, vh))
                    new.append(mk("toprail", a - 0.04, a + 0.04, c0, c1, zh(a) - 0.12, zh(a) - 0.04, "railmetal", "handrail bracket"))
    # landing guards (level): pickets -> vertical cable over a bottom rail
    if ext.vertical:
        for lr in [b for b in B if b.kind == "toprail" and (b.tag or "") == "landing rail"]:
            hz = (lr.x1 - lr.x0) > (lr.y1 - lr.y0)
            c = (lr.y0 + lr.y1) / 2 if hz else (lr.x0 + lr.x1) / 2
            a0, a1 = (lr.x0, lr.x1) if hz else (lr.y0, lr.y1)
            zf = lr.z0 - hr                                                         # the landing surface
            for k, b in enumerate(B):
                bc = (b.y0 + b.y1) / 2 if hz else (b.x0 + b.x1) / 2
                ba = (b.x0 + b.x1) / 2 if hz else (b.y0 + b.y1) / 2
                if b.kind == "baluster" and abs(bc - c) < 0.05 and a0 - 0.01 <= ba <= a1 + 0.01 and b.z0 < lr.z0:
                    drop.add(k)
            new.append(Box("botrail", *((a0, a1, c - 0.05, c + 0.05) if hz else (c - 0.05, c + 0.05, a0, a1)), zf + 0.25, zf + 0.33, "railmetal", 7, tag="landing bottom rail"))
            a = a0 + pitch
            while a < a1 - 0.02:
                new.append(Box("cable", *((a - 0.008, a + 0.008, c - 0.008, c + 0.008) if hz else (c - 0.008, c + 0.008, a - 0.008, a + 0.008)), zf + 0.33, lr.z0 - 0.01, "cable", 7, tag="vertical landing cable"))
                a += pitch
    B[:] = [b for k, b in enumerate(B) if k not in drop] + new


# ============================================================================ the sheets: the PCG title block, as-built words, overlays
T, TH, R, LN, C, PGN, esc = DW.T, DW.TH, DW.R, DW.LN, DW.C, DW.PG, DW.esc
INK, CREAM, MUTE, GOLD = DW.INK, DW.CREAM, DW.MUTE, DW.GOLD
W_, H_ = DW.W_, DW.H_
BLUE = "#3f5d8a"


def mx_sheet_meta(L, customer: bool = False) -> dict:
    """The title block's lines for this job: the brand's, the as-built tag's — never the engine's GSX header line."""
    s = L.spec
    if _ext(s) is None or not _CTX.get("brand"):
        return _CTX["orig"]["sheet_meta"](L, customer)
    ext, br = _ext(s), _CTX["brand"]
    return dict(job_line=f"{s.job} · {s.site.address}, {s.site.city}".strip(" ,·"),
                rev_line=f"{br['short']} · {_CTX['date']} · Rev 0 · " + ("AS-BUILT PERMIT SET" if ext.as_built else "PERMIT SET"),
                footer=f"{br['footer']} · " + ("As built, field-verified" if ext.as_built else "Field verify") + (" · the stamped design governs" if s.extras.engineered else "") + " · Do not scale",
                mx=True)


def mx_sheet(num: str, title: str, sub: str, body: List[str], scale_note: str, meta: dict) -> str:
    """The engine's sheet frame with the job's title block: the brand's logo (or a text mark) and name, the AS-BUILT tag, the
    brand's colors for the engine's gold, the per-sheet overlays (HOOKS) and the as-built / California wording on every word."""
    if not meta.get("mx"):
        return _CTX["orig"]["sheet"](num, title, sub, body, scale_note, meta)
    body = list(body)
    if num in HOOKS:                                            # before the pending callout words are flushed: a hook's own go with them
        body = HOOKS[num](body)
    body += DW._PANEL.pop("labels", [])
    br, ext = _CTX["brand"], _CTX["ext"]
    lw = 34 * br["aspect"]
    rx = W_ - 18 - lw - 12                                      # the job / rev lines right-aligned clear of the logo
    hdr = [R(0, 0, W_, 46, INK, "none", 0), T(18, 27, num, 20, 900, fill=br["accent_b"]), T(110, 22, title.upper(), 15, 900, fill="#f3ead9"),
           T(110, 39, textwrap.shorten(_words(sub), 100, placeholder="…"), 9.5, 400, fill="#d8cfbf"),
           T(rx, 20, textwrap.shorten(meta["job_line"], 56, placeholder="…"), 9.5, 700, "end", "#d8cfbf"), T(rx, 36, meta["rev_line"], 8.5, 400, "end", "#b8b0a2")]
    if ext.as_built:                                            # the AS-BUILT tag, under the sheet number
        hdr += [R(18, 32, 60, 11, br["accent_b"], "none", 0), T(48, 40.6, "AS-BUILT", 7.6, 900, "middle", "#ffffff")]
    if br.get("logo_dark"):
        hdr.append(f'<image href="{br["logo_dark"]}" x="{W_ - 18 - lw:.1f}" y="6" width="{lw:.1f}" height="34" preserveAspectRatio="xMaxYMid meet"/>')
    else:                                                       # no logo: a clean text mark
        hdr += [R(W_ - 18 - lw, 8, lw, 30, "none", br["accent_b"], 1.2), T(W_ - 18 - lw / 2, 28, br["short"], 14, 900, "middle", "#ffffff")]
    room, sn = W_ - 60 - len(meta["footer"]) * 8.6 * 0.5, 9.5
    if len(scale_note) * sn * 0.52 > room:
        sn = max(7.0, room / (len(scale_note) * 0.52))
        if len(scale_note) * sn * 0.52 > room:
            scale_note = textwrap.shorten(scale_note, max(20, int(room / (sn * 0.52))), placeholder="…")
    ftr = [LN(0, H_ - 34, W_, H_ - 34, br["accent_a"], 2), T(18, H_ - 14, _words(scale_note), round(sn, 1), 600, fill=MUTE), T(W_ - 18, H_ - 14, meta["footer"], 8.6, 400, "end", MUTE)]
    cid = f"clip{num.replace('-', '')}"
    inner = _paint("".join(body), br)
    svg = (f'<svg viewBox="0 0 {W_} {H_}" xmlns="http://www.w3.org/2000/svg" font-family="Nunito Sans, -apple-system, Helvetica, Arial, sans-serif">'
           f'<rect width="{W_}" height="{H_}" fill="{CREAM}"/><defs><clipPath id="{cid}"><rect x="0" y="0" width="{W_}" height="{H_ - 52 - 36}"/></clipPath></defs>'
           + "".join(hdr) + f'<g transform="translate(0,52)" clip-path="url(#{cid})">' + inner + "</g>" + "".join(ftr) + "</svg>")
    return re.sub(r'(<text\b[^>]*>)([^<]*)(</text>)', lambda m: m.group(1) + esc(_words(_html.unescape(m.group(2)))) + m.group(3), svg)


def _paint(svg: str, br: dict) -> str:
    """The engine's gold in the brand's colors: text and strokes in the brand blue, filled badges in a light tint of it."""
    tint = "#bcd6ee"
    svg = re.sub(r'(<(?:circle|rect|polygon)\b[^>]*?)fill="#d49e1b"', lambda m: m.group(1) + f'fill="{tint}"', svg)
    return svg.replace('fill="#d49e1b"', f'fill="{br["accent_b"]}"').replace('stroke="#d49e1b"', f'stroke="{br["accent_b"]}"')


_AS_BUILT_WORDS = [
    (r"\bthe new decks\b", "the decks"), (r"\bnew decks\b", "decks"), (r"\bNew deck\b", "Existing deck — as built"), (r"\bnew deck\b", "existing deck — as built"),
    (r"\bthe new work\b", "the deck"), (r"\bnew work\b", "the deck"), (r"\bNew concrete\b", "Concrete"), (r"\bnew roof covers?\b", "roof cover"),
    (r"; field-verify grade before setting the piers", ", as surveyed"), (r" — field-measure each\.?", ""), (r"Rail LF for labor = deck-edge LF of actual rail\.?", ""),
    (r" \(8' kits cut to bay\)", ""), (r"membrane \+ L-flashing", "flashed (R507.2.4)"), (r"membrane 12\" up the wall", "flashing at the ledger (R507.2.4)"),
    (r", plies laminated \(RSS screws 2 rows @ 12\"\)", ""), (r"GRK RSS 3-1/8\"", "structural screws"), (r", joist tape\b", ""),
    (r"\bthe owner's choice\b", "as built"), (r"House shown for context only \(the deck work only\)\.", "House shown for context only."), (r"\bDesign intent\b", "As built"),
    (r"\bdesign intent\b", "as built"), (r"; every member in the model — the cut list is on T-600", "; every member as built"),
    (r"\s*Call 811(?: first| before drilling)?\.", ""),
]


def _words(s: str) -> str:
    """Every word on a sheet, as this job reads it: the CRC for the IRC (California), the as-built record for new work, the job's
    hardware for the engine's defaults."""
    spec, ext = _CTX.get("spec"), _CTX.get("ext")
    if not s or ext is None:
        return s
    if _ca(spec):
        s = re.sub(r"\b2021 IRC\b", SECTIONS[_ed(spec)]["code"], s)
        s = re.sub(r"\b2022 CRC\b", SECTIONS[_ed(spec)]["code"], s)
        s = re.sub(r"\bIRC\b", "CRC", s)
        if _ed(spec) == "2025":                                 # the 2025 CRC's numbers for the engine's 2021 IRC sections
            for pat, rep_ in ((r"\bR312\.1\.2\b", "R321.1.2"), (r"\bR312\.1\.3\b", "R321.1.3"), (r"\bR312\.1\.1\b", "R321.1.1"), (r"\bR312(?:\.1)?\b", "R321.1"),
                              (r"\bR311\.7\.8(?:\.\d+)?\b", "R320"), (r"\bR311\.7", "R318.7"), (r"\bR308\.4\.4\b", "R324.4.4"), (r"\bR308\.1\b", "R324.1"),
                              (r"\bR303\.7\b", "R325.7"), (r"\bR403\.1\.4\b", "R507.3.2"), (r"CRC R337(?:\.\d+)*", "CWUIC 504.7.3"), (r"\bASCE 7-16\b", "ASCE 7-22")):
                s = re.sub(pat, rep_, s)
        s = s.replace("IWUIC", "CRC R337").replace("a Colorado PE", "a California-licensed engineer").replace("Colorado PE", "California-licensed engineer")
        s = re.sub(r"Guard 36\" min above the deck; openings under 4\" \(CRC R312\)\.?", f"Guard {spec.railing.height_in:g}\" (CRC R312.1.2: 42\" min.); openings reject a 4\" sphere (R312.1.3)", s)
    if ext.as_built:
        for pat, rep in _AS_BUILT_WORDS:
            s = re.sub(pat, rep, s)
    if ext.joist_ties and ext.joist_ties.upper() != "H2.5AZ":
        s = s.replace("H2.5AZ", ext.joist_ties)
    if ext.tie_model != "DTT1Z":
        s = s.replace("DTT1Z", ext.tie_model)
    if ext.brace != "4x4":
        s = s.replace("4x4 knee brace", f"{ext.brace} knee brace").replace("with 4x4 knee braces", f"with {ext.brace} knee braces")
    if ext.fascia:
        s = s.replace("rail posts shown for the pockets", "guard posts shown outside the edge, on the fascia brackets")
    return s


def _wrap_member_key(orig):
    """The isometric keys: the job's brace stock and bolts, the guard as built (glass, fascia posts), its brackets, the stair cable
    and the handrail."""
    def member_key(L, S, t):
        ks = orig(L, S, t)
        ext = _ext(L.spec)
        if ext is None:
            return ks
        s = L.spec
        out = []
        for lab, pred, where, pick in ks:
            if "knee brace at 45" in lab:
                lab = (f"{ext.brace} knee brace at 45°, " + ("in the planes of the beams" if ext.knee_brace_layout else "both directions") + ", "
                       + (ext.knee_brace_bolts or "through-bolted each end") + _v("knee_brace_bolts"))
            elif ext.as_built and ext.footing_words and pred(Box("post", 0, 1, 0, 1, 0, 1, "timber")) and " post on " in lab:
                lab = lab.split(" post on ")[0] + " post on its existing cast-in base" + _v("footings")
            elif lab.startswith("Double ") and "rim" in lab and ext.as_built:
                lab = lab.split(",")[0]
            elif pred(Box("toprail", 0, 1, 0, 1, 0, 1, "railmetal")) and L.rail:
                fm = fascia_mount(s)
                lab = (f"{fm['name'] or CAT.rail_name(s.railing.system)} guard, {s.railing.color}, {s.railing.height_in:g}\"" + (": glass infill" if ext.glass else "")
                       + (", fascia-mounted posts" if ext.fascia else ""))
            out.append((lab, pred, where, pick))
            if lab.startswith(fascia_mount(s)["name"] or "~") and "guard" in lab:
                if ext.fascia:
                    out.append(("Fascia-mount bracket on the rim, over solid 2x blocking", lambda b: b.kind == "railbracket", (0.5, 0.5, 0.5), "first"))
                if ext.glass:
                    out.append((f"Tempered safety-glass infill panel ({_code(s)} R308.4.4)", lambda b: b.kind == "glasspanel", (0.5, 0.5, 0.6), "mid"))
                if ext.vertical:
                    out.append(("Stair guard: vertical cable, 3\" clear, over a bottom rail", lambda b: (b.tag or "") == "vertical stair cable", (0.5, 0.5, 0.5), "mid"))
                if ext.stair_handrail != "none":
                    out.append(("Graspable handrail, 34-38\" over the nosings", lambda b: (b.tag or "") == "graspable handrail", (0.5, 0.5, 0.5), "mid"))
        return [k for k in out if any(k[1](b) for b in S.boxes)]
    return member_key


def _sheet_scene(S):
    """The scene as the sheets see it (the engine's all_sheets drops the yard, a louvered roof and the styling furniture)."""
    import dataclasses as _dc
    return _dc.replace(S, boxes=[b for b in S.boxes if getattr(b, "layer", "") not in DW.NOT_ON_SHEETS])


def _wrap_all_sheets(orig):
    def all_sheets(L, t, flags, scene=None, customer=False):
        ext = _ext(L.spec)
        if ext is None or hasattr(L, "parts"):
            return orig(L, t, flags, scene, customer)
        S = scene or SC.build_scene(L)
        _CTX.update(L=L, S=_sheet_scene(S), t=t)
        out = list(orig(L, t, flags, S, customer))
        meta = mx_sheet_meta(L, customer)
        if ext.as_built and not ext.keep_connection_details:     # the engine's connection sheets carry its house fastening rules
            out = [x for x in out if x[0] not in ("D-502", "D-504")]
        photos = photo_sheets(ext.photos, meta)
        at = next((i for i, x in enumerate(out) if x[0].startswith("D-")), len(out))
        out = out[:at] + photos + out[at:]
        notes = notes_sheets(ext.notes, meta)
        if notes:                                                # the job's own general notes replace the engine's G-002
            out = [out[0]] + notes + [x for x in out[1:] if x[0] != "G-002"]
        svg_c = Path(str((ext.site_plan or {}).get("svg") or ""))
        if str(svg_c) and svg_c.is_file():                       # a finished site plan (the site-plan agent's C-100.svg) as the C-100 sheet
            c100 = ("C-100", "Site plan", site_plan_sheet(svg_c, meta))
            out = [x for x in out if x[0] != "C-100"]
            at = next((i for i, x in enumerate(out) if not x[0].startswith("G-")), len(out))
            out = out[:at] + [c100] + out[at:]
        if ext.callouts:
            out.append(("D-505", "Connection details — guard, ties, bracing", sheet_d505(L, _CTX["S"], t, meta)))
        index = [(n_, ttl) for n_, ttl, _ in out]
        if _CTX.get("renders"):
            index.insert(next((i for i, (n_, _) in enumerate(index) if n_ == "A-002"), 1), ("A-001", "3D views of the model"))
        out[0] = ("G-001", "General notes · design criteria", sheet_g001(L, _CTX["S"], t, meta, index))
        return out
    return all_sheets


# ---------------------------------------------------------------------------- G-001: the job's cover sheet
def _criteria(spec, ext: Ext, L, t) -> List[Tuple[str, str]]:
    """The design-criteria rows: the code's values for this job, then the job's own (a dict of values or [[label, text]] rows)."""
    code = _code(spec)
    dc = ext.design_criteria if isinstance(ext.design_criteria, dict) else {}
    g = lambda k, d=None: dc.get(k, d)
    site = spec.site
    live, dead, guard = g("live_psf", 40), g("dead_psf", 10), g("guard_lb", 200)
    snow = g("snow_psf", site.ground_snow_psf)
    rows = [("Live load", f"{live:g} psf uniform, deck ({code} Table R301.5)"), ("Dead load", f"{g('dead_psf_text', str(dead) + ' psf, deck framing and decking')}"),
            ("Guard load", f"{guard:g} lb concentrated at the top in any direction; infill 50 lb on 1 SF ({code} Table R301.5, footnote)"),
            ("Ground snow", f"{snow:g} psf" + (" — none at this site; the 40 psf live load governs" if not snow else "")),
            ("Wind", g("wind_text") or f"{g('wind_vult_mph', site.wind_speed_mph):g} mph Vult, Exposure {g('wind_exposure', 'C')}, Risk Category {g('risk_category', 'II')} ({g('asce', _sec(spec, 'asce') or 'ASCE 7-16')})"),
            ("Seismic", "SDC " + str(g("seismic_sdc", site.seismic_design_category)) + "".join(f" · {lab} {g(k)}" for k, lab in (("ss", "Ss"), ("s1", "S1"), ("sds", "SDS"), ("sd1", "SD1"), ("site_class", "Site Class")) if g(k) is not None)
             + f" · Risk Category {g('risk_category', 'II')} ({g('asce', _sec(spec, 'asce') or 'ASCE 7-16')})"),
            ("Footing depth", f"{g('footing_min_in', g('frost_in', site.frost_depth_in)):g}\" min. below undisturbed grade, on firm native soil ({code} {_sec(spec, 'footing_depth') or 'R403.1.4'})" + _v("footings")),
            ("Soil bearing", f"{g('soil_psf', site.soil_bearing_psf):,.0f} psf presumptive ({code} Table R401.4.1) — no soils report"),
            ("Design total", f"{live + dead:g} psf on the deck")]
    if ext.wui:
        rows.append(("Wildfire", f"Wildland-Urban Interface fire area: {_sec(spec, 'wui') or code + ' R337'} — walking surfaces per {_sec(spec, 'wui_deck') or 'R337.9'}, the guard aluminum and glass (see the WUI notes)"))
    rows.append(("Engineering", "Stamped structural design by a California-licensed engineer governs" if spec.extras.engineered and _ca(spec)
                 else "Stamped structural design governs" if spec.extras.engineered else f"Prescriptive — the members as built checked against {code} R507"))
    key = lambda k: str(k).split(" (")[0].strip().lower()
    for k, v in dc.items():                                    # any other value is a row of its own
        if k not in ("live_psf", "dead_psf", "guard_lb", "snow_psf", "wind_vult_mph", "wind_exposure", "risk_category", "seismic_sdc", "ss", "s1", "sds", "sd1",
                     "site_class", "footing_min_in", "frost_in", "soil_psf", "dead_psf_text", "asce", "wind_text"):
            rows.append((str(k).replace("_", " ").capitalize(), str(v)))
    for lab, txt in (ext.design_criteria if isinstance(ext.design_criteria, list) else []):
        hit = next((i for i, (k_, _) in enumerate(rows) if key(k_) == key(lab)), None)
        if hit is None:
            rows.append((str(lab), str(txt)))
        else:
            rows[hit] = (str(lab), str(txt))
    return rows


def _codes(spec, ext: Ext) -> List[str]:
    if ext.codes:
        return list(ext.codes)
    if _ca(spec):
        return ["2022 California Residential Code (CRC)", "2022 California Building Code (CBC)", "ASCE 7-16"]
    return [spec.site.code_basis or f"2021 IRC as adopted by {spec.site.city or 'the jurisdiction'}", "ASCE 7-16"]


def _structure(spec, ext: Ext, L, t) -> List[Tuple[str, str]]:
    sm, sch = t.summary, t.schedule
    bls = L.beam_lines or []
    rows = [("Footings", ext.footing_words or sm["posts"].split(" on ")[-1]), ("Posts", sm["posts"].split(" on ")[0]),
            ("Beams", "; ".join(f"{b.label} — {b.n_posts} posts" for b in bls) if bls else "none"), ("Joists", sm["joists"]), ("Rims", sm["rims"]),
            ("Ledger", sch.get("Ledger", "—"))]
    for k in ("Joist ties", "Lateral", "Blocking", "Knee braces"):
        if sch.get(k):
            rows.append((k, sch[k]))
    rows += [("Decking", sm["decking"]), ("Guard", sm.get("rail", "—"))]
    if L.stairs:
        rows.append(("Stairs", "; ".join(sm.get("stairs") or [])))
    return rows


def _blocks_fit(blocks, y0: float, y_max: float, base: float = 8.2) -> Tuple[float, float]:
    """(font size, line height) that fit a column's blocks [(heading, [(label, [lines])])] between y0 and y_max."""
    for k in (1.0, 0.95, 0.9, 0.85, 0.8, 0.75):
        lh = 11.5 * k
        h = sum(26 * k + sum(max(1, len(ls)) * lh + 1 for _, ls in rows) for _, rows in blocks)
        if y0 + h <= y_max:
            return base * k, lh
    return base * 0.75, 11.5 * 0.75


def _draw_blocks(o, blocks, x, y, fs, lh, label_w=118, accent="#2E75B6"):
    for head, rows in blocks:
        o.append(T(x, y + 12 * fs / 8.2, head, 9 * fs / 8.2, 800, fill=accent)); y += 26 * fs / 8.2
        for lab, ls in rows:
            for i, ln in enumerate(ls or [""]):
                if lab and i == 0:
                    o.append(T(x, y, lab, fs, 800))
                o.append(T(x + (label_w if lab else 0), y, ln, fs, 400)); y += lh
            y += 1
    return y


def sheet_g001(L, S, t, meta, index) -> str:
    """G-001 for this job: the project, the as-built scope, the design criteria and the structure on the left; the sheet index,
    the codes, the site and the WUI notes on the right — sized to fit the sheet."""
    s, ext, br = L.spec, _ext(L.spec), _CTX["brand"]
    wrapL, wrapR = 92, 70
    proj = [("", [s.job]), ("", [f"{s.site.address}, {s.site.city} {s.site.state} {s.site.zip}".strip(", ")]),
            ("", [f"Owner: {s.client}"] if s.client else []), ("", [f"{L.deck_sf:g} SF · surface {ftin(s.geometry.height_in)} above grade · {len(L.zones)} zone{'s' if len(L.zones) > 1 else ''}"])]
    left = [("PROJECT", [r for r in proj if r[1]])]
    if ext.as_built:
        note = ext.as_built_note or "Dimensions and members are field-verified from the as-built survey and photos (A-501); the sheets record the deck as it stands."
        left.append(("SCOPE", [("", ["Existing deck — as-built (legalization of the deck as built)"]), ("", textwrap.wrap(note, wrapL + 8))]))
    left.append(("DESIGN CRITERIA", [(k, textwrap.wrap(v, wrapL - 12)[:3]) for k, v in _criteria(s, ext, L, t)]))
    left.append(("STRUCTURE (AS BUILT)" if ext.as_built else "STRUCTURE", [(k, textwrap.wrap(_words(v), wrapL - 12)[:3]) for k, v in _structure(s, ext, L, t)]))
    right = [("SHEET INDEX", [("", [f"{n_}   {ttl}"]) for n_, ttl in index]), ("CODES", [("", textwrap.wrap(c, wrapR)) for c in _codes(s, ext)]),
             ("SITE", [("", textwrap.wrap(_words(x), wrapR)) for x in (DW._site_lines(s) if not ext.as_built or (s.site.plan or {}).get("site_lines") or s.site.notes
                                                                      else ["Lot lines, setbacks and the deck's distances to them: C-100 / the survey"])])]
    if ext.wui:
        code = _code(s)
        dk = f"{s.decking.brand} {s.decking.collection} {s.decking.color}"
        w_all, w_deck = _sec(s, "wui") or f"{code} R337", _sec(s, "wui_deck") or f"{code} R337.9"
        rows_w = [f"The site is in a Wildland-Urban Interface fire area: {w_all} applies to the deck as built.",
                  f"Walking surfaces ({w_deck}): {dk} — " + (ext.wui_listing or "its ignition-resistant listing as recorded (SFM 12-7A-4 / ASTM E2632); submit the listing")]
        if _sec(s, "wui_flash"):
            rows_w.append(f"Deck-to-wall flashing: 6\" min. metal flashing applied vertically on the wall at every deck-to-wall line ({_sec(s, 'wui_flash')})" + _v("ledger_flashing"))
        rows_w += [
                  f"Guard: {fascia_mount(s)['name'] or CAT.rail_name(s.railing.system)} — noncombustible aluminum posts and rails"
                  + (", tempered glass infill" if ext.glass else "") + (", stainless cable on the stairs" if ext.vertical else ""),
                  "The deck's framing, fascia and the area below kept clear of combustible storage and debris."]
        right.append(("WILDFIRE (WUI) NOTES", [("", textwrap.wrap(x, wrapR)) for x in rows_w]))
    if ext.verify:
        right.append(("FIELD-VERIFY (V)", [("", textwrap.wrap("(V) marks a value taken from the photos, sketches or the 2018 design: the owner verifies it in the field before "
                                                              f"the final submittal. The {len(ext.verify)} items are listed first on " + ("G-002." if ext.notes else "this sheet."), wrapR))]
                      + ([] if ext.notes else [("", textwrap.wrap(f"{k.replace('_', ' ')}: {v}" if v else k.replace('_', ' '), wrapR)) for k, v in ext.verify.items()])))
    o = []
    fsl, lhl = _blocks_fit(left, 8, 606)
    _draw_blocks(o, left, 24, 8, fsl, lhl, accent=br["accent_b"])
    fsr, lhr = _blocks_fit(right, 8, 606)
    _draw_blocks(o, right, 600, 8, fsr, lhr, accent=br["accent_b"])
    return mx_sheet("G-001", "General notes · design criteria", ("Existing deck — as built: " if ext.as_built else "") + "codes, design criteria, structure, sheet index, site", o, "No scale", meta)


# ---------------------------------------------------------------------------- S-101: the hardware on the framing plan
def _plan_xf(S):
    x0, x1, y0, y1 = DW.plan_bounds(S)
    return DW.plan_xform(x0, x1, y0 - 2, y1, 40, 24, 700, 560)


def _hook_s101(body: List[str]) -> List[str]:
    """H2.5A at every joist-to-beam bearing, the R507.9.2 devices at the house line, every blocking row named, the fascia posts
    with the blocking behind them, and a legend with the counts — drawn on the engine's own plan transform."""
    L, S, t, ext, br = _CTX["L"], _CTX["S"], _CTX["t"], _CTX["ext"], _CTX["brand"]
    if not ext.callouts:
        return body
    X, Y, sc = _plan_xf(S)
    s = L.spec
    jb = CAT.actual(s.framing.joist_size)[0]
    o = []
    n_h = 0
    for z in L.zones:
        fr = z.frame
        rim_t = fr.rim_plies * jb
        xs = [z.x0 + x for x in fr.joist_x + fr.pf_x] + [z.x0 + rim_t / 2, z.x0 + z.W - rim_t / 2]
        yo = max((z_.wall_y + b_.cl_y for z_ in L.zones for b_ in z_.frame.beams if b_.kind == "drop"), default=0)
        for b in [b for b in fr.beams if b.kind == "drop" and (ext.joist_tie_lines != "outer" or abs(z.wall_y + b.cl_y - yo) < 0.5)]:
            yy = Y((z.wall_y + b.cl_y) * IN)
            for x in xs:
                xx = X(x * IN)
                o.append(PGN([(xx - 2.6, yy + 2.2), (xx + 2.6, yy + 2.2), (xx, yy - 2.6)], "#b3261e", "#ffffff", 0.3)); n_h += 1
        for r in fr.blocking_rows_y:
            at_beam = any(abs(r - b.cl_y) < 2.5 for b in fr.beams)
            o.append(TH(X((z.x0 + z.W) * IN) - 20, Y((z.wall_y + r) * IN) - 3.2, f"SOLID BLOCKING ROW · {'over the beam' if at_beam else 'mid-span'} · {ftin(r)} from the house",
                        5.8, 800, "end", fill=BLUE))
    ties = getattr(L, "_mx_ties", [])
    for i, (x, yw) in enumerate(ties, 1):
        xx, yy = X(x * IN), Y(yw * IN)
        o.append(R(xx - 3, yy - 1, 6, 7, INK, "#ffffff", 0.4))
        o.append(LN(xx, yy - 1, xx, yy - 13, INK, 0.5))
        o.append(TH(xx, yy - 16, f"LT{i} · {ext.tie_model}", 6.0, 800, "middle", fill=INK))
    if ext.fascia and L.rail:
        out = fascia_offset_in(s)
        for p in L.rail.posts:
            xx, yy = X(p.x * IN), Y(p.y * IN)
            o.append(R(xx - 2.6, yy - 2.6, 5.2, 5.2, "#ffffff", INK, 0.7))
            for e in [e for e in (L.outline_edges or L.edges) if e.exposed and e.length > 1]:
                Le = e.length; ux, uy = (e.x1 - e.x0) / Le, (e.y1 - e.y0) / Le
                nx, ny = -uy, ux
                d_ = (p.x - e.x0) * nx + (p.y - e.y0) * ny
                tt = (p.x - e.x0) * ux + (p.y - e.y0) * uy
                if abs(d_ - out) > 1.0 or not (-out - 1 <= tt <= Le + out + 1):
                    continue
                tt = min(max(tt, 6.0), Le - 6.0)                        # the blocking pair inside the rim, one joist bay along it
                rim_in = L.frame.rim_plies * jb
                cx, cy = e.x0 + ux * tt - nx * (rim_in + 1.5), e.y0 + uy * tt - ny * (rim_in + 1.5)
                hb = (L.frame.spacing - jb) / 2
                pts = [(cx - ux * hb - nx * 1.5, cy - uy * hb - ny * 1.5), (cx + ux * hb - nx * 1.5, cy + uy * hb - ny * 1.5),
                       (cx + ux * hb + nx * 1.5, cy + uy * hb + ny * 1.5), (cx - ux * hb + nx * 1.5, cy - uy * hb + ny * 1.5)]
                o.append(PGN([(X(a * IN), Y(b_ * IN)) for a, b_ in pts], br["accent_b"], "none", 0))
    # the legend, in the plan window's emptiest corner
    n_tie = next((ln.net for ln in t.lines if ln.sku in ("H2.5A", "H2.5AZ", ext.joist_tie)), n_h)
    items = [("tri", f"{ext.joist_tie} at every joist-to-beam bearing{' on the outer beam' if ext.joist_tie_lines == 'outer' else ''} — {n_tie:g} ties{_v('joist_ties')} (D-505 / 3)")] if n_h else []
    if ties:
        items.append(("sq", f"{ext.tie_model} lateral-load device at the ledger — {len(ties)} x {ext.tie_lb} lb{_v('lateral_ties')} ({_code(s)} R507.9.2; D-505 / 4)"))
    if any(z.frame.blocking_rows_y for z in L.zones):
        items.append(("line", "Solid blocking rows: one over every beam" + ((", one at mid-span of the house-side bay" if str(ext.blocking_midspan).lower() == "house" else ", one at mid-span of every span") if ext.blocking_midspan else "")))
    if ext.fascia and L.rail:
        items.append(("post", f"Fascia-mounted guard post ({len(L.rail.posts)}), solid 2x blocking behind each{_v('guard_blocking')} (D-505 / 1-2)"))
    if s.framing.knee_braces:
        items.append(("brace", f"{ext.brace} knee braces both ways at every beam post{_v('knee_brace_bolts')} (D-505 / 5)"))
    for bn in ext.beam_notes:
        items.append(("note", bn))
    if items:
        wl, hl = 380, 16 + 12 * len(items)
        occ = [(X(b.x0), Y(b.y0), X(b.x1), Y(b.y1)) for b in S.boxes if b.kind in ("tread", "riser", "board", "border", "fascia", "rim", "joist", "house", "footing", "post") and b.layer != "site"]
        def free(x_, y_):
            return not any(x_ < q[2] + 4 and q[0] - 4 < x_ + wl and y_ < q[3] + 4 and q[1] - 4 < y_ + hl for q in occ)
        cands = [(44, 584 - hl), (740 - wl, 584 - hl), (44, 28), (740 - wl, 28)]
        lx, ly = next((c for c in cands if free(*c)), cands[0])
        o.append(R(lx, ly, wl, hl, "#ffffff", INK, 0.6))
        o.append(T(lx + 8, ly + 11, "HARDWARE + BLOCKING (AS BUILT)" if ext.as_built else "HARDWARE + BLOCKING", 7.2, 800, fill=br["accent_b"]))
        for k, (sym, txt) in enumerate(items):
            yy = ly + 24 + 12 * k
            if sym == "tri":
                o.append(PGN([(lx + 10, yy), (lx + 16, yy), (lx + 13, yy - 5.5)], "#b3261e", "none", 0))
            elif sym == "sq":
                o.append(R(lx + 10, yy - 6, 6, 7, INK, "none", 0))
            elif sym == "line":
                o.append(R(lx + 8, yy - 4, 10, 3, BLUE, "none", 0))
            elif sym == "post":
                o.append(R(lx + 10, yy - 6, 6, 6, "#ffffff", INK, 0.8)); o.append(R(lx + 18, yy - 4.5, 7, 3, br["accent_b"], "none", 0))
            elif sym == "note":
                o.append(T(lx + 13, yy, "·", 9, 900, "middle"))
            else:
                o.append(LN(lx + 9, yy, lx + 17, yy - 6, FILL_DK, 2))
            o.append(T(lx + 30, yy, textwrap.shorten(txt, 92, placeholder="…"), 6.6, 600))
    return body + o


FILL_DK = DW.FILL["timber_dk"]


# ---------------------------------------------------------------------------- A-301: the section's hardware, glass, braces
def _hook_a301(body: List[str]) -> List[str]:
    L, S, t, ext = _CTX["L"], _CTX["S"], _CTX["t"], _CTX["ext"]
    s = L.spec
    deep = max(L.zones, key=lambda z: z.D)
    Yv, Z, sc = DW.elev_xform(deep.wall_y * IN - 3.0, S.y_front + 4.0, -max(4.0, L.frame.footing_depth_in / 12 + 1), S.deck_top + 4.5, 40, 24, 560, 560)
    i_el = next((i for i, x in enumerate(body) if x.startswith('<defs><clipPath id="a301el">')), len(body))
    lim = Yv(S.y_front + 4.0)
    xc = (deep.x0 + deep.W / 2) * IN
    behind = {(f"{Yv(b.y0):.1f}", f"{Z(b.z1):.1f}") for b in S.boxes if b.kind == "railpost" and (b.x0 + b.x1) / 2 > xc + 0.5}   # behind the viewer
    keep = []
    for i, x in enumerate(body):
        m = re.match(r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)"', x)
        if i < i_el and m and (float(m.group(1)) > lim or (m.group(1), m.group(2)) in behind):
            continue                                            # past the section's frame, or behind the viewer: a post the cut cannot show
        if ">4x4 knee brace<" in x:
            continue                                            # the brace is called out below with its stock and bolts
        keep.append(x)
    body = keep
    drop_b = sorted([b for b in deep.frame.beams if b.kind == "drop"], key=lambda b: b.cl_y)
    cant = [i for i, x in enumerate(body) if re.search(r"> ?[^<]* cantilever<", x)]
    if len(drop_b) > 1 and cant:                                # only the front beam carries a cantilever: redraw that one
        for i in reversed(cant):
            del body[i - 3:i + 1]
        bf = drop_b[-1]
        DW.dim_h(body, Yv, Z(S.deck_top) - 14, (deep.wall_y + bf.cl_y) * IN, S.y_front, f"{ftin((S.y_front - (deep.wall_y + bf.cl_y) * IN) * 12)} cantilever", 7.5)
    if not ext.callouts:
        return body
    xc = (deep.x0 + deep.W / 2) * IN
    zt = S.deck_top
    jd = CAT.actual(s.framing.joist_size)[1] * IN
    jbot = zt - CAT.decking_facts(s.decking.collection)["thick"] * IN - jd
    o = []
    for b in S.boxes:                                           # the glass and the brackets the engine's section does not draw
        if b.kind in ("glasspanel", "railbracket", "botrail") and (b.x0 <= xc <= b.x1 or b.kind == "railbracket"):
            o.append(R(Yv(b.y0), Z(b.z1), max(1.2, (b.y1 - b.y0) * sc), (b.z1 - b.z0) * sc, "#a9c6da" if b.kind == "glasspanel" else DW.FILL["railmetal"], INK, 0.3))
    targets = []
    bl_drop = [b for b in deep.frame.beams if b.kind == "drop"]
    bl_t = bl_drop[-1:] if ext.joist_tie_lines == "outer" else bl_drop[:1]
    for b in bl_t:
        targets.append(((Yv((deep.wall_y + b.cl_y) * IN), Z(jbot) - 1), f"{ext.joist_tie} each joist to the {'outer ' if ext.joist_tie_lines == 'outer' else ''}beam ({_count(t, ext.joist_tie)}{_v('joist_ties')}; D-505 / 3)"))
        targets.append(((Yv((deep.wall_y + b.cl_y) * IN) + 6, Z(jbot + jd / 2)), "Solid blocking row over the beam"))
    for i_b, (b, bn) in enumerate(zip(sorted(bl_drop, key=lambda q: q.cl_y), ext.beam_notes)):
        if bl_t and b is bl_t[0]:
            continue
        targets.append(((Yv((deep.wall_y + b.cl_y) * IN) - 4, Z(jbot - b.depth * IN / 2)), bn + _v("beam_positions")))
    if s.framing.knee_braces:
        targets.append(((Yv((deep.wall_y + bl_drop[0].cl_y) * IN - 1.2) if bl_drop else Yv(deep.wall_y * IN + 3), Z(jbot - 1.0)),
                        f"{ext.brace} knee brace, " + (ext.knee_brace_bolts or "through-bolted each end") + _v("knee_brace_bolts") + " (D-505 / 5)"))
    if getattr(L, "_mx_ties", None):
        targets.append(((Yv(deep.wall_y * IN + 0.15), Z(jbot + jd / 2)), f"Ledger{_v('ledger')}; {ext.tie_model} lateral devices{_v('lateral_ties')}, {_code(s)} R507.9.2 (D-505 / 4)"))
    if ext.fascia and L.rail:
        yf = S.y_front + fascia_offset_in(s) * IN
        targets.append(((Yv(yf), Z(jbot + 0.3)), f"Fascia-mounted guard post on its bracket{_v('guard_system')}, solid blocking behind{_v('guard_blocking')} (D-505 / 1)"))
    if ext.glass:
        targets.append(((Yv(S.y_front + fascia_offset_in(s) * IN if ext.fascia else S.y_front), Z(zt + 1.6)), f"Tempered safety-glass infill ({_code(s)} R308.4.4){_v('glass_marks')}"))
    # the words in a column under the deck, clear of the brace; each leader from the end of its first line to the member
    lx, ly = Yv(deep.wall_y * IN + 0.45), Z(zt - (L.frame.post_len * IN) * 0.42 - 1.2)
    for i, ((tx, ty), txt) in enumerate(targets):
        ls = textwrap.wrap(txt, 36)
        ex = lx + 3 + max(len(q) for q in ls[:1]) * 6.5 * 0.53
        o.append(LN(ex + 2, ly - 2.5, tx, ty, INK, 0.45)); o.append(C(tx, ty, 1.4, INK, "none", 0))
        for j, ln in enumerate(ls):
            o.append(TH(lx + 3, ly + j * 8.2, ln, 6.5, 700, halo="#ffffff"))
        ly += 8.2 * len(ls) + 8
    return body + o


def _count(t, sku) -> str:
    n = next((ln.net for ln in t.lines if ln.sku == sku), None)
    return f"{n:g} ties" if n else "every joist"


# ---------------------------------------------------------------------------- A-201: the glass in the elevation, the guard words
def _hook_a201(body: List[str]) -> List[str]:
    L, S, ext, t = _CTX["L"], _CTX["S"], _CTX["ext"], _CTX["t"]
    if not (ext.glass or ext.fascia or ext.vertical or ext.as_built):
        return body
    s, code, rl = L.spec, _code(L.spec), L.rail
    body = [x for x in body if not (x.startswith('<text x="760.0"') and ">RAILING<" not in x)]
    notes = [t.summary.get("rail", "")]
    if rl:
        side_ = lambda v: re.sub(r"^edge:(\d+)$", r"side \1", v)
        notes.append("Bays: " + " · ".join(f"{side_(s_.side)} {ftin(s_.ctc)}" for s_ in rl.sections[:14]))
    if ext.fascia:
        fm = fascia_mount(s)
        notes.append(f"Posts fascia-mounted outside the rim on the {fm['bracket']}, {fm['standoff_in']:g}\" off the fascia, the foot at the rim's bottom edge; "
                     f"{fm['post_screws']}; {fm['rim_fastening']}; solid 2x blocking behind every post (D-505 / 1-2)")
    if ext.glass:
        notes.append(ext.glass_note or f"Infill: tempered safety-glass panels in a top rail and a bottom-rail channel. Glazing in a guard is a hazardous location: "
                                       f"safety glazing, each lite permanently labeled ({code} R308.4.4, R308.1)")
    notes.append(f"Guard {s.railing.height_in:g}\" over the deck" + (f" ({code} R312.1.2: 42\" min.)" if _ca(s) else f" ({code} R312.1.2)") + f"; openings reject a 4\" sphere (R312.1.3); "
                 f"200 lb at the top in any direction, 50 lb on 1 SF of infill (Table R301.5)")
    if ext.vertical:
        notes.append(f"Stairs and landings: vertical cable at 3\" clear between a bottom rail and the top rail, 34\" min. over the nosing line"
                     + ("" if ext.stair_handrail == "none" else f"; a graspable handrail 34-38\" over the nosings ({code} R311.7.8)") + " (D-505 / 6)")
    yy = 40
    for n_ in [n for n in notes if n]:
        for ln in textwrap.wrap(_words(n_), 42)[:12]:
            body.append(T(760, yy, ln, 7.4, 400)); yy += 10.2
        yy += 4
    Xe, Z, sce = DW.elev_xform(-2.0, S.W + 2.0, S.deck_top - 1.2, S.deck_top + 4.4, 40, 350, 700, 230)
    o = []
    for b in S.boxes:
        if b.kind in ("glasspanel", "railbracket") and b.y1 >= S.y_front - 0.5 and not b.rot:
            o.append(R(Xe(b.x0), Z(b.z1), (b.x1 - b.x0) * sce, (b.z1 - b.z0) * sce, "#a9c6da" if b.kind == "glasspanel" else DW.FILL["railmetal"],
                       _CTX["brand"]["accent_b"] if b.kind == "glasspanel" else INK, 0.4, 'fill-opacity="0.55"' if b.kind == "glasspanel" else ""))
    return body + o


# ---------------------------------------------------------------------------- D-501: the guard-post panel for a fascia post
def _hook_d501(body: List[str]) -> List[str]:
    ext = _CTX["ext"]
    if not ext.fascia:
        return body
    i_t = next((i for i, x in enumerate(body) if ">4  RAIL POST · GUARD<" in x), None)
    i_5 = next((i for i, x in enumerate(body) if x.startswith('<rect x="340.0" y="330.0" width="300.0" height="270.0"')), None)
    if i_t is None or i_5 is None or i_5 < i_t:
        return body
    o = []
    o.append(R(20, 330, 300, 270, "#fff", INK, 0.8)); o.append(R(20, 330, 300, 18, INK, "none", 0)); o.append(T(28, 343, "4  GUARD POST · FASCIA MOUNT", 9, 800, fill=GOLD))
    _fascia_post_drawing(o, 20, 348, 300, 252, small=True)
    return body[:i_t - 2] + o + body[i_5:]


def _lab(o, ax, ay, tx, ty, txt, chars=40, size=6.3, w=600, color=INK) -> float:
    """A leader from (ax, ay) to the words at (tx, ty), drawn now and wrapped to `chars`; returns the y under the last line."""
    ls = textwrap.wrap(txt, max(12, chars))
    o.append(LN(ax, ay, tx - 1.5, ty - 2.5, INK, 0.45)); o.append(C(ax, ay, 1.3, INK, "none", 0))
    for j, ln in enumerate(ls):
        o.append(TH(tx, ty + j * (size + 1.7), ln, size=size, w=w, fill=color, halo="#ffffff"))
    return ty + len(ls) * (size + 1.7)


def _fascia_post_drawing(o, x, y, w, h, small=False) -> None:
    """The fascia-mounted guard post in section: decking and its nose, the doubled rim, two 2x blocks behind it, the fascia, the
    bracket, the post from the rim's bottom edge to the guard height, the top rail, the glass (or cable), the bracket's fasteners,
    the 200 lb load — the words beside the post and under the rim, inside the panel."""
    L, ext, br = _CTX["L"], _CTX["ext"], _CTX["brand"]
    s = L.spec
    fm = fascia_mount(s)
    k = 2.6 if small else 3.2                                    # px to the inch
    jd = CAT.actual(s.framing.joist_size)[1]
    gh = L.rail.height if L.rail else s.railing.height_in
    top = y + 24                                                 # the post's top
    yd = top + gh * k                                            # the deck surface
    xo = x + (118 if small else 128)                             # the rim's outer face
    ply = 1.5 * k
    rt, rb = yd + k, yd + k + jd * k                             # the rim's top and bottom
    hang = s.framing.hanger or CAT.HANGER_FOR_JOIST.get(s.framing.joist_size, "LUS210Z")
    o.append(R(x + 14, rt, xo - ply * 4 - x - 14, jd * k, "none", MUTE, 0.6, 'stroke-dasharray="3 2"'))   # the joist beyond
    for i_ in range(2):
        DW._wood(o, xo - ply * (i_ + 1), rt, ply, jd * k)                                                  # the rim plies
        DW._wood(o, xo - ply * (i_ + 3), rt, ply, jd * k, dark=True)                                       # the blocks behind them
    fas = max(1.4, 0.5 * k)
    o.append(R(xo, rt - 1, fas, jd * k + 2, DW.FILL["fascia"], INK, 0.4))
    sto = fm["standoff_in"] * k
    o.append(R(xo + fas, rt + 2, sto, jd * k - 2, DW.FILL["railmetal"], INK, 0.4))                          # the bracket
    pw = CAT.rail_system_for(s.railing)["post_w"] * k
    px = xo + fas + sto
    o.append(R(px, top, pw, rb - top, DW.FILL["railmetal"], INK, 0.5))                                      # the post, foot at the rim's bottom
    o.append(R(px - 1.5, top - 3, pw + 3, 3, DW.FILL["railmetal"], INK, 0.4))                               # its cap
    o.append(R(x + 14, yd, xo + fas + 0.47 * k - x - 14, k, DW.FILL["deck"], INK, 0.4))                     # the decking and its nose
    o.append(R(px - 24, top + 1, 24, 4.5, DW.FILL["railmetal"], INK, 0.4))                                  # the top rail beyond
    if ext.glass:
        o.append(R(px - 24, yd - 12, 24, 4, DW.FILL["railmetal"], INK, 0.4))
        o.append(R(px - 14, top + 6, 3, yd - 12 - top - 6, "#a9c6da", br["accent_b"], 0.4))
    else:
        for j in range(int(gh // 3.25)):
            o.append(LN(px - 22, yd - 4 - j * 3.25 * k, px, yd - 4 - j * 3.25 * k, "#888", 0.5))
    for yy in (rt + jd * k * 0.3, rt + jd * k * 0.72):                                                    # bracket to the rim, into the blocks
        o.append(LN(xo + fas + sto, yy, xo - ply * 4 + 2, yy, INK, 1.1))
    for yy in (rt + 5, rb - 5):
        o.append(C(px + pw / 2, yy, 1.2, INK, "none", 0))
    ax = px + pw + 4                                                                                       # the load: 200 lb at the top
    o.append(f'<polyline points="{ax + 20:.1f},{top + 2:.1f} {ax:.1f},{top + 2:.1f}" fill="none" stroke="#b3261e" stroke-width="1.3"/>')
    o.append(PGN([(ax, top + 2), (ax + 5, top - 0.8), (ax + 5, top + 4.8)], "#b3261e", "none", 0))
    DW.dim_v(o, lambda v: v, px - 30, top, yd, f"{gh:g}\" guard", 6.2, left=True)
    tx = px + pw + 28
    rc = int((x + w - 8 - tx) / (6.3 * 0.53))
    o.append(T(tx, top + 3, "200 lb at the top, any direction", 6.3, 800, fill="#b3261e"))
    o.append(T(tx, top + 11, f"({_code(s)} Table R301.5, footnote)", 6.0, 600, fill="#b3261e"))
    yy = _lab(o, px + pw / 2, top + 26, tx, top + 26, f"{fm['name'] or CAT.rail_name(s.railing.system)} {CAT.rail_system_for(s.railing)['post_w']:g}\" post, {s.railing.color}, "
              "its foot flush with the bracket's at the rim's bottom edge", rc)
    _lab(o, xo + fas + sto / 2, rt + jd * k * 0.5, tx, max(yy + 8, yd - 18), f"{fm['bracket'].split(' (')[0].capitalize()}; {fm['post_screws']}", rc)
    bc = int((w - 28) / (6.3 * 0.53))
    yy = _lab(o, xo + fas + 1, rt + jd * k * 0.3, x + 14, rb + 12, fm["rim_fastening"][:1].upper() + fm["rim_fastening"][1:] + _v("guard_system") + ".", bc) + 3
    yy = _lab(o, xo - ply * 3, rt + jd * k * 0.8, x + 14, yy, f"(2) {s.framing.joist_size} solid blocks between the joists behind every post, tight to the rim, nailed to the joists{_v('guard_blocking')}.", bc) + 3
    _lab(o, x + 40, rt + jd * k * 0.5, x + 14, yy, f"Joist to rim: Simpson {hang} face-mount hanger at every joist; the rim plies fastened together.", bc)


# ---------------------------------------------------------------------------- D-505: guard post, ties, lateral, braces, stair guard
def sheet_d505(L, S, t, meta) -> str:
    s, ext, br = L.spec, _ext(L.spec), _CTX["brand"]
    code = _code(s)
    W3, H2, P = DW._grid6()
    o: List[str] = []
    jsz = s.framing.joist_size
    # 1 guard post, fascia mount, section
    x, y = P[0]; DW._panel(o, x, y, W3, H2, "1", "GUARD POST — FASCIA MOUNT (SECTION)" if ext.fascia else "GUARD POST (SECTION)")
    _fascia_post_drawing(o, x, y + 17, W3, H2 - 17)
    # 2 plan at the rim
    x, y = P[1]; DW._panel(o, x, y, W3, H2, "2", "GUARD POSTS + BLOCKING — PLAN AT THE RIM")
    sp = L.frame.spacing * 2.2
    o.append(T(x + W3 / 2 + 20, y + 34, f"deck — joists at {L.frame.spacing:g}\" OC", 6.6, 700, "middle", MUTE))
    for i_ in range(6):
        DW._wood(o, x + 52 + i_ * sp, y + 40, 4, 130)                                                     # the joists
    DW._wood(o, x + 30, y + 170, W3 - 60, 7); DW._wood(o, x + 30, y + 177, W3 - 60, 7)                    # the front rim, 2 plies
    DW._wood(o, x + 30, y + 40, 7, 144); DW._wood(o, x + 37, y + 40, 7, 130)                              # the side rim
    o.append(R(x + 26, y + 40, 4, 148, DW.FILL["fascia"], INK, 0.3)); o.append(R(x + 26, y + 184, W3 - 52, 4, DW.FILL["fascia"], INK, 0.3))
    pl = x + 54 + sp * 2.5                                                                                 # a line post on the front
    for px_, py_, kind_ in ((x + 18, y + 196, "corner"), (pl, y + 196, "front"), (x + 18, y + 100, "side")):
        o.append(R(px_ - 6, py_ - 6, 12, 12, DW.FILL["railmetal"], INK, 0.6))
        if kind_ == "front":
            o.append(R(px_ - 6, py_ - 9, 12, 3, "#5b6166", INK, 0.3))
            DW._wood(o, px_ - sp / 2 + 2, y + 160, sp - 4, 4.5, dark=True); DW._wood(o, px_ - sp / 2 + 2, y + 155.5, sp - 4, 4.5, dark=True)
        elif kind_ == "side":
            o.append(R(px_ + 6, py_ - 6, 3, 12, "#5b6166", INK, 0.3))
            DW._wood(o, x + 44, py_ - 6, sp + 6, 4.5, dark=True); DW._wood(o, x + 44, py_ + 1.5, sp + 6, 4.5, dark=True)
        else:
            o.append(R(px_ + 6, py_ - 9, 3, 6, "#5b6166", INK, 0.3)); o.append(R(px_ + 3, py_ - 9, 6, 3, "#5b6166", INK, 0.3))
    if L.rail:
        DW.dim_h(o, lambda v: v, y + 214, x + 18, pl, ("bays 72.43\" max. OC (6' panels)" if ext.fascia else f"bays {ftin(max(s_.ctc for s_ in L.rail.sections))} max."), 6.2, up=False)
    _lab(o, pl, y + 158, x + 14, y + 240, f"(2) {jsz} solid blocks between the joists behind every post, tight to the rim: the bracket's fasteners bear in solid wood", 44)
    _lab(o, x + 18, y + 200, x + 168, y + 240, ("Outside-corner bracket at a corner post, straight brackets at the others" + (" (the maker pairs a corner bracket with a straight one per panel)" if ext.fascia else "")) if ext.fascia else "Guard post", 42)
    _lab(o, x + 24, y + 100, x + 150, y + 76, "Side-rim post: the blocks run from the rim to the first joist", 40)
    # 3 the joist ties at the beam
    x, y = P[2]; DW._panel(o, x, y, W3, H2, "3", f"{ext.joist_tie} AT EVERY JOIST-TO-BEAM BEARING")
    bl = next((b for b in (L.beam_lines or []) if b.kind == "drop"), None)
    DW._wood(o, x + 40, y + 140, W3 - 80, 70, dark=True)                                                  # the beam
    o.append(T(x + W3 / 2, y + 180, f"{bl.size} {bl.species} drop beam" if bl else "drop beam", 7.0, 700, "middle", "#ffffff"))
    DW._wood(o, x + 40, y + 92, W3 - 80, 48)                                                              # joist (side view)
    o.append(T(x + W3 / 2, y + 120, f"{jsz} joist @ {L.frame.spacing:g}\" OC", 7.0, 700, "middle"))
    o.append(f'<polyline points="{x + 150},{y + 112} {x + 150},{y + 150} {x + 170},{y + 150} {x + 170},{y + 112}" fill="none" stroke="#5b6166" stroke-width="3"/>')
    for yy in (118, 128, 138):
        o.append(C(x + 150, y + yy, 1.3, INK, "none", 0)); o.append(C(x + 170, y + yy, 1.3, INK, "none", 0))
    for yy in (146,):
        o.append(C(x + 156, y + yy, 1.3, INK, "none", 0)); o.append(C(x + 164, y + yy, 1.3, INK, "none", 0))
    n_t = next((ln.net for ln in t.lines if ln.sku in (ext.joist_tie, "H2.5AZ", "H2.5A")), 0)
    DW._lead(o, x + 160, y + 112, x + 190, y + 60, f"Simpson {ext.joist_tie} hurricane tie, joist to beam, the nails Simpson lists in every hole{_v('joist_ties')}")
    DW._lead(o, x + 80, y + 160, x + 24, y + 236, (f"{n_t:g} ties: every joist and both rims at the outer beam; the inner beam's joists hang from a header" if ext.joist_tie_lines == "outer" else
                                                   f"{n_t:g} ties: every joist and both rims at each drop beam" + (f" ({len([b for b in L.beam_lines if b.kind == 'drop'])} beams)" if L.beam_lines else "")))
    DW._lead(o, x + 250, y + 110, x + 220, y + 236, "Solid blocking row over the beam between the joists")
    # 4 lateral load, plan
    x, y = P[3]; DW._panel(o, x, y, W3, H2, "4", f"LATERAL LOAD — {ext.tie_model} ({code} R507.9.2)")
    o.append(R(x + 20, y + 30, W3 - 40, 64, DW.FILL["house"], INK, 0.6)); o.append(T(x + 28, y + 41, "house floor framing — a floor joist, or blocking where they run parallel", 6.2, 700, fill=MUTE))
    for i_ in range(6):
        o.append(R(x + 36 + i_ * 50, y + 46, 5, 48, DW.FILL["timber_dk"], INK, 0.4))
    DW._wood(o, x + 20, y + 94, W3 - 40, 6, dark=True); DW._wood(o, x + 20, y + 100, W3 - 40, 6)
    for i_ in range(7):
        DW._wood(o, x + 26 + i_ * 44, y + 106, 5, 84)
    ends = [x + 31, x + W3 - 18 - 5] if ext.tie_count <= 2 else [x + 31, x + 75, x + W3 - 62, x + W3 - 18 - 5]
    for ex_ in ends:
        o.append(LN(ex_ + 2.5, y + 62, ex_ + 2.5, y + 142, "#5b6166", 1.6)); o.append(R(ex_ - 3, y + 136, 11, 14, "#5b6166", INK, 0.5)); o.append(R(ex_ - 3, y + 58, 11, 10, "#5b6166", INK, 0.5))
    DW.dim_h(o, lambda v: v, y + 200, x + 20, ends[0] + 2.5, "24\" max.", 6.2, up=False)
    DW.dim_h(o, lambda v: v, y + 200, ends[-1] + 2.5, x + W3 - 20, "24\" max.", 6.2, up=False)
    yy = _lab(o, ends[0] + 2.5, y + 143, x + 14, y + 222,
              f"({ext.tie_count}) Simpson {ext.tie_model}, {ext.tie_lb} lb each, within 24\" of each end of the deck: one on a deck joist with the screws the device "
              f"calls for, a 1/2\" threaded rod through the ledger and the band to a second device on a house floor joist{_v('lateral_ties')}", 84)
    _lab(o, x + 160, y + 103, x + 14, yy + 4, f"{s.ledger_size} ledger to the house band ({code} R507.9.1); the devices are in addition to the ledger fasteners", 84)
    # 5 knee brace
    x, y = P[4]; DW._panel(o, x, y, W3, H2, "5", f"KNEE BRACE — {ext.brace}, BOTH DIRECTIONS")
    bsz = bl.size if bl else "beam"
    DW._wood(o, x + 20, y + 40, W3 - 40, 44, dark=True); o.append(T(x + W3 / 2, y + 66, f"{bsz} beam", 7.0, 700, "middle", "#ffffff"))
    DW._wood(o, x + 136, y + 84, 34, 176); o.append(T(x + 153, y + 218, f"{s.framing.post_size} post", 6.6, 700, "middle", INK, rot=-90))
    kb, kd = CAT.actual(ext.brace)
    th = kd * 2.2
    o.append(PGN([(x + 170, y + 166), (x + 170, y + 166 - th * 1.41), (x + 170 + 82 - th * 1.41, y + 84), (x + 252, y + 84)], DW.FILL["timber_dk"], INK, 0.7))
    o.append(PGN([(x + 136, y + 166), (x + 136, y + 166 - th * 1.41), (x + 136 - 82 + th * 1.41, y + 84), (x + 54, y + 84)], DW.FILL["timber_dk"], INK, 0.7))
    two = "(2)" in (ext.knee_brace_bolts or "")
    for bx_, by_ in ((x + 176, y + 156), (x + 238, y + 92), (x + 130, y + 156), (x + 68, y + 92)):
        DW._bolt(o, bx_, by_)
        if two:
            DW._bolt(o, bx_ + (6 if bx_ > x + 150 else -6), by_ - 6)
    DW.dim_h(o, lambda v: v, y + 274, x + 170, x + 252, f"{ftin(s.framing.knee_leg_in)} leg", 6.2, up=False)
    _lab(o, x + 214, y + 126, x + 184, y + 192, f"{ext.brace} brace at 45°, " + (ext.knee_brace_bolts or "(1) 1/2\" through-bolt each end") + ", 2\" min. edge distance" + _v("knee_brace_bolts"), 32)
    _lab(o, x + 92, y + 126, x + 16, y + 192, f"The same toward the house at every post, up to a {jsz} block between two joists", 30)
    # 6 the stair guard
    x, y = P[5]
    if ext.vertical or ext.stair_handrail != "none":
        DW._panel(o, x, y, W3, H2, "6", "STAIR GUARD — VERTICAL CABLE + HANDRAIL" if ext.vertical else "STAIR HANDRAIL")
        steps = 7
        rx_, rz_ = 30.0, 22.0
        x0_, y0_ = x + 24, y + 96
        pts = []
        for i_ in range(steps):
            pts += [(x0_ + i_ * rx_, y0_ + i_ * rz_), (x0_ + (i_ + 1) * rx_, y0_ + i_ * rz_)]
        o.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + f'" fill="none" stroke="{INK}" stroke-width="1.2"/>')
        nose = lambda u: y0_ + (u - x0_) * rz_ / rx_
        gpx = 3.6                                                  # px per inch on the guard
        top_ = lambda u: nose(u) - 36 * gpx * 0.62
        hr_ = lambda u: nose(u) - HANDRAIL_IN * gpx * 0.5
        ua, ub = x0_ + 6, x0_ + steps * rx_ - 6
        o.append(LN(ua, top_(ua), ub, top_(ub), DW.FILL["railmetal"], 3.2))
        o.append(LN(ua, nose(ua) - 14, ub, nose(ub) - 14, DW.FILL["railmetal"], 2.2))
        for uu in (ua, (ua + ub) / 2, ub):
            o.append(LN(uu, nose(uu) + 4, uu, top_(uu) - 4, DW.FILL["railmetal"], 4.0))
        if ext.vertical:
            u = ua + 9
            while u < ub - 4:
                if abs(u - (ua + ub) / 2) > 5:
                    o.append(LN(u, nose(u) - 14, u, top_(u), "#888", 0.6))
                u += 9
            o.append(C(ua + 45, (nose(ua + 45) - 14 + top_(ua + 45)) / 2, 7, "none", "#b3261e", 0.8, "2 2"))
        if ext.stair_handrail != "none":
            o.append(LN(ua, hr_(ua) + 6, ub, hr_(ub) + 6, "#5b6166", 2.4))
        o.append(LN(ua - 2, nose(ua - 2) - 1, ub + 6, nose(ub + 6) - 1, "#b3261e", 0.6, "4 2"))
        DW._lead(o, ub - 40, nose(ub - 40) - 1, x + 200, y + 262, "Line connecting the nosings")
        DW._lead(o, ua + 30, top_(ua + 30), x + 160, y + 36, f"Top rail: {spec_guard_words(s)}")
        if ext.vertical:
            DW._lead(o, ua + 45 + 7, (nose(ua + 45) - 14 + top_(ua + 45)) / 2, x + 24, y + 236, "Vertical cable at 3\" clear between the bottom rail and the top rail — a 4\" sphere cannot pass (R312.1.3)")
            DW._lead(o, ub - 70, nose(ub - 70) - 14, x + 230, y + 200, "Bottom rail 4\" over the tread line: the triangle under it rejects a 6\" sphere (R312.1.3)")
        if ext.stair_handrail != "none":
            DW._lead(o, ua + 80, hr_(ua + 80) + 6, x + 200, y + 120, f"Graspable handrail on brackets, 34-38\" over the nosings, 1-1/4\" to 2\" round ({code} R311.7.8)")
    else:
        DW._panel(o, x, y, W3, H2, "6", "BLOCKING ROWS")
        for i_, ln in enumerate(textwrap.wrap(t.schedule.get("Blocking", ""), 60)):
            o.append(T(x + 20, y + 40 + i_ * 11, ln, 7.0, 500))
    return mx_sheet("D-505", "Connection details — guard, ties, bracing",
                    ("Guard post on the fascia bracket · " if ext.fascia else "") + f"{ext.joist_tie} at the beams · {ext.tie_model} lateral load · knee braces" + (" · the stair guard" if ext.vertical else ""),
                    o, "Schematic details, not to scale · the plans, the code sections cited and the manufacturers' instructions govern", meta)


def spec_guard_words(s) -> str:
    return f"{s.railing.height_in:g}\" guard on the deck; on the stairs 34\" min. over the nosing line ({_code(s)} R312.1.2)"


# ---------------------------------------------------------------------------- A-501..: the photo exhibit
def _photo_data(path: str, max_px: int = 1300) -> Tuple[str, float]:
    """(data URI, width / height) of a photo, downscaled to max_px on its long side (JPEG q80) so the set stays printable."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), im.width / im.height


def photo_sheets(photos: List[dict], meta: dict) -> List[Tuple[str, str, str]]:
    """The existing-conditions photos, 4-6 a sheet (A-501, A-502, ...): each photo with numbered circles at its callout points and the
    labels placed clear of each other and of the circles, leaders to the points, the caption under it — all SVG, so it prints."""
    if not photos:
        return []
    n = len(photos)
    n_sh = int(math.ceil(n / 6))
    per = int(math.ceil(n / n_sh))
    br = _CTX["brand"]
    out = []
    k_all = 0
    for si in range(n_sh):
        chunk = photos[si * per:(si + 1) * per]
        cols = 2 if len(chunk) <= 4 else 3
        rows = 1 if len(chunk) <= 2 else 2
        gx, gy, x0, y0, wf, hf = 16, 14, 20, 8, 960, 596
        cw, ch = (wf - gx * (cols - 1)) / cols, (hf - gy * (rows - 1)) / rows
        if rows == 1:                                            # one row: the photos and their captions centred in the field
            ch = min(ch, cw * 0.75 + 46)
            y0 = 8 + (hf - ch) / 2
        o = []
        for i, ph in enumerate(chunk):
            k_all += 1
            cx, cy = x0 + (i % cols) * (cw + gx), y0 + (i // cols) * (ch + gy)
            cap = textwrap.wrap(f"Photo {k_all}. {ph.get('caption', '')}", int(cw / 3.9))[:3]
            ih_max = ch - 12 * len(cap) - 6
            try:
                uri, ar = _photo_data(ph["img"])
            except Exception:
                uri, ar = None, 4 / 3
            iw, ih = (cw, cw / ar) if cw / ar <= ih_max else (ih_max * ar, ih_max)
            ix, iy = cx + (cw - iw) / 2, cy
            if uri:
                o.append(f'<image href="{uri}" x="{ix:.1f}" y="{iy:.1f}" width="{iw:.1f}" height="{ih:.1f}" preserveAspectRatio="none"/>')
            else:
                o.append(R(ix, iy, iw, ih, "#ddd", "none", 0)); o.append(T(ix + iw / 2, iy + ih / 2, f"photo not found: {Path(ph.get('img', '')).name}", 8, 700, "middle", "#b3261e"))
            o.append(R(ix, iy, iw, ih, "none", INK, 0.8))
            o.append(R(ix + 6, iy + 6, 34, 15, INK, "none", 0)); o.append(T(ix + 23, iy + 17, f"P{k_all}", 9, 900, "middle", "#ffffff"))
            placed: List[Tuple[float, float, float, float]] = [(ix + 6, iy + 6, ix + 40, iy + 21)]
            pts = [(ix + float(c.get("x", 0.5)) * iw, iy + float(c.get("y", 0.5)) * ih, str(c.get("label", ""))) for c in (ph.get("callouts") or [])]
            for px_, py_, _ in pts:
                placed.append((px_ - 8, py_ - 8, px_ + 8, py_ + 8))
            for j, (px_, py_, lab) in enumerate(pts, 1):
                lines = textwrap.wrap(lab, 30)[:3] or [""]
                bw = max(len(ln) for ln in lines) * 7.2 * 0.56 + 10
                bh = 10.5 * len(lines) + 5
                best = None
                for dx, dy in ((22, -bh - 8), (22, 10), (-22 - bw, -bh - 8), (-22 - bw, 10), (26, -bh / 2), (-26 - bw, -bh / 2), (-bw / 2, -bh - 24), (-bw / 2, 24),
                               (40, -bh - 30), (-40 - bw, -bh - 30), (40, 30), (-40 - bw, 30)):
                    bx0, by0 = px_ + dx, py_ + dy
                    bx0 = min(max(bx0, ix + 3), ix + iw - bw - 3); by0 = min(max(by0, iy + 3), iy + ih - bh - 3)
                    box = (bx0, by0, bx0 + bw, by0 + bh)
                    ov = sum(max(0, min(box[2], q[2]) - max(box[0], q[0])) * max(0, min(box[3], q[3]) - max(box[1], q[1])) for q in placed)
                    if best is None or ov < best[0]:
                        best = (ov, box)
                    if ov == 0:
                        break
                box = best[1]
                placed.append(box)
                qx, qy = min(max(px_, box[0]), box[2]), min(max(py_, box[1]), box[3])
                o.append(LN(px_, py_, qx, qy, "#ffffff", 2.6)); o.append(LN(px_, py_, qx, qy, INK, 1.0))
                o.append(R(box[0], box[1], box[2] - box[0], box[3] - box[1], "#ffffff", INK, 0.7, 'fill-opacity="0.92"'))
                for m, ln in enumerate(lines):
                    o.append(T(box[0] + 5, box[1] + 11 + 10.5 * m, (f"{j}  " if m == 0 else "    ") + ln, 7.2, 700 if m == 0 else 600))
                o.append(C(px_, py_, 7.5, br["accent_b"], "#ffffff", 1.4)); o.append(T(px_, py_ + 3.2, str(j), 8.5, 900, "middle", "#ffffff"))
            for m, ln in enumerate(cap):
                o.append(T(cx, iy + ih + 13 + 12 * m, ln, 8.0, 700 if m == 0 else 500))
        num = f"A-{501 + si}"
        ttl = "Existing conditions — photos" + (f" ({si + 1} of {n_sh})" if n_sh > 1 else "")
        out.append((num, ttl, mx_sheet(num, ttl, "The deck as it stands: photos with the members and hardware called out", o, "Photographs · not to scale · numbered callouts", meta)))
    return out


def _hook_s100(body: List[str]) -> List[str]:
    """The footing schedule's estimates marked: post stations, lengths and the footings themselves as the job lists them (V); the
    engine's footing sizing words give way to the footings as built (framing.footing_words)."""
    ext = _CTX["ext"]
    if ext.footing_words:
        i_id = next((i for i, x in enumerate(body) if '>ID<' in x and x.startswith('<text x="710.0"')), None)
        if i_id is not None:
            desc = [i for i, x in enumerate(body[:i_id]) if x.startswith('<text x="710.0"') and 'font-size="8"' in x]
            if desc:
                y0 = float(re.search(r'y="([\d.]+)"', body[desc[0]]).group(1))
                n_l = len(desc)
                ws = textwrap.wrap(ext.footing_words, 58)
                fs_ = 8.0 if len(ws) <= n_l else max(6.0, 8.0 * n_l / len(ws))
                ws = textwrap.wrap(ext.footing_words, int(58 * 8.0 / fs_))[:max(n_l, int(n_l * 11 / (fs_ * 1.25)))]
                new = [T(710, y0 + j * fs_ * 1.25, ln, round(fs_, 1), 500) for j, ln in enumerate(ws)]
                body = [x for i, x in enumerate(body) if i not in desc]
                at = desc[0]
                body = body[:at] + new + body[at:]
    keys = [k for k in ("post_stations", "post_lengths", "footings") if k in (ext.verify or {})]
    if not keys:
        return body
    txt = ("(V) " + "; ".join({"post_stations": "post stations estimated from the photos and the owner's sketch",
                               "post_lengths": "post lengths ~9' inner / ~11' outer",
                               "footings": "footing size and depth not seen"}[k] for k in keys) + " — field-verify")
    o = [T(710, 560 + 9 * j, ln, 6.8, 700, fill="#b3261e") for j, ln in enumerate(textwrap.wrap(txt, 58)[:4])]
    return body + o


# ---------------------------------------------------------------------------- G-002..: the job's general notes, paginated
def notes_sheets(notes: List[dict], meta: dict) -> List[Tuple[str, str, str]]:
    """The general notes as the job writes them ([{"head", "items"}], an item "- ..." a bullet under the one before): numbered per
    section, three columns a sheet, as many sheets as they take (G-002, G-003, ...); the field-verify (V) list goes first."""
    if not notes:
        return []
    ext = _CTX.get("ext")
    if ext is not None and ext.verify:
        notes = [{"head": "Field-verify (V)", "items": ["(V) on these sheets marks a value taken from the owner's sketches, the site photos or the 2018 design. "
                                                        "The owner verifies each one in the field and reports any difference before the final submittal:"]
                  + [f"- {k.replace('_', ' ').capitalize()}: {v}" if v else f"- {k.replace('_', ' ').capitalize()}" for k, v in ext.verify.items()]}] + list(notes)
    fs, lh, cw = 6.9, 8.6, 82
    cols, y0, y_max = (20, 348, 676), 12, 604
    blocks = []                                                   # (lines [(indent, text, bold, color)], keep-with-next)
    br = _CTX["brand"]
    for sec in notes:
        blocks.append(([(0, str(sec.get("head", "")).upper(), True, br["accent_b"])], True))
        n = 0
        for it in sec.get("items") or []:
            it = str(it)
            if it.startswith("- "):
                ls = textwrap.wrap(it[2:], cw - 8)
                blocks.append(([(14, ("· " if i == 0 else "  ") + ln, False, INK) for i, ln in enumerate(ls)], False))
            else:
                n += 1
                ls = textwrap.wrap(it, cw - 4)
                blocks.append(([(0, f"{n}.", True, br["accent_b"])] + [(10, ln, False, INK) for ln in ls], False))
    pages, cur, ci, y = [], [], 0, y0
    for k, (lines, keep) in enumerate(blocks):
        h = lh * (len(lines) - (1 if lines[0][1][-1:] == "." and lines[0][0] == 0 and len(lines) > 1 else 0)) + (6 if keep else 2)
        nxt = lh * len(blocks[k + 1][0]) if keep and k + 1 < len(blocks) else 0
        if y + h + nxt > y_max:
            ci += 1; y = y0
            if ci == len(cols):
                pages.append(cur); cur, ci = [], 0
        x = cols[ci]
        if lines[0][1][-1:] == "." and lines[0][0] == 0 and len(lines) > 1 and lines[0][2]:     # a number and its text on one line
            cur.append(T(x, y, lines[0][1], fs, 800, fill=lines[0][3]))
            for j, (ind, ln, b, c) in enumerate(lines[1:]):
                cur.append(T(x + 13, y + j * lh, ln, fs, 700 if b else 400, fill=c))
            y += lh * (len(lines) - 1) + 2
        else:
            for j, (ind, ln, b, c) in enumerate(lines):
                cur.append(T(x + ind, y + j * lh, ln, fs + (1.2 if keep else 0), 800 if b else 400, fill=c))
            y += lh * len(lines) + (6 if keep else 2)
    if cur:
        pages.append(cur)
    out = []
    for i, o in enumerate(pages):
        num = f"G-{2 + i:03d}"
        ttl = "General notes" + (f" ({i + 1} of {len(pages)})" if len(pages) > 1 else "")
        out.append((num, ttl, mx_sheet(num, ttl, "The code and County requirements for the deck as built — read with G-001 and the details", o, "No scale", meta)))
    return out


def site_plan_sheet(path: Path, meta: dict) -> str:
    """A finished site plan (the site-plan agent's C-100.svg) inside this set's title block, scaled into the drawing field."""
    raw = re.sub(r"<\?xml[^>]*\?>\s*", "", path.read_text())
    m = re.search(r'viewBox="([-\d.\s]+)"', raw)
    vb = m.group(1) if m else "0 0 1000 700"
    inner = re.sub(r"^\s*<svg\b[^>]*>|</svg>\s*$", "", raw.strip())
    body = [f'<svg x="0" y="0" width="1000" height="612" viewBox="{vb}" preserveAspectRatio="xMidYMid meet">{inner}</svg>']
    return mx_sheet("C-100", "Site plan", "The parcel, the house and the deck as built, distances to the lot lines", body, "Plan · see the scale and north arrow on the plan", meta)


HOOKS = {"S-101": _hook_s101, "A-301": _hook_a301, "A-201": _hook_a201, "D-501": _hook_d501, "S-100": _hook_s100}


# ============================================================================ the permit set: the engine's page under the job's brand
PERMIT_BAD = ("GS Exterior", "GSX", "Deck Division", "Design intent", "design intent", "$", "financ", "Fulton", "Prime+", "LedgerLOK", "Cap-Tor", "HeadLOK rail",
              "G-Tape", "GRK", "Camo ")


def render_permit_set(parts: list, out_dir: str, key: str, name: str, sub: str = "", pdf: bool = False, date_line: Optional[str] = None,
                      renders: Optional[dict] = None, photos: Optional[list] = None, brand=None, no_engineering: bool = False) -> dict:
    """decktakeoff.page.render_permit_set for this job: the engine builds the sheets and the page inside `active()` (the job's sheets,
    words and title block), then the page takes the brand — its logo or text mark, name, lines and colors — and the as-built cover
    words; nothing of GSX stays (checked), and the PDF is printed from that page. photos: the A-501 exhibit (else the job's own)."""
    spec = parts[0]["spec"]
    ext = _ext(spec)
    if ext is None:
        raise ValueError("render_permit_set: the spec carries no Messner job fields — load it with load_job()")
    if photos is not None:
        ext.photos = [dict(p, img=str(Path(p["img"]).resolve())) for p in photos]
    br = brand if (isinstance(brand, dict) and brand.get("lines") is not None and "accent_a" in brand) else load_brand(brand or ext.brand)
    today = date_line or date.today().strftime("%B %d, %Y")
    _CTX["renders"] = bool(renders)
    with active(spec, br, today):
        r = PG.render_permit_set(parts, out_dir, key, name, sub=sub, pdf=False, date_line=today, renders=renders, unbranded=False, no_engineering=no_engineering)
    out = Path(out_dir).resolve()
    page = (out / "page.html").read_text()
    page = brand_page(page, spec, ext, br, name)
    (out / "page.html").write_text(page)
    r["html"] = str(out / "page.html")
    if pdf:
        r["pdf"] = print_pdf(page, r.get("files") or {}, out)
    return r


def brand_page(page: str, spec, ext: Ext, br: dict, name: str) -> str:
    """The permit page under the brand: the band's mark and line, the title, the cover words, the footer and the colors."""
    ab = ext.as_built
    code = SECTIONS[_ed(spec)]["code"] if _ca(spec) else "2021 IRC"
    mark = (f'<img src="{br["logo_dark"]}" alt="{_html.escape(br["name"])}" style="height:44px;width:auto;display:block;margin-bottom:6px">' if br.get("logo_dark")
            else f'<span style="display:inline-block;border-left:3px solid {br["accent_b"]};padding-left:10px;font-weight:900;font-size:22px;letter-spacing:.14em;color:#fff">{_html.escape(br["short"])}</span>')
    page = page.replace('<div class="kick">GS Exterior Experts · Deck Division · permit set</div>',
                        f'{mark}<div class="kick">{_html.escape(br["name"])} · ' + ("as-built permit set" if ab else "permit set") + '</div>', 1)
    page = page.replace(f"<title>{_html.escape(name)} — Permit Set</title>", f"<title>{_html.escape(name)} — " + ("As-Built Permit Set" if ab else "Permit Set") + "</title>", 1)
    cover = ((f"Existing deck — as built: the record of the deck as it stands, for its legalization. Dimensions and members are field-verified from the as-built survey "
              f"and photos{' (A-501)' if ext.photos else ''}. " if ab else "") + (f"Checked against the {code} (R507)" + ("; the stamped structural design governs" if spec.extras.engineered else "") + ". ")
             + "Do not scale. This set carries no pricing.")
    page = re.sub(r'(<div class="cover-list"><h2 class="kicker" id="g-index">Sheet index</h2><ol class="index">.*?</ol>)<p>.*?</p>', lambda m: m.group(1) + f"<p>{_html.escape(cover)}</p>", page, count=1, flags=re.S)
    foot = " · ".join(_html.escape(x) for x in (br.get("lines") or [br["footer"]]))
    page = re.sub(r"<footer><span>GS Exterior Experts · Deck Division · Jade Pender 303-550-9558</span><span>.*?</span></footer>",
                  lambda m: f"<footer><span>{foot}</span><span>" + ("As-built permit set — drawings only. Existing deck as built; " if ab else "Permit set — drawings only; ") + f"{code}.</span></footer>", page, count=1, flags=re.S)
    page = page.replace('<h2 class="kicker" id="g-views">3D views <span class="tag">design intent</span></h2>',
                        '<h2 class="kicker" id="g-views">3D views <span class="tag">' + ("the model of the deck as built" if ab else "model") + "</span></h2>")
    css = (f"<style>:root{{--gold:{br['accent_b']};--gold-ink:{br['accent_a']};}}@media (prefers-color-scheme: dark){{:root:not([data-theme=\"light\"]){{--gold:{br['accent_b']};--gold-ink:#9cc3e6;}}}}"
           f":root[data-theme=\"dark\"]{{--gold:{br['accent_b']};--gold-ink:#9cc3e6;}}.band .kick{{color:#9cc3e6;}}"
           "@media print{.sheet-page:last-of-type{break-after:auto;page-break-after:auto;} main > footer{display:none;}}</style>")   # every sheet carries the brand: no page for the footer alone
    page = page.replace("</head>", css + "</head>", 1)
    txt = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    txt = re.sub(r"data:[a-z+/.-]+;base64,[A-Za-z0-9+/=]+", "", txt)
    left = [b for b in PERMIT_BAD if b in txt]
    assert not left, f"the {br['short']} permit set still carries: {left}"
    return page


def print_pdf(page: str, files: dict, out: Path) -> str:
    """The page to Letter landscape (the engine's print path), the render files beside it."""
    import shutil
    from decktakeoff.render import _chromium
    from playwright.sync_api import sync_playwright
    for k, v in files.items():
        (out / k).parent.mkdir(parents=True, exist_ok=True); shutil.copy(v, out / k)
    (out / "_print.html").write_text(page.replace(' loading="lazy"', ""))
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1400, "height": 1000})
        pg.goto("file://" + str(out / "_print.html")); pg.wait_for_timeout(2500)
        pg.emulate_media(media="print")
        pg.pdf(path=str(out / "page.pdf"), format="Letter", landscape=True, print_background=True, prefer_css_page_size=True)
        b.close()
    return str(out / "page.pdf")
