import pytest

from decktakeoff import engineering as eng
from decktakeoff import run
from decktakeoff.spec import DeckSpec


def test_joist_table_values():
    assert eng.joist_allowable("2x10", "SYP", 16)[0] == 168
    assert eng.joist_allowable("2x10", "DF", 16)[0] == 163
    assert eng.joist_allowable("2x8", "SYP", 12)[0] == 157
    assert eng.check_joist("2x10", "SYP", 16, 170, 50).ok is False


def test_snow_scales_spans_and_notes():
    allow, table = eng.joist_allowable("2x10", "SYP", 16, total_psf=70)
    assert table == 168 and allow < 168
    assert eng.check_joist("2x10", "SYP", 16, 120, 70).note


def test_beam_span_interpolation():
    allow, _, _ = eng.beam_allowable("4x10", "DF", 15.33 * 12)
    assert 57 <= allow <= 59
    assert eng.beam_allowable("6x10", "DF", 120)[2]      # aliased beams carry a note


def test_ledger_counts():
    assert eng.ledger_fastener_count(141, 160, "LedgerLOK")[0] == 13
    n, rule = eng.ledger_fastener_count(144, 168, "1/2 lag")
    assert "13" in rule and n > 20


def test_stairs():
    g = eng.stair_geometry(30, 48)
    assert g.risers == 4 and g.treads == 3 and g.handrail_required and not g.guard_required
    g = eng.stair_geometry(54, 48)
    assert g.risers == 7 and abs(g.riser_in - 54 / 7) < 0.01 and g.guard_required
    assert g.stringers == 5


def test_deep_deck_adds_a_beam():
    t, f, _ = run(DeckSpec.from_dict({"geometry": {"width": 16, "depth": 24, "height_in": 36}}))
    assert len(t.layout.frame.beams) == 2
    assert all(c.ok for c in t.layout.frame.joist_checks)
    assert any("added a drop beam" in n for n in t.notes)


def test_flush_front_beam_is_the_rim():
    t, f, _ = run(DeckSpec.from_dict({"geometry": {"width": 12, "depth": 12, "height_in": 40},
                                      "framing": {"beams": [{"kind": "flush", "size": "(2)2x10", "species": "SYP", "setback_in": 0}]}}))
    assert not [c for c in t.cut_list if c.member == "Front rim plies"]
    assert t.layout.frame.beams[0].label.startswith("FRONT FLUSH")
    assert not [l for l in t.lines if "H2.5AZ" in l.item]


def test_flags_fire_snow_setback_engineering():
    spec = DeckSpec.from_dict({"site": {"wui_fire_zone": True, "ground_snow_psf": 60, "rear_setback_required_ft": 20, "deck_to_rear_line_ft": 12},
                               "geometry": {"width": 12, "depth": 12, "height_in": 30}, "decking": {"collection": "Prime+", "color": "Coconut Husk"},
                               "extras": {"hot_tub": True}})
    _, f, _ = run(spec)
    topics = {(x.severity, x.topic) for x in f}
    assert ("STOP", "fire") in topics
    assert ("ENGINEER", "snow") in topics
    assert ("STOP", "setback") in topics
    assert ("ENGINEER", "engineering") in topics


def test_guard_required_over_30():
    _, f, _ = run(DeckSpec.from_dict({"geometry": {"width": 12, "depth": 12, "height_in": 36}, "railing": {"system": "none"}}))
    assert any(x.severity == "STOP" and x.topic == "guard" for x in f)


def test_footing_upgrade_and_concrete():
    t, f, _ = run(DeckSpec.from_dict({"geometry": {"width": 20, "depth": 14, "height_in": 30}, "site": {"ground_snow_psf": 40},
                                      "framing": {"beams": [{"kind": "drop", "size": "4x12", "species": "DF", "setback_in": 24, "post_spacing_max_in": 84}]}}))
    fr = t.layout.frame
    assert fr.footing_load_lb > 0
    t2, _, _ = run(DeckSpec.from_dict({"geometry": {"width": 20, "depth": 14, "height_in": 30}, "framing": {"footing_type": "concrete"},
                                       "site": {"frost_depth_in": 36, "soil_bearing_psf": 1500}}))
    assert t2.layout.frame.footing_dia_in >= 12 and t2.layout.frame.footing_depth_in == 42
    assert any("Concrete mix" in l.item for l in t2.lines)
