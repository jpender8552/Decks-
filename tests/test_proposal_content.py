"""The client proposal's content: facts-only price words, the product facts and the makers' warranty words, the schedule from
the engine's day plan with the payments, the materials table, what the price does not include, who to call, the box steps
that wrap a corner read as one step for the client (the crew documents keep both names), page numbers and the 3D link."""
import html as _html
import json
import re
from datetime import date
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff.spec import DeckSpec

ROOT = Path(__file__).resolve().parent.parent
DATE = "October 28, 2026"                    # the document's date; the price holds 30 days from it


def _prentice(**extras):
    d = json.load(open(ROOT / "jobs/prentice_centennial.json"))
    d["extras"].update(extras)
    return d


def _visible(h: str) -> str:
    h = re.sub(r"<(script|style)\b.*?</\1>", "", h, flags=re.S)
    h = re.sub(r"data:[a-z]+/[a-z+.-]+;base64,[A-Za-z0-9+/=]+", "", h)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h)))


@pytest.fixture(scope="module")
def prentice():
    return run(DeckSpec.from_dict(_prentice()))


def test_quote_price_words_and_product_facts(prentice):
    from decktakeoff.report import quote_markdown, client_allocation
    t, _, p = prentice
    q = quote_markdown(t, p, DATE)
    for good in (f"**Financed price: ${p.retail:,.0f}**", f"120 monthly payments of ${p.monthly:,.0f} at 6.99% APR (10 years)",
                 "Also available with approved credit: 12 or 18 months with no payments", f"**Check or ACH price: ${p.sell:,.0f}**",
                 "% less than the financed price", "applies to payment by check or ACH", "This price holds through November 27, 2026.",
                 'TimberTech Impression Rail Express, vertical aluminum balusters, White, 36"; TimberTech Reserve Antique Leather drink rail between the posts',
                 'Diamond Pier DP-50 foundations with 50" steel pins — precast concrete heads, no poured concrete',
                 'ProWood TrueFrame 2x10 (#1 Southern Yellow Pine, pressure-treated for ground contact) at 12" on center',
                 "Grooved boards in the field; square-shouldered boards on the picture frame, dividers and stair treads",
                 "| Fascia and risers | James Hardie trim (Hardie Trim), ColorPlus Arctic White, on the fascia and every riser. |",
                 "TimberTech 30-year limited product warranty and 30-year limited fade & stain warranty (residential; prorated from year 11; labor not covered)",
                 "5 matte white LED riser lights (3 in the center stair, 2 in the left box step)",
                 "| 5 LED riser lights — 3 in the center stair, 2 in the left box step — included at no charge | $0 |",
                 "| Center stair + Left box step (wraps the corner) |", "- Left box step (wraps the corner): 2 risers",
                 "| Not included | Resetting the brick border along the left side about 5\" lower for the new box steps. A new outdoor outlet"):   # the job's own words, a sentence each
        assert good in q, good
    for bad in ("Total investment", "savings", "no money down", "about $", "Numbers hold", "modern top rail", "no excavation", "lifetime",
                "Left box step — left side", "Left box step — front angle", "(811)", "HardieTrim fascia around the frame", "drink rail on top"):
        assert bad not in q, bad
    assert sum(v for _, v in client_allocation(t, p)) == sum(v for _, v in p.allocation) == p.sell     # the client's words, the same numbers


def test_the_crew_documents_keep_both_box_step_names(prentice):
    from decktakeoff.report import takeoff_markdown, stair_groups, stair_rows
    t, flags, _ = prentice
    md = takeoff_markdown(t, flags)
    assert "Left box step — left side" in md and "Left box step — front angle" in md
    assert [g["name"] for g in stair_groups(t)] == ["Center stair", "Left box step (wraps the corner)"]
    assert stair_rows(t)[1] == ("Left box step (wraps the corner)", "2 risers at 6-3/16\", 6'-1\" along the left side and 5'-8\" along the front angle")


