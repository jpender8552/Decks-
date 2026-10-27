"""The interactive 3D options page: ONE self-contained HTML file (three.js r128 inlined, no network, phone + desktop) that
shows a job's base bid and its options on the real house and yard — toggles that add each option, a time-of-day slider
with the real sun at the address (sky, shadows, the shade under a louvered roof), the louvers turning and stopping at any
angle, the roof's screens running up and down, and the lights glowing at night. It is the finished deck in its yard: no
framing layers, no exploded view, no build steps (decktakeoff.viewer is the technical viewer).

    from decktakeoff.configurator import build_configurator
    build_configurator(base_spec, {"stairs": stair_spec, "lights": lights_spec, "roof": roof_spec, "screens": screens_spec},
                       "out/fillmore_3d.html", title="7303 S Fillmore Cir")

How the options become toggles (exact, no hand tagging needed): every option is a spec (the base plus that option). Its
change against the base (against the base plus its prerequisites, for "screens": the roof) is a JSON patch; the page's
scenes are built for EVERY valid combination of options (base, +stairs, +lights, +stairs+lights, ...) with
composite.build_composite + scene.build_scene, and every box carries a bit mask of the combinations it appears in. So a
box an option adds shows only with it, a box an option replaces (the rail posts a roof post takes over, the rail
sections a stair opening cuts) hides with it, and the lights on the yard stair show only with both options on. The
"option:<label>" layers the engine puts on option boxes (and the lighting / louvered layers) are cross-checked against
the masks and reported in the stats. Given a single all-options spec instead (options=None), the groups come from those
layers alone (boxes an option replaces then stay in the base view).

Live parts the page draws itself from scene.meta["louvered_roofs"] (decktakeoff.louvered.descriptors): the blades (one
instanced mesh per roof, each blade turning about its own long axis through its pivot: a section point (u, v) sits at
pivot + (u cos a - v sin a) across + (u sin a + v cos a) up) and the screens (fabric + bottom bar from the cassette
down to the drop). Their static boxes (kinds "lvblade", "lvscreen") are left out of the merged meshes.

The sun: scene.sun_vector's NOAA approximation, ported to the page, with the site's UTC offset following Mountain DST
like cycles.sun_at (a -6 / -7 offset is -6 from the 2nd Sunday of March to the 1st Sunday of November) — the page and
the Cycles renders put the sun in the same place for the same local date and time. The page opens at site.sun_when.

Lights: every LED lens (material keys led_riser / led_cap, or any material carrying an "emission" / "emit" colour, like
the roof's LED strip) glows from dusk (the photocell) and lights its surroundings through a small shader add-on in every
material (a riser light is a spot out of the riser 50 deg down at the tread below, as in the Cycles pass; a post-cap
light lights down and out; an LED strip lights the deck under it) — no per-light three.js lights, so it stays fast on a
phone. The house windows glow warm after dark; coach lanterns light their doors.

Speed: boxes merge by material and option mask into a few dozen meshes (vertex-coloured board tones, world-mapped
textures), the blades are instanced, the shadow map fits the deck and the shadows it throws, and the page renders only
when something changes.

URL parameters (also how the QA stills are taken): opts=stairs,lights|all|none, date=YYYY-MM-DD|summer|equinox|winter,
t=HH:MM (local clock), louver=<deg>, screens=<0-100>|front:100,left:0, view=<key>, ui=0 (no panel), still=1."""
from __future__ import annotations

import copy
import html as _html
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

OPTION_LABELS = {"stairs": "Stairs to the yard", "lights": "Lighting", "roof": "Louvered roof", "screens": "Roof screens"}
OPTION_SHORT = {"stairs": "Yard stairs", "lights": "Lighting", "roof": "Louvered roof", "screens": "Screens"}
REQUIRES = {"screens": ["roof"]}
LED_KEYS = ("led_riser", "led_cap")
LIVE_KINDS = {"lvblade", "lvscreen"}                     # drawn live by the page (the blades turn, the screens run)
NO_CAST_KINDS = {"ground", "gravel", "concrete_slab", "concrete_joint", "water", "lawn", "mulch", "soil", "groundcover"}
ROLE_NOCAST, ROLE_GLASS, ROLE_LED, ROLE_LANTERN, ROLE_DOUBLE, ROLE_TREE = 1, 2, 4, 8, 16, 32
SHAPES = {"box": 0, "cyl": 1, "sphere": 2, "cone": 3, "mesh": 4}
AXES = {"y": 0, "x": 1, "z": 2}
GLASS_MATS = {"hglass", "glass", "nglass"}
_DEL = "\x00delete"


# ================================================================== spec patches
def _load(spec) -> dict:
    """A DeckSpec, a dict or a path -> a normalised spec dict (DeckSpec round trip, so defaults never read as changes)."""
    from .spec import DeckSpec
    if isinstance(spec, (str, Path)):
        spec = json.loads(Path(spec).read_text())
    if isinstance(spec, dict):
        spec = DeckSpec.from_dict(copy.deepcopy(spec))
    return spec.to_dict()


def _diff(a, b, path: tuple = ()) -> List[Tuple[tuple, object]]:
    """The patch [(path, value)] that turns a into b: dicts by key, equal-length lists by index, anything else whole."""
    if isinstance(a, dict) and isinstance(b, dict):
        ops: List[Tuple[tuple, object]] = []
        for k in b:
            ops += [(path + (k,), copy.deepcopy(b[k]))] if k not in a else _diff(a[k], b[k], path + (k,))
        ops += [(path + (k,), _DEL) for k in a if k not in b]
        return ops
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [op for i, (x, y) in enumerate(zip(a, b)) for op in _diff(x, y, path + (i,))]
    return [] if a == b else [(path, copy.deepcopy(b))]


def _apply(d: dict, ops) -> dict:
    d = copy.deepcopy(d)
    for path, v in ops:
        cur = d
        for k in path[:-1]:
            if isinstance(cur, dict) and k not in cur:
                cur[k] = {}
            cur = cur[k]
        if v == _DEL:
            if isinstance(cur, dict):
                cur.pop(path[-1], None)
        else:
            cur[path[-1]] = copy.deepcopy(v)
    return d


def _path_str(p: tuple) -> str:
    return "".join(f"[{k}]" if isinstance(k, int) else (f".{k}" if i else str(k)) for i, k in enumerate(p))


def _scene(d: dict):
    """(spec, layout, scene) of a spec dict: a composite job through build_composite, else the ordinary takeoff."""
    from .scene import build_scene
    from .spec import DeckSpec
    spec = DeckSpec.from_dict(copy.deepcopy(d))
    if getattr(spec.geometry, "parts", None):
        from .composite import build_composite
        L = build_composite(spec)[0].layout
    else:
        from .takeoff import build_takeoff
        L = build_takeoff(spec).layout
    return spec, L, build_scene(L)


# ================================================================== boxes
def _key(b) -> tuple:
    r = lambda v: round(float(v), 3)
    k = (b.kind, b.mat, b.shape, r(b.x0), r(b.x1), r(b.y0), r(b.y1), r(b.z0), r(b.z1), round(float(b.rot or 0.0), 4), b.rot_axis if b.rot else "")
    if b.shape == "mesh" and b.pts:
        k += (tuple(r(v) for q in b.pts for v in q),)
    return k


def _emit_hex(md: dict) -> str:
    for k in ("emission", "emit", "emissive", "glow"):
        v = md.get(k)
        if isinstance(v, str) and v.startswith("#"):
            return v
    return ""


def _role(b, mats: dict) -> int:
    md = mats.get(b.mat, {})
    tag = (b.tag or "").lower()
    r = 0
    if b.kind in NO_CAST_KINDS or (b.shape == "mesh" and b.kind == "ground"):
        r |= ROLE_NOCAST
    if b.mat in GLASS_MATS and "lantern" not in tag:
        r |= ROLE_GLASS
    if b.mat in LED_KEYS or _emit_hex(md):
        r |= ROLE_LED
    if "coach lantern" in tag:
        r |= ROLE_LANTERN
    if b.shape == "mesh":
        r |= ROLE_DOUBLE
    if b.kind == "tree":                 # the yard's trees: the page can hide them (the Trees chip) and fades them near the camera
        r |= ROLE_TREE
    return r


def _layer_option(b) -> str:
    """The option an engine layer / tag names: "option:<label>" layers, the lighting option's tags, the louvered layer."""
    lay = getattr(b, "layer", "") or ""
    tag = (b.tag or "")
    if lay.startswith("option:"):
        return lay[len("option:"):].strip()
    if "Lighting option:" in tag:
        return "Lighting"
    if lay == "louvered":
        return "Roof screens" if ("screen (" in tag or b.kind in ("lvcassette", "lvtrack", "lvscreen")) else "Louvered roof"
    return ""


# ================================================================== fixtures (the page's virtual lights)
FX_SPOT, FX_CAP, FX_LINE = 0, 1, 2


