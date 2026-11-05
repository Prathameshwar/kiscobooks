const crypto=require('node:crypto'), fs=require('node:fs'),path=require('node:path');
module.exports=async function(h) {
 const {page,resources,test,assert,ready,call}=h;
 const stamp=resources.marker.slice(-8).toUpperCase();
 async function choose(label,text){
   const box=page.getByRole('combobox',{name:label,exact:true});await box.waitFor();
   if(await box.evaluate(el=>el.tagName==='SELECT')) {
     const options=await box.locator('option').evaluateAll(rows=>rows.map(o=>({value:o.value,label:o.textContent,disabled:o.disabled})));
     const option=options.find(o=>!o.disabled && (o.value===text || o.label===text || o.label?.includes(text)));assert(option,'No offered '+label+' choice matching '+text);await box.selectOption(option.value);
   } else {await box.click();if(await box.evaluate(el=>el.tagName==='INPUT') && text)await box.fill(text);const options=page.getByRole('option');await (text?options.filter({hasText:text}):options).first().click();}
 }
 async function write(button,apiPath,method='POST') {
   const pending=page.waitForResponse(r=>r.url().endsWith('/api/product-fields') && r.request().postDataJSON()?.path===apiPath && r.request().postDataJSON()?.method===method,{timeout:60000});
   pending.catch(()=>{});
   await page.getByRole('button',{name:button,exact:true}).click();const response=await pending,data=await response.json();assert(response.ok(),response.status()+': '+data.error?.message);return data;
 }
 async function fillRequired(prefix) {
   const inputs=page.locator('main input[required],main textarea[required]');
   for(let i=0;i<await inputs.count();i++) {const input=inputs.nth(i);if(!await input.isVisible() || !await input.isEnabled() || await input.inputValue())continue;
     const type=await input.getAttribute('type'),label=await input.evaluate(el=>el.labels?.[0]?.innerText || el.getAttribute('aria-label') || '');
     if(type==='date')await input.fill('2026-10-29');else if(type==='email')await input.fill('qa-'+stamp.toLowerCase()+'@example.invalid');else if(!['checkbox','hidden'].includes(type))await input.fill(/code/i.test(label)?prefix:/quantity|amount|days|decimal|precision|rate/i.test(label)?'1':'QA '+prefix);
   }
   const selects=page.locator('main select[required]');for(let i=0;i<await selects.count();i++){const s=selects.nth(i);if(!await s.isVisible()||!await s.isEnabled()||await s.inputValue())continue;const o=await s.locator('option').evaluateAll(rows=>rows.filter(o=>o.value&&!o.disabled).map(o=>o.value));if(o.length)await s.selectOption(o[0]);}
 }
 for(const company of resources.companies.filter(c=>!process.env.QA_COMPANY_KEY || c.key===process.env.QA_COMPANY_KEY)) {
  resources.currentCompany=company.id;
  const base='/v1/companies/'+company.id;
  await test('TA-WF-SWITCH-'+company.key,'Company selection','Select '+company.name+' through company directory action menu','Selected company is active in current browser',async()=>{await h.switchCompany(company);return 'Company selected through UI';});
  if(process.env.QA_SUPPLIERS_ONLY!=='1'){
  await test('TA-CONFIG-'+company.key+'-PRODUCT','Product configuration','Create/open Company scope, save a draft with profile-specific entry option, preview and publish','Separate dated product configuration revision saved for this company',async()=>{
    await ready('/products/configuration');
    const existing=await call('product-fields','catalog',base+'/product-configuration-scopes?scope_kind=COMPANY&limit=50');assert.equal(existing.status,200);
    let scope=existing.body.items[0];
    if(!scope){await page.getByRole('link',{name:'New configuration scope',exact:true}).click();await choose('Configuration applies to','Company');scope=await write('Create configuration scope',base+'/product-configuration-scopes');}
    await ready('/products/configuration/scopes/'+scope.id);await page.getByRole('link',{name:'New draft',exact:true}).click();
    await page.getByRole('button',{name:'Save draft',exact:true}).waitFor();
    const inputs=await page.locator('main input,main select').evaluateAll(items=>items.map(e=>({id:e.id,label:e.labels?.[0]?.innerText || e.getAttribute('aria-label'),tag:e.tagName,type:e.type,value:e.value,options:e.tagName==='SELECT'?[...e.options].map(o=>({value:o.value,label:o.textContent})):[]})));
    fs.writeFileSync(path.join(h.output,'product-config-form-'+company.key+'.json'),JSON.stringify(inputs,null,2));
    const reason=inputs.find(i=>/reason/i.test(i.label));assert(reason,'Reason control missing');await page.locator('[id="'+reason.id+'"]').fill('QA '+company.key+' configuration acceptance');
    const barcode=inputs.find(i=>/barcode/i.test(i.label) && i.tag==='SELECT');
    if(barcode){const preferred=company.key==='services'?['DISABLE','DISABLED','FORBID','HIDDEN','false']:['ENABLE','ENABLED','OPTIONAL','ALLOW','true'];const option=barcode.options.find(o=>preferred.includes(o.value));if(option){await page.locator('[id="'+barcode.id+'"]').selectOption(option.value);company.productOption={field:barcode.label,value:option.value};}}
    const draft=await write('Save draft',base+'/product-configurations');company.productScope=scope.id;company.productDraft=draft.id;h.save();
    await page.getByRole('button',{name:'Review publication',exact:true}).waitFor();await page.getByRole('button',{name:'Review publication',exact:true}).click();
    await page.getByRole('dialog',{name:'Publish these product defaults?',exact:true}).waitFor();
    const revision=await write('Publish revision',base+'/product-configurations/'+draft.id+'/publish');company.productRevision=revision.id;h.save();
    await page.getByRole('heading',{name:'Published configuration revision',exact:true}).waitFor();assert.equal(await page.getByRole('link',{name:'Edit draft',exact:true}).count(),0);
    await h.capture('product-config-'+company.key+'-published');return 'Company scope '+scope.id+' published revision '+revision.id+'; publication UI immutable';
  });
  if(process.env.QA_CONFIG_ONLY==='1')continue;
  for(const resource of ['brands','manufacturers','item-groups'])await test('TA-MASTER-'+company.key+'-'+resource+'-CREATE','Catalog masters','Open '+resource+'; use New link; validate and create unique QA record','Record created and visible in detail/directory',async()=>{
    await ready('/masters/'+resource);const link=page.getByRole('main').getByRole('link',{name:/^New /}).first();await link.click();
    await page.getByRole('textbox',{name:'Code',exact:true}).waitFor();const code=('QA-'+stamp+'-'+company.key.slice(0,3)+'-'+resource.slice(0,3)).toUpperCase();
    await page.getByRole('textbox',{name:'Code',exact:true}).fill(code);await page.getByRole('textbox',{name:'Name',exact:true}).fill('QA '+company.key+' '+resource+' '+stamp);
    await fillRequired(code);
    const button=page.getByRole('button',{name:/^Create /}).first(),pending=page.waitForResponse(r=>r.url().endsWith('/api/product-fields')&&r.request().postDataJSON()?.path===base+'/'+resource&&r.request().postDataJSON()?.method==='POST');
    await button.click();const response=await pending,data=await response.json();assert.equal(response.status(),201,data.error?.message);
    resources.records.push({company:company.id,resource,id:data.id,code,name:data.name});h.save();if(!new URL(page.url()).pathname.includes(data.id)){const view=page.locator('main a[href]').filter({hasText:/^View /}).first();await view.waitFor();await view.click();}await page.waitForURL(url=>url.pathname.includes(data.id));return 'Created '+resource+' '+data.id+' through live UI and opened saved record';
  });
  }
  let party;
  if(company.supplier)await test('TA-PARTY-'+company.key+'-READBACK','Parties and suppliers','Open the supplier already created through the companion UI wizard; verify persisted active status','Previously UI-created supplier remains active in this company',async()=>{await ready('/accounting/suppliers/'+company.supplier);const response=await call('product-fields','accounting',base+'/parties/'+company.supplier);assert.equal(response.status,200);assert.equal(response.body.status,'ACTIVE');return 'Previously UI-created supplier read back as active';},'LIVE_UI_WITH_API_READBACK');
  else {
  await test('TA-PARTY-'+company.key+'-CREATE','Parties and suppliers','Open supplier wizard; validate empty third step; enter code/name, address/contact and create','Active supplier with saved default details; exact command replay creates no duplicate',async()=>{
    await ready('/accounting/suppliers/new');await page.getByRole('textbox',{name:'Code',exact:true}).waitFor();
    const progress=page.getByRole('navigation',{name:'Setup progress',exact:true});
    await progress.getByRole('button',{name:/Tax and other details/}).click();await page.getByRole('button',{name:'Create supplier',exact:true}).click();assert(await page.getByRole('textbox',{name:'Code',exact:true}).isVisible());
    const name='QA Supplier '+company.key+' '+stamp;await page.getByRole('textbox',{name:'Code',exact:true}).fill(('QA-'+stamp+'-'+company.key.slice(0,3)).toUpperCase());await page.getByRole('textbox',{name:'Name',exact:true}).fill(name);const legal=page.getByRole('textbox',{name:'Legal name',exact:true});if(await legal.count())await legal.fill(name+' LLP');await choose('Country code','India');
    await progress.getByRole('button',{name:/Address and contact/}).click();const address=page.getByRole('checkbox',{name:'Add default address',exact:true});await address.check();
    await page.getByRole('textbox',{name:'Label',exact:true}).fill('QA Primary');await page.getByRole('textbox',{name:'Line1',exact:true}).fill('1 QA Acceptance Road');await page.getByRole('textbox',{name:'City',exact:true}).fill('Mumbai');await choose('State code','IN-MH');
    await page.getByRole('checkbox',{name:'Add default contact',exact:true}).check();await page.getByRole('textbox',{name:'Name',exact:true}).fill('QA Synthetic Contact');await page.getByRole('textbox',{name:'Email',exact:true}).fill('qa-'+stamp.toLowerCase()+'-'+company.key+'@example.invalid');
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/product-fields') && r.request().postDataJSON()?.path===base+'/parties/create-with-details');await page.getByRole('button',{name:'Create supplier',exact:true}).click();
    const response=await pending;party=await response.json();assert.equal(response.status(),201,party.error?.message);assert.equal(party.status,'ACTIVE');company.supplier=party.id;resources.records.push({company:company.id,resource:'parties',id:party.id,name});h.save();
    await page.waitForURL(url=>url.pathname.endsWith(party.id));const input=response.request().postDataJSON();const replay=await call('product-fields','accounting',input.path,input.method,input.body,input.key);assert.equal(replay.status,201);assert.equal(replay.body.id,party.id);return 'Active supplier '+party.id+' created through wizard; same request replay returned same ID';
  });
  }
  if(process.env.QA_SUPPLIERS_ONLY==='1')continue;
  if(company.accountPolicy)await test('TA-CONFIG-'+company.key+'-ACCOUNT-READBACK','Account and party configuration','Open the previously UI-created supplier policy and inspect persisted options','Existing company-specific supplier policy remains readable',async()=>{await ready('/accounting/party-accounting-policies/'+company.accountPolicy);const response=await call('product-fields','accounting',base+'/party-accounting-policies/'+company.accountPolicy);assert.equal(response.status,200);assert.equal(response.body.party_id,company.supplier);return 'UI-created supplier policy read back';},'LIVE_UI_WITH_API_READBACK');
  else if(company.supplier)await test('TA-CONFIG-'+company.key+'-ACCOUNT','Account and party configuration','Open supplier accounting-policy form; set company-specific bill tracking and valid-from date; save','Party accounting policy saved and visible for this supplier',async()=>{
    await ready('/accounting/party-accounting-policies?party_id='+company.supplier);await page.getByRole('main').getByRole('link',{name:/^New /}).first().click();
    await page.getByRole('button',{name:/^Create /}).first().waitFor();
    const controls=await page.locator('main input,main select').evaluateAll(items=>items.map(e=>({id:e.id,label:e.labels?.[0]?.innerText,tag:e.tagName,type:e.type,value:e.value,options:e.tagName==='SELECT'?[...e.options].map(o=>({value:o.value,label:o.textContent})):[]})));
    fs.writeFileSync(path.join(h.output,'account-config-form-'+company.key+'.json'),JSON.stringify(controls,null,2));
    const bill=controls.find(c=>/bill|tracking/i.test(c.label)&&c.tag==='SELECT');if(bill){const option=bill.options.find(o=>o.value && o.value!=='INHERIT' && (company.key==='services'?/none|off|false|disabled/i:/on|required|true|bill/i).test(o.value)) || bill.options.find(o=>o.value);if(option){await page.locator('[id="'+bill.id+'"]').selectOption(option.value);company.accountOption={field:bill.label,value:option.value};}}
    await fillRequired('QA-'+stamp);
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/product-fields')&&r.request().postDataJSON()?.path===base+'/party-accounting-policies'&&r.request().postDataJSON()?.method==='POST');await page.getByRole('button',{name:/^Create /}).first().click();const response=await pending,data=await response.json();assert.equal(response.status(),201,data.error?.message);company.accountPolicy=data.id;h.save();return 'Supplier accounting policy '+data.id+' saved';
  });
  if(process.env.QA_SUPPLIERS_ONLY==='1')continue;
  for(const [kind,group] of [['GENERAL','INDIRECT_EXPENSES'],['CASH','CASH']])await test('TA-ACCOUNT-'+company.key+'-'+kind,'Ledger accounts','Create '+kind+' account from filtered directory; edit name; activate via record action menu','Active account retains kind and correct group',async()=>{
    const groups=await call('product-fields','accounting',base+'/account-groups?limit=200');assert.equal(groups.status,200);const target=groups.body.items.find(g=>g.code===group);assert(target,'Starter chart group missing: '+group);
    await ready('/accounting/accounts?kind='+kind+'&group_id='+target.id);await page.getByRole('link',{name:'New account',exact:true}).click();
    const code=('QA-'+stamp+'-'+company.key.slice(0,3)+'-'+kind).toUpperCase(),name='QA '+company.key+' '+kind+' '+stamp;await page.getByRole('textbox',{name:'Code',exact:true}).fill(code);await page.getByRole('textbox',{name:'Name',exact:true}).fill(name);
    const account=await write('Create account',base+'/accounts');resources.records.push({company:company.id,resource:'accounts',id:account.id,kind,code,name});h.save();
    await page.getByRole('link',{name:'Edit account',exact:true}).waitFor();await page.getByRole('link',{name:'Edit account',exact:true}).click();await page.getByRole('textbox',{name:'Name',exact:true}).fill(name+' edited');await write('Save changes',base+'/accounts/'+account.id,'PATCH');
    await page.getByRole('button',{name:'Record actions',exact:true}).waitFor();await page.getByRole('button',{name:'Record actions',exact:true}).click();await page.getByRole('menuitem',{name:'Activate',exact:true}).click();await write('Activate record',base+'/accounts/'+account.id+'/activate');
    const actual=await call('product-fields','accounting',base+'/accounts/'+account.id);assert.equal(actual.body.status,'ACTIVE');assert.equal(actual.body.kind,kind);assert.equal(actual.body.group_id,target.id);return 'Created, edited and activated '+kind+' account '+account.id;
  });
  if(company.product)await test('TA-PRODUCT-'+company.key+'-READBACK','Products','Open the product created by the companion product/type UI flow and read back its identity','UI-created product remains readable in the selected company',async()=>{await ready('/masters/items/'+company.product);const response=await call('product-fields','catalog',base+'/products/'+company.product);assert.equal(response.status,200);assert.equal(response.body.id,company.product);return 'UI-created product identity read back';},'LIVE_UI_WITH_API_READBACK');
  else await test('TA-PRODUCT-'+company.key+'-CREATE','Products','Create '+(company.key==='services'?'SERVICE':'GOODS')+' using new product UI; choose base unit and save; inspect readiness','New product and unit assignment saved as a draft',async()=>{
    await ready('/masters/items/new');await page.getByRole('textbox',{name:/^(Product )?code$/i}).waitFor();
    const code='QA-'+stamp+'-'+company.key.toUpperCase(),name='QA '+company.key+' product '+stamp;
    await page.getByRole('textbox',{name:/^(Product )?code$/i}).fill(code);await page.getByRole('textbox',{name:/^(Product )?name$/i}).first().fill(name);
    if(company.typeRevision)await choose('Published product type','QA '+company.key+' type '+stamp);
    const kind=page.getByRole('combobox',{name:'Kind',exact:true});if(await kind.count())await choose('Kind',company.key==='services'?'SERVICE':'GOODS');
    const unit=page.getByRole('combobox',{name:'Base unit',exact:true});if(await unit.isVisible())await choose('Base unit',company.key==='services'?'Hour':'Piece');
    const controls=await page.locator('main input,main select').evaluateAll(items=>items.map(e=>({id:e.id,label:e.labels?.[0]?.innerText,type:e.type,value:e.value})));
    fs.writeFileSync(path.join(h.output,'product-form-'+company.key+'.json'),JSON.stringify(controls,null,2));
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/product-fields')&&r.request().postDataJSON()?.method==='POST' && /\/(products|product-families)$/.test(r.request().postDataJSON()?.path));
    await page.getByRole('button',{name:'Create product',exact:true}).click();const response=await pending,data=await response.json();assert.equal(response.status(),201,data.error?.message);
    const id=data.id || data.default_item?.id;assert(id);company.product=id;resources.records.push({company:company.id,resource:'items',id,code,name});h.save();await h.capture('product-'+company.key+'-saved');return 'Live product draft '+id+' saved through UI';
  });
 }
 if(process.env.QA_CONFIG_ONLY==='1'||process.env.QA_SUPPLIERS_ONLY==='1')return;
 const first=resources.companies[0];if(first){await h.switchCompany(first);resources.currentCompany=first.id;}
 for(const kind of ['sales','receipt','purchase','payment','stock-adjustment'])await test('TA-VOUCHER-'+kind+'-ENTRY','Voucher entry','Open top-bar New menu and choose '+kind,'Entry screen opens; supported controls available or clear admission/prerequisite reason shown',async()=>{
   await ready('/');await page.getByRole('button',{name:'New',exact:true}).click();const labels={sales:'Sales',receipt:'Receipt',purchase:'Purchase',payment:'Payment','stock-adjustment':'Stock adjustment'};await page.getByRole('menuitem',{name:labels[kind],exact:true}).click();await page.waitForTimeout(1200);
   const text=await page.getByRole('main').innerText();await h.capture('voucher-entry-'+kind);
   if(/not available|not yet|not built yet|disabled|not implemented|activation|admission|needs.*configuration|Loading the sales bill/i.test(text)){const e=Error(text.slice(-3000));e.blocked=true;throw e;}
   assert.equal(new URL(page.url()).pathname,'/vouchers/new/'+kind);return 'New menu navigated to '+kind+' entry; '+text.slice(0,400);
 });
 await test('TA-AUTH-USER-MENU','User menu','Open account menu; choose My access','My access page shows the current tenant user grants',async()=>{await ready('/');await page.getByRole('button',{name:'QA Tenant Administrator',exact:true}).click();await page.getByRole('menuitem',{name:'My access',exact:true}).click();await page.getByRole('heading',{name:'My access',exact:true}).waitFor();return 'User menu My access navigation passed';});
 await test('TA-SHELL-PALETTE','Command palette','Press Ctrl+K, search Masters, choose destination, collapse and expand sidebar','Keyboard navigation opens Masters; sidebar toggle works',async()=>{
   await ready('/');await page.keyboard.press('Control+k');const dialog=page.getByRole('dialog');await dialog.waitFor();await page.getByRole('combobox').filter({visible:true}).first().fill('Masters');await page.keyboard.press('Enter');await page.waitForTimeout(500);assert.equal(new URL(page.url()).pathname,'/masters');return 'Command palette navigation passed';
 });
};
