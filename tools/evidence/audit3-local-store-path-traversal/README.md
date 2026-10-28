# audit3-local-store-path-traversal 실행 증거

기준 커밋: `0026667dfe971aef4fd8077b4b9489aa79efdb8c` + 이 노드의 변경. [감리 수정 기록](../../../docs/blueprint/audits/2026-10-28_local_store_path_traversal.md).

이 증거는 P02·P03·P14의 원본·출처 관리 도구 보안 회귀 시험이다. 합성 바이트·임시 디렉터리·모의 버킷을 사용하며 09의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.

| 파일 | 실행·결과 |
|---|---|
| [before.log](before.log) | 신규 경로 회귀 13개를 수정 전 코드에서 실행: 종료 1, 하위 사례 실패 29건·오류 9건. 버킷 키의 외부 쓰기, 외부 파일 읽기, 심볼릭 링크, 예측 가능한 임시 파일 문제 등을 재현 |
| [after.log](after.log) | 같은 신규 회귀 13개 통과, 종료 0 |
| [archive-tests.log](archive-tests.log) | `test_source_archive*.py` 65개 통과, 종료 0. 기존 `--extra` 예약 필드·형식 검증·CLI 무변경 거부도 포함 |
| [python-tests.log](python-tests.log) | `python3 -m unittest discover -s tools/tests -v`: 1,254개, 실패·오류 0, 기존 환경 의존 skip 6, 종료 0 |
| [rust-tests.log](rust-tests.log) | `cargo test --all`: 통과, 기존 픽스처 재생성 시험 1개 ignored, 종료 0 |
| [spec-check.log](spec-check.log) | 설계 묶음 기계 검사 45/45·존재 검사 72/72 통과 |
| [vocabulary.log](vocabulary.log), [validation.log](validation.log) | 정본 어휘 49축·270값, 검증 자료 내부 정합성 통과 |
| [blueprint-status.log](blueprint-status.log), [blueprint-counts.log](blueprint-counts.log) | 결정 기록 36개 색인 및 현재 시험·어휘 등록 수 대조 통과 |
| [manifest.json](manifest.json) | 변경 소스·시험·문서·로그의 SHA-256과 실행 결과 |

Python skip 6개는 로컬 원본 보관소 미설정 2개, 로컬 보관소·`pdftotext` 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해 적용되지 않는 구버전 거부 시험 1개다. 신규 회귀 및 아카이브 시험 65개에는 skip이 없다. 위 추가 검사와 `git diff --check`도 종료 0이다.

재현(저장소 루트):

```sh
python3 -m unittest discover -s tools/tests -p test_source_archive_paths.py -v
python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v
python3 -m unittest discover -s tools/tests -v
cargo test --all
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/blueprint_status.py
python3 -I tools/blueprint_counts.py
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
git diff --check
```

`before.log`는 신규 시험 파일을 추가한 뒤 구현을 고치기 전에 실행했다. 기준 구현에 `UnsafeStoreKey`가 없으므로 예외 클래스의 이름에 의존하지 않고 `ValueError`와 외부 파일의 실제 바이트·생성 여부를 검사한다. 수정 뒤 CLI 오류 코드·메시지·예산 정산도 검사한다. 루트 밖 쓰기가 거부될 때 원본 센티널의 바이트와 로컬 저장소가 유지되는 것을 확인한다.

로컬 루트의 악의적인 동시 교체를 격리하는 샌드박스 시험은 아니다. 실제 클라우드·비밀키·원문 공시 데이터·GitHub는 사용하지 않았다. 커밋·푸시·배포하지 않았다.
