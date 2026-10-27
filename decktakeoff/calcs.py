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
  * Footings follow the spec's footing_type: caissons / concrete piers (the engine's end bearing + skin-friction capacity,
    uplift by the shaft's weight, IBC 1807.3.2.1 lateral embedment, frost depth) or Diamond Piers (Pin Foundations chart by
    soil, catalog.pier_capacity_lb). Simpson caps / bases from the job's materials research; other connectors are marked
    "verify" where the value is a conservative catalog reading.

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
JOIST_STICK_MAX = 240.0  # 20' stock: a longer joist run is spliced over an interior beam (GSX practice; structure.md)

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
    "ABU88RZ": dict(down=19870, up=4045, v=True, src="Simpson C-C-2026, rough 8x8 (2 x 5/8\" anchors)"),
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


def section_size(size: str) -> str:
    """'(2)2x10' -> '2x10'."""
    s = (size or "").replace(" ", "")
    return s[s.index(")") + 1:] if s.startswith("(") and ")" in s else s


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


# ================================================================== checks and the package
GROUPS = ["Joists & cantilevers", "Ledger & hangers", "Beams", "Columns", "Caps & bases", "Footings", "Lateral system",
          "Inset stair & notch", "Stairs to the yard", "Louvered roof load path", "Guards"]


@dataclass
class Check:
    id: str
    group: str
    member: str
    what: str
    demand: float
    capacity: float
    unit: str
    code: str
    basis: str = ""
    status: str = ""             # "" -> PASS / FAIL from the ratio; "REVIEW" / "INFO" set by the check
    scope: str = "Base"
    tags: List[str] = field(default_factory=list)
    note: str = ""

    @property
    def ratio(self) -> float:
        if not self.capacity:
            return 0.0 if (not self.demand or self.status in ("INFO", "REVIEW")) else 9.99
        return abs(self.demand) / abs(self.capacity)

    @property
    def result(self) -> str:
        if self.status:
            return self.status
        return "PASS" if self.ratio <= 1.0 + 1e-6 else "FAIL"

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(ratio=round(self.ratio, 3), result=self.result)
        return d


@dataclass
class Package:
    job: str
    address: str
    client: str
    prepared: str
    criteria: Criteria
    criteria_rows: List[Tuple[str, str, str]]
    load_rows: List[Tuple[str, str, str]]
    material_rows: List[Tuple[str, str, str]]
    checks: List[Check]
    columns: List[dict]
    assumptions: List[str]
    review: List[str]
    sources: List[str]
    scopes: List[str]
    method: List[str] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for c in self.checks:
            out[c.result] = out.get(c.result, 0) + 1
        return out

    def to_dict(self) -> dict:
        return dict(job=self.job, address=self.address, client=self.client, prepared=self.prepared, criteria=asdict(self.criteria),
                    criteria_rows=self.criteria_rows, load_rows=self.load_rows, material_rows=self.material_rows,
                    checks=[c.to_dict() for c in self.checks], columns=self.columns, assumptions=self.assumptions,
                    review=self.review, sources=self.sources, scopes=self.scopes, method=self.method, counts=self.counts())


def _f(v: float, unit: str) -> str:
    """A number as the sheet prints it."""
    if unit == "in":
        return f"{v:.2f}\"" if abs(v) < 10 else f"{v:,.1f}\""
    if unit == "ft":
        return f"{v:,.2f}'"
    if unit in ("lb", "lb-in", "plf", "psi", "lb-ft"):
        return f"{v:,.0f} {unit}"
    if unit == "-":
        return f"{v:.2f}"
    return f"{v:,.2f} {unit}".strip()


