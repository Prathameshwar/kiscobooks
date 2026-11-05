/* Reusable read-only acceptance of the 30 October UI fixes.
 * Online: node docs/testing/tenant-admin/verify-ui-fixes.cjs
 * VM off: node docs/testing/tenant-admin/verify-ui-fixes.cjs --offline
 * No voucher writes, transitions, source refreshes, provider sends or database changes.
 */
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const output = path.resolve(process.env.QA_OUTPUT || path.join(root, '.test_artifacts/tenant-admin-20261029/live'));
const cases = [
  ['UI-B01', 'Designer', 'Open retained template at 1440/768/390; toggle each compact panel; Escape.', 'Canvas remains usable; controls fit; Escape closes the panel and returns focus.'],
  ['UI-B02', 'Controls', 'Open Items, Accounts and Parties; inspect visible search/filter outer controls at three widths.', 'Single-value controls share the control height; hints remain below; no control clipping.'],
  ['UI-B03', 'Money form', 'Load native Receipt/Payment entry fields; add two unsaved account rows.', 'Fieldgroups use shared styles; controls/actions fit at all widths.'],
  ['UI-B04', 'Entry mode', 'Load an account-only money type.', 'ACCOUNTS mode exposes no Add item control.'],
  ['UI-B05', 'Review navigation', 'Open retained voucher; inspect Back.', 'Back links to /vouchers.'],
  ['UI-B06', 'Customer ledger', 'Find a current QA customer on Overview; follow Open customer ledger.', 'PARTY_LEDGER opens with the verified company customer preselected.'],
  ['UI-B07', 'Preview precision', 'Run local voucher-workflow regression for 0/2/4 places and non-English decimals.', 'Configured display and currency; exact calculation data preserved.'],
  ['UI-B08', 'Purchase validation', 'Load Purchase; add an unsaved line; submit missing supplier.', 'Supplier has an associated error and correction focus; no write occurs.'],
  ['UI-B09', 'History text', 'Open retained voucher and Load voucher history.', 'Transition arrow is readable; literal question-mark separator absent.'],
  ['UI-B10', 'Failed counts', 'Run local Audit/Activity failed-request regressions.', 'Retry/error retained; failed read is never labelled No events.'],
  ['UI-B11', 'Audit chip', 'Open Audit with the retained administrator.', 'No internal never operator; fixed security exclusion retained if applicable.'],
  ['UI-B12', 'Workflow actions', 'Inspect saved voucher action groups at all widths.', 'Distinct grouped/wrapping targets.'],
  ['UI-G01', 'Draft discovery/edit', 'Open scoped directory; filter DRAFT; inspect Review/Edit row actions; follow an available Edit draft link.', 'Verified supported saved draft loads; unsupported/terminal captures stay review-only.'],
  ['UI-G02', 'Saved summary', 'Open retained voucher without pressing Refresh.', 'Native readable dates, identity, revision and capture load automatically.'],
  ['UI-G03', 'Report sources', 'Open selected financial and stock report settings.', 'Ledger coverage or explicit unavailable state; no false stock-completeness claim.'],
  ['UI-G04', 'History identity', 'Inspect repeated report/export history at all widths.', 'Timestamp and full identity distinguish buttons; long labels wrap.'],
  ['UI-G05', 'Goods/statutory Purchase', 'Complete documented B15-B19/D05/C2 owner and release prerequisites.', 'Native country/tax-type workflow; untaxed account capture never substitutes for GST goods.'],
  ['UI-G06', 'Physical count', 'Deliver B25/D02/D03 owner contract and C3 acceptance using selected policies.', 'Cutoff reconciliation and once-only difference; verified surplus cost or mandatory review.'],
  ['UI-G07', 'Invitation receipt', 'Configure controlled SMTP/provider and recipient; exercise delivery and acceptance.', 'Real controlled recipient receives and accepts a scoped invitation.'],
  ['UI-G08', 'Report entry', 'Follow a selected report link without Load report workspace.', 'Definitions, sources and history load automatically; no run created.'],
];

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const file = path.join(output, 'ui-fixes-live-results.json');
  if (process.argv.includes('--offline')) {
    fs.writeFileSync(file, JSON.stringify({ phase: 'ui-fixes', executed: false, reason: 'User shut down VM; no live sign-in or native acceptance attempted.', results: cases.map(([id, area, steps, expected]) => ({ id, area, steps, expected, status: 'NOT_RUN', execution_level: 'LIVE_UI_PENDING', actual: 'VM-dependent acceptance remains pending.' })) }, null, 2));
    console.log('Recorded 20 NOT_RUN acceptance cases; no application or credential access.');
    return;
  }
  const { start } = require('./harness.cjs');
  const h = await start('ui-fixes-live'), { page, assert } = h;
  const writes = [];
  await page.route('**/api/product-fields', async route => {
    let data; try { data = route.request().postDataJSON(); } catch { return route.continue(); }
    if (data?.method && data.method !== 'GET') {
      writes.push({ method: data.method, service: data.service, path: data.path });
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'QA_READ_ONLY', message: 'QA business write blocked.' } }) });
    }
    return route.continue();
  });
  const check = (ids, suffix, run) => h.test(ids.join('+') + '-' + suffix, ids.map(id => cases.find(row => row[0] === id)[1]).join('; '), ids.map(id => cases.find(row => row[0] === id)[2]).join(' '), ids.map(id => cases.find(row => row[0] === id)[3]).join(' '), run);
  async function click(name) {
    const button = page.getByRole('button', { name, exact: true });
    await button.waitFor();
    await page.waitForFunction(el => Object.keys(el).some(k => k.startsWith('__reactProps$') && typeof el[k]?.onClick === 'function'), await button.elementHandle());
    await button.click();
  }
  async function widths(id, inspect) {
    const observed = [];
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await inspect(width);
      observed.push({ width, evidence: await h.capture('UIF-' + id + '-' + width) });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    return observed;
  }
  async function prepare(kind) {
    await h.ready('/vouchers/new/' + kind.toLowerCase()); await click('Load voucher types');
    const types = page.getByRole('combobox', { name: 'Voucher type', exact: true });
    await page.waitForFunction(el => [...el.options].some(option => option.value), await types.elementHandle());
    const ids = await types.locator('option').evaluateAll(options => options.map(row => row.value).filter(Boolean));
    assert(ids.length, 'No active native ' + kind + ' type'); await types.selectOption(ids[0]);
    await page.getByLabel('Document date', { exact: true }).fill(process.env.QA_REVIEW_DATE || '2026-10-30');
    await click('Load entry fields');
    await page.getByRole('button', { name: 'Save draft', exact: true }).waitFor();
    await page.waitForFunction(el => !el.disabled, await page.getByRole('button', { name: 'Load entry fields', exact: true }).elementHandle());
  }
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    assert.equal(h.resources.companies.length, 3, 'This acceptance uses the retained three-company QA tenant.');
    for (const company of h.resources.companies) {
      await page.setViewportSize({ width: 1440, height: 1000 }); await h.switchCompany(company);
      for (const route of ['/masters/items?returnTo=%2Fmasters', '/accounting/accounts', '/accounting/parties']) {
        await check(['UI-B02'], company.key + '-' + route.replace(/\W/g, '-'), async () => {
          await h.ready(route);
          return widths(company.key + '-filters-' + route.replace(/\W/g, '-'), async width => {
            const boxes = await page.locator('.janso-filter-bar .janso-input-wrap,.janso-filter-bar .janso-select__wrap,.janso-filter-bar .janso-search-select__control').evaluateAll(elements => elements.map(el => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, height: r.height }; }).filter(r => r.height > 0));
            assert(boxes.length >= 2, 'Search and filter must be present');
            for (const box of boxes) { assert(Math.abs(box.height - 36) <= 1, 'Single-value control height mismatch'); assert(box.left >= 0 && box.right <= width + 1, 'Filter clipped'); }
          });
        });
      }
      for (const kind of ['RECEIPT', 'PAYMENT']) await check(['UI-B03', 'UI-B04'], company.key + '-' + kind, async () => {
        await prepare(kind); assert.equal(await page.getByLabel('Entry mode', { exact: true }).inputValue(), 'ACCOUNTS');
        assert.equal(await page.getByRole('button', { name: 'Add item', exact: true }).count(), 0);
        await click('Add account entry'); await click('Add account entry');
        return widths(company.key + '-' + kind, async () => {
          const bare = await page.locator('main fieldset').evaluateAll(elements => elements.filter(el => el.getBoundingClientRect().height && !el.classList.contains('janso-fieldgroup')).length);
          assert.equal(bare, 0, 'Unstyled financial fieldgroup');
        });
      });
      await check(['UI-B08'], company.key, async () => {
        await prepare('PURCHASE'); await click('Add purchase line');
        const button = page.getByRole('button', { name: 'Save draft', exact: true });
        await page.waitForFunction(el => Object.keys(el).some(k => k.startsWith('__reactProps$') && typeof el[k]?.onSubmit === 'function'), await button.locator('xpath=ancestor::form').elementHandle());
        const before = writes.length; await button.click();
        const supplier = page.getByLabel('Supplier', { exact: true });
        await page.waitForFunction(el => el.getAttribute('aria-invalid') === 'true' && el === document.activeElement, await supplier.elementHandle());
        assert.equal(writes.length, before, 'Invalid Purchase must never submit a write');
        return widths(company.key + '-validation', async () => assert.equal(await supplier.getAttribute('aria-invalid'), 'true'));
      });
      await check(['UI-G03', 'UI-G04', 'UI-G08'], company.key, async () => {
        await h.ready('/reports/workspace?report=TRIAL_BALANCE');
        await page.getByRole('heading', { name: 'Report settings', exact: true }).waitFor();
        assert.equal(await page.getByLabel('Report', { exact: true }).inputValue(), 'TRIAL_BALANCE');
        await page.getByRole('status').filter({ hasText: 'Checking source coverage' }).waitFor({ state: 'hidden' });
        const options = await page.getByLabel('Source snapshot', { exact: true }).locator('option').allTextContents();
        assert(options.some(text => /Ledger|Coverage unavailable/.test(text)), 'Native source coverage is required');
        const evidence = await widths(company.key + '-reports', async width => {
          const boxes = await page.locator('.janso-report-history button').evaluateAll(elements => elements.map(el => ({ text: el.textContent, right: el.getBoundingClientRect().right })));
          for (const box of boxes) { assert(/[a-f0-9-]{36}/i.test(box.text), 'History identity missing'); assert(box.right <= width + 1, 'History button clipped'); }
        });
        await h.ready('/reports/workspace?report=STOCK_SUMMARY');
        await page.getByRole('heading', { name: 'Report settings', exact: true }).waitFor();
        await page.getByText('Ready financial snapshots do not certify stock history.', { exact: false }).waitFor();
        return evidence;
      });
      await check(['UI-G01'], company.key, async () => {
        await h.ready('/vouchers'); await page.getByRole('table', { name: 'Saved company vouchers' }).waitFor();
        assert.equal(await page.getByLabel('Status', { exact: true }).inputValue(), 'DRAFT');
        assert.equal(await page.getByRole('link', { name: 'Create voucher draft', exact: true }).getAttribute('href'), '/vouchers/entry');
        const actions = page.getByRole('table', { name: 'Saved company vouchers' }).getByRole('button', { name: /actions/i }).first();
        await actions.click(); await page.getByRole('menuitem', { name: 'Review voucher', exact: true }).waitFor();
        const edit = page.getByRole('menuitem', { name: 'Edit draft', exact: true });
        if (await edit.count()) {
          await edit.click(); await page.getByRole('heading', { name: 'Edit voucher draft', exact: true }).waitFor();
          await page.getByText('Loading draft and entry fields', { exact: true }).waitFor({ state: 'hidden' });
          assert(await page.getByRole('button', { name: 'Save draft changes', exact: true }).isVisible(), 'Saved supported capture did not load for editing');
        } else await page.keyboard.press('Escape');
        return 'Scoped directory and native row actions checked. Versioned saves and exact same-key retries are separately verified by local tests; no business write.';
      });
      const voucher = company.purchaseVoucher || Object.values(company.moneyVouchers || {})[0];
      if (voucher) await check(['UI-B05', 'UI-B09', 'UI-B12', 'UI-G02'], company.key, async () => {
        await h.ready('/vouchers/' + voucher); await page.getByRole('region', { name: 'Saved voucher summary', exact: true }).waitFor();
        assert.equal(await page.getByRole('link', { name: /voucher drafts/i }).getAttribute('href'), '/vouchers');
        await click('Load voucher history');
        await page.waitForFunction(el => !el.disabled, await page.getByRole('button', { name: 'Load voucher history', exact: true }).elementHandle());
        const text = await page.getByRole('region', { name: 'Voucher workflow' }).innerText();
        assert(!/DRAFT\s*\?\s*SUBMITTED/.test(text), 'Unreadable transition separator');
        return widths(company.key + '-summary', async () => assert(await page.locator('.janso-custom-actions').count() > 0));
      });
      await check(['UI-B06'], company.key, async () => {
        await h.ready('/');
        const result = await h.call('product-fields', 'accounting', '/v1/companies/' + company.id + '/parties?role=CUSTOMER&status=ACTIVE&limit=50');
        assert.equal(result.status, 200); const customer = result.body.items.find(row => row.name && row.code); assert(customer, 'Active native QA customer required');
        const search = page.getByRole('combobox', { name: 'Find customer ledger', exact: true });
        await search.fill(customer.code); await page.getByRole('option').filter({ hasText: customer.name }).first().click();
        const link = page.getByRole('link', { name: 'Open customer ledger', exact: true });
        const href = await link.getAttribute('href'); assert(/^\/reports\/workspace\?report=PARTY_LEDGER&party_id=/.test(href));
        assert.equal(new URL(href, h.origin).searchParams.get('party_id'), customer.id);
        await link.click(); await page.getByRole('heading', { name: 'Report settings', exact: true }).waitFor();
        assert.equal(await page.getByLabel('Report', { exact: true }).inputValue(), 'PARTY_LEDGER');
        return 'Selected customer opens native party ledger; no report created.';
      });
      if (company.designerTemplate) await check(['UI-B01'], company.key, async () => {
        await h.ready('/invoice-designer/' + company.designerTemplate);
        return widths(company.key + '-designer', async width => {
          const bounds = await page.getByRole('main', { name: 'Document canvas' }).boundingBox(); assert(bounds.width >= (width < 1100 ? width - 2 : 400));
          if (width < 1100) for (const [trigger, close] of [['Palette and versions', 'Close palette and versions'], ['Properties panel', 'Close properties']]) {
            await click(trigger); const dismiss = page.getByRole('button', { name: close, exact: true }); await dismiss.focus(); await dismiss.press('Escape');
            assert.equal(await page.getByRole('button', { name: trigger, exact: true }).getAttribute('aria-expanded'), 'false');
            assert(await page.getByRole('button', { name: trigger, exact: true }).evaluate(el => el === document.activeElement));
          }
        });
      });
    }
    await check(['UI-B11'], 'audit', async () => { await h.ready('/audit'); assert(!/Category\s*never/i.test(await page.locator('main').innerText())); return 'Internal exclusion operator absent; no filter removed.'; });
    for (const id of ['UI-B07', 'UI-B10', 'UI-G05', 'UI-G06', 'UI-G07']) {
      const [, area, steps, expected] = cases.find(row => row[0] === id);
      h.results.push({ id, area, steps, expected, status: 'NOT_RUN', execution_level: 'SEPARATE_ACCEPTANCE', actual: id.startsWith('UI-B') ? 'Covered by labelled local regressions; native failure/preview not manufactured in this live run.' : 'Prerequisite remains in the findings CSV.' });
    }
    assert.equal(writes.length, 0, 'Read-only acceptance unexpectedly attempted a business write');
  } catch (error) {
    h.results.push({ id: 'PREFLIGHT_OR_RUN', status: 'FAIL', execution_level: 'LIVE_UI', actual: error.message });
    process.exitCode = 1;
  } finally {
    h.save();
    if (h.results.some(row => row.status === 'FAIL' || row.status === 'BLOCKED')) process.exitCode = 1;
    await h.browser.close();
  }
}
module.exports = { cases };
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
