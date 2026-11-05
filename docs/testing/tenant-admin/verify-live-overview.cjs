/* Verify the real source-backed overview (figures, cards, period control) and native customer ledger navigation. */
const { start } = require('./harness.cjs');
(async () => {
  const h = await start('pending-14'), { page, assert, resources } = h;
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    const accounting = await require('./identity_reader.cjs')(h, 'accounting');
    for (const company of resources.companies) {
      await h.switchCompany(company);
      await h.test('P14-OVERVIEW-' + company.key, 'Live company overview', 'Open Business overview; compare figures and covered dates with the native source API; refresh the same scoped view', 'Verified balances and posted activity render without sample figures, with explicit source/coverage notices', async () => {
        await h.ready('/');
        await page.getByText('Cash and bank', { exact: true }).waitFor({ timeout: 90000 });
        const result = await h.call('product-fields', 'reports', '/v2/companies/' + company.id + '/overview'); assert.equal(result.status, 200, result.body.error?.message);
        assert.equal(result.body.company_id, company.id);
        for (const amount of Object.values(result.body.totals)) assert.equal(amount, '0.0000');
        for (const side of [result.body.receivables, result.body.payables]) {
          assert.equal(side.net, '0.0000'); assert.equal(side.overdue, '0.0000'); assert.deepEqual(side.parties, []);
          for (const amount of Object.values(side.buckets)) assert.equal(amount, '0.0000');
        }
        assert.deepEqual(result.body.top_expenses, []); assert.equal(result.body.other_expenses, '0.0000');
        assert.equal(result.body.position.length, result.body.series.length);
        assert(result.body.position.every(row => row.cash_and_bank === '0.0000'));
        assert.equal(result.body.earlier_history_unavailable, true);
        await page.getByText(/History from/).waitFor();
        await page.getByText('Nothing posted in this period', { exact: true }).waitFor();
        // no invented figures: nothing about collections at risk, tax coverage or stock appears
        for (const invented of ['Collections at risk', 'Tax & compliance coverage', 'Top customers']) assert.equal(await page.getByText(invented, { exact: true }).count(), 0);
        for (const card of ['Bills by age', 'Who owes you', 'Where money went']) await page.getByRole('heading', { name: card, exact: true }).waitFor();
        const refresh = page.getByRole('button', { name: 'Refresh overview', exact: true });
        const pending = page.waitForResponse(r => r.url().endsWith('/api/product-fields') && r.request().postDataJSON()?.path?.startsWith('/v2/companies/' + company.id + '/overview')); pending.catch(() => {});
        await refresh.click(); assert.equal((await pending).status(), 200);
        await page.getByText('Cash and bank', { exact: true }).waitFor();
        // the period control re-reads the same scoped view for a preset range and records it in the URL
        const period = page.getByRole('combobox', { name: 'Period', exact: true }); await period.waitFor();
        const month = page.waitForResponse(r => r.url().endsWith('/api/product-fields') && /date_from=/.test(r.request().postDataJSON()?.path ?? '')); month.catch(() => {});
        await period.selectOption('month'); assert.equal((await month).status(), 200);
        await page.waitForURL(url => url.searchParams.get('period') === 'month');
        await page.getByText('Cash and bank', { exact: true }).waitFor();
        await h.capture('live-overview-' + company.key);
        return 'Native zero-effect balances/activity from ' + result.body.generation_id + '; coverage ' + result.body.date_from + ' to ' + result.body.date_to + '; source/refreshed dates and history limitation visible';
      }, 'LIVE_UI_WITH_API_READBACK');
      await h.test('P14-CUSTOMER-' + company.key, 'Native customer lookup', 'Search a real customer by code and follow the offered customer ledger link', 'Lookup uses current scoped Accounting customers and opens their party ledger', async () => {
        await h.ready('/');
        const rows = await accounting('/v1/companies/' + company.id + '/parties?role=CUSTOMER&status=ACTIVE&limit=50'); assert.equal(rows.status, 200);
        const customer = rows.body.items.find(row => row.name && row.code); assert(customer, 'Retained active QA customer required');
        const lookup = page.getByRole('combobox', { name: 'Find customer ledger', exact: true }); await lookup.waitFor({ timeout: 90000 }); await lookup.fill(customer.code);
        await page.getByRole('option').filter({ hasText: customer.name }).first().click({ timeout: 90000 });
        const link = page.getByRole('link', { name: 'Open customer ledger', exact: true }); assert.equal(await link.getAttribute('href'), '/reports/workspace?report=PARTY_LEDGER&party_id=' + customer.id);
        await link.click(); await page.waitForURL(url => url.pathname === '/reports/workspace' && url.searchParams.get('party_id') === customer.id);
        await page.getByRole('heading', { name: 'Report settings', exact: true }).waitFor();
        assert.equal(await page.getByLabel('Report', { exact: true }).inputValue(), 'PARTY_LEDGER');
        await page.getByRole('heading', { level: 1 }).waitFor();
        assert(!/Application error|Internal Server Error/.test(await page.getByRole('main').innerText()));
        await h.capture('live-customer-ledger-' + company.key);
        return 'Actual customer ' + customer.id + ' selected by native scoped lookup; scoped party ledger opened; no run created';
      }, 'LIVE_UI_WITH_API_READBACK');
    }
    await h.switchCompany(resources.companies[0]);
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } finally { h.save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
