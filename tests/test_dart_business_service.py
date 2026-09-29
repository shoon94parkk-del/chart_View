import pandas as pd

from dart_business_service import extract_revenue_mix, _stock_code, _viewer_nodes


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

def test_parses_current_dart_assignment_style_viewer_nodes():
    script = """
    var node2 = {};
    node2['text'] = "3. 주요 제품 및 서비스";
    node2['id'] = "23";
    node2['rcpNo'] = "20260515000361";
    node2['dcmNo'] = "11381582";
    node2['eleId'] = "23";
    node2['offset'] = "456789";
    node2['length'] = "12345";
    node2['dtd'] = "dart4.xsd";
    node1['children'].push(node2);
    """
    nodes = _viewer_nodes(script)
    assert len(nodes) == 1
    assert nodes[0]["title"] == "3. 주요 제품 및 서비스"
    assert nodes[0]["rcp"] == "20260515000361"
    assert nodes[0]["dcm"] == "11381582"
    assert nodes[0]["ele"] == "23"

def test_parses_dart_first_body_row_as_embedded_header():
    html = """
    <table>
      <tbody>
        <tr><td>구 분</td><td>품 목</td><td>매출액</td><td>비율</td></tr>
        <tr><td>의료진단기기 (ACCUNIQ)</td><td>체성분분석기</td><td>9591529</td><td>31.12%</td></tr>
        <tr><td>의료진단기기 (ACCUNIQ)</td><td>전자동혈압계</td><td>3882692</td><td>12.60%</td></tr>
        <tr><td>보조공학기기 (HIMS)</td><td>점자정보단말기</td><td>9551554</td><td>30.99%</td></tr>
        <tr><td>보조공학기기 (HIMS)</td><td>음성독서기</td><td>1610481</td><td>5.22%</td></tr>
        <tr><td>합 계</td><td>합 계</td><td>30824696</td><td>100.00%</td></tr>
      </tbody>
    </table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "제품별 매출"
    assert result["topItem"]["name"] == "체성분분석기"
    assert result["topItem"]["share"] == 31.12
    assert result["items"][1]["name"] == "점자정보단말기"
    assert result["items"][1]["share"] == 30.99

def test_prefers_clean_product_mix_over_double_counted_sales_channel_table():
    clean = """
    <table><tbody>
      <tr><td>구 분</td><td>품 목</td><td>매출액</td><td>비율</td></tr>
      <tr><td>의료진단기기</td><td>체성분분석기</td><td>9591529</td><td>31.12%</td></tr>
      <tr><td>의료진단기기</td><td>전자동혈압계</td><td>3882692</td><td>12.60%</td></tr>
      <tr><td>보조공학기기</td><td>점자정보단말기</td><td>9551554</td><td>30.99%</td></tr>
      <tr><td>합 계</td><td>합 계</td><td>30824696</td><td>100.00%</td></tr>
    </tbody></table>
    """
    doubled = """
    <table><tbody>
      <tr><td>매출유형</td><td>품목</td><td>구분</td><td>판매경로</td><td>매출액</td><td>비중</td></tr>
      <tr><td>제품</td><td>체성분분석기</td><td>국내</td><td>직접판매</td><td>956596</td><td>5.60%</td></tr>
      <tr><td>제품</td><td>체성분분석기</td><td>수출</td><td>딜러</td><td>7816305</td><td>45.76%</td></tr>
      <tr><td>제품</td><td>체성분분석기</td><td>소계</td><td>소계</td><td>9591529</td><td>56.16%</td></tr>
      <tr><td>제품</td><td>혈압계</td><td>국내</td><td>직접판매</td><td>2319801</td><td>13.58%</td></tr>
      <tr><td>제품</td><td>혈압계</td><td>소계</td><td>소계</td><td>3882692</td><td>22.73%</td></tr>
    </tbody></table>
    """
    result = extract_revenue_mix([doubled, clean], 2025)
    assert result is not None
    assert result["topItem"]["name"] == "체성분분석기"
    assert result["topItem"]["share"] == 31.12
    assert all(row["share"] <= 100 for row in result["items"])


def test_excludes_named_sales_total_rows():
    html = """
    <table><tbody>
      <tr><td>품목</td><td>매출액</td><td>비중</td></tr>
      <tr><td>제품A</td><td>60</td><td>60%</td></tr>
      <tr><td>제품B</td><td>40</td><td>40%</td></tr>
      <tr><td>매출합계</td><td>100</td><td>100%</td></tr>
    </tbody></table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert [row["name"] for row in result["items"]] == ["제품A", "제품B"]

