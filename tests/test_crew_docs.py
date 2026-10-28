"""Crew documents per the makers' rules — the Prentice job (jobs/prentice_centennial.json) and the jobs that take the other branches
(Jefferson's steel frame, Glengarry's zone-line breaker and engineered ledger, a deck without stairs, Fillmore's two levels): the
build set's steps, the drawing labels, details and schedules, and the flags say what TimberTech (decking guide REV 09/23, IRX and
IRX drink-rail guides, lighting), James Hardie (TR1509 09/25), Simpson and FastenMaster require — and none of the wrong statements.
Spacings and counts are read from the layout and the order, so the tests hold while the geometry and order groups change them."""
import copy
import html
import json
import re
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff.buildset import OFFICE_CHECK, _tread_supports, build_set, step_sheets
from decktakeoff.takeoff import inches_frac
from decktakeoff.drawings import (_LL_RULE, _hy, all_sheets, corner45, divider_groups, divider_offset, foot_block_bays, irx_posts, ledger_oc,
                                  ledger_oc_words, ledger_pieces, ledger_words, ledgerlok_len)
from decktakeoff.flags import tread_oc_max
from decktakeoff.scene import build_scene
from decktakeoff.spec import DeckSpec
from decktakeoff.takeoff import Line

ROOT = Path(__file__).parent.parent
EX = ROOT / "examples"


def _txt(svg: str) -> str:
    """A sheet's words in reading order, wrapped lines joined (a hyphen-broken word put back together)."""
    words = " ".join(html.unescape(re.sub(r"<[^>]+>", "", m)) for m in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S))
    return re.sub(r"-\s+", "-", re.sub(r"\s+", " ", words))


def _flat(st: dict) -> str:
    return " ".join(st["goes_in"] + [h for h in st["how"] if h] + st["check"])


def _spec(path: str, extras=None, **railing) -> DeckSpec:
    d = json.loads((ROOT / path).read_text())
    d.setdefault("railing", {}).update(railing)
    d.setdefault("extras", {}).update(extras or {})
    return DeckSpec.from_dict(d)


def _job(spec: DeckSpec, sheets: bool = False) -> dict:
    t, f, _ = run(spec, with_pricing=False)
    L = t.layout
    out = dict(t=t, f=f, L=L, steps=step_sheets(t, L))
    if sheets:
        out["sheets"] = {n: _txt(svg) for n, _, svg in all_sheets(L, t, f, build_scene(L))}
    return out


def _step(p: dict, start: str) -> dict:
    return next(s for s in p["steps"] if s["title"].startswith(start))


def _rail_lag(l) -> bool:
    """The order's IRX post lags — not the DTT1Z ties' 3/8" lag."""
    return "lag" in l.item.lower() and "3/8" in l.item and "6\"" in l.item and any(k in f"{l.item} {l.why or ''}".lower() for k in ("rail", "post", "irx"))


@pytest.fixture(scope="module")
def prentice():
    return _job(_spec("jobs/prentice_centennial.json"), sheets=True)


def test_steps_in_build_order(prentice):
    titles = [s["title"] for s in prentice["steps"]]
    i = {k: next(n for n, t_ in enumerate(titles) if t_.startswith(k)) for k in ("Frame", "Lighting rough-in", "Decking", "Rail", "Stairs", "Light fixtures", "HardieTrim fascia, risers and skirts")}
    assert i["Frame"] < i["Lighting rough-in"] < i["Decking"] < i["Rail"] < i["Stairs"] < i["Light fixtures"] < i["HardieTrim fascia, risers and skirts"] == len(titles) - 1
    assert "Lights" not in titles                                         # the one lights step is now two
    assert prentice["steps"][-1]["check"][-1] == "End of construction"
    assert [s["code"] for s in prentice["steps"]] == [f"T-4{k:02d}" for k in range(len(titles))]
    # every card's still ships with the pages: a deck under 30" drops the views from under it (page.render_page)
    assert prentice["L"].spec.geometry.height_in < 30 and not {s["still"] for s in prentice["steps"]} & {"under", "underiso", "structure-underiso"}
    assert _step(prentice, "Lighting rough-in")["still"] == "step5"


