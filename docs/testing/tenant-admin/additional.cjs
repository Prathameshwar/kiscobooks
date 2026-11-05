module.exports=async function(h){
 const {page,resources,test,ready,assert,call}=h, stamp=resources.marker.slice(-8);
 async function command(button,apiPath,method='POST'){
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/access')&&r.request().postDataJSON()?.path===apiPath&&r.request().postDataJSON()?.method===method);pending.catch(()=>{});
  await page.getByRole('button',{name:button,exact:true}).click();const response=await pending,value=await response.json();assert(response.ok(),response.status()+': '+value.error?.message);return value;
 }
 for(const company of resources.companies){
  resources.currentCompany=company.id;
  await test('TA-WF-SWITCH-'+company.key,'Company selection','Choose '+company.name+' from directory actions and verify actual context','Correct company name in context switcher and API selection succeeds',async()=>{await h.switchCompany(company);return 'UI selection and rendered company context verified';});
  await test('TA-SWITCH-'+company.key,'Company selection','Open companies; select '+company.name+'; verify actual company context','Correct company selected through UI',async()=>{await h.switchCompany(company);return 'Correct company context verified';});
  if(company.productDraft && !company.productRevision)await test('TA-CONFIG-'+company.key+'-RECOVERY','Product configuration','Reopen the saved configuration draft; refresh preview after stale conflict and retry publication','Existing draft publishes through reviewed UI recovery, without creating another scope',async()=>{
   const base='/v1/companies/'+company.id+'/product-configurations/'+company.productDraft,attempts=[];
   for(let attempt=0;attempt<3;attempt++){
    await ready('/products/configuration/drafts/'+company.productDraft);await page.getByRole('button',{name:'Review publication',exact:true}).click();await page.getByRole('dialog',{name:'Publish these product defaults?',exact:true}).waitFor();
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/product-fields')&&r.request().postDataJSON()?.path===base+'/publish');pending.catch(()=>{});await page.getByRole('button',{name:'Publish revision',exact:true}).click();const response=await pending,value=await response.json();attempts.push({status:response.status(),message:value.error?.message});
    if(response.ok()){company.productRevision=value.id;h.save();await page.getByRole('heading',{name:'Published configuration revision',exact:true}).waitFor();return 'Published existing draft after UI review; attempts='+JSON.stringify(attempts);}
    assert.equal(response.status(),409,'Publication failure: '+value.error?.message);
   }
   throw Error('Three refreshed UI publication attempts failed: '+JSON.stringify(attempts));
  });
  if(company.productDraft && !company.productRevision)await test('TA-CONFIG-'+company.key+'-API-RECOVERY','Product configuration','Use authenticated application API to refresh preview and publish the same UI-created draft','UI-created draft publishes with fresh version/generation/source guards',async()=>{
   const base='/v1/companies/'+company.id+'/product-configurations/'+company.productDraft,attempts=[];
   for(let attempt=0;attempt<3;attempt++){
    const preview=await call('product-fields','catalog',base+'/preview');assert.equal(preview.status,200,preview.body.error?.message);
    const response=await call('product-fields','catalog',base+'/publish','POST',{expected_version:preview.body.draft_version,expected_generation:preview.body.policy_generation,expected_source_version:preview.body.source_version},require('node:crypto').randomUUID());attempts.push({status:response.status,message:response.body.error?.message});
    if(response.status<300){company.productRevision=response.body.id;h.save();await ready('/products/configuration/revisions/'+response.body.id);return 'Published same UI-created draft via application API; attempts='+JSON.stringify(attempts);}
    assert.equal(response.status,409,response.body.error?.message);
   }
   throw Error('Fresh application API publication also failed: '+JSON.stringify(attempts));
  },'LIVE_API_SUPPORT_AFTER_UI_FAILURE');
  if(!resources.records.some(r=>r.resource==='departments'&&r.company===company.id))await test('TA-ORG-'+company.key+'-DEPARTMENT','Departments','Create a root QA department; deactivate/reactivate with reason','Department lifecycle preserves its identity and readback',async()=>{
   await ready('/departments/new');await page.getByRole('textbox',{name:'Code',exact:true}).fill(('QA-'+company.key.slice(0,3)+'-'+stamp).toUpperCase());await page.getByRole('textbox',{name:'Name',exact:true}).fill('QA '+company.key+' department '+stamp);
   const record=await command('Create department','/v1/companies/'+company.id+'/departments');resources.records.push({company:company.id,resource:'departments',id:record.id,name:record.name});h.save();
   await page.getByRole('link',{name:'View department',exact:true}).click();await page.getByRole('button',{name:'Deactivate department',exact:true}).waitFor();
   await page.getByRole('button',{name:'Deactivate department',exact:true}).click();await page.getByRole('textbox',{name:'Reason',exact:true}).fill('QA reversible lifecycle verification');
   const pending=page.waitForResponse(r=>r.url().endsWith('/api/access')&&r.request().postDataJSON()?.method==='POST');pending.catch(()=>{});await page.getByRole('dialog').getByRole('button',{name:'Deactivate',exact:true}).click();assert.equal((await pending).status(),200);
   await page.getByRole('button',{name:'Reactivate department',exact:true}).waitFor();await page.getByRole('button',{name:'Reactivate department',exact:true}).click();await page.getByRole('textbox',{name:'Reason',exact:true}).fill('QA leave department active');
   const restored=page.waitForResponse(r=>r.url().endsWith('/api/access')&&r.request().postDataJSON()?.method==='POST');restored.catch(()=>{});await page.getByRole('dialog').getByRole('button',{name:'Reactivate',exact:true}).click();assert.equal((await restored).status(),200);
   return 'Root department created, deactivated and reactivated through UI; left active';
  });

 }
 await test('TA-ORG-GROUP-CREATE','User groups','Create a tenant user group from New user group UI','Active group saved; empty membership does not grant access',async()=>{
  await ready('/user-groups/new');const inputs=page.locator('main input[required]');for(let i=0;i<await inputs.count();i++){const input=inputs.nth(i),label=await input.evaluate(e=>e.labels?.[0]?.innerText || '');await input.fill(/code/i.test(label)?'QA_'+stamp.toUpperCase():'QA review group '+stamp);}
  const group=await command('Create user group','/v1/user-groups');resources.testGroup=group.id;h.save();await page.getByRole('link',{name:'View user group',exact:true}).click();return 'Tenant group '+group.id+' created through UI';
 });
 await test('TA-ORG-ROLE-CREATE','Roles and permissions','Create custom tenant role; choose company.read from the permission catalogue; save and view','Role contains exactly the selected permitted permission',async()=>{
  await ready('/roles/new');await page.getByRole('button',{name:'Save role',exact:true}).click();assert(await page.getByRole('textbox',{name:'Role key',exact:true}).isVisible());
  await page.getByRole('textbox',{name:'Role key',exact:true}).fill('qa_reader_'+stamp);await page.getByRole('textbox',{name:'Role name',exact:true}).fill('QA Company Reader '+stamp);await page.getByRole('combobox',{name:'Scope hint',exact:true}).selectOption('company');
  const permissions=page.getByRole('combobox',{name:'Permissions',exact:true});await permissions.fill('company.read');await page.getByRole('option').filter({hasText:'company.read'}).first().click();await page.keyboard.press('Escape');
  const receipt=await command('Save role','/v1/roles'),role=receipt.role || receipt;resources.testRole=role.id;h.save();assert.deepEqual(role.permissions,['company.read']);await page.getByRole('link',{name:'View saved role',exact:true}).click();return 'Custom read role '+role.id+' saved with exactly company.read';
 });
 await test('TA-ORG-USER-INVITE','Users','Validate empty invitation; invite a synthetic backup person through user UI','Pending invitation saved without granting roles/company access',async()=>{
  await ready('/users/new');await page.getByRole('button',{name:'Invite user',exact:true}).click();await page.getByRole('textbox',{name:'Email',exact:true}).fill('qa-backup-'+stamp+'@example.invalid');await page.getByRole('textbox',{name:'First name',exact:true}).fill('QA');await page.getByRole('textbox',{name:'Last name',exact:true}).fill('Backup');await page.getByRole('textbox',{name:'Display name',exact:true}).fill('QA Backup '+stamp);
  const user=await command('Invite user','/v1/users');resources.backupUser=user.id;h.save();return 'Synthetic user invitation '+user.id+' saved; external mailbox delivery is not claimed';
 });
 await test('TA-BOUNDARY-EXISTING-COMPANY','Tenant isolation','Request a known existing company belonging to another tenant through authenticated company proxy','Company data refused with 403 or 404',async()=>{
  const response=await call('company','identity','/v1/companies/01a17d0d-a959-72bc-9026-e162ad43e249');assert([403,404].includes(response.status),'Unexpected status '+response.status);return 'Existing wrong-tenant company lookup refused with '+response.status;
 },'LIVE_API_SUPPORT');
 await test('TA-BOUNDARY-RANDOM-COMPANY-CONTEXT','Company isolation','Attempt to select a random inaccessible company through context API','Selection denied; active company preserved',async()=>{
  const response=await page.evaluate(async()=>{const r=await fetch('/api/company-context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company:crypto.randomUUID()})});return r.status;});assert([403,404,422].includes(response));return 'Invalid/inaccessible company selection refused with '+response;
 },'LIVE_API_SUPPORT');
 await test('TA-AUDIT-COMPANY-WRITES','Audit history','Open audit UI and read tenant audit events for a newly created QA company','At least one delivered audited change exists for the new company',async()=>{
  const company=resources.companies[0];await h.switchCompany(company);await ready('/audit');
  const response=await page.request.get(h.origin+'/api/audit/v1/audit-events?company_id='+company.id+'&limit=50');assert.equal(response.status(),200);const data=await response.json();assert(data.items.length>0,'No delivered tenant audit events for new company '+company.id);await h.capture('new-company-audit-events');return 'Audit UI loaded; '+data.items.length+' delivered company-scoped audit events verified';
 },'LIVE_UI_WITH_API_READBACK');
 await test('TA-AUTH-PASSWORD-LINK','Authentication','Choose Change password from the user menu; inspect provider handoff without changing password','User reaches provider-owned password-change flow',async()=>{
  await ready('/');await page.getByRole('button',{name:'QA Tenant Administrator',exact:true}).click();await page.getByRole('menuitem',{name:'Change password',exact:true}).click();await page.waitForTimeout(1200);assert(new URL(page.url()).origin===h.auth || new URL(page.url()).pathname.includes('flow'));await h.capture('password-change-handoff');return 'User menu opens provider-owned password change; current password retained';
 });
};
