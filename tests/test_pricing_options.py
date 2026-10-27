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


def _timeline(n_days=3):
    rows = [dict(key=f"r{i}", option="base", label=f"work {i}", title=f"Work {i}", days=f"Day {i}", first_day=i, last_day=i, gantt_x=[i, i + 1])
            for i in range(1, n_days + 1)]
    return dict(title=f"{n_days} working days on site, weather permitting", rows=rows,
                precon=dict(label="Ordering", weeks=[2, 3], text="Ordering — about 2–3 weeks from signing", gantt_x=[0, 1]),
                schedule_lines=["Ordering — about 2–3 weeks from signing."] + [f"Day {i} — work {i}." for i in range(1, n_days + 1)])


def test_timeline_included_rows_confirm_box_and_brand(tmp_path):
    from decktakeoff.page import render_page
    from decktakeoff.report import quote_markdown
    d = json.load(open(ROOT / "examples/jason_ct.json"))
    d.setdefault("extras", {}).update(timeline=_timeline(), brand="cde",
                                      included=[{"title": "Up top", "text": "a row of the job's own"}, {"title": "Site", "text": ""}],
                                      confirm=["HOA approval. The HOA approves decks in writing.", "One more line"])
    s = DeckSpec.from_dict(d)
    t, _, p = run(s)
    q = quote_markdown(t, p)
    assert "1. Ordering — about 2–3 weeks from signing." in q and "4. Day 3 — work 3." in q            # the job's own schedule lines
    inc = q[q.index("## INCLUDED"):q.index("## PLAN")]
    assert inc.splitlines()[3] == "| Up top | a row of the job's own |" and "| Site |" not in inc
    opt = copy.deepcopy(d)
    opt["extras"]["timeline"] = _timeline(4)
    r = render_page(s, str(tmp_path / "p"), mode="proposal", key="t", render=False, viewer_url="",
                    options=[dict(key="o", number="Option 1", title="More", price=1000, spec=None, timeline=_timeline(4))])
    h = Path(r["html"]).read_text()
    assert 'class="gantt"' in h and "3 working days on site, weather permitting" in h and "4 working days on site, 1 more" in h
    assert "Still to confirm before we build" in h and "<b>HOA approval.</b>" in h
    assert "Colorado Deck Experts" in h and "Colorado Deck Experts · a GS Exterior Experts company" in h
    bad = copy.deepcopy(d)
    bad["extras"]["timeline"]["rows"][0]["title"] = "City inspection"
    import pytest
    with pytest.raises(ValueError):
        render_page(DeckSpec.from_dict(bad), str(tmp_path / "b"), mode="proposal", key="t", render=False, viewer_url="")


def test_footings_and_rail_words_follow_the_spec():
    import warnings
    from decktakeoff.report import quote_markdown, rail_words, foundation_words, timeline_of
    d = json.load(open(ROOT / "examples/eagles_nest.json"))         # a caisson job
    s = DeckSpec.from_dict(d)
    t, _, p = run(s)
    assert foundation_words(t)[1] == "caissons" and "Diamond Pier" not in quote_markdown(t, p)
    d["extras"] = dict(d.get("extras") or {}, timeline=dict(_timeline(), schedule_lines=["Day 1 — Diamond Pier footings driven."]))
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        assert timeline_of(DeckSpec.from_dict(d)) is None            # a timeline written for Diamond Piers stays out of a caisson job
    r = copy.deepcopy(d)
    r["railing"].update(drink_rail=True, drink_rail_mount="over")
    for sysname in ("IRX Baluster", s.railing.system):
        assert "modern top rail" not in rail_words(DeckSpec.from_dict(r), sysname)
