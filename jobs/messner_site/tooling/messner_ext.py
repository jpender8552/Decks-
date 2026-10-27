"""Messner as-built permit set — the job-local extension (149 Morning Sun Ave, Mill Valley, Marin County; owner Adam Messner).

An existing deck documented as built (extras.facts): every statement on the sheets is the observed fact or carries (V); the
elevations, the section and the details are drawn true (piers at two levels on a sloped grade, the house's cantilevered main
floor); plans, elevations and sections are drawn at standard architectural scales of 1/4" = 1'-0" or more for 24x36 output
(1000 x 700 sheet units on the 24" height), each labeled with a graphic bar; render_permit_set(..., sheet_size="archd" |
"tabloid" | "letter") prints one sheet a page, a reduced size stamped REDUCED COPY — NOT TO SCALE.

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
  site.site_plan              {"field_svg": the site plan's 1000 x 612 drawing field -> C-100, 1:1; "vicinity_svg": 300 x 220 -> G-001, 1:1}
  extras.facts                the deck as built, in the words every sheet prints (an existing deck: each statement is the observed
                              fact or carries (V)) and the geometry the drawings draw true: pier tops by row (pier_top_in), pier
                              diameter and reveal, the grade profile across the deck (grade_profile_in: [[y, z], ...] inches out
                              from the house / from the inner pier tops), a retaining wall, the house's main-floor cantilever past
                              the basement wall (house_cantilever_in), stringers per flight, the one lateral tie seen
                              (lateral_tie_seen_ft_from_north) — see messner_spec.json for every key
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
    site_plan: dict = field(default_factory=dict)           # {"json": siteplan.json (merged into site.plan when in the engine's format), "field_svg":
                                                            #   C-100_submittal_field.svg (the 1000 x 612 field, embedded 1:1 as C-100), "vicinity_svg":
                                                            #   vicinity.svg (300 x 220, embedded 1:1 on G-001)}
    knee_brace_layout: dict = field(default_factory=dict)   # the braces as built, by beam line from the house: {"inner": {"single": [post index, ...],
                                                            #   "y": [...]}, "outer": {...}} — single: one brace toward mid-span, y: both ways along the
                                                            #   beam; {} -> the engine's (both ways at every post). Braces stay in the beam's plane.
    footing_words: str = ""                                 # S-100's footing description as built (over the engine's sizing words)
    facts: dict = field(default_factory=dict)               # the deck as built: words and true geometry (extras.facts; see the docstring)

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
           "extras": ("as_built", "as_built_note", "keep_connection_details", "verify", "notes", "facts"),
           "site": ("codes", "design_criteria", "wui", "wui_listing", "as_built", "code_edition", "site_plan")}

# the code sections the sheets cite, by edition (2025: the 2025 CRC renumbered the guards, stairs, handrails, glazing and lighting
# sections, and moved the wildfire rules to the 2025 CWUIC)
SECTIONS = {
    "2022": dict(code="2022 CRC", guard="R312.1", guard_where="R312.1.1", guard_height="R312.1.2", openings="R312.1.3", glazing="R308.4.4", glazing_mark="R308.1",
                 stairs="R311.7", stair_width="R311.7.1", handrail="R311.7.8", stair_light="R303.7", wui="CRC R337", wui_deck="CRC R337.9", wui_flash="",
                 footing_depth="R403.1.4", ledger="R507.9.1.3", ledger_flash="R507.2.4", asce="ASCE 7-16"),
    "2025": dict(code="2025 CRC", guard="R321.1", guard_where="R321.1.1", guard_height="R321.1.2", openings="R321.1.3", glazing="R324.4.4", glazing_mark="R324.1",
                 stairs="R318.7", stair_width="R318.7.1", handrail="R320", stair_light="R325.7", wui="CWUIC Ch. 5", wui_deck="CWUIC 504.7.3", wui_flash="CWUIC 504.7.3.1",
                 footing_depth="R403.1.4", ledger="R507.9.1.3", ledger_flash="R507.9.1.5 / R703.4", asce="ASCE 7-22"),
}
# field-verify keys (extras.verify): where each is marked (V)
VERIFY_KEYS = ("deck_edge", "height", "border_color", "ledger", "ledger_flashing", "beam_positions", "species", "splices", "post_stations", "post_lengths",
               "post_caps", "knee_brace_bolts", "footings", "lateral_ties", "joist_ties", "guard_system", "guard_blocking", "glass_marks", "stair_landing", "stair_base",
               "stair_guard", "house_cantilever")


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
        par = d.get("parcel") if isinstance(d, dict) else None
        if isinstance(par, list) and par and all(isinstance(q, (list, tuple)) and len(q) == 2 for q in par):
            spec.site.plan = _merge(spec.site.plan or {}, d)   # (a site-plan agent's own format is not the engine's: left alone)
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


def _fx(key: str, default: Any = "", ext: Optional[Ext] = None) -> Any:
    """A fact of the deck as built (extras.facts), or default."""
    ext = ext or _CTX.get("ext")
    return ((ext.facts or {}).get(key, default) if ext is not None else default) or default


def _asb(ext: Optional[Ext] = None) -> bool:
    """An existing deck recorded as built from its facts: the sheets print the facts, never the engine's defaults."""
    ext = ext or _CTX.get("ext")
    return bool(ext is not None and ext.as_built and ext.facts)


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


# ============================================================================ true scales: every sheet is 1000 x 700 units, 24" tall at 24x36
SHEET_SIZES = {"archd": (36.0, 24.0, "24x36"), "tabloid": (17.0, 11.0, "11x17"), "letter": (11.0, 8.5, "8-1/2x11")}
UPI = 700.0 / 24.0                        # sheet units per inch at 24x36 (1 unit = 0.0342857")
ARCH_SCALES = [(3.0, '3"'), (1.5, '1-1/2"'), (1.0, '1"'), (0.75, '3/4"'), (0.5, '1/2"'), (0.375, '3/8"'), (0.25, '1/4"'), (0.1875, '3/16"'),
               (0.125, '1/8"'), (0.09375, '3/32"'), (0.0625, '1/16"')]
MIN_IPF = 0.25                            # Marin: plans and elevations 1/4" = 1'-0" minimum


def snap_scale(sc_fit: float, floor_ipf: float = MIN_IPF) -> Tuple[Optional[float], str]:
    """The largest standard architectural scale (units per foot at 24x36) not larger than a view's fitted one, and its label;
    (None, "") when even the floor scale does not fit (the view keeps its fit, labeled AS SHOWN with a graphic bar)."""
    for ipf, lab in ARCH_SCALES:
        u = ipf * UPI
        if ipf >= floor_ipf - 1e-9 and u <= sc_fit + 1e-9:
            return u, f"{lab} = 1'-0\""
    return None, ""


def _note_view(kind: str, px0: float, py0: float, w: float, h: float, u: float, lab: str) -> None:
    _CTX.setdefault("views", []).append(dict(kind=kind, px0=px0, py0=py0, w=w, h=h, u=u, lab=lab))


def _snap_plan(orig):
    def plan_xform(x0, x1, y0, y1, px0, py0, pw, ph):
        X, Y, sc = orig(x0, x1, y0, y1, px0, py0, pw, ph)
        if not _CTX.get("true_scale"):
            return X, Y, sc
        u, lab = snap_scale(sc)
        u = u or sc
        _note_view("plan", px0, py0, (x1 - x0) * u, (y1 - y0) * u, u, lab)
        return (lambda x: px0 + (x - x0) * u), (lambda y: py0 + (y - y0) * u), u
    return plan_xform


def _snap_elev(orig):
    def elev_xform(x0, x1, z0, z1, px0, py0, pw, ph):
        X, Z, sc = orig(x0, x1, z0, z1, px0, py0, pw, ph)
        if not _CTX.get("true_scale"):
            return X, Z, sc
        u, lab = snap_scale(sc)
        u = u or sc
        _note_view("elevation", px0, py0, (x1 - x0) * u, (z1 - z0) * u, u, lab)
        return (lambda x: px0 + (x - x0) * u), (lambda z: py0 + (z1 - z) * u), u
    return elev_xform


def scale_block(o: List[str], x: float, y: float, title: str, u: float, lab: str, anchor: str = "start") -> float:
    """A view's title, its scale ("SCALE: 1/4" = 1'-0" @ 24x36", or AS SHOWN) and a graphic scale bar in the view's own units, so it
    stays true at any print size. Returns the y under it."""
    br = _CTX.get("brand") or {}
    o.append(T(x, y, title, 8.4, 800, fill=br.get("accent_b", INK)))
    o.append(T(x, y + 10.5, f"SCALE: {lab} @ 24x36" if lab else "SCALE: AS SHOWN (graphic)", 6.8, 700))
    span = next((f_ for f_ in (1, 2, 4, 5, 8, 10, 16, 20, 40) if f_ * u >= 70), 40)
    step = span / 4
    bx, by = x, y + 15.5
    for k_ in range(4):
        o.append(R(bx + k_ * step * u, by, step * u, 3.2, INK if k_ % 2 == 0 else "#ffffff", INK, 0.5))
    for k_, lab_ in ((0, "0"), (2, f"{span / 2:g}"), (4, f"{span:g} FT")):
        o.append(T(bx + k_ * step * u, by + 10.5, lab_, 5.8, 700, "middle" if k_ < 4 else "start"))
    return by + 14


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
                    renders=bool(prev_ctx.get("renders")), orig=dict(sheet=DW.sheet, sheet_meta=DW.sheet_meta),
                    sheet_size=prev_ctx.get("sheet_size") or "archd", true_scale=bool(ext and _asb(ext)), siteplan_scale=prev_ctx.get("siteplan_scale", ""))
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
        patch(DW, "plan_xform", _snap_plan(DW.plan_xform))
        patch(DW, "elev_xform", _snap_elev(DW.elev_xform))
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
        n_str = int(_fx("stringers_per_flight", 0, ext) or 0)
        if n_str:                                                  # as built: the stringers counted in the photos
            for st in L.stairs:
                if getattr(st, "build", "stringers") != "box":
                    st.stringers = n_str
        L._mx_ties = tie_positions(spec, L)
        L._mx_tie_seen = tie_seen(spec, L)
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


def tie_seen(spec, L) -> List[Tuple[float, float]]:
    """(x, wall y) of the lateral tie(s) seen as built (facts.lateral_tie_seen_ft_from_north: ft from the right / north end of the
    ledger), on the nearest joist — tagged on the plan with (V)."""
    ext = _ext(spec)
    ft = _fx("lateral_tie_seen_ft_from_north", None, ext) if ext else None
    zl = [z for z in L.zones if z.frame.ledger]
    if ft is None or not zl:
        return []
    right = max(z.x0 + z.W for z in zl)
    x = right - float(ft) * 12.0
    js = sorted(z.x0 + q for z in zl for q in z.frame.joist_x + z.frame.pf_x)
    if js:
        x = min(js, key=lambda q: abs(q - x))
    return [(round(x, 2), next((z.wall_y for z in zl if z.x0 - 0.5 <= x <= z.x0 + z.W + 0.5), zl[0].wall_y))]


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
    if _asb(ext):
        _facts_schedule(t, spec, ext)
        return
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


def _facts_schedule(t, spec, ext: Ext) -> None:
    """An existing deck: the schedule and the summary say what was seen (extras.facts), each estimate marked (V) — none of the
    engine's sizing, spacing or fastening defaults."""
    f = lambda k, d="": _fx(k, d, ext)
    sch, sm, L = t.schedule, t.summary, t.layout
    sch["Ledger"] = "; ".join(x for x in (f("ledger"), f("ledger_flashing"), f("ledger_support")) if x)
    if f("lateral_ties"):
        sch["Lateral"] = f("lateral_ties")
    if f("joist_ties"):
        sch["Joist ties"] = f("joist_ties")
    if spec.framing.knee_braces:
        sch["Knee braces"] = "; ".join(x for x in (f("knee_braces"), f("knee_brace_ends")) if x)
    sch["Blocking"] = "; ".join(x for x in (f("blocking"), f("guard_blocking") if ext.fascia else "") if x)
    sch["Field"] = f"{f('decking')}; border {f('border')}; {f('deck_fasteners')}"
    sch["Fascia"] = f("fascia")
    for k in ("Face screws", "Picture frame + stairs", "Joist tape"):
        sch.pop(k, None)
    if L.rail:
        sch["Rail"] = "; ".join(x for x in (f("guard"), f("guard_bracket"), f("guard_blocking"), ext.glass_note, f("stair_guard"), f("handrail")) if x)
    sm["height"] = f("height") or sm.get("height")
    sm["joists"] = f("joists") or sm["joists"]
    sm["rims"] = f("rims") or sm["rims"]
    sm["posts"] = "; ".join(x for x in (f("posts"), f("post_caps")) if x) or sm["posts"]
    sm["decking"] = f"{f('decking')}; picture frame and breakers in {f('border')}; {f('deck_fasteners')}"
    if L.rail:
        sm["rail"] = f("guard") + f"; {L.rail.rail_lf:g} LF of deck edge" + ("; stairs and landing in vertical cable" if ext.vertical else "")
    if L.stairs and f("stairs"):
        sm["stairs"] = ["; ".join(x for x in (f("stairs"), f("stringers"), f("stair_connectors"), f("tread_angles"), f("stair_base")) if x)]


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
    # ---- the deck as built: piers at their true levels, the house's cantilevered main floor, nothing invented
    if _asb(ext):
        _scene_as_built(S, L, ext)
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


def beam_rows(L) -> Dict[str, Any]:
    """The drop-beam lines by row: {"inner": the line nearest the house, "outer": the farthest}."""
    lines = sorted([bl for bl in (L.beam_lines or []) if bl.kind == "drop"], key=lambda q: q.y)
    return {"inner": lines[0], "outer": lines[-1]} if lines else {}


def pier_top_ft(row: str, ext: Optional[Ext] = None) -> float:
    """A row's pier-top elevation (ft) from the job's datum (the inner-row pier tops), facts.pier_top_in."""
    return float((_fx("pier_top_in", {}, ext) or {}).get(row, 0.0)) * IN


def grade_profile(ext: Optional[Ext] = None) -> List[Tuple[float, float]]:
    """The grade across the deck as [(y ft out from the house, z ft from the datum)], facts.grade_profile_in."""
    return [(float(y) * IN, float(z) * IN) for y, z in (_fx("grade_profile_in", [], ext) or [])]


def grade_at(y_ft: float, ext: Optional[Ext] = None) -> float:
    """The grade (ft) at y (ft), on the profile's lowest branch where it steps (a retaining wall): the ground a pier stands in."""
    gp = grade_profile(ext)
    if not gp:
        return 0.0
    if y_ft <= gp[0][0]:
        return gp[0][1]
    for (ya, za), (yb, zb) in zip(gp, gp[1:]):
        if ya <= y_ft <= yb and yb > ya:
            return za + (zb - za) * (y_ft - ya) / (yb - ya)
    return gp[-1][1]


def _scene_as_built(S, L, ext: Ext) -> None:
    """The deck as built in the model the sheets are drawn from: the beam rows' piers ~13" round with their tops at the row's own
    level (facts.pier_top_in: the outer row ~2' below the inner), the posts and bases on them; the house's main floor cantilevered
    past the basement wall (facts.house_cantilever_in) with its soffit; the engine's flat yard, door and windows left out (the house
    openings are not recorded)."""
    import dataclasses as _dc
    B = S.boxes
    spec = L.spec
    B[:] = [b for b in B if b.kind != "ground" and not (b.kind == "glass" or (b.kind == "trim" and (b.tag or "") != "fascia board"))]
    rows = beam_rows(L)
    dia = float(_fx("pier_dia_in", 13, ext)) * IN
    rev = float(_fx("pier_reveal_in", 8, ext)) * IN
    at = []                                                   # (x, y, row) of every beam-line post, feet
    for row, bl in rows.items():
        at += [(px * IN, bl.y * IN, row) for px in bl.posts_x]
    for b in B:
        if b.kind not in ("footing", "base", "post") or (b.tag or "").startswith(("landing", "stair")):
            continue
        cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
        hit = next((r for x, y, r in at if abs(cx - x) < 0.3 and abs(cy - y) < 0.3), None)
        if hit is None:
            continue
        zp = pier_top_ft(hit, ext)
        if b.kind == "footing":
            b.x0, b.x1, b.y0, b.y1, b.shape = cx - dia / 2, cx + dia / 2, cy - dia / 2, cy + dia / 2, "cyl"
            b.z0, b.z1 = min(zp - rev, grade_at(cy, ext)) - 1.0, zp
            b.tag = f"existing pier ({hit} row)"
        elif b.kind == "base":
            b.z0, b.z1 = zp, zp + 0.12
        else:
            b.z0 = zp + 0.1
    cant = float(_fx("house_cantilever_in", 0, ext)) * IN
    if cant > 0:
        zt = spec.geometry.height_in * IN
        jtop = zt - CAT.decking_facts(spec.decking.collection)["thick"] * IN
        z_soffit = jtop - CAT.actual(spec.framing.ledger_size or "2x12")[1] * IN - 1.0 * IN
        add = []
        for b in B:
            if b.kind == "house" and abs(b.y1 - min(z.wall_y for z in L.zones) * IN) < 0.05 and b.z0 < z_soffit < b.z1:
                add.append(_dc.replace(b, kind="basement", layer="house", y1=b.y1 - cant, z0=max(b.z0, grade_at(b.y1 - cant - 0.05, ext)), z1=z_soffit,
                                       tag=(b.tag or "house") + " — basement wall"))
                b.z0 = z_soffit
                b.tag = (b.tag or "house") + " — main floor, cantilevered"
        B.extend(add)


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
    if _asb(ext):
        return dict(job_line=f"{s.site.address}, {s.site.city} · existing deck, as built".strip(" ,·"),
                    rev_line=f"{br['short']} · {_CTX['date']} · Rev 0 · AS-BUILT PERMIT SET",
                    footer=f"Prepared by: {br['short']} — {br['legal_name']} · " + " · ".join(br["lines"][1:2]) + " · As built — (V) = field-verify"
                    + (" · the stamped design governs" if s.extras.engineered else ""), mx=True)
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
    scale_note = _scale_note(num, scale_note)
    if _asb(ext) and num in SUB_AS_BUILT:
        sub = SUB_AS_BUILT[num]
    lw = 34 * br["aspect"]
    rx = W_ - 18 - lw - 12                                      # the job / rev lines right-aligned clear of the logo
    hdr = [R(0, 0, W_, 46, INK, "none", 0), T(18, 27, num, 20, 900, fill=br["accent_b"]), T(110, 22, title.upper(), 15, 900, fill="#f3ead9"),
           T(110, 39, textwrap.shorten(_words(sub), 104 if _asb(ext) else 100, placeholder="…"), 9.5 if not _asb(ext) else 8.8, 400, fill="#d8cfbf"),
           T(rx, 20, textwrap.shorten(meta["job_line"], 64 if _asb(ext) else 56, placeholder="…"), 9.5, 700, "end", "#d8cfbf"), T(rx, 36, meta["rev_line"], 8.5, 400, "end", "#b8b0a2")]
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


