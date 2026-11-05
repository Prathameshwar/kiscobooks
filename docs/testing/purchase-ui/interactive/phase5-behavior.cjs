const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
process.env.PLAYWRIGHT_BROWSERS_PATH ||= path.join(root, '.tools/purchase-ui-browsers');
const { chromium, firefox, webkit } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const output = path.join(__dirname, process.env.PURCHASE_REVIEW_OUTPUT || '../phase5');
fs.mkdirSync(output, { recursive: true });
const base = process.env.PURCHASE_REVIEW_URL || 'http://127.0.0.1:4418';

async function reach(page, target) {
  for (let index = 0; index < 100; index++) {
    if (await target.evaluate(element => element === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  throw Error('Keyboard could not reach ' + await target.getAttribute('aria-label'));
}
async function focusVisible(page) {
  return page.evaluate(() => {
    const target = document.activeElement, rect = target.getBoundingClientRect();
    const overlay = target.closest('[role="dialog"]');
    const footer = (overlay || document).querySelector('.janso-overlay-foot, .janso-entry-workspace__actions');
    return { top: rect.top, bottom: rect.bottom, footer: footer?.getBoundingClientRect().top ?? innerHeight, height: innerHeight };
  });
}
(async () => {
  const results = [];
  for (const channel of (process.env.PURCHASE_REVIEW_BROWSERS || 'msedge,chrome').split(',')) {
    console.log('Checking ' + channel);
    const browser = await (channel === 'firefox' ? firefox : channel === 'webkit' ? webkit : chromium).launch({ ...(channel === 'msedge' || channel === 'chrome' ? { channel } : {}), headless: true });
    const checks = [], errors = [];
    try {
      let page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      const fresh = async (query, width = 1440, height = 1000) => {
        await page.close(); page = await browser.newPage({ viewport: { width, height } });
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(base + '/?' + query);
      };
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(base + '/?workflow=NEW&blank');
      await page.getByRole('heading', { name: 'New purchase', exact: true }).waitFor();
      const supplier = page.getByRole('combobox', { name: 'Supplier', exact: true });
      await reach(page, supplier); await page.keyboard.type('Paper'); await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
      let invoice = page.getByLabel('Supplier invoice number', { exact: true });
      await reach(page, invoice); await page.keyboard.type('KEYBOARD-001');
      await reach(page, page.getByRole('button', { name: 'Accounts / services', exact: true })); await page.keyboard.press('Enter');
      const account = page.getByRole('combobox', { name: /Expense \/ service account, line 1/ });
      await reach(page, account); await page.keyboard.type('Office'); await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
      const amount = page.getByRole('textbox', { name: /Base amount, line 1/ });
      await reach(page, amount); await page.keyboard.type('4200'); await page.keyboard.press('Tab');
      await reach(page, page.getByRole('button', { name: 'Save demo draft', exact: true })); await page.keyboard.press('Enter');
      await page.getByText(/DEMO-LOCAL-1 · revision 1/).waitFor();
      assert.equal(await invoice.inputValue(), 'KEYBOARD-001');
      assert.equal(await amount.inputValue(), '4,200.00');
      checks.push('Keyboard-only blank supplier/account bill saved to the tab adapter; no calculation evidence invented');

      await fresh('workflow=DRAFT'); invoice = page.getByLabel('Supplier invoice number', { exact: true });
      await page.evaluate(() => history.pushState({}, '', location.href + '&step'));
      await invoice.click();
      await invoice.fill('BACK-RETAIN');
      const cancellableBack = await page.evaluate(() => !!window.navigation);
      if (cancellableBack) {
        await page.evaluate(() => history.back());
        await page.getByRole('dialog', { name: 'Leave purchase preview?' }).waitFor();
        await page.getByRole('button', { name: 'Stay with this purchase', exact: true }).click();
        assert.equal(await invoice.inputValue(), 'BACK-RETAIN');
      }
      let dismissedReload = false;
      page.once('dialog', dialog => { assert.equal(dialog.type(), 'beforeunload'); dismissedReload = true; return dialog.dismiss(); });
      await page.reload({ timeout: 5000 }).catch(() => {});
      assert(dismissedReload, 'Native beforeunload was dismissed');
      assert.equal(await invoice.inputValue(), 'BACK-RETAIN');
      checks.push(`${cancellableBack ? 'Real Back cancellation and native reload dismissal' : 'Navigation API unavailable; native reload dismissal'} preserve the dirty draft`);

      await fresh('workflow=NEW&slowlookup&blank');
      const asyncSupplier = page.getByRole('combobox', { name: 'Supplier', exact: true });
      await asyncSupplier.fill('Pa');
      await page.getByText('Searching…', { exact: true }).waitFor();
      await asyncSupplier.fill('North');
      await page.getByRole('option', { name: /Northstar Business Services/ }).waitFor();
      assert.equal(await page.getByRole('option', { name: /Paper & Co/ }).count(), 0);
      await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
      assert.equal(await page.getByLabel('Supplier payable account', { exact: true }).inputValue(), '');
      await asyncSupplier.fill('error'); await page.getByRole('button', { name: 'Try again', exact: true }).waitFor();
      await page.keyboard.press('Enter'); await page.getByText('Searching…', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Try again', exact: true }).waitFor();
      await asyncSupplier.fill('Paper'); await page.getByRole('option', { name: /Paper & Co/ }).waitFor(); await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
      checks.push('Delayed actual supplier lookup, query cancellation, current results, explicit failure/retry and recovery');

      await fresh('workflow=NEW');
      const rate = page.getByRole('textbox', { name: /Rate, line 2$/ });
      await rate.fill('125.12345'); await page.keyboard.press('Tab');
      const focusedBeforeResize = await page.evaluateHandle(() => document.activeElement);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole('button', { name: 'Use line cards', exact: true }).waitFor();
      assert(await focusedBeforeResize.evaluate(element => element === document.activeElement), 'Resize preserves the currently focused field in the retained grid');
      await focusedBeforeResize.dispose();
      assert.equal(await rate.inputValue(), '125.12345');
      assert(await page.getByRole('button', { name: 'Use line cards', exact: true }).isDisabled());
      await rate.fill('125'); await page.keyboard.press('Tab');
      await page.getByRole('button', { name: 'Use line cards', exact: true }).click();
      assert(await page.getByRole('button', { name: 'Edit line 2', exact: true }).evaluate(element => element === document.activeElement));
      await page.keyboard.press('Enter');
      const dialog = page.getByRole('dialog', { name: 'Edit purchase line 2' });
      const description = dialog.getByLabel('Line description', { exact: true });
      await reach(page, description); await page.keyboard.type('MOBILE-STAGED');
      // Allow the drawer's entrance animation and native focus scrolling to finish.
      await page.waitForFunction(() => {
        const active = document.activeElement, rect = active.getBoundingClientRect();
        const footer = active.closest('[role="dialog"]')?.querySelector('.janso-overlay-foot');
        return rect.top >= 0 && rect.bottom <= (footer?.getBoundingClientRect().top ?? innerHeight);
      }, undefined, { timeout: 5000 }).catch(async error => {
        console.error(channel, 'focus geometry', await focusVisible(page));
        await page.screenshot({ path: path.join(output, channel + '-focus-failure.png') });
        throw error;
      });
      const geometry = await focusVisible(page);
      assert(geometry.top >= 0 && geometry.bottom <= geometry.footer, channel + ': focused description must be visible: ' + JSON.stringify(geometry));
      await reach(page, dialog.getByRole('button', { name: 'Apply line', exact: true })); await page.keyboard.press('Enter');
      await page.getByRole('button', { name: 'Edit line 2', exact: true }).click(); assert.equal(await description.inputValue(), 'MOBILE-STAGED');
      await page.keyboard.press('Escape');
      await page.screenshot({ path: path.join(output, channel + '-mobile-cards.png'), animations: 'disabled' });
      checks.push('Invalid raw value survives resize; explicit card switch restores focus; keyboard mobile edit applies once and remains visible');

      await fresh('workflow=DRAFT', 390, 844);
      await page.getByRole('button', { name: 'Review & submit demo', exact: true }).click();
      const review = page.getByRole('dialog', { name: 'Review before demo submission' });
      await reach(page, review.getByRole('region', { name: 'Review before demo submission', exact: true }));
      const before = await review.locator('.janso-overlay-body').evaluate(element => element.scrollTop);
      await page.keyboard.press('PageDown');
      await page.waitForFunction(old => document.querySelector('[role="dialog"] .janso-overlay-body').scrollTop > old, before);
      for (let index = 0; index < 12; index++) { await page.keyboard.press('Tab'); assert(await review.evaluate(element => element.contains(document.activeElement)), 'Focus stays inside review'); }
      await page.keyboard.press('Escape');
      checks.push('Read-only review body is keyboard-scrollable, Tab stays trapped and Escape restores entry');
      assert.deepEqual(errors, []);
      results.push({ channel, browser: browser.version(), checks, runtimeErrors: errors });
      await page.close();
    } finally { await browser.close(); }
  }
  fs.writeFileSync(path.join(output, 'behavior.json'), JSON.stringify({ checkedAt: new Date().toISOString(), surface: base, results }, null, 2) + '\n');
  console.log('PASS: keyboard entry, supported navigation, delayed lookup and compact editing in selected browsers.');
})().catch(error => { console.error(error); process.exitCode = 1; });
