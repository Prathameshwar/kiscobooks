'use client';
import {FinancialStatementWorkspace,type FinancialStatementProps} from './FinancialStatementWorkspace';
export function ProfitLossWorkspace(props:FinancialStatementProps){
  return <FinancialStatementWorkspace {...props} reportCode="PROFIT_LOSS"/>;
}
