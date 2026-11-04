# Audit 4 — 기관 원장 정규화의 빈 입력·원자적 저장·CI

대상: `audit4-registry-normalize-tests`, `tools/registry_normalize.py`.
연결: Blueprint A1·Q7·L0/L1·I6(근거 보존 기반)·V0/M1, 09 제품 목적 대응표 P01·P02.

작업 시작 시 이미 `tools/tests/test_registry_normalize.py`와 CI의 전체 Python 발견 실행이 있었다. `disclosure_access` 누락도 기존 `.get()` 경로에서 안전했다. 이 부분을 새 구현으로 주장하지 않고 공시 URL이 있으나 접근 열이 없는 입력을 별도 회귀 시험으로 보강했다. 홈페이지 접근 결과에 따라 `unqueried`·`failed`·`blocked`를 유지하고 `disclosure_entry_missing`을 기록한다.

이번 변경으로 빈 접근 로그에서 `rows[0]`을 읽던 오류를 해결했다. 0바이트·헤더만 있는 원장과 접근 로그는 0행을 반환하고 바이트를 그대로 유지한다. 두 CSV 저장 경로는 같은 디렉터리에 임시 파일을 만들고, 전체 CSV 작성·기존 권한 적용·flush·fsync·파일 닫기 후 `os.replace()`로 교체한다. 쓰기·동기화·교체 실패는 호출자에게 전달하며 원본 바이트를 보존하고 임시 파일을 정리한다. 원자성은 **개별 파일 교체**에 적용되며 네 CSV를 묶는 트랜잭션이나 전원 장애 후 디렉터리 엔트리 영속성을 보장하지 않는다.

회귀 시험은 두 함수 모두에 대해 교체 직전 원본 바이트와 완성된 임시 CSV를 대조하고, 파일 권한·임시 파일 정리·부분 쓰기·fsync·교체 오류를 검사한다. 기존 어휘 매핑·원문 증거 보존·멱등성·격리된 네 CSV 실행 시험도 유지한다. CI에는 외부 의존성 설치·Rust 빌드 전에 표준 라이브러리만으로 실행되는 `Registry normalization regressions` 단계를 추가했고 시험이 이 연결을 검사한다. CI에서 실제 원장에 정규화 명령을 실행하지 않는다.

실행 명령·결과·수정 전 재현 로그는 [작업 증거](../../../tools/evidence/audit4-registry-normalize-tests/README.md)에 기록한다. 시험은 임시 CSV와 로컬 빌드만 사용하고 저장소의 실제 원장 CSV는 수정하지 않았다. GitHub CI 실행 결과는 주장하지 않으며 선언된 CI 명령을 로컬에서 검증했다.

이 기록은 P01·P02의 원장 관리 도구 회귀 증거다. 실제 상품·특약 분모, 공시 확보율, 원문 보관, 트윈·소비자 화면 또는 첫 출시 완료 증거를 대체하지 않는다.
