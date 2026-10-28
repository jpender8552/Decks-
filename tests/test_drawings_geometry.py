"""Drawing geometry on the Prentice job (jobs/prentice_centennial.json): the sheets draw the model as it is built — the bay's
angled walls turned on the plans, the A-301 front elevation at the deck's true width (members turned in plan at their true
extent across the view), a border on every exposed outline side painted over the field boards in the isometrics, the
field boards cut to the outline at the bay faces, every callout leader ending on its own member as painted, the key's whole
labels at one weight, D-501 detail 6's callouts inside their panel, and no type under the minimum printed size."""
import html
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import decktakeoff.axo as axo
from decktakeoff import drawings as D
from decktakeoff import run
from decktakeoff.scene import build_scene
from decktakeoff.spec import DeckSpec

ROOT = Path(__file__).resolve().parent.parent
JOB = json.loads((ROOT / "jobs" / "prentice_centennial.json").read_text())
ISOS = ("A-002", "A-003", "S-102")


def _sheets(job):
    """The job's drawing sheets {num: svg}, with what each isometric painted caught on the way: {num: boxes, record (every
    face in paint order), to_sheet, key, callout items (n, anchor point, label, hidden)}."""
    spec = DeckSpec.from_dict(job)
    t, flags, _ = run(spec, with_pricing=False)
    S = build_scene(t.layout)
    iso, cur = {}, {}
    real_sheet, real_draw, real_callouts = D._axo_sheet, axo.draw, axo.callouts

    def sheet_(num, title, sub, L, S_, t_, meta, boxes, *a, **k):
        cur["num"] = num
        iso[num] = {"key": k.get("key") if k.get("key") is not None else D.member_key(L, S_, t_)}
        try:
            return real_sheet(num, title, sub, L, S_, t_, meta, boxes, *a, **k)
        finally:
            cur["num"] = None

    def draw_(boxes, *a, **k):
        out = real_draw(boxes, *a, **k)
        if cur.get("num") and k.get("record") is not None:
            iso[cur["num"]].update(boxes=list(boxes), record=k["record"], to_sheet=out[1])
        return out

    def callouts_(items, to_sheet, frame, *a, **k):
        if cur.get("num"):
            iso[cur["num"]]["items"] = list(items)
        return real_callouts(items, to_sheet, frame, *a, **k)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(D, "_axo_sheet", sheet_)
        mp.setattr(axo, "draw", draw_)
        mp.setattr(axo, "callouts", callouts_)
        sheets = {num: svg for num, _, svg in D.all_sheets(t.layout, t, flags, S)}
    return SimpleNamespace(spec=spec, t=t, L=t.layout, S=S, sheets=sheets, iso=iso)


@pytest.fixture(scope="module")
def prentice():
    return _sheets(JOB)


def _in_poly(P, x, y, tol=0.02) -> bool:
    """Inside the polygon, or within tol of one of its sides."""
    for (x0, y0), (x1, y1) in zip(P, P[1:] + P[:1]):
        L_ = math.hypot(x1 - x0, y1 - y0) or 1e-9
        t_ = max(0.0, min(1.0, ((x - x0) * (x1 - x0) + (y - y0) * (y1 - y0)) / L_ ** 2))
        if math.hypot(x - (x0 + t_ * (x1 - x0)), y - (y0 + t_ * (y1 - y0))) <= tol:
            return True
    return axo._in_poly(P, x, y)


# ------------------------------------------------------------------ type size
def test_no_type_under_the_minimum_printed_size(prentice):
    assert D.MIN_TEXT * 9.6 * 72 / 1000 >= 6.5        # the 1000-unit sheet prints 9.6" wide: the minimum is 6.5 pt or more
    small = _sheets(json.loads((ROOT / "jobs" / "deck_10x10.json").read_text())).sheets       # a second job: the floor is the engine's
    for job, sheets in (("prentice", prentice.sheets), ("deck_10x10", small)):
        for num, svg in sheets.items():
            sizes = [float(v) for v in re.findall(r'font-size="([\d.]+)"', svg)]
            assert sizes, (job, num)
            assert min(sizes) >= D.MIN_TEXT - 1e-9, (job, num, min(sizes))


