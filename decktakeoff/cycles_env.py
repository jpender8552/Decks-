"""The photographic environment for decktakeoff.cycles: image-based sky light, a camera model and a late-October lawn.
Each part sits behind its own flag; cycles.py calls in here through small hooks only when the flag is on.

  --hdri=<name|1|0>    Day sky from a Poly Haven CC0 "puresky" HDRI (1 = pizzo_pernice_puresky: clear, sun 53 deg up, a
                       textbook clear-sky diffuse/direct ratio of 0.128) for sky light, reflections and the camera's sky.
                       The physical sun lamp stays for the crisp shadows: the HDRI's own sun is painted out (its energy
                       measured), the map is turned so its circumsolar glow sits at the lamp's azimuth, and its strength
                       is set so the diffuse sky / direct sun ratio is the one measured in that capture (elevation-
                       corrected). Below the horizon: a ground of plausible radiance. --sky-sat: the camera's view of the
                       sky a little deeper (a phone's sky rendering; the light and the reflections keep the map's color).
  --hdri-dusk=<name|0> Blue-hour sky (default qwantani_dusk_2_puresky when --hdri is on), turned so the afterglow sits at
                       the set sun's azimuth, tinted a little later and bluer (--dusk-tint), dim enough that the LED
                       fixtures carry the picture (--dusk-sky-lux, 4 lux on the ground).
  --hdri-dir=PATH      Where <name>_<res>.hdr live (else $DECK_HDRI_DIR, else decktakeoff/data/hdri). --hdri-res=2k|4k|8k.
  --cam=<photo|0>      The camera: metered exposure (a sunlit 18 % card at 0.18 x 2^--ev-bias; dusk: the old +3 EV +
                       --dusk-ev-bias), white balance (auto from the sun + sky on the ground, 80 % adapted; --dusk-wb
                       Kelvin at dusk), a phone's color and HDR (--sat, --local edge-aware local tone mapping, a light
                       shadow lift), Blender's AgX view (--view=agx-mhc by day, --dusk-view=agx-base; or agx, agx-punchy,
                       filmic, aces2, pbr, grade = the old numpy curve), a slight vignette (--vignette EV at the corners),
                       lateral CA (--ca px), depth of field on close-ups only (stations named "detail*" or with
                       "dof": true / "fstop"; f/4 full-frame), a gentle glare around the LEDs at dusk only (--glare), fine
                       sensor grain (--grain) and the phone's mild sharpening (--sharpen). Each EXR gets a .json sidecar
                       so regrade() can develop it again without rendering.
  --lawn=<oct|0>       Late-October Kentucky bluegrass: denser blades of mixed length and color in clumps, straw and dead
                       blades, thatch, dark soil gaps, a far-field color that matches the blades, grass filled to the
                       edges of walls / pavers / stones on a 3" sub-grid with an untrimmed, uneven edge.

Frames as in cycles.py: plan feet (x along the wall, y into the yard, z up) -> Blender (x, -y, z), 1 unit = 1 ft.
Light units (verified): a sun lamp of strength S gives irradiance S (a white diffuse plane facing it renders S/pi); a
world of radiance L gives a horizontal plane pi*L. The HDRI's integrals are radiometric, so they compare directly."""
from __future__ import annotations

import json
import math
import os
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------------------------------------------- config
DAY_HDRI = "pizzo_pernice_puresky"           # clear Alpine sky, sun 53 deg up (Centennial Sep 15 noon: 52), ratio 0.128
DUSK_HDRI = "qwantani_dusk_2_puresky"         # after sunset: deep blue overhead, a pink-gray afterglow low in the west
CFG: Dict[str, object] = dict(
    hdri="", hdri_dusk="", hdri_dir="", hdri_res="4k", hdri_rot=0.0, sky_ratio=0.0,
    ground_albedo=(0.10, 0.115, 0.075),       # what lies below the horizon past the modeled yard (lawn, roofs, trees)
    dusk_sky_lux=4.0,                         # the blue-hour sky's illuminance on the ground (real: ~3-10 lux at -4..-6 deg)
    sky_sat=1.15,                             # the camera's view of the sky only: a phone's deep Colorado blue
    dusk_tint=(0.86, 0.94, 1.12),             # the blue-hour sky light a little later and bluer than the capture's pink
    cam="", view="agx-mhc", dusk_view="agx-base", wb="auto", wb_adapt=0.8, dusk_wb=4000.0, ev_bias=1.05, dusk_ev_bias=0.9,
    vignette=0.3, ca=0.6, glare=0.07, grain=1.0, sharpen=0.35, lift_day=(0.25, 0.03), lift_dusk=(0.2, 0.02),
    local=0.25, dusk_local=0.15, sat=1.05,
    dof="auto", fstop=4.0,
    lawn="", grass_reach=34.0,
)
STATE: Dict[str, object] = {}                # what the world setup measured (the light on the ground, the WB), per mode


