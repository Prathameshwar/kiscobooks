/* Live hub search/category/card checks, with a real ordinary Cash Book run. */
const { start } = require('./harness.cjs');
(async () => {
  const h = await start('pending-10-11'), { page, assert } = h;
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    const accounting = await require('./identity_reader.cjs')(h, 'accounting');
    for (const company of h.resources.companies) {
      if (process.env.QA_COMPANY_KEY && company.key !== process.env.QA_COMPANY_KEY) continue;
      await h.switchCompany(company);
      for (const [root, code] of [['/reports', 'TRIAL_BALANCE'], ['/books', 'CASH_BOOK']]) {
        await h.test('P' + (root === '/reports' ? '10' : '11') + '-NAV-' + company.key, 'Report/book navigation', 'Discover scoped cards, search/clear the hub, open a category and follow a report card', 'Supported cards retain exact native codes and open the existing company report workspace', async () => {
          await h.ready(root);
          const link = page.locator('main a[href="/reports/workspace?report=' + code + '"]').first(); await link.waitFor({ timeout: 90000 });
          const cards = await page.locator('main a[href^="/reports/workspace?report="]').evaluateAll(links => links.map(link => new URL(link.href).searchParams.get('report')));
          const catalogue = await h.call('product-fields', 'reports', '/v2/companies/' + company.id + '/report-definitions'); assert.equal(catalogue.status, 200);
          assert(cards.every(code => catalogue.body.items.some(item => item.definition.code === code)), 'A card links to a code outside current discovery');
          const search = page.getByRole('searchbox', { name: root === '/reports' ? 'Search reports' : 'Search books', exact: true });
          await search.fill('no matching QA catalogue entry');
          await page.getByText(new RegExp('No ' + (root === '/reports' ? 'reports' : 'books') + ' match your search')).waitFor();
          await search.press('Escape'); await link.waitFor();
          const category = page.locator('main a[href^="' + root + '/"]').filter({ hasNotText: 'workspace' }).first();
          if (await category.count()) { await category.click(); assert(new URL(page.url()).pathname.startsWith(root + '/')); await h.ready(root); }
          await link.click(); assert.equal(new URL(page.url()).searchParams.get('report'), code);
          const load = page.getByRole('button', { name: 'Load report workspace', exact: true }); await load.waitFor();
          await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onClick === 'function'), await load.elementHandle(), { timeout: 90000 });
          await load.click(); await page.getByRole('heading', { name: 'Report settings', exact: true }).waitFor();
          assert.equal(await page.getByRole('combobox', { name: 'Report', exact: true }).inputValue(), code);
          return cards.length + ' permitted hub cards; search/clear and category navigation pass; native ' + code + ' workspace selected';
        });
      }
      await h.test('P11-CASH-BOOK-' + company.key, 'Ordinary financial book', 'Run Cash Book through the offered workspace and read its immutable result', 'Native Cash Book completes for the covered QA date range with zero posted cash effects', async () => {
        const base = '/v2/companies/' + company.id;
        const catalogue = await h.call('product-fields', 'reports', base + '/report-definitions'); assert.equal(catalogue.status, 200);
        const selected = catalogue.body.items.find(row => row.definition.code === 'CASH_BOOK'); assert(selected?.run_enabled);
        const setup = await accounting('/v1/companies/' + company.id + '/financial-setup'); assert.equal(setup.status, 200);
        const sources = await h.call('product-fields', 'reports', base + '/report-generations?limit=50'); assert.equal(sources.status, 200);
        const generation = sources.body.items.find(row => row.status === 'READY'); assert(generation, 'No verified READY source is offered');
        await page.getByRole('combobox', { name: 'Source snapshot', exact: true }).selectOption(generation.id);
        const properties = selected.parameter_schema.properties;
        await page.getByLabel(properties.date_from.title ?? 'date from', { exact: false }).fill(setup.body.books_begin_date);
        await page.getByLabel(properties.date_to.title ?? 'date to', { exact: false }).fill(new Date().toISOString().slice(0, 10));
        const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/report-runs' && r.request().postDataJSON()?.method === 'POST'); pending.catch(() => {});
        await page.getByRole('button', { name: 'Create report', exact: true }).click(); const response = await pending; assert.equal(response.status(), 202); const run = await response.json();
        const deadline = Date.now() + 180000;
        let job;
        do { const result = await h.call('product-fields', 'reports', base + '/report-runs/' + run.id); assert.equal(result.status, 200); job = result.body; assert(!['FAILED', 'BLOCKED', 'CANCELLED'].includes(job.status), job.failure_code); if (job.status !== 'COMPLETE') await new Promise(resolve => setTimeout(resolve, 2000)); } while (job.status !== 'COMPLETE' && Date.now() < deadline);
        assert.equal(job.status, 'COMPLETE');
        const rows = await h.call('product-fields', 'reports', base + '/report-runs/' + run.id + '/rows?limit=50'); assert.equal(rows.status, 200); assert.equal(rows.body.page.next_cursor, null);
        for (const row of rows.body.items) for (const [key, value] of Object.entries(row.data)) if (['debit', 'credit', 'opening', 'closing', 'net', 'amount'].includes(key) && value != null) assert.equal(value, '0.0000');
        await page.getByRole('button', { name: 'Refresh report', exact: true }).click(); await page.getByRole('status').filter({ hasText: 'Report: COMPLETE' }).waitFor();
        await h.capture('cash-book-' + company.key);
        return 'CASH_BOOK COMPLETE; ' + rows.body.items.length + ' authoritative rows; no posted cash effects; source ' + job.generation_id;
      }, 'LIVE_UI_WITH_API_READBACK');
    }
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } finally { h.save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
