#!/usr/bin/env node
/* 영어 모드에서 '번역되지 않고 남은 한글'을 화면별로 찾는 개발용 점검 도구.
 *
 * 사용법 (저장소 루트에서):
 *   (cd docs && python3 -m http.server 8765 &)          # 정적 서버
 *   npm i -D playwright && npx playwright install chromium   # 최초 1회
 *   node tools/i18n_sweep.js http://localhost:8765 en     # 영어 모드 점검 (ko 도 가능)
 *
 * - GitHub API 는 빈 목록으로 대체하고, 대시보드는 docs/data/*.json(저장소 데이터)으로 그린다.
 * - 결과의 '(hidden)' 은 접힌 패널/숨은 탭이다. 데이터에서 온 자유 문장(판단 근거·소송 요지 등)은
 *   번역 대상이 아니므로 남아 있는 것이 정상이며, 화면 문구(UI)만 사전(docs/i18n-en.js)에 추가한다.
 * - 정적 HTML 의 누락은 `python -m unittest tests.test_i18n` 이 브라우저 없이도 잡는다.
 */
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://localhost:8765";
const LANG = process.argv[3] || "en";
const PAGES = [
  "request", "results", "how",
  "dashboard", "dashboard/stats", "dashboard/litigation", "dashboard/charts", "dashboard/trend",
  "dashboard/table", "dashboard/confidence",
  "paper-request", "paper-results", "paper-dashboard", "paper-how",
];

(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1200, height: 900 } })).newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("https://api.github.com/**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.addInitScript((l) => { try { localStorage.setItem("lang", l); } catch (e) { /* 무시 */ } }, LANG);

  const found = new Map(); // 한글 문자열 → 처음 발견된 화면
  const collect = async (where) => {
    const items = await page.evaluate(() => {
      const HAN = /[가-힣]/, out = [];
      const skip = (el) => el.closest('[translate="no"], script, style');
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) {
        const el = n.parentElement;
        if (!el || !HAN.test(n.nodeValue) || skip(el)) continue;
        const visible = !!(el.offsetParent || el.getClientRects().length);
        out.push([n.nodeValue.replace(/\s+/g, " ").trim(), visible]);
      }
      document.querySelectorAll("[placeholder],[title],[aria-label],[alt]").forEach((el) =>
        ["placeholder", "title", "aria-label", "alt"].forEach((a) => {
          const v = el.getAttribute(a);
          if (v && HAN.test(v) && !skip(el)) out.push([`@${a}: ${v.replace(/\s+/g, " ").trim()}`, true]);
        }));
      return out;
    });
    items.forEach(([k, visible]) => { if (!found.has(k)) found.set(k, where + (visible ? "" : " (hidden)")); });
  };

  await page.goto(`${BASE}/#request`);
  for (const p of PAGES) {
    await page.evaluate((h) => { location.hash = h; }, p);
    await page.waitForTimeout(900);
    await collect(p);
  }
  console.log(`[${LANG}] 한글이 남은 항목: ${found.size} | JS 오류: ${errors.length}`);
  errors.slice(0, 5).forEach((e) => console.log("  JS 오류:", e));
  for (const [k, where] of found) console.log(` - ${where.padEnd(26)} | ${k.slice(0, 140)}`);
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})();