def test_normalizes_compound_dart_revenue_unit():
    html = """
    <html><body>
      <p>(단위 : 천원, %)</p>
      <table>
        <thead><tr><th>품목</th><th>매출액</th><th>비중</th></tr></thead>
        <tbody>
          <tr><td>A</td><td>600</td><td>60%</td></tr>
          <tr><td>B</td><td>400</td><td>40%</td></tr>
          <tr><td>합계</td><td>1000</td><td>100%</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["unit"] == "천원"

def test_recovers_hlbpep_rowspan_revenue_mix_without_double_counting():
    html = """
    <html><body>
      <p>(단위 : 백만원)</p>
      <table>
        <thead>
          <tr><th>구분</th><th>품목</th><th>내용</th><th>주요 수요처</th><th>매출액</th><th>비율(%)</th></tr>
        </thead>
        <tbody>
          <tr><td rowspan="6">의약용 펩타이드 소재</td><td>루프로렐린</td><td>치료제</td><td>국내외 제약사</td><td>244.0</td><td>4.92</td></tr>
          <tr><td>데스모프레신</td><td>치료제</td><td>국내외 제약사</td><td>991.1</td><td>19.97</td></tr>
          <tr><td>임상용 펩타이드</td><td>위탁생산</td><td>국내외 제약사</td><td>275.7</td><td>5.56</td></tr>
          <tr><td>기타 의약용 펩타이드</td><td>기타</td><td>국내외 제약사</td><td>-</td><td>-</td></tr>
          <tr><td>위탁 용역</td><td>CMC 등</td><td>국내외 제약사</td><td>358.3</td><td>7.22</td></tr>
          <tr><td>소 계</td><td>소 계</td><td>소 계</td><td>1869.1</td><td>37.67</td></tr>
          <tr><td rowspan="4">연구용 펩타이드 소재</td><td>주문자 펩타이드</td><td>주문 생산</td><td>제약사·대학</td><td rowspan="2">2688.7</td><td rowspan="2">54.19</td></tr>
          <tr><td>카탈로그 펩타이드</td><td>상용화 펩타이드</td><td>제약사·대학</td></tr>
          <tr><td>용역</td><td>연구 용역</td><td>제약사·대학</td><td>33.0</td><td>0.66</td></tr>
          <tr><td>소 계</td><td>소 계</td><td>소 계</td><td>2721.7</td><td>54.85</td></tr>
          <tr><td>상품 외</td><td>상품</td><td>화합물 라이브러리</td><td>제약사·대학</td><td>370.9</td><td>7.48</td></tr>
          <tr><td>합 계</td><td>합 계</td><td>합 계</td><td>합 계</td><td>4961.7</td><td>100.00</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "제품별 매출"
    assert result["unit"] == "백만원"
    assert result["topItem"]["name"] == "주문자 펩타이드"
    assert result["topItem"]["share"] == 54.19
    assert all(row["name"] != "카탈로그 펩타이드" for row in result["items"])
    assert sum(row["share"] for row in result["items"]) <= 100.01

def test_extracts_samsung_segment_mix_with_internal_transaction_elimination():
    html = """
    <html><body>
      <p>(단위 : 억원, %)</p>
      <table>
        <thead><tr><th>부 문</th><th>주요 제품</th><th>매출액</th><th>비중</th></tr></thead>
        <tbody>
          <tr><td>DX 부문</td><td>TV, 모니터, 냉장고, 스마트폰 등</td><td>1,879,673</td><td>56.3%</td></tr>
          <tr><td>DS 부문</td><td>DRAM, NAND Flash, 모바일AP 등</td><td>1,301,282</td><td>39.0%</td></tr>
          <tr><td>SDC</td><td>스마트폰용 OLED패널 등</td><td>298,417</td><td>8.9%</td></tr>
          <tr><td>Harman</td><td>디지털 콕핏, 카오디오 등</td><td>157,833</td><td>4.7%</td></tr>
          <tr><td>기타</td><td>부문간 내부거래 제거 등</td><td>△301,146</td><td>△8.9%</td></tr>
          <tr><td>총 계</td><td>총 계</td><td>3,336,059</td><td>100.00%</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result=extract_revenue_mix([html],2025)
    assert result is not None
    assert result["basis"] == "사업부문별 매출"
    assert result["unit"] == "억원"
    assert result["topItem"]["name"] == "DX 부문"
    assert result["topItem"]["share"] == 56.3
    assert "스마트폰" in result["topItem"]["detail"]
    assert all(row["name"] != "기타" for row in result["items"])


def test_triangle_marker_is_parsed_as_negative():
    from dart_business_service import _number
    assert _number("△301,146") == -301146
    assert _number("△8.9%") == -8.9

