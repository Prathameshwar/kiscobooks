/* Authenticated Items delivery review. Secrets remain in protected local artifacts. */
const fs = require('node:fs'), path = require('node:path');
const { start, privateLoad } = require('../tenant-admin/harness.cjs');
const root = path.resolve(__dirname, '../../..');
const report = { observed_at: new Date().toISOString(), checks: [], errors: [], qa_records: [], dependency_recoveries: [] };
const selectedChecks = process.env.QA_CHECKS ? new Set(process.env.QA_CHECKS.split(',')) : null;
const publicFile = path.join(__dirname, selectedChecks ? 'review-recovery.json' : 'review.json');
let h;
async function check(name, work) {
  if (selectedChecks && !selectedChecks.has(name)) return;
  const row = { name };
  console.log('CHECK ' + name);
  try { Object.assign(row, await work(), { status: 'PASS' }); }
  catch (error) {
    row.status = 'FAIL'; row.failure_type = error.name; row.message = String(error.message).split('\n')[0].slice(0, 180);
    if (h) row.page_path = new URL(h.page.url()).pathname;
    if (h) await h.page.screenshot({ path: path.join(h.output, name + '-failure-private.png'), fullPage: true }).catch(() => {});
    if (h) fs.writeFileSync(path.join(h.output, name + '-controls-private.json'), JSON.stringify(await h.page.locator('[role=option]').evaluateAll(rows => rows.map(row => ({
      text: row.textContent, ancestors: Array.from((function* () { for (let el = row; el; el = el.parentElement) yield el; })()).map(el => ({ tag: el.tagName, role: el.getAttribute('role'), hidden: el.hidden, inert: el.inert, ariaHidden: el.getAttribute('aria-hidden'), display: getComputedStyle(el).display, visibility: getComputedStyle(el).visibility })),
    }))).catch(() => []), null, 2));
  }
  report.checks.push(row);
  console.log(JSON.stringify(row));
}
(async () => {
  h = await start('items-delivery');
  const { page, assert } = h;
  page.setDefaultTimeout(90000);
  const requests = [];
  page.on('response', async response => {
    if (new URL(response.url()).pathname !== '/api/product-fields') return;
    const input = response.request().postDataJSON();
    if (input?.service === 'catalog') requests.push({ method: input.method, path: input.path, status: response.status() });
  });
  const credentials = privateLoad(process.env.QA_CREDENTIAL_FILE || path.join(root, '.test_artifacts/purchase-api-local-20261031/credentials.dpapi'));
  await page.goto(h.auth + '/login');
  const continuation = page.getByRole('button', { name: 'Continue to sign in', exact: true });
  await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onClick === 'function'), await continuation.elementHandle());
  await continuation.click();
  const form = page.getByRole('form', { name: 'Sign in', exact: true });
  await form.waitFor();
  await page.waitForFunction(el => Object.keys(el).some(key => key.startsWith('__reactProps$') && typeof el[key]?.onSubmit === 'function'), await form.elementHandle());
  await page.getByRole('textbox', { name: /^(?:Username or email address|Email address)$/ }).fill(credentials.email ?? credentials.username);
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL(url => url.origin === h.origin || url.origin === h.auth && url.pathname === '/onboarding', { timeout: 60000 });
  async function open(route) {
    for (let attempt = 0; ; attempt++) {
      try {
        await page.goto(h.origin + route, { waitUntil: 'domcontentloaded' });
        break;
      } catch (error) {
        if (attempt >= 2 || !/ERR_ABORTED|interrupted by another navigation/.test(error.message)) throw error;
        report.dependency_recoveries.push({ route, control: 'Repeat interrupted read navigation' });
        await page.waitForLoadState('domcontentloaded');
      }
    }
    const heading = page.getByRole('heading', { level: 1 }).first();
    const retry = page.getByRole('button', { name: 'Retry settings', exact: true });
    await Promise.race([heading.waitFor({ timeout: 90000 }), retry.waitFor({ timeout: 90000 })]);
    if (await retry.isVisible()) {
      report.dependency_recoveries.push({ route, control: 'Retry settings' });
      await retry.click();
    }
    await heading.waitFor({ timeout: 90000 });
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  }
  function unrecovered(rows) {
    return rows.some((row, index) => row.status >= 400 && !(row.status === 503 && rows.slice(index + 1).some(next => next.method === row.method && next.path === row.path && next.status < 400)));
  }
  await check('authenticated-directory', async () => {
    await open('/masters/items?returnTo=%2Fmasters');
    await page.getByRole('heading', { name: 'Products', exact: true }).waitFor();
    await page.getByRole('searchbox', { name: 'Search', exact: true }).waitFor();
    assert(!unrecovered(requests), 'Catalog directory requests failed');
    return { catalog_requests: requests.length };
  });
  await check('short-search-bookmark', async () => {
    const before = requests.length;
    await open('/masters/items?q=x&returnTo=%2Fmasters');
    assert(!unrecovered(requests.slice(before)), 'Short bookmarked search triggered a rejected Catalog request');
  });
  await check('new-product-form', async () => {
    const before = requests.length;
    await open('/masters/items/new?returnTo=%2Fmasters%2Fitems');
    await page.getByRole('button', { name: 'Create product', exact: true }).waitFor({ timeout: 90000 });
    assert(!unrecovered(requests.slice(before)), 'New-product dependencies failed');
    const labels = await page.locator('main label').allTextContents();
    return { field_labels: labels.map(label => label.trim()).filter(Boolean), notices: await page.locator('main [role=alert]').allTextContents() };
  });
  const identity = await require('../tenant-admin/identity_reader.cjs')(h);
  const companies = await identity('/v1/companies?limit=50');
  assert.equal(companies.status, 200); h.resources.companies = companies.body.items.map(company => ({ id: company.id }));
  report.company_count = h.resources.companies.length;
  if (h.resources.companies.length === 1) {
    report.company_id = h.resources.companies[0].id;
    const catalog = await require('../tenant-admin/identity_reader.cjs')(h, 'catalog');
    for (const resource of ['products', 'product-types', 'units']) {
      const result = await catalog('/v1/companies/' + report.company_id + '/' + resource + '?limit=50');
      report[resource.replace('-', '_')] = { status: result.status, count: result.body.items?.length };
    }
    const recordFile = path.join(h.output, 'qa-product.json');
    let qa = fs.existsSync(recordFile) ? JSON.parse(fs.readFileSync(recordFile, 'utf8')) : null;
    const directory = '/masters/items?status=DRAFT&sort=-name&returnTo=%2Fmasters';
    async function choose(label, query) {
      console.log('SELECT ' + label);
      const control = page.getByRole('combobox', { name: label, exact: true });
      await control.click();
      if (await control.evaluate(el => el.tagName === 'SELECT')) await control.selectOption(query);
      else {
        await control.fill(query);
        const option = page.getByRole('listbox', { name: label + ' results', exact: true }).getByRole('option').first();
        await option.waitFor(); await option.click();
      }
    }
    async function submit(control, suffix) {
      const pending = page.waitForResponse(response => {
        if (new URL(response.url()).pathname !== '/api/product-fields') return false;
        const input = response.request().postDataJSON();
        return input?.service === 'catalog' && input.method === 'POST' && input.path.endsWith(suffix);
      }); pending.catch(() => {});
      await control.click();
      const response = await pending, body = await response.json();
      assert(response.ok(), response.status() + ': ' + body.error?.message);
      return body;
    }
    const typeFile = path.join(h.output, 'qa-product-type.json');
    let qaType = fs.existsSync(typeFile) ? JSON.parse(fs.readFileSync(typeFile, 'utf8')) : null;
    await check('create-selectable-qa-type', async () => {
      if (qaType?.published_at) return { reused_qa_type: true, id: qaType.id };
      if (qaType) throw new Error('An unfinished QA type is preserved; resume its requirements instead of creating another type');
      await open('/masters/items/new?returnTo=' + encodeURIComponent(directory));
      await page.getByRole('textbox', { name: 'Product name', exact: true }).fill('QA draft preserved during type setup');
      await page.getByRole('button', { name: 'New product type', exact: true }).click();
      const drawer = page.getByRole('dialog', { name: 'New product type', exact: true });
      await drawer.waitFor();
      const stamp = Date.now().toString(36).toUpperCase();
      await drawer.getByRole('textbox', { name: 'Code', exact: true }).fill('QART-' + stamp);
      await drawer.getByRole('textbox', { name: 'Name', exact: true }).fill('QA delivery type ' + stamp);
      qaType = await submit(drawer.getByRole('button', { name: 'Create product type', exact: true }), '/product-types');
      assert.equal(qaType.company_id, report.company_id);
      fs.writeFileSync(typeFile, JSON.stringify(qaType, null, 2));
      await drawer.getByRole('button', { name: 'Save draft requirements', exact: true }).waitFor();
      const metadata = await catalog('/v1/companies/' + report.company_id + '/entities/catalog.product_type_revision/field-set?operation=create');
      assert.equal(metadata.status, 200);
      for (const [key, selected] of [['inventory_modes', 'NON_STOCK'], ['tracking_modes', 'NONE'], ['unit_dimensions', 'COUNT']]) {
        const field = metadata.body.fields.find(field => field.key === key); assert(field?.control);
        for (const choice of field.control.choices || []) {
          const control = drawer.getByRole('checkbox', { name: choice.label, exact: true });
          if (await control.count()) await control.setChecked(choice.value === selected);
        }
      }
      const revision = await submit(drawer.getByRole('button', { name: 'Save draft requirements', exact: true }), '/product-types/' + qaType.id + '/revisions');
      qaType.revision_id = revision.id; fs.writeFileSync(typeFile, JSON.stringify(qaType, null, 2));
      await drawer.getByRole('button', { name: 'Publish requirements', exact: true }).click();
      const confirmation = page.getByRole('dialog', { name: 'Publish product type requirements?', exact: true });
      await confirmation.waitFor();
      const published = await submit(confirmation.getByRole('button', { name: 'Publish requirements', exact: true }), '/revisions/' + revision.id + '/publish');
      assert(published.published_at); qaType.published_at = published.published_at;
      fs.writeFileSync(typeFile, JSON.stringify(qaType, null, 2));
      await drawer.waitFor({ state: 'hidden' });
      assert.equal(await page.getByRole('textbox', { name: 'Product name', exact: true }).inputValue(), 'QA draft preserved during type setup');
      return { id: qaType.id, revision_id: revision.id, qa_only_requirements_published: true, parent_draft_preserved: true };
    });
    const groupFile = path.join(h.output, 'qa-product-group.json');
    let qaGroup = fs.existsSync(groupFile) ? JSON.parse(fs.readFileSync(groupFile, 'utf8')) : null;
    await check('create-selectable-qa-group', async () => {
      if (qaGroup) { assert.equal(qaGroup.company_id, report.company_id); return { reused_qa_group: true, id: qaGroup.id }; }
      await open('/masters/items/new?returnTo=' + encodeURIComponent(directory));
      await page.getByRole('textbox', { name: 'Product name', exact: true }).fill('QA draft preserved during group setup');
      await page.getByRole('button', { name: 'New product group', exact: true }).click();
      const drawer = page.getByRole('dialog', { name: 'New product group', exact: true });
      const stamp = Date.now().toString(36).toUpperCase();
      await drawer.getByRole('textbox', { name: 'Code', exact: true }).fill('QARG-' + stamp);
      await drawer.getByRole('textbox', { name: 'Name', exact: true }).fill('QA delivery group ' + stamp);
      qaGroup = await submit(drawer.getByRole('button', { name: 'Create item group', exact: true }), '/item-groups');
      assert.equal(qaGroup.company_id, report.company_id); assert.equal(qaGroup.is_active, true);
      fs.writeFileSync(groupFile, JSON.stringify(qaGroup, null, 2));
      await drawer.waitFor({ state: 'hidden' });
      assert.equal(await page.getByRole('textbox', { name: 'Product name', exact: true }).inputValue(), 'QA draft preserved during group setup');
      return { id: qaGroup.id, parent_draft_preserved: true };
    });
    report.qa_setup = { product_type: { id: qaType?.id, revision_id: qaType?.revision_id, published_at: qaType?.published_at }, product_group: { id: qaGroup?.id } };
    await check('create-product-draft', async () => {
      if (qa) { assert.equal(qa.company_id, report.company_id); return { reused_qa_draft: true, id: qa.id }; }
      await open('/masters/items/new?returnTo=' + encodeURIComponent(directory));
      await choose('Kind', 'GOODS');
      const stamp = Date.now().toString(36).toUpperCase();
      const name = 'QA delivery AC/DC ' + stamp;
      await page.getByRole('textbox', { name: 'Product name', exact: true }).fill(name);
      await page.getByRole('textbox', { name: 'Product code', exact: true }).fill('QAREV-' + stamp);
      await choose('Published product type', qaType?.name || 'QA delivery type');
      await choose('Base unit', 'Piece');
      await choose('Primary product group', qaGroup?.name || 'QA delivery group');
      const response = page.waitForResponse(response => {
        if (new URL(response.url()).pathname !== '/api/product-fields') return false;
        const request = response.request().postDataJSON(); return request?.service === 'catalog' && request.method === 'POST' && request.path.endsWith('/products');
      });
      response.catch(() => {});
      await page.getByRole('button', { name: 'Create product', exact: true }).click();
      const result = await response, body = await result.json(); assert.equal(result.status(), 201, body.error?.message);
      assert.equal(body.company_id, report.company_id); assert.equal(body.status, 'DRAFT');
      qa = { id: body.id, company_id: body.company_id, code: body.code, name: body.name, status: body.status };
      fs.writeFileSync(recordFile, JSON.stringify(qa, null, 2)); report.qa_records.push(qa);
      await page.getByRole('heading', { name: 'Product created', exact: true }).waitFor();
      return { id: qa.id, draft_status: body.status };
    });
    if (qa) {
      if (!report.qa_records.length) report.qa_records.push(qa);
      await check('saved-detail-reload', async () => {
        await open('/masters/items/' + qa.id + '?returnTo=' + encodeURIComponent(directory));
        await page.getByRole('heading', { level: 1, name: qa.name, exact: true }).waitFor();
        const row = await catalog('/v1/companies/' + report.company_id + '/products/' + qa.id);
        assert.equal(row.status, 200); assert.equal(row.body.company_id, report.company_id); assert.equal(row.body.name, qa.name);
      });
      await check('edit-draft-and-reload', async () => {
        await open('/masters/items/' + qa.id + '?returnTo=' + encodeURIComponent(directory));
        console.log('EDIT detail ' + new URL(page.url()).pathname);
        await page.getByRole('link', { name: 'Edit product', exact: true }).click({ timeout: 90000 });
        console.log('EDIT form ' + new URL(page.url()).pathname);
        const control = page.getByRole('textbox', { name: 'Product name', exact: true });
        await control.waitFor({ timeout: 90000 });
        const revised = qa.name.endsWith(' reviewed')
          ? qa.name.replace(/ reviewed$/, ' verified')
          : qa.name.replace(/ verified$/, '') + ' reviewed';
        assert.notEqual(revised, qa.name, 'The retained QA fixture must actually change');
        await control.fill(revised);
        const response = page.waitForResponse(response => {
          if (new URL(response.url()).pathname !== '/api/product-fields') return false;
          const request = response.request().postDataJSON(); return request?.method === 'PATCH' && request.path.endsWith('/products/' + qa.id);
        }); response.catch(() => {});
        await page.getByRole('button', { name: 'Save changes', exact: true }).click();
        console.log('EDIT save ' + new URL(page.url()).pathname);
        const result = await response, body = await result.json(); assert.equal(result.status(), 200, body.error?.message);
        qa.name = body.name; fs.writeFileSync(recordFile, JSON.stringify(qa, null, 2));
        await page.getByRole('heading', { name: 'Product updated', exact: true }).waitFor();
        await page.getByRole('link', { name: 'View product', exact: true }).click();
        await page.getByRole('heading', { level: 1, name: qa.name, exact: true }).waitFor();
        await page.reload(); await page.getByRole('heading', { level: 1, name: qa.name, exact: true }).waitFor();
        const back = new URL(await page.getByRole('link', { name: 'Back to previous page', exact: true }).getAttribute('href'), h.origin);
        assert.equal(back.pathname, '/masters/items'); assert.equal(back.searchParams.get('status'), 'DRAFT');
        const persisted = await catalog('/v1/companies/' + report.company_id + '/products/' + qa.id);
        assert.equal(persisted.body.name, qa.name);
      });
      await check('punctuation-search-and-mobile', async () => {
        const before = requests.length;
        await open(directory + '&q=' + encodeURIComponent('QA delivery AC/DC'));
        await page.getByRole('link', { name: qa.name, exact: true }).waitFor();
        assert(!unrecovered(requests.slice(before)), 'Search requests failed');
        await page.setViewportSize({ width: 390, height: 844 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile page overflows its viewport');
        await page.screenshot({ path: path.join(h.output, 'products-mobile-private.png'), fullPage: true });
        await page.setViewportSize({ width: 1440, height: 1000 });
      });
      await check('filtered-detail-return', async () => {
        await open('/masters/items/' + qa.id + '?returnTo=' + encodeURIComponent(directory));
        const back = page.getByRole('link', { name: 'Back to previous page', exact: true });
        const target = new URL(await back.getAttribute('href'), h.origin);
        assert.equal(target.pathname, '/masters/items');
        assert.equal(target.searchParams.get('status'), 'DRAFT'); assert.equal(target.searchParams.get('sort'), '-name');
        await back.click(); await page.getByRole('heading', { name: 'Products', exact: true }).waitFor();
        assert.equal(await page.getByRole('combobox', { name: 'Status', exact: true }).inputValue(), 'DRAFT');
        assert.equal(await page.getByRole('combobox', { name: 'Sort by', exact: true }).inputValue(), '-name');
      });
    }
  }
  await check('company-settings-voucher-types', async () => {
    await open('/settings');
    const card = page.getByRole('link', { name: 'Voucher types', exact: true });
    await card.waitFor(); assert.equal(await card.getAttribute('href'), '/masters/voucher-types');
    await card.click(); await page.getByRole('heading', { name: 'Voucher types', exact: true }).waitFor();
    await page.getByRole('link', { name: 'New voucher type', exact: true }).waitFor();
    return { route: '/settings', voucher_type_creation_discoverable: true };
  });
  await check('directory-network-failure-recovery', async () => {
    let interrupted = false;
    const intercept = async route => {
      const input = route.request().postDataJSON();
      if (!interrupted && input?.service === 'catalog' && input.method === 'GET' && /\/products\?/.test(input.path)) {
        interrupted = true; await route.abort('connectionfailed');
      } else await route.continue();
    };
    await page.route('**/api/product-fields', intercept);
    try {
      await open('/masters/items?returnTo=%2Fmasters');
      await page.getByRole('button', { name: 'Retry loading', exact: true }).waitFor({ timeout: 90000 });
      assert(interrupted, 'The intended read was not interrupted');
      assert.equal(await page.getByText('No products yet', { exact: true }).count(), 0);
      await page.getByRole('button', { name: 'Retry loading', exact: true }).click();
      await page.getByRole('table', { name: 'Products', exact: true }).waitFor({ timeout: 90000 });
      return { actual_network_interruption: true, retry_used_native_catalog: true };
    } finally { await page.unroute('**/api/product-fields', intercept); }
  });
  await check('mobile-validation-keyboard-and-discard', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await open('/masters/items/new?returnTo=%2Fmasters%2Fitems');
    const name = page.getByRole('textbox', { name: 'Product name', exact: true });
    await name.focus(); await page.keyboard.press('Tab');
    assert(await page.getByRole('textbox', { name: 'Product code', exact: true }).evaluate(el => el === document.activeElement), 'Keyboard order skips product code');
    await page.getByRole('button', { name: 'Create product', exact: true }).click();
    assert.equal(await name.getAttribute('aria-invalid'), 'true', 'Required name validation is missing');
    assert(await name.evaluate(el => el === document.activeElement), 'Invalid field is not focused');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile form overflows');
    await name.fill('QA unsaved draft to discard');
    await page.getByRole('link', { name: /^Back to/ }).first().click();
    const dialog = page.getByRole('dialog', { name: 'Discard unsaved changes?', exact: true });
    await dialog.waitFor(); await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    assert.equal(await name.inputValue(), 'QA unsaved draft to discard');
    await page.screenshot({ path: path.join(h.output, 'product-form-mobile-private.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
  });
  await page.screenshot({ path: path.join(h.output, 'new-product-private.png'), fullPage: true });
})().catch(error => {
  report.errors.push({ type: error.name, message: String(error.message).split('\n')[0].slice(0, 180) });
}).finally(async () => {
  if (h) await h.browser.close();
  fs.writeFileSync(publicFile, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ checks: report.checks.length, failed: report.checks.filter(row => row.status === 'FAIL').length, errors: report.errors.length }));
  process.exitCode = report.errors.length || report.checks.some(row => row.status === 'FAIL') ? 1 : 0;
});
