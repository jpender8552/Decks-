"""Box steps on an outline deck — the Prentice job (jobs/prentice_centennial.json): a 73" box step on the left side (edge:2) and a
68" one on the front angle (edge:3) both reach their shared outline corner and miter into one step that follows the deck
(scene._miter_box_steps / box_step_miters / outline_side_frames / box_plan_corners, the cut pieces' true outline in Box.quad);
the step off the angled side is drawn turned onto it, outside the deck; the takeoff cuts the mitered treads and risers long to
the miter; the yard model still reads the old "neighbours" key; and what reads Box.quad (the isometrics, the viewer export, the
C-100 / A-100 plans) draws the mitered outline."""
import copy
import dataclasses
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from decktakeoff import run
from decktakeoff import scene as scene_mod
from decktakeoff.layout import build_layout
from decktakeoff.scene import Box, box_plan_corners, box_step_miters, build_scene, outline_side_frames, rot_box
from decktakeoff.spec import DeckSpec
from decktakeoff.units import ftin, to_inches

ROOT = Path(__file__).resolve().parent.parent
JOB = json.loads((ROOT / "jobs" / "prentice_centennial.json").read_text())
SIDE_A, SIDE_B = "edge:2", "edge:3"       # "Left box step — left side" (73") and "— front angle" (68"): they share outline vertex 3
TOL = 0.05                                 # ft
MITER_PTS = [(-0.087, 10.161), (-1.075, 10.565)]     # where the two treads meet: inner (nose of the top riser) and outer edge


def _build(job):
    """The job's takeoff, flags and scene, plus what _miter_box_steps was handed and did, caught on the way through:
    steps = {side: the step's boxes in drawing order}, dropped = the boxes it took out."""
    spec = DeckSpec.from_dict(job)
    t, flags, _ = run(spec, with_pricing=False)
    seen = {}
    real = scene_mod._miter_box_steps

    def spy(B, edge_steps, poly, *a, **k):
        drop = real(B, edge_steps, poly, *a, **k)
        seen["steps"] = {rec[0].side: B[rec[2]:rec[3]] for rec in edge_steps}    # (stair layout, side index, first box, last box)
        seen["dropped"] = [B[i] for i in sorted(drop)]
        return drop

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(scene_mod, "_miter_box_steps", spy)
        sc = build_scene(t.layout)
    assert seen, "build_scene no longer hands the edge box steps to _miter_box_steps"
    return SimpleNamespace(spec=spec, t=t, L=t.layout, flags=flags, sc=sc, steps=seen["steps"], dropped=seen["dropped"])


@pytest.fixture(scope="module")
def prentice():
    return _build(JOB)


# ------------------------------------------------------------------ helpers (plan feet)
def _poly(spec):
    return [(float(x), float(y)) for x, y in spec.geometry.outline]


def _inside(poly, x, y):
    c = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            c = not c
    return c


def _area(P):
    return 0.5 * sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))


