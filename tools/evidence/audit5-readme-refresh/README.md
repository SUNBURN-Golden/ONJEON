# audit5-readme-refresh 검증 증거

노드: `audit5-readme-refresh`. 기록일: 2026-11-10(UTC).
대상: [루트 README](../../../README.md)의 ADR·DEC 색인과 문서 위계 문구,
[회귀 시험](../../tests/test_readme_index.py),
[감리 기록](../../../docs/blueprint/audits/2026-11-10_readme_refresh.md).

## 감리 지적과 현재 대조

감리 지적은 `README.md:22`가 ADR 0011까지만 나열하고 `:24`가 폐기된
“불변 원칙 → 제2부 → 제3부 → 제1부” 우선순위를 쓴다는 것이다. 작업
시작 시점의 README는 이미 ADR 0001~0019를 모두 나열했고, 우선순위는
[BLUEPRINT §0.1 문서 위계](../../../docs/BLUEPRINT.md#01-문서-위계)
링크로 대체돼 있었다(선행 `audit4-readme-drift`, `1ee1dac`). 따라서
지적된 문구를 다시 추가하거나 삭제하지 않았다.

대신 재발 방지를 강화했다. ADR 번호가 중복·역순 없이 한 번씩 나열되는지
검사하고, DEC 기록 계열(`DEC-D-xx`, `DEC-Oxx`, `DEC-CANON-*`,
`DEC-BUNDLE-STATUS`)을 README 행에서 확인하며 디렉터리의 모든
`DEC-*.md`가 그 계열에 속하는지 대조한다. README의 DEC 안내 문구도
실제 계열 이름을 쓰도록 정확히 했다.

## 실행 명령과 결과

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -I -m unittest discover -s tools/tests -p 'test_readme_index.py' -v` | 13건 통과, 종료 0 | [focused.log](focused.log) |
| `python3 -I tools/evidence/audit5-readme-refresh/readme_mutation.py` | 변이 4종 모두 의도한 시험 실패로 검출, README 파일 불변, 종료 0 | [mutation.log](mutation.log) |
| `python3 -I tools/blueprint_status.py` | ADR·DEC 37개 색인 일치, 종료 0 | [status.log](status.log) |
| `cargo build --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir /tmp/onjeon-onto-audit5-readme` | 온톨로지 실행기 빌드 성공, 종료 0 | [ontology-build.log](ontology-build.log) |
| `ONJEON_ONTOLOGY_RUNNER=/tmp/onjeon-onto-audit5-readme/debug/ontology-case-runner python3 -I -m unittest discover -s tools/tests -v` | 1,468건 통과, 실패·오류 0, 기존 조건부 건너뜀 60건, 종료 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 513건 통과, 실패 0, 기존 무시 1건, 종료 0 | [rust-tests.log](rust-tests.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir /tmp/onjeon-onto-audit5-readme` | 4건 통과, 종료 0 | [ontology-tests.log](ontology-tests.log) |
| 허용 경로·보호 문서·공백 검사 | 허용 경로만 변경, 보호 문서 diff 없음, `git diff --check` 깨끗함 | [scope.log](scope.log) |

Python 전체 시험의 건너뜀 60건은 원본 보관 경로·로컬 보관소·`pdftotext`
등 기존 환경 조건부 건너뜀이며 이번 변경과 무관하다. Rust 수는 무시된
시험을 포함한 등록 수가 아니라 실행 통과 수다.

## 변이 검증

[readme_mutation.py](readme_mutation.py)는 README 파일을 건드리지 않고
모듈 문자열만 바꿔 감리 지적 상태를 재현한다.

| 변이 | 검출 시험 |
|---|---|
| ADR 목록을 0011까지만 남김 | `DecisionsRow.test_every_adr_number_is_listed` |
| DEC 기록 계열 안내를 지움 | `DecisionsRow.test_dec_record_families_are_named_and_cover_every_record` |
| 감사 당시 우선순위 복원 | `DocumentHierarchy`의 두 시험 |
| BLUEPRINT 링크 유지 중에도 옛 우선순위 재삽입 | `DocumentHierarchy.test_replaced_masterplan_priority_is_not_present` |

## 범위

로컬 저장소의 문서·시험·검증 도구만 실행했다. commit·push·GitHub 호출·
비밀값 조회·R2/클라우드/프로덕션 접근은 하지 않았다. 이 증거는 README
색인과 문서 위계의 회귀 검증이며, 실제 공시 데이터·트윈·소비자 화면·
P01~P19 첫 출시 완료 증거나 T-OP-08 출시 판정을 대신하지 않는다.
