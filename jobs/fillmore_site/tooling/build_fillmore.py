#!/usr/bin/env python3
"""7303 S Fillmore Cir — every document in one command (publishing prep; the Prentice build, for a two-level deck with options).

    cd /home/user/Decks- && python3 $S/fillmore/publish/build_fillmore.py                 # everything: stills .. deliver
    python3 build_fillmore.py combine proposal roof deliver                               # only these steps (in the order below)
    python3 build_fillmore.py --urls=$S/fillmore/publish/urls.json roof proposal deliver  # rebuild the customer docs with the links

Options (every path is a variable below; these override it):
    --spec-dir=DIR     the spec files (default: the spec assembler's $S/fillmore/spec; or /home/user/Decks-/jobs)
    --render-dir=DIR   the rendering agent's photoreal sets (default $S/fillmore/render/final: <set>/<station>[_HHMM|_dusk].jpg)
    --out-root=DIR     where the documents go (default /home/user/Decks-/out: out/fillmore*, out/fillmore_deliver)
    --urls=FILE        the published links the documents and the hub carry (default $S/fillmore/publish/urls.json)
    --copy=FILE        the customer copy (default $S/fillmore/publish/copy_fillmore.json, transcribed from copy/copy.md)
    --date="October 28, 2026"   the date line (default: today)       --no-pdf   HTML only (fast)
    --brand=cde|gs|spec          whose brand the client documents carry when the spec sets none (default gs: GS Exterior Experts — owner 27 Oct)
    --keep-stills                reuse the three.js stills already rendered (default: render them fresh)

Steps, in this order (default: all):
    stills     three.js stills of the base deck: isometrics, exploded, plan, build steps 1-8, sun study (OUT/buildset/renders); and
               the permit set's finished views with the styling furniture off (OUT/renders_permit)
    optstills  three.js stand-ins for an option render set the rendering agent has not delivered (stairs, roof, screens)
    combine    the folders the documents read — base (three.js + the photoreal set under the page's still names), the options'
               renders (stairs-*, night-*, roof-*, screens-*), the roof document's — each with a captions.json
    3d         the interactive 3D page (the configurator agent's build_spec.py on these specs; else a copy of its latest page)
    prices     the base and every option exactly as the proposal prices them -> publish/prices.json (the hub's numbers)
    internal   takeoff + build set (internal) with "Options in the proposal" (how each option is priced; an ESTIMATE flagged)
    roof       the louvered roof's own document, with the screens add-on
    proposal   the customer proposal: the base, Option 1 lighting, Option 2 stairs to the yard and Option 2B stairs along the
               deck (one or the other; each with the lights on its stairs as an add-on), Option 3 louvered roof (+ 3a screens),
               each with its own renders and price; links to the 3D page and the roof document (from urls.json; without a
               link the line is left out)
    supplier   Decks & Docks take-off + build set (the base; no prices)   [supplier_opts: the deck with Options 1 + 2, opt-in]
    cost       cost stack (internal) with the options' basis
    permit     permit set: whole-deck sheets (both levels in one frame) + 3D views (no furniture: OUT/renders_permit); no prices
    dims       the A-100 dimension plan on one Letter-landscape page
    deliver    every PDF into OUT_ROOT/fillmore_deliver/ under its GSX name; publish/manifest.json (what to publish, the files)
Anything missing (a spec, a render set, a URL, a copy line marked [TBD]) is skipped and listed in the summary at the end and in
publish/build_status.json. Publishing order: the 3D page -> URL_3D; `roof` -> URL_ROOF; then `proposal` (it links both) ->
URL_PROPOSAL; internal / cost / supplier / permit; then hub_merge_fillmore.py and the hub (see publish/manifest.json)."""
import copy as _copy
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

# ============================================================================ paths and names (all variables)
S = Path("/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad")
REPO = Path("/home/user/Decks-")
F = S / "fillmore"
PUB = F / "publish"
SPEC_DIR = F / "spec"                                   # the spec assembler's files
SPEC_NAME = "fillmore_centennial"
SPEC_KEYS = [("base", ""), ("lighting", "_lighting"), ("yardstair", "_yardstair"), ("yardstair_alt", "_yardstair_alt"), ("roof", "_roof"),
             ("roof_screens", "_roof_screens"), ("all", "_all"), ("lighting_yardstair", "_lighting_yardstair"),
             ("lighting_yardstair_alt", "_lighting_yardstair_alt")]   # the lighting_* pairs: built from the stair spec + lighting's lights when absent
# The two yard-stair layouts (owner 27 Oct, "show both"): Option 2 the horseshoe, Option 2B along the deck — one or the other, each
# with its own price line, renders and lights-on-the-stair add-on (the lights add-on rides under its stair: the extra over both alone).
# (spec key, block key, number, default title, its lights spec key, render pick, lights render pick, facts prefix, facts suffix)
STAIR_OPTIONS = [
    ("yardstair", "stairs", "Option 2", "Stairs to the yard", "lighting_yardstair", "stairs", "lights_addon", "yard", ""),
    ("yardstair_alt", "stairs2b", "Option 2B", "Stairs to the yard \u2014 along the deck", "lighting_yardstair_alt", "stairs_alt", "lights_addon_alt", "yard2b", "_2b"),
]
BUILT_KEYS = {"lighting_yardstair": "yardstair", "lighting_yardstair_alt": "yardstair_alt"}
DRAFT = F / "draft" / "fillmore_draft.json"             # the fallback base when the assembler's base is missing (base only, no options)
RENDER_FINAL = F / "render" / "final"                   # render_final.sh: <set>/<station>[_HHMM|_dusk].jpg + renders.json + captions.json
CAMERAS = F / "render" / "cameras.json"                 # station labels (the captions' views)
CONFIG_BUILD = F / "configurator" / "tools" / "build_spec.py"     # the configurator agent's builder: build_spec.py SPEC_DIR OUT.html
CONFIG_HTML = F / "configurator" / "fillmore_3d.html"   # its latest page (the fallback)
COPY_FILE = PUB / "copy_fillmore.json"                  # customer copy, from copy/copy.md; {braces} filled from the engine
COPY_AGENT_JSON = F / "copy" / "copy.json"              # if the copy agent ever writes JSON, its keys win
COPY_MD = F / "copy" / "copy.md"                        # watched: a newer copy.md than the transcription -> a warning
URLS_FILE = PUB / "urls.json"                           # URL_3D, URL_ROOF, URL_PROPOSAL, URL_INTERNAL, URL_COST, URL_PERMIT, URL_DD
OUT_ROOT = REPO / "out"
HUB_URL = "https://claude.ai/artifact/J81Bm9MuruFvPFDfcHhV2a"     # "GSX Deck Files" (the jobs hub)
ADDRESS = "7303 S Fillmore Cir"
KEY = "fm"                                              # file keys: r/fm-*.jpg (proposal, internal, cost, supplier), fmr (roof), fmk (permit)
BRAND = "gs"                                            # owner 27 Oct: "Do GS Exteriors for branding" (the engine's default brand)
HERO_SLOT = "corner"                                    # the proposal's cover image: the page still name BASE_MAP puts the hero view in

# The rendering agent's base stations -> the still names page.py's galleries show (proposal: At a glance yard + iso2; Renders
# corner, corner2, ondeck, facade, isolow, under; Isometrics iso, iso2, underiso, plan). A photoreal still replaces the three.js
# still of the same name; a slot with no photoreal keeps its three.js still. Stations with no slot here are not shown.
BASE_MAP = {                 # (copy.md v3 3.1 uses the same slots, so its captions and these files agree)
    "yard": "yard",            # u01, from the yard in front of the lower level: At a glance (first)
    "yard_center": "corner",   # u17, at the step between the levels (both levels, the inset stair): the proposal's cover (HERO_SLOT)
    "yard_left": "corner2",    # u02, across to the upper level
    "upper_deck": "ondeck",    # u18, on the upper level at the stair
    "yard_along": "facade",    # u13, along the deck below the lower level
    "high34": "isolow",        # high view from the arm (left) end
    "high34r": "iso",          # optional: high view from the right end (dropped from render_final.sh at 02:02)
    "under": "under",          # optional: a photoreal view under the upper level (tested in render/t6), else the three.js one
    # no slot in page.py's galleries: "lower_deck" (u03), "arm" (u20), "upper_rail" (u06) — the docs agent would add names
}
BASE_OPTIONAL = {"high34r", "under"}                    # stations the base set may not have: not reported as missing
SCREENS_PRICE = None       # a price for the screens add-on set here (check or ACH); None = the engine's: the spec's
                           # louvered_roofs[].screens_price (owner 27 Oct: $15,000), else the louvered engine's ESTIMATE
