"""Takeoff fixes from the engine code review (decktakeoff/takeoff.py), on the Prentice job (jobs/prentice_centennial.json) and
its variants, Jefferson (a Vintage deck under a HardieTrim fascia) and every job in jobs/:
B1 — a HardieTrim skirt takes its own trim screws, so a PVC deck under one orders no TOPLoc fascia screws, and every Cap-Tor
     "N screws needed (part a · part b ...)" total is the sum of the parts it lists (Prentice as Vintage with CONCEALoc and no
     border fastener once ordered a TOPLoc pack for the Hardie fascia and Cap-Tor "204 needed" for 37 + 170 + 194 = 401: a box short);
B2 — a box step mitered into its neighbor at an outline corner has no end skirt there (scene._miter_box_steps drops it), so the
     order and the cut list carry only the skirts the scene keeps (Prentice: the edge:2 and edge:3 steps, one each); the miter is
     the step the scene reads on that side (the last box step listed there), so a skirted stringer stair or another box step on
     the same side keeps both its skirts and its square-cut treads;
B3 — the face-screw schedule names exactly the Cap-Tor line's parts, no empty part between its separators ("@ 16\" ·  · stair")."""
import copy
import json
import math
import re
from collections import Counter
from pathlib import Path

import pytest

from decktakeoff import run
from decktakeoff import scene as scene_mod
from decktakeoff.scene import box_step_miters, build_scene
from decktakeoff.spec import DeckSpec

ROOT = Path(__file__).resolve().parent.parent
JOBS = sorted(p for p in (ROOT / "jobs").glob("*.json") if "messner" not in str(p))
PRENTICE = json.loads((ROOT / "jobs" / "prentice_centennial.json").read_text())
BOX_SIDES = ("edge:2", "edge:3")            # "Left box step — left side" and "— front angle": mitered into one step at their shared corner
TOPLOC = "TOPLoc fascia screws for Advanced PVC fascia"
NEEDED = re.compile(r"(-?\d+) screws needed\s+\(([^)]*)\)")
RULES = {"first row": "first row 1 per joist", "border": "borders 2 per bearing point", "fascia": "fascia 2 at each board end", "stairs": "stair treads 2 per stringer"}


def _variant(coll=None, color=None, fastener=None, border="keep", hardie=True, profile=None, job=PRENTICE):
    d = copy.deepcopy(job)
    dk = d["decking"]
    if coll:
        dk["collection"], dk["color"] = coll, color
    if fastener:
        dk["fastener_system"] = fastener
    if profile:
        dk["profile"] = profile
    if border != "keep":
        dk.pop("border_fastener", None)
        if border:
            dk["border_fastener"] = border
    if not hardie:
        d["extras"].pop("hardie_skirt", None); d["extras"].pop("hardie_color", None)
    return d


def _takeoff(job):
    return run(DeckSpec.from_dict(job), with_pricing=False)[0]


def _lines(t, needle, cat="Fasteners"):
    return [l for l in t.lines if l.category == cat and needle in l.item]


def _cap_tor(t):
    """The Cap-Tor line for the face screws left over (not the face-screwed field's, not a step-face skirt's): its total and parts."""
    m = [l for l in _lines(t, "Starborn Cap-Tor") if NEEDED.search(l.why)]
    if not m:
        return None, 0, {}
    assert len(m) == 1, [l.why for l in m]
    tot, parts = NEEDED.search(m[0].why).groups()
    return m[0], int(tot), {k_: int(v_) for k_, v_ in (p_.rsplit(" ", 1) for p_ in parts.split(" · "))}


def _lead(why):
    return int(re.match(r"\s*(-?\d+)", why).group(1))


def _skirt_cuts(t):
    return [c for c in t.cut_list if c.member.startswith("Stair skirt")]


# ------------------------------------------------------------------ B1: the fascia screws under a HardieTrim skirt
@pytest.fixture(scope="module")
def vintage():
    """Prentice in Vintage (PVC) on CONCEALoc: with the job's Hardie skirt or not, with its Cortex border or no border fastener."""
    return {(h, b): _takeoff(_variant("Vintage", "Coastline", "CONCEALoc", border=b, hardie=h)) for h in (True, False) for b in ("Cortex", None)}


