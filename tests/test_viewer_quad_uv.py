"""The viewer's mitered pieces (Box.quad: the picture-frame borders, a box step cut on a miter) carry board grain like the
field boards: quadPrism maps u 0..1 along the board and v 0..1 across it on the top and bottom (v up the height on the
sides), and material() gives them the along-u (horizontal) grain in a material of their own. Every top vertex used to get
v = 1 (the grain sampled from one row of the texture: flat borders), and a border long in y took the vertical grain while
its u ran along it (bands across it). The viewer's own script (pulled from the generated page) runs in node over the outline
decks' quads and pieces laid out by hand; a board's run comes from its box (the longer extent, turned by its rot), not from
the quad's proportions."""
import json
import math
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

from decktakeoff.layout import build_layout
from decktakeoff.scene import build_scene
from decktakeoff.spec import DeckSpec
from decktakeoff.viewer import viewer_html

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="runs the viewer's script in node")
ROOT = Path(__file__).resolve().parent.parent
TOL = 1e-6
# outline decks with mitered pieces, and the kinds each carries at least: Prentice (the picture frame, and two box steps
# mitered into one at a corner: the treads, risers, frame rims and stone beds that run along a side to it), Glengarry (a front
# curve in mitered segments, sides a hair off square), Jefferson (a plain picture frame)
JOBS = {"prentice_centennial": {"border", "tread", "riser", "rim", "stepbase"},
        "glengarry_1_fulton_existing": {"border"}, "jefferson_louisville": {"border"}}

# just enough of three.js for quadPrism and material(); texFor hands back which grain was asked for
HARNESS = r"""
const THREE = {DoubleSide: 2,
  BufferGeometry: class { constructor() { this.attributes = {}; this.userData = {}; } setAttribute(k, a) { this.attributes[k] = a; } computeVertexNormals() {} },
  Float32BufferAttribute: class { constructor(a, n) { this.array = Array.from(a); this.itemSize = n; } },
  Color: class { constructor(c) { this.c = c; } convertSRGBToLinear() { return this; } },
  MeshStandardMaterial: class { constructor(o) { Object.assign(this, o); } }};
const D = {materials: __MATERIALS__}, MATC = {};
const texFor = (mat, vertical, variant) => ({clone: () => ({vertical, repeat: {set(x, y) { this.x = x; this.y = y; }}})});
__FUNCTIONS__
process.stdout.write(JSON.stringify(__BOXES__.map(b => { const g = b.quad ? quadPrism(b) : null, m = material(b);
  return {pos: g && g.attributes.position.array, uv: g && g.attributes.uv.array, c: g && g.userData.c, key: Object.keys(MATC).find(k => MATC[k] === m),
          map: m.map ? {vertical: m.map.vertical, repeat: [m.map.repeat.x, m.map.repeat.y]} : null}; })));
"""


def _js_function(page, name):
    """`function name(...) {...}` out of the viewer's script (its braces matched; none sit in its strings)."""
    i = page.index(f"function {name}(")
    depth = 0
    for k in range(page.index("{", i), len(page)):
        depth += {"{": 1, "}": -1}.get(page[k], 0)
        if depth == 0:
            return page[i:k + 1]
    raise ValueError(name)


def _run(boxes, materials, page):
    js = HARNESS.replace("__FUNCTIONS__", "\n".join(_js_function(page, n) for n in ("quadPrism", "material")))
    js = js.replace("__MATERIALS__", json.dumps(materials)).replace("__BOXES__", json.dumps(boxes))
    return json.loads(subprocess.run([NODE, "-"], input=js, capture_output=True, text=True, check=True, timeout=120).stdout)


@lru_cache(maxsize=None)
def _job(name):
    """(the viewer page, its data, the mitered boxes, what the viewer's script made of each)"""
    S = build_scene(build_layout(DeckSpec.from_dict(json.loads((ROOT / "jobs" / f"{name}.json").read_text()))))
    page = viewer_html(S, three_src="")
    data, _ = json.JSONDecoder().raw_decode(page.split("const D = ", 1)[1])
    quads = [b for b in data["boxes"] if b.get("quad")]
    return page, data, quads, _run(quads, data["materials"], page)


