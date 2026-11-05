import {createRequire} from 'node:module';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {ProfitLossWorkspace} from '../app/components/ProfitLossWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {trialProps,uuid} from './trial-balance-fixture';
import {consoleLayoutCss} from './console-layout-fixture';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn(),ProductFieldError:class extends Error{}}));
vi.mock('../app/components/ReportWorkspace',()=>({ReportWorkspace:()=>null}));

const display={company_label:'Example Company',base_currency:'INR',amount_precision:2,quantity_precision:3,rounding_mode:'half_up',date_format:'dd MMM yyyy',datetime_format:'dd MMM yyyy HH:mm',digit_grouping:'indian',currency_display:'code',currency_symbol_position:'prefix',decimal_separator:'.',thousands_separator:',',negative_format:'minus',timezone:'Asia/Kolkata',locale:'en-IN'};
const summary={currency:'INR',sections:{},totals:{TOTAL_INCOME:{current:'123456.1200',previous:'111000.0000'},TOTAL_EXPENSE:{current:'45000.0000',previous:'50000.0000'},GROSS_PROFIT:{current:'78456.1200',previous:'61000.0000'},NET_PROFIT:{current:'-999999999999999.1200',previous:'61000.0000'}}};
const long='International Consulting and Software Development Revenue Account';
const rows=[
  {ordinal:1,data:{row_kind:'SECTION',label:'Direct income',amount:'123456.1200',previous_amount:'111000.0000',change_amount:'12456.1200',change_percent:'11.22%',currency:'INR'},drilldowns:[]},
  {ordinal:2,data:{row_kind:'GROUP',label:'Sales and services',group_id:'group-sales',group_code:'4000',amount:'123456.1200',previous_amount:'111000.0000',change_amount:'12456.1200',change_percent:'11.22%',currency:'INR'},drilldowns:[]},
  {ordinal:3,data:{row_kind:'ACCOUNT',label:long,group_id:'group-sales',group_name:'Sales and services',account_id:uuid(5),account_code:'400001',amount:'123456.1200',previous_amount:'111000.0000',change_amount:'12456.1200',change_percent:'11.22%',currency:'INR'},drilldowns:[]},
  {ordinal:4,data:{row_kind:'GROSS_PROFIT',label:'Gross profit',amount:'78456.1200',previous_amount:'61000.0000',change_amount:'17456.1200',change_percent:'28.62%',currency:'INR'},drilldowns:[]},
  {ordinal:5,data:{row_kind:'NET_PROFIT',label:'Net profit',amount:'78456.1200',previous_amount:'61000.0000',change_amount:'17456.1200',change_percent:'28.62%',currency:'INR'},drilldowns:[]},
];
const views=[{key:'default',title:'Statement',calculation:'profit_statement',columns:[{key:'label',title:'Account / group',kind:'TEXT'}]},{key:'comparison',title:'Period comparison',calculation:'profit_comparison',columns:[{key:'label',title:'Account / group',kind:'TEXT'}]}];

it('keeps both views within the page at desktop and mobile widths',async()=>{
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const artifacts=resolve('../../../.tools/profit-loss-review');mkdirSync(artifacts,{recursive:true});
  const css=consoleLayoutCss();
  try{
    for(const mode of ['default','comparison'] as const){
      const run={id:uuid(mode==='default'?50:51),kind:'RUN',code:'PROFIT_LOSS',version:6,status:'COMPLETE',generation_id:uuid(9),parameters:{date_from:'2026-04-01',date_to:'2026-04-30',...(mode==='comparison'?{comparative_from:'2026-03-01',comparative_to:'2026-03-31'}:{})},view:mode,views,display,completed_rows:5,result:{evidence:{profit_summary:summary}}};
      vi.mocked(productFieldRequest).mockImplementation(async(_service,_method,path)=>{
        if(path.endsWith('/report-definitions/PROFIT_LOSS'))return {definition:{code:'PROFIT_LOSS',version:6,views},run_enabled:true,export_limits:[]};
        if(path.includes('/rows?'))return {items:rows,page:{next_cursor:null,has_more:false,limit:200}};
        return run;
      });
      const mounted=render(<ProfitLossWorkspace {...trialProps} initialRun={run.id} permissions={['report.read','report.export']}/>);
      await screen.findByText(long);
      expect(screen.getByRole('radio',{name:mode==='default'?'Statement':'Period comparison'})).toHaveAttribute('aria-checked','true');
      const page=await browser.newPage();
      for(const width of [1440,390,320])for(const theme of ['light','dark']){
        await page.setViewportSize({width,height:900});
        await page.setContent('<!doctype html><html data-theme="'+theme+'"><head><meta name="viewport" content="width=device-width"><style>'+css+'</style></head><body class="janso-root">'+mounted.container.innerHTML+'</body></html>');
        const bounds=await page.evaluate(()=>({viewport:document.documentElement.clientWidth,page:document.documentElement.scrollWidth,table:document.querySelector('.janso-profit-scroll')!.getBoundingClientRect().width,inside:document.querySelector('.janso-profit-scroll')!.scrollWidth,card:document.querySelector('.janso-profit-summary')!.getBoundingClientRect().width}));
        expect(bounds.page).toBeLessThanOrEqual(bounds.viewport+1);
        expect(bounds.table).toBeGreaterThan(0);
        expect(bounds.card).toBeLessThanOrEqual(bounds.viewport);
        const overflowingCards=await page.locator('.janso-profit-summary > div').evaluateAll((nodes:HTMLElement[])=>nodes.filter(node=>node.scrollWidth>node.clientWidth+1).length);
        expect(overflowingCards).toBe(0);
        if(width<=390){
          const labelWidth=await page.getByRole('columnheader',{name:'Account / group'}).evaluate((node:HTMLElement)=>node.getBoundingClientRect().width);
          expect(labelWidth).toBeLessThan(bounds.table*0.65);
        }
        if(mode==='comparison'&&width<=390)expect(bounds.inside).toBeGreaterThan(bounds.table);
        expect(await page.getByRole('columnheader',{name:'Account / group'}).evaluate((node:HTMLElement)=>getComputedStyle(node).position)).toBe('sticky');
        await page.screenshot({path:resolve(artifacts,`${mode}-${width}-${theme}.png`),fullPage:true,animations:'disabled'});
      }
      await page.close();mounted.unmount();
    }
  }finally{await browser.close();}
},120_000);
