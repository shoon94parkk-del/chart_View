import pandas as pd
import pytest

from guru_extensions import technical_metrics
from scripts.generate_guru_market import frame_bars
from scripts.generate_screener import extract_frame


def history(count=310):
    dates=pd.bdate_range(end='2026-10-07',periods=count)
    return pd.DataFrame({'Close':[1000+i for i in range(count)],
                         'High':[1010+i for i in range(count)],
                         'Low':[990+i for i in range(count)],
                         'Volume':[10000+i for i in range(count)]},index=dates)


def test_shared_batch_index_does_not_discard_sufficient_newer_listing_history():
    mature=history(420); newer=history(310)
    batch=pd.concat({'000001.KS':mature,'000002.KS':newer},axis=1)
    raw=extract_frame(batch,'000002.KS')
    assert raw.iloc[:110].isna().all(axis=1).all()
    bars=frame_bars(raw,'2026-10-07')
    assert bars==frame_bars(newer,'2026-10-07')
    assert len(bars)==273
    assert bars[-1]==['2026-10-07',1309,1319,1299,10309]
    assert technical_metrics(bars,'2026-10-07')['barCount']==273


def test_leading_padding_does_not_fabricate_253_actual_sessions():
    batch=pd.concat({'old':history(420),'ipo':history(252)},axis=1)
    assert frame_bars(extract_frame(batch,'ipo'),'2026-10-07') is None


@pytest.mark.parametrize('field',['Close','High','Low','Volume'])
def test_partial_source_rows_remain_invalid(field):
    raw=history();raw.loc[raw.index[0],field]=float('nan')
    assert frame_bars(raw,'2026-10-07') is None


def test_empty_gap_after_first_source_observation_remains_invalid():
    raw=history();raw.loc[raw.index[150],:]=float('nan')
    assert frame_bars(raw,'2026-10-07') is None


def test_missing_target_date_and_invalid_price_range_remain_invalid():
    raw=history()
    assert frame_bars(raw.iloc[:-1],'2026-10-07') is None
    raw.loc[raw.index[-1],'High']=1
    assert frame_bars(raw,'2026-10-07') is None


def test_future_session_is_not_used_and_source_frame_is_unchanged():
    raw=history()
    expected=frame_bars(raw,'2026-10-07')
    raw.loc[pd.Timestamp('2026-10-08')]=[999999,1000000,999998,999999]
    before=raw.copy(deep=True)
    assert frame_bars(raw,'2026-10-07')==expected
    pd.testing.assert_frame_equal(raw,before)