def _flag(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("", "0", "off", "no", "false", "none") else s


_MOD = None                                   # the running cycles module (it runs as __main__ under python -m)


def configure(opts: dict, module=None) -> None:
    """Read the flags (cycles.main's opts dict: '--name' -> value or True); module: the running decktakeoff.cycles."""
    global _MOD
    if module is not None:
        _MOD = module
    g = lambda k, d=None: opts.get(k, d)
    h = g("--hdri")
    if h is not None:
        h = _flag(h)
        CFG["hdri"] = DAY_HDRI if h in ("1", "True", "on", "yes") else h
        CFG["hdri_dusk"] = DUSK_HDRI if CFG["hdri"] else ""      # the dusk sky follows unless --hdri-dusk says otherwise
    hd = g("--hdri-dusk")
    if hd is not None:
        hd = _flag(hd)
        CFG["hdri_dusk"] = DUSK_HDRI if hd in ("1", "True", "on", "yes") else hd
    for k, key, typ in (("--hdri-dir", "hdri_dir", str), ("--hdri-res", "hdri_res", str), ("--hdri-rot", "hdri_rot", float),
                        ("--sky-ratio", "sky_ratio", float), ("--dusk-sky-lux", "dusk_sky_lux", float),
                        ("--view", "view", str), ("--wb", "wb", str), ("--wb-adapt", "wb_adapt", float),
                        ("--dusk-wb", "dusk_wb", float), ("--ev-bias", "ev_bias", float), ("--dusk-ev-bias", "dusk_ev_bias", float),
                        ("--vignette", "vignette", float), ("--ca", "ca", float), ("--glare", "glare", float),
                        ("--grain", "grain", float), ("--sharpen", "sharpen", float), ("--dof", "dof", str),
                        ("--local", "local", float), ("--sat", "sat", float), ("--sky-sat", "sky_sat", float),
                        ("--dusk-view", "dusk_view", str), ("--dusk-local", "dusk_local", float),
                        ("--fstop", "fstop", float), ("--grass-reach", "grass_reach", float)):
        if g(k) is not None and g(k) is not True:
            CFG[key] = typ(g(k))
    if g("--dusk-tint") not in (None, True):
        CFG["dusk_tint"] = tuple(float(v) for v in str(g("--dusk-tint")).split(","))[:3]
    c = g("--cam")
    if c is not None:
        c = _flag(c)
        CFG["cam"] = "photo" if c in ("1", "True", "on", "yes") else c
    lw = g("--lawn")
    if lw is not None:
        lw = _flag(lw)
        CFG["lawn"] = "oct" if lw in ("1", "True", "on", "yes") else lw


def on(part: str) -> bool:
    return bool(CFG.get(part))


def _C():
    """The cycles module that is running (bound by configure(); a second import under python -m would get its own
    LIGHTS and the world switch would never see the HDRI worlds)."""
    if _MOD is not None:
        return _MOD
    from decktakeoff import cycles as C       # lazy: cycles imports this module
    return C


# ---------------------------------------------------------------------------------------------------------------- HDRI files
def hdri_dir() -> str:
    for d in (str(CFG.get("hdri_dir") or ""), os.environ.get("DECK_HDRI_DIR", ""),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hdri")):
        if d and os.path.isdir(d):
            return d
    raise FileNotFoundError("no HDRI directory: pass --hdri-dir=PATH or set DECK_HDRI_DIR")


def hdri_file(name: str, res: str = "") -> str:
    d = hdri_dir()
    order = [res or str(CFG["hdri_res"])] + [r for r in ("4k", "8k", "2k", "16k", "1k") if r != (res or CFG["hdri_res"])]
    for r in order:
        for ext in (".hdr", ".exr"):
            p = os.path.join(d, f"{name}_{r}{ext}")
            if os.path.exists(p):
                return p
    raise FileNotFoundError(f"HDRI {name} not found in {d}")


def _load_rgb(path: str) -> np.ndarray:
    """A float image via Blender's loader -> (H, W, 3) float32, rows bottom-up (Blender's order: row 0 = v 0 = nadir)."""
    import bpy
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3].copy()


def _save_exr(path: str, rgb_bu: np.ndarray) -> None:
    import bpy
    h, w = rgb_bu.shape[:2]
    im = bpy.data.images.new(os.path.basename(path), w, h, alpha=True, float_buffer=True)
    a = np.ones((h, w, 4), np.float32); a[..., :3] = rgb_bu
    im.pixels.foreach_set(a.ravel())
    im.filepath_raw = path
    im.file_format = "OPEN_EXR"
    im.save()
    bpy.data.images.remove(im)


def _dirs(h: int, w: int):
    """Unit directions of an equirect map's pixel centers (rows bottom-up), in the map's own frame. Blender's lookup,
    verified by a render: column u -> azimuth atan2(y, x) = (0.5 - u) 2pi, row v -> elevation (v - 0.5) pi."""
    u = (np.arange(w) + 0.5) / w
    v = (np.arange(h) + 0.5) / h
    az = (0.5 - u) * 2.0 * math.pi
    el = (v - 0.5) * math.pi
    ce, se = np.cos(el)[:, None], np.sin(el)[:, None]
    return np.stack(np.broadcast_arrays(ce * np.cos(az)[None, :], ce * np.sin(az)[None, :], se), -1), el


def prep_hdri(path: str) -> dict:
    """Measure an HDRI and paint out its sun (cached next to it in derived/). The sun: the luminance peak; its core is
    where the radial profile stands above the power-law aureole fitted 6-15 deg out; the core is replaced by that aureole
    (capped) in the annulus' color, and what was taken out is the sun's direct irradiance (RGB). Also: the diffuse sky's
    irradiance on a horizontal plane (RGB, upper hemisphere, sun removed), the brightest azimuth along the horizon (the
    afterglow at dusk) and the zenith / horizon radiance. Returns the metadata; meta['map'] is the sunless EXR."""
    d = os.path.join(os.path.dirname(path), "derived")
    os.makedirs(d, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    mp, js = os.path.join(d, base + "_nosun.exr"), os.path.join(d, base + ".json")
    if os.path.exists(mp) and os.path.exists(js) and os.path.getmtime(js) >= os.path.getmtime(path):
        meta = json.load(open(js))
        meta["map"] = mp
        return meta
    t0 = time.time()
    rgb = _load_rgb(path)
    h, w = rgb.shape[:2]
    lumw = np.array([0.2126, 0.7152, 0.0722], np.float32)
    Y = rgb @ lumw
    dirs, el = _dirs(h, w)
    dA = (2 * math.pi / w) * (math.pi / h) * np.cos(el)              # solid angle per pixel, by row
    up = el > 0
    Yu = np.where(up[:, None], Y, 0.0)
    r, c = np.unravel_index(int(np.argmax(Yu)), Yu.shape)
    peak = float(Yu[r, c])
    sky_med = float(np.median(Y[up]))
    has_sun = peak > 400.0 * sky_med
    meta = dict(file=os.path.basename(path), w=w, h=h, peak=peak, sky_median=sky_med, has_sun=bool(has_sun))
    new = rgb.copy()
    if has_sun:
        m = Yu > 0.25 * peak                                           # the sun's centroid (sub-pixel)
        wts = (Yu * m)[..., None]
        sd = (dirs * wts).sum((0, 1)); sd /= np.linalg.norm(sd)
        cosang = np.clip(dirs @ sd, -1.0, 1.0)
        th = np.degrees(np.arccos(cosang))
        win = th < 20.0
        bins = np.arange(0.0, 20.0, 0.25)
        idx = np.digitize(th[win], bins) - 1
        prof = np.array([np.median(Y[win][idx == i]) if np.any(idx == i) else np.nan for i in range(len(bins))])
        tb = bins + 0.125
        fit_sel = (tb >= 6.0) & (tb <= 15.0) & np.isfinite(prof)
        bcoef, acoef = np.polyfit(np.log(tb[fit_sel]), np.log(prof[fit_sel]), 1)
        fit = lambda t: np.exp(acoef + bcoef * np.log(np.maximum(t, 1e-3)))
        rc = 1.5
        for t_, p_ in zip(tb, prof):                                   # the core ends where the profile meets the aureole
            if t_ >= 1.0 and np.isfinite(p_) and p_ < 1.3 * fit(t_):
                rc = max(rc, float(t_) + 0.5)
                break
        rc = float(min(rc, 8.0))
        ann = (th >= rc) & (th < rc + 2.0)
        chroma = rgb[ann].mean(0) / max(1e-9, float(Y[ann].mean()))
        target = np.minimum(fit(th), fit(0.6 * rc))[..., None] * chroma[None, None, :]
        wgt = np.clip((rc - th) / 0.75, 0.0, 1.0)[..., None]          # full inside rc - 0.75 deg, feathered to rc
        excess = np.maximum(rgb - target, 0.0) * wgt
        # the lens's star (diffraction spikes) out to 14 deg: azimuthal outliers of the ring around the sun, clipped to
        # 2.2 x the ring's median (a small cloud near the sun survives most of it; the spikes are 10-100 x)
        ring_med = np.interp(th, tb, np.nan_to_num(prof, nan=float(np.nanmedian(prof))))
        spike = (th >= rc - 0.75) & (th < 14.0)
        lim = (2.2 * ring_med)[..., None] * (rgb / np.maximum(Y, 1e-9)[..., None])
        excess = np.where(spike[..., None], np.maximum(excess, np.maximum(rgb - lim, 0.0)), excess)
        new = rgb - excess
        E_sun = (excess * dA[:, None, None]).sum((0, 1))               # the sun's direct irradiance (normal incidence)
        az = math.degrees(math.atan2(sd[1], sd[0])); sel = math.degrees(math.asin(sd[2]))
        meta.update(sun_az=az, sun_el=sel, core_deg=rc, aureole_slope=float(bcoef), sun_E=[float(v) for v in E_sun],
                    sun_rgb=[float(v / max(E_sun)) for v in E_sun])
    # the diffuse sky on a horizontal plane, and on the horizon ring (dusk: where the glow is)
    sinel = np.sin(el)
    dhi = (new * (np.where(up, sinel, 0.0) * dA)[:, None, None]).sum((0, 1))
    ring = (el > math.radians(0.5)) & (el < math.radians(8.0))
    Yr = (new @ lumw)[ring].mean(0)                                   # per column
    k = 31
    Yr_s = np.convolve(np.concatenate([Yr[-k:], Yr, Yr[:k]]), np.ones(k) / k, "same")[k:-k]
    gaz = math.degrees((0.5 - (int(np.argmax(Yr_s)) + 0.5) / w) * 2 * math.pi)
    zen = new[el > math.radians(80)].mean((0, 1))
    hor = new[ring].mean((0, 1))
    meta.update(dhi=[float(v) for v in dhi], glow_az=gaz, zenith=[float(v) for v in zen], horizon=[float(v) for v in hor])
    if has_sun:
        meta["ratio"] = float(dhi[1] / meta["sun_E"][1])
    _save_exr(mp, new.astype(np.float32))
    json.dump(meta, open(js, "w"), indent=1)
    meta["map"] = mp
    print(f"hdri: {base} measured in {time.time() - t0:.0f}s: " + (f"sun az {meta['sun_az']:.1f} el {meta['sun_el']:.1f}, core {meta['core_deg']:.1f} deg, diffuse/direct {meta['ratio']:.3f}" if has_sun else f"no sun (glow az {gaz:.0f})"), flush=True)
    return meta


# ---------------------------------------------------------------------------------------------------------------- the world
def _clear_sky_ratio(el_deg: float) -> float:
    """Diffuse-horizontal / direct-normal for a clear sky (Haurwitz global, Meinel direct): ~0.125 at 43 deg, ~0.118 at
    52, rising toward the horizon. Used only to carry a capture's measured ratio to the scene's sun elevation."""
    el = math.radians(max(3.0, el_deg))
    cz = math.sin(el)
    am = 1.0 / (cz + 0.50572 * (6.07995 + el_deg) ** -1.6364)
    dni = 1353.0 * 0.7 ** (am ** 0.678)
    ghi = 1098.0 * cz * math.exp(-0.057 / cz)
    return max(0.04, (ghi - dni * cz) / dni)


def _az(v) -> float:
    return math.degrees(math.atan2(v[1], v[0]))


def _world(name: str, meta: dict, beta_deg: float, strength: float, ground_rgb, tint=None, cam_sat: float = 1.0) -> "object":
    """World: the sunless map turned by beta about Z, x strength (x tint); below the horizon a ground of the given
    radiance, reached through a soft 2.5-deg band (distant haze over the next yards). cam_sat: the sky as the camera
    sees it more saturated (a phone's sky rendering) - the light and the reflections keep the map's own color."""
    import bpy
    w = bpy.data.worlds.new(name)
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    N = nt.nodes.new
    tc = N("ShaderNodeTexCoord")
    mp = N("ShaderNodeMapping"); mp.name = "env_map"; mp.vector_type = "POINT"
    mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(beta_deg))
    env = N("ShaderNodeTexEnvironment"); env.name = "env_tex"
    env.image = bpy.data.images.load(meta["map"], check_existing=True)
    env.interpolation = "Cubic"
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    env_c = env.outputs["Color"]
    if tint is not None:
        tn = N("ShaderNodeVectorMath"); tn.operation = "MULTIPLY"
        tn.inputs[1].default_value = tuple(float(v) for v in tint)
        nt.links.new(env_c, tn.inputs[0]); env_c = tn.outputs["Vector"]
    sep = N("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    t = N("ShaderNodeMapRange"); t.interpolation_type = "SMOOTHSTEP"
    for k, v in (("From Min", -0.044), ("From Max", 0.0), ("To Min", 0.0), ("To Max", 1.0)):
        t.inputs[k].default_value = v
    nt.links.new(sep.outputs["Z"], t.inputs["Value"])
    mx = N("ShaderNodeMix"); mx.data_type = "RGBA"; mx.name = "env_ground"
    sock = lambda coll, ident: next(x for x in coll if x.identifier == ident)
    sock(mx.inputs, "A_Color").default_value = tuple(float(c) / strength for c in ground_rgb) + (1.0,)
    nt.links.new(t.outputs["Result"], sock(mx.inputs, "Factor_Float")); nt.links.new(env_c, sock(mx.inputs, "B_Color"))
    col = sock(mx.outputs, "Result_Color")
    if cam_sat != 1.0:
        hs = N("ShaderNodeHueSaturation"); hs.name = "env_cam_sat"; hs.inputs["Saturation"].default_value = float(cam_sat)
        nt.links.new(col, hs.inputs["Color"])
        lp = N("ShaderNodeLightPath")
        cm = N("ShaderNodeMix"); cm.data_type = "RGBA"
        nt.links.new(lp.outputs["Is Camera Ray"], sock(cm.inputs, "Factor_Float"))
        nt.links.new(col, sock(cm.inputs, "A_Color")); nt.links.new(hs.outputs["Color"], sock(cm.inputs, "B_Color"))
        col = sock(cm.outputs, "Result_Color")
    bg = N("ShaderNodeBackground"); bg.name = "env_bg"; bg.inputs["Strength"].default_value = strength
    nt.links.new(col, bg.inputs["Color"])
    out = N("ShaderNodeOutputWorld"); nt.links.new(bg.outputs[0], out.inputs[0])
    return w


def setup_world(D, spec, sun_strength: float = 5.0) -> None:
    """The day: the puresky HDRI (sun painted out) for sky light, reflections and the camera's sky + the sun lamp."""
    import bpy
    import mathutils
    C = _C()
    meta = prep_hdri(hdri_file(str(CFG["hdri"])))
    sun = D["meta"].get("sun") or [-0.5, 0.5, 0.7]
    v = mathutils.Vector(C.B(*sun)).normalized()
    el = math.degrees(math.asin(max(-1.0, min(1.0, v.z))))
    S = float(sun_strength)
    ratio = float(CFG["sky_ratio"]) or meta["ratio"] * _clear_sky_ratio(el) / _clear_sky_ratio(meta["sun_el"])
    k = ratio * S / meta["dhi"][1]                                    # the map's strength: DHI_G = ratio x DNI
    beta = meta["sun_az"] - _az(v) + float(CFG["hdri_rot"])
    E_h = S * max(0.0, v.z) + k * meta["dhi"][1]
    ground = [a * E_h / math.pi for a in CFG["ground_albedo"]]
    w = _world("sky_hdri", meta, beta, k, ground, cam_sat=float(CFG["sky_sat"]))
    bpy.context.scene.world = w
    # the lamp: the capture's own sun color, carried to this elevation by the old model's warming
    sc = np.array(meta["sun_rgb"]) * np.array(C._sun_rgb(el)) / np.array(C._sun_rgb(meta["sun_el"]))
    sc = sc / sc.max()
    ld = bpy.data.lights.new("sun", "SUN")
    ld.energy = S
    ld.angle = math.radians(0.53)
    ld.color = tuple(float(c) for c in sc)
    ob = bpy.data.objects.new("sun", ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
    C.LIGHTS["modes"]["day"] = dict(world=w, sun=ob, energy=S, env=dict(meta=meta, k=k, S=S))
    _day_light(S, v, sc, k, meta)
    print(f"sky: {meta['file']} x{k:.4f} turned {beta:.1f} deg; diffuse/direct {ratio:.3f} "
          f"(capture {meta['ratio']:.3f} at {meta['sun_el']:.0f} deg, sun here {el:.0f} deg); sun lamp {S} {tuple(round(float(c), 3) for c in sc)}",
          flush=True)


def _day_light(S, v, sun_rgb, k, meta) -> None:
    """The light on a horizontal plane (sun + sky, RGB): the camera's meter and its auto white balance read it."""
    E = np.array(sun_rgb) * S * max(0.0, float(v.z)) + k * np.array(meta["dhi"])
    STATE["day"] = dict(E=E.tolist(), E_h=float(E @ np.array([0.2126, 0.7152, 0.0722])))


def on_set_sun(vb) -> None:
    """set_sun() moved the day sun: turn the map with it and re-read the light for the meter / WB."""
    C = _C()
    m = C.LIGHTS["modes"].get("day") or {}
    env = m.get("env")
    if not env:
        return
    meta = env["meta"]
    beta = meta["sun_az"] - _az(vb) + float(CFG["hdri_rot"])
    nd = m["world"].node_tree.nodes.get("env_map")
    if nd is not None:
        nd.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(beta))
    if vb.z > 0:
        el = math.degrees(math.asin(max(-1.0, min(1.0, vb.z))))
        sc = np.array(meta["sun_rgb"]) * np.array(C._sun_rgb(el)) / np.array(C._sun_rgb(meta["sun_el"]))
        sc = sc / sc.max()
        m["sun"].data.color = tuple(float(c) for c in sc)
        _day_light(env["S"], vb, sc, env["k"], meta)


def setup_dusk(D, spec, sun_vec) -> None:
    """Blue hour: the dusk HDRI turned so its afterglow sits at the set sun's azimuth, scaled to `dusk_sky_lux` on the
    ground (the old twilight model's scale: 5 units of sun = 100,000 lux, the fixtures at LM_W per lumen x 160, so the
    sky here is 160 x dusk_sky_lux in those units) - dim enough that the LED fixtures carry the picture."""
    import bpy
    import mathutils
    C = _C()
    meta = prep_hdri(hdri_file(str(CFG["hdri_dusk"])))
    v = mathutils.Vector(C.B(*sun_vec)).normalized()
    E_target = 160.0 * float(CFG["dusk_sky_lux"]) / 20000.0           # scene units (1 unit = 20,000 lux)
    k = E_target / meta["dhi"][1]
    ref = meta["sun_az"] if meta.get("has_sun") else meta["glow_az"]
    beta = ref - _az(v) + float(CFG["hdri_rot"])
    ground = [a * E_target / math.pi for a in CFG["ground_albedo"]]
    tint = tuple(float(v) for v in CFG["dusk_tint"])
    w = _world("dusk_hdri", meta, beta, k, ground, tint=tint)
    C.LIGHTS["modes"]["dusk"] = dict(world=w, sun=None, env=dict(meta=meta, k=k))
    STATE["dusk"] = dict(E=(k * np.array(meta["dhi"]) * np.array(tint)).tolist(), E_h=E_target)
    print(f"dusk sky: {meta['file']} x{k:.5f} turned {beta:.1f} deg ({CFG['dusk_sky_lux']} lux on the ground)", flush=True)


# ---------------------------------------------------------------------------------------------------------------- exposure
def metered_ev(mode: str, default: float) -> float:
    """The camera's exposure: a sunlit 18 % horizontal card at 0.18 x 2^bias (bias: a phone exposes a sunny yard a
    little bright). Dusk: the old default (+3 EV on the fixture-calibrated scale) + dusk_ev_bias."""
    if mode == "day":
        st = STATE.get("day")
        if not st:
            return default
        return math.log2(math.pi / st["E_h"]) + float(CFG["ev_bias"])
    return default + float(CFG["dusk_ev_bias"])


# ---------------------------------------------------------------------------------------------------------------- camera
def camera_hook(cam, c: dict, name: str, pos) -> None:
    """Depth of field on close-ups only: stations named detail*, or carrying "dof": true / "fstop". Focus on the
    station's target; the f-stop is a full-frame lens's (Blender reads the aperture in meters, the scene is in feet)."""
    if on("lawn"):
        _grass_view(c, pos, float(CFG["grass_reach"]))
    if not on("cam"):
        return
    dof = str(CFG.get("dof") or "")
    want = bool(c.get("dof")) or c.get("fstop") is not None or (dof == "auto" and name.lower().startswith("detail"))
    if dof in ("0", "off", "none") or not want:
        return
    cd = cam.data
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 24.0
    cd.angle_y = math.radians(float(c.get("fov", 40)))
    at = np.array(c["at"], float); p = np.array(pos, float)
    cd.dof.use_dof = True
    cd.dof.focus_distance = float(np.linalg.norm(at - p))
    N = float(c.get("fstop") or CFG["fstop"])
    cd.dof.aperture_fstop = N * 0.3048                                # 1 unit = 1 ft: the same physical aperture
    cd.dof.aperture_blades = 7
    cd.dof.aperture_rotation = math.radians(12.0)
    print(f"dof: {name} focus {cd.dof.focus_distance:.1f} ft, f/{N:g} ({cd.lens:.0f} mm full-frame)", flush=True)


# ---------------------------------------------------------------------------------------------------------------- grade
_XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
_BRAD = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]])