# The option render sets -> the still names the option blocks and the roof document use: <prefix><view>[-HHMM]
OPTION_SETS = {   # set: (name prefix, the caption's lead — dropped when the view already says it)
    "yardstair": ("stairs-", "With the stairs to the yard"),
    "yardstair_alt": ("stairs2b-", "With the stairs along the deck"),
    "lights": ("night-", "The lights on"),
    "lights_yardstair": ("night-stairs-", "With the stairs to the yard, lit"),
    "lights_yardstair_alt": ("night-stairs2b-", "With the stairs along the deck, lit"),
    "roof_open": ("roof-open-", "Louvers open"),
    "roof_part": ("roof-partopen-", "Louvers part open"),
    "roof_closed": ("roof-closed-", "Louvers closed"),
    "roof_dusk": ("roof-dusk-", "At dusk"),
    "screens_down": ("screens-down-", "Screens down"),
    "screens_half": ("screens-half-", "Screens half down"),
}
SCREENS_UP_FROM = "roof_closed"          # render_final.sh: "screens up" = the roof with the louvers closed at the screens' time
SCREEN_TIME = "1600"
ROOF_TIMES = ["1000", "1300", "1600"]
# What each block shows: every entry is a preference list — the first still that exists wins (the photoreal name, then the
# three.js stand-in from `optstills`). Missing entries are skipped and reported.
PICKS = {
    "lights": [["night-dusk"], ["night-dusk_deck"]],
    "lights_addon": [["night-stairs-dusk_stair"]],
    "stairs": [["stairs-stair_yard", "stairs-webgl-corner"], ["stairs-high34", "stairs-yard_left", "stairs-webgl-iso"]],
    # 2B's stations are the rendering agent's to name: "*prefix" takes the next still of that set
    "stairs_alt": [["stairs2b-stair_yard", "*stairs2b-", "stairs2b-webgl-corner"], ["stairs2b-high34", "*stairs2b-", "stairs2b-webgl-iso"]],
    "lights_addon_alt": [["night-stairs2b-dusk_stair", "*night-stairs2b-"]],
    "roof": [["roof-open-1000-yard", "roof-open-1300-yard", "roof-open-webgl-corner"], ["roof-closed-1000-yard", "roof-closed-1300-yard", "roof-closed-webgl-corner"]],
    "screens": [["screens-down-1600-yard", "screens-down-webgl-corner"], ["screens-up-1600-yard"]],
    "roof_hero": [["roof-open-1000-yard", "roof-partopen-1000-yard", "roof-open-1300-yard", "roof-open-webgl-corner"]],
    # (the view from inside with the screens down is left out: the render shows the black mesh near opaque; from inside it reads see-through)
    "screens_doc": [["screens-down-1600-yard", "screens-down-webgl-corner"], ["screens-half-1600-yard"], ["screens-up-1600-yard"]],
}
# The roof document's gallery (the owner: open and closed at several times of day, the shade moving on the deck): at each time,
# the yard view open | closed, then the deck view open | closed; then the extras: the roof at dusk with its gutter LED strip on
# (owner 27 Oct: the strip is in the $35,000, "I have that in the bid"). "*" = any render time (the dusk time comes from the render).
ROOF_DOC_STATES = ["open", "closed"]
ROOF_DOC_VIEWS = ["yard", "deck"]
ROOF_DOC_EXTRA = ["roof-dusk-*-yard", "roof-dusk-*-deck"]
# three.js stand-ins (optstills) for a set with no photoreal stills: set -> (spec key, roof changes, views)
FALLBACK_SETS = {
    "yardstair": ("yardstair", None, ["corner", "iso"]),
    "yardstair_alt": ("yardstair_alt", None, ["corner", "iso"]),
    "roof_open": ("roof", dict(angle_deg=90.0, screens=None), ["corner", "iso"]),
    "roof_closed": ("roof", dict(angle_deg=0.0, screens=None), ["corner"]),
    "screens_down": ("roof_screens", dict(angle_deg=0.0, drop=1.0), ["corner"]),
}
WEBGL_VIEW = {"corner": "3D model, from the front corner", "iso": "3D model, from above", "yard": "3D model, from the yard"}
# Customer captions by station: the copy file's "captions" first (copy.md section 3), then these, then cameras.json's label
# (sides as seen from the yard; the arm is the left end). The render's date and time follow ("June 21, 10:30 AM").
VIEW_TEXT = {
    "high34": "From above, the arm (left) end",
    "high34r": "From above, the right end",
    "dusk": "At dusk with the lights on, from the yard",
    "dusk_deck": "At dusk on the lower level: the riser lights in the stair between the levels",
    "dusk_stair": "At dusk: the stairs to the yard lit",
}
ORDER = ["stills", "optstills", "combine", "3d", "prices", "internal", "roof", "proposal", "supplier", "supplier_opts", "cost", "permit", "dims", "deliver"]
EXTRA_STEPS = ["supplier_opts"]                         # opt-in: name it on the command line
STEPS = [s_ for s_ in ORDER if s_ not in EXTRA_STEPS]
OWNER_CHECKS = [   # (spec key, what the owner decided, test on the spec dict as written) — a mismatch is a warning, never a change
    ("base", "footings: 20\" x 42\" concrete caissons (owner 27 Oct: \"Just do caissons, no diamond piers\")",
     lambda d: d.get("framing", {}).get("footing_type") == "caisson" and float(d.get("framing", {}).get("caisson_depth_in") or 0) >= 42),
    ("base", "client: Andie Jones (the buyer)", lambda d: d.get("client") == "Andie Jones"),
    ("base", "brand: GS Exterior Experts (owner 27 Oct: 'Do GS Exteriors for branding' — extras.brand unset or 'gs')",
     lambda d: (d.get("extras") or {}).get("brand") in (None, "gs")),
    ("base", "margin: cost + 40% (extras.gm 0.4)", lambda d: abs(float((d.get("extras") or {}).get("gm") or 0) - 0.4) < 1e-9),
    ("lighting", "margin: 40% on everything but the roof and screens — lights at the job margin (no sell_each)", lambda d: not ((d.get("extras") or {}).get("lights") or {}).get("sell_each")),
    ("base", "margin: the rail at the job margin (extras.rail_sell_per_lf 0), no stair rule", lambda d: (d.get("extras") or {}).get("rail_sell_per_lf") == 0 and not (d.get("extras") or {}).get("stair_rule")),
    ("roof_screens", "screens: $15,000 (louvered_roofs[].screens_price)",
     lambda d: all(float(r.get("screens_price") or 0) == 15000 for r in (d.get("geometry", {}).get("louvered_roofs") or []) if r.get("screens"))),
    ("roof", "roof: $175/SF, 200 SF = $35,000", lambda d: all(float(r.get("price_per_sf") or 0) == 175 and float(r.get("price") or 35000) == 35000
                                                         for r in (d.get("geometry", {}).get("louvered_roofs") or [{}]))),
]
# three.js stills the yard model's trees block from the generic cameras (dry run 27 Oct): rendered with the viewer's
# notrees switch (its generic camera, trees and fences hidden), as the build steps already are; the sun study too
NOTREES_STILLS = ["corner", "iso", "iso2", "isolow"]
NOTREES_SUN = True
# The permit set never shows the styling furniture (owner 27 Oct: styling only, never in the drawings). Its finished views are
# three.js stills rendered with the styling layer off (render_stills styling=False -> the viewer's furn=0) into OUT/renders_permit,
# never the proposal's stills (corner / yard are photoreal there, iso / iso2 furnished); the technical views (exploded, frame,
# structure) never draw furniture (viewer.py), so they come from the base set as before.
PERMIT_FINISHED = ["corner", "yard", "iso2", "iso"]
# The deliverables: (step, out dir attr, delivered file name, hub docs path, url key, artifact icon)
DELIVER = [
    ("proposal", "OUT_PROPOSAL", f"{ADDRESS} - Proposal + Bid Set.pdf", "docs/fillmore-proposal.pdf", "URL_PROPOSAL", "home"),
    ("roof", "OUT_ROOF", f"{ADDRESS} - Louvered Roof - Proposal.pdf", "docs/fillmore-roof.pdf", "URL_ROOF", "home"),
    ("internal", "OUT", f"{ADDRESS} - Takeoff + Build Set.pdf", "docs/fillmore-takeoff.pdf", "URL_INTERNAL", "clipboard"),
    ("cost", "OUT_COST", f"{ADDRESS} - Cost Stack (internal).pdf", "docs/fillmore-cost.pdf", "URL_COST", "calculator"),
    ("permit", "OUT_PERMIT", f"{ADDRESS} - Permit Set.pdf", "docs/fillmore-permit.pdf", "URL_PERMIT", "blueprint"),
    ("supplier", "OUT_DD", f"{ADDRESS} - Decks & Docks Take-off.pdf", "docs/fillmore-decks-docks.pdf", "URL_DD", "clipboard"),
    ("dims", "OUT_DIMS", f"{ADDRESS} - Dimension Plan (inches).pdf", "docs/fillmore-dimensions.pdf", None, None),
    ("supplier_opts", "OUT_DD_OPTS", f"{ADDRESS} - Decks & Docks Take-off - with Options 1 + 2.pdf", "docs/fillmore-decks-docks-options.pdf", "URL_DD_OPTS", "clipboard"),
]
DESCRIPTIONS = {   # one line each for the artifact cards
    "3d": "Interactive 3D of 7303 S Fillmore Cir: the deck with each option, the sun through the day, the louvers and screens, the lights at night.",
    "proposal": "Proposal for 7303 S Fillmore Cir: the two-level deck, then lighting, stairs to the yard and the louvered roof, each priced and rendered.",
    "roof": "The louvered roof for 7303 S Fillmore Cir on its own: Suncoast, black, 20' x 10', with the screens add-on.",
    "internal": "Takeoff and build set for 7303 S Fillmore Cir: order, flags, cut list, the options' price basis, drawings and build steps.",
    "cost": "Cost stack for 7303 S Fillmore Cir: materials, labor, site services and margin, with the options' basis.",
    "permit": "Permit set for 7303 S Fillmore Cir: whole-deck sheets for both levels, no pricing.",
    "supplier": "Decks & Docks take-off and build set for 7303 S Fillmore Cir (the base), to quote.",
    "supplier_opts": "Decks & Docks take-off for 7303 S Fillmore Cir with Options 1 and 2, to quote.",
}
CUSTOMER_DOCS = {"proposal", "roof"}
COLOR_CARD_GLOB = "color/*color*check*.jpg"            # the color agent's card (Prentice delivered one), if it lands: under F
COLOR_CARD_NAME = None                                  # None: the card keeps the color agent's file name
BAD_IN_CUSTOMER_PDF = ["PLACEHOLDER", "[TBD]", "TBD", "placeholder", "ESTIMATE", "Lorem",
                       "% off", "promo", "Promo", "discount", "Discount",          # owner 27 Oct: no promo anywhere
                       "Colorado Deck Experts",                                    # owner 27 Oct: GS Exterior Experts branding
                       "setback", "setbacks", "zoning", "Zoning", "variance", "lot line"]   # the client wording stays neutral


# ============================================================================ plumbing
class Ctx:
    def __init__(self):
        self.status = []           # (step, "ok" | "skip" | "FAIL", note, seconds)
        self.warnings = []
        self.missing = []
        self.outputs = {}          # step -> {html, pdf, files}
        self.specs, self.dicts, self.src = {}, {}, {}
        self.draft = False
        self.used = {}             # render picks actually used, per block
        self.screens_price = None  # the spec's screens_price when the engine does not apply it

    def warn(self, msg):
        if msg in self.warnings:                 # option_blocks runs once per document: say each thing once
            return
        self.warnings.append(msg)
        log(f"  WARNING: {msg}")

    def miss(self, msg):
        if msg not in self.missing:
            self.missing.append(msg)


LOG = None


def log(msg=""):
    print(msg, flush=True)
    if LOG is not None:
        LOG.write(msg + "\n"); LOG.flush()


