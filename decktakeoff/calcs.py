"""Structural calculation package for an elevated, ledger-attached wood deck — written for a Colorado PE to review and stamp.

Every number comes from the spec and the engine's layout (build_composite / build_takeoff): member sizes, spans, cantilevers,
post positions, column heights, beam pieces and splices, stair geometry, the inset-stair notch, louvered-roof posts. Nothing
is typed in per job. The methods:

  * Loads: 2021 IRC R301.5 / R507 (40 psf live + 10 psf dead deck, 200 lb guard, 220 lb cantilever point load for
    deflection), the site's ground snow, ASCE 7-16 wind (Vult, exposure, Kz, Kd 0.85, Kzt, Ke) and seismic (SDC), ASD load
    combinations ASCE 7-16 §2.4.1 with the NDS load-duration factor of the shortest load in each combination.
  * Members: NDS 2018 + Supplement reference design values (Tables 4A/4B/4D) with the wet-service, size, repetitive-member,
    load-duration and stability factors; bending, shear, deflection (live L/360, total with Kcr L/240, cantilevers on twice the
    overhang), bearing, column buckling (Cp) and combined axial + bending (NDS 3.9.2); bolts by the NDS yield-limit equations.
  * Analysis: every joist, beam piece, header, trimmer and rim is solved as a beam on point supports (a small Euler-Bernoulli
    finite-element solver, exact for these load types), with the live load patterned span by span (the envelope is the dead
    case plus every live span that makes the effect worse). Beam pieces are continuous over their posts and end at splices.
  * Products: Diamond Pier capacities from the Pin Foundations chart by soil (catalog.pier_capacity_lb), Simpson caps / bases
    from the job's materials research, other connectors marked "verify" where the value is a conservative catalog reading.

run_calcs(spec) -> Package (all checks: demand, capacity, ratio, PASS / FAIL / REVIEW, code section, basis);
calc_package(base_spec, options) adds the option specs' checks that differ (yard stair, louvered roof);
calc_sheets(pkg_or_spec) -> [(num, title, svg)] in the drawing set's sheet frame (the permit-set hook);
render_html(pkg, out_dir, pdf=True) -> calcs.html (+ calcs.pdf, Letter landscape) + calcs.json.

CLI: python3 -m decktakeoff.calcs base.json [--option "Option 2 — stairs to the yard=yard.json" ...] --out DIR [--pdf]
"""
from __future__ import annotations

