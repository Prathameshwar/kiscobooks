'use client';
import { useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, CardBody, Checkbox, ConfirmDialog, Notice, ReviewList, SectionHeader, useFormatters } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { operationLabels, useWarehouseCommand, useWarehouseRead, type WarehousePolicy, type WarehousePreview } from '../lib/warehouse-ui';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { CatalogMasterError } from './CatalogMasterDirectory';

export function WarehouseOperationPolicy({ company, id, canPublish }: { company: string; id: string; canPublish: boolean }) {
  const path = `/v1/companies/${company}/warehouses/${id}/operation-policy`, read = useWarehouseRead<WarehousePolicy>(company, path, 'catalog.warehouse_operation_policy_revision', canPublish, id), command = useWarehouseCommand(), format = useFormatters();
  const [draft, setDraft] = useState<Record<string, boolean>>({}), [preview, setPreview] = useState<WarehousePreview | null>(null), [failure, setFailure] = useState<RequestFailure | null>(null), [previewing, setPreviewing] = useState(false), [message, setMessage] = useState('');
  const previewBusy = useRef(false), alive = useRef(true), dirty = useRef(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (read.data && read.data.warehouse_id === id) { setDraft(Object.fromEntries(Object.keys(operationLabels).filter(key => typeof read.data!.current?.[key as keyof typeof operationLabels] === 'boolean').map(key => [key, read.data!.current![key as keyof typeof operationLabels] as boolean]))); dirty.current = false; } }, [read.data, id]);
  useUnsavedChanges(() => dirty.current || previewBusy.current || command.pending);
  const fields = read.fields.filter(field => field.visible && field.key in operationLabels);
  const complete = Object.keys(operationLabels).every(key => typeof draft[key] === 'boolean') && read.data?.warehouse_id === id;
  const editable = canPublish && complete && fields.some(field => field.writable);
  async function review() {
    if (!editable || previewBusy.current || command.pending || command.uncertain) return;
    previewBusy.current = true; setPreviewing(true); setFailure(null); setMessage('');
    try { const result = await masterRequest<WarehousePreview>({ path: path + '/preview', method: 'POST', body: draft });
      if (alive.current) {
        if (result.warehouse_id !== id) throw { status: 502, message: 'The preview did not match this warehouse.' };
        if (!result.publishable) { setFailure({ status: 422, message: (result.issues ?? []).map(issue => issue.message).join(' ') || 'This policy change cannot be published.' }); return; }
        setPreview(result); setDialogOpen(true);
      }
    } catch (error) { if (alive.current) setFailure(requestFailure(error, 'warehouse service')); }
    finally { previewBusy.current = false; if (alive.current) setPreviewing(false); }
  }
  return <Card><CardBody><div className="janso-flow"><SectionHeader title="Warehouse operations" description="Review the allowed activities for this location. Separate stock permissions still apply." />
    <CatalogMasterError failure={read.failure ?? failure} retry={read.refresh} />
    {command.uncertain && !dialogOpen ? <Notice tone="warning">The publication could not be confirmed. The reviewed proposal is retained. <Button variant="ghost" onClick={() => setDialogOpen(true)}>Recover publication</Button></Notice> : null}
    {read.loading ? <p role="status">Loading warehouse operations...</p> : read.data?.warehouse_id === id ? <>
      {read.data.current ? <><Badge tone={read.data.current.delivery_state === 'APPLIED' ? 'success' : 'warn'}>{read.data.current.delivery_state}</Badge>
        {read.data.current.delivery_state !== 'APPLIED' ? <Notice tone="warning">The stock service has not confirmed that this revision is applied. Publication does not confirm enforcement.</Notice> : null}</> : <Notice tone="warning">No reviewed operation policy is available. Ask an administrator to initialize warehouse settings.</Notice>}
      {message ? <Notice tone="success">{message}</Notice> : null}
      <div className="janso-flow">{fields.filter(field => field.key in draft).map(field => <Checkbox key={field.key} name={field.key} checked={draft[field.key]} disabled={!canPublish || !field.writable || previewing || command.pending || command.uncertain} onChange={event => { dirty.current = true; setDraft(current => ({ ...current, [field.key]: event.target.checked })); setPreview(null); setFailure(null); }}>{operationLabels[field.key as keyof typeof operationLabels]}</Checkbox>)}</div>
      {canPublish && !editable ? <Notice>Your field access or the available policy does not allow a complete change. No hidden values are assumed.</Notice> : null}
      <div className="janso-form-actions">{canPublish ? <Button disabled={!editable || command.uncertain} loading={previewing} onClick={() => void review()}>Review operation changes</Button> : null}
        <Button variant="ghost" disabled={command.pending || previewing || command.uncertain} onClick={() => { if (!dirty.current || window.confirm('Discard unsaved operation changes?')) { dirty.current = false; setPreview(null); command.clear(); read.refresh(); } }}>Reload operations</Button></div>
      <SectionHeader title="Policy history" /><ReviewList items={(read.data.history ?? []).map(row => ({ label: row.revision == null ? 'Policy revision' : 'Revision ' + row.revision, value: `${row.effective_from ? format.dateTime(row.effective_from) : 'Date unavailable'} · ${row.delivery_state}` }))} />
    </> : null}
    <ConfirmDialog open={!!preview && dialogOpen} title="Publish warehouse operation changes?" confirmLabel={command.uncertain ? 'Retry same publication' : 'Publish reviewed changes'} busy={command.pending} error={command.failure ? command.failure.message + (command.failure.status === 409 ? ' Cancel and reload operations to review the latest policy before trying again.' : '') : null} onCancel={() => { setDialogOpen(false); if (!command.uncertain) { setPreview(null); command.clear(); } }} onConfirm={async () => {
      if (!preview?.publishable || !complete || !canPublish) return;
      if (await command.execute(path + '/publish', { ...draft, expected_generation: preview.expected_generation, expected_source_version: preview.expected_source_version })) { dirty.current = false; setPreview(null); setMessage('Operation policy published. Check delivery status for stock-service confirmation.'); read.refresh(); }
    }}>
      <p>Changes apply through the stock service after acknowledgement. Existing policy history is retained.</p>
      {preview ? <><ReviewList items={Object.keys(operationLabels).map(key => ({ label: operationLabels[key as keyof typeof operationLabels], value: draft[key] ? 'Allowed' : 'Blocked' }))} />
        {(preview.issues ?? []).map(issue => <Notice key={issue.code} tone={preview.publishable ? 'info' : 'warning'}>{issue.message}</Notice>)}</> : null}
      {command.uncertain ? <Notice tone="warning">The publication could not be confirmed. Retry the same reviewed change to recover its result.</Notice> : null}
    </ConfirmDialog>
  </div></CardBody></Card>;
}
