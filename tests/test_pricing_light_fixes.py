"""The lights in the price, on the Prentice job (free riser lights, lights.riser_pick): free riser lights with a set price per light
(the count, the note, the allocation, the lighting option), options at the job margin, the drink-rail sums (not the accent light
"just below the drink rail"), and options against the gift: riser lights an option adds pay their way (at the option margin, or
sell_each a light) as if there were no gift; an option that changes only the post lights is the two quotes' difference."""
import copy
import json
from pathlib import Path

from decktakeoff import run, lighting
from decktakeoff.pricing import _deep_merge, _factor_rate, drink_rail_line, gift_excess, option_delta
from decktakeoff.spec import DeckSpec

from test_lighting import TWO

ROOT = Path(__file__).resolve().parent.parent
JOB = json.loads((ROOT / "jobs" / "prentice_centennial.json").read_text())
PICK = dict(JOB["extras"]["lights"]["riser_pick"], **{"edge:3": "all"})        # + the 2 risers of the front-angle box step
POSTS = [("no post lights", {"post_cap": False}), ("every other post", {"every": 2})]
ADDS = [("+2 riser lights", {"riser_pick": PICK}, 2), ("2 lights per riser", {"per_riser": 2}, 5)]     # (name, change, riser lights added)


def _spec(lights=None, railing=None, **extras):
    d = copy.deepcopy(JOB)
    d["extras"]["lights"] = dict(d["extras"]["lights"], **(lights or {}))
    d["railing"].update(railing or {})
    d["extras"].update(extras)
    return DeckSpec.from_dict(d)


def _alloc(p, word):
    return [(k, v) for k, v in p.allocation if word in k]


def _options(changes, lights=None, **extras):
    """Each lights change as an extras.option on the job (price_options): the OptionPrice list."""
    opts = [{"name": c[0], "changes": {"extras": {"lights": c[1]}}} for c in changes]
    return run(_spec(lights=lights, options=opts, **extras))[2].options


def _quotes(change, lights=None, **extras):
    """(the job's quote, the quote of the job with the lights change) — what the proposal's option blocks take."""
    l0 = dict(JOB["extras"]["lights"], **(lights or {}))
    return run(_spec(lights=l0, **extras))[2], run(_spec(lights=_deep_merge(l0, change), **extras))[2]


def test_free_riser_lights_with_sell_each_charge_only_the_post_lights():
    spec = _spec(lights={"sell_each": 250})
    t, _, p = run(spec)
    pl = t.lighting
    assert pl.n_riser == 5 and pl.n_cap == 9 and p.light_sell == 250 * 9
    # the note counts the lights charged
    assert "9 lights at $250 installed ($2,250; " in p.rail_note and "14 lights" not in p.rail_note
    # the riser lights read once: on the $0 line, not in the paid label
    risers = _alloc(p, "riser lights")
    assert len(risers) == 1 and risers[0][1] == 0 and risers[0][0].endswith("included at no charge")
    assert sum(v for _, v in p.allocation) == p.sell
    # the lighting option sells what the job charges for the lights
    a = lighting.option_price(spec)
    assert a["check"] == p.light_sell == 2250 and a["fixtures"] == 14 and a["financed"] > a["check"]
    # the note's cost is the charged lights' own; the free riser lights' on their own
    assert lighting.paid_lights(pl) == 9 and 0 < p.light_free < p.light_work
    assert f"their cost ${p.light_work - p.light_free:,.0f}," in p.rail_note and f"5 riser lights free (their cost ${p.light_free:,.0f})" in p.rail_note
    assert dict(p.allocation)[lighting.short_words(pl, risers=False)] == 250 * 9
    # without the gift every light is charged, as before
    t2, _, p2 = run(_spec(lights={"sell_each": 250, "riser_free": False}))
    assert p2.light_sell == 250 * 14 and p2.light_free == 0 and "14 lights at $250" in p2.rail_note
    assert lighting.option_price(_spec(lights={"riser_free": False}), sell_each=250)["check"] == 250 * 14


