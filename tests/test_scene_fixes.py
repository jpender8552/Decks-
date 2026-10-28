"""Scene fixes from the code review (decktakeoff/scene.py), each on the job it was found on:
A1. a box step between two others is mitered at both ends: Prentice (jobs/prentice_centennial.json) plus a 68" box step on the
    front-left angle (edge:1), so the 73" left-side step (edge:2) meets a neighbor at both of its corners. The second miter used
    to read the first one's outline as the box and square that end off again (the tread ran square to 6.523' and into the
    edge:3 step);
A2. a miter cuts only the pieces that run along the side: the box frame's cross members and a stair rail's posts and balusters
    stay square at the corner (the end cross member came out a 2.5"-5.6" wedge on Prentice, on S-101 and the framing
    isometrics); at an inside corner (box steps on Prentice's edge:5 and edge:6), where they would stand in the other step, the
    cross member is set back inside its own step and the rail's pieces go, instead of coming out reversed. A stair rail on the
    angled side at an outside corner stays whole (its pitched top rail, measured by its unturned box, once went and left its
    posts); at a deep inside corner (two and three treads around the 90-degree corner of Jefferson's L) each tier keeps one
    cross member at the miter instead of a stack of them on one spot; a stair rail that reaches over the miter line goes as
    a whole;
A3. an option stair's guard across its opening stands on the deck rail's post line on a vertical outline side too, where the
    stair starts outside the fascia (Fillmore's yard stair, jobs/fillmore_centennial_yardstair.json, moved onto the lower
    level's edge:1; an option stair off Prentice's edge:10);
A4. a job's color typed in British spelling ("Grey", "Steel Grey") draws the gray it names: rail, roof, sail, Hardie, styling
    furniture, decking; and the color tables keep one American key each."""
import ast
import copy
import inspect
import json
import math
import textwrap
from collections import Counter
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace

import pytest

from decktakeoff import run
from decktakeoff import scene as scene_mod
from decktakeoff.catalog import BOARDS_PALETTE
from decktakeoff.layout import RAIL_POST_INSET
from decktakeoff.scene import (FURN_DEFAULT_COLOR, FURN_HEX, HARDIE_HEX, SAIL_COLORS, Box, box_plan_corners, box_step_miters, build_scene,
                               furniture_boxes, furniture_levels, furniture_materials, materials_for, outline_side_frames)
from decktakeoff.spec import DeckSpec

from test_box_step_miter import JOB, _build, _kept, _local, _overlap, _poly, _skirt

ROOT = Path(__file__).resolve().parent.parent
FILLMORE = json.loads((ROOT / "jobs" / "fillmore_centennial_yardstair.json").read_text())
RP = RAIL_POST_INSET / 12                  # ft: the deck rail's posts stand this far in from the frame line
EDGE_STEP = JOB["stairs"][2]               # Prentice's 68" box step on the front angle: the model for the test steps


def _job(name):
    return json.loads((ROOT / "jobs" / f"{name}.json").read_text())


def _three_steps():
    """Prentice plus a 68" box step on edge:1 from its start: the edge:2 step now has a box step at each of its corners."""
    job = copy.deepcopy(JOB)
    job["stairs"].append(dict(copy.deepcopy(EDGE_STEP), side="edge:1", width_in=68, position_in=0, name="Test box step — front-left angle"))
    return job


def _inside_corner():
    """Prentice with box steps at an inside corner, in place of the center stair: a 54" one along the whole of edge:5 (the angle
    into the center notch), with a stair rail on both sides, and a 60" one on edge:6 from that corner."""
    job = copy.deepcopy(JOB)
    assert job["stairs"][0]["side"] == "edge:6"
    job["stairs"][0].update(position_in=0, width_in=60, build="box", total_rise_in=12.4, name="Test box step — notch")
    job["stairs"].append(dict(copy.deepcopy(EDGE_STEP), side="edge:5", width_in=54, position_in=0, rails=2, name="Test box step — notch angle"))
    return job


@pytest.fixture(scope="module")
def prentice():
    return _build(JOB)


@pytest.fixture(scope="module")
def three():
    return _build(_three_steps())


@pytest.fixture(scope="module")
def inside():
    return _build(_inside_corner())