def _scale_note(num: str, note: str) -> str:
    """The footer's scale note: the scales the sheet's views were drawn at (at 24x36), or NOT TO SCALE; a reduced copy says so."""
    views = _CTX.pop("views", [])
    if not _CTX.get("true_scale"):
        return note
    seen, labs = set(), []
    for v in views:
        k = (v["kind"], v["lab"])
        if k not in seen:
            seen.add(k)
            labs.append(f"{v['kind'].upper()} {v['lab'] or 'AS SHOWN (graphic bar)'}")
    for k, v in (_CTX.pop("extra_scales", None) or []):
        labs.append(f"{k.upper()} {v}")
    rest = re.sub(r"(?i)\b(?:not to (?:a common )?scale|no scale)\b", "", note)
    rest = " · ".join(x.strip().rstrip(",") for x in re.split(r"·", rest) if x.strip().rstrip(",") and x.strip().lower() not in ("plan", "plans", "elevations", "section"))
    if labs:
        out = "SCALE @ 24x36: " + " · ".join(dict.fromkeys(labs)) + (" · " + rest if rest else "")
    else:
        out = "NOT TO SCALE" + (" · " + rest if rest else "")
    if (_CTX.get("sheet_size") or "archd") != "archd":
        out = "REDUCED COPY — NOT TO SCALE · " + out
    return out


def _paint(svg: str, br: dict) -> str:
    """The engine's gold in the brand's colors: text and strokes in the brand blue, filled badges in a light tint of it."""
    tint = "#bcd6ee"
    svg = re.sub(r'(<(?:circle|rect|polygon)\b[^>]*?)fill="#d49e1b"', lambda m: m.group(1) + f'fill="{tint}"', svg)
    return svg.replace('fill="#d49e1b"', f'fill="{br["accent_b"]}"').replace('stroke="#d49e1b"', f'stroke="{br["accent_b"]}"')


_AS_BUILT_WORDS = [
    (r"\bthe new decks\b", "the decks"), (r"\bnew decks\b", "decks"), (r"\bNew deck\b", "Existing deck — as built"), (r"\bnew deck\b", "existing deck — as built"),
    (r"\bthe new work\b", "the deck"), (r"\bnew work\b", "the deck"), (r"\bNew concrete\b", "Concrete"), (r"\bnew roof covers?\b", "roof cover"),
    (r"; field-verify grade before setting the piers", ""), (r"\bVintage Mahogany\b", "a darker Vintage board (color V)"), (r" — field-measure each\.?", ""), (r"Rail LF for labor = deck-edge LF of actual rail\.?", ""),
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
                              (r"\bR303\.7\b", "R325.7"), (r"CRC R337(?:\.\d+)*", "CWUIC 504.7.3"), (r"\bASCE 7-16\b", "ASCE 7-22")):
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
        if _asb(ext):
            return _facts_key(L, S, ks, ext)
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


def _facts_key(L, S, ks, ext: Ext):
    """The isometric keys of an existing deck: every label the observed fact or (V) (extras.facts), in the engine's build order."""
    f = lambda k, d="": _fx(k, d, ext)
    s = L.spec
    probe = lambda pred, kind, mat="timber", tag="": pred(Box(kind, 0, 1, 0, 1, 0, 1, mat, tag=tag))
    nst = int(f("stringers_per_flight", 0) or 0)
    words = [
        ("post", f"6x6 PT post, ~9' inner / ~11' outer (V), on a cast-in CBSQ66-type base on a ~13\" round concrete pier (V)"),
        ("brace", "6x6 knee brace at 45° in the beam plane (layout on S-101); end connections not visible (V)"),
        ("beam", "6x12 drop beams B1 / B2 (V); post caps CCQ/ECCQ-type — model and fasteners (V)"),
        ("joist", "2x10 PT DF joist @ 16\" o.c. (grade stamp (V)); LUS210Z hangers at the ledger"),
        ("rim", "2x10 rim (single ply), PVC fascia over it"),
        ("ledger", "2x12 ledger (V) on the cantilevered main-floor band (V): 1/2\"-5/8\" bolts or lags, plate washers ~16\" o.c. (V); flashing (V)"),
        ("block", "2x10 solid blocking over both beams + mid-span of the house-side bay"),
        ("board", f"{s.decking.brand} {s.decking.collection} {s.decking.color} field decking, {f('deck_fasteners')}"),
        ("border", f"Picture frame + breaker boards: {f('border')}"),
        ("fascia", f("fascia") or "Fascia"),
        ("tread", f"Stair: 16 risers (11 + 5), {nst or 'the'} stringers per flight (notched 3x center + 2 solid outer); lower flight on a PT plank at grade (V)"),
        ("toprail", f"Black aluminum guard, IRX-type (V), {s.railing.height_in:g}\": glass infill, fascia-mounted posts ~5-6' o.c."),
    ]
    out = []
    for lab, pred, where, pick in ks:
        hit = next((w for k, w in words if probe(pred, k, "railmetal" if k == "toprail" else ("deck" if k in ("board", "border") else "timber"))), None)
        if hit is None and probe(pred, "stringer"):
            hit = dict(words)["tread"]
        if hit is None:
            continue                                                  # a part the engine labels that this deck has no fact for
        out.append((hit, pred, where, pick))
        if hit == dict(words)["toprail"]:
            if ext.fascia:
                out.append(("Fascia bracket: (2) hex lags + washers per flange into the rim, as seen; blocking behind not visible (V)", lambda b: b.kind == "railbracket", (0.5, 0.5, 0.5), "first"))
            if ext.glass:
                out.append((f"Glass infill panel: tempered safety glazing — the etched mark (V) ({_code(s)} R308.4.4)", lambda b: b.kind == "glasspanel", (0.5, 0.5, 0.6), "mid"))
            if ext.vertical:
                out.append(("Stair + landing guard: vertical stainless cable, ~38\" over the nosings (V)", lambda b: (b.tag or "") == "vertical stair cable", (0.5, 0.5, 0.5), "mid"))
            if ext.stair_handrail != "none":
                out.append(("Graspable handrail, one side of each flight, looped returns", lambda b: (b.tag or "") == "graspable handrail", (0.5, 0.5, 0.5), "mid"))
    return [k for k in out if any(k[1](b) for b in S.boxes)]


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
        if _asb(ext):                                            # an existing deck: the elevations, the section and the details drawn as built
            mine = {"A-202": lambda: ("A-202", "Elevations — as built", sheet_a202_facts(L, _CTX["S"], t, meta)),
                    "A-301": lambda: ("A-301", "Building section — as built", sheet_a301_facts(L, _CTX["S"], t, meta)),
                    "D-501": lambda: ("D-501", "Details — as built", sheet_d501_facts(L, _CTX["S"], t, meta))}
            out = [mine[x[0]]() if x[0] in mine else x for x in out]
        photos = photo_sheets(ext.photos, meta)
        at = next((i for i, x in enumerate(out) if x[0].startswith("D-")), len(out))
        out = out[:at] + photos + out[at:]
        notes = notes_sheets(ext.notes, meta)
        if notes:                                                # the job's own general notes replace the engine's G-002
            out = [out[0]] + notes + [x for x in out[1:] if x[0] != "G-002"]
        svg_c = Path(str((ext.site_plan or {}).get("field_svg") or ""))
        if str(svg_c) and svg_c.is_file():                       # the site-plan agent's submittal field (1000 x 612 units, true scale) as C-100
            c100 = ("C-100", "Site plan", site_plan_sheet(svg_c, meta))
            out = [x for x in out if x[0] != "C-100"]
            at = next((i for i, x in enumerate(out) if not x[0].startswith("G-")), len(out))
            out = out[:at] + [c100] + out[at:]
        if ext.callouts:
            out.append(("D-505", "Connection details — guard, ties, bracing", sheet_d505_facts(L, _CTX["S"], t, meta) if _asb(ext) else sheet_d505(L, _CTX["S"], t, meta)))
        index = [(n_, ttl) for n_, ttl, _ in out]
        if _asb(ext) and index and index[0][0] == "G-001":
            index[0] = ("G-001", "Cover sheet · project data · design criteria")
        if _CTX.get("renders"):
            index.insert(next((i for i, (n_, _) in enumerate(index) if n_ == "A-002"), 1), ("A-001", "3D views of the model"))
        out[0] = (("G-001", "Cover sheet · project data · design criteria", sheet_g001_facts(L, _CTX["S"], t, meta, index)) if _asb(ext) else
                  ("G-001", "General notes · design criteria", sheet_g001(L, _CTX["S"], t, meta, index)))
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
        rows.append(("Wildfire", f"Wildland-Urban Interface fire area: {_sec(spec, 'wui') or code + ' R337'} — walking surfaces per {_sec(spec, 'wui_deck') or 'R337.9'}, the guard aluminum and glass "
                     + ("(general notes, section 9)" if _asb(ext) else "(see the WUI notes)")))
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
    if _asb(ext) and _fx("summary", None, ext):
        return [(str(k), str(v)) for k, v in _fx("summary", [], ext)]
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
            ("", [f"Owner: {s.client}"] if s.client else []),
            ("", [f"{_fx('area', '', ext)} · surface ~10'-9\" (inner row) to ~12'-9\" (outer row) over the pier tops (V)"] if _asb(ext) else
                 [f"{L.deck_sf:g} SF · surface {ftin(s.geometry.height_in)} above grade · {len(L.zones)} zone{'s' if len(L.zones) > 1 else ''}"])]
    if _fx("prior_permit", "", ext):
        proj.append(("", textwrap.wrap(_fx("prior_permit", "", ext), wrapL + 8)))
    left = [("PROJECT", [r for r in proj if r[1]])]
    if ext.as_built:
        note = ext.as_built_note or "Dimensions and members are field-verified from the as-built survey and photos (A-501); the sheets record the deck as it stands."
        left.append(("SCOPE", [("", ["Existing deck — as-built (legalization of the deck as built)"])] + ([("", textwrap.wrap(_fx("scope", "", ext), wrapL + 8))] if _fx("scope", "", ext) else [])
                     + [("", textwrap.wrap(note, wrapL + 8))]))
    left.append(("DESIGN CRITERIA", [(k, textwrap.wrap(v, wrapL - 12)[:3]) for k, v in _criteria(s, ext, L, t)]))
    left.append(("STRUCTURE (AS BUILT)" if ext.as_built else "STRUCTURE", [(k, textwrap.wrap(_words(v), wrapL - 12)[:3 if not _asb(ext) else 4]) for k, v in _structure(s, ext, L, t)]))
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
                  (f"Guard: black aluminum posts and rails (IRX-type (V)), noncombustible" + (", tempered glass infill (safety mark (V))" if ext.glass else "")
                   + (", stainless cable on the stairs" if ext.vertical else "")) if _asb(ext) else
                  (f"Guard: {fascia_mount(s)['name'] or CAT.rail_name(s.railing.system)} — noncombustible aluminum posts and rails"
                   + (", tempered glass infill" if ext.glass else "") + (", stainless cable on the stairs" if ext.vertical else "")),
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


def _col_blocks(o: List[str], x: float, y0: float, w: float, blocks, y_max: float, label_w: float = 74.0, base: float = 7.6) -> float:
    """A cover-sheet column: [(heading, [(label, text)])], each text wrapped to the column; the font steps down until it all fits."""
    accent = _CTX["brand"]["accent_b"]
    for k in (1.0, 0.96, 0.92, 0.88, 0.84, 0.8, 0.76, 0.72, 0.68):
        fs, lw = base * k, label_w * k
        lh = fs * 1.3
        wrap = lambda lab, txt: textwrap.wrap(txt, max(12, int((w - (lw if lab else 0)) / (fs * 0.53)))) or [""]
        h = sum(fs * 1.3 + 5 + sum(len(wrap(l_, t_)) * lh + 2.5 for l_, t_ in rows) + 7 for _, rows in blocks)
        if y0 + h <= y_max:
            break
    y = y0
    for head, rows in blocks:
        o.append(T(x, y + fs * 1.15, head, fs * 1.2, 800, fill=accent)); y += fs * 1.3 + 5
        for lab, txt in rows:
            ls = wrap(lab, txt)
            if lab:
                o.append(T(x, y + fs, lab, fs, 800))
            for j, ln in enumerate(ls):
                o.append(T(x + (lw if lab else 0), y + fs + j * lh, ln, fs, 400))
            y += len(ls) * lh + 2.5
        y += 7
    return y


def vicinity_block(o: List[str], x: float, y: float, path: Optional[str]) -> float:
    """The vicinity map (the site-plan agent's vicinity.svg, viewBox 0 0 300 220 in sheet units) embedded 1:1, or a placeholder."""
    br = _CTX["brand"]
    o.append(T(x, y + 9, "VICINITY MAP", 9.1, 800, fill=br["accent_b"]))
    y += 14
    p = Path(path) if path else None
    if p and p.is_file():
        raw = re.sub(r"<\?xml[^>]*\?>\s*|<!DOCTYPE[^>]*>\s*", "", p.read_text())
        root = re.search(r"<svg\b[^>]*>", raw)
        m = re.search(r'viewBox="([-\d.\s]+)"', root.group(0) if root else "")
        vb = " ".join((m.group(1) if m else "0 0 300 220").split())
        inner = _embed_clean(re.sub(r"^\s*<svg\b[^>]*>|</svg>\s*$", "", raw.strip()))
        o.append(_embed_g(inner, vb, x, y, 300.0, 220.0, "g001vicinity"))
        o.append(R(x, y, 300, 220, "none", INK, 0.6))
        if not re.search(r"(?i)scale|n\.?t\.?s", re.sub(r"<[^>]+>", " ", inner)):
            o.append(T(x + 296, y + 216, "N.T.S.", 6.6, 800, "end"))
    else:
        o.append(R(x, y, 300, 220, "#ffffff", INK, 0.6, 'stroke-dasharray="4 3"'))
        o.append(T(x + 150, y + 104, "VICINITY MAP — N.T.S.", 8.4, 800, "middle", MUTE))
        o.append(T(x + 150, y + 118, "149 Morning Sun Ave, Mill Valley (unincorporated Marin County)", 6.6, 600, "middle", MUTE))
    return y + 220 + 10


def sheet_g001_facts(L, S, t, meta, index) -> str:
    """G-001 for the existing deck: the County's cover items — the project and its prior permit, the owner-builder, the scope, the
    person in responsible charge, deferred submittals, conventional and engineered construction — the design criteria and codes,
    the vicinity map, the sheet index and the field-verify pointer; three columns, sized to fit. The structure summary is on G-002."""
    s, ext = L.spec, _ext(L.spec)
    f = lambda k, d="": _fx(k, d, ext)
    cv = f("cover", {}) or {}
    note = ext.as_built_note or ""
    c1 = [("PROJECT", [("", f"{s.site.address}, {s.site.city}, {s.site.state} {s.site.zip}"), ("", s.site.notes or ""), ("", cv.get("owner", "")),
                       ("", f"{f('area')} · surface ~10'-9\" (inner row) to ~12'-9\" (outer row) over the pier tops (V)"), ("", f("prior_permit"))]),
          ("SCOPE", [("", "Existing deck — as-built (legalization of the deck as built)."), ("", f("scope")), ("", note)]),
          ("PERSON IN RESPONSIBLE CHARGE", [("", q) for q in cv.get("responsible", [])]),
          ("DEFERRED SUBMITTALS", [("", q) for q in cv.get("deferred", ["None."])]),
          ("CONVENTIONAL / NON-CONVENTIONAL CONSTRUCTION", [("", q) for q in cv.get("conventional", [])])]
    c1 = [(h, [r for r in rows if r[1]]) for h, rows in c1]
    crit = []
    for k, v in _criteria(s, ext, L, t):
        if k == "Footing depth" and cv.get("footing_depth"):
            v = re.sub(r"^Footing depth:\s*", "", cv["footing_depth"])
        crit.append((k, v))
    c2 = [("DESIGN CRITERIA", crit), ("CODES", [("", c) for c in _codes(s, ext)])]
    o: List[str] = []
    _col_blocks(o, 20, 6, 300, c1, 606, base=7.6)
    _col_blocks(o, 345, 6, 300, c2, 606, label_w=70, base=7.4)
    y3 = vicinity_block(o, 670, 6, (ext.site_plan or {}).get("vicinity_svg"))
    c3 = [("SHEET INDEX", [("", f"{n_}   {ttl}") for n_, ttl in index]),
          ("FIELD-VERIFY (V)", [("", "(V) marks a value taken from the photos, sketches or the 2018 design: the owner verifies it in the field before the final "
                                     f"submittal. The {len(ext.verify)} items are listed first on G-002, with the structure as built.")])]
    _col_blocks(o, 670, y3, 310, c3, 606, base=7.6)
    o.append(LN(333, 8, 333, 600, "#d8cfbf", 0.6)); o.append(LN(658, 8, 658, 600, "#d8cfbf", 0.6))
    return mx_sheet("G-001", "Cover sheet · project data · design criteria", "Existing deck — as built: project data, scope, responsible charge, construction types, criteria, codes, index",
                    o, "No scale", meta)


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
    if _asb(ext):
        return _hook_s101_facts(body)
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


