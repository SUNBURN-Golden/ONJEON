// 비교_시안.html 실행 검증: node run.js <시안.html> <캡처 폴더>
const { chromium } = require('/opt/node-tools/node_modules/playwright');
const path = require('path');
const FILE = 'file://' + path.resolve(process.argv[2]);
const OUT = process.argv[3];
const log = []; let fail = 0;
function check(name, cond, detail) { log.push((cond ? 'PASS ' : 'FAIL ') + name + (detail ? '  [' + detail + ']' : '')); if (!cond) fail++; }
(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const page = await browser.newPage({ viewport: { width: 1000, height: 1000 }, deviceScaleFactor: 2 });
  const errors = []; page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); }); page.on('pageerror', e => errors.push(String(e)));
  await page.goto(FILE); await page.evaluate(() => document.fonts.ready);
  check('웹 글꼴(IBM Plex Sans KR) 적용', await page.evaluate(() => document.fonts.check('16px "IBM Plex Sans KR"', '가')));
  const txt = async s => (await page.locator(s).innerText()).replace(/\s+/g, ' ').trim();
  const vis = s => page.locator(s).isVisible();
  const y = async s => (await page.locator(s).first().boundingBox()).y;
  const layout = async (label) => {
    const r = await page.evaluate(() => {
      const out = [];
      const sc = document.getElementById('screen-cmp'); const sb = sc.getBoundingClientRect();
      sc.querySelectorAll('*').forEach(el => {
        if (el.closest('[data-toast]')) return;
        const b = el.getBoundingClientRect(); if (!b.width || !b.height) return;
        if (b.left < sb.left - 1 || b.right > sb.right + 1) out.push('밖으로 나감: ' + (el.textContent || el.tagName).trim().slice(0, 20));
        if (el.children.length === 0 && el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== 'visible') out.push('잘림: ' + el.textContent.trim().slice(0, 20));
      });
      const kids = [...sc.children].filter(k => getComputedStyle(k).position !== 'absolute' && k.getBoundingClientRect().height > 0);
      for (let i = 1; i < kids.length; i++) { const a = kids[i-1].getBoundingClientRect(), b = kids[i].getBoundingClientRect(); if (b.top < a.bottom - 1) out.push('겹침: ' + (kids[i].textContent || '').trim().slice(0, 20)); }
      // 상품 행 안에서 이름과 금액이 겹치지 않는지
      document.querySelectorAll('.prod-head').forEach(h => { const a = h.children[0].getBoundingClientRect(), b = h.children[1].getBoundingClientRect(); if (a.right > b.left + 1) out.push('이름·금액 겹침: ' + h.textContent.trim().slice(0, 20)); });
      return out;
    });
    check('겹침·잘림 없음(' + label + ')', r.length === 0, r.slice(0, 5).join(' | '));
  };
  const shot = async (name) => { await page.locator('#screen-cmp').screenshot({ path: OUT + '/' + name }); log.push('캡처 ' + name); };

  // 읽는 순서: 상황 → 공통 가정 → 경과 기간 → 금액 → 차이 → 보험료 → 근거
  const ys = [await y('[data-testid="situation"]'), await y('[data-testid="common"]'), await y('.seg'), await y('[data-prod="lotte"]'), await y('[data-testid="diff"]'), await y('[data-testid="price-note"]'), await y('[data-fold]')];
  check('순서: 상황 → 공통 가정 → 경과 기간 → 금액 → 차이 → 보험료 → 근거', ys.every((v, i) => i === 0 || ys[i-1] < v), ys.map(Math.round).join(' < '));

  // 상품별 금액 또는 이유가 같은 자리(오른쪽 위)에 있는지
  const pos = await page.evaluate(() => [...document.querySelectorAll('.prod')].map(p => { const r = p.getBoundingClientRect(), a = p.querySelector('.pamt').getBoundingClientRect(); return [Math.round(a.right - r.right), Math.round(a.top - r.top)]; }));
  check('세 상품 모두 금액·이유가 같은 자리(오른쪽 위)', pos.length === 3 && pos.every(p => p[0] === pos[0][0] && p[1] === pos[0][1]), JSON.stringify(pos));
  check('금액 자리에 가입금액이 아닌 계산 결과 또는 이유', (await txt('[data-testid="amt-lotte"]')) === '계산 보류' && (await txt('[data-testid="amt-hana"]')) === '500만 원' && (await txt('[data-testid="amt-hd"]')) === '1,000만 원');
  check('계산 보류 상품에 이유 표시', (await page.locator('[data-prod="lotte"] .limit').innerText()).includes('정의가 없어요'));
  check('결과를 바꾸는 조건(50%)이 금액 바로 아래', await vis('[data-testid="limit-hana"]'));

  // 최저가 표시·가격 정렬 없음
  const all = await page.locator('#screen-cmp').innerText();
  check('"최저가"·"가장 싼" 같은 표시 없음', !/최저가|가장 싼|저렴|추천|1위/.test(all));
  const order = await page.evaluate(() => [...document.querySelectorAll('[data-price]')].map(e => e.getAttribute('data-price')));
  const prodOrder = await page.evaluate(() => [...document.querySelectorAll('[data-prod]')].map(e => e.getAttribute('data-prod')));
  check('보험료 순서는 상품 순서(가나다)와 같고 가격순 아님', JSON.stringify(order) === JSON.stringify(prodOrder) && JSON.stringify(order) === '["lotte","hana","hd"]');
  check('보험료 직접 비교하지 않는다는 안내', (await txt('[data-testid="price-note"]')).includes('직접 비교하지 않아요'));
  check('보험료마다 공시 조건 표시', (await page.locator('[data-price] .cond').count()) === 3);
  check('미확인 칸 표시(3칸)', (await page.locator('[data-testid="diff"] td.u').count()) === 3);
  check('근거 접힘이 기본', (await page.locator('.detail:visible').count()) === 0);
  await layout('기본');
  await shot('01_비교_기본.png');

  // 경과 기간 2년
  await page.click('[data-elapsed="2y"]');
  check('2년: 버튼 상태', (await page.getAttribute('[data-elapsed="2y"]', 'aria-pressed')) === 'true' && (await page.getAttribute('[data-elapsed="8m"]', 'aria-pressed')) === 'false');
  check('2년: 진단일 2028.8.20', (await txt('#dates')).includes('2028.8.20'));
  check('2년: 하나손보 1,000만 원', (await txt('[data-testid="amt-hana"]')) === '1,000만 원');
  check('2년: 하나손보 50% 줄 숨김', !(await vis('[data-testid="limit-hana"]')));
  check('2년: 롯데 가정 금액 1,000만 원, 50% 문구 없음', (await txt('[data-testid="branch-lotte"]')) === '일반암에 든다면 공시 문구 기준 1,000만 원');
  check('2년: 현대해상 그대로 1,000만 원', (await txt('[data-testid="amt-hd"]')) === '1,000만 원');
  await layout('2년');
  await shot('02_비교_2년.png');
  await page.click('[data-elapsed="8m"]');
  check('8개월로 되돌림: 500만 원, 50% 줄, 롯데 문구 복귀', (await txt('[data-testid="amt-hana"]')) === '500만 원' && (await vis('[data-testid="limit-hana"]')) && (await txt('[data-testid="branch-lotte"]')) === '일반암에 든다면 공시 문구 기준 500만 원(1년 미만 50%)');

  // 근거 펼침
  for (const id of ['d-lotte', 'd-hana', 'd-hd']) {
    await page.click('[data-fold="' + id + '"]');
    check(id + ' 펼침', (await vis('#' + id)) && (await page.getAttribute('[data-fold="' + id + '"]', 'aria-expanded')) === 'true');
  }
  check('근거마다 출처 있음', (await page.locator('.detail dt', { hasText: '출처' }).count()) === 3);
  await layout('근거 펼침');
  await page.click('[data-fold="d-lotte"]'); await page.click('[data-fold="d-hana"]');
  check('접기', !(await vis('#d-lotte')) && !(await vis('#d-hana')) && (await vis('#d-hd')));
  await shot('03_비교_현대해상_근거.png');
  await page.click('[data-fold="d-hd"]');

  // 시안 전용 버튼
  const protos = await page.locator('[data-proto]').all(); let ok = 0;
  for (const el of protos) {
    const before = await page.evaluate(() => [location.href, document.querySelector('[data-testid="amt-hana"]').textContent]);
    await el.click();
    const t = page.locator('[data-toast]');
    const shown = (await t.isVisible()) && (await t.innerText()) === '화면 시안이라 아직 연결되지 않았어요.';
    const after = await page.evaluate(() => [location.href, document.querySelector('[data-testid="amt-hana"]').textContent]);
    if (shown && JSON.stringify(before) === JSON.stringify(after)) ok++;
  }
  check('시안 전용 버튼 ' + protos.length + '개: 누르면 시안 안내, 상태·주소 변화 없음', ok === protos.length, ok + '/' + protos.length);

  await page.setViewportSize({ width: 390, height: 844 });
  check('390px 폭에서 가로 스크롤 없음', !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));
  await layout('390px 창');
  check('콘솔 오류 없음', errors.length === 0, errors.join(' | '));
  await browser.close();
  console.log(log.join('\n')); console.log('\n실패 ' + fail + '건');
  process.exit(fail ? 1 : 0);
})();
