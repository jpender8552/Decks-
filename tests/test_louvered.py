"""Louvered roof (louvered.py): a roof on a one-rectangle deck and on a two-level composite — the rail takes the roof posts,
the takeoff swaps the rail post kits for wall-mount kits, the scene draws it on its own layer with a live-viewer descriptor,
the price is $/SF x the area, the drawing set gets A-403; a job without a roof is untouched."""
import copy

from decktakeoff import run
from decktakeoff import louvered as lv
from decktakeoff.scene import build_scene
from decktakeoff.spec import DeckSpec

RECT = dict(job="roof test", geometry=dict(width_in=240, depth_in=144, size_mode="frame", height_in=96),
            railing=dict(system="IRX Baluster", sides=["left", "right", "front"]),
            decking=dict(collection="Vintage", color="English Walnut"))
ROOF = dict(x0=0, x1=20, y0=0, y1=12, price_per_sf=175, angle_deg=30)


def _spec(roof=None, **kw):
    d = copy.deepcopy(RECT)
    if roof is not None:
        d["geometry"]["louvered_roofs"] = [dict(roof, **kw)]
    return DeckSpec.from_dict(d)


def test_no_roof_untouched():
    t, f, p = run(_spec())
    assert not any(getattr(q, "roof", False) for q in t.layout.rail.posts)
    assert not any("Wall Mount" in l.item for l in t.lines)
    S = build_scene(t.layout)
    assert "louvered_roofs" not in S.meta and not any(b.layer == "louvered" for b in S.boxes)
    assert not any(k.startswith("lv") for k in S.materials)


def test_roof_rail_takeoff_scene_price():
    t0, _, _ = run(_spec())
    t, f, p = run(_spec(ROOF))
    roof_posts = [q for q in t.layout.rail.posts if getattr(q, "roof", False)]
    assert len({q.roof for q in roof_posts}) == 2                      # both front corners are the roof's posts
    kits = lambda t_: sum(l.order for l in t_.lines if l.category == "Rail" and "post kit" in l.item.lower())
    assert kits(t) == kits(t0) + len(t.layout.rail.posts) - len(t0.layout.rail.posts) - len(roof_posts)
    assert sum(l.order for l in t.lines if "Wall Mount" in l.item) == 4
    S = build_scene(t.layout)
    lvb = [b for b in S.boxes if b.layer == "louvered"]
    assert any(b.kind == "lvblade" and b.shape == "mesh" and b.pts for b in lvb)
    assert not any(b.kind == "railpost" and any(abs((b.x0 + b.x1) / 2 - q.x / 12) < 0.05 and abs((b.y0 + b.y1) / 2 - q.y / 12) < 0.05
                                                for q in roof_posts) for b in S.boxes)
    d = S.meta["louvered_roofs"][0]
    assert d["box_kind"] == "lvblade" and d["angle_default_deg"] == 30 and d["angle_max_deg"] == 140 and len(d["blades"]) > 10
    assert lv.roof_pricing(t.spec, t.layout)["sell"] == 175 * 240
    from decktakeoff.drawings import all_sheets
    assert any(n == "A-403" for n, _, _ in all_sheets(t.layout, t, f))


def test_option_roof_leaves_the_deck_alone():
    t0, _, p0 = run(_spec())
    t, _, p = run(_spec(ROOF, priced="option"))
    assert p.sell == p0.sell and [l.item for l in t.lines] == [l.item for l in t0.lines]
    assert lv.option_prices(t.spec, 0.4)[0].check == 175 * 240


def test_screens_minimal_spec():
    t, _, _ = run(_spec(ROOF, screens=[{"side": "front"}, {"side": "right", "drop": 1}]))
    S = build_scene(t.layout)
    scr = S.meta["louvered_roofs"][0]["screens"]
    assert [s_["side"] for s_ in scr] == ["front", "right"] and all(s_["max_drop"] > 5 for s_ in scr)
    assert any(b.kind == "lvscreen" for b in S.boxes) and "lvfabric" in S.materials


def test_part_roofs_frame():
    part = {"name": "Upper", "placement": {"origin": [29.1667, 0]}, "geometry": {}}
    q = lv.part_roofs([dict(x0=29.6, x1=49.6, y0=0, y1=10)], part)[0]
    assert q["_global"] and abs(q["x0"] - 0.4333) < 1e-3 and abs(q["x1"] - 20.4333) < 1e-3