import html as _html
import json
import math
import re
import textwrap
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ================================================================== reference data
# NDS 2018 Supplement reference design values, psi. Southern Pine (Table 4B) values are size-specific (SPIB 2013 values,
# no size factor); Douglas Fir-Larch dimension lumber (Table 4A) takes CF; DF-L timbers (Table 4D): Beams & Stringers (5"+
# thick, width more than 2" over thickness) and Posts & Timbers (5"x5"+, width not more than 2" over thickness).
_SYP1 = dict(Fv=175, Fcp=565, E=1.6e6, Emin=580_000)
_SYP2 = dict(Fv=175, Fcp=565, E=1.4e6, Emin=510_000)
SAWN = {
    ("SYP", "No.1", "4"): dict(_SYP1, Fb=1500, Fc=1650), ("SYP", "No.1", "6"): dict(_SYP1, Fb=1350, Fc=1550),
    ("SYP", "No.1", "8"): dict(_SYP1, Fb=1250, Fc=1500), ("SYP", "No.1", "10"): dict(_SYP1, Fb=1050, Fc=1450),
    ("SYP", "No.1", "12"): dict(_SYP1, Fb=1000, Fc=1350),
    ("SYP", "No.2", "4"): dict(_SYP2, Fb=1100, Fc=1450), ("SYP", "No.2", "6"): dict(_SYP2, Fb=1000, Fc=1400),
    ("SYP", "No.2", "8"): dict(_SYP2, Fb=925, Fc=1350), ("SYP", "No.2", "10"): dict(_SYP2, Fb=800, Fc=1300),
    ("SYP", "No.2", "12"): dict(_SYP2, Fb=750, Fc=1250),
    ("DF", "No.1", "dim"): dict(Fb=1000, Ft=675, Fv=180, Fcp=625, Fc=1500, E=1.7e6, Emin=620_000),
    ("DF", "No.2", "dim"): dict(Fb=900, Ft=575, Fv=180, Fcp=625, Fc=1350, E=1.6e6, Emin=580_000),
    ("DF", "No.1", "B&S"): dict(Fb=1350, Ft=675, Fv=170, Fcp=625, Fc=925, E=1.6e6, Emin=580_000),
    ("DF", "No.2", "B&S"): dict(Fb=875, Ft=425, Fv=170, Fcp=625, Fc=600, E=1.3e6, Emin=470_000),
    ("DF", "No.1", "P&T"): dict(Fb=1200, Ft=825, Fv=170, Fcp=625, Fc=1000, E=1.6e6, Emin=580_000),
    ("DF", "No.2", "P&T"): dict(Fb=750, Ft=475, Fv=170, Fcp=625, Fc=700, E=1.3e6, Emin=470_000),
}
SAWN_TABLE = {"SYP": "NDS 2018 Supp. Table 4B", "DF": "NDS 2018 Supp. Table 4A", "DF-timber": "NDS 2018 Supp. Table 4D"}
SPECIFIC_GRAVITY = {"DF": 0.50, "SYP": 0.55}           # NDS Table 12.3.3A
# DF-L dimension-lumber size factors (Table 4A): by actual width, for 2"-3" thick and 4" thick members
CF_FB = {2: {3.5: 1.5, 5.5: 1.3, 7.25: 1.2, 9.25: 1.1, 11.25: 1.0}, 4: {3.5: 1.5, 5.5: 1.3, 7.25: 1.3, 9.25: 1.2, 11.25: 1.1}}
CF_FC = {3.5: 1.15, 5.5: 1.1, 7.25: 1.05, 9.25: 1.0, 11.25: 1.0}
CD = {"D": 0.9, "L": 1.0, "S": 1.15, "W": 1.6, "E": 1.6}          # NDS Table 2.3.2
WOOD_PCF = 40.0          # wet-service treated SYP / green DF timbers, for self weight
KCR_WET = 2.0            # NDS 3.5.2 creep factor, wet service

# ASD load combinations, ASCE 7-16 §2.4.1 (Lr and R do not govern a deck; W is the signed wind effect, E the seismic effect)
COMBOS = [
    ("D", dict(D=1.0)),
    ("D + L", dict(D=1.0, L=1.0)),
    ("D + S", dict(D=1.0, S=1.0)),
    ("D + 0.75L + 0.75S", dict(D=1.0, L=0.75, S=0.75)),
    ("D + 0.6W", dict(D=1.0, W=0.6)),
    ("D + 0.75L + 0.75(0.6W) + 0.75S", dict(D=1.0, L=0.75, W=0.45, S=0.75)),
    ("0.6D + 0.6W", dict(D=0.6, W=0.6)),
    ("D + 0.7E", dict(D=1.0, E=0.7)),
    ("0.6D + 0.7E", dict(D=0.6, E=0.7)),
]

