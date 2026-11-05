/* Read-only live checks following real login. */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
module.exports = async function ({ page, context, origin, output, results }) {
  const settled = async () => {
    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
    await page.getByText(/^Loading platform details/).waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
    await page.getByText('Loading rows', { exact: true }).waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
    await page.getByRole('status', { name: 'Loading notifications' }).first().waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
  };
  async function check(id, run) {
    if (process.env.QA_READ_CASE && process.env.QA_READ_CASE !== id) return;
    try { results.push({ id, result: 'PASS', actual: await run() }); }
    catch (error) { results.push({ id, result: 'FAIL', actual: String(error) }); }
    console.log(JSON.stringify(results.at(-1)));
  }
  await check('LIVE-UNAUTHENTICATED-BOUNDARY', async () => {
    const anonymous = await context.browser().newContext();
    try {
      for (const target of ['/v1/platform/details', '/v1/platform/tenants', '/v1/platform/access/role', '/v1/platform/pricing']) {
        const response = await anonymous.request.post(origin + '/api/platform', { headers: { Origin: origin }, data: { service: 'identity', method: 'GET', path: target } });
        assert.equal(response.status(), 401, target);
      }
    } finally { await anonymous.close(); }
    return 'Four real Console proxy requests refused absent sessions with HTTP 401';
  });
  await check('LIVE-READ-API-CATALOGS', async () => {
    await page.goto(origin + '/platform');
    const observations = [];
    for (const target of ['/v1/platform/details', '/v1/platform/pricing', '/v1/platform/tenants', '/v1/platform/accounts', '/v1/platform/access/role', '/v1/platform/references/countries', '/v1/platform/references/states', '/v1/platform/references/currencies', '/v1/platform/references/languages', '/v1/platform/references/timezones']) {
      const row = await page.evaluate(async target => {
        const response = await fetch('/api/platform', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ service: 'identity', method: 'GET', path: target }) });
        const body = await response.json();
        return { target, status: response.status, count: body.items?.length, error: body.error?.message };
      }, target);
      observations.push(row);
      assert.equal(row.status, 200, JSON.stringify(row));
    }
    fs.writeFileSync(path.join(output, 'catalog-read-results.json'), JSON.stringify(observations, null, 2));
    return 'Ten live Identity read contracts returned HTTP 200';
  });
  await check('LIVE-SETTLED-DATA-PAGES', async () => {
    for (const route of ['/platform/details', '/platform/pricing', '/platform/references/states', '/platform/history']) {
      await page.goto(origin + route);
      await settled();
      const body = await page.getByRole('main').innerText();
      fs.writeFileSync(path.join(output, route.replaceAll('/', '_') + '-settled.txt'), body);
      await page.screenshot({ path: path.join(output, route.replaceAll('/', '_') + '-settled.png'), fullPage: true });
      assert(!/Loading rows|Loading platform details|unable to|unavailable/i.test(body), route + ': ' + body.slice(0, 1000));
    }
    return 'Metadata, pricing, states and history finished loading and displayed no service error';
  });
  await check('LIVE-TENANT-SEARCH', async () => {
    await page.goto(origin + '/platform/tenants');
    await page.getByRole('searchbox', { name: 'Search tenants', exact: true }).fill('QA Platform');
    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
    await page.waitForTimeout(1000);
    const body = await page.getByRole('main').innerText();
    assert(/QA Platform/.test(body));
    assert(!/Demo Tenant/.test(body));
    return 'Tenant prefix search returned QA tenant and excluded unrelated demo tenants';
  });
  await check('LIVE-NOTIFICATION-DESTINATIONS-SETTLED', async () => {
    await page.goto(origin + '/platform/notifications');
    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
    const links = [...new Set(await page.getByRole('main').locator('a[href^="/platform/notifications/"]').evaluateAll(elements => elements.map(element => element.getAttribute('href'))))];
    assert(links.length > 0);
    const observations = [];
    for (const link of links) {
      const response = await page.goto(origin + link);
      await settled();
      const text = await page.getByRole('main').innerText();
      assert.equal(await page.getByRole('status', { name: 'Loading notifications' }).count(), 0, link + ' remained loading');
      assert(!text.includes('Loading rows'), link + ' remained loading');
      fs.writeFileSync(path.join(output, link.replaceAll('/', '_') + '.txt'), text);
      observations.push({ link, status: response.status(), text: text.slice(0, 2200) });
    }
    fs.writeFileSync(path.join(output, 'notification-results.json'), JSON.stringify(observations, null, 2));
    assert(observations.every(row => row.status === 200 && !/unable to|unavailable|failed to|permission is required/i.test(row.text)), JSON.stringify(observations.filter(row => row.status !== 200 || /unable to|unavailable|failed to|permission is required/i.test(row.text))));
    return `Loaded ${links.length} notification destinations with live services and no visible service errors`;
  });
  await check('LIVE-MOBILE-VERIFIED-THEMES', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    const observations = [];
    for (const route of ['/platform', '/platform/tenants', '/platform/pricing', '/platform/access/permissions']) {
      for (const theme of ['light', 'dark', 'ledger']) {
        await page.evaluate(theme => {
          document.cookie = 'janso-theme=' + theme + '; path=/; SameSite=Lax';
          localStorage.setItem('janso-theme', theme);
        }, theme);
        await page.goto(origin + route);
        await settled();
        assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
        const widths = await page.evaluate(() => ({ actual: document.documentElement.scrollWidth, viewport: innerWidth }));
        observations.push({ route, theme, ...widths });
        await page.screenshot({ path: path.join(output, route.replaceAll('/', '_') + '-' + theme + '-390.png'), fullPage: true });
      }
    }
    fs.writeFileSync(path.join(output, 'verified-mobile-results.json'), JSON.stringify(observations, null, 2));
    assert(observations.every(row => row.actual <= row.viewport), JSON.stringify(observations.filter(row => row.actual > row.viewport)));
    await page.setViewportSize({ width: 1440, height: 1000 });
    return 'Verified applied theme attribute and lack of document overflow on 12 mobile page/theme combinations';
  });
  await check('LIVE-CHANGE-PASSWORD-PAGE', async () => {
    await page.goto((process.env.QA_AUTH_URL || 'http://localhost:4310') + '/change-password');
    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
    const body = await page.locator('body').innerText();
    fs.writeFileSync(path.join(output, 'change-password.txt'), body);
    assert(/change.*password/i.test(body));
    assert(!/unavailable|not configured/i.test(body), body);
    return 'Authenticated change-password handoff page loaded; supplied account password left unchanged';
  });
};
