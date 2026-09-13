"""Length parsing and formatting. Everything inside the engine is inches (float)."""
from __future__ import annotations

import math
import re
from fractions import Fraction

_FT_IN = re.compile(
    r"""^\s*(?P<neg>-)?\s*
        (?:(?P<ft>\d+(?:\.\d+)?)\s*(?:'|ft|feet|foot)\s*-?\s*)?
        (?:(?P<in>\d+(?:\.\d+)?)?\s*(?:\s+(?P<num>\d+)\s*/\s*(?P<den>\d+))?\s*(?:"|''|in|inch|inches)?)?\s*$""",
    re.X | re.I,
)


def to_inches(value, default_unit: str = "ft") -> float:
    """Accepts 187.5, "15'-7 1/2\"", "15' 7.5\"", "187.5in", "15.625ft", "12x16" is NOT accepted here.
    Bare numbers are interpreted in `default_unit` ("ft" or "in")."""
    if value is None:
        raise ValueError("length is required")
    if isinstance(value, (int, float)):
        return float(value) * (12.0 if default_unit == "ft" else 1.0)
    s = str(value).strip().replace("’", "'").replace("”", '"').replace("″", '"').replace("′", "'")
    if not s:
        raise ValueError("empty length")
    # bare number with no unit -> default unit
    if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return float(s) * (12.0 if default_unit == "ft" else 1.0)
    m = _FT_IN.match(s)
    if not m or (m.group("ft") is None and m.group("in") is None and m.group("num") is None):
        raise ValueError(f"cannot parse length: {value!r}")
    ft = float(m.group("ft") or 0)
    inch = float(m.group("in") or 0)
    if m.group("num"):
        inch += float(Fraction(int(m.group("num")), int(m.group("den"))))
    # "12in" style: the regex puts 12 into <in> only when a unit or feet marker exists; a bare "12" was handled above
    if m.group("ft") is None and m.group("in") is not None and not re.search(r'("|in)', s, re.I):
        # e.g. "7 1/2" -> inches
        pass
    total = ft * 12 + inch
    return -total if m.group("neg") else total


def ftin(inches: float, frac: bool = True) -> str:
    """inches -> 15'-7 1/2\" (nearest 1/16)."""
    sign = "-" if inches < 0 else ""
    inches = abs(inches)
    ft = int(inches // 12)
    rem = inches - ft * 12
    whole = int(math.floor(rem + 1e-9))
    f = rem - whole
    fr = ""
    if frac:
        num = round(f * 16)
        if num == 16:
            whole += 1
            num = 0
        if whole == 12:
            ft += 1
            whole = 0
        if num:
            q = Fraction(num, 16)
            fr = f" {q.numerator}/{q.denominator}"
    else:
        whole = int(round(rem))
        if whole == 12:
            ft += 1
            whole = 0
    if ft == 0:
        if whole == 0 and fr:
            return f'{sign}{fr.strip()}"'
        return f'{sign}{whole}{fr}"'
    return f"{sign}{ft}'-{whole}{fr}\""


def ft_dec(inches: float, nd: int = 2) -> float:
    return round(inches / 12.0, nd)


def sf(w_in: float, d_in: float) -> float:
    return w_in * d_in / 144.0


def ceil_div(a: float, b: float) -> int:
    return int(math.ceil(a / b - 1e-9))
