"""The build set (drawing sheets, 3D scene, viewer, build steps) builds for both standards without a browser."""
import json
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff.buildset import build_set, step_sheets
from decktakeoff.drawings import SHEET_INDEX, all_sheets
from decktakeoff.scene import build_scene
from decktakeoff.spec import DeckSpec
from decktakeoff.viewer import viewer_html

EX = Path(__file__).parent.parent / "examples"
SHEET_NUMBERS = ["G-001", "S-100", "S-101", "A-101", "A-201", "A-301", "D-501"]   # the drawn sheets (A-001 = renders, T-* = generated pages)


@pytest.fixture(scope="module", params=["eagles_nest.json", "jason_ct.json"])
def job(request):
    spec = DeckSpec.from_dict(json.loads((EX / request.param).read_text()))
    t, f, _ = run(spec)
    return t, f


def test_scene_has_every_system(job):
    t, _ = job
    S = build_scene(t.layout)
    kinds = {b.kind for b in S.boxes}
    for k in ("footing", "post", "beam", "ledger", "rim", "joist", "board", "border", "railpost", "toprail"):
        assert k in kinds, k
    phases = {b.phase for b in S.boxes}
    assert phases >= {1, 2, 4, 5, 6}                         # footings, posts/beams, frame, decking, rail
    d = S.to_dict()
    assert d["W"] > 0 and d["deck_top"] > 0 and len(d["boxes"]) == len(S.boxes)
    posts = [b for b in S.boxes if b.kind == "post"]
    assert len(posts) == sum(len(bl.posts_x) for bl in t.layout.beam_lines)


def test_sheets_cover_the_index(job):
    t, f = job
    sheets = all_sheets(t.layout, t, f, build_scene(t.layout))
    nums = [n for n, _, _ in sheets]
    assert nums == SHEET_NUMBERS
    for n, title, svg in sheets:
        assert svg.startswith("<svg") and n in svg and len(svg) > 2000, n


def test_viewer_is_self_contained_and_steps_follow_phases(job):
    t, _ = job
    S = build_scene(t.layout)
    html = viewer_html(S, None, title="t")
    assert "three" in html and "__ready" in html and '"boxes"' in html
    steps = step_sheets(t, t.layout)
    codes = [s["code"] for s in steps]
    assert codes[0] == "T-400" and codes == sorted(codes)         # numbered by phase; a job without stone bases skips T-402
    assert all(s["goes_in"] and s["how"] and s["check"] for s in steps)


def test_build_set_writes_the_folder(job, tmp_path):
    t, f = job
    out = build_set(t, f, str(tmp_path / "bs"), render=False)
    assert Path(out["buildset"]).exists() and Path(out["viewer"]).exists()
    assert sorted(p.stem for p in (tmp_path / "bs" / "sheets").glob("*.svg")) == sorted(SHEET_NUMBERS)
    assert (tmp_path / "bs" / "scene.json").exists()
    assert out["stills"] == {}
