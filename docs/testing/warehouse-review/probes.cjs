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
global.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
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
const { waitFor } = dep('@testing-library/react');
// Fixed-behavior regression using the actual editor and shared UI controls.
const { CatalogMasterEditor } = component('CatalogMasterEditor.tsx');
const { masterConfig } = lib('catalog-masters.ts');
const { DisplayConfigProvider } = require(path.join(root, 'mfes/packages/ui/src/index.ts'));
const company = '01990000-0000-7000-8000-000000000001';
const config = masterConfig('warehouses');
async function main() {
  const writes = [];
  service = async (_endpoint, request) => {
    if (request.path.includes('/entities/')) return {
      company_id: company, entity_type: config.entity,
      fields: ['code', 'name', 'kind'].map((key, order) => ({
        key, label:key, order, source:'native', visible:true, writable:true,
        required:true, conditional_access:false,
      })),
    };
    if (request.method === 'POST') {
      writes.push(request);
      if (writes.length === 1) throw {status:503, message:'Save response unavailable'};
      return {...request.body, id:'01990000-0000-7000-8000-000000000002', company_id:company, row_version:1};
    }
    throw {status:404, message:'Unexpected '+request.path};
  };
  render(React.createElement(DisplayConfigProvider, {config:{timezone:'Asia/Kolkata'}},
    React.createElement(CatalogMasterEditor, {company, config})));
  const name = await screen.findByRole('textbox', {name:'Name'});
  const code = screen.getByRole('textbox', {name:'Code'});
  await act(async () => {
    fireEvent.change(code, {target:{value:'STORE_A'}});
    fireEvent.change(name, {target:{value:'Retail store'}});
  });
  assert.equal(screen.getByRole('button', {name:'Create warehouse'}).disabled, false);
  await act(async () => fireEvent.submit(document.querySelector('form')));
  await screen.findByText(/Save response unavailable/);
  assert.equal(code.disabled, true);
  await act(async () => fireEvent.change(code, {target:{value:'STORE_B'}}));
  await act(async () => fireEvent.submit(document.querySelector('form')));
  await waitFor(() => assert.equal(writes.length, 2));
  assert.equal(writes[0].key, writes[1].key);
  assert.equal(writes[0].body.code, 'STORE_A');
  assert.equal(writes[1].body.code, 'STORE_A');
  await screen.findByText('Warehouse created.');
  cleanup();
  console.log('PASS: standalone warehouse create freezes uncertain identity and recovers with the original idempotency key.');
}
main().catch(error => {console.error(error); process.exitCode=1;});

