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
    # the sun in the renders: the site's position and which way the deck faces
    lat: Optional[float] = None
    lon: Optional[float] = None
    rear_azimuth_deg: Optional[float] = None   # compass bearing of the outward normal of the wall the deck is on (the plan's +y)
    utc_offset_h: float = -6.0                 # local clock offset from UTC (Colorado summer -6, winter -7)
    sun_when: str = "2026-06-21T16:00"         # local date-time of the hero render's sun
    ahj_flags: List[List[str]] = field(default_factory=list)   # jurisdiction findings from the site research: [severity, topic, text, ref]
    code_basis: str = ""                 # the adopted codes line on G-001 ("" -> 2021 IRC as adopted by the city)
    wind_note: str = ""                  # the wind line on G-001 ("" -> Vult, Exposure C, ASCE 7-16)
    snow_note: str = ""                  # the ground-snow source note on G-001
    plan: dict = field(default_factory=dict)   # site plan (C-100), plan frame feet: {parcel, footprint, street, street_side, lot_lines, info, coverage, setback_ref, source}


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
    freestanding: bool = False           # no house behind this zone: a rear beam on posts instead of a ledger, rail along the wall line ("wall:<name>" edge)


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
    height_min_in: Optional[float] = None    # the lowest surface-to-grade point when height_in is an average (a walkway over uneven grade)
    attachment: str = "ledger"           # "ledger" | "freestanding"
    bay_ledger: bool = False             # a bay on the house takes a ledger on its faces (it bears on the foundation — not a cantilevered floor)
    board_direction: str = "parallel"    # "parallel" (to the house) | "perpendicular"
    picture_frame: bool = True
    fit_frame_to_boards: bool = True     # shrink/grow the depth a hair so the last field board is a full board
    shape: str = "rectangle"             # anything else is flagged; the engine takes the bounding rectangle
    notches: List[dict] = field(default_factory=list)   # [{"corner":"front-left","w_in":..,"d_in":..}] informational
    levels: int = 1
    zones: List[Zone] = field(default_factory=list)      # jogged / multi-zone plans (Eagle's Nest). Empty = one rectangle.
    # composite decks (a deck that wraps a corner of the house): a list of PARTS, each its own rectangle / zone set on its own
    # wall, placed in one global frame by an axis-aligned transform. Each part dict: {"name", "geometry": {...}, "railing": {...},
    # "stairs": [...], "placement": {"origin": [x_ft, y_ft], "xx": 1, "xy": 0, "yx": 0, "yy": 1}} — global = origin + M·local.
    parts: Optional[List[dict]] = None
    house_blocks: List[List[float]] = field(default_factory=list)     # global frame, feet: [x0, x1, y0, y1] blocks of the house footprint (drawn, not counted)
    house_openings: List[List[float]] = field(default_factory=list)   # [x0, x1, y_face, z0, z1] doors / windows on a wall facing the deck
    cover: Optional[List[float]] = None                                 # porch cover: [x0, x1, y0, y1, slope] (feet), drawn as a shed roof on posts
    planters: List[dict] = field(default_factory=list) # built-in planter boxes: {name, path: [[x, y], [x, y]] (ft, the deck edge it sits on, run like the outline), width_in 17, height_in 17}
    house_model: Optional[dict] = None   # the house behind the deck as measured (house.py): walls + openings, roofs, gutters, downspouts, bays
    site_model: Optional[dict] = None    # the yard as measured (landscape.py): graded lawn, beds, block walls, pavers, plants, fences, neighbours
    door_step: Optional[dict] = None   # a box step at the door on top of the deck: {x0, x1 (ft, plan frame), depth_in, rise_in}
    benches: List[dict] = field(default_factory=list)  # built-in benches: {name, path: [[x, y], ...] (ft, the deck edge the bench backs onto, run like the outline
                                                       #   so the deck is on the left-hand normal), depth_in 18, seat_in 18 (seat top above the deck), back True, back_in 34}
    sails: List[dict] = field(default_factory=list)    # shade sails: {name, corners: [[x, y, z] x 3-4] (ft, plan frame, z above grade: the attachment points),
                                                       #   posts: [corner indices on steel posts], color, post_od_in, post_embed_ft, footing_dia_in, fabric_price_sf}
    covers: List[dict] = field(default_factory=list)   # one or more lean-to roof covers: {name, x0, x1, y0, y1 (ft, post/beam rectangle),
                                                       #  slope "+y", clear_high_in / clear_low_in (bottom of the ledger at the house /
                                                       #  bottom of the beam at the posts, above the deck), posts_x_ft, footing
                                                       #  "deck" | "diamond_pier", overhang_ft, blinds [{"from_ft","to_ft","lowered"}]}
    louvered_roofs: List[dict] = field(default_factory=list)  # motorized aluminum louvered roofs (Suncoast) over the deck — keys and defaults in louvered.py (DEFAULTS)
    step_skirt: Optional[dict] = None    # the face between two levels clad in the decking fascia installed VERTICALLY (cut to height, seams
                                         # showing) on 2x4 furring: {"edges": ["edge:1", ...] (outline sides it covers: the step face and an
                                         # inset stair's notch cheeks), "drop_in": 36 (deck surface to the lower level's surface), "gap_in": 0.125
                                         # (between panels), "stud_oc_in": 16} — layout.step_skirt_layout reads it
    outline: List[List[float]] = field(default_factory=list)            # the deck's true outline as a polygon [[x, y], ...] (feet, plan frame) when it is not a union of rectangles:
                                                                        # deck pieces outside it are clipped, and mitred rim / fascia pieces are added along every angled edge
    house_walls: List[List[float]] = field(default_factory=list)        # angled house walls to draw: [x0, y0, x1, y1] segments (feet)
    overhead: List[List[float]] = field(default_factory=list)           # a deck / roof above this one, drawn: [x0, x1, y0, y1, z_under_ft, z_top_ft] (feet, grade = 0)
    through_columns: List[List[float]] = field(default_factory=list)    # existing columns that pass through the deck to the structure above: [x_ft, y_ft, size_ft]
    house_finish: str = "lap"            # how the house is drawn: "lap" siding | "stucco" | "brick"
    house_color: Optional[str] = None    # the siding color to draw (hex), from the photos — the finish's default otherwise


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
    posts_x_ft: Optional[List[float]] = None   # explicit post positions along the beam line (feet from the left frame face): the
                                               # existing columns, or the count the photos show — overrides the span-table spacing


