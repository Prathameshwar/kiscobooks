/* Actual connected components with mocked owner responses. UI evidence, never authenticated E2E. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const id = n => '10000000-0000-7000-8000-' + String(n).padStart(12, '0'), company = id(1);
const metadata = { native: { properties: Object.fromEntries(['invoice', 'parties', 'references', 'posting_date', 'document_date', 'credit_terms_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])) }, custom: [], configuration: { kind: 'PURCHASE', profile: 'STANDARD', type_revision_id: id(2), policy: { schema_version: 2, allowed_modes: ['ACCOUNTS'], allowed_party_roles: ['SUPPLIER'], invoice: { allowed_supply_kinds: ['ACCOUNT'] } } } };
metadata.native.properties.invoice = { properties: { ...Object.fromEntries(['party_line_key', 'party_account_id', 'party_account_version', 'bill_reference', 'due_date', 'tax', 'supplier_declared_total', 'allocations', 'tenders', 'components'].map(key => [key, {}])), supplies: { items: { properties: Object.fromEntries(['line_key', 'account_id', 'account_version', 'description', 'amount', 'supply_kind'].map(key => [key, {}])) } } } };
Object.assign(metadata.native.properties.invoice.properties, { rounding_account_id: {}, rounding_account_version: {}, supplier_difference_reason: {} });
async function install(page) {
  let saved, writes = [];
  await page.route('**/api/product-fields', async route => {
    const request = route.request().postDataJSON(), url = new URL(request.path, 'http://owner.test'), p = url.pathname;
    let body;
    if (p.endsWith('/voucher-capabilities')) body = { financial_execution: false, invoice_execution: false, kinds: [{ kind: 'PURCHASE', execution_ready: false }] };
    else if (p.endsWith('/voucher-types')) body = { items: [{ id: id(2), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', name: 'QA account purchases' }], page: { next_cursor: null } };
    else if (p.endsWith('/field-set')) body = metadata;
    else if (p.endsWith('/parties')) body = { items: [{ id: id(3), company_id: company, name: 'QA Supplier', code: 'SUP1' }], page: { next_cursor: null } };
    else if (p.endsWith('/parties/' + id(3))) body = { id: id(3), company_id: company, status: 'ACTIVE', row_version: 2, name: 'QA Supplier' };
    else if (p.endsWith('/party-roles')) body = { items: [{ id: id(23), company_id: company, party_id: id(3), role: 'SUPPLIER' }], page: { next_cursor: null } };
    else if (p.endsWith('/accounts')) { const supplier = url.searchParams.get('kind') === 'PARTY'; body = { items: [{ id: id(supplier ? 4 : 7), company_id: company, name: supplier ? 'Supplier payable' : 'Consulting expense' }], page: { next_cursor: null } }; }
    else if (p.endsWith('/accounts/' + id(4))) body = { id: id(4), company_id: company, status: 'ACTIVE', row_version: 3, name: 'Supplier payable', kind: 'PARTY', party_id: id(3), party_role: 'SUPPLIER' };
    else if (p.endsWith('/accounts/' + id(7))) body = { id: id(7), company_id: company, status: 'ACTIVE', row_version: 4, name: 'Consulting expense', kind: 'GENERAL', inventory_affected: false, group_id: id(9), posting_policy: 'MANUAL_ALLOWED' };
    else if (p.endsWith('/account-groups/' + id(9))) body = { id: id(9), company_id: company, head_id: id(10) };
    else if (p.endsWith('/account-heads/' + id(10))) body = { id: id(10), company_id: company, nature: 'EXPENSE' };
    else if (p.endsWith('/invoice-preview')) body = { calculation_hash: 'a'.repeat(64), calculation_version: 1, currency: 'INR', commercial_total: '42.1234', tax_total: '0.0000', charged_tax_total: '0.0000', rounding: '-0.0034', payable: '42.1200', supplier_difference: null, lines: [], components: [], allocations: [], tax_evidence: [] };
    else if (request.method === 'POST' || request.method === 'PUT') {
      writes.push(request);
      if (p.endsWith('/invoice-acceptance')) saved = { ...saved, row_version: saved.row_version + 1, revision_number: saved.revision_number + 1, revision_id: id(32), invoice: { ...saved.invoice, accepted_calculation_hash: request.body.calculation_hash } };
      else saved = { ...(request.body.content ?? request.body), id: id(90), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', status: 'DRAFT', row_version: 1, revision_number: 1, revision_id: id(31), lines: [], attachments: [], links: [], custom_fields: {} };
      body = saved;
    } else if (saved && p.endsWith('/vouchers/' + saved.id)) body = saved;
    else return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Unimplemented review fixture path' } }) });
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return writes;
}
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [], errors = [];
  try {
    for (const theme of ['light', 'dark', 'ledger']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); page.on('pageerror', error => errors.push(error.message));
      const writes = await install(page);
      await page.goto((process.env.PURCHASE_REVIEW_URL || 'http://127.0.0.1:4418') + '/?connected=1&theme=' + theme);
      await page.getByRole('heading', { name: 'New purchase', exact: true }).waitFor();
      assert.equal(await page.getByText('Synthetic examples', { exact: false }).count(), 0);
      await page.getByRole('combobox', { name: 'Supplier', exact: true }).fill('QA'); await page.getByRole('option', { name: /QA Supplier/ }).click();
      await page.getByText('Supplier payable', { exact: true }).waitFor();
      await page.getByRole('combobox', { name: 'Expense / service account, line 1', exact: true }).fill('Consulting'); await page.getByRole('option', { name: /Consulting expense/ }).click();
      await page.getByLabel('Supplier invoice number', { exact: true }).fill('SUP-API-' + theme);
      await page.getByRole('textbox', { name: 'Amount, line 1', exact: true }).fill('42.1234');
      await page.getByRole('checkbox', { name: 'This bill carries no tax', exact: true }).check();
      await page.getByRole('button', { name: 'Save draft', exact: true }).click();
      await page.getByRole('heading', { name: 'Purchase bill · revision 1', exact: true }).waitFor();
      assert.equal(writes[0].body.invoice.supplies[0].amount, '42.1234');
      await page.getByRole('button', { name: 'Calculate saved bill', exact: true }).click(); await page.getByRole('button', { name: 'Accept Accounting calculation', exact: true }).click();
      await page.getByRole('heading', { name: 'Purchase bill · revision 2', exact: true }).waitFor();
      for (const width of [1440, 800, 390]) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
        await page.addScriptTag({ path: path.join(root, '.tools/purchase-ui-audit/axe-4.10.3.min.js') });
        const violations = await page.evaluate(async () => (await window.axe.run(document)).violations.map(v => ({ id: v.id, impact: v.impact })));
        assert.deepEqual(violations, []); assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        results.push({ theme, width, surface: 'saved-account-purchase', violations });
      }
      await page.getByRole('button', { name: 'Edit terms and details', exact: true }).click();
      await page.getByRole('textbox', { name: 'Credit days', exact: true }).fill('45');
      await page.getByRole('button', { name: 'Cancel', exact: true }).click();
      await page.getByRole('button', { name: 'Keep editing details', exact: true }).click();
      await page.getByRole('button', { name: 'Apply bill details', exact: true }).click();
      await page.screenshot({ path: path.join(__dirname, 'connected-' + theme + '-mobile.png'), fullPage: true });
      results.push({ theme, surface: 'native-details-staging', result: 'PASS' });
      await page.close();
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(__dirname, 'ui-review.json'), JSON.stringify({ observed_at: new Date().toISOString(), evidence: 'Actual connected components with mocked owner responses; no authenticated E2E claim', results, errors }, null, 2) + '\n');
    console.log(JSON.stringify({ checks: results.length, runtime_errors: errors.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
