# Audit 1: BLUEPRINT §11 현황과 ADR·DEC 변경 시 갱신

검증일: 2026-10-26. 대상: `audit1-blueprint-s11-refresh`.

§11의 기준일 2026-10-09와 누락된 `tools/daemon/`, `tools/r2_budget.py`,
`tools/registry_normalize.py`, 이후 ADR·DEC 기록을 현재 저장소와 대조했다.
현황은 2026-10-26으로 갱신하고 수집·검증 도구, 개발 도구, 계약·트윈·서비스
코드와 모바일 프레임을 반영했다. 2026-10-09의 Rust 39개 + doctest 3개와
R2 원본 58키·파생 61키는 과거 관측으로 유지하며 현재 검증 결과와 구분한다.

§10 규칙 8은 마일스톤 완료 여부와 관계없이 ADR·DEC 변경과 같은 변경에서
§11 상태·관문 검토와 날짜 갱신을 요구한다. `tools/blueprint_status.py`는
ADR 18개·DEC 17개의 파일명·내용 SHA-256을 대조한다. `--write`는 UTC 기준일과
전체 링크 색인만 갱신한다. 상태·관문은 사람이 검토하며 자동 완료 판정하지 않는다.
기존 CI의 Python 시험 검색에 `tools/tests/test_blueprint_status.py`가 포함된다.

변경 전 검사 실패는 [before.log](../../../tools/evidence/audit1-blueprint-s11-refresh/before.log)에
보관했다. 새 시험은 ADR·DEC 각각의 추가·수정·삭제·개명, 같은 날 수정,
다음 날 재갱신, 무변경 과거 날짜 허용, 잘못된 날짜·색인·마커·헤더 거부,
CLI의 읽기 전용 검사·쓰기·입력 오류, 상태·다른 절 보존을 확인한다.

기준 커밋: `9f10911daa6437819d2eb5cb11c618e875fa2322`.
로그 디렉터리: [tools/evidence/audit1-blueprint-s11-refresh/](../../../tools/evidence/audit1-blueprint-s11-refresh/).
각 실행 로그에는 명령과 종료 코드를 남겼다. 아래 결과는 로컬에서 직접 실행한 것이며 CI 실행을 주장하지 않는다.

| 검사 | 결과 | 로그 |
|---|---|---|
| `python3 -I tools/blueprint_status.py` | ADR·DEC 35개 일치 | [status-final.log](../../../tools/evidence/audit1-blueprint-s11-refresh/status-final.log) |
| 새 §11 검사 + 기존 R2 문서·역사적 시험 수 검사 | 43건 통과. 새 §11 시험 18건 포함 | [focused-final.log](../../../tools/evidence/audit1-blueprint-s11-refresh/focused-final.log) |
| `python3 -m unittest discover -s tools/tests -v` | 852건 실행: 846건 통과·6건 건너뜀, 실패·오류 0 | [python-final.log](../../../tools/evidence/audit1-blueprint-s11-refresh/python-final.log) |
| `cargo fmt --all -- --check`, `cargo clippy --offline --all-targets -- -D warnings`, `cargo test --offline --all` | 모두 통과. Rust 단위·통합 399건 + doctest 3건, 무시 1건 | [rust-1.log](../../../tools/evidence/audit1-blueprint-s11-refresh/rust-1.log), [rust-2.log](../../../tools/evidence/audit1-blueprint-s11-refresh/rust-2.log), [rust-3.log](../../../tools/evidence/audit1-blueprint-s11-refresh/rust-3.log) |
| 어휘·검증 자료 내부 일관성·검사기 자체 시험 | 모두 통과. 변조 38종이 의도한 이유로 거부됨 | [design-1.log](../../../tools/evidence/audit1-blueprint-s11-refresh/design-1.log), [design-2.log](../../../tools/evidence/audit1-blueprint-s11-refresh/design-2.log), [design-3.log](../../../tools/evidence/audit1-blueprint-s11-refresh/design-3.log) |
| 설계 명세 검사·온톨로지 runner 빌드/검사 | 기계 44/44·존재 72/72, 질문 11/11·제약 자체 시험 15/15·릴리스/문서 모델 25/25 통과 | [design-4.log](../../../tools/evidence/audit1-blueprint-s11-refresh/design-4.log), [design-5.log](../../../tools/evidence/audit1-blueprint-s11-refresh/design-5.log), [design-6.log](../../../tools/evidence/audit1-blueprint-s11-refresh/design-6.log) |
| 제품 목적 등록 검사·누출 검사·스켈레톤 검사 | 모두 통과(정적 검사 범위) | [ci-2.log](../../../tools/evidence/audit1-blueprint-s11-refresh/ci-2.log), [ci-4.log](../../../tools/evidence/audit1-blueprint-s11-refresh/ci-4.log), [ci-5.log](../../../tools/evidence/audit1-blueprint-s11-refresh/ci-5.log) |

