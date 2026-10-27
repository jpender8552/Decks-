"""Build the Fillmore 3D page from the spec assembler's files ($S/fillmore/spec/fillmore_centennial*.json, or jobs/ when they
land there):

    python3 build_spec.py [SPEC_DIR] [OUT.html] [--preview-alt=ALT.json]

Options (the toggles, in this order): stairs = _yardstair (the horseshoe), stairs_alt = _yardstair_alt (along the deck; only
when that file exists, or --preview-alt names a stand-in), lights = _lighting, roof = _roof, screens = _roof_screens.
House: the specs carry geometry.house_model. A spec without one gets $S/fillmore/house/house_model.json inlined (the same
file the assembler inlines); with neither, a STAND-IN house (blocks from the site research's roof print, plan_frame.json,
openings at the spec's own deck heights). Everything that is substituted is printed in "substituted"."""
import copy, json, sys, time
from pathlib import Path
from decktakeoff.configurator import build_configurator
S = Path("/tmp/claude-0/-home-user-Decks-/3110cd41-980c-5ceb-b230-1490acc026a8/scratchpad")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
src = Path(args[0]) if len(args) > 0 else S / "fillmore/spec"
out = args[1] if len(args) > 1 else str(S / "fillmore/configurator/fillmore_3d.html")
HOUSE = S / "fillmore/house/house_model.json"
STANDIN_BLOCKS = [[7.583, 50.167, -30.5, 0.0], [50.167, 64.7, -30.5, -2.0], [-1.5, 7.583, -45.0, -13.5], [7.583, 23.05, -53.3, -30.5],
                  [23.05, 44.97, -43.06, -30.5], [5.833, 7.583, -11.17, -6.17, "brick", 0.0, 24.0]]
substituted = []


def standin_openings(d):
    """Doors / windows on the stand-in house at the spec's own deck heights (never constants)."""
    lo, up = [p["geometry"]["height_in"] / 12.0 for p in d["geometry"]["parts"]][:2]
    H = d["geometry"]["height_in"] / 12.0 + 9.5            # the stand-in house's eave (scene.draw_house_from_spec)
    top = lambda z, h: min(z + h, H - 0.4)
    return [[33.0, 39.0, 0.0, up + 0.05, top(up, 6.6)], [12.0, 18.0, 0.0, lo + 0.05, top(lo, 6.7)], [1.0, 7.0, -13.5, lo + 0.05, top(lo, 6.7)],
            [53.0, 60.0, -2.0, up + 2.4, top(up, 5.8)], [32.0, 38.0, 0.0, 0.0, min(6.8, up - 1.4)], [42.0, 47.0, 0.0, up + 2.2, top(up, 5.6)]]


def load(path: Path):
    d = json.loads(path.read_text())
    g = d.setdefault("geometry", {})
    if not g.get("house_model") and not g.get("house_blocks"):
        if HOUSE.exists():
            g["house_model"] = json.loads(HOUSE.read_text())
            substituted.append(f"{path.name}: house_model inlined from {HOUSE}")
        else:
            g["house_blocks"] = copy.deepcopy(STANDIN_BLOCKS)
            g["house_openings"] = standin_openings(d)
            substituted.append(f"{path.name}: STAND-IN house blocks")
    return d


f = lambda n: src / f"fillmore_centennial{n}.json"
opts = {"stairs": f("_yardstair")}
alt = Path(flags["preview-alt"]) if flags.get("preview-alt") else f("_yardstair_alt")
if alt.exists():
    opts["stairs_alt"] = alt
    if flags.get("preview-alt"):
        substituted.append(f"stairs_alt: PREVIEW spec {alt}")
opts.update(lights=f("_lighting"), roof=f("_roof"), screens=f("_roof_screens"))
t0 = time.time()
st = build_configurator(load(f("")), {k: load(v) for k, v in opts.items()}, out, title="7303 S Fillmore Cir")
st["seconds"] = round(time.time() - t0, 2)
st["substituted"] = sorted(set(substituted))
print(json.dumps({k: v for k, v in st.items() if k != "warnings"}, indent=1)[:6000])
print("warnings:", len(st["warnings"]))
for w in st["warnings"]:
    print("  -", w[:600])
