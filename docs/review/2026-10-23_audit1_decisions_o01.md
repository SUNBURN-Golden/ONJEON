# Audit 1: O01 완료 표시 수정안과 검증

검증일: 2026-10-23. 작업 트리: `audit1-decisions-o01-close`.

**미적용 상태다. 원장의 O01은 아직 열려 있으므로 finding 해결 또는 수락 조건 완료를 주장하지 않는다.**
요청은 `docs/blueprint/DECISIONS.md:52` 수정을 지시하면서 같은 파일을 `never touch` 목록에
포함했다. 이 충돌에 대한 확인을 요청했고, 허용 응답 전에는 해당 파일을 변경하지 않았다.
새로운 제품·법률·비용·운영 결정은 필요하지 않으며 `DECISION_REQUIRED.md`는 만들지 않았다.

## 근거와 수정안

- [ADR-0018 §4 및 결과](../decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md):
  우체국보험 포함·기관 유형 구분, 공제 제외·확보율 분모에서도 제외를 확정했고,
  공제·우체국보험 포함 여부의 열린 결정을 닫는다고 명시한다.
- [결정 원장 D19](../blueprint/DECISIONS.md)는 같은 범위를 이미 반영했다.
- 같은 원장의 O13처럼 O01 질문에 취소선을 넣고 D19·ADR-0018 §4와 확정 범위를 적는다.
  전체 기관·소스 목록 작성이 구현 작업이라는 D11 설명과 나머지 행·열은 보존한다.
- [검토용 패치](2026-10-23_audit1_decisions_o01.patch)는 원장 O01 한 행 변경과
  `tools/tests/test_decisions_o01.py` 회귀 시험 2개 추가를 담는다. 이 시험도 아직 작업 트리에
  설치되지 않았고, 패치를 적용한 임시 사본에서 실행했다.

## 검증 결과

| 검증 | 결과 |
|---|---|
| `git apply --check docs/review/2026-10-23_audit1_decisions_o01.patch` | 통과. 작업 트리에 적용하지 않고 패치 적용 가능성만 검사 |
| 임시 사본에 패치 적용 후 `python3 -I -m unittest discover -s tools/tests -p test_decisions_o01.py -v` | 2/2 통과: 취소선·결정 참조·D11 작업 구분, D19와 일치하는 포함/제외 범위 |
| 같은 사본에서 원장만 원래 바이트로 복구 후 같은 시험 실행 | 2/2 실패, 종료 코드 1. 기존 O01 누락을 실제 탐지 |
| 원본/후보 줄 비교 | 줄 수 동일, 변경된 줄은 O01 하나뿐. 작업 트리 원장 바이트는 원본과 동일 |
| `python3 tools/vocab_check.py` | 통과: 45축·228값 |
| `python3 tools/validation_check.py` | 통과: 14개 표본의 내부 정합성. 보관 원본 재검증은 아님 |
| `python3 tools/validation_check.py --selftest` | 통과: 변조 38종 적발 |
| `python3 -m unittest discover -s tools/tests -v` | 종료 코드 1: 551개 실행, 오류 6건·skip 7건. 이 실행은 미적용 작업 트리 기준 |
| `CARGO_TARGET_DIR=/tmp/audit1-o01-target cargo test --all --offline --no-fail-fast` | 종료 코드 101: Rust 386 통과·2 실패·1 ignored. 이 실행도 미적용 작업 트리 기준 |
| `CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=/tmp/audit1-o01-target cargo test -p onjeon-contracts --lib --offline` | 재검증 통과: Rust 54개 및 중첩 Python codegen 시험 129개 |
| `git diff --check` | 통과 |

Python 오류 6건은 `test_r2_budget.EndToEnd` 3건과 `test_r2_checkpoint.EndToEnd` 3건으로,
모두 로컬 HTTP 서버 생성 시 `PermissionError: [Errno 1] Operation not permitted`였다.
Skip은 비공개 보관본/도구 미지정 5건, 현재 botocore가 conditional put을 지원하는 경우 1건,
온톨로지 runner의 오프라인 의존성 빌드 실패 1건이다.

Rust 실패는 `onjeon-collect --test http_conformance`의 동일한 소켓 권한 오류와
`onjeon-contracts --lib`의 중첩 Python 호환성 시험이 `serde` 조회를 위해 네트워크에
접근한 경우다. 바깥 `--offline`은 중첩 Cargo 호출에 전파되지 않는다.
중첩 호출까지 `CARGO_NET_OFFLINE=true`를 전파한 contracts 재검증은 통과했다.
재검증 로그는 `/tmp/audit1-o01-contracts-offline.log`에 있다.
전체 실행 로그는 `/tmp/audit1-o01-python-tests.log`, `/tmp/audit1-o01-cargo-tests.log`에 있다.

## 보호 문서를 변경하지 않는 패치 재검증

저장소 루트에서 아래 명령은 임시 사본만 수정한다.

```sh
python3 - <<'PY'
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path.cwd()
patch = root / 'docs/review/2026-10-23_audit1_decisions_o01.patch'
with tempfile.TemporaryDirectory(prefix='audit1-o01-') as temp:
    stage = Path(temp)
    path = Path('docs/blueprint/DECISIONS.md')
    (stage / path).parent.mkdir(parents=True)
    shutil.copyfile(root / path, stage / path)
    original = (stage / path).read_bytes()
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=stage, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=stage, check=True)
    command = ['python3', '-I', '-m', 'unittest', 'discover',
               '-s', 'tools/tests', '-p', 'test_decisions_o01.py', '-v']
    subprocess.run(command, cwd=stage, check=True)
    (stage / path).write_bytes(original)
    assert subprocess.run(command, cwd=stage).returncode == 1
    assert (root / path).read_bytes() == original
PY
```

이 변경은 기존 범위 결정의 원장 표시만 정정하는 제안이다. 실제 데이터 확보·트윈·소비자 UX의
완료 증거나 `09_제품목적_대응표` 행의 출시 완료 증거로 집계하지 않는다.
