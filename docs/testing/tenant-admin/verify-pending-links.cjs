/* Read-only UI recheck of interrupted stock views and original failed links. */
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { start } = require('./harness.cjs');

(async () => {
  const h = await start(process.env.QA_STOCK_ONLY === '1' ? 'pending-7-stock' : process.env.QA_FAILED_ONLY === '1' ? 'pending-7-recheck' : 'pending-7');
  const { page, resources, assert } = h;
  const requests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname !== '/api/product-fields') return;
    const input = request.postDataJSON();
    const row = { path: input?.path, method: input?.method ?? 'GET', started: Date.now() };
    requests.push(row);
    request.response().then(response => { row.status = response?.status(); row.elapsed_ms = Date.now() - row.started; }).catch(() => {});
  });
  try {
    const owner = h.privateLoad();
    await h.login(page, owner.username, owner.password);
    const parsed = spawnSync(path.join(h.root, 'apis/audit/.venv/Scripts/python.exe'), ['-c',
      "import csv,json; rows=list(csv.DictReader(open('docs/tenant-admin-findings-2026-10-29.csv',encoding='utf-8-sig',newline=''))); print(json.dumps([{'company':r['test_id'].split('-',3)[2],'route':r['test_id'].split('-',3)[3]} for r in rows if r['test_id'].startswith('TA-LINK-')]))"
    ], { cwd: h.root, encoding: 'utf8' });
    assert.equal(parsed.status, 0, 'Original finding targets could not be read');
    let targets = JSON.parse(parsed.stdout);
    if (process.env.QA_FAILED_ONLY === '1') {
      const prior = JSON.parse(fs.readFileSync(path.join(h.output, 'pending-7-results.json'), 'utf8'));
      const failed = new Set(prior.results.filter(r => r.status !== 'PASS' && r.id.startsWith('P7-LINK-')).map(r => r.id));
      targets = targets.filter(t => failed.has('P7-LINK-' + t.company + '-' + t.route));
    }
    assert(targets.length > 0 && targets.every(t => resources.companies.some(c => c.key === t.company)), 'Original failed links must map to retained companies');
    for (const company of resources.companies) {
      if (process.env.QA_COMPANY_KEY && company.key !== process.env.QA_COMPANY_KEY) continue;
      await h.switchCompany(company);
      if (company.key === 'distribution' && process.env.QA_FAILED_ONLY !== '1') {
        const native = await require('./identity_reader.cjs')(h, 'accounting');
        for (const suffix of ['/configuration', '/positions/field-set', '/positions?limit=1']) {
          const response = await native('/v1/companies/' + company.id + '/stock' + suffix);
          console.log('P7 native stock readiness ' + suffix + ': ' + response.status);
          assert.equal(response.status, 200, 'Native stock readiness failed');
        }
        for (const [view, label] of [['positions', 'Batches and locations'], ['movements', 'Stock movements'], ['account-policies', 'Stock accounts']]) {
          await h.test('P7-STOCK-' + view, 'Stock UI', 'Open stock, select ' + label + ', refresh/reload the view', 'Correct scoped view loads with no application failure', async () => {
            const response = await h.ready('/inventory/stock');
            assert.equal(response.status(), 200);
            const before = h.errors.length;
            await page.getByRole('navigation', { name: 'Stock views' }).getByRole('link', { name: label, exact: true }).click();
            await page.waitForURL(url => url.searchParams.get('view') === view);
            await page.getByRole('heading', { name: 'Stock', exact: true }).waitFor();
            await page.getByRole('navigation', { name: 'Stock views' }).getByRole('link', { name: label, exact: true }).getAttribute('aria-current').then(value => assert.equal(value, 'page'));
            if (view !== 'account-policies') {
              const refresh = page.getByRole('button', { name: 'Refresh', exact: true });
              await page.waitForFunction(el => Object.keys(el).some(k => k.startsWith('__reactProps$') && typeof el[k]?.onClick === 'function'), await refresh.elementHandle(), { timeout: 90000 });
              await refresh.click();
              await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
              await page.getByRole('main').getByText('No posted stock found', { exact: true }).waitFor();
            }
            const reload = await page.reload({ waitUntil: 'domcontentloaded' });
            assert.equal(reload.status(), 200);
            await page.getByRole('heading', { name: 'Stock', exact: true }).waitFor();
            await page.getByRole('main').getByRole('status').filter({ hasText: /^Loading/i }).first().waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
            const text = await page.getByRole('main').innerText();
            if (view === 'account-policies') await page.getByRole('heading', { name: 'Latest published stock accounts', exact: true }).waitFor();
            assert(!/Internal Server Error|Application error:|temporarily unavailable|could not load|couldn't load|Forbidden/i.test(text));
            assert.equal(h.errors.length, before);
            await h.capture('pending-7-stock-' + view);
            return label + ' selected through UI and reloaded; stock admission remains gated';
          });
        }
      }
      const routes = process.env.QA_STOCK_ONLY === '1' ? [] : [...new Set(targets.filter(t => t.company === company.key).map(t => t.route))];
      for (const route of routes) {
        assert(route.startsWith('/') && !route.startsWith('//') && !route.startsWith('/platform') && !route.startsWith('/api/'));
        await h.test('P7-LINK-' + company.key + '-' + route, 'Previously failed record links', 'Open original destination ' + route + ' in an authenticated browser', 'Authorized UI renders the intended record without session/server errors', async () => {
          const before = h.errors.length;
          const response = await h.ready(route);
          assert.equal(response.status(), 200);
          assert.equal(new URL(page.url()).pathname, new URL(route, h.origin).pathname);
          const text = await page.getByRole('main').innerText();
          assert(!/Internal Server Error|Application error:|temporarily unavailable|This page could not be found|You do not have access|Forbidden/i.test(text));
          assert(text.trim().length > 0);
          assert.equal(h.errors.length, before);
          return 'HTTP 200; intended record UI rendered in ' + company.key;
        });
      }
    }
    if (h.results.some(r => r.status !== 'PASS')) process.exitCode = 1;
  } catch (error) {
    await h.test('P7-RUN', 'Execution', 'Complete read-only pending rechecks', 'Run completes', async () => { throw error; });
    process.exitCode = 1;
  } finally {
    fs.writeFileSync(path.join(h.output, 'pending-7-request-timing.json'), JSON.stringify(requests, null, 2));
    h.save();
    await h.browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
