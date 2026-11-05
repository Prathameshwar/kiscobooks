/* Explicit opt-in live writes, exclusively to new QA records. No secrets saved. */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
module.exports = async function ({ page, context, origin, results, output }) {
  const fs = require('node:fs'), path = require('node:path');
  const stamp = Date.now().toString(36);
  const resources = { marker: 'QA Platform ' + stamp, tenant: null, price: null };
  let disposableCredentials;
  const call = (apiPath, method = 'GET', body, key) => page.evaluate(async input => {
    const response = await fetch('/api/platform', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal: AbortSignal.timeout(30000) });
    return { status: response.status, body: await response.json() };
  }, { service: 'identity', path: apiPath, method, ...(body ? { body } : {}), ...(key ? { key } : {}) });
  const cases = async (id, run) => {
    try { const detail = await run(); results.push({ id, result: 'PASS', actual: detail }); }
    catch (error) { results.push({ id, result: 'FAIL', actual: String(error) }); }
    console.log(JSON.stringify(results.at(-1)));
    fs.writeFileSync(path.join(output, 'qa-resources.json'), JSON.stringify(resources, null, 2));
  };
  await page.goto(origin + '/platform');
  await cases('LIVE-TENANT-CREATE-REPLAY', async () => {
    const choices = await call('/v1/platform/tenant-options');
    assert.equal(choices.status, 200);
    const country = choices.body.countries.find(item => item.code === 'IN') || choices.body.countries[0];
    const state = choices.body.states.find(item => item.country_code === country.code);
    const body = { name: resources.marker, country_code: country.code, state_code: state?.code || null, administrator_name: 'QA Disposable Owner', administrator_email: `qa-platform-${stamp}@example.invalid`, administrator_password: crypto.randomBytes(24).toString('base64url'), recipient_confirmed: true };
    const key = crypto.randomUUID();
    const created = await call('/v1/platform/tenants', 'POST', body, key);
    assert.equal(created.status, 201, JSON.stringify(created.body.error || { status: created.status }));
    resources.tenant = created.body.id;
    disposableCredentials = { username: created.body.administrator_username, password: body.administrator_password };
    const replay = await call('/v1/platform/tenants', 'POST', body, key);
    assert.equal(replay.status, 201);
    assert.equal(replay.body.id, resources.tenant);
    assert.equal(replay.body.administrator_password, null);
    return 'Created a disposable tenant through the live provider and DB; replay returned the same ID without the password';
  });
  if (resources.tenant) {
    const tenantPath = '/v1/platform/tenants/' + resources.tenant;
    await cases('LIVE-TENANT-DETAIL-EDIT', async () => {
      const edited = await call(tenantPath, 'PATCH', { name: resources.marker + ' reviewed' });
      assert.equal(edited.status, 200);
      await page.goto(origin + '/platform/tenants/' + resources.tenant);
      await page.getByRole('main').getByRole('heading', { name: resources.marker + ' reviewed', exact: true }).waitFor();
      return 'Live edit persisted and rendered on the full tenant detail page';
    });
    await cases('LIVE-ADMIN-LAST-OWNER-AND-INVITATION', async () => {
      const base = '/v1/platform/access/tenants/' + resources.tenant + '/administrators';
      const roster = await call(base);
      assert.equal(roster.status, 200);
      assert.equal(roster.body.items.length, 1);
      const owner = await call(base + '/' + roster.body.items[0].id);
      resources.administrator = owner.body.id;
      const command = (detail, action) => ({ action, reason: 'QA disposable access verification', expected_updated_at: detail.updated_at, expected_assignment_updated_at: detail.assignment_updated_at });
      const blocked = await call(base + '/' + owner.body.id + '/commands', 'POST', command(owner.body, 'revoke'), crypto.randomUUID());
      assert.equal(blocked.status, 409);
      const invitation = await call(base, 'POST', { display_name: 'QA Disposable Backup', email: `qa-backup-${stamp}@example.invalid`, reason: 'QA disposable invitation verification' }, crypto.randomUUID());
      assert.equal(invitation.status, 201, JSON.stringify(invitation.body.error || {}));
      const target = base + '/' + invitation.body.administrator_id;
      for (const action of ['resend_invitation', 'revoke', 'restore', 'revoke']) {
        const detail = await call(target);
        const changed = await call(target + '/commands', 'POST', command(detail.body, action), crypto.randomUUID());
        assert.equal(changed.status, 200, action + ': ' + JSON.stringify(changed.body.error || {}));
      }
      const wrong = await call('/v1/platform/access/tenants/' + crypto.randomUUID() + '/administrators/' + owner.body.id);
      assert.equal(wrong.status, 404);
      return 'Last-owner revocation refused; backup invite/resend/revoke/restore passed; wrong-tenant lookup refused; backup left revoked';
    });
    await cases('LIVE-DISPOSABLE-ADMIN-RECOVERY-LINK', async () => {
      assert(resources.administrator, 'Administrator roster must load first');
      const base = '/v1/platform/access/tenants/' + resources.tenant + '/administrators/' + resources.administrator;
      const detail = await call(base);
      assert(detail.body.recovery_deliveries.includes('link'), 'Native provider recovery is unavailable for the disposable administrator');
      const result = await call(base + '/password-recovery', 'POST', { delivery: 'link', reason: 'QA disposable recovery verification', expected_updated_at: detail.body.updated_at, expected_assignment_updated_at: detail.body.assignment_updated_at });
      assert.equal(result.status, 200, JSON.stringify(result.body.error || {}));
      const url = new URL(result.body.recovery_url);
      assert.equal(url.protocol, 'https:');
      assert.equal(url.pathname, '/if/flow/bill-administrator-recovery/');
      assert(url.searchParams.get('flow_token'));
      assert(Date.parse(result.body.expires_at) > Date.now());
      assert(Date.parse(result.body.expires_at) <= Date.now() + 10 * 60 * 1000);
      if (process.env.QA_RECOVERY_COMPLETE === '1') {
        return await require('./live_recovery.cjs')({ browser: context.browser(), origin, output, link: result.body.recovery_url, credentials: disposableCredentials });
      }
      return 'Native provider issued a bounded HTTPS recovery link for the disposable account; link was neither saved nor consumed; no password changed';
    });
    await cases('LIVE-TENANT-LIFECYCLE-REPLAY-STALE', async () => {
      for (const status of ['suspended', 'active', 'suspended']) {
        const before = await call(tenantPath);
        const key = crypto.randomUUID();
        const body = { status, reason: 'QA disposable lifecycle verification', expected_updated_at: before.body.updated_at };
        const changed = await call(tenantPath + '/lifecycle', 'POST', body, key);
        assert.equal(changed.status, 200);
        assert.equal(changed.body.status, status);
        const replay = await call(tenantPath + '/lifecycle', 'POST', body, key);
        assert.deepEqual(replay.body, changed.body);
        const stale = await call(tenantPath + '/lifecycle', 'POST', { ...body, status: status === 'active' ? 'suspended' : 'active' }, crypto.randomUUID());
        assert.equal(stale.status, 409);
      }
      return 'Deactivate/activate/deactivate, exact replay and stale revision refusal passed; QA tenant left suspended';
    });
  }
  await cases('LIVE-PRICING-CRUD-REVISIONS', async () => {
    const body = { code: 'qa-' + stamp, name: resources.marker, category: 'platform', term_months: 12, unit: 'none', monthly_fee: '449', is_active: false };
    const created = await call('/v1/platform/pricing', 'POST', body);
    assert.equal(created.status, 201, JSON.stringify(created.body.error || {}));
    resources.price = created.body.id;
    const base = '/v1/platform/pricing/' + resources.price;
    const changed = await call(base, 'PATCH', { ...body, monthly_fee: '389', expected_version: 1 });
    assert.equal(changed.status, 200);
    assert.equal(changed.body.prices[0].term_total, '5508.24');
    for (const [action, version] of [['delete', 2], ['restore', 3], ['delete', 4]]) {
      const result = await call(base + '/' + action, 'POST', { expected_version: version });
      assert.equal(result.status, 200);
    }
    const revisions = await call(base + '/revisions');
    assert.equal(revisions.status, 200);
    assert.equal(revisions.body.items.length, 5);
    return 'Inactive QA price create/edit/delete/restore/delete and five revisions passed; tax total exact; QA price left deleted';
  });
  await cases('LIVE-AUDIT-DELIVERY', async () => {
    assert(resources.tenant, 'Tenant creation must pass before delivery can be checked');
    let count = 0;
    for (let attempt = 0; attempt < 6; attempt++) {
      const response = await page.evaluate(async id => {
        const result = await fetch('/api/audit/v1/platform-events?entity_id=' + id + '&limit=50');
        return { status: result.status, body: await result.json() };
      }, resources.tenant);
      assert.equal(response.status, 200, JSON.stringify(response.body.error || {}));
      count = response.body.items.length;
      if (count) break;
      await page.waitForTimeout(5000);
    }
    assert(count > 0, 'No QA tenant platform event was delivered within 30 seconds');
    return `Observed ${count} delivered platform events for the QA tenant in the Audit API`;
  });
  if (process.env.QA_CORE_ONLY === '1') return;
  await require('./live_reads.cjs')({ page, context, origin, output, results });
};