def test_schedule_from_the_day_plan_payments_and_the_date_the_price_holds(prentice):
    from decktakeoff.report import engine_timeline, payment_schedule, price_holds_through
    from decktakeoff.page import _NOT_FOR_CLIENT
    t, _, p = prentice
    tl = engine_timeline(t)
    rows = tl["rows"]
    assert tl["title"] == f"{rows[-1]['last_day']} working days on site, weather permitting" and 12 <= rows[-1]["last_day"] <= 16
    frame = next(r for r in rows if r["title"].startswith("Frame"))
    rail = next(r for r in rows if "Impression Rail Express" in r["title"])
    lights = next(r for r in rows if r["title"].startswith("Low-voltage lighting"))
    assert "wire for the lights" in frame["title"] and lights["first_day"] > rail["last_day"]     # rough-in with the frame, fixtures after the rail
    assert rows[-1]["title"].endswith("end of construction") and "modern top rail" not in rail["title"]
    assert not any(_NOT_FOR_CLIENT.search(x) for x in [r["title"] for r in rows] + [tl["precon"]["text"], tl["title"]])
    pays = payment_schedule(p.sell)
    assert [s_ for s_, _, _ in pays] == ["10%", "40%", "40%", "10%"] and sum(a for _, _, a in pays) == round(p.sell)
    assert payment_schedule(45008) == [("10%", "At signing", 4501), ("40%", "At material order", 18003), ("40%", "Frame complete", 18003),
                                       ("10%", "End of construction", 4501)]
    for s_ in (DATE, "Oct 28, 2026", "28 October 2026", "2026-10-28", "Revised Oct. 28, 2026"):
        assert price_holds_through(s_) == "November 27, 2026", s_
    assert price_holds_through(date(2026, 12, 15)) == "January 14, 2027"


def test_materials_and_the_makers_warranty_words(prentice):
    from decktakeoff.report import materials_rows
    from decktakeoff.catalog import (RAIL_WARRANTY, LIGHT_WARRANTY, HARDIE_TRIM_WARRANTY, FASTENER_WARRANTY, TRUEFRAME_WARRANTY, DIAMOND_PIER_WARRANTY,
                                     decking_facts)
    t, _, _ = prentice
    rows = {r[0]: r for r in materials_rows(t)}
    assert list(rows) == ["Decking", "Hidden fasteners", "Face screws", "Fascia and risers", "Railing", "Drink rail", "Lighting", "Frame", "Posts", "Foundations",
                          "Connectors", "Ledger fasteners", "Ledger flashing", "Joist protection"]          # every component on the order, by name
    fasteners = [r for r in materials_rows(t) if r[0] in ("Hidden fasteners", "Face screws")]       # the owner's template rows, from the order
    assert [r[1] for r in fasteners] == ["TimberTech CONCEALoc", "TimberTech Cortex", "Starborn Cap-Tor xd"]
    assert [r[3] for r in fasteners] == [FASTENER_WARRANTY, FASTENER_WARRANTY, ""] and "25-year" in FASTENER_WARRANTY     # TimberTech's fastener warranty; Starborn's: none downloaded
    assert fasteners[1][2] == "Screws with color-matched plugs on the picture frame, dividers and stair treads" and fasteners[2][2] == "Color-matched screws at the first field row"
    assert rows["Frame"][3] == TRUEFRAME_WARRANTY and rows["Foundations"][3] == DIAMOND_PIER_WARRANTY     # the makers' own (ProWood, Pin Foundations)
    assert rows["Posts"][1:3] == ("6x6 rough-sawn Douglas fir #1", "11 posts on Simpson ABA66RZ post bases")
    assert rows["Ledger fasteners"][1:3] == ("FastenMaster LedgerLOK", "Structural screws through the ledger into the house framing; Simpson DTT1Z lateral ties")
    assert rows["Ledger flashing"][1] == "Grace Vycor Plus membrane + galvanized L-flashing"            # as the order buys them
    assert rows["Joist protection"][1:3] == ("Nichigo G-Tape 3035", '2" tape on every joist, 4" on the rims')
    assert rows["Lighting"][1:3] == ("TimberTech LED lights", "9 post-cap lights; 5 matte white riser lights; a transformer with a photocell and timer")
    assert rows["Decking"][3] == decking_facts("Terrain+")["warranty"] == ("TimberTech 30-year limited product warranty and 30-year limited fade & stain "
                                                                         "warranty (residential; prorated from year 11; labor not covered)")
    assert rows["Railing"][3] == RAIL_WARRANTY["IRX Baluster"] and "25-year limited" in rows["Railing"][3]
    assert rows["Lighting"][3] == LIGHT_WARRANTY and "5-year limited" in LIGHT_WARRANTY and "matte white riser lights" in rows["Lighting"][2]
    assert rows["Fascia and risers"][1:] == ("James Hardie trim (Hardie Trim), ColorPlus Arctic White", "On the fascia and every riser", HARDIE_TRIM_WARRANTY + ", on the fascia")
    assert "30-year limited warranty (substrate)" in HARDIE_TRIM_WARRANTY and "ColorPlus 15-year limited finish" in HARDIE_TRIM_WARRANTY
    assert rows["Drink rail"][1:3] == ("TimberTech Reserve, Antique Leather", "Between the posts")
    assert rows["Frame"][1] == "ProWood TrueFrame 2x10" and rows["Foundations"][2].endswith("precast concrete heads, no poured concrete")
    assert not any("lifetime" in w_.lower() for w_ in RAIL_WARRANTY.values())


