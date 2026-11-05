import {beforeEach,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {AnalyticsReportWorkspace} from '../app/components/AnalyticsReportWorkspace';
import {AnalyticsInsights} from '../app/components/AnalyticsInsights';
import {productFieldRequest} from '../app/lib/product-fields';
import {completionFixture} from './analytics-completion-fixture';
import {trialProps,uuid} from './trial-balance-fixture';
import type {AnalyticsSummary} from '../app/lib/analytics-workspace';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
beforeEach(()=>{vi.mocked(productFieldRequest).mockReset();localStorage.clear();});

it.each([['BUYER_PROFIT','invoices','Invoices and returns'],['PRODUCT_PROFIT','groups','Product groups']] as const)('runs the second %s view and preserves the new report identity',async(code,view,title)=>{
 const fixture=completionFixture(code);
 vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<AnalyticsReportWorkspace {...trialProps} report={code}/>);
 await screen.findByRole('region',{name:'Business insights'});
 const selection=screen.getByLabelText('Report view');
 expect(within(selection).getByRole('option',{name:title})).toBeInTheDocument();
 fireEvent.change(selection,{target:{value:view}});
 fireEvent.click(screen.getByRole('button',{name:'Apply'}));
 await waitFor(()=>expect(vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs')).at(-1)?.[3]).toMatchObject({code,view}));
 expect(screen.queryByLabelText('Trend interval')).not.toBeInTheDocument();
 expect(screen.getByRole('columnheader',{name:/Period/})).toBeVisible();
});

it('loads product groups from the same frozen snapshot as the report',async()=>{
 const fixture=completionFixture('PRODUCT_PROFIT');
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body)=>{
  if(path.includes('/inventory?'))return {generation_id:uuid(9),items:[{id:uuid(77),name:'Retained group'}],next_cursor:null};
  return fixture.request(service,method,path,body);
 });
 render(<AnalyticsReportWorkspace {...trialProps} report="PRODUCT_PROFIT"/>);
 await screen.findByRole('region',{name:'Business insights'});
 const selector=screen.getByRole('combobox',{name:'Product group'});
 fireEvent.focus(selector);
 fireEvent.change(selector,{target:{value:'Retained'}});
 fireEvent.click(await screen.findByRole('option',{name:'Retained group'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Apply'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Apply'}));
 await waitFor(()=>expect(vi.mocked(productFieldRequest).mock.calls.filter(call=>call[1]==='POST'&&call[2].endsWith('/report-runs')).at(-1)?.[3]).toMatchObject({parameters:{group_id:uuid(77)}}));
 expect(vi.mocked(productFieldRequest).mock.calls.some(call=>call[2].includes('/report-generations/'+uuid(9)+'/inventory?kind=GROUP'))).toBe(true);
 expect(vi.mocked(productFieldRequest).mock.calls.some(call=>call[2].includes('/account-groups'))).toBe(false);
});

it('offers a buyer selector and hides exports without permission',async()=>{
 const fixture=completionFixture('BUYER_PROFIT');
 vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<AnalyticsReportWorkspace {...trialProps} report="BUYER_PROFIT" permissions={['report.read']}/>);
 await screen.findByRole('region',{name:'Business insights'});
 expect(screen.getByRole('combobox',{name:'Buyer'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'Print / PDF'})).toBeNull();
});

it.each([['BUYER_PROFIT','invoices'],['PRODUCT_PROFIT','groups']] as const)('restores the retained %s view in its selector',async(code,view)=>{
 const fixture=completionFixture(code,view);
 vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<AnalyticsReportWorkspace {...trialProps} report={code} initialRun={fixture.job.id}/>);
 await screen.findByRole('region',{name:'Business insights'});
 expect(screen.getByLabelText('Report view')).toHaveValue(view);
});

it('keeps missing costs and overlapping group totals explicit beside the figures',()=>{
 const summary:AnalyticsSummary={code:'PRODUCT_PROFIT',calculation_version:3,date_from:'2026-04-01',date_to:'2026-04-30',comparison_present:false,amounts:{CURRENT:{INR:{net_sales:'200',cost:null,gross_profit:null,margin_percent:null,unavailable_line_count:2}}},trends:[],notices:['Group rows are not additive; summary totals count each line once.','Some costs are unavailable.']};
 render(<AnalyticsInsights summary={summary}/>);
 for(const note of summary.notices)expect(screen.getByText(note).closest('details')).toBeNull();
 expect(within(screen.getByRole('region',{name:'INR insights'})).getAllByText('Unavailable')).toHaveLength(3);
 expect(screen.getByText('Lines missing cost').parentElement).toHaveTextContent('2');
});

