"""The D&D order for the frame (Prentice, jobs/prentice_centennial.json): framing lumber packed into its offcuts and priced per length,
the hardware and hanger nails by Simpson's schedules, the G-Tape, GRK RSS, flashing, LedgerLOK and lateral-tie lags — and the crew's
build steps, cut list and 3D agreeing with that order."""
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from decktakeoff.spec import DeckSpec
from decktakeoff.takeoff import (box_cross_members, build_takeoff, ledger_spans, ledgerlok_count, ledgerlok_spacing, pack_lumber,
                                 pack_plan)

JOBS = Path(__file__).parent.parent / "jobs"
EXAMPLES = Path(__file__).parent.parent / "examples"


def _spec(path):
    return DeckSpec.from_dict(json.loads(path.read_text()))


def _takeoff(name):
    return build_takeoff(_spec(JOBS / name))


@pytest.fixture(scope="module")
def t():
    return _takeoff("prentice_centennial.json")


def line(t, needle):
    m = [l for l in t.lines if needle in l.item]
    assert m, f"no line containing {needle!r}"
    return m[0]


# ---------------------------------------------------------------- the packer
def test_short_pieces_fill_offcuts_before_new_stock():
    pieces = [("2x10", 129.25, "joist")] * 2 + [("2x10", 10.5, "block")] * 2     # 10'-9 1/4" joists leave 14-1/2" offcuts in 12' stock
    plan = pack_plan(pieces)
    assert [(n, s) for n, s, _ in plan] == [("2x10", 12), ("2x10", 12)]       # both blocks ride the offcuts: no third board
    assert all(sum(L + 0.25 for L, _, _ in cut) <= s * 12 for _, s, cut in plan)
    assert pack_lumber(pieces)[("2x10", 12)] == (2, ["joist, block", "joist, block"])


def test_a_length_goes_when_moving_up_costs_less_than_its_cull():
    price = lambda nom, st: {10: 38.80, 12: 43.93, 14: 54.32, 16: 62.03, 20: 80.51}[st]
    pieces = [("2x10", 113.0, "joist")] * 2 + [("2x10", 129.0, "joist")] * 3 + [("2x10", 165.0, "joist")] * 15 + [("2x10", 203.5, "ledger")]
    packed = pack_lumber(pieces, price=price)
    assert ("2x10", 10) not in packed and packed[("2x10", 12)][0] == 5       # 2 x $5.13 up to 12' < the 10' cull ($38.80)
    assert packed[("2x10", 14)][0] == 15 and packed[("2x10", 20)][0] == 1    # 15 x $26.19 up to 20' > the 14' cull: the 14s stay
    assert pack_lumber(pieces)[("2x10", 10)][0] == 2                         # no prices: each piece on its own shortest stock


def test_a_length_moves_up_only_to_a_documented_price():
    price = lambda nom, st: {12: 43.93, 16: 62.03, 24: 93.12}[st]
    pieces = [("2x10", 190.0, "joist")] + [("2x10", 280.0, "rim")] * 14
    assert pack_lumber(pieces, price=price)[("2x10", 24)][0] == 15           # unrestricted: the lone 16' rides a 24'
    packed = pack_lumber(pieces, price=price, known=lambda nom, st: st in (12, 16, 20))
    assert packed[("2x10", 16)][0] == 1 and packed[("2x10", 24)][0] == 14   # 24' has no D&D price (and no TrueFrame 24'): the 16' stays


def test_fillmore_keeps_its_documented_16_foot_joist():
    from decktakeoff import run
    t = run(_spec(JOBS / "fillmore_centennial.json"), with_pricing=False)[0]      # two levels: the composite order
    l16, l24 = line(t, "2x10x16 "), line(t, "2x10x24 ")
    assert (l16.net, l16.order, l16.unit_cost) == (2, 3, 62.03) and (l24.net, l24.order) == (14, 15)       # (the lower level's bay fill joist cuts from a 16')


def test_lengths_keep_the_order_the_pieces_call_for_them():
    assert list(pack_lumber([("4x10", 190.0, "b"), ("4x10", 130.0, "a")])) == [("4x10", 16), ("4x10", 12)]


def test_box_step_cross_members_follow_the_layout_when_it_counts_them():
    assert box_cross_members(SimpleNamespace(width=73.0)) == 6                     # every 16" between the end members
    assert box_cross_members(SimpleNamespace(width=73.0, cross_members=10)) == 10  # the stair layout's own count wins


