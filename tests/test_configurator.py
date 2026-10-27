"""The interactive options page (decktakeoff.configurator): option specs become JSON patches, the scenes of every valid
combination are merged with a mask per box (an option's boxes show only with it, the boxes it replaces hide with it), the
lights become the page's fixtures, and the page is one self-contained file."""
import copy
import json
import re

from decktakeoff.configurator import _apply, _diff, _load, build_configurator, configurator_data

TWO = {
    "job": "two-level configurator test", "site": {"city": "Centennial", "lat": 39.5843, "lon": -104.9524, "rear_azimuth_deg": 25.25,
                                                   "utc_offset_h": -6.0, "sun_when": "2026-06-21T16:00"},
    "geometry": {"height_in": 96, "attachment": "ledger", "picture_frame": True, "parts": [
        {"name": "Lower level", "placement": {"origin": [0, 0]},
         "geometry": {"height_in": 96, "zones": [{"name": "B", "width_in": 240, "depth_in": 120, "wall_offset_in": 0}]},
         "railing": {"edges": ["end:left", "front:B"]}, "stairs": []},
        {"name": "Upper level", "placement": {"origin": [20, 0]},
         "geometry": {"height_in": 132, "zones": [{"name": "C", "width_in": 240, "depth_in": 120, "wall_offset_in": 0}]},
         "railing": {"edges": ["end:left", "front:C", "end:right"]},
         "stairs": [{"side": "left", "width_in": 44, "position_in": 72, "total_rise_in": 36, "landing": "deck", "rails": 1}]}]},
    "framing": {"joist_size": "2x10", "joist_spacing_in": 12, "post_size": "6x6", "footing_type": "diamond_pier",
                "beams": [{"kind": "drop", "size": "(3)2x10", "setback_in": 24}]},
    "decking": {"brand": "TimberTech", "collection": "Vintage", "color": "English Walnut", "profile": "square"},
    "railing": {"system": "IRX Baluster", "color": "Black", "height_in": 36, "drink_rail": True},
    "extras": {}}


def _options():
    stairs = copy.deepcopy(TWO)
    stairs["geometry"]["parts"][0]["stairs"] = [{"side": "front", "width_in": 48, "position_in": 60, "landing": "grade", "rails": 2,
                                                 "name": "Stairs to the yard"}]
    lights = copy.deepcopy(TWO)
    lights["extras"]["lights"] = {"riser": True, "post_cap": True}
    return {"stairs": stairs, "lights": lights}


def test_patches_round_trip():
    base = _load(TWO)
    for opt in _options().values():
        o = _load(opt)
        assert _apply(base, _diff(base, o)) == o


def test_masks_follow_the_options():
    data, st = configurator_data(TWO, _options())
    assert st["combos"] == 4 and st["options"] == ["stairs", "lights"]
    assert st["deltas"] == {"stairs": ["geometry.parts[0].stairs"], "lights": ["extras.lights"]}
    groups = st["groups"]
    assert groups["base"] > 100 and groups["option:Stairs to the yard"] > 0 and groups["option:Lighting"] > 0
    assert any(g.startswith("option:Stairs to the yard + Lighting") for g in groups)       # the yard stair's own lights
    bits = {o["key"]: o["bit"] for o in data["options"]}
    with_lights = sum(1 << i for i, c in enumerate(data["combos"]) if c >> bits["lights"] & 1)     # bit i = the i-th valid combination
    assert data["fixtures"] and all(f[9] & ~with_lights == 0 for f in data["fixtures"])   # a light shows only with the lighting option
    kinds, B, k = data["kinds"], data["boxes"], data["stride"]
    with_stairs = sum(1 << i for i, c in enumerate(data["combos"]) if c >> bits["stairs"] & 1)
    tread = kinds.index("tread")
    # the upper level's inter-level stair is base; the yard stair's treads come only with the stairs option
    masks = {B[i + 12] for i in range(0, len(B), k) if B[i + 9] == tread}
    assert data["all_mask"] in masks and with_stairs in masks
    assert data["site"]["rear_az"] == 25.25 and data["site"]["minutes"] == 16 * 60 and data["site"]["date"] == "2026-06-21"
    assert {v["key"] for v in data["views"]} >= {"yard", "upper", "lower", "aerial"}


def test_page_is_one_self_contained_file(tmp_path):
    st = build_configurator(TWO, _options(), tmp_path / "deck.html", title="Configurator test")
    html = (tmp_path / "deck.html").read_text()
    assert st["bytes"] < 8_000_000 and "<title>Configurator test</title>" in html
    assert "https://" not in re.sub(r"<script>.*?</script>", "", html, flags=re.S)           # nothing loads from the network
    payload = re.search(r'<script type="application/json" id="cfg-data">(.*?)</script>', html, re.S).group(1)
    data = json.loads(payload.replace("<\\/", "</"))
    assert data["options"][0]["label"] == "Stairs to the yard" and len(data["boxes"]) % data["stride"] == 0
    assert "THREE.WebGLRenderer" in html and "window.__ready = true" in html


def test_two_layouts_of_one_option_are_exclusive():
    opts = _options()
    alt = copy.deepcopy(TWO)
    alt["geometry"]["parts"][0]["stairs"] = [{"side": "front", "width_in": 48, "position_in": 150, "landing": "grade", "rails": 2,
                                              "name": "Stairs to the yard"}]
    data, st = configurator_data(TWO, {"stairs": opts["stairs"], "stairs_alt": alt, "lights": opts["lights"]})
    bits = {o["key"]: o["bit"] for o in data["options"]}
    assert st["combos"] == 6 and not any(c >> bits["stairs"] & 1 and c >> bits["stairs_alt"] & 1 for c in data["combos"])
    by = {o["key"]: o for o in data["options"]}
    assert by["stairs"]["excludes"] == ["stairs_alt"] and by["stairs_alt"]["excludes"] == ["stairs"] and by["lights"]["excludes"] == []
    assert by["stairs_alt"]["label"] == "Stairs to the yard — along the deck"
    on = lambda key: sum(1 << i for i, c in enumerate(data["combos"]) if c >> bits[key] & 1)
    tread = data["kinds"].index("tread")
    B, k = data["boxes"], data["stride"]
    masks = {B[i + 12] for i in range(0, len(B), k) if B[i + 9] == tread}
    assert on("stairs") in masks and on("stairs_alt") in masks                     # each layout's treads show with it alone
    assert not st["warnings"]
