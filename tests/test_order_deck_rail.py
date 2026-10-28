"""The Decks & Docks order for the decking, fasteners, HardieTrim and rail — the Prentice job (jobs/prentice_centennial.json),
its IRX alternate, Jefferson (HardieTrim on a steel frame) and every job in jobs/:
- the field's 2 spares in all (the standard: "field boards +2"), on the length every row fits — Prentice 27 x 16' + 25 x 20';
- Terrain+ / Reserve square-shouldered boards come in 16' and 20' only (TimberTech 2026 guide: TC5416DO / TC5420DO): the stair
  treads are cut from the picture-frame boards with one shared spare — Prentice 6 x 20' + 3 x 16', no 12' square edge;
- the composite Cortex kit (CTC100LFDO, 224 screws) on the borders, dividers and treads only — the HardieTrim risers take nails;
  a Cortex-screwed composite field the 300 SF kit (CTC300SFDO, 1,050 screws);
- CONCEALoc in D&D's 100 SF box (CLOCFAST, 175 clips): ceil(clips / 175) boxes;
- HardieTrim per James Hardie TR1509 09/25: 316SS ring-shank finish nails (screws on a steel frame), the touch-up kit, no fascia
  behind a closed-riser stair or box step (the 3D stops it there too; an open-riser or option stair keeps it), no skirt at a
  mitered box-step corner, risers ripped (1/4" over the tread / brick, 2" off the soil) and nested two to a width on the fascia
  offcuts;
- the drink rail between the posts: post face to post face, not mitered, on 16' Reserve with the spare an offcut (3 boards);
- White IRX part numbers for a White rail (43" posts and 42" kits for a 42" rail), a 22.5-degree bracket pack per 45-degree
  corner post, (4) 3/8" x 6" lags per post (none at a louvered-roof post);
- the documented D&D prices, EST — ask D&D on the rest."""
import copy
import json
import math
import re
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff.catalog import PRICEBOOK, decking_facts, deck_lengths
from decktakeoff.scene import build_scene
from decktakeoff.spec import DeckSpec
from decktakeoff.takeoff import _riser_rips, _sku, pack_boards, repack_boards

ROOT = Path(__file__).resolve().parent.parent
JOBS = sorted(p for p in (ROOT / "jobs").glob("*.json") if "messner" not in str(p))
PRENTICE = json.loads((ROOT / "jobs" / "prentice_centennial.json").read_text())
IRX_ALT = json.loads((ROOT / "jobs" / "prentice_centennial_irx.json").read_text())
JEFFERSON = json.loads((ROOT / "jobs" / "jefferson_louisville.json").read_text())
FILLMORE_ROOF = json.loads((ROOT / "jobs" / "fillmore_centennial_roof.json").read_text())
LANSING = json.loads((ROOT / "jobs" / "lansing_englewood.json").read_text())


def _takeoff(job):
    return run(DeckSpec.from_dict(job), with_pricing=False)[0]


def _stock(l):
    return int(re.search(r"1x6x(\d+)", l.item).group(1))


def _scene_fascia(L):
    """{outline side: [3D fascia piece lengths, inches]} — what the drawings, build set and viewer show."""
    out = {}
    for b in build_scene(L).boxes:
        if b.kind == "fascia" and (b.tag or "").startswith("fascia side edge:"):
            out.setdefault(b.tag[len("fascia side "):], []).append(round(((b.x1 - b.x0) if b.rot else max(b.x1 - b.x0, b.y1 - b.y0)) * 12, 1))
    return out


@pytest.fixture(scope="module")
def t():
    return _takeoff(PRENTICE)