# ---------------------------------------------------------------- lumber
def test_frame_lumber_packs_offcuts_and_prices_per_length(t):
    assert not [l for l in t.lines if l.item.startswith("2x10x10 ")]            # its 2 joists come from 12' stock
    l12, l14, l20 = line(t, "2x10x12 "), line(t, "2x10x14 "), line(t, "2x10x20 ")
    assert (l12.net, l12.order, l12.unit_cost) == (35, 36, 43.93) and "210N12TFJ" in l12.source      # (with the bay's fill joist and the breaker blocks)
    assert (l14.net, l14.order) == (15, 16) and l14.source.startswith("EST")      # no GSEXT1 price for a 14'
    assert (l20.net, l20.order, l20.unit_cost) == (1, 2, 80.51)
    assert all(l.why.startswith("+1 cull") for l in (l12, l14, l20))           # the owner's cull: 1 per length
    assert "PF block" in l14.why                                                # blocks cut from the joist offcuts
    assert line(t, "2x12x12 ").unit_cost == 57.37
    l26 = line(t, "2x6x12 ")
    assert (l26.item, l26.unit_cost, l26.net, l26.order) == ("2x6x12 #1 KDAT GC", 21.62, 6, 7)     # no TrueFrame 2x6 (box-step cross members at 8" max)
    assert "rail post blocking" in l26.why and "rail post cross block" in l26.why                     # TimberTech's IRX post detail is 2x6
    assert line(t, "6x6x8 Douglas Fir").unit_cost == 90.73                    # D&D's DF rough, not the #2 treated $46


def test_box_step_2x6_follows_the_cut_list(t):
    frames = [c for c in t.cut_list if c.member.startswith("Box step frame")]
    cms = [c for c in t.cut_list if c.member.startswith("Box step cross members")]
    assert len(frames) == len(cms) == 2
    for c in frames:                                          # the two box steps miter at the corner: rims run long to the miter
        assert c.qty == 2 and "mitered to the next box step" in c.note and re.search(r"\b(\d+) cross members between", c.note)
    assert next(c for c in frames if "left side" in c.member).length_in > 73.0
    boxes = [s_ for s_ in t.layout.stairs if getattr(s_, "build", "") == "box"]           # the layout's count: the tread line's 8" max (11 + 10)
    assert sorted(int(re.search(r"\b(\d+) cross members between", c.note).group(1)) for c in frames) == sorted(s_.cross_members for s_ in boxes)
    assert sum(c.qty for c in cms) == sum(s_.cross_members for s_ in boxes) and all(c.nominal == "2x6" and c.length_in == 7.63 for c in cms)
    assert "box step cross member" in line(t, "2x6x12 ").why


def test_box_step_cut_list_matches_the_3d(t):
    from decktakeoff.scene import build_scene
    S = build_scene(t.layout)
    rims, cms = {}, {}
    for b in S.boxes:
        if "box step frame" in (b.tag or ""):
            side = b.tag.split()[-1].replace("edge:", "side ")
            q = b.quad
            ln = max(math.hypot(q[(i + 1) % 4][0] - q[i][0], q[(i + 1) % 4][1] - q[i][1]) for i in range(4)) * 12 if q else max(b.x1 - b.x0, b.y1 - b.y0) * 12
            (rims if b.kind == "rim" else cms).setdefault(side, []).append(ln)
    assert sorted(rims) == ["side 2", "side 3"]
    for side, lens in rims.items():                          # each rim's long point as the 3D cuts it, within 1/32"
        c = next(c for c in t.cut_list if c.member.startswith("Box step frame") and ("left side" if side == "side 2" else "front angle") in c.member)
        assert abs(c.length_in - max(lens)) < 1 / 32
    assert sorted(round(x, 1) for x in rims["side 2"]) == [74.1, 77.8] and sorted(round(x, 1) for x in rims["side 3"]) == [69.1, 72.8]
    assert all(abs(min(v) - 7.63) < 0.01 for v in cms.values())       # square cross members: the run less the 3/4" HardieTrim riser and two rims