@pytest.fixture(scope="module")
def railed():
    job = copy.deepcopy(JOB)
    assert job["stairs"][1]["side"] == "edge:2"
    job["stairs"][1]["rails"] = 2          # a stair rail on both sides of the left-side box step: one of them at the mitered corner
    return _build(job)


# ------------------------------------------------------------------ helpers (plan feet)
def _frames(P):
    return outline_side_frames(_poly(P.spec))


def _miter(fa, fb):
    """The corner where side a ends and side b starts: k, how far its miter line (the bisector of the two outward normals) runs
    along side a per foot out from it — + at an outside corner, - at an inside one; along side b it runs -k."""
    (_, tA, nA, _), (_, _, nB, _) = fa, fb
    m = (nA[0] + nB[0], nA[1] + nB[1])
    return (m[0] * tA[0] + m[1] * tA[1]) / (m[0] * nA[0] + m[1] * nA[1])


def _ends(frame, quad):
    """A cut piece's outline in its side's frame: for each of its two edges along the side (u out from it, nearer one first), the
    v where the edge starts and where it ends."""
    rows = {}
    for v, u in _local(frame, quad):
        rows.setdefault(round(u, 6), []).append(v)
    assert len(rows) == 2 and all(len(vs) == 2 for vs in rows.values()), rows
    return [(u, min(vs), max(vs)) for u, vs in sorted(rows.items())]


def _convex(q):
    """Plan points that run around a convex outline one way (not a bow tie, not folded over)."""
    n = len(q)
    cr = [(q[(i + 1) % n][0] - q[i][0]) * (q[(i + 2) % n][1] - q[(i + 1) % n][1]) - (q[(i + 1) % n][1] - q[i][1]) * (q[(i + 2) % n][0] - q[(i + 1) % n][0])
          for i in range(n)]
    return all(c > 1e-9 for c in cr) or all(c < -1e-9 for c in cr)


def _square(b):
    return box_plan_corners(b, miter=False)


def _mine(P, side, boxes):
    return [b for b in boxes if any(b is q for q in P.steps[side])]


def _v(frame, b):
    return [v for v, _ in _local(frame, box_plan_corners(b))]


ALONG = {"tread", "riser", "rim", "stepbase"}      # what runs along the side to the corner: cut on the miter
ACROSS = {"joist", "railpost", "baluster", "toprail", "cable"}    # the frame's cross members, a stair rail's pieces: never cut


# ------------------------------------------------------------------ A1: a step mitered at both ends
def test_middle_step_is_mitered_at_both_ends(three):
    f1, f2, f3 = _frames(three)[:3]
    k12, k23 = _miter(f1, f2), _miter(f2, f3)
    assert k12 == pytest.approx(0.4093, abs=1e-3) and k23 == pytest.approx(0.4093, abs=1e-3)      # two outside corners
    m = box_step_miters(three.spec, three.L.stairs)
    assert m["edge:2"] == (2, pytest.approx(k23)) and m["edge:1"][0] == m["edge:3"][0] == 1
    cut = [b for b in _kept(three, "edge:2") if b.quad]
    assert Counter(b.kind for b in cut) == Counter(tread=1, riser=2, rim=2, stepbase=1)
    for b in cut:                          # each end on its own corner's miter line, at both edges along the side
        for u, v_start, v_end in _ends(f2, b.quad):
            assert v_start == pytest.approx(-k12 * u, abs=1e-6), b.tag
            assert v_end == pytest.approx(f2[3] + k23 * u, abs=1e-6), b.tag
    (tread,) = [b for b in cut if b.kind == "tread"]
    # the end runs out on the miter, and so does the start (the steps sit off the real 3/4" HardieTrim fascia: 0.17" x k further out than at 0.58")
    assert [round(v_end, 3) for _, _, v_end in _ends(f2, tread.quad)] == [6.125, 6.529]
    assert [round(v_start, 3) for _, v_start, _ in _ends(f2, tread.quad)] == [-0.042, -0.446]


