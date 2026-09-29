import pandas as pd

from dart_business_service import extract_revenue_mix, _stock_code


def test_extracts_top_revenue_product_and_share_from_explicit_sales_table():
    html = """
    <html><body>
      <p>(단위 : 백만원)</p>
      <table>
        <thead><tr><th>품목</th><th>2025년 매출액</th><th>매출비중</th></tr></thead>
        <tbody>
          <tr><td>체성분측정기</td><td>48,000</td><td>48.0%</td></tr>
          <tr><td>혈압계</td><td>31,000</td><td>31.0%</td></tr>
          <tr><td>전자정보단말기</td><td>21,000</td><td>21.0%</td></tr>
          <tr><td>합계</td><td>100,000</td><td>100%</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "제품별 매출"
    assert result["unit"] == "백만원"
    assert result["topItem"]["name"] == "체성분측정기"
    assert result["topItem"]["share"] == 48.0
    assert [row["name"] for row in result["items"][:3]] == ["체성분측정기", "혈압계", "전자정보단말기"]


def test_computes_share_only_when_explicit_sales_amount_exists():
    html = """
    <table>
      <thead><tr><th>사업부문</th><th>매출액</th></tr></thead>
      <tbody>
        <tr><td>반도체 장비</td><td>700</td></tr>
        <tr><td>디스플레이 장비</td><td>300</td></tr>
        <tr><td>합계</td><td>1000</td></tr>
      </tbody>
    </table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "사업부문별 매출"
    assert result["topItem"]["share"] == 70.0


def test_rejects_non_revenue_tables_instead_of_guessing():
    html = """
    <table>
      <thead><tr><th>제품</th><th>생산능력</th></tr></thead>
      <tbody><tr><td>A</td><td>10</td></tr><tr><td>B</td><td>20</td></tr></tbody>
    </table>
    """
    assert extract_revenue_mix([html], 2025) is None


def test_rejects_overseas_tickers():
    try:
        _stock_code("NVDA")
        assert False, "expected ValueError"
    except ValueError:
        pass