def _cct_xy(T: float) -> Tuple[float, float]:
    """Planckian locus (Kim et al. 2002), 1667-25000 K."""
    T = float(min(25000.0, max(1667.0, T)))
    if T <= 4000:
        x = -0.2661239e9 / T ** 3 - 0.2343589e6 / T ** 2 + 0.8776956e3 / T + 0.179910
    else:
        x = -3.0258469e9 / T ** 3 + 2.1070379e6 / T ** 2 + 0.2226347e3 / T + 0.240390
    if T <= 2222:
        y = -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
    elif T <= 4000:
        y = -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - 0.37001483
    return x, y


def _xy_rgb(xy) -> np.ndarray:
    x, y = xy
    XYZ = np.array([x / y, 1.0, (1 - x - y) / y])
    return np.linalg.solve(_XYZ, XYZ)


def _bradford(src_rgb, dst_rgb=(1.0, 1.0, 1.0), adapt: float = 1.0) -> np.ndarray:
    """3x3 (linear Rec.709) that maps the white src_rgb to dst_rgb (Bradford), partially (adapt 0..1)."""
    s = _BRAD @ (_XYZ @ np.asarray(src_rgb, float))
    d = _BRAD @ (_XYZ @ np.asarray(dst_rgb, float))
    g = (d / s) ** float(adapt)
    M = np.linalg.inv(_XYZ) @ np.linalg.inv(_BRAD) @ np.diag(g) @ _BRAD @ _XYZ
    lum = np.array([0.2126, 0.7152, 0.0722])
    return M / float(lum @ M @ np.asarray(src_rgb, float) / (lum @ np.asarray(src_rgb, float)))   # keep the white's luminance


