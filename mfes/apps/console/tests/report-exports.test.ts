import { afterEach, expect, it, vi } from 'vitest';
import type { components } from '@janso/api-client/reports';
import { productFieldRequest } from '../app/lib/product-fields';
import { primaryExportFormats, reportDownloadHref, reportExportOptions, canPreviewReportExport, trackReportExport } from '../app/lib/report-exports';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
type Job = components['schemas']['JobDetail'];
const views = [{ key: 'default', title: 'Report', columns: [{ key: 'number', title: 'Number', kind: 'TEXT' as const }] }];
const run = { status: 'COMPLETE' as const, completed_rows: 75, views };
const limits = primaryExportFormats.map(format => ({ format, max_rows: 100, max_cells: 1000 }));
const exported = (status: Job['status'] = 'QUEUED'): Job => ({
  id: 'export', kind: 'EXPORT', status, parameters: { format: 'PDF' }, delivery: 'SINGLE',
  attempt: 1, code: 'TEST_REPORT', completed_rows: 0, created_at: '2026-11-01T00:00:00Z',
  display: null, failure_code: null, generation_id: 'generation', origin: null,
  parent_id: 'run', result: null, title: 'Test report', version: 1, views,
});
afterEach(() => { vi.useRealTimers(); vi.resetAllMocks(); });

