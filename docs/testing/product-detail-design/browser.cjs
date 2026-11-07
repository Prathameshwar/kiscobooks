
(async()=>{
 const { chromium }=await import(process.env.PLAYWRIGHT_MODULE || '/tmp/kisco-e2e/node_modules/playwright/index.mjs');
 const { gunzipSync }=require('node:zlib');
 const bundle=JSON.parse(gunzipSync(Buffer.from(require('node:fs').readFileSync(0,'utf8').trim(),'base64')).toString()); const pages=Object.fromEntries(Object.entries(bundle.pages).map(([name,html])=>[name,html.replace('__CSS__',bundle.css)]));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']});
 const result={measurements:[],screenshots:[]};
 try{
  for(const [name,html] of Object.entries(pages))for(const width of [1440,1024,768,390,320]){
   const page=await browser.newPage({viewport:{width,height:1000}});
   await page.setContent(html);await page.waitForFunction(()=>document.body.hasAttribute('data-layout'));
   const geometry=await page.evaluate(()=>{
    const elements=[...document.querySelectorAll('.janso-product-detail__section,.janso-product-detail__hero,.janso-product-detail__navigation a')];
    return {width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:elements.filter(e=>{const r=e.getBoundingClientRect();return r.left< -1||r.right>innerWidth+1}).map(e=>e.textContent.trim().slice(0,60)),heroColumns:getComputedStyle(document.querySelector('.janso-product-detail__hero')).display,columns:getComputedStyle(document.querySelector('.janso-product-detail__layout')).gridTemplateColumns};
   });
   result.measurements.push({name,...geometry});
   if(geometry.overflow.length || geometry.scroll>width+1)throw new Error(name+' overflows at '+width+'px');
   if(name==='simple-light'&&[1440,390].includes(width)||name==='sku-light'&&width===1440||name==='profile-light'&&width===1440||name==='simple-dark'&&width===1440||name==='simple-ledger'&&width===1440)result.screenshots.push({name:name+'-'+width,data:(await page.screenshot({fullPage:true})).toString('base64')});
   const anchor=page.locator('nav[aria-label="Product detail sections"] a').first();
   if(await anchor.count()){await anchor.focus();await page.keyboard.press('Enter');if(!await page.evaluate(()=>document.activeElement.matches('.janso-product-detail__section')))throw new Error(name+' section navigation did not move keyboard focus');}
   await page.close();
  }
  process.stdout.write(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{process.stdout.write(JSON.stringify({error:e.message}));process.exitCode=1;});