def wb_matrix(mode: str) -> np.ndarray:
    """Day 'auto': adapt `wb_adapt` of the way from the light on a horizontal plane (sun + sky) to neutral, as a camera's
    AWB does (a sunny scene keeps a trace of warmth). A number: that Kelvin read as neutral, where the HDRI's capture
    balance (~5300 K) is the render's neutral. Dusk: dusk_wb Kelvin the same way (~4300 K: deep blue sky, warm LEDs)."""
    if mode == "dusk":
        T = float(CFG["dusk_wb"])
    else:
        wb = str(CFG["wb"])
        if wb == "auto":
            E = np.array((STATE.get("day") or {}).get("E", [1, 1, 1]), float)
            return _bradford(E / E.max(), adapt=float(CFG["wb_adapt"]))
        if wb in ("0", "off", "none"):
            return np.eye(3)
        T = float(wb)
    ref = _xy_rgb(_cct_xy(5300.0))
    src = _xy_rgb(_cct_xy(T))
    rel = src / ref                                                   # T as it looks in the 5300 K-neutral render
    return _bradford(rel / rel.max())


def _gauss_fft(img: np.ndarray, sigma: float) -> np.ndarray:
    h, w = img.shape[:2]
    fy = np.fft.fftfreq(h)[:, None]; fx = np.fft.rfftfreq(w)[None, :]
    G = np.exp(-2.0 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    out = np.empty_like(img)
    for ch in range(img.shape[2]):
        out[..., ch] = np.fft.irfft2(np.fft.rfft2(img[..., ch]) * G, s=(h, w))
    return out


def _box(a: np.ndarray, r: int) -> np.ndarray:
    """Mean over a (2r+1)^2 window (edges clamped), by cumulative sums."""
    p = np.pad(a, r + 1, mode="edge").astype(np.float64)
    c = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return (s / (k * k))[: a.shape[0], : a.shape[1]].astype(np.float32)


def _guided(I: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Self-guided filter (He et al.): the edge-aware base layer of I (strong edges kept, so no halos at the roofline)."""
    mI = _box(I, r); vI = _box(I * I, r) - mI * mI
    a = vI / (vI + eps); b = mI - a * mI
    return _box(a, r) * I + _box(b, r)


def _scale_about_center(ch: np.ndarray, s: float) -> np.ndarray:
    """Resample one channel scaled by s about the image center (bilinear): lateral chromatic aberration."""
    h, w = ch.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    sx, sy = cx + (xx - cx) / s, cy + (yy - cy) / s
    x0 = np.clip(np.floor(sx).astype(int), 0, w - 2); y0 = np.clip(np.floor(sy).astype(int), 0, h - 2)
    fx = np.clip(sx - x0, 0, 1); fy = np.clip(sy - y0, 0, 1)
    return (ch[y0, x0] * (1 - fx) * (1 - fy) + ch[y0, x0 + 1] * fx * (1 - fy) + ch[y0 + 1, x0] * (1 - fx) * fy
            + ch[y0 + 1, x0 + 1] * fx * fy)


def develop(lin: np.ndarray, exposure: float, mode: str = "day") -> np.ndarray:
    """Scene-linear (top-down rows) -> the camera's linear image before the view transform: exposure, white balance,
    lateral CA, vignette, glare (dusk: the LEDs only), the phone's shadow lift (hue kept)."""
    x = lin[..., :3].astype(np.float32) * np.float32(2.0 ** exposure)
    x = np.maximum(x @ wb_matrix(mode).T.astype(np.float32), 0.0)
    h, w = x.shape[:2]
    ca = float(CFG["ca"])
    if ca:
        half_diag = 0.5 * math.hypot(w, h)
        s = ca / half_diag                                            # ca px of R/B split at the corners
        x[..., 0] = _scale_about_center(x[..., 0], 1.0 + s)
        x[..., 2] = _scale_about_center(x[..., 2], 1.0 - s)
    vig = float(CFG["vignette"])
    if vig:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r2 = (((xx - (w - 1) / 2) ** 2 + (yy - (h - 1) / 2) ** 2) / (0.25 * (w * w + h * h)))
        x *= (2.0 ** (-vig * r2 ** 1.25))[..., None]
    if mode == "dusk" and float(CFG["glare"]):
        L = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        thr = 3.0
        hot = x * (np.maximum(L - thr, 0.0) / np.maximum(L, 1e-6))[..., None]
        sc = w / 1500.0
        g = float(CFG["glare"])
        x = x + g * (0.6 * _gauss_fft(hot, 2.5 * sc) + 0.3 * _gauss_fft(hot, 9.0 * sc) + 0.1 * _gauss_fft(hot, 30.0 * sc))
    sat = float(CFG.get("sat") or 1.0)
    if sat != 1.0:                                                    # a phone's color profile: midtone saturation
        L = (x @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        x = np.maximum(L + (x - L) * np.float32(sat), 0.0)
    loc = float(CFG.get("dusk_local" if mode == "dusk" else "local") or 0.0)
    if loc:                                                           # a phone's HDR: compress the large-scale contrast
        L = np.maximum(x @ np.array([0.2126, 0.7152, 0.0722], np.float32), 1e-5)
        l = np.log2(L)
        base = _guided(l, max(4, int(w / 24)), 0.6 ** 2)
        anchor = float(np.median(base))
        x = x * (2.0 ** (-loc * (base - anchor)))[..., None]
    a, b = CFG["lift_dusk"] if mode == "dusk" else CFG["lift_day"]
    if a:
        L = np.maximum(x @ np.array([0.2126, 0.7152, 0.0722], np.float32), 0.0)
        x = x * (1.0 + np.float32(a) * np.exp(-L / np.float32(b)))[..., None]
    return x


_LOOKS = {"agx": ("AgX", "None"), "agx-base": ("AgX", "AgX - Base Contrast"), "agx-mhc": ("AgX", "AgX - Medium High Contrast"),
          "agx-punchy": ("AgX", "AgX - Punchy"), "agx-hc": ("AgX", "AgX - High Contrast"), "filmic": ("Filmic", "Medium High Contrast"),
          "aces2": ("ACES 2.0", "None"), "pbr": ("Khronos PBR Neutral", "None")}


def view_transform(x: np.ndarray, tmp_png: str, mode: str = "day") -> np.ndarray:
    """Camera-linear (top-down) -> display sRGB 0..1 through Blender's own OCIO view (AgX by default) or grade()."""
    view = str(CFG["dusk_view"] if mode == "dusk" else CFG["view"])
    if view == "grade":
        C = _C()
        return C.grade(np.concatenate([x, np.ones_like(x[..., :1])], -1), 0.0, (0.0, 0.05))
    import bpy
    vt, look = _LOOKS.get(view, _LOOKS["agx-mhc"])
    scn = bpy.context.scene
    vs = scn.view_settings
    keep = (vs.view_transform, vs.look, vs.exposure, vs.gamma, scn.render.image_settings.file_format,
            scn.render.image_settings.color_mode, scn.render.image_settings.color_depth)
    h, w = x.shape[:2]
    im = bpy.data.images.new("_dev", w, h, alpha=True, float_buffer=True)
    a = np.ones((h, w, 4), np.float32); a[..., :3] = x[::-1]
    im.pixels.foreach_set(a.ravel())
    try:
        vs.view_transform = vt; vs.look = look; vs.exposure = 0.0; vs.gamma = 1.0
        scn.render.image_settings.file_format = "PNG"; scn.render.image_settings.color_mode = "RGB"
        scn.render.image_settings.color_depth = "16"
        im.save_render(tmp_png, scene=scn)
    finally:
        bpy.data.images.remove(im)
        (vs.view_transform, vs.look, vs.exposure, vs.gamma, scn.render.image_settings.file_format,
         scn.render.image_settings.color_mode, scn.render.image_settings.color_depth) = keep
    rd = bpy.data.images.load(tmp_png, check_existing=False)     # 16-bit back through Blender (PIL reads 48-bit as 8)
    rd.colorspace_settings.name = "Non-Color"
    px = np.empty(w * h * 4, np.float32)
    rd.pixels.foreach_get(px)
    bpy.data.images.remove(rd)
    os.remove(tmp_png)
    return px.reshape(h, w, 4)[::-1, :, :3].copy()


def finish(y: np.ndarray, seed: int = 0) -> "object":
    """Display sRGB 0..1 -> the JPEG's 8-bit image: a phone's mild sharpening and a fine, mostly luminance grain."""
    from PIL import Image, ImageFilter
    g = float(CFG["grain"])
    if g:
        rng = np.random.default_rng(seed)
        h, w = y.shape[:2]
        L = y @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        amp = (g / 255.0) * (0.6 + 1.2 * (1.0 - L))[..., None]       # a little more in the shadows
        n = rng.standard_normal((h, w, 1)).astype(np.float32) + 0.3 * rng.standard_normal((h, w, 3)).astype(np.float32)
        y = y + amp * n
    im = Image.fromarray((np.clip(y, 0, 1) * 255.0 + 0.5).astype(np.uint8), "RGB")
    s = float(CFG["sharpen"])
    if s:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.1, percent=int(100 * s), threshold=1))
    return im


def grade_exr(exr_path: str, jpg_path: str, exposure: float, mode: str = "day", quality: int = 92) -> None:
    """The camera: the rendered linear EXR -> the JPEG (develop -> view transform -> finish)."""
    import bpy
    img = bpy.data.images.load(exr_path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    lin = px.reshape(h, w, 4)[::-1]
    try:                                       # the sidecar: what regrade() needs to develop this EXR again
        json.dump(dict(exposure=exposure, mode=mode, state=STATE.get(mode), cfg={k: v for k, v in CFG.items()}),
                  open(os.path.splitext(exr_path)[0] + ".json", "w"), indent=1, default=str)
    except Exception:
        pass
    x = develop(lin, exposure, mode)
    y = view_transform(x, os.path.splitext(jpg_path)[0] + "._dev.png", mode)
    seed = int.from_bytes(os.path.basename(jpg_path).encode()[:4].ljust(4, b"_"), "little")
    finish(y, seed).save(jpg_path, quality=quality, subsampling=0)


def regrade(exr_path: str, jpg_path: str, ev_offset: float = 0.0, **cfg) -> None:
    """Develop a rendered EXR again with other camera settings (no render): its sidecar gives the exposure, the mode and
    the measured light; cfg overrides CFG (e.g. view="grade", vignette=0)."""
    side = json.load(open(os.path.splitext(exr_path)[0] + ".json"))
    keep = dict(CFG)
    try:
        CFG.update({k: v for k, v in side.get("cfg", {}).items() if k in CFG and k not in ("lift_day", "lift_dusk", "ground_albedo")})
        CFG.update(cfg)
        if side.get("state"):
            STATE[side["mode"]] = side["state"]
        grade_exr(exr_path, jpg_path, float(side["exposure"]) + ev_offset, side["mode"])
    finally:
        CFG.clear(); CFG.update(keep)


# ---------------------------------------------------------------------------------------------------------------- the lawn
def _lin(hexc: str) -> np.ndarray:
    h = hexc.lstrip("#")
    s = np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    return np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)


# Kentucky bluegrass in a Colorado late October (watered, fertilized, a few frosts): deep cool greens, older olive
# blades, straw-dead blades and dark brown dead ones; the mower's cut tips dried tan. sRGB.
BLADES = dict(
    green=("#4f7230", "#5a7b35", "#64843b", "#6e8b44", "#527033", "#5e8239", "#668040"),
    olive=("#7a8644", "#878f4f", "#738040"),
    straw=("#a8975f", "#b8a874", "#958353", "#c4b787", "#9e8e5e"),
    dead=("#6d5a3b", "#5a4931", "#7a6646"),
    tip="#b9ab7d", thatch="#4f4330", soil="#3a3025", moss="#3d4825",
    gc=("#2f4a24", "#3a5a2b", "#466633", "#35502a", "#5b6e3a"),       # the ground-cover bed: a low leafy mat
)
BLADE_P = (0.68, 0.14, 0.12, 0.06)


def _blade_palette():
    groups = [np.array([_lin(c) for c in BLADES[k]]) for k in ("green", "olive", "straw", "dead")]
    return groups


def lawn_mean_lin() -> np.ndarray:
    """The blades' mean albedo (linear): the far lawn's color is built around it."""
    groups = _blade_palette()
    return sum(p * g.mean(0) for p, g in zip(BLADE_P, groups))


def gc_patch_arrays(rng, n: int, size: float):
    """Ground-cover leaves (vinca / creeping jenny habit): short wide blades held low, dark glossy greens."""
    V, F, COL = grass_patch_arrays(rng, n, size, tall=0.5, leafy=True)
    return V, F, COL


def grass_patch_arrays(rng, n_blades: int, size: float, tall: float = 1.0, leafy: bool = False):
    """Blade strips for a size x size patch centered on 0 (Blender frame, z up): clumped (wrapped, so patches tile),
    lengths and widths varied, each blade rising at 60-88 deg and bending over by 15-75 deg in three segments, a little
    twist; ~6 % thatch (dead blades lying down). Colors per vertex: the blade's color, darker and browner at the base,
    cut tips dried tan on a third of the green ones. Returns (V (n*7, 3), F list, COL (n*7, 4))."""
    groups = _blade_palette()
    n = int(n_blades)
    nclump = max(1, int(30 * size * size))
    centers = rng.uniform(-size / 2, size / 2, (nclump, 2))
    in_clump = rng.random(n) < 0.45
    ci = rng.integers(0, nclump, n)
    pos = rng.uniform(-size / 2, size / 2, (n, 2))
    pos[in_clump] = centers[ci[in_clump]] + rng.normal(0.0, 0.035, (int(in_clump.sum()), 2))
    pos = (pos + size / 2) % size - size / 2                          # wrap: the patch tiles without a seam
    clump_h = rng.uniform(0.85, 1.18, nclump)
    hf = np.where(in_clump, clump_h[ci], 1.0)
    L = np.clip(0.235 * np.exp(rng.normal(0.0, 0.2, n)) * hf * tall, 0.10, 0.48)
    long_ = rng.random(n) < 0.04                                      # a few blades the mower missed
    L[long_] *= rng.uniform(1.3, 1.7, int(long_.sum()))
    wd = rng.uniform(0.0085, 0.0145, n)
    az = rng.uniform(0, 2 * math.pi, n)
    a0 = np.radians(rng.uniform(60, 88, n))
    bend = np.radians(rng.uniform(15, 75, n))
    if leafy:
        wd = rng.uniform(0.028, 0.05, n)
        L = np.clip(rng.uniform(0.07, 0.16, n), 0.05, 0.2)
        a0 = np.radians(rng.uniform(15, 55, n))
        bend = np.radians(rng.uniform(10, 50, n))
    thatch = rng.random(n) < 0.06
    a0[thatch] = np.radians(rng.uniform(8, 30, int(thatch.sum())))
    bend[thatch] = np.radians(rng.uniform(5, 25, int(thatch.sum())))
    L[thatch] *= 0.75
    twist = np.radians(rng.uniform(-35, 35, n))
    # colors: group by probability (clumps share a group and a shade)
    gsel = rng.choice(4, n, p=BLADE_P)
    clump_g = rng.choice(4, nclump, p=BLADE_P)
    gsel = np.where(in_clump & (rng.random(n) < 0.7), clump_g[ci], gsel)
    gsel[thatch] = np.where(rng.random(int(thatch.sum())) < 0.6, 3, 2)
    col = np.array([groups[g][int(rng.integers(len(groups[g])))] for g in gsel])
    if leafy:
        gcp = np.array([_lin(c) for c in BLADES["gc"]])
        col = gcp[rng.integers(0, len(gcp), n)]
        col[thatch] = _lin(BLADES["dead"][0])
    col *= rng.uniform(0.86, 1.12, (n, 1)) * rng.uniform(0.96, 1.04, (n, 3))
    tip = col.copy()
    cut = (gsel == 0) & (rng.random(n) < 0.33)
    tip[cut] = 0.45 * col[cut] + 0.55 * _lin(BLADES["tip"])
    thc = _lin(BLADES["thatch"])
    base = 0.78 * (0.7 * col + 0.3 * thc)
    # geometry
    d = np.stack([np.cos(az), np.sin(az)], 1)
    P = np.zeros((n, 4, 3))
    P[:, 0, :2] = pos
    for k in range(3):
        a = a0 - bend * (k + 0.5) / 3.0
        seg = (L / 3.0)[:, None]
        P[:, k + 1, :2] = P[:, k, :2] + seg * np.cos(a)[:, None] * d
        P[:, k + 1, 2] = P[:, k, 2] + (L / 3.0) * np.sin(a)
    V = np.zeros((n, 7, 3))
    widths = (0.45, 1.0, 0.75) if leafy else (1.0, 0.92, 0.7)
    for k in range(3):
        tw = twist * k / 3.0
        ca_, sa_ = np.cos(az + math.pi / 2 + tw), np.sin(az + math.pi / 2 + tw)
        half = (wd * widths[k] / 2)[:, None]
        wv = np.stack([ca_, sa_, np.zeros(n)], 1) * half
        V[:, 2 * k] = P[:, k] - wv
        V[:, 2 * k + 1] = P[:, k] + wv
    V[:, 6] = P[:, 3]
    C = np.zeros((n, 7, 4)); C[..., 3] = 1.0
    C[:, 0, :3] = C[:, 1, :3] = base
    C[:, 2, :3] = C[:, 3, :3] = 0.35 * base + 0.65 * col
    C[:, 4, :3] = C[:, 5, :3] = col
    C[:, 6, :3] = tip
    F = []
    for i in range(n):
        o = 7 * i
        F += [(o, o + 1, o + 3, o + 2), (o + 2, o + 3, o + 5, o + 4), (o + 4, o + 5, o + 6)]
    return V.reshape(-1, 3), F, C.reshape(-1, 4)


def _patch_mesh(name: str, V, F, COL, mat):
    import bpy
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in V], [], F)
    ca = me.color_attributes.new(name="tint", type="FLOAT_COLOR", domain="POINT")
    ca.data.foreach_set("color", np.asarray(COL, np.float32).ravel())
    try:
        me.shade_smooth()
    except Exception:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.materials.append(mat)
    return me


