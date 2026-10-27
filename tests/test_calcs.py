"""decktakeoff.calcs: the solver against closed-form beams, NDS values, the yield model, and full packages from specs."""
import json
import math
import re

import pytest

from decktakeoff import calcs
from decktakeoff.spec import DeckSpec

EI = 1.6e6 * 98.9


def test_beam_solver_matches_closed_form():
    m = calcs.BeamModel(0, 120.0, [0, 120.0], EI, {"u": [("u", 0, 120.0, 1.0)], "p": [("p", 60.0, 100.0)]})
    i = min(range(m.n), key=lambda k: abs(m.x[k] - 60))
    u, p = m.results["u"], m.results["p"]
    assert u.R == pytest.approx([60.0, 60.0]) and u.M[i] == pytest.approx(1800.0)
    assert u.v[i] == pytest.approx(5 * 120.0 ** 4 / (384 * EI))
    assert p.M[i] == pytest.approx(3000.0) and p.v[i] == pytest.approx(100 * 120.0 ** 3 / (48 * EI))
    # overhang: R1 = wL/2 - wa^2/2L, tip deflection AISC case 24
    L, a = 100.0, 25.0
    m = calcs.BeamModel(0, L + a, [0, L], EI, {"u": [("u", 0, L + a, 1.0)], "tip": [("p", L + a, 100.0)]})
    assert m.results["u"].R == pytest.approx([L / 2 - a * a / (2 * L), L + a - (L / 2 - a * a / (2 * L))])
    assert m.results["u"].v[-1] == pytest.approx(a / (24 * EI) * (4 * a * a * L - L ** 3 + 3 * a ** 3))
    assert m.results["tip"].v[-1] == pytest.approx(100 * a * a * (L + a) / (3 * EI))
    # two equal continuous spans: 3/8, 10/8, 3/8 and -wL^2/8 over the middle support
    m = calcs.BeamModel(0, 192.0, [0, 96.0, 192.0], EI, {"u": [("u", 0, 192.0, 1.0)]})
    r = m.results["u"]
    assert r.R == pytest.approx([36.0, 120.0, 36.0]) and r.M[m.si[1]] == pytest.approx(-1152.0)


def test_pattern_envelope_takes_the_worst_spans():
    r = calcs.run_member(calcs.section("6x10", "DF"), 0, 192.0, [0, 96.0, 192.0], [("u", 0, 192.0, 1.0)], [("u", 0, 192.0, 1.0)])
    mx, mn = calcs.envelope(r.dead, r.lives)
    assert mx.R[1] == pytest.approx(240.0)             # live on both spans
    assert mx.R[0] == pytest.approx(36.0 + 42.0)       # live on the first span only: 7/16 wL
    assert mn.R[2] == pytest.approx(36.0 - 6.0)        # live on the far span lifts this end by wL/16


def test_nds_adjusted_values():
    j = calcs.section("2x10", "SYP", "#1 True Frame GC", repetitive=True)
    assert j.ref["Fb"] == 1050 and j.Fb() == pytest.approx(1050 * 1.15)      # Fb x CF-free SYP value x Cr; CM 1.0 (Fb <= 1,150)
    assert j.Fv() == pytest.approx(175 * 0.97) and j.Fcp() == pytest.approx(565 * 0.67) and j.E() == pytest.approx(1.6e6 * 0.9)
    b = calcs.section("6x10", "DF", "DF#1")
    assert b.cls == "B&S" and b.Fb() == 1350 and b.Fcp() == pytest.approx(625 * 0.67) and (b.b, b.d) == (5.5, 9.5)
    c = calcs.section("8x8", "DF", "DF#1")
    assert c.cls == "P&T" and c.Fc_star() == pytest.approx(1000 * 0.91)
    cp, FcE = c.Cp(96.0)
    assert 0.0 < cp < 1.0 and FcE == pytest.approx(0.822 * 580000 / (96 / 7.5) ** 2)


def test_bolt_yield_model_and_pole_embedment():
    # 1/2" bolt, 1-1/2" DF side member, 3-1/2" DF main member, parallel to grain: Mode IIIs governs (NDS Table 12A ~ 610 lb)
    assert calcs.bolt_Z(0.5, 1.5, 3.5, 0.5, 0.5) == pytest.approx(615, abs=5)
    assert calcs.bolt_Z(0.5, 1.5, 3.5, 0.5, 0.5, 90, 90) < calcs.bolt_Z(0.5, 1.5, 3.5, 0.5, 0.5)
    d = calcs.pole_embedment(270.0, 0.5, 20 / 12.0)
    S1 = 2 * 100 * d / 3
    A = 2.34 * 270 / (S1 * 20 / 12.0)
    assert d == pytest.approx(0.5 * A * (1 + math.sqrt(1 + 4.36 * 0.5 / A)), rel=1e-3)


def test_combinations_pick_the_governing_one():
    comp = {"D": (500.0, 500.0), "L": (1500.0, 0.0), "S": (1200.0, 1200.0), "W": (800.0, -1400.0)}
    names = [n for n, *_ in calcs.combine(comp)]
    assert "D + 0.75L + 0.75(0.6W) + 0.75S" in names and "0.6D + 0.6W" in names
    r, nm, e, cap = calcs.governing(comp, lambda cd: 2000.0 * cd, sign=1)
    assert e > 0 and r == pytest.approx(max(emax / (2000.0 * cd) for _, cd, emax, _ in calcs.combine(comp)))
    r, nm, e, cap = calcs.governing(comp, lambda cd: 1000.0, sign=-1)
    assert nm == "0.6D + 0.6W" and e == pytest.approx(0.6 * 500 - 0.6 * 1400)


