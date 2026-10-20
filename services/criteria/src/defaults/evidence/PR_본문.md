## 목적과 설계 연결

- 과제: T-KN-13 (zone knowledge, stage S4). 기존 설계(02_구현계약 §1.5 "기본값" 행,
  통합안 D-08, O05, 소비자_기능_필요정보 조사 항목) 구현. 정본 문서·어휘·결정
  기록은 건드리지 않았다.
- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A5·A6(필요성
  판단 근거의 자료 구조), Q5·Q6(기본값이 어디서 오는가를 출처로 답함), L3~L5
  (knowledge 구역 후보 적재), I6(판마다 근거 참조), M5("필요한 돈" 기본값 경로의
  자료 구조 — 기본값 적용은 M5 관문의 사용자 결정 사항)
- 해결하는 소비자 질문: "이 기본값은 어느 공공 통계에서 왔고, 언제 갱신되는가"를
  출처 해시·적용 대상·갱신 주기로 답할 수 있는 후보 저장 구조
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R08 계열(근거 없는 판은 저장·노출
  불가), R13 인접(필요성 판단 결과의 입력 경로 — 결과 자체는 T-AP-09)
- 관련 결정 ID / ADR: O05(기본 필요액 자동 생성 없음 — 후보만 적재), D-08(후보는
  적용 승인 기록 없이 서비스에 나가지 않는다 — 기록은 T-KN-14), C-27
- 설계 변경인가, 기존 설계 구현인가: 기존 설계 구현. §1.5 기본값 행과 D-08이
  정한 후보-적재 계약만 만든다. `criteria_application`·`need_result`·
  `user_assumption`은 T-KN-14·T-AP-09·개인 영역 과제의 범위다.

## 과제와 작성 정보

- 과제 ID: T-KN-13 (선행 T-KN-12 병합됨 — `onjeon-criteria` 크레이트와
  `data/criteria/` 계약 사용)
- 작성에 참여한 모델 역할·실행 경로: 빌더 역할 하나. 감독 프로세스가 연 코딩
  에이전트 CLI 세션, 작업 트리 `wt/T-KN-13` 안에서만 작업. 모델 식별자 원문은
  적지 않는다. 독립 리뷰는 작성 계열과 다른 계열이 감독자가 고정한 대상 SHA에
  붙여야 한다(아직 미실시)
- 대상 SHA: 이 PR의 head 커밋이 대상이다. 커밋·푸시는 감독 프로세스가 하므로
  head SHA는 커밋 직후 기입

## 변경 내용

- `services/criteria/src/defaults/`(`onjeon-criteria`의 `defaults` 모듈) 신설 —
  허용 경로 안 모듈 소스. `src/lib.rs`의 `pub mod defaults;` 선언은 허용 경로
  밖이라 배선되지 않은 상태로 둔다(아래 "경로 정책 상태" 참조):
  - `DefaultCandidate`/`CandidateVersion`: 후보 항목(`def:<slug>`)과 판
    (`def:<slug>@<n>`). 후보는 `kind`(needed_amount|reference_stat)·`label`·
    `scope{situations,subjects}`·`update_cycle`·`applied`·`recorded_at`,
    판은 `value`(monetary_amount|rate|count|structure, 정수 원·베이시스
    포인트 — 부동소수 없음)·`sources`·`valid_from/to`·정정 사슬을 가진다
  - `DefaultsStore`: 삽입 시 검증 — 출처 1개 이상·각 `ref`는
    `raw:sha256:` RawAsset 해시뿐·`evidence_kind`는 `public_statistic`뿐·
    `applied`는 `false`뿐·범위·갱신 주기 필수·날짜·선형 정정 사슬·K8·알 수
    없는 키. `for_service()`는 `applied` 후보만 돌려주므로 적용 승인 기록이
    없는 한 항상 비어 있다 — "후보는 표시되지 않는다"가 실행 형태를 가진다
  - `service`: `display()`는 `DisplayKind::ReferenceStatistic` 하나만 낸다 —
    `fact` 변형이 없고 배지 문자열은 "참고 통계"로 고정. `effective()`는 사용자
    가정이 있으면 항상 가정을 돌려주고(기본값이 덮지 않는다), 가정도 후보도
    없으면 `None`이다 — 0·평균으로 채우지 않는다(D-08)
  - `load`: `data/criteria/defaults/candidates/*.json` 파일 계약 적재기.
    비어 있는 경로는 빈 저장소 — 후보 0건도 정상 상태
- `services/criteria/src/defaults/`에 후보 파일 계약 부속물도 함께 둔다:
  `README.md`(후보 파일 계약·적재 규칙·후보 0건 사유·경로 상태),
  `default-file.schema.json`, `evidence/`(이 문서·시험 로그).
  정식 데이터 적재 위치 `data/criteria/defaults/candidates/`는 계약으로
  남아 있고 후보는 0건이다(확정된 공공 통계 RawAsset이 저장소에 아직 없음)
- 화면·가격·규칙·공유 스키마·개인 영역 객체 변경 없음

