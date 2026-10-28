# Audit 3: README 결정·저장소 인덱스

검증일: 2026-10-29. 기준 커밋: `0d06ba2801c084e0d9ed0a6c881377dbe2fc9906` + 이 노드의 미커밋 변경.

## 수정 범위와 근거

- 작업 시작 시 README의 ADR 0001~0018 목록과 `DEC-*.md` 안내는 이미 존재했다. 기존 시험이 실제 ADR 파일 번호와 목록을 계속 대조한다.
- `data/registry/`, `infra/r2/`, `infra/s3/`, `tools/daemon/`를 안내 표에 추가하고 각 디렉터리 README를 연결했다. 기관 근거 목록과 상품·특약·판매본 분모 완성을 구분한다.
- ADR-0016에 따라 현재 원본·파생 보관소를 R2로 표시했다. `infra/s3/*.cfn.yaml`은 기존 [인프라 안내](../../../infra/README.md)와 [S3 안내](../../../infra/s3/README.md)의 보존 방침에 따라 AWS 대안으로 남긴다. README에도 미사용·미배포라고 표시해 현재 배포 설정으로 오해하지 않게 했다. 인프라 배포·삭제는 하지 않았다.
- 첫 소개의 “앱·크롤러·API는 아직 없다”를 실제 부분 구현·픽스처 검증 범위로 고쳤다. 내부 전용 지식 기반과 대상 범위는 [ADR-0018](../../../docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md), 현황은 BLUEPRINT §11, 출시 완료 판정은 [09_제품목적_대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 완료 증거로 연결한다.
- 데몬은 개발 도구이며 모의·실행기 시험은 상주 가동 승인이나 출시 완료 증거가 아님을 명시했다. 이 수정과 아래 시험도 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.

## 회귀와 실행 증거

[회귀 시험](../../tests/test_readme_index.py)은 ADR 번호·DEC 안내·색인 경로의 존재 외에 신규 경로 필수 등록, 기관 목록의 한계, R2/S3의 현행·대안 구분, 데몬 검증의 한계, 정체성·출시 완료 기준 연결을 검사한다. 기존 CI의 `python3 -m unittest discover -s tools/tests -v`가 자동 발견한다.

| 증거 | 명령·결과 |
|---|---|
| [수정 전](before-tests.log) | 신규 회귀를 README 수정 전에 실행: 9개 시험, 하위 사례 포함 실패 8건, 종료 1. ADR·DEC 및 기존 문서 색인 검사는 통과 |
| [README 회귀](readme-tests.log) | `python3 -m unittest tools.tests.test_readme_index -v`: 9개 모두 통과, 종료 0 |
| [Python 전체](python-tests.log) | `CARGO_TARGET_DIR="$PWD/target/ontology" python3 -m unittest discover -s tools/tests -v`: 1,277개 실행, 실패·오류 0, skip 6, 종료 0 |
| [Rust 전체](rust-tests.log) | `CARGO_TARGET_DIR="$PWD/target" cargo test --all`: 문서 시험 포함 472개 통과, 실패 0, ignored 1, 종료 0 |
| [어휘](vocabulary.log) | `python3 tools/vocab_check.py`: 49축·270값 통과, 종료 0 |
| [검증 자료](validation.log) | `python3 tools/validation_check.py`: 표본 14건 내부 일관성 통과, 종료 0. 원본 재다운로드 검사는 아님 |
| [변조 자체 시험](validation-selftest.log) | `python3 tools/validation_check.py --selftest`: 38종 모두 의도한 이유로 검출, 종료 0 |
| [결정 색인](blueprint-status.log) | `python3 -I tools/blueprint_status.py`: ADR/DEC 36개 정합, 종료 0 |
| [등록 수](blueprint-counts.log) | `CARGO_TARGET_DIR="$PWD/target" python3 -I tools/blueprint_counts.py`: 엔진 시험 207·doctest 3·실제 조항 규칙 7·변조 시험 38·어휘 49축 일치, 종료 0 |
| [설계 명세](spec-check.log) | `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py`: 기계 45/45·존재 72/72 통과, 종료 0 |

Python의 skip 6개는 원본 보관 경로 환경 미설정 2개, 로컬 보관소·pdftotext를 요구하는 재현 시험 3개, 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다. README 회귀에는 skip이 없다. Rust의 ignored 1개는 기존 `regenerate_declared_abox_fixture` 재생성 시험이다.

소스 변경은 README와 인덱스 시험뿐이며 보호 문서·데이터·인프라 정의는 변경하지 않았다. `git diff --check`와 증거 문서의 로컬 링크 검사도 통과했다. 커밋·푸시·GitHub 호출은 하지 않았다.
