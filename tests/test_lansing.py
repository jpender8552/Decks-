"""5549 S Lansing Ct: 8' x 12' at 10' on a (2)4x10 and two DF #1 posts, knee braces, IRX baluster rail at the owner's $120/LF."""
import json
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff.drawings import all_sheets
from decktakeoff.scene import build_scene, _rail_pairs

SPEC = json.loads((Path(__file__).parent.parent / "jobs" / "lansing_englewood.json").read_text())


@pytest.fixture(scope="module")
def result():
    from decktakeoff.spec import DeckSpec
    return run(DeckSpec.from_dict(SPEC), with_pricing=True)


def test_rail_sells_at_the_owner_rate(result):
    t, f, p = result
    assert dict(p.allocation)["Railing"] == round(120 * t.layout.rail.rail_lf)


def test_front_bay_spans_the_corners(result):
    t, f, p = result
    pairs = _rail_pairs(t.layout.rail)
    assert len(pairs) == len(t.layout.rail.sections)


def test_beam_posts_and_braces(result):
    t, f, p = result
    items = [l.item for l in t.lines]
    assert any(i.startswith("4x10x8 Douglas Fir #1") for i in items)
    assert any(i.startswith("6x6x10 Douglas Fir #1") for i in items)
    assert any("knee braces" in i for i in items)
    assert any("CCQ" in i for i in items)
    S = build_scene(t.layout)
    assert sum(1 for b in S.boxes if b.kind == "brace") == 4


def test_permit_sheets_have_the_wood_details(result):
    t, f, p = result
    nums = [n for n, _, _ in all_sheets(t.layout, t, f)]
    assert {"C-100", "D-502", "D-504"} <= set(nums)
