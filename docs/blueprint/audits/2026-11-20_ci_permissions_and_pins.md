# Audit 7 — 워크플로 권한과 액션 SHA

`audit7-ci-permissions-and-pins`의 기준 커밋은 `558483250241`이다.
지정된 세 로컬 브랜치의 끝 커밋은 모두 기준의 조상이며, 병합할 고유 커밋은 0개다.

| 로컬 브랜치 접미사 | 끝 커밋 | 기준에서 확인한 동작 |
|---|---|---|
| `audit1-ci-permissions-and-persist-credentials` | `d1db00a` | `b7e20f9`로 병합. CI 최상위 `contents: read`, 두 checkout의 자격 증명 비보존 |
| `audit1-workflows-pin-actions-by-sha` | `9d1f0ec` | `8d6db86`으로 병합. CI·출처 검증·PR 추적의 액션 참조 7개가 40자리 SHA |
| `audit1-sources-yml-vars-via-env` | `20b4f1c` | 브랜치 끝은 이미 포함. 버킷 변수의 작업 `env` 바인딩과 인자 인용은 Audit 6 병합 `e2ef66d`에 포함 |

CI의 초기 검사에 `sources.yml`을 추가했고, 출처 검증 작업 두 곳에서 checkout의
`persist-credentials: false`를 지정했다. 검사기는 저장소의 블록형 YAML에 대해
최상위와 작업 범위에 명시된 읽기 권한, 그리고 각 checkout의 `with` 입력을 검사한다.

CI가 선언한 셸 명령을 임시 워크플로 복사본에서 실행했다. 이전 검사에서는 작업별
권한 확대 6건, 중복 최상위 권한 선언 1건, checkout 자격 증명 보존을 같은 단계의
`env`로 가린 변이 1건이 통과했다. 출처 검증의 두 checkout에는 비보존 입력이 없었다.
현재 검사는 이 변이와 최상위 권한 삭제·확대, checkout 입력 누락·보존 활성화,
7개 액션을 각각 태그·브랜치·짧은 SHA로 바꾼 21건을 거부한다. 버킷 변수 시험은
합성 문자열을 사용해 두 OCR 설정에서 Bash가 원래 값을 단일 인자로 전달하는지 검사한다.
[CI 워크플로 회귀](../../../tools/tests/test_ci_workflow_security.py) ·
[버킷 변수 회귀](../../../tools/tests/test_workflow_source_variables.py).

## 로컬 실행

```sh
python3 tools/workflow_check.py .github/workflows/ci.yml .github/workflows/sources.yml .github/workflows/pr-traceability.yml
python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v
python3 -m unittest discover -s tools/tests -p test_ci_workflow_security.py -v
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api
cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline
python3 -I tools/ci/check_product_purpose.py
```

세 워크플로의 권한 검사, 워크플로 회귀 시험 40개, 실제 CI 검사 명령 시험 7개,
Rust 워크스페이스 시험 537개(기존 ignored 1개), 시나리오 API 4개와 온톨로지
실행기 4개가 통과했다. 전체 Python 시험은 기본 OS 임시 디렉터리에서 1,731개를
실행해 실패 없이 끝났다(기존 건너뜀 6개). 임시 디렉터리를 작업 트리 안으로
지정한 실행에서는 트리 밖 파일 생성을 확인하는 온톨로지 시험 3개가 실패했다.
Rust 형식·Clippy 검사와 09 행의 작업·시험 ID 정적 대응 검사도 통과했다.

로컬 파일과 합성 입력으로 검증했다. GitHub Actions 실행, 원격 액션의 태그 대조와
실제 R2 재현은 이 기록의 검증 범위 밖이다. 개발 도구 증거의 위치는
[09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)다.
