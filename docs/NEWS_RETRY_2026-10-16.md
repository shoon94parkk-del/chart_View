# 뉴스 제공처 오류 재시도 — 2026-10-16

기존 `/api/personalized-news`는 제공처의 일시 오류도 300초 캐시에 보관한다. 화면의 재시도가 브라우저 캐시만 우회하면 복구된 제공처를 다시 확인하지 못한다.

선택적 `force=true`를 추가해 명시적 재시도에서 **오류 그룹만** 다시 확인한다. 성공·실제로 뉴스 없음인 그룹은 기존 300초 캐시를 유지한다. 기존 내부 `_cached_fetch(force=True)`의 전체 재조회 의미, 동시 제공처 제한·관계 판단·순위·응답 형식은 유지한다. 일반 호출과 웹 UI에는 변경이 없다. 토스 프런트의 재시도에서만 이 플래그를 사용하며 실패/부분 응답은 브라우저 성공 캐시에 넣지 않는다.

`tests/test_v37_personalized_news.py`의 HTTP TestClient와 합성 제공처로 실패→복구, 일반 오류 캐시 적중, 부분 재시도의 정상/no_news 보존 및 기존 내부 force를 검증했다. 새 회귀는 수정 전 2개 실패 후 통과했다. 뉴스·관계 집중 검사 29개 및 **전체 Python 960개 통과**(기존 경고80개,15.99초), `python scripts/build_frontend_bundle.py --check` exit0. 별도 독립 코드 검토 PASS. 실제 제공처·LLM 호출은 테스트에 사용하지 않았다.

변경 파일: `news_service_v37.py`, `tests/test_v37_personalized_news.py`, 관련 운영 기록. 매크로·PICK/LAB·선정 데이터·계산·기존 Web 번들·환경 설정은 변경하지 않았다. 기준 main은 `934e0546f78e0e2ee0017b2923dc0cae49c7ad27`이다. PR CI·정확한 배포 revision 및 운영 결과는 PR 댓글에 별도로 남긴다.