def _overlap(P, Q):
    """The plan area (sq ft) two convex outlines share (Sutherland-Hodgman, either winding)."""
    out = list(P) if _area(P) > 0 else list(P)[::-1]
    C = list(Q) if _area(Q) > 0 else list(Q)[::-1]
    for i in range(len(C)):
        (ax, ay), (bx, by) = C[i], C[(i + 1) % len(C)]
        side = lambda p: (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        inp, out = out, []
        for j in range(len(inp)):
            p, q = inp[j - 1], inp[j]
            sp, sq = side(p), side(q)
            if (sp >= 0) != (sq >= 0):
                f = sp / (sp - sq)
                out.append((p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f))
            if sq >= 0:
                out.append(q)
        if len(out) < 3:
            return 0.0
    return abs(_area(out))


def _local(frame, pts):
    """Plan points in an outline side's frame: (v along the side from its start, u out of the deck)."""
    (px, py), (tx, ty), (nx, ny), _ = frame
    return [((x - px) * tx + (y - py) * ty, (x - px) * nx + (y - py) * ny) for x, y in pts]


def _samples(pts):
    """A footprint's corners, the middles of its sides and its center."""
    n = len(pts)
    mids = [((pts[i][0] + pts[(i + 1) % n][0]) / 2, (pts[i][1] + pts[(i + 1) % n][1]) / 2) for i in range(n)]
    return list(pts) + mids + [(sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n)]


def _near(b, pt):
    return min(math.hypot(x - pt[0], y - pt[1]) for x, y in box_plan_corners(b))


def _skirt(b):
    return b.kind == "fascia" and "skirt" in (b.tag or "")


def _kept(P, side):
    """The step's boxes as _miter_box_steps left them (the skirts it dropped taken out)."""
    gone = {id(b) for b in P.dropped}
    return [b for b in P.steps[side] if id(b) not in gone]


def _drawn(P, side):
    """... and of those, the ones in the finished scene."""
    final = {id(b) for b in P.sc.boxes}
    return [b for b in _kept(P, side) if id(b) in final]


def _cyclic(ring, quad):
    """ring runs around quad (any start point, either way)."""
    Q = [(float(x), float(y)) for x, y in quad]
    for R in (Q, Q[::-1]):
        for i in range(len(R)):
            if all(math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-9 for a, b in zip(ring, R[i:] + R[:i])):
                return True
    return False


def _similar(P, quad, tol=0.35):
    """The scale s > 0 when the sheet polygon P is the plan outline `quad` scaled and shifted (a plan sheet: no turn, the yard
    down the sheet), from any start point or winding; else None."""
    Q = [(float(x), float(y)) for x, y in quad]
    if len(P) != len(Q):
        return None
    for R in [Q[i:] + Q[:i] for i in range(len(Q))] + [Q[::-1][i:] + Q[::-1][:i] for i in range(len(Q))]:
        dq = math.hypot(R[2][0] - R[0][0], R[2][1] - R[0][1])
        s = math.hypot(P[2][0] - P[0][0], P[2][1] - P[0][1]) / dq
        ox, oy = P[0][0] - s * R[0][0], P[0][1] - s * R[0][1]
        if s > 0 and all(math.hypot(px - (ox + s * qx), py - (oy + s * qy)) < tol for (px, py), (qx, qy) in zip(P, R)):
            return s
    return None


# ------------------------------------------------------------------ the outline frame and the miter test
def test_job_still_has_the_two_box_steps_at_one_corner(prentice):
    st = {s.side: s for s in prentice.L.stairs}
    assert st[SIDE_A].build == st[SIDE_B].build == "box" and (st[SIDE_A].width, st[SIDE_B].width) == (73, 68)
    assert st[SIDE_A].opening.start_in == st[SIDE_B].opening.start_in == 0
    poly = _poly(prentice.spec)
    assert poly[2] == (0.0, 10.125)                 # side 2 ends and side 3 starts at the corner
    assert set(prentice.steps) == {SIDE_A, SIDE_B}  # the center stair (stringers, edge:6) is not a box step


def test_outline_side_frames_point_out_of_the_deck(prentice):
    """Every side as (start, unit tangent, unit outward normal, length), whichever way the outline is wound."""
    poly = _poly(prentice.spec)
    for pts in (poly, poly[::-1]):
        frames = outline_side_frames(pts)
        assert len(frames) == len(pts)
        for i, ((px, py), (tx, ty), (nx, ny), Ls) in enumerate(frames):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
            assert (px, py) == (ax, ay) and Ls == pytest.approx(math.hypot(bx - ax, by - ay))
            assert math.hypot(tx, ty) == pytest.approx(1) and math.hypot(nx, ny) == pytest.approx(1) and abs(tx * nx + ty * ny) < 1e-9
            mx, my = ax + tx * Ls / 2, ay + ty * Ls / 2
            assert not _inside(poly, mx + 0.25 * nx, my + 0.25 * ny), f"side {i + 1}: the normal points into the deck"
            assert _inside(poly, mx - 0.25 * nx, my - 0.25 * ny), f"side {i + 1}"
    side2, side3 = outline_side_frames(poly)[1:3]
    assert side2[2] == pytest.approx((-1.0, 0.0)) and side2[3] * 12 == pytest.approx(73, abs=0.01)
    assert side3[3] * 12 == pytest.approx(68, abs=0.05)


def test_box_plan_corners_quad_turned_and_square():
    q = [[0.0, 0.0], [2.0, 0.0], [1.5, 1.0], [0.0, 1.0]]
    assert box_plan_corners(Box("tread", 0, 2, 0, 1, 0, 0.1, "deck", quad=q)) == [(0.0, 0.0), (2.0, 0.0), (1.5, 1.0), (0.0, 1.0)]
    turned = box_plan_corners(Box("tread", 0, 2, 0, 1, 0, 0.1, "deck", rot=math.pi / 2, rot_axis="z"))      # about its center
    assert sorted((round(x, 9), round(y, 9)) for x, y in turned) == [(0.5, -0.5), (0.5, 1.5), (1.5, -0.5), (1.5, 1.5)]
    pitched = box_plan_corners(Box("stringer", 0, 2, 0, 1, 0, 0.1, "timber", rot=0.6, rot_axis="x"))         # a pitch does not turn the plan
    assert sorted((round(x, 9), round(y, 9)) for x, y in pitched) == [(0, 0), (0, 1), (2, 0), (2, 1)]


def test_box_step_miters_one_end_each_at_the_corner_angle(prentice):
    poly = _poly(prentice.spec)
    heading = lambda a, b: math.atan2(b[1] - a[1], b[0] - a[0])
    turn = abs(heading(poly[1], poly[2]) - heading(poly[2], poly[3]))      # side 2 runs vertex 2 -> 3, side 3 vertex 3 -> 4
    k = math.tan(turn / 2)
    assert k == pytest.approx(0.4093, abs=1e-3)                              # a 44.5 degree turn
    m = box_step_miters(prentice.spec, prentice.L.stairs)
    assert set(m) == {SIDE_A, SIDE_B}
    for side in (SIDE_A, SIDE_B):
        ends, k_ = m[side]
        assert ends == 1 and k_ == pytest.approx(k, abs=1e-9), side


# ------------------------------------------------------------------ the mitered step in the scene
def test_mitered_treads_meet_on_the_miter_line(prentice):
    frames = outline_side_frames(_poly(prentice.spec))
    fa, fb = frames[1], frames[2]
    corner = fb[0]
    (ta,) = [b for b in _drawn(prentice, SIDE_A) if b.kind == "tread"]
    (tb,) = [b for b in _drawn(prentice, SIDE_B) if b.kind == "tread"]
    assert ta.quad and tb.quad and len(ta.quad) == len(tb.quad) == 4
    assert (ta.z0, ta.z1) == pytest.approx((tb.z0, tb.z1))                  # one step: the same tread height on both sides
    edges = lambda q: [(tuple(q[i]), tuple(q[(i + 1) % len(q)])) for i in range(len(q))]
    d = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])
    shared = [(p, q) for p, q in edges(ta.quad) for r, s in edges(tb.quad)
              if (d(p, r) < TOL and d(q, s) < TOL) or (d(p, s) < TOL and d(q, r) < TOL)]
    assert len(shared) == 1, "the two treads' outlines do not share the miter line"
    inner, outer = sorted(shared[0], key=lambda p: d(p, corner))
    assert d(inner, MITER_PTS[0]) < TOL and d(outer, MITER_PTS[1]) < TOL
    nx, ny = fa[2][0] + fb[2][0], fa[2][1] + fb[2][1]                     # the corner's bisector
    for x, y in (inner, outer):
        assert abs((x - corner[0]) * ny - (y - corner[1]) * nx) / math.hypot(nx, ny) < 0.01
    _, k = box_step_miters(prentice.spec, prentice.L.stairs)[SIDE_A]       # the k the takeoff cuts by is the k the scene cut by
    assert all(v == pytest.approx(fa[3] + k * u, abs=0.01) for v, u in _local(fa, (inner, outer)))
    assert all(v == pytest.approx(-k * u, abs=0.01) for v, u in _local(fb, (inner, outer)))


