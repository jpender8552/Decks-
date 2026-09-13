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
    assert L.deck_sf == 617.2
    assert abs(L.finished_w - 55.2 * 12) < 0.01                                   # 55.2' along the house
    assert L.deck_sf == 617.2
    names = [e.name for e in L.edges]
    assert names == ["end:left", "front:C", "front:B", "front:A", "end:right"]   # fronts collinear: the house jogs, the deck edge is straight
    assert not [e for e in L.edges if e.name == "end:left"][0].exposed          # privacy wall
    assert L.zones[0].hot_tub and not L.zones[1].hot_tub


def test_rail_62_lf_cable(result):
    t, _, _ = result
    rl = t.layout.rail
    assert rl.system == "IRX" and rl.rail_lf == 62.2
    assert len(rl.posts) == 10 and len(rl.sections) == 9          # RP1-RP10, 9 bays of 8' kits cut to bay (handoff)
    assert any(p.kind == "CORNER" for p in rl.posts)
    assert all(s.ctc <= 96 + 0.01 for s in rl.sections)
    assert line(t, "IRX Cable Rail kit 8'").net == 9
    assert line(t, "IRX 36\" post kit").net == 10
    assert line(t, "Drink rail").order == 5 and line(t, "drink-rail brackets").net == 9
    assert line(t, "HeadLOK").net == 1


def test_timber_frame_and_caissons(result):
    t, _, _ = result
    L = t.layout
    assert all(b.size == "6x12" for z in L.zones for b in z.frame.beams)
    n_posts = sum(z.frame.n_posts for z in L.zones)
    assert n_posts == 8                                                        # B1 drop x 6 + B2 flush x 2 (handoff)
    labels = [bl.label for bl in L.beam_lines]
    assert any(l.startswith("DROP") and "C+B+A" in l for l in labels)          # one continuous drop beam 3' back
    assert any(l.startswith("FLUSH") and l.endswith(" C") for l in labels)
    assert line(t, "Sonotube 20\"").net == 3 and line(t, "Quikrete").net == 120
    assert line(t, "Stone veneer column base").net == 8
    assert line(t, "APB88").net == 8 and line(t, "anchor bolt").net == 8
    assert line(t, "CCQ68").net == 4 and line(t, "ECCQ68").net == 4
    assert line(t, "LUS410Z").net >= 80 and line(t, "H2.5AZ").net >= 60
    assert line(t, "LedgerLOK 6\"").net == 3 and "107 needed" in line(t, "LedgerLOK 6\"").why
    assert line(t, "Vycor").net == 2 and line(t, "L-flashing").net == 8 and line(t, "26 ga").net == 8
    assert line(t, "8x8x8").net == 8
    assert sum(l.net for l in t.lines if "Coastline 1x6x" in l.item) == 96      # 94 field + 2 rip boards
    assert line(t, "Dark Hickory 1x6x16").net == 4 and line(t, "Dark Hickory 1x6x20").net == 2
    assert line(t, "Coastline plugs").net == 9
    assert not [l for l in t.lines if "HUCQ" in l.item or "Camo EdgeClip" in l.item or l.category == "Fascia"]


def test_borders_and_dividers(result):
    t, _, _ = result
    members = [c.member for c in t.cut_list]
    assert any(m.startswith("Divider dc/b") for m in members) and any(m.startswith("Divider db/a") for m in members)
    assert any(m.startswith("Divider da1") for m in members)                    # zone A split at mid-span: no butt joints
    assert "Border end:right" in members and any(m.startswith("Outer border") for m in members)


def test_flags(result):
    _, f, _ = result
    sev = {(x.severity, x.topic) for x in f}
    assert ("ENGINEER", "snow") in sev
    assert ("ENGINEER", "engineering") in sev
    assert not [x for x in f if x.severity == "STOP"]
    assert any("noncombustible" in x.text for x in f)


def test_quote_pricing(result):
    """The handoff stack: materials 35,678.80 x 1.15 -> tax 4% -> labor 24,080.76 -> GC 7,200 at cost -> 42.5% GM -> $123,291 check / $132,571 financed."""
    t, f, p = result
    assert p.material_factor == 1.15 and p.tax_rate == 0.04 and p.gm == 0.425
    assert abs(p.labor - 24080.76) < 0.01
    assert p.gc == 7200
    assert abs(p.materials - 35678.80) / 35678.80 < 0.02
    assert abs(p.sell - 123291) / 123291 < 0.01
    assert p.retail == round(p.sell / 0.93)
    assert p.engineering == (1800, 3000)
    assert sum(v for _, v in p.allocation) == p.sell
    assert [k for k, _ in p.allocation][0].startswith("Timber-frame deck") and p.allocation[-1][0] == "Site & project services"
    opts = {o.name: o for o in p.options}
    assert opts["No stone column bases"].check == -14888 and opts["No stone column bases"].financed == -16009
    assert opts["Concrete pad under the deck"].check == 17757 and opts["Concrete pad under the deck"].financed == 19094
    assert opts["Fortress Evolution steel frame"].check == 1969
    assert -9500 < opts["TimberTech Fulton Rail in place of the IRX cable rail"].check < -6500   # handoff -7,000 at $260 EST panels; GS sheet $150 here
    assert abs(opts["Dark walnut oil finish on all timbers"].check - 4499) < 150
    assert opts["Privacy wall, Hardie board & batten — 23'"].check == 7597
    q = quote_markdown(t, p)
    assert "QUOTE · PRE-ENGINEERING" in q and "Check or ACH" in q and "Engineering —" in q and "OPTIONS" in q
    assert "INTERNAL" not in q and "GM" not in q
