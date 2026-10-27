"""The Messner extension's tests:  cd /home/user/Decks- && python3 -m pytest -q jobs/messner_site/tooling

The engine's own suite (tests/) is not touched by this job; these check the job-local features and that leaving `active()`
gives the engine back exactly as it was."""
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import messner_ext as MX                                     # noqa: E402
from decktakeoff import buildset as BS, catalog as CAT, drawings as DW, layout as LY, scene as SC, takeoff as TK   # noqa: E402
import decktakeoff                                           # noqa: E402
from decktakeoff.spec import DeckSpec                        # noqa: E402

TEST = MX.SITE_DIR / "test"
SPEC, EXTRA = TEST / "as_built_test.json", TEST / "as_built_test_extra.json"
IN = 1 / 12.0


def job():
    return MX.load_job(SPEC, EXTRA)


def core_sheets(path):
    s = DeckSpec.from_dict(json.load(open(path)))
    t, f, _ = decktakeoff.run(s, with_pricing=False)
    return [(n, ttl, re.sub(r"\w+ \d{1,2}, \d{4}", "DATE", svg)) for n, ttl, svg in DW.all_sheets(t.layout, t, f, customer=True)]


def test_job_fields_and_core_fields():
    spec, ext = job()
    assert ext.fascia and ext.glass and ext.vertical and ext.as_built and ext.callouts
    assert ext.tie_model == "DTT2Z" and ext.tie_count == 2 and spec.framing.lateral_ties == 2
    assert ext.brace == "4x6" and ext.joist_tie == "H2.5A" and ext.blocking_midspan
    assert len(ext.photos) == 2 and all(Path(p["img"]).exists() for p in ext.photos)
    assert spec._mx is ext and spec.site.wui_fire_zone and spec.railing.post_kind == "fascia"


def test_active_restores_the_engine():
    before = core_sheets(MX.REPO / "jobs" / "prentice_centennial.json")
    names = [(m, n, getattr(m, n)) for m in (DW, BS) for n in ("sheet", "sheet_meta", "all_sheets")] + [(LY, "build_layout", LY.build_layout),
             (TK, "build_takeoff", TK.build_takeoff), (decktakeoff, "build_takeoff", decktakeoff.build_takeoff), (SC, "build_scene", SC.build_scene)]
    irx = dict(CAT.RAIL_SYSTEMS["IRX"])
    spec, ext = job()
    with MX.active(spec):
        assert DW.sheet is MX.mx_sheet and CAT.RAIL_SYSTEMS["IRX"]["max_ctc"] == pytest.approx(72.43)
        t, f, _ = decktakeoff.run(spec, with_pricing=False)
        assert t.layout.rail.posts
    assert all(getattr(m, n) is v for m, n, v in names)
    assert CAT.RAIL_SYSTEMS["IRX"] == irx and CAT.RAIL_SYSTEMS["Impression Rail Express"] is CAT.RAIL_SYSTEMS["IRX"]
    assert core_sheets(MX.REPO / "jobs" / "prentice_centennial.json") == before


def test_fascia_posts_stand_outboard_at_the_bracket_spacing():
    spec, ext = job()
    with MX.active(spec):
        L = LY.build_layout(spec)
        d = MX.fascia_offset_in(spec)
    W, D = L.finished_w, L.finished_d
    assert d == pytest.approx(0.5 + 0.75 + 1.5)                 # Vintage fascia + the bracket standoff + half a 3" post
    for p in L.rail.posts:
        assert p.x < 0 or p.x > W or p.y > D                     # every post outside the frame face
        assert min(abs(p.x + d), abs(p.x - (W + d)), abs(p.y - (D + d))) < 0.05
    assert max(s.ctc for s in L.rail.sections) <= 72.43 + 0.01
    corners = [p for p in L.rail.posts if p.kind == "CORNER"]
    assert sorted((round(p.x, 1), round(p.y, 1)) for p in corners) == sorted([(round(-d, 1), round(D + d, 1)), (round(W + d, 1), round(D + d, 1))])
    st = L.stairs[0]
    assert all(s_.ctc <= 70.0 + 0.01 for s_ in st.stair_sections)


