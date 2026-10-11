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
  const fam = await page.evaluate(() => document.fonts.check('16px "IBM Plex Sans KR"', '가'));
  check('웹 글꼴(IBM Plex Sans KR) 적용', fam);
  const txt = s => page.locator(s).innerText();
  const vis = s => page.locator(s).isVisible();
  const shot = async (sel, name) => { await page.locator(sel).screenshot({ path: OUT + '/' + name }); log.push('캡처 ' + name); };

  // 기본 화면
  check('A 기본: 일반 암 5,100만 원', (await txt('#screen-a [data-a="general"] .big')) === '5,100만 원');
  check('B 기본: 아직 모르는 것 접힘', !(await vis('#b-unknown-body')));
  check('C 기본: 5,100만 원', (await txt('#c-total')) === '5,100만 원');
  check('C 기본: 조건 문구', (await txt('#c-lead')) === '처음 받는 진단금이라는 조건에서');
  check('C 기본: 이전 수령 질문 보임', await vis('#c-ask'));
  await shot('#screen-a', '01_A_기본.png'); await shot('#screen-b', '02_B_기본.png'); await shot('#screen-c', '03_C_기본.png');

  // A 전환
  await page.click('#screen-a .seg button[data-scen="thyroid"]');
  check('A 갑상선암: 특별조건 카드 보임', await vis('#screen-a [data-a="thyroid"] .tint'));
  check('A 갑상선암: 일반 암 금액 숨김', !(await vis('#screen-a [data-a="general"]')));
  await shot('#screen-a', '11_A_갑상선암.png');
  await page.click('#screen-a .seg button[data-scen="insitu"]');
  check('A 제자리암 등: 600만 원', (await txt('#screen-a [data-a="insitu"] .big')) === '600만 원');
  await shot('#screen-a', '12_A_제자리암등.png');
  await page.click('#screen-a .seg button[data-scen="general"]');

  // B 펼침
  await page.click('#b-unknown');
  check('B 펼침: 내용 보임', await vis('#b-unknown-body'));
  await shot('#screen-b', '13_B_아직모르는것_펼침.png');
  await page.click('#b-unknown');
  check('B 접힘으로 돌아감', !(await vis('#b-unknown-body')));

  // C 순서: 받은 적 있음 → 선택 → 해제 → 처음으로
  await page.click('#c-yes');
  check('C 받은 적 있음 직후: 금액 숨김', !(await vis('#c-number')));
  check('C 받은 적 있음 직후: "확인 중" 표시', (await txt('[data-testid="c-checking"]')).replace(/\s+/g,' ') === '어떤 진단금을 받았는지 확인 중이에요');
  await shot('#screen-c', '04_C_받은적있음_확인중.png');
  await page.click('#c-answered-yes [data-item="cancer"]');
  await page.click('#c-breakdown');
  check('C 암진단 선택: 2,100만 원', (await txt('#c-total')) === '2,100만 원');
  check('C 암진단 선택: 예시 금액 문구', (await txt('#c-lead')) === '고른 진단금을 뺀 예시 금액');
  check('C 암진단 선택: 칩 눌림', (await page.getAttribute('#c-answered-yes [data-item="cancer"]', 'aria-pressed')) === 'true');
  check('C 암진단 선택: 내역 "이미 받음"', (await txt('#c-rows [data-row="cancer"] .v')) === '이미 받음');
  await shot('#screen-c', '05_C_암진단선택_재계산.png');
  await page.click('#c-answered-yes [data-item="renew"]');
  check('C 갱신형까지 선택: 100만 원', (await txt('#c-total')) === '100만 원');
  await page.click('#c-answered-yes [data-item="renew"]');
  await page.click('#c-answered-yes [data-item="cancer"]');
  check('C 선택 모두 해제: 다시 "확인 중"', (await vis('[data-testid="c-checking"]')) && !(await vis('#c-number')));
  check('C 선택 해제: 내역 원래 금액', (await txt('#c-rows [data-row="cancer"] .v')) === '3,000만 원');
  await page.click('#c-reset');
  check('C 처음으로: 질문 다시 보임', await vis('#c-ask'));
  check('C 처음으로: 5,100만 원', (await txt('#c-total')) === '5,100만 원');
  check('C 처음으로: 조건 문구 원래대로', (await txt('#c-lead')) === '처음 받는 진단금이라는 조건에서');
  // 받은 적 없음 → 고치기
  await page.click('#c-no');
  check('C 받은 적 없음: 답변 기준 문구', (await txt('#c-lead')) === '확인한 진단과 답하신 내용 기준으로');
  check('C 받은 적 없음: 5,100만 원', (await txt('#c-total')) === '5,100만 원');
  await page.click('#c-fix');
  check('C 고치기: 질문으로 돌아감', await vis('#c-ask'));
  await page.click('#c-inputs');
  check('C 계산에 쓴 정보 펼침', await vis('#c-inputs-body'));
  await shot('#screen-c', '14_C_계산에쓴정보_펼침.png');
  await page.click('#c-inputs'); await page.click('#c-breakdown');

  // 미구현 버튼: 표시와 무반응
  for (const s of ['a', 'b', 'c']) {
    const n = await page.locator('#screen-' + s + ' .todo').count();
    const tags = await page.locator('#screen-' + s + ' .todo .todo-tag').count();
    const icon = await page.locator('#screen-' + s + ' .todo.icon-btn').count();
    check('화면 ' + s.toUpperCase() + ' 미구현 버튼 ' + n + '개 모두 표시(점선 + 미구현 글자 또는 아이콘 라벨)', tags + icon === n, '글자 ' + tags + ', 아이콘 ' + icon);
  }
  const before = await page.evaluate(() => [location.hash, document.getElementById('c-total').textContent]);
  for (const el of await page.locator('#screen-c .todo').all()) { if (await el.isVisible()) await el.click({ force: true }); }
  const after = await page.evaluate(() => [location.hash, document.getElementById('c-total').textContent]);
  check('C 미구현 버튼 누름: 상태·주소 변화 없음', JSON.stringify(before) === JSON.stringify(after));

  // 화면 사이 이동
  await page.click('#screen-a a.primary');
  check('A "실제로 진단받았어요" → C', (await page.evaluate(() => location.hash)) === '#screen-c');
  await page.click('#screen-b a.primary');
  check('B "이런 일이 생기면?" → A', (await page.evaluate(() => location.hash)) === '#screen-a');

  // 좁은 화면(390px) 가로 넘침
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check('390px 폭에서 가로 스크롤 없음', !overflow);

  check('콘솔 오류 없음', errors.length === 0, errors.join(' | '));
  await browser.close();
  console.log(log.join('\n')); console.log('\n실패 ' + fail + '건');
  process.exit(fail ? 1 : 0);
})();