def test_free_riser_lights_alone_read_as_before():
    t, _, p = run(_spec())
    assert p.light_sell == 0 and p.rail_note == f"5 riser lights free (their cost ${p.light_work:,.0f})"
    assert [k for k, _ in _alloc(p, "Lighting — ")] == ["Lighting — 9 post-cap lights, LED, warm white, on a transformer with a photocell and timer"]
    # risers only, free: one $0 line names them (no $0 "Lighting — 5 riser lights" line beside it)
    for lights in ({"post_cap": False}, {"post_cap": False, "sell_each": 250}):
        p1 = run(_spec(lights=lights))[2]
        assert len(_alloc(p1, "riser lights")) == 1 and not _alloc(p1, "Lighting — ") and sum(v for _, v in p1.allocation) == p1.sell
    assert p.light_free == p.light_work > 0
    # the gift, as the settings that light only it on an option's deck: the job's own risers, its riser light at its price
    g = p.light_gift
    assert g["riser_pick"] == {"Center stair": [1, 2, 3], "Left box step — left side": [1, 2]} and g["per_riser"] == 1
    assert g["riser_sku"] == "AZTDLRECRISERMW" and g["prices"] == {"AZTDLRECRISERMW": lighting.product(t.lighting.cfg, "AZTDLRECRISERMW")["each"]}
    assert gift_excess(p, p) == (0.0, 0.0) and run(_spec(lights={"riser_free": False}))[2].light_gift is None


def test_the_gift_names_stairs_that_share_a_name_by_side():
    cfg = dict(lighting.DEFAULTS, riser_free=True)
    pl = lighting.LightPlan(cfg, [], 5, 0, 0, 2.0, 3.0, [], [], 0.0, 0, (0.0, 0.0), 0,
                            risers_lit=[("front:A", "Stair at the front", [1, 2]), ("front:B", "Stair at the front", [1, 2]),
                                        ("left", "Back stair", [3]), ("right", "Back stair", []), ("edge:4", "Side stair", [1])])
    assert lighting.gift_of(pl)["riser_pick"] == {"front:A": [1, 2], "front:B": [1, 2], "left": [3], "Side stair": [1]}
    assert lighting.gift_of(lighting.LightPlan(dict(cfg, riser_free=False), [], 5, 0, 0, 2.0, 3.0, [], [], 0.0, 0, (0.0, 0.0), 0)) is None


def test_options_price_at_the_job_margin_with_free_riser_lights():
    fixed = [{"name": "a fixed $1,000 item", "cost": 1000.0}]
    p = run(_spec(options=fixed))[2]
    assert p.gm < p.gm_job == 0.30 and p.options_gm == p.gm_job               # the blend the free lights make stays the job's
    assert p.options[0].check == round(1000 / 0.70) == 1429
    assert run(_spec(lights={"riser_free": False}, options=fixed))[2].options[0].check == 1429
    for lights, extras in (({"sell_each": 250}, {}), ({}, {"drink_rail_sell": 2500})):
        q = run(_spec(lights=lights, options=fixed, **extras))[2]
        assert q.gm != q.gm_job and q.options_gm == q.gm_job and q.options[0].check == 1429


def test_options_margin_unchanged_without_the_lights_or_drink_rail_at_a_set_price():
    for job in ("deck_16x14_seasalt", "deck_20x20_castlerock", "deck_10x10"):      # a rail sold per LF (blended), and a plain deck
        p = run(DeckSpec.from_dict(json.loads((ROOT / "jobs" / f"{job}.json").read_text())))[2]
        assert p.options_gm == p.gm
        assert p.light_gift is None and p.light_free == 0


def test_drink_rail_sums_leave_out_the_accent_light():
    over = {"drink_rail_mount": "over"}
    on, off = {"post_light": None}, {"post_light": None, "post_cap": False}     # accent lights on the posts / none (riser lights stay)
    t, _, p = run(_spec(lights=on, railing=over))
    acc = next(l for l in t.lines if l.category == "Lighting" and "AZTIXLEDACCB" == l.sku)
    assert t.lighting.post_kind == "accent" and "drink rail" in acc.item and not drink_rail_line(acc)
    assert {l.category for l in t.lines if drink_rail_line(l)} == {"Rail"} and any(l.item.startswith("Drink rail") for l in t.lines if drink_rail_line(l))
    # the drink rail and the railing in "what the price includes" don't move with the post lights (within the $1 the owner's fixed
    # labor cut moves as it spreads over every labor line, the lights' included)
    p0 = run(_spec(lights=off, railing=over))[2]
    for word in ("drink rail", "Railing"):
        a_, b_ = _alloc(p, word), _alloc(p0, word)
        assert [k for k, _ in a_] == [k for k, _ in b_] and all(abs(x[1] - y[1]) <= 1 for x, y in zip(a_, b_)), word
    # at the owner's drink-rail price: its cost is its own, and the accent lights stay in the price at the margin
    pd, pd0 = run(_spec(lights=on, railing=over, drink_rail_sell=2500))[2], run(_spec(lights=off, railing=over, drink_rail_sell=2500))[2]
    cost = lambda q: q.rail_note.split("drink rail at $2,500 installed (its cost ")[1].split(",")[0]
    assert cost(pd) == cost(pd0)
    assert abs((pd.sell - pd0.sell) - (p.sell - p0.sell)) <= 1
    assert sum(v for _, v in pd.allocation) == pd.sell and dict(pd.allocation)[next(k for k, _ in _alloc(pd, "drink rail"))] == 2500