def test_hardie_skirt_on_pvc_orders_no_toploc_and_the_whole_cap_tor(vintage):
    t = vintage[(True, None)]
    assert not _lines(t, TOPLOC)                                            # the fascia is HardieTrim, on its own fasteners
    assert _lines(t, "finish nail", "Fascia")                               # TR1509: ring-shank finish nails into a wood frame (G2a)
    assert "Fascia" not in t.schedule                                       # no TOPLoc rule for a HardieTrim fascia
    line, tot, parts = _cap_tor(t)
    assert set(parts) == {"first row", "border", "stairs"} and tot == sum(parts.values())
    # the same counts the Cortex-border variant hands to Cortex (border + stairs) and leaves to Cap-Tor (first row)
    cx = vintage[(True, "Cortex")]
    (cl,) = _lines(cx, "plugs — picture frame, dividers")
    b_, s_ = map(int, re.search(r"border/divider (\d+) · stairs (\d+)", cl.why).groups())
    assert parts == {"first row": _cap_tor(cx)[2]["first row"], "border": b_, "stairs": s_}
    assert line.order == math.ceil(tot / 350)                               # every part counted (the old line ordered 1 box for "204" of 401)


def test_pvc_fascia_without_hardie_still_takes_toploc(vintage):
    t, h = vintage[(False, None)], vintage[(True, None)]
    (tl,) = _lines(t, TOPLOC)
    assert _lead(tl.why) > 0 and "TOPLoc" in t.schedule["Fascia"]
    _, tot, parts = _cap_tor(t)
    # the fascia goes to TOPLoc or to the Hardie nails, never Cap-Tor; PVC risers are screwed with the treads, HardieTrim risers nailed (G2a)
    sup = lambda st: st.stringers or int(math.ceil(st.width / 16.0)) + 1          # a riser: every stringer, or a box step's front rim every 16"
    risers = sum(st.riser_pieces * sup(st) * 2 for st in t.layout.stairs)
    hparts = _cap_tor(h)[2]
    assert "fascia" not in parts and parts == {**hparts, "stairs": hparts["stairs"] + risers} and tot == sum(parts.values())
    assert RULES["fascia"] not in t.schedule["Face screws"]                 # the schedule does not send Cap-Tor to a TOPLoc fascia
    _, _, cparts = _cap_tor(vintage[(False, "Cortex")])
    assert cparts == {"first row": parts["first row"]}                      # a Cortex border takes the border and the stairs


def test_jefferson_hardie_fascia_orders_no_toploc():
    t = _takeoff(json.loads((ROOT / "jobs" / "jefferson_louisville.json").read_text()))
    assert t.spec.extras.hardie_skirt and t.layout.decking.material == "PVC"
    assert not _lines(t, TOPLOC) and "Fascia" not in t.schedule
    line, tot, parts = _cap_tor(t)
    assert set(parts) == {"first row", "border", "stairs"} and tot == sum(parts.values()) and line.order == math.ceil(tot / 350)
    assert t.schedule["Face screws"] == ("Cap-Tor xd color-matched ONLY at: first row 1 per joist on the house edge · "     # the borders at the frame's own spacing
                                         f"borders 2 per bearing point @ {t.layout.frame.spacing:g}\" · stair treads 2 per stringer per board")


def test_cortex_field_leaves_cap_tor_only_the_fascia():
    t = _takeoff(_variant("Terrain+", "Dark Oak", "Cortex", border=None, hardie=False))
    (field,) = [l for l in _lines(t, "Cortex for TimberTech") if "borders" not in l.item]
    assert "stair treads + risers" in field.why                             # the field, the stairs and (below) the borders are Cortex
    assert _lines(t, "plugs — borders + dividers")
    line, tot, parts = _cap_tor(t)
    assert list(parts) == ["fascia"] and tot == parts["fascia"] > 0         # was "165 needed (first row 37 · border 170 · fascia 165)"
    assert t.schedule["Face screws"] == "Cap-Tor xd color-matched ONLY at: fascia 2 at each board end then alternate top/bottom every 12\", pre-drilled"