@dataclass
class Framing:
    system: str = "dimensional"          # "dimensional" (2x SYP, hangers, double rims) | "timber" (DF #1 4x joists, 6x beams, 8x8 posts)
                                         # | "steel" (CEMCO cold-formed steel, sized as the same-depth lumber, then swapped — see steel.py)
    joist_size: str = "2x10"
    joist_species: str = "SYP"           # "SYP" | "DF" | "SPF" | "HF" | "CEDAR"
    joist_grade: str = "#1 True Frame GC"
    joist_spacing_in: Optional[float] = None   # None -> from decking (composite 16, PVC 12)
    rim_plies: int = 2                   # double rims everywhere (GSX standard). Never 3 or 4.
    ledger_size: Optional[str] = None    # None -> same as joist
    ledger_fastener: str = "LedgerLOK"   # "LedgerLOK" | "1/2 lag" | "1/2 bolt"
    hanger: str = ""                     # joist face-mount hanger SKU; "" = the one sized to the joist (2x10 -> LUS210Z)
    beams: List[Beam] = field(default_factory=lambda: [Beam()])
    edge_posts_ft: List[List[float]] = field(default_factory=list)   # outline plans: posts under the rims at these outline points ([x, y] ft;
                                         # a corner snaps to the vertex, else to the side) — the doubled rim spans post to post as a
                                         # flush beam, so the front is carried without a cantilever (a flush beam cannot cantilever)
    post_size: str = "6x6"
    footing_type: str = "diamond_pier"   # "diamond_pier" | "concrete" | "caisson" | "existing" (the caissons stay: standoff bases on epoxy anchors)
    existing_posts: bool = False         # the existing columns stay too: no post lumber or bases, new column caps / saddles engineered
    footing_model: str = "DP-50/50"
    footing_model_lock: bool = False     # the owner's pier model stays (Fillmore: "We need DP-50"): posts are added instead of upgrading the pier
    knee_braces: bool = False                # 4x4 knee braces at 45 deg, both directions at every beam post (tall posts / lateral)
    knee_leg_in: float = 30.0                # brace leg (each way) from the post / beam intersection
    post_species: str = ""                   # deck posts: "" -> #2 GC treated; "DF#1" -> Douglas fir #1 (owner-specified)
    post_rough: bool = False                 # 6x6 posts are rough-sawn full dimension (Douglas fir rough): R-series bases and caps
    steel_deck_post: str = "hss"             # steel frame: what stands on a deck-only pier — "hss" (3x3 stub) | "wood" (6x6 post, steel saddle to the beam)
    steel_joist: str = "600S162-54"          # steel frame jobs: SSMA joist designation (depth S flange - mils), G90
    steel_track: str = "600T"                # track for the rims and the ledger (54 mil)
    footing_price: Optional[float] = None    # owner's price per Diamond Pier (material, each) — overrides the pricebook
    blocking_rows: Optional[int] = None  # None -> 1 row over each beam (composite), 2 for PVC
    joist_tape: bool = True
    lateral_ties: int = 4                # DTT1Z count (IRC R507.9.2 alternative: 4 x 750 lb)
    caisson_dia_in: float = 20.0         # footing_type "caisson": drilled pier diameter
    caisson_depth_in: Optional[float] = None   # None -> frost depth + 2"
    caisson_above_in: float = 6.0        # caisson top above grade (0 = poured flush with a slab it is drilled through)
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
    border_fastener: Optional[str] = None   # "Cortex": picture frame, dividers and stair treads face-screwed with Cortex plugs (field stays hidden)
    face_screw: str = "Starborn Cap-Tor xd 2-3/4\""
    gap_in: Optional[float] = None       # override the line's field gap (Eagle's Nest: 1/8" on square-shoulder Vintage)
    border_collection: Optional[str] = None    # contrast picture frame / dividers (None -> field collection)
    border_color: Optional[str] = None
    dividers: bool = False               # breaker boards: with an outline, only where a run would exceed the longest stock (on zone lines); else one on every zone boundary
    price_per_lf: Optional[float] = None       # owner's decking price per LF (every 1x6 field / border / tread board): overrides the pricebook
    divider_x_ft: List[float] = field(default_factory=list)   # explicit breaker lines, feet from the left frame face (overrides the rule)


