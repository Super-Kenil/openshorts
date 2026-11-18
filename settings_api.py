import asyncio
import json
import os
import re
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request

import caption_style
import db

router = APIRouter()

_KEY = re.compile(r"^[a-z0-9_.]{1,60}$")
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "::1")
MAX_VALUE_BYTES = 20_000
MAX_KEYS = 200


def _guard(request: Request):
    if os.environ.get("BILLING_ENABLED", "").lower() in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="Not found")
    origin = request.headers.get("origin")
    if origin and (urlparse(origin).hostname or "") not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="Only the local dashboard can use this")


@router.get("/api/settings")
async def get_settings(request: Request):
    _guard(request)
    return {"settings": await asyncio.to_thread(db.all_settings)}


@router.put("/api/settings")
async def put_settings(request: Request):
    _guard(request)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Send a JSON object")
    items = body.get("settings") if isinstance(body, dict) else None
    if not isinstance(items, dict) or len(items) > MAX_KEYS:
        raise HTTPException(status_code=400, detail="Send {\"settings\": {key: value}}")
    for key, value in items.items():
        if not _KEY.match(str(key)):
            raise HTTPException(status_code=400, detail=f"Bad setting name: {key[:40]}")
        if len(json.dumps(value)) > MAX_VALUE_BYTES:
            raise HTTPException(status_code=400, detail=f"{key} is too large")

    def write():
        for key, value in items.items():
            if value is None:
                db.delete_setting(key)
            else:
                db.set_setting(key, value)
    await asyncio.to_thread(write)
    return {"ok": True}


@router.post("/api/caption-preview")
async def caption_preview(request: Request):
    _guard(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    style = body.get("style") if isinstance(body, dict) else None
    text = body.get("text") if isinstance(body, dict) else None
    try:
        frames = await asyncio.to_thread(caption_style.render_preview, style or {}, text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)[:200]}")
    return {"frames": frames, "style": caption_style.resolve(style or {})}
