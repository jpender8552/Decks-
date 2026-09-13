import json

from fastapi.testclient import TestClient

from decktakeoff.intake import parse_details, spec_from_extraction
from decktakeoff.service import app
from decktakeoff.units import to_inches, ftin


def test_units():
    assert to_inches("15'-7 1/2\"") == 187.5
    assert to_inches("11'9") == 141
    assert to_inches("187.5in") == 187.5
    assert to_inches(15.625) == 187.5
    assert to_inches(30, "in") == 30
    assert ftin(187.5) == "15'-7 1/2\""
    assert ftin(6.0625) == "6 1/16\""


def test_parse_details():
    s = parse_details("11'9 x 15'7.5 deck in Thornton, 30 in high, Prime+ Coconut Husk, Fulton rail black, demo the old deck, 4 steps on the right")
    assert (s.geometry.width_in, s.geometry.depth_in, s.geometry.height_in) == (141, 187.5, 30)
    assert (s.decking.collection, s.decking.color) == ("Prime+", "Coconut Husk")
    assert s.railing.system == "Fulton" and s.railing.color == "Black"
    assert s.extras.demo_existing and s.stairs[0].side == "right"
    assert s.site.city == "Thornton"
    s = parse_details("14' deep x 20' wide, 42 inches high, Vintage Dark Hickory, 2x12 joists @ 12 oc, flush beam, freestanding, concrete piers, snow 60 psf, wui")
    assert (s.geometry.width_in, s.geometry.depth_in) == (240, 168)
    assert s.framing.joist_size == "2x12" and s.framing.joist_spacing_in == 12
    assert s.framing.beams[0].kind == "flush" and s.framing.beams[0].size == "(2)2x12"
    assert s.geometry.attachment == "freestanding" and s.framing.footing_type == "concrete"
    assert s.site.ground_snow_psf == 60 and s.site.wui_fire_zone


def test_spec_from_extraction_merges_and_notes():
    x = dict(width_ft=12, depth_ft=16, height_in=0, attachment="ledger", board_direction="parallel", picture_frame=True,
             stairs=[{"side": "front", "width_in": 48, "risers": 4}], rail_sides=["left", "right", "front"], rail_openings=[], beam_kind="drop",
             beam_setback_ft=2, decking_collection="Prime+", decking_color="Sea Salt Gray", rail_system="Fulton", rail_color="Black",
             notes=["12'-0\" along house", "16'-0\" projection"], confidence="medium", unreadable=["height above grade"])
    s = spec_from_extraction(x, details="30 in high")
    assert s.geometry.height_in == 30 and s.geometry.width_in == 144 and s.geometry.depth_in == 192
    assert s.decking.color == "Sea Salt Gray" and s.stairs[0].side == "front"
    assert any("NOT on the drawing" in n for n in s.source_notes)


def test_service_takeoff():
    c = TestClient(app)
    assert c.get("/health").json() == {"ok": True}
    r = c.post("/takeoff", json={"spec": json.load(open("examples/jason_ct.json")), "price": True, "gsx": True})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["layout"]["decking"]["clips"] == 330
    assert j["pricing"]["sell"] > 0 and "# Takeoff" in j["markdown"] and "BOM = [" in j["gsx_job_block"]
    r = c.post("/takeoff", json={"details": "12x16, 30 in high, Prime+ Coconut Husk"})
    assert r.status_code == 200 and r.json()["summary"]["deck_sf"] > 0
    assert c.post("/takeoff", json={}).status_code == 400
