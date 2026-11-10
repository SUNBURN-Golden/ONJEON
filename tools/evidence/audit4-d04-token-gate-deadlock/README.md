# D-04 게이트 정합성 검증 (2026-11-10)

[소유자 위험 수용 기록](../../../docs/blueprint/audits/2026-11-10_d04_token_risk_acceptance.md)의 로컬 검증 증거.
실제 R2·Cloudflare·자격 증명은 사용하지 않았다. commit·push·GitHub 호출도 수행하지 않았다.
문서·작업 게이트 정합성에 대한 증거이며 실제 수집·S1 관통·09 제품 출시 완료 증거가 아니다.

| 실행 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_o13_ruling.py -v` | 11개 통과 | [O13](o13-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target/d04-tests" CARGO_NET_OFFLINE=true python3 -m unittest discover -s tools/tests -v` | 1,372개 실행, 실패·오류 0, skip 6 | [Python 전체](python-final-tests.log) |
| `cargo test --all --locked --offline` | 500개 통과, ignored 1, 실패 0 | [Rust 전체](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 | [온톨로지 실행기](ontology-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 45/45·존재 72/72 | [명세](spec-tests.log) |
| `python3 -I tools/blueprint_status.py --write` | DEC 변경 반영, 37개 ADR/DEC 색인 정합 | [색인](blueprint-status.log) |
| `python3 -I tools/vocab_check.py` | 49축·270값 통과 | [어휘](vocabulary.log) |
| `python3 -I tools/validation_check.py` / `--selftest` | 표본 정합·40개 변조 검사 통과 | [표본](validation.log), [변조](validation-selftest.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all` | 필수 모의 시나리오 전부 통과 | [모의 보고서](../../daemon/reports/dry_run.log) |
| `python3 -m unittest tools.tests.test_daemon_dry_run -v` | 289개 통과, 소스 해시 갱신 | [데몬 회귀](../../daemon/reports/unittest.log) |
| `python3 -I tools/ci/check_leak.py` | 누출 패턴 없음 | [누출](leak.log) |
| HEAD와 변경 경로·보호 파일·모든 작업 게이트 직접 대조 | 허용 경로만 변경, 보호 파일 동일, D-04 이외의 게이트 동일 | [범위·소스 해시](scope-check.log) |

첫 전체 실행은 예전 D-04 차단을 기대하던 검사 6개와 문서 행 이름 검사 1개에서 실패했다
([초기 결과](python-tests.log)). 최신 소유자 결정에 맞게 해당 검사를 갱신하고 DEC 변경 후 설계도 색인을 재생성했다.
관련 [결정 기록](decision-record-tests.log), [설계도 색인](blueprint-status-tests.log),
[시작 게이트](start-gate-tests.log), [O19 분모 게이트](registry-gate-tests.log),
[보관소 문서](storage-doc-tests.log) 테스트는 모두 통과했다.
그 다음 전체 실행은 데몬 증거 로그의 소스 해시 불일치 1건만 남았다
([증거 갱신 전](python-before-evidence-tests.log)). `tools/daemon/README.md`의 증거 기록 규칙에 따라
두 보고서를 재생성했고 데몬 테스트 289개가 통과했다.

O13 시험은 실제 tasks.json의 게이트를 모의 데몬에 복사해 D-04 등록 없이 T-OP-04 시작·T-DT-01 실데이터 허용,
T-OP-02의 D-02·T-DT-04의 O19 잔여 차단을 확인한다.
[변경 전 기준](../../tests/fixtures/o13_unchanged_gates.json)은 D-04 이외 모든 작업 게이트와 결정 색인,
O14·O17·O19 원장 행 및 D-02·O14·O17 결정·ADR-0017·비용 정책·데몬 규칙의 SHA-256을 보존한다.
O17의 대량 자동 수집 선행 조건과 실제 R2 검증은 이번 작업에서 완료 처리하지 않았다.

최종 전체 실행은 1,372개, 실패·오류 0, skip 6으로 통과했다. skip은 보관 원본 부재 5개와 구버전 botocore 거부 시험 1개다.
`git diff --check`도 통과했다.
