// Loopback-only test host: production shell/readiness/proxies, fixture Identity/Accounting.
import react from '@vitejs/plugin-react';
import { resolve, dirname } from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { randomBytes } from 'node:crypto';
import { NextRequest } from 'next/server.js';
const require = createRequire(import.meta.url);
const { encode } = require('next-auth/jwt');
const vitest = createRequire(require.resolve('vitest/package.json'));
const { createServer } = await import(pathToFileURL(resolve(dirname(vitest.resolve('vite/package.json')), 'dist/node/index.js')).href);
const root = process.cwd(), port = Number(process.env.COMPANY_E2E_PORT), origin = 'http://127.0.0.1:' + port;
const ids = { a: '01990000-0000-7000-8000-000000000001', b: '01990000-0000-7000-8000-000000000002', yearA: '01990000-0000-7000-8000-000000000003', yearB: '01990000-0000-7000-8000-000000000004', prior: '01990000-0000-7000-8000-000000000005' };
process.env.NEXTAUTH_SECRET = randomBytes(32).toString('hex');
process.env.AUTH_URL = origin; process.env.IDENTITY_URL = origin + '/identity'; process.env.ACCOUNTING_GATEWAY_URL = origin + '/accounting';
const companies = [{ id: ids.a, name: 'Company A', code: 'A', isDefault: true }, { id: ids.b, name: 'Company B', code: 'B' }];
const permissionsA = ['company.read', 'period.read', 'accounting.finance.read', 'ledger.read', 'report.read', 'vouchers.read'];
const permissionsB = ['company.read', 'period.read'];
function cookies(req) { return Object.fromEntries((req.headers.cookie ?? '').split('; ').filter(Boolean).map(value => { const at = value.indexOf('='); return [value.slice(0, at), decodeURIComponent(value.slice(at + 1))]; })); }
function year(id) { return { id, code: id === ids.prior ? '2025-26' : '2026-27', startDate: id === ids.prior ? '2025-04-01' : '2026-04-01', endDate: id === ids.prior ? '2026-03-31' : '2027-03-31', current: id !== ids.prior, open: id !== ids.prior }; }
function configuration(req, url) {
  const saved = cookies(req), company = saved['janso-company'] === ids.b ? companies[1] : companies[0];
  const profile = url.searchParams.get('profile') ?? saved['company-fixture-profile'] ?? 'company';
  const permissions = profile === 'reader' ? [] : company.id === ids.a ? permissionsA : permissionsB;
  const shared = profile === 'tenant' ? [{ permissions: ['notification.provider.read', 'company.read'], scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null }] : [];
  const years = company.id === ids.a ? [year(ids.yearA), year(ids.prior)] : [year(ids.yearB)];
  const selected = saved['janso-fiscal-year']?.split('.');
  return { profile, session: { user: { id: 'fixture-user', name: 'Company Operator', secondary: 'Fixture organisation', theme: 'light', defaultCompanyId: ids.a }, organisation: { id: 'fixture-tenant', name: 'Fixture organisation', code: 'TEST' }, company, role: 'company operator', permissions: [...permissions, ...shared.flatMap(grant => grant.permissions)], companySource: 'explicit', stepUpCompanyId: null, companyScopes: [ids.a, ids.b], grants: [...shared, { permissions, scope_type: 'company', scope_id: company.id, valid_from: '2020-01-01', valid_to: null }], display: { currency: company.id === ids.a ? 'INR' : 'USD', timezone: 'Asia/Kolkata' } },
    context: { companies, companiesNote: null, fiscalYears: years, fiscalYear: years.find(item => selected?.[0] === company.id && item.id === selected?.[1]) ?? years[0], fiscalNote: null } };
}
const server = await createServer({ configFile: false, root, plugins: [react()], resolve: { alias: [{ find: /^@janso\/ui$/, replacement: resolve(root, '../../packages/ui/src/index.ts') }] }, server: { host: '127.0.0.1', port, strictPort: true, fs: { allow: [resolve(root, '../../..'), resolve(root, '../../../clients')] } }, appType: 'custom' });
server.middlewares.use(async (req, res, next) => {
  const reply = (value, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
  try {
    const url = new URL(req.url, origin);
    if (url.pathname.startsWith('/identity/') || url.pathname.startsWith('/accounting/')) {
      if (req.headers.authorization !== 'Bearer fixture-company-token') return reply({}, 401);
      const company = url.searchParams.get('company_id') ?? url.pathname.match(/\/companies\/([^/]+)/)?.[1];
      if (company && ![ids.a, ids.b].includes(company)) return reply({ error: { message: 'Company access denied' } }, 403);
      if (url.pathname === '/identity/v1/session') return reply({ company: { id: company } });
      if (url.pathname === '/identity/v1/session/companies') return reply({ items: companies.map(row => ({ ...row, display_name: row.name, is_default: !!row.isDefault, requires_step_up: false })), page: { has_more: false, next_cursor: null } });
      if (url.pathname.endsWith('/setup-readiness')) return reply({ company_id: company, company_status: 'active', first_posted_at: null, frozen_company_fields: [], features: [] });
      if (url.pathname.startsWith('/identity/')) return reply({ id: company, display_name: company === ids.a ? 'Company A' : 'Company B', code: company === ids.a ? 'A' : 'B', status: 'active', base_currency: company === ids.a ? 'INR' : 'USD', books_begin_date: '2026-04-01', default_tax_system: 'gst_in' });
      const requestedYear = url.pathname.match(/\/fiscal-years\/([^/]+)/)?.[1];
      if (requestedYear && !(company === ids.a ? [ids.yearA, ids.prior] : [ids.yearB]).includes(requestedYear)) return reply({ error: { message: 'Year access denied' } }, 403);
      if (url.pathname.endsWith('/readiness')) return reply({ fiscal_year_id: requestedYear, ready_for_posting: false, blockers: ['OPENING_NOT_FINALIZED'], periods: [{ id: 'fixture-period', code: 'Apr', status: 'OPEN' }] });
      if (requestedYear) return reply({ id: requestedYear, company_id: company });
      return reply({ id: 'fixture-books', company_id: company, base_currency: company === ids.a ? 'INR' : 'USD', books_begin_date: '2026-04-01', first_posted_at: null });
    }
    if (req.method === 'POST' && ['/api/company', '/api/company-context'].includes(url.pathname)) {
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      const { POST } = await server.ssrLoadModule('/app' + url.pathname + '/route.ts');
      const response = await POST(new NextRequest(origin + req.url, { method: 'POST', headers: req.headers, body: Buffer.concat(chunks).toString() }));
      res.writeHead(response.status, { 'Content-Type': 'application/json', 'Set-Cookie': response.headers.getSetCookie() }); res.end(await response.text()); return;
    }
    if (req.method !== 'GET' || !req.headers.accept?.includes('text/html')) return next();
    const config = configuration(req, url);
    const jwt = await encode({ secret: process.env.NEXTAUTH_SECRET, token: { accessToken: 'fixture-company-token', accessTokenExpires: Date.now() + 3600000 } });
    res.setHeader('Set-Cookie', ['next-auth.session-token=' + jwt + '; Path=/; HttpOnly; SameSite=Lax', 'company-fixture-profile=' + config.profile + '; Path=/; HttpOnly; SameSite=Lax']);
    const html = await server.transformIndexHtml(req.url, `<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body class="janso-root"><div id="root"></div><script>window.__COMPANY_FIXTURE__=${JSON.stringify(config)}</script><script type="module" src="/tests/company-foundation-e2e/main.tsx"></script></body></html>`);
    res.setHeader('Content-Type', 'text/html'); res.end(html);
  } catch (error) { console.error(error.stack); reply({ error: { message: 'Fixture host error' } }, 500); }
});
await server.listen(); console.log('Company foundation browser fixture ready on ' + port);
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await server.close(); process.exit(0); });
