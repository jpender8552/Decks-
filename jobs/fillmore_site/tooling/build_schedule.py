"""7303 S Fillmore Cir — schedule model (research helper; writes ../schedule.json and prints markdown tables).

Two clocks:
  * pre-construction in BUSINESS DAYS from signing (bd 0 = the signing day), and
  * construction in WORKING DAYS (day 1 = first crew day on site), half-day resolution.
One 4-person GSX crew is the single resource: crew tasks run in list order, each starting at
max(previous crew task end, its predecessors' ends). Inspections, the electrician and the roof dealer
are other resources; a "hold" blocks the crew. Weather float is added per month from NOAA normals.

Run:  python3 build_schedule.py            (prints tables, writes ../schedule.json)
"""
import json, math, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "schedule.json"

# ----------------------------------------------------------------------------------------------
# Counts (engine run of the stairs agent's t0.json, 27 Oct 2026; lighting.md §4)
COUNTS = dict(deck_sf=729.2, piers="8 caissons 24\" x 42\" (owner 27 Oct: fewer columns, larger caissons; the roof version 9, 30\" under the upper level)", columns="8", beam_pieces=5, joists=73,
              ledger_runs=4, rail_lf=111.6, rail_posts=23, cortex_base=3710, cortex_yard=350, inset_risers=5, yard_risers=10,
              fascia_boards=13, lights_base=28, lights_yard=22, brick_columns="~10", slab_openings=3)
PLUG_RATE = 180      # plugged Cortex screws per installer-hour, all-in (E; see schedule.md §3.3)

