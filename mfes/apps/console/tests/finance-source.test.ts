import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {financeRunFailure,financeSourceStale,prepareFinanceSource} from '../app/lib/finance-source';
import {productFieldRequest,ProductFieldError} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',async original=>({...await original<typeof import('../app/lib/product-fields')>(),productFieldRequest:vi.fn()}));
beforeEach(()=>vi.mocked(productFieldRequest).mockReset());
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();});

it('rebuilds a failed incremental source once and reports implementation failures accurately',async()=>{
 const command=vi.fn().mockResolvedValueOnce({id:'refresh',status:'QUARANTINED'}).mockResolvedValueOnce({id:'fresh',status:'READY'});
 const result=await prepareFinanceSource('/company','old',new AbortController().signal,command,{current:null},()=>{});
 expect(result.id).toBe('fresh');expect(command.mock.calls.map(call=>call[1])).toEqual([{strategy:'REFRESH',base_generation_id:'old'},{strategy:'FRESH'}]);
 expect(financeRunFailure('REPORT_IMPLEMENTATION_UNAVAILABLE','Profit and Loss')).toMatch(/service was updated/);
 expect(financeRunFailure('REPORT_IMPLEMENTATION_UNAVAILABLE','Profit and Loss')).not.toMatch(/snapshot/);
});

it('bounds source recovery and stops on an aborted wait',async()=>{
 const failed=vi.fn().mockResolvedValue({id:'bad',status:'FAILED'});
 await expect(prepareFinanceSource('/company','old',new AbortController().signal,failed,{current:null},()=>{})).rejects.toThrow(/did not complete/);
 expect(failed).toHaveBeenCalledTimes(2);
 vi.useFakeTimers();const controller=new AbortController(),command=vi.fn().mockResolvedValue({id:'build',status:'BUILDING'});
 const result=prepareFinanceSource('/company','',controller.signal,command,{current:null},()=>{});
 await Promise.resolve();controller.abort();await expect(result).rejects.toMatchObject({name:'AbortError'});
 expect(productFieldRequest).not.toHaveBeenCalled();
});

it('names a quarantined source instead of implying Accounting is offline',async()=>{
 const failed=vi.fn().mockResolvedValue({id:'bad',status:'QUARANTINED',strategy:'FRESH',failure_code:'SOURCE_VERIFICATION_FAILED'});
 await expect(prepareFinanceSource('/company','',new AbortController().signal,failed,{current:null},()=>{})).rejects.toThrow(/failed verification and was quarantined/);
});

it('refreshes snapshots older than five minutes without inventing an age for retained legacy data',()=>{
 const now=Date.parse('2026-11-03T10:00:00Z');
 expect(financeSourceStale('2026-11-03T09:54:59Z',now)).toBe(true);
 expect(financeSourceStale('2026-11-03T09:55:00Z',now)).toBe(false);
 expect(financeSourceStale(null,now)).toBe(false);
});

it('rebuilds when a retained base is no longer the latest verified cut',async()=>{
 const command=vi.fn().mockRejectedValueOnce(new ProductFieldError('refresh requires the latest verified cut in this source epoch',{},409)).mockResolvedValueOnce({id:'fresh',status:'READY'});
 expect((await prepareFinanceSource('/company','old',new AbortController().signal,command,{current:null},()=>{})).id).toBe('fresh');
 expect(command.mock.calls.map(call=>call[1])).toEqual([{strategy:'REFRESH',base_generation_id:'old'},{strategy:'FRESH'}]);
});

it('joins an existing company build instead of admitting another one',async()=>{
 const command=vi.fn().mockRejectedValue(new ProductFieldError('a source build is already pending for this company',{},409));
 vi.mocked(productFieldRequest).mockResolvedValueOnce({items:[{id:'pending',status:'BUILDING'}],page:{next_cursor:null}}).mockResolvedValueOnce({id:'pending',status:'READY',strategy:'FRESH'});
 const result=await prepareFinanceSource('/company','old',new AbortController().signal,command,{current:null},()=>{});
 expect(result.id).toBe('pending');expect(command).toHaveBeenCalledOnce();
 expect(vi.mocked(productFieldRequest).mock.calls.at(-2)?.[2]).toBe('/company/report-generations?limit=1');
});

it('does not rebuild after permission or unrelated admission failures',async()=>{
 const command=vi.fn().mockRejectedValue(new ProductFieldError('Access denied',{},403));
 await expect(prepareFinanceSource('/company','old',new AbortController().signal,command,{current:null},()=>{})).rejects.toMatchObject({status:403});
 expect(command).toHaveBeenCalledOnce();
});
