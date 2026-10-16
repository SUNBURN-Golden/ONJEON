# 로컬 Compose (T-OP-01)

개발 PC에서 공개 영역 DB, 개인 영역 DB, S3 호환 객체 저장소를 한 명령으로 띄운다. 근거: 제3부 §48.1 5항(로컬을 Compose로 전부 띄운다), §48.2, §48.4(local = 합성 픽스처), ADR-0001, BLUEPRINT §4(개인 영역은 저장·권한·로그가 분리), I12.

**로컬 개발 전용이다.** TLS 없음, 127.0.0.1에만 열림, 백업 없음. 운영·staging 구성이 아니고 운영 공급자(미정)를 정하지 않는다. 합성 픽스처 외의 자료, 특히 실제 개인 계약·건강·가족력 자료를 넣지 않는다.

## 쓰는 법

```bash
bash infra/compose/up.sh            # 처음 한 번: 자격 증명 생성 + 기동 + 버킷 생성. 몇 번을 다시 실행해도 안전
bash infra/compose/down.sh          # 컨테이너·네트워크 제거, 데이터 볼륨은 남김
bash infra/compose/down.sh --purge  # 볼륨과 생성 파일까지 제거(DB를 처음부터 다시 만들고 싶을 때)
bash infra/compose/smoke.sh         # 시험(아래)
```

필요한 것: Docker Engine(또는 Docker Desktop)과 compose v2 플러그인, bash. `up.sh`는 `.env.example`을 `infra/compose/.env`로 복사하고 비어 있는 비밀값만 `/dev/urandom` 무작위 값으로 채운다. `.env`와 `.generated/`는 Git에 올라가지 않는다(`.gitignore`). 이미 채워진 값은 바꾸지 않는다.

기동 뒤 접속 정보는 `up.sh`가 출력한다. 기본 포트: 공개 DB 15432, 개인 DB 15433, 객체 저장소 18333(모두 127.0.0.1). 값은 `.env`에서 바꾼다. 비우면 임의 포트다.

**비밀번호는 데이터 볼륨을 처음 만들 때 한 번만 반영된다.** `.env`의 DB 비밀번호를 나중에 바꿔도 이미 만들어진 볼륨에는 적용되지 않는다. 바꾸려면 `down.sh --purge` 뒤 다시 `up.sh`를 실행한다. 볼륨을 남긴 채 `.env`만 지우면 접속할 수 없게 된다.

## 구성

| 서비스 | 이미지 | 역할 |
|---|---|---|
| `db-public` | `postgres:16.15-alpine` | **공개 영역**: 공시 코퍼스·릴리스(L0~L7). 개인 자료 금지 |
| `db-private` | `postgres:16.15-alpine` | **개인 영역**: 계약 스냅샷·가정·동의(BLUEPRINT §4, 계약 §5 ContractSnapshot). 질의문을 서버 로그에 남기지 않는다(I11) |
| `s3` | `chrislusf/seaweedfs:4.48` | S3 호환 객체 저장소. 신원이 셋(관리·공개 영역·개인 영역) |
| `s3-init` | `amazon/aws-cli:2.38.1` | 버킷 세 개 생성(일회성, 멱등). `up.sh`가 끝나기를 기다린다 |
| `s3-check` | 같음 | 영역 간 권한 확인. 시험용이라 `--profile check`일 때만 돈다 |

### 공개 영역과 개인 영역은 이렇게 갈라진다

| | 공개 영역 | 개인 영역 |
|---|---|---|
| DB 서버 | `db-public` | `db-private` (별도 서버 프로세스·볼륨·네트워크 `private-zone`) |
| DB 관리 역할 | `PUBLIC_DB_ADMIN_USER` | `PRIVATE_DB_ADMIN_USER` |
| DB 앱 역할(큐 읽기·쓰기만, 슈퍼유저·DDL 불가) | `PUBLIC_DB_APP_USER` | `PRIVATE_DB_APP_USER` |
| 비밀번호 | 네 개 모두 서로 다른 무작위 값. 두 DB가 읽는 환경 변수 이름도 겹치지 않는다 | |
| 객체 저장소 신원 | `public-zone`: `onjeon-raw-sources`, `onjeon-derived-sources`만 | `private-zone`: `onjeon-private-contracts`만 |
| 작업 큐 | `db-public`의 `queue.jobs` | `db-private`의 `queue.jobs` |

한 영역의 자격 증명으로는 다른 영역의 DB·버킷에 들어갈 수 없다. `smoke.sh`가 이 거부를 실제로 확인한다. 한 객체 저장소 프로세스를 두 영역이 공유하는 것은 로컬 편의이고, 분리는 신원별 버킷 권한으로 강제한다. 운영에서는 영역별 계정·버킷·키로 나눈다(`infra/s3/README.md` §1 마지막 문단).

### DB 초기화(`initdb/`)

이미지가 **빈 데이터 디렉터리의 첫 기동에서 한 번** 실행한다. 영역별로 같은 스크립트가 `ONJEON_ZONE`만 달리 받는다.

- 앱 역할 생성(`NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`), 접속 권한을 PUBLIC에서 회수해 앱 역할에만 부여(관리용 DB `postgres`·`template1` 포함), `public` 스키마 권한 회수.
- 영역 표지: `SELECT current_setting('onjeon.zone')`이 `public` 또는 `private`을 돌려준다. 서비스가 엉뚱한 영역에 붙었는지 시작할 때 확인하는 데 쓴다.
- 작업 큐 `queue.jobs`: PostgreSQL 기반 큐(ADR-0001, §48.2 1순위). 꺼내기는 `FOR UPDATE SKIP LOCKED`. 상태는 `ready/running/done/failed`, 본문 `payload`는 8KiB 제한이다. **본문에는 식별자·참조만 넣고 원문·금액·건강정보를 넣지 않는다.** 개인 영역 작업은 개인 영역 큐로만 보낸다. 공개 영역 재조사 큐로 보내는 것은 개인정보를 제거한 공개 상품 식별 후보뿐이다(계약 §11).
- 이 파일은 **도메인 스키마를 만들지 않는다.** 공개/개인 분리 스키마와 I7·I12의 제약은 M1 범위다. 큐 상태값은 인프라 작업 상태이며 `vocabulary.json`의 도메인 상태 축과 무관하다.

