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
