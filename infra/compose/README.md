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
| `db-private` | `postgres:16.15-alpine` | **개인 영역**: 계약 스냅샷·가정·동의(BLUEPRINT §4, 계약 §5 ContractSnapshot). 서버 로그에 질의문·오류(ERROR)·오류 DETAIL을 남기지 않는다(I11 중 서버 설정 부분) |
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

1. **정적 시험**(docker 불필요, `tests/test_compose_static.py`): 비밀값 비노출, 포트·이미지 고정, 공개/개인 구성이 아무것도 공유하지 않음, `.env` 생성(전부 채움·서로 다름·재실행 불변·기존 값 보존), 신원 파일(영역별 버킷 범위, 디렉터리 700·파일 644), 셸 문법, 부정 검사 도우미가 올바른 사유의 실패만 통과시키는지(smoke.sh의 `denied`·`unreachable`를 가짜 명령으로 실행, `check-objects.sh`는 접근 거부 응답만 인정).
2. **실제 기동 시험**(docker compose 필요): 격리된 임시 프로젝트(다른 이름·상태 디렉터리·임의 포트)로 `up.sh`를 두 번 실행 → 영역 표지, 큐 넣기·꺼내기, 앱 역할 권한, 공개↔개인 자격 거부(DB 4방향), 네트워크 분리(대조 포함), 신원 파일을 비root 컨테이너 사용자(uid 65534)로 읽기, 개인 DB 서버 로그 시험(대조 포함), 객체 저장소 허용·거부(`s3-check`) → `down.sh --purge` 뒤 컨테이너·볼륨·네트워크가 남지 않음.

부정 검사는 "실패했다"로 통과하지 않는다. 자격 거부는 인증 실패·권한 거부 사유를, 영역 간 도달 불가는 `pg_isready`의 "응답 없음"(종료 코드 2)을, 객체 권한은 접근 거부 응답(403)을 요구한다. 컨테이너가 죽었거나 명령이 없어서 실패한 경우는 FAIL이다.

docker가 없으면 2단계를 못 돌린 것이므로 `LIVE: FAILED`와 종료 코드 1이다. 정적 시험만 돌리려면 `ONJEON_SMOKE_STATIC_ONLY=1`(이때는 `LIVE: SKIPPED`, 종료 코드 0이며 완료의 근거가 아니다). 완료의 근거는 `LIVE: PASSED`뿐이다.

### 이 작업 환경에서 실제로 확인한 것과 한계

`evidence/smoke.log`는 **실제 Docker 데몬**(Docker 29.9.1 + Compose v5.6.0, 작업 VM에 임시로 올림)에서 이 디렉터리의 현재 내용으로 `bash infra/compose/smoke.sh`를 끝까지 돌린 기록이고 `LIVE: PASSED`로 끝난다. 빈 data-root에서 시작해 이미지 세 개(`postgres:16.15-alpine`, `chrislusf/seaweedfs:4.48`, `amazon/aws-cli:2.38.1`)를 그 실행에서 레지스트리에서 당겼다(로그의 `Image ... Pulled` 줄, 다이제스트는 `evidence/images.log`). 확인한 것: `up.sh` 두 번(멱등), healthcheck가 초기화 완료 뒤에야 정상, 마운트한 `10-zone.sh` 실행, aws-cli v2로 버킷 생성·영역별 허용/거부 16항목, 공개↔개인 자격 거부 4방향(거부 사유까지 확인), 두 영역 컨테이너 사이 도달 불가("응답 없음"만 인정, 대조 포함), 신원 파일을 uid 65534로 읽기, 개인 DB 서버 로그 시험(대조 포함), `down.sh --purge` 뒤 컨테이너·볼륨·네트워크 0. 기본 경로(`up.sh`→`down.sh`→`down.sh --purge`, 고정 포트 15432·15433·18333)도 따로 한 번 실행했다.

변이 확인(`evidence/mutations.log`): 개인 DB에서 `log_min_messages=log`를 빼면 로그 시험 두 항목이 FAIL이고 `LIVE: FAILED`(종료 코드 1)다. 신원 파일을 600으로 바꾸면 uid 65534 컨테이너 사용자는 `Permission denied`로 읽지 못한다(644면 읽는다). `check-objects.sh`를 죽은 endpoint에 돌리면 16항목 전부 FAIL이고 "거부"로 통과하는 항목이 없다(`evidence/component_object_store.log`).