def test_scene_fascia_glass_vertical_cable_handrail_braces():
    spec, ext = job()
    with MX.active(spec):
        L = LY.build_layout(spec)
        S = SC.build_scene(L)
    zt = spec.geometry.height_in * IN
    jbot = zt - 1.0 * IN - 9.25 * IN
    rp = [b for b in S.boxes if b.kind == "railpost" and "fascia-mount" in (b.tag or "")]
    assert len(rp) == len(L.rail.posts) and all(abs(b.z0 - jbot) < 1e-6 and b.z1 > zt + 3.4 for b in rp)
    assert len([b for b in S.boxes if b.kind == "railbracket"]) >= len(L.rail.posts)
    assert [b for b in S.boxes if b.kind == "glasspanel"] and "glazing" in S.materials
    assert not [b for b in S.boxes if b.kind == "cable" and (not b.rot or b.rot_axis == "z") and b.z0 >= zt - 0.01 and "vertical" not in (b.tag or "")]
    vc = sorted((b for b in S.boxes if b.tag == "vertical stair cable"), key=lambda b: (round((b.x0 + b.x1) / 2, 2), (b.y0 + b.y1) / 2))
    assert len(vc) > 40
    ys = sorted({round((b.y0 + b.y1) / 2, 4) for b in vc if abs((b.x0 + b.x1) / 2 - (vc[0].x0 + vc[0].x1) / 2) < 0.01})
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    assert max(g for g in gaps if g < 0.5) <= (3.0 + 0.1875) / 12 + 1e-3       # 3" clear: a 4" sphere cannot pass
    assert [b for b in S.boxes if b.tag == "stair bottom rail"] and [b for b in S.boxes if b.tag == "graspable handrail"]
    assert [b for b in S.boxes if b.tag == "vertical landing cable"]
    br = [b for b in S.boxes if b.kind == "brace"]
    assert br and all("4x6" in b.tag for b in br)
    assert not [b for b in S.boxes if b.kind == "gravel"]                     # as built: no new-work gravel under the deck


def test_takeoff_hardware_words():
    spec, ext = job()
    with MX.active(spec):
        t, f, _ = decktakeoff.run(spec, with_pricing=False)
    items = {ln.sku or ln.item: ln for ln in t.lines}
    assert items["DTT2Z"].net == 2 and "R507.9.2" in items["DTT2Z"].why
    assert items["H2.5A"].net == 104 and "H2.5A" in items["H2.5A"].item
    lines = " | ".join(ln.item for ln in t.lines)
    assert "solid blocking behind the fascia-mounted guard posts" in lines and "fascia-mount bracket kit" in lines
    assert "vertical cable stair panel kit" in lines and "glass infill kit" in lines and "Knee-brace bolts as built" in lines
    assert "4x6x" in lines
    rows = [r for z in t.layout.zones for r in z.frame.blocking_rows_y]
    assert len(rows) == 4                                                     # over both beams + mid-span of both spans
    for k in ("LedgerLOK", "Cap-Tor", "HeadLOK", "G-Tape", "RSS"):
        assert k not in " ".join(t.schedule.values())


@pytest.fixture(scope="module")
def permit(tmp_path_factory):
    out = tmp_path_factory.mktemp("mx_permit")
    spec, ext = job()
    r = MX.render_permit_set([dict(spec=spec, title="Existing deck")], str(out), key="mxt", name="100 Test Way · Existing Deck — As Built", date_line="October 27, 2026")
    page = Path(r["html"]).read_text()
    sheets = dict((m.group(1), m.group(2)) for m in re.finditer(r'<div class="sheet-page" id="s-1-([A-Z]-\d+)"><h3>[^<]*</h3>(.*?</svg>)</div>', page, flags=re.S))
    return r, page, sheets


def _txt(svg):
    import html
    return " ".join(html.unescape(x) for x in re.findall(r"<text[^>]*>([^<]*)</text>", svg))


def test_permit_set_sheets_and_words(permit):
    r, page, sheets = permit
    assert {"G-001", "S-101", "A-301", "A-501", "D-501", "D-505"} <= set(sheets) and not {"D-502", "D-504"} & set(sheets)
    for num, svg in sheets.items():
        assert "AS-BUILT" in _txt(svg), num
    g = _txt(sheets["G-001"])
    assert "Existing deck — as-built (legalization of the deck as built)" in g and "field-verified" in g
    for c in ("2022 California Residential Code (CRC)", "2022 California Building Code (CBC)", "CALGreen", "Marin County Code Title 19"):
        assert c in g
    assert "A-501" in g and "D-505" in g and "CRC R337" in g and "R401.4.1" in g and "SDS 1.2" in g
    s101 = _txt(sheets["S-101"])
    assert "H2.5A at every joist-to-beam bearing — 104 ties" in s101 and "LT1 · DTT2Z" in s101 and "SOLID BLOCKING ROW" in s101
    a301 = _txt(sheets["A-301"])
    assert "H2.5A each joist" in a301 and "4x6 knee brace" in a301 and "R507.9.2" in a301
    d505 = _txt(sheets["D-505"])
    for k in ("GUARD POST — FASCIA MOUNT", "200 lb at the top, any direction", "R301.5", "within 24\" of each end", "DTT2Z", "manufacturer's installation instructions",
              "solid blocks between the joists", "VERTICAL CABLE", "3\" clear", "KNEE BRACE — 4x6"):
        assert k in d505, k
    assert sheets["A-501"].count('<image href="data:image/jpeg;base64,') == 2 and "Fascia-mount bracket on the" in _txt(sheets["A-501"])