def _notes_col(o, x, y, blocks, wrap=44, fs=7.0, lh=9.2, y_max=600.0, accent=None) -> float:
    """A notes column: [(heading or "", [item, ...])], each item wrapped and bulleted; shrinks to fit y_max. Returns the y under it."""
    accent = accent or _CTX["brand"]["accent_b"]
    for k in (1.0, 0.94, 0.88, 0.82, 0.76):
        n = sum((1.6 if h else 0) + sum(len(textwrap.wrap(it, int(wrap / k))) + 0.35 for it in its) for h, its in blocks)
        if y + n * lh * k <= y_max:
            break
    f_, l_, w_ = fs * k, lh * k, int(wrap / k)
    for h, its in blocks:
        if h:
            o.append(T(x, y, h, f_ + 1.6, 800, fill=accent)); y += l_ * 1.6
        for it in its:
            for j, ln in enumerate(textwrap.wrap(it, w_)):
                if j == 0:
                    o.append(T(x, y, "·", f_ + 1, 900))
                o.append(T(x + 7, y, ln, f_, 400)); y += l_
            y += l_ * 0.35
    return y


def _hook_s101_facts(body: List[str]) -> List[str]:
    """S-101 for an existing deck: the engine's plan with its own words replaced by the record — one house label, the beam rows named
    with their (V) positions, the blocking rows once each, H2.5A along B2, the DTT2Z seen at its position (V) and the R507.9.2 end
    positions marked (V), the knee braces where they are, the fascia posts with the blocking behind them (not visible, V), a legend
    and the framing notes as built."""
    L, S, t, ext, br = _CTX["L"], _CTX["S"], _CTX["t"], _CTX["ext"], _CTX["brand"]
    s = L.spec
    f = lambda k, d="": _fx(k, d, ext)
    X, Y, sc = _plan_xf(S)
    jb = CAT.actual(s.framing.joist_size)[0]
    drop = lambda x: (x.startswith('<text x="760.0"') or (x.startswith("<text") and (">HOUSE — " in x or " field + " in x or (">DROP " in x and 'fill="#3f5d8a"' in x))))
    body = [x for x in body if not drop(x)]
    o: List[str] = []
    rows = beam_rows(L)
    yh0, yh1 = Y(-2.0), Y(0.0)
    o.append(TH((X(0) + X(S.W)) / 2, (yh0 + yh1) / 2 + 2.5, "EXISTING HOUSE — main-floor band, cantilevered ~2'-9\" (V)", 6.6, 800, "middle", fill=MUTE, halo=DW.FILL["house"]))
    # the beam rows and the blocking rows, once each
    lab_b = {"inner": f"B1 · 6x12 drop beam ~{rows['inner'].y:.0f}\" from the house (V) · header for the house-side joists + blocking row on it" if rows else "",
             "outer": f"B2 · 6x12 drop beam ~{rows['outer'].y:.0f}\" from the house (V) · joists bear on it, H2.5A each · blocking row" if rows else ""}
    for k, bl in rows.items():
        o.append(TH(X(bl.x0 * IN) + 6, Y(bl.y * IN) - 6, lab_b[k], 6.6, 800, fill=BLUE))
    zs = sorted({round(z.wall_y + r, 1) for z in L.zones for r in z.frame.blocking_rows_y})
    for r in zs:
        if not any(abs(r - bl.y) < 3 for bl in rows.values()):
            o.append(TH(X(0) + 6, Y(r * IN) - 3, "SOLID BLOCKING ROW · mid-span of the house-side bay (as seen)", 6.2, 800, fill=BLUE))
    # H2.5A at each joist on the outer beam
    n_h = 0
    if rows:
        yo = rows["outer"].y
        for z in L.zones:
            if not any(abs(z.wall_y + b.cl_y - yo) < 0.5 for b in z.frame.beams if b.kind == "drop"):
                continue
            fr = z.frame
            for x in [z.x0 + q for q in fr.joist_x + fr.pf_x] + [z.x0 + fr.rim_plies * jb / 2, z.x0 + z.W - fr.rim_plies * jb / 2]:
                xx, yy = X(x * IN), Y(yo * IN)
                o.append(PGN([(xx - 2.4, yy + 2.0), (xx + 2.4, yy + 2.0), (xx, yy - 2.4)], "#b3261e", "#ffffff", 0.3)); n_h += 1
    # the knee braces as built, in the beam planes
    lg = s.framing.knee_leg_in * IN
    for key, lay in (ext.knee_brace_layout or {}).items():
        bl = rows.get(key)
        if bl is None:
            continue
        xs = sorted(bl.posts_x)
        mid = (bl.x0 + bl.x1) / 2
        for kind_, idx in (("single", lay.get("single") or []), ("y", lay.get("y") or [])):
            for i in idx:
                if 0 <= i < len(xs):
                    for sx in ([1 if xs[i] < mid else -1] if kind_ == "single" else [1, -1]):
                        x0_ = xs[i] * IN + sx * 0.3
                        o.append(LN(X(x0_), Y(bl.y * IN) + 3.2, X(x0_ + sx * lg), Y(bl.y * IN) + 3.2, FILL_DK, 2.2))
    # the lateral ties: the one seen, and the code's end positions (V)
    seen = getattr(L, "_mx_tie_seen", []) or []
    for x, yw in seen:
        xx, yy = X(x * IN), Y(yw * IN)
        o.append(R(xx - 3, yy - 1, 6, 7, INK, "#ffffff", 0.4))
        o.append(TH(xx + 4, yy + 13, "DTT2Z seen (V)", 6.0, 800, "start", fill=INK))
    ends_ = getattr(L, "_mx_ties", []) or []
    mid_ = (min(q[0] for q in ends_) + max(q[0] for q in ends_)) / 2 if ends_ else 0.0
    for x, yw in ends_:
        xx, yy = X(x * IN), Y(yw * IN)
        o.append(R(xx - 3, yy - 1, 6, 7, "#ffffff", "#b3261e", 0.8, 'stroke-dasharray="1.6 1"'))
        left = x < mid_
        o.append(TH(xx - 3 if left else xx + 3, yy + 13, "(V) — R507.9.2: within 24\" of each end", 6.0, 800, "start" if left else "end", fill="#b3261e"))
    # the fascia posts, the blocking behind them (not visible: dashed)
    if ext.fascia and L.rail:
        out = fascia_offset_in(s)
        for p in L.rail.posts:
            xx, yy = X(p.x * IN), Y(p.y * IN)
            o.append(R(xx - 2.4, yy - 2.4, 4.8, 4.8, "#ffffff", INK, 0.7))
            for e in [e for e in (L.outline_edges or L.edges) if e.exposed and e.length > 1]:
                Le = e.length; ux, uy = (e.x1 - e.x0) / Le, (e.y1 - e.y0) / Le
                nx, ny = -uy, ux
                d_ = (p.x - e.x0) * nx + (p.y - e.y0) * ny
                tt = (p.x - e.x0) * ux + (p.y - e.y0) * uy
                if abs(d_ - out) > 1.0 or not (-out - 1 <= tt <= Le + out + 1):
                    continue
                tt = min(max(tt, 6.0), Le - 6.0)
                rim_in = L.frame.rim_plies * jb
                cx, cy = e.x0 + ux * tt - nx * (rim_in + 1.5), e.y0 + uy * tt - ny * (rim_in + 1.5)
                hb = (L.frame.spacing - jb) / 2
                pts = [(cx - ux * hb - nx * 1.5, cy - uy * hb - ny * 1.5), (cx + ux * hb - nx * 1.5, cy + uy * hb - ny * 1.5),
                       (cx + ux * hb + nx * 1.5, cy + uy * hb + ny * 1.5), (cx - ux * hb + nx * 1.5, cy - uy * hb + ny * 1.5)]
                o.append(f'<polygon points="{" ".join(f"{X(a * IN):.1f},{Y(b_ * IN):.1f}" for a, b_ in pts)}" fill="none" stroke="{br["accent_b"]}" stroke-width="0.7" stroke-dasharray="1.5 1"/>')
    # the legend, under the plan
    items = [("tri", f"Simpson H2.5A at each joist on B2 ({n_h} bearings) — ~10 seen; count (V) (D-505 / 3)")] if n_h else []
    if seen:
        items.append(("sq", "Simpson DTT2Z seen at the ledger (IMG_5677) — 1 confirmed, ~30-35 ft from the north end (V) (D-505 / 4)"))
    if getattr(L, "_mx_ties", None):
        items.append(("sqv", "CRC R507.9.2: 2 devices x 1,500 lb within 24\" of each end of the deck — devices at these positions (V)"))
    items.append(("line", "Solid blocking rows: over both beams + mid-span of the house-side bay (as seen)"))
    if ext.fascia and L.rail:
        items.append(("post", f"Fascia-mounted guard post ({len(L.rail.posts)} drawn at the system's 72.43\" max.; ~5-6' o.c. as seen (V)); blocking behind not visible (V)"))
    if ext.knee_brace_layout:
        items.append(("brace", "6x6 knee brace in the beam plane: B2 singles at both end posts + Y-braces at posts 2, 4, 6; B1 one at the south end post (D-505 / 5)"))
    wl, hl = 600, 16 + 12 * len(items)
    yb = _view_blocks(o, ["FRAMING PLAN"], [44])
    lx, ly = 44, (yb[0] + 14) if yb else Y(S.y_front) + 46
    o.append(R(lx, ly, wl, hl, "#ffffff", INK, 0.6))
    o.append(T(lx + 8, ly + 11, "HARDWARE, BLOCKING AND BRACES (AS BUILT)", 7.2, 800, fill=br["accent_b"]))
    for k, (sym, txt) in enumerate(items):
        yy = ly + 24 + 12 * k
        if sym == "tri":
            o.append(PGN([(lx + 10, yy), (lx + 16, yy), (lx + 13, yy - 5.5)], "#b3261e", "none", 0))
        elif sym == "sq":
            o.append(R(lx + 10, yy - 6, 6, 7, INK, "none", 0))
        elif sym == "sqv":
            o.append(R(lx + 10, yy - 6, 6, 7, "#ffffff", "#b3261e", 0.8, 'stroke-dasharray="1.6 1"'))
        elif sym == "line":
            o.append(R(lx + 8, yy - 4, 10, 3, BLUE, "none", 0))
        elif sym == "post":
            o.append(R(lx + 10, yy - 6, 6, 6, "#ffffff", INK, 0.8)); o.append(R(lx + 18, yy - 4.5, 7, 3, "none", br["accent_b"], 0.6, 'stroke-dasharray="1.5 1"'))
        else:
            o.append(LN(lx + 8, yy - 2, lx + 20, yy - 2, FILL_DK, 2.2))
        o.append(T(lx + 30, yy, txt, 6.6, 600))
    # the framing notes, as built
    hw = ["Simpson LUS210Z at every joist at the ledger (stamp legible)", f("header"), f("joist_ties"), f("lateral_ties"), f("post_caps"),
          f("stair_connectors"), f("tread_angles"), "Catalog fastening for each: G-002, note 6 (connector schedule)"]
    blocks = [("FRAMING NOTES (AS BUILT)", [x for x in (f("joists"), f("rims"), f("beams"), f("blocking"), f("ledger"), f("ledger_support"), f("ledger_flashing")) if x]),
              ("HARDWARE SEEN", [x for x in hw if x])]
    _notes_col(o, 760, 24, blocks, wrap=46, fs=6.9, lh=9.0, y_max=604)
    return body + o


# ---------------------------------------------------------------------------- A-301: the section's hardware, glass, braces
def _hook_a301(body: List[str]) -> List[str]:
    if _asb():
        return body                                             # the as-built A-301 is drawn whole (sheet_a301_facts)
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


# ---------------------------------------------------------------------------- as-built drawing helpers: bubbles, cut members, ground
def _bubble(o, n, x, y, r=6.5, fill=None):
    br = _CTX["brand"]
    o.append(C(x, y, r, fill or "#ffffff", br["accent_b"], 1.1)); o.append(T(x, y + 2.9, str(n), 7.6, 900, "middle", br["accent_b"]))


def _x_mark(o, x, y, w, h, sw=0.4):
    """The cross drawn through a member the section cuts."""
    o.append(LN(x, y, x + w, y + h, INK, sw)); o.append(LN(x, y + h, x + w, y, INK, sw))


def _segs_cross(a, b, c, d) -> bool:
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def place_bubbles(targets, keep_out, bounds, r=6.5):
    """Numbered bubbles near their targets: targets [(n, tx, ty, angle_deg preferred)], keep_out [(x0, y0, x1, y1)] (members, dims,
    words), bounds (x0, y0, x1, y1). Each bubble takes the first spot, nearest first around its preferred angle, that clears the
    keep-out boxes and the bubbles already placed, and whose leader crosses no other leader. Returns [(n, tx, ty, bx, by)]."""
    placed, leaders = [], []
    for n, tx, ty, pref in targets:
        best = None
        for dist in (24, 32, 42, 54, 68, 84, 102):
            for k in range(0, 24):
                da = (k + 1) // 2 * 15 * (1 if k % 2 else -1)
                a = math.radians(pref + da)
                bx, by = tx + dist * math.cos(a), ty + dist * math.sin(a)
                if not (bounds[0] + r < bx < bounds[2] - r and bounds[1] + r < by < bounds[3] - r):
                    continue
                if any(x0 - r - 1 < bx < x1 + r + 1 and y0 - r - 1 < by < y1 + r + 1 for x0, y0, x1, y1 in keep_out):
                    continue
                if any(math.hypot(bx - q[3], by - q[4]) < 2 * r + 5 for q in placed):
                    continue
                if any(_segs_cross((tx, ty), (bx, by), a_, b_) for a_, b_ in leaders):
                    continue
                best = (bx, by)
                break
            if best:
                break
        if best is None:
            best = (tx + 30, ty - 30)
        placed.append((n, tx, ty, best[0], best[1]))
        leaders.append(((tx, ty), best))
    return placed


def _draw_bubbles(o, placed, r=6.5):
    for n, tx, ty, bx, by in placed:
        L_ = math.hypot(bx - tx, by - ty) or 1.0
        ex, ey = bx - (bx - tx) / L_ * r, by - (by - ty) / L_ * r
        o.append(LN(tx, ty, ex, ey, INK, 0.5)); o.append(C(tx, ty, 1.3, INK, "none", 0))
    for n, tx, ty, bx, by in placed:
        _bubble(o, n, bx, by, r)


def _keyed_notes(o, x, y, notes, w_chars=62, fs=6.9, lh=8.9, y_max=600.0, head="NOTES"):
    """The keyed list beside a drawing: a bubble with each number, the words wrapped beside it; shrinks to fit y_max."""
    br = _CTX["brand"]
    for k in (1.0, 0.95, 0.9, 0.85, 0.8):
        n_ln = sum(len(textwrap.wrap(t_, int(w_chars / k))) + 0.45 for _, t_ in notes)
        if y + 16 + n_ln * lh * k <= y_max:
            break
    o.append(T(x, y, head, 9, 800, fill=br["accent_b"])); y += 16
    for n, txt in notes:
        ls = textwrap.wrap(txt, int(w_chars / k))
        _bubble(o, n, x + 6, y - 2.5 * k, 5.6 * k)
        for j, ln in enumerate(ls):
            o.append(T(x + 16, y + j * lh * k, ln, fs * k, 400))
        y += lh * k * (len(ls) + 0.45)
    return y


def ground_poly(Hx, Z, y_lo, y_hi, z_floor, ext=None):
    """The grade profile as a filled polygon from y_lo to y_hi (ft), down to z_floor; Hx maps y to the sheet."""
    gp = grade_profile(ext)
    if not gp:
        return None
    pts = [(y_lo, gp[0][1])] + [(y_, z_) for y_, z_ in gp if y_lo < y_ < y_hi] + [(y_hi, grade_at(y_hi, ext) if y_hi < gp[-1][0] else gp[-1][1])]
    return [(Hx(y_), Z(z_)) for y_, z_ in pts], [(Hx(y_hi), Z(z_floor)), (Hx(y_lo), Z(z_floor))]