def jload(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def money(v):
    return ("−" if v < 0 else "") + f"${abs(v):,.0f}"


def signed(v):
    return ("+" if v >= 0 else "−") + f"${abs(v):,.0f}"


def short_ft(inches):
    """20' for a whole number of feet, else 20'-7 5/8\" (units.ftin)."""
    from decktakeoff.units import ftin
    v = float(inches)
    return f"{int(round(v / 12))}'" if abs(v / 12 - round(v / 12)) < 1e-6 else ftin(v)


def parse_args(argv):
    opts = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
    steps = [a for a in argv if not a.startswith("--")]
    bad = [s for s in steps if s not in ORDER]
    if bad or "help" in opts:
        print(__doc__)
        if bad:
            print("unknown step(s):", bad)
        sys.exit(0 if not bad else 2)
    return opts, ([s for s in ORDER if s in steps] if steps else list(STEPS))


def paths(ctx, opts):
    ctx.spec_dir = Path(opts.get("spec-dir", SPEC_DIR))
    ctx.render_dir = Path(opts.get("render-dir", RENDER_FINAL))
    ctx.out_root = Path(opts.get("out-root", OUT_ROOT)).resolve()
    ctx.urls_file = Path(opts.get("urls", URLS_FILE))
    ctx.copy_file = Path(opts.get("copy", COPY_FILE))
    ctx.pdf = not opts.get("no-pdf", False)
    ctx.brand = str(opts.get("brand", BRAND))
    ctx.keep_stills = bool(opts.get("keep-stills", False))
    ctx.date_line = opts.get("date") if isinstance(opts.get("date"), str) else None
    o = ctx.out_root
    ctx.OUT = o / "fillmore"                       # the internal page; its build set holds the three.js stills
    ctx.RD3 = ctx.OUT / "buildset" / "renders"      # three.js stills (render_stills)
    ctx.RD = ctx.OUT / "renders_all"                # the base set the documents use
    ctx.RO = ctx.OUT / "renders_options"            # every option's stills (stairs-*, night-*, roof-*, screens-*)
    ctx.RR = ctx.OUT / "renders_roof"               # the roof document's stills
    ctx.ROF = ctx.OUT / "stills_options"            # three.js stand-ins for missing option sets
    ctx.RP = ctx.OUT / "renders_permit"             # the permit set's finished views, furniture off (PERMIT_FINISHED)
    ctx.OUT_PROPOSAL = o / "fillmore_proposal"
    ctx.OUT_ROOF = o / "fillmore_roof"
    ctx.OUT_DD = o / "fillmore_dd"
    ctx.OUT_DD_OPTS = o / "fillmore_dd_options"
    ctx.OUT_COST = o / "fillmore_cost"
    ctx.OUT_PERMIT = o / "fillmore_permit"
    ctx.OUT_DIMS = o / "fillmore_dimensions"
    ctx.OUT_3D = o / "fillmore_3d"
    ctx.DELIVER = o / "fillmore_deliver"


def import_engine(tries=4, wait=45):
    """Other agents edit the engine while it runs: an import that fails mid-edit is retried, never patched."""
    sys.path.insert(0, str(REPO))
    for i in range(tries):
        try:
            import decktakeoff.page  # noqa: F401
            import decktakeoff.spec  # noqa: F401
            return
        except Exception as e:
            if i == tries - 1:
                raise
            log(f"  engine import failed ({type(e).__name__}: {e}); retrying in {wait}s")
            for m in [m for m in sys.modules if m.startswith("decktakeoff")]:
                del sys.modules[m]
            time.sleep(wait)


# ============================================================================ specs, copy, urls
def load_specs(ctx):
    from decktakeoff.spec import DeckSpec
    d, src = {}, {}
    for k, sfx in SPEC_KEYS:
        p = ctx.spec_dir / f"{SPEC_NAME}{sfx}.json"
        if p.exists():
            d[k], src[k] = json.load(open(p)), str(p)
    if "base" not in d:
        if not DRAFT.exists():
            raise SystemExit(f"no base spec: {ctx.spec_dir / (SPEC_NAME + '.json')} and no draft {DRAFT}")
        d, src = {"base": json.load(open(DRAFT))}, {"base": str(DRAFT)}
        ctx.draft = True
        ctx.warn(f"no {SPEC_NAME}.json in {ctx.spec_dir}: built from the DRAFT ({DRAFT}, placeholder numbers) — base only, no options; "
                 "the delivered PDFs are named 'DRAFT - ...'")
    for k, sfx in SPEC_KEYS:
        if k not in d and not ctx.draft and k not in BUILT_KEYS:
            ctx.miss(f"spec {SPEC_NAME}{sfx}.json" + (" (Option 2B, the stairs along the deck)" if k == "yardstair_alt" else ""))
    for lk, sk in BUILT_KEYS.items():                    # the lights on a yard stair: that stair's spec with the lighting spec's lights
        if lk not in d and "lighting" in d and sk in d:
            x = _copy.deepcopy(d[sk])
            x.setdefault("extras", {})["lights"] = _copy.deepcopy(d["lighting"].get("extras", {}).get("lights"))
            x["job"] = str(x.get("job", "")) + " + OPTION 1 lighting (built by build_fillmore.py)"
            d[lk], src[lk] = x, f"{sk} + lighting's extras.lights (built)"
    if ctx.brand != "spec":
        for k, v in d.items():
            ex = v.setdefault("extras", {})
            if not ex.get("brand"):
                ex["brand"] = ctx.brand
    for key, what, ok in OWNER_CHECKS:                    # the files as written (the brand default below is this build's own)
        if key in src and "/" in str(src[key]):
            try:
                good = ok(jload(src[key], {}) or {})
            except Exception:
                good = False
            if not good:
                ctx.warn(f"spec {Path(src[key]).name} does not match the owner's decision — {what}")
    ctx.dicts, ctx.src = d, src
    ctx.specs = {k: DeckSpec.from_dict(v) for k, v in d.items()}
    log("  specs: " + ", ".join(f"{k} <- {Path(v).name if '/' in str(v) else v}" for k, v in src.items()))
    for k in ("base", "lighting", "yardstair", "roof_screens"):
        if k in src and "/" in str(src[k]):
            log(f"    {k}: modified {datetime.fromtimestamp(Path(src[k]).stat().st_mtime, timezone.utc):%d %b %H:%M} UTC")


def load_copy(ctx):
    c = jload(ctx.copy_file, {}) or {}
    if not c:
        ctx.warn(f"no customer copy at {ctx.copy_file}: the documents use the page's own words")
    over = jload(COPY_AGENT_JSON, {}) or {}
    if over:
        c.update(over)
        log(f"  copy: {ctx.copy_file.name} + the copy agent's {COPY_AGENT_JSON.name}")
    if COPY_MD.exists() and c.get("_copy_md_mtime") and COPY_MD.stat().st_mtime > float(c["_copy_md_mtime"]) + 1:
        ctx.warn(f"{COPY_MD.name} changed ({datetime.fromtimestamp(COPY_MD.stat().st_mtime, timezone.utc):%H:%M} UTC) after {ctx.copy_file.name} "
                 f"was transcribed from it ({datetime.fromtimestamp(float(c['_copy_md_mtime']), timezone.utc):%H:%M} UTC): re-sync the copy file")
    CAPTIONS.clear()
    CAPTIONS.update({k: v for k, v in (c.get("captions") or {}).items() if isinstance(v, str) and "TBD" not in v})
    ctx.copy = c


def load_urls(ctx):
    u = jload(ctx.urls_file, {}) or {}
    ctx.urls = {k: v for k, v in u.items() if isinstance(v, str) and v.startswith("http")}


def fill(ctx, text, where):
    """A copy line with {keys} filled from the engine facts; None (the page's own words are used) when a key is missing or the
    line still says [TBD]."""
    if not text:
        return None
    if "[TBD]" in text or "TBD" in text:
        ctx.warn(f"copy {where}: still marked TBD — left out")
        return None
    try:
        return text.format(**ctx.facts)
    except (KeyError, IndexError, ValueError) as e:
        ctx.warn(f"copy {where}: no engine value for {e} — left out")
        return None


def fill_lines(ctx, lines, where):
    """A list of copy lines, each filled (fill); the lines that cannot be filled or still say TBD are dropped."""
    out = []
    for i, x in enumerate(lines or []):
        if isinstance(x, (list, tuple)):          # (label, text) rows
            t = fill(ctx, x[1], f"{where}[{i}]")
            if t:
                out.append((x[0], t))
        else:
            t = fill(ctx, x, f"{where}[{i}]")
            if t:
                out.append(t)
    return out


# ============================================================================ engine facts (the numbers the copy and the hub quote)
def engine_facts(ctx):
    from decktakeoff import run
    from decktakeoff.units import ftin
    from decktakeoff.takeoff import inches_frac
    f = {}
    t, flags, p = run(ctx.specs["base"])
    ctx.base_run = (t, flags, p)
    L = t.layout
    f["sf"] = f"{L.deck_sf:,.1f}".rstrip("0").rstrip(".")
    try:
        f["width"] = ftin(L.finished_w)
    except Exception:
        pass
    try:
        from decktakeoff.report import levels_of
        lv = levels_of(t)
        if len(lv) >= 2:
            lo, up = sorted(lv, key=lambda v: v["height_in"])[:2]
            f.update(lower_h=ftin(lo["height_in"]), upper_h=ftin(up["height_in"]), step=ftin(up["height_in"] - lo["height_in"]),
                     step_in=f"{up['height_in'] - lo['height_in']:g}", lower_sf=f"{lo['sf']:g}", upper_sf=f"{up['sf']:g}")
    except Exception as e:
        ctx.warn(f"levels: {e}")
    f["columns"] = str(L.n_footings)
    f["piers"] = str(int(sum(l.order for l in t.lines if l.item.lower().startswith("diamond pier"))) or L.n_footings)
    fr = ctx.specs["base"].framing
    ft, n_ = str(fr.footing_type), L.n_footings
    dia = f'{float(getattr(fr, "caisson_dia_in", 20) or 20):g}"'
    f["footing_type"] = ft
    f["footing_one"] = {"diamond_pier": "a Diamond Pier", "caisson": "a concrete caisson", "concrete": "a concrete pier",     # copy.md v3.3 wording
                        "existing": "the existing caisson"}.get(ft, ft.replace("_", " "))
    depth = getattr(fr, "caisson_depth_in", None) or (float(ctx.specs["base"].site.frost_depth_in or 36) + 2)
    f["footings_internal"] = {"diamond_pier": f"{fr.footing_model} Diamond Piers" + (" (model locked)" if getattr(fr, "footing_model_lock", False) else ""),
                              "caisson": f'{dia} x {float(depth):g}" concrete caissons', "concrete": "concrete piers", "existing": "the existing caissons"}.get(ft, ft)
    f["column_bases_internal"] = (f'Simpson ABU88RZ bases set on the cured caissons with (2) 5/8" Titen HD each (never wet-set), on {f["footings_internal"]} (the upper row through saw-cut openings in the patio slab, poured flush)'
                                  if ft == "caisson" else f'ABU88Z / ABU88RZ bases on {f["footings_internal"]}')
    f["footings_hub"] = f"{n_} " + f["footings_internal"]
    try:
        rl = sum(float(pt.layout.rail.rail_lf) for pt in L.parts if getattr(pt.layout, "rail", None)) if hasattr(L, "parts") else float(L.rail.rail_lf)
        f["rail_lf"] = f"{rl:g}"
    except Exception:
        pass
    # Option 1: the lights (and the add-on's extra lights on the yard stair)
    if "lighting" in ctx.specs:
        try:
            from decktakeoff.report import lights_of, post_light_terms
            tl, _, _ = run(ctx.specs["lighting"])
            lo = lights_of(tl)
            plan = getattr(tl, "lighting", None)
            lb_ = lights_of(run(ctx.specs["base"])[0]) if "base" in ctx.specs else dict(total=0, riser=0, post_cap=0)   # lights in the base (none: the lights are a la carte, owner 27 Oct)
            f.update(base_riser=str(lb_["riser"]), opt1_post=str(lo["post_cap"] - lb_["post_cap"]), opt1_total=str(lo["total"] - lb_["total"]))
            f.update(lights_total=str(lo["total"]), lights_riser=str(lo["riser"]), lights_post=str(lo["post_cap"]),
                     post_label=post_light_terms(tl)[0], post_kind=getattr(plan, "post_kind", "") or "",
                     light_each=f"{float((plan.cfg if plan else {}).get('sell_each') or 0):,.0f}")
            for _sk, _bk, _num, _tt, lkey, _rp, _lp, _pre, suf in STAIR_OPTIONS:
                if lkey in ctx.specs:
                    la = lights_of(run(ctx.specs[lkey])[0])
                    f.update({f"add_riser{suf}": str(la["riser"] - lo["riser"]), f"add_post{suf}": str(la["post_cap"] - lo["post_cap"]),
                              f"add_total{suf}": str(la["total"] - lo["total"])})
        except Exception as e:
            ctx.warn(f"lighting facts: {type(e).__name__}: {e}")
    # Options 2 / 2B: each yard stair (flights, landing, width) — the stair the base does not have (page._added_facts' rule)
    from decktakeoff.pricing import stair_specs
    for skey, _bk, num, _tt, _lk, _rp, _lp, pre, _suf in STAIR_OPTIONS:
        if skey not in ctx.specs:
            continue
        try:
            ty, _, _ = run(ctx.specs[skey])
            s0 = stair_specs(t)
            new = [(ss, st) for ss, st in zip(stair_specs(ty), ty.layout.stairs) if ss not in s0]
            if not new:
                raise LookupError(f"{num}'s spec has no stair the base does not have")
            ss, st = new[0]
            g = st.geo
            turn = str(getattr(ss, "turn", "") or "")
            f.update({f"{pre}_width": ftin(ss.width_in), f"{pre}_width_short": short_ft(ss.width_in), f"{pre}_turn": turn,
                      f"{pre}_lands_on": str(getattr(ss, "landing", "") or ""), f"{pre}_risers": str(g.risers),
                      f"{pre}_riser_h": inches_frac(g.riser_in), f"{pre}_flights": str(len(g.flights))})
            if len(g.flights) >= 2:
                f.update({f"{pre}_f1": str(g.flights[0].risers), f"{pre}_f2": str(g.flights[1].risers)})
            f[f"{pre}_layout"] = ("horseshoe" if turn == "switchback" and len(g.flights) == 2 and g.flights[0].risers > 1
                                  else "relay" if len(g.flights) == 2 and g.flights[0].risers == 1 else "other")
            if not 6.0 <= float(g.riser_in) <= 7.75:
                ctx.warn(f"{num}'s yard stair has risers of {inches_frac(g.riser_in)} ({g.risers} risers, flights "
                         f"{'+'.join(str(fl.risers) for fl in g.flights)}): its facts print the engine's stair line as is — the stairs "
                         "agent's flights must land in the spec first (copy.md 1.11)")
            if getattr(ss, "landings", None):
                a_, b_ = ss.landings[0]
                f[f"{pre}_landing"] = f"{ftin(a_)} x {ftin(b_)}"
                f[f"{pre}_landing_short"] = f"{short_ft(a_)} x {short_ft(b_)}"
        except Exception as e:
            ctx.warn(f"{num} yard stair facts: {type(e).__name__}: {e}")
    # Option 3: the roof as sold, and its screens
    rs = ctx.specs.get("roof_screens") or ctx.specs.get("roof")
    if rs is not None:
        try:
            from decktakeoff.louvered import roofs_of, roof_pricing, resolve, surfaces_of
            from decktakeoff.pricing import price_louvered, roof_size_ft
            r = roofs_of(rs)[0]
            ap = price_louvered(rs, r)
            w_, d_ = roof_size_ft(r)
            Lr = run(rs)[0].layout
            rp = roof_pricing(rs, Lr)["roofs"][0]
            q = resolve(r, surfaces_of(Lr))
            sold_w, sold_d = float(rp.get("width_ft") or w_), float(rp.get("depth_ft") or d_)
            f.update(roof_w=short_ft(round(sold_w * 12, 3)), roof_d=short_ft(round(sold_d * 12, 3)), roof_sf=f"{float(rp.get('area_sf') or ap.sf):g}",
                     roof_rate=f"{ap.rate:,.0f}", roof_price=f"{ap.sell:,.0f}", roof_zones=str(q.get("n_zones", "")),
                     roof_posts=str(len(q.get("posts") or [])), roof_rail_posts=str(sum(1 for pt in (q.get("posts") or []) if pt.get("on_rail"))))
            if q.get("lights"):
                f["roof_led"] = "yes"
            if "all" in ctx.specs and "lighting_yardstair" in ctx.specs:     # the roof's posts take rail posts, and their lights
                from decktakeoff.report import lights_of
                fewer = lights_of(run(ctx.specs["lighting_yardstair"])[0])["post_cap"] - lights_of(run(ctx.specs["all"])[0])["post_cap"]
                if fewer > 0 and (ctx.dicts["all"].get("extras") or {}).get("lights"):
                    f["roof_fewer_posts"] = str(fewer)
            sides = [str(s_.get("side", "front")) for s_ in (r.get("screens") or [])]
            f["screen_sides"] = "+".join(sorted(sides, key=lambda s_: ("front", "left", "right").index(s_) if s_ in ("front", "left", "right") else 9))
            f["screen_words"] = "; ".join(x.get("words", "") for x in (rp.get("screens") or []) if x.get("words"))
            f["screens_estimate"] = bool(rp.get("screens_estimate")) or any(x.get("estimate") for x in (rp.get("screens") or []))
            sp_price = r.get("screens_price")
            if sp_price is not None and r.get("screens") and abs(float(rp.get("screens_sell") or 0) - float(sp_price)) > 0.5:
                ctx.screens_price = float(sp_price)
                ctx.warn(f"the spec sets the screens at ${float(sp_price):,.0f} (louvered_roofs[].screens_price) but the louvered engine prices "
                         f"${float(rp.get('screens_sell') or 0):,.0f}{' (its ESTIMATE)' if f['screens_estimate'] else ''}: louvered.resolve() hands "
                         "_screens() its result dict, which has no screens_price — this build passes the spec's price itself (louvered.py's "
                         "owner to fix)")
        except Exception as e:
            ctx.warn(f"roof facts: {type(e).__name__}: {e}")
    want_client = (ctx.copy or {}).get("client")
    if want_client and str(ctx.specs["base"].client or "") != want_client:
        ctx.warn(f"the spec's client reads {ctx.specs['base'].client!r}: the cover says 'Prepared for {ctx.specs['base'].client}' "
                 f"(the copy has {want_client!r}; the spec assembler sets `client`)")
    ctx.facts = f
    log("  facts: " + ", ".join(f"{k}={v}" for k, v in f.items() if k not in ("screen_words",)))


# ============================================================================ renders
def set_info(set_dir):
    """{stem: info} for one render set: decktakeoff.cycles' renders.json (station, mode, when, sun_caption) + the rendering
    agent's captions.json (view, louvers, screens), else just the files."""
    out = {}
    if not set_dir.is_dir():
        return out
    rj = jload(set_dir / "renders.json", {}) or {}
    cj = jload(set_dir / "captions.json", {}) or {}
    for fpath in sorted(set_dir.glob("*.jpg")):
        r = dict(rj.get(fpath.name) or {})
        c = cj.get(fpath.name)
        if isinstance(c, dict):
            r.update({k: v for k, v in c.items() if v is not None and k != "sun"})
            if isinstance(c.get("sun"), str) and not r.get("sun_caption"):
                r["sun_caption"] = c["sun"]
        st = r.get("station")
        if not st:
            m = re.match(r"(.+?)_(\d{4}|dusk)$", fpath.stem)
            st = m.group(1) if m else fpath.stem
        r["station"] = st
        r["suffix"] = fpath.stem[len(st) + 1:] if fpath.stem.startswith(st + "_") else ""
        r["path"] = fpath
        out[fpath.stem] = r
    return out


CAPTIONS = {}            # the copy file's captions by station (load_copy)


def view_words(info, cams):
    st = info["station"]
    v = CAPTIONS.get(st) or VIEW_TEXT.get(st) or (cams.get(st) or {}).get("label") or info.get("view") or st.replace("_", " ")
    if info.get("mode") == "dusk" and "dusk" not in v.lower():
        v += ", at dusk"
    return v


def when_words(info):
    """The render's local date and time as a homeowner reads it: "June 21, 10:30 AM" (from renders.json "when")."""
    w = info.get("when")
    try:
        dt = datetime.fromisoformat(str(w))
        return f"{dt:%B} {dt.day}, {dt.hour % 12 or 12}:{dt:%M} {'AM' if dt.hour < 12 else 'PM'}"
    except Exception:
        return (info.get("sun_caption") or "").split(" — ")[0]


def caption(info, cams, lead="", extra_view=None):
    v = extra_view or view_words(info, cams)
    lw, vw = lead.lower(), v.lower()
    if lead and (lw in vw or ("stairs to the yard" in lw and "stairs to the yard" in vw)
                 or (lw == "the lights on" and ("light" in vw or " lit" in vw))):
        lead = ""
    return " · ".join(x for x in (lead, v, when_words(info)) if x)


def opt_name(prefix, info):
    """roof-open-1000-yard, roof-dusk-2105-deck, screens-down-1600-yard (time first: the roof document sorts by it, copy.md
    v3 3.4); untimed sets keep the station: stairs-stair_yard, night-dusk, night-upper_deck."""
    short = re.sub(r"^roof_", "", info["station"])
    suf = info.get("suffix") or ""
    if suf == "dusk":
        try:
            suf = datetime.fromisoformat(str(info.get("when"))).strftime("%H%M") if prefix.startswith(("roof-", "screens-")) else ""
        except Exception:
            suf = "dusk" if prefix.startswith(("roof-", "screens-")) else ""
    return f"{prefix}{suf}-{short}" if suf else f"{prefix}{short}"


def pick(ctx, key, folder):
    """The stills a block shows: per PICKS entry, the first name that exists — a "*prefix" entry takes the next photoreal still of
    that set (not a three.js stand-in); an entry with nothing is reported."""
    have = sorted(q.stem for q in Path(folder).glob("*.jpg"))
    out = []
    for prefs in PICKS.get(key, []):
        hit = None
        for n in prefs:
            if n.startswith("*"):
                hit = next((h for h in have if h.startswith(n[1:]) and h not in out and "-webgl-" not in h), None)
            elif n in have and n not in out:
                hit = n
            if hit:
                break
        if hit:
            out.append(hit)
        else:
            ctx.miss(f"render for {key}: {prefs[0]}")
    ctx.used[key] = out
    return out


def clear_jpgs(d):
    d.mkdir(parents=True, exist_ok=True)
    for q in list(d.glob("*.jpg")) + [d / "captions.json", d / "sun.json"]:
        if q.exists():
            q.unlink()


# ============================================================================ steps
def step_stills(ctx):
    from decktakeoff import run
    from decktakeoff.buildset import build_set
    if not ctx.keep_stills and ctx.RD3.exists():
        for q in ctx.RD3.glob("*.jpg"):          # render_stills keeps a still that exists: start fresh so nothing is stale
            q.unlink()
    t, flags, p = ctx.base_run
    from decktakeoff.render import render_stills, STILLS
    from decktakeoff.scene import build_scene, sun_study_stills
    pre = [(n_, dict(q_, notrees="1")) for n_, q_ in STILLS if n_ in NOTREES_STILLS]
    if NOTREES_SUN:
        pre += [(n_, dict(q_, notrees="1")) for n_, q_, _ in sun_study_stills(t.layout.spec.site)]
    if pre:                                      # first, so build_set's render (it keeps a still that exists) fills only the rest
        render_stills(build_scene(t.layout), str(ctx.RD3), which=[], extra=pre)
    r = build_set(t, flags, str(ctx.OUT / "buildset"), render=True, customer=False)
    n = len(list(ctx.RD3.glob("*.jpg")))
    err = ctx.OUT / "buildset" / "renders_error.txt"
    if not n and err.exists():
        raise RuntimeError("three.js stills failed: " + err.read_text()[:300])
    # the permit set's finished views: the same cameras as the base set's, the styling furniture off
    if not ctx.keep_stills:
        clear_jpgs(ctx.RP)
    sp = dict(STILLS)
    render_stills(build_scene(t.layout), str(ctx.RP), which=[], styling=False,
                  extra=[(n_, dict(sp[n_], **({"notrees": "1"} if n_ in NOTREES_STILLS else {}))) for n_ in PERMIT_FINISHED])
    n_p = len([n_ for n_ in PERMIT_FINISHED if (ctx.RP / f"{n_}.jpg").exists()])
    return f"{n} three.js stills in {ctx.RD3}; {n_p} permit views without furniture in {ctx.RP}"


def step_optstills(ctx):
    from decktakeoff import run
    from decktakeoff.spec import DeckSpec
    from decktakeoff.scene import build_scene
    from decktakeoff.render import render_stills
    done = []
    for set_name, (skey, change, views) in FALLBACK_SETS.items():
        if set_info(ctx.render_dir / set_name):
            continue                              # the photoreal set is there: no stand-in
        if skey not in ctx.dicts:
            continue
        d = _copy.deepcopy(ctx.dicts[skey])
        for r in (d.get("geometry", {}).get("louvered_roofs") or []):
            if change:
                if "angle_deg" in change:
                    r["angle_deg"] = change["angle_deg"]
                if change.get("screens", 1) is None:
                    r.pop("screens", None)
                if "drop" in change:
                    for s_ in r.get("screens") or []:
                        s_["drop"] = change["drop"]
        out = ctx.ROF / set_name
        clear_jpgs(out)
        t, _, _ = run(DeckSpec.from_dict(d))
        render_stills(build_scene(t.layout), str(out), which=[], extra=[(v, dict(view=v, notrees="1")) for v in views])
        done.append(f"{set_name} ({len(list(out.glob('*.jpg')))})")
    return ("three.js stand-ins: " + ", ".join(done)) if done else "every option set has photoreal stills: no stand-ins needed"


def step_combine(ctx):
    cams = jload(CAMERAS, {}) or {}
    rf = ctx.render_dir
    # ---- the base: three.js stills, then the photoreal set under the page's names
    clear_jpgs(ctx.RD)
    for q in ctx.RD3.glob("*.jpg"):
        shutil.copy(q, ctx.RD / q.name)
    if (ctx.RD3 / "sun.json").exists():
        shutil.copy(ctx.RD3 / "sun.json", ctx.RD / "sun.json")
    caps = {}
    base = set_info(rf / "base")
    placed = []
    for station, slot in BASE_MAP.items():
        info = base.get(station)
        if info is None:
            if station not in BASE_OPTIONAL:
                ctx.miss(f"photoreal base/{station}.jpg (slot '{slot}' keeps the three.js still)")
            continue
        shutil.copy(info["path"], ctx.RD / f"{slot}.jpg")
        caps[slot] = caption(info, cams)
        placed.append(slot)
    json.dump(caps, open(ctx.RD / "captions.json", "w"), indent=1)
    unplaced = sorted(set(base) - set(BASE_MAP))
    # ---- the options: every set under <prefix><view>[-HHMM]
    clear_jpgs(ctx.RO)
    oc = {}
    got = {}
    for set_name, (prefix, lead) in OPTION_SETS.items():
        info = set_info(rf / set_name)
        got[set_name] = len(info)
        for stem, i in info.items():
            nm = opt_name(prefix, i)
            shutil.copy(i["path"], ctx.RO / f"{nm}.jpg")
            oc[nm] = caption(i, cams, lead)
        if set_name == SCREENS_UP_FROM:          # "screens up" = the louvers closed at the screens' time
            for stem, i in info.items():
                if i.get("suffix") == SCREEN_TIME:
                    nm = opt_name("screens-up-", i)
                    shutil.copy(i["path"], ctx.RO / f"{nm}.jpg")
                    oc[nm] = caption(i, cams, "Screens up")
        if not info:
            fb = ctx.ROF / set_name
            for q in sorted(fb.glob("*.jpg")) if fb.is_dir() else []:
                nm = f"{prefix}webgl-{q.stem}"
                shutil.copy(q, ctx.RO / f"{nm}.jpg")
                oc[nm] = " · ".join(x for x in (lead, WEBGL_VIEW.get(q.stem, "3D model")) if x)
            ctx.miss(f"photoreal set {set_name}" + (" (three.js stand-in used)" if fb.is_dir() and any(fb.glob("*.jpg")) else ""))
    json.dump(oc, open(ctx.RO / "captions.json", "w"), indent=1)
    # ---- the roof document: its roof-* and screens-* stills
    clear_jpgs(ctx.RR)
    rc = {}
    for q in ctx.RO.glob("*.jpg"):
        if q.stem.startswith(("roof-", "screens-")):
            shutil.copy(q, ctx.RR / q.name)
            rc[q.stem] = oc.get(q.stem, q.stem)
    json.dump(rc, open(ctx.RR / "captions.json", "w"), indent=1)
    n3 = len(list(ctx.RD3.glob("*.jpg")))
    if not n3:
        ctx.miss("three.js stills (run the 'stills' step): the documents have no isometrics, exploded views or build steps")
    return (f"base: {n3} three.js + {len(placed)}/{len(BASE_MAP)} photoreal ({', '.join(placed) or 'none'})"
            + (f"; not placed: {', '.join(unplaced)}" if unplaced else "")
            + f" · options: {len(oc)} stills (" + ", ".join(f"{k} {v}" for k, v in got.items()) + f") · roof document: {len(rc)}")


def step_3d(ctx):
    ctx.OUT_3D.mkdir(parents=True, exist_ok=True)
    out = ctx.OUT_3D / "fillmore_3d.html"
    note = ""
    if CONFIG_BUILD.exists() and not ctx.draft:
        r = subprocess.run([sys.executable, str(CONFIG_BUILD), str(ctx.spec_dir), str(out)], cwd=str(REPO), capture_output=True, text=True, timeout=1500)
        if r.returncode == 0 and out.exists():
            ctx.outputs["3d"] = dict(html=str(out), files={})
            if "yardstair_alt" in ctx.specs and not re.search(r"along the deck|yardstair_alt|stairs2b|Option 2B", out.read_text(errors="ignore")):
                ctx.warn("the 3D page has no Option 2B toggle (stairs along the deck) yet: the configurator agent's build_spec.py adds it")
            tail = (r.stdout or "").strip().splitlines()
            return f"built from {ctx.spec_dir} by {CONFIG_BUILD.name} ({out.stat().st_size // 1024} KB)" + (f"; {tail[-1]}" if tail else "")
        note = f"{CONFIG_BUILD.name} failed (exit {r.returncode}): {(r.stderr or r.stdout or '').strip().splitlines()[-1:]}"
        ctx.warn(note)
    if CONFIG_HTML.exists():
        shutil.copy(CONFIG_HTML, out)
        ctx.outputs["3d"] = dict(html=str(out), files={})
        ctx.warn(f"3D page: copied the configurator agent's latest {CONFIG_HTML.name} (built from its own spec copies, "
                 f"{datetime.fromtimestamp(CONFIG_HTML.stat().st_mtime, timezone.utc):%d %b %H:%M} UTC)")
        return f"copied {CONFIG_HTML}" + (f" ({note})" if note else "")
    raise RuntimeError("no configurator builder and no configurator page")


def roof_deck_work(ctx):
    """The deck structure the roof needs (owner 27 Oct: the base is designed without the roof; the roof version re-lays U1 with a
    column under each roof post on 30" caissons): the roof spec's deck price less the base's, at the deck's margin. None if <= 0."""
    from decktakeoff import run
    sp = ctx.specs
    rs = sp.get("roof") or sp.get("roof_screens")
    if rs is None or "base" not in sp:
        return None
    d = run(rs)[2].sell - run(sp["base"])[2].sell
    if d <= 0:
        return None
    return dict(price=float(d), label="the deck structure for it",
                note=f"Its price includes the deck structure the roof needs: a column on a larger concrete caisson under each of its two posts, with blocking and ties (${d:,.0f}).")


def option_blocks(ctx, customer=True):
    """The proposal's option blocks (page.render_page options=[dict]): Option 1 lighting; Option 2 stairs to the yard and Option
    2B stairs along the deck (one or the other), each with the lights on its stairs as an add-on; Option 3 louvered roof (+ 3a
    screens) — each its spec or roof, its renders, its words."""
    c = ctx.copy or {}
    f = ctx.facts
    sp = ctx.specs
    ro = str(ctx.RO)
    blocks = []
    if "lighting" in sp:
        cl = c.get("lights") or {}
        o = dict(key="lights", number="Option 1", title=cl.get("title", "Lighting"), spec=sp["lighting"], renders=pick(ctx, "lights", ro), renders_dir=ro)
        b = fill(ctx, cl.get("blurb_accent" if f.get("post_kind") == "accent" else "blurb_cap"), "lights.blurb")
        if b:
            o["blurb"] = b
        if cl.get("note") and f.get("roof_fewer_posts") and (sp.get("roof_screens") or sp.get("roof")) is not None:
            n = fill(ctx, cl["note"], "lights.note")       # with Option 3 the roof posts take rail posts (and their lights)
            if n:
                o["note"] = n
        blocks.append(o)
    elif not ctx.draft:
        ctx.miss("Option 1 lighting (no lighting spec)")
    for skey, bkey, num, title, lkey, rpick, lpick, pre, _suf in STAIR_OPTIONS:
        if skey not in sp:
            if not ctx.draft:
                ctx.miss(f"{num} {title} (no {SPEC_NAME}{dict(SPEC_KEYS)[skey]}.json)")
            continue
        cs = c.get(bkey) or {}
        o = dict(key=bkey, number=num, title=cs.get("title", title), spec=sp[skey], renders=pick(ctx, rpick, ro), renders_dir=ro,
                 group="yard stair")              # one or the other: for page.py's "every option" total once it reads a group (ignored today)
        lay = f.get(f"{pre}_layout", "other")
        b = fill(ctx, cs.get(f"blurb_{lay}"), f"{bkey}.blurb_{lay}")
        if b:
            o["blurb"] = b
        if "lighting" in sp and lkey in sp:              # with Option 1: the lights on these stairs (the extra over both alone)
            a = dict(label=cs.get("addon_label", "With Option 1: lights on these stairs"), spec=sp[lkey], against=sp["lighting"],
                     renders=pick(ctx, lpick, ro), renders_dir=ro)
            n = fill(ctx, cs.get("addon_note"), f"{bkey}.addon_note")
            if n:
                a["note"] = n
            o["addons"] = [a]
        blocks.append(o)
    rs = sp.get("roof_screens") or sp.get("roof")
    if rs is not None:
        cr = c.get("roof") or {}
        dw = roof_deck_work(ctx)
        o = dict(key="roof", number="Option 3", title=cr.get("title", "Louvered roof"), roof=0, roof_spec=rs, renders=pick(ctx, "roof", ro), renders_dir=ro,
                 note=cr.get("note", "The louvered roof has its own document with the details.") + (" " + dw["note"] if dw else ""))
        if dw:
            o["deck_work"] = dw
        b = fill(ctx, cr.get("blurb"), "roof.blurb")
        if b:
            o["blurb"] = b
        fl = fill_lines(ctx, cr.get("facts"), "roof.facts")    # the copy's scope lines (the engine's say "centres"); none -> the engine's
        if fl:
            o["facts"] = fl
        if ctx.urls.get("URL_ROOF"):
            o["url"], o["url_text"] = ctx.urls["URL_ROOF"], cr.get("url_text", "Open the louvered roof's document")
        elif customer:
            ctx.miss("URL_ROOF (the proposal's Option 3 has no link to the roof document)")
        if "roof_screens" in sp and f.get("screen_sides"):
            cs_ = c.get("screens") or {}
            sides = f["screen_sides"]
            lab = (cs_.get("label") or {}).get(sides) or (cs_.get("label") or {}).get("*") or "Motorized screens"
            tail = (cs_.get("note_tail") or {}).get(sides, "")
            note = " ".join(x for x in ((f.get("screen_words", "").strip() + ".") if f.get("screen_words") else "", fill(ctx, tail, "screens.note_tail") or "") if x)
            a = dict(label=lab, renders=pick(ctx, "screens", ro), renders_dir=ro)
            if SCREENS_PRICE is not None or ctx.screens_price is not None:
                a["price"] = float(SCREENS_PRICE if SCREENS_PRICE is not None else ctx.screens_price)    # the owner's number
            else:
                a["screens"] = True                          # the louvered engine's price for them (an ESTIMATE until the owner sets it)
            if note:
                a["note"] = note
            o["addons"] = [a]
        blocks.append(o)
    elif not ctx.draft:
        ctx.miss("Option 3 louvered roof (no roof spec)")
    return blocks


def _names(ctx):
    c = ctx.copy or {}
    return dict(proposal=c.get("name_proposal", f"Deck Replacement · {ADDRESS}"),
                internal=c.get("name_internal", f"{ADDRESS} · Deck Replacement · Centennial"),
                roof=c.get("name_roof", f"Louvered Roof · {ADDRESS}"),
                supplier=c.get("name_supplier", f"{ADDRESS} · Deck Replacement"),
                permit=c.get("name_permit", f"{ADDRESS} · Deck Replacement"))


def _sub(ctx, key):
    s = fill(ctx, (ctx.copy or {}).get(key), key) or fill(ctx, (ctx.copy or {}).get("sub_internal"), "sub_internal") or ""
    return ("DRAFT (placeholder numbers) · " + s) if ctx.draft else s


def _record(ctx, step, r, files_from=None):
    ctx.outputs[step] = dict(html=r.get("html"), pdf=r.get("pdf"), files=r.get("files") or {})
    return ctx.outputs[step]


def step_prices(ctx):
    """The numbers the proposal prints, made the same way (page._option_blocks), for the hub and the summary."""
    from decktakeoff import run
    from decktakeoff import page as PG
    t, flags, p = ctx.base_run
    blocks = option_blocks(ctx, customer=False)
    rows, total = [], (p.sell, p.retail, p.monthly)
    if blocks:
        ob = PG._option_blocks(ctx.specs["base"], t, p, blocks, KEY, ctx.RD, {})
        it = iter(ob["rows"])
        for b in blocks:
            lab, c_, f_, m_, sub, basis = next(it)
            rows.append(dict(key=b["key"], label=lab, sell=c_, retail=f_, monthly=m_, sub=False, basis=basis))
            for ai, a in enumerate(b.get("addons") or [], 1):
                lab, c_, f_, m_, sub, basis = next(it)
                rows.append(dict(key=f"{b['key']}-a{ai}", label=lab, sell=c_, retail=f_, monthly=m_, sub=True, basis=basis))
        total = ob["total"]
    hub_key = {"lights": "O1", "stairs": "O2", "stairs-a1": "O2L", "stairs2b": "O2B", "stairs2b-a1": "O2BL", "roof": "O3", "roof-a1": "O3A"}
    lights_each = ctx.facts.get("light_each")
    each_ok = lights_each and lights_each != "0"
    short = {"lights": (f"${lights_each} a light installed (owner), {ctx.facts.get('lights_total', '?')} lights" if each_ok else "engine delta at the job margin"),
             "stairs": f"engine delta at the job margin ({p.gm:.0%})", "stairs2b": f"engine delta at the job margin ({p.gm:.0%})",
             "stairs-a1": (f"${lights_each} a light, {ctx.facts.get('add_total', '?')} more" if each_ok else "engine delta"),
             "stairs2b-a1": (f"${lights_each} a light, {ctx.facts.get('add_total_2b', '?')} more" if each_ok else "engine delta"),
             "roof": None, "roof-a1": None}
    # "every option": the two yard-stair layouts are one or the other, so each total takes one of them (and its lights)
    from decktakeoff.pricing import _monthly
    alts = [bk for _sk, bk, *_rest in STAIR_OPTIONS if any(r["key"] == bk for r in rows)]
    def total_for(choice):
        inc = [r for r in rows if r["key"].split("-a")[0] not in set(alts) - {choice}]
        f_ = p.retail + sum(r["retail"] for r in inc)
        return p.sell + sum(r["sell"] for r in inc), f_, _monthly(f_)
    page_total = total
    totals = {bk: total_for(bk) for bk in alts}
    total = totals.get("stairs") or (totals[alts[0]] if alts else page_total)
    if len(alts) > 1 and abs(page_total[0] - total[0]) > 0.5:
        ctx.warn(f"the proposal's 'The deck with every option' line adds both yard-stair layouts ({money(page_total[0])}); with Option 2 it is "
                 f"{money(totals['stairs'][0])}, with Option 2B {money(totals['stairs2b'][0])} — page.py needs a one-or-the-other rule "
                 "(proposals agent); the hub carries the two right totals")
    H = {"{{BASE_SELL}}": money(p.sell), "{{BASE_RETAIL}}": money(p.retail), "{{BASE_MONTHLY}}": money(p.monthly),
         "{{BASE_BASIS}}": f"engine: cost + {p.gm:.0%} margin" + (f" ({p.gm:.1%})" if abs(p.gm - round(p.gm, 2)) > 0.0005 else ""),
         "{{TOTAL_SELL}}": money(total[0]), "{{TOTAL_RETAIL}}": money(total[1]), "{{TOTAL_MONTHLY}}": money(total[2])}
    if "stairs2b" in totals:
        t2b = totals["stairs2b"]
        H.update({"{{TOTAL2B_SELL}}": money(t2b[0]), "{{TOTAL2B_RETAIL}}": money(t2b[1]), "{{TOTAL2B_MONTHLY}}": money(t2b[2])})
    est = []
    for r in rows:
        k = hub_key.get(r["key"])
        if not k:
            continue
        H[f"{{{{{k}_SELL}}}}"], H[f"{{{{{k}_RETAIL}}}}"], H[f"{{{{{k}_MONTHLY}}}}"] = signed(r["sell"]), signed(r["retail"]), signed(r["monthly"])
        b = short.get(r["key"])
        if r["key"] == "roof":
            ff = ctx.facts
            b = (f"owner: ${ff['roof_rate']}/SF x {ff['roof_sf']} SF, sold on its own" if ff.get("roof_rate") and ff.get("roof_sf")
                 else r["basis"].split(", sold on its own")[0])
            H["{{ROOF_SELL}}"], H["{{ROOF_RETAIL}}"], H["{{ROOF_MONTHLY}}"] = money(r["sell"]), money(r["retail"]), money(r["monthly"])
        if r["key"] == "roof-a1":
            b = "ESTIMATE — not set by the owner (the louvered engine's placeholder rate)" if "ESTIMATE" in r["basis"] else "owner-set"
        if "ESTIMATE" in r["basis"]:
            est.append(r["label"])
        H[f"{{{{{k}_BASIS}}}}"] = b or r["basis"]
    f = ctx.facts
    for k, v in (("SF", f.get("sf")), ("LOWER_H", f.get("lower_h")), ("UPPER_H", f.get("upper_h")), ("STEP_IN", f.get("step_in")),
                 ("COLUMNS", f.get("columns")), ("PIERS", f.get("piers")), ("FOOTINGS", f.get("footings_hub")), ("COLUMN_BASES", f.get("column_bases_internal")), ("RAIL_LF", f.get("rail_lf")),
                 ("LIGHTS_TOTAL", f.get("lights_total")),
                 ("SCREEN_SIDES", {"front+right": "the front and the right end", "front+left+right": "the front and both ends",
                                   "front": "the front"}.get(f.get("screen_sides", ""), f.get("screen_sides", "")))):
        if v:
            H[f"{{{{{k}}}}}"] = str(v)
    # cross-check: the everything-on spec (the 3D page's) against the proposal's "deck with every option"
    chk = ""
    if "all" in ctx.specs:
        try:
            _, _, pa = run(ctx.specs["all"])
            roof_rows = [r for r in rows if r["key"].startswith("roof")]
            deck_opts = sum(r["sell"] for r in rows if not r["key"].startswith(("roof", "stairs2b")))
            chk = (f"everything-on spec: deck {money(pa.sell)} vs base + Options 1 + 2 + add-on {money(p.sell + deck_opts)} "
                   f"(diff {signed(pa.sell - p.sell - deck_opts)}: the roof posts in place of rail posts / lights); "
                   f"+ roof and screens {money(sum(r['sell'] for r in roof_rows))}")
        except Exception as e:
            chk = f"everything-on cross-check failed: {e}"
    data = dict(built=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), spec_dir=str(ctx.spec_dir), draft=ctx.draft,
                specs={k: (dict(path=v, mtime=datetime.fromtimestamp(Path(v).stat().st_mtime, timezone.utc).strftime("%d %b %H:%M UTC")) if "/" in str(v) else v)
                       for k, v in ctx.src.items()},
                base=dict(sell=round(p.sell), retail=round(p.retail), monthly=round(p.monthly, 2), gm=p.gm, sf=float(ctx.base_run[0].layout.deck_sf)),
                options=[dict(r, sell=round(r["sell"]), retail=round(r["retail"]), monthly=round(r["monthly"], 2)) for r in rows],
                total=dict(sell=round(total[0]), retail=round(total[1]), monthly=round(total[2], 2)),
                totals={bk: dict(sell=round(v[0]), retail=round(v[1]), monthly=round(v[2], 2)) for bk, v in totals.items()},
                page_total=dict(sell=round(page_total[0]), retail=round(page_total[1]), monthly=round(page_total[2], 2)),
                estimates=est, cross_check=chk, facts={k: v for k, v in ctx.facts.items()}, hub=H)
    PUB.mkdir(parents=True, exist_ok=True)
    json.dump(data, open(PUB / "prices.json", "w"), indent=1, default=str)
    ctx.prices = data
    log(f"  base {money(p.sell)} / {money(p.retail)} / {money(p.monthly)}/mo")
    for r in rows:
        log(f"  {'   ' if r['sub'] else ''}{r['label']}: {signed(r['sell'])} / {signed(r['retail'])} / {signed(r['monthly'])}/mo   [{r['basis'][:110]}]")
    for bk, v in (totals.items() if totals else [("", total)]):
        log(f"  the deck with every option{' (with ' + dict((b_, n_) for _s, b_, n_, *_r in STAIR_OPTIONS).get(bk, bk) + ')' if bk else ''}: "
            f"{money(v[0])} / {money(v[1])} / {money(v[2])}/mo")
    if chk:
        log("  " + chk)
    if est:
        ctx.warn("ESTIMATE in the prices (owner has not set it): " + "; ".join(est))
    return f"publish/prices.json · base {money(p.sell)} · every option {money(total[0])}"


