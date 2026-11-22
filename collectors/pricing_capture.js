// Capture a pricing page in its default billing mode and in both toggle states.
// Usage: node collectors/pricing_capture.js <url>  -> one JSON object on stdout.
const { chromium } = require('playwright');

const MONTHLY = /monthly|pay monthly|billed monthly/i;
const YEARLY = /yearly|annual|annually|pay yearly/i;
const SEL = 'button, [role=tab], [role=radio], [role=switch], label, input[type=radio]';
const TOTAL_MS = 45000;

// Describe every toggle-like control: text, selected state, kind.
const scan = () => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll('button, [role=tab], [role=radio], [role=switch], label, input[type=radio]').forEach((el, idx) => {
    let label = el.tagName === 'INPUT' ? ((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label') || el.value || '') : (el.innerText || '');
    label = (label + ' ' + (el.getAttribute('aria-label') || '')).replace(/\s+/g, ' ').trim();
    const cls = (el.className && el.className.toString ? el.className.toString() : '');
    const blob = label + ' ' + cls;
    if (!/monthly|annual|yearly|billed/i.test(blob) || label.length > 80) return;
    const r = el.getBoundingClientRect();
    const visible = r.width > 0 && r.height > 0;
    const selected = el.getAttribute('aria-checked') === 'true' || el.getAttribute('aria-pressed') === 'true' ||
      el.getAttribute('aria-selected') === 'true' || el.checked === true || /(^|[\s_-])(active|selected|checked|current)([\s_-]|$)/i.test(cls);
    const key = label + '|' + el.tagName + '|' + Math.round(r.x) + ',' + Math.round(r.y);
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ idx, tag: el.tagName.toLowerCase(), role: el.getAttribute('role'), text: label, visible, selected,
      cls: cls.slice(0, 80) });
  });
  return out;
};

(async () => {
  const url = process.argv[2];
  const res = { url, final_url: null, default_mode: 'unknown', modes: { default: null, monthly: null, yearly: null },
    toggles_found: [], error: null };
  const t0 = Date.now();
  const left = () => Math.max(1000, TOTAL_MS - (Date.now() - t0));
  let browser;
  try {
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(5000);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: Math.min(30000, left()) });
    await page.waitForTimeout(3500);
    res.final_url = page.url();
    const text = async () => (await page.evaluate(() => document.body.innerText)).replace(/\n{3,}/g, '\n\n');
    res.modes.default = await text();

    let ctrls = await page.evaluate(scan);
    // Plain "Accept" cookie button only when there is no visible billing toggle.
    if (!ctrls.some((c) => c.visible && (MONTHLY.test(c.text) || YEARLY.test(c.text)))) {
      const acc = page.locator('button', { hasText: /^\s*(accept|accept all|accept all cookies)\s*$/i }).first();
      if (await acc.count()) {
        await acc.click({ timeout: 2000 }).catch(() => {});
        await page.waitForTimeout(1000);
        ctrls = await page.evaluate(scan);
      }
    }
    res.toggles_found = ctrls.filter((c) => c.visible).map(({ idx, ...c }) => c);
    const vis = ctrls.filter((c) => c.visible);
    const sel = vis.filter((c) => c.selected);
    const pick = sel.find((c) => YEARLY.test(c.text)) ? 'yearly' : sel.find((c) => MONTHLY.test(c.text)) ? 'monthly' : null;
    if (pick) res.default_mode = pick;

    const handleOf = async (c) => (await page.evaluateHandle((i) => document.querySelectorAll('button, [role=tab], [role=radio], [role=switch], label, input[type=radio]')[i], c.idx)).asElement();
    const clickCtrl = async (c) => {
      const h = await handleOf(c);
      if (!h) return null;
      try {
        await h.scrollIntoViewIfNeeded({ timeout: 2000 });
        await h.click({ timeout: 3000 });
        await page.waitForTimeout(1500);
        return await text();
      } catch (e) { return null; }
    };
    // Separate monthly / yearly controls (tabs, radios, buttons) or one switch whose label names both.
    const short = vis.filter((c) => c.text.length <= 40);
    const pair = (rx, other) => short.filter((c) => rx.test(c.text) && !other.test(c.text));
    // Try each matching control (a hidden radio input may refuse the click; its label works).
    const tryAll = async (list) => {
      for (const c of list) {
        if (Date.now() - t0 > TOTAL_MS - 4000) break;
        const t = await clickCtrl(c);
        if (t) return t;
      }
      return null;
    };
    const mList = pair(MONTHLY, YEARLY), yList = pair(YEARLY, MONTHLY);
    if (mList.length || yList.length) {
      res.modes.monthly = await tryAll(mList);
      res.modes.yearly = await tryAll(yList);
    } else {
      const sw = vis.find((c) => MONTHLY.test(c.text) && YEARLY.test(c.text) && c.text.length <= 120 && c.tag !== 'label');
      if (sw) {
        // One switch: the state after each click is known from the default, so flip it as needed.
        let state = res.default_mode;
        if (state === 'unknown') {
          const m = sw.text.match(/(monthly|annual\w*|yearly)\s+selected/i);
          if (m) state = /month/i.test(m[1]) ? 'monthly' : 'yearly';
        }
        if (state !== 'unknown') {
          res.default_mode = state;
          res.modes[state] = res.modes.default;
          const other = state === 'monthly' ? 'yearly' : 'monthly';
          res.modes[other] = await clickCtrl(sw);
        }
      }
    }
    if (!res.modes.monthly && !res.modes.yearly && !vis.length) res.error = null; // no toggle: default only
  } catch (e) {
    res.error = String(e.message || e).slice(0, 300);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
  console.log(JSON.stringify(res));
})();
