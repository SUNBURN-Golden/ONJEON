## 목적과 설계 연결

- 과제: T-KN-12 (zone knowledge, stage S2). 기존 설계(02_구현계약 §1.5, 전체_구조_1차_정리 영역 C, 소비자_기능_필요정보 §4·§6, O05) 구현. 정본 문서·어휘는 건드리지 않았다.
- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A5·A6(필요성 판단의 기반이 되는 판단 기준 관리), Q5·Q6·Q7(기준 평가 이유의 근거 사슬), L3~L5·L7(knowledge 구역, 별도 기준 릴리스), I6(판마다 근거 참조)·I16(기준 릴리스 불변), M5(필요성 판단 경험의 기반)
- 해결하는 소비자 질문: "이 판단은 어떤 기준·어느 출처에 근거하는가"를 판과 출처로 답할 수 있게 하는 저장 구조
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R08(근거 없는 판은 저장·릴리스 불가), R21(정정 이력·변경 목록으로 영향 추적), R22(정정된 판에 기대는 저장 결과를 stale로 표시하는 입력). 필요성 결과 자체(R13 인접)는 T-AP-09
- 관련 결정 ID / ADR: O05(기본 필요액 없음 — 이 과제에서 생성하지 않음), D-08(서비스 적용 승인 관문은 T-KN-14), C-27
- 설계 변경인가, 기존 설계 구현인가: 기존 설계 구현. §1.5 계약의 객체(기준·판·출처·적용 범위·기준 릴리스·변경 목록)만 만들고 `need_result`·`criteria_application`·`user_assumption`은 후속 과제에 남긴다

## 과제와 작성 정보

- 과제 ID: T-KN-12 (선행 T-CT-05·T-CT-02 병합됨 — `infra/db/criteria/` 스키마와 `criterion_source_kind` 등 어휘 축 사용)
- 작성에 참여한 모델 역할·실행 경로: 빌더 역할 하나. 감독 프로세스가 연 코딩 에이전트 CLI 세션, 작업 트리 `wt/T-KN-12` 안에서만 작업. 모델 식별자 원문은 적지 않는다. 독립 리뷰는 작성 계열과 다른 계열이 감독자가 고정한 대상 SHA에 붙여야 한다(아직 미실시)
- 대상 SHA: 이 PR의 head 커밋이 대상이다. 커밋·푸시는 감독 프로세스가 하므로 head SHA는 커밋 직후 기입

## 변경 내용

- `services/criteria`(crate `onjeon-criteria`) 신설:
  - `Criterion`/`CriterionVersion`/`CriterionSource`/`CriterionScope`/`CriterionKind`(4종): 기준 항목과 판. 판은 출처 ≥1 + `evidence_kind`(어휘 `criterion_source_kind`) + 적용 범위(`scope{situations,subjects}` 필수 비어 있지 않음)를 항상 가진다
  - `CriterionStore`: 삽입 시 검증(식별자 `crit:<slug>`·`crit:<slug>@<n>`, 출처 문법 `raw:`·`clause:`·`obs:`의 evidence_ref, 날짜, K8 개인 식별자 접두어, 알 수 없는 키). 수정·삭제 없음 — 정정은 새 판 + `supersedes`(바로 이전 판)·`correction_reason` 쌍
  - `freeze`/`verify`: 기준 릴리스 `crel:<yyyymmdd>-<n>`(지식 릴리스 `rel:`와 별도 ID). 고정 시점 각 기준의 최신 판 목록 + 내용 SHA-256. fixture 판 거부(ONJ-KN-S-050), 구성원 누락·제자리 변경 검사(ONJ-KN-S-052)
  - `diff_releases`·`diff_to_tips`: 변경 목록(added/corrected/removed). `affected_version_ids()`가 `conclusion_dependency.deps.criteria`에서 영향받는 결론을 찾는 입력
  - `load.rs`: `data/criteria/` 파일 계약 적재기. `default`·`defaults`·`default_*` 키는 어느 위치에도 있으면 `DefaultOutsideGate`로 거부 — 기본 필요액·기본값 후보는 T-KN-13(`data/criteria/defaults/`)+ D-08 기록(T-KN-14)의 경로다
- `data/criteria/` 신설: `README.md`(파일 계약·규칙·릴리스·변경 목록 설명), `criterion-file.schema.json`, `release-file.schema.json`, `criteria/`, `releases/`(둘 다 비어 있음 — 서비스 기준 0건)
- `Cargo.toml` workspace members에 `"services/criteria"` 한 줄 추가, `Cargo.lock`은 cargo 재생성분만
- 화면·가격·규칙·공유 스키마 변경 없음. 개인 영역 객체 없음

## 검증과 한계

- 수락 기준 대응: `need-criteria-versioned` 통과(v1→v2 정정 시 v1 보존·v2 supersedes; 출처 없는 판 저장·릴리스 거부; `default*` 키 거부). 모든 기준 판에 출처·근거 종류·적용 범위 강제(삽입 시). 기준 릴리스는 `crel:` 별도 ID. 기본 필요액 값은 생성하지 않음(`data/criteria/defaults/`도 없음)
- 실제 수행한 검증 및 결과:
  - `cargo test -p onjeon-criteria` → 33/33 통과(`evidence/cargo_test.log`, `TEST_LOG.txt`). 필수 시험 외 판 사슬·릴리스·변경 목록·파일 검증·DB/어휘/산출 경로 대조 시험 포함
  - `cargo fmt --check -p onjeon-criteria` 통과, `cargo clippy -p onjeon-criteria --all-targets -- -D warnings` 통과
  - `cargo test --all` → 전 워크스페이스 통과(기존 크레이트 영향 없음)
  - `python3 -I tools/ci/check_leak.py` → 0건, `check_skeleton.py` → 0건(정적), `check_deps.py` → 기존 packages/ontology 지식→트윈 위반 3건만(이 과제 변경 없는 기존 문제; `services/criteria`는 지적 없음)
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: 합성 검증(시험 전용 fixture 파일·인라인 JSON, `origin=fixture`). 실제 출처 수집·기준 작성 절차는 이 과제 범위 밖
- 미정 또는 지원하지 않는 동작: 인메모리 저장소뿐(DB 적재·쿼리는 후속 적재기). 출처 `ref`의 실재 확인은 하지 않는다(문법만). `criteria_application`(D-08)·`need_result`·`user_assumption`·기본값 후보는 T-KN-13·T-KN-14·T-AP-09의 범위다

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다(없음).
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다 — 해당 없음(기준 자료는 아직 0건, 구조만 신설).
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [ ] 설계와 구현의 상태를 요구사항 추적표에 반영했다 — `docs/blueprint/**`는 금지 경로라 반영하지 않았다. 병합 후 별도 갱신 필요.
