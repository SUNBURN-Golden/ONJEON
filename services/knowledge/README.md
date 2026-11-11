# onjeon-knowledge (T-KN-04)

공개 지식의 추가 전용 저장소. 서비스는 `KnowledgeRepository::connect(config, allowlist)`로 PostgreSQL에 연결한다. `new()`는 시험·오프라인 검사 전용 메모리 저장소다. DB 접속 정보는 호출자가 제공하며 오류와 Debug 출력에는 포함하지 않는다.

T-CT-05의 `infra/db/public/apply.sh`를 적용한 DB에 아래 보조 마이그레이션을 한 번 적용한다. 어댑터가 스키마를 자동 생성하거나 기존 제약을 해제하지 않는다.

```sh
psql -X -v ON_ERROR_STOP=1 --single-transaction -f services/knowledge/migrations/001_repository.sql
```

접속에는 psql의 환경 변수 또는 서비스의 외부 설정을 쓴다. 관리자 자격은 마이그레이션에만 필요하다. 서비스는 T-CT-05의 `knowledge_writer`, 원본·구획·조항 적재는 `data_writer` 권한 경계를 따른다. 검수 결정은 ai-review 실행 결과를 전달받는 API이며 이 크레이트가 모델 검수나 문의 초안을 생성하지 않는다.

## 저장과 검사

- `ingest_assertion`은 추가만 한다. 수정 메서드는 없다. 정정은 새 ID와 `supersedes`·`correction_reason`이다. 둘 이상의 정정과 충돌은 `ingest_corrections`로 한 트랜잭션에 저장한다. DB 지연 제약 실패 시 모두 롤백된다.
- 구획·조항·본문 판·계열 등은 `insert_record`, 충돌은 `insert_conflict`, 공백과 작업은 각각 `insert_gap`·`insert_task`로 저장한다. 작업 상태 변경은 공백 상태를 바꾸지 않는다. 충돌 구성원은 `assertions`가 정식 필드이며 이전 `assertion_ids` 입력도 같은 형식으로 변환한다.
- 영속 입력은 T-CT-05의 열 이름과 필수 열을 사용한다. 예: 구획의 `raw_asset_id`, 조항의 `segment_id`, 주장의 소문자 `criticality`와 객체 `value{raw, normalized, ...}`, 가격의 `source_as_of`. DB가 필수 열·어휘·FK·accepted·불변성 제약을 다시 검사한다. 필수 값을 자동으로 채우지 않는다.
- 온톨로지 전용 속성(`decision.covers`, 규칙 연결 등)은 본 행과 같은 트랜잭션에서 `knowledge.record_extension`에 보존한다. 조회 시 DB 열이 우선한다. 닫힌 역변환이 하나 있다. `scope_relation`처럼 대상(`object`)과 값(`value`)을 함께 쓰는 주장은 `chk_assertion_object_xor_value` 때문에 대상만 열에 넣고 값은 확장 행에만 둔다. 재접속 시 NULL인 값 열을 확장 행의 값으로 되돌리므로 K4·K12가 같은 관계를 읽는다. 그 밖의 술어는 DB의 XOR 제약이 그대로 적용된다. `get`·`list`·`task`는 마지막 적재/`refresh()` 시점의 캐시를 읽는다. `check_candidate`는 매번 새 DB 스냅샷을 검사한다. 승격은 검사한 스냅샷의 구성원을 저장한다.
- 검사 경계에서만 `c0` → `C0`, 영문 문서 역할 → 온톨로지 역할, `source_as_of` → `as_of` 등을 변환한다. 구획의 정규 `fingerprint_rule`·`fingerprint_sha256` 열이 있으면 NULL까지 검사 지문에 반영하며, 확장 행의 `fingerprint`가 덮어쓰지 못한다. 노드는 `public.node`의 `kind` 열을 `class`로 읽고 `attrs`를 펼친다. DB 행은 기본값을 포함해 항상 `attrs`가 있으므로 확장 행의 다른 `class`가 있어도 정규 `kind`가 우선한다. `attrs`의 `kind`(예: 감액)·`applies_to`·`value`가 K7이 읽는 값이며, 열(`id`·`label`·`origin`·`onto_version`·`recorded_at`)과 클래스는 `attrs`가 덮어쓰지 못한다. `attrs` 없이 `class`가 있는 오프라인 온톨로지 형식 노드는 `kind`를 속성으로 유지한다. 저장된 원본 필드는 바꾸지 않는다. K1~K16 검사 뒤 가격을 포함한 accepted 검수 관문과 R2 근거 관문도 재검사한다. 위반 집합은 승격되지 않는다.
- R2 allowlist는 Git 고정 관측 목록을 호출자가 읽어 제공한다. 두 기존 원시 목록 형식을 지원하며 다운로드 검증 결과의 불일치·실패 항목은 제외한다. `raw`·`seg`·`clause`·`obs`·`premium` 근거를 RawAsset까지 해소한다. 미존재·순환 참조·목록 밖 해시는 거부한다. `insert_record("raw_assets", …)` 자체도 목록 검사다. 해시가 목록 밖이거나 `id`가 `raw:sha256:<해시>`가 아니면 거부한다. 후보 검사는 참조 여부와 무관하게 모든 원본 행을 다시 목록과 대조하며(B4), 서비스를 거치지 않고 들어온 행도 승격을 막는다. `set_allowlist` 이후 후보 검사에도 새 목록이 적용된다.
- B1은 `packages/fixtures/**`와 `docs/blueprint/**`를 상대·절대 경로, 부모 경로 이동, 기존 심볼릭 링크까지 확인하여 거부한다. B2/B3은 주장과 가격에 모두 적용한다.

