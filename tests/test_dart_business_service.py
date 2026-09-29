import pandas as pd

from dart_business_service import extract_revenue_mix, _stock_code, _viewer_nodes


def test_extracts_hanwha_style_period_segment_sales_with_consolidation_adjustment():
    html = """
    <p>(단위 : 백만원)</p><table><thead><tr>
      <th>사업부문</th><th>매출유형</th><th>품목</th><th>구분</th><th>제26기</th><th>제25기</th>
    </tr></thead><tbody>
      <tr><td>상선</td><td>제품</td><td>선박</td><td>수출</td><td>10,501,445</td><td>8,675,531</td></tr>
      <tr><td>상선</td><td>제품</td><td>선박</td><td>내수</td><td>21,920</td><td>82</td></tr>
      <tr><td>해양 및 특수선</td><td>제품</td><td>해양 구조물</td><td>수출</td><td>826,509</td><td>1,101,703</td></tr>
      <tr><td>해양 및 특수선</td><td>제품</td><td>해양 구조물</td><td>내수</td><td>1,204,398</td><td>1,041,865</td></tr>
      <tr><td>E&amp;I</td><td>제품</td><td>플랜트</td><td>플랜트</td><td>819,373</td><td>336,815</td></tr>
      <tr><td>기타</td><td>기타</td><td>기타</td><td>기타</td><td>140,694</td><td>95,358</td></tr>
      <tr><td>연결조정</td><td>-</td><td>-</td><td>-</td><td>(730,827)</td><td>(475,349)</td></tr>
      <tr><td>합계</td><td>합계</td><td>합계</td><td>합계</td><td>12,783,512</td><td>10,776,005</td></tr>
    </tbody></table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "사업부문별 매출"
    assert result["unit"] == "백만원"
    assert result["topItem"]["name"] == "상선"
    assert result["topItem"]["revenue"] == 10523365
    assert result["topItem"]["share"] == 82.32
    assert result["hasConsolidationAdjustment"] is True


def test_period_segment_sales_requires_reconciled_total():
    html = """<table><tr><th>사업부문</th><th>매출유형</th><th>제26기</th></tr>
    <tr><td>A</td><td>제품</td><td>70</td></tr><tr><td>B</td><td>제품</td><td>30</td></tr>
    <tr><td>합계</td><td>합계</td><td>200</td></tr></table>"""
    assert extract_revenue_mix([html], 2025) is None


def test_attachment_only_correction_does_not_replace_business_report_body(monkeypatch):
    import dart_business_service as dart
    monkeypatch.setattr(dart, "_corp_codes", lambda key: {"033500": {"corpCode": "00123456"}})
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"status": "000", "list": [
                {"report_nm": "[첨부정정]사업보고서 (2025.12)", "rcept_no": "20260319000704"},
                {"report_nm": "사업보고서 (2024.12)", "rcept_no": "20250318001705"},
            ]}
    monkeypatch.setattr(dart.requests, "get", lambda *args, **kwargs: Response())
    assert dart._search_report_api("test-key", "033500") is None


def test_normalizes_dart_spaced_segment_labels():
    from dart_business_service import _row_label
    assert _row_label("PU 단열재 사 업 부 문") == "PU 단열재 사업부문"
    assert _row_label("가 스 사 업 부 문") == "가스 사업부문"


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
        <tr><td>기타</td><td>기타제품</td><td>6188440</td><td>20.07%</td></tr>
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
      <tr><td>기타</td><td>기타제품</td><td>7798921</td><td>25.29%</td></tr>
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

def test_extracts_combined_amount_share_column_for_samsung_sdi():
    html = """
    <html><body>
      <p>(단위 : 백만원)</p>
      <table>
        <thead><tr><th>사업부문</th><th>매출유형</th><th>품 목</th><th>구체적용도</th><th>주요상표 등</th><th>매출액(비율)</th></tr></thead>
        <tbody>
          <tr><td>에너지솔루션</td><td>제품 및 기타 매출</td><td>소형전지 등</td><td>전기자동차용, ESS용 배터리 등</td><td>PRiMX</td><td>12,384,169(93%)</td></tr>
          <tr><td>전자재료</td><td>제품 및 기타 매출</td><td>EMC 등</td><td>반도체 소재, OLED 소재 등</td><td>스타콤 등</td><td>882,562(7%)</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "사업부문별 매출"
    assert result["topItem"]["name"] == "에너지솔루션"
    assert result["topItem"]["share"] == 93.0
    assert "소형전지" in result["topItem"]["detail"]


