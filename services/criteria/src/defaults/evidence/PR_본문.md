## 목적과 설계 연결

- 과제 ID: T-KN-13, knowledge/S4, need-criteria, fix round 2.
- A5·A6, Q5·Q6, L1·L5, I6, M5: 참고 통계 후보의 출처 보존·판·적용 대상·갱신 주기를 검증한다.
- 요구 ID: R04(원문 보존), R08(근거 없는 결과 차단), R17(근거 추적). 이번 수정은 후보 납품 검증 범위이며 실제 상품·사용자 결과 검증은 아니다.
- 관련 결정: DEC-D-08·O05. 기존 설계 구현이고 기본값 적용 승인은 활성화하지 않는다.
- 소비자 질문: 기본값의 공공 통계 출처와 적용 대상·갱신 시점은 무엇인가.

## 작성·대상·독립 리뷰

- 작성 참여 모델 역할·실행 경로: 빌더 역할의 코딩 에이전트 CLI, `/workspace/onjeon-run/wt/T-KN-13`. 하위 에이전트 사용 없음. 모델 식별자 원문은 기록하지 않는다.
- 시작·현재 HEAD SHA: `38291e75914302affd962a41be744f0bfba28d15`.
- 시험 대상은 위 SHA에 이번 미커밋 변경을 더한 작업 파일이다. 컴파일·시험 입력을 `test_inputs.sha256`으로 고정했다.
- 전달받은 독립 리뷰 `st_re_review`는 위 HEAD에 고정된 BLOCK이다. 이번 미커밋 변경의 독립 승인 기록은 없으며, 최종 커밋 SHA 고정과 작성 계열이 다른 리뷰는 감독 단계에서 필요하다. 기존 리뷰를 새 변경의 승인으로 재사용하지 않는다.
- 커밋·푸시·GitHub 호출 없음. 비밀값·모델 식별자 원문·원문 발췌 없음.

## 변경 내용

- 후보 납품 시험은 출처 참조와 실제 보존 응답의 SHA-256·바이트 수 일치를 요구한다. 수신 기록에는 기관·통계표·기준연도·HTTPS URL·관측 시각·응답 상태·형식이 필요하다.
- 변조된 바이트·빈 응답·허구 해시를 거부하는 fixture_only 회귀 시험을 추가했다.
- 별도 제품 API 시험은 실제 납품 판의 적재·비노출·참고 통계 라벨·사용자 가정 우선도 검사한다. 모듈 미연결은 여전히 컴파일 실패로 드러난다.
- `product-integration.patch`에 제품 모듈 선언과 충돌 conformance 단정의 교체안을 준비했다. `git apply --check`는 통과했다. 허용 경로 밖의 실제 파일에는 적용하지 않았다.
- 실제 통계 판은 여전히 0건이다. 공식 URL 원본 직접 수신은 TLS 오류로 실패했다(`source_acquisition.log`). 웹으로 조회한 표를 재구성해 RawAsset으로 기록하지 않았다.
- 제품 코드·화면·기존 결과·캐시·개인정보에는 이번 변경이 연결되지 않는다.

## 검증과 한계

| 명령 | 실제 결과 |
|---|---|
| `cargo test -p onjeon-criteria defaults` | 종료 0, 실행 시험 0개. 수락 통과가 아니다 |
| `cargo test -p onjeon-criteria --locked --offline` | 기존 시험 33개 통과. defaults 모듈은 포함되지 않는다 |
| `cargo test --workspace --locked --offline` | 종료 0. 별도 verification 워크스페이스는 포함되지 않는다 |
| `cargo test --manifest-path services/criteria/src/defaults/verification/Cargo.toml --locked --offline --lib` | 17개 통과, 납품 시험 1개 실패, 종료 101 |
| 위 명령의 `--lib` 대신 `--test product_api` | 제품 API 미연결로 컴파일 실패, 종료 101 |
| `python3 -I tools/ci/check_leak.py` 및 `--selftest` | 모두 통과 |
| `python3 -I tools/ci/check_skeleton.py` 및 `--selftest` | 모두 통과. 제품 서버를 탐침한 결과가 아니다 |
| `python3 -I -m unittest discover -s tools/ci/tests -p test_ci_checkers.py -k SkeletonRuntime -v` | 로컬 stub 기반 비노출 회귀 시험 2개 통과 |

전체 출력은 `cargo_test_defaults.log`, `cargo_test_workspace.log`에 첨부했다. 합성 검증·정적 검증을 실제 원문·제품 API 검증으로 표시하지 않는다.

## 미해소 차단 사항

| 리뷰 지적 | 현재 상태와 필요한 후속 조치 |
|---|---|
| P1 제품 크레이트 미연결 | 미해소. `services/criteria/src/lib.rs`와 `services/criteria/tests/conformance.rs`의 허용 경로 추가 요청에 대한 응답이 필요하다. 준비된 패치는 제품 연결과 기존 디렉터리 금지 단정의 교체를 함께 다룬다 |
| P1 출처가 확정된 판 부재 | 미해소. 공식 통계의 보존된 전체 원본 바이트와 검증 가능한 수신 기록이 필요하다. 네트워크 수신 실패를 데이터 부재나 성공으로 대체하지 않는다 |
| 최종 SHA 고정 독립 리뷰 | 이번 미커밋 변경에는 아직 없다. 감독이 최종 커밋 후 다른 작성 계열로 수행해야 한다 |

비가역·금전·법률·비밀값·운영 적용 결정은 필요하지 않으므로 `DECISION_REQUIRED.md`는 생성하지 않았다. 경로 제한과 원본 수신 실패에 따른 구현 차단이며, 병합 가능한 상태가 아니다.

## 확인

- [x] README·설계도·불변 원칙·D-08·요구사항·작업 명세를 읽었다. 적용 대상 AGENTS.md는 없었다.
- [x] 실제 변경 파일은 지정된 허용 경로 안에만 있다(`path_check.log`).
- [x] 수락 실패와 검증 범위를 기록했다. CI 성공을 실제 정확도·출시 승인으로 표현하지 않았다.
- [ ] 두 P1 차단 사항 해결, 실제 원문 검증, 제품 연결 수락 통과.
- [ ] 최종 SHA 고정 독립 리뷰 승인.