기존 R2 문서 시험은 §11의 새 `수집·검증 도구` 행에서 보존·재현·비용 도구와
미배포 S3 대안을 확인하도록 갱신했다. 원본 보존·대조 문구와 실제 R2 기록의
바이트 일치·재현 수 검사는 유지하고 과거 관측일 표기도 확인한다.

추가 검사에서 확인한 **기존 실패**: `tools/ci/tests` 20건 중 2건 실패,
`check_deps.py`가 온톨로지→규칙 엔진 참조 위반 3건을 보고한다.
`packages/ontology/Cargo.toml:15`, `packages/ontology/tests/common/mod.rs:350`,
`packages/ontology/tests/fixture_origin/main.rs:126`의 DEP-ZONE·IMP-ZONE이다.
기준 커밋의 파일을 이 worktree 내 임시 디렉터리에 추출해 같은 명령을 실행했고,
동일한 2건 실패와 3건 위반을 재현했다. 임시 디렉터리는 제거했다.
[기준 시험](../../../tools/evidence/audit1-blueprint-s11-refresh/baseline-1.log),
[기준 의존성 검사](../../../tools/evidence/audit1-blueprint-s11-refresh/baseline-2.log),
[현재 시험](../../../tools/evidence/audit1-blueprint-s11-refresh/ci-1.log),
[현재 의존성 검사](../../../tools/evidence/audit1-blueprint-s11-refresh/ci-3.log),
[위반 3건의 정확 일치 대조](../../../tools/evidence/audit1-blueprint-s11-refresh/baseline-comparison.log).
이 노드는 해당 의존성 정책이나 온톨로지 코드를 변경하지 않았다.

Python 건너뜀 6건: `ONJEON_ARCHIVE_RAW` 미설정 원본 시험 2건,
현재 botocore가 이미 조건부 쓰기를 지원해 해당하지 않는 구버전 시험 1건,
로컬 보관본·`pdftotext`를 요구하는 재현 시험 3건이다. 실제 원본을 새로
검증했다는 주장은 하지 않는다. 새 §11 시험 18건에는 건너뜀이 없다.
변경 소스·문서의 해시는 [source-snapshot.json](../../../tools/evidence/audit1-blueprint-s11-refresh/source-snapshot.json)에,
허용 경로·금지 문서 불변·공백·로컬 링크 검사는 [scope.log](../../../tools/evidence/audit1-blueprint-s11-refresh/scope.log)에 남겼다.
실행 로그는 행 끝 공백·파일 끝 빈 줄만 정리했다.

09_제품목적_대응표와의 관계: 이 변경은 단일 기준의 현황·결정 추적을 고치는
감리 후속이다. P01~P19의 실제 데이터·화면 시험·출시 완료 증거를 제공하지 않는다.
개발 도구 완성과 첫 출시 완성을 구분하고 T-OP-08 관문을 유지한다.
DEC-D-02의 위임·사용자 확정 대기, D-04 접근 차단, O14 잠금 승인,
O17 대량 자동 수집 차단, 정본 변경의 조건부 승인·병합 미승인도 유지한다.
실제 R2·AI 제공자·GitHub에 접근하거나 외부 작업을 실행하지 않았다.