# ------------------------------------------------------------------ 1. field spares
def test_field_spares_two_in_all_on_the_length_every_row_fits(t):
    field = [l for l in t.lines if l.category == "Decking" and l.item.startswith("TimberTech Terrain+ Dark Oak 1x6x") and " — " not in l.item]
    # (with the 3/4" HardieTrim the rows pack 1 x 12' + 26 x 16' + 24 x 20'; was 25 + 2 and 25 + 2 per length)
    assert {_stock(l): (l.net, l.order) for l in field} == {12: (1, 1), 16: (26, 28), 20: (24, 24)}
    longest = max(c.length_in for c in t.cut_list if c.member.startswith("Field boards"))
    assert longest + 0.375 <= 16 * 12 - 2.0                                  # a 16' holds every row: the spares are 16'
    (sp,) = [l for l in field if l.order > l.net]
    assert sp.why.startswith("+2  (the field's 2 spares, on the 16' every row fits")
    assert [l.why.startswith("exact  (the field's 2 spares are on the 16'") for l in field if l is not sp] == [True, True]


@pytest.mark.parametrize("path", JOBS, ids=[p.stem for p in JOBS])
def test_every_job_orders_two_field_spares(path):
    job = json.loads(path.read_text())
    if job.get("quoted_order"):
        pytest.skip("the owner's quoted order")
    tj = _takeoff(job)
    dk = tj.spec.decking
    field = [l for l in tj.lines if l.category == "Decking" and l.item.startswith(f"{dk.brand} {dk.collection} {dk.color} 1x6x") and " — " not in l.item]
    if field:
        assert sum(l.order - l.net for l in field) == 2, [(l.item, l.net, l.order) for l in field]
    for l in tj.lines:                                                       # every spare carries its reason; no SKU left a template
        assert "{" not in (l.sku or ""), (l.item, l.sku)
        if l.category in ("Decking", "Fascia", "Rail", "Stairs", "Fasteners") and l.order > l.net and not tj.spec.geometry.parts:
            assert l.why.lstrip().startswith(f"+{l.order - l.net:g}"), (l.item, l.why)
        assert not re.search(r"(Terrain\+|Reserve) .*1x6x12 Square Edge", l.item), l.item     # no 12' square shoulder in these lines
    if tj.spec.extras.hardie_skirt:                                          # TR1509: nails into wood, screws into steel — never both
        nails = [l for l in tj.lines if "finish nail" in l.item and l.category in ("Fascia", "Stairs")]    # the deck's own (a roof cover's fascia is on wood)
        screws = [l for l in tj.lines if "trim screw" in l.item and l.category in ("Fascia", "Stairs")]
        assert (len(nails), len(screws)) == ((0, 1) if tj.spec.framing.system == "steel" else (1, 0)), path.stem


# ------------------------------------------------------------------ 2. square shoulder: 16' / 20', treads on the border boards
def test_terrain_plus_and_reserve_square_shoulder_lengths():
    assert deck_lengths("Terrain+", "square") == (16, 20) and deck_lengths("Reserve", "square") == (16, 20)
    assert deck_lengths("Terrain+", "grooved") == (12, 16, 20) and deck_lengths("Reserve", "grooved") == (12, 16, 20)


def test_treads_cut_from_the_border_boards_on_one_spare(t):
    sq = [l for l in t.lines if l.category == "Decking" and "Square Edge — borders, dividers & stair treads" in l.item]
    assert {_stock(l): (l.net, l.order) for l in sq} == {16: (2, 3), 20: (6, 6)}       # 6 x 20' + 3 x 16'
    assert sum(l.order - l.net for l in sq) == 1                             # one spare for the borders and treads
    assert not [l for l in t.lines if "1x6x12 Square Edge" in l.item]        # the 9 x 12' tread line was unorderable
    assert not [l for l in t.lines if l.category == "Stairs" and " — treads (" in l.item]
    assert sum(l.why.count("tread (") for l in sq) == sum(st.tread_pieces for st in t.layout.stairs)
    treads = [c for c in t.cut_list if c.member.startswith("Stair treads")]
    assert len(treads) == 3 and all("cut from the square-edge border boards, Cortex + plugs" in c.note for c in treads)


