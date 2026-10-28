"""G1 geometry (Prentice, 28 Oct 2026): every field-board end at a breaker bears a full joist width — the two divider joists
sit bw/2 + gap + jb/2 off the breaker line (on a zone line the zone's picture-frame joist tight inside its rim) and the breaker
rides blocks between them, one more at a breaker end where a divider joist stops short (no end overhangs its framing by over
1"); no joist bay over the spacing where a zone line drops the picture-frame joists; whatever carries a stair tread is at the
tread line's own max spacing (Terrain+ 8"); HardieTrim fascia and risers at their real 3/4"; the lights wired as a run each
side of the outlet; the #12-rated wire connector."""
import copy
import json
import math
from pathlib import Path

import pytest

from decktakeoff import engineering as eng
from decktakeoff import lighting, run
from decktakeoff.layout import build_layout, divider_joist_offset, hardie_thick, outline_framing, zone_divider_framing
from decktakeoff.scene import box_plan_corners, build_scene
from decktakeoff.spec import DeckSpec

ROOT = Path(__file__).parent.parent
PRENTICE = json.loads((ROOT / "jobs" / "prentice_centennial.json").read_text())


def _job(name, folder="jobs"):
    return json.loads((ROOT / folder / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def prentice():
    t, flags, p = run(DeckSpec.from_dict(PRENTICE))
    return t, flags, p, outline_framing(t.layout.spec, t.layout), build_scene(t.layout)


def _bearing(end, toward, ym, joists):
    """The widest joist width under the last 1-3/4" of a board that ends at `end` and runs toward +x (toward=1) or -x (-1),
    at plan y ym. joists: (x0, x1, y0, y1) inches."""
    a, b = (end, end + 1.75) if toward > 0 else (end - 1.75, end)
    return max([min(b, x1) - max(a, x0) for x0, x1, y0, y1 in joists if y0 - 0.01 <= ym <= y1 + 0.01] + [0.0])


def _row_ends(rows, x):
    """(end, toward, row) of every outline-plan field row that ends at the breaker line x."""
    return [(r.x1, -1, r) for r in rows if r.right == "divider" and abs(r.x1 - x) < 4] + \
           [(r.x0, 1, r) for r in rows if r.left == "divider" and abs(r.x0 - x) < 4]


def _scene_joists(S):
    return [(b.x0 * 12, b.x1 * 12, b.y0 * 12, b.y1 * 12) for b in S.boxes if b.kind == "joist" and not b.rot]


def _framing_at(S):
    """(x, y) plan inches -> is a framing member of the 3D model (joist, block, ledger, rim, header, trimmer) under that point."""
    qs = [box_plan_corners(b) for b in S.boxes if b.kind in ("joist", "block", "ledger", "rim", "header", "doubler") and not (b.rot and b.rot_axis in ("x", "y"))]

    def inside(q, x, y):
        c = [(bx - ax) * (y - ay) - (by - ay) * (x - ax) for (ax, ay), (bx, by) in zip(q, q[1:] + q[:1])]
        return all(v >= -1e-9 for v in c) or all(v <= 1e-9 for v in c)
    return lambda x, y: any(inside(q, x / 12, y / 12) for q in qs)


def _levels(name, folder="jobs"):
    t, _, _ = run(DeckSpec.from_dict(_job(name, folder)), with_pricing=False)
    return [q.layout for q in t.layout.parts] if hasattr(t.layout, "parts") else [t.layout]


def _breakers(L):
    """(x, y_lo, y_hi, label) of every breaker, the ends at the board's own ends (the outline plan) or the frame face."""
    if L.plan is not None:
        return list(L.plan.dividers)
    y_front = max(z.wall_y + z.D for z in L.zones)
    return [(x, y_front - Ld, y_front, lab) for x, Ld, lab in L.divider_x]


def _in_poly(poly, x, y):
    c = False
    for (xi, yi), (xj, yj) in zip(poly, poly[-1:] + poly[:-1]):
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
    return c


def _board_end(L, S, lab, x, y, sg):
    """Where a breaker's board really ends at plan x: from its drawn end y inward (sg) past any house (off the deck) and past any
    other border board drawn over it (the breaker butts that board)."""
    poly = [(float(a) * 12, float(b) * 12) for a, b in (L.spec.geometry.outline or [])]
    on_deck = (lambda x_, y_: _in_poly(poly, x_, y_)) if poly else \
        (lambda x_, y_: any(z.x0 <= x_ <= z.x0 + z.W and z.wall_y <= y_ <= z.wall_y + z.D for z in L.zones))
    others = [box_plan_corners(b) for b in S.boxes if b.kind == "border" and b.tag != f"breaker {lab}" and b.tag != lab]

    def under(x_, y_):
        for q in others:
            c = [(bx - ax) * (y_ / 12 - ay) - (by - ay) * (x_ / 12 - ax) for (ax, ay), (bx, by) in zip(q, q[1:] + q[:1])]
            if all(v >= 0 for v in c) or all(v <= 0 for v in c):
                return True
        return False
    for k in range(2400):
        y_ = y + sg * 0.05 * k
        if on_deck(x, y_ + sg * 0.01) and not under(x, y_ + sg * 0.01):
            return y_
    return None


# ------------------------------------------------------------------ 1. breakers: every field-board end on a joist
def test_every_field_board_end_at_a_breaker_bears_a_full_joist(prentice):
    t, _, _, OF, S = prentice
    L = t.layout
    dk = L.zones[0].decking
    d_off = divider_joist_offset(dk, 1.5)
    assert abs(d_off - (dk.bw / 2 + dk.gap + 0.75)) < 1e-9 and abs(d_off - 3.6175) < 1e-3       # 3-5/8" off the line, 7-1/4" apart
    assert [lab for *_, lab in L.plan.dividers] == ["DL/C", "DC/R"]
    for x, lo, hi, lab in L.plan.dividers:
        pair = [(X, a, b) for X, a, b, ea, eb, lab_ in OF.joists if lab_ == f"divider joist {lab}"]
        assert sorted({round(X - x, 4) for X, _, _ in pair}) == [round(-d_off, 4), round(d_off, 4)]
        js = [(X - 0.75, X + 0.75, a, b) for X, a, b in pair]
        ends = _row_ends(L.plan.rows, x)
        assert len(ends) >= 40                                        # both sides of the breaker, every row
        for end, toward, r in ends:
            ya, yb = max(r.y0, max(a for _, _, a, _ in js)), min(r.y1, min(b for _, _, _, b in js))     # (the ledger takes the house row)
            for ym in (ya + 0.1, (ya + yb) / 2, yb - 0.1):              # the board's full width bears
                assert _bearing(end, toward, ym, js) >= 1.5 - 1e-3, (lab, r)
        # the 3D model's own joists carry the same ends
        for end, toward, r in ends:
            assert _bearing(end, toward, (r.y0 + r.y1) / 2, _scene_joists(S)) >= 1.5 - 1e-3, (lab, r)


def test_the_breaker_rides_blocks_between_its_joists(prentice):
    t, _, _, OF, S = prentice
    L = t.layout
    sp = min(L.spec.joist_spacing, 16.0)
    d_off = divider_joist_offset(L.zones[0].decking, 1.5)
    for x, lo, hi, lab in L.plan.dividers:
        blk = sorted((y0, x0 - x, x1 - x) for x0, y0, x1, y1, lab_ in OF.blocks if lab_ == f"divider block {lab}")
        pair = [(X, a, b) for X, a, b, ea, eb, lab_ in OF.joists if lab_ == f"divider joist {lab}"]
        td = L.zones[0].decking.bw / 2 + L.zones[0].decking.gap
        end = min(max(r.y1 for r in L.plan.rows if r.right == "divider" and abs(r.x1 - (x - td)) < 0.1),
                  max(r.y1 for r in L.plan.rows if r.left == "divider" and abs(r.x0 - (x + td)) < 0.1))     # it butts the front border level with the rows
        assert end < hi - 4.0                                                                     # 129-11/16", not the frame face at 134"
        a_c, b_c = max(max(a for _, a, _ in pair), lo), min(min(b for _, _, b in pair), hi, end + 0.75)
        assert len(blk) == 12
        assert abs(blk[0][0] - 0.75 - a_c) < 1e-6 and abs(blk[-1][0] + 0.75 - b_c) < 1e-6      # tight to the ledger; the last one under its end
        assert abs(blk[-1][0] + 0.75 - end - 0.75) < 1e-6                                       # the breaker's end bears 3/4" on it
        assert all(q[0] - p[0] <= sp + 1e-6 for p, q in zip(blk, blk[1:]))                     # at the joist spacing (16" max)
        assert all(abs(x0 + d_off - 0.75) < 1e-6 and abs(x1 - d_off + 0.75) < 1e-6 for _, x0, x1 in blk)   # joist face to joist face
    n_db = sum(1 for *_, lab in OF.blocks if lab.startswith("divider block"))
    n_de = sum(1 for *_, lab in OF.blocks if lab.startswith("divider end block"))
    assert n_db == 24 and n_de == 1
    assert len(OF.blocks) - n_db - n_de == 33              # one per joist bay under the 45s: 32, +1 where the joist added at the zone line splits a bay
    # the 3D model shows the same members
    dj = sorted(round((b.x0 + b.x1) / 2 * 12, 3) for b in S.boxes if b.kind == "joist" and b.tag.startswith("divider joist"))
    assert sorted(round(X, 3) for X, *_, lab in OF.joists if lab.startswith("divider")) == dj
    assert sum(1 for b in S.boxes if b.kind == "block" and b.tag.startswith("divider")) == n_db + n_de
    assert any("24 blocks" in n and "between the divider joists" in n and "1 more at a breaker end" in n for n in t.notes)
    assert any(n.startswith("divider joists: 3 5/8\" each side of the breaker line") for n in t.notes)


def test_a_breaker_end_past_a_divider_joist_gets_its_own_block(prentice):
    """DC/R meets the house at the corner of the bay: its right divider joist dies on the angled bay ledger 5-5/16" out while the
    breaker runs to 2-1/4" — a block at the breaker's end from the left divider joist to the bay ledger, beveled to it."""
    t, _, _, OF, S = prentice
    L = t.layout
    x, lo, hi, _ = next(d for d in L.plan.dividers if d[3] == "DC/R")
    (i, (x0, yc, x1, _, lab)), = [(i, b) for i, b in enumerate(OF.blocks) if b[4].startswith("divider end block")]
    assert lab == "divider end block DC/R" and abs(yc - 0.75 - lo) < 1e-6                     # at the breaker's own end
    right = next(X for X, *_, lab_ in OF.joists if lab_ == "divider joist DC/R" and X > x)
    left = next(X for X, *_, lab_ in OF.joists if lab_ == "divider joist DC/R" and X < x)
    assert abs(x0 - (left + 0.75)) < 1e-6 and x1 < right - 0.75 - 1.0                          # from the left joist; short of the right one
    q = OF.block_quads[i]
    assert q[1][0] < x1 < q[2][0] and abs(q[2][0] - q[1][0] - 1.5 * 22.05 / 20.0) < 0.05     # the far end on the 42-degree bay ledger
    bx = next(b for b in S.boxes if b.kind == "block" and b.tag == lab)
    assert bx.quad and abs(bx.quad[1][0] * 12 - q[1][0]) < 1e-6                              # the 3D draws its true outline


@pytest.mark.parametrize("name, folder", [("prentice_centennial", "jobs"), ("prentice_centennial_irx", "jobs"), ("fillmore_centennial", "jobs"),
                                          ("glengarry_2_fulton_new", "jobs"), ("glengarry_lower", "jobs"), ("jefferson_louisville", "jobs"),
                                          ("eagles_nest", "examples")])
def test_no_breaker_end_overhangs_its_framing_more_than_an_inch(name, folder):
    """TimberTech composite guide p.2: 1" max overhang. Across the breaker's full width, framing within 1" of each of its ends
    (where the board really ends: at the house wall, or butting the border drawn over its end)."""
    n = 0
    for L in _levels(name, folder):
        S = build_scene(L)
        on = _framing_at(S)
        bw = L.zones[0].decking.bw
        for x, lo, hi, lab in _breakers(L):
            for xs in [x - bw / 2 + 0.05 + (bw - 0.1) * k / 8 + 0.013 * (k == 4) for k in range(9)]:      # (off the zone line itself)
                for y_end, sg in ((lo, 1.0), (hi, -1.0)):
                    y_b = _board_end(L, S, lab, xs, y_end, sg)
                    assert y_b is not None and any(on(xs, y_b + sg * d) for d in (0.05, 0.25, 0.5, 0.75, 1.0)), (name, lab, round(xs, 2), y_end, y_b)
            n += 1
    assert n >= 1


@pytest.mark.parametrize("name", ["prentice_centennial", "prentice_centennial_irx", "fillmore_centennial"])
def test_no_joist_bay_over_the_spacing_at_a_zone_line(name):
    """An outline frame drops both zones' picture-frame joists at a zone line (no border there): Prentice's bay at 144" was
    13-5/16" on a 12" OC deck (15-7/16" before the divider joists moved), Fillmore's lower level 18-1/16" over 16" Vintage
    spans, and its zone B's last bay 13-3/4" — a field joist goes in evenly between. (An inset stair's trimmers count as framing.)"""
    for L in _levels(name):
        OF = outline_framing(L.spec, L)
        xs = sorted({round(X, 3) for X, *_ in OF.joists} | {round(tr[0], 3) for nt in OF.notches for tr in nt.get("trimmer", [])})
        assert max(b - a for a, b in zip(xs, xs[1:])) <= L.spec.joist_spacing + 1e-6, (name, xs)
    if name == "prentice_centennial":
        OF = outline_framing(L.spec, L)
        assert any(abs(X - 150.666) < 0.01 and lab == "joist" for X, *_, lab in OF.joists)       # midway between 144" and 157-5/16"
        assert any("1 field joist added where a bay ran over 12\"" in n for n in OF.notes)


def test_a_zone_line_breaker_takes_the_picture_frame_joist():
    """Zone framing: at a breaker's zone line the zone's picture-frame joist moves tight inside its rim and the field-board ends
    bear on it (no rail post in its 1-1/2" gap there) — no joist stacked against it; a field joist goes in only where the move opens
    the bay past the spacing (Glengarry zone W: 72" to 84-1/4", one at 78-1/8"). The 3D draws exactly these joists."""
    L = build_layout(DeckSpec.from_dict(_job("glengarry_2_fulton_new")))
    S = build_scene(L)
    for zi, z in enumerate(L.zones):
        js, blk, prs = zone_divider_framing(L, zi)
        assert not blk and not prs                                            # zone lines only: the breakers ride the rims
        xs = [X for X, _ in js]
        assert all(b - a > 1.5 + 1e-6 for a, b in zip(xs, xs[1:]))                 # nothing stacked
        assert all(b - a <= L.spec.joist_spacing + 1e-6 for a, b in zip(xs, xs[1:]))
        for dx, _, lab in L.divider_x:
            if abs(dx - z.x0) < 0.6 or abs(dx - z.x0 - z.W) < 0.6:
                assert sum(1 for X, l in js if l == f"divider joist {lab}" and abs(abs(X - dx) - 3.75) < 1e-6) == 1
                assert not any(l == "PF joist" and abs(X - dx) < 8 for X, l in js)
        n_extra = len(js) - len(z.frame.joist_x) - len(z.frame.pf_x)
        assert n_extra == (1 if z.name == "W" else 0), (z.name, n_extra)
    allj = [X for zi in range(len(L.zones)) for X, _ in zone_divider_framing(L, zi)[0]]
    for dx, _, lab in L.divider_x:
        in3d = sorted({round((b.x0 + b.x1) / 2 * 12, 2) for b in S.boxes if b.kind == "joist" and abs((b.x0 + b.x1) / 2 * 12 - dx) < 14})
        assert in3d == sorted({round(X, 2) for X in allj if abs(X - dx) < 14}), (lab, in3d)


@pytest.mark.parametrize("name", ["prentice_centennial", "fillmore_centennial"])
def test_no_joist_under_a_breaker_or_overlapping_a_divider_joist(name):
    t, _, _ = run(DeckSpec.from_dict(_job(name)), with_pricing=False)
    parts = [q.layout for q in t.layout.parts] if hasattr(t.layout, "parts") else [t.layout]
    for L in parts:
        OF = outline_framing(L.spec, L)
        d_off = divider_joist_offset(L.zones[0].decking, 1.5)
        for dx, _, lab in L.divider_x:
            for X, a, b, ea, eb, lab_ in OF.joists:
                if not lab_.startswith("divider"):
                    assert abs(X - dx) >= d_off + 1.5 - 1e-6, (name, lab, X, lab_)       # outside the pair, at most touching it
        js = sorted(OF.joists)
        for i, p in enumerate(js):
            for q in js[i + 1:]:
                assert not (abs(p[0] - q[0]) < 1.5 - 1e-6 and min(p[2], q[2]) - max(p[1], q[1]) > 0.5), (name, p, q)


def test_zone_framed_breakers_bear_on_a_joist_inside_each_rim():
    """Glengarry is framed zone by zone: on a zone line the divider joist sits tight inside each zone's own rim (the breaker
    rides the two rims), no joist inside a rim ply, every field-board end over the zones' framing bears."""
    sp = DeckSpec.from_dict(_job("glengarry_2_fulton_new"))
    L = build_layout(sp)
    assert outline_framing(sp, L) is None and L.divider_x
    S = build_scene(L)
    rims = [b for b in S.boxes if b.kind == "rim" and b.tag == "side rim"]
    js = _scene_joists(S)
    for x, lo, hi, lab in L.plan.dividers:
        dv = sorted(round((b.x0 + b.x1) / 2 * 12 - x, 3) for b in S.boxes if b.kind == "joist" and b.tag.startswith("divider joist") and abs((b.x0 + b.x1) / 2 * 12 - x) < 6)
        assert dv == [-3.75, 3.75], (lab, dv)                                 # 2-ply rim 3" + half a joist
        for b in S.boxes:
            if b.kind == "joist" and abs((b.x0 + b.x1) / 2 * 12 - x) < 8:
                assert not any(r.x0 + 1e-6 < (b.x0 + b.x1) / 2 < r.x1 - 1e-6 and min(r.y1, b.y1) - max(r.y0, b.y0) > 0.1 for r in rims)
        n = 0
        for end, toward, r in _row_ends(L.plan.rows, x):
            zs = [z for z in L.zones if z.x0 - 0.6 <= end <= z.x0 + z.W + 0.6 and z.wall_y + 1.5 <= r.y0 and r.y1 <= z.wall_y + z.D]
            if zs:                                                            # (rows in the bay pocket left of DW/M have no zone frame)
                n += 1
                assert _bearing(end, toward, (r.y0 + r.y1) / 2, js) >= 1.5 - 1e-3, (lab, r)
        assert n >= 30


def test_a_breaker_inside_a_zone_rides_blocks():
    """Eagle's Nest (4x10 timber frame, zone decking): the breaker inside zone A gets a 4x joist each side (its inside face under
    the board ends: 2-11/16 + 3/16 + 1-3/4 = 4-5/8" off the line), the field joist on the line goes, 4x blocks between at 12"."""
    sp = DeckSpec.from_dict(_job("eagles_nest", "examples"))
    L = build_layout(sp)
    S = build_scene(L)
    dx = next(x for x, _, lab in L.divider_x if lab == "DA1")
    near = sorted(round((b.x0 + b.x1) / 2 * 12 - dx, 3) for b in S.boxes if b.kind == "joist" and abs((b.x0 + b.x1) / 2 * 12 - dx) < 8)
    assert sorted(set(near)) == [-4.625, 4.625]
    blk = sorted(b.y0 * 12 for b in S.boxes if b.kind == "block" and b.tag == "divider block DA1")
    assert len(blk) >= 6 and all(q - p <= min(L.spec.joist_spacing, 16.0) + 1e-6 for p, q in zip(blk, blk[1:]))
    js = _scene_joists(S)
    za = next(z for z in L.zones if z.name == "A")
    ends = [(b.x1 * 12, -1, b) for b in S.boxes if b.kind == "board" and abs(b.x1 * 12 - dx) < 4] + \
           [(b.x0 * 12, 1, b) for b in S.boxes if b.kind == "board" and abs(b.x0 * 12 - dx) < 4]
    ends = [(e, s, b) for e, s, b in ends if b.y0 * 12 >= za.wall_y + 1.5]     # (not the rows over the ledger)
    assert len(ends) >= 20
    for end, toward, b in ends:
        assert _bearing(end, toward, (b.y0 + b.y1) * 6, js) >= 1.5 - 1e-3


# ------------------------------------------------------------------ 2. stair treads carried at the tread line's own max
def test_tread_support_spacing_by_tread_line():
    assert eng.tread_support_oc("Terrain+")[0] == eng.tread_support_oc("Terrain")[0] == 8.0           # CCRR-0128 Table 1
    assert "CCRR-0128" in eng.tread_support_oc("Terrain+")[1]
    for c in ("Legacy", "Reserve", "Prime", "Prime+", "Premier", "Premier+"):
        assert eng.tread_support_oc(c)[0] == 9.0                                                      # TimberTech FAQ / guide p.8
    for c in ("Legacy", "Reserve", "Prime", "Prime+"):                     # 9" only on the FAQ's word (the guide chart says 10"): cite it
        assert "timbertech.com/resources/faqs" in eng.tread_support_oc(c)[1] and "10\"" in eng.tread_support_oc(c)[1]
    for c in ("Vintage", "Landmark", "Harvest", "Harvest+"):
        assert eng.tread_support_oc(c)[0] == 10.0                                                     # CCRR-0101 / PVC guide p.17
    assert eng.tread_support_oc("Cedar", wood=True)[0] == 16.0
    assert eng.tread_support_oc("unknown line")[0] == eng.STRINGER_OC_COMPOSITE == 10.0
    assert all(v[0] <= eng.STRINGER_OC_COMPOSITE for v in eng.TREAD_SPAN_MAX.values())
    g = eng.stair_geometry(21, 67, True, 11.375, stringer_oc=8.0)
    assert g.stringers == 10 and 67 / (g.stringers - 1) <= 8.0


def test_prentice_stairs_and_box_steps_at_8_inches(prentice):
    t, flags, _, _, S = prentice
    st = {s.side: s for s in t.layout.stairs}
    cs = st["edge:6"]
    assert cs.stringers == 10 and cs.support_oc == 8.0 and (cs.width - 1.5) / (cs.stringers - 1) <= 8.0
    assert sum(1 for b in S.boxes if b.kind == "stringer" and b.tag == "stringer edge:6") == 10
    for side, w, n in (("edge:2", 73, 11), ("edge:3", 68, 10)):
        bx = st[side]
        assert bx.build == "box" and bx.width == w and bx.cross_members == n and (w - 1.5) / (n - 1) <= 8.0 and bx.stringers == 0
        assert sum(1 for b in S.boxes if b.kind == "joist" and b.tag == f"box step frame {side}") == n * bx.geo.treads
        assert any(f"{n} cross members a box" in x and "8\" max under Terrain+ treads" in x for x in bx.notes)
    lsc = next(l for l in t.lines if "LSCZ" in l.item)
    assert lsc.net == 10                                                       # one stringer connector per stringer
    txt = " ".join(f.text for f in flags)
    assert "@ 12\" OC (composite treads)" not in txt and "stringers 10 @ 7\" OC (8\" max under Terrain+ treads" in txt
    assert "11 cross members a box @ 7 1/8\" OC" in txt and "10 cross members a box @ 7 3/8\" OC" in txt


def _takeoff_has(fn, marker):
    import inspect
    from decktakeoff import takeoff as tk
    return marker in inspect.getsource(getattr(tk, fn))


@pytest.mark.skipif(not _takeoff_has("_rims_from_outline", "divider end block"), reason="takeoff.py follow-up (r3/takeoff_followup.patch) not landed")
def test_the_order_counts_what_the_frame_draws(prentice):
    """With the takeoff follow-up: the cut list, schedule and order carry the breaker blocks, the box steps' cross members, the
    tread line's stringer max and the box-step treads' Cortex at their real supports."""
    t, _, _, OF, _ = prentice
    cut = {c.member: c for c in t.cut_list}
    assert cut["Blocks under the 45-degree borders"].qty == 33 and "bevel" in cut["Blocks under the 45-degree borders"].note
    assert cut["Breaker blocks between the divider joists"].qty == 24 and abs(cut["Breaker blocks between the divider joists"].length_in - 5.735) < 0.01
    assert cut["Breaker end block"].qty == 1 and "beveled" in cut["Breaker end block"].note
    assert t.schedule["Blocking"].startswith("33 x 2x10 blocks under the 45-degree picture-frame borders + 25 under the breakers")
    cm2, cm3 = cut["Box step cross members (Left box step — left side)"], cut["Box step cross members (Left box step — front angle)"]
    assert cm2.qty == 11 and "@ 7 1/8\" OC (8\" max)" in cm2.note and "11 cross members" in cut["Box step frame (Left box step — left side)"].note
    assert cm3.qty == 10 and "@ 7 3/8\" OC (8\" max)" in cm3.note and "10 cross members" in cut["Box step frame (Left box step — front angle)"].note
    assert "(max 8\")" in cut["Stair stringers (Center stair)"].note and cut["Stair stringers (Center stair)"].qty == 10
    assert "stairs 164" in next(l for l in t.lines if l.item.startswith("Cortex")).why    # treads only: HardieTrim risers take finish nails (G2a); 2 per support per board
    t2, _, _ = run(DeckSpec.from_dict(_job("fillmore_centennial")), with_pricing=False)
    assert all(v.split(": ", 1)[-1].startswith("22 x 2x10 blocks under the breakers") for v in t2.schedule["Blocking"].split("  ||  "))
    import re
    assert not re.search(r"(^|\s|: )0 x ", t2.schedule["Blocking"])                    # (the build set drops a "0 x" line)


@pytest.mark.skipif(not _takeoff_has("accumulate", "zone_divider_framing"), reason="owner decision: r3/takeoff_zone_dividers.patch not landed")
@pytest.mark.parametrize("name, folder", [("glengarry_2_fulton_new", "jobs"), ("eagles_nest", "examples")])
def test_a_zone_framed_order_counts_the_joists_the_3d_draws(name, folder):
    t, _, _ = run(DeckSpec.from_dict(_job(name, folder)), with_pricing=False)
    L = t.layout
    n3d = sum(len(zone_divider_framing(L, zi)[0]) for zi in range(len(L.zones)))
    assert int(t.summary["joists"].split()[0]) == n3d                                        # the joists the 3D draws, no doubler on top
    members = [c.member for c in t.cut_list]
    assert not any(m.startswith("Divider doublers") for m in members) and any(m.startswith("Divider joists") for m in members)
    blk = sum(len(zone_divider_framing(L, zi)[1]) for zi in range(len(L.zones)))
    assert sum(c.qty for c in t.cut_list if c.member.startswith("Breaker blocks")) == blk


@pytest.mark.parametrize("name, side, n, oc", [("deck_16x14_seasalt", "front", 8, 9.0), ("deck_20x20_castlerock", "right", 6, 10.0)])
def test_other_tread_lines_use_their_own_max(name, side, n, oc):
    t, flags, _ = run(DeckSpec.from_dict(_job(name)), with_pricing=False)          # Prime+ 9" / Vintage 10"
    st = next(s for s in t.layout.stairs if s.side == side)
    assert st.support_oc == oc and st.stringers == n and st.width / (n - 1) <= oc and st.width / (n - 2) > oc


# ------------------------------------------------------------------ 3. HardieTrim at its real thickness
def test_hardie_fascia_and_risers_are_three_quarter_inch(prentice):
    t, _, _, _, S = prentice
    assert hardie_thick(t.layout.spec) == 0.75
    assert all(z.decking.fascia_t == 0.75 for z in t.layout.zones)
    fas = [b for b in S.boxes if b.kind == "fascia" and b.tag.startswith("fascia side")]
    assert fas and all(abs((b.y1 - b.y0) * 12 - 0.75) < 1e-6 for b in fas)          # rot_box: the local y extent is the board's thickness
    for side, n in (("edge:6", 3), ("edge:2", 2)):
        rs = [b for b in S.boxes if b.kind == "riser" and b.tag.endswith(side)]
        assert len(rs) == n and all(abs(min(b.x1 - b.x0, b.y1 - b.y0) * 12 - 0.75) < 1e-6 for b in rs)
    sk = [b for b in S.boxes if b.kind == "fascia" and b.tag == "stair skirt edge:6"]
    assert sk and all(abs(min(b.x1 - b.x0, b.y1 - b.y0) * 12 - 0.75) < 1e-6 for b in sk)
    t2, _, _ = run(DeckSpec.from_dict(_job("prentice_centennial_irx")), with_pricing=False)   # the composite-fascia alternate keeps 0.58"
    assert hardie_thick(t2.layout.spec) is None and t2.layout.decking.fascia_t == 0.58
    d = copy.deepcopy(PRENTICE)
    d["extras"]["hardie_skirt"] = "5/4 x 12 Arctic White"
    assert hardie_thick(DeckSpec.from_dict(d)) == 1.0
    d["decking"]["fascia"] = False
    assert hardie_thick(DeckSpec.from_dict(d)) is None


def test_hardie_shrinks_a_nominal_frame_to_stay_inside_the_size():
    d = _job("deck_10x10")
    assert d["extras"].get("hardie_skirt") and d["geometry"].get("size_mode") == "nominal"
    L1 = build_layout(DeckSpec.from_dict(d))
    d2 = copy.deepcopy(d); d2["extras"]["hardie_skirt"] = None
    L2 = build_layout(DeckSpec.from_dict(d2))
    assert L1.decking.fascia_t == 0.75 and L2.decking.fascia_t == 0.5
    assert L1.decking.deck_w <= 96.0 and L1.decking.deck_d <= 96.0                 # still 8' x 8' max over the fascia
    assert L1.finished_w < L2.finished_w                                           # the frame gives the room back


@pytest.mark.parametrize("name", ["summit_point_deck", "parkview_deck", "prentice_centennial", "glengarry_2_fulton_new"])
def test_zone_rows_never_overfill(name):
    """A zone framed at its drawn depth gets no row its gaps can't make room for (1/32" a gap at most) — Summit's zone W at the
    3/4" Hardie fascia is 62 rows and a rip at the house, not 63 rows 2-3/4" too deep."""
    L = build_layout(DeckSpec.from_dict(_job(name)))
    for z in L.zones:
        dk = z.decking
        assert dk.last_row_dev <= max(0.5, dk.rows / 32.0) + 1e-9, (name, z.name, dk.rows, dk.last_row_dev)
    if name == "summit_point_deck":
        w = next(z for z in L.zones if z.name == "W").decking
        assert w.rows == 62 and -w.last_row_dev - w.gap > 2.5                       # a 2-3/4" rip at the house


# ------------------------------------------------------------------ 4. lighting: a run each side of the outlet
def test_prentice_lighting_splits_at_the_outlet(prentice):
    t, _, _, _, _ = prentice
    pl = t.lighting
    assert len(pl.runs) == 2
    assert [round(r.watts) for r in pl.runs] == [30, 16]                      # right: center stair + posts to the bay; left
    assert all(r.watts <= pl.cfg["run_max_w"] + 1e-6 for r in pl.runs)
    assert max(r.drop_v for r in pl.runs) < 0.6
    ox = pl.outlet[0]
    for r in pl.runs:                                                          # each run stays on its own side of the outlet
        assert len({n.x < ox for n in r.nodes}) == 1
    assert any(n.what.startswith("stair: Center stair") for n in pl.runs[0].nodes)
    assert any(n.what.startswith("stair: Left box step") for n in pl.runs[1].nodes)
    assert 190 <= pl.wire_lf <= 210
    tr = [lighting.product(pl.cfg, s) for s in pl.transformers]
    assert pl.transformers == ["AZTDL100TRAN"] and sum(p["watts_max"] for p in tr) == 90.0
    assert pl.load_w <= sum(p["watts_max"] for p in tr) and pl.load_w * pl.cfg["headroom"] <= sum(p["watts"] for p in tr)
    assert not any("V drop" in n for n in t.notes)


def test_one_side_of_the_outlet_stays_one_chain():
    d = copy.deepcopy(PRENTICE)
    d["extras"]["lights"]["transformer_at"] = [0.0, 0.0]                     # the outlet at the left end: every light on one side
    t, _, _ = run(DeckSpec.from_dict(d), with_pricing=False)
    assert len(t.lighting.runs) == 1 and round(t.lighting.runs[0].watts) == 46


def test_wire_connector_is_rated_for_12_awg(prentice):
    t, _, _, _, _ = prentice
    p = lighting.PRODUCTS["DRYCONN62225"]
    assert p["count"] == 20 and "62225" in p["desc"] and "#12" in p["desc"] and "UL 486D" in p["desc"] and 10 < p["each"] < 30
    assert p["source"].startswith("EST")
    assert lighting.DEFAULTS["connector_sku"] == "DRYCONN62225"
    ln = next(l for l in t.lines if l.category == "Lighting" and l.sku == "DRYCONN62225")
    need = int(math.ceil(2 * t.lighting.splices * 1.1))
    assert ln.order == int(math.ceil(need / 20)) and f"{need} needed" in ln.why
