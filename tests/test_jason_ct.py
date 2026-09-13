"""Regression: the engine must reproduce the hand takeoff Jade approved for 9528 Jason Ct (R5 set)."""
import json
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff.spec import DeckSpec

SPEC = json.loads((Path(__file__).parent.parent / "examples" / "jason_ct.json").read_text())


@pytest.fixture(scope="module")
def result():
    return run(DeckSpec.from_dict(SPEC))


def line(t, needle):
    m = [l for l in t.lines if needle in l.item]
    assert m, f"no line containing {needle!r}"
    return m[0]


def test_nominal_12x16_sizes_to_the_boards(result):
    t, _, _ = result
    assert SPEC["geometry"]["width"] == 12 and SPEC["geometry"]["depth"] == 16
    assert t.layout.finished_w == 141.0            # 11'-9" frame
    assert t.layout.finished_d == 187.5            # 15'-7 1/2" frame
    assert abs(t.layout.decking.field_len - 132.0) < 0.01   # field boards cut to 11'-0"
    assert t.layout.decking.deck_w <= 144 and t.layout.decking.deck_d <= 192


def test_frame_geometry(result):
    t, _, _ = result
    fr = t.layout.frame
    assert fr.joist_x == [16, 32, 48, 64, 80, 96, 112, 128]
    assert fr.pf_x == [5.25, 135.75]
    assert fr.joist_len == 183.0
    b = fr.beams[0]
    assert b.kind == "drop" and b.size == "4x10"
    assert abs(b.cl_y - 161.75) < 0.01
    assert [round(x, 2) for x in b.posts_x] == [12.5, 70.5, 128.5]
    assert abs(b.post_spacing - 58.0) < 0.01 and b.check.ok
    assert fr.n_blocks_per_row == 9 and len(fr.blocking_rows_y) == 1
    assert fr.n_posts == 3 and fr.footing_model == "DP-50/50"
    assert fr.footing_load_lb < 3300


def test_decking_counts(result):
    t, _, _ = result
    d = t.layout.decking
    assert d.rows == 33 and d.sf == 187
    assert d.clips == 330
    assert (d.first_row_screws, d.border_screws, d.fascia_screws) == (10, 76, 59)
    assert line(t, "1x6x12 Grooved").net == 33 and line(t, "1x6x12 Grooved").order == 35
    assert line(t, "1x6x16 Square Edge").net == 3 and line(t, "1x6x16 Square Edge").order == 4
    assert line(t, "Fascia").net == 4 and line(t, "Fascia").order == 5
    assert line(t, "EdgeClip").order == 4
    assert line(t, "Cap-Tor").order == 1 and "145" in line(t, "Cap-Tor").why


def test_lumber_and_hardware(result):
    t, _, _ = result
    assert line(t, "2x10x12").net == 4 and line(t, "2x10x12").order == 5
    assert line(t, "2x10x16").net == 14 and line(t, "2x10x16").order == 15
    assert line(t, "4x10x12").order == 1
    assert line(t, "6x6x8").order == 1
    assert line(t, "LUS28Z").net == 20
    assert line(t, "HUCQ210-2").net == 4
    assert line(t, "H2.5AZ").net == 12
    assert line(t, "BC46Z").net == 3 and line(t, "ABA66Z").net == 3
    assert "13 needed" in line(t, "LedgerLOK").why
    assert line(t, "DTT1Z").net == 4
    assert "66 needed" in line(t, "SD10212").why
    assert "120 needed" in line(t, 'nail 3"').why and "200 needed" in line(t, 'nail 1-1/2"').why
    assert line(t, "7/16").net == 12 and line(t, "7/16").order == 14
    assert line(t, 'G-Tape 3035 2"').order == 3 and line(t, 'G-Tape 3035 4"').order == 1


def test_rail(result):
    t, _, _ = result
    rl = t.layout.rail
    kinds = sorted(p.kind for p in rl.posts)
    assert kinds == ["CORNER", "CORNER", "END", "END", "LINE", "LINE"]
    assert rl.rail_lf == 35
    assert line(t, "Fulton Rail 8'").net == 3 and line(t, "Fulton Rail 6'").net == 2


def test_pricing_model(result):
    t, f, p = result
    assert p.tax_rate == 0.085
    assert p.gm == 0.45
    assert p.gc == 4 * 187 + 800
    assert p.sell == round((p.materials + p.tax + p.labor) / 0.55 + p.gc)
    assert p.retail == round((p.sell - p.gc) / 0.93 + p.gc)
    assert sum(v for _, v in p.allocation) == p.sell
    assert dict(p.labor_lines and [(l[0], l[4]) for l in p.labor_lines])["Railing"] == 35 * 20


def test_flags_clean(result):
    _, f, _ = result
    assert not [x for x in f if x.severity == "STOP"]
    assert not [x for x in f if x.severity == "ENGINEER"]