def test_face_screwed_field_with_a_cortex_border_counts_each_screw_once():
    var = {b: _takeoff(_variant("Terrain", "Brown Oak", "Cap-Tor xd face screw", border=b, hardie=False, profile="square")) for b in ("Cortex", None)}
    for t in var.values():
        assert all(_lead(l.why) >= 0 for l in t.lines if l.category == "Fasteners")
        assert _cap_tor(t)[0] is None                                       # the face-screwed field takes every face screw itself
    field = {b: _lines(t, "face screwed field")[0] for b, t in var.items()}
    (cl,) = _lines(var["Cortex"], "plugs — picture frame, dividers and stair treads")
    b_, s_ = map(int, re.search(r"border/divider (\d+) · stairs (\d+)", cl.why).groups())
    assert b_ > 0 and s_ > 0 and _lead(cl.why) == b_ + s_
    assert _lead(field["Cortex"].why) == _lead(field[None].why) - b_ - s_  # the Cortex border's screws come off the field, not twice
    for f_ in field.values():
        assert f_.order == math.ceil(_lead(f_.why) / 350)


@pytest.mark.parametrize("path", JOBS, ids=[p.stem for p in JOBS])
def test_every_needed_total_is_its_parts(path):
    t = _takeoff(json.loads(path.read_text()))
    for l in t.lines:
        if l.category != "Fasteners":
            continue
        found = NEEDED.findall(l.why)                                       # a composite lists each part's line: "Lower level: ... + Upper level: ..."
        for tot, parts in found:
            nums = [int(p_.rsplit(" ", 1)[1]) for p_ in parts.split(" · ")]
            assert int(tot) == sum(nums) and all(n_ > 0 for n_ in nums), (l.item, l.why)
        if len(found) == 1 and "Cap-Tor" in l.item:
            assert l.order == math.ceil(int(found[0][0]) / 350), (l.item, l.why)
        assert not re.search(r"(^|\s)-\d", l.why), (l.item, l.why)
    if t.spec.extras.hardie_skirt:
        assert not [l for l in _lines(t, TOPLOC) if "step-face skirt" not in l.item], path.stem
    fs = t.schedule.get("Face screws")
    if fs:
        assert "·  ·" not in fs and not fs.rstrip().endswith(("·", ":")), fs
        assert all(p_.strip() for p_ in fs.split("||")[0].split(": ", 1)[1].split(" · ")), fs
        if not t.spec.geometry.parts:                                       # one deck: the schedule names exactly the Cap-Tor line's parts
            _, _, parts = _cap_tor(t)
            assert {k_ for k_, r_ in RULES.items() if r_ in fs} == set(parts), (fs, parts)


# ------------------------------------------------------------------ B2: the box steps' skirts
@pytest.fixture(scope="module")
def prentice():
    t = _takeoff(PRENTICE)
    return t, build_scene(t.layout)


def _scene_skirts(sc, side):
    return [b for b in sc.boxes if b.kind == "fascia" and (b.tag or "") == f"stair skirt {side}"]


def test_mitered_box_steps_order_only_the_skirts_the_scene_keeps(prentice):
    t, sc = prentice
    assert {s_: m_[0] for s_, m_ in box_step_miters(t.spec, t.layout.stairs).items()} == {"edge:2": 1, "edge:3": 1}
    cuts = _skirt_cuts(t)
    for st, ss in zip(t.layout.stairs, t.spec.stairs):
        mine = [c for c in cuts if c.member.startswith(f"Stair skirt ({ss.name},")]
        (fg,) = st.geo.flights
        assert len(_scene_skirts(sc, st.side)) == len(mine) * fg.treads, st.side     # the scene: one skirt box per side under each tread
        if st.side in BOX_SIDES:
            assert len(mine) == 1 and mine[0].member.endswith("free end)"), [c.member for c in mine]
        else:
            assert len(mine) == 2 and not [c for c in mine if "free end" in c.member]
    (fl,) = [l for l in t.lines if l.category == "Fascia" and l.item.startswith("Deck fascia")]
    assert fl.why.count("stair skirt (") == len(cuts) == 4                  # the order lists the same pieces as the cut list (was 6)


