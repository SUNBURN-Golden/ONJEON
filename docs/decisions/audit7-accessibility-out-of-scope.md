# Decision: BLUEPRINT §7.2 says accessibility is "not a goal". Confirm that for an insurance app whose users ske

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-18 12:40 KST); reversible.

**Decision:** BLUEPRINT §7.2의 ‘접근성 목표 아님’을 첫 출시의 최소 접근성 기준으로 대체한다. 새 ADR로 첫 출시 모바일 앱과 공개 웹에 세 가지 기준을 적용한다. ① 모바일 시스템 글자 크기와 웹 확대를 200%까지 적용해도 핵심 문구가 잘리지 않고 모든 조작에 도달할 수 있어야 한다. ② 명암 대비는 일반 텍스트 4.5:1, 큰 텍스트와 조작에 필요한 비텍스트 요소 3:1 이상으로 한다. ③ 스크린 리더에서 제목, 버튼 이름·역할·상태, 읽기 순서와 활성화 동작을 확인할 수 있어야 한다. [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/#contrast-minimum) [Flutter 접근성 테스트](https://docs.flutter.dev/ui/accessibility/accessibility-testing) 09의 P19 완료 증거에 실제 화면의 확대·대비·시맨틱 트리 회귀시험과 TalkBack·VoiceOver·웹 스크린 리더 실행 기록을 추가한다. T-UX-01은 고령 참가자를 사전등록하고 P18의 설명·원문 대조 과제 결과를 기록한다.

**Why:** 보험 소비자가 보장·면책·가격 조건을 읽고 약관 원문까지 확인할 수 있어야 09의 P18·P19 목적을 달성할 수 있다. 저장된 Flutter 로그는 네 탭의 360px·1.6배 레이아웃과 예시 배너 라벨 검사를 기록한다(apps/mobile/evidence/test.log:106). 현재 색상 토큰을 재계산한 결과 ‘예시로 둘러보기’ 4.47:1, ‘예시 끝내기’ 4.48:1, ‘확인 필요’ 4.14:1로 모두 일반 텍스트 기준에 미달한다. 탭은 자식 시맨틱을 제외하는데 활성화 콜백이 자식 InkWell에만 있다(apps/mobile/lib/app/shell.dart:139). [Flutter excludeSemantics 문서](https://api.flutter.dev/flutter/widgets/Semantics/excludeSemantics.html) 이번 읽기 전용 검토에서 정적 검증을 실행했다. ADR 반영과 실제 화면 검증은 남아 있으며, 로컬 Flutter SDK가 없어 위젯 시험은 저장 로그로 확인했다.

**Options:** ['현행 제외 결정을 유지하고 고령 참가자 이해도 시험으로 이탈 요인을 조사한다.', '첫 출시 앱과 공개 웹에 글자 확대·명암 대비·스크린 리더 기준을 적용하고 09에 완료 증거를 남긴다. 채택.', '첫 출시 범위에 WCAG 2.2 AA 전 항목 검증을 포함한다.']

**Revisit if:** 실제 화면 시험이나 고령 참가자 확인 회차에서 보장·면책·가격 조건 또는 원문에 도달하지 못하는 문제가 재현되면 출시 전에 해당 경로를 수정하고 재검증한다. 지원 플랫폼이나 사용자 요구가 달라지면 검증 범위를 다시 정한다.
