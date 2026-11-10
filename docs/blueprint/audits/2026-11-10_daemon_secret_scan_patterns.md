# Audit 5 — 데몬 비밀값 형식 누락

2026-11-10. 개발 도구 T-OP-00·T-OP-09의 비밀값 탐지·제외 규칙을 보강했다.
제품 추적은 BLUEPRINT §9.5·09 §5의 T-OP-08 축 5에 한정한다.

기존 규칙은 `R2_SECRET_ACCESS_KEY`의 뒷부분과 JSON 키의 닫는 따옴표를 처리하지 못했다.
R2/S3/AWS 자격 이름이 붙은 32/64자리 hex, AWS ASIA, GitHub github_pat_·ghs_, Bearer 형식도 빠져 있었고,
파일 제외는 `.env`만 지정하며 모의 fnmatch와 실제 Git glob 모두 대소문자를 구분했다.

[규칙 데이터](../proposals/설계검토_결과/daemon_rules.json)에 해당 형식과 `.env.*`를 추가하고,
모의 어댑터는 casefold·fnmatchcase, 실제 어댑터는 Git `icase` pathspec으로 동일한 제외를 적용한다.
탐지 패턴은 계속 공용 `core/secret_scan.py`에서 읽으며 세 검사 지점과 R-10 처리는 유지한다.
일반 대입식의 값에 점을 허용하면 `token = self.credentials.token(...)` 같은 소스까지 탐지하므로
그 경계도 음성 사례로 고정하고, 점과 `_`가 포함된 Bearer(RFC 6750 b64token)는 같은 패턴으로 검사한다.
32/64자리 hex는 처음에는 `*_ACCESS_KEY_ID`·`*_SECRET_ACCESS_KEY` 같은 R2/S3/AWS credential 이름에
붙은 값만 탐지했다. Cargo.lock의 `checksum`·`sha256:` 로그·내용 해시처럼 같은 모양의 일반 digest는
자격증명이 아니며, 이를 모두 비밀로 보면 보존 대상 트리의 모든 파일이 R-10으로 반송된다.
따라서 자격 이름 없는 32/64자리 hex도 탐지하되, `checksum`·`sha256`·`content_hash`·`tree_hash`
같은 digest 이름에 바로 대입된 값만 음성 경계로 남긴다.

[회귀 시험](../../../tools/tests/test_daemon_secret_scan.py)은 실제 제공자의 형식·길이를 따르는
합성 문자열 29개를 실행 중 조립한다. 이전 구현에서 초기 7개 시험의 하위 사례 118건 실패를
재현한 뒤 수정했다. 파일 보존의 R-10 반송·커밋/푸시 0건, 결과·전환 신호·하트비트의 거부와
inbox_seen 보존, 중첩 문자열 가림과 저널 추가 전 가림을 검사한다.
`.env.local`·대소문자 변형 등 제외 10개와 일반 경로 5개는 모의 Git과 실제 Git 임시 인덱스로 대조한다.
실제 Git 시험은 init·add·write-tree·ls-files만 허용하며 원격·커밋을 만들지 않는다.

T-OP-09 CLI는 선택된 `--rules`가 합성 corpus를 모두 탐지하고, 비밀이 아닌 경계 값은 하나도
탐지하지 않는지 원격 준비·시나리오 실행 전에 확인한다. 빈 패턴과 `"."`처럼 모든 값에 일치하는
패턴은 corpus를 전부 통과하므로 음성 경계 검사가 이를 거부한다. 누락·빈 패턴·컴파일 오류·
규칙 읽기 오류는 종료 1이며 출력은 사례 이름 또는 일반 오류 설명뿐이다.
현재 회귀 17개와 관련 시험 결과·재현 명령은 [실행 증거](../../../tools/evidence/audit5-daemon-secret-scan-patterns/README.md)에 기록한다.

