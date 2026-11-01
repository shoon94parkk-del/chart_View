"""Offline investment-learning curriculum and versioned, server-graded lessons.

The primers describe business models, not current results or recommendations.
Every study asks the learner to verify dated original disclosures. No provider or
LLM is called here. Persist the private lesson when a session is created and pass
only ``public_lesson`` to clients before they submit an attempt.
"""

from copy import deepcopy
from datetime import date
import hashlib
import json
import re


_DART = {"title": "DART 전자공시 — 회사명·기간·정정공시 확인", "url": "https://dart.fss.or.kr/dsab001/main.do"}
_BOK = {"title": "한국은행 — 환율·물가·금리 원자료 확인", "url": "https://www.bok.or.kr/portal/main/main.do"}
_BASELINE = (
    "이 자료는 사업 구조를 읽기 위한 기초 안내이며 최신 실적·고객 계약·시장점유율을 검증한 자료가 아닙니다. "
    "학습일 기준 공시된 가장 최근 사업·분기보고서와 IR 자료를 직접 열어 공시일, 대상 기간, 연결/별도, 통화·단위를 기록하세요. "
    "아직 공시되지 않은 기간과 확인하지 못한 수치는 '미확인'으로 남기고, 결측치를 0으로 채우지 마세요."
)


def _entry(symbol, name, industry, business, customers, economics, risks, metrics, peers, url):
    return {
        "company": {"symbol": symbol, "name": name, "industry": industry},
        "business": business, "customers": customers, "economics": economics,
        "risks": risks, "metrics": metrics, "peers": peers, "url": url,
    }


