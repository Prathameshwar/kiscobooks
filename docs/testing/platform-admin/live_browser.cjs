/* Live checks; writes require QA_MUTATE. Credentials come from environment, never saved. */
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const output = path.resolve(process.env.QA_OUTPUT || path.join(root, '.test_artifacts/platform-admin-live'));
const origin = process.env.QA_CONSOLE_URL || 'http://localhost:4320';
const auth = process.env.QA_AUTH_URL || 'http://localhost:4310';
const results = [];
const errors = [];
async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.QA_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  page.on('pageerror', error => errors.push(String(error)));
  page.on('response', async response => {
    if (new URL(response.url()).pathname.includes('/api/v3/flows/executor/')) {
      const data = await response.json().catch(() => ({}));
      console.log('Provider stage', JSON.stringify({ status: response.status(), component: data.component, error_message: data.error_message, errors: data.response_errors }));
    }
  });
  try {
    await page.goto(auth + '/login', { timeout: 120000 });
    await page.getByRole('button', { name: 'Continue to sign in', exact: true }).click();
    let passwordSubmissions = 0;
    for (let iteration = 0; iteration < 150; iteration++) {
      if (new URL(page.url()).origin === origin) break;
      if (await page.locator('ak-loading-overlay:visible').count()) {
        await page.waitForTimeout(1000);
        continue;
      }
      const username = page.getByRole('textbox', { name: /Email or Username|Username/i }).and(page.locator(':visible')).first();
      const password = page.locator('input[type="password"]:visible').first();
      if (await username.isVisible()) {
        await username.fill(process.env.QA_USERNAME || 'pratham');
        await username.press('Tab');
        await page.getByRole('button', { name: /log in|sign in|continue|next/i }).first().click({ timeout: 10000 }).catch(error => {
          if (new URL(page.url()).origin === 'https://localhost:9443') throw error;
        });
        console.log('Submitted provider username');
        await username.waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
        await page.waitForTimeout(1500);
      } else if (await password.isVisible() && passwordSubmissions < 3 && new URL(page.url()).origin !== auth) {
        await password.fill(process.env.QA_PASSWORD);
        await password.press('Tab');
        await page.waitForTimeout(250);
        await page.getByRole('button', { name: /log in|sign in|continue/i }).first().click({ timeout: 10000 }).catch(error => {
          if (new URL(page.url()).origin === 'https://localhost:9443') throw error;
        });
        passwordSubmissions++;
        console.log('Submitted provider password stage', passwordSubmissions);
        await page.waitForTimeout(2000);
        await page.screenshot({ path: path.join(output, 'provider-stage-' + passwordSubmissions + '.png'), fullPage: true });
        await password.waitFor({ state: 'hidden', timeout: 20000 }).catch(() => {});
      } else {
        await page.waitForTimeout(1000);
      }
    }
    if (new URL(page.url()).origin !== origin) throw new Error('Real login did not reach Console; inspect blocked screenshot');
    console.log('Console reached', new URL(page.url()).pathname);
    results.push({ id: 'LIVE-LOGIN', result: 'PASS', actual: 'Real Authentik username/password login reached Console' });
    await page.waitForURL(url => url.pathname === '/platform', { timeout: 60000 });
    results.push({ id: 'LIVE-PLATFORM-LANDING', result: 'PASS', actual: 'Company-less platform operator landed on platform administration' });
    for (const route of process.env.QA_WORKFLOWS_ONLY === '1' ? [] : ['/platform', '/platform/details', '/platform/tenants', '/platform/tenants/new', '/platform/accounts', '/platform/access/administrators', '/platform/access/role', '/platform/access/permissions', '/platform/pricing', '/platform/references', '/platform/references/countries', '/platform/references/states', '/platform/references/currencies', '/platform/references/languages', '/platform/references/timezones', '/platform/notifications', '/platform/history']) {
      const before = errors.length;
      const response = await page.goto(origin + route, { timeout: 120000 });
      await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(800);
      const text = await page.getByRole('main').innerText().catch(() => page.locator('body').innerText());
      const slug = route.replaceAll('/', '_');
      fs.writeFileSync(path.join(output, slug + '.txt'), text);
      await page.screenshot({ path: path.join(output, slug + '.png'), fullPage: true });
      const row = { id: route, http: response.status(), result: 'OBSERVED', url: new URL(page.url()).pathname, text: text.slice(0, 9000), errors: errors.slice(before) };
      results.push(row);
      console.log(JSON.stringify(row));
    }
    if (process.env.QA_MUTATE === '1') await require('./live_workflows.cjs')({ page, context, origin, auth, output, results });
    if (process.env.QA_LIVE_READS === '1' && (process.env.QA_MUTATE !== '1' || process.env.QA_CORE_ONLY === '1')) await require('./live_reads.cjs')({ page, context, origin, auth, output, results });
    if (results.some(row => ['FAIL', 'BLOCKED'].includes(row.result))) process.exitCode = 1;
  } catch (error) {
    const text = await page.locator('body').innerText().catch(() => '');
    results.push({ id: 'RUN-ERROR', result: 'BLOCKED', error: String(error), pathname: new URL(page.url()).pathname, text: text.slice(0, 6000) });
    console.log(JSON.stringify(results.at(-1)));
    await page.screenshot({ path: path.join(output, 'blocked.png'), fullPage: true }).catch(() => {});
    process.exitCode = 1;
  } finally {
    fs.writeFileSync(path.join(output, 'live-results.json'), JSON.stringify({ results, errors }, null, 2));
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