def _noise2(x: float, y: float, seed: int = 0) -> float:
    """A cheap smooth 2-D value field in 0..1 (sum of sines at incommensurate angles) for per-cell height."""
    s = 0.0
    for k, (f, a) in enumerate(((0.11, 0.3), (0.23, 1.9), (0.37, 4.1), (0.07, 2.6))):
        s += math.sin(f * (x * math.cos(a) + y * math.sin(a)) * 2 * math.pi + seed * 1.7 + k)
    return 0.5 + s / 8.0


def _blocked_fn(spec, D):
    """Where no grass grows, at the true edges: the house side, the deck (+ 0.15'), beds, the walls' outside faces
    (+ 0.2': the buried courses step out), the paver band's own polygon, the fences, flagstone ellipses, trunks, shrubs
    and stairs (+ 0.12')."""
    from decktakeoff.landscape import _resample, _in_poly
    sm = spec.geometry.site_model or {}
    polys = []
    walls = {w.get("name"): w for w in sm.get("walls", [])}
    for b in sm.get("beds", []):
        if b.get("wall"):
            w = walls[b["wall"]]
            polys.append(_resample(w["path"], 0.5, smooth=w.get("smooth", True)) + [tuple(q) for q in b.get("close", [])])
        else:
            polys.append([tuple(q) for q in b["poly"]])
    for p in sm.get("pavers", []):                                     # the band as landscape.pavers lays it
        path = [tuple(q[:2]) for q in p["path"]]
        wd = float(p.get("width_in", 16)) / 12.0 + 0.04
        side = 1.0 if p.get("side", "left") == "left" else -1.0

        def nrm(a, b):
            L = math.hypot(b[0] - a[0], b[1] - a[1]); return (-(b[1] - a[1]) / L * side, (b[0] - a[0]) / L * side)
        outer = []
        for i, q in enumerate(path):
            if i == 0:
                n_ = nrm(path[0], path[1]); outer.append((q[0] + n_[0] * wd, q[1] + n_[1] * wd))
            elif i == len(path) - 1:
                n_ = nrm(path[-2], path[-1]); outer.append((q[0] + n_[0] * wd, q[1] + n_[1] * wd))
            else:
                n1, n2 = nrm(path[i - 1], q), nrm(q, path[i + 1])
                bx, by = n1[0] + n2[0], n1[1] + n2[1]; bl_ = math.hypot(bx, by)
                cosh = (n1[0] * bx + n1[1] * by) / bl_
                outer.append((q[0] + bx / bl_ * wd / cosh, q[1] + by / bl_ * wd / cosh))
        polys.append(path + outer[::-1])
    segs = []
    for w in sm.get("walls", []):
        segs.append((_resample(w["path"], 0.5, smooth=w.get("smooth", True)), 0.2))
    for f in sm.get("fences", []):
        segs.append(([tuple(q[:2]) for q in f["path"]], 0.2))
    ells = []
    for f in sm.get("flagstones", []):
        a, b = f.get("size", [3.0, 2.2]); th = math.radians(f.get("rot", 0.0))
        ells.append((f["at"][0], f["at"][1], a / 2 * 1.06 + 0.03, b / 2 * 1.06 + 0.03, math.cos(th), math.sin(th)))
    discs = [(t["at"][0], t["at"][1], 0.55) for t in sm.get("trees", []) if t.get("type", "deciduous") != "shrub"]
    discs += [(t["at"][0], t["at"][1], float(t.get("radius", 2.0)) * 0.75) for t in sm.get("trees", []) if t.get("type") == "shrub"]
    boxes = [(b["x0"] - 0.12, b["x1"] + 0.12, b["y0"] - 0.12, b["y1"] + 0.12) for b in D["boxes"]
             if b["kind"] in ("tread", "riser", "stringer") or (b.get("tag") or "").startswith("box step")]
    out = [tuple(p) for p in (spec.geometry.outline or [])]

    def seg_d(x, y, pl):
        best = 9e9
        for (ax, ay), (bx, by) in zip(pl, pl[1:]):
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy or 1e-9
            t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
            best = min(best, math.hypot(x - (ax + vx * t), y - (ay + vy * t)))
        return best

    def blocked(x, y):
        if y < 0.4:
            return True
        if out and (_in_poly(x, y, out) or seg_d(x, y, out + out[:1]) < 0.15):
            return True
        if any(_in_poly(x, y, P) for P in polys):
            return True
        if any(seg_d(x, y, pl) < hw for pl, hw in segs):
            return True
        for cx, cy, ra, rb, c_, s_ in ells:
            dx, dy = x - cx, y - cy
            u, v = dx * c_ + dy * s_, -dx * s_ + dy * c_
            if (u / ra) ** 2 + (v / rb) ** 2 < 1.0:
                return True
        if any(math.hypot(x - cx, y - cy) < r for cx, cy, r in discs):
            return True
        if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in boxes):
            return True
        return False
    return blocked