def step_internal(ctx):
    from decktakeoff.page import render_page
    n = _names(ctx)
    r = render_page(ctx.specs["base"], str(ctx.OUT), mode="internal", key=KEY, name=n["internal"], sub=_sub(ctx, "sub_internal"), render=False,
                    renders_dir=str(ctx.RD), pdf=ctx.pdf, date_line=ctx.date_line, options=option_blocks(ctx, customer=False) or None)
    _record(ctx, "internal", r)
    return f"{r['html']}" + (f" + {Path(r['pdf']).name}" if r.get("pdf") else "") + f" · {money(r['pricing'].sell)}"


def step_roof(ctx):
    from decktakeoff.page import render_page
    rs = ctx.specs.get("roof_screens") or ctx.specs.get("roof")
    if rs is None:
        return "SKIP: no roof spec (fillmore_centennial_roof_screens.json / _roof.json)"
    c = ctx.copy or {}
    cd = c.get("roof_doc") or {}
    n = _names(ctx)
    hero = (pick(ctx, "roof_hero", ctx.RR) or [None])[0]
    have = {q.stem for q in ctx.RR.glob("*.jpg")}
    rn = [f"roof-{st_}-{tm}-{v}" for tm in ROOF_TIMES for v in ROOF_DOC_VIEWS for st_ in ROOF_DOC_STATES] + [
        m for pat in ROOF_DOC_EXTRA for m in (sorted(fnmatch.filter(have, pat)) if "*" in pat else [pat])]
    rn = [x for x in rn if x in have] or sorted(x for x in have if x.startswith("roof-"))
    sides = ctx.facts.get("screen_sides", "")
    addon = dict(renders=rn or None,
                 screens=dict(label=(cd.get("screens_label") or {}).get(sides) or (cd.get("screens_label") or {}).get("*") or "Motorized screens",
                              renders=pick(ctx, "screens_doc", ctx.RR) or None, renders_dir=str(ctx.RR)))
    bl = fill(ctx, (cd.get("screens_blurb") or {}).get(sides), "roof_doc.screens_blurb")
    if bl:
        addon["screens"]["blurb"] = bl
    if SCREENS_PRICE is not None or ctx.screens_price is not None:
        addon["screens"]["price"] = float(SCREENS_PRICE if SCREENS_PRICE is not None else ctx.screens_price)
    if cd.get("facts"):                                  # over proposal_look.LOUVER_FACTS, section by section
        fx = {k: fill_lines(ctx, v, f"roof_doc.facts.{k}") for k, v in cd["facts"].items() if isinstance(v, list)}
        addon["facts"] = {k: v for k, v in fx.items() if v}
    for k in ("schedule", "exclusions", "terms"):
        lines = fill_lines(ctx, cd.get(k), f"roof_doc.{k}")
        if lines:
            addon[k] = lines
    dw = roof_deck_work(ctx)
    if dw:
        addon["deck_work"] = dict(price=dw["price"], label="The deck structure for the roof: a column on a 30\" caisson under each roof post, blocking and ties")
    dn = fill(ctx, cd.get("deck_note"), "roof_doc.deck_note")
    if dn:
        addon["deck_note"] = dn
    url3d = ctx.urls.get("URL_3D")
    if not url3d:
        ctx.miss("URL_3D (the roof document has no link to the 3D page)")
    r = render_page(rs, str(ctx.OUT_ROOF), mode="addon", key=f"{KEY}r", name=n["roof"], hero=hero or "hero", renders_dir=str(ctx.RR), pdf=ctx.pdf,
                    date_line=ctx.date_line, roof=0, lede=fill(ctx, cd.get("lede"), "roof_doc.lede") or "",
                    viewer_url=url3d or "", viewer_note=cd.get("viewer_note"), addon=addon)
    _record(ctx, "roof", r)
    pr = r.get("pricing") or {}
    sc = pr.get("screens") or {}
    return (f"{r['html']}" + (f" + {Path(r['pdf']).name}" if r.get("pdf") else "") + f" · roof {money(pr.get('roof', {}).get('sell', 0))}"
            + (f" · screens {money(sc.get('sell', 0))}{' (ESTIMATE)' if sc.get('estimate') else ''}" if sc else "")
            + f" · hero {hero or 'none'} · {len(rn)} roof stills")