_PRIMERS = [
    _entry(
        "278470.KS", "에이피알", "화장품",
        "자체 화장품 브랜드와 홈 뷰티 디바이스를 소비자에게 판매하는 사업 구조입니다. 브랜드·제품 기획과 판매 채널 운영을 함께 살펴보세요.",
        "최종 소비자와 온라인·오프라인 유통 채널을 구분하고, 직접 판매와 유통사 판매의 매출 인식·비용 차이를 확인하세요.",
        "화장품과 뷰티 디바이스의 판매량·제품 구성, 해외 채널 확대, 광고비와 판매 수수료가 수익성의 주요 검토 항목입니다.",
        "유행 변화, 광고 효율 저하, 특정 제품·채널 집중, 디바이스 품질·규제와 반품 위험을 확인하세요.",
        "화장품/디바이스 및 지역별 매출, 판매관리비율, 광고비 대비 매출, 재고·반품 추이",
        "자체 브랜드 업체와 비교하고, 코스맥스·한국콜마 같은 ODM 업체와는 고객과 비용 구조가 다름을 먼저 확인하세요.",
        "https://www.apr-in.com/",
    ),
    _entry(
        "192820.KS", "코스맥스", "화장품",
        "화장품 브랜드 고객에게 연구개발·제형 설계·생산을 제공하는 화장품 ODM 사업이 핵심입니다. 브랜드의 소비자 판매와 제조사의 납품 매출을 구분하세요.",
        "주요 고객 유형은 화장품 브랜드사입니다. 고객명·거래 비중이 공시되지 않으면 특정 브랜드와의 관계를 추정하지 마세요.",
        "고객의 주문량, 공장 가동률, 지역별 제품 구성과 원가·인건비가 ODM 수익성을 좌우할 수 있습니다.",
        "고객 주문 변동, 국가별 수요·규제, 공장 수율과 품질 문제, 신규 생산능력의 고정비 부담을 검토하세요.",
        "지역별 매출·영업이익, 생산능력·가동률, 원가율, 매출채권·재고 회전",
        "한국콜마 등 ODM 업체와 같은 회계기간·사업 범위로 비교하고 에이피알의 브랜드 판매 구조와 구분하세요.",
        "https://www.cosmax.com/",
    ),
    _entry(
        "161890.KS", "한국콜마", "화장품",
        "화장품 브랜드사를 위한 연구개발·제조 ODM 사업을 운영합니다. 연결 자회사의 제약·건강 관련 사업 등은 화장품 사업과 나누어 공시 범위를 확인하세요.",
        "화장품 브랜드사가 제조 고객이며, 연결 자회사 고객은 사업별로 다릅니다. 한국콜마와 지주회사 콜마홀딩스의 공시를 혼동하지 마세요.",
        "화장품 주문·가동률과 제품 구성, 자회사 실적과 연결조정이 연결 매출·이익 해석에 영향을 줍니다.",
        "브랜드 고객 주문 변동, 품질·규제, 생산설비 고정비, 자회사와 본업을 섞은 이익 해석을 경계하세요.",
        "화장품 부문 매출·이익, 국내외 가동률, 연결 자회사 기여와 연결조정, 재고·매출채권",
        "코스맥스와 화장품 ODM 부문을 우선 비교하고 연결 전체 이익의 구성 차이는 별도로 표시하세요.",
        "https://www.kolmar.co.kr/",
    ),
    _entry(
        "003230.KS", "삼양식품", "K-푸드",
        "불닭 등 브랜드의 라면과 식품을 생산·판매하는 식품 기업입니다. 해외 수출과 현지 유통, 국내 판매를 나누어 읽으세요.",
        "제품의 최종 수요자는 소비자이고 직접 거래 상대는 수입·유통사나 판매 채널일 수 있습니다. 출하와 소비자 재구매를 구분하세요.",
        "라면 판매량, 수출 국가·제품 구성, 생산 가동률과 밀·팜유·포장재 등 원재료 및 물류비가 이익에 영향을 줍니다.",
        "특정 브랜드·지역 의존, 식품 규제, 유통 재고, 원재료·환율, 증설 후 가동률을 점검하세요.",
        "해외/국내 매출, 판매량·제품 구성, 원재료비율, 가동률, 재고·영업현금흐름",
        "농심과 지역·제품 구성 차이를 비교하고 CJ제일제당의 바이오 등 다른 사업을 분리하세요.",
        "https://www.samyangfoods.com/",
    ),
    _entry(
        "004370.KS", "농심", "K-푸드",
        "신라면 등 라면과 스낵을 생산·판매하며 국내외 식품 사업을 운영합니다. 제품 브랜드와 생산·판매 지역을 함께 확인하세요.",
        "소비자 수요가 소매·도매 유통망의 주문으로 연결됩니다. 국내 가격 정책과 해외 현지 판매 조건은 따로 살펴보세요.",
        "라면·스낵 판매량과 가격, 해외 사업 구성, 밀·팜유 등 원재료와 유통·물류 비용이 수익성의 검토 항목입니다.",
        "내수 경쟁과 가격 인상 제약, 해외 공장 비용, 원재료·환율, 식품 안전·회수 위험을 확인하세요.",
        "국내외 매출·영업이익, 제품 가격·판매량, 원가율, 해외 공장 가동률, 재고",
        "삼양식품과 수출·현지 생산·내수의 구성을 맞춰 비교하며 인기 브랜드가 전체 이익을 설명한다고 가정하지 마세요.",
        "https://www.nongshim.com/",
    ),
    _entry(
        "097950.KS", "CJ제일제당", "K-푸드",
        "가공식품·식품소재와 아미노산 등 바이오 사업을 함께 읽어야 하는 기업입니다. 연결 범위와 사업 재편 여부를 최신 공시에서 확인하세요.",
        "식품의 소비자·유통 고객과 바이오 소재의 기업 고객은 수요와 가격 결정 방식이 다릅니다.",
        "식품 브랜드·해외 사업의 제품 구성, 바이오 제품의 판매가격·원가, 연결 사업별 이익 기여와 차입 부담을 구분하세요.",
        "곡물·에너지·환율 변동, 바이오 공급 경쟁, 해외 사업 비용, 부채와 사업 범위 변경을 점검하세요.",
        "식품/바이오 부문 매출·이익, 원재료·제품 가격, 영업현금흐름, 순차입금, 연결 범위",
        "라면 업체와 연결 총매출만 비교하지 말고 식품 부문·지역·제품군을 맞추며 바이오 수익성은 따로 보세요.",
        "https://www.cj.co.kr/",
    ),
    _entry(
        "042660.KS", "한화오션", "조선·LNG",
        "LNG 운반선 등 상선 선박, 해양 설비와 잠수함·함정 등 특수선 사업을 하는 조선 기업입니다. 사업별 계약·건조·인도 과정을 나누어 보세요.",
        "상선의 선주, 해양 사업 발주처, 특수선의 정부·군 등은 계약·대금 회수 조건이 다릅니다. 고객·수주 사실은 공시로 확인하세요.",
        "수주 가격과 선종 구성, 건조 진척, 강재·인건비, 공정 안정성, 환헤지와 충당금이 손익을 좌우할 수 있습니다.",
        "공정 지연, 원가 상승, 계약 변경·취소, 해양 프로젝트 손실과 특수선 인허가를 검토하세요.",
        "선종별 신규수주·수주잔고, 인도 일정, 계약자산·선수금, 공사손실충당금, 영업현금흐름",
        "삼성중공업의 해양·상선 구성과 HD한국조선해양의 연결 자회사 범위를 구분해 비교하세요.",
        "https://www.hanwhaocean.com/",
    ),
    _entry(
        "010140.KS", "삼성중공업", "조선·LNG",
        "LNG 운반선 등 상선과 부유식 LNG 생산설비 등 해양 설비를 설계·건조하는 사업을 운영합니다.",
        "선주와 에너지·해양 사업 발주처가 주요 고객 유형입니다. 개별 해양 계약의 공정과 대금 조건을 구분하세요.",
        "선종·해양 프로젝트의 수주 가격, 건조 공정, 자재·인건비와 환헤지, 프로젝트별 원가 추정 변경이 손익에 영향을 줍니다.",
        "해양 공사의 복잡성, 납기·원가 초과, 계약 손실 추정, 환율과 발주 지연을 점검하세요.",
        "상선/해양 수주·잔고와 인도 일정, 공정률, 계약자산, 충당금, 영업현금흐름",
        "한화오션과 선종·해양 비중 및 계약 연도를 맞춰 비교하며 단순 잔고 크기로 이익 순위를 정하지 마세요.",
        "https://www.samsungshi.com/",
    ),
    _entry(
        "009540.KS", "HD한국조선해양", "조선·LNG",
        "조선 자회사들을 연결해 읽는 조선 중간지주 성격의 기업이며 조선 기술 연구개발 등을 수행합니다. 특정 조선소 단독 실적과 연결 실적을 구분하세요.",
        "실제 선박 건조·수주를 수행하는 자회사와 선주 계약의 관계, 연결 지분과 비지배지분을 최신 공시로 확인하세요.",
        "자회사별 선종·수주 가격·생산성, 연결조정과 비지배지분 때문에 연결 영업이익과 지배주주 이익의 해석이 다릅니다.",
        "자회사 간 사업 구성, 조선 공정·원가 위험, 지배구조·연결 범위 변동을 점검하세요.",
        "자회사별 수주·실적, 연결조정, 비지배지분, 지배주주 순이익, 현금흐름",
        "한화오션·삼성중공업과 비교할 때 연결 범위와 귀속 이익을 먼저 맞추고 자회사 수주를 중복 합산하지 마세요.",
        "https://www.hdksoe.co.kr/",
    ),
    _entry(
        "012450.KS", "한화에어로스페이스", "방산",
        "항공 엔진·부품과 자주포 등 지상 방산 사업을 함께 살펴야 하는 기업입니다. 연결 자회사·사업 재편에 따른 범위는 최신 보고서로 확인하세요.",
        "정부·군과 방산 업체, 항공 엔진 관련 고객 등은 발주·승인·개발 주기가 서로 다릅니다.",
        "방산 수출 계약의 제품 구성·납품 일정, 생산능력, 항공 엔진 사업의 개발·양산 비용과 연결 범위가 이익에 영향을 줍니다.",
        "수출 승인·정치, 납품 지연, 현지화·품질 의무, 개발비와 계약 조건, 재편에 따른 비교 기준 변동을 점검하세요.",
        "사업별 신규수주·잔고·납품, 수출 비중, 계약부채·재고, 영업현금흐름, 연결 범위",
        "LIG넥스원의 유도무기·전자와 현대로템의 철도·전차를 구분해 제품·납품 구조로 비교하세요.",
        "https://www.hanwhaaerospace.com/",
    ),
    _entry(
        "079550.KS", "LIG넥스원", "방산",
        "유도무기, 감시정찰, 지휘통제·통신과 항공전자 등 방산 전자체계를 개발·생산하는 사업 구조입니다. 079550의 현재 법인명과 사명 변경은 최신 공시에서 확인하세요.",
        "정부·군과 체계 업체 등이 고객 유형이며 개발 계약과 양산·정비 계약의 조건을 구분하세요.",
        "개발·양산 단계별 매출 인식, 제품 구성, 수출 납품과 연구개발·품질 비용을 함께 확인하세요.",
        "개발 지연·성능 검증, 수출 승인, 고객·프로젝트 집중, 계약 원가와 품질 의무를 점검하세요.",
        "개발/양산 수주·잔고, 납품 일정, 연구개발비, 계약자산·재고, 영업현금흐름",
        "한화에어로스페이스와 제품·개발 단계가 다르므로 국방 예산 증가율을 같은 이익 증가율로 적용하지 마세요.",
        "https://www.lignex1.com/",
    ),
    _entry(
        "064350.KS", "현대로템", "방산",
        "철도 차량·시스템과 전차 등 방산, 산업 설비 관련 사업을 운영합니다. 철도와 방산의 수주·손익 구조를 나누어 보세요.",
        "철도 운영기관·공공 발주처, 정부·군과 산업 설비 고객은 발주 절차와 계약·인도 조건이 다릅니다.",
        "철도·방산별 제품 구성, 장기 프로젝트 공정·원가, 전차 수출 납품과 현지화 조건을 확인하세요.",
        "장기 공정 손실, 납품·승인 지연, 현지 생산 조건, 환율과 사업별 수익성 차이를 검토하세요.",
        "철도/방산 부문 매출·이익·수주잔고, 납품 일정, 계약자산·충당금, 현금흐름",
        "방산 동종사 비교에서도 철도 부문과 연결 전체를 혼동하지 말고 같은 제품·납품 기간을 맞추세요.",
        "https://www.hyundai-rotem.co.kr/",
    ),
    _entry(
        "034020.KS", "두산에너빌리티", "원전",
        "원전 주기기와 발전 설비·서비스, 가스터빈 등 에너지 설비 사업을 운영합니다. 연결 자회사 사업은 원전 본업과 나누어 확인하세요.",
        "발전 사업자와 발전소 건설·설계 업체 등이 고객 유형이며 주기기 제작과 서비스의 계약 주기가 다릅니다.",
        "주기기 제작 수주와 납품, 발전 설비·서비스 구성, 대형 제작설비 가동과 원가, 연결 자회사 기여를 검토하세요.",
        "정책·인허가와 프로젝트 지연, 제작 품질·원가, 신규 기술 상용화 불확실성, 연결 범위 변동을 확인하세요.",
        "에너지 부문 수주·잔고·납품, 원전 주기기 계약, 서비스 매출, 계약자산, 연결조정",
        "현대건설의 건설 EPC, 한전KPS의 정비와 역할을 구분하세요. 원전 테마만으로 같은 수익 구조라 가정하지 마세요.",
        "https://www.doosanenerbility.com/",
    ),
    _entry(
        "000720.KS", "현대건설", "원전",
        "주택·건축, 토목, 플랜트 등 건설 사업을 운영하며 원전 건설도 수행합니다. 원전 관련 기대와 연결 전체 건설 손익을 분리하세요.",
        "국내외 공공·민간 발주처와 주택 고객이 포함됩니다. 원전 건설의 발주·계약·착공 단계는 서로 다릅니다.",
        "공사 계약 가격과 진척, 자재·인건비, 공사 원가 추정, 주택 분양·대금 회수와 연결 자회사 구성이 중요합니다.",
        "공사 원가 초과, 미분양·미수금, 부동산 금융, 해외 공사·원전 승인 지연을 점검하세요.",
        "사업별 수주잔고·공정, 공사손익·충당금, 미수금·계약자산, 현금흐름, 원전 계약 단계",
        "원전 주기기 제작사·정비사와 달리 건설 EPC의 원가·공정·대금 회수 위험을 따로 비교하세요.",
        "https://www.hdec.kr/",
    ),
    _entry(
        "051600.KS", "한전KPS", "원전",
        "원자력·화력 등 발전 설비의 정비와 관련 서비스를 제공하는 기업입니다. 발전소 건설이나 전력 판매가 주된 사업이라고 혼동하지 마세요.",
        "발전 사업자 등의 계획예방정비·경상정비 수요와 해외 서비스 계약을 나누어 확인하세요.",
        "정비 물량과 일정, 계약 단가, 인력 운영·인건비, 해외 사업 구성이 수익성을 좌우할 수 있습니다.",
        "정비 일정 변화, 안전·품질 책임, 인건비, 주요 고객 의존과 해외 계약 위험을 점검하세요.",
        "발전원별 정비 매출·계약, 계획예방정비 일정, 인건비율, 해외 사업 이익, 영업현금흐름",
        "두산에너빌리티의 설비 제작과 현대건설의 신규 건설 수주보다 운영 중 설비의 정비 수요가 중요함을 구분하세요.",
        "https://www.kps.co.kr/",
    ),
    _entry(
        "267260.KS", "HD현대일렉트릭", "전력기기",
        "전력 변압기, 차단기 등 전력기기를 제작·판매합니다. 발전·송배전 투자와 산업 설비 수요가 제품별 주문으로 연결되는 경로를 보세요.",
        "전력회사, 산업 설비·건설 고객 등과 지역별 판매·계약 조건을 확인하세요. 데이터센터 투자가 곧 특정 고객 계약을 뜻하지는 않습니다.",
        "고압 전력기기의 수주 가격·제품·지역 구성, 생산능력과 가동률, 구리·전기강판 원가와 환율을 함께 확인하세요.",
        "원재료 상승, 증설 후 가동률, 납기·품질, 지역·고객 집중과 무역 정책을 점검하세요.",
        "제품·지역별 수주·잔고, 평균 납기, 가동률·증설, 원가율, 계약부채·현금흐름",
        "LS ELECTRIC의 배전·자동화와 산일전기의 산업·특수 변압기를 제품·전압·고객 기준으로 구분하세요.",
        "https://www.hd-hyundaielectric.com/",
    ),
    _entry(
        "010120.KS", "LS ELECTRIC", "전력기기",
        "전력기기·전력 시스템과 산업 자동화 기기·시스템을 공급합니다. 배전 관련 사업과 자동화 사업의 수요·제품 구성을 구분하세요.",
        "전력·산업·건설 고객과 설비 제조사 등이 고객 유형이며 직접·유통 판매 및 프로젝트 계약 조건을 확인하세요.",
        "전력·자동화 부문별 제품 구성, 국내외 설비 투자, 시스템 프로젝트 원가와 구리 등 원재료·환율을 함께 검토하세요.",
        "설비 투자 둔화, 프로젝트 원가, 원재료·환율, 해외 확대 비용과 품질 문제를 점검하세요.",
        "전력/자동화 매출·이익, 지역·제품 구성, 수주잔고, 프로젝트 원가, 재고·현금흐름",
        "HD현대일렉트릭과 전력기기 제품 구성이 같다고 가정하지 말고 자동화 부문의 별도 수요를 보세요.",
        "https://www.ls-electric.com/",
    ),
    _entry(
        "062040.KS", "산일전기", "전력기기",
        "산업용·특수 변압기와 리액터 등을 제조·판매합니다. 전력망용 제품과 신재생·산업 설비 적용 제품의 실제 구성을 공시로 확인하세요.",
        "전력·산업 설비 관련 고객의 주문이 매출로 이어집니다. 특정 해외 고객과 적용처의 비중은 확인된 공시 범위만 기록하세요.",
        "변압기 제품·고객·수출 지역 구성, 생산능력·가동률, 구리·전기강판 원가와 환율이 수익성 검토 항목입니다.",
        "고객·지역 집중, 수출·무역 정책, 원재료와 증설 부담, 품질·납기 위험을 점검하세요.",
        "제품·지역 매출과 고객 집중도, 수주·납기, 가동률·증설, 원재료비, 현금흐름",
        "대형 고압 기기나 배전·자동화 업체와 제품·고객·생산 규모를 맞춰 비교하고 업종 이름만으로 같은 마진을 적용하지 마세요.",
        "https://www.sanil.co.kr/",
    ),
]

