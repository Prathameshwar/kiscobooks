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
const { form, COMPANY } = require(path.join(app, 'tests/accounting-configuration-fixtures.ts'));
const { accountingBody } = lib('accounting-configuration.ts');
const { AccountingFields } = component('AccountingConfigurationCommon.tsx');
const { supplierRequest, expenseAccountRequest } = lib('purchase-quick-create.ts');
const { SupplierQuickCreate, ExpenseAccountQuickCreate } = component('PurchaseQuickCreate.tsx');
let passed = 0;
async function check(name, fn) { await fn(); cleanup(); passed++; console.log('PASS ' + name); }
const page = items => ({items, page:{limit:200, has_more:false, next_cursor:null}});
async function main() {
  for (const resource of ['accounts','parties']) await check(resource + ' native master Code optional and validates manual text', () => {
    const code = form(resource).fields.find(field => field.key === 'code');
    let entered;
    render(React.createElement(AccountingFields, {company:COMPANY, resource, fields:[code], values:{code:''}, onChange(_key,value){entered=value;}}));
    const input = screen.getByRole('textbox', {name:'Code'});
    assert.equal(input.required, false);
    assert.equal(input.maxLength, 80);
    fireEvent.change(input,{target:{value:'😀'.repeat(41)}});
    assert.equal(entered,'😀'.repeat(40));
    fireEvent.change(input,{target:{value:'a'.repeat(41)}});
    assert.equal(entered,'a'.repeat(40));
    assert.match(document.getElementById(input.getAttribute('aria-describedby')).textContent, /Leave blank.*eight-character/);
    assert.deepEqual(accountingBody([code], {code:'   '}), {body:{}, errors:{}});
    assert.deepEqual(accountingBody([code], {code:' 00-Office & rent '}).body, {code:'00-Office & rent'});
    assert.deepEqual(accountingBody([code], {code:'😀'.repeat(40)}).errors, {});
    assert.match(accountingBody([code], {code:'😀'.repeat(41)}).errors.code, /40 characters/);
    assert.match(accountingBody([code], {code:'x'.repeat(41)}).errors.code, /40 characters/);
    assert.match(accountingBody([code], {code:'bad\u0000code'.replace('\\u0000','\u0000')}).errors.code || '', /control characters/);
    cleanup(); code.editable = false;
    render(React.createElement(AccountingFields, {company:COMPANY, resource, fields:[code], values:{code:'OLD001'}, onChange(){}}));
    assert.equal(screen.queryByRole('textbox', {name:'Code'}), null);
    assert.equal(screen.getByText('OLD001').textContent, 'OLD001');
  });
  await check('Purchase request builders omit blank code and retain manual identity', () => {
    const supplier = {name:'Supplier', code:' ', countryCode:'IN', gstStatus:'NONE', stateCode:'', gstin:''};
    const account = {name:'Rent', code:' ', groupId:COMPANY, description:''};
    const groups = [{id:COMPANY, name:'Indirect Expenses', head:'Expenses'}];
    assert.equal('code' in supplierRequest(supplier, {tax:false}).body, false);
    assert.equal('code' in expenseAccountRequest(account, groups).body, false);
    assert.equal(supplierRequest({...supplier, code:' 00-Office & rent '}, {tax:false}).body.code, '00-Office & rent');
    assert.deepEqual(supplierRequest({...supplier, code:'😀'.repeat(40)}, {tax:false}).errors, {});
    assert.deepEqual(expenseAccountRequest({...account, code:'😀'.repeat(40)}, groups).errors, {});
    assert.match(expenseAccountRequest({...account, code:'x'.repeat(41)}, groups).errors.code, /40 characters/);
  });
  for (const kind of ['supplier', 'expense']) await check('Purchase ' + kind + ' actual optional Code control and blank-code submission', async () => {
    const writes = [], headId='01990000-0000-7000-8000-000000000010', groupId='01990000-0000-7000-8000-000000000020';
    service = async (_endpoint, request) => {
      if (request.path.includes('/configuration/options/countries')) return page([{value:'IN',label:'India',code:'IN'}]);
      if (request.path.includes('/account-heads?')) return page([{id:headId,company_id:COMPANY,name:'Expenses'}]);
      if (request.path.endsWith('/account-heads/'+headId)) return {id:headId,company_id:COMPANY,name:'Expenses',nature:'EXPENSE'};
      if (request.path.includes('/account-groups?')) return page([{id:groupId,company_id:COMPANY,name:'Indirect Expenses',head_id:headId}]);
      if (request.method === 'POST') { writes.push(request); return {id:'01990000-0000-7000-8000-000000000050',company_id:COMPANY,row_version:1,status:'ACTIVE',code:'AABBCCDD',name:'Office',kind:'GENERAL',inventory_affected:false,posting_policy:'MANUAL_ALLOWED',group_id:groupId}; }
      throw {status:404,message:'Unexpected '+request.path};
    };
    let created;
    const props={company:COMPANY,companyCountry:'IN',canTax:false,onCreated:value=>{created=value;},onClose(){}};
    render(React.createElement(kind==='supplier'?SupplierQuickCreate:ExpenseAccountQuickCreate, props));
    const code = screen.getByRole('textbox', {name:kind==='supplier'?/Supplier code/:/Account code/});
    assert.equal(code.required, false);
    await act(async () => fireEvent.change(screen.getByRole('textbox', {name:kind==='supplier'?/Supplier name/:/Account name/}), {target:{value:'Office'}}));
    assert.equal(code.value, '');
    assert.equal(code.maxLength,80);
    await act(async()=>fireEvent.change(code,{target:{value:'😀'.repeat(41)}}));
    assert.equal(code.value,'😀'.repeat(40));
    await act(async()=>fireEvent.change(code,{target:{value:''}}));
    if (kind==='supplier') await waitFor(()=>assert.equal(screen.getByRole('combobox',{name:/Country/}).value,'India'));
    else await waitFor(()=>assert.equal(screen.getByRole('combobox',{name:'Account group'}).value,groupId));
    await act(async () => fireEvent.submit(document.querySelector('[data-quick-create-form]')));
    await waitFor(()=>assert.equal(writes.length, 1));
    await waitFor(()=>assert.equal(created?.meta, 'AABBCCDD'));
    assert.equal('code' in writes[0].body, false);
  });
  for (const field of ['code', 'party.code', 'ledger.code']) await check('Purchase displays ' + field + ' beside Code and recovers with automatic generation', async () => {
    const writes = [];
    let created;
    service = async (_endpoint, request) => {
      if (request.path.includes('/configuration/options/countries')) return page([{value:'IN',label:'India',code:'IN'}]);
      if (request.method === 'POST') {
        writes.push(request);
        if (writes.length === 1) throw {status:422,message:'Validation failed',fields:{[field]:'Choose a unique Code or leave it blank.'}};
        return {id:'01990000-0000-7000-8000-000000000050',company_id:COMPANY,row_version:1,status:'ACTIVE',code:'AABBCCDD',name:'Office'};
      }
      throw {status:404,message:'Unexpected '+request.path};
    };
    render(React.createElement(SupplierQuickCreate, {company:COMPANY,companyCountry:'IN',canTax:false,onCreated:value=>{created=value;},onClose(){}}));
    const code = screen.getByRole('textbox', {name:/Supplier code/});
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox', {name:/Supplier name/}), {target:{value:'Office'}});
      fireEvent.change(code, {target:{value:'TAKEN'}});
    });
    await waitFor(()=>assert.equal(screen.getByRole('combobox',{name:/Country/}).value,'India'));
    await act(async()=>fireEvent.submit(document.querySelector('[data-quick-create-form]')));
    await waitFor(()=>assert.match((code.getAttribute('aria-describedby')||'').split(' ').map(id=>document.getElementById(id)?.textContent||'').join(' '), /Choose a unique Code/));
    assert.equal(screen.queryByText('The supplier was not created'), null);
    await act(async()=>fireEvent.change(code, {target:{value:''}}));
    await act(async()=>fireEvent.submit(document.querySelector('[data-quick-create-form]')));
    await waitFor(()=>assert.equal(created?.meta,'AABBCCDD'));
    assert.equal(writes.length,2);
    assert.equal(writes[0].body.code,'TAKEN');
    assert.equal('code' in writes[1].body,false);
    assert.notEqual(writes[0].key,writes[1].key);
  });
  console.log(passed + ' regression groups passed');
}
main().catch(error => {console.error(error);process.exitCode=1;});
