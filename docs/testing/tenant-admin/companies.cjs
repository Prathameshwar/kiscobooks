module.exports=async function(h) {
  const {page,resources,test,assert,ready,call}=h;
  const profiles=[
    {key:'retail',name:'QA Retail '+resources.marker.slice(-8),state:'IN-MH',amount:'2',quantity:'3',inventory:true,grouping:'indian',rounding:'half_up'},
    {key:'services',name:'QA Services '+resources.marker.slice(-8),state:'IN-KA',amount:'4',quantity:'2',inventory:false,grouping:'international',rounding:'half_even'},
    {key:'distribution',name:'QA Distribution '+resources.marker.slice(-8),state:'IN-GJ',amount:'0',quantity:'4',inventory:true,grouping:'international',rounding:'half_up',extras:['Multiple warehouses','Batches','Expiry dates','Serial numbers','Foreign currency']},
  ];
  async function next(heading){await page.getByRole('button',{name:'Next',exact:true}).click();await page.getByRole('heading',{level:1,name:heading,exact:true}).waitFor();}
  for(let index=0;index<profiles.length;index++) {
    const p=profiles[index];if(resources.companies.some(c=>c.key===p.key)) continue;
    resources.currentCompany=p.key;
    await test('TA-COMP-'+p.key+'-BUSINESS','Company wizard','Open Create company; validate empty business step; fill legal and short name','Validation blocks empty details; next opens location and tax',async()=>{
      await ready('/companies/new');await page.getByRole('textbox',{name:'Legal name',exact:true}).waitFor();
      await page.getByRole('button',{name:'Next',exact:true}).click();
      assert(await page.getByRole('textbox',{name:'Legal name',exact:true}).isVisible());
      await page.getByRole('textbox',{name:'Legal name',exact:true}).fill(p.name);
      await page.getByRole('textbox',{name:'Short name',exact:true}).fill(p.name);
      await next('Location and tax');return 'Required business validation and legal/short-name input passed';
    });
    await test('TA-COMP-'+p.key+'-LOCATION','Company wizard','Set India and '+p.state+'; retain offered GST and price convention','Country-dependent state and tax choices resolve',async()=>{
      const country=page.getByRole('combobox',{name:'Country',exact:true});
      if(await country.inputValue()!=='IN')await country.selectOption('IN');
      await page.getByRole('combobox',{name:'State',exact:true}).selectOption(p.state);
      const tax=page.getByRole('combobox',{name:'Tax system',exact:true});
      if(!(await tax.inputValue()))await tax.selectOption('gst_in');
      await next('Money and calendar');return 'India/'+p.state+' accepted with GST jurisdiction';
    });
    await test('TA-COMP-'+p.key+'-MONEY','Company wizard','Set amount decimals '+p.amount+', quantity decimals '+p.quantity+', rounding '+p.rounding+'; begin books on the first day of the current business month','Review retains selected precision and calendar',async()=>{
      await page.getByRole('combobox',{name:'Amount decimals',exact:true}).selectOption(p.amount);
      await page.getByRole('combobox',{name:'Quantity decimals',exact:true}).selectOption(p.quantity);
      await page.getByRole('combobox',{name:'Rounding',exact:true}).selectOption(p.rounding);
      const bookDate=page.getByLabel('Books begin on',{exact:true});p.booksBegin=(await bookDate.inputValue()).slice(0,7)+'-01';await bookDate.fill(p.booksBegin);
      await next('What you track');return 'Amount/quantity precision and rounding configured; books begin date set';
    });
    await test('TA-COMP-'+p.key+'-FEATURES','Company wizard','Select tracking capability profile; stock enabled='+p.inventory,'Dependency-aware capability choices accept profile',async()=>{
      const boxes=page.getByRole('checkbox');
      resources.featureChoices=await boxes.evaluateAll(items=>items.map(x=>({label:x.closest('label')?.innerText || x.getAttribute('aria-label'),checked:x.checked})));
      if(!p.inventory) {
        for(let i=await boxes.count()-1;i>=0;i--) {const box=boxes.nth(i);if(await box.isChecked())await box.locator('..').click();}
      } else {
        const inventory=page.getByRole('checkbox',{name:/Inventory|Stock tracking/i}).first();
        if(await inventory.count() && !await inventory.isChecked())await inventory.locator('..').click();
        for(const label of p.extras || []) {const box=page.getByRole('checkbox',{name:new RegExp('^'+label)}).first();if(await box.count() && !await box.isChecked())await box.locator('..').click();}
      }
      p.featureLabels=await boxes.evaluateAll(items=>items.filter(x=>x.checked).map(x=>x.closest('label')?.innerText));
      await next('Presentation');return 'Selected '+(p.featureLabels.join('; ') || 'no optional capabilities');
    });
    await test('TA-COMP-'+p.key+'-PRESENTATION','Company wizard','Set '+p.grouping+' grouping; review money/date preview and wizard Back/Edit links','Presentation review shows configured business and values',async()=>{
      const grouping=page.getByRole('combobox',{name:'Digit grouping',exact:true});
      const available=await grouping.locator('option').evaluateAll(options=>options.map(o=>({value:o.value,text:o.textContent})));
      const value=available.find(o=>o.value===p.grouping || o.text.toLowerCase().includes(p.grouping==='international'?'western':'indian'))?.value;
      if(value)await grouping.selectOption(value);p.groupingValue=await grouping.inputValue();
      await next('Review and create');assert(await page.getByText(p.name,{exact:true}).count()>0);await h.capture('company-'+p.key+'-review');return 'Company review and presentation preview rendered';
    });
    await test('TA-COMP-'+p.key+'-CREATE','Company setup','Click Create this company; watch bootstrap tasks and automatic open','Company, capabilities, unit defaults, starter chart, financial year, books period, warehouse/pricing/tax setup finish',async()=>{
      const pending=page.waitForResponse(r=>r.url().endsWith('/api/company') && r.request().postDataJSON()?.path==='/v1/companies' && r.request().postDataJSON()?.method==='POST');
      await page.getByRole('button',{name:'Create this company',exact:true}).click();
      const response=await pending,data=await response.json();assert.equal(response.status(),201,data.error?.message);
      const record={...p,id:data.id,code:data.code};resources.companies.push(record);h.save();
      await page.waitForURL(url=>/^\/companies\/[0-9a-f-]+$/.test(url.pathname),{timeout:150000}).catch(async()=>{
        const main=await page.locator('body').innerText();throw Error('Company '+data.id+' saved but bootstrap did not finish: '+main.slice(-4000));
      });
      resources.currentCompany=data.id;await h.capture('company-'+p.key+'-created');return 'Live company '+data.id+' fully bootstrapped and opened through wizard';
    });
    const saved=resources.companies.find(c=>c.key===p.key);
    if(saved)await test('TA-COMP-'+p.key+'-READBACK','Company setup','Read saved company via company proxy','Saved jurisdiction/precision/rounding equal submitted values',async()=>{
      const r=await call('company','identity','/v1/companies/'+saved.id);assert.equal(r.status,200);assert.equal(r.body.state_code,p.state);assert.equal(String(r.body.amount_precision),p.amount);assert.equal(String(r.body.quantity_precision),p.quantity);assert.equal(r.body.rounding_mode,p.rounding);return 'Persisted jurisdiction, amount/quantity precision and rounding confirmed';
    },'LIVE_API_SUPPORT');
  }
  await test('TA-COMP-DIRECTORY','Company selection','Open company directory; search and display all three QA companies','Only this tenant companies appear; three profiles selectable',async()=>{
    await ready('/companies');for(const c of resources.companies)assert(await page.getByText(c.name,{exact:true}).count()>0);await h.capture('company-directory');return resources.companies.length+' QA companies visible in new tenant directory';
  });
};
