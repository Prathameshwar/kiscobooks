// Fixed-behavior regressions using actual React components and shared UI controls.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const app = path.join(root, 'mfes/apps/console');
const dep = name => require(path.join(app, 'node_modules', name));
const ts = dep('typescript');
for (const extension of ['.ts', '.tsx']) require.extensions[extension] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename, compilerOptions: { module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, filename);
};
const { JSDOM } = dep('jsdom');
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://console.invalid' });
for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'Element', 'Node', 'MutationObserver', 'localStorage', 'sessionStorage']) global[key] = dom.window[key];
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true });
global.IS_REACT_ACT_ENVIRONMENT = true;
global.requestAnimationFrame = callback => setTimeout(callback, 0);
global.cancelAnimationFrame = clearTimeout;
Element.prototype.scrollIntoView = function () {};
window.matchMedia = query => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} });
const React = dep('react');
const original = Module._load;
let service;
Module._load = function(request, parent, isMain) {
  if (request === 'react') return React;
  if (request === 'react/jsx-runtime') return dep('react/jsx-runtime');
  if (request === '@janso/ui') return original.call(this, path.join(root, 'mfes/packages/ui/src/index.ts'), parent, isMain);
  if (request === 'next/link') return { __esModule: true, default: ({ children, href, ...props }) => React.createElement('a', { ...props, href }, children) };
  if (request.endsWith('/ProductModeProvider')) return { useProductMode: () => ({ data: { product_family_sku_enabled: true } }) };
  if (request.endsWith('/service-call')) return { ...original.call(this, request, parent, isMain), serviceCall: (...args) => service(...args) };
  if (request.endsWith('/product-fields')) return { ...original.call(this, request, parent, isMain), productFieldRequest: (name, method, url, body, key) => service('/api/product-fields', { service: name, method: method === 'GET' ? undefined : method, path: url, body, key }) };
  return original.call(this, request, parent, isMain);
};
const { render, screen, cleanup, fireEvent, act } = dep('@testing-library/react');
const lib = file => require(path.join(app, 'app/lib', file));
const component = file => require(path.join(app, 'app/components', file));
// Fixed-behavior regressions; the loader is copied from the read-only review harness.
const { newWork } = lib('advanced-product-draft.ts');
const { emptyOpening, putOpening, openingErrors } = lib('advanced-product-opening.ts');
const { serialInputs } = component('SimpleProductSerials.tsx');
const { trackingBody } = lib('stock-tracking-command.ts');
const { normalizedSerialIdentifier } = lib('serial-identity.ts');
const { COMPANY, ITEM, RECORD, trackingFixture, sourceFixture } = require(path.join(app, 'tests/stock-tracking-fixtures.ts'));
const rule = (type = 'SERIAL', min = 1, max = 1, namespace = 'COMPANY') => ({ identifier_type: type, namespace_rule: namespace, min_count: min, max_count: max, requires_slot: max > 1 });
const options = {
  today: '2026-11-07', books_begin_date: '2026-11-07', inventory_enabled: true,
  currency: 'INR', price_levels_accessible: true, batch: { available: false },
  serial: { enabled: true, requirements: [rule()] }, selected_type: { inventory_modes: ['STOCK'] },
  defaults: { configuration: { profiles: {}, pricing: { sale_price_mode: 'DISABLED', purchase_reference_mode: 'DISABLED', mrp_mode: 'DISABLED' } } }, sale_price_levels: [],
};
const unit = value => ({ key: crypto.randomUUID(), identifiers: [{ identifier_type: 'SERIAL', slot: 1, value }] });
function openingWork(serials, extraSku = false) {
  let work = newWork();
  if (extraSku) work.skus.push({ ...work.skus[0], key: 'second-sku', sku: 'SECOND' });
  for (const sku of work.skus) work = putOpening(work, sku, {
    ...emptyOpening(), decision: 'OPEN', opening_date: options.books_begin_date,
    opening_quantity: String(serials.length), purchase_price: '10', serials,
  });
  return work;
}
let failures = 0;
function check(name, fn) { try { fn(); console.log('PASS ' + name); } catch (error) { failures++; console.error('FAIL ' + name + ': ' + error.message); } }
check('S03 browser Unicode upgrades do not accept native-unassigned identifiers', () => assert.throws(() => normalizedSerialIdentifier('\u{1CCD6}')));
check('Purchase serial eligibility query passes the browser boundary', () => assert.equal(lib('stock-tracking-policy.ts').allowedStockTrackingRequest('GET', `/v1/companies/${COMPANY}/stock-tracking/serials?id=${RECORD}&item_id=${ITEM}&receipt_eligible=true&limit=1`), true));
check('S02 invalid IMEI rejected', () => {
  const rows = [{ key: 'imei', identifiers: [{ identifier_type: 'IMEI', slot: 1, value: '123456789012345' }] }];
  assert(Object.keys(openingErrors(openingWork(rows), { ...options, serial: { enabled: true, requirements: [rule('IMEI')] } })).length);
});
check('S02 duplicate slots rejected', () => {
  const rows = [{ key: 'slots', identifiers: [{ identifier_type: 'SERIAL', slot: 1, value: 'A' }, { identifier_type: 'SERIAL', slot: 1, value: 'B' }] }];
  assert(Object.keys(openingErrors(openingWork(rows), { ...options, serial: { enabled: true, requirements: [rule('SERIAL', 2, 2)] } })).length);
});
check('S03 canonical casefold duplicate rejected in Simple', () => {
  const rows = ['SS', 'ß'].map((value, at) => ({ key: String(at), values: { 'SERIAL.1': value } }));
  assert(Object.keys(serialInputs(rows, options).errors).length);
});
check('S03 normalized expansion rejected', () => {
  assert(Object.keys(serialInputs([{ key: 'expanded', values: { 'SERIAL.1': 'ﬃ'.repeat(41) } }], options).errors).length);
});
check('S04 trimmed Advanced duplicates rejected', () => assert(Object.keys(openingErrors(openingWork([unit(' ABC '), unit('abc')]), options)).length));
check('S05 company namespace spans SKUs', () => assert(Object.keys(openingErrors(openingWork([unit('SAME')], true), options)).length));
check('S05 SKU namespace remains separate', () => assert.deepEqual(openingErrors(openingWork([unit('SAME')], true), { ...options, serial: { enabled: true, requirements: [rule('SERIAL', 1, 1, 'MANUFACTURER_SKU')] } }), {}));
check('S09 physical units need an identifier across optional types', () => assert(Object.keys(openingErrors(openingWork([{ key: 'empty', identifiers: [] }]), { ...options, serial: { enabled: true, requirements: [rule('SERIAL', 0, 1)] } })).length));
check('valid IMEI and allowed second slot pass', () => {
  const value = { key: 'imei', identifiers: [{ identifier_type: 'IMEI', slot: 2, value: '490154203237518' }] };
  assert.deepEqual(openingErrors(openingWork([value]), { ...options, serial: { enabled: true, requirements: [rule('IMEI', 1, 2)] } }), {});
});
check('standalone casefold duplicates rejected', () => {
  const fields = ['item_id', 'identifiers', 'reason'].map(key => ({ key, required: false, visible: true, writable: true }));
  const values = { item_id: ITEM, reason: 'Supplier registration', identifiers: [{ identifier_type: 'SERIAL', slot: 1, value: 'SS' }, { identifier_type: 'SERIAL', slot: 2, value: 'ß' }] };
  assert(Object.keys(trackingBody('serials', 'prepare', fields, values, undefined, { ...sourceFixture, lot_tracking: false, requirements: [rule('SERIAL', 2, 2)] }).errors).length);
});
check('S08 optional slots are optional and removable', () => {
  const { AdvancedOpeningSerials } = component('AdvancedOpeningSerials.tsx');
  render(React.createElement(AdvancedOpeningSerials, { title: 'Optional slots', requirements: [rule('SERIAL', 1, 2)], rows: [{ key: 'optional', identifiers: [{ identifier_type: 'SERIAL', slot: 1, value: 'A' }, { identifier_type: 'SERIAL', slot: 2, value: 'B' }] }], disabled: false, onChange() {} }));
  try { assert.equal(screen.getByLabelText('Serial number 2').required, false); assert(screen.getByRole('button', { name: /Remove SERIAL slot 2/ })); } finally { cleanup(); }
});
check('S07 review contains entered serial identity', () => {
  const { AdvancedOpeningReviewStep } = component('AdvancedOpeningReviewStep.tsx');
  render(React.createElement(AdvancedOpeningReviewStep, { company: COMPANY, work: openingWork([unit('REVIEW-UNIT')]), options, errors: {}, onChange() {}, onEdit() {}, disabled: false }));
  try { assert(screen.getByRole('heading', { name: 'Review before creating' }).closest('section').textContent.includes('REVIEW-UNIT')); } finally { cleanup(); }
});
check('S06 native batch-serial errors remain visible', () => {
  const { AdvancedOpeningReviewStep } = component('AdvancedOpeningReviewStep.tsx');
  let work = newWork();
  work = putOpening(work, work.skus[0], { ...emptyOpening(), decision: 'OPEN', opening_date: options.books_begin_date, batches: [{ key: 'batch', code: 'LOT', opening_quantity: '1', purchase_price: '10', sale_prices: {}, manufactured_on: '', expires_on: '', mrp: '', serials: [unit('A')] }] });
  render(React.createElement(AdvancedOpeningReviewStep, { company: COMPANY, work, options: { ...options, batch: { available: true, required: true } }, errors: { 'opening.skus.0.batches.0.serials.0.identifiers': 'NATIVE SERIAL ERROR' }, onChange() {}, onEdit() {}, disabled: false }));
  try { assert(screen.getByText('NATIVE SERIAL ERROR')); } finally { cleanup(); }
});
async function recoveryFieldCheck() {
  const { AdvancedCreationProgress } = component('AdvancedCreationProgress.tsx');
  const work = openingWork([unit('IMEI-ENTRY')]);
  const creation = '22222222-2222-4222-8222-222222222222';
  const state = { id: creation, company_id: COMPANY, family_id: '33333333-3333-4333-8333-333333333333', sku_ids: [ITEM], row_version: 1, status: 'OPENING', sku_progress: [{ item_id: ITEM, setup_done: true, activated: true, opening_state: 'NOT_REQUESTED', price_draft_ids: [], published_price_ids: [] }] };
  service = async (_, request) => {
    if (request.path.endsWith('/opening-preflight')) throw { status: 422, message: 'Review serial identifiers', fields: { 'serials.0.identifiers': 'Invalid IMEI' } };
    return state;
  };
  let edited;
  render(React.createElement(AdvancedCreationProgress, { initial: { company: COMPANY, key: crypto.randomUUID(), creation_id: creation, definition: { profile: { kind: 'GOODS' }, skus: [{}] }, work, commands: {} }, onEdit: (...args) => { edited = args; } }));
  try {
    const review = await screen.findByRole('button', { name: 'Review remaining setup' });
    fireEvent.click(review);
    assert.deepEqual(edited[3], { 'opening.skus.0.serials.0.identifiers': 'Invalid IMEI' });
    assert.equal(edited[2], 4);
    console.log('PASS S06 progress passes exact physical errors back to review');
  } catch (error) { failures++; console.error('FAIL S06 progress error recovery: ' + error.message.split('\n')[0]); } finally { cleanup(); }
  const fixture = require(path.join(app, 'tests/units-identifiers-fixtures.ts'));
  service = async (_, request) => fixture.response(request);
  const { UnitsIdentifiersEditor } = component('UnitsIdentifiersEditor.tsx');
  const { masterConfig } = lib('catalog-masters.ts');
  const { PermissionProvider } = require(path.join(root, 'mfes/packages/ui/src/index.ts'));
  render(React.createElement(PermissionProvider, { permissions: [] }, React.createElement(UnitsIdentifiersEditor, { company: fixture.COMPANY, config: masterConfig('identifier-profiles'), id: fixture.RECORD, access: fixture.access })));
  try { assert((await screen.findByRole('textbox', { name: 'Code' })).disabled); console.log('PASS S12 profile code is readonly in edit'); } catch (error) { failures++; console.error('FAIL S12 readonly profile code: ' + error.message.split('\n')[0]); } finally { cleanup(); }
  await uncertainReloadCheck();
  await recoveryGuards();
  process.exitCode = failures ? 1 : 0;
}
async function recoveryGuards() {
  const { renderHook } = dep('@testing-library/react');
  const { useServiceCommand } = lib('service-resource.ts');
  const request = { path: `/v1/companies/${COMPANY}/stock-tracking/serials`, method: 'POST', body: { item_id: ITEM, identifiers: [{ identifier_type: 'SERIAL', slot: 1, value: 'S1' }], reason: 'Supplier registration' } };
  const recovery = { storageKey: 'tracking-command:guard-actor', targetPath: request.path };
  try {
    const calls = []; let responses = 0;
    const reader = async value => { calls.push(value); if (++responses === 1) throw { status: 503, message: 'Lost response' }; if (responses === 2) throw { status: 403, message: 'Read access revoked' }; return {}; };
    const view = renderHook(() => useServiceCommand(reader, 'serial', recovery));
    await act(async () => { await view.result.current.execute(request, () => {}); });
    assert(view.result.current.uncertain);
    await act(async () => { view.result.current.clear(); await view.result.current.execute({ ...request, body: { reason: 'Changed body' } }, () => {}); });
    assert.equal(calls.length, 1);
    await act(async () => { await view.result.current.retry(() => {}); });
    assert(view.result.current.uncertain);
    await act(async () => { await view.result.current.retry(() => {}); });
    assert.equal(calls.length, 3); assert.deepEqual(calls[2], calls[0]);
    assert.equal(sessionStorage.getItem(recovery.storageKey), null);
    cleanup();
    console.log('PASS S11 changed-body/clear protection and permission-loss retry preserve identity');
    sessionStorage.setItem(recovery.storageKey, '{broken');
    let sent = 0;
    const blocked = renderHook(() => useServiceCommand(async () => { sent++; return {}; }, 'serial', recovery));
    assert(blocked.result.current.blocked);
    await act(async () => { blocked.result.current.clear(); await blocked.result.current.execute(request, () => {}); });
    assert.equal(sent, 0); assert.equal(sessionStorage.getItem(recovery.storageKey), '{broken');
    cleanup();
    const anotherActor = renderHook(() => useServiceCommand(async () => ({}), 'serial', { ...recovery, storageKey: 'another-actor' }));
    assert.equal(anotherActor.result.current.restoredRequest, undefined);
    assert.equal(anotherActor.result.current.uncertain, false);
    cleanup(); sessionStorage.clear();
    console.log('PASS S11 corrupted receipt fails closed and another actor does not restore it');
    const nativeSet = dom.window.Storage.prototype.setItem;
    dom.window.Storage.prototype.setItem = function(key, value) { if (key === recovery.storageKey) throw new Error('Quota exceeded'); return nativeSet.call(this, key, value); };
    try {
      const quota = renderHook(() => useServiceCommand(async () => { sent++; return {}; }, 'serial', recovery));
      await act(async () => { await quota.result.current.execute(request, () => {}); });
      assert.equal(sent, 0); assert(quota.result.current.uncertain);
      cleanup();
    } finally { dom.window.Storage.prototype.setItem = nativeSet; }
    console.log('PASS S11 storage failure blocks transmission before any native write');
  } catch (error) { failures++; console.error('FAIL S11 recovery guards: ' + error.message.split('\n')[0]); } finally { cleanup(); sessionStorage.clear(); }
}
async function uncertainReloadCheck() {
  const { StockTrackingPage } = component('StockTrackingPage.tsx');
  const recoveryScope = '11111111-1111-4111-8111-111111111111:22222222-2222-4222-8222-222222222222';
  const writes = [];
  sessionStorage.clear();
  service = async (_, request) => {
    if (request.method) { writes.push(request); if (writes.length === 1) throw { status: 503, message: 'Response lost' }; }
    return request.path.includes('/context/') ? { ...sourceFixture, lot_tracking: false } : trackingFixture(request);
  };
  const show = () => render(React.createElement(StockTrackingPage, { company: COMPANY, kind: 'serials', page: 'new', itemId: ITEM, recoveryScope, access: { manage: true, hold: true } }));
  try {
    show();
    fireEvent.change(await screen.findByLabelText('SERIAL 1'), { target: { value: 'LOST-RESPONSE-UNIT' } });
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Supplier registration' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Register serial' })); await new Promise(resolve => setTimeout(resolve, 5)); });
    await screen.findByRole('button', { name: 'Retry same save' });
    cleanup(); show();
    const retry = await screen.findByRole('button', { name: 'Retry same save' }, { timeout: 500 });
    assert.equal(screen.getByLabelText('SERIAL 1').value, 'LOST-RESPONSE-UNIT');
    assert(screen.getByLabelText('SERIAL 1').disabled);
    await act(async () => { fireEvent.click(retry); await new Promise(resolve => setTimeout(resolve, 5)); });
    await screen.findByText('Tracking record registered.');
    assert.equal(writes.length, 2); assert.equal(writes[0].key, writes[1].key); assert.deepEqual(writes[0].body, writes[1].body);
    console.log('PASS S11 reload restores the exact serial registration body and key');
  } catch (error) { failures++; console.error('FAIL S11 uncertain reload recovery: ' + error.message.split('\n')[0]); } finally { cleanup(); sessionStorage.clear(); }
}
recoveryFieldCheck().catch(error => { console.error(error); process.exitCode = 1; });
