"""Regression: the Eagle's Nest quote (9 Eagle's Nest Ct, Silverthorne — the GSX standard for timber / multi-zone / engineered decks)."""
import json
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff.report import quote_markdown
from decktakeoff.spec import DeckSpec

SPEC = json.loads((Path(__file__).parent.parent / "examples" / "eagles_nest.json").read_text())


@pytest.fixture(scope="module")
def result():
    return run(DeckSpec.from_dict(SPEC))


def line(t, needle):
    m = [l for l in t.lines if needle in l.item]
    assert m, f"no line containing {needle!r}"
    return m[0]


def test_zones_area_and_outline(result):
    t, _, _ = result
    L = t.layout
    assert L.multi and [z.name for z in L.zones] == ["C", "B", "A"]
    assert L.deck_sf == 617
    assert abs(L.finished_w - (12 * 12 + 7 + 14 * 12 + 7 + 28 * 12)) < 0.01      # 55'-2" along the house
    names = [e.name for e in L.edges]
    assert names == ["end:left", "front:C", "front:B", "step:B-A", "front:A", "end:right"]
    assert not [e for e in L.edges if e.name == "end:left"][0].exposed          # privacy wall
    assert L.zones[0].hot_tub and not L.zones[1].hot_tub


def test_rail_62_lf_cable(result):
    t, _, _ = result
    rl = t.layout.rail
    assert rl.system == "IRX" and rl.rail_lf == 62
    assert any(p.kind == "CORNER" for p in rl.posts)
    assert all(s.ctc <= 72 + 0.01 for s in rl.sections)
    assert line(t, "cable infill kit").net == len(rl.sections)
    assert "drink rail" in line(t, "Dark Hickory 1x6x20 Square Edge — drink rail").item


def test_timber_frame_and_caissons(result):
    t, _, _ = result
    L = t.layout
    assert all(b.size == "6x12" for z in L.zones for b in z.frame.beams)
    n_posts = sum(z.frame.n_posts for z in L.zones)
    assert 8 <= n_posts <= 10
    assert line(t, "Drilled caisson 20\"").net == n_posts
    assert line(t, "Stone column base").net == n_posts
    assert line(t, "HU410").item.endswith("black powder-coat")
    assert line(t, "CCQ88").net == n_posts
    assert line(t, "4x10x20 Douglas Fir #1").net > 0
    assert line(t, "8x8x8").net == n_posts
    assert not [l for l in t.lines if "HUCQ" in l.item or "LedgerLOK" in l.item or "G-Tape" in l.item or "Fascia" in l.category]
    assert not [l for l in t.lines if "Camo EdgeClip" in l.item]
    assert "Cortex" in line(t, "Cortex for TimberTech").item


def test_borders_and_dividers(result):
    t, _, _ = result
    members = [c.member for c in t.cut_list]
    assert "Divider c/b" in members and "Divider b/a" in members
    assert "Border front:a" in members and "Border end:right" in members
    assert "Border end:left" in members            # a border along the privacy wall edge, no rail there


def test_flags(result):
    _, f, _ = result
    sev = {(x.severity, x.topic) for x in f}
    assert ("ENGINEER", "snow") in sev
    assert ("ENGINEER", "engineering") in sev
    assert not [x for x in f if x.severity == "STOP"]
    assert any("noncombustible" in x.text for x in f)


def test_quote_pricing(result):
    t, f, p = result
    assert p.tax_rate == 0.08375
    assert p.retail == round(p.sell / 0.93)
    assert p.engineering == (1800, 3000)
    assert sum(v for _, v in p.allocation) == p.sell
    names = [o.name for o in p.options]
    assert "No stone column bases" in names and "No drink rail" in names
    stone = next(o for o in p.options if o.name == "No stone column bases")
    assert stone.check < 0 and stone.financed == round(stone.check / 0.93)
    pad = next(o for o in p.options if o.name.startswith("Concrete pad"))
    assert pad.check == round(9500 / 0.55)
    q = quote_markdown(t, p)
    assert "QUOTE · PRE-ENGINEERING" in q and "Check or ACH" in q and "Engineering —" in q and "OPTIONS" in q
    assert "INTERNAL" not in q and "GM" not in q