## 시험

`bash infra/compose/smoke.sh`

1. **정적 시험**(docker 불필요, `tests/test_compose_static.py`): 비밀값 비노출, 포트·이미지 고정, 공개/개인 구성이 아무것도 공유하지 않음, `.env` 생성(전부 채움·서로 다름·재실행 불변·기존 값 보존), 신원 파일(영역별 버킷 범위·파일 권한), 셸 문법, 권한 거부가 접근 거부 응답일 때만 인정되는지.
2. **실제 기동 시험**(docker compose 필요): 격리된 임시 프로젝트(다른 이름·상태 디렉터리·임의 포트)로 `up.sh`를 두 번 실행 → 영역 표지, 큐 넣기·꺼내기, 앱 역할 권한, 공개↔개인 자격 거부(DB 4방향), 네트워크 분리, 객체 저장소 허용·거부(`s3-check`) → `down.sh --purge` 뒤 컨테이너·볼륨·네트워크가 남지 않음.

docker가 없으면 2단계는 `LIVE: SKIPPED`를 출력하고 **통과로 세지 않는다**(종료 코드는 0). 그 환경에서 실패로 만들려면 `ONJEON_SMOKE_REQUIRE_DOCKER=1`.

### 이 작업 환경에서 실제로 확인한 것과 못 한 것

작업 VM에는 Docker가 없어 **`docker compose up`과 `smoke.sh` 2단계는 실행하지 못했다.** 대신 구성요소를 같은 입력으로 따로 실행해 확인했다(`evidence/`).

| 확인한 것 | 방법 | 로그 |
|---|---|---|
| `docker-compose.yml` 문법·앵커·병합 | PyYAML 해석 | (실행 기록은 PR 본문) |
| DB 초기화 SQL 전체와 smoke의 DB 검사 | 실제 PostgreSQL 16.14 서버 둘(공개·개인)에서 `10-zone.sh`·`zone-init.psql` 실행. 영역 표지, 큐 꺼내기, 권한 거부, 교차 자격 거부, 개인 서버 로그에 질의문 없음 | `evidence/component_postgres.log` |
| 객체 저장소 플래그와 신원 형식, `init-objects.sh`, `check-objects.sh` | 실제 SeaweedFS 4.48 바이너리에 저장소가 만든 신원 파일을 주고 실제 스크립트 실행(AWS CLI v1). 버킷 생성·재실행·영역 간 허용/거부. 끊긴 엔드포인트에서는 모든 검사가 실패로 나옴 | `evidence/component_object_store.log` |

**확인하지 못한 것(Docker 있는 환경에서 `smoke.sh`로 확인해야 함):** 컨테이너 이미지 기동 자체(이미지 당김, `postgres:16.15-alpine`의 초기화 단계에서 마운트한 스크립트 실행, 컨테이너 안 healthcheck 명령의 동작), 컨테이너 사이 네트워크 이름 해석, `amazon/aws-cli` v2에서의 동작(위 검증은 v1), `up --wait`와 `run --rm` 순서, 종료 뒤 자원 정리. 이 항목들은 실행으로 확인되기 전까지 "동작한다"고 쓰지 않는다.

## 알려진 한계와 선택

- **객체 저장소가 MinIO가 아니다.** ADR-0001·§48.2는 "S3 호환(로컬 MinIO)"을 제안(미확정)으로 적었다. 이 작업을 한 2026-10-16에 `minio/minio`·`minio/mc` 이미지는 Docker Hub에서 조회되지 않았고 MinIO 저장소는 보관(archived) 상태였다(GitHub API `archived: true`, 마지막 푸시 2026-04-24). 고정할 수 있는 이미지가 없어 같은 요건(S3 호환, 신원별 버킷 권한, 로컬 단일 컨테이너)을 충족하고 태그를 확인한 SeaweedFS를 썼다. 객체 저장소는 S3 API로만 쓰므로 바꿔도 코드가 영향받지 않는다. 문서(§48.2, ADR-0001)의 MinIO 표기는 이 과제의 허용 경로 밖이라 고치지 않았다. **문서 갱신이 필요하다.**
- 로컬 저장소는 운영의 R2/S3 보호(쓰기 한 번만, 버전 관리, 삭제 거부, 비공개 강제; `infra/r2/README.md` §2)를 흉내 내지 않는다. 불변성 시험은 운영 도구(`tools/source_archive.py`)와 해당 시험의 몫이다.
- pgvector는 넣지 않았다(검색은 계산 권위 데이터가 아니고 이 과제 범위 밖). 필요해지면 공개 영역 이미지만 바꾼다.
- `s3`는 컨테이너 안에서 보조 포트(마스터·필러)도 연다. 호스트에 게시하지 않는다.
- 이 디렉터리의 시험은 `tools/tests`가 아니므로 CI(`python3 -m unittest discover -s tools/tests`)가 돌리지 않는다. CI에 넣으려면 `.github/workflows/`를 바꿔야 하는데 이 과제의 허용 경로 밖이다. 감독자 또는 별도 과제의 몫이다.
- 이미지 태그는 고정했으나 다이제스트로 고정하지는 않았다(이 환경에서 당길 수 없어 확인하지 못함).
