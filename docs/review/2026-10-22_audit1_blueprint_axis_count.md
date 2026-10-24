# Audit 1: 어휘 축 수를 손으로 적은 자리

검증일: 2026-10-22. 대상: `audit1-blueprint-axis-count` finding.

`docs/BLUEPRINT.md` 174행은 "전체 31개 축"이라고 적고,
`docs/blueprint/proposals/인계_설계책임/README.md` 53행도 "상태 어휘 정본(31개 축)"이라고 적는다.
정본 `packages/schemas/vocabulary.json`의 축 수는 이 finding이 열릴 때 33개였고 지금은 45개다.
손으로 적은 수는 축이 늘 때마다 어긋나므로 Audit 1은 숫자를 빼거나 `vocab_check.py`가
생성 문서 `docs/blueprint/VOCABULARY.md`에 그 수를 쓰게 하라고 했다.

| 위치 | 상태 | 비고 |
|---|---|---|
| `docs/blueprint/VOCABULARY.md` "## 축 목록" | **장치만 고침** | `vocab_check.py --write`가 이제 "전체 N개 축." 줄을 생성한다. 이 파일도 이 노드의 수정 금지 목록이라 커밋된 문서에는 아직 그 줄이 없다. 소유자가 `--write`를 돌리면 들어가고, 들어간 뒤에는 수를 정본에서 다시 세므로 낡지 않는다 |
| `docs/BLUEPRINT.md` 174행 "전체 31개 축" | **미수정, 보호 문서** | 아래 교체안 |
| `docs/blueprint/proposals/인계_설계책임/README.md` 53행 "상태 어휘 정본(31개 축)" | **미수정, 보호 문서** | 아래 교체안 |

세 파일 모두 이 작업의 수정 금지 목록에 있어 고치지 못했다. 이 finding은 두 prose 자리를
고치고 생성 문서를 다시 만들기 전에는 닫히지 않는다. 문서 소유자가 아래대로 하면 된다.

## 교체안

`docs/BLUEPRINT.md` 174행:

> 전체 축과 화면 문구, 폐기된 표기의 대응은 VOCABULARY.md에 있다. 제3부 §44.3·§56, 화면 설계서 §6의 이전 표기는 이 정본으로 대체된다.

(숫자만 뺀다. 축 수는 생성 문서 VOCABULARY.md가 단다.)

`docs/blueprint/proposals/인계_설계책임/README.md` 53행, `packages/schemas/vocabulary.json` 행의
"무엇" 칸:

> 상태 어휘 정본

그리고 `python3 tools/vocab_check.py --write`로 생성 문서를 다시 만든다.

## 눈감지 않는 장치

`tools/vocab_check.py`는 어휘를 가리키는 줄의 손으로 적은 "N개 축"을 검사한다.

- 생성 문서: `render()`가 "전체 N개 축." 줄을 만들고, 신선도 검사는 커밋된 문서에 그 줄이
  아직 없는 것(소유자가 아직 `--write`를 안 돌린 상태)까지만 허용한다. 줄이 있으면
  정본의 수와 같아야 하고, 두 번 적혀 있거나 다른 줄이 하나라도 다르면 실패다.
- 고칠 수 있는 계약 문서에 정본과 다른 수가 있으면 실패다. 숫자를 빼라고 적는다.
- 수정 금지 문서(`PROTECTED_DOCS`: BLUEPRINT·PRINCIPLES·계약 정본류·data·registry·제안서)는
  실행할 때마다 실제 수를 다시 계산한 알림을 출력한다. 실패가 아니므로 CI는 막지 않지만,
  틀린 수가 매 실행 로그에 계속 보이고 문서가 고쳐지면 알림도 저절로 사라진다.
- 제안서(`docs/blueprint/proposals/`)는 계약 문서가 아니라 원래 검사 밖이었으나, 이 finding의
  두 번째 위치이므로 알림 대상에는 포함한다.

## 시험

`tools/tests/test_vocab_check.py`:

- 어휘 가리킴 줄의 손 적은 축 수: 고칠 수 있는 문서는 실패, 보호 문서는 알림, 수가 맞거나
  허용 표시가 있으면 조용.
- 생성 문서: `render()`가 살아 있는 축 수를 쓰고, 축 수 줄이 없는 커밋 문서는 신선도
  검사를 통과하지만 틀리거나 겹친 축 수·그 밖의 차이는 실패.

`tools/tests/test_blueprint_axis_count.py`:

- 생성기가 정본의 축 수와 같은 "전체 N개 축."을 만들고, 커밋된 생성 문서가 신선도 검사를
  통과하며 다른 축 수를 적지 않는다.
- 고칠 수 있는 계약 문서에 틀린 수가 없다.
- BLUEPRINT·제안서 README의 틀린 수와 보호 문서 알림: `expectedFailure`다. 소유자가 교체안을
  반영하면 "unexpected success"로 실패하므로 그때 데코레이터를 지운다.
- 이 기록이 두 미수정 위치와 교체안을 다 든다.

```sh
python3 -m unittest tools/tests/test_blueprint_axis_count.py -v
python3 -m unittest discover -s tools/tests
python3 tools/vocab_check.py
```

## 실행 결과와 한계

- `python3 tools/vocab_check.py`: 종료 0. 생성 문서에 축 수 줄이 아직 없다는 안내와 두 보호
  문서 알림("says 31 axes, vocabulary.json has 45")이 출력된다.
- `python3 -m unittest discover -s tools/tests`: 통과(`expectedFailure` 3건은 예정된 실패로 센다).
- 한계: 보호 문서 두 곳의 "31"은 여전히 본문에 있고, 커밋된 VOCABULARY.md에는 축 수 줄이
  아직 없다. 소유자가 교체안을 반영하고 `--write`를 돌리고 시험 데코레이터를 지워야
  finding이 닫힌다.
