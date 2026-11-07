// Real React controls and native UI policies, without an esbuild child process.
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
const React = dep('react');
const original = Module._load;
let service;
Module._load = function(request, parent, isMain) {
  if (request === 'react') return React;
  if (request === 'react/jsx-runtime') return dep('react/jsx-runtime');
  if (request === '@janso/ui') return original.call(this, path.join(root, 'mfes/packages/ui/src/index.ts'), parent, isMain);
  if (request === 'next/link') return { __esModule: true, default: ({ children, href, ...props }) => React.createElement('a', { ...props, href }, children) };
  if (request.endsWith('/ProductModeProvider')) return { useProductMode: () => ({ data: { product_family_sku_enabled: false } }) };
  if (request.endsWith('/service-call')) return { ...original.call(this, request, parent, isMain), serviceCall: (...args) => service(...args) };
  if (request.endsWith('/product-fields')) return { ...original.call(this, request, parent, isMain), productFieldRequest: (name, method, requestPath, body, key) => service('/api/product-fields', { service: name, method: method === 'GET' ? undefined : method, path: requestPath, body, key }) };
  return original.call(this, request, parent, isMain);
};
const { render, screen, cleanup, fireEvent, waitFor } = dep('@testing-library/react');
const { DisplayConfigProvider } = require(path.join(root, 'mfes/packages/ui/src/index.ts'));
const { batchInputs, batchColumns, SimpleProductBatches } = require(path.join(consoleRoot, 'app/components/SimpleProductBatches.tsx'));
const { openingCommand, emptyOpening } = require(path.join(consoleRoot, 'app/lib/advanced-product-opening.ts'));
const options = {
  currency: 'INR', opening_date: '2026-11-07',
  configuration: { pricing: { purchase_reference_mode: 'DISABLED', sale_price_mode: 'DISABLED', mrp_mode: 'DISABLED' } },
  batch: { available: true, required: false, expiry_enabled: false, expiry_required: false, manufacture_date_required: false },
  serial: { enabled: false }, sale_price_levels: [],
  fields: ['batch_enabled', 'batch_code', 'opening_quantity', 'opening_unit_cost'].map(key => ({ key, visible: true, writable: true, conditional_access: false })),
};
const row = { key: 'row', values: { code: 'LOT-1', opening_quantity: '2', opening_unit_cost: '7.50' } };
const prepared = batchInputs([row], options);
assert.deepEqual(prepared.errors, {});
assert.equal(prepared.batches[0].opening_unit_cost, '7.50');
assert.equal(prepared.batches[0].purchase_price, undefined);
assert(!batchColumns(options).some(column => column.key === 'purchase_price'));
render(React.createElement(DisplayConfigProvider, { config: { currency: 'INR', timezone: 'Asia/Kolkata' } },
  React.createElement(SimpleProductBatches, { options, enabled: true, rows: [row], locked: false, errors: {}, onToggle() {}, onRows() {} })));
assert.equal(screen.getByLabelText('Opening unit cost 1').value, '7.50');
assert.equal(screen.getByLabelText('Opening unit cost 1').required, true);
assert.equal(screen.queryByLabelText('Purchase reference 1'), null);
cleanup();
console.log('PASS B04: Simple batch cost entry remains available with purchase references disabled.');
const advanced = openingCommand({ ...emptyOpening(), decision: 'OPEN', opening_date: '2026-11-07',
  batches: [{ key: 'batch', code: 'LOT-1', opening_quantity: '2', purchase_price: '7.50', purchase_reference: '', sale_prices: {}, manufactured_on: '', expires_on: '', mrp: '', serials: [] }] });
assert.equal(advanced.batches[0].opening_unit_cost, '7.50');
assert.equal(advanced.batches[0].purchase_price, null);
const independent = openingCommand({ ...emptyOpening(), decision: 'OPEN', opening_date: '2026-11-07',
  batches: [{ key: 'batch', code: 'LOT-1', opening_quantity: '2', purchase_price: '7.50', purchase_reference: '9.00', sale_prices: {}, manufactured_on: '', expires_on: '', mrp: '', serials: [] }] });
assert.equal(independent.batches[0].opening_unit_cost, '7.50');
assert.equal(independent.batches[0].purchase_price, '9.00');
console.log('PASS B04: Advanced captures independent opening cost and purchase reference values.');

async function fullSimpleForm() {
  const { SimpleProductCreate } = require(path.join(consoleRoot, 'app/components/SimpleProductCreate.tsx'));
  const { simpleOptions, COMPANY, GROUP } = require(path.join(consoleRoot, 'tests/simple-product-ready-fixtures.ts'));
  const options = simpleOptions();
  options.configuration.pricing.purchase_reference_mode = 'DISABLED';
  options.fields = options.fields.filter(field => field.key !== 'purchase_price');
  options.fields.push({ key: 'opening_unit_cost', label: 'Opening unit cost', visible: true, writable: true, conditional_access: false, required: false });
  const writes = [];
  const rootPath = `/v1/companies/${COMPANY}/simple-product-creations`;
  service = async (_, request) => {
    if (request.method) writes.push(request);
    if (request.path.includes('/options?')) return options;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' };
    if (request.path.includes('/option-sources/')) return { items: [{ id: '33333333-3333-4333-8333-333333333333', label: 'Numbers' }], page: { has_more: false } };
    if (request.path === rootPath) return { id: 'job', company_id: COMPANY, code: 'COST123456', status: 'COMPLETE', step: 'COMPLETE', opening_posted: true };
    throw Error(request.path);
  };
  render(React.createElement(DisplayConfigProvider, { config: { currency: 'INR', timezone: 'Asia/Kolkata' } }, React.createElement(SimpleProductCreate, { company: COMPANY })));
  fireEvent.change(await screen.findByLabelText(/Product name/), { target: { value: 'Tea' } });
  fireEvent.click(screen.getByRole('combobox', { name: /Base unit/ }));
  fireEvent.click(await screen.findByRole('option', { name: 'Numbers' }));
  const next = screen.queryByRole('button', { name: 'Next: Stock and prices' });
  if (next) fireEvent.click(next);
  fireEvent.change(screen.getByLabelText('Opening quantity'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText(/Opening unit cost/), { target: { value: '7.50' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save product' }));
  await waitFor(() => assert(writes.some(request => request.path === rootPath)));
  const body = writes.find(request => request.path === rootPath).body;
  assert.equal(body.opening_unit_cost, '7.50');
  assert.equal(body.purchase_price, undefined);
  assert.equal(body.opening_quantity, '2');
  cleanup();
  console.log('PASS B04: Simple product form submits valued opening stock with purchase references disabled.');
}
fullSimpleForm().catch(error => { console.error(error); process.exitCode = 1; });
