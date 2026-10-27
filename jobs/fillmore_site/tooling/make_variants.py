"""Render variants for 7303 S Fillmore Cir (rendering agent): the assembler's option specs ($S/fillmore/spec) plus the
render-only deltas - the louver angle (open / half / closed), the screens' drop (down / half), lighting with the yard stair.
Writes $S/fillmore/render/specs/<set>.json and prints the list. The option specs themselves are not changed.

    python3 make_variants.py [--spec-dir=DIR] [--out=DIR] [--house=house_model.json]
--house: inline this house model into any variant whose spec has none yet (the spec's own house model wins).
Louvered engine angle rule (louvered.py): 0 = closed flat .. 90 = blades on edge (open) .. 140 = Suncoast max."""
import copy, json, os, sys

S = "/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad"
opts = dict(a.lstrip("-").split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
SPEC_DIR = opts.get("spec-dir", "/home/user/Decks-/jobs")          # the final specs (lead, 27 Oct)
OUT = opts.get("out", f"{S}/fillmore/render/specs")
HOUSE = opts.get("house", f"{S}/fillmore/house/house_model.json")
NAME = "fillmore_centennial"
OPEN, HALF, CLOSED = 90.0, 45.0, 0.0


def load(sfx=""):
    p = os.path.join(SPEC_DIR, f"{NAME}{sfx}.json")
    return (json.load(open(p)), p) if os.path.exists(p) else (None, p)


def roofs(d):
    return d["geometry"].get("louvered_roofs") or []


def main():
    os.makedirs(OUT, exist_ok=True)
    house = json.load(open(HOUSE)) if HOUSE and os.path.exists(HOUSE) else None
    base, _ = load()
    yard, _ = load("_yardstair")
    yard_alt, _ = load("_yardstair_alt")
    lit, _ = load("_lighting")
    roof, _ = load("_roof")
    scr, _ = load("_roof_screens")
    v = {"base": base, "yardstair": yard, "lights": lit}
    if yard_alt:
        v["yardstair_alt"] = yard_alt
    ly = copy.deepcopy(yard)                                     # the lighting option with the yard stair (the add-on's lights)
    ly["extras"]["lights"] = copy.deepcopy(lit["extras"].get("lights") or {"riser": True, "post_cap": True})
    v["lights_yardstair"] = ly
    if yard_alt:                                                 # the same lights with Option 2B (the stairs along the deck)
        lya = copy.deepcopy(yard_alt)
        lya["extras"]["lights"] = copy.deepcopy(ly["extras"]["lights"])
        v["lights_yardstair_alt"] = lya
    for nm, ang in (("roof_open", OPEN), ("roof_half", HALF), ("roof_closed", CLOSED)):
        d = copy.deepcopy(roof)
        for r in roofs(d):
            r["angle_deg"] = ang
            r.pop("screens", None)
        v[nm] = d
    for nm, drop in (("screens_down", 1.0), ("screens_half", 0.5)):
        d = copy.deepcopy(scr)
        for r in roofs(d):
            r["angle_deg"] = CLOSED                               # the screened room: louvers closed, screens down / half down
            for s_ in r.get("screens") or []:
                s_["drop"] = drop
        v[nm] = d
    for nm, d in v.items():
        inl = ""
        if house and not d["geometry"].get("house_model"):
            d["geometry"]["house_model"] = house
            inl = "  [house_model inlined from " + os.path.basename(HOUSE) + "]"
        p = os.path.join(OUT, f"{nm}.json")
        json.dump(d, open(p, "w"), indent=1)
        rs = roofs(d)
        print(f"{nm:18s} -> {p}" + (f"  (louvers {rs[0].get('angle_deg')} deg" + (f", screens {[(s_.get('side'), s_.get('drop')) for s_ in rs[0].get('screens') or []]}" if rs[0].get('screens') else "") + ")" if rs else "") + inl)


if __name__ == "__main__":
    main()
