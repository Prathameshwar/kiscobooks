'use client';

import type { FiscalYearChoice } from '../lib/company-context';
import type { InventoryReportCode } from '../lib/inventory-workspace';
import { NativeBookWorkspace } from './NativeBookWorkspace';

export function InventoryReportWorkspace({ report, ...props }: { report: InventoryReportCode; company: string; companyName: string; actor: string; permissions: readonly string[]; year?: FiscalYearChoice | null }) {
  return <NativeBookWorkspace {...props} book="stock-summary" inventoryReport={report} />;
}