def test_the_three_steps_meet_without_overlapping(three):
    for a, b in (("edge:1", "edge:2"), ("edge:2", "edge:3")):
        A, B_ = _kept(three, a), _kept(three, b)
        worst = max((_overlap(box_plan_corners(p), box_plan_corners(q)), p.tag, q.tag) for p in A for q in B_)
        assert worst[0] < 1e-4, worst                                                   # sq ft
        assert max(_overlap(_square(p), _square(q)) for p in A for q in B_ if p.kind == q.kind == "tread") > 0.005   # uncut, they do
    skirts = Counter(b.tag.split()[-1] for b in three.dropped if _skirt(b))
    assert skirts == Counter({"edge:1": 1, "edge:2": 2, "edge:3": 1}) and len(three.dropped) == 4     # a miter has no exposed end
    assert not [b for b in _kept(three, "edge:2") if _skirt(b)]


def test_the_double_miter_does_not_depend_on_which_corner_is_cut_first(three):
    job = _three_steps()
    job["stairs"].insert(1, job["stairs"].pop())          # the edge:1 step listed first: its corner is cut before the edge:2 / edge:3 one
    other = _build(job)
    quads = lambda P: sorted((b.kind, b.tag, [[round(v, 9) for v in p] for p in b.quad]) for b in P.sc.boxes
                             if b.quad and not b.tag.startswith(("pf ", "divider end block")))       # the steps' pieces (not the frame's beveled blocks)
    assert quads(other) == quads(three) and len(quads(three)) == 18


# ------------------------------------------------------------------ A2: only what runs along the side is cut
def test_cross_members_at_the_corner_stay_square(prentice):
    drawn = {id(b) for b in prentice.sc.boxes}
    for side in ("edge:2", "edge:3"):
        f = _frames(prentice)[int(side.split(":")[1]) - 1]
        st = next(s for s in prentice.L.stairs if s.side == side)
        cross = [b for b in _kept(prentice, side) if b.kind == "joist" and "box step frame" in b.tag]
        assert len(cross) == st.cross_members and all(id(b) in drawn for b in cross), side      # the layout's count (the tread line's max spacing)
        assert not [b.tag for b in cross if b.quad], side                               # never a wedge
        for b in cross:
            vs = _v(f, b)
            assert (max(vs) - min(vs)) * 12 == pytest.approx(1.5, abs=1e-6), side     # a 1 1/2" member
            assert -1e-6 < min(vs) and max(vs) < (st.opening.start_in + st.width) / 12 + 1e-6, side    # inside its own step (an outside corner)
        spans = sorted((min(_v(f, b)), max(_v(f, b))) for b in cross)
        assert spans[0][0] == pytest.approx(0, abs=1e-6) and spans[-1][1] == pytest.approx(st.width / 12, abs=1e-6), side   # one at each end
        assert all(b.quad for b in _kept(prentice, side) if b.kind in ALONG), side      # what runs along the side is still cut


def test_stair_rail_posts_and_balusters_at_the_corner_stay_square(railed):
    f = _frames(railed)[1]
    rail = [b for b in railed.steps["edge:2"] if b.kind in ACROSS - {"joist"}]
    assert {"railpost", "baluster", "toprail"} <= {b.kind for b in rail}
    gone = {id(b) for b in railed.dropped}
    assert not [b.tag for b in rail if b.quad or id(b) in gone]
    at_corner = [b for b in rail if max(_v(f, b)) > f[3] - 0.5]
    assert len([b for b in at_corner if b.kind == "railpost"]) == 2 and all(max(_v(f, b)) < f[3] for b in at_corner)


