import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST } from '../app/api/product-fields/route';
import { allowedProductRequest } from '../app/lib/product-request-policy';
vi.mock('next-auth/jwt',() => ({getToken:vi.fn()}));
const token=vi.mocked(getToken);
const company='00000000-0000-0000-0000-000000000001';
const path='/v1/companies/'+company+'/items';
it('allows only company-scoped frozen inventory reference reads',()=>{
  const path='/v2/companies/'+company+'/report-generations/'+company+'/inventory?kind=ITEM&q=wire&limit=50';
  expect(allowedProductRequest('reports','GET',path)).toBe(true);
  expect(allowedProductRequest('reports','POST',path)).toBe(false);
  expect(allowedProductRequest('reports','GET',path+'&secret=value')).toBe(false);
  expect(allowedProductRequest('reports','GET','/internal/v1/stock-report-sources')).toBe(false);
});
it('preserves product search punctuation as query data under the trusted gateway', async () => {
  const route = '/v1/companies/' + company + '/products?' + new URLSearchParams({ q: 'AC/DC .. https://other.invalid/a', limit: '25' });
  const fetch = vi.fn().mockResolvedValue(Response.json({ items: [] })); vi.stubGlobal('fetch', fetch);
  const result = await call({ service: 'catalog', method: 'GET', path: route });
  expect(result.status).toBe(200);
  expect(fetch).toHaveBeenCalledWith('http://gateway.test/catalog' + route, expect.objectContaining({ method: 'GET', redirect: 'error' }));
});
beforeEach(() => {vi.stubEnv('AUTH_URL','http://auth.test');vi.stubEnv('IDENTITY_URL','http://gateway.test');vi.stubEnv('CATALOG_GATEWAY_URL','http://gateway.test/catalog');vi.stubEnv('NEXTAUTH_SECRET','test');token.mockResolvedValue({accessToken:'test-access',accessTokenExpires:Date.now()+60000});});
afterEach(() => {vi.unstubAllEnvs();vi.unstubAllGlobals();vi.clearAllMocks();});
function call(input:unknown,origin='http://console.test') {return POST(new NextRequest('http://console.test/api/product-fields',{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify(input)}));}
it.each(['company_currency=true&value=INR&limit=1', 'company_currency=true&limit=50', 'base_only=true&limit=50'])('forwards the currency restriction %s to Accounting', async query => {
  vi.stubEnv('ACCOUNTING_GATEWAY_URL', 'http://gateway.test/accounting');
  const route = `/v1/companies/${company}/configuration/options/currencies?${query}`;
  const choices = { items: [{ value: 'INR', label: 'Indian rupee' }], page: { has_more: false, next_cursor: null, limit: 50 } };
  const fetch = vi.fn().mockResolvedValue(Response.json(choices)); vi.stubGlobal('fetch', fetch);
  const result = await call({ service: 'accounting', method: 'GET', path: route });
  expect(result.status).toBe(200); expect(await result.json()).toEqual(choices);
  expect(fetch).toHaveBeenCalledWith('http://gateway.test/accounting' + route, expect.objectContaining({ method: 'GET' }));
});
it.each([
  ['POST', 'currencies?company_currency=true'], ['GET', 'parties?company_currency=true'],
  ['GET', 'currencies?company_currency=invalid'], ['GET', 'currencies?base_only=invalid'],
  ['GET', 'currencies?company_currency=true&company_currency=false'], ['GET', 'currencies?unknown=true'],
])('refuses unsupported currency option requests: %s %s', (method, suffix) => {
  expect(allowedProductRequest('accounting', method, `/v1/companies/${company}/configuration/options/${suffix}`)).toBe(false);
});
it.each([
  ['POST', '/products', 45000], ['POST', '/product-families', 45000],
  ['GET', '/products', 15000], ['PATCH', '/products/' + company, 15000],
])('uses the aggregate creation budget only for %s %s', async (method, suffix, budget) => {
  const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(new AbortController().signal);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ id: company })));
  try {
    expect((await call({ service: 'catalog', method, path: '/v1/companies/' + company + suffix, key: 'same-create', body: {} })).status).toBe(200);
    expect(timeout).toHaveBeenCalledWith(budget);
  } finally { timeout.mockRestore(); }
});
it('loads the Items page product structure settings through the catalog gateway', async () => {
 const route = '/v1/companies/' + company + '/product-configuration/authoring';
 const settings = { company_id: company, product_family_sku_enabled: false, row_version: 0, policy_generation: 1 };
 const fetch = vi.fn().mockResolvedValue(Response.json(settings)); vi.stubGlobal('fetch', fetch);
 const result = await call({ service: 'catalog', method: 'GET', path: route });
 expect(result.status).toBe(200); expect(await result.json()).toEqual(settings);
 expect(fetch).toHaveBeenCalledWith('http://gateway.test/catalog' + route, expect.objectContaining({ method: 'GET', headers: expect.objectContaining({ Authorization: 'Bearer test-access' }) }));
});
it.each([['reports','POST','/report-runs'],['reports','GET','/report-runs/'+company+'/download?token=signed'],['accounting','GET','/bank-instruments'],['accounting','POST','/bank-instruments/'+company+'/events'],['accounting','GET','/finance/field-sets/bank-instrument-events'],['vouchers','POST','/vouchers/'+company+'/post'],['vouchers','POST','/vouchers/'+company+'/reverse']])('allows scoped money request %s %s %s',(service,method,suffix)=>{expect(allowedProductRequest(service,method,'/v1/companies/'+company+suffix)).toBe(true);});
it.each([['reports','POST','/report-runs/'+company+'/download'],['accounting','DELETE','/bank-instruments/'+company],['accounting','POST','/journals'],['vouchers','GET','/vouchers/'+company+'/post'],['reports','GET','/report-runs/%2fprivate']])('rejects unrelated money request %s %s %s',(service,method,suffix)=>{expect(allowedProductRequest(service,method,'/v1/companies/'+company+suffix)).toBe(false);});
it('proxies signed report downloads as private CSV without returning the gateway token',async()=>{
 vi.stubEnv('REPORTS_GATEWAY_URL','http://gateway.test/reports');
 const fetch=vi.fn().mockResolvedValue(new Response('amount\n1.0000',{headers:{'content-type':'text/csv'}}));vi.stubGlobal('fetch',fetch);
 const result=await call({service:'reports',method:'GET',path:'/v1/companies/'+company+'/report-runs/'+company+'/download?token=signed'});
 expect(result.status).toBe(200);expect(result.headers.get('Cache-Control')).toBe('no-store');expect(result.headers.get('Content-Type')).toContain('text/csv');expect(await result.text()).toBe('amount\n1.0000');
 expect(fetch.mock.calls[0][0]).toContain('http://gateway.test/reports/v1/companies/');
});
it.each([['reports','GET','/report-generations/'+company],['accounting','GET','/bank-instruments/'+company],['accounting','POST','/bank-instruments/adopt'],['accounting','GET','/fiscal-years/'+company+'/readiness']])('allows read and adoption handoff %s %s %s',(service,method,suffix)=>{expect(allowedProductRequest(service,method,'/v1/companies/'+company+suffix)).toBe(true);});
it.each(['/bank-instruments/'+company+'/events','/bank-instruments/adopt','/fiscal-years/'+company+'/readiness'])('does not widen banking methods %s',suffix=>{expect(allowedProductRequest('accounting','DELETE','/v1/companies/'+company+suffix)).toBe(false);});
it.each([['catalog','GET',path],['catalog','PATCH',path+'/'+company],['identity','GET','/v1/custom-field-definitions'],['identity','POST','/v1/custom-field-definitions'],['catalog','POST','/v1/companies/'+company+'/entities/catalog.item/custom-field-adoption/preview']])('allows its bounded route %s %s %s',(service,method,route) => {expect(allowedProductRequest(service,method,route)).toBe(true);});
it.each(['https://attacker.test','/internal/v1/anything','/v1/companies/../secret','/v1/companies/'+company+'/entities/catalogXitem/field-set'])('refuses other routes %s',route => {expect(allowedProductRequest('catalog','GET',route)).toBe(false);});
it('checks origin and session before forwarding',async () => {expect((await call({service:'catalog',method:'GET',path},'http://attacker.test')).status).toBe(403);token.mockResolvedValue(null);expect((await call({service:'catalog',method:'GET',path})).status).toBe(401);});
it('forwards through the trusted gateway and preserves service validation errors',async () => {
  const fetch=vi.fn().mockResolvedValue(Response.json({error:{message:'Invalid',fields:{'custom_fields.cf_note':'Required'}}},{status:422}));vi.stubGlobal('fetch',fetch);
  const result=await call({service:'catalog',method:'PATCH',path:path+'/'+company,body:{expected_version:1},key:'retry_1'});
  expect(result.status).toBe(422);expect((await result.json()).error.fields).toEqual({'custom_fields.cf_note':'Required'});
  expect(fetch).toHaveBeenCalledWith('http://gateway.test/catalog'+path+'/'+company,expect.objectContaining({redirect:'error',headers:expect.objectContaining({'Idempotency-Key':'retry_1',Authorization:'Bearer test-access'})}));
});
it('forwards an exact FX candidate with its retry identity through the Accounting boundary', async () => {
  vi.stubEnv('ACCOUNTING_GATEWAY_URL', 'http://gateway.test/accounting');
  const fetch = vi.fn().mockResolvedValue(Response.json({ id: company, rate: '83.123456789012' }, { status: 201 })); vi.stubGlobal('fetch', fetch);
  const body = { from_currency: 'USD', to_currency: 'INR', rate: '83.123456789012', source_reference: 'Reviewed treasury quote' };
  const route = '/v1/companies/' + company + '/exchange-rates/candidates';
  const result = await call({ service: 'accounting', method: 'POST', path: route, key: 'same-quote', body });
  expect(result.status).toBe(201); expect((await result.json()).rate).toBe(body.rate);
  expect(fetch).toHaveBeenCalledWith('http://gateway.test/accounting' + route, expect.objectContaining({ body: JSON.stringify(body), headers: expect.objectContaining({ 'Idempotency-Key': 'same-quote' }) }));
});
it('reports unavailable configuration and upstream failures',async () => {vi.stubEnv('CATALOG_GATEWAY_URL','');expect((await call({service:'catalog',method:'GET',path})).status).toBe(503);vi.stubEnv('CATALOG_GATEWAY_URL','http://gateway.test/catalog');vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));expect((await call({service:'catalog',method:'GET',path})).status).toBe(503);});

