/* Verify actual product-directory control geometry with the authorized QA tenant. */
const { start } = require('./harness.cjs');
(async () => {
  const h = await start(process.env.QA_LAYOUT_PHASE || 'items-filter-layout');
  const { page, assert } = h;
  try {
    const owner = h.privateLoad();
    await h.login(page, owner.username, owner.password);
    for (const company of h.resources.companies) {
      if (process.env.QA_COMPANY_KEY && company.key !== process.env.QA_COMPANY_KEY) continue;
      await page.setViewportSize({ width: 1440, height: 1000 });
      await h.switchCompany(company);
      for (const width of [1440, 768, 390]) {
        await page.setViewportSize({ width, height: 1000 });
        await h.test('ITEMS-FILTER-' + company.key + '-' + width, 'Product directory', 'Open requested Items route at ' + width + 'px; measure search/filter geometry and focus', 'Search and inline filter controls align without overflow and remain keyboard reachable', async () => {
          await h.ready('/masters/items?returnTo=%2Fmasters');
          const search = page.getByRole('searchbox').first();
          await search.waitFor();
          const status = page.getByRole('combobox', { name: 'Status', exact: true });
          const sort = page.getByRole('combobox', { name: 'Sort by', exact: true });
          const geometry = await page.evaluate(() => {
            const input = document.querySelector('main input[type="search"]');
            const controls = [...document.querySelectorAll('main .janso-select')].filter(el => [...el.querySelectorAll('label')].some(label => /^(Status|Sort by)$/.test(label.textContent.trim())));
            const box = el => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height }; };
            return { search: box(input), filters: controls.map(el => ({ inline: el.classList.contains('janso-select--inline'), box: box(el.querySelector('select')) })), width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth };
          });
          assert(geometry.filters.length >= 2, 'Status and sort filters are missing');
          for (const filter of geometry.filters) {
            assert(filter.inline, 'Filter label is stacked beside a label-free search input');
            assert(filter.box.left >= 0 && filter.box.right <= geometry.width + 1, 'Filter extends beyond viewport');
            if (Math.abs(filter.box.top - geometry.search.top) < geometry.search.height) assert(Math.abs(filter.box.top - geometry.search.top) <= 1, 'Controls on the same row have different top edges');
          }
          assert(geometry.scrollWidth <= geometry.width + 1, 'Page overflows horizontally');
          await search.focus(); assert(await search.evaluate(el => el === document.activeElement));
          await status.focus(); assert(await status.evaluate(el => el === document.activeElement));
          await sort.focus(); assert(await sort.evaluate(el => el === document.activeElement));
          await h.capture('items-filter-' + company.key + '-' + width);
          return 'Aligned inline filters, accessible focus and no horizontal overflow; geometry ' + JSON.stringify(geometry);
        });
      }
    }
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } finally { h.save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
