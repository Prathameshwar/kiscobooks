import { beforeEach, expect, it, vi } from 'vitest';
const { api } = vi.hoisted(() => ({api:{GET:vi.fn()}}));
vi.mock('@janso/api-client', () => ({createAuditClient:()=>api}));
import { platformAuditDetailLoader, platformAuditLoader } from '../app/lib/platform-audit-api';
beforeEach(()=>api.GET.mockReset());
it('calls the platform audit endpoint with cursor and exact subject scope', async () => {
  api.GET.mockResolvedValue({data:{items:[],page:{has_more:false,next_cursor:null}},response:{ok:true}});
  await platformAuditLoader('subject')({entity_type:'account_review',limit:50,cursor:'signed'},new AbortController().signal);
  expect(api.GET).toHaveBeenCalledWith('/v1/platform-events',expect.objectContaining({params:{query:expect.objectContaining({entity_id:'subject',entity_type:'account_review',cursor:'signed'})}}));
});
it('loads details with the exact partition timestamp and preserves changed markers', async () => {
  api.GET.mockResolvedValue({data:{changes:{name:{changed:true},status:'approved',attested:true,version:3,lifecycle:{from:'active',to:'suspended'}},context:null},response:{ok:true}});
  const result=await platformAuditDetailLoader()({id:'event',occurred_at:'2026-10-22T00:00:00Z'} as never,new AbortController().signal);
  expect(api.GET).toHaveBeenCalledWith('/v1/platform-events/{event_id}',expect.objectContaining({params:{path:{event_id:'event'},query:{occurred_at:'2026-10-22T00:00:00Z'}}}));
  expect(result.changes?.name.changed).toBe(true);
  expect(result.changes?.status).toEqual({from:null,to:'approved'});
  expect(result.changes?.attested).toEqual({from:null,to:'true'});
  expect(result.changes?.version).toEqual({from:null,to:'3'});
  expect(result.changes?.lifecycle).toEqual({from:'active',to:'suspended'});
});
it.each([401,403,404,422,503])('preserves an API failure %s for the shared history UI', async status=>{
  api.GET.mockResolvedValue({response:{ok:false,status}});
  await expect(platformAuditLoader()({},new AbortController().signal)).rejects.toMatchObject({status});
});