def test_hardie_trim_step_per_tr1509(prentice):
    hs = _step(prentice, "HardieTrim fascia")
    how = " ".join(hs["how"])
    for w in ("stair stringers (LSCZ)", "box-step frames (RSS)", "bare, taped rim", "nothing structural goes through the HardieTrim",
              "2\" min above soil or mulch", "1/4\" min above brick, pavers and treads", "never caulked",
              "2-1/2\" 16-ga 316SS ring-shank finish nails", "4 per 16\" on the fascia", "2 every 16\" on the stair skirts", "2 per stringer on the stair risers",
              "2 every 16\" on the box-step fronts and free ends", "1/2\" from the edges and 1\" from the ends", "snug through the laminate", "22.5-degree miters",
              "edge-seal every cut with the ColorPlus edge coater before the piece goes up", "G-Tape patch on the rim behind each miter",
              "factory edge down, 1/4\" open above each tread", "touch-up kit only", "dime-size", "above 40F", "Peel the laminate right after nailing", "Hardie blade",
              "vacuum", "stepped skirts both sides of the Center stair", "the box-step fronts and free ends (none at a mitered corner)",
              "the fascia on every rim side but sides 2 and 3 (the box steps' risers are the face there)"):    # the two box steps mitered into one: one free end each
        assert w in how, w
    assert "trim screw" not in how
    assert "HardieTrim gaps open: 1/4\" over treads/brick, 2\" over soil/mulch" in hs["check"]
    assert any("James Hardie Technical Services' written OK for HardieTrim as deck fascia and stair risers (not a listed use) before ordering — 800-942-7343" in c for c in hs["check"])
    nails = [l for l in prentice["t"].lines if "finish nail" in l.item.lower()]
    orders = [c for c in hs["check"] if c.startswith("Order:")]
    if not nails:                                                         # the order still lists trim screws
        assert any("ring-shank finish nails for the HardieTrim — not on the order" in c for c in orders)
    elif not any("ring" in l.item.lower() for l in nails):               # TR1509 p.3: stainless nails ring shank
        assert any(c.startswith("Order: ring-shank 316SS finish nails") for c in orders)
    else:
        assert not orders
    assert any("Deck fascia — HardieTrim" in g for g in hs["goes_in"]) and any("every riser (stairs)" in g for g in hs["goes_in"])
    every = " ".join(_flat(s) for s in prentice["steps"])
    assert "Skirts and fascia tight" not in every and "316SS trim screws" not in every and "pre-drilled, 316SS" not in every
    fl = next(f.text for f in prentice["f"] if f.topic == "hardie" and "TR1509 (09/25)" in f.text)
    assert "ring-shank finish nails, 1/2\" from the edges" in fl and "trim screws" not in fl


def test_hardie_on_a_steel_frame_takes_screws():
    """Jefferson (CEMCO track rim, hat-channel furring): TR1509 p.3 — screws or ET&F pins into steel, 3/4" from the edges, no finish nails."""
    j = _job(_spec("jobs/jefferson_louisville.json"))
    assert j["L"].spec.framing.system == "steel" and j["L"].spec.extras.hardie_skirt
    hs = _step(j, "HardieTrim")
    how = " ".join(hs["how"])
    assert "Fasten with color-matched 316SS trim screws (or ET&F pins) into the steel furring / track" in how and "3/4\" from the edges and 1\" from the ends" in how
    assert "finish nail" not in how.replace("no finish nails into steel", "") and "G-Tape" not in how
    assert not any("finish nail" in c for c in hs["check"]) and any(c.startswith("Screws 3/4\" from the edges") for c in hs["check"])
    fl = next(f.text for f in j["f"] if f.topic == "hardie" and "TR1509 (09/25)" in f.text)
    assert "trim screws (or ET&F pins) into the steel furring / track, 3/4\" from the edges" in fl and "finish nails" not in fl


def test_hardie_gaps_without_stairs():
    j = _job(_spec("jobs/deck_10x10.json"))
    assert j["L"].spec.extras.hardie_skirt and not j["L"].spec.stairs
    hs = _step(j, "HardieTrim fascia")
    assert hs["title"] == "HardieTrim fascia" and "HardieTrim gaps open: 1/4\" over brick/pavers, 2\" over soil/mulch" in hs["check"]
    assert "treads" not in " ".join(hs["how"] + hs["check"]) and "stair risers" not in " ".join(hs["check"])


