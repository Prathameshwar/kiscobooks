const id='[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
export function allowedReportRequest(method:string,path:string):boolean {
  const inventoryRoute=path.split('?')[0];
  if(new RegExp('^/v2/companies/'+id+'/report-generations/'+id+'/inventory$','i').test(inventoryRoute)) {
    if(method!=='GET'||inventoryRoute.includes('\\')||inventoryRoute.includes('..')||path.includes('#')||/%2f|%5c/i.test(inventoryRoute))return false;
    const query=new URLSearchParams(path.includes('?')?path.slice(path.indexOf('?')+1):'');
    const keys=Array.from(query.keys());
    if(new Set(keys).size!==keys.length||keys.some(key=>!['kind','q','object_id','item_id','cursor','limit'].includes(key)))return false;
    return (!query.has('kind')||['ITEM','LOCATION','GROUP','LOT'].includes(query.get('kind')!))
      &&(!query.has('q')||query.get('q')!.length<=120)
      &&['object_id','item_id'].every(key=>!query.has(key)||new RegExp('^'+id+'$','i').test(query.get(key)!))
      &&(!query.has('cursor')||query.get('cursor')!.length<=4096)
      &&(!query.has('item_id')||query.get('kind')==='LOT')
      &&(!query.has('limit')||/^(?:[1-9]|[1-9][0-9]|100)$/.test(query.get('limit')!));
  }
  if(path.includes('\\')||path.includes('..')||path.includes('#')||/%2f|%5c/i.test(path))return false;
  const route=path.split('?')[0],prefix='^/v2/companies/'+id;
  if(new RegExp(prefix+'/report-runs/'+id+'/hierarchy$','i').test(route)) {
    const query=new URLSearchParams(path.includes('?')?path.slice(path.indexOf('?')+1):'');
    const keys=Array.from(query.keys());
    return method==='GET'&&new Set(keys).size===keys.length
      &&keys.every(key=>['parent','period','show_zero','limit','cursor'].includes(key))
      &&(!query.has('parent')||query.get('parent')==='root'||new RegExp('^(?:head|group|account):'+id+'$').test(query.get('parent')!))
      &&(!query.has('period')||['CURRENT','COMPARATIVE'].includes(query.get('period')!))
      &&(!query.has('show_zero')||['true','false'].includes(query.get('show_zero')!))
      &&(!query.has('limit')||/^(?:[1-9]|[1-9][0-9]|1[0-9]{2}|200)$/.test(query.get('limit')!))
      &&(!query.has('cursor')||query.get('cursor')!.length<=4096);
  }
  if(new RegExp(prefix+'/source-readiness$','i').test(route))return method==='GET'&&!path.includes('?');
  if(new RegExp(prefix+'/overview$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/(?:gst-return-context|gstr1-context)$','i').test(route))return method==='GET'&&route===path;
  if(new RegExp(prefix+'/report-runs/'+id+'/(?:gst-review|gstr1-review)$','i').test(route))return ['GET','POST'].includes(method)&&route===path;
  if(new RegExp(prefix+'/report-runs/'+id+'/(?:gst-records|gstr1-records)$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/report-definitions(?:/[A-Z][A-Z0-9_]{0,63}(?:/field-set)?)?$').test(route))return method==='GET';
  if(new RegExp(prefix+'/report-definitions/[A-Z][A-Z0-9_]{0,63}/validate$').test(route))return method==='POST';
  if(new RegExp(prefix+'/(?:report-generations|report-runs)$','i').test(route))return ['GET','POST'].includes(method);
  if(new RegExp(prefix+'/report-exports$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/(?:report-generations|report-runs|report-exports)/'+id+'$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/report-runs/'+id+'/rows$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/report-runs/'+id+'/rows/[1-9][0-9]{0,18}$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/report-runs/'+id+'/(?:exports|drilldowns|queries|cancel|retry)$','i').test(route))return method==='POST';
  return method==='POST'&&new RegExp(prefix+'/report-exports/'+id+'/(?:cancel|retry)$','i').test(route);
}
