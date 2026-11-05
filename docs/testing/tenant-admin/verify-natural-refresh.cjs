/* Wait for the real provider access-token expiry; do not edit any token or cookie. */
const fs = require('node:fs');
const path = require('node:path');
const { start } = require('./harness.cjs');

(async () => {
  const h = await start('pending-8-refresh');
  try {
    const owner = h.privateLoad();
    await h.login(h.page, owner.username, owner.password);
    const company = h.resources.companies[0];
    await h.switchCompany(company);
    const configuration = Object.fromEntries(fs.readFileSync(path.join(h.root, 'mfes/apps/auth/.env.local'), 'utf8').split(/\r?\n/).filter(line => line.includes('=') && !line.trimStart().startsWith('#')).map(line => { const index = line.indexOf('='); return [line.slice(0, index), line.slice(index + 1).replace(/^(['"])(.*)\1$/, '$2')]; }));
    const { decode } = require(path.join(h.root, 'mfes/apps/auth/node_modules/next-auth/jwt'));
    async function expiry() {
      const cookies = await h.context.cookies();
      const name = cookies.some(c => c.name.startsWith('next-auth.session-token')) ? 'next-auth.session-token' : '__Secure-next-auth.session-token';
      const pieces = cookies.filter(c => c.name === name || c.name.startsWith(name + '.')).sort((a, b) => Number(a.name.slice(name.length + 1) || 0) - Number(b.name.slice(name.length + 1) || 0));
      const token = await decode({ token: pieces.map(c => c.value).join(''), secret: configuration.NEXTAUTH_SECRET });
      h.assert(Number.isFinite(token?.accessTokenExpires), 'Actual provider expiry metadata is unavailable');
      return token.accessTokenExpires;
    }
    await h.test('P8-NATURAL-REFRESH', 'Authentication', 'Wait for the real access-token expiry, observe refusal, refresh through Auth and retry the same read', 'Natural expiry is enforced and real refresh restores the authorized read without exposing tokens', async () => {
      const before = await expiry();
      h.assert(before <= Date.now() + 3600000, 'Provider expiry exceeds the one-hour evidence window');
      console.log('Waiting for real provider expiry at ' + new Date(before).toISOString());
      while (Date.now() <= before + 1000) await new Promise(resolve => setTimeout(resolve, Math.min(15000, Math.max(1000, before + 1001 - Date.now()))));
      const input = { service: 'accounting', path: '/v1/companies/' + company.id + '/stock/configuration', method: 'GET' };
      const read = () => h.page.request.post(h.origin + '/api/product-fields', { headers: { Origin: h.origin }, data: input });
      const refused = await read();
      h.assert.equal(refused.status(), 401);
      h.assert.equal((await refused.json()).error.code, 'session_expired');
      const refreshed = await h.page.request.post(h.auth + '/api/session/refresh', { headers: { Origin: h.origin }, data: {} });
      h.assert.equal(refreshed.status(), 200);
      const reply = await refreshed.json();
      h.assert.equal(reply.authenticated, true);
      h.assert(!('accessToken' in reply) && !('refreshToken' in reply));
      h.assert.equal((await read()).status(), 200);
      h.assert((await expiry()) > before);
      return 'Naturally expired cookie refused with 401; real Auth refresh and identical company read succeeded; credentials remained private';
    }, 'LIVE_PROVIDER_EXPIRY_AND_AUTHENTICATED_API');
    if (h.results.some(r => r.status !== 'PASS')) process.exitCode = 1;
  } catch (error) {
    await h.test('P8-REFRESH-RUNNER', 'Execution', 'Complete natural expiry check', 'Run completes', async () => { throw error; });
    process.exitCode = 1;
  } finally {
    h.save();
    await h.browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
