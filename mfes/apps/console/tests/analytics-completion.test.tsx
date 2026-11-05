import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {AnalyticsReportWorkspace} from '../app/components/AnalyticsReportWorkspace';
import {ControlReportWorkspace} from '../app/components/ControlReportWorkspace';
import {controlWorkspaces,type ControlReportCode} from '../app/lib/control-workspace';
import {analyticsCodes} from '../app/lib/analytics-workspace';
import {productFieldRequest} from '../app/lib/product-fields';
import {completionFixture} from './analytics-completion-fixture';
import {trialProps,trialJob} from './trial-balance-fixture';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
beforeEach(()=>{vi.mocked(productFieldRequest).mockReset();localStorage.clear();vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});});
afterEach(()=>vi.restoreAllMocks());

it.each(Object.keys(controlWorkspaces) as ControlReportCode[])('opens %s as a dedicated report and exports its retained view',async code=>{
 const fixture=completionFixture(code);vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<ControlReportWorkspace {...trialProps} report={code} initialRun={trialJob.id}/>);
 await screen.findByText('1 '+controlWorkspaces[code].resultNoun);
 expect(screen.getByRole('link',{name:'Analytics'})).toHaveAttribute('href','/reports/analytics');
 expect(screen.getByRole('heading',{name:controlWorkspaces[code].title})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Print / PDF'}));
 const link=await screen.findByRole('link',{name:'Download report'});
 expect(link.closest('.janso-finance-status')).not.toBeNull();
 expect(vi.mocked(productFieldRequest).mock.calls.find(call=>call[2].endsWith('/exports'))?.[3]).toMatchObject({view:'default',format:'PDF'});
});

it('uses the complete selected financial year for continuity, even before year end',async()=>{
 const fixture=completionFixture('BALANCE_CONTINUITY');vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<ControlReportWorkspace {...trialProps} report="BALANCE_CONTINUITY" years={[trialProps.year]}/>);
 await screen.findByText('1 continuity checks');
 expect(vi.mocked(productFieldRequest).mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))?.[3]).toMatchObject({parameters:{date_from:'2026-04-01',date_to:'2027-03-31'}});
 fireEvent.click(screen.getByRole('button',{name:'Filters'}));
 expect(screen.getByLabelText('Financial year to review')).toHaveValue(trialProps.year.id);
});

it('keeps source reconciliation snapshot-wide without period inputs',async()=>{
 const fixture=completionFixture('SOURCE_RECONCILIATION');vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<ControlReportWorkspace {...trialProps} report="SOURCE_RECONCILIATION"/>);
 await screen.findByText('1 source checks');fireEvent.click(screen.getByRole('button',{name:'Filters'}));
 expect(screen.queryByLabelText('From date')).toBeNull();expect(screen.queryByLabelText('To date')).toBeNull();
 expect(vi.mocked(productFieldRequest).mock.calls.find(call=>call[1]==='POST'&&call[2].endsWith('/report-runs'))?.[3]).toMatchObject({parameters:{}});
});

it('uses verified invoice and account selectors for the invoice bridge',async()=>{
 const fixture=completionFixture('INVOICE_GL_BRIDGE');vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<ControlReportWorkspace {...trialProps} report="INVOICE_GL_BRIDGE"/>);
 await screen.findByText('1 posted effects');fireEvent.click(screen.getByRole('button',{name:'Filters'}));
 expect(screen.getByRole('combobox',{name:'Invoice'})).toBeVisible();
 expect(screen.getByRole('combobox',{name:'Ledger account'})).toBeVisible();
});

it.each(analyticsCodes)('preserves frozen formatting in %s figures and rows',async code=>{
 const fixture=completionFixture(code);fixture.job.display={...fixture.job.display,amount_precision:4,date_format:'yyyy-MM-dd'};
 vi.mocked(productFieldRequest).mockImplementation(fixture.request as typeof productFieldRequest);
 render(<AnalyticsReportWorkspace {...trialProps} report={code} initialRun={trialJob.id}/>);
 const insights=await screen.findByRole('region',{name:'Business insights'});
 expect(within(insights).getByText(/Applied period 2026-04-01/)).toBeVisible();
 expect(insights.textContent).toMatch(/\.0000/);
 await waitFor(()=>expect(screen.getByRole('button',{name:'Print / PDF'})).toBeEnabled());
});

it('denies control workspaces without report access',()=>{
 render(<ControlReportWorkspace {...trialProps} permissions={[]} report="SOURCE_RECONCILIATION"/>);
 expect(screen.getByRole('alert')).toHaveTextContent('access is unavailable');expect(productFieldRequest).not.toHaveBeenCalled();
});
