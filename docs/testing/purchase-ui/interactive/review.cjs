const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const output = path.join(__dirname, '../phase2');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [name, theme, width, height] of [
      ['desktop-light', 'light', 1440, 1000], ['desktop-dark', 'dark', 1440, 1000], ['desktop-ledger', 'ledger', 1440, 1000],
      ['tablet-light', 'light', 1024, 900], ['mobile-light', 'light', 390, 844], ['empty-light', 'light', 1440, 1000],
    ]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`http://127.0.0.1:4417/?theme=${theme}${name.startsWith('empty') ? '&blank' : ''}`);
      await page.getByRole('heading', { name: 'New purchase', exact: true }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      const measurements = await page.evaluate(() => ({
        viewport: innerWidth, document: document.documentElement.scrollWidth,
        actions: [...document.querySelectorAll('.janso-entry-workspace__actions button')].map(element => ({ text: element.textContent, height: element.getBoundingClientRect().height })),
        scrollableTable: document.querySelector('.janso-entry-grid__scroll').scrollWidth > document.querySelector('.janso-entry-grid__scroll').clientWidth,
        overflowing: [...document.querySelectorAll('*')].filter(element => element.getBoundingClientRect().right > innerWidth + 1).slice(0, 18).map(element => ({ tag: element.tagName, class: element.className, position: getComputedStyle(element).position, width: element.getBoundingClientRect().width, right: element.getBoundingClientRect().right })),
      }));
      await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
      if (measurements.document > width) console.log(JSON.stringify(measurements));
      assert.equal(measurements.document <= width, true, `${name}: page overflows`);
      assert.deepEqual(errors, [], `${name}: runtime errors`);
      if (width === 390) assert(measurements.actions.every(action => action.height >= 44), 'Mobile action target smaller than 44px');
      if (name === 'desktop-light') {
        await page.getByRole('button', { name: 'Review bill', exact: true }).click();
        await page.getByRole('dialog', { name: 'Review purchase bill' }).waitFor();
        await page.screenshot({ path: path.join(output, 'review-light.png'), fullPage: true });
        await page.keyboard.press('Escape');
        assert(await page.getByRole('button', { name: 'Review bill', exact: true }).evaluate(element => element === document.activeElement), 'Review returns focus');
        const rate = page.getByRole('textbox', { name: /^Rate, line 1/ });
        await rate.fill('130'); await rate.blur();
        assert.equal(await page.getByText('₹5,723.00', { exact: true }).count(), 0, 'No stale supplied total after editing');
        await page.getByRole('button', { name: 'Save demo draft', exact: true }).click();
        await page.getByText('Demo draft only', { exact: true }).waitFor();
        await page.screenshot({ path: path.join(output, 'edited-light.png'), fullPage: true });
      }
      results.push({ name, theme, width, height, measurements, runtimeErrors: errors });
      await page.close();
    }
    fs.writeFileSync(path.join(output, 'review.json'), JSON.stringify({ browser: browser.version(), checkedAt: new Date().toISOString(), surface: 'Actual React PurchaseWorkspace in an isolated local component harness; route authorization checked by unit tests.', results }, null, 2) + '\n');
    console.log(`PASS: ${results.length} responsive/theme renders, 8 screenshots, no page overflow or runtime errors; review focus, exact edit invalidation and honest demo action checked.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
