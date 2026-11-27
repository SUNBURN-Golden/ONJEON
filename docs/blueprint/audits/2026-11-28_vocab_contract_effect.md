# Audit 8 계약 효과 어휘 검증

`audit8-vocab-contract-effect`의 대상은 rule-0.2의 계약 효과 선언값과 엔진 결과의 계약 효과 판정이다. 어휘 1.10.0의 `contract_effect`는 `none`·`void_refund_premium`·`terminated_pay_reserve`를, `contract_effect_kind`는 `none`·`applies`·`undetermined`를 정의한다. 공유 JSON Schema와 생성된 Rust·TypeScript·Dart 계약은 세 필드를 이 두 축으로 제한한다. 기존 엔진 결과의 문자열과 필드 구조는 이어지며, 과거 결과에서 `contract_effect`를 생략하는 것도 지원한다.

## 회귀 증거

| 확인 | 명령과 결과 |
|---|---|
| 엔진 허용값과 결과 태그 | `cargo test -p onjeon-rules-engine --locked --offline --test vocabulary contract_effect`의 두 시험이 변경 전에는 각각 축 누락으로 실패했다. 변경 후에는 두 축이 로더 허용값 및 실제 평가 결과의 직렬화와 정확히 일치해 통과했다. |
| 엔진과 공유 계약 왕복 | `cargo test -p onjeon-contracts --locked --offline contract_effect`가 효과 선언 3종과 적격 판정 3종의 9개 조합을 실제로 평가해 통과했다. `kind`·`effect`·`conditional_effect`에 정의되지 않은 코드를 각각 넣으면 역직렬화가 실패했다. |
| 스키마와 이전 결과 | `python3 -I -m unittest discover -s packages/schemas/codegen/tests -p test_schemas.py -k contract_effect -v`의 두 시험이 통과했다. 스키마는 세 필드 모두에서 미등록 코드를 거부하고, 과거 평가 결과에서 `contract_effect`의 생략을 허용한다. Rust 왕복 시험도 이 생략을 확인했다. |
| 3개 언어 | `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh`가 Rust 빌드, TypeScript 5.9.3 타입 검사, Dart 3.13.5 분석·픽스처 왕복을 통과했다. TypeScript와 Dart에서 미등록 코드 3건을 각각 거부했다. |
| 정본과 생성물 | `tools/vocab_check.py`(52축, 277값), `packages/schemas/codegen/gen.sh --check`(생성물 30개), `tools/blueprint_counts.py` 통과. |
| Rust 전체 | `ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline`에서 563개 통과, 픽스처 재생성용 1개 기본 제외. 내장 Python 시험은 API 39개·계약 144개 통과. `order-tests` 2개, 시나리오 API 4개, 온톨로지 실행기 4개, 서식 검사·Clippy도 통과했다. |
| Python 도구 | `python3 -m unittest discover -s tools/tests -v`의 1,812개 중 1,803개가 통과했고 원본 보관소·구형 botocore가 필요한 6개는 건너뛰었다. 3개 실패는 `TMPDIR`이 시험 대상 저장소 내부에 있었기 때문이다. 작업 트리 내부의 별도 소스 복사본과 그 바깥 임시 디렉터리에서 `test_ontology_check_tempfile.py` 6개를 재실행해 모두 통과했다. |
| 데몬 검증 | `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v`의 81개 중 78개가 통과했다. R12의 HTTP 재시도와 R13의 첫 heartbeat에서 시간 초과가 발생했고, 시나리오 집계 시험도 실패했다. `runner_verify/run.sh --remote local --no-cli --scenario R12,R13`로 재실행해 두 시나리오의 검사 30건 및 정적·로그 검사를 모두 통과했다. |
| 설계 검증 | `tools/validation_check.py` 일반 실행과 변이 자체 시험, 설계 묶음 `spec_check.py`, 온톨로지 `ontology_check.py`의 제약·릴리스·금액 시험이 통과했다. |

## 최초 변경의 계약 호환