def _job(name):
    return run(DeckSpec.from_dict(json.load(open(ROOT / f"jobs/{name}.json"))))


@pytest.mark.parametrize("job, beams", [("glengarry_1_fulton_existing", "three 6x12 Douglas fir drop beams"),
                                        ("parkview_deck", "two doubled 2x10 pressure-treated SYP drop beams"),
                                        ("summit_point_deck", "two doubled 2x10 pressure-treated SYP drop beams"),
                                        ("deck_20x20_castlerock", "two 4x12 Douglas fir drop beams"),
                                        ("lansing_englewood", "a doubled 4x10 Douglas fir flush beam as the front rim")])
def test_the_frame_words_count_the_takeoffs_beam_lines(job, beams):
    from decktakeoff.report import frame_words, beam_line_words, materials_rows, quote_markdown
    t, _, p = _job(job)
    assert beam_line_words(t) == beams and beams in frame_words(t)              # every beam line, not the spec's beam list
    assert beams in {r[0]: r for r in materials_rows(t)}["Frame"][2]
    assert f"| Frame | {frame_words(t)} |" in quote_markdown(t, p, DATE)


def test_the_at_a_glance_names_the_posts_once():
    from decktakeoff.page import _reads_rows
    t, _, _ = _job("lansing_englewood")
    st = dict(_reads_rows(t, t.layout, t.summary))["Structure"]
    assert "6x6 Douglas fir #1 posts with 4x4 knee braces on 2 Diamond Pier foundations" in st and "braces posts" not in st
    assert "doubled 2x10 side rims; a doubled 4x10 Douglas fir flush beam as the front rim" in st
    t, _, _ = _job("glengarry_2_fulton_new")
    assert '8x8 Douglas fir #1 posts on 9 concrete caissons, 20" across and 3\'-2" deep' in dict(_reads_rows(t, t.layout, t.summary))["Structure"]


