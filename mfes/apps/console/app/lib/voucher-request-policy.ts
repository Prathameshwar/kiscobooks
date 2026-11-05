const id='[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
export function allowedVoucherRequest(method:string,path:string):boolean {
  if(path.includes('\\')||path.includes('..')||path.includes('#')||/%2f|%5c/i.test(path)) return false;
  const route=path.split('?')[0], prefix='^/v1/companies/'+id;
  if(new RegExp(prefix+'/day-book/query$','i').test(route))return method==='POST'&&!path.includes('?');
  if(new RegExp(prefix+'/day-book/types/'+id+'/revisions$','i').test(route))return method==='GET'&&!path.includes('?');
  if(new RegExp(prefix+'/voucher-type-defaults/bootstrap$','i').test(route))return method==='POST'&&!path.includes('?');
  // Typed administration (`vouchers.type.manage`): create, revise the policy, retire. The service authorizes each
  // again, and treats a retry on the same key as the same command.
  if(method==='POST'&&new RegExp(prefix+'/voucher-types$','i').test(route)) return true;
  if(method==='POST'&&new RegExp(prefix+'/voucher-types/'+id+'/(?:revisions|retire)$','i').test(route)) return true;
  if(new RegExp(prefix+'/voucher-types(?:/'+id+'(?:/(?:field-set|effective-configuration))?)?$','i').test(route)) return method==='GET';
  if(new RegExp(prefix+'/(?:voucher-series|voucher-classes|voucher-templates)$','i').test(route)) return method==='GET';
  if(new RegExp(prefix+'/vouchers$','i').test(route)) return method==='GET'||method==='POST';
  // The Purchase page warns about a bill the supplier has already sent; the service checks again at submit.
  if(new RegExp(prefix+'/vouchers/duplicate-bills$','i').test(route)) return method==='GET';
  if(new RegExp(prefix+'/vouchers/'+id+'$','i').test(route)) return method==='GET'||method==='PUT';
  if(new RegExp(prefix+'/vouchers/'+id+'/(?:history|field-set)$','i').test(route)) return method==='GET';
  if(new RegExp(prefix+'/vouchers/'+id+'/revisions/'+id+'$','i').test(route)) return method==='GET';
  // The workflow's Preview and Accept buttons call these; without them the proxy refused both.
  if(new RegExp(prefix+'/vouchers/'+id+'/(?:invoice-preview|invoice-acceptance)$','i').test(route)) return method==='POST';
  if(new RegExp(prefix+'/vouchers/'+id+'/(?:submit|approve|reject|cancel|issue|accept|decline|expire|artifacts|post|reverse)$','i').test(route)) return method==='POST';
  if(new RegExp(prefix+'/voucher-operations/'+id+'$','i').test(route)) return method==='GET';
  if(new RegExp(prefix+'/voucher-capabilities$','i').test(route))return method==='GET';
  // What each kind's printer prints from a designed layout; the designer blocks the rest.
  if(new RegExp(prefix+'/print-capabilities$','i').test(route))return method==='GET'&&route===path;
  if(new RegExp(prefix+'/voucher-operations/'+id+'/(?:recover|cancel)$','i').test(route))return method==='POST';
  if(new RegExp(prefix+'/voucher-import-templates$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/voucher-imports$','i').test(route))return method==='GET'||method==='POST';
  if(new RegExp(prefix+'/voucher-imports/'+id+'(?:/vouchers(?:/[A-Za-z0-9][A-Za-z0-9_.-]{0,63})?|/report-ticket|/report)?$','i').test(route))return method==='GET';
  if(new RegExp(prefix+'/voucher-imports/'+id+'/(?:validate|commit|cancel|run)$','i').test(route))return method==='POST';
  return false;
}
