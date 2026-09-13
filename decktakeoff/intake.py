"""Intake: turn what Jade gives us — a drawing/photo plus a few lines of details — into a DeckSpec.

Two paths:
  * parse_details(text)            — deterministic regex parse of plain-English details ("12x16, 30 in high, Prime+ Coconut Husk, Fulton black, 4 steps front").
  * spec_from_drawing(image, text) — Claude reads the drawing (dimensions, ledger, beam, stairs, rail, notes) and returns a
                                     DeckSpec-shaped JSON via structured outputs. Needs ANTHROPIC_API_KEY (or `ant auth login`).
The engine never trusts the drawing silently: everything the model read is echoed in spec.source_notes for Jade to confirm.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Optional

from .catalog import DECKING
from .spec import DeckSpec
from .units import to_inches

# a single plan dimension: 12 · 12' · 12ft · 11'9 · 11'-9" · 11 ft 9 in · 15'7.5" · 15'-7 1/2"
_DIM1 = r"""\d+(?:\.\d+)?(?:\s*(?:'|ft|feet)\s*-?\s*(?:\d+(?:\.\d+)?(?:\s+\d+/\d+)?\s*(?:"|in|inches)?)?)?"""
_DIMPAIR = r"(?P<a>" + _DIM1 + r")\s*(?:deep|wide|long|out)?\s*(?:x|×|by)\s*(?P<b>" + _DIM1 + r")"


def _ft(s: str) -> float:
    """dimension text -> decimal feet (bare numbers are feet)."""
    s = s.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    return to_inches(s, "ft") / 12.0


def parse_details(text: str, base: Optional[dict] = None) -> DeckSpec:
    """Best-effort parse of free-text details into a spec dict merged over `base`."""
    d = json.loads(json.dumps(base)) if base else {}
    t = text or ""
    low = t.lower()
    g = d.setdefault("geometry", {})
    m = re.search(_DIMPAIR, low)
    if m:
        a, b = _ft(m.group("a")), _ft(m.group("b"))
        # convention: first number along the house (width), second out from the house (depth) unless told otherwise
        after_a = low[m.start("a"):m.start("b")]
        after_b = low[m.end():m.end() + 30]
        if re.search(r"deep|projection|out from", after_a) or re.search(r"^\s*'?\s*(?:wide|along the house)", after_b):
            a, b = b, a
        g["width_in"], g["depth_in"] = a * 12, b * 12
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\"|in(?:ch(?:es)?)?)\s*(?:high|tall|off (?:the )?grade|above grade)", low) or \
        re.search(r"(?:height|high|tall)\D{0,12}(\d+(?:\.\d+)?)\s*(?:\"|in|inch)", low)
    if m:
        g["height_in"] = float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:'|ft|feet)\s*(?:high|tall|off (?:the )?grade|above grade)", low)
    if m and "height_in" not in g:
        g["height_in"] = float(m.group(1)) * 12
    if re.search(r"free.?standing|floating|no ledger", low):
        g["attachment"] = "freestanding"
    if re.search(r"perpendicular|boards? run(?:ning)? (?:out|away)", low):
        g["board_direction"] = "perpendicular"
    if re.search(r"no picture ?frame|without (?:a )?picture ?frame", low):
        g["picture_frame"] = False
    # decking
    dk = d.setdefault("decking", {})
    for coll, f in sorted(DECKING.items(), key=lambda kv: -len(kv[0])):   # longest name first: "Prime+" before "Prime"
        if coll != "Wood" and re.search(r"(?<![a-z+])" + re.escape(coll.lower()) + r"(?![a-z+])", low) and "collection" not in dk:
            dk["collection"] = coll
    for coll, f in DECKING.items():
        for c in f["colors"]:
            if c.lower() in low and (dk.get("collection") in (None, coll) or c.lower() not in [x.lower() for x in DECKING.get(dk.get("collection", ""), {}).get("colors", [])]):
                dk["collection"], dk["color"] = coll, c
    if re.search(r"\bcedar\b|\bpt\b|pressure.?treated deck", low) and "collection" not in dk:
        dk["collection"], dk["color"] = "Wood", "Cedar"
    if re.search(r"square.?(?:edge|shoulder)", low):
        dk["profile"] = "square"
    if re.search(r"no fascia", low):
        dk["fascia"] = False
    # framing
    fr = d.setdefault("framing", {})
    m = re.search(r"\b(2x(?:6|8|10|12))\s*(?:joist|@)", low)
    if m:
        fr["joist_size"] = m.group(1)
    m = re.search(r"@?\s*(12|16|24)\s*(?:\"|in)?\s*(?:o\.?c\.?|on cent)", low)
    if m:
        fr["joist_spacing_in"] = float(m.group(1))
    if re.search(r"flush beam", low):
        fr["beams"] = [{"kind": "flush", "size": "(2)" + fr.get("joist_size", "2x10"), "species": "SYP", "setback_in": 0}]
    m = re.search(r"drop beam[^.]{0,20}?(\d+(?:\.\d+)?)\s*(?:'|ft|feet)\s*(?:back|cantilever|overhang)", low)
    if m:
        fr["beams"] = [{"kind": "drop", "size": "4x10", "species": "DF", "setback_in": float(m.group(1)) * 12}]
    m = re.search(r"\b((?:\(\d\))?\s?[46]x(?:8|10|12))\s*(?:df|doug|beam)", low)
    if m:
        fr.setdefault("beams", [{"kind": "drop", "size": "4x10", "species": "DF", "setback_in": 24}])
        fr["beams"][0]["size"] = m.group(1).replace(" ", "")
    if re.search(r"concrete (?:pier|footing|caisson)|sonotube|caisson", low):
        fr["footing_type"] = "concrete"
    if re.search(r"diamond pier", low):
        fr["footing_type"] = "diamond_pier"
    if re.search(r"\b(?:lag|1/2\" lag)", low):
        fr["ledger_fastener"] = "1/2 lag"
    # rail
    rl = d.setdefault("railing", {})
    if re.search(r"no rail|without rail", low):
        rl["system"] = "none"
    for sysn in ("Fulton", "Impression", "Classic Composite"):
        if sysn.lower() in low:
            rl["system"] = sysn
    for col in ("Black", "White", "Bronze", "Dark Bronze", "Kona"):
        if re.search(r"\b" + col.lower() + r"\b(?: rail| fulton| posts?)?", low) and ("rail" in low or "fulton" in low):
            rl["color"] = col
    m = re.search(r"(42|36)\s*(?:\"|in)?\s*(?:rail|guard)", low)
    if m:
        rl["height_in"] = float(m.group(1))
    m = re.search(r"open(?:ing)?[^.]{0,30}?(left|right|front)", low)
    # stairs
    sts = []
    for m in re.finditer(r"(\d+)\s*(?:steps?|risers?|stairs?)(?:[^.]{0,30}?(?:on|off|at) the (left|right|front))?", low):
        sts.append({"side": m.group(2) or "front", "width_in": 48.0})
    if not sts and re.search(r"\bstairs?\b|\bsteps\b", low):
        m2 = re.search(r"stairs?[^.]{0,30}?(left|right|front)", low)
        sts.append({"side": m2.group(1) if m2 else "front", "width_in": 48.0})
    m = re.search(r"(\d+)\s*(?:\"|in|inch|')\s*wide (?:stair|step)", low)
    if m and sts:
        w = float(m.group(1)); sts[0]["width_in"] = w * 12 if w < 10 else w
    if sts:
        d["stairs"] = sts
    ex = d.setdefault("extras", {})
    if re.search(r"demo|tear.?out|remove (?:the )?(?:old|existing)", low):
        ex["demo_existing"] = True
    if "hot tub" in low or "spa" in low.split():
        ex["hot_tub"] = True
    if re.search(r"brick|stone veneer", low):
        ex["ledger_on_brick_veneer"] = True
    site = d.setdefault("site", {})
    m = re.search(r"snow\D{0,10}(\d+)\s*psf", low)
    if m:
        site["ground_snow_psf"] = float(m.group(1))
    m = re.search(r"wind\D{0,10}(\d+)\s*mph", low)
    if m:
        site["wind_speed_mph"] = float(m.group(1))
    if re.search(r"\bwui\b|fire zone|wildfire", low):
        site["wui_fire_zone"] = True
    m = re.search(r"frost\D{0,10}(\d+)\s*(?:\"|in)", low)
    if m:
        site["frost_depth_in"] = float(m.group(1))
    m = re.search(r"(?:rear|back) setback\D{0,6}(\d+(?:\.\d+)?)\s*(?:'|ft)", low)
    if m:
        site["rear_setback_required_ft"] = float(m.group(1))
    m = re.search(r"side setback\D{0,6}(\d+(?:\.\d+)?)\s*(?:'|ft)", low)
    if m:
        site["side_setback_required_ft"] = float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:'|ft)\s*(?:to|from) the (?:rear|back) (?:property )?line", low)
    if m:
        site["deck_to_rear_line_ft"] = float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:'|ft)\s*(?:to|from) the side (?:property )?line", low)
    if m:
        site["deck_to_side_line_ft"] = float(m.group(1))
    for city in ("thornton", "denver", "aurora", "westminster", "arvada", "broomfield", "northglenn", "commerce city", "brighton", "lakewood",
                 "littleton", "centennial", "parker", "castle rock", "boulder", "longmont", "golden", "erie", "firestone", "fort collins", "loveland", "colorado springs"):
        if city in low:
            site["city"] = city.title()
    spec = DeckSpec.from_dict(d)
    spec.source_notes.append("details parsed: " + t.strip()[:300])
    return spec


# ---------------------------------------------------------------- drawing intake (Claude vision)
SPEC_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["width_ft", "depth_ft", "height_in", "attachment", "board_direction", "picture_frame", "stairs", "rail_sides",
                 "rail_openings", "beam_kind", "beam_setback_ft", "decking_collection", "decking_color", "rail_system", "rail_color",
                 "notes", "confidence", "unreadable"],
    "properties": {
        "width_ft": {"type": "number", "description": "deck dimension along the house wall, in decimal feet, outside of frame"},
        "depth_ft": {"type": "number", "description": "deck dimension out from the house, decimal feet"},
        "height_in": {"type": "number", "description": "deck surface above grade in inches; 0 if not shown"},
        "attachment": {"type": "string", "enum": ["ledger", "freestanding", "unknown"]},
        "board_direction": {"type": "string", "enum": ["parallel", "perpendicular", "unknown"]},
        "picture_frame": {"type": "boolean"},
        "stairs": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["side", "width_in", "risers"],
                   "properties": {"side": {"type": "string", "enum": ["left", "right", "front"]}, "width_in": {"type": "number"}, "risers": {"type": "integer"}}}},
        "rail_sides": {"type": "array", "items": {"type": "string", "enum": ["left", "right", "front", "rear"]}},
        "rail_openings": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["side", "start_in", "length_in", "reason"],
                          "properties": {"side": {"type": "string"}, "start_in": {"type": "number"}, "length_in": {"type": "number"}, "reason": {"type": "string"}}}},
        "beam_kind": {"type": "string", "enum": ["drop", "flush", "unknown"]},
        "beam_setback_ft": {"type": "number", "description": "beam face back from the front rim (cantilever), decimal feet; -1 if not shown"},
        "decking_collection": {"type": "string"},
        "decking_color": {"type": "string"},
        "rail_system": {"type": "string"},
        "rail_color": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}, "description": "every dimension, callout, and assumption read from the drawing"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "unreadable": {"type": "array", "items": {"type": "string"}, "description": "things the drawing should show but you could not read"},
    },
}

