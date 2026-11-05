'use client';
import {FinancialStatementWorkspace,type FinancialStatementProps} from './FinancialStatementWorkspace';
export function BalanceSheetWorkspace(props:FinancialStatementProps){
  return <FinancialStatementWorkspace {...props} reportCode="BALANCE_SHEET"/>;
}