it('keeps comparison-only currencies visible without inventing current totals',()=>{
 const summary=completionFixture('PRODUCT_PROFIT').job.result.evidence.analytics!;
 summary.comparison_present=true;
 summary.amounts={CURRENT:{},COMPARATIVE:{USD:{net_sales:'200',cost:'150',gross_profit:'50',margin_percent:'25',unavailable_line_count:0}}};
 render(<AnalyticsInsights summary={summary}/>);
 const currency=screen.getByRole('region',{name:'USD insights'});
 expect(within(currency).getByText('No current-period activity for this currency.')).toBeVisible();
 expect(within(currency).getAllByText(/Comparison:/).some(node=>node.textContent?.includes('200'))).toBe(true);
 expect(within(currency).getAllByText('No activity')).toHaveLength(5);
});

it('keeps applied comparison dates and frozen dimension names visible while filters are edited',async()=>{
 const fixture=completionFixture('PRODUCT_PROFIT');
 fixture.job.parameters={...fixture.job.parameters,comparative_from:'2025-04-01',comparative_to:'2025-04-30'};
 fixture.job.result.evidence.analytics!.comparison_present=true;
 fixture.job.result.evidence.analytics!.selected_filters={item_id:'Retained product ('+uuid(70)+')',group_id:'Retained group ('+uuid(71)+')'};
 vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<AnalyticsReportWorkspace {...trialProps} report="PRODUCT_PROFIT" initialRun={fixture.job.id}/>);
 const insights=await screen.findByRole('region',{name:'Business insights'});
 expect(within(insights).getByText(/Comparison period 01 Apr 2025/)).toHaveTextContent('30 Apr 2025');
 expect(within(insights).getByText('Product: Retained product')).toBeVisible();
 expect(within(insights).getByText('Product group: Retained group')).toBeVisible();
 expect(screen.getByRole('combobox',{name:'Product'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:/More filters/}));
 fireEvent.change(screen.getByLabelText('Compare from'),{target:{value:'2024-04-01'}});
 expect(within(insights).getByText(/Comparison period 01 Apr 2025/)).toBeVisible();
});

it('labels invoice buyers clearly and formats comparison evidence in row details',async()=>{
 const fixture=completionFixture('BUYER_PROFIT','invoices');
 const row={ordinal:1,data:{...fixture.data,row_kind:'INVOICE_PROFIT',invoice_kind:'CREDIT_NOTE',account_name:'Example buyer',comparison_amount:'1234.5',change_amount:null,change_percent:null,return_count:1},drilldowns:[{key:'row_detail',title:'Profit details',method:'GET',token:'signed'}]};
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body)=>{
  if(path.includes('/rows/1?'))return row;
  if(path.includes('/rows?'))return {items:[row],page:{next_cursor:null}};
  return fixture.request(service,method,path,body);
 });
 render(<AnalyticsReportWorkspace {...trialProps} report="BUYER_PROFIT" initialRun={fixture.job.id}/>);
 await screen.findByRole('region',{name:'Business insights'});
 expect(screen.getByRole('columnheader',{name:'Buyer'})).toBeVisible();
 expect(screen.getByRole('columnheader',{name:'Gross margin'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:/Actions for/}));
 fireEvent.click(screen.getByRole('menuitem',{name:'Profit details'}));
 const detail=await screen.findByRole('dialog',{name:'Profit details'});
 expect(await within(detail).findByText('Comparison gross profit')).toBeVisible();
 expect(within(detail).getByText('1,234.50')).toBeVisible();
 expect(within(detail).getByText('Credit note')).toBeVisible();
 expect(within(detail).getByText('Gross profit change').nextElementSibling).toHaveTextContent('Unavailable');
});

it.each([['BUYER_PROFIT','default'],['BUYER_PROFIT','invoices'],['PRODUCT_PROFIT','default'],['PRODUCT_PROFIT','groups']] as const)('exports the retained %s/%s view with a top download link',async(code,view)=>{
 const fixture=completionFixture(code,view);
 vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 const download=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 try{
  render(<AnalyticsReportWorkspace {...trialProps} report={code} initialRun={fixture.job.id}/>);
  await screen.findByRole('region',{name:'Business insights'});
  fireEvent.click(screen.getByRole('button',{name:'Print / PDF'}));
  expect((await screen.findByRole('link',{name:'Download report'})).closest('.janso-finance-status')).not.toBeNull();
  expect(download).toHaveBeenCalledOnce();
  expect(vi.mocked(productFieldRequest).mock.calls.find(call=>call[2].endsWith('/exports'))?.[3]).toMatchObject({view,format:'PDF'});
 }finally{download.mockRestore();}
});
