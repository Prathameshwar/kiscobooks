'use client';
import { useEffect, useState } from 'react';
import { Select, useFormatters } from '@janso/ui';
import type { components } from '@janso/api-client/reports';
import { productFieldRequest as request } from '../lib/product-fields';
import { reportSourceSummary, type SourceSummary } from '../lib/report-source-summary';

export function ReportSources({ company, sources, value, onChange, disabled, inventory }: { company: string; sources: components['schemas']['ListItem'][]; value: string; onChange: (value: string) => void; disabled: boolean; inventory: boolean }) {
  const format = useFormatters();
  const [state, setState] = useState<{ company: string; details: Record<string, SourceSummary | null>; loading: boolean }>({ company, details: {}, loading: true });
  useEffect(() => {
    const controller = new AbortController(), details: Record<string, SourceSummary | null> = {};
    setState({ company, details, loading: true });
    const ready = sources.filter(row => row.status === 'READY').slice(0, 50);
    async function load() {
      for (let offset = 0; offset < ready.length && !controller.signal.aborted; offset += 5) {
        await Promise.all(ready.slice(offset, offset + 5).map(async row => {
          try {
            const result = await request<components['schemas']['GenerationDetail']>('reports', 'GET', `/v2/companies/${company}/report-generations/${row.id}`, undefined, undefined, controller.signal);
            details[row.id] = reportSourceSummary(company, row.id, result);
          } catch { details[row.id] = null; }
        }));
        if (!controller.signal.aborted) setState({ company, details: { ...details }, loading: offset + 5 < ready.length });
      }
      if (!controller.signal.aborted) setState({ company, details: { ...details }, loading: false });
    }
    void load();
    return () => controller.abort();
  }, [company, sources]);
  const details = state.company === company ? state.details : {};
  const coverage = (row: SourceSummary) => row.coverageStart ? 'Ledger from ' + format.date(row.coverageStart) + (row.completeLedger ? '' : ' · incomplete history') : 'Ledger coverage unavailable';
  return <div className="janso-flow">
    <Select label="Source snapshot" value={value} disabled={disabled} options={sources.filter(row => row.status === 'READY').map(row => ({ value: row.id, label: `Sequence ${row.applied_sequence ?? '—'} · ${details[row.id] ? coverage(details[row.id]!) : state.loading ? 'Checking coverage' : 'Coverage unavailable'} · ${row.id}` }))} onChange={onChange} />
    {state.loading && <p role="status">Checking source coverage</p>}
    {value && details[value] === null && <p>Coverage for the selected snapshot could not be verified. Refresh the workspace to retry; report creation will validate the source.</p>}
    {inventory && <p>Ready financial snapshots do not certify stock history. Stock coverage and compatibility are validated when this report is created.</p>}
  </div>;
}