def test_rail_post_blocks_cut_to_the_bay(t):
    # IRX: TimberTech's 2x6 blocking + 2x6 cross block under every post (IRX install guide Dia. #3A/#3B), each cut to the bay
    for m in ("Rail post blocking (IRX)", "Rail post cross blocks (IRX)"):
        c = next(c for c in t.cut_list if c.member == m)
        assert (c.nominal, c.length_in, c.qty) == ("2x6", 10.5, len(t.layout.rail.posts)) == ("2x6", 10.5, 9), m      # 12" OC less a joist, one per post
    assert not [c for c in t.cut_list if c.member == "Rail post blocks"]
    te = build_takeoff(_spec(EXAMPLES / "eagles_nest.json"))                          # timber: 4x10 joists @ 12" leave an 8-1/2" bay
    ce = next(c for c in te.cut_list if c.member == "Rail post blocks")
    assert ce.nominal == "4x10" and ce.length_in == 12 - 3.5 and "(12\" OC bay)" in ce.note


# ---------------------------------------------------------------- footings, hardware, nails
def test_post_bases_and_piers(t):
    assert line(t, "ABA66RZ").unit_cost == 28.97
    sd = line(t, "SD10212")
    assert sd.net == 1 and "88 needed" in sd.why                              # Simpson: (8) per ABA66RZ x 11
    dp = line(t, "Diamond Pier")
    assert dp.unit_cost == 150.0 and dp.source.startswith("owner")          # the owner's $150 stands (D&D quotes $165.61)


def test_hangers_and_angles(t):
    sur, sul = line(t, "SUR210Z skewed"), line(t, "SUL210Z skewed")
    assert (sur.net, sur.order, sul.net, sul.order) == (13, 14, 15, 16)       # by hand, 1 spare each (+ the fill joist's rim end)
    assert "sides 3, 7, 11" in sur.why and "sides 1, 5, 9" in sul.why
    d2 = line(t, "SUL210-2Z skewed double hanger")                          # the double named by its hand, as D&D ships it
    assert (d2.net, d2.order) == (1, 1) and "skewed left" in d2.item and not [l for l in t.lines if "SUR210-2Z" in l.item]
    lssu = line(t, "LSSU210Z field-skewable")
    assert (lssu.net, lssu.order) == (4, 5)                                   # bends to either hand: 1 spare
    a35 = line(t, "A35Z framing angle — the rims to the edge posts")
    assert (a35.net, a35.order) == (42, 44) and "1 mid-span under one continuous rim x 2" in a35.why


def test_hanger_nails_per_simpson(t):
    n3, n16 = line(t, 'hanger nail 3"'), line(t, '0.162" x 3-1/2"')
    n25, n15 = line(t, '0.162" x 2-1/2"'), line(t, 'hanger nail 1-1/2"')
    assert n3.net == 2 and "564 needed" in n3.why                             # LUS210Z 44 x (8 + 4) + LSSU210Z 4 x 9
    assert n16.net == 2 and "308 needed" in n16.why                           # SUR/SUL210Z 28 x 10 + the two doubles x 14
    assert n25.net == 1 and "6 needed" in n25.why                             # SUR/SUL210-2Z joist nails
    assert n15.net == 2 and "824 needed" in n15.why                           # SUR/SUL 280 + LSSU 28 + LSSU-2 12 + A35Z 42 x 12
    h = t.schedule["Hangers"]
    assert "SUR/SUL210Z (10) 16d face + (10) 10d x 1-1/2\"" in h and "LSSU210Z bent to the skew, (9) 10d face" in h


def test_no_nail_box_without_a_need():
    tl = _takeoff("lansing_englewood.json")                                  # LUS joist nails are 3": nothing takes a 1-1/2" nail
    assert not [l for l in tl.lines if 'hanger nail 1-1/2"' in l.item]
    assert all("0 needed" not in l.why for l in tl.lines if "nail" in l.item)


def test_rss_tape_and_flashing(t):
    rss = [l for l in t.lines if l.item.startswith("GRK RSS")]
    assert len(rss) == 1 and "50 ct" in rss[0].item and rss[0].unit_cost == 15.88
    assert rss[0].net == 14 and "691 needed" in rss[0].why and "blocking 348" in rss[0].why and "box steps 108" in rss[0].why   # 58 blocks x 6; 11 + 10 cross members
    assert "rail post blocks 108" in rss[0].why                                 # 9 posts x 2 pieces x (3) each end
    g4 = line(t, 'G-Tape 3035 4"')
    assert g4.net == 1 and "63' needed" in g4.why                             # one 4" strip over the doubled rim, not one per ply
    v = line(t, "Vycor")
    assert v.item.startswith("Grace Vycor Plus") and v.unit_cost == 62.6
    lf = line(t, "L-flashing")
    assert (lf.net, lf.unit_cost, lf.sku) == (5, 9.65, "LFLASH448G") and "x 8'" in lf.item and "G-Tape" in lf.why