## 가격 원시 보존과 비교 자격

가격 API의 기준일은 `source_as_of` 하나다. `missing_dimensions`의 기준일 이름은 DB 계약대로 `as_of`이며 누락 목록은 실제 공백과 일치해야 한다. `comparison_eligible=true`에는 비어 있지 않은 조건·구성·기준일·비교 기준과 유효한 accepted 검수 결정이 필요하다.

기존 `public.premium_observation`은 조건 없는 행을 거부한다. 조건이 없는 원시 관측은 보조 표 `knowledge.raw_premium_observation`에 저장한다. 이 표는 기존 가격 표의 제약을 복제하고 조건 필수 제약만 원시 보존 전용 제약으로 바꾼다. 항상 비교 불가이며 `conditions` 공백을 기록해야 한다. 근거·금액·관측 시각, fixture/accepted, 검수 결정, 개인정보 및 추가 전용 제약은 유지한다. 재접속 후 두 경로를 함께 조회한다. 비교 자격 변경은 새 ID의 가격 관측이다.

후보 저장은 내부 제약 검사 결과이며 공개 ReleaseManifest 발행이 아니다. production 릴리스의 B5/B10·그림자 비교·공개 API는 T-KN-07 등 후속 과제다. 이 크레이트는 비교·정렬·예산 API를 제공하지 않는다.

## 실행한 시험

```sh
bash services/knowledge/test.sh
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo fmt --all -- --check
bash infra/db/public/test.sh
python3 -I tools/ci/check_leak.py
python3 -I tools/ci/check_skeleton.py
python3 -I -m unittest discover -s tools/ci/tests -k SkeletonRuntime
```

`test.sh`는 로컬 PostgreSQL 도구로 Unix 소켓 전용 임시 DB를 만들고 종료 시 클러스터 전체를 제거한다. DB 시험마다 비어 있는 마이그레이션 완료 DB를 복제하므로 다른 시험의 위반이 승격 실패를 가리지 않는다. PostgreSQL이 없으면 실패하며, 외부 DB를 받아 사용하지 않는다. 일반 cargo 시험에서는 DB 시험 3개가 명시적으로 ignored다. `test.sh`는 `--include-ignored`로 실제 실행한다. r26 시험은 같은 T-KN-02 A-box에서 이력 제약 0건·질문 11/11과 서비스 거부를 함께 확인한다. 질문 계산은 기존 시험 CLI를 별도 target 디렉터리에 `--locked`로 빌드해서 호출한다.

최신 로그는 `evidence/fix_round_5_*.log`다. round 5는 확장 행의 `fingerprint`·`class`가 정규 DB 컬럼을 가려 K16·K3를 우회하던 두 문제를 고쳤다. 메모리 시험은 지문 규칙·해시 불일치와 NULL, 클래스 충돌과 `attrs.class` 충돌을 확인한다. DB 시험은 확장 행에 충돌 값이 남는 것을 확인한 뒤 재접속하여 K16·K3 및 승격 거부·후보 0행을 확인한다. 확장 지문이 달라도 정규 지문이 판 구성과 맞으면 승격된다. 기존 K7·관계 값 복원·R2 목록 검사는 유지한다. 마이그레이션은 바꾸지 않았다.

전체 워크스페이스 시험은 414개 통과, 4개 ignored다. knowledge DB 시험 3개는 `test.sh`에서 별도로 실행해 서비스 시험 29개(단위 1, 저장소 23, r26 1, DB 3, 문서 1)가 모두 통과했다. 나머지 ignored는 twin-runtime의 픽스처 재생성 도구이며, 같은 파일의 최신성 검증 시험은 통과했다. DB 제약 시험 166개, clippy·fmt, 누출·스켈레톤 정적 검사와 비노출 시험 2개도 통과했다.

round 2의 CI 검사기 전체 자기 시험은 기존 온톨로지 의존성 위반 3건으로 20개 중 2개 실패했다. `fix_round_2_baseline.log`는 당시 HEAD의 읽기 전용 사본과 작업 트리에서 해당 위반이 같음을 확인한다. round 3~5에서 이 전체 자기 시험을 다시 실행한 것으로 표시하지 않는다. PR 설명 게시와 새 커밋 SHA에 고정된 작성 계열(OpenAI·Anthropic) 외 리뷰는 감독 프로세스의 미완료 작업이다. 로컬 `PR_BODY.md`와 파일 해시 기록은 이 두 수락 조건을 충족하지 않는다. 원격 CI 실행이나 적격 독립 리뷰를 로컬 시험의 결과로 주장하지 않는다.