# Products. v = verified in the job's research files (materials.md / footings.md / structure.md, which cite the documents);
# otherwise a conservative catalog reading the engineer confirms ("verify" on the sheet).
PIER = {"DP-50/50": dict(up=1200, lat=600, frost=48, bolt="1/2\""), "DP-75/63": dict(up=1600, lat=600, frost=60, bolt="5/8\"")}
PIER_SRC = "Pin Foundations load chart DOC0008 (1,500 psf silts/clays; 2,000 psf sands) / ICC-ES ESR-1895"
PRODUCTS = {
    "CCQ68SDS2.5": dict(down=37815, up=6785, v=True, src="Simpson C-C-2026 CCQ (DF/SP); uplift n/a at splices"),
    "ECCQ68SDS2.5": dict(down=25780, up=3785, v=True, src="Simpson C-C-2026 ECCQ (DF/SP)"),
    "CCQ66SDS2.5": dict(down=27000, up=6785, v=False, src="Simpson C-C CCQ66 — verify"),
    "ECCQ66SDS2.5": dict(down=19000, up=3785, v=False, src="Simpson C-C ECCQ66 — verify"),
    "ABU88Z": dict(down=22405, up=4120, v=True, src="Simpson C-C-2026 (2 x 5/8\" anchors — not on a Diamond Pier)"),
    "ABU66Z": dict(down=18205, up=2475, v=True, src="Simpson C-C-2026 (1 x 5/8\" anchor)"),
    "ABW66RZ": dict(down=12935, up=1190, v=True, src="Simpson C-C-2026 (1 x 1/2\" anchor)"),
    "LUS210Z": dict(down=1000, up=500, v=False, src="Simpson C-C LUS210 (DF/SP) — conservative reading, verify"),
    "HUCQ210-2-SDS": dict(down=2500, up=1000, v=False, src="Simpson C-C HUCQ210-2-SDS — conservative reading, verify"),
    "H2.5AZ": dict(up=595, lat=110, v=False, src="Simpson C-C H2.5A (DF/SP, CD 1.6) — verify"),
    "DTT1Z": dict(tension=750, v=True, src="IRC R507.9.2 Fig. (2): 750 lb device (Simpson rates DTT1Z for it)"),
    "DTT2Z": dict(tension=1500, v=True, src="IRC R507.9.2 Fig. (1): 1,500 lb device (Simpson rates DTT2Z for it)"),
    "CS16": dict(tension=1705, v=False, src="Simpson C-C CS16 strap (DF/SP) — verify"),
    "LedgerLOK": dict(per_screw=375, v=False, src="1/2\" lag equivalence of IRC Table R507.9.1.3(1) (375 lb/fastener at 50 psf); ESR-1078 table governs"),
}
IRC_LAG_SPACING = {6: 30, 8: 23, 10: 18, 12: 15, 14: 13, 16: 11, 18: 10}      # IRC Table R507.9.1.3(1), 1/2" lags, in. o.c.


# ================================================================== design criteria
@dataclass
class Criteria:
    live_psf: float = 40.0
    dead_psf: float = 10.0
    ground_snow_psf: float = 30.0
    roof_snow_psf: float = 30.0          # Centennial Sec. 18-2-30: 30 psf non-reducible roof snow
    wind_mph: float = 115.0
    exposure: str = "C"
    Kd: float = 0.85
    Kzt: float = 1.0
    Ke: float = 1.0
    G: float = 0.85
    sdc: str = "B"
    sds: float = 0.33                    # upper bound of SDC B (ASCE 7-16 Table 11.6-1) — conservative
    R: float = 1.5
    Ie: float = 1.0
    frost_in: float = 36.0
    soil_psf: float = 1500.0
    guard_lb: float = 200.0              # IRC Table R301.5 concentrated load at the top of the guard
    cant_point_lb: float = 220.0         # IRC Table R507.6 note: deflection at the cantilever end under 220 lb
    edge_dead_plf: float = 15.0          # doubled rim + fascia + guard + drink rail at the deck edge (E)
    stair_live_psf: float = 40.0
    stair_dead_psf: float = 10.0
    rail_solidity: float = 0.35          # IRX vertical balusters: 3/4" balusters @ 4-1/2" + rails + posts

    @property
    def deck_live_psf(self) -> float:
        """IRC R507: the deck carries 40 psf live or the ground snow, whichever is more — not both."""
        return max(self.live_psf, self.ground_snow_psf)


def criteria_for(spec, exposure: Optional[str] = None) -> Criteria:
    s = spec.site
    exp = exposure or "C"
    if exposure is None:
        m = re.findall(r"[Ee]xposure (?:[Cc]ategory )?([BCD])\b", getattr(s, "wind_note", "") or "")
        if len(set(m)) == 1:
            exp = m[0]
    return Criteria(ground_snow_psf=float(s.ground_snow_psf or 0), roof_snow_psf=max(30.0, float(s.ground_snow_psf or 0)),
                    wind_mph=float(s.wind_speed_mph or 115), exposure=exp, sdc=str(s.seismic_design_category or "B"),
                    frost_in=float(s.frost_depth_in or 36), soil_psf=float(s.soil_bearing_psf or 1500))