def test_mitered_pvc_skirts_take_no_toploc_screws(monkeypatch):
    job = _variant("Vintage", "Coastline", "CONCEALoc", border=None, hardie=False)
    t1 = _takeoff(job)
    mit = box_step_miters(t1.spec, t1.layout.stairs)
    ends = {ss.name: mit.get(st.side, (0, 0.0))[0] for st, ss in zip(t1.layout.stairs, t1.spec.stairs)}       # mitered ends per stair
    monkeypatch.setattr(scene_mod, "box_step_miters", lambda spec, stairs: {})     # the takeoff as it was: blind to the miter
    t0 = _takeoff(job)
    gone = [c for nm, m_ in ends.items() for c in [c_ for c_ in _skirt_cuts(t0) if c_.member.startswith(f"Stair skirt ({nm},")][:m_]]
    assert len(gone) == 2 and len(_skirt_cuts(t1)) == len(_skirt_cuts(t0)) - len(gone) == 4      # one corner skirt off each box step
    per = sum(4 + max(0, math.ceil(c.length_in / 12) - 1) for c in gone)     # 2 at each end + every 12", per dropped corner skirt
    assert _lead(_lines(t0, TOPLOC)[0].why) - _lead(_lines(t1, TOPLOC)[0].why) == per > 0


def test_a_box_step_mitered_at_both_ends_has_no_skirt():
    job = copy.deepcopy(PRENTICE)
    st1 = copy.deepcopy(job["stairs"][2]); st1.update(side="edge:1", width_in=68, position_in=0, name="Test step side 1")
    job["stairs"].append(st1)                                               # box steps on sides 1, 2 and 3: side 2 mitered at both ends
    t = _takeoff(job)
    assert {s_: m_[0] for s_, m_ in box_step_miters(t.spec, t.layout.stairs).items()} == {"edge:1": 1, "edge:2": 2, "edge:3": 1}
    sc = build_scene(t.layout)
    names = Counter(c.member for c in _skirt_cuts(t))
    for st, ss in zip(t.layout.stairs, t.spec.stairs):
        n_ = sum(v_ for k_, v_ in names.items() if k_.startswith(f"Stair skirt ({ss.name},"))
        assert len(_scene_skirts(sc, st.side)) == n_ * st.geo.treads, (st.side, names)
    assert not [k_ for k_ in names if job["stairs"][1]["name"] in k_]          # the left-side step: no exposed end, no skirt


def test_box_step_short_of_the_corner_keeps_both_skirts():
    job = copy.deepcopy(PRENTICE)
    job["stairs"][1]["width_in"] = 60                                       # the left-side step ends 13" short of the corner: no miter
    t = _takeoff(job)
    assert box_step_miters(t.spec, t.layout.stairs) == {}
    for ss in job["stairs"][1:]:
        mine = [c for c in _skirt_cuts(t) if c.member.startswith(f"Stair skirt ({ss['name']},")]
        assert len(mine) == 2 and not [c for c in mine if "free end" in c.member], ss["name"]


# ------------------------------------------------------------------ B2: two stairs on one side, one of them the mitered box step
def _skirt_len(st):
    """A stair's stepped skirt piece: one side of every tread of its flight, 1" past the nose."""
    return round(st.geo.treads * st.geo.tread_in + 1.0, 1)


def _side_cuts(t, what, side):
    """The cut pieces `what` ("Stair skirt", "Stair treads") off one outline side, whichever stair listed there they read by."""
    return [c for c in t.cut_list if c.member.startswith(tuple(f"{what} ({ss.name}{d_}" for ss in t.spec.stairs if ss.side == side for d_ in ",)"))]


def _side_skirts(t, side):
    """{piece length: (pieces, "free end" pieces)} of the skirts off one side. The takeoff names the pieces off a side after the
    first stair listed there, so the stairs on a shared side tell apart by their skirt's length (their tread count)."""
    out = {}
    for c in _side_cuts(t, "Stair skirt", side):
        n_, f_ = out.get(c.length_in, (0, 0))
        out[c.length_in] = (n_ + 1, f_ + ("free end" in c.member))
    return out


def _wrap_job(pvc=False):
    """Prentice with its box steps moved to wrap the inside 5/6 corner (54" on side 5, 40" on side 6) beside the center stair, narrowed
    to 48" to fit side 6 past the box step: a skirted stringer stair on the side of a mitered box step."""
    j = copy.deepcopy(PRENTICE)
    cs, box = j["stairs"][0], j["stairs"][1]
    j["stairs"] = [dict(cs, width_in=48, position_in=44), dict(box, side="edge:5", width_in=54, position_in=0, name="Test box step side 5"),
                   dict(box, side="edge:6", width_in=40, position_in=0, name="Test box step side 6")]
    return _variant("Vintage", "Coastline", "CONCEALoc", border=None, hardie=False, job=j) if pvc else j


