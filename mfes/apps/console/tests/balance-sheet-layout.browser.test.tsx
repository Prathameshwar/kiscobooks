import {createRequire} from 'node:module';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {fireEvent,render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {BalanceSheetWorkspace} from '../app/components/BalanceSheetWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {balanceMock,balanceProps,balanceJob,balanceRows} from './balance-sheet-fixture';
import {consoleLayoutCss} from './console-layout-fixture';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn(),ProductFieldError:class extends Error{}}));
vi.mock('../app/components/ReportWorkspace',()=>({ReportWorkspace:()=>null}));

it('renders Standard sides and Comparative columns across screen sizes and themes',async()=>{
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const artifacts=resolve('../../../.tools/balance-sheet-review');mkdirSync(artifacts,{recursive:true});
  try{
    for(const mode of ['default','comparison'] as const){
      vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body)=>{
        if(path.endsWith('/report-runs/'+balanceJob.id))return {...balanceJob,view:mode,parameters:{...balanceJob.parameters,...(mode==='comparison'?{comparative_to:'2026-03-31'}:{})}};
        return balanceMock(service,method,path,body);
      });
      const mounted=render(<BalanceSheetWorkspace {...balanceProps} initialRun={balanceJob.id}/>);
      await screen.findByText('Operating bank account');
      const page=await browser.newPage();
      for(const filters of [false,true]){
        if(filters)fireEvent.click(screen.getByRole('button',{name:'Filters'}));
        for(const width of [1440,390,320])for(const theme of ['light','dark']){
          await page.setViewportSize({width,height:1000});
          await page.setContent('<!doctype html><html data-theme="'+theme+'"><head><meta name="viewport" content="width=device-width"><style>'+consoleLayoutCss()+'</style></head><body class="janso-root">'+mounted.container.innerHTML+'</body></html>');
          expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width+1);
          if(mode==='default'){
            const sides=await page.locator('.janso-balance-sides > section').evaluateAll((nodes:HTMLElement[])=>nodes.map(node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,bottom:r.bottom};}));
            expect(sides).toHaveLength(2);
            if(width===1440){expect(sides[0].y).toBe(sides[1].y);expect(sides[0].x).toBeLessThan(sides[1].x);}
            else expect(sides[1].y).toBeGreaterThanOrEqual(sides[0].bottom);
          }else if(width<=390){
            const table=await page.locator('.janso-profit-scroll').evaluate((node:HTMLElement)=>({width:node.clientWidth,inside:node.scrollWidth}));
            expect(table.inside).toBeGreaterThan(table.width);
          }
          await page.screenshot({path:resolve(artifacts,mode+'-'+width+'-'+theme+(filters?'-filters':'')+'.png'),fullPage:true,animations:'disabled'});
        }
      }
      await page.close();mounted.unmount();
    }
  }finally{await browser.close();}
},120_000);

it('keeps large balances inside their cells in both views on narrow screens',async()=>{
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    for(const mode of ['default','comparison'] as const){
      vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body)=>{
        if(path.includes('/rows?'))return {items:balanceRows.map(row=>({...row,data:{...row.data,amount:'-999999999999999.9999',previous_amount:'999999999999999.9999',change_amount:'-1999999999999999.9998'}})),page:{next_cursor:null}};
        if(path.endsWith('/report-runs/'+balanceJob.id))return {...balanceJob,view:mode,parameters:{...balanceJob.parameters,...(mode==='comparison'?{comparative_to:'2026-03-31'}:{})}};
        return balanceMock(service,method,path,body);
      });
      const mounted=render(<BalanceSheetWorkspace {...balanceProps} initialRun={balanceJob.id}/>);
      await screen.findByText('Operating bank account');
      const page=await browser.newPage();
      for(const width of [320,390]){
        await page.setViewportSize({width,height:1000});
        await page.setContent('<!doctype html><html><head><style>'+consoleLayoutCss()+'</style></head><body class="janso-root">'+mounted.container.innerHTML+'</body></html>');
        await page.evaluate(()=>document.fonts.ready);
        const cells=await page.locator('.janso-profit-scroll td').evaluateAll((nodes:HTMLElement[])=>nodes.map(node=>{
          const range=document.createRange();range.selectNodeContents(node);
          const text=range.getBoundingClientRect(),cell=node.getBoundingClientRect();
          return {textLeft:text.left,cellLeft:cell.left,textRight:text.right,cellRight:cell.right};
        }));
        for(const cell of cells){expect(cell.textLeft).toBeGreaterThanOrEqual(cell.cellLeft);expect(cell.textRight).toBeLessThanOrEqual(cell.cellRight);}
        expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width+1);
      }
      mounted.unmount();await page.close();
    }
  }finally{await browser.close();}
},60_000);
