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
  const ys = [await y('[data-testid="situation"]'), await y('[data-testid="common"]'), await y('.seg'), await y('[data-prod="lotte"]'), await y('[data-testid="diff"]'), await y('[data-testid="price-note"]'), await y('[data-fold="d-lotte"]')];
  check('순서: 상황 → 공통 가정 → 경과 기간 → 금액 → 차이 → 보험료 → 근거', ys.every((v, i) => i === 0 || ys[i-1] < v), ys.map(Math.round).join(' < '));

  // 상품별 금액 또는 이유가 같은 자리(오른쪽 위)에 있는지
  const pos = await page.evaluate(() => [...document.querySelectorAll('.prod')].map(p => { const r = p.getBoundingClientRect(), a = p.querySelector('.pamt').getBoundingClientRect(); return [Math.round(a.right - r.right), Math.round(a.top - r.top)]; }));
  check('세 상품 모두 금액·이유가 같은 자리(오른쪽 위)', pos.length === 3 && pos.every(p => p[0] === pos[0][0] && p[1] === pos[0][1]), JSON.stringify(pos));
  check('대표 결과: 롯데는 지급액 확인 필요, 하나·현대는 약관 기준 계산(24차 사실 정정)', (await txt('[data-testid="kind-lotte"]')) === '이 상황의 지급액 확인 필요' && (await txt('[data-testid="kind-hana"]')) === '약관 기준 계산' && (await txt('[data-testid="kind-hd"]')) === '약관 기준 계산');
  check('큰 금액 자리: 하나 500만 원, 현대 1,000만 원, 롯데는 금액 없음', (await page.locator('[data-prod] .pamt .v').count()) === 2 && (await txt('[data-testid="amt-hana"]')) === '500만 원' && (await txt('[data-testid="amt-hd"]')) === '1,000만 원' && (await page.locator('[data-prod="lotte"] .v').count()) === 0);
  check('하나 계산에 적용 조건(약관)과 가정 표시', (await txt('[data-testid="rule-hana"]')).startsWith('적용한 조건') && (await txt('[data-testid="rule-hana"]')).includes('보험계약일부터 1년 미만이면 50%') && (await txt('[data-testid="apply-hana"]')).includes('실제 계약에서 확인한 것은 아니에요'));
  check('확인 필요 상품(롯데): 이유와 요약서 조건(약관 대조 전 표시, ADR-0014)', (await txt('[data-testid="reason-lotte"]')).includes('약관 별표는 아직 받지 못했어요') && (await txt('[data-testid="rule-lotte"]')).includes('약관과 대조 전') && (await txt('[data-testid="rule-lotte"]')).includes('1회한') && (await txt('[data-testid="rule-lotte"]')).includes('90일'));
  check('확인 필요 표시는 계산 표시와 같은 색(강조색 아님)', await page.evaluate(() => { const c = s => getComputedStyle(document.querySelector(s)).color; return c('[data-testid="kind-lotte"]') === c('[data-testid="kind-hd"]') && c('[data-testid="kind-hana"]') === c('[data-testid="kind-hd"]') && c('[data-testid="kind-lotte"]') === 'rgb(102, 85, 74)'; }));
  check('공통 가정: 약관상 진단 요건을 충족한 최초 진단', (await txt('[data-testid="common-dx"]')) === '약관상 진단 요건을 충족한 최초 진단이라고 가정');
  check('현대 계산에 적용 조건과 "실제 계약에서 확인한 것은 아님"', (await txt('[data-testid="rule-hd"]')).startsWith('적용한 조건') && (await txt('[data-testid="apply-hd"]')).includes('실제 계약에서 확인한 것은 아니에요'));
  check('공통 가정에 가입금액 1,000만 원 맞춤 명시', (await txt('[data-testid="common-amount"]')).includes('가입금액을 1,000만 원으로 맞춤'));

  const all = await page.locator('#screen-cmp').innerText();
  check('"최저가"·"추천" 같은 표시 없음', !/최저가|가장 싼|저렴|추천|1위/.test(all));
  check('"공시에 없음" 표현 없음', !all.includes('공시에 없음'));
  const order = await page.evaluate(() => [...document.querySelectorAll('[data-price]')].map(e => e.getAttribute('data-price')));
  const prodOrder = await page.evaluate(() => [...document.querySelectorAll('[data-prod]')].map(e => e.getAttribute('data-prod')));
  check('보류 상품도 같은 목록, 순서는 가나다(가격순 아님)', JSON.stringify(order) === JSON.stringify(prodOrder) && JSON.stringify(order) === '["lotte","hana","hd"]');
  check('보험료: 직접 비교하지 않고 담보 묶음 예시임을 안내', (await txt('[data-testid="price-note"]')).includes('담보만의 보험료가 아니고'));
  check('보험료마다 "위 보장 구성의 견적이 아님"과 공시 조건', (await page.locator('[data-price] .nq', { hasText: '위 보장 구성의 견적이 아님' }).count()) === 3 && (await page.locator('[data-price] .cond').count()) === 3);
  check('차이는 표가 아니라 항목별 세로 나열', (await page.locator('#screen-cmp table').count()) === 0);
  const items = await page.evaluate(() => [...document.querySelectorAll('[data-item]')].filter(e => e.offsetParent).map(e => [e.getAttribute('data-item'), e.querySelectorAll('.cell').length, [...e.querySelectorAll('.cell')].every(c => /^(공시|약관|요약서)$/.test((c.querySelector('.tag') || {}).textContent || ''))]));
  check('기본으로 보이는 차이: 지급 대상·감액·보장 시작, 항목마다 세 상품과 출처 꼬리표', JSON.stringify(items) === JSON.stringify([['target',3,true],['reduce',3,true],['start',3,true]]), JSON.stringify(items));
  check('출처와 적용 구분 안내', (await txt('[data-testid="legend"]')).includes('출처'));
  check('근거·전체 조건 접힘이 기본', (await page.locator('.detail:visible').count()) === 0 && !(await vis('#d-more')));
  await layout('기본');
  await shot('01_비교_기본.png');

  // 경과 기간 2년
  await page.click('[data-elapsed="2y"]');
  check('2년: 버튼 상태', (await page.getAttribute('[data-elapsed="2y"]', 'aria-pressed')) === 'true' && (await page.getAttribute('[data-elapsed="8m"]', 'aria-pressed')) === 'false');
  check('2년: 진단일 2028.8.20', (await txt('#dates')).includes('2028.8.20'));
  check('2년: 하나 1,000만 원, 롯데는 여전히 금액 없음', (await txt('[data-testid="amt-hana"]')) === '1,000만 원' && (await page.locator('[data-prod="lotte"] .v').count()) === 0);
  check('2년: 감액 규칙은 남고 "해당 없음"(기준일이 약관으로 확인됨)', (await txt('[data-testid="rule-hana"]')).includes('보험계약일부터 1년 미만이면 50%') && (await txt('[data-testid="apply-hana"]')).includes('해당 없어요'));
  check('2년: 현대해상 그대로 1,000만 원', (await txt('[data-testid="amt-hd"]')) === '1,000만 원');
  await layout('2년');
  await shot('02_비교_2년.png');
  await page.click('[data-elapsed="8m"]');
  check('8개월로 되돌림: 진단일·하나 500만 원 복귀', (await txt('#dates')).includes('2027.4.20') && (await txt('[data-testid="amt-hana"]')) === '500만 원' && (await txt('[data-testid="apply-hana"]')).includes('50%를 적용했어요'));

  // 근거 펼침
  for (const id of ['d-more', 'd-lotte', 'd-hana', 'd-hd']) {
    await page.click('[data-fold="' + id + '"]');
    check(id + ' 펼침', (await vis('#' + id)) && (await page.getAttribute('[data-fold="' + id + '"]', 'aria-expanded')) === 'true');
  }
  check('전체 조건: 갱신·따로 보는 암·지급 횟수', (await page.locator('#d-more [data-item]').count()) === 3);
  check('하나 근거: 약관 조항(별표1 C16, 별표12)과 계산 전제', (await txt('[data-testid="hana-terms"]')).includes('C16') && (await txt('[data-testid="hana-terms"]')).includes('별표12') && (await page.locator('#d-hana dt', { hasText: '계산 전제(가정)' }).count()) === 1);
  check('현대 근거에 계산 전제(가정)', (await page.locator('#d-hd dt', { hasText: '계산 전제(가정)' }).count()) === 1);
  check('근거마다 출처 있음', (await page.locator('.detail dt', { hasText: '출처' }).count()) === 3);
  await layout('근거 펼침');
  await page.click('[data-fold="d-lotte"]'); await page.click('[data-fold="d-hana"]');
  check('접기', !(await vis('#d-lotte')) && !(await vis('#d-hana')) && (await vis('#d-hd')) && (await vis('#d-more')));
  await shot('03_비교_전체조건_현대해상_근거.png');
  await page.click('[data-fold="d-hd"]'); await page.click('[data-fold="d-more"]');

  // 시안 전용 버튼
  const protos = await page.locator('[data-proto]').all(); let ok = 0;
  for (const el of protos) {
    const before = await page.evaluate(() => [location.href, document.getElementById('dates').textContent]);
    await el.click();
    const t = page.locator('[data-toast]');
    const shown = (await t.isVisible()) && (await t.innerText()) === '화면 시안이라 아직 연결되지 않았어요.';
    const after = await page.evaluate(() => [location.href, document.getElementById('dates').textContent]);
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