# ---------------------------------------------------------------------------- A-301 as built: the building section
def sheet_a301_facts(L, S, t, meta) -> str:
    """The section through zone A at a post station, looking toward the south end, drawn true: the house's main floor cantilevered
    ~2'-9" past the basement wall (dashed) with its soffit, the ledger on the band, the joists, both beams with the header on B1,
    the posts on piers at two levels, the grade falling away to the retaining wall, the guard; heights to each row's pier tops (V);
    numbered bubbles keyed to the notes at the right."""
    s, ext = L.spec, _ext(L.spec)
    f = lambda k, d="": _fx(k, d, ext)
    code = _code(s)
    rows = beam_rows(L)
    zt = s.geometry.height_in * IN
    bt = CAT.decking_facts(s.decking.collection)["thick"] * IN
    jd = CAT.actual(s.framing.joist_size)[1] * IN
    jtop, jbot = zt - bt, zt - bt - jd
    led_d = CAT.actual(s.framing.ledger_size or "2x12")[1] * IN
    cant = float(f("house_cantilever_in", 0) or 0) * IN
    z_soff = jtop - led_d - 1.0 * IN
    deep = max(L.zones, key=lambda z: z.D)
    stations = sorted({round(px * IN, 3) for bl in rows.values() for px in bl.posts_x if deep.x0 <= px <= deep.x0 + deep.W})
    xm = (deep.x0 + deep.W / 2) * IN
    xc = min(stations, key=lambda q: abs(q - xm)) if stations else xm
    gp = grade_profile(ext)
    y_lo, y_hi = -(cant + 3.6), max(S.y_front + 5.6, (gp[-1][0] if gp else 0) - 0.5)
    z_lo, z_hi = min([q[1] for q in gp] + [-3.0]) - 1.4, zt + 4.9
    Hx, Z, sc = DW.elev_xform(y_lo, y_hi, z_lo, z_hi, 22, 14, 616, 584)
    o: List[str] = []
    keep: List[Tuple[float, float, float, float]] = []
    rect = lambda y0, y1, z0, z1: (Hx(y0), Z(z1), Hx(y1), Z(z0))
    # the ground and the retaining wall
    gpoly = ground_poly(Hx, Z, y_lo, y_hi, z_lo, ext)
    if gpoly:
        top, bot = gpoly
        o.append(PGN(top + bot, "#e6dcc4", "none", 0))
        o.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in top) + f'" fill="none" stroke="{INK}" stroke-width="1.1"/>')
    rw = f("retaining_wall", {}) or {}
    if rw:
        yw_ = float(rw["y_in"]) * IN
        o.append(R(Hx(yw_ - 0.42), Z(float(rw["top_in"]) * IN + 0.15), 0.42 * sc, (float(rw["top_in"]) - float(rw["bottom_in"])) * IN * sc + 0.15 * sc, FILL_DK, INK, 0.6))
        for k_ in range(1, 4):
            zz = float(rw["bottom_in"]) * IN + k_ * (float(rw["top_in"]) - float(rw["bottom_in"])) * IN / 4
            o.append(LN(Hx(yw_ - 0.42), Z(zz), Hx(yw_), Z(zz), INK, 0.4))
    # the house: the main floor and wall above it, cantilevered over the basement wall (dashed, set back)
    hx0 = y_lo
    o.append(R(Hx(hx0), Z(z_hi), (0 - 0.5 - hx0) * sc, (z_hi - (jtop + 0.06)) * sc, DW.FILL["house"], "none", 0))
    o.append(R(Hx(-0.5), Z(z_hi), 0.5 * sc, (z_hi - (jtop + 0.06)) * sc, "#ddd3bf", INK, 0.8))                 # the exterior wall over the floor
    o.append(R(Hx(hx0), Z(jtop + 0.06), (-0.125 - hx0) * sc, (jtop + 0.06 - z_soff) * sc, "#efe7d6", INK, 0.6))  # the floor framing
    for k_ in range(1, 6):                                                                                        # its joists, running out to the band
        o.append(LN(Hx(hx0), Z(z_soff + (jtop + 0.06 - z_soff) * k_ / 6), Hx(-0.125), Z(z_soff + (jtop + 0.06 - z_soff) * k_ / 6), "#b9ad97", 0.4))
    o.append(R(Hx(-0.125), Z(jtop + 0.06), 0.125 * sc, (jtop + 0.06 - z_soff) * sc, FILL_DK, INK, 0.7))        # the band joist
    o.append(LN(Hx(hx0), Z(z_soff), Hx(0.0), Z(z_soff), INK, 1.0))                                              # the soffit
    bw0, bw1 = -cant - 0.67, -cant
    zb_g = grade_at(bw1 + 0.01, ext)
    o.append(R(Hx(bw0), Z(z_soff), (bw1 - bw0) * sc, (z_soff - zb_g) * sc, "#f3eee4", INK, 0.8, 'stroke-dasharray="4 2.5"'))
    o.append(TH(Hx((hx0 + bw0) / 2) + 2, Z(z_soff) + 40, "BASEMENT", 6.4, 800, "middle", fill=MUTE, halo=DW.FILL["house"]))
    o.append(T(Hx((bw0 + bw1) / 2) + 3, Z((z_soff + zb_g) / 2), "basement wall (set back) — dashed", 6.0, 700, "middle", MUTE, rot=-90))
    o.append(TH(Hx((hx0 - 0.5) / 2), Z(z_hi) + 14, "EXISTING HOUSE — MAIN FLOOR", 7.0, 800, "middle", fill=MUTE, halo=DW.FILL["house"]))
    keep += [rect(hx0, 0.0, z_soff, z_hi), rect(bw0, bw1, zb_g, z_soff)]
    if cant > 0:
        DW.dim_h(o, Hx, Z(z_soff) + 16, bw1, 0.0, f"~{ftin(cant * 12)} (V)", 6.6, up=False)
        keep.append((Hx(bw1), Z(z_soff) + 10, Hx(0.0), Z(z_soff) + 30))
    # the deck: the members the cut passes through, the posts and piers at the station, the guard at the front
    near = lambda b: abs((b.x0 + b.x1) / 2 - xc) < 0.35
    js_ = [b for b in S.boxes if b.kind == "joist" and b.x1 - b.x0 < 0.3]
    jn = min(js_, key=lambda b: abs((b.x0 + b.x1) / 2 - xc)) if js_ else None
    if jn:
        o.append(R(Hx(jn.y0), Z(jn.z1), (jn.y1 - jn.y0) * sc, (jn.z1 - jn.z0) * sc, DW.FILL["timber"], INK, 0.5))
    for b in sorted([b for b in S.boxes if b.x0 <= xc <= b.x1 and b.kind in ("ledger", "rim", "beam", "block", "board", "border", "fascia", "toprail", "botrail", "glasspanel", "railcap")
                     and not b.rot], key=lambda q: q.z0):
        if b.kind == "rim" and b.y1 - b.y0 > 1.0:
            continue                                                   # a side rim along y: not in this cut
        fill = "#a9c6da" if b.kind == "glasspanel" else DW.fill_for(b)
        if b.kind == "ledger":                                     # the ledger as built: a 2x12, its top at the joists' top
            b = Box("ledger", b.x0, b.x1, b.y0, b.y1, jtop - led_d, jtop, b.mat)
        o.append(R(Hx(b.y0), Z(b.z1), max(0.8, (b.y1 - b.y0) * sc), (b.z1 - b.z0) * sc, fill, INK, 0.4 if b.kind in ("board", "border") else 0.6))
        if b.kind in ("ledger", "beam", "rim", "block"):
            _x_mark(o, Hx(b.y0), Z(b.z1), (b.y1 - b.y0) * sc, (b.z1 - b.z0) * sc)
        if b.kind in ("beam", "ledger", "rim"):
            keep.append(rect(b.y0, b.y1, b.z0, b.z1))
    for b in [b for b in S.boxes if b.kind in ("glasspanel", "botrail", "toprail") and not b.rot and abs((b.y0 + b.y1) / 2 - S.y_front) < 1.0
              and (b.x1 - b.x0) > (b.y1 - b.y0) and b.x0 - 6.5 <= xc <= b.x1 + 6.5]:                         # the guard beyond the cut, its glass edge-on
        o.append(R(Hx(b.y0), Z(b.z1), max(1.6, (b.y1 - b.y0) * sc), (b.z1 - b.z0) * sc, "#a9c6da" if b.kind == "glasspanel" else DW.FILL["railmetal"],
                   _CTX["brand"]["accent_b"] if b.kind == "glasspanel" else INK, 0.4))
    for b in [b for b in S.boxes if b.kind in ("railpost", "railbracket") and abs((b.y0 + b.y1) / 2 - S.y_front) < 1.0 and abs((b.x0 + b.x1) / 2 - xc) < 3.5]:
        o.append(R(Hx(b.y0), Z(b.z1), (b.y1 - b.y0) * sc, (b.z1 - b.z0) * sc, DW.FILL["railmetal"], INK, 0.4))
        keep.append(rect(b.y0, b.y1, b.z0, b.z1))
    for b in [b for b in S.boxes if b.kind == "glasspanel" and not b.rot and abs((b.y0 + b.y1) / 2 - S.y_front) < 1.0 and (b.x1 - b.x0) > (b.y1 - b.y0)
              and b.x0 - 6.5 <= xc <= b.x1 + 6.5][:1]:                                                          # the glass seen past the post
        o.append(R(Hx(b.y0) - 1.0, Z(b.z1), 3.2, (b.z1 - b.z0) * sc, "#a9c6da", _CTX["brand"]["accent_b"], 0.5, 'fill-opacity="0.85"'))
    if rows:                                                     # B1's header: the house-side joists hang from it (IMG_5676)
        yi_ = rows["inner"].y * IN
        hw_ = 3.0 * IN
        o.append(R(Hx(yi_ - hw_ / 2), Z(jtop), hw_ * sc, (jtop - jbot) * sc, FILL_DK, INK, 0.7))
        _x_mark(o, Hx(yi_ - hw_ / 2), Z(jtop), hw_ * sc, (jtop - jbot) * sc)
    piers = []
    for b in sorted([b for b in S.boxes if b.kind in ("footing", "base", "post", "cap") and near(b)], key=lambda q: q.z0):
        yc = (b.y0 + b.y1) / 2
        if b.kind == "footing":
            g = grade_at(yc, ext)
            o.append(R(Hx(b.y0), Z(b.z1), (b.y1 - b.y0) * sc, (b.z1 - g) * sc, DW.FILL["concrete"], INK, 0.7))
            d36 = 3.0
            o.append(R(Hx(b.y0), Z(g), (b.y1 - b.y0) * sc, (d36 - 1.0) * sc, "none", INK, 0.5, 'stroke-dasharray="3 2"'))
            o.append(R(Hx(yc - 0.625), Z(g - d36 + 1.0), 1.25 * sc, 1.0 * sc, "none", INK, 0.5, 'stroke-dasharray="3 2"'))
            piers.append((yc, b.z1, g))
            keep.append(rect(b.y0, b.y1, g - d36, b.z1))
        else:
            o.append(R(Hx(b.y0), Z(b.z1), (b.y1 - b.y0) * sc, (b.z1 - b.z0) * sc, DW.FILL["steel"] if b.kind in ("base", "cap") else DW.FILL["timber"], INK, 0.6))
            keep.append(rect(b.y0, b.y1, b.z0, b.z1))
    # the guard at the front: post, glass, rails (cut)
    keep.append(rect(-0.2, S.y_front + 0.4, jbot - 0.1, zt + 0.05))
    # dimensions: the bays across the top, the heights to each row's pier tops (V), the guard
    yd = Z(zt + 3.95)
    marks = [(0.0, "house")] + [(bl.y * IN, k) for k, bl in rows.items()] + [(S.y_front, "front")]
    for (ya, _), (yb, kb) in zip(marks, marks[1:]):
        lab = f"{ftin((yb - ya) * 12)}" + (" (V)" if kb != "front" else " cantilever (V)")
        DW.dim_h(o, Hx, yd, ya, yb, lab, 6.6)
    for ya, _ in marks:
        o.append(LN(Hx(ya), yd + 3, Hx(ya), Z(zt) - 2, "#9a948b", 0.35, "2 2"))
    keep.append((Hx(0) - 2, yd - 12, Hx(S.y_front) + 2, yd + 5))
    for (yc, ztop, g), (dx, side) in zip(sorted(piers), ((-0.95, True), (0.95, False))):
        xx = Hx(yc + dx)
        o.append(LN(xx, Z(ztop), xx, Z(zt), INK, 0.8)); o.append(LN(xx - 4, Z(ztop), xx + 4, Z(ztop), INK, 0.8)); o.append(LN(xx - 4, Z(zt), xx + 4, Z(zt), INK, 0.8))
        o.append(LN(Hx(yc), Z(ztop), xx, Z(ztop), "#9a948b", 0.35, "2 2"))
        o.append(T(xx - 4 if side else xx + 11, (Z(ztop) + Z(zt)) / 2, f"~{ftin((zt - ztop) * 12)} to the pier top (V)", 6.8, 800, "middle", INK, rot=-90))
        keep.append((xx - 13, Z(zt), xx + 13, Z(ztop)))
    if L.rail:
        xg = Hx(S.y_front + 1.15)
        o.append(LN(xg, Z(zt), xg, Z(zt + L.rail.height * IN), INK, 0.8))
        for zz in (zt, zt + L.rail.height * IN):
            o.append(LN(xg - 4, Z(zz), xg + 4, Z(zz), INK, 0.8))
        o.append(T(xg + 11, Z(zt + L.rail.height * IN / 2), f"{L.rail.height:g}\" guard", 6.8, 800, "middle", INK, rot=-90))
        keep.append((xg - 6, Z(zt + L.rail.height * IN), xg + 14, Z(zt)))
    vv = (_CTX.get("views") or [{}])[-1]
    if vv:
        vv["kind"] = "section"
    yb = min(Z(z_lo) + 8, 574)
    scale_block(o, Hx(y_lo) + 4, yb, f"SECTION at the post station {ftin(xc * 12)} from the south end (zone {deep.name}) — looking south", sc, vv.get("lab", ""))
    keep.append((Hx(y_lo), yb - 10, Hx(y_lo) + 470, yb + 30))
    # the numbered callouts
    yi, yo_ = (rows["inner"].y * IN, rows["outer"].y * IN) if rows else (7.0, 14.0)
    ymid = (yi + 0.0) / 2
    p_in = next((p for p in piers if abs(p[0] - yi) < 0.5), None)
    p_out = next((p for p in piers if abs(p[0] - yo_) < 0.5), None)
    yf = S.y_front + fascia_offset_in(s) * IN if ext.fascia else S.y_front
    g_mid = grade_at((yi + yo_) / 2, ext)
    T_ = [  # (n, point (y, z) ft, preferred angle, words)
        (1, (0.07, (jbot + jtop) / 2), 60, "Ledger — " + f("ledger")),
        (2, (-0.06, jtop + 0.25), 225, f("ledger_flashing")),
        (3, (-cant / 2, z_soff), 120, f("house") + ". " + f("ledger_support")),
        (4, (0.5, jbot + 0.12), 70, f("lateral_ties") + f" (S-101; D-505 / 4)"),
        (5, (ymid + 1.2, (jbot + jtop) / 2), 90, "Joists — " + f("joists")),
        (6, (ymid, jtop - 0.1), 110, f("blocking")),
        (7, (yi + 0.15, jbot - 0.45), 60, f"6x12 drop beam B1, ~{rows['inner'].y:.0f}\" from the house (V). " + f("header") if rows else f("header")),
        (8, (yo_ - 0.1, jbot - 0.45), 120, (f"6x12 drop beam B2, ~{rows['outer'].y:.0f}\" from the house (V): the joists bear on top. " if rows else "") + f("joist_ties")),
        (9, (yi + 0.25, jbot - 1.05), 20, f("post_caps")),
        (10, (yi + 0.2, (p_in[1] if p_in else 0) + 4.0), 0, f("posts") + "; " + f("post_base")),
        (11, (yo_ - 0.25, jbot - 2.0), 160, f("knee_braces") + ". " + f("knee_brace_ends") + " (A-202, S-101, D-505 / 5)"),
        (12, (yi + 0.1, (p_in[1] - 0.25) if p_in else -0.3), 210, f("footings")),
        (13, (yf, jbot + 0.2), 20, f("guard") + ". " + f("guard_bracket") + ". " + f("guard_blocking")),
        (14, (yf - 0.1, zt + 2.2), 0, (ext.glass_note.split(";")[0] if ext.glass_note else "Glass infill") + "; " + ";".join(ext.glass_note.split(";")[1:3]) if ext.glass_note else ""),
        (15, ((yi + yo_) / 2, zt - 0.02), 270, f"Decking — {f('decking')}; picture frame and breakers {f('border')}; {f('deck_fasteners')}; {f('fascia')}"),
        (16, ((yi + yo_) / 2, g_mid), 70, f("grade")),
    ]
    if rw:
        T_.append((17, (float(rw["y_in"]) * IN - 0.2, (float(rw["top_in"]) + float(rw["bottom_in"])) / 2 * IN), 330, rw.get("words", "")))
    T_ = [q for q in T_ if q[3]]
    targets = [(n, Hx(y_), Z(z_), ang) for n, (y_, z_), ang, _ in T_]
    placed = place_bubbles(targets, keep, (Hx(y_lo) + 2, 12, Hx(y_hi) - 2, Z(z_lo) - 18))
    _draw_bubbles(o, placed)
    # the keyed notes
    _keyed_notes(o, 652, 22, [(n, w) for n, _, _, w in T_], w_chars=70, fs=6.9, lh=8.8, y_max=604, head="SECTION — AS BUILT")
    return mx_sheet("A-301", "Building section — as built", "Through zone A at a post station: the house's cantilevered main floor, the ledger, both beams, posts on piers at two levels, the grade",
                    o, "Section · not to scale · heights to the pier tops (V) · read with S-100, S-101, A-202 and the details", meta)


# ---------------------------------------------------------------------------- A-202 as built: the elevations
def _snapped_draw(bx, cols, view, frame, fit):
    """axo.draw at the largest standard scale (24x36) that fits the frame, centred in it: (polys, to_sheet, units/ft, label)."""
    from decktakeoff.axo import draw
    polys, to_sheet, sc = draw(bx, cols, view, frame, fit_boxes=fit)
    u, lab = snap_scale(sc)
    if u is None or sc <= 0:
        return polys, to_sheet, sc, ""
    k = u / sc
    fx_, fy_, fw_, fh_ = frame
    fr2 = (fx_ + fw_ / 2 - fw_ * k / 2, fy_ + fh_ / 2 - fh_ * k / 2, fw_ * k, fh_ * k)
    polys, to_sheet, sc2 = draw(bx, cols, view, fr2, fit_boxes=fit)
    return polys, to_sheet, sc2, lab


