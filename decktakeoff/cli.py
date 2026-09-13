"""CLI:  python -m decktakeoff SPEC.json [--details "..."] [--image drawing.png] [--out DIR] [--price] [--gsx]
        python -m decktakeoff --details "12x16, 30in high, Prime+ Coconut Husk, Fulton black, stairs front" --out out/"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import run
from .intake import parse_details, spec_from_drawing
from .report import gsx_job_block, order_csv, takeoff_json, takeoff_markdown
from .spec import DeckSpec


def main(argv=None):
    ap = argparse.ArgumentParser(prog="decktakeoff", description="Deck takeoff engine")
    ap.add_argument("spec", nargs="?", help="spec JSON file")
    ap.add_argument("--details", help="plain-English details to parse / override the spec")
    ap.add_argument("--image", help="drawing or photo to read with Claude (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--out", help="output directory (writes takeoff.md/.json, order.csv, gsx_job_block.py)")
    ap.add_argument("--price", action="store_true", help="include the internal pricing section")
    ap.add_argument("--gsx", action="store_true", help="also print the gsx-deck-docs job block")
    ap.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    a = ap.parse_args(argv)
    base = json.loads(Path(a.spec).read_text()) if a.spec else None
    if a.image:
        spec = spec_from_drawing(a.image, a.details or "", base)
    elif a.details:
        spec = parse_details(a.details, base)
    elif base is not None:
        spec = DeckSpec.from_dict(base)
    else:
        ap.error("give a spec JSON, --details, or --image")
    t, f, p = run(spec, with_pricing=a.price)
    md = takeoff_markdown(t, f, p)
    js = takeoff_json(t, f, p)
    if a.out:
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        (out / "takeoff.md").write_text(md)
        (out / "takeoff.json").write_text(json.dumps(js, indent=2, default=str))
        (out / "order.csv").write_text(order_csv(t))
        (out / "spec.json").write_text(spec.to_json())
        (out / "gsx_job_block.py").write_text(gsx_job_block(t))
        print(f"wrote {out}/takeoff.md, takeoff.json, order.csv, spec.json, gsx_job_block.py")
    if a.json:
        print(json.dumps(js, indent=2, default=str))
    else:
        print(md)
    if a.gsx:
        print(gsx_job_block(t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
