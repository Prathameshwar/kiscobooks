import {createRequire} from 'node:module';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {act,render,waitFor} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {AnalyticsReportWorkspace} from '../app/components/AnalyticsReportWorkspace';
import {ControlReportWorkspace} from '../app/components/ControlReportWorkspace';
import {isAnalyticsReport} from '../app/lib/analytics-workspace';
import {isControlReport} from '../app/lib/control-workspace';
import {productFieldRequest} from '../app/lib/product-fields';
import definitions from './analytics-definitions.json';
import {completionFixture,type CompletionCode} from './analytics-completion-fixture';
import {trialProps,trialJob} from './trial-balance-fixture';
import {consoleLayoutCss} from './console-layout-fixture';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
it('contains every Analytics view at desktop and mobile widths in both themes',async()=>{
 const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const artifacts=resolve('../../../.tools/analytics-completion/browser');mkdirSync(artifacts,{recursive:true});
 try{
  const page=await browser.newPage();
  for(const code of Object.keys(definitions) as CompletionCode[])for(const view of definitions[code].definition.views){
   const fixture=completionFixture(code,view.key);
   if(code==='BUYER_PROFIT'||code==='PRODUCT_PROFIT'){
    fixture.job.parameters={...fixture.job.parameters,comparative_from:'2025-04-01',comparative_to:'2025-04-30'};
    const summary=fixture.job.result.evidence.analytics!;
    summary.comparison_present=true;
    summary.amounts.COMPARATIVE={INR:{net_sales:'900',cost:null,gross_profit:null,margin_percent:null,unavailable_line_count:2},USD:{net_sales:'200',cost:'100',gross_profit:'100',margin_percent:'50',unavailable_line_count:0}};
    summary.selected_filters=code==='BUYER_PROFIT'?{party_id:'Retained buyer with a long registered business name'}:{group_id:'Parent group / long retained product subgroup name',item_id:'ProductWithAnUnbrokenNameThatMustWrapInsideTheAppliedSelection'};
   }
   vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
   let mounted!:ReturnType<typeof render>;
   await act(async()=>{mounted=render(isAnalyticsReport(code)?<AnalyticsReportWorkspace {...trialProps} report={code} initialRun={trialJob.id}/>:isControlReport(code)?<ControlReportWorkspace {...trialProps} report={code} years={[trialProps.year]} initialRun={trialJob.id}/>:<></>);});
   await waitFor(()=>expect(mounted.container.querySelector('tbody td')).not.toBeNull());
   for(const width of [1440,390,320])for(const theme of ['light','dark']){
    await page.setViewportSize({width,height:1000});
    await page.setContent('<!doctype html><html data-theme="'+theme+'"><head><style>'+consoleLayoutCss()+'</style></head><body class="janso-root">'+mounted.container.innerHTML+'</body></html>');
    await page.evaluate(()=>document.fonts.ready);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth),code+'/'+view.key+'/'+width).toBeLessThanOrEqual(width+1);
    const table=page.locator('.janso-day-book__table-scroll').last();
    expect(await table.evaluate((node:HTMLElement)=>node.scrollWidth>=node.clientWidth)).toBe(true);
    if(width===1440&&isAnalyticsReport(code)){
     for(const chart of await page.locator('.janso-analytics-trend .janso-chart').all()){
      expect((await chart.boundingBox())!.height).toBeLessThanOrEqual(300);
     }
    }
    if(view.key==='default'||width===1440&&theme==='light')await page.screenshot({path:resolve(artifacts,code+'-'+view.key+'-'+width+'-'+theme+'.png'),fullPage:true});
   }
   mounted.unmount();
  }
 }finally{await browser.close();}
},240_000);
