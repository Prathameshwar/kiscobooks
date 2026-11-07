// Fixed-behavior workflow regressions using actual React and shared UI controls.
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

const { SerialRegistration } = component('SerialRegistration.tsx');
const { COMPANY, ITEM, RECORD, sourceFixture, trackingFixture } = require(path.join(app, 'tests/stock-tracking-fixtures.ts'));
const rule = {identifier_type:'SERIAL',namespace_rule:'COMPANY',min_count:1,max_count:1,requires_slot:false};
async function run() {
 sessionStorage.clear();
 const writes=[];
 service=async (_,request)=>{
   if(request.path.includes('field-set'))return trackingFixture(request);
   if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,shelf_life_days:null,minimum_remaining_life_days:null,requirements:[rule]};
   if(request.method){writes.push(structuredClone(request));return {id:crypto.randomUUID(),company_id:COMPANY,item_id:ITEM,lot_id:null,status:'ACTIVE',is_held:false,row_version:1,identifiers:request.body.identifiers};}
   throw Error('Unexpected read '+request.path);
 };
 const registered=[];
 render(React.createElement(SerialRegistration,{company:COMPANY,item:ITEM,recoveryScope:'tenant:user',onRegistered:ids=>registered.push(ids)}));
 await screen.findByRole('button',{name:'Add serial unit'});
 fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value:'SCAN-A'}});
 fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});
 fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value:'SCAN-B'}});
 fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});
 assert.equal(screen.getAllByText(/Physical unit/).length,2);
 fireEvent.change(screen.getByLabelText('Registration reason'),{target:{value:'Incoming supplier serials'}});
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Register 2 units'}));await new Promise(r=>setTimeout(r,20));});
 await screen.findByText('2 of 2 units registered.');
 assert.equal(writes.length,2);assert.notEqual(writes[0].key,writes[1].key);
 fireEvent.click(screen.getByRole('button',{name:'Use registered units'}));
 assert.equal(registered.at(-1).length,2);
 console.log('PASS bulk scanner registers units with distinct keys and returns their references');
 cleanup();
 sessionStorage.clear();
 const lost=[], committed=new Map();let fail=true;
 service=async (_,request)=>{
  if(request.path.includes('field-set')) return trackingFixture(request);
  if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,shelf_life_days:null,minimum_remaining_life_days:null,requirements:[rule]};
  if(request.method){lost.push(structuredClone(request));if(!committed.has(request.key))committed.set(request.key,{id:crypto.randomUUID(),company_id:COMPANY,item_id:ITEM,lot_id:null,identifiers:request.body.identifiers});if(lost.length===2&&fail){fail=false;throw {status:503,message:'Lost receipt'};}return committed.get(request.key);}
  throw Error('Unexpected read');
 };
 const show=()=>render(React.createElement(SerialRegistration,{company:COMPANY,item:ITEM,recoveryScope:'tenant:user'}));
 show();await screen.findByRole('button',{name:'Add serial unit'});
 for(const value of ['RELOAD-A','RELOAD-B']){fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value}});fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});}
 fireEvent.change(screen.getByLabelText('Registration reason'),{target:{value:'Receipt recovery'}});
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Register 2 units'}));await new Promise(r=>setTimeout(r,15));});
 await screen.findByText('1 of 2 units registered.');cleanup();show();
 await screen.findByRole('button',{name:'Retry remaining registrations'});
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Retry remaining registrations'}));await new Promise(r=>setTimeout(r,15));});
 await screen.findByText('2 of 2 units registered.');
 assert.equal(lost.length,3);assert.equal(lost[1].key,lost[2].key);assert.deepEqual(lost[1].body,lost[2].body);assert.equal(committed.size,2);
 console.log('PASS partial bulk reload replays only the uncertain unit with its exact key');cleanup();sessionStorage.clear();

 let checkpoints=0;const setItem=dom.window.Storage.prototype.setItem;
 dom.window.Storage.prototype.setItem=function(key,value){if(key.startsWith('serial-registration:')&&!key.endsWith(':command')&&++checkpoints===2)throw Error('Checkpoint unavailable');return setItem.call(this,key,value);};
 const crashWrites=[];const crashReceipts=new Map();
 service=async (_,request)=>{if(request.path.includes('field-set'))return trackingFixture(request);if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,shelf_life_days:null,minimum_remaining_life_days:null,requirements:[rule]};crashWrites.push(structuredClone(request));if(!crashReceipts.has(request.key))crashReceipts.set(request.key,{id:crypto.randomUUID(),company_id:COMPANY,item_id:ITEM,lot_id:null});return crashReceipts.get(request.key);};
 show();await screen.findByRole('button',{name:'Add serial unit'});fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value:'CHECKPOINT-UNIT'}});fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});fireEvent.change(screen.getByLabelText('Registration reason'),{target:{value:'Checkpoint recovery'}});
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Register 1 units'}));await new Promise(r=>setTimeout(r,15));});
 await screen.findByText('Checkpoint unavailable');cleanup();dom.window.Storage.prototype.setItem=setItem;show();await screen.findByRole('button',{name:'Retry remaining registrations'});
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Retry remaining registrations'}));await new Promise(r=>setTimeout(r,15));});
 await screen.findByText('1 of 1 units registered.');assert.equal(crashWrites[0].key,crashWrites[1].key);assert.equal(crashReceipts.size,1);
 console.log('PASS crash after native receipt but before queue checkpoint preserves the unit key');cleanup();sessionStorage.clear();

 let deniedWrites=0;
 service=async (_,request)=>{if(request.path.includes('field-set'))return trackingFixture(request);if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,shelf_life_days:null,minimum_remaining_life_days:null,requirements:[rule]};deniedWrites++;throw Error('Unexpected write');};
 show();await screen.findByRole('button',{name:'Add serial unit'});
 for(const value of ['SS','ß']){fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value}});fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});}
 fireEvent.change(screen.getByLabelText('Registration reason'),{target:{value:'Duplicate check'}});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Register 2 units'}));await new Promise(r=>setTimeout(r,5));});assert.equal(deniedWrites,0);await screen.findByText('This identifier is already entered for another unit.');
 console.log('PASS canonical bulk duplicates fail before the first write');cleanup();sessionStorage.clear();

 const {serialQueueKey}=lib('serial-registration.ts');const badKey=serialQueueKey('tenant:user',COMPANY,ITEM);
 sessionStorage.setItem(badKey,JSON.stringify({units:[{key:crypto.randomUUID(),body:{item_id:RECORD,reason:'Bad scope',identifiers:[{identifier_type:'SERIAL',slot:1,value:'BAD'}]}}]}));
 show();await screen.findByText(/The retained serial queue could not be verified/);assert.equal(screen.getByRole('button',{name:'Register 0 units'}).disabled,true);assert.equal(deniedWrites,0);
 console.log('PASS malformed or wrong-product retained queue fails closed');cleanup();sessionStorage.clear();
 const corrected=[];let secondRejected=false;
 service=async(_,request)=>{if(request.path.includes('field-set'))return trackingFixture(request);if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,requirements:[rule]};corrected.push(structuredClone(request));if(corrected.length===2){secondRejected=true;throw {status:422,message:'Duplicate native identifier',fields:{identifiers:'Identity already registered'}};}return {id:crypto.randomUUID(),company_id:COMPANY,item_id:ITEM,lot_id:null};};
 show();await screen.findByRole('button',{name:'Add serial unit'});for(const value of ['KNOWN-A','NATIVE-CONFLICT']){fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value}});fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});}fireEvent.change(screen.getByLabelText('Registration reason'),{target:{value:'Native rejection recovery'}});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Register 2 units'}));await new Promise(r=>setTimeout(r,10));});assert(secondRejected);fireEvent.click(await screen.findByRole('button',{name:'Correct remaining units'}));fireEvent.change(screen.getByLabelText('Serial number 1'),{target:{value:'CORRECTED-PENDING'}});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Register 1 units'}));await new Promise(r=>setTimeout(r,10));});await screen.findByText('2 of 2 units registered.');assert.equal(corrected.length,3);assert.notEqual(corrected[1].key,corrected[2].key);assert.equal(corrected[2].body.identifiers[0].value,'CORRECTED-PENDING');
 console.log('PASS deterministic rejection can be corrected with a new key without repeating completed units');cleanup();sessionStorage.clear();

 const replacementWrites=[];
 service=async(_,request)=>{if(request.path.includes('field-set'))return {...trackingFixture(request),fields:[...trackingFixture(request).fields,...['replaces_unit_id','expected_replaced_version'].map(key=>({key,visible:true,writable:true,readable:true,required:false}))]};if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,shelf_life_days:null,minimum_remaining_life_days:null,requirements:[rule]};replacementWrites.push(request);return {id:crypto.randomUUID(),company_id:COMPANY,item_id:ITEM,lot_id:null};};
 render(React.createElement(SerialRegistration,{company:COMPANY,item:ITEM,recoveryScope:'tenant:user',replacement:{id:RECORD,item_id:ITEM,row_version:3}}));await screen.findByRole('button',{name:'Add serial unit'});fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value:'CORRECTED-ID'}});fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});fireEvent.change(screen.getByLabelText('Registration reason'),{target:{value:'Correct unused identity'}});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Create audited replacement'}));await new Promise(r=>setTimeout(r,10));});await screen.findByText('1 of 1 units registered.');assert.equal(replacementWrites[0].body.replaces_unit_id,RECORD);assert.equal(replacementWrites[0].body.expected_replaced_version,3);assert(!screen.queryByRole('button',{name:'Start another queue'}));
 console.log('PASS replacement UI submits original identity/version with one new unit');cleanup();sessionStorage.clear();
 const {StockTrackingPage}=component('StockTrackingPage.tsx');const {serialFixture}=require(path.join(app,'tests/stock-tracking-fixtures.ts'));const lifecycleWrites=[];let lifecycleCommitted=false;
 service=async(_,request)=>{if(request.path.includes('field-set'))return trackingFixture(request);if(request.method){lifecycleWrites.push(structuredClone(request));if(!lifecycleCommitted){lifecycleCommitted=true;throw {status:503,message:'Lost hold response'};}return {...serialFixture,is_held:true,row_version:4};}return {...serialFixture,is_held:lifecycleCommitted,row_version:lifecycleCommitted?4:3};};
 const edit=()=>render(React.createElement(StockTrackingPage,{company:COMPANY,kind:'serials',id:RECORD,page:'edit',access:{manage:true,hold:true},recoveryScope:'tenant:user'}));
 edit();fireEvent.change(await screen.findByLabelText('Reason'),{target:{value:'Hold for inspection'}});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Save change'}));await new Promise(r=>setTimeout(r,10));});await screen.findByRole('button',{name:'Retry same save'});cleanup();edit();await screen.findByRole('button',{name:'Retry same save'});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Retry same save'}));await new Promise(r=>setTimeout(r,10));});await screen.findByText('Change saved.');assert.equal(lifecycleWrites.length,2);assert.equal(lifecycleWrites[0].key,lifecycleWrites[1].key);assert.deepEqual(lifecycleWrites[0].body,lifecycleWrites[1].body);assert.equal(lifecycleWrites[1].body.expected_version,3);assert(lifecycleWrites[1].path.endsWith('/hold'));
 console.log('PASS lifecycle reload retains the old action/version even after the native row changes');cleanup();sessionStorage.clear();

 const {PurchaseStockDetails}=component('PurchaseStockDetails.tsx');const {TrackingRecoveryProvider}=component('TrackingRecoveryProvider.tsx');const purchaseWrites=[];
 service=async(_,request)=>{if(request.path.includes('warehouse-configuration'))return {company_id:COMPANY,default_purchase_warehouse_id:RECORD};if(request.path.includes('field-set'))return trackingFixture(request);if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,shelf_life_days:null,minimum_remaining_life_days:null,requirements:[rule]};if(request.method){purchaseWrites.push(request);return {...serialFixture,id:crypto.randomUUID(),identifiers:request.body.identifiers,lot_id:null};}if(request.path.includes('stock-tracking/serials?'))return {items:[{...serialFixture,id:new URL(request.path,'https://fixture.invalid').searchParams.get('id'),lot_id:null}],page:{has_more:false,next_cursor:null}};if(request.path.includes('/warehouses/'))return {id:RECORD,company_id:COMPANY,name:'Warehouse',kind:'GODOWN',is_active:true};return {items:[],page:{has_more:false,next_cursor:null}};};
 const selected=[];const line={key:'p1',kind:'ITEM',subject:ITEM,label:'Phone',received:'2',billed:'2',stock:{warehouseId:RECORD,binId:'',lotId:'',unitIds:[RECORD]}};
 const purchase=canPrepareSerial=>render(React.createElement(TrackingRecoveryProvider,{scope:'tenant:user'},React.createElement(PurchaseStockDetails,{company:COMPANY,line,postingDate:'2026-11-07',canEdit:true,access:{warehouse:true,bin:true,batch:true,serial:true},canReadBatch:true,canPrepareSerial,onChange:value=>selected.push(value)})));
 purchase(false);await screen.findByLabelText('Prepared serials');assert(!screen.queryByRole('button',{name:'Create or scan serials for this purchase'}));cleanup();purchase(true);fireEvent.click(await screen.findByRole('button',{name:'Create or scan serials for this purchase'}));await screen.findByRole('dialog',{name:'Register serials for this purchase'});await screen.findByRole('button',{name:'Add serial unit'});fireEvent.change(screen.getByLabelText('Scan or enter identifier'),{target:{value:'PURCHASE-NEW'}});fireEvent.keyDown(screen.getByLabelText('Scan or enter identifier'),{key:'Enter'});fireEvent.change(screen.getByLabelText('Registration reason'),{target:{value:'Incoming purchase unit'}});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Register 1 units'}));await new Promise(r=>setTimeout(r,10));});await screen.findByRole('button',{name:'Use registered units'});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Use registered units'}));await new Promise(r=>setTimeout(r,10));});assert.equal(selected.at(-1).unitIds.length,2);assert(selected.at(-1).unitIds.includes(RECORD));assert.equal(selected.at(-1).warehouseId,RECORD);assert.equal(purchaseWrites.length,1);assert(purchaseWrites[0].path.endsWith('/stock-tracking/serials'));assert(!screen.queryByRole('dialog'));
 console.log('PASS Purchase registration is permission gated and appends units while preserving destination');cleanup();sessionStorage.clear();
 const readyKey=serialQueueKey('tenant:user',COMPANY,ITEM);sessionStorage.setItem(readyKey,JSON.stringify({units:[{key:crypto.randomUUID(),id:RECORD,body:{item_id:ITEM,identifiers:[{identifier_type:'SERIAL',slot:1,value:'ALREADY-RECEIVED'}],reason:'Previously registered'}}]}));let applied=false;
 service=async(_,request)=>{if(request.path.includes('field-set'))return trackingFixture(request);if(request.path.includes('/context/'))return {...sourceFixture,lot_tracking:false,requirements:[rule]};if(request.path.includes('serials?'))return {items:[],page:{has_more:false,next_cursor:null}};throw Error('Unexpected write');};
 render(React.createElement(SerialRegistration,{company:COMPANY,item:ITEM,recoveryScope:'tenant:user',forReceipt:true,onRegistered:()=>{applied=true;}}));await screen.findByRole('button',{name:'Use registered units'});await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Use registered units'}));await new Promise(r=>setTimeout(r,5));});await screen.findByText(/registered unit is no longer available/);assert.equal(applied,false);
 console.log('PASS Purchase handoff rechecks native eligibility and refuses already-received retained units');cleanup();sessionStorage.clear();
}
run().catch(error=>{console.error(error);process.exitCode=1;});