def test_the_two_steps_do_not_overlap_in_plan(prentice):
    A, B_ = _kept(prentice, SIDE_A), _kept(prentice, SIDE_B)
    assert sum(bool(b.quad) for b in A) >= 4 and sum(bool(b.quad) for b in B_) >= 4    # treads, risers, frame, stone bed cut
    worst = max((_overlap(box_plan_corners(a), box_plan_corners(b)), a.tag, b.tag) for a in A for b in B_)
    assert worst[0] < 1e-4, worst                                           # sq ft (0.014 sq in)
    # the boxes alone (no miter outline) run into each other at the corner, so the check has teeth
    sq = lambda b: box_plan_corners(dataclasses.replace(b, quad=None))
    assert max(_overlap(sq(a), sq(b)) for a in A for b in B_ if a.kind == b.kind == "tread") > 0.005
    # and every piece stays on its own side of the miter line
    frames = outline_side_frames(_poly(prentice.spec))
    fa, fb = frames[1], frames[2]
    _, k = box_step_miters(prentice.spec, prentice.L.stairs)[SIDE_A]
    for b in A:
        assert all(v <= fa[3] + k * u + 0.01 for v, u in _local(fa, box_plan_corners(b))), b.tag
    for b in B_:
        assert all(v >= -k * u - 0.01 for v, u in _local(fb, box_plan_corners(b))), b.tag