# ----------------------------------------------------------------------------------------------
# Construction tasks, in crew order.  opt: base | opt1 (lighting) | opt2 (yard stair) | opt12 (lights on the
# yard stair, only with 1+2) | opt3 (louvered roof) | opt3a (roof screens).  kind: crew | hold | insp | elec | dealer
# dur in working days.  after = predecessors (ids).  cust = customer label (None = not shown to the customer).
T = [
 # id            opt     kind    dur   after                         internal label / basis                                                                 cust
 ("demo",        "base", "crew", 3.00, [],                           "Mobilize, protect patio/beds; tear-off decking, rail, the stair; framing down; brick columns down; haul-off (2 roll-offs)",
                                                                                                                                                              "Protection; old deck, stair and brick columns out; haul-off"),
 ("slab_ftg",    "base", "crew", 1.00, ["demo"],                     "Saw-cut/core 3 openings in the patio slab for the upper caissons (4 with the roof); the old brick-column footings per the owner's plan",
                                                                                                                                                              None),
 ("piers",       "base", "crew", 1.00, ["slab_ftg"],                     "Layout (string lines, laser); auger 8 caisson holes 24\" x 42\" (track auger through the side gate; spoils hauled); Sonotubes + cages set",
                                                                                                                                                              "Layout; the caisson holes drilled"),
 ("piers_y",     "opt2", "crew", 0.25, ["piers"],                    "+4 caisson holes 12\" x 42\" for the yard-stair landing (same rig)", "4 caissons for the stair landing"),
 ("insp_ftg",    "base", "insp", 0.25, ["piers", "piers_y"],         "FOOTING inspection of the open caisson holes + cages before the pour: City (request by 3:30 pm -> next business-day a.m.) and, per Centennial R109.1.1, the PE's observation + stamped report [C]", None),
 ("ledgers",     "base", "crew", 1.00, ["piers", "piers_y"],         "4 ledger runs (B, arm door wall, C band above the veneer, D): siding strip, membrane + Z-flashing, LedgerLOK, 8 DTT2Z from inside (runs while the footing inspection happens)",
                                                                                                                                                              "Ledgers flashed and fastened"),
 ("pour",        "base", "crew", 0.50, ["insp_ftg", "ledgers"],      "Pour the caissons, nothing wet-set (the ABU88RZ bases go on after the cure); flush with the slab on the patio, 7\" up in the beds", "Caissons poured"),
 ("cure",        "base", "cure", 2.00, ["pour"],                     "Caisson cure: 2 days before the columns load them", None),
 ("posts_beams", "base", "crew", 1.75, ["ledgers", "cure"],      "8 rough 8x8 DF columns on ABU88RZ bases set on the cured caissons ((2) 5/8\" Titen HD each), cut to elevation; 5 beam pieces 6x10 DF (L1 x2 spliced, A2, U1 x2 spliced) lifted onto CCQ/ECCQ caps",
                                                                                                                                                              "8x8 Douglas fir columns; 6x10 Douglas fir beams"),
 ("roof_gsx",    "opt3", "crew", 0.25, ["posts_beams"],              "Solid blocking + uplift ties (H2.5AZ/CS16) at the 2 roof-post bases; the roof version's own structure — U1 on 4 columns with 30\" caissons, drilled and poured with the deck's", None),
 ("framing",     "base", "crew", 3.50, ["posts_beams", "roof_gsx"],  "~73 2x10 TrueFrame joists @12\" (LUS210Z, H2.5AZ on the beams), double rims, blocking @4' + picture-frame/breaker blocking, joist tape, inset-stair notch, arm A over beam A2, rail-post blocking",
                                                                                                                                                              "Frame both levels: 2x10 joists at 12\", joist tape, the stair opening"),
 ("landing_y",   "opt2", "crew", 0.50, ["framing"],                  "Yard stair: 4 landing posts + 9'x4' landing frame", "Stair landing framed"),
 ("light_rough", "opt1", "crew", 0.25, ["framing"],                  "Lighting rough-in: 12/2 through the blocking to every post + home run to the transformer spot", None),
 ("roof_elec1",  "opt3", "elec", 0.50, ["framing"],                  "Electrician: circuit for the roof motor to the house-side attachment (rough), electrical permit", None),
 ("insp_frame",  "base", "hold", 0.50, ["framing", "landing_y", "light_rough"], "FRAMING inspection (ledger, flashing, hangers, caps, lateral ties, notch, landing). Next-day a.m.; crew holds ~1/2 day", None),
 ("fascia",      "base", "crew", 1.25, ["insp_frame"],               "Vintage EW fascia 1/2x11-3/4 (13 x 12', TOPLoc, pre-drilled) + vertical-board step-face skirt on 2x4 furring",
                                                                                                                                                              "English Walnut fascia; the vertical-board face between the levels"),
 ("decking",     "base", "crew", 3.00, ["fascia"],                   "Vintage EW decking: picture frame + breakers first, field, rips; ~3,710 Cortex screws + plugs (~1 crew-day of it at 180/installer-hr x 3)",
                                                                                                                                                              "Vintage English Walnut decking: picture frame and breaker boards first, every screw plugged"),
 ("inset_stair", "base", "crew", 0.75, ["decking"],                  "Inset stair: 5 stringers, 4 treads, 5 risers, Cortex, waterfall skirts, graspable handrail",
                                                                                                                                                              "The stair between the levels"),
 ("flights_y",   "opt2", "crew", 1.25, ["decking", "landing_y"],     "Yard stair: two flights (10 risers), treads, risers, ~350 Cortex, waterfall skirts", "The stair to the yard: landing deck and two flights"),
 ("rail",        "base", "crew", 2.00, ["decking"],                  "IRX black: 23 posts (HeadLOK into blocking), 20 panels, drink-rail covers + clips, Vintage EW drink rail OVER the posts (posts cut level, inserts, seams on post centres, mitred corners)",
                                                                                                                                                              "Impression Rail Express, black, with the English Walnut drink rail"),
 ("rail_y",      "opt2", "crew", 0.75, ["rail", "flights_y"],        "Yard stair rail (both sides on the horseshoe, the yard side along the deck) + landing guard + graspable handrails", "Rail on the stair to the yard"),
 ("elec_outlet", "opt1", "elec", 0.50, ["insp_frame"],               "Electrician (by others): GFCI in-use outlet at the transformer spot, if none exists", None),
 ("light_trim",  "opt1", "crew", 0.75, ["rail", "inset_stair", "elec_outlet"], "Lighting: 23 post-side accent lights (drink rail is over the posts) + 5 riser lights, transformer (photocell/timer), splice, test at dusk",
                                                                                                                                                              "Low-voltage lighting: riser lights and post lights"),
 ("lights_y",    "opt12","crew", 0.50, ["light_trim", "rail_y"],     "Yard-stair lighting: 10 riser + 5-12 post lights, wire down the stringers", "Lights on the stair to the yard"),
 ("clean",       "base", "crew", 0.50, ["rail", "inset_stair"],      "Punch list, magnet sweep, final clean (end of construction)", "Final clean; end of construction"),
 ("insp_final",  "base", "insp", 0.25, ["clean"],                    "FINAL inspection (deck, stairs, guards, lights) — next business day; then HOA ACC close-out request", None),
]
ROOF = [  # opt3 / opt3a work after the deck (dealer + electrician + GSX return)
 ("roof_inst",   "opt3", "dealer", 2.00, "Suncoast dealer: 2 roof posts on the deck at the rail line, house attachment at soffit/roof line, 20'x10' frame, louvers, Gaposa motor, gutters/downspouts in the posts"),
 ("roof_elec2",  "opt3", "elec",   0.50, "Electrician: motor (and sensors) connected; electrical final"),
 ("gsx_return",  "opt3", "crew",   0.50, "GSX: IRX bays terminated into the 2 roof posts (wall-mount kits), cap-light swap if Option 1"),
 ("screens",     "opt3a","dealer", 1.00, "Dealer: motorized retractable screens — front 20', both 10' ends (tracks, housings, motors)"),
 ("scr_elec",    "opt3a","elec",   0.25, "Electrician: screen motors connected"),
 ("insp_roof",   "opt3", "insp",   0.25, "Roof FINAL (+ electrical final)"),
]

