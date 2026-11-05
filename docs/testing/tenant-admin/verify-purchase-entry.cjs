/* Native account Purchase preparation; financial/statutory release remains separate. */
const { start } = require('./harness.cjs');
const native = require('./identity_reader.cjs');
const crypto = require('node:crypto');
(async () => {
  const h = await start(process.env.QA_PURCHASE_PHASE || 'pending-13'), { page, assert } = h;
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    const vouchers = await native(h, 'vouchers'), accounting = await native(h, 'accounting'), catalog = await native(h, 'catalog');
    for (const company of h.resources.companies) {
      if (process.env.QA_COMPANY_KEY && company.key !== process.env.QA_COMPANY_KEY) continue;
      await h.switchCompany(company); company.businessKeys ??= {};
      const base = '/v1/companies/' + company.id, stamp = h.resources.marker.slice(-8).toUpperCase();
      // Independent expected totals for the three retained display/rounding profiles.
      const payableTotal = { retail: '42.1200', services: '42.1234', distribution: '42.0000' }[company.key];
      assert(payableTotal, 'The QA rounding expectation must be specified for this profile');
      let supplier, payable, expense;
      const setup = await h.test('P13-SETUP-' + company.key, 'Purchase prerequisites', 'Verify native active supplier/payable/expense and configure an account Purchase type', 'Same-company active source versions and explicit account-bill configuration are available', async () => {
        const party = await accounting(base + '/parties/' + company.supplier); assert.equal(party.status, 200); supplier = party.body; assert.equal(supplier.status, 'ACTIVE');
        const roles = await accounting(base + '/party-roles?party_id=' + supplier.id + '&role=SUPPLIER&limit=50'); assert.equal(roles.status, 200); assert(roles.body.items.some(row => row.party_id === supplier.id && row.role === 'SUPPLIER'), 'Native supplier role is unavailable');
        const accounts = await accounting(base + '/accounts?status=ACTIVE&limit=200'); assert.equal(accounts.status, 200);
        payable = accounts.body.items.find(row => row.kind === 'PARTY' && row.party_id === supplier.id && row.party_role === 'SUPPLIER');
        if (!payable) {
          const groups = await accounting(base + '/account-groups?limit=200'); assert.equal(groups.status, 200);
          const group = groups.body.items.find(row => row.code === 'CREDITORS'); assert(group, 'Starter supplier group is unavailable');
          const code = 'QAPY-' + stamp + '-' + company.key.toUpperCase();
          const prior = await accounting(base + '/accounts?code=' + encodeURIComponent(code) + '&limit=200'); assert.equal(prior.status, 200);
          payable = prior.body.items.find(row => row.code === code);
          if (!payable) {
            company.businessKeys.purchasePayable ??= crypto.randomUUID(); h.save();
            const saved = await accounting(base + '/accounts', 'POST', { code, name: 'QA ' + company.key + ' supplier payable ' + stamp, group_id: group.id, kind: 'PARTY', party_id: supplier.id, party_role: 'SUPPLIER', currency_mode: 'BASE' }, company.businessKeys.purchasePayable);
            assert.equal(saved.status, 201, saved.body.error?.message); payable = saved.body;
          }
          if (payable.status !== 'ACTIVE') {
            const detail = await accounting(base + '/accounts/' + payable.id); assert.equal(detail.status, 200);
            company.businessKeys.purchasePayableActivate ??= crypto.randomUUID(); h.save();
            const active = await accounting(base + '/accounts/' + payable.id + '/activate', 'POST', { expected_version: detail.body.row_version }, company.businessKeys.purchasePayableActivate); assert.equal(active.status, 200, active.body.error?.message); payable = active.body;
          }
        }
        const groups = await accounting(base + '/account-groups?limit=200'); assert.equal(groups.status, 200);
        const expenseGroups = new Set();
        for (const group of groups.body.items) {
          const head = await accounting(base + '/account-heads/' + group.head_id); assert.equal(head.status, 200);
          if (head.body.nature === 'EXPENSE') expenseGroups.add(group.id);
        }
        const expenseGroup = groups.body.items.find(row => expenseGroups.has(row.id)); assert(expenseGroup, 'Expense account group is unavailable');
        const expenseCode = 'QAPE-' + stamp + '-' + company.key.toUpperCase();
        const priorExpense = await accounting(base + '/accounts?code=' + expenseCode + '&limit=50'); assert.equal(priorExpense.status, 200);
        expense = priorExpense.body.items.find(row => row.code === expenseCode);
        if (!expense) {
          company.businessKeys.purchaseExpense ??= crypto.randomUUID(); h.save();
          const created = await accounting(base + '/accounts', 'POST', {code: expenseCode, name: 'QA untaxed purchase expense ' + company.key + ' ' + stamp, group_id: expenseGroup.id, kind: 'GENERAL', currency_mode: 'BASE'}, company.businessKeys.purchaseExpense);
          assert.equal(created.status, 201, created.body.error?.message); expense = created.body;
        }
        const expenseDetail = await accounting(base + '/accounts/' + expense.id); assert.equal(expenseDetail.status, 200); expense = expenseDetail.body;
        if (expense.status !== 'ACTIVE') {
          company.businessKeys.purchaseExpenseActivate ??= crypto.randomUUID(); h.save();
          const active = await accounting(base + '/accounts/' + expense.id + '/activate', 'POST', {expected_version: expense.row_version}, company.businessKeys.purchaseExpenseActivate); assert.equal(active.status, 200, active.body.error?.message); expense = active.body;
        }
        const defaults = await accounting(base + '/account-tax-defaults?account_id=' + expense.id + '&direction=PURCHASE&limit=50'); assert.equal(defaults.status, 200);
        if (!defaults.body.items.length) {
          const classification = await catalog(base + '/tax-classifications/' + company.taxClassification); assert.equal(classification.status, 200);
          company.businessKeys.purchaseExpenseDefault ??= crypto.randomUUID(); h.save();
          const created = await accounting(base + '/account-tax-defaults', 'POST', {account_id: expense.id, direction: 'PURCHASE', supply_kind: classification.body.code_system === 'SAC' ? 'SERVICE' : 'GOODS', code_system: classification.body.code_system, code: classification.body.code, treatment: 'NON_GST', itc_eligibility: 'INELIGIBLE', valid_from: '2026-10-29'}, company.businessKeys.purchaseExpenseDefault);
          assert.equal(created.status, 201, created.body.error?.message);
        } else {
          assert(defaults.body.items.every(row => row.treatment === 'NON_GST'), 'Synthetic expense must remain explicitly untaxed');
        }
        if (!company.purchaseType) {
          const code = 'QAPU-' + stamp + '-' + company.key.toUpperCase();
          const prior = await vouchers(base + '/voucher-types?kind=PURCHASE&limit=200'); assert.equal(prior.status, 200); let type = prior.body.items.find(row => row.code === code);
          if (!type) {
            company.businessKeys.purchaseType ??= crypto.randomUUID(); h.save();
            const created = await vouchers(base + '/voucher-types', 'POST', { code, name: 'QA ' + company.key + ' account purchase ' + stamp, kind: 'PURCHASE', profile: 'STANDARD', policy: { schema_version: 2, allowed_modes: ['ACCOUNTS'], default_mode: 'ACCOUNTS', allowed_party_roles: ['SUPPLIER'], supplier_reference_required: true, approval_required: true, self_approval_allowed: false, invoice: { allowed_supply_kinds: ['ACCOUNT'] } } }, company.businessKeys.purchaseType);
            assert.equal(created.status, 201, created.body.error?.message); type = created.body;
          }
          company.purchaseType = type.id; h.save();
        }
        const type = await vouchers(base + '/voucher-types/' + company.purchaseType); assert.equal(type.status, 200); assert.equal(type.body.status, 'ACTIVE'); assert.equal(type.body.kind, 'PURCHASE');
        return 'Active supplier/payable/general expense and native Purchase ACCOUNT policy; execution flags unchanged';
      }, 'LIVE_AUTHENTICATED_API');
      if (setup.status !== 'PASS') continue;
      const draft = await h.test('P13-DRAFT-' + company.key, 'Purchase entry', 'Select native type/supplier/payable/expense; reject zero; save exact invoice, replay and reload', 'Single native untaxed account draft retains exact amounts and verified source versions', async () => {
        if (company.purchaseVoucher) {
          const old = await vouchers(base + '/vouchers/' + company.purchaseVoucher); assert.equal(old.status, 200); assert.equal(old.body.kind, 'PURCHASE'); assert.equal(old.body.invoice.supplies[0].amount, '42.1234');
          if (old.body.status === 'DRAFT' && (old.body.invoice.supplies[0].account_id !== expense.id || old.body.invoice.supplier_declared_total !== payableTotal)) {
            const content = Object.fromEntries(['type_revision_id','class_id','document_date','posting_date','stock_date','statutory_date','credit_terms_date','mode','currency','narration','lines','parties','references','attachments','links','assignments','counter','custom_fields','invoice'].filter(key => old.body[key] !== undefined).map(key => [key, old.body[key]]));
            content.invoice = {...content.invoice, supplier_declared_total: payableTotal, accepted_calculation_hash: null, supplies: content.invoice.supplies.map(line => ({...line, account_id: expense.id, account_version: expense.row_version}))};
            company.businessKeys.purchaseFixtureRevision ??= crypto.randomUUID(); h.save();
            const revised = await vouchers(base + '/vouchers/' + old.body.id, 'PUT', {expected_version: old.body.row_version, reason: 'Correct synthetic untaxed expense and configured rounded total', content}, company.businessKeys.purchaseFixtureRevision); assert.equal(revised.status, 200, revised.body.error?.message);
          }
          await h.ready('/vouchers/' + old.body.id); return 'Retained Purchase readback; any old QA expense/declared-total fixture corrected through the native revision API, without duplicate creation';
        }
        await h.ready('/vouchers/new/purchase'); await page.getByRole('heading', { name: 'New purchase', exact: true }).waitFor();
        const load = page.getByRole('button', { name: 'Load voucher types', exact: true });
        await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onClick === 'function'), await load.elementHandle(), { timeout: 90000 });
        await load.click(); await page.getByRole('combobox', { name: 'Voucher type', exact: true }).selectOption(company.purchaseType);
        const date = new Date().toISOString().slice(0, 10); await page.getByLabel('Document date', { exact: true }).fill(date); await page.getByRole('button', { name: 'Load entry fields', exact: true }).click();
        await page.getByRole('heading', { name: 'Account purchase bill', exact: true }).waitFor();
        async function select(label, row) {
          const control = page.getByRole('combobox', { name: label, exact: true }); await control.fill(row.code ?? row.name); await page.getByRole('option').filter({ hasText: row.name }).first().click();
          await page.getByRole('button', { name: 'Save draft', exact: true }).waitFor({ state: 'visible' });
          await assertEventuallyEnabled(page.getByRole('button', { name: 'Save draft', exact: true }));
        }
        async function assertEventuallyEnabled(control) { await control.evaluate(el => new Promise((resolve, reject) => { const start = Date.now(); const check = () => { if (!el.disabled) resolve(); else if (Date.now() - start > 30000) reject(new Error('Purchase reference verification did not finish')); else setTimeout(check, 50); }; check(); })); }
        await select('Supplier', supplier); await select('Supplier payable account', payable);
        await page.getByLabel('Supplier invoice reference', { exact: true }).fill('QAP-' + stamp + '-' + company.key);
        await page.getByLabel('Payment due date', { exact: true }).fill(date); await page.getByRole('button', { name: 'Add purchase line', exact: true }).click(); await select('Expense account 1', expense);
        await page.getByLabel('Purchase description 1', { exact: true }).fill('Synthetic QA account purchase'); await page.getByLabel('Purchase amount 1 (INR)', { exact: true }).fill('0');
        await page.getByRole('button', { name: 'Save draft', exact: true }).click(); await page.getByText(/enter a positive amount with at most four decimal places/).waitFor();
        await page.getByLabel('Purchase amount 1 (INR)', { exact: true }).fill('42.1234'); await page.getByLabel('Supplier-declared total (INR)', { exact: true }).fill(payableTotal);
        const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/vouchers' && r.request().postDataJSON()?.method === 'POST'); pending.catch(() => {});
        await page.getByRole('button', { name: 'Save draft', exact: true }).click(); const response = await pending; assert.equal(response.status(), 201, (await response.json()).error?.message);
        const saved = await response.json(), input = response.request().postDataJSON(); company.purchaseVoucher = saved.id; h.save();
        const replay = await h.call('product-fields', 'vouchers', base + '/vouchers', 'POST', input.body, input.key); assert.equal(replay.status, 201); assert.equal(replay.body.id, saved.id);
        const detail = await vouchers(base + '/vouchers/' + saved.id); assert.equal(detail.status, 200); assert.equal(detail.body.status, 'DRAFT'); assert.equal(detail.body.invoice.supplies[0].amount, '42.1234'); assert.equal(detail.body.invoice.party_account_id, payable.id); assert.equal(detail.body.invoice.tax.profile, 'UNTAXED_ACCOUNT');
        await h.capture('purchase-entry-' + company.key); return 'INR 42.1234 native account Purchase saved/replayed once; zero amount refused; supplier/payable/source versions verified';
      }, 'LIVE_UI_WITH_API_READBACK');
      if (draft.status !== 'PASS') continue;
      await h.test('P13-SUBMIT-' + company.key, 'Purchase invoice workflow', 'Preview, accept and submit through UI; attempt self approval and inspect retained native revision', 'Authoritative calculation agrees; submission succeeds; self approval is refused without state change', async () => {
        let detail = await vouchers(base + '/vouchers/' + company.purchaseVoucher); assert.equal(detail.status, 200);
        await h.ready('/vouchers/' + detail.body.id); const refresh = page.getByRole('button', { name: 'Refresh voucher', exact: true });
        await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onClick === 'function'), await refresh.elementHandle(), { timeout: 90000 }); await refresh.click(); await page.getByLabel('Reason', { exact: true }).waitFor();
        if (detail.body.status === 'DRAFT') {
          if (!detail.body.invoice.accepted_calculation_hash) {
            const preview = page.waitForResponse(r => r.request().postDataJSON()?.path === base + '/vouchers/' + detail.body.id + '/invoice-preview'); preview.catch(() => {});
            await page.getByRole('button', { name: 'Preview invoice', exact: true }).click(); const result = await preview; assert.equal(result.status(), 200, (await result.json()).error?.message); assert.equal((await result.json()).payable, payableTotal);
            const accepted = page.waitForResponse(r => r.request().postDataJSON()?.path === base + '/vouchers/' + detail.body.id + '/invoice-acceptance'); accepted.catch(() => {}); await page.getByRole('button', { name: 'Accept calculation', exact: true }).click(); assert.equal((await accepted).status(), 200);
          }
          await page.getByLabel('Reason', { exact: true }).fill('QA account Purchase submission'); const submitted = page.waitForResponse(r => r.request().postDataJSON()?.path === base + '/vouchers/' + detail.body.id + '/submit'); submitted.catch(() => {}); await page.getByRole('button', { name: 'Submit', exact: true }).click(); assert.equal((await submitted).status(), 200);
        }
        detail = await vouchers(base + '/vouchers/' + detail.body.id); assert.equal(detail.body.status, 'SUBMITTED'); assert.match(detail.body.invoice.accepted_calculation_hash, /^[0-9a-f]{64}$/);
        const refused = await vouchers(base + '/vouchers/' + detail.body.id + '/approve', 'POST', { expected_version: detail.body.row_version, reason: 'QA self approval refusal' }); assert.equal(refused.status, 403);
        const after = await vouchers(base + '/vouchers/' + detail.body.id); assert.equal(after.body.row_version, detail.body.row_version); assert.equal(after.body.status, 'SUBMITTED');
        return 'Native exact invoice preview/acceptance and SUBMITTED state; self approval refused; posting/issuance remains gated';
      }, 'LIVE_UI_WITH_API_READBACK');
    }
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } finally { h.save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
