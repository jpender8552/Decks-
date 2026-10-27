#!/usr/bin/env python3
"""149 Morning Sun Ave, Mill Valley — the as-built permit set for Adam Messner's deck, under the PCG brand.

    cd /home/user/Decks- && python3 jobs/messner_site/tooling/build_messner.py                       # the job: messner.json + messner_extra.json
    python3 jobs/messner_site/tooling/build_messner.py SPEC.json --extra EXTRA.json --out DIR --no-pdf
    python3 jobs/messner_site/tooling/build_messner.py jobs/messner_site/test/as_built_test.json --extra jobs/messner_site/test/as_built_test_extra.json

The engine (decktakeoff/) is used as it is: messner_ext.py patches it only for the length of this build (see its docstring for every
job field). Writes DIR/page.html (+ page.pdf), DIR/buildset-1/sheets/*.svg and DIR/files.json; prints the sheet list."""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import messner_ext as MX          # noqa: E402

SITE = HERE.parent
DEFAULT_SPEC = SITE / "messner.json"
DEFAULT_EXTRA = SITE / "messner_extra.json"
DEFAULT_OUT = MX.REPO / "out" / "messner_permit"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="build_messner", description="Messner as-built permit set (PCG)")
    ap.add_argument("spec", nargs="?", default=str(DEFAULT_SPEC), help="the job spec (default jobs/messner_site/messner.json)")
    ap.add_argument("--extra", default=None, help="the job-local fields JSON (default jobs/messner_site/messner_extra.json when it exists)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output folder (default out/messner_permit)")
    ap.add_argument("--key", default="messner", help="file key for the page's render files")
    ap.add_argument("--name", default=None, help="the set's name (default: the spec's job)")
    ap.add_argument("--sub", default="", help="the line under the name (default: the address)")
    ap.add_argument("--date", default=None, help='the date line, e.g. "October 28, 2026" (default today)')
    ap.add_argument("--renders", default=None, help="a JSON {title: [[caption, jpg], ...]} of 3D views to add after the sheets")
    ap.add_argument("--no-pdf", action="store_true", help="HTML only")
    a = ap.parse_args(argv)
    extra = a.extra or (str(DEFAULT_EXTRA) if DEFAULT_EXTRA.exists() and Path(a.spec).resolve() == DEFAULT_SPEC.resolve() else None)
    spec, ext = MX.load_job(a.spec, extra)
    renders = json.load(open(a.renders)) if a.renders else None
    name = a.name or f"{spec.site.address} · " + ("Existing Deck — As Built" if ext.as_built else spec.job)
    r = MX.render_permit_set([dict(spec=spec, title="Deck" if not ext.as_built else "Existing deck")], a.out, key=a.key, name=name, sub=a.sub,
                             pdf=not a.no_pdf, date_line=a.date, renders={k: [tuple(x) for x in v] for k, v in renders.items()} if renders else None)
    print(f"wrote {r['html']}" + (f" and {r['pdf']}" if r.get("pdf") else "") + f" — {r['sheets']} sheets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
