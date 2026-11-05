/* Configure and exercise ordinary Receipt/Payment drafts without financial activation. */
const { start } = require('./harness.cjs');
const native = require('./identity_reader.cjs');
const crypto = require('node:crypto');
(async () => {
  const h = await start(process.env.QA_MONEY_PHASE || 'pending-12'), { page, assert } = h;
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    const vouchers = await native(h, 'vouchers'), accounting = await native(h, 'accounting');
    for (const company of h.resources.companies) {
      if (process.env.QA_COMPANY_KEY && company.key !== process.env.QA_COMPANY_KEY) continue;
      await h.switchCompany(company);
      company.moneyTypes ??= {}; company.moneyVouchers ??= {}; company.businessKeys ??= {};
      const base = '/v1/companies/' + company.id, stamp = h.resources.marker.slice(-8).toUpperCase();
      const accounts = await accounting(base + '/accounts?status=ACTIVE&limit=200'); assert.equal(accounts.status, 200);
      const heads = await accounting(base + '/account-heads?limit=200'); assert.equal(heads.status, 200);
      // Head list items are deliberately lean; nature comes from authorized detail reads.
      for (let index = 0; index < heads.body.items.length; index++) {
        const detail = await accounting(base + '/account-heads/' + heads.body.items[index].id);
        assert.equal(detail.status, 200); heads.body.items[index] = detail.body;
      }
      const groups = await accounting(base + '/account-groups?limit=200'); assert.equal(groups.status, 200);
      const cash = accounts.body.items.find(row => row.kind === 'CASH'); assert(cash, 'Active cash account is missing');
      for (const kind of ['RECEIPT', 'PAYMENT']) {
        const lower = kind.toLowerCase(), nature = kind === 'RECEIPT' ? 'INCOME' : 'EXPENSE';
        let counter = accounts.body.items.find(row => row.kind === 'GENERAL' && heads.body.items.some(head => head.nature === nature && groups.body.items.some(group => group.head_id === head.id && group.id === row.group_id)));
        const configured = await h.test('P12-SETUP-' + company.key + '-' + kind, 'Money entry prerequisites', 'Configure native kind/type and active scoped account prerequisites', 'Explicit ordinary-money policy and active account source versions are available', async () => {
          if (!counter) {
            const group = groups.body.items.find(group => group.status === 'ACTIVE' && heads.body.items.some(head => head.id === group.head_id && head.nature === nature));
            assert(group, 'Active ' + nature.toLowerCase() + ' group is unavailable');
            const code = 'QA' + kind[0] + '-' + stamp + '-' + company.key.toUpperCase();
            const prior = await accounting(base + '/accounts?code=' + encodeURIComponent(code) + '&limit=200'); assert.equal(prior.status, 200);
            counter = prior.body.items.find(row => row.code === code);
            if (!counter) {
              const key = 'moneyAccount' + kind; company.businessKeys[key] ??= crypto.randomUUID(); h.save();
              const saved = await accounting(base + '/accounts', 'POST', { code, name: 'QA ' + company.key + ' ' + nature.toLowerCase() + ' ' + stamp, group_id: group.id, kind: 'GENERAL', currency_mode: 'BASE' }, company.businessKeys[key]);
              assert.equal(saved.status, 201, saved.body.error?.message); counter = saved.body;
            }
            if (counter.status !== 'ACTIVE') {
              const detail = await accounting(base + '/accounts/' + counter.id); assert.equal(detail.status, 200);
              const key = 'moneyAccountActivate' + kind; company.businessKeys[key] ??= crypto.randomUUID(); h.save();
              const active = await accounting(base + '/accounts/' + counter.id + '/activate', 'POST', { expected_version: detail.body.row_version }, company.businessKeys[key]); assert.equal(active.status, 200, active.body.error?.message); counter = active.body;
            }
          }
          if (!company.moneyTypes[kind]) {
            const code = 'QA' + kind.slice(0, 2) + '-' + stamp + '-' + company.key.toUpperCase();
            const prior = await vouchers(base + '/voucher-types?kind=' + kind + '&limit=200'); assert.equal(prior.status, 200);
            let type = prior.body.items.find(row => row.code === code);
            if (!type) {
              const key = 'moneyType' + kind; company.businessKeys[key] ??= crypto.randomUUID(); h.save();
              const created = await vouchers(base + '/voucher-types', 'POST', { code, name: 'QA ' + company.key + ' ' + lower + ' ' + stamp, kind, profile: 'STANDARD', policy: { schema_version: 2, allowed_modes: ['ACCOUNTS'], default_mode: 'ACCOUNTS', approval_required: true, self_approval_allowed: false, money: { allowed_purposes: ['GENERAL'], allowed_tender_modes: ['CASH'], max_tenders: 1 } } }, company.businessKeys[key]);
              assert.equal(created.status, 201, created.body.error?.message); type = created.body;
            }
            company.moneyTypes[kind] = type.id; h.save();
          }
          const type = await vouchers(base + '/voucher-types/' + company.moneyTypes[kind]); assert.equal(type.status, 200); assert.equal(type.body.kind, kind); assert.equal(type.body.status, 'ACTIVE');
          return 'Active ' + kind + ' type and cash/' + nature.toLowerCase() + ' accounts; GENERAL/CASH/one-tender policy; no execution flags changed';
        }, 'LIVE_AUTHENTICATED_API');
        if (configured.status !== 'PASS') continue;
        const entry = await h.test('P12-DRAFT-' + company.key + '-' + kind, 'Receipt/Payment entry', 'Open offered kind; choose scoped type/date/accounts; reject nonpositive input; save, replay and reload exact capture', 'Native draft retains exact amount/source versions and an idempotent single result', async () => {
          if (company.moneyVouchers[kind]) {
            const saved = await vouchers(base + '/vouchers/' + company.moneyVouchers[kind]); assert.equal(saved.status, 200); assert.equal(saved.body.kind, kind); assert.equal(saved.body.financial.accounts[0].amount, '42.1234');
            await h.ready('/vouchers/' + saved.body.id);
            return 'Retained ' + kind + ' draft/submission readback verified without duplicate creation';
          }
          await h.ready('/vouchers/new/' + lower);
          await page.getByRole('heading', { name: 'New ' + lower, exact: true }).waitFor();
          const load = page.getByRole('button', { name: 'Load voucher types', exact: true });
          await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onClick === 'function'), await load.elementHandle(), { timeout: 90000 });
          await load.click(); await page.getByRole('combobox', { name: 'Voucher type', exact: true }).selectOption(company.moneyTypes[kind]);
          const date = new Date().toISOString().slice(0, 10);
          await page.getByLabel('Document date', { exact: true }).fill(date);
          await page.getByRole('button', { name: 'Load entry fields', exact: true }).click();
          await page.getByRole('group', { name: 'Accounts and settlement', exact: true }).waitFor();
          await page.getByRole('button', { name: 'Add account entry', exact: true }).click();
          await page.getByRole('button', { name: 'Add account entry', exact: true }).click();
          const chosen = kind === 'RECEIPT' ? [cash, counter] : [counter, cash];
          for (let index = 0; index < chosen.length; index++) {
            const selector = page.getByRole('combobox', { name: 'Account ' + (index + 1), exact: true });
            await selector.fill(chosen[index].code ?? chosen[index].name); await page.getByRole('option').filter({ hasText: chosen[index].name }).first().click();
            await page.getByLabel('Amount ' + (index + 1), { exact: true }).fill(index ? '42.1234' : '0');
          }
          const cashIndex = kind === 'RECEIPT' ? 1 : 2;
          await page.getByRole('button', { name: 'Add payment detail ' + cashIndex, exact: true }).click();
          const invalid = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/vouchers' && r.request().postDataJSON()?.method === 'POST'); invalid.catch(() => {});
          await page.getByRole('button', { name: 'Save draft', exact: true }).click(); assert.equal((await invalid).status(), 422, 'Nonpositive money must be refused');
          await page.getByLabel('Amount 1', { exact: true }).fill('42.1234');
          await page.getByLabel('Tender amount 1', { exact: true }).fill('42.1234');
          const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/vouchers' && r.request().postDataJSON()?.method === 'POST'); pending.catch(() => {});
          await page.getByRole('button', { name: 'Save draft', exact: true }).click(); const response = await pending; assert.equal(response.status(), 201, (await response.json()).error?.message);
          const saved = await response.json(), input = response.request().postDataJSON(); company.moneyVouchers[kind] = saved.id; h.save();
          const replay = await h.call('product-fields', 'vouchers', base + '/vouchers', 'POST', input.body, input.key); assert.equal(replay.status, 201); assert.equal(replay.body.id, saved.id);
          const detail = await vouchers(base + '/vouchers/' + saved.id); assert.equal(detail.status, 200); assert.equal(detail.body.status, 'DRAFT'); assert.equal(detail.body.kind, kind);
          assert(detail.body.financial.accounts.every(row => row.amount === '42.1234')); assert.equal(detail.body.financial.tenders[0].amount, '42.1234');
          await page.getByRole('button', { name: 'Refresh voucher', exact: true }).click(); await page.getByText('Status: DRAFT', { exact: true }).waitFor();
          await h.capture('money-entry-' + company.key + '-' + kind);
          return 'Balanced INR 42.1234 draft, cash tender and authoritative account versions saved once; nonpositive input refused; native reload/replay verified';
        }, 'LIVE_UI_WITH_API_READBACK');
        if (entry.status !== 'PASS') continue;
        await h.test('P12-SUBMIT-' + company.key + '-' + kind, 'Money workflow', 'Submit retained money draft through UI; attempt self approval; confirm refusal preserves submitted state', 'Submission succeeds; self-approval produces no financial authority or state change', async () => {
          let detail = await vouchers(base + '/vouchers/' + company.moneyVouchers[kind]); assert.equal(detail.status, 200);
          await h.ready('/vouchers/' + detail.body.id);
          const refresh = page.getByRole('button', { name: 'Refresh voucher', exact: true });
          await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onClick === 'function'), await refresh.elementHandle(), { timeout: 90000 });
          await refresh.click();
          if (detail.body.status === 'DRAFT') {
            await page.getByLabel('Reason', { exact: true }).fill('QA ordinary money submission');
            const pending = page.waitForResponse(r => r.request().postDataJSON()?.path === base + '/vouchers/' + detail.body.id + '/submit'); pending.catch(() => {});
            await page.getByRole('button', { name: 'Submit', exact: true }).click(); assert.equal((await pending).status(), 200);
          }
          detail = await vouchers(base + '/vouchers/' + detail.body.id); assert.equal(detail.body.status, 'SUBMITTED');
          const version = detail.body.row_version;
          const refused = await vouchers(base + '/vouchers/' + detail.body.id + '/approve', 'POST', { expected_version: version, reason: 'QA self approval refusal' }); assert.equal(refused.status, 403);
          const after = await vouchers(base + '/vouchers/' + detail.body.id); assert.equal(after.body.status, 'SUBMITTED'); assert.equal(after.body.row_version, version);
          return 'SUBMITTED retained money voucher; self approval refused with unchanged row version; posting remains gated';
        }, 'LIVE_UI_WITH_API_READBACK');
      }
    }
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } finally { h.save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