_BY_SYMBOL = {p["company"]["symbol"]: p for p in _PRIMERS}

_INDUSTRIES = {
    "화장품": {
        "chain": "원료·용기 → ODM 연구개발·제조 → 브랜드 기획·마케팅 → 유통 채널 → 소비자. 자체 브랜드·뷰티 디바이스 판매와 화장품 ODM 제조의 역할을 구분합니다.",
        "scenario": "해외 화장품 수요가 늘었지만 광고비·판매 수수료와 제조 원가도 상승했다고 가정합니다. 이는 학습용 조건이며 실제 발생한 사건이 아닙니다.",
        "response": "브랜드는 채널별 매출·광고비·수수료, ODM은 주문·가동률·원가를 나누어 비교해야 이익 영향을 판단할 수 있습니다.",
        "metrics": "브랜드의 판매관리비·제품 구성과 ODM의 가동률·지역별 원가율",
        "concept": "브랜드와 ODM의 수요 전달·비용 구조",
    },
    "K-푸드": {
        "chain": "곡물·유지·포장재 → 식품 생산 → 수출·현지 유통 → 소매 채널 → 소비자. 바이오 소재의 기업 고객 사업이 있다면 라면 소비재와 별도로 봅니다.",
        "scenario": "밀·팜유의 달러 가격과 원/달러 환율이 함께 오르고 판매가격은 당장 바꾸기 어렵다고 가정합니다. 이는 학습용 조건입니다.",
        "response": "원재료 매입·재고 반영 시차, 가격 전가, 수출 수입과 현지 생산·환헤지를 확인해야 원가와 이익 영향을 판단할 수 있습니다.",
        "metrics": "제품·지역별 판매량과 가격, 원재료비·재고 회전, 수출과 현지 생산 비중",
        "concept": "식품 원가·환율·가격 전가의 시차",
    },
    "조선·LNG": {
        "chain": "설계·선주 발주 → 강재·엔진·기자재 → 조선소 건조 → 인도·대금 회수 → 선박 운항. LNG 운반선과 LNG 해양 생산설비는 용도·프로젝트 위험이 다릅니다.",
        "scenario": "신규 LNG선 수주가 늘고 강재 가격·인건비도 상승했으나 기존 수주 선박은 아직 건조 중이라고 가정합니다. 이는 학습용 조건입니다.",
        "response": "수주 연도별 계약 가격·원가·공정과 손실충당금, 환헤지를 확인해야 잔고가 언제 어느 이익으로 인식되는지 판단할 수 있습니다.",
        "metrics": "수주 연도·선종별 잔고, 인도 일정·공정, 원가 추정·충당금, 계약자산·현금흐름",
        "concept": "수주잔고와 공정·이익·현금의 구분",
    },
    "방산": {
        "chain": "정부 예산·요구 → 개발·성능 검증 → 계약·수출 승인 → 부품·체계 생산 → 납품·후속 지원. 항공 엔진·지상무기·유도무기·철도 사업은 같은 수익 구조가 아닙니다.",
        "scenario": "한 국가의 국방 예산과 수출 논의가 늘었으나 최종 계약·수출 승인·납품 일정은 확정되지 않았다고 가정합니다. 이는 학습용 조건입니다.",
        "response": "예산·협의와 확정 계약을 구분하고 승인 조건·양산 능력·현지화 비용·납품에 따른 매출 인식을 확인해야 합니다.",
        "metrics": "확정 수주와 승인 조건, 제품별 잔고·납품, 개발·양산 원가, 계약부채·현금흐름",
        "concept": "방산 예산·수출 승인·납품의 단계",
    },
    "원전": {
        "chain": "정책·인허가·발주 → 설계·건설 EPC → 주기기 제작·설치 → 상업운전 → 장기 정비. 주기기 제작·건설·정비의 역할과 수익 시점을 구분합니다.",
        "scenario": "원전 확대 정책이 발표됐지만 신규 발전소의 인허가·주기기 계약·착공은 남아 있고 기존 원전은 계속 운전한다고 가정합니다. 이는 학습용 조건입니다.",
        "response": "제작·건설의 확정 계약·공정과 운영 중 설비의 정비 계약·일정을 나누어 봐야 세 기업의 실적 반영 시점을 판단할 수 있습니다.",
        "metrics": "인허가·확정 계약·공정, 주기기 납품, 운영 설비의 정비 일정·물량, 원가·대금 회수",
        "concept": "원전 제작·건설·정비의 다른 수익 시점",
    },
    "전력기기": {
        "chain": "전력망·산업 설비 투자 → 변압기·차단기·배전·자동화 발주 → 자재 조달·제작 → 납품·검수. 제품·전압·용도·고객별로 세 기업의 노출이 다릅니다.",
        "scenario": "전력망 투자와 주문이 늘고 구리·전기강판 가격도 상승하며 공장 증설이 진행 중이라고 가정합니다. 이는 학습용 조건입니다.",
        "response": "제품별 계약 가격·원가 전가 조건, 납기·가동률·증설 비용과 환헤지를 확인해야 잔고 증가가 이익·현금으로 이어지는지 판단할 수 있습니다.",
        "metrics": "제품·지역별 수주·납기, 가격·원가 전가, 생산능력·가동률, 계약부채·현금흐름",
        "concept": "전력기기 수주·원가 전가·생산능력",
    },
}

