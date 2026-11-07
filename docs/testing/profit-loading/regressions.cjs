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

const { ProfitLossWorkspace }=component('ProfitLossWorkspace.tsx');
const company='01990000-0000-7000-8000-000000000001', gen='01990000-0000-7000-8000-000000000002';
const floor='2026-11-06';let ytd=false;const posts=[],sourcePosts=[];
service=async (_,req)=>{
 if(req.path.endsWith('/report-definitions/PROFIT_LOSS'))return {definition:{code:'PROFIT_LOSS',version:6,title:'Profit and Loss',views:[]},run_enabled:true,parameter_schema:{properties:{}},export_limits:[]};
 if(req.path.includes('/report-generations?'))return {items:[{id:gen,status:'READY'}],page:{next_cursor:null}};
 if(req.path.endsWith('/report-generations/'+gen))return {id:gen,status:'READY',verified_at:new Date().toISOString(),manifest:{control:{coverage_start:floor}}};
 if(req.path.endsWith('/report-runs')&&req.method==='POST'){
  posts.push(req.body);const bad=!ytd&&req.body.parameters.date_from<floor;
  return {id:'01990000-0000-7000-8000-'+String(posts.length+10).padStart(12,'0'),kind:'RUN',code:'PROFIT_LOSS',version:6,generation_id:gen,parameters:req.body.parameters,view:req.body.view,views:[],status:bad?'BLOCKED':'COMPLETE',failure_code:bad?'INSUFFICIENT_ACCOUNTING_HISTORY':null,result:null};
 }
 if(req.path.includes('/rows?'))return {items:[],page:{next_cursor:null,has_more:false}};
 if(req.path.endsWith('/report-generations')&&req.method==='POST'){sourcePosts.push(req);throw Error('Coverage must not trigger a source rebuild');}
 throw Error('Unexpected request '+req.path);
};
const props={company,companyName:'BTCL',actor:gen,permissions:['report.read','report.definition.manage'],year:{id:gen,code:'FY2026',startDate:'2026-04-01',endDate:'2027-03-31',current:true,open:true}};
async function main(){
 render(React.createElement(ProfitLossWorkspace,props));
 await screen.findByText(/This is a partial financial-year report/);
 await waitFor(()=>assert.equal(posts.length,1));
 assert.equal(posts[0].parameters.date_from,floor);assert.equal(sourcePosts.length,0);
 fireEvent.click(screen.getByRole('button',{name:'Filters'}));
 fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-04-01'}});
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Apply filters'})));
 await screen.findByText(/Accounting history is available from/);
 assert.equal(posts.length,2);assert.equal(sourcePosts.length,0);cleanup();
 console.log('PASS automatic P&L opening defaults to valid disclosed history before admission; manual invalid periods do not retry or rebuild.');
 posts.length=0;ytd=true;
 render(React.createElement(ProfitLossWorkspace,props));
 await screen.findByText('No detail rows on this page.');
 fireEvent.click(screen.getByRole('button',{name:'Filters'})); fireEvent.change(screen.getByLabelText('From date'),{target:{value:'2026-04-01'}}); await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Apply filters'}))); await waitFor(()=>assert.equal(posts.length,2)); assert.equal(posts[1].parameters.date_from,'2026-04-01');
 cleanup();
 console.log('PASS explicit full-year imported-YTD P&L remains supported.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