OPTS = {  # name -> set of option tags
    "Base": {"base"},
    "Base + Option 1 (lighting)": {"base", "opt1"},
    "Base + Option 2 (yard stair)": {"base", "opt2"},
    "Base + Options 1 + 2 (incl. yard-stair lights)": {"base", "opt1", "opt2", "opt12"},
    "Base + Option 3 (louvered roof)": {"base", "opt3"},
    "Base + Options 3 + 3a (roof + screens)": {"base", "opt3", "opt3a"},
    "Everything (1 + 2 + 3 + 3a)": {"base", "opt1", "opt2", "opt12", "opt3", "opt3a"},
}

def schedule(tags):
    """Forward pass with one crew. Returns rows with start/end in working days (0-based, fractional)."""
    rows, end, crew_free = [], {}, 0.0
    for tid, opt, kind, dur, after, label, cust in T:
        if opt not in tags:
            continue
        dep = max([end[a] for a in after if a in end] + [0.0])
        if kind == "crew":
            s = max(dep, crew_free); e = s + dur; crew_free = e
        elif kind == "hold":                       # crew waits for the inspector
            s = max(dep, crew_free); e = s + dur; crew_free = e
        elif kind == "insp":                       # next business-day a.m. window: starts at the next whole day
            s = math.ceil(dep - 1e-9); e = s + dur
        else:                                      # elec: another trade, any time after its predecessors
            s = dep; e = s + dur
        end[tid] = e
        rows.append(dict(id=tid, option=opt, kind=kind, start=round(s, 2), dur=dur, end=round(e, 2), after=[a for a in after if a in end],
                         label=label, customer=cust))
    return rows, crew_free

def day_span(s, e):
    """0-based fractional [s, e) -> 1-based whole working days covered."""
    a = int(math.floor(s + 1e-9)) + 1
    b = int(math.ceil(e - 1e-9))
    return a, max(a, b)