_GENERAL = {
    "chain": "원재료·기술 공급자 → 연구개발·생산 → 판매 채널·기업 고객 → 최종 수요의 흐름을 공시로 직접 작성하세요. 미확인 거래 관계는 추정하지 마세요.",
    "scenario": "수요가 늘면서 원재료비·금리·환율도 변했다고 가정합니다. 회사의 실제 노출과 계약 조건은 미확인이며 학습용 조건입니다.",
    "response": "공시로 제품·고객·통화 노출과 가격 전가·비용·시차를 먼저 확인하고 조건별 이익·현금흐름을 구분해야 합니다.",
    "metrics": "확인된 사업별 판매량·가격·원가, 대금 회수·재고, 차입·통화 노출",
    "concept": "확인된 사실과 조건부 추론의 구분",
}


def default_curriculum() -> dict:
    """Return an independent editable copy of the initial six-week schedule."""
    return {
        "id": "investment-learning-2026-11",
        "title": "6주 기업 공부 — 사업 구조에서 투자 판단까지",
        "startDate": "2026-11-02",
        "weeks": [
            {"id": f"week-{i // 3 + 1}", "industry": _PRIMERS[i]["company"]["industry"],
             "companies": [deepcopy(p["company"]) for p in _PRIMERS[i:i + 3]]}
            for i in range(0, len(_PRIMERS), 3)
        ],
    }