def test_post_light_options_on_free_riser_lights_are_the_two_quotes_difference():
    """Fewer post lights put the transformer and the home runs on the free riser lights (light_free rises, no riser light is
    added): the option is still the difference of the two quotes — the post lights at what "what the price includes" lists."""
    for lights in ({}, {"sell_each": 250}):
        for (name, change), o in zip(POSTS, _options(POSTS, lights)):
            p0, p1 = _quotes(change, lights)
            assert gift_excess(p0, p1) == (0.0, 0.0), name
            assert option_delta(p0, p1)[0] == p1.sell - p0.sell < 0 and o.check == p1.sell - p0.sell, name
            assert option_delta(p0, p1)[1:] == (p1.retail - p0.retail, p1.monthly - p0.monthly), name
    p0, p1 = _quotes({"post_cap": False})
    assert p1.light_free > p0.light_free and abs(option_delta(p0, p1)[0] + _alloc(p0, "post-cap lights")[0][1]) <= 10
    p0, p1 = _quotes({"post_cap": False}, {"sell_each": 250})
    assert abs(option_delta(p0, p1)[0] + 250 * 9) <= 10                               # the 9 post lights at $250
    # the two-level deck (a composite), through the proposal's option blocks
    lit = copy.deepcopy(TWO)
    for lights, want in (({"riser_free": True}, None), ({"riser_free": True, "sell_each": 250}, [-250 * 16, -250 * 8])):
        lit["extras"]["lights"] = dict({"riser": True, "post_cap": True}, **lights)
        p0, got = run(DeckSpec.from_dict(lit))[2], []
        for name, change in POSTS:
            d = copy.deepcopy(lit)
            d["extras"]["lights"].update(change)
            p1 = run(DeckSpec.from_dict(d))[2]
            assert p1.light_free >= p0.light_free and option_delta(p0, p1)[0] == p1.sell - p0.sell < 0, name
            got.append(option_delta(p0, p1)[0])
        assert want is None or got == want


def test_riser_lights_an_option_adds_price_as_without_the_gift():
    for lights in ({}, {"sell_each": 250}, {"sell_each": 150}):
        gift, paid = _options(ADDS, lights), _options(ADDS, dict(lights, riser_free=False))
        assert [(o.check, o.financed) for o in gift] == [(o.check, o.financed) for o in paid], lights      # price_options
        for (name, change, n), o in zip(ADDS, gift):
            p0, p1 = _quotes(change, lights)
            assert p1.light_free > p0.light_free and abs(p1.sell - p0.sell) <= 5, name   # the gift alone would give them away
            c, f, m = option_delta(p0, p1)                                              # the proposal's option blocks
            q0, q1 = _quotes(change, dict(lights, riser_free=False))
            assert abs(c - o.check) <= 1 and abs(c - option_delta(q0, q1)[0]) <= 1 and abs(f - o.financed) <= 2 and abs(f - (q1.retail - q0.retail)) <= 2 and m > 0, name
            xs, xw = gift_excess(p0, p1)
            if lights:                                                                  # sell_each a light
                assert (xs, xw) == (lights["sell_each"] * n, 0.0) and abs(c - lights["sell_each"] * n) <= 5, name
            else:                                                                       # their work at the option margin
                assert xs == 0 and abs(xw - o.cost) <= 0.01 * xw and abs(c - round(o.cost / 0.70)) <= 1, name
    # on a deck sold per SF: the same prices, from the cost math
    plain = [o.check for o in _options(ADDS)]
    assert [o.check for o in _options(ADDS, sell_per_sf=110)] == plain
    p0, p1 = _quotes(ADDS[0][1], sell_per_sf=110)
    assert p1.sell == p0.sell and option_delta(p0, p1)[0] == plain[0]
    # financed the way the job's price gets it (extras.retail_markup), as without the gift
    p0, p1 = _quotes(ADDS[0][1], retail_markup=0.10)
    q0, q1 = _quotes(ADDS[0][1], {"riser_free": False}, retail_markup=0.10)
    c, f, m = option_delta(p0, p1)
    cq, fq, mq = option_delta(q0, q1)                                                # each side rounds its own prices: within $1
    assert abs(c - cq) <= 1 and abs(c - plain[0]) <= 1 and f == round((p0.sell + c) * 1.10) - p0.retail and abs(f - fq) <= 1 and abs(m - mq) < 0.05


