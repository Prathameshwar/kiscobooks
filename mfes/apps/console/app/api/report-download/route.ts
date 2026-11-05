import {getToken} from 'next-auth/jwt';
import {NextRequest,NextResponse} from 'next/server';

const identifier=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const media:Record<string,string>={
  'application/zip':'zip',
  'text/csv':'csv','text/html':'html','application/pdf':'pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'xlsx',
};
const failure=(status:number,message:string)=>NextResponse.json({error:{message}},
  {status,headers:{'Cache-Control':'no-store'}});

/** Browser navigation streams the body; neither Next nor React buffers a large export. */
export async function GET(request:NextRequest){
  if(request.headers.get('sec-fetch-site')==='cross-site')return failure(403,'Invalid request origin');
  const entries=[...request.nextUrl.searchParams],company=request.nextUrl.searchParams.get('company'),
    identity=request.nextUrl.searchParams.get('export'),preview=request.nextUrl.searchParams.get('preview');
  if(entries.length!==(preview===null?2:3)||preview!==null&&preview!=='1'||!company||!identity||!identifier.test(company)||!identifier.test(identity))
    return failure(422,'Select a completed report export');
  const secret=process.env.NEXTAUTH_SECRET,authUrl=process.env.AUTH_URL,base=process.env.REPORTS_GATEWAY_URL;
  if(!secret||!authUrl||!base)return failure(503,'Reports service is not configured');
  const session=await getToken({req:request,secret,secureCookie:authUrl.startsWith('https://')});
  if(!session)return failure(401,'Sign in to download the report');
  if(typeof session.accessToken!=='string'||!session.accessToken||typeof session.accessTokenExpires!=='number'||
      !Number.isFinite(session.accessTokenExpires)||Date.now()>=session.accessTokenExpires-10000){
    const target=new URL('/refresh',authUrl);target.searchParams.set('returnTo',request.url);
    const response=NextResponse.redirect(target);response.headers.set('Cache-Control','no-store');return response;
  }
  const proof=request.cookies.get('janso-step-up-'+company.toLowerCase())?.value;
  const headers={Authorization:'Bearer '+session.accessToken,...(proof?{'X-Company-Step-Up':proof}:{})};
  const path=base.replace(/\/$/,'')+'/v2/companies/'+company+'/report-exports/'+identity;
  try{
    const grant=await fetch(path+'/download-token',{headers,cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
    if(!grant.ok)return failure(grant.status,'Report download is unavailable. Check your access and export status.');
    const value=await grant.json();
    if(typeof value.token!=='string'||value.token.length>4096)return failure(502,'Invalid report download response');
    const response=await fetch(path+'/download?token='+encodeURIComponent(value.token),
      {headers,cache:'no-store',redirect:'error',signal:request.signal});
    if(!response.ok)return failure(response.status,'Report download is unavailable. Refresh and retry.');
    const type=response.headers.get('content-type')?.split(';')[0]??'',extension=media[type];
    if(!extension||!response.body)return failure(502,'Unexpected report download format');
    if(preview==='1'&&type!=='application/pdf')return failure(422,'Print preview requires a PDF report');
    const output=new Headers({'Content-Type':response.headers.get('content-type')!,
      'Content-Disposition':`${preview==='1'?'inline':'attachment'}; filename="report-${identity}.${extension}"`,
      'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
      'Content-Security-Policy':"default-src 'none'; sandbox",'Referrer-Policy':'no-referrer'});
    const length=response.headers.get('content-length');
    if(length&&/^\d+$/.test(length))output.set('Content-Length',length);
    return new NextResponse(response.body,{headers:output});
  }catch{return failure(503,'Reports service is unavailable. Retry the download.');}
}
