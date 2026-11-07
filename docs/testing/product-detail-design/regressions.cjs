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
  if (request.endsWith('/ProductModeProvider')) return { useProductMode: () => ({ company: '01990000-0000-7000-8000-000000000001', data: { product_family_sku_enabled: false, row_version: 1 }, loading: false, failure: null }) };
  if (request.endsWith('/service-call')) return { ...original.call(this, request, parent, isMain), serviceCall: (...args) => service(...args) };
  if (request.endsWith('/product-fields')) return { ...original.call(this, request, parent, isMain), productFieldRequest: (name, method, url, body, key) => service('/api/product-fields', { service: name, method: method === 'GET' ? undefined : method, path: url, body, key }) };
  return original.call(this, request, parent, isMain);
};
const { render, screen, cleanup, fireEvent, act } = dep('@testing-library/react');
const lib = file => require(path.join(app, 'app/lib', file));
const component = file => require(path.join(app, 'app/components', file));
const { waitFor } = dep('@testing-library/react');

console.log('Loading product detail components...');
const { ProductDetailHeader,ProductDetailView }=component('ProductDetailView.tsx');
const { SimpleProductRecord }=component('SimpleProductRecord.tsx');
const { ProductCatalogDetail }=component('ProductCatalogDetail.tsx');
console.log('Loading product fixtures...');
const fixtures=require(path.join(app,'tests/product-classification-fixtures.ts'));
const { fields,access,COMPANY,RECORD,SOURCE,response }=fixtures;
const { masterConfig }=lib('catalog-masters.ts');
const row={id:RECORD,company_id:COMPANY,name:'Banjara Blue Notebook',code:'BN-A5-BLUE',sku:'BN-A5-BLUE',status:'ACTIVE',kind:'GOODS',description:'A5 ruled notebook.\nBlue cover with 160 pages.\nDesigned for everyday writing and organised notes.',sellable:true,purchasable:false,min_sale_quantity:'2.0000',row_version:4,revision:'signed-test-revision',authoring_version:1,custom_fields:{},shared_custom_fields:{}};
const metadata=[...fields('catalog.item'),...fields('catalog.product_family').filter(f=>['kind','description'].includes(f.key))];
const simpleFields=[...fields('catalog.item','update'),...fields('catalog.product_family','update').filter(f=>['kind','description'].includes(f.key))].map(f=>({...f,key:f.key==='sku'?'code':f.key}));
const writes=[];
const reads=[];
service=async (_,request)=>{
 if(!request.method)reads.push(request.path);
 if(request.method==='PATCH'){writes.push(request);return {...row,...request.body};}
 if(request.path.includes('/products/field-set'))return {company_id:COMPANY,authoring_version:1,fields:simpleFields};
 if(request.path.endsWith('/products/'+RECORD)||request.path.endsWith('/items/'+RECORD)||request.path.endsWith('/product-families/'+RECORD))return row;
 return response(request);
};
const artifacts=path.join(root,'.test_artifacts/product-detail-design');fs.mkdirSync(artifacts,{recursive:true});
const cssNames=[...fs.readFileSync(path.join(app,'app/layout.tsx'),'utf8').matchAll(/import '@janso\/ui\/styles\/([^']+)'/g)].map(m=>m[1]);
let css=cssNames.map(n=>fs.readFileSync(path.join(root,'mfes/packages/ui/src/styles',n),'utf8')).join('\n');
css=css.replace(/@import[^;]+;/g,'')+'\n'+fs.readFileSync(path.join(root,'mfes/packages/ui/src/styles/product-detail.css'),'utf8');
css+='\n'+['globals.css','console.css'].map(name=>fs.readFileSync(path.join(app,'app',name),'utf8')).join('\n');
const font=fs.readFileSync(path.join(root,'mfes/packages/ui/src/assets/fonts/InterVariable.woff2')).toString('base64');
css=css.replaceAll('../assets/fonts/InterVariable.woff2','data:font/woff2;base64,'+font);
const props={company:COMPANY,config:masterConfig('items'),id:RECORD,access,canManage:true};
async function main(){
 console.log('Checking rendered product details...');
 const view=render(React.createElement(React.Fragment,null,React.createElement(ProductDetailHeader,{title:row.name,fields:metadata,row,actions:React.createElement('button',null,'Edit product')}),React.createElement(ProductDetailView,{company:COMPANY,fields:metadata,row,access,returnTo:'/masters/items/'+RECORD})));
 assert.equal(screen.getByRole('heading',{level:1}).textContent,row.name);
 assert.ok(screen.getByRole('region',{name:'Trading'}));assert.ok(!screen.queryByRole('textbox',{name:'Name'}));
 assert.equal(screen.getAllByText('Enabled').length,1);assert.equal(screen.getAllByText('Disabled').length,1);
 for(const link of document.querySelectorAll('nav[aria-label="Product detail sections"] a')) assert.ok(document.getElementById(link.getAttribute('href').slice(1)));
 cleanup();
 console.log('PASS detail presentation, trading values and section targets.');
 render(React.createElement(React.Fragment,null,React.createElement(ProductDetailHeader,{title:row.name,fields:metadata.map(f=>({...f,visible:!['sku','status'].includes(f.key)})),row}),React.createElement(ProductDetailView,{company:COMPANY,fields:metadata.map(f=>({...f,visible:!['sku','status','description','sellable','purchasable','min_sale_quantity'].includes(f.key)})),row,access,returnTo:'/masters/items/'+RECORD})));
 assert.ok(!screen.queryByText('Active'));assert.ok(!screen.queryByRole('heading',{name:'Trading'}));assert.ok(!screen.queryByText(/Blue cover with 160 pages/));cleanup();
 console.log('PASS protected facts and status remain hidden.');
 const beforeReferenceReads=reads.length;
 render(React.createElement(ProductDetailView,{company:COMPANY,fields:metadata,row:{...row,base_unit_id:SOURCE},access:{...access,units:false},returnTo:'/masters/items/'+RECORD}));
 assert.equal(screen.getByRole('textbox',{name:'Base unit'}).value,'Existing reference retained');
 assert.ok(!screen.queryByText(SOURCE));assert.equal(reads.length,beforeReferenceReads);
 cleanup();console.log('PASS denied reference access does not fetch or expose its identifier.');
 for(const scenario of ['simple','sku','profile']){
  const view=render(React.createElement(scenario==='simple'?SimpleProductRecord:ProductCatalogDetail,{...props,config:masterConfig(scenario==='profile'?'product-families':'items')}));
  await screen.findByRole('heading',{name:'Product overview'});
  assert.ok(screen.getByRole('region',{name:'Record details'}));
  assert.ok(screen.getByRole('button',{name:scenario==='profile'?'Manage profile':'Manage product'}));
  for(const theme of ['light','dark','ledger']){
   const geometry=`<script>addEventListener('load',()=>{document.fonts.ready.then(()=>{const boxes=[...document.querySelectorAll('.janso-product-detail__section,.janso-product-detail__hero')].map(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width}});document.body.setAttribute('data-layout',JSON.stringify({width:innerWidth,scroll:document.documentElement.scrollWidth,boxes}));});});</script>`;
   const html='<!doctype html><html data-theme="'+theme+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>'+css+'</style></head><body class="janso-root">'+view.container.innerHTML+geometry+'</body></html>';
   fs.writeFileSync(path.join(artifacts,scenario+'-'+theme+'.html'),html);
  }
  cleanup();console.log('PASS '+scenario+' detail route and visible management trigger.');
 }
 render(React.createElement(SimpleProductRecord,{...props,editing:true}));
 const name=await screen.findByRole('textbox',{name:'Name'});
 assert.ok(!name.disabled);fireEvent.change(name,{target:{value:'Revised notebook'}});
 fireEvent.click(screen.getByRole('button',{name:'Save changes'}));
 await screen.findByText('Changes saved.');
 assert.equal(writes.length,1);assert.equal(writes[0].body.name,'Revised notebook');
 assert.equal(writes[0].body.revision,row.revision);assert.equal(writes[0].body.authoring_version,row.authoring_version);
 cleanup();console.log('PASS unchanged Simple edit form saves the retained revision and authoring version.');
 render(React.createElement(SimpleProductRecord,{...props,canManage:false}));
 await screen.findByRole('heading',{name:'Product overview'});
 assert.ok(!screen.queryByRole('link',{name:'Edit product'}));
 assert.equal(writes.length,1);cleanup();console.log('PASS read-only access hides editing and opening details makes no writes.');
 console.log('ARTIFACTS '+artifacts);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
