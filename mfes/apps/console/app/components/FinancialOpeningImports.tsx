'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, DataTable, FileUpload, Notice, Pager, ReviewList, SectionHeader, TextField, useFormatters, type Column } from '@janso/ui';
import { download, importBase, request, saveFile, sum, verifyJob, type Access, type Declaration, type Entry, type ImportJob } from '../lib/financial-opening';
import { useServiceCommand, useServiceList, useServiceRead } from '../lib/service-resource';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { FinancialOpeningAccount, FinancialOpeningDocumentEvidence, FinancialOpeningFieldErrors } from './FinancialOpeningCommon';
type Template = { marker: string; version: number; required_columns: string[]; optional_columns: string[]; maximum_file_bytes: number; maximum_file_rows: number; reference_policy: string; effect: string };
type ImportItem = { id: string; source_key: string; state: string; row_version: number; batch_id: string | null };
export function FinancialOpeningImports({ company, access, onChanged, onDirty }: { company: string; access: Access; onChanged: (batch: string | null) => void; onDirty: (dirty: boolean) => void }) {
  const format = useFormatters();
  const root = importBase(company);
  const [file, setFile] = useState<File | null>(null), [source, setSource] = useState(''), [job, setJob] = useState<ImportJob | null>(null), [error, setError] = useState(''), [working, setWorking] = useState(false), [action, setAction] = useState<'commit' | 'cancel' | null>(null);
  const command = useServiceCommand(request, 'opening import'), frozen = useRef<Parameters<typeof command.execute>[0] | null>(null), busy = useRef(false);
  const template = useServiceRead<Template>(root + '/template', request, value => {
    if (value.marker !== '_financial_opening_schema_version' || value.version !== 1 || !Array.isArray(value.required_columns) || !Array.isArray(value.optional_columns) || [...value.required_columns, ...value.optional_columns].some(key => !/^[a-z_]+$/.test(key))) throw { status: 502, message: 'Import template metadata could not be verified.' };
  });
  const list = useServiceList<ImportItem>(root, '', request);
  const locked = command.pending || command.uncertain || working;
  const capturedFor = useRef<string | null>(null);
  const captured = useServiceRead<Declaration>(job ? root + '/' + job.id + '/declaration' : undefined, request, value => {
    if (!Array.isArray(value.entries) || !value.source_id) throw { status: 502, message: 'The staged source could not be verified.' };
    capturedFor.current = job?.id ?? null;
  });
  const [reviewPage, setReviewPage] = useState(0);
  const [reviewEntry, setReviewEntry] = useState<Entry | null>(null);
  useEffect(() => { onDirty(!!file || locked || !!action); return () => onDirty(false); }, [file, locked, action, onDirty]);
  async function run(payload: Parameters<typeof command.execute>[0]) {
    frozen.current = payload;
    const result = await command.execute<ImportJob>(payload, verifyJob(company));
    if (result) { setJob(result); setFile(null); setAction(null); setReviewEntry(null); setReviewPage(0); list.first(); onChanged(result.batch_id); }
  }
  async function stage() {
    if (!file || locked || busy.current || !access.manage) return;
    if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/.test(source)) { setError('Enter a stable import reference containing letters, numbers, dots, colons, underscores or hyphens.'); return; }
    if (!template.data || !file.size || file.size > Math.min(2097152, template.data.maximum_file_bytes)) { setError('Choose a non-empty file up to 2 MiB.'); return; }
    busy.current = true; setWorking(true); setError('');
    try {
      const format = file.name.split('.').at(-1)?.toUpperCase();
      let body: { source_key: string; format: string; document?: Declaration; content_base64?: string };
      if (format === 'JSON') body = { source_key: source, format, document: JSON.parse(await file.text()) as Declaration };
      else if (['CSV', 'TSV', 'XLSX'].includes(format ?? '')) {
        const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
        for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        body = { source_key: source, format: format!, content_base64: btoa(binary) };
      } else throw new Error('Choose CSV, TSV, XLSX or JSON.');
      await run({ path: root, method: 'POST', body });
    } catch (failure) { setError(failure instanceof SyntaxError ? 'The JSON file is invalid. Use a complete opening declaration with decimal amounts as text.' : failure instanceof Error ? failure.message : 'The file could not be read. Review it and try again.'); }
    finally { busy.current = false; setWorking(false); }
  }
  async function load(id: string) {
    if (locked || file) return; setWorking(true); setError(''); setJob(null); setReviewEntry(null); setReviewPage(0);
    try { const result = await request<ImportJob>({ path: root + '/' + id }); verifyJob(company)(result); setJob(result); }
    catch { setError('The import could not be loaded. Access may have changed; reload history.'); }
    finally { setWorking(false); }
  }
  async function act(operation: 'validate' | 'commit' | 'prepare-drafts' | 'cancel') {
    if (!job || locked || !access.manage) return;
    await run({ path: root + '/' + job.id + '/' + operation, method: 'POST', body: { expected_version: job.row_version, ...(operation === 'commit' ? { review_hash: job.review_hash } : {}) } });
  }
  function csvTemplate() {
    if (!template.data) return;
    const columns = [template.data.marker, ...template.data.required_columns, ...template.data.optional_columns];
    saveFile(new Blob(['\uFEFF' + columns.join(',') + '\r\n'], { type: 'text/csv;charset=utf-8' }), 'account-party-opening-template.csv');
  }
  const columns: Column<ImportItem>[] = [
    { type: 'custom', key: 'source', header: 'Import reference', render: row => <Button variant="ghost" disabled={locked || !!file} onClick={() => void load(row.id)}>{row.source_key}</Button> },
    { type: 'custom', key: 'state', header: 'Status', render: row => row.state.replaceAll('_', ' ') },
    { type: 'custom', key: 'version', header: 'Version', render: row => String(row.row_version) },
  ];
  return <div className="janso-flow">
    <Card><CardBody><div className="janso-flow"><SectionHeader title="Import opening balances" description="Upload a complete, balanced migration declaration. Staging and validation never post money." />
      <AccountingFailure failure={template.failure} retry={template.refresh} />
      {template.data && <><Notice>{template.data.reference_policy} Maximum {template.data.maximum_file_rows.toLocaleString()} spreadsheet rows and 2 MiB. Keep UUIDs and exact decimal amounts as text in spreadsheets. Set the schema marker to 1 on each data row.</Notice><Button variant="ghost" disabled={locked} onClick={csvTemplate}>Download CSV template</Button></>}
      {error && <Notice tone="danger"><span role="alert">{error}</span></Notice>}
      {access.manage ? <><TextField label="Import reference" value={source} maxLength={100} disabled={locked} hint="Reuse the same source reference when retrying the same file." onChange={event => setSource(event.target.value)} />
        <FileUpload label="Opening balance file" accept=".csv,.tsv,.xlsx,.json" acceptLabel="CSV, TSV, XLSX or JSON" maxSizeBytes={2097152} maxFiles={1} disabled={locked} items={file ? [{ id: 'selected', name: file.name, size: file.size, status: working ? 'uploading' : 'pending' }] : []} onSelect={files => { setFile(files[0] ?? null); setError(''); }} onRemove={() => setFile(null)} />
        <Button disabled={!file || locked || !template.data} loading={working} onClick={() => void stage()}>Stage file for validation</Button></> : <Notice>Finance management access is required to import. Existing jobs remain readable.</Notice>}
    </div></CardBody></Card>
    <AccountingFailure failure={command.failure} retry={list.first} write />
    <FinancialOpeningFieldErrors failure={command.failure} />
    {command.uncertain && !action && <Button disabled={command.pending} onClick={() => frozen.current && void run(frozen.current)}>Retry the same import request</Button>}
    {job && <Card><CardBody><div className="janso-flow"><SectionHeader title={'Import ' + job.source_key} />
      <ReviewList items={[{ label: 'State', value: job.state }, { label: 'Prepared journals', value: String(job.journal_ids.length) }, { label: 'Draft preparation', value: job.drafts_complete ? 'Complete' : 'Remaining or not committed' }, { label: 'Opening status', value: job.opening_status ?? 'Not captured' }]} />
      <Notice>Commit creates a declaration and native drafts only. Posting and finalization are separate. Cancelling the job retains any declaration and drafts already created.</Notice>
      <AccountingFailure failure={captured.failure} retry={captured.refresh} />
      {captured.data && capturedFor.current === job.id && <><ReviewList items={[{ label: 'Source', value: captured.data.source_system + ' / ' + captured.data.source_id }, { label: 'Opening / covered through', value: format.date(captured.data.posting_date) + ' / ' + format.date(captured.data.covered_through) }, { label: 'Reporting mode', value: captured.data.coverage_mode ?? 'POST_CUTOVER_ONLY' }, { label: 'Account lines / documents', value: captured.data.entries.length + ' / ' + captured.data.entries.reduce((n, entry) => n + (entry.documents?.length ?? 0), 0) }, { label: 'Declared base debit / credit', value: importedTotal(captured.data, 'DEBIT') + ' / ' + importedTotal(captured.data, 'CREDIT') }]} />
        <DataTable caption="Imported account balances to review" columns={[
          { type: 'custom', key: 'source', header: 'Source', render: row => row.source_key },
          { type: 'custom', key: 'account', header: 'Account', render: row => <FinancialOpeningAccount company={company} id={row.account_id} /> },
          { type: 'custom', key: 'balance', header: 'Balance', render: row => row.side + ' · ' + row.amount + ' ' + row.currency },
          { type: 'custom', key: 'base', header: 'Base value', render: row => row.base_amount ?? 'Derived in validation' },
          { type: 'custom', key: 'documents', header: 'Documents', render: row => <Button variant="ghost" disabled={locked || !row.documents?.length} onClick={() => setReviewEntry(row)}>Review {row.documents?.length ?? 0} documents</Button> },
        ]} rows={captured.data.entries.slice(reviewPage * 25, (reviewPage + 1) * 25)} rowId={row => row.source_key} rowLabel={row => row.source_key} />
        <div className="janso-form-actions"><Button variant="ghost" disabled={reviewPage === 0 || locked} onClick={() => setReviewPage(n => n - 1)}>Previous imported lines</Button><Button variant="ghost" disabled={(reviewPage + 1) * 25 >= captured.data.entries.length || locked} onClick={() => setReviewPage(n => n + 1)}>Next imported lines</Button></div>
      </>}
      {reviewEntry && !captured.failure && <div className="janso-flow"><SectionHeader title={'Imported documents · ' + reviewEntry.source_key} /><FinancialOpeningDocumentEvidence key={reviewEntry.source_key} documents={reviewEntry.documents ?? []} currency={reviewEntry.currency} /></div>}
      {job.issues.length > 0 && <Notice tone="danger"><ul>{job.issues.map((issue, i) => <li key={i}>{String(issue.message ?? issue.code ?? 'Validation issue')}{issue.row ? ` · row ${String(issue.row)}` : ''}{issue.field ? ` · ${String(issue.field)}` : ''}</li>)}</ul></Notice>}
      <div className="janso-form-actions">
        <Button variant="ghost" disabled={!access.manage || locked || !!file || !['STAGED', 'BLOCKED', 'READY'].includes(job.state)} onClick={() => void act('validate')}>Validate import</Button>
        <Button disabled={!access.manage || locked || !!file || job.state !== 'READY' || !job.review_hash || !captured.data || capturedFor.current !== job.id || !!captured.failure || captured.loading} onClick={() => setAction('commit')}>Commit reviewed import</Button>
        <Button variant="ghost" disabled={!access.manage || locked || !!file || job.state !== 'COMMITTED' || job.drafts_complete} onClick={() => void act('prepare-drafts')}>Prepare remaining import drafts</Button>
        <Button variant="ghost" disabled={!access.manage || locked || !!file || job.state === 'CANCELLED'} onClick={() => setAction('cancel')}>Cancel import job</Button>
        {access.export && <Button variant="ghost" disabled={locked} onClick={async () => { setWorking(true); try { await download(root + '/' + job.id + '/report-ticket', company); } catch { setError('The private import report is unavailable. Reload and review access.'); } finally { setWorking(false); } }}>Download validation report</Button>}
      </div>
    </div></CardBody></Card>}
    <AccountingFailure failure={list.failure} retry={list.first} />
    <Card><DataTable caption="Opening import history" columns={columns} rows={list.data?.items ?? []} rowId={row => row.id} rowLabel={row => row.source_key} loading={list.loading} emptyTitle="No opening imports" emptyBody="Staged jobs remain here so preparation can resume later." /><Pager count={list.data?.items.length ?? 0} limit={list.limit} busy={list.loading || locked} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} noun="import" /></Card>
    <ConfirmDialog open={!!action} busy={command.pending} title={action === 'commit' ? 'Commit the reviewed import?' : 'Cancel this import job?'} confirmLabel={command.uncertain ? 'Retry the same request' : action === 'commit' ? 'Create declaration and drafts' : 'Cancel job'} onCancel={() => { if (!locked) setAction(null); }} onConfirm={() => command.uncertain && frozen.current ? void run(frozen.current) : action && void act(action)}>
      {command.uncertain ? 'The outcome is unconfirmed. Retry preserves the exact body and idempotency key.' : action === 'commit' ? 'The reviewed file will create the company declaration and at most two native journal drafts. No balances are posted. Changed master data or authority requires validation again.' : 'This stops the import job. Existing financial evidence and independently created drafts are retained.'}
      {command.failure && <p role="alert">{command.failure.message}</p>}
    </ConfirmDialog>
  </div>;
}
function importedTotal(value: Declaration, side: string) {
  try { return sum(value.entries.filter(entry => entry.side === side).map(entry => entry.base_amount ?? (entry.currency === value.currency ? entry.amount : ''))); }
  catch { return 'Calculated by server validation'; }
}
