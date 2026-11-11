# audit5-non-claude-ai-provider evidence

기록일: 2026-11-11. 노드: `audit5-non-claude-ai-provider` (fix round 1).
감리 지적: DEC-D-02가 구성 원칙·정책 소유자는 정했지만 비-claude 업체·모델 ID를
고정하지 않아 확보 대상이 비어 있었고, 이 항목이 V1 이종 계열 검수·T-OP-03·
T-KN-06·S1 관문과 유일한 독립 병합 리뷰 경로를 막는다는 지적이었다.

수정: 결정 기록 `docs/decisions/audit5-non-claude-ai-provider.md`가 위임·가역
개발 기준을 정한다 — 승인 계열 X=OpenAI gpt(첫 후보 gpt-6-astra, 이 저장소에서
운영 식별 증거가 있는 유일한 비-claude 계열), 레드팀 Y=grok(동일 05 §2 API 경로
검증 조건부, 검증 전에는 X의 다른 모델·프롬프트 + degraded 기록), 키는 사용자
발급·실행 환경 비밀값 전용, 지출 미승인(제공자 측 월 한도 확인 뒤), 접근 확인
기록 이후에만 D-02를 decisions_recorded에 등록. 병합 리뷰 경로는 D-02에 막히지
않는다는 전제 정정(audit1-independent-review-path)을 유지한다. 이 노드는 지출·
계정·키 발급·배포를 하지 않으며 정본(캐논)에 모델 ID를 박지 않는다.

fix round 1의 국소 시험 실패는 코드 결함이 아니라 환경 문제였다: 새 작업 트리에
잠긴 Cargo 의존성이 캐시되지 않아 Python 시험의 오프라인 온톨로지 실행기 빌드가
serde_json을 내려받지 못했다(잠금 파일은 serde_json 1.0.154/1.0.151을 요구하나
캐시에는 1.0.149만 있었다). README의 준비 절차(rustup override + 두 작업 공간
`cargo fetch --locked`, `pip install --user boto3==1.43.100`)로 해결했고
Rust·Python 코드는 바꾸지 않았다.

## 로그

| 파일 | 명령 | 결과 |
|---|---|---|
| [prep.log](prep.log) | `rustup override set --path "$PWD" 1.98.1` + 두 작업 공간 `cargo fetch --locked` | 의존성 캐시 완료(serde_json 1.0.154/1.0.151 등) |
| [focused.log](focused.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -p 'test_audit5_non_claude_ai_provider.py' -v` | 신규 회귀 시험 25건 전체 통과 |
| [python-tests.log](python-tests.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -v` | 1,555건 실행, 실패·오류 0, 건너뜀 6(이전 라운드의 ontology-runner 빌드 오류 2건 해소) |
| [cargo-tests.log](cargo-tests.log) | `cargo test --all --locked --offline` + 온톨로지 실행기 `cargo test --locked --offline` | 71개 스위트 518건 통과, 실패 0 |
| [status.log](status.log) | `git status --short`·`git diff --check`·`python3 -I tools/blueprint_status.py` | 허용 경로 내 새 파일 3개뿐, 공백 오류 없음, §11 결정 색인 37개 ADR/DEC 일치 |

건너뜀 6건은 이 환경에 없는 선택 의존성 때문이다(비공개 원본 보관소
`ONJEON_ARCHIVE_RAW` 2건, 로컬 아카이브·pdftotext 3건, botocore If-None-Match
지원 1건). 이전 라운드와 같은 건너뜀 프로파일이다.

## 범위

- 이 증거는 결정 기록의 근거 대조와 회귀 시험 실행만 검증한다. 실제 비-claude
  API 접근 확인(05 §2), 키 발급·월 한도 설정·지출, D-02 등록, 실제 이종 계열
  ReviewDecision은 여전히 사용자 조치와 후속 과제(T-KN-06·T-OP-03)의 몫이며
  이 노드에서 수행하거나 승인하지 않았다.
- 신규 회귀 시험은 결정 기록의 정책 경계(무지출·무키·등록 시점·전제 정정)와
  그 근거(review_records.log, tasks.json 관문, daemon_rules.json cond, 05 §2·§4,
  C-19, ai-gateway, roles.draft.json, audit1·audit2 기록)를 고정한다.