def test_fascia_leaves_the_decking_step(prentice):
    dk = _step(prentice, "Decking")
    assert not any("HardieTrim" in g or "trim screw" in g or "finish nail" in g for g in dk["goes_in"])
    st = _step(prentice, "Stairs")
    assert not any("HardieTrim" in g or "finish nail" in g for g in st["goes_in"])
    assert "to the bare, taped rim before any HardieTrim goes on" in " ".join(st["how"])


def test_decking_fastening_rows_gaps_and_cortex(prentice):
    dk = _step(prentice, "Decking")
    how = " ".join(dk["how"])
    for w in ("one clip per board end", "the first field row against each front border and the last row at the house and the bay", "outer edge only, 1 per joist, 3/4\" from the edge",
              "pre-drilled 5/32\" (Cap-Tor xd)", "pre-drill every hole 7/32\" the full board depth", "setting tool in a drill, no impact driver", "pillars with the alignment guide",
              "2 per joist, block or stringer per board", "none within 3/4\" of an edge or end", "2 each side of every miter",
              "3/16\" at 32F and below, 1/8\" at 33-74F, 1/32\" at 75F and above", "3/16\" minimum at the house, the bay faces and the threshold", "cut and fasten each board the same day"):
        assert w in how, w
    assert "ONLY at: first row 1 per joist on the house edge" not in how
    assert any("877-275-2935" in c and "TOPLoc, 5/32\" pilot" in c for c in dk["check"])
    assert any(c.startswith("TimberTech's written OK for Cap-Tor xd on the first and last field rows") and OFFICE_CHECK.match(c) for c in dk["check"])
    chk = [f for f in prentice["f"] if f.severity == "CHECK"]
    assert any("Restricted Cortex Uses" in f.text and "877-275-2935" in f.text and "5/32\"" in f.text for f in chk)
    assert any(f.topic == "product" and "TOPLoc for Composite" in f.text and "Cap-Tor xd" in f.text for f in chk)
    # the maker's own screw for those rows is an office matter: never in a crew line or on a sheet (client and permit pages print both)
    for st in prentice["steps"]:
        assert not any("TOPLoc" in h for h in st["how"]), st["title"]
    for n in ("A-101", "D-501"):
        assert "TOPLoc" not in prentice["sheets"][n] and "TimberTech specifies" not in prentice["sheets"][n], n
    assert "End gaps at borders and breakers 3/16\"" in prentice["sheets"]["D-501"]          # the deck-edge detail carries the end gaps


def test_breakers_two_divider_joists_off_the_line(prentice):
    L = prentice["L"]
    assert _hy(divider_offset(L)) == "3-5/8\""                           # half a 5.36" breaker + its 3/16" end gap + half the joist
    assert divider_groups(L) == ([], ["DL/C", "DC/R"])                    # one outline field: no zone rims at the lines
    fr = " ".join(_step(prentice, "Frame")["how"])
    for w in ("two divider joists per breaker, centers 3-5/8\" each side of the divider line", "every field-board end bears a full 1-1/2\"",
              "the breaker board on 2x10 blocks @ 12\" OC between them", "one CONCEALoc clip per field-board end"):
        assert w in fr, w
    sh = prentice["sheets"]
    assert "2 divider joists 3-5/8\" each side · DL/C" in sh["S-101"] and "2 divider joists 3-5/8\" each side · DC/R" in sh["S-101"]
    assert "two divider joists per breaker" in sh["A-101"] and "2 divider joists 3-5/8\" off the line" in sh["D-504"]
    assert "between the two divider joists under each breaker" in sh["D-504"]
    for n in ("S-101", "A-101", "D-504"):
        assert "doubled joist" not in sh[n], n
    assert "doubled joist" not in " ".join(_flat(s) for s in prentice["steps"])


def test_zone_line_breaker_rides_the_rims():
    """Glengarry lower is zone-framed: its breaker sits on the S/A zone line, where each zone has its own rim — the breaker rides both
    rims with a divider joist inside each, no blocks between divider joists."""
    j = _job(_spec("jobs/glengarry_lower.json"), sheets=True)
    assert divider_groups(j["L"]) == (["DS/A"], [])
    dv = next(h for h in _step(j, "Frame")["how"] if h.startswith("Breaker"))
    assert dv.startswith("Breaker DS/A on the zone line: the breaker board rides the two zones' rims, a divider joist tight inside each rim")
    assert "two divider joists per breaker" not in dv and "blocks" not in dv
    assert "breaker on both zones' rims · DS/A" in j["sheets"]["S-101"]


