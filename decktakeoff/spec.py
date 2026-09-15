"""DeckSpec — everything the takeoff engine needs to know about a job.

Coordinate convention (used everywhere in this package):
  * Plan view, house at the TOP of the page. y = 0 is the house face; y grows out into the yard.
  * x = 0 is the LEFT frame face as you stand in the yard facing the house; x grows to your right.
  * "left" / "right" / "front" rail runs and stairs use the same convention (standing in the yard
    facing the house — the GSX way of naming sides).
All lengths are stored in inches. Inputs accept feet-inches strings ("15'-7 1/2\""), decimal feet, or "187.5in".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields, is_dataclass
from typing import Any, List, Optional

from .units import to_inches


def _len(v, default, unit="ft"):
    if v is None:
        return default
    return to_inches(v, unit)


@dataclass
class Site:
    address: str = ""
    city: str = ""
    state: str = "CO"
    zip: str = ""
    ground_snow_psf: float = 30.0        # ASCE 7 / local amendment ground snow load
    wind_speed_mph: float = 115.0        # ASCE 7 ultimate (Vult) basic wind speed
    frost_depth_in: float = 36.0         # local frost line (concrete footings must bear below it)
    soil_bearing_psf: float = 1500.0     # IRC Table R401.4.1 presumptive unless a soils report says otherwise
    wui_fire_zone: bool = False          # Wildland-Urban Interface / ignition-resistant construction area
    seismic_design_category: str = "B"
    # setbacks — required by zoning vs. actual distance from the proposed deck edge
    rear_setback_required_ft: Optional[float] = None
    side_setback_required_ft: Optional[float] = None
    deck_to_rear_line_ft: Optional[float] = None
    deck_to_side_line_ft: Optional[float] = None
    easements: List[str] = field(default_factory=list)   # e.g. ["10' utility easement along rear"]
    hoa: bool = False
    tax_rate: Optional[float] = None     # None -> pricebook standing rate (4% on factored materials); set for a destination rate
    notes: str = ""


@dataclass
class Zone:
    """One rectangular bay of a jogged / multi-zone deck. Zones are listed LEFT to RIGHT as you stand in the yard facing
    the house. wall_offset_in: how far this zone's house wall is set BACK from the reference wall (a recessed gable or
    a jog) — positive = further from the yard, so front edge y = depth_in - wall_offset_in."""
    name: str = "A"
    width_in: float = 144.0
    depth_in: float = 144.0
    wall_offset_in: float = 0.0
    label: str = ""                      # "Lounge", "Dining terrace", "Deep wing"
    privacy_wall: bool = False           # an existing wall along this zone's outer end (no rail there)
    end_wall: str = "privacy"            # what that wall is: "privacy" (lot / screen wall, sold as an option) | "house" (the house's own return wall, full height)


@dataclass
class Option:
    """An upgrade / downgrade priced both ways. Either a spec change (delta re-priced through the engine) or a fixed cost
    (a site item with no takeoff, e.g. a concrete pad) — or both."""
    name: str
    changes: dict = field(default_factory=dict)   # deep-merged over the spec dict, e.g. {"railing": {"system": "Fulton"}}
    cost: float = 0.0                              # direct cost (materials + labor) of a fixed-cost option
    note: str = ""


@dataclass
class Geometry:
    width_in: float = 144.0              # along the house. size_mode "nominal": max finished size over the fascia (12' = "a 12x16 deck")
    depth_in: float = 192.0              # out from the house. size_mode "frame": outside-of-frame dimensions as drawn
    size_mode: str = "nominal"           # "nominal" (GSX: the engine sizes the frame DOWN to full boards inside the nominal size) | "frame"
    height_in: float = 30.0              # finished deck surface above grade at the LOWEST grade point
    height_high_in: Optional[float] = None   # surface above grade at the highest point (sloped lots), if different
    attachment: str = "ledger"           # "ledger" | "freestanding"
    board_direction: str = "parallel"    # "parallel" (to the house) | "perpendicular"
    picture_frame: bool = True
    fit_frame_to_boards: bool = True     # shrink/grow the depth a hair so the last field board is a full board
    shape: str = "rectangle"             # anything else is flagged; the engine takes the bounding rectangle
    notches: List[dict] = field(default_factory=list)   # [{"corner":"front-left","w_in":..,"d_in":..}] informational
    levels: int = 1
    zones: List[Zone] = field(default_factory=list)      # jogged / multi-zone plans (Eagle's Nest). Empty = one rectangle.


@dataclass
class Beam:
    kind: str = "drop"                   # "drop" (under the joists, joists cantilever past) | "flush" (in-plane, joists hang)
    size: str = "4x10"                   # "4x10", "(2)2x10", "(3)2x10", "4x12", "6x10" ...
    species: str = "DF"                  # "DF" | "SYP" | "SPF" | "HF"
    setback_in: Optional[float] = 24.0   # beam FACE back from the front rim face (drop) / beam CL back from the front rim face (flush)
    post_spacing_max_in: Optional[float] = None   # None -> from span table
    position_in: Optional[float] = None  # explicit CL from the house face (overrides setback; single-zone only)
    zones: Optional[List[str]] = None    # multi-zone plans: which zones this beam runs under (None = all). A drop beam at the same
                                         # setback in adjacent zones is one continuous beam line with shared posts.


@dataclass
class Framing:
    system: str = "dimensional"          # "dimensional" (2x SYP, hangers, double rims) | "timber" (DF #1 4x joists, 6x beams, 8x8 posts)
    joist_size: str = "2x10"
    joist_species: str = "SYP"           # "SYP" | "DF" | "SPF" | "HF" | "CEDAR"
    joist_grade: str = "#1 True Frame GC"
    joist_spacing_in: Optional[float] = None   # None -> from decking (composite 16, PVC 12)
    rim_plies: int = 2                   # double rims everywhere (GSX standard). Never 3 or 4.
    ledger_size: Optional[str] = None    # None -> same as joist
    ledger_fastener: str = "LedgerLOK"   # "LedgerLOK" | "1/2 lag" | "1/2 bolt"
    beams: List[Beam] = field(default_factory=lambda: [Beam()])
    post_size: str = "6x6"
    footing_type: str = "diamond_pier"   # "diamond_pier" | "concrete"
    footing_model: str = "DP-50/50"
    blocking_rows: Optional[int] = None  # None -> 1 row over each beam (composite), 2 for PVC
    joist_tape: bool = True
    lateral_ties: int = 4                # DTT1Z count (IRC R507.9.2 alternative: 4 x 750 lb)
    caisson_dia_in: float = 20.0         # footing_type "caisson": drilled pier diameter
    caisson_depth_in: Optional[float] = None   # None -> frost depth + 2"
    hardware_finish: str = "ZMAX"        # "ZMAX" | "black" (powder-coat, Outdoor Accents)
    finish: str = "none"                 # timbers: "none" (unfinished, weathers gray) | "oil" (dark walnut, 2 coats)
    end_grain_seal: bool = True          # timber frames: seal every cut end


@dataclass
class Decking:
    brand: str = "TimberTech"
    collection: str = "Prime+"
    color: str = "Coconut Husk"
    profile: str = "grooved"             # field boards: "grooved" | "square"
    board_length_in: Optional[float] = None    # preferred field board stock length; None -> best fit
    border_rows: int = 1
    fascia: bool = True
    fascia_color: Optional[str] = None   # None -> field color
    fastener_system: Optional[str] = None      # None -> GSX default by material (composite: Camo EdgeClip; PVC: CONCEALoc)
    face_screw: str = "Starborn Cap-Tor xd 2-3/4\""
    gap_in: Optional[float] = None       # override the line's field gap (Eagle's Nest: 1/8" on square-shoulder Vintage)
    border_collection: Optional[str] = None    # contrast picture frame / dividers (None -> field collection)
    border_color: Optional[str] = None
    dividers: bool = False               # a divider board at every zone boundary (multi-zone plans)


@dataclass
class RailOpening:
    side: str                            # "left" | "right" | "front"
    start_in: float                      # from the house face (sides) or from the left frame face (front)
    length_in: float
    reason: str = "opening"


@dataclass
class Railing:
    system: str = "Fulton"               # "Fulton" | "Impression" | "Classic Composite" | "none"
    color: str = "Black"
    height_in: float = 36.0
    sides: List[str] = field(default_factory=lambda: ["left", "right", "front"])
    openings: List[RailOpening] = field(default_factory=list)
    post_kind: str = "surface"           # Fulton = 2" steel post inside the outer rim ply (GSX detail)
    edges: Optional[List[str]] = None    # multi-zone plans: which outline edges get rail — "front:A", "step:C-B", "end:left", "end:right". None -> every exposed edge
    drink_rail: bool = False             # deck board on top of the rail (IRX): collection/color below
    drink_rail_collection: Optional[str] = None
    drink_rail_color: Optional[str] = None


@dataclass
class Stair:
    side: str = "front"                  # where the stair leaves the deck
    width_in: float = 48.0               # clear tread width (min 36")
    position_in: Optional[float] = None  # start of the stair opening along that side
    total_rise_in: Optional[float] = None   # None -> deck height at that edge
    landing: str = "concrete pad"        # "concrete pad" | "existing" | "grade" | "deck"
    rails: int = 2                       # stair guards/handrails: 0, 1 or 2 sides
    stringer_size: str = "2x12"
    closed_risers: bool = True


@dataclass
class Extras:
    demo_existing: bool = False
    demo_sf: Optional[float] = None
    hot_tub: bool = False
    roof_over: bool = False
    ledger_on_brick_veneer: bool = False
    ledger_on_cantilevered_floor: bool = False
    privacy_wall: bool = False
    lighting: bool = False
    gm: Optional[float] = None           # gross-margin override (default 42.5%, 40% floor)
    material_factor: Optional[float] = None    # None -> pricebook 1.15 (owner: materials +15%)
    site_extras: List[dict] = field(default_factory=list)   # [{"item": "Dumpster + portable toilet", "cost": 800}] (per-SF GC method)
    general_conditions: List[dict] = field(default_factory=list)   # itemized GC at cost [{"item","amount","why"}]; empty -> $4/SF + site_extras
    hot_tub_zone: Optional[str] = None   # zone name carrying the tub (multi-zone); None -> whole deck
    hot_tub_bay_in: float = 96.0         # tub bay square, doubled joists across it
    stone_bases: bool = False            # stone-veneer column bases at every post (2'x2' x 3' + 24" cap)
    engineered: bool = False             # a stamped design is part of the job (quote shows engineering at cost)
    engineering_fee_low: float = 1800.0
    engineering_fee_high: float = 3000.0
    options: List[Option] = field(default_factory=list)


@dataclass
class DeckSpec:
    job: str = "Deck"
    client: str = ""
    site: Site = field(default_factory=Site)
    geometry: Geometry = field(default_factory=Geometry)
    framing: Framing = field(default_factory=Framing)
    decking: Decking = field(default_factory=Decking)
    railing: Railing = field(default_factory=Railing)
    stairs: List[Stair] = field(default_factory=list)
    extras: Extras = field(default_factory=Extras)
    source_notes: List[str] = field(default_factory=list)   # what the intake read off the drawing / details

    # ----- construction helpers -----
    @classmethod
    def from_dict(cls, d: dict) -> "DeckSpec":
        d = dict(d or {})
        # tolerant length inputs
        g = dict(d.get("geometry") or {})
        for k, unit in (("width", "ft"), ("depth", "ft"), ("height", "in"), ("height_high", "in")):
            if k in g and f"{k}_in" not in g:
                g[f"{k}_in"] = to_inches(g.pop(k), unit)
            elif f"{k}_in" in g and g[f"{k}_in"] is not None:
                g[f"{k}_in"] = to_inches(g[f"{k}_in"], "in")
        for k in ("width_ft", "depth_ft"):
            if k in g:
                g[k.replace("_ft", "_in")] = float(g.pop(k)) * 12
        zs = []
        for z in g.get("zones") or []:
            z = dict(z)
            for k, unit in (("width", "ft"), ("depth", "ft"), ("wall_offset", "ft")):
                if k in z and f"{k}_in" not in z:
                    z[f"{k}_in"] = to_inches(z.pop(k), unit)
            zs.append(z)
        if zs:
            g["zones"] = zs
        d["geometry"] = g
        st = []
        for s in d.get("stairs") or []:
            s = dict(s)
            for k in ("width", "total_rise", "position"):
                if k in s and f"{k}_in" not in s:
                    s[f"{k}_in"] = to_inches(s.pop(k), "in")
            st.append(s)
        d["stairs"] = st
        return _build(cls, d)

    @classmethod
    def from_json(cls, s: str) -> "DeckSpec":
        return cls.from_dict(json.loads(s))

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent=2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    # ----- derived defaults -----
    @property
    def joist_spacing(self) -> float:
        if self.framing.joist_spacing_in:
            return float(self.framing.joist_spacing_in)
        from .catalog import decking_material
        return 12.0 if decking_material(self.decking.collection) == "PVC" else 16.0

    @property
    def blocking_rows(self) -> int:
        if self.framing.blocking_rows is not None:
            return int(self.framing.blocking_rows)
        from .catalog import decking_material
        return 2 if decking_material(self.decking.collection) == "PVC" else 1

    @property
    def ledger_size(self) -> str:
        return self.framing.ledger_size or self.framing.joist_size

    @property
    def is_timber(self) -> bool:
        return self.framing.system == "timber"

    @property
    def rim_plies(self) -> int:
        return 1 if self.is_timber else self.framing.rim_plies

    @property
    def deck_gap(self) -> float:
        if self.decking.gap_in is not None:
            return float(self.decking.gap_in)
        from .catalog import decking_facts
        return decking_facts(self.decking.collection)["gap"]

    @property
    def zone_list(self) -> List["Zone"]:
        """Always at least one zone: a single rectangle becomes zone 'A'."""
        if self.geometry.zones:
            return list(self.geometry.zones)
        return [Zone("A", self.geometry.width_in, self.geometry.depth_in, 0.0)]


_TYPE_MAP = {
    "site": Site, "geometry": Geometry, "framing": Framing, "decking": Decking,
    "railing": Railing, "extras": Extras,
}
_LIST_MAP = {"beams": Beam, "openings": RailOpening, "stairs": Stair, "zones": Zone, "options": Option}


def _build(cls, d: dict):
    """Build a dataclass from a dict, ignoring unknown keys (so a drawing-intake JSON with extras still loads)."""
    kwargs = {}
    names = {f.name: f for f in fields(cls)}
    for k, v in (d or {}).items():
        if k not in names:
            continue
        if k in _TYPE_MAP and isinstance(v, dict):
            kwargs[k] = _build(_TYPE_MAP[k], v)
        elif k in _LIST_MAP and isinstance(v, list):
            kwargs[k] = [_build(_LIST_MAP[k], x) if isinstance(x, dict) else x for x in v]
        else:
            kwargs[k] = v
    return cls(**kwargs)
