import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {NextRequest} from 'next/server';
import {getToken} from 'next-auth/jwt';
import {GET} from '../app/api/report-download/route';
import {allowedReportRequest} from '../app/lib/report-request-policy';

vi.mock('next-auth/jwt',()=>({getToken:vi.fn()}));
const company='00000000-0000-0000-0000-000000000001',identity='00000000-0000-0000-0000-000000000002';
beforeEach(()=>{
  vi.stubEnv('AUTH_URL','http://auth.test');vi.stubEnv('NEXTAUTH_SECRET','test');
  vi.stubEnv('REPORTS_GATEWAY_URL','http://gateway.test/reports');
  vi.mocked(getToken).mockResolvedValue({accessToken:'private-access',accessTokenExpires:Date.now()+60000});
});
afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals();vi.clearAllMocks();});
function call(query=`company=${company}&export=${identity}`,headers:Record<string,string>={}){
  return GET(new NextRequest('http://console.test/api/report-download?'+query,{headers}));
}
it.each(['text/csv','text/html; charset=utf-8','application/pdf','application/zip','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])('streams %s with private headers and no browser bearer grant',async media=>{
  let output:ReadableStreamDefaultController<Uint8Array>|undefined;
  const stream=new ReadableStream<Uint8Array>({start(controller){output=controller;}});
  const upstream=new Response(stream,{headers:{'Content-Type':media}});
  vi.spyOn(upstream,'arrayBuffer').mockRejectedValue(new Error('Do not buffer'));
  vi.spyOn(upstream,'text').mockRejectedValue(new Error('Do not buffer'));
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({token:'private-grant'})).mockResolvedValueOnce(upstream);
  vi.stubGlobal('fetch',fetch);
  const response=await call();expect(response.status).toBe(200);
  expect(response.headers.get('Content-Disposition')).toMatch(/^attachment;/);
  expect(response.headers.get('Cache-Control')).toContain('no-store');
  expect(response.headers.get('Content-Security-Policy')).toContain('sandbox');
  expect([...response.headers].join(' ')).not.toContain('private-grant');
  expect(fetch.mock.calls[1][0]).toContain('/download?token=private-grant');
  output!.enqueue(new TextEncoder().encode('complete artifact'));output!.close();
  expect(await response.text()).toBe('complete artifact');
});
it.each([401,403,409,500])('preserves denied/unavailable status %s before download',async status=>{
  const fetch=vi.fn().mockResolvedValue(new Response('{}',{status}));vi.stubGlobal('fetch',fetch);
  expect((await call()).status).toBe(status);expect(fetch).toHaveBeenCalledTimes(1);
});
it('checks session, identifiers, origin and configuration',async()=>{
  expect((await call(`company=${company}&export=../../private`)).status).toBe(422);
  expect((await call(`company=${company}&export=${identity}&export=${identity}`)).status).toBe(422);
  expect((await call(undefined,{'sec-fetch-site':'cross-site'})).status).toBe(403);
  vi.mocked(getToken).mockResolvedValue(null);expect((await call()).status).toBe(401);
  vi.stubEnv('REPORTS_GATEWAY_URL','');expect((await call()).status).toBe(503);
});
it('refreshes an expired cookie before browser download and returns to the same export',async()=>{
  vi.mocked(getToken).mockResolvedValue({accessToken:'expired',accessTokenExpires:0});
  const response=await call();expect(response.status).toBe(307);
  const target=new URL(response.headers.get('location')!);
  expect(target.origin+target.pathname).toBe('http://auth.test/refresh');
  expect(target.searchParams.get('returnTo')).toBe(`http://console.test/api/report-download?company=${company}&export=${identity}`);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
});
it('streams an authorized PDF inline for print preview, while keeping HTML attachment-only',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({token:'signed'})).mockResolvedValueOnce(new Response('%PDF',{headers:{'Content-Type':'application/pdf'}}));
  vi.stubGlobal('fetch',fetch);
  const response=await call(`company=${company}&export=${identity}&preview=1`);
  expect(response.status).toBe(200);
  expect(response.headers.get('Content-Disposition')).toMatch(/^inline;/);
  expect(response.headers.get('Cache-Control')).toContain('no-store');
  expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(Response.json({token:'signed'})).mockResolvedValueOnce(new Response('<script>bad</script>',{headers:{'Content-Type':'text/html'}})));
  expect((await call(`company=${company}&export=${identity}&preview=1`)).status).toBe(422);
  expect((await call(`company=${company}&export=${identity}&preview=2`)).status).toBe(422);
});
it('rejects invalid responses and recovers network errors',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({token:5})));expect((await call()).status).toBe(502);
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));expect((await call()).status).toBe(503);
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(Response.json({token:'signed'})).mockResolvedValueOnce(new Response('bad',{headers:{'Content-Type':'application/javascript'}})));
  expect((await call()).status).toBe(502);
});
it.each([['GET','/report-definitions'],['GET','/report-definitions/TRIAL_BALANCE/field-set'],['POST','/report-definitions/TRIAL_BALANCE/validate'],['GET','/report-runs'],['GET','/report-exports'],['POST','/report-runs/'+identity+'/drilldowns'],['POST','/report-runs/'+identity+'/exports'],['POST','/report-exports/'+identity+'/cancel']])('allows bounded v2 %s %s',(method,suffix)=>expect(allowedReportRequest(method,'/v2/companies/'+company+suffix)).toBe(true));
it.each([['DELETE','/report-runs'],['POST','/report-exports'],['GET','/report-exports/'+identity+'/download'],['POST','/report-runs/'+identity+'/rows'],['GET','/../internal']])('rejects unsupported v2 %s %s',(method,suffix)=>expect(allowedReportRequest(method,'/v2/companies/'+company+suffix)).toBe(false));