@dataclass
class RailOpening:
    side: str                            # "left" | "right" | "front"
    start_in: float                      # from the house face (sides) or from the left frame face (front)
    length_in: float
    reason: str = "opening"


@dataclass
class Railing:
    system: str = "Fulton"               # "Fulton" | "Impression" | "Classic Composite" | "none"
    existing_parapet: bool = False       # an existing stucco / masonry parapet stays on the open edges: no rail in the takeoff, drawn in the model
    parapet_sides: List[str] = field(default_factory=list)   # edge names that carry the parapet ("end:left", "front:A"); [] -> every exposed edge
    parapet_note: str = ""               # customer wording for the rail line when the parapet stays (e.g. which side is open)
    post_size_in: Optional[float] = None # rail post width override (e.g. 3.0 for a 3" post) — the system's stock post otherwise
    color: str = "Black"
    height_in: float = 36.0
    sides: List[str] = field(default_factory=lambda: ["left", "right", "front"])
    openings: List[RailOpening] = field(default_factory=list)
    post_kind: str = "surface"           # Fulton = 2" steel post inside the outer rim ply (GSX detail)
    edges: Optional[List[str]] = None    # multi-zone plans: which outline edges get rail — "front:A", "step:C-B", "end:left", "end:right". None -> every exposed edge
    drink_rail: bool = False             # deck board on top of the rail (IRX): collection/color below
    drink_rail_collection: Optional[str] = None
    drink_rail_color: Optional[str] = None
    drink_rail_mount: str = "between"    # IRX drink rail: "over" the posts (posts cut level under one continuous board, post inserts, no caps) | "between" them (post caps stay)


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
    mid_support: Optional[bool] = None   # a carrier beam on two posts / footings at mid-run under the stringers (None -> yes when the run is over 6')
    landings: List[List[float]] = field(default_factory=list)   # intermediate landings [[width_in, depth_in], ...] — framed platforms on 4 posts, decked, counted with the stairs
    flights: List[int] = field(default_factory=list)   # risers per flight, top down ([7, 6]: down 7 to the landing, turn, 6 more); [] -> one straight flight
    turn: str = "switchback"             # how flight 2 leaves the landing: "switchback" (180°, back alongside flight 1) | "straight" (same direction)
    turn_side: str = "left"              # switchback: which side of flight 1 the landing extends to and flight 2 runs down ("left" = toward the stair's low edge in plan)
    flight_rails: List[int] = field(default_factory=list)   # rail sides per flight ([1, 2]); [] -> `rails` on every flight
    landing_guard_lf: Optional[float] = None   # LF of guard on the landings' open sides (None -> each landing's perimeter less the stair widths in and out)
    build: str = "stringers"             # "stringers" (cut 2x12) | "box": a framed 2x6 box step on a compacted base — no stringers, fascia-wrapped (a step or two at grade)
    name: Optional[str] = None           # how the stair reads in client documents ("Centre stair", "Left-side box step"); None -> from the side
    skirts: bool = False                 # fascia skirts on both open sides, stepped under each tread — no stringer or framing shows
    inset: bool = False                  # recessed into the deck: leaves the inner face of a notch in the outline (side "edge:N") and runs out
                                         # to the face the notch is cut in, its bottom riser flush with that face's skirt; the notch is framed
                                         # (trimmer, headers, posts at its outer corners, a carrier under the stringer feet), its cheeks are the
                                         # stair's side walls (geometry.step_skirt), the deck's picture-frame board is the top nosing
    handrail: str = ""                   # "" -> one graspable handrail kit per stair when 4+ risers | "each flight": one along every flight |
                                         # "guard posts": an inset stair's handrail, bracketed to the deck guard's posts along one cheek
    handrail_side: str = "right"         # the side the handrail is on, going down ("right" | "left")
    option: str = ""                     # the option this stair belongs to ("Stairs to the yard"): its 3D boxes carry layer "option:<name>"
    landing_footing: str = ""            # "" -> each landing's 4 posts and footings are their own stair lines | "deck": they stand on the deck's
                                         # footing type (caisson / pier / Diamond Pier, the deck's bases), counted and installed with the deck's posts
    landing_grade_in: Optional[float] = None   # the grade under the landings' open edges, inches from the stair's foot (negative: the yard
                                         # falls away from the foot): the landing guard rule (over 30" above grade), the landing posts' length
                                         # and where the 3D sets their footings. None -> the ground is level with the foot


