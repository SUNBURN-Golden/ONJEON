# Audit 5 — 데몬 비밀값 형식 누락

2026-11-10. 개발 도구 T-OP-00·T-OP-09의 비밀값 탐지·제외 규칙을 보강했다.
제품 추적은 BLUEPRINT §9.5·09 §5의 T-OP-08 축 5에 한정한다.

기존 규칙은 `R2_SECRET_ACCESS_KEY`의 뒷부분과 JSON 키의 닫는 따옴표를 처리하지 못했다.
단독 R2 32/64자리 hex, AWS ASIA, GitHub github_pat_·ghs_, Bearer 형식도 빠져 있었고,
파일 제외는 `.env`만 지정하며 모의 fnmatch와 실제 Git glob 모두 대소문자를 구분했다.

[규칙 데이터](../proposals/설계검토_결과/daemon_rules.json)에 해당 형식과 `.env.*`를 추가하고,
모의 어댑터는 casefold·fnmatchcase, 실제 어댑터는 Git `icase` pathspec으로 동일한 제외를 적용한다.
탐지 패턴은 계속 공용 `core/secret_scan.py`에서 읽으며 세 검사 지점과 R-10 처리는 유지한다.
일반 대입식의 값에 점을 허용하면 `token = self.credentials.token(...)` 같은 소스까지 탐지하므로
그 경계도 음성 사례로 고정하고, 점이 포함된 Bearer는 별도 패턴으로 검사한다.

[회귀 시험](../../../tools/tests/test_daemon_secret_scan.py)은 실제 제공자의 형식·길이를 따르는
합성 문자열 23개를 실행 중 조립한다. 이전 구현에서 초기 7개 시험의 하위 사례 118건 실패를
재현한 뒤 수정했다. 파일 보존의 R-10 반송·커밋/푸시 0건, 결과·전환 신호·하트비트의 거부와
inbox_seen 보존, 중첩 문자열 가림과 저널 추가 전 가림을 검사한다.
`.env.local`·대소문자 변형 등 제외 10개와 일반 경로 5개는 모의 Git과 실제 Git 임시 인덱스로 대조한다.
실제 Git 시험은 init·add·write-tree·ls-files만 허용하며 원격·커밋을 만들지 않는다.

T-OP-09 CLI는 선택된 `--rules`가 합성 corpus를 모두 탐지하는지 원격 준비·시나리오 실행 전에 확인한다.
누락·빈 패턴·컴파일 오류·규칙 읽기 오류는 종료 1이며 출력은 사례 이름 또는 일반 오류 설명뿐이다.
현재 회귀 10개와 관련 시험 결과·재현 명령은 [실행 증거](../../../tools/evidence/audit5-daemon-secret-scan-patterns/README.md)에 기록한다.

전체 Python 시험에서 D-04 회귀의 규칙 파일 전체 해시 고정이 이번 변경을 거부했다.
HEAD와 구조적으로 대조해 `preserve_manifest.excludes`·`secret_patterns.patterns`·설명 필드
`_exclude_matching` 외 모든 값이 같은지 확인한 뒤 `o13_unchanged_gates.json`의 해당 파일 해시와
갱신 이유만 수정했다. 다른 결정·작업 게이트·자격·전이·비용 정책은 그대로 대조한다.

패턴 기반 검사이므로 임의 비밀값 전체를 검출한다는 보장은 없다. 단독 32/64자리 hex는 같은 길이의
일반 해시도 탐지하는 보수적 정책이다. 40자리 Git OID와 인접 영숫자에 포함된 부분 문자열은 제외한다.
이번 작업에서 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
실제 원격 시나리오 전체 재실행은 커밋·푸시 금지 범위 때문에 수행하지 않았다.
이 증거는 [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 개발 도구 보강이며,
P01~P19의 전 상품 수집·트윈·소비자 화면·첫 출시 완료 판정을 바꾸지 않는다.