def test_the_corner_end_skirts_go(prentice):
    corner = _poly(prentice.spec)[2]
    assert len(prentice.dropped) == 2 and all(_skirt(b) for b in prentice.dropped)
    for side in (SIDE_A, SIDE_B):
        mine = [b for b in prentice.dropped if any(b is p for p in prentice.steps[side])]
        assert len(mine) == 1 and _near(mine[0], corner) < 0.15, side       # the skirt at the corner (a miter has no exposed end)
        left = [b for b in _kept(prentice, side) if _skirt(b)]
        assert len(left) == 1 and _near(left[0], corner) > 5.0, side        # the one at the step's free end stays
    assert not [b for b in prentice.sc.boxes if _skirt(b) and _near(b, corner) < 0.5]


def test_step_off_the_angled_side_is_turned_onto_it_outside_the_deck(prentice):
    poly = _poly(prentice.spec)
    fb = outline_side_frames(poly)[2]
    phi = math.atan2(poly[3][1] - poly[2][1], poly[3][0] - poly[2][0])
    width = next(s.width for s in prentice.L.stairs if s.side == SIDE_B) / 12
    pieces = _kept(prentice, SIDE_B)
    assert {"tread", "riser", "rim", "joist", "stepbase"} <= {b.kind for b in pieces}
    final = {id(b) for b in prentice.sc.boxes}
    for b in pieces:
        assert id(b) in final, b.tag                                        # every piece of it is drawn
        assert b.rot_axis == "z" and b.rot == pytest.approx(phi, abs=1e-9), b.tag
        if b.kind in ("tread", "riser", "rim"):
            assert b.x1 - b.x0 >= width - 0.01 > b.y1 - b.y0, b.tag         # the box's own x runs along the side (before the turn)
        for pts in (box_plan_corners(b), box_plan_corners(dataclasses.replace(b, quad=None))):
            for v, u in _local(fb, pts):
                assert 0 < u < 1.5 and -0.5 < v < fb[3] + 0.5, b.tag         # out from side 3, along it — not under the deck
            assert not [p for p in _samples(pts) if _inside(poly, *p)], b.tag
    for b in _kept(prentice, SIDE_A):                                       # the square side's step stays square, also outside
        assert not (b.rot and b.rot_axis == "z"), b.tag
        assert not [p for p in _samples(box_plan_corners(b)) if _inside(poly, *p)], b.tag


def test_both_steps_keep_their_box_frame_and_free_end_skirt(prentice):
    """apply_outline once clipped the square step's frame and free-end skirt (and the center stair's skirts) to nothing."""
    skirts6 = [b for b in prentice.sc.boxes if b.kind == "fascia" and (b.tag or "") == "stair skirt edge:6"]
    assert len(skirts6) == 4                                                # the center stair: both sides, under each of its 2 treads
    for side in (SIDE_A, SIDE_B):
        mine = [b for b in prentice.sc.boxes if (b.tag or "").split()[-1:] == [side]]
        rims = [b for b in mine if b.kind == "rim" and "box step frame" in b.tag]
        cross = [b for b in mine if b.kind == "joist" and "box step frame" in b.tag]
        assert len(rims) == 2 and all(b.quad for b in rims), side            # front and back rims, both cut on the miter
        assert len(cross) >= 2, side
        assert len([b for b in mine if _skirt(b)]) == 1, side                # the free end's (the corner's went with the miter)


