"""The internal documents: no pricing in the takeoff + build set or the supplier take-off, the cost stack as Jade's one or two
pages (the sell, the stack, the margin bridge, the labor with the owner's cut in its parts), print margins with a running
footer, titles that never run off the page, and the permit set's render pages as titled sheets."""
import json, re, html, shutil, subprocess
from pathlib import Path
import pytest
from decktakeoff import run
from decktakeoff.spec import DeckSpec
from decktakeoff.page import render_page, render_permit_set, _pct, _m, _h1, _no_money, _money_clauses

ROOT = Path(__file__).resolve().parent.parent
PRENTICE = "jobs/prentice_centennial.json"


def _spec(job, **extras):
    d = json.load(open(ROOT / job))
    d.setdefault("extras", {}).update(extras)
    return DeckSpec.from_dict(d)


def _text(page_html):
    t = re.sub(r"<(script|style)\b.*?</\1>", "", page_html, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def _cost(tmp_path, job, sub="c", **extras):
    s = _spec(job, **extras)
    return s, run(s)[2], _text(Path(render_page(s, str(tmp_path / sub), mode="cost", key="t", render=False)["html"]).read_text())


def _browser():
    from decktakeoff.render import _chromium
    if not _chromium() or not shutil.which("pdfinfo"):
        pytest.skip("no Chromium / pdfinfo")
    from playwright.sync_api import sync_playwright
    return _chromium(), sync_playwright


@pytest.mark.parametrize("job", [PRENTICE, "jobs/deck_16x14_seasalt.json", "jobs/lansing_englewood.json", "jobs/parkview_deck.json",
                                 "jobs/fillmore_centennial_yardstair_alt.json"])
def test_takeoff_and_supplier_carry_no_pricing(tmp_path, job):
    """A rail at its $/LF, a sold job, a quoted order, flags with dollar figures: no dollar figure, price, margin or financing in either."""
    s = _spec(job)
    for mode in ("internal", "supplier"):
        h = Path(render_page(s, str(tmp_path / mode), mode=mode, key="t", render=False)["html"]).read_text()
        txt = _text(h)
        for bad in ("$", "Check or ACH", "Financed", "Gross profit", "rate card", "The stack", "The quote"):
            assert bad not in txt, (job, mode, bad)
        assert '<body class="doc">' in h and "@page doc" in h and 'counter(pages)' in h      # margins + the running footer
        assert ("Decks &amp; Docks Take-off + Build Set</title>" if mode == "supplier" else "Takeoff + Build Set</title>") in h
        if "yardstair_alt" in job and mode == "internal":      # the takeoff prints the flag without its figure, the facts kept
            assert "the ADA kit + 1 extension kit (AZTIXADAPREKB). With Option 3" in txt


@pytest.mark.parametrize("job", ["jobs/fillmore_centennial_yardstair_alt.json", "jobs/fillmore_centennial_all.json"])
def test_takeoff_flags_lose_their_figures_not_their_facts(job):
    """_no_money cuts the dollar sub-phrases only: clauses split outside parentheses, parentheses stay paired, nothing else goes."""
    t, flags, p = run(_spec(job))
    out = {}
    for f in flags:
        g, had = _no_money(f)
        assert "$" not in g.text + (g.ref or "") and g.text.count("(") == g.text.count(")"), g.text
        if not had:
            assert g is f
            continue
        assert g.text.endswith("Its cost note is in the cost stack.") and "$" in _money_clauses(f.text)
        out[f.topic] = g.text
    assert "Demo labor is the card's rate on the 750 SF existing deck; the 9 brick columns come out with it (owner:" in out["demo"]
    assert "engineer's detail required (R507.9.1.2); fallback free-standing (structure.md v3)." in out["ledger"]
    assert "use-tax deposit 2.75% on 50% of valuation at issuance; plan review 5 business days for residential alterations." in out["site"]
    if "yardstair_alt" in job:
        assert "Flight 2's handrail is 9.1' long: the ADA kit + 1 extension kit (AZTIXADAPREKB). With Option 3 (the roof):" in out["yard stair"]
    else:
        assert "the owner's price for the front + right end together (split by width); the left end stays open over the inset stair." in out["screens"]
        assert out["louvered roof"].startswith("Confirm what the price includes: engineering + permit, electrical, LEDs / sensors, house flashing")
        assert '(24" caissons under the roof posts: owner question), downspout routing, screens (not included).' in out["louvered roof"]


def test_titles_wrap_and_never_run_off(tmp_path):
    """A short part of a title (24 characters or less) stays whole, a long part wraps; the CLI's default name (the long job line)
    drops its materials and sets smaller; at a phone's 375 px and on a Letter page nothing runs past the edge."""
    h = _h1("19105 E Prentice Cir · Deck Replacement · Centennial")
    assert h.count('class="nw"') == 3 and h.count("&nbsp;·") == 2 and "long" not in h
    assert 'class="nw"' not in _h1("19105 E Prentice Cir — ground-level deck replacement, 34'-6\" double octagon")
    s = _spec(PRENTICE)
    assert 'class="long"' in _h1(s.job) and "TimberTech" not in _h1(s.job) and 'class="nw"' not in _h1(s.job)
    chrome, sync_playwright = _browser()
    pages = [render_page(s, str(tmp_path / m), mode=m, key="t", render=False)["html"] for m in ("cost", "internal")]
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
        for path in pages:
            for w, media in ((375, "screen"), (816, "print")):
                pg = b.new_page(viewport={"width": w, "height": 900})
                pg.route("**/*", lambda rt: rt.abort() if rt.request.url.startswith("http") else rt.continue_())
                pg.goto("file://" + path, wait_until="domcontentloaded")
                pg.emulate_media(media=media)
                m = pg.evaluate("() => { const h = document.querySelector('header.band h1'); return [document.documentElement.scrollWidth, innerWidth, h.scrollWidth, h.clientWidth]; }")
                assert m[0] <= m[1] and m[2] <= m[3], (path, w, media, m)
                pg.close()
        b.close()


def test_cost_stack_is_the_compact_document(tmp_path):
    s = _spec(PRENTICE, labor_adjust=-179.4, under_3ft_credit=True)        # the owner's $1,000 labor cut (since put back on the job)
    t, _, p = run(s)
    r = render_page(s, str(tmp_path / "c"), mode="cost", key="t", render=False)
    h = Path(r["html"]).read_text()
    txt = _text(h)
    # no drawings, no build set, no order, no renders
    assert "<svg" not in h and 'class="sheets"' not in h and "<img" not in h and "The order" not in txt and "Build set" not in txt
    # the big check / ACH number, financed with the monthly and its terms, GP $ and GP % of the sell
    assert re.search(r'<span class="v">' + re.escape(_m(p.sell)) + "</span>", h)
    assert _m(p.retail) in txt and f"{_m(p.monthly)}/mo" in txt and "12 or 18 months" in txt
    gp = p.sell - round(round(p.materials_factored, 2) + round(p.tax, 2) + round(p.labor, 2) + round(p.gc, 2), 2)
    assert f"{_pct(gp / p.sell)} of the sell" in txt and abs(gp - p.gp) < 0.02
    # the margin bridge: 30% on the work, the free riser lights' cost, the blended margin — all from the pricing object
    assert f"{_pct(p.gm_job)} gross on the work" in txt and _pct(p.gm_job) == "30%"
    assert _m(-p.light_work, True) in txt and f"blends to {_pct(p.gm)}" in txt and _pct(p.gm) == "28.5%"
    # the labor: the card, then the owner's $1,000 cut in its two parts, footing to the labor in the price; the owner's own rate tagged
    assert "less the owner's $1,000 cut" in txt and "−$820.60" in txt and "$179.40 spread over the lines above in proportion" in txt
    assert f"Labor in the price {_m(p.labor, True)}" in txt and "Line Qty Unit Rate Ext" in txt and "Card rate" not in txt
    assert re.search(r"Lighting — install [^<]*<span class=\"cs-tag\">owner rate</span>", h) and "each scaled rate to 4 places" in txt
    # the stack in order, the allocation sums to the sell, the 40% floor with what it holds
    cost = round(p.materials_factored, 2) + round(p.tax, 2) + round(p.labor, 2) + round(p.gc, 2)
    order = ["Materials — the order at cost", "× 1.15 material factor", "Sales tax", "Labor — rate card", "Work — carries the margin",
             "Dumpster + portable toilet — at cost", f"Cost {_m(cost, True)}", "Sell — check or ACH"]
    pos = [txt.index(x) for x in order]
    assert pos == sorted(pos)
    assert sum(v for _, v in p.allocation) == p.sell
    assert f"At the 40% floor the sell would be {_m(p.sell_floor)} (the riser lights still free); this job is set at 30%, under the floor" in txt
    assert "labor at the rate card, less the owner's $1,000 cut, dumpster + portable toilet at cost. Internal" in txt


def test_cost_stack_other_jobs(tmp_path):
    """A rail at its $/LF reads as priced on its own; a sold job reads its sold price and its cost to build; an owner-set labor
    total reads as such; the floor note names only what the floor holds; no words for at-cost items a job does not have."""
    s, p, h = _cost(tmp_path, "jobs/deck_16x14_seasalt.json", "r")
    assert "is priced on its own" in h and "How the sell is set" in h
    s, p, h = _cost(tmp_path, "jobs/prentice_centennial_irx.json", "x")          # rail, benches, planter: a plural subject
    assert "are priced on their own" in h and "is priced on its own" not in h
    s, p, h = _cost(tmp_path, "jobs/lansing_englewood.json", "s")
    assert "Sold · check or ACH" in h and "Cost to build" in h and "How the sell is set" not in h
    s, p, h = _cost(tmp_path, "jobs/jefferson_louisville.json", "j")             # sold, nothing priced on its own
    assert f"scaled to the owner's ${s.extras.labor_total:,.0f} total" in h and f"Labor in the price {_m(p.labor, True)}" in h
    assert f"At the 40% floor the sell would be {_m(p.sell_floor)}." in h and "still at their price" not in h
    assert "both roof covers: posts, ledger, beam, rafters, sheathing, roofing, Hardie, set on the piers owner-set" in h
    assert "tear off the existing roof cover and haul estimate" in h
    s, p, h = _cost(tmp_path, "jobs/parkview_deck.json", "p")                    # no general conditions, a job rate on the rail
    assert p.gc == 0 and "general conditions" not in h.lower() and "at-cost items" not in h
    assert "Railing job rate 44 LF $50.00" in h and "Cost stack: materials at the order, tax, labor at the rate card. Internal" in h
    s, p, h = _cost(tmp_path, PRENTICE, "o", sell_override=47000)                # a sold price: the floor holds the free lights only
    assert f"At the 40% floor the sell would be {_m(p.sell_floor)} (the riser lights still free)." in h


@pytest.mark.parametrize("job", [PRENTICE, "examples/eagles_nest.json"])
def test_cost_stack_prints_on_two_pages_at_most(tmp_path, job):
    """Eagle's Nest carries 11 general-conditions lines and 8 options; a long table breaks with its header repeated."""
    _browser()
    r = render_page(_spec(job), str(tmp_path / "c"), mode="cost", key="t", render=False, pdf=True)
    pages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", r["pdf"]], capture_output=True, text=True).stdout).group(1))
    txt = subprocess.run(["pdftotext", r["pdf"], "-"], capture_output=True, text=True).stdout
    assert pages <= 2 and f"page {pages} of {pages}" in re.sub(r"\s+", " ", txt)


def test_permit_render_pages_are_titled_sheets(tmp_path):
    from PIL import Image
    imgs = []
    for n in ("yard", "iso"):
        f = tmp_path / f"{n}.jpg"
        Image.new("RGB", (140, 90), (120, 140, 90)).save(f)
        imgs.append((f"view {n}", str(f)))
    d = json.load(open(ROOT / PRENTICE)); d["stairs"] = []
    r = render_permit_set([dict(spec=DeckSpec.from_dict(d), title="Deck replacement")], str(tmp_path / "p"), key="k", name="19105 E Prentice Cir · Deck Replacement",
                          renders={"Deck": imgs}, date_line="October 28, 2026")
    h = Path(r["html"]).read_text()
    pages = re.findall(r'<div class="sheet-page" id="s-r\d+">(.*?)</svg></div>', h, flags=re.S)
    assert len(pages) == 2 and "A-001.1–.2" in h
    for k, pg in enumerate(pages, 1):
        assert f"Deck replacement · A-001.{k} · Isometric · renders" in pg and "PERMIT SET" in pg and f"{k} of 2" in pg
        assert "Design intent per 2021 IRC R507 prescriptive" in pg and '<image href="r/k-' in pg       # the drawing sheets' footer
    assert "counter(pages)" in h and "$" not in _text(h)


def test_permit_page_rule_yields_to_a_later_sheet_size(tmp_path):
    """render_permit_set's @page (Letter landscape, the running footer) is not !important, so a wrapper's later @page wins:
    messner_ext prints page.html at 24x36 ARCH D with margin 0, and no GSX footer lands on its sheets."""
    chrome, sync_playwright = _browser()
    d = json.load(open(ROOT / PRENTICE)); d["stairs"] = []
    r = render_permit_set([dict(spec=DeckSpec.from_dict(d), title="Deck replacement")], str(tmp_path / "p"), key="k", name="19105 E Prentice Cir · Deck Replacement",
                          date_line="October 28, 2026")
    page = Path(r["html"]).read_text()
    assert "!important" not in "".join(re.findall(r"@page[^{]*\{[^}]*", page))
    (tmp_path / "w.html").write_text(page.replace("</head>", "<style>@media print{@page{size:36in 24in;margin:0;}}</style></head>", 1))
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1400, "height": 1000})
        pg.route("**/*", lambda rt: rt.abort() if rt.request.url.startswith("http") else rt.continue_())
        pg.goto("file://" + str(tmp_path / "w.html"), wait_until="domcontentloaded")
        pg.emulate_media(media="print")
        pg.pdf(path=str(tmp_path / "w.pdf"), width="36in", height="24in", print_background=True, prefer_css_page_size=True)
        b.close()
    info = subprocess.run(["pdfinfo", str(tmp_path / "w.pdf")], capture_output=True, text=True).stdout
    assert re.search(r"Page size:\s+2592 x 1728 pts", info), info
    assert not re.search(r"page \d+ of \d+", subprocess.run(["pdftotext", str(tmp_path / "w.pdf"), "-"], capture_output=True, text=True).stdout)