def test_a_face_screwed_tread_reads_no_cortex():
    job = copy.deepcopy(PRENTICE)
    job["decking"].pop("border_fastener")                                    # CONCEALoc field, no Cortex border: Cap-Tor on the treads
    treads = [c for c in _takeoff(job).cut_list if c.member.startswith("Stair treads")]
    assert treads and all("border boards" in c.note and "Cortex" not in c.note for c in treads)


def test_repack_keeps_every_piece_and_never_buys_more():
    pieces = [("border", 134.0), ("border", 131.9), ("border", 95.1), ("border", 77.3), ("border", 76.3), ("border", 74.1), ("border", 74.1),
              ("border", 74.1), ("border", 73.4), ("border", 73.4), ("border", 71.1), ("border", 59.4), ("border", 55.4)] + [("tread", 67.25)] * 4
    first = pack_boards(pieces, stocks=(16, 20))
    better = repack_boards(first, stocks=(16, 20))
    assert sorted(p for b in [b for v in better.values() for b in v] for p in b) == sorted(pieces)
    assert sum(s * len(v) for s, v in better.items()) <= sum(s * len(v) for s, v in first.items())
    for s, bins in better.items():
        for b in bins:
            assert sum(x + 0.125 for _, x in b) <= (s * 12 - 2.0 if s < 20 else 240.0) + 1e-6


# ------------------------------------------------------------------ 3. Cortex: the composite kit, borders + treads only
def test_cortex_composite_kit_on_the_borders_and_treads(t):
    (cx,) = [l for l in t.lines if l.category == "Fasteners" and l.item.startswith("Cortex")]
    assert cx.item == "Cortex for TimberTech Composite (Terrain+), Dark Oak plugs — picture frame, dividers and stair treads"
    assert cx.sku == "CTC100LFDO" and cx.source.startswith("EST — ask D&D") and PRICEBOOK["decking"]["Cortex_TimberTech_100lf"]["count"] == 224
    tot, bd, st_ = map(int, re.match(r"(\d+) screws  \(border/divider (\d+) · stairs (\d+)\)", cx.why).groups())
    assert tot == bd + st_ and cx.order == math.ceil(tot / 224) == 2         # ~274 screws: 2 kits, not the 350 ct PVC kit
    # the stairs count is the treads alone: what the HardieTrim risers would add as riser boards they take as nails
    job = copy.deepcopy(PRENTICE)
    job["extras"].pop("hardie_skirt")
    (cx0,) = [l for l in _takeoff(job).lines if l.category == "Fasteners" and l.item.startswith("Cortex")]
    st0 = int(re.search(r"· stairs (\d+)\)", cx0.why).group(1))
    (nl,) = [l for l in t.lines if "finish nail" in l.item]
    assert st0 - st_ == int(re.search(r"risers (\d+):", nl.why).group(1)) > 0


def test_a_cortex_composite_field_takes_the_300_sf_kit():
    job = copy.deepcopy(PRENTICE)
    job["decking"]["fastener_system"] = "Cortex"                             # the field face-screwed: CTC300SFDO, not 10 x CTC100LFDO
    cx = [l for l in _takeoff(job).lines if l.category == "Fasteners" and l.item.startswith("Cortex")]
    (fl,) = [l for l in cx if "300 SF collated kit" in l.item]
    n = int(re.match(r"(\d+) screws", fl.why).group(1))
    assert fl.sku == "CTC300SFDO" and fl.order == math.ceil(n / 1050) and fl.source.startswith("EST — ask D&D")
    assert [l.sku for l in cx if l is not fl] == ["CTC100LFDO"]              # the borders keep the 100 LF kit


def test_the_pvc_cortex_kit_at_the_october_quote():
    d = PRICEBOOK["decking"]["Cortex_TimberTech_350"]                        # the same collated 100 SF kit as July's $175 SO
    assert d["each"] == 97.82 and "990585" in d["source"] and "CTC100SFEW" in d["source"]


