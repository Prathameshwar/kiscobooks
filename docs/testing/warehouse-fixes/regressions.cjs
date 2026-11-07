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

const { ProductWarehousePolicies } = component('ProductWarehousePolicies.tsx');
const { WarehousePolicyReleases } = component('WarehousePolicyReleases.tsx');
const { operationLabels } = lib('warehouse-ui.ts');
const company = '01990000-0000-7000-8000-000000000001', item = '01990000-0000-7000-8000-000000000002';
const keys = ['effective_date','change_reason','selection_mode','default_sale_warehouse_id','default_purchase_warehouse_id','default_customer_return_warehouse_id','default_opening_warehouse_id','warehouse_id','purchase_binding_id','safety_quantity','reorder_quantity','target_quantity','min_order_quantity','max_order_quantity','order_multiple','lead_time_days',...Object.keys(operationLabels)];
const writes=[];
service=async (_, request)=>{
 if(request.method){writes.push(request);return {};}
 if(request.path.includes('/entities/'))return {company_id:company,entity_type:request.path.split('/entities/')[1].split('/')[0],fields:keys.map(key=>({key,visible:true,writable:true}))};
 if(request.path.endsWith('/warehouse-configuration'))return {company_id:company,location_mode:'MULTI_LOCATION'};
 if(request.path.includes('/unit-bindings'))return {items:[{id:item,item_id:item,usage_role:'BASE',code:'PCS'}],page:{has_more:false}};
 if(request.path.endsWith('/policy-releases'))return {policy_generation:1,source_version:1,history:[],current:null};
 return {item_id:item,policy_generation:1,source_version:1,selection_mode:'ALLOW_ALL_ACTIVE',locations:[],scopes:[]};
};
async function main(){
 render(React.createElement(ProductWarehousePolicies,{company,item,canManage:true}));
 await screen.findByRole('button',{name:'Add replenishment band'});
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Add replenishment band'})));
 fireEvent.change(screen.getByLabelText('Target quantity'),{target:{value:'17.1250'}});
 fireEvent.click(screen.getByRole('button',{name:'Review location policy'}));
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Save policy'})));
 await waitFor(()=>assert.equal(writes.length,1));
 await waitFor(()=>assert.equal(screen.getByLabelText('Target quantity').value,'17.1250'));
 assert.equal(writes[0].method,'PUT'); cleanup();
 console.log('PASS product policy save preserves unsaved replenishment quantities.');
 render(React.createElement(WarehousePolicyReleases,{company,canPublish:false}));
 await screen.findByText('Release history');
 assert.equal(screen.queryByRole('button',{name:'Review release'}),null); cleanup();
 console.log('PASS release history respects publication authority.');

 const reader=service, attempts=[];
 service=async (endpoint,request)=>{
  if(request.method){attempts.push(request);if(attempts.length===1)throw {status:503,message:'Reply lost'};return {};}
  return reader(endpoint,request);
 };
 render(React.createElement(WarehousePolicyReleases,{company,canPublish:true}));
 await screen.findByLabelText('Release change reason');
 fireEvent.change(screen.getByLabelText('Release change reason'),{target:{value:'Reviewed stock locations'}});
 fireEvent.click(screen.getByRole('button',{name:'Review company release'}));
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Publish release'})));
 await screen.findByRole('button',{name:'Retry same release'});
 assert.equal(screen.getByLabelText('Release change reason').disabled,true);
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Retry same release'})));
 await waitFor(()=>assert.equal(attempts.length,2));
 assert.equal(attempts[0].key,attempts[1].key);
 assert.deepEqual(attempts[0].body,attempts[1].body);
 cleanup();service=reader;
 console.log('PASS uncertain company publication freezes its review and retries the same command.');

 const { allowedWarehouseAction }=lib('warehouse-request-policy.ts');
 const base='/v1/companies/'+company;
 assert.equal(allowedWarehouseAction('POST',base+'/policy-releases'),true);
 assert.equal(allowedWarehouseAction('PUT',base+'/items/'+item+'/warehouse-policy'),true);
 assert.equal(allowedWarehouseAction('POST',base+'/items/'+item+'/warehouse-policy'),false);
 assert.equal(allowedWarehouseAction('GET',base+'/policy-releases?x=1'),false);
 assert.equal(allowedWarehouseAction('GET',base+'/entities/catalog.item_warehouse_policy/field-set?operation=update&operation=publish'),false);
 console.log('PASS warehouse BFF routes reject unsupported mutations and ambiguous queries.');

 const { PurchaseDetailSections } = component('PurchaseDetailSections.tsx');
 const { PurchaseDetailsPanel } = component('PurchaseDetailsPanel.tsx');
 const { livePurchasePolicy } = lib('purchase-api.ts');
 const { newPurchaseWorkspace } = lib('purchase-workspace.ts');
 const meta={native:{properties:{invoice:{anyOf:[{properties:{components:{}}}]}}},configuration:{policy:{allowed_modes:['ITEMS'],invoice:{charges_allowed:true,manual_discounts_allowed:false}}}};
 const policy=livePurchasePolicy('INR',meta,company), draft=newPurchaseWorkspace('2026-11-07');
 assert.equal(policy.details.panels.components.available,true);
 assert.equal(policy.details.panels.components.writable,true);
 let open=null;
 render(React.createElement(PurchaseDetailSections,{draft,policy,disabled:false,onOpen:value=>{open=value;}}));
 fireEvent.click(screen.getByRole('button',{name:/Charges & discounts/}));
 assert.equal(open,'components'); cleanup();
 render(React.createElement(PurchaseDetailsPanel,{panel:'components',draft,policy,canEdit:true,onApply(){},onClose(){}}));
 assert.ok(screen.getByRole('button',{name:'Add charge'}));
 assert.ok(screen.getByText('No document discounts or charges. Line discounts stay in the bill grid.')); cleanup();
 delete meta.native.properties.invoice.anyOf[0].properties.components;
 assert.deepEqual(livePurchasePolicy('INR',meta,company).details.panels.components,{available:true,writable:false});
 console.log('PASS new product Purchase shows optional charge entry and respects denied write fields.');

}
main().catch(error=>{console.error(error);process.exitCode=1;});