# ------------------------------------------------------------------ A-301: the front elevation at the true width
def test_a301_front_elevation_spans_the_true_deck_width(prentice):
    S = prentice.S
    P = S.meta["outline"]
    want = (max(x for x, _ in P) - min(x for x, _ in P) + 2 * S.meta["edge"]) * 12        # inches: the outline + the picture-frame overhang each end
    o = []
    D.draw_elev_boxes(o, lambda x: x * 12.0, lambda z: -z * 12.0, 12.0, S.boxes, ("board", "border"))
    spans = [(float(a), float(a) + float(w)) for a, w in (re.search(r'<rect x="([-\d.]+)" y="[-\d.]+" width="([\d.]+)"', r).groups() for r in o)]
    got = max(b for _, b in spans) - min(a for a, _ in spans)
    assert abs(got - want) <= 1.0, (got, want)
    turned = [b for b in S.boxes if b.kind in ("border", "fascia", "riser") and D._turned(b)]
    assert turned, "the angled sides' members are no longer turned in plan"
    for b in turned:                                    # each turned member at its true extent across the view, not its length
        o = []
        D.draw_elev_boxes(o, lambda x: x * 12.0, lambda z: -z * 12.0, 12.0, [b], (b.kind,))
        x_, w_ = (float(v) for v in re.search(r'<rect x="([-\d.]+)" y="[-\d.]+" width="([\d.]+)"', o[0]).groups())
        xs = [p[0] * 12 for p in D._turned_corners(b)]
        assert abs(x_ - min(xs)) < 0.1 and abs(w_ - (max(xs) - min(xs))) < 0.1, b.tag
    words = [html.unescape(w) for w in re.findall(r"<text[^>]*>([^<]*)</text>", prentice.sheets["A-301"])]
    assert "FRONT ELEVATION — from the yard" in words and D.ftin(414) in words       # the elevation, dimensioned at the overall width


# ------------------------------------------------------------------ the bay's angled walls on the plans
def test_bay_walls_drawn_turned_on_the_plans(prentice):
    S = prentice.S
    zt = getattr(S, "deck_top", 0.0)
    turned = [b for b in S.boxes if b.kind == "house" and D._turned(b) and not (b.z0 > zt + 6.0 and b.y1 > 0.05)]
    assert turned, "the bay's angled walls are no longer turned in the model"
    o = []
    D.house_outline(o, lambda x: x, lambda y: y, 1.0, S)
    polys = [s for s in o if s.startswith("<polygon")]
    for b in turned:                                    # each one drawn along its own face, not as its square box
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in D._turned_corners(b))
        assert any(f'points="{pts}"' in s for s in polys), b.tag
    for num in ("S-100", "S-101", "A-101", "A-201"):
        n = len(re.findall(r'<polygon points="[^"]*" fill="%s"' % re.escape(D.FILL["house"]), prentice.sheets[num]))
        assert n >= len(turned), (num, n, len(turned))


# ------------------------------------------------------------------ borders: on every exposed side, over the field
def _iso(prentice, num):
    c = prentice.iso[num]
    return c, axo.Painted(c["record"])


def test_every_exposed_side_shows_its_border_over_the_field(prentice):
    S, L = prentice.S, prentice.L
    P = [(float(a), float(b)) for a, b in S.meta["outline"]]
    exposed = [e for e in (L.outline_edges or []) if e.exposed]
    assert exposed
    for num in ("A-002", "A-003"):
        c, painted = _iso(prentice, num)
        borders = [b for b in c["boxes"] if b.kind == "border"]
        for e in exposed:                               # a border runs along every exposed side and shows in the view
            ex0, ey0, ex1, ey1 = e.x0 / 12, e.y0 / 12, e.x1 / 12, e.y1 / 12        # the outline sides are in inches, the model in feet
            Le = math.hypot(ex1 - ex0, ey1 - ey0)
            ux, uy = (ex1 - ex0) / Le, (ey1 - ey0) / Le
            on = []
            for b in borders:
                cs = D._turned_corners(b) if D._turned(b) else [(b.x0, b.y0), (b.x1, b.y0), (b.x1, b.y1), (b.x0, b.y1)]
                cx, cy = sum(p[0] for p in cs) / 4, sum(p[1] for p in cs) / 4
                ts = [(p[0] - ex0) * ux + (p[1] - ey0) * uy for p in cs]
                if abs((cx - ex0) * uy - (cy - ey0) * ux) < 0.6 and max(ts) > 0.05 and min(ts) < Le - 0.05:
                    on.append(b)
            assert on, (num, e.name)
            ids = {id(b) for b in on}
            assert axo.anchor_visible(c["boxes"], lambda b: id(b) in ids, painted, c["to_sheet"],
                                      num == "A-003", None, "mid", (0.5, 0.5, 1.0)) is not None, (num, e.name)
        for b in borders:                               # no field board painted over a border's top
            lf = axo.lift_of(b, num == "A-003", None)
            cs = D._turned_corners(b) if D._turned(b) else [(b.x0, b.y0), (b.x1, b.y0), (b.x1, b.y1), (b.x0, b.y1)]
            q = (sum(p[0] for p in cs) / 4, sum(p[1] for p in cs) / 4, b.z1 + lf)
            top = painted.top(*c["to_sheet"](q))
            assert top is None or top.kind != "board" or (top.tag or "").split(": ")[-1].startswith(D._BUILT_IN), (num, b.tag, top.tag)