def test_permit_set_brand_and_no_house_words(permit):
    r, page, sheets = permit
    txt = re.sub(r"data:[a-z+/.-]+;base64,[A-Za-z0-9+/=]+", "", re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S))
    assert "Pender Consulting Group" in txt and "PCG" in txt
    for bad in ("GS Exterior", "GSX", "Deck Division", "Design intent", "design intent", "Fulton", "Prime+", "LedgerLOK", "Cap-Tor", "G-Tape", "GRK",
                "new deck", "New deck", "new work", "Rail LF for labor", "T-600", "$"):
        assert bad not in txt, bad
    assert re.search(r"\bIRC\b", " ".join(_txt(v) for v in sheets.values())) is None      # California: the CRC throughout


def test_photo_exhibit_splits_four_to_six_a_sheet(tmp_path):
    spec, ext = job()
    ph = ext.photos * 4                                              # 8 photos -> 2 sheets of 4
    with MX.active(spec):
        out = MX.photo_sheets(ph[:7], MX.mx_sheet_meta(LY.build_layout(spec)))
    assert [n for n, _, _ in out] == ["A-501", "A-502"]
    assert [svg.count('<image href="data:image/jpeg') for _, _, svg in out] == [4, 3]


def test_engine_package_is_byte_identical():
    git = shutil.which("git")
    if not git:
        pytest.skip("no git")
    r = subprocess.run([git, "diff", "--quiet", "HEAD", "--", "decktakeoff", "tests"], cwd=MX.REPO)
    assert r.returncode == 0, "decktakeoff/ or tests/ differ from HEAD"


# ---------------------------------------------------------------------------- the real job spec (authored from asbuilt.json)
JOB = MX.SITE_DIR / "messner_spec.json"


@pytest.fixture(scope="module")
def messner(tmp_path_factory):
    out = tmp_path_factory.mktemp("messner")
    spec, ext = MX.load_job(JOB)
    r = MX.render_permit_set([dict(spec=spec, title="Existing deck")], str(out), key="mx", name="149 Morning Sun Ave · Existing Deck — As Built", date_line="October 27, 2026")
    page = Path(r["html"]).read_text()
    sheets = dict((m.group(1), m.group(2)) for m in re.finditer(r'<div class="sheet-page" id="s-1-([A-Z]-\d+)"><h3>[^<]*</h3>(.*?</svg>)</div>', page, flags=re.S))
    with MX.active(spec):
        t, f, _ = decktakeoff.run(spec, with_pricing=False)
        S = SC.build_scene(t.layout)
    return spec, ext, t, S, sheets


def test_messner_structure_from_the_as_built_model(messner):
    spec, ext, t, S, sheets = messner
    L = t.layout
    assert [(z.name, z.W, z.D) for z in L.zones] == [("A", 546.0, 184.0), ("B", 69.0, 90.0)]
    lines = sorted(L.beam_lines, key=lambda b: b.y)
    assert [round(b.y) for b in lines] == [87, 172] and [b.n_posts for b in lines] == [7, 7] and all(b.size == "6x12" for b in lines)
    st = L.stairs[0]
    assert st.geo.risers == 16 and abs(st.geo.riser_in - 6.625) < 1e-6 and [fg.risers for fg in st.geo.flights] == [11, 5]
    items = {ln.sku: ln for ln in t.lines if ln.sku}
    assert items["DTT2Z"].net == 2 and len(L._mx_ties) == 2                     # one ledger run: one device near each end
    assert items["H2.5A"].net == len(L.zones[0].frame.joist_x) + len(L.zones[0].frame.pf_x) + 2   # the outer beam only
    assert len([b for b in S.boxes if b.kind == "brace"]) == 9 and all(b.rot_axis == "y" for b in S.boxes if b.kind == "brace")   # in the beam planes
    assert [round(r) for r in L.zones[0].frame.blocking_rows_y] == [44, 87, 172]   # over both beams + the house-side bay's mid-span
    assert not any("HUCQ" in ln.item for ln in t.lines)                            # single rims as built