def test_single_deck_package():
    spec = DeckSpec.from_dict(json.load(open("examples/jason_ct.json")))
    pkg = calcs.run_calcs(spec)
    groups = {c.group for c in pkg.checks}
    assert {"Joists & cantilevers", "Ledger & hangers", "Beams", "Columns", "Footings", "Lateral system"} <= groups
    assert not [c for c in pkg.checks if c.result == "FAIL"]
    j1 = next(c for c in pkg.checks if c.id.startswith("J-") and c.id.endswith(".1"))
    assert j1.unit == "psi" and 0 < j1.ratio < 1 and "F'b" in j1.basis
    assert all(c.code for c in pkg.checks) and all(c.result in ("PASS", "FAIL", "REVIEW", "INFO") for c in pkg.checks)


TWO_LEVELS = {
    "job": "calc test — two levels", "client": "Test",
    "site": {"address": "1 Test Ct", "city": "Centennial", "state": "CO", "ground_snow_psf": 30, "wind_speed_mph": 115,
             "soil_bearing_psf": 1500, "frost_depth_in": 36},
    "geometry": {"height_in": 66, "parts": [
        {"name": "Lower level", "placement": {"origin": [0, 0]},
         "geometry": {"height_in": 66, "zones": [{"name": "B", "width": 20, "depth": 10}]}, "railing": {"edges": ["front:B"]}},
        {"name": "Upper level", "placement": {"origin": [20, 0]},
         "geometry": {"height_in": 102, "zones": [{"name": "C", "width": 20, "depth": 10}]}, "railing": {"edges": ["front:C"]}}]},
    "framing": {"joist_size": "2x10", "joist_species": "SYP", "joist_spacing_in": 12, "post_size": "8x8", "post_species": "DF#1", "post_rough": True,
                "footing_type": "caisson", "caisson_dia_in": 20, "caisson_depth_in": 42,
                "beams": [{"kind": "drop", "size": "6x10", "species": "DF", "setback_in": 20}]},
    "decking": {"collection": "Vintage", "color": "English Walnut"},
    "railing": {"system": "IRX Baluster", "color": "Black"},
}


def test_two_level_composite_package_and_options():
    base = DeckSpec.from_dict(TWO_LEVELS)
    pkg = calcs.run_calcs(base)
    tags = {c.id.split("-")[1][:1] for c in pkg.checks if c.id.startswith("J-")}
    assert tags == {"L", "U"}                                   # both parts analysed, each zone's joists
    cols = [c for c in pkg.columns if c["kind"] == "beam"]
    assert cols and all(c["height_in"] > 0 for c in cols)
    up = [c for c in cols if c["part"] == "Upper level"]
    lo = [c for c in cols if c["part"] == "Lower level"]
    assert up[0]["height_in"] - lo[0]["height_in"] == pytest.approx(36.0, abs=0.5)     # the column heights follow the spec's height_in
    f = [c for c in pkg.checks if c.group == "Footings" and c.what.startswith("Caisson bearing")]
    assert len(f) == len(cols) and all(c.capacity == pytest.approx(math.pi * (20 / 24) ** 2 * 1500 + math.pi * 20 / 12 * 42 / 12 * 400, rel=1e-3) for c in f)
    assert not [c for c in pkg.checks if "Pin Foundations" in c.code or "ESR-1895" in c.code]     # caissons: no pier references
    # an option that adds a roof brings only its own and its changed checks
    d = json.loads(json.dumps(TWO_LEVELS))
    d["geometry"]["louvered_roofs"] = [{"x0": 20.5, "x1": 39.5, "y0": 0, "y1": 10, "attach": "house", "price_per_sf": 175}]
    pkg2 = calcs.calc_package(base, [("Option — roof", DeckSpec.from_dict(d))])
    opt = [c for c in pkg2.checks if c.scope == "Option — roof"]
    assert opt and any(c.group == "Louvered roof load path" for c in opt)
    assert all(c.scope in ("Base", "Option — roof") for c in pkg2.checks)
    assert len(pkg2.checks) < 2 * len(pkg.checks)


def test_sheets_and_html(tmp_path):
    pkg = calcs.run_calcs(DeckSpec.from_dict(TWO_LEVELS))
    sheets = calcs.calc_sheets(pkg)
    assert sheets[0][0] == "S-901" and all(re.match(r"S-9\d\d$", n) for n, _, _ in sheets)
    for n, t, svg in sheets:
        assert svg.startswith("<svg") and "$" not in svg and 'viewBox="0 0 1000 700"' in svg
    # the permit set rewrites the drawing sheets' revision line: the calc sheets carry the same pattern
    assert re.search(r"GS Exterior Experts · [A-Z][a-z]+ \d{1,2}, \d{4} · Rev 0", sheets[0][2])
    r = calcs.render_html(pkg, str(tmp_path), pdf=False)
    page = open(r["html"]).read()
    assert "<title>Structural Calculations</title>" in page and page.count('class="sheet-page"') + page.count("class='sheet-page'") == len(sheets)
    data = json.load(open(r["json"]))
    assert data["counts"] == pkg.counts() and len(data["checks"]) == len(pkg.checks)


def test_steel_frame_is_outside_this_calc():
    pkg = calcs.run_calcs(DeckSpec.from_dict(json.load(open("jobs/jefferson_louisville.json"))))
    assert [c.result for c in pkg.checks] == ["REVIEW"]
