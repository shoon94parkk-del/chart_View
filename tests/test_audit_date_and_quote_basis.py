from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import market_service as market
import realtime_korea as korea


def stamp(value):
    return int(datetime.fromisoformat(value).timestamp())


@pytest.mark.parametrize('symbol,tz,times', [
    ('005930.KS', 'Asia/Seoul', ['2026-09-30T09:00:00+09:00', '2026-10-01T09:00:00+09:00', '2026-10-02T09:00:00+09:00']),
    ('AAPL', 'America/New_York', ['2026-09-30T09:30:00-04:00', '2026-10-01T09:30:00-04:00', '2026-10-02T09:30:00-04:00']),
])
def test_custom_range_clips_before_normalizing_returns(symbol, tz, times):
    chart = {'meta': {'exchangeTimezoneName': tz}, 'timestamp': list(map(stamp, times)),
             'indicators': {'quote': [{'close': [90, 100, 150]}], 'adjclose': [{'adjclose': [45, 50, 75]}]}}
    with patch.object(market, '_chart_result', return_value=chart), patch.object(market, '_local_names', return_value={}):
        result = market._load_compare_stock(symbol, '1mo', '2026-10-01', '2026-10-01', '1d')
    assert result['startDate'] == result['endDate'] == '2026-10-01'
    assert result['observations'] == 1
    assert result['return'] == 0
    assert result['data'] == [{'time': stamp(times[1]), 'price': 50, 'value': 0}]


def test_weekend_end_uses_last_actual_session_and_no_invented_points():
    chart = {'meta': {'exchangeTimezoneName': 'Asia/Seoul'},
             'timestamp': [stamp('2026-10-02T09:00:00+09:00'), stamp('2026-10-05T09:00:00+09:00')],
             'indicators': {'quote': [{'close': [100, 120]}]}}
    with patch.object(market, '_chart_result', return_value=chart), patch.object(market, '_local_names', return_value={}):
        result = market._load_compare_stock('005930.KS', '1mo', '2026-10-02', '2026-10-04', '1d')
    assert result['endDate'] == '2026-10-02'
    assert result['observations'] == 1


@pytest.mark.parametrize('symbol,expected', [
    ('005930.KS', ['2026-09-30T15:00:00+00:00', '2026-10-01T15:00:00+00:00']),
    ('AAPL', ['2026-10-01T04:00:00+00:00', '2026-10-02T04:00:00+00:00']),
])
def test_provider_exclusive_bounds_are_local_calendar_days(symbol, expected):
    calls = []
    with patch.object(market, '_http_json', side_effect=lambda url, params: calls.append(params) or {'chart': {'result': [{'meta': {'currency': 'USD'}}]}}):
        market._chart_result(symbol, start='2026-10-01', end='2026-10-01')
    assert [calls[0]['period1'], calls[0]['period2']] == list(map(stamp, expected))


def test_closed_status_does_not_turn_late_latest_quote_into_regular_close():
    latest = korea._quote_session_fields('CLOSE', '2026-10-06T20:20:00+09:00')
    assert latest['priceBasis'] == 'provider_latest'
    assert latest['sessionType'] != 'regular'
    assert korea._quote_session_fields('CLOSE', None)['priceBasis'] == 'provider_latest'
    assert korea._quote_session_fields('CLOSE', '2026-10-06T15:30:00+09:00')['priceBasis'] == 'regular_close'
