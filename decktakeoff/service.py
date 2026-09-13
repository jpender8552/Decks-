"""HTTP service.  uvicorn decktakeoff.service:app --port 8000
POST /takeoff      {spec: {...}, details?: "...", price?: bool}          -> takeoff JSON (+ markdown)
POST /intake       multipart: image=<file>, details=<text>, spec?=<json>  -> spec read from the drawing + the takeoff
POST /spec/parse   {details: "..."}                                        -> DeckSpec from plain English
GET  /health
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import run
from .intake import parse_details, spec_from_drawing
from .report import gsx_job_block, order_csv, quote_markdown, takeoff_json, takeoff_markdown
from .spec import DeckSpec

app = FastAPI(title="Deck Takeoff Service", version="0.1.0")


class TakeoffRequest(BaseModel):
    spec: Optional[dict] = None
    details: Optional[str] = None
    price: bool = False
    gsx: bool = False


def _run(spec: DeckSpec, with_price: bool, gsx: bool) -> dict:
    t, f, p = run(spec, with_pricing=with_price)
    out = takeoff_json(t, f, p)
    out["markdown"] = takeoff_markdown(t, f, p)
    out["order_csv"] = order_csv(t)
    if p is not None:
        out["quote_markdown"] = quote_markdown(t, p)
    if gsx:
        out["gsx_job_block"] = gsx_job_block(t)
    return out


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/spec/parse")
def spec_parse(req: TakeoffRequest):
    if not req.details:
        raise HTTPException(400, "details required")
    return parse_details(req.details, req.spec).to_dict()


@app.post("/takeoff")
def takeoff(req: TakeoffRequest):
    if req.spec is None and not req.details:
        raise HTTPException(400, "spec or details required")
    try:
        spec = parse_details(req.details, req.spec) if req.details else DeckSpec.from_dict(req.spec)
        return _run(spec, req.price, req.gsx)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))


@app.post("/intake")
async def intake(image: UploadFile = File(...), details: str = Form(""), spec: str = Form(""), price: bool = Form(False)):
    base = json.loads(spec) if spec else None
    suffix = Path(image.filename or "drawing.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await image.read())
        path = tmp.name
    try:
        sp = spec_from_drawing(path, details, base)
    except Exception as e:  # model / network errors surface as 502 with the reason
        raise HTTPException(502, f"drawing intake failed: {e}")
    finally:
        Path(path).unlink(missing_ok=True)
    out = _run(sp, price, False)
    out["spec_read"] = sp.to_dict()
    return out
