"""Low-voltage lighting (extras.lights): off by default; on, a light in every riser and on every rail post, one transformer set
for the whole job (a composite too), the 3D fixtures tagged for the option, the option priced as an engine delta."""
import copy
import json
from pathlib import Path

import pytest

from decktakeoff import run, lighting
from decktakeoff.scene import build_scene
from decktakeoff.spec import DeckSpec

ROOT = Path(__file__).parent.parent
SINGLE = json.loads((ROOT / "examples" / "flush_beam_stairs.json").read_text())

# a two-level deck (the Fillmore shape, small): a lower part with rail, an upper part with rail and a stair down to the lower level
TWO = {
    "job": "two-level lighting test", "site": {"city": "Centennial", "tax_rate": 0.0725},
    "geometry": {"height_in": 96, "attachment": "ledger", "picture_frame": True, "parts": [
        {"name": "Lower level", "placement": {"origin": [0, 0]},
         "geometry": {"height_in": 96, "zones": [{"name": "B", "width_in": 240, "depth_in": 120, "wall_offset_in": 0}]},
         "railing": {"edges": ["end:left", "front:B"]}, "stairs": []},
        {"name": "Upper level", "placement": {"origin": [20, 0]},
         "geometry": {"height_in": 132, "zones": [{"name": "C", "width_in": 240, "depth_in": 120, "wall_offset_in": 0}]},
         "railing": {"edges": ["end:left", "front:C", "end:right"]},
         "stairs": [{"side": "left", "width_in": 44, "position_in": 72, "total_rise_in": 36, "landing": "deck", "rails": 1,
                     "name": "Stair between the levels"}]}]},
    "framing": {"joist_size": "2x10", "joist_spacing_in": 12, "post_size": "6x6", "footing_type": "diamond_pier",
                "beams": [{"kind": "drop", "size": "(3)2x10", "setback_in": 24}]},
    "decking": {"brand": "TimberTech", "collection": "Vintage", "color": "English Walnut", "profile": "square"},
    "railing": {"system": "IRX Baluster", "color": "Black", "height_in": 36, "drink_rail": True},
    "extras": {}}


def lit(d, **cfg):
    d = copy.deepcopy(d)
    d.setdefault("extras", {})["lights"] = dict({"riser": True, "post_cap": True}, **cfg)
    return DeckSpec.from_dict(d)


def lighting_lines(t):
    return [l for l in t.lines if l.category == "Lighting"]


def test_off_by_default_changes_nothing():
    t, _, p = run(DeckSpec.from_dict(SINGLE))
    assert not lighting_lines(t) and not hasattr(t, "lighting")
    assert not [i for i, *_ in p.labor_lines if i.startswith("Lighting")]
    sc = build_scene(t.layout)
    assert not [b for b in sc.boxes if b.mat.startswith("led")] and not [k for k in sc.materials if k.startswith("led")]


def test_single_deck_counts_follow_the_layout():
    t, _, p = run(lit(SINGLE))
    L, pl = t.layout, t.lighting
    risers = sum(st.geo.risers for st in L.stairs if st.riser_pieces)
    posts = len(L.rail.posts) + sum(st.stair_posts + st.landing_posts for st in L.stairs)
    assert pl.n_riser == risers and pl.n_cap == posts
    ln = {l.sku: l for l in lighting_lines(t)}
    assert ln["AZTDLRECRISERMB"].order == risers and ln["AZTDL3X3LANCAPB"].order == posts
    assert sum(lighting.product(pl.cfg, s)["watts"] for s in pl.transformers) >= 1.2 * pl.load_w
    assert all(r.watts <= 60.0 + 1e-6 for r in pl.runs)
    assert all(i.startswith("Lighting") and n.startswith("ESTIMATE") for i, q, u, r, n in lighting.labor_lines(t, {}))
    assert any(k.startswith("Lighting") for k, v in p.allocation)
    # the 3D: one lens on every riser box and every rail-post box, tagged for the option
    sc = build_scene(L)
    lens = [b for b in sc.boxes if b.mat in ("led_riser", "led_cap")]
    assert sum(b.mat == "led_riser" for b in lens) == sum(b.kind == "riser" for b in sc.boxes) == risers
    assert sum(b.mat == "led_cap" for b in lens) == sum(b.kind == "railpost" for b in sc.boxes)
    assert all(b.tag.startswith("Lighting option: ") for b in lens)
    assert {"led_riser", "led_cap", "led_housing"} <= set(sc.materials) and sc.materials["led_riser"]["emission"].startswith("#")


