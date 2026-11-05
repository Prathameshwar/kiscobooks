import type { components } from '@janso/api-client/reports';

export type SourceSummary = { coverageStart: string | null; completeLedger: boolean; sequence: number };
export function reportSourceSummary(company: string, id: string, detail: components['schemas']['GenerationDetail']): SourceSummary {
  const manifest = detail?.manifest, control = manifest?.control as Record<string, unknown> | undefined;
  if (detail?.id !== id || detail.status !== 'READY' || manifest?.company_id !== company || !Number.isSafeInteger(detail.applied_sequence) || !control || !['RETAINED_LEDGER', 'INCOMPLETE'].includes(String(control.coverage_kind))) throw new Error('Source coverage is unavailable or could not be verified.');
  const date = control.coverage_start;
  if (date !== null && (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date))) throw new Error('Source coverage is unavailable or could not be verified.');
  return { coverageStart: date as string | null, completeLedger: control.coverage_kind === 'RETAINED_LEDGER', sequence: detail.applied_sequence };
}
