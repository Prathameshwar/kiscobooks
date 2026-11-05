const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../../..');
const {chromium} = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const output = path.resolve(process.env.QA_OUTPUT || path.join(root, '.test_artifacts/tenant-admin-20261029/live'));
const origin = process.env.QA_CONSOLE_URL || 'http://localhost:4320';
const auth = process.env.QA_AUTH_URL || 'http://localhost:4310';
fs.mkdirSync(output, {recursive:true});
function privateSave(value) {
  const ps = spawnSync('powershell.exe', ['-NoProfile','-Command', '$value = [Console]::In.ReadToEnd(); ConvertTo-SecureString -String $value -AsPlainText -Force | ConvertFrom-SecureString'], {input:JSON.stringify(value),encoding:'utf8'});
  assert.equal(ps.status,0,'Windows protected credential storage failed');
  fs.writeFileSync(path.join(output,'credentials.dpapi'),ps.stdout.trim());
}
function privateLoad(credentialFile=path.join(output,'credentials.dpapi')) {
  const ps=spawnSync('powershell.exe',['-NoProfile','-Command','$secure = [Console]::In.ReadToEnd() | ConvertTo-SecureString; $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure); try { [Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }'],{input:fs.readFileSync(credentialFile,'utf8'),encoding:'utf8'});
  assert.equal(ps.status,0,'Windows protected credential read failed');
  return JSON.parse(ps.stdout);
}
async function login(page,username,password) {
  await page.goto(auth+'/login',{timeout:120000});
  const continueButton=page.getByRole('button',{name:'Continue to sign in',exact:true});await continueButton.waitFor();await page.waitForFunction(el=>Object.keys(el).some(k=>k.startsWith('__reactProps$')&&typeof el[k]?.onClick==='function'),await continueButton.elementHandle(),{timeout:90000});await continueButton.click();
  const end=Date.now()+180000;let submissions=0,continuations=0;
  while(Date.now()<end) {
    if(page.url().startsWith(origin)) {await page.locator('.janso-shell,.janso-setup').first().waitFor({timeout:90000});return;}
    if(page.url().startsWith(auth+'/login')&&await page.getByRole('button',{name:'Continue to sign in',exact:true}).isVisible()){if(++continuations>3)throw Error('Provider sign-in repeatedly returned to the Auth login page; inspect OAuth/provider error logs');await page.getByRole('button',{name:'Continue to sign in',exact:true}).click();await page.waitForTimeout(2000);continue;}
    const identifier=page.getByRole('textbox',{name:/Email or Username|Username/i}).and(page.locator(':visible')).first();
    const secret=page.locator('input[type=password]:visible').first();
    if(await page.locator('ak-loading-overlay:visible').count()) {await page.waitForTimeout(400);continue;}
    if(await identifier.isVisible()) {
      await identifier.fill(username);await identifier.press('Tab');
      await page.getByRole('button',{name:/^(Continue|Log in|Sign in)$/i}).first().click();
      await page.waitForTimeout(2000);
    } else if(await secret.isVisible()) {
      if(++submissions>5)throw Error('Provider repeatedly refused password stage');
      await secret.fill(password);await secret.press('Tab');await page.waitForTimeout(300);
      await page.getByRole('button',{name:/^(Continue|Log in|Sign in)$/i}).first().click();
      await page.waitForTimeout(2000);
    } else await page.waitForTimeout(400);
  }
  throw Error('Real provider sign-in did not reach Console; path='+new URL(page.url()).pathname);
}
async function start(phase) {
  const browser=await chromium.launch({executablePath:process.env.QA_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
  const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}});
  const page=await context.newPage();page.setDefaultTimeout(Number(process.env.QA_ACTION_TIMEOUT_MS || 30000));page.setDefaultNavigationTimeout(120000);
  page.on('dialog',dialog=>dialog.type()==='beforeunload'?dialog.accept():dialog.dismiss());
  const file=path.join(output,'resources.json');
  const resources=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{marker:'QA Tenant '+new Date().toISOString().slice(0,10)+' '+Date.now().toString(36),companies:[],records:[]};
  const results=[], errors=[], network=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{if(response.status()>=400 && new URL(response.url()).origin===origin) network.push({status:response.status(),path:new URL(response.url()).pathname});});
  function save(){
    if(fs.existsSync(file)){
      const latest=JSON.parse(fs.readFileSync(file,'utf8'));
      if(!latest.tenant||!resources.tenant||latest.tenant===resources.tenant){
        for(const company of resources.companies){const prior=latest.companies?.find(c=>c.id===company.id);if(prior){
          for(const key of ['businessKeys','moneyTypes','moneyVouchers'])if(prior[key]&&company[key])company[key]={...prior[key],...company[key]};
          Object.assign(company,{...prior,...company});
        }}
        for(const record of latest.records || [])if(!resources.records.some(r=>r.id===record.id))resources.records.push(record);
        for(const [key,value] of Object.entries(latest))if(!(key in resources))resources[key]=value;
      }
    }
    fs.writeFileSync(file,JSON.stringify(resources,null,2));fs.writeFileSync(path.join(output,phase+'-results.json'),JSON.stringify({phase,results,errors,network},null,2));
  }
  async function capture(id){
    const slug=id.replace(/[^a-zA-Z0-9-]/g,'_').slice(0,150);
    const text=await page.locator('body').innerText({timeout:10000}).catch(()=> '');
    fs.writeFileSync(path.join(output,slug+'.txt'),text.replace(/One-time password[\s\S]*?Copy password/g,'[credential handoff masked]'));
    await page.screenshot({path:path.join(output,slug+'.png'),fullPage:true,timeout:10000,mask:[page.locator('input[type=password]'),page.getByRole('textbox',{name:'One-time password',exact:true})]}).catch(()=>{});
    return path.relative(root,path.join(output,slug+'.png')).replaceAll('\\','/');
  }
  async function test(id,area,steps,expected,run,level='LIVE_UI') {
    const row={id,area,company:resources.currentCompany||'',preconditions:'New active QA tenant; administrator signed in; configured local services',steps,expected,execution_level:level,started_utc:new Date().toISOString()};
    console.log('START '+id);
    try {row.actual=await run();row.status='PASS';}
    catch(error){row.status=error.blocked?'BLOCKED':'FAIL';row.actual=String(error.message).slice(0,2500);row.evidence=await capture(id);}
    results.push(row);save();console.log(JSON.stringify(row));return row;
  }
  async function call(proxy,service,apiPath,method='GET',body,key) {
    const execute=()=>page.evaluate(async input=>{
      const response=await fetch(input.proxy,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input.data),signal:AbortSignal.timeout(60000)});
      return {status:response.status,body:await response.json()};
    },{proxy:'/api/'+proxy,data:{service,path:apiPath,method,...(body===undefined?{}:{body}),...(key?{key}:{})}});
    async function stableRead(){for(let attempt=0;attempt<3;attempt++){try{return await execute();}catch(error){if(method!=='GET'||attempt===2||!/Execution context was destroyed|Cannot find context|navigation/i.test(error.message))throw error;await page.waitForLoadState('domcontentloaded',{timeout:30000}).catch(()=>{});await page.waitForTimeout(600);}}}
    let result=await stableRead();if(result.status===401&&method==='GET'){
      const renewed=await page.request.post(auth+'/api/session/refresh',{headers:{Origin:origin,'Content-Type':'application/json'},data:{}});
      if(renewed.status()===200)result=await stableRead();
    }return result;
  }
  async function ready(route){let response;for(let attempt=0;attempt<3;attempt++){try{response=await page.goto(origin+route,{timeout:120000,waitUntil:'domcontentloaded'});break;}catch(error){if(!/ERR_ABORTED|interrupted by another navigation/.test(error.message)||attempt===2)throw error;await page.waitForTimeout(1000);}}if(new URL(page.url()).origin!==origin){const eventFile=path.join(output,'authentication-recovery-events.json');const events=fs.existsSync(eventFile)?JSON.parse(fs.readFileSync(eventFile,'utf8')):[];events.push({started_utc:new Date().toISOString(),requested_route:route,landed_origin:new URL(page.url()).origin,landed_path:new URL(page.url()).pathname});fs.writeFileSync(eventFile,JSON.stringify(events,null,2));const owner=privateLoad();await login(page,owner.username,owner.password);response=await page.goto(origin+route,{timeout:120000,waitUntil:'domcontentloaded'});assert.equal(new URL(page.url()).origin,origin,'Authentication recovery did not reach the intended application');}await page.getByRole('heading',{level:1}).first().waitFor({timeout:20000}).catch(()=>{});await page.waitForLoadState('networkidle',{timeout:10000}).catch(()=>{});await page.getByRole('main').getByRole('status').filter({hasText:/^Loading/i}).first().waitFor({state:'hidden',timeout:10000}).catch(()=>{});await page.waitForTimeout(600);return response;}
  async function switchCompany(company){
    // Company scenarios start with a real authenticated exchange; expiry itself has
    // a separate acceptance runner that deliberately waits for the provider boundary.
    const renewed=await page.request.post(auth+'/api/session/refresh',{headers:{Origin:origin,'Content-Type':'application/json'},data:{}});
    assert.equal(renewed.status(),200,'Real authentication refresh failed before company selection');
    resources.currentCompany=company.id;
    await ready('/companies');const row=page.getByRole('row').filter({hasText:company.name}).first();const trigger=row.getByRole('button',{name:'Actions for '+company.name,exact:true});
    await trigger.waitFor();await page.waitForFunction(el=>Object.keys(el).some(key=>key.startsWith('__reactProps$') && typeof el[key]?.onClick==='function'),await trigger.elementHandle(),{timeout:20000});await trigger.click();
    await page.getByRole('menu').waitFor();
    if(await page.getByRole('menuitem',{name:/^Already open/}).count()){await page.keyboard.press('Escape');return;}
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/company-context') && r.request().method()==='POST');pending.catch(()=>{});await page.getByRole('menuitem',{name:'Open this company',exact:true}).click();assert.equal((await pending).status(),200);await page.waitForTimeout(800);await ready('/companies');assert((await page.locator('.janso-switcher').first().innerText()).includes(company.name),'Selected company did not match '+company.name);
  }
  return {browser,context,page,resources,results,errors,network,test,call,ready,capture,save,switchCompany,root,output,origin,auth,assert,login,privateSave,privateLoad};
}
module.exports={start,login,privateSave,privateLoad,root,output,origin,auth};
