/* Fresh company bootstrap and native opening controls; no direct database writes. */
const { start } = require('./harness.cjs');

(async () => {
  const previewOnly = process.argv.includes('--preview-only');
  const h = await start(previewOnly ? 'pending-8-opening-preview' : 'pending-8-opening-access'), { page, resources, assert } = h;
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    const identity = await require('./identity_reader.cjs')(h);
    const accounting = await require('./identity_reader.cjs')(h, 'accounting');
    for (const company of previewOnly ? [] : resources.companies) {
      await h.switchCompany(company);
      await h.test('OPENING-EXISTING-' + company.key, 'Opening access', 'Open retained company opening and inspect native capture authority and state', 'Finance management is available; existing finalized history remains protected', async () => {
        const base = '/v1/companies/' + company.id + '/opening-batches';
        const metadata = await accounting(base + '/workspaces/field-set'); assert.equal(metadata.status, 200);
        assert(Object.values(metadata.body.capture_permissions.journal_lines).some(Boolean), 'Opening capture still has no writable fields');
        const readiness = await accounting(base + '/readiness'); assert.equal(readiness.status, 200);
        await h.ready('/accounting/opening');
        await page.getByRole('heading', { name: 'Account and party openings', exact: true }).waitFor();
        assert.equal(await page.getByText('You have read access. A user with finance management access must save, prepare and finalize the opening.', { exact: true }).count(), 0);
        if (readiness.body.status === 'FINALIZED') assert.equal(readiness.body.can_prepare, false);
        await h.capture('opening-existing-' + company.key);
        return 'Native capture fields writable; opening status ' + readiness.body.status + '; finalized safeguards retained';
      }, 'LIVE_UI_WITH_API_READBACK');
    }
    const previewCompany = resources.companies[0]; await h.switchCompany(previewCompany);
    await h.test('OPENING-NATIVE-PREVIEW-' + previewCompany.key, 'Opening preview', 'Capture two balanced test lines through UI, validate native preview, then discard without saving', 'Native finance authority enables scoped capture and exact balanced preview without posting money', async () => {
      const base = '/v1/companies/' + previewCompany.id;
      const accounts = await accounting(base + '/accounts?limit=200'); assert.equal(accounts.status, 200);
      const cash = accounts.body.items.find(row => row.kind === 'CASH' && row.status === 'ACTIVE');
      const capital = accounts.body.items.find(row => row.kind === 'GENERAL' && row.status === 'ACTIVE' && (row.code === 'RETAINED_EARNINGS' || /capital/i.test(row.name)));
      assert(cash && capital, 'Active bootstrap cash/capital accounts required');
      await h.ready('/accounting/opening');
      await page.getByRole('textbox', { name: 'Opening source and reason', exact: true }).fill('QA preview only; discard balanced test values without saving');
      await page.getByRole('button', { name: 'Next step', exact: true }).click();
      for (const [account, side] of [[cash, 'DEBIT'], [capital, 'CREDIT']]) {
        await page.getByRole('button', { name: 'Add account balance', exact: true }).click();
        const lookup = page.getByRole('combobox', { name: 'Ledger account', exact: true }); await lookup.fill(account.code);
        await page.getByRole('option').filter({ hasText: account.name }).first().click({ timeout: 90000 });
        await page.getByRole('combobox', { name: 'Balance side', exact: true }).selectOption(side);
        await page.getByRole('textbox', { name: 'Opening amount', exact: true }).fill('100.0000');
        await page.getByRole('button', { name: 'Keep account line', exact: true }).click();
        await page.getByRole('textbox', { name: 'Opening amount', exact: true }).waitFor({ state: 'hidden' });
      }
      await page.getByRole('button', { name: 'Next step', exact: true }).click();
      const pending = page.waitForResponse(r => r.url().endsWith('/api/financial-opening') && r.request().postDataJSON()?.path === base + '/opening-batches/workspaces/preview'); pending.catch(() => {});
      await page.getByRole('button', { name: 'Validate and preview', exact: true }).click(); const response = await pending; assert.equal(response.status(), 200); const result = await response.json();
      assert.equal(result.entry_count, 2); assert.equal(result.journal_count, 1);
      await page.getByRole('status').filter({ hasText: 'Preview passed:' }).first().waitFor();
      assert.equal(await page.getByRole('button', { name: 'Save reviewed opening', exact: true }).isEnabled(), true);
      await h.capture('opening-native-balanced-preview');
      await page.getByRole('button', { name: 'Discard worksheet changes', exact: true }).click();
      return 'Two exact 100.0000 cash/capital test lines passed native preview; reviewed-save enabled; worksheet discarded with no saved declaration or posted effect';
    }, 'LIVE_UI_WITH_API_READBACK');
    if (previewOnly) { if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1; return; }
    const create = await h.test('OPENING-NEW-COMPANY', 'Company bootstrap', 'Create an auxiliary new services company through all wizard steps and allow native bootstrap', 'New active company inherits the same permanent administrator authority and working books', async () => {
      if (resources.openingCompany) {
        const retained = await identity('/v1/companies/' + resources.openingCompany.id); assert.equal(retained.status, 200); assert.equal(retained.body.status, 'active');
        return 'Retained auxiliary opening company reused without creating another company';
      }
      await h.ready('/companies/new');
      const name = 'QA Opening ' + resources.marker.slice(-8);
      await page.getByRole('textbox', { name: 'Legal name', exact: true }).fill(name);
      await page.getByRole('textbox', { name: 'Short name', exact: true }).fill(name);
      async function next(heading) { await page.getByRole('button', { name: 'Next', exact: true }).click(); await page.getByRole('heading', { name: heading, exact: true }).waitFor(); }
      await next('Location and tax');
      await page.getByRole('combobox', { name: 'Country', exact: true }).selectOption('IN');
      await page.getByRole('combobox', { name: 'State', exact: true }).selectOption('IN-MH');
      await next('Money and calendar');
      await page.getByRole('combobox', { name: 'Amount decimals', exact: true }).selectOption('4');
      await page.getByRole('combobox', { name: 'Quantity decimals', exact: true }).selectOption('4');
      await next('What you track');
      const boxes = page.getByRole('checkbox');
      for (let i = await boxes.count() - 1; i >= 0; i--) if (await boxes.nth(i).isChecked()) await boxes.nth(i).locator('..').click();
      await next('Presentation'); await next('Review and create');
      const pending = page.waitForResponse(r => r.url().endsWith('/api/company') && r.request().postDataJSON()?.path === '/v1/companies' && r.request().postDataJSON()?.method === 'POST'); pending.catch(() => {});
      await page.getByRole('button', { name: 'Create this company', exact: true }).click();
      const response = await pending, result = await response.json(); assert.equal(response.status(), 201, result.error?.message);
      resources.openingCompany = { id: result.id, key: 'opening-bootstrap', name, code: result.code }; h.save();
      await page.waitForURL(url => url.pathname === '/companies/' + result.id, { timeout: 180000 });
      const retained = await identity('/v1/companies/' + result.id); assert.equal(retained.status, 200); assert.equal(retained.body.status, 'active');
      return 'Active auxiliary services company created and bootstrapped through UI: ' + result.id;
    }, 'LIVE_UI_WITH_API_READBACK');
    if (create.status !== 'PASS') { process.exitCode = 1; return; }
    const company = resources.openingCompany; await h.switchCompany(company);
    const base = '/v1/companies/' + company.id;
    await h.test('OPENING-NEW-EDITABLE', 'Opening controls', 'Open fresh company worksheet, edit source, add/cancel an account line and reject an empty worksheet; retain finalized protection on reuse', 'Opening capture works; empty balances use explicit zero confirmation', async () => {
      const readiness = await accounting(base + '/opening-batches/readiness'); assert.equal(readiness.status, 200);
      await h.ready('/accounting/opening');
      if (readiness.body.status === 'FINALIZED') return 'Auxiliary zero opening is finalized; historical edit restriction retained on repeat run';
      assert.equal(readiness.body.can_prepare, true, JSON.stringify(readiness.body.blockers));
      const reason = page.getByRole('textbox', { name: 'Opening source and reason', exact: true }); await reason.waitFor(); assert.equal(await reason.isEnabled(), true);
      await reason.fill('QA reviewed empty new-company opening; no migration balances');
      await page.getByRole('button', { name: 'Next step', exact: true }).click();
      const add = page.getByRole('button', { name: 'Add account balance', exact: true }); assert.equal(await add.isEnabled(), true); await add.click();
      assert.equal(await page.getByRole('combobox', { name: 'Ledger account', exact: true }).isEnabled(), true);
      assert.equal(await page.getByRole('textbox', { name: 'Opening amount', exact: true }).isEnabled(), true);
      await page.getByRole('button', { name: 'Cancel', exact: true }).click();
      await page.getByRole('button', { name: 'Next step', exact: true }).click();
      await page.getByRole('button', { name: 'Validate and preview', exact: true }).click();
      await page.getByRole('alert').filter({ hasText: 'Add at least two balanced account lines.' }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Save reviewed opening', exact: true }).isEnabled(), false);
      await h.capture('opening-new-editable-preview');
      await page.getByRole('button', { name: 'Discard worksheet changes', exact: true }).click();
      return 'Editable source and account lookup/amount verified; empty worksheet refused and explicit zero-confirmation path retained';
    }, 'LIVE_UI_WITH_API_READBACK');
    await h.test('OPENING-NEW-ZERO-FINALIZE', 'Opening completion', 'Explicitly confirm empty starting balances through company readiness; replay and inspect native readiness', 'Zero opening finalizes once, without a journal; ordinary fiscal guards remain', async () => {
      const review = await accounting(base + '/financial-setup/zero-opening-review'); assert.equal(review.status, 200);
      if (review.body.blocker === 'OPENING_ALREADY_FINALIZED') return 'Retained finalized zero opening reused; duplicate confirmation not issued';
      assert.equal(review.body.eligible, true, review.body.blocker);
      await h.ready('/settings/readiness');
      await page.getByRole('button', { name: 'Review zero opening', exact: true }).click();
      const pending = page.waitForResponse(r => r.url().endsWith('/api/company') && r.request().postDataJSON()?.path === base + '/financial-setup/confirm-zero-opening'); pending.catch(() => {});
      await page.getByRole('button', { name: 'Confirm zero opening', exact: true }).click(); const response = await pending; assert.equal(response.status(), 201); const row = await response.json();
      assert.equal(row.status, 'FINALIZED'); assert.equal(row.journal_id, null);
      const request = response.request().postDataJSON();
      const replay = await accounting(request.path, request.method, request.body, request.key); assert.equal(replay.status, 201); assert.equal(replay.body.id, row.id);
      resources.openingCompany.zeroOpeningId = row.id; resources.openingCompany.zeroOpeningKey = request.key; h.save();
      const current = await accounting(base + '/opening-batches/readiness'); assert.equal(current.status, 200); assert.equal(current.body.status, 'FINALIZED'); assert.equal(current.body.can_prepare, false);
      await h.capture('opening-new-finalized-zero');
      return 'Native zero opening finalized with one replayed identity and no journal; finalized opening remains protected';
    }, 'LIVE_UI_WITH_API_READBACK');
    await h.switchCompany(resources.companies[0]);
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } finally { h.save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
