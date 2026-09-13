"""decktakeoff — deck takeoff engine (foundations, framing, hardware, flashing, decking, fasteners, fascia, rail, stairs) with
code/site flags and the GSX pricing model."""
from .spec import DeckSpec
from .takeoff import build_takeoff, Takeoff
from .flags import run_flags
from .pricing import price
from .report import takeoff_markdown, takeoff_json, order_csv, gsx_job_block, quote_markdown
from .intake import parse_details, spec_from_drawing

__all__ = ["DeckSpec", "build_takeoff", "Takeoff", "run_flags", "price", "takeoff_markdown", "takeoff_json", "order_csv",
           "gsx_job_block", "quote_markdown", "parse_details", "spec_from_drawing", "run"]
__version__ = "0.1.0"


def run(spec: DeckSpec, with_pricing: bool = True):
    """One call: takeoff + flags (+ pricing). Returns (takeoff, flags, pricing|None)."""
    t = build_takeoff(spec)
    f = run_flags(t.layout)
    p = price(t) if with_pricing else None
    return t, f, p
