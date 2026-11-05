import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useServiceCommand } from '../app/lib/service-resource';
import type { ServiceRequest } from '../app/lib/service-call';
it('retries the retained creation body and key without reading changed opening metadata',async()=>{
  const sent:ServiceRequest[]=[];
  const reader=vi.fn(async(request:ServiceRequest)=>{sent.push(structuredClone(request));if(sent.length===1)throw {status:503,message:'Response unavailable'};return {id:'confirmed'};});
  const view=renderHook(()=>useServiceCommand(reader as never));
  const body={name:'Capital',opening:{amount:'100.0001',side:'CREDIT',opening_date:'2026-04-01'}};
  await act(async()=>{await view.result.current.execute({path:'/accounts',method:'POST',body},()=>{});});
  expect(view.result.current.uncertain).toBe(true);
  body.opening.amount='999';
  await act(async()=>{await view.result.current.retry(()=>{});});
  expect(sent).toHaveLength(2);expect(sent[1]).toEqual(sent[0]);expect(view.result.current.uncertain).toBe(false);
});
it('does not send a retry before a request or after a confirmed response',async()=>{
  const reader=vi.fn(async()=>({id:'confirmed'})),view=renderHook(()=>useServiceCommand(reader as never));
  await act(async()=>{expect(await view.result.current.retry(()=>{})).toBeNull();});expect(reader).not.toHaveBeenCalled();
  await act(async()=>{await view.result.current.execute({path:'/accounts',body:{name:'Cash'}},()=>{});expect(await view.result.current.retry(()=>{})).toBeNull();});expect(reader).toHaveBeenCalledTimes(1);
});
it('prevents duplicate submission and clearing while creation is in flight',async()=>{
  let finish!:(value:object)=>void;const reader=vi.fn(()=>new Promise(resolve=>{finish=resolve;})),view=renderHook(()=>useServiceCommand(reader as never));
  let first!:Promise<unknown>;
  await act(async()=>{first=view.result.current.execute({path:'/accounts',body:{name:'Cash'}},()=>{});view.result.current.clear();expect(await view.result.current.execute({path:'/accounts'},()=>{})).toBeNull();});
  expect(reader).toHaveBeenCalledTimes(1);expect(view.result.current.pending).toBe(true);
  await act(async()=>{finish({id:'confirmed'});await first;});expect(view.result.current.pending).toBe(false);
});
it('keeps an unverified receipt locked and rejects a changed creation until confirmed',async()=>{
  const reader=vi.fn(async()=>({id:'confirmed'})),view=renderHook(()=>useServiceCommand(reader as never));
  await act(async()=>{await view.result.current.execute({path:'/accounts',body:{name:'Cash'}},()=>{throw {status:502,message:'Unverified receipt'};});});expect(view.result.current.uncertain).toBe(true);
  await act(async()=>{expect(await view.result.current.execute({path:'/accounts',body:{name:'Changed'}},()=>{})).toBeNull();});expect(reader).toHaveBeenCalledTimes(1);
  await act(async()=>{await view.result.current.retry(()=>{});});expect(reader).toHaveBeenCalledTimes(2);expect(view.result.current.blocked).toBe(false);
});
it('uses a fresh key after an explicit clear or a definitive validation rejection',async()=>{
  const sent:ServiceRequest[]=[],reader=vi.fn(async(request:ServiceRequest)=>{sent.push(request);throw {status:sent.length===1?503:422,message:'Rejected'};}),view=renderHook(()=>useServiceCommand(reader as never));
  await act(async()=>{await view.result.current.execute({path:'/accounts'},()=>{});});
  await act(async()=>{view.result.current.clear();await view.result.current.execute({path:'/accounts'},()=>{});});expect(sent[1]!.key).not.toBe(sent[0]!.key);expect(view.result.current.uncertain).toBe(false);
  await act(async()=>{expect(await view.result.current.retry(()=>{})).toBeNull();await view.result.current.execute({path:'/accounts'},()=>{});});expect(sent[2]!.key).not.toBe(sent[1]!.key);
});
it('retains the key when the native creation is still busy',async()=>{
  const sent:ServiceRequest[]=[],reader=vi.fn(async(request:ServiceRequest)=>{sent.push(request);if(sent.length===1)throw {status:409,message:'request is busy; retry with the same idempotency key'};return {id:'confirmed'};}),view=renderHook(()=>useServiceCommand(reader as never));
  await act(async()=>{await view.result.current.execute({path:'/accounts'},()=>{});});expect(view.result.current.uncertain).toBe(true);
  await act(async()=>{await view.result.current.retry(()=>{});});expect(sent[1]!.key).toBe(sent[0]!.key);
});