def sheet_a202_facts(L, S, t, meta) -> str:
    """Front and both end elevations of the deck as built, true orthographic projections of the model at standard scales: the piers at
    their two levels shown down to their own grade, the grade drawn across each view (the end views show it falling away from the
    house to the retaining wall), the heights to each row's pier tops (V)."""
    from decktakeoff.axo import View
    import dataclasses as _dc
    s, ext = L.spec, _ext(L.spec)
    f = lambda k, d="": _fx(k, d, ext)
    cols = DW._axo_colors(S)
    rows = beam_rows(L)
    zt = S.deck_top
    gp = grade_profile(ext)
    rw = f("retaining_wall", {}) or {}
    bx = []
    for b in S.boxes:
        if b.kind in ("ground", "glass", "gravel"):
            continue
        if b.kind == "footing":                                    # a pier shows down to its own grade: the ground in front hides the rest
            g = grade_at((b.y0 + b.y1) / 2, ext)
            if b.z1 <= g + 0.01:
                continue
            b = _dc.replace(b, z0=max(b.z0, g))
        bx.append(b)
    fit = [b for b in bx if not DW._house(b)]
    o: List[str] = []
    ylo = min([q[0] for q in gp] + [-2.0]) if gp else -2.0
    yhi = max([q[0] for q in gp] + [S.y_front + 2]) if gp else S.y_front + 2
    zlo = min([q[1] for q in gp] + [0.0]) if gp else 0.0
    x0_ = min(b.x0 for b in fit)
    views = [("FRONT ELEVATION — from the yard (east)", 0.0, (20, 6, 960, 280)), ("RIGHT END ELEVATION — from the north", 90.0, (20, 300, 470, 248)),
             ("LEFT END ELEVATION — from the south", -90.0, (510, 300, 470, 248))]
    for ttl, az, fr in views:
        fitv = list(fit)
        if az != 0 and gp:
            fitv.append(Box("fit", x0_, x0_ + 0.01, max(ylo, -2.5), min(yhi, S.y_front + 5.5), max(zlo, -3.2), max(zlo, -3.2) + 0.01, "concrete"))
        else:
            fitv.append(Box("fit", x0_, x0_ + 0.01, S.y_front, S.y_front + 0.01, -0.6, -0.59, "concrete"))
        polys, to_sheet, u, lab = _snapped_draw(bx, cols, View(az, 0.0), (fr[0], fr[1] + 16, fr[2], fr[3] - 30), fitv)
        cid = f"a202{int(az + 180)}"
        o.append(f'<defs><clipPath id="{cid}"><rect x="{fr[0]}" y="{fr[1] + 14}" width="{fr[2]}" height="{fr[3] - 18}"/></clipPath></defs>')
        g_el = []
        if az == 0:                                                # from the yard the ground rises away: the farthest (at the house) shows behind all
            gh_ = max(q[1] for q in gp) if gp else 0.0
            yh_ = to_sheet((0, 0, gh_))[1]
            g_el.append(R(fr[0], yh_, fr[2], fr[1] + fr[3] + 40 - yh_, "#e6dcc4", "none", 0))
            g_el.append(LN(fr[0], yh_, fr[0] + fr[2], yh_, "#7a6a48", 0.7))
            gy = to_sheet((0, S.y_front, 0.0))[1]
            g_el.append(LN(fr[0], gy, fr[0] + fr[2], gy, INK, 1.1))
            if rows:
                gi = grade_at(rows["inner"].y * IN, ext)
                yy = to_sheet((0, 0, gi))[1]
                g_el.append(LN(fr[0], yy, fr[0] + fr[2], yy, "#7a6a48", 0.7, "5 3"))
        elif gp:                                                   # the profile across the deck, seen from the end
            pts = [to_sheet((0, y_, z_)) for y_, z_ in gp]
            xs_ = [q[0] for q in pts]
            left, right = min(xs_), max(xs_)
            poly = pts + [(pts[-1][0], fr[1] + fr[3] + 40), (pts[0][0], fr[1] + fr[3] + 40)]
            g_el.append(PGN(poly, "#e6dcc4", "none", 0))
            g_el.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + f'" fill="none" stroke="{INK}" stroke-width="1.1"/>')
            if rw:
                a_ = to_sheet((0, float(rw["y_in"]) * IN, float(rw["top_in"]) * IN + 0.15))
                b_ = to_sheet((0, float(rw["y_in"]) * IN - 0.42 * (1 if az > 0 else -1), float(rw["bottom_in"]) * IN))
                g_el.append(R(min(a_[0], b_[0]), a_[1], abs(b_[0] - a_[0]), b_[1] - a_[1], FILL_DK, INK, 0.6))
        o.append(f'<g clip-path="url(#{cid})">' + "".join(g_el) + "".join(polys) + "</g>")
        scale_block(o, fr[0], fr[1] + 2, ttl, u, lab)
        _note_view("elevation", fr[0], fr[1], fr[2], fr[3], u, lab)
        if az == 0:
            gy = to_sheet((0, S.y_front, 0.0))[1]
            o.append(TH(fr[0] + fr[2] - 4, gy + 10, "GRADE AT THE OUTER ROW B2 (V)", 6.4, 800, "end", fill=MUTE, halo="#e6dcc4"))
            if rows:
                yy = to_sheet((0, 0, grade_at(rows["inner"].y * IN, ext)))[1]
                o.append(TH(fr[0] + fr[2] - 4, yy - 3, "grade at the inner row B1, behind (V)", 6.2, 700, "end", fill="#7a6a48"))
                o.append(TH(fr[0] + fr[2] - 4, to_sheet((0, 0, max(q[1] for q in gp)))[1] - 3, "grade at the house, behind (V)", 6.2, 700, "end", fill="#7a6a48"))
                xd = to_sheet((x0_ - 1.6, S.y_front, 0))[0]
                for k_, (row, lab_) in enumerate((("outer", "B2"), ("inner", "B1"))):
                    zp = pier_top_ft(row, ext)
                    xx = xd - 26 * k_
                    ya_, yb_ = to_sheet((0, 0, zp))[1], to_sheet((0, 0, zt))[1]
                    o.append(LN(xx, ya_, xx, yb_, INK, 0.8)); o.append(LN(xx - 4, ya_, xx + 4, ya_, INK, 0.8)); o.append(LN(xx - 4, yb_, xx + 4, yb_, INK, 0.8))
                    o.append(T(xx - 4, (ya_ + yb_) / 2, f"~{ftin((zt - zp) * 12)} to the {lab_} pier tops (V)", 6.4, 800, "middle", rot=-90))
        elif az < 0 and rows:                                      # the heights to each row's pier tops, stacked outboard of B2 (clear of the stair)
            xo_ = to_sheet((0, rows["outer"].y * IN, 0))[0]
            for k_, (row, lab_) in enumerate((("outer", "B2"), ("inner", "B1"))):
                yr = rows[row].y * IN
                zp = pier_top_ft(row, ext)
                xa = xo_ + 16 + 20 * k_
                ya_, yb_ = to_sheet((0, yr, zp))[1], to_sheet((0, yr, zt))[1]
                o.append(LN(xa, ya_, xa, yb_, INK, 0.8)); o.append(LN(xa - 4, ya_, xa + 4, ya_, INK, 0.8)); o.append(LN(xa - 4, yb_, xa + 4, yb_, INK, 0.8))
                if row == "inner":
                    o.append(LN(to_sheet((0, yr, zp))[0] + 4, ya_, xa, ya_, "#9a948b", 0.35, "2 2"))
                o.append(TH(xa + 10, (ya_ + yb_) / 2, f"~{ftin((zt - zp) * 12)} to the {lab_} pier tops (V)", 6.2, 800, "middle", rot=-90))
            if rw:
                q = to_sheet((0, float(rw["y_in"]) * IN, float(rw["bottom_in"]) * IN))
                o.append(TH(q[0] + 4, min(q[1] + 10, fr[1] + fr[3] - 6), "retaining wall (V)", 6.2, 700, fill=MUTE, halo="#e6dcc4"))
            hx = to_sheet((0, -0.5, zt + 3.0))
            o.append(TH(hx[0] - 4, hx[1], "HOUSE", 6.6, 800, "end", fill=MUTE))
    notes = [f("height"), f("grade") + "; " + (rw.get("words", "") if rw else ""), f("house") + " — the house is shown for context only; its openings are not recorded",
             "Deck frame: 2x10 PT DF @ 16\" o.c. on two 6x12 drop beams B1 / B2 (V), 14 6x6 posts (S-100 / S-101); 6x6 knee braces in the beam planes as built (S-101, A-301)",
             f"Guard {s.railing.height_in:g}\" ({_code(s)} R321.1.2): the surface is more than 30\" above grade; stair guard ~38\" (V) (A-201, D-505)"]
    o.append(T(20, 556, "NOTES", 8.4, 800, fill=_CTX["brand"]["accent_b"]))
    yy = 566
    for n_ in [n for n in notes if n]:
        for ln in textwrap.wrap("· " + n_, 230)[:2]:
            o.append(T(20, yy, ln, 6.6, 500)); yy += 8.0
    return mx_sheet("A-202", "Elevations — as built", "Front from the yard and both ends: true orthographic projections of the model, the grade, heights to the pier tops",
                    o, "Elevations · heights to the pier tops (V)", meta)


# ---------------------------------------------------------------------------- A-201: the glass in the elevation, the guard words
def _hook_a201(body: List[str]) -> List[str]:
    L, S, ext, t = _CTX["L"], _CTX["S"], _CTX["ext"], _CTX["t"]
    if not (ext.glass or ext.fascia or ext.vertical or ext.as_built):
        return body
    s, code, rl = L.spec, _code(L.spec), L.rail
    body = [x for x in body if not (x.startswith('<text x="760.0"') and ">RAILING<" not in x)]
    notes = [t.summary.get("rail", "")]
    if _asb(ext):
        f = lambda k: _fx(k, "", ext)
        side_ = lambda v: re.sub(r"^edge:(\d+)$", r"side \1", v)
        notes = [f("guard"), f("guard_bracket"), f("guard_blocking"),
                 ("Posts drawn at the system's maximum spacing (72.43\" o.c.); as built they stand ~5-6' o.c. (V). Bays drawn: " + " · ".join(f"{side_(s_.side)} {ftin(s_.ctc)}" for s_ in rl.sections[:10])) if rl else "",
                 ext.glass_note, f"Guard {s.railing.height_in:g}\" over the deck ({code} R321.1.2: 42\" min.); openings reject a 4\" sphere (R321.1.3); 200 lb at the top in any direction, 50 lb on 1 SF of infill (Table R301.5)",
                 f("stair_guard") + " (D-505 / 6)", f("handrail")]
        body = _house_label(body, (40, 24, 700, 300))
        body = _rp_labels(body)
        o_ = []
        _view_blocks(o_, ["RAILING PLAN", "OUTER-EDGE ELEVATION — the guard"], [30, 44])
        _notes_col(o_, 760, 40, [("", [n for n in notes if n])], wrap=44, fs=7.2, lh=9.6, y_max=600)
        body += o_
        notes = []
    if rl and notes:
        side_ = lambda v: re.sub(r"^edge:(\d+)$", r"side \1", v)
        notes.append("Bays: " + " · ".join(f"{side_(s_.side)} {ftin(s_.ctc)}" for s_ in rl.sections[:14]))
    if ext.fascia and notes:
        fm = fascia_mount(s)
        notes.append(f"Posts fascia-mounted outside the rim on the {fm['bracket']}, {fm['standoff_in']:g}\" off the fascia, the foot at the rim's bottom edge; "
                     f"{fm['post_screws']}; {fm['rim_fastening']}; solid 2x blocking behind every post (D-505 / 1-2)")
    if ext.glass and notes:
        notes.append(ext.glass_note or f"Infill: tempered safety-glass panels in a top rail and a bottom-rail channel. Glazing in a guard is a hazardous location: "
                                       f"safety glazing, each lite permanently labeled ({code} R308.4.4, R308.1)")
    if notes:
        notes.append(f"Guard {s.railing.height_in:g}\" over the deck" + (f" ({code} R312.1.2: 42\" min.)" if _ca(s) else f" ({code} R312.1.2)") + f"; openings reject a 4\" sphere (R312.1.3); "
                     f"200 lb at the top in any direction, 50 lb on 1 SF of infill (Table R301.5)")
    if ext.vertical and notes:
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
    if not ext.fascia or _asb(ext):
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


# ---------------------------------------------------------------------------- D-501 as built: six schematic details of what was seen
def _lab_r(o, ax, ay, tx, ty, txt, chars, size=6.2, w=600, color=INK, right=False):
    """_lab, right-aligned when the words sit left of their point."""
    if not right:
        return _lab(o, ax, ay, tx, ty, txt, chars, size, w, color)
    ls = textwrap.wrap(txt, max(12, chars))
    o.append(LN(ax, ay, tx + 1.5, ty - 2.5, INK, 0.45)); o.append(C(ax, ay, 1.3, INK, "none", 0))
    for j, ln in enumerate(ls):
        o.append(TH(tx, ty + j * (size + 1.7), ln, size=size, w=w, anchor="end", fill=color, halo="#ffffff"))
    return ty + len(ls) * (size + 1.7)


def _dashed(o, x, y, w, h, stroke=INK, sw=0.6, fill="none"):
    o.append(R(x, y, w, h, fill, stroke, sw, 'stroke-dasharray="3 2"'))


