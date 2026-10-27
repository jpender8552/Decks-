#!/usr/bin/env python3
"""Exterior color study, 7303 S Fillmore Cir: three.js stills of the house + base deck per paint palette.
Same still path as build_fillmore.py's optstills (decktakeoff.render.render_stills on a spec copy), same stations as the proposal:
  yard   = the proposal's 'yard' still (site camera u01, trees on)
  corner = the proposal's 'corner' still (generic front-corner camera, trees + fences hidden: notrees=1)
  upper  = site camera 'upper_deck' (u18, the photoreal set's 'ondeck' slot)
    python3 render_palettes.py [palette ...]      (default: every palette in palettes.json)
"""
import copy, json, sys, time
from pathlib import Path
sys.path.insert(0, "/home/user/Decks-")
HERE = Path(__file__).resolve().parent.parent
SPEC = Path("/home/user/Decks-/jobs/fillmore_centennial.json")
VIEWS = [("yard", dict(view="yard")), ("corner", dict(view="corner", notrees="1")), ("upper", dict(view="upper_deck"))]

def main(argv):
    from decktakeoff import run
    from decktakeoff.spec import DeckSpec
    from decktakeoff.scene import build_scene
    import decktakeoff.render as R
    from decktakeoff.render import render_stills
    _vh = R.viewer_html
    OLD_TONES = "const tones = [shade(hex, -0.14), shade(hex, -0.06), hex, hex, shade(hex, 0.07), shade(hex, 0.14), shade(hex, 0.04), shade(hex, -0.22)];"
    OLD_BG = "g.fillStyle = shade(hex, 0.18); g.fillRect(0, 0, 512, 512);\n    for (let r = 0; r < nc; r++)"
    OLD_FLASH = "g.globalAlpha = 0.25; g.fillStyle = shade(hex, 0.25);"
    def painted_viewer_html(scene, **kw):
        """The brick painted: one paint colour on every brick (a faint sandy face), the joints the same paint in shadow."""
        h = _vh(scene, **kw)
        for a in (OLD_TONES, OLD_BG, OLD_FLASH):
            assert h.count(a) == 1, "viewer brick code changed: " + a[:40]
        return (h.replace(OLD_TONES, "const tones = [shade(hex, -0.02), hex, hex, shade(hex, 0.02)];")
                 .replace(OLD_BG, OLD_BG.replace("shade(hex, 0.18)", "shade(hex, -0.18)"))
                 .replace(OLD_FLASH, "g.globalAlpha = 0.0; g.fillStyle = shade(hex, 0.25);"))
    pals = json.load(open(HERE / "palettes.json"))
    base = json.load(open(SPEC))
    names = [a for a in argv if not a.startswith("--")] or list(pals)
    views = VIEWS
    for nm in names:
        p = pals[nm]
        d = copy.deepcopy(base)
        d["geometry"]["house_model"]["colors"].update(p.get("house") or {})
        if p.get("deck"):
            d["decking"]["color"] = p["deck"]
        out = HERE / "renders" / nm
        out.mkdir(parents=True, exist_ok=True)
        for q in out.glob("*.jpg"):
            q.unlink()
        t0 = time.time()
        t, _, _ = run(DeckSpec.from_dict(d))
        R.viewer_html = painted_viewer_html if p.get("brick_painted", True) else _vh
        render_stills(build_scene(t.layout), str(out), which=[], extra=views)
        (out / "_viewer_local.html").unlink(missing_ok=True)
        print(f"{nm}: {len(list(out.glob('*.jpg')))} stills in {time.time() - t0:.0f}s ({out})", flush=True)

if __name__ == "__main__":
    main(sys.argv[1:])
