"""Pricing mechanics and the option / add-on documents: a deck sold per SF, options as engine deltas against it, the louvered
roof's own price, option blocks in the proposal, the internal basis table, the roof's own document."""
import copy
import json
import re
from pathlib import Path

from decktakeoff import run
from decktakeoff.spec import DeckSpec
from decktakeoff.pricing import option_delta, price_louvered, fixed_terms

ROOT = Path(__file__).resolve().parent.parent


def _eagles():
    return json.load(open(ROOT / "examples/eagles_nest.json"))


def test_sell_per_sf_scales_the_price_and_options_stay_engine_deltas():
    d = _eagles()
    t0, _, p0 = run(DeckSpec.from_dict(d))
    d2 = copy.deepcopy(d)
    d2["extras"]["sell_per_sf"] = 175
    t2, _, p2 = run(DeckSpec.from_dict(d2))
    assert p2.sell == round(175 * t2.layout.deck_sf)
    assert sum(v for _, v in p2.allocation) == p2.sell
    assert p2.per_sf == 175 and abs(p2.options_gm - p0.gm) < 1e-9          # options at the job margin, not the per-SF one
    assert [o.check for o in p2.options] == [o.check for o in p0.options]
    d3 = copy.deepcopy(d2)
    d3["extras"]["sell_per_sf"] = {"rate": 175, "options_gm": "effective"}
    p3 = run(DeckSpec.from_dict(d3))[2]
    assert abs(p3.options_gm - p3.gm) < 1e-9


def test_option_delta_against_a_per_sf_deck_prices_from_cost():
    d = _eagles()
    d["extras"]["sell_per_sf"] = 175
    d_opt = copy.deepcopy(d)
    d_opt["railing"]["drink_rail"] = False
    p, q = run(DeckSpec.from_dict(d))[2], run(DeckSpec.from_dict(d_opt))[2]
    assert q.sell == p.sell                                   # the rate alone says the option is worth $0
    c, f, m = option_delta(p, q)
    assert c == round((q.work - p.work) / (1 - p.options_gm)) and c < 0 and f == round(c / 0.93) and m < 0
    p_plain = run(DeckSpec.from_dict(_eagles()))[2]
    assert option_delta(p_plain, p_plain) == (0, 0, 0)


def test_louvered_roof_price_is_its_own():
    spec = DeckSpec.from_dict(json.load(open(ROOT / "examples/jason_ct.json")))
    ap = price_louvered(spec, {"x0": 0, "x1": 20, "y0": 0, "y1": 10, "price_per_sf": 175})
    assert (ap.sell, ap.retail, round(ap.monthly)) == (35000, 37634, 437) and ap.sf == 200
    assert price_louvered(spec, {"x0": 0, "x1": 20, "y0": 0, "y1": 10, "price": 30000}).sell == 30000
    assert fixed_terms(spec, 1000)[:2] == (1000, 1075)


def test_option_blocks_summary_viewer_link_and_internal_basis(tmp_path):
    from decktakeoff.page import render_page
    d = json.load(open(ROOT / "examples/jason_ct.json"))
    base = DeckSpec.from_dict(d)
    d_opt = copy.deepcopy(d)
    d_opt["railing"]["color"] = "White"
    options = [dict(key="rail", number="Option 1", title="White rail", spec=DeckSpec.from_dict(d_opt)),
               dict(key="pad", number="Option 2", title="Concrete pad", price=2400, addons=[dict(label="Sealer", price=300)])]
    r = render_page(base, str(tmp_path / "p"), mode="proposal", key="t", render=False, options=options, viewer_url="https://example.invalid/3d")
    h = Path(r["html"]).read_text()
    assert h.count('class="optblock"') == 2 and "The deck with every option" in h and "+$2,400" in h and "+$300" in h
    assert "const D = " not in h and "https://example.invalid/3d" in h          # the link, not the embedded viewer
    r = render_page(base, str(tmp_path / "i"), mode="internal", key="t", render=False, options=options)
    h = Path(r["html"]).read_text()
    assert "Options in the proposal" in h and "owner-set price" in h and "engine delta" in h


def test_roof_document(tmp_path):
    from decktakeoff.page import render_page
    d = json.load(open(ROOT / "examples/jason_ct.json"))
    d["geometry"]["louvered_roofs"] = [{"x0": 0.5, "x1": 10.5, "y0": 0, "y1": 8, "attach": "house", "price_per_sf": 175,
                                        "screens": [{"side": "front"}]}]
    r = render_page(DeckSpec.from_dict(d), str(tmp_path / "roof"), mode="addon", key="r", render=False, viewer_url="")
    h = Path(r["html"]).read_text()
    assert r["pricing"]["roof"]["sell"] == 14000 and r["pricing"]["screens"]["estimate"] is True
    assert "$14,000" in h and "Size and placement" in h and "<svg" in h and "Motorized screens" in h
    assert not re.search(r"ESTIMATE|estimate|internal", re.sub(r"<(script|style)\b.*?</\1>", "", h, flags=re.S))
