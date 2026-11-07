'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, Notice, ReviewList, SectionHeader, TextField, businessToday, useDisplayConfig, useFormatters } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { assertMasterFields, masterRequest } from '../lib/catalog-master-api';
import type { MasterFieldSet } from '../lib/catalog-masters';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useWarehouseCommand } from '../lib/warehouse-ui';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { CatalogMasterError } from './CatalogMasterDirectory';

type View = components['schemas']['ReleaseView'];
type Detail = components['schemas']['ReleaseDetail'];
type Input = components['schemas']['PolicyReleaseInput'];
const entity = 'catalog.catalog_policy_release';

export function WarehousePolicyReleases({ company, canPublish, generation }: { company: string; canPublish: boolean; generation?: number }) {
  const display = useDisplayConfig(), format = useFormatters(), command = useWarehouseCommand();
  const root = `/v1/companies/${company}/policy-releases`;
  const [data, setData] = useState<View | null>(null), [failure, setFailure] = useState<RequestFailure | null>(null);
  const [loading, setLoading] = useState(true), [revision, setRevision] = useState(0), [writable, setWritable] = useState(false);
  const [date, setDate] = useState(() => businessToday(display.timezone)), [reason, setReason] = useState('');
  const [review, setReview] = useState<Input | null>(null), [selected, setSelected] = useState<Detail | null>(null), [message, setMessage] = useState('');
  useUnsavedChanges(() => command.pending || command.uncertain || !!review);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null); setWritable(false);
    Promise.all([
      masterRequest<View>({ path: root, signal: controller.signal }),
      masterRequest<MasterFieldSet>({ path: `/v1/companies/${company}/entities/${entity}/field-set?operation=publish`, signal: controller.signal }),
    ]).then(([value, metadata]) => {
      if (controller.signal.aborted) return;
      if (!Number.isSafeInteger(value.policy_generation) || !Number.isSafeInteger(value.source_version) || !Array.isArray(value.history)) throw { status: 502, message: 'Release information could not be verified. Reload releases.' };
      const fields = assertMasterFields(metadata, company, entity);
      setWritable(['effective_date', 'change_reason'].every(key => fields.some(field => field.key === key && field.visible && field.writable)));
      setData(value); setSelected(null); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error, 'warehouse service')); setLoading(false); } });
    return () => controller.abort();
  }, [company, root, generation, revision]);
  const locked = loading || command.pending || command.uncertain;
  const current = selected ?? data?.current;
  async function history(id: string) {
    if (locked) return;
    setFailure(null);
    try {
      const value = await masterRequest<Detail>({ path: root + '/' + id });
      if (value.id !== id) throw { status: 502, message: 'The release response changed. Reload releases.' };
      setSelected(value);
    } catch (error) { setFailure(requestFailure(error, 'warehouse service')); }
  }
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title="Company policy releases" description="Publish the reviewed warehouse operations and activity defaults as one company release. Stock-service confirmation and retirement checks use this release." />
    <CatalogMasterError failure={failure} retry={() => setRevision(value => value + 1)} />
    {message && <Notice tone="success">{message}</Notice>}
    {loading ? <p role="status">Loading policy releases...</p> : data && <>
      <Notice>{data.current ? `Release ${data.current.revision ?? '—'} is in force. Delivery: ${data.current.delivery_state}.` : 'No company policy release is in force. Publish a release before retiring an empty warehouse.'}</Notice>
      {canPublish && writable ? <div className="janso-form-grid">
        <TextField label="Release effective date" type="date" required min={businessToday(display.timezone)} value={date} disabled={locked || !!review} onChange={event => setDate(event.target.value)} />
        <TextField label="Release change reason" required maxLength={500} value={reason} disabled={locked || !!review} onChange={event => setReason(event.target.value)} />
      </div> : <Notice>Company release publication requires warehouse management, publication and writable release fields.</Notice>}
      <div className="janso-form-actions">
        {canPublish && writable && <Button disabled={locked || !!review || !date || !reason.trim()} onClick={() => setReview({ effective_date: date, change_reason: reason.trim(), expected_generation: data.policy_generation, expected_source_version: data.source_version })}>Review company release</Button>}
        <Button variant="ghost" disabled={locked || !!review} onClick={() => setRevision(value => value + 1)}>Reload releases</Button>
        {data.current?.effective_date && canPublish && writable && <Button variant="ghost" disabled={locked || !!review || data.current.effective_date !== businessToday(display.timezone)} onClick={() => setReview({ effective_date: data.current!.effective_date!, change_reason: 'Retry delivery of reviewed warehouse policy', expected_generation: data.policy_generation, expected_source_version: data.source_version })}>Review delivery retry</Button>}
      </div>
      <SectionHeader title="Release history" />
      <ul>{(data.history ?? []).map(row => <li key={row.id}><Button variant="ghost" disabled={locked} onClick={() => void history(row.id)}>Release {row.revision ?? '—'}</Button> {row.effective_date ? format.date(row.effective_date) : 'Date unavailable'} · {row.delivery_state}</li>)}</ul>
      {current && <><SectionHeader title="Stock-service acknowledgements" /><ul>{(current.acknowledgements ?? []).map(row => <li key={row.id}>{row.consumer} · {row.aggregate} · {row.result}{row.reason_code ? ' · ' + row.reason_code : ''} · {format.dateTime(row.acknowledged_at)}</li>)}</ul>{!current.acknowledgements?.length && <p>No stock-service acknowledgement has arrived for this release.</p>}</>}
    </>}
    <ConfirmDialog open={!!review} title="Publish reviewed company warehouse policy?" confirmLabel={command.uncertain ? 'Retry same release' : 'Publish release'} busy={command.pending} error={command.failure?.message} onCancel={() => { if (!command.uncertain) { setReview(null); command.clear(); } }} onConfirm={async () => {
      if (!review || !canPublish || !writable) return;
      if (await command.execute(root, review)) { setReview(null); setReason(''); setMessage('Company policy release submitted. Check the delivery state and acknowledgements.'); setRevision(value => value + 1); }
    }}>
      {review && <ReviewList items={[{ label: 'Effective date', value: format.date(review.effective_date) }, { label: 'Reason', value: review.change_reason }, { label: 'Policy generation', value: String(review.expected_generation) }]} />}
      <p>This publishes the complete company warehouse policy. Retrying an unchanged same-day release retries delivery to stock services.</p>
      {command.uncertain && <Notice tone="warning">The release result is uncertain. Retry this same reviewed command to recover its result.</Notice>}
    </ConfirmDialog>
  </div></CardBody></Card>;
}