def _run_axis(b):
    """The board's run in plan, from its box: the longer extent, turned by its rot about z."""
    r = b["rot"] if b.get("rot_axis") == "z" else 0.0
    return (math.cos(r), math.sin(r)) if b["x1"] - b["x0"] >= b["y1"] - b["y0"] else (-math.sin(r), math.cos(r))


def _grain(b):
    """Where the grain runs: along the quad's first edge q0 -> q1 (the true outline: a side a hair off square keeps a square
    box), or square to that edge when the box runs across it (the viewer's fallback for such a piece)."""
    (x0, y0), (x1, y1) = b["quad"][0], b["quad"][1]
    L = math.hypot(x1 - x0, y1 - y0)
    e, r = ((x1 - x0) / L, (y1 - y0) / L), _run_axis(b)
    return e if abs(e[0] * r[0] + e[1] * r[1]) > math.sqrt(0.5) else (-e[1], e[0])


def _fractions(pts, d):
    """Each point's place along d as a fraction of the piece's extent that way."""
    s = [x * d[0] + y * d[1] for x, y in pts]
    return [(v - min(s)) / (max(s) - min(s)) for v in s]


def _matches(vals, fr):
    """vals are the fractions fr, counted from either end."""
    return any(all(abs(a - (f if fwd else 1 - f)) < TOL for a, f in zip(vals, fr)) for fwd in (True, False))


def _top_uv(o):
    """{plan corner: (u, v)} on the top face."""
    return {(round(o["pos"][3 * i] + o["c"][0], 3), round(o["pos"][3 * i + 2] + o["c"][1], 3)): (round(o["uv"][2 * i], 4), round(o["uv"][2 * i + 1], 4))
            for i in range(6)}


@pytest.fixture(scope="module")
def prentice():
    return _job("prentice_centennial")


@pytest.mark.parametrize("name", JOBS)
def test_top_and_bottom_run_the_grain_along_the_board(name):
    _, _, quads, out = _job(name)
    assert {b["kind"] for b in quads} >= JOBS[name]
    for b, o in zip(quads, out):
        g, r = _grain(b), _run_axis(b)
        assert abs(g[0] * r[0] + g[1] * r[1]) > 0.99, b["tag"]                     # the grain runs with the board (its box)
        for face in (range(0, 6), range(6, 12)):                  # the top's two triangles, then the bottom's
            pts = [(o["pos"][3 * i] + o["c"][0], o["pos"][3 * i + 2] + o["c"][1]) for i in face]
            u, v = [o["uv"][2 * i] for i in face], [o["uv"][2 * i + 1] for i in face]
            assert _matches(u, _fractions(pts, g)), b["tag"]                        # u: 0..1 along the board
            assert _matches(v, _fractions(pts, (-g[1], g[0]))), b["tag"]            # v: 0..1 straight across it
            assert min(v) == pytest.approx(0, abs=TOL) and max(v) == pytest.approx(1, abs=TOL), b["tag"]   # not one row of the texture


@pytest.mark.parametrize("name", JOBS)
def test_sides_run_along_the_board_and_up_the_height(name):
    _, _, quads, out = _job(name)
    for b, o in zip(quads, out):
        P, uv = o["pos"], o["uv"]
        top_u = {(P[3 * i], P[3 * i + 2]): uv[2 * i] for i in range(6)}
        for i in range(12, 36):
            assert uv[2 * i + 1] == (1 if P[3 * i + 1] > 0 else 0), b["tag"]               # v up the height
            assert uv[2 * i] == pytest.approx(top_u[(P[3 * i], P[3 * i + 2])], abs=TOL), b["tag"]   # u as on the top: the grain wraps the edge


