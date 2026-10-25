"""Small Home projection of the existing published close-based screener."""
import asyncio
import math
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()
_SOURCE_FIELDS = ("tradeDate", "updated", "source", "status", "pending", "refreshing",
                  "refreshScheduled", "error", "available", "generatedAt", "asOf", "basis", "dataSource")
# Match JS Number(string), rather than Python float's extra underscore/Unicode
# digit syntax. JS trim includes BOM but excludes U+0085.
_JS_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_RADIX = re.compile(r"0(?:[xX][0-9a-fA-F]+|[bB][01]+|[oO][0-7]+)")


def _volume_surge(value):
    # JSON arrays coerce to comma-joined strings in JS. Only a singleton chain
    # can yield a number >=2; empty/multiple items and objects cannot match.
    while isinstance(value, list):
        if len(value) != 1:
            return False
        value = value[0]
    if isinstance(value, str):
        value = value.strip(_JS_SPACE)
        if _RADIX.fullmatch(value):
            value = int(value[2:], {"x": 16, "b": 2, "o": 8}[value[1].lower()])
        elif _DECIMAL.fullmatch(value):
            value = float(value)
        else:
            return False
    if not isinstance(value, (int, float)):
        return False
    try:
        number = float(value)
        return math.isfinite(number) and number >= 2
    except OverflowError:
        return False


@router.get("/api/home-screener-summary")
async def home_screener_summary():
    from published_data import get_published_data

    try:
        payload, source = await asyncio.to_thread(get_published_data, "screener.json")
        stocks = payload.get("stocks")
        if not isinstance(stocks, list) or any(not isinstance(row, dict) for row in stocks):
            raise ValueError("invalid screener universe")
        summary = {key: payload[key] for key in _SOURCE_FIELDS if key in payload}
        summary.update(schemaVersion=1, counts={"volumeSurge": sum(_volume_surge(row.get("volumeRatio")) for row in stocks)})
    except Exception:
        raise HTTPException(status_code=503, detail="Home screener summary unavailable") from None
    return JSONResponse(content=summary, headers={
        "Cache-Control": "no-store, max-age=0, must-revalidate",
        "X-ChartView-Data-Source": source,
        "X-ChartView-Data-AsOf": str(payload.get("updated") or payload.get("generatedAt") or "")[:48],
    })