def test_stair_supports_follow_the_layout(prentice):
    """Every spacing from the layout (the geometry group closes the stringers up and adds box-step cross members): the over-limit
    office check if and only if a stair is over its tread line's max, and the max in the crew's line only when every stair meets it."""
    t, L = prentice["t"], prentice["L"]
    s = L.spec

    def check(steps):
        st = next(x for x in steps if x["title"].startswith("Stairs"))
        how = " ".join(st["how"])
        over = []
        for ss, sl in zip(s.stairs, L.stairs):
            oc, mx = _tread_supports(t, sl, ss.name), tread_oc_max(s, sl)
            assert mx == 8.0 and oc, ss.name                              # Terrain+ treads: CCRR-0128 Table 1's 8"
            assert (f"cross members @ {inches_frac(oc, 8)} OC" if sl.build == "box" else f"{sl.stringers} 2x12 stringers @ {oc:.0f}\" OC") in how, ss.name   # the cut list's spacing
            over.append(oc > mx + 0.25)
            flagged = any(c.startswith(f"{ss.name}: tread supports @ {oc:.0f}\" OC — over the 8\" max for Terrain+ treads") and "CCRR-0128 Figure 10" in c for c in st["check"])
            assert flagged == over[-1], ss.name
        assert ("supports @ 8\" OC max" in how) == (not any(over))
        for w in ("square-shouldered Terrain+ boards on Cortex", "no CONCEALoc on stairs", "the front edge flush with the riser face"):
            assert w in how, w
        assert "strictest" not in how and "CCRR-0128" not in how          # the maker-limit sources stay in the flags
        return st

    check(prentice["steps"])
    cs = next(sl for sl in L.stairs if sl.build != "box")
    boxes = [sl for sl in L.stairs if sl.build == "box"]
    saved = (cs.stringers, [getattr(b, "cross_members", 0) for b in boxes])
    try:                                                                  # the geometry group's layout: 10 stringers, cross members at 8" max
        cs.stringers = 10
        for b in boxes:
            b.cross_members = int(-(-b.width // 8)) + 1
        st2 = check(step_sheets(t, L))
        assert "10 2x12 stringers @ 7\" OC" in " ".join(st2["how"]) and not any("tread supports @" in c for c in st2["check"])
        assert "supports @ 8\" OC max" in " ".join(st2["how"])
    finally:
        cs.stringers = saved[0]
        for b, n in zip(boxes, saved[1]):
            b.cross_members = n


def test_stair_flags_follow_the_layout(prentice):
    cs = next(sl for sl in prentice["L"].stairs if sl.build != "box")
    oc = cs.width / (cs.stringers - 1)
    info = [f.text for f in prentice["f"] if f.topic == "stairs" and f.severity == "INFO" and f"stringers {cs.stringers} @ {oc:.0f}\" OC" in f.text]
    assert info and all("12\" OC (composite treads)" not in x for x in info)
    over = [f.text for f in prentice["f"] if f.topic == "stairs" and f.severity == "CHECK" and f"stringers @ {oc:.0f}\" OC — over the 8\" max for Terrain+ treads" in f.text]
    assert bool(over) == (oc > 8.25) and all("CCRR-0128 Figure 10" in x for x in over)


def test_irx_posts_lags_corners_foot_blocks(prentice):
    L, t = prentice["L"], prentice["t"]
    assert irx_posts(L) == (9, "5 CORNER, 4 END") and corner45(L.rail) == 5 and foot_block_bays(L.rail) == 5
    rl = _step(prentice, "Rail")
    how = " ".join(rl["how"])
    for w in ("(4) 3/8\" x 6\" HDG lag screws with washers per post", "3/16\" pilots", "shims under the base", "5/8\" wire hole", "before the post is fastened",
              "set at 22.5 degrees on the corner bisector", "AZTIXBKT22KIT", "fit them before cutting any panel", "a foot block under the middle of each of the 5 bays over 4'",
              "Caps last", "post-cap lights go on with them"):
        assert w in how, w
    assert "HeadLOK" not in how
    assert any(c.startswith("Order: (36) 3/8\" x 6\" HDG lag screws") for c in rl["check"]) == (not any(_rail_lag(l) for l in t.lines))
    assert any(c.startswith("Order: (5) AZTIXBKT22KIT") for c in rl["check"]) == (not any("BKT22" in l.item.upper() for l in t.lines))
    assert "Rail post blocking (IRX)" in " ".join(_step(prentice, "Frame")["how"])
    d4 = prentice["sheets"]["D-504"]
    assert "(4) 3/8\" x 6\" HDG lag screws + washers into the blocking, 3/16\" pilots" in d4 and "5/8\" wire hole" in d4 and "HeadLOK" not in d4


def test_dtt1z_lags_never_pass_for_the_post_lags(prentice):
    """A 3/8" x 6" lag line for the DTT1Z ties clears the DTT1Z check, never the IRX posts' own; a rail-post lag line clears that."""
    t = copy.copy(prentice["t"])
    t.lines = [l for l in prentice["t"].lines if not _rail_lag(l) and "lag" not in l.item.lower()] + [
        Line("Hardware", "3/8\" x 6\" HDG lag screw + washer, fully threaded — DTT1Z lateral ties", 4, 6, "ea",
             "+2  (1 per DTT1Z through the ledger, 3\" min. into the house framing, predrilled — IRC R507.9.2(2))")]
    steps = step_sheets(t, t.layout)
    assert any(c.startswith("Order: (36) 3/8\" x 6\" HDG lag screws") for c in next(s for s in steps if s["title"] == "Rail")["check"])
    assert not any("for the DTT1Z ties" in c for c in next(s for s in steps if s["title"] == "Frame")["check"])
    t.lines = t.lines + [Line("Hardware", "3/8\" x 6\" HDG lag screw + washer — IRX rail posts, through the base plate into the blocking", 36, 38, "ea", "+2  (9 rail posts x 4)")]
    assert not any(c.startswith("Order: (36) 3/8\"") for c in next(s for s in step_sheets(t, t.layout) if s["title"] == "Rail")["check"])


def test_drink_rail_between_the_posts(prentice):
    how = " ".join(_step(prentice, "Rail")["how"])
    for w in ("universal panel cover on each panel in place of the top rail", "clips 4 per 6' panel", "within the first baluster at each end", "18\" max apart",
              "Reserve Antique Leather board cut to fit between the posts with its corners trimmed — not mitered", "centered on the cover, embossed face up",
              "#8 x 3/4\" SS K-Lath screws", "1/8\" x 3/4\" deep pilots", "no face screws, no plugs"):
        assert w in how, w
    for bad in ("drink-rail brackets", "mitered at every turn", "plugs color-matched"):
        assert bad not in how, bad
    sh = prentice["sheets"]
    assert "Modern top rail" not in sh["D-504"] and "drink rail between the posts, on clips over the universal panel cover (no top rail" in sh["D-504"]
    assert "post cap + LED cap light" in sh["D-504"] and "post cap + LED cap light" in sh["D-501"]      # each post rises past the board to its cap
    assert "panel cover (no top rail)" in sh["D-501"] and "drink-rail brackets" not in sh["D-501"]
    assert "corners trimmed, not mitered" in sh["A-201"]


def test_drink_rail_over_the_posts():
    """railing.drink_rail_mount "over": posts cut level, wood inserts, the board mitered with its seams on post centers — and no caps."""
    j = _job(_spec("jobs/prentice_centennial.json", drink_rail_mount="over"))
    rl = _step(j, "Rail")
    how = " ".join(rl["how"])
    for w in ("Drink rail over the posts (IRX drink-rail guide 01-31-20)", "every post cut level, its top within 1/4\" of the panel covers", "a wood insert cut to fit inside each post",
              "mitered at the corner posts, seams on post centers", "(3) 2-1/2\" Cortex or TOPLoc screws each side of a seam into the insert", "K-Lath"):
        assert w in how, w
    assert "Caps last" not in how and "corners trimmed" not in how and "between the posts" not in how
    assert any(c.startswith("Post tops level") for c in rl["check"]) and not any("a cap on every post" in c for c in rl["check"])


def test_lighting_rough_in_and_fixtures(prentice):
    ri, fx = _step(prentice, "Lighting rough-in"), _step(prentice, "Light fixtures")
    r = " ".join(ri["how"])
    for w in ("12/2", "stapled under the frame", "wire loop at each of the 9 rail post locations", "5/8\" hole", "wiring goes in before the posts are secured",
              "under the rim's bottom edge", "two runs from the transformer"):
        assert w in r, w
    assert all("cable" in g.lower() or "staple" in g.lower() for g in ri["goes_in"])
    x = " ".join(fx["how"])
    for w in ("cut each HardieTrim riser for its housing", "fiber-cement blade in the jig saw", "ColorPlus edge coater", "2x backing", "above the outdoor GFCI outlet",
              "coach lantern", "about 11 V or more at the far end of each run", "against 90 W, the TimberTech maximum on the 100 W transformer", "two runs from the transformer, none over 60 W"):
        assert w in x, w
    assert "against the 100 W" not in x and not any("cable" in g.lower() for g in fx["goes_in"])


def test_ledgerlok_per_fastenmaster(prentice):
    L, t = prentice["L"], prentice["t"]
    fr = _step(prentice, "Frame")
    how, chk = " ".join(fr["how"]), fr["check"]
    sch = t.schedule["Ledger"]
    if _LL_RULE.search(sch):           # the order still counts the owner's 12" OC: the crew text carries FastenMaster's spacing and count
        assert [q[2] for q in ledger_pieces(t, L)] == [10, 10, 10, 10]       # 13'-9 1/2" joists: Table 1's 14' row at 40 psf, on all 4 pieces
        assert "staggered 10\" OC (FastenMaster Table 1: joists to 14'), first 3-3/4\" from each end of each piece · 36 fasteners" in how
        assert any(c.startswith("LedgerLOK at FastenMaster's spacing: 36 on the 4 ledger pieces (3-3/4\" from each end of each) — the order counts 29 at 12\" OC") for c in chk)
    else:                              # the order spaces them by the joist span itself: its words, as written, and no count to reconcile
        assert ledger_words(t, L) == sch and sch in how and not any(c.startswith("LedgerLOK at") for c in chk)
    assert "first 3\" from each end" not in how
    sh, ll = prentice["sheets"], ledgerlok_len(t)
    assert f"LedgerLOK {ll} 2 rows {ledger_oc_words(t, L)}, first 3-3/4\" from each end" in sh["D-502"]            # the labels read the same ledger text
    assert f"LedgerLOK {ll}, 2 rows {ledger_oc_words(t, L, compact=True)}" in sh["D-504"]
    for n in ("G-001", "S-101", "A-301", "D-501", "D-502", "D-504"):
        assert "first 3\" from each end" not in sh[n], n
        if 12 not in ledger_oc(t, L):
            assert "staggered 12\" OC" not in sh[n], n


def test_engineered_deck_reads_table1_too():
    """Glengarry lower is engineered: its LedgerLOKs still follow FastenMaster Table 1 by joist span (zone A's 16' joists: 9" OC)."""
    j = _job(_spec("jobs/glengarry_lower.json"))
    t, L = j["t"], j["L"]
    assert L.spec.extras.engineered
    sch = t.schedule["Ledger"]
    fr = " ".join(_step(j, "Frame")["how"])
    if _LL_RULE.search(sch):
        assert {nm: sp for nm, _, sp, _ in ledger_pieces(t, L)} == {"S": 12, "A": 9}
        assert "S 2'-1\" @ 12\" · A 17'-0\" @ 9\"" in fr and "staggered 12\" OC" not in fr
    else:
        assert sch in fr
    assert ledger_oc_words(t, L) != "staggered 12\" OC"


def test_dtt1z_and_ventilation(prentice):
    t = prentice["t"]
    fr = _step(prentice, "Frame")
    how, chk = " ".join(fr["how"]), fr["check"]
    assert "(4) Simpson DTT1Z spread evenly along the ledger, one within 24\" of each end, each on a 3/8\" lag 3\" min into the house framing" in how and "R507.9.2(2)" in how
    lag = any("lag" in l.item.lower() and ("DTT" in l.item or "lateral" in (l.why or "").lower()) for l in t.lines)
    assert any(c.startswith("Order: (4) 3/8\" lag screws for the DTT1Z ties") for c in chk) == (not lag)
    assert any("1-1/2\" between grade and the bottom of every joist and rim" in c for c in chk)
    assert any(fl.topic == "ventilation" and fl.severity == "CHECK" for fl in prentice["f"])
    d4 = prentice["sheets"]["D-504"]
    assert "1/2\" threaded rod" not in d4 and "1/2\" rod" not in d4 and "one within 24\" of each end" in d4


def test_d504_fastening_schedule_and_fascia_label(prentice):
    d4 = prentice["sheets"]["D-504"]
    assert "HardieTrim Arctic White fascia: 2-1/2\" 16-ga 316SS ring-shank finish nails, 4 per 16\"; 2\" over soil, 1/4\" over brick and treads, never caulked" in d4
    assert "HardieTrim 16-ga 316SS ring-shank finish nails, 4 per 16\"" in d4 and "Hardie gaps 1/4\" over treads / brick, 2\" over soil / mulch, open" in d4
    assert "fascia: Cap-Tor xd" not in d4 and "trim screws" not in d4


def test_plain_job_keeps_its_own_words():
    """A Fulton / Prime+ deck without HardieTrim, IRX or lights: fascia goes in with the decking, no new steps, no IRX or Hardie lines."""
    j = _job(DeckSpec.from_dict(json.loads((EX / "jason_ct.json").read_text())))
    titles = [s["title"] for s in j["steps"]]
    assert not any(k in " ".join(titles) for k in ("HardieTrim", "Lighting rough-in", "Light fixtures"))
    flat = " ".join(_flat(s) for s in j["steps"])
    assert "lag screws with washers per post" not in flat and "AZTIXBKT22KIT" not in flat and "finish nails" not in flat
    assert any("fascia" in g.lower() for g in _step(j, "Decking")["goes_in"])
    assert not any(fl.topic == "hardie" for fl in j["f"])


def test_composite_keeps_the_louvered_roof_posts():
    """Fillmore (two levels, IRX, a louvered roof): the roof's posts stand in the rail line — not counted as IRX posts, their note kept."""
    j = _job(_spec("jobs/fillmore_centennial_all.json"))
    how = " ".join(_step(j, "Rail")["how"])
    assert how.startswith("21 posts") and "louvered-roof posts" in how and "wall-mount brackets" in how
    assert any(c.startswith("Order: (84) 3/8\" x 6\" HDG lag screws") for c in _step(j, "Rail")["check"]) == (not any(_rail_lag(l) for l in j["t"].lines))
    assert "on the 100 W + 100 W transformers" in " ".join(_step(j, "Light fixtures")["how"])
    assert "first 3\" from each end" not in " ".join(_step(j, "Frame")["how"])


def test_composite_hardie_step_reads_the_parts_stairs():
    """A two-level deck with HardieTrim: its stairs live in its parts, and the HardieTrim step still puts on their risers."""
    j = _job(_spec("jobs/fillmore_centennial.json", extras={"hardie_skirt": "4/4 x 12 smooth"}))
    hs = _step(j, "HardieTrim")
    assert hs["title"] == "HardieTrim fascia, risers and skirts" and "every stair riser" in " ".join(hs["how"])
    assert "HardieTrim gaps open: 1/4\" over treads/brick, 2\" over soil/mulch" in hs["check"]


def test_office_checks_stay_off_client_pages(prentice, tmp_path):
    """The order gaps, the makers' written OKs and a design over a maker's limit are for the internal build set only: build_set(customer=True)
    (the customer, supplier and option pages) leaves them out, keeps every crew check, and no crew line carries a maker's deviation."""
    office = [c for s in prentice["steps"] for c in s["check"] if OFFICE_CHECK.match(c)]
    assert any(c.startswith("Get James Hardie") for c in office) and any(c.startswith("TimberTech's written OK for Cortex") for c in office)
    assert any(c.startswith("TimberTech's written OK for Cap-Tor xd") for c in office)
    r = build_set(prentice["t"], prentice["f"], str(tmp_path / "bs"), render=False, customer=True)
    kept = [c for s in r["steps"] for c in s["check"]]
    assert not any(OFFICE_CHECK.match(c) for c in kept)
    assert "HardieTrim gaps open: 1/4\" over treads/brick, 2\" over soil/mulch" in kept and "End of construction" in kept
    how = " ".join(h for s in r["steps"] for h in s["how"] if h)
    for bad in ("TOPLoc", "TimberTech specifies", "strictest", "over the 8\" max"):
        assert bad not in how, bad