@pytest.mark.parametrize("name", JOBS)
def test_mitered_pieces_take_the_along_u_grain_in_their_own_material(name):
    _, data, quads, out = _job(name)
    for b, o in zip(quads, out):
        m = data["materials"][b["mat"]]
        assert o["key"].startswith("q|"), b["tag"]
        if m.get("grain"):
            rep = max(1, math.floor(max(b["x1"] - b["x0"], b["y1"] - b["y0"]) / 8 + 0.5))     # (Math.round)
            assert o["map"] == {"vertical": False, "repeat": [rep, 1]}, b["tag"]
        elif m.get("pattern"):
            assert o["map"]["vertical"] is False, b["tag"]
    # among them a border long in y: it took the vertical grain, crossways to its u
    assert any(b["y1"] - b["y0"] > b["x1"] - b["x0"] and data["materials"][b["mat"]].get("grain") for b in quads)


def test_the_box_path_keeps_its_grain(prentice):
    # a breaker (a plain border long in y) keeps the vertical grain; a mitered border's box twin (the same texture) gets a
    # material of its own, so the miter's double-sided material stays on the miter
    page, data, quads, out = prentice
    brk = next(b for b in data["boxes"] if b["kind"] == "border" and not b.get("quad") and b["y1"] - b["y0"] > b["x1"] - b["x0"])
    q = next(b for b in quads if b["kind"] == "border" and b["x1"] - b["x0"] > b["y1"] - b["y0"])
    o_brk, o_twin = _run([brk, dict(q, quad=None)], data["materials"], page)
    assert o_brk["map"]["vertical"] is True and not o_brk["key"].startswith("q|")
    assert o_twin["key"] == out[quads.index(q)]["key"][2:]


def test_a_mitered_border_by_hand(prentice):
    page, data, _, _ = prentice
    # a 6' border down the deck's left side (long in y), 0.447' wide, both ends mitered at 45 degrees
    b = dict(kind="border", mat="border", tag="by hand", x0=10.0, x1=10.447, y0=0.0, y1=6.0, z0=1.0, z1=1.083, tone=0.0, rot=0.0,
             rot_axis="y", shape="box", quad=[[10.0, 0.0], [10.0, 6.0], [10.447, 5.553], [10.447, 0.447]])
    o = _run([b], data["materials"], page)[0]
    assert _top_uv(o) == {(10.0, 0.0): (0, 0), (10.0, 6.0): (1, 0), (10.447, 5.553): (0.9255, 1), (10.447, 0.447): (0.0745, 1)}
    assert o["map"] == {"vertical": False, "repeat": [1, 1]}        # it was the vertical grain, crossways to u


def test_a_piece_whose_box_runs_across_its_first_edge_by_hand(prentice):
    page, data, _, _ = prentice
    # the fallback: a 6" block (long in x) whose outline's first edge runs 0.6' across it, the far side 1.1', wider than the
    # block is long; the grain still runs along the block (its box), not along the first edge or the outline's longer way
    b = dict(kind="joist", mat="timber", tag="by hand", x0=0.0, x1=0.5, y0=0.0, y1=0.125, z0=0.5, z1=1.0, tone=0.0, rot=0.0,
             rot_axis="y", shape="box", quad=[[0.0, 0.0], [0.0, 0.6], [0.5, 1.1], [0.5, 0.0]])
    o = _run([b], data["materials"], page)[0]
    assert _top_uv(o) == {(0.0, 0.0): (0, 0), (0.0, 0.6): (0, 0.5455), (0.5, 1.1): (1, 1), (0.5, 0.0): (1, 0)}
    # the same block turned 90 degrees about the vertical (its box's x now runs along plan y): the grain turns with it
    b2 = dict(b, rot=math.pi / 2, rot_axis="z", quad=[[0.0, 0.0], [-0.6, 0.0], [-1.1, 0.5], [0.0, 0.5]])
    o2 = _run([b2], data["materials"], page)[0]
    assert _top_uv(o2) == {(0.0, 0.0): (0, 0), (-0.6, 0.0): (0, 0.5455), (-1.1, 0.5): (1, 1), (0.0, 0.5): (1, 0)}