def test_composite_one_transformer_set_for_the_job():
    t, _, p = run(lit(TWO))
    pl = t.lighting
    parts = t.layout.parts
    assert pl.n_riser == 5 * 1                       # 36" over 5 risers, one light each on a 44" stair
    assert pl.deck_posts == sum(len(q.layout.rail.posts) for q in parts)
    tr = [l for l in lighting_lines(t) if "transformer" in l.item.lower() or "PowerPack" in l.item]
    assert sum(l.order for l in tr) == len(pl.transformers) <= 2
    assert len({l.item for l in lighting_lines(t)}) == len(lighting_lines(t))      # the parts' own lines were replaced, not summed
    sc = build_scene(t.layout)
    assert sum(b.mat == "led_riser" for b in sc.boxes) == 5
    assert all("Lighting option" in b.tag for b in sc.boxes if b.mat in ("led_riser", "led_cap"))


def test_option_delta_and_stair_addon():
    base = DeckSpec.from_dict(TWO)
    a = lighting.option_price(base)
    assert a["check"] > 0 and a["cost"] > 0 and a["risers"] == 5
    d = copy.deepcopy(TWO)
    d["geometry"]["parts"][0]["stairs"] = [{"side": "front:B", "width_in": 48, "position_in": 96, "total_rise_in": 96, "landing": "grade",
                                            "rails": 2, "name": "Stair to the yard"}]
    add = lighting.stair_addon(base, DeckSpec.from_dict(d))
    assert add["risers"] > 0 and add["caps"] > 0 and add["check"] > 0


def test_drink_rail_over_the_posts_takes_accent_lights():
    """A drink rail OVER the posts leaves no post caps: each post light is a small accent light on the post's deck side, just
    below the drink rail (railing.drink_rail_mount "over", or extras.lights.post_light "accent")."""
    d = copy.deepcopy(TWO)
    d["railing"]["drink_rail_mount"] = "over"
    spec = lit(d, post_light="accent")
    t, _, p = run(spec)
    pl = t.lighting
    assert pl.post_kind == "accent" and lighting.post_fixture(spec, pl.cfg) == "accent"
    skus = {l.sku for l in lighting_lines(t)}
    assert "AZTIXLEDACCB" in skus and "AZTDL3X3LANCAPB" not in skus
    assert pl.cap_w == 1.0 and pl.load_w == pl.n_riser * 2.0 + pl.n_cap * 1.0
    sc = build_scene(t.layout)
    acc = [b for b in sc.boxes if b.mat == "led_accent"]
    posts = [b for b in sc.boxes if b.kind == "railpost"]
    assert len(acc) == len(posts) and not [b for b in sc.boxes if b.mat == "led_cap"]
    for b in acc:                                     # on a side face of its post, below the post top, tagged for the option
        cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
        q = min(posts, key=lambda q: abs((q.x0 + q.x1) / 2 - cx) + abs((q.y0 + q.y1) / 2 - cy))
        assert (b.x0 >= q.x1 - 0.05 or b.x1 <= q.x0 + 0.05 or b.y0 >= q.y1 - 0.05 or b.y1 <= q.y0 + 0.05) and b.z1 < q.z1
        assert b.tag.endswith("Lighting option: accent light")
    assert "led_accent" in sc.materials and "led_cap" not in sc.materials


def test_sell_each_prices_the_lights_per_light():
    """extras.lights.sell_each: the lights sell at that price each, installed; the rest of the job keeps its margin."""
    t0, _, p0 = run(DeckSpec.from_dict(TWO))
    t1, _, p1 = run(lit(TWO, sell_each=200))
    n = t1.lighting.fixtures
    assert abs((p1.sell - p0.sell) - 200 * n) <= 1
    assert dict(p1.allocation)[lighting.short_words(t1.lighting)] == 200 * n
    assert abs(p1.light_sell - 200 * n) < 0.01 and p1.light_work > 0
    a = lighting.option_price(DeckSpec.from_dict(TWO), sell_each=200)
    assert a["check"] == 200 * a["fixtures"] and a["financed"] > a["check"]
