# CRAWL-09 보관 업로더

이 노드는 Blueprint L1의 원본 보존과 P02/P03의 불변 원본·관측 이력을 위한
로컬 구현이다. 아래 시험은 합성 데이터(`origin=fixture`)의 완료 증거이며,
실제 보험 문서 확보, R2 보존 대조, 구획 추출·판 연결 또는 제품 전체의 완료
증거를 대신하지 않는다. 실제 수집을 시작하지 않는다.

```sh
PYTHONPATH=tools python3 -m crawler.uploader --spool /absolute/spool --target file:///absolute/archive
PYTHONPATH=tools python3 -m crawler.uploader --spool /absolute/spool --target file:///absolute/archive --apply
```

첫 명령은 기본 dry-run이다. 존재하는 스풀의 잠금을 잡아 저널을 읽고,
계획을 JSONL로 출력한다. 파일·디렉터리·저널·상태를 생성하거나 수정하지 않는다.
`Spool` 생성자나 복구를 수행하는 `list_pending()`도 호출하지 않는다.
스풀 소유자가 먼저 복구해야 하는 미완료 트랜잭션이나 찢어진 저널은 거부한다.
스풀 경로나 기존 `Spool` 인스턴스를 `upload(spool, target, mode="dry_run")`에
전달할 수 있다. CLI 오류·거부는 1, 키 충돌은 3, 예산 중단은 4다.

`--apply`의 파일 저장은 기존 `source_archive.LocalStore`를 확장하여
`put_raw`, `put_observation`, `put_once`를 사용한다. 키 생성·관측 JSON·조건부
생성 규칙은 기존 모듈이 담당한다. 기존 파일은 청크 단위로 해시를 비교한다.
동일 바이트는 `already_present`, 다른 바이트는 `Conflict`로 즉시 중단한다.
원본은 읽기 전에 64 MiB 상한을 확인하고, 한 번에 하나만 메모리에 올린다.
중복 계획은 이전 작업을 재탐색하므로 큰 스풀에서는 느릴 수 있지만, 모든 키나
원본을 메모리에 모으지 않는다. 호출자는 시간 함수를 `clock`으로 주입할 수
있으며, 대기·무작위·재시도 루프는 없다.

객체와 관측, `status/<UTC stamp>.json`을 모두 파일에서 다시 읽어 해시와
크기가 일치한 뒤에만 저널에 `uploaded, verified_file=true`를 fsync한다.
상태에는 시각, 스풀의 누적 문서 수, gap 수, 호출자가 전달한 `status`가 들어간다.
같은 초의 같은 상태는 멱등적이며, 같은 상태 키에 다른 내용은 충돌한다.
업로드 중 일부가 저장된 뒤 실패해도 스풀 항목은 완료 표시·삭제되지 않는다.
완료 표시 도중 프로세스가 중단되면 이미 표시한 항목도 검증된 항목이며,
나머지는 재실행할 수 있다.

스풀 삭제는 파일 apply의 `--cleanup`을 명시한 경우에만 한다. 검증된 완료
표시가 있는 항목의 관측 파일과, 다른 대기 항목이 참조하지 않는 본문만 삭제한다.
저널·gap 이력·아카이브는 삭제하지 않는다. `Spool.mark_uploaded()`로 외부에서
기록한 검증 증거 없는 표시만으로는 정리하지 않는다. 성공 뒤 별도 정리가
필요하면 같은 파일 대상에 `--apply --cleanup`을 다시 실행한다.

`--gaps /absolute/gaps.jsonl`은 기존 `GapWriter` 형식이다. 관측 키는 기존
`put_observation`으로 생성하고 `gap=true, status=null`을 기록한다. 이 키의
해시 접미사는 gap 메타데이터의 해시이며, 원본 확보를 의미하지 않는다.
본문 저장 없이 `object_key`, `sha256`, `bytes` 필드를 제거한다. URL은 API의
`gap_urls={source_id: url}`로 전달하며, 모르면 빈 문자열을 기록한다.
gap과 status도 조건부 생성·재읽기 검증을 거친다. 새 보관 접두사는 `status/`뿐이다.

비용 수치는 **추정치**다. 각 계획 행은 키·바이트·`stored` 또는
`already_present`를 출력한다. 요약의 `bytes`는 새 키의 본문 합계,
`total_bytes`는 중복을 포함한 모든 계획 행의 본문 합계다.
`class_a_estimate`는 새 키당 PUT 1회로 계산한다. 새 문서는 보통 원본 1회와
관측 1회로 2회, 여기에 새 status 1회가 더해진다. 본문 중복은 원본 PUT을
줄이고, gap은 관측 PUT 1회다. `class_b_estimate`는 계획 행당 조회 1회,
apply는 재검증까지 2회로 계산하는 참고치다. 파일 대상에는 실제 Class A/B
과금이 없다. 원격 apply의 두 번째 조회는 보수적으로 포함한 참고치이며,
이 노드는 원격 본문 재다운로드 검증을 수행하지 않는다. 실제 R2 사용량에는
예산 원장의 admission/reservation/settlement와 그 GET·PUT·LIST,
동시 생성 충돌, SDK 재시도도 영향을 준다. 이 추정치는 예산 예약이나 실제
사용량 계측을 대체하지 않는다.

`s3://`는 `--apply`, `--allow-real-r2`, 환경 변수
`ONJEON_CRAWLER_ALLOW_R2=1`, `--job`을 **모두** 요구한다. 하나라도 없으면
예산 처리·클라이언트 생성 전에 거부한다. 모두 주어진 경로는
`source_archive.with_budget(job, endpoint_url, fn)` 안에서만 저장소를 만든다.
엔드포인트·자격 증명 처리와 실제 요청 계측은 기존 도구에 맡긴다.
이 노드는 R2 실행을 검증했다는 주장을 하지 않으며, R2 경로에서는 로컬
항목을 완료 표시하거나 정리하지 않는다. 실제 실행·비용 결정은 이 작업의 범위 밖이다.
원격 기존 키의 체크섬이 없거나 조건부 생성 경합이 생기면, 업로드 버퍼와
별도로 본문 전체를 내려받는 기존 도구의 fallback을 실행하지 않고 중단한다.
이 경우도 스풀을 유지하며, 별도 검증이 필요하다.

예산 중단(4)은 즉시 반환하고 재시도하지 않는다. apply 실패는 로컬 스풀의
`upload_status.json`에 `upload_failed=true`와
`spool.upload_failures=1`을 기록해 기존 `status.upload_failed()`에 연결한다.
이 파일은 원격 보관 접두사가 아니다. 이후 성공하면 기존 실패 표시를 해제한다.
dry-run은 실패 상태 파일도 쓰지 않는다.

검증 명령:

```sh
python3 -m unittest discover -s tools/tests -p 'test_crawler_uploader.py'
python3 -m unittest discover -s tools/tests
```

새 시험은 실제 소켓·S3 클라이언트·프로세스 실행·대기를 차단한다.
R2 성공 경로는 실행하지 않으며, 15가지 누락 게이트 조합과 클라이언트 생성
이전의 예산 중단을 확인한다. fixture만으로 무쓰기, 기존 함수와의 바이트 일치,
중복, 충돌, 검증 실패, 정리 범위, gap/status, 상한과 경고 플래그를 확인한다.