def test_an_inside_corner_sets_back_or_drops_what_crosses_the_miter_and_cuts_the_rest_short(inside):
    f5, f6 = _frames(inside)[4:6]
    k = _miter(f5, f6)
    assert k == pytest.approx(-0.382, abs=1e-3)                                      # an inside corner: the miter runs back along both sides
    m = box_step_miters(inside.spec, inside.L.stairs)
    assert m["edge:5"] == m["edge:6"] == (1, pytest.approx(-k))
    # gone: the end skirts at the corner, and the stair rail on edge:5's corner side (the step runs on around the corner there)
    gone5, gone6 = _mine(inside, "edge:5", inside.dropped), _mine(inside, "edge:6", inside.dropped)
    assert Counter(b.kind for b in gone5) == Counter(fascia=1, railpost=2, baluster=2, toprail=1) and Counter(b.kind for b in gone6) == Counter(fascia=1)
    assert all(min(_v(f5, b)) > f5[3] - 0.5 for b in gone5)
    rail_left = [b for b in _kept(inside, "edge:5") if b.kind in ACROSS - {"joist"}]
    assert len([b for b in rail_left if b.kind == "railpost"]) == 2 and all(max(_v(f5, b)) < 0.5 for b in rail_left)    # the free side's rail stays
    # each frame keeps all its cross members, square; the one at the corner is set back inside its own step, its outer face on the miter
    for side, f, at_end in (("edge:5", f5, True), ("edge:6", f6, False)):
        st = next(s for s in inside.L.stairs if s.side == side)
        cross = sorted((b for b in _kept(inside, side) if b.kind == "joist"), key=lambda b: min(_v(f, b)))
        assert len(cross) == st.cross_members and not [b.tag for b in cross if b.quad], side
        loc = _local(f, box_plan_corners(cross[-1] if at_end else cross[0]))
        vs, u_out = [v for v, _ in loc], max(u for _, u in loc)
        assert (max(vs) - min(vs)) * 12 == pytest.approx(1.5, abs=1e-6), side
        assert (max(vs) if at_end else min(vs)) == pytest.approx((f[3] + k * u_out) if at_end else -k * u_out, abs=1e-6), side
    A, B_ = _kept(inside, "edge:5"), _kept(inside, "edge:6")
    for b in A:
        assert all(v <= f5[3] + k * u + 0.01 for v, u in _local(f5, box_plan_corners(b))), b.tag
    for b in B_:
        assert all(v >= -k * u - 0.01 for v, u in _local(f6, box_plan_corners(b))), b.tag
    for b in A + B_:
        assert (b.kind in ALONG) == bool(b.quad), b.tag                                 # cut only along the side, never reversed
        assert not b.quad or _convex(b.quad), b.tag
    worst = max((_overlap(box_plan_corners(p), box_plan_corners(q)), p.tag, q.tag) for p in A for q in B_)
    assert worst[0] < 1e-4, worst
    assert max(_overlap(_square(p), _square(q)) for p in A for q in B_ if p.kind == q.kind == "tread") > 0.005
    (t5,) = [b for b in A if b.kind == "tread"]
    for u, _, v_end in _ends(f5, t5.quad):
        assert v_end == pytest.approx(f5[3] + k * u, abs=1e-6)                          # shorter the farther out from the deck


def _angled_rails(total_rise_in=None):
    """Prentice with a stair rail on both sides of the 68" box step off the front angle (edge:3), one of them at its mitered
    corner with the left-side step (an outside corner); total_rise_in (both steps): a step of two treads."""
    job = copy.deepcopy(JOB)
    assert job["stairs"][1]["side"] == "edge:2" and job["stairs"][2]["side"] == "edge:3"
    job["stairs"][2]["rails"] = 2
    if total_rise_in:
        job["stairs"][1]["total_rise_in"] = job["stairs"][2]["total_rise_in"] = total_rise_in
    return job


@pytest.mark.parametrize("total_rise_in, treads", [(None, 1), (21, 2)])
def test_a_stair_rail_on_the_angled_side_stays_whole_at_an_outside_corner(total_rise_in, treads):
    P = _build(_angled_rails(total_rise_in))
    f2, f3 = _frames(P)[1:3]
    k = _miter(f2, f3)
    assert k > 0 and box_step_miters(P.spec, P.L.stairs)["edge:3"] == (1, pytest.approx(k))      # an outside corner
    assert next(s for s in P.L.stairs if s.side == "edge:3").geo.treads == treads
    rail = [b for b in P.steps["edge:3"] if b.kind in ACROSS - {"joist"}]
    assert Counter(b.kind for b in rail) == Counter(railpost=4, toprail=2, baluster=4 * treads)    # both sides, the corner's too
    drawn = {id(b) for b in P.sc.boxes}
    assert all(id(b) in drawn for b in rail) and not [b.tag for b in rail if b.quad]            # all of it drawn, all square
    assert len(P.dropped) == 2 * treads and all(_skirt(b) for b in P.dropped)                   # only the end skirts at the corner go
    width = next(s for s in P.L.stairs if s.side == "edge:3").width / 12
    for b in rail:     # measured by its center, each piece is its own cross-section across the side, inside its own step
        v0, v1, _, _ = scene_mod._side_span(b, f3, turned=True)
        assert v1 - v0 == pytest.approx(b.x1 - b.x0, abs=1e-9) and 0 < v0 and v1 < width, b.kind
    # the corner side's top rail, by the bounds of its unturned box, reaches over the miter line: what once dropped it
    (corner,) = [b for b in rail if b.kind == "toprail" and scene_mod._side_span(b, f3, turned=True)[0] < width / 2]
    loc = _local(f3, box_plan_corners(corner))
    assert min(v for v, _ in loc) < max(-k * u for _, u in loc)