def test_ledgerlok_spacing_follows_fastenmaster_table_1():
    n, rule = ledgerlok_count([(144.0, 144.0)])
    assert n == 13 and 'staggered 12" OC, first 3-3/4" from each end' in rule      # 12' joists: 12" OC
    assert ledgerlok_count([(144.0, 156.0)])[0] == 15     # 13' joists: 10" OC
    assert ledgerlok_count([(144.0, 108.0)])[0] == 13     # 9' joists: the table's 14" never opens the owner's 12"
    assert ledgerlok_count([(144.0, 156.0)], 60.0)[0] == 21   # 60 psf, 14' row: 7"
    assert [ledgerlok_spacing(s * 12.0) for s in (6, 10, 12, 13, 14, 15)] == [12, 12, 12, 10, 10, 9]
    assert ledgerlok_spacing(156.0, species="HF") == 8    # Hem-Fir ledger, 14' row


def test_ledger_and_lateral_ties(t):
    ll = line(t, "LedgerLOK")
    assert ll.net == 1 and "35 needed" in ll.why
    rule = t.schedule["Ledger"]                         # the tightest spacing leads (the drawings read 'staggered N" OC'), the piece that opens up after
    assert 'staggered 10" OC' in rule and '12" OC on the 2\'-5 3/4" bay-face piece (joists to' in rule and "35 fasteners" in rule
    assert "side 1" not in rule                         # the pieces by the cut list's names: A-100 and S-101 number only the open sides
    segs = ledger_spans(t.spec, t.layout)               # the same pieces and spans from the layout alone (what the drawings can call)
    assert [s for _, _, s in segs] == ["bay face", "bay face", "bay face", "main wall"] and ledgerlok_count(segs)[0] == 35
    dtt, lag = line(t, "DTT1Z lateral tie kit"), line(t, '3/8" x 6" HDG lag')
    n_dtt = int(re.search(r"(\d+) DTT1Z x 1", lag.why).group(1))        # one lag per tie, on the line the IRX rail posts' lags share (one +2)
    assert n_dtt == dtt.net and lag.order == lag.net + 2 and "R507.9.2(2)" in lag.why


def test_frame_build_step_lists_every_frame_line(t):
    from decktakeoff.buildset import step_sheets
    steps = {s_["title"]: s_ for s_ in step_sheets(t, t.layout)}
    fin = steps["Frame"]["goes_in"]
    for k in ("Galvanized L-flashing", 'G-Tape 3035 2"', 'G-Tape 3035 4"', "GRK RSS", "Vycor", '3/8" x 6" HDG lag', "SUL210-2Z"):
        assert any(k in g for g in fin), k
    sin = next(v for k_, v in steps.items() if k_.startswith("Stairs"))["goes_in"]
    assert any("GRK RSS" in g and "box steps" in g for g in sin)            # the box steps' crew day gets its screws


def test_details_name_the_hangers_the_order_buys(t):
    import html, re
    from decktakeoff.drawings import all_sheets
    from decktakeoff.flags import run_flags
    txt = {code: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", svg))) for code, _, svg in all_sheets(t.layout, t, run_flags(t.layout))}   # wrapped labels read as one line
    assert "SUR/SUL210-2Z skewed (45°)" in txt["D-502"]                     # the SUL210-2Z line still reads as the skewed double
    assert "SUR/SUL210-2Z (45°)" in txt["D-504"]
    assert "SUR/SUL210Z: (10) 16d face + (10) 10d x 1-1/2\" joist" in txt["D-504"]       # Simpson's schedules, as the nails are counted
    assert "LSSU210Z, bent: (9) 10d face + (7) 10d x 1-1/2\"" in txt["D-504"] and "skewed hanger, 10d HDG every hole" not in txt["D-504"]


def test_net_order_reasons(t):
    for l in t.lines:
        if l.category in ("Lumber", "Footings", "Hardware", "Flashing & waterproofing"):
            assert l.order >= l.net and (l.order == l.net or l.why.startswith("+")), l
