"""Cache-only evidence retrieval; browser visits never trigger DART collection."""
from __future__ import annotations
import json
from pathlib import Path
import re
import threading

from fastapi import APIRouter, HTTPException, Query

router=APIRouter()
EVIDENCE_PATH=Path(__file__).resolve().parent/'static/data/guru_evidence.json'
_cache_key=None
_cache={}
_lock=threading.Lock()


def get_guru_evidence(ticker: str, version: str) -> dict:
    global _cache_key, _cache
    if not re.fullmatch(r'\d{6}\.(KS|KQ)',ticker):
        raise HTTPException(400,detail={'code':'invalid_ticker'})
    try:
        stat=EVIDENCE_PATH.stat()
        key=(str(EVIDENCE_PATH),stat.st_mtime_ns,stat.st_size,stat.st_ino)
        with _lock:
            if key!=_cache_key or _cache.get('snapshotVersion')!=version:
                data=json.loads(EVIDENCE_PATH.read_text(encoding='utf-8'))
                if not isinstance(data.get('companies'),dict) or not data.get('snapshotVersion'): raise ValueError()
                _cache=data; _cache_key=key
            data=_cache
    except (OSError,ValueError,TypeError):
        raise HTTPException(503,detail={'code':'evidence_unavailable'}) from None
    if data['snapshotVersion']!=version:
        raise HTTPException(409,detail={'code':'snapshot_changed','currentVersion':data['snapshotVersion']})
    row=data['companies'].get(ticker)
    if not row: raise HTTPException(404,detail={'code':'evidence_not_found'})
    return {**row,'snapshotVersion':data['snapshotVersion'],'tradeDate':data.get('tradeDate'),
            'criteriaVersion':data.get('criteriaVersion')}


@router.get('/api/guru-investing/{ticker}')
def guru_evidence(ticker: str, version: str=Query(...,max_length=64)):
    return get_guru_evidence(ticker,version)