def step_proposal(ctx):
    from decktakeoff.page import render_page
    n = _names(ctx)
    url3d = ctx.urls.get("URL_3D")
    if not url3d:
        ctx.miss("URL_3D (the proposal has no link to the 3D page)")
    blocks = option_blocks(ctx, customer=True)
    r = render_page(ctx.specs["base"], str(ctx.OUT_PROPOSAL), mode="proposal", key=KEY, name=n["proposal"], hero=HERO_SLOT, render=False,
                    renders_dir=str(ctx.RD), pdf=ctx.pdf, date_line=ctx.date_line, lede=fill(ctx, (ctx.copy or {}).get("lede"), "lede") or "",
                    options=blocks or None, viewer_url=url3d or "", viewer_note=(ctx.copy or {}).get("viewer_note"))
    _record(ctx, "proposal", r)
    return f"{r['html']}" + (f" + {Path(r['pdf']).name}" if r.get("pdf") else "") + f" · base {money(r['pricing'].sell)} · {len(blocks)} option blocks"


def step_supplier(ctx, which="supplier"):
    from decktakeoff.page import render_page
    from decktakeoff.spec import DeckSpec
    n = _names(ctx)
    spec, out, name = ctx.specs["base"], ctx.OUT_DD, n["supplier"]
    if which == "supplier_opts":
        if "lighting_yardstair" not in ctx.dicts:
            return "SKIP: needs the lighting and yard-stair specs"
        spec, out, name = DeckSpec.from_dict(ctx.dicts["lighting_yardstair"]), ctx.OUT_DD_OPTS, name + " · with Options 1 + 2"
    r = render_page(spec, str(out), mode="supplier", key=KEY, name=name, sub=_sub(ctx, "sub_supplier"), render=False,
                    renders_dir=str(ctx.RD), pdf=ctx.pdf, date_line=ctx.date_line)
    _record(ctx, which, r)
    return f"{r['html']}" + (f" + {Path(r['pdf']).name}" if r.get("pdf") else "")


