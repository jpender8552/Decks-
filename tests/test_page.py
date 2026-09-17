"""The job page is one template for every job: the same sections in the same order, internal and customer, from any spec."""
import json, re
from pathlib import Path
from decktakeoff.spec import DeckSpec
from decktakeoff.page import render_page

ROOT = Path(__file__).resolve().parent.parent
INTERNAL = ["Design reads", "Site &amp; code flags", "The order", "Fastener &amp; connector schedule", "The stack", "The quote", "Renders", "Isometrics", "Exploded", "Drawing set", "Build set", "3D model"]
CUSTOMER = ["At a glance", "What it is", "Renders", "Isometrics", "Exploded views", "Structure", "Drawing set", "Materials", "Fastening", "How it", "Investment", "3D model"]


def _kickers(html):
    return [re.sub(r"<[^>]+>", "", k).strip() for k in re.findall(r'<h2 class="kicker[^"]*"[^>]*>(.*?)</h2>', html)]


def _order_ok(kickers, expected):
    pos = [next(i for i, k in enumerate(kickers) if k.startswith(e)) for e in expected]
    return pos == sorted(pos)


def test_internal_and_customer_pages_same_template(tmp_path):
    for job in ("examples/jason_ct.json", "jobs/parkview_deck.json"):
        spec = DeckSpec.from_dict(json.load(open(ROOT / job)))
        r = render_page(spec, str(tmp_path / "i"), mode="internal", key="t", render=False)
        html = Path(r["html"]).read_text()
        assert _order_ok(_kickers(html), INTERNAL), job
        r = render_page(spec, str(tmp_path / "c"), mode="customer", key="t", render=False)
        html = Path(r["html"]).read_text()
        assert _order_ok(_kickers(html), CUSTOMER), job
        txt = re.sub(r"<script.*?</script>", "", html, flags=re.S)
        for bad in ("internal", "rate card", "GM", "Jade", "STOP", "ENGINEER"):
            assert bad not in txt, (job, bad)
        assert 'class="cover"' in html and "Prepared for" in html


def test_switchback_stair_flights():
    """A two-flight stair: the riser count is the spec's, treads drop one per flight, and the landing guard is counted."""
    import json
    from decktakeoff import run
    from decktakeoff.spec import DeckSpec
    from decktakeoff.engineering import stair_geometry
    g = stair_geometry(96, 48, True, 11.0, flights=[7, 6])
    assert g.risers == 13 and g.treads == 11 and len(g.flights) == 2
    assert [f.risers for f in g.flights] == [7, 6] and [f.treads for f in g.flights] == [6, 5]
    assert abs(g.flights[0].run_in - 66.0) < 1e-6 and abs(g.riser_in - 96 / 13) < 0.01
    sp = DeckSpec.from_dict(json.load(open("jobs/glengarry_2_fulton_new.json")))
    t, flags, p = run(sp)
    st = t.layout.stairs[0]
    assert st.geo.risers == 13 and st.flight_rails == [1, 2] and st.stair_posts == 6
    assert st.landing_rail_lf == 21.0 and st.landing_posts >= 3
    items = [l.item for l in t.lines if l.category == "Stairs"]
    assert any("landing guard" in i and "LEVEL" in i for i in items)
    assert any("treads" in i for i in items)
    from decktakeoff.scene import build_scene
    S = build_scene(t.layout)
    treads = [b for b in S.boxes if b.tag and b.tag.startswith("tread")]
    assert len(treads) == 11
    assert sum(1 for b in S.boxes if b.tag == "landing footing") == 8
    # flight 2 runs back the other way (+y) and lands lower than flight 1
    f1 = [b for b in treads if "flight 1" in b.tag]; f2 = [b for b in treads if "flight 2" in b.tag]
    assert min(b.z1 for b in f2) < min(b.z1 for b in f1)
    assert max(b.x1 for b in f2) < min(b.x0 for b in f1)
