# Audit 7 결정 ID 구분 검증

기준 HEAD `c777f98`. [결정 원장 §1.2](../../../docs/blueprint/DECISIONS.md#decision-id-namespaces)에 번호 16~18의 R2 확정 방향과 작업 묶음 실행 게이트를 나란히 적고, 각 항목의 ADR·DEC 원문을 연결했다. 원장의 이전 ID는 §1.1로 확인한다.

[DEC-D-04의 현행 결정](../../../docs/decisions/DEC-D-04.md#현행-결정--2026-11-10-재확인)은 R2 토큰 처리에 적용한다. R2 제공자·비용·초기 운영의 참조는 `BP-D-16`·`BP-D-17`·`BP-D-18`이다. BLUEPRINT §0.1, 작업 묶음 README §6, 09 §6에서도 같은 구분표를 찾을 수 있다.

[회귀 시험](../../tests/test_decision_records.py)은 세 번호의 각 주제, ADR·DEC 원문 링크, O 항목, 문서 네 곳에서 표로 가는 링크를 확인한다. 작업 계약의 `decision_index`와 과제별 `decision_gates`도 함께 검사한다.

| 실행 게이트 | 검증한 작업 범위 |
|---|---|
| `D-16` | T-UX-01 시작 |
| `D-17` | T-PS-01·02·03 실데이터, T-OP-07 출시 |
| `D-18` | T-OP-07 출시 |

새 시험을 기준 HEAD 문서로 실행했을 때 표·링크·현행 토큰 적용 범위 누락을 검출했다. 수정 후 문서 집중 회귀 61개가 통과했다. `tasks.json`·`daemon_rules.json`과 09 P01~P19의 행·완료 증거를 기준 HEAD와 대조했다. 첫 출시 완료 판정은 09의 실제 데이터·화면·출시 증거를 따른다.

## 로컬 실행 결과

| 검사 | 결과 |
|---|---|
| `python3 -B -m unittest discover -s tools/tests -v` | 1,751개 실행, 1,745개 통과, 6개 건너뜀 |
| `cargo test --all --locked --offline` | 537개 통과, 1개 무시 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline` | 4개 통과 |
| 온톨로지 실행기 `cargo test --locked --offline` | 4개 통과 |
| `spec_check.py` | 기계 검사 47/47, 존재 검사 72/72 |
| `blueprint_status.py`, `blueprint_counts.py` | ADR·DEC 43개, 등록 수 대조 통과 |
| `ontology_check.py`, `vocab_check.py`, `registry_check.py`, `validation_check.py --selftest` | 통과 |
| `dry_run.py --scenario all --require-all` | 필수 모의 시험 통과 |

Python 시험에는 오프라인으로 빌드한 온톨로지 실행기를 `ONJEON_ONTOLOGY_RUNNER`로 지정했다. 건너뛴 6개는 로컬 원본 보관본이 필요한 시험 5개와 구버전 botocore 호환성 시험 1개다.
