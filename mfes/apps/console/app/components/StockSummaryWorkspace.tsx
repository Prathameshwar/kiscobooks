'use client';

import type { FiscalYearChoice } from '../lib/company-context';
import { InventoryReportWorkspace } from './InventoryReportWorkspace';

/** Inventory route shares the tested Day Book report, paging and export shell. */
export function StockSummaryWorkspace(props:{company:string;companyName:string;actor:string;permissions:readonly string[];year?:FiscalYearChoice|null}) {
  return <InventoryReportWorkspace {...props} report="STOCK_SUMMARY" />;
}
