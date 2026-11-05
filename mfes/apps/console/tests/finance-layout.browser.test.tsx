import {createRequire} from 'node:module';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {act,fireEvent,render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {FinanceReportWorkspace} from '../app/components/FinanceReportWorkspace';
import {ReportsHub} from '../app/components/ReportsHub';
import {financeWorkspaces,type FinanceReportCode} from '../app/lib/finance-workspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {financeFixture} from './finance-fixture';
import {trialProps,trialJob} from './trial-balance-fixture';
import {consoleLayoutCss} from './console-layout-fixture';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));

it('keeps every Finance view compact and contains wide financial tables on mobile',async()=>{
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const artifacts=resolve('../../../.tools/finance-review');mkdirSync(artifacts,{recursive:true});
  const css=consoleLayoutCss();
  try {
    const page=await browser.newPage();
    for(const code of Object.keys(financeWorkspaces) as FinanceReportCode[]) {
      for(const view of financeFixture(code).definition.definition.views) {
        const fixture=financeFixture(code,view.key);
        vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
        let mounted!:ReturnType<typeof render>;
        await act(async()=>{mounted=render(<FinanceReportWorkspace {...trialProps} report={code} initialRun={trialJob.id}/>);});
        await screen.findByText(/1 report rows|1 statement rows/);
        for(const filters of [false,true]) {
          if(filters)fireEvent.click(screen.getByRole('button',{name:'Filters'}));
          for(const width of [1440,390,320])for(const theme of ['light','dark']) {
            await page.setViewportSize({width,height:1000});
            await page.setContent('<!doctype html><html data-theme="'+theme+'"><head><style>'+css+'</style></head><body class="janso-root">'+mounted.container.innerHTML+'</body></html>');
            await page.evaluate(()=>document.fonts.ready);
            expect(await page.evaluate(()=>document.documentElement.scrollWidth),code).toBeLessThanOrEqual(width+1);
            if(!filters&&width===1440)expect((await page.locator('.janso-day-book__report').boundingBox()).y,code).toBeLessThan(360);
            const cells=await page.locator('td.janso-day-book__amount').evaluateAll((nodes:HTMLElement[])=>nodes.map(node=>{const range=document.createRange();range.selectNodeContents(node);const text=range.getBoundingClientRect(),cell=node.getBoundingClientRect();return text.left>=cell.left&&text.right<=cell.right;}));
            expect(cells.every(Boolean),code+' money cells').toBe(true);
            if(!filters||width===320)await page.screenshot({path:resolve(artifacts,code+'-'+view.key+'-'+width+'-'+theme+(filters?'-filters':'')+'.png'),fullPage:true,animations:'disabled'});
          }
        }
        mounted.unmount();
      }
    }
    await page.close();
  }finally{await browser.close();}
},240_000);

it('keeps GST setup actions on one line inside the disabled tax cards',async()=>{
  vi.mocked(productFieldRequest).mockResolvedValue({items:[]});
  const mounted=render(<ReportsHub company={trialProps.company} category="tax"/>);
  await screen.findAllByRole('link',{name:'Set up GST'});
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await browser.newPage();
    for(const width of [1440,768,390,320]) {
      await page.setViewportSize({width,height:1000});
      await page.setContent('<!doctype html><html><head><style>'+consoleLayoutCss()+'</style></head><body class="janso-root">'+mounted.container.innerHTML+'</body></html>');
      await page.evaluate(()=>document.fonts.ready);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width+1);
      const links=await page.locator('.janso-action-card__footer--setup > a').evaluateAll((nodes:HTMLElement[])=>nodes.map(node=>{
        const link=node.getBoundingClientRect(),card=node.closest('article')!.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(node);
        return {inside:link.left>=card.left&&link.right<=card.right&&link.bottom<=card.bottom,lines:range.getClientRects().length};
      }));
      expect(links).toHaveLength(2);
      for(const link of links){expect(link.inside).toBe(true);expect(link.lines).toBe(1);}
      const artifacts=resolve('../../../.tools/finance-review');mkdirSync(artifacts,{recursive:true});
      await page.screenshot({path:resolve(artifacts,'tax-setup-'+width+'.png'),fullPage:true});
    }
  }finally{mounted.unmount();await browser.close();}
},60_000);