def test_accepts_single_explicit_100pct_segment_for_sk_hynix():
    html = """
    <table>
      <thead><tr><th>사업부문</th><th>매출유형</th><th>품목</th><th>구체적용도</th><th>주요상표등</th><th>매출액(비율)</th></tr></thead>
      <tbody>
        <tr><td>반도체 부문</td><td>제품 외</td><td>DRAM, NAND Flash 등</td><td>산업용 전자기기</td><td>SK하이닉스</td><td>97,146,675(100%)</td></tr>
        <tr><td>합계</td><td>합계</td><td>합계</td><td>합계</td><td>합계</td><td>97,146,675(100%)</td></tr>
      </tbody>
    </table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["topItem"]["name"] == "반도체 부문"
    assert result["topItem"]["share"] == 100.0
    assert "DRAM" in result["topItem"]["detail"]


def test_extracts_naver_service_mix_from_generic_amount_share_columns():
    html = """
    <table>
      <thead>
        <tr><th rowspan="2">구분</th><th colspan="2">제27기</th><th colspan="2">제26기</th></tr>
        <tr><th>금액</th><th>비중</th><th>금액</th><th>비중</th></tr>
      </thead>
      <tbody>
        <tr><td>영업수익</td><td>12035007</td><td>100.0</td><td>10737719</td><td>100.0</td></tr>
        <tr><td>- 서치플랫폼</td><td>4168936</td><td>34.6</td><td>3946166</td><td>36.8</td></tr>
        <tr><td>- 커머스</td><td>3688407</td><td>30.6</td><td>2922977</td><td>27.2</td></tr>
        <tr><td>- 핀테크</td><td>1690684</td><td>14.1</td><td>1508407</td><td>14.0</td></tr>
        <tr><td>- 콘텐츠</td><td>1899173</td><td>15.8</td><td>1796421</td><td>16.7</td></tr>
        <tr><td>- 엔터프라이즈</td><td>587807</td><td>4.9</td><td>563748</td><td>5.3</td></tr>
      </tbody>
    </table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["topItem"]["name"] == "서치플랫폼"
    assert result["topItem"]["share"] == 34.6
    assert sum(row["share"] for row in result["items"]) == 100.0


def test_merges_split_hyundai_segment_tables_when_shares_reconcile_to_100():
    manufacturing = """
    <table><tbody>
      <tr><td>구분</td><td>구분</td><td>2025년 (제58기)</td><td>2025년 (제58기)</td><td>2024년</td><td>2024년</td></tr>
      <tr><td>구분</td><td>구분</td><td>금액</td><td>비중</td><td>금액</td><td>비중</td></tr>
      <tr><td>차량 부문</td><td>매출액</td><td>145631818</td><td>78.2</td><td>136725011</td><td>78.1</td></tr>
      <tr><td>차량 부문</td><td>영업이익</td><td>8470939</td><td>73.9</td><td>11411499</td><td>80.1</td></tr>
      <tr><td>기타 부문</td><td>매출액</td><td>10389879</td><td>5.6</td><td>10059492</td><td>5.7</td></tr>
    </tbody></table>
    """
    finance = """
    <table><tbody>
      <tr><td>구분</td><td>구분</td><td>2025년 (제58기)</td><td>2025년 (제58기)</td><td>2024년</td><td>2024년</td></tr>
      <tr><td>구분</td><td>구분</td><td>금액</td><td>비중</td><td>금액</td><td>비중</td></tr>
      <tr><td>금융 부문</td><td>매출액</td><td>30232775</td><td>16.2</td><td>28446650</td><td>16.2</td></tr>
      <tr><td>금융 부문</td><td>영업이익</td><td>2164043</td><td>18.9</td><td>1795249</td><td>12.6</td></tr>
    </tbody></table>
    """
    result = extract_revenue_mix([manufacturing, finance], 2025)
    assert result is not None
    assert result["basis"] == "사업부문별 매출"
    assert result["topItem"]["name"] == "차량 부문"
    assert result["topItem"]["share"] == 78.2
    assert [row["name"] for row in result["items"][:3]] == ["차량 부문", "금융 부문", "기타 부문"]
    assert round(sum(row["share"] for row in result["items"]), 1) == 100.0