JEFFERSON_L = [[0, 0], [0, 3.667], [14.75, 3.667], [14.75, 11.917], [27.667, 11.917], [27.667, 0]]   # wound clockwise, as the edge: stair rule reads it


def _deep_inside_corner(total_rise_in, rails=0):
    """Jefferson's L outline (jobs/jefferson_louisville.json) with box steps wrapping its 90-degree inside corner: 177" along the
    whole of the left wing's front (edge:2) and 99" up the middle's side (edge:3) from that corner; rails: a stair rail on both
    sides of each (on Prentice's rail system, as Jefferson has none)."""
    job = _job("jefferson_louisville")
    job["geometry"]["outline"] = copy.deepcopy(JEFFERSON_L)
    if rails:
        job["railing"] = dict(copy.deepcopy(JOB["railing"]), edges=["edge:1", "edge:4", "edge:5"])
    job["stairs"] = [dict(side=s, width_in=w, position_in=0, total_rise_in=total_rise_in, landing="grade", rails=rails, build="box",
                          skirts=True, closed_risers=True, name=f"Test box step {s}") for s, w in (("edge:2", 177), ("edge:3", 99))]
    return job


@pytest.mark.parametrize("total_rise_in, tiers, rails", [(22, 2, 0), (29, 3, 0), (22, 2, 2)])
def test_a_deep_inside_corner_keeps_one_cross_member_per_tier_at_the_miter(total_rise_in, tiers, rails):
    P = _build(_deep_inside_corner(total_rise_in, rails))
    f2, f3 = _frames(P)[1:3]
    k = _miter(f2, f3)
    assert k == pytest.approx(-1.0, abs=1e-3)                                            # a 90-degree inside corner
    assert box_step_miters(P.spec, P.L.stairs) == {"edge:2": (1, pytest.approx(1.0, abs=1e-3)), "edge:3": (1, pytest.approx(1.0, abs=1e-3))}
    line = {"edge:2": lambda u: f2[3] + k * u, "edge:3": lambda u: -k * u}             # the miter line along each side, u out from it
    for side, f, at_end in (("edge:2", f2, True), ("edge:3", f3, False)):
        st = next(s for s in P.L.stairs if s.side == side)
        assert st.geo.treads == tiers
        cross = [b for b in _kept(P, side) if b.kind == "joist" and "box step frame" in b.tag]
        by_tier = {}
        for b in cross:
            by_tier.setdefault(round(b.z1, 6), []).append(b)
        assert len(by_tier) == tiers and not [b.tag for b in cross if b.quad], side
        for grp in by_tier.values():
            # no two on one spot (each used to be set back by its own overshoot, all onto the same one)
            assert max(_overlap(box_plan_corners(p), box_plan_corners(q)) for p, q in combinations(grp, 2)) < 1e-9, side
            for b in grp:                  # square, 1 1/2", inside its own step and on its own side of the miter line
                loc = _local(f, box_plan_corners(b))
                vs = [v for v, _ in loc]
                assert (max(vs) - min(vs)) * 12 == pytest.approx(1.5, abs=1e-6), side
                assert -1e-6 < min(vs) and max(vs) < st.width / 12 + 1e-6, side
                assert all((v <= line[side](u) + 1e-6) if at_end else (v >= line[side](u) - 1e-6) for v, u in loc), side
            # and one closes the tier at the miter: its outer face within a member's width of where the line comes nearest
            near = max(grp, key=lambda b: max(_v(f, b))) if at_end else min(grp, key=lambda b: min(_v(f, b)))
            loc = _local(f, box_plan_corners(near))
            us = [u for _, u in loc]
            m = (min if at_end else max)(line[side](min(us)), line[side](max(us)))
            face = max(v for v, _ in loc) if at_end else min(v for v, _ in loc)
            assert -1e-9 <= (m - face if at_end else face - m) < 1.5 / 12 + 1e-6, side
    A, B_ = _kept(P, "edge:2"), _kept(P, "edge:3")
    assert max(_overlap(box_plan_corners(p), box_plan_corners(q)) for p in A for q in B_) < 1e-4       # the steps meet, never overlap
    assert all(_convex(b.quad) for b in A + B_ if b.quad)
    if rails:          # the rail on each step's corner side goes as a whole, the one on its free side stays whole
        for side, f in (("edge:2", f2), ("edge:3", f3)):
            gone = [b for b in _mine(P, side, P.dropped) if b.kind in ACROSS - {"joist"}]
            kept = [b for b in _kept(P, side) if b.kind in ACROSS - {"joist"}]
            assert Counter(b.kind for b in gone) == Counter(railpost=2, toprail=1, baluster=2 * tiers) == Counter(b.kind for b in kept), side
            mid = next(s for s in P.L.stairs if s.side == side).width / 24
            assert all((min(_v(f, b)) > mid) == (side == "edge:2") for b in gone), side