이 실행의 한계(숨기지 않는다):
- 작업 VM에는 Docker가 없어 정적 바이너리(Docker 29.9.1)와 Compose 플러그인을 `/tmp`에 받아 루트 데몬으로 임시 기동했다. 이 VM에는 iptables가 없어 Debian 패키지의 iptables-legacy를 `/tmp`에 풀어 데몬의 `PATH`에 두었다. 일반 Docker Desktop·Engine과 다른 점이 있을 수 있다.
- 저장소를 새로 클론한 것이 아니라 이 작업 트리(깨끗한 체크아웃)에서 실행했다. `.env`와 `.generated/`는 실행이 만들었고(gitignore) 시험 뒤 지웠다.
- 한 번의 실행이다(Linux x86_64 한 대). macOS·Windows의 Docker Desktop은 확인하지 않았다.
- 이 VM의 상위 DNS는 모르는 이름에도 응답했다. 그래서 영역 분리는 이름 해석이 아니라 상대 영역 컨테이너의 실제 IP에 닿는지로 확인한다(smoke.sh 주석 참고).

이전 실제 기동 실행이 잡은 문제 두 가지는 고쳤다: smoke.sh 자신의 `grep | wc` 파이프가 `pipefail`로 죽던 것, 그리고 `log_error_verbosity=terse`만으로는 오류 본문이 인용하는 값(`invalid input syntax for type integer: "..."`)이 개인 DB 로그에 남던 것(→ `log_min_messages=log` 추가).

구성요소를 따로 실행한 기록(`evidence/component_*.log`, `evidence/harness/`)은 Docker 없는 환경에서 쓰던 대체 검증이며 위 실제 기동 시험을 대신하지 않는다. 개인 DB 로그 설정의 효과는 실제 PostgreSQL 16 서버에서도 확인했다.

## 알려진 한계와 선택

- **객체 저장소가 MinIO가 아니다.** ADR-0001·§48.2는 "S3 호환(로컬 MinIO)"을 제안(미확정)으로 적었다. 이 작업을 한 2026-10-16에 `minio/minio`·`minio/mc` 이미지는 Docker Hub에서 조회되지 않았고 MinIO 저장소는 보관(archived) 상태였다(GitHub API `archived: true`, 마지막 푸시 2026-04-24). 고정할 수 있는 이미지가 없어 같은 요건(S3 호환, 신원별 버킷 권한, 로컬 단일 컨테이너)을 충족하고 태그를 확인한 SeaweedFS를 썼다. 객체 저장소는 S3 API로만 쓰므로 바꿔도 코드가 영향받지 않는다. 문서(§48.2, ADR-0001)의 MinIO 표기는 이 과제의 허용 경로 밖이라 고치지 않았다. **문서 갱신이 필요하다.**
- 로컬 저장소는 운영의 R2/S3 보호(쓰기 한 번만, 버전 관리, 삭제 거부, 비공개 강제; `infra/r2/README.md` §2)를 흉내 내지 않는다. 불변성 시험은 운영 도구(`tools/source_archive.py`)와 해당 시험의 몫이다.
- pgvector는 넣지 않았다(검색은 계산 권위 데이터가 아니고 이 과제 범위 밖). 필요해지면 공개 영역 이미지만 바꾼다.
- `s3`는 컨테이너 안에서 보조 포트(마스터·필러)도 연다. 호스트에 게시하지 않는다.
- 신원 파일 `.generated/s3.json`(비밀키 포함)은 **644**이고 디렉터리 `.generated/`는 **700**이다. 컨테이너에 바인드 마운트되는 것은 파일이라, 컨테이너 사용자가 root도 호스트 사용자도 아닐 때(비root 이미지, rootless Docker) 600이면 읽지 못한다(변이로 확인). 다른 호스트 사용자는 디렉터리에서 막힌다. 비밀값 보호를 디렉터리 권한에 맡기므로 `ONJEON_COMPOSE_STATE_DIR`를 다른 곳으로 둘 때도 `render_s3_config`가 디렉터리를 700으로 만든다. 현재 이미지는 root로 돈다(uid 0 확인).
- 이 디렉터리의 시험은 `tools/tests`가 아니므로 CI(`python3 -m unittest discover -s tools/tests`)가 돌리지 않는다. CI에 넣으려면 `.github/workflows/`를 바꿔야 하는데 이 과제의 허용 경로 밖이다. 감독자 또는 별도 과제의 몫이다.
- 이미지 태그는 고정했고(세 태그 모두 실제로 당겨 기동했다) 다이제스트로 고정하지는 않았다.
- 개인 DB는 ERROR·WARNING을 서버 로그에서 뺀다(`log_min_messages=log`). 개발 중 개인 DB의 SQL 오류는 클라이언트 출력으로만 보인다. 서버 로그 설정은 I11의 일부일 뿐이고 앱 로그·분석 쪽 누출 시험은 후속 과제다.
