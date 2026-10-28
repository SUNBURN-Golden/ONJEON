# Audit 3: 실제 조항 7개에 대한 I1·I18·콘텐츠 해시 회귀 검사

검증일: 2026-10-28. 노드: `audit3-engine-invariant-tests-strengthen`.
BLUEPRINT A1·A2·A5, Q1·Q2·Q5·Q7, L6, I1·I2·I18 및
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견과 변경

감리 발견은 합성 fixture에 한정된 입력 숨김 검사, 같은 메모리 객체의 반복 평가만
검사하는 재현성 시험, 합성 규칙 하나의 콘텐츠 해시 고정이었다. 이 작업 시작 시점에는
실제 조항 규칙의 `null` 입력 숨김 검사와 7개 해시 파일이 이미 있었다.
기존 검사와 고정값을 보존하고 다음 범위를 보강했다.

- I1: 합성·실제 규칙에 같은 검사기를 적용한다. 확정 결과가 있는 사례에서 알려진
  입력을 하나씩 `null` 또는 키 삭제로 숨긴다. 숨긴 뒤에도 확정 결과가 나오면 원래
  지급 결과와 같아야 한다. 이미 `null`인 입력은 숨김 수에 넣지 않는다.
  모름을 `false`/`0`으로 바꾸는 잘못된 평가기를 같은 검사기가 두 방식 모두에서 잡는다.
- I18: 합성 15사례와 실제 105사례에 반복 평가·파일 재로딩을 적용한다. 매 사례에서
  새 JSON을 파싱하고 새 `Rule`을 로드하며 규칙·입력의 객체 키를 각각 정순/역순으로
  바꾼 4개 조합을 검사한다. 중첩 객체와 배열 내부 객체도 재귀적으로 처리하되 배열
  원소 순서는 보존한다. `Map`에 역순 삽입하면 기본 `BTreeMap`이 다시 정렬하므로
  JSON 원문을 직접 써서 파싱 경계에 다른 키 순서를 전달한다. 원문 바이트가 바뀌고
  파싱 값은 유지되는지도 확인한다(키가 없는 합성 사례는 입력 순서 변경 대상이 없다).
  비교 대상은 지급 결과뿐 아니라 trace·누락 입력·버전·릴리스·근거·두 해시를 포함한
  전체 공개 결과의 직렬화 바이트다.
- 콘텐츠 해시: 기존 `packages/fixtures/rules/real.content_hashes.json`의 7개 고정값과
  로더 해시를 대조하고 실제 105사례의 모든 결과에서 같은 고정값을 확인한다.
  규칙별 첫 사례만 선택하던 선택적 검사를 제거했다. 규칙과 고정값의 키 집합이
  정확히 같아야 하고, 사례 없는 규칙이나 사례 수 누락도 실패한다.
- 세 검사 모두 고정된 7개 규칙 ID 목록과 실제 실행 집합을 대조한다. 규칙 파일과
  고정값을 함께 삭제해 검사 범위가 줄어드는 경우도 거부한다.
  엔진 로직·실제 규칙·해시 고정값은 바꾸지 않았다.

## 실제 실행 범위

[focused.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/focused.log)에 규칙별 실행 수가 출력된다.

| 규칙 | I1 `null`·키 삭제 조합 수 | I18·고정 해시 사례 수 |
|---|---:|---:|
| `kb-driver-fine` | 200 | 12 |
| `kb-driver-lawyer-fee` | 606 | 20 |
| `kyobo-1995-cancer-waiting` | 40 | 5 |
| `kyobo-cancer-main-dx` | 326 | 18 |
| `kyobo-small-cancer-skin` | 320 | 17 |
| `kyobo-wholelife-accident-death` | 198 | 10 |
| `kyobo-wholelife-disease-death` | 488 | 23 |
| 합계 | **2,178** | **105** |

I18은 실제 사례당 키 순서 조합 4개, 총 420개를 추가 비교한다.
입력 숨김은 알려진 입력 하나씩을 숨기는 범위이며 모든 입력 부분집합의 증명은 아니다.

## 직접 실행한 검증

로그 위치: [tools/evidence/audit3-engine-invariant-tests-strengthen](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/).
아래 명령은 모두 종료 코드 0이다. 음성 대조의 내부 Cargo 실패는 기대한 종료 코드
101과 의도한 진단을 확인한 결과다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test golden --test soundness -- --nocapture` | 17개 통과: [focused.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/focused.log) |
| `cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 467개 통과·실패 0·기존 무시 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/workspace.log) |
| `cargo fmt --all -- --check` | 진단 없음: [fmt.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/fmt.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 통과: [clippy.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/clippy.log) |
| `python3 -I tools/evidence/audit3-engine-invariant-tests-strengthen/negative_controls.py` | 원본을 바꾸지 않는 작업 트리 내부 임시 복사본에서 정상 고정값 통과. 각 규칙의 해시 변조 7건·누락 7건 거부. 각 규칙 파일과 고정값을 함께 삭제했을 때 I1·I18·해시 검사 각각 거부(21건): [negative-controls.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/negative-controls.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_counts.py -v` | 17개 통과: [counts-tests.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/counts-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 14개 통과: [purpose-tests.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/purpose-tests.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 `python3 -I tools/blueprint_counts.py` | 엔진 단위·통합 등록 202개·doctest 3개·규칙 7개 일치: [counts.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 등록 정합성 통과: [product-purpose.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/spec-check.log) |
| `python3 -I tools/blueprint_status.py` | 결정 색인·기준일 일치: [status.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/status.log) |

기존 CI의 `cargo test --all`이 새 시험도 실행한다. BLUEPRINT §8의 I1·I18 검사
근거, §11 자동 등록 수, 엔진 README, 09 §7의 P08·P14 연결을 갱신했다.
허용 경로·보호 문서 불변·로컬 링크·공백·기존 고정값 보존은
[scope.log](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/scope.log)에 기록했다.
`git diff --check`도 통과했다.

## 제품 목적과 한계

실제 약관을 옮긴 규칙 7개는 계속 `fixture_only`이며 AI 해석·미검수 설계 검증
자료다. 이 증거는 소비자가 보는 계산의 미확인 전파·재현성·내용 추적을 지키는
엔진 회귀 증거다. 실제 상품 릴리스 정확도·전 상품 수집·소비자 화면·출시 완료나
P08·P14 전체 완료 판정을 대체하지 않는다.
