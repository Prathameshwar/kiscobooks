const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const output = path.join(__dirname, '../phase3');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [name, theme, width, height, scenario, panel] of [
      ['desktop-light', 'light', 1440, 1000, 'goods'],
      ['desktop-dark', 'dark', 1440, 1000, 'goods'],
      ['desktop-ledger', 'ledger', 1440, 1000, 'goods'],
      ['tablet-light', 'light', 1024, 900, 'goods'],
      ['mobile-light', 'light', 390, 844, 'goods'],
      ['empty-light', 'light', 1440, 1000, 'blank'],
      ['components-light', 'light', 1440, 1000, 'goods', 'Discounts & charges'],
      ['tax-recipient-dark', 'dark', 1440, 1000, 'recipient', 'Tax details'],
      ['receipt-light', 'light', 1440, 1000, 'receipt', 'Goods receipt'],
      ['tracking-light', 'light', 1440, 1000, 'tracking', 'Line tracking'],
      ['settlement-ledger', 'ledger', 1440, 1000, 'goods', 'Payment & terms'],
      ['evidence-light', 'light', 1440, 1000, 'goods', 'Supplier bill & attachments'],
      ['components-mobile', 'light', 390, 844, 'goods', 'Discounts & charges'],
      ['receipt-mobile', 'light', 390, 844, 'receipt', 'Goods receipt'],
      ['tracking-mobile-dark', 'dark', 390, 844, 'tracking', 'Line tracking'],
      ['settlement-mobile', 'light', 390, 844, 'goods', 'Payment & terms'],
      ['evidence-mobile', 'light', 390, 844, 'goods', 'Supplier bill & attachments'],
    ]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`http://127.0.0.1:4417/?theme=${theme}&${scenario === 'blank' ? 'blank' : 'scenario=' + scenario}`);
      await page.getByRole('heading', { name: 'New purchase', exact: true }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      if (panel) {
        await page.getByRole('button', { name: new RegExp('^' + panel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click();
        const dialog = page.getByRole('dialog', { name: panel, exact: true });
        await dialog.waitFor();
        if (panel === 'Payment & terms') {
          await dialog.getByLabel('Payment to record', { exact: true }).fill('2000');
          await dialog.getByLabel('Payment account', { exact: true }).selectOption('demo-bank');
          await dialog.getByRole('button', { name: 'Apply details' }).click();
          await page.getByText('₹2,723.00', { exact: true }).waitFor();
          assert.equal(await page.getByText('₹5,723.00', { exact: true }).count(), 2, 'Settlement must retain full bill');
          await page.getByRole('button', { name: /^Payment & terms/ }).click();
        }
        if (panel === 'Goods receipt') {
          await dialog.getByText(/Remaining after all selected slices: 4.0000/).waitFor();
          await dialog.getByText(/Existing receipts will not be received again/).waitFor();
        }
        if (panel === 'Tax details') {
          await dialog.getByText(/Recipient liability · excluded/).waitFor();
          assert.equal(await dialog.locator('input,select,textarea').count(), 0, 'Tax rates read only');
        }
        if (panel === 'Supplier bill & attachments') {
          await dialog.getByLabel('Supplier-declared bill total', { exact: true }).fill('5750');
          await dialog.getByLabel('Supplier-declared bill total', { exact: true }).blur();
          await dialog.getByLabel('Supplier bill attachments', { exact: true }).setInputFiles({
            name: 'supplier-bill.png', mimeType: 'image/png',
            buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=', 'base64'),
          });
          await dialog.getByText(/Selected locally/).waitFor();
          assert.equal(await dialog.getByText(/Uploaded/).count(), 0, 'No uploaded claim');
          await dialog.getByRole('button', { name: 'Preview attachment 1', exact: true }).click();
          const image = page.getByRole('img', { name: 'Selected purchase attachment', exact: true });
          await image.waitFor();
          await image.evaluate(element => element.decode());
          assert.equal(await image.evaluate(element => element.naturalWidth), 1, 'Local image decoded');
          await page.getByRole('button', { name: 'Close preview', exact: true }).click();
        }
      }
      // Visible is not the end of the shared drawer's enter animation.
      await page.locator('[role="dialog"]').evaluateAll(async elements => {
        await Promise.all(elements.flatMap(element => element.getAnimations()).map(animation => animation.finished));
      });
      const measurements = await page.evaluate(() => ({
        viewport: innerWidth, document: document.documentElement.scrollWidth,
        dialogs: [...document.querySelectorAll('[role="dialog"]')].map(element => ({ width: element.clientWidth, scroll: element.scrollWidth })),
        actions: [...document.querySelectorAll('.janso-entry-workspace__actions button')].map(element => element.getBoundingClientRect().height),
      }));
      assert(measurements.document <= width, `${name}: document overflow ${JSON.stringify(measurements)}`);
      assert(measurements.dialogs.every(dialog => dialog.scroll <= dialog.width), `${name}: dialog overflow`);
      if (width === 390) assert(measurements.actions.every(height => height >= 44), 'Mobile actions at least 44px');
      await page.screenshot({ path: path.join(output, name + '.png'), fullPage: !panel, animations: 'disabled' });
      if (panel === 'Discounts & charges') {
        const dialog = page.getByRole('dialog', { name: panel, exact: true });
        if (width === 1440) {
          const payable = await dialog.getByLabel('Component 1 payable treatment', { exact: true }).boundingBox();
          const tax = await dialog.getByLabel('Component 1 tax treatment', { exact: true }).boundingBox();
          assert(Math.abs(payable.y - tax.y) <= 1, 'Paired treatment controls align');
        }
        await dialog.getByLabel('Component 1 value', { exact: true }).fill('200');
        await page.keyboard.press('Escape');
        await page.getByRole('dialog', { name: 'Discard panel changes?', exact: true }).waitFor();
        await page.getByRole('button', { name: 'Discard panel changes', exact: true }).click();
        assert(await page.getByRole('button', { name: /^Discounts & charges/ }).evaluate(element => element === document.activeElement), 'Discard returns focus');
        assert.equal(await page.getByText('₹5,723.00', { exact: true }).count(), 2, 'Cancel retains bill');
      }
      assert.deepEqual(errors, [], `${name}: runtime errors`);
      results.push({ name, theme, width, height, scenario, panel, measurements, runtimeErrors: errors });
      await page.close();
    }
    fs.writeFileSync(path.join(output, 'review.json'), JSON.stringify({ browser: browser.version(), checkedAt: new Date().toISOString(), surface: 'Actual React component harness; synthetic examples; not authenticated API E2E.', results }, null, 2) + '\n');
    console.log(`PASS: ${results.length} renders/screenshots; no document/dialog overflow or runtime errors; receipt residual, settlement separation, local files, read-only tax and dirty cancellation checked.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