def catalog() -> dict:
    return {"schemaVersion": 1, "curriculum": default_curriculum(),
            "companies": [deepcopy(p["company"]) for p in _PRIMERS]}


def _text(value, field, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"invalid {field}")
    return value.strip()


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid calendar date") from exc


def _company(value):
    if not isinstance(value, dict):
        raise ValueError("invalid company")
    symbol = _text(value.get("symbol"), "symbol", 32)
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,31}", symbol):
        raise ValueError("invalid company symbol")
    if re.fullmatch(r"\d{6}", symbol):
        raise ValueError("Korean company symbol requires .KS or .KQ")
    name = _text(value.get("name"), "company name", 120)
    industry = _text(value.get("industry"), "company industry", 80)
    if symbol in _BY_SYMBOL:
        return deepcopy(_BY_SYMBOL[symbol]["company"])
    return {"symbol": symbol, "name": name, "industry": industry}


def _curriculum(value):
    if not isinstance(value, dict):
        raise ValueError("invalid curriculum")
    curriculum = {"id": _text(value.get("id"), "curriculum id", 120),
                  "title": _text(value.get("title"), "curriculum title", 200),
                  "startDate": value.get("startDate")}
    if _date(curriculum["startDate"]).weekday() != 0:
        raise ValueError("curriculum must start on Monday")
    weeks = value.get("weeks")
    if not isinstance(weeks, list) or not 1 <= len(weeks) <= 104:
        raise ValueError("curriculum requires 1 to 104 weeks")
    curriculum["weeks"] = []
    week_ids = set()
    for week in weeks:
        if not isinstance(week, dict):
            raise ValueError("invalid week")
        week_id = _text(week.get("id"), "week id", 120)
        if week_id in week_ids:
            raise ValueError("duplicate week id")
        week_ids.add(week_id)
        industry = _text(week.get("industry"), "week industry", 80)
        companies = week.get("companies")
        if not isinstance(companies, list) or len(companies) != 3:
            raise ValueError("each week requires exactly three companies")
        companies = [_company(company) for company in companies]
        if len({c["symbol"] for c in companies}) != 3:
            raise ValueError("week companies must be distinct")
        curriculum["weeks"].append({"id": week_id, "industry": industry, "companies": companies})
    return curriculum