def wind_q(c: Criteria, z_ft: float, V: Optional[float] = None) -> Tuple[float, float]:
    """ASCE 7-16 (26.10-1): velocity pressure qz (psf, strength level) and Kz at height z above grade."""
    alpha, zg = {"B": (7.0, 1200.0), "C": (9.5, 900.0), "D": (11.5, 700.0)}[c.exposure]
    z = max(15.0, min(float(z_ft), zg))
    Kz = 2.01 * (z / zg) ** (2.0 / alpha)
    V = c.wind_mph if V is None else V
    return 0.00256 * Kz * c.Kzt * c.Kd * c.Ke * V * V, Kz


# ================================================================== sections and adjusted design values (NDS 2018)
LUMBER_ACTUAL = {"2x4": (1.5, 3.5), "2x6": (1.5, 5.5), "2x8": (1.5, 7.25), "2x10": (1.5, 9.25), "2x12": (1.5, 11.25),
                 "4x4": (3.5, 3.5), "4x6": (3.5, 5.5), "4x8": (3.5, 7.25), "4x10": (3.5, 9.25), "4x12": (3.5, 11.25),
                 "6x6": (5.5, 5.5), "6x8": (5.5, 7.5), "6x10": (5.5, 9.5), "6x12": (5.5, 11.5),
                 "8x8": (7.5, 7.5), "8x10": (7.5, 9.5), "8x12": (7.5, 11.5)}   # NDS Supp. Table 1B dressed sizes (timbers 1/2" off)


def _species_key(sp: str) -> str:
    s = (sp or "").upper()
    return "SYP" if s.startswith(("SYP", "SP", "SOUTHERN")) else "DF"


def _grade_key(gr: str) -> str:
    g = (gr or "").upper().replace(" ", "")
    return "No.2" if ("#2" in g or "NO.2" in g or "NO2" in g) else "No.1"


