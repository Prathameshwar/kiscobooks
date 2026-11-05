import {createRequire} from 'node:module';
import {mkdirSync,readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {act,fireEvent,render,screen,within} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {OpeningStockEntry} from '../app/components/OpeningStockEntry';
import {serviceCall} from '../app/lib/service-call';
import {COMPANY,ITEM} from './opening-stock-fixtures';
vi.mock('../app/lib/service-call',async original=>({...await original<typeof import('../app/lib/service-call')>(),serviceCall:vi.fn()}));
vi.mock('../app/components/StockTrackingCommon',async()=>{
  const {TextField}=await import('@janso/ui');return {TrackingReference:({label,value}:{label:string;value:string})=><TextField label={label} value={value} readOnly/>};
});
vi.mock('../app/components/VoucherStock',async()=>{
  const {TextField}=await import('@janso/ui');return {StockReference:({label}:{label:string})=><TextField label={label} value="" readOnly/>,OpeningReference:()=>null};
});
it('keeps product opening steps, cost modes and tracking readable across widths and themes',async()=>{
  vi.mocked(serviceCall).mockResolvedValue({company_id:COMPANY,item_id:ITEM,lot_tracking:true,serial_tracking:true,expiry_required:true,manufacture_date_required:true} as never);
  const css=['tokens.css','theme-light.css','theme-dark.css','theme-ledger.css','janso-ui.css','controls.css','shell.css','data.css','search-select.css','overlay.css','setup.css','master-opening.css'].map(name=>readFileSync(resolve('../../packages/ui/src/styles',name),'utf8')).join('\n');
  let view!:ReturnType<typeof render>;
  await act(async()=>{view=render(<OpeningStockEntry company={COMPANY} initialItemId={ITEM} date="2026-04-01" currency="INR" mode="COMBINED" disabled={false} onAdd={vi.fn()} onDirty={()=>{}}/>);});
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright'),artifacts=resolve('../../../.tools/product-opening-review');mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage();
    for(const stage of ['Product and location','Cost and value','Unit cost','Tracking and history','Review allocation']){
      fireEvent.click(within(screen.getByRole('navigation',{name:'Setup progress'})).getByRole('button',{name:new RegExp(stage==='Unit cost'?'Cost and value':stage)}));
      if(stage==='Unit cost')fireEvent.change(screen.getByRole('combobox',{name:'Cost entry'}),{target:{value:'RATE'}});
      for(const select of view.container.querySelectorAll('select'))for(const option of select.options)option.toggleAttribute('selected',option.selected);
      for(const width of [1440,768,390,320])for(const theme of ['light','dark','ledger']){
        await page.setViewportSize({width,height:1000});await page.setContent('<!doctype html><html data-theme="'+theme+'"><head><meta name="viewport" content="width=device-width"><style>'+css+'</style></head><body class="janso-root"><main class="janso-page">'+view.container.innerHTML+'</main></body></html>');
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
        const progress=page.getByRole('navigation',{name:'Setup progress'});expect(await progress.getByRole('button').count()).toBe(4);
        if(width>=1024)expect((await progress.boundingBox())!.height).toBeLessThanOrEqual(120);
        if(width<640)for(const label of await page.locator('.janso-stepper__text > span:first-child').all())expect(await label.evaluate((element:HTMLElement)=>element.getBoundingClientRect().height/parseFloat(getComputedStyle(element).lineHeight))).toBeLessThanOrEqual(2.1);
        const current=progress.locator('[aria-current="step"]');await current.focus();expect(await current.evaluate((element:HTMLElement)=>document.activeElement===element)).toBe(true);
        await page.screenshot({path:resolve(artifacts,stage.toLowerCase().replaceAll(' ','-')+'-'+width+'-'+theme+'.png'),fullPage:true,animations:'disabled'});
      }
    }
    await page.setViewportSize({width:768,height:1000});await page.evaluate(()=>{document.documentElement.style.zoom='2';});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
  }finally{await browser.close();view.unmount();}
},120_000);