def test_switches_to_product_basis_when_segment_repeats_across_priced_products():
    html = """
    <table>
      <thead>
        <tr><th>사업부문</th><th>매출유형</th><th>품목</th><th>2025년도 금액</th><th>2025년도 비중</th></tr>
      </thead>
      <tbody>
        <tr><td>바이오의약품</td><td>제품 및 상품 등</td><td>바이오의약품 등</td><td>3879697</td><td>93.20%</td></tr>
        <tr><td>바이오의약품</td><td>용역</td><td>제품관련 서비스 등</td><td>2838</td><td>0.07%</td></tr>
        <tr><td>바이오의약품</td><td>소계</td><td>소계</td><td>3882535</td><td>93.27%</td></tr>
        <tr><td>케미컬의약품</td><td>제품 및 상품 등</td><td>케미컬의약품 등</td><td>272156</td><td>6.54%</td></tr>
        <tr><td>케미컬의약품</td><td>용역</td><td>기타 서비스 등</td><td>6139</td><td>0.15%</td></tr>
        <tr><td>케미컬의약품</td><td>기타</td><td>기타</td><td>1665</td><td>0.04%</td></tr>
        <tr><td>케미컬의약품</td><td>소계</td><td>소계</td><td>279960</td><td>6.73%</td></tr>
        <tr><td>합계</td><td>합계</td><td>합계</td><td>4162495</td><td>100.00%</td></tr>
      </tbody>
    </table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "제품별 매출"
    assert result["topItem"]["name"] == "바이오의약품 등"
    assert result["topItem"]["share"] == 93.2


def test_extracts_product_mix_from_domestic_export_total_rows():
    html = """
    <table>
      <thead><tr><th>매출 유형</th><th>품목</th><th>구분</th><th>제82기 ('25.1.1~12.31)</th><th>제81기</th></tr></thead>
      <tbody>
        <tr><td>제품</td><td>승용</td><td>내수</td><td>3554913</td><td>3503745</td></tr>
        <tr><td>제품</td><td>승용</td><td>수출</td><td>4734171</td><td>4280518</td></tr>
        <tr><td>제품</td><td>승용</td><td>합계</td><td>8289084</td><td>7784262</td></tr>
        <tr><td>제품</td><td>RV</td><td>내수</td><td>13609944</td><td>12652011</td></tr>
        <tr><td>제품</td><td>RV</td><td>수출</td><td>29220221</td><td>26973985</td></tr>
        <tr><td>제품</td><td>RV</td><td>합계</td><td>42830165</td><td>39625996</td></tr>
        <tr><td>제품</td><td>상용</td><td>합계</td><td>2322858</td><td>2321379</td></tr>
        <tr><td>제품 외 기타</td><td>제품 외 기타</td><td>합계</td><td>11706569</td><td>13518904</td></tr>
        <tr><td>합계</td><td>합계</td><td>합계</td><td>65148676</td><td>63256745</td></tr>
      </tbody>
    </table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "제품별 매출"
    assert result["topItem"]["name"] == "RV"
    assert round(result["topItem"]["share"], 1) == 65.7

def test_keeps_segment_basis_when_same_segment_revenue_is_repeated_across_subservices():
    html = """
    <table>
      <thead><tr><th>구분</th><th>매출 유형</th><th>사업영역</th><th>주요 제품 및 서비스</th><th>매출액</th><th>비중</th></tr></thead>
      <tbody>
        <tr><td>플랫폼 부문</td><td>제품/용역</td><td>톡비즈</td><td>카카오톡, 선물하기</td><td>4318175</td><td>53.3%</td></tr>
        <tr><td>플랫폼 부문</td><td>제품/용역</td><td>포털비즈</td><td>다음(Daum) 등</td><td>4318175</td><td>53.3%</td></tr>
        <tr><td>플랫폼 부문</td><td>제품/용역</td><td>플랫폼 기타</td><td>카카오T, 카카오페이</td><td>4318175</td><td>53.3%</td></tr>
        <tr><td>콘텐츠 부문</td><td>제품/용역</td><td>게임</td><td>모바일 및 PC 게임</td><td>3780973</td><td>46.7%</td></tr>
        <tr><td>콘텐츠 부문</td><td>제품/용역</td><td>뮤직</td><td>음원 플랫폼</td><td>3780973</td><td>46.7%</td></tr>
        <tr><td>합계</td><td>합계</td><td>합계</td><td>합계</td><td>8099148</td><td>100.0%</td></tr>
      </tbody>
    </table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "사업부문별 매출"
    assert result["topItem"]["name"] == "플랫폼 부문"
    assert result["topItem"]["share"] == 53.3


def test_rejects_geography_only_revenue_categories():
    html = """
    <table>
      <thead><tr><th>구분</th><th>매출액</th><th>비중</th></tr></thead>
      <tbody>
        <tr><td>국내외</td><td>9573</td><td>95.73%</td></tr>
        <tr><td>기타</td><td>427</td><td>4.27%</td></tr>
        <tr><td>합계</td><td>10000</td><td>100%</td></tr>
      </tbody>
    </table>
    """
    assert extract_revenue_mix([html], 2025) is None

def test_does_not_treat_separate_revenue_ratio_column_as_combined_amount_cell():
    html = """
    <table><tbody>
      <tr><td>사업부문</td><td>사업부문</td><td>품 목</td><td>2025년 (제55기)</td><td>2025년 (제55기)</td></tr>
      <tr><td>사업부문</td><td>사업부문</td><td>품 목</td><td>매출액</td><td>매출액 비율(%)</td></tr>
      <tr><td>기초소재 사업</td><td>내화물 사업</td><td>내화물 제조</td><td>505309</td><td>17.2</td></tr>
      <tr><td>기초소재 사업</td><td>라임화성 사업</td><td>생석회 등</td><td>859306</td><td>29.2</td></tr>
      <tr><td>에너지소재 사업</td><td>에너지소재 사업</td><td>양극재, 음극재</td><td>1574083</td><td>53.6</td></tr>
      <tr><td>합 계</td><td>합 계</td><td>-</td><td>2938698</td><td>100.0</td></tr>
    </tbody></table>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["topItem"]["name"] == "양극재, 음극재"
    assert result["topItem"]["revenue"] == 1574083.0
    assert result["topItem"]["share"] == 53.6

def test_prefers_company_wide_posco_segment_mix_over_subbusiness_product_mix():
    html = """
    <html><body>
      <table><tbody>
        <tr><td>사업부문</td><td>제58기(당기)</td><td>제58기(당기)</td><td>제58기(당기)</td><td>제58기(당기)</td></tr>
        <tr><td>사업부문</td><td>자산</td><td>자산</td><td>매출</td><td>매출</td></tr>
        <tr><td>철강부문</td><td>65562938</td><td>38%</td><td>59413172</td><td>51%</td></tr>
        <tr><td>인프라(무역부문)</td><td>23610546</td><td>14%</td><td>42220911</td><td>36%</td></tr>
        <tr><td>인프라(건설부문)</td><td>9797114</td><td>6%</td><td>7228333</td><td>6%</td></tr>
        <tr><td>인프라(물류 등 부문)</td><td>2041956</td><td>1%</td><td>3554224</td><td>3%</td></tr>
        <tr><td>이차전지소재부문</td><td>17624390</td><td>10%</td><td>3338386</td><td>3%</td></tr>
        <tr><td>기타부문</td><td>52486865</td><td>31%</td><td>1500108</td><td>1%</td></tr>
        <tr><td>합계</td><td>171123809</td><td>100%</td><td>117255134</td><td>100%</td></tr>
      </tbody></table>

      <table><tbody>
        <tr><td>사업부문</td><td>사업부문</td><td>품 목</td><td>2025년 (제55기)</td><td>2025년 (제55기)</td></tr>
        <tr><td>사업부문</td><td>사업부문</td><td>품 목</td><td>매출액</td><td>매출액 비율(%)</td></tr>
        <tr><td>기초소재 사업</td><td>내화물 사업</td><td>내화물 제조</td><td>505309</td><td>17.2%</td></tr>
        <tr><td>기초소재 사업</td><td>라임화성 사업</td><td>생석회 등</td><td>859306</td><td>29.2%</td></tr>
        <tr><td>에너지소재 사업</td><td>에너지소재 사업</td><td>양극재, 음극재</td><td>1574083</td><td>53.6%</td></tr>
        <tr><td>합 계</td><td>합 계</td><td>-</td><td>2938698</td><td>100.0%</td></tr>
      </tbody></table>
    </body></html>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["basis"] == "사업부문별 매출"
    assert result["topItem"]["name"] == "철강부문"
    assert result["topItem"]["share"] == 51.0

def test_ignores_non_monetary_units_before_revenue_unit():
    html = """
    <html><body>
      <p>(단위 : tCO2e)</p>
      <p>(단위 : 백만원, %)</p>
      <table>
        <thead><tr><th>사업부문</th><th>매출액</th><th>비중</th></tr></thead>
        <tbody>
          <tr><td>HS</td><td>261259</td><td>29.3%</td></tr>
          <tr><td>MS</td><td>194263</td><td>21.8%</td></tr>
          <tr><td>기타</td><td>436347</td><td>48.9%</td></tr>
          <tr><td>합계</td><td>891869</td><td>100.0%</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    result = extract_revenue_mix([html], 2025)
    assert result is not None
    assert result["unit"] == "백만원"