def test_the_day_plan_matches_the_frame_and_the_foundations():
    from decktakeoff.report import _schedule, quote_markdown
    t, _, p = _job("glengarry_1_fulton_existing")       # existing columns and caissons; one freestanding zone, the rest on ledgers
    days = " ".join(_schedule(t))
    assert "layout on the 9 existing columns and caissons, ledger set" in days and "beams set on the existing columns" in days and "Diamond Pier" not in days
    q = quote_markdown(t, p, DATE)
    assert any(l.item.startswith("FastenMaster LedgerLOK") for l in t.lines) and "freestanding" not in q
    assert "| Foundation | The 9 existing columns and caissons stay. |" in q                   # no new post bases under columns that stay
    t, _, _ = _job("glengarry_5_parapet_newposts")
    assert "layout, new post bases epoxy-set on the 9 existing caissons, ledger set" in " ".join(_schedule(t))
    t, _, p = _job("parkview_deck")
    q = quote_markdown(t, p, DATE)
    n = re.search(r"\| Foundation \| (\d+) Diamond Pier", q).group(1)
    assert f"layout, {n} Diamond Piers driven, ledger set" in q                    # the Foundation row's count
    t, _, _ = _job("jefferson_louisville")               # the old covers come out on day 1; no invented day rate for building the new ones
    days = _schedule(t)
    assert "old deck and roof covers out" in days[1] and not any("lean-to roof cover" in d for d in days)


def test_the_rail_by_its_maker_the_lights_by_the_order():
    from decktakeoff.report import materials_rows, quote_markdown, lights_of
    t, _, p = _job("deck_10x10")                         # Cinch
    rows = {r[0]: r for r in materials_rows(t)}
    assert rows["Railing"][1] == "Cinch Rail, Satin Black" and rows["Railing"][3] == "Cinch 15-year finish warranty"
    q = quote_markdown(t, p, DATE)
    assert "| Railing | Cinch Rail, Satin Black" in q and "TimberTech Cinch" not in q
    t, _, _ = _job("deck_16x14_seasalt")                 # Fulton
    assert {r[0]: r for r in materials_rows(t)}["Railing"][1:] == ("TimberTech Fulton Rail, Black", '36" high; 38 LF', "TimberTech 15-year limited warranty (residential)")
    t, _, p = _job("fillmore_centennial_all")            # two transformers on the order
    assert "low voltage, on two transformers, each with a photocell and timer" in quote_markdown(t, p, DATE)
    assert {r[0]: r for r in materials_rows(t)}["Lighting"][2].endswith("two transformers, each with a photocell and timer")
    t, _, p = _job("fillmore_centennial_yardstair")      # a handrail "one per flight" is not a light
    assert lights_of(t)["total"] == 0 and "| Lighting |" not in quote_markdown(t, p, DATE) and "Lighting" not in [r[0] for r in materials_rows(t)]


def test_every_component_on_two_levels_and_on_steel():
    from decktakeoff.report import materials_rows
    rows = {r[0]: r for r in materials_rows(_job("fillmore_centennial_all")[0])}
    assert "6x10 Douglas fir drop beams (2 under the lower level, 1 under the upper level)" in rows["Frame"][2] and "8x8 Douglas fir rough columns" in rows["Frame"][2]
    assert rows["Foundations"][1:3] == ("Concrete caissons", '9 caissons: 5 under the lower level, 24" across and 3\'-6" deep; '
                                        '4 under the upper level, 30" across and 3\'-6" deep, with rebar')
    rows = {r[0]: r for r in materials_rows(_job("jefferson_louisville")[0])}
    assert rows["Frame"][1] == "CEMCO cold-formed steel, G90" and rows["Roof covers"][2].startswith("Two lean-to covers on 6x6 posts")
    # the deck posts on their saddles, the ledger track's screws and the tension ties, from the order (the LedgerLOKs on it are the roof covers')
    assert rows["Posts"][2] == "3 posts on galvanized steel beam saddles, on 7 Diamond Pier foundations; 4 steel side brackets tie the beams to the roof covers' posts"
    assert rows["Ledger fasteners"][1:3] == ("Structural screws + Simpson DTT2Z", "Through the ledger track into the house rim board; 8 lateral-load tension ties")