def test_no_miter_when_a_step_stops_short_of_the_corner():
    job = copy.deepcopy(JOB)
    assert job["stairs"][1]["side"] == SIDE_A
    job["stairs"][1]["width_in"] = 60                                       # the left-side step ends 13" short of the corner
    P = _build(job)
    assert box_step_miters(P.spec, P.L.stairs) == {}
    assert not P.dropped
    assert not [b.tag for side in (SIDE_A, SIDE_B) for b in P.steps[side] if b.quad]
    assert len([b for b in P.steps[SIDE_B] if _skirt(b)]) == 2              # the angled step keeps both end skirts
    name = job["stairs"][1]["name"]
    risers = next(c for c in P.t.cut_list if c.member == f"Stair risers ({name})")
    assert risers.length_in == 60 and "mitered" not in risers.note


# ------------------------------------------------------------------ the takeoff's miter allowance
def test_takeoff_cuts_the_mitered_risers_long(prentice):
    t, spec = prentice.t, prentice.spec
    miters = box_step_miters(spec, t.layout.stairs)
    hardie = [l for l in t.lines if l.item.startswith("HardieTrim") and "every riser" in l.item]
    assert len(hardie) == 1                                                 # extras.hardie_skirt: every riser cut from HardieTrim
    shown_long = {SIDE_A: "6'-6 1/16\"", SIDE_B: "6'-1 1/16\""}             # 73" and 68" run long to the miter
    for st, ss in zip(t.layout.stairs, spec.stairs):
        ends, k = miters.get(st.side, (0, 0.0))
        cut_w = st.width + ends * k * (st.geo.treads * st.geo.tread_in + 1.0)    # the outer edge of the lowest tread / riser
        m = re.search(r"(\d+) @ ([^()·]+?) \(" + re.escape(ss.name) + r"\)", hardie[0].why)
        assert m, (ss.name, hardie[0].why)
        assert int(m.group(1)) == st.riser_pieces and to_inches(m.group(2)) == pytest.approx(cut_w, abs=1 / 32 + 1e-6)
        risers = next(c for c in t.cut_list if c.member == f"Stair risers ({ss.name})")
        treads = next(c for c in t.cut_list if c.member == f"Stair treads ({ss.name})")
        if st.side in (SIDE_A, SIDE_B):
            assert ends == 1 and cut_w - st.width == pytest.approx(5.07, abs=0.05) and ftin(cut_w) == shown_long[st.side]
            for c in (risers, treads):
                assert "mitered at the corner" in c.note and f"outer edge {ftin(cut_w)}" in c.note, c
        else:                                                               # the center stair: square ends, cut to its width
            assert cut_w == st.width and "mitered" not in risers.note + treads.note


# ------------------------------------------------------------------ the yard model: "neighbours" still reads as "neighbors"
def test_old_neighbours_key_draws_the_same_houses():
    from dataclasses import asdict
    from decktakeoff.landscape import build_site, neighbor_materials
    houses = [{"name": "plain neighbor", "rect": [-30, -10, 40, 60], "eave": 18.0, "ridge": 25.0, "axis": "x", "mat": "nsiding_a",
               "windows": [[-25, -21, 39.95, 40.05, 4.0, 8.0]]},
              {"name": "turned neighbor", "rect": [20, 44, 50, 80], "rot": 12, "axis": "y", "base": {"z1": 6.0}, "mat": "nsiding_b",
               "face_windows": [["y0", 4, 8, 4, 8]]}]

    def draw(model):
        out = []
        build_site(model, lambda *a, **k: out.append(asdict(Box(*a, **k))), lambda *a, **k: out.append(asdict(rot_box(*a, **k))),
                   lambda kind, tri, mat, tag="": out.append((kind, mat, tag, [[float(v) for v in q] for q in tri])), 1.5)
        return out

    new, old = draw({"neighbors": houses}), draw({"neighbours": copy.deepcopy(houses)})
    assert old == new and len(new) > len(draw({}))
    assert {"plain neighbor", "turned neighbor", "turned neighbor (brick)"} <= {b["tag"] for b in new if isinstance(b, dict)}
    assert neighbor_materials({"neighbours": houses}) == neighbor_materials({"neighbors": houses})
    assert {"nsiding_a", "nsiding_b", "nsiding_b_base", "nroof", "ntrim", "nglass"} <= set(neighbor_materials({"neighbours": houses}))


