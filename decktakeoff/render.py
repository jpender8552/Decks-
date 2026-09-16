"""Headless stills of the 3D viewer (Playwright + the preinstalled Chromium, SwiftShader GL). Writes JPEGs.
Views: yard, corner, ondeck, iso, plan, under; build steps 1..8 in iso; exploded iso."""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .scene import Scene
from .viewer import viewer_html

STILLS = [("yard", dict(view="yard")), ("corner", dict(view="corner")), ("ondeck", dict(view="ondeck")), ("iso", dict(view="iso")),
          ("plan", dict(view="plan")), ("under", dict(view="under")), ("exploded", dict(view="iso", explode="1")),
          # the second set: the opposite front corner, a low isometric, an isometric from under the frame, and the explosions from three angles
          ("iso2", dict(view="iso2")), ("isolow", dict(view="isolow")), ("underiso", dict(view="underiso")),
          ("exploded2", dict(view="iso2", explode="1")), ("exploded-corner", dict(view="corner", explode="1")), ("exploded-low", dict(view="isolow", explode="1")),
          ("frame-iso2", dict(view="iso2", phase="5")), ("rail-iso2", dict(view="iso2", phase="7")), ("structure-underiso", dict(view="underiso", phase="4"))] + \
         [(f"step{n}", dict(view="iso", phase=str(n))) for n in range(1, 9)]


def _chromium() -> Optional[str]:
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome", "/opt/pw-browsers/chromium", "/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"):
        m = sorted(glob.glob(pat))
        if m:
            return m[-1]
    return None


def three_source() -> Optional[str]:
    for p in (os.environ.get("THREE_MIN_JS"), str(Path(__file__).resolve().parent / "data" / "three.min.js")):
        if p and Path(p).exists():
            return Path(p).read_text()
    return None


def render_stills(scene: Scene, out_dir: str, which: Optional[List[str]] = None, size: Tuple[int, int] = (1400, 900), quality: int = 82) -> Dict[str, str]:
    """Returns {name: path}. Skips stills that already exist. Needs playwright + three.min.js on disk (data/ or $THREE_MIN_JS)."""
    from playwright.sync_api import sync_playwright
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    src = three_source()
    if src is None:
        raise RuntimeError("three.min.js not found: put it at decktakeoff/data/three.min.js or set THREE_MIN_JS")
    html = viewer_html(scene, three_src=src)
    page_path = out / "_viewer_local.html"
    page_path.write_text(html)
    done: Dict[str, str] = {}
    todo = [(n, p) for n, p in STILLS if (which is None or n in which)]
    exe = _chromium()
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=exe, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"])
        pg = b.new_page(viewport={"width": size[0], "height": size[1]})
        for name, params in todo:
            target = out / f"{name}.jpg"
            if target.exists():
                done[name] = str(target); continue
            qs = "&".join(f"{k}={v}" for k, v in dict(params, still="1").items())
            pg.goto(f"file://{page_path}?{qs}")
            pg.wait_for_function("window.__ready === true", timeout=60000)
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(target), type="jpeg", quality=quality, full_page=False)
            done[name] = str(target)
        b.close()
    return done