def step_cost(ctx):
    from decktakeoff.page import render_page
    n = _names(ctx)
    r = render_page(ctx.specs["base"], str(ctx.OUT_COST), mode="cost", key=KEY, name=n["internal"], sub=_sub(ctx, "sub_internal"), render=False,
                    renders_dir=str(ctx.RD), pdf=ctx.pdf, date_line=ctx.date_line, options=option_blocks(ctx, customer=False) or None)
    _record(ctx, "cost", r)
    return f"{r['html']}" + (f" + {Path(r['pdf']).name}" if r.get("pdf") else "") + f" · {money(r['pricing'].sell)}"


def step_permit(ctx):
    from decktakeoff.page import render_permit_set
    n = _names(ctx)
    caps = jload(ctx.RD / "captions.json", {}) or {}
    want = [("corner", "From the yard"), ("yard", "From the yard, the upper level"), ("iso2", "From above, the arm end"), ("iso", "From above, the right end"),
            ("exploded", "Exploded — every layer"), ("exploded-corner", "Exploded — from the front corner"), ("frame-iso2", "The frame — decking off"),
            ("structure-underiso", "Posts and beams on the footings")]
    views = []
    for k, c_ in want:                           # finished views: only the furniture-free stills (never the proposal's)
        src = (ctx.RP / f"{k}.jpg") if k in PERMIT_FINISHED else (ctx.RD / f"{k}.jpg")
        if src.exists():
            views.append((c_ if k in PERMIT_FINISHED else caps.get(k, c_), str(src)))
        elif k in PERMIT_FINISHED:
            ctx.miss(f"permit view {k} without furniture ({ctx.RP.name}/{k}.jpg: run the 'stills' step)")
    title = (ctx.copy or {}).get("permit_title", "Two-level deck")
    r = render_permit_set([dict(spec=ctx.specs["base"], title=title)], str(ctx.OUT_PERMIT), key=f"{KEY}k", name=n["permit"],
                          sub=_sub(ctx, "sub_permit"), pdf=ctx.pdf, date_line=ctx.date_line, renders={title: views} if views else None)
    _record(ctx, "permit", r)
    return f"{r['html']}" + (f" + {Path(r['pdf']).name}" if r.get("pdf") else "") + f" · {r['sheets']} sheets, {len(views)} 3D views"