def _hand_drawn_corner(turn_deg):
    """Two box steps meeting at an outline corner, drawn the way build_scene draws one off an axis-aligned side: side 2 of a
    clockwise outline runs +x along y = 10 to the corner at (10, 10), side 3 turns turn_deg to the left off it (the deck bends
    out toward the steps: an inside corner) or to the right (an outside one). The 120" step on side 2 has a tread and a stair
    rail on each side (posts, balusters and a top rail pitched about x); the one on side 3 starts at the corner."""
    a = math.radians(turn_deg)
    poly = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (20.0, 10.0 + 10.0 * math.tan(a)), (20.0, 0.0)]
    B = [Box("tread", -0.1, 10.1, 10.0, 11.6, 0.9, 1.0, "deck", 6, tag="tread 1 edge:2")]
    for vc in (0.12, 9.88):
        B += [Box("railpost", vc - 0.1, vc + 0.1, 10.0 + u - 0.1, 10.0 + u + 0.1, 0.0, 4.0, "railmetal", 7, tag="stair post") for u in (0.2, 1.5)]
        B += [Box("baluster", vc - 0.03, vc + 0.03, 10.0 + u - 0.03, 10.0 + u + 0.03, 0.0, 3.0, "railmetal", 7) for u in (0.5, 1.0)]
        B.append(Box("toprail", vc - 0.06, vc + 0.06, 10.2, 11.5, 3.0, 3.1, "railmetal", 7, rot=0.6, rot_axis="x"))
    steps = [(SimpleNamespace(side="edge:2", width=120.0, opening=SimpleNamespace(start_in=0.0)), 2, 0, len(B)),
             (SimpleNamespace(side="edge:3", width=60.0, opening=SimpleNamespace(start_in=0.0)), 3, len(B), len(B))]
    return B, steps, poly


def test_a_stair_rail_that_reaches_over_the_miter_line_goes_as_a_whole():
    """At a shallow inside corner only the rail's bottom post reaches over the line: the whole rail on that side goes with it
    (one cut short of the corner would stop in mid-step); at the outside corner the same turn the other way, nothing goes."""
    B, steps, poly = _hand_drawn_corner(4.0)
    k = _miter(*outline_side_frames(poly)[1:3])
    assert k == pytest.approx(-math.tan(math.radians(2.0)))
    f2 = outline_side_frames(poly)[1]
    over = {i: max(v - (f2[3] + k * u) for v, u in _local(f2, box_plan_corners(b))) for i, b in enumerate(B)}     # how far each reaches over the line
    corner_side = {i for i, b in enumerate(B) if b.kind != "tread" and (b.x0 + b.x1) / 2 > 5}
    assert {i for i in corner_side if over[i] > 0} == {i for i in corner_side if B[i].kind == "railpost" and B[i].y0 > 10.5}   # just the bottom post
    assert scene_mod._miter_box_steps(B, steps, poly) == corner_side and B[0].quad
    B, steps, poly = _hand_drawn_corner(-4.0)
    assert _miter(*outline_side_frames(poly)[1:3]) > 0
    assert scene_mod._miter_box_steps(B, steps, poly) == set() and B[0].quad and not [b for b in B[1:] if b.quad]


