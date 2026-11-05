import {createRequire} from 'node:module';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {fireEvent,render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {TrialBalanceWorkspace} from '../app/components/TrialBalanceWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {trialJob,trialMock,trialProps,trialRun} from './trial-balance-fixture';
import {consoleLayoutCss} from './console-layout-fixture';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn(),ProductFieldError:class extends Error{}}));
const css=consoleLayoutCss();

it('renders both nonempty layouts in all themes and widths with a bounded scroll area',async()=>{
  const longName='Cash in hand '+ 'LongAccountNameWithoutSpaces'.repeat(5);
  vi.mocked(productFieldRequest).mockImplementation(async(...args)=>{
    const result=await trialMock(...args);
    if(args[2].includes('/hierarchy?')){const page=result as {items:{data:{row_kind:string;name:string}}[]};return {...page,items:page.items.map(item=>item.data.row_kind==='ACCOUNT'?{...item,data:{...item.data,name:longName}}:item)};}
    return result;
  });
  const mounted=render(<TrialBalanceWorkspace {...trialProps} years={[trialProps.year]} permissions={[...trialProps.permissions,'report.definition.manage']}/>);await screen.findByText('Current assets');
  fireEvent.click(screen.getByRole('button',{name:'Expand Current assets'}));await screen.findByRole('button',{name:longName});
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const artifacts=resolve('../../../.tools/trial-balance-review');mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage();
    for(const mode of ['Closing balances','Opening and movement']){
      fireEvent.click(screen.getByRole('radio',{name:mode}));
      for(const expanded of [false,true]){
      const filters=screen.getByRole('button',{name:'Filter'});
      if(filters.getAttribute('aria-expanded')!==String(expanded))fireEvent.click(filters);
      for(const select of mounted.container.querySelectorAll('select'))for(const option of select.options)option.toggleAttribute('selected',option.selected);
      for(const width of [1440,768,390,320])for(const theme of ['light','dark','ledger']){
        await page.setViewportSize({width,height:1000});
        await page.setContent('<!doctype html><html data-theme="'+theme+'" style="color-scheme:'+ (theme==='dark'?'dark':'light')+'"><head><meta name="viewport" content="width=device-width"><style>'+css+'</style></head><body class="janso-root" style="background:var(--janso-paper)">'+mounted.container.innerHTML+'</body></html>');
        await page.screenshot({path:resolve(artifacts,mode.replaceAll(' ','-')+'-'+width+'-'+theme+'-filters-'+(expanded?'open':'closed')+'.png'),fullPage:true,animations:'disabled'});
        const measurements=await page.evaluate(()=>{
          const hint=document.querySelector('.janso-trial-scroll-hint')!;
          const above=getComputedStyle(hint).display==='none'?document.querySelector('.janso-trial-viewbar')!:hint;
          return {width:document.documentElement.clientWidth,content:document.documentElement.scrollWidth,table:document.querySelector('.janso-trial-scroll')!.getBoundingClientRect().width,caption:document.querySelector('caption')!.getBoundingClientRect().height,subtitleGap:document.querySelector('.janso-trial-heading p')!.getBoundingClientRect().top-document.querySelector('h1')!.getBoundingClientRect().bottom,tableGap:document.querySelector('.janso-trial-scroll')!.getBoundingClientRect().top-above.getBoundingClientRect().bottom};
        });
        expect(measurements.content).toBeLessThanOrEqual(measurements.width+1);
        expect(measurements.table).toBeGreaterThan(0);
        expect(measurements.caption).toBeLessThanOrEqual(1);
        expect(measurements.subtitleGap).toBeLessThanOrEqual(4);
        expect(measurements.tableGap).toBeLessThanOrEqual(12);
        expect(await page.getByRole('columnheader',{name:'Debit',exact:true}).first().evaluate((element:HTMLElement)=>getComputedStyle(element).textAlign)).toBe('right');
        const disclosure=await page.getByRole('button',{name:'Collapse Current assets'}).boundingBox();
        expect(disclosure!.width).toBeGreaterThanOrEqual(24);
        expect(disclosure!.height).toBeGreaterThanOrEqual(24);
        expect(await page.getByRole('region',{name:'Trial Balance filters'}).count()).toBe(expanded?1:0);
        if(mode==='Opening and movement'){
          const debit=page.getByRole('columnheader',{name:'Debit',exact:true}).first();
          expect(await debit.evaluate((element:HTMLElement)=>getComputedStyle(element).position)).toBe('static');
          expect(await debit.evaluate((element:HTMLElement)=>getComputedStyle(element).backgroundColor)).toBe(await page.getByRole('columnheader',{name:'Credit',exact:true}).first().evaluate((element:HTMLElement)=>getComputedStyle(element).backgroundColor));
        }
        expect(await page.getByRole('columnheader',{name:'Account / group'}).evaluate((element:HTMLElement)=>getComputedStyle(element).position)).toBe('sticky');
        await expect(page.getByText('Grand total',{exact:true}).count()).resolves.toBe(1);
        await page.getByRole('region',{name:'Trial Balance accounts'}).focus();
        expect(await page.getByRole('region',{name:'Trial Balance accounts'}).evaluate((element:HTMLElement)=>document.activeElement===element)).toBe(true);
      }
      }
    }
    await page.setViewportSize({width:768,height:1000});
    await page.evaluate(()=>{document.documentElement.style.zoom='2';});
    const zoom=await page.evaluate(()=>({width:document.documentElement.clientWidth,content:document.documentElement.scrollWidth}));
    expect(zoom.content).toBeLessThanOrEqual(zoom.width+1);
    await page.getByRole('button',{name:'Collapse Current assets'}).focus();
    expect(await page.getByRole('button',{name:'Collapse Current assets'}).evaluate((element:HTMLElement)=>document.activeElement===element)).toBe(true);
    await page.screenshot({path:resolve(artifacts,'Opening-and-movement-200-percent-zoom.png'),fullPage:true,animations:'disabled'});
    // Normal account names give the visual review a representative compact desktop/mobile page.
    fireEvent.click(screen.getByRole('radio',{name:'Closing balances'}));
    fireEvent.click(screen.getByRole('button',{name:'Filter'}));
    for(const width of [1440,390,320]){
      await page.setViewportSize({width,height:1000});
      await page.setContent('<!doctype html><html data-theme="light"><head><meta name="viewport" content="width=device-width"><style>'+css+'</style></head><body class="janso-root" style="background:var(--janso-paper)">'+mounted.container.innerHTML.replaceAll(longName,'Cash in hand')+'</body></html>');
      const accounts=page.getByRole('region',{name:'Trial Balance accounts'});
      expect(await accounts.evaluate((element:HTMLElement)=>element.scrollWidth-element.clientWidth)).toBeLessThanOrEqual(1);
      expect(await page.getByLabel('Export hierarchy').evaluate((element:HTMLSelectElement)=>{
        const style=getComputedStyle(element),canvas=document.createElement('canvas'),context=canvas.getContext('2d')!;
        context.font=style.font;
        return context.measureText(element.selectedOptions[0].text).width <= element.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight);
      })).toBe(true);
      await page.screenshot({path:resolve(artifacts,'trial-balance-toolbar-'+width+'.png'),fullPage:true,animations:'disabled'});
    }
    const touchPage=await browser.newPage({viewport:{width:390,height:844},hasTouch:true});
    await touchPage.setContent(await page.content());
    expect(await touchPage.getByRole('button',{name:'Collapse Current assets'}).evaluate((element:HTMLElement)=>element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await touchPage.close();
  }finally{await browser.close();mounted.unmount();}
},120_000);

