// Review real React screens and shared controls in JSDOM, without Vite/esbuild.
// Only remote service calls, product-mode context and Next navigation are mocked.
// Assertions confirm current defects; they are not fixed-behavior regressions.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const consoleRoot = path.join(root, 'mfes/apps/console');
const dep = name => require(path.join(consoleRoot, 'node_modules', name));
const ts = dep('typescript');
for (const extension of ['.ts', '.tsx']) require.extensions[extension] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, filename);
};
const { JSDOM } = dep('jsdom');
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://console.invalid', pretendToBeVisual: true });
for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'Element', 'Node', 'MutationObserver', 'localStorage', 'sessionStorage', 'getComputedStyle']) {
  global[key] = key === 'getComputedStyle' ? dom.window.getComputedStyle.bind(dom.window) : dom.window[key];
}
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true });
global.requestAnimationFrame = callback => setTimeout(callback, 0);
global.cancelAnimationFrame = clearTimeout;
global.IS_REACT_ACT_ENVIRONMENT = true;
window.matchMedia = query => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} });
Element.prototype.scrollIntoView = function () {};
const React = dep('react');
const originalLoad = Module._load;
let service;
Module._load = function (request, parent, isMain) {
  if (request === 'react') return React;
  if (request === 'react/jsx-runtime') return dep('react/jsx-runtime');
  if (request === '@janso/ui') return originalLoad(path.join(root, 'mfes/packages/ui/src/index.ts'), parent, isMain);
  if (request === 'next/link') return { __esModule: true, default: ({ children, href, ...props }) => React.createElement('a', { ...props, href }, children) };
  if (request.endsWith('/ProductModeProvider')) return { useProductMode: () => ({ data: { product_family_sku_enabled: true } }) };
  if (request.endsWith('/service-call')) {
    const actual = originalLoad.call(this, request, parent, isMain);
    return { ...actual, serviceCall: (...args) => service(...args) };
  }
  if (request.endsWith('/product-fields')) {
    const actual = originalLoad.call(this, request, parent, isMain);
    return { ...actual, productFieldRequest: (serviceName, method, requestPath, body, key, signal) =>
      service('/api/product-fields', { service: serviceName, method: method === 'GET' ? undefined : method, path: requestPath, body, key, signal }) };
  }
  return originalLoad.call(this, request, parent, isMain);
};
const { render, screen, fireEvent, waitFor, cleanup } = dep('@testing-library/react');
const { StockTrackingPage } = require(path.join(consoleRoot, 'app/components/StockTrackingPage.tsx'));
const { trackingFixture, batchFixture, sourceFixture, COMPANY, ITEM, RECORD } = require(path.join(consoleRoot, 'tests/stock-tracking-fixtures.ts'));
let writes = [];
function reset(handler) {
  cleanup(); writes = [];
  service = async (endpoint, request) => {
    if (request.method) writes.push(request);
    return handler ? handler(request) : trackingFixture(request);
  };
}
function show(page) {
  return render(React.createElement(StockTrackingPage, {
    company: COMPANY, kind: 'batches', page, itemId: ITEM,
    id: ['new', 'list'].includes(page) ? undefined : RECORD,
    access: { manage: true, hold: true },
  }));
}
async function main() {
  reset(request => {
    const result = trackingFixture(request);
    if (request.path.endsWith('/' + RECORD)) {
      const partial = { ...batchFixture }; delete partial.manufactured_on; return partial;
    }
    return result;
  });
  show('edit');
  assert.equal((await screen.findByLabelText('Expiry date')).value, '');
  console.log('PASS U01: readable existing expiry renders blank when manufacture is read-protected.');
  reset(request => {
    const result = trackingFixture(request);
    if (request.path.endsWith('/' + RECORD)) {
      const partial = { ...batchFixture }; delete partial.manufactured_on; return partial;
    }
    return result;
  });
  show('detail');
  await screen.findByText(batchFixture.code);
  assert.equal(screen.queryByText('Expiry'), null);
  console.log('PASS U01 detail: the same permitted expiry is absent from the detail summary.');

  reset(); show('new');
  await screen.findByLabelText('Expiry date');
  await waitFor(() => assert.ok(!screen.getByRole('button', { name: 'Register batch' }).disabled || screen.getByLabelText('MRP amount').disabled === false));
  assert.equal(sourceFixture.expiry_required, true);
  assert.equal(screen.getByLabelText('Expiry date').required, false);
  assert.equal(screen.getByLabelText('Manufacture date').required, false);
  console.log('PASS U02: required profile dates are rendered as optional in batch registration.');

  reset(request => {
    if (request.method) throw { status: 422, message: 'at least one date correction is required' };
    return trackingFixture(request);
  });
  show('edit');
  fireEvent.change(await screen.findByLabelText('Reason'), { target: { value: 'Review unchanged expiry' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save change' }));
  await waitFor(() => assert.equal(writes.length, 1));
  assert.deepEqual(Object.keys(writes[0].body).sort(), ['expected_version', 'reason']);
  console.log('PASS U03: a reason-only date correction is submitted although the owner rejects it.');

  reset(request => {
    if (request.method) throw { status: 409, message: 'batch dates are used by posted stock; a controlled stock correction is required' };
    return trackingFixture(request);
  });
  show('edit');
  fireEvent.change(await screen.findByLabelText('Expiry date'), { target: { value: '2028-01-01' } });
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Review discard behavior' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save change' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Reload and review' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Discard and reload' }));
  await waitFor(() => assert.equal(screen.getByLabelText('Expiry date').disabled, false));
  assert.equal(screen.getByLabelText('Expiry date').value, batchFixture.expires_on);
  assert.equal(screen.getByLabelText('Reason').value, '');
  assert.equal(screen.getByRole('button', { name: 'Save change' }).disabled, true);
  console.log('PASS positive control: discard/reload restores saved dates and clears the reason.');
  cleanup();

  const lib = path.join(consoleRoot, 'app/lib');
  const { newWork } = require(path.join(lib, 'advanced-product-draft.ts'));
  const { emptyBusiness, putBusiness } = require(path.join(lib, 'advanced-product-business.ts'));
  const { emptyOpening, putOpening, openingErrors, openingCommand } = require(path.join(lib, 'advanced-product-opening.ts'));
  const { AdvancedOpeningReviewStep } = require(path.join(consoleRoot, 'app/components/AdvancedOpeningReviewStep.tsx'));
  const options = {
    today: '2026-11-07', books_begin_date: '2026-11-07', inventory_enabled: true,
    currency: 'INR', price_levels_accessible: true,
    batch: { available: true, required: false, expiry_enabled: true, expiry_required: false, manufacture_date_required: true },
    serial: { enabled: false }, selected_type: { inventory_modes: ['STOCK'] },
    defaults: { configuration: { profiles: {}, pricing: {
      sale_price_mode: 'OPTIONAL', purchase_reference_mode: 'OPTIONAL', mrp_mode: 'OPTIONAL',
    }}}, sale_price_levels: [],
  };
  let work = newWork();
  work = putBusiness(work, work.skus[0], { ...emptyBusiness(), batch_enabled: true });
  const opening = { ...emptyOpening(), decision: 'OPEN', opening_date: options.books_begin_date,
    batches: [{ key: 'batch-row', code: 'LOT1', opening_quantity: '1', purchase_price: '10',
      sale_prices: {}, mrp: '19', manufactured_on: '2026-01-01', expires_on: '2028-01-01', serials: [] }],
  };
  work = putOpening(work, work.skus[0], opening);
  const advancedProps = { company: COMPANY, work, options, errors: {}, onChange() {}, onEdit() {}, disabled: false };
  render(React.createElement(AdvancedOpeningReviewStep, advancedProps));
  const review = screen.getByRole('heading', { name: 'Review before creating' }).closest('section').textContent;
  assert.ok(!review.includes('2028-01-01') && !review.includes('2026-01-01') && !review.includes('19'));
  assert.equal(screen.getByLabelText('Expires on').value, '2028-01-01');
  console.log('PASS U04: final Advanced review omits batch expiry, manufacture and physical MRP.');
  cleanup();
  const changedOptions = { ...options, batch: { ...options.batch, expiry_enabled: false, manufacture_date_required: false } };
  assert.deepEqual(openingErrors(work, changedOptions), {});
  render(React.createElement(AdvancedOpeningReviewStep, { ...advancedProps, options: changedOptions }));
  assert.equal(screen.queryByLabelText('Expires on'), null);
  assert.equal(screen.queryByLabelText('Manufactured on'), null);
  assert.equal(openingCommand(opening).batches[0].expires_on, '2028-01-01');
  console.log('PASS U05: disabled hidden expiry passes Advanced validation and remains in the submitted payload.');
  cleanup();

  const { batchInputs } = require(path.join(consoleRoot, 'app/components/SimpleProductBatches.tsx'));
  const simple = { currency: 'INR', opening_date: options.today, batch: { expiry_enabled: true },
    serial: { enabled: false }, sale_price_levels: [],
    configuration: { pricing: { sale_price_mode: 'DISABLED', purchase_reference_mode: 'DISABLED', mrp_mode: 'DISABLED' } },
    fields: ['batch_enabled', 'batch_code', 'batch_expires_on', 'opening_quantity'].map(key => ({ key, visible: true, writable: true })),
  };
  const row = (code, expiry = '') => ({ key: crypto.randomUUID(), values: { code, opening_quantity: '0', expires_on: expiry } });
  assert.deepEqual(batchInputs([row('ss'), row('ß')], simple).errors, {});
  assert.deepEqual(batchInputs([row('\ufb03'.repeat(40))], simple).errors, {});
  assert.deepEqual(batchInputs([row('LOT', '0001-01-01')], simple).errors, {});
  console.log('PASS U06: Simple accepts backend-invalid duplicate codes, normalization overflow and pre-1000 expiry.');

  reset(request => {
    if (request.method) throw { status: 422, message: 'expiry date is required', fields: { expires_on: 'Required by the published inventory profile.' } };
    return trackingFixture(request);
  });
  show('edit');
  fireEvent.change(await screen.findByLabelText('Expiry date'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Review required expiry clearing' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save change' }));
  await waitFor(() => assert.equal(writes.length, 1));
  assert.equal(writes[0].body.expires_on, null);
  console.log('PASS U02 edit: required-expiry clearing is sent without loading profile requirements.');
  cleanup();

  const expired = { ...opening, batches: [{ ...opening.batches[0], manufactured_on: '2026-01-01', expires_on: '2026-02-01' }] };
  const expiredWork = putOpening(work, work.skus[0], expired);
  assert.deepEqual(openingErrors(expiredWork, options), {});
  const future = { ...opening, batches: [{ ...opening.batches[0], manufactured_on: '2027-01-01', expires_on: '2028-01-01' }] };
  assert.deepEqual(openingErrors(putOpening(work, work.skus[0], future), options), {});
  console.log('PASS U07: Advanced validates already-expired opening stock and manufacture after the opening date.');

  const { AdvancedCreationProgress } = require(path.join(consoleRoot, 'app/components/AdvancedCreationProgress.tsx'));
  const progress = { id: RECORD, company_id: COMPANY, family_id: RECORD, sku_ids: [ITEM],
    status: 'OPENING', row_version: 3,
    sku_progress: [{ setup_done: true, activated: true, opening_state: 'NOT_REQUESTED', price_draft_ids: [] }],
  };
  let returnedEdit;
  reset(request => {
    if (request.path.endsWith('/opening-preflight')) throw {
      status: 422, message: 'Check the batch dates', fields: { 'batches.0.expires_on': 'Must cover the opening date: 2026-11-07.' },
    };
    if (request.path.endsWith('/definitions/' + RECORD)) return progress;
    throw new Error('Unexpected request: ' + request.path);
  });
  render(React.createElement(AdvancedCreationProgress, {
    initial: { company: COMPANY, key: ITEM, creation_id: RECORD, work: expiredWork, definition: {}, commands: {} },
    onEdit: (...args) => { returnedEdit = args; },
  }));
  await screen.findByRole('button', { name: 'Review remaining setup' });
  assert.equal(screen.queryByText('Must cover the opening date: 2026-11-07.'), null);
  fireEvent.click(screen.getByRole('button', { name: 'Review remaining setup' }));
  assert.equal(returnedEdit.length, 3);
  assert.equal(returnedEdit[2], 4);
  assert.ok(!returnedEdit.some(value => JSON.stringify(value).includes('Must cover the opening date')));
  console.log('PASS U08: opening field-error details are neither displayed nor transferred back to the edit screen.');
  cleanup();

  const { PurchaseBatchChooser } = require(path.join(consoleRoot, 'app/components/PurchaseBatchChooser.tsx'));
  let purchaseSelected;
  reset(request => {
    if (request.method && writes.length === 1) throw { status: 503, message: 'Registration reply lost after commit' };
    if (request.method) return {
      id: RECORD, company_id: COMPANY, item_id: ITEM, code: request.body.code,
      status: 'ACTIVE', is_held: false, manufactured_on: null, expires_on: null,
    };
    return { items: [], page: { has_more: false, next_cursor: null } };
  });
  render(React.createElement(PurchaseBatchChooser, {
    company: COMPANY, item: ITEM, name: 'Tea', postingDate: '2026-11-07', canCreate: true,
    profile: { companyId: COMPANY, itemId: ITEM, profileRevisionId: RECORD, lotTracking: true, serialTracking: false,
      expiryRequired: false, manufactureDateRequired: false, shelfLifeDays: null, minimumRemainingLifeDays: null },
    onSelect: result => { purchaseSelected = result; }, onClose() {},
  }));
  fireEvent.click(screen.getByRole('tab', { name: 'Create batch' }));
  fireEvent.change(screen.getByLabelText('Batch code'), { target: { value: 'LOT-REPLY-LOST' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create and select batch' }));
  await screen.findByText('The batch could not be created.');
  assert.equal(screen.getByLabelText('Batch code').disabled, false);
  assert.equal(screen.queryByRole('button', { name: 'Retry same save' }), null);
  fireEvent.change(screen.getByLabelText('Batch code'), { target: { value: 'LOT-SECOND-ATTEMPT' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create and select batch' }));
  await waitFor(() => assert.ok(purchaseSelected));
  assert.equal(writes.length, 2);
  assert.notEqual(writes[0].key, writes[1].key);
  assert.equal(writes[0].body.code, 'LOT-REPLY-LOST');
  assert.equal(writes[1].body.code, 'LOT-SECOND-ATTEMPT');
  console.log('PASS U09: Purchase batch creation permits a new body/key after an uncertain registration response.');
  cleanup();

  reset(request => {
    if (request.method && writes.length === 1) throw { status: 503, message: 'Reply lost after commit' };
    return trackingFixture(request);
  });
  show('edit');
  fireEvent.change(await screen.findByLabelText('Expiry date'), { target: { value: '2028-01-01' } });
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Review exact retry behavior' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save change' }));
  const retry = await screen.findByRole('button', { name: 'Retry same save' });
  assert.equal(screen.getByLabelText('Expiry date').disabled, true);
  fireEvent.click(retry);
  await screen.findByText('Change saved.');
  assert.equal(writes.length, 2);
  assert.equal(writes[0].key, writes[1].key);
  assert.deepEqual(writes[0].body, writes[1].body);
  console.log('PASS positive control: batch master edit freezes inputs and replays the same body/key after a lost reply.');
  cleanup();
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => { cleanup(); dom.window.close(); });
