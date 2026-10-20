# data/criteria — 판단 기준 관리(영역 C) 자료

판단 기준의 데이터 계약이다(02_구현계약 §1.5, T-KN-12). 적재·검증·릴리스·변경 목록의
구현은 `services/criteria`(`onjeon-criteria`)에 있고, DB 제약은 `infra/db/criteria/`에 있다.

## 디렉터리

| 경로 | 내용 | 지금 상태 |
|---|---|---|
| `criteria/<slug>.json` | 기준 파일 하나 = 기준 항목 + 그 판들 | 없음(서비스 기준 0건) |
| `releases/<id>.json` | 고정된 기준 릴리스(불변) | 없음 |
| `criterion-file.schema.json` | 기준 파일의 JSON Schema | 있음 |
| `release-file.schema.json` | 릴리스 파일의 JSON Schema | 있음 |

서비스 기준은 아직 0건이다. 기준 판 작성은 출처를 요구하고, 적용 승인(`criteria_application`,
D-08, T-KN-14) 없이는 서비스 모드에 쓰이지 않는다. 시험 전용 자료는 이 디렉터리에 두지
않는다 — `origin=fixture` 표식과 함께 `services/criteria/tests/fixtures/`에 둔다.

`data/criteria/defaults/`는 이 과제의 것이 아니다. 기본 필요액·참고 통계 기본값 후보는
T-KN-13의 경로이며, 기준 파일 어디에도 `default`·`defaults`·`default_*` 키를 쓸 수 없다
(적재기가 거부한다). 기본값이 없으면 사용자 직접 가정만 쓴다(§1.5, O05).

## 기준 파일 계약

```json
{
  "criterion": {
    "id": "crit:<slug>",
    "kind": "priority_rule | reference_stat | applicability_rule | question_rule",
    "label": "...",
    "scope": { "situations": ["..."], "subjects": ["..."] },
    "recorded_at": "RFC3339"
  },
  "versions": [
    {
      "version": 1,
      "valid_from": "YYYY-MM-DD", "valid_to": null,
      "sources": [{ "ref": "raw:|clause:|obs: 근거 참조", "evidence_kind": "..." }],
      "rationale": "...",
      "recorded_at": "RFC3339",
      "origin": "pipeline | fixture"
    },
    {
      "version": 2,
      "supersedes": "crit:<slug>@1",
      "correction_reason": "error_correction | source_changed | interpretation_improved | rule_changed",
      "valid_from": "...", "sources": [...], "rationale": "...", "recorded_at": "...", "origin": "pipeline"
    }
  ]
}
```

규칙(DB 제약과 같은 것, 적재기가 DB보다 좁은 부분만 더 강제한다):

- **기준은 고치지 않는다.** 정정은 새 판(`version` +1)이고 `supersedes`가 바로 이전 판을
  가리킨다(선형 사슬). `version=1`은 `supersedes`가 없고, `supersedes`와
  `correction_reason`은 쌍으로만 온다.
- **출처 없는 판은 없다.** `sources`는 1개 이상이며 각 `ref`는 `raw:sha256:<64>`·
  `clause:<문법>`·`obs:src:<문법>`의 근거 참조다. `evidence_kind`는 어휘 축
  `criterion_source_kind`(`public_statistic`·`statute`·`regulator_notice`·`terms_fact`·
  `editorial`)다. `editorial`은 "참고 통계"가 아니라 "온전의 판단"으로 표시된다.
- **적용 범위는 항상 있다.** `scope.situations`·`scope.subjects` 모두 한 항목 이상.
  범위 밖이면 그 기준은 평가에 쓰지 않는다.
- **알 수 없는 키는 거부된다.** 어휘·열거값에 없는 값도 성공으로 처리하지 않는다.
- **개인 식별자는 올 수 없다.** `contract:`·`person:`·`upload:`·`del:`·`consent:`·
  `assume:` 접두어가 어느 문자열에도 있으면 거부(K8).
- `id`(`crit:<slug>@<n>`)는 `criterion_id`·`version`에서 파생하므로 파일에는 쓰지 않는다.

## 기준 릴리스

`releases/<id>.json`은 불변 스냅샷이다. 지식 릴리스(`rel:`)와 **별도 ID 공간**(`crel:`)을
갖고 지식 릴리스가 `criteria_release_ref`로 참조만 한다.

```json
{
  "id": "crel:<yyyymmdd>-<n>",
  "members": { "criterion_versions": ["crit:a@2", "crit:b@1"] },
  "content_sha256": "<members와 각 판 내용의 정규 JSON SHA-256>",
  "frozen_at": "RFC3339"
}
```

`members`는 고정 시점 각 기준의 최신 판 목록(정렬). 내용 해시는 구성원과 각 판의
전체 내용(기준 항목·판·출처)을 덮는다 — 고정 뒤 구성원이 빠지거나 판 내용이 제자리에서
바뀌면 무결성 검사(`verify`, ONJ-KN-S-052)가 잡는다. `origin=fixture` 판은 릴리스에
들어가지 못한다(ONJ-KN-S-050).

## 변경 목록

기준 판이 정정되면 두 릴리스(또는 릴리스와 현재 판)의 차이가 **변경 목록**이다.
`added`·`corrected`·`removed` 항목의 `before` 판 id가, `conclusion_dependency.deps.criteria`에서
영향받는 결론을 찾는 입력이다 — 그 판에 기대는 저장 결과는 `stale`로 표시된다(§1.5 정정 영향).

이 디렉터리에 기준이 추가될 때는 출처가 실제 존재하는 공개 근건만 단다. 설계 문서나
화면 문구는 기준의 출처가 아니다.