@dataclass
class Extras:
    demo_existing: bool = False
    demo_sf: Optional[float] = None
    labor_extras: List[dict] = field(default_factory=list)   # owner-set labor lines [{"item", "qty", "unit", "rate"}] (e.g. slab openings 6 x $200), marked up like the card
    demo_columns: List[dict] = field(default_factory=list)   # masonry columns out [{"what": "brick columns (9)", "lf": 55}] -> the card's stone / stucco column demo per LF
    hot_tub: bool = False
    roof_over: bool = False
    ledger_on_brick_veneer: bool = False
    ledger_on_cantilevered_floor: bool = False
    privacy_wall: bool = False
    lighting: bool = False               # True = the riser + post lights at the defaults (same as lights = {})
    lights: Optional[dict] = None        # low-voltage LED lights: {"riser": true, "post_cap": true, ...} — keys and defaults in lighting.py (DEFAULTS); None = off
    gm: Optional[float] = None           # gross-margin override (default 42.5%, 40% floor)
    gm_below_floor: bool = False         # the owner set a margin under the 40% floor on purpose — use it as given
    field_flags: List[dict] = field(default_factory=list)   # job-specific flags for the internal set: [{severity, topic, text, ref}]
    material_factor: Optional[float] = None    # None -> pricebook 1.15 (owner: materials +15%)
    site_extras: List[dict] = field(default_factory=list)   # [{"item": "Dumpster + portable toilet", "cost": 800}] (per-SF GC method)
    general_conditions: List[dict] = field(default_factory=list)   # itemized GC at cost [{"item","amount","why"}]; empty -> $4/SF + site_extras
    hot_tub_zone: Optional[str] = None   # zone name carrying the tub (multi-zone); None -> whole deck
    hot_tub_bay_in: float = 96.0         # tub bay square, doubled joists across it
    stone_bases: bool = False            # stone-veneer column bases at every post (2'x2' x 3' + 24" cap)
    engineered: bool = False             # a stamped design is part of the job (quote shows engineering at cost)
    engineering_fee_low: float = 1800.0
    engineering_fee_high: float = 3000.0
    engineering_included: bool = False   # the engineer's letter is in the price: no fee range shown (engineering_note says so)
    engineering_note: str = ""           # customer-facing line when engineering is outside the price ("billed at cost if the county asks for a stamped set")
    no_general_conditions: bool = False  # drop the $/SF general conditions and site extras entirely
    labor_rates: dict = field(default_factory=dict)   # per-job overrides of pricebook labor keys: {"rail_per_lf": 50, "cable_rail_addon_per_lf": 0}
    extra_beam_sets: Optional[int] = None             # override the "extra beam set" labor count (None -> beam lines minus one)
    builtin_sell: Optional[dict] = None               # built-ins sold at a set price per section: {"bench": 3000, "planter": 2500} — their materials + labor cost lands at 60% of it
    rail_sell_per_lf: Optional[float] = None          # rail sold at a fixed installed price per LF (None -> pricebook rail_sell_per_lf for the system, if any)
    sell_override: Optional[float] = None             # owner-set check/ACH price; the allocation scales to it
    sell_per_sf: Optional[float] = None               # owner-set check/ACH price per deck SF (or {"rate", "options_gm"}): sell = rate x deck SF, scaled like sell_override (pricing.sell_per_sf_rule)
    retail_markup: Optional[float] = None             # financed = sell x (1 + markup) instead of sell / 0.93
    options: List[Option] = field(default_factory=list)
    hardie_skirt: Optional[str] = None   # deck skirt / rim wrap in HardieTrim instead of the decking fascia: "4/4 x 12 Timber Bark"
    cover_soffit: Optional[str] = None   # porch cover ceiling: "HardieSoffit 4x10 cedarmill Timber Bark" (None -> 1x6 T&G pine)
    cover_fascia: Optional[str] = None   # porch cover fascia + rakes: "HardieTrim 4/4 x 7.25 rustic Timber Bark" (None -> painted 2x8)
    cover_roof: str = "shingles"         # porch cover roofing: "shingles" | "standing seam" (24 ga steel, snap-lock, 16" panels, HT underlayment, snow retention)
    cover_roof_color: str = ""           # roof panel color ("Charcoal", "Matte Black", "Burnished Slate"); "" -> to be selected
    cover_gutters: bool = False          # 5" K-style seamless aluminum gutter on the low eave + 2x3 downspouts on the cover posts
    cover_gutter_color: str = ""         # "" -> match the fascia / Timber Bark-compatible brown
    cover_roof_panel: str = "snap-lock"  # "snap-lock" (3:12 min by most makers) | "mechanical" (double-lock seam, low-slope rated)
    show_financing: bool = True          # proposal shows the financed price / monthly; False on a cash-only job (one-off)
    brand: str = "gs"                    # whose name, logo and colors the client documents carry: "gs" (GS Exterior Experts) | "cde" (Colorado Deck Experts, a GS company) — proposal_look.BRANDS + data/brands/<key>/
    timeline: Any = None                 # the job's own customer timeline instead of the generic day rates: a schedule model's customer block {title, precon, rows, schedule_lines}, or "schedule.json#Scenario" — report.timeline_of
    included: List[dict] = field(default_factory=list)   # the job's own "What it is" rows over the engine's: [{"title", "text"}] — same title replaces the row ("" drops it), a new one goes after the previous entry (report._included_rows)
    confirm: Any = None                  # the proposal's "Still to confirm" box for the client: [lines] or {"title", "intro", "items"}; prints on an engineered quote too (page._confirm_box)

    proposal_note: str = ""              # a closing paragraph on the proposal, under the next step (owner's terms / exclusions)
    price_breakdown: bool = True        # proposal shows a sell value per item; False -> the items listed, one total
    connection_details: bool = False    # permit set: add the wood-frame connection detail sheets (D-502 frame, D-504 edge / rail / lateral)
    under_deck_gravel: bool = False      # gravel over 6-mil poly under the deck (Louisville: decks 6' or less above grade)
    cover_post_species: str = "WRC"      # roof-cover posts: "WRC" (western red cedar) | "DF" (Douglas fir #1)
    labor_total: Optional[float] = None         # owner-set total labor for the job: owner-set lots stay, the rest scale to make it up
    cover_labor_total: Optional[float] = None   # owner-set labor for ALL roof covers together, roofing included (replaces the per-SF cover lines)
    demo_covers: bool = False            # tear off and haul the existing roof covers being replaced
    blinds_reinstall: bool = False       # take down, store and rehang the owner's roll-down blinds on the new cover beams
    exclusions: List[str] = field(default_factory=list)   # what the price does not include, printed on the quote ("Electrical")
    hardie_color: str = ""               # James Hardie ColorPlus color for the skirt, cover fascia, rakes and soffit ("Arctic White"); "" -> Timber Bark


