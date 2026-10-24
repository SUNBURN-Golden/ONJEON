# Audit 1: 보관소를 아직 S3로 적은 문서

검증일: 2026-10-22. 대상: `audit1-blueprint-v1-row-s3-stale` finding.

보관소 제공자는 ADR-0016(2026-10-09)에서 S3에서 R2로 바뀌었다. 같은 날 원본 58키·파생 v2 61키를
R2에 보존하고 다시 받아 전부 바이트 일치했고, 표본 14건 원본 해시도 14/14 일치했다
(`docs/blueprint/validation/source_checks/2026-10-09_r2_*.json`). 그런데 세 곳이 이전 상태를 적고 있었다.

| 위치 | 상태 | 비고 |
|---|---|---|
| `docs/blueprint/validation/GAP_REPORT.md` 21행 | **고침** | R2 결정·보존·대조 결과와 재현 8/14로 다시 썼다 |
| `docs/BLUEPRINT.md` §9.2 V1 행 (253행) "보관소는 S3로 결정(ADR-0015)", 남은 조건 "S3 실제 보존과 다운로드 대조(자격 증명 필요)" | **미수정, 보호 문서** | 아래 교체안 |
| `docs/BLUEPRINT.md` §11 "코드" 행 (318행) "S3 버킷 정의(미배포)" | **미수정, 보호 문서** | 아래 교체안 |

`docs/BLUEPRINT.md`는 이 작업의 수정 금지 목록에 있어 고치지 않았다. 이 finding은 그 파일을 고치기 전에는
닫히지 않는다. 문서 소유자가 아래 문구로 바꾸면 된다.

## BLUEPRINT.md 교체안

253행, "보관소는 S3로 결정(ADR-0015)"부터 행 끝까지:

> 보관소는 R2로 결정(ADR-0015의 S3 결정을 ADR-0016이 바꿈), 원본 58키·파생 v2 61키를 R2에 보존하고 다시 받아 전부 바이트 일치(2026-10-09, 표본 원본 해시·인용 14/14, 파생 결과까지 완전 재현 8/14, 나머지 6건은 재생성 도구 없음으로 미검증). 남은 조건: 파생 6건의 재생성 도구와 재현 검증, 다른 계열 AI 검수, 화면 열린 항목(S1·S6)

318행, "S3 버킷 정의(미배포)":

> R2 보존·대조 도구와 비용 한도 장치(`infra/r2/`), 대안으로만 남긴 AWS S3 버킷 정의(`infra/s3/`, 미배포)

남은 조건에서 "S3 실제 보존과 다운로드 대조(자격 증명 필요)"를 뺀 이유: §11 "데이터" 행과 마일스톤 행이 이미
"원본 R2 보존·대조 완료"라고 적고 있어, 253행만 남으면 같은 문서가 서로 어긋난다.

## 시험

`tools/tests/test_storage_provider_docs.py` (6개, 기존 `unittest discover -s tools/tests`에 포함):

- GAP_REPORT: 이전 문구가 없고, R2·ADR-0016을 이름으로 대고, 인용한 `2026-10-09_r2_*.json`이 존재하고
  validation README에 올라 있으며, "완전 재현 8건·미검증 6건"이 R2 재현 기록과 같다.
- BLUEPRINT: §11이 R2 대조 완료를 적고 있음을 확인. 이전 문구 부재 시험은 `expectedFailure`다. 위 교체안이
  반영되면 "unexpected success"로 실패하므로 그때 데코레이터를 지운다.

```sh
python3 -m unittest tools/tests/test_storage_provider_docs.py -v
python3 -m unittest discover -s tools/tests
python3 tools/validation_check.py && python3 tools/vocab_check.py
```