def test_messner_sheets_2025_numbering_and_verify(messner):
    spec, ext, t, S, sheets = messner
    assert {"G-001", "G-002", "G-003", "S-101", "A-301", "D-505"} <= set(sheets)
    alltxt = " ".join(_txt(v) for v in sheets.values())
    for k in ("CRC R321", "R324.4.4", "CWUIC 504.7.3", "R507.9.2", "2025 California Residential Code (CRC)", "(V)", "Field-verify (V)".upper()[:6]):
        assert k in alltxt, k
    for bad in ("R312.1", "R308.4.4", "R311.7.8", "2022 CRC", "ASCE 7-16", "GSX", "GS Exterior", "Fulton", "LedgerLOK", "Call 811"):
        assert bad not in alltxt, bad
    assert "FIELD-VERIFY (V)" in _txt(sheets["G-002"]) and "Footings:" in _txt(sheets["G-002"]) and "Quik-Tube" in _txt(sheets["G-002"])


def test_messner_says_only_what_was_seen(messner):
    """QA truth pass: none of the engine's sizing, spacing or fastening defaults reads as the deck as built; the record does."""
    spec, ext, t, S, sheets = messner
    alltxt = " ".join(_txt(v) for v in sheets.values())
    for bad in ("through-bolts with washers @ 36", "24\" concrete piers", "24\" pier", "CCQ66SDS2.5 column cap", "carriage bolt", "1/2\" x 8\"", "Mahogany",
                "4 stringers", "stringers @ 12\" OC", "CONCEALoc hidden fasteners at every joist", "2 x DTT2Z", "both ways at every beam post", "BOTH DIRECTIONS",
                "as surveyed", "Frost 1'-0\"", "0.131 x 1-1/2 in. per manufacturer", "The same toward the house", "10'-9\" deck", "Deck surface 10'-9\" above grade",
                "flashed at the wall", "34\" min. over the nosing line; a graspable", "R507.3.2", "NEW if missing", "corrective"):
        assert bad not in alltxt, bad
    for good in ("1 confirmed (IMG_5677", "(V) — R507.9.2: within 24\" of each end", "3 stringers per flight", "LSCZ-type stringer connectors at the deck header: 2 seen (V)",
                 "PT plank at grade (V)", "a darker Vintage board (color V)", "hidden clips (CONCEALoc-type) (V)", "(10) 0.131\" x 2-1/2\"",
                 "~10'-9\" to the B1 pier tops (V)", "~12'-9\" to the B2 pier tops (V)", "cantilever", "not visible (V)", "~38\" over the nosings (V)"):
        assert good in alltxt, good
    g = _txt(sheets["G-001"])
    for k in ("B.P. 157826", "DEFERRED SUBMITTALS", "None.", "PERSON IN RESPONSIBLE CHARGE", "Engineer of record (engineered portions): [name, CA license no.] (V).",
              "Non-conventional", "owner-builder", "VICINITY MAP", "12\" min. below undisturbed grade (CRC R403.1.4)", "including the extension to the south"):
        assert k in g, k
    notes = " ".join(_txt(sheets[n]) for n in sheets if n.startswith("G-00") and n != "G-001")
    assert "(10) 0.131\" x 2-1/2\" nails" in notes and "(8) 1/4\" x 1-1/2\" SDS" in notes and "NEW" not in notes


def test_messner_geometry_drawn_true(messner):
    """Piers ~13" round at two levels (the outer row ~2' below the inner), the house's main floor cantilevered past a set-back
    basement wall, nothing invented on the house, 3 stringers a flight."""
    spec, ext, t, S, sheets = messner
    L = t.layout
    rows = MX.beam_rows(L)
    piers = [b for b in S.boxes if b.kind == "footing" and "existing pier" in (b.tag or "")]
    assert len(piers) == 14 and all(abs((b.x1 - b.x0) * 12 - 13) < 0.01 for b in piers)
    tops = {r: {round(b.z1 * 12, 2) for b in piers if r in b.tag} for r in ("inner", "outer")}
    assert tops == {"inner": {32.0}, "outer": {8.0}}
    posts = {r: [b for b in S.boxes if b.kind == "post" and abs((b.y0 + b.y1) / 2 - rows[r].y * IN) < 0.3 and (b.tag or "").startswith("P")] for r in rows}
    assert len(posts["inner"]) == len(posts["outer"]) == 7
    assert abs((posts["outer"][0].z1 - posts["outer"][0].z0) - (posts["inner"][0].z1 - posts["inner"][0].z0) - 2.0) < 1e-6
    hs = [b for b in S.boxes if b.kind == "house"]
    bs = [b for b in S.boxes if b.kind == "basement"]
    assert hs and bs and all(abs(b.y1 + 33 * IN) < 1e-6 for b in bs) and all(min(h.z0 for h in hs) > b.z1 - 1e-6 for b in bs)
    assert not [b for b in S.boxes if b.kind == "glass"]
    assert len([b for b in S.boxes if b.kind == "stringer"]) == 6 and all(st.stringers == 3 for st in L.stairs)
    assert "basement wall (set back)" in _txt(sheets["A-301"]) and "BASEMENT" in _txt(sheets["A-301"])


