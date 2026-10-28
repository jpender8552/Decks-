"""lights.riser_pick (which risers carry lights) and extras.labor_adjust (the owner's labor change), on the Prentice job."""
import copy
import json
import os

import pytest

from decktakeoff.lighting import picked_risers
from decktakeoff.spec import DeckSpec
from decktakeoff.layout import build_layout
from decktakeoff.scene import build_scene, outline_side_frames
from decktakeoff.takeoff import build_takeoff
from decktakeoff.pricing import price

JOB = os.path.join(os.path.dirname(__file__), "..", "jobs", "prentice_centennial.json")


def _job(**extras):
    d = json.load(open(JOB))
    for k, v in extras.items():
        if k == "lights":
            d["extras"]["lights"] = dict(d["extras"]["lights"], **v)
        else:
            d["extras"][k] = v
    return d


def _takeoff(d):
    return build_takeoff(DeckSpec.from_dict(d))


def test_picked_risers():
    cfg = {"riser_pick": {"edge:6": "all", "edge:2": [1], "Back stair": [2, 9]}}
    assert picked_risers(cfg, "edge:6", "", 3) == [1, 2, 3]
    assert picked_risers(cfg, "edge:2", "", 2) == [1]
    assert picked_risers(cfg, "edge:3", "", 2) == []                 # not named: no lights
    assert picked_risers(cfg, "rear", "Back stair", 4) == [2]        # by name; numbers past the stair dropped
    assert picked_risers({}, "edge:3", "", 2) == [1, 2]              # no pick: every riser
    assert picked_risers(cfg, "edge:6", "", 0) == []


def test_prentice_five_riser_lights():
    t = _takeoff(_job())
    plan = t.lighting
    assert plan.n_riser == 5
    lit = {nm: nr for nm, nr, k, _ in plan.stairs if nr}
    assert lit == {"Center stair": 3, "Left box step — left side": 2}
    assert not plan.every_riser
    line = next(l for l in t.lines if l.category == "Lighting" and "riser" in l.item.lower())
    assert line.order == 5 and "each riser listed" in line.item


def test_prentice_riser_lights_in_3d():
    d = _job()
    s = DeckSpec.from_dict(d)
    S = build_scene(build_layout(s))
    lights = [b for b in S.boxes if b.kind == "light" and "riser" in (b.tag or "")]
    assert len(lights) == 5
    # the two on the straight far-left side sit in the middle of that side
    (sx, sy), (tx, ty), _n, ln = outline_side_frames([(float(x), float(y)) for x, y in d["geometry"]["outline"]])[1]
    mid_y = sy + ty * ln / 2
    left = [b for b in lights if (b.x0 + b.x1) / 2 < 0.5]
    assert len(left) == 2
    for b in left:
        assert abs((b.y0 + b.y1) / 2 - mid_y) < 0.02


def test_turned_step_lights_face_out():
    """A pick on the angled side (a z-turned step) lights its risers, outside the deck outline."""
    d = _job(lights={"riser_pick": {"edge:3": "all"}})
    s = DeckSpec.from_dict(d)
    S = build_scene(build_layout(s))
    lights = [b for b in S.boxes if b.kind == "light" and "riser" in (b.tag or "")]
    assert len(lights) == 2 and all(abs(b.rot) > 0.1 and b.rot_axis == "z" for b in lights)
    risers = [b for b in S.boxes if b.kind == "riser" and (b.tag or "").endswith("edge:3")]
    (sx, sy), (tx, ty), (nx, ny), ln = outline_side_frames([(float(x), float(y)) for x, y in d["geometry"]["outline"]])[2]
    for lt in lights:                       # each lens stands proud of its riser, on the yard side
        r = min(risers, key=lambda q: abs(q.z0 - lt.z0) + abs(q.z1 - lt.z1))
        dx, dy = (lt.x0 + lt.x1) / 2 - (r.x0 + r.x1) / 2, (lt.y0 + lt.y1) / 2 - (r.y0 + r.y1) / 2
        assert dx * nx + dy * ny > 0


def test_labor_adjust_cuts_exactly():
    base = price(_takeoff(_job(labor_adjust=None)))
    cut = price(_takeoff(_job(labor_adjust=-1000)))
    assert cut.labor == pytest.approx(base.labor - 1000, abs=1.0)
    assert cut.sell < base.sell
