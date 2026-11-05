import { act, fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ReportsHub } from '../app/components/ReportsHub';
import WorkspacePage from '../app/reports/workspace/page';
import CategoryPage from '../app/reports/[category]/page';
import { reportSections, reportCategories, reportSectionsFor } from '../app/lib/report-cards';
import { productFieldRequest } from '../app/lib/product-fields';
import { pageContext } from '../app/lib/page-context';
import { flattenNavigation, navigationFor, navSections, sidebarCurrentHref } from '../app/nav';
import { sessionFor, companyContextFor } from './helpers';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ReportWorkspace', () => ({ ReportWorkspace: ({ initialReport, permissions }: { initialReport?: string; permissions: string[] }) => <p>Workspace {initialReport} {permissions.join(',')}</p> }));
vi.mock('../app/components/BalanceSheetWorkspace', () => ({ BalanceSheetWorkspace: () => <p>Balance Sheet workspace</p> }));
vi.mock('../app/components/ProfitLossWorkspace', () => ({ ProfitLossWorkspace: () => <p>Profit and Loss workspace</p> }));
vi.mock('../app/components/FinanceReportWorkspace', () => ({ FinanceReportWorkspace: ({report}: {report:string}) => <p>Finance workspace {report}</p> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
const company='01990000-0000-7000-8000-000000000001';
const catalog=()=>({items:[]});
beforeEach(async()=>{
  vi.mocked(productFieldRequest).mockReset();vi.mocked(productFieldRequest).mockResolvedValue(catalog());
  const session=await sessionFor({permissions:['report.read','report.export']});session.company={id:company,name:'Company A'};
  session.grants=[{scope_type:'company',scope_id:company,permissions:session.permissions,valid_from:'2000-01-01',valid_to:null}];
  vi.mocked(pageContext).mockResolvedValue({session,context:companyContextFor()});
});
it('registers 45 native reports including analytics and GST returns with unique codes',()=>{
  const cards=reportSections.flatMap(section=>section.reports);expect(cards).toHaveLength(45);expect(new Set(cards.map(card=>card.code)).size).toBe(45);expect(reportSections).toHaveLength(9);
});
it('assigns every existing report to exactly one category',()=>{
  const codes=reportCategories.flatMap(category=>reportSectionsFor(category.key).flatMap(section=>section.reports.map(report=>report.code)));
  expect(codes).toHaveLength(45);expect(new Set(codes).size).toBe(45);
  expect(new Set(codes)).toEqual(new Set(reportSections.flatMap(section=>section.reports.map(report=>report.code))));
});
it('keeps GSTR-1 and GSTR-3B visible with a setup explanation when the catalogue omits them',async()=>{
  render(<ReportsHub company={company} category="tax"/>);
  await waitFor(()=>expect(screen.queryByText('Checking report availability…')).not.toBeInTheDocument());
  for(const name of ['GSTR-1','GSTR-3B']) {
    const card=screen.getByRole('heading',{name}).closest('article')!;
    expect(within(card).getByText(/eligible Indian GST registration/)).toBeVisible();
    expect(within(card).getByRole('button',{name:'GST setup or access required'})).toBeDisabled();
    expect(within(card).getByRole('link',{name:'Set up GST'})).toHaveAttribute('href','/companies/'+company+'/gst-settings');
  }
});
it('opens an available Day Book in the selected reports workspace',async()=>{
  vi.mocked(productFieldRequest).mockResolvedValue({items:[{definition:{code:'DAY_BOOK',version:6},run_enabled:true}]});
  render(<ReportsHub company={company} category="finance"/>);
  expect(await screen.findByRole('link',{name:'Day book'})).toHaveAttribute('href','/reports/workspace?report=DAY_BOOK');
});
it.each(['inventory','finance','tax','analytics'])('renders the authorised %s landing route',async category=>{
  render(await CategoryPage({params:Promise.resolve({category})}));
  expect(screen.getByRole('heading',{level:1,name:reportCategories.find(item=>item.key===category)!.title})).toBeVisible();
  await waitFor(()=>expect(screen.queryByText('Checking report availability…')).not.toBeInTheDocument());
  for(const card of screen.getAllByRole('article'))expect(within(card).getByRole('button')).toBeDisabled();
});
it.each(['other company','expired','department','none'] as const)('rejects category page and submenu access from %s authority',async reason=>{
  const {session}=await pageContext();if(reason==='other company')session.grants![0].scope_id='other';if(reason==='expired')session.grants![0].valid_to='2000-01-01';if(reason==='department')session.grants![0].scope_type='department';if(reason==='none')session.grants=[];
  render(await CategoryPage({params:Promise.resolve({category:'inventory'})}));expect(screen.getByRole('alert')).toBeVisible();
  expect(flattenNavigation(navigationFor(session).flatMap(section=>section.items)).some(item=>item.href.startsWith('/reports'))).toBe(false);
});
it.each(['unknown','../finance','INVENTORY'])('rejects unknown report category %s',async category=>{
  await expect(CategoryPage({params:Promise.resolve({category})})).rejects.toThrow('not found');
});
it('keeps loading reports unavailable and retains catalogue search',()=>{
  vi.mocked(productFieldRequest).mockReturnValue(new Promise(()=>{}));
  render(<ReportsHub company={company}/>);
  const cards=screen.getAllByRole('article');expect(cards).toHaveLength(45);
  expect(document.querySelectorAll('.janso-action-card-grid--compact')).toHaveLength(9);
  expect(screen.getByText('Search reports')).toBeVisible();
  for(const card of cards)expect(within(card).getByRole('button')).toBeDisabled();
  expect(screen.queryByRole('link',{name:'Trial balance'})).not.toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'Open report workspace'})).not.toBeInTheDocument();
  expect(productFieldRequest).toHaveBeenCalled();
});
it.each([
  ['inventory','Inventory reports','Stock summary','Trial balance'],
  ['finance','Finance reports','Trial balance','Stock summary'],
  ['tax','Tax reports','Invoice tax register','Source reconciliation'],
  ['analytics','Analytics','Source reconciliation','Tax to ledger reconciliation'],
] as const)('limits %s landing cards and search to the correct category', async (category,title,present,absent)=>{
  render(<ReportsHub company={company} category={category}/>);
  expect(screen.getByRole('heading',{level:1,name:title})).toBeVisible();
  expect(screen.getByRole('heading',{level:3,name:present})).toBeVisible();
  expect(screen.queryByRole('heading',{level:3,name:absent})).not.toBeInTheDocument();
  for(const card of screen.getAllByRole('article'))expect(within(card).getByRole('button')).toBeDisabled();
  fireEvent.change(screen.getByRole('searchbox',{name:'Search reports'}),{target:{value:absent}});
  expect(await screen.findByText(/No reports match/)).toBeVisible();
});
it.each(['trial bal','TRIAL_BALANCE','balance sheet','stock exp'])('finds full and partial names or native codes: %s',async value=>{
  vi.useFakeTimers();
  try {
    render(<ReportsHub company={company}/>);
    await act(async()=>{fireEvent.change(screen.getByRole('searchbox',{name:'Search reports'}),{target:{value}});await vi.advanceTimersByTimeAsync(1000);});
    const title=value.toLowerCase().includes('trial')?'Trial balance':value==='balance sheet'?'Balance sheet':'Stock expiry';
    expect(screen.getAllByRole('heading',{level:3})).toHaveLength(1);expect(screen.getByRole('heading',{level:3,name:title})).toBeVisible();
  } finally {vi.useRealTimers();}
});
it('recovers from no search results with the shared clear search control',async()=>{
  render(<ReportsHub company={company}/>);fireEvent.change(screen.getByRole('searchbox',{name:'Search reports'}),{target:{value:'not a report name'}});
  expect(await screen.findByText(/No reports match/)).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Clear search'}));
  expect(await screen.findByRole('heading',{level:3,name:'Day book'})).toBeVisible();
});
it('places four report submenus inside Books and Reports and keeps Masters in Administer',async()=>{
  const {session}=await pageContext();const books=navSections.find(section=>section.label==='Books and Reports')!;
  expect(books).toBeDefined();
  const reports=books.items.find(item=>item.href==='/reports')!;
  expect(reports.children?.map(item=>item.label)).toEqual(['Inventory reports','Finance reports','Tax reports','Analytics']);
  expect(reports.children?.map(item=>item.href)).toEqual(['/reports/inventory','/reports/finance','/reports/tax','/reports/analytics']);
  expect(reports.children?.every(item=>!item.children)).toBe(true);
  expect(navSections.find(section=>section.label==='Administer')!.items.find(item=>item.href==='/masters')?.children).toBeUndefined();
  const items=navigationFor(session).flatMap(section=>section.items);
  expect(flattenNavigation(items).filter(item=>item.href==='/reports')).toHaveLength(1);
  for(const category of ['inventory','finance','tax','analytics'])expect(sidebarCurrentHref(items,'/reports/'+category)).toBe('/reports/'+category);
  expect(sidebarCurrentHref(items,'/reports/workspace')).toBe('/reports');
});
  it('opens the selected finance report in its dedicated workspace',async()=>{
    render(await WorkspacePage({searchParams:Promise.resolve({report:'INCOME_EXPENSE'})}));expect(screen.getByText(/Finance workspace INCOME_EXPENSE/)).toBeVisible();
});
it('routes Profit and Loss to its dedicated workspace',async()=>{
  render(await WorkspacePage({searchParams:Promise.resolve({report:'PROFIT_LOSS'})}));
  expect(screen.getByText('Profit and Loss workspace')).toBeVisible();
});
it.each(['other company','expired','department','none'] as const)('rejects workspace and menu access from %s authority',async reason=>{
  const {session}=await pageContext();if(reason==='other company')session.grants![0].scope_id='other';if(reason==='expired')session.grants![0].valid_to='2000-01-01';if(reason==='department')session.grants![0].scope_type='department';if(reason==='none')session.grants=[];
  render(await WorkspacePage({}));expect(screen.getByRole('alert')).toBeVisible();expect(flattenNavigation(navigationFor(session).flatMap(section=>section.items)).some(item=>item.href==='/reports')).toBe(false);
});
it.each(['https://outside.invalid','../TRIAL_BALANCE','TRIAL_BALANCE?other=1'])('rejects unsafe report codes: %s',async report=>{
  await expect(WorkspacePage({searchParams:Promise.resolve({report})})).rejects.toThrow('not found');
});

it('routes retained Balance Sheet runs to the dedicated workspace',async()=>{
  render(await WorkspacePage({searchParams:Promise.resolve({report:'BALANCE_SHEET',run:'01990000-0000-7000-8000-000000000002'})}));
  expect(screen.getByText('Balance Sheet workspace')).toBeVisible();
});
