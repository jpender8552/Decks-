"""Styling furniture (geometry.furniture): drawn in the 3D scene on layer "styling", tagged "(not included)"; never in the
takeoff, the price or a drawing sheet; a job without it builds exactly the scene it did before."""
import copy
import json
from dataclasses import asdict

from decktakeoff import run
from decktakeoff.configurator import ROLE_FURN, _role
from decktakeoff.drawings import all_sheets
from decktakeoff.scene import FURN_LAYER, build_scene
from decktakeoff.spec import DeckSpec

from test_lighting import SINGLE, TWO

SET = [
    dict(type="sectional", model="Teak Outdoor L Sectional - 4 Seat", level="lower", x=8.0, y=3.0, rot_deg=0, ret="+x", frame="teak", cushion="Pacific Fog Gray"),
    dict(type="coffee_table", level="lower", x=6.0, y=6.0, frame="teak"),
    dict(type="lounge_chair", level="lower", x=2.5, y=5.5, rot_deg=-75, frame="teak", cushion="Deep Sea Navy"),
    dict(type="dining_table", level="upper", x=30.0, y=4.0, frame="charcoal", top="teak"),
    dict(type="dining_chair", level="upper", x=30.0, y=1.2, arms=True, cushion="Pacific Fog Gray"),
    dict(type="side_table", level="upper", x=36.0, y=3.0, rot_deg=30),
    dict(type="umbrella", level="upper", x=36.0, y=6.0, canopy="white"),
]


def styled(d):
    d = copy.deepcopy(d)
    d["geometry"]["furniture"] = copy.deepcopy(SET)
    return DeckSpec.from_dict(d)


def test_styling_is_drawn_tagged_and_on_its_own_layer():
    t, _f, _p = run(styled(TWO), with_pricing=False)
    S = build_scene(t.layout)
    fb = [b for b in S.boxes if b.layer == FURN_LAYER]
    assert fb and all(b.kind == "furn" and b.mat.startswith("furn_") for b in fb)
    assert all(b.tag.startswith("Styling: Outer ") and b.tag.endswith(" (not included)") for b in fb)
    assert not [b for b in S.boxes if b.kind == "furn" and b.layer != FURN_LAYER]
    assert {"furn_teak", "furn_frame", "furn_cushion", "furn_cushion_deep_sea_navy", "furn_canopy_white"} <= set(S.materials)
    assert all(m["label"].endswith("(styling only, not included)") for k, m in S.materials.items() if k.startswith("furn_"))
    lower, upper = 96 / 12, 132 / 12                            # each piece stands on its level's deck surface
    assert min(b.z0 for b in fb if "Sectional" in b.tag) == lower
    assert min(b.z0 for b in fb if "Dining Table" in b.tag) == upper
    assert any(b.shape == "mesh" for b in fb) and any(b.rot and b.rot_axis == "z" for b in fb)
    assert all(_role(b, S.materials) & ROLE_FURN for b in fb)      # the 3D page's Furniture chip finds every piece
    assert [m["model"] for m in S.meta["styling"]][:1] == ["Teak Outdoor L Sectional - 4 Seat"]


def test_styling_never_priced_ordered_or_on_a_sheet():
    for base in (TWO, SINGLE):
        plain, dressed = DeckSpec.from_dict(copy.deepcopy(base)), styled(base) if "parts" in base["geometry"] else None
        if dressed is None:                                      # a single deck: the pieces on its one floor
            d = copy.deepcopy(base)
            d["geometry"]["furniture"] = [dict(p, level="deck") for p in SET[:3]]
            dressed = DeckSpec.from_dict(d)
        t0, f0, p0 = run(plain)
        t1, f1, p1 = run(dressed)
        assert [(l.category, l.item, l.net, l.order) for l in t0.lines] == [(l.category, l.item, l.net, l.order) for l in t1.lines]
        assert p0.sell == p1.sell
        S1 = build_scene(t1.layout)
        assert any(b.layer == FURN_LAYER for b in S1.boxes)
        sheets0 = all_sheets(t0.layout, t0, f0, build_scene(t0.layout), customer=True)
        sheets1 = all_sheets(t1.layout, t1, f1, S1, customer=True)
        assert [(n, svg) for n, _, svg in sheets0] == [(n, svg) for n, _, svg in sheets1]
        assert not any("Styling" in svg for _n, _t, svg in sheets1)


def test_a_job_without_furniture_builds_the_same_scene():
    d = copy.deepcopy(TWO)
    S0 = build_scene(run(DeckSpec.from_dict(d), with_pricing=False)[0].layout)
    d["geometry"]["furniture"] = []
    S1 = build_scene(run(DeckSpec.from_dict(d), with_pricing=False)[0].layout)
    assert json.dumps([asdict(b) for b in S0.boxes]) == json.dumps([asdict(b) for b in S1.boxes])
    assert S0.materials == S1.materials and "styling" not in S1.meta