@dataclass
class Section:
    """A sawn-lumber member, possibly built up of plies (each ply its own dressed size)."""
    nominal: str                 # "2x10", "6x10", "8x8"
    species: str                 # "SYP" | "DF"
    grade: str = "No.1"
    plies: int = 1
    wet: bool = True             # exterior deck framing: wet service (CM)
    repetitive: bool = False     # Cr 1.15 (joists 24" o.c. or less, 3+ members)
    incised: bool = False

    def __post_init__(self):
        self.species = _species_key(self.species)
        self.grade = _grade_key(self.grade)
        t, w = LUMBER_ACTUAL[self.nominal]
        self.t, self.w = t, w                 # one ply: thickness (b), width (d)
        if self.species == "DF" and t >= 5.0:
            self.cls = "P&T" if (w - t) <= 2.0 else "B&S"
            self.ref = SAWN[("DF", self.grade, self.cls)]
            self.table = SAWN_TABLE["DF-timber"]
        elif self.species == "DF":
            self.cls = "dim"
            self.ref = SAWN[("DF", self.grade, "dim")]
            self.table = SAWN_TABLE["DF"]
        else:
            self.cls = "dim"
            wkey = {3.5: "4", 5.5: "6", 7.25: "8", 9.25: "10", 11.25: "12"}.get(w, "10")
            self.ref = SAWN[("SYP", self.grade, wkey)]
            self.table = SAWN_TABLE["SYP"]

    # geometry (strong axis: depth = w, width = plies x t)
    @property
    def b(self) -> float:
        return self.plies * self.t

    @property
    def d(self) -> float:
        return self.w

    @property
    def A(self) -> float:
        return self.b * self.d

    @property
    def S(self) -> float:
        return self.b * self.d ** 2 / 6.0

    @property
    def I(self) -> float:
        return self.b * self.d ** 3 / 12.0

    @property
    def weight_plf(self) -> float:
        return self.A / 144.0 * WOOD_PCF

    @property
    def label(self) -> str:
        sp = {"SYP": "SYP", "DF": "DF-L"}[self.species]
        nm = f"({self.plies}){self.nominal}" if self.plies > 1 else self.nominal
        return f"{nm} {sp} {self.grade}" + (f" {self.cls}" if self.cls != "dim" else "")

    # adjustment factors
    def _cf(self, prop: str) -> float:
        if self.species != "DF":
            return 1.0
        if self.cls != "dim":
            return min(1.0, (12.0 / self.d) ** (1 / 9)) if prop == "Fb" and self.d > 12 else 1.0
        if prop == "Fb":
            return CF_FB[4 if self.t >= 3.5 else 2].get(self.w, 1.0)
        if prop == "Fc":
            return CF_FC.get(self.w, 1.0)
        return 1.0

    def _cm(self, prop: str) -> float:
        if not self.wet:
            return 1.0
        if self.cls != "dim":
            return {"Fb": 1.0, "Fv": 1.0, "Fcp": 0.67, "Fc": 0.91, "E": 1.0, "Emin": 1.0}[prop]
        if prop == "Fb":
            return 0.85 if self.ref["Fb"] * self._cf("Fb") > 1150 else 1.0
        if prop == "Fc":
            return 0.8 if self.ref["Fc"] * self._cf("Fc") > 750 else 1.0
        return {"Fv": 0.97, "Fcp": 0.67, "E": 0.9, "Emin": 0.9}[prop]

    def _ci(self, prop: str) -> float:
        if not self.incised:
            return 1.0
        return {"Fb": 0.8, "Fv": 0.8, "Fc": 0.8, "Fcp": 1.0, "E": 0.95, "Emin": 0.95}[prop]

    def Fb(self, cd: float = 1.0, CL: float = 1.0) -> float:
        cr = 1.15 if (self.repetitive and self.cls == "dim") else 1.0
        return self.ref["Fb"] * cd * self._cm("Fb") * self._cf("Fb") * self._ci("Fb") * cr * CL

    def Fv(self, cd: float = 1.0) -> float:
        return self.ref["Fv"] * cd * self._cm("Fv") * self._ci("Fv")

    def Fcp(self) -> float:
        return self.ref["Fcp"] * self._cm("Fcp")

    def E(self) -> float:
        return self.ref["E"] * self._cm("E") * self._ci("E")

    def Emin(self) -> float:
        return self.ref["Emin"] * self._cm("Emin") * self._ci("Emin")

    def Fc_star(self, cd: float = 1.0) -> float:
        return self.ref["Fc"] * cd * self._cm("Fc") * self._cf("Fc") * self._ci("Fc")

    def Cp(self, le: float, cd: float = 1.0) -> Tuple[float, float]:
        """NDS 3.7.1 column stability factor and FcE, buckling about the least dimension (a built-up column is not
        treated as solid: plies are taken as one solid section only for a single member)."""
        dmin = min(self.t if self.plies == 1 else self.b, self.d)
        FcE = 0.822 * self.Emin() / (le / dmin) ** 2
        Fcs = self.Fc_star(cd)
        a = FcE / Fcs
        c = 0.8
        cp = (1 + a) / (2 * c) - math.sqrt(((1 + a) / (2 * c)) ** 2 - a / c)
        return cp, FcE

    def factors_text(self, prop: str, cd: float = 1.0) -> str:
        cr = 1.15 if (self.repetitive and self.cls == "dim" and prop == "Fb") else 1.0
        parts = [f"{self.ref[prop if prop != 'Fcp' else 'Fcp']:,.0f}", f"CD {cd:g}", f"CM {self._cm(prop):g}"]
        if prop in ("Fb", "Fc") and self._cf(prop) != 1.0:
            parts.append(f"CF {self._cf(prop):g}")
        if cr != 1.0:
            parts.append("Cr 1.15")
        if self.incised and self._ci(prop) != 1.0:
            parts.append(f"Ci {self._ci(prop):g}")
        return " x ".join(parts)


