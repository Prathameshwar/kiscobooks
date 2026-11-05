/* Discover every available master card and check actual filter geometry through the UI. */
const { start } = require('./harness.cjs');
(async () => {
  const h = await start(process.env.QA_LAYOUT_PHASE || 'master-filter-layout');
  const { page, assert } = h;
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    const company = h.resources.companies.find(row => row.key === (process.env.QA_COMPANY_KEY || 'retail'));
    assert(company, 'QA company is unavailable'); await h.switchCompany(company);
    await h.ready('/masters');
    await page.getByRole('link', { name: /Open products/i }).first().waitFor().catch(() => {});
    let routes = [...new Set(await page.locator('main a.janso-action-card[href]').evaluateAll(links => links.map(link => link.getAttribute('href'))))];
    if (!routes.length) routes = [...new Set(await page.locator('main a[href]').evaluateAll(links => links.map(link => link.getAttribute('href')).filter(href => /^(?:\/masters|\/accounting|\/tax|\/inventory)\/[^/?]+(?:\?.*)?$/.test(href))))];
    if (process.env.QA_LAYOUT_ROUTES) routes = process.env.QA_LAYOUT_ROUTES.split(',');
    routes = routes.filter(route => /^\/(masters|accounting|tax|inventory)\/[a-z][a-z0-9-]*(\?returnTo=%2Fmasters)?$/.test(route));
    if (process.env.QA_FAILED_ONLY === '1') {
      const source = require('node:path').join(h.output, (process.env.QA_RECHECK_PHASE || 'master-filter-layout') + '-results.json');
      const failed = JSON.parse(require('node:fs').readFileSync(source, 'utf8')).results.filter(row => row.status !== 'PASS').map(row => row.steps.match(/^Visit (\S+) at /)?.[1]);
      routes = routes.filter(route => failed.includes(route));
    }
    assert(routes.length, 'No available master directory destinations were discovered');
    const widths = (process.env.QA_LAYOUT_WIDTHS || '1440').split(',').map(Number);
    assert(widths.every(width => [1440, 768, 390].includes(width)), 'Unsupported geometry width');
    console.log('Discovered ' + routes.length + ' master directory destinations');
    for (const route of routes) for (const width of widths) {
      await page.setViewportSize({ width, height: 1000 });
      await h.test('MASTER-FILTER-' + route.split('?')[0].replaceAll('/', '-') + '-' + width, 'Master directory filters', 'Visit ' + route + ' at ' + width + 'px; measure each query/filter field', 'Controls align and fit; hints do not move adjacent controls; focus remains accessible', async () => {
        const response = await h.ready(route);
        assert(response?.status() < 400, 'Directory HTTP status ' + response?.status());
        await page.locator('main [role="status"]').filter({ hasText: /^Loading/ }).first().waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
        const geometry = await page.evaluate(() => {
          const box = el => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height }; };
          const fields = [...document.querySelectorAll('main .janso-filter-bar__controls .janso-field')].filter(field => field.getBoundingClientRect().height > 0);
          const missingBars = [...document.querySelectorAll('main .janso-table-search')].filter(field => !field.closest('.janso-filter-bar'));
          return { width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, missingBars: missingBars.length,
            fields: fields.map(field => { const control = field.querySelector('.janso-input-wrap,.janso-select__wrap,.janso-search-select__control'); return { label: field.querySelector('label')?.textContent.trim() ?? '', field: box(field), control: control ? box(control) : null, hint: field.querySelector('.janso-hint') ? box(field.querySelector('.janso-hint')) : null }; }) };
        });
        assert.equal(geometry.missingBars, 0, 'Directory search is outside the shared filter layout');
        assert(geometry.scrollWidth <= geometry.width + 1, 'Directory has horizontal overflow');
        for (const field of geometry.fields.filter(field => field.control)) {
          assert(Math.abs(field.field.top - field.control.top) <= 1, field.label + ' control is below its neighbouring search/select row');
          assert(Math.abs(field.control.height - 36) <= 1, field.label + ' control has inconsistent height ' + field.control.height);
          assert(field.control.left >= 0 && field.control.right <= geometry.width + 1, field.label + ' exceeds the viewport');
          if (field.hint) assert(field.hint.top >= field.control.bottom - 1, field.label + ' hint overlaps the control');
        }
        await h.capture('master-filter-' + route.split('?')[0].replaceAll('/', '-') + '-' + width);
        return geometry.fields.length ? 'Verified ' + geometry.fields.length + ' query/filter controls; ' + JSON.stringify(geometry) : 'Directory loads without query/filter controls; no alignment assertion needed';
      });
    }
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } finally { h.save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
