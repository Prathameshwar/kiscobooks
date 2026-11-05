/* Run from the repository root with the existing local browser tools installed. */
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../../..');
const { chromium } = require(path.join(root, '.tools/setup-browser/node_modules/playwright'));
const packages = path.join(root, 'mfes/node_modules/.pnpm');
const esbuild = require(path.join(packages, fs.readdirSync(packages).find(name => name.startsWith('esbuild@')), 'node_modules/esbuild'));
const output = path.join(root, '.tools/company-management/browser');
(async () => {
  fs.mkdirSync(output, { recursive: true });
  await esbuild.build({ entryPoints: [path.join(__dirname, 'main.tsx')], bundle: true, outfile: path.join(output, 'bundle.js'), jsx: 'automatic',
    nodePaths: [path.join(root, 'mfes/apps/console/node_modules')], alias: { '@janso/ui': path.join(root, 'mfes/packages/ui/src/index.ts'), '@janso/ui/styles': path.join(root, 'mfes/packages/ui/src/styles') },
    define: { 'process.env.NODE_ENV': '"development"' }, plugins: [{ name: 'fixture-api', setup(build) {
      build.onResolve({ filter: /\/lib\/company-api$/ }, () => ({ path: path.join(__dirname, 'api.ts') }));
    } }] });
  const server = http.createServer((request, response) => {
    if (['/bundle.js', '/bundle.css'].includes(request.url)) {
      response.setHeader('content-type', request.url.endsWith('.css') ? 'text/css' : 'text/javascript');
      return response.end(fs.readFileSync(path.join(output, request.url.slice(1))));
    }
    response.setHeader('content-type', 'text/html');
    response.end('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/bundle.css"></head><body class="janso-root"><div id="root"></div><script src="/bundle.js"></script></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [];
    page.on('pageerror', error => { errors.push(error.message); console.error('Browser error:', error.message); });
    const origin = `http://127.0.0.1:${server.address().port}`;
    for (const mode of ['directory', 'view', 'edit']) {
      await page.goto(origin + (mode === 'directory' ? '/companies/manage' : '/companies/01990000-0000-7000-8000-000000000001' + (mode === 'edit' ? '/edit' : '')));
      await (mode === 'directory' ? page.getByRole('link', { name: 'Acme Manufacturing', exact: true }) : mode === 'edit' ? page.getByRole('textbox', { name: 'Display name' }) : page.getByRole('heading', { name: 'Acme Manufacturing', exact: true })).waitFor();
      for (const theme of ['Light', 'Dark', 'Ledger']) {
        await page.getByRole('radio', { name: theme, exact: true }).click();
        await page.screenshot({ path: path.join(output, `${mode}-${theme}-desktop.png`), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${mode} ${theme} mobile overflow`);
        await page.screenshot({ path: path.join(output, `${mode}-${theme}-mobile.png`), fullPage: true });
        await page.setViewportSize({ width: 1440, height: 1000 });
      }
    }
    await page.getByRole('textbox', { name: 'Display name' }).fill('Acme Manufacturing Updated');
    await page.getByRole('button', { name: 'Save company' }).click();
    await page.getByText('Company saved.', { exact: false }).waitFor();
    await page.goto(origin + '/companies/manage');
    await page.getByRole('link', { name: 'Acme Manufacturing', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Actions for Acme Manufacturing', exact: true }).click();
    assert.equal(await page.getByRole('menuitem', { name: 'Manage years' }).getAttribute('href'), '/companies/01990000-0000-7000-8000-000000000001/years');
    await page.getByRole('menuitem', { name: 'Manage years' }).click();
    await page.getByRole('link', { name: 'FY2026-2027' }).waitFor();
    for (const mode of ['years', 'generate', 'periods']) {
      const base = '/companies/01990000-0000-7000-8000-000000000001/years';
      await page.goto(origin + base + (mode === 'generate' ? '/new' : mode === 'periods' ? '/01990000-0000-7000-8000-000000000002' : ''));
      await (mode === 'generate' ? page.getByRole('textbox', { name: 'Starting year' }) : mode === 'periods' ? page.getByText('P1', { exact: true }) : page.getByRole('link', { name: 'FY2026-2027' })).waitFor();
      for (const theme of ['Light', 'Dark', 'Ledger']) {
        await page.getByRole('radio', { name: theme, exact: true }).click();
        await page.screenshot({ path: path.join(output, `${mode}-${theme}-desktop.png`), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${mode} ${theme} mobile overflow`);
        await page.screenshot({ path: path.join(output, `${mode}-${theme}-mobile.png`), fullPage: true });
        await page.setViewportSize({ width: 1440, height: 1000 });
      }
    }
    await page.getByRole('button', { name: 'Actions for P1', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Open period', exact: true }).click();
    await page.getByRole('textbox', { name: 'Reason for status change' }).fill('Reviewed opening period');
    await page.getByRole('button', { name: 'Open period', exact: true }).click();
    await page.getByText('Open period completed.', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('Passed company and financial-year pages: kebab links, six page modes, three themes, desktop/mobile, company save and period open; no overflow or page errors.');
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
