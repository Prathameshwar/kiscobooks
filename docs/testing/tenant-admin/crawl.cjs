const fs=require('node:fs'),path=require('node:path');
module.exports=async function(h) {
  const {page,resources,test,assert,ready}=h;
  const inventories=[];
  for(const name of fs.readdirSync(h.output).filter(name=>/^surface-inventory-.*\.json$/.test(name)))inventories.push(...JSON.parse(fs.readFileSync(path.join(h.output,name),'utf8')));
  const roots=['/','/companies','/companies/manage','/organisation','/organisation/access','/users','/departments','/roles','/permissions','/assignments','/user-groups','/my-access','/settings','/settings/company','/settings/readiness','/settings/notifications','/masters','/products/configuration','/products/attributes','/products/custom-fields','/accounting','/accounting/opening','/inventory','/inventory/stock','/inventory/stock/opening','/inventory/batches','/inventory/serials','/vouchers','/books','/reports','/reports/workspace','/activity','/audit','/invoice-designer','/documents/routing'];
  const crawlCompanies=process.env.QA_COMPANY_KEY?resources.companies.filter(c=>c.key===process.env.QA_COMPANY_KEY):resources.companies;
  for(const company of crawlCompanies) {
    resources.currentCompany=company.id;
    await test('TA-SWITCH-'+company.key,'Company selection','Open companies and click '+company.name,'Company context changes through UI',async()=>{
      await ready('/companies');
      await h.switchCompany(company);return 'Selected company through directory action menu';
    });
    const queue=[...roots,'/companies/'+company.id,'/companies/'+company.id+'/edit','/companies/'+company.id+'/configuration','/companies/'+company.id+'/years'];
    const prior=inventories.filter(item=>item.company===company.key);
    const seen=new Set(prior.map(item=>item.route));
    const invalidFile=path.join(h.output,'authentication-redirect-inventory.json');
    const mustRender=new Set(fs.existsSync(invalidFile)?JSON.parse(fs.readFileSync(invalidFile,'utf8')).filter(item=>item.company===company.key).map(item=>item.route):[]);
    for(const route of mustRender)if(!seen.has(route))queue.push(route);
    const shape=route=>route.split('?')[0].replace(/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/ig,':id');
    const renderedShapes=new Set(prior.map(item=>shape(item.route))),httpQueue=[];
    for(const item of prior)for(const link of item.links){if(!link.href?.startsWith('/')||link.href.startsWith('//')||link.href.startsWith('/api/')||link.href.startsWith('/platform'))continue;const target=new URL(link.href,h.origin);target.searchParams.delete('returnTo');if(target.pathname.startsWith('/companies/')&&!target.pathname.includes(company.id)&&!['/companies/new','/companies/manage'].includes(target.pathname))continue;if(!seen.has(target.pathname+target.search))queue.push(target.pathname+target.search);}
    while(queue.length) {
      const route=queue.shift();if(seen.has(route))continue;seen.add(route);
      if(process.env.QA_COLLAPSE_RECORD_LINKS==='1'&&!mustRender.has(route)&&renderedShapes.has(shape(route))&&(/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/i.test(route)||route.includes('?'))){httpQueue.push(route);continue;}
      renderedShapes.add(shape(route));
      await test('TA-ROUTE-'+company.key+'-'+route,'Routes and menus','Open '+route+' as new tenant administrator; inspect rendered state and linked controls','Page renders intended authorized state, with no HTTP/browser/server error',async()=>{
        const before=h.errors.length,netBefore=h.network.length;
        const response=await ready(route);
        const actualPath=new URL(page.url()).pathname;
        assert.equal(new URL(page.url()).origin,h.origin,'Authentication redirect: intended application route was not reached');
        assert(!/^\/(?:login|refresh|if\/flow|flow)(?:\/|$)/.test(actualPath),'Authentication redirect: intended application route was not reached');
        const main=page.getByRole('main').first();
        const text=await main.innerText().catch(()=>page.locator('body').innerText());
        const links=await page.locator('a[href]').evaluateAll(items=>items.map(a=>({label:(a.textContent || a.getAttribute('aria-label') || '').trim(),href:a.getAttribute('href')})));
        const controls=await page.locator('main button,main input,main select,main [role="combobox"],main [role="tab"],main [role="menuitem"],main [role="checkbox"]').evaluateAll(items=>items.map(a=>({tag:a.tagName,role:a.getAttribute('role'),type:a.getAttribute('type'),label:a.getAttribute('aria-label') || a.labels?.[0]?.innerText || a.textContent?.trim() || a.getAttribute('placeholder'),disabled:a.disabled || a.getAttribute('aria-disabled')==='true',name:a.getAttribute('name')})));
        const item={company:company.key,route,http:response?.status(),actualPath,text:text.slice(0,14000),links,controls,errors:h.errors.slice(before),network:h.network.slice(netBefore)};inventories.push(item);
        fs.writeFileSync(path.join(h.output,'surface-inventory-'+company.key+'.json'),JSON.stringify(inventories.filter(i=>i.company===company.key),null,2));
        for(const link of links){
          if(!link.href?.startsWith('/') || link.href.startsWith('//') || link.href.startsWith('/api/') || link.href.startsWith('/platform') || link.href.startsWith('/login') || link.href.startsWith('/logout'))continue;
          const target=new URL(link.href,h.origin);target.searchParams.delete('returnTo');
          if(target.pathname.startsWith('/companies/') && !target.pathname.includes(company.id) && !['/companies/new','/companies/manage'].includes(target.pathname))continue;
          if(!seen.has(target.pathname+target.search))queue.push(target.pathname+target.search);
        }
        assert(response && response.status()<400,'HTTP '+response?.status()+' for '+route);
        assert.equal(h.errors.length,before,'Browser error: '+h.errors.slice(before).join('; '));
        assert(!/Application error:|Internal Server Error|Authentication is not configured|This page could not be found/i.test(text),'Error page: '+text.slice(-1500));
        if(/You don't have access to this|You do not have (?:permission|access)|company read access is required|Forbidden|temporarily unavailable|source.*unavailable/i.test(text))throw Error('Rendered refusal/unavailability for tenant administrator: '+text.slice(-2500));
        const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);assert(!overflow,'Desktop horizontal overflow');
        await h.capture('route-'+company.key+'-'+route);
        return 'HTTP '+response.status()+'; '+controls.length+' controls; '+links.length+' links; '+(text.trim()?'rendered content':'empty page');
      },'LIVE_UI_ROUTE_SMOKE');
      const last=inventories.at(-1);
      if(last && last.route===route && last.controls.some(c=>c.type==='search'))await test('TA-SEARCH-'+company.key+'-'+route,'Directory search','Enter unique absent text in the page search; clear it','Filtered empty state is visible and recoverable',async()=>{
        const search=page.getByRole('main').getByRole('searchbox').first();if(!await search.count())throw Error('Search is not accessible as a searchbox');
        await search.fill('ZZZQA-NO-MATCH-20261029');await page.waitForTimeout(800);
        await search.fill('');await page.waitForTimeout(500);return 'Search field accepts and clears unmatched query; no page crash';
      },'LIVE_UI_INTERACTION_SMOKE');
    }
    // Repeated detail URLs and query variants are distinct links, but share an
    // already-rendered UI shape. Verify each using the authenticated app HTTP
    // endpoint and label the narrower scope explicitly in the result ledger.
    for(let index=0;index<httpQueue.length;index+=4){
      const batch=await Promise.allSettled(httpQueue.slice(index,index+4).map(async route=>{const response=await page.request.get(h.origin+route,{timeout:120000});return {route,status:response.status(),path:new URL(response.url()).pathname,origin:new URL(response.url()).origin};}));
      for(let offset=0;offset<batch.length;offset++){const result=batch[offset],route=httpQueue[index+offset];await test('TA-LINK-'+company.key+'-'+route,'Discovered links','Follow '+route+' through the authenticated app HTTP route; its UI shape was rendered separately','Authorized link resolves without server error or sign-in redirect',async()=>{if(result.status==='rejected')throw result.reason;assert(result.value.status<400,'HTTP '+result.value.status);assert.equal(result.value.origin,h.origin,'Unexpected authentication origin');assert(!/^\/(?:login|api\/auth)/.test(result.value.path),'Unexpected sign-in redirect');return 'HTTP '+result.value.status+'; UI shape '+shape(route)+' rendered separately; this specific URL was HTTP-checked only';},'LIVE_AUTHENTICATED_LINK_HTTP');}
    }
    await ready('/masters');
    for(const width of [390,768,1440])for(const theme of ['light','dark','ledger'])await test('TA-LAYOUT-'+company.key+'-'+width+'-'+theme,'Responsive UI','Set '+width+'px viewport and '+theme+' theme on Masters','Readable layout without document overflow',async()=>{
      await page.setViewportSize({width,height:1000});await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);await page.waitForTimeout(200);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'Horizontal viewport overflow');await h.capture('layout-'+company.key+'-'+width+'-'+theme);return 'No document overflow at '+width+'px in '+theme;
    });
    await page.setViewportSize({width:1440,height:1000});
  }
  resources.crawledCompanies=crawlCompanies.map(c=>c.key);
};