def test_rail_words_drop_the_top_rail_under_a_drink_rail():
    from decktakeoff.report import rail_words, drink_rail_words
    s = DeckSpec.from_dict(_prentice())
    assert rail_words(s, "IRX Baluster") == "Impression Rail Express, vertical aluminum balusters"
    assert drink_rail_words(s) == "TimberTech Reserve Antique Leather drink rail between the posts"
    d = _prentice()
    d["railing"]["drink_rail"] = False
    assert rail_words(DeckSpec.from_dict(d), "IRX Baluster").endswith("modern top rail")


def test_an_option_says_where_its_riser_lights_go():
    from decktakeoff.page import _added_facts
    d0 = _prentice()
    d0["extras"].pop("lights")
    t0 = run(DeckSpec.from_dict(d0))[0]
    t1 = run(DeckSpec.from_dict(_prentice()))[0]
    assert dict(_added_facts(t0, t1))["Riser lights"] == "5 LED lights, 3 in the center stair, 2 in the left box step"
    d2 = _prentice()
    d2["extras"]["lights"].pop("riser_pick")
    t2 = run(DeckSpec.from_dict(d2))[0]
    assert dict(_added_facts(t0, t2))["Riser lights"] == f"{t2.lighting.n_riser} LED lights, one in every riser"     # the lighting plan's riser_where


def test_the_proposal_page(tmp_path):
    from decktakeoff.page import render_page, CLIENT_FOOT, _NOT_FOR_CLIENT
    from decktakeoff.report import payment_schedule
    from decktakeoff import proposal_look as PL
    r = render_page(DeckSpec.from_dict(_prentice()), str(tmp_path / "p"), mode="proposal", key="pren", name="Deck Replacement · 19105 E Prentice Cir",
                    render=False, viewer_url="https://example.invalid/3d", date_line=DATE)
    h = Path(r["html"]).read_text()
    txt, p = _visible(h), r["pricing"]
    assert "family=Saira+Semi+Condensed" in h and '--display:"Saira Semi Condensed"' in h          # the owner's headings
    assert PL.PP_WHEEL == PL.WHEEL and all(f'stroke="{c}"' in h for c in PL.WHEEL[:6])             # the owner's multi-color wheel
    for good in ("Two ways to pay", "Check or ACH price", "Financed price", "Price breakdown", "less than the financed price",
                 "Applies to payment by check or ACH", f"120 monthly payments of ${p.monthly:,.0f} at 6.99% APR (10 years)",
                 "Also available with approved credit: 12 or 18 months with no payments", "This price holds through November 27, 2026.",
                 CLIENT_FOOT, "Open the 3D model: https://example.invalid/3d", "Materials & warranties", "Every component, by name",
                 "TimberTech 25-year limited warranty", "TimberTech 5-year limited warranty",
                 "James Hardie 30-year limited warranty (substrate) + ColorPlus 15-year limited finish warranty",
                 "Not included Resetting the brick border along the left side", "Pavers or a pad at the foot of the center stair",
                 "working days on site, weather permitting", "Payments on the check or ACH price", "End of construction",
                 "Jade Pender", "Head of Deck Division", "303-550-9558", "9083 W. Parkview Dr", "Colorado natives. Family-owned since 1999.",
                 "Better Business Bureau rating", "Left box step (wraps the corner)", "5 LED riser lights 3 in the center stair, 2 in the left box step — included at no charge $0",
                 "Drink rail TimberTech Reserve Antique Leather", "Fascia and risers Hardie Trim Arctic White", 'joists 12" apart'):
        assert good in txt, good
    for _, _, a in payment_schedule(p.sell):
        assert f"${a:,.0f}" in txt
    for bad in ("Where every dollar goes", "Total investment", "savings", "no money down", "About $", "/month", "Numbers hold",
                "modern top rail", "no excavation", "all flush", "Left box step — left side", "Left box step — front angle",
                "sign-off", "close-out", "care guide", "jurisdiction", "skirt"):
        assert bad.lower() not in txt.lower(), bad
    assert not _NOT_FOR_CLIENT.search(txt)                 # no permit / inspection / vendor words ("weather permitting" is fine)
    # "lifetime" only where the maker says it (ProWood TrueFrame, Diamond Pier) — never for the rail or the decking
    assert re.findall(r"(?i)[a-z]+ (?:limited )?lifetime", txt) == ["ProWood lifetime", "performance limited lifetime"]
    assert h.count('class="pno"') >= 6                     # page numbers on the printed pages (FIT_JS fills them in)
    ids = ['id="g-what"', 'id="g-materials"', 'id="g-schedule"', 'id="g-investment"', 'id="g-company"']
    assert [h.index(i) for i in ids] == sorted(h.index(i) for i in ids)
    r2 = render_page(DeckSpec.from_dict(_prentice()), str(tmp_path / "q"), mode="proposal", key="pren", render=False, viewer_url="", date_line=DATE)
    assert "Open the 3D model" not in Path(r2["html"]).read_text()