def test_prentice_yard_is_the_same_under_either_spelling():
    old = copy.deepcopy(JOB)
    sm = old["geometry"]["site_model"]
    sm["neighbours"] = sm.pop("neighbors")
    sc_new = build_scene(build_layout(DeckSpec.from_dict(JOB)))
    sc_old = build_scene(build_layout(DeckSpec.from_dict(old)))
    site = lambda sc: [dataclasses.asdict(b) for b in sc.boxes if b.layer == "site"]
    assert site(sc_old) == site(sc_new)
    assert sc_old.materials == sc_new.materials
    assert {"south neighbor", "north neighbor", "rear neighbor"} <= {b.tag for b in sc_old.boxes if b.layer == "site" and b.kind == "house"}
    assert {"nsiding_s", "nsiding_n", "nsiding_e"} <= set(sc_old.materials)


# ------------------------------------------------------------------ what reads Box.quad
def test_axo_corners_are_the_quad_prism():
    from decktakeoff.axo import FACES, corners
    q = [[0.0, 0.0], [2.0, 0.0], [1.4, 0.9], [0.0, 0.9]]
    cs = corners(Box("tread", 0.0, 2.0, 0.0, 0.9, 1.0, 1.1, "deck", quad=q), lift=0.5)
    assert len(cs) == 8 and {(x, y) for x, y, _ in cs} == {tuple(p) for p in q}
    top, bottom = [cs[i] for i in FACES[5]], [cs[i] for i in FACES[4]]
    assert all(z == pytest.approx(1.6) for *_, z in top) and all(z == pytest.approx(1.5) for *_, z in bottom)
    assert _cyclic([(x, y) for x, y, _ in top], q) and _cyclic([(x, y) for x, y, _ in bottom], q)    # no bow tie


def test_axo_draws_the_mitered_step(prentice):
    from decktakeoff.axo import View, corners, draw
    pieces = _kept(prentice, SIDE_A) + _kept(prentice, SIDE_B)
    quads = [b for b in pieces if b.quad]
    assert len(quads) >= 8
    for b in quads:
        assert {(x, y) for x, y, _ in corners(b)} == {(float(x), float(y)) for x, y in b.quad}, b.tag
    svg, _, sc = draw(pieces, {}, View(35.0, 28.0), (0, 0, 400, 300))
    assert sc > 0 and len(svg) >= len(pieces) and all(s.startswith("<polygon") for s in svg)


def test_viewer_export_carries_each_miter_outline(prentice):
    from decktakeoff.viewer import viewer_html
    h = viewer_html(prentice.sc, three_src="")
    data, _ = json.JSONDecoder().raw_decode(h.split("const D = ", 1)[1])
    assert len(data["boxes"]) == len(prentice.sc.boxes) and all("quad" in b for b in data["boxes"])
    want = [[[float(v) for v in p] for p in b.quad] for b in prentice.sc.boxes if b.quad]
    assert [b["quad"] for b in data["boxes"] if b["quad"]] == want and len(want) >= 10
    assert {b["tag"].split()[-1] for b in data["boxes"] if b["kind"] == "tread" and b["quad"]} == {SIDE_A, SIDE_B}
    assert "quadPrism(b)" in h                                              # the viewer builds the prism over the outline


@pytest.fixture(scope="module")
def sheets(prentice):
    from decktakeoff.drawings import all_sheets
    sc = build_scene(prentice.L)                                            # its own scene: the sheets read it, the other tests don't
    return sc, {num: svg for num, _, svg in all_sheets(prentice.L, prentice.t, prentice.flags, scene=sc)}


def test_plan_sheets_draw_each_mitered_tread_as_its_outline(sheets):
    sc, svgs = sheets
    assert {"C-100", "A-100", "A-002", "A-003", "S-101", "S-102"} <= set(svgs)      # the plans and isometrics all built over the quads
    treads = [b for b in sc.boxes if b.kind == "tread" and b.quad]
    assert len(treads) == 2
    for num in ("C-100", "A-100"):
        polys = [[tuple(float(v) for v in p.split(",")) for p in pts.split()] for pts in re.findall(r'<polygon points="([^"]+)"', svgs[num])]
        scales = []
        for b in treads:
            hit = [s for s in (_similar(P, b.quad) for P in polys) if s]
            assert hit, f"{num}: no polygon traces {b.tag}"
            scales.append(hit[0])
        assert scales[0] == pytest.approx(scales[1], rel=0.01), num          # both at the sheet's one scale