def test_an_option_prices_as_its_parts():
    """Riser lights added and post lights taken out in one option: the parts' sum. Fewer free riser lights: no credit. A pricier
    riser light: charged, as without the gift (with a set price per light, the same price)."""
    both = [("+2 riser lights, no post lights", dict(ADDS[0][1], post_cap=False)), ("+2 riser lights, every other post", dict(ADDS[0][1], every=2))]
    t0, _, p0 = run(_spec())
    # the order buys whole bags of connectors: two options can need one bag fewer together than apart (one bag at the option margin)
    bag = lighting.product(t0.lighting.cfg, t0.lighting.cfg["connector_sku"])["each"] * p0.material_factor * (1 + p0.tax_rate) / (1 - p0.options_gm) + 1
    for lights in ({}, {"sell_each": 250}):
        add, none, other = (o.check for o in _options([ADDS[0]] + POSTS, lights))
        c1, c2 = (o.check for o in _options(both, lights))
        assert abs(c1 - (add + none)) <= bag and abs(c2 - (add + other)) <= bag, lights
        for (name, change), c in zip(both, (c1, c2)):
            assert abs(option_delta(*_quotes(change, lights))[0] - c) <= 1, name
    less = [("no riser lights", {"riser": False}), ("riser lights on the center stair only", {"riser_pick": {"edge:2": False}})]
    for o, o_paid in zip(_options(less), _options(less, {"riser_free": False})):
        assert abs(o.check) <= 5 and o_paid.check < -250, o.name                       # the gift taken back is no credit
    pricier = [("a pricier riser light", {"prices": {"AZTDLRECRISERMW": 125.0}})]
    o, o_paid = _options(pricier)[0], _options(pricier, {"riser_free": False})[0]
    factor, rate = _factor_rate(_spec())
    each = lighting.product(dict(lighting.DEFAULTS), "AZTDLRECRISERMW")["each"]
    assert abs(o.cost - 5 * (125.0 - each) * factor * (1 + rate)) < 0.01 and o.check == o_paid.check == round(o.cost / 0.70)
    assert [(o.check, o.financed) for o in _options(pricier, {"sell_each": 250})] == [(0, 0)]


def test_lighting_option_and_stair_addon_with_free_riser_lights():
    """The job's own lights keep their gift (the lighting option is the post lights at the margin); the yard stair's riser
    lights are not the base deck's, so the add-on is the same as without the gift — at the margin, or sell_each a light."""
    p = run(_spec())[2]
    a = lighting.option_price(_spec())
    assert a["free_work"] == round(p.light_free, 2) and abs(a["check"] - (a["cost"] - a["free_work"]) / 0.70) <= 15
    d = copy.deepcopy(TWO)
    d["geometry"]["parts"][0]["stairs"] = [{"side": "front:B", "width_in": 48, "position_in": 96, "total_rise_in": 96, "landing": "grade",
                                            "rails": 2, "name": "Stair to the yard"}]
    base, stair = DeckSpec.from_dict(TWO), DeckSpec.from_dict(d)
    for cfg in ({}, {"sell_each": 200}):
        plain, free = lighting.stair_addon(base, stair, **cfg), lighting.stair_addon(base, stair, riser_free=True, **cfg)
        assert free["risers"] == plain["risers"] == 13 and free["caps"] == plain["caps"] == 6, cfg
        assert abs(free["check"] - plain["check"]) <= 1 and abs(free["financed"] - plain["financed"]) <= 1 and free["financed"] > free["check"], cfg
        assert free["with_stair"]["free_work"] > free["base"]["free_work"] > 0       # the base deck's riser lights still ride the gift
        assert free["base"]["check"] < plain["base"]["check"]
    assert lighting.stair_addon(base, stair, riser_free=True, sell_each=200)["check"] == 200 * 19 == 3800
    # the yard stair's risers left dark (riser_pick): only its post lights are added
    only = {"riser_pick": {"Stair between the levels": "all"}}
    plain, free = lighting.stair_addon(base, stair, **only), lighting.stair_addon(base, stair, riser_free=True, **only)
    assert free["risers"] == 0 and abs(free["check"] - plain["check"]) <= 1 and plain["check"] > 0      # each rounds its own quote