it('offers PDF, real Excel and CSV with the server-advertised capacities', () => {
  const options = reportExportOptions({ run, limits, view: 'default', formats: primaryExportFormats });
  expect(options.map(item => item.id)).toEqual(['PDF', 'XLSX', 'CSV']);
  expect(options.map(item => item.label)).toEqual(['PDF report', 'Excel workbook', 'CSV spreadsheet']);
  expect(options.every(item => !item.disabledReason)).toBe(true);
});
it('keeps mandatory formats visible with a clear reason when unavailable', () => {
  const options = reportExportOptions({ run, limits: limits.filter(item => item.format === 'CSV'), view: 'default', formats: primaryExportFormats });
  expect(options).toHaveLength(3);
  expect(options[0].disabledReason).toMatch(/not enabled/i);
  expect(options[1].disabledReason).toMatch(/not enabled/i);
  expect(options[2].disabledReason).toBeUndefined();
});
it('checks the complete result instead of the visible page, including row and cell bounds', () => {
  const options = reportExportOptions({ run: { ...run, completed_rows: 101 }, limits, view: 'default' });
  expect(options.every(item => item.disabledReason?.includes('100 rows'))).toBe(true);
  expect(reportExportOptions({ run, limits: [{ ...limits[0], max_cells: 74 }], view: 'default' })[0].disabledReason).toMatch(/cell limit/i);
});
it('accepts a verified streamed-result row count and treats an explicit missing count as unavailable', () => {
  const pinned = { ...run, completed_rows: 0 };
  expect(reportExportOptions({ run: pinned, limits, view: 'default', rowCount: 75 })[0].disabledReason).toBeUndefined();
  expect(reportExportOptions({ run: pinned, limits, view: 'default', rowCount: 101 })[0].disabledReason).toMatch(/100 rows/i);
  expect(reportExportOptions({ run: pinned, limits, view: 'default', rowCount: null })[0].disabledReason).toMatch(/row count/i);
});
it('rejects incomplete reports, missing row counts and incompatible calculation views', () => {
  expect(reportExportOptions({ run: null, limits, view: 'default' })[0].disabledReason).toMatch(/completed report/i);
  expect(reportExportOptions({ run: { ...run, status: 'RUNNING' }, limits, view: 'default' })[0].disabledReason).toMatch(/complete/i);
  expect(reportExportOptions({ run: { ...run, completed_rows: NaN }, limits, view: 'default' })[0].disabledReason).toMatch(/row count/i);
  expect(reportExportOptions({ run, limits, view: 'missing' })[0].disabledReason).toMatch(/view/i);
  const changed = { ...run, view: 'default', views: [...views, { ...views[0], key: 'summary', calculation: 'summary' }] };
  expect(reportExportOptions({ run: changed, limits, view: 'summary' })[0].disabledReason).toMatch(/new report/i);
});
it('uses existing packaged PDF delivery only within both row and part limits', () => {
  const input = { run: { ...run, completed_rows: 4000 }, view: 'default', limits: [{ format: 'PDF' as const, max_rows: 2000, max_cells: 10000 }], delivery: 'PACKAGE' as const, packageLimits: { max_rows: 5000, max_parts: 4 } };
  expect(reportExportOptions(input)[0].disabledReason).toBeUndefined();
  expect(reportExportOptions({ ...input, packageLimits: { ...input.packageLimits, max_parts: 3 } })[0].disabledReason).toMatch(/part limit/i);
  expect(reportExportOptions({ ...input, run: { ...run, completed_rows: 5001 } })[0].disabledReason).toMatch(/5,000 rows/);
});
it('uses the same scoped private download route and previews only a completed single PDF', () => {
  expect(reportDownloadHref('company', 'export')).toBe('/api/report-download?company=company&export=export');
  expect(reportDownloadHref('company', 'export', true)).toContain('&preview=1');
  expect(new URL(reportDownloadHref('a&company=b', 'x/y'), 'http://localhost').searchParams.get('company')).toBe('a&company=b');
  expect(canPreviewReportExport(exported('COMPLETE'))).toBe(true);
  expect(canPreviewReportExport(exported())).toBe(false);
  expect(canPreviewReportExport({ ...exported('COMPLETE'), delivery: 'PACKAGE' })).toBe(false);
  expect(canPreviewReportExport({ ...exported('COMPLETE'), parameters: { format: 'CSV' } })).toBe(false);
});
it('tracks queued and running exports sequentially through the existing API', async () => {
  vi.useFakeTimers();
  vi.mocked(productFieldRequest).mockResolvedValueOnce(exported('RUNNING')).mockResolvedValueOnce(exported('COMPLETE'));
  const update = vi.fn(), signal = new AbortController().signal;
  const result = trackReportExport('company', exported(), signal, update);
  await vi.advanceTimersByTimeAsync(1500); expect(update).toHaveBeenCalledWith(expect.objectContaining({ status: 'RUNNING' }));
  await vi.advanceTimersByTimeAsync(1500); expect((await result).status).toBe('COMPLETE');
  expect(productFieldRequest).toHaveBeenLastCalledWith('reports', 'GET', '/v2/companies/company/report-exports/export', undefined, undefined, signal);
  expect(vi.getTimerCount()).toBe(0);
});
it.each(['COMPLETE', 'FAILED', 'BLOCKED', 'CANCELLED'] as const)('stops tracking a %s export', async status => {
  expect((await trackReportExport('company', exported(status), new AbortController().signal)).status).toBe(status);
  expect(productFieldRequest).not.toHaveBeenCalled();
});
it('aborts a waiting poll without leaving timers or issuing a request', async () => {
  vi.useFakeTimers(); const controller = new AbortController();
  const result = trackReportExport('company', exported(), controller.signal);
  const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
  controller.abort(); await rejected; await vi.runAllTimersAsync();
  expect(productFieldRequest).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
});
it('does not apply an in-flight response after navigation aborts the request', async () => {
  vi.useFakeTimers(); const controller = new AbortController(), update = vi.fn();
  let finish!: (value: Job) => void;
  vi.mocked(productFieldRequest).mockImplementationOnce(() => new Promise<Job>(resolve => { finish = resolve; }));
  const result = trackReportExport('company', exported(), controller.signal, update);
  const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
  await vi.advanceTimersByTimeAsync(1500); controller.abort(); finish(exported('COMPLETE')); await rejected;
  expect(update).not.toHaveBeenCalled();
});
it('rejects a response for another job and propagates polling failures for recovery', async () => {
  vi.useFakeTimers();
  vi.mocked(productFieldRequest).mockResolvedValueOnce({ ...exported('COMPLETE'), id: 'other' });
  const mismatched = expect(trackReportExport('company', exported(), new AbortController().signal)).rejects.toThrow(/different export/i);
  await vi.advanceTimersByTimeAsync(1500); await mismatched;
  vi.mocked(productFieldRequest).mockRejectedValueOnce(new Error('Service unavailable'));
  const failed = expect(trackReportExport('company', exported(), new AbortController().signal)).rejects.toThrow('Service unavailable');
  await vi.advanceTimersByTimeAsync(1500); await failed;
  expect(vi.getTimerCount()).toBe(0);
});