it.each([['GET','/items/'+company+'/attribute-form'],['PUT','/items/'+company+'/attributes'],['PUT','/product-families/'+company+'/attributes'],['POST','/product-families/'+company+'/variants'],['POST','/attribute-definitions'],['PATCH','/attribute-options/'+company],['POST','/attribute-options/'+company+'/activate'],['GET','/entities/catalog.attribute_option/field-set'],['GET','/units']])('allows attribute workflow %s %s',(method,suffix)=>expect(allowedProductRequest('catalog',method,'/v1/companies/'+company+suffix)).toBe(true));
it('allows only the protected barcode scan lookup',()=>{expect(allowedProductRequest('catalog','POST','/v1/companies/'+company+'/barcodes/resolve')).toBe(true);expect(allowedProductRequest('catalog','GET','/v1/companies/'+company+'/barcodes/resolve')).toBe(false);});
it.each([['POST','/items/'+company+'/attribute-form'],['DELETE','/attribute-definitions/'+company],['POST','/attribute-options/activate'],['PUT','/units'],['POST','/entities/catalog.attribute_option/field-set']])('rejects unrelated attribute methods %s %s',(method,suffix)=>expect(allowedProductRequest('catalog',method,'/v1/companies/'+company+suffix)).toBe(false));
it.each([['text/csv','csv','import_key\nA'],['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','xlsx','PK']])('passes voucher import %s files through privately',async(media,extension,body)=>{
 vi.stubEnv('VOUCHERS_GATEWAY_URL','http://gateway.test/vouchers');
 const fetch=vi.fn().mockResolvedValue(new Response(body,{headers:{'content-type':media}}));vi.stubGlobal('fetch',fetch);
 const result=await call({service:'vouchers',method:'GET',path:'/v1/companies/'+company+'/voucher-import-templates?voucher_type_id='+company+'&format=CSV'});
 expect(result.status).toBe(200);expect(result.headers.get('Cache-Control')).toBe('no-store');
 expect(result.headers.get('Content-Disposition')).toBe('attachment; filename="voucher-import.'+extension+'"');
 expect(await result.text()).toBe(body);
 const failed=vi.fn().mockResolvedValue(Response.json({error:{message:'Denied'}},{status:403,headers:{'content-type':'text/csv'}}));vi.stubGlobal('fetch',failed);
 const denied=await call({service:'vouchers',method:'GET',path:'/v1/companies/'+company+'/voucher-import-templates'});
 expect(denied.status).toBe(403);expect((await denied.json()).error.message).toBe('Denied');
});

