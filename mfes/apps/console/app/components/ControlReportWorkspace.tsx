'use client';
import type {FinancialStatementProps} from './FinancialStatementWorkspace';
import type {ControlReportCode} from '../lib/control-workspace';
import {NativeBookWorkspace} from './NativeBookWorkspace';

export function ControlReportWorkspace({report,...props}:FinancialStatementProps & {report:ControlReportCode}){
 if(!props.permissions.includes('report.read'))return <p role="alert">Your report access is unavailable.</p>;
 return <NativeBookWorkspace key={props.company+':'+props.actor+':'+report+':'+(props.initialRun??'')} {...props} book="account-ledger" controlReport={report}/>;
}
