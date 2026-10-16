# infra

| 디렉터리 | 내용 | 상태 |
|---|---|---|
| `compose/` | 로컬 개발 스택: 공개 영역 DB, 개인 영역 DB, S3 호환 객체 저장소, PostgreSQL 기반 큐. `bash infra/compose/up.sh` / `down.sh`. [README](compose/README.md) | 구현(T-OP-01). 실제 컨테이너 기동은 Docker 있는 환경에서 `compose/smoke.sh`로 확인 필요 |
| `r2/` | 원본 보관소(Cloudflare R2), 비용 한도 | 사용 중([README](r2/README.md)) |
| `s3/` | 원본 보관소의 AWS 대안 정의 | 쓰지 않음([README](s3/README.md)) |

비밀값은 이 디렉터리의 어떤 파일에도 쓰지 않는다. 로컬 자격 증명은 `compose/up.sh`가 `.env`에 만들며 Git에 올라가지 않는다.
