import {ControlReportWorkspace} from '../../components/ControlReportWorkspace';
import {isControlReport} from '../../lib/control-workspace';
import {FinanceReportWorkspace} from '../../components/FinanceReportWorkspace';
import {isFinanceReport} from '../../lib/finance-workspace';
import { notFound } from 'next/navigation';
import { ErrorState, PageNavigation } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { NoCompany } from '../../components/NoCompany';
import { ReportWorkspace } from '../../components/ReportWorkspace';
import { TrialBalanceWorkspace } from '../../components/TrialBalanceWorkspace';
import { BalanceSheetWorkspace } from '../../components/BalanceSheetWorkspace';
import { ProfitLossWorkspace } from '../../components/ProfitLossWorkspace';
import { InventoryReportWorkspace } from '../../components/InventoryReportWorkspace';
import { isInventoryReport } from '../../lib/inventory-workspace';
import {AnalyticsReportWorkspace} from '../../components/AnalyticsReportWorkspace';
import {isAnalyticsReport} from '../../lib/analytics-workspace';
import {TaxReportWorkspace} from '../../components/TaxReportWorkspace';
import {Gstr3bWorkspace} from '../../components/Gstr3bWorkspace';
import {Gstr1Workspace} from '../../components/Gstr1Workspace';
import {isTaxReport} from '../../lib/tax-workspace';
import { pageContext } from '../../lib/page-context';
import { companyPermission } from '../../lib/company-permissions';
import { trackingId } from '../../lib/stock-tracking-resources';

export default async function WorkspacePage({ searchParams = Promise.resolve({}) }: { searchParams?: Promise<{ report?: string; party_id?: string; run?:string; trial_balance_run?:string }> }) {
  const query = await searchParams;
  if (query.report !== undefined && (typeof query.report !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(query.report))) notFound();
  if (query.party_id !== undefined && (query.report !== 'PARTY_LEDGER' || typeof query.party_id !== 'string' || !trackingId.test(query.party_id))) notFound();
  if(query.run!==undefined&&(!(['TRIAL_BALANCE','PROFIT_LOSS','BALANCE_SHEET','ACCOUNT_LEDGER'].includes(query.report??'')||isFinanceReport(query.report)||isAnalyticsReport(query.report)||isControlReport(query.report))||!trackingId.test(query.run)))notFound();
  if(query.trial_balance_run!==undefined&&(query.report!=='ACCOUNT_LEDGER'||!query.run||!trackingId.test(query.trial_balance_run)))notFound();
  const { session, context } = await pageContext(), company = session.company.id;
  const permissions = session.permissions.filter(key => companyPermission(session, key, company));
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/reports">
    {!company ? <NoCompany action="report on" context={context} canCreate={companyPermission(session, 'company.create')} />
      : !companyPermission(session, 'report.read', company) ? <ErrorState status={403} />
      : query.report === 'TRIAL_BALANCE' ? <TrialBalanceWorkspace key={company+':'+session.user.id} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear} years={context.fiscalYears} initialRun={query.run}/>
      : query.report === 'BALANCE_SHEET' ? <BalanceSheetWorkspace key={company+':'+session.user.id} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear} years={context.fiscalYears} initialRun={query.run}/>
      : query.report === 'PROFIT_LOSS' ? <ProfitLossWorkspace key={company+':'+session.user.id} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear} years={context.fiscalYears} initialRun={query.run}/>
      : isFinanceReport(query.report) ? <FinanceReportWorkspace report={query.report} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear} years={context.fiscalYears} initialRun={query.run} initialParty={query.party_id} trialBalanceRun={query.trial_balance_run}/>
      : isControlReport(query.report) ? <ControlReportWorkspace report={query.report} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear} years={context.fiscalYears} initialRun={query.run}/>
      : query.report === 'GSTR3B' ? <Gstr3bWorkspace key={company+':'+session.user.id} company={company} permissions={permissions} />
      : query.report === 'GSTR1' ? <Gstr1Workspace key={company+':'+session.user.id} company={company} permissions={permissions} />
      : isAnalyticsReport(query.report) ? <AnalyticsReportWorkspace report={query.report} key={company+':'+session.user.id+':'+query.report} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear} initialRun={query.run}/>
      : isInventoryReport(query.report) ? <InventoryReportWorkspace report={query.report} key={company+':'+session.user.id+':'+query.report} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear} />
      : isTaxReport(query.report) ? <TaxReportWorkspace report={query.report} key={company+':'+session.user.id+':'+query.report} company={company} companyName={session.company.name} actor={session.user.id??''} permissions={permissions} year={context.fiscalYear}/>
      : <div className="janso-page"><PageNavigation back={{ href: '/reports', label: 'reports' }} breadcrumbs={[{ label: 'Reports', href: '/reports' }, { label: 'Report workspace' }]} />
        {query.trial_balance_run&&<a href={'/reports/workspace?'+new URLSearchParams({report:'TRIAL_BALANCE',run:query.trial_balance_run})}>Back to Trial Balance</a>}
        <ReportWorkspace key={[company,session.user.id,query.report,query.party_id,query.run].join(':')} company={company} permissions={permissions} year={context.fiscalYear} years={context.fiscalYears} initialReport={query.report} initialParty={query.party_id} initialRun={query.run}/></div>}
  </ConsoleShell></Providers>;
}