def step_dims(ctx):
    """The A-100 dimension plan alone, one Letter-landscape page (Prentice's dims_pdf.py, for a composite: whole-deck A-100)."""
    from decktakeoff.drawings import all_sheets, composite_sheets
    from decktakeoff.page import FONT
    t, flags, p = ctx.base_run
    L = t.layout
    sheets = composite_sheets(L, t, flags, None, customer=True, only={"A-100"}) if hasattr(L, "parts") else all_sheets(L, t, flags, None, customer=True)
    svg = {n_: v for n_, _, v in sheets}.get("A-100")
    if not svg:
        raise RuntimeError("the engine drew no A-100")
    out = ctx.OUT_DIMS
    out.mkdir(parents=True, exist_ok=True)
    html = ("<!doctype html><html><head><meta charset='utf-8'>" + FONT + "<style>@page{size:11in 8.5in;margin:0.25in}"
            "html,body{margin:0;padding:0;background:#fff}svg{width:10.5in;height:7.35in;display:block;margin-top:0.3in}</style></head><body>" + svg + "</body></html>")
    (out / "_a100.html").write_text(html)
    (out / "A-100.svg").write_text(svg)
    pdf = out / f"{ADDRESS} - Dimension Plan (inches).pdf"
    if ctx.pdf:
        from decktakeoff.render import _chromium
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
            pg = b.new_page()
            pg.goto("file://" + str(out / "_a100.html")); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1500)
            pg.pdf(path=str(pdf), width="11in", height="8.5in", print_background=True, prefer_css_page_size=True)
            b.close()
    ctx.outputs["dims"] = dict(html=str(out / "_a100.html"), pdf=str(pdf) if pdf.exists() else None, files={})
    return str(pdf if pdf.exists() else out / "A-100.svg")