def test_a_stringer_stair_beside_a_mitered_box_step_keeps_both_skirts():
    t = _takeoff(_wrap_job())
    cs, b5, b6 = t.layout.stairs
    assert (cs.build, cs.geo.treads, b6.geo.treads) == ("stringers", 2, 1)
    assert {s_: m_[0] for s_, m_ in box_step_miters(t.spec, t.layout.stairs).items()} == {"edge:5": 1, "edge:6": 1}
    assert _side_skirts(t, "edge:6") == {_skirt_len(cs): (2, 0), _skirt_len(b6): (1, 1)}       # the stair's two skirts, the box step's free end
    assert _side_skirts(t, "edge:5") == {_skirt_len(b5): (1, 1)}
    sc = build_scene(t.layout)
    assert len(_scene_skirts(sc, "edge:6")) == 2 * cs.geo.treads + b6.geo.treads == 5          # the scene: both sides of each stair tread + 1
    assert len(_scene_skirts(sc, "edge:5")) == b5.geo.treads
    # only the box step's treads run long to the miter; the stair's are cut square at its 48" width
    assert {c.length_in: "mitered at the corner" in c.note for c in _side_cuts(t, "Stair treads", "edge:6")} == {48: False, 40: True}


def test_a_stringer_stair_beside_a_mitered_box_step_keeps_its_toploc_screws(monkeypatch):
    t1 = _takeoff(_wrap_job(pvc=True))
    monkeypatch.setattr(scene_mod, "box_step_miters", lambda spec, stairs: {})     # the takeoff blind to the miter: every skirt
    t0 = _takeoff(_wrap_job(pvc=True))
    per = lambda st: 4 + max(0, math.ceil((st.geo.treads * st.geo.tread_in + 1.0) / 12) - 1)     # 2 at each end + every 12"
    gone = [st for st in t1.layout.stairs if st.build == "box"]                  # each box step's corner skirt, none of the stair's
    assert len(gone) == 2 and _lead(_lines(t0, TOPLOC)[0].why) - _lead(_lines(t1, TOPLOC)[0].why) == sum(per(st) for st in gone) == 10


@pytest.mark.parametrize("corner_last", [True, False], ids=["corner-step-listed-last", "corner-step-listed-first"])
def test_two_box_steps_on_a_side_only_the_one_the_scene_miters_loses_a_skirt(corner_last):
    """Side 3 split into a 30" box step at the 2/3 corner and a 28" one at its far end (two treads, so its skirts run longer). The
    scene (and box_step_miters) read the last box step listed on a side: the corner step miters into the left-side step only when
    it is listed last; listed first, the far step is the one read, short of the corner, and nothing miters."""
    j = copy.deepcopy(PRENTICE)
    box = j["stairs"][2]
    near = dict(box, width_in=30, position_in=0, name="Test corner box step side 3")
    far = dict(box, width_in=28, position_in=40, total_rise_in=21, name="Test far box step side 3")
    j["stairs"] = j["stairs"][:2] + ([far, near] if corner_last else [near, far])
    t = _takeoff(j)
    st_ = {ss.name: st for st, ss in zip(t.layout.stairs, t.spec.stairs)}
    n_, f_, lb = st_[near["name"]], st_[far["name"]], st_[j["stairs"][1]["name"]]
    assert (n_.geo.treads, f_.geo.treads) == (1, 2)
    m = int(corner_last)                                                    # mitered ends: one on the corner step, one on the left-side step
    assert {s_: v_[0] for s_, v_ in box_step_miters(t.spec, t.layout.stairs).items()} == ({"edge:2": 1, "edge:3": 1} if m else {})
    assert _side_skirts(t, "edge:3") == {_skirt_len(f_): (2, 0), _skirt_len(n_): (2 - m, m)}   # the far step keeps both skirts either way
    assert _side_skirts(t, "edge:2") == {_skirt_len(lb): (2 - m, m)}
    sc = build_scene(t.layout)
    assert len(_scene_skirts(sc, "edge:3")) == 2 * f_.geo.treads + (2 - m) * n_.geo.treads
    assert len(_scene_skirts(sc, "edge:2")) == (2 - m) * lb.geo.treads
    assert {c.length_in: "mitered at the corner" in c.note for c in _side_cuts(t, "Stair treads", "edge:3")} == {30: bool(m), 28: False}