it('keeps report progress and Stop visible without horizontal overflow',async()=>{
  vi.mocked(productFieldRequest).mockReset();
  vi.mocked(productFieldRequest).mockImplementation(async(...args)=>{
    if(args[1]==='POST'&&args[2].endsWith('/report-runs'))return {...trialJob,status:'QUEUED'};
    if(args[1]==='GET'&&args[2].endsWith('/report-runs/'+trialRun))return {...trialJob,status:'QUEUED'};
    return trialMock(...args);
  });
  const mounted=render(<TrialBalanceWorkspace {...trialProps} permissions={[...trialProps.permissions,'report.definition.manage']}/>);
  await screen.findByText('Report queued');
  const {chromium}=createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const artifacts=resolve('../../../.tools/trial-balance-review');mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage();
    for(const width of [1440,390,320]){
      await page.setViewportSize({width,height:900});
      await page.setContent('<!doctype html><html data-theme="light"><head><meta name="viewport" content="width=device-width"><style>'+css+'</style></head><body class="janso-root">'+mounted.container.innerHTML+'</body></html>');
      const bounds=await page.getByRole('region',{name:'Trial Balance progress'}).boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(width+1);
      expect(bounds!.height).toBeLessThanOrEqual(width<=390?128:72);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      expect(await page.getByRole('button',{name:'Stop Trial Balance report'}).evaluate((button:HTMLElement)=>button.getBoundingClientRect().height)).toBeGreaterThanOrEqual(width<=390?44:36);
      await page.screenshot({path:resolve(artifacts,'trial-balance-progress-'+width+'.png'),fullPage:true,animations:'disabled'});
      await page.evaluate(()=>{
        const panel=document.querySelector('.janso-trial-progress')!;
        panel.setAttribute('data-stage','RUNNING');
        panel.querySelector('strong')!.textContent='Calculating report';
        panel.querySelector('.janso-trial-progress__message span')!.textContent='Building the Trial Balance.';
        const steps=panel.querySelectorAll('.janso-trial-progress__steps li');
        steps[1].setAttribute('data-state','done');steps[2].setAttribute('data-state','current');
      });
      const running=await page.getByRole('region',{name:'Trial Balance progress'}).boundingBox();
      expect(running!.y).toBe(bounds!.y);
      expect(running!.height).toBeLessThanOrEqual(bounds!.height+2);
    }
  }finally{await browser.close();mounted.unmount();}
},120_000);