# ------------------------------------------------------------------ 4. CONCEALoc in D&D's 100 SF box
def test_concealoc_in_the_100_sf_box(t):
    (cl,) = [l for l in t.lines if l.category == "Fasteners" and "CONCEALoc" in l.item]
    clips = int(re.match(r"(\d+) clips needed", cl.why).group(1))
    assert cl.order == cl.net == math.ceil(clips / 175) and cl.sku == "CLOCFAST" and cl.unit_cost == 172.96
    assert "500" not in cl.item and "CONCEALoc_500" not in PRICEBOOK["decking"]
    assert f"({cl.order} boxes of 175)" in cl.why
    (cl1,) = [l for l in _takeoff(LANSING).lines if l.category == "Fasteners" and "CONCEALoc" in l.item]
    assert cl1.order == 1 and "(1 box of 175)" in cl1.why                     # never "1 boxes"


# ------------------------------------------------------------------ 5. HardieTrim per TR1509
def test_hardietrim_nailed_and_sealed(t):
    assert not [l for l in t.lines if "trim screw" in l.item]                 # the Camo trim screws are off a wood frame
    (nl,) = [l for l in t.lines if "Type 316 stainless ring-shank finish nail" in l.item]     # TR1509 p.3: ring shank with stainless
    n, fa, sk, ri = map(int, re.match(r"(\d+) nails  \(fascia (\d+): 4 per 16\" · skirts (\d+) \+ risers (\d+)", nl.why).groups())
    assert n == fa + sk + ri and nl.order == math.ceil(n / 1000) and nl.source.startswith("EST — ask D&D")
    assert "ring shank — confirm SKU with D&D" in nl.source and "B16212SS" not in nl.source    # no smooth-shank part as the basis
    fas = [c for c in t.cut_list if c.nominal == "fascia"]
    assert fa == sum(4 * (math.ceil(max(0.0, c.length_in - 2.0) / 16) + 1) for c in fas if not c.member.startswith("Stair skirt"))
    assert sk == sum(2 * (math.ceil(max(0.0, c.length_in - 2.0) / 16) + 1) for c in fas if c.member.startswith("Stair skirt"))
    (tk,) = [l for l in t.lines if l.item.startswith("James Hardie ColorPlus Touch-up Kit, Arctic White")]
    assert tk.order == 1 and "Edge Sealer" in tk.item
    hs = t.schedule["HardieTrim"]
    assert "Type 316 stainless ring-shank finish nails" in hs and "4 per 16\"" in hs and "Edge Sealer on every field cut" in hs


def test_hardietrim_on_a_steel_frame_takes_screws():
    tj = _takeoff(JEFFERSON)
    assert tj.spec.framing.system == "steel" and tj.spec.extras.hardie_skirt
    (sc,) = [l for l in tj.lines if l.category == "Fascia" and "trim screw" in l.item]
    n = int(re.match(r"(\d+) screws", sc.why).group(1))
    assert sc.order == math.ceil(n / 100) and "not finish nails" in sc.why and "3/4\" from the edges" in sc.why
    assert "trim screws into the steel framing" in tj.schedule["HardieTrim"]


def test_fascia_stops_at_the_stair_and_box_step_openings(t):
    fas = [c for c in t.cut_list if c.nominal == "fascia"]
    assert not [c.member for c in fas if c.member.startswith(("Fascia side 2", "Fascia side 3"))]     # the box steps' upper risers
    s6 = [c for c in fas if c.member.startswith("Fascia side 6")]
    e6 = next(e for e in t.layout.outline_edges if e.name == "edge:6")
    st6 = next(st for st in t.layout.stairs if st.side == "edge:6")
    assert [c.member for c in s6] == ["Fascia side 6 (1 of 2, beside the Center stair)", "Fascia side 6 (2 of 2, beside the Center stair)"]
    assert sum(c.length_in for c in s6) == pytest.approx(e6.length - st6.width + 1.5, abs=0.05)      # 3/4" at each outline corner
    assert len([c for c in fas if c.member.startswith("Stair skirt")]) == 4  # the center stair's 2 + each box step's free end
    (fl,) = [l for l in t.lines if l.category == "Fascia" and l.item.startswith("Deck fascia")]
    assert fl.why.count(" · ") + 1 == len(fas)                               # the order lists the cut list's pieces
    # the 3D (drawings, build-set stills, viewer) stops the fascia at the same openings
    assert t.layout.fascia_gaps == {"edge:6": [(14.5, 81.5)], "edge:2": [(0, 73)], "edge:3": [(0, 68)]}
    sc = _scene_fascia(t.layout)
    assert "edge:2" not in sc and "edge:3" not in sc and len(sc["edge:6"]) == 2
    sides = {c.member for c in fas if c.member.startswith("Fascia side")}
    assert {f"edge:{m.split()[2]}" for m in sides} == set(sc)                # a fascia piece on every side the 3D draws, and only there


