/* Apply the reviewed fixed catalogue through the real platform UI, then verify QA grants. */
const path = require('node:path');
const { start } = require('./harness.cjs');

(async () => {
  const opening = process.argv.includes('--opening');
  const required = opening ? ['accounting.finance.manage', 'ledger.post_journal', 'period.post', 'accounting.export.read', 'opening_balance.read', 'opening_balance.manage', 'opening_balance.initialize_zero'] : ['report.read', 'report.export', 'report.definition.manage'];
  const h = await start(opening ? 'permanent-opening-authority' : 'permanent-role-authority');
  const { page, resources, assert } = h;
  try {
    const operator = h.privateLoad(path.join(h.output, 'platform-credentials.dpapi'));
    await h.login(page, operator.username, operator.password);
    resources.currentCompany = '';
    await h.test('ROLE-CATALOGUE-APPLY', 'Platform role catalogue', 'Open System role updates, review the canonical grant changes, enter a reason and apply', 'Permanent role seed applies through a fresh configured operator with one audited command', async () => {
      await h.ready('/platform/system-roles');
      await page.getByRole('heading', { name: 'Review role changes', exact: true }).waitFor({ timeout: 90000 });
      const plan = await h.call('platform', 'identity', '/v1/platform/system-roles');
      assert.equal(plan.status, 200);
      if (!plan.body.changes.length) return 'Shipped catalogue already applied; no additional write issued';
      const admin = plan.body.changes.find(change => change.key === 'tenant_admin');
      assert(admin && (opening ? required.every(key => admin.added.includes(key)) : admin.added.includes('report.export') && admin.added.includes('report.definition.manage')));
      assert(!admin.added.includes('vouchers.post') && !admin.added.includes('vouchers.approve'));
      await page.getByRole('textbox', { name: 'Reason for role update', exact: true }).fill(opening ? 'Apply user-approved permanent tenant administrator native opening authority' : 'Apply reviewed permanent tenant administrator reporting capabilities');
      const button = page.getByRole('button', { name: 'Apply reviewed role updates', exact: true });
      await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onSubmit === 'function'), await button.locator('xpath=ancestor::form').elementHandle(), { timeout: 90000 });
      const pending = page.waitForResponse(response => new URL(response.url()).pathname === '/api/platform' && response.request().postDataJSON()?.path === '/v1/platform/system-roles/reconcile');
      pending.catch(() => {});
      await button.click();
      const response = await pending;
      const result = await response.json();
      assert.equal(response.status(), 200, result.error?.message);
      assert.equal(result.changed, true);
      resources[opening ? 'permanentOpeningRoleReceipt' : 'permanentRoleReceipt'] = result;
      h.save();
      const request = response.request().postDataJSON();
      const replay = await h.call('platform', 'identity', request.path, request.method, request.body, request.key);
      assert.equal(replay.status, 200);
      assert.deepEqual(replay.body, result);
      await page.getByText('No role changes are pending.', { exact: true }).waitFor();
      await h.capture('permanent-role-catalogue-updated');
      return 'Reviewed fixed catalogue applied; exact replay returned the same receipt; ' + result.added_grants + ' grants added without assignment changes';
    }, 'LIVE_UI_WITH_API_READBACK');
    await h.context.clearCookies();
    const owner = h.privateLoad();
    await h.login(page, owner.username, owner.password);
    const read = await require('./identity_reader.cjs')(h);
    for (const company of resources.companies) {
      await h.switchCompany(company);
      await h.test('ROLE-' + (opening ? 'OPENING' : 'REPORT') + '-AUTHORITY-' + company.key, 'Tenant administrator capabilities', 'Read actual effective company authority after the canonical update', 'Required permanent permissions resolve for the same administrator', async () => {
        const response = await read('/v1/session?company_id=' + company.id);
        assert.equal(response.status, 200);
        const permissions = response.body.permissions;
        assert(Array.isArray(permissions));
        assert(required.every(key => permissions.includes(key)));
        return 'Existing QA administrator resolves permanent ' + (opening ? 'native opening capture/posting/export authority' : 'report read/create/export authority') + '; existing assignment retained';
      }, 'LIVE_AUTHENTICATED_API');
    }
    if (h.results.some(row => row.status !== 'PASS')) process.exitCode = 1;
  } catch (error) {
    await h.test('ROLE-AUTHORITY-RUN', 'Execution', 'Complete permanent role verification', 'Run completes', async () => { throw error; });
    process.exitCode = 1;
  } finally {
    h.save();
    await h.browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
