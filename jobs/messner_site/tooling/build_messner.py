#!/usr/bin/env python3
"""149 Morning Sun Ave, Mill Valley — the as-built permit set for Adam Messner's deck, under the PCG brand.

    cd /home/user/Decks- && python3 jobs/messner_site/tooling/build_messner.py                       # the job: messner_spec.json (+ messner_extra.json if present)
    python3 jobs/messner_site/tooling/build_messner.py SPEC.json --extra EXTRA.json --out DIR --no-pdf
    python3 jobs/messner_site/tooling/build_messner.py jobs/messner_site/test/as_built_test.json --extra jobs/messner_site/test/as_built_test_extra.json
    python3 jobs/messner_site/tooling/build_messner.py --sheet-size tabloid --out /tmp/reduced     # an 11x17 reduced copy (not to scale)

The engine (decktakeoff/) is used as it is: messner_ext.py patches it only for the length of this build (see its docstring for every
job field). Writes DIR/page.html (+ page.pdf: one sheet a page, 24x36 at true scale by default), DIR/buildset-1/sheets/*.svg and DIR/files.json."""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import messner_ext as MX          # noqa: E402

SITE = HERE.parent
DEFAULT_SPEC = SITE / "messner_spec.json"
DEFAULT_EXTRA = SITE / "messner_extra.json"
DEFAULT_OUT = MX.REPO / "out" / "messner_permit"
SCRATCH = "/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad/messner"
# the site-plan agent's output: C-100_submittal_field.svg (the 1000 x 612 drawing field at true scale, no title block) becomes C-100;
# its C-100.svg is the internal analysis sheet and never goes in the permit set
DEFAULT_SITEPLAN = Path(os.environ.get("MESSNER_SITEPLAN_DIR") or f"{SCRATCH}/siteplan")
# the photo exhibit agent's list: [{"img", "caption", "callouts": [{"x", "y", "label"}]}] (paths relative to it) -> A-501..
DEFAULT_PHOTOS = Path(os.environ.get("MESSNER_PHOTOS") or f"{SCRATCH}/photo_exhibit/photos.json")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="build_messner", description="Messner as-built permit set (PCG)")
    ap.add_argument("spec", nargs="?", default=str(DEFAULT_SPEC), help="the job spec (default jobs/messner_site/messner_spec.json)")
    ap.add_argument("--extra", default=None, help="the job-local fields JSON (default jobs/messner_site/messner_extra.json when it exists)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output folder (default out/messner_permit)")
    ap.add_argument("--key", default="messner", help="file key for the page's render files")
    ap.add_argument("--name", default=None, help="the set's name (default: the spec's job)")
    ap.add_argument("--sub", default="", help="the line under the name (default: the address)")
    ap.add_argument("--date", default=None, help='the date line, e.g. "October 28, 2026" (default today)')
    ap.add_argument("--renders", default=None, help="a JSON {title: [[caption, jpg], ...]} of 3D views to add after the sheets")
    ap.add_argument("--siteplan-dir", default=str(DEFAULT_SITEPLAN), help="the site plan: C-100_submittal_field.svg there becomes C-100 (never C-100.svg)")
    ap.add_argument("--siteplan-scale", default="", help='the site plan\'s scale note when its SVG carries none, e.g. "1\" = 10\'-0\""')
    ap.add_argument("--photos", default=str(DEFAULT_PHOTOS), help='the photo exhibit: a JSON list [{"img", "caption", "callouts": [{"x", "y", "label"}]}] (paths relative to it); used when it exists')
    ap.add_argument("--sheet-size", default="archd", choices=sorted(MX.SHEET_SIZES), help="archd = 24x36 ARCH D, the sheets at true scale (default); tabloid (11x17) or letter: a reduced copy, not to scale")
    ap.add_argument("--no-pdf", action="store_true", help="HTML only")
    a = ap.parse_args(argv)
    extra_path = a.extra or (str(DEFAULT_EXTRA) if DEFAULT_EXTRA.exists() and Path(a.spec).resolve() == DEFAULT_SPEC.resolve() else None)
    extra = json.load(open(extra_path)) if extra_path else {}
    spd = Path(a.siteplan_dir)
    sp = {k: str(spd / f) for k, f in (("json", "siteplan.json"), ("field_svg", "C-100_submittal_field.svg"), ("vicinity_svg", "vicinity.svg")) if (spd / f).is_file()}
    if sp:
        extra = MX._merge(extra, {"site": {"site_plan": sp}})
        print("site plan:", ", ".join(sp.values()))
    spec, ext = MX.load_job(a.spec, extra=extra)
    photos = None
    if a.photos and Path(a.photos).is_file():
        pj = Path(a.photos).resolve()
        lst = json.load(open(pj))
        lst = lst.get("photos", lst) if isinstance(lst, dict) else lst
        photos = [dict(p, img=str((pj.parent / p["img"]).resolve()) if not Path(p["img"]).is_absolute() else p["img"]) for p in lst]
        print(f"photos: {len(photos)} from {pj}")
    renders = json.load(open(a.renders)) if a.renders else None
    name = a.name or f"{spec.site.address} · " + ("Existing Deck — As Built" if ext.as_built else spec.job)
    r = MX.render_permit_set([dict(spec=spec, title="Deck" if not ext.as_built else "Existing deck")], a.out, key=a.key, name=name, sub=a.sub,
                             pdf=not a.no_pdf, date_line=a.date, renders={k: [tuple(x) for x in v] for k, v in renders.items()} if renders else None, photos=photos,
                             sheet_size=a.sheet_size, siteplan_scale=a.siteplan_scale)
    print(f"wrote {r['html']}" + (f" and {r['pdf']}" if r.get("pdf") else "") + f" — {r['sheets']} sheets at {MX.SHEET_SIZES[r['sheet_size']][2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
