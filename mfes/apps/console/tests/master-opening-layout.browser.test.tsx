import {createRequire} from 'node:module';
import {mkdirSync,readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {AccountingConfigurationEditor} from '../app/components/AccountingConfigurationEditor';
import {accountingResource} from '../app/lib/accounting-configuration-resources';
import {serviceCall} from '../app/lib/service-call';
import {capture} from './master-opening-fixture';
import {COMPANY,GROUP,response} from './accounting-configuration-fixtures';
vi.mock('../app/lib/service-call',async original=>({...await original<typeof import('../app/lib/service-call')>(),serviceCall:vi.fn()}));
const css=['tokens.css','theme-light.css','theme-dark.css','theme-ledger.css','janso-ui.css','controls.css','shell.css','data.css','search-select.css','overlay.css','table.css','master-opening.css','setup.css'].map(name=>readFileSync(resolve('../../packages/ui/src/styles',name),'utf8')).join('\n');
it('keeps the four-step wizard and both opening modes readable at desktop and mobile widths',async()=>{
  vi.mocked(serviceCall).mockImplementation(async(_,request)=>request.path.endsWith('/master-balances/capture')?{...capture,company_id:COMPANY} as never:response(request.path,request.method,request.body) as never);
  const view=render(<AccountingConfigurationEditor company={COMPANY} config={accountingResource('parties')!} supplier availableResources={['parties','party-roles','accounts']} manageableResources={['parties','party-roles','accounts']}/>);
  await screen.findByRole('textbox',{name:'Name'});
  fireEvent.click(within(screen.getByRole('navigation',{name:'Setup progress'})).getByRole('button',{name:/Opening balance/}));
  await waitFor(()=>expect(screen.getByRole('textbox',{name:'Opening balance'})).toBeEnabled());
  fireEvent.change(screen.getByRole('textbox',{name:'Opening balance'}),{target:{value:'1000.0001'}});fireEvent.change(screen.getByRole('combobox',{name:'Dr / Cr'}),{target:{value:'CREDIT'}});
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const artifacts=resolve('../../../.tools/master-opening-review');mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage();
    for(const mode of ['simple','bills']){
      if(mode==='bills'){
        fireEvent.click(screen.getByRole('radio',{name:'Bill-wise'}));
        for(const [label,value] of [['Bill number','PUR-2026-0001'],['Bill amount','2000'],['Pending amount','1000.0001'],['Bill date','2026-03-12'],['Due date','2026-04-10']])fireEvent.change(screen.getByLabelText(label!),{target:{value}});
        fireEvent.click(screen.getByRole('button',{name:'Add bill'}));fireEvent.click(screen.getByRole('button',{name:'Add another bill'}));
      }
      for(const select of view.container.querySelectorAll('select'))for(const option of select.options)option.toggleAttribute('selected',option.selected);
      for(const width of [1440,768,390,320])for(const theme of ['light','dark','ledger']){
        await page.setViewportSize({width,height:1000});
        await page.setContent('<!doctype html><html data-theme="'+theme+'"><head><meta name="viewport" content="width=device-width"><style>'+css+'</style></head><body class="janso-root">'+view.container.innerHTML+'</body></html>');
        const size=await page.evaluate(()=>({width:document.documentElement.clientWidth,content:document.documentElement.scrollWidth}));expect(size.content).toBeLessThanOrEqual(size.width+1);
        expect(await page.getByRole('navigation',{name:'Setup progress'}).getByRole('button').count()).toBe(4);
        const amount=page.getByRole('textbox',{name:'Opening balance'});expect(await amount.isVisible()).toBe(true);await amount.focus();expect(await amount.evaluate((element:HTMLElement)=>document.activeElement===element)).toBe(true);
        if(mode==='bills'){
          const pending=page.locator('tbody td[data-label="Pending"]');expect(await pending.isVisible()).toBe(true);expect((await pending.boundingBox())!.width).toBeGreaterThan(30);
          if(width<640){const bounds=(await page.locator('.janso-master-opening__list').boundingBox())!;for(const figure of [pending,page.locator('tfoot td.janso-figure')]){const box=(await figure.boundingBox())!;expect(box.x+box.width).toBeLessThanOrEqual(bounds.x+bounds.width);}}
        }
        const bounds=await page.locator('.janso-master-opening__fields').first().boundingBox();expect(bounds!.width).toBeGreaterThan(100);
        await page.screenshot({path:resolve(artifacts,`opening-${mode}-${width}-${theme}.png`),fullPage:true,animations:'disabled'});
      }
    }
    await page.setViewportSize({width:768,height:1000});await page.evaluate(()=>{document.documentElement.style.zoom='2';});const zoom=await page.evaluate(()=>({width:document.documentElement.clientWidth,content:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(element=>element.getBoundingClientRect().right>document.documentElement.clientWidth+1).map(element=>({tag:element.tagName,cls:element.className,text:element.textContent?.slice(0,80),parent:element.parentElement?.className,right:element.getBoundingClientRect().right})).slice(0,8)}));expect(zoom.content,JSON.stringify(zoom.overflow)).toBeLessThanOrEqual(zoom.width+1);
  }finally{await browser.close();view.unmount();}
},120_000);
it.each(['GENERAL','BANK','TAX'])('keeps the %s account opening step and clear action readable across widths and themes',async(kind)=>{
  vi.mocked(serviceCall).mockImplementation(async(_,request)=>request.path.endsWith('/master-balances/capture')?{...capture,company_id:COMPANY} as never:response(request.path,request.method,request.body) as never);
  const view=render(<AccountingConfigurationEditor company={COMPANY} config={accountingResource('accounts')!} prefills={{kind,group_id:GROUP}}/>);
  fireEvent.change(await screen.findByRole('textbox',{name:'Code'}),{target:{value:'CAPITAL'}});fireEvent.change(screen.getByRole('textbox',{name:'Name'}),{target:{value:'Opening capital'}});
  fireEvent.click(screen.getByRole('button',{name:'Next'}));await waitFor(()=>expect(screen.getByLabelText('Opening balance')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Opening balance'),{target:{value:'100.0001'}});fireEvent.change(screen.getByRole('combobox',{name:'Dr / Cr'}),{target:{value:'CREDIT'}});
  expect(screen.queryByRole('radio',{name:'Bill-wise'})).toBeNull();
  for(const select of view.container.querySelectorAll('select'))for(const option of select.options)option.toggleAttribute('selected',option.selected);
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright'),artifacts=resolve('../../../.tools/account-opening-review');mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage();
    for(const width of [1440,768,390,320])for(const theme of ['light','dark','ledger']){
      await page.setViewportSize({width,height:1000});await page.setContent('<!doctype html><html data-theme="'+theme+'"><head><meta name="viewport" content="width=device-width"><style>'+css+'</style></head><body class="janso-root">'+view.container.innerHTML+'</body></html>');
      const dimensions=await page.evaluate(()=>({content:document.documentElement.scrollWidth,width:document.documentElement.clientWidth}));expect(dimensions.content).toBeLessThanOrEqual(dimensions.width+1);
      if(width<640)for(const label of await page.locator('.janso-stepper__text > span:first-child').all()){
        expect(await label.evaluate((element:HTMLElement)=>element.getBoundingClientRect().height/parseFloat(getComputedStyle(element).lineHeight))).toBeLessThanOrEqual(2.1);
      }
      expect(await page.getByLabel('Opening date').isVisible()).toBe(true);const clear=page.getByRole('button',{name:'Clear opening balance'});await clear.focus();expect(await clear.evaluate((element:HTMLElement)=>document.activeElement===element)).toBe(true);
      expect(await page.getByRole('button',{name:'Create account'}).isVisible()).toBe(true);await page.screenshot({path:resolve(artifacts,`account-${width}-${theme}.png`),fullPage:true,animations:'disabled'});
    }
    await page.setViewportSize({width:768,height:1000});await page.evaluate(()=>{document.documentElement.style.zoom='2';});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
  }finally{await browser.close();view.unmount();}
},120_000);