def _pdf_check(path, customer):
    out = {}
    try:
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=60).stdout
        m = re.search(r"Pages:\s+(\d+)", info)
        out["pages"] = int(m.group(1)) if m else None
    except Exception:
        pass
    out["mb"] = round(Path(path).stat().st_size / 1e6, 2)
    if customer:
        try:
            txt = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, timeout=120).stdout
            out["bad_words"] = sorted({w for w in BAD_IN_CUSTOMER_PDF if re.search(r"\b" + re.escape(w) + r"\b", txt)}
                                      | ({"$0"} if re.search(r"\$0(?![\d,.])", txt) else set()))   # a $0 price: an unset rate filled in
        except Exception:
            pass
    return out


def _title_of(html_path):
    try:
        m = re.search(r"<title>(.*?)</title>", Path(html_path).read_text(errors="ignore")[:20000], flags=re.S)
        import html as _h
        return _h.unescape(m.group(1)).strip() if m else ""
    except Exception:
        return ""


def step_deliver(ctx):
    D = ctx.DELIVER
    if D.exists():
        shutil.rmtree(D)
    D.mkdir(parents=True)
    pre = "DRAFT - " if ctx.draft else ""
    docs, lines = [], []
    for step, attr, fname, hub_doc, url_key, icon in DELIVER:
        outdir = getattr(ctx, attr)
        src = outdir / (fname if step == "dims" else "page.pdf")
        html = (outdir / "_a100.html") if step == "dims" else (outdir / "page.html")
        if step == "supplier_opts" and not src.exists():
            continue
        entry = dict(key=step, title=_title_of(html) if html.exists() else "", html=str(html) if html.exists() and step != "dims" else None,
                     files=jload(outdir / "files.json", {}) if step != "dims" else {}, hub_doc=hub_doc, url_key=url_key,
                     url=ctx.urls.get(url_key or "", ""), icon=icon, description=DESCRIPTIONS.get(step, ""), customer=step in CUSTOMER_DOCS)
        if not src.exists():
            ctx.miss(f"PDF for {step} ({src})")
            entry["pdf"] = None
        else:
            dst = D / (pre + fname)
            shutil.copy(src, dst)
            entry["pdf"] = str(dst)
            entry.update(_pdf_check(dst, step in CUSTOMER_DOCS))
            if entry.get("bad_words"):
                ctx.warn(f"{dst.name}: contains {entry['bad_words']} — check before it goes to the client")
            if entry["mb"] > 15:
                ctx.warn(f"{dst.name} is {entry['mb']} MB: over the 15 MB per-file limit for publishing it on the hub")
            age = (time.time() - src.stat().st_mtime) / 3600
            newest = max((Path(v).stat().st_mtime for v in ctx.src.values() if "/" in str(v) and Path(v).exists()), default=0)
            if src.stat().st_mtime < newest:
                ctx.warn(f"{dst.name}: built {datetime.fromtimestamp(src.stat().st_mtime, timezone.utc):%H:%M} UTC, before the spec files changed "
                         f"({datetime.fromtimestamp(newest, timezone.utc):%H:%M} UTC): rebuild its step")
            elif age > 2:
                ctx.warn(f"{dst.name}: copied from a PDF built {age:.1f} h ago (its step did not run this time)")
            lines.append(f"    {dst.name}  ({entry.get('pages', '?')} pages, {entry['mb']} MB)")
        if entry.get("html"):
            entry["files_mb"] = round(sum(Path(v).stat().st_size for v in entry["files"].values() if Path(v).exists()) / 1e6, 2)
        docs.append(entry)
    cards = sorted(F.glob(COLOR_CARD_GLOB), key=lambda q: q.stat().st_mtime)
    if cards:
        dst = D / (pre + (COLOR_CARD_NAME or cards[-1].name))
        shutil.copy(cards[-1], dst)
        docs.append(dict(key="color", title="color check", html=None, files={}, hub_doc="docs/fillmore-color-check.jpg", url_key=None, url="",
                         icon=None, customer=False, pdf=str(dst), mb=round(dst.stat().st_size / 1e6, 2)))
        lines.append(f"    {dst.name}  (from {cards[-1]})")
    else:
        ctx.miss(f"color check card ({F / COLOR_CARD_GLOB})")
    cs_pdf = S / "fillmore" / "colorstudy" / f"{ADDRESS} - Exterior Color Study.pdf"    # its own build: colorstudy/tools/run_photoreal.sh
    if cs_pdf.exists():
        dst = D / cs_pdf.name
        shutil.copy(cs_pdf, dst)
        docs.append(dict(key="colorstudy", title="Exterior color study", html=None, files={}, hub_doc="docs/fillmore-color-study.pdf", url_key="URL_COLORSTUDY",
                         url=ctx.urls.get("URL_COLORSTUDY", ""), icon=None, customer=True, pdf=str(dst), mb=round(dst.stat().st_size / 1e6, 2)))
        lines.append(f"    {dst.name}  (from {cs_pdf.parent})")
    else:
        ctx.miss(f"exterior color study PDF ({cs_pdf})")
    threed = ctx.OUT_3D / "fillmore_3d.html"
    docs.insert(0, dict(key="3d", title=_title_of(threed) if threed.exists() else "", html=str(threed) if threed.exists() else None, files={},
                        hub_doc=None, url_key="URL_3D", url=ctx.urls.get("URL_3D", ""), icon="cube", description=DESCRIPTIONS["3d"], customer=True, pdf=None))
    manifest = dict(
        built=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), deliver_dir=str(D), draft=ctx.draft,
        publish_order=["publish 3d -> put its link in urls.json as URL_3D; then: build_fillmore.py roof proposal deliver",
                       "publish roof -> URL_ROOF; then: build_fillmore.py proposal deliver", "publish proposal -> URL_PROPOSAL",
                       "publish internal -> URL_INTERNAL, cost -> URL_COST, supplier -> URL_DD, permit -> URL_PERMIT (supplier_opts -> URL_DD_OPTS if built)",
                       f"hub: python3 {PUB / 'hub_merge_fillmore.py'} then publish hub_index_new.html to {HUB_URL} with the files in hub_files.json"],
        how=("Each document: Artifact publish file_path=<html>, files=<files> (r/... -> the stills), icon, a one-line description; "
             "on a re-publish pass url=<its URL>. Put each URL in publish/urls.json under url_key."),
        documents=docs, hub=dict(url=HUB_URL, merge=str(PUB / "hub_merge_fillmore.py"), section=str(PUB / "fillmore_section.html")),
        prices=({k: getattr(ctx, "prices", {}).get(k) for k in ("base", "options", "total", "totals", "estimates")} if getattr(ctx, "prices", None) else
                "run the prices step"))
    json.dump(manifest, open(PUB / "manifest.json", "w"), indent=1)
    log("\n".join(lines))
    return f"{len(lines)} PDFs in {D} · publish/manifest.json"


# ============================================================================ main
def main(argv):
    global LOG
    opts, steps = parse_args(argv)
    ctx = Ctx()
    paths(ctx, opts)
    PUB.mkdir(parents=True, exist_ok=True)
    LOG = open(PUB / "build.log", "a")
    t_all = time.time()
    log(f"\n=== {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC build_fillmore.py {' '.join(argv)}")
    log(f"  steps: {' '.join(steps)}\n  spec dir: {ctx.spec_dir}\n  renders: {ctx.render_dir}\n  out: {ctx.out_root}   pdf: {ctx.pdf}")
    os.chdir(REPO)
    import_engine()
    load_specs(ctx)
    load_copy(ctx)
    load_urls(ctx)
    log("  urls: " + (", ".join(sorted(ctx.urls)) or "none yet (publish/urls.json)"))
    engine_facts(ctx)
    fns = dict(stills=step_stills, optstills=step_optstills, combine=step_combine, prices=step_prices, internal=step_internal, roof=step_roof,
               proposal=step_proposal, supplier=step_supplier, cost=step_cost, permit=step_permit, dims=step_dims, deliver=step_deliver,
               supplier_opts=lambda c: step_supplier(c, "supplier_opts"))
    fns["3d"] = step_3d
    for st in steps:
        t0 = time.time()
        log(f"\n--- {st}")
        try:
            note = fns[st](ctx)
            ok = "skip" if str(note).startswith("SKIP") else "ok"
        except Exception as e:
            ok, note = "FAIL", f"{type(e).__name__}: {e}"
            log(traceback.format_exc())
        dt = time.time() - t0
        ctx.status.append((st, ok, note, round(dt, 1)))
        log(f"  [{ok}] {note}  ({dt:.0f}s)")
    # ---- the summary
    log("\n=== summary")
    for st, ok, note, dt in ctx.status:
        log(f"  {ok:5s} {st:10s} {dt:6.0f}s  {note}")
    if ctx.missing:
        log("\n  missing / skipped:")
        for m in ctx.missing:
            log(f"    - {m}")
    if ctx.warnings:
        log("\n  warnings:")
        for w in ctx.warnings:
            log(f"    - {w}")
    if ctx.used:
        log("\n  renders used: " + "; ".join(f"{k}: {', '.join(v) or 'none'}" for k, v in ctx.used.items()))
    log(f"\n  total {time.time() - t_all:.0f}s · log {PUB / 'build.log'}")
    json.dump(dict(built=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), argv=argv, steps=ctx.status, missing=ctx.missing,
                   warnings=ctx.warnings, renders_used=ctx.used, outputs=ctx.outputs, draft=ctx.draft),
              open(PUB / "build_status.json", "w"), indent=1, default=str)
    return 1 if any(ok == "FAIL" for _, ok, _, _ in ctx.status) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
