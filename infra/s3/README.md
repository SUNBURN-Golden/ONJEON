# 공시 원본·파생 AWS S3 경로 폐기

[ADR-0016](../../docs/decisions/ADR-0016-원본-보관소-R2.md)이 ADR-0015의 AWS S3 선택을 Cloudflare R2로 대체했다. 기존 문서의 참조를 위해 이 안내만 남긴다. Audit 7에서 미배포 CloudFormation 템플릿과 AWS 실행 예제를 삭제하고, Python 보관 도구의 기본 AWS 분기도 제거했다.

현재 공시 보관소의 구성과 명령은 [R2 안내](../r2/README.md)를 따른다. `s3://`는 S3 호환 API의 버킷 주소 형식이다. R2 사용 시 `ONJEON_S3_ENDPOINT` 또는 `--endpoint-url`로 HTTPS R2 엔드포인트를 지정하고 `--job`을 전달한다.
