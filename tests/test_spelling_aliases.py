"""British spellings a job can still carry read the same after the American spelling pass: a grey louvered roof or screen
and a grey rail or Hardie chip take their gray tones (not the default black), the homeowner's roof lines turn British
words into American ones (case kept), and the color study's spec tool counts the yard model's neighbor houses under the
new "neighbors" key and the old "neighbours" one. The color tables keep one key per color."""
import ast
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from decktakeoff import louvered as lv
from decktakeoff import proposal_look as PL
from decktakeoff import run
from decktakeoff.page import _roof_scope, _us_words
from decktakeoff.spec import DeckSpec

ROOT = Path(__file__).resolve().parent.parent
RECT = dict(job="spelling test", geometry=dict(width_in=240, depth_in=144, size_mode="frame", height_in=96),
            railing=dict(system="IRX Baluster", sides=["left", "right", "front"]),
            decking=dict(collection="Vintage", color="English Walnut"))
ROOF = dict(x0=0, x1=20, y0=0, y1=12, price_per_sf=175, angle_deg=30)


def _spec(roof=None, **kw):
    d = copy.deepcopy(RECT)
    if roof is not None:
        d["geometry"]["louvered_roofs"] = [roof]
    for k, v in kw.items():
        d.setdefault(k, {}).update(v)
    return DeckSpec.from_dict(d)


# ------------------------------------------------------------------ the louvered roof and its screens
@pytest.mark.parametrize("name", ["grey", "Grey", "GREY", " grey ", "gray", "Gray"])
def test_grey_roof_and_screens_take_the_gray_tones(name):
    q = lv.resolve(dict(ROOF, color=name))
    assert q["hex"] == lv.HEX["gray"] == "#6b6e70"
    m = lv.materials(_spec(dict(ROOF, color=name, screens=[{"side": "front", "color": name}])))
    assert m[lv.MAT]["color"] == "#6b6e70" and m[lv.SCREEN_MAT]["color"] == "#55585a"
    assert m[lv.MAT]["label"] == "Suncoast gray powder-coat aluminum" and m[lv.SCREEN_MAT]["label"].endswith(" gray mesh")
    assert "gray powder-coated aluminum" in lv.scope_words(q)[0] and lv.option_name(q).endswith("motorized, gray")


def test_other_roof_colors_unchanged():
    assert lv.resolve(dict(ROOF, color="Black"))["hex"] == "#141416" and lv.resolve(dict(ROOF, color="Bronze"))["hex"] == "#4b3b2c"
    assert lv.resolve(dict(ROOF, color="sky blue"))["hex"] == "#141416"          # a name the table does not know: black, as before
    m = lv.materials(_spec(dict(ROOF, color="Linen", screens=[{"side": "front"}])))
    assert m[lv.MAT]["color"] == "#e9e3d3" and m[lv.SCREEN_MAT]["color"] == "#1b1c1e"   # screens default black
    assert lv.option_name(lv.resolve(dict(ROOF, color="Black"))).endswith("motorized, black")


def test_roof_page_lines_read_american():
    lines = _roof_scope(lv.resolve(dict(ROOF, color="Grey")))
    txt = " ".join(lines)
    assert "gray powder-coated aluminum" in txt and "centers" in txt and "around every zone" in txt
    assert not any(w in txt.lower() for w in ("grey", "centre", "colour", "aluminium"))


# ------------------------------------------------------------------ the proposal's rail and fascia chips
def test_rail_and_hardie_chips_accept_grey():
    t, _, _ = run(_spec(railing={"color": "Grey"}, extras={"hardie_skirt": "4/4 x 12 Iron Grey", "hardie_color": "Iron Grey"}))
    rows = {k: hx for k, _, hx in PL.materials(t.spec, t.layout)}
    assert rows["Rail"] == PL.RAIL_HEX["gray"] == "#7a7c7e"                      # not the black default
    assert rows["Fascia"] == PL.HARDIE_HEX["iron gray"]
    assert ("%g'" % t.layout.rail.rail_lf, "gray rail") in PL.telemetry(t.spec, t.layout, 4)
    t, _, _ = run(_spec(railing={"color": "White"}))
    assert {k: hx for k, _, hx in PL.materials(t.spec, t.layout)}["Rail"] == "#f1f0ea"


# ------------------------------------------------------------------ the homeowner's spelling of a line
@pytest.mark.parametrize("brit, us", [
    ('8" blades on 8" centres', '8" blades on 8" centers'),
    ("the centre stair, centred on the door, centre to centre", "the center stair, centered on the door, center to center"),
    ("Centre stair", "Center stair"),
    ("GREY", "GRAY"),
    ("Grey powder-coated aluminium", "Gray powder-coated aluminum"),
    ("colour-matched plugs, two colours", "color-matched plugs, two colors"),
    ("the neighbour's fence, the neighbours' houses", "the neighbor's fence, the neighbors' houses"),
    ("a 2.4 metre run", "a 2.4 meter run"),
    ("mitred at every corner, a mitre cut", "mitered at every corner, a miter cut"),
    ("a two-storey house, two storeys", "a two-story house, two stories"),
    ("fibre-cement trim", "fiber-cement trim"),
    ("on the centreline, toward the house", "on the centerline, toward the house"),
])
def test_us_words_converts_british_words(brit, us):
    assert _us_words(brit) == us


def test_us_words_leaves_american_text_and_keeps_its_other_rules():
    for s in ('8" blades on 8" centers', "gray, color, neighbor, miter, aluminum", "Centennial, CO", "a greyhound", ""):
        assert _us_words(s) == s
    assert _us_words("2 6x6 aluminum posts") == "Two 6x6 aluminum posts"
    assert _us_words("the gutter round every zone") == "the gutter around every zone"


# ------------------------------------------------------------------ the color study's spec tool (Fillmore tooling)
def _make_specs():
    sp = importlib.util.spec_from_file_location("make_specs", ROOT / "jobs/fillmore_site/tooling/colorstudy/make_specs.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


@pytest.mark.parametrize("key", ["neighbors", "neighbours"])
def test_make_specs_counts_neighbor_houses_under_either_key(tmp_path, capsys, key):
    ms = _make_specs()
    ms.HERE = tmp_path                                     # palettes.json beside the specs it writes
    (tmp_path / "palettes.json").write_text(json.dumps({"cream": {"house": {"siding": "#EFE8DB"}}}))
    job = dict(geometry=dict(furniture=[], house_model=dict(colors={}), site_model={key: [dict(rect=[0, 1, 0, 1]), dict(rect=[2, 3, 0, 1])]}),
               railing=dict(drink_rail=False), decking=dict(color="English Walnut"))
    (tmp_path / "job.json").write_text(json.dumps(job))
    ms.main(["--job", str(tmp_path / "job.json"), "--out", str(tmp_path / "specs")])
    out = capsys.readouterr().out
    assert "2 neighbor houses" in out and "neighbour houses" not in out
    assert json.loads((tmp_path / "specs" / "cream.json").read_text())["geometry"]["house_model"]["colors"]["siding"] == "#EFE8DB"


# ------------------------------------------------------------------ one key per color
@pytest.mark.parametrize("mod", ["louvered", "proposal_look", "page"])
def test_color_tables_have_one_key_per_color(mod):
    tree = ast.parse((ROOT / "decktakeoff" / f"{mod}.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            assert len(keys) == len(set(keys)), (mod, node.lineno, sorted(k for k in keys if keys.count(k) > 1))