def span_txt(s, e):
    a, b = day_span(s, e)
    return f"Day {a}" if a == b else f"Days {a}–{b}"

# ----------------------------------------------------------------------------------------------
# Weather: NOAA NCEI 1991-2020 monthly normals.  P10 = days with precip >= 0.10" and T32 = days with max <= 32 F at
# DENVER CENTENNIAL AP (USW00093067, ~5.7 mi E of the site); S1 = days with snowfall >= 1.0" at DENVER-STAPLETON
# (USW00023062; KAPA has no snow normals).  Lost workdays/month = 5/7 x (P10*w + 0.5*T32 + 0.5*S1), w = 0.5 Jun-Aug
# (afternoon storms cost part days).  Float fraction = lost / workdays in the month.
P10 = {1: 1.4, 2: 1.9, 3: 2.6, 4: 4.6, 5: 5.1, 6: 3.9, 7: 4.8, 8: 4.1, 9: 2.9, 10: 3.0, 11: 2.0, 12: 1.0}
T32 = {1: 4.5, 2: 4.9, 3: 1.7, 4: 0.6, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0, 9: 0.0, 10: 0.7, 11: 2.3, 12: 6.0}
S1 = {1: 2.3, 2: 2.5, 3: 2.3, 4: 2.1, 5: 0.4, 6: 0.0, 7: 0.0, 8: 0.0, 9: 0.3, 10: 1.2, 11: 2.5, 12: 2.3}
WD = {1: 21, 2: 20, 3: 22, 4: 21, 5: 21, 6: 22, 7: 22, 8: 21, 9: 21, 10: 22, 11: 20, 12: 21}

def lost(m):
    w = 0.5 if m in (6, 7, 8) else 1.0
    return 5 / 7 * (P10[m] * w + 0.5 * T32[m] + 0.5 * S1[m])

FLOAT = {m: lost(m) / WD[m] for m in range(1, 13)}
WINTER_SLOW = 0.10   # Dec-Feb: ~9.4-10.7 h of daylight (sunrise 7:16 / sunset 4:38 on 21 Dec at the site), frost on the frame, stiff PVC (E)

# ----------------------------------------------------------------------------------------------
# Pre-construction (business days from signing).  Planning values; ranges in schedule.md.
PRE = [
 # id               bd_start bd_dur  after               label
 ("sign",            0,  0,  [],                 "Contract signed (deposit); HOA ACC request + drawings submitted the same week"),
 ("verify",          1,  1,  ["sign"],           "Field verification: deck heights, ledger bands, old column centres, slab edges, chimney nook; dig beside one old column per level to expose its footing (footings.md 7, 13); private-line locate"),
 ("hoa",             1, 15,  ["sign"],           "Tiffany HOA ACC review — submit >= 3 weeks before work; ACC allows up to 3 weeks"),
 ("eng",             2, 12,  ["verify"],         "Stamped engineering (6x10 DF beams outside IRC tables; 8x8 DF columns on 20\" caissons): GSX planning 2-3 weeks"),
 ("permit",         14, 10,  ["eng"],            "Centennial deck permit: intake + plan-review fee (~2 bd), review 5 bd after fee paid, issue (~1 bd), +2 bd buffer; a comment round adds up to 5 bd"),
 ("ord_timber",     14, 12,  ["eng"],            "Order 8x8 DF #1 rough + 6x10 DF (special order via D&D): 10-15 bd planning; release earlier on the engineer's preliminary sizes if possible"),
 ("ord_dp",         14, 12,  ["eng"],            "Order Simpson ABU88RZ bases + CCQ/ECCQ caps (rough W2 = 8\" is a Simpson special order) via D&D; Sonotubes, rebar, anchors, concrete from stock"),
 ("ord_vintage",    14,  8,  ["eng"],            "Order Vintage English Walnut deck boards/fascia/risers + Cortex EW plugs (stock at D&D Denver unconfirmed; ProDeck MN quotes <2 wk)"),
 ("ord_irx",        14,  8,  ["eng"],            "Order IRX black panels/posts (stock) + drink-rail panel covers (special order) + clip kits"),
 ("ord_light",      14,  8,  ["eng"],            "Option 1: order TimberTech lights/transformer (not on any D&D quote; retail stock is shallow)"),
 ("locates",        22,  3,  ["permit"],         "Colorado 811 locates (2-3 business days; marks good ~30 days)"),
]
START_BD = 25   # construction day 1 = business day 25 after signing (permit issued end of bd 24)
ROOF_ZONING_BD = 15     # Planning interpretation (LDC 12-14-805) "a reasonable period": planning value 3 weeks (E)
ROOF_MFG_BD = 35        # factory 7 weeks planning (6-10 wk benchmarks; Suncoast unpublished)