@pytest.mark.parametrize("change", ["open risers", "option"])
def test_an_open_riser_or_option_stair_keeps_the_fascia(change):
    job = copy.deepcopy(IRX_ALT)                                             # center stair on side 6, a box step on side 2
    for s in job["stairs"]:
        if change == "open risers":
            s["closed_risers"] = False                                       # the rim shows between the treads: the fascia stays
        else:
            s["option"] = "Stairs"                                           # an option: the base fascia stays whole (the 3D toggles it)
    tk = _takeoff(job)
    fas = {c.member: c.length_in for c in tk.cut_list if c.nominal == "fascia" and c.member.startswith(("Fascia side 2", "Fascia side 6"))}
    assert set(fas) == {"Fascia side 2", "Fascia side 6"} and not getattr(tk.layout, "fascia_gaps", None)
    sc = _scene_fascia(tk.layout)
    assert len(sc["edge:2"]) == len(sc["edge:6"]) == 1
    closed = _takeoff(IRX_ALT)                                               # closed risers, no option: cut in the order and the 3D
    assert len([c for c in closed.cut_list if c.member.startswith(("Fascia side 2", "Fascia side 6"))]) == 4
    assert sorted(closed.layout.fascia_gaps) == ["edge:2", "edge:6"] and len(_scene_fascia(closed.layout)["edge:6"]) == 2


def test_composite_fascia_screws_come_off_with_the_pieces():
    with_ = _takeoff(IRX_ALT)                                                # Terrain+ fascia, Cap-Tor 2 at each end + every 12"
    job = copy.deepcopy(IRX_ALT)
    for s in job["stairs"]:
        s["position_in"] = 0.0
    def capt(tk):
        (ct,) = [l for l in tk.lines if l.category == "Fasteners" and l.item.startswith("Starborn Cap-Tor") and "fascia" in l.why]
        return int(re.search(r"fascia (\d+)", ct.why).group(1))
    pcs = lambda tk: [c.length_in for c in tk.cut_list if c.nominal == "fascia" and not c.member.startswith(("Stair skirt", "Landing"))]
    per = lambda L_: 4 + max(0, math.ceil(L_ / 12) - 1)
    a, b = with_, _takeoff(job)
    assert capt(a) - capt(b) == sum(per(x) for x in pcs(a)) - sum(per(x) for x in pcs(b))


def test_risers_ripped_per_tr1509_and_nested_on_the_fascia_offcuts(t):
    th = decking_facts("Terrain+")["thick"]
    for st in t.layout.stairs:
        rr = _riser_rips(st, th)
        assert rr[0] == pytest.approx(st.geo.riser_in - th - 0.25)           # 1/4" open over the tread below (Fig. 2 / 5)
        if getattr(st, "build", "") == "box":
            assert set(rr) == {rr[0]}                                        # the box steps sit on the reset brick border
        else:
            assert rr[-1] == pytest.approx(st.geo.riser_in - th - 2.0)       # the center stair lands on the lawn: 2" off the soil
    risers = {c.member: c.note for c in t.cut_list if c.member.startswith("Stair risers")}
    assert risers["Stair risers (Center stair)"].startswith("rip to 5-13/16\"") and "the bottom one to 4-1/16\"" in risers["Stair risers (Center stair)"]
    assert all("factory edge down, Edge Sealer on every cut" in n_ for n_ in risers.values())
    (rl,) = [l for l in t.lines if l.category == "Stairs" and "every riser" in l.item]
    (fl,) = [l for l in t.lines if l.category == "Fascia" and l.item.startswith("Deck fascia")]
    both, alone = map(int, re.search(r"(\d+) boards for both, (\d+) for the fascia alone", rl.why).groups())
    assert (rl.net, rl.order, fl.net, fl.order) == (both - alone, both - alone, alone, alone + 1)
    assert fl.order + rl.order <= 11 < 13                                    # 13 boards before (8 fascia + 5 risers)