def test_every_cut_outline_is_convex_and_runs_around_one_way(prentice, three, inside, railed):
    for P in (prentice, three, inside, railed):
        quads = [b for b in P.sc.boxes if b.quad and not b.tag.startswith("pf ")]
        assert quads and all(len(b.quad) == 4 and _convex(b.quad) for b in quads), [b.tag for b in quads if not _convex(b.quad)]


# ------------------------------------------------------------------ A3: the guard across an option stair's opening
def _option_guard(job, part=None):
    """The scene the option stair is drawn in (a composite's part, or the deck), its guard's top rail and the deck rail's posts."""
    t, _, _ = run(DeckSpec.from_dict(job), with_pricing=False)
    L = t.layout.parts[part].layout if part is not None else t.layout
    S = build_scene(L)
    (g,) = [b for b in S.boxes if b.kind == "toprail" and "guard across" in (b.tag or "")]
    assert g.layer.startswith("base:")
    posts = [b for b in S.boxes if b.kind == "railpost" and not (b.layer or "").startswith(("option:", "base:"))]
    return L, S, g, posts


def _fillmore_on(side, position_in):
    job = copy.deepcopy(FILLMORE)
    st = job["geometry"]["parts"][0]["stairs"][0]
    assert st["option"] and st["side"] == "edge:2"
    st.update(side=side, position_in=position_in)
    return job


def _prentice_option_on(side, position_in, width_in):
    job = copy.deepcopy(JOB)
    job["stairs"].append(dict(copy.deepcopy(JOB["stairs"][0]), side=side, position_in=position_in, width_in=width_in, rails=2,
                              name="Test option stair", option="Test option stair"))
    return job


@pytest.mark.parametrize("label, job, part, side, inward", [
    ("Fillmore lower level, left side (the stair goes -x)", lambda: _fillmore_on("edge:1", 60), 0, "edge:1", 1),
    ("Fillmore lower level, left side, farther out", lambda: _fillmore_on("edge:1", 150), 0, "edge:1", 1),
    ("Prentice, right end (the stair goes +x)", lambda: _prentice_option_on("edge:10", 17, 36), None, "edge:10", -1),
    ("Fillmore as the job has it: the lower level's front", lambda: copy.deepcopy(FILLMORE), 0, "edge:2", -1),
])
def test_option_guard_stands_on_the_deck_rail_line(label, job, part, side, inward):
    L, S, g, posts = _option_guard(job(), part)
    e = next(q for q in L.outline_edges if q.name == side)
    vert = abs(e.x1 - e.x0) < 0.5
    frame = (e.x0 if vert else e.y0) / 12                                               # the side's frame line (ft)
    line = ((g.x0 + g.x1) if vert else (g.y0 + g.y1)) / 2
    assert line == pytest.approx(frame + inward * RP, abs=1e-3), label                  # RP in from the frame, toward the deck
    lo, hi = (g.y0, g.y1) if vert else (g.x0, g.x1)
    at_ends = [p for p in posts if min(abs(((p.y0 + p.y1) if vert else (p.x0 + p.x1)) / 2 - a) for a in (lo, hi)) < 0.05
               and abs(((p.x0 + p.x1) if vert else (p.y0 + p.y1)) / 2 - line) < 0.3]
    assert at_ends and all(((p.x0 + p.x1) if vert else (p.y0 + p.y1)) / 2 == pytest.approx(line, abs=1e-3) for p in at_ends), label