def sheet_d501_facts(L, S, t, meta) -> str:
    s, ext = L.spec, _ext(L.spec)
    f = lambda k, d="": _fx(k, d, ext)
    W3, H2, P = DW._grid6()
    o: List[str] = []
    red = "#b3261e"
    # 1 the ledger on the cantilevered main-floor band
    x, y = P[0]; DW._panel(o, x, y, W3, H2, "1", "LEDGER ON THE CANTILEVERED MAIN-FLOOR BAND")
    k = 3.3
    bx_ = x + 168                                   # the band's outer face
    fy0 = y + 74                                    # the house floor framing's top
    fd = 11.25 * k
    o.append(R(x + 8, y + 20, bx_ - x - 8 - 30, fy0 - 3 - y - 20, DW.FILL["house"], "none", 0))
    o.append(R(bx_ - 30, y + 20, 30, fy0 - 3 - y - 20, "#ddd3bf", INK, 0.7))                       # the wall over the floor
    o.append(R(x + 8, fy0 - 3, bx_ - x - 8, 3, "#e4dccb", INK, 0.5))                                # the subfloor
    o.append(R(x + 8, fy0, bx_ - 5 - x - 8, fd, "#efe7d6", INK, 0.5))                              # the floor joists, out to the band
    DW._wood(o, bx_ - 5, fy0, 5, fd, dark=True)                                                     # the band
    o.append(LN(x + 8, fy0 + fd + 1.5, bx_, fy0 + fd + 1.5, INK, 1.0))                              # the soffit
    wall_x = bx_ - 33 * k
    _dashed(o, wall_x - 8 * k, fy0 + fd + 1.5, 8 * k, y + 250 - (fy0 + fd + 1.5), fill="#f3eee4")  # the basement wall, set back
    o.append(LN(x + 8, y + 250, x + W3 - 8, y + 250, INK, 0.8)); o.append(T(x + W3 - 10, y + 247, "grade", 6.0, 600, "end", MUTE))
    ly0 = fy0 + 3
    DW._wood(o, bx_, ly0, 1.5 * k, 11.25 * k)                                                       # the ledger
    jd_ = 9.25 * k
    DW._wood(o, bx_ + 1.5 * k + 1, ly0, x + W3 - 8 - (bx_ + 1.5 * k + 1), jd_)                    # the deck joist
    o.append(f'<polyline points="{bx_ + 1.5 * k + 1:.1f},{ly0 + 4:.1f} {bx_ + 1.5 * k + 1:.1f},{ly0 + jd_ + 1.5:.1f} {bx_ + 1.5 * k + 13:.1f},{ly0 + jd_ + 1.5:.1f} {bx_ + 1.5 * k + 13:.1f},{ly0 + 4:.1f}" fill="none" stroke="#5b6166" stroke-width="1.6"/>')
    o.append(R(bx_ + 1.5 * k + 1, ly0 - 3.3, x + W3 - 8 - (bx_ + 1.5 * k + 1), 3.3, DW.FILL["deck"], INK, 0.4))
    yb_ = ly0 + 11.25 * k * 0.55
    o.append(LN(bx_ - 30, yb_, bx_ + 1.5 * k + 3, yb_, INK, 1.4))                                    # a bolt or lag through the ledger
    o.append(R(bx_ + 1.5 * k, yb_ - 4, 2.2, 8, "#9aa0a6", INK, 0.4))                                 # its plate washer
    o.append(f'<polyline points="{bx_ - 9:.1f},{y + 52:.1f} {bx_ + 1:.1f},{y + 52:.1f} {bx_ + 1:.1f},{ly0 - 0.5:.1f} {bx_ + 1.5 * k + 6:.1f},{ly0 - 0.5:.1f}" fill="none" stroke="{red}" stroke-width="0.9" stroke-dasharray="2.5 1.6"/>')
    DW.dim_h(o, lambda v: v, fy0 + fd + 16, wall_x, bx_, "~2'-9\" (V)", 6.4, up=False)
    _lab(o, bx_ - 6, y + 56, x + 14, y + 26, "Flashing: not visible (V); CWUIC 504.7.3.1: 6\" vertical metal flashing at the deck-to-wall line (V)", 54, color=red)
    _lab_r(o, bx_ + 3, ly0 + 18, x + W3 - 10, y + 160, "2x12 ledger (V): 1/2\"-5/8\" bolts or lags (V), ~2-1/2\" sq. plate washers, ~1 per joist bay (V)", 34, right=True)
    _lab_r(o, bx_ + 1.5 * k + 7, ly0 + jd_ - 2, x + W3 - 10, y + 196, "2x10 joist in a Simpson LUS210Z (stamp legible): (8) + (4) 0.148\" x 3\" nails or SD screws (SD seen)", 34, right=True)
    yy = _lab(o, bx_ - 3, fy0 + fd * 0.5, x + 14, y + 168, "Main-floor band at the end of the floor cantilever, ~2'-9\" past the basement wall (V)", 30)
    _lab(o, wall_x - 4 * k, y + 214, x + 14, yy + 4, "Basement wall below, set back (dashed)", 30)
    o.append(T(x + 14, y + 268, "Ledger on the cantilevered band: engineered", 6.4, 800, fill=red))
    o.append(T(x + 14, y + 277, "(CRC R507.9.1.2 / R301.1.3). A DTT2Z rod runs through", 6.2, 600))
    o.append(T(x + 14, y + 285, "the ledger and band at the device seen (D-505 / 4).", 6.2, 600))
    # 2 B2: post, beam, cap, joists bearing with H2.5A, a Y-brace in the beam plane
    x, y = P[1]; DW._panel(o, x, y, W3, H2, "2", "B2 (OUTER) — POST · CAP · BEAM · H2.5A · BRACE")
    k = 3.0
    by0, bh = y + 86, 11.25 * k
    DW._wood(o, x + 16, by0, W3 - 32, bh, dark=True); o.append(T(x + W3 / 2, by0 + bh / 2 + 3, "6x12 drop beam B2", 6.8, 700, "middle", "#ffffff"))
    for i_ in range(4):
        jx = x + 34 + i_ * 16 * k * 1.3
        DW._wood(o, jx, by0 - 9.25 * k, 1.5 * k, 9.25 * k)
        o.append(R(jx + 1.5 * k, by0 - 9.25 * k * 0.55, 3, 9.25 * k * 0.55 + 7, "#9aa0a6", INK, 0.4))   # the H2.5A
    o.append(R(x + 16, by0 - 9.25 * k - 3, W3 - 32, 3, DW.FILL["deck"], INK, 0.4))
    pc = x + 170
    pw_ = 5.5 * k
    DW._wood(o, pc - pw_ / 2, by0 + bh, pw_, y + 248 - (by0 + bh))
    o.append(R(pc - pw_ / 2 - 6, by0 + bh - 12, pw_ + 12, 12, DW.FILL["steel"], INK, 0.5))        # the cap's black plate on the beam face
    o.append(R(pc - pw_ / 2 - 2, by0 + bh, 3, 16, "#b9bdc1", INK, 0.4)); o.append(R(pc + pw_ / 2 - 1, by0 + bh, 3, 16, "#b9bdc1", INK, 0.4))
    lg = 30 * k * 0.95
    th = 5.5 * k
    for sx in (1, -1):
        x0 = pc + sx * pw_ / 2
        o.append(PGN([(x0, by0 + bh + lg), (x0, by0 + bh + lg - th * 1.41), (x0 + sx * (lg - th * 1.41), by0 + bh), (x0 + sx * lg, by0 + bh)], DW.FILL["timber_dk"], INK, 0.6))
        for (qx, qy) in ((x0 + sx * 5, by0 + bh + lg - 8), (x0 + sx * (lg - 8), by0 + bh + 5)):
            o.append(C(qx, qy, 3.2, "none", red, 0.7, "1.5 1"))
    _lab(o, x + 34 + 1.5 * k + 2, by0 - 9, x + 16, y + 26, f("joist_ties"), 62)
    _lab_r(o, pc + pw_ / 2 + 4, by0 + bh - 6, x + W3 - 10, y + 212, "Post cap: black-painted plate, galvanized legs (CCQ/ECCQ-type) — model and fasteners (V); CCQ66SDS2.5: (16) + (14) 1/4\" x 2-1/2\" SDS", 34, right=True)
    _lab(o, pc - pw_ / 2 - lg + 14, by0 + bh + 10, x + 14, y + 206, "6x6 Y knee brace in the beam plane (B2 posts 2, 4, 6; singles at the end posts)", 26)
    _lab(o, pc - pw_ / 2 - 4, by0 + bh + lg - 8, x + 14, y + 244, f("knee_brace_ends"), 26, color=red)
    o.append(T(pc + 12, y + 262, "6x6 PT post, ~11' to the", 6.2, 600)); o.append(T(pc + 12, y + 270, "B2 pier top (V)", 6.2, 600))
    o.append(T(x + W3 - 10, y + 286, "B2 ~172\" from the house (V); splices over posts (V)", 6.2, 600, "end"))
    # 3 the pier and the post base
    x, y = P[2]; DW._panel(o, x, y, W3, H2, "3", "PIER · POST BASE (EXISTING)")
    k = 2.6
    gy_ = y + 168
    pc = x + 110
    pd = 13 * k
    o.append(LN(x + 10, gy_, x + W3 - 10, gy_, INK, 1.0)); o.append(T(x + 14, gy_ - 3, "grade", 6.0, 600, fill=MUTE))
    top_ = gy_ - 8 * k
    o.append(R(pc - pd / 2, top_, pd, gy_ - top_, DW.FILL["concrete"], INK, 0.8))
    _dashed(o, pc - pd / 2, gy_, pd, 24 * k)
    _dashed(o, pc - 7.5 * k, gy_ + 24 * k, 15 * k, 12 * k)
    o.append(R(pc - 5.75 * k / 2 - 3, top_ - 3.5, 5.75 * k + 6, 3.5, DW.FILL["steel"], INK, 0.5))       # the base's standoff plate
    pw_ = 5.5 * k
    DW._wood(o, pc - pw_ / 2, y + 26, pw_, top_ - 3.5 - (y + 26))
    o.append(R(pc - pw_ / 2 - 2.5, top_ - 3.5 - 20, 2.5, 20, DW.FILL["steel"], INK, 0.4)); o.append(R(pc + pw_ / 2, top_ - 3.5 - 20, 2.5, 20, DW.FILL["steel"], INK, 0.4))
    DW.dim_v(o, lambda v: v, pc + pd / 2 + 8, top_, gy_, "4-12\"", 6.0, left=False)
    _lab(o, pc + pw_ / 2 + 3, top_ - 14, x + 160, y + 40, f("post_base"), 34)
    _lab(o, pc + pd / 2 - 2, top_ + 10, x + 160, y + 100, "Existing round concrete pier ~12-14\" dia. (drawn 13\"), 4-12\" above grade (V)", 34)
    _lab(o, pc + pd / 2 - 1, gy_ + 40, x + 160, y + 196, "Below grade (dashed): footing size and depth not seen (V). 2018 design: 12\" Quik-Tube pier on a 15\" sq x 12\" footing, 36\" min. into competent bearing", 34)
    o.append(T(x + 14, y + 278, "Pier tops: the outer row ~2' below the inner (V). Slope", 6.2, 600))
    o.append(T(x + 14, y + 286, "36.7% average: footing setbacks per CRC R403.1.7 (EOR).", 6.2, 600))
    o.append(T(x + 14, y + 40, "6x6 PT post", 6.4, 700))
    # 4 B1: the header on the beam, the house-side joists hung from it
    x, y = P[3]; DW._panel(o, x, y, W3, H2, "4", "B1 (INNER) — HEADER ON THE BEAM")
    k = 3.0
    bc = x + 150
    bw_, bh = 5.5 * k, 11.25 * k
    by0 = y + 152
    DW._wood(o, bc - bw_ / 2, by0, bw_, bh, dark=True); _x_mark(o, bc - bw_ / 2, by0, bw_, bh)
    hw_, hh_ = 3.0 * k, 9.25 * k
    DW._wood(o, bc - hw_ / 2, by0 - hh_, hw_, hh_); _x_mark(o, bc - hw_ / 2, by0 - hh_, hw_, hh_)
    jd_ = 9.25 * k
    DW._wood(o, x + 14, by0 - hh_, bc - hw_ / 2 - 1 - x - 14, jd_)
    o.append(f'<polyline points="{bc - hw_ / 2 - 1:.1f},{by0 - hh_ + 4:.1f} {bc - hw_ / 2 - 1:.1f},{by0 - hh_ + jd_ + 1.5:.1f} {bc - hw_ / 2 - 12:.1f},{by0 - hh_ + jd_ + 1.5:.1f} {bc - hw_ / 2 - 12:.1f},{by0 - hh_ + 4:.1f}" fill="none" stroke="#5b6166" stroke-width="1.6"/>')
    DW._wood(o, bc + hw_ / 2 + 1, by0 - hh_, x + W3 - 14 - (bc + hw_ / 2 + 1), jd_)
    o.append(R(x + 14, by0 - hh_ - 3, W3 - 28, 3, DW.FILL["deck"], INK, 0.4))
    o.append(f'<polyline points="{bc + hw_ / 2 + 1:.1f},{by0 - 2:.1f} {bc + hw_ / 2 + 8:.1f},{by0 - 2:.1f} {bc + hw_ / 2 + 8:.1f},{by0 + 8:.1f}" fill="none" stroke="#9aa0a6" stroke-width="2"/>')   # the A35/LTP4-type clip
    DW._wood(o, bc - 5.5 * k / 2, by0 + bh, 5.5 * k, y + 262 - (by0 + bh))
    o.append(R(bc - 5.5 * k / 2 - 5, by0 + bh - 10, 5.5 * k + 10, 10, DW.FILL["steel"], INK, 0.5))
    o.append(C(bc + hw_ / 2 + 12, by0 - hh_ + jd_ / 2, 5, "none", red, 0.7, "1.5 1"))
    _lab(o, x + 60, by0 - hh_ + jd_ / 2, x + 14, y + 26, "House-side joists hang from the header in LUS-type face-mount hangers (model and nails (V))", 40)
    _lab_r(o, bc, by0 - hh_ + 5, x + W3 - 10, y + 50, "Continuous header on the beam (size (V)); a solid blocking row over B1", 30, right=True)
    _lab_r(o, bc + hw_ / 2 + 15, by0 - hh_ + jd_ / 2, x + W3 - 10, y + 82, "Outer-bay joists at the header: connection (V)", 26, right=True, color=red)
    _lab_r(o, bc + hw_ / 2 + 6, by0 + 4, x + W3 - 10, y + 196, "A35 / LTP4-type clips header to beam, ~1 per bay: (12) 0.131\" x 1-1/2\" nails each per the catalog (V)", 30, right=True)
    _lab(o, bc - bw_ / 2, by0 + bh / 2, x + 14, y + 214, "6x12 drop beam B1, ~87\" from the house (V); post cap CCQ/ECCQ-type (V)", 30)
    o.append(T(x + 14, y + 286, "6x6 PT post, ~9' to the B1 pier top (V)", 6.2, 600))
    # 5 the deck edge: border, field, fascia, guard bracket
    x, y = P[4]; DW._panel(o, x, y, W3, H2, "5", "DECK EDGE — BORDER · FASCIA · GUARD BRACKET")
    k = 3.6
    ry0 = y + 104
    rx1 = x + 196
    DW._wood(o, rx1 - 1.5 * k, ry0, 1.5 * k, 9.25 * k)                                               # the rim
    DW._wood(o, x + 14, ry0, rx1 - 1.5 * k - x - 14 - 2, 9.25 * k)                                   # a joist beyond
    o.append(R(rx1, ry0 - 1, 0.75 * k, 2 * 5.5 * k * 0.9, DW.FILL["fascia"], INK, 0.5))             # the fascia, two boards
    o.append(LN(rx1, ry0 - 1 + 5.5 * k * 0.9, rx1 + 0.75 * k, ry0 - 1 + 5.5 * k * 0.9, INK, 0.4))
    bw = 5.5 * k
    for i_ in range(5):
        xb = rx1 + 0.75 * k + 3 - (i_ + 1) * (bw + 0.7)
        col = "#5c4636" if i_ < 2 else DW.FILL["deck"]
        o.append(R(xb, ry0 - 1.0 * k, bw, 1.0 * k, col, INK, 0.4))
        if i_ >= 2:
            o.append(R(xb + bw - 1.5, ry0 - 1.0 * k + 1, 2.2, 1.0 * k - 2, "#2b2b2b", "none", 0))
    o.append(R(rx1 + 0.75 * k, ry0 + 6, 0.9 * k, 9.25 * k - 10, DW.FILL["railmetal"], INK, 0.4))   # the bracket
    o.append(R(rx1 + 1.65 * k, y + 70, 3 * k, ry0 - (y + 70) + 9.25 * k, DW.FILL["railmetal"], INK, 0.5))  # the post (its top above, cut off)
    o.append(T(rx1 + 1.65 * k + 1.5 * k, y + 66, "guard post", 6.0, 700, "middle", MUTE))
    for yy_ in (ry0 + 9, ry0 + 9.25 * k - 9):
        o.append(LN(rx1 + 0.75 * k + 0.9 * k, yy_, rx1 - 1.5 * k - 7, yy_, INK, 1.1))
    _dashed(o, rx1 - 1.5 * k - 10, ry0 + 2, 9, 9.25 * k - 4, stroke=_CTX["brand"]["accent_b"])
    _lab(o, rx1 - bw, ry0 - 2, x + 14, y + 30, f"Picture frame (double) + breaker boards: {f('border')}", 46)
    _lab(o, rx1 - 4 * bw, ry0 - 3, x + 14, y + 52, f"Field: {f('decking')}; {f('deck_fasteners')}", 46)
    _lab(o, rx1 + 1, ry0 + 20, x + 14, y + 190, f("fascia") + "; single 2x10 rim behind", 40)
    _lab_r(o, rx1 + 1.2 * k, ry0 + 12, x + W3 - 10, y + 214, "Bracket lags: (2) per flange through the fascia into the rim, as seen", 26, right=True)
    _lab(o, rx1 - 1.5 * k - 6, ry0 + 30, x + 14, y + 222, f("guard_blocking"), 40, color=red)
    o.append(T(x + 14, y + 278, "Board overhang at the edge and the fascia height (V).", 6.2, 600))
    o.append(T(x + 14, y + 286, "WUI: walking surface per CWUIC 504.7.3 (G-001).", 6.2, 600))
    # 6 the stair base
    x, y = P[5]; DW._panel(o, x, y, W3, H2, "6", "STAIR — LOWER FLIGHT AT GRADE")
    gy_ = y + 214
    o.append(LN(x + 10, gy_, x + W3 - 10, gy_, INK, 1.0)); o.append(T(x + W3 - 12, gy_ - 3, "grade", 6.0, 600, "end", MUTE))
    o.append(R(x + 20, gy_ - 5, 120, 5, DW.FILL["timber"], INK, 0.6))                                 # the PT plank
    rz, rx = 6.625 * 3.4, 11.5 * 3.4
    pts = [(x + 34, gy_ - 5)]
    for i_ in range(5):
        pts += [(x + 34 + i_ * rx, gy_ - 5 - (i_ + 1) * rz), (x + 34 + (i_ + 1) * rx, gy_ - 5 - (i_ + 1) * rz)]
    o.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + f'" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    o.append(PGN([(x + 30, gy_ - 5), (x + 30 + 5 * rx + 8, gy_ - 5 - 5 * rz - 2), (x + 30 + 5 * rx + 8, gy_ - 5 - 5 * rz + 34), (x + 74, gy_ - 5)], DW.FILL["timber"], INK, 0.6))
    for i_ in range(5):
        tx_, ty_ = x + 34 + i_ * rx, gy_ - 5 - (i_ + 1) * rz
        o.append(R(tx_ + 2, ty_, rx - 2, 3.4, DW.FILL["deck"], INK, 0.4))
        o.append(R(tx_ + rx * 0.45, ty_ + 3.4, 7, 5, "#9aa0a6", INK, 0.4))
    _lab(o, x + 60, gy_ - 3, x + 14, y + 240, f("stair_base"), 50, color=red)
    _lab(o, x + 34 + 1.45 * rx, gy_ - 5 - 2 * rz + 6, x + 14, y + 112, f("tread_angles") + "; TA10Z per the catalog: (4) + (3) 1/4\" x 1-1/2\" SDS (model (V))", 30)
    _lab(o, x + 34 + 3.5 * rx, gy_ - 5 - 4 * rz + 14, x + 14, y + 60, f("stringers") + " (the outer stringer shown)", 30)
    o.append(T(x + 14, y + 30, "Lower flight: 5 risers ~6-5/8\" (V); treads 2 PVC boards,", 6.2, 600))
    o.append(T(x + 14, y + 38, "closed risers. Landing at the foot per CRC R318.7.6 (V).", 6.2, 600))
    o.append(T(x + 14, y + 286, "Bearing at grade: per the engineer of record (V).", 6.2, 600))
    return mx_sheet("D-501", "Details — as built", "Ledger on the cantilevered band · B2 post, cap, beam, brace · pier and base · B1 header · deck edge · stair base",
                    o, "Schematic details · not to scale · what was seen, (V) where not", meta)


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


