/** Shared browser mechanisms for the existing Reports export/artifact framework. */
import type { components } from '@janso/api-client/reports';
import { productFieldRequest as request } from './product-fields';

type Schemas = components['schemas'];
type Job = Schemas['JobDetail'];
export type ReportExportFormat = Schemas['ExportRequest']['format'];
export const primaryExportFormats = ['PDF', 'XLSX', 'CSV'] as const;
export const reportExportLabels: Record<ReportExportFormat, string> = {
  PDF: 'PDF report', XLSX: 'Excel workbook', CSV: 'CSV spreadsheet', HTML: 'HTML document',
};
type ExportRun = Pick<Job, 'status' | 'completed_rows' | 'views' | 'view'>;
type Limit = Pick<Schemas['ExportDefinition'], 'format' | 'max_rows' | 'max_cells'>;
export type ReportExportOption = {
  id: ReportExportFormat; label: string; delivery: 'SINGLE' | 'PACKAGE'; disabledReason?: string;
};

/** Capacity uses all retained result rows and the selected registered view, never the UI page. */
export function reportExportOptions({ run, limits = [], view, formats = limits.map(item => item.format), delivery = 'SINGLE', packageLimits, rowCount: suppliedRowCount }: {
  run: ExportRun | null; limits?: readonly Limit[]; view: string; formats?: readonly ReportExportFormat[];
  delivery?: 'SINGLE' | 'PACKAGE'; packageLimits?: { max_rows?: number; max_parts?: number }; rowCount?: number | null;
}): ReportExportOption[] {
  const rowCount = suppliedRowCount !== undefined ? suppliedRowCount : run?.completed_rows;
  return [...new Set(formats)].map(id => {
    const limit = limits.find(item => item.format === id);
    const packaged = delivery === 'PACKAGE' && (id === 'PDF' || id === 'HTML');
    const selected = run?.views?.find(item => item.key === view);
    const retained = run?.views?.find(item => item.key === (run.view ?? 'default'));
    let disabledReason: string | undefined;
    if (!limit) disabledReason = 'This format is not enabled. Ask your administrator to check report exports.';
    else if (!run || run.status !== 'COMPLETE') disabledReason = 'Create a completed report before exporting.';
    else if (!selected || !selected.columns.length) disabledReason = 'Select an available report view before exporting.';
    else if (!retained || (selected.calculation ?? 'detail') !== (retained.calculation ?? 'detail')) disabledReason = 'Create a new report to use this calculation view.';
    else if (!Number.isSafeInteger(rowCount) || (rowCount ?? -1) < 0) disabledReason = 'The report row count is unavailable. Refresh the report.';
    else {
      const maximum = packaged ? packageLimits?.max_rows ?? limit.max_rows : limit.max_rows;
      if (rowCount! > maximum) disabledReason = `This format supports up to ${maximum.toLocaleString('en-IN')} rows. Narrow the period or choose another format.`;
      else if (!packaged && rowCount! * selected.columns.length > limit.max_cells) disabledReason = 'This view exceeds the cell limit for this format. Narrow the period or choose another format.';
      else if (packaged) {
        const partRows = Math.min(id === 'PDF' ? 1000 : 10000, limit.max_rows, Math.floor(limit.max_cells / selected.columns.length));
        if (!packageLimits?.max_parts || partRows < 1 || Math.ceil(rowCount! / partRows) > packageLimits.max_parts) disabledReason = 'This result exceeds the document part limit. Narrow the period or use Excel/CSV.';
      }
    }
    return { id, label: reportExportLabels[id], delivery: packaged ? 'PACKAGE' : 'SINGLE', ...(disabledReason ? { disabledReason } : {}) };
  });
}

export function reportDownloadHref(company: string, identity: string, preview = false): string {
  const query = new URLSearchParams({ company, export: identity });
  if (preview) query.set('preview', '1');
  return '/api/report-download?' + query;
}

export function canPreviewReportExport(job: Job): boolean {
  return job.status === 'COMPLETE' && job.parameters?.format === 'PDF' && job.delivery !== 'PACKAGE' && job.parameters?.delivery !== 'PACKAGE';
}

export function reportExportFailure(job: Job): string {
  if (job.status === 'CANCELLED') return 'The export was cancelled. Choose a format to prepare it again.';
  if (job.failure_code === 'AUTHORITY_REVOKED') return 'Your export access has changed. Refresh the page to check your current access.';
  if (job.failure_code === 'REPORT_CAPACITY_EXCEEDED') return 'The export exceeds the supported capacity. Narrow the period or choose another format.';
  return 'The export could not complete. Retry or select another format.';
}

function pause(signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 1500);
    signal.addEventListener('abort', abort, { once: true });
  });
}

/** Sequential, abortable polling shared by report screens; terminal failures remain reviewable. */
export async function trackReportExport(company: string, initial: Job, signal: AbortSignal, update?: (job: Job) => void): Promise<Job> {
  let current = initial;
  signal.throwIfAborted();
  while (current.status === 'QUEUED' || current.status === 'RUNNING') {
    await pause(signal);
    const next = await request<Job>('reports', 'GET', '/v2/companies/' + encodeURIComponent(company) + '/report-exports/' + encodeURIComponent(initial.id), undefined, undefined, signal);
    signal.throwIfAborted();
    if (next.id !== initial.id || next.kind !== 'EXPORT') throw new Error('The status response belongs to a different export. Refresh the report.');
    current = next; update?.(current);
  }
  return current;
}
