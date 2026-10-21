# onjeon-criteria

판단 기준 관리(영역 C, T-KN-12, 02_구현계약 §1.5). 약관 지식("무엇을 지급하나")과 다른
종류의 판단("무엇을 우선 살펴볼 만한가")을 저장·판·근거가 나뉜 구조로 관리한다.

- `Criterion`(`crit:<slug>`)와 `CriterionVersion`(`crit:<slug>@<n>`): 기준 항목과 그 판.
  판마다 출처(`sources` ≥1, `ref`는 `raw:`·`clause:`·`obs:` 근거 참조)와 근거 종류
  (`evidence_kind` = 어휘 축 `criterion_source_kind`), 적용 범위(기준의 `scope{situations,
  subjects}`)가 있다. `editorial`은 "참고 통계"가 아니라 "온전의 판단" 근거다.
- 판은 불변. 정정은 새 판 + `supersedes`(바로 이전 판) + `correction_reason`이다.
  추가만 있고 수정·삭제는 없다.
- `criteria release`(`crel:<yyyymmdd>-<n>`): 고정 시점의 판 목록(members) + 내용 해시
  (SHA-256, 정규 JSON). 지식 릴리스(`rel:`)와 별도 ID 공간이다. `freeze`로 고정하고
  `verify`가 구성원 누락·제자리 변경을 잡는다(ONJ-KN-S-052).
- 변경 목록(`diff_releases`·`diff_to_tips`): added/corrected/removed 항목과 옛 판 id.
  `conclusion_dependency.deps.criteria`에서 영향받는 결론을 찾는 입력이다(§1.5 정정 영향).

## 하지 않는 것

- **기본 필요액·기본값 없음.** 기준 판에 `default`·`defaults`·`default_*` 키가 있으면
  적재가 거부된다(`DefaultOutsideGate`). 후보 적재는 T-KN-13(`data/criteria/defaults/`),
  서비스 적용 승인(`criteria_application`, D-08)은 T-KN-14다. 기본값이 없으면 사용자
  직접 가정만 쓴다(O05).
- `need_result`·`user_assumption`·`criteria_application`은 다른 과제(T-AP-09·T-KN-14)다.
- 데이터베이스가 아니다 — 파일 계약(`data/criteria/`)의 검증과 같은 규칙을
  `infra/db/criteria/`도 강제한다. 실제 DB 적재는 후속 적재기 과제의 몫이다.

## 데이터 계약

`data/criteria/README.md`와 `criterion-file.schema.json`·`release-file.schema.json`.
서비스 기준은 아직 0건이다 — 작성 절차를 거친 기준이 없고, 출처가 실제 존재하는 공개
근거만 둘 수 있다. 시험 전용 자료는 `tests/fixtures/`에 `origin=fixture`로 둔다.

## 시험

```sh
cargo test -p onjeon-criteria
```

33건: 필수 `need-criteria-versioned`(정정 사슬·출처 없는 판 거부·기본값 키 거부),
판 규칙, 릴리스 고정·무결성·별도 ID, 변경 목록, 파일 검증(알 수 없는 키·K8·날짜·
출처 문법), 그리고 `infra/db/criteria` SQL·`vocabulary.json`·`data/criteria`와의 대조.
실행 기록은 `evidence/cargo_test.log`.

## 한계

- 저장소는 인메모리 `CriterionStore`다. 파일 로더(`load_dir`·`load_file`)만 있고 DB
  적재·쿼리는 후속 과제다.
- `valid_from`/`valid_to`의 실제 달력 검증은 형식 수준이다. 판 사이의 기간 겹침 규칙은
  없다(계약에도 없다).
- 출처 `ref`의 존재 여부는 확인하지 않는다 — 문법만 검사한다(실재 확인은 R2 관측
  목록·적재기의 몫).
