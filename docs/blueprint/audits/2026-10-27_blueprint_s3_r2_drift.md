# Audit 2: 원본 보관소 S3/R2 결정 드리프트 정정

검증일: 2026-10-27. 노드: `audit2-blueprint-s3-r2-drift`.
연결: A1·A2·A4, L1·L2, I6, V1, 제품 목적 대응표 P02·P03의 근거 관리.

## 확인과 수정

작업 시작 시 `BLUEPRINT.md` §9.2 V1 행과 `validation/GAP_REPORT.md`의 원본 보관소 설명은 이미 ADR-0016의 R2 결정과 2026-10-09 보존·다운로드 대조 기록을 반영하고 있었다. 해당 설명은 유지하고 기존 회귀 시험으로 다시 대조했다.

- §7.2에 원본·파생 보관소의 현행 결정을 등록했다. Cloudflare R2 비공개 버킷, 원본·파생 분리, ADR-0017 비용 제한과 §12 운영 관문을 연결한다.
- §7.3에 ADR-0015의 AWS S3·서울 리전·S3 고유 설정이 ADR-0016으로 대체됐음을 기록했다. 나머지 보존 규칙은 유지한다. ADR 원문은 변경하지 않았다.
- §12의 포괄적인 “클라우드·저장소” 미정 행을 “서비스 실행 클라우드”로 좁혔다. 원본·파생 보관소는 R2로 확정됐음을 같은 행에 명시하고 M3·로컬 Compose 안내를 유지했다. R2 접근(D-04), 버킷 잠금(O14), 대량 자동 수집(O17) 관문은 계속 적용된다.

## 근거와 한계

기존 `validation/source_checks/2026-10-09_r2_*.json`을 대조했다. 원본 58/58키·파생 v2 61/61키의 다운로드 해시가 일치하고, 표본 14/14건의 원본 해시·인용 위치가 맞다. 파생 결과까지 완전히 재현한 것은 8/14건이고, 나머지 6건은 재생성 도구가 없어 미검증이다. 회귀 시험은 각 결과의 해시·상태와 문서 수치를 함께 확인한다.

이는 2026-10-09의 고정 기록에 대한 로컬 검증이다. 이번 작업에서 R2 접속·업로드·원본 재다운로드를 실행하지 않았다. V1 관문은 미통과이며, 파생 6건 재현·다른 계열 AI 검수·화면 열린 항목(S1·S6)은 남아 있다. 이 문서는 P02·P03의 실제 문서 확보·변경 전파 또는 P01~P19·T-OP-08의 제품 출시 완료 증거를 대신하지 않는다.

## 검증

실행 로그: [tools/evidence/audit2-blueprint-s3-r2-drift/](../../../tools/evidence/audit2-blueprint-s3-r2-drift/).

`tools/tests/test_storage_provider_docs.py`에 네 검사를 추가했다. §7.2 현행 결정, §7.3 대체 이력, §12 확정/미정 구분, R2 운영 관문 유지를 검사한다. 문서 수정 전 새 결정 검사 3개가 실패했고 운영 관문 검사는 통과했다([수정 전 로그](../../../tools/evidence/audit2-blueprint-s3-r2-drift/storage-docs-before.log)). 수정 후에는 기존 검사와 합쳐 14개 모두 통과했다([수정 후 로그](../../../tools/evidence/audit2-blueprint-s3-r2-drift/storage-docs-after.log)). 기존 Python 전체 시험 CI가 이 파일을 자동 발견하므로 워크플로 수정은 필요 없다.

첫 Python 전체 실행은 환경의 공유 `CARGO_TARGET_DIR` 때문에 온톨로지 실행기 경로를 찾지 못한 오류 2건으로 실패했다([초기 로그](../../../tools/evidence/audit2-blueprint-s3-r2-drift/python-tests-initial.log)). 기존 시험은 `runner/target/debug/ontology-case-runner`를 기대하므로 `env -u CARGO_TARGET_DIR`로 빌드 출력 환경을 복원해 재실행했다. 온톨로지 명세 검사는 아래 표의 명시적 `--target-dir` 빌드 결과를 사용한다.

| 명령 | 결과 |
|---|---|
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,120개 실행: 통과 1,114·건너뜀 6·실패/오류 0 |
| `cargo test --all` | Rust 447개 통과, 실패 0, 무시 1(문서 시험 포함) |
| `python3 tools/vocab_check.py` | 통과 |
| `python3 tools/validation_check.py` | 내부 일관성 통과 |
| `python3 tools/validation_check.py --selftest` | 변조 38종 검출 |
| `python3 -I tools/blueprint_status.py` | 결정 색인·내용 해시 일치 |
| `python3 -I tools/blueprint_counts.py` | 현재 등록 수 일치 |
| `cargo fmt --all -- --check` | 통과 |
| `cargo clippy --all-targets -- -D warnings` | 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 44/44·존재 72/72 통과 |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/audit2-ontology` 후 `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit2-ontology/debug/ontology-case-runner` | 질문 11/11·제약 자체 시험 15/15·릴리스/문서 모델 25/25 통과 |
