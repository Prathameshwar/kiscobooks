'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, FileUpload, Notice } from '@janso/ui';
import { requestFailure, type ServiceRequest } from '../lib/service-call';
import { downloadPurchaseFile, fileBase64, purchaseFileBase, purchaseFileCall, verifyPurchaseFile, type PurchaseStoredFile } from '../lib/purchase-files';

type Props = {
  company: string; voucher?: string; revision?: string; version?: number; enabled: boolean;
  editable: boolean; disabled: boolean; files: PurchaseStoredFile[];
  linkedKeys?: readonly string[];
  onChange: (files: PurchaseStoredFile[]) => void; onBusy: (busy: boolean) => void;
};
/** Uploads register private bytes. Apply + Save explicitly links them to a revision. */
export function PurchaseSupportingFiles({ company, voucher, revision, version, enabled, editable, disabled, files, linkedKeys = [], onChange, onBusy }: Props) {
  const [failure, setFailure] = useState(''), [pending, setPending] = useState(false);
  const [retry, setRetry] = useState<ServiceRequest | null>(null);
  const alive = useRef(true), busy = useRef(false);
  const currentFiles = useRef(files); currentFiles.current = files;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const send = async (request: ServiceRequest) => {
    if (busy.current || !voucher) return;
    busy.current = true; setPending(true); onBusy(true); setFailure(''); setRetry(request);
    try {
      const file = await purchaseFileCall<PurchaseStoredFile>(request); verifyPurchaseFile(file, company, voucher);
      if (!alive.current) return;
      onChange([...currentFiles.current.filter(row => row.object_key !== file.object_key), file]); setRetry(null);
    } catch (error) {
      if (alive.current) setFailure(error instanceof Error ? error.message : requestFailure(error, 'supporting file').message);
    } finally { busy.current = false; if (alive.current) { setPending(false); onBusy(false); } }
  };
  const select = async (file: File) => {
    if (!voucher || !version || busy.current) return;
    // Reading a 10 MiB local file is asynchronous too; guard repeat selection immediately.
    busy.current = true; setPending(true); onBusy(true); setFailure('');
    try {
      const content = await fileBase64(file); if (!alive.current) return;
      busy.current = false;
      await send({ path: purchaseFileBase(company, voucher), method: 'POST', key: crypto.randomUUID(), body: { expected_version: version, filename: file.name, media_type: file.type, content_base64: content } });
    } catch { if (alive.current) setFailure('The file could not be read. Select it again.'); }
    finally { busy.current = false; if (alive.current) { setPending(false); onBusy(false); } }
  };
  return <fieldset className="janso-entry-detail__group"><legend>Supporting files</legend>
    <p>PDF, PNG, JPEG or UTF-8 text, up to 10 MiB each. Upload, then apply bill details and save to attach the file to this Purchase. Removing a file preserves earlier saved revisions.</p>
    {!enabled ? <Notice title="Uploads unavailable">Ask your administrator to enable supporting files for this installation.</Notice> : !voucher ? <Notice title="Save the bill first">Save the first draft, then return here to add supporting files.</Notice> : null}
    {failure ? <Notice tone="danger" title="Supporting file needs attention">{failure}</Notice> : null}
    {pending ? <p role="status">Verifying supporting file…</p> : null}
    {retry && !pending ? <Button variant="ghost" disabled={disabled} onClick={() => void send(retry)}>Retry same file upload</Button> : null}
    {retry && !pending ? <Button variant="ghost" disabled={disabled} onClick={() => { setRetry(null); setFailure(''); }}>Choose a different file</Button> : null}
    <FileUpload label="Purchase supporting files" items={files.map(file => ({ id: file.object_key, name: file.filename, size: file.size_bytes, status: 'done' }))}
      accept="application/pdf,image/png,image/jpeg,text/plain" acceptLabel="PDF, PNG, JPEG or text" maxSizeBytes={10 * 1024 * 1024} maxFiles={20} multiple={false}
      disabled={disabled || pending || !editable || !enabled || !voucher || !!retry} onSelect={selected => { if (selected[0]) void select(selected[0]); }}
      onRemove={editable && !disabled && !pending ? item => onChange(files.filter(file => file.object_key !== item.id)) : undefined} />
    {voucher && revision ? files.filter(file => !!file.id && linkedKeys.includes(file.object_key)).map(file => <Button key={file.object_key} variant="ghost" disabled={disabled || pending} onClick={async () => {
      if (busy.current) return; busy.current = true; setPending(true); onBusy(true); setFailure('');
      try { await downloadPurchaseFile(company, voucher, revision, file); } catch (error) { if (alive.current) setFailure((error as Error).message); }
      finally { busy.current = false; if (alive.current) { setPending(false); onBusy(false); } }
    }}>Download {file.filename}</Button>) : null}
  </fieldset>;
}
