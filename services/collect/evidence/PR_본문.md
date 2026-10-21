## 목적과 설계 연결

- 과제: T-DT-01. 기존 설계 구현, 범위·정책 변경 없음.
- A1·A2·A4 / Q1·Q2·Q4·Q7 / L1 / I6·I11·I12 / M2.
- 요구 ID: R04(직접). R02·R10·R21·R22는 후속 소비 경로 지원이며 완료 주장 아님.
- 소비자 질문: 이 숫자·조건의 원문은 무엇이며, 과거 원문과 미확보 사유가 남아 있는가?
- 계약: DATA_PIPELINE_CONTRACT §3.1, ADR-0015·0016·0017, 09 대응표 P02·P03.

## 변경 내용

- `onjeon-collect`: 내용 주소 원본 키, 조건부 쓰기, 관측 기록, 목록, 복사와 전 키 재다운로드 검증.
- 같은 URL에서 바이트가 달라지면 이전 원본을 교체하지 않고 새 원본·관측을 보존한다.
- 형식 실패는 quarantine, 미확보는 사유가 있는 unacquired로 분리한다. 문서 역할은 공유 어휘 enum을 쓴다.
- 원본 키 연결 오류, 예약 메타데이터 덮어쓰기, 정적 경로/심볼릭 링크 탈출, 동시 쓰기 임시 파일 충돌, 잘못된 listing의 항목 누락을 방지한다.
- 로컬 S3는 loopback HTTP에서 조건부 PUT·서명·체크섬·HEAD/GET/listing을 지원한다. 삭제 API/명령 없음.
- 화면·가격·규칙·공유 스키마 변경 없음. 공시 원본용이며 개인 자료 보관용이 아니다.

## 실제 검증과 한계

- 재실행: `python3 services/collect/tests/verify.py`. 전체 명령·종료 코드·원본별 SHA-256: `verification.json`, 출력: `verification-00.log`~`verification-10.log`.
- Rust collect 18개 통과, Python/Rust 바이트 적합성 등 Python 2개 통과. 전체 Rust workspace 통과.
- Python tools 388개 실행, 실패 없음, 6개 skip. 실제 원본/추출기 환경이 필요한 시험 등의 skip은 통과 증거가 아니다.
- collect fmt·clippy 통과. 누출·스켈레톤 정적 검사와 각각의 selftest 통과. 런타임 UI 경로를 시험한 것으로 표현하지 않는다.
- 의존 경계 검사는 실패: 수정하지 않은 packages/ontology의 knowledge→twin 위반 3개. `verification-06.log` 참조. `git diff --quiet -- packages/ontology` 종료 0. 정책을 바꾸거나 허용 경로 밖 코드를 수정하지 않았다.
- 실제 TCP fixture로 로컬 S3 전송을 확인했지만 Compose/SeaweedFS 실기동과 실제 R2를 시험하지 않았다.
- R2/AWS는 항상 fail-closed다. 공개 Session 생성자가 없고, Rust에서 예산 원장 입장·예약·정산을 구현한 척하지 않는다. 실제 원격 작업은 기존 Python 예산 도구의 책임이다.
- 형식 검증은 비어 있음·기본 시그니처·HTML MIME 불일치·JSON 파싱 수준이다. PDF 페이지/구획 추출과 판 연결은 후속 단계다.
- 합성 fixture 검증만으로 P02 확보율이나 P03 실제 R2 관측 대조, 실제 화면 연결, 첫 출시 완료를 선언하지 않는다.

## 작성·리뷰·대상 고정

- 작성 역할: 구현 및 자체 검증. 실행 경로: CLI → 이 worktree → cargo / Python unittest. 모델 식별자 원문은 기록하지 않았다.
- 기준 SHA: `2621d66367637c649e7761c0ed70708d1636a6d2`.
- 대상 commit SHA: 감독자 커밋 후 기입 필요. 이 세션은 커밋·푸시·GitHub 호출을 하지 않았다. 현재 코드 바이트는 `verification.json`의 파일별 SHA-256으로 고정했다.
- 독립 리뷰: 미실시. 작성 계열과 다른 리뷰어가 감독자 생성 대상 SHA에 고정해 리뷰해야 한다. 자체 검증을 독립 리뷰로 대체하지 않는다.
- 변경 범위: services/collect/**, Cargo.toml의 workspace member 추가, cargo 생성 Cargo.lock. 최초 작업 트리에 이미 있던 미완성 collect 파일과 workspace 등록을 이어서 완성했다.
- 감독자는 별도 task runner의 allowed_paths와 최종 커밋 범위를 확인해야 한다. 금지 문서는 수정하지 않았다.

## 확인

- [x] BLUEPRINT·PRINCIPLES 및 보존 계약을 확인했다.
- [x] 비밀값·실제 개인 자료·원문 발췌를 증거에 넣지 않았다. 합성 입력은 fixture_only 또는 origin=fixture로 구분했다.
- [x] 예산·보안 정책을 완화하지 않았고, 실제 원격 호출·삭제를 하지 않았다.
- [ ] 의존 경계의 기존 위반은 담당 과제에서 해결 필요.
- [ ] 대상 commit SHA와 독립·타 계열 리뷰는 감독자 후속 관문.
- [ ] 실제 데이터와 화면을 포함한 P02·P03 제품 완료 증거는 후속 관문.