def _ftin(v_in: float) -> str:
    v = abs(v_in)
    ft = int(v // 12)
    inch = v - 12 * ft
    s = f"{ft}'-{inch:.1f}\"" if ft else f"{inch:.1f}\""
    return s.replace(".0\"", "\"")


# ================================================================== combinations
def _cd_of(f: Dict[str, float]) -> float:
    return max(CD[k] for k in f)


def combine(comp: Dict[str, Tuple[float, float]]) -> List[Tuple[str, float, float, float]]:
    """ASD combinations of load effects. comp: load type -> (largest, smallest) effect of that load at the point (a patterned
    live load or a wind that can push or pull gives a range). Returns [(combination, CD, max effect, min effect)] for the
    combinations whose variable loads are all present (an absent load leaves a combination equal to a simpler one)."""
    out = []
    have = {k for k, (a, b) in comp.items() if abs(a) > 1e-9 or abs(b) > 1e-9}
    for name, f in COMBOS:
        var = [k for k in f if k != "D"]
        if var and not all(k in have for k in var):
            continue
        emax = sum(c * (comp.get(k, (0.0, 0.0))[0] if c > 0 else comp.get(k, (0.0, 0.0))[1]) for k, c in f.items())
        emin = sum(c * (comp.get(k, (0.0, 0.0))[1] if c > 0 else comp.get(k, (0.0, 0.0))[0]) for k, c in f.items())
        out.append((name, _cd_of(f), emax, emin))
    return out


def governing(comp: Dict[str, Tuple[float, float]], cap_at_cd, sign: int = 0) -> Tuple[float, str, float, float]:
    """The worst ratio |effect| / capacity(CD) over the combinations. sign +1: only positive effects (down / compression),
    -1: only negative (uplift), 0: either. Returns (ratio, combination, effect, capacity)."""
    best = (0.0, "—", 0.0, cap_at_cd(1.0))
    for name, cd, emax, emin in combine(comp):
        cands = []
        if sign >= 0 and emax > 0:
            cands.append(emax)
        if sign <= 0 and emin < 0:
            cands.append(emin)
        if sign == 0:
            cands = [emax, emin]
        for e in cands:
            cap = cap_at_cd(cd)
            r = abs(e) / cap if cap else 9.99
            if r > best[0]:
                best = (r, name, e, cap)
    return best


# ================================================================== member runs (a member on its supports under its loads)
@dataclass
class Run:
    sec: Section
    x0: float
    x1: float
    supports: List[float]
    model: BeamModel
    dead: BeamResult
    lives: List[BeamResult]
    segs: List[Tuple[float, float]]
    other: Dict[str, BeamResult]

    def comp_at(self, attr: str, i: int, extra: Sequence[str] = ("S", "Wd", "Wu")) -> Dict[str, Tuple[float, float]]:
        """Load-type ranges of response `attr` (M, Vl, Vr, v, R) at node / support i."""
        d = getattr(self.dead, attr)[i]
        lp = sum(max(0.0, getattr(l, attr)[i]) for l in self.lives)
        ln = sum(min(0.0, getattr(l, attr)[i]) for l in self.lives)
        comp = {"D": (d, d), "L": (lp, ln)}
        if "S" in self.other:
            s = getattr(self.other["S"], attr)[i]
            comp["S"] = (s, s)
        wd = getattr(self.other["Wd"], attr)[i] if "Wd" in self.other else 0.0
        wu = getattr(self.other["Wu"], attr)[i] if "Wu" in self.other else 0.0
        if wd or wu:
            comp["W"] = (max(wd, wu), min(wd, wu))
        return comp

    def span_of(self, i: int) -> Tuple[float, float, bool]:
        """The span (a, b) node i lies in and whether it is an overhang."""
        xx = self.model.x[i]
        s = self.supports
        if xx < s[0] - 1e-6:
            return (self.x0, s[0], True)
        if xx > s[-1] + 1e-6:
            return (s[-1], self.x1, True)
        for a, b in zip(s, s[1:]):
            if a - 1e-6 <= xx <= b + 1e-6:
                return (a, b, False)
        return (s[0], s[-1], False)


def run_member(sec: Section, x0: float, x1: float, supports: Sequence[float], dead: list, live: list,
               other: Optional[Dict[str, list]] = None, mesh: float = 3.0) -> Run:
    """Solve a member: `dead` and `live` load lists (("u", a, b, w) / ("p", x, P)); the live load is split by span
    (overhangs are spans too) so the envelope can pattern it. `other`: extra cases by name (S, Wd, Wu, P220 ...)."""
    sup = sorted(float(s) for s in supports)
    bounds = [x0] + [s for s in sup if x0 + 1e-6 < s < x1 - 1e-6] + [x1]
    segs = list(zip(bounds, bounds[1:]))
    cases: Dict[str, list] = {"D": list(dead)}
    for k, (a, b) in enumerate(segs):
        cl = []
        for ld in live:
            if ld[0] == "u":
                lo, hi = max(a, ld[1]), min(b, ld[2])
                if hi > lo + 1e-9:
                    cl.append(("u", lo, hi, ld[3]))
            elif a - 1e-9 <= ld[1] < b - 1e-9 or (k == len(segs) - 1 and abs(ld[1] - b) < 1e-9):
                cl.append(ld)
        cases[f"L{k}"] = cl
    for k, v in (other or {}).items():
        cases[k] = list(v)
    m = BeamModel(x0, x1, sup, sec.E() * sec.I, cases, mesh=mesh)
    lives = [m.results[f"L{k}"] for k in range(len(segs))]
    oth = {k: m.results[k] for k in (other or {})}
    return Run(sec, x0, x1, sup, m, m.results["D"], lives, segs, oth)


def flexure_checks(r: Run, cid: str, group: str, member: str, scope: str, code_b: str = "NDS 2018 3.3, 4.3", CL: float = 1.0,
                   defl_live: float = 360.0, defl_total: float = 240.0, tags: Optional[List[str]] = None,
                   cant_limit: float = 180.0, note: str = "") -> List[Check]:
    """Bending, shear, live and total deflection (spans and overhangs) of a solved member, governing combination."""
    sec = r.sec
    tags = tags or []
    out: List[Check] = []
    n = len(r.model.x)
    # bending
    best = (0.0, "—", 0.0, 1.0, 0)
    for i in range(n):
        rr, nm, e, cap = governing(r.comp_at("M", i), lambda cd: sec.Fb(cd, CL) * sec.S)
        if rr > best[0]:
            best = (rr, nm, e, cap, i)
    rr, nm, M, capM, i = best
    cdv = dict(COMBO_CD).get(nm, 1.0)
    out.append(Check(f"{cid}.1", group, member, "Bending", abs(M) / sec.S, capM / sec.S, "psi", f"{code_b}; {sec.table}",
                     f"M = {abs(M):,.0f} lb-in at {r.model.x[i]:.1f}\" ({nm}{', live patterned' if r.lives else ''}) · fb = M/S = {abs(M):,.0f}/{sec.S:.2f} = {abs(M) / sec.S:,.0f} psi · "
                     f"F'b = {sec.factors_text('Fb', cdv)}{' x CL ' + format(CL, 'g') if CL != 1 else ''} = {capM / sec.S:,.0f} psi", scope=scope, tags=tags, note=note))
    # shear
    best = (0.0, "—", 0.0, 1.0, 0)
    for i in range(n):
        for attr in ("Vl", "Vr"):
            rr, nm, e, cap = governing(r.comp_at(attr, i), lambda cd: sec.Fv(cd) * sec.A / 1.5)
            if rr > best[0]:
                best = (rr, nm, e, cap, i)
    rr, nm, V, capV, i = best
    cdv = dict(COMBO_CD).get(nm, 1.0)
    out.append(Check(f"{cid}.2", group, member, "Shear", 1.5 * abs(V) / sec.A, capV * 1.5 / sec.A, "psi", f"NDS 2018 3.4; {sec.table}",
                     f"V = {abs(V):,.0f} lb ({nm}; at the support face, conservative) · fv = 1.5V/bd = {1.5 * abs(V) / sec.A:,.0f} psi · F'v = {sec.factors_text('Fv', cdv)} = {capV * 1.5 / sec.A:,.0f} psi",
                     scope=scope, tags=tags))
    # deflection: live per span / overhang, and total with creep on the dead load
    worst_l = (0.0, 0.0, 0.0, "", 0)
    worst_t = (0.0, 0.0, 0.0, "", 0)
    for i in range(n):
        a, b, ovh = r.span_of(i)
        span = b - a
        if span < 6:
            continue
        lim_len = 2 * span if ovh else span                   # a cantilever's deflection limit is on twice its length (IBC Table 1604.3 note)
        if ovh:
            dl = max(abs(sum(max(0.0, l.v[i]) for l in r.lives)), abs(sum(min(0.0, l.v[i]) for l in r.lives)))
        else:
            # mid-span deflection relative to the supports (a span between two supports)
            dl = max(abs(sum(max(0.0, l.v[i]) for l in r.lives)), abs(sum(min(0.0, l.v[i]) for l in r.lives)))
        s_v = abs(r.other["S"].v[i]) if "S" in r.other else 0.0
        dl_all = dl + s_v
        lim = lim_len / defl_live
        if dl_all / lim > worst_l[0]:
            worst_l = (dl_all / lim, dl_all, lim, ("overhang " if ovh else "span ") + _ftin(span), i)
        dt = KCR_WET * abs(r.dead.v[i]) + dl_all
        limt = lim_len / defl_total
        if dt / limt > worst_t[0]:
            worst_t = (dt / limt, dt, limt, ("overhang " if ovh else "span ") + _ftin(span), i)
    if worst_l[2]:
        out.append(Check(f"{cid}.3", group, member, f"Deflection, live (L/{defl_live:g})", worst_l[1], worst_l[2], "in", "IRC Table R301.7; NDS 3.5",
                         f"Δ live = {worst_l[1]:.3f}\" ({worst_l[3]}, worst live pattern{', + roof snow' if 'S' in r.other else ''}) · limit " +
                         ("2 x " if worst_l[3].startswith("overhang") else "") + f"{worst_l[3].split(' ', 1)[1]}/{defl_live:g} = {worst_l[2]:.3f}\" · E' = {sec.E():,.0f} psi, I = {sec.I:.1f} in4",
                         scope=scope, tags=tags))
    if worst_t[2]:
        out.append(Check(f"{cid}.4", group, member, f"Deflection, total (L/{defl_total:g})", worst_t[1], worst_t[2], "in", "IRC Table R301.7; NDS 3.5.2 (Kcr 2.0 wet)",
                         f"Δ = Kcr·Δ_D + Δ_L = {worst_t[1]:.3f}\" ({worst_t[3]}) · limit {worst_t[2]:.3f}\"", scope=scope, tags=tags))
    return out


COMBO_CD = [(nm, _cd_of(f)) for nm, f in COMBOS]


def bearing_check(cid, group, member, R: float, sec_bearing: Section, width: float, length: float, scope: str, what: str = "Bearing (perp. to grain)",
                  tags=None) -> Check:
    A = width * length
    cap = sec_bearing.Fcp() * A
    return Check(cid, group, member, what, R / A, cap / A, "psi", "NDS 2018 3.10.2 (Cb = 1.0)",
                 f"R = {R:,.0f} lb on {width:g}\" x {length:g}\" = {A:.1f} in2 · fc⊥ = {R / A:,.0f} psi · F'c⊥ = {sec_bearing.ref['Fcp']:,.0f} x CM {sec_bearing._cm('Fcp'):g} = {sec_bearing.Fcp():,.0f} psi",
                 scope=scope, tags=tags or [])


# ================================================================== the analysis of one spec
class _Pl:
    """Identity placement for a single (non-composite) deck."""
    def pt(self, x, y):
        return (x, y)


@dataclass
class _Part:
    idx: int
    name: str
    tag: str
    spec: object
    L: object            # Layout
    t: object            # Takeoff
    pl: object           # Placement
    flags: list


def _tag_of(names: List[str]) -> List[str]:
    tags = []
    for i, n in enumerate(names):
        t = (n.strip()[:1] or chr(65 + i)).upper()
        if t in tags:
            t = f"{t}{i + 1}"
        tags.append(t)
    return tags if len(names) > 1 else [""]


class Calc:
    """All checks for one spec (every part of a composite)."""

    def __init__(self, spec, scope: str = "Base", exposure: Optional[str] = None):
        self.spec = spec
        self.scope = scope
        self.c = criteria_for(spec, exposure)
        self.checks: List[Check] = []
        self.cols: List[dict] = []
        self.assumptions: List[str] = []
        self.review: List[str] = []
        self.beam_pts: Dict[Tuple[int, int], List[Tuple[float, Dict[str, float], str]]] = {}
        self.beam_corr: Dict[Tuple[int, int], List[Tuple[float, float, float, float, str]]] = {}
        self.joist_R: Dict[Tuple[int, str], dict] = {}
        self.post_comp: Dict[Tuple[int, int, int], Dict[str, List[float]]] = {}
        self.roofs: List[dict] = []
        self.extra_lat: Dict[int, List[float]] = {}         # part -> [Hx, Hy] ASD lateral the roof posts bring to the deck
        self._build()

    # -------------------------------------------------------------- the model
    def _build(self):
        spec = self.spec
        if spec.geometry.parts:
            from .composite import build_composite
            t, flags = build_composite(spec)
            names = [p.name for p in t.layout.parts]
            tags = _tag_of(names)
            self.parts = [_Part(i, p.name, tags[i], p.spec, p.layout, p.takeoff, p.placement, p.flags) for i, p in enumerate(t.layout.parts)]
        else:
            from .takeoff import build_takeoff
            from .flags import run_flags
            t = build_takeoff(spec)
            flags = run_flags(t.layout)
            self.parts = [_Part(0, "Deck", "", spec, t.layout, t, _Pl(), flags)]
        self.t, self.flags = t, flags

    def add(self, ck: Check) -> Check:
        if not ck.scope or ck.scope == "Base":
            ck.scope = self.scope
        self.checks.append(ck)
        return ck

    def gxy(self, P: _Part, x_in: float, y_in: float) -> Tuple[float, float]:
        return P.pl.pt(x_in / 12.0, y_in / 12.0)

    # -------------------------------------------------------------- joists
    def joist_section(self, P: _Part) -> Section:
        fr = P.spec.framing
        return section(fr.joist_size, fr.joist_species, fr.joist_grade, repetitive=True)

    def zone_supports(self, P: _Part, z) -> Tuple[float, List[float], float]:
        """(start of the joists, supports, end) in the zone's own y (inches from its wall)."""
        fr = z.frame
        rim_t = fr.rim_plies * 1.5
        start = 1.5 if fr.ledger else rim_t
        sup = ([1.5] if fr.ledger else []) + sorted(b.cl_y for b in fr.beams)
        if P.spec.framing.edge_posts_ft:
            sup.append(z.D - rim_t / 2)
        return start, sorted(set(round(s, 3) for s in sup)), float(z.D)

    def zone_joists(self, P: _Part, z):
        c = self.c
        fr = z.frame
        sec = self.joist_section(P)
        s = float(fr.spacing)
        start, sup, end = self.zone_supports(P, z)
        tag = f"{P.tag}{z.name}"
        member = f"Zone {z.name} ({P.name}) joists {sec.label} @ {s:g}\" o.c."
        if len(sup) < 2 and not (len(sup) == 1 and end - sup[0] < 1):
            self.add(Check(f"J-{tag}", "Joists & cantilevers", member, "Support layout", 0, 0, "-", "IRC R507.6",
                           "fewer than two supports under the joists — no analysis", status="REVIEW"))
            return
        wD = c.dead_psf * s / 144.0
        wL = c.deck_live_psf * s / 144.0
        tipD = c.edge_dead_plf * s / 12.0
        dead = [("u", start, end, wD), ("p", end, tipD)]
        live = [("u", start, end, wL)]
        other = {"P220": [("p", end, c.cant_point_lb)]}
        runs = []
        # spliced over every interior support (each piece a simple span; the last one keeps the overhang) ...
        if len(sup) > 2:
            for k in range(len(sup) - 1):
                a, b = sup[k], sup[k + 1]
                last = k == len(sup) - 2
                x0 = start if k == 0 else a
                x1 = end if last else b
                dl = [("u", x0, x1, wD)] + ([("p", end, tipD)] if last else [])
                runs.append(("spliced", run_member(sec, x0, x1, [a, b], dl, [("u", x0, x1, wL)], other if last else None)))
            if end - start <= JOIST_STICK_MAX:   # ... and continuous where one stick can run
                runs.append(("continuous", run_member(sec, start, end, sup, dead, live, other)))
        else:
            runs.append(("one piece", run_member(sec, start, end, sup, dead, live, other)))
        cant = end - sup[-1]
        back = sup[-1] - sup[-2] if len(sup) > 1 else 0.0
        desc = " · ".join(_ftin(b - a) for a, b in zip(sup, sup[1:])) + (f" + {_ftin(cant)} cantilever" if cant > 1 else "")
        member = f"Zone {z.name} ({P.name}): {sec.label} @ {s:g}\" — spans {desc}"
        cks = []
        for how, r in runs:
            for ck in flexure_checks(r, f"J-{tag}", "Joists & cantilevers", member, self.scope):
                ck.basis = (f"[{how}] " if len(runs) > 1 else "") + ck.basis
                cks.append(ck)
        best: Dict[str, Check] = {}
        for ck in cks:
            if ck.id not in best or ck.ratio > best[ck.id].ratio:
                best[ck.id] = ck
        for k in sorted(best):
            self.add(best[k])
        rmain = runs[-1][1] if runs[-1][0] != "continuous" else runs[0][1]
        last = [r for how, r in runs if how != "continuous"][-1] if any(h != "continuous" for h, _ in runs) else runs[0][1]
        if cant > 1.0:
            p220 = abs(last.other["P220"].v[-1])
            self.add(Check(f"J-{tag}.5", "Joists & cantilevers", member, f"Cantilever, {c.cant_point_lb:g} lb at the end (2a/180)", p220, 2 * cant / 180.0, "in",
                           "IRC Table R507.6 note a; IBC Table 1604.3 note",
                           f"Δ = P a² (L + a) / 3EI = {p220:.3f}\" for a = {cant:.1f}\", L = {back:.1f}\" · limit 2a/180 = {2 * cant / 180:.3f}\""))
            lim4 = back / 4.0
            ck = Check(f"J-{tag}.6", "Joists & cantilevers", member, "Cantilever length (L/4)", cant, lim4, "in", "IRC R507.6 / Table R507.6; DCA6",
                       f"cantilever {cant:.1f}\" vs back-span {back:.1f}\"/4 = {lim4:.1f}\"")
            if ck.ratio > 1.0:
                ck.status = "REVIEW"
                ck.note = "beyond the prescriptive L/4: the strength and deflection rows above govern; engineer accepts"
            self.add(ck)
        # reactions: every support, both runs, D and the worst live pattern
        Rsup: Dict[float, Tuple[float, float, float]] = {}
        for how, r in runs:
            for k, ys in enumerate(r.supports):
                d = r.dead.R[k]
                lp = sum(max(0.0, l.R[k]) for l in r.lives)
                ln = sum(min(0.0, l.R[k]) for l in r.lives)
                old = Rsup.get(round(ys, 2), (0.0, 0.0, 0.0))
                if how == "spliced":     # a splice support carries both pieces
                    Rsup[round(ys, 2)] = (old[0] + d, old[1] + lp, min(old[2], 0.0) + ln)
                else:
                    Rsup[round(ys, 2)] = (max(old[0], d), max(old[1], lp), min(old[2], ln))
        # a continuous run's interior reaction can exceed the two spliced halves: keep the larger of the two models
        if len(runs) > 1 and runs[-1][0] == "continuous":
            rc = runs[-1][1]
            for k, ys in enumerate(rc.supports):
                d = rc.dead.R[k]; lp = sum(max(0.0, l.R[k]) for l in rc.lives); ln = sum(min(0.0, l.R[k]) for l in rc.lives)
                o = Rsup[round(ys, 2)]
                Rsup[round(ys, 2)] = (max(o[0], d), max(o[1], lp), min(o[2], ln))
        self.joist_R[(P.idx, z.name)] = dict(R=Rsup, s=s, sec=sec, start=start, sup=sup, end=end, wD=wD, wL=wL, tipD=tipD, runs=runs)
        # bearing of the joist on each beam (drop beams): the beam's width
        widths = {round(b.cl_y, 2): b.width for b in fr.beams}
        worst = max(((R[0] + R[1], ys) for ys, R in Rsup.items() if ys in widths), default=None)
        if worst:
            self.add(bearing_check(f"J-{tag}.7", "Joists & cantilevers", member, worst[0], sec, sec.b, widths[worst[1]], self.scope,
                                   what="Bearing on the beam"))
        if fr.ledger and round(sup[0], 2) in Rsup:
            Rd, Rl, Rn = Rsup[round(sup[0], 2)]
            self.ledger_checks(P, z, Rd, Rl, Rn, s, back if len(sup) == 2 else sup[1] - sup[0])

    def ledger_checks(self, P: _Part, z, Rd: float, Rl: float, Rn: float, s: float, span: float):
        c = self.c
        tag = f"{P.tag}{z.name}"
        member = f"Zone {z.name} ({P.name}) ledger, 2x ledger to the house band"
        R = Rd + Rl
        hz = PRODUCTS["LUS210Z"]
        self.add(Check(f"LG-{tag}.1", "Ledger & hangers", member, "Joist hanger LUS210Z, download", R, hz["down"], "lb", hz["src"],
                       f"joist end reaction D {Rd:,.0f} + L {Rl:,.0f} = {R:,.0f} lb (worst pattern)"))
        if Rd + Rn < 0:
            self.add(Check(f"LG-{tag}.1u", "Ledger & hangers", member, "Joist hanger LUS210Z, uplift", -(Rd + Rn), hz["up"], "lb", hz["src"],
                           f"cantilever loaded, back span empty: D {Rd:,.0f} + L {Rn:,.0f} lb"))
        plf = R / s * 12.0
        ll = PRODUCTS["LedgerLOK"]
        sp = 12.0           # GSX: 2 rows, staggered, one screw per 12" of ledger
        dem = plf * sp / 12.0
        self.add(Check(f"LG-{tag}.2", "Ledger & hangers", member, "LedgerLOK, load per screw", dem, ll["per_screw"], "lb",
                       "IRC R507.9.1.3; ICC-ES ESR-1078",
                       f"ledger load {R:,.0f} lb / {s:g}\" = {plf:,.0f} plf · one LedgerLOK per {sp:g}\" (2 rows staggered) = {dem:,.0f} lb/screw · "
                       f"capacity {ll['per_screw']} lb = {ll['src']}"))
        js_ft = span / 12.0
        key = next((k for k in sorted(IRC_LAG_SPACING) if js_ft <= k), 18)
        self.add(Check(f"LG-{tag}.3", "Ledger & hangers", member, "Fastener spacing vs IRC 1/2\" lag table", sp, IRC_LAG_SPACING[key], "in",
                       "IRC Table R507.9.1.3(1)",
                       f"joist span {js_ft:.1f}' -> 1/2\" lags at {IRC_LAG_SPACING[key]}\" o.c.; LedgerLOK provided at {sp:g}\" (ESR-1078's own table governs)",
                       note="spacing comparison"))
        if getattr(P.spec.extras, "ledger_on_brick_veneer", False):
            self.add(Check(f"LG-{tag}.4", "Ledger & hangers", member, "Ledger on masonry veneer", 1, 0, "-", "IRC R507.9.1.1",
                           "the spec says the ledger bears on brick veneer: not permitted — freestanding beam or engineered support", status="FAIL"))

    # -------------------------------------------------------------- beam lines
    def line_tag(self, P: _Part, li: int) -> str:
        """Beam lines numbered from the yard in: 1 = the front-most line of the part (structure.md's L1 / U1)."""
        order = sorted(range(len(P.L.beam_lines)), key=lambda i: (-P.L.beam_lines[i].y, P.L.beam_lines[i].x0))
        return f"{P.tag}{order.index(li) + 1}"

    def line_loads(self, P: _Part, li: int, ln) -> Tuple[list, list, List[str]]:
        """Dead and live uniform loads (lb/in) along the beam line from the joists of every zone it carries, with the
        corrections a stair notch makes (short tail joists instead of full joists over the notch's width)."""
        c = self.c
        dead, live, notes = [], [], []
        sec_b = section(ln.size, ln.species, ln.species)
        zmap = {z.name: z for z in P.L.zones}
        for zn in ln.zones:
            z = zmap.get(zn)
            if z is None:
                continue
            jr = self.joist_R.get((P.idx, zn))
            yz = round(ln.y - z.wall_y, 2)
            a, b = max(ln.x0, z.x0), min(ln.x1, z.x0 + z.W)
            if b <= a:
                continue
            if jr:
                hit = min(jr["R"], key=lambda ys: abs(ys - yz))
                if abs(hit - yz) <= 1.5:
                    Rd, Rl, _ = jr["R"][hit]
                    dead.append(("u", a, b, Rd / jr["s"])); live.append(("u", a, b, Rl / jr["s"]))
                    continue
            # fallback: tributary depth from the zone frame
            bl = next((bb for bb in z.frame.beams if abs(z.wall_y + bb.cl_y - ln.y) < 2.0), None)
            trib = bl.trib_depth if bl else 48.0
            dead.append(("u", a, b, c.dead_psf * trib / 144.0)); live.append(("u", a, b, c.deck_live_psf * trib / 144.0))
            notes.append(f"zone {zn}: tributary {trib:.0f}\" (no joist support matched)")
        for a, b, dD, dL, why in self.beam_corr.get((P.idx, li), []):
            a, b = max(ln.x0, a), min(ln.x1, b)
            if b > a:
                dead.append(("u", a, b, dD)); live.append(("u", a, b, dL))
                notes.append(why)
        dead.append(("u", ln.x0, ln.x1, sec_b.weight_plf / 12.0))
        return dead, live, notes

    def beam_lines(self, P: _Part):
        for li, ln in enumerate(P.L.beam_lines):
            sec_b = section(ln.size, ln.species, ln.species)
            dead, live, notes = self.line_loads(P, li, ln)
            pts = self.beam_pts.get((P.idx, li), [])
            tag = self.line_tag(P, li)
            name = ln.label.replace("DROP ", "").replace("FLUSH ", "flush ")
            spans = [b - a for a, b in zip(ln.posts_x, ln.posts_x[1:])]
            splices = [round(b, 1) for (a, b) in ln.pieces[:-1]]
            member = (f"Beam {tag} {sec_b.label} ({name}): {_ftin(ln.x1 - ln.x0)} on {len(ln.posts_x)} posts, spans "
                      + " · ".join(_ftin(sv) for sv in spans) + (f" · spliced at {', '.join(_ftin(x) for x in splices)}" if splices else ""))

            def piece_loads(a, b):
                dl = [(ld[0], max(a, ld[1]), min(b, ld[2]), ld[3]) for ld in dead if min(b, ld[2]) > max(a, ld[1])]
                lv = [(ld[0], max(a, ld[1]), min(b, ld[2]), ld[3]) for ld in live if min(b, ld[2]) > max(a, ld[1])]
                other: Dict[str, list] = {}
                for x, comp, lab in pts:
                    if not (a - 0.6 <= x <= b + 0.6):
                        continue
                    xx = min(b, max(a, x))
                    if comp.get("D"):
                        dl.append(("p", xx, comp["D"]))
                    if comp.get("L"):
                        lv.append(("p", xx, comp["L"]))
                    for k in ("S", "Wd", "Wu"):
                        if comp.get(k):
                            other.setdefault(k, []).append(("p", xx, comp[k]))
                return dl, lv, other

            cks: List[Check] = []
            for pi, (a, b) in enumerate(ln.pieces):
                posts = [px for px in ln.posts_x if a - 0.6 <= px <= b + 0.6]
                if len(posts) < 2:
                    self.add(Check(f"B-{tag}.p{pi + 1}", "Beams", member, "Piece on one post", 0, 0, "-", "IRC R507.5",
                                   f"piece {_ftin(a)}-{_ftin(b)} has {len(posts)} post(s): a cantilevered piece — detail the splice", status="REVIEW"))
                    continue
                dl, lv, other = piece_loads(a, b)
                r = run_member(sec_b, a, b, posts, dl, lv, other or None)
                for ck in flexure_checks(r, f"B-{tag}", "Beams", member, self.scope):
                    cks.append(ck)
                # post reactions of this piece
                for k, px in enumerate(r.supports):
                    j = min(range(len(ln.posts_x)), key=lambda q: abs(ln.posts_x[q] - px))
                    comp = r.comp_at("R", k)
                    acc = self.post_comp.setdefault((P.idx, li, j), {"D": [0.0, 0.0], "L": [0.0, 0.0], "S": [0.0, 0.0], "W": [0.0, 0.0], "pieces": [0, 0]})
                    for key, (hi, lo) in comp.items():
                        acc[key][0] += hi; acc[key][1] += lo
                    acc["pieces"][0] += 1
                    end_here = abs(px - a) < 1.0 or abs(px - b) < 1.0
                    acc["pieces"][1] += 1 if end_here else 0
                # an interior column of a continuous piece takes ~1.25 wL: what it would carry with the splice over it
                for k in range(1, len(posts) - 1):
                    px = posts[k]
                    tot = [0.0, 0.0]
                    for (aa, bb) in ((a, px), (px, b)):
                        ps = [q for q in posts if aa - 0.6 <= q <= bb + 0.6]
                        if len(ps) < 2:
                            tot = None
                            break
                        d2, l2, o2 = piece_loads(aa, bb)
                        r2 = run_member(sec_b, aa, bb, ps, d2, l2, None, mesh=6.0)
                        kk = min(range(len(r2.supports)), key=lambda q: abs(r2.supports[q] - px))
                        tot[0] += r2.dead.R[kk]; tot[1] += sum(max(0.0, l.R[kk]) for l in r2.lives)
                    if tot:
                        j = min(range(len(ln.posts_x)), key=lambda q: abs(ln.posts_x[q] - px))
                        self.post_comp[(P.idx, li, j)]["alt"] = tot
            best: Dict[str, Check] = {}
            for ck in cks:
                if ck.id not in best or ck.ratio > best[ck.id].ratio:
                    best[ck.id] = ck
            for k in sorted(best):
                if notes:
                    best[k].note = "; ".join(notes)
                self.add(best[k])
            # bearing on the cap (the post width under the beam), worst post
            worst = None
            for j in range(len(ln.posts_x)):
                comp = self.post_comp.get((P.idx, li, j))
                if not comp:
                    continue
                rr, nm, e, cap = governing({k: tuple(v) for k, v in comp.items() if k in ("D", "L", "S", "W")}, lambda cd: 1.0, sign=1)
                if worst is None or e > worst[0]:
                    worst = (e, j, nm)
            pw = LUMBER_ACTUAL.get(P.spec.framing.post_size, (5.5, 5.5))[0]
            if worst:
                self.add(bearing_check(f"B-{tag}.5", "Beams", member, worst[0], sec_b, sec_b.b, pw, self.scope, what=f"Bearing on the column cap ({worst[2]})"))
            # beam overhangs past the end posts (IRC R507.5 note: span / 4)
            for side, ov, adj in (("left", ln.posts_x[0] - ln.x0, spans[0] if spans else 0), ("right", ln.x1 - ln.posts_x[-1], spans[-1] if spans else 0)):
                if ov > 6.0 and adj > 0:
                    ck = Check(f"B-{tag}.6{side[0]}", "Beams", member, f"Overhang past the {side} end post (span/4)", ov, adj / 4.0, "in", "IRC Table R507.5 note",
                               f"overhang {ov:.1f}\" vs adjacent span {adj:.1f}\"/4 = {adj / 4:.1f}\" (strength and deflection of the overhang are in the rows above)")
                    if ck.ratio > 1.0:
                        ck.status = "REVIEW"
                        ck.note = "beyond the prescriptive span/4: the bending, shear and overhang deflection rows govern; engineer accepts"
                    self.add(ck)
            # columns under this line
            for j, px in enumerate(ln.posts_x):
                comp = self.post_comp.get((P.idx, li, j))
                if comp is None:
                    continue
                zone = ln.post_zone[j] if j < len(ln.post_zone) else ln.zones[0]
                gx, gy = self.gxy(P, px, ln.y)
                self.cols.append(dict(id=f"{tag}-{j + 1}", part=P.idx, part_name=P.name, line=li, j=j, kind="beam", x=px, y=ln.y, gx=gx, gy=gy,
                                      zone=zone, height=float(ln.post_len), comp={k: list(v) for k, v in comp.items() if k in ("D", "L", "S", "W")},
                                      pieces=comp["pieces"], label=f"beam {tag} post {j + 1} ({name})", line_label=name,
                                      end_post=j in (0, len(ln.posts_x) - 1), cap_mid=ln.cap_mid, cap_end=ln.cap_end, Vb=0.0, braced=False,
                                      on_footing=True, size=P.spec.framing.post_size, alt=comp.get("alt"), line_tag=tag))

    # -------------------------------------------------------------- columns, caps, bases, footings
    def col_section(self, col: dict) -> Section:
        size = col.get("size") or self.spec.framing.post_size
        if col.get("kind") in ("notch",) and str(size).startswith("4x"):
            return section(size, "SYP", "No.2")                    # PT 4x4 / 4x6 posts on the stair base ledger
        sp = self.spec.framing.post_species or "DF#1"
        return section(size, "DF" if sp.upper().startswith("DF") else sp, sp)

    def col_comp(self, col: dict) -> Dict[str, Tuple[float, float]]:
        sec = self.col_section(col)
        selfw = sec.weight_plf * col["height"] / 12.0 + 15.0          # column + cap + base
        comp = {k: (v[0], v[1]) for k, v in col["comp"].items()}
        d = comp.get("D", (0.0, 0.0))
        comp["D"] = (d[0] + selfw, d[1] + selfw)
        return comp

    def columns(self):
        from .engineering import POST_MAX_HEIGHT
        c = self.c
        heights_done = set()
        for col in self.cols:
            sec = self.col_section(col)
            comp = self.col_comp(col)
            le = col["height"]
            lab = f"Column {col['id']} {sec.label}, {_ftin(le)} ({col['label']})"

            def cap(cd, sec=sec, le=le):
                cp, _ = sec.Cp(le, cd)
                return sec.Fc_star(cd) * cp * sec.A
            rr, nm, P, capP = governing(comp, cap, sign=1)
            cdv = dict(COMBO_CD).get(nm, 1.0)
            cp, FcE = sec.Cp(le, cdv)
            dmin = min(sec.t if sec.plies == 1 else sec.b, sec.d)
            ck = Check(f"C-{col['id']}", "Columns", lab, f"Axial + buckling ({nm})", P / sec.A, capP / sec.A, "psi", f"NDS 2018 3.6, 3.7; {sec.table}",
                       f"P = {P:,.0f} lb (incl. self weight) · fc = P/A = {P / sec.A:,.0f} psi · le/d = {le:.0f}/{dmin:g} = {le / dmin:.1f} (≤ 50) · "
                       f"Fc* = {sec.factors_text('Fc', cdv)} = {sec.Fc_star(cdv):,.0f} psi · FcE = 0.822 Emin'/(le/d)² = {FcE:,.0f} psi · Cp = {cp:.3f} · F'c = {capP / sec.A:,.0f} psi")
            self.add(ck)
            col["P_max"], col["P_combo"] = P, nm
            if col["kind"] == "beam":
                P_ = self.parts[col["part"]]
                lat = getattr(P_, "lat", None)
                if lat:
                    w = 0.6 * lat["qz"] * c.G * 2.0 * sec.d / 12.0 / 12.0          # lb/in on the column face (ASD wind), Cf 2.0
                    Mw = w * le * le / 8.0
                    worst = None
                    for nm2, kP, kM in (("D + 0.6W", dict(D=1.0), 1.0), ("D + 0.75L + 0.75(0.6W)", dict(D=1.0, L=0.75), 0.75)):
                        Pq = sum(k_ * comp.get(t_, (0.0, 0.0))[0] for t_, k_ in kP.items())
                        cpq, FcEq = sec.Cp(le, 1.6)
                        fc, fb = Pq / sec.A, kM * Mw / sec.S
                        inter = (fc / (sec.Fc_star(1.6) * cpq)) ** 2 + fb / (sec.Fb(1.6) * (1 - fc / FcEq))
                        if worst is None or inter > worst[0]:
                            worst = (inter, nm2, fc, fb)
                    col["wind_inter"] = worst
            hkey = (col["size"], round(le))
            if col["kind"] == "beam" and hkey not in heights_done:
                heights_done.add(hkey)
                mx = POST_MAX_HEIGHT.get(col["size"], 0)
                if mx:
                    self.add(Check(f"C-H{col.get('line_tag', col['line'] + 1)}", "Columns", f"{col['size']} columns under beam {col.get('line_tag', '')} ({col['line_label']})", "Height vs IRC Table R507.4",
                                   le, mx, "in", "IRC Table R507.4", f"column {_ftin(le)} (top of footing to the underside of the beam) vs {_ftin(mx)} for {col['size']}"))

    def column_wind_rows(self):
        """Per beam line, its worst column: axial + bending from wind on the column itself (pinned both ends)."""
        c = self.c
        by_line: Dict[Tuple[int, int], dict] = {}
        for col in self.cols:
            wi = col.get("wind_inter")
            if not wi:
                continue
            key = (col["part"], col["line"])
            if key not in by_line or wi[0] > by_line[key]["wind_inter"][0]:
                by_line[key] = col
        for (pi, li), col in by_line.items():
            inter, nm, fc, fb = col["wind_inter"]
            P_ = self.parts[pi]
            self.add(Check(f"C-W{col.get('line_tag', li + 1)}", "Columns", f"Column {col['id']} (worst under beam {col.get('line_tag', '')}), {_ftin(col['height'])}, wind on its face",
                           f"Axial + wind bending ({nm})", inter, 1.0, "-", "NDS 2018 3.9.2 (Eq. 3.9-3); ASCE 7-16 Ch. 29",
                           f"w = 0.6 qz G Cf b = 0.6 x {P_.lat['qz']:.1f} x {c.G:g} x 2.0 x 7.5\"/12 per ft · M = wL²/8 · fc = {fc:,.0f} psi, fb = {fb:,.0f} psi · "
                           f"(fc/F'c)² + fb/(F'b(1 - fc/FcE)) = {inter:.2f} (pinned ends: the joists brace the top, the base is a pin)"))

    def caps_and_bases(self):
        base_req: Dict[Tuple[str, str], dict] = {}
        for col in self.cols:
            comp = self.col_comp(col)
            down = max((e for _, _, e, _ in combine(comp)), default=0.0)
            up = -min((e2 for _, _, _, e2 in combine(comp)), default=0.0)
            col["down"], col["up"] = down, max(0.0, up)
            if col["kind"] == "beam":
                splice = col["pieces"][0] >= 2
                end = (not splice) and col["pieces"][1] >= 1
                cap_name = (col["cap_end"] if end else col["cap_mid"]) or "CCQ68SDS2.5"
                pr = PRODUCTS.get(cap_name)
                lab = f"Column {col['id']} cap {cap_name}" + (" (splice: two beam ends)" if splice else " (beam end)" if end else "")
                if pr is None:
                    self.add(Check(f"K-{col['id']}", "Caps & bases", lab, "Cap capacity", down, 0, "lb", "Simpson C-C-2026",
                                   f"no published value on file for {cap_name}", status="REVIEW"))
                else:
                    r_d = down / pr["down"]; r_u = (col["up"] / pr["up"]) if col["up"] > 0 else 0.0
                    if r_u > r_d:
                        ck = Check(f"K-{col['id']}", "Caps & bases", lab, "Cap uplift", col["up"], pr["up"], "lb", pr["src"],
                                   f"net uplift {col['up']:,.0f} lb (0.6D + 0.6W / patterned live) vs {pr['up']:,} lb", note="splice: Simpson's uplift value does not apply — strap the splice" if splice else "")
                        if splice:
                            ck.status = "REVIEW"
                    else:
                        ck = Check(f"K-{col['id']}", "Caps & bases", lab, "Cap download", down, pr["down"], "lb", pr["src"],
                                   f"P = {down:,.0f} lb (governing ASD combination) vs {pr['down']:,} lb" + (f"; uplift {col['up']:,.0f} lb vs {pr['up']:,} lb" if col["up"] > 0 else "; no net uplift"))
                    self.add(ck)
            if col.get("on_footing"):
                fi_ = self.footing_info(col)
                key = (col["size"], fi_["type"], bool(fi_.get("own")))         # the stair's own 12" caissons get their own row
                b = base_req.setdefault(key, dict(down=0.0, up=0.0, lat=0.0, ids=[], part=col["part"], model=fi_.get("model", ""), dia=fi_.get("dia")))
                b["down"] = max(b["down"], down); b["up"] = max(b["up"], col["up"]); b["lat"] = max(b["lat"], col.get("Vb", 0.0))
                b["ids"].append(col["id"])
        from .catalog import POST_BASE, TIMBER_BASE
        from .takeoff import _deck_base
        for (size, ftype, own), b in base_req.items():
            conc = ftype in ("caisson", "existing", "concrete")
            pspec = self.parts[b["part"]].spec
            if conc and size in TIMBER_BASE and size == pspec.framing.post_size:
                # the base the takeoff orders on concrete (ABU88RZ under a rough 8x8): the deck's columns and the stair's own posts alike
                sku = _deck_base(pspec, pspec.framing.hardware_finish == "black").replace("_black", "")
            else:
                sku = POST_BASE.get(size, {}).get("concrete" if conc else ftype, "")
            pr = PRODUCTS.get(sku)
            cid = f"K-BASE-{size}" + ("-ST" if own else "")
            lab = (f"{size} post base on the stair's own {b['model']}s ({len(b['ids'])} posts)" if own
                   else f"{size} column base on {ftype.replace('_', ' ')} ({len(b['ids'])} columns)")
            req = f"required (worst column): down {b['down']:,.0f} lb · uplift {b['up']:,.0f} lb · lateral {b['lat']:,.0f} lb · 1\" standoff. "
            if pr is None and not conc:
                self.add(Check(cid, "Caps & bases", lab, "Post base — no catalog part", b["down"], 0, "lb",
                               "IRC R507.4.1; ESR-1895 §5.2; Simpson C-C-2026",
                               req + f"No Simpson 8x8 base takes the pier's single cast-in bolt (ABU88 / APB88 / CPT88 need two anchors): an engineer-detailed "
                               f"HDG standoff base on the pier bolt, or a tenoned foot in an ABU66Z / ABW66RZ", status="REVIEW"))
            elif pr is None:
                self.add(Check(cid, "Caps & bases", lab, f"Post base {sku or '(none)'}", b["down"], 0, "lb", "Simpson C-C-2026",
                               req + f"no published value on file for {sku or 'this post size'}: confirm the base against the catalog", status="REVIEW"))
            else:
                if pspec.framing.post_rough and sku.endswith("Z") and (sku[:-1] + "RZ") in PRODUCTS:
                    sku = sku[:-1] + "RZ"
                    pr = PRODUCTS[sku]
                r_d, r_u = b["down"] / pr["down"], (b["up"] / pr["up"] if b["up"] else 0.0)
                two = sku.startswith(("ABU88", "APB88", "CPT88"))
                on_dp = ftype == "diamond_pier"
                anchors = "two 5/8\" anchors" if two else "the 5/8\" anchor"
                where_ = (f" · {anchors} cast in each {b['model']}, 1\" standoff" if own
                          else f" · anchors cast in the {ftype} (standard catalog condition), 1\" standoff" if not on_dp else "")
                note = ("the second anchor in the 5-5/8\" pier plinth (edge distance, the head's concrete limit) is not a catalog condition: "
                        "Pin Foundations and the engineer confirm; the pier's own uplift (chart) governs uplift" if two and on_dp else "")
                if own and two and not on_dp:
                    note = f"two cast-in anchors in a {b['dia'] or STAIR_CAISSON_DIA:g}\" shaft: the engineer confirms their embedment and edge distance (ACI 318-14 Ch. 17)"
                self.add(Check(cid, "Caps & bases", lab, f"Post base {sku}", b["down"] if r_u <= r_d else b["up"],
                               pr["down"] if r_u <= r_d else pr["up"], "lb", pr["src"],
                               f"down {b['down']:,.0f} / {pr['down']:,} lb · uplift {b['up']:,.0f} / {pr['up']:,} lb · lateral {b['lat']:,.0f} lb"
                               + (" · two 5/8\" anchors: the cast-in pier bolt + one drilled into the pier head (owner 27 Oct)" if two and on_dp else "")
                               + where_,
                               status="REVIEW" if (two and on_dp) else "", note=note))

    def footing_info(self, col: dict) -> dict:
        """The footing under a column, from the layout: type, model / diameter, depth, capacity (the engine's numbers)."""
        if col.get("footing"):
            return dict(col["footing"])
        P_ = self.parts[col["part"]]
        zm = {z.name: z for z in P_.L.zones}
        z = zm.get(col.get("zone"))
        fr = z.frame if z is not None else P_.L.zones[0].frame
        fsp = P_.spec.framing
        ftype = (fr.footing_type if z is not None else fsp.footing_type) or fsp.footing_type
        info = dict(type=ftype)
        if ftype == "diamond_pier":
            info["model"] = col.get("model") or (fr.footing_model if z is not None else fsp.footing_model)
        elif ftype in ("caisson", "existing", "concrete"):
            dia = float(fr.footing_dia_in or 0) or float(getattr(fsp, "caisson_dia_in", 0) or 0) or 20.0
            depth = float(fr.footing_depth_in or 0) or float(getattr(fsp, "caisson_depth_in", 0) or 0) or (self.c.frost_in + 2.0)
            end_b = math.pi * (dia / 24.0) ** 2 * self.c.soil_psf
            cap = float(fr.footing_capacity_lb or 0) if ftype != "concrete" else 0.0
            if not cap:
                cap = end_b + (math.pi * dia / 12.0 * depth / 12.0 * CAISSON_SKIN_PSF if ftype != "concrete" else 0.0)
            info.update(model=f"{dia:g}\" x {depth:g}\" {'caisson' if ftype != 'concrete' else 'pier'}", dia=dia, depth=depth, cap=cap, end=end_b,
                        weight=math.pi * (dia / 24.0) ** 2 * depth / 12.0 * CONCRETE_PCF)
        return info

    def footings(self):
        c = self.c
        fcols = [col for col in self.cols if col.get("on_footing")]
        kinds = set()
        for col in fcols:
            fi = self.footing_info(col)
            col["ftype"] = fi["type"]
            kinds.add(fi["type"])
            if fi["type"] == "diamond_pier":
                self.pier_rows(col, fi)
            elif fi["type"] in ("caisson", "existing", "concrete"):
                self.caisson_rows(col, fi)
            else:
                self.add(Check(f"F-{col['id']}", "Footings", f"Column {col['id']} footing ({fi['type']})", "Footing", col["down"], 0, "lb", "IRC R403 / R507.3",
                               f"P = {col['down']:,.0f} lb on a {fi['type']} footing — size by the soil bearing ({c.soil_psf:,.0f} psf)", status="REVIEW"))
        self.footing_once_rows(fcols, kinds)

    def _over_note(self, col: dict, cap: float, what: str, bigger: str = "") -> str:
        down = col["down"]
        if down <= cap:
            return ""
        alt = col.get("alt")
        altP = (alt[0] + alt[1] + (down - col["comp"]["D"][0] - col["comp"]["L"][0])) if alt else None
        return (f"over the {what}: " + (f"{bigger}; " if bigger else "")
                + (f"with the beam spliced over this column it drops to about {altP:,.0f} lb; " if altP and altP < down - 1 else "")
                + "or add a column / shorten the spans")

    def pier_rows(self, col: dict, fi: dict):
        from .catalog import pier_capacity_lb
        c = self.c
        model = fi["model"]
        col["model"] = model
        down = col["down"]
        capb = pier_capacity_lb(model, c.soil_psf)
        pr = PIER.get(model)
        need = next((m for m in ("DP-50/50", "DP-75/63") if down <= pier_capacity_lb(m, c.soil_psf) and col["up"] <= PIER[m]["up"]), None)
        col["need"] = need or "over DP-75/63"
        where = "" if col["gx"] != col["gx"] else f", x {col['gx']:.2f}', y {col['gy']:.2f}'"
        lab = f"Column {col['id']} on {model} ({col['part_name']}{where})"
        if not capb or pr is None:
            self.add(Check(f"F-{col['id']}", "Footings", lab, "Pier bearing", down, 0, "lb", PIER_SRC, f"{model}: no chart value on file", status="REVIEW"))
            return
        col["fcap"] = capb
        self.add(Check(f"F-{col['id']}", "Footings", lab, "Pier bearing (ASD)", down, capb, "lb", f"{PIER_SRC}; IRC R507.3",
                       f"P = {down:,.0f} lb ({col.get('P_combo', 'governing')}, incl. column + base) vs {model} {capb:,.0f} lb at {c.soil_psf:,.0f} psf · smallest pier that works: {col['need']}",
                       note=self._over_note(col, capb, f"specified {model}", f"a {need} carries it" if need and need != model else "")))
        if col["up"] > 0:
            self.add(Check(f"F-{col['id']}u", "Footings", lab, "Pier uplift", col["up"], pr["up"], "lb", "Pin Foundations DOC0008 (tested; ESR-1895 §5.6 does not evaluate uplift)",
                           f"net uplift {col['up']:,.0f} lb vs {pr['up']:,} lb", note="PE accepts the chart uplift value"))
        if col.get("Vb", 0.0) > 0:
            self.add(Check(f"F-{col['id']}l", "Footings", lab, "Pier lateral", col["Vb"], pr["lat"], "lb",
                           "Pin Foundations DOC0008 (tested; not ESR-evaluated)", f"base shear {col['Vb']:,.0f} lb (with the knee brace) vs {pr['lat']} lb"))

    def caisson_rows(self, col: dict, fi: dict):
        c = self.c
        down = col["down"]
        col["model"] = fi["model"]
        d_req = math.sqrt(4.0 * down / (math.pi * c.soil_psf)) * 12.0
        d_req = max(12.0, math.ceil(d_req / 2.0) * 2.0)
        col["need"] = f"{d_req:g}\" end bearing"
        where = "" if col["gx"] != col["gx"] else f", x {col['gx']:.2f}', y {col['gy']:.2f}'"
        lab = f"Column {col['id']} on a {fi['model']} ({col['part_name']}{where})"
        skin = fi["cap"] - fi["end"]
        col["fcap"] = fi["cap"]
        note = self._over_note(col, fi["cap"], f"{fi['model']}", "a larger diameter or a deeper shaft")
        if not note and down > fi["end"]:
            note = f"carries more than end bearing alone ({fi['end']:,.0f} lb): the skin-friction share is an estimate — the engineer confirms (soils report if Centennial R401.2 applies)"
        self.add(Check(f"F-{col['id']}", "Footings", lab, "Caisson bearing (ASD)", down, fi["cap"], "lb", "IRC R403.1, Table R401.4.1, R507.3; engine estimate",
                       f"P = {down:,.0f} lb ({col.get('P_combo', 'governing')}, incl. column + base) · end bearing π(d/2)² q = π x ({fi['dia']:g}/24)² x {c.soil_psf:,.0f} = {fi['end']:,.0f} lb "
                       f"+ skin friction ≈ {CAISSON_SKIN_PSF:g} psf x π d L = {skin:,.0f} lb = {fi['cap']:,.0f} lb · end bearing alone needs a {d_req:g}\" shaft", note=note))
        if col["up"] > 0:
            res = 0.6 * fi["weight"]
            self.add(Check(f"F-{col['id']}u", "Footings", lab, "Caisson uplift (0.6 x its weight)", col["up"], res, "lb", "ASCE 7-16 2.4.1 (0.6D); IRC R507.3",
                           f"net uplift {col['up']:,.0f} lb vs 0.6 x {fi['weight']:,.0f} lb of concrete ({CONCRETE_PCF:g} pcf) — skin friction in uplift adds to it (not counted)"))
        if col.get("Vb", 0.0) > 0:
            dreq = pole_embedment(col["Vb"], 0.5, fi["dia"] / 12.0)
            self.add(Check(f"F-{col['id']}l", "Footings", lab, "Caisson lateral embedment (IBC 1807.3.2.1)", dreq * 12.0, fi["depth"], "in",
                           "IBC 2021 Eq. 18-1, Table 1806.2 (100 psf/ft, x2 isolated)",
                           f"base shear {col['Vb']:,.0f} lb (with the knee brace) at 6\" above grade on a {fi['dia']:g}\" shaft: required embedment {dreq * 12:.1f}\" vs {fi['depth']:g}\""))

    def footing_once_rows(self, fcols: List[dict], kinds: set):
        c = self.c
        if "diamond_pier" in kinds:
            for m in sorted({col.get("model") for col in fcols if col.get("ftype") == "diamond_pier"}):
                pr = PIER.get(m)
                if pr:
                    self.add(Check(f"F-frost-{m}", "Footings", f"{m} frost rating", "Frost depth", c.frost_in, pr["frost"], "in", "IRC R403.1.4.1 / R507.3.3; ESR-1895 §5.3",
                                   f"site frost line {c.frost_in:g}\" vs the pier's frost-zone rating {pr['frost']}\" (code official approves per R507.3.3)"))
            piers = [q for q in fcols if q.get("ftype") == "diamond_pier" and q["gx"] == q["gx"]]
            for i, a in enumerate(piers):
                for b in piers[i + 1:]:
                    d = math.hypot(a["gx"] - b["gx"], a["gy"] - b["gy"]) * 12.0
                    if d < 36.0:
                        self.add(Check(f"F-sp-{a['id']}-{b['id']}", "Footings", f"Piers under {a['id']} and {b['id']}", "Pier spacing (3'-0\" min.)", 36.0, d, "in",
                                       "ICC-ES ESR-1895; Pin Foundations installation manual", f"centre to centre {d:.1f}\" < 36\": merge the columns or move one (each closer pier loses about 13%)",
                                       status="FAIL"))
        cais = [q for q in fcols if q.get("ftype") in ("caisson", "existing", "concrete")]
        if cais:
            seen = set()
            for q in cais:
                fi = self.footing_info(q)
                key = (fi["dia"], fi["depth"])
                if key in seen:
                    continue
                seen.add(key)
                self.add(Check(f"F-frost-{fi['dia']:g}x{fi['depth']:g}", "Footings", f"{fi['model']} (bottom of the shaft)", "Below the frost line", c.frost_in, fi["depth"], "in",
                               "IRC R403.1.4.1, R507.3.2; Centennial Table R301.2(1)",
                               f"shaft depth {fi['depth']:g}\" vs frost line {c.frost_in:g}\" (and 12\" min. below undisturbed grade)"))
            pts = [q for q in cais if q["gx"] == q["gx"]]
            for i, a in enumerate(pts):
                for b in pts[i + 1:]:
                    d = math.hypot(a["gx"] - b["gx"], a["gy"] - b["gy"]) * 12.0
                    lim = self.footing_info(a)["dia"] + self.footing_info(b)["dia"]
                    if d < lim:
                        self.add(Check(f"F-sp-{a['id']}-{b['id']}", "Footings", f"Caissons under {a['id']} and {b['id']}", "Shaft spacing (2 diameters)", lim, d, "in",
                                       "drilled-shaft practice", f"centre to centre {d:.1f}\" < {lim:g}\": the holes run together — one footing under both or move a column",
                                       status="REVIEW"))


    # -------------------------------------------------------------- lateral
    def lateral(self):
        c = self.c
        for P in self.parts:
            L, spec = P.L, P.spec
            if not L.zones:
                continue
            x0 = min(z.x0 for z in L.zones); x1 = max(z.x0 + z.W for z in L.zones)
            depth = max(z.D for z in L.zones)
            Lx, Dy = x1 - x0, depth
            area = sum(z.W * z.D for z in L.zones) / 144.0
            h_deck = float(spec.geometry.height_in)
            jd = LUMBER_ACTUAL.get(spec.framing.joist_size, (1.5, 9.25))[1]
            band = 1.0 + jd
            outer = max(L.beam_lines, key=lambda ln: ln.y) if L.beam_lines else None
            if outer is not None and any(abs(outer.y - (z.wall_y + z.D)) < 8.0 for z in L.zones):
                band += outer.depth                                     # a beam under the rim adds to the solid face
            rail_h = float(getattr(spec.railing, "height_in", 36) or 36) if L.rail else 0.0
            mycols = [col for col in self.cols if col["part"] == P.idx and col["kind"] == "beam"]
            col_w = LUMBER_ACTUAL.get(spec.framing.post_size, (5.5, 5.5))[0]
            qz, Kz = wind_q(c, (h_deck + rail_h) / 12.0)
            # strength-level wind on the open frame: solid band Cf 1.8, rail infill and columns Cf 2.0 (ASCE 7-16 Ch. 29, open signs / frames)
            Ay_band = Lx * band / 144.0; Ay_rail = Lx * rail_h * c.rail_solidity / 144.0
            Ay_cols = sum(col_w * col["height"] for col in mycols) / 144.0
            Fy = qz * c.G * (1.8 * Ay_band + 2.0 * (Ay_rail + Ay_cols))
            Ax_band = Dy * band / 144.0; Ax_rail = Dy * rail_h * c.rail_solidity / 144.0
            ends = sorted(mycols, key=lambda q: q["x"])
            Ax_cols = sum(col_w * q["height"] for q in ends[:1] + ends[-1:]) / 144.0 if ends else 0.0
            Fx = qz * c.G * (1.8 * Ax_band + 2.0 * (Ax_rail + Ax_cols))
            W_seis = c.dead_psf * area + sum(section(ln.size, ln.species).weight_plf * (ln.x1 - ln.x0) / 12.0 for ln in L.beam_lines) \
                + sum(self.col_section(q).weight_plf * q["height"] / 24.0 for q in mycols)
            Cs = c.sds / (c.R / c.Ie)
            E = Cs * W_seis
            ex = self.extra_lat.get(P.idx, [0.0, 0.0])
            HX = max(0.6 * Fx, 0.7 * E); HY = max(0.6 * Fy, 0.7 * E)
            if any(ex):          # screens down only up to 65 mph (they retract above it): a separate case at 65 mph
                k65 = (SCREEN_V_MPH / c.wind_mph) ** 2
                HX = max(HX, k65 * 0.6 * Fx + ex[0]); HY = max(HY, k65 * 0.6 * Fy + ex[1])
            gx = "wind" if 0.6 * Fx >= 0.7 * E else "seismic"; gy = "wind" if 0.6 * Fy >= 0.7 * E else "seismic"
            P.lat = dict(Fx=Fx, Fy=Fy, E=E, HX=HX, HY=HY, qz=qz, Kz=Kz, W=W_seis, Cs=Cs, area=area, band=band)
            tag = P.tag or "D"
            basis_w = (f"qz = 0.00256 Kz Kzt Kd Ke V² = 0.00256 x {Kz:.2f} x {c.Kzt:g} x {c.Kd:g} x {c.Ke:g} x {c.wind_mph:g}² = {qz:.1f} psf (Exp. {c.exposure}, z = {(h_deck + rail_h) / 12:.1f}') · "
                       f"F = qz G Σ Cf A (G {c.G:g}; band {band:.1f}\" Cf 1.8, rail x {c.rail_solidity:g} and columns Cf 2.0)")
            basis_e = f"seismic SDC {c.sdc}: Cs = SDS/(R/Ie) = {c.sds:g}/({c.R:g}/{c.Ie:g}) = {Cs:.3f} · W = {W_seis:,.0f} lb · E = {E:,.0f} lb"
            if any(ex):
                basis_w += (f" · screens-down case at {SCREEN_V_MPH:g} mph: ({SCREEN_V_MPH:g}/{c.wind_mph:g})² of the deck wind + the roof posts' base shear "
                            f"{ex[0]:,.0f} lb x / {ex[1]:,.0f} lb y — the larger case governs")
            # Y: the house takes it through the joists; pull-away by the R507.9.2 hold-downs
            ties = int(spec.framing.lateral_ties if spec.framing.lateral_ties is not None else _framing_default("lateral_ties", 4))
            dev = "DTT2Z" if any("DTT2Z" in (ln.item or "") or getattr(ln, "sku", "") == "DTT2Z" for ln in P.t.lines) else "DTT1Z"
            capd = PRODUCTS[dev]["tension"]
            self.add(Check(f"LT-{tag}.1", "Lateral system", f"{P.name}: house attachment, perpendicular to the house", f"Pull-away vs {ties} x {dev} hold-downs ({gy} governs)",
                           HY, ties * capd, "lb", "IRC R507.9.2; ASCE 7-16 2.4.1",
                           f"0.6 Wy = 0.6 x {Fy:,.0f} = {0.6 * Fy:,.0f} lb; 0.7 E = {0.7 * E:,.0f} lb · {ties} devices x {capd:,} lb · {basis_w}"))
            ok_presc = (ties >= 4 and capd >= 750) or (ties >= 2 and capd >= 1500)
            self.add(Check(f"LT-{tag}.2", "Lateral system", f"{P.name}: R507.9.2 lateral load connection", "Prescriptive hold-down count", 1 if ok_presc else 2, 1, "-",
                           "IRC R507.9.2, Figures R507.9.2(1)/(2)", f"{ties} x {dev} ({capd:,} lb each): R507.9.2 asks for 2 x 1,500 lb within 24\" of each end, or 4 x 750 lb; "
                           "the devices reach a house floor joist or blocking (interior access)", status="PASS" if ok_presc else "FAIL"))
            # X: half to the ledger line (LedgerLOK in shear), the outer half to the beam line(s) and back through the joists
            n_ll = sum(int(math.ceil(z.W / 12.0)) + 1 for z in L.zones if z.frame.ledger)
            share_beam = 0.0
            for z in L.zones:
                st_, sup, end = self.zone_supports(P, z)
                if len(sup) >= 2:
                    share_beam += z.W * ((end - sup[-1]) + (sup[-1] - sup[-2]) / 2.0) / max(1.0, end - st_)
                else:
                    share_beam += z.W
            share_beam /= max(1.0, sum(z.W for z in L.zones))
            house = HX * (1.0 - share_beam)
            if n_ll:
                self.add(Check(f"LT-{tag}.3", "Lateral system", f"{P.name}: ledger line, parallel to the house", f"LedgerLOK in shear ({gx} governs)", house / n_ll,
                               PRODUCTS["LedgerLOK"]["per_screw"], "lb", "IRC R507.9.1.3; ESR-1078",
                               f"HX = max(0.6 x {Fx:,.0f}, 0.7 x {E:,.0f}) = {HX:,.0f} lb; ledger share {1 - share_beam:.2f} = {house:,.0f} lb over {n_ll} screws "
                               f"(vector sum with the gravity load is under the screw value: see LG rows) · {basis_e}"))
            lines = [ln for ln in L.beam_lines]
            tot_len = sum(ln.x1 - ln.x0 for ln in lines) or 1.0
            for li, ln in enumerate(lines):
                H = HX * share_beam * (ln.x1 - ln.x0) / tot_len
                nj = max(1, int((ln.x1 - ln.x0) / max(1.0, P.L.zones[0].frame.spacing)))
                ltag = self.line_tag(P, li)
                self.add(Check(f"LT-{ltag}.4", "Lateral system", f"Beam {ltag} line to the joists (diaphragm path)", "H2.5AZ ties, lateral", H / nj, PRODUCTS["H2.5AZ"]["lat"], "lb",
                               PRODUCTS["H2.5AZ"]["src"], f"line share {H:,.0f} lb over {nj} joist ties = {H / nj:,.0f} lb each; the deck boards and joists carry it to the ledger "
                               "(columns pinned at both ends: Simpson bases are not moment connections, the joists brace the column tops)"))
                self.knee_brace(P, li, ln, H)

    def knee_brace(self, P: _Part, li: int, ln, H: float):
        """Knee braces at the line's two end columns, in the plane of the beam (AWC DCA6 FAQ: corners only) — checked as a
        path that can carry the line's whole share if the deck diaphragm is not relied on."""
        spec = P.spec
        a = float(spec.framing.knee_leg_in or _framing_default("knee_leg_in", 30.0))
        cols = sorted([q for q in self.cols if q["part"] == P.idx and q["line"] == li and q["kind"] == "beam"], key=lambda q: q["x"])
        if len(cols) < 2:
            return
        Lp = cols[0]["height"]
        if Lp <= a + 12:
            return
        in_spec = bool(getattr(spec.framing, "knee_braces", False))
        brace = section("4x6" if spec.framing.post_size == "8x8" else "4x4", "DF", "No.1")
        Vb = H / 2.0
        Fh = Vb * Lp / a
        Fb_ = Fh * math.sqrt(2.0)
        lb = a * math.sqrt(2.0)
        ltag = self.line_tag(P, li)
        note = "" if in_spec else "knee braces are not in the spec: add them at these two columns (recommended), or the engineer relies on the house attachment alone"
        cp, FcE = brace.Cp(lb, 1.6)
        capB = brace.Fc_star(1.6) * cp * brace.A
        self.add(Check(f"LT-{ltag}.5", "Lateral system", f"Beam {ltag}: {brace.nominal} DF No.1 knee braces at the end columns, {a:g}\" legs at 45°",
                       "Brace axial (compression)", Fb_, capB, "lb", "NDS 2018 3.7; AWC DCA6 FAQ (corner posts only)",
                       f"Vb = {H:,.0f}/2 = {Vb:,.0f} lb per braced column · F_h = Vb Lp/a = {Vb:,.0f} x {Lp:.0f}/{a:g} = {Fh:,.0f} lb · F = F_h √2 = {Fb_:,.0f} lb · "
                       f"le = {lb:.0f}\", le/d = {lb / brace.t:.1f}, Cp {cp:.3f}, F'c = {capB / brace.A:,.0f} psi", status="" if in_spec else "REVIEW", note=note))
        Z1 = bolt_Z(0.5, brace.t, 7.5 if spec.framing.post_size == "8x8" else 5.5, 0.50, 0.50, theta_s=0.0, theta_m=45.0)
        Zp = Z1 * 1.6 * 0.7
        self.add(Check(f"LT-{ltag}.6", "Lateral system", f"Beam {ltag}: knee-brace bolts, 2 x 1/2\" per end", "Bolts in single shear", Fb_, 2 * Zp, "lb",
                       "NDS 2018 12.3 (yield limit equations), CD 1.6, CM 0.7",
                       f"Z = {Z1:,.0f} lb (brace 3.5\" side member, 0° to grain; column main member, 45° to grain; G 0.50) · Z' = Z x 1.6 x 0.7 = {Zp:,.0f} lb · 2 bolts",
                       status="" if in_spec else "REVIEW", note=note))
        sec = self.col_section(cols[0])
        for q in (cols[0], cols[-1]):
            q["Vb"] = max(q.get("Vb", 0.0), Vb)
            q["braced"] = True
            comp = self.col_comp(q)
            M = Vb * (Lp - a)
            worst = (0.0, "", 0.0, 0.0)
            for nm, kP, kM in (("D + 0.6W", dict(D=1.0), 1.0), ("D + 0.75L + 0.75(0.6W)", dict(D=1.0, L=0.75), 0.75)):
                Pq = sum(k * comp.get(t, (0.0, 0.0))[0] for t, k in kP.items())
                cpq, FcEq = sec.Cp(Lp, 1.6)
                Fc_ = sec.Fc_star(1.6) * cpq
                fc = Pq / sec.A
                fb = kM * M / sec.S
                Fb1 = sec.Fb(1.6)
                inter = (fc / Fc_) ** 2 + fb / (Fb1 * (1 - fc / FcEq))
                if inter > worst[0]:
                    worst = (inter, nm, fc, fb)
            self.add(Check(f"LT-{q['id']}c", "Lateral system", f"Column {q['id']} with a knee brace (pinned base)", f"Axial + bending ({worst[1]})", worst[0], 1.0, "-",
                           "NDS 2018 3.9.2 (Eq. 3.9-3)", f"M = Vb (Lp - a) = {Vb:,.0f} x {Lp - a:.0f} = {M:,.0f} lb-in · fc = {worst[2]:,.0f} psi, fb = {worst[3]:,.0f} psi · "
                           f"(fc/F'c)² + fb/(F'b(1 - fc/FcE)) = {worst[0]:.2f}", status="" if in_spec else "REVIEW", note=note))


def pole_embedment(P: float, h: float, b: float, s_lat: float = 100.0, iso: float = 2.0) -> float:
    """IBC 2021 1807.3.2.1 (nonconstrained, Eq. 18-1): embedment d (ft) for a lateral load P (lb) at h (ft) above grade on a
    shaft b (ft) wide; S1 = the lateral bearing (psf/ft, Table 1806.2) at d/3, doubled for an isolated pole (1806.3.4)."""
    d = 2.0
    for _ in range(60):
        S1 = iso * s_lat * d / 3.0
        A = 2.34 * P / (S1 * b)
        d_new = 0.5 * A * (1 + math.sqrt(1 + 4.36 * h / A))
        if abs(d_new - d) < 1e-4:
            break
        d = 0.5 * (d + d_new)
    return d


CONCRETE_PCF = 150.0
STAIR_CAISSON_DIA = 12.0      # Stair.landing_footing "caisson12": the stair's own landing / carrier posts (footings agent, 27 Oct)
CAISSON_SKIN_PSF = 400.0      # the engine's skin-friction estimate (layout.frame_layout) — the engineer sizes the shaft


def _framing_default(name: str, fallback):
    try:
        from .spec import Framing
        return getattr(Framing(), name)
    except Exception:
        return fallback


def bolt_Z(D: float, ls: float, lm: float, Gs: float, Gm: float, theta_s: float = 0.0, theta_m: float = 0.0, Fyb: float = 45000.0,
           Fes: Optional[float] = None) -> float:
    """NDS 2018 Table 12.3.1A single-shear bolt reference lateral design value Z (lb): the least of the yield modes.
    Fes: dowel bearing strength of a metal side plate (NDS 12.3.4: 1.5 Fu for steel), else the wood side member's."""
    def fe(G, th):
        fpar = 11200.0 * G
        fper = 6100.0 * G ** 1.45 / math.sqrt(D)
        t = math.radians(th)
        return fpar * fper / (fpar * math.sin(t) ** 2 + fper * math.cos(t) ** 2)
    metal = Fes is not None
    Fem = fe(Gm, theta_m)
    Fes = Fes if metal else fe(Gs, theta_s)
    Re, Rt = Fem / Fes, lm / ls
    Kth = 1 + 0.25 * (max(0.0 if metal else theta_s, theta_m) / 90.0)
    k1 = (math.sqrt(Re + 2 * Re ** 2 * (1 + Rt + Rt ** 2) + Rt ** 2 * Re ** 3) - Re * (1 + Rt)) / (1 + Re)
    k2 = -1 + math.sqrt(2 * (1 + Re) + 2 * Fyb * (1 + 2 * Re) * D ** 2 / (3 * Fem * lm ** 2))
    k3 = -1 + math.sqrt(2 * (1 + Re) / Re + 2 * Fyb * (2 + Re) * D ** 2 / (3 * Fem * ls ** 2))
    modes = [D * lm * Fem / (4 * Kth), D * ls * Fes / (4 * Kth), k1 * D * ls * Fes / (3.6 * Kth),
             k2 * D * lm * Fem / ((1 + 2 * Re) * 3.2 * Kth), k3 * D * ls * Fem / ((2 + Re) * 3.2 * Kth),
             D ** 2 / (3.2 * Kth) * math.sqrt(2 * Fem * Fyb / (3 * (1 + Re)))]
    return min(modes)


# ================================================================== the inset stair, the yard stair, the roof, the guards
def _inv(pl, gx: float, gy: float) -> Tuple[float, float]:
    """Global ft -> a part's local ft (axis-aligned placements)."""
    if isinstance(pl, _Pl):
        return gx, gy
    dx, dy = gx - pl.ox, gy - pl.oy
    det = pl.xx * pl.yy - pl.xy * pl.yx or 1.0
    return ((pl.yy * dx - pl.xy * dy) / det, (-pl.yx * dx + pl.xx * dy) / det)


def _throat(d: float, rise: float, tread: float) -> float:
    return d - rise * tread / math.hypot(rise, tread)


class _CalcMore(Calc):
    """The members a stair, a notch or a roof adds (split from Calc only to keep each part readable)."""

    def zone_at(self, P: _Part, x: float, y: Optional[float] = None):
        for z in P.L.zones:
            if z.x0 - 0.5 <= x <= z.x0 + z.W + 0.5 and (y is None or z.wall_y - 0.5 <= y <= z.wall_y + z.D + 0.5):
                return z
        return None

    # -------------------------------------------------------------- stringers (any stair)
    def stringers(self, P: _Part, st, cid: str, group: str, label: str, tags: List[str]) -> Tuple[float, float, float]:
        """Stringer checks for every flight; returns the end reaction per stringer (D, L) of the worst flight and the trib."""
        c = self.c
        g = st.geo
        n = max(2, int(st.stringers or 2))
        trib = float(st.width) / (n - 1)
        sec = section("2x12", P.spec.framing.joist_species, P.spec.framing.joist_grade, repetitive=True)
        wD = c.stair_dead_psf * trib / 144.0
        wL = c.stair_live_psf * trib / 144.0
        th = _throat(sec.d, g.riser_in, g.tread_in)
        worst = (0.0, 0.0, 0.0)
        for fi, fg in enumerate(g.flights):
            if fg.run_in < 6.0:          # a single riser onto a landing: no stringers to check
                continue
            n_car = 0
            if st.mid_support and fi in (st.carrier_flights or []):
                n_car = len(st.carrier_fracs or [0.5])
            span = fg.run_in / (n_car + 1)
            ftag = f"{cid}.f{fi + 1}" if len(g.flights) > 1 else cid
            mem = f"{label}: {n} stringers 2x12 {sec.species} {sec.grade} @ {trib:.1f}\", flight {fi + 1} ({fg.risers} risers, run {_ftin(fg.run_in)}" + (f", {n_car} carrier{'s' if n_car > 1 else ''}" if n_car else "") + ")"
            S = sec.t * th ** 2 / 6.0; A = sec.t * th; I = sec.t * th ** 3 / 12.0
            M = (wD + wL) * span ** 2 / 8.0
            V = (wD + wL) * span / 2.0
            self.add(Check(f"{ftag}.1", group, mem, "Bending on the throat", M / S, sec.Fb(1.0), "psi", f"NDS 2018 3.3; {sec.table}",
                           f"w = ({c.stair_dead_psf:g} + {c.stair_live_psf:g}) psf x {trib:.1f}\" = {(wD + wL) * 12:.0f} plf (horizontal) · span {span:.1f}\" · M = wL²/8 = {M:,.0f} lb-in · "
                           f"throat {th:.2f}\" (2x12 less r·t/√(r²+t²) at {g.riser_in:.2f}/{g.tread_in:.2f}) · S = {S:.2f} in3 · F'b = {sec.factors_text('Fb')} = {sec.Fb():,.0f} psi", tags=tags))
            self.add(Check(f"{ftag}.2", group, mem, "Shear on the throat", 1.5 * V / A, sec.Fv(1.0), "psi", "NDS 2018 3.4",
                           f"V = {V:,.0f} lb · fv = 1.5V/(b x throat) = {1.5 * V / A:,.0f} psi", tags=tags))
            dl = 5 * wL * span ** 4 / (384 * sec.E() * I)
            self.add(Check(f"{ftag}.3", group, mem, "Deflection, live (L/360)", dl, span / 360.0, "in", "IRC Table R301.7",
                           f"Δ = 5 wL L⁴/384 E'I on the throat = {dl:.3f}\" vs {span:.1f}/360 = {span / 360:.3f}\"", tags=tags))
            # DCA6's 6'-0" is a prescriptive limit: past it, with the NDS rows above passing, the span is the engineer's call (REVIEW) —
            # a flight the spec leaves without a mid-run carrier (owner, 27 Oct) shows its full run here
            r_nds = max(M / S / sec.Fb(1.0), 1.5 * V / A / sec.Fv(1.0), dl / (span / 360.0))
            note4 = ""
            if span > 72.0 and r_nds <= 1.0:
                note4 = (("no mid-run carrier on this flight (the stair's mid_support is off)" if not n_car else f"{n_car} carrier{'s' if n_car > 1 else ''}")
                         + f": over DCA6's prescriptive 6'-0\" for cut 2x12 stringers; the NDS checks on the throat (bending, shear, deflection) pass, worst ratio {r_nds:.2f} — "
                         "the engineer accepts the span or details a support")
            self.add(Check(f"{ftag}.4", group, mem, "Span between supports (DCA6 6'-0\")", span, 72.0, "in", "AWC DCA6 Fig. 24 (cut 2x12 stringers)",
                           f"horizontal span {span:.1f}\" vs 72\"", status="REVIEW" if note4 else "", note=note4, tags=tags))
            margin = th - 5.0
            m_txt = f"{margin:.2f}" if margin >= 0.01 else f"{margin:.3f}"
            note5 = f"{m_txt}\" over the 5\" minimum (under 1/8\"): the engineer confirms the cut throat" if 0.0 <= margin < 0.125 else ""
            self.add(Check(f"{ftag}.5", group, mem, "Throat (5\" min.)", 5.0, th, "in", "AWC DCA6 Fig. 24", f"throat {th:.2f}\" ≥ 5\"",
                           status="REVIEW" if note5 else "", note=note5, tags=tags))
            R = (wD + wL) * span / 2.0
            if R > worst[0] + worst[1]:
                worst = (wD * span / 2.0, wL * span / 2.0, trib)
        return worst

    # -------------------------------------------------------------- the inset stair's notch (structure.md §5.2 framing)
    def notch(self, P: _Part, st):
        c = self.c
        nt = st.notch or {}
        tags = ["stair:" + str(getattr(st, "side", ""))]
        grp = "Inset stair & notch"
        tag = f"N-{P.tag}"
        if nt.get("axis") != "x":
            self.add(Check(tag, grp, f"Inset stair on {st.side}", "Notch framing", 0, 0, "-", "IRC R507", "the notch's inner face crosses the joists: framed by the outline rims — engineer to detail",
                           status="REVIEW", tags=tags))
            return
        z = self.zone_at(P, nt["face"])
        if z is None:
            return
        fr = z.frame
        sec_j = self.joist_section(P)
        plies = fr.rim_plies
        hdr = section(f"({plies}){P.spec.framing.joist_size}" if plies > 1 else P.spec.framing.joist_size, P.spec.framing.joist_species, P.spec.framing.joist_grade)
        ht = plies * 1.5
        s = float(fr.spacing)
        start, sup, end = self.zone_supports(P, z)
        lo, hi = nt["lo"] - z.wall_y, nt["hi"] - z.wall_y
        face, out, sgn, pline = nt["face"], nt["out"], nt["sgn"], nt.get("post_line", nt["out"])
        wD, wL = c.dead_psf * s / 144.0, c.deck_live_psf * s / 144.0
        tipD = c.edge_dead_plf * s / 12.0
        # stringers and their end reactions
        RsD, RsL, trib_s = self.stringers(P, st, f"N-{P.tag}S", grp, "Inset stair", tags)
        n_s = max(2, int(st.stringers or 2))
        # tail joists: house side (ledger -> inner header) and yard side (outer header -> beam -> front)
        y_bh, y_fh = lo - ht / 2.0, hi + ht / 2.0
        bt = (lo - ht) - start
        tail_back = (wD * bt / 2.0, wL * bt / 2.0) if (fr.ledger and bt > 6.0) else (0.0, 0.0)
        ft_sup = [hi + ht] + [b for b in sup if b > hi + ht + 1.0]
        tail_front = (0.0, 0.0, 0.0)
        if len(ft_sup) >= 2:
            rf = run_member(sec_j, hi + ht, end, ft_sup, [("u", hi + ht, end, wD), ("p", end, tipD)], [("u", hi + ht, end, wL)])
            d0 = rf.dead.R[0]; lp = sum(max(0.0, l.R[0]) for l in rf.lives); ln_ = sum(min(0.0, l.R[0]) for l in rf.lives)
            tail_front = (d0, lp, ln_)
            back = ft_sup[1] - ft_sup[0]; cant = end - ft_sup[-1]
            mem = f"Notch tail joists, yard side: {_ftin(back)} back-span + {_ftin(cant)} cantilever off the outer header"
            if d0 + ln_ < 0:
                hz = PRODUCTS["LUS210Z"]
                self.add(Check(f"{tag}.T1", grp, mem, "Uplift at the outer header (LUS210Z)", -(d0 + ln_), hz["up"], "lb", hz["src"] + "; IRC R507.6 (L/4)",
                               f"the tail joist cantilevers {cant:.1f}\" past the beam on a {back:.1f}\" back-span: header end reaction D {d0:,.0f} + L {ln_:,.0f} lb (lifts)",
                               status="REVIEW" if cant > back / 4 else "", note="the cantilever is over L/4 of the back-span: the outer header must hold the tails down — move the beam out under the rim (structure.md U1) or detail the uplift", tags=tags))
            for ck in flexure_checks(rf, f"{tag}.TF", grp, mem, self.scope, tags=tags):
                self.add(ck)
            # over the notch's width the beam carries these short tails, not full joists: correct the beam line's uniform load
            jr = self.joist_R.get((P.idx, z.name))
            xa_, xb_ = sorted((out, face))
            for k in range(1, len(ft_sup)):
                yb = ft_sup[k] + z.wall_y
                li = next((i for i, ln in enumerate(P.L.beam_lines) if abs(ln.y - yb) < 1.5), None)
                if li is None or not jr:
                    continue
                typ = jr["R"].get(round(ft_sup[k], 2))
                if typ is None:
                    continue
                td = rf.dead.R[k]; tl = sum(max(0.0, l.R[k]) for l in rf.lives)
                self.beam_corr.setdefault((P.idx, li), []).append((xa_, xb_, (td - typ[0]) / s, (tl - typ[1]) / s,
                                                                    f"over the stair notch ({_ftin(xa_)}-{_ftin(xb_)}) the beam carries tail joists ({td + tl:,.0f} lb each), not full joists"))
        # the two headers: notch post (outer end) -> trimmer (hanger)
        xa, xb = sorted((out, face))
        hdr_sup = sorted((pline, face))
        Rh = {}
        for key, y_h, (tD, tL, *rest) in (("inner", y_bh, tail_back + (0.0,)), ("outer", y_fh, tail_front)):
            if abs(tD) + abs(tL) < 1e-6 and key == "inner" and not fr.ledger:
                continue
            dead = [("u", xa, xb, tD / s + hdr.weight_plf / 12.0 + c.edge_dead_plf / 12.0)]
            live = [("u", xa, xb, tL / s)]
            other = {}
            if rest and rest[0] < 0:
                other["Wu"] = []           # placeholder (no wind on the header)
            r = run_member(hdr, xa, xb, hdr_sup, dead, live)
            mem = f"Notch {key} header {hdr.label}, {_ftin(abs(face - pline))} from the notch post to the trimmer"
            for ck in flexure_checks(r, f"{tag}.H{'I' if key == 'inner' else 'O'}", grp, mem, self.scope, tags=tags):
                self.add(ck)
            k_tr = 0 if hdr_sup[0] == face else 1
            k_po = 1 - k_tr
            Rtr = (r.dead.R[k_tr], sum(max(0.0, l.R[k_tr]) for l in r.lives), sum(min(0.0, l.R[k_tr]) for l in r.lives))
            Rpo = (r.dead.R[k_po], sum(max(0.0, l.R[k_po]) for l in r.lives), sum(min(0.0, l.R[k_po]) for l in r.lives))
            if key == "outer" and tail_front[2] < 0:     # the tails' uplift case on the header
                up_tr = (tail_front[0] + tail_front[2]) * abs(face - xa) / 2.0 / s
                Rtr = (Rtr[0], Rtr[1], min(Rtr[2], up_tr - Rtr[0]))
            Rh[key] = dict(y=y_h, tr=Rtr, po=Rpo)
            hz = PRODUCTS["HUCQ210-2-SDS"]
            self.add(Check(f"{tag}.H{'I' if key == 'inner' else 'O'}.h", grp, mem, "Hanger at the trimmer (HUCQ210-2-SDS)", Rtr[0] + Rtr[1], hz["down"], "lb", hz["src"],
                           f"header end on the trimmer: D {Rtr[0]:,.0f} + L {Rtr[1]:,.0f} lb", tags=tags))
        # the trimmer: ledger -> beam(s) -> front, carrying both header ends and the stringer tops
        tri = hdr
        xt = face + sgn * ht / 2.0
        dead = [("u", start, end, wD), ("p", end, tipD), ("u", lo, hi, RsD * n_s / max(1.0, hi - lo))]
        live = [("u", start, end, wL), ("u", lo, hi, RsL * n_s / max(1.0, hi - lo))]
        for key, v in Rh.items():
            dead.append(("p", v["y"], v["tr"][0])); live.append(("p", v["y"], v["tr"][1]))
        if len(sup) >= 2:
            rt = run_member(tri, start, end, sup, dead, live)
            mem = f"Notch trimmer {tri.label} at the top riser: spans " + " · ".join(_ftin(b - a) for a, b in zip(sup, sup[1:])) + (f" + {_ftin(end - sup[-1])}" if end - sup[-1] > 1 else "")
            for ck in flexure_checks(rt, f"{tag}.TR", grp, mem, self.scope, tags=tags):
                self.add(ck)
            if fr.ledger:
                R0 = rt.dead.R[0] + sum(max(0.0, l.R[0]) for l in rt.lives)
                hz = PRODUCTS["HUCQ210-2-SDS"]
                self.add(Check(f"{tag}.TR.h", grp, mem, "Hanger at the ledger (HUCQ210-2-SDS)", R0, hz["down"], "lb", hz["src"] + "; IRC R507.9.1.1 (no beam on the ledger)",
                               f"trimmer end on the ledger: {R0:,.0f} lb — joist-scale, not a girder", tags=tags))
            kb = len(sup) - 1
            Rb = rt.dead.R[kb] + sum(max(0.0, l.R[kb]) for l in rt.lives)
            bw = next((b.width for b in fr.beams if abs(b.cl_y - sup[kb]) < 1.0), 5.5)
            self.add(bearing_check(f"{tag}.TR.b", grp, mem, Rb, tri, tri.b, bw, self.scope, what="Bearing on the beam", tags=tags))
            # what the trimmer adds to the beam line over a typical joist
            jr = self.joist_R.get((P.idx, z.name))
            for k in range(1, len(sup)):
                yb = sup[k] + z.wall_y
                li = next((i for i, ln in enumerate(P.L.beam_lines) if abs(ln.y - yb) < 1.5), None)
                if li is None:
                    continue
                d = rt.dead.R[k]; l_ = sum(max(0.0, l.R[k]) for l in rt.lives)
                typ = jr["R"].get(round(sup[k], 2), (0.0, 0.0, 0.0)) if jr else (0.0, 0.0, 0.0)
                self.beam_pts.setdefault((P.idx, li), []).append((xt, dict(D=max(0.0, d - typ[0]), L=max(0.0, l_ - typ[1])), "notch trimmer"))
        # notch posts (header outer ends) and the stair foot
        ps = nt.get("post_size") or P.spec.framing.post_size
        Pp = [Rh[k]["po"] for k in ("inner", "outer") if k in Rh]
        if "ledger_bolts" in nt:
            self.base_ledger(P, st, nt, Pp, (RsD, RsL), n_s, ps, tags)
        else:
            self.carrier(P, st, nt, Pp, (RsD, RsL), n_s, ps, tags)

    def base_ledger(self, P, st, nt, Pp, Rs, n_s, ps, tags):
        """structure.md §5.2: the stringer heels and the two short notch posts bear on a (2)2x6 PT ledger through-bolted to
        the lower level's rim; that rim then works as a small flush beam to the lower ledger and beam."""
        c = self.c
        grp = "Inset stair & notch"
        tag = f"N-{P.tag}"
        n_b = int(nt.get("ledger_bolts") or 6)
        tot_D = Rs[0] * n_s + sum(p[0] for p in Pp)
        tot_L = Rs[1] * n_s + sum(p[1] for p in Pp)
        Zb = bolt_Z(0.5, 3.0, 3.0, 0.55, 0.55, theta_s=90.0, theta_m=90.0)
        Zp = Zb * 1.0 * 0.7
        tot = tot_D + tot_L
        self.add(Check(f"{tag}.BL", grp, f"Stair base ledger (2)2x6 PT, {n_b} x 1/2\" through-bolts to the lower rim", "Bolts, single shear ⊥ grain", tot / n_b, Zp, "lb",
                       "NDS 2018 12.3 (yield limit), CD 1.0, CM 0.7",
                       f"stringer heels {n_s} x {Rs[0] + Rs[1]:,.0f} lb + notch posts {sum(p[0] + p[1] for p in Pp):,.0f} lb = {tot:,.0f} lb / {n_b} bolts · "
                       f"Z⊥ = {Zb:,.0f} lb (3\" ledger on a 3\" rim, G 0.55) x 0.7 = {Zp:,.0f} lb", tags=tags))
        # the short posts on the ledger
        secp = section(ps, "SYP", "No.2")
        hp = float(getattr(st, "notch_post_len", 27.0) or 27.0)
        for i, p in enumerate(Pp):
            Pd = p[0] + p[1]
            cp, FcE = secp.Cp(hp, 1.0)
            cap = secp.Fc_star(1.0) * cp * secp.A
            self.add(Check(f"{tag}.P{i + 1}", grp, f"Notch post {ps} PT SYP No.2, {_ftin(hp)}, on the base ledger", "Axial + buckling", Pd, cap, "lb", "NDS 2018 3.7",
                           f"header end D {p[0]:,.0f} + L {p[1]:,.0f} lb · le/d = {hp / secp.t:.1f} · Cp {cp:.3f}", tags=tags))
            self.add(bearing_check(f"{tag}.P{i + 1}b", grp, f"Notch post {ps} on the (2)2x6 base ledger", Pd, section("(2)2x6", "SYP", "No.2"), secp.t, min(3.0, secp.d), self.scope,
                                   what="Post bearing on the ledger", tags=tags))
            if p[0] + p[2] < 0:
                self.add(Check(f"{tag}.P{i + 1}u", grp, f"Notch post {ps} hold-down", "Uplift at the header end", -(p[0] + p[2]), 2 * 295, "lb", "Simpson A35Z F1 x 2 (verify)",
                               f"the outer tails lift the header end: {-(p[0] + p[2]):,.0f} lb — tie the post to the header and to the base ledger", tags=tags))
        # the lower level's rim under the base ledger
        gx_face, gy0 = P.pl.pt(nt["out"] / 12.0, 0.0)
        for Q in self.parts:
            if Q is P:
                continue
            for zq in Q.L.zones:
                for side, xf in (("right", zq.x0 + zq.W), ("left", zq.x0)):
                    gxq, _ = Q.pl.pt(xf / 12.0, 0.0)
                    if abs(gxq - gx_face) > 2.0 / 12.0:
                        continue
                    self.lower_rim(Q, zq, side, xf, P, nt, tot_D, tot_L, tags)
                    return
        self.add(Check(f"{tag}.LR", grp, "Lower level rim under the stair base ledger", "Rim as a flush beam", 0, 0, "-", "IRC R507",
                       "no lower-level rim found on the notch's face line — the stair foot's support needs a detail", status="REVIEW", tags=tags))

    def lower_rim(self, Q, zq, side, xf, P, nt, totD, totL, tags):
        c = self.c
        grp = "Inset stair & notch"
        fr = zq.frame
        plies = fr.rim_plies
        rim = section(f"({plies}){Q.spec.framing.joist_size}" if plies > 1 else Q.spec.framing.joist_size, Q.spec.framing.joist_species, Q.spec.framing.joist_grade)
        start, sup, end = self.zone_supports(Q, zq)
        if len(sup) < 2:
            return
        # the base ledger's y range in the lower zone's own y
        _, gy_lo = P.pl.pt(0.0, nt.get("ledger_lo", nt["lo"]) / 12.0)
        _, gy_hi = P.pl.pt(0.0, nt.get("ledger_hi", nt["hi"]) / 12.0)
        ylo = _inv(Q.pl, 0.0, gy_lo)[1] * 12.0 - zq.wall_y
        yhi = _inv(Q.pl, 0.0, gy_hi)[1] * 12.0 - zq.wall_y
        ylo, yhi = sorted((ylo, yhi))
        s = float(fr.spacing)
        wD = c.dead_psf * (s / 2.0) / 144.0 + rim.weight_plf / 12.0 + 5.0 / 12.0       # half a bay + the rim + the skirt bearing on it
        wL = c.deck_live_psf * (s / 2.0) / 144.0
        span = max(1.0, yhi - ylo)
        dead = [("u", start, end, wD), ("u", ylo, yhi, totD / span), ("p", end, c.edge_dead_plf * s / 24.0)]
        live = [("u", start, end, wL), ("u", ylo, yhi, totL / span)]
        r = run_member(rim, start, end, sup, dead, live)
        mem = f"{Q.name} zone {zq.name} {side} rim {rim.label} carrying the stair foot: spans " + " · ".join(_ftin(b - a) for a, b in zip(sup, sup[1:])) + (f" + {_ftin(end - sup[-1])}" if end - sup[-1] > 1 else "")
        tag = f"N-{Q.tag}R"
        for ck in flexure_checks(r, tag, grp, mem, self.scope, tags=tags):
            self.add(ck)
        if fr.ledger:
            R0 = r.dead.R[0] + sum(max(0.0, l.R[0]) for l in r.lives)
            hz = PRODUCTS["HUCQ210-2-SDS"]
            self.add(Check(f"{tag}.h", grp, mem, "Hanger at the ledger (HUCQ210-2-SDS)", R0, hz["down"], "lb", hz["src"] + "; IRC R507.9.1.1",
                           f"rim end on the ledger {R0:,.0f} lb (an ordinary joist end is about {self.joist_R.get((Q.idx, zq.name), {}).get('R', {}).get(round(sup[0], 2), (0, 0, 0))[0] + self.joist_R.get((Q.idx, zq.name), {}).get('R', {}).get(round(sup[0], 2), (0, 0, 0))[1]:,.0f} lb)", tags=tags))
        xr = (zq.x0 + zq.W - plies * 0.75) if side == "right" else (zq.x0 + plies * 0.75)
        jr = self.joist_R.get((Q.idx, zq.name))
        for k in range(1, len(sup)):
            yb = sup[k] + zq.wall_y
            li = next((i for i, ln in enumerate(Q.L.beam_lines) if abs(ln.y - yb) < 1.5), None)
            if li is None:
                continue
            d = r.dead.R[k]; l_ = sum(max(0.0, l.R[k]) for l in r.lives)
            typ = jr["R"].get(round(sup[k], 2), (0.0, 0.0, 0.0)) if jr else (0.0, 0.0, 0.0)
            self.beam_pts.setdefault((Q.idx, li), []).append((xr, dict(D=max(0.0, d - typ[0] / 2.0), L=max(0.0, l_ - typ[1] / 2.0)), "lower rim with the stair foot"))

    def carrier(self, P, st, nt, Pp, Rs, n_s, ps, tags):
        """Older notch framing: the stringer feet on a (2)2x10 carrier hung between two posts on footings."""
        c = self.c
        grp = "Inset stair & notch"
        tag = f"N-{P.tag}"
        posts = nt.get("posts") or []
        if len(posts) < 2:
            return
        (xa, ya), (xb, yb) = posts[0], posts[1]
        Lc = abs(yb - ya)
        car = section("(2)" + P.spec.framing.joist_size, P.spec.framing.joist_species, P.spec.framing.joist_grade)
        ys = [min(ya, yb) + Lc * (k + 0.5) / n_s for k in range(n_s)]
        r = run_member(car, min(ya, yb), max(ya, yb), [min(ya, yb), max(ya, yb)], [("p", y, Rs[0]) for y in ys], [("p", y, Rs[1]) for y in ys])
        for ck in flexure_checks(r, f"{tag}.CA", grp, f"Stair foot carrier {car.label}, {_ftin(Lc)} between the notch posts", self.scope, tags=tags):
            self.add(ck)
        hgt = float(getattr(st, "notch_post_len", 0.0) or 0.0)
        for i, ((x, y), p) in enumerate(zip(posts, Pp + [(0.0, 0.0, 0.0)] * 2)):
            k = 0 if i == 0 else 1
            Rd = r.dead.R[k] + p[0]; Rl = sum(max(0.0, l.R[k]) for l in r.lives) + p[1]
            gx, gy = self.gxy(P, x, y)
            self.cols.append(dict(id=f"{P.tag}N{i + 1}", part=P.idx, part_name=P.name, line=-1, j=i, kind="notch", x=x, y=y, gx=gx, gy=gy, zone=None,
                                  height=hgt, comp={"D": [Rd, Rd], "L": [Rl, 0.0]}, pieces=[1, 1], label="inset-stair notch post", line_label="notch",
                                  end_post=True, cap_mid="", cap_end="", Vb=0.0, braced=False, on_footing=True, size=ps))

    # -------------------------------------------------------------- stairs to the yard (flights, landings, the top on the rim)
    def yard_stair(self, P: _Part, k: int, st, sd):
        c = self.c
        name = getattr(sd, "name", "") or f"stair on {st.side}"
        grp = "Stairs to the yard"
        tags = ["stair:" + name]
        tag = f"ST-{P.tag}{k + 1}"
        RsD, RsL, trib = self.stringers(P, st, f"{tag}S", grp, name, tags)
        n = max(2, int(st.stringers or 2))
        # the top flight hangs on the deck's rim: one stringer per joist bay, at the joist cantilever tip
        self.stair_on_rim(P, st, (RsD, RsL), name, tags)
        lands = [l for l in (getattr(sd, "landings", None) or []) if l]
        if not lands:
            self.stair_carriers(P, k, st, sd, name, tags)
            return
        g = st.geo
        for li, (la, lb) in enumerate(lands):
            la, lb = float(la), float(lb)
            long_, short = max(la, lb), min(la, lb)
            fr = P.L.zones[0].frame
            plies = fr.rim_plies
            jsec = self.joist_section(P)
            rim = section(f"({plies}){P.spec.framing.joist_size}", P.spec.framing.joist_species, P.spec.framing.joist_grade)
            pb = LUMBER_ACTUAL.get(P.spec.framing.post_size, (5.5, 5.5))[0]
            # landing joists @ 12" across the short way, rim to rim
            jsp = short - 2 * plies * 1.5
            wD, wL = c.dead_psf * 12.0 / 144.0, c.stair_live_psf * 12.0 / 144.0
            rj = run_member(jsec, 0.0, jsp, [0.0, jsp], [("u", 0.0, jsp, wD)], [("u", 0.0, jsp, wL)])
            for ck in flexure_checks(rj, f"{tag}L{li + 1}J", grp, f"{name}: landing {li + 1} joists {jsec.label} @ 12\", {_ftin(jsp)}", self.scope, tags=tags):
                self.add(ck)
            # the rim the flights bear on / hang from: half the landing + both flights (a switchback puts them side by side on it)
            span = long_ - pb
            x0, x1 = 0.0, span
            fl_w = float(st.width)
            half = c.dead_psf * short / 2.0 / 144.0, c.stair_live_psf * short / 2.0 / 144.0
            dead = [("u", x0, x1, half[0] + rim.weight_plf / 12.0 + c.edge_dead_plf / 12.0)]
            live = [("u", x0, x1, half[1])]
            nfl = len(g.flights)
            spots = [(x0, min(x1, x0 + fl_w))] + ([(max(x0, x1 - fl_w), x1)] if nfl > 1 else [])
            for (a, b) in spots:
                dead.append(("u", a, b, RsD * n / max(1.0, b - a))); live.append(("u", a, b, RsL * n / max(1.0, b - a)))
            rr = run_member(rim, x0, x1, [x0, x1], dead, live)
            mem = f"{name}: landing {li + 1} rim {rim.label}, {_ftin(span)} between corner posts (half the landing + the flights)"
            for ck in flexure_checks(rr, f"{tag}L{li + 1}R", grp, mem, self.scope, tags=tags):
                self.add(ck)
            # corner posts and footings: the layout's landing_post_h (frame bottom above the grade under the landing, the yard's fall
            # included) less the footing's top and the base; on the stair's own 12" caissons when own_footings > 0 — always the deck's
            # post and base (owner 27 Oct: 8x8 rough on ABU88RZ, no 6x6 / ABU66)
            Rd = max(rr.dead.R); Rl = max(sum(max(0.0, l.R[q]) for l in rr.lives) for q in range(2))
            own = int(getattr(st, "own_footings", 0) or 0)
            lph = list(getattr(st, "landing_post_h", None) or [])
            if li < len(lph):
                hp = max(6.0, float(lph[li]) - self.stair_standoff(P, own))
                hsrc = f"landing_post_h {lph[li]:.1f}\" less {self.stair_standoff(P, own):g}\" (footing top + base)"
            else:
                from .layout import DP_STANDOFF
                hland = g.total_rise_in - sum(f.rise_in for f in g.flights[:li + 1]) - float(getattr(sd, "landing_grade_in", None) or 0.0)
                hp = max(6.0, hland - 1.0 - LUMBER_ACTUAL[P.spec.framing.joist_size][1] - (DP_STANDOFF if P.spec.framing.footing_type == "diamond_pier" else self.stair_standoff(P, 0)))
                hsrc = "from the flights' rise"
            size = P.spec.framing.post_size
            foot = self.stair_caisson(P) if own else None
            model = None
            if not own and P.spec.framing.footing_type == "diamond_pier":
                model = next((ln_.item.split("—")[0].replace("Diamond Pier", "").strip() for ln_ in P.t.lines if "landing" in (ln_.item or "") and "Diamond Pier" in (ln_.item or "")), None)
                model = model if model in PIER else P.spec.framing.footing_model
            for q in range(4):
                self.cols.append(dict(id=f"{P.tag}S{k + 1}L{li + 1}-{q + 1}", part=P.idx, part_name=P.name, line=-1, j=q, kind="landing", x=0.0, y=0.0, gx=float("nan"), gy=float("nan"),
                                      zone=None, height=hp, comp={"D": [Rd, Rd], "L": [Rl, 0.0]}, pieces=[1, 1], label=f"{name} landing {li + 1} post ({hsrc})", line_label="landing",
                                      end_post=True, cap_mid="", cap_end="", Vb=0.0, braced=False, on_footing=True, size=size, model=model, footing=foot, tags=tags))
        self.stair_carriers(P, k, st, sd, name, tags)

    def stair_standoff(self, P: _Part, own: int) -> float:
        """Footing top above grade + the 1" standoff base: a caisson's caisson_above_in (6" default), the stair's own 12" caissons
        the same (6" when the deck is on another footing type), a Diamond Pier's head, a concrete pier's 2"."""
        from .layout import DP_STANDOFF, CONC_STANDOFF
        fsp = P.spec.framing
        if own or fsp.footing_type == "caisson":
            above = float(fsp.caisson_above_in) if (fsp.footing_type == "caisson" and fsp.caisson_above_in is not None) else 6.0
            return above + 1.0
        return {"diamond_pier": DP_STANDOFF, "concrete": CONC_STANDOFF}.get(fsp.footing_type, CONC_STANDOFF)

    def stair_caisson(self, P: _Part) -> dict:
        """Stair.landing_footing "caisson12": 12" caissons to the deck's caisson depth (frost + 2" without one)."""
        fsp = P.spec.framing
        dia = STAIR_CAISSON_DIA
        depth = float(fsp.caisson_depth_in or (self.c.frost_in + 2.0))
        end_b = math.pi * (dia / 24.0) ** 2 * self.c.soil_psf
        cap = end_b + math.pi * dia / 12.0 * depth / 12.0 * CAISSON_SKIN_PSF
        return dict(type="caisson", model=f"{dia:g}\" x {depth:g}\" caisson", dia=dia, depth=depth, cap=cap, end=end_b,
                    weight=math.pi * (dia / 24.0) ** 2 * depth / 12.0 * CONCRETE_PCF, own=True)

    def stair_carriers(self, P: _Part, k: int, st, sd, name: str, tags: List[str]):
        """A flight the spec gives a mid-run carrier (Stair.mid_support): a 2-ply 2x6 under the stringers on two of the deck's posts
        (on the stair's own 12" caissons when own_footings, else the deck's footings). With mid_support off there is none: the
        stringer rows show the full flight (beyond DCA6's 6'-0" it is the engineer's REVIEW)."""
        if not getattr(st, "mid_support", False):
            return
        c = self.c
        grp = "Stairs to the yard"
        tag = f"ST-{P.tag}{k + 1}"
        g = st.geo
        n = max(2, int(st.stringers or 2))
        trib = float(st.width) / (n - 1)
        w = (c.stair_dead_psf + c.stair_live_psf) * trib / 144.0
        wD = c.stair_dead_psf * trib / 144.0
        fracs = list(st.carrier_fracs or [0.5])
        own = int(getattr(st, "own_footings", 0) or 0)
        car = section("(2)2x6", P.spec.framing.joist_species, P.spec.framing.joist_grade)
        size = P.spec.framing.post_size                    # the deck's post and base under the stairs too (owner 27 Oct)
        pb = LUMBER_ACTUAL.get(size, (5.5, 5.5))[0]
        for fi in (st.carrier_flights or []):
            fg = g.flights[fi]
            span = fg.run_in / (len(fracs) + 1)
            R1 = 1.25 * w * span if len(fracs) == 1 else 1.1 * w * span        # a stringer continuous over the carrier(s)
            R1d = R1 * wD / w
            L_c = float(st.width) + 6.0 - pb
            ys = [L_c * (j + 0.5) / n for j in range(n)]
            r = run_member(car, 0.0, L_c, [0.0, L_c], [("p", y, R1d) for y in ys] + [("u", 0.0, L_c, car.weight_plf / 12.0)],
                           [("p", y, R1 - R1d) for y in ys])
            mem = f"{name}: carrier {car.label} under flight {fi + 1} ({len(fracs)} per flight), {_ftin(L_c)} between its posts, {n} stringers at {R1:,.0f} lb"
            for ck in flexure_checks(r, f"{tag}C{fi + 1}", grp, mem, self.scope, tags=tags):
                self.add(ck)
            below = sum(f_.rise_in for f_ in g.flights[fi + 1:])
            for ci, fr_ in enumerate(fracs):
                h_c = max(6.0, below + fg.rise_in * (1.0 - fr_) - self.stair_standoff(P, own))
                Rd = r.dead.R[0]; Rl = sum(max(0.0, l.R[0]) for l in r.lives)
                for q in range(2):
                    self.cols.append(dict(id=f"{P.tag}S{k + 1}C{fi + 1}{chr(97 + ci)}-{q + 1}", part=P.idx, part_name=P.name, line=-1, j=q, kind="landing", x=0.0, y=0.0,
                                          gx=float("nan"), gy=float("nan"), zone=None, height=h_c, comp={"D": [Rd, Rd], "L": [Rl, 0.0]}, pieces=[1, 1],
                                          label=f"{name} carrier post (flight {fi + 1})", line_label="carrier", end_post=True, cap_mid="", cap_end="", Vb=0.0,
                                          braced=False, on_footing=True, size=size, model=None, footing=self.stair_caisson(P) if own else None, tags=tags))

    def stair_on_rim(self, P: _Part, st, Rs, name, tags):
        """The top flight's stringers hang on the deck rim (LSCZ): the joists at the opening carry one stringer reaction each
        at the cantilever tip."""
        c = self.c
        edges = getattr(P.L, "outline_edges", None) or []
        pos = None
        if str(st.side).startswith("edge:") and edges:
            try:
                e = edges[int(str(st.side).split(":")[1]) - 1]
                L_ = e.length or 1.0
                t_ = (float(st.opening.start_in) + float(st.width) / 2.0) / L_
                pos = (e.x0 + (e.x1 - e.x0) * t_, e.y0 + (e.y1 - e.y0) * t_)
            except (ValueError, IndexError, AttributeError):
                pos = None
        if pos is None:
            for e in (P.L.edges or []):
                if e.name == st.side or e.name.startswith(str(st.side)):
                    pos = ((e.x0 + e.x1) / 2.0, (e.y0 + e.y1) / 2.0)
                    break
        if pos is None:
            return
        z = self.zone_at(P, pos[0])
        if z is None or abs(pos[1] - (z.wall_y + z.D)) > 6.0:
            self.add(Check(f"ST-{P.tag}top", "Stairs to the yard", f"{name}: top of the stair", "Stair hung on a side rim", 0, 0, "-", "IRC R507",
                           "the stair leaves a side of the deck: the rim it hangs on needs its own check", status="REVIEW", tags=tags))
            return
        jr = self.joist_R.get((P.idx, z.name))
        if not jr:
            return
        sec = jr["sec"]
        s = jr["s"]
        start, sup, end = jr["start"], jr["sup"], jr["end"]
        x0 = sup[-2] if len(sup) > 2 else start
        dead = [("u", x0, end, jr["wD"]), ("p", end, jr["tipD"] + Rs[0])]
        live = [("u", x0, end, jr["wL"]), ("p", end, Rs[1])]
        r = run_member(sec, x0, end, sup[-2:] if len(sup) > 2 else sup, dead, live, {"P220": [("p", end, c.cant_point_lb)]})
        mem = f"Zone {z.name} joists at the {name} opening: one stringer ({Rs[0] + Rs[1]:,.0f} lb) on each joist's cantilever tip (LSCZ on the rim)"
        for ck in flexure_checks(r, f"J-{P.tag}{z.name}st", "Stairs to the yard", mem, self.scope, tags=tags):
            self.add(ck)

    # -------------------------------------------------------------- the louvered roof's posts on the deck
    def roof(self):
        from . import louvered as lv
        try:
            roofs = [r for r in lv.roofs_of(self.spec) if lv.built(r)] if self.spec.geometry.parts else \
                [r for r in (getattr(self.spec.geometry, "louvered_roofs", None) or []) if lv.built(r)]
        except Exception:
            roofs = []
        if not roofs:
            return
        c = self.c
        surf = lv.surfaces_of(self.t.layout)
        for ri, r in enumerate(roofs):
            q = lv.resolve(r, surf)
            posts = q["posts"]
            n = max(1, len(posts))
            trib = q["area"] / 2.0 / n if q["attach"] == "house" else q["area"] / n
            qh, Kz = wind_q(c, q["z_top"])
            D = ROOF_DEAD_PSF * trib + ROOF_POST_DEAD_LB
            S = (c.roof_snow_psf + ROOF_SLIDING_PSF) * trib
            Wd = qh * c.G * ROOF_CN_DOWN * trib
            Wu = -qh * c.G * ROOF_CN_UP * trib
            self.roofs.append(dict(name=q["name"], area=q["area"], trib=trib, D=D, S=S, Wd=Wd, Wu=Wu, qh=qh, Kz=Kz, z_top=q["z_top"], attach=q["attach"],
                                   posts=[(p["x"], p["y"]) for p in posts], screens=q.get("screens") or []))
            grp = "Louvered roof load path"
            tags = ["roof"]
            self.add(Check(f"R-{ri + 1}.0", grp, f"{q['name']} ({q['W']:.1f}' x {q['D']:.1f}', {q['attach']}-attached, {n} posts on the deck)", "Post reactions (ASD inputs)",
                           D + S, 0.0, "lb", "ASCE 7-16 Ch. 7, 26-27; Centennial Sec. 18-2-30",
                           f"trib {trib:.0f} SF per post · D = {ROOF_DEAD_PSF:g} psf x {trib:.0f} + {ROOF_POST_DEAD_LB:g} = {D:,.0f} lb · S = ({c.roof_snow_psf:g} + {ROOF_SLIDING_PSF:g} sliding) psf = {S:,.0f} lb · "
                           f"qh = {qh:.1f} psf at {q['z_top']:.1f}' (Kz {Kz:.2f}) · W↓ = qh G {ROOF_CN_DOWN:g} = {Wd:,.0f} lb, W↑ = {Wu:,.0f} lb (louvers closed)",
                           status="INFO", tags=tags, note="Suncoast's stamped reactions replace these"))
            self.roof_screens(q, posts, tags)
            for pi, p in enumerate(posts):
                part = None
                for P in self.parts:
                    if abs(P.spec.geometry.height_in / 12.0 - p["z_deck"]) < 0.2 or len(self.parts) == 1:
                        lx, ly = _inv(P.pl, p["x"], p["y"])
                        if self.zone_at(P, lx * 12.0, ly * 12.0) is not None:
                            part = (P, lx * 12.0, ly * 12.0)
                            break
                if part is None:
                    continue
                P, xl, yl = part
                self.roof_post(P, ri, pi, xl, yl, dict(D=D, S=S, Wd=Wd, Wu=Wu), q, tags)

    def roof_screens(self, q: dict, posts: list, tags: List[str]):
        """Option 3a: screens down catch wind (rated to 65 mph, they retract above it). The fabric spans between its side
        tracks; each track post takes half a screen, half of that at its (pinned) base."""
        c = self.c
        scr = [sc for sc in (q.get("screens") or []) if float(sc.get("drop") or 0) > 0]
        if not scr:
            return
        grp = "Louvered roof load path"
        for sc in scr:
            h = max(0.0, float(sc["z_top"]) - float(sc["z_bottom"])) * float(sc.get("drop") or 1.0)
            A = float(sc["width"]) * h
            q65, Kz = wind_q(c, (float(sc["z_top"]) + float(sc["z_bottom"])) / 2.0, V=SCREEN_V_MPH)
            F = 0.6 * q65 * c.G * SCREEN_CF * A
            V = F / 4.0
            direction = "y" if sc.get("plane") == "y" else "x"
            near = []
            for p in posts:
                d = min(math.hypot(p["x"] - sc["a"][0], p["y"] - sc["a"][1]), math.hypot(p["x"] - sc["b"][0], p["y"] - sc["b"][1]))
                if d < 1.5:
                    near.append(p)
            for p in near:
                part = next((P for P in self.parts if abs(P.spec.geometry.height_in / 12.0 - p["z_deck"]) < 0.2), self.parts[0])
                ex = self.extra_lat.setdefault(part.idx, [0.0, 0.0])
                ex[0 if direction == "x" else 1] += V
            Zb = bolt_Z(0.5, 0.5, 3.0, 0.0, SPECIFIC_GRAVITY["SYP"], theta_m=90.0, Fes=1.5 * 38000.0)
            cap = 4 * Zb * 1.6 * 0.7
            self.add(Check(f"R-S{sc.get('index', 0) + 1}", grp, f"{q['name']}: {sc.get('name', sc['side'] + ' screen')} down, {float(sc['width']):.1f}' x {h:.1f}' ({A:.0f} SF)",
                           f"Base shear per track post at {SCREEN_V_MPH:g} mph", V, cap, "lb", "ASCE 7-16 Ch. 29 (Cf {0:g}); NDS 2018 12.3".format(SCREEN_CF),
                           f"qz = {q65:.1f} psf at {SCREEN_V_MPH:g} mph (Kz {Kz:.2f}) · F = 0.6 qz G Cf A = {F:,.0f} lb · half to each side track, half of that at the pinned base: {V:,.0f} lb "
                           f"on {len(near)} roof post(s) ({direction}) · 4 x 1/2\" bolts, aluminum plate (Fe 1.5 x 38 ksi) into SYP blocking: 4 x {Zb:,.0f} x 1.6 x 0.7 = {cap:,.0f} lb",
                           tags=tags + ["screens"], note="the screens retract automatically above 65 mph (wind sensor) — the roof's frame braces the post tops"))

    def roof_post(self, P: _Part, ri: int, pi: int, xl: float, yl: float, R: dict, q: dict, tags: List[str]):
        c = self.c
        grp = "Louvered roof load path"
        tag = f"R-{ri + 1}.{pi + 1}"
        mem = f"Roof post {pi + 1} at ({q['posts'][pi]['x']:.2f}', {q['posts'][pi]['y']:.2f}') on the {P.name.lower()}"
        # a column directly under it?
        best = None
        for li, ln in enumerate(P.L.beam_lines):
            for j, px in enumerate(ln.posts_x):
                d = math.hypot(px - xl, ln.y - yl)
                if best is None or d < best[0]:
                    best = (d, li, j, px, ln)
        if best and best[0] <= 9.0:
            d, li, j, px, ln = best
            self.beam_pts.setdefault((P.idx, li), []).append((px, dict(D=R["D"], S=R["S"], Wd=R["Wd"], Wu=R["Wu"]), "roof post"))
            self.add(Check(f"{tag}.a", grp, mem, "Load path: column directly under the roof post", d, 9.0, "in", "load path",
                           f"roof post {d:.1f}\" from column {P.tag}{li + 1}-{j + 1} on beam {P.tag}{li + 1}: the reactions go straight down the column (beam, cap, column, base "
                           f"and pier rows include them)", tags=tags))
            self.roof_uplift_chain(P, tag, mem, R, tags)
            return
        # otherwise it stands on the joists: a doubled joist + blocking takes it on its cantilever
        z = self.zone_at(P, xl, yl)
        if z is None:
            return
        jr = self.joist_R.get((P.idx, z.name))
        if not jr:
            return
        sup, end = jr["sup"], jr["end"]
        y = yl - z.wall_y
        sec2 = section("(2)" + P.spec.framing.joist_size, P.spec.framing.joist_species, P.spec.framing.joist_grade)
        x0 = sup[-2]
        dead = [("u", x0, end, 2 * jr["wD"]), ("p", end, 2 * jr["tipD"]), ("p", min(end, y), R["D"])]
        live = [("u", x0, end, 2 * jr["wL"])]
        other = {"S": [("p", min(end, y), R["S"])], "Wd": [("p", min(end, y), R["Wd"])], "Wu": [("p", min(end, y), R["Wu"])]}
        r = run_member(sec2, x0, end, sup[-2:], dead, live, other)
        m2 = mem + f" — on a doubled joist {_ftin(y - sup[-1])} out on the cantilever (no column under it)"
        for ck in flexure_checks(r, f"{tag}.c", grp, m2, self.scope, tags=tags):
            self.add(ck)
        k0 = 0
        rr, nm, e, cap = governing(r.comp_at("R", k0), lambda cd: PRODUCTS["LUS210Z"]["up"] * 2, sign=-1)
        if e < 0:
            self.add(Check(f"{tag}.u", grp, m2, f"Uplift at the back support ({nm})", -e, 2 * PRODUCTS["LUS210Z"]["up"], "lb", PRODUCTS["LUS210Z"]["src"],
                           f"the roof post's lever on the cantilever lifts the joists' back ends: {-e:,.0f} lb on 2 hangers", tags=tags))
        li = next((i for i, ln in enumerate(P.L.beam_lines) if abs(ln.y - (sup[-1] + z.wall_y)) < 1.5), None)
        if li is not None:
            k = len(r.supports) - 1
            comp = r.comp_at("R", k)
            self.beam_pts.setdefault((P.idx, li), []).append((xl, dict(D=comp["D"][0] - 2 * jr["R"].get(round(sup[-1], 2), (0, 0, 0))[0], S=comp.get("S", (0, 0))[0],
                                                                  Wd=r.other["Wd"].R[k], Wu=r.other["Wu"].R[k]), "roof post via the joists"))
        self.roof_uplift_chain(P, tag, m2, R, tags)

    def roof_uplift_chain(self, P, tag, mem, R, tags):
        c = self.c
        grp = "Louvered roof load path"
        U = -(0.6 * R["D"] + 0.6 * R["Wu"])
        if U <= 0:
            self.add(Check(f"{tag}.U", grp, mem, "Net uplift (0.6D + 0.6W)", 0.0, 1.0, "lb", "ASCE 7-16 2.4.1", "dead load exceeds the wind uplift", tags=tags))
            return
        wash = 3.8 * section("2x10", P.spec.framing.joist_species).Fcp()
        self.add(Check(f"{tag}.U1", grp, mem, "Base plate to blocking: 4 x 1/2\" bolts, 2\"x2\" plate washers", U / 4.0, wash, "lb", "NDS 2018 3.10 (washer bearing)",
                       f"net uplift U = 0.6 x {R['D']:,.0f} + 0.6 x ({R['Wu']:,.0f}) = {-U:,.0f} lb · per bolt {U / 4:,.0f} lb vs washer bearing 3.8 in2 x F'c⊥ = {wash:,.0f} lb", tags=tags))
        cs = PRODUCTS["CS16"]
        self.add(Check(f"{tag}.U2", grp, mem, "Blocking to the beam / column: CS16 strap", U, cs["tension"], "lb", cs["src"],
                       f"U = {U:,.0f} lb from the blocking down the beam face to the column (structure.md §7.3)", tags=tags))
        self.add(Check(f"{tag}.M", grp, mem, "Base moment if the deck had to fix the post", c.guard_lb * ROOF_GUARD_H_IN, 0.0, "lb-in", "IRC Table R301.5; ESR-4217 §5.4",
                       f"the post is a rail post: the 200 lb guard load at {ROOF_GUARD_H_IN:g}\" alone is {c.guard_lb * ROOF_GUARD_H_IN:,.0f} lb-in, plus wind / screens. "
                       "The deck gives a pinned base: Suncoast's frame (house attachment, knee braces) must brace the post top in both directions", status="REVIEW", tags=tags))

    # -------------------------------------------------------------- guards
    def guards(self):
        c = self.c
        for P in self.parts:
            if not P.L.rail:
                continue
            sysname = getattr(P.L.rail, "system", "") or ""
            H = float(getattr(P.spec.railing, "height_in", 36) or 36) + (1.5 if getattr(P.spec.railing, "drink_rail", False) else 0.0) + 1.0
            M = c.guard_lb * H
            lever = 4.375
            T = M / lever
            tag = f"G-{P.tag}" if P.tag else "G"
            if "IRX" in sysname or "Impression" in sysname:
                self.add(Check(f"{tag}.1", "Guards", f"{P.name}: {sysname} posts on surface bases (4 x 3/8\" x 6\" GRK RSS)", "Post, base and screws (tested assembly)",
                               0.50, SPECIFIC_GRAVITY.get(_species_key(P.spec.framing.joist_species), 0.5), "-", "ICC-ES ESR-4217 §4.2, §5.4; IRC Table R301.5",
                               f"ESR-4217 qualifies the post + base + four screws into wood of SG ≥ 0.50 for the 200 lb top load; blocking is {P.spec.framing.joist_species} "
                               f"(G {SPECIFIC_GRAVITY.get(_species_key(P.spec.framing.joist_species), 0.5)}) · M = 200 x {H:.1f}\" = {M:,.0f} lb-in at the deck (drink cap raises it)"))
            blk = section("(2)" + P.spec.framing.joist_size, P.spec.framing.joist_species, P.spec.framing.joist_grade)
            span = P.L.zones[0].frame.spacing - 1.5
            Mb = T / 2.0 * span / 4.0 * 2.0
            self.add(Check(f"{tag}.2", "Guards", f"{P.name}: rail-post blocking {blk.label} between joists ({span:g}\")", "Blocking bending under the post couple",
                           Mb / blk.S, blk.Fb(1.0), "psi", "NDS 2018 3.3",
                           f"tension pair T = M / {lever}\" = {T:,.0f} lb as two loads near mid-span of a {span:g}\" block: M ≈ {Mb:,.0f} lb-in · S = {blk.S:.1f} in3"))


ROOF_DEAD_PSF = 6.0          # louvered/research.md §3.4 (E; a StruXure ICC design uses 5 psf)
ROOF_POST_DEAD_LB = 150.0    # front beam half + post + base + gutter, per post (E)
ROOF_SLIDING_PSF = 11.0      # ASCE 7-16 §7.9 sliding snow off the house roof, averaged over the roof (W ≈ 14' assumed — research §3.4, structure §7.1)
ROOF_CN_DOWN = 1.2           # net pressure coefficients, louvers closed (ASCE 7-16 Fig. 27.3-4 free roof; §30.11 attached canopy ≈ 1.3)
ROOF_CN_UP = 1.3
ROOF_GUARD_H_IN = 42.0       # the IRX guard's 200 lb at the drink-rail top, when the roof post is the rail post
SCREEN_V_MPH = 65.0          # Suncoast screens are rated to 65 mph and retract above it (louvered/research.md §1.6)
SCREEN_CF = 1.3              # mesh at 80-90% density taken as a solid sign (ASCE 7-16 Fig. 29.3-1, wide and shallow)


# ================================================================== run + package
def _analyze(spec, scope: str = "Base", exposure: Optional[str] = None) -> _CalcMore:
    k = _CalcMore(spec, scope, exposure)
    sizes = {spec.framing.joist_size, spec.framing.post_size} | {section_size(b.size) for b in (spec.framing.beams or [])}
    if spec.framing.system == "steel" or any(sz not in LUMBER_ACTUAL for sz in sizes if sz):
        k.add(Check("X-1", "Joists & cantilevers", f"{spec.framing.system} frame ({', '.join(sorted(x for x in sizes if x))})", "Member design", 0, 0, "-",
                    "AISI S100 / S240 (cold-formed steel) or the engineer's design",
                    "this calculation covers sawn-lumber frames (NDS); the frame's members are outside it — the engineer of record designs them", status="REVIEW"))
        return k
    for P in k.parts:
        for z in P.L.zones:
            k.zone_joists(P, z)
    for P in k.parts:
        for st in P.L.stairs:
            if getattr(st, "inset", False) and st.notch:
                k.notch(P, st)
    for P in k.parts:
        sds = list(P.spec.stairs or [])
        for i, st in enumerate(P.L.stairs):
            if getattr(st, "inset", False):
                continue
            sd = sds[i] if i < len(sds) else None
            k.yard_stair(P, i, st, sd)
    k.roof()
    for P in k.parts:
        k.beam_lines(P)
    k.lateral()
    k.columns()
    k.column_wind_rows()
    k.caps_and_bases()
    k.footings()
    k.guards()
    return k


def _criteria_rows(spec, c: Criteria) -> List[Tuple[str, str, str]]:
    s = spec.site
    q15, kz15 = wind_q(c, 15.0)
    return [
        ("Code", "2021 IRC as amended by the City of Centennial (Ord. 2023-O-06, Sec. 18-2-30); IRC R507 decks" if (s.city or "").lower() == "centennial"
         else "2021 IRC (R507 decks) as adopted", "jurisdiction"),
        ("Design standards", "ASCE 7-16 (loads, ASD combinations 2.4.1) · AWC NDS 2018 + Supplement · AWC DCA6 (cross-checks)", "IRC R301.1.3"),
        ("Deck live load", f"{c.live_psf:g} psf (IRC Table R301.5); ground snow {c.ground_snow_psf:g} psf, not concurrent — the deck carries {c.deck_live_psf:g} psf", "IRC R301.5, R507.1"),
        ("Deck dead load", f"{c.dead_psf:g} psf (PVC decking, 2x joists @ 12\", blocking, hardware) + beam and column self weight at {WOOD_PCF:g} pcf + {c.edge_dead_plf:g} plf at the deck edge", "IRC R507 tables basis"),
        ("Guard", f"{c.guard_lb:g} lb concentrated at the top, any direction", "IRC Table R301.5"),
        ("Cantilever", f"{c.cant_point_lb:g} lb at the cantilever end, deflection 2a/180", "IRC Table R507.6 note"),
        ("Stairs", f"{c.stair_live_psf:g} psf live + {c.stair_dead_psf:g} psf dead; 300 lb on a tread (treads by TimberTech)", "IRC Table R301.5"),
        ("Roof snow", f"{c.roof_snow_psf:g} psf non-reducible (louvered roof) + sliding snow off the house roof", "Centennial Sec. 18-2-30; ASCE 7-16 7.9"),
        ("Wind", f"Vult {c.wind_mph:g} mph, Risk Cat. II, Exposure {c.exposure}, Kd {c.Kd:g}, Kzt {c.Kzt:g} (city: no topographic effect), Ke {c.Ke:g} · qz = {q15:.1f} psf at 15'",
         "ASCE 7-16 Ch. 26; Centennial Table R301.2(1)"),
        ("Seismic", f"SDC {c.sdc} · SDS taken {c.sds:g} (top of SDC B), R {c.R:g}, Ie {c.Ie:g}", "Centennial Table R301.2(1); ASCE 7-16 Ch. 11-12"),
        ("Frost / soil", f"frost line {c.frost_in:g}\" · {c.soil_psf:,.0f} psf presumptive (silts / clays)", "Centennial Table R301.2(1); IRC Table R401.4.1"),
        ("Service", "wet service (exterior): CM on every member; treated SYP not incised; DF-L timbers per NDS Table 4D", "NDS 2018 4.1.4"),
    ]


def _material_rows(k: _CalcMore) -> List[Tuple[str, str, str]]:
    rows = []
    seen = set()
    P = k.parts[0]
    fr = P.spec.framing
    cands = []
    for args in [(fr.joist_size, fr.joist_species, fr.joist_grade), ("2x12", fr.joist_species, fr.joist_grade)] + \
            [(ln.size, ln.species, ln.species) for Q in k.parts for ln in Q.L.beam_lines]:
        if section_size(args[0]) in LUMBER_ACTUAL:
            cands.append(section(*args, repetitive=args[0] in (fr.joist_size, "2x12")))
    if fr.post_size in LUMBER_ACTUAL:
        cands.append(k.col_section(dict(size=fr.post_size, kind="beam")))
    for sec in cands:
        key = sec.label
        if key in seen:
            continue
        seen.add(key)
        r = sec.ref
        rows.append((sec.label, f"Fb {r['Fb']:,} · Fv {r['Fv']} · Fc⊥ {r['Fcp']} · Fc {r['Fc']:,} · E {r['E'] / 1e6:.1f}M · Emin {r['Emin']:,} psi · "
                                f"F'b {sec.Fb():,.0f} · F'v {sec.Fv():,.0f} · F'c⊥ {sec.Fcp():,.0f} · E' {sec.E() / 1e6:.2f}M psi (CD 1.0, wet)", sec.table))
    return rows


def _load_rows(k: _CalcMore) -> List[Tuple[str, str, str]]:
    c = k.c
    rows = []
    for P in k.parts:
        lat = getattr(P, "lat", None)
        if lat:
            rows.append((f"{P.name}: lateral", f"wind Fx {lat['Fx']:,.0f} / Fy {lat['Fy']:,.0f} lb (strength) · seismic E = {lat['Cs']:.3f} x {lat['W']:,.0f} = {lat['E']:,.0f} lb · "
                                                 f"ASD HX {lat['HX']:,.0f} / HY {lat['HY']:,.0f} lb", f"qz {lat['qz']:.1f} psf, Kz {lat['Kz']:.2f}, {lat['area']:.0f} SF"))
    for r in k.roofs:
        rows.append((f"{r['name']}: per post", f"D {r['D']:,.0f} · S {r['S']:,.0f} · W↓ {r['Wd']:,.0f} · W↑ {r['Wu']:,.0f} lb (strength-level W)",
                     f"{r['trib']:.0f} SF per post, qh {r['qh']:.1f} psf at {r['z_top']:.1f}'"))
    return rows


def _review_and_assumptions(k: _CalcMore) -> Tuple[List[str], List[str]]:
    c = k.c
    spec = k.spec
    review = [
        "Verify every connector value marked \"verify\" against Simpson C-C-2026 / the current ESRs (LUS210Z, HUCQ210-2-SDS, H2.5AZ, CS16, A35Z): these rows use conservative catalog readings.",
        _base_review(k),
        *_footing_review(k),
        *_stair_review(k),
        "LedgerLOK is checked at a 1/2\" lag equivalence of 375 lb per screw: confirm with ESR-1078's ledger table for the joist spans here. Verify each ledger lands on a solid band (no brick veneer, IRC R507.9.1.1) and the hold-downs reach interior framing.",
        f"Wind Exposure {c.exposure} is used (conservative for the greenbelt behind the lot; IRC default B). Ke = 1.0 (ASCE 7-16 Table 26.9-1 allows about 0.82 at this elevation).",
        f"Seismic SDS taken at {c.sds:g} (top of SDC B); wind governs the deck's lateral design in both directions here.",
        "The lateral system is the house attachment (ledgers + R507.9.2 hold-downs + the deck boards and joists as a diaphragm); columns are pinned at both ends and braced at the top by the joists. Knee braces at the end columns of each line are checked as a redundant path (AWC: corner posts only) — confirm the patio headroom (6'-8\") where they go.",
        "6x10 DF-L No.1 beams are outside IRC Table R507.5: this calculation (continuous spliced pieces, patterned live load) is their design; splices land on columns and are strapped (cap uplift values do not apply at splices).",
        "Untreated Douglas fir timbers outdoors need the building official's acceptance (IRC R317 / R507.2) or treated timbers; keep the column feet on standoff bases.",
    ]
    if k.roofs:
        review.insert(3, "Louvered roof: Suncoast's stamped engineering (30 psf roof snow + sliding snow, 115 mph, house attachment, front beam on 2 posts) replaces the roof reactions used here; "
                         "the deck gives the roof posts a pinned base — the roof's own frame must brace the post tops.")
    if any(st.inset for P in k.parts for st in P.L.stairs):
        review.append("The inset stair's level-change details (notch headers on short posts, the stair base ledger bolted to the lower rim, the lower rim as a flush beam) are non-table: confirm the details shown.")
    fails = [ck for ck in k.checks if ck.result == "FAIL"]
    if fails:
        review.insert(0, f"{len(fails)} check{'s' if len(fails) != 1 else ''} FAIL as the layout stands: " + "; ".join(f"{ck.id} ({ck.what})" for ck in fails[:8])
                      + (" …" if len(fails) > 8 else "") + " — resolve before the set is stamped.")
    assumptions = [
        f"Geometry is the engine's layout of the spec: deck heights {', '.join(f'{P.name} {_ftin(P.spec.geometry.height_in)}' for P in k.parts)} above grade; column lengths from the deck height less decking, joist, beam and the pier standoff.",
        "Joists are analyzed both spliced over interior beams and continuous (where one stick can run); the worse result governs. Beam pieces are continuous over their posts and end at the splices the layout shows.",
        "Live load is patterned span by span on every member (the envelope takes each span's live load where it makes the effect worse); deck live load and snow are not concurrent (IRC R507).",
        "Over a stair notch the beam carries the notch's short tail joists (the typical joist line load is corrected there) plus the trimmer's reaction above a typical joist's.",
        "Member sizes are dressed (NDS Table 1B): 6x10 = 5-1/2 x 9-1/2, 8x8 = 7-1/2 x 7-1/2; rough-sawn stock is larger (conservative).",
        "Shear is checked at the support (loads within d of the support not removed) — conservative.",
        f"Deck-edge dead load {c.edge_dead_plf:g} plf (doubled rim, fascia, guard and drink rail) at every joist's end.",
    ]
    if k.roofs:
        assumptions.append(f"Louvered roof: {ROOF_DEAD_PSF:g} psf dead + {ROOF_POST_DEAD_LB:g} lb per post; {c.roof_snow_psf:g} psf snow + {ROOF_SLIDING_PSF:g} psf average sliding snow "
                           f"(house roof W ≈ 14' assumed — measure); net pressure coefficients {ROOF_CN_DOWN:g} down / {ROOF_CN_UP:g} up with the louvers closed; half the roof to the house.")
    return review, assumptions


def _footing_review(k) -> List[str]:
    kinds = {col.get("ftype") for col in k.cols if col.get("on_footing")}
    out = []
    if "diamond_pier" in kinds:
        out.append("Diamond Pier uplift and lateral values are Pin Foundations' tested chart values (ESR-1895 §5.6 does not evaluate them): accept or replace. "
                   "Get PFI's written OK for a job over 600 SF.")
    if kinds & {"caisson", "existing", "concrete"}:
        out.append(f"Caissons: capacity = end bearing at the presumptive {k.c.soil_psf:,.0f} psf + the engine's ≈{CAISSON_SKIN_PSF:g} psf skin-friction estimate — confirm the soil "
                   "(Buick loam, CL/ML; a soils report if Centennial's R401.2 amendment applies), size the shafts and their reinforcing, and the cast-in anchors. "
                   "Centennial R109.1.1: the footing inspection is by a Colorado PE.")
    return out


def _stair_review(k) -> List[str]:
    """The stringer rows left to the engineer (REVIEW): a flight past DCA6's 6'-0" whose NDS rows pass, a throat within 1/8" of 5"."""
    out = []
    groups: Dict[Tuple[str, str, str], List[Tuple[str, str]]] = {}
    for ck in k.checks:              # one line per stair and finding: the flights with the same throat share it
        if ck.result == "REVIEW" and ck.note and ck.what.startswith(("Span between supports (DCA6", "Throat (5")):
            what = f"horizontal span {_ftin(ck.demand)}" if ck.what.startswith("Span") else f"throat {ck.capacity:.2f}\""
            m = re.search(r"flight (\d+)", ck.member)
            groups.setdefault((ck.member.split(":")[0], what, ck.note), []).append((ck.id, m.group(1) if m else ""))
    for (label, what, note), rows in groups.items():
        fl = [f for _, f in rows if f]
        where = f", flight{'s' if len(fl) > 1 else ''} {' and '.join(fl)}" if fl else ""
        out.append(f"{' / '.join(i for i, _ in rows)} — {label}{where}: {what}; {note}.")
    for ck in k.checks:              # the stair's own caissons carry the deck's post and base
        if ck.id.startswith("K-BASE") and ck.id.endswith("-ST") and ck.note:
            out.append(f"{ck.member}: {ck.what.replace('Post base ', '')} — {ck.note}.")
    return out


def _sources(k) -> List[str]:
    kinds = {col.get("ftype") for col in k.cols if col.get("on_footing")}
    out = list(SOURCES)
    if "diamond_pier" not in kinds:
        out = [x for x in out if "Diamond Pier" not in x]
    if kinds & {"caisson", "existing", "concrete"}:
        out.insert(4, "IBC 2021 1806.2 / 1807.3.2.1 (lateral bearing, embedded poles) for the caissons' lateral check; ACI 318 / ACI 332 for the concrete")
    return out


def _base_review(k) -> str:
    ck = next((x for x in k.checks if x.id.startswith("K-BASE")), None)
    if ck is None:
        return "Post bases: confirm the base under every column for the down / uplift / lateral values on the Caps & bases sheet."
    if "no catalog part" in ck.what:
        return ("The column base on the Diamond Pier has no catalog part: detail an HDG standoff base on the single pier bolt (or a tenoned foot in an ABU66Z / ABW66RZ) "
                "for the down / uplift / lateral values on the Caps & bases sheet.")
    on_dp = "diamond pier" in ck.member.lower()
    if on_dp and ("ABU88" in ck.what or "APB88" in ck.what):
        return (f"{ck.what.replace('Post base ', '')} on the Diamond Pier: the base's second 5/8\" anchor is drilled into the pier head beside the cast-in bolt (owner's choice) — "
                "not a catalog condition (5-5/8\" plinth edge distance, the head's concrete limit): Pin Foundations and the engineer confirm, or detail a single-bolt HDG standoff base.")
    if not on_dp:
        return (f"{ck.what.replace('Post base ', '')} bases with their 5/8\" anchors cast in the footing (catalog condition, 1\" standoff keeps the Douglas fir off the concrete): "
                "the engineer confirms the anchor embedment and edge distance in the shaft.")
    return f"{ck.what}: confirm it on the pier for the down / uplift / lateral values on the Caps & bases sheet."


SOURCES = [
    "2021 International Residential Code: R301.5, R301.7, R311.7, R312, R317, R507 (decks)",
    "City of Centennial Ordinance 2023-O-06 (Sec. 18-2-30: Table R301.2(1) — 30 psf snow, 115 mph, SDC B, 36\" frost; R109.1.1 PE pier inspection)",
    "ASCE 7-16 Minimum Design Loads: 2.4.1, Ch. 7, 11-12, 26-27, 29-30",
    "AWC NDS 2018 and NDS Supplement (Tables 4A, 4B, 4D, 12.3.1A); AWC DCA6 Prescriptive Residential Wood Deck Construction Guide",
    "ICC-ES ESR-1895 Diamond Pier (Dec 2025) and Pin Foundations Residential Load Chart DOC0008",
    "ICC-ES ESR-4217 TimberTech Impression Rail Express; ICC-ES ESR-1078 FastenMaster LedgerLOK",
    "Simpson Strong-Tie catalog C-C-2026 (CCQ / ECCQ caps, ABU / ABW bases, hangers, ties, straps)",
    "Job research: materials.md §4, structure.md, footings/footings.md, louvered/research.md (Fillmore working notes)",
]

METHOD = [
    "Members: NDS 2018 ASD — F' = F x CD x CM x Ct x CF x Ci x Cr x CL (Ct, Ci 1.0); bending fb = M/S, shear fv = 1.5V/A, bearing, column Cp (NDS 3.7.1, c 0.8, Emin'), combined NDS 3.9.2.",
    "Analysis: each member is an Euler-Bernoulli beam on point supports solved by finite elements at every support and load boundary (exact for these loads); reactions, moments and shears by statics.",
    "Load combinations: ASCE 7-16 2.4.1 ASD with the NDS load-duration factor of the shortest load in each (D 0.9, L 1.0, S 1.15, W/E 1.6); the governing combination is named on each row.",
    "Deflection: live L/360 (spans) and 2a/360 (overhangs), total Kcr·Δ_D + Δ_L ≤ L/240 with Kcr 2.0 for wet service; cantilever 220 lb point at 2a/180.",
    "Ratio = demand / capacity; PASS ≤ 1.00. REVIEW = the engineer of record decides (a non-catalog part, a prescriptive limit exceeded but checked, or a value to confirm). INFO = an input.",
]


def run_calcs(spec, scope: str = "Base", exposure: Optional[str] = None) -> Package:
    """Every check for one spec."""
    k = _analyze(spec, scope, exposure)
    return _package(k, [scope])


def _package(k: _CalcMore, scopes: List[str]) -> Package:
    spec = k.spec
    s = spec.site
    review, assumptions = _review_and_assumptions(k)
    cols = []
    for col in k.cols:
        cols.append(dict(id=col["id"], part=col["part_name"], kind=col["kind"], label=col["label"], gx=None if col["gx"] != col["gx"] else round(col["gx"], 2),
                         gy=None if col["gy"] != col["gy"] else round(col["gy"], 2), height_in=round(col["height"], 1), size=col.get("size"),
                         D=round(col["comp"].get("D", [0, 0])[0]), L=round(col["comp"].get("L", [0, 0])[0]), S=round(col["comp"].get("S", [0, 0])[0]),
                         W=[round(v) for v in col["comp"].get("W", [0, 0])], P=round(col.get("down", 0)), combo=col.get("P_combo", ""), uplift=round(col.get("up", 0)),
                         Vb=round(col.get("Vb", 0.0)), model=col.get("model", ""), need=col.get("need", ""), on_footing=col.get("on_footing", False),
                         fcap=round(col.get("fcap", 0.0)), ftype=col.get("ftype", "")))
    return Package(job=spec.job, address=", ".join(x for x in (s.address, s.city, f"{s.state} {s.zip}".strip()) if x), client=spec.client,
                   prepared=date.today().strftime("%B %d, %Y"), criteria=k.c, criteria_rows=_criteria_rows(spec, k.c), load_rows=_load_rows(k),
                   material_rows=_material_rows(k), checks=k.checks, columns=cols, assumptions=assumptions, review=review, sources=_sources(k),
                   scopes=scopes, method=list(METHOD))


def calc_package(base_spec, options: Sequence[Tuple[str, object]] = (), exposure: Optional[str] = None) -> Package:
    """The base deck's checks, then for each option (label, spec) the checks it adds or changes (a new member — the yard stair,
    the roof's load path — or one whose result, demand or capacity differs by more than 1% from every earlier scope's row),
    labeled with the option."""
    kb = _analyze(base_spec, "Base", exposure)
    pkg = _package(kb, ["Base"])

    def same(ck, b):            # the same member and result, demand and capacity within 1%
        return (b.member == ck.member and ck.result == b.result and abs(ck.demand - b.demand) <= 0.01 * max(1.0, abs(b.demand))
                and abs(ck.capacity - b.capacity) <= 0.01 * max(1.0, abs(b.capacity)))
    seen: Dict[str, List[Check]] = {}
    for ck in kb.checks:
        seen.setdefault(ck.id, []).append(ck)
    for label, spec in options:
        ko = _analyze(spec, label, exposure)
        added = 0
        for ck in ko.checks:
            # every earlier scope counts: two exclusive layouts of one stair (Options 2 / 2B) each show their own rows
            if not any(same(ck, b) for b in seen.get(ck.id, [])):
                ck.scope = label
                pkg.checks.append(ck)
                seen.setdefault(ck.id, []).append(ck)
                added += 1
        if not added:
            pkg.assumptions.append(f"{label}: analyzed — no check differs from the base or the options above (member, result, demand and capacity within 1%).")
        for col in _package(ko, [label]).columns:
            if not any(c_["id"] == col["id"] and c_.get("label") == col.get("label") and c_.get("model") == col.get("model")
                       and abs(col["P"] - c_["P"]) <= 0.01 * max(1, c_["P"]) for c_ in pkg.columns):    # against every earlier scope's row, like the checks
                pkg.columns.append(dict(col, scope=label))
        r2, a2 = _review_and_assumptions(ko)
        for x in r2:
            if x not in pkg.review and not x.split(" ")[0].isdigit():
                pkg.review.append(x)
        for x in a2:
            if x not in pkg.assumptions:
                pkg.assumptions.append(x)
        pkg.load_rows += [r for r in _load_rows(ko) if r not in pkg.load_rows]
        pkg.scopes.append(label)
    # the FAIL summary covers every scope
    pkg.review = [x for x in pkg.review if "FAIL as the layout stands" not in x]
    fails = [ck for ck in pkg.checks if ck.result == "FAIL"]
    if fails:
        pkg.review.insert(0, f"{len(fails)} check{'s' if len(fails) != 1 else ''} FAIL as the layout stands: " + "; ".join(f"{ck.id} {ck.what} [{ck.scope}]" for ck in fails[:10])
                          + (" …" if len(fails) > 10 else "") + " — resolve before the set is stamped.")
    return pkg


# ================================================================== sheets (the drawing set's frame: 1000 x 700, black band, gold number, cream ground)
INK, GOLD, CREAM, MUTE, LINE_C = "#111111", "#d49e1b", "#f7f2e8", "#6b665e", "#d9d2c3"
RES_COLOR = {"PASS": "#2f6b3a", "FAIL": "#b3261e", "REVIEW": "#9a6a00", "INFO": "#6b665e"}
SW, SH = 1000, 700
BODY_H = SH - 52 - 36
CALC_SHEET_PREFIX = "S-9"


def _esc(t) -> str:
    return _html.escape(str(t), quote=True)


def _t(x, y, s, size=9.0, w=400, anchor="start", fill=INK, italic=False) -> str:
    st = ' font-style="italic"' if italic else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{w}" text-anchor="{anchor}" fill="{fill}"{st}>{_esc(s)}</text>'


def _r(x, y, w, h, fill, stroke="none", sw=0.8, rx=0) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{max(h, 0):.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _ln(x0, y0, x1, y1, stroke=INK, sw=0.6) -> str:
    return f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{stroke}" stroke-width="{sw}"/>'


def _wrap(s: str, width_px: float, size: float) -> List[str]:
    n = max(10, int(width_px / (0.53 * size)))
    return textwrap.wrap(str(s), n) or [""]


def _sheet_svg(num: str, title: str, sub: str, body: List[str], meta: dict) -> str:
    hdr = [_r(0, 0, SW, 46, INK), _t(18, 30, num, 22, 900, fill=GOLD), _t(110, 22, title.upper(), 15, 900, fill="#f3ead9"),
           _t(110, 39, textwrap.shorten(sub, 120, placeholder="…"), 9.5, 400, fill="#d8cfbf"),
           _t(SW - 18, 20, textwrap.shorten(meta["job_line"], 70, placeholder="…"), 9.5, 700, "end", "#d8cfbf"),
           _t(SW - 18, 36, meta["rev_line"], 8.5, 400, "end", "#b8b0a2")]
    ftr = [_ln(0, SH - 34, SW, SH - 34, GOLD, 2), _t(18, SH - 14, meta.get("scale", "Calculations — no scale"), 9.5, 600, fill=MUTE),
           _t(SW - 18, SH - 14, meta["footer"], 8.6, 400, "end", MUTE)]
    cid = f"clip{num.replace('-', '').replace('.', '')}"
    return (f'<svg viewBox="0 0 {SW} {SH}" xmlns="http://www.w3.org/2000/svg" font-family="Nunito Sans, -apple-system, Helvetica, Arial, sans-serif">'
            f'<rect width="{SW}" height="{SH}" fill="{CREAM}"/><defs><clipPath id="{cid}"><rect x="0" y="0" width="{SW}" height="{BODY_H}"/></clipPath></defs>'
            + "".join(hdr) + f'<g transform="translate(0,52)" clip-path="url(#{cid})">' + "".join(body) + "</g>" + "".join(ftr) + "</svg>")


def _meta(pkg: Package, standalone: bool = False) -> dict:
    return dict(job_line=f"{pkg.job} · {pkg.address}".strip(" ·"),
                rev_line=f"GS Exterior Experts · {pkg.prepared} · Rev 0" + (" · CALCULATIONS FOR REVIEW" if standalone else ""),
                footer="Structural calculations for review and seal by a Colorado-licensed professional engineer. The sealed set governs. Field verify.")


def _num(v: float, unit: str) -> str:
    if unit == "-":
        return f"{v:.2f}"
    return _f(v, unit)


def _check_rows(checks: List[Check]) -> List[Tuple[str, object]]:
    """Flatten into ("member", text) / ("check", Check) rows: a member line, then its checks."""
    rows: List[Tuple[str, object]] = []
    last = None
    for ck in checks:
        head = ck.member + (f"  [{ck.scope}]" if ck.scope and ck.scope != "Base" else "")
        if head != last:
            rows.append(("member", head))
            last = head
        rows.append(("check", ck))
    return rows


def _row_height(kind: str, obj) -> float:
    if kind == "member":
        return 15.0 * len(_wrap(obj, 950, 8.8))
    ck = obj
    basis = ck.basis + (f"  Note: {ck.note}" if ck.note else "")
    return 12.5 + 9.2 * min(3, len(_wrap(basis, 884, 7.3))) + 3.0


def _table_header(y: float) -> List[str]:
    o = [_r(14, y - 11, SW - 28, 15, "#ece3d1")]
    for x, s, a in ((18, "ID", "start"), (98, "CHECK", "start"), (382, "DEMAND", "end"), (472, "CAPACITY", "end"), (516, "RATIO", "end"),
                    (530, "RESULT", "start"), (590, "CODE / SOURCE", "start")):
        o.append(_t(x, y, s, 7.6, 800, a, MUTE))
    return o


def _render_rows(rows: List[Tuple[str, object]], y0: float) -> List[str]:
    o = _table_header(y0)
    y = y0 + 15
    for kind, obj in rows:
        if kind == "member":
            for ln in _wrap(obj, 950, 8.8):
                o.append(_t(18, y + 9, ln, 8.8, 800, fill=INK))
                y += 15
            o.append(_ln(18, y - 3, SW - 18, y - 3, LINE_C, 0.6))
            continue
        ck: Check = obj
        res = ck.result
        col = RES_COLOR.get(res, MUTE)
        y += 9
        o.append(_t(18, y, ck.id, 7.8, 700, fill=MUTE))
        o.append(_t(98, y, textwrap.shorten(ck.what, 58, placeholder="…"), 8.4, 700))
        cap_txt = "—" if (not ck.capacity and res in ("REVIEW", "INFO")) else _num(ck.capacity, ck.unit)
        rat_txt = "—" if (not ck.capacity and res in ("REVIEW", "INFO")) else f"{ck.ratio:.2f}"
        o.append(_t(382, y, _num(ck.demand, ck.unit), 8.4, 600, "end"))
        o.append(_t(472, y, cap_txt, 8.4, 600, "end"))
        o.append(_t(516, y, rat_txt, 8.4, 800, "end", col))
        o.append(_r(530, y - 8.5, 48, 11, col, rx=2))
        o.append(_t(554, y, res, 7.2, 800, "middle", "#ffffff"))
        o.append(_t(590, y, textwrap.shorten(ck.code, 80, placeholder="…"), 7.6, 400, fill=MUTE))
        basis = ck.basis + (f"  Note: {ck.note}" if ck.note else "")
        lines = _wrap(basis, 884, 7.3)
        if len(lines) > 3:
            lines = lines[:3]
            lines[-1] = textwrap.shorten(lines[-1] + " …", 200, placeholder="…")
        for ln in lines:
            y += 9.2
            o.append(_t(98, y, ln, 7.3, 400, fill="#3d3a35"))
        y += 6.0
    return o


def calc_sheets(pkg_or_spec, meta: Optional[dict] = None, standalone: bool = False) -> List[Tuple[str, str, str]]:
    """[(num, title, svg)] — the calculation sheets in the drawing set's frame (S-901 ...). Accepts a Package or a DeckSpec
    (calculated on the spot). This is the permit-set hook: append these after the drawing sheets."""
    pkg = pkg_or_spec if isinstance(pkg_or_spec, Package) else run_calcs(pkg_or_spec)
    meta = meta or _meta(pkg, standalone)
    sheets: List[Tuple[str, str, List[str], str]] = []      # (title, sub, body, kind)
    # ---------------- S-901: basis
    o: List[str] = []
    o.append(_t(24, 22, "PROJECT", 9, 800, fill=GOLD))
    y = 38
    for ln in [pkg.job[:110], pkg.address, f"Prepared for {pkg.client}" if pkg.client else "", f"Prepared {pkg.prepared} · scope: " + " · ".join(pkg.scopes)]:
        if ln:
            for w in _wrap(ln, 540, 9.5)[:2]:
                o.append(_t(24, y, w, 9.5, 600)); y += 13
    y += 8
    o.append(_t(24, y, "DESIGN CRITERIA", 9, 800, fill=GOLD)); y += 15
    for k_, v, src in pkg.criteria_rows:
        ws = _wrap(v, 335, 7.8)
        o.append(_t(24, y, k_, 7.8, 800))
        for i, w in enumerate(ws[:3]):
            o.append(_t(128, y + i * 10, w, 7.8, 400))
        for i, w in enumerate(_wrap(src, 86, 6.8)[:2]):
            o.append(_t(566, y + i * 8.5, w, 6.8, 400, "end", MUTE))
        y += 10 * min(3, max(len(ws), 1 + (len(_wrap(src, 86, 6.8)) > 1))) + 3
    y += 6
    o.append(_t(24, y, "MATERIALS (NDS 2018 reference values, psi; adjusted for wet service)", 9, 800, fill=GOLD)); y += 14
    for nm, v, src in pkg.material_rows:
        o.append(_t(24, y, nm, 7.8, 800)); y += 10
        for w in _wrap(v + " · " + src, 530, 7.4)[:2]:
            o.append(_t(32, y, w, 7.4, 400)); y += 9.5
        y += 2
    x2 = 600
    yy = 22
    o.append(_t(x2, yy, "METHOD", 9, 800, fill=GOLD)); yy += 15
    for m in pkg.method:
        for i, w in enumerate(_wrap(m, 370, 7.6)):
            o.append(_t(x2 + (10 if i else 0), yy, ("• " if i == 0 else "") + w, 7.6, 400)); yy += 10
        yy += 3
    yy += 6
    o.append(_t(x2, yy, "RESULTS", 9, 800, fill=GOLD)); yy += 16
    cnt = pkg.counts()
    bx = x2
    for res in ("PASS", "FAIL", "REVIEW", "INFO"):
        n = cnt.get(res, 0)
        o.append(_r(bx, yy - 11, 86, 30, RES_COLOR[res], rx=3))
        o.append(_t(bx + 43, yy + 4, f"{n}", 15, 900, "middle", "#ffffff"))
        o.append(_t(bx + 43, yy + 15, res, 7, 800, "middle", "#ffffff"))
        bx += 92
    yy += 34
    o.append(_t(x2, yy, "SHEETS", 9, 800, fill=GOLD)); yy += 14
    idx_y = yy
    # (index filled after the sheets are laid out)
    seal_y = BODY_H - 150
    o.append(_r(x2, seal_y, 372, 138, "#fffdf8", INK, 0.8))
    o.append(_t(x2 + 10, seal_y + 16, "ENGINEER OF RECORD — SEAL, SIGNATURE, DATE", 8, 800, fill=MUTE))
    o.append(_t(x2 + 10, seal_y + 128, "Colorado PE · reviewed for the loads and criteria on this sheet", 7.2, 400, fill=MUTE))
    sheets.append(("Structural calculations — basis", "Codes, design criteria, materials, method and the result count — the calculation set's cover", o, "basis"))
    # ---------------- S-902: columns, reactions, footings
    rows = [c_ for c_ in pkg.columns]
    hdrs = [("COLUMN", 18, "start"), ("WHERE", 92, "start"), ("x, y (ft)", 300, "start"), ("HEIGHT", 392, "end"), ("D", 440, "end"), ("L", 485, "end"),
            ("S", 528, "end"), ("W ↓/↑", 590, "end"), ("P ASD", 646, "end"), ("UPLIFT", 696, "end"), ("BASE V", 744, "end"), ("FOOTING", 760, "start"),
            ("CAPACITY", 868, "end"), ("SCOPE", 904, "start")]
    chunks = [rows[i:i + 36] for i in range(0, len(rows), 36)] or [[]]
    for ci, chunk in enumerate(chunks):
        o = [_t(24, 20, "COLUMN LOADS AND FOOTINGS (lb; components at the column top, P = governing ASD combination incl. column and base weight)", 9, 800, fill=GOLD)]
        o.append(_r(14, 30, SW - 28, 15, "#ece3d1"))
        for h, x, a in hdrs:
            o.append(_t(x, 41, h, 7.4, 800, a, MUTE))
        y = 58
        for r in chunk:
            where = f"{r['part']} · {r['label']}"
            xy = "—" if r["gx"] is None else f"{r['gx']:.2f}, {r['gy']:.2f}"
            over = bool(r.get("fcap")) and r["P"] > r["fcap"]
            vals = [(r["id"], 18, "start", 700, INK), (textwrap.shorten(where, 44, placeholder="…"), 92, "start", 400, INK), (xy, 300, "start", 400, INK),
                    (_ftin(r["height_in"]), 392, "end", 400, INK), (f"{r['D']:,}", 440, "end", 400, INK), (f"{r['L']:,}", 485, "end", 400, INK),
                    (f"{r['S']:,}" if r["S"] else "—", 528, "end", 400, INK), (f"{r['W'][0]:,}/{r['W'][1]:,}" if any(r["W"]) else "—", 590, "end", 400, INK),
                    (f"{r['P']:,}", 646, "end", 800, RES_COLOR["FAIL"] if over else INK), (f"{r['uplift']:,}" if r["uplift"] else "—", 696, "end", 400, INK),
                    (f"{r['Vb']:,}" if r["Vb"] else "—", 744, "end", 400, INK), (textwrap.shorten(r.get("model") or "—", 20, placeholder="…"), 760, "start", 600, INK),
                    (f"{r['fcap']:,}" if r.get("fcap") else "—", 868, "end", 600, RES_COLOR["FAIL"] if over else INK), (textwrap.shorten(r.get("scope", "Base"), 16, placeholder="…"), 904, "start", 400, MUTE)]
            for s_, x, a, w, f in vals:
                o.append(_t(x, y, s_, 7.8, w, a, f))
            o.append(_ln(14, y + 4, SW - 14, y + 4, LINE_C, 0.4))
            y += 14.5
        y += 10
        if ci == len(chunks) - 1:
            kinds = {r.get("ftype") for r in rows}
            if "diamond_pier" in kinds:
                o.append(_t(24, y, "Piers: " + PIER_SRC + ". Capacities by soil (catalog.pier_capacity_lb); uplift and lateral are tested chart values, not ESR-evaluated (ESR-1895 §5.6).", 7.6, 400, fill=MUTE)); y += 11
            if kinds & {"caisson", "existing", "concrete"}:
                o.append(_t(24, y, f"Caissons: end bearing at the presumptive {pkg.criteria.soil_psf:,.0f} psf (IRC Table R401.4.1) + the engine's ≈{CAISSON_SKIN_PSF:g} psf skin-friction estimate; "
                                   "uplift by the shaft's weight; lateral by IBC 1807.3.2.1 — the engineer sizes the shafts.", 7.6, 400, fill=MUTE))
        sheets.append(("Column loads and footings" + (f" ({ci + 1}/{len(chunks)})" if len(chunks) > 1 else ""),
                       "Every column: load components, the governing ASD load, uplift, base shear, its footing and the footing's capacity", o, "cols"))
    # ---------------- check sheets, by group
    for g in GROUPS:
        cks = [ck for ck in pkg.checks if ck.group == g]
        if not cks:
            continue
        rows = _check_rows(cks)
        page: List[Tuple[str, object]] = []
        hgt = 20.0
        pages = []
        for i_, (kind, obj) in enumerate(rows):
            h = _row_height(kind, obj)
            nxt = _row_height(*rows[i_ + 1]) if (kind == "member" and i_ + 1 < len(rows)) else 0.0     # a member line keeps its first check
            if hgt + h + nxt > BODY_H - 14 and page:
                pages.append(page); page = []; hgt = 20.0
                if kind == "check":           # repeat the member line on a new sheet
                    prev = next((o_ for k_, o_ in reversed(rows[:i_]) if k_ == "member"), None)
                    if prev:
                        page.append(("member", prev + " (cont.)")); hgt += _row_height("member", prev)
            page.append((kind, obj)); hgt += h
        if page:
            pages.append(page)
        sub = {"Joists & cantilevers": "2x10 joists: bending, shear, deflection L/360, cantilevers (L/4, 220 lb at the end) — NDS 2018, IRC R507.6",
               "Ledger & hangers": "Joist hangers and LedgerLOK at every ledger — IRC R507.9, ESR-1078",
               "Beams": "6x10 DF-L No.1 drop beams, continuous pieces on their posts, live load patterned — NDS 2018 (outside IRC R507.5)",
               "Columns": "8x8 DF-L No.1 columns: axial + buckling at their heights — NDS 2018 3.7, IRC R507.4",
               "Caps & bases": "Column caps (CCQ / ECCQ) and post bases — Simpson C-C-2026",
               "Footings": ("Caissons: bearing (end + skin friction), uplift, lateral embedment, frost — IRC R403 / R507.3, IBC 1807.3"
                            if not any(r.get("ftype") == "diamond_pier" for r in pkg.columns) else
                            "Diamond Piers: bearing by soil, uplift, lateral, frost, spacing — ESR-1895, Pin Foundations chart"),
               "Lateral system": "House attachment (R507.9.2 hold-downs, ledger), deck diaphragm, knee braces at the end columns",
               "Inset stair & notch": "Stringers, notch headers and trimmer, the stair base ledger and the lower rim",
               "Stairs to the yard": "Option: stringers, landing joists and rims, the stair on the deck rim (its posts: Columns, Caps & bases, Footings)",
               "Louvered roof load path": "Option: roof post reactions to the deck — gravity, uplift chain, base moment",
               "Guards": "Guard posts and their blocking — IRC Table R301.5, ESR-4217"}.get(g, "")
        for pi, pg in enumerate(pages):
            body = _render_rows(pg, 10)
            sheets.append((g + (f" ({pi + 1}/{len(pages)})" if len(pages) > 1 else ""), sub, body, "checks"))
    # ---------------- review / assumptions / sources
    o = [_t(24, 20, "FOR THE ENGINEER OF RECORD", 9, 800, fill=GOLD)]
    y = 36
    for i, r in enumerate(pkg.review):
        ws = _wrap(r, 920, 8.0)
        o.append(_t(24, y, f"{i + 1}.", 8.0, 800, fill=GOLD))
        for w in ws:
            o.append(_t(42, y, w, 8.0, 400)); y += 10.5
        y += 3
    y += 8
    o.append(_t(24, y, "ASSUMPTIONS", 9, 800, fill=GOLD)); y += 15
    for a in pkg.assumptions:
        for i, w in enumerate(_wrap(a, 920, 7.8)):
            o.append(_t(24 + (12 if i else 0), y, ("• " if i == 0 else "") + w, 7.8, 400)); y += 10
        y += 2
    y += 8
    o.append(_t(24, y, "SOURCES", 9, 800, fill=GOLD)); y += 15
    for s_ in pkg.sources:
        for i, w in enumerate(_wrap(s_, 920, 7.6)):
            o.append(_t(24 + (12 if i else 0), y, ("• " if i == 0 else "") + w, 7.6, 400, fill="#3d3a35")); y += 9.8
    sheets.append(("Review items, assumptions, sources", "What the engineer of record decides, what this calculation assumes, and where the values come from", o, "review"))
    # number them and fill the index on the cover
    out = []
    nums = [f"{CALC_SHEET_PREFIX}{i + 1:02d}" for i in range(len(sheets))]
    idx = []
    per_col = int(math.ceil(len(sheets) / 2.0))
    step = min(10.6, (BODY_H - 162 - idx_y) / max(1, per_col))
    for i, ((title, sub, body, kind), num) in enumerate(zip(sheets, nums)):
        cx = x2 + (0 if i < per_col else 188)
        yy = idx_y + (i % per_col) * step
        idx.append(_t(cx, yy, num, 7.4, 800, fill=GOLD)); idx.append(_t(cx + 40, yy, textwrap.shorten(title, 34, placeholder="…"), 7.4, 500))
    sheets[0][2].extend(idx)
    for (title, sub, body, kind), num in zip(sheets, nums):
        out.append((num, title, _sheet_svg(num, title, sub, body, meta)))
    return out


PIER_CAP_CACHE: Dict[Tuple[str, float], float] = {}


def _pier_cap(model: str, soil: float) -> float:
    from .catalog import pier_capacity_lb
    k = (model, soil)
    if k not in PIER_CAP_CACHE:
        PIER_CAP_CACHE[k] = pier_capacity_lb(model, soil)
    return PIER_CAP_CACHE[k]


PAGE_CSS = """<style>
:root { --ink:#141414; --ink-3:#8a8172; --ground:#fbf9f4; --paper:#ffffff; --line:#d9d2c3; --gold:#d49e1b; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --ink:#f2ede2; --ink-3:#9a9182; --ground:#121110; --paper:#1b1916; --line:#3a352d; --gold:#e0ac2a; } }
:root[data-theme="dark"] { --ink:#f2ede2; --ink-3:#9a9182; --ground:#121110; --paper:#1b1916; --line:#3a352d; --gold:#e0ac2a; }
* { box-sizing:border-box; }
body { margin:0; background:var(--ground); color:var(--ink); font-family:"Nunito Sans", "Segoe UI", system-ui, sans-serif; font-size:15px; line-height:1.5; }
.band { background:#000; color:#fff; padding:22px 20px 24px; }
.band .in { max-width:1100px; margin:0 auto; }
.band .kick { color:#d49e1b; font-weight:800; font-size:12px; letter-spacing:.14em; text-transform:uppercase; }
.band h1 { margin:6px 0 4px; font-size:clamp(24px, 4.5vw, 36px); font-weight:900; line-height:1.08; }
.band p { margin:0; color:#ecddb6; font-weight:300; }
.wrap { max-width:1100px; margin:0 auto; padding:16px 16px 60px; }
.index { columns:2; column-gap:28px; font-size:14px; padding-left:18px; }
.counts { display:flex; gap:10px; flex-wrap:wrap; margin:10px 0 18px; }
.counts span { padding:4px 10px; border-radius:4px; color:#fff; font-weight:800; font-size:13px; }
.sheet-page { margin:0 0 26px; }
.sheet-page h3 { font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-3); margin:0 0 6px; }
.sheet-page svg { width:100%; height:auto; display:block; border:1px solid var(--line); background:#fff; }
footer { color:var(--ink-3); font-size:12px; margin-top:20px; }
@media (max-width: 640px) { .index { columns:1; } }
@media print { @page { size: Letter landscape; margin: 0.3in; } body { background:#fff; color:#000; } .band, .intro, footer { display:none; }
  .sheet-page { break-after: page; page-break-after: always; margin:0; } .sheet-page h3 { display:none; } .sheet-page svg { border:0; max-height:7.6in; } }
</style>"""


def render_html(pkg: Package, out_dir: str, pdf: bool = True, name: str = "calcs") -> dict:
    """calcs.html (one sheet per Letter-landscape page when printed), calcs.json, and calcs.pdf with Chromium when asked."""
    out = Path(out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    sheets = calc_sheets(pkg, standalone=True)
    cnt = pkg.counts()
    title = f"{pkg.address.split(',')[0] if pkg.address else pkg.job} — structural calculations"
    head = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Structural Calculations</title>"
            f"<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,300;6..12,400;6..12,600;6..12,700;6..12,800;6..12,900&display=swap'>"
            f"{PAGE_CSS}</head><body>")
    band = (f"<header class='band'><div class='in'><div class='kick'>GS Exterior Experts · Deck Division · structural calculations</div>"
            f"<h1>{_esc(title)}</h1><p>{_esc(pkg.address)} · {_esc(pkg.prepared)} · {' · '.join(_esc(s) for s in pkg.scopes)}</p></div></header>")
    intro = ("<section class='intro'><div class='counts'>" + "".join(f"<span style='background:{RES_COLOR[r]}'>{cnt.get(r, 0)} {r}</span>" for r in ("PASS", "FAIL", "REVIEW", "INFO"))
             + "</div><ol class='index'>" + "".join(f"<li><b>{n}</b> {_esc(t)}</li>" for n, t, _ in sheets) + "</ol></section>")
    body = "".join(f"<div class='sheet-page' id='{n}'><h3>{n} · {_esc(t)}</h3>{svg}</div>" for n, t, svg in sheets)
    page = head + band + "<main class='wrap'>" + intro + body + ("<footer>Structural calculations for review and seal by a Colorado-licensed professional engineer. "
                                                                 "Generated by decktakeoff.calcs from the job's spec and layout.</footer></main></body></html>\n")
    (out / f"{name}.html").write_text(page)
    (out / f"{name}.json").write_text(json.dumps(pkg.to_dict(), indent=1, default=str))
    res = dict(html=str(out / f"{name}.html"), json=str(out / f"{name}.json"), sheets=len(sheets), counts=cnt)
    if pdf:
        try:
            from .render import _chromium
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                b = pw.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
                pg = b.new_page(viewport={"width": 1400, "height": 1000})
                pg.goto("file://" + str(out / f"{name}.html")); pg.wait_for_timeout(1500)
                pg.emulate_media(media="print")
                pg.pdf(path=str(out / f"{name}.pdf"), format="Letter", landscape=True, print_background=True, prefer_css_page_size=True)
                b.close()
            res["pdf"] = str(out / f"{name}.pdf")
        except Exception as e:      # no Chromium here: the HTML still prints from a browser
            res["pdf_error"] = str(e)
    return res


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    from .spec import DeckSpec
    ap = argparse.ArgumentParser(prog="python -m decktakeoff.calcs", description="Structural calculation package for a deck spec")
    ap.add_argument("spec", help="base spec JSON")
    ap.add_argument("--option", action="append", default=[], help='"Label=path.json": an option spec whose added / changed checks join the package')
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--exposure", choices=["B", "C", "D"], default=None)
    a = ap.parse_args(argv)
    base = DeckSpec.from_dict(json.load(open(a.spec)))
    opts = []
    for o in a.option:
        label, path = o.rsplit("=", 1)
        opts.append((label, DeckSpec.from_dict(json.load(open(path)))))
    pkg = calc_package(base, opts, exposure=a.exposure)
    r = render_html(pkg, a.out, pdf=a.pdf)
    print(json.dumps({k: v for k, v in r.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