def validate_curriculum(curriculum: dict) -> dict:
    """Return the same normalized, independent schedule used by lesson building.

    API saves and imports must call this before persistence so every accepted
    curriculum can subsequently produce lessons with the same invariants.
    """
    return _curriculum(curriculum)


def _question(question_id, dimension, prompt, correct, distractors, explanation, concept, seed):
    # A stable permutation prevents the answer position from teaching a pattern.
    correct_index = hashlib.sha256(f"{seed}:{question_id}".encode()).digest()[0] % 4
    options = list(distractors)
    options.insert(correct_index, correct)
    return {"id": question_id, "dimension": dimension, "prompt": prompt, "options": options,
            "correctIndex": correct_index, "explanation": explanation, "concept": concept}


def _unknown_primer(company):
    return {
        "company": company,
        "business": "이 기업의 제품·사업 구조·고객·경쟁사와 매출·이익 수치는 미확인입니다. 직접 공시와 공식 IR 자료를 찾아 사업 구조부터 작성하세요.",
        "customers": "고객·경쟁사·거래 관계는 미확인입니다. 공식 공시에 명시된 범위만 적고 추정은 따로 표시하세요.",
        "economics": "가격·판매량·원가·계약·현금 회수 구조가 미확인입니다. 확인된 사업별 매출과 비용을 같은 기간·회계 기준으로 읽으세요.",
        "risks": "회사 고유 위험은 미확인입니다. 원문 위험요인과 매출·비용·차입·환율 노출을 확인한 뒤 가설을 작성하세요.",
        "metrics": "공시로 확인할 사업별 매출·이익, 원가, 재고·채권, 현금흐름과 자료 기준일",
        "peers": "동종 기업과 비교 가능성도 미확인입니다. 제품·고객·기간·연결 범위가 맞는지 직접 확인하세요.",
        "url": None,
    }


def _questions(companies, primers, model, kind, seed):
    first = primers[0]
    known = companies[0]["symbol"] in _BY_SYMBOL
    if kind == "company" and known:
        business_answer = first["business"]
        business_prompt = f"{companies[0]['name']}의 사업을 공시에서 검증할 때 적절한 출발점은?"
        business_explanation = first["business"] + " 최신 사업 범위와 매출 구성은 원문 공시로 다시 확인해야 합니다."
    elif kind == "company":
        business_answer = "공식 보고서에서 제품·고객·매출 인식 구조를 직접 확인하고 미확인 사항을 구분한다."
        business_prompt = "이 사용자 지정 기업의 사업 구조가 아직 미확인일 때 첫 단계는?"
        business_explanation = "제공된 이름과 업종만으로 제품·고객·매출을 만들 수 없습니다. 원문과 대상 기간을 확인해야 합니다."
    else:
        business_answer = model["chain"]
        business_prompt = "이번 주 기업들을 가치사슬로 공부하는 방법 중 적절한 것은?"
        business_explanation = model["chain"] + " 같은 업종이라는 이유만으로 직접 납품 관계가 성립하지는 않습니다."
    return [
        _question("business-structure", "business", business_prompt, business_answer, [
            "주가가 같은 방향으로 움직이는 기업은 모두 서로의 직접 고객이므로 거래 관계를 확정한다.",
            "이름에 같은 업종이 들어가면 제품·고객과 비용 구조도 같다고 본다.",
            "소비자에게 유명한 제품 하나의 인기가 연결 전체 매출과 이익을 모두 설명한다고 본다.",
        ], business_explanation, "사업·고객·가치사슬의 구분", seed),
        _question("business-economics", "business", "사업 성장을 이익의 질과 함께 확인할 자료 조합은?",
                  (first["metrics"] + "; 동일 기간·연결 범위의 매출·영업이익과 영업현금흐름을 함께 확인한다.")
                  if kind == "company" else (model["metrics"] + "; 각 기업의 동일 기간·연결 범위와 공시 근거를 함께 확인한다."), [
                      "주가 상승률만 비교하면 사업의 판매량·수익성과 현금 회수도 확인된다.",
                      "수주·주문 또는 매출 총액만 늘면 비용·계약 조건 없이도 이익 증가를 확정한다.",
                      "연결 연간 매출과 별도 분기 이익을 그대로 나누고 결측치는 0으로 채운다.",
                  ], "매출·이익·현금은 다릅니다. 기간, 연결/별도, 통화·단위를 맞추고 사업별 지표와 운전자본을 함께 봐야 합니다. " + first["economics"],
                  "비교 가능한 재무 기간·범위와 현금흐름", seed),
        _question("inference-transmission", "inference", model["scenario"] + " 가장 타당한 해석은?", model["response"], [
            "업종 수요가 늘면 모든 기업의 영업이익은 즉시 같은 비율로 늘어난다.",
            "환율과 원가는 매출에 영향을 줄 수 있어도 이익·현금에는 영향을 주지 않는다.",
            "정책 발표나 주문 증가는 확정 매출·현금 수령과 같으므로 추가 자료는 필요 없다.",
        ], model["response"] + " 거시 변수는 계약·제품·지역과 비용 구조를 거쳐 시차를 두고 전달되며 결과를 보장하지 않습니다.",
                  model["concept"], seed),
        _question("inference-verification", "inference", "'업종 호재가 이 기업의 이익을 개선한다'는 가설을 검증하는 가장 적절한 방법은?",
                  "개선 경로와 반증 조건을 먼저 쓰고, 날짜·기간이 있는 공시의 사업별 지표·원가·현금으로 이후 결과를 대조한다.", [
                      "다음 날 주가가 오르면 다른 사업 근거 없이 가설을 맞았다고 판정한다.",
                      "좋은 기사만 모으고 반대 지표와 기존 가설의 작성 날짜는 제외한다.",
                      "확인되지 않은 고객·수익 수치를 채워 넣어 분석의 빈칸을 없앤다.",
                  ], "주가는 여러 요인의 결과입니다. 사업 가정과 관찰 결과의 기간·출처를 보존하고 지지·반박·판단 보류를 구분해야 합니다.",
                  "사업 가설의 근거·반증·불확실성", seed),
    ]


