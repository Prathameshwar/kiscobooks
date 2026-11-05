const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const output = path.join(__dirname, '../phase4');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [name, theme, width, height, workflow, action] of [
      ['new-light', 'light', 1440, 1000, 'NEW'],
      ['new-dark', 'dark', 1440, 1000, 'NEW'],
      ['new-ledger', 'ledger', 1440, 1000, 'NEW'],
      ['new-tablet', 'light', 1024, 900, 'NEW'],
      ['new-mobile', 'light', 390, 844, 'NEW'],
      ['empty-light', 'light', 1440, 1000, 'NEW', 'empty'],
      ['review-light', 'light', 1440, 1000, 'DRAFT', 'review'],
      ['submitted-dark', 'dark', 1440, 1000, 'SUBMITTED'],
      ['approved-ledger', 'ledger', 1440, 1000, 'APPROVED'],
      ['rejected-mobile', 'light', 390, 844, 'REJECTED'],
      ['correction-light', 'light', 1440, 1000, 'REJECTED', 'correction'],
      ['uncertain-mobile', 'light', 390, 844, 'NEW', 'uncertain'],
      ['stale-light', 'light', 1440, 1000, 'DRAFT', 'stale'],
      ['master-changed-light', 'light', 1440, 1000, 'MASTER_CHANGED'],
      ['leave-mobile', 'light', 390, 844, 'DRAFT', 'leave'],
    ]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [], checks = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`http://127.0.0.1:4417/?theme=${theme}&workflow=${workflow}${action === 'empty' ? '&blank' : ''}`);
      await page.getByRole('heading', { level: 1 }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      const invoice = page.getByLabel('Supplier invoice number', { exact: true });
      if (['SUBMITTED', 'APPROVED', 'REJECTED'].includes(workflow)) {
        assert(await invoice.isDisabled(), 'Frozen workflow header');
        assert.equal(await page.getByRole('button', { name: 'Save demo draft', exact: true }).count(), 0);
        checks.push('Read-only revision has no save action');
      }
      if (action === 'review') {
        await page.getByRole('button', { name: 'Review & submit demo', exact: true }).click();
        const dialog = page.getByRole('dialog', { name: 'Review before demo submission' });
        await dialog.getByText('₹5,723.00', { exact: true }).waitFor();
        await dialog.getByText('₹4,723.00', { exact: true }).waitFor();
        checks.push('Review shows exact saved revision and separate full bill / remaining');
      }
      if (action === 'correction') {
        await page.getByRole('button', { name: 'Correct purchase', exact: true }).click();
        await page.getByRole('button', { name: 'Create demo correction', exact: true }).click();
        assert(await page.getByLabel('Reason for correction', { exact: true }).evaluate(element => element === document.activeElement));
        await page.getByLabel('Reason for correction', { exact: true }).fill('Correct supplier invoice reference');
        checks.push('Correction requires and focuses a reason');
      }
      if (action === 'uncertain' || action === 'stale') {
        if (action === 'stale') await invoice.fill('PC-261034-mine');
        await page.getByText('Explore workflow examples', { exact: true }).click();
        await page.getByLabel('Next demo command outcome', { exact: true }).selectOption(action === 'stale' ? 'STALE' : 'UNCERTAIN');
        await page.getByRole('button', { name: 'Save demo draft', exact: true }).click();
        if (action === 'uncertain') {
          await page.getByText('Demo result unconfirmed', { exact: true }).waitFor();
          assert(await invoice.isDisabled(), 'Unconfirmed result freezes edits');
          assert(await page.getByRole('button', { name: 'Open workflow example', exact: true }).isDisabled());
          // Collapse fixture controls before capturing the recovery UI.
          await page.getByText('Explore workflow examples', { exact: true }).click();
          checks.push('Unconfirmed command freezes edits and example replacement');
        } else {
          await page.getByRole('button', { name: 'Compare latest demo revision', exact: true }).click();
          await page.getByRole('dialog', { name: 'Compare demo revisions' }).waitFor();
          assert.equal(await invoice.inputValue(), 'PC-261034-mine');
          checks.push('Stale comparison retains local entries');
        }
      }
      if (action === 'leave') {
        await invoice.fill('PC-261034-mine');
        await page.getByRole('link', { name: 'Back to vouchers', exact: true }).click();
        await page.getByRole('dialog', { name: 'Leave purchase preview?' }).waitFor();
      }
      await page.locator('[role="dialog"]').evaluateAll(async elements => {
        await Promise.all(elements.flatMap(element => element.getAnimations()).map(animation => animation.finished));
      });
      const measurements = await page.evaluate(() => ({
        viewport: innerWidth, document: document.documentElement.scrollWidth,
        dialogs: [...document.querySelectorAll('[role="dialog"]')].map(element => ({ width: element.clientWidth, scroll: element.scrollWidth })),
        actions: [...document.querySelectorAll('.janso-entry-workspace__actions button')].map(element => element.getBoundingClientRect().height),
        dialogActions: [...document.querySelectorAll('[role="dialog"] .janso-overlay-foot button')].map(element => element.getBoundingClientRect().height),
      }));
      assert(measurements.document <= width, `${name}: document overflow`);
      assert(measurements.dialogs.every(dialog => dialog.scroll <= dialog.width), `${name}: dialog overflow`);
      if (width === 390) assert(measurements.actions.every(height => height >= 44), 'Mobile actions at least 44px');
      if (width === 390) assert(measurements.dialogActions.every(height => height >= 44), 'Mobile dialog actions at least 44px');
      const modal = await page.getByRole('dialog').count() > 0;
      await page.screenshot({ path: path.join(output, name + '.png'), fullPage: !modal, animations: 'disabled' });
      if (action === 'review') {
        await page.getByRole('button', { name: 'Submit demo for review', exact: true }).click();
        await page.getByText('Submitted · demo', { exact: true }).waitFor();
        assert(await invoice.isDisabled());
        checks.push('Submission transitions to a frozen revision');
      }
      if (action === 'correction') {
        await page.getByRole('button', { name: 'Create demo correction', exact: true }).click();
        await page.getByRole('heading', { name: 'Correct purchase draft', exact: true }).waitFor();
        assert(await invoice.isEnabled());
        await page.getByText(/Corrects DEMO-REJECTED, revision 3/).waitFor();
        checks.push('Separate editable correction retains original lineage');
      }
      if (action === 'uncertain') {
        await page.getByRole('button', { name: 'Recover same demo command', exact: true }).click();
        await page.getByText(/DEMO-LOCAL-1 · revision 1/).waitFor();
        assert(await invoice.isEnabled());
        checks.push('Same-command recovery yields one editable demo record');
      }
      if (action === 'leave') {
        await page.getByRole('button', { name: 'Stay with this purchase', exact: true }).click();
        assert.equal(await invoice.inputValue(), 'PC-261034-mine');
        assert(await page.getByRole('link', { name: 'Back to vouchers' }).evaluate(element => element === document.activeElement));
        checks.push('Cancel leave preserves entries and restores focus');
      }
      if (name === 'new-light') {
        const supported = await page.evaluate(() => !!window.navigation);
        if (supported) {
          await page.evaluate(() => history.pushState({}, '', location.href + '&history-step'));
          await invoice.fill('PC-BACK-TEST');
          await page.evaluate(() => history.back());
          await page.getByRole('dialog', { name: 'Leave purchase preview?' }).waitFor();
          await page.getByRole('button', { name: 'Stay with this purchase', exact: true }).click();
          assert.equal(await invoice.inputValue(), 'PC-BACK-TEST');
          checks.push('Real same-document browser Back is canceled; stay preserves inputs');
        }
        assert(supported, 'Record browser Navigation API coverage');
      }
      assert.deepEqual(errors, [], `${name}: runtime errors`);
      results.push({ name, theme, width, height, workflow, action, measurements, checks, runtimeErrors: errors });
      await page.close();
    }
    fs.writeFileSync(path.join(output, 'review.json'), JSON.stringify({ browser: browser.version(), checkedAt: new Date().toISOString(), surface: 'Actual React workflow component harness; synthetic memory adapter; not authenticated API E2E.', results }, null, 2) + '\n');
    console.log(`PASS: ${results.length} workflow renders/screenshots; no document/dialog overflow or runtime errors; review, correction, uncertainty, conflict, leave cancellation and browser Back checked.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
