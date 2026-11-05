import type {components} from '@janso/api-client/reports';
import {productFieldRequest as request} from './product-fields';

type Source=components['schemas']['SourceGenerationDetail'];
type Command=<T>(path:string,body:unknown,signal:AbortSignal)=>Promise<T>;
type Pending={current:Source|null};
const pending=(source:Source)=>['PENDING','BUILDING','QUEUED','RUNNING'].includes(source.status);
export class FinanceSourceError extends Error {}

/** Recheck owner data for new calculations after five minutes; retained runs stay frozen. */
export function financeSourceStale(verifiedAt:string|null|undefined,now=Date.now()):boolean{
  const timestamp=verifiedAt?Date.parse(verifiedAt):NaN;
  return Number.isFinite(timestamp)&&now-timestamp>5*60*1000;
}

/** Resume an admitted build after a transient read failure; rebuild a failed chain once. */
export async function prepareFinanceSource(base:string,previous:string,signal:AbortSignal,command:Command,candidate:Pending,onWait:()=>void):Promise<Source>{
  const strategies=previous&&candidate.current?.strategy!=='FRESH'?['REFRESH','FRESH']:['FRESH'];
  for(const strategy of strategies){
    let source:Source;
    try{
      source=candidate.current&&pending(candidate.current)?candidate.current:await command<Source>('/report-generations',strategy==='REFRESH'?{strategy,base_generation_id:previous}:{strategy},signal);
    }catch(error){
      signal.throwIfAborted();
      const conflict=error instanceof Error&&'status' in error&&error.status===409;
      if(conflict&&strategy==='REFRESH'&&/latest verified cut|verified versioned base generation/.test(error.message))continue;
      if(!conflict||!error.message.includes('source build is already pending'))throw error;
      // Admission permits one company build. The newest generation is that build or its just-finished cut.
      const page=await request<components['schemas']['ResourcePage']>('reports','GET',base+'/report-generations?limit=1',undefined,undefined,signal);
      const latest=page.items[0];
      if(!latest)throw new FinanceSourceError('The pending accounting build could not be found. Retry the report.');
      source=await request<Source>('reports','GET',base+'/report-generations/'+latest.id,undefined,undefined,signal);
      signal.throwIfAborted();
      if(source.id!==latest.id)throw new FinanceSourceError('The accounting snapshot response changed. Retry the report.');
    }
    candidate.current=source;
    while(pending(source)){
      onWait();
      await new Promise<void>((resolve,reject)=>{
        signal.throwIfAborted();
        const stop=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
        const timer=setTimeout(()=>{signal.removeEventListener('abort',stop);resolve();},1500);
        signal.addEventListener('abort',stop,{once:true});
      });
      const updated=await request<Source>('reports','GET',base+'/report-generations/'+source.id,undefined,undefined,signal);
      signal.throwIfAborted();
      if(updated.id!==source.id)throw new Error('The accounting snapshot response changed. Retry the report.');
      source=updated;candidate.current=source;
    }
    candidate.current=null;
    if(source.status==='READY')return source;
    if(source.strategy==='FRESH')break;
  }
  throw new FinanceSourceError('Accounting data could not be verified after rebuilding. Retry when the accounting source is available.');
}

export function financeRunFailure(code:string|null|undefined,title:string):string{
  if(code==='REPORT_IMPLEMENTATION_UNAVAILABLE')return 'The report service was updated. Refresh the page and run the report again.';
  if(code==='AUTHORITY_REVOKED')return 'Your access changed. Refresh the page to check your current authority.';
  if(code==='REPORT_VERIFICATION_FAILED')return 'The accounting snapshot could not be verified. Retry the report.';
  if(code==='REPORT_CAPACITY_EXCEEDED')return 'This report exceeds its supported capacity. Choose a shorter period.';
  if(code==='DEPENDENCY_UNAVAILABLE')return 'A required reporting service is unavailable. Retry in a moment.';
  return title+' could not complete. Retry the report.';
}
