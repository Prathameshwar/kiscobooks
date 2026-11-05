/* Catalogue controls/parameter validation; excludes unsupported populated-owner claims. */
const {start}=require('./harness.cjs');
(async()=>{
  const h=await start(process.env.QA_REPORT_PHASE||'pending-17-controls'),{page,assert}=h;
  try{
    const owner=h.privateLoad();await h.login(page,owner.username,owner.password);
    const accounting=await require('./identity_reader.cjs')(h,'accounting');
    for(const company of h.resources.companies){
      if(process.env.QA_COMPANY_KEY&&company.key!==process.env.QA_COMPANY_KEY)continue;
      await h.switchCompany(company);const base='/v2/companies/'+company.id;
      await h.ready('/reports/workspace');const load=page.getByRole('button',{name:'Load report workspace',exact:true});
      await page.waitForFunction(el=>Object.keys(el).some(key=>key.startsWith('__reactProps$')&&typeof el[key]?.onClick==='function'),await load.elementHandle(),{timeout:90000});
      await load.click();const catalog=await h.call('product-fields','reports',base+'/report-definitions');assert.equal(catalog.status,200);assert.equal(catalog.body.items.length,38);
      const setup=await accounting('/v1/companies/'+company.id+'/financial-setup');assert.equal(setup.status,200);
      for(const entry of catalog.body.items){
        const {code}=entry.definition,properties=entry.parameter_schema.properties??{},required=entry.parameter_schema.required??[];
        await h.test('P17-CONTROLS-'+company.key+'-'+code,'Native report controls','Select '+code+'; inspect each advertised parameter, toggle boolean/enum controls and restore','Every native parameter renders its applicable labelled control and is operable',async()=>{
          await page.getByRole('combobox',{name:'Report',exact:true}).selectOption(code);await page.getByRole('heading',{name:'Report settings',exact:true}).waitFor();
          for(const [key,raw] of Object.entries(properties)){
            const field=raw.anyOf?.find(branch=>branch.type!=='null')??raw,label=raw.title??key.replaceAll('_',' ');
            if(key==='currency'&&properties.basis&&(await page.getByLabel(properties.basis.title??'basis',{exact:true}).inputValue())!=='TRANSACTION')continue;
            if(field.type==='boolean'){
              const control=page.getByRole('checkbox',{name:label,exact:true});assert(await control.isVisible());const original=await control.isChecked();await control.setChecked(!original);assert.equal(await control.isChecked(),!original);await control.setChecked(original);
            }else{
              const control=page.getByLabel(label,{exact:true});assert(await control.isVisible(),'Missing labelled parameter '+key);
              if(['account_id','group_id','party_id','item_id','location_id','lot_id'].includes(key))assert.equal(await control.getAttribute('role'),'combobox');
              else if(field.enum){const original=await control.inputValue();const alternate=field.enum.find(value=>value!==original);if(alternate){await control.selectOption(alternate);assert.equal(await control.inputValue(),alternate);await control.selectOption(original);}}
              else if(field.type==='integer')assert.equal(await control.getAttribute('type'),'number');
              else if(field.format==='date')assert.equal(await control.getAttribute('type'),'date');
              else if(field.type==='array')assert.equal(await control.inputValue(),(raw.default??[]).join(', '));
            }
          }
          return Object.keys(properties).length+' labelled controls checked; rendering/interaction only, not populated calculation acceptance';
        });
        await h.test('P17-VALIDATE-'+company.key+'-'+code,'Native report parameter validation','Validate actual company dates/product/default values against '+code,'Native validation accepts typed parameters; unavailable bank dependencies remain explicit',async()=>{
          if(required.some(key=>['account_id','session_id','statement_balance'].includes(key))){const error=new Error('Bank account/statement/session fixture is required; no artificial bank evidence supplied');error.blocked=true;throw error;}
          const values={};for(const [key,raw] of Object.entries(properties))if(raw.default!==null&&raw.default!==undefined)values[key]=raw.default;
          for(const key of required){if(key==='date_from')values[key]=setup.body.books_begin_date;else if(['date_to','as_of'].includes(key))values[key]=new Date().toISOString().slice(0,10);else if(key==='item_id')values[key]=company.product;else if(values[key]===undefined){const error=new Error('Required native fixture is unavailable for '+key);error.blocked=true;throw error;}}
          if(code==='STOCK_AGEING')values.buckets=[30,90,180];
          const result=await h.call('product-fields','reports',base+'/report-definitions/'+code+'/validate','POST',{version:entry.definition.version,parameters:values});assert.equal(result.status,200,result.body.error?.message);
          if(code==='STOCK_AGEING')assert.deepEqual(result.body.parameters.buckets,[30,90,180]);
          return 'Native parameter validation passed; hash '+result.body.parameter_hash+'; no report run or owner posting implied';
        },'LIVE_UI_AND_NATIVE_PARAMETER_API');
      }
      await h.capture('report-controls-'+company.key);
    }
    if(h.results.some(row=>row.status==='FAIL'))process.exitCode=1;
  }finally{h.save();await h.browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