def test_field_boards_cut_to_the_outline_at_the_bay(prentice):
    S = prentice.S
    P = [(float(a), float(b)) for a, b in S.meta["outline"]]
    cut = [b for b in D._cut_to_outline(S.boxes, S) if getattr(b, "qpoly", None)]
    assert cut, "no field board meets an angled house face any more"
    for b in cut:                                       # the cut board stays inside the deck: its angled end on the face
        assert all(_in_poly(P, x, y) for x, y in b.qpoly), b.tag
        assert len(b.qpoly) >= 3


# ------------------------------------------------------------------ callouts and the key
def test_callout_leaders_end_on_their_members(prentice):
    for num in ISOS:
        c, painted = _iso(prentice, num)
        key = c["key"]
        assert c["items"], num
        for n, q, lab, *hid in c["items"]:
            if hid and hid[0]:
                continue                                # hidden in this view: a dashed leader to where it lies
            top = painted.top(*c["to_sheet"](q))
            assert top is not None and key[n - 1][1](top), (num, n, lab, getattr(top, "tag", None))
    c, _ = _iso(prentice, "A-003")
    led = [it for it in c["items"] if "ledger" in it[2].lower()]
    assert led and not any(len(it) > 3 and it[3] for it in led), "A-003: the ledger's leader must end on the ledger"


def test_key_lists_whole_labels_at_one_weight(prentice):
    for num in ISOS:
        svg = prentice.sheets[num]
        lines = re.findall(r'<text x="753\.0" y="[-\d.]+" font-size="([\d.]+)" font-weight="(\d+)" text-anchor="start" fill="#111111">([^<]*)</text>', svg)
        assert lines, num
        assert {w for _, w, _ in lines} == {"600"} and {f for f, _, _ in lines} == {"9.5"}, num
        text = " ".join(" ".join(html.unescape(t).split()) for _, _, t in lines)
        labels = {n: lab for n, _, lab, *_ in prentice.iso[num]["items"]}
        for n, lab in labels.items():                   # every listed member's whole label, in its words
            assert " ".join(lab.split()) in text, (num, n, lab)


# ------------------------------------------------------------------ D-501 detail 6: the callouts inside the panel
def test_d501_blocking_callouts_inside_their_panel(prentice):
    svg = prentice.sheets["D-501"]
    x0, y0, w, h = 660, 330, 320, 270                   # panel 6
    for word in ("joists", "blocks, staggered", "(3) screws each end"):
        m = re.search(r'<text[^>]*\sx="([-\d.]+)" y="([-\d.]+)" font-size="([\d.]+)"[^>]*>' + re.escape(html.escape(word, quote=True)) + "</text>", svg)
        assert m, word
        x, y, fs = (float(v) for v in m.groups())
        assert x0 + 4 <= x and x + len(word) * fs * 0.55 <= x0 + w - 4, (word, x)
        assert y0 + 18 <= y <= y0 + h - 4, (word, y)


def _ray_planes(b, lf):
    """A box's prism as (outward unit normal, point) planes — the faces draw() paints, in plan feet."""
    cs = axo.corners(b, lf)
    qp = getattr(b, "qpoly", None)
    if qp:
        top_, bot_ = [(x, y, b.z1 + lf) for x, y in qp], [(x, y, b.z0 + lf) for x, y in qp]
        cs, fl = top_ + bot_, [top_, bot_[::-1]] + [[bot_[i - 1], bot_[i], top_[i], top_[i - 1]] for i in range(len(qp))]
    else:
        fl = [[cs[i] for i in f] for f in axo.FACES]
    cc = [sum(q[k] for q in cs) / len(cs) for k in range(3)]
    out = []
    for f in fl:
        n = [sum((f[i - 1][(k + 1) % 3] - f[i][(k + 1) % 3]) * (f[i - 1][(k + 2) % 3] + f[i][(k + 2) % 3]) for i in range(len(f))) for k in range(3)]
        fc = [sum(q[k] for q in f) / len(f) for k in range(3)]
        if sum(n[k] * (fc[k] - cc[k]) for k in range(3)) < 0:
            n = [-v for v in n]
        ln = math.sqrt(sum(v * v for v in n))
        if ln > 1e-12:
            out.append(([v / ln for v in n], fc))
    return out