def test_messner_true_scales_at_24x36(messner):
    """Every plan, elevation and section at a standard architectural scale of 1/4" = 1'-0" or more at 24x36, labeled with a graphic bar;
    details NOT TO SCALE; one <svg> per sheet (nothing nested for the page CSS to resize)."""
    spec, ext, t, S, sheets = messner
    ok = {lab for ipf, lab in MX.ARCH_SCALES if ipf >= 0.25}
    for num, svg in sheets.items():
        tx = _txt(svg)
        assert svg.count("<svg") == 1, num
        labs = re.findall(r"SCALE: (\S+) = 1'-0\" @ 24x36", tx)
        if num in ("S-100", "S-101", "A-101", "A-201", "A-202", "A-301"):
            assert labs and set(labs) <= ok, (num, labs)
            assert re.search(r"SCALE @ 24x36: (PLAN|ELEVATION|SECTION)", tx), num
        if num.startswith("D-") or num in ("A-002", "A-003", "S-102"):
            assert "NOT TO SCALE" in tx, num
    u, lab = MX.snap_scale(10.37)
    assert lab == "1/4\" = 1'-0\"" and abs(u - 7.2917) < 1e-3 and MX.snap_scale(5.0) == (None, "")


def test_print_sizes_and_reduced_copy(tmp_path):
    css = MX.print_css("archd")
    assert "@page{size:36in 24in;margin:0;}" in css and "width:34.2857in" in css and "height:24.0000in" in css
    assert "@page{size:17in 11in;margin:0;}" in MX.print_css("tabloid")
    spec, ext = MX.load_job(JOB)
    MX._CTX["sheet_size"] = "tabloid"
    try:
        with MX.active(spec):
            MX._CTX.update(views=[dict(kind="plan", px0=0, py0=0, w=1, h=1, u=7.29, lab="1/4\" = 1'-0\"")])
            note = MX._scale_note("S-101", "Plan · not to scale · house at the top")
    finally:
        MX._CTX.pop("sheet_size", None)
    assert note.startswith("REDUCED COPY — NOT TO SCALE") and "PLAN 1/4\" = 1'-0\"" in note


def test_site_plan_field_and_vicinity_embed_one_to_one(tmp_path):
    field = tmp_path / "C-100_submittal_field.svg"
    field.write_text('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="34.2857in" height="20.9829in" viewBox="0 0 1000 612">'
                     '<style>*{stroke:red}</style><defs><clipPath id="p1"><rect width="10" height="10"/></clipPath></defs>'
                     '<g clip-path="url(#p1)"><text x="10" y="600">SITE PLAN — SCALE: 1/8" = 1\'-0" @ 24x36</text></g></svg>')
    vic = tmp_path / "vicinity.svg"
    vic.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 220"><rect width="300" height="220"/></svg>')
    spec, ext = MX.load_job(JOB)
    ext.site_plan = {"field_svg": str(field), "vicinity_svg": str(vic)}
    with MX.active(spec):
        L = LY.build_layout(spec)
        MX._CTX.update(L=L, S=SC.build_scene(L))
        svg = MX.site_plan_sheet(field, MX.mx_sheet_meta(L))
        o = []
        MX.vicinity_block(o, 670, 6, str(vic))
        o2 = []
        MX.vicinity_block(o2, 670, 6, None)
    assert svg.count("<svg") == 1 and "<style" not in svg and 'transform="translate(0.0000,0.0000)"' in svg
    assert "SITE PLAN 1/8\" = 1'-0\"" in _txt(svg) and "url(#e" in svg
    v = "".join(o)
    assert "<svg" not in v and 'transform="translate(670.0000,20.0000)"' in v and "N.T.S." in v
    assert "VICINITY MAP — N.T.S." in "".join(o2)