def test_the_customer_cover_chips_and_tiles(tmp_path):
    from decktakeoff.page import render_page
    from decktakeoff import proposal_look as PL
    r = render_page(DeckSpec.from_dict(_prentice()), str(tmp_path / "c"), mode="customer", key="c", render=False, date_line=DATE)
    txt = _visible(Path(r["html"]).read_text())
    for good in ("Drink rail TimberTech Reserve Antique Leather", "Fascia and risers Hardie Trim Arctic White", 'joists 12" apart',
                 "less than the financed price", "Financed price", "120 monthly payments at 6.99% APR (10 years)", "This price holds through November 27, 2026."):
        assert good in txt, good
    for bad in ("all flush", "no money down", "Numbers hold"):          # (the drawing sheets here are drawings.py's own labels)
        assert bad.lower() not in txt.lower(), bad
    s = DeckSpec.from_dict(json.load(open(ROOT / "jobs/deck_20x20_castlerock.json")))       # a deck on beams keeps its joist spacing words
    t = run(s)[0]
    if t.layout.beam_lines:
        assert PL.telemetry(s, t.layout, 1, t)[3][1].startswith("joists @ ")


def test_the_roof_and_the_combined_documents_are_facts_only(tmp_path):
    from decktakeoff.page import render_page, render_combined
    d = json.load(open(ROOT / "examples/jason_ct.json"))
    d["geometry"]["louvered_roofs"] = [{"x0": 0.5, "x1": 10.5, "y0": 0, "y1": 8, "attach": "house", "price_per_sf": 175}]
    h = _visible(Path(render_page(DeckSpec.from_dict(d), str(tmp_path / "roof"), mode="addon", key="r", render=False, viewer_url="",
                                  date_line=DATE)["html"]).read_text())
    assert "This price holds through November 27, 2026." in h and "Financed price" in h and "with approved credit" in h
    for bad in ("no money down", "Numbers hold", "savings", "Total investment"):
        assert bad not in h, bad
    s = DeckSpec.from_dict(json.load(open(ROOT / "examples/jason_ct.json")))
    rd = tmp_path / "renders"
    rd.mkdir()
    c = _visible(Path(render_combined([dict(spec=s, renders_dir=str(rd), key="a", title="Deck A"), dict(spec=s, renders_dir=str(rd), key="b", title="Deck B")],
                                      str(tmp_path / "both"), key="both", name="Two decks", lede="", date_line=DATE)["html"]).read_text())
    assert "This price holds through November 27, 2026." in c and "less than the financed price" in c and "Also available with approved credit" in c
    assert "ProWood TrueFrame" in c and "True Frame Joist" not in c        # the Frame row in the homeowner's words (report.frame_words), as in render_page
    for bad in ("no money down", "saves 7%", "Numbers hold"):
        assert bad not in c, bad
