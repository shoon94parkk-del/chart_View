import asyncio
import threading
import time
import pytest
from fastapi import HTTPException, Response
import export_momentum_service as service


def test_slow_cold_refresh_has_a_response_budget_and_one_shared_worker(monkeypatch):
    gate=threading.Event();calls=[]
    def build():
        calls.append(True)
        assert gate.wait(3)
        return {'period':'2026-10','checkpoints':[{'stage':10}],'meta':{}}
    monkeypatch.setattr(service,'_build_provisional_radar',build)
    monkeypatch.setattr(service,'_PROVISIONAL_CACHE',{'data':None,'timestamp':0,'lastError':None})
    monkeypatch.setattr(service,'_PROVISIONAL_CACHE_LOCK',asyncio.Lock())
    monkeypatch.setattr(service,'PROVISIONAL_RESPONSE_TIMEOUT_SEC',.02,raising=False)
    monkeypatch.setattr(service,'_PROVISIONAL_REFRESH_TASK',None,raising=False)
    async def run():
        try:
            responses=await asyncio.wait_for(asyncio.gather(*[service.export_momentum_provisional(Response()) for _ in range(3)],return_exceptions=True),.3)
            assert all(isinstance(row,HTTPException) and row.status_code==503 for row in responses)
            assert len(calls)==1
            gate.set()
            await service._PROVISIONAL_REFRESH_TASK
            actual=await service.export_momentum_provisional(Response())
            assert actual['period']=='2026-10'
            assert actual['meta']['cacheStatus']=='fresh'
            assert len(calls)==1
        finally:gate.set()
    asyncio.run(run())


def test_timeout_retains_real_stale_data_and_refresh_keeps_running(monkeypatch):
    old={'period':'2026-09','checkpoints':[{'stage':20}],'meta':{}}
    monkeypatch.setattr(service,'_PROVISIONAL_CACHE',{'data':old,'timestamp':0,'lastError':None})
    monkeypatch.setattr(service,'PROVISIONAL_RESPONSE_TIMEOUT_SEC',.01,raising=False)
    monkeypatch.setattr(service,'_PROVISIONAL_REFRESH_TASK',None,raising=False)
    async def run():
        gate=asyncio.Event()
        async def refresh():
            await gate.wait()
            return old
        monkeypatch.setattr(service,'_refresh_provisional_radar',refresh)
        try:
            actual=await asyncio.wait_for(service.export_momentum_provisional(Response()),.2)
            assert actual['period']=='2026-09'
            assert actual['meta']['cacheStatus']=='stale-error'
            assert old['meta']=={}
            assert not service._PROVISIONAL_REFRESH_TASK.done()
        finally:
            gate.set()
            if service._PROVISIONAL_REFRESH_TASK:await service._PROVISIONAL_REFRESH_TASK
    asyncio.run(run())