ROOF_PRE = [
 ("r_zoning",   1, 15, "Planning: written LDC 12-14-805 interpretation that the louvered roof is a 'pergola' (3 ft) not an attached roof (20 ft rear setback) — STOP until answered; variance path = P&Z hearing 6-10 wk"),
 ("r_measure",  3,  3, "Suncoast Denver (Cale Pilling) site visit + measure (soffit/roof line; deck side from GSX drawings)"),
 ("r_react",    6,  3, "Dealer sends post reactions (down/uplift, base shear) to the GSX engineer (deck limits ~2,900 lb down / 1,400 lb up per post)"),
 ("r_draw",     6, 10, "Dealer drawings + Colorado-PE stamped engineering (30 psf non-reducible + sliding snow, 115 mph, soffit/roof-line attachment)"),
 ("r_permit",  16, 10, "Separate Centennial patio-cover permit (zoning approval required; 5 bd review after fee) after the Planning answer"),
 ("r_mfg",     16, 35, "Factory: released on the Planning answer + deposit; 6-8 wk (Marygrove), 6-10 wk (Paragon), Suncoast unpublished -> 7 wk planning"),
]

# ----------------------------------------------------------------------------------------------
HOLIDAYS = {dt.date(2026, 11, 26), dt.date(2026, 11, 27), dt.date(2026, 12, 24), dt.date(2026, 12, 25), dt.date(2027, 1, 1),
            dt.date(2027, 1, 18), dt.date(2027, 2, 15), dt.date(2027, 5, 31), dt.date(2027, 7, 5), dt.date(2027, 9, 6)}

def add_bd(d0, n):
    d, k = d0, 0
    while k < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d not in HOLIDAYS:
            k += 1
    return d

def weather_days(start_date, crew_days, winter_thaw=True):
    """Float for crew_days of outdoor work starting start_date: sum of each day's month fraction, + 1 day ground thaw
    for the caissons in Dec-Feb (frozen ground thawed before drilling; blankets on the pour below 40 F)."""
    d, f, k = start_date, 0.0, 0
    while k < crew_days:
        if d.weekday() < 5 and d not in HOLIDAYS:
            f += FLOAT[d.month] + (WINTER_SLOW if d.month in (12, 1, 2) else 0.0); k += 1
        d += dt.timedelta(days=1)
    thaw = 1.0 if (winter_thaw and start_date.month in (12, 1, 2)) else 0.0
    return f, thaw