# ------------------------------------------------------------------ A4: British "grey" in a job's colors
def test_a_british_gray_reads_as_gray():
    rail, roof = scene_mod._rail_hex, scene_mod._roof_hex
    assert rail("Grey") == rail("Steel Grey") == rail("Gray") == "#6b6e70" != rail("Black")
    assert roof("Grey") == roof("gray") == "#6b6e70" and roof("Charcoal Grey") == roof("Charcoal")
    assert scene_mod._hardie_hex("Iron Grey") == scene_mod._hardie_hex("Iron Gray") == HARDIE_HEX["iron gray"]
    assert scene_mod._hardie_hex("Night Grey (color TBD)") == HARDIE_HEX["night gray"]
    assert scene_mod._furn_hex("Grey") == scene_mod._furn_hex("gray") == FURN_HEX["gray"]
    assert scene_mod._furn_hex("Dark Pebble Grey") == FURN_HEX["dark pebble gray"]
    assert scene_mod._furn_mat("canopy", "Grey") == scene_mod._furn_mat("canopy", "gray") == "furn_canopy"           # the default key
    assert scene_mod._furn_mat("cushion", "Pacific Fog Grey") == "furn_cushion"
    assert scene_mod._palette("Prime+", "Sea Salt Grey") == scene_mod._palette("Prime+", "sea salt gray") == BOARDS_PALETTE[("Prime+", "Sea Salt Gray")]
    assert scene_mod._palette("Prime", "Maritime Grey") == BOARDS_PALETTE[("Prime", "Maritime Gray")]
    assert scene_mod._palette("Vintage", "Coastline") == BOARDS_PALETTE[("Vintage", "Coastline")]


@pytest.mark.parametrize("name, path, british, american, key, default", [
    ("prentice_centennial", ("railing", "color"), "Grey", "Gray", "railmetal", "#141416"),
    ("jefferson_louisville", ("extras", "cover_roof_color"), "Grey", "Gray", "ssroof", "#3a3c3f"),
    ("lansing_englewood", ("geometry", "sails", 0, "color"), "Steel Grey", "Steel Gray", "sail", "#e6e1d2"),
    ("prentice_centennial", ("extras", "hardie_color"), "Iron Grey", "Iron Gray", "hardie", "#4b3f34"),
    ("prentice_centennial", ("decking", "color"), "Sea Salt Grey", "Sea Salt Gray", "deck", None),
])
def test_a_job_color_typed_british_draws_the_same(name, path, british, american, key, default):
    def color(value):
        job = _job(name)
        if key == "deck":
            job["decking"]["collection"] = "Prime+"
        node = job
        for p in path[:-1]:
            node = node[p]
        node[path[-1]] = value
        return materials_for(DeckSpec.from_dict(job))[key]
    br, am = color(british), color(american)
    assert br["color"] == am["color"] and br.get("palette") == am.get("palette")
    assert br["color"] != (default or scene_mod._palette("", "")[2])                    # not the fallback


def test_styling_colors_typed_british_use_the_default_materials():
    job = copy.deepcopy(FILLMORE)
    job["geometry"]["furniture"] = [dict(type="umbrella", level="upper", x=36.0, y=6.0, canopy="Grey"),
                                    dict(type="sofa", level="lower", x=8.0, y=3.0, cushion="Pacific Fog Grey")]
    spec = DeckSpec.from_dict(job)
    mats = furniture_materials(spec)
    assert {"furn_canopy", "furn_cushion"} <= set(mats) and not [k for k in mats if "grey" in k]
    assert mats["furn_canopy"]["color"] == FURN_HEX[FURN_DEFAULT_COLOR["canopy"]] and mats["furn_cushion"]["color"] == FURN_HEX["pacific fog gray"]
    t, _, _ = run(spec, with_pricing=False)
    used = {b.mat for b in furniture_boxes(spec, furniture_levels(t.layout))}
    assert {"furn_canopy", "furn_cushion"} <= used <= set(mats)


def test_color_tables_keep_one_american_key_each():
    tree = ast.parse(Path(scene_mod.__file__).read_text())
    for node in ast.walk(tree):                         # no dict in scene.py spells a key twice (the rename left "gray" twice)
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            assert len(keys) == len(set(keys)), sorted({k for k in keys if keys.count(k) > 1})
    (loop,) = [n for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(scene_mod._roof_hex)))) if isinstance(n, ast.For)]
    names = [e.elts[0].value for e in loop.iter.elts]
    assert "gray" in names and len(names) == len(set(names))
    for table in (SAIL_COLORS, FURN_HEX, HARDIE_HEX, FURN_DEFAULT_COLOR):
        assert not [k for k in list(table) + [str(v) for v in table.values()] if "grey" in k.lower()]
    # British input is read in one place: the lookup's normalization
    grey = lambda src: [ln.strip() for ln in src.splitlines() if "grey" in ln.lower()]
    assert grey(inspect.getsource(scene_mod)) == grey(inspect.getsource(scene_mod._color_key)) and grey(inspect.getsource(scene_mod._color_key))
