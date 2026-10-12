// 세흐름_시안.html 실행 검증: node run.js <시안.html> <캡처 폴더>
const { chromium } = require('/opt/node-tools/node_modules/playwright');
const path = require('path');
const FILE = 'file://' + path.resolve(process.argv[2]);
const OUT = process.argv[3];
const log = []; let fail = 0;
function check(name, cond, detail) { log.push((cond ? 'PASS ' : 'FAIL ') + name + (detail ? '  [' + detail + ']' : '')); if (!cond) fail++; }
(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const page = await browser.newPage({ viewport: { width: 1360, height: 1000 }, deviceScaleFactor: 2 });
  const errors = []; page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); }); page.on('pageerror', e => errors.push(String(e)));
  await page.goto(FILE); await page.evaluate(() => document.fonts.ready);
  check('웹 글꼴(IBM Plex Sans KR) 적용', await page.evaluate(() => document.fonts.check('16px "IBM Plex Sans KR"', '가')));
  const txt = async s => (await page.locator(s).innerText()).replace(/\s+/g, ' ').trim();
  const vis = s => page.locator(s).isVisible();
  const y = async s => (await page.locator(s).boundingBox()).y;
  // 겹침·잘림 검사: 화면 밖으로 나가는 요소, 서로 겹치는 블록, 잘린 글자
  const layout = async (label) => {
    const r = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll('.screen').forEach(sc => {
        const sb = sc.getBoundingClientRect();
        sc.querySelectorAll('*').forEach(el => {
          if (el.closest('.scrim') || el.closest('[data-toast]')) return;
          const b = el.getBoundingClientRect(); if (!b.width || !b.height) return;
          if (b.left < sb.left - 1 || b.right > sb.right + 1) out.push(sc.id + ' 밖으로 나감: ' + (el.textContent || el.tagName).trim().slice(0, 20));
          if (el.children.length === 0 && el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== 'visible') out.push(sc.id + ' 잘림: ' + el.textContent.trim().slice(0, 20));
        });
        const kids = [...sc.children].filter(k => getComputedStyle(k).position !== 'absolute' && k.getBoundingClientRect().height > 0);
        for (let i = 1; i < kids.length; i++) { const a = kids[i-1].getBoundingClientRect(), b = kids[i].getBoundingClientRect(); if (b.top < a.bottom - 1) out.push(sc.id + ' 겹침: ' + (kids[i].textContent || '').trim().slice(0, 20)); }
      });
      return out;
    });
    check('겹침·잘림 없음(' + label + ')', r.length === 0, r.slice(0, 5).join(' | '));
  };
  const shot = async (sel, name) => { await page.locator(sel).screenshot({ path: OUT + '/' + name }); log.push('캡처 ' + name); };

  // A: 상황 선택 → 큰 금액 → 가정 조건 → 내역
  const ySeg = await y('#screen-a .seg'), yBig = await y('[data-testid="a-big"]'), yAs = await y('[data-testid="a-assume"]'), yRows = await y('#screen-a [data-a="general"] .rows');
  check('A 순서: 상황 선택 → 금액 → 가정 조건 → 내역', ySeg < yBig && yBig < yAs && yAs < yRows, [ySeg, yBig, yAs, yRows].map(Math.round).join(' < '));
  { const h = (await page.locator('[data-testid="a-assume"]').boundingBox()).height; check('A 가정 조건 한 줄', h <= 44, Math.round(h) + 'px'); }
  check('A 소개 문장 없음', !(await page.locator('#screen-a').innerText()).includes('미리 알아보는 계산이에요'));
  check('A 기본: 5,100만 원', (await txt('[data-testid="a-big"]')) === '5,100만 원');

  // B: 가입금액 의미, 기본계약 기준
  check('B 제목: 가입한 진단 보장', (await txt('[data-testid="b-head"]')) === '가입한 진단 보장');
  check('B 금액 열 이름: 가입금액', (await page.locator('#screen-b .rows-head').first().innerText()).includes('가입금액'));
  check('B 만기 표시: 기본계약 기준', (await txt('[data-testid="b-meta"]')).includes('기본계약 100세 만기'));
  check('B "진단받으면" 표현 없음', !(await page.locator('#screen-b').innerText()).includes('진단받으면'));

  // C 기본
  check('C 기본: 5,100만 원', (await txt('#c-total')) === '5,100만 원');
  check('C 주 행동은 하나', (await page.locator('[data-testid="c-cta"] .primary').count()) === 1 && (await page.locator('[data-testid="c-cta"] .secondary').count()) === 0);
  check('C 납입면제 안내는 보험별 내역 안', (await page.locator('#c-breakdown-body [data-testid="c-waiver-guide"]').count()) === 1);
  await layout('기본 화면');
  await shot('#screen-a', '01_A_기본.png'); await shot('#screen-b', '02_B_기본.png'); await shot('#screen-c', '03_C_기본.png');

  // C: 받은 적 있음 → 시트
  await page.click('#c-yes');
  check('시트 열림', await vis('[data-testid="c-sheet"]'));
  check('시트 열림: 본문은 금액 대신 "확인 중"', !(await vis('#c-number')) && (await txt('[data-testid="c-pending"]')) === '어떤 진단금을 받았는지 확인 중이에요');
  check('시트: 아무것도 안 고르면 완료 비활성', await page.locator('#c-sheet-done').isDisabled());
  check('시트: 비활성 이유 표시', await vis('[data-testid="c-sheet-why"]'));
  check('시트: "어떤 보장인지 모르겠어요" 있음', await vis('#c-sheet .opt[data-opt="unknown"]'));
  await page.click('#c-sheet .opt[data-opt="cancer"]');
  check('암진단 선택: 체크 표시 보임', await page.locator('#c-sheet .opt[data-opt="cancer"] .box svg').evaluate(e => getComputedStyle(e).visibility === 'visible'));
  check('암진단 선택: 체크박스 checked', await page.locator('#c-sheet .opt[data-opt="cancer"] input').isChecked());
  check('암진단 선택: 완료 활성', await page.locator('#c-sheet-done').isEnabled());
  check('암진단 선택: 비활성 이유 숨김', !(await vis('[data-testid="c-sheet-why"]')));
  await layout('시트 열림');
  await shot('#screen-c', '04_C_시트_암진단선택.png');
  await page.click('#c-sheet-done');
  check('완료: 시트 닫힘', !(await vis('[data-testid="c-sheet"]')));
  check('완료: "이전에 받은 보장 1개 반영"', (await txt('#c-summary-text')) === '이전에 받은 보장 1개 반영');
  check('완료: 2,100만 원', (await txt('#c-total')) === '2,100만 원');
  check('완료: 예시 금액 문구', (await txt('#c-lead')) === '이전에 받은 보장을 뺀 예시 금액');
  check('완료: 선택 목록은 본문에 펼쳐지지 않음', !(await vis('#c-sheet .opt[data-opt="cancer"]')));
  await layout('1개 반영');
  await shot('#screen-c', '05_C_완료_1개반영.png');

  // 수정 → 선택 유지 확인 → 해제 → 취소(변경 버림)
  await page.click('#c-edit');
  check('수정: 이전 선택 유지', await page.locator('#c-sheet .opt[data-opt="cancer"] input').isChecked());
  await page.click('#c-sheet .opt[data-opt="cancer"]');
  check('수정: 해제하면 완료 비활성', await page.locator('#c-sheet-done').isDisabled());
  await page.click('#c-sheet-cancel');
  check('취소: 본문은 이전 결과 그대로(1개 반영, 2,100만 원)', (await txt('#c-summary-text')) === '이전에 받은 보장 1개 반영' && (await txt('#c-total')) === '2,100만 원');

  // 수정 → 모르겠어요 → 완료
  await page.click('#c-edit');
  await page.click('#c-sheet .opt[data-opt="renew"]');
  await page.click('#c-sheet .opt[data-opt="unknown"]');
  check('모르겠어요를 고르면 특정 보장 선택이 풀림', !(await page.locator('#c-sheet .opt[data-opt="cancer"] input').isChecked()) && !(await page.locator('#c-sheet .opt[data-opt="renew"] input').isChecked()));
  await page.click('#c-sheet-done');
  check('모르겠어요 완료: 금액 숨김', !(await vis('#c-number')));
  check('모르겠어요 완료: "확인이 필요해요"', (await txt('[data-testid="c-pending"]')) === '어떤 보장을 받았는지 확인이 필요해요');
  check('모르겠어요 완료: 요약 "확인 필요"', (await txt('#c-summary-text')) === '이전에 받은 보장 확인 필요');
  await page.click('#c-breakdown');
  check('모르겠어요 완료: 내역도 "확인 필요"', (await txt('#c-rows [data-row="cancer"] .v')) === '확인 필요');
  await layout('모르겠어요, 내역 펼침');
  await shot('#screen-c', '06_C_모르겠어요.png');
  await page.click('#c-breakdown');

  // 수정 → 특정 보장 고르면 모르겠어요 해제 → 두 개 → 완료
  await page.click('#c-edit');
  await page.click('#c-sheet .opt[data-opt="cancer"]');
  check('특정 보장을 고르면 모르겠어요 해제', !(await page.locator('#c-sheet .opt[data-opt="unknown"] input').isChecked()));
  await page.click('#c-sheet .opt[data-opt="renew"]');
  await page.click('#c-sheet-done');
  check('두 개 반영: 100만 원, "2개 반영"', (await txt('#c-total')) === '100만 원' && (await txt('#c-summary-text')) === '이전에 받은 보장 2개 반영');

  // 처음 질문으로: 없음 경로
  await page.click('#c-edit'); await page.click('#c-sheet .opt[data-opt="cancer"]'); await page.click('#c-sheet .opt[data-opt="renew"]');
  await page.click('#c-sheet-cancel');
  check('취소하면 확정된 2개 반영 유지', (await txt('#c-summary-text')) === '이전에 받은 보장 2개 반영');
  // 새로 열어 처음 상태 시험
  await page.reload(); await page.evaluate(() => document.fonts.ready);
  await page.click('#c-yes'); await page.click('#c-sheet-cancel');
  check('처음 열고 취소: 질문으로 돌아가고 5,100만 원', (await vis('#c-ask')) && (await txt('#c-total')) === '5,100만 원' && (await txt('#c-lead')) === '처음 받는 진단금이라는 조건에서');
  await page.click('#c-no');
  check('받은 적 없음: 요약과 답변 기준 문구', (await txt('#c-summary-text')) === '이전에 받은 진단금 없음(답하신 내용)' && (await txt('#c-lead')) === '확인한 진단과 답하신 내용 기준으로');
  await page.click('#c-edit');
  check('받은 적 없음 수정: 질문으로', await vis('#c-ask'));

  // 시안에서만 연결하지 않은 버튼: 실제 디자인 유지 + 누르면 시안 안내, 상태 변화 없음
  check('C 보험금 청구 준비: 정상 테라코타 주 버튼', await page.locator('[data-testid="c-cta"] .primary').evaluate(e => getComputedStyle(e).backgroundColor === 'rgb(174, 88, 63)' && !e.disabled));
  check('미구현 표시 없음(흐린 비활성 모양·"미구현" 글자)', (await page.locator('.off, .off-tag').count()) === 0 && !(await page.locator('.screen').allInnerTexts()).join(' ').includes('미구현'));
  for (const s of ['a', 'b', 'c']) {
    const n = await page.locator('#screen-' + s + ' [data-proto]').count();
    let ok = 0;
    for (const el of await page.locator('#screen-' + s + ' [data-proto]').all()) {
      if (!(await el.isVisible())) {
        if (s === 'a') await page.click('#screen-a .seg button[data-scen="thyroid"]');
        else { const fold = s === 'b' ? '#b-unknown' : (await el.evaluate(x => !!x.closest('#c-breakdown-body'))) ? '#c-breakdown' : '#c-inputs'; await page.click(fold); }
      }
      const before = await page.evaluate(() => [location.hash, document.getElementById('c-total').textContent, document.getElementById('c-summary-text').textContent]);
      await el.click();
      const toast = page.locator('#screen-' + s + ' [data-toast]');
      const shown = (await toast.isVisible()) && (await toast.innerText()) === '화면 시안이라 아직 연결되지 않았어요.';
      const after = await page.evaluate(() => [location.hash, document.getElementById('c-total').textContent, document.getElementById('c-summary-text').textContent]);
      if (shown && JSON.stringify(before) === JSON.stringify(after)) ok++;
    }
    check('화면 ' + s.toUpperCase() + ' 시안 전용 버튼 ' + n + '개: 누르면 시안 안내, 상태·주소 변화 없음', ok === n, ok + '/' + n);
  }
  await page.click('#screen-a .seg button[data-scen="general"]');
  await page.click('[data-testid="c-cta"] .primary');
  await shot('#screen-c', '07_C_청구준비_시안안내.png');
  for (const f of ['#b-unknown', '#c-breakdown', '#c-inputs']) { if ((await page.getAttribute(f, 'aria-expanded')) === 'true') await page.click(f); }

  // 화면 사이 이동
  await page.click('#screen-a a.primary');
  check('A "실제로 진단받았어요" → C', (await page.evaluate(() => location.hash)) === '#screen-c');
  await page.click('#screen-b a.primary');
  check('B "이런 일이 생기면?" → A', (await page.evaluate(() => location.hash)) === '#screen-a');

  // A 다른 경우
  await page.click('#screen-a .seg button[data-scen="thyroid"]');
  check('A 갑상선암: 특별조건 카드', await vis('#screen-a [data-a="thyroid"] .tint'));
  await layout('A 갑상선암');
  await shot('#screen-a', '11_A_갑상선암.png');
  await page.click('#screen-a .seg button[data-scen="general"]');

  await page.setViewportSize({ width: 390, height: 844 });
  check('390px 폭에서 가로 스크롤 없음', !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));
  check('콘솔 오류 없음', errors.length === 0, errors.join(' | '));
  await browser.close();
  console.log(log.join('\n')); console.log('\n실패 ' + fail + '건');
  process.exit(fail ? 1 : 0);
})();