_SYSTEM = """You read residential deck drawings, sketches and site photos for a deck builder's takeoff engine.
Conventions: 'left' and 'right' are as you stand in the yard facing the house. Width runs along the house; depth runs out from the house.
Report exactly what the drawing shows. Do not invent dimensions: if a value is not on the drawing, say so in `unreadable` and use 0 / -1 / 'unknown'.
Scale from labeled dimensions only, never from pixel measurements. List every number and callout you used in `notes`."""


def _image_block(path: str) -> dict:
    p = Path(path)
    mt = mimetypes.guess_type(p.name)[0] or "image/png"
    data = base64.standard_b64encode(p.read_bytes()).decode("utf-8")
    if mt == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": mt, "data": data}}
    return {"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}}


def read_drawing(image_path: str, details: str = "", model: str = "claude-opus-5") -> dict:
    """Ask Claude to read the drawing. Returns the raw extraction dict (SPEC_SCHEMA)."""
    import anthropic
    client = anthropic.Anthropic()
    content = [_image_block(image_path)]
    prompt = "Read this deck drawing and fill the schema."
    if details:
        prompt += f"\n\nThe builder's own details (these override the drawing where they conflict):\n{details}"
    content.append({"type": "text", "text": prompt})
    resp = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": SPEC_SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("the model declined to read this drawing")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return json.loads(text)


def spec_from_extraction(x: dict, details: str = "", base: Optional[dict] = None) -> DeckSpec:
    """Merge a drawing extraction with the typed details (details win) into a DeckSpec."""
    d = json.loads(json.dumps(base)) if base else {}
    g = d.setdefault("geometry", {})
    if x.get("width_ft", 0) > 0:
        g["width_in"] = x["width_ft"] * 12
    if x.get("depth_ft", 0) > 0:
        g["depth_in"] = x["depth_ft"] * 12
    if x.get("height_in", 0) > 0:
        g["height_in"] = x["height_in"]
    if x.get("attachment") in ("ledger", "freestanding"):
        g["attachment"] = x["attachment"]
    if x.get("board_direction") in ("parallel", "perpendicular"):
        g["board_direction"] = x["board_direction"]
    if "picture_frame" in x:
        g["picture_frame"] = bool(x["picture_frame"])
    fr = d.setdefault("framing", {})
    if x.get("beam_kind") in ("drop", "flush"):
        b = {"kind": x["beam_kind"], "size": "4x10" if x["beam_kind"] == "drop" else "(2)2x10", "species": "DF" if x["beam_kind"] == "drop" else "SYP"}
        if x.get("beam_setback_ft", -1) >= 0:
            b["setback_in"] = x["beam_setback_ft"] * 12
        fr["beams"] = [b]
    dk = d.setdefault("decking", {})
    if x.get("decking_collection") in DECKING:
        dk["collection"] = x["decking_collection"]
        if x.get("decking_color"):
            dk["color"] = x["decking_color"]
    rl = d.setdefault("railing", {})
    if x.get("rail_sides"):
        rl["sides"] = x["rail_sides"]
    if x.get("rail_openings"):
        rl["openings"] = x["rail_openings"]
    if x.get("rail_system"):
        rl["system"] = x["rail_system"]
    if x.get("rail_color"):
        rl["color"] = x["rail_color"]
    if x.get("stairs"):
        d["stairs"] = [{"side": s["side"], "width_in": s.get("width_in") or 48.0} for s in x["stairs"]]
    spec = parse_details(details, d) if details else DeckSpec.from_dict(d)
    spec.source_notes = [f"drawing read ({x.get('confidence', '?')} confidence): " + n for n in x.get("notes", [])] + \
                        [f"NOT on the drawing: {u}" for u in x.get("unreadable", [])] + spec.source_notes
    return spec


def spec_from_drawing(image_path: str, details: str = "", base: Optional[dict] = None, model: str = "claude-opus-5") -> DeckSpec:
    return spec_from_extraction(read_drawing(image_path, details, model), details, base)