def _section(title, minutes, body, *prompts):
    return {"title": title, "minutes": minutes, "body": body, "prompts": list(prompts)}


def _sections(kind, companies, primers, model):
    summaries = "\n".join(f"{p['company']['name']}: {p['business']}" for p in primers)
    financial_prompt = "자료의 기준일·공시일·대상 기간, 연결/별도, 통화·단위와 원문 URL을 적으세요."
    quiz_body = "사업 구조와 거시 변수의 전달 경로를 묻는 객관식 네 문항에 답하세요. 정답·해설은 실제 제출 후 표시됩니다."
    judgment_body = "성장 이유·가장 큰 위험·반드시 확인할 지표를 근거와 함께 쓰고, 증거·논리·지표의 0~4점 자기평가를 따로 기록하세요. 주가 변화만으로 사업 판단의 정오를 판정하지 마세요."
    common_end = [
        _section("객관식으로 이해 확인", 5, quiz_body, "각 선택에 사용한 사업 근거와 조건을 생각하세요."),
        _section("판단과 다음 확인", 5, judgment_body, "가설이 틀렸음을 보여줄 반증 지표와 다음 확인 날짜는?"),
    ]
    if kind == "company":
        p = primers[0]
        return [
            _section("사업 구조 기초 읽기", 3, p["business"] + "\n" + p["customers"], "누가 어떤 제품·서비스의 대가를 지불하나요?", "고객 유형과 경쟁사는 무엇이며 확인된 거래 근거가 있나요?"),
            _section("공식 근거 확인", 6, _BASELINE + "\n" + p["economics"], financial_prompt, "매출·영업이익·마진과 영업현금흐름을 같은 기준으로 확인했나요?"),
            _section("내 기록과 지표", 6, p["risks"] + "\n확인할 지표: " + p["metrics"] + "\n비교 관점: " + p["peers"], "새로 알게 된 사실과 아직 모르는 개념을 구분해 적으세요.", "성장 이유·가장 큰 위험·필수 지표를 한 문장씩 적으세요."),
            *common_end,
        ]
    if kind == "value_chain":
        first = _section("산업 흐름 읽기", 3, model["chain"], "최종 수요에서 각 기업 매출까지 어떤 단계가 있나요?")
        second = _section("세 기업의 역할 검증", 7, summaries + "\n" + _BASELINE, financial_prompt, "제조·브랜드·서비스·자회사 중 어떤 역할이며 직접 거래 관계는 공시로 확인됐나요?")
        third = _section("가치사슬 내 기록", 5, "공급자·고객·병목·가격 결정력과 원가 전가 경로를 그려보세요. 미확인 관계는 표시하고 실제 계약처럼 쓰지 마세요.", "누가 수요 증가의 이익을 먼저 얻고 누가 비용을 부담하나요?", "공급 제약과 대체 가능성을 확인할 지표는?")
    elif kind == "comparison":
        first = _section("비교 기준 세우기", 3, summaries, "세 기업의 제품·고객·연결 범위에서 가장 큰 차이는?")
        second = _section("같은 기준으로 원문 비교", 7, _BASELINE + "\n" + "\n".join(f"{p['company']['name']}: {p['metrics']}" for p in primers), financial_prompt, "같은 기간의 매출·이익·마진·현금을 비교할 수 없다면 어떤 차이를 표시해야 하나요?")
        third = _section("우열보다 차이 기록", 5, "성장·수익성·현금 회수와 위험을 같은 축에서 비교하세요. 사업 구성과 회계 범위가 다른 총액을 단순 순위로 만들지 마세요.", "각 기업의 성장 조건과 반증 지표는?", "비교에서 아직 자료가 없는 항목은?")
    elif kind == "scenario":
        first = _section("가정 읽기", 3, model["scenario"], "여기서 주어진 조건과 실제 관찰된 사실은 무엇이 다른가요?")
        second = _section("전달 경로 검증", 7, model["chain"] + "\n" + summaries + "\n" + _BASELINE, financial_prompt, "환율·금리·원재료·수요 중 각 기업의 매출과 비용에 닿는 경로는?")
        third = _section("조건별 가설 기록", 5, "수요·가격·원가·계약·현금의 경로와 시차를 나누고 좋은 조건·나쁜 조건을 각각 적으세요. 실제 결과로 확정하지 마세요.\n관찰할 자료: " + model["metrics"], "어떤 조건에서는 이익이 늘고 어떤 조건에서는 줄 수 있나요?", "다음 공시에서 가설을 반박할 지표는?")
    else:  # review
        first = _section("주간 구조 복기", 3, model["chain"] + "\n" + summaries, "자료를 닫고 각 기업의 고객·제품·이익 동인을 설명할 수 있나요?")
        second = _section("기록과 근거 다시 읽기", 7, "저장된 이번 주 기록과 실제 제출한 오답이 있다면 먼저 읽으세요. 기록이나 제출이 없으면 이번 주 첫 복습으로 진행하며 점수·완료 이력을 만들지 않습니다.\n" + _BASELINE, financial_prompt, "새로운 사실과 기존 생각을 구분했나요? 오답 개념을 원문으로 설명할 수 있나요?")
        third = _section("이해와 가설 수정", 5, "과거 판단을 지우지 말고 당시 가정·지금 관찰·출처를 대조하세요. 자료가 부족하면 판단 보류로 남깁니다.\n복습 지표: " + model["metrics"], "당시 판단을 지지하거나 반박하는 사업 근거는?", "가장 약한 개념과 다음 복습에서 다시 볼 질문은?")
    return [first, second, third, *common_end]