# ------------------------------------------------------------------ 6. drink rail between the posts
def test_drink_rail_between_the_posts(t):
    (dr,) = [l for l in t.lines if l.category == "Rail" and l.item.startswith("Drink rail")]
    assert "between the posts" in dr.item and "mitered" not in dr.item and "no miters" in dr.why
    assert (dr.net, dr.order, dr.unit_cost, dr.sku) == (3, 3, 89.6, "TTR1616AL")       # 3 x 16', not 4; the spare is an offcut
    pieces = [s.ctc - 3.0 for s in t.layout.rail.sections]                   # post face to post face
    off = 3 * 192 - sum(p + 0.125 for p in pieces)
    assert off > max(pieces) and "the spare is a" in dr.why


# ------------------------------------------------------------------ 7. IRX: White SKUs, 22.5-degree packs, post lags
def test_irx_parts_order_in_the_rails_color(t):
    skus = {l.sku for l in t.lines if l.category in ("Rail", "Stairs") and l.sku.startswith("AZT")}
    assert {"AZTIX36UNLP6W", "AZTBULKIXBR6W", "AZTIX3X3PK38W", "AZTIXDRCKITW", "AZTIXACCKITW", "AZTIXBKT22KIT"} <= skus
    assert not [s for s in skus if s.endswith(("B", "BR"))]                  # never the Black parts it was quoted as
    (ck,) = [l for l in t.lines if "drink rail clip kit" in l.item]
    assert "White" in ck.item and "black" not in ck.item.lower()


def test_sku_colors():
    d = {"sku": "AZTIX{h}UNLP6{c}"}
    assert [_sku(d, c) for c in ("White", "Black", "Bronze", "Dark Bronze", "Gray")] == ["AZTIX36UNLP6W", "AZTIX36UNLP6B", "AZTIX36UNLP6BR", "AZTIX36UNLP6BR", ""]
    assert _sku(d, "White", 42) == "AZTIX42UNLP6W"
    assert _sku({"sku": "CTC100LF{cc}"}, "Dark Oak") == "CTC100LFDO" and _sku({"sku": "CTC100LF{cc}"}, "Toasted Wheat") == ""
    assert _sku({}, "White") == "" and _sku(None, "White") == ""


def test_irx_45_degree_bracket_packs_and_post_lags(t):
    (bk,) = [l for l in t.lines if l.category == "Rail" and "22.5° Angle Bracket Pack" in l.item]
    assert bk.order == 5 and bk.sku == "AZTIXBKT22KIT" and bk.source.startswith("EST — ask D&D")
    n_posts = len(t.layout.rail.posts) + sum(st.stair_posts for st in t.layout.stairs)
    (lag,) = [l for l in t.lines if l.category == "Hardware" and "3/8\" x 6\" HDG lag" in l.item]     # one item with the DTT1Z ties' lags, one +2
    (dtt,) = [l for l in t.lines if l.category == "Hardware" and l.item.startswith("Simpson DTT1Z")]
    assert (lag.net, lag.order) == (4 * n_posts + dtt.net, 4 * n_posts + dtt.net + 2) and "rail posts x 4" in lag.why and f"{dtt.net:g} DTT1Z" in lag.why
    assert not [l for l in t.lines if "HeadLOK" in l.item]
    assert "(4) 3/8\" x 6\" HDG lag screws with washers per post" in t.schedule["Rail"] and "22.5°" in t.schedule["Rail"]