def _ray_exit(planes, P, d, zc):
    """Where a ray P + t d (d toward the eye) leaves the prism nearest the eye — None when it misses it (or only meets it below zc)."""
    lo, hi = -1e18, 1e18
    for n, q0 in planes:
        nd, rhs = sum(n[k] * d[k] for k in range(3)), sum(n[k] * (q0[k] - P[k]) for k in range(3))
        if abs(nd) < 1e-12:
            if rhs < -1e-9:
                return None
            continue
        hi, lo = (min(hi, rhs / nd), lo) if nd > 0 else (hi, max(lo, rhs / nd))
    if zc is not None and d[2] > 1e-12:
        lo = max(lo, (zc - P[2]) / d[2])
    return hi if lo <= hi + 1e-9 else None


def _iso_records(job):
    """[(boxes, record with the border-over-field reorder, record without it, to_sheet, scale, view, explode, gaps)] for A-002 and
    A-003: each drawing painted both ways."""
    spec = DeckSpec.from_dict(job)
    t, flags, _ = run(spec, with_pricing=False)
    S, L, got = build_scene(t.layout), t.layout, []
    real_draw, real_fof = axo.draw, axo._frame_over_field

    def draw_(boxes, colors, view, frame, explode=False, gaps=None, *a, **k):
        k.setdefault("record", [])
        out = real_draw(boxes, colors, view, frame, explode, gaps, *a, **k)
        rb = []
        axo._frame_over_field = lambda order, *a_, **k_: order
        try:
            real_draw(boxes, colors, view, frame, explode, gaps, *a, **dict(k, record=rb))
        finally:
            axo._frame_over_field = real_fof
        got.append(([b for b in boxes if (getattr(b, "layer", "") or "") != "styling"], k["record"], rb, out[1], out[2], view, explode, gaps))
        return out
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(axo, "draw", draw_)
        if hasattr(L, "parts"):
            D.composite_sheets(L, t, flags, S, only={"A-002", "A-003"})
        else:
            meta = D.sheet_meta(L)
            D.sheet_iso_assembled(L, S, t, meta); D.sheet_iso_exploded(L, S, t, meta)
    return got


@pytest.mark.parametrize("name", ["glengarry_3_parapet_existing", "glengarry_lower", "jefferson_louisville", "fillmore_centennial", "prentice_centennial"])
def test_the_frame_over_field_reorder_only_uncovers_what_stands_in_front(name):
    """Sampled across A-002 and A-003, the border-over-field paint order changes what shows on top only where a field board
    painted over a border or over something that stands in front of it (a rail on the deck, a cover post): at every point it
    changed, the face now on top is a border over the board, or the face a ray along the view meets first. A wall, a parapet,
    a fascia, a riser or a lowered blind that the board hides stays hidden (Glengarry, Jefferson, Fillmore's step skirt)."""
    job = json.loads((ROOT / "jobs" / f"{name}.json").read_text())
    recs = _iso_records(job)
    assert len(recs) >= 2
    changed = 0
    for bx, ra, rb, to_sheet, sc, view, explode, gaps in recs:
        pa, pb = axo.Painted(ra), axo.Painted(rb)          # the same boxes both ways (one call of the sheet)
        ox, oy = to_sheet((0.0, 0.0, 0.0))
        pl, pts = {}, set()
        for b, Q in ra:                                    # only a field board's faces move: sample where they paint
            if b.kind == "board":
                for gx in range(int(min(q[0] for q in Q) // 3), int(max(q[0] for q in Q) // 3) + 1):
                    for gy in range(int(min(q[1] for q in Q) // 3), int(max(q[1] for q in Q) // 3) + 1):
                        pts.add((gx * 3.0 + 1.5, gy * 3.0 + 1.5))
        for x, y in sorted(pts):
            ta, tb = pa.top(x, y), pb.top(x, y)
            if ta is tb or tb is None:
                continue
            changed += 1
            assert tb.kind == "board", (name, round(x), round(y), tb.kind, ta.kind if ta else None)     # only a field board ever gives way
            if ta.kind == "border":
                continue
            px, py = (x - ox) / sc, (oy - y) / sc
            P = [px * view.r[k] + py * view.u[k] for k in range(3)]
            for b in (ta, tb):
                if id(b) not in pl:
                    lf = axo.lift_of(b, explode, gaps)
                    pl[id(b)] = (_ray_planes(b, lf), None if b.kind in ("footing", "base", "house", "ground") else lf)
            ha, hb = (_ray_exit(pl[id(b)][0], P, view.d, pl[id(b)][1]) for b in (ta, tb))
            assert ha is not None and (hb is None or ha >= hb - 1e-3), (name, round(x), round(y), ta.kind, ta.tag, tb.tag)   # now on top: nearer the eye
    assert changed, name                                   # the reorder still does its job: borders over the field boards' ends