def _yard_poly(sm) -> Optional[list]:
    """The fenced yard as one polygon: the fence paths chained end to end (a gap - the house - closed straight)."""
    paths = [[tuple(q[:2]) for q in f["path"]] for f in sm.get("fences", []) if len(f.get("path", [])) >= 2]
    if not paths:
        return None
    chain = list(paths.pop(0))
    while paths:
        end = chain[-1]
        best = min(range(len(paths)), key=lambda i: min(math.dist(end, paths[i][0]), math.dist(end, paths[i][-1])))
        p = paths.pop(best)
        if math.dist(end, p[-1]) < math.dist(end, p[0]):
            p = p[::-1]
        chain += p[1:] if math.dist(end, p[0]) < 0.5 else p
    return chain if len(chain) >= 3 else None


def _grass_view(c: dict, pos, reach: float) -> None:
    """Only the grass the current view needs renders: patches within `reach` ft (3-D: an elevated view sees none and
    the lawn is the far field's color all over, no hard-edged rectangles of blades) and in front of the lens."""
    obs = STATE.get("grass") or []
    if not obs:
        return
    px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
    ax, ay = c["at"][0] - px, c["at"][1] - py
    L = math.hypot(ax, ay) or 1.0
    dx, dy = ax / L, ay / L
    half = math.radians(float(c.get("fov", 40))) * 0.5 * 1.7
    n = 0
    for ob, cx, cy, cz in obs:
        vx, vy = cx - px, cy - py
        dd = math.hypot(vx, vy)
        d3 = math.sqrt(dd * dd + (cz - pz) ** 2)
        ok = d3 <= reach and (dd < 4.0 or math.acos(max(-1.0, min(1.0, (vx * dx + vy * dy) / max(dd, 1e-6)))) <= half)
        ob.hide_render = not ok
        n += ok
    print(f"grass: {n} of {len(obs)} patches in this view", flush=True)