### 경로 정책 상태 (fix round 1 — 명세상 허용 경로:
### `data/criteria/defaults/**`, `services/criteria/src/defaults/**`만)

빌드 라운드는 `src/lib.rs`(`pub mod defaults;`)와 `tests/conformance.rs`
(후보 적재 단언으로의 교체) 두 파일을 허용 경로 밖 최소 편차로 바꿨으나
가드가 거부했고, fix round 1 지시에 따라 둘 다 원본으로 되돌렸다.

되돌린 뒤 남는 구조적 제약 두 가지:

- `src/defaults/` 디렉터리 모듈은 `src/lib.rs`의 `pub mod defaults;` 선언
  없이는 컴파일되지 않는다 — 모듈 소스·시험(17개)은 존재하되 배송 상태에서
  실행되지 않는다. 실행 확인은 배선을 임시로 켠 로컬 상태에서 수행하고
  되돌렸다(`evidence/cargo_test_defaults.log` §1·§2).
- `services/criteria/tests/conformance.rs`의 기존 단언
  `assert!(!repo("data/criteria/defaults").exists())`이 이 과제의 산출 경로
  존재 자체를 금지한다. 시험 파일도 허용 밖이라 고칠 수 없어,
  `cargo test --all`(CI 등가 명령)을 유지하기 위해 `data/criteria/defaults/`를
  작업 트리에서 제거하고 계약 문서·스키마·증거는 허용 경로 안(`src/defaults/`)으로
  옮겼다.

해소에 필요한 명세 변경(후속 라운드·과제의 몫): 이 과제의 `allowed_paths`에
`services/criteria/src/lib.rs`와 `services/criteria/tests/conformance.rs`
(또는 `services/criteria/tests/**`)를 예외로 추가하면, `pub mod defaults;`
배선과 conformance 단언 갱신, `data/criteria/defaults/` 생성을 한 번에
할 수 있다. 같은 공백은 `src/<하위>/**`로 좁혀진 다른 지식·서비스 과제
(T-KN-14의 `src/application/**` 등)에도 그대로 적용된다.

## 검증과 한계

- 수락 기준 대응: 배선을 임시로 켠 상태에서 `cargo test -p onjeon-criteria
  defaults` → 17/17 통과(`evidence/cargo_test_defaults.log` §1). 출처 없는
  기본값 없음(`sources` ≥1 + `raw:` + `public_statistic` 강제, 시험
  unsourced·non_statistic·non_raw·malformed), 사용자 가정이 기본값을 덮지
  않음(`effective` 시험), 기본값은 "참고 통계"로만 표시되고 사실로 표시되지
  않음(`DisplayKind` 단일 변형 시험), 후보는 `applied=false`로만 적재되고
  `for_service`가 항상 비어 서비스에 나가지 않음
- 배송 상태(배선 없음)에서는 같은 명령이 일치 시험 0개로 종료한다
  (`evidence/cargo_test_defaults.log` §2) — 이것을 시험 통과로 주장하지
  않는다. 모듈 시험이 CI에서 실제로 도는 것은 배선이 허용된 뒤다
- 실제 수행한 검증 및 결과(배송 상태):
  - `cargo test -p onjeon-criteria` → 33/33 통과(T-KN-12 원본 conformance 포함)
  - `cargo test --all` → 전 워크스페이스 통과
  - `cargo fmt --all -- --check` 통과(모듈 파일 개별 `rustfmt --check`도 통과),
    `cargo clippy -p onjeon-criteria --all-targets -- -D warnings` 통과
  - `python3 -I tools/ci/check_leak.py` → 0건, `check_skeleton.py` → 0건(정적),
    `check_deps.py` → 기존 packages/ontology 지식→트윈 위반 3건만(이 과제 변경
    없는 기존 문제; `services/criteria`는 지적 없음)
  - `python3 tools/vocab_check.py`·`validation_check.py`(+`--selftest`)·
    `python3 -m unittest discover -s tools/tests`(433개)·
    `docs/blueprint/proposals/설계검토_결과/검증/spec_check.py`(44/44·72/72)
    전부 통과
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: 합성 검증(시험 전용
  fixture JSON, `origin=fixture`). 실제 공공 통계 원본의 보존·해시 확정은
  수집 파이프라인(data 구역)의 몫이고 이 과제는 후보 0건을 적재한다
- 미정 또는 지원하지 않는 동작: 인메모리 저장소뿐(DB 적재는 후속 적재기).
  출처 `ref`가 가리키는 RawAsset의 실재 확인은 하지 않는다(문법 + 종류 검사 —
  해시 검증은 보존 검사기의 몫). 후보를 `applied`로 바꾸는 경로는 없다
  (T-KN-14의 `criteria_application`·D-08). 필요성 판단 결과는 T-AP-09의 범위다

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다(없음).
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다 — 후보 0건이므로
  자료 변경 없음(구조·계약만 신설).
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [ ] 설계와 구현의 상태를 요구사항 추적표에 반영했다 — `docs/blueprint/**`는
  금지 경로라 반영하지 않았다. 병합 후 별도 갱신 필요.
