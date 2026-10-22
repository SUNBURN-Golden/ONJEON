# Audit 1: 수집·재현·정규화 도구의 미시험 경로

검증일: 2026-10-22. 대상: `audit1-tools-untested-paths` finding.

운영 코드는 변경하지 않고 기존 `unittest discover -s tools/tests`에 자동 포함되는
단위 시험 60개를 추가했다. 원본·파생 저장은 실제 `LocalStore`, 입력 CSV·문서·출력은
임시 디렉터리, 외부 추출·OCR 실행은 모의 `subprocess.run`을 사용한다.
정규화 CLI 시험도 임시 트리에 복사한 스크립트와 CSV만 실행한다.

## Finding과 시험 대응

| 대상 | 시험 파일 | 검증한 동작 |
|---|---|---|
| `source_archive.cmd_fetch` | `tools/tests/test_source_archive_commands.py` (파일 전체 16개) | 해시 키로 여러 원본을 중첩 경로에 복원, 없는 원본의 실패와 출력 미생성. 경로 탈출 거부는 기존 `test_source_archive.ConfinedPath`도 유지 |
| `source_archive.cmd_archive_samples` | 같은 파일 | 원본·출처·문서 역할·시점 기록, 재실행 불변성, 파생 manifest의 해시·원본 연결, 파생 입력 미지정, 누락·해시 불일치·위험 경로의 실패와 다음 행 처리, 보관 키 충돌 시 중단 |
| `source_archive.cmd_add_observation` | 같은 파일 | MIME 추론·지정·fallback, 추가 메타데이터, 재실행 불변성, 원본 변경 시 이전 원본·관측 유지, 관측 충돌·없는 파일·잘못된 JSON·source ID 거부 |
| `verify_sources.reproduce_one` | `tools/tests/test_reproduce_paths.py` (파일 전체 19개) | 원본 누락·변조의 조기 반환, PDF의 쪽·인용 정규화, HTML 셀과 짝 문서, 누락 개수·예시 상한, OCR 선택·쪽 캐시·내부 캐시 비노출, 실제 LocalStore manifest와 재생성 바이트 대조, 재현·불일치·기록 훼손·미검증 판정 |
| `verify_sources.Regenerator` | 같은 파일 | Poppler 두 모드와 각각의 캐시, 버전 불일치·도구 부재, OCR 버전·실행 선택·기존 쪽 캐시·UTF-8 바이트, 300dpi 회색조 쪽 렌더링과 한국어 OCR 인자, 렌더링 실패 전파, 지원하지 않는 도구·형식·이름 |
| `registry_normalize.py` 전체 | `tools/tests/test_registry_normalize.py` (16개) | 축 조회, 정본 코드·모든 host alias·HTTP 상태·redirect·빈 값·미지 값, 공시 확보/차단/실패/미조회 구분, evidence alias, detail 보존, 상품·특약 분모 기본값과 기존 진척 보존, 선택적 공시 처리, CSV 재실행 바이트 동일성, 잘못된 행 입력의 무변경, 접근 로그 변환·보존, 세 CSV를 처리하는 CLI |
| `vocab_check.lint` | `tools/tests/test_vocab_check.py` (9개) | 폐기·금지 상태·필드·시각 alias, 다른 축에서 살아 있는 코드 허용, 명시적 허용 줄, 생성 문서·비계약 문서 제외, 중복 제거·파일/토큰 순서·줄 번호, 토큰 경계·대문자·짧은 alias, 금지 사유 우선순위, 대상 파일 없음 |

## 재실행

저장소 루트에서:

```sh
python3 -m unittest tools/tests/test_source_archive_commands.py tools/tests/test_reproduce_paths.py tools/tests/test_registry_normalize.py tools/tests/test_vocab_check.py -v
python3 -m trace --count --summary --missing --coverdir /tmp/audit1-coverage --module unittest tools/tests/test_source_archive_commands.py tools/tests/test_reproduce_paths.py tools/tests/test_registry_normalize.py tools/tests/test_vocab_check.py
python3 -m unittest discover -s tools/tests -v
python3 tools/vocab_check.py
python3 tools/validation_check.py
python3 tools/validation_check.py --selftest
cargo fmt --all -- --check
cargo clippy --all-targets -- -D warnings
cargo test --all
```

## 실행 결과와 한계

- 추가 시험: **60/60 통과**, skip 없음. 표준 라이브러리 `trace`의 실행 줄 기록에서
  위에 지정한 모든 함수·메서드 범위에 미실행 표시(`>>>>>>`)가 없음을 확인했다.
  이는 실행 줄 확인이며 정식 branch coverage 측정은 아니다. 정규화 스크립트의
  `__main__` 경로는 별도 임시 트리 CLI 시험으로 확인했다.
- 어휘 검사 통과: 33축·177값. 검증 자료 내부 정합성 검사 통과: 14개 표본.
  변조 자체 시험 통과: 38종 모두 의도한 사유로 적발.
- Rust 시험 **94개 통과**(문서 시험 3개 포함). 포맷·Clippy 검사 통과.
- 전체 Python 시험: **365개 실행, 356개 통과·3개 오류·6개 skip**, 종료 코드 1.
  변경 전 실행도 305개 중 같은 3개 오류·6개 skip이었다.
  오류는 `test_r2_budget.EndToEnd`의 아래 세 시험이며 모두
  `S3Stub`의 로컬 HTTP 서버 소켓 생성 시 `PermissionError: [Errno 1] Operation not permitted`로
  발생했다. 해당 검증은 소켓을 허용하는 환경에서 다시 실행해야 한다.
  - `test_admitted_run_spends_within_its_admission_before_reserving`
  - `test_repeated_refused_runs_are_recorded_then_closed`
  - `test_settlement_retry_is_counted_in_the_settlement`
- 기존 skip 6개: 실제 보관본을 요구하는 HTML 시험 2개·재현 시험 3개는 보관본 미지정,
  구형 botocore 거부 시험 1개는 설치 버전이 conditional put을 지원해 skip됐다.
  신규 시험 때문에 기존 시험의 skip 조건을 바꾸지 않았다.
- 일부 기존 CSV 읽기 구현은 파일을 명시적으로 닫지 않아 `ResourceWarning`을 출력한다.
  이번 변경은 해당 구현을 수정하거나 경고를 숨기지 않는다.
- 별도 `runner_verify` 확장 시험도 시작했으나 이 finding 밖의 임시 Git 원격 시나리오를
  실행하는 것을 확인해 중단했다. 해당 확장 시험을 통과로 집계하지 않는다.

## 제품 목적과 증거 범위

`BLUEPRINT`의 L0~L2 수집·보존·복원 기반과 `09_제품목적_대응표`의 P01~P03을
지원하는 **도구 단위 시험 증거**다. 이번 finding의 “시험 없음”은 해소했다.
합성 입력·모의 추출 결과이므로 실제 전 보험사·상품·특약 확보, 실제 파생물 재현,
소비자 화면 연결, 첫 출시 관문 또는 P01~P03의 실제 데이터 완료 증거로 세지 않는다.
