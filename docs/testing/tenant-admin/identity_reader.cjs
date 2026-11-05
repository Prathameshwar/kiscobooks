/* Read/write ordinary API endpoints using the actual provider token from
   this authorized browser session. The token stays in memory and is never saved. */
const fs=require('node:fs'),path=require('node:path');
module.exports=async function(h,service='identity'){
 h.assert(['identity','catalog','accounting','vouchers'].includes(service),'Unsupported native API service');
 await h.page.request.get(h.auth+'/api/auth/session');
 const configuration={};for(const line of fs.readFileSync(path.join(h.root,'mfes/apps/auth/.env.local'),'utf8').split(/\r?\n/)){const at=line.indexOf('=');if(at>0&&!line.trimStart().startsWith('#'))configuration[line.slice(0,at).trim()]=line.slice(at+1).trim().replace(/^(['"])(.*)\1$/,'$2');}
 const {decode}=require(path.join(h.root,'mfes/apps/auth/node_modules/next-auth/jwt'));
 async function session(){const cookies=await h.context.cookies();const name=cookies.some(c=>c.name.startsWith('next-auth.session-token'))?'next-auth.session-token':'__Secure-next-auth.session-token';const parts=cookies.filter(c=>c.name===name||c.name.startsWith(name+'.')).sort((a,b)=>Number(a.name.slice(name.length+1)||0)-Number(b.name.slice(name.length+1)||0));h.assert(parts.length,'Authenticated session cookie is absent');const value=await decode({token:parts.map(c=>c.value).join(''),secret:configuration.NEXTAUTH_SECRET});h.assert(value?.accessToken,'Provider access token is unavailable');return value;}
 async function refresh(){const result=await h.page.request.post(h.auth+'/api/session/refresh',{headers:{Origin:h.origin,'Content-Type':'application/json'},data:{}});h.assert.equal(result.status(),200,'Real Auth refresh failed; sign in again');}
 return async(apiPath,method='GET',body,key)=>{
  h.assert(apiPath.startsWith('/v1/')&&!/[\\#]/.test(apiPath)&&!/%2f|%5c|\.\./i.test(apiPath),'Only ordinary API paths are allowed');
  if(service!=='identity')h.assert([...h.resources.companies, h.resources.openingCompany].filter(Boolean).some(c=>apiPath.startsWith('/v1/companies/'+c.id+'/')),'Native API is limited to the retained QA companies');
  const requestKey=method!=='GET'?(key||require('node:crypto').randomUUID()):null;
  let token=await session();if(typeof token.accessTokenExpires==='number'&&Date.now()>=token.accessTokenExpires-10000){await refresh();token=await session();}
  const execute=()=>h.page.request.fetch('http://localhost:8090/'+service+apiPath,{method,headers:{Authorization:'Bearer '+token.accessToken,...(requestKey?{'Idempotency-Key':requestKey}: {})},...(body===undefined?{}:{data:body}),timeout:30000});
  let response;try{response=await execute();if(response.status()===401){await refresh();token=await session();response=await execute();}}catch{throw Error('Authenticated API request failed; credentials withheld');}
  return {status:response.status(),body:await response.json().catch(()=>({}))};
 };
};
