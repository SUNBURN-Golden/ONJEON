# Audit 6 — 빌더 자격 수명과 리스 만료 연결

노드: `audit6-daemon-credential-ttl-vs-lease` · 2026-11-13.
추적: T-OP-09, [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 개발 도구.

`harness.py`의 자격 TTL은 7,200초인데 리스 TTL은 3,600초다. 기존 pre-receive
hook은 자격 자체의 회수·만료·과제 범위만 검사했다. 따라서 데몬이 tick·재시작으로
만료를 처리하기 전에는 만료된 리스의 빌더가 보유한 자격으로 직접 푸시할 수 있었다.
`issue-credential` 역시 `status=active`만 보고 이미 만료된 리스에 재발급했다.

빌더 쓰기 자격을 등록할 때 원격의 토큰 레코드에 상태 파일·시계 파일 경로를 함께
저장한다. hook은 이 바인딩의 원자적 상태 스냅샷을 읽어 같은 `lease_id`, 활성 상태,
`now < expires_at`을 확인한다. 데몬과 같은 offset 시계를 사용하므로 정리 동작 없이
만료를 거부하고, 하트비트 갱신은 현재 만료 시각으로 반영한다. 자격 자체의 실제
시각 기반 TTL·회수·범위 검사도 유지한다. 바인딩 누락, 상태 소실·손상, 잘못된
만료 값·시계는 거부한다. offset 파일 생성 전에는 기존 ClockFile처럼 offset 0을 쓴다.

만료된 리스에는 두 빌더 자격(`builder_write_credential`, `builder_token`)을
새로 발급하지 않는다. 데몬의 `preserve_credential`은 종료·인계 후 작업 보존에
필요한 별도 권한이므로 자격 TTL·회수·과제 범위 검사를 계속 적용한다.
상태 읽기는 원자적 rename 스냅샷을 사용한다. 트랜잭션 안에서 수행되는 보존
푸시와 잠금이 얽히지 않도록 hook에서 상태 저장소의 잠금을 잡지 않는다.

[실행 증거와 재현 명령](../../../tools/evidence/audit6-daemon-credential-ttl-vs-lease/README.md)에
수정 전 실패, 새 회귀, 실행기 전체·프로젝트 시험 결과를 기록한다. 새 시험은
실제 로컬 bare 원격의 거부·ref 불변·로그 사유를 확인한다. 실제 Git 호스트의
토큰 API·보호 설정 검증이나 상주 데몬 가동·P01~P19·첫 출시 완료 증거는 아니다.
