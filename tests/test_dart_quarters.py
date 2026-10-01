from unittest.mock import patch
import dart_quarter_service as service

def packet(year,q,sales,profit,**extra):
 return dict(year=year,quarter=q,revenue=sales,operatingProfit=profit,currency='KRW',basis='CFS',rceptNo='20260814001146',**extra)

def test_q4_difference_and_ttm_require_consecutive_matching_quarters():
 packets=[packet(2025,3,90,9),packet(2025,4,120,12),packet(2026,1,35,4,singleQuarter={'revenue':35,'operatingProfit':4}),packet(2026,2,80,10,singleQuarter={'revenue':45,'operatingProfit':6}),packet(2026,3,140,18,singleQuarter={'revenue':60,'operatingProfit':8})]
 result=service.assemble_quarters(packets,(2026,3))
 assert result['quarters'][-4]['revenue']==30
 assert result['quarters'][-4]['method']=='annual_minus_q3'
 assert result['ttm']['revenue']==170
 assert result['ttm']['operatingProfit']==21
 assert len(result['quarters'])==8
 assert len(result['quarters'][-4]['sourceUrls'])==2

def test_missing_quarter_is_not_zero_and_blocks_ttm():
 result=service.assemble_quarters([packet(2026,2,80,10)],(2026,2))
 assert result['quarters'][-1]['revenue'] is None
 assert result['ttm'] is None
 assert result['quarters'][-1]['available'] is False

def test_direct_quarter_and_year_ago_growth_with_loss():
 result=service.assemble_quarters([packet(2025,2,70,5,singleQuarter={'revenue':40,'operatingProfit':-2}),packet(2026,2,80,10,singleQuarter={'revenue':60,'operatingProfit':6})],(2026,2))
 assert result['quarters'][-1]['revenueGrowth']==50
 assert result['quarters'][-1]['profitGrowth'] is None
 assert result['quarters'][-1]['priorOperatingProfit']==-2

def test_mixed_basis_and_currency_never_subtracted():
 a=packet(2025,3,90,9);b=packet(2025,4,120,12);b['basis']='OFS'
 assert service.assemble_quarters([a,b],(2025,4))['quarters'][-1]['revenue'] is None
 b['basis']='CFS';b['currency']='USD'
 assert service.assemble_quarters([a,b],(2025,4))['quarters'][-1]['revenue'] is None

def test_interim_parser_preserves_direct_and_cumulative_values():
 from dart_financial_service import parse_financial_statement
 common={'sj_div':'IS','account_detail':'-','rcept_no':'20260814001146','currency':'KRW'}
 rows=[dict(common,account_id='ifrs-full_Revenue',account_nm='매출액',thstrm_add_amount='80',thstrm_amount='45'),dict(common,account_id='dart_OperatingIncomeLoss',account_nm='영업이익',thstrm_add_amount='10',thstrm_amount='6')]
 row=parse_financial_statement(rows,2026,'11012')
 assert row['revenue']==80
 assert row['singleQuarter']=={'revenue':45,'operatingProfit':6}

def test_cold_lookup_returns_loading_and_schedules_only_one_collection():
 service._CACHE.clear();service._RUNNING.clear()
 with patch.object(service,'_read',return_value=None),patch.object(service._POOL,'submit') as submit:
  assert service.fetch_quarters('005930.KS')['state']=='loading'
  assert service.fetch_quarters('005930.KS')['state']=='loading'
  assert submit.call_count==1
 service._RUNNING.clear()

def test_invalid_ticker_is_client_error_and_stale_success_survives_failure():
 from fastapi import HTTPException
 import pytest
 with pytest.raises(HTTPException) as error:service.financial_quarters('AAPLxx')
 assert error.value.status_code==400
 service._CACHE['005930']=(0,{'stockCode':'005930','available':True,'quarters':[{'year':2026}]})
 with patch.object(service,'_collect',return_value={'available':False,'state':'error'}):
  service._refresh('005930','005930.KS')
 assert service._CACHE['005930'][1]['available'] is True
 assert service._CACHE['005930'][1]['refreshFailed'] is True
 service._CACHE.clear()

def test_entire_failed_provider_refresh_keeps_old_success_timestamp_and_marks_failure():
 from datetime import datetime
 packets=[packet(y,q,100,10,singleQuarter={'revenue':25,'operatingProfit':2}) for y,q in service.slots((2026,2),13)]
 old={'packets':packets,'available':True,'checkedAt':'2026-08-15T00:00:00+09:00'}
 with patch.dict(service.os.environ,{'DART_API_KEY':'test-not-a-real-key'}),patch.object(service,'_corp_codes',return_value={'005930':{'corpCode':'12345678'}}),patch.object(service,'_static_row',return_value={'available':True,'basis':'연결재무제표'}),patch.object(service,'_read',return_value=old),patch.object(service,'_get_statement',side_effect=TimeoutError),patch.object(service,'datetime') as clock:
  clock.now.return_value=datetime(2026,10,2,tzinfo=service.KST)
  row=service._collect('005930','005930.KS')
 assert row['available'] is True
 assert row['refreshFailed'] is True
 assert row['checkedAt']==old['checkedAt']
