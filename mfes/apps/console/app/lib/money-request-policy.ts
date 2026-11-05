import {allowedReportRequest} from './report-request-policy';
const id='[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
export function allowedMoneyRequest(service:string,method:string,path:string):boolean{
  if(path.includes('\\')||path.includes('..')||path.includes('#')||/%2f|%5c/i.test(path))return false;
  const route=path.split('?')[0],prefix='^/v1/companies/'+id;
  if(service==='reports'){
    if(route.startsWith('/v2/'))return allowedReportRequest(method,path);
    if(new RegExp(prefix+'/report-definitions(?:/[A-Z_]+/field-set)?$').test(route))return method==='GET';
    if(new RegExp(prefix+'/(?:report-generations|report-runs)$','i').test(route))return method==='GET'||method==='POST';
    return method==='GET'&&new RegExp(prefix+'/(?:report-generations/'+id+'|report-runs/'+id+'(?:/(?:rows|download))?)$','i').test(route);
  }
  if(service==='accounting'){
    if(new RegExp(prefix+'/invoice-records(?:/'+id+')?$','i').test(route)){
      if(method!=='GET')return false;
      if(new RegExp('/invoice-records/'+id+'$','i').test(route))return route===path;
      const query=new URLSearchParams(path.split('?')[1]);
      return [...query.keys()].every(key=>['limit','cursor','date_from','date_to'].includes(key)&&query.getAll(key).length===1)
        &&['date_from','date_to'].every(key=>!query.has(key)||/^\d{4}-\d{2}-\d{2}$/.test(query.get(key)!))
        &&(!query.has('cursor')||query.get('cursor')!.length<=4096)
        &&(!query.has('limit')||/^(?:[1-9]|[1-9][0-9]|1[0-9]{2}|200)$/.test(query.get('limit')!));
    }
    if(new RegExp(prefix+'/bank-reconciliation/sessions(?:/'+id+')?$','i').test(route)){
      if(method!=='GET')return false;const query=new URLSearchParams(path.split('?')[1]);
      if(new RegExp('/sessions/'+id+'$','i').test(route))return route===path;
      return [...query.keys()].every(key=>['account_id','limit','after'].includes(key)&&query.getAll(key).length===1)&&new RegExp('^'+id+'$','i').test(query.get('account_id')??'')&&(!query.has('after')||new RegExp('^'+id+'$','i').test(query.get('after')??''))&&(!query.has('limit')||/^(?:[1-9]|[1-9][0-9]|1[0-9]{2}|200)$/.test(query.get('limit')??''));
    }
    if(new RegExp(prefix+'/(?:gst-return-records|gst-outward-records)$','i').test(route))return method==='POST'&&route===path;
    if(new RegExp(prefix+'/finance/field-sets/(?:gst-return-records|gst-outward-records)$','i').test(route))return method==='GET'&&route===path;
    if(new RegExp(prefix+'/finance/field-sets/bank-instrument-events$','i').test(route))return method==='GET';
    if(new RegExp(prefix+'/(?:parties|accounts|open-items|account-groups|fiscal-years|bank-instruments)(?:/'+id+')?$','i').test(route))return method==='GET';
    // The dated balance of one open item: how much of a supplier advance can still be applied on a bill.
    if(new RegExp(prefix+'/open-items/'+id+'/balance$','i').test(route))return method==='GET';
    // The dated ledger balance of one party account: what a supplier is owed or owes, read once when a supplier is chosen on a bill.
    if(new RegExp(prefix+'/ledger/balance$','i').test(route))return method==='GET';
    if(new RegExp(prefix+'/bank-instruments/'+id+'/events$','i').test(route))return method==='GET'||method==='POST';
    if(new RegExp(prefix+'/bank-instruments/adopt$','i').test(route))return method==='POST';
    return method==='GET'&&new RegExp(prefix+'/fiscal-years/'+id+'/readiness$','i').test(route);
  }
  return false;
}
