"""Low-voltage deck lighting: a recessed LED light in every stair riser and an LED light on every rail post, on a 12 V
transformer with a photocell and timer, wired with 12/2 low-voltage cable. The post light follows the rail: a lantern cap
light on each post, or, where the drink rail runs OVER the posts (railing.drink_rail_mount "over": no post caps), a small
accent light on the deck side of each post just below the drink rail.

Off unless the spec turns it on (an OPTION on most jobs: the option spec sets it, the engine prices the delta):
    extras.lights = {"riser": true, "post_cap": true, ...}      keys and defaults in DEFAULTS
    extras.lighting = true                                     (the older flag) = both, at the defaults
Nothing here draws a stair or a rail. Every piece works from what the engine has already built:
    scene_lights(boxes, spec)   3D: a faceplate + lens on the face of every riser box; on every rail-post box a lantern cap, or
                                an accent light (housing + lens) on its deck-side face below the drink rail
    materials(spec)             the material keys led_riser / led_cap / led_accent (emissive: emission, emission_strength, lumens)
                                and led_housing
    finish_takeoff(t)           the Lighting lines: fixtures from the layout's own stairs and rail posts, the transformer(s)
                                sized at 1.2 x the load, the 12/2 runs estimated from the layout, splices, staples.
                                Runs once per Takeoff (takeoff.Takeoff.__post_init__); a composite redoes it for the whole job
    labor_lines(t, lr)          install labor (ESTIMATE: the GSX rate card has no lighting line)
    fixed_sell(...)             extras.lights.sell_each: the lights sell at a set price each, installed (the rest of the job keeps
                                its margin; the cost stack still shows their real materials and labor)
    allocation(...)             "what the price includes": what is lit and how it switches, at its sell value
    option_price / stair_addon  the option, and the extra for the lights on another option (the yard stair), as engine deltas
Every fixture box carries a tag naming the option ("Lighting option: riser light" / "... post-cap light" / "... accent light" /
"... housing"), so an interactive page can find, toggle and glow them."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CATEGORY = "Lighting"
IN = 1 / 12.0

DEFAULTS = dict(
    riser=True,                 # a light in every riser of every stair (closed risers)
    post_cap=True,              # a light on every rail post (the key keeps its old name: a cap light or an accent light, below)
    post_light=None,            # "cap" | "accent" | None -> from the rail: "accent" when the drink rail runs over the posts
                                #   (railing.drink_rail_mount "over": no post caps), else "cap"
    stair_posts=True,           # ... the stair and landing-guard posts included, with the same light (False: the deck rail posts only)
    every=1,                    # 1 = every post, 2 = every other post (TimberTech: every post or alternate posts)
    per_riser=None,             # lights per riser; None -> one per 5' of stair width (one on a 4' stair)
    riser_sku="AZTDLRECRISERMB",
    cap_sku="AZTDL3X3LANCAPB",
    accent_sku="AZTIXLEDACCB",
    transformers=["AZTDL100TRAN", "AZTDL150PPR"],   # candidates; the cheapest installed set >= 1.2 x the load wins
    wire_skus=["LV12-2-250", "LV12-2-100"],          # 12/2 stock rolls; the cheapest mix that covers the estimate
    connector_sku="wirenut_silicone_25",
    staple_sku="lv_staples_100",
    headroom=1.2,               # transformer capacity >= 1.2 x the connected load
    run_max_w=60.0,             # TimberTech: 60 W max on one run
    transformer_at=None,        # [x, y] plan feet (job frame) of the outdoor outlet; None -> the house wall at the middle of the deck
    outlet_z_ft=1.5,            # the outlet / transformer height above grade
    timer="dusk + 6 h",         # how the timer is set ("dusk + 4 h", "dusk + 6 h", "dusk to dawn")
    kelvin=2700,
    option="Lighting",          # the option name in the 3D tags ("Lighting option: riser light")
    wire_lf=None,               # owner / field count of 12/2 (overrides the estimate)
    prices={},                  # per-job unit costs by SKU: {"AZTDL3X3LANCAPB": 129.99}
    sell_each=None,             # the owner's installed sell per light (riser or post), margin included: the lights sell at
                                #   sell_each x lights and the rest of the job keeps its margin (None -> cost + the job margin)
)

# Products (shape of the pricebook entries). Sources: $S/fillmore/materials.md section 6.1 (TimberTech 2026 Product Guide p.39,
# Lumbermens list eff. 1 Jun 2026); 12/2 cable from a retail listing. No lighting is on a D&D quote yet: every price is an estimate.
PRODUCTS: Dict[str, dict] = {
    "AZTDLRECRISERMB": dict(desc="TimberTech Recessed LED Riser Light, Matte Black, 12V, 2700K, 6' lead", each=88.24, watts=2.0,
                            face_in=(5.75, 2.75), lens_in=(3.25, 1.25), proud_in=0.1875, depth_in=0.5,
                            source="EST — Lumbermens list eff. 1 Jun 2026 (The Deck Store $94.99); not on a D&D quote"),
    "AZTDL3X3LANCAPB": dict(desc="TimberTech 3\" LED Lantern Post Cap Light for Impression Rail Express, Black, 12V, 2700K", each=136.0, watts=3.0,
                            source="EST — TimberTech 3\" LED Lantern Post Cap (IRX); Lumbermens list 4\" lantern $135.69 eff. 1 Jun 2026; not on a D&D quote; "
                                   "3 W (TimberTech Metal Railing Lighting Installation Guide 10.24)"),
    "AZTIXLEDACCB": dict(desc="TimberTech Small Accent Light for Impression Rail Express, Black, 12V AC, 1-5/8\" x 3/4\" x 4-1/4\"", each=58.99, watts=1.0,
                         size_in=(1.625, 0.75, 4.25), lens_in=(1.0, 1.25),
                         source="EST — The Deck Store $58.99 (Small Accent Light, TimberTech / AZEK), 27 Oct 2026; not on a D&D quote; SKU per the "
                                "TimberTech 2026 Product Guide (materials.md); 1 W (TimberTech Metal Railing Lighting Installation Guide 10.24)"),
    "AZTDL3X3LEDCAP": dict(desc="TimberTech Impression Rail Express Post Cap Light (LED lens between the post and its cap), 12V", each=78.99, watts=4.0,
                           source="EST — The Deck Store $78.99 (AZTDL3X3LEDCAP); not on a D&D quote"),
    "AZTDL100TRAN": dict(desc="TimberTech 100W 12V transformer with photocell + timer", each=135.15, watts=100.0, watts_max=90.0,
                         photocell=True, timer=True, dimmer=False,
                         source="EST — Lumbermens list eff. 1 Jun 2026 (The Deck Store $137.99); 90 W max load, 60 W max per run (TimberTech metal-rail guide)"),
    "AZTDL150PPR": dict(desc="TimberTech 150W PowerPack 12V transformer with photocell (photo eye), timer, dimmer and remote", each=373.95, watts=150.0, watts_max=135.0,
                        photocell=True, timer=True, dimmer=True,
                        source="EST — Lumbermens list eff. 1 Jun 2026 (The Deck Store $301.99); planned at 135 W max (90%); needs a GFCI in-use receptacle"),
    "LV12-2-250": dict(desc="12/2 stranded copper low-voltage landscape lighting cable, 250' (Southwire 55213444)", each=119.77, lf=250,
                       source="EST — Home Depot $119.77 (48¢/ft), 27 Oct 2026; not on a D&D quote"),
    "LV12-2-100": dict(desc="12/2 stranded copper low-voltage landscape lighting cable, 100'", each=55.0, lf=100,
                       source="EST — ~55¢/ft retail; not on a D&D quote"),
    "AZTDLLEDWIRE": dict(desc="TimberTech 16/2 AWG low-voltage wire, 100'", each=112.13, lf=100,
                         source="EST — Lumbermens list eff. 1 Jun 2026"),
    "wirenut_silicone_25": dict(desc="Silicone-filled outdoor wire connectors (25 pk)", each=20.0, count=25, source="EST"),
    "lv_staples_100": dict(desc="Insulated cable staples for the 12/2 along the framing (100 pk)", each=9.0, count=100, source="EST"),
}

R_12AWG = 1.62          # ohm / 1000 ft, one conductor, stranded copper (16 AWG: 4.09)
V_DROP_NOTE = 1.2       # volts (10% of 12 V) at the end of a run: past this the run is fed from its middle or split


def lights_of(spec) -> Optional[dict]:
    """The lighting settings when the spec turns lights on (DEFAULTS merged with extras.lights), else None."""
    ex = getattr(spec, "extras", None)
    d = getattr(ex, "lights", None) if ex is not None else None
    if d is None and not getattr(ex, "lighting", False):
        return None
    cfg = dict(DEFAULTS)
    cfg.update(d or {})
    if not cfg.get("enabled", True) or not (cfg.get("riser") or cfg.get("post_cap")):
        return None
    return cfg


def product(cfg: dict, sku: str) -> dict:
    """A product entry: the pricebook's lighting section when it has the SKU, else PRODUCTS; the job's own price wins."""
    from .catalog import PRICEBOOK
    p = dict(PRODUCTS.get(sku) or {"desc": sku, "each": 0.0, "source": "no price on file"})
    p.update(PRICEBOOK.get("lighting", {}).get(sku) or {})
    if sku in (cfg.get("prices") or {}):
        p["each"], p["source"] = float(cfg["prices"][sku]), "job price"
    p["sku"] = sku
    return p


def per_riser(cfg: dict, width_in: float) -> int:
    return int(cfg["per_riser"]) if cfg.get("per_riser") else max(1, int(math.ceil(width_in / 60.0 - 1e-9)))


def post_fixture(spec, cfg: dict) -> str:
    """"cap" (a lantern cap light on each post) or "accent" (a small accent light on the post's deck side): the job's choice
    (extras.lights.post_light), else from the rail — a drink rail OVER the posts (railing.drink_rail_mount "over") leaves no
    post cap, so the post light is an accent light; a drink rail between the posts, or none, keeps the caps."""
    if cfg.get("post_light") in ("cap", "accent"):
        return cfg["post_light"]
    r = getattr(spec, "railing", None)
    return "accent" if (getattr(r, "drink_rail", False) and str(getattr(r, "drink_rail_mount", "between") or "between").lower() == "over") else "cap"


def post_sku(spec, cfg: dict) -> str:
    return cfg["accent_sku"] if post_fixture(spec, cfg) == "accent" else cfg["cap_sku"]


# ================================================================== the plan: what gets a light, the load, the transformer, the runs
@dataclass
class Node:
    """A stop on a run: a deck rail post, or a whole stair (its riser lights and its own posts) hung at the top of the stair."""
    x: float                 # job frame, feet
    y: float
    z_deck: float            # the deck it sits on, feet above grade
    watts: float
    wire_ft: float           # cable inside the node: up and down the post / down the stair
    what: str
    part: str = ""


@dataclass
class Run:
    nodes: List[Node]
    home_ft: float
    chain_ft: float

    @property
    def watts(self) -> float:
        return sum(n.watts for n in self.nodes)

    @property
    def drop_v(self) -> float:
        """Voltage drop at the end of the run, 12/2, the load spread evenly along the chain."""
        amps = self.watts / 12.0
        return amps * 2 * R_12AWG / 1000.0 * (self.home_ft + self.chain_ft / 2)


@dataclass
class LightPlan:
    cfg: dict
    stairs: List[Tuple[str, int, int, int]]       # (stair name, risers lit, lights per riser, posts lit) per stair
    n_riser: int
    deck_posts: int                               # deck rail posts lit
    stair_posts: int                              # stair + landing guard posts lit
    riser_w: float
    cap_w: float                                  # watts of a post light (cap or accent)
    transformers: List[str]
    runs: List[Run]
    wire_ft: float                                # the estimate before slack
    wire_lf: int                                  # what the order covers (slack, rounded)
    outlet: Tuple[float, float]
    splices: int
    notes: List[str] = field(default_factory=list)
    parts: List[str] = field(default_factory=list)
    post_kind: str = "cap"                        # "cap" | "accent" (post_fixture)

    @property
    def n_cap(self) -> int:
        """Post lights (cap or accent: post_kind says which)."""
        return self.deck_posts + self.stair_posts

    @property
    def n_post(self) -> int:
        return self.n_cap

    @property
    def load_w(self) -> float:
        return self.n_riser * self.riser_w + self.n_cap * self.cap_w

    @property
    def fixtures(self) -> int:
        return self.n_riser + self.n_cap


def _deck_rail_posts(spec, Lp) -> list:
    """The part's own deck rail posts that carry a rail post (and so a cap light): the rail layout's posts, less a corner that
    is a shade-sail post (the takeoff's post-kit rule) and any post a roof post stands in for (louvered roof, when marked)."""
    rl = getattr(Lp, "rail", None)
    if not rl:
        return []
    posts = list(rl.posts)
    sails = [(float(sl["corners"][k][0]) * 12, float(sl["corners"][k][1]) * 12) for sl in (spec.geometry.sails or [])
             if sl.get("mount") == "deck_rail" for k in sl.get("posts", [])]
    if sails:
        posts = [p for p in posts if not any(abs(p.x - sx) < 5 and abs(p.y - sy) < 5 for sx, sy in sails)]
    return [p for p in posts if not getattr(p, "roof", False)]        # a louvered-roof post IS the rail post there: no IRX post, no cap light


def _stair_top(st, Lp) -> Tuple[float, float, Tuple[float, float]]:
    """The middle of a stair's opening at the deck edge (part frame, inches) and the direction it leaves in."""
    side, start, w = st.side, st.opening.start_in, st.width
    zs = Lp.zones
    if side in ("right", "end:right"):
        z = zs[-1]; return z.x0 + z.W, z.wall_y + start + w / 2, (1.0, 0.0)
    if side in ("left", "end:left"):
        z = zs[0]; return z.x0, z.wall_y + start + w / 2, (-1.0, 0.0)
    if side.startswith("step:"):
        na, nb = side.split(":")[1].split("-")
        za = next((q for q in zs if q.name == na), zs[0]); zb = next((q for q in zs if q.name == nb), zs[-1])
        y0 = (za.wall_y + za.D) if zb.D > za.D else (zb.wall_y + zb.D)
        return za.x0 + za.W, y0 + start + w / 2, ((-1.0 if zb.D > za.D else 1.0), 0.0)
    if side.startswith("edge:"):
        e = next((q for q in getattr(Lp, "outline_edges", []) or [] if q.name == side), None)
        if e is not None:
            if abs(e.y1 - e.y0) < 0.5:
                return min(e.x0, e.x1) + start + w / 2, e.y0, (0.0, 1.0 if e.x1 > e.x0 else -1.0)
            return e.x0, min(e.y0, e.y1) + start + w / 2, (-1.0 if e.y1 > e.y0 else 1.0, 0.0)
    if side.startswith("wall:"):
        z = next((q for q in zs if q.name == side.split(":")[1]), zs[0]); return z.x0 + z.W - start - w / 2, z.wall_y, (0.0, -1.0)
    zn = side.split(":")[1] if ":" in side else None
    z = next((q for q in zs if q.name == zn), zs[0])
    return z.x0 + start + w / 2, z.wall_y + z.D, (0.0, 1.0)


def _manhattan(a: Node, b: Node) -> float:
    return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.z_deck - b.z_deck)


def _split(chain: List[Node], cap: float) -> List[List[Node]]:
    """The chain cut into the fewest consecutive runs of at most `cap` watts, as even as they go (the lightest cap that
    still needs no more runs)."""
    def fill(lim):
        out, cur, w = [], [], 0.0
        for n in chain:
            if cur and w + n.watts > lim + 1e-6:
                out.append(cur); cur, w = [], 0.0
            cur.append(n); w += n.watts
        return out + [cur]
    best = fill(cap)
    lo, hi = max(n.watts for n in chain), cap
    for _ in range(30):
        mid = (lo + hi) / 2
        if len(fill(mid)) <= len(best):
            hi = mid
        else:
            lo = mid
    return fill(hi)


def _choose_transformers(cfg: dict, load: float) -> List[str]:
    """The cheapest installed set (unit cost x the material factor + the install labor each) whose capacity is at least
    headroom x the load and whose max-load ratings carry the load."""
    from .catalog import PRICEBOOK
    factor = PRICEBOOK.get("material_factor", 1.0)
    lab = float(PRICEBOOK.get("labor", {}).get("lighting_transformer_each", 175.0))
    cands = [product(cfg, s) for s in cfg["transformers"]]
    cands = [c for c in cands if c.get("watts")]
    if not cands or load <= 0:
        return []
    need = cfg["headroom"] * load
    best = None
    import itertools
    for combo in itertools.product(range(0, 5), repeat=len(cands)):
        if not any(combo):
            continue
        cap = sum(k * c["watts"] for k, c in zip(combo, cands))
        mx = sum(k * c.get("watts_max", c["watts"]) for k, c in zip(combo, cands))
        if cap + 1e-6 < need or mx + 1e-6 < load:
            continue
        cost = sum(k * (c["each"] * factor + lab) for k, c in zip(combo, cands))
        key = (round(cost, 2), sum(combo))
        if best is None or key < best[0]:
            best = (key, combo)
    if best is None:                       # past four of the biggest: as many big ones as it takes
        big = max(cands, key=lambda c: c["watts"])
        return [big["sku"]] * int(math.ceil(need / big["watts"]))
    out = []
    for k, c in zip(best[1], cands):
        out += [c["sku"]] * k
    return sorted(out, key=lambda s: -product(cfg, s)["watts"])


def light_plan(spec, L, cfg: Optional[dict] = None) -> Optional[LightPlan]:
    """Everything the lines, the labor and the words need, from the layout (a composite: every part, in the job frame)."""
    from .takeoff import stair_name
    cfg = cfg or lights_of(spec)
    if cfg is None:
        return None
    kind = post_fixture(spec, cfg)                    # "cap" or "accent" (a drink rail over the posts: no caps)
    rp = product(cfg, cfg["riser_sku"]); cp = product(cfg, post_sku(spec, cfg))
    riser_w, cap_w = float(rp.get("watts", 2.0)), float(cp.get("watts", 3.0 if kind == "cap" else 1.0))
    # cable at a post: a cap light splices in the cavity under its cap (TimberTech), so the run goes up into every post and back
    # down; an accent light's lead goes in through a 3/8" hole behind it and down inside the post to a splice on the run under
    # the deck (5/8" hole through the decking under the post)
    per_post = (lambda h: 2 * (h + 0.75)) if kind == "cap" else (lambda h: h + 1.0)
    parts = [(p.layout, p.placement, p.spec, p.name) for p in L.parts] if hasattr(L, "parts") else [(L, None, spec, "")]
    stairs, nodes, notes = [], [], []
    n_riser = deck_posts = stair_posts = 0
    every = max(1, int(cfg.get("every") or 1))
    zone_boxes = []                         # job frame, feet: (x0, x1, y0, y1) per zone, for the outlet default
    for Lp, pl, sp, pname in parts:
        to_job = (lambda x, y, pl=pl: pl.pt(x, y)) if pl is not None else (lambda x, y: (x, y))
        z_deck = sp.geometry.height_in / 12.0
        for z in Lp.zones:
            xs, ys = zip(*(to_job(x / 12.0, y / 12.0) for x in (z.x0, z.x0 + z.W) for y in (z.wall_y, z.wall_y + z.D)))
            zone_boxes.append((min(xs), max(xs), min(ys), max(ys)))
        rl = getattr(Lp, "rail", None)
        post_h = ((rl.height if rl else 36.0) + 2.0) / 12.0       # IRX: a 38" post for a 36" rail
        if cfg.get("post_cap"):
            dps = _deck_rail_posts(sp, Lp)
            lit = dps[::every]
            deck_posts += len(lit)
            for p in lit:
                x, y = to_job(p.x / 12.0, p.y / 12.0)
                nodes.append(Node(x, y, z_deck, cap_w, per_post(post_h), "post", pname))
        for st, ss in zip(Lp.stairs, list(sp.stairs) + [None] * len(Lp.stairs)):
            nm = stair_name(ss, st) if ss is not None else f"Stair ({st.side})"
            nr = st.geo.risers if (cfg.get("riser") and st.riser_pieces) else 0
            k = per_riser(cfg, st.width) if nr else 0
            sposts = (st.stair_posts + st.landing_posts) if (cfg.get("post_cap") and cfg.get("stair_posts")) else 0
            sposts = int(math.ceil(sposts / every)) if sposts else 0
            if not (nr or sposts):
                continue
            n_riser += nr * k
            stair_posts += sposts
            stairs.append((nm, nr, k, sposts))
            run_ft = sum(math.hypot(fg.run_in, fg.rise_in) for fg in st.geo.flights) / 12.0
            land_ft = sum((float(a) + float(b)) for a, b in (getattr(ss, "landings", None) or [])) / 12.0 if ss is not None else 0.0
            trunk = run_ft + land_ft + 3.0                         # down the stringer, across the landings, the tee at the top
            leads = 1.0 * nr * k + per_post(((rl.height if rl else 36.0) + 7.5) / 12.0) * sposts   # slack at each riser; each 43-1/2" stair post
            tx, ty, _ = _stair_top(st, Lp)
            x, y = to_job(tx / 12.0, ty / 12.0)
            w_st = nr * k * riser_w + sposts * cap_w
            n_sub = max(1, int(math.ceil(w_st / cfg["run_max_w"] - 1e-9)))   # a stair heavier than one run: each sub-run lights a stretch further down
            for i in range(n_sub):
                nodes.append(Node(x, y, z_deck, w_st / n_sub, trunk * (i + 1) / n_sub + leads / n_sub, f"stair: {nm}" + (f" ({i + 1}/{n_sub})" if n_sub > 1 else ""), pname))
    if not nodes:
        return LightPlan(cfg, stairs, 0, 0, 0, riser_w, cap_w, [], [], 0.0, 0, (0.0, 0.0), 0, ["nothing to light: no closed risers and no rail posts"],
                         post_kind=kind)
    # the outlet: the job's own point, else the house wall behind the middle of the lights
    if cfg.get("transformer_at"):
        ox, oy = float(cfg["transformer_at"][0]), float(cfg["transformer_at"][1])
    else:                                   # the house wall behind the middle of the deck (fixed: an option's stair doesn't move it)
        ox = (min(b[0] for b in zone_boxes) + max(b[1] for b in zone_boxes)) / 2
        zb = min(zone_boxes, key=lambda b: 0.0 if b[0] <= ox <= b[1] else min(abs(ox - b[0]), abs(ox - b[1])))
        oy = zb[2]
        ox = min(max(ox, zb[0]), zb[1])
    outlet = Node(ox, oy, float(cfg.get("outlet_z_ft", 1.5)), 0.0, 0.0, "outlet")
    # the runs: per deck level, a nearest-neighbour chain from the light closest to the outlet, cut into runs of at most run_max_w
    runs: List[Run] = []
    for pname in dict.fromkeys(n.part for n in nodes):
        todo = [n for n in nodes if n.part == pname]
        chain = [min(todo, key=lambda n: _manhattan(outlet, n))]
        todo.remove(chain[0])
        while todo:
            nxt = min(todo, key=lambda n: _manhattan(chain[-1], n))
            chain.append(nxt); todo.remove(nxt)
        groups = _split(chain, cfg["run_max_w"])
        for g in groups:
            home = _manhattan(outlet, g[0]) + 3.0                 # up the wall to the frame, across, 3' of slack at the transformer
            chain_ft = sum(_manhattan(a, b) for a, b in zip(g, g[1:])) + sum(n.wire_ft for n in g) - (g[-1].wire_ft / 2 if g[-1].what == "post" else 0.0)
            runs.append(Run(g, round(home, 1), round(chain_ft, 1)))
    wire_ft = sum(r.home_ft + r.chain_ft for r in runs)
    wire_lf = int(cfg["wire_lf"]) if cfg.get("wire_lf") else int(math.ceil(wire_ft * 1.10 / 10.0) * 10)
    splices = n_riser + deck_posts + stair_posts + sum(1 for n in nodes if n.what.startswith("stair"))    # every fixture lead, every stair's tee
    plan = LightPlan(cfg, stairs, n_riser, deck_posts, stair_posts, riser_w, cap_w, [], runs, round(wire_ft, 1), wire_lf, (round(ox, 2), round(oy, 2)),
                     splices, notes, [p[3] for p in parts if p[3]], post_kind=kind)
    plan.transformers = _choose_transformers(cfg, plan.load_w)
    for i, r in enumerate(runs):
        if r.drop_v > V_DROP_NOTE:
            notes.append(f"lighting run {i + 1} ({r.watts:.0f} W, {r.home_ft + r.chain_ft:.0f}' of 12/2): about {r.drop_v:.1f} V drop at the far end — feed it from the middle or split it")
    return plan


# ================================================================== takeoff lines
def _wire_mix(cfg: dict, lf: int) -> List[Tuple[dict, int]]:
    """The cheapest mix of the stock rolls that covers lf."""
    rolls = [product(cfg, s) for s in cfg["wire_skus"]]
    rolls = [r for r in rolls if r.get("lf")]
    if not rolls or lf <= 0:
        return []
    best = None
    import itertools
    hi = [int(math.ceil(lf / r["lf"])) + 1 for r in rolls]
    for combo in itertools.product(*[range(0, h + 1) for h in hi]):
        got = sum(k * r["lf"] for k, r in zip(combo, rolls))
        if got < lf:
            continue
        key = (round(sum(k * r["each"] for k, r in zip(combo, rolls)), 2), sum(combo))
        if best is None or key < best[0]:
            best = (key, combo)
    return [(r, k) for r, k in zip(rolls, best[1]) if k]


def lines_for(plan: LightPlan) -> list:
    from .takeoff import Line
    cfg = plan.cfg
    out = []
    if plan.n_riser:
        p = product(cfg, cfg["riser_sku"])
        what = " · ".join(f"{nm} {nr} risers" + (f" x {k}" if k > 1 else "") for nm, nr, k, _ in plan.stairs if nr)
        one = all(k == 1 for _, nr, k, _ in plan.stairs if nr)
        out.append(Line(CATEGORY, f"{p['desc']} — {'one in' if one else 'in'} every riser", plan.n_riser, plan.n_riser, "ea", f"exact  ({what})", p["each"], p["source"], p["sku"]))
    accent = plan.post_kind == "accent"
    if plan.n_cap:
        p = product(cfg, cfg["accent_sku"] if accent else cfg["cap_sku"])
        what = (f"{plan.deck_posts} deck rail posts" + (f" + {plan.stair_posts} stair / landing posts" if plan.stair_posts else "") + (" — every other post" if cfg.get("every", 1) > 1 else "")
                + ("; the drink rail runs over the posts, so no post caps: a 3/8\" wire hole and two #8 x 3/4\" screws per light" if accent else ""))
        where = ("on the deck side of every rail post, just below the drink rail" if accent else "on every rail post") if cfg.get("every", 1) == 1 else \
                ("on the deck side of every other rail post" if accent else "on every other rail post")
        out.append(Line(CATEGORY, f"{p['desc']} — {where}", plan.n_cap, plan.n_cap, "ea", f"exact  ({what})", p["each"], p["source"], p["sku"]))
    load = plan.load_w
    for sku in dict.fromkeys(plan.transformers):
        p = product(cfg, sku)
        n = plan.transformers.count(sku)
        sizing = (f"{load:.0f} W connected ({plan.n_cap} post lights x {plan.cap_w:g} W + {plan.n_riser} risers x {plan.riser_w:g} W) x {cfg['headroom']:g} = "
                  f"{cfg['headroom'] * load:.0f} W ≤ {sum(product(cfg, s)['watts'] for s in plan.transformers):.0f} W; {len(plan.runs)} run{'s' if len(plan.runs) != 1 else ''} ≤ {cfg['run_max_w']:g} W")
        out.append(Line(CATEGORY, p["desc"], n, n, "ea", f"exact  ({sizing})", p["each"], p["source"], p["sku"]))
    if plan.wire_lf:
        home = sum(r.home_ft for r in plan.runs)
        posts = sum(n.wire_ft for r in plan.runs for n in r.nodes if n.what == "post")
        stair = sum(n.wire_ft for r in plan.runs for n in r.nodes if n.what.startswith("stair"))
        along = plan.wire_ft - home - posts - stair
        why = (f"{plan.wire_lf} LF: {len(plan.runs)} runs — home runs {home:.0f}', along the frame {along:.0f}', {'down' if accent else 'up and down'} the posts {posts:.0f}', "
               f"down the stairs {stair:.0f}', +10%" if not cfg.get("wire_lf") else f"{plan.wire_lf} LF (job count)")
        mix = _wire_mix(cfg, plan.wire_lf)
        for r, k in mix:
            out.append(Line(CATEGORY, r["desc"], round(plan.wire_lf / r["lf"], 2) if len(mix) == 1 else k, k, "roll", why, r["each"], r["source"], r["sku"]))
    if plan.fixtures:
        p = product(cfg, cfg["connector_sku"])
        need = int(math.ceil(2 * plan.splices * 1.1))             # two conductors at every splice, +10% spares
        n = int(math.ceil(need / p.get("count", 25)))
        out.append(Line(CATEGORY, p["desc"] + (" — splices on the run under the deck at each post and behind the risers" if accent else
                                               " — splices in the post-cap cavity and behind the risers"),
                        n, n, "pk", f"{need} needed  ({plan.splices} splices x 2 conductors, +10%)", p["each"], p["source"], p["sku"]))
        p = product(cfg, cfg["staple_sku"])
        need = int(math.ceil((plan.wire_ft - sum(n.wire_ft for r in plan.runs for n in r.nodes if n.what == "post")) / 1.5))
        n = max(1, int(math.ceil(need / p.get("count", 100))))
        out.append(Line(CATEGORY, p["desc"], n, n, "pk", f"~{need} staples (every 18\" along the frame)", p["each"], p["source"], p["sku"]))
    return out


def finish_takeoff(t) -> None:
    """Add the Lighting lines when the spec turns lights on (no-op otherwise). A composite's merged part lines are replaced
    by one set for the whole job: one transformer set, every part's fixtures and runs."""
    cfg = lights_of(t.spec)
    if cfg is None:
        return
    plan = light_plan(t.spec, t.layout, cfg)
    t.lines[:] = [l for l in t.lines if l.category != CATEGORY]
    t.lines.extend(lines_for(plan))
    t.lighting = plan
    t.summary["lighting"] = words(plan)
    if not hasattr(t.layout, "parts"):
        t.summary["material_cost"] = round(sum(l.ext for l in t.lines), 2)
    t.notes = [n for n in t.notes if not (n.startswith("lighting") or ": lighting" in n)] + plan.notes     # a composite: the parts' notes go
    if plan.n_cap and getattr(t.spec.railing, "drink_rail", False):
        t.notes.append("lighting: the drink rail runs over the posts (no post caps), so each post light is a small accent light on the post's "
                       "deck side just below the drink rail — 3/8\" wire hole behind it, the lead down inside the post to the run under the deck"
                       if plan.post_kind == "accent" else
                       "lighting: the post-cap lights need the drink rail BETWEEN the posts (each post keeps its cap) — an over-the-post "
                       "drink rail covers the post tops and leaves no place for a cap light (railing.drink_rail_mount \"over\" switches the post "
                       "lights to accent lights)")


# ================================================================== labor, the sell allocation, the words
def labor_lines(t, lr: dict) -> list:
    """(line, qty, unit, rate, note) — ESTIMATE: the GSX card has no lighting rate (pricebook / extras.labor_rates keys
    lighting_fixture_each, lighting_transformer_each)."""
    plan = getattr(t, "lighting", None)
    if plan is None or not plan.fixtures or not any(l.category == CATEGORY for l in t.lines):
        return []
    what = (f"{plan.n_riser} riser + {plan.n_cap} post accent lights: cut the riser openings, drill each post (3/8\" wire hole, 2 screws), "
            "fish the lead down the post, splice under the deck, mount" if plan.post_kind == "accent" else
            f"{plan.n_riser} riser + {plan.n_cap} post-cap lights: cut the riser openings, pull the 12/2 through the posts, splice, mount")
    out = [(f"Lighting — install {what}", plan.fixtures, "fixture", float(lr.get("lighting_fixture_each", 50.0)), "ESTIMATE — no lighting rate on the card; confirm")]
    if plan.transformers:
        out.append((f"Lighting — mount the transformer{'s' if len(plan.transformers) > 1 else ''}, run the home runs, set the photocell and timer, test",
                    len(plan.transformers), "ea", float(lr.get("lighting_transformer_each", 175.0)), "ESTIMATE — no lighting rate on the card; confirm"))
    return out


def fixed_sell(t, labor_lines, factor: float, rate: float) -> Tuple[float, float]:
    """(sell, work) of the lights when extras.lights.sell_each sets their installed price (the owner: "$200 per, installed, with
    margin"): sell = sell_each x lights (risers + posts); work = their real materials (x the material factor, + tax) + their
    labor — pricing.price takes the work off the margin base and adds the sell, so the rest of the job keeps its margin and the
    cost stack still shows what the lights cost. (0, 0) without a set price or without lights."""
    plan = getattr(t, "lighting", None)
    each = (plan.cfg.get("sell_each") if plan is not None else None)
    if not each or not plan.fixtures or not any(l.category == CATEGORY for l in t.lines):
        return 0.0, 0.0
    m = sum(l.ext for l in t.lines if l.category == CATEGORY)
    lab = sum(e for i, q, u, r_, e in labor_lines if str(i).startswith("Lighting"))
    return round(float(each) * plan.fixtures, 2), m * factor * (1 + rate) + lab


def allocation(t, mats, labsum, comp) -> list:
    """The lighting's line in "what the price includes" (sell value: sell_each x lights when set), or nothing."""
    plan = getattr(t, "lighting", None)
    m = mats(lambda l: l.category == CATEGORY)
    if plan is None or not m:
        return []
    if plan.cfg.get("sell_each"):
        return [(short_words(plan), round(float(plan.cfg["sell_each"]) * plan.fixtures))]
    return [(short_words(plan), round(comp(m, labsum("Lighting"))))]


def post_label(plan: "LightPlan", n: Optional[int] = None) -> str:
    """How the post lights read: "post-cap lights" or "post accent lights" (with a count when n is given)."""
    lab = "post accent light" if plan.post_kind == "accent" else "post-cap light"
    return f"{n} {lab}{'s' if n != 1 else ''}" if n is not None else lab + "s"


NUM = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _switching(plan: LightPlan) -> str:
    cfg = plan.cfg
    tr = [product(cfg, s) for s in plan.transformers]
    n_dim = sum(1 for p in tr if p.get("dimmer"))
    timer = str(cfg.get("timer") or "").lower()
    hrs = timer.split("+")[1].strip().split()[0] if "+" in timer else ""
    off = "at dawn" if "dawn" in timer else (f"{hrs} hours later" if hrs else "at the time it is set to")
    n = len(tr)
    dim = "" if not n_dim else (" with a dimmer and remote" if n == 1 else f", {'one' if n_dim == 1 else NUM.get(n_dim, n_dim)} with a dimmer and remote")
    return (f"{NUM.get(n, n)} 12-volt transformer{'s' if n != 1 else ''}{dim}; a photocell turns the lights on at dusk and the timer "
            f"turns them off {off}")


def short_words(plan: LightPlan) -> str:
    bits = []
    if plan.n_riser:
        bits.append(f"{plan.n_riser} riser lights")
    if plan.n_cap:
        bits.append(post_label(plan, plan.n_cap))
    n = len(plan.transformers)
    return ("Lighting — " + " and ".join(bits) + ", LED, warm white, on " + (f"{NUM.get(n, n)} transformers with photocells and timers" if n > 1
                                                                          else "a transformer with a photocell and timer"))


def words(plan: LightPlan) -> str:
    """What is lit and how it switches (customer wording: facts only)."""
    cfg = plan.cfg
    lit = []
    if plan.n_riser:
        rs = [(nm, nr, k) for nm, nr, k, _ in plan.stairs if nr]
        low = lambda nm: nm[0].lower() + nm[1:]
        if len(rs) == 1:
            nm, nr, k = rs[0]
            lit.append((f"{'a' if k == 1 else NUM.get(k, k)} recessed LED light{'s' if k > 1 else ''} in each of the {nr} risers of the {low(nm)}"))
        else:
            lit.append("a recessed LED light in each stair riser (" + ", ".join(f"{nr * k} on the {low(nm)}" for nm, nr, k in rs) + ")")
    if plan.n_cap and plan.post_kind == "accent":
        stair = f" (on the stair and landing posts, the side toward the stair)" if plan.stair_posts else ""
        lit.append((f"a small LED accent light on each of the {plan.n_cap} rail posts, on the deck side just below the drink rail" if cfg.get("every", 1) == 1
                    else f"a small LED accent light on every other rail post ({plan.n_cap}), on the deck side just below the drink rail") + stair)
    elif plan.n_cap:
        lit.append(f"an LED cap light on each of the {plan.n_cap} rail posts" if cfg.get("every", 1) == 1 else f"an LED cap light on every other rail post ({plan.n_cap})")
    k = cfg.get("kelvin", 2700)
    return (f"Low-voltage LED lighting, {k:g}K warm white: " + " and ".join(lit) + ". " + _switching(plan)[0].upper() + _switching(plan)[1:]
            + ". It plugs into an outdoor GFCI outlet with an in-use cover; adding an outlet, if one is needed, is not included.")


# ================================================================== the option, priced as engine deltas
def with_lights(spec, on: bool = True, **cfg):
    """A copy of the spec with the lights on (cfg over DEFAULTS) or off."""
    from .spec import DeckSpec
    d = spec.to_dict() if hasattr(spec, "to_dict") else copy.deepcopy(spec)
    ex = d.setdefault("extras", {})
    if on:
        ex["lights"] = dict(ex.get("lights") or {}, **cfg) if ex.get("lights") else (dict(cfg) or {"riser": True, "post_cap": True})
    else:
        ex["lights"] = None
        ex["lighting"] = False
    return DeckSpec.from_dict(d)


def _terms(spec, check: float) -> Tuple[float, float, float]:
    """(check, financed, monthly) for a set price — pricing.fixed_terms when it is there (financed / 0.93 or x the job's markup)."""
    try:
        from .pricing import fixed_terms
        return fixed_terms(spec, check)
    except ImportError:
        from .catalog import PRICEBOOK
        retail = round(check / PRICEBOOK["retail_factor"])
        r, n = PRICEBOOK["finance_rate"] / 12, PRICEBOOK["finance_years"] * 12
        return round(check), retail, retail * r / (1 - (1 + r) ** -n)


def option_price(spec, **cfg) -> dict:
    """The lighting option on this spec: the whole installed difference of the spec with the lights against it without
    (check, financed, monthly; cost = the work delta). With extras.lights.sell_each the option sells at that price per light
    (risers + posts), financed and monthly as usual; otherwise materials + labor at the job margin. Plus the counts."""
    from . import run
    off = with_lights(spec, on=False)
    on = with_lights(spec, on=True, **cfg)
    t0, _, p0 = run(off)
    t1, _, p1 = run(on)
    plan = getattr(t1, "lighting", None)
    each = plan.cfg.get("sell_each") if plan is not None else None
    if each:
        check, retail, monthly = _terms(on, float(each) * plan.fixtures)
    else:
        try:
            from .pricing import option_delta
            check, retail, monthly = option_delta(p0, p1)
        except ImportError:
            check, retail, monthly = p1.sell - p0.sell, p1.retail - p0.retail, p1.monthly - p0.monthly
    cost = round(p1.work - p0.work, 2)
    return dict(check=round(check), financed=round(retail), monthly=round(monthly, 2), cost=cost,
                gm=round(1 - cost / check, 4) if check else 0.0, sell_each=each, fixtures=plan.fixtures if plan else 0,
                materials=round(sum(l.ext for l in t1.lines if l.category == CATEGORY), 2),
                labor=round(sum(e for i, q, u, r, e in p1.labor_lines if i.startswith("Lighting")), 2),
                risers=plan.n_riser if plan else 0, caps=plan.n_cap if plan else 0, post_kind=plan.post_kind if plan else "",
                load_w=plan.load_w if plan else 0.0, transformers=list(plan.transformers) if plan else [], wire_lf=plan.wire_lf if plan else 0,
                words=words(plan) if plan else "", lines=[l for l in t1.lines if l.category == CATEGORY])


def stair_addon(base_spec, with_stair_spec, **cfg) -> dict:
    """The extra for the lights when another option (the yard stair) is also chosen: the lighting option on the spec with
    that option, less the lighting option on the base (with sell_each: sell_each x the stair's lights, financed as usual)."""
    a, b = option_price(base_spec, **cfg), option_price(with_stair_spec, **cfg)
    out = {k: round(b[k] - a[k], 2) for k in ("check", "financed", "monthly", "cost", "materials", "labor", "risers", "caps", "fixtures", "load_w", "wire_lf")}
    if a.get("sell_each") and b.get("sell_each"):
        out["check"], out["financed"], out["monthly"] = _terms(with_lights(with_stair_spec, on=True, **cfg), out["check"])
        out["monthly"] = round(out["monthly"], 2)
    out["gm"] = round(1 - out["cost"] / out["check"], 4) if out["check"] else 0.0
    return dict(out, base=a, with_stair=b)


# ================================================================== 3D: fixture boxes on the finished stair and rail boxes
def _kelvin_hex(k: float) -> str:
    """Black-body colour (Tanner Helland's fit), sRGB hex."""
    t = k / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255.0 if t >= 66 else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    c = [int(max(0, min(255, v))) for v in (r, g, b)]
    return "#%02x%02x%02x" % tuple(c)


def materials(spec) -> Dict[str, dict]:
    """led_riser / led_cap / led_accent: the lenses — `color` is the daylight lens colour (the WebGL viewer), `emission` +
    `emission_strength` (W/m², a physical estimate to tune at render) and `lumens` light them at night; led_housing: the riser
    faceplates (the post-cap collar and top and the accent light's housing use the rail's own railmetal: they come in the rail's
    finish). Only the post light the job uses is listed (led_cap or led_accent)."""
    cfg = lights_of(spec)
    if cfg is None:
        return {}
    k = float(cfg.get("kelvin", 2700))
    glow = _kelvin_hex(k)
    rp, pp = product(cfg, cfg["riser_sku"]), product(cfg, post_sku(spec, cfg))
    out = dict(
        led_riser=dict(color="#fff0d8", rough=0.25, emission=glow, emission_strength=60.0, kelvin=k, watts=rp.get("watts", 2.0), lumens=50,
                       light="riser", label=f"{rp['desc']} — lens"),
        led_housing=dict(color="#141416", metal=0.55, rough=0.5, label="matte black powder-coat (riser light faceplates)"),
    )
    if post_fixture(spec, cfg) == "accent":       # a 1 W accent light washing down the post face onto the deck
        out["led_accent"] = dict(color="#fff2de", rough=0.3, emission=glow, emission_strength=40.0, kelvin=k, watts=pp.get("watts", 1.0), lumens=30,
                                 light="accent", aim="down", label=f"{pp['desc']} — lens")
    else:
        out["led_cap"] = dict(color="#fff2de", rough=0.3, emission=glow, emission_strength=30.0, kelvin=k, watts=pp.get("watts", 3.0), lumens=100,
                              light="post_cap", label=f"{pp['desc']} — lens")
    return out


def _covers(q, x: float, y: float) -> bool:
    """The box's plan footprint holds the point (a box turned in plan about its centre, rot_axis "z", included)."""
    if q.rot and q.rot_axis == "z":
        cx, cy = (q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2
        c, s = math.cos(-q.rot), math.sin(-q.rot)
        u, v = (x - cx) * c - (y - cy) * s, (x - cx) * s + (y - cy) * c
        return abs(u) <= (q.x1 - q.x0) / 2 + 1e-6 and abs(v) <= (q.y1 - q.y0) / 2 + 1e-6
    return q.x0 - 1e-6 <= x <= q.x1 + 1e-6 and q.y0 - 1e-6 <= y <= q.y1 + 1e-6


def _post_inward(p, rails, walk) -> Tuple[str, int]:
    """(axis, +1 / -1): the face of a rail post that looks onto what it guards — the deck, the stair, the landing. The rail line
    through the post (its balusters and rails) gives the axis it runs along; the face is across it, on the side where a walking
    surface (deck board, tread) lies at the post's foot."""
    cx, cy, pw = (p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2, max(p.x1 - p.x0, p.y1 - p.y0)
    votes = {"x": 0.0, "y": 0.0}
    for q in rails:
        qx, qy = (q.x0 + q.x1) / 2, (q.y0 + q.y1) / 2
        if q.z1 < p.z0 - 0.2 or q.z0 > p.z1 + 0.4:
            continue
        if q.kind == "baluster":
            dx, dy = qx - cx, qy - cy
            if 0.1 < math.hypot(dx, dy) < 1.6:
                votes["x" if abs(dx) > abs(dy) else "y"] += 1.0
        else:
            along_x = (q.x1 - q.x0) >= (q.y1 - q.y0)
            if along_x and q.y0 - 0.3 <= cy <= q.y1 + 0.3 and q.x0 - 0.3 <= cx <= q.x1 + 0.3:
                votes["x"] += 3.0
            elif not along_x and q.x0 - 0.3 <= cx <= q.x1 + 0.3 and q.y0 - 0.3 <= cy <= q.y1 + 0.3:
                votes["y"] += 3.0
    run = "x" if votes["x"] >= votes["y"] else "y"
    ax = "y" if run == "x" else "x"
    def hits(sg):                       # walking surface on that side: at the post's own level counts double (a notch's guard
        n = 0                           # faces the deck it stands on, not the stair below it)
        for dist in (pw / 2 + 0.6, pw / 2 + 1.5, pw / 2 + 2.5):
            px, py = (cx + sg * dist, cy) if ax == "x" else (cx, cy + sg * dist)
            zs = [q.z1 for q in walk if q.x0 <= px <= q.x1 and q.y0 <= py <= q.y1 and p.z0 - 1.5 <= q.z1 <= p.z0 + 0.8]
            n += (2 if any(abs(z - p.z0) < 0.15 for z in zs) else 1) if zs else 0
        return n
    hp, hm = hits(1), hits(-1)
    return ax, (1 if hp >= hm else -1)


def _overlap(a0, a1, b0, b1, tol=0.0) -> bool:
    return a0 < b1 + tol and b0 < a1 + tol


def _riser_face(b, risers, treads, decks) -> Optional[Tuple[str, int]]:
    """(thin axis, +1 / -1): which face of a riser box shows (toward the tread at its foot, away from the riser above)."""
    ax = "x" if (b.x1 - b.x0) < (b.y1 - b.y0) else "y"
    lo, hi = (b.x0, b.x1) if ax == "x" else (b.y0, b.y1)          # thin
    l0, l1 = (b.y0, b.y1) if ax == "x" else (b.x0, b.x1)          # long
    mid = (lo + hi) / 2
    def span(q):
        return ((q.x0, q.x1), (q.y0, q.y1)) if ax == "x" else ((q.y0, q.y1), (q.x0, q.x1))
    # the tread at its foot: top at the riser's bottom, across the same width, starting at the riser face
    for q in treads:
        (t0, t1), (w0, w1) = span(q)
        if abs(q.z1 - b.z0) < 0.06 and _overlap(w0, w1, l0, l1) and (abs(t0 - hi) < 0.2 or abs(t1 - lo) < 0.2):
            return ax, (1 if (t0 + t1) / 2 > mid else -1)
    # the riser above (its bottom at this one's top): this face looks away from it
    for q in risers:
        (t0, t1), (w0, w1) = span(q)
        if q is not b and abs(q.z0 - b.z1) < 0.08 and _overlap(w0, w1, l0, l1) and abs((t0 + t1) / 2 - mid) < 2.5:
            return ax, (1 if mid > (t0 + t1) / 2 else -1)
    # the riser below: this face looks toward it
    for q in risers:
        (t0, t1), (w0, w1) = span(q)
        if q is not b and abs(q.z1 - b.z0) < 0.08 and _overlap(w0, w1, l0, l1) and abs((t0 + t1) / 2 - mid) < 2.5:
            return ax, (1 if (t0 + t1) / 2 > mid else -1)
    # a single riser: the deck or landing it drops from is behind it
    for q in decks:
        (t0, t1), (w0, w1) = span(q)
        if abs(q.z1 - (b.z1 + 0.02)) < 0.06 and _overlap(w0, w1, l0, l1) and _overlap(t0, t1, lo - 0.5, hi + 0.5):
            c = (t0 + t1) / 2
            if abs(c - mid) > 0.02:
                return ax, (1 if mid > c else -1)
    return None


def scene_lights(boxes: list, spec) -> list:
    """New boxes: on the showing face of every riser box, a matte-black faceplate with a warm lens (led_riser) centred on the
    riser below the nosing (one per riser on a 4'-wide stair); on every rail-post box, a lantern cap (collar and top in the
    rail's finish, a lens band led_cap between) on whatever caps the post — its flat cap, or the drink-rail board where the
    rail carries one (the drink rail runs between the posts when they carry cap lights). Two posts drawn at one spot take one."""
    cfg = lights_of(spec)
    if cfg is None:
        return []
    from .scene import Box
    from .catalog import decking_facts
    opt = f"{cfg.get('option') or 'Lighting'} option"
    bt = decking_facts(spec.decking.collection)["thick"] * IN
    out: List = []
    if cfg.get("riser"):
        rp = product(cfg, cfg["riser_sku"])
        fw, fh = [v * IN for v in rp.get("face_in", (5.75, 2.75))]
        lw, lh = [v * IN for v in rp.get("lens_in", (3.25, 1.25))]
        proud, deep = rp.get("proud_in", 0.1875) * IN, rp.get("depth_in", 0.5) * IN
        risers = [b for b in boxes if b.kind == "riser" and not b.rot]
        treads = [b for b in boxes if b.kind == "tread"]
        decks = [b for b in boxes if b.kind in ("board", "border", "tread")]
        for b in risers:
            f = _riser_face(b, risers, treads, decks)
            if f is None:
                continue
            ax, sg = f
            l0, l1 = (b.y0, b.y1) if ax == "x" else (b.x0, b.x1)
            face = b.x1 if (ax == "x" and sg > 0) else b.x0 if ax == "x" else (b.y1 if sg > 0 else b.y0)
            zc = (b.z0 + b.z1 + 0.02 - bt) / 2                      # the middle of the riser that shows under the nosing
            n = per_riser(cfg, (l1 - l0) * 12)
            for i in range(n):
                c = l0 + (l1 - l0) * (i + 0.5) / n
                for kind, mat, w_, h_, t0, t1, what in (("fixture", "led_housing", fw, fh, face - sg * deep, face + sg * proud, "riser light faceplate"),
                                                         ("light", "led_riser", lw, lh, face - sg * deep * 0.8, face + sg * (proud + 0.03 * IN), "riser light")):
                    a0, a1 = sorted((t0, t1))
                    if ax == "x":
                        out.append(Box(kind, a0, a1, c - w_ / 2, c + w_ / 2, zc - h_ / 2, zc + h_ / 2, mat, b.phase or 6, tag=f"{opt}: {what}"))
                    else:
                        out.append(Box(kind, c - w_ / 2, c + w_ / 2, a0, a1, zc - h_ / 2, zc + h_ / 2, mat, b.phase or 6, tag=f"{opt}: {what}"))
    if cfg.get("post_cap"):
        caps = [b for b in boxes if b.kind in ("railcap", "drink") and (not b.rot or b.rot_axis == "z")]
        posts = [b for b in boxes if b.kind == "railpost" and not b.rot]
        if not cfg.get("stair_posts"):
            posts = [b for b in posts if not str(b.tag).endswith(("stair post", "landing post"))]
        uniq = []                                                  # two posts drawn at one corner (a guard's run ends) take one light
        for p in posts:
            c = ((p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2)
            if not any(abs(c[0] - u[0]) < 0.25 and abs(c[1] - u[1]) < 0.25 and abs(p.z1 - u[2]) < 0.1 for u in uniq):
                uniq.append((c[0], c[1], p.z1, p))
        posts = [u[3] for u in uniq]
        every = max(1, int(cfg.get("every") or 1))
        if every > 1:
            posts = sorted(posts, key=lambda q: (round(q.y0, 1), q.x0))[::every]
        if post_fixture(spec, cfg) == "accent":
            # a drink rail over the posts: no caps — a small accent light on the post's face toward the deck (the stair, the
            # landing), its top 2" below the post top (just under the drink rail; the panels hang off the side faces), a lens low on
            # its face washing down onto the deck; housing in the rail's finish
            ap = product(cfg, cfg["accent_sku"])
            aw, ad, ah = [v * IN for v in ap.get("size_in", (1.625, 0.75, 4.25))]
            lw, lh = [v * IN for v in ap.get("lens_in", (1.0, 1.25))]
            rails = [b for b in boxes if b.kind in ("baluster", "toprail", "botrail", "drink", "cable") and (not b.rot or b.rot_axis in ("x", "y"))]
            walk = [b for b in boxes if b.kind in ("board", "border", "tread")]
            for p in posts:
                ax, sg = _post_inward(p, rails, walk)
                cx, cy = (p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2
                face = (p.x1 if sg > 0 else p.x0) if ax == "x" else (p.y1 if sg > 0 else p.y0)
                zt_ = p.z1 - 2.0 * IN
                zl = zt_ - ah + 0.5 * IN                                # the lens: low on the face
                for kind, mat, w_, t0, t1, z0, z1, what in (("fixture", "railmetal", aw, face - sg * 0.01, face + sg * ad, zt_ - ah, zt_, "accent light housing"),
                                                             ("light", "led_accent", lw, face + sg * (ad - 0.01), face + sg * (ad + 0.03 * IN), zl, zl + lh, "accent light")):
                    a0, a1 = sorted((t0, t1))
                    if ax == "x":
                        out.append(Box(kind, a0, a1, cy - w_ / 2, cy + w_ / 2, z0, z1, mat, 7, tag=f"{opt}: {what}"))
                    else:
                        out.append(Box(kind, cx - w_ / 2, cx + w_ / 2, a0, a1, z0, z1, mat, 7, tag=f"{opt}: {what}"))
            return out
        for p in posts:
            cx, cy, pw = (p.x0 + p.x1) / 2, (p.y0 + p.y1) / 2, max(p.x1 - p.x0, p.y1 - p.y0)
            top, seen = p.z1, set()
            while True:                                            # climb the stack on the post: its cap, the drink board on it
                nxt = [q for q in caps if id(q) not in seen and _covers(q, cx, cy) and abs(q.z0 - top) < 0.02]
                if not nxt:
                    break
                for q in nxt:
                    seen.add(id(q))
                top = max(q.z1 for q in nxt)
            z = top - 0.01
            for kind, mat, w_, h_, what in (("fixture", "railmetal", pw + 0.4 * IN, 0.5 * IN, "post-cap light collar"),     # the cap in the rail's finish
                                            ("light", "led_cap", pw + 0.25 * IN, 1.25 * IN, "post-cap light"),
                                            ("fixture", "railmetal", pw + 0.5 * IN, 0.5 * IN, "post-cap light top")):
                out.append(Box(kind, cx - w_ / 2, cx + w_ / 2, cy - w_ / 2, cy + w_ / 2, z, z + h_, mat, 7, tag=f"{opt}: {what}"))
                z += h_ - 0.002                                    # each piece sits a hair into the one below: no shared faces
    return out
