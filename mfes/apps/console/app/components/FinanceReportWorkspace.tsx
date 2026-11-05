'use client';
import type {FinancialStatementProps} from './FinancialStatementWorkspace';
import {NativeBookWorkspace} from './NativeBookWorkspace';
import type {FinanceReportCode} from '../lib/finance-workspace';

export function FinanceReportWorkspace({report,initialParty,trialBalanceRun,...props}:FinancialStatementProps & {report:FinanceReportCode;initialParty?:string;trialBalanceRun?:string}){
  if(!props.permissions.includes('report.read'))return <p role="alert">Your report access is unavailable.</p>;
  return <NativeBookWorkspace key={props.company+':'+props.actor+':'+report+':'+(props.initialRun??'')} {...props} book="account-ledger" financeReport={report} initialParty={initialParty} trialBalanceRun={trialBalanceRun}/>;
}