def _fixtures(entries, mats: dict) -> List[list]:
    """[x, y, z, ax, ay, az, kind, gain, half, mask] per light, plan feet. Riser lights: a spot out of the riser (the side
    the tread below lies on) 50 deg down, as cycles.add_fixture_lights; post-cap lights: a down-and-out lantern at the lens;
    any other emitter (the roof's LED strip): a line light along its long side, facing down; coach lanterns: a lantern
    just in front of the glass."""
    treads = [b for b, _m in entries if b.kind == "tread"]
    out = []
    for b, mask in entries:
        md = mats.get(b.mat, {})
        tag = (b.tag or "").lower()
        lantern = "coach lantern" in tag
        if not (b.mat in LED_KEYS or _emit_hex(md) or lantern):
            continue
        cx, cy, cz = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2
        hx, hy, hz = (b.x1 - b.x0) / 2, (b.y1 - b.y0) / 2, (b.z1 - b.z0) / 2
        if lantern:
            out.append([cx, b.y1 + 0.3, cz - 0.1, 0, 0, -1, FX_CAP, 2.2, 0.0, mask])
            continue
        what = f"{b.mat} {b.kind} {tag}"
        if b.mat == "led_cap" or ("cap" in what and b.mat != "led_riser") or "post" in what:
            out.append([cx, cy, cz, 0, 0, -1, FX_CAP, 1.0, 0.0, mask])
            continue
        if b.mat == "led_riser" or "riser" in what or "step" in what:
            ux, uy, h = (1.0, 0.0, hx) if hx <= hy else (0.0, 1.0, hy)
            below = [t for t in treads if cz - 1.3 <= t.z1 <= cz + 0.05]
            above = [t for t in treads if t.z1 > cz + 0.05]
            tc = lambda t: ((t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2)
            sgn = 1.0
            if below:
                t = min(below, key=lambda t: math.hypot(tc(t)[0] - cx, tc(t)[1] - cy))
                sgn = 1.0 if (tc(t)[0] - cx) * ux + (tc(t)[1] - cy) * uy >= 0 else -1.0
            elif above:
                t = min(above, key=lambda t: math.hypot(tc(t)[0] - cx, tc(t)[1] - cy))
                sgn = -1.0 if (tc(t)[0] - cx) * ux + (tc(t)[1] - cy) * uy >= 0 else 1.0
            ox, oy = ux * sgn, uy * sgn
            c50, s50 = math.cos(math.radians(50)), math.sin(math.radians(50))
            out.append([cx + ox * (h + 0.03), cy + oy * (h + 0.03), cz, ox * c50, oy * c50, -s50, FX_SPOT, 1.0, 0.0, mask])
            continue
        # an LED strip / any other emitter: a line light along its long side, on its underside, facing down
        if hx >= hy:
            out.append([cx, cy, b.z0 - 0.02, 1, 0, 0, FX_LINE, 1.0, hx, mask])
        else:
            out.append([cx, cy, b.z0 - 0.02, 0, 1, 0, FX_LINE, 1.0, hy, mask])
    out.sort(key=lambda f: f[0])                   # along x: the page's light loop skips / stops by x
    return [[round(v, 3) if isinstance(v, float) else v for v in f] for f in out]


# ================================================================== camera presets
def _parts_of(L) -> List[dict]:
    IN = 1 / 12.0
    out = []
    for p in (getattr(L, "parts", None) or []):
        boxes = [p.placement.box(z.x0 * IN, (z.x0 + z.W) * IN, z.wall_y * IN, (z.wall_y + z.D) * IN) for z in p.layout.zones]
        out.append(dict(name=p.name, x0=min(b[0] for b in boxes), x1=max(b[1] for b in boxes), y0=min(b[2] for b in boxes),
                        y1=max(b[3] for b in boxes), top=p.spec.geometry.height_in * IN))
    if not out:
        zs = L.zones
        out.append(dict(name="Deck", x0=min(z.x0 for z in zs) * IN, x1=max(z.x0 + z.W for z in zs) * IN, y0=min(z.wall_y for z in zs) * IN,
                        y1=max(z.wall_y + z.D for z in zs) * IN, top=L.spec.geometry.height_in * IN))
    return out


def _occluders(boxes) -> list:
    """Axis-aligned bounds of what blocks a view in the yard: tree crowns and trunks (shrunk a little: crowns are not solid
    boxes), neighbouring houses and walls of the site layer."""
    out = []
    for b in boxes:
        if (b.layer or "") != "site" or b.kind not in ("tree", "house", "wall"):
            continue
        k = 0.18 if b.kind == "tree" and b.shape in ("sphere", "cone", "mesh") else 0.0
        dx, dy, dz = (b.x1 - b.x0) * k / 2, (b.y1 - b.y0) * k / 2, (b.z1 - b.z0) * k / 2
        out.append((b.x0 + dx, b.x1 - dx, b.y0 + dy, b.y1 - dy, b.z0 + dz, b.z1 - dz))
    return out


def _clear(pos, targets, occ) -> float:
    """The share of the sight lines from pos to the targets that no occluder cuts (slab test, numpy)."""
    if not occ:
        return 1.0
    import numpy as np
    O = np.array(occ, dtype=float)                       # (n, 6): x0 x1 y0 y1 z0 z1
    lo, hi = O[:, [0, 2, 4]], O[:, [1, 3, 5]]
    p = np.array(pos, dtype=float)
    if np.any(np.all((p >= lo - 0.3) & (p <= hi + 0.3), axis=1)):
        return 0.0                                        # standing inside a crown / a house
    ok = 0
    for t in targets:
        d = np.array(t, dtype=float) - p
        inv = 1.0 / np.where(np.abs(d) < 1e-9, 1e-9, d)
        t0, t1 = (lo - p) * inv, (hi - p) * inv
        tn = np.max(np.minimum(t0, t1), axis=1)
        tf = np.min(np.maximum(t0, t1), axis=1)
        ok += not np.any((tn <= tf) & (tf > 0.02) & (tn < 0.97))
    return ok / max(1, len(targets))


def _views(parts: List[dict], roofs: List[dict], cams: Optional[dict], grade, occ=None) -> List[dict]:
    """Preset cameras (plan feet): Yard, Upper deck (under the roof when there is one), Lower deck, Aerial. A measured site's
    own camera stations (site_model.cameras) win: "yard", "roof_deck" / "upper_deck", "lower_deck", "high34" — they stand
    where a person can stand (inside the lot, clear of the trees); otherwise the stations are computed from the layout."""
    cams = cams or {}
    x0 = min(p["x0"] for p in parts); x1 = max(p["x1"] for p in parts)
    y0 = min(p["y0"] for p in parts); y1 = max(p["y1"] for p in parts)
    W = x1 - x0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    top = max(p["top"] for p in parts)
    mid_top = sum(p["top"] for p in parts) / len(parts)
    hi = max(parts, key=lambda p: p["top"])
    lo = min(parts, key=lambda p: p["top"])
    roof = next((r for r in roofs if r.get("frame")), None)

    occ = occ or []
    deck_pts = [(x0 + (x1 - x0) * i / 6.0, y, hi["top"] if x0 + (x1 - x0) * i / 6.0 >= hi["x0"] - 0.5 else lo["top"])
                for i in range(7) for y in (y1 - 0.5, (y0 + y1) / 2)]

    def station(key, label, *names):
        best = None
        for i, n in enumerate(names):                    # the first listed station with the clearest view of the deck
            c = cams.get(n)
            if c and c.get("pos") and c.get("at"):
                sc_ = _clear(c["pos"], deck_pts, occ) if key in ("yard", "aerial") else 1.0
                if best is None or sc_ > best[0] + 0.15:
                    best = (sc_, dict(key=key, label=label, pos=c["pos"], at=c["at"], fov=c.get("fov", 60), fixed=True, station=n))
        return best[1] if best else None
    views = []
    v = station("yard", "Yard", "yard_center", "yard", "yard_left", "dusk")
    if not v:
        d = max(36.0, min(90.0, W * 0.92))
        zg = grade(cx, y1 + d)
        v = dict(key="yard", label="Yard", pos=[cx + W * 0.05, y1 + d, zg + 5.6], at=[cx, cy, mid_top * 0.95], fov=44, fit=W + 16)
    views.append(v)
    up_label = "Upper deck" if len(parts) > 1 else ("Under the roof" if roof else "On the deck")
    v = station("upper", up_label, *(("roof_deck", "upper_deck", "upper_rail") if roof else ("upper_deck", "upper_rail")))
    if not v and roof:                       # under the roof: inside its outer corner, looking across the deck toward the house
        f = roof["frame"]
        zd = float(roof.get("z_deck") or hi["top"])
        rx0, rx1, ry0, ry1 = f["x0"], f["x1"], f["y0"], f["y1"]
        v = dict(key="upper", label=up_label, pos=[rx1 - 2.2, ry1 - 1.6, zd + 5.4], at=[rx0 + (rx1 - rx0) * 0.25, ry0 + (ry1 - ry0) * 0.35, zd + 3.4], fov=64)
    if not v:                                # stand at the part's end away from the deck's middle, near the front, look along it
        far = hi["x1"] if (hi["x0"] + hi["x1"]) / 2 >= cx else hi["x0"]
        nxt = hi["x0"] if far == hi["x1"] else hi["x1"]
        sg = -1 if far == hi["x1"] else 1
        v = dict(key="upper", label=up_label, pos=[far + sg * 2.5, hi["y1"] - 2.0, hi["top"] + 5.4], at=[nxt, (hi["y0"] + hi["y1"]) / 2, hi["top"] + 2.2], fov=60)
    views.append(v)
    if len(parts) > 1:
        v = station("lower", "Lower deck", "lower_deck")
        if not v:
            far = lo["x1"] if (lo["x0"] + lo["x1"]) / 2 >= cx else lo["x0"]
            sg = -1 if far == lo["x1"] else 1
            tgt_x = hi["x0"] + 6 if hi["x0"] >= lo["x1"] - 1 else hi["x1"] - 6
            v = dict(key="lower", label="Lower deck", pos=[far + sg * 2.5, lo["y1"] - 2.0, lo["top"] + 5.4], at=[tgt_x, (lo["y0"] + lo["y1"]) / 2, lo["top"] + 3.0], fov=60)
        views.append(v)
    # aerial: high over the yard, a little to the right of straight out, looking down ~62 deg at the whole deck (a tree crown
    # in the way is cut away by the page)
    at = [cx, cy - 1, mid_top * 0.5]
    R, e, a_ = max(70.0, W * 1.25), math.radians(62), math.radians(10)
    views.append(dict(key="aerial", label="Aerial", pos=[at[0] + R * math.cos(e) * math.sin(a_), at[1] + R * math.cos(e) * math.cos(a_), at[2] + R * math.sin(e)],
                      at=at, fov=40, fit=W + 14))
    return [dict(v, pos=[round(float(q), 2) for q in v["pos"]], at=[round(float(q), 2) for q in v["at"]]) for v in views]


# ================================================================== the page's data
def configurator_data(spec_base, options: Optional[Dict[str, object]] = None, *, labels: Optional[Dict[str, str]] = None,
                      requires: Optional[Dict[str, Sequence[str]]] = None, combos: Optional[Dict[str, object]] = None,
                      site: Optional[dict] = None, title: Optional[str] = None, default_on: Sequence[str] = (),
                      views: Optional[List[dict]] = None) -> Tuple[dict, dict]:
    """(data for the page, stats). See build_configurator."""
    base = _load(spec_base)
    options = dict(options or {})
    names = list(options)
    labels = dict(OPTION_LABELS, **(labels or {}))
    req = {k: [r for r in v if r in names] for k, v in dict(REQUIRES, **(requires or {})).items() if k in names}
    stats: dict = dict(warnings=[], deltas={}, groups={}, mode="specs" if names else "layers")
    # ---- each option's patch, against the base plus its prerequisites
    opt_dicts = {n: _load(options[n]) for n in names}
    patches: Dict[str, list] = {}
    for n in names:
        ref = base
        for r in req.get(n, []):
            ref = _apply(ref, patches.get(r) or _diff(base, opt_dicts[r]))
        ops = _diff(ref, opt_dicts[n])
        ops = [(p, v) for p, v in ops if p and p[0] not in ("job",)]
        patches[n] = ops
        stats["deltas"][n] = [_path_str(p) for p, _v in ops]
        if not ops:
            stats["warnings"].append(f"option {n}: its spec is the same as the base")
    # ---- every valid combination of options
    bits = {n: i for i, n in enumerate(names)}
    valid = []
    for c in range(1 << len(names)):
        on = [n for n in names if c >> bits[n] & 1]
        if all(all(r in on for r in req.get(n, [])) for n in on):
            valid.append(c)
    explicit = {}
    for k, v in (combos or {}).items():
        on = [s.strip() for s in k.replace(",", "+").split("+") if s.strip()]
        explicit[sum(1 << bits[n] for n in on if n in bits)] = _load(v)
    union: Dict[tuple, list] = {}
    mats: Dict[str, dict] = {}
    roofs: Dict[str, dict] = {}
    roof_mask: Dict[str, int] = {}
    screen_mask: Dict[Tuple[str, str], int] = {}
    meta0 = None
    spec0 = L0 = None
    for c in sorted(valid, key=lambda c: -bin(c).count("1")):      # all-on first: its boxes are the representatives
        if c in explicit:
            d = explicit[c]
        else:
            d = base
            for n in names:
                if c >> bits[n] & 1:
                    d = _apply(d, patches[n])
        spec, L, sc = _scene(d)
        if meta0 is None:
            meta0, spec0, L0 = sc.meta, spec, L
        for k, v in sc.materials.items():
            mats.setdefault(k, v)
        for b in sc.boxes:
            if b.kind in LIVE_KINDS:
                continue
            k = _key(b)
            if k in union:
                union[k][1] |= 1 << c
            else:
                union[k] = [b, 1 << c]
        for r in sc.meta.get("louvered_roofs") or []:
            nm = r.get("name", "roof")
            if nm not in roofs or len(r.get("screens") or []) > len(roofs[nm].get("screens") or []):
                roofs[nm] = r
            roof_mask[nm] = roof_mask.get(nm, 0) | 1 << c
            for s_ in r.get("screens") or []:
                screen_mask[(nm, s_["side"])] = screen_mask.get((nm, s_["side"]), 0) | 1 << c
    all_mask = sum(1 << c for c in valid)
    if not names:                                                   # one spec: the groups from the engine's option layers
        order = list(OPTION_LABELS.values())
        found = sorted({_layer_option(b) for b, _m in union.values()} - {""}, key=lambda f: (order.index(f) if f in order else len(order), f))
        names = [next((k for k, v in labels.items() if v == f), f.lower().replace(" ", "_")) for f in found]
        for n, f in zip(names, found):
            labels.setdefault(n, f)
        bits = {n: i for i, n in enumerate(names)}
        req = {n: [r for r in REQUIRES.get(n, []) if r in names] for n in names}
        valid = [c for c in range(1 << len(names)) if all(all(c >> bits[r] & 1 for r in req.get(n, [])) for n in names if c >> bits[n] & 1)]
        all_mask = sum(1 << c for c in valid)
        lab2n = {labels[n]: n for n in names}
        for e in union.values():
            o = _layer_option(e[0])
            e[1] = sum(1 << c for c in valid if c >> bits[lab2n[o]] & 1) if o in lab2n else all_mask
        for nm in list(roof_mask):
            rn = lab2n.get(labels.get("roof", "Louvered roof"))
            roof_mask[nm] = sum(1 << c for c in valid if rn is None or c >> bits[rn] & 1)
        for key in list(screen_mask):
            sn = lab2n.get(labels.get("screens", "Roof screens"))
            screen_mask[key] = sum(1 << c for c in valid if sn is None or c >> bits[sn] & 1)
    # ---- what each mask means, in words; cross-check the engine's option layers
    def with_(n):
        return sum(1 << c for c in valid if c >> bits[n] & 1)

    def describe(m):
        """The simplest 'shows with A (+ B), not with C (or D)' that gives exactly this mask."""
        if m == all_mask:
            return "base"
        import itertools
        best = None
        for states in itertools.product((0, 1, 2), repeat=len(names)):       # 0 free, 1 on, 2 off
            mm = all_mask
            for n, st_ in zip(names, states):
                mm &= with_(n) if st_ == 1 else (~with_(n) if st_ == 2 else all_mask)
            if mm == m:
                cost = sum(1 for x in states if x)
                if best is None or cost < best[0]:
                    best = (cost, states)
        if best is None:
            return f"combinations {m:#x}"
        on = [labels.get(n, n) for n, x in zip(names, best[1]) if x == 1]
        off = [labels.get(n, n) for n, x in zip(names, best[1]) if x == 2]
        txt = ("option:" + " + ".join(on)) if on else "base"
        return txt + (", replaced by " + " or ".join(off) if off else "")
    groups: Dict[str, int] = {}
    mask_labels: Dict[int, str] = {}
    mism = []
    lab2key = {labels.get(n, n): n for n in names}
    for b, m in union.values():
        g = mask_labels.setdefault(m, describe(m))
        groups[g] = groups.get(g, 0) + 1
        n_lo = lab2key.get(_layer_option(b))      # a box the engine marks as an option's must show only with that option on
        if n_lo is not None and m & ~with_(n_lo) and len(mism) < 12:
            mism.append(f"{b.kind} {b.tag[:60]!r}: layer says {labels.get(n_lo, n_lo)}, the specs say {g}")
    stats["groups"] = dict(sorted(groups.items(), key=lambda kv: -kv[1]))
    if mism:
        stats["warnings"].append("engine option layers vs spec diffs: " + "; ".join(mism))
    # ---- pack
    mat_names = sorted({b.mat for b, _m in union.values()} | {r.get("blade_mat", "lvmetal") for r in roofs.values()}
                       | {s_.get("mat", "lvfabric") for r in roofs.values() for s_ in r.get("screens") or []})
    kinds = sorted({b.kind for b, _m in union.values()})
    layers = sorted({b.layer or "" for b, _m in union.values()})
    mi, ki, li = {m: i for i, m in enumerate(mat_names)}, {k: i for i, k in enumerate(kinds)}, {k: i for i, k in enumerate(layers)}
    rd = lambda v: round(float(v), 3)
    flat: List[float] = []
    meshes = []
    for b, m in union.values():
        role = _role(b, mats)
        if b.shape == "mesh":
            if not b.pts:
                continue
            meshes.append([mi[b.mat], ki[b.kind], m, role, li[b.layer or ""], [rd(v) for q in b.pts for v in q]])
            continue
        flat += [rd(b.x0), rd(b.x1), rd(b.y0), rd(b.y1), rd(b.z0), rd(b.z1), round(float(b.rot or 0.0), 5), round(float(b.tone or 0.0), 3),
                 mi[b.mat], ki[b.kind], SHAPES.get(b.shape, 0), AXES.get(b.rot_axis or "y", 0), m, role, li[b.layer or ""]]
    keep = ("color", "palette", "grain", "pattern", "rough", "metal", "opacity", "glass", "emission", "emit", "emissive", "glow", "emission_strength", "label")
    mats_out = {k: {f: v for f, v in mats.get(k, {"color": "#8a8a8a"}).items() if f in keep} for k in mat_names}
    for k in mat_names:
        e = _emit_hex(mats_out[k])
        if e:
            mats_out[k]["emit"] = e
    # ---- live roof parts
    roofs_out = []
    for nm, r in roofs.items():
        rr = dict(name=nm, mask=roof_mask[nm], blade_mat=r.get("blade_mat", "lvmetal"), angle_min=float(r.get("angle_min_deg", 0.0)),
                  angle_open=float(r.get("angle_open_deg", 90.0)), angle_max=float(r.get("angle_max_deg", 140.0)),
                  angle_default=float(r.get("angle_default_deg", 45.0)), across=r.get("across"), up=r.get("up", [0, 0, 1]),
                  profile=r.get("profile"), frame=r.get("frame"), z_deck=r.get("z_deck"),
                  blades=[[rd(q) for q in bl["pivot"]] + [rd(q) for q in bl["axis"]] + [rd(bl["length"]), rd(bl["width"]), rd(bl["thick"]),
                          1 if bl.get("motor") else 0] for bl in r.get("blades") or []],
                  screens=[dict(side=s_["side"], a=s_["a"], b=s_["b"], plane=s_.get("plane"), line=s_.get("line"), z_top=s_["z_top"],
                                z_bottom=s_["z_bottom"], max_drop=s_.get("max_drop", s_["z_top"] - s_["z_bottom"]),
                                down=float(s_.get("down_default", 0.0)), thick=s_.get("thick", 0.02), hem=s_.get("hem") or dict(h=0.17, t=0.12, mat="lvmetal"),
                                track_w=s_.get("track_w", 0.12), mat=s_.get("mat", "lvfabric"), fabric=s_.get("fabric", "mesh"),
                                mask=screen_mask.get((nm, s_["side"]), 0)) for s_ in r.get("screens") or []])
        roofs_out.append(rr)
    # ---- the site and its sun
    s = dict(lat=spec0.site.lat, lon=spec0.site.lon, rear_az=spec0.site.rear_azimuth_deg, utc=spec0.site.utc_offset_h, when=spec0.site.sun_when)
    s.update({k: v for k, v in (site or {}).items() if v is not None})
    if s.get("lat") is None or s.get("lon") is None or s.get("rear_az") is None:
        stats["warnings"].append("the spec has no site lat / lon / rear_azimuth_deg: the page's sun is a stand-in (Denver, deck facing south)")
        s.update(lat=39.74 if s.get("lat") is None else s["lat"], lon=-104.99 if s.get("lon") is None else s["lon"],
                 rear_az=180.0 if s.get("rear_az") is None else s["rear_az"])
    when = str(s.get("when") or "2026-06-21T15:00")
    s["date"], hhmm = (when.split("T") + ["15:00"])[:2]
    hh, mm = (hhmm.split(":") + ["0"])[:2]
    s["minutes"] = int(hh) * 60 + int(mm)
    # ---- frame, region, cameras
    parts = _parts_of(L0)
    sm = getattr(spec0.geometry, "site_model", None)
    if sm and sm.get("grade") and any((b.layer or "") == "site" for b, _m in union.values()):     # the yard is drawn: stand on it
        try:
            from .landscape import grade_at
            grade = lambda x, y: float(grade_at(sm, x, y))
        except Exception:                                          # noqa: BLE001 — a yard model mid-edit: flat grade
            grade = lambda x, y: 0.0
    else:
        grade = lambda x, y: 0.0
    vws = views or _views(parts, list(roofs.values()), (meta0 or {}).get("cameras"), grade, _occluders(b for b, _m in union.values()))
    bx0 = min(p["x0"] for p in parts); bx1 = max(p["x1"] for p in parts)
    by0 = min(p["y0"] for p in parts); by1 = max(p["y1"] for p in parts)
    ztop = max([p["top"] for p in parts] + [float((r.get("frame") or {}).get("z_top", 0.0)) for r in roofs.values()])
    fixtures = _fixtures([(b, m) for b, m in union.values()], mats)
    gboxes = [b for b, _m in union.values() if b.kind == "ground" and b.shape == "box"]
    gbig = max(gboxes, key=lambda b: (b.x1 - b.x0) * (b.y1 - b.y0)) if gboxes else None
    opts = [dict(key=n, label=labels.get(n, n.title()), short=OPTION_SHORT.get(n, labels.get(n, n.title())), bit=bits[n], requires=req.get(n, []))
            for n in names]
    addr = f"{spec0.site.address}, {spec0.site.city}".strip(", ") if spec0.site.address else spec0.job
    data = dict(title=title or (spec0.site.address or spec0.job or "Deck"), address=addr, options=opts, combos=valid, all_mask=all_mask,
                mask_labels={str(k): v for k, v in sorted(mask_labels.items())},
                default_on=[n for n in default_on if n in bits], mats=mats_out, mat_names=mat_names, kinds=kinds, layers=layers,
                boxes=flat, stride=15, meshes=meshes, roofs=roofs_out, fixtures=fixtures, site=s, views=vws,
                deck=dict(x0=bx0, x1=bx1, y0=by0, y1=by1, top=max(p["top"] for p in parts), z_max=ztop,
                          parts=[dict(name=p["name"], top=p["top"]) for p in parts]),
                ground=dict(z=round(gbig.z1, 3) if gbig else 0.0, mat=gbig.mat if gbig else "ground"))
    stats.update(boxes=len(flat) // 15, meshes=len(meshes), combos=len(valid), fixtures=len(fixtures), roofs=len(roofs_out),
                 options=[o["key"] for o in opts], views=[v["key"] for v in vws])
    return data, stats


def configurator_html(data: dict, three_src: Optional[str] = None, standalone: bool = True) -> str:
    """The page. three_src: the three.js r128 source to inline (default decktakeoff/data/three.min.js)."""
    if three_src is None:
        from .render import three_source
        three_src = three_source()
        if three_src is None:
            raise RuntimeError("three.min.js not found: put it at decktakeoff/data/three.min.js or set THREE_MIN_JS")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    title = _html.escape(str(data.get("title") or "Deck options"))
    body = (BODY.replace("__TITLE__", title).replace("__ADDR__", _html.escape(str(data.get("address") or "")))
            + f'<script type="application/json" id="cfg-data">{payload}</script>\n'
            + f"<script>{three_src}</script>\n<script>{JS}</script>")
    opts = ", ".join(o["label"].lower() for o in data.get("options") or [])
    desc = _html.escape(f"{data.get('address') or title}: the deck in 3D" + (f" with its options ({opts})" if opts else "")
                        + ", the sun at the address through the day.")
    head = (f'<title>{title}</title>\n<meta name="description" content="{desc}">\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'<style>{CSS}</style>\n')
    if not standalone:
        return head + body
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            f'{head}</head><body>\n{body}\n</body></html>\n')


def build_configurator(spec_base, options: Optional[Dict[str, object]] = None, out_html: Union[str, Path] = "configurator.html", *,
                       title: Optional[str] = None, site: Optional[dict] = None, labels: Optional[Dict[str, str]] = None,
                       requires: Optional[Dict[str, Sequence[str]]] = None, combos: Optional[Dict[str, object]] = None,
                       default_on: Sequence[str] = (), views: Optional[List[dict]] = None, three_src: Optional[str] = None,
                       standalone: bool = True) -> dict:
    """Write the interactive options page; returns stats (path, bytes, boxes, combos, the groups each box landed in, each
    option's patch paths, warnings).

    spec_base   the base bid: a DeckSpec, a spec dict or a path to the job JSON.
    options     {key: spec} — each option's whole spec (the base plus that option), in the order the toggles show. Keys with
                built-in labels: "stairs" (Stairs to the yard), "lights" (Lighting), "roof" (Louvered roof), "screens" (Roof
                screens — needs the roof; its spec carries the roof too). None: `spec_base` is one spec with every option on
                and the groups come from the engine's "option:<label>" layers (see the module doc).
    combos      {"stairs+lights": spec}: a whole spec for a combination whose patches do not simply add up (used as given).
    requires    {"screens": ["roof"]} (the default): an option offered only with its prerequisites.
    site        overrides of the sun's site: {"lat", "lon", "rear_az" (deg, the plan's +y), "utc" (h), "when" ("YYYY-MM-DDTHH:MM")}.
    default_on  the options the page opens with (default: the base alone); the URL's ?opts= overrides.
    views       camera presets [{key, label, pos: [x, y, z], at: [x, y, z], fov, fit}] in plan feet (default: yard / upper
                deck (under the roof) / lower deck / aerial from the layout and the roof).
    standalone  False: the body only (title, style, markup, scripts) for a host that wraps its own document."""
    data, stats = configurator_data(spec_base, options, labels=labels, requires=requires, combos=combos, site=site, title=title,
                                    default_on=default_on, views=views)
    page = configurator_html(data, three_src=three_src, standalone=standalone)
    out = Path(out_html)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    stats.update(path=str(out), bytes=len(page.encode("utf-8")))
    return stats


# ================================================================== the page
CSS = r"""
/* Layout: the 3D stage fills the screen; the controls sit in a side panel on wide screens and under the stage on a phone. */
:root {
  --space: #0b0d10; --panel: #111419; --raise: #1b1f26; --line: rgba(244, 242, 236, .14); --ink: #f4f2ec; --mute: #a9a69e;
  --gold: #d49e1b; --gold-2: #ffe28d; --on-ink: #120e05; --night: #1b2236;
  --display: "Saira Semi Condensed", "Avenir Next Condensed", "Arial Narrow", "Roboto Condensed", system-ui, sans-serif;
  --body: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color-scheme: dark;
}
html, body { height: 100%; margin: 0; background: var(--space); color: var(--ink); }
body { font: 14px/1.35 var(--body); -webkit-text-size-adjust: 100%; overflow: hidden; }
[hidden] { display: none !important; }
#app { position: fixed; top: 0; right: 0; bottom: 0; left: 0; display: flex; flex-direction: row; }
#stage { position: relative; flex: 1 1 auto; min-width: 0; min-height: 0; background: var(--night); touch-action: none; overflow: hidden; }
#stage canvas { display: block; width: 100%; height: 100%; touch-action: none; outline: none; -webkit-tap-highlight-color: transparent; }
#panel { flex: 0 0 340px; width: 340px; background: var(--panel); border-left: 1px solid var(--line); overflow-y: auto; -webkit-overflow-scrolling: touch;
  display: flex; flex-direction: column; gap: 14px; padding-block: max(14px, env(safe-area-inset-top, 0px)) max(16px, env(safe-area-inset-bottom, 0px));
  padding-left: 16px; padding-right: max(16px, env(safe-area-inset-right, 0px)); box-sizing: border-box; }
.cap { position: absolute; top: max(10px, env(safe-area-inset-top, 0px)); left: max(12px, env(safe-area-inset-left, 0px)); right: 12px; pointer-events: none;
  text-shadow: 0 1px 3px rgba(0, 0, 0, .65); display: flex; flex-direction: column; gap: 2px; }
.cap .addr { font: 800 13px/1.1 var(--display); letter-spacing: .14em; text-transform: uppercase; color: #fff; }
.cap .state { font-size: 12.5px; color: #f1eee6; font-variant-numeric: tabular-nums; }
.hint { position: absolute; left: 50%; bottom: 14px; transform: translateX(-50%); background: rgba(8, 10, 13, .66); color: var(--ink); font-size: 12px;
  padding: 6px 12px; border-radius: 999px; pointer-events: none; white-space: nowrap; transition: opacity .6s; }
.hint.gone { opacity: 0; }
.fail { position: absolute; top: 0; right: 0; bottom: 0; left: 0; display: flex; align-items: center; justify-content: center; text-align: center; padding: 24px; color: var(--ink); font-size: 15px; }
.grp { display: flex; flex-direction: column; gap: 8px; }
.grp + .grp { border-top: 1px solid var(--line); padding-top: 12px; }
.grp h2 { margin: 0; font: 700 11.5px/1 var(--display); letter-spacing: .22em; text-transform: uppercase; color: var(--mute); display: flex; justify-content: space-between; gap: 8px; }
.grp h2 output { font: 700 13px/1 var(--display); letter-spacing: .06em; color: var(--gold-2); text-transform: none; font-variant-numeric: tabular-nums; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip, .btn { appearance: none; -webkit-appearance: none; font: 600 13px/1 var(--body); color: var(--ink); background: var(--raise); border: 1px solid var(--line);
  border-radius: 6px; padding: 0 11px; min-height: 36px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; touch-action: manipulation; }
.chip:hover, .btn:hover { border-color: rgba(244, 242, 236, .34); }
.chip[aria-pressed="true"], .btn.on { background: var(--gold); border-color: var(--gold); color: var(--on-ink); }
.chip[disabled] { opacity: .45; cursor: default; }
.chip.base { cursor: default; background: transparent; color: var(--mute); }
.chip .tick { width: 14px; height: 14px; border-radius: 3px; border: 1.5px solid currentColor; display: inline-block; position: relative; box-sizing: border-box; }
.chip[aria-pressed="true"] .tick::after, .chip.base .tick::after { content: ""; position: absolute; left: 3.5px; top: 0.5px; width: 3.5px; height: 7px;
  border: solid currentColor; border-width: 0 2px 2px 0; transform: rotate(45deg); }
.chip:focus-visible, .btn:focus-visible, input:focus-visible { outline: 2px solid var(--gold-2); outline-offset: 2px; }
.row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.row.wrap { flex-wrap: wrap; }
.row .grow { flex: 1 1 auto; min-width: 0; }
.muted { color: var(--mute); font-size: 12px; font-variant-numeric: tabular-nums; }
input[type=range] { -webkit-appearance: none; appearance: none; width: 100%; height: 30px; background: transparent; margin: 0; touch-action: pan-y; }
input[type=range]::-webkit-slider-runnable-track { height: 8px; border-radius: 4px; background: var(--track, var(--raise)); border: 1px solid var(--line); }
input[type=range]::-moz-range-track { height: 8px; border-radius: 4px; background: var(--track, var(--raise)); border: 1px solid var(--line); }
input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 26px; height: 26px; margin-top: -10px; border-radius: 50%; background: var(--ink);
  border: 3px solid var(--gold); box-shadow: 0 1px 4px rgba(0, 0, 0, .5); }
input[type=range]::-moz-range-thumb { width: 20px; height: 20px; border-radius: 50%; background: var(--ink); border: 3px solid var(--gold); }
input[type=date] { font: 600 13px var(--body); color: var(--ink); background: var(--raise); border: 1px solid var(--line); border-radius: 6px; min-height: 36px;
  padding: 0 8px; box-sizing: border-box; min-width: 0; }
.ticks { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--mute); margin-top: -4px; font-variant-numeric: tabular-nums; }
.btn.icon { width: 40px; justify-content: center; padding: 0; }
.btn svg { width: 14px; height: 14px; fill: currentColor; }
.views { display: grid; grid-template-columns: repeat(auto-fit, minmax(92px, 1fr)); gap: 6px; }
.views .btn { justify-content: center; }
.note { font-size: 11.5px; color: var(--mute); line-height: 1.4; margin: 0; }
.grab { display: none; }
@media (max-width: 760px) and (orientation: portrait), (max-width: 520px) {
  #app { flex-direction: column; }
  #panel { flex: 0 0 auto; width: auto; max-height: 47%; border-left: 0; border-top: 1px solid var(--line); gap: 10px;
    padding-block: 10px max(12px, env(safe-area-inset-bottom, 0px)); padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
  #panel.folded { max-height: 44px; overflow: hidden; }
  .grp + .grp { padding-top: 10px; }
  .grab { display: flex; align-items: center; justify-content: center; gap: 8px; margin: -6px 0 -2px; min-height: 30px; background: none; border: 0;
    color: var(--mute); font: 600 11px/1 var(--display); letter-spacing: .18em; text-transform: uppercase; cursor: pointer; }
  .grab .bar { width: 34px; height: 4px; border-radius: 2px; background: var(--line); }
  .hint { bottom: 54px; }
  #g-view { display: none; }
  .vbar:not([hidden]) { display: flex; }
}
.vbar { display: none; position: absolute; left: max(10px, env(safe-area-inset-left, 0px)); right: max(10px, env(safe-area-inset-right, 0px)); bottom: 10px; gap: 6px; overflow-x: auto; }
.vbar .btn { background: rgba(14, 16, 20, .78); min-height: 34px; font-size: 12.5px; white-space: nowrap; flex: 0 0 auto; }
.vbar .btn.on { background: var(--gold); }
@media (max-height: 520px) and (orientation: landscape) {
  #panel { flex-basis: 300px; width: 300px; gap: 10px; }
}
@media (prefers-reduced-motion: reduce) { .hint { transition: none; } }
"""

BODY = r"""<div id="app">
  <div id="stage">
    <div class="cap" aria-live="polite"><div class="addr">__ADDR__</div><div class="state" id="state"></div></div>
    <div class="hint" id="hint">Drag to turn &middot; scroll or pinch to zoom &middot; right-drag or two fingers to move</div>
    <div class="vbar" id="vbar" role="group" aria-label="Views"></div>
    <div class="fail" id="fail" hidden></div>
  </div>
  <aside id="panel" aria-label="Options and controls">
    <button type="button" class="grab" id="fold" aria-label="Hide the controls" aria-expanded="true"><span class="bar"></span><span id="foldlab">Hide controls</span></button>
    <section class="grp" id="g-opts"><h2>Options</h2><div class="chips" id="chips"></div></section>
    <section class="grp" id="g-time">
      <h2><span>Sun and time</span><output id="tlab" for="t"></output></h2>
      <div class="row"><input type="range" id="t" min="300" max="1380" step="5" aria-label="Time of day" class="grow">
        <button type="button" class="btn icon" id="play" aria-label="Play the day"><svg viewBox="0 0 16 16"><path id="playpath" d="M4 2.5v11l9-5.5z"/></svg></button></div>
      <div class="ticks"><span>5 AM</span><span>9</span><span>Noon</span><span>3 PM</span><span>6</span><span>9</span><span>11 PM</span></div>
      <div class="row wrap"><div class="chips" id="seasons"></div><input type="date" id="date" aria-label="Date"></div>
      <div class="muted" id="sunlab"></div>
    </section>
    <section class="grp" id="g-louv" hidden>
      <h2><span>Louvers</span><output id="lvlab" for="lv"></output></h2>
      <input type="range" id="lv" min="0" max="140" step="1" aria-label="Louver angle">
      <div class="row"><button type="button" class="btn" id="lvClose">Close</button><button type="button" class="btn" id="lvOpen">Open</button>
        <span class="muted grow" id="lvnote"></span></div>
    </section>
    <section class="grp" id="g-scr" hidden>
      <h2><span>Screens</span><output id="sclab" for="sc"></output></h2>
      <input type="range" id="sc" min="0" max="100" step="1" aria-label="Screens down">
      <div class="row wrap"><button type="button" class="btn" id="scUp">Up</button><button type="button" class="btn" id="scDown">Down</button>
        <div class="chips" id="sides" role="group" aria-label="Which screens"></div></div>
    </section>
    <section class="grp" id="g-view"><h2>View</h2><div class="views" id="views"></div></section>
    <p class="note" id="note"></p>
  </aside>
</div>
"""

JS = r"""
(function () {
'use strict';
var failEl = document.getElementById('fail');
function fail(msg) { failEl.textContent = msg; failEl.hidden = false; window.__ready = true; window.__failed = msg; }
var D;
try { D = JSON.parse(document.getElementById('cfg-data').textContent); } catch (e) { fail('The 3D data could not be read.'); return; }
if (typeof THREE === 'undefined') { fail('The 3D engine did not load.'); return; }
var Q = new URLSearchParams(location.search);
var STILL = Q.get('still') === '1';
var NOUI = Q.get('ui') === '0';
var PERF = Q.get('perf') === '1';
var RM = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var $ = function (id) { return document.getElementById(id); };

// ------------------------------------------------------------------ options / combos
var OPT = D.options, VALID = {}, SITE = D.site, ROOFS = D.roofs || [];
D.combos.forEach(function (c) { VALID[c] = 1; });
var OBYKEY = {}; OPT.forEach(function (o) { OBYKEY[o.key] = o; });
function comboOf(on) { var c = 0; OPT.forEach(function (o) { if (on[o.key]) c |= 1 << o.bit; }); return c; }
function shows(mask, c) { return ((mask >>> c) & 1) === 1; }

// ------------------------------------------------------------------ state (+ URL)
var S = { on: {}, date: SITE.date, min: SITE.minutes, view: D.views[0].key, louver: 0, louverGoal: null, scr: {}, scrGoal: {}, sel: {}, playing: false, trees: Q.get('trees') !== '0' };
(D.default_on || []).forEach(function (k) { S.on[k] = true; });
var qo = Q.get('opts');
if (qo !== null) { S.on = {}; if (qo === 'all') OPT.forEach(function (o) { S.on[o.key] = true; }); else qo.split(',').forEach(function (k) { if (OBYKEY[k]) S.on[k] = true; }); }
function fixRequires() { OPT.forEach(function (o) { if (S.on[o.key]) o.requires.forEach(function (r) { if (!S.on[r]) S.on[o.key] = false; }); }); }
fixRequires();
var YEAR = +SITE.date.slice(0, 4);
var SEASONS = [['summer', 'Summer', YEAR + '-06-21'], ['equinox', 'Equinox', YEAR + '-09-22'], ['winter', 'Winter', YEAR + '-12-21']];
var qd = Q.get('date');
if (qd) { var se = SEASONS.filter(function (s) { return s[0] === qd; })[0]; if (se) S.date = se[2]; else if (/^\d{4}-\d\d-\d\d$/.test(qd)) S.date = qd; }
var qt = Q.get('t');
if (qt) { var mt = /^(\d{1,2}):(\d\d)$/.exec(qt); S.min = mt ? (+mt[1]) * 60 + (+mt[2]) : Math.round(+qt) || S.min; }
S.min = Math.max(300, Math.min(1380, S.min));
var ROOF = ROOFS[0] || null;
S.louver = ROOF ? ROOF.angle_default : 0;
if (Q.get('louver') !== null && ROOF) S.louver = Math.max(ROOF.angle_min, Math.min(ROOF.angle_max, +Q.get('louver') || 0));
var SCREENS = [];
ROOFS.forEach(function (r, ri) { (r.screens || []).forEach(function (s) { s.roof = ri; s.id = r.name + '|' + s.side; SCREENS.push(s); S.scr[s.id] = s.down || 0; S.sel[s.side] = true; }); });
var qs = Q.get('screens');
if (qs !== null) qs.split(',').forEach(function (p) {
  var kv = p.split(':');
  SCREENS.forEach(function (s) { if (kv.length === 1 || kv[0] === s.side) S.scr[s.id] = Math.max(0, Math.min(1, (+kv[kv.length - 1] || 0) / 100)); });
});
if (Q.get('view')) S.view = Q.get('view');

// ------------------------------------------------------------------ renderer
var stage = $('stage');
var renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: STILL || PERF, powerPreference: 'high-performance' });
} catch (e) { fail('This page needs WebGL. Open it in Safari, Chrome or Edge.'); return; }
var DPR = Math.min(window.devicePixelRatio || 1, 2);
renderer.setPixelRatio(DPR);
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
stage.insertBefore(renderer.domElement, stage.firstChild);
renderer.domElement.setAttribute('role', 'img');
renderer.domElement.setAttribute('aria-label', '3D view of the deck, the house and the yard');
renderer.domElement.addEventListener('webglcontextlost', function (e) { e.preventDefault(); }, false);
renderer.domElement.addEventListener('webglcontextrestored', function () { renderer.shadowMap.needsUpdate = true; invalidate(); }, false);
var gl = renderer.getContext();
var scene = new THREE.Scene();
var P3 = function (x, y, z) { return new THREE.Vector3(x, z, y); };   // plan (x along the house, y to the yard, z up) -> three
var DK = D.deck, CX = (DK.x0 + DK.x1) / 2, CY = (DK.y0 + DK.y1) / 2;

// ------------------------------------------------------------------ sky dome
var skyU = { uTop: { value: new THREE.Color() }, uHor: { value: new THREE.Color() }, uGnd: { value: new THREE.Color() },
  uSun: { value: new THREE.Vector3(0, 1, 0) }, uSunCol: { value: new THREE.Color() }, uGlow: { value: 0 }, uDisc: { value: 0 } };
var sky = new THREE.Mesh(new THREE.SphereGeometry(1500, 40, 20), new THREE.ShaderMaterial({
  uniforms: skyU, side: THREE.BackSide, depthWrite: false, fog: false, toneMapped: false,
  vertexShader: 'varying vec3 vD; void main(){ vD = normalize(position); vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_Position = p.xyww; }',
  fragmentShader: [
    'uniform vec3 uTop, uHor, uGnd, uSunCol, uSun; uniform float uGlow, uDisc; varying vec3 vD;',
    'void main(){ vec3 d = normalize(vD); float h = d.y;',
    ' vec3 c = h >= 0.0 ? mix(uHor, uTop, pow(clamp(h * 1.15, 0.0, 1.0), 0.5)) : mix(uHor, uGnd, smoothstep(0.0, 0.12, -h));',
    ' float cs = max(dot(d, uSun), 0.0);',
    ' c += uSunCol * uGlow * (0.55 * pow(cs, 6.0) + 0.45 * pow(cs, 48.0)) * (1.0 - smoothstep(0.0, 0.55, h) * 0.6);',
    ' c += uSunCol * uDisc * smoothstep(0.99994, 0.99998, cs);',
    ' gl_FragColor = vec4(c, 1.0); }'].join('\n')
}));
sky.renderOrder = -10; sky.frustumCulled = false; scene.add(sky);
var stars = (function () {
  var n = 700, pos = new Float32Array(n * 3), s = 12345;
  var rnd = function () { s = (s * 16807) % 2147483647; return s / 2147483647; };
  for (var i = 0; i < n; i++) { var u = rnd() * 2 * Math.PI, v = 0.06 + rnd() * 0.94, r = Math.sqrt(1 - v * v);
    pos[i * 3] = Math.cos(u) * r * 1400; pos[i * 3 + 1] = v * 1400; pos[i * 3 + 2] = Math.sin(u) * r * 1400; }
  var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  var m = new THREE.PointsMaterial({ color: 0xffffff, size: 1.6 * DPR, sizeAttenuation: false, transparent: true, opacity: 0, depthWrite: false, fog: false, toneMapped: false });
  var p = new THREE.Points(g, m); p.frustumCulled = false; p.renderOrder = -9; scene.add(p); return p;
})();
scene.fog = new THREE.Fog(0xcfd9e3, 300, 2200);

// ------------------------------------------------------------------ lights
var hemi = new THREE.HemisphereLight(0xcfe0f2, 0x5b5546, 0.5); scene.add(hemi);
var sun = new THREE.DirectionalLight(0xfff1dc, 1.5);
sun.castShadow = true;
var SMAP = Q.get('smap') ? +Q.get('smap') : 2048;
sun.shadow.mapSize.set(SMAP, SMAP); sun.shadow.bias = -0.00035; sun.shadow.normalBias = 0.025; sun.shadow.radius = 2;
scene.add(sun); scene.add(sun.target);
var moon = new THREE.DirectionalLight(0x8fa6d6, 0); moon.position.set(CX - 40, 120, CY + 90); moon.target.position.set(CX, 0, CY); scene.add(moon); scene.add(moon.target);

// ------------------------------------------------------------------ textures (the viewer's board grain and patterns)
function shade(hex, k) { var n = parseInt(hex.slice(1), 16), r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  r = Math.max(0, Math.min(255, Math.round(r * (1 + k)))); g = Math.max(0, Math.min(255, Math.round(g * (1 + k)))); b = Math.max(0, Math.min(255, Math.round(b * (1 + k))));
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0'); }
var ANISO = Math.min(4, renderer.capabilities.getMaxAnisotropy());
function canvasTex(c) { var t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = ANISO; return t; }
function grainTex(hexes, seed) {
  var c = document.createElement('canvas'), Lp = 1024, Sp = 128; c.width = Lp; c.height = Sp;
  var g = c.getContext('2d'), s = seed, rnd = function () { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  g.fillStyle = hexes[Math.floor(hexes.length / 2)]; g.fillRect(0, 0, Lp, Sp);
  for (var i = 0; i < 110; i++) { var p = rnd() * Sp, a0 = rnd() * 0.4 * Lp, a1 = Lp * (0.6 + rnd() * 0.4);
    g.strokeStyle = hexes[Math.floor(rnd() * hexes.length)]; g.globalAlpha = 0.6 * (0.4 + rnd() * 0.6); g.lineWidth = 0.6 + rnd() * 2.2;
    g.beginPath(); g.moveTo(a0, p); g.lineTo(a1, p + (rnd() - 0.5) * 3); g.stroke(); }
  g.globalAlpha = 0.35; g.fillStyle = shade(hexes[0], -0.35); g.fillRect(0, 0, Lp, 3); g.fillRect(0, Sp - 3, Lp, 3); g.globalAlpha = 1;
  return canvasTex(c);
}
function patternTex(kind, hex, seed) {
  var c = document.createElement('canvas'); c.width = 512; c.height = 512; var g = c.getContext('2d'), s = seed;
  var rnd = function () { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  g.fillStyle = hex; g.fillRect(0, 0, 512, 512);
  var i, x, y, r_;
  if (kind === 'stone') { var cols = [shade(hex, -0.28), shade(hex, -0.14), hex, shade(hex, 0.1), shade(hex, 0.2), '#a3907a', '#6f6a63'];
    y = 0; while (y < 512) { var h = 22 + rnd() * 30; x = -rnd() * 60; while (x < 512) { var w = 50 + rnd() * 120; g.fillStyle = cols[Math.floor(rnd() * cols.length)]; g.fillRect(x + 2, y + 2, w - 4, h - 4); x += w; } y += h; }
  } else if (kind === 'lap') { for (y = 0; y < 512; y += 32) { g.fillStyle = shade(hex, -0.22); g.fillRect(0, y, 512, 3); g.fillStyle = shade(hex, 0.06); g.fillRect(0, y + 3, 512, 2); }
  } else if (kind === 'batten') { for (x = 0; x < 512; x += 64) { g.fillStyle = shade(hex, -0.25); g.fillRect(x, 0, 6, 512); g.fillStyle = shade(hex, 0.08); g.fillRect(x + 6, 0, 2, 512); }
  } else if (kind === 'brick') { var bh = 512 / 36, bw = 512 / 12;
    for (r_ = 0; r_ < 36; r_++) { var off = (r_ % 2) * bw / 2; for (var cc = -1; cc < 13; cc++) { g.fillStyle = [shade(hex, -0.12), hex, shade(hex, 0.1), shade(hex, -0.05), shade(hex, 0.18)][Math.floor(rnd() * 5)]; g.fillRect(cc * bw + off + 1.5, r_ * bh + 1.5, bw - 3, bh - 3); } }
    g.globalAlpha = 0.5; g.fillStyle = '#b9b0a4'; for (r_ = 0; r_ <= 36; r_++) g.fillRect(0, r_ * bh - 0.5, 512, 1.5); g.globalAlpha = 1;
  } else if (kind === 'seam') { for (x = 0; x < 512; x += 85.33) { g.fillStyle = shade(hex, 0.35); g.fillRect(x, 0, 5, 512); g.fillStyle = shade(hex, -0.45); g.fillRect(x + 5, 0, 4, 512); }
  } else if (kind === 'grass') { for (i = 0; i < 26000; i++) { g.fillStyle = [shade(hex, -0.16), shade(hex, -0.08), shade(hex, 0.08), shade(hex, 0.16), '#93a267', '#6f8c48'][Math.floor(rnd() * 6)]; g.globalAlpha = 0.6 + rnd() * 0.4; g.fillRect(rnd() * 512, rnd() * 512, 1, 1 + rnd() * 2); } g.globalAlpha = 1;
  } else if (kind === 'louver') { for (y = 0; y < 512; y += 18) { g.fillStyle = shade(hex, -0.28); g.fillRect(0, y + 13, 512, 4); g.fillStyle = shade(hex, 0.04); g.fillRect(0, y, 512, 3); }
  } else if (kind === 'shingle') { for (y = 0; y < 512; y += 21) { var o2 = (y / 21) % 2 ? 0 : 32; g.fillStyle = shade(hex, -0.3); g.fillRect(0, y + 18, 512, 3);
      for (x = -o2; x < 512; x += 64) { g.fillStyle = [shade(hex, -0.1), hex, shade(hex, 0.08), shade(hex, -0.04)][Math.floor(rnd() * 4)]; g.fillRect(x + 1, y, 62, 18); } }
    g.globalAlpha = 0.25; for (i = 0; i < 9000; i++) { g.fillStyle = rnd() > 0.5 ? '#000' : '#fff'; g.fillRect(rnd() * 512, rnd() * 512, 1, 1); } g.globalAlpha = 1;
  } else if (kind === 'paver') { var u = 512 / 24;
    for (i = 0; i < 12; i++) for (var j = 0; j < 12; j++) for (var k = 0; k < 2; k++) { g.fillStyle = [shade(hex, -0.12), hex, shade(hex, 0.1), shade(hex, -0.05), shade(hex, 0.16)][Math.floor(rnd() * 5)];
      if ((i + j) % 2) g.fillRect(i * 2 * u + 1.5, j * 2 * u + k * u + 1.5, 2 * u - 3, u - 3); else g.fillRect(i * 2 * u + k * u + 1.5, j * 2 * u + 1.5, u - 3, 2 * u - 3); }
  } else if (kind === 'gravel') { for (i = 0; i < 5000; i++) { g.fillStyle = [shade(hex, -0.25), shade(hex, -0.1), shade(hex, 0.12), shade(hex, 0.25)][Math.floor(rnd() * 4)]; g.beginPath(); g.arc(rnd() * 512, rnd() * 512, 1.5 + rnd() * 3, 0, 6.3); g.fill(); }
  } else if (kind === 'fabric') { g.globalAlpha = 0.5; for (y = 0; y < 512; y += 4) { g.fillStyle = shade(hex, (y / 4) % 2 ? 0.25 : -0.2); g.fillRect(0, y, 512, 1); }
    for (x = 0; x < 512; x += 4) { g.fillStyle = shade(hex, 0.18); g.fillRect(x, 0, 1, 512); } g.globalAlpha = 1; }
  return canvasTex(c);
}
var TILE = { grass: 5, gravel: 6 };

// ------------------------------------------------------------------ fixture lights: a shader add-on in every lit material
var FXN = Math.max(1, D.fixtures.length);
var maxFU = renderer.capabilities.maxFragmentUniforms || 221;
if (2 * FXN + 120 > maxFU) FXN = Math.max(1, Math.floor((maxFU - 120) / 2));
var FX = D.fixtures.slice(0, FXN);
var fxA = [], fxB = [];
for (var fi = 0; fi < FXN; fi++) { fxA.push(new THREE.Vector4()); fxB.push(new THREE.Vector4()); }
var FXU = { fxA: { value: fxA }, fxB: { value: fxB }, fxCol: { value: new THREE.Color(1.0, 0.72, 0.45) }, fxGain: { value: 0 },
  fxFocus: { value: new THREE.Vector3() }, fxCut: { value: Math.min(26, 0.42 * (D.deck.x1 - D.deck.x0)) },
  fxBox: { value: new THREE.Vector4(0, 0, 0, 0) }, fxY: { value: new THREE.Vector2(0, 0) } };
(function () {                                   // where any light can reach: fragments outside skip the loop
  if (!D.fixtures.length) return;
  var xs = D.fixtures.map(function (f) { return f[0]; }), ys = D.fixtures.map(function (f) { return f[1]; }), zs = D.fixtures.map(function (f) { return f[2]; });
  var R = 11.5, mn = function (a) { return Math.min.apply(null, a); }, mx = function (a) { return Math.max.apply(null, a); };
  FXU.fxBox.value.set(mn(xs) - R, mx(xs) + R, mn(ys) - R, mx(ys) + R); FXU.fxY.value.set(mn(zs) - R, mx(zs) + 2.0);
})();
var FX_GAIN = [7.0, 2.6, 0.9];        // a riser spot, a post-cap lantern, an LED strip (its nearest point)
var FX_CHUNK = [
  '#define FX_N ' + FXN,
  'uniform vec4 fxA[FX_N]; uniform vec4 fxB[FX_N]; uniform vec3 fxCol; uniform float fxGain; uniform vec4 fxBox; uniform vec2 fxY;',
  'varying vec3 vFxW; varying vec3 vFxN;',
  'vec3 fxLight(vec3 P, vec3 N) {',
  '  float acc = 0.0;',
  '  if (P.x < fxBox.x || P.x > fxBox.y || P.z < fxBox.z || P.z > fxBox.w || P.y < fxY.x || P.y > fxY.y) return vec3(0.0);',
  '  for (int i = 0; i < FX_N; i++) {',
  '    vec4 a = fxA[i];',
  '    if (a.x < P.x - 11.0) continue;',
  '    if (a.x > P.x + 11.0) break;',
  '    if (a.w <= 0.0) continue;',
  '    vec4 b = fxB[i]; vec3 Lp = a.xyz;',
  '    if (b.w > 2.5) { float h = b.w - 3.0; vec3 t = vec3(b.x, 0.0, b.z); Lp = a.xyz + t * clamp(dot(P - a.xyz, t), -h, h); }',
  '    vec3 L = Lp - P; float d2 = dot(L, L); if (d2 > 121.0) continue;',
  '    float d = sqrt(d2); vec3 l = L / max(d, 0.001);',
  '    float k = b.w < 1.5 ? 2.6 : (b.w < 2.5 ? 1.5 : 1.2);',
  '    float w = a.w / (1.0 + k * d2) * (1.0 - smoothstep(3.5, 11.0, d)) * max(dot(N, l), 0.0);',
  '    if (b.w < 1.5) w *= smoothstep(b.w, min(1.0, b.w + 0.35), dot(-l, b.xyz));',
  '    else if (b.w < 2.5) w *= mix(0.12, 1.0, smoothstep(-0.2, 0.45, l.y));',
  '    else w *= smoothstep(0.0, 0.5, l.y);',
  '    acc += w;',
  '  }',
  '  return acc * fxCol * fxGain;',
  '}'].join('\n');
function addFx(mat, fade) {
  mat.onBeforeCompile = function (sh) {
    sh.uniforms.fxA = FXU.fxA; sh.uniforms.fxB = FXU.fxB; sh.uniforms.fxCol = FXU.fxCol; sh.uniforms.fxGain = FXU.fxGain;
    sh.uniforms.fxBox = FXU.fxBox; sh.uniforms.fxY = FXU.fxY;
    sh.vertexShader = 'varying vec3 vFxW; varying vec3 vFxN;\n' + sh.vertexShader.replace('#include <worldpos_vertex>', [
      '#include <worldpos_vertex>',
      'vec4 fxw = vec4(transformed, 1.0); vec3 fxn = objectNormal;',
      '#ifdef USE_INSTANCING', 'fxw = instanceMatrix * fxw; fxn = mat3(instanceMatrix) * fxn;', '#endif',
      'vFxW = (modelMatrix * fxw).xyz; vFxN = normalize(mat3(modelMatrix) * fxn);'].join('\n'));
    var fs = sh.fragmentShader;
    if (fade) {      // the trees: a crown the camera is in, or the part of one between the camera and what it looks at, is cut away
      sh.uniforms.fxFocus = FXU.fxFocus; sh.uniforms.fxCut = FXU.fxCut;
      fs = 'uniform vec3 fxFocus; uniform float fxCut;\n' + fs.replace('void main() {', [
        'void main() {',
        '  vec3 fxSeg = fxFocus - cameraPosition; float fxT = clamp(dot(vFxW - cameraPosition, fxSeg) / max(dot(fxSeg, fxSeg), 1.0), 0.0, 1.0);',
        '  float fxR = distance(vFxW, cameraPosition + fxSeg * fxT);',
        '  if (distance(vFxW, cameraPosition) < ' + fade.toFixed(1) + ' || (fxT < 0.75 && fxR < max(2.5, fxCut * fxT))) discard;'].join('\n'));
    }
    sh.fragmentShader = FX_CHUNK + '\n' + fs.replace('gl_FragColor = vec4( outgoingLight, diffuseColor.a );',
      'if (fxGain > 0.0) { vec3 fxN = normalize(vFxN) * (gl_FrontFacing ? 1.0 : -1.0); outgoingLight += diffuseColor.rgb * fxLight(vFxW, fxN); }\n' +
      'gl_FragColor = vec4( outgoingLight, diffuseColor.a );');
  };
  mat.customProgramCacheKey = function () { return 'fx' + FXN + (fade ? 'fade' : ''); };
}

// ------------------------------------------------------------------ materials
var MATS = {}, GLASS_M = [], LED_M = [];
var ROOM = new THREE.Color('#ffb06a');
function matFor(key, side, opts2) {
  var k = key + '|' + side + (opts2 ? '|' + opts2 : '');
  if (MATS[k]) return MATS[k];
  var m = D.mats[key] || { color: '#8a8a8a' };
  var o = { roughness: m.rough == null ? 0.8 : m.rough, metalness: m.metal || 0, vertexColors: true, side: side === 'd' ? THREE.DoubleSide : THREE.FrontSide };
  if (m.grain || m.palette) {
    var pal = m.palette || [shade(m.color, -0.18), shade(m.color, -0.08), m.color, shade(m.color, 0.08), shade(m.color, 0.16)];
    o.map = grainTex(pal, 11 + key.length * 7); o.color = new THREE.Color(0xffffff);
  } else if (m.pattern) { o.map = patternTex(m.pattern, m.color, 5 + key.length * 3); o.color = new THREE.Color(0xffffff); }
  else o.color = new THREE.Color(m.color || '#8a8a8a').convertSRGBToLinear();
  if (m.glass) { o.transparent = true; o.opacity = 0.28; o.depthWrite = false; }
  if (m.opacity != null && m.opacity < 1) { o.transparent = true; o.opacity = m.opacity; o.depthWrite = false; o.side = THREE.DoubleSide; }
  var mm = new THREE.MeshStandardMaterial(o);
  mm.userData = { key: key, op0: o.opacity == null ? 1 : o.opacity };
  if (m.emit) { mm.emissive = new THREE.Color(m.emit).convertSRGBToLinear(); mm.emissiveIntensity = 0; mm.userData.led = true; LED_M.push(mm); }
  if (opts2 === 'glass') { mm.emissive = ROOM.clone().convertSRGBToLinear(); mm.emissiveIntensity = 0; GLASS_M.push(mm); }
  addFx(mm, opts2 === 'tree' ? 9.0 : 0);
  MATS[k] = mm; return mm;
}

// ------------------------------------------------------------------ geometry: boxes merged by material x option mask
var GROUPS = {};
function grp(matKey, mask, role) {
  var dbl = (role & 16) ? 'd' : 'f', variant = (role & 2) ? 'glass' : ((role & 32) ? 'tree' : ''), cast = (role & 1) ? 0 : 1;
  var k = matKey + '|' + mask + '|' + dbl + '|' + variant + '|' + cast;
  var g = GROUPS[k];
  if (!g) g = GROUPS[k] = { mat: matKey, mask: mask, side: dbl, variant: variant, cast: cast, P: [], N: [], U: [], C: [] };
  return g;
}
var _v = new THREE.Vector3(), _n = new THREE.Vector3(), _m4 = new THREE.Matrix4(), _m3 = new THREE.Matrix3();
var AX = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
// faces: [normal axis, sign, a axis, b axis] with a x b = n (outward winding)
var FACES = [[0, 1, 1, 2], [0, -1, 2, 1], [1, 1, 2, 0], [1, -1, 0, 2], [2, 1, 0, 1], [2, -1, 1, 0]];
function pushTri(g, p, n, uv, c) { for (var i = 0; i < 3; i++) { g.P.push(p[i].x, p[i].y, p[i].z); g.N.push(n.x, n.y, n.z); g.U.push(uv[i][0], uv[i][1]); g.C.push(c, c, c); } }
function boxInto(g, x0, x1, y0, y1, z0, z1, rot, axis, tone, mdef) {
  var hs = [(x1 - x0) / 2, (z1 - z0) / 2, (y1 - y0) / 2];                // three axes: x, y(up), z(plan y)
  var ctr = new THREE.Vector3((x0 + x1) / 2, (z0 + z1) / 2, (y0 + y1) / 2);
  var R = null;
  if (rot) { R = new THREE.Matrix4(); if (axis === 1) R.makeRotationX(rot); else if (axis === 2) R.makeRotationY(-rot); else R.makeRotationZ(rot); }
  var grain = !!(mdef.grain || mdef.palette), pat = !grain && mdef.pattern ? (TILE[mdef.pattern] || 8) : 0;
  var c = 1 + 0.08 * Math.max(-1, Math.min(1, tone || 0));
  var longAx = hs[0] >= hs[1] && hs[0] >= hs[2] ? 0 : (hs[2] >= hs[1] ? 2 : 1);
  for (var f = 0; f < 6; f++) {
    var F = FACES[f], na = F[0], sg = F[1], aa = F[2], ba = F[3];
    if (hs[na] < 1e-5) continue;
    var n = AX[na].clone().multiplyScalar(sg), av = AX[aa], bv = AX[ba];
    var pts = [], uvs = [];
    var corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
    for (var q = 0; q < 4; q++) {
      var p = n.clone().multiplyScalar(hs[na]).addScaledVector(av, corners[q][0] * hs[aa]).addScaledVector(bv, corners[q][1] * hs[ba]);
      if (R) p.applyMatrix4(R);
      p.add(ctr); pts.push(p);
    }
    var nw = n.clone(); if (R) nw.transformDirection(R);
    if (grain) {
      var uAx = (aa === longAx || (ba !== longAx && hs[aa] >= hs[ba])) ? 0 : 1;   // 0: u along a
      for (q = 0; q < 4; q++) { var sa = (corners[q][0] + 1) / 2, sb = (corners[q][1] + 1) / 2;
        uvs.push(uAx === 0 ? [sa * 2 * hs[aa] / 8, sb] : [sb * 2 * hs[ba] / 8, sa]); }
    } else if (pat) {
      var A_, B_;
      if (Math.abs(nw.y) > 0.7) { A_ = AX[0]; B_ = AX[2]; } else { A_ = new THREE.Vector3(0, 1, 0).cross(nw).normalize(); B_ = AX[1]; }
      for (q = 0; q < 4; q++) uvs.push([pts[q].dot(A_) / pat, pts[q].dot(B_) / pat]);
    } else { for (q = 0; q < 4; q++) uvs.push([0, 0]); }
    pushTri(g, [pts[0], pts[1], pts[2]], nw, [uvs[0], uvs[1], uvs[2]], c);
    pushTri(g, [pts[0], pts[2], pts[3]], nw, [uvs[0], uvs[2], uvs[3]], c);
  }
}
function flatGeo(g) { return g.index ? g.toNonIndexed() : g; }
var UNIT = { 1: flatGeo(new THREE.CylinderGeometry(0.5, 0.5, 1, 16)), 2: flatGeo(new THREE.IcosahedronGeometry(0.5, 1)), 3: flatGeo(new THREE.ConeGeometry(0.5, 1, 12)) };
function shapeInto(g, shape, x0, x1, y0, y1, z0, z1, rot, axis) {
  var geo = UNIT[shape], P = geo.attributes.position, N = geo.attributes.normal, Uv = geo.attributes.uv;
  var w = x1 - x0, h = z1 - z0, d = y1 - y0;
  _m4.makeScale(w, h, d);
  if (rot) { var R = new THREE.Matrix4(); if (axis === 1) R.makeRotationX(rot); else if (axis === 2) R.makeRotationY(-rot); else R.makeRotationZ(rot); _m4.premultiply(R); }
  _m4.premultiply(new THREE.Matrix4().makeTranslation((x0 + x1) / 2, (z0 + z1) / 2, (y0 + y1) / 2));
  _m3.getNormalMatrix(_m4);
  for (var i = 0; i < P.count; i++) {
    _v.fromBufferAttribute(P, i).applyMatrix4(_m4); _n.fromBufferAttribute(N, i).applyMatrix3(_m3).normalize();
    g.P.push(_v.x, _v.y, _v.z); g.N.push(_n.x, _n.y, _n.z); g.U.push(Uv.getX(i) * Math.max(1, w) / 4, Uv.getY(i) * Math.max(1, h) / 4); g.C.push(1, 1, 1);
  }
}
function meshInto(g, pts, mdef) {
  var per = mdef.pattern ? (TILE[mdef.pattern] || 8) : 8;
  for (var t = 0; t + 8 < pts.length; t += 9) {
    var A = new THREE.Vector3(pts[t], pts[t + 2], pts[t + 1]), C = new THREE.Vector3(pts[t + 3], pts[t + 5], pts[t + 4]), B = new THREE.Vector3(pts[t + 6], pts[t + 8], pts[t + 7]);
    var n = B.clone().sub(A).cross(C.clone().sub(A)); if (n.lengthSq() < 1e-12) continue; n.normalize();
    var t1 = new THREE.Vector3(0, 1, 0).cross(n); if (t1.lengthSq() < 1e-6) t1.set(1, 0, 0); t1.normalize();
    var t2 = n.clone().cross(t1).normalize(); if (t2.y < 0) t2.multiplyScalar(-1);
    var uv = [A, B, C].map(function (P) { return [P.dot(t1) / per, P.dot(t2) / per]; });
    pushTri(g, [A, B, C], n, uv, 1);
  }
}
(function build() {
  var B = D.boxes, st = D.stride, MN = D.mat_names;
  for (var i = 0; i + st - 1 < B.length; i += st) {
    var mat = MN[B[i + 8]], shape = B[i + 10], role = B[i + 13], mask = B[i + 12];
    var g = grp(mat, mask, role), md = D.mats[mat] || {};
    if (shape === 0) boxInto(g, B[i], B[i + 1], B[i + 2], B[i + 3], B[i + 4], B[i + 5], B[i + 6], B[i + 11], B[i + 7], md);
    else shapeInto(g, shape, B[i], B[i + 1], B[i + 2], B[i + 3], B[i + 4], B[i + 5], B[i + 6], B[i + 11]);
  }
  D.meshes.forEach(function (m) { meshInto(grp(MN[m[0]], m[2], m[3] | 16), m[5], D.mats[MN[m[0]]] || {}); });
})();
var GMESH = [];
Object.keys(GROUPS).forEach(function (k) {
  var g = GROUPS[k]; if (!g.P.length) return;
  var geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(g.P, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(g.N, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(g.U, 2));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(g.C, 3));
  geo.computeBoundingSphere();
  var mesh = new THREE.Mesh(geo, matFor(g.mat, g.side, g.variant));
  mesh.castShadow = !!g.cast && !mesh.material.transparent; mesh.receiveShadow = true; mesh.userData.mask = g.mask; mesh.userData.tree = g.variant === 'tree';
  if (mesh.material.transparent) mesh.renderOrder = 2;
  scene.add(mesh); GMESH.push(mesh);
  g.P = g.N = g.U = g.C = null;
});

// ------------------------------------------------------------------ the far field: a ground disc out to the fogged horizon
(function () {
  var g = new THREE.CircleGeometry(2600, 72); g.rotateX(-Math.PI / 2);
  var P = g.attributes.position, uv = g.attributes.uv, per = TILE[(D.mats[D.ground.mat] || {}).pattern] || 8;
  for (var i = 0; i < P.count; i++) uv.setXY(i, P.getX(i) / per, P.getZ(i) / per);
  g.setAttribute('color', new THREE.Float32BufferAttribute(new Array(P.count * 3).fill(1), 3));
  var m = new THREE.Mesh(g, matFor(D.ground.mat, 'f'));
  m.position.set(CX, D.ground.z - 0.04, CY); m.receiveShadow = true; m.renderOrder = -1; scene.add(m);
})();

// ------------------------------------------------------------------ louvered roofs: instanced blades turning about their own axes
var BLADES = [];
ROOFS.forEach(function (r) {
  if (!r.blades.length) return;
  var prof = r.profile && r.profile.length > 2 ? r.profile : [[-0.333, 0], [-0.25, 0.05], [0.25, 0.05], [0.333, 0], [0.25, -0.035], [-0.25, -0.035]];
  var w0 = Math.max.apply(null, prof.map(function (p) { return p[0]; })) - Math.min.apply(null, prof.map(function (p) { return p[0]; }));
  var t0 = Math.max.apply(null, prof.map(function (p) { return p[1]; })) - Math.min.apply(null, prof.map(function (p) { return p[1]; }));
  // local frame: x = u (across), y = v (up), z = along the blade (-0.5 .. 0.5); right-handed, wound outward
  var pos = [], nor = [], n = prof.length, k, a, b, e;
  var cxp = 0, cyp = 0; prof.forEach(function (p) { cxp += p[0] / n; cyp += p[1] / n; });
  for (k = 0; k < n; k++) {
    a = prof[k]; b = prof[(k + 1) % n];
    var ex = b[0] - a[0], ey = b[1] - a[1], nx = ey, ny = -ex, ln = Math.hypot(nx, ny) || 1; nx /= ln; ny /= ln;
    var mx = (a[0] + b[0]) / 2 - cxp, my = (a[1] + b[1]) / 2 - cyp; if (nx * mx + ny * my < 0) { nx = -nx; ny = -ny; }
    var quad = [[a[0], a[1], -0.5], [b[0], b[1], -0.5], [b[0], b[1], 0.5], [a[0], a[1], 0.5]];
    var v1 = [quad[1][0] - quad[0][0], quad[1][1] - quad[0][1], 0], v2 = [quad[2][0] - quad[0][0], quad[2][1] - quad[0][1], 1];
    var cr = [v1[1] * v2[2] - v1[2] * v2[1], v1[2] * v2[0] - v1[0] * v2[2], v1[0] * v2[1] - v1[1] * v2[0]];
    var order = (cr[0] * nx + cr[1] * ny >= 0) ? [0, 1, 2, 0, 2, 3] : [0, 2, 1, 0, 3, 2];
    order.forEach(function (oi) { pos.push(quad[oi][0], quad[oi][1], quad[oi][2]); nor.push(nx, ny, 0); });
  }
  for (e = -1; e <= 1; e += 2) for (k = 1; k < n - 1; k++) {
    var tri = [prof[0], prof[k], prof[k + 1]];
    var c1 = (tri[1][0] - tri[0][0]) * (tri[2][1] - tri[0][1]) - (tri[1][1] - tri[0][1]) * (tri[2][0] - tri[0][0]);
    if (c1 * e < 0) tri = [tri[0], tri[2], tri[1]];
    tri.forEach(function (p) { pos.push(p[0], p[1], e * 0.5); nor.push(0, 0, e); });
  }
  var geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(new Array(pos.length / 3 * 2).fill(0), 2));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(new Array(pos.length).fill(1), 3));
  var im = new THREE.InstancedMesh(geo, matFor(r.blade_mat, 'f'), r.blades.length);
  im.castShadow = true; im.receiveShadow = true; im.frustumCulled = false; im.userData.mask = r.mask;
  scene.add(im);
  var acr = r.across ? P3(r.across[0], r.across[1], r.across[2]) : null;
  BLADES.push({ roof: r, mesh: im, w0: w0, t0: t0, across: acr });
});
var _M = new THREE.Matrix4();
function setLouvers(deg) {
  var a = deg * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a), up = new THREE.Vector3(0, 1, 0);
  BLADES.forEach(function (B) {
    B.roof.blades.forEach(function (bl, i) {
      var piv = P3(bl[0], bl[1], bl[2]), ax = P3(bl[3], bl[4], bl[5]).normalize();
      var acr = B.across || new THREE.Vector3(1, 0, 0);
      if (!B.across) { acr = up.clone().cross(ax); if (acr.lengthSq() < 1e-6) acr.set(1, 0, 0); acr.normalize(); }
      var c0 = acr.clone().multiplyScalar(ca).addScaledVector(up, sa).multiplyScalar(1.03 * bl[7] / (B.w0 || bl[7]));   // 3% wider: closed blades seal
      var c1 = acr.clone().multiplyScalar(-sa).addScaledVector(up, ca).multiplyScalar(bl[8] / (B.t0 || bl[8]));
      var c2 = c0.clone().cross(c1).normalize().multiplyScalar(bl[6]);
      _M.set(c0.x, c1.x, c2.x, piv.x, c0.y, c1.y, c2.y, piv.y, c0.z, c1.z, c2.z, piv.z, 0, 0, 0, 1);
      B.mesh.setMatrixAt(i, _M);
    });
    B.mesh.instanceMatrix.needsUpdate = true;
  });
}

// ------------------------------------------------------------------ roof screens: fabric + bottom bar, from the cassette down
var SCR = [];
(function () {
  if (!SCREENS.length) return;
  SCREENS.forEach(function (s) {
    var md = D.mats[s.mat] || { color: '#1b1c1e', opacity: 0.8 };
    var open = 1 - (md.opacity == null ? 0.8 : md.opacity);
    // the shadow: a fine random weave the shadow map samples at random, so the shade under a screen is partial (the fabric's openness)
    var dc = document.createElement('canvas'); dc.width = dc.height = 64; var g = dc.getContext('2d'), id = g.createImageData(64, 64), rs = 97;
    for (var i = 0; i < 4096; i++) { rs = (rs * 16807) % 2147483647; var v = rs / 2147483647 < open ? 0 : 255; id.data[i * 4] = id.data[i * 4 + 1] = id.data[i * 4 + 2] = v; id.data[i * 4 + 3] = 255; }
    g.putImageData(id, 0, 0);
    var dt = new THREE.CanvasTexture(dc); dt.magFilter = dt.minFilter = THREE.NearestFilter; dt.generateMipmaps = false; dt.wrapS = dt.wrapT = THREE.RepeatWrapping;
    var fm = new THREE.MeshStandardMaterial({ color: new THREE.Color(md.color || '#1b1c1e').convertSRGBToLinear(), roughness: md.rough == null ? 0.9 : md.rough,
      metalness: 0, transparent: true, opacity: md.opacity == null ? 0.8 : md.opacity, depthWrite: false, side: THREE.DoubleSide,
      map: patternTex('fabric', md.color || '#1b1c1e', 7) });
    fm.map.encoding = THREE.sRGBEncoding; addFx(fm);
    var fab = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), fm);
    fab.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, alphaMap: dt, alphaTest: 0.5, side: THREE.DoubleSide });
    fab.castShadow = open < 0.97; fab.receiveShadow = false; fab.renderOrder = 3;
    var hem = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), matFor((s.hem && s.hem.mat) || 'lvmetal', 'f'));
    hem.geometry.setAttribute('color', new THREE.Float32BufferAttribute(new Array(hem.geometry.attributes.position.count * 3).fill(1), 3));
    hem.castShadow = true; hem.receiveShadow = true;
    scene.add(fab); scene.add(hem);
    SCR.push({ s: s, fab: fab, hem: hem, dtex: dt });
  });
})();
function placeScreen(o, down) {
  var s = o.s, hemH = (s.hem && s.hem.h) || 0.17, hemT = (s.hem && s.hem.t) || 0.12, tw = s.track_w || 0.12;
  var zt = s.z_top, zh = zt - hemH - down * (s.max_drop - hemH);          // the bottom bar's underside (louvered.draw_screen)
  var alongX = s.plane === 'y' || (s.plane == null && Math.abs(s.b[0] - s.a[0]) > Math.abs(s.b[1] - s.a[1]));
  var a = alongX ? Math.min(s.a[0], s.b[0]) + tw : Math.min(s.a[1], s.b[1]) + tw, b = alongX ? Math.max(s.a[0], s.b[0]) - tw : Math.max(s.a[1], s.b[1]) - tw;
  var line = s.line != null ? s.line : (alongX ? s.a[1] : s.a[0]), L = Math.max(0.01, b - a), mid = (a + b) / 2;
  var fh = zt - (zh + hemH);
  o.fab.visible = o.vis && fh > 0.02; o.hem.visible = o.vis;
  if (fh > 0.02) {
    o.fab.scale.set(L, fh, 1); o.fab.position.copy(alongX ? P3(mid, line, zh + hemH + fh / 2) : P3(line, mid, zh + hemH + fh / 2));
    o.fab.rotation.set(0, alongX ? 0 : Math.PI / 2, 0);
    o.fab.material.map.repeat.set(L / 1.2, fh / 1.2); o.dtex.repeat.set(L * 2.5, fh * 2.5);
  }
  o.hem.scale.copy(alongX ? new THREE.Vector3(L, hemH, hemT) : new THREE.Vector3(hemT, hemH, L));
  o.hem.position.copy(alongX ? P3(mid, line, zh + hemH / 2) : P3(line, mid, zh + hemH / 2));
}

// ------------------------------------------------------------------ the fixtures' lenses: halos
var HALO;
(function () {
  if (!FX.length) return;
  var pos = new Float32Array(FX.length * 3), sz = new Float32Array(FX.length), on = new Float32Array(FX.length);
  FX.forEach(function (f, i) { var p = P3(f[0], f[1], f[2]); if (f[6] === 0) p.addScaledVector(P3(f[3], f[4], 0), -0.06); pos.set([p.x, p.y, p.z], i * 3);
    sz[i] = f[6] === 0 ? 0.55 : (f[6] === 1 ? 0.75 : 0); });
  var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('aSize', new THREE.BufferAttribute(sz, 1));
  g.setAttribute('aOn', new THREE.BufferAttribute(on, 1));
  var m = new THREE.ShaderMaterial({ uniforms: { uGlow: { value: 0 }, uScale: { value: 400 }, uCol: { value: new THREE.Color('#ffd7a3') } },
    vertexShader: 'attribute float aSize; attribute float aOn; varying float vOn; uniform float uScale; void main(){ vOn = aOn; vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_PointSize = min(160.0, aSize * uScale / max(0.5, -mv.z)); gl_Position = projectionMatrix * mv; }',
    fragmentShader: 'uniform float uGlow; uniform vec3 uCol; varying float vOn; void main(){ float r = length(gl_PointCoord - 0.5) * 2.0; float a = pow(max(1.0 - r, 0.0), 2.4) * uGlow * vOn; if (a < 0.004) discard; gl_FragColor = vec4(uCol * a, a); }',
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false, toneMapped: false });
  HALO = new THREE.Points(g, m); HALO.frustumCulled = false; HALO.renderOrder = 5; scene.add(HALO);
})();

// ------------------------------------------------------------------ the sun at the address (scene.sun_vector, DST like cycles.sun_at)
var RAD = Math.PI / 180;
function mtOffset(y, m, d, base) {
  if (base !== -6 && base !== -7) return base;
  var s = 8 + (7 - new Date(Date.UTC(y, 2, 8)).getUTCDay()) % 7, e = 1 + (7 - new Date(Date.UTC(y, 10, 1)).getUTCDay()) % 7, t = Date.UTC(y, m - 1, d);
  return (t >= Date.UTC(y, 2, s) && t < Date.UTC(y, 10, e)) ? -6 : -7;
}
function sunAt(date, minutes) {
  var p = date.split('-').map(Number), y = p[0], mo = p[1], d = p[2];
  var off = mtOffset(y, mo, d, +SITE.utc), n = Math.round((Date.UTC(y, mo - 1, d) - Date.UTC(y, 0, 1)) / 864e5) + 1, hour = minutes / 60;
  var g = 2 * Math.PI / 365 * (n - 1 + (hour - 12) / 24);
  var eqt = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
  var decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  var tst = hour * 60 + eqt + 4 * SITE.lon - 60 * off, ha = (tst / 4 - 180) * RAD, lat = SITE.lat * RAD;
  var cz = Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(ha);
  var el = Math.PI / 2 - Math.acos(Math.max(-1, Math.min(1, cz)));
  var az = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat)) / RAD + 180;
  var rel = (az - SITE.rear_az) * RAD;
  return { x: -Math.sin(rel) * Math.cos(el), y: Math.cos(rel) * Math.cos(el), z: Math.sin(el), el: el / RAD, az: ((az % 360) + 360) % 360, off: off };
}
var WIND = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
function clock(m) { m = Math.round(m); var h = Math.floor(m / 60) % 24, mi = m % 60, ap = h < 12 ? 'AM' : 'PM', h12 = h % 12 || 12; return h12 + ':' + (mi < 10 ? '0' : '') + mi + ' ' + ap; }
var RS = {};
function riseSet(date) {
  if (RS[date]) return RS[date];
  var rise = null, set = null, prev = sunAt(date, 180).el;
  for (var m = 182; m <= 1380; m += 2) { var e = sunAt(date, m).el; if (prev < -0.833 && e >= -0.833 && rise === null) rise = m; if (prev >= -0.833 && e < -0.833) set = m; prev = e; }
  return (RS[date] = [rise, set]);
}

// ------------------------------------------------------------------ sky, sun and night by the sun's height
function lerpC(a, b, t) { return a.clone().lerp(b, Math.max(0, Math.min(1, t))); }
function C(h) { return new THREE.Color(h); }
var SKY_K = [   // elevation (deg), zenith, horizon (display sRGB)
  [-18, C('#03050b'), C('#070b16')], [-11, C('#060b1a'), C('#121a33')], [-6, C('#0f1a36'), C('#2f3758')], [-3, C('#1d2d55'), C('#5a5873')],
  [0, C('#2f4c80'), C('#c98f6a')], [4, C('#3a63a0'), C('#e6b48a')], [10, C('#3c6eae'), C('#d9d6cf')], [25, C('#3772b6'), C('#cfdeec')], [60, C('#2c69b2'), C('#c9dcee')]];
function skyAt(el) {
  for (var i = 0; i < SKY_K.length - 1; i++) { var a = SKY_K[i], b = SKY_K[i + 1];
    if (el <= b[0]) { var t = el <= a[0] ? 0 : (el - a[0]) / (b[0] - a[0]); return [lerpC(a[1], b[1], t), lerpC(a[2], b[2], t)]; } }
  var l = SKY_K[SKY_K.length - 1]; return [l[1].clone(), l[2].clone()];
}
function sstep(a, b, x) { var t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); }
function sunRGB(el) { var t = Math.pow(Math.max(0, Math.min(1, (30 - el) / 27)), 1.5); return new THREE.Color(1, 0.955 + (0.78 - 0.955) * t, 0.89 + (0.55 - 0.89) * t); }
var NIGHT = 0, SUN = null;
var REG_PTS = [];
function applySun() {
  var s = sunAt(S.date, S.min); SUN = s;
  var el = s.el, dir = P3(s.x, s.y, s.z).normalize();
  var ks = skyAt(el);
  skyU.uTop.value.copy(ks[0]); skyU.uHor.value.copy(ks[1]); skyU.uGnd.value.copy(ks[1]).multiplyScalar(0.85);
  skyU.uSun.value.copy(dir);
  skyU.uSunCol.value.copy(lerpC(C('#ffd2a0'), C('#fff6e6'), sstep(2, 30, el)));
  skyU.uGlow.value = sstep(-10, -1, el) * (0.55 + 0.6 * (1 - sstep(4, 35, el)));
  skyU.uDisc.value = sstep(-1.5, 0.5, el) * 1.4;
  scene.fog.color.copy(ks[1]);         // r128 mixes the fog in after the tone mapping and the sRGB encoding: the sky's own horizon colour
  var day = sstep(-1.0, 6.0, el), high = sstep(4, 40, el);
  sun.intensity = day * (1.05 + 0.6 * high);
  sun.color.copy(sunRGB(el));
  hemi.color.copy(ks[0]).convertSRGBToLinear().lerp(new THREE.Color(0.85, 0.9, 1.0), 0.45);
  hemi.groundColor.copy(C('#5a5444')).convertSRGBToLinear().multiplyScalar(0.25 + 0.75 * day);
  hemi.intensity = 0.035 + 0.17 * sstep(-12, -2, el) + 0.33 * sstep(-2, 25, el);
  NIGHT = 1 - sstep(-4, 3, el);
  moon.intensity = 0.07 * (1 - sstep(-12, -3, el));
  renderer.toneMappingExposure = 1.0 + 0.3 * NIGHT;
  stars.material.opacity = 0.9 * (1 - sstep(-14, -7, el));
  // the shadow box: the deck, the house beside it, and where their shadows fall
  if (day > 0) {
    var H = DK.z_max + 2, ext = 140;
    var gx = Math.max(-ext, Math.min(ext, -s.x / Math.max(0.06, s.z) * H)), gy = Math.max(-ext, Math.min(ext, -s.y / Math.max(0.06, s.z) * H));
    var x0 = DK.x0 - 14, x1 = DK.x1 + 14, y0 = DK.y0 - 10, y1 = DK.y1 + 14;
    var xs = [x0, x1, x0 + Math.min(0, gx), x1 + Math.max(0, gx)], ys = [y0, y1, y0 + Math.min(0, gy), y1 + Math.max(0, gy)];
    var bx0 = Math.min.apply(null, xs), bx1 = Math.max.apply(null, xs), by0 = Math.min.apply(null, ys), by1 = Math.max.apply(null, ys);
    var ctr = P3((bx0 + bx1) / 2, (by0 + by1) / 2, DK.top / 2);
    sun.position.copy(ctr).addScaledVector(dir, 400); sun.target.position.copy(ctr); sun.target.updateMatrixWorld(); sun.updateMatrixWorld();
    var cam = sun.shadow.camera; cam.position.copy(sun.position); cam.lookAt(ctr); cam.updateMatrixWorld(); cam.matrixWorldInverse.copy(cam.matrixWorld).invert();
    var mnx = 1e9, mxx = -1e9, mny = 1e9, mxy = -1e9, mnz = 1e9, mxz = -1e9;
    [bx0, bx1].forEach(function (x) { [by0, by1].forEach(function (y) { [-2, H + 6].forEach(function (z) {
      var p = P3(x, y, z).applyMatrix4(cam.matrixWorldInverse);
      mnx = Math.min(mnx, p.x); mxx = Math.max(mxx, p.x); mny = Math.min(mny, p.y); mxy = Math.max(mxy, p.y); mnz = Math.min(mnz, p.z); mxz = Math.max(mxz, p.z); }); }); });
    cam.left = mnx - 1; cam.right = mxx + 1; cam.bottom = mny - 1; cam.top = mxy + 1; cam.near = Math.max(1, -mxz - 220); cam.far = -mnz + 8;
    cam.updateProjectionMatrix();
    renderer.shadowMap.autoUpdate = true;
  } else { renderer.shadowMap.autoUpdate = false; }
  applyGlow();
  invalidate();
}
function applyGlow() {
  var lit = NIGHT;
  FXU.fxGain.value = lit;
  LED_M.forEach(function (m) { m.emissiveIntensity = 0.1 + 2.6 * lit; });
  GLASS_M.forEach(function (m) { m.emissiveIntensity = 0.38 * lit; m.opacity = m.userData.op0 + (Math.min(0.92, m.userData.op0 + 0.6) - m.userData.op0) * lit; });
  if (HALO) HALO.material.uniforms.uGlow.value = lit;
}

// ------------------------------------------------------------------ options -> what shows
function applyOptions() {
  fixRequires();
  var c = comboOf(S.on);
  GMESH.forEach(function (m) { m.visible = shows(m.userData.mask, c) && (S.trees || !m.userData.tree); });
  BLADES.forEach(function (B) { B.mesh.visible = shows(B.roof.mask, c); });
  SCR.forEach(function (o) { o.vis = shows(o.s.mask, c); placeScreen(o, S.scr[o.s.id]); });
  for (var i = 0; i < FXN; i++) {
    var f = FX[i];
    if (!f) { fxA[i].set(1e5, 0, 0, 0); fxB[i].set(0, 0, 0, 0); continue; }
    var p = P3(f[0], f[1], f[2]), a = P3(f[3], f[4], f[5]);
    if (!shows(f[9], c)) { fxA[i].set(p.x, p.y, p.z, 0); continue; }      // off: keeps its place in the x order
    var gain = FX_GAIN[f[6]] * f[7];
    fxA[i].set(p.x, p.y, p.z, gain);
    if (f[6] === 0) fxB[i].set(a.x, a.y, a.z, Math.cos(62 * RAD));
    else if (f[6] === 1) fxB[i].set(0, -1, 0, 2.0);
    else fxB[i].set(a.x, a.y, a.z, 3.0 + f[8]);
  }
  if (HALO) { var on = HALO.geometry.attributes.aOn; for (var j = 0; j < FX.length; j++) on.array[j] = shows(FX[j][9], c) ? 1 : 0; on.needsUpdate = true; }
  var roofOn = ROOFS.some(function (r) { return shows(r.mask, c); });
  $('g-louv').hidden = !roofOn || !BLADES.length;
  var scrOn = SCR.some(function (o) { return o.vis; });
  $('g-scr').hidden = !scrOn;
  renderer.shadowMap.needsUpdate = true;
  syncUI(); applyGlow(); invalidate();
}

// ------------------------------------------------------------------ camera: orbit / pan / zoom, preset views
var stageW = 1, stageH = 1;
var cam = new THREE.PerspectiveCamera(50, 1, 0.3, 4000);
var tgt = new THREE.Vector3(), sph = new THREE.Spherical(30, 1, 0), FOV = 50;
var VIEWS = {}; D.views.forEach(function (v) { VIEWS[v.key] = v; });
if (Q.get('cam') && Q.get('at')) {                 // ?cam=x,y,z&at=x,y,z (plan feet) [&fov=]: a custom view, e.g. a link to one spot
  VIEWS.custom = { key: 'custom', label: 'Custom', pos: Q.get('cam').split(',').map(Number), at: Q.get('at').split(',').map(Number), fov: +(Q.get('fov') || 55), fixed: true };
  S.view = 'custom';
}
function viewPose(v) {
  var pos = P3(v.pos[0], v.pos[1], v.pos[2]), at = P3(v.at[0], v.at[1], v.at[2]), fov = v.fov || 50;
  var asp = stageW / Math.max(1, stageH);
  // a view is framed for a 1.4:1 screen: on a narrower one keep its width by opening the lens (a measured station stays put)
  var hh = Math.atan(Math.tan(fov * RAD / 2) * 1.4), need = 2 * Math.atan(Math.tan(hh) / asp) / RAD;
  if (need > fov) fov = Math.min(v.fixed ? 80 : 72, need);
  if (v.fit && !v.fixed) {                           // still too narrow: step back until the deck's width fits
    var d = pos.distanceTo(at), hx = Math.atan(Math.tan(fov * RAD / 2) * asp), dd = (v.fit / 2) / Math.tan(hx);
    if (dd > d) { var k = Math.min(1.8, dd / d); pos = at.clone().add(pos.clone().sub(at).multiplyScalar(k)); }
  }
  return { pos: pos, at: at, fov: fov };
}
function setPose(p) { tgt.copy(p.at); sph.setFromVector3(p.pos.clone().sub(p.at)); FOV = p.fov; updCam(); }
function updCam() {
  sph.makeSafe(); sph.phi = Math.max(0.03, Math.min(1.72, sph.phi)); sph.radius = Math.max(1.0, Math.min(700, sph.radius));
  cam.position.copy(tgt).add(new THREE.Vector3().setFromSpherical(sph));
  if (cam.position.y < -1.5) cam.position.y = -1.5;
  cam.fov = FOV; cam.aspect = stageW / Math.max(1, stageH); cam.updateProjectionMatrix(); cam.lookAt(tgt);
  FXU.fxFocus.value.copy(tgt);
  if (HALO) HALO.material.uniforms.uScale.value = stageH * DPR / (2 * Math.tan(FOV * RAD / 2));
  invalidate();
}
var tween = null;
function goView(key, instant) {
  var v = VIEWS[key] || D.views[0]; S.view = v.key;
  var p = viewPose(v);
  if (instant || RM || STILL) { tween = null; setPose(p); }
  else tween = { t: 0, from: { pos: cam.position.clone(), at: tgt.clone(), fov: FOV }, to: p };
  syncUI(); writeURL();
}
function stepTween(dt) {
  if (!tween) return false;
  tween.t = Math.min(1, tween.t + dt / 0.85); var e = tween.t < 0.5 ? 4 * Math.pow(tween.t, 3) : 1 - Math.pow(-2 * tween.t + 2, 3) / 2;
  setPose({ pos: tween.from.pos.clone().lerp(tween.to.pos, e), at: tween.from.at.clone().lerp(tween.to.at, e), fov: tween.from.fov + (tween.to.fov - tween.from.fov) * e });
  if (tween.t >= 1) tween = null;
  return true;
}
function orbit(dx, dy) { sph.theta -= dx * 0.0065; sph.phi -= dy * 0.0065; tween = null; updCam(); }
function pan(dx, dy) {
  var k = sph.radius * 2 * Math.tan(FOV * RAD / 2) / Math.max(1, stageH);
  var right = new THREE.Vector3().setFromMatrixColumn(cam.matrix, 0), up = new THREE.Vector3().setFromMatrixColumn(cam.matrix, 1);
  tgt.addScaledVector(right, -dx * k).addScaledVector(up, dy * k); tween = null; updCam();
}
function zoom(f) {
  var r = sph.radius * f;
  if (r < 3.0 && f < 1) { var fwd = tgt.clone().sub(cam.position).normalize(); tgt.addScaledVector(fwd, 3.0 - r); r = 3.0; }   // walk forward past the target
  sph.radius = r; tween = null; updCam();
}
var el3 = renderer.domElement, drag = null, touches = null;
el3.addEventListener('contextmenu', function (e) { e.preventDefault(); });
el3.addEventListener('mousedown', function (e) { drag = { x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey || e.button === 1 }; hideHint(); e.preventDefault(); });
window.addEventListener('mousemove', function (e) { if (!drag) return; var dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY; if (drag.pan) pan(dx, dy); else orbit(dx, dy); });
window.addEventListener('mouseup', function () { drag = null; });
el3.addEventListener('wheel', function (e) { e.preventDefault(); hideHint(); zoom(Math.exp((e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY) * (e.ctrlKey ? 0.01 : 0.0012))); }, { passive: false });
function tinfo(e) { var t = e.touches; if (t.length === 1) return { n: 1, x: t[0].clientX, y: t[0].clientY };
  return { n: 2, x: (t[0].clientX + t[1].clientX) / 2, y: (t[0].clientY + t[1].clientY) / 2, d: Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY) }; }
el3.addEventListener('touchstart', function (e) { e.preventDefault(); hideHint(); touches = tinfo(e); }, { passive: false });
el3.addEventListener('touchmove', function (e) {
  e.preventDefault(); if (!touches) return; var t = tinfo(e);
  if (t.n !== touches.n) { touches = t; return; }
  if (t.n === 1) orbit(t.x - touches.x, t.y - touches.y);
  else { if (touches.d > 0 && t.d > 0) zoom(touches.d / t.d); pan(t.x - touches.x, t.y - touches.y); }
  touches = t;
}, { passive: false });
el3.addEventListener('touchend', function (e) { touches = e.touches.length ? tinfo(e) : null; }, { passive: false });
document.addEventListener('gesturestart', function (e) { e.preventDefault(); });
var hintEl = $('hint');
if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) hintEl.textContent = 'Drag to turn \u00b7 pinch to zoom \u00b7 two fingers to move';
function hideHint() { if (hintEl) { hintEl.classList.add('gone'); hintEl = null; } }
if (STILL || NOUI) $('hint').hidden = true; else setTimeout(hideHint, 9000);

// ------------------------------------------------------------------ the panel
function el(tag, attrs, html) { var e = document.createElement(tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (html != null) e.innerHTML = html; return e; }
var chips = $('chips');
chips.appendChild(el('span', { class: 'chip base' }, '<span class="tick"></span>Base deck'));
OPT.forEach(function (o) {
  var b = el('button', { type: 'button', class: 'chip', 'data-opt': o.key, 'aria-pressed': 'false', id: 'opt-' + o.key }, '<span class="tick"></span>' + o.label);
  b.addEventListener('click', function () {
    S.on[o.key] = !S.on[o.key];
    if (S.on[o.key]) o.requires.forEach(function (r) { S.on[r] = true; });
    else OPT.forEach(function (p) { if (p.requires.indexOf(o.key) >= 0) S.on[p.key] = false; });
    applyOptions(); writeURL();
  });
  chips.appendChild(b);
});
var seasons = $('seasons');
SEASONS.forEach(function (s) { var b = el('button', { type: 'button', class: 'btn', 'data-date': s[2], id: 'season-' + s[0] }, s[1]);
  b.addEventListener('click', function () { S.date = s[2]; dateChanged(); }); seasons.appendChild(b); });
var tIn = $('t'), dIn = $('date');
tIn.value = S.min; dIn.value = S.date;
tIn.addEventListener('input', function () { S.min = +tIn.value; stopPlay(); applySun(); syncUI(); writeURLsoon(); });
dIn.addEventListener('change', function () { if (/^\d{4}-\d\d-\d\d$/.test(dIn.value)) { S.date = dIn.value; dateChanged(); } });
function dateChanged() { applySun(); paintTrack(); syncUI(); writeURL(); }
function paintTrack() {
  var stops = [];
  for (var m = 300; m <= 1380; m += 30) { var e = sunAt(S.date, m).el, k = skyAt(e)[e > 2 ? 0 : 1].clone(); if (e > 2) k.lerp(C('#8fb6dc'), 0.5); stops.push('#' + k.getHexString() + ' ' + ((m - 300) / 10.8).toFixed(1) + '%'); }
  tIn.style.setProperty('--track', 'linear-gradient(90deg,' + stops.join(',') + ')');
}
var playBtn = $('play');
playBtn.addEventListener('click', function () { if (S.playing) stopPlay(); else { S.playing = true; if (S.min >= 1375) S.min = 300; playBtn.setAttribute('aria-label', 'Pause'); $('playpath').setAttribute('d', 'M4 2.5h3v11H4zM9 2.5h3v11H9z'); } });
function stopPlay() { if (!S.playing) return; S.playing = false; playBtn.setAttribute('aria-label', 'Play the day'); $('playpath').setAttribute('d', 'M4 2.5v11l9-5.5z'); writeURL(); }
var lv = $('lv');
if (ROOF) { lv.min = ROOF.angle_min; lv.max = ROOF.angle_max; }
lv.value = S.louver;
lv.addEventListener('input', function () { S.louverGoal = null; S.louver = +lv.value; setLouvers(S.louver); renderer.shadowMap.needsUpdate = true; syncUI(); invalidate(); writeURLsoon(); });
$('lvOpen').addEventListener('click', function () { S.louverGoal = ROOF ? ROOF.angle_open : 90; });
$('lvClose').addEventListener('click', function () { S.louverGoal = ROOF ? ROOF.angle_min : 0; });
var sc = $('sc'), sides = $('sides');
var SIDES = []; SCREENS.forEach(function (s) { if (SIDES.indexOf(s.side) < 0) SIDES.push(s.side); });
SIDES.forEach(function (sd) { var b = el('button', { type: 'button', class: 'chip', 'aria-pressed': 'true', id: 'side-' + sd }, '<span class="tick"></span>' + sd.charAt(0).toUpperCase() + sd.slice(1));
  b.addEventListener('click', function () { S.sel[sd] = !S.sel[sd]; if (!SIDES.some(function (x) { return S.sel[x]; })) S.sel[sd] = true; syncUI(); }); sides.appendChild(b); });
function selScreens() { return SCR.filter(function (o) { return S.sel[o.s.side] && o.vis; }); }
sc.addEventListener('input', function () { var v = +sc.value / 100; selScreens().forEach(function (o) { S.scrGoal[o.s.id] = null; S.scr[o.s.id] = v; placeScreen(o, v); });
  renderer.shadowMap.needsUpdate = true; syncUI(); invalidate(); writeURLsoon(); });
$('scUp').addEventListener('click', function () { selScreens().forEach(function (o) { S.scrGoal[o.s.id] = 0; }); });
$('scDown').addEventListener('click', function () { selScreens().forEach(function (o) { S.scrGoal[o.s.id] = 1; }); });
var vwrap = $('views'), vbar = $('vbar');
D.views.forEach(function (v) {
  [vwrap, vbar].forEach(function (host, hi) { var b = el('button', { type: 'button', class: 'btn', 'data-view': v.key, id: (hi ? 'vb-' : 'view-') + v.key }, v.label);
    b.addEventListener('click', function () { goView(v.key); }); host.appendChild(b); });
});
var HAS_TREES = GMESH.some(function (m) { return m.userData.tree; });
if (HAS_TREES) [vwrap, vbar].forEach(function (host, hi) {
  var b = el('button', { type: 'button', class: 'btn trees', id: hi ? 'vb-trees' : 'trees', 'aria-pressed': 'true' }, 'Trees');
  b.addEventListener('click', function () { S.trees = !S.trees; applyOptions(); writeURL(); }); host.appendChild(b); });
var panel = $('panel'), fold = $('fold');
fold.addEventListener('click', function () { var f = panel.classList.toggle('folded'); fold.setAttribute('aria-expanded', f ? 'false' : 'true');
  fold.setAttribute('aria-label', f ? 'Show the controls' : 'Hide the controls'); $('foldlab').textContent = f ? 'Show controls' : 'Hide controls';
  panel.scrollTop = 0; setTimeout(resize, 30); });
if (NOUI) { panel.hidden = true; vbar.hidden = true; }
$('note').textContent = 'Sun position for ' + D.address + ' (' + SITE.lat.toFixed(3) + '°, ' + SITE.lon.toFixed(3) + '°), local clock time. Lights switch on at dusk.';
function onLabel() { var ks = OPT.filter(function (o) { return S.on[o.key]; }).map(function (o) { return o.short.toLowerCase(); }); return 'Base deck' + (ks.length ? ' + ' + ks.join(' + ') : ''); }
function dateLabel(d) { var p = d.split('-').map(Number); return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][p[1] - 1] + ' ' + p[2]; }
function sunWords(s) { if (s.el < -0.833) return 'sun ' + Math.round(-s.el) + '° below the horizon'; return 'sun ' + WIND[Math.floor((s.az + 11.25) / 22.5) % 16] + ', ' + Math.round(s.el) + '° up'; }
function syncUI() {
  OPT.forEach(function (o) { var b = $('opt-' + o.key); if (!b) return; b.setAttribute('aria-pressed', S.on[o.key] ? 'true' : 'false');
    b.title = o.requires.length && !o.requires.every(function (r) { return S.on[r]; }) ? 'Adds ' + o.requires.map(function (r) { return OBYKEY[r].label; }).join(', ') + ' too' : ''; });
  if (document.activeElement !== tIn) tIn.value = S.min;
  dIn.value = S.date;
  SEASONS.forEach(function (s) { var b = $('season-' + s[0]); if (b) b.classList.toggle('on', S.date === s[2]); });
  var s = SUN || sunAt(S.date, S.min);
  $('tlab').textContent = clock(S.min);
  var rs = riseSet(S.date);
  $('sunlab').textContent = dateLabel(S.date) + ' · ' + sunWords(s) + (rs[0] ? ' · sunrise ' + clock(rs[0]) + ', sunset ' + clock(rs[1]) : '');
  if (document.activeElement !== lv) lv.value = Math.round(S.louver);
  $('lvlab').textContent = Math.round(S.louver) + '°';
  $('lvnote').textContent = S.louver < 2 ? 'Closed' : (Math.abs(S.louver - 90) < 2 ? 'Open, blades on edge' : (S.louver > 90 ? 'Past open' : 'Partly open'));
  var sel = selScreens(), avg = sel.length ? sel.reduce(function (a, o) { return a + S.scr[o.s.id]; }, 0) / sel.length : 0;
  if (document.activeElement !== sc) sc.value = Math.round(avg * 100);
  $('sclab').textContent = Math.round(avg * 100) + '% down';
  SIDES.forEach(function (sd) { var b = $('side-' + sd); if (b) b.setAttribute('aria-pressed', S.sel[sd] ? 'true' : 'false'); });
  document.querySelectorAll('[data-view]').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-view') === S.view); });
  document.querySelectorAll('.btn.trees').forEach(function (b) { b.setAttribute('aria-pressed', S.trees ? 'true' : 'false'); b.classList.toggle('on', S.trees); });
  $('state').textContent = onLabel() + ' · ' + dateLabel(S.date) + ', ' + clock(S.min) + ' · ' + sunWords(s);
}
var urlTimer = null;
function writeURLsoon() { clearTimeout(urlTimer); urlTimer = setTimeout(writeURL, 400); }
function writeURL() {
  if (STILL) return;
  try {
    var p = new URLSearchParams(location.search);
    var on = OPT.filter(function (o) { return S.on[o.key]; }).map(function (o) { return o.key; });
    if (on.length) p.set('opts', on.join(',')); else p.delete('opts');
    p.set('date', S.date); p.set('t', Math.floor(S.min / 60) + ':' + ('0' + Math.round(S.min % 60)).slice(-2));
    if (ROOF) p.set('louver', Math.round(S.louver)); p.set('view', S.view);
    if (!S.trees) p.set('trees', '0'); else p.delete('trees');
    history.replaceState(null, '', location.pathname + '?' + p.toString() + location.hash);
  } catch (e) { /* a sandboxed frame: the state stays in the page */ }
}

// ------------------------------------------------------------------ size, loop
function resize() {
  var w = Math.max(1, stage.clientWidth), h = Math.max(1, stage.clientHeight);
  if (w === stageW && h === stageH) return;
  var first = stageW === 1;
  stageW = w; stageH = h; renderer.setSize(w, h, true);
  if (first) goView(S.view, true); else updCam();
}
if (window.ResizeObserver) new ResizeObserver(function () { resize(); }).observe(stage);
window.addEventListener('resize', resize);
var dirty = true, last = performance.now(), frames = 0, ftime = 0;
function invalidate() { dirty = true; }
function step(dt) {
  var anim = stepTween(dt);
  if (S.louverGoal != null) {
    var d = S.louverGoal - S.louver, sp = 45 * dt;
    if (Math.abs(d) <= sp) { S.louver = S.louverGoal; S.louverGoal = null; writeURL(); } else S.louver += Math.sign(d) * sp;
    setLouvers(S.louver); renderer.shadowMap.needsUpdate = true; anim = true; syncUI();
  }
  SCR.forEach(function (o) { var gl_ = S.scrGoal[o.s.id]; if (gl_ == null) return; var d = gl_ - S.scr[o.s.id], sp = 0.4 * dt;
    if (Math.abs(d) <= sp) { S.scr[o.s.id] = gl_; S.scrGoal[o.s.id] = null; } else S.scr[o.s.id] += Math.sign(d) * sp;
    placeScreen(o, S.scr[o.s.id]); renderer.shadowMap.needsUpdate = true; anim = true; syncUI(); });
  if (S.playing) { S.min += dt * 50; if (S.min >= 1380) { S.min = 1380; stopPlay(); } applySun(); syncUI(); anim = true; }
  return anim;
}
function loop(now) {
  requestAnimationFrame(loop);
  var dt = Math.min(0.5, (now - last) / 1000); last = now;      // a slow frame still moves the louvers / screens / clock in real time
  if (step(dt)) dirty = true;
  if (!dirty) return;
  dirty = false;
  var t0 = performance.now();
  renderer.render(scene, cam);
  if (PERF) { gl.finish(); ftime += performance.now() - t0; frames++; }
}
// QA / embedding hooks
window.cfg = {
  state: S, set: function (o) {
    if (o.opts) { S.on = {}; o.opts.forEach(function (k) { S.on[k] = true; }); }
    if (o.date) S.date = o.date; if (o.t != null) S.min = o.t;
    if (o.louver != null) { S.louver = o.louver; S.louverGoal = null; setLouvers(S.louver); }
    if (o.screens != null) SCR.forEach(function (s) { S.scr[s.s.id] = o.screens; S.scrGoal[s.s.id] = null; });
    applyOptions(); applySun(); if (o.view) goView(o.view, true); syncUI(); renderer.render(scene, cam); },
  render: function () { renderer.render(scene, cam); },
  timeFrames: function (n) { var px = new Uint8Array(4); renderer.render(scene, cam); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    var t0 = performance.now(); for (var i = 0; i < n; i++) { renderer.shadowMap.needsUpdate = true; renderer.render(scene, cam); }
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); return (performance.now() - t0) / n; },
  info: function () { return { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, meshes: GMESH.length, fixtures: FX.length, fxn: FXN, maxFragmentUniforms: maxFU }; },
  camera: function () { return { pos: cam.position.toArray(), target: tgt.toArray(), fov: cam.fov }; }
};
setLouvers(S.louver);
paintTrack();
resize();
applyOptions();
applySun();
goView(S.view, true);
renderer.render(scene, cam); dirty = false;
window.__ready = true;
requestAnimationFrame(loop);
})();
"""


def main(argv: Optional[List[str]] = None) -> int:
    """python -m decktakeoff.configurator BASE.json [stairs=S.json lights=L.json roof=R.json screens=SC.json] -o OUT.html [--title=..]"""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    out, title, opts, base = "configurator.html", None, {}, None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-o":
            out = args[i + 1]; i += 2; continue
        if a.startswith("--title="):
            title = a.split("=", 1)[1]
        elif "=" in a and not a.endswith(".json") or ("=" in a and a.split("=", 1)[0].isidentifier()):
            k, v = a.split("=", 1); opts[k] = v
        else:
            base = a
        i += 1
    if not base:
        print(main.__doc__); return 2
    st = build_configurator(base, opts or None, out, title=title)
    print(json.dumps({k: v for k, v in st.items() if k != "groups"}, indent=1))
    print("groups:", json.dumps(st["groups"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