변경 전 HEAD의 `packages/schemas`와 `codegen/compat.py`로 직접 대조했다. 세 필드가 문자열에서 생성 enum으로 바뀌면서 타입 변경 세 건을 비호환으로 분류했다. 기존 엔진 JSON의 유효한 값은 그대로 왕복한다. 어휘는 1.10.0으로 올렸다. 당시 계약 패키지 판과 Rust 크레이트 판이 같았으므로 같은 방식으로 계약 판을 올리려면 루트 `Cargo.lock`을 갱신해야 했다.

`ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest`는 이전 `contracts-*` 태그가 없어 자체 시험으로 실행했고 통과했다. 전체 Rust 시험에 포함된 세 언어의 합성 태그 탐침도 통과했다.

이 증거의 범위는 [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08의 트윈 평가 결과 계약이다. P08 완료에는 실제 릴리스의 경계일 시나리오, 모바일 E2E 및 Q1~Q10 골든 증거가 필요하다.

## 수정 1차 병합 재검증

`main` 병합 충돌은 [설계도 §11](../../BLUEPRINT.md#11-현재-위치)의 자동 생성 시험 수에서 발생했다. `python3 -I tools/blueprint_counts.py --write`로 두 브랜치가 합쳐진 트리의 표를 다시 만들었다. 계약 효과 어휘 회귀와 `main`의 로더·날짜 회귀를 포함해 엔진 단위·통합 시험 279개와 doctest 3개가 등록됐다. 어휘 52축·277값과 생성물 30개의 일치도 확인했다.

병합 트리에서 Rust·TypeScript·Dart 계약 빌드, 서식 검사와 Clippy, 별도 Cargo 매니페스트의 키 순서 보존·시나리오 API·온톨로지 시험(각각 2개·4개·4개)이 통과했다. 이전 `contracts-*` 태그가 없어 `check_compat.sh --latest`는 필드 삭제 검출 자체 시험을 실행해 통과했다.

작업 트리의 `target/`을 지정해 `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline`을 실행했다. Rust 시험 567개가 통과했고 픽스처 재생성 시험 1개는 기본 설정에 따라 제외됐다. 내장 Python 시험은 API 39개와 계약 144개가 통과했다. 계약 효과 정본 일치·직렬화 왕복·미등록 코드 거부 시험과 로더 경계 시험도 통과했다.

Python 도구 시험은 총 1,812개 중 1,806개가 통과했고 기존 건너뜀 6개가 있었다. 이 중 온톨로지 임시 파일 격리 시험 6개는 작업 트리 내부의 소스 복사본을 대상으로 실행했다. 임시 파일은 그 복사본의 바깥이면서 작업 트리 안에 두었다. 설계도 수치·결정 색인, 제품 목적, 레지스트리, 설계 묶음, 온톨로지와 검증 자료 검사도 통과했다.

`runner_verify` 첫 실행에서 R3 작업 인계의 `drain`이 시간 초과되어 해당 시험과 시나리오 집계 시험이 실패했다. 로컬 원격을 사용한 R3 단독 실행의 검사 12건이 모두 통과했고, `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` 전체 재실행도 81개 모두 통과했다.

## 수정 3차 검증

`terminated_pay_reserve`는 보험기간 중 피보험자가 사망하면 보험회사가 사망 당시의 계약자적립액을 지급하고 계약이 소멸하는 효과다. 정본을 고치고 어휘 문서와 Rust·TypeScript·Dart 계약을 재생성했다. [G23](../validation/GAP_REPORT.md#3-부족분-등록부) · [교보 암 주계약 별표1 주2](../validation/extracts/kyobo_cancer_terms.md#주계약-별표1-보험금-지급기준표1년-이상미만-금액)

PR 기준 커밋 `d54a2826`의 `packages/schemas`를 `git archive`로 추출해 `codegen/compat.py --prev`로 비교했다. `kind`·`effect`·`conditional_effect`의 세 타입 변경이 비호환으로, 두 어휘 축 추가가 호환 변경으로 분류됐다. 계약 패키지 0.2.0은 0.x의 minor 상향 규칙을 충족해 비교가 종료 코드 0으로 끝났다. 등록 전 문자열 스키마를 복원하는 회귀 시험과 G23 정의를 검사하는 회귀 시험은 각각 수정 전 실패, 수정 후 통과했다.

계약 패키지 판에 맞춰 오류·이벤트 카탈로그 세 곳과 시나리오 API 잠금 파일을 갱신했다. 루트 `Cargo.lock`은 노드의 허용 경로 밖에 있다. 작업 트리 안의 검증용 소스 복사본에서 Cargo로 `onjeon-contracts` 항목 한 줄을 갱신했다. 작업 트리 루트의 `cargo metadata --locked --offline`은 이 잠금 파일 변경이 필요함을 확인했다.

검증용 복사본에서 `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline`은 Rust 시험 567개와 내장 Python 계약 시험 146개·API 시험 39개를 통과했다. Rust 픽스처 재생성 시험 1개는 기본 설정에 따라 제외됐다. Rust·TypeScript·Dart 빌드, 서식 검사, Clippy와 설계도 수치 검사도 통과했다. 별도 잠금 파일을 쓰는 키 순서 보존·시나리오 API·온톨로지 실행기 시험은 각각 2개·4개·4개 통과했다.

정본 검사에서 기준 어휘 대비 2축·6값이 추가됐고 생성물 30개가 최신임을 확인했다. 이전 계약 태그가 없는 체크아웃에서 `check_compat.sh --latest`는 필드 삭제 자체 시험을 통과했다. 데몬 검증 시험 81개와 설계 묶음·온톨로지·레지스트리·검증 자료 검사도 통과했다.

작업 트리의 Python 계약 시험 146개가 세 언어 탐침을 켠 상태에서 통과했다. 검증용 소스 복사본에서 Python 도구 시험은 1,812개 중 1,806개가 통과했고 6개는 건너뛰었다.

## 수정 4차 검증

`packages/schemas/Cargo.toml`의 `[package.metadata.onjeon-contracts]`에 공유 계약 판 0.2.0을 기록했다. Rust 상수와 TypeScript·Dart 패키지 판은 이 값을 사용해 생성하며 오류·이벤트 카탈로그도 같은 판을 검사한다. 비공개 Rust 크레이트 판은 0.1.0이다. 루트와 시나리오 API의 `Cargo.lock`을 기준 커밋과 대조해 변경이 없음을 확인했다.

`d54a2826`의 스키마와 직접 대조한 호환 검사에서 타입 변경 3건과 어휘 축 추가 2건을 검출했고 0.1.0 → 0.2.0 상향으로 검사를 통과했다. 합성 태그 시험은 과거 매니페스트의 `[package].version`과 새 메타데이터를 모두 검증했다. 메타데이터가 있는 태그의 버전을 그대로 둔 채 스키마를 바꾸면 호환 검사가 실패했다. 실제 이전 `contracts-*` 태그가 없는 체크아웃의 `--latest`에서는 필드 삭제 자체 시험이 통과했다.

실제 작업 트리에서 `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline`이 Rust 시험 567개와 내장 Python 계약 시험 148개·API 시험 39개를 통과했다. Rust 픽스처 재생성 시험 1개는 기본 설정에 따라 제외됐다. Rust·TypeScript·Dart 빌드, 서식 검사·Clippy, 키 순서 보존·시나리오 API·온톨로지 실행기 시험도 통과했다. 어휘 52축·277값과 최신 생성물 30개를 확인했으며 설계도 수치, 검증 자료, 온톨로지, 설계 묶음, 데몬 검증 시험 81개가 통과했다.

Python 도구 시험은 총 1,812개 중 1,806개가 통과했고 기존 건너뜀 6개가 있었다. 전체를 `target/` 아래 복사본에서 실행했을 때 설계 검사 세 건은 경로 규칙에 따라 크레이트 검색에서 제외됐다. 설계 검사를 포함한 나머지 시험을 실제 작업 트리에서 실행하고, 소스 외부의 임시 디렉터리가 필요한 온톨로지 시험 6개를 복사본에서 실행해 재검증했다.
