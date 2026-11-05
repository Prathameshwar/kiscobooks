/* Read-only browser review. Retained tenant/company fixtures; never submit business writes.
 * Run from repository root: node docs/testing/tenant-admin/review-ui.cjs
 * QA_UI_REVIEW_PART=screens|workflows|details|remaining|payment-recheck; outputs stay in ignored .test_artifacts.
 * Browser-intercepted responses are labelled separately from live acceptance evidence.
 */
const fs = require('node:fs');
const path = require('node:path');
const { start } = require('./harness.cjs');
(async () => {
  const part = process.env.QA_UI_REVIEW_PART || 'screens';
  const reviewDate = process.env.QA_REVIEW_DATE || new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(reviewDate)) throw new Error('QA_REVIEW_DATE must use YYYY-MM-DD');
  const h = await start('ui-review-' + part), { page, assert } = h;
  const rows = [], observations = [], interceptedWrites = [];
  const file = path.join(h.output, 'ui-review-' + part + '.json');
  const save = () => fs.writeFileSync(file, JSON.stringify({ part, rows, observations, interceptedWrites, errors: h.errors, network: h.network }, null, 2));
  const guard = async route => {
    let data; try { data = route.request().postDataJSON(); } catch { return route.continue(); }
    if (data?.method && data.method !== 'GET' && !/\/(?:invoice-preview|validate)$/.test(data.path || '')) {
      interceptedWrites.push({ service: data.service, path: data.path, method: data.method });
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'REVIEW_WRITE_BLOCKED', message: 'Review only: the business write was intercepted; no record was changed.' } }) });
    }
    return route.continue();
  };
  async function check(id, route, run, level = 'LIVE_UI') {
    console.log('START ' + id);
    const row = { id, route, company: h.resources.currentCompany, execution_level: level, started_utc: new Date().toISOString() };
    try { row.actual = await run(); row.status = 'PASS'; }
    catch (error) { row.actual = error.message; row.status = error.blocked || /No retained active .* type/.test(error.message) ? 'BLOCKED' : 'FAIL'; row.evidence = await h.capture('UIR-' + id + '-failure'); }
    rows.push(row); save(); console.log(JSON.stringify(row));
  }
  async function click(name) {
    const control = page.getByRole('button', { name, exact: true });
    await control.waitFor();
    await page.waitForFunction(el => Object.keys(el).some(k => k.startsWith('__reactProps$') && typeof el[k]?.onClick === 'function'), await control.elementHandle(), { timeout: 60000 });
    await control.click();
  }
  async function snapshot(id, route, widths = [1440, 768, 390]) {
    await page.waitForFunction(() => ![...document.querySelectorAll('main .janso-skeleton, main [aria-busy=true], main [role=status][aria-label^="Loading"]')].some(el => el.getBoundingClientRect().height && getComputedStyle(el).visibility !== 'hidden'), null, { timeout: 90000 }).catch(() => {});
    for (const width of widths) {
      await page.setViewportSize({ width, height: 1000 });
      await page.waitForTimeout(300);
      const geometry = await page.evaluate(() => {
        const main = document.querySelector('main') || document.body;
        const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
        const box = el => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) }; };
        return {
          documentWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth,
          title: document.title, heading: main.querySelector('h1')?.textContent,
          controls: [...main.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,button')].filter(visible).map(el => ({ tag: el.tagName, label: el.getAttribute('aria-label') || el.labels?.[0]?.textContent || el.textContent?.trim().slice(0, 90), disabled: el.disabled, ...box(el) })),
          fieldsets: [...main.querySelectorAll('fieldset')].filter(visible).map(el => ({ class: el.className, legend: el.querySelector('legend')?.textContent, border: getComputedStyle(el).borderTop, padding: getComputedStyle(el).padding, ...box(el) })),
          alerts: [...main.querySelectorAll('[role=alert],[role=status]')].map(el => ({ role: el.getAttribute('role'), text: el.textContent?.slice(0, 500) })),
        };
      });
      const evidence = await h.capture('UIR-' + id + '-' + width);
      observations.push({ id, route, company: h.resources.currentCompany, width, evidence, geometry }); save();
      console.log('CAPTURE ' + id + ' ' + width + ' overflow=' + (geometry.scrollWidth - geometry.documentWidth));
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  async function prepare(kind, company) {
    await h.ready('/vouchers/new/' + kind.toLowerCase()); await click('Load voucher types');
    await page.waitForFunction(el => !el.disabled, await page.getByRole('button', { name: 'Load voucher types', exact: true }).elementHandle(), { timeout: 90000 });
    const id = kind === 'PURCHASE' ? company.purchaseType : company.moneyTypes?.[kind];
    const select = page.getByRole('combobox', { name: 'Voucher type', exact: true });
    if (id) await select.selectOption(id); else {
      const available = await select.locator('option').evaluateAll(options => options.map(o => o.value).filter(Boolean));
      assert(available.length, 'No retained active ' + kind + ' type'); await select.selectOption(available[0]);
    }
    await page.getByLabel('Document date', { exact: true }).fill(reviewDate); await click('Load entry fields');
    await page.getByRole('button', { name: 'Save draft', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Load entry fields', exact: true }).waitFor({ state: 'visible' });
    await page.waitForFunction(el => !el.disabled, await page.getByRole('button', { name: 'Load entry fields', exact: true }).elementHandle(), { timeout: 90000 });
    if (kind === 'PURCHASE') await click('Add purchase line');
  }
  try {
    const owner = h.privateLoad(); await h.login(page, owner.username, owner.password);
    await page.route('**/api/product-fields', guard);
    const companies = h.resources.companies;
    await h.switchCompany(companies[0]);
    if (part === 'screens') {
      const routes = [
        ['overview', '/'], ['companies', '/companies'], ['recovery-unavailable', '/session-recovery?reason=unavailable&returnTo=%2Fmasters%2Fitems'],
        ['recovery-access', '/session-recovery?reason=access&returnTo=%2Fmasters%2Fitems'], ['audit', '/audit'], ['activity', '/activity'],
        ['items', '/masters/items?returnTo=%2Fmasters'], ['accounts', '/accounting/accounts'], ['parties', '/accounting/parties'],
        ['opening', '/accounting/opening'], ['attributes', '/products/attributes'], ['product-config', '/products/configuration?scope_kind=SKU&item_id=' + companies[0].product],
        ['reports-hub', '/reports'], ['books-hub', '/books'], ['cash-book', '/books/cash-book'], ['report-workspace', '/reports/workspace?report=CASH_BOOK'],
        ['stock', '/inventory/stock'], ['stock-adjustment', '/vouchers/new/stock-adjustment'], ['sales', '/vouchers/new/sales'],
        ['voucher-drafts', '/vouchers'], ['users-new', '/users/new'], ['notifications', '/settings/notifications'], ['readiness', '/settings/readiness'],
      ];
      for (const [id, route] of routes) await check('SCREEN-' + id, route, async () => {
        const response = await h.ready(route); await snapshot(id, route);
        return { response: response?.status(), landedPath: new URL(page.url()).pathname, heading: await page.locator('main h1').first().textContent().catch(() => '') };
      });
      for (const company of companies) {
        await h.switchCompany(company);
        for (const kind of ['RECEIPT', 'PAYMENT', 'PURCHASE']) await check('FORM-' + company.key + '-' + kind, '/vouchers/new/' + kind.toLowerCase(), async () => {
          await prepare(kind, company);
          if (kind !== 'PURCHASE') { await click('Add account entry'); await click('Add account entry'); }
          await snapshot('form-' + company.key + '-' + kind.toLowerCase(), new URL(page.url()).pathname, company.key === 'retail' ? [1440, 768, 390] : [1440, 390]);
          return 'Native active type and date loaded; unsaved form controls inspected; no Save or transition';
        });
        if (company.key !== 'retail') await check('OVERVIEW-' + company.key, '/', async () => { await h.ready('/'); await snapshot('overview-' + company.key, '/', [1440, 390]); return 'Scoped live overview and configured money display inspected'; });
      }
      const services = companies.find(c => c.designerTemplate);
      if (services) {
        await h.switchCompany(services);
        await check('DESIGNER', '/invoice-designer/' + services.designerTemplate, async () => { await h.ready('/invoice-designer/' + services.designerTemplate); await snapshot('designer', new URL(page.url()).pathname); return 'Retained published template opened; no restore, save or publish'; });
      }
    } else if (part === 'workflows' || part === 'remaining') {
      const company = companies[0];
      await check('VOUCHER-REVIEW', '/vouchers/' + company.purchaseVoucher, async () => {
        await h.ready('/vouchers/' + company.purchaseVoucher);
        const initial = await page.locator('main').innerText();
        await snapshot('voucher-review-initial', new URL(page.url()).pathname, [1440, 390]);
        await click('Refresh voucher'); await page.getByText(/^Status: /).waitFor({ timeout: 90000 });
        await click('Load voucher history'); await page.locator('main ol li').first().waitFor();
        const links = await page.locator('main a').evaluateAll(elements => elements.map(el => ({ label: el.textContent, href: el.getAttribute('href') })));
        await snapshot('voucher-review-loaded', new URL(page.url()).pathname);
        return { initial, loaded: await page.locator('main').innerText(), links };
      });
      await check('PURCHASE-VALIDATION', '/vouchers/new/purchase', async () => {
        await prepare('PURCHASE', company);
        await page.getByLabel('Supplier invoice reference', { exact: true }).fill('UI-REVIEW-UNSAVED');
        await page.getByLabel('Purchase description 1', { exact: true }).fill('UI review only');
        await page.getByLabel('Purchase amount 1 (INR)', { exact: true }).fill('0');
        const saveButton = page.getByRole('button', { name: 'Save draft', exact: true });
        await page.waitForFunction(el => Object.keys(el).some(k => k.startsWith('__reactProps$') && typeof el[k]?.onSubmit === 'function'), await saveButton.locator('xpath=ancestor::form').elementHandle(), { timeout: 90000 });
        await saveButton.click();
        await page.getByRole('status').filter({ hasText: /supplier|reference|positive|account/i }).last().waitFor();
        const state = await page.evaluate(() => ({ focus: document.activeElement?.textContent, invalid: [...document.querySelectorAll('main [aria-invalid=true]')].length, message: [...document.querySelectorAll('main [role=status],[role=alert]')].map(el => ({ role: el.getAttribute('role'), text: el.textContent })) }));
        await snapshot('purchase-validation', new URL(page.url()).pathname, [1440, 390]); return state;
      });
      await check('REPORT-WORKSPACE', '/reports/workspace?report=STOCK_SUMMARY', async () => {
        await h.ready('/reports/workspace?report=STOCK_SUMMARY'); await click('Load report workspace');
        await page.getByRole('heading', { name: 'Report settings', exact: true }).waitFor();
        await snapshot('report-loaded-stock', new URL(page.url()).pathname);
        return await page.locator('main').innerText();
      });
      await check('CUSTOMER-LINK', '/', async () => {
        await h.ready('/');
        const lookup = page.getByRole('combobox', { name: 'Find customer ledger', exact: true }); await lookup.click();
        await page.getByRole('option').first().click();
        const link = page.getByRole('link', { name: 'Open customer ledger', exact: true }); const href = await link.getAttribute('href'); await link.click();
        await page.getByRole('heading', { level: 1 }).first().waitFor(); await page.waitForLoadState('networkidle').catch(() => {});
        await snapshot('customer-ledger-destination', href, [1440, 390]); return { href, text: await page.locator('main').innerText() };
      });
      await check('OVERVIEW-FAILURE', '/', async () => {
        const fail = async route => { const d = route.request().postDataJSON(); if (d.service === 'reports' && /\/overview/.test(d.path)) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'UNAVAILABLE', message: 'Simulated review source unavailable' } }) }); return route.fallback(); };
        await page.route('**/api/product-fields', fail); await h.ready('/');
        await page.getByText('Simulated review source unavailable', { exact: true }).waitFor();
        await snapshot('overview-failure', '/', [1440, 390]); await page.unroute('**/api/product-fields', fail);
        await click('Retry overview'); await page.getByText('Cash and bank', { exact: true }).waitFor(); return 'Source failure and Retry recover to real native overview';
      }, 'SIMULATED_UI_FAILURE_THEN_LIVE_RECOVERY');
    }
    if (part === 'details' || part === 'remaining') {
      async function scrollCapture(id, width) {
        await page.setViewportSize({ width, height: 1000 });
        const measurements = await page.evaluate(() => {
          const main = document.querySelector('.janso-main');
          return main ? { clientHeight: main.clientHeight, scrollHeight: main.scrollHeight, width: main.clientWidth, scrollWidth: main.scrollWidth } : null;
        });
        const evidence = [];
        for (const fraction of [0, 0.5, 1]) {
          await page.evaluate(f => { const main = document.querySelector('.janso-main'); if (main) main.scrollTop = (main.scrollHeight - main.clientHeight) * f; }, fraction);
          await page.waitForTimeout(150);
          const name = 'UIR-' + id + '-' + width + '-scroll-' + fraction;
          const target = path.join(h.output, name + '.png');
          await page.screenshot({ path: target, fullPage: false });
          evidence.push(path.relative(h.root, target).replaceAll('\\', '/'));
        }
        observations.push({ id, company: h.resources.currentCompany, width, measurements, evidence }); save();
        await page.setViewportSize({ width: 1440, height: 1000 });
      }
      const retail = companies[0];
      await check('SALES-RESPONSIVE-CLIPPING', '/vouchers/new/sales', async () => {
        await h.ready('/vouchers/new/sales'); await page.keyboard.press('Escape');
        const measurements = [];
        for (const width of [1440, 768, 390]) {
          await page.setViewportSize({ width, height: 1000 });
          measurements.push(await page.evaluate(() => {
            const selectors = ['.janso-shell', '.janso-main', '.janso-entry-frame', '.janso-entry', '.janso-entry-grid__scroll', '.janso-entry-grid', '.janso-entry__rail'];
            return { width: innerWidth, documentScroll: document.documentElement.scrollWidth, elements: selectors.map(selector => {
              const el = document.querySelector(selector); if (!el) return { selector, missing: true };
              const box = el.getBoundingClientRect(); return { selector, x: box.x, width: box.width, clientWidth: el.clientWidth, scrollWidth: el.scrollWidth, overflowX: getComputedStyle(el).overflowX };
            }) };
          }));
          await scrollCapture('sales-scroll', width);
        }
        return measurements;
      });
      for (const kind of ['RECEIPT', 'PAYMENT', 'PURCHASE']) await check('SCROLLED-FORM-' + kind, '/vouchers/new/' + kind.toLowerCase(), async () => {
        await prepare(kind, retail);
        if (kind !== 'PURCHASE') { await click('Add account entry'); await click('Add account entry'); }
        await scrollCapture('scrolled-' + kind.toLowerCase(), 1440); await scrollCapture('scrolled-' + kind.toLowerCase(), 390);
        return 'Top, middle and bottom of the native form captured in the actual main scroll container';
      });
      await check('MONEY-ACCOUNT-MODE-ITEMS', '/vouchers/new/receipt', async () => {
        await prepare('RECEIPT', retail);
        const mode = await page.getByRole('combobox', { name: 'Entry mode', exact: true }).inputValue();
        await click('Add item'); await page.getByRole('combobox', { name: 'Product 1', exact: true }).waitFor();
        const metadata = await h.call('product-fields', 'vouchers', '/v1/companies/' + retail.id + '/voucher-types/' + retail.moneyTypes.RECEIPT + '/field-set?date=' + reviewDate);
        assert.equal(metadata.status, 200);
        await scrollCapture('money-account-mode-item', 1440);
        return { mode, allowedModes: metadata.body.configuration.policy.allowed_modes, itemControlVisible: true, note: 'Local item line only; no Save. Native documents.py rejects item lines in ACCOUNTS mode.' };
      }, 'LIVE_UI_WITH_NATIVE_METADATA_AND_SOURCE_REVIEW');
      await check('OPENING-EDIT-CONTROLS', '/accounting/opening', async () => {
        await h.ready('/accounting/opening');
        const next = page.getByRole('button', { name: 'Next step', exact: true }); await next.waitFor(); await next.click();
        const add = page.getByRole('button', { name: 'Add account balance', exact: true }); assert(await add.isEnabled(), 'Tenant Admin opening entry remains read only'); await add.click();
        await scrollCapture('opening-entry', 1440); await scrollCapture('opening-entry', 390);
        return 'Permanent opening authority exposes enabled account-entry controls; no preview, save, finalization or posting';
      });
      for (const company of companies) {
        await h.switchCompany(company);
        await check('INVOICE-PREVIEW-DISPLAY-' + company.key, '/vouchers/' + company.purchaseVoucher, async () => {
          await h.ready('/vouchers/' + company.purchaseVoucher);
          const base = '/v1/companies/' + company.id;
          const native = await h.call('product-fields', 'vouchers', base + '/vouchers/' + company.purchaseVoucher); assert.equal(native.status, 200);
          const simulated = async route => {
            const d = route.request().postDataJSON();
            if (d.service === 'vouchers' && d.path === base + '/vouchers/' + company.purchaseVoucher && d.method === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...native.body, status: 'DRAFT' }) });
            if (d.service === 'vouchers' && d.path === base + '/vouchers/' + company.purchaseVoucher + '/invoice-preview') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ calculation_hash: 'a'.repeat(64), payable: '42.1234', commercial_total: '42.1234', tax_total: '0.0000' }) });
            return route.fallback();
          };
          await page.route('**/api/product-fields', simulated);
          await click('Refresh voucher'); await page.getByText('Status: DRAFT', { exact: true }).waitFor(); await click('Preview invoice');
          const total = await page.getByText(/^Invoice total:/).innerText();
          await snapshot('preview-display-' + company.key, new URL(page.url()).pathname, [1440, 390]);
          await page.unroute('**/api/product-fields', simulated);
          return { total, exactInput: '42.1234', note: 'Browser-only DRAFT and preview response; native saved voucher remained SUBMITTED' };
        }, 'SIMULATED_NATIVE_RESPONSE_UI_WITH_LIVE_DETAIL');
      }
      const services = companies.find(c => c.designerTemplate);
      if (services) {
        await h.switchCompany(services);
        await check('DESIGNER-RESTORE-UNDO', '/invoice-designer/' + services.designerTemplate, async () => {
          await h.ready('/invoice-designer/' + services.designerTemplate);
          await click('Restore version 1 into the editor');
          const undo = page.getByRole('button', { name: 'Undo', exact: true }); await undo.waitFor();
          await page.waitForFunction(el => !el.disabled, await undo.elementHandle());
          await page.waitForTimeout(1000); await page.screenshot({ path: path.join(h.output, 'UIR-designer-restored.png'), fullPage: false });
          await undo.click(); await page.screenshot({ path: path.join(h.output, 'UIR-designer-undo.png'), fullPage: false });
          return 'Native historical version loaded into unsaved editor; Undo restored local edit state; no Save or Publish';
        });
      }
      await h.context.clearCookies(); h.resources.currentCompany = ''; const operator = h.privateLoad(path.join(h.output, 'platform-credentials.dpapi')); await h.login(page, operator.username, operator.password);
      await page.route('**/api/platform', guard);
      await check('PLATFORM-ROLE-PREVIEW', '/platform/system-roles', async () => {
        await h.ready('/platform/system-roles'); await page.getByRole('heading', { name: 'Review role changes', exact: true }).waitFor();
        await snapshot('platform-role-preview', '/platform/system-roles');
        return 'Operator preview loaded with pending/unchanged catalogue; no role reconciliation applied';
      });
    }
    if (part === 'payment-recheck' || part === 'final-checks') {
      if (part === 'final-checks') {
        await check('PURCHASE-VALIDATION-RECHECK', '/vouchers/new/purchase', async () => {
          await prepare('PURCHASE', companies[0]);
          await page.getByLabel('Supplier invoice reference', { exact: true }).fill('UI-REVIEW-UNSAVED');
          await page.getByLabel('Purchase description 1', { exact: true }).fill('UI review only');
          await page.getByLabel('Purchase amount 1 (INR)', { exact: true }).fill('0');
          const button = page.getByRole('button', { name: 'Save draft', exact: true });
          await page.waitForFunction(el => Object.keys(el).some(k => k.startsWith('__reactProps$') && typeof el[k]?.onSubmit === 'function'), await button.locator('xpath=ancestor::form').elementHandle(), { timeout: 90000 });
          await button.click(); await page.getByRole('status').filter({ hasText: /supplier|reference|positive|account/i }).last().waitFor();
          const state = await page.evaluate(() => ({ focused: document.activeElement?.textContent, invalid: [...document.querySelectorAll('main [aria-invalid=true]')].length, messages: [...document.querySelectorAll('main [role=status],[role=alert]')].map(el => ({ role: el.getAttribute('role'), text: el.textContent })) }));
          await snapshot('purchase-validation-recheck', new URL(page.url()).pathname, [1440, 390]); return state;
        });
        await check('PURCHASE-CONTROL-HEIGHTS', '/vouchers/new/purchase', async () => {
          await page.setViewportSize({ width: 1440, height: 1000 });
          const measured = await page.evaluate(() => {
            const box = el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
            return [...document.querySelectorAll('main input')].filter(el => /^(Supplier|Supplier payable account|Supplier invoice reference|Payment due date)$/.test(el.labels?.[0]?.textContent?.replace('*', '').trim())).map(el => ({ label: el.labels[0].textContent, input: box(el), visibleControl: box(el.closest('.janso-search-select__control') || el) }));
          });
          return measured;
        });
        await check('SALES-LINE-SCROLLER', '/vouchers/new/sales', async () => {
          await h.ready('/vouchers/new/sales'); await page.keyboard.press('Escape');
          const output = [];
          for (const width of [768, 390]) {
            await page.setViewportSize({ width, height: 1000 });
            output.push(await page.evaluate(() => {
              const scroller = document.querySelector('.janso-entry-grid__scroll'); scroller.scrollIntoView({ block: 'center' }); scroller.scrollLeft = scroller.scrollWidth;
              const main = document.querySelector('.janso-main');
              return { width: innerWidth, mainWidth: main.clientWidth, mainScroll: main.scrollWidth, lineScroll: scroller.scrollLeft, lineOverflow: scroller.scrollWidth - scroller.clientWidth,
                externalOverflow: [...document.body.querySelectorAll('*')].filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.right > innerWidth + 1 && !el.closest('.janso-entry-grid__scroll,.janso-shell__rail'); }).slice(0, 12).map(el => ({ tag: el.tagName, class: el.className, position: getComputedStyle(el).position, visibility: getComputedStyle(el).visibility, x: el.getBoundingClientRect().x, width: el.getBoundingClientRect().width })) };
            }));
            await page.screenshot({ path: path.join(h.output, 'UIR-sales-line-scrolled-' + width + '.png'), fullPage: false });
          }
          return output;
        });
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
      for (const company of companies.slice(1)) {
        await h.switchCompany(company);
        await check('PAYMENT-TYPE-RECHECK-' + company.key, '/vouchers/new/payment', async () => {
          const actual = await h.call('product-fields', 'vouchers', '/v1/companies/' + company.id + '/voucher-types?status=ACTIVE&kind=PAYMENT&limit=200');
          assert.equal(actual.status, 200);
          if (!actual.body.items.length) {
            await h.ready('/vouchers/new/payment'); await click('Load voucher types');
            await page.getByText(/No active payment voucher types/).waitFor(); await snapshot('payment-unconfigured-' + company.key, '/vouchers/new/payment', [1440, 390]);
            const error = new Error('Native active PAYMENT type prerequisite is missing for this company'); error.blocked = true; throw error;
          }
          await prepare('PAYMENT', company); await click('Add account entry'); await click('Add account entry');
          await snapshot('payment-recheck-' + company.key, '/vouchers/new/payment', [1440, 390]);
          return { activeTypes: actual.body.items.length, note: 'Waited for the load action to finish before reading options; no business write' };
        }, 'LIVE_UI_WITH_NATIVE_TYPE_READBACK');
      }
    }
  } finally { save(); await h.browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