// A Purchase of 100 lines with ordinary narration is far larger than the 16 KiB a catalog form needs;
// the service accepts up to 256 KiB, so the proxy must not be the thing that refuses a real bill.
const longBill = (lines: number) => ({
  type_revision_id: company, mode: 'ACCOUNTS',
  invoice: { supplies: Array.from({ length: lines }, (_, index) => ({ line_key: company, description: `Line ${index} ` + 'x'.repeat(300), amount: '10.0000' })) },
});
it('forwards a large Purchase create, within the size the Vouchers service accepts', async () => {
  vi.stubEnv('VOUCHERS_GATEWAY_URL', 'http://gateway.test/vouchers');
  const fetch = vi.fn().mockResolvedValue(Response.json({ id: company })); vi.stubGlobal('fetch', fetch);
  const body = longBill(100); expect(JSON.stringify(body).length).toBeGreaterThan(30_000);
  const result = await call({ service: 'vouchers', method: 'POST', path: '/v1/companies/' + company + '/vouchers', key: 'bill-create-1', body });
  expect(result.status).toBe(200);
  expect(fetch).toHaveBeenCalledTimes(1);
});
it('still refuses a body larger than any voucher can be', async () => {
  vi.stubEnv('VOUCHERS_GATEWAY_URL', 'http://gateway.test/vouchers');
  const fetch = vi.fn().mockResolvedValue(Response.json({ id: company })); vi.stubGlobal('fetch', fetch);
  const result = await call({ service: 'vouchers', method: 'POST', path: '/v1/companies/' + company + '/vouchers', key: 'bill-create-2', body: longBill(1100) });
  expect(result.status).toBe(413);
  expect(fetch).not.toHaveBeenCalled();
});
it('does not read a large body for a caller who is not signed in', async () => {
  vi.stubEnv('VOUCHERS_GATEWAY_URL', 'http://gateway.test/vouchers');
  token.mockResolvedValue(null);
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  // Over the cap: a signed-in caller would get 413 after the body is read; an anonymous one must be refused first.
  const result = await call({ service: 'vouchers', method: 'POST', path: '/v1/companies/' + company + '/vouchers', key: 'anon-1', body: longBill(1100) });
  expect(result.status).toBe(401);
  expect(fetch).not.toHaveBeenCalled();
});