def _quiet_lawn_ground() -> None:
    """The lawn's ground material without the old sheen (it went minty gray at grazing angles once blades were dense)."""
    import bpy
    for nm in ("lawn", "ground", "meadow", "groundcover"):
        m = bpy.data.materials.get(nm)
        if m is None or not m.node_tree:
            continue
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                for k, v in (("Sheen Weight", 0.0), ("Roughness", 0.97), ("Specular IOR Level", 0.25)):
                    try:
                        n.inputs[k].default_value = v
                    except KeyError:
                        pass


def _blade_material():
    """Waxy blades: a dielectric sheen (they mirror the bright sky at grazing angles - the silvery cast of a lawn seen
    toward the light), 30 % translucency (backlit blades glow), the vertex color x the lawn's world-space field."""
    import bpy
    mat = bpy.data.materials.new("grass_blades_oct")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    attr = nt.nodes.new("ShaderNodeAttribute"); attr.attribute_name = "tint"
    patch, _ = lawn_nodes(nt, "lawn", {}, relative=True)
    tm = nt.nodes.new("ShaderNodeVectorMath"); tm.operation = "MULTIPLY"
    nt.links.new(attr.outputs["Color"], tm.inputs[0]); nt.links.new(patch, tm.inputs[1])
    nt.links.new(tm.outputs["Vector"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.38
    bsdf.inputs["Specular IOR Level"].default_value = 0.55
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent"); nt.links.new(tm.outputs["Vector"], tr.inputs["Color"])
    mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs[0].default_value = 0.3
    nt.links.new(bsdf.outputs[0], mx.inputs[1]); nt.links.new(tr.outputs[0], mx.inputs[2]); nt.links.new(mx.outputs[0], out.inputs[0])
    return mat


def add_grass(spec, D, cams: Dict[str, dict], names: List[str], col, reach: float = 34.0, cell: float = 1.0) -> int:
    """Blade patches within `reach` ft of the rendering cameras (and in front of them): a 1' patch where the whole cell
    is lawn; where the cell meets an edge, 3" sub-patches on the free sub-cells - taller (the trimmer misses them) and a
    few left out (a ragged edge). 12 + 8 variants, turned by quarter turns and mirrored; the patch height follows a smooth
    field (no per-cell steps); each patch lies in the slope's plane."""
    import bpy
    import mathutils
    from decktakeoff.landscape import Grade
    C = _C()
    t0 = time.time()
    sm = spec.geometry.site_model or {}
    gm = sm.get("grade", {})
    grade = Grade(gm.get("points", [[0, 0, 0]]))
    x0, x1, y0, y1 = gm.get("extent", [-40, 60, -12, 36])
    blocked = _blocked_fn(spec, D)
    rng = np.random.default_rng(1031)
    mat = _blade_material()
    full = [_patch_mesh(f"grass_oct_{k}", *grass_patch_arrays(rng, 1750, cell), mat) for k in range(12)]
    sub = 0.25 * cell
    small = [_patch_mesh(f"grass_oct_s{k}", *grass_patch_arrays(rng, 120, sub, tall=1.12), mat) for k in range(8)]
    gcm = [_patch_mesh(f"groundcover_{k}", *gc_patch_arrays(rng, 70, 0.5), mat) for k in range(6)]
    _quiet_lawn_ground()
    yard = _yard_poly(sm)
    from decktakeoff.landscape import _in_poly, _resample
    STATE["grass"] = []
    stations = []
    for nm in names:
        c = cams.get(nm)
        if not c:
            continue
        px, py = c["pos"][0], c["pos"][1]
        ax, ay = c["at"][0] - px, c["at"][1] - py
        L = math.hypot(ax, ay) or 1.0
        stations.append((px, py, ax / L, ay / L, math.radians(float(c.get("fov", 40))) * 0.5 * 1.7))

    def place(meshes, cx, cy, size, zs, lift=0.0):
        ob = bpy.data.objects.new("grass", meshes[int(rng.integers(len(meshes)))])
        ob.location = C.B(cx, cy, grade(cx, cy) - 0.02 + lift)
        STATE["grass"].append((ob, cx, cy, grade(cx, cy)))
        e = 0.5 * size
        gx = (grade(cx + e, cy) - grade(cx - e, cy)) / size
        gy = (grade(cx, cy + e) - grade(cx, cy - e)) / size
        tilt = mathutils.Vector((0.0, 0.0, 1.0)).rotation_difference(mathutils.Vector(C.B(-gx, -gy, 1.0)).normalized())
        spin = mathutils.Quaternion((0.0, 0.0, 1.0), float(rng.integers(4)) * math.pi / 2)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = tilt @ spin
        ob.scale = ((1 if rng.random() < 0.5 else -1), 1.0, zs)
        col.objects.link(ob)
    n_full = n_sub = 0
    for x in np.arange(x0, x1, cell):
        for y in np.arange(y0, y1, cell):
            cx, cy = x + cell / 2, y + cell / 2
            ok = False
            for px, py, dx, dy, half in stations:
                vx, vy = cx - px, cy - py
                dd = math.hypot(vx, vy)
                if dd > reach or dd < 0.5:
                    continue
                ang = math.acos(max(-1.0, min(1.0, (vx * dx + vy * dy) / dd)))
                if ang <= half or dd < 4.0:
                    ok = True
                    break
            if not ok:
                continue
            zs = 0.88 + 0.24 * _noise2(cx, cy)
            probe = [(cx, cy)] + [(cx + sx * 0.45 * cell, cy + sy * 0.45 * cell) for sx in (-1, 1) for sy in (-1, 1)]
            bl = [blocked(px_, py_) or (yard is not None and not _in_poly(px_, py_, yard)) for px_, py_ in probe]
            if not any(bl):
                place(full, cx, cy, cell, zs); n_full += 1
                continue
            for i in range(4):
                for j in range(4):
                    sx_, sy_ = x + (i + 0.5) * sub, y + (j + 0.5) * sub
                    if blocked(sx_, sy_) or (yard is not None and not _in_poly(sx_, sy_, yard)) or rng.random() < 0.08:
                        continue
                    place(small, sx_, sy_, sub, zs * float(rng.uniform(1.0, 1.25))); n_sub += 1
    # the ground-cover beds: low leafy plants on a 6" grid (a few gaps), the bed's soil between them
    n_gc = 0
    walls = {w.get("name"): w for w in sm.get("walls", [])}
    for b in sm.get("beds", []):
        if b.get("mat") != "groundcover":
            continue
        if b.get("wall"):
            w = walls[b["wall"]]
            P = _resample(w["path"], 0.5, smooth=w.get("smooth", True)) + [tuple(q) for q in b.get("close", [])]
        else:
            P = [tuple(q) for q in b["poly"]]
        xs_, ys_ = [q[0] for q in P], [q[1] for q in P]
        for gx_ in np.arange(min(xs_), max(xs_), 0.5):
            for gy_ in np.arange(min(ys_), max(ys_), 0.5):
                qx, qy = gx_ + 0.25, gy_ + 0.25
                if not _in_poly(qx, qy, P) or rng.random() < 0.12:
                    continue
                place(gcm, qx, qy, 0.5, float(rng.uniform(0.8, 1.2)), lift=float(b.get("lift", 0.0))); n_gc += 1
    print(f"grass (late October): {n_full} 1-ft patches + {n_sub} 3-in edge patches + {n_gc} ground-cover tufts in {time.time() - t0:.0f}s", flush=True)
    return n_full + n_sub + n_gc


def lawn_nodes(nt, key: str, md: dict, relative: bool = False):
    """The lawn's world-space color field, late October. relative=True (the blades): a multiplier about 1.0 - broad
    green / dry swaths (~25'), mottling (~4'), a few straw-dead spots (~2'). The ground (relative=False): under the
    near-field blades (closer than the grass reach) dark thatch and soil with moss; beyond it the blades' mean color
    under the same field, darkened for the canopy's self-shadowing, with blade-scale speckle. Returns (color, height)."""
    N = nt.nodes.new
    geo = N("ShaderNodeNewGeometry")

    def noise(scale, detail, rough=0.5, dist=0.0, w=None):
        n = N("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Distortion"].default_value = dist
        nt.links.new(geo.outputs["Position"], n.inputs["Vector"])
        return n.outputs["Fac"]

    def mrange(sock, a, b, lo, hi, smooth=False):
        m = N("ShaderNodeMapRange")
        if smooth:
            m.interpolation_type = "SMOOTHSTEP"
        for nm, v in (("From Min", a), ("From Max", b), ("To Min", lo), ("To Max", hi)):
            m.inputs[nm].default_value = v
        nt.links.new(sock, m.inputs["Value"])
        return m.outputs["Result"]

    def mixc(a, b, f):
        m = N("ShaderNodeMix"); m.data_type = "RGBA"
        sock = lambda coll, ident: next(x for x in coll if x.identifier == ident)
        for s, ident in ((f, "Factor_Float"), (a, "A_Color"), (b, "B_Color")):
            if isinstance(s, (tuple, list, np.ndarray)):
                sock(m.inputs, ident).default_value = tuple(float(v) for v in s)[:3] + (1.0,)
            elif isinstance(s, (int, float)):
                sock(m.inputs, ident).default_value = float(s)
            else:
                nt.links.new(s, sock(m.inputs, ident))
        return sock(m.outputs, "Result_Color")

    def scale(c, s):
        m = N("ShaderNodeVectorMath"); m.operation = "SCALE"
        nt.links.new(c, m.inputs[0])
        if isinstance(s, (int, float)):
            m.inputs["Scale"].default_value = float(s)
        else:
            nt.links.new(s, m.inputs["Scale"])
        return m.outputs["Vector"]

    def mul(a, b):
        m = N("ShaderNodeMath"); m.operation = "MULTIPLY"
        nt.links.new(a, m.inputs[0]); nt.links.new(b, m.inputs[1])
        return m.outputs[0]
    dry_k = 1.25 if key == "meadow" else 1.0
    # the patch field: 1.0 = the lawn's mean; green swaths a little darker and greener, dry ones straw
    green_f = np.array([0.88, 0.98, 0.88])
    dry_f = np.array([1.22, 1.10, 1.06]) ** dry_k
    straw_f = np.array([1.6, 1.35, 1.3])
    n1 = noise(0.045, 3.0, 0.55, 0.3)
    swath = mixc(green_f, dry_f, mrange(n1, 0.38, 0.66, 0.0, 1.0, smooth=True))
    n2 = noise(0.26, 2.0)
    mott = mrange(n2, 0.3, 0.7, 0.9, 1.1)
    n5 = noise(0.55, 3.0, 0.6, 0.5)
    spot = mrange(n5, 0.68, 0.76, 0.0, 0.5, smooth=True)             # a few straw-dead spots
    field = mixc(swath, straw_f, spot)
    field = scale(field, mott)
    n3, n4 = noise(1.3, 2.0), noise(34.0, 1.0)
    h = N("ShaderNodeMath"); h.operation = "MULTIPLY_ADD"
    nt.links.new(n3, h.inputs[0]); h.inputs[1].default_value = 0.3; nt.links.new(n4, h.inputs[2])
    if relative:
        return field, h.outputs[0]
    # the ground: far = the canopy as a whole x field x speckle (a lit canopy reflects ~0.45 x its blades' mean albedo -
    # shadowed gaps, edge-on and backlit blades - and less saturated); near = thatch / soil / moss
    m0 = lawn_mean_lin()
    lum = float(m0 @ np.array([0.2126, 0.7152, 0.0722]))
    mean = (lum + (m0 - lum) * 0.7) * 0.45
    far = N("ShaderNodeVectorMath"); far.operation = "MULTIPLY"
    far.inputs[0].default_value = tuple(float(v) for v in mean)
    nt.links.new(field, far.inputs[1])
    speck = mrange(n4, 0.3, 0.7, 0.8, 1.18)
    far_c = scale(far.outputs["Vector"], speck)
    far_c = scale(far_c, mrange(noise(3.2, 3.0, 0.6), 0.3, 0.7, 0.84, 1.14))   # tufts and thin spots read from afar
    far_c = scale(far_c, mrange(noise(0.9, 2.0), 0.3, 0.7, 0.9, 1.1))
    nb = noise(2.2, 4.0, 0.6, 0.4)
    near = mixc(_lin(BLADES["soil"]), _lin(BLADES["thatch"]), mrange(nb, 0.35, 0.65, 0.0, 1.0))
    near = mixc(near, _lin(BLADES["moss"]), mrange(noise(0.8, 2.0), 0.55, 0.75, 0.0, 0.6, smooth=True))
    near = scale(near, mrange(noise(9.0, 2.0), 0.3, 0.7, 0.8, 1.2))
    cd = N("ShaderNodeCameraData")
    reach = float(CFG["grass_reach"])
    t = mrange(cd.outputs["View Distance"], reach - 9.0, reach - 1.0, 0.0, 1.0, smooth=True)
    if key == "ground":                                               # the far field beyond the fences: no blades ever
        return far_c, h.outputs[0]
    if key == "groundcover":                                          # the bed: soil + leaf litter, dark green mats
        mats_ = mixc(near, np.array([v for v in _lin(BLADES["gc"][1])]) * 0.6, mrange(noise(1.6, 3.0, 0.6), 0.45, 0.6, 0.0, 1.0, smooth=True))
        return mats_, h.outputs[0]
    return mixc(near, far_c, t), h.outputs[0]
