/* Read-only runtime audit. Credentials stay in memory; no activation or business writes. */
const fs = require('node:fs'), path = require('node:path');
const { start, privateLoad } = require('../tenant-admin/harness.cjs');
const root = path.resolve(__dirname, '../../..');
const reportFile = path.join(__dirname, 'runtime.json');
const report = { observed_at: new Date().toISOString(), health: [], authenticated: { status: 'NOT_RUN' }, companies: [] };
let stage = 'health';
(async () => {
  const services = JSON.parse(fs.readFileSync(path.join(root, 'start/win/conf/services.json'))).services;
  report.health = await Promise.all(services.filter(row => ['identity', 'catalog', 'accounting', 'vouchers', 'reports'].includes(row.code)).map(async row => {
    try { const response = await fetch('http://127.0.0.1:' + row.port + '/health/ready', { signal: AbortSignal.timeout(10000) }); return { service: row.code, status: response.status }; }
    catch { return { service: row.code, status: 'UNAVAILABLE' }; }
  }));
  const h = await start('purchase-api-read-only');
  const signInRequests = [];
  h.page.on('response', response => { const url = new URL(response.url()); if (url.pathname === '/api/local/login') signInRequests.push({ method: response.request().method(), status: response.status() }); });
  try {
    const credentials = privateLoad(process.env.QA_PURCHASE_CREDENTIAL_FILE);
    stage = 'sign-in-page';
    await h.page.goto(h.auth + '/login');
    const continuation = h.page.getByRole('button', { name: 'Continue to sign in', exact: true });
    await h.page.waitForFunction(button => Object.keys(button).some(key => key.startsWith('__reactProps$') && typeof button[key]?.onClick === 'function'), await continuation.elementHandle(), { timeout: 60000 });
    await continuation.click();
    const identifier = h.page.getByRole('textbox', { name: /^(?:Username or email address|Email address)$/ });
    await identifier.waitFor({ timeout: 20000 });
    // Do not submit a server-rendered form until React owns its submit event.
    await h.page.waitForFunction(form => Object.keys(form).some(key => key.startsWith('__reactProps$') && typeof form[key]?.onSubmit === 'function'), await h.page.getByRole('form', { name: 'Sign in', exact: true }).elementHandle(), { timeout: 60000 });
    stage = 'local-sign-in';
    const email = credentials.email ?? credentials.username;
    if (typeof email !== 'string' || !email.includes('@')) throw Error('Retained QA account has no email suitable for the active local provider.');
    await identifier.fill(email);
    await h.page.getByLabel('Password', { exact: true }).fill(credentials.password);
    await h.page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await h.page.waitForURL(url => url.origin === h.origin || url.origin === h.auth && url.pathname === '/onboarding', { timeout: 30000 });
    stage = 'company-access';
    const identity = await require('../tenant-admin/identity_reader.cjs')(h, 'identity');
    const companies = await identity('/v1/companies?limit=50');
    if (companies.status !== 200 || !Array.isArray(companies.body.items)) throw Error('Company access could not be verified.');
    // The native QA reader accepts only explicitly scoped companies. Derive its
    // read-only scope from this account's actual Identity result, not old artifacts.
    h.resources.companies = companies.body.items.map(company => ({ id: company.id }));
    report.authenticated = { status: 'PASS', company_count: companies.body.items.length, landed_path: new URL(h.page.url()).pathname };
    const native = await require('../tenant-admin/identity_reader.cjs')(h, 'vouchers');
    stage = 'voucher-capabilities';
    for (const company of companies.body.items) {
      const base = '/v1/companies/' + company.id;
      const capabilities = await native(base + '/voucher-capabilities');
      const types = await native(base + '/voucher-types?kind=PURCHASE&status=ACTIVE&limit=200');
      const flags = capabilities.body;
      report.companies.push({ company_id: company.id, capabilities_status: capabilities.status, capabilities: capabilities.status === 200 ? { financial_execution: flags.financial_execution ?? null, invoice_execution: flags.invoice_execution ?? null, purchase_supporting_files: flags.purchase_supporting_files ?? null, kinds: flags.kinds?.filter(row => row.kind === 'PURCHASE').map(row => ({ kind: row.kind, execution_ready: row.execution_ready })) } : undefined, type_status: types.status, active_purchase_type_count: types.body.items?.length });
    }
  } catch (error) {
    report.authenticated = report.authenticated.status === 'PASS' ? { status: 'PASS', capability_audit: 'Company or service access could not be verified.' } : { status: 'BLOCKED', reason: 'The browser audit did not establish an authenticated session. This does not establish whether the credentials are valid. No account, provider or company configuration was changed.', failure_type: error.name };
    report.authenticated.stage = stage;
    report.authenticated.sign_in_requests = signInRequests;
    const at = new URL(h.page.url()); report.authenticated.landed_path = at.pathname;
    await h.page.screenshot({ path: path.join(h.output, 'purchase-sign-in-private.png'), fullPage: true, mask: [h.page.locator('input[type=password]'), h.page.locator('input[type=email]')] }).catch(() => {});
  } finally { await h.browser.close(); }
})().catch(() => { report.authenticated = { status: 'BLOCKED', reason: 'Runtime audit could not start. No configuration changed.' }; }).finally(() => {
  fs.writeFileSync(reportFile, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ health: report.health, authenticated: report.authenticated, company_count: report.companies.length }));
});