# ----------------------------------------------------------------------------------------------
# Customer view: crew rows merged into homeowner-readable groups (no permit / inspection / vendor words — docs/standards.md),
# whole working days, ending "end of construction" (no walk-through day).  x0/x1 = the skill Gantt's bar convention
# (column 0 = "Pre-con", Day d spans [d, d+1)), from the exact half-day plan.
GROUPS = [
 # group key  task ids                                         label (base)                                                                   option
 ("out",      ["demo", "slab_ftg"],                            "protection; old deck, stair and brick columns out; haul-off",                 "base"),
 ("piers",    ["piers", "piers_y", "pour"],           "layout; concrete caissons drilled and poured",                                 "base"),
 ("structure",["ledgers", "posts_beams", "roof_gsx"],          "ledgers flashed and fastened; 8x8 Douglas fir columns and 6x10 Douglas fir beams set", "base"),
 ("frame",    ["framing", "landing_y", "light_rough", "insp_frame"], "frame both levels: 2x10 joists at 12\" with joist tape, blocking, the stair opening", "base"),
 ("fascia",   ["fascia"],                                      "English Walnut fascia; the vertical-board face between the levels",           "base"),
 ("decking",  ["decking"],                                     "Vintage English Walnut decking: picture frame and breaker boards first, every screw plugged", "base"),
 ("stair",    ["inset_stair"],                                 "the stair between the levels",                                                 "base"),
 ("yard",     ["flights_y"],                                   "the stair to the yard: landing deck and two flights",                           "opt2"),
 ("rail",     ["rail", "rail_y"],                              "Impression Rail Express, black, with the English Walnut drink rail",           "base"),
 ("lights",   ["light_trim", "lights_y"],                      "low-voltage lighting: riser lights and post lights on a transformer with photocell and timer", "opt1"),
 ("clean",    ["clean"],                                       "final clean; end of construction",                                             "base"),
]
PRECON_TXT = ("Engineering & ordering — about 5–6 weeks from signing: stamped drawings; the Douglas fir timbers, footings and "
              "English Walnut boards ordered; samples approved")

def customer_rows(rows, tags):
    by = {r["id"]: r for r in rows}
    out, prev_end_r = [], 0
    vis = [(k, [by[i] for i in ids if i in by], lab, opt) for k, ids, lab, opt in GROUPS]
    vis = [(k, rs, lab, opt) for k, rs, lab, opt in vis if rs]
    n = len(vis)
    for j, (k, rs, lab, opt) in enumerate(vis):
        s = min(r["start"] for r in rs); e = max(r["end"] for r in rs)
        if k == "piers" and "opt2" in tags:
            lab = "layout; concrete caissons drilled and poured, the stair-landing caissons included"
        if k == "frame" and "opt2" in tags:
            lab = lab + "; the yard-stair landing framed"
        if k == "rail" and "opt2" in tags:
            lab = lab + "; rail and handrails on the stair to the yard"
        if k == "lights" and "opt12" in tags:
            lab = lab + ", the stair to the yard included"
        e_r = math.ceil(e - 1e-9) if j == n - 1 else math.ceil(e - 0.5 - 1e-9)     # round half down; the last row ends on the last crew day
        a, b = prev_end_r + 1, max(prev_end_r + 1, e_r)
        prev_end_r = b
        out.append(dict(key=k, option=opt, label=lab, title=lab[0].upper() + lab[1:], days=(f"Day {a}" if a == b else f"Days {a}–{b}"), first_day=a, last_day=b,
                        exact_start=s, exact_end=e, gantt_x=[round(s + 1, 2), round(e + 1, 2)]))
    return out

def schedule_lines(cust):
    """The report._schedule() shape: a list of strings, the first one the pre-construction line."""
    return [PRECON_TXT + "."] + [f"{c['days']} — {c['label']}." for c in cust]