def test_no_lags_at_a_louvered_roof_post():
    tf = _takeoff(FILLMORE_ROOF)                                             # the roof's 2 posts stand at 3 rail-post positions (a corner ends two runs)
    (lag,) = [l for l in tf.lines if l.category == "Hardware" and "3/8\" x 6\" HDG lag" in l.item]
    assert "3 rail-post positions are the 2 louvered-roof posts, which bolt down through their own base plates" in lag.why
    n_lp = sum(int(m) for m in re.findall(r"(\d+) rail posts x 4", lag.why))
    n_dtt = sum(int(m) for m in re.findall(r"(\d+) DTT1Z x 1", lag.why))                # the DTT1Z ties' lags ride the same line
    assert lag.net == 4 * n_lp + n_dtt and "the 3 louvered-roof posts" not in lag.why


def test_a_42_inch_irx_rail_orders_the_43_inch_posts_and_42_inch_kits():
    job = copy.deepcopy(PRENTICE)
    job["railing"]["height_in"] = 42                                         # IRX order form 2023: 3x3x43" posts for a 42" rail
    tk = _takeoff(job)
    (pk,) = [l for l in tk.lines if l.category == "Rail" and "post kit" in l.item]
    assert pk.sku == "AZTIX3X3PK43W" and "43\"" in pk.item and "for a 42\" rail" in pk.item and pk.source.startswith("EST — ask D&D")
    (pn,) = [l for l in tk.lines if l.category == "Rail" and "universal panel kit" in l.item]
    assert pn.sku == "AZTIX42UNLP6W" and pn.item.startswith("TimberTech Impression Rail Express 42\" 6' level") and pn.source.startswith("EST — ask D&D")
    assert not [l.sku for l in tk.lines if "PK38" in l.sku or "AZTIX36" in l.sku]


# ------------------------------------------------------------------ 8. prices
def test_documented_dd_prices_and_the_estimates():
    pb = PRICEBOOK
    assert pb["decking"]["TimberTech|Terrain+|per_lf"]["each"] == 4.14
    assert pb["decking"]["TimberTech|Reserve|16|square"]["each"] == 89.6
    assert pb["rail"]["IRX Baluster|post_kit"]["each"] == 87.0 and pb["rail"]["IRX Baluster|panel|6|level"]["each"] == 199.5
    assert pb["rail"]["IRX Baluster|accessory_kit"]["each"] == 38.09
    assert pb["hardware"]["irx baluster_drink_rail_bracket_kit"]["each"] == 127.0
    assert pb["cover"]["hardie_trim_4_4x12_12ft"]["each"] == 61.74
    for sec, key in (("decking", "Cortex_TimberTech_100lf"), ("decking", "Cortex_TimberTech_300sf"), ("rail", "IRX Baluster|post_kit|42"),
                     ("rail", "IRX Baluster|bracket_22"), ("hardware", "lag_3/8x6"), ("rail", "IRX Baluster|panel_cover|6"),
                     ("rail", "IRX Baluster|panel_cover|8"), ("cover", "hardie_touchup"), ("cover", "hardie_finish_nail_316_1000")):
        assert pb[sec][key]["source"].startswith("EST — ask D&D"), key


def test_built_ins_cut_from_16ft_are_priced_as_16ft():
    ti = _takeoff(IRX_ALT)                                                   # benches, planter and door step in Terrain+ (no 12' square)
    rows = [l for l in ti.lines if l.category in ("Benches", "Planters", "Stairs") and re.search(r"Terrain\+ Dark Oak 1x6x\d+ Square Edge", l.item)]
    assert rows and all(_stock(l) == 16 and l.unit_cost == round(4.14 * 16, 2) for l in rows)
    assert not [l for l in rows if "12' boards" in l.why]
