# Audit 7 소스 워크플로 자격 증명과 예산 중단

작업 `audit7-sources-yml-secret-scope` · BLUEPRINT L1·L2 · 09 P03.

## 변경

작업 시작 기준본 `75ee8df`에는 R2 endpoint, 검증 키 쌍과 쓰기 가능한 원장 키 쌍이 이미 두 보관소 도구 단계의 `env`에 있었다. 작업 수준의 `env`에는 작업 명세 경로와 버킷 이름만 있다. 기존 시험으로 다섯 비밀 참조를 작업 수준으로 옮기거나 설치, checkout, 보고서 단계 등 8개 비소비 단계에 하나씩 추가한 변이를 다시 확인했다.

두 checkout에 `persist-credentials: false`를 설정했다. detect와 reproduce는 각각의 잠금 파일로 `pip install --require-hashes --only-binary=:all:`을 실행한다. reproduce는 detect의 PDF 의존성 잠금을 재사용하고 보관소 클라이언트 의존성을 추가한다. Linux x86_64의 CPython 3.12~3.14에 맞는 wheel 21개와 직접·전이 의존성 15개를 고정했다. 해시는 다운로드한 wheel 바이트와 PyPI 릴리스 메타데이터를 대조했다.

목록 검사 단계는 `shell: bash`에서 실패 즉시 종료한다. 원본 또는 파생 목록 검사에서 종료 코드 4가 반환되면 단계가 실패하고, 기본 성공 조건을 쓰는 재현 단계는 건너뛴다. `always()`는 두 artifact 업로드에만 있으며 목록 검사에서 생성된 JSON도 업로드 대상에 포함된다. detect 결과 요약은 `!cancelled()`로 성공과 실패 시 표시하고 취소 시 건너뛴다.

## 로컬 검증

- 새 회귀 시험을 기준본에 적용하면 재현 단계의 `always()`, 두 pip 명령의 해시 검사 누락, 두 checkout의 자격 증명 기본값을 검출한다. 수정본에서는 재현 단계의 실패 후 실행 조건, 목록 검사의 실패 무시, checkout별 설정 제거와 `true` 변이를 거부한다. 실제 목록 검사 Bash 본문에서 첫 번째 또는 두 번째 호출에 4를 반환시켜 이후 호출 중단과 이미 작성된 보고서 보존을 확인했다.
- CPython 3.12와 3.13에서 두 `Extractors` 스크립트의 실제 pip 명령을 로컬 wheel 디렉터리로 실행했다. 네 가상환경의 `pip check` 및 `python -I` import가 통과했다. CPython 3.14 대상은 pip의 `--python-version 3.14`로 두 잠금 파일의 wheel 선택과 해시를 검증했다. PDF wheel에 바이트를 덧붙이면 두 잠금 파일 모두 해시 불일치로 거부했다. 이 시험에서 apt 명령은 로컬 스텁으로 대체했다. 3.12에서 재현 잠금 파일의 PyPI 다운로드도 해시 검사와 함께 통과했다.
- 재현 잠금 파일로 구성한 CPython 3.13 환경에서 `python -m unittest tools.tests.test_r2_budget tools.tests.test_source_archive tools.tests.test_verify_sources -v`를 실행했다. 148개 중 145개 통과, 기존 건너뜀 3개였다.
- `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v`에서 43개 통과. `python3 -m unittest discover -s tools/ci/tests -v`에서 21개 통과. `tools/workflow_check.py`로 `ci.yml`, `pr-traceability.yml`, `sources.yml`을 검사했고 의존성·검증 자료·제품 목적 연결·추적 자격 증명 검사도 통과했다.
- `python3 -m unittest discover -s tools/tests -v` 재실행은 1,732개 중 1,726개 통과, 기존 건너뜀 6개였다. 처음에 작업 트리 안으로 `TMPDIR`를 지정해 온톨로지 격리 시험 3개가 실패했다. 기본 OS 임시 경로로 복원한 뒤 전체 시험을 다시 실행했다.
- `cargo test --all --locked --offline`에서 537개 통과, 1개 기존 무시. README의 별도 Cargo 시험에서 scenario API와 온톨로지 실행기 각각 4개 통과. `cargo fmt --all -- --check`와 `cargo clippy --locked --offline --all-targets -- -D warnings`도 통과했다.

GitHub 실행과 R2 접근은 미실행이다. 이 기록이 다루는 P03 증거의 범위는 워크플로 회귀 시험까지다.