def section(size: str, species: str, grade: str = "No.1", **kw) -> Section:
    """'(2)2x10' / '2x10' / '6x10' -> Section."""
    s = size.replace(" ", "")
    plies = 1
    if s.startswith("(") and ")" in s:
        plies = int(s[1:s.index(")")]); s = s[s.index(")") + 1:]
    return Section(s, species, grade, plies=plies, **kw)


# ================================================================== a beam on point supports (Euler-Bernoulli, banded FE)
@dataclass
class BeamResult:
    x: List[float]               # node positions (in)
    M: List[float]               # bending moment at the nodes, sagging + (lb-in)
    Vl: List[float]              # shear just left / right of each node (lb), + = left part pushed up
    Vr: List[float]
    v: List[float]               # deflection at the nodes, down + (in)
    R: List[float]               # support reactions, up + (lb), in support order

    def __add__(self, o: "BeamResult") -> "BeamResult":
        return BeamResult(self.x, *[[a + b for a, b in zip(p, q)] for p, q in ((self.M, o.M), (self.Vl, o.Vl), (self.Vr, o.Vr), (self.v, o.v), (self.R, o.R))])

    def scale(self, k: float) -> "BeamResult":
        return BeamResult(self.x, *[[a * k for a in p] for p in (self.M, self.Vl, self.Vr, self.v, self.R)])


def zero_result(x: List[float], n_sup: int) -> BeamResult:
    z = [0.0] * len(x)
    return BeamResult(x, list(z), list(z), list(z), list(z), [0.0] * n_sup)


