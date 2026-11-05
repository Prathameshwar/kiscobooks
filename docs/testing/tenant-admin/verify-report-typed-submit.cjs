/* Real UI submission of typed parameters; read-only report jobs, no financial effects. */
const {start}=require('./harness.cjs');
(async()=>{
  const h=await start(process.env.QA_REPORT_PHASE||'pending-17-typed-submit'),{page,assert}=h;
  try{
    const owner=h.privateLoad();await h.login(page,owner.username,owner.password);
    for(const company of h.resources.companies){
      if(process.env.QA_COMPANY_KEY&&company.key!==process.env.QA_COMPANY_KEY)continue;
      await h.switchCompany(company);const base='/v2/companies/'+company.id;
      let submission;
      const typed=await h.test('P17-TYPED-SUBMIT-'+company.key,'Typed stock report submission','Reject invalid age bucket text; submit whole-number buckets and a boolean through the UI; inspect the native request and response','UI sends integer arrays and booleans; invalid text is refused; a known missing-source refusal is preserved',async()=>{
        await h.ready('/reports/workspace?report=STOCK_AGEING');const load=page.getByRole('button',{name:'Load report workspace',exact:true});
        await page.waitForFunction(el=>Object.keys(el).some(key=>key.startsWith('__reactProps$')&&typeof el[key]?.onClick==='function'),await load.elementHandle(),{timeout:90000});await load.click();
        await page.getByRole('heading',{name:'Report settings',exact:true}).waitFor();
        const catalog=await h.call('product-fields','reports',base+'/report-definitions');assert.equal(catalog.status,200);
        const entry=catalog.body.items.find(row=>row.definition.code==='STOCK_AGEING');assert(entry?.run_enabled);
        const sources=await h.call('product-fields','reports',base+'/report-generations?limit=50');assert.equal(sources.status,200);const generation=sources.body.items.find(row=>row.status==='READY');assert(generation,'A verified READY source is required');
        await page.getByLabel('Source snapshot',{exact:true}).selectOption(generation.id);
        const properties=entry.parameter_schema.properties,label=key=>properties[key].title??key.replaceAll('_',' ');
        await page.getByLabel(label('as_of'),{exact:true}).fill(new Date().toISOString().slice(0,10));
        await page.getByLabel(label('buckets'),{exact:true}).fill('30, invalid, 180');
        await page.getByRole('button',{name:'Create report',exact:true}).click();await page.getByText(/requires a whole number within its supported range/).waitFor();
        await page.getByLabel(label('buckets'),{exact:true}).fill('30, 90, 180');await page.getByRole('checkbox',{name:label('include_inactive'),exact:true}).uncheck();
        const pending=page.waitForResponse(response=>response.request().postDataJSON()?.path===base+'/report-runs'&&response.request().postDataJSON()?.method==='POST');pending.catch(()=>{});
        await page.getByRole('button',{name:'Create report',exact:true}).click();const response=await pending;
        const input=response.request().postDataJSON().body;assert.deepEqual(input.parameters.buckets,[30,90,180]);assert.equal(input.parameters.include_inactive,false);
        submission={status:response.status(),body:await response.json()};
        if(submission.status===409&&submission.body.error?.message==='complete inventory source coverage is unavailable')return 'UI sent native array [30,90,180] and boolean false; invalid text was refused locally. Owner correctly refused missing inventory coverage; job acceptance is a separate prerequisite case.';
        assert.equal(submission.status,202,submission.body.error?.message);
        const saved=submission.body,detail=await h.call('product-fields','reports',base+'/report-runs/'+saved.id);assert.equal(detail.status,200);assert.deepEqual(detail.body.parameters.buckets,[30,90,180]);assert.equal(detail.body.parameters.include_inactive,false);assert.equal(detail.body.generation_id,generation.id);
        await h.capture('typed-report-submit-'+company.key);
        return 'Native job '+saved.id+' accepted array [30,90,180] and boolean false; invalid text was rejected locally. Execution status '+detail.body.status+'; populated stock/report acceptance remains separate';
      },'LIVE_UI_WITH_API_READBACK');
      if(typed.status==='PASS')await h.test('P17-STOCK-SOURCE-'+company.key,'Stock report source readiness','Require native complete inventory source coverage before accepting the stock report job','Native stock report job is accepted only with complete inventory coverage',async()=>{
        if(submission.status===409&&submission.body.error?.message==='complete inventory source coverage is unavailable'){const error=new Error('The retained READY financial source has no complete inventory coverage; stock report job correctly refused with 409. Owner stock-source prerequisites remain open.');error.blocked=true;throw error;}
        assert.equal(submission.status,202);return 'Native inventory report job accepted; populated result verification remains separate';
      },'LIVE_NATIVE_SOURCE_GUARD');
    }
    if(h.results.some(row=>row.status==='FAIL'))process.exitCode=1;
  }finally{h.save();await h.browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