def main():
    out = dict(job="7303 S Fillmore Cir, Centennial CO 80122", made="2026-10-27", units="working days; construction day 1 = first day on site",
               crew="one GSX crew of 4", counts=COUNTS, plug_rate_per_installer_hour=PLUG_RATE,
               precon=[dict(id=i, start_bd=s, dur_bd=n, end_bd=s + n, after=a, label=l) for i, s, n, a, l in PRE],
               construction_start_bd=START_BD,
               roof_precon=[dict(id=i, start_bd=s, dur_bd=n, end_bd=s + n, label=l) for i, s, n, l in ROOF_PRE],
               weather_float_by_month={m: round(FLOAT[m], 3) for m in FLOAT},
               scenarios={})
    print("WEATHER FLOAT by month (lost workdays / workdays):")
    for m in range(1, 13):
        print(f"  {dt.date(2026, m, 1):%b}: lost {lost(m):.1f} of {WD[m]} -> {FLOAT[m]*100:.0f}%")
    for name, tags in OPTS.items():
        rows, crew_end = schedule(tags)
        last = max(r["end"] for r in rows)
        cust = customer_rows(rows, tags)
        sc = dict(tags=sorted(tags), rows=rows, crew_days=crew_end, end_of_construction_day=math.ceil(crew_end - 1e-9),
                  customer=dict(precon=dict(label="Engineering & ordering", weeks=[5, 6], text=PRECON_TXT, gantt_x=[0, 1]),
                                rows=cust, schedule_lines=schedule_lines(cust),
                                title=f"{math.ceil(crew_end - 1e-9)} working days on site, weather permitting"))
        out["scenarios"][name] = sc
        print(f"\n== {name}: crew days {crew_end:g} (end of construction = day {sc['end_of_construction_day']})")
        for r in rows:
            print(f"  {r['id']:12s} {r['option']:5s} {r['kind']:6s} {r['start']:6.2f} -> {r['end']:6.2f}  {span_txt(r['start'], r['end']):11s} {r['label'][:90]}")
        print("  -- customer:")
        for c in cust:
            print(f"     {c['days']:11s} x{c['gantt_x']}  [{c['option']}] {c['title']}")
    # calendar examples
    print("\nCALENDAR EXAMPLES (crew days incl. float)")
    cal = {}
    for sign in (dt.date(2026, 11, 9), dt.date(2027, 2, 1), dt.date(2027, 3, 15)):
        start = add_bd(sign, START_BD)
        cal[str(sign)] = {}
        for name in OPTS:
            cd = out["scenarios"][name]["crew_days"]
            f, thaw = weather_days(start, math.ceil(cd))
            total = math.ceil(cd + f + thaw - 1e-9)
            endd = add_bd(start, total - 1)
            roof = None
            if "opt3" in OPTS[name]:
                deliver = add_bd(sign, 1 + ROOF_ZONING_BD + ROOF_MFG_BD)   # factory released on the Planning answer
                deck_ready = add_bd(start, math.ceil(16.0 + f))      # upper level decked ~ day 16 (+ float)
                r0 = max(deliver, deck_ready, endd)                  # dealer installs after the deck crew is off site
                r0 = add_bd(r0, 1)
                n = 2 + (1 if "opt3a" in OPTS[name] else 0)
                rend = add_bd(r0, n - 1 + 1)                         # + electrician/GSX return day
                roof = dict(roof_install_start=str(r0), roof_done=str(rend))
            weeks = ((roof and dt.date.fromisoformat(roof["roof_done"])) or endd) - sign
            cal[str(sign)][name] = dict(start=str(start), crew_days=cd, weather_days=round(f, 1), thaw=thaw, working_days=total,
                                        end_of_construction=str(endd), **(roof or {}), weeks_from_signing=round(weeks.days / 7, 1))
            print(f"  sign {sign} | {name:48s} start {start} | {cd:g} + wx {f:.1f} + thaw {thaw:g} = {total} wd | end {endd}"
                  + (f" | roof {roof['roof_install_start']}..{roof['roof_done']}" if roof else "") + f" | {weeks.days/7:.1f} wk")
    out["calendar_examples"] = cal
    OUT.write_text(json.dumps(out, indent=1, default=str))
    REPO_OUT = Path("/home/user/Decks-/jobs/fillmore_site/schedule.json")      # the specs' extras.timeline reads this copy
    if REPO_OUT.parent.exists():
        REPO_OUT.write_text(json.dumps(out, indent=1, default=str))
    print("\nwrote", OUT)

if __name__ == "__main__":
    main()