def _quiz_version(lesson):
    definition = {"schemaVersion": 1, "questions": lesson["questions"], "judgmentPrompt": lesson["judgmentPrompt"]}
    payload = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "learning-quiz-v1:" + hashlib.sha256(payload).hexdigest()


def build_lesson(curriculum: dict, date_str: str, symbol: str | None = None, company: dict | None = None) -> dict:
    """Build a private lesson. Explicit company studies may use unscheduled dates.

    Date strings represent the learner's Asia/Seoul calendar date; this function
    never infers a local date from a server clock. Invalid inputs and a regular
    request outside the curriculum raise ValueError.
    """
    curriculum = _curriculum(curriculum)
    lesson_date = _date(date_str)
    if company is not None or symbol is not None:
        if company is not None:
            selected = _company(company)
            if symbol is not None and symbol != selected["symbol"]:
                raise ValueError("company symbol mismatch")
        else:
            if not isinstance(symbol, str):
                raise ValueError("invalid company symbol")
            if symbol in _BY_SYMBOL:
                selected = deepcopy(_BY_SYMBOL[symbol]["company"])
            else:
                selected = next((deepcopy(c) for w in curriculum["weeks"] for c in w["companies"] if c["symbol"] == symbol), None)
                if selected is None:
                    raise ValueError("unknown company requires an explicit identity")
        companies = [selected]
        industry = selected["industry"]
        kind, week_id = "company", "company-study"
    else:
        offset = (lesson_date - _date(curriculum["startDate"])).days
        if not 0 <= offset < len(curriculum["weeks"]) * 7:
            raise ValueError("no lesson scheduled for this date")
        week = curriculum["weeks"][offset // 7]
        weekday = offset % 7
        kind = ("company", "company", "company", "value_chain", "comparison", "scenario", "review")[weekday]
        companies = deepcopy([week["companies"][weekday]]) if weekday < 3 else deepcopy(week["companies"])
        industry = companies[0]["industry"] if kind == "company" else week["industry"]
        week_id = week["id"]
    primers = [_BY_SYMBOL.get(c["symbol"], _unknown_primer(c)) for c in companies]
    # A user-authored industry label does not establish facts about an unknown
    # company. Mixed or relabelled groups use evidence-first general questions.
    matching_known_industry = all(c["symbol"] in _BY_SYMBOL and c["industry"] == industry for c in companies)
    model = _INDUSTRIES.get(industry, _GENERAL) if matching_known_industry else _GENERAL
    title = {"company": f"{companies[0]['name']} — 사업 구조와 투자 가설",
             "value_chain": f"{industry} — 가치사슬과 이익의 흐름",
             "comparison": f"{industry} — 세 기업 비교",
             "scenario": f"{industry} — 거시 시나리오",
             "review": f"{industry} — 주간 복습과 가설 점검"}[kind]
    seed = json.dumps({"curriculum": curriculum["id"], "week": week_id, "date": date_str,
                       "kind": kind, "symbols": [c["symbol"] for c in companies]}, sort_keys=True)
    sources = [deepcopy(_DART)]
    sources.extend({"title": f"{p['company']['name']} 공식 사업·IR — 최신 공시와 대조", "url": p["url"]} for p in primers if p["url"])
    if kind == "scenario":
        sources.append(deepcopy(_BOK))
    lesson = {
        "id": "lesson-" + hashlib.sha256(seed.encode()).hexdigest()[:24],
        "date": date_str, "kind": kind, "title": title, "industry": industry,
        "companies": companies, "duration": 25, "sections": _sections(kind, companies, primers, model),
        "sources": sources, "questions": _questions(companies, primers, model, kind, seed),
        "judgmentPrompt": (
            "확인된 사업 근거와 자료 기준일·기간·원문 URL을 바탕으로 성장 이유, 가장 큰 위험, 반드시 확인할 지표를 쓰세요. "
            "거시 조건이 매출·원가·현금에 전달되는 경로와 반증 조건을 설명하고, 미확인 사실을 표시하세요. "
            "증거·논리·지표를 각각 0~4점으로 직접 평가하세요. 이는 자기평가이며 AI나 서버가 판단의 정답을 채점한 점수가 아닙니다."
        ),
    }
    lesson["quizVersion"] = _quiz_version(lesson)
    return deepcopy(lesson)


def public_lesson(lesson: dict) -> dict:
    """Copy only the public contract, withholding the pinned grading definition."""
    fields = ("id", "date", "kind", "title", "industry", "companies", "duration", "sections", "sources", "judgmentPrompt")
    public = {field: deepcopy(lesson[field]) for field in fields}
    public["questions"] = [
        {field: deepcopy(question[field]) for field in ("id", "dimension", "prompt", "options")}
        for question in lesson["questions"]
    ]
    public["quizVersion"] = _quiz_version(lesson)
    return public