def sheet_d505_facts(L, S, t, meta) -> str:
    """D-505 for the deck as built: the guard post on its fascia bracket, the brackets and the (unseen) blocking in plan, H2.5A on B2,
    the lateral ties (the one seen mid-deck, the code's end positions (V)), the knee braces as they stand, the stair guard."""
    s, ext = L.spec, _ext(L.spec)
    f = lambda k, d="": _fx(k, d, ext)
    code = _code(s)
    W3, H2, P = DW._grid6()
    o: List[str] = []
    red, blue = "#b3261e", _CTX["brand"]["accent_b"]
    jsz = s.framing.joist_size
    # 1 the guard post on its fascia bracket (section)
    x, y = P[0]; DW._panel(o, x, y, W3, H2, "1", "GUARD POST — FASCIA BRACKET (SECTION)")
    k = 2.7
    jd = CAT.actual(jsz)[1]
    gh = s.railing.height_in
    top = y + 34
    yd = top + gh * k
    xo = x + 110
    rt, rb = yd + k, yd + k + jd * k
    o.append(R(x + 14, rt, xo - 1.5 * k - 6 - x - 14, jd * k, "none", MUTE, 0.6, 'stroke-dasharray="3 2"'))      # a joist beyond
    DW._wood(o, xo - 1.5 * k, rt, 1.5 * k, jd * k)                                                               # the single rim
    _dashed(o, xo - 1.5 * k - 5.2, rt + 2, 5, jd * k - 4, stroke=blue)                                          # blocking behind: not seen
    fas = max(1.4, 0.75 * k)
    o.append(R(xo, rt - 1, fas, jd * k + 2, DW.FILL["fascia"], INK, 0.4))
    sto = 0.9 * k
    o.append(R(xo + fas, rt + 3, sto, jd * k - 6, DW.FILL["railmetal"], INK, 0.4))                               # the bracket
    pw = 3.0 * k
    px = xo + fas + sto
    o.append(R(px, top, pw, rb - top, DW.FILL["railmetal"], INK, 0.5)); o.append(R(px - 1.5, top - 3, pw + 3, 3, DW.FILL["railmetal"], INK, 0.4))
    o.append(R(x + 14, yd, xo + fas + 0.47 * k - x - 14, k, DW.FILL["deck"], INK, 0.4))
    o.append(R(px - 26, top + 1, 26, 4.5, DW.FILL["railmetal"], INK, 0.4))
    if ext.glass:
        o.append(R(px - 26, yd - 12, 26, 4, DW.FILL["railmetal"], INK, 0.4)); o.append(R(px - 15, top + 6, 3, yd - 12 - top - 6, "#a9c6da", blue, 0.4))
    for yy_ in (rt + jd * k * 0.3, rt + jd * k * 0.72):
        o.append(LN(xo + fas + sto, yy_, xo - 1.5 * k - 3, yy_, INK, 1.1))
    ax = px + pw + 4
    o.append(f'<polyline points="{ax + 20:.1f},{top + 2:.1f} {ax:.1f},{top + 2:.1f}" fill="none" stroke="{red}" stroke-width="1.3"/>')
    o.append(PGN([(ax, top + 2), (ax + 5, top - 0.8), (ax + 5, top + 4.8)], red, "none", 0))
    DW.dim_v(o, lambda v: v, px - 34, top, yd, f"{gh:g}\" guard", 6.2, left=True)
    tx = px + pw + 28
    o.append(T(tx, top + 3, "200 lb at the top, any direction", 6.3, 800, fill=red)); o.append(T(tx, top + 11, f"({code} Table R301.5, footnote)", 6.0, 600, fill=red))
    yy = _lab(o, px + pw / 2, top + 30, tx, top + 30, "Black aluminum post, IRX-type (system (V)), on a fascia bracket (U-cup with side flanges)", 30)
    _lab(o, xo + fas + sto / 2, rt + jd * k * 0.5, tx, max(yy + 8, yd - 26), "Bracket lags: (2) galvanized hex lags + washers per flange through the PVC fascia into the rim, as seen", 30)
    yy = _lab(o, xo - 1.5 * k - 2.6, rb - 6, x + 14, rb + 14, f("guard_blocking") + " (dashed). ESR-4217 covers the bracket on concrete only: the attachment to the wood rim is engineered.", 70, color=red)
    _lab(o, xo - 0.75 * k, rt + jd * k * 0.85, x + 14, yy + 3, "Single 2x10 rim; PVC fascia over it, two boards high", 70)
    # 2 the brackets and the blocking behind them, plan at the rim
    x, y = P[1]; DW._panel(o, x, y, W3, H2, "2", "GUARD POSTS + BRACKETS — PLAN AT THE RIM")
    sp = 16 * 2.2
    o.append(T(x + W3 / 2 + 20, y + 32, f"deck — {jsz} joists at {L.frame.spacing:g}\" o.c.", 6.6, 700, "middle", MUTE))
    for i_ in range(6):
        DW._wood(o, x + 52 + i_ * sp, y + 40, 4, 118)
    DW._wood(o, x + 30, y + 158, W3 - 60, 6)                                                                 # the front rim, single
    DW._wood(o, x + 30, y + 40, 6, 124)                                                                      # the side rim
    o.append(R(x + 26, y + 40, 4, 128, DW.FILL["fascia"], INK, 0.3)); o.append(R(x + 26, y + 164, W3 - 52, 4, DW.FILL["fascia"], INK, 0.3))
    pl = x + 54 + sp * 2.5
    for px_, py_, kind_ in ((x + 18, y + 176, "corner"), (pl, y + 176, "front"), (x + 18, y + 96, "side")):
        o.append(R(px_ - 5, py_ - 5, 10, 10, DW.FILL["railmetal"], INK, 0.6))
        if kind_ == "front":
            o.append(R(px_ - 8, py_ - 10, 16, 3, "#5b6166", INK, 0.3))
            for dx_ in (-6, -3, 3, 6):
                o.append(LN(px_ + dx_, py_ - 10, px_ + dx_, y + 150, INK, 0.8))
            _dashed(o, px_ - sp / 2 + 2, y + 146, sp - 4, 9, stroke=blue)
        elif kind_ == "side":
            o.append(R(px_ + 5, py_ - 8, 3, 16, "#5b6166", INK, 0.3))
            _dashed(o, x + 37, py_ - 5, sp + 15, 10, stroke=blue)
        else:
            o.append(R(px_ + 5, py_ - 8, 3, 6, "#5b6166", INK, 0.3)); o.append(R(px_ + 2, py_ - 8, 6, 3, "#5b6166", INK, 0.3))
    DW.dim_h(o, lambda v: v, y + 196, x + 18, pl, "~5-6' o.c. as seen (V)", 6.2, up=False)
    _lab(o, pl + 6, y + 166, x + 150, y + 222, "Bracket on the fascia: (2) hex lags + washers per flange (4 per bracket) into the rim, as seen", 36)
    _lab(o, pl - 6, y + 150, x + 14, y + 222, f("guard_blocking") + " (dashed)", 26, color=red)
    _lab(o, x + 18, y + 181, x + 14, y + 262, "Corner post at each outside corner (the deck guard has 3); the stair and landing posts are on D-505 / 6", 70)
    # 3 H2.5A at each joist on B2
    x, y = P[2]; DW._panel(o, x, y, W3, H2, "3", "B2 — H2.5A AT EACH JOIST")
    bl = rows_ = beam_rows(L).get("outer")
    DW._wood(o, x + 40, y + 140, W3 - 80, 70, dark=True)
    o.append(T(x + W3 / 2, y + 180, f"{bl.size} drop beam B2" if bl else "drop beam B2", 7.0, 700, "middle", "#ffffff"))
    DW._wood(o, x + 40, y + 92, W3 - 80, 48)
    o.append(T(x + 92, y + 120, f"{jsz} joist @ {L.frame.spacing:g}\" o.c.", 7.0, 700, "middle"))
    o.append(f'<polyline points="{x + 150},{y + 112} {x + 150},{y + 150} {x + 170},{y + 150} {x + 170},{y + 112}" fill="none" stroke="#5b6166" stroke-width="3"/>')
    for yy_ in (118, 126, 134, 142):
        o.append(C(x + 150, y + yy_, 1.3, INK, "none", 0)); o.append(C(x + 170, y + yy_, 1.3, INK, "none", 0))
    o.append(C(x + 160, y + 146, 1.3, INK, "none", 0)); o.append(C(x + 160, y + 156, 1.3, INK, "none", 0))
    _lab(o, x + 160, y + 112, x + 150, y + 40, "Simpson H2.5A, joist to beam: (10) 0.131\" x 2-1/2\" nails, (5) into the joist and (5) into the beam, per the 2026 catalog (nails (V))", 36)
    _lab(o, x + 80, y + 160, x + 14, y + 232, f("joist_ties") + ". B1's house-side joists hang from a header instead (D-501 / 4).", 70)
    _lab(o, x + 250, y + 110, x + 14, y + 266, "Solid blocking row over the beam between the joists (as seen)", 70)
    # 4 the lateral ties: the one seen, the code's end positions
    x, y = P[3]; DW._panel(o, x, y, W3, H2, "4", f"LATERAL — DTT2Z ({code} R507.9.2)")
    o.append(R(x + 20, y + 30, W3 - 40, 40, DW.FILL["house"], INK, 0.6)); o.append(T(x + 28, y + 41, "house: the main-floor band and floor joists (anchorage (V))", 6.0, 700, fill=MUTE))
    DW._wood(o, x + 20, y + 70, W3 - 40, 6, dark=True); DW._wood(o, x + 20, y + 76, W3 - 40, 6)
    for i_ in range(13):
        DW._wood(o, x + 24 + i_ * 21.5, y + 82, 4, 70)
    o.append(T(x + W3 / 2, y + 166, "the ledger along the house, south end left — north end right (schematic)", 6.0, 700, "middle", MUTE))
    seen_x = x + 20 + (W3 - 40) * (1 - 32.5 / 51.25)
    ends = [x + 28, x + W3 - 30]
    for ex_ in ends:
        o.append(R(ex_ - 4, y + 112, 9, 14, "#ffffff", red, 0.9, 'stroke-dasharray="1.6 1"'))
    o.append(LN(seen_x + 1, y + 50, seen_x + 1, y + 120, "#5b6166", 1.6)); o.append(R(seen_x - 3.5, y + 112, 10, 14, "#5b6166", INK, 0.5)); o.append(R(seen_x - 3.5, y + 46, 10, 10, "#5b6166", INK, 0.5))
    DW.dim_h(o, lambda v: v, y + 140, x + 20, ends[0] + 0.5, "24\" max.", 6.0, up=False)
    DW.dim_h(o, lambda v: v, y + 140, ends[1] + 0.5, x + W3 - 20, "24\" max.", 6.0, up=False)
    yy = _lab(o, seen_x + 6, y + 120, x + 14, y + 186, "Simpson DTT2Z seen (IMG_5677), on the side of a joist at the ledger, mid-deck, ~30-35 ft from the north end (V): (8) 1/4\" x 1-1/2\" SDS into the joist + a 1/2\" threaded rod through the ledger and band (catalog); the anchorage inside the house (V)", 80)
    _lab(o, ends[0], y + 126, x + 14, yy + 6, "(V) — R507.9.2: within 24\" of each end — 2 devices of 1,500 lb (or 4 of 750 lb) are required; the devices at these positions are to be verified (V)", 80, color=red)
    # 5 the knee braces as they stand
    x, y = P[4]; DW._panel(o, x, y, W3, H2, "5", "KNEE BRACES — 6x6, IN THE BEAM PLANE")
    DW._wood(o, x + 16, y + 40, W3 - 32, 34, dark=True); o.append(T(x + W3 / 2, y + 61, "6x12 beam (B2 shown)", 6.8, 700, "middle", "#ffffff"))
    for pc, kind_ in ((x + 70, "single"), (x + 220, "y")):
        DW._wood(o, pc - 9, y + 74, 18, 160)
        th = 6 * 2.2
        for sx in ([1] if kind_ == "single" else [1, -1]):
            x0 = pc + sx * 9
            o.append(PGN([(x0, y + 74 + 72), (x0, y + 74 + 72 - th * 1.41), (x0 + sx * (72 - th * 1.41), y + 74), (x0 + sx * 72, y + 74)], DW.FILL["timber_dk"], INK, 0.6))
            for (qx, qy) in ((x0 + sx * 5, y + 74 + 64), (x0 + sx * 64, y + 80)):
                o.append(C(qx, qy, 3.4, "none", red, 0.7, "1.5 1"))
    o.append(T(x + 70, y + 246, "end post: single", 6.4, 700, "middle")); o.append(T(x + 220, y + 246, "Y-brace", 6.4, 700, "middle"))
    DW.dim_h(o, lambda v: v, y + 156, x + 79, x + 151, f"{ftin(s.framing.knee_leg_in)} leg (V)", 6.0, up=False)
    _lab(o, x + 79 + 5, y + 74 + 64, x + 92, y + 190, f("knee_brace_ends") + " (dashed circles)", 22, color=red)
    for j, ln in enumerate(textwrap.wrap(f("knee_braces") + ". No braces toward the house; plan positions on S-101.", 80)[:3]):
        o.append(T(x + 14, y + 264 + 8 * j, ln, 6.2, 600))
    # 6 the stair guard as built
    x, y = P[5]; DW._panel(o, x, y, W3, H2, "6", "STAIR GUARD + HANDRAIL — AS BUILT")
    steps = 7
    rx_, rz_ = 30.0, 19.0
    x0_, y0_ = x + 24, y + 110
    pts = []
    for i_ in range(steps):
        pts += [(x0_ + i_ * rx_, y0_ + i_ * rz_), (x0_ + (i_ + 1) * rx_, y0_ + i_ * rz_)]
    o.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + f'" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    nose = lambda u: y0_ + (u - x0_) * rz_ / rx_
    top_ = lambda u: nose(u) - 38 * 3.6 * 0.6
    hr_ = lambda u: nose(u) - 36 * 3.6 * 0.5
    ua, ub = x0_ + 6, x0_ + steps * rx_ - 6
    o.append(LN(ua, top_(ua), ub, top_(ub), DW.FILL["railmetal"], 3.2))
    o.append(LN(ua, nose(ua) - 14, ub, nose(ub) - 14, DW.FILL["railmetal"], 2.2))
    for uu in (ua, (ua + ub) / 2, ub):
        o.append(LN(uu, nose(uu) + 4, uu, top_(uu) - 4, DW.FILL["railmetal"], 4.0))
    u = ua + 9
    while u < ub - 4:
        if abs(u - (ua + ub) / 2) > 5:
            o.append(LN(u, nose(u) - 14, u, top_(u), "#888", 0.6))
        u += 9
    o.append(LN(ua, hr_(ua) + 6, ub, hr_(ub) + 6, "#5b6166", 2.4))
    o.append(LN(ua - 2, nose(ua - 2) - 1, ub + 6, nose(ub + 6) - 1, red, 0.6, "4 2"))
    DW._lead(o, ub - 40, nose(ub - 40) - 1, x + 196, y + 278, "Line connecting the nosings")
    DW._lead(o, ua + 30, top_(ua + 30), x + 150, y + 30, "Top rail ~38\" over the nosings (V) (stair guard: 34\" min., CRC R321.1.2)")
    DW._lead(o, ua + 45, (nose(ua + 45) - 14 + top_(ua + 45)) / 2, x + 14, y + 248, "Vertical stainless cable ~3-1/4\" o.c. (V); stair openings reject a 4-3/8\" sphere, the landing's 4\" (CRC R321.1.3)")
    DW._lead(o, ua + 90, hr_(ua + 90) + 6, x + 184, y + 120, f("handrail") + "; 34-38\" over the nosings (V) (CRC R320)")
    return mx_sheet("D-505", "Connection details — guard, ties, bracing (as built)",
                    "Guard post on its fascia bracket · brackets and blocking · H2.5A on B2 · DTT2Z lateral · knee braces · the stair guard",
                    o, "Schematic details · not to scale · the code sections cited and the manufacturers' instructions govern", meta)


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
            cap = textwrap.wrap(f"Photo {k_all}. {ph.get('caption', '')}", int(cw / 3.95))[:6]
            ih_max = ch - 10.5 * len(cap) - 8
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
                bw = max(len(ln) for ln in lines) * 7.2 * 0.6 + 14
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
                o.append(T(cx, iy + ih + 12 + 10.5 * m, ln, 7.3, 700 if m == 0 else 500))
        num = f"A-{501 + si}"
        ttl = "Existing conditions — photos" + (f" ({si + 1} of {n_sh})" if n_sh > 1 else "")
        out.append((num, ttl, mx_sheet(num, ttl, "The deck as it stands: photos with the members and hardware called out", o, "Photographs · not to scale · numbered callouts", meta)))
    return out


def _house_label(body: List[str], window=(40, 24, 700, 560), words="EXISTING HOUSE (context)") -> List[str]:
    """The engine's per-zone HOUSE labels replaced by one, centred in the house band of the plan drawn in `window`."""
    S = _CTX["S"]
    body = [x for x in body if not (x.startswith("<text") and ">HOUSE — " in x)]
    x0, x1, y0, y1 = DW.plan_bounds(S)
    X, Y, sc = DW.plan_xform(x0, x1, y0 - 2, y1, *window)
    return body + [TH((X(0) + X(S.W)) / 2, (Y(y0 - 2) + Y(0)) / 2 + 2.5, words, 6.6, 800, "middle", fill=MUTE, halo=DW.FILL["house"])]


def _view_blocks(o: List[str], titles: List[Optional[str]], gaps=None) -> List[float]:
    """The title, scale and graphic bar under each scaled view the sheet's transforms drew (in the order they were made)."""
    vs, seen = [], set()
    for v in _CTX.get("views", []):
        k = (round(v["px0"]), round(v["py0"]), v["kind"])
        if k not in seen:
            seen.add(k); vs.append(v)
    out = []
    for i, (v, t) in enumerate(zip(vs, titles)):
        if t:
            out.append(scale_block(o, v["px0"], v["py0"] + v["h"] + ((gaps or [])[i] if gaps and i < len(gaps) else 40), t, v["u"], v["lab"]))
    return out


def _rp_labels(body: List[str]) -> List[str]:
    """A-201: the post labels on the deck's side edges set beside their posts (at true scale the engine's, above or below, sit on them)."""
    L, S = _CTX["L"], _CTX["S"]
    if not L.rail:
        return body
    x0, x1, y0, y1 = DW.plan_bounds(S)
    X, Y, sc = DW.plan_xform(x0, x1, y0 - 2, y1, 40, 24, 700, 300)
    xs = [p.x for p in L.rail.posts]
    lo, hi = min(xs), max(xs)
    out = list(body)
    for i, p in enumerate(L.rail.posts):
        lab = f"RP{i + 1} {p.kind[0]}"
        if p.kind == "CORNER" or not (abs(p.x - lo) < 1 or abs(p.x - hi) < 1):
            continue
        k = next((j for j, x in enumerate(out) if x.startswith("<text") and f">{lab}<" in x), None)
        if k is None:
            continue
        left = abs(p.x - lo) < 1
        out[k] = T(X(p.x * IN) + (-6 if left else 6), Y(p.y * IN) + 2.5, lab, 6.5, 800, "end" if left else "start")
    return out


