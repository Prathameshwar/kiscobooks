const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const base = process.env.PURCHASE_REVIEW_URL || 'http://127.0.0.1:4418';
const build = path.join(root, '.tools/purchase-ui-production');
const html = fs.readFileSync(path.join(build, 'index.html'), 'utf8');
const asset = html.match(/src="([^\"]+\.js)"/)[1];
const bundle = fs.readFileSync(path.join(build, asset.replace(/^\//, '')));
const round = value => Math.round(value * 10) / 10;
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const count of [1, 50, 200]) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      const started = performance.now();
      await page.goto(base + '/?workflow=NEW&lines=' + count);
      const rate = page.getByRole('textbox', { name: new RegExp(`^Rate, line ${count}$`) });
      await rate.waitFor(); await page.evaluate(() => document.fonts.ready);
      const initialReadyMs = round(performance.now() - started);
      const timings = [];
      for (let index = 0; index < 13; index++) {
        const start = performance.now();
        await rate.fill(String(126 + index));
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        timings.push(round(performance.now() - start));
      }
      assert.equal(await rate.inputValue(), '138');
      const warm = timings.slice(1).sort((a, b) => a - b), p95 = warm[Math.ceil(warm.length * 0.95) - 1];
      results.push({ lines: count, initialReadyMs, firstEditMs: timings[0], warmSamplesMs: timings.slice(1), warmMedianMs: warm[Math.floor(warm.length / 2)], warmP95Ms: p95, inputCount: await page.locator('input').count(), runtimeErrors: errors });
      console.log(`${count} lines: ready ${initialReadyMs} ms; warm median ${results.at(-1).warmMedianMs} ms; p95 ${p95} ms`);
      assert.deepEqual(errors, []);
      await page.close();
    }
    fs.writeFileSync(path.join(__dirname, '../phase5/performance.json'), JSON.stringify({ checkedAt: new Date().toISOString(), browser: browser.version(), node: process.version, build: 'Vite 5.4.21 production component harness; React 19.3.0; not the Next production application', asset, sha256: crypto.createHash('sha256').update(bundle).digest('hex'), method: 'Automation fill of the last line rate through two browser animation frames; includes protocol, scrolling and rendering. First edit separate; 12 warm edits per size. Local review budget: warm p95 <= 250 ms, not a product SLO.', viewport: '1440x1000', results }, null, 2) + '\n');
    assert(results.every(result => result.warmP95Ms <= 250), 'Local interaction budget exceeded');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
