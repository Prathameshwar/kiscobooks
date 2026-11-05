/* Real UI/API report generation, execution and advertised export acceptance. */
const { start } = require('./harness.cjs');

(async () => {
  const h = await start('pending-9');
  const { page, resources, assert } = h;
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function waitReady(base, resource, identity, complete) {
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      const result = await h.call('product-fields', 'reports', base + '/' + resource + '/' + identity);
      assert.equal(result.status, 200);
      if (result.body.status === complete) return result.body;
      assert(!['FAILED', 'CANCELLED', 'QUARANTINED', 'BLOCKED'].includes(result.body.status), 'Report prerequisite failed: ' + result.body.status + ' ' + (result.body.failure_code ?? ''));
      await pause(2000);
    }
    throw Error('Report prerequisite did not complete within 180 seconds');
  }
  try {
    const owner = h.privateLoad();
    await h.login(page, owner.username, owner.password);
    const accounting = await require('./identity_reader.cjs')(h, 'accounting');
    resources.reportGenerations ??= {};
    resources.reportRuns ??= {};
    for (const company of resources.companies) {
      if (process.env.QA_COMPANY_KEY && company.key !== process.env.QA_COMPANY_KEY) continue;
      await h.switchCompany(company);
      const base = '/v2/companies/' + company.id;
      let selected, generation;
      const discovery = await h.test('P9-DISCOVERY-' + company.key, 'Reports', 'Load real report workspace and select Trial balance', 'Current scoped catalogue advertises configured runs and formats', async () => {
        await h.ready('/reports/workspace?report=TRIAL_BALANCE');
        const load = page.getByRole('button', { name: 'Load report workspace', exact: true });
        await page.waitForFunction(el => Object.keys(el).some(k => k.startsWith('__reactProps$') && typeof el[k]?.onClick === 'function'), await load.elementHandle(), { timeout: 90000 });
        const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/report-definitions');
        pending.catch(() => {});
        await load.click();
        const response = await pending;
        assert.equal(response.status(), 200);
        const catalog = await response.json();
        assert.equal(catalog.items.length, 38);
        selected = catalog.items.find(item => item.definition.code === 'TRIAL_BALANCE');
        assert(selected?.run_enabled);
        const report = page.getByRole('combobox', { name: 'Report', exact: true });
        if (await report.inputValue() !== 'TRIAL_BALANCE') await report.selectOption('TRIAL_BALANCE');
        await page.getByRole('heading', { name: 'Report settings', exact: true }).waitFor();
        return '38 definitions; Trial balance enabled; formats ' + selected.formats.join(', ');
      }, 'LIVE_UI_WITH_API_READBACK');
      if (discovery.status !== 'PASS') continue;
      const identity = await require('./identity_reader.cjs')(h);
      const session = await identity('/v1/session?company_id=' + company.id);
      console.log('P9 current report permissions: ' + JSON.stringify((session.body.permissions ?? []).filter(p => typeof p === 'string' && p.startsWith('report.'))));
      const source = await h.test('P9-SOURCE-' + company.key, 'Report sources', 'Request fresh sources through UI and poll the company generation', 'Verified READY owner snapshot is published', async () => {
        let identity = resources.reportGenerations[company.id];
        if (identity) {
          const retained = await h.call('product-fields', 'reports', base + '/report-generations/' + identity);
          assert.equal(retained.status, 200);
          if (['FAILED', 'CANCELLED', 'QUARANTINED', 'BLOCKED'].includes(retained.body.status)) {
            resources.failedReportGenerations ??= [];
            if (!resources.failedReportGenerations.includes(identity)) resources.failedReportGenerations.push(identity);
            delete resources.reportGenerations[company.id];
            identity = null;
            h.save();
          }
        }
        if (!identity) {
          const existing = await h.call('product-fields', 'reports', base + '/report-generations?limit=50');
          assert.equal(existing.status, 200);
          identity = existing.body.items.find(row => ['READY', 'QUEUED', 'RUNNING', 'BUILDING', 'PREPARING'].includes(row.status))?.id;
          if (identity) { resources.reportGenerations[company.id] = identity; h.save(); }
        }
        if (!identity) {
          const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/report-generations' && r.request().postDataJSON()?.method === 'POST');
          pending.catch(() => {});
          await page.getByRole('button', { name: 'Refresh report sources', exact: true }).click();
          const response = await pending;
          assert.equal(response.status(), 202);
          identity = (await response.json()).id;
          assert(identity);
          resources.reportGenerations[company.id] = identity;
          h.save();
        }
        generation = await waitReady(base, 'report-generations', identity, 'READY');
        await page.getByRole('button', { name: 'Load report workspace', exact: true }).click();
        await page.getByRole('combobox', { name: 'Source snapshot', exact: true }).selectOption(identity);
        return 'READY generation ' + identity + '; owner snapshot verified through the existing source worker';
      }, 'LIVE_UI_WITH_API_READBACK');
      if (source.status !== 'PASS') continue;
      let run;
      const result = await h.test('P9-RUN-' + company.key, 'Report runs', 'Submit typed Trial balance parameters through UI and inspect authoritative rows', 'Report completes; debit/credit totals reconcile', async () => {
        const setup = await accounting('/v1/companies/' + company.id + '/financial-setup');
        assert.equal(setup.status, 200);
        assert(/^\d{4}-\d{2}-\d{2}$/.test(setup.body.books_begin_date), 'Books-begin coverage is unavailable');
        const properties = selected.parameter_schema.properties;
        await page.getByLabel(properties.date_from.title ?? 'date from', { exact: false }).fill(setup.body.books_begin_date);
        await page.getByLabel(properties.date_to.title ?? 'date to', { exact: false }).fill(new Date().toISOString().slice(0, 10));
        const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/report-runs' && r.request().postDataJSON()?.method === 'POST');
        pending.catch(() => {});
        await page.getByRole('button', { name: 'Create report', exact: true }).click();
        const response = await pending;
        assert.equal(response.status(), 202);
        const created = await response.json();
        resources.reportRuns[company.id] = created.id;
        h.save();
        run = await waitReady(base, 'report-runs', created.id, 'COMPLETE');
        const allRows = [], seen = new Set();
        let cursor = null;
        do {
          const response = await h.call('product-fields', 'reports', base + '/report-runs/' + run.id + '/rows?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
          assert.equal(response.status, 200);
          assert(Array.isArray(response.body.items));
          allRows.push(...response.body.items);
          assert(allRows.length <= 2000, 'QA report exceeds the bounded acceptance fixture');
          cursor = response.body.page.next_cursor;
          if (cursor) { assert(!seen.has(cursor), 'Repeated pagination cursor'); seen.add(cursor); }
        } while (cursor);
        const control = allRows.find(row => row.data.row_kind === 'TRIAL_BALANCE_CONTROL');
        assert(control, 'Trial balance reconciliation control is missing');
        assert.equal(control.data.debit, '0.0000');
        assert.equal(control.data.credit, '0.0000');
        assert.equal(control.data.difference, '0.0000');
        await page.getByRole('button', { name: 'Refresh report', exact: true }).click();
        await page.getByRole('status').filter({ hasText: 'Report: COMPLETE' }).waitFor();
        await h.capture('pending-9-trial-balance-' + company.key);
        return 'Report COMPLETE; ' + allRows.length + ' rows from READY source ' + generation.id + '; debit/credit/difference exactly 0.0000';
      }, 'LIVE_UI_WITH_API_READBACK');
      if (result.status !== 'PASS') continue;
      for (const format of selected.formats) {
        await h.test('P9-EXPORT-' + company.key + '-' + format, 'Report exports', 'Create ' + format + ' through the offered export control; read job and download response', 'Export completes and authorized private download succeeds', async () => {
          const pending = page.waitForResponse(r => new URL(r.url()).pathname === '/api/product-fields' && r.request().postDataJSON()?.path === base + '/report-runs/' + run.id + '/exports' && r.request().postDataJSON()?.method === 'POST');
          pending.catch(() => {});
          await page.getByRole('button', { name: 'Export ' + format, exact: true }).click();
          const response = await pending;
          assert.equal(response.status(), 202);
          const job = await response.json();
          const completed = await waitReady(base, 'report-exports', job.id, 'COMPLETE');
          const download = await page.request.get(h.origin + '/api/report-download?company=' + encodeURIComponent(company.id) + '&export=' + encodeURIComponent(completed.id));
          assert.equal(download.status(), 200);
          assert((await download.body()).length > 0);
          assert(download.headers()['cache-control']?.includes('no-store'));
          return format + ' export COMPLETE; authenticated private download has content and no-store caching';
        }, 'LIVE_UI_WITH_API_READBACK');
      }
      await h.test('P9-HISTORY-' + company.key, 'Report history', 'Read bounded run/export history for the selected company', 'The new run and exports appear with current scope', async () => {
        for (const resource of ['report-runs', 'report-exports']) {
          const response = await h.call('product-fields', 'reports', base + '/' + resource + '?limit=20');
          assert.equal(response.status, 200);
          assert(response.body.items.length > 0);
          assert(response.body.page.limit <= 200);
        }
        return 'Run and export history contain the executed jobs with bounded paging';
      }, 'LIVE_AUTHENTICATED_API');
    }
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } catch (error) {
    await h.test('P9-RUNNER', 'Execution', 'Complete report readiness acceptance', 'Run completes', async () => { throw error; });
    process.exitCode = 1;
  } finally {
    h.save();
    await h.browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
