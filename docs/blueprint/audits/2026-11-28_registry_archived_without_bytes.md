# Audit 8 — 공시 응답 해시와 원문 보관 상태

`audit8-registry-archived-without-bytes`는 기관 원장의 공시 보관 상태를 검증한다. Blueprint A1·Q7·L0/L1·I6, 09 제품 목적 대응표 P01·P02에 연결된다.

작업 시작 시 보험사 53곳 중 공시 접근이 확인된 8곳은 이미 `disclosure_access=reachable`, `disclosure_status=unqueried`였고 `archived` 집계는 0이었다. 각 공시 URL에 대한 HTTP 200과 응답 본문의 SHA-256은 `sources.csv`에 있다. 원문 불변 보관을 확인하려면 `observations/`에서 관측 기록을 찾아 해당 보관 객체의 바이트와 해시를 대조해야 한다.

정규화기는 홈페이지 접근 결과의 대체 매핑을 `unqueried`, `blocked`, `failed`로 제한한다. 접근이 확인된 공시 URL은 보관 전 사유와 함께 `unqueried`로 기록한다. 읽기 전용 CI 원장 검사기는 기관 CSV의 `disclosure_status=archived`를 파일·행 번호·기관 ID와 함께 거부한다.

실제 원장의 임시 복사본에서 HTTP 200과 SHA-256을 유지한 채 8행에 `archived`를 넣었다. 검사기는 8행 모두를 지목했고 검사 전후 CSV 바이트가 일치했다. 같은 CI 명령의 종료 코드 1, 공제·기타 기관의 공시 보관 오표기 거부, 상품 목록 상태의 독립 처리를 확인했다. 홈페이지 접근 결과에 `archived`를 매핑하면 정규화기가 CSV 교체 전에 중단했다. 새 시험 세 개는 변경 전 코드에서 모두 실패했다. [검사기 시험](../../../tools/tests/test_registry_check.py) · [정규화기 시험](../../../tools/tests/test_registry_normalize.py).

`python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v`는 91개 통과했다. `python3 -I tools/registry_check.py`와 `python3 -I tools/vocab_check.py`는 현재 원장에서 통과했다. `tools/tests` 전체는 1,815개 중 1,809개 통과·6개 건너뜀, `tools/daemon/runner_verify/tests`는 81개 통과했다. Rust 1.98.1에서 워크스페이스 시험은 564개 통과·1개 제외, 규칙 순서 시험은 2개, 시나리오 API와 온톨로지 실행기 시험은 각각 4개 통과했다.

이 실행은 로컬 원장 도구의 회귀 증거다. 실제 R2 상태는 조회하지 않았다. P01·P02의 완료는 09의 실제 분모·보존·구획 추출·판 연결 증거로 판단한다.