@dataclass
class DeckSpec:
    job: str = "Deck"
    client: str = ""
    site: Site = field(default_factory=Site)
    # an order the owner already took off and priced (a Decks & Docks quote): [{"sku","item","qty","unit","unit_cost","category"?}].
    # When present the takeoff's lines ARE these, priced as quoted; the engine's own counts are kept as model_lines for a cross-check.
    quoted_order: List[dict] = field(default_factory=list)
    quoted_ref: str = ""                 # "Decks & Docks quote 979610 · 09/11/2026 · Henry Frederick"
    quoted_tax: Optional[float] = None   # the sales tax on that quote; when set, it IS the tax (no rate applied to the materials)
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


COVER_DEFAULTS = dict(name="Porch cover", slope="+y", beam="(2)2x10", ledger="2x10", clear_high_in=None, clear_low_in=None, posts_x_ft=None, footing="deck",
                      overhang_ft=1.0, blinds=[])


def post_words(spec) -> str:
    """How a 6x6 post reads: 'Douglas fir rough' / 'Douglas fir #1' / 'cedar' (cover posts) — the deck posts follow the same wood."""
    if spec.framing.post_rough:
        return "Douglas fir rough"
    if spec.framing.post_species.upper().startswith("DF"):
        return "Douglas fir #1"
    return "Douglas fir #1" if spec.extras.cover_post_species.upper().startswith("DF") else "cedar"


def post_base_sku(spec) -> str:
    return "ABA66RZ" if spec.framing.post_rough else "ABA66Z"


def covers_of(spec) -> List[dict]:
    """Every roof cover on the job as a dict (the legacy single `cover` list first, then `covers`)."""
    out = []
    c = spec.geometry.cover
    if c:
        d = dict(COVER_DEFAULTS); d.update(x0=c[0], x1=c[1], y0=c[2], y1=c[3], slope=c[4] if len(c) > 4 else "+y", legacy=True)
        out.append(d)
    for c in spec.geometry.covers or []:
        d = dict(COVER_DEFAULTS); d.update(c)
        out.append(d)
    return out
