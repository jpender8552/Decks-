#!/usr/bin/env python3
"""Per-palette render specs for the exterior color study, 7303 S Fillmore Cir: specs/<palette>.json, the input of the Cycles stills
(cycles_all.sh). Each one is the CURRENT /home/user/Decks-/jobs/fillmore_centennial.json plus the palette's paint from palettes.json:
geometry.house_model.colors updated, and decking.color set when the palette has a deck. These are the same two writes
render_palettes.py makes in memory for the three.js stills, so both stills sets come from the same job. Nothing else is touched:
the job's furniture (geometry.furniture), structure and site model come through as they are. The repo is only read.
    python3 make_specs.py [--job PATH] [--out DIR]
It checks every spec against the job and stops if any key outside those two differs. Written as compact json, as before;
a spec that would not change is left alone (same mtime).
"""
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
JOB = "/home/user/Decks-/jobs/fillmore_centennial.json"
ALLOWED = ("/geometry/house_model/colors/", "/decking/color")     # the only paths a palette may change


def diff(a, b, path=""):
    """Paths where a and b differ: [(path, old, new)]. A missing key is reported as None."""
    if type(a) != type(b):
        return [(path or "/", a, b)]
    if isinstance(a, dict):
        out = []
        for k in sorted(a.keys() | b.keys()):
            out += diff(a.get(k), b.get(k), f"{path}/{k}") if (k in a and k in b) else [(f"{path}/{k}", a.get(k), b.get(k))]
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [(path, f"list of {len(a)}", f"list of {len(b)}")]
        return [x for i, (p, q) in enumerate(zip(a, b)) for x in diff(p, q, f"{path}[{i}]")]
    return [] if a == b else [(path, a, b)]


def main(argv):
    job, out = JOB, HERE / "specs"
    if "--job" in argv:
        job = argv[argv.index("--job") + 1]
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    pals = json.load(open(HERE / "palettes.json"))
    base = json.load(open(job))
    sm = base["geometry"].get("site_model") or {}
    nbs = sm.get("neighbors") or sm.get("neighbours") or []          # older job files spell the key the British way
    print(f"job: {job} ({len(base['geometry'].get('furniture') or [])} furniture pieces, {len(nbs)} neighbor houses, "
          f"drink rail: {base['railing'].get('drink_rail')})")
    for nm, p in pals.items():
        d = copy.deepcopy(base)
        d["geometry"]["house_model"]["colors"].update(p.get("house") or {})
        if p.get("deck"):
            d["decking"]["color"] = p["deck"]
        bad = [x for x in diff(base, d) if not x[0].startswith(ALLOWED)]
        if bad:
            sys.exit(f"{nm}: keys outside the palette differ from the job: {bad[:5]}")
        txt, f = json.dumps(d), out / f"{nm}.json"
        same = f.exists() and f.read_text() == txt          # an unchanged spec keeps its mtime (cycles_all.sh skips stills newer than it)
        if not same:
            f.write_text(txt)
        print(f"{nm}: {f}  ({'unchanged' if same else 'written'}; {len(diff(base, d))} palette keys differ from the job; deck {d['decking']['color']})")


if __name__ == "__main__":
    main(sys.argv[1:])
