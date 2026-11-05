module.exports=async function(h){
 const {page,resources,test,ready,assert,call}=h;
 for(const company of resources.companies.filter(c=>!process.env.QA_COMPANY_KEY||c.key===process.env.QA_COMPANY_KEY)){
  resources.currentCompany=company.id;await h.switchCompany(company);
  for(const record of resources.records.filter(r=>r.company===company.id&&['brands','manufacturers','item-groups'].includes(r.resource)&&(!process.env.QA_RESOURCE||r.resource===process.env.QA_RESOURCE)&&(!process.env.QA_RECORD_IDS||process.env.QA_RECORD_IDS.split(',').includes(r.id))))await test('TA-MASTER-'+company.key+'-'+record.resource+'-EDIT-LIFECYCLE','Catalog masters','Open the UI-created record; choose Edit from Record actions; save name; deactivate/reactivate through available record actions','Detail, changed name and both lifecycle operations persist; record left active',async()=>{
   const base='/v1/companies/'+company.id+'/'+record.resource+'/'+record.id;
   async function transition(action){await ready('/masters/'+record.resource+'/'+record.id);const prior=await call('product-fields','catalog',base);assert.equal(prior.status,200);if(prior.body.is_active===(action==='activate'))return;const label=action==='deactivate'?'Deactivate':'Activate',button=page.getByRole('main').getByRole('button',{name:new RegExp('^'+label+' ')}).first();const inline=await button.waitFor({state:'visible',timeout:4000}).then(()=>true,()=>false);if(inline)await button.click();else{await page.getByRole('button',{name:'Record actions',exact:true}).click();await page.getByRole('menuitem',{name:new RegExp('^'+label)}).first().click();}const pending=page.waitForResponse(r=>r.url().endsWith('/api/product-fields')&&r.request().postDataJSON()?.path===base+'/'+action&&r.request().postDataJSON()?.method==='POST');pending.catch(()=>{});await page.getByRole('dialog').getByRole('button',{name:new RegExp('^(?:'+label+'|Confirm change)')}).first().click();const response=await pending,data=await response.json();assert(response.ok(),response.status()+': '+data.error?.message);}
   await transition('activate');await ready('/masters/'+record.resource+'/'+record.id);
   const edit=page.getByRole('main').getByRole('link',{name:/^Edit /}).first();
   if(await edit.count())await edit.click();else{await page.getByRole('button',{name:'Record actions',exact:true}).click();await page.getByRole('menuitem',{name:/^Edit /}).first().click();}
   await page.waitForLoadState('networkidle',{timeout:10000}).catch(()=>{});await page.waitForTimeout(600);
   const nameInput=page.getByRole('textbox',{name:'Name',exact:true});const currentName=await nameInput.inputValue();const nextName=currentName.replace(/(?: reviewed| checked-[a-z0-9]+)+$/i,'')+' checked-'+Date.now().toString(36).slice(-4);await nameInput.fill(nextName);assert.equal(await nameInput.inputValue(),nextName);
   const saved=page.waitForResponse(r=>r.url().endsWith('/api/product-fields')&&r.request().postDataJSON()?.path===base&&r.request().postDataJSON()?.method==='PATCH');saved.catch(()=>{});await page.getByRole('button',{name:/^Save/}).first().click();assert((await saved).ok());await ready('/masters/'+record.resource+'/'+record.id);
   for(const action of ['deactivate','activate'])await transition(action);
   const actual=await call('product-fields','catalog',base);assert.equal(actual.status,200);assert.equal(actual.body.is_active,true);assert.equal(actual.body.name,nextName);record.name=nextName;h.save();return 'UI-created '+record.resource+' '+record.id+' edited, deactivated/reactivated and read back active';
  });
 }
};