class BeamModel:
    """x0..x1 (in), rigid point supports at `supports` (in), constant EI (lb-in^2). Loads per case: ("u", a, b, w lb/in) or
    ("p", x, P lb), down positive. The mesh holds every support and every load boundary, so the nodal results are exact for
    point loads and uniform segments (moments and shears by statics from the reactions)."""

    def __init__(self, x0: float, x1: float, supports: Sequence[float], EI: float, cases: Dict[str, list], mesh: float = 3.0):
        self.x0, self.x1, self.EI = float(x0), float(x1), float(EI)
        self.sup = sorted(float(s) for s in supports)
        pts = {self.x0, self.x1, *self.sup}
        for loads in cases.values():
            for ld in loads:
                if ld[0] == "u":
                    pts.update((max(self.x0, min(self.x1, ld[1])), max(self.x0, min(self.x1, ld[2]))))
                else:
                    pts.add(max(self.x0, min(self.x1, ld[1])))
        base = sorted(pts)
        xs = [base[0]]
        for a, b in zip(base, base[1:]):
            if b - a < 1e-6:
                continue
            n = max(1, int(math.ceil((b - a) / mesh - 1e-9)))
            xs += [a + (b - a) * k / n for k in range(1, n + 1)]
        self.x = xs
        self.n = len(xs)
        self.si = [min(range(self.n), key=lambda i: abs(xs[i] - s)) for s in self.sup]
        self._factor()
        self.results = {k: self._solve(v) for k, v in cases.items()}

    def _ke(self, h: float):
        k = self.EI / h ** 3
        return [[12 * k, 6 * h * k, -12 * k, 6 * h * k], [6 * h * k, 4 * h * h * k, -6 * h * k, 2 * h * h * k],
                [-12 * k, -6 * h * k, 12 * k, -6 * h * k], [6 * h * k, 2 * h * h * k, -6 * h * k, 4 * h * h * k]]

    def _factor(self):
        N = 2 * self.n
        bw = 3
        K = [[0.0] * N for _ in range(N)]
        for e in range(self.n - 1):
            ke = self._ke(self.x[e + 1] - self.x[e])
            dof = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
            for a in range(4):
                for b in range(4):
                    K[dof[a]][dof[b]] += ke[a][b]
        self.K = [row[:] for row in K]
        self.fixed = {2 * i for i in self.si}
        for d in self.fixed:
            for j in range(max(0, d - bw), min(N, d + bw + 1)):
                K[d][j] = 0.0; K[j][d] = 0.0
            K[d][d] = 1.0
        # banded Cholesky
        L = [[0.0] * N for _ in range(N)]
        for i in range(N):
            for j in range(max(0, i - bw), i + 1):
                s = K[i][j] - sum(L[i][k] * L[j][k] for k in range(max(0, i - bw, j - bw), j))
                if i == j:
                    if s <= 0:
                        raise ValueError("beam model is unstable (needs two supports, or one support and no load)")
                    L[i][i] = math.sqrt(s)
                else:
                    L[i][j] = s / L[j][j]
        self.L, self.N, self.bw = L, N, bw

    def _loadvec(self, loads) -> List[float]:
        f = [0.0] * self.N
        for ld in loads:
            if ld[0] == "p":
                i = min(range(self.n), key=lambda k: abs(self.x[k] - ld[1]))
                f[2 * i] += ld[2]
            else:
                a, b, w = max(self.x0, ld[1]), min(self.x1, ld[2]), ld[3]
                for e in range(self.n - 1):
                    xa, xb = self.x[e], self.x[e + 1]
                    if xa >= a - 1e-9 and xb <= b + 1e-9:
                        h = xb - xa
                        f[2 * e] += w * h / 2; f[2 * e + 1] += w * h * h / 12
                        f[2 * e + 2] += w * h / 2; f[2 * e + 3] -= w * h * h / 12
        return f

    def _solve(self, loads) -> BeamResult:
        f = self._loadvec(loads)
        fc = [0.0 if i in self.fixed else f[i] for i in range(self.N)]
        L, N, bw = self.L, self.N, self.bw
        y = [0.0] * N
        for i in range(N):
            y[i] = (fc[i] - sum(L[i][k] * y[k] for k in range(max(0, i - bw), i))) / L[i][i]
        u = [0.0] * N
        for i in range(N - 1, -1, -1):
            u[i] = (y[i] - sum(L[k][i] * u[k] for k in range(i + 1, min(N, i + bw + 1)))) / L[i][i]
        R = []
        for i in self.si:
            d = 2 * i
            r = sum(self.K[d][j] * u[j] for j in range(max(0, d - bw), min(N, d + bw + 1))) - f[d]
            R.append(-r)
        # statics from the left: reactions, point loads, uniform segments
        pts = [(s, r) for s, r in zip(self.sup, R)] + [(ld[1], -ld[2]) for ld in loads if ld[0] == "p"]
        uds = [(max(self.x0, ld[1]), min(self.x1, ld[2]), ld[3]) for ld in loads if ld[0] == "u"]
        M, Vl, Vr = [], [], []
        for xx in self.x:
            m = sum(F * (xx - xp) for xp, F in pts if xp < xx - 1e-9)
            vl = sum(F for xp, F in pts if xp < xx - 1e-9)
            vr = sum(F for xp, F in pts if xp <= xx + 1e-9)
            for a, b, w in uds:
                if xx > a:
                    e = min(xx, b)
                    if e > a:
                        m -= w * (e - a) * (xx - (a + e) / 2)
                        vl -= w * (e - a); vr -= w * (e - a)
            M.append(m); Vl.append(vl); Vr.append(vr)
        return BeamResult(self.x, M, Vl, Vr, [u[2 * i] for i in range(self.n)], R)


def envelope(dead: BeamResult, lives: Sequence[BeamResult], k_live: float = 1.0) -> Tuple[BeamResult, BeamResult]:
    """(max, min) of dead + k x (every subset of the live cases), point by point: the worst pattern adds each live case
    exactly where it makes the effect worse."""
    mx = BeamResult(dead.x, *[list(a) for a in (dead.M, dead.Vl, dead.Vr, dead.v, dead.R)])
    mn = BeamResult(dead.x, *[list(a) for a in (dead.M, dead.Vl, dead.Vr, dead.v, dead.R)])
    for lv in lives:
        for attr in ("M", "Vl", "Vr", "v", "R"):
            A, B, C = getattr(mx, attr), getattr(mn, attr), getattr(lv, attr)
            for i, c in enumerate(C):
                if c > 0:
                    A[i] += k_live * c
                else:
                    B[i] += k_live * c
    return mx, mn
