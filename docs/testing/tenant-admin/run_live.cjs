/* Live UI-led acceptance. Writes are restricted to this run's new QA tenant. */
const crypto=require('node:crypto');
const {start}=require('./harness.cjs');
const phase=process.argv[2] || 'provision';
(async()=>{
  const h=await start(phase), {page,resources,test,call,assert,ready}=h;
  try {
    if(phase==='provision') {
      assert(!resources.tenant,'This output already contains a tenant. Use companies/crawl/workflows or a new QA_OUTPUT.');
      const signedIn=await test('TA-SETUP-001','Tenant setup','Sign in as platform operator using Auth UI and real Authentik credentials','Console platform administration opens',async()=>{
        await h.login(page,process.env.QA_USERNAME,process.env.QA_PASSWORD);await page.waitForURL('**/platform');return 'Real Authentik login reached platform administration';
      });
      if(signedIn.status!=='PASS')throw Error('Operator login failed; tenant setup is blocked');
      let owner;
      await test('TA-SETUP-002','Tenant setup','Open tenant creation; submit empty tenant details','Required field validation prevents creation',async()=>{
        await ready('/platform/tenants/new');await page.getByRole('button',{name:'Next',exact:true}).click();
        assert(await page.getByRole('textbox',{name:'Tenant name',exact:true}).isVisible());return 'Empty wizard remains at tenant details; no create request issued';
      });
      await test('TA-SETUP-003','Tenant setup','Fill new tenant name and IN-MH; create a new administrator; attest synthetic email; review and create','Tenant and administrator active; generated credentials supplied once',async()=>{
        await page.getByRole('textbox',{name:'Tenant name',exact:true}).fill(resources.marker);
        await page.getByRole('combobox',{name:'State',exact:true}).selectOption('IN-MH');
        await page.getByRole('button',{name:'Next',exact:true}).click();
        await page.getByRole('textbox',{name:'Administrator full name',exact:true}).fill('QA Tenant Administrator');
        await page.getByRole('textbox',{name:'Administrator email',exact:true}).fill('qa-tenant-'+Date.now().toString(36)+'@example.invalid');
        const confirmation=page.getByRole('checkbox',{name:/I confirm this person controls/});
        if(!await confirmation.isChecked()) await confirmation.locator('..').click();
        await page.getByRole('button',{name:'Next',exact:true}).click();
        await page.getByRole('heading',{name:'Review & create',exact:true}).waitFor();
        const pending=page.waitForResponse(r=>r.url().endsWith('/api/platform') && r.request().postDataJSON()?.path==='/v1/platform/tenants' && r.request().postDataJSON()?.method==='POST');
        await page.getByRole('button',{name:'Create tenant',exact:true}).click();
        const response=await pending,data=await response.json();assert.equal(response.status(),201,data.error?.message);
        resources.tenant=data.id;resources.tenantName=data.name;resources.administrator=data.administrator_id;
        await page.getByRole('heading',{name:'Tenant created',exact:true}).waitFor();
        const password=await page.getByRole('textbox',{name:'One-time password',exact:true}).inputValue();
        assert(password.length>=12);owner={username:data.administrator_username,password};h.privateSave(owner);
        assert.equal(data.status,'active');
        resources.creationRequest={path:'/v1/platform/tenants',key:response.request().postDataJSON().key};
        return 'Created active tenant '+data.id+' through three-step UI; administrator credentials stored only as Windows DPAPI ciphertext in ignored runtime artifacts';
      });
      if(!resources.tenant) throw Error('Tenant creation failed; dependent tests cannot run');
      await test('TA-SETUP-004','Tenant setup','Read new tenant detail through authenticated platform proxy','New tenant remains active',async()=>{
        const r=await call('platform','identity','/v1/platform/tenants/'+resources.tenant);assert.equal(r.status,200);assert.equal(r.body.status,'active');return 'Live readback confirms active tenant';
      },'LIVE_API_SUPPORT');
      await h.context.clearCookies();owner=owner||h.privateLoad();
      await test('TA-AUTH-001','Authentication','Sign in through Auth UI as newly created tenant administrator','Administrator reaches company onboarding without platform access',async()=>{
        await h.login(page,owner.username,owner.password);assert(!new URL(page.url()).pathname.startsWith('/platform'));await h.capture('new-tenant-first-login');return 'Real new administrator login reached '+new URL(page.url()).pathname;
      });
      await test('TA-AUTH-002','Authorization','Call platform tenant directory as new tenant administrator','403 and no tenant list',async()=>{
        const r=await call('platform','identity','/v1/platform/tenants?limit=1');assert.equal(r.status,403);return 'Platform tenant directory refused with 403';
      },'LIVE_API_SUPPORT');
    } else {
      const owner=h.privateLoad();await h.login(page,owner.username,owner.password);
      if(phase==='companies') await require('./companies.cjs')(h);
      else if(phase==='crawl') await require('./crawl.cjs')(h);
      else if(phase==='workflows') await require('./workflows.cjs')(h);
      else if(phase==='additional') await require('./additional.cjs')(h);
      else if(phase==='products') await require('./products.cjs')(h);
      else if(phase==='suppliers') {process.env.QA_SUPPLIERS_ONLY='1';await require('./workflows.cjs')(h);}
      else if(phase==='policies') await require('./policies.cjs')(h);
      else if(phase==='masters') await require('./masters.cjs')(h);
      else if(phase==='verify') await require('./verify.cjs')(h);
      else if(phase==='finish') await require('./finish.cjs')(h);
      else if(phase==='access-checks') await require('./access-checks.cjs')(h);
      else if(phase==='retain-fixtures') await require('./retain-fixtures.cjs')(h);
      else if(phase==='last-mile') await require('./last-mile.cjs')(h);
      else if(phase==='reports') await require('./reports.cjs')(h);
      else throw Error('Unknown phase: '+phase);
    }
  } catch(error) {await test('TA-RUN-'+phase,'Execution','Execute requested phase','Phase completes',async()=>{throw error;});process.exitCode=1;}
  finally{h.save();await h.browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