def _hook_s100_facts(body: List[str]) -> List[str]:
    S, ext = _CTX["S"], _CTX["ext"]
    i_id = next((i for i, x in enumerate(body) if '>ID<' in x and x.startswith('<text x="710.0"')), None)
    desc = [i for i, x in enumerate(body[:i_id] if i_id else []) if x.startswith('<text x="710.0"') and 'font-size="8"' in x]
    if desc:
        y0 = float(re.search(r'y="([\d.]+)"', body[desc[0]]).group(1))
        new = [T(710, y0 + j * 10, ln, 7.6, 500) for j, ln in enumerate(["Existing round concrete piers with cast-in post bases;", "size, depth and condition: see the note below (V)."])]
        body = [x for i, x in enumerate(body) if i not in desc]
        body = body[:desc[0]] + new + body[desc[0]:]
    i_x = next((i for i, x in enumerate(body) if x.startswith('<text x="710.0"') and "x from the left frame face" in x), None)
    if i_x is not None:
        y_ = float(re.search(r'y="([\d.]+)"', body[i_x]).group(1)) + 44
        o = []
        for j, ln in enumerate(textwrap.wrap("Piers as built: " + (ext.footing_words or _fx("footings", "", ext)), 66)):
            o.append(T(710, y_ + 9 * j, ln, 7.0, 600))
        body = body + o
    # the landing posts' labels, beside their posts
    x0, x1, y0, y1 = DW.plan_bounds(S)
    X, Y, sc = DW.plan_xform(x0, x1, y0 - 2, y1, 40, 24, 640, 560)
    lp = [((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2) for b in S.boxes if b.tag == "landing footing"]
    if lp:
        n0 = max(int(m.group(1)) for x in body for m in [re.search(r">P(\d+)<", x)] if m) - len(lp) + 1
        xs_ = sorted({round(p[0], 2) for p in lp})
        for k, (cx, cy) in enumerate(lp):
            lab = f"P{n0 + k}"
            j = next((i for i, x in enumerate(body) if x.startswith("<text") and f">{lab}<" in x), None)
            if j is not None:
                right = cx > xs_[0] + 0.1
                body[j] = T(X(cx) + (8 if right else -8), Y(cy) + 3, lab, 7.0, 800, "start" if right else "end")
    return _house_label(body, (40, 24, 640, 560))


def _hook_a101(body: List[str]) -> List[str]:
    """A-101 for an existing deck: the decking as recorded — the field, the border's color (V), the clips (V), the fascia; the board
    layout drawn is schematic (no row counts, no gaps or overhangs the record does not give), the overall length the owner's (V)."""
    L, ext = _CTX["L"], _CTX["ext"]
    if not _asb(ext):
        return body
    f = lambda k: _fx(k, "", ext)
    body = [x for x in body if not x.startswith('<text x="760.0"')]
    body = [re.sub(r">([A-Z]) · \d+ rows<", r">\1<", x) for x in body]
    body = [re.sub(r">[^<]* over the edge boards<", f">{ftin(L.spec.geometry.zones[0].width_in + sum(z.width_in for z in L.spec.geometry.zones[1:]))} along the house — the owner's dimension to the deck edge (V)<", x) for x in body]
    body = _house_label(body, (40, 24, 700, 560))
    o = [T(760, 24, "DECKING (AS BUILT)", 9, 800, fill=GOLD)]
    _view_blocks(o, ["DECKING PLAN"], [44])
    _notes_col(o, 760, 40, [("", [f"Field: {f('decking')}", f"Picture frame and breaker boards: {f('border')}", f"Fasteners: {f('deck_fasteners')}", f"Fascia: {f('fascia')}",
                                  "The board layout is drawn schematically: board count, gaps and the edge overhang are not recorded (V)",
                                  "WUI: the walking surface per CWUIC 504.7.3 (G-001)"])], wrap=44, fs=7.2, lh=9.6, y_max=600)
    return body + o


def _axo_note(body: List[str], lines: List[str]) -> List[str]:
    """An isometric sheet's note under its key, rewritten: the engine's note lines (7.2 px, muted, at the key's x) go, these come."""
    i_n = [i for i, x in enumerate(body) if x.startswith('<text x="735.0"') and 'font-size="7.2"' in x and f'fill="{MUTE}"' in x]
    if not i_n or not _asb():
        return body
    y0 = float(re.search(r'y="([\d.]+)"', body[i_n[0]]).group(1))
    new = [T(735, y0 + 9.5 * j, ln, 7.2, 400, fill=MUTE) for j, ln in enumerate(textwrap.wrap(" ".join(lines), 46))]
    keep = [x for i, x in enumerate(body) if i not in i_n]
    return keep[:i_n[0]] + new + keep[i_n[0]:]


def _hook_a002(body: List[str]) -> List[str]:
    return _axo_note(body, ["House shown for context only: its openings are not recorded and are not drawn.", "The frame is called out on S-102 and A-003."])


def _hook_s102(body: List[str]) -> List[str]:
    return _axo_note(body, ["Decking, rail and house removed to show the frame.", "The joists hang from the ledger in LUS210Z hangers; the house-side joists hang from a header on B1;",
                            "the joists bear on B2 with H2.5A ties (count (V)). Piers: the outer row ~2' below the inner (V)."])


def _hook_s100(body: List[str]) -> List[str]:
    """The footing schedule's estimates marked: post stations, lengths and the footings themselves as the job lists them (V); the
    engine's footing sizing words give way to the footings as built (framing.footing_words)."""
    ext = _CTX["ext"]
    if _asb(ext):
        body = _hook_s100_facts(body)
    elif ext.footing_words:
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
    if _asb(ext):
        o_ = []
        _view_blocks(o_, ["FOUNDATION PLAN"], [50])
        i_fr = next((i for i, x in enumerate(body) if re.search(r">Frost [^<]*<", x)), None)
        if i_fr is not None:
            y_fr = float(re.search(r'y="([\d.]+)"', body[i_fr]).group(1))
            soil = re.search(r"soil [^<]*", body[i_fr])
            body = body[:i_fr] + [T(710, y_fr + 9 * j, ln, 7.2, 400, fill=MUTE) for j, ln in enumerate(textwrap.wrap(
                _fx("cover", {}, ext).get("footing_depth", "") + (" " + soil.group(0).replace("·", "—") + " (calc.)" if soil else ""), 62))] + body[i_fr + 1:]
        body = body + o_
    keys = [k for k in ("post_stations", "post_lengths", "footings") if k in (ext.verify or {})]
    if not keys:
        return body
    txt = ("(V) " + "; ".join({"post_stations": "post stations estimated (~90\" o.c.) from the photos and the owner's sketch",
                               "post_lengths": "pier tops at two levels: the outer row (B2) ~2' below the inner (B1) — posts ~9' inner / ~11' outer",
                               "footings": "pier size (~12-14\" dia., drawn 13\") and footing depth not seen"}[k] for k in keys) + " — field-verify")
    ls = textwrap.wrap(txt, 58)[:6]
    o = [T(710, 600 - 9 * (len(ls) - j), ln, 6.8, 700, fill="#b3261e") for j, ln in enumerate(ls)]
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
    if ext is not None and _asb(ext) and _fx("summary", None, ext):
        notes = notes[:1] + [{"head": "Structure as built (summary; the sheets give the detail)", "items": [f"{k}: {v}" for k, v in _fx("summary", [], ext)]}] + notes[1:]
    fs, lh, cw = (6.8, 8.35, 83) if (ext is not None and _asb(ext)) else (6.9, 8.6, 82)
    cols, y0, y_max = (20, 348, 676), (8 if (ext is not None and _asb(ext)) else 12), 606
    blocks = []                                                   # (lines [(indent, text, bold, color)], keep-with-next)
    br = _CTX["brand"]
    for sec in notes:
        blocks.append(([(0, ln, True, br["accent_b"]) for ln in textwrap.wrap(str(sec.get("head", "")).upper(), int((cw - 6) * fs / (fs + 1.2) * 0.92))], True))
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
        numbered = bool(re.fullmatch(r"\d+\.", lines[0][1])) and lines[0][0] == 0 and len(lines) > 1
        h = lh * (len(lines) - (1 if numbered else 0)) + (6 if keep else 2)
        nxt = lh * len(blocks[k + 1][0]) if keep and k + 1 < len(blocks) else 0
        if y + h + nxt > y_max:
            ci += 1; y = y0
            if ci == len(cols):
                pages.append(cur); cur, ci = [], 0
        x = cols[ci]
        if numbered and lines[0][2]:                                  # a number and its text on one line
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


def _embed_clean(inner: str) -> str:
    """Another tool's SVG made safe to inline beside the sheets: no <style> (an inline SVG's CSS reaches the whole page), no
    metadata, its ids prefixed so they cannot meet another sheet's."""
    inner = re.sub(r"<style\b[^>]*>.*?</style>|<metadata\b.*?</metadata>|<title\b[^>]*>.*?</title>", "", inner, flags=re.S)
    pre = "e" + format(abs(hash(inner)) % 10 ** 8, "08d") + "_"
    inner = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{pre}{m.group(1)}"', inner)
    inner = re.sub(r'url\(#([^)]+)\)', lambda m: f"url(#{pre}{m.group(1)})", inner)
    return re.sub(r'(xlink:)?href="#([^"]+)"', lambda m: f'{m.group(1) or ""}href="#{pre}{m.group(2)}"', inner)


def _embed_g(inner: str, vb: str, x: float, y: float, w: float, h: float, cid: str) -> str:
    """Another SVG's content placed in (x, y, w, h) as a group — never a nested <svg> (the page's CSS sizes every svg inside a
    sheet) — at its viewBox's own scale when that is the box (1:1), else fitted; clipped to the box."""
    vx, vy, vw, vh = [float(v) for v in vb.split()]
    k = min(w / vw, h / vh)
    tr = f"translate({x - vx * k:.4f},{y - vy * k:.4f})" + ("" if abs(k - 1) < 1e-9 else f" scale({k:.6f})")
    return (f'<defs><clipPath id="{cid}"><rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"/></clipPath></defs>'
            f'<g clip-path="url(#{cid})"><g transform="{tr}" stroke-linejoin="round">{inner}</g></g>')


def site_plan_sheet(path: Path, meta: dict) -> str:
    """The site-plan agent's submittal field (C-100_submittal_field.svg: viewBox 0 0 1000 612, this set's units at true scale for
    24x36, no title block of its own) embedded 1:1 in the drawing field under this set's title block; its scale note is the one it
    carries (data-scale on its root, or a SCALE line in its <title> / <desc>), or the one the build was given."""
    raw = re.sub(r"<\?xml[^>]*\?>\s*|<!DOCTYPE[^>]*>\s*", "", path.read_text())
    root = re.search(r"<svg\b[^>]*>", raw)
    m = re.search(r'viewBox="([-\d.\s]+)"', root.group(0) if root else "")
    vb = " ".join((m.group(1) if m else "0 0 1000 612").split())
    exact = [float(v) for v in vb.split()] == [0.0, 0.0, 1000.0, 612.0]
    inner = _embed_clean(re.sub(r"^\s*<svg\b[^>]*>|</svg>\s*$", "", raw.strip()))
    sc = _CTX.get("siteplan_scale") or ""
    if not sc:
        a = re.search(r'data-scale(?:-note)?="([^"]+)"', root.group(0) if root else "")
        d_ = re.search(r"<(?:title|desc)\b[^>]*>([^<]*SCALE[^<]*)</(?:title|desc)>", raw, flags=re.I)
        txts = [_html.unescape(re.sub(r"<[^>]+>", "", q)) for q in re.findall(r"<text\b[^>]*>(.*?)</text>", raw, flags=re.S)]
        rat = r"(\d+(?:-\d+)?(?:/\d+)?\" = (?:1'-0\"|\d+'(?:-0\")?))"
        found = []
        for q in txts:
            m_ = re.search(rat, q)
            if m_ and re.search(r"(?i)scale|plan|elevation|section", q):
                name_ = re.split(r"\s+[—-]\s+|\s*SCALE:", q)[0].strip().rstrip(":") or "plan"
                found.append((name_ if len(name_) < 40 else "plan", m_.group(1)))
        if found and not a:
            _CTX["extra_scales"] = list(dict.fromkeys(found))
            sc = "found"
        else:
            sc = (a.group(1) if a else (d_.group(1).strip() if d_ else "")) or "SCALE: AS NOTED ON THE PLAN"
    body = [_embed_g(inner, vb, 0.0, 0.0, 1000.0, 612.0, "c100field")]
    if not exact:
        sc = "SCALE: AS SHOWN (graphic) — the plan was fitted to the field"
    if sc != "found":
        _CTX["extra_scales"] = [("site plan", re.sub(r"(?i)^scale:\s*", "", sc))]
    return mx_sheet("C-100", "Site plan", "The parcel, the house and the deck as built, distances to the lot lines (GIS lines, not a survey)", body,
                    "Site plan · lot lines from County GIS, not a survey", meta)


HOOKS = {"S-101": _hook_s101, "A-301": _hook_a301, "A-201": _hook_a201, "D-501": _hook_d501, "S-100": _hook_s100, "A-002": _hook_a002, "S-102": _hook_s102,
         "A-101": _hook_a101}
SUB_AS_BUILT = {          # an existing deck's sheet subtitles (the engine's speak of new work)
    "A-101": "The field, the picture frame and breakers, the guard posts outside the edge on the fascia brackets — the board layout schematic",
    "S-101": "Ledger, joists, rims, blocking and beams as built; the hardware seen and the knee braces where they are",
    "S-100": "The existing piers, posts and beam rows with the footing schedule; beams dashed (below the joists)",
    "A-002": "Everything called out: piers, posts, braces, beams, decking, picture frame, fascia, stair and guard as built",
    "A-003": "Each layer lifted: piers · posts + knee braces · beams · frame · decking · stair · guard",
    "S-102": "Piers, post bases, posts, knee braces, post caps, beams, joists, rim, ledger, blocking — as built",
    "A-201": "Guard post IDs and types (E end · L line · C corner), the bays as drawn, the outer-edge elevation",
}


# ============================================================================ the permit set: the engine's page under the job's brand
PERMIT_BAD = ("GS Exterior", "GSX", "Deck Division", "Design intent", "design intent", "$", "financ", "Fulton", "Prime+", "LedgerLOK", "Cap-Tor", "HeadLOK rail",
              "G-Tape", "GRK", "Camo ")


def render_permit_set(parts: list, out_dir: str, key: str, name: str, sub: str = "", pdf: bool = False, date_line: Optional[str] = None,
                      renders: Optional[dict] = None, photos: Optional[list] = None, brand=None, no_engineering: bool = False,
                      sheet_size: str = "archd", siteplan_scale: str = "") -> dict:
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
    sheet_size = (sheet_size or "archd").lower().replace("arch-d", "archd").replace("24x36", "archd").replace("11x17", "tabloid")
    if sheet_size not in SHEET_SIZES:
        raise ValueError(f"sheet size {sheet_size!r}: one of {', '.join(SHEET_SIZES)}")
    _CTX["sheet_size"], _CTX["siteplan_scale"] = sheet_size, siteplan_scale
    with active(spec, br, today):
        r = PG.render_permit_set(parts, out_dir, key, name, sub=sub, pdf=False, date_line=today, renders=renders, unbranded=False, no_engineering=no_engineering)
    out = Path(out_dir).resolve()
    page = (out / "page.html").read_text()
    page = brand_page(page, spec, ext, br, name, sheet_size)
    (out / "page.html").write_text(page)
    r["html"] = str(out / "page.html")
    r["sheet_size"] = sheet_size
    if pdf:
        r["pdf"] = print_pdf(page, r.get("files") or {}, out, sheet_size)
    return r


def brand_page(page: str, spec, ext: Ext, br: dict, name: str, sheet_size: str = "letter") -> str:
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
           "@media print{.sheet-page:last-of-type{break-after:auto;page-break-after:auto;} main > footer{display:none;}}" + print_css(sheet_size, _asb(ext)) + "</style>")   # every sheet carries the brand: no page for the footer alone
    page = page.replace("</head>", css + "</head>", 1)
    txt = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    txt = re.sub(r"data:[a-z+/.-]+;base64,[A-Za-z0-9+/=]+", "", txt)
    left = [b for b in PERMIT_BAD if b in txt]
    assert not left, f"the {br['short']} permit set still carries: {left}"
    return page


def print_css(sheet_size: str, sheets_only: bool = True) -> str:
    """Print rules for one sheet per page at the sheet size: 24x36 ARCH D (the sheet's 700 units on the 24" height, 1 unit =
    0.0342857", centred on the 36" width), or a reduced copy (11x17, Letter) fitted with a 1/4" margin. The cover band and index go
    (G-001 carries the index), so the PDF is the sheets alone."""
    W, H, _ = SHEET_SIZES.get(sheet_size, SHEET_SIZES["archd"])
    m = 0.0 if sheet_size == "archd" else 0.25
    k = min((W - 2 * m) / 1000.0, (H - 2 * m) / 700.0)
    sw, sh = 1000 * k, 700 * k
    hide = "header.band,.cover-list,#g-views,.gal,h2.kicker{display:none !important;}" if sheets_only else ""
    return ("@media print{" + f"@page{{size:{W:g}in {H:g}in;margin:0;}}" + hide
            + "html,body{margin:0 !important;padding:0 !important;background:#fff;} main.wrap,.wrap{padding:0 !important;margin:0 !important;max-width:none !important;width:auto !important;}"
            + "section.job{margin:0 !important;padding:0 !important;}"
            + f".sheet-page{{width:{W:g}in;height:{H - 0.001:.3f}in;margin:0 !important;padding:0;display:flex;align-items:center;justify-content:center;overflow:hidden;"
            + "break-after:page;page-break-after:always;break-inside:avoid;box-sizing:border-box;}"
            + ".sheet-page:last-of-type{break-after:auto;page-break-after:auto;} .sheet-page h3{display:none !important;}"
            + f".sheet-page > svg{{width:{sw:.4f}in !important;height:{sh:.4f}in !important;max-height:none !important;border:0 !important;flex:none;}}" + "}")


def print_pdf(page: str, files: dict, out: Path, sheet_size: str = "archd") -> str:
    """The page to PDF, one sheet a page at the sheet size (print_css), the render files beside it."""
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
        W, H, _ = SHEET_SIZES.get(sheet_size, SHEET_SIZES["archd"])
        pg.pdf(path=str(out / "page.pdf"), width=f"{W:g}in", height=f"{H:g}in", print_background=True, prefer_css_page_size=True)
        b.close()
    return str(out / "page.pdf")