Fix round 1은 감리 지적 6건을 모두 반영했다. (1) 32/64자리 hex 규칙을 R2/S3/AWS credential
문맥으로 좁히고 digest 음성 사례와 digest 파일이 있는 모의 인계 시험을 추가했다. (2) Bearer
`b64token`의 `_`를 선두·중간에 둔 사례를 corpus에 추가해 고정했다(기존 문자군에 `_`가 있었다).
(3) 빈 패턴과 모두 일치 패턴을 음성 경계로 거부하고 CLI가 원격·시나리오 전에 종료하는지 시험했다.
(4) corpus 라벨 25개를 고정해 형식 삭제가 조용히 통과하지 않게 했다. (5) 실제 Git 시험이
임시 인덱스를 쓰며 기본 인덱스를 읽거나 바꾸지 않음을 전후 `ls-files`로 확인하도록 주석과 검사를
고쳤다. (6) `assertNotIn(json.dumps(...))` 대신 스냅샷 전체의 패턴 일치 수가 0인지 검사한다.

Fix round 2는 남은 차단 지적을 반영했다. 자격 이름 없는 32/64자리 hex를 음성 사례에서 양성
corpus(`bare-r2-key-32`·`bare-r2-key-64`·`bare-r2-key-json`)로 옮겼다. 사전 검사는 bare 키
패턴이 빠진 규칙을 `missing-format:bare-r2-key-*`로 거부하는 회귀를 추가했고, digest 문맥
음성 사례와 digest 파일이 있는 인계 통과 시험은 그대로 유지한다. Cargo.lock `checksum`·
`sha256:` 로그처럼 이름이 붙은 일반 해시는 계속 비밀로 보지 않는다.

Fix round 3는 round 2의 줄 단위 예외가 만든 차단 지적을 반영했다. 줄 어디에든 digest 이름이
있으면 그 줄의 32/64자리 hex를 모두 건너뛰어, `{"sha256": "<digest>", "value": "<bare-key>"}`
같은 압축 JSON에서 bare 키가 탐지되지 않았다. 이제 digest 예외는 digest 이름에 **바로 대입된
값 하나**에만 적용하며(`core/secret_scan.py`의 `_DIGEST_ASSIGNMENT`가 값 직전의 대입만 본다),
규칙의 bare hex 패턴은 모든 32/64자리 hex를 찾는다. 사전 검사 corpus에 `bare-r2-key-mixed-with-digest`
(29개)를 추가하고, 혼합·역순·두 digest 뒤 bare 키, digest만 있는 값의 음성 경계를 회귀에 넣었다.
인계 시험은 digest와 bare 키가 같은 파일에 있을 때 R-10으로 반송되고 커밋·푸시가 0건인지
검사한다. 정적 비밀값 검사도 같은 `secret_scan` 판정을 쓰므로 digest fixture는 통과하고
혼합 값은 위반으로 남는다.

전체 Python 시험에서 D-04 회귀의 규칙 파일 전체 해시 고정이 이번 변경을 거부했다.
HEAD와 구조적으로 대조해 `preserve_manifest.excludes`·`secret_patterns.patterns`·설명 필드
`_exclude_matching` 외 모든 값이 같은지 확인한 뒤 `o13_unchanged_gates.json`의 해당 파일 해시와
갱신 이유만 수정했다. 다른 결정·작업 게이트·자격·전이·비용 정책은 그대로 대조한다.

패턴 기반 검사이므로 임의 비밀값 전체를 검출한다는 보장은 없다. 자격 이름 없는 32/64자리 hex는
탐지하며, digest 이름에 바로 대입된 값만 일반 해시로 보고 제외한다. digest 이름과 값 사이에 다른
토큰이 끼어 있는 드문 배치나 이름 없이 파일 어딘가에 놓인 일반 해시는 탐지될 수 있다.
`R2_SECRET_ACCESS_KEY=<hex>`처럼 credential 이름이 붙은 값도 탐지한다. 40자리 Git OID와 인접
영숫자에 포함된 부분 문자열은 제외한다.
이번 작업에서 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
실제 원격 시나리오 전체 재실행은 커밋·푸시 금지 범위 때문에 수행하지 않았다.
이 증거는 [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 개발 도구 보강이며,
P01~P19의 전 상품 수집·트윈·소비자 화면·첫 출시 완료 판정을 바꾸지 않는다.
