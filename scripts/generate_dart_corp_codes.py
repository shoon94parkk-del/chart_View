"""Generate a local OpenDART stock-code -> corp-code cache.

The DART corp code itself is public metadata. The API key is used only by the
GitHub runner to download the official archive; it is never written to output.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import requests

KST=timezone(timedelta(hours=9))
OUT=Path("static/data/dart_corp_codes.json")
URL="https://opendart.fss.or.kr/api/corpCode.xml"


def clean(value) -> str:
    return str(value or "").strip()


def build() -> None:
    api_key=clean(os.environ.get("DART_API_KEY"))
    if not api_key:
        raise RuntimeError("DART_API_KEY is required")
    response=requests.get(
        URL,
        params={"crtfc_key":api_key},
        headers={"User-Agent":"ChartView/dart-corp-cache"},
        timeout=300,
    )
    response.raise_for_status()
    archive=zipfile.ZipFile(BytesIO(response.content))
    root=ET.fromstring(archive.read(archive.namelist()[0]))

    companies={}
    for node in root.findall("list"):
        stock_code=clean(node.findtext("stock_code"))
        corp_code=clean(node.findtext("corp_code"))
        corp_name=clean(node.findtext("corp_name"))
        if len(stock_code)!=6 or len(corp_code)!=8:
            continue
        companies[stock_code]={
            "corpCode":corp_code,
            "corpName":corp_name,
        }

    if len(companies)<2000:
        raise RuntimeError(f"unexpected DART listed-company count: {len(companies)}")

    payload={
        "updated":datetime.now(KST).isoformat(timespec="seconds"),
        "source":"OpenDART corpCode.xml",
        "count":len(companies),
        "companies":companies,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(
        json.dumps(payload,ensure_ascii=False,separators=(",",":")),
        encoding="utf-8",
    )
    print("Saved",len(companies),"DART listed-company corp codes")


if __name__=="__main__":
    build()